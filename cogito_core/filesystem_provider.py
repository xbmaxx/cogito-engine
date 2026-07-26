"""
filesystem_provider.py — 通用本地文件系统搜索。

用 ripgrep 搜索本地 markdown 目录，适配 Obsidian / Logseq / 任何 .md 文件目录。
不绑定特定应用——同一个 Provider，换 path 适配不同知识源。
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import List

from .knowledge_provider import KnowledgeProvider

logger = logging.getLogger(__name__)

# YAML frontmatter 分隔符
_YAML_RE = re.compile(r"^---\s*$", re.MULTILINE)


class FileSystemProvider(KnowledgeProvider):
    """通用本地文件搜索 — 按 path + glob 搜索 markdown 文件。

    不绑定特定应用（Obsidian / Logseq / 飞书导出 / ...），
    同一个 Provider，换 path 就能适配不同知识源。

    首次 search() 时预热文件列表，后续利用缓存快速检索。
    """

    def __init__(
        self,
        path: str,
        glob: str = "*.md",
        label: str = "filesystem",
    ) -> None:
        """初始化。

        Args:
            path: 知识库根目录
            glob: 文件匹配模式（如 "*.md"）
            label: 显示名（如 "Obsidian Vault"）
        """
        self._path = Path(path).expanduser()
        self._glob = glob
        self._label = label
        self._file_list: List[Path] = []
        self._warmed = False

    def name(self) -> str:
        return self._label

    def available(self) -> bool:
        """目录存在且有匹配文件即为可用。"""
        if not self._path.exists():
            return False
        try:
            return any(self._path.glob(self._glob))
        except Exception:
            return False

    def search(self, query: str, limit: int = 3) -> List[str]:
        """用 ripgrep 搜索知识库目录。"""
        if not self.available():
            return []

        if not self._warmed:
            self._warm()

        # 拆分为单词，每个单独搜索（ripgrep 不支持中文短语）
        words = query.split()
        if len(words) <= 1:
            patterns = ["-e", query]
        else:
            patterns = []
            for w in words:
                patterns.extend(["-e", w])

        try:
            result = subprocess.run(
                [
                    "rg",
                    "--no-heading",
                    "--with-filename",
                    "--max-count=2",
                    "--max-filesize=1M",
                    "--glob", self._glob,
                    *patterns,
                    str(self._path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode > 1:
                logger.debug("ripgrep 搜索失败: %s", result.stderr[:200])
                return []

            lines = result.stdout.strip().split("\n")
            snippets = []
            for line in lines:
                if not line.strip():
                    continue
                cleaned = self._strip_frontmatter(line)
                if cleaned:
                    if ":" in cleaned:
                        cleaned = cleaned.split(":", 1)[1].strip()
                    if cleaned and len(cleaned) > 10:
                        snippets.append(cleaned[:300])
                if len(snippets) >= limit:
                    break

            return snippets[:limit]

        except FileNotFoundError:
            logger.debug("ripgrep 未安装，降级为 Python 文件遍历")
            return self._fallback_search(query, limit)
        except Exception as exc:
            logger.debug("FileSystemProvider.search() 失败: %s", exc)
            return []

    def _warm(self) -> None:
        """预热：缓存目录下所有匹配文件路径。"""
        try:
            self._file_list = list(self._path.rglob(self._glob))
        except Exception:
            self._file_list = []
        self._warmed = True

    def _fallback_search(self, query: str, limit: int) -> List[str]:
        """无 ripgrep 时的 Python 原生降级搜索。"""
        if not self._warmed:
            self._warm()

        keywords = query.lower().split()
        results = []
        for fp in self._file_list:
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
                text = self._remove_frontmatter(text)
                # 检查文件级匹配：所有关键词都在文件中
                if not all(kw in text.lower() for kw in keywords):
                    continue
                # 提取匹配行（只需包含任一关键词即可）
                for line in text.split("\n"):
                    if any(kw in line.lower() for kw in keywords) and line.strip():
                        results.append(line.strip()[:300])
                        if len(results) >= limit:
                            return results
            except Exception:
                continue
        return results[:limit]

    def _strip_frontmatter(self, line: str) -> str:
        """ripgrep 输出可能包含 frontmatter 行，去掉元数据行。"""
        # ripgrep 输出格式: "path:content"
        # 提取 content 部分
        if ":" in line:
            content = line.split(":", 1)[1]
        else:
            content = line

        stripped = content.strip().lstrip("---").strip()
        # frontmatter 元数据字段（tag/alias/date 等）
        fm_keys = ["tags:", "aliases:", "created:", "updated:", "date:", "cssclasses:"]
        if any(stripped.startswith(k) for k in fm_keys):
            return ""
        return line

    @staticmethod
    def _remove_frontmatter(text: str) -> str:
        """去掉 YAML frontmatter 块。"""
        if text.startswith("---"):
            parts = _YAML_RE.split(text, maxsplit=2)
            if len(parts) >= 3:
                return parts[2]
        return text

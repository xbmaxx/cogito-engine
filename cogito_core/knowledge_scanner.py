"""
knowledge_scanner.py — 全量知识源探针 + 决策引擎。

网关启动时一次性扫描用户本地所有可接入的知识源：
  1. Hermes 注册的工具（fact_store / rag / ...）
  2. 本地文件系统（Obsidian vault / Logseq graph / ...）
  3. 本地 SQLite 知识库（knowledge_base.db / memory_store.db）

决策规则：
  - 0 个源 → 静默降级
  - 1 个源 → 自动接入
  - 2+ 个源 → 提示用户选择一个
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class KnowledgeSource:
    """扫描发现的单个知识源。"""

    provider_type: str          # "hermes_tool" | "filesystem" | "sqlite"
    label: str                  # 中文名："Hermes 记忆库"
    description: str = ""       # 完整描述
    path: str = ""              # 文件系统路径（filesystem/sqlite 用）
    tool_name: str = ""         # Hermes 工具名（hermes_tool 用）
    glob: str = ""              # 文件过滤模式（filesystem 用）
    priority: int = 0           # 排序优先级


class DecisionEngine:
    """多源决策：0 静默 / 1 自动 / 2+ 提示用户选择。"""

    def __init__(self) -> None:
        self._sources: List[KnowledgeSource] = []
        self._chosen: Optional[KnowledgeSource] = None
        self.needs_prompt = False

    def decide(self, sources: List[KnowledgeSource]) -> Optional[KnowledgeSource]:
        """根据源数量做决策。

        Returns:
            选中的源，或 None（0 源 / 多源待用户选择）。
        """
        self._sources = sorted(sources, key=lambda s: s.priority, reverse=True)
        self.needs_prompt = False

        if len(self._sources) == 0:
            logger.debug("KnowledgeScanner: 0 knowledge sources found")
            return None

        if len(self._sources) == 1:
            s = self._sources[0]
            logger.info("KnowledgeScanner: auto-selected '%s'", s.label)
            self._chosen = s
            return s

        # 2+ sources: prompt user
        self.needs_prompt = True
        logger.info(
            "KnowledgeScanner: %d sources found, prompting user",
            len(self._sources),
        )
        return None

    def get_prompt(self) -> str:
        """生成用户选择提示文本。"""
        if not self._sources:
            return ""

        lines = ["检测到以下外部知识库，您想接入哪一个？\n"]
        for i, s in enumerate(self._sources, 1):
            desc = s.description or f"{s.label}（{s.path}）"
            lines.append(f"  {i}. {s.label} — {desc}")

        lines.append("\n回复编号即可（如 '1'），或输入名称切换。")
        return "\n".join(lines)

    @property
    def sources(self) -> List[KnowledgeSource]:
        return self._sources

    def select(self, index: int) -> Optional[KnowledgeSource]:
        """用户选择编号（1-based）。"""
        if 0 <= index < len(self._sources):
            self._chosen = self._sources[index]
            return self._chosen
        return None


class KnowledgeScanner:
    """全量探针 — 扫描本地所有可接入的知识源。

    不绑定具体应用名（Holographic / Obsidian / ...），
    按存储类型分类扫描：Hermes 工具 / 文件系统 / SQLite。
    """

    def __init__(self, ctx: Any = None) -> None:
        """初始化。

        Args:
            ctx: Hermes 插件上下文（有 tools 属性时可探测 Hermes 工具）。
                 传 None 时跳过 Hermes 工具探测。
        """
        self._ctx = ctx

    def scan(self) -> List[KnowledgeSource]:
        """全量扫描，返回所有发现的知识源（按 priority 降序）。"""
        sources: List[KnowledgeSource] = []
        sources.extend(self._probe_hermes_tools())
        sources.extend(self._probe_filesystem())
        sources.extend(self._probe_sqlite())
        sources.sort(key=lambda s: s.priority, reverse=True)
        return sources

    # ── 维度 1: Hermes 工具 ──

    def _probe_hermes_tools(self) -> List[KnowledgeSource]:
        """探测 Hermes 已注册的记忆/知识类工具。"""
        results: List[KnowledgeSource] = []

        # 通过 ctx.tools 探测
        if self._ctx and hasattr(self._ctx, "tools"):
            tools = getattr(self._ctx, "tools", {}) or {}
            if isinstance(tools, dict) and "fact_store" in tools:
                results.append(KnowledgeSource(
                    provider_type="hermes_tool",
                    tool_name="fact_store",
                    label="Hermes 记忆库",
                    description="已注册的 Hermes 记忆插件",
                    priority=10,
                ))

        # 也尝试从全局工具注册表探测
        try:
            from hermes_cli.tools import get_registered_tools
            reg_tools = get_registered_tools()
            if isinstance(reg_tools, dict):
                if "fact_store" in reg_tools:
                    results.append(KnowledgeSource(
                        provider_type="hermes_tool",
                        tool_name="fact_store",
                        label="Hermes 记忆库",
                        description="已注册的 Hermes 记忆插件",
                        priority=10,
                    ))
                for name in ["rag", "vector_store", "doc_search"]:
                    if name in reg_tools:
                        results.append(KnowledgeSource(
                            provider_type="hermes_tool",
                            tool_name=name,
                            label=f"Hermes {name}",
                            description=f"已注册的 Hermes {name} 工具",
                            priority=9,
                        ))
        except Exception:
            pass

        return results

    # ── 维度 2: 本地文件系统 ──

    def _probe_filesystem(
        self,
        base_dirs: Optional[List[str]] = None,
    ) -> List[KnowledgeSource]:
        """扫描常见本地知识库目录。

        Args:
            base_dirs: 可选，额外的搜索根目录列表（测试用）。
                       传 None 时使用内建探测模式。
        """
        results: List[KnowledgeSource] = []

        # 内建探测模式（仅在未指定 base_dirs 时运行）
        if base_dirs is None:
            patterns = [
                ("Obsidian Vault", "~/Documents/Obsidian Vault", "*.md"),
                ("Logseq Graph", "~/Documents/Logseq", "*.md"),
                ("本地知识库", "~/Documents/Knowledge Base", "*.md"),
                ("飞书导出", "~/Documents/Feishu Export", "*.md"),
            ]
            for label, path_str, glob in patterns:
                path = Path(path_str).expanduser()
                try:
                    if path.exists() and any(path.glob(glob)):
                        results.append(KnowledgeSource(
                            provider_type="filesystem",
                            path=str(path),
                            glob=glob,
                            label=label,
                            description=f"{label}（{path}）",
                            priority=5,
                        ))
                except Exception:
                    continue

        # 额外扫描指定目录（含子目录）
        if base_dirs:
            for base in base_dirs:
                bp = Path(base)
                if not bp.exists():
                    continue
                try:
                    # 先检查目录本身
                    if any(bp.rglob("*.md")):
                        results.append(KnowledgeSource(
                            provider_type="filesystem",
                            path=str(bp),
                            glob="*.md",
                            label=bp.name,
                            description=f"知识库（{bp}）",
                            priority=4,
                        ))
                    # 再检查子目录
                    for sub in bp.iterdir():
                        if sub.is_dir() and any(sub.rglob("*.md")):
                            results.append(KnowledgeSource(
                                provider_type="filesystem",
                                path=str(sub),
                                glob="*.md",
                                label=sub.name,
                                description=f"知识库（{sub}）",
                                priority=4,
                            ))
                except Exception:
                    continue

        return results

    # ── 维度 3: 本地 SQLite ──

    def _probe_sqlite(
        self,
        base_paths: Optional[List[str]] = None,
    ) -> List[KnowledgeSource]:
        """扫描含 facts 表的 SQLite 知识库。

        Args:
            base_paths: 可选，额外的搜索目录（测试用）。
        """
        results: List[KnowledgeSource] = []

        patterns = [
            ("本地知识库", "~/.cogito/knowledge_base.db"),
            ("Hermes 记忆存储", "~/.hermes/memory/memory_store.db"),
            ("本地知识库", "~/.hermes/memory/knowledge_base.db"),
        ]

        for label, path_str in patterns:
            try:
                path = Path(path_str).expanduser()
                if not path.exists() or path.stat().st_size == 0:
                    continue
                conn = sqlite3.connect(str(path))
                tables = [
                    r[0] for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                ]
                conn.close()
                if "facts" in tables:
                    results.append(KnowledgeSource(
                        provider_type="sqlite",
                        path=str(path),
                        label=label,
                        description=f"{label}（{path}，含 facts 表）",
                        priority=3,
                    ))
            except Exception:
                continue

        # 额外目录扫描
        if base_paths:
            for base in base_paths:
                bp = Path(base)
                if not bp.exists():
                    continue
                for db_file in bp.rglob("*.db"):
                    try:
                        if db_file.stat().st_size == 0:
                            continue
                        conn = sqlite3.connect(str(db_file))
                        tables = [
                            r[0] for r in conn.execute(
                                "SELECT name FROM sqlite_master WHERE type='table'"
                            ).fetchall()
                        ]
                        conn.close()
                        if "facts" in tables:
                            results.append(KnowledgeSource(
                                provider_type="sqlite",
                                path=str(db_file),
                                label=db_file.stem,
                                description=f"SQLite 知识库（{db_file}，含 facts 表）",
                                priority=2,
                            ))
                    except Exception:
                        continue

        return results

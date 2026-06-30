"""
narrative_store.py —— 叙事记忆存储。

跨会话的叙事总结、洞察与未解决问题的持久化。
存储为 JSONL 文件于 ~/.cogito/narrative.jsonl。

平台无关版本 —— 替代 Hermes Holographic+ memory store。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 持久化路径 ──

_COGITO_HOME = Path(
    os.environ.get("COGITO_HOME", os.path.expanduser("~/.cogito"))
)


def set_cogito_home(path: str) -> None:
    """重设 cogito 持久化目录（测试或自定义部署用）。"""
    global _COGITO_HOME
    _COGITO_HOME = Path(path)


def _narrative_file() -> Path:
    """返回叙事文件路径。"""
    _COGITO_HOME.mkdir(parents=True, exist_ok=True)
    return _COGITO_HOME / "narrative.jsonl"


# ── 叙事条目结构 ──

class NarrativeStore:
    """叙事记忆存储。

    每条叙事条目：
        {
            "timestamp": ISO8601,
            "session_id": str,
            "summary": str,          # 叙事总结
            "insights": str,         # 洞察
            "unresolved": str,       # 未解决问题
            "focus_topics": [str],   # 焦点话题
            "emotion_summary": str,  # 情感总结
        }

    Attributes:
        max_entries: 内存中缓存的最近条目数
    """

    def __init__(self, max_entries: int = 50) -> None:
        self.max_entries = max_entries
        self._cache: Optional[List[Dict[str, Any]]] = None

    def _load_all(self) -> List[Dict[str, Any]]:
        """从文件加载所有叙事条目。"""
        nf = _narrative_file()
        if not nf.exists():
            return []
        try:
            with open(nf, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return [
                json.loads(line)
                for line in lines
                if line.strip()
            ]
        except Exception as exc:
            logger.warning("加载叙事文件失败: %s", exc)
            return []

    def _save_all(self, entries: List[Dict[str, Any]]) -> None:
        """保存所有叙事条目到文件（覆写模式）。"""
        nf = _narrative_file()
        try:
            with open(nf, "w", encoding="utf-8") as f:
                for entry in entries:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.error("保存叙事文件失败: %s", exc)

    def append(
        self,
        summary: str,
        insights: str = "",
        unresolved: str = "",
        focus_topics: Optional[List[str]] = None,
        emotion_summary: str = "",
        session_id: str = "",
    ) -> Dict[str, Any]:
        """追加一条叙事条目。

        Args:
            summary: 叙事总结文本
            insights: 洞察
            unresolved: 未解决问题
            focus_topics: 焦点话题列表
            emotion_summary: 情感总结
            session_id: 会话 ID

        Returns:
            新追加的叙事条目 dict。
        """
        entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id or "",
            "summary": summary.strip(),
            "insights": insights.strip(),
            "unresolved": unresolved.strip(),
            "focus_topics": focus_topics or [],
            "emotion_summary": emotion_summary.strip(),
        }

        nf = _narrative_file()
        try:
            with open(nf, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.error("追加叙事条目失败: %s", exc)

        # 修剪到 max_entries
        self._trim()
        return entry

    def load_recent(self, k: int = 3) -> List[Dict[str, Any]]:
        """加载最近 k 条叙事条目。

        Args:
            k: 返回条数

        Returns:
            最近 k 条叙事条目（按时间倒序）。
        """
        entries = self._load_all()
        return entries[-k:] if entries else []

    def finalize(self) -> None:
        """最终化（会话结束时调用）。

        如果内存中有未持久化的条目，写入文件。
        """
        # 当前实现中 append() 已实时写入，
        # 此方法保留用于未来扩展（如批量写入）。
        pass

    def get_context_block(self, k: int = 3) -> str:
        """生成叙事上下文文本块。

        Args:
            k: 返回条数

        Returns:
            格式化的叙事上下文文本。
        """
        recent = self.load_recent(k)
        if not recent:
            return "暂无叙事记忆"

        parts = []
        for i, entry in enumerate(reversed(recent)):
            ts = entry.get("timestamp", "")[:16]
            summary = entry.get("summary", "")
            unresolved = entry.get("unresolved", "")
            parts.append(f"[{i + 1}] {ts}")
            parts.append(f"    总结: {summary}")
            if unresolved and unresolved != "无":
                parts.append(f"    未解: {unresolved}")
            insights = entry.get("insights", "")
            if insights:
                parts.append(f"    洞察: {insights}")

        return "\n".join(parts)

    def _trim(self) -> None:
        """修剪叙事文件到 max_entries 条。"""
        entries = self._load_all()
        if len(entries) > self.max_entries:
            trimmed = entries[-self.max_entries:]
            self._save_all(trimmed)

    @staticmethod
    def clear() -> None:
        """清空所有叙事记忆。"""
        nf = _narrative_file()
        if nf.exists():
            nf.unlink()

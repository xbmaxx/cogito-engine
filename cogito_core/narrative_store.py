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
        pending: bool = False,
    ) -> Dict[str, Any]:
        """追加一条叙事条目。

        Args:
            summary: 叙事总结文本
            insights: 洞察
            unresolved: 未解决问题
            focus_topics: 焦点话题列表
            emotion_summary: 情感总结
            session_id: 会话 ID
            pending: 是否等待 LLM 完整摘要（deferred reflection）

        Returns:
            新追加的叙事条目 dict。
        """
        entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pending": pending,
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

    def has_pending(self) -> bool:
        """检查是否有等待 deferred reflection 的条目。

        Returns:
            True 表示有 pending 条目需要处理。
        """
        entries = self._load_all()
        return any(e.get("pending", False) for e in entries)

    def mark_session_resolved(self, session_id: str) -> int:
        """批量标记指定 session 的所有 pending 条目为已处理。

        解决同 session 多条目（delegate_task 场景）中旧条目被 update_entry
        永久遗弃的问题。一次调用标记该 session 所有 pending=true 的条目。

        Args:
            session_id: 目标会话 ID

        Returns:
            被标记的条目数。
        """
        entries = self._load_all()
        count = 0
        for entry in entries:
            if entry.get("session_id") == session_id and entry.get("pending", False):
                entry["pending"] = False
                count += 1
        if count > 0:
            self._save_all(entries)
        if count > 1:
            logger.info(
                "批量标记 session %s 的 %d 条 pending 条目为已处理",
                session_id[:20], count,
            )
        return count

    def update_entry(
        self,
        session_id: str,
        summary: Optional[str] = None,
        insights: Optional[str] = None,
        unresolved: Optional[str] = None,
        emotion_summary: Optional[str] = None,
        focus_topics: Optional[List[str]] = None,
        pending: Optional[bool] = None,
    ) -> bool:
        """更新指定 session 的最新叙事条目（用于 deferred reflection 回写）。

        Args:
            session_id: 目标会话 ID
            summary: 新的叙事总结（None = 不更新）
            insights: 新的洞察（None = 不更新）
            unresolved: 新的未解决问题（None = 不更新）
            emotion_summary: 新的情感总结（None = 不更新）
            focus_topics: 新的焦点话题列表（None = 不更新）
            pending: 新的 pending 状态（None = 不更新）

        Returns:
            True 表示找到并更新了匹配条目，False 表示未找到
        """
        entries = self._load_all()
        if not entries:
            return False

        # 从后往前找到第一个匹配 session_id 的条目
        for i in range(len(entries) - 1, -1, -1):
            if entries[i].get("session_id") == session_id:
                if summary is not None:
                    entries[i]["summary"] = summary
                if insights is not None:
                    entries[i]["insights"] = insights
                if unresolved is not None:
                    entries[i]["unresolved"] = unresolved
                if emotion_summary is not None:
                    entries[i]["emotion_summary"] = emotion_summary
                if focus_topics is not None:
                    entries[i]["focus_topics"] = focus_topics
                if pending is not None:
                    entries[i]["pending"] = pending
                self._save_all(entries)
                return True

        return False

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

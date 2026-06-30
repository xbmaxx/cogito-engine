"""
session_reflector.py —— 会话反射记忆。

在每个会话结束时，基于关键帧生成会话摘要并持久化。

平台无关版本 —— 无 Hermes 依赖。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .keyframe_extractor import KeyframeExtractor, estimate_conversation_rounds

logger = logging.getLogger(__name__)

_COGITO_HOME = Path(
    os.environ.get("COGITO_HOME", os.path.expanduser("~/.cogito"))
)


def _reflections_file() -> Path:
    _COGITO_HOME.mkdir(parents=True, exist_ok=True)
    return _COGITO_HOME / "session_reflections.jsonl"


class SessionReflector:
    """会话反射器 —— 在会话结束时生成摘要。

    Attributes:
        extractor: 关键帧提取器
        max_history: 内存中保留的最近反射条目数
    """

    def __init__(
        self,
        keyframe_interval: int = 5,
        keyframe_max_frames: int = 20,
        max_history: int = 100,
    ) -> None:
        self.extractor = KeyframeExtractor(
            interval=keyframe_interval,
            max_frames=keyframe_max_frames,
        )
        self.max_history = max_history

    def reflect(
        self,
        messages: List[Dict[str, Any]],
        session_id: str = "",
        tick_count: int = 0,
        focus_topics: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """基于关键帧生成会话反射条目。

        Args:
            messages: 当前会话的消息列表
            session_id: 会话 ID
            tick_count: TICK 计数
            focus_topics: 焦点话题列表

        Returns:
            反射条目 dict，包含：
            {
                "ts": ISO8601,
                "session_id": str,
                "trigger": "termination",
                "tick_count": int,
                "focus_depth": int,
                "topic_keywords": [str],
                "keyframe_count": int,
                "message_count": int,
                "rounds": int,
            }
        """
        keyframes = self.extractor.extract(messages)
        rounds = estimate_conversation_rounds(messages)

        entry: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "trigger": "termination",
            "tick_count": tick_count,
            "focus_depth": len(focus_topics) if focus_topics else 0,
            "topic_keywords": focus_topics or [],
            "keyframe_count": len(keyframes),
            "message_count": len(messages),
            "rounds": rounds,
        }

        # 持久化
        self._persist(entry)

        return entry

    def _persist(self, entry: Dict[str, Any]) -> None:
        """将反射条目写入 JSONL 文件。"""
        rf_file = _reflections_file()
        try:
            with open(rf_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.error("保存会话反射失败: %s", exc)

        # 修剪
        self._trim()

    def load_recent(self, k: int = 3) -> List[Dict[str, Any]]:
        """加载最近 k 条反射条目。"""
        rf_file = _reflections_file()
        if not rf_file.exists():
            return []
        try:
            with open(rf_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return [
                json.loads(line)
                for line in lines[-k:]
                if line.strip()
            ]
        except Exception as exc:
            logger.warning("加载会话反射失败: %s", exc)
            return []

    def _trim(self) -> None:
        """修剪反射文件到 max_history 条。"""
        rf_file = _reflections_file()
        try:
            if rf_file.stat().st_size > self.max_history * 300:
                with open(rf_file, "r") as f:
                    lines = f.readlines()
                if len(lines) > self.max_history:
                    with open(rf_file, "w") as f:
                        f.writelines(lines[-self.max_history:])
        except Exception:
            pass

    @staticmethod
    def clear() -> None:
        """清空所有反射记录。"""
        rf_file = _reflections_file()
        if rf_file.exists():
            rf_file.unlink()

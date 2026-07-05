"""
session_reflector.py —— 会话反射记忆。

在每个会话结束时，基于关键帧生成会话摘要并持久化。
支持两种模式：
- 快速模式（reflect）：保存 metadata + keyframe texts + pending=true
- LLM 模式（reflect_with_llm）：用 LLM 生成 5-section 结构化摘要

平台无关版本 —— 无 Hermes 依赖。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

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
            反射条目 dict，包含 keyframe_texts 和 pending 标记，
            供下个 session 的 deferred reflection 使用。
        """
        keyframes = self.extractor.extract(messages)
        rounds = estimate_conversation_rounds(messages)

        # 提取关键帧文本（截断单条 200 字符）
        keyframe_texts = []
        for kf in keyframes:
            content = str(kf.get("content", ""))
            role = kf.get("role", "unknown")
            text = f"[{role}]: {content}"
            if len(text) > 200:
                text = text[:197] + "..."
            keyframe_texts.append(text)

        entry: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "trigger": "termination",
            "tick_count": tick_count,
            "focus_depth": len(focus_topics) if focus_topics else 0,
            "topic_keywords": focus_topics or [],
            "keyframe_count": len(keyframes),
            "keyframe_texts": keyframe_texts,
            "message_count": len(messages),
            "rounds": rounds,
            "pending": True,
        }

        # 持久化
        self._persist(entry)

        return entry

    def reflect_with_llm(
        self,
        keyframe_texts: List[str],
        focus_topics: List[str],
        llm_fn: Callable[[str], str],
        max_keyframes: int = 15,
    ) -> Dict[str, Any]:
        """用 LLM 生成结构化会话摘要（deferred reflection）。

        由 engine.process() 在下个 session 首次消息时调用。

        Args:
            keyframe_texts: 关键帧文本列表（"[role]: content" 格式）
            focus_topics: 焦点话题关键词
            llm_fn: LLM 调用函数，签名 (prompt: str) -> str
            max_keyframes: 送入 LLM 的关键帧上限

        Returns:
            {
                "summary": str,        # 叙事总结
                "insights": str,       # 洞察
                "unresolved": str,     # 未解决问题
                "emotion_summary": str,# 情感总结
            }
        """
        # 截断关键帧
        frames = keyframe_texts[-max_keyframes:]

        # 构建 prompt
        prompt = self._build_reflection_prompt(frames, focus_topics)

        # 调用 LLM
        try:
            raw = llm_fn(prompt)
            result = self._parse_reflection(raw)
        except Exception as exc:
            logger.warning("LLM 反射失败，降级到关键词摘要: %s", exc)
            result = self._fallback_reflection(focus_topics)

        return result

    def _build_reflection_prompt(
        self,
        keyframe_texts: List[str],
        focus_topics: List[str],
    ) -> str:
        """构建 reflection prompt —— 紧凑格式，最小化 token 消耗。"""
        frames_block = "\n".join(
            f"[{i + 1}] {t}" for i, t in enumerate(keyframe_texts)
        )
        topics_str = ", ".join(focus_topics) if focus_topics else "无"

        return (
            "你是会话反射器。阅读以下对话关键帧，生成结构化 JSON 摘要。\n"
            "\n"
            "对话关键帧：\n"
            f"{frames_block}\n"
            "\n"
            f"焦点话题：{topics_str}\n"
            "\n"
            "只返回一个 JSON 对象（无代码块包裹，无其他文字）：\n"
            '{"summary": "...", "insights": "...", "unresolved": "...", "emotion_summary": "..."}\n'
            "\n"
            "字段说明：\n"
            "- summary: 100-200 字叙事总结，说明讨论了什么、做了什么决策\n"
            "- insights: 一条关键洞察或发现，无则填\"无\"\n"
            "- unresolved: 最需要跨会话延续的未决问题，无则填\"无\"\n"
            "- emotion_summary: 情感基调（正面/负面/混合/中性）"
        )

    def _parse_reflection(self, raw: str) -> Dict[str, Any]:
        """解析 LLM 返回的 JSON 摘要。"""
        # 尝试直接解析
        text = raw.strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # 尝试提取 JSON（容错：可能有 markdown 包裹）
            import re
            match = re.search(r'\{[^{}]*"summary"[^{}]*\}', text, re.DOTALL)
            if match:
                data = json.loads(match.group())
            else:
                raise

        return {
            "summary": str(data.get("summary", "")),
            "insights": str(data.get("insights", "")),
            "unresolved": str(data.get("unresolved", "")),
            "emotion_summary": str(data.get("emotion_summary", "")),
        }

    def _fallback_reflection(
        self, focus_topics: List[str]
    ) -> Dict[str, Any]:
        """LLM 不可用时的降级摘要（保留当前行为）。"""
        kw_str = "".join(focus_topics[:5]) if focus_topics else "未知话题"
        return {
            "summary": f"讨论了{kw_str}等话题",
            "insights": "",
            "unresolved": "",
            "emotion_summary": "",
        }

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

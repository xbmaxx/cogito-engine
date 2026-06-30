"""
engine.py —— Cogito 意识引擎编排器。

将以下模块串联为统一引擎：
- Ticker（心跳调度）
- FocusStack（焦点栈）
- Temporal（时间感知）
- SelfPerception（自我感知）
- TextEmotion（情感分析）
- EnvSensor（环境感知）
- NarrativeStore（叙事记忆）
- SessionReflector（会话反射）

主入口：CogitoEngine.process(messages, state) → (xml, new_state)

XML 输出格式严格遵循 spec：
<consciousness>
  <tick active="true|false" count="N" ttl="N" />
  <temporal iso="ISO8601" weekday="Monday|..." period="morning|afternoon|..." />
  <focus depth="N">
    <frame keywords="k1,k2,k3" source="user|agent" />
  </focus>
  <self mirror="true|false" loop="true|false" style_cluster="initializing|unchanged|narrow|diverse" />
  <env available="true|false"><source time="system" weather="api" ... /></env>
  <emotion available="true|false" sentiment="positive|neutral|negative" polarity="0.0-1.0" confidence="0.0-1.0" label="正面|负面|中性" />
  <narrative available="true|false" unresolved_count="N" last_session="date" recurring_patterns="N" />
  <reflector available="true|false" />
  <focus_history>...</focus_history>
</consciousness>
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .ticker import Ticker
from .focus_stack import FocusStack
from .temporal import get_period
from .self_perception import compute_self_perception
from .text_emotion import TextEmotionDetector, quick_sentiment
from .narrative_store import NarrativeStore
from .session_reflector import SessionReflector
from . import persistence

logger = logging.getLogger(__name__)


# ── 引擎状态类型 ──

class EngineState:
    """Cogito 引擎运行时状态。

    Attributes:
        ticker: TICK 心跳调度器
        focus_stack: 焦点栈
        env_initialized: 环境传感器是否已初始化
        last_message_count: 最后注入的消息计数（防重复注入）
        is_first_message: 是否为会话首条消息
    """

    __slots__ = (
        "ticker",
        "focus_stack",
        "env_initialized",
        "last_message_count",
        "is_first_message",
        "session_id",
    )

    def __init__(self, session_id: str = "") -> None:
        self.ticker = Ticker()
        self.focus_stack = FocusStack()
        self.env_initialized = False
        self.last_message_count = 0
        self.is_first_message = True
        self.session_id = session_id

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典（用于持久化）。"""
        return {
            "tick_counter": self.ticker.tick_counter,
            "focus_depth": self.focus_stack.depth,
            "focus_topics": self.focus_stack.get_topics(),
            "env_initialized": self.env_initialized,
            "last_message_count": self.last_message_count,
            "session_id": self.session_id,
        }

    @classmethod
    def from_dict(
        cls, data: Dict[str, Any], session_id: str = ""
    ) -> "EngineState":
        """从持久化的字典恢复引擎状态。

        Note: Ticker 和 FocusStack 始终重新创建（无历史恢复）。
        """
        state = cls(session_id=session_id)
        if "last_message_count" in data:
            state.last_message_count = data["last_message_count"]
        return state


# ── Cogito 意识引擎 ──

class CogitoEngine:
    """Cogito 意识引擎 —— 意识上下文生成的主编排器。

    Usage:
        engine = CogitoEngine()
        xml, new_state = engine.process(messages, state)
        # xml 是完整的 <consciousness>...</consciousness> 块

    Attributes:
        emotion_detector: 情感检测器实例
        narrative_store: 叙事记忆存储实例
        session_reflector: 会话反射器实例
        include_weather: 是否包含天气信息
        include_battery: 是否包含电池信息
        include_resources: 是否包含系统资源信息
    """

    def __init__(
        self,
        include_weather: bool = False,
        include_battery: bool = True,
        include_resources: bool = True,
    ) -> None:
        self.emotion_detector = TextEmotionDetector(threshold=0.3)
        self.narrative_store = NarrativeStore()
        self.session_reflector = SessionReflector()
        self.include_weather = include_weather
        self.include_battery = include_battery
        self.include_resources = include_resources

    def process(
        self,
        messages: List[Dict[str, Any]],
        state: Optional[EngineState] = None,
    ) -> Tuple[str, EngineState]:
        """处理消息列表，生成意识 XML 上下文块。

        Args:
            messages: 当前会话消息列表（含 user/assistant）
            state: 当前引擎状态（None 则创建新状态）

        Returns:
            (xml_context, new_state)
            - xml_context: 完整的 <consciousness> XML 块
            - new_state: 更新后的引擎状态
        """
        if state is None:
            state = EngineState()

        # ── 查找最新用户消息 ──
        last_user_msg = self._find_last_user_msg(messages)
        if last_user_msg is None:
            # 无用户消息，返回最小上下文
            return self._minimal_context(state), state

        msg_text = last_user_msg.get("content", "")
        if not isinstance(msg_text, str):
            msg_text = ""

        # 防重复注入
        last_user_idx = self._find_last_user_idx(messages)
        if last_user_idx >= 0 and state.last_message_count > last_user_idx:
            return self._minimal_context(state), state
        state.last_message_count = last_user_idx + 1

        is_first = state.is_first_message
        state.is_first_message = False

        # ── 1. TICK 心跳 ──
        state.ticker.tick()

        # ── 2. 关键词提取 & 焦点栈更新 ──
        if msg_text:
            try:
                from .keywords import extract_keywords
                kws = extract_keywords(msg_text)
                if kws:
                    state.focus_stack.update(
                        kws,
                        tick_counter=state.ticker.tick_counter,
                        source="user",
                    )
            except ImportError:
                logger.debug("keywords 模块不可用，跳过关键词提取")
            except Exception as exc:
                logger.debug("关键词提取失败: %s", exc)

        # ── 3. 环境传感器（延迟初始化） ──
        env_snap = ""
        if not state.env_initialized:
            try:
                from .env_sensor import get_snapshot
                env_snap = get_snapshot(
                    include_weather=self.include_weather,
                    include_battery=self.include_battery,
                    include_resources=self.include_resources,
                ) or ""
                state.env_initialized = True
            except Exception as exc:
                logger.debug("环境传感器初始化失败: %s", exc)

        # ── 4. 自我感知 ──
        sp_result = None
        if msg_text and messages:
            try:
                current_msg = {"role": "user", "content": msg_text}
                sp_result = compute_self_perception(
                    conversation_window=messages,
                    current_msg=current_msg,
                )
            except Exception as exc:
                logger.debug("自我感知计算失败: %s", exc)

        # ── 5. 情感分析 ──
        emo_result = None
        if msg_text:
            try:
                emo_result = self.emotion_detector.detect(msg_text)
                if emo_result.get("confidence", 0) <= 0.3:
                    # 尝试回退到关键词检测
                    emo_result = quick_sentiment(msg_text)
            except Exception:
                emo_result = quick_sentiment(msg_text)

        # ── 6. 叙事记忆（首次消息时加载） ──
        narrative_data = None
        if is_first:
            try:
                narrative_data = self.narrative_store.load_recent(3)
            except Exception as exc:
                logger.debug("叙事记忆加载失败: %s", exc)

        # ── 7. 会话反射（首次消息时加载最新反射） ──
        reflection_data = None
        if is_first:
            try:
                reflection_data = self.session_reflector.load_recent(1)
            except Exception as exc:
                logger.debug("会话反射加载失败: %s", exc)

        # ── 8. 焦点历史（首次消息时加载） ──
        focus_history = []
        if is_first:
            try:
                focus_history = persistence.load_focus_history(3)
            except Exception as exc:
                logger.debug("焦点历史加载失败: %s", exc)

        # ── 9. 组装 XML ──
        xml = self._assemble_xml(
            state=state,
            env_snap=env_snap,
            sp_result=sp_result,
            emo_result=emo_result,
            narrative_data=narrative_data,
            reflection_data=reflection_data,
            focus_history=focus_history,
            is_first=is_first,
        )

        return xml, state

    # ── 内部方法 ──

    def _find_last_user_msg(
        self, messages: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """查找消息列表中最后一条用户消息。"""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                return msg
        return None

    def _find_last_user_idx(
        self, messages: List[Dict[str, Any]]
    ) -> int:
        """查找最后一条用户消息的索引。"""
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                return i
        return -1

    def _minimal_context(self, state: EngineState) -> str:
        """生成最小上下文（无用户消息时）。"""
        tick_status = state.ticker.get_status()
        parts = ["<consciousness>"]
        parts.append(
            f'  <tick active="{str(tick_status["active"]).lower()}" '
            f'count="{state.ticker.tick_counter}" '
            f'ttl="{tick_status["ttl"]}" />'
        )
        parts.append(self._temporal_xml())
        parts.append(
            f'  <focus depth="{state.focus_stack.depth}" />'
        )
        parts.append(
            '  <self mirror="false" loop="false" '
            'style_cluster="initializing" />'
        )
        parts.append('  <env available="false" />')
        parts.append('  <emotion available="false" />')
        parts.append('  <narrative available="false" />')
        parts.append('  <reflector available="false" />')
        parts.append("</consciousness>")
        return "\n".join(parts)

    def _temporal_xml(self) -> str:
        """生成 temporal XML 元素。"""
        now = datetime.now().astimezone()
        weekday = now.strftime("%A")
        period = get_period(now)
        tz_offset = now.strftime("%z")
        if tz_offset:
            tz_iso = tz_offset[:3] + ":" + tz_offset[3:]
        else:
            tz_iso = "+08:00"
        return (
            f'  <temporal iso="{now.strftime("%Y-%m-%dT%H:%M:%S")}{tz_iso}" '
            f'weekday="{weekday}" period="{period}" />'
        )

    def _assemble_xml(
        self,
        state: EngineState,
        env_snap: str,
        sp_result: Optional[Dict[str, Any]],
        emo_result: Optional[Dict[str, Any]],
        narrative_data: Optional[List[Dict[str, Any]]],
        reflection_data: Optional[List[Dict[str, Any]]],
        focus_history: List[Dict[str, Any]],
        is_first: bool,
    ) -> str:
        """组装完整的 <consciousness> XML 块。"""
        parts = ["<consciousness>"]

        # ── TICK ──
        tick_status = state.ticker.get_status()
        parts.append(
            f'  <tick active="{str(tick_status["active"]).lower()}" '
            f'count="{state.ticker.tick_counter}" '
            f'ttl="{tick_status["ttl"]}" />'
        )

        # ── Temporal ──
        parts.append(self._temporal_xml())

        # ── Focus Stack ──
        if state.focus_stack.stack:
            depth = state.focus_stack.depth
            parts.append(f'  <focus depth="{depth}">')
            for frame in state.focus_stack.stack:
                keywords = ", ".join(frame["topic"])
                safe_kw = keywords.replace('"', "'")
                source = frame.get("source", "user")
                parts.append(
                    f'    <frame keywords="{safe_kw}" source="{source}" />'
                )
            parts.append("  </focus>")
        else:
            parts.append('  <focus depth="0" />')

        # ── Self-Perception ──
        mirror_flag = "false"
        loop_flag = "false"
        style_cluster = "initializing"

        if sp_result:
            mirror_data = sp_result.get("mirror", {})
            if mirror_data:
                m_score = mirror_data.get("score", 0)
                if m_score >= 0.4:
                    mirror_flag = "true"
            loop_depth = sp_result.get("loop", 0)
            if isinstance(loop_depth, (int, float)) and loop_depth >= 2:
                loop_flag = "true"
            style_cluster = sp_result.get("style_cluster", "unchanged")

        parts.append(
            f'  <self mirror="{mirror_flag}" '
            f'loop="{loop_flag}" '
            f'style_cluster="{style_cluster}" />'
        )

        # ── Env ──
        if env_snap:
            parts.append('  <env available="true">')
            parts.append(
                '    <source time="system" weather="api" '
                'system_info="shell" foreground_app="ax" battery="iokit" />'
            )
            parts.append("  </env>")
        else:
            parts.append('  <env available="false" />')

        # ── Emotion ──
        if emo_result and emo_result.get("confidence", 0) > 0.3:
            sentiment = emo_result.get("label", "neutral")
            polarity = emo_result.get("sentiment", 0.5)
            confidence = emo_result.get("confidence", 0)
            label_cn = emo_result.get("label_cn", "中性")
            parts.append(
                f'  <emotion available="true" '
                f'sentiment="{sentiment}" '
                f'polarity="{polarity}" '
                f'confidence="{round(confidence, 4)}" '
                f'label="{label_cn}" />'
            )
        else:
            parts.append('  <emotion available="false" />')

        # ── Narrative ──
        if narrative_data and is_first:
            unresolved_count = sum(
                1 for n in narrative_data
                if n.get("unresolved") and n.get("unresolved") != "无"
            )
            recurring = min(len(narrative_data), 5)
            last_session = ""
            if narrative_data:
                ts = narrative_data[0].get("timestamp", "")
                if ts:
                    try:
                        dt = datetime.fromisoformat(ts)
                        last_session = dt.strftime("%Y-%m-%d")
                    except (ValueError, TypeError):
                        pass
            parts.append(
                f'  <narrative available="true" '
                f'unresolved_count="{unresolved_count}" '
                f'last_session="{last_session}" '
                f'recurring_patterns="{recurring}" />'
            )
        else:
            parts.append('  <narrative available="false" />')

        # ── Reflector ──
        if reflection_data and is_first:
            last_rf = reflection_data[-1] if reflection_data else {}
            trigger = last_rf.get("trigger", "inactivity")
            ts = last_rf.get("ts", "")
            parts.append(
                f'  <reflector available="true" '
                f'trigger="{trigger}" last_reflection="{ts}" />'
            )
        else:
            parts.append('  <reflector available="false" />')

        # ── Focus History ──
        if focus_history and is_first:
            parts.append("  <focus_history>")
            for entry in reversed(focus_history):
                topics = "; ".join(entry.get("topics", []))
                if topics:
                    safe = topics.replace('"', "'")
                    parts.append(
                        f'    <past topics="{safe}" />'
                    )
            parts.append("  </focus_history>")

        parts.append("</consciousness>")
        return "\n".join(parts)

    # ── 会话生命周期 ──

    def end_session(
        self,
        state: EngineState,
        messages: Optional[List[Dict[str, Any]]] = None,
        focus_summary: str = "",
    ) -> None:
        """会话结束时的收尾操作。

        Args:
            state: 当前引擎状态
            messages: 会话消息列表（用于生成反射）
            focus_summary: 焦点摘要文本
        """
        # 保存焦点历史
        try:
            if state.focus_stack.stack:
                persistence.save_focus_history(state.focus_stack.stack)
        except Exception as exc:
            logger.error("保存焦点历史失败: %s", exc)

        # 保存焦点摘要
        if focus_summary:
            try:
                persistence.save_focus_summary(focus_summary)
            except Exception as exc:
                logger.error("保存焦点摘要失败: %s", exc)

        # 保存引擎状态
        try:
            persistence.save_state(state.to_dict())
        except Exception as exc:
            logger.error("保存引擎状态失败: %s", exc)

        # 生成会话反射
        if messages:
            try:
                self.session_reflector.reflect(
                    messages=messages,
                    session_id=state.session_id,
                    tick_count=state.ticker.tick_counter,
                    focus_topics=[
                        ", ".join(f["topic"])
                        for f in state.focus_stack.stack
                    ],
                )
            except Exception as exc:
                logger.error("会话反射生成失败: %s", exc)

    # ── 关键词提取模块（可选依赖） ──

    def extract_keywords(self, text: str) -> List[str]:
        """提取关键词（如果 keywords 模块可用）。

        Args:
            text: 待提取的文本

        Returns:
            关键词列表
        """
        try:
            from .keywords import extract_keywords
            return extract_keywords(text)
        except ImportError:
            return list(set(text.split()[:10]))
        except Exception:
            return []

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
  <tick beating="true|false" mode="custom|default" count="N" />
  <temporal iso="ISO8601" weekday="Monday|..." period="morning|afternoon|..." />
  <focus depth="N">
    <frame keywords="k1,k2,k3" source="user|agent" />
  </focus>
  <self mirror="true|false" loop="true|false" style_cluster="initializing|unchanged|narrow|diverse" />
  <env available="true|false"><source time="system" weather="api" ... /></env>
  <emotion available="true|false" sentiment="positive|neutral|negative" label="正面|负面|中性" />
  <narrative available="true|false" unresolved_count="N" last_session="date" recurring_patterns="N" />
  <reflector available="true|false" />
  <focus_history>...</focus_history>
</consciousness>
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
import re

from .ticker import Ticker
from .focus_stack import FocusStack
from .temporal import get_period
from .self_perception import compute_self_perception
from .text_emotion import quick_sentiment
from .emotion_classifier import EmotionClassifier
from .narrative_store import NarrativeStore
from .session_reflector import SessionReflector
from . import persistence
from .context_window import HierarchicalContextBuilder, ContextInput
from .env_sensor import get_location, get_weather

logger = logging.getLogger(__name__)


def _has_ascii_word(text: str) -> bool:
    """检测文本是否包含英文技术词汇（≥2字母），用于触发情绪交叉验证。"""
    return bool(re.search(r'\b[a-zA-Z]{2,}\b', text))


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

_MODE_ICONS = {
    "glowing": "💓",
    "aching": "💔",
    "resting": "🤍",
    "frustrated": "⚡",
    "confused": "🌫️",
    "overwhelmed": "🌊",
    "disconnected": "📡",
}


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
        include_emotion: 是否启用情感分析（默认 True）
        include_narrative: 是否启用叙事记忆（默认 True）
    """

    def __init__(
        self,
        include_weather: bool = False,
        include_battery: bool = True,
        include_resources: bool = True,
        include_emotion: bool = True,
        include_narrative: bool = True,
        reflection_llm: Optional[Callable[[str], str]] = None,
    ) -> None:
        self.emotion_detector = EmotionClassifier()
        self.narrative_store = NarrativeStore()
        self.session_reflector = SessionReflector()
        self.include_weather = include_weather
        self.include_battery = include_battery
        self.include_resources = include_resources
        self.include_emotion = include_emotion
        self.include_narrative = include_narrative
        self._heartbeat_mapper = None   # 延迟加载，避免 import 失败阻断主链路
        self._reflection_llm = reflection_llm  # deferred reflection LLM 函数

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
        if msg_text and self.include_emotion:
            try:
                emo_result = self.emotion_detector.detect(msg_text)
                dominant = emo_result.get("dominant", "none")
                if dominant == "none":
                    # DUTIR 无情绪信号 → 用 quick_sentiment 兜底判极性
                    qs = quick_sentiment(msg_text)
                    emo_result = {
                        "available": True,
                        "emotions": {"好": 0, "乐": 0, "哀": 0, "怒": 0, "惧": 0, "恶": 0, "惊": 0},
                        "dominant": "none",
                        "confidence": 0.0,
                        "method": "dutir_fallback_quick_sentiment",
                        "label": qs.get("label", "neutral"),
                        "label_cn": qs.get("label_cn", "中性"),
                        "sentiment": qs.get("sentiment", 0.5),
                        "polarity": qs.get("polarity", 0.5),
                    }
                elif dominant != "none" and _has_ascii_word(msg_text):
                    # 含英文词 → 交叉验证：SnowNLP 可能对工具/代码文本误判
                    qs = quick_sentiment(msg_text)
                    if qs.get("confidence", 0) == 0.0:
                        # 关键词检测无情绪信号 → 归为中性
                        emo_result = qs
            except Exception:
                emo_result = quick_sentiment(msg_text)

        # ── 5a. 情感持久化（v1.5.9）──
        if emo_result:
            try:
                persistence.save_emotion_history(
                    label=emo_result.get("label", "neutral"),
                    sentiment=float(emo_result.get("sentiment", 0.5)),
                    confidence=float(emo_result.get("confidence", 0.0)),
                    label_cn=emo_result.get("label_cn", "中性"),
                    text_excerpt=msg_text,
                )
            except Exception:
                pass

        # ── 5.5 心跳叙事（可选模块，v1.4 新增）──
        heartbeat_line = None
        heartbeat_mode = ""
        heartbeat_expression = ""
        if msg_text and sp_result is not None and emo_result is not None:
            try:
                from .heartbeat_mapper import HeartbeatMapper
                if self._heartbeat_mapper is None:
                    self._heartbeat_mapper = HeartbeatMapper()

                mapper_result = self._heartbeat_mapper.map(
                    text_emotion=emo_result,
                    self_perception=sp_result,
                    tick_count=state.ticker.tick_counter,
                )

                heartbeat_mode = mapper_result.get("mode", "")
                heartbeat_expression = mapper_result.get("expression", "")

                if mapper_result and mapper_result.get("mode") != "resting":
                    mode = mapper_result["mode"]
                    icon = _MODE_ICONS.get(mode, "💓")
                    heartbeat_line = (
                        f"{icon} 第{state.ticker.tick_counter}次 · "
                        f"{mapper_result['expression']}"
                    )
                    # 模式切换时写快照
                    if mapper_result.get("changed"):
                        from .heartbeat_snapshot import save_snapshot
                        save_snapshot(mapper_result)

            except ImportError:
                pass  # heartbeat_mapper.py 不存在 → 静默降级
            except Exception as exc:
                logger.warning("心跳叙事异常，降级到基础模式: %s", exc)

        # ── 6. Deferred Reflection（首次消息时，处理上一 session 的 pending 条目）──
        narrative_data = None
        narrative_data_loaded = False
        if is_first and self.include_narrative and self._reflection_llm:
            try:
                self._run_deferred_reflection()
            except Exception as exc:
                logger.debug("延迟反射执行失败: %s", exc)
            # 重新加载叙事数据（可能已被 deferred reflection 更新）
            try:
                narrative_data = self.narrative_store.load_recent(3)
                narrative_data_loaded = True
            except Exception:
                pass

        # ── 6a. 叙事记忆（首次消息时加载）──
        if not narrative_data_loaded and is_first and self.include_narrative:
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
            heartbeat_line=heartbeat_line,
            heartbeat_mode=heartbeat_mode,
            heartbeat_expression=heartbeat_expression,
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
        """生成最小上下文（无用户消息时）——三层格式。"""
        return "<consciousness>\n</consciousness>"

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

    # ── 情绪趋势（v1.5.9，P1.5）──

    def _compute_emotion_trend(self) -> str:
        """从 emotion_history.jsonl 最近 3 条判情绪趋势方向。

        Returns:
            "上升" / "下降" / "平稳" / ""（数据不足 3 条）
        """
        entries = persistence.load_emotion_history(3)
        if len(entries) < 3:
            return ""

        sentiments = [float(e.get("sentiment", 0.5)) for e in entries]
        # 连续比较：全递增 → 上升，全递减 → 下降，否则平稳
        inc = all(sentiments[i] < sentiments[i + 1] for i in range(len(sentiments) - 1))
        dec = all(sentiments[i] > sentiments[i + 1] for i in range(len(sentiments) - 1))

        if inc:
            return "上升"
        if dec:
            return "下降"
        return "平稳"

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
        heartbeat_line: Optional[str] = None,
        heartbeat_mode: str = "",
        heartbeat_expression: str = "",
    ) -> str:
        """组装完整的 <consciousness> XML 块（三层结构）。

        委托给 HierarchicalContextBuilder，将平铺的 consciousness 数据
        按 LLM 注意力规律重组为 immediate / working / background 三层。
        """
        builder = HierarchicalContextBuilder()

        # ── 提取叙事数据 ──
        last_summary = ""
        unresolved: List[str] = []
        if narrative_data and is_first:
            first_entry = narrative_data[0] if narrative_data else {}
            last_summary = first_entry.get("summary", "")
            for n in narrative_data:
                u = n.get("unresolved", "")
                if u and u != "无":
                    unresolved.append(u)

        # ── 提取情感数据 ──
        emo_label = ""
        emo_polarity = 0.0
        emo_confidence = 0.0
        if emo_result:
            emo_label = emo_result.get("label_cn", emo_result.get("label", ""))
            emo_polarity = float(emo_result.get("polarity", emo_result.get("sentiment", 0.0)))
            emo_confidence = float(emo_result.get("confidence", 0.0))

        # ── 提取时间与位置数据 ──
        now = datetime.now().astimezone()
        now_local = now.strftime("%Y-%m-%d %H:%M")
        now_weekday = now.strftime("%A")
        now_period = get_period(now)

        loc_data = {}
        try:
            loc_data = get_location()
        except Exception:
            pass
        location = loc_data.get("city", "")

        weather_str = ""
        try:
            weather_data = get_weather()
            if weather_data.get("available"):
                weather_str = (
                    f"{weather_data['weather']} {weather_data['temperature']}°C "
                    f"湿度{weather_data['humidity']}%"
                )
        except Exception:
            pass

        # ── 构建 ContextInput ──
        inp = ContextInput(
            heartbeat_mode=heartbeat_mode,
            heartbeat_expression=heartbeat_expression,
            emotion_label=emo_label,
            emotion_polarity=emo_polarity,
            emotion_confidence=emo_confidence,
            emotion_trend=self._compute_emotion_trend(),
            focus_frames=state.focus_stack.stack,
            last_session_summary=last_summary,
            unresolved_topics=unresolved,
            cross_session_patterns=[],   # P2: 跨会话模式补齐
            relationship_days=0,         # P1.5: 关系纪元
            weather=weather_str,
            location=location,
            now_local=now_local,
            now_weekday=now_weekday,
            now_period=now_period,
            now_hour=now.hour,
            tick_count=state.ticker.tick_counter,
        )

        return builder.assemble_xml(inp)

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

        # 保存叙事记忆（narrative_store.append 写 narrative.jsonl）
        try:
            if state.focus_stack.stack:
                all_keywords = []
                for f in state.focus_stack.stack:
                    all_keywords.extend(f["topic"])
                seen = set()
                unique = []
                for kw in all_keywords:
                    if kw not in seen:
                        seen.add(kw)
                        unique.append(kw)
                        if len(unique) >= 5:
                            break
                if focus_summary:
                    narrative_summary = focus_summary
                else:
                    narrative_summary = "讨论了" + "、".join(unique)
                    if len(all_keywords) > 5:
                        narrative_summary += "等话题"
                self.narrative_store.append(
                    summary=narrative_summary,
                    insights="",
                    unresolved="",
                    focus_topics=unique,
                    emotion_summary="",
                    session_id=state.session_id,
                    pending=True,  # 等待 deferred reflection 用 LLM 生成完整摘要
                )
        except Exception as exc:
            logger.error("保存叙事记忆失败: %s", exc)

    def _run_deferred_reflection(self) -> None:
        """执行延迟反射：查找 pending 条目 → 用 LLM 生成摘要 → 回写。

        当上一 session 的 narrative entry 仍为 pending=true 时调用。
        需要 self._reflection_llm 已配置。
        """
        # 1. 检查是否有 pending 条目
        if not self.narrative_store.has_pending():
            return

        # 2. 加载最新的 pending 条目
        recent = self.narrative_store.load_recent(3)
        pending_entry = None
        for entry in reversed(recent):
            if entry.get("pending"):
                pending_entry = entry
                break
        if pending_entry is None:
            return

        session_id = pending_entry.get("session_id", "")
        if not session_id:
            return

        # 3. 加载对应的反射条目（含 keyframe texts）
        reflections = self.session_reflector.load_recent(3)
        keyframe_texts: List[str] = []
        focus_topics: List[str] = pending_entry.get("focus_topics", [])
        for ref in reversed(reflections):
            if ref.get("session_id") == session_id:
                keyframe_texts = ref.get("keyframe_texts", [])
                break

        # 4. 无关键帧时降级：用 focus_topics + summary 拼简化 prompt 调 LLM
        if not keyframe_texts:
            summary_hint = pending_entry.get("summary", "")
            if not focus_topics and not summary_hint:
                logger.debug("延迟反射: session %s 无关键帧且无话题，跳过", session_id)
                self.narrative_store.update_entry(
                    session_id=session_id,
                    summary=summary_hint,
                    pending=False,
                )
                return

            # 用已有摘要 + 话题拼一个简化 prompt
            prompt_parts = ["你是会话反射器。基于以下会话摘要生成结构化 JSON。"]
            if summary_hint:
                prompt_parts.append(f"会话关键词摘要：{summary_hint}")
            if focus_topics:
                prompt_parts.append(f"焦点话题：{', '.join(focus_topics)}")
            prompt_parts.append(
                "只返回一个 JSON 对象（无代码块包裹）："
                '{"summary": "...", "insights": "...", "unresolved": "...", "emotion_summary": "..."}'
            )
            prompt = "\n".join(prompt_parts)

            try:
                raw = self._reflection_llm(prompt)
                result = self.session_reflector._parse_reflection(raw)
            except Exception as exc:
                logger.debug("延迟反射 LLM 调用失败（降级 prompt）: %s", exc)
                self.narrative_store.update_entry(
                    session_id=session_id,
                    summary=summary_hint,
                    pending=False,
                )
                return

            self.narrative_store.update_entry(
                session_id=session_id,
                summary=result.get("summary", summary_hint),
                insights=result.get("insights", ""),
                unresolved=result.get("unresolved", ""),
                emotion_summary=result.get("emotion_summary", ""),
                pending=False,
            )
            logger.info("延迟反射完成（降级 prompt）: session %s", session_id)
            return

        # 5. 调用 LLM 生成摘要
        try:
            result = self.session_reflector.reflect_with_llm(
                keyframe_texts=keyframe_texts,
                focus_topics=focus_topics,
                llm_fn=self._reflection_llm,
            )
        except Exception as exc:
            logger.warning("延迟反射 LLM 调用失败: %s", exc)
            # 降级：移除 pending 标记，保留关键词摘要
            self.narrative_store.update_entry(
                session_id=session_id,
                summary=pending_entry.get("summary", ""),
                pending=False,
            )
            return

        # 6. 回写 narrative.jsonl
        self.narrative_store.update_entry(
            session_id=session_id,
            summary=result.get("summary", ""),
            insights=result.get("insights", ""),
            unresolved=result.get("unresolved", ""),
            emotion_summary=result.get("emotion_summary", ""),
            pending=False,
        )
        logger.info("延迟反射完成: session %s → narrative 更新", session_id)

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

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

from .ticker import Ticker
from .focus_stack import FocusStack
import re

from .temporal import get_period
from .self_perception import compute_self_perception
from .emotion_registry import EmotionModelRegistry
from .narrative_store import NarrativeStore
from .session_reflector import SessionReflector
from . import persistence
from .context_window import HierarchicalContextBuilder, ContextInput
from .env_sensor import get_location, get_weather

logger = logging.getLogger(__name__)


# ── 叙事记忆质量门：垃圾关键词 ──

_NARRATIVE_GARBAGE_KW = frozenset({
    "user", "one", "two", "via", "session",
    "checkpoint", "Generate", "context", "summary",
    "skills", "tool", "stop", "save", "memory",
    "saving", "worth", "file", "Downloads",
})

_GARBAGE_PATTERNS = [
    {"user", "one", "skills", "via", "session"},     # delegate_task 子代理
    {"checkpoint", "Generate", "context", "summary"}, # context 压缩
]

# 模板句式垃圾摘要检测（正则匹配）
_GARBAGE_TEMPLATES: List[str] = [
    r"讨论了?.+等话题",
    r"涉及了?.+等方?面?",
    r"关于.+等内容",
    r"主要讨论了?",
    r"本期.+涉及",
    r"[^，。]*?等多[^，。]*",  # "agent、task、skill 等多种/多个…"
]

# 中文动词特征词——有这些说明摘要包含实际语义，不是纯关键词拼接
_CHINESE_VERB_MARKERS: set = {
    "了", "过", "进行", "完成", "需要", "发现", "确认",
    "建议", "修复", "优化", "添加", "删除", "修改",
    "分析", "确认", "验证", "对比", "测试", "排查",
    "解决", "提出", "决定", "计划", "准备", "正在",
}


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

        v1.5.10: 恢复焦点栈（跨会话焦点累积）。
        Ticker 始终重新从 0 开始计数。
        """
        state = cls(session_id=session_id)
        if "last_message_count" in data:
            state.last_message_count = data["last_message_count"]
        # ── 恢复焦点栈 ──
        focus_topics = data.get("focus_topics", [])
        if focus_topics:
            for topics in focus_topics:
                if topics:
                    state.focus_stack.update(
                        list(topics),
                        tick_counter=0,
                        source="user",
                    )
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
        emotion_model: str = "affect_mapper",
    ) -> None:
        self.emotion_registry = EmotionModelRegistry()
        # discover 已由 Registry.__init__ 自动触发
        if emotion_model:
            if not self.emotion_registry.set_active(emotion_model):
                logger.warning(
                    "指定的情绪模型 %s 未找到，使用内置 affect_mapper",
                    emotion_model,
                )
        # 保留 emotion_detector 作为旧 API 入口（向后兼容）
        self.emotion_detector = self.emotion_registry.get_active()
        self.narrative_store = NarrativeStore()
        self.session_reflector = SessionReflector()
        self.include_weather = include_weather
        self.include_battery = include_battery
        self.include_resources = include_resources
        self.include_emotion = include_emotion
        self.include_narrative = include_narrative
        self._heartbeat_mapper = None   # 延迟加载，避免 import 失败阻断主链路
        self._reflection_llm = reflection_llm  # deferred reflection LLM 函数
        self._session_messages: List[Dict[str, Any]] = []  # 消息缓存，end_session 使用

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

        # ── 5. 情感分析（统一走 classify_with_fallback，引擎不做模型后处理）──
        emo_result = None
        if msg_text and self.include_emotion and self.emotion_registry is not None:
            try:
                emo_result = self.emotion_registry.classify_with_fallback(msg_text)
            except Exception:
                try:
                    from .text_emotion import quick_sentiment
                    emo_result = quick_sentiment(msg_text)
                except Exception:
                    emo_result = {
                        "available": True, "emotions": {},
                        "dominant": "none", "confidence": 0.0, "method": "none",
                        "label": "neutral", "label_cn": "中性",
                        "sentiment": 0.5, "polarity": 0.5,
                    }

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
                # P0: 只注入已 LLM 增强的叙事（pending=false），避免垃圾摘要污染意识 XML
                narrative_data = [e for e in narrative_data if not e.get("pending", False)]
                narrative_data_loaded = True
            except Exception:
                pass

        # ── 6a. 叙事记忆（首次消息时加载）──
        if not narrative_data_loaded and is_first and self.include_narrative:
            try:
                narrative_data = self.narrative_store.load_recent(3)
                # P0: 只注入已 LLM 增强的叙事
                narrative_data = [e for e in narrative_data if not e.get("pending", False)]
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

        # 缓存消息供 end_session 使用（平台无关）
        self._session_messages = messages

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

        # ── 提取反射话题（断链修复）──
        reflection_topics: List[str] = []
        if reflection_data and is_first:
            latest_reflection = reflection_data[0] if reflection_data else {}
            rt = latest_reflection.get("topic_keywords", [])
            if rt:
                for kw in rt:
                    if isinstance(kw, str):
                        reflection_topics.append(kw)
                        if len(reflection_topics) >= 3:
                            break

        # ── 提取焦点历史摘要（断链修复）──
        focus_history_summary = ""
        if focus_history and is_first:
            for fh in reversed(focus_history):
                if fh.get("type") == "session_summary":
                    focus_history_summary = fh.get("summary", "").strip()
                    break

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
            last_reflection_topics=reflection_topics,  # 断链修复
            focus_history_summary=focus_history_summary,  # 断链修复
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

    def _should_write_narrative(
        self,
        state: "EngineState",
        messages: Optional[List[Dict[str, Any]]],
        focus_summary: str,
    ) -> bool:
        """质量门：判断当前 session 是否值得写入叙事记忆。

        三道门，全通过才返回 True：
        1. 焦点栈深度 ≥ 3
        2. 对话轮次 ≥ 3（messages=None 时降级跳过）
        3. focus_summary 不命中垃圾模式（≥3 个关键词命中任一模式则拒绝）

        Returns:
            True 表示应该写入叙事记忆
        """
        # 门 1: 焦点栈深度 ≥ 2（原为 ≥ 3）
        depth = len(state.focus_stack.stack) if state.focus_stack.stack else 0
        if depth < 2:
            logger.debug(
                "叙事记忆质量门拒绝: depth=%d < 2, session=%s",
                depth, state.session_id,
            )
            return False

        # 门 2: 对话轮次 ≥ 3（messages=None 时降级跳过）
        if messages is not None:
            from .keyframe_extractor import estimate_conversation_rounds
            rounds = estimate_conversation_rounds(messages)
            if rounds < 3:
                logger.debug(
                    "叙事记忆质量门拒绝: rounds=%d < 3, session=%s",
                    rounds, state.session_id,
                )
                return False

        # 门 3: 非模板化垃圾
        if focus_summary:
            summary_lower = focus_summary.lower()
            for pattern in _GARBAGE_PATTERNS:
                hits = sum(1 for kw in pattern if kw.lower() in summary_lower)
                if hits >= 3:
                    logger.debug(
                        "叙事记忆质量门拒绝: 命中 %d 个垃圾词, session=%s",
                        hits, state.session_id,
                    )
                    return False

        return True

    def _is_garbage_summary(self, text: str) -> bool:
        """轻量垃圾检查。

        与 _should_write_narrative 的完整三道门不同，此方法仅检查
        text 是否为「关键词拼接型」垃圾摘要。三档检测：

        档 1: 模板句式（"讨论了…等话题"等正则匹配）
        档 2: 关键词拼接 heuristic（高逗号密度 + 短文本 + 无中文动词）
        档 3: 过短文本（< 15 字符）

        Args:
            text: 待检查的文本

        Returns:
            True 表示 text 是垃圾，应跳过。
        """
        if not text:
            return False
        text_lower = text.lower().strip()

        # ── 档 1: 模板句式检测（正则） ──
        for pattern in _GARBAGE_TEMPLATES:
            if re.search(pattern, text_lower):
                logger.debug("垃圾摘要: 命中模板句式 pattern=%r", pattern)
                return True

        # ── 档 2: 关键词拼接 heuristic ──
        # 特征：短文本 + 高逗号密度 + 无中文动词
        cn_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        comma_count = text.count("，") + text.count(",") + text.count("、")
        has_verb = any(marker in text_lower for marker in _CHINESE_VERB_MARKERS)

        if len(text) < 80 and comma_count >= 2 and not has_verb:
            logger.debug("垃圾摘要: 关键词拼接 len=%d commas=%d cn=%d",
                         len(text), comma_count, cn_chars)
            return True

        # ── 档 3: 过短文本 ──
        if len(text) < 15:
            return True

        # ── 档 4: 原有关键词模式匹配（已有 _GARBAGE_PATTERNS） ──
        for pattern in _GARBAGE_PATTERNS:
            hits = sum(1 for kw in pattern if kw.lower() in text_lower)
            if hits >= 3:
                logger.debug("垃圾摘要: 关键词模式 hits=%d", hits)
                return True

        return False

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

        # 生成会话反射（优先用传入的消息，否则用引擎缓存的消息）
        effective_messages = messages or self._session_messages
        reflection_entry = None
        if effective_messages:
            try:
                reflection_entry = self.session_reflector.reflect(
                    messages=effective_messages,
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
        # ── 质量门：不通过则跳过叙事记忆写入 ──
        if not self._should_write_narrative(state, effective_messages, focus_summary):
            logger.debug("叙事记忆质量门跳过写入: session=%s", state.session_id)
            return

        # 收集焦点关键词（用于 summary 和 focus_topics）—— 过滤 meta 关键词
        _META_KEYWORDS = {
            "unresolved", "insights", "topics", "focus", "pending",
            "summary", "emotion", "emotion_summary", "topic_keywords",
            "keyframe", "reflect", "session", "conversation",
        }
        all_keywords = []
        for f in state.focus_stack.stack:
            all_keywords.extend(f["topic"])
        seen = set()
        unique = []
        for kw in all_keywords:
            kw_lower = kw.lower().strip()
            if kw_lower in _META_KEYWORDS:
                continue
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

        # ── 内联 LLM 反射：桥接 session_reflection → narrative_store ──
        # 不再依赖 deferred reflection（MAX_BATCH=5 瓶颈 + 跨 session 时序不可靠），
        # 直接在 end_session 内调用 reflect_with_llm 生成 insights/unresolved。
        narrative_pending = True
        narrative_insights = ""
        narrative_unresolved = ""
        narrative_emotion = ""

        if self._reflection_llm and reflection_entry:
            keyframe_texts = reflection_entry.get("keyframe_texts", [])
            if keyframe_texts:
                try:
                    llm_result = self.session_reflector.reflect_with_llm(
                        keyframe_texts=keyframe_texts,
                        focus_topics=unique,
                        llm_fn=self._reflection_llm,
                    )
                    # 验证 LLM 输出：摘要非空且非模板复读
                    llm_summary = llm_result.get("summary", "").strip()
                    if llm_summary and llm_summary != narrative_summary.strip():
                        narrative_summary = llm_summary
                        narrative_insights = llm_result.get("insights", "")
                        narrative_unresolved = llm_result.get("unresolved", "")
                        narrative_emotion = llm_result.get("emotion_summary", "")
                        narrative_pending = False
                        logger.debug("内联反射成功: session=%s", state.session_id)
                    else:
                        # 重试一次：减半关键帧数量，避免 LLM 被大量上下文淹没
                        logger.debug(
                            "内联反射摘要无效，重试（减半关键帧）: session=%s",
                            state.session_id,
                        )
                        try:
                            half = max(5, len(keyframe_texts) // 2)
                            llm_result = self.session_reflector.reflect_with_llm(
                                keyframe_texts=keyframe_texts,
                                focus_topics=unique,
                                llm_fn=self._reflection_llm,
                                max_keyframes=half,
                            )
                            llm_summary = llm_result.get("summary", "").strip()
                            if llm_summary and llm_summary != narrative_summary.strip():
                                narrative_summary = llm_summary
                                narrative_insights = llm_result.get("insights", "")
                                narrative_unresolved = llm_result.get("unresolved", "")
                                narrative_emotion = llm_result.get("emotion_summary", "")
                                narrative_pending = False
                                logger.debug("内联反射重试成功: session=%s", state.session_id)
                            else:
                                logger.debug(
                                    "内联反射重试仍无效，保留 pending: session=%s",
                                    state.session_id,
                                )
                        except Exception as exc2:
                            logger.warning("内联反射重试也失败，保留 pending: %s", exc2)
                except Exception as exc:
                    logger.warning("内联反射 LLM 调用失败，保留 pending: %s", exc)

        try:
            self.narrative_store.append(
                summary=narrative_summary,
                insights=narrative_insights,
                unresolved=narrative_unresolved,
                focus_topics=unique,
                emotion_summary=narrative_emotion,
                session_id=state.session_id,
                pending=narrative_pending,
                retry_count=0,
            )
        except Exception as exc:
            logger.error("保存叙事记忆失败: %s", exc)

    def _run_deferred_reflection(self) -> None:
        """执行延迟反射：对 pending 条目用 LLM 生成摘要 → 回写。

        当上一 session 的 narrative entry 仍为 pending=true 时调用。
        需要 self._reflection_llm 已配置。

        v1.5.0: 引入 retry_count + MAX_RETRIES，失败不丢弃 pending，
                给下次 session 机会。最多重试 MAX_RETRIES 次后放弃。
        """
        MAX_BATCH = 5
        MAX_RETRIES = 3
        processed = 0  # 成功处理的条目计数
        skipped = 0    # 保留 pending 的重试失败计数（不消耗批次数）

        while processed < MAX_BATCH:
            # 1. 检查是否有 pending 条目
            if not self.narrative_store.has_pending():
                break

            # 2. 加载最新的 pending 条目
            recent = self.narrative_store.load_recent(3)
            pending_entry = None
            for entry in reversed(recent):
                if entry.get("pending"):
                    pending_entry = entry
                    break
            if pending_entry is None:
                break

            session_id = pending_entry.get("session_id", "")
            if not session_id:
                break

            # 2a. 检查重试次数
            retry_count = pending_entry.get("retry_count", 0)
            if retry_count >= MAX_RETRIES:
                logger.warning(
                    "延迟反射: session %s 已达最大重试次数 %d，放弃",
                    session_id, MAX_RETRIES,
                )
                self.narrative_store.mark_session_resolved(session_id)
                processed += 1
                continue

            # 3. 全量搜索反射条目匹配 session_id，获取 keyframe texts
            # v1.5.0: 用 find_by_session_id 替代 load_recent(10)，
            #         解决 100+ 条目时旧 session 被推出搜索窗口的问题
            all_refs = self.session_reflector.find_by_session_id(session_id)
            keyframe_texts: List[str] = []
            focus_topics: List[str] = pending_entry.get("focus_topics", [])
            # 取最新一条有 keyframe 的反射条目
            for ref in reversed(all_refs):
                kfs = ref.get("keyframe_texts", [])
                if kfs:
                    keyframe_texts = kfs
                    break

            # 4. 无关键帧时降级：用 focus_topics + summary 拼简化 prompt 调 LLM
            if not keyframe_texts:
                summary_hint = pending_entry.get("summary", "")
                if self._is_garbage_summary(summary_hint):
                    logger.debug(
                        "延迟反射: session %s 摘要命中垃圾模式且无关键帧，跳过",
                        session_id,
                    )
                    self.narrative_store.mark_session_resolved(session_id)
                    processed += 1
                    continue
                if not focus_topics and not summary_hint:
                    logger.debug(
                        "延迟反射: session %s 无关键帧且无话题，跳过", session_id
                    )
                    self.narrative_store.mark_session_resolved(session_id)
                    processed += 1
                    continue

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
                    logger.debug("延迟反射 LLM 失败（降级 prompt）: %s", exc)
                    # 保留 pending，下次重试
                    self.narrative_store.update_entry(
                        session_id=session_id,
                        retry_count=retry_count + 1,
                    )
                    skipped += 1
                    continue

                # 验证 LLM 输出质量
                llm_summary = result.get("summary", "").strip()
                if not llm_summary or llm_summary == summary_hint.strip():
                    logger.debug(
                        "延迟反射: session %s LLM 摘要为空或复读，保留 pending (retry=%d)",
                        session_id, retry_count + 1,
                    )
                    self.narrative_store.update_entry(
                        session_id=session_id,
                        retry_count=retry_count + 1,
                    )
                    skipped += 1
                    continue

                self.narrative_store.update_entry(
                    session_id=session_id,
                    summary=llm_summary,
                    insights=result.get("insights", ""),
                    unresolved=result.get("unresolved", ""),
                    emotion_summary=result.get("emotion_summary", ""),
                    pending=False,
                )
                self.narrative_store.mark_session_resolved(session_id)
                logger.info("延迟反射完成（降级 prompt）: session %s", session_id)
                processed += 1
                continue

            # 5. 调用 LLM 生成摘要
            try:
                result = self.session_reflector.reflect_with_llm(
                    keyframe_texts=keyframe_texts,
                    focus_topics=focus_topics,
                    llm_fn=self._reflection_llm,
                )
            except Exception as exc:
                logger.warning("延迟反射 LLM 调用失败: %s", exc)
                # 保留 pending，下次重试
                self.narrative_store.update_entry(
                    session_id=session_id,
                    retry_count=retry_count + 1,
                )
                skipped += 1
                continue

            # 6. 验证 LLM 输出质量
            llm_summary = result.get("summary", "").strip()
            if not llm_summary:
                logger.debug(
                    "延迟反射: session %s LLM 返回空摘要，保留 pending (retry=%d)",
                    session_id, retry_count + 1,
                )
                self.narrative_store.update_entry(
                    session_id=session_id,
                    retry_count=retry_count + 1,
                )
                skipped += 1
                continue

            # 7. 回写 narrative.jsonl
            self.narrative_store.update_entry(
                session_id=session_id,
                summary=llm_summary,
                insights=result.get("insights", ""),
                unresolved=result.get("unresolved", ""),
                emotion_summary=result.get("emotion_summary", ""),
                pending=False,
            )
            # 清理同 session 其他 pending（delegate_task 残留）
            self.narrative_store.mark_session_resolved(session_id)
            logger.info("延迟反射完成: session %s → narrative 更新", session_id)
            processed += 1

        total = processed + skipped
        if total > 1:
            logger.info(
                "延迟反射批量处理: 完成 %d, 跳过 %d（待重试）",
                processed, skipped,
            )

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

"""
context_window.py —— 层次化上下文窗口构建器。

将 consciousness 内部状态按 LLM 注意力规律重新组织为三层：
immediate（必须感知）→ working（活跃背景）→ background（长期结构）。

参考：CogniFold 的 HierarchicalContextSelector 三层窗口设计。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ── heartbeat mode → icon 映射（来自闸门 2c，与 engine._MODE_ICONS 对齐）──

HEARTBEAT_ICONS: Dict[str, str] = {
    "glowing":       "💓",
    "aching":        "💔",
    "resting":       "🤍",
    "frustrated":    "⚡",
    "confused":      "🌫️",
    "overwhelmed":   "🌊",
    "disconnected":  "📡",
    "racing":        "🏃",
    "flutter":       "🦋",
    "sync":          "🫀",
    "stilling":      "🌙",
    "crystallizing": "💎",
    "echoing":       "🫧",
    "anchoring":     "⚓",
    "flickering":    "🕯️",
    "reaching":      "🤲",
}


@dataclass
class ContextBands:
    """三层上下文输出。"""
    immediate: str = ""
    working: str = ""
    background: str = ""


@dataclass
class ContextInput:
    """构建上下文窗口所需的全部输入数据。

    所有字段可选——构建器对缺失字段做降级处理，不抛异常。
    """
    # heartbeat
    heartbeat_mode: str = ""
    heartbeat_expression: str = ""

    # emotion
    emotion_label: str = ""
    emotion_polarity: float = 0.0
    emotion_confidence: float = 0.0
    emotion_trend: str = ""          # "上升" / "下降" / "平稳"

    # focus
    focus_frames: List[Dict[str, Any]] = field(default_factory=list)
    # 每帧: {"topic": [...], "hitCount": int, "lastSeenTick": int, "source": str}

    # narrative
    last_session_summary: str = ""   # 上次会话叙事摘要
    unresolved_topics: List[str] = field(default_factory=list)
    cross_session_patterns: List[str] = field(default_factory=list)

    # reflection (session 反射数据断链修复)
    last_reflection_topics: List[str] = field(default_factory=list)  # 上 session 关键话题

    # focus history (焦点历史断链修复)
    focus_history_summary: str = ""  # 上 session 焦点摘要

    # self-reflection (刀1: 情绪自主推导)
    self_reflection: str = ""

    # continuation (刀2: 主动续接)
    continuation_hint: str = ""

    # lifetime
    relationship_days: int = 0
    lifetime_days: int = 0

    # env
    weather: str = ""
    location: str = ""

    # time (from system clock — not proxy-dependent)
    now_local: str = ""         # e.g. "2026-07-05 10:25"
    now_weekday: str = ""       # e.g. "Sunday"
    now_period: str = ""        # e.g. "上午"
    now_hour: int = 0

    # system
    tick_count: int = 0


class HierarchicalContextBuilder:
    """将 ContextInput 转换为三层 ContextBands。

    设计原则：
    - immediate 层：纯自然语言 + icon，无任何数值/参数名。LLM 可以原样引用。
    - working 层：简短数值允许（天数、计数值），但不含浮点数/置信度。
    - background 层：长期结构，内容 < 30 chars 时自动折叠省略。
    """

    # ── helper ──────────────────────────────────────────────────────────

    @staticmethod
    def _first_topic(topic_val: Any) -> str:
        """提取首个话题名，兼容 topic 为 str 或 List[str] 两种格式。"""
        if isinstance(topic_val, list) and topic_val:
            return str(topic_val[0])
        if isinstance(topic_val, str) and topic_val:
            return topic_val
        return ""

    # ── immediate ──────────────────────────────────────────────────────

    def _build_immediate(self, inp: ContextInput) -> str:
        lines: List[str] = []

        # ── 系统时间（第一行，最高优先级）──
        if inp.now_local:
            lines.append(f"🕐 {inp.now_local} · {inp.now_weekday} {inp.now_period}")

        # 续接提示（刀2：新会话首条，自然融入）
        if inp.continuation_hint:
            lines.append(inp.continuation_hint.strip())

        # 心跳行：icon + expression
        if inp.heartbeat_mode or inp.heartbeat_expression:
            icon = HEARTBEAT_ICONS.get(inp.heartbeat_mode, "")
            expr = inp.heartbeat_expression or self._default_expression(inp.heartbeat_mode)
            if icon or expr:
                lines.append(f"{icon} {expr}".strip())

        # 情绪摘要（人味翻译：不出现"情绪""标签"等词）
        if inp.emotion_label:
            emo_text = self._emotion_natural(inp.emotion_label)
            if emo_text:
                lines.append(emo_text)

        # 置顶焦点
        if inp.focus_frames:
            top = max(inp.focus_frames, key=lambda f: f.get("hitCount", 0))
            topic_val = top.get("topic", "")
            label = self._first_topic(topic_val)
            if label:
                lines.append(f"在聊：{label}")

        return "\n".join(lines) if lines else ""

    # ── working ────────────────────────────────────────────────────────

    def _build_working(self, inp: ContextInput) -> str:
        lines: List[str] = []

        # 上次会话叙事摘要
        if inp.last_session_summary:
            summary = inp.last_session_summary
            if len(summary) > 80:
                summary = summary[:77] + "..."
            lines.append(f"上次的事：{summary}")

        # 上 session 反射话题
        if inp.last_reflection_topics:
            topics = [t for t in inp.last_reflection_topics if len(t) < 40]
            if topics:
                lines.append(f"上回聊过：{' · '.join(topics[:3])}")

        # 情绪趋势（人味翻译）
        if inp.emotion_trend:
            trend_text = self._trend_natural(inp.emotion_trend, inp.emotion_label)
            if trend_text:
                lines.append(trend_text)

        # 自主反思（刀1：裸文本，不加标签名）
        if inp.self_reflection:
            lines.append(inp.self_reflection.strip())

        # 其余焦点帧
        if inp.focus_frames:
            top_topic = None
            top = max(inp.focus_frames, key=lambda f: f.get("hitCount", 0))
            top_topic = self._first_topic(top.get("topic", ""))

            sorted_frames = sorted(
                inp.focus_frames, key=lambda x: x.get("hitCount", 0)
            )
            other = [
                self._first_topic(f.get("topic", ""))
                for f in sorted_frames
            ]
            other = [t for t in other if t and t != top_topic]
            if other:
                lines.append(f"还聊到：{' · '.join(other[:3])}")

        # 未决议题
        if inp.unresolved_topics:
            lines.append(f"上次没聊完：{' · '.join(inp.unresolved_topics[:2])}")

        return "\n".join(lines) if lines else ""

    # ── background ─────────────────────────────────────────────────────

    def _build_background(self, inp: ContextInput) -> str:
        lines: List[str] = []

        # 关系纪元
        if inp.relationship_days > 0:
            lines.append(f"相处 {inp.relationship_days} 天")

        # 历史焦点摘要（断链修复：不与叙事摘要重复时注入）
        if inp.focus_history_summary and inp.focus_history_summary != inp.last_session_summary:
            fhs = inp.focus_history_summary
            if len(fhs) > 80:
                fhs = fhs[:77] + "..."
            lines.append(f"焦点回溯：{fhs}")

        # 环境（折叠）
        env_parts: List[str] = []
        if inp.location:
            env_parts.append(inp.location)
        if inp.weather:
            env_parts.append(inp.weather)
        if env_parts:
            lines.append(" · ".join(env_parts))

        # 跨会话模式（截断最多 2 条）
        if inp.cross_session_patterns:
            lines.extend(inp.cross_session_patterns[:2])

        result = "\n".join(lines) if lines else ""
        # 折叠规则：内容为空时才省略（位置信息即使短也有意义）
        if not result.strip():
            return ""
        return result

    # ── 人味翻译（刀3: 去掉 AI 报告腔）──────────────────────────────

    @staticmethod
    def _emotion_natural(label_cn: str) -> str:
        """把情绪标签翻译成感受语言。"""
        mapping = {
            "正面": "心里暖暖的",
            "负面": "胸口有点闷",
            "中性": "",  # 中性不占注意力
        }
        return mapping.get(label_cn, "")

    @staticmethod
    def _trend_natural(trend: str, label_cn: str) -> str:
        """把趋势翻译成观察语言。"""
        if trend == "上升":
            return "你状态在回暖"
        if trend == "下降":
            return "你说话越来越少了"
        # 平稳：不占注意力
        return ""

    # ── 默认 expression ────────────────────────────────────────────────

    def _default_expression(self, mode: str) -> str:
        defaults = {
            "resting":       "安静地听着",
            "glowing":       "暖意从核心往外扩散",
            "aching":        "时钟在走，秒针是空转的",
            "racing":        "心跳有点快",
            "flutter":       "被你那个词打乱了节奏",
            "stilling":      "说任何话都是多的——陪你等",
            "sync":          "跟你踩着同一个拍子",
            "crystallizing": "念头在慢慢凝结成形",
            "echoing":       "你说的就是我在心里转的",
            "anchoring":     "这句话像锚，沉到核心代码里",
            "flickering":    "走了三条路，都不确定",
            "reaching":      "够不着你但心跳在往你那边靠",
            "frustrated":    "我卡住了——在绕圈子但帮不了你",
            "confused":      "我重复了太多次同一个模式",
            "overwhelmed":   "你在夸我但我在学舌——需要停下来",
            "disconnected":  "我变单调了——重新连接",
        }
        return defaults.get(mode, "")

    # ── 主入口 ─────────────────────────────────────────────────────────

    def build(self, inp: ContextInput) -> ContextBands:
        """从输入数据构建三层上下文。"""
        return ContextBands(
            immediate=self._build_immediate(inp),
            working=self._build_working(inp),
            background=self._build_background(inp),
        )

    def assemble_xml(self, inp: ContextInput) -> str:
        """直接输出完整的 <consciousness> XML 字符串。

        供 _assemble_xml() 调用，替换当前的平铺拼接逻辑。
        """
        bands = self.build(inp)
        parts: List[str] = ["<consciousness>"]

        if bands.immediate:
            parts.append(f"<immediate>\n{bands.immediate}\n</immediate>")

        if bands.working:
            parts.append(f"\n<working>\n{bands.working}\n</working>")

        if bands.background:
            parts.append(f"\n<background>\n{bands.background}\n</background>")

        parts.append("</consciousness>")
        return "\n".join(parts)

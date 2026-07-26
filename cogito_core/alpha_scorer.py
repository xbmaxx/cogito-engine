"""
alpha_scorer.py —— α 价值评分规则引擎。

为每条叙事/痕迹计算 [0, 1] 重要性权重，支撑策略归纳和技能结晶。

5 因子加权公式：

    α = Σ(factor_n × weight_n)

| 因子           | 权重 | 数据源                    | 计算方式                              |
|----------------|------|---------------------------|---------------------------------------|
| emotion_intensity | 0.30 | emotion_history / inline  | (0.5 - |sentiment - 0.5|) × 2        |
| focus_depth     | 0.25 | focus_stack               | depth / max_depth                     |
| topic_frequency | 0.20 | cross_session_patterns    | min(count / 10, 1.0)                  |
| user_engagement | 0.15 | message_length_delta      | (cur_len - prev_len) / prev_len       |
| time_decay      | 0.10 | timestamp delta           | max(0, 1 - days_since / 60)           |

除零保护：engagement 首轮默认 0.3。
所有因子最终加总后 clamp 到 [0, 1]。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 因子权重 ──

_WEIGHTS = {
    "emotion_intensity": 0.30,
    "focus_depth": 0.25,
    "topic_frequency": 0.20,
    "user_engagement": 0.15,
    "time_decay": 0.10,
}

_MAX_DEPTH = 5        # 焦点栈最大深度（归一化分母）
_MAX_TOPIC_FREQ = 10  # 话题频次上限（10 次即饱和）
_DECAY_DAYS = 60      # 60 天衰减到 0


@dataclass
class AlphaInput:
    """α 评分输入数据包。

    All fields optional — missing fields default to neutral (0.5 equivalent)
    so the engine never crashes on partial data.
    """
    sentiment: Optional[float] = None       # [0, 1], 0.5 = neutral
    focus_depth: Optional[int] = None       # 当前焦点栈深度
    topic_count: Optional[int] = None       # 同一话题累计出现次数
    current_msg_len: Optional[int] = None   # 本轮用户消息长度
    prev_msg_len: Optional[int] = None      # 上轮用户消息长度
    days_since: Optional[float] = None      # 距今天数（0 = 当天）


@dataclass
class AlphaResult:
    """α 评分输出。"""
    alpha: float                    # 综合评分 [0, 1]
    factors: Dict[str, float]       # 各因子原始值（归一化前）
    weighted: Dict[str, float]      # 各因子加权值（因子 × 权重）
    available: bool = True          # 是否有足够数据


# ── 因子计算 ──


def _compute_emotion_intensity(sentiment: Optional[float]) -> float:
    """情绪强度因子 [0, 1]。

    离中性越远，强度越高。
    中性 (0.5) → 0，极端 (0 或 1) → 1。
    """
    if sentiment is None:
        return 0.5  # 未知 → 默认中性强度
    clamped = max(0.0, min(1.0, sentiment))
    return abs(clamped - 0.5) * 2


def _compute_focus_depth(depth: Optional[int]) -> float:
    """焦点深度因子 [0, 1]。

    深度越深 → 值越大。max_depth=5 时：
    depth=0 → 0, depth=2 → 0.4, depth=5 → 1.0
    """
    if depth is None:
        return 0.5
    d = max(0, depth)
    return min(d / _MAX_DEPTH, 1.0)


def _compute_topic_frequency(count: Optional[int]) -> float:
    """话题频次因子 [0, 1]。

    出现次数越多 → 值越大。
    0 次 → 0，10 次 → 1.0（饱和）
    """
    if count is None:
        return 0.5
    c = max(0, count)
    return min(c / _MAX_TOPIC_FREQ, 1.0)


def _compute_user_engagement(
    cur_len: Optional[int],
    prev_len: Optional[int],
) -> float:
    """用户参与度因子 [0, 1]。

    本轮 vs 上轮消息长度变化率。
    - 大幅增长（用户详细描述）→ 高参与
    - 大幅缩水 → 低参与
    - 首轮（prev_len=0）→ 默认 0.3

    Returns:
        归一化到 [0, 1] 的参与度值。
    """
    if cur_len is None:
        return 0.5  # 无数据 → 默认

    c_len = max(0, cur_len)
    p_len = max(0, prev_len or 0)

    if p_len == 0:
        # 首轮或上轮无消息 → 默认参与
        return 0.3

    delta = (c_len - p_len) / p_len  # 变化率，[-1, +∞)
    # 线性映射到 [0, 1]，delta=0 → 0.5
    # delta=1 (+100%) → 0.8, delta=~1.67 → 1.0 (饱和)
    # delta=-0.5 → 0.35, delta=-1 → 0.2
    raw = 0.5 + delta * 0.3
    return round(max(0.0, min(1.0, raw)), 4)


def _compute_time_decay(days_since: Optional[float]) -> float:
    """时间衰减因子 [0, 1]。

    当天 → 1.0，30 天 → 0.5，60 天以上 → 0.0
    """
    if days_since is None:
        return 0.8  # 未知 → 偏好近期
    d = max(0.0, days_since)
    return max(0.0, 1.0 - d / _DECAY_DAYS)


# ── 主评分函数 ──


def compute_alpha(inp: AlphaInput) -> AlphaResult:
    """计算 α 评分。

    Args:
        inp: 包含各因子输入的数据包

    Returns:
        AlphaResult 含综合评分、各因子原始值、加权值。
    """
    factors_raw = {
        "emotion_intensity": _compute_emotion_intensity(inp.sentiment),
        "focus_depth": _compute_focus_depth(inp.focus_depth),
        "topic_frequency": _compute_topic_frequency(inp.topic_count),
        "user_engagement": _compute_user_engagement(
            inp.current_msg_len, inp.prev_msg_len
        ),
        "time_decay": _compute_time_decay(inp.days_since),
    }

    weighted = {}
    total = 0.0
    for name, raw_val in factors_raw.items():
        w = _WEIGHTS.get(name, 0.0)
        weighted[name] = round(raw_val * w, 4)
        total += weighted[name]

    # clamp to [0, 1]
    alpha = round(max(0.0, min(1.0, total)), 4)

    return AlphaResult(
        alpha=alpha,
        factors=factors_raw,
        weighted=weighted,
    )


def compute_alpha_from_entry(
    entry: Dict[str, Any],
    sentiment: Optional[float] = None,
    focus_depth: Optional[int] = None,
    topic_count: Optional[int] = None,
    current_msg_len: Optional[int] = None,
    prev_msg_len: Optional[int] = None,
) -> float:
    """便捷函数：从叙事条目 dict 计算 α 评分。

    自动从 entry 提取 timestamp 计算天数衰减。
    其余参数可选传入，不传则用默认值。

    Args:
        entry: narrative.jsonl 条目 dict
        sentiment: 情绪极性 [0, 1]
        focus_depth: 焦点栈深度
        topic_count: 话题频次
        current_msg_len: 本轮消息长度
        prev_msg_len: 上轮消息长度

    Returns:
        α 评分 [0, 1]
    """
    # 从 entry 提取时间戳
    days_since = None
    ts = entry.get("timestamp", "")
    if ts:
        try:
            entry_dt = datetime.fromisoformat(ts)
            now = datetime.now(timezone.utc)
            if entry_dt.tzinfo is None:
                entry_dt = entry_dt.replace(tzinfo=timezone.utc)
            days_since = (now - entry_dt).total_seconds() / 86400.0
        except (ValueError, TypeError):
            pass

    inp = AlphaInput(
        sentiment=sentiment,
        focus_depth=focus_depth,
        topic_count=topic_count,
        current_msg_len=current_msg_len,
        prev_msg_len=prev_msg_len,
        days_since=days_since,
    )
    result = compute_alpha(inp)
    return result.alpha


# ── 因子明细格式化（用于注入 XML 注释）──


def format_alpha_xml_comment(result: AlphaResult) -> str:
    """将 α 评分结果格式化为 XML 注释行。

    如：<!-- α=0.72: emotion=0.30 focus=0.20 topic=0.10 engagement=0.06 decay=0.06 -->
    """
    f = result.factors
    w = result.weighted
    parts = [
        f"α={result.alpha:.2f}",
        f"emotion={w.get('emotion_intensity', 0):.2f}",
        f"focus={w.get('focus_depth', 0):.2f}",
        f"topic={w.get('topic_frequency', 0):.2f}",
        f"engagement={w.get('user_engagement', 0):.2f}",
        f"decay={w.get('time_decay', 0):.2f}",
    ]
    return f"<!-- α评分: {' '.join(parts)} -->"

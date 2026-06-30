"""
temporal.py —— 相对时间词解析。

将中文口语中的相对时间表达转换为 ISO 8601 区间。
纯函数，零外部依赖。

核心算法来源：白龙马（MIT）

示例：
    "刚刚" → ("2024-01-15T10:30:00+08:00", "2024-01-15T10:35:00+08:00")
    "今天上午" → ("2024-01-15T06:00:00+08:00", "2024-01-15T12:00:00+08:00")
    "昨天" → ("2024-01-14T00:00:00+08:00", "2024-01-15T00:00:00+08:00")
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple


# ── 相对时间词 → (开始偏移, 结束偏移, 是否含小时) ──
_RELATIVE_RULES: list[tuple[str, str, tuple[int, int, bool]]] = [
    # (正则模式, 描述, (开始偏移秒, 结束偏移秒, 是否精确到小时))
    ("刚刚", "just now", (-300, 0, True)),
    ("刚才", "just now", (-300, 0, True)),
    ("现在", "now", (0, 0, True)),
    ("此刻", "now", (0, 0, True)),
    ("今早", "this morning", (-3600 * 6, 0, False)),
    ("今天早上", "this morning", (-3600 * 6, 0, False)),
    ("今天上午", "this morning", (-3600 * 6, 0, False)),
    ("上午", "morning", (-3600 * 6, 0, False)),
    ("中午", "noon", (-3600 * 2, 0, False)),
    ("今天下午", "this afternoon", (-3600 * 6, 0, False)),
    ("下午", "afternoon", (-3600 * 6, 0, False)),
    ("今天晚上", "this evening", (-3600 * 4, 0, False)),
    ("今晚", "this evening", (-3600 * 4, 0, False)),
    ("今天", "today", (-3600 * 12, 0, False)),
    ("昨天", "yesterday", (-3600 * 36, -3600 * 12, False)),
    ("前天", "day before yesterday", (-3600 * 60, -3600 * 36, False)),
    ("明天", "tomorrow", (0, 3600 * 24, False)),
    ("后天", "day after tomorrow", (3600 * 24, 3600 * 48, False)),
    ("本周", "this week", (-3600 * 24 * 7, 0, False)),
    ("上周", "last week", (-3600 * 24 * 14, -3600 * 24 * 7, False)),
    ("下周", "next week", (0, 3600 * 24 * 7, False)),
    ("本月", "this month", (-3600 * 24 * 30, 0, False)),
    ("上个月", "last month", (-3600 * 24 * 60, -3600 * 24 * 30, False)),
    ("下个月", "next month", (0, 3600 * 24 * 30, False)),
    ("今年", "this year", (-3600 * 24 * 365, 0, False)),
    ("去年", "last year", (-3600 * 24 * 730, -3600 * 24 * 365, False)),
    ("明年", "next year", (0, 3600 * 24 * 365, False)),
    (r"\d+分钟前", "minutes ago", (0, 0, True)),
    (r"\d+小时前", "hours ago", (0, 0, True)),
    (r"\d+天前", "days ago", (0, 0, True)),
    (r"\d+分钟(?:之?)后", "minutes later", (0, 0, True)),
    (r"\d+小时(?:之?)后", "hours later", (0, 0, True)),
    (r"\d+天(?:之?)后", "days later", (0, 0, True)),
]

# 数字提取模式
_NUM_RE = re.compile(r"(\d+)")


def parse_relative_time(
    text: str,
    reference: Optional[datetime] = None,
) -> Optional[Tuple[str, str]]:
    """解析中文相对时间词为 ISO 8601 区间。

    Args:
        text: 含相对时间词的中文文本
        reference: 参考时间（默认现在），带时区的 datetime

    Returns:
        (开始ISO, 结束ISO) 或 None（无匹配时）
    """
    if not text or not isinstance(text, str):
        return None

    if reference is None:
        reference = datetime.now().astimezone()

    # 统一换行
    text_clean = text.replace("\n", " ").strip()

    for pattern, _desc, (delta_start, delta_end, has_hour) in _RELATIVE_RULES:
        if not re.search(pattern, text_clean):
            continue

        # 处理带数字的规则
        if _NUM_RE.search(pattern):
            num_match = _NUM_RE.search(text_clean)
            if num_match:
                num = int(num_match.group(1))
                if "分钟" in pattern:
                    delta_start = -num * 60
                elif "小时" in pattern:
                    delta_start = -num * 3600
                elif "天" in pattern:
                    delta_start = -num * 86400
                if "后" in pattern:
                    delta_start = abs(delta_start)
                    delta_end = delta_start
                else:
                    delta_end = 0

        start_dt = reference + timedelta(seconds=delta_start)
        end_dt = reference + timedelta(seconds=delta_end)

        # 对于非精确模式，对齐到天的边界
        if not has_hour:
            start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            end_dt = end_dt.replace(hour=0, minute=0, second=0, microsecond=0)

        return (start_dt.isoformat(), end_dt.isoformat())

    return None


# ── 时间区间格式化 ──

_TIME_WINDOWS = {
    "凌晨": (0, 5),
    "清晨": (5, 9),
    "上午": (9, 12),
    "中午": (12, 14),
    "下午": (14, 18),
    "傍晚": (18, 21),
    "深夜": (21, 24),
}


def get_time_window(
    reference: Optional[datetime] = None,
) -> str:
    """获取当前时间窗口名称。

    Returns:
        "凌晨" | "清晨" | "上午" | "中午" | "下午" | "傍晚" | "深夜"
    """
    if reference is None:
        reference = datetime.now().astimezone()

    hour = reference.hour

    for name, (start, end) in _TIME_WINDOWS.items():
        if start <= hour < end:
            return name

    return "深夜"


def get_period(
    reference: Optional[datetime] = None,
) -> str:
    """获取当前时间段（英文）。

    Returns:
        "morning" | "noon" | "afternoon" | "evening" | "night"
    """
    if reference is None:
        reference = datetime.now().astimezone()

    hour = reference.hour

    if hour < 5:
        return "night"
    elif hour < 9:
        return "morning"
    elif hour < 12:
        return "morning"
    elif hour < 14:
        return "noon"
    elif hour < 18:
        return "afternoon"
    elif hour < 21:
        return "evening"
    return "night"

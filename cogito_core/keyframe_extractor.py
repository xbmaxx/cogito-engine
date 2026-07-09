"""
keyframe_extractor.py —— 从对话历史中提取关键帧。

每 interval 轮取一轮作为"关键帧"
- 优先保留用户消息（user role）
- 包含轮次的 assessment 信息
- 降级：消息不足时取全部

O(n) 单次遍历，无额外内存分配。
平台无关版本 —— 零外部依赖。
"""

from __future__ import annotations

from typing import Optional

# agent/assistant 角色名集合
_ASSISTANT_ROLES: frozenset[str] = frozenset({"assistant"})


class KeyframeExtractor:
    """从对话历史中提取关键帧。

    关键帧 = 从完整对话中按间隔采样的代表性消息，
    用于后续生成叙事总结。

    Attributes:
        interval: 每隔多少轮取一帧（默认 5）
        max_frames: 最多取多少帧（默认 20，防止过长）
    """

    def __init__(self, interval: int = 5, max_frames: int = 20) -> None:
        self.interval = max(1, interval)
        self.max_frames = max(1, max_frames)

    def extract(self, messages: list[dict]) -> list[dict]:
        """从消息列表中提取关键帧。

        策略（按优先级）：
        1. 对话长度足够 → 每 interval 轮取一帧
        2. 在每个窗口内优先选择 user 消息
        3. 无 user 消息时取该窗口第一条
        4. 总消息数 < interval → 返回全部

        Args:
            messages: 对话消息列表，每条含 role/content，
                      可选含 assessment 字段。

        Returns:
            关键帧列表（原消息 dict 的浅拷贝）。
        """
        if not messages:
            return []

        n = len(messages)
        # 降级：消息不足 interval 时取全部
        if n <= self.interval:
            return list(messages)

        frames: list[dict] = []
        # 按 interval 分窗口，每窗口选一条最优消息
        for window_start in range(0, n, self.interval):
            window_end = min(window_start + self.interval, n)
            window = messages[window_start:window_end]

            # 优先选 user 消息
            chosen = _pick_best_in_window(window)
            if chosen is not None:
                frames.append(_copy_frame(chosen))

            # 达到 max_frames 上限
            if len(frames) >= self.max_frames:
                break

        return frames


def _pick_best_in_window(window: list[dict]) -> Optional[dict]:
    """在一个窗口内选择最优消息作为关键帧。

    优先级：
    1. 含 assessment 字段的 user 消息
    2. 普通 user 消息
    3. 含 assessment 的消息
    4. 第一条消息
    """
    if not window:
        return None

    # 分类
    user_msgs = [m for m in window if m.get("role") == "user"]
    user_with_assessment = [m for m in user_msgs if m.get("assessment")]
    non_user_with_assessment = [
        m for m in window if m.get("role") != "user" and m.get("assessment")
    ]

    # 按优先级选取
    if user_with_assessment:
        return user_with_assessment[-1]  # 取窗口内最后一条（最新）
    if user_msgs:
        return user_msgs[-1]
    if non_user_with_assessment:
        return non_user_with_assessment[-1]
    return window[0]


def _copy_frame(msg: dict) -> dict:
    """浅拷贝消息，仅保留关键字段以节省内存。

    保留: role, content, assessment, name, timestamp
    """
    keep_keys = {"role", "content", "assessment", "name", "timestamp"}
    return {k: v for k, v in msg.items() if k in keep_keys}


def estimate_conversation_rounds(messages: list[dict]) -> int:
    """估算对话轮数（user → assistant 对）。

    用于确定合适的 interval 值。
    """
    return sum(1 for m in messages if m.get("role") == "user")

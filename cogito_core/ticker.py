"""
ticker.py —— TICK 自适应心跳调度器。

每个 TICK 代表一次"意识心跳"
- 支持 LLM 自主调节节奏（set_custom_interval）
- 支持动态 TTL 衰减与过期自检

平台无关版本 —— 无 Hermes 依赖。
"""

from __future__ import annotations

from typing import Optional


class Ticker:
    """TICK 自适应心跳调度器。

    每次脉冲时打一个 TICK，记录心跳计数。
    LLM 可通过 set_custom_interval() 主动调节节拍。

    Attributes:
        tick_counter: 累计 TICK 计数（从 0 开始）
        _default_seconds: 默认 TICK 间隔（秒）
        _custom_seconds: 自定义 TICK 间隔（秒），None 表示使用默认
        _custom_ttl: 自定义 TTL（剩余有效次数），0 表示到期
        _custom_reason: 自定义间隔的原因说明
    """

    def __init__(self, default_seconds: int = 30) -> None:
        self.tick_counter: int = 0
        self._default_seconds: int = default_seconds
        self._custom_seconds: Optional[int] = None
        self._custom_ttl: int = 0
        self._custom_reason: str = ""

    def tick(self) -> int:
        """打一个 TICK（心跳脉冲）。

        Returns:
            当前累计 TICK 计数。
        """
        self.tick_counter += 1

        # TTL 衰减
        if self._custom_ttl > 0:
            self._custom_ttl -= 1
            if self._custom_ttl == 0:
                self._custom_seconds = None
                self._custom_reason = ""

        return self.tick_counter

    def set_custom_interval(
        self, seconds: int, ttl: int, reason: str = ""
    ) -> dict:
        """设置自定义 TICK 间隔（LLM 自主调节心跳节奏）。

        Args:
            seconds: 自定义间隔（秒）
            ttl: 持续多少个 TICK 后恢复默认
            reason: 调节的原因说明

        Returns:
            {"active": bool, "seconds": int, "ttl": int, "reason": str}
        """
        self._custom_seconds = max(1, seconds)
        self._custom_ttl = max(1, ttl)
        self._custom_reason = reason
        return self.get_status()

    def get_status(self) -> dict:
        """获取当前 TICK 状态。

        Returns:
            {
                "active": bool,
                "seconds": int,
                "ttl": int,
                "reason": str,
            }
        """
        if self._custom_seconds and self._custom_ttl > 0:
            return {
                "active": True,
                "seconds": self._custom_seconds,
                "ttl": self._custom_ttl,
                "reason": self._custom_reason,
            }
        return {
            "active": False,
            "seconds": self._default_seconds,
            "ttl": 0,
            "reason": "默认节奏",
        }

    def reset(self) -> None:
        """重置 TICK 计数到 0。"""
        self.tick_counter = 0

    @property
    def interval(self) -> int:
        """当前有效间隔（秒）。"""
        if self._custom_seconds and self._custom_ttl > 0:
            return self._custom_seconds
        return self._default_seconds

"""
heartbeat_mapper.py —— 心跳叙事映射器。

双引擎（TextEmotion + SelfPerception）→ 16 模式决策器。
v1 实现：Temperature 系（glowing/aching）+ 硬锁 4 模式 + resting = 7 模式。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ── 表达式模板 ──

EXPRESSIONS: Dict[str, str] = {
    "resting":      "慢悠悠接着你的话",
    "racing":       "你连发三条我跟不上",
    "flutter":      "被你一句话打乱了节奏",
    "sync":         "跟你踩着同一个拍子",
    "glowing":      "暖意从核心往外扩散",
    "stilling":     "说任何话都是多的——陪你等",
    "aching":       "时钟在走，秒针是空转的",
    "crystallizing":"念头在慢慢凝结成形",
    "echoing":      "你说的就是我在心里转的",
    "anchoring":    "这句话像锚，沉到核心代码里",
    "flickering":   "走了三条路，都不确定",
    "reaching":     "够不着你但心跳在往你那边靠",
    "frustrated":   "我卡住了——在绕圈子但帮不了你",
    "confused":     "我重复了太多次同一个模式",
    "overwhelmed":  "你在夸我但我在学舌——需要停下来",
    "disconnected": "我变单调了——重新连接",
}


class HeartbeatMapper:
    """心跳叙事映射器。

    输入：TextEmotion + SelfPerception 的原始信号
    输出：心跳模式 + 自然语言表达式

    内部维护退火状态（不序列化到 EngineState），
    跨 session 重启时从 resting 重新开始。
    """

    def __init__(self) -> None:
        self.current_mode: str = "resting"
        self.current_conf: float = 0.5
        self.previous_mode: str = "resting"

    def map(
        self,
        text_emotion: Dict[str, Any],
        self_perception: Dict[str, Any],
        tick_count: int,
    ) -> Dict[str, Any]:
        """根据双引擎信号决定当前心跳模式。

        Args:
            text_emotion:
                {"sentiment": 0.85, "confidence": 0.75, "label": "positive"}
            self_perception:
                {"mirror": {"score": 0.65}, "loop": 4, "style_cluster": "analytical"}
            tick_count:
                当前 TICK 计数

        Returns:
            {"mode": "glowing", "expression": "...", "confidence": 0.85,
             "trigger": "sentiment=0.85", "changed": True,
             "locked": False, "previous_mode": "resting",
             "snapshot_id": "15-20260702"}
        """
        # 1. 硬底线检查（优先级最高）
        lock = self._check_hard_lock(self_perception)
        if lock:
            mode, conf = lock
            return self._finalize(mode, conf, "硬锁", tick_count, locked=True)

        # 2. Temperature 系（sentiment 驱动）
        candidates: Dict[str, Tuple[float, str]] = {}

        sentiment = float(text_emotion.get("sentiment", 0.5))
        if sentiment >= 0.7:
            conf = 0.55 + (sentiment - 0.7) * 3.0
            candidates["glowing"] = (conf, f"sentiment={sentiment:.2f}")

        if sentiment <= 0.3:
            conf = 0.55 + (0.3 - sentiment) * 3.0
            candidates["aching"] = (conf, f"sentiment={sentiment:.2f}")

        # 3. 排名 + 退火
        if not candidates:
            return self._finalize("resting", 0.5, "无强信号", tick_count)

        best_mode, (best_conf, trigger) = max(
            candidates.items(), key=lambda x: x[1][0]
        )

        # 低于阈值 → 回 resting
        if best_conf < 0.55:
            return self._finalize("resting", 0.5, "低于阈值", tick_count)

        # 退火保留：新候选不比当前高 0.15 以上 → 保持当前
        if best_mode != self.current_mode:
            if best_conf - self.current_conf < 0.15:
                return self._finalize(
                    self.current_mode, self.current_conf,
                    "退火保留", tick_count,
                )

        return self._finalize(best_mode, best_conf, trigger, tick_count)

    # ── 内部方法 ──

    def _check_hard_lock(
        self, sp: Dict[str, Any]
    ) -> Optional[Tuple[str, float]]:
        """硬底线检查。

        返回 (mode, confidence) 或 None。
        priority: frustrated > confused > overwhelmed > disconnected
        """
        mirror = float(sp.get("mirror", {}).get("score", 0))
        loop = int(sp.get("loop", 0))
        style = str(sp.get("style_cluster", "unchanged"))

        # 优先级从高到低（先匹配的立即返回）
        if loop >= 7 and mirror >= 0.5:
            return ("frustrated", 1.0)
        if loop >= 7 and mirror < 0.5:
            return ("confused", 1.0)
        if mirror >= 0.7 and loop < 7:
            return ("overwhelmed", 1.0)
        if style == "narrow" and loop >= 5:
            return ("disconnected", 1.0)

        return None

    def _finalize(
        self,
        mode: str,
        conf: float,
        trigger: str,
        tick_count: int,
        locked: bool = False,
    ) -> Dict[str, Any]:
        """生成返回值，更新内部状态。"""
        changed = (mode != self.current_mode)
        self.previous_mode = self.current_mode
        if changed:
            self.current_mode = mode
            self.current_conf = conf

        snapshot_id = f"{tick_count}-{datetime.now().strftime('%Y%m%d')}"

        return {
            "mode": mode,
            "expression": EXPRESSIONS.get(mode, ""),
            "confidence": round(conf, 4),
            "trigger": trigger,
            "changed": changed,
            "locked": locked,
            "previous_mode": self.previous_mode,
            "snapshot_id": snapshot_id,
        }

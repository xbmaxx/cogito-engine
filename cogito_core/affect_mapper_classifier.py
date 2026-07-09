"""
affect_mapper_classifier.py —— AffectMapper 情绪坐标映射模型。

将 DUTIR 七维离散情绪输出映射到 Valence/Arousal 连续坐标空间，
产出五象限分类标签，零外部依赖。

设计：
- Phase 1: 调用 EmotionClassifier 获取 DUTIR 7-dim 输出
- Phase 2: 加权重心法映射至 V/A 空间
- Phase 3: 象限映射 + 置信度计算
- 质量门：DUTIR 低质量输出时返回中性结果

AffectMapper 坐标映射 —— 七维情绪词至 V/A 连续空间映射表。
"""

from __future__ import annotations

import math
from typing import Any, Dict

# ── 坐标映射表 ──
# DUTIR 七维 → Valence/Arousal 坐标
# 来源：AffectMapper (1980) 情绪词 V/A 评分，语义相近词聚类取均值
_DIM_TO_VA: Dict[str, tuple] = {
    "好": (0.75, 0.25),   # 满足、满意 → 中高 V，低 A
    "乐": (0.85, 0.65),   # 快乐、兴奋 → 高 V，中高 A
    "哀": (0.20, 0.20),   # 悲伤、忧郁 → 低 V，低 A
    "怒": (0.15, 0.80),   # 愤怒、烦躁 → 低 V，高 A
    "惧": (0.15, 0.70),   # 恐惧、焦虑 → 低 V，高 A
    "恶": (0.10, 0.40),   # 厌恶、轻蔑 → 极低 V，中低 A
    "惊": (0.50, 0.85),   # 惊讶（中性）→ 中性 V，高 A
}

# ── 象限边界（基于 V/A 坐标的 5 象限分类）──
# 条件：V ≥ 0.6 ∧ A ≥ 0.5 → excited
#        V ≥ 0.6 ∧ A < 0.5 → content
#        0.4 ≤ V < 0.6     → neutral
#        V < 0.4 ∧ A ≥ 0.5 → distressed
#        V < 0.4 ∧ A < 0.5 → melancholy
_NEG_THRESHOLD = 0.4
_POS_THRESHOLD = 0.6
_AROUSAL_THRESHOLD = 0.5
_QUALITY_GATE = 0.1  # DUTIR 各维度最低信号阈值

# ── 象限标签 → legacy 情绪倾向映射 ──
_QUADRANT_SENTIMENT: Dict[str, float] = {
    "excited": 0.85,
    "content": 0.70,
    "neutral": 0.50,
    "distressed": 0.25,
    "melancholy": 0.30,
}

# ── 模型元信息 ──
MODEL_NAME = "affect_mapper"
MODEL_DIMS = ["valence", "arousal"]
MODEL_VERSION = "1.0"


def _va_to_label(valence: float, arousal: float) -> str:
    """根据 V/A 坐标判定象限标签。"""
    if valence >= _POS_THRESHOLD:
        return "excited" if arousal >= _AROUSAL_THRESHOLD else "content"
    if valence >= _NEG_THRESHOLD:
        return "neutral"
    # valence < _NEG_THRESHOLD
    return "distressed" if arousal >= _AROUSAL_THRESHOLD else "melancholy"


def _compute_confidence(valence: float, arousal: float) -> float:
    """从中心点 (0.5, 0.5) 的距离计算置信度。

    距离越远→置信度越高（情绪越明确）。
    中性文本（靠近中心）→置信度接近 0。
    """
    distance = math.sqrt((valence - 0.5) ** 2 + (arousal - 0.5) ** 2)
    return min(1.0, distance * 1.5)


def _neutral_result() -> Dict[str, Any]:
    """返回中性结果（质量门触发或 DUTIR 异常时使用）。"""
    return {
        "available": True,
        "emotions": {
            "valence": 0.5,
            "arousal": 0.3,
        },
        "dominant": "neutral",
        "confidence": 0.0,
        "method": "affect_mapper_neutral",
    }


class Classifier:
    """AffectMapper 情绪坐标映射分类器。

    以 DUTIR 七维离散输出为底层，投影到连续 V/A 坐标空间。
    无需外部设备或训练数据，零外部 Python 依赖。

    Usage:
        clf = Classifier()
        result = clf.classify("今天心情不错")
        # → {"emotions": {"valence": 0.72, "arousal": 0.31},
        #     "dominant": "content", "confidence": 0.35, ...}
    """

    MODEL_NAME = MODEL_NAME
    MODEL_DIMS = MODEL_DIMS
    MODEL_VERSION = MODEL_VERSION

    def __init__(self, dict_path: str | None = None) -> None:
        """初始化 AffectMapper 映射器。

        Args:
            dict_path: 兼容性参数，AffectMapper 不使用外部词典。
                       仅用于 EmotionModelRegistry._get_or_create() 兼容。
        """
        self._dict_path = dict_path

    def is_available(self) -> bool:
        """AffectMapper 始终可用（无外部依赖）。"""
        return True

    def classify(self, text: str) -> Dict[str, Any]:
        """执行 DUTIR → V/A 映射。

        Args:
            text: 输入文本

        Returns:
            {
                "available": True,
                "emotions": {"valence": v, "arousal": a},
                "dominant": "content",
                "confidence": 0.72,
                "method": "affect_mapper",
            }
        """
        if not text or not text.strip():
            return _neutral_result()

        # Phase 1: 获取 DUTIR 7-dim 输出
        # 惰性导入避免循环依赖
        from .emotion_classifier import EmotionClassifier

        try:
            dutir = EmotionClassifier(dict_path=self._dict_path)
            raw = dutir.classify(text)
        except Exception:
            return _neutral_result()

        if not raw.get("available", False):
            return _neutral_result()

        emotions = raw.get("emotions", {})
        if not emotions:
            return _neutral_result()

        # 质量门：所有维度概率极低 → 无情绪信号
        if max(emotions.values()) < _QUALITY_GATE:
            return _neutral_result()

        # Phase 2: 加权重心法映射至 V/A 空间
        total_prob = 0.0
        v_sum = 0.0
        a_sum = 0.0

        for dim, prob in emotions.items():
            if dim not in _DIM_TO_VA:
                continue
            va = _DIM_TO_VA[dim]
            v_sum += prob * va[0]
            a_sum += prob * va[1]
            total_prob += prob

        if total_prob <= 0:
            return _neutral_result()

        valence = v_sum / total_prob
        arousal = a_sum / total_prob

        # Phase 3: 象限映射 + 置信度
        dominant = _va_to_label(valence, arousal)
        confidence = _compute_confidence(valence, arousal)

        return {
            "available": True,
            "emotions": {
                "valence": round(valence, 4),
                "arousal": round(arousal, 4),
            },
            "dominant": dominant,
            "confidence": round(confidence, 4),
            "method": "affect_mapper",
        }

    # ── 向后兼容适配器 ──

    def detect(self, text: str) -> Dict[str, Any]:
        """兼容旧版 detect() 接口。

        Returns:
            classify() 结果（不含旧版字段——由下游 enrich_legacy_fields 处理）
        """
        result = self.classify(text)
        from .emotion_protocol import enrich_legacy_fields
        return enrich_legacy_fields(result)

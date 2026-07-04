"""
text_emotion.py —— 文本情感分析。

使用 SnowNLP 实现零 LLM 成本的情感检测。
支持中文情感极性分析。

平台无关版本 —— 无 Hermes 依赖。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class TextEmotionDetector:
    """文本情感检测器（基于 SnowNLP）。

    Attributes:
        _threshold: 置信度阈值（低于此值视为中性）
    """

    def __init__(self, threshold: float = 0.15) -> None:
        self._threshold = threshold
        self._snownlp = None

    def _ensure_snownlp(self) -> bool:
        """延迟加载 SnowNLP。"""
        if self._snownlp is not None:
            return True
        try:
            from snownlp import SnowNLP
            self._snownlp = SnowNLP
            return True
        except ImportError:
            logger.warning("SnowNLP 未安装，情感分析不可用")
            return False

    def detect(self, text: str) -> Dict[str, Any]:
        """检测文本情感。

        Args:
            text: 中文文本

        Returns:
            {
                "label": "positive" | "negative" | "neutral",
                "label_cn": "正面" | "负面" | "中性",
                "sentiment": float,   # 0.0-1.0 极性（>0.5 偏正）
                "confidence": float,  # 0.0-1.0 置信度
            }
        """
        result: Dict[str, Any] = {
            "label": "neutral",
            "label_cn": "中性",
            "sentiment": 0.5,
            "confidence": 0.0,
        }

        if not text or not isinstance(text, str):
            return result

        if not self._ensure_snownlp():
            return result

        try:
            s = self._snownlp(text)
            sentiment = s.sentiments
            # 计算置信度（离 0.5 越远越确信）
            confidence = abs(sentiment - 0.5) * 2

            if sentiment > 0.6:
                label = "positive"
                label_cn = "正面"
            elif sentiment < 0.4:
                label = "negative"
                label_cn = "负面"
            else:
                label = "neutral"
                label_cn = "中性"

            result["label"] = label
            result["label_cn"] = label_cn
            result["sentiment"] = round(sentiment, 4)
            result["confidence"] = round(confidence, 4)
        except Exception as exc:
            logger.debug("情感分析失败: %s", exc)

        return result


# ── 简易回退：基于关键词的快速情感检测（不需要 SnowNLP） ──

_POSITIVE_WORDS = frozenset({
    "好", "棒", "赞", "厉害", "优秀", "出色", "完美", "喜欢", "爱",
    "开心", "高兴", "快乐", "满意", "感谢", "谢谢", "感动", "温暖",
    "支持", "加油", "期待", "漂亮", "帅", "酷", "牛逼", "强大",
    "好用", "方便", "快捷", "稳定", "可靠", "优雅",
})

_NEGATIVE_WORDS = frozenset({
    "差", "烂", "糟", "讨厌", "烦", "恶心", "垃圾", "失望", "难受",
    "难过", "伤心", "痛苦", "生气", "愤怒", "焦虑", "害怕", "恐惧",
    "失败", "错误", "问题", "bug", "崩溃", "卡", "慢", "不行",
    "不好", "糟糕", "惨", "无聊", "没用",
})


def quick_sentiment(text: str) -> Dict[str, Any]:
    """基于关键词的快速情感检测（无需 SnowNLP）。

    适用场景：环境中安装 SnowNLP 失败时的回退方案。

    Returns:
        与 TextEmotionDetector.detect() 相同格式。
    """
    if not text or not isinstance(text, str):
        return {
            "label": "neutral",
            "label_cn": "中性",
            "sentiment": 0.5,
            "confidence": 0.0,
        }

    pos_count = sum(1 for w in _POSITIVE_WORDS if w in text)
    neg_count = sum(1 for w in _NEGATIVE_WORDS if w in text)

    total = pos_count + neg_count
    if total == 0:
        return {
            "label": "neutral",
            "label_cn": "中性",
            "sentiment": 0.5,
            "confidence": 0.0,
        }

    sentiment = pos_count / max(total, 1)
    confidence = abs(sentiment - 0.5) * 2 * min(total / 5, 1.0)

    if sentiment > 0.6:
        label = "positive"
        label_cn = "正面"
    elif sentiment < 0.4:
        label = "negative"
        label_cn = "负面"
    else:
        label = "neutral"
        label_cn = "中性"

    return {
        "label": label,
        "label_cn": label_cn,
        "sentiment": round(sentiment, 4),
        "confidence": round(confidence, 4),
    }

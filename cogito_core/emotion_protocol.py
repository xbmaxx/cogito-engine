"""
emotion_protocol.py —— 情绪模型结构协议 + 字段适配器。

定义情绪分类器的接口契约（typing.Protocol + duck typing 双重检查），
以及引擎层对 legacy 字段的自动合成。

任何 Python 模块，只要暴露 Classifier 类并实现 classify() 和 is_available()，
即可作为 Cogito 情绪模型使用。无需继承任何基类。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# ── 情绪正负面维度映射 ──

_POSITIVE_DIMS = frozenset({
    "好", "乐", "excited", "content",
    "peace", "acceptance", "courage", "positive",
    "joy", "love", "hope", "trust",
})

_NEGATIVE_DIMS = frozenset({
    "哀", "怒", "惧", "恶", "惊",
    "distressed", "melancholy",
    "apathy", "grief", "fear", "anger", "disgust", "sadness",
    "sad", "angry", "fearful", "disgusted",
})


@runtime_checkable
class EmotionClassifierProtocol(Protocol):
    """情绪分类器结构协议。

    任何情绪模型只需满足此协议即可被 CogitoEngine 加载。
    引擎通过 isinstance(instance, EmotionClassifierProtocol) 和
    hasattr 双重校验。

    Attributes:
        MODEL_NAME: 模型标识，用于 method 字段
        MODEL_DIMS: 模型维度列表，用于 list_models() 元信息
        MODEL_VERSION: 模型版本号（可选）
    """
    MODEL_NAME: str = "unknown"
    MODEL_DIMS: list = []
    MODEL_VERSION: str = "1.0"

    def is_available(self) -> bool:
        """模型是否可用（词典/依赖是否加载成功）。"""
        ...

    def classify(self, text: str) -> Dict[str, Any]:
        """对输入文本进行情绪分类。

        Args:
            text: 输入文本

        Returns:
            dict 包含以下字段：
            - available (bool): 模型是否可用
            - emotions (dict[str, float]): 各维度概率
            - dominant (str): 主导情绪标签，无情绪时为 "none"
            - confidence (float): 置信度 [0, 1]
            - method (str): 模型标识
        """
        ...


def is_valid_model(mod) -> bool:
    """检查模块是否符合情绪模型协议。

    双重检查：先查 Classifier 属性存在，再查关键方法可调用。

    Args:
        mod: Python 模块对象

    Returns:
        True 如果模块暴露了有效的 Classifier 类
    """
    cls = getattr(mod, "Classifier", None)
    if cls is None:
        return False
    return (
        callable(getattr(cls, "classify", None))
        and callable(getattr(cls, "is_available", None))
    )


def enrich_legacy_fields(result: Dict[str, Any]) -> Dict[str, Any]:
    """从 classify() 返回的 emotions + dominant 合成 legacy 字段。

    引擎的 classify_with_fallback() 在返回前调用此函数，自动添加
    label/label_cn/sentiment/polarity 字段，确保下游消费者
    （heartbeat_mapper、persistence、XML assembly）不受影响。

    如果模型已提供 label 字段，则跳过自动填充（模型可以覆盖默认行为）。

    Args:
        result: classify() 的原始返回

    Returns:
        添加 legacy 字段后的结果 dict
    """
    if "label" in result:
        return result  # 模型已提供，跳过

    dominant = result.get("dominant", "none")
    confidence = float(result.get("confidence", 0.0))

    if dominant in _POSITIVE_DIMS:
        val = 0.5 + confidence * 0.5
        result.update({
            "label": "positive",
            "label_cn": "正面",
            "sentiment": round(val, 4),
            "polarity": round(val, 4),
        })
    elif dominant in _NEGATIVE_DIMS:
        val = 0.5 - confidence * 0.5
        result.update({
            "label": "negative",
            "label_cn": "负面",
            "sentiment": round(val, 4),
            "polarity": round(val, 4),
        })
    else:
        result.update({
            "label": "neutral",
            "label_cn": "中性",
            "sentiment": 0.5,
            "polarity": 0.5,
        })
    return result

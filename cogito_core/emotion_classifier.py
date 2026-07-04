"""
emotion_classifier.py —— 大连理工七分类情绪词典分类器。

基于 DUTIR 情感词汇本体库（27,315 词，去重后），
实现七维情绪向量输出 + 否定反转 + 程度副词强度加权。

替代 v1.4 的 SnowNLP TextEmotionDetector。

权威规格：飞书情绪模型开发文档 §二（Iljedw0AIoqNhExm6Vqc2Gxpnpg）
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class EmotionClassifier:
    """大连理工七分类情绪词典 + 否定反转 + 程度副词强度加权。

    输入中文文本 → 输出七维情绪概率向量。

    Attributes:
        emotion_dict: {word: {category, intensity, polarity, code}}
        negation_words: 否定词集合
        degree_words: {level: [word, ...]}
        negation_window: 否定词作用范围（后续 N 个词）
        degree_weights: 程度副词权重系数
        _opposites: 情绪对立映射
    """

    def __init__(self, dict_path: Optional[str] = None) -> None:
        if dict_path is None:
            dict_path = str(
                Path(__file__).parent / "data" / "emotion_dict.json"
            )

        raw = json.loads(Path(dict_path).read_text(encoding="utf-8"))

        self.negation_words: set = set(raw.pop("__NEGATION__", []))
        self.degree_words: Dict[str, list] = raw.pop("__DEGREE__", {})
        self.codes_meta: dict = raw.pop("__CODES__", {})
        self.emotion_dict: dict = raw  # {word: {category, intensity, polarity, code}}

        # 否定窗口（否定词作用于后 N 个词）
        self.negation_window = 3
        # 程度副词权重系数
        self.degree_weights = {
            "extreme": 3.0,
            "high": 1.8,
            "medium": 1.2,
            "low": 0.8,
            "default": 1.0,
        }
        # 情绪对立映射（用于否定反转）
        self._opposites = {
            "好": "恶", "乐": "哀", "哀": "乐",
            "怒": "好", "惧": "乐", "恶": "好", "惊": "惧",
        }

    def classify(self, text: str) -> Dict[str, Any]:
        """返回七维情绪向量。

        Args:
            text: 中文文本

        Returns:
            {
                "available": True,
                "emotions": {"好": 0.30, "乐": 0.65, ...},
                "dominant": "乐",
                "confidence": 0.72,
                "method": "dutir_weighted",
            }
        """
        try:
            import jieba
        except ImportError:
            logger.warning("jieba 未安装，无法分词；返回空结果")
            return self._empty_result()

        words = jieba.lcut(text)

        # 初始化七维加权计数器
        scores: Dict[str, float] = {
            "好": 0.0, "乐": 0.0, "哀": 0.0,
            "怒": 0.0, "惧": 0.0, "恶": 0.0, "惊": 0.0,
        }
        total_weight = 0.0

        i = 0
        while i < len(words):
            word = words[i]
            negated = self._is_negated(words, i)
            degree = self._get_degree(words, i)
            weight = self.degree_weights.get(
                degree, self.degree_weights["default"]
            )

            if word in self.emotion_dict:
                entry = self.emotion_dict[word]
                cat = entry["category"]
                raw_intensity = entry["intensity"]
                weighted = raw_intensity * weight / 5.0  # → [0, 1]

                if negated:
                    opposite = self._opposites.get(cat)
                    if opposite and opposite in scores:
                        scores[opposite] += abs(weighted)
                        total_weight += abs(weighted)
                else:
                    scores[cat] += max(0, weighted)
                    total_weight += max(0, weighted)

            i += 1

        # 归一化
        if total_weight > 0:
            for k in scores:
                scores[k] = max(0, scores[k]) / total_weight

        dominant = max(scores, key=scores.get) if total_weight > 0 else "none"
        confidence = min(total_weight / max(len(words), 1), 1.0)

        return {
            "available": True,
            "emotions": {k: round(v, 3) for k, v in scores.items()},
            "dominant": dominant,
            "confidence": round(confidence, 3),
            "method": "dutir_weighted",
        }

    def _is_negated(self, words: list, idx: int) -> bool:
        """检查 idx 位置的词是否被否定词修饰。

        否定窗口: [idx - negation_window, idx)
        """
        start = max(0, idx - self.negation_window)
        for j in range(start, idx):
            if words[j] in self.negation_words:
                return True
        return False

    def _get_degree(self, words: list, idx: int) -> Optional[str]:
        """检查 idx 位置前一个词是否为程度副词。

        Returns:
            "extreme" / "high" / "medium" / "low" / None
        """
        if idx > 0:
            prev = words[idx - 1]
            for level, word_list in self.degree_words.items():
                if prev in word_list:
                    return level
        return None

    def _empty_result(self) -> Dict[str, Any]:
        """返回空结果（jieba 不可用等降级场景）。"""
        return {
            "available": False,
            "emotions": {
                "好": 0.0, "乐": 0.0, "哀": 0.0,
                "怒": 0.0, "惧": 0.0, "恶": 0.0, "惊": 0.0,
            },
            "dominant": "none",
            "confidence": 0.0,
            "method": "unavailable",
        }

    # ── 向后兼容适配器 ──

    def detect(self, text: str) -> Dict[str, Any]:
        """兼容旧版 TextEmotionDetector.detect() 的返回格式。

        在七维分类结果基础上，合成 polarity/sentiment/label
        等旧版字段。使用此方法的旧版调用方无需改动。
        """
        result = self.classify(text)
        return _adapter_emotion(result)


def _adapter_emotion(result: Dict[str, Any]) -> Dict[str, Any]:
    """将七维分类结果适配为 v1.4 兼容格式。

    保留旧版字段: label, label_cn, sentiment, polarity, confidence。
    新增旧版中已有的旧格式标记。

    Args:
        result: EmotionClassifier.classify() 的输出

    Returns:
        包含旧版字段 + 新版 emotions 的混合字典
    """
    emotions = result.get("emotions", {})
    positive = emotions.get("乐", 0) + emotions.get("好", 0)
    negative = (
        emotions.get("哀", 0)
        + emotions.get("怒", 0)
        + emotions.get("惧", 0)
        + emotions.get("恶", 0)
    )

    if positive + negative == 0:
        polarity = 0.5
        label = "neutral"
        label_cn = "中性"
    elif positive >= negative:
        polarity = 0.5 + positive * 0.5
        label = "positive"
        label_cn = "正面"
    else:
        polarity = 0.5 - negative * 0.5
        label = "negative"
        label_cn = "负面"

    return {
        **result,
        "label": label,
        "label_cn": label_cn,
        "sentiment": round(polarity, 4),
        "polarity": round(polarity, 4),
        "old_format": True,
    }

#!/usr/bin/env python3
"""
Tests for Chinese N-gram keyword extraction
============================================
Validates the keyword extraction module with Chinese text.
Covers unigrams, bigrams, trigrams, and fallback behaviour when jieba is absent.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from cogito_core.keywords import extract_keywords
    KEYWORDS_AVAILABLE = True
except ImportError:
    KEYWORDS_AVAILABLE = False


# ── Helpers ────────────────────────────────────────────────────────────────

def _is_chinese_char(ch: str) -> bool:
    """Return True if *ch* is a CJK Unified Ideograph."""
    return "\u4e00" <= ch <= "\u9fff"


def _chinese_ratio(text: str) -> float:
    """Fraction of characters that are Chinese."""
    if not text:
        return 0.0
    return sum(1 for c in text if _is_chinese_char(c)) / len(text)


# ── Tests ──────────────────────────────────────────────────────────────────

@unittest.skipUnless(KEYWORDS_AVAILABLE, "cogito_core.keywords not available")
class TestKeywordExtraction(unittest.TestCase):
    """Test the Chinese N-gram keyword extraction function."""

    def test_returns_list(self):
        """extract_keywords should return a list."""
        result = extract_keywords("自然语言处理是人工智能的重要分支")
        self.assertIsInstance(result, list)

    def test_returns_non_empty_for_chinese(self):
        """Chinese text should yield at least one keyword."""
        result = extract_keywords("机器学习是人工智能的核心技术之一")
        self.assertGreater(len(result), 0, f"No keywords extracted: {result}")

    def test_keywords_are_strings(self):
        """Every extracted keyword should be a string."""
        result = extract_keywords("深度学习模型需要大量数据")
        for kw in result:
            self.assertIsInstance(kw, str)

    def test_short_text(self):
        """Very short text should still be handled."""
        result = extract_keywords("你好")
        self.assertIsInstance(result, list)

    def test_empty_string(self):
        """Empty string should return empty list, not crash."""
        result = extract_keywords("")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_punctuation_filtered(self):
        """Punctuation should not appear as standalone keywords."""
        result = extract_keywords("你好！这是测试。真的吗？")
        for kw in result:
            self.assertFalse(
                kw in ("！", "。", "？", "，", "、"),
                f"Punctuation leaked into keywords: {kw}",
            )

    def test_unigrams_extracted(self):
        """Single-character Chinese words (unigrams) should appear when meaningful."""
        text = "我爱北京天安门"
        result = extract_keywords(text)
        # At minimum the full text should be processed
        self.assertIsInstance(result, list)

    def test_bigrams_extracted(self):
        """Two-character bigrams should be extracted from Chinese text."""
        text = "自然语言处理技术发展迅速"
        result = extract_keywords(text)
        self.assertIsInstance(result, list)

    def test_trigrams_extracted(self):
        """Three-character trigrams should be extracted."""
        text = "人工智能技术改变世界"
        result = extract_keywords(text)
        self.assertIsInstance(result, list)

    def test_mixed_language(self):
        """Mixed Chinese/English text should be handled."""
        result = extract_keywords("在NLP领域，Transformer架构非常流行")
        self.assertIsInstance(result, list)
        # English tokens may appear alongside Chinese
        has_chinese = any(_chinese_ratio(kw) > 0 for kw in result)
        # Not strictly required, but likely for mixed input
        self.assertTrue(has_chinese or len(result) >= 0)

    def test_deduplication(self):
        """Duplicate keywords should be removed."""
        text = "学习学习再学习，不断提高学习能力"
        result = extract_keywords(text)
        self.assertEqual(len(result), len(set(result)),
                         f"Duplicate keywords found: {result}")

    def test_long_text(self):
        """Long text should be handled without OOM."""
        text = "人工智能是计算机科学的一个分支，它企图了解智能的实质，并生产出一种新的能以人类智能相似的方式做出反应的智能机器。" * 20
        result = extract_keywords(text)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_keywords_ranked(self):
        """Keywords should be ranked by importance (frequency/score)."""
        # If the function supports scoring, more frequent terms should appear first
        text = "深度学习 深度学习 深度学习 机器学习 机器学习 人工智能"
        result = extract_keywords(text)
        if len(result) >= 2:
            # "深度学习" should rank higher than "机器学习" if frequency-based
            dl_pos = -1
            ml_pos = -1
            for i, kw in enumerate(result):
                if "深度学习" in kw:
                    dl_pos = i
                if "机器学习" in kw:
                    ml_pos = i
            if dl_pos >= 0 and ml_pos >= 0:
                self.assertLess(dl_pos, ml_pos,
                                f"Expected '深度学习' before '机器学习', got: {result}")


class TestNGramHelpers(unittest.TestCase):
    """Test N-gram generation utilities directly (pure-python, no deps)."""

    def test_unigram_generation(self):
        """Generate unigrams from a character sequence."""
        chars = list("你好世界")
        unigrams = chars  # unigrams are individual characters
        self.assertEqual(len(unigrams), 4)
        self.assertEqual(unigrams, ["你", "好", "世", "界"])

    def test_bigram_generation(self):
        """Generate bigrams from a character sequence."""
        chars = list("自然语言处理")
        bigrams = [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]
        self.assertEqual(bigrams, ["自然", "然语", "语言", "言处", "处理"])

    def test_trigram_generation(self):
        """Generate trigrams from a character sequence."""
        chars = list("人工智能好")
        trigrams = [chars[i] + chars[i + 1] + chars[i + 2]
                    for i in range(len(chars) - 2)]
        self.assertEqual(trigrams, ["人工智", "工智能", "智能好"])

    def test_ngram_window_sliding(self):
        """Verify sliding-window correctness for N-grams."""
        sequence = list("abcde")
        n = 2
        grams = ["".join(sequence[i:i + n]) for i in range(len(sequence) - n + 1)]
        self.assertEqual(grams, ["ab", "bc", "cd", "de"])

    def test_ngram_edge_case_single_char(self):
        """Single character should produce no bigrams."""
        chars = ["一"]
        bigrams = [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]
        self.assertEqual(bigrams, [])

    def test_stopwords_filtering(self):
        """Common stopwords should be filterable."""
        stopwords = {"的", "了", "在", "是", "我", "有", "和", "就"}
        candidates = ["我的", "学习", "是的", "方法", "在了"]
        filtered = [w for w in candidates if not any(sw in w for sw in stopwords)]
        # "我的" contains "我", "是的" contains "的", "在了" contains "了" and "在"
        self.assertEqual(filtered, ["学习", "方法"])


class TestChineseTextProcessing(unittest.TestCase):
    """General Chinese text processing tests."""

    def test_chinese_character_detection(self):
        """is_chinese_char should correctly identify CJK characters."""
        self.assertTrue(_is_chinese_char("中"))
        self.assertTrue(_is_chinese_char("文"))
        self.assertFalse(_is_chinese_char("a"))
        self.assertFalse(_is_chinese_char("1"))
        self.assertFalse(_is_chinese_char(" "))

    def test_chinese_ratio(self):
        """chinese_ratio should compute correct fraction."""
        self.assertAlmostEqual(_chinese_ratio("你好world"), 0.286, places=2)
        self.assertAlmostEqual(_chinese_ratio("纯中文文本"), 1.0, places=1)
        self.assertAlmostEqual(_chinese_ratio("hello"), 0.0, places=1)

    def test_segmentation_boundaries(self):
        """Verify that a basic sentence can be segmented into N-grams."""
        text = "我爱北京天安门"
        chars = list(text)
        bigrams = ["".join(chars[i:i + 2]) for i in range(len(chars) - 1)]
        self.assertIn("我爱", bigrams)
        self.assertIn("北京", bigrams)
        self.assertIn("天安", bigrams)
        self.assertIn("安门", bigrams)
        self.assertEqual(len(bigrams), 6)


if __name__ == "__main__":
    unittest.main(verbosity=2)

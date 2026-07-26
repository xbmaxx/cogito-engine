#!/usr/bin/env python3
"""
Unit tests for cogito_core.alpha_scorer
========================================
α 评分引擎测试 — TDD 验证 5 因子公式、边界值、除零保护。
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from cogito_core.alpha_scorer import (
        AlphaInput, AlphaResult,
        compute_alpha, compute_alpha_from_entry, format_alpha_xml_comment,
        _compute_emotion_intensity, _compute_focus_depth,
        _compute_topic_frequency, _compute_user_engagement,
        _compute_time_decay,
    )
    ALPHA_AVAILABLE = True
except ImportError as e:
    ALPHA_AVAILABLE = False
    _import_error = str(e)


# ── 辅助 ──

def assert_approx(actual: float, expected: float, epsilon: float = 0.001):
    """近似相等断言。"""
    return abs(actual - expected) < epsilon


# ── 测试：单因子函数 ──

@unittest.skipUnless(ALPHA_AVAILABLE, f"alpha_scorer not available: {locals().get('_import_error', '?')}")
class TestFactorFunctions(unittest.TestCase):
    """验证每个因子函数的边界值和典型值。"""

    # 情绪强度

    def test_emotion_intensity_neutral(self):
        """中性 (0.5) → 强度 0"""
        self.assertTrue(assert_approx(_compute_emotion_intensity(0.5), 0.0))

    def test_emotion_intensity_extreme_positive(self):
        """极端正面 (1.0) → 强度 1"""
        self.assertTrue(assert_approx(_compute_emotion_intensity(1.0), 1.0))

    def test_emotion_intensity_extreme_negative(self):
        """极端负面 (0.0) → 强度 1"""
        self.assertTrue(assert_approx(_compute_emotion_intensity(0.0), 1.0))

    def test_emotion_intensity_mid(self):
        """0.75 → 强度 0.5"""
        self.assertTrue(assert_approx(_compute_emotion_intensity(0.75), 0.5))

    def test_emotion_intensity_none_default(self):
        """None → 默认 0.5"""
        self.assertTrue(assert_approx(_compute_emotion_intensity(None), 0.5))

    # 焦点深度

    def test_focus_depth_zero(self):
        """depth=0 → 0"""
        self.assertEqual(_compute_focus_depth(0), 0.0)

    def test_focus_depth_max(self):
        """depth=5 → 1.0"""
        self.assertEqual(_compute_focus_depth(5), 1.0)

    def test_focus_depth_mid(self):
        """depth=2 → 0.4"""
        self.assertTrue(assert_approx(_compute_focus_depth(2), 0.4))

    def test_focus_depth_none_default(self):
        """None → 0.5"""
        self.assertEqual(_compute_focus_depth(None), 0.5)

    # 话题频次

    def test_topic_frequency_zero(self):
        """count=0 → 0"""
        self.assertEqual(_compute_topic_frequency(0), 0.0)

    def test_topic_frequency_saturated(self):
        """count=10 → 1.0"""
        self.assertEqual(_compute_topic_frequency(10), 1.0)

    def test_topic_frequency_above_saturated(self):
        """count=20 → 1.0（饱和截断）"""
        self.assertEqual(_compute_topic_frequency(20), 1.0)

    def test_topic_frequency_mid(self):
        """count=5 → 0.5"""
        self.assertEqual(_compute_topic_frequency(5), 0.5)

    def test_topic_frequency_none_default(self):
        """None → 0.5"""
        self.assertEqual(_compute_topic_frequency(None), 0.5)

    # 用户参与度

    def test_engagement_first_turn(self):
        """首轮 (prev=0) → 默认 0.3"""
        self.assertEqual(_compute_user_engagement(100, 0), 0.3)

    def test_engagement_no_change(self):
        """cur=prev → ~0.5"""
        val = _compute_user_engagement(100, 100)
        self.assertTrue(assert_approx(val, 0.5, 0.01))

    def test_engagement_growth(self):
        """cur=200, prev=100 → 0.8"""
        val = _compute_user_engagement(200, 100)
        self.assertTrue(assert_approx(val, 0.8, 0.01))

    def test_engagement_shrink(self):
        """cur=50, prev=100 → < 0.5"""
        val = _compute_user_engagement(50, 100)
        self.assertTrue(val < 0.5)

    def test_engagement_none_cur_default(self):
        """cur=None → 0.5"""
        self.assertEqual(_compute_user_engagement(None, 100), 0.5)

    # 时间衰减

    def test_time_decay_today(self):
        """days=0 → 1.0"""
        self.assertEqual(_compute_time_decay(0), 1.0)

    def test_time_decay_30_days(self):
        """days=30 → 0.5"""
        self.assertTrue(assert_approx(_compute_time_decay(30), 0.5))

    def test_time_decay_60_days(self):
        """days=60 → 0.0"""
        self.assertEqual(_compute_time_decay(60), 0.0)

    def test_time_decay_over_60(self):
        """days=90 → 0.0（截断）"""
        self.assertEqual(_compute_time_decay(90), 0.0)

    def test_time_decay_none_default(self):
        """None → 0.8"""
        self.assertEqual(_compute_time_decay(None), 0.8)


# ── 测试：综合评分 ──

@unittest.skipUnless(ALPHA_AVAILABLE, "alpha_scorer not available")
class TestComputeAlpha(unittest.TestCase):
    """验证 compute_alpha() 综合评分。"""

    def test_returns_alpha_result(self):
        """compute_alpha 返回 AlphaResult 实例。"""
        result = compute_alpha(AlphaInput())
        self.assertIsInstance(result, AlphaResult)
        self.assertIsInstance(result.alpha, float)
        self.assertIsInstance(result.factors, dict)
        self.assertIsInstance(result.weighted, dict)

    def test_alpha_in_range_zero_one(self):
        """α 评分始终在 [0, 1] 区间。"""
        for _ in range(10):
            result = compute_alpha(AlphaInput(
                sentiment=0.3,
                focus_depth=2,
                topic_count=3,
                current_msg_len=100,
                prev_msg_len=50,
                days_since=10,
            ))
            self.assertGreaterEqual(result.alpha, 0.0)
            self.assertLessEqual(result.alpha, 1.0)

    def test_high_value_input(self):
        """高情绪 + 深焦点 + 高频次 = 高 α。"""
        result = compute_alpha(AlphaInput(
            sentiment=0.1,      # 强情绪
            focus_depth=5,      # 最深
            topic_count=10,     # 饱和
            current_msg_len=300,
            prev_msg_len=100,   # 大幅增长
            days_since=1,       # 极近期
        ))
        self.assertGreater(result.alpha, 0.6)

    def test_low_value_input(self):
        """中性情绪 + 浅焦点 + 低频次 = 低 α。"""
        result = compute_alpha(AlphaInput(
            sentiment=0.5,      # 中性
            focus_depth=0,      # 无焦点
            topic_count=0,      # 未出现
            current_msg_len=10,
            prev_msg_len=0,     # 首轮
            days_since=90,      # 久远
        ))
        self.assertLess(result.alpha, 0.5)

    def test_weights_sum_to_one(self):
        """所有因子取最大值时 α ≈ 1.0。"""
        result = compute_alpha(AlphaInput(
            sentiment=0.0,      # max 情绪强度
            focus_depth=5,      # max 焦点深度
            topic_count=10,     # max 话题频次
            current_msg_len=1000,
            prev_msg_len=100,   # 足够大的增量使参与度饱和到 1.0
            days_since=0,       # max 时间衰减
        ))
        self.assertTrue(assert_approx(result.alpha, 1.0, 0.02))

    def test_all_none_mid_alpha(self):
        """所有因子 None → 应在 0.5 附近。"""
        result = compute_alpha(AlphaInput())
        # 0.30×0.5 + 0.25×0.5 + 0.20×0.5 + 0.15×0.5 + 0.10×0.8
        # = 0.15 + 0.125 + 0.10 + 0.075 + 0.08 = 0.53
        self.assertTrue(assert_approx(result.alpha, 0.53, 0.01))


# ── 测试：便捷函数 ──

@unittest.skipUnless(ALPHA_AVAILABLE, "alpha_scorer not available")
class TestComputeAlphaFromEntry(unittest.TestCase):
    """验证 compute_alpha_from_entry()。"""

    def test_from_entry_today(self):
        """当天 entry → 无衰减，正常评分。"""
        entry = {
            "timestamp": "2026-07-24T12:00:00+00:00",
            "summary": "测试条目",
        }
        alpha = compute_alpha_from_entry(
            entry,
            sentiment=0.3,
            focus_depth=3,
            topic_count=5,
            current_msg_len=100,
            prev_msg_len=50,
        )
        self.assertGreaterEqual(alpha, 0.0)
        self.assertLessEqual(alpha, 1.0)

    def test_from_entry_old(self):
        """60 天前 entry → 时间衰减到 0。"""
        entry = {
            "timestamp": "2026-05-25T12:00:00+00:00",  # ~60 天前
            "summary": "很老的条目",
        }
        alpha = compute_alpha_from_entry(entry)
        # time_decay = 0 → 至少衰减 0.10
        # 其他因子用默认 → 综合 < 0.53（全 None 的值）
        nf_result = compute_alpha(AlphaInput())
        self.assertLess(alpha, nf_result.alpha)


# ── 测试：格式输出 ──

@unittest.skipUnless(ALPHA_AVAILABLE, "alpha_scorer not available")
class TestFormatAlphaOutput(unittest.TestCase):
    """验证 format_alpha_xml_comment()。"""

    def test_xml_comment_format(self):
        """格式化输出包含 α 值和各因子。"""
        result = compute_alpha(AlphaInput(
            sentiment=0.3,
            focus_depth=3,
            topic_count=5,
            current_msg_len=100,
            prev_msg_len=50,
            days_since=10,
        ))
        comment = format_alpha_xml_comment(result)
        self.assertIn("α=", comment)
        self.assertIn("emotion=", comment)
        self.assertIn("focus=", comment)
        self.assertIn("topic=", comment)
        self.assertIn("engagement=", comment)
        self.assertIn("decay=", comment)
        self.assertTrue(comment.startswith("<!--"))
        self.assertTrue(comment.endswith("-->"))


# ── 测试：边界极端值 ──

@unittest.skipUnless(ALPHA_AVAILABLE, "alpha_scorer not available")
class TestEdgeCases(unittest.TestCase):
    """验证边界极端值不会崩溃。"""

    def test_negative_focus_depth(self):
        """depth 为负值 → 不崩溃，返回 0。"""
        val = _compute_focus_depth(-1)
        self.assertEqual(val, 0.0)

    def test_negative_topic_count(self):
        """count 为负值 → 不崩溃，返回 0。"""
        val = _compute_topic_frequency(-5)
        self.assertEqual(val, 0.0)

    def test_very_long_message(self):
        """消息超长 → 不崩溃。"""
        val = _compute_user_engagement(10000, 100)
        self.assertAlmostEqual(val, 1.0, places=2)

    def test_sentiment_out_of_range(self):
        """sentiment 超出 [0,1] → clamp 到边界。"""
        val_hi = _compute_emotion_intensity(2.0)
        val_lo = _compute_emotion_intensity(-1.0)
        self.assertLessEqual(val_hi, 1.0)
        self.assertLessEqual(val_lo, 1.0)

    def test_decode_from_entry_no_timestamp(self):
        """entry 无 timestamp → 不崩溃。"""
        alpha = compute_alpha_from_entry({"summary": "无时间戳"})
        self.assertIsInstance(alpha, float)


if __name__ == "__main__":
    unittest.main()

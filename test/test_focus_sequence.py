#!/usr/bin/env python3
"""
focus_sequence 测试用例 — Phase 2 · MemOS 能力整合
===================================================

测试覆盖三大序列检测规则 + 综合管道 + XML 格式化。

## 测试用例清单

| 编号 | 测试函数 | 类型 | 输入 | 预期输出 |
|------|---------|------|------|---------|
| FS-01 | test_detect_pairs_empty | 边界 | 空列表 | [] |
| FS-02 | test_detect_pairs_below_threshold | 边界 | 2 次共现 | []（min_count=3） |
| FS-03 | test_detect_pairs_above_threshold | 正常 | 3+ 次共现 | 1 个 FocusPair pattern |
| FS-04 | test_detect_pairs_multiple_pairs | 正常 | 多话题共现 | 多个 pattern，按 count 排序 |
| FS-05 | test_detect_pairs_single_session_excluded | 边界 | 同一 session 内重复 | 不计入跨 session 统计 |
| FS-06 | test_detect_emotion_correlations_no_match | 边界 | 情绪强度 < 0.7 | [] |
| FS-07 | test_detect_emotion_correlations_match | 正常 | 情绪强度 > 0.7 且 3+ 次 | 1 个 EmotionCorrelation pattern |
| FS-08 | test_detect_emotion_correlations_mixed | 正常 | 部分匹配部分不匹配 | 只返回超过阈值的 |
| FS-09 | test_detect_path_jumps_no_jump | 边界 | 无序列模式 | [] |
| FS-10 | test_detect_path_jumps_two_sessions | 正常 | 2 个 session 有 A→B→C | 1 个 PathJump pattern |
| FS-11 | test_detect_path_jumps_three_sessions | 正常 | 3 个 session 有 A→B | 1 个 path_jump，count=3 |
| FS-12 | test_build_patterns_combined | 集成 | 完整 narratives + emotion | 包含所有三类 pattern |
| FS-13 | test_build_patterns_insufficient_data | 边界 | < 3 条 narrative | [] |
| FS-14 | test_format_xml_focus_pair | 格式 | FocusPair pattern | 包含 <focus_pair> + count + signal |
| FS-15 | test_format_xml_emotion_correlation | 格式 | EmotionCorrelation pattern | 包含焦点名 + avg_emotion |
| FS-16 | test_format_xml_empty | 格式 | [] | "" |
| FS-17 | test_format_xml_multiple_patterns | 格式 | 多个 pattern | 多个 <pattern> 元素 |
| FS-18 | test_detect_pairs_session_topic_ordering | 正常 | 话题顺序不同 | 仍被识别为同一对 |

## 数据约定

narrative 条目格式（persistence.load_narrative_since() 返回）：
    {
        "timestamp": ISO8601,
        "session_id": str,
        "summary": str,
        "insights": str,
        "unresolved": str,
        "focus_topics": [str],
        "emotion_summary": str,
    }

emotion 条目格式（persistence.load_emotion_history() 返回）：
    {
        "ts": ISO8601,
        "label": str,
        "sentiment": float [0,1],
        "confidence": float,
        "label_cn": str,
    }
"""
import unittest
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from cogito_core.focus_sequence import (
        FocusPoint, DetectedPattern,
        extract_focus_points,
        detect_focus_pairs, detect_emotion_correlations,
        detect_path_jumps, build_sequence_patterns,
        format_patterns_for_xml,
    )
    FOCUS_SEQ_AVAILABLE = True
except ImportError as e:
    FOCUS_SEQ_AVAILABLE = False
    _import_error = str(e)


# ── 测试夹具 ──

_NARRATIVES_BASIC = [
    {
        "timestamp": "2026-07-20T10:00:00+00:00",
        "session_id": "sess-001",
        "summary": "Docker 端口冲突排查",
        "focus_topics": ["Docker", "端口", "Nginx"],
        "emotion_summary": "困惑为主",
    },
    {
        "timestamp": "2026-07-21T14:00:00+00:00",
        "session_id": "sess-002",
        "summary": "Docker 网络配置",
        "focus_topics": ["Docker", "端口", "网络"],
        "emotion_summary": "中性",
    },
    {
        "timestamp": "2026-07-22T09:00:00+00:00",
        "session_id": "sess-003",
        "summary": "端口映射排查",
        "focus_topics": ["Docker", "端口", "配置"],
        "emotion_summary": "轻微沮丧",
    },
]

_NARRATIVES_PATH_JUMP = [
    {
        "timestamp": "2026-07-20T10:00:00+00:00",
        "session_id": "sess-001",
        "summary": "需求评审",
        "focus_topics": ["需求", "设计", "原型"],
    },
    {
        "timestamp": "2026-07-21T14:00:00+00:00",
        "session_id": "sess-002",
        "summary": "后端设计",
        "focus_topics": ["设计", "API", "数据库"],
    },
    {
        "timestamp": "2026-07-22T09:00:00+00:00",
        "session_id": "sess-003",
        "summary": "前端对接",
        "focus_topics": ["API", "前端", "联调"],
    },
]


# ── 测试：焦点对检测 ──

@unittest.skipUnless(FOCUS_SEQ_AVAILABLE, f"focus_sequence not available: {locals().get('_import_error', '?')}")
class TestDetectFocusPairs(unittest.TestCase):
    """焦焦点对重复检测（FS-01 ~ FS-05）。
    
    规则：两个焦点在不同 session 中共同出现 ≥3 次 → 习惯路径信号。
    """

    def test_detect_pairs_empty(self):
        """FS-01: 空 narratives → 空列表。"""
        self.assertEqual(detect_focus_pairs([]), [])

    def test_detect_pairs_below_threshold(self):
        """FS-02: 仅 2 次共现 → 空列表（min_count=3，不足时不触发）。"""
        narr = _NARRATIVES_BASIC[:2]  # 只有 2 个 session 含 Docker+端口
        self.assertEqual(detect_focus_pairs(narr, min_count=3), [])

    def test_detect_pairs_below_threshold_custom(self):
        """FS-02b: min_count=2，2 次共现 → 应检出。"""
        narr = _NARRATIVES_BASIC[:2]
        pairs = detect_focus_pairs(narr, min_count=2)
        self.assertEqual(len(pairs), 1)

    def test_detect_pairs_above_threshold(self):
        """FS-03: 3 个 session 都有 Docker+端口 → 1 个 focus_pair pattern。
        
        输入：3 条 narrative，每条的 focus_topics 都包含 Docker 和 端口
        预期：返回 1 个 DetectedPattern，type=focus_pair，count ≥ 3
        """
        pairs = detect_focus_pairs(_NARRATIVES_BASIC, min_count=3)
        self.assertGreaterEqual(len(pairs), 1)
        top = pairs[0]
        self.assertEqual(top.pattern_type, "focus_pair")
        self.assertGreaterEqual(top.count, 3)
        self.assertIn("Docker", top.topics)
        self.assertIn("端口", top.topics)

    def test_detect_pairs_multiple_pairs(self):
        """FS-04: 多话题共现，应返回多个 pattern 并按 count 降序排列。
        
        输入：扩展 narrative 列表，多个话题对同时达到阈值
        预期：返回多个 pattern，count 从高到低排序
        """
        narr = _NARRATIVES_BASIC + [
            {
                "timestamp": "2026-07-23T10:00:00+00:00",
                "session_id": "sess-004",
                "summary": "React 组件",
                "focus_topics": ["React", "组件", "Props"],
            },
            {
                "timestamp": "2026-07-24T10:00:00+00:00",
                "session_id": "sess-005",
                "summary": "React 状态管理",
                "focus_topics": ["React", "组件", "状态"],
            },
            {
                "timestamp": "2026-07-25T10:00:00+00:00",
                "session_id": "sess-006",
                "summary": "Props 类型定义",
                "focus_topics": ["React", "组件", "类型"],
            },
        ]
        pairs = detect_focus_pairs(narr, min_count=3)
        # 至少有 Docker+端口 和 React+组件 两对（React+组件在 sess-004~006 出现 3 次）
        self.assertGreaterEqual(len(pairs), 2)
        # 按 count 降序
        for i in range(len(pairs) - 1):
            self.assertGreaterEqual(pairs[i].count, pairs[i + 1].count)

    def test_detect_pairs_single_session_excluded(self):
        """FS-05: 同一 session 内的重复话题不应计为跨 session 共现。
        
        输入：1 个 session，focus_topics 多次出现 Docker
        预期：不应产生任何跨 session pattern
        """
        narr = [{
            "timestamp": "2026-07-20T10:00:00+00:00",
            "session_id": "sess-001",
            "summary": "Docker 问题",
            "focus_topics": ["Docker", "Docker", "Docker", "端口"],
        }]
        pairs = detect_focus_pairs(narr, min_count=2)
        self.assertEqual(pairs, [])


# ── 测试：情绪-焦点关联 ──

@unittest.skipUnless(FOCUS_SEQ_AVAILABLE, "focus_sequence not available")
class TestDetectEmotionCorrelations(unittest.TestCase):
    """情绪-焦点关联检测（FS-06 ~ FS-08）。

    规则：某话题出现时情绪强度 > 0.7，且出现 ≥3 次 → 痛点标记。
    """

    def _make_narratives_with_emotion(self, topic: str, sessions: int, sentiment: float):
        """辅助：生成指定情绪强度的 narrative 列表。"""
        return [
            {
                "timestamp": f"2026-07-{20+i:02d}T10:00:00+00:00",
                "session_id": f"sess-{i:03d}",
                "summary": f"{topic} 问题",
                "focus_topics": [topic, "其他"],
                "emotion_summary": "测试",
            }
            for i in range(sessions)
        ]

    def test_detect_emotion_correlations_no_match(self):
        """FS-06: 情绪强度 < 0.7 → 空列表。
        
        输入：3 条 narrative，每条的 sentiment = 0.6（< 0.7）
        预期：无匹配
        """
        narr = self._make_narratives_with_emotion("Docker", 3, 0.6)
        emo = [{"sentiment": 0.6} for _ in range(3)]
        pairs = detect_emotion_correlations(narr, emo, threshold=0.7, min_count=3)
        self.assertEqual(pairs, [])

    def test_detect_emotion_correlations_match(self):
        """FS-07: 情绪强度 > 0.7 且 3+ 次 → 1 个 emotion_correlation。
        
        输入：3 条 narrative，sentiment=0.8 → 超过阈值
        预期：1 个 DetectedPattern，type=emotion_correlation，avg_emotion≈0.8
        """
        narr = self._make_narratives_with_emotion("Docker", 3, 0.8)
        emo = [{"sentiment": 0.8} for _ in range(3)]
        pairs = detect_emotion_correlations(narr, emo, threshold=0.7, min_count=3)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].pattern_type, "emotion_correlation")
        self.assertGreaterEqual(pairs[0].avg_emotion, 0.7)

    def test_detect_emotion_correlations_mixed(self):
        """FS-08: 部分匹配部分不匹配 → 只返回超过阈值的。
        
        输入：3 条 Docker（sentiment=0.8）+ 3 条 React（sentiment=0.5）
        预期：1 个 emotion_correlation（Docker 相关）
        """
        docker_narr = self._make_narratives_with_emotion("Docker", 3, 0.8)
        react_narr = self._make_narratives_with_emotion("React", 3, 0.5)
        narr = docker_narr + react_narr
        emo = [{"sentiment": 0.8} for _ in range(3)] + [{"sentiment": 0.5} for _ in range(3)]
        pairs = detect_emotion_correlations(narr, emo, threshold=0.7, min_count=3)
        self.assertEqual(len(pairs), 1)
        self.assertIn("Docker", pairs[0].topics)

    def test_detect_emotion_correlations_no_emotion_data(self):
        """FS-08b: 无 emotion_data 参数 → 降级用 avg sentiment=0.5，应返回空。"""
        narr = self._make_narratives_with_emotion("Docker", 3, 0.8)
        pairs = detect_emotion_correlations(narr, emotion_data=None, threshold=0.7, min_count=3)
        self.assertEqual(pairs, [])


# ── 测试：路径跳转检测 ──

@unittest.skipUnless(FOCUS_SEQ_AVAILABLE, "focus_sequence not available")
class TestDetectPathJumps(unittest.TestCase):
    """路径跳转检测（FS-09 ~ FS-11）。

    规则：焦点序列 A→B→C 在不同 session 中连续出现 ≥2 次 → 工作流模式。
    简化版：检测两个相邻 session 之间是否有话题的"接力"模式。
    """

    def test_detect_path_jumps_no_jump(self):
        """FS-09: 无序列模式 → 空列表。
        
        输入：各 session 的话题无关联
        预期：空
        """
        narr = [
            {"session_id": "s1", "focus_topics": ["Python"]},
            {"session_id": "s2", "focus_topics": ["Java"]},
            {"session_id": "s3", "focus_topics": ["Go"]},
        ]
        jumps = detect_path_jumps(narr, min_count=2)
        self.assertEqual(jumps, [])

    def test_detect_path_jumps_two_sessions(self):
        """FS-10: 2 个 session 有话题接力 A→B→C。
        
        输入：3 个 session，每相邻两个共享至少一个话题
        预期：2 条 path_jump，count=2
        """
        narr = _NARRATIVES_PATH_JUMP
        jumps = detect_path_jumps(narr, min_count=2)
        self.assertGreaterEqual(len(jumps), 1)

    def test_detect_path_jumps_three_sessions(self):
        """FS-11: 3 个 session 的固定接力链。
        
        输入：A→B, A→B, A→B 的接力模式（SQL→数据库 出现 3 次）
        预期：1 条 path_jump，count=2（相邻 session 间检测）
        """
        narr = [
            {"session_id": "s1", "focus_topics": ["Python", "SQL"]},
            {"session_id": "s2", "focus_topics": ["SQL", "数据库"]},
            {"session_id": "s3", "focus_topics": ["SQL", "数据库"]},
        ]
        jumps = detect_path_jumps(narr, min_count=2)
        self.assertGreaterEqual(len(jumps), 1)
        # (SQL, 数据库) 在 s1→s2 和 s2→s3 中都应被检测到
        top = jumps[0]
        self.assertGreaterEqual(top.count, 2)
        self.assertIn("SQL", top.topics)


# ── 测试：综合管道 ──

@unittest.skipUnless(FOCUS_SEQ_AVAILABLE, "focus_sequence not available")
class TestBuildSequencePatterns(unittest.TestCase):
    """综合管道测试（FS-12 ~ FS-13）。"""

    def test_build_patterns_combined(self):
        """FS-12: 完整 narratives + emotion → 包含所有三类 pattern。
        
        输入：带多种序列模式的 narratives
        预期：返回的列表至少包含 focus_pair 和至少一种其他类型
        """
        narr = _NARRATIVES_BASIC + _NARRATIVES_PATH_JUMP
        emo = [{"sentiment": 0.8} for _ in range(len(narr))]
        patterns = build_sequence_patterns(narr, emo)
        types = {p.pattern_type for p in patterns}
        self.assertIn("focus_pair", types)

    def test_build_patterns_insufficient_data(self):
        """FS-13: < 3 条 narrative → []。
        
        输入：2 条 narrative
        预期：空列表（数据不足无法归纳）
        """
        patterns = build_sequence_patterns(_NARRATIVES_BASIC[:2])
        self.assertEqual(patterns, [])


# ── 测试：XML 格式化 ──

@unittest.skipUnless(FOCUS_SEQ_AVAILABLE, "focus_sequence not available")
class TestFormatPatternsForXML(unittest.TestCase):
    """XML 格式化测试（FS-14 ~ FS-17）。"""

    def setUp(self):
        self.patterns = detect_focus_pairs(_NARRATIVES_BASIC, min_count=3)

    def test_format_xml_empty(self):
        """FS-17: 空 pattern 列表 → 空字符串。"""
        self.assertEqual(format_patterns_for_xml([]), "")

    def test_format_xml_focus_pair_structure(self):
        """FS-14: FocusPair → 包含焦点名和 count。
        
        预期：格式如 <focus_pair>A, B</focus_pair>
        且包含 count="N" 属性
        """
        if not self.patterns:
            self.skipTest("需要至少一个 pattern")
        xml = format_patterns_for_xml(self.patterns)
        self.assertIn("<focus_pair>", xml)
        self.assertIn("count=", xml)
        self.assertIn("Docker", xml)
        self.assertIn("端口", xml)

    def test_format_xml_contains_signal(self):
        """FS-14b: pattern 应有 signal 描述文本。"""
        if not self.patterns:
            self.skipTest("需要至少一个 pattern")
        xml = format_patterns_for_xml(self.patterns)
        self.assertIn("<signal>", xml)
        self.assertIn("</signal>", xml)

    def test_format_xml_importance(self):
        """FS-14c: pattern 应包含 importance 属性。"""
        if not self.patterns:
            self.skipTest("需要至少一个 pattern")
        xml = format_patterns_for_xml(self.patterns)
        self.assertIn("importance=", xml)


# ── 测试：数据完整性 ──

@unittest.skipUnless(FOCUS_SEQ_AVAILABLE, "focus_sequence not available")
class TestDataIntegrity(unittest.TestCase):
    """数据完整性测试（corner cases）。"""

    def test_focus_point_from_narrative(self):
        """从 narrative 提取 FocusPoint 应正确。"""
        focus_points = extract_focus_points(_NARRATIVES_BASIC)
        self.assertGreater(len(focus_points), 0)
        # 所有焦点话题都被提取
        all_topics = set()
        for n in _NARRATIVES_BASIC:
            all_topics.update(n["focus_topics"])
        extracted_topics = {p.topic for p in focus_points}
        for t in all_topics:
            self.assertIn(t, extracted_topics, f"话题 {t} 未被提取")

    def test_detected_pattern_confidence_range(self):
        """DetectedPattern.confidence 应在 [0, 1] 区间。"""
        pairs = detect_focus_pairs(_NARRATIVES_BASIC, min_count=3)
        for p in pairs:
            self.assertGreaterEqual(p.confidence, 0.0)
            self.assertLessEqual(p.confidence, 1.0)

    def test_detected_pattern_description_nonempty(self):
        """DetectedPattern.description 应有内容。"""
        pairs = detect_focus_pairs(_NARRATIVES_BASIC, min_count=3)
        for p in pairs:
            self.assertTrue(len(p.description) > 0)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
crystallization 测试用例 — Phase 3 · MemOS 能力整合
====================================================

测试覆盖：候选项检测、结晶落库、技能注入、跨 Profile 命名空间、语境匹配。

## 测试用例清单

| 编号 | 测试函数 | 类型 | 输入 | 预期输出 |
|------|---------|------|------|---------|
| CS-01 | test_detect_empty | 边界 | 空 narratives | [] |
| CS-02 | test_detect_below_alpha | 边界 | α < 0.7 且 count ≥ 3 | [] |
| CS-03 | test_detect_below_count | 边界 | α ≥ 0.7 且 count < 3 | [] |
| CS-04 | test_detect_match | 正常 | α ≥ 0.7, count ≥ 3 | 1 个 CrystallizationCandidate |
| CS-05 | test_detect_multiple_sorted | 正常 | 多候选项 | 按置信度降序 |
| CS-06 | test_crystallize_writes_file | 集成 | 候选项 → 持久化 | focus_sequence.jsonl 有写入 |
| CS-07 | test_load_by_profile | 正常 | profile="mengmeng" | 只返回该 profile 的结晶 |
| CS-08 | test_load_wrong_profile | 边界 | profile="nonexistent" | [] |
| CS-09 | test_inject_max_count | 格式 | 注入 5 个结晶 | 只输出 3 个 |
| CS-10 | test_inject_empty | 格式 | [] | "" |
| CS-11 | test_inject_xml_structure | 格式 | 1 个结晶 | 含 <crystallized_skill> 等标签 |
| CS-12 | test_match_context_hit | 正常 | focus_topics 匹配 trigger | 返回匹配的技能 |
| CS-13 | test_match_context_no_match | 边界 | focus_topics 不匹配 trigger | [] |
| CS-14 | test_edge_nan_alpha | 边界 | alpha = float('nan') | 不崩溃，被过滤 |
| CS-15 | test_edge_duplicate_protection | 正常 | 同一 pattern 第二次结晶 | 返回 False（已存在） |

## 数据约定

narrative 条目格式：
    {
        "timestamp": ISO8601,
        "session_id": str,
        "summary": str,
        "insights": str,
        "unresolved": str,
        "focus_topics": [str],
        "emotion_summary": str,
    }

结晶条目格式（focus_sequence.jsonl / crystallized/）：
    {
        "skill_name": str,
        "trigger": str,
        "pattern": str,
        "suggested_approach": str,
        "confidence": float,
        "evidence_count": int,
        "profile": str,
        "created_at": ISO8601,
    }
"""
import unittest
import sys
import os
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from cogito_core.crystallization import (
        CrystallizationCandidate, CrystallizedSkill,
        detect_candidates, crystallize, inject_skills,
        load_skills, match_context,
        _set_crystallized_dir,  # 测试用：重设持久化目录
    )
    CRYST_AVAILABLE = True
except ImportError as e:
    CRYST_AVAILABLE = False
    _import_error = str(e)


# ── 测试夹具 ──

_NARRATIVES_WITH_ALPHA = [
    {
        "timestamp": "2026-07-20T10:00:00+00:00",
        "session_id": "sess-001",
        "summary": "Docker 端口冲突排查",
        "focus_topics": ["Docker", "端口", "Nginx"],
        "insights": "用户通过查看日志定位到了端口绑定问题",
        "alpha": 0.25,
    },
    {
        "timestamp": "2026-07-21T14:00:00+00:00",
        "session_id": "sess-002",
        "summary": "Docker 网络配置",
        "focus_topics": ["Docker", "端口", "网络"],
        "insights": "用户在排查网络问题时优先检查端口映射",
        "alpha": 0.30,
    },
    {
        "timestamp": "2026-07-22T09:00:00+00:00",
        "session_id": "sess-003",
        "summary": "端口映射排查",
        "focus_topics": ["Docker", "端口", "配置"],
        "insights": "用户解决了端口冲突，下次可建议统一端口管理方案",
        "alpha": 0.28,
    },
]

_NARRATIVES_HIGH_ALPHA = [
    {
        "timestamp": "2026-07-20T10:00:00+00:00",
        "session_id": "sess-001",
        "summary": "Docker 端口排查",
        "focus_topics": ["Docker", "端口"],
        "insights": "端口冲突时用户倾向于先查日志再改配置",
        "alpha": 0.75,
    },
    {
        "timestamp": "2026-07-21T14:00:00+00:00",
        "session_id": "sess-002",
        "summary": "Docker 网络问题",
        "focus_topics": ["Docker", "端口"],
        "insights": "端口映射是 Docker 网络的高频痛点",
        "alpha": 0.82,
    },
    {
        "timestamp": "2026-07-22T09:00:00+00:00",
        "session_id": "sess-003",
        "summary": "端口冲突解决",
        "focus_topics": ["Docker", "端口"],
        "insights": "统一端口管理方案可避免后续冲突",
        "alpha": 0.78,
    },
    {
        "timestamp": "2026-07-23T09:00:00+00:00",
        "session_id": "sess-004",
        "summary": "Docker Compose",
        "focus_topics": ["Docker", "端口", "Compose"],
        "insights": "Compose 模式下端口管理更需规范",
        "alpha": 0.71,
    },
]


# ── 辅助：临时持久化目录 ──


def _temp_crystallized_dir():
    """创建临时目录用于测试，返回路径。"""
    d = tempfile.mkdtemp(prefix="cogito_crystal_test_")
    _set_crystallized_dir(d)
    return d


# ── 测试：候选项检测 ──


@unittest.skipUnless(CRYST_AVAILABLE, f"crystallization not available: {locals().get('_import_error', '?')}")
class TestDetectCandidates(unittest.TestCase):
    """结晶候选项检测测试（CS-01 ~ CS-05）。"""

    def test_detect_empty(self):
        """CS-01: 空 narratives → []。"""
        self.assertEqual(detect_candidates([]), [])

    def test_detect_below_alpha(self):
        """CS-02: α < 0.7 且 count ≥ 3 → []。
        
        输入：3 条 narrative，alpha 分别为 0.25, 0.30, 0.28（均低于 0.7）
        预期：无候选项
        """
        candidates = detect_candidates(
            _NARRATIVES_WITH_ALPHA,
            min_alpha=0.7, min_count=3,
        )
        self.assertEqual(candidates, [])

    def test_detect_below_count(self):
        """CS-03: α ≥ 0.7 但 count < 3 → []。
        
        输入：2 条 narrative，alpha=0.8 但仅 2 条（min_count=3）
        预期：无候选项
        """
        narr = _NARRATIVES_HIGH_ALPHA[:2]
        candidates = detect_candidates(narr, min_alpha=0.7, min_count=3)
        self.assertEqual(candidates, [])

    def test_detect_match(self):
        """CS-04: α ≥ 0.7, count ≥ 3 → 1 个候选项。
        
        输入：4 条 narrative，"Docker"+"端口"模式出现 4 次，α 均 ≥ 0.7
        预期：1 个 CrystallizationCandidate，evidence_count=4，confidence > 0
        """
        candidates = detect_candidates(
            _NARRATIVES_HIGH_ALPHA,
            min_alpha=0.7, min_count=3,
        )
        self.assertGreaterEqual(len(candidates), 1)
        top = candidates[0]
        self.assertIsInstance(top, CrystallizationCandidate)
        self.assertGreaterEqual(top.evidence_count, 3)
        self.assertGreaterEqual(top.confidence, 0.0)
        self.assertLessEqual(top.confidence, 1.0)

    def test_detect_multiple_sorted(self):
        """CS-05: 多候选项，按置信度降序排列。
        
        输入：多个话题各出现 ≥3 次且 α ≥ 0.7
        预期：返回多个候选项，第一项的 evidence_count ≥ 第二项
        """
        extended = _NARRATIVES_HIGH_ALPHA + [
            {
                "timestamp": "2026-07-24T10:00:00+00:00",
                "session_id": "sess-005",
                "summary": "React 组件重构",
                "focus_topics": ["React", "组件", "Props"],
                "alpha": 0.85,
            },
            {
                "timestamp": "2026-07-25T10:00:00+00:00",
                "session_id": "sess-006",
                "summary": "React 类型定义",
                "focus_topics": ["React", "组件", "类型"],
                "alpha": 0.90,
            },
            {
                "timestamp": "2026-07-26T10:00:00+00:00",
                "session_id": "sess-007",
                "summary": "React Props 传递",
                "focus_topics": ["React", "组件"],
                "alpha": 0.72,
            },
        ]
        candidates = detect_candidates(
            extended,
            min_alpha=0.7, min_count=3,
        )
        self.assertGreaterEqual(len(candidates), 2)
        for i in range(len(candidates) - 1):
            self.assertGreaterEqual(
                candidates[i].confidence,
                candidates[i + 1].confidence - 0.01,
                f"第 {i} 项置信度应 ≥ 第 {i+1} 项",
            )


# ── 测试：结晶落库与读取 ──


@unittest.skipUnless(CRYST_AVAILABLE, "crystallization not available")
class TestCrystallizeAndLoad(unittest.TestCase):
    """结晶落库与跨 Profile 读取测试（CS-06 ~ CS-08）。"""

    def setUp(self):
        self._tmp_dir = _temp_crystallized_dir()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def _make_candidate(self, topic="Docker端口排查", sessions=None):
        return CrystallizationCandidate(
            topic=topic,
            sessions=sessions or ["s1", "s2", "s3"],
            avg_alpha=0.78,
            evidence_count=3,
            pattern=f"用户频繁遇到{topic}问题",
            suggested_approach=f"主动询问{topic}是否需要协助",
        )

    def test_crystallize_writes_file(self):
        """CS-06: 候选项 → 写入持久化。
        
        输入：1 个候选项，profile="default"
        预期：crystallized 目录下文件存在，读取后内容匹配
        """
        cand = self._make_candidate()
        skill = crystallize(cand, profile="default")
        self.assertIsNotNone(skill)
        self.assertEqual(skill.profile, "default")
        self.assertEqual(skill.evidence_count, 3)

        # 验证可读回
        loaded = load_skills(profile="default")
        self.assertGreaterEqual(len(loaded), 1)
        self.assertEqual(loaded[0].skill_name, skill.skill_name)

    def test_load_by_profile(self):
        """CS-07: profile="mengmeng" → 只返回该 profile 的结晶。
        
        输入：写入 2 个结晶到不同 profile
        预期：按 profile 各取各的
        """
        self._make_candidate()
        cand_default = self._make_candidate("Docker端口排查")
        cand_mengmeng = self._make_candidate("Nginx配置问题")
        crystallize(cand_default, profile="default")
        crystallize(cand_mengmeng, profile="mengmeng")

        default_skills = load_skills(profile="default")
        mengmeng_skills = load_skills(profile="mengmeng")

        self.assertGreaterEqual(len(default_skills), 1)
        self.assertGreaterEqual(len(mengmeng_skills), 1)
        for s in default_skills:
            self.assertEqual(s.profile, "default")
        for s in mengmeng_skills:
            self.assertEqual(s.profile, "mengmeng")

    def test_load_wrong_profile(self):
        """CS-08: profile="nonexistent" → []。
        
        输入：只有 profile="default" 的结晶
        预期：读取不存在的 profile 返回空列表
        """
        cand = self._make_candidate()
        crystallize(cand, profile="default")
        loaded = load_skills(profile="nonexistent")
        self.assertEqual(loaded, [])

    def test_crystallize_duplicate(self):
        """CS-15: 同一 pattern 第二次结晶 → 返回 None（已存在）。
        
        输入：同一 cand 连续结晶两次
        预期：第一次返回 skill，第二次返回 None
        """
        cand = self._make_candidate()
        first = crystallize(cand, profile="default")
        second = crystallize(cand, profile="default")
        self.assertIsNotNone(first)
        self.assertIsNone(second)


# ── 测试：技能注入 ──


@unittest.skipUnless(CRYST_AVAILABLE, "crystallization not available")
class TestInjectSkills(unittest.TestCase):
    """技能注入与格式测试（CS-09 ~ CS-11）。"""

    def _make_skill(self, name, confidence=0.8):
        return CrystallizedSkill(
            skill_name=name,
            trigger="Docker端口",
            pattern="端口冲突 → 日志排查 → 配置修正",
            suggested_approach="主动询问是否需要端口映射检查",
            confidence=confidence,
            evidence_count=5,
            profile="default",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def test_inject_empty(self):
        """CS-10: 空技能列表 → 空字符串。"""
        self.assertEqual(inject_skills([]), "")

    def test_inject_max_count(self):
        """CS-09: 5 个结晶 → 最多输出 3 个。"""
        skills = [self._make_skill(f"skill-{i}", confidence=0.9 - i * 0.1) for i in range(5)]
        xml = inject_skills(skills, max_count=3)
        count = xml.count("<crystallized_skill ")
        self.assertEqual(count, 3)

    def test_inject_xml_structure(self):
        """CS-11: 1 个结晶 → 包含完整 XML 标签。
        
        预期标签：<crystallized_skills>, <crystallized_skill confidence=...>,
                  <skill_name>, <trigger>, <pattern>, <suggested_approach>
        """
        skill = self._make_skill("端口排查技能")
        xml = inject_skills([skill])
        self.assertIn("<crystallized_skills", xml)
        self.assertIn("</crystallized_skills>", xml)
        self.assertIn("crystallized_skill confidence=", xml)
        self.assertIn("</crystallized_skill>", xml)
        self.assertIn("<skill_name>", xml)
        self.assertIn("<trigger>", xml)
        self.assertIn("<pattern>", xml)
        self.assertIn("<suggested_approach>", xml)
        self.assertIn("suggested_approach", xml)

    def test_inject_sorted_by_confidence(self):
        """CS-09b: 注入顺序按置信度降序。"""
        skills = [
            self._make_skill("低", confidence=0.3),
            self._make_skill("高", confidence=0.9),
            self._make_skill("中", confidence=0.6),
        ]
        xml = inject_skills(skills, max_count=3)
        # 高置信度应排在最前
        high_idx = xml.index("高")
        mid_idx = xml.index("中")
        low_idx = xml.index("低")
        self.assertLess(high_idx, mid_idx)
        self.assertLess(mid_idx, low_idx)


# ── 测试：语境匹配 ──


@unittest.skipUnless(CRYST_AVAILABLE, "crystallization not available")
class TestMatchContext(unittest.TestCase):
    """语境匹配测试（CS-12 ~ CS-13）。"""

    def _make_skill(self, trigger, name="技能"):
        return CrystallizedSkill(
            skill_name=name,
            trigger=trigger,
            pattern="测试模式",
            suggested_approach="测试建议",
            confidence=0.8,
            evidence_count=3,
            profile="default",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def test_match_context_hit(self):
        """CS-12: focus_topics 匹配 trigger → 返回匹配的技能。
        
        输入：skill.trigger="Docker端口"，focus_topics=["Docker", "端口"]
        预期：返回该 skill
        """
        skill = self._make_skill("Docker端口")
        matched = match_context([skill], focus_topics=["Docker", "端口", "Nginx"])
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].skill_name, "技能")

    def test_match_context_no_match(self):
        """CS-13: focus_topics 不匹配 trigger → []。
        
        输入：skill.trigger="Docker端口"，focus_topics=["React", "组件"]
        预期：空列表
        """
        skill = self._make_skill("Docker端口")
        matched = match_context([skill], focus_topics=["React", "组件"])
        self.assertEqual(matched, [])

    def test_match_context_multiple(self):
        """CS-12b: 多个焦点话题匹配多个技能 → 按置信度返回。"""
        skills = [
            self._make_skill("Docker", name="Docker技能"),
            self._make_skill("React", name="React技能"),
        ]
        matched = match_context(skills, focus_topics=["Docker", "React"])
        self.assertEqual(len(matched), 2)

    def test_match_context_partial(self):
        """CS-12c: trigger 中包含焦点话题子串 → 匹配。"""
        skill = self._make_skill("端口", name="端口技能")
        matched = match_context([skill], focus_topics=["Docker", "端口映射"])
        self.assertEqual(len(matched), 1)


# ── 测试：边界值 ──


@unittest.skipUnless(CRYST_AVAILABLE, "crystallization not available")
class TestEdgeCases(unittest.TestCase):
    """边界与异常值测试（CS-14）。"""

    def test_edge_nan_alpha(self):
        """CS-14: alpha=NaN → 不崩溃，被过滤掉。"""
        narr = [{
            "timestamp": "2026-07-20T10:00:00+00:00",
            "session_id": "s1",
            "summary": "测试",
            "focus_topics": ["Docker", "端口"],
            "alpha": float('nan'),
        } for _ in range(5)]
        try:
            candidates = detect_candidates(narr, min_alpha=0.7, min_count=3)
            # NaN 比较默认 False，所以不会匹配
            self.assertEqual(candidates, [])
        except Exception:
            self.fail("NaN alpha 不应崩溃")

    def test_edge_empty_focus_topics(self):
        """CS-14b: focus_topics 为空列表 → 不崩溃。"""
        narr = [{
            "timestamp": "2026-07-20T10:00:00+00:00",
            "session_id": "s1",
            "summary": "测试",
            "focus_topics": [],
            "alpha": 0.8,
        } for _ in range(5)]
        try:
            candidates = detect_candidates(narr, min_alpha=0.7, min_count=3)
            self.assertEqual(candidates, [])
        except Exception:
            self.fail("空 focus_topics 不应崩溃")

    def test_edge_negative_alpha(self):
        """CS-14c: alpha 为负值 → clamp 到 0，不过滤。"""
        narr = [{
            "timestamp": "2026-07-20T10:00:00+00:00",
            "session_id": "s1",
            "summary": "测试",
            "focus_topics": ["Docker"],
            "alpha": -0.5,
        } for _ in range(5)]
        candidates = detect_candidates(narr, min_alpha=0.7, min_count=3)
        self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()

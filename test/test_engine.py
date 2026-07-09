#!/usr/bin/env python3
"""
Unit tests for cogito_core.engine
=================================
Tests process() and end_session() with XML-format validation.
"""

import unittest
import sys
import os
import re
import io
from unittest.mock import patch

# Allow importing cogito_core even when running from test/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# We import conditionally because cogito_core may not exist yet in CI
try:
    from cogito_core.engine import ConsciousnessEngine
    ENGINE_AVAILABLE = True
except ImportError:
    ENGINE_AVAILABLE = False


# ── XML helpers ────────────────────────────────────────────────────────────

def _has_xml_structure(text: str) -> bool:
    """Check that text contains valid-looking XML with expected tags."""
    return bool(re.search(r"<\w+[^>]*>.*?</\w+>", text, re.DOTALL))


def _tag_present(text: str, tag: str) -> bool:
    """Return True if <tag> or <tag attr=...> appears in text."""
    return bool(re.search(rf"<{tag}[\s>]", text))


# ── Tests ──────────────────────────────────────────────────────────────────

@unittest.skipUnless(ENGINE_AVAILABLE, "cogito_core not available")
class TestConsciousnessEngine(unittest.TestCase):
    """Test the core ConsciousnessEngine methods."""

    def setUp(self):
        self.engine = ConsciousnessEngine()

    def test_process_returns_string(self):
        """process() should return a non-empty string."""
        result = self.engine.process("你好，请帮我分析这段代码")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result.strip()), 0)

    def test_process_contains_xml(self):
        """process() output should contain XML-structured content."""
        result = self.engine.process("refactor this function")
        self.assertTrue(
            _has_xml_structure(result),
            f"Expected XML in output, got: {result[:200]}",
        )

    def test_process_preserves_identity_tags(self):
        """Output should include consciousness identity tags like <cogito>, <thought> etc."""
        result = self.engine.process("hello")
        tags_to_check = ["cogito", "thought"]
        for tag in tags_to_check:
            self.assertTrue(
                _tag_present(result, tag),
                f"Expected <{tag}> in output, got: {result[:300]}",
            )

    def test_process_with_chinese_input(self):
        """Chinese input should be handled correctly."""
        result = self.engine.process("我今天心情很好")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)

    def test_process_with_empty_input(self):
        """Empty input should not crash."""
        result = self.engine.process("")
        self.assertIsInstance(result, str)

    def test_end_session_returns_xml(self):
        """end_session() should return XML summary."""
        result = self.engine.end_session()
        self.assertIsInstance(result, str)
        self.assertTrue(
            _has_xml_structure(result),
            f"end_session() output should be XML, got: {result[:200]}",
        )

    def test_end_session_contains_summary_tag(self):
        """end_session() XML should include a summary tag."""
        result = self.engine.end_session()
        self.assertTrue(
            _tag_present(result, "summary"),
            f"Expected <summary> in end_session output, got: {result[:200]}",
        )

    def test_multiple_process_calls(self):
        """Multiple process() calls should each return valid XML."""
        prompts = [
            "What is the meaning of consciousness?",
            "帮我写一个排序算法",
            "Refactor this class",
        ]
        for prompt in prompts:
            result = self.engine.process(prompt)
            self.assertTrue(_has_xml_structure(result), f"Missing XML for: {prompt}")


@unittest.skipUnless(ENGINE_AVAILABLE, "cogito_core not available")
class TestEngineState(unittest.TestCase):
    """Test engine state management."""

    def setUp(self):
        self.engine = ConsciousnessEngine()

    def test_session_id_persistence(self):
        """Session ID should be consistent across calls."""
        sid1 = getattr(self.engine, "session_id", None)
        self.engine.process("test 1")
        sid2 = getattr(self.engine, "session_id", None)
        self.engine.process("test 2")
        sid3 = getattr(self.engine, "session_id", None)
        self.assertEqual(sid1, sid2)
        self.assertEqual(sid2, sid3)

    def test_turn_counter_increments(self):
        """Turn counter should increment with each process() call."""
        initial = getattr(self.engine, "turn_count", None)
        self.engine.process("turn 1")
        after_one = getattr(self.engine, "turn_count", None)
        self.engine.process("turn 2")
        after_two = getattr(self.engine, "turn_count", None)

        if initial is not None and after_one is not None:
            self.assertGreaterEqual(after_one, initial)
        if after_one is not None and after_two is not None:
            self.assertGreaterEqual(after_two, after_one)


class TestXMLFormatValidation(unittest.TestCase):
    """Tests that don't require the actual engine – pure format validation."""

    def test_valid_cogito_xml(self):
        """A hand-crafted valid XML should pass all format checks."""
        valid = """<cogito>
  <thought>Analyzing user request</thought>
  <action type="reasoning">Working on it</action>
  <reflection>Self-checking</reflection>
</cogito>"""
        self.assertTrue(_has_xml_structure(valid))
        self.assertTrue(_tag_present(valid, "cogito"))
        self.assertTrue(_tag_present(valid, "thought"))

    def test_invalid_flat_string(self):
        """Plain text without XML should fail XML checks."""
        plain = "Just a normal response"
        self.assertFalse(_has_xml_structure(plain))

    def test_missing_required_tags(self):
        """XML without required tags should be detectable."""
        partial_xml = "<cogito><other>stuff</other></cogito>"
        self.assertTrue(_has_xml_structure(partial_xml))
        self.assertFalse(_tag_present(partial_xml, "thought"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

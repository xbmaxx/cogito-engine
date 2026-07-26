#!/usr/bin/env python3
"""
Unit tests for cogito_core.engine (v1.6+ API)
=============================================
Tests CogitoEngine.process() and end_session() with current API.
"""
import unittest
import sys
import os
import re
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from cogito_core.engine import CogitoEngine, EngineState
    ENGINE_AVAILABLE = True
except ImportError:
    ENGINE_AVAILABLE = False


# ── Helpers ─────────────────────────────────────────────────────────────────

def _run_first_turn(engine, text: str) -> str:
    """Run a first-turn process() and return XML."""
    state = EngineState(session_id="test")
    xml, _ = engine.process(
        [{"role": "user", "content": text}], state
    )
    return xml


# ── Tests ───────────────────────────────────────────────────────────────────

@unittest.skipUnless(ENGINE_AVAILABLE, "cogito_core not available")
class TestCogitoEngine(unittest.TestCase):
    """Test CogitoEngine process() and end_session() with current API."""

    def setUp(self):
        self.engine = CogitoEngine(
            include_weather=False,
            include_battery=False,
            include_emotion=True,
            include_narrative=True,
        )
        self.state = EngineState(session_id="test-engine")

    # ── process() ──

    def test_process_returns_xml(self):
        """process() 返回 (xml_str, state) 元组，xml 非空。"""
        xml, st = self.engine.process(
            [{"role": "user", "content": "你好"}], self.state
        )
        self.assertIsInstance(xml, str)
        self.assertGreater(len(xml.strip()), 0)
        self.assertIsInstance(st, EngineState)

    def test_process_contains_consciousness_tag(self):
        """process() 输出包含 <consciousness> 标签。"""
        xml = _run_first_turn(self.engine, "test message")
        self.assertIn("<consciousness>", xml)
        self.assertIn("</consciousness>", xml)

    def test_process_with_chinese_input(self):
        """中文输入正常处理。"""
        xml = _run_first_turn(self.engine, "我今天心情很好")
        self.assertIsInstance(xml, str)
        self.assertIn("<consciousness>", xml)

    def test_process_with_empty_messages(self):
        """空消息列表不崩溃。"""
        try:
            xml, _ = self.engine.process([], self.state)
            self.assertIsInstance(xml, str)
        except Exception as exc:
            self.fail(f"空消息不应崩溃: {exc}")

    def test_process_with_malformed_message(self):
        """畸形消息不崩溃。"""
        try:
            xml, _ = self.engine.process(
                [{"role": "unknown", "no_content": 123}], self.state
            )
            self.assertIsInstance(xml, str)
        except Exception as exc:
            self.fail(f"畸形消息不应崩溃: {exc}")

    def test_process_contains_immediate_layer(self):
        """process() 输出包含 <immediate> 层（时间/心跳/焦点）。"""
        xml = _run_first_turn(self.engine, "Docker端口配置")
        self.assertTrue(
            "<immediate>" in xml and "</immediate>" in xml,
            f"缺少 <immediate> 层: {xml[:300]}",
        )

    def test_multiple_process_calls(self):
        """多次 process() 调用均不崩溃。"""
        for i, msg in enumerate([
            "Docker问题排查",
            "端口映射配置",
            "日志分析",
        ]):
            xml, self.state = self.engine.process(
                [{"role": "user", "content": msg}], self.state
            )
            self.assertIsInstance(xml, str)
            self.assertIn("<consciousness>", xml)

    # ── end_session() ──

    def test_end_session_no_crash(self):
        """end_session() 不崩溃。"""
        _run_first_turn(self.engine, "Docker端口配置")
        try:
            self.engine.end_session(
                self.state,
                [{"role": "user", "content": "Docker端口配置"}],
                focus_summary="Docker端口配置",
            )
        except Exception as exc:
            self.fail(f"end_session() 不应崩溃: {exc}")

    # ── EngineState ──

    def test_engine_state_creation(self):
        """EngineState 正确创建。"""
        state = EngineState(session_id="test-state")
        self.assertEqual(state.session_id, "test-state")
        self.assertIsNotNone(state.ticker)


@unittest.skipUnless(ENGINE_AVAILABLE, "cogito_core not available")
class TestEngineState(unittest.TestCase):
    """EngineState 状态管理。"""

    def test_state_session_id(self):
        state = EngineState(session_id="s1")
        self.assertEqual(state.session_id, "s1")

    def test_state_ticker_exists(self):
        state = EngineState(session_id="s2")
        self.assertIsNotNone(state.ticker)

    def test_state_is_first_message(self):
        state = EngineState(session_id="s3")
        self.assertTrue(state.is_first_message)

    def test_state_focus_stack(self):
        state = EngineState(session_id="s4")
        self.assertIsNotNone(state.focus_stack)


if __name__ == "__main__":
    unittest.main()

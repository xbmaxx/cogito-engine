#!/usr/bin/env python3
"""
Tests for hook_entry.py – stdin/stdout JSON protocol
=====================================================
Simulates the JSON I/O contract that hook_entry.py implements:
1. Read a JSON object from stdin
2. Process it through the engine
3. Write a JSON response to stdout
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_ENTRY = REPO_ROOT / "cogito_core" / "hook_entry.py"


# ── Helpers ────────────────────────────────────────────────────────────────

def _has_hook_entry() -> bool:
    return HOOK_ENTRY.is_file()


def _run_hook(input_json: dict, timeout: int = 5) -> dict:
    """Send *input_json* to hook_entry.py stdin; return parsed stdout JSON."""
    proc = subprocess.run(
        [sys.executable, str(HOOK_ENTRY)],
        input=json.dumps(input_json, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(REPO_ROOT),
    )
    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        raise AssertionError(
            f"hook_entry.py did not return valid JSON.\n"
            f"stdout: {stdout[:500]}\n"
            f"stderr: {stderr[:500]}\n"
            f"returncode: {proc.returncode}"
        )


# ── Tests ──────────────────────────────────────────────────────────────────

@unittest.skipUnless(_has_hook_entry(), "hook_entry.py not found")
class TestHookEntryJSONProtocol(unittest.TestCase):
    """Verify that hook_entry.py speaks the expected stdin/stdout JSON protocol."""

    def test_basic_prompt_returns_json(self):
        """A simple prompt should return a JSON object."""
        result = _run_hook({"prompt": "hello", "session_id": "test-001"})
        self.assertIsInstance(result, dict)

    def test_response_contains_expected_keys(self):
        """The response JSON should include 'response' and 'session_id'."""
        result = _run_hook({"prompt": "test prompt", "session_id": "s1"})
        self.assertIn("response", result, f"Missing 'response' key: {list(result.keys())}")
        # session_id echo or updated session_id
        self.assertTrue(
            "session_id" in result or "session" in result,
            f"Expected session key: {list(result.keys())}",
        )

    def test_response_is_not_empty(self):
        """The 'response' value should be non-empty."""
        result = _run_hook({"prompt": "hello", "session_id": "s2"})
        response = result.get("response", "")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response.strip()), 0, "Response should not be empty")

    def test_response_contains_xml(self):
        """The engine response should include XML tags from the consciousness stream."""
        result = _run_hook({"prompt": "hello world", "session_id": "s3"})
        response = result.get("response", "")
        self.assertTrue(
            "<cogito>" in response or "<cogito " in response,
            f"Response should contain <cogito> tag, got: {response[:300]}",
        )

    def test_chinese_prompt(self):
        """Chinese prompts should be handled via JSON without encoding issues."""
        result = _run_hook({"prompt": "你好，今天天气真好", "session_id": "cn-1"})
        response = result.get("response", "")
        self.assertIsInstance(response, str)
        self.assertGreater(len(response), 0)

    def test_multiple_turns_same_session(self):
        """Multiple turns with the same session_id should work."""
        sid = "multi-1"
        r1 = _run_hook({"prompt": "first", "session_id": sid})
        r2 = _run_hook({"prompt": "second", "session_id": sid})
        self.assertIn("response", r1)
        self.assertIn("response", r2)
        # Responses should differ
        self.assertNotEqual(r1.get("response"), r2.get("response"),
                            "Responses should vary between turns")

    def test_empty_prompt(self):
        """An empty prompt should not crash."""
        result = _run_hook({"prompt": "", "session_id": "empty-1"})
        self.assertIsInstance(result, dict)

    def test_missing_session_id(self):
        """Missing session_id should either work (auto-generated) or return error."""
        result = _run_hook({"prompt": "hello"})
        self.assertIsInstance(result, dict)
        # Should still have a response
        self.assertIn("response", result)

    def test_stdin_json_error_handling(self):
        """Non-JSON stdin should produce an error, not crash."""
        proc = subprocess.run(
            [sys.executable, str(HOOK_ENTRY)],
            input="not-json!!!",
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(REPO_ROOT),
        )
        # Should exit non-zero for bad input
        self.assertNotEqual(proc.returncode, 0,
                            f"Expected non-zero exit for bad JSON input, got {proc.returncode}")


class TestHookEntryCLI(unittest.TestCase):
    """Test CLI behaviour of hook_entry.py."""

    @unittest.skipUnless(_has_hook_entry(), "hook_entry.py not found")
    def test_executable_runs(self):
        """hook_entry.py should be importable / executable."""
        proc = subprocess.run(
            [sys.executable, str(HOOK_ENTRY), "--help"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(REPO_ROOT),
        )
        # May or may not have --help; the point is it doesn't crash immediately
        # If exit code is 0, good; if not, check that it didn't segfault
        self.assertIn(proc.returncode, (0, 2), f"Unexpected exit code: {proc.returncode}")


class TestJSONRoundTrip(unittest.TestCase):
    """Pure-protocol tests that don't need the real engine."""

    def test_sample_request_shape(self):
        """Verify we know what a valid request looks like."""
        request = {"prompt": "hello", "session_id": "abc-123"}
        # Round-trip through JSON should be lossless
        self.assertEqual(request, json.loads(json.dumps(request)))

    def test_sample_response_shape(self):
        """Verify we know what a valid response looks like."""
        response = {
            "response": "<cogito><thought>Processing</thought></cogito>",
            "session_id": "abc-123",
            "turn": 1,
        }
        self.assertIn("response", response)
        self.assertIn("session_id", response)


if __name__ == "__main__":
    unittest.main(verbosity=2)

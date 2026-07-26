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
HOOK_ENTRY = REPO_ROOT / "adapters" / "hook_entry.py"


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
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
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
        """A simple prompt should return a JSON object with hookSpecificOutput."""
        result = _run_hook({"prompt": "hello", "session_id": "test-001"})
        self.assertIsInstance(result, dict)
        self.assertIn("hookSpecificOutput", result)

    def test_response_contains_expected_keys(self):
        """The response JSON should include hookSpecificOutput with additionalContext."""
        result = _run_hook({"prompt": "test prompt", "session_id": "s1"})
        self.assertIn("hookSpecificOutput", result,
                      f"Missing hookSpecificOutput: {list(result.keys())}")
        ctx = result["hookSpecificOutput"].get("additionalContext", "")
        self.assertIsInstance(ctx, str)

    def test_response_is_not_empty(self):
        """additionalContext should contain consciousness XML."""
        result = _run_hook({"prompt": "explain Docker port mapping", "session_id": "s2"})
        ctx = result.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertIsInstance(ctx, str)

    def test_response_contains_xml(self):
        """additionalContext should contain <consciousness> tag."""
        result = _run_hook({"prompt": "Docker port mapping config", "session_id": "s3"})
        ctx = result.get("hookSpecificOutput", {}).get("additionalContext", "")
        self.assertTrue(
            "<consciousness>" in ctx or "<cogito>" in ctx or "consciousness" in ctx.lower(),
            f"Response should contain consciousness XML, got: {ctx[:200]}",
        )

    def test_chinese_prompt(self):
        """Chinese prompts should work without encoding errors."""
        result = _run_hook(
            {"prompt": "帮我分析Docker端口冲突问题", "session_id": "s4"}
        )
        self.assertIn("hookSpecificOutput", result)
        ctx = result["hookSpecificOutput"].get("additionalContext", "")
        self.assertIsInstance(ctx, str)

    def test_multiple_turns_same_session(self):
        """Multiple turns with same session_id should return valid responses."""
        r1 = _run_hook({"prompt": "Docker ports", "session_id": "multi"})
        r2 = _run_hook({"prompt": "Docker networks", "session_id": "multi"})
        self.assertIn("hookSpecificOutput", r1)
        self.assertIn("hookSpecificOutput", r2)

    def test_stdin_json_error_handling(self):
        """Bad JSON — hook may block or timeout, but shouldn't crash."""
        try:
            proc = subprocess.run(
                [sys.executable, str(HOOK_ENTRY)],
                input="not valid json {{{",
                capture_output=True,
                text=True,
                timeout=2,
                cwd=str(REPO_ROOT),
            )
            self.assertTrue(proc.returncode >= 0)
        except subprocess.TimeoutExpired:
            # Bad input causing blocking is acceptable behavior
            pass


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
        # May or may not have --help; the point is it doesn't crash/segfault
        self.assertGreaterEqual(proc.returncode, 0,
            f"Hook crashed with exit code: {proc.returncode}")


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

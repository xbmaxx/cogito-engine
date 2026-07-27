#!/usr/bin/env python3
"""
tool_trace 测试用例 — Phase 4 · MemOS 能力整合
================================================

测试覆盖：工具调用采集、持久化、错误模式检测、洞察生成、XML 注入。

## 测试用例清单

| 编号 | 测试函数 | 类型 | 输入 | 预期输出 |
|------|---------|------|------|---------|
| CT-01 | test_collect_writes_file | 集成 | 1 条工具调用 | tool_trace_log.jsonl 有写入 |
| CT-02 | test_load_traces | 正常 | 写入后读回 | 内容匹配 |
| CT-03 | test_load_traces_empty | 边界 | 从未写入 | [] |
| CT-04 | test_error_pattern_match | 正常 | 3 条同类型错误 | 1 个 ErrorPattern |
| CT-05 | test_error_pattern_no_match | 边界 | 不同错误 | [] |
| CT-06 | test_error_pattern_below_threshold | 边界 | 仅 1 条 | [] |
| CT-07 | test_build_insights_empty | 边界 | 空 traces | "" |
| CT-08 | test_build_insights_with_data | 正常 | 有工具调用 | 含调用次数 |
| CT-09 | test_build_insights_with_errors | 正常 | 有错误 | 含错误提示 |
| CT-10 | test_format_xml_nonempty | 格式 | insights 文本 | 含 <tool_insights> |
| CT-11 | test_format_xml_empty | 格式 | "" | "" |
| CT-12 | test_edge_long_args | 边界 | args 很长 | 不崩溃，truncated |
| CT-13 | test_edge_error_no_type | 边界 | error_type=None | status="error" 可识别 |
| CT-14 | test_edge_mixed_success_error | 正常 | 混合记录 | 正确计算成功率 |

## 数据约定

ToolTrace 条目格式（tool_trace_log.jsonl）：
    {
        "timestamp": ISO8601,
        "session_id": str,
        "tool_name": str,
        "args": str,            # JSON 序列化
        "status": str,          # "ok" | "error"
        "duration_ms": int,
        "error_type": str or "",
        "error_message": str or "",
    }
"""
import unittest
import sys
import os
import json
import tempfile
import shutil
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from cogito_core.tool_trace import (
        ToolTrace, ErrorPattern,
        collect_tool_call, load_traces, clear_traces,
        analyze_error_patterns, build_tool_insights,
        format_tool_insights_xml,
        _set_trace_dir,
    )
    TOOL_TRACE_AVAILABLE = True
except ImportError as e:
    TOOL_TRACE_AVAILABLE = False
    _import_error = str(e)


def _temp_trace_dir():
    """创建临时目录用于测试，返回路径。"""
    d = tempfile.mkdtemp(prefix="cogito_trace_test_")
    _set_trace_dir(d)
    return d


@unittest.skipUnless(TOOL_TRACE_AVAILABLE, f"tool_trace not available: {locals().get('_import_error', '?')}")
class TestCollectAndLoad(unittest.TestCase):
    """采集与加载测试（CT-01 ~ CT-03）。"""

    def setUp(self):
        self._tmp = _temp_trace_dir()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_collect_writes_file(self):
        """CT-01: 采集 1 条工具调用 → 文件被写入。"""
        collect_tool_call(
            tool_name="terminal",
            args={"command": "ls -la"},
            result="file1 file2",
            status="ok",
            session_id="sess-001",
            duration_ms=120,
        )
        traces = load_traces()
        self.assertGreaterEqual(len(traces), 1)
        self.assertEqual(traces[0]["tool_name"], "terminal")
        self.assertEqual(traces[0]["status"], "ok")

    def test_load_traces(self):
        """CT-02: 写入 2 条 → 读回 2 条，内容匹配。"""
        collect_tool_call(tool_name="read_file", args={"path": "/a"}, result="ok", status="ok")
        collect_tool_call(tool_name="write_file", args={"path": "/b"}, result="ok", status="ok")
        traces = load_traces()
        self.assertEqual(len(traces), 2)

    def test_load_traces_empty(self):
        """CT-03: 从未写入 → []. """
        _set_trace_dir(tempfile.mkdtemp(prefix="empty_"))
        self.assertEqual(load_traces(), [])

    def test_collect_with_error(self):
        """CT-01b: 采集错误调用 → status="error"，error_type 保留。"""
        collect_tool_call(
            tool_name="terminal",
            args={"command": "docker ps"},
            result="Error response from daemon",
            status="error",
            error_type="DockerError",
            error_message="Cannot connect to Docker daemon",
            session_id="sess-001",
        )
        traces = load_traces()
        self.assertGreaterEqual(len(traces), 1)
        self.assertEqual(traces[0]["status"], "error")
        self.assertEqual(traces[0]["error_type"], "DockerError")


@unittest.skipUnless(TOOL_TRACE_AVAILABLE, "tool_trace not available")
class TestErrorPatternDetection(unittest.TestCase):
    """错误模式检测测试（CT-04 ~ CT-06）。"""

    def test_error_pattern_match(self):
        """CT-04: 3 条同类型错误 → 1 个 ErrorPattern。"""
        _tmp = _temp_trace_dir()
        for _ in range(3):
            collect_tool_call(tool_name="unknown_tool", args={}, result="err", status="error",
                              error_type="ToolNotFound", error_message="command not found")
        traces = load_traces()
        patterns = analyze_error_patterns(traces, min_count=2)
        self.assertGreaterEqual(len(patterns), 1)
        self.assertEqual(patterns[0].error_type, "ToolNotFound")
        self.assertGreaterEqual(patterns[0].count, 3)
        shutil.rmtree(_tmp, ignore_errors=True)

    def test_error_pattern_no_match(self):
        """CT-05: 不同的错误类型 → []。"""
        _tmp = _temp_trace_dir()
        collect_tool_call(tool_name="read_file", args={}, result="err", status="error",
                          error_type="FileNotFound", error_message="not found")
        collect_tool_call(tool_name="terminal", args={}, result="err", status="error",
                          error_type="DockerError", error_message="timeout")
        traces = load_traces()
        patterns = analyze_error_patterns(traces, min_count=2)
        self.assertEqual(patterns, [])
        shutil.rmtree(_tmp, ignore_errors=True)

    def test_error_pattern_below_threshold(self):
        """CT-06: 仅 1 条 → []（min_count=2 不足）。"""
        _tmp = _temp_trace_dir()
        collect_tool_call(tool_name="bad", args={}, result="err", status="error",
                          error_type="Unknown", error_message="fail")
        traces = load_traces()
        patterns = analyze_error_patterns(traces, min_count=2)
        self.assertEqual(patterns, [])
        shutil.rmtree(_tmp, ignore_errors=True)


@unittest.skipUnless(TOOL_TRACE_AVAILABLE, "tool_trace not available")
class TestBuildInsights(unittest.TestCase):
    """洞察生成测试（CT-07 ~ CT-09）。"""

    def test_build_insights_empty(self):
        """CT-07: 空 traces → \"\"。"""
        self.assertEqual(build_tool_insights([]), "")

    def test_build_insights_with_data(self):
        """CT-08: 有工具调用 → 含行为评估和调用统计。"""
        traces = [
            {"tool_name": "terminal", "status": "ok", "duration_ms": 100},
            {"tool_name": "terminal", "status": "ok", "duration_ms": 200},
            {"tool_name": "read_file", "status": "error", "duration_ms": 50,
             "error_type": "FileNotFound"},
        ]
        insights = build_tool_insights(traces)
        self.assertIn("行为评估", insights)
        self.assertIn("次调用", insights)       # 含统计数字

    def test_build_insights_with_errors(self):
        """CT-09: 有错误 → 含风险提示。"""
        traces = [
            {"tool_name": "terminal", "status": "error", "duration_ms": 100,
             "error_type": "DockerError", "error_message": "daemon not running"},
            {"tool_name": "terminal", "status": "error", "duration_ms": 100,
             "error_type": "DockerError", "error_message": "connection refused"},
        ]
        insights = build_tool_insights(traces)
        self.assertIn("行为评估", insights)
        self.assertIn("terminal", insights)     # 工具名出现在风险提示中


@unittest.skipUnless(TOOL_TRACE_AVAILABLE, "tool_trace not available")
class TestFormatXML(unittest.TestCase):
    """XML 注入格式测试（CT-10 ~ CT-11）。"""

    def test_format_xml_nonempty(self):
        """CT-10: insights 文本 → 含 <tool_insights> 标签。"""
        xml = format_tool_insights_xml("调用了 5 次工具，成功率 80%")
        self.assertIn("<tool_insights>", xml)
        self.assertIn("</tool_insights>", xml)
        self.assertIn("调用了 5 次工具", xml)

    def test_format_xml_empty(self):
        """CT-11: 空文本 → 空字符串。"""
        self.assertEqual(format_tool_insights_xml(""), "")


@unittest.skipUnless(TOOL_TRACE_AVAILABLE, "tool_trace not available")
class TestEdgeCases(unittest.TestCase):
    """边界值测试（CT-12 ~ CT-14）。"""

    def test_edge_long_args(self):
        """CT-12: args 很长（>1000 字符）→ 不崩溃，自动截断。"""
        _tmp = _temp_trace_dir()
        long_args = {"data": "x" * 5000}
        try:
            collect_tool_call(tool_name="test", args=long_args, result="ok", status="ok")
            traces = load_traces()
            self.assertGreaterEqual(len(traces), 1)
            stored_args = traces[0].get("args", "")
            self.assertLessEqual(len(stored_args), 2000)
        except Exception:
            self.fail("长 args 不应崩溃")
        shutil.rmtree(_tmp, ignore_errors=True)

    def test_edge_error_no_type(self):
        """CT-13: error_type=None → status="error" 即可识别。"""
        _tmp = _temp_trace_dir()
        collect_tool_call(tool_name="test", args={}, result="fail",
                          status="error", error_type=None, error_message="unknown")
        traces = load_traces()
        self.assertEqual(traces[0]["status"], "error")
        shutil.rmtree(_tmp, ignore_errors=True)

    def test_edge_mixed_success_error(self):
        """CT-14: 混合记录 → 正确计算并展示统计。"""
        traces = [
            {"tool_name": "t1", "status": "ok"},
            {"tool_name": "t2", "status": "ok"},
            {"tool_name": "t3", "status": "error", "error_type": "X"},
            {"tool_name": "t1", "status": "ok"},
        ]
        insights = build_tool_insights(traces)
        self.assertIn("行为评估", insights)
        self.assertIn("次调用", insights)       # 含调用次数统计


if __name__ == "__main__":
    unittest.main()

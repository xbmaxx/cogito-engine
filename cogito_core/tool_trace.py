"""
tool_trace.py —— 工具调用采集与错误模式检测引擎。

采集 Hermes 的 tool call 记录，持久化到 tool_trace_log.jsonl，
支持 session-end 阶段的工具链分析和错误模式检测。

依赖于 Hermes 的 post_tool_call hook（已在框架中确认存在）。
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .persistence import get_cogito_home

logger = logging.getLogger(__name__)

# ── 持久化路径 ──

# 本地覆盖（测试用）——不改 persistence 全局，避免破坏测试隔离
_LOCAL_TRACE_DIR: Optional[Path] = None

TRACE_FILE = "tool_trace_log.jsonl"
_MAX_TRACES = 1000
_ARGS_MAX_LEN = 1500  # args 序列化最大长度


def _set_trace_dir(path: Optional[str]) -> None:
    """重设 trace 目录（测试用，仅影响本模块，不改 persistence 全局）。

    传 None 清空本地覆盖，回退到 persistence 统一目录。
    """
    global _LOCAL_TRACE_DIR
    _LOCAL_TRACE_DIR = Path(path) if path is not None else None


def _trace_file() -> Path:
    """返回 trace 文件路径。本地覆盖优先，回退到 persistence 统一目录。"""
    if _LOCAL_TRACE_DIR is not None:
        return _LOCAL_TRACE_DIR / TRACE_FILE
    return get_cogito_home() / TRACE_FILE


# ── 数据类 ──


@dataclass
class ToolTrace:
    """一条工具调用记录。"""
    timestamp: str = ""
    session_id: str = ""
    tool_name: str = ""
    args: str = ""
    status: str = "ok"        # "ok" | "error"
    duration_ms: int = 0
    error_type: str = ""
    error_message: str = ""


@dataclass
class ErrorPattern:
    """检测到的错误模式。"""
    error_type: str
    count: int
    tools: List[str] = field(default_factory=list)
    message_samples: List[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        return min(1.0, self.count / 10.0)


# ── 采集 ──


def collect_tool_call(
    tool_name: str,
    args: Optional[Dict[str, Any]] = None,
    result: Any = None,
    status: str = "ok",
    error_type: Optional[str] = None,
    error_message: Optional[str] = None,
    duration_ms: int = 0,
    session_id: str = "",
) -> None:
    """采集一条工具调用并写入持久化。

    Args:
        tool_name: 工具名称
        args: 调用参数
        result: 调用结果（仅用于日志，不持久化完整内容）
        status: "ok" 或 "error"
        error_type: 错误类型
        error_message: 错误消息
        duration_ms: 耗时（毫秒）
        session_id: 会话 ID
    """
    # 序列化 args，限制长度
    args_str = ""
    if args:
        try:
            args_raw = json.dumps(args, ensure_ascii=False)
            args_str = args_raw[:_ARGS_MAX_LEN]
        except (TypeError, ValueError):
            args_str = str(args)[:_ARGS_MAX_LEN]

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id or "",
        "tool_name": tool_name or "",
        "args": args_str,
        "status": status or "ok",
        "duration_ms": int(duration_ms or 0),
        "error_type": error_type or "",
        "error_message": (error_message or "")[:200],
    }

    try:
        fp = _trace_file()
        with open(fp, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        _trim_traces()
    except Exception as exc:
        logger.error("写入工具调用记录失败: %s", exc)


def _trim_traces() -> None:
    """修剪 trace 文件到 _MAX_TRACES 行。"""
    fp = _trace_file()
    if not fp.exists():
        return
    try:
        with open(fp, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) <= _MAX_TRACES:
            return
        with open(fp, "w", encoding="utf-8") as f:
            f.writelines(lines[-_MAX_TRACES:])
    except Exception as exc:
        logger.error("修剪 trace 文件失败: %s", exc)


# ── 加载 ──


def load_traces(k: int = 100) -> List[Dict[str, Any]]:
    """加载最近 k 条工具调用记录。

    Args:
        k: 返回条数

    Returns:
        最近 k 条记录（按时间倒序，最新的在后）。
    """
    fp = _trace_file()
    if not fp.exists():
        return []
    try:
        with open(fp, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [
            json.loads(line)
            for line in lines[-k:] if line.strip()
        ]
    except Exception as exc:
        logger.error("加载工具调用记录失败: %s", exc)
        return []


def clear_traces() -> None:
    """清空所有 trace 记录（测试用）。"""
    fp = _trace_file()
    if fp.exists():
        try:
            fp.unlink()
        except Exception:
            pass


# ── 错误模式检测 ──


def analyze_error_patterns(
    traces: List[Dict[str, Any]],
    min_count: int = 2,
) -> List[ErrorPattern]:
    """从工具调用记录中检测错误模式。

    策略：按 error_type 聚合，出现 ≥min_count 次 → 错误模式。

    Args:
        traces: 工具调用记录列表
        min_count: 最低出现次数

    Returns:
        按 count 降序排列的 ErrorPattern 列表
    """
    if not traces:
        return []

    error_groups: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
        "count": 0, "tools": set(), "messages": [],
    })

    for t in traces:
        if t.get("status") != "error":
            continue
        et = t.get("error_type", "") or "UnknownError"
        error_groups[et]["count"] += 1
        error_groups[et]["tools"].add(t.get("tool_name", ""))
        msg = t.get("error_message", "")
        if msg:
            error_groups[et]["messages"].append(msg[:100])

    results: List[ErrorPattern] = []
    for et, data in error_groups.items():
        if data["count"] >= min_count:
            results.append(ErrorPattern(
                error_type=et,
                count=data["count"],
                tools=sorted(data["tools"]),
                message_samples=data["messages"][:3],
            ))

    results.sort(key=lambda p: p.count, reverse=True)
    return results


# ── 洞察生成 ──


def build_tool_insights(
    traces: List[Dict[str, Any]],
) -> str:
    """从工具调用记录生成自然语言洞察。

    Args:
        traces: 工具调用记录列表

    Returns:
        洞察文本，空 traces 时返回 ""。
    """
    if not traces:
        return ""

    total = len(traces)
    ok_count = sum(1 for t in traces if t.get("status") == "ok")
    err_count = total - ok_count
    success_rate = (ok_count / total * 100) if total > 0 else 0

    # 统计工具调用频次
    tool_counts: Counter = Counter()
    for t in traces:
        name = t.get("tool_name", "unknown")
        if name:
            tool_counts[name] += 1

    top_tools = tool_counts.most_common(3)

    parts: List[str] = []
    parts.append(f"当前 session 调用了 {total} 次工具，成功率 {success_rate:.0f}%")

    if top_tools:
        tools_desc = "、".join(f"{n}({c}次)" for n, c in top_tools)
        parts.append(f"高频工具：{tools_desc}")

    if err_count > 0:
        # 错误模式
        patterns = analyze_error_patterns(traces, min_count=1)
        if patterns:
            top_err = patterns[0]
            parts.append(f"最常见错误：{top_err.error_type}（{top_err.count}次）")

    return " | ".join(parts)


# ── XML 注入 ──


def format_tool_insights_xml(insights: str) -> str:
    """将工具洞察格式化为 XML 注入片段。

    Args:
        insights: build_tool_insights() 输出的文本

    Returns:
        XML 字符串，空时返回 ""。
    """
    if not insights:
        return ""
    return f"<tool_insights>{_xml_escape(insights)}</tool_insights>"


def _xml_escape(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))

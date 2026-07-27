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
    """从工具调用记录生成可指导 LLM 决策的行为评估。

    不做的事：告诉 LLM "你调了 25 次 terminal"——LLM 刚做完这些调用。
    要做的事：转化为 LLM 不知道的信息——
    1. 行为画像：当前任务的工具使用特征（探索型/执行型/修复型）
    2. 模式检测：稳定降级路径、反常波动、效率问题
    3. 决策指引：该加强、该回避、该保留的行为

    Args:
        traces: 工具调用记录列表（按时间顺序）

    Returns:
        紧凑行为评估文本，空 traces 时返回 ""。
        Token 控制在 ~80-150，不膨胀 context。
    """
    if not traces:
        return ""

    total = len(traces)
    ok_count = sum(1 for t in traces if t.get("status") == "ok")
    success_rate = (ok_count / total * 100) if total > 0 else 0

    # ── 1. 工具使用画像 ──
    tool_counts: Counter = Counter()
    err_tool_counts: Counter = Counter()
    tool_sequence: List[str] = []
    for t in traces:
        name = t.get("tool_name", "unknown")
        if name:
            tool_counts[name] += 1
            tool_sequence.append(name)
            if t.get("status") != "ok":
                err_tool_counts[name] += 1

    # 画像分类
    exploration_tools = {"read_file", "search_files", "skill_view", "vision_analyze"}
    execution_tools = {"terminal", "patch", "write_file", "execute_code", "process"}
    modification_tools = {"patch", "write_file", "skill_manage"}

    expl_count = sum(tool_counts.get(t, 0) for t in exploration_tools)
    exec_count = sum(tool_counts.get(t, 0) for t in execution_tools)
    mod_count = sum(tool_counts.get(t, 0) for t in modification_tools)

    # 画像标签
    if total >= 10 and expl_count / total >= 0.5:
        profile = "探索型——正在大范围了解项目结构"
    elif total >= 10 and mod_count / total >= 0.4:
        profile = "修整型——大量代码编辑和文件变更"
    else:
        profile = "执行型——主要在运行命令和做具体操作"

    # ── 2. 模式检测 ──
    parts: List[str] = []

    # 2a. 降级链: 工具A失败→工具B成功
    fallback_chains: Dict[str, Counter] = defaultdict(Counter)
    prev_status = None
    prev_tool = ""
    for t in traces:
        name = t.get("tool_name", "")
        if not name:
            continue
        status = t.get("status", "ok")
        if prev_status == "error" and status == "ok" and prev_tool != name:
            fallback_chains[prev_tool][name] += 1
        prev_status = status
        prev_tool = name

    fallback_lines: List[str] = []
    for src_tool, fallbacks in fallback_chains.items():
        for dst_tool, cnt in fallbacks.items():
            if cnt >= 2:
                fallback_lines.append(f"{src_tool}→{dst_tool}降级已稳定{cnt}次")

    # 2b. 全局异常对比
    global_anomaly = ""
    try:
        all_traces = load_traces(k=_MAX_TRACES)
        if len(all_traces) > len(traces):
            all_ok = sum(1 for t in all_traces if t.get("status") == "ok")
            all_total = len(all_traces)
            global_rate = (all_ok / all_total * 100) if all_total > 0 else 0
            delta = success_rate - global_rate
            if delta < -15:
                global_anomaly = f"当前成功率明显低于全局（{global_rate:.0f}%），可能是任务难度偏高或工具不稳定"
    except Exception:
        pass

    # 2c. 高失败率工具
    risky_tools: List[str] = []
    for name, total_cnt in tool_counts.most_common():
        if total_cnt >= 2:
            err_cnt = err_tool_counts.get(name, 0)
            if err_cnt > 0 and err_cnt / total_cnt >= 0.3:
                risky_tools.append(name)

    # ── 3. 构建输出 ──
    status_label = "稳定" if success_rate >= 90 else ("正常" if success_rate >= 70 else "波动")
    parts.append(f"行为评估：{profile}，工具链{status_label}（{total}次调用）")

    if fallback_lines:
        parts.append("模式：" + "；".join(fallback_lines))

    if risky_tools:
        risky_desc = "、".join(risky_tools[:3])
        alt_hint = _suggest_alternative(risky_tools[:2])
        parts.append(f"注意：{risky_desc}失败率偏高。{alt_hint}")

    if global_anomaly:
        parts.append(global_anomaly)

    if success_rate >= 95 and not risky_tools:
        parts.append("无异常，继续当前策略。")

    return "。".join(parts) + "。" if parts[-1].endswith("。") else "。".join(parts)


def _suggest_alternative(risky_tools: List[str]) -> str:
    """为高失败率工具生成替代建议。"""
    alt_map = {
        "skill_manage": "优先用patch直接编辑文件",
        "skill_view": "用read_file直接读skill目录",
        "execute_code": "用terminal替代简单脚本",
        "terminal": "检查命令是否需要pty或timeout参数",
        "write_file": "确认目标目录存在且可写",
        "read_file": "确认文件存在后再读取",
    }
    hints = []
    for t in risky_tools:
        if t in alt_map:
            hints.append(alt_map[t])
    if hints:
        return "；".join(hints[:2])
    return "考虑降级到更稳健的替代工具"


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


def _suggest_for_error(error_type: str, tools: List[str]) -> str:
    """根据错误类型生成可操作建议。

    LLM 拿到这个建议后可以调整行为，无需额外推理。
    """
    tool_list = "、".join(tools[:3]) if tools else "工具"
    suggestions = {
        "timeout": f"{tool_list} 多次超时 → 考虑缩短 timeout 参数或分批处理",
        "ConnectionError": f"{tool_list} 网络不稳定 → 优先用缓存或降级到本地方案",
        "PermissionError": f"{tool_list} 权限不足 → 确认路径可写或使用 /tmp 替代",
        "FileNotFoundError": f"{tool_list} 文件未找到 → 确认路径有效性后再调用",
        "HTTPError": f"{tool_list} HTTP 请求失败 → 检查 URL 可达性，避免硬编码地址",
        "RateLimitError": f"{tool_list} 被限流 → 降低调用频率，合并请求",
        "JSONDecodeError": f"{tool_list} 返回格式异常 → 先验证响应完整性再解析",
    }
    for key, msg in suggestions.items():
        if key.lower() in error_type.lower():
            return msg
    return f"{tool_list} 出错（{error_type}）→ 采用更鲁棒的替代方案"

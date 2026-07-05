"""
hook_entry.py —— Claude Code / Copilot / Codex 统一 CLI 入口。

这三家 AI Coding Agent 的 hook JSON 接口高度相似：
- stdin 读取包含 messages 数组的 JSON
- 调 CogitoEngine.process()
- stdout 输出 {"hookSpecificOutput": {"additionalContext": "<consciousness>XML</consciousness>"}}

支持 --session-end 参数触发 end_session。

使用方式：
    # 作为 hook 脚本
    python3 hook_entry.py < input.json
    python3 hook_entry.py --session-end < input.json

    # Claude Code hook 配置示例 (claude_hooks.json)：
    {
      "hooks": {
        "PreToolUse": [
          {
            "matcher": "*",
            "hooks": [{
              "type": "command",
              "command": "python3 adapters/hook_entry.py"
            }]
          }
        ]
      }
    }
"""

from __future__ import annotations

import json
import sys
import os
import argparse
from typing import Any, Dict, List, Optional, Tuple

# 确保能找到 cogito_core
# 尝试多个路径：repo 同级目录 > 用户运行时目录 > 当前目录
_cogito_paths = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    os.path.expanduser("~/.cogito"),
    os.path.expanduser("~/.hermes/plugins/hermes_consciousness"),
]
for _p in _cogito_paths:
    if os.path.isdir(os.path.join(_p, "cogito_core")):
        sys.path.insert(0, _p)
        break
else:
    # 最后兜底：当前工作目录
    sys.path.insert(0, os.getcwd())

from cogito_core.engine import CogitoEngine, EngineState

# 状态持久化路径（跨 hook 调用之间共享状态）
_STATE_DIR = os.path.expanduser("~/.cogito/hook_states")
_STATE_FILE_TEMPLATE = "hook_state_{session_hash}.json"


def _session_hash(messages: List[Dict[str, Any]]) -> str:
    """根据消息内容生成简单的 session hash（用于状态持久化文件名）。"""
    import hashlib

    key = ""
    for msg in messages[-3:]:
        content = msg.get("content", "")
        if isinstance(content, str):
            key += content[:100]
    return hashlib.md5(key.encode()).hexdigest()[:12]


def _load_state(session_hash: str) -> EngineState:
    """从磁盘加载引擎状态。"""
    os.makedirs(_STATE_DIR, exist_ok=True)
    path = os.path.join(_STATE_DIR, _STATE_FILE_TEMPLATE.format(session_hash=session_hash))
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return EngineState.from_dict(data, session_id=session_hash)
        except Exception:
            pass
    return EngineState(session_id=session_hash)


def _save_state(session_hash: str, state: EngineState) -> None:
    """持久化引擎状态到磁盘。"""
    os.makedirs(_STATE_DIR, exist_ok=True)
    path = os.path.join(_STATE_DIR, _STATE_FILE_TEMPLATE.format(session_hash=session_hash))
    try:
        with open(path, "w") as f:
            json.dump(state.to_dict(), f, indent=2)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("保存 hook 状态失败: %s", exc)


def parse_hook_input() -> Dict[str, Any]:
    """从 stdin 读取 hook JSON 输入。

    支持的格式：
    - Claude Code hook: {"messages": [...], "session_id": "..."}
    - Copilot/Copilot hook: {"messages": [...], ...}
    - Codex hook: 同上

    Returns:
        解析后的 JSON 字典
    """
    raw = sys.stdin.read()
    if not raw.strip():
        return {"messages": []}

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # 可能只有单条消息文本
        return {"messages": [{"role": "user", "content": raw.strip()}]}


def extract_messages(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 hook 输入中提取 messages 数组。"""
    # 直接有 messages 字段
    if "messages" in data and isinstance(data["messages"], list):
        return data["messages"]

    # Claude Code 格式：可能嵌套在 hook_input 中
    for key in ("hook_input", "input", "context"):
        if key in data and isinstance(data[key], dict):
            nested = data[key]
            if "messages" in nested and isinstance(nested["messages"], list):
                return nested["messages"]

    return []


def format_output(xml: str) -> str:
    """格式化为 hook 标准输出 JSON。

    Claude Code / Copilot / Codex 均支持：
    {"hookSpecificOutput": {"additionalContext": "..."}}

    Copilot 额外支持：
    {"hookSpecificOutput": {"additionalContext": "...", "hookEventName": "..."}}
    """
    output = {
        "hookSpecificOutput": {
            "additionalContext": xml,
        }
    }
    return json.dumps(output, ensure_ascii=False)


def format_end_session_output(reflection: Optional[Dict[str, Any]] = None) -> str:
    """格式化为会话结束时的输出 JSON。"""
    output = {
        "hookSpecificOutput": {
            "additionalContext": "",
            "reflection": reflection or {},
        }
    }
    return json.dumps(output, ensure_ascii=False)


def main() -> None:
    """hook_entry 主入口。"""
    parser = argparse.ArgumentParser(
        description="Cogito Engine hook entry for Claude Code / Copilot / Codex"
    )
    parser.add_argument(
        "--session-end",
        action="store_true",
        help="触发 end_session 而非 process",
    )
    parser.add_argument(
        "--no-save-state",
        action="store_true",
        help="不持久化引擎状态到磁盘",
    )
    args = parser.parse_args()

    # 读取输入
    data = parse_hook_input()
    messages = extract_messages(data)

    if not messages:
        # 空消息：输出空 XML
        print(format_output("<consciousness />"))
        return

    # 创建引擎
    engine = CogitoEngine(
        include_weather=False,
        include_battery=True,
        include_resources=True,
    )

    session_hash = _session_hash(messages) if not args.no_save_state else "ephemeral"

    if args.session_end:
        # ── 会话结束模式 ──
        state = _load_state(session_hash) if not args.no_save_state else EngineState()
        engine.end_session(state=state, messages=messages)

        # 尝试读取反射
        reflection = None
        try:
            latest = engine.session_reflector.load_recent(1)
            if latest:
                reflection = latest[0]
        except Exception:
            pass

        if not args.no_save_state:
            _save_state(session_hash, state)

        print(format_end_session_output(reflection))

    else:
        # ── 正常 process 模式 ──
        state = _load_state(session_hash) if not args.no_save_state else EngineState()
        xml, new_state = engine.process(messages, state)

        if not args.no_save_state:
            _save_state(session_hash, new_state)

        print(format_output(xml))


if __name__ == "__main__":
    main()

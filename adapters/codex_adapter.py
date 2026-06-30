"""
codex_adapter.py —— OpenAI Codex CLI hook 适配器（薄封装）。

Codex 的 hook JSON 接口与 Claude Code / Copilot 高度相似，
直接复用 hook_entry.py 的 CLI 入口。

Codex hook 配置示例 (.codex/hooks.json 或 codex.yaml)：
hooks:
  PreToolUse:
    - command: python3 /path/to/adapters/hook_entry.py
  SessionEnd:
    - command: python3 /path/to/adapters/hook_entry.py --session-end
"""

# Codex 直接使用 hook_entry.py 作为 CLI 入口
# 此文件仅作为文档/配置引用和薄封装存在

from .hook_entry import main, parse_hook_input, extract_messages, format_output

__all__ = ["main", "parse_hook_input", "extract_messages", "format_output"]

# CLI 入口（可直接运行）
if __name__ == "__main__":
    main()

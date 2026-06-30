"""
adapters —— Cogito Engine 平台适配器集合。

每个适配器是一个薄层（50-200行），将特定平台/AI Agent 的 hooks 事件
翻译为 CogitoEngine.process() / end_session() 调用。

适配器清单：
- HermesAdapter: Hermes Plugin 适配器（register / _pre_llm_call / _on_session_end）
- hook_entry: Claude Code / Copilot / Codex 通用 CLI 入口
- gemini_adapter: Gemini CLI BeforeModel hook 适配器
- prompt_only_adapter: .cursorrules / .windsurfrules 内容生成

使用方式：
    from cogito_engine.adapters import HermesAdapter
    from cogito_engine.adapters.hook_entry import main as hook_main
"""

from .hermes_adapter import HermesAdapter
from .gemini_adapter import GeminiAdapter
from .prompt_only_adapter import generate_cursor_rules, generate_windsurf_rules

__all__ = [
    "HermesAdapter",
    "GeminiAdapter",
    "generate_cursor_rules",
    "generate_windsurf_rules",
]

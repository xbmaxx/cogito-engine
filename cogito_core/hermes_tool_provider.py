"""
hermes_tool_provider.py — 通用 Hermes 工具适配器。

不绑定具体插件类（如 HolographicMemoryProvider）。
通过 Hermes 已注册的工具名（如 "fact_store"）做通用适配。
任何在 Hermes 中注册为工具的记忆/知识插件，都能通过同一接口检索。
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from .knowledge_provider import KnowledgeProvider

logger = logging.getLogger(__name__)


class HermesToolProvider(KnowledgeProvider):
    """通用 Hermes 工具适配器 — 不绑定具体记忆插件。

    通过 tool name（如 "fact_store"）和注入的 tool 对象来适配。
    底层是什么记忆插件（Holographic / Hindsight / 自定义）对调用方透明。
    """

    def __init__(
        self,
        tool: Any = None,
        tool_name: str = "hermes_tool",
    ) -> None:
        """初始化。

        Args:
            tool: Hermes 注册的工具对象，需有 search(query, limit) 方法。
                  传 None 表示后续通过 set_tool() 注入。
            tool_name: 工具标识名，用于 name() 返回。
        """
        self.tool = tool
        self._tool_name = tool_name

    def name(self) -> str:
        return self._tool_name

    def available(self) -> bool:
        """工具对象存在且有 search 方法即为可用。"""
        try:
            return self.tool is not None and hasattr(self.tool, "search")
        except Exception:
            return False

    def search(self, query: str, limit: int = 3) -> List[str]:
        """委托给注入的 tool.search()。"""
        if not self.available():
            return []
        try:
            results = self.tool.search(query, limit=limit)
            # 统一输出格式：如果 tool 返回 dict 列表，取 content 字段
            normalized = []
            for r in results[:limit]:
                if isinstance(r, dict):
                    normalized.append(str(r.get("content", r)))
                else:
                    normalized.append(str(r))
            return normalized
        except Exception as exc:
            logger.debug("HermesToolProvider.search() 失败: %s", exc)
            return []

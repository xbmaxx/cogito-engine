"""
fact_store_provider.py — Hermes Holographic Memory 适配器。

实现 KnowledgeProvider 接口，从 Hermes 的 Holographic Memory (fact_store)
检索事实，注入到 Cogito 意识流的 KnowledgeBridge 层。

当 Holographic Memory 不可用时优雅降级。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FactStoreProvider:
    """包装 Hermes 的 Holographic Memory，为 KnowledgeBridge 提供事实检索。

    通过工具接口查询 fact_store，支持语义搜索和实体探测。
    """

    def __init__(self) -> None:
        self._memory: Optional[Any] = None
        self._init_error: Optional[str] = None
        self._probed = False

    def _lazy_init(self) -> None:
        """延迟初始化：在首次 search() 时探测可用性。"""
        if self._probed:
            return
        self._probed = True
        try:
            # 尝试从 Hermes 内存系统获取 MemoryProvider
            # 注意：fact_store 作为 Hermes 工具（通过 Holographic Memory 插件注册）
            # 在内部可通过 memory provider 的 search/query 接口访问
            from plugins.memory.holographic import HolographicMemoryProvider

            # 获取全局 MemoryProvider 实例
            from hermes_cli.plugins import get_plugin_manager

            pm = get_plugin_manager()
            if hasattr(pm, "memory_provider") and pm.memory_provider is not None:
                self._memory = pm.memory_provider
                logger.debug("FactStoreProvider: 绑定 HolographicMemoryProvider")
            else:
                # 尝试直接创建（兜底）
                self._memory = HolographicMemoryProvider()
                logger.debug("FactStoreProvider: 创建 HolographicMemoryProvider 实例")
        except Exception as exc:
            self._init_error = str(exc)
            logger.debug("FactStoreProvider: 初始化失败 (%s), 降级为空提供者", exc)

    def name(self) -> str:
        return "fact_store"

    def available(self) -> bool:
        self._lazy_init()
        return self._memory is not None

    def search(self, query: str, limit: int = 3) -> List[str]:
        """搜索 Holographic Memory，返回相关事实列表。"""
        self._lazy_init()
        if not self._memory:
            return []

        try:
            # 尝试 query/search 方法（接口可能因版本不同）
            if hasattr(self._memory, "query"):
                results = self._memory.query(query, limit=limit)
            elif hasattr(self._memory, "search"):
                results = self._memory.search(query, limit=limit)
            else:
                return []

            if not results:
                return []

            # 统一格式化为字符串列表
            formatted = []
            for r in results:
                if isinstance(r, str):
                    formatted.append(r)
                elif isinstance(r, dict):
                    formatted.append(r.get("content", str(r)))
                else:
                    formatted.append(str(r))
            return formatted[:limit]
        except Exception as exc:
            logger.debug("FactStoreProvider.search 失败: %s", exc)
            return []

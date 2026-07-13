"""
knowledge_provider.py — 外部知识检索提供者抽象基类。

任何实现 KnowledgeProvider 接口的外部记忆库都能接入 Cogito 意识流。
"""

from abc import ABC, abstractmethod
from typing import List


class KnowledgeProvider(ABC):
    """外部知识检索提供者。只需实现两个方法即可接入。"""

    @abstractmethod
    def search(self, query: str, limit: int = 3) -> List[str]:
        """语义检索，返回相关事实列表。无匹配时返回空列表。"""
        ...

    @abstractmethod
    def name(self) -> str:
        """提供者标识（如 "fact_store"、"obsidian"）。"""
        ...

    def available(self) -> bool:
        """提供者是否可用。默认 True，子类可覆盖做连接检查。"""
        return True

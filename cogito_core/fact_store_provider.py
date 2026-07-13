"""
fact_store_provider.py — 从 Hermes fact_store 检索知识。

FactStoreProvider 实现 KnowledgeProvider 接口，
从 ~/.hermes/memory_store.db 检索事实，并按信任分分级：
- trust ≥ 0.8：追加行为指引（触发指令）
- trust 0.7-0.8：只展示事实
- trust < 0.7：不检索

验证基准：facts 表 → content(TEXT)、trust_score(REAL)。2026-07-13 实测确认。
"""

import sqlite3
import os
from typing import List, Optional

from .knowledge_provider import KnowledgeProvider


# ── 行为指引规则表 ──

_ACTION_RULES = [
    ("短句", "回复控制在 3 行以内，别写长篇大论"),
    ("数学模型", "讨论方案时给数据，别给直觉"),
    ("偏好", "注意他之前表达过的偏好"),
    ("情绪", "留意他的情绪变化"),
    ("决策", "给选项而不是给建议"),
    ("不打扰", "别频繁追问，等他自己说"),
    ("Markdown", "用表格和短句，别写大段文字"),
    ("观点", "观点要清晰直接，不要模棱两可"),
    ("推理", "给出推理过程，不要直接给结论"),
    ("产品", "从用户角度思考，不要只从技术角度"),
]


class FactStoreProvider(KnowledgeProvider):
    """从 Hermes fact_store 检索知识。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.expanduser(
            "~/.hermes/memory_store.db"
        )

    def name(self) -> str:
        return "fact_store"

    def available(self) -> bool:
        """检查 db 文件存在且可读（防止路径存在但权限不足）。"""
        if not os.path.exists(self.db_path):
            return False
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute("SELECT 1 FROM facts LIMIT 1")
            conn.close()
            return True
        except Exception:
            return False

    def search(self, query: str, limit: int = 3) -> List[str]:
        """
        用 LIKE 模糊匹配检索 fact_store。

        将查询拆为 2-4 字关键词片段，多个 LIKE OR 组合提高命中率。
        trust ≥ 0.8 的事实追加行为指引（→），0.7-0.8 只展示事实。
        无匹配时返回空列表。
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        # 拆 query 为关键词片段（2-4 字），避免长句无法匹配短事实
        keywords = self._tokenize(query)
        if not keywords:
            conn.close()
            return []

        # 构建 OR 条件
        like_clauses = " OR ".join(["content LIKE ?"] * len(keywords))
        params = [f"%{kw}%" for kw in keywords] + [limit]

        rows = conn.execute(f"""
            SELECT content, trust_score
            FROM facts
            WHERE ({like_clauses})
              AND trust_score >= 0.7
              AND length(content) BETWEEN 15 AND 120
            ORDER BY trust_score DESC
            LIMIT ?
        """, params).fetchall()

        conn.close()

        results: List[str] = []
        for row in rows:
            text = row["content"]
            trust = row["trust_score"]

            # Provider 层截断：自然句边界，控制在 120 字内
            if len(text) > 120:
                cut = text[:120].rfind("。")
                if cut > 80:
                    text = text[:cut + 1]
                else:
                    text = text[:117] + "..."

            # 高 trust 追加行为指引
            if trust >= 0.8:
                action = self._derive_action(text)
                if action:
                    text = f"· {text} → {action}"
                else:
                    text = f"· {text}"
            else:
                text = f"· {text}"

            results.append(text)

        return results

    @staticmethod
    def _tokenize(query: str) -> List[str]:
        """将查询拆为 2-4 字关键词片段，用于 LIKE 多词匹配。"""
        if not query or len(query) < 2:
            return [query] if query else []

        tokens = []
        # 2 字片段
        for i in range(len(query) - 1):
            tokens.append(query[i:i+2])
        # 3 字片段
        for i in range(len(query) - 2):
            tokens.append(query[i:i+3])
        # 4 字片段
        for i in range(len(query) - 3):
            tokens.append(query[i:i+4])

        # 去重，限制最多 20 个避免 SQL 过长
        seen = set()
        unique = []
        for t in tokens:
            if t not in seen:
                seen.add(t)
                unique.append(t)
                if len(unique) >= 20:
                    break
        return unique

    @staticmethod
    def _derive_action(text: str) -> Optional[str]:
        """基于事实内容的关键词匹配行为建议。

        初期用规则，后续可升级为 LLM 生成。
        """
        for keyword, action in _ACTION_RULES:
            if keyword in text:
                return action
        return None

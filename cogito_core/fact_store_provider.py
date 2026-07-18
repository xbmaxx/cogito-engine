"""
fact_store_provider.py — 从 Hermes fact_store 检索知识（v3 本地嵌入版）。

Local embedding via fastembed + BAAI/bge-small-zh-v1.5 (dim=512).
完全不依赖外部 API，零配置，全本地推理。

Two-tier search:
  1. LIKE 关键词匹配（baseline，始终运行）
  2. 语义嵌入检索（fastembed 可用即启用，不可用退回 LIKE）

依赖：pip install fastembed（已安装 v0.7.4）
模型自动下载：首次运行时从 HuggingFace 拉取 ONNX 版（~33MB）
"""

from __future__ import annotations

import logging
import os
import sqlite3
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from .knowledge_provider import KnowledgeProvider

logger = logging.getLogger(__name__)

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


# ── 向量工具 ──


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """余弦相似度。返回 [-1, 1] 归一化值。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(av * bv for av, bv in zip(a, b))
    na = sum(av * av for av in a) ** 0.5
    nb = sum(bv * bv for bv in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _pack_vector(vec: List[float]) -> bytes:
    """float32 列表 → 二进制 bytes。"""
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack_vector(data: bytes) -> List[float]:
    """二进制 bytes → float32 列表。"""
    count = len(data) // 4
    return list(struct.unpack(f"<{count}f", data))


# ── 模型句柄（模块级单例，避免重复加载）──

_EMBED_MODEL = None
_EMBED_MODEL_LOCK = threading.Lock()


def _get_embed_model():
    """惰性加载 fastembed 模型。失败时返回 None（退回 LIKE）。"""
    global _EMBED_MODEL
    if _EMBED_MODEL is not None:
        return _EMBED_MODEL
    with _EMBED_MODEL_LOCK:
        if _EMBED_MODEL is not None:
            return _EMBED_MODEL
        try:
            from fastembed import TextEmbedding
            _EMBED_MODEL = TextEmbedding(model_name="BAAI/bge-small-zh-v1.5")
            try:
                logger.info("本地嵌入模型已加载: bge-small-zh-v1.5 dim=%d", _EMBED_MODEL.length)
            except Exception:
                logger.info("本地嵌入模型已加载: bge-small-zh-v1.5")
        except Exception as exc:
            logger.warning("fastembed 不可用（退回 LIKE 检索）: %s", exc)
            _EMBED_MODEL = False  # 标记不可用，不再重试
    return _EMBED_MODEL if _EMBED_MODEL is not False else None


# ── FactStoreProvider ──


class FactStoreProvider(KnowledgeProvider):
    """从 Hermes fact_store 检索知识。支持 LIKE + 本地嵌入两路并行检索。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.expanduser(
            "~/.hermes/memory_store.db"
        )
        # LRU 缓存：query → (embedding, timestamp)
        self._emb_cache: Dict[str, tuple] = {}
        # 标记 embedding 列是否已就绪
        self._emb_column_ready = False
        # 后台 embedding 生成
        self._embed_bg_done = False
        # 预热：触发模型加载（非阻塞）
        if _get_embed_model() is not None:
            self._start_background_embed()

    # ── 后台 embedding 批量生成（不阻塞对话）──

    def _start_background_embed(self) -> None:
        """在后台线程中为所有可命中事实预生成向量。"""
        def _run():
            try:
                self._ensure_embedding_column()
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                rows = conn.execute("""
                    SELECT fact_id, content FROM facts
                    WHERE trust_score >= 0.7
                      AND length(content) BETWEEN 15 AND 120
                      AND (category IS NULL OR category != 'roleplay')
                      AND embedding IS NULL
                """).fetchall()
                conn.close()
                if not rows:
                    self._embed_bg_done = True
                    return

                model = _get_embed_model()
                if model is None:
                    self._embed_bg_done = True
                    return

                # fastembed 支持批量推理，一次处理全部
                texts = [row["content"][:500] for row in rows]
                embeddings = list(model.embed(texts))

                conn2 = sqlite3.connect(self.db_path)
                for i, (vec, row) in enumerate(zip(embeddings, rows)):
                    if vec is not None:
                        blob = _pack_vector(list(vec))
                        conn2.execute(
                            "UPDATE facts SET embedding = ? WHERE fact_id = ?",
                            (blob, row["fact_id"]),
                        )
                    if i > 0 and i % 20 == 0:
                        conn2.commit()
                conn2.commit()
                conn2.close()
                self._embed_bg_done = True
                logger.info("本地嵌入后台生成完成: %d 条", len(rows))
            except Exception as exc:
                logger.debug("后台嵌入生成失败: %s", exc)
                self._embed_bg_done = True

        _t = threading.Thread(target=_run, daemon=True)
        _t.start()

    # ── 接口 ──

    def name(self) -> str:
        return "fact_store"

    def available(self) -> bool:
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
        """两路并行检索：LIKE + 本地嵌入。"""
        like_rows = self._like_search(query, limit * 2)
        like_formatted = [self._format_result(r) for r in like_rows]

        emb_formatted: List[tuple] = []
        if len(query) >= 5 and _get_embed_model() is not None:
            try:
                emb_formatted = self._embedding_search(query, limit * 2)
            except Exception as exc:
                logger.debug("嵌入检索失败（退回 LIKE）: %s", exc)

        return self._merge_results(like_formatted, emb_formatted, limit)

    # ── LIKE 检索 ──

    def _like_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        self._ensure_embedding_column()
        keywords = self._tokenize(query)
        if not keywords:
            return []
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            clauses = " OR ".join(["content LIKE ?"] * len(keywords))
            params = [f"%{kw}%" for kw in keywords] + [limit]
            rows = conn.execute(f"""
                SELECT fact_id, content, trust_score, embedding
                FROM facts
                WHERE ({clauses})
                  AND trust_score >= 0.7
                  AND length(content) BETWEEN 15 AND 120
                  AND (category IS NULL OR category != 'roleplay')
                ORDER BY trust_score DESC
                LIMIT ?
            """, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _format_result(self, row: Dict[str, Any], prefix: str = "") -> str:
        text = row["content"]
        trust = row.get("trust_score", 0.0)
        if len(text) > 120:
            cut = text[:120].rfind("。")
            text = text[:cut + 1] if cut > 80 else text[:117] + "..."
        if trust >= 0.8:
            action = self._derive_action(text)
            return f"{prefix}· {text} → {action}" if action else f"{prefix}· {text}"
        return f"{prefix}· {text}"

    # ── 本地嵌入检索（fastembed）──

    def _get_local_embedding(self, text: str) -> Optional[List[float]]:
        """fastembed 本地推理，带 LRU 缓存。"""
        cache_key = text[:80]
        cached = self._emb_cache.get(cache_key)
        if cached:
            return cached[0]

        model = _get_embed_model()
        if model is None:
            return None

        try:
            vec = list(model.embed(text[:800]))[0]
            vec_list = list(vec) if hasattr(vec, '__iter__') else list(vec)
            self._emb_cache[cache_key] = (vec_list, time.monotonic())
            if len(self._emb_cache) > 64:
                oldest = sorted(self._emb_cache.items(), key=lambda x: x[1][1])[:32]
                for k, _ in oldest:
                    del self._emb_cache[k]
            return vec_list
        except Exception as exc:
            logger.debug("本地嵌入推理失败: %s", exc)
            return None

    def _embedding_search(self, query: str, limit: int) -> List[tuple]:
        """语义检索：本地 query embedding → 余弦相似度 → top N。"""
        self._ensure_embedding_column()

        conn = sqlite3.connect(self.db_path)
        embedded = conn.execute(
            "SELECT COUNT(*) FROM facts WHERE embedding IS NOT NULL AND trust_score >= 0.7"
        ).fetchone()[0]
        conn.close()
        if embedded == 0:
            return []

        q_vec = self._get_local_embedding(query)
        if not q_vec:
            return []

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT fact_id, content, trust_score, embedding
                FROM facts
                WHERE trust_score >= 0.7
                  AND length(content) BETWEEN 15 AND 120
                  AND (category IS NULL OR category != 'roleplay')
            """).fetchall()
        finally:
            conn.close()

        rows_dicts = [dict(r) for r in rows]
        scored: List[tuple] = []
        for r in rows_dicts:
            blob = r.get("embedding")
            if not blob:
                continue
            try:
                f_vec = _unpack_vector(blob)
            except Exception:
                continue
            sim = _cosine_similarity(q_vec, f_vec)
            if sim > 0.3:
                formatted = self._format_result(r, prefix="[语义]")
                scored.append((sim, formatted))

        scored.sort(key=lambda x: -x[0])
        return scored[:limit]

    # ── 合并策略 ──

    @staticmethod
    def _merge_results(
        like_formatted: List[str],
        emb_formatted: List[tuple],
        limit: int,
    ) -> List[str]:
        """合并 LIKE + 嵌入结果：去重、交替排列。"""
        def _key(s: str) -> str:
            return s[:30].lstrip("·[语义] ")
        seen: set = set()
        merged: List[str] = []
        li, ei = 0, 0
        like_turn = True
        while len(merged) < limit:
            if like_turn and li < len(like_formatted):
                text = like_formatted[li]; li += 1
                k = _key(text)
                if k not in seen: seen.add(k); merged.append(text)
            elif not like_turn and ei < len(emb_formatted):
                _, text = emb_formatted[ei]; ei += 1
                k = _key(text)
                if k not in seen: seen.add(k); merged.append(text)
            else:
                while li < len(like_formatted):
                    text = like_formatted[li]; li += 1
                    k = _key(text)
                    if k not in seen: seen.add(k); merged.append(text); break
                while ei < len(emb_formatted):
                    _, text = emb_formatted[ei]; ei += 1
                    k = _key(text)
                    if k not in seen: seen.add(k); merged.append(text); break
                if len(merged) < limit and li >= len(like_formatted) and ei >= len(emb_formatted):
                    break
            like_turn = not like_turn
        return merged[:limit]

    # ── embedding 列管理 ──

    def _ensure_embedding_column(self):
        if self._emb_column_ready:
            return
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute("PRAGMA table_info(facts)")
            cols = {row[1] for row in cur.fetchall()}
            if "embedding" not in cols:
                conn.execute("ALTER TABLE facts ADD COLUMN embedding BLOB")
                conn.commit()
            self._emb_column_ready = True
        except Exception as exc:
            logger.warning("添加 embedding 列失败: %s", exc)
        finally:
            conn.close()

    # ── 工具方法 ──

    @staticmethod
    def _tokenize(query: str) -> List[str]:
        if not query or len(query) < 2:
            return [query] if query else []
        tokens = []
        for i in range(len(query) - 1): tokens.append(query[i:i+2])
        for i in range(len(query) - 2): tokens.append(query[i:i+3])
        for i in range(len(query) - 3): tokens.append(query[i:i+4])
        seen = set(); unique = []
        for t in tokens:
            if t not in seen: seen.add(t); unique.append(t)
            if len(unique) >= 20: break
        return unique

    @staticmethod
    def _derive_action(text: str) -> Optional[str]:
        for keyword, action in _ACTION_RULES:
            if keyword in text:
                return action
        return None

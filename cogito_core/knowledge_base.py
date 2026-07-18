"""
knowledge_base.py — 通用 SQLite 知识库检索（本地嵌入版）。

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
    # ── 按事实类别匹配（category 字段，适用于任何知识库）──
    # 这些是通用规则，不依赖具体关键词
    (None, "user_pref", "注意他之前表达过的偏好和习惯"),
    (None, "insight", "引用经验总结时说明来源和可信度"),
    (None, "project", "引用项目决策时给出上下文和版本"),
    (None, "tool", "引用工具经验时说明平台和版本差异"),
]

# ── 从知识库自动生成的关键词规则（启动时扫描）──
# 格式：[("关键词", "行为描述"), ...]
# 由 _build_dynamic_rules() 在 KnowledgeBaseProvider 初始化时填充
_DYNAMIC_RULES: List[tuple] = []


# ── 嵌入相似度门槛（环境变量可覆盖）──
# COGITO_SIM_THRESHOLD=0.25 可调低以召回更多结果
# 默认 0.3，范围 0.0-1.0
try:
    _EMBED_SIM_THRESHOLD = float(os.environ.get("COGITO_SIM_THRESHOLD", "0.3"))
except (ValueError, TypeError):
    _EMBED_SIM_THRESHOLD = 0.3


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


# ── KnowledgeBaseProvider ──


class KnowledgeBaseProvider(KnowledgeProvider):
    """从 Hermes fact_store 检索知识。支持 LIKE + 本地嵌入两路并行检索。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.expanduser(
            "~/.cogito/knowledge_base.db"
        )
        # LRU 缓存：query → (embedding, timestamp)
        self._emb_cache: Dict[str, tuple] = {}
        # 标记 embedding 列是否已就绪
        self._emb_column_ready = False
        # 后台 embedding 生成
        self._embed_bg_done = False
        # 从知识库自动生成关键词规则
        self._build_dynamic_rules()
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
        return "knowledge_base"

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
        category = row.get("category", "")
        if len(text) > 120:
            cut = text[:120].rfind("。")
            text = text[:cut + 1] if cut > 80 else text[:117] + "..."
        if trust >= 0.8:
            action = self._derive_action(text, category)
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
            if sim > _EMBED_SIM_THRESHOLD:
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

    def _build_dynamic_rules(self) -> None:
        """从用户知识库扫描高频关键词，自动生成行为指引规则。

        取信任 ≥ 0.7 的事实，提取 2-4 字中文片段，
        仅保留纯中文词（过滤英文/数字/混合噪声），
        出现 ≥ 3 次的关键词生成规则。
        """
        global _DYNAMIC_RULES
        if not os.path.exists(self.db_path):
            _DYNAMIC_RULES = []
            return

        import re
        _STOP = frozenset({
            "一个", "可以", "这个", "那个", "什么", "怎么", "如何",
            "没有", "不是", "因为", "所以", "但是", "如果", "虽然",
            "已经", "通过", "进行", "使用", "需要", "用于", "还有",
            "之后", "之前", "其中", "相关", "以及", "或者", "不过",
            "对于", "就是", "只是", "还是", "因为", "所以", "这样",
            "可能", "应该", "可以", "必须", "需要", "不会", "不会",
        })

        try:
            conn = sqlite3.connect(self.db_path)
            rows = conn.execute("""
                SELECT content FROM facts
                WHERE trust_score >= 0.7
                  AND length(content) BETWEEN 15 AND 120
                  AND (category IS NULL OR category != 'roleplay')
            """).fetchall()
            conn.close()
        except Exception:
            _DYNAMIC_RULES = []
            return

        from collections import Counter
        counter: Counter = Counter()
        for (content,) in rows:
            text = content[:120]
            # 提取 2-6 字中文片段
            for match in re.finditer(r'[\u4e00-\u9fff]{2,6}', text):
                seg = match.group()
                if seg not in _STOP:
                    counter[seg] += 1

        rules = []
        for kw, cnt in counter.most_common(50):
            if cnt >= 2:  # 出现 2 次即生成规则
                rules.append((kw, f"讨论到「{kw}」时参考此条"))
        _DYNAMIC_RULES = rules[:30]  # 最多 30 条

    @staticmethod
    def _derive_action(text: str, category: str = "") -> Optional[str]:
        # 先按 category 匹配（优先级高）
        if category:
            for kw, cat, action in _ACTION_RULES:
                if kw is None and cat == category:
                    return action
        # 再按动态关键词匹配（从知识库自动生成）
        for kw, action in _DYNAMIC_RULES:
            if kw in text:
                return action
        return None

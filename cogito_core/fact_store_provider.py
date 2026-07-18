"""
fact_store_provider.py — 从 Hermes fact_store 检索知识（v2 语义检索版）。

Two-tier search:
  1. LIKE 关键词匹配（baseline，始终运行）
  2. 语义嵌入检索（自动探测 embedding provider，不可用则静默退回 LIKE）

embedding provider 选择策略：
  1. EMBEDDING_API_KEY / EMBEDDING_BASE_URL / EMBEDDING_MODEL 环境变量 → 专用配置
  2. Hermes config.yaml 的 model.provider → 自动映射已知 embedding 模型
  3. 通用环境变量（DEEPSEEK_API_KEY 等）→ 自动推导
  4. 以上都不行 → 只用 LIKE，不崩溃
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import struct
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import request as urllib_request
from urllib.error import URLError

from .knowledge_provider import KnowledgeProvider

logger = logging.getLogger(__name__)

# ── embedding 模型映射（provider → (model_name)）──
# 这些 provider 的 base URL 与 chat 共用，只需换 model name
_EMBEDDING_MODEL_MAP: Dict[str, str] = {
    "deepseek": "deepseek-embedding",
    "openai": "text-embedding-3-small",
    "zai": "zai-embedding",
    "openrouter": "text-embedding-3-small",
}

# ── 通用 embedding fallback：环境变量 → (base_url, model) ──
_EMBEDDING_FALLBACK: Dict[str, tuple] = {
    "DEEPSEEK_API_KEY": ("https://api.deepseek.com/v1", "deepseek-embedding"),
    "OPENAI_API_KEY": ("https://api.openai.com/v1", "text-embedding-3-small"),
    "OPENROUTER_API_KEY": ("https://openrouter.ai/api/v1", "text-embedding-3-small"),
}

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
    """float32 列表 → 二进制 bytes（小端序，struct 紧凑打包）。"""
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack_vector(data: bytes) -> List[float]:
    """二进制 bytes → float32 列表。"""
    count = len(data) // 4
    return list(struct.unpack(f"<{count}f", data))


# ── FactStoreProvider ──


class FactStoreProvider(KnowledgeProvider):
    """从 Hermes fact_store 检索知识。支持 LIKE + embedding 两路并行检索。"""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.expanduser(
            "~/.hermes/memory_store.db"
        )
        # embedding 配置（自动探测，不可用时为 None）
        self._emb_config: Optional[Dict[str, str]] = self._detect_embedding_config()
        # LRU 缓存：query → (embedding, timestamp)
        self._emb_cache: Dict[str, tuple] = {}
        # 标记 embedding 列是否已就绪
        self._emb_column_ready = False

    # ── 接口 ──

    def name(self) -> str:
        return "fact_store"

    def available(self) -> bool:
        """检查 db 文件存在且可读。"""
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
        """两路并行检索：LIKE + embedding。

        1. LIKE 检索（始终运行，baseline）
        2. embedding 检索（配置可用 + 查询 ≥ 5 字时）
        3. 合并结果：去重、交插、排序
        """
        # ── LIKE 检索 ──
        like_rows = self._like_search(query, limit * 2)
        like_formatted = [self._format_result(r) for r in like_rows]

        # ── embedding 检索 ──
        emb_formatted: List[tuple] = []  # [(score, text)]
        if self._emb_config and len(query) >= 5:
            try:
                emb_formatted = self._embedding_search(query, limit * 2)
            except Exception as exc:
                logger.debug("embedding 检索失败（退回 LIKE）: %s", exc)

        # ── 合并 ──
        return self._merge_results(like_formatted, emb_formatted, limit)

    # ── embedding provider 探测 ──

    @staticmethod
    def _detect_embedding_config() -> Optional[Dict[str, str]]:
        """按优先级探测 embedding API 配置。失败返回 None（只用 LIKE）。"""
        # 策略 1: 专用环境变量
        key = os.environ.get("EMBEDDING_API_KEY", "").strip()
        if key:
            return {
                "api_key": key,
                "base_url": os.environ.get("EMBEDDING_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
                "model": os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small"),
            }

        # 策略 2: 读 Hermes config.yaml
        config = _load_hermes_config()
        provider = (config.get("model", {}) or {}).get("provider", "").lower()
        if provider:
            api_key, base_url = _find_creds(config, provider)
            model = _EMBEDDING_MODEL_MAP.get(provider)
            if api_key and base_url and model:
                return {"api_key": api_key, "base_url": base_url.rstrip("/"), "model": model}

        # 策略 3: 通用环境变量 fallback
        for env_var, (base_url, model) in _EMBEDDING_FALLBACK.items():
            key = os.environ.get(env_var, "").strip()
            if key:
                return {"api_key": key, "base_url": base_url.rstrip("/"), "model": model}

        return None

    # ── embedding API ──

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """调 embedding API，返回向量。缓存命中时直接返回。"""
        cache_key = text[:80]
        cached = self._emb_cache.get(cache_key)
        if cached:
            return cached[0]

        if not self._emb_config:
            return None

        endpoint = f"{self._emb_config['base_url']}/embeddings"
        payload = json.dumps({
            "model": self._emb_config["model"],
            "input": text[:800],  # 截断过长的输入
        }).encode("utf-8")

        try:
            req = urllib_request.Request(
                endpoint, data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._emb_config['api_key']}",
                },
                method="POST",
            )
            with urllib_request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            vector = data["data"][0]["embedding"]
            # 写缓存（最多 64 条）
            self._emb_cache[cache_key] = (vector, time.monotonic())
            if len(self._emb_cache) > 64:
                # 移除最旧的一半
                oldest = sorted(self._emb_cache.items(), key=lambda x: x[1][1])[:32]
                for k, _ in oldest:
                    del self._emb_cache[k]
            return vector
        except (URLError, KeyError, IndexError, json.JSONDecodeError) as exc:
            logger.debug("embedding API 失败: %s", exc)
            return None

    # ── embedding 列管理 ──

    def _ensure_embedding_column(self):
        """确保 facts 表有 embedding 列。幂等。"""
        if self._emb_column_ready:
            return
        conn = sqlite3.connect(self.db_path)
        try:
            # 检查列是否存在
            cur = conn.execute("PRAGMA table_info(facts)")
            cols = {row[1] for row in cur.fetchall()}
            if "embedding" not in cols:
                conn.execute("ALTER TABLE facts ADD COLUMN embedding BLOB")
                conn.commit()
                logger.info("facts 表已添加 embedding 列")
            self._emb_column_ready = True
        except Exception as exc:
            logger.warning("添加 embedding 列失败（LIKE-only 模式）: %s", exc)
        finally:
            conn.close()

    def _batch_embed_facts(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """为无 embedding 的事实批量补充向量（最多 50 条/批）。"""
        self._ensure_embedding_column()
        need_embed = [r for r in rows if not r.get("embedding")]
        if not need_embed:
            return rows

        conn = sqlite3.connect(self.db_path)
        try:
            for r in need_embed[:50]:
                vec = self._get_embedding(r["content"][:500])
                if vec:
                    blob = _pack_vector(vec)
                    conn.execute(
                        "UPDATE facts SET embedding = ? WHERE rowid = ?",
                        (blob, r["rowid"]),
                    )
            conn.commit()
            logger.debug("批量生成了 %d 条 embedding", min(len(need_embed), 50))
        except Exception as exc:
            logger.debug("批量生成 embedding 失败: %s", exc)
        finally:
            conn.close()

        # 重新读取（含新 embedding）
        conn2 = sqlite3.connect(self.db_path)
        conn2.row_factory = sqlite3.Row
        ids = tuple(r["rowid"] for r in rows)
        if len(ids) == 1:
            ids = (ids[0],)
        cur = conn2.execute(
            f"SELECT rowid, content, trust_score, embedding FROM facts WHERE rowid IN ({','.join('?'*len(ids))})",
            ids,
        )
        refreshed = [dict(r) for r in cur.fetchall()]
        conn2.close()
        return refreshed

    # ── LIKE 检索 ──

    def _like_search(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """LIKE 关键词检索（原 search 逻辑，返回原始行数据）。"""
        self._ensure_embedding_column()
        keywords = self._tokenize(query)
        if not keywords:
            return []

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            like_clauses = " OR ".join(["content LIKE ?"] * len(keywords))
            params = [f"%{kw}%" for kw in keywords] + [limit]
            rows = conn.execute(
                f"""
                SELECT rowid, content, trust_score, embedding
                FROM facts
                WHERE ({like_clauses})
                  AND trust_score >= 0.7
                  AND length(content) BETWEEN 15 AND 120
                  AND (category IS NULL OR category != 'roleplay')
                ORDER BY trust_score DESC
                LIMIT ?
                """, params
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _format_result(self, row: Dict[str, Any], prefix: str = "") -> str:
        """将原始行格式化为注入文本。"""
        text = row["content"]
        trust = row.get("trust_score", 0.0)

        if len(text) > 120:
            cut = text[:120].rfind("。")
            text = text[:cut + 1] if cut > 80 else text[:117] + "..."

        action = self._derive_action(text) if trust >= 0.8 else None
        if action:
            text = f"{prefix}· {text} → {action}"
        else:
            text = f"{prefix}· {text}"
        return text

    # ── embedding 检索 ──

    def _embedding_search(self, query: str, limit: int) -> List[tuple]:
        """语义检索：query embedding → 余弦相似度 → top N。

        Returns:
            [(score, formatted_text), ...]
        """
        self._ensure_embedding_column()

        q_vec = self._get_embedding(query)
        if not q_vec:
            return []

        # 加载所有可命中事实（含 embedding 列）
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("""
                SELECT rowid, content, trust_score, embedding
                FROM facts
                WHERE trust_score >= 0.7
                  AND length(content) BETWEEN 15 AND 120
                  AND (category IS NULL OR category != 'roleplay')
            """).fetchall()
        finally:
            conn.close()

        if not rows:
            return []

        rows_dicts = [dict(r) for r in rows]

        # 批量为无 embedding 的事实生成向量
        rows_dicts = self._batch_embed_facts(rows_dicts)

        # 余弦相似度排序
        scored: List[tuple] = []  # (score, formatted_text, content)
        for r in rows_dicts:
            blob = r.get("embedding")
            if not blob:
                continue
            try:
                f_vec = _unpack_vector(blob)
            except Exception:
                continue
            sim = _cosine_similarity(q_vec, f_vec)
            if sim > 0.3:  # 相似度门槛，过滤明显不相关
                formatted = self._format_result(r, prefix="[语义]")
                scored.append((sim, formatted, r["content"]))

        scored.sort(key=lambda x: -x[0])
        return scored[:limit]

    # ── 合并策略 ──

    @staticmethod
    def _merge_results(
        like_formatted: List[str],
        emb_formatted: List[tuple],
        limit: int,
    ) -> List[str]:
        """合并 LIKE + embedding 结果：去重、交替排列、保序。

        Args:
            like_formatted: LIKE 检索格式化文本列表
            emb_formatted: embedding 检索结果 [(score, text), ...]
            limit: 最终返回条数

        Returns:
            格式化后的文本列表
        """
        # 去重：短内容前缀相同只保留一条
        seen: set = set()
        merged: List[str] = []
        li, ei = 0, 0
        like_turn = True

        def _key(s: str) -> str:
            return s[:30].lstrip("·[语义] ")

        while len(merged) < limit:
            if like_turn and li < len(like_formatted):
                text = like_formatted[li]
                li += 1
                k = _key(text)
                if k not in seen:
                    seen.add(k)
                    merged.append(text)
            elif not like_turn and ei < len(emb_formatted):
                _, text = emb_formatted[ei]
                ei += 1
                k = _key(text)
                if k not in seen:
                    seen.add(k)
                    merged.append(text)
            else:
                # 某一端耗尽，从另一端补充
                if li < len(like_formatted):
                    text = like_formatted[li]
                    li += 1
                    k = _key(text)
                    if k not in seen:
                        seen.add(k)
                        merged.append(text)
                elif ei < len(emb_formatted):
                    _, text = emb_formatted[ei]
                    ei += 1
                    k = _key(text)
                    if k not in seen:
                        seen.add(k)
                        merged.append(text)
                else:
                    break
            like_turn = not like_turn  # 交替

        return merged[:limit]

    # ── 工具方法 ──

    @staticmethod
    def _tokenize(query: str) -> List[str]:
        """将查询拆为 2-4 字关键词片段。"""
        if not query or len(query) < 2:
            return [query] if query else []

        tokens = []
        for i in range(len(query) - 1):
            tokens.append(query[i:i+2])
        for i in range(len(query) - 2):
            tokens.append(query[i:i+3])
        for i in range(len(query) - 3):
            tokens.append(query[i:i+4])

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
        """基于事实内容的关键词匹配行为建议。"""
        for keyword, action in _ACTION_RULES:
            if keyword in text:
                return action
        return None


# ── Hermes config 读取工具 ──


def _load_hermes_config() -> Dict[str, Any]:
    """读取 Hermes config.yaml，返回解析后的 dict。"""
    config_path = os.path.join(Path.home(), ".hermes", "config.yaml")
    if not os.path.exists(config_path):
        return {}
    try:
        import yaml
        with open(config_path, "r") as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        return {}
    except Exception:
        return {}


def _find_creds(config: Dict[str, Any], provider: str) -> tuple:
    """从 Hermes config 查找 provider 的 API Key + base_url。

    策略同 hermes_adapter.py 的 _find_api_key（简化版）。
    """
    provider_lower = provider.lower()

    # custom_providers 数组
    for cp in (config.get("custom_providers", []) or []):
        cp_name = (cp.get("name") or "").lower()
        if cp_name == provider_lower or cp_name == provider_lower.replace("custom:", "", 1):
            key = cp.get("api_key", "")
            url = cp.get("base_url", "")
            if key:
                return key, url

    # providers dict
    pconfig = (config.get("providers", {}) or {}).get(provider, {})
    if pconfig:
        key = pconfig.get("api_key", "")
        if key:
            return key, pconfig.get("base_url", "")

    # 环境变量
    key = os.environ.get(f"{provider.upper()}_API_KEY", "")
    if key:
        return key, ""

    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        return key, ""

    return "", ""

"""
persistence.py —— 统一持久化层。

管理 ~/.cogito/ 目录下的所有状态文件：
- state.json          — 引擎运行时状态
- focus_history.jsonl — 焦点栈历史
- emotion_history.jsonl — 情感记录历史
- narrative.jsonl     — 叙事记忆
- session_reflections.jsonl — 会话反射

平台无关 —— 零外部依赖（仅 stdlib）。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── 配置 ──

_COGITO_HOME = Path(
    os.environ.get("COGITO_HOME", os.path.expanduser("~/.cogito"))
)

MAX_FOCUS_HISTORY = 200
MAX_EMOTION_HISTORY = 2000
MAX_NARRATIVE = 200
MAX_REFLECTIONS = 500


def set_cogito_home(path: str) -> None:
    """重设 cogito 持久化目录。"""
    global _COGITO_HOME
    _COGITO_HOME = Path(path)


def get_cogito_home() -> Path:
    """获取 cogito 持久化目录。"""
    _COGITO_HOME.mkdir(parents=True, exist_ok=True)
    return _COGITO_HOME


# ── 通用 JSONL 工具 ──

def _append_jsonl(filename: str, entry: Dict[str, Any]) -> Path:
    """追加一行 JSON 到 JSONL 文件。"""
    filepath = get_cogito_home() / filename
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("写入 %s 失败: %s", filename, exc)
    return filepath


def _read_jsonl(filename: str) -> List[Dict[str, Any]]:
    """读取 JSONL 文件的所有行。"""
    filepath = get_cogito_home() / filename
    if not filepath.exists():
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [json.loads(line) for line in lines if line.strip()]
    except Exception as exc:
        logger.warning("读取 %s 失败: %s", exc)
        return []


def _trim_jsonl(filename: str, max_lines: int) -> None:
    """修剪 JSONL 文件到最近 N 行。"""
    filepath = get_cogito_home() / filename
    try:
        if filepath.stat().st_size > max_lines * 300:
            with open(filepath, "r") as f:
                lines = f.readlines()
            if len(lines) > max_lines:
                with open(filepath, "w") as f:
                    f.writelines(lines[-max_lines:])
    except Exception:
        pass


# ── 引擎状态 ──

STATE_FILE = "state.json"


def save_state(state: Dict[str, Any]) -> None:
    """保存引擎运行时状态到 JSON 文件。

    Args:
        state: 状态字典（可序列化内容）
    """
    filepath = get_cogito_home() / STATE_FILE
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **state,
    }
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.error("保存引擎状态失败: %s", exc)


def load_state() -> Dict[str, Any]:
    """加载引擎运行时状态。

    Returns:
        状态字典（空 dict 表示无状态文件）。
    """
    filepath = get_cogito_home() / STATE_FILE
    if not filepath.exists():
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("加载引擎状态失败: %s", exc)
        return {}


# ── 焦点历史 ──

FOCUS_HISTORY_FILE = "focus_history.jsonl"


def save_focus_history(stack: List[Dict[str, Any]]) -> None:
    """保存焦点栈到焦点历史 JSONL。

    每条记录：
        {
            "ts": ISO8601,
            "topics": ["话题1", "话题2"],
            "depth": int,
        }
    """
    topics = []
    for frame in stack:
        if isinstance(frame.get("topic"), list):
            topics.append(", ".join(frame["topic"]))

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "topics": topics,
        "depth": len(stack),
    }
    _append_jsonl(FOCUS_HISTORY_FILE, entry)
    _trim_jsonl(FOCUS_HISTORY_FILE, MAX_FOCUS_HISTORY)


def save_focus_summary(summary: str) -> None:
    """保存会话焦点摘要（独立行）。"""
    if not summary:
        return
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "summary": summary.strip(),
        "type": "session_summary",
    }
    _append_jsonl(FOCUS_HISTORY_FILE, entry)


def load_focus_history(k: int = 5) -> List[Dict[str, Any]]:
    """加载最近 k 条焦点历史。"""
    entries = _read_jsonl(FOCUS_HISTORY_FILE)
    return entries[-k:] if entries else []


# ── 情感历史 ──

EMOTION_HISTORY_FILE = "emotion_history.jsonl"


def save_emotion_history(
    label: str,
    sentiment: float,
    confidence: float,
    label_cn: str = "中性",
    text_excerpt: str = "",
) -> None:
    """保存情感检测结果到情感历史 JSONL。

    Args:
        label: 情感标签（positive/negative/neutral）
        sentiment: 情感极性 0.0-1.0
        confidence: 置信度 0.0-1.0
        label_cn: 中文标签（正面/负面/中性）
        text_excerpt: 文本摘录
    """
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "label_cn": label_cn,
        "sentiment": round(sentiment, 4),
        "confidence": round(confidence, 4),
        "text_excerpt": text_excerpt[:80] if text_excerpt else "",
    }
    _append_jsonl(EMOTION_HISTORY_FILE, entry)
    _trim_jsonl(EMOTION_HISTORY_FILE, MAX_EMOTION_HISTORY)


def load_emotion_history(k: int = 10) -> List[Dict[str, Any]]:
    """加载最近 k 条情感历史。"""
    entries = _read_jsonl(EMOTION_HISTORY_FILE)
    return entries[-k:] if entries else []


# ── 叙事记忆（委托给 narrative_store） ──

NARRATIVE_FILE = "narrative.jsonl"


def save_narrative(entry: Dict[str, Any]) -> None:
    """保存一条叙事条目。

    Args:
        entry: 叙事条目 dict（含 timestamp/summary/insights 等）
    """
    _append_jsonl(NARRATIVE_FILE, entry)
    _trim_jsonl(NARRATIVE_FILE, MAX_NARRATIVE)


def load_narrative(k: int = 3) -> List[Dict[str, Any]]:
    """加载最近 k 条叙事记忆。"""
    entries = _read_jsonl(NARRATIVE_FILE)
    return entries[-k:] if entries else []


# ── 会话反射 ──

REFLECTIONS_FILE = "session_reflections.jsonl"


def save_session_reflection(
    session_id: str = "",
    tick_count: int = 0,
    focus_depth: int = 0,
    topic_keywords: Optional[List[str]] = None,
    message_count: int = 0,
    rounds: int = 0,
) -> None:
    """保存一条会话反射条目。

    Args:
        session_id: 会话 ID
        tick_count: TICK 计数
        focus_depth: 焦点栈深度
        topic_keywords: 焦点话题列表
        message_count: 消息数
        rounds: 对话轮数
    """
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "trigger": "termination",
        "tick_count": tick_count,
        "focus_depth": focus_depth,
        "topic_keywords": topic_keywords or [],
        "message_count": message_count,
        "rounds": rounds,
    }
    _append_jsonl(REFLECTIONS_FILE, entry)
    _trim_jsonl(REFLECTIONS_FILE, MAX_REFLECTIONS)


def load_session_reflections(k: int = 3) -> List[Dict[str, Any]]:
    """加载最近 k 条会话反射。"""
    entries = _read_jsonl(REFLECTIONS_FILE)
    return entries[-k:] if entries else []


# ── 时间范围查询（按天过滤）──


def _filter_since(entries: List[Dict[str, Any]], days: int, ts_field: str = "ts") -> List[Dict[str, Any]]:
    """过滤最近 N 天的条目。`days <= 0` 时返回全量。"""
    if days <= 0:
        return entries
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    results = []
    for e in entries:
        ts_str = e.get(ts_field) or e.get("timestamp", "")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if ts >= cutoff:
                results.append(e)
        except (ValueError, TypeError):
            continue
    return results


def load_emotion_since(days: int = 7) -> List[Dict[str, Any]]:
    """加载最近 N 天的情绪历史。"""
    return _filter_since(_read_jsonl(EMOTION_HISTORY_FILE), days, ts_field="ts")


def load_narrative_since(days: int = 7) -> List[Dict[str, Any]]:
    """加载最近 N 天的叙事记忆。"""
    return _filter_since(_read_jsonl(NARRATIVE_FILE), days, ts_field="timestamp")


def load_focus_since(days: int = 7) -> List[Dict[str, Any]]:
    """加载最近 N 天的焦点历史。"""
    return _filter_since(_read_jsonl(FOCUS_HISTORY_FILE), days, ts_field="ts")


def load_reflections_since(days: int = 30) -> List[Dict[str, Any]]:
    """加载最近 N 天的会话反射。"""
    return _filter_since(_read_jsonl(REFLECTIONS_FILE), days, ts_field="ts")

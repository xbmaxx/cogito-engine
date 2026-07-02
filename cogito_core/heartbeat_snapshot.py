"""
heartbeat_snapshot.py —— 心跳快照持久化。

每次模式切换写入一条 JSONL 记录，上限 200 条 FIFO 截断。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

SNAPSHOT_PATH = os.path.expanduser("~/.hermes/cogito/heartbeat_snapshots.jsonl")
MAX_SNAPSHOTS = 200


def save_snapshot(result: Dict[str, Any]) -> None:
    """追加一条快照记录。超出上限触发 FIFO 截断。"""
    try:
        os.makedirs(os.path.dirname(SNAPSHOT_PATH), exist_ok=True)

        record = {
            "snapshot_id": result.get("snapshot_id", ""),
            "ts": datetime.now(timezone.utc).isoformat(),
            "tick": (
                int(result.get("snapshot_id", "0-").split("-")[0])
                if result.get("snapshot_id")
                else 0
            ),
            "mode": result.get("mode", ""),
            "previous_mode": result.get("previous_mode", ""),
            "trigger": result.get("trigger", ""),
            "expression": result.get("expression", ""),
            "locked": result.get("locked", False),
        }

        # 读已有记录
        records: List[Dict[str, Any]] = []
        if os.path.exists(SNAPSHOT_PATH):
            with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
                records = [
                    json.loads(line)
                    for line in f
                    if line.strip()
                ]

        records.append(record)

        # FIFO 截断
        if len(records) > MAX_SNAPSHOTS:
            records = records[-MAX_SNAPSHOTS:]

        with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    except Exception as exc:
        logger.warning("心跳快照写入失败: %s", exc)


def load_recent(n: int = 10) -> List[Dict[str, Any]]:
    """加载最近 N 条快照记录。"""
    try:
        if not os.path.exists(SNAPSHOT_PATH):
            return []
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            records = [
                json.loads(line)
                for line in f
                if line.strip()
            ]
        return records[-n:]
    except Exception as exc:
        logger.warning("心跳快照读取失败: %s", exc)
        return []


def get_timeline_text() -> str:
    """生成可注入的心跳历程摘要。"""
    records = load_recent(5)
    if not records:
        return ""
    modes = [r["mode"] for r in records]
    unique: List[str] = list(dict.fromkeys(modes))  # 去重保序
    return " → ".join(unique)

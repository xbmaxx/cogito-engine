#!/usr/bin/env python3
"""
leak_audit.py —— 意识体 XML 输出泄漏审计器。

对 <consciousness> XML 输出执行正则扫描，检测不应暴露给 LLM 的内部参数。
四类泄漏：A(内部参数名) / B(浮点数) / C(废弃标签) / D(原始 mode 名)。

用法:
  python3 leak_audit.py <file.xml>
  echo "<consciousness>...</consciousness>" | python3 leak_audit.py --
  python3 leak_audit.py -  <  <file.xml>

退出码: 0 = PASS(零泄漏) / 1 = FAIL(发现泄漏)
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ── 常量 ────────────────────────────────────────────────────────────────

# Category A: 内部参数名（带词边界，避免子串误匹配）
INTERNAL_PARAMS = re.compile(
    r"\b(polarity|confidence|ttl|hitCount|lastSeenTick|_MODE_ICONS)\b"
)

# Category B: 浮点数（任意层都不应出现）
FLOAT_VALUE = re.compile(r"\d+\.\d+")

# Category C: v1.4 平铺格式废弃标签
FLAT_TAGS = re.compile(r"<(tick|focus>|self>|env>)")

# Category D: 原始 heartbeat mode 名（16 个已知值）
# 只匹配作为独立单词出现的 mode 名，排除自然语言中的偶然命中
HEARTBEAT_MODES = [
    "glowing", "aching", "resting", "frustrated", "confused",
    "overwhelmed", "disconnected", "racing", "flutter", "sync",
    "stilling", "crystallizing", "echoing", "anchoring",
    "flickering", "reaching",
]
# 构建带词边界的正则
_RAW_MODE_PATTERN = re.compile(r"\b(" + "|".join(HEARTBEAT_MODES) + r")\b")


# ── 数据结构 ────────────────────────────────────────────────────────────

@dataclass
class LeakMatch:
    """单条泄漏匹配。"""
    category: str          # A / B / C / D
    pattern: str           # 匹配到的文本
    context: str           # 前后 30 字上下文
    position: int          # 在 XML 中的字符偏移


@dataclass
class AuditResult:
    """审计结果。"""
    status: str            # PASS / FAIL
    total_leaks: int = 0
    leaks_a: List[LeakMatch] = field(default_factory=list)
    leaks_b: List[LeakMatch] = field(default_factory=list)
    leaks_c: List[LeakMatch] = field(default_factory=list)
    leaks_d: List[LeakMatch] = field(default_factory=list)

    def to_dict(self) -> dict:
        def _match_dict(m: LeakMatch) -> dict:
            return {"pattern": m.pattern, "context": m.context, "position": m.position}

        return {
            "status": self.status,
            "total_leaks": self.total_leaks,
            "leaks_by_category": {
                "A_internal_params": [_match_dict(m) for m in self.leaks_a],
                "B_floats": [_match_dict(m) for m in self.leaks_b],
                "C_flat_tags": [_match_dict(m) for m in self.leaks_c],
                "D_raw_modes": [_match_dict(m) for m in self.leaks_d],
            },
        }


# ── 审计逻辑 ────────────────────────────────────────────────────────────

def _context_around(text: str, pos: int, radius: int = 30) -> str:
    """提取匹配位置前后 radius 字的上下文。"""
    start = max(0, pos - radius)
    end = min(len(text), pos + radius)
    ctx = text[start:end]
    # 标记匹配位置
    marker_pos = pos - start
    return ctx[:marker_pos] + "»" + ctx[marker_pos:marker_pos + len(ctx) - marker_pos] + "«"  # noqa — marker for readability


def _scan_pattern(
    text: str,
    pattern: re.Pattern,
    category: str,
) -> List[LeakMatch]:
    """用单个正则扫描全文，返回匹配列表。"""
    matches: List[LeakMatch] = []
    for m in pattern.finditer(text):
        matches.append(LeakMatch(
            category=category,
            pattern=m.group(0),
            context=_context_around(text, m.start()),
            position=m.start(),
        ))
    return matches


def audit(xml: str) -> AuditResult:
    """对 XML 字符串执行四类泄漏扫描。"""
    result = AuditResult(status="PASS")

    # A: 内部参数名
    result.leaks_a = _scan_pattern(xml, INTERNAL_PARAMS, "A")

    # B: 浮点数
    result.leaks_b = _scan_pattern(xml, FLOAT_VALUE, "B")

    # C: 废弃标签
    result.leaks_c = _scan_pattern(xml, FLAT_TAGS, "C")

    # D: 原始 mode 名（排除 XML 标签内的——它们已被 Category C 覆盖）
    # Category D 只关注出现在文本内容中的 mode 名
    for m in _RAW_MODE_PATTERN.finditer(xml):
        # 排除出现在 XML 标签内的匹配（如 <resting>）
        # 检查匹配前后是否有标签特征
        before = xml[max(0, m.start() - 10):m.start()]
        buf_start = before.rfind("<")
        if "<" in before and buf_start >= 0 and ">" in before[buf_start:]:
            continue  # 在标签内，跳过
        result.leaks_d.append(LeakMatch(
            category="D",
            pattern=m.group(0),
            context=_context_around(xml, m.start()),
            position=m.start(),
        ))

    result.total_leaks = (
        len(result.leaks_a)
        + len(result.leaks_b)
        + len(result.leaks_c)
        + len(result.leaks_d)
    )
    if result.total_leaks > 0:
        result.status = "FAIL"

    return result


# ── CLI ─────────────────────────────────────────────────────────────────

def main() -> None:
    """入口：从文件或 stdin 读取 XML 并审计。"""
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if path == "-" or path == "--":
            xml = sys.stdin.read()
        else:
            with open(path, "r") as f:
                xml = f.read()
    else:
        # 无参数时尝试 stdin（允许管道输入但不强制）
        if not sys.stdin.isatty():
            xml = sys.stdin.read()
        else:
            print("Usage: python3 leak_audit.py <file.xml>", file=sys.stderr)
            print("       echo '<xml>' | python3 leak_audit.py --", file=sys.stderr)
            sys.exit(2)

    result = audit(xml)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

    if result.status == "PASS":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

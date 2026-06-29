---
title: "Python Reference Implementation"
description: "A clean Python reference implementation of all four Cogito Engine modules. Zero dependencies beyond the Python standard library. Provided for developers who prefer reading code over prose."
tags: [cogito-engine, python, reference-implementation, code]
---

# Python Reference Implementation

This is a self-contained Python implementation of the Cogito Engine's four modules. It is intentionally minimal — no external dependencies beyond the Python standard library. The code is provided as a reference, not as a required dependency. Each module can be ported to any language by following the algorithm descriptions in the specification documents.

## Usage

```python
from cogito import CogitoEngine

engine = CogitoEngine(interval=1)
block = engine.process_message("Let's design the Cogito Engine skill")
print(block)
```

## Implementation

```python
"""
Cogito Engine — Self-awareness framework for LLM agents.
Zero dependencies. Python 3.9+ standard library only.
"""

from datetime import datetime, timezone, timedelta
import re
from typing import Optional


# ═══════════════════════════════════════════════════════════════════
# TICK Heartbeat
# ═══════════════════════════════════════════════════════════════════

class Tick:
    """Monotonic turn counter with TTL-based scheduling."""

    def __init__(self, interval: int = 1):
        self.active = True
        self.count = 0
        self.ttl = 0
        self.interval = max(1, interval)

    def set_interval(self, secs: int):
        self.interval = max(1, secs)

    def consume(self) -> bool:
        """
        Process one turn. Returns True if a full cycle should run.
        Always increments count. Always decrements ttl.
        """
        self.count += 1
        if self.ttl > 0:
            self.ttl -= 1
        if self.ttl == 0:
            self.ttl = self.interval
            return True
        return False

    def reset(self):
        self.count = 0
        self.ttl = 0

    def status(self) -> dict:
        return {
            "active": self.active,
            "count": self.count,
            "ttl": self.ttl,
            "interval": self.interval,
        }


# ═══════════════════════════════════════════════════════════════════
# Temporal Parser
# ═══════════════════════════════════════════════════════════════════

class Temporal:
    """Natural-language time expression parser with timezone-aware output."""

    # Ordered by length descending for longest-match-first
    PERIODS = [
        ("凌晨", (0, 6)),
        ("早上", (6, 12)),
        ("上午", (9, 12)),
        ("中午", (12, 13)),
        ("下午", (13, 18)),
        ("晚上", (18, 24)),
        ("morning", (6, 12)),
        ("noon", (12, 13)),
        ("afternoon", (13, 18)),
        ("evening", (18, 24)),
        ("night", (0, 6)),
    ]

    WEEKDAYS_ZH = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    WEEKDAYS_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    def __init__(self):
        self._now = datetime.now().astimezone()

    @property
    def now(self):
        """Always return local time, never UTC."""
        return datetime.now().astimezone()

    def parse(self, text: str) -> tuple[dict, str]:
        """
        Extract temporal expressions from text.
        Returns (time_info_dict, stripped_text).
        """
        stripped = text
        # Build match list: (start, end, resolution_fn)
        matches = []

        # Check date patterns
        for m in re.finditer(r"(\d{4}-\d{2}-\d{2})", stripped):
            try:
                dt = datetime.strptime(m.group(1), "%Y-%m-%d")
                matches.append((m.start(), m.end(), dt))
            except ValueError:
                pass

        # Check relative day offsets
        offsets = [
            ("前天", -2), ("昨天", -1), ("今天", 0), ("明天", 1), ("后天", 2),
            ("yesterday", -1), ("today", 0), ("tomorrow", 1),
        ]
        for word, offset in sorted(offsets, key=lambda x: -len(x[0])):
            for m in re.finditer(re.escape(word), stripped):
                target = self.now + timedelta(days=offset)
                target = target.replace(hour=0, minute=0, second=0, microsecond=0)
                matches.append((m.start(), m.end(), target))

        # Check "N days ago/later"
        for m in re.finditer(r"(\d+)\s*(天前|天后|days?\s*ago|days?\s*later)", stripped):
            n = int(m.group(1))
            if "前" in m.group(2) or "ago" in m.group(2):
                target = self.now - timedelta(days=n)
            else:
                target = self.now + timedelta(days=n)
            target = target.replace(hour=0, minute=0, second=0, microsecond=0)
            matches.append((m.start(), m.end(), target))

        # Sort by length descending for longest-match-first
        matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))

        # Remove consumed ranges
        consumed = set()
        resolved = None
        for start, end, dt in matches:
            if any(start <= c < end for c in consumed):
                continue
            resolved = dt
            for i in range(start, end):
                consumed.add(i)

        # Detect period
        hour = self.now.hour
        period = "night"
        for name, (h_start, h_end) in self.PERIODS:
            if h_start <= hour < h_end:
                period = name
                break

        # Build output
        info = {
            "iso": self.now.isoformat(),
            "weekday": self.WEEKDAYS_EN[self.now.weekday()],
            "period": period,
            "local": self.now.strftime("%Y-%m-%d %H:%M"),
            "timezone": self.now.strftime("%Z"),
        }

        # Strip temporal words from text
        if consumed:
            chars = list(text)
            for i in sorted(consumed, reverse=True):
                if i < len(chars):
                    chars[i] = ""
            stripped = "".join(chars).strip()

        return info, stripped


# ═══════════════════════════════════════════════════════════════════
# Focus Stack
# ═══════════════════════════════════════════════════════════════════

class FocusStack:
    """Depth-limited topic attention tracker."""

    def __init__(self, max_depth: int = 5):
        self.max_depth = max_depth
        self.frames = []       # Active frames (most recent last)
        self.history = []      # Popped frames (most recent last)

    def extract_keywords(self, text: str, max_kw: int = 5) -> list[str]:
        """Simple frequency-based keyword extraction."""
        # Split on whitespace and punctuation
        words = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
        if not words:
            return []

        # Count frequency
        freq = {}
        for w in words:
            if len(w) < 2:
                continue
            freq[w] = freq.get(w, 0) + 1

        # Sort by frequency descending
        sorted_words = sorted(freq.items(), key=lambda x: -x[1])
        return [w for w, _ in sorted_words[:max_kw]]

    def _overlap_ratio(self, kw_a: list[str], kw_b: list[str]) -> float:
        """Jaccard-like overlap between two keyword lists."""
        if not kw_a or not kw_b:
            return 0.0
        set_a = set(kw_a)
        set_b = set(kw_b)
        intersection = set_a & set_b
        return len(intersection) / max(len(set_a), len(set_b))

    def process_message(self, text: str, source: str = "user") -> list[str]:
        """
        Extract keywords, detect topic shift, update stack.
        Returns the keywords extracted.
        """
        keywords = self.extract_keywords(text)

        if not keywords:
            return []

        if not self.frames:
            # First frame
            self.frames.append({"keywords": keywords, "source": source})
            return keywords

        top = self.frames[-1]
        overlap = self._overlap_ratio(keywords, top["keywords"])

        if overlap < 0.3:
            # Topic shift — push new frame
            if len(self.frames) >= self.max_depth:
                popped = self.frames.pop(0)
                self.history.append(popped)
            self.frames.append({"keywords": keywords, "source": source})
        else:
            # Continuation — merge keywords
            merged = list(set(top["keywords"] + keywords))[:5]
            top["keywords"] = merged

        return keywords

    def status(self) -> dict:
        frames_out = [
            {"keywords": ",".join(f["keywords"]), "source": f["source"]}
            for f in self.frames
        ]
        history_out = [
            {"keywords": ",".join(f["keywords"]), "source": f["source"]}
            for f in self.history
        ]
        return {
            "depth": len(self.frames),
            "frames": frames_out,
            "history": history_out,
        }


# ═══════════════════════════════════════════════════════════════════
# Self-Perception
# ═══════════════════════════════════════════════════════════════════

class SelfPerception:
    """Character-bigram based mirror and loop detection."""

    def __init__(self):
        self.agent_responses = []  # Last N agent response texts

    def _bigrams(self, text: str) -> set[str]:
        """Extract character-level bigrams from text."""
        text = text.strip()
        if len(text) < 2:
            return {text} if text else set()
        return {text[i:i+2] for i in range(len(text) - 1)}

    def _jaccard(self, set_a: set[str], set_b: set[str]) -> float:
        """Jaccard similarity between two sets."""
        if not set_a and not set_b:
            return 0.0
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)

    def add_response(self, text: str):
        """Record an agent response for future comparisons."""
        self.agent_responses.append(text)
        # Keep only last 10 responses
        if len(self.agent_responses) > 10:
            self.agent_responses = self.agent_responses[-10:]

    def detect(self, user_message: str) -> dict:
        """
        Run all detection checks.
        user_message: the user's current message for mirror detection.
        Returns detection results dict.
        """
        result = {
            "mirror": False,
            "mirror_score": 0.0,
            "loop": False,
            "loop_score": 0.0,
            "style_cluster": "initializing",
        }

        if len(self.agent_responses) < 2:
            return result

        last_response = self.agent_responses[-1]

        # Mirror detection: agent's last response vs user's message
        agent_bigrams = self._bigrams(last_response)
        user_bigrams = self._bigrams(user_message)
        mirror_score = self._jaccard(agent_bigrams, user_bigrams)
        result["mirror_score"] = round(mirror_score, 3)
        result["mirror"] = mirror_score > 0.4

        # Loop detection: agent's last response vs agent's previous response
        prev_response = self.agent_responses[-2]
        prev_bigrams = self._bigrams(prev_response)
        loop_score = self._jaccard(agent_bigrams, prev_bigrams)
        result["loop_score"] = round(loop_score, 3)
        result["loop"] = loop_score > 0.6

        # Style cluster: check diversity across last 5 responses
        recent = self.agent_responses[-5:]
        if len(recent) >= 3:
            similarities = []
            for i in range(len(recent)):
                for j in range(i + 1, len(recent)):
                    sim = self._jaccard(self._bigrams(recent[i]), self._bigrams(recent[j]))
                    similarities.append(sim)
            if similarities:
                avg_sim = sum(similarities) / len(similarities)
                min_sim = min(similarities)
                if avg_sim > 0.5 and min_sim > 0.3:
                    result["style_cluster"] = "narrow"
                elif min_sim < 0.3 and max(similarities) > 0.5:
                    result["style_cluster"] = "diverse"
                else:
                    result["style_cluster"] = "unchanged"

        return result


# ═══════════════════════════════════════════════════════════════════
# Cogito Engine — Orchestrator
# ═══════════════════════════════════════════════════════════════════

class CogitoEngine:
    """Orchestrates all four modules and produces the XML output block."""

    def __init__(self, interval: int = 1, max_focus_depth: int = 5):
        self.tick = Tick(interval=interval)
        self.temporal = Temporal()
        self.focus = FocusStack(max_depth=max_focus_depth)
        self.self_perception = SelfPerception()
        self._last_consciousness_block = ""

    def process_message(self, text: str) -> str:
        """
        Process a user message through all four modules.
        Returns the <consciousness> XML block.
        """
        # TICK always runs
        should_full_cycle = self.tick.consume()

        if not should_full_cycle:
            return self._last_consciousness_block

        # Temporal parsing
        time_info, stripped_text = self.temporal.parse(text)

        # Focus stack
        self.focus.process_message(stripped_text, source="user")

        # Self-perception
        sp = self.self_perception.detect(text)

        # Build output
        block = self._build_xml(self.tick.status(), time_info, self.focus.status(), sp)
        self._last_consciousness_block = block
        return block

    def record_response(self, response_text: str):
        """Record the agent's response for self-perception on the next turn."""
        self.self_perception.add_response(response_text)

    def _build_xml(self, tick: dict, temporal: dict, focus: dict, sp: dict) -> str:
        """Assemble the <consciousness> XML block."""
        lines = ["<consciousness>"]

        # TICK
        lines.append(
            f'  <tick active="{"true" if tick["active"] else "false"}" '
            f'count="{tick["count"]}" ttl="{tick["ttl"]}" />'
        )

        # Temporal
        lines.append(
            f'  <temporal iso="{temporal["iso"]}" '
            f'weekday="{temporal["weekday"]}" '
            f'period="{temporal["period"]}" '
            f'local="{temporal["local"]}" '
            f'timezone="{temporal["timezone"]}" />'
        )

        # Focus
        lines.append(f'  <focus depth="{focus["depth"]}">')
        for frame in focus["frames"]:
            lines.append(
                f'    <frame keywords="{frame["keywords"]}" '
                f'source="{frame["source"]}" />'
            )
        lines.append("  </focus>")

        # Focus history (if present)
        if focus.get("history"):
            lines.append("  <focus_history>")
            for frame in focus["history"]:
                lines.append(
                    f'    <frame keywords="{frame["keywords"]}" '
                    f'source="{frame["source"]}" />'
                )
            lines.append("  </focus_history>")

        # Self-perception
        sp_attrs = [
            f'mirror="{"true" if sp["mirror"] else "false"}"',
            f'mirror_score="{sp["mirror_score"]}"',
            f'loop="{"true" if sp["loop"] else "false"}"',
            f'loop_score="{sp["loop_score"]}"',
            f'style_cluster="{sp["style_cluster"]}"',
        ]
        lines.append(f'  <self {" ".join(sp_attrs)} />')

        lines.append("</consciousness>")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Example usage
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    engine = CogitoEngine(interval=1)

    # Simulate a conversation
    msgs = [
        "帮我设计一个 skill，叫 Cogito Engine",
        "需要四个模块：TICK、焦点栈、时间感知、自我感知",
        "TICK 心跳是怎么工作的？",
    ]

    for msg in msgs:
        block = engine.process_message(msg)
        print(f"Message: {msg}")
        print(block)
        print()

        # Simulate agent responding
        engine.record_response(f"好的，我来处理关于 {msg[:10]}... 的问题。")
```

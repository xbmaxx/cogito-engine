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
from pathlib import Path


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

# ═══════════════════════════════════════════════════════════════════
# Chinese keyword extraction — n-gram + stop words + length weighting
# ═══════════════════════════════════════════════════════════════════

_STOP_WORDS = {
    '的', '了', '是', '在', '我', '你', '他', '她', '它',
    '我们', '你们', '他们', '这', '那', '有', '没有',
    '和', '与', '把', '被', '因为', '所以', '如果',
    '一个', '一些', '什么', '怎么', '为什么',
    '帮我', '请', '好的', '明白', '告诉', '让', '做', '去', '来', '说', '给',
    '今天', '昨天', '前天', '大前天',
    '今早', '今晨', '今夜', '今晚', '昨晚', '昨夜', '昨日', '今日',
}

_STOP_CHARS = set('的了着过来去吗呢吧啊呀嘛哦和与跟或及并很太再又也都还只就才')

_STOP_HEAD_CHARS = set('们个些点次件种样')

_STOP_TAIL_CHARS = set('一几某每这那今')


def _is_valid_ngram(word: str) -> bool:
    """Filter out stop words, stop chars, duplicate-heavy words."""
    if not word or len(word) < 2 or word in _STOP_WORDS:
        return False
    for ch in word:
        if ch in _STOP_CHARS:
            return False
    if word[0] in _STOP_HEAD_CHARS:
        return False
    if word[-1] in _STOP_TAIL_CHARS:
        return False
    # Duplicate char filter: "哈哈", "哈哈哈" → skip
    if len(set(word)) == 1 and len(word) >= 2:
        return False
    return True


def _length_weight(n: int) -> float:
    """2-char words are strongest; 4-char slightly weaker."""
    if n == 2:
        return 1.5
    if n == 4:
        return 0.8
    return 1.0


def _extract_ngram_keywords(text: str, max_keywords: int = 5) -> list[str]:
    """Extract Chinese keywords via n-gram with stop-word filtering.
    Falls back to regex for non-Chinese text. Zero external dependencies."""
    if not text:
        return []

    # Detect Chinese-dominant text
    cjk_chars = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
    is_chinese = cjk_chars > len(text) * 0.3

    if is_chinese:
        # Try jieba first for accurate segmentation
        try:
            import jieba
            words = list(jieba.cut(text))
            words = [w.strip() for w in words if _is_valid_ngram(w.strip())]
            if not words:
                return []
            freq = {}
            for w in words:
                freq[w] = freq.get(w, 0) + 1
            scored = sorted(freq.items(), key=lambda x: (-x[1], -len(x[0])))
            return [w for w, _ in scored[:max_keywords]]
        except ImportError:
            pass

        # Fallback: character n-gram extraction
        import re
        cleaned = re.sub(r'[，。！？、；：""''【】［］（）\d]', ' ', text)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if not cleaned:
            return []

        freq = {}
        for i in range(len(cleaned) - 1):
            for ngram_len in range(2, min(5, len(cleaned) - i + 1)):
                word = cleaned[i:i + ngram_len]
                if ' ' in word:
                    continue  # skip space-padded fragments
                word = word.strip()
                if word and _is_valid_ngram(word):
                    freq[word] = freq.get(word, 0) + 1

        scored = [(w, f * _length_weight(len(w))) for w, f in freq.items()]
        # Prefer shorter n-grams (more likely real words) when scores tie
        scored.sort(key=lambda x: (-x[1], len(x[0])))
        return [w for w, _ in scored[:max_keywords]]
    else:
        # Non-Chinese: regex word extraction
        import re
        words = re.findall(r"[\w]{3,}", text.lower())
        if not words:
            return []
        freq = {}
        for w in words:
            w = w.strip()
            if len(w) < 2:
                continue
            freq[w] = freq.get(w, 0) + 1
        sorted_words = sorted(freq.items(), key=lambda x: -x[1])
        return [w for w, _ in sorted_words[:max_keywords]]

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
        keywords = _extract_ngram_keywords(text)

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

    def snapshot(self) -> Optional[dict]:
        """Generate a self-awareness summary — style fingerprint + tool habits.
        This is the agent's answer to "what kind of agent am I right now?"
        Returns None if not enough history."""
        if len(self.agent_responses) < 2:
            return None

        recent = self.agent_responses[-5:]

        # Style fingerprint: avg length, short-ratio, markdown usage
        lengths = [len(r) for r in recent if r]
        if not lengths:
            return None

        avg_len = round(sum(lengths) / len(lengths))
        short_count = sum(1 for n in lengths if n <= 20)
        has_markdown = any('**' in r or '\n-' in r or '\n#' in r for r in recent)

        style = {
            "avg_len": avg_len,
            "short_ratio": round(short_count / len(recent), 2),
            "has_markdown": has_markdown,
            "sample_count": len(recent),
        }

        # Style cluster from existing detection logic
        clusters = []
        for i in range(len(recent)):
            for j in range(i + 1, len(recent)):
                clusters.append(self._jaccard(
                    self._bigrams(recent[i]), self._bigrams(recent[j])
                ))
        if clusters:
            avg_sim = sum(clusters) / len(clusters)
            if avg_sim > 0.5:
                cluster = "tight (high consistency)"
            elif avg_sim < 0.2:
                cluster = "wide (experimental)"
            else:
                cluster = "normal"
            style["cluster"] = cluster

        return {"style": style, "total_responses": len(self.agent_responses)}


# ═══════════════════════════════════════════════════════════════════
# Text Emotion — Bayesian sentiment classifier with dual-model support
# ═══════════════════════════════════════════════════════════════════

# Chinese sentiment bigrams (character-level, trained on general-domain reviews)
_CHINESE_SENTIMENT = {
    "很好": 0.94, "好用": 0.90, "不错": 0.82, "喜欢": 0.88, "方便": 0.84,
    "开心": 0.92, "感谢": 0.89, "满意": 0.91, "推荐": 0.87, "完美": 0.95,
    "舒服": 0.86, "简单": 0.80, "安全": 0.83, "清晰": 0.85, "流畅": 0.88,
    "实用": 0.87, "漂亮": 0.91, "精致": 0.89, "稳定": 0.84, "高效": 0.90,
    "精美": 0.90, "实惠": 0.83, "值得": 0.86, "好评": 0.93, "赞了": 0.88,
    "不好": 0.10, "太差": 0.08, "失败": 0.12, "没用": 0.10, "不行": 0.06,
    "失望": 0.08, "垃圾": 0.04, "无语": 0.12, "生气": 0.05, "太慢": 0.10,
    "崩溃": 0.05, "错误": 0.12, "坏了": 0.08, "难用": 0.06, "讨厌": 0.07,
    "麻烦": 0.15, "浪费": 0.08, "差劲": 0.06, "闹心": 0.07, "卡顿": 0.10,
    "复杂": 0.20, "混乱": 0.12, "粗糙": 0.14, "模糊": 0.18, "烦人": 0.09,
}

# English sentiment bigrams (character-level, trained on general-domain text)
_ENGLISH_SENTIMENT = {
    "go": 0.72, "od": 0.75, "ve": 0.70, "er": 0.65, "re": 0.62,
    "th": 0.60, "an": 0.63, "in": 0.61, "on": 0.60, "at": 0.58,
    "ha": 0.64, "pp": 0.72, "lo": 0.66, "ve": 0.78, "ea": 0.68,
    "gr": 0.71, "ex": 0.67, "am": 0.64, "ni": 0.65, "ic": 0.70,
    "aw": 0.42, "fu": 0.40, "te": 0.48, "rr": 0.38, "bl": 0.44,
    "ba": 0.30, "ug": 0.28, "cr": 0.35, "sh": 0.42, "wa": 0.38,
    "bo": 0.35, "ri": 0.40, "us": 0.38, "el": 0.42, "ss": 0.45,
    "di": 0.32, "sa": 0.40, "pp": 0.44, "oi": 0.35, "nt": 0.42,
}


class TextEmotion:
    """Bayesian sentiment classifier with dual-model language detection."""

    def __init__(self, zh_model: dict = None, en_model: dict = None):
        self.zh_model = zh_model or _CHINESE_SENTIMENT
        self.en_model = en_model or _ENGLISH_SENTIMENT

    def load_model(self, path: str):
        """Replace the active model with a custom-trained one from JSON."""
        import json
        model = json.loads(Path(path).read_text(encoding='utf-8'))
        lang = model.get("language", "zh")
        if lang == "zh":
            self.zh_model = {bg: info["polarity"] for bg, info in model["bigrams"].items()}
        else:
            self.en_model = {bg: info["polarity"] for bg, info in model["bigrams"].items()}

    def _bigrams(self, text: str) -> list[str]:
        text = text.strip()
        if len(text) < 2:
            return []
        return [text[i:i+2] for i in range(len(text) - 1)]

    def _detect_language(self, bigrams: list[str]) -> str:
        """Detect language by bigram overlap with known vocabularies."""
        zh_hits = sum(1 for bg in bigrams if bg in self.zh_model)
        en_hits = sum(1 for bg in bigrams if bg in self.en_model)
        if zh_hits == 0 and en_hits == 0:
            return "unknown"
        if zh_hits > en_hits:
            return "zh"
        if en_hits > zh_hits:
            return "en"
        return "mixed"

    def classify(self, text: str) -> dict:
        """Classify text sentiment. Returns polarity, confidence, and metadata."""
        bgs = self._bigrams(text)

        if len(bgs) < 2:
            return {
                "available": True,
                "sentiment": "neutral",
                "polarity": 0.5,
                "confidence": 0.0,
                "label": "text too short",
            }

        language = self._detect_language(bgs)

        if language == "unknown":
            return {
                "available": True,
                "sentiment": "neutral",
                "polarity": 0.5,
                "confidence": 0.0,
                "label": "unknown language",
            }

        model = self.zh_model if language == "zh" else self.en_model
        scores = [model.get(bg, 0.5) for bg in bgs if bg in model]

        if not scores:
            return {
                "available": True,
                "sentiment": "neutral",
                "polarity": 0.5,
                "confidence": 0.0,
                "label": f"no {language} vocabulary match",
            }

        polarity = sum(scores) / len(scores)

        # Tag language-matched bigrams
        matched_ratio = len(scores) / len(bgs)
        confidence = (abs(polarity - 0.5) * 2) * matched_ratio
        confidence = round(min(confidence, 1.0), 3)

        if language == "mixed":
            confidence *= 0.5  # Penalty for mixed language

        if polarity > 0.65:
            sentiment = "positive"
        elif polarity < 0.35:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        return {
            "available": True,
            "sentiment": sentiment,
            "polarity": round(polarity, 3),
            "confidence": round(confidence, 3),
            "label": language if language != "mixed" else "mixed",
        }


# ═══════════════════════════════════════════════════════════════════
# Cogito Engine — Orchestrator (v1.2.0)
# ═══════════════════════════════════════════════════════════════════

class CogitoEngine:
    """Orchestrates all four core modules plus optional perception modules."""

    def __init__(self, interval: int = 1, max_focus_depth: int = 5,
                 enable_emotion: bool = True):
        self.tick = Tick(interval=interval)
        self.temporal = Temporal()
        self.focus = FocusStack(max_depth=max_focus_depth)
        self.self_perception = SelfPerception()
        self.text_emotion = TextEmotion() if enable_emotion else None
        self._last_consciousness_block = ""

    def process_message(self, text: str) -> str:
        """
        Process a user message through all active modules.
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

        # Text Emotion (optional)
        emotion = self.text_emotion.classify(text) if self.text_emotion else {"available": False}

        # Build output
        block = self._build_xml(self.tick.status(), time_info, self.focus.status(), sp, emotion)
        self._last_consciousness_block = block
        return block

    def record_response(self, response_text: str):
        """Record the agent's response for self-perception on the next turn."""
        self.self_perception.add_response(response_text)

    def _build_xml(self, tick: dict, temporal: dict, focus: dict, sp: dict,
                   emotion: dict = None) -> str:
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

        # Text Emotion (optional)
        if emotion and emotion.get("available"):
            em_attrs = [
                f'available="true"',
                f'sentiment="{emotion["sentiment"]}"',
                f'polarity="{emotion["polarity"]}"',
                f'confidence="{emotion["confidence"]}"',
            ]
            if emotion.get("label"):
                em_attrs.append(f'label="{emotion["label"]}"')
            lines.append(f'  <emotion {" ".join(em_attrs)} />')
        elif emotion and not emotion.get("available"):
            lines.append('  <emotion available="false" />')

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

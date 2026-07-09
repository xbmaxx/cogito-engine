---
title: "Focus Stack Specification"
description: "Specification for the Focus Stack module: keyword extraction, topic shift detection, frame push/pop rules, depth limits, and focus history serialization."
tags: [cogito-engine, focus-stack, attention, specification]
---

# Focus Stack Specification

## Purpose

The Focus Stack tracks what the agent is paying attention to across conversation turns. It extracts keywords from messages, detects topic shifts, and maintains a depth-limited stack of focus frames. The stack provides continuity — the agent knows what was just discussed and how the conversation arrived at the current topic.

## Data Model

A focus frame is a lightweight object:

| Field | Type | Description |
|-------|------|-------------|
| `keywords` | string[] | 2–5 keywords extracted from the message |
| `ts` | ISO 8601 | When this frame was created (local time) |
| `source` | string | "user" or "agent" — who triggered the frame |

The focus stack holds frames in LIFO order (most recent on top). The entire stack:

| Field | Type | Description |
|-------|------|-------------|
| `depth` | integer | Current number of frames (1–max_depth) |
| `frames` | frame[] | Active frames, most recent first |
| `history` | frame[] | Archived frames that were popped off |

## Keyword Extraction

Extract 2–5 keywords per message using the following heuristics:

1. **Proper nouns first.** Names, products, technologies, project names take priority.
2. **Domain terms next.** Specialized vocabulary relevant to the conversation context.
3. **Action verbs last.** Only include verbs if they signal a topic shift (e.g., "design," "deploy," "refactor").
4. **Stop words excluded.** Articles, prepositions, pronouns, and common verbs are ignored.
5. **Minimum length 2 characters.** Single-character Chinese words can be meaningful and are included.

The agent may use a simple frequency-based extraction or a more sophisticated NLP approach. The specification only requires that keywords are representative and discriminable.

## Topic Shift Detection

A topic shift occurs when the new message's keywords have less than 30% overlap with the keywords of the top frame. When a shift is detected, a new frame is pushed onto the stack.

```
new_keywords ∩ top_frame.keywords
─────────────────────────────────  < 0.3  →  topic shift → push new frame
    max(|new_keywords|, |top_frame.keywords|)
```

### Continuous topic

When overlap is >= 30%, the top frame's keywords are merged with the new keywords (union, capped at 5). The frame's timestamp is updated. No new frame is created.

### No-top-frame edge case

If the stack is empty (first message of a session), always push a new frame with the extracted keywords.

## Depth Management

The maximum depth is configurable. Default: **5**.

| Depth | Behavior |
|-------|----------|
| < max_depth | Push new frame normally |
| = max_depth | Pop oldest frame into history, push new frame |
| > max_depth | Should never occur — implementations must enforce the limit on push |

## History

Frames that are popped off the stack are stored in the `history` array. History is ordered most-recent-first. The history preserves the arc of the conversation for reflection and summarization.

History is not purged automatically. Implementations should cap history at a reasonable size (e.g., 50 frames) to prevent unbounded growth.

## Session Summary

When a session ends, the focus stack should produce a summary frame:

```xml
<summary keywords="..." type="session_summary" />
```

The summary's keywords are the top 3 most frequent keywords across all frames (active + history). This summary frame is stored in history and can be loaded at the start of the next session for continuity.

## Output

The Focus Stack module produces the following XML fragment:

```xml
<focus depth="2">
  <frame keywords="Cogito,Engine,skill,design" source="user" />
  <frame keywords="consciousness,architecture" source="agent" />
</focus>
```

When empty:

```xml
<focus depth="0" />
```

## Focus History Output

When requested explicitly (e.g., via `consciousness_get_status`), include history:

```xml
<focus depth="2">
  <frame keywords="next-topic,implementation" source="user" />
  <frame keywords="current,active" source="user" />
</focus>
<focus_history>
  <frame keywords="earlier,topic" source="user" />
  <frame keywords="even-earlier" source="user" />
</focus_history>
```

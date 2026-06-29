---
title: "Consciousness XML Output Format"
description: "Complete XML schema for the consciousness output block: field definitions, validation rules, and platform adaptation notes."
tags: [cogito-engine, consciousness, xml-format, output-schema]
---

# Consciousness XML Output Format

## Purpose

All four Cogito Engine modules converge into a single `<consciousness>` XML element. This document defines the complete schema, required and optional fields, and validation rules.

## Complete Schema

```xml
<consciousness>
  <tick active="true|false" count="integer" ttl="integer" />
  <temporal iso="ISO8601" weekday="string" period="string" [local="string"] [timezone="string"] />
  <focus depth="integer">
    [<frame keywords="comma,separated" source="user|agent" />]*
  </focus>
  [<focus_history>
    [<frame keywords="comma,separated" source="user|agent" [type="session_summary"] />]*
  </focus_history>]
  <self mirror="true|false" [mirror_score="float"] loop="true|false" [loop_score="float"] style_cluster="string" />
</consciousness>
```

## Field Definitions

### `<tick>`

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `active` | boolean | Yes | Whether the heartbeat is running |
| `count` | integer | Yes | Monotonic turn counter |
| `ttl` | integer | Yes | Turns remaining until next full cycle |

### `<temporal>`

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `iso` | ISO 8601 | Yes | Current local time with timezone offset |
| `weekday` | string | Yes | Day of week in English (Monday–Sunday) |
| `period` | string | Yes | Time period (morning/noon/afternoon/evening/night) |
| `local` | string | No | Human-readable local time (e.g., "2026-06-29 15:41") |
| `timezone` | string | No | Timezone abbreviation (e.g., "CST", "EST") |

### `<focus>`

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `depth` | integer | Yes | Number of active focus frames |

### `<frame>` (inside `<focus>` or `<focus_history>`)

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `keywords` | string | Yes | Comma-separated keywords |
| `source` | string | Yes | "user" or "agent" |
| `type` | string | No | "session_summary" for summary frames in history |

### `<focus_history>`

Optional. Contains archived frames in chronological order (oldest first, newest last). Present only when explicitly requested.

### `<self>`

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `mirror` | boolean | Yes | Whether mirroring was detected |
| `mirror_score` | float | No | Jaccard score vs user message |
| `loop` | boolean | Yes | Whether looping was detected |
| `loop_score` | float | No | Jaccard score vs previous response |
| `style_cluster` | string | Yes | "initializing", "unchanged", "narrow", or "diverse" |

## Validation Rules

1. The `<consciousness>` root element must contain exactly one each of `<tick>`, `<temporal>`, `<focus>`, and `<self>`.
2. `<focus_history>` is optional and may appear at most once.
3. All boolean attributes must be the literal strings "true" or "false".
4. `depth` must equal the number of `<frame>` children inside `<focus>`.
5. `ttl` must be <= `interval` (interval is not serialized in the output).
6. `iso` must include a timezone offset (e.g., `+08:00`), not "Z" or no offset.

## Platform Adaptation

Not all platforms can parse or inject XML natively. The following adaptations are valid as long as all fields are preserved:

### JSON adaptation

```json
{
  "tick": {"active": true, "count": 12, "ttl": 5},
  "temporal": {"iso": "2026-06-29T15:41:00+08:00", "weekday": "Monday", "period": "afternoon"},
  "focus": {"depth": 2, "frames": [
    {"keywords": ["Cogito", "Engine"], "source": "user"}
  ]},
  "self": {"mirror": false, "loop": false, "style_cluster": "unchanged"}
}
```

### Plain text adaptation

For platforms with strict token constraints, collapse all fields into a single line:

```
[TICK:12/ttl:5] [TIME:2026-06-29T15:41:00+08:00 Mon afternoon] [FOCUS:Cogito,Engine>consciousness,architecture] [SELF:no-mirror no-loop unchanged]
```

The plain text format is lossy (no frame source tracking, no focus history). Use only when context budget is severely constrained.

## Injection Point

The `<consciousness>` block must be the first element in the agent's context for each new turn. It should appear before:

- System instructions
- Conversation history
- User's current message

This positions the awareness state as the lens through which the agent processes all subsequent input.

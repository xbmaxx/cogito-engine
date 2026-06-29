---
title: "Consciousness XML Output Format"
description: "Complete XML schema for the consciousness output block: field definitions, validation rules, and platform adaptation notes."
tags: [cogito-engine, consciousness, xml-format, output-schema]
---

# Consciousness XML Output Format

## Purpose

All Cogito Engine modules converge into a single `<consciousness>` XML element. The Core Layer elements are always present. The Perception Layer elements appear only when the agent's platform supports them. This document defines the complete schema, required and optional fields, and validation rules.

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

  <!-- Perception Layer (optional — each appears only when available) -->
  [<env available="true|false">
    [<source time="string" [weather="string"] [system_info="string"] [foreground_app="string"] [battery="string"] [network="string"] [location="string"] />]
  </env>]
  [<emotion available="true|false" [sentiment="positive|neutral|negative"] [polarity="float"] [confidence="float"] [label="string"] />]
  [<narrative available="true|false" [unresolved_count="integer"] [last_session="date"] [recurring_patterns="integer"] />]
  [<reflector available="true|false" [trigger="string"] [last_reflection="ISO8601"] />]
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

### `<env>` (Perception Layer — optional)

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `available` | boolean | Yes | Whether environment data was successfully probed |

### `<source>` (inside `<env>`)

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `time` | string | Yes | Source of time data (always "system") |
| `weather` | string | No | Source of weather data (e.g., "api", "wttr.in") |
| `system_info` | string | No | Source of system info (e.g., "shell", "psutil") |
| `foreground_app` | string | No | Source of foreground app detection |
| `battery` | string | No | Source of battery data |
| `network` | string | No | Source of network status |
| `location` | string | No | Source of geolocation data |

### `<emotion>` (Perception Layer — optional)

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `available` | boolean | Yes | Whether text sentiment analysis is available |
| `sentiment` | string | No | "positive", "neutral", or "negative" |
| `polarity` | float | No | Sentiment score 0.0 (negative) to 1.0 (positive) |
| `confidence` | float | No | Classification confidence 0.0 to 1.0 |
| `label` | string | No | Optional emotion label (e.g., "焦虑", "excited") |

### `<narrative>` (Perception Layer — optional)

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `available` | boolean | Yes | Whether narrative memory is active |
| `unresolved_count` | integer | No | Number of unresolved questions carried from past sessions |
| `last_session` | string | No | Date of the most recent previous session |
| `recurring_patterns` | integer | No | Number of detected recurring patterns |

### `<reflector>` (Perception Layer — optional)

| Attribute | Type | Required | Description |
|-----------|------|----------|-------------|
| `available` | boolean | Yes | Whether session reflector is active |
| `trigger` | string | No | Detection method ("signal", "inactivity", "command", "termination") |
| `last_reflection` | ISO 8601 | No | Timestamp of the most recent session reflection |

## Validation Rules

1. The `<consciousness>` root element must contain exactly one each of `<tick>`, `<temporal>`, `<focus>`, and `<self>`.
2. Perception Layer elements (`<env>`, `<emotion>`, `<narrative>`, `<reflector>`) are optional and may appear at most once each.
3. `<focus_history>` is optional and may appear at most once.
4. All boolean attributes must be the literal strings "true" or "false".
5. `depth` must equal the number of `<frame>` children inside `<focus>`.
6. `ttl` must be <= `interval` (interval is not serialized in the output).
7. `iso` must include a timezone offset (e.g., `+08:00`), not "Z" or no offset.
8. When a Perception Layer element has `available="false"`, it must have no other attributes or children.

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

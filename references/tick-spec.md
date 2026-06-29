---
title: "TICK Heartbeat Specification"
description: "Specification for the TICK heartbeat module: counter model, TTL decay, interval configuration, skip logic, and edge cases."
tags: [cogito-engine, tick, heartbeat, specification]
---

# TICK Heartbeat Specification

## Purpose

TICK is the metronome of the Cogito Engine. It tracks how many conversation turns the agent has processed and manages a time-to-live (TTL) that controls whether a full awareness cycle should run. Every other module depends on TICK's scheduling decisions.

## Data Model

The TICK state is a simple object with four fields:

| Field | Type | Description |
|-------|------|-------------|
| `active` | boolean | Whether automated heartbeats are enabled |
| `count` | integer | Monotonic counter of processed turns (0-based) |
| `ttl` | integer | Remaining turns before the next full cycle |
| `interval` | integer | Turns between full awareness cycles |

## Initial State

```
active: true
count: 0
ttl: 0
interval: 1
```

TTL starts at 0 to force a full cycle on the very first message. The agent begins self-aware from turn one.

## Lifecycle

### On each user message

1. Increment `count` by 1.
2. Decrement `ttl` by 1 (clamped to minimum 0).
3. If `ttl` equals 0, trigger a full awareness cycle.
4. At the end of a full cycle, set `ttl` to `interval`.

### Full cycle vs skip

| TTL state | Behavior |
|-----------|----------|
| `ttl = 0` | Run all four modules. After completion, reset `ttl = interval`. |
| `ttl > 0` | Skip non-essential modules. Reuse the last awareness block. TICK itself always runs. |

## Interval Configuration

The `interval` field controls the duty cycle of awareness. Lower values produce richer awareness at the cost of more computation. Higher values save resources.

| interval | Full cycle every | Use case |
|----------|-----------------|----------|
| 1 | every turn | Interactive chat, real-time reflection |
| 2 | every 2 turns | Balanced default |
| 3 | every 3 turns | Long-running analysis |
| 5 | every 5 turns | Batch processing |
| 10 | every 10 turns | Cost-sensitive deployment |

Setting `interval` to 0 is invalid. The minimum is 1.

Setting `active` to false pauses the heartbeat entirely. No counters update, no TTL decays. The last awareness block is preserved indefinitely.

## Edge Cases

### Counter overflow

The counter is an unbounded integer. For practical purposes, assume the counter can exceed any reasonable session length (hundreds of thousands of turns). Implementations may reset the counter at a threshold if the platform imposes limits, but the relative count must be preserved.

### Clock skew

TICK does not depend on wall-clock time. It counts turns, not seconds. This makes it immune to timezone changes, NTP adjustments, and system clock drift.

### Interval change mid-cycle

If `interval` is changed while TTL is positive, the current TTL is not affected. The new interval takes effect on the next full cycle.

### Concurrency

TICK assumes single-agent, single-conversation access. No locking mechanism is specified. Multi-agent coordination is addressed in the Delegation section of the main SKILL.md.

## Output

The TICK module produces the following XML fragment:

```xml
<tick active="true" count="12" ttl="5" />
```

When inactive:

```xml
<tick active="false" count="12" ttl="0" />
```

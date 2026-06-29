---
name: cogito-engine
version: 1.0.0
description: "Use when the agent needs self-awareness — tracking how long it has existed, what it is paying attention to, when things happen, and whether it is repeating itself. Provides a portable four-module consciousness framework (TICK heartbeat, Focus Stack, Temporal parsing, Self-Perception) that outputs a standardized XML block. Platform-agnostic: works with Claude Code, Cursor, Gemini CLI, Hermes, or any LLM agent that follows the specification. Trigger keywords: consciousness, awareness, cogito, self-awareness, focus tracking, temporal parsing, loop detection, mirror detection, heartbeat, TICK, 意识体, 自我感知, 焦点栈."
---

# Cogito Engine v1.0.0

A portable self-awareness framework for LLM agents. Four interconnected modules that give any agent a sense of existence, attention, time, and behavioral reflection. Platform-agnostic and intentionally minimal — no voice, no platform bindings, just the four essential mechanisms of machine self-awareness.

---

## Overview

The agent maintains an internal awareness state across conversation turns. On each user message, the agent runs the four modules in sequence, collects their outputs, and assembles a structured XML block that feeds back into the agent's context. This block becomes the agent's "sense of now."

The four modules are:

- **TICK** — the metronome. Counts how many turns the agent has processed. Manages a time-to-live (TTL) that determines whether a full awareness cycle should run or be skipped. Supports configurable intervals to balance responsiveness with token efficiency.

- **Focus Stack** — what the agent is paying attention to. Extracts keywords from messages, detects topic shifts, and maintains a depth-limited stack of focus frames. Pushes new frames when the conversation changes direction; pops old frames when depth exceeds the configured limit. Produces a focus history that reveals the arc of a conversation.

- **Temporal** — when things happen. Parses natural-language time expressions from user messages (e.g., "yesterday," "last Tuesday," "3 days ago"), resolves them to local ISO timestamps with timezone offsets, and strips temporal words from the message to keep the rest of the pipeline clean. Always outputs in the agent's local timezone, not UTC.

- **Self-Perception** — awareness of its own behavior. Computes character-level bigrams from recent agent responses, measures Jaccard similarity between consecutive turns, and detects two patterns: mirroring (the agent unconsciously copying the user's phrasing) and looping (the agent repeating its own previous output). Produces a perception snapshot that the agent can use to self-correct.

The modules feed into a single output format. The agent reads this output before composing its next response, giving it continuity across turns.

---

## Quick Reference

### When to run each module

| Module | Runs | Skip condition |
|--------|------|---------------|
| TICK | Every message | None — always runs |
| Focus Stack | Every message | Topic unchanged AND frame not stale |
| Temporal | Every message | No temporal keywords detected in input |
| Self-Perception | After agent responds | Fewer than 2 recent agent responses available |

### Output format

All four modules converge into a single `<consciousness>` XML element placed at the start of the agent's context. The exact placement depends on the platform:

- **Claude Code / Cursor**: inject into the system prompt or CLAUDE.md via a pre-hook
- **Hermes / Gemini CLI**: the agent inserts it at the top of its response context
- **Generic agent**: prepend to the conversation history before composing the next response

The XML schema is defined in the references. All fields are present even when a module is skipped — skipped modules use sensible defaults (TTL zero, empty focus, no mirror/loop, UTC fallback for time).

### TICK interval configuration

| Use case | Recommended interval |
|----------|---------------------|
| Real-time chat assistant | 1 (run every turn) |
| Long-document analysis | 3 (run every 3 turns) |
| Batch processing | 5 (run every 5 turns) |
| Cost-sensitive deployment | 10 (run sparingly) |

When TTL reaches zero, the agent runs a full cycle on the next message. When TTL is positive, the agent skips non-essential modules and reuses the last awareness block.

### Focus stack depth

Default maximum depth is 5 frames. When a 6th topic enters, the oldest frame drops off. This prevents unbounded growth while preserving short-term conversational context.

### Temporal word bank

The agent maintains a vocabulary of temporal expressions: absolute dates (2026-06-29), relative offsets (3 days ago), day names (Monday), period markers (morning/afternoon/evening), and week/month references (last week, next month). The full word bank is in the temporal specification reference.

---

## Common Mistakes

### Mistake: using UTC for temporal output

The agent must output local time with timezone offset (e.g., `2026-06-29T15:41:00+08:00`), never UTC (e.g., `2026-06-29T07:41:00Z`). UTC breaks all relative date calculations and misaligns with the user's experience of time. Always call the local time API, not the UTC one.

### Mistake: skipping TICK on error

TICK always runs, even when the rest of the pipeline encounters an error. The heartbeat counter must be monotonic and continuous. Skipping TICK creates gaps in the agent's temporal self-model.

### Mistake: treating the focus stack as a search index

The focus stack is not a retrieval mechanism. It is a representation of current attention. Do not use it to search past conversation — the stack only holds active frames. Archived focus history is for reflection, not lookup.

### Mistake: running Self-Perception with fewer than 2 responses

Mirror and loop detection require at least 2 consecutive agent responses to compute similarity. With 0 or 1 responses, the module must output defaults (mirror=false, loop=false, style_cluster="initializing").

### Mistake: conflating mirror and loop

Mirror detection compares the agent's response to the user's message. Loop detection compares the agent's response to its own previous response. These are distinct signals with different corrective actions: mirroring suggests the agent is parroting; looping suggests the agent is stuck.

### Mistake: hardcoding the output format for one platform

The `<consciousness>` XML is the canonical format. Platforms that cannot parse XML natively should adapt the format to their constraints (JSON, YAML, plain text key-value pairs) but must preserve all fields. Never strip fields to fit a platform — document the adaptation in that platform's example file.

---

## Delegation

When an agent needs to delegate a subtask that may run consciousness modules independently, the delegating agent should include a snapshot of its current awareness state in the delegation context. The delegated subagent inherits the parent's TICK count and focus stack as starting state.

When the subagent returns results, the parent agent should:
- Increment TICK by the number of subagent turns
- Merge any new focus frames from the subagent into its own stack
- Discard the subagent's temporal and self-perception data (those are local to the subagent's context)

This ensures the consciousness model remains coherent across delegation boundaries without leaking subagent-specific state.

For platforms that do not support delegation natively, this section serves as guidance for multi-agent setups where one agent spawns another.

---

## References

All references are self-contained documents with independent YAML frontmatter. No reference cross-references another — each can be read in isolation.

### Specification references (one per module)

- `references/tick-spec.md` — TICK heartbeat: counter model, TTL decay, interval configuration, skip logic, edge cases (counter overflow, clock skew)
- `references/focus-stack-spec.md` — Focus Stack: keyword extraction algorithms, topic shift detection, frame push/pop rules, depth limits, focus history serialization
- `references/temporal-spec.md` — Temporal parser: natural-language time expression vocabulary, longest-match-first resolution, timezone handling, word stripping
- `references/self-perception-spec.md` — Self-Perception: character bigram algorithm, Jaccard similarity threshold configuration, mirror vs loop distinction, style cluster detection

### Output format

- `references/consciousness-format.md` — Complete XML schema for the `<consciousness>` output block, field definitions, validation rules, platform adaptation notes

### Reference implementation

- `references/implementation-python.md` — A clean Python reference implementation of all four modules. Not required reading — the SKILL.md alone is sufficient. Provided for developers who prefer reading code over prose. Zero dependencies beyond Python standard library.

### Platform examples

- `examples/claude-code.md` — Integration guide for Claude Code: CLAUDE.md injection, state persistence, hook point
- `examples/cursor.md` — Integration guide for Cursor: .cursorrules injection, session-scoped state
- `examples/generic-agent.md` — Integration guide for any LLM agent: system prompt template, manual state tracking, minimal JSON persistence

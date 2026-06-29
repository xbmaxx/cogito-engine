---
title: "Narrative Memory Specification"
description: "Specification for the Narrative Memory module: insight journal format, cross-session persistence, unresolved question tracking, and pattern accumulation."
tags: [cogito-engine, narrative-memory, cross-session, specification]
---

# Narrative Memory Specification

## Purpose

Narrative Memory gives the agent continuity across conversation sessions. It maintains a lightweight journal of unresolved questions, discovered patterns, and recurring themes. Unlike a full memory system, it stores insights — not transcripts. A few hundred characters per session, enough to remind the agent what was left unfinished.

## Activation Condition

Narrative Memory requires persistent storage. On startup, the agent probes:

```
Can I write a file/record that survives session restart?
  ├── Yes → activate Narrative Memory
  └── No  → disable it; work with single-session context only
```

The probe can be as simple as writing a test file to a known location and reading it back after a simulated restart. Platforms with built-in persistence APIs (Hermes memory, Claude Code project files, Cursor session storage) can use those directly.

## Insight Journal Format

Narrative Memory uses a single append-only journal file per agent instance. Each entry is a short structured record:

```json
{
  "session_id": "2026-06-29-001",
  "timestamp": "2026-06-29T15:41:00+08:00",
  "insights": [
    {
      "type": "unresolved_question",
      "content": "User wants to deploy Cogito Engine to production but hasn't decided on state persistence approach",
      "priority": "high"
    },
    {
      "type": "pattern",
      "content": "User frequently asks about cross-platform compatibility — may need a dedicated examples/ directory",
      "frequency": 3
    }
  ],
  "summary": "Discussed Cogito Engine architecture and deployment. User decided on dual-layer design. Unresolved: persistence strategy."
}
```

### Entry types

| Type | Description | Example |
|------|-------------|---------|
| `unresolved_question` | A question or decision the user left open | "Which database to use for state persistence?" |
| `pattern` | A recurring theme or behavior observed across sessions | "User prefers Chinese documentation" |
| `decision` | A confirmed decision made during the session | "Decided to use JSON format for state files" |
| `insight` | A general observation or learned fact | "User's development environment is macOS with Hermes" |

### Journal size management

The journal is capped at 50 entries. When full, the oldest entries are archived to a secondary file. The agent reads the most recent 5 entries on session start for context injection.

## Cross-Session Injection

When Narrative Memory is active, the agent prepends a context summary to its first response in each new session:

```
[Cross-session context from Narrative Memory]
Last session: 2026-06-28 — Discussed Cogito Engine architecture.
Unresolved: persistence strategy decision needed.
Recurring pattern: cross-platform compatibility concerns (3 sessions).
```

This summary is compact — typically 2-4 lines. It gives the agent continuity without flooding the context window.

## Unresolved Question Tracking

Unresolved questions are the most valuable part of Narrative Memory. They represent the user's open loops — things they asked about but didn't resolve. The agent tracks:

- **Question content** — what was asked
- **Session first raised** — when it appeared
- **Priority** — high (user explicitly asked for follow-up), medium, low
- **Status** — unresolved / partially addressed / resolved

When a question is resolved in a later session, the agent marks it resolved rather than deleting it. This preserves the trail of how the question evolved.

## Pattern Detection

Pattern detection is a simple frequency counter. When the same theme appears across 3+ sessions, the agent records it as a pattern. Examples:

- "User asks about deployment on every session"
- "User prefers examples over abstract documentation"
- "User consistently works late at night (messages after 10 PM)"

Patterns help the agent anticipate user needs without explicit instruction.

## Output Format

When available:

```xml
<narrative available="true" unresolved_count="3" last_session="2026-06-28" recurring_patterns="2" />
```

When unavailable:

```xml
<narrative available="false" />
```

## Integration with Session Reflector

Narrative Memory and Session Reflector work together. At session end, the Session Reflector generates the summary entry that Narrative Memory stores. Narrative Memory provides the storage and retrieval; Session Reflector provides the content generation.

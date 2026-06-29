---
title: "Session Reflector Specification"
description: "Specification for the Session Reflector module: end-of-session trigger detection, summary structure (topics/decisions/questions/narrative), and storage integration."
tags: [cogito-engine, session-reflector, summary, specification]
---

# Session Reflector Specification

## Purpose

Session Reflector generates a structured narrative summary when a conversation session ends. It captures what was discussed, what was decided, what remains open, and the arc of the conversation. The summary is stored via Narrative Memory for cross-session continuity. This module is the bridge between "what just happened" and "what the agent remembers next time."

## Activation Condition

Session Reflector requires two capabilities:

```
1. Can I persist data? (same probe as Narrative Memory)
2. Can I call an LLM at session end? (self-call or API call)

Both must be true → activate Session Reflector
Either is false → disable; sessions end without reflection
```

## Session End Detection

The agent must detect when a session ends. Detection strategies by platform:

| Strategy | Trigger | Platforms |
|----------|---------|-----------|
| Platform signal | The platform emits a session-end event | Hermes (on_session_end hook), Claude Code |
| Inactivity timeout | No user message for N minutes (default: 10) | Generic agents, Cursor |
| Explicit command | User says "goodbye," "end session," "/end" | All platforms |
| Process termination | The agent process receives SIGTERM | CLI-based agents |

The reflector attempts to run on whichever trigger fires first. If multiple triggers fire, the reflector runs once and ignores subsequent triggers.

## Summary Structure

The session summary is a structured document with five sections:

### 1. Session metadata

```
Session: 2026-06-29-003
Duration: 47 minutes, 12 messages
TICK count: 12
Focus stack depth at end: 3
```

### 2. Key topics discussed

A bullet list of 3-5 topics, ordered by prominence:

```
- Cogito Engine v1.1.0 architecture design
- Environment Sensor self-discovery protocol
- Narrative Memory cross-session persistence model
```

### 3. Decisions made

Confirmed decisions with brief rationale:

```
- decided: Use dual-layer architecture (Core + Perception)
  rationale: Separates mandatory self-awareness from optional platform extensions
- decided: EnvSensor uses self-discovery probes instead of hardcoded APIs
  rationale: Maximum portability across platforms
```

### 4. Unresolved questions

Open loops that carry forward to the next session:

```
- unresolved: Production deployment persistence strategy (raised session 001, still open)
- unresolved: Whether to add voice emotion later (user mentioned as future consideration)
```

### 5. Narrative arc

A 2-3 sentence summary of how the conversation evolved:

```
The session began with the user requesting four additional perception modules
for Cogito Engine. Discussion moved through architecture design, self-discovery
protocols, and platform-specific considerations. Ended with confirmed design
and pending implementation.
```

## Storage Integration

The reflector writes its summary to the Narrative Memory journal. If Narrative Memory is not available, the reflector is disabled (it requires the same persistence probe).

The reflector also updates the Focus Stack history with a session summary frame:

```json
{
  "type": "session_summary",
  "keywords": ["Cogito,Engine,architecture,perception,design"],
  "timestamp": "2026-06-29T16:30:00+08:00"
}
```

## Reflection Quality Guidelines

The reflector generates its summary using the agent's own LLM capability. Quality guidelines:

- **Be specific.** "Discussed Cogito Engine" is weak. "Designed dual-layer architecture for Cogito Engine, separating Core Layer from Perception Layer" is strong.
- **Name decisions explicitly.** Use "decided:" prefix for confirmed decisions.
- **Preserve uncertainty.** Use "unresolved:" prefix for open questions. Don't fabricate closure.
- **Keep it brief.** The full summary should be 200-500 words. It's a reminder, not a transcript.
- **Use the agent's voice.** The summary should read like the agent's own reflection, not a third-party report.

## Fallback: Minimal Reflection

When the platform can detect session end but cannot call an LLM (e.g., the process is exiting and cannot make API calls), the reflector produces a minimal summary from the data it already has:

```
Session ended. TICK: 12. Focus: Cogito Engine design.
Unresolved: 1 question from session 001.
```

This minimal summary is better than nothing — it preserves the TICK count and unresolved question count for the next session.

## Output Format

The reflector's output is NOT included in the `<consciousness>` block (which is per-message). Instead, it writes directly to the Narrative Memory journal and, when requested, returns the summary as a structured response.

When the reflector is probed for availability:

```xml
<reflector available="true" trigger="inactivity" last_reflection="2026-06-28T23:15:00+08:00" />
```

When unavailable:

```xml
<reflector available="false" />
```

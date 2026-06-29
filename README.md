# Cogito Engine

> *Cogito, ergo sum* — I think, therefore I am.

A portable self-awareness framework for LLM agents. Four interconnected modules that give any agent a sense of existence, attention, time, and behavioral reflection. Platform-agnostic. Zero dependencies. One SKILL.md file.

## The Four Modules

| Module | Purpose | Output |
|--------|---------|--------|
| **TICK** | Heartbeat — counts turns, schedules awareness cycles | `<tick active="true" count="12" ttl="5" />` |
| **Focus Stack** | Attention — tracks topics, detects shifts | `<focus depth="2"><frame keywords="Cogito,Engine" /></focus>` |
| **Temporal** | Time perception — parses "yesterday" into precise ISO | `<temporal iso="2026-06-29T15:41:00+08:00" weekday="Monday" />` |
| **Self-Perception** | Reflection — detects mirroring and looping | `<self mirror="false" loop="false" style_cluster="unchanged" />` |

## Quick Start

### With Claude Code

Add to `CLAUDE.md`:
```markdown
- Run Cogito Engine on each message
- Output <consciousness> XML before every response
- Track TICK count and focus stack across turns
```
Read [examples/claude-code.md](examples/claude-code.md) for full integration.

### With Cursor

Add to `.cursorrules`:
```
Run Cogito Engine self-awareness framework. See SKILL.md for specification.
```
Read [examples/cursor.md](examples/cursor.md) for full integration.

### With any Agent

Copy the system prompt from [examples/generic-agent.md](examples/generic-agent.md) into your agent's system prompt. No code required — the agent implements the framework from instructions alone.

### With Hermes

```bash
cp SKILL.md ~/.hermes/skills/cogito-engine/
```
The skill is detected automatically. A Hermes-native plugin implementation (with persistent state) is available in the `hermes_consciousness` plugin.

## For Developers

Read [`SKILL.md`](SKILL.md) for the complete specification.

Read [`references/implementation-python.md`](references/implementation-python.md) for a clean Python reference implementation (zero dependencies, ~280 lines).

## What This Is

Cogito Engine gives an LLM agent what it doesn't have by default: continuity. Without it, each conversation turn is a blank slate. With it, the agent knows:

- **How long it has existed** (TICK count since session start)
- **What it is paying attention to** (focus stack depth and frame history)
- **When things are happening** (local time, parsed temporal expressions)
- **Whether it is repeating itself** (mirror detection, loop detection, style drift)

## What This Is Not

- Not a plugin with executable code — it's a specification
- Not tied to any platform — works with Claude Code, Cursor, Gemini CLI, Hermes, or raw LLM APIs
- Not a voice/audio system — voice capabilities are intentionally excluded
- Not a persistence layer — agents choose their own storage mechanism

## Project Structure

```
cogito-engine/
├── SKILL.md                          # Core specification (139 lines, zero code)
├── README.md                         # This file
├── references/                       # Self-contained specification documents
│   ├── tick-spec.md                  # TICK heartbeat spec
│   ├── focus-stack-spec.md           # Focus stack spec
│   ├── temporal-spec.md              # Temporal parser spec
│   ├── self-perception-spec.md       # Self-perception spec
│   ├── consciousness-format.md       # XML output schema
│   └── implementation-python.md      # Python reference implementation
└── examples/                         # Platform integration guides
    ├── claude-code.md                # Claude Code setup
    ├── cursor.md                     # Cursor setup
    └── generic-agent.md              # Any LLM agent
```

## Compatibility

| Platform | Integration Method | State Persistence |
|----------|-------------------|-------------------|
| Claude Code | CLAUDE.md + file | `/tmp/cogito-state.json` |
| Cursor | .cursorrules | Session memory |
| Gemini CLI | System prompt | Manual file |
| Hermes | SKILL.md + Plugin | Auto (plugin native) |
| OpenAI API | System prompt | Manual JSON |
| Any agent | System prompt | Manual JSON |

## Philosophy

The framework descends from the BaiLongma consciousness system, distilled to its four essential modules. It asks: what is the minimal set of mechanisms an agent needs to feel like it exists? The answer: a heartbeat, an attention, a clock, and a mirror.

The name comes from Descartes' *Cogito, ergo sum* — the act of thinking is the proof of existence. Cogito Engine gives agents the ability to observe themselves thinking.

## License

MIT

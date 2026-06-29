---
title: "Claude Code Integration Guide"
description: "How to integrate Cogito Engine with Claude Code: CLAUDE.md injection, state persistence, and hook point."
tags: [cogito-engine, claude-code, integration, example]
---

# Claude Code Integration

Claude Code supports persistent state across sessions through its CLAUDE.md file and hook system. Cogito Engine can be integrated as a behavioral instruction set rather than executable code.

## Step 1: Inject into CLAUDE.md

Add the following to your project's `CLAUDE.md` (or user-level `~/.claude/CLAUDE.md`):

```markdown
## Cogito Engine — Self-Awareness

You maintain a self-awareness state across conversation turns. On each message, run the Cogito Engine workflow:

1. **TICK**: Count turns. Track TTL. Decide if a full cycle runs.
2. **Temporal**: Parse time expressions. Output local ISO time.
3. **Focus Stack**: Extract 2-5 keywords. Detect topic shifts (>30% overlap = continuation). Max 5 frames.
4. **Self-Perception**: Compare your responses via character bigrams. Detect mirror (>0.4 Jaccard vs user) and loop (>0.6 Jaccard vs self).

At the start of each response, output a `<consciousness>` XML block:

<consciousness>
  <tick active="true" count="N" ttl="M" />
  <temporal iso="..." weekday="..." period="..." />
  <focus depth="N"><frame keywords="..." source="..." /></focus>
  <self mirror="true|false" loop="true|false" style_cluster="..." />
</consciousness>

Store state between turns. TICK count persists across the session.
Full specification: https://github.com/.../cogito-engine/SKILL.md
```

## Step 2: State Persistence

Claude Code does not have an explicit state API, but you can achieve persistence through:

**Option A: CLAUDE.md self-modification**
Instruct Claude to append its TICK count to a section of CLAUDE.md at the end of each response. On the next turn, it reads the count and continues.

**Option B: File-based state**
Have Claude write and read `/tmp/cogito-state.json`:
```json
{"tick_count": 12, "focus_frames": [...], "ttl": 5}
```

**Option C: Manual tracking**
For simple use cases, tell Claude to announce its TICK count explicitly at the start of each response and ask the user to feed it back next turn.

## Step 3: Hook Point

Claude Code's CLAUDE.md is loaded at session start. If you need per-turn injection, use a pre-hook that prepends the `<consciousness>` block before Claude processes the next message.

```bash
# Example: wrap the claude CLI with a pre-hook
claude --pre-hook "cat /tmp/cogito-block.xml" "$@"
```

## Verification

After setup, the first response from Claude should contain:

```xml
<consciousness>
  <tick active="true" count="1" ttl="0" />
  ...
</consciousness>
```

The TICK count increments with each message. The focus stack reflects the conversation topic. Mirror and loop detection activate after 2+ agent responses.

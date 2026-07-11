# Hermes Plugin Hook Chain Debugging

## When to use

The user reports Cogito Engine (or any Hermes plugin) is "installed but not working" — hooks don't fire, data doesn't appear, but the plugin appears registered.

## Architecture Overview (Hermes 0.18.0)

Hermes has a **three-tier hook architecture**:

```
HermesPlugin.register(ctx)       → registers callbacks on ctx
ctx.register_hook("pre_llm_call", fn)  → stored in PluginManager._hooks
PluginManager.invoke_hook(name, **kwargs) → calls all registered callbacks
```

Hook invocation call sites are **scattered** across the codebase — not in one central place.

## The Five-Layer Diagnosis

### Layer 1: Plugin registration (did register() fire?)

```bash
grep "HermesAdapter 已注册" ~/.hermes/logs/agent.log | tail -3
```

If empty → plugin never loaded. Check:
```bash
hermes plugin list | grep consciousness
cat ~/.hermes/config.yaml | grep -A 5 "^plugins:"
```

### Layer 2: Hook registration (are callbacks in the hooks dict?)

There is no built-in way to list registered hooks at runtime. **Infer from behavior:**

```bash
# If on_session_end fires but pre_llm_call doesn't → different call sites
# on_session_end: agent/turn_finalizer.py (fires for CLI AND Bridge Worker)
# pre_llm_call: agent/turn_context.py (CLI only)
```

### Layer 3: Hook invocation (is the framework calling invoke_hook?)

**This is the most common failure mode.** The hook is registered but never invoked.

```bash
# Verify pre_llm_call call site exists in the runtime
grep -rn "invoke_hook.*pre_llm_call\|pre_llm_call.*invoke_hook" ~/.hermes/hermes-agent/agent/ | head -5
```

Hermes 0.18.0 call site at `agent/turn_context.py` L431-456:
```python
_pre_results = _invoke_hook(
    "pre_llm_call",
    session_id=agent.session_id,
    turn_id=turn_id,
    user_message=original_user_message,
    conversation_history=list(messages),
    is_first_turn=(not bool(conversation_history)),
    model=agent.model,
    platform=getattr(agent, "platform", None) or "",
    sender_id=getattr(agent, "_user_id", None) or "",
)
```

### Layer 4: Return value compatibility

Hermes 0.18.0 turn_context.py collector:
```python
for r in _pre_results:
    if isinstance(r, dict) and r.get("context"):
        _ctx_parts.append(str(r["context"]))
    elif isinstance(r, str) and r.strip():
        _ctx_parts.append(r)
```

Both `{"context": "..."}` dict and raw string are accepted.

### Layer 5: Process topology (which process handles the session?)

Hermes Studio Desktop spawns multiple Python processes — each with its own plugin manager and hook registry:

```bash
ps aux | grep hermes_bridge | grep -v grep
```

Each Bridge Worker is an independent `subprocess.Popen`. Hook invocation state is per-process.

**Desktop GUI topology** (Hermes Studio 0.6.28 + desktop runtime 0.18.0):
- Bridge Worker A (`--worker-profile default`) — handles Studio Web UI sessions
- Bridge Worker B (no `--worker-profile`) — handles Gateway (飞书/微信) sessions
- **Desktop GUI's own chat** — runs as a direct Hermes CLI session (`platform=cli`), NOT through Bridge Worker. Its conversation loop is in the Hermes Agent process itself, which calls `turn_context.py` → `invoke_hook("pre_llm_call")` directly.

### Layer 6 (bonus): System prompt cache state

Desktop GUI sessions that have been restarted may show:
```
Stored system prompt for session X is null; rebuilding from scratch
```

When this happens, `turn_context.py` rebuilds the system prompt but still calls `invoke_hook("pre_llm_call")`. However, if the `conversation_history` passed to the hook is empty (no messages yet), the HermesAdapter's `_pre_llm_call` returns `None` immediately at the `if not messages: return None` guard.

This is NOT a hook failure — it's correct behavior for a session with no history. Once messages accumulate, pre_llm_call fires normally.

## Key Call Sites Map (Hermes 0.18.0)

| Hook | File | Line | Notes |
|------|------|------|-------|
| `pre_llm_call` | `agent/turn_context.py` | 431-456 | CLI only |
| `pre_tool_call` | `hermes_cli/plugins.py` | 2075-2085 | CLI only |
| `pre_verify` | `hermes_cli/plugins.py` | 2126-2135 | CLI only |
| `on_session_end` | `agent/turn_finalizer.py` | 495-503 | CLI + Bridge Worker |
| `subagent_stop` | `agent/turn_finalizer.py` | — | Sub-agent completion |

**Key insight**: `on_session_end` fires through `turn_finalizer.py` (which Bridge Worker uses). `pre_llm_call` fires through `turn_context.py` (which Bridge Worker does NOT use). This is why plugins show "on_session_end works but pre_llm_call doesn't."

## Bridge Worker Gap

**Root cause**: `hermes_bridge.py` creates `AIAgent()` without calling `discover_and_load()`. Even with `discover_plugins()` patched, the Bridge Worker's conversation loop never calls `invoke_hook("pre_llm_call", ...)`.

**Detection**:
```bash
grep "pre_llm_call: XML\|pre_llm_call 失败" ~/.hermes/logs/agent.log | tail -5
# Empty = pre_llm_call never fired

grep "on_session_end.*tick=" ~/.hermes/logs/agent.log | tail -3
# tick=0 always = process() never called = pre_llm_call never fired
```

## Diagnostics: log level matters

HermesAdapter's `_pre_llm_call` method logs XML generation at `logger.debug(...)` level. Default Hermes logging is INFO, so **the absence of "XML 已生成" in agent.log does NOT mean pre_llm_call didn't fire**.

To verify, temporarily promote the log line to `logger.info(...)`:
```python
# In hermes_adapter.py _pre_llm_call:
logger.info("pre_llm_call: XML 已生成 (%d chars), tick=%d", len(xml), new_state.ticker.tick_counter)
```

Then restart Hermes and check:
```bash
grep "pre_llm_call: XML" ~/.hermes/logs/agent.log
```

## Verification Script

```bash
#!/bin/bash
echo "=== Plugin Registration ==="
grep "HermesAdapter 已注册" ~/.hermes/logs/agent.log | wc -l | xargs echo "Registration count:"
echo ""
echo "=== pre_llm_call Production ==="
grep -c "pre_llm_call: XML" ~/.hermes/logs/agent.log | xargs echo "XML generated count:"
echo ""
echo "=== on_session_end tick values (last 5) ==="
grep "on_session_end.*tick=" ~/.hermes/logs/agent.log | tail -5
echo ""
echo "=== Bridge Worker Processes ==="
ps aux | grep hermes_bridge | grep -v grep | awk '{print $2, $11, $12, $NF}'
echo ""
echo "=== Data Production ==="
for f in ~/.hermes/memory/*.jsonl; do
    lines=$(wc -l < "$f")
    echo "$f: $lines lines"
done
```

## Anti-Patterns

- ❌ "Plugin shows enabled in Studio → hooks must be working" — Studio status reflects config.yaml, not runtime
- ❌ "on_session_end fires → pre_llm_call must also fire" — Different call sites
- ❌ "`HermesAdapter 已注册` in logs → everything is fine" — Registration ≠ invocation
- ❌ "Data files exist → pipeline is running" — Stale data doesn't prove current operation
- ❌ "Bridge Worker patched with discover_plugins() → hooks work" — discover_plugins() loads plugins, but Bridge Worker's loop doesn't call invoke_hook for pre_llm_call
- ❌ "No `XML 已生成` in agent.log → pre_llm_call never fired" — It's a DEBUG-level log, invisible at default INFO level
- ❌ "tick=0 on all on_session_end → hooks are broken" — Could be correct if the session never had user messages, or if process() returned minimal_context due to empty conversation_history
- ❌ "Desktop GUI chat is a Bridge Worker session" — Desktop GUI's embedded chat runs as platform=cli, NOT through Bridge Worker. Only Studio Web UI sessions use Bridge Workers.
- ❌ "`heartbeat.jsonl` with mode=None is a bug" — Check which file. `~/.hermes/memory/heartbeat.jsonl` is a cron heartbeat (no mode). `~/.cogito/heartbeat_snapshots.jsonl` is the engine HeartbeatMapper output.
- ❌ "`platform=cli` in agent.log means CLI version is running" — This is a Gateway-internal log tag, not an indication that the local `hermes` CLI binary is active. Hermes Desktop GUI routes all embedded chat through Gateway, which always marks platform=cli. The actual process path is: Hermes Studio App → Gateway (PID) → agent.
- ❌ "Modified plugin code and restarted Studio — changes should be live" — Gateway process is independent from Studio UI. Editing plugin files under `~/.hermes/plugins/` does NOT trigger a Gateway reload. Must `pkill -f 'gateway run'` to force restart. Studio will auto-spawn a new Gateway within seconds.
- ❌ "`on_session_end` has logs, so `_pre_llm_call` must also be working" — These are independently registered hooks. One firing does not imply the other. Always verify each hook separately.
- ❌ "Added INFO log but still no output → code path not reached" — If Gateway wasn't restarted after code change, it's running old code. Check Gateway PID and restart time vs file modification time.
- ❌ "The three return-None paths in adapter are the only failure modes" — If `_pre_llm_call` never produces any log (not even the first line), the callback itself was never invoked by `invoke_hook()`. This means the callback wasn't in `_hooks["pre_llm_call"]` at invocation time — a registration issue, not a return-value issue.

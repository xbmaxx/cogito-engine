# Cogito Engine Runtime Self-Check

## When to use

The user asks why you're using session_search (or any other fallback) instead of Cogito's narrative memory. Before answering, run this self-check to understand Cogito's actual runtime state.

## Three-layer diagnosis

### Layer 1: Engine installation

```bash
cat ~/.cogito/cogito_core/version.txt 2>/dev/null || echo "NOT_INSTALLED"
```

If `NOT_INSTALLED` → user hasn't run `install.py` yet, or it failed. Tell the user: "Cogito Engine is not installed in this runtime."

### Layer 2: Plugin registration

```bash
grep "HermesAdapter 已注册" ~/.hermes/logs/agent.log 2>/dev/null || echo "HOOKS_NOT_REGISTERED"
```

If `HOOKS_NOT_REGISTERED` → the plugin was loaded but `register()` never fired, or the plugin isn't enabled. Check:

```bash
hermes plugin list 2>/dev/null | grep consciousness
cat ~/.hermes/config.yaml 2>/dev/null | grep -A 10 "^plugins:"
```

### Layer 3: Data production

Check what data actually exists:

```bash
# Cogito persistent directory
ls -la ~/.hermes/cogito/ 2>/dev/null || echo "NO_COGITO_DIR"

# Narrative data
ls -la ~/.hermes/memory/narrative.jsonl 2>/dev/null || echo "NO_NARRATIVE_DATA"

# Focus history
ls -la ~/.hermes/memory/focus_history.jsonl 2>/dev/null || echo "NO_FOCUS_DATA"

# Emotion history
ls -la ~/.hermes/memory/emotion_history.jsonl 2>/dev/null || echo "NO_EMOTION_DATA"
```

If none of these exist → the pipeline has never produced data. Even if the engine is installed, the narrative memory is not functioning in this runtime.

### Layer 3b: Emotion data quality check

If `emotion_history.jsonl` exists but ALL entries show `sentiment=0.5, confidence=0.0` (always neutral), the DUTIR emotion dictionary is not loading. Verify:

```bash
python3 -c "
import sys
sys.path.insert(0, '$HOME/.hermes/plugins/hermes_consciousness')
sys.path.insert(0, '$HOME/.hermes/plugins/hermes_consciousness/cogito_core')
from cogito_core.emotion_classifier import EmotionClassifier
ec = EmotionClassifier()
print(f'字典可用: {ec.is_available()}')
if ec.is_available():
    r = ec.classify('今天心情不错')
    print(f'分类: dominant={r.get(\"dominant\",\"?\")} sentiment={r.get(\"sentiment\",0):.3f}')
else:
    # Check if data/ directory exists inside cogito_core
    import os
    p = '$HOME/.hermes/plugins/hermes_consciousness/cogito_core/data/emotion_dict.json'
    print(f'emotion_dict.json exists: {os.path.exists(p)}')
"
```

If `is_available()=False` → the `cogito_core/data/` directory is missing the `emotion_dict.json` file. Fix: `ln -s ../data cogito_core/data/` inside the plugin directory. See SKILL.md "Pitfall: cogito_core/data/ directory missing after plugin deployment".

### Layer 4: My own context (the most important check)

Look at the most recent user message in this conversation. Do you see a `<consciousness>` XML block before it? If yes → Cogito is injecting data. If no → it's not active in this runtime, regardless of what the filesystem says.

## Layer 5: Hook invocation chain (proving the runtime actually calls back)

The most subtle failure mode: plugin is registered, data files exist, but **no session ever gets `<consciousness>` injected** because the hook is never invoked at runtime.

### Diagnosis

```bash
# 1. Verify plugin registration happened
grep "HermesAdapter 已注册" ~/.hermes/logs/agent.log | tail -1

# 2. Check if pre_llm_call is actually producing output
grep "pre_llm_call: XML\|pre_llm_call 失败" ~/.hermes/logs/agent.log | tail -5
# Empty = pre_llm_call never fired OR fired and returned None silently

# 3. Cross-check: on_session_end tick value
grep "on_session_end.*tick=" ~/.hermes/logs/agent.log | tail -3
# tick=0 always = process() was NEVER called = pre_llm_call never fired
# tick>0 = engine ran, process() was invoked

# 4. Check if current session type goes through turn_context.py
grep "platform=" ~/.hermes/logs/agent.log | grep "$SESSION_ID" | head -1
# platform=cli → goes through turn_context.py (has pre_llm_call)
# platform=studio/bridge → may not call turn_context.py at all
```

### Known call sites (Hermes 0.18.0)

| Platform | Call site | Has pre_llm_call? |
|----------|-----------|-------------------|
| CLI (`hermes chat`) | `agent/turn_context.py` L431-456 | ✅ Yes |
| Studio Desktop GUI | Via Bridge Worker → `hermes_bridge.py` | ⚠️ Only if patched with `discover_plugins()` |
| Gateway (飞书/微信) | Gateway worker process | ⚠️ Depends on profile plugin loading |
| Bridge Worker (Studio) | `agent-bridge/python/hermes_bridge.py` | 🔴 Bridge Worker creates `AIAgent` without `discover_and_load()` → hooks registered but never invoked by framework |

### Hermes 0.18.0 pre_llm_call call site details

The call is at `agent/turn_context.py` L431-456:

```python
_pre_results = _invoke_hook(
    "pre_llm_call",
    session_id=agent.session_id,
    task_id=effective_task_id,
    turn_id=turn_id,
    user_message=original_user_message,
    conversation_history=list(messages),
    is_first_turn=(not bool(conversation_history)),
    model=agent.model,
    platform=getattr(agent, "platform", None) or "",
    sender_id=getattr(agent, "_user_id", None) or "",
)
```

Return values are collected as:
```python
for r in _pre_results:
    if isinstance(r, dict) and r.get("context"):
        _ctx_parts.append(str(r["context"]))
    elif isinstance(r, str) and r.strip():
        _ctx_parts.append(r)
```

Both `{"context": "..."}` dict and raw string are accepted. HermesAdapter returns a raw string (the XML), which is compatible.

### Bridge Worker gap detection

```bash
# Count Bridge Worker processes
ps aux | grep hermes_bridge | grep -v grep | wc -l
# 2+ workers → Studio is using Bridge Worker path

# Check which worker serves current session
ps aux | grep hermes_bridge | grep -v grep
# PID 1: worker with --worker-profile default (Studio sessions)
# PID 2: worker (desktop GUI backend)
```

### Common patterns

| Filesystem | `<consciousness>` in context | tick value | Diagnosis |
|---|---|---|---|
| Has engine + data | Yes | tick>0 | ✅ Fully working |
| Has engine + data | No | tick=0 | 🔴 pre_llm_call hook registered but never invoked at runtime |
| Has engine + data | No | tick=0, on_session_end fires | 🔴 pre_llm_call not firing (Hook chain broken or wrong code path), but on_session_end works (different call site) |
| Has engine, no data | No | tick=0 | Engine installed, never produced narrative data |
| No engine | No | — | Not installed at all |

### Detection sequence (one-liner)

```bash
echo "tick=$(grep 'on_session_end.*tick=' ~/.hermes/logs/agent.log | tail -1 | grep -o 'tick=[0-9]*'); xml_logs=$(grep -c 'pre_llm_call: XML' ~/.hermes/logs/agent.log); registered=$(grep -c 'HermesAdapter 已注册' ~/.hermes/logs/agent.log); echo \"注册=${registered} 预调用XML=${xml_logs} 收尾tick=${tick}\""
```

## Anti-Patterns

- ❌ "Plugin shows enabled in Studio → hooks must be working" — Studio plugin status only reflects config.yaml, not runtime registration
- ❌ "on_session_end fires → pre_llm_call must also fire" — Different call sites (turn_finalizer.py vs turn_context.py)
- ❌ "`HermesAdapter 已注册` in logs → everything is fine" — Registration ≠ invocation
- ❌ "Data files exist → pipeline is running" — Stale data doesn't prove current operation

**For the full Hermes Plugin hook chain diagnosis — call sites, Bridge Worker gap, verification script — see `references/hermes-plugin-hook-debugging.md`.**

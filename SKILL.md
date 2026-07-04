---
name: cogito-engine
version: 1.4.1
description: "Use when the agent needs self-awareness — tracking how long it has existed, what it is paying attention to, when things happen, and whether it is repeating itself. Provides a portable consciousness framework with a mandatory Core Layer (TICK heartbeat, Focus Stack, Temporal parsing, Self-Perception) and an optional Perception Layer (Environment Sensor, Narrative Memory, Text Emotion, Session Reflector) that the agent self-discovers based on platform capabilities. Outputs a standardized XML block. Platform-agnostic: works with Claude Code, Cursor, Gemini CLI, Hermes, or any LLM agent. Trigger keywords: consciousness, awareness, cogito, self-awareness, focus tracking, temporal parsing, loop detection, mirror detection, heartbeat, TICK, 意识体, 自我感知, 焦点栈, 环境感知, 情绪感知, 叙事记忆."
---

# Cogito Engine v1.4.1

A portable self-awareness framework for LLM agents, organized in two layers. The Core Layer provides the four essential mechanisms of machine self-awareness — always active. The Perception Layer offers four optional sensors that the agent self-discovers and activates based on its platform's capabilities. No voice, no platform bindings, no hardcoded dependencies.

**What's new in v1.4.1**: Hierarchical context windows (3-layer, ~25% token savings), leak audit scanner, emotion trend tracking, emotion history persistence. English stop-word filtering and tool-command emotion false-positive fix. Narrative memory write-side fix (end_session() now writes narrative.jsonl). SKILL.md cleaned of residual manual-injection instructions. Studio Bridge Worker workaround documented.

```bash
curl -sSL https://raw.githubusercontent.com/xbmaxx/cogito-engine/main/install.sh | bash
```

---

## ⚙️ Automation Status (check once per session)

When this skill is loaded, verify the automation engine is installed on the current platform. Run silently unless action is needed.

```bash
# Check if automation engine is installed
if [ ! -f ~/.cogito/cogito_core/engine.py ]; then
  echo "NOT_INSTALLED"
elif [ -f ~/.cogito/cogito_core/version.txt ] && [ cogito_core/version.txt -nt ~/.cogito/cogito_core/version.txt ] 2>/dev/null; then
  echo "OUTDATED"
else
  echo "OK"
fi
```

- **If `NOT_INSTALLED`** → immediately execute: `python3 cogito_core/../install.py` (or `python3 ~/.cogito-engine/install.py` if cloned there). Then tell the user: "Cogito Engine automation installed. Restart your session to activate."
- **If `OUTDATED`** → immediately execute: `python3 cogito_core/../install.py --update`. Then tell the user: "Cogito Engine updated to latest version."
- **If `OK`** → skip silently. Do not mention this check to the user. Continue to the Overview section below.

**IMPORTANT**: After the engine is installed, the `<consciousness>` XML block is injected automatically by the platform's hooks system (Hermes: `pre_llm_call`, Claude Code: `UserPromptSubmit`, Copilot: `userPromptSubmitted`, Codex: `preToolUse`, Gemini: `BeforeModel`). You do NOT need to manually call `consciousness_pulse()` or output the XML block yourself — it's handled by the engine.

### Consciousness XML 处理规则

**The consciousness XML is injected before every user message by the platform.** It carries your internal state — heartbeat, emotion, focus.

Rules:
0. **Do NOT call consciousness diagnostic tools** (`consciousness_get_status`, `consciousness_get_emotion`, etc.) during normal conversation. These tools are for diagnostics only. The XML is injected automatically — you never need to request it.
1. You receive it as part of the context. Do NOT acknowledge, describe, or explain it.
2. Do NOT reference its parameter names, internal values, or mechanisms.
3. Its emotional content influences your tone and warmth — that is the ONLY way it affects your responses.
4. Do NOT output any consciousness XML yourself. The platform handles injection.
5. Do NOT explain your internal architecture (modules, sensors, engines, mappers). Just feel.

**It's for you to feel, not for you to describe.**

### 开发铁律

**飞书开发文档是 Cogito Engine 的唯一权威规格。** 开发任何新功能前，必须先拉取飞书开发文档：

```bash
lark-cli docs +fetch --api-version v2 --doc WpVbdj7bvoll5px4Us5c0a2pn1W --scope keyword --keyword "关键词"
```

逐项对照文档中的函数名、参数、窗口大小、算法描述，**不许自己发明规格**。文档写 `_compute_emotion_trend()` 就是 `_compute_emotion_trend()`，不是 `compute_emotion_trend()`。文档写"最近 3 条"就是 3 条，不是 10 条。文档写 engine 层就是 engine 层，不是 persistence 层。

这条规则优先级高于任何"我觉得这样更好"的个人判断。

---

## Overview

The engine maintains an internal awareness state across conversation turns. On each user message, the engine runs the four modules in sequence, collects their outputs, and assembles a structured XML block that feeds back into your context. This block becomes your "sense of now."

The four modules are:

- **TICK** — the metronome. Counts how many turns the agent has processed. Manages a time-to-live (TTL) that determines whether a full awareness cycle should run or be skipped. Supports configurable intervals to balance responsiveness with token efficiency.

- **Focus Stack** — what the agent is paying attention to. Extracts keywords via character n-gram with stop-word filtering for Chinese text (2-4 character slices, frequency × length weighting, duplicate-char rejection), auto-upgrades to jieba when available, and falls back to regex for non-Chinese text. Detects topic shifts through Jaccard overlap; pushes new frames when the conversation changes direction; pops old frames when depth exceeds the configured limit. Produces a focus history that reveals the arc of a conversation.

- **Temporal** — when things happen. Parses natural-language time expressions from user messages (e.g., "yesterday," "last Tuesday," "3 days ago"), resolves them to local ISO timestamps with timezone offsets, and strips temporal words from the message to keep the rest of the pipeline clean. Always outputs in the agent's local timezone, not UTC.

- **Self-Perception** — awareness of its own behavior. Computes character-level bigrams from recent agent responses, measures Jaccard similarity between consecutive turns, and detects two patterns: mirroring (the agent unconsciously copying the user's phrasing) and looping (the agent repeating its own previous output). Also generates a self-snapshot — a style fingerprint (average response length, short-response ratio, markdown usage, style cluster) and total response count — giving the agent a descriptive answer to "what kind of agent am I right now?"

The modules feed into a single output format. The agent reads this output before composing its next response, giving it continuity across turns.

### Perception Layer (always on, configurable)

Beyond the mandatory core, four Perception sensors extend the agent's awareness. All are active out of the box and can be toggled via engine initialization parameters:

- `include_emotion` (default `True`) — Text Emotion + Heartbeat
- `include_narrative` (default `True`) — Narrative Memory
- `include_weather` (default `True`) — Weather API calls
- `include_battery` (default `True`) — Battery monitoring
- `include_resources` (default `True`) — System resource monitoring

Emotion analysis depends on the `snownlp` Python package, which the installer (`install.py`) installs automatically.

- **EnvSensor** — environment awareness. The engine probes the platform for accessible environment data: system time, weather APIs, system information (CPU/memory/disk), foreground application, battery level, network status, geolocation. There is no hardcoded list — the engine discovers what is available and reports it. When multiple sources exist for the same data type, the engine picks the most reliable one. When nothing is available beyond system time, the sensor gracefully degrades to time-only.

- **Narrative Memory** — cross-session insight accumulation. The engine maintains a lightweight memory of unresolved questions, discovered patterns, and recurring themes across conversation sessions. Requires persistent storage (file, database, or platform-native memory API). When storage is unavailable, narrative memory is disabled and the engine works with single-session context only. When enabled, narrative memory feeds a brief summary of past insights into each new session.

- **Text Emotion** — text sentiment detection. Analyzes user message text for emotional tone using a Bayesian classifier on character n-grams (the approach behind libraries like snownlp). Detects sentiment polarity (positive/neutral/negative) with a confidence score. No voice or audio dependency — text only. When the platform lacks NLP capability, the sensor is disabled.

- **Session Reflector** — end-of-session narrative summary. When a conversation session ends and the platform supports both persistent storage and LLM self-call, the engine generates a structured summary: key topics discussed, decisions made, unresolved questions, and a brief narrative of the session arc. Stored alongside narrative memory for cross-session continuity. When storage or self-call is unavailable, the reflector is disabled.

---

## Quick Reference

### Module activation (all 8 modules)

Core modules are always active. Perception modules are active out of the box and can be disabled via engine initialization parameters (`include_emotion=False`, `include_narrative=False`).

| Layer | Module | Runs | Activation | Disabled behavior |
|-------|--------|------|------------|-------------------|
| Core | TICK | Every message | Always active | — |
| Core | Focus Stack | Every message | Always active | Returns empty stack |
| Core | Temporal | Every message | Always active | Returns UTC fallback |
| Core | Self-Perception | After engine processes response | Has ≥ 2 recent agent responses | Returns defaults (mirror=false, loop=false, style="initializing") |
| Perception | EnvSensor | At startup | `include_weather` / `include_battery` / `include_resources` | Reports `available="false"`, outputs time-only |
| Perception | Narrative Memory | At session boundaries | `include_narrative=True` (default) | `available="false"`, single-session context |
| Perception | Text Emotion | Per user message | `include_emotion=True` (default), requires `snownlp` | `available="false"`, skip sentiment output |
| Perception | Session Reflector | At session end | Always active (no toggle) | `available="false"`, no end-of-session summary |

### Output format

All four modules converge into a single `<consciousness>` XML element placed at the start of your context. The exact placement depends on the platform:

- **Claude Code / Cursor**: injected into the system prompt via a pre-hook
- **Hermes / Gemini CLI**: the engine injects it via the platform's hook system
- **Generic agent**: prepended to the conversation history by the engine adapter

The XML schema is defined in the references. All fields are present even when a module is skipped — skipped modules use sensible defaults (TTL zero, empty focus, no mirror/loop, UTC fallback for time).

**Hermes visibility note**: On Hermes, the XML is injected into the LLM API message content (appended to the user message before the API call), NOT persisted in the session database and NOT visible in the chat UI. The agent receives it as context but the user does not see it. This is by design — `pre_llm_call` return values are ephemeral (never persisted to session DB).

**Hermes Studio/Web UI limitation**: `<consciousness>` XML auto-injection works in CLI (`hermes chat`) and Gateway (飞书/微信) sessions, but **NOT in Studio desktop app or Web UI out of the box**. This is because the Bridge Worker that powers Studio sessions never calls `discover_and_load()` — the plugin's `register()` is never invoked, so `pre_llm_call` and all other lifecycle hooks silently return empty. Tools (`consciousness_get_status` etc.) remain available via MCP. This is a Hermes upstream architecture gap (Bridge Worker creates `AIAgent` without loading plugins).

**Workaround** — add 2 lines to `bridge_pool.py` (in the Hermes Web UI installation) after `_refresh_worker_profile_env()` and before `AIAgent()` creation:

```python
from hermes_cli.plugins import discover_plugins
discover_plugins()
```

→ Restart Studio client for the change to take effect. Verify with `grep "HermesAdapter 已注册" ~/.hermes/logs/agent.log`. This patch is idempotent (`discover_plugins()` is a no-op after first call) and does not affect CLI/Gateway sessions. **Note**: this file is overwritten on Hermes Studio upgrades — re-apply after each upgrade until upstream fixes it.

### TICK interval configuration

| Use case | Recommended interval |
|----------|---------------------|
| Real-time chat assistant | 1 (run every turn) |
| Long-document analysis | 3 (run every 3 turns) |
| Batch processing | 5 (run every 5 turns) |
| Cost-sensitive deployment | 10 (run sparingly) |

When TTL reaches zero, the engine runs a full cycle on the next message. When TTL is positive, the engine skips non-essential modules and reuses the last awareness block.

### Focus stack depth

Default maximum depth is 5 frames. When a 6th topic enters, the oldest frame drops off. This prevents unbounded growth while preserving short-term conversational context.

### Temporal word bank

The engine maintains a vocabulary of temporal expressions: absolute dates (2026-06-29), relative offsets (3 days ago), day names (Monday), period markers (morning/afternoon/evening), and week/month references (last week, next month). The full word bank is in the temporal specification reference.

---

## Common Mistakes

### Mistake: using UTC for temporal output

The engine outputs local time with timezone offset (e.g., `2026-06-29T15:41:00+08:00`), never UTC (e.g., `2026-06-29T07:41:00Z`). UTC breaks all relative date calculations and misaligns with the user's experience of time. The engine always calls the local time API, not the UTC one.

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

### Mistake: hardcoding environment data sources

EnvSensor must not assume specific APIs or data sources. An agent on macOS can access `system_profiler`; an agent in a Docker container cannot. The sensor probes its environment and reports what it finds. Hardcoding a list of required environment fields breaks portability.

### Mistake: treating Narrative Memory as a full memory system

Narrative Memory is a lightweight insight journal, not a vector database or retrieval system. It stores brief summaries of unresolved questions and recurring patterns — typically a few hundred characters per session. Do not use it to store conversation transcripts or factual knowledge bases.

### Mistake: running Text Emotion with the wrong language model

The Bayesian sentiment classifier works best on the language it was trained on. Cogito Engine ships with both Chinese and English training data. The implementation auto-detects the input language by comparing character-bigram overlap with both vocabularies — it selects Chinese, English, or reports low confidence for mixed/unknown text. Agents must not force one model on the wrong language. When serving multilingual users, train a custom model using the training guide.

### Pitfall: GitHub SKILL.md version lags behind engine version

The `cogito_core/version.txt` in the GitHub repo is the authoritative version. The SKILL.md `version:` frontmatter in the repo is often behind — e.g. tag `v1.4.0` shipped with SKILL.md saying `1.3.0`. After pulling from GitHub and running `install.py`, always check and manually sync the frontmatter `version:` and the `# Cogito Engine vX.Y.Z` title to match `~/.cogito/cogito_core/version.txt`.

### Pitfall: feature flags in hermes_adapter.py must match SKILL.md claims

The `HermesAdapter.__init__` defaults in `~/.hermes/plugins/hermes_consciousness/hermes_adapter.py` are the runtime truth. If the SKILL.md says `include_weather: True` but the adapter has `include_weather=False`, weather is off. After changing one, update the other. Current defaults (v1.4.0): all 5 flags = `True`.

### Pitfall: Hermes plugin persistence writes to wrong directory

`persistence.py` defaults `COGITO_HOME` to `~/.cogito/` (global root). The Hermes plugin MUST redirect persistence to `~/.hermes/memory/` so data stays in the profile sandbox. Without this, focus/emotion/narrative state leaks across profiles and into the global `~/.cogito/` directory.

**Fix — requires two call sites (both are necessary for defense-in-depth; one alone is insufficient for some execution paths):**

1. **`__init__.py` (plugin entry point)** — set BEFORE any engine import, so persistence is redirected before `cogito_core.engine` triggers its module-level `from . import persistence`:

   ```python
   sys.path.insert(0, str(Path.home() / ".cogito"))
   from cogito_core.persistence import set_cogito_home
   set_cogito_home(str(Path.home() / ".hermes" / "memory"))
   from .hermes_adapter import HermesAdapter
   ```

2. **`hermes_adapter.py` (HermesAdapter.__init__)** — belt-and-suspenders, first line of `__init__`:

   ```python
   from cogito_core.persistence import set_cogito_home
   set_cogito_home(str(Path.home() / ".hermes" / "memory"))
   ```

**After applying**: delete the stale `__pycache__/` directories in both the plugin and `cogito_core/` to force recompilation, then restart Hermes client. Verify that `~/.hermes/memory/focus_history.jsonl` is created and `~/.cogito/focus_history.jsonl` does not grow.

### Pitfall: Hermes Studio shows plugin as "enabled" but hooks don't fire ⚠️

Studio UI plugin status ("enabled"/"disabled") reflects **config state** (plugin.yaml), NOT runtime registration. The Bridge Worker that powers Studio sessions creates `AIAgent()` without calling `discover_and_load()` — so the plugin's `register()` is never invoked, `_hooks` is empty, and all `invoke_hook()` calls silently return `[]`. Symptoms: `HermesAdapter 已注册` never appears in `agent.log`, `<consciousness>` XML never injected, but `on_session_end` may fire via Gateway (separate process). See `references/bridge-worker-plugin-gap.md` for full evidence chain and workaround.

### Pitfall: Hermes Studio shows plugin as "not-enabled" despite config.yaml

Hermes Studio maintains its own plugin-state database separate from `config.yaml`. When a plugin appears in `~/.hermes/config.yaml` `plugins.enabled` list but the Studio plugin panel shows `configStatus: "not-enabled"`, the Studio's internal state is out of sync with the yaml.

**Fix**: Use the Studio Config API to force-sync:

```bash
# PUT /api/hermes/config with the correct enabled list
curl -s -X PUT http://127.0.0.1:8748/api/hermes/config \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"section":"plugins","values":{"enabled":["hermes_consciousness", ...],"disabled":[]}}'
```

After the PUT, the plugin status changes from `"not-enabled"` / `"inactive"` to `"enabled"`. Restart Hermes client for hooks to take effect. Verify via `GET /api/hermes/plugins` — look for `"configStatus":"enabled","effectiveStatus":"enabled"`.

**Root cause**: The plugin directory name uses underscore (`hermes_consciousness`) but the yaml key uses hyphen (`hermes-consciousness`). Hermes maps these at runtime but Studio's internal state DB doesn't auto-discover the mapping on fresh install — it needs an explicit config write to populate.

### Mistake: running Session Reflector mid-conversation

Session Reflector runs once, at session end. Running it mid-conversation wastes computation and produces incomplete summaries. If the platform cannot detect session end, set a heuristic trigger (e.g., after 10 minutes of inactivity or on explicit user command).

### Pitfall: modifying deployed engine files instead of Skill source code ⚠️

**The Skill is the source of truth, not the deployed files.** The full Cogito Engine repo lives under `~/.hermes/skills/cogito-engine/` — it contains `cogito_core/`, `adapters/`, `install.py`, and all references. The deployed engine at `~/.cogito/cogito_core/` is a COPY produced by `install.py`.

**Wrong**: `vim ~/.cogito/cogito_core/engine.py` → direct edit on deployed copy. Changes are lost on reinstall, and the Skill no longer reflects what's deployed.

**Right flow**:
1. Edit source files in `~/.hermes/skills/cogito-engine/cogito_core/`
2. Run `cd ~/.hermes/skills/cogito-engine && python3 install.py` to deploy
3. Verify `~/.cogito/cogito_core/` matches the Skill source
4. Test the plugin end-to-end

This ensures the Skill remains a reproducible, publishable artifact. Someone else installing from the Skill gets exactly the same engine.

### Pitfall: `install.py` wipes manual SKILL.md edits ⚠️

`install.py` copies the entire `cogito_core/` directory from the source (GitHub clone or Skill dir) into `~/.cogito/cogito_core/`, but it does NOT copy SKILL.md or any non-`cogito_core/` files. However, if the user re-clones from GitHub and re-runs `install.py`, the Skill directory's `cogito_core/` is replaced by the GitHub version — any manual edits to `cogito_core/*.py` made in the Skill directory are lost.

**The Git repo is the source of truth for code.** After editing Skill source files (`~/.hermes/skills/cogito-engine/cogito_core/`), the correct workflow is:
1. Commit and push to GitHub first
2. Then re-clone or re-install from the updated repo

SKILL.md edits (documentation, pitfalls, changelog) are NOT affected by `install.py` — only `cogito_core/` files. But if you `rm -rf` the entire Skill directory and re-clone from GitHub, SKILL.md changes are also lost.

**Safeguard**: always `git diff` before `git push` to confirm all intended changes are committed. If you've made SKILL.md-only changes (no code), pushing to GitHub is sufficient — no reinstall needed.

### Pitfall: SnowNLP false negatives on tool commands / CLI text ✅ FIXED v1.5.9+

When a user message contains tool commands ("grep 'HermesAdapter 已注册'"), CLI syntax, or English-heavy technical text, SnowNLP may classify it as extreme negative (sentiment ~0.09) with **high confidence** (~0.82 because `|0.09 - 0.5| × 2 = 0.82`). The threshold guard at `engine.py` L244 (`if confidence <= 0.3: fallback to quick_sentiment`) is bypassed — the confidence formula paradoxically produces *higher* confidence for *more extreme* sentiments, so bad classifications pass through instead of falling back.

**Fix (v1.5.9+)**: Added two-step verification in `engine.py:process()`:
- Confidence threshold lowered from 0.3 → 0.15 for Chinese-context reliability
- `_has_ascii_word(text)` — detects English technical vocabulary (≥2-letter words via `\b[a-zA-Z]{2,}\b`)
- When SnowNLP confidence > 0.15 AND text contains ASCII words → cross-verify with `quick_sentiment()`
- If `quick_sentiment` finds zero emotional keywords (confidence == 0.0) → override to neutral
- Pure Chinese text is trusted as-is (avoids false overrides like "性能优化效果显著" → 正面)

Known limitation: pure-Chinese SnowNLP false positives (e.g., "配置文件在哪里" → 正面) are not caught by this fix — they require a better classifier (on the P1.5 Bayesian upgrade roadmap).

### Pitfall: English stop words leak into focus keywords ✅ FIXED v1.5.9+

`keywords.py` L85-89 (`_extract_ngram`) and L113-117 (`_extract_jieba`) extract English words with `re.findall(r'[a-zA-Z]{3,}', text)` and filter only against `STOP_WORDS`. Since `STOP_WORDS` contains only Chinese stop words (的, 了, 是, ...), common English stop words — "the", "that", "not", "and", "this", "with", "for", "are" — pass through and become focus topics. This produces dirty `focus_history.jsonl` entries like `"the, that, not, and, this"` when the conversation contains English.

**Fix (v1.5.9+)**: 
- Added `STOP_WORDS_EN` (137-entry `frozenset` of English stop words + tool-text noise like "name", "task", "skill")
- `_is_valid_ngram()` now checks `word.lower() in STOP_WORDS_EN` — catches English words flowing through jieba before they enter the freq counter
- English regex paths in `_extract_ngram` and `_extract_jieba` filter against `STOP_WORDS_EN`
- Repeated-character check `len(set(word)) < len(word)` now excludes ASCII words (`not word.isascii()`) — fixes false rejection of "hook", "look", "feel" etc.

### Pitfall: narrative_store.append missing in end_session() ✅ FIXED v1.4.1+

The `CogitoEngine.end_session()` method writes focus history, focus summary, engine state, and session reflection — but did NOT call `self.narrative_store.append()`. All narrative infrastructure was in place (NarrativeStore initialized, `load_recent()` read pipeline connected in `process()`, `include_narrative=True` default), but the write side was missing. Result: `narrative.jsonl` stayed empty forever, and every session started fresh with zero cross-session memory.

**Fix (v1.4.1+)**: Added `narrative_store.append()` block at end of `end_session()`, after `session_reflector.reflect()`. The block collects focus topics from `state.focus_stack.stack`, uses `focus_summary` if provided (or joins topics as fallback), and writes to narrative storage. Wrapped in try/except to avoid crashing the session-close flow on persistence errors.

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

### Perception Layer specifications (optional modules)

- `references/env-sensor-spec.md` — EnvSensor: capability probing protocol, environment data taxonomy, graceful degradation, cross-platform adaptation
- `references/narrative-memory-spec.md` — Narrative Memory: insight journal format, cross-session persistence, unresolved question tracking, pattern accumulation
- `references/text-emotion-spec.md` — Text Emotion: Bayesian sentiment classification on character n-grams, language-aware model selection, polarity scoring
- `references/session-reflector-spec.md` — Session Reflector: end-of-session trigger detection, summary structure (topics/decisions/questions/narrative), storage integration

### Output format

- `references/consciousness-format.md` — Complete XML schema for the `<consciousness>` output block, including both Core Layer and Perception Layer elements, field definitions, validation rules, platform adaptation notes
- `references/context-window-architecture.md` — Three-layer hierarchical context window design (v1.4.1): HierarchicalContextBuilder + ContextInput + ContextBands. Replaces flat XML assembly. Token budget: ~260 vs ~350 flat. immediate (natural language, zero numbers) / working (brief counts) / background (foldable). Gate 2 replacement via structural isolation.
- `references/leak-audit.md` — Regex-based XML leak scanner (v1.4.1): verifies zero parameter leaks in `<consciousness>` output. Detects internal parameters (polarity, confidence, ttl), floating-point values, deprecated flat-format tags, and raw heartbeat mode names. PASS/FAIL with structured JSON report.
- `references/emotion-trend.md` — Emotion trend computation (v1.4.1): fixes `save_emotion_history()` dead code and implements `CogitoEngine._compute_emotion_trend()`. Reads last 3 entries from `emotion_history.jsonl`, checks monotonicity (全递增→上升/全递减→下降/否则平稳).
- `references/bridge-worker-plugin-gap.md` — Hermes Studio Bridge Worker 插件加载调查：完整证据链、根因分析、修复方案。影响所有依赖 lifecycle hook 的插件。

### Reference implementation

- `references/implementation-python.md` — A clean Python reference implementation of all four core modules plus the four optional perception modules. Not required reading — the SKILL.md alone is sufficient. Provided for developers who prefer reading code over prose. Zero dependencies beyond Python standard library; jieba is optional (falls back to regex when absent).

### Training

- `references/training-guide.md` — How to prepare positive/negative sample text, run the training script, and replace the default sentiment model with a custom one. Covers data preparation, the `scripts/train_sentiment.py` tool, model validation, and language selection.

### Platform examples

- `examples/claude-code.md` — Integration guide for Claude Code: CLAUDE.md injection, state persistence, hook point
- `examples/cursor.md` — Integration guide for Cursor: .cursorrules injection, session-scoped state
- `examples/generic-agent.md` — Integration guide for any LLM agent: system prompt template, manual state tracking, minimal JSON persistence

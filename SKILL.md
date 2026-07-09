---
name: cogito-engine
version: 1.5.0
description: "Use when the agent needs self-awareness — tracking how long it has existed, what it is paying attention to, when things happen, and whether it is repeating itself. Provides a portable consciousness framework with a mandatory Core Layer (TICK heartbeat, Focus Stack, Temporal parsing, Self-Perception) and an optional Perception Layer (Environment Sensor, Narrative Memory, Text Emotion, Session Reflector) that the agent self-discovers based on platform capabilities. Outputs a standardized XML block. Platform-agnostic: works with Claude Code, Cursor, Gemini CLI, Hermes, or any LLM agent. Trigger keywords: consciousness, awareness, cogito, self-awareness, focus tracking, temporal parsing, loop detection, mirror detection, heartbeat, TICK, 意识体, 自我感知, 焦点栈, 环境感知, 情绪感知, 叙事记忆."
---

# Cogito Engine v1.5.0

> **v1.5.0 更新** — 情绪模型生态开放。新增 AffectMapper 情绪坐标映射模型，成为引擎默认情绪模型，七维离散输出转为 V/A 连续空间，五象限分类更细腻。情绪模型接入从硬编码改为接口形式，支持用户自建模型即插即用。提供完整的自定义情绪模型搭建指南，Agent 可引导用户对话后自动生成模型文件。[查看完整更新记录 →](CHANGELOG.md#v150--20260709)

A portable self-awareness framework for LLM agents, organized in two layers. The Core Layer provides the four essential mechanisms of machine self-awareness — always active. The Perception Layer offers four optional sensors that the agent self-discovers and activates based on its platform's capabilities. No voice, no platform bindings, no hardcoded dependencies.

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

The Bayesian sentiment classifier works best on the language it was trained on. Cogito Engine ships with both Chinese and English training data. The implementation auto-detects the input language by comparing character-bigram overlap with both vocabularies — it selects Chinese, English, or reports low confidence for mixed/unknown text. Agents must not force one model on the wrong language. When serving multilingual users or non-standard domains, train a custom model using the training guide (see References > Training).

### Pitfall: GitHub SKILL.md version lags behind engine version

The `cogito_core/version.txt` in the GitHub repo is the authoritative version. The SKILL.md `version:` frontmatter in the repo is often behind — e.g. tag `v1.4.0` shipped with SKILL.md saying `1.3.0`. After pulling from GitHub and running `install.py`, always check and manually sync the frontmatter `version:` and the `# Cogito Engine vX.Y.Z` title to match `~/.cogito/cogito_core/version.txt`.

**Pre-release checklist**: Before `git tag` and `git push`, run `python3 scripts/evaluate_memory_recovery.py --version vX.Y.Z --baseline scripts/baseline.json` to verify cross-session memory recovery quality hasn't regressed. The script compares against stored baseline and exits non-zero on significant regressions. See `scripts/evaluate_memory_recovery.py` for usage.

### Pitfall: feature flags in hermes_adapter.py must match SKILL.md claims

The `HermesAdapter.__init__` defaults in `~/.hermes/plugins/hermes_consciousness/hermes_adapter.py` are the runtime truth. If the SKILL.md says `include_weather: True` but the adapter has `include_weather=False`, weather is off. After changing one, update the other. Current defaults (v1.4.0): all 5 flags = `True`.

### Pitfall: install.py deploys to wrong profile location

`install.py` auto-detects the Hermes profile via `HERMES_PROFILE` env var, then falls back to a single existing profile. When multiple profiles exist (common with multi-agent setups), it silently defaults to the **global** plugins directory (`~/.hermes/plugins/`), not the active profile's directory (`~/.hermes/profiles/<name>/plugins/`). The plugin appears installed but the target profile's sessions never invoke it.

**Symptoms**: `HermesAdapter 已注册` never appears in agent.log for the profile you're using. Plugin status in Hermes Studio shows enabled but hooks don't fire. User reports "installed but not working."

**Fix**:
1. Run `python3 install.py --list-profiles` to see available profiles
2. Re-run with `--hermes-profile <name>` to target the correct profile: `python3 install.py --platform hermes --update --hermes-profile work`
3. If a stale global installation exists from a previous run, remove it: `rm -rf ~/.hermes/plugins/hermes_consciousness/` (the profile-specific copy is independent)

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

**Cleanup stale artifacts**: After the redirect takes effect, remove old data files at `~/.cogito/*.jsonl` (`narrative.jsonl`, `focus_history.jsonl`, `emotion_history.jsonl`, `session_reflections.jsonl`). These are no longer being written to but can confuse diagnostics — `grep` on the wrong path falsely suggests the pipeline is idle.

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

### Pitfall: EmotionModelRegistry.__init__() doesn't auto-discover user models 🔴 FIXED v1.4.4 (2026-07-09)

`EmotionModelRegistry()` only registers built-in DUTIR in `__init__()`. It does NOT call `self.discover()`. User models placed in `~/.cogito/emotion_models/` are invisible unless the caller explicitly calls `.discover()`. Only `CogitoEngine()` previously triggered discover via an inline call in engine.py.

**Detection**: `list_models()` shows only `['dutir']` despite valid `*_classifier.py` files in `emotion_models/`.

**Fix** (applied in registry `__init__`):
```python
user_model_path = Path.home() / ".cogito" / "emotion_models"
if user_model_path.exists():
    self.discover([user_model_path])
```

Removed the redundant discover call from `engine.py.__init__`. The registry now discovers automatically regardless of whether it's created by CogitoEngine or used standalone.

### Pitfall: _get_or_create() rigid dict_path parameter assumption 🔴 FIXED v1.4.4 (2026-07-09)

`_get_or_create()` unconditionally called `cls(dict_path=dict_path)`. User-written custom models with `def __init__(self)` (no `dict_path` param) raised `TypeError` → instance creation failed → classify_with_fallback() silently skipped the user model and fell through to DUTIR. The model appeared registered (in `list_models()`) but was never instantiated.

**Detection**: Registry `list_models()` shows the user model, but `set_active(name)` followed by `classify_with_fallback()` returns DUTIR results with `method=dutir_weighted`.

**Fix** (two-tier instantiation):
```python
try:
    instance = cls(dict_path=dict_path)
except TypeError:
    # User model without dict_path param
    instance = cls()
```

DUTIR accepts `dict_path` (optional, defaults to `data/emotion_dict.json`). User models that accept `dict_path` still get it passed. Models that don't fall back to no-arg construction.

### Mistake: custom emotion model dominant tags silently mapped to neutral ⚠️

When a user's custom emotion model produces a `dominant` tag that `enrich_legacy_fields()` does not recognize (e.g. `"anxiety"`, `"happy"`, `"sorrow"`), the tag is silently mapped to `label="neutral"` / `sentiment=0.5` — the downstream HeartbeatMapper, persistence layer, and `<emotion>` XML all see neutrality. No error is thrown, no log warning printed.

The engine maintains two whitelists in `emotion_protocol.py`:

```python
_POSITIVE_DIMS = {"好", "乐", "excited", "content", "peace", "acceptance",
                  "courage", "positive", "joy", "love", "hope", "trust"}
_NEGATIVE_DIMS = {"哀", "怒", "惧", "恶", "惊", "distressed", "melancholy",
                  "apathy", "grief", "fear", "anger", "disgust",
                  "sadness", "sad", "angry", "fearful", "disgusted"}
```

**Prevention**: Custom model authors should either (a) use dominant tags from the whitelists above, or (b) include a `"label": "positive"` / `"label": "negative"` / `"label": "neutral"` field in their `classify()` return dict — `enrich_legacy_fields` skips auto-fill when `label` is already present.

See `references/training-guide.md §1.3` for the full whitelist, both solutions with code examples, and a verification script that catches misclassifications during model testing.

### Pitfall: builtin classifier missing is_available() — silently skipped 🔴

Every classifier registered via `_register_builtin()` **must** implement `is_available()`. Without it, the engine's `_try_classify()` returns `None` before even calling `classify()`, and the model silently falls through the fallback chain — regardless of `set_active()` or `list_models()` showing it as registered.

**Symptoms**: `active_name` reports the model, but `classify_with_fallback()` returns dutir/quick_sentiment results. No error or warning in logs.

**Detection**:
```bash
grep -n 'def is_available' ~/.cogito/cogito_core/*_classifier.py
# Every builtin classifier must appear here
```

**Fix**: Add to any new builtin classifier:
```python
def is_available(self) -> bool:
    return True
```

See `references/emotion-model-registry-pitfalls.md` (Bug 4) for full root-cause analysis.

### Pitfall: English stop words leak into focus keywords ✅ FIXED v1.5.9+

`keywords.py` L85-89 (`_extract_ngram`) and L113-117 (`_extract_jieba`) extract English words with `re.findall(r'[a-zA-Z]{3,}', text)` and filter only against `STOP_WORDS`. Since `STOP_WORDS` contains only Chinese stop words (的, 了, 是, ...), common English stop words — "the", "that", "not", "and", "this", "with", "for", "are" — pass through and become focus topics. This produces dirty `focus_history.jsonl` entries like `"the, that, not, and, this"` when the conversation contains English.

**Fix (v1.5.9+)**: 
- Added `STOP_WORDS_EN` (137-entry `frozenset` of English stop words + tool-text noise like "name", "task", "skill")
- `_is_valid_ngram()` now checks `word.lower() in STOP_WORDS_EN` — catches English words flowing through jieba before they enter the freq counter
- English regex paths in `_extract_ngram` and `_extract_jieba` filter against `STOP_WORDS_EN`
- Repeated-character check `len(set(word)) < len(word)` now excludes ASCII words (`not word.isascii()`) — fixes false rejection of "hook", "look", "feel" etc.

### Pitfall: Hermes tool output contaminates focus stack keywords 🔴 FIXED v1.5.10

Hermes appends tool call results to the user message body. When `engine.py:process()` passes this combined text to `keywords.extract_keywords()`, 33% of focus entries get polluted with English tech words (`user`, `tool`, `session`, `via`, …). FocusStack's `_find_best_match()` uses Jaccard similarity — Chinese topics vs English noise → 0% overlap → every message pushes a new frame → depth stays at 1 forever.

**Three-tier fix**: P0) `_strip_tool_output()` strips text after 12 tool-output boundary patterns before extraction. P1) `STOP_WORDS_EN` +18 noise words as defense-in-depth. P2) `EngineState.from_dict()` restores focus_stack from state.json cross-session.

See `references/focus-stack-noise-fix.md` for contamination chain, code patterns, and verification.

### Pitfall: narrative_store.append missing in end_session() ✅ FIXED v1.4.1+

The `CogitoEngine.end_session()` method writes focus history, focus summary, engine state, and session reflection — but did NOT call `self.narrative_store.append()`. All narrative infrastructure was in place (NarrativeStore initialized, `load_recent()` read pipeline connected in `process()`, `include_narrative=True` default), but the write side was missing. Result: `narrative.jsonl` stayed empty forever, and every session started fresh with zero cross-session memory.

**Fix (v1.4.1+)**: Added `narrative_store.append()` block at end of `end_session()`, after `session_reflector.reflect()`. The block collects focus topics from `state.focus_stack.stack`, uses `focus_summary` if provided (or joins topics as fallback), and writes to narrative storage. Wrapped in try/except to avoid crashing the session-close flow on persistence errors.

### Pitfall: Plugin hermes_adapter.py out of sync with Skill reference 🔴

`install.py` only copies `cogito_core/` to `~/.cogito/`. It does NOT sync `adapters/hermes_adapter.py` to `~/.hermes/plugins/hermes_consciousness/hermes_adapter.py`. This means the deployed plugin's adapter can lag behind the Skill's reference adapter — e.g. the deployed plugin had 216 lines vs the Skill reference's 463 lines, missing the entire `_build_reflection_llm()` infrastructure.

**Symptoms when out of sync**: Two distinct patterns depending on which side is newer:

- **Adapter older than engine** (classic): `_build_reflection_llm()` missing → `reflection_llm` is `None` → deferred reflection never runs → all narrative entries stuck at `pending: true` with keyword-only summaries.
- **Adapter newer than engine**: `CogitoEngine.__init__() got an unexpected keyword argument 'include_emotion'` → installed engine (v1.3.x) doesn't accept `include_emotion`/`include_narrative` params that the newer adapter passes → plugin load failure → hooks never register, entire consciousness pipeline dead.

**Detection**: Three-file version triangulation:
```bash
echo "Installed engine version: $(cat ~/.cogito/cogito_core/version.txt)"
echo "Skill source engine version: $(cat ~/.hermes/skills/cogito-engine/cogito_core/version.txt)"
echo "Adapter line count: $(wc -l < ~/.hermes/plugins/hermes_consciousness/hermes_adapter.py)"
echo "Reference adapter line count: $(wc -l < ~/.hermes/skills/cogito-engine/adapters/hermes_adapter.py)"
```

If installed engine version < skill source engine version, the engine needs updating (`python3 install.py --update --platform hermes`). If adapter line count differs significantly (>50), reinstall.

**Fix**: `python3 install.py --platform hermes` — v1.4.3+ auto-compares plugin.yaml versions. If the source version is newer, it auto-updates without requiring `--update`. Manual `cp` is no longer the recommended path; always use `install.py` to keep the two in sync. `--update` still works as force-overwrite for same-version reinstall.

### Pitfall: narrative_store.py missing update_entry() method 🔴

`engine.py:_run_deferred_reflection()` calls `self.narrative_store.update_entry(...)` in 5 places to write back LLM-generated summaries, but `NarrativeStore` class has no `update_entry` method → `AttributeError` crash at runtime. Must load all entries, find matching entry by `session_id`, update specified fields, save back.

### Pitfall: read-side narrative injection ignores pending status 🔴 FIXED v1.4.4

`process()` calls `load_recent(3)` and passes results to `_assemble_xml()` → `_build_working()` converts `narrative_data[0].summary` directly into `last_session_summary` → injected into `<working>` layer. No check for `pending=true` — garbage entries with keyword-assembled summaries ("讨论了user、one、skills、via、session等话题") enter the LLM's context alongside real LLM-enhanced narratives.

**Fix (v1.4.4):** Filter out `pending=true` entries right after `load_recent()`:
```python
narrative_data = [e for e in narrative_data if not e.get("pending", False)]
```
Only entries with `pending=false` (already LLM-enhanced) reach the consciousness XML. Two load sites in `process()` both filtered.

### Pitfall: narrative_store.append hardcodes empty insights/unresolved ✅ FIXED d2168b6

`end_session()` previously called `narrative_store.append(insights="", unresolved="", pending=True)` — the two most valuable fields were hardcoded as empty strings. Deferred reflection was supposed to backfill them via `_run_deferred_reflection()` → `update_entry()`, but this path was unreliable (MAX_BATCH=5 bottleneck, `is_first` trigger constraint, LLM failures silently resolved entries). Result: 50% of narrative entries permanently locked at keyword-stub summaries.

**Diagnosis**: `grep '"insights": ""' ~/.hermes/memory/narrative.jsonl | wc -l` — if >10% of entries have empty insights, the bridge is broken.

**Fix (d2168b6)**: Moved LLM call from deferred to inline within `end_session()`:
- `session_reflector.reflect()` → extract keyframes
- `reflect_with_llm(keyframes)` → LLM generates real insights/unresolved → inline
- `narrative_store.append(insights=real, unresolved=real, pending=False)` → populated at write time
- If LLM fails → `pending=True` preserves entry for one last deferred retry

See `references/narrative-inline-reflection.md` for architecture diagrams and diagnostic flow.

### Pitfall: deferred reflection batch bottleneck 🔴 FIXED v1.4.4

`_run_deferred_reflection()` processed exactly 1 pending entry per new session — when 50 entries accumulated (delegate_task flood), 49 were permanently unreachable. Combined with `update_entry` only touching the latest same-session_id entry, older entries from the same session were abandoned.

**Fix (v1.4.4):**
- `while processed < MAX_BATCH=5` loop in `_run_deferred_reflection()` — up to 5 per invocation
- `NarrativeStore.mark_session_resolved(session_id)` — batch-marks all same-session pending entries
- All 7 exit paths (success, LLM failure, skip-garbage, no-topics) call `mark_session_resolved`

### Pitfall: session_reflector keyframe gap — no keyframes for real sessions ✅ FIXED v1.4.5

**Root cause**: Hermes `invoke_hook("on_session_end")` (at `agent/turn_finalizer.py` L495-503) never passes `conversation_history` — only `session_id`, `task_id`, `turn_id`, `completed`, `interrupted`, `model`, `platform`. So adapter's `kwargs.get("conversation_history", [])` is always `[]` → `end_session()`'s `if messages:` gate skips `session_reflector.reflect()` → zero keyframes for all real sessions.

**Fix (v1.4.5) — platform-agnostic self-caching**:
The engine now maintains its own message cache instead of relying on platform hooks:

```python
# __init__
self._session_messages: List[Dict[str, Any]] = []

# process() — cache every call
self._session_messages = messages

# end_session() — fallback to cache
effective_messages = messages or self._session_messages
if effective_messages:
    self.session_reflector.reflect(messages=effective_messages, ...)
```

**Design principle**: When a platform doesn't provide data the engine needs, make the engine self-sufficient — do NOT write platform-specific adapter hacks. The engine already receives `messages` on every `process()` call; caching it costs zero and works on any platform.

See `references/session-reflector-keyframe-gap.md`.

### Pitfall: Hermes Studio on_session_end fires for every delegate_task completion 🔴

The plugin assumes `on_session_end` fires **once** when the user closes a conversation. In Hermes Studio, it fires for **every delegate_task sub-agent completion** — and `session_id` is the **parent** session, not the sub-agent's. Result: one long session with N delegate_task calls = 2N narrative entries (N real + N garbage with sub-agent keywords like `['user', 'one', 'skills', 'via', 'session']`). 76% of entries originate from this, vs 12% from context compression and 12% from real session end. `_run_deferred_reflection()` only handles 1 pending entry per new session → 98% never enriched. See `references/delegate-task-narrative-backlog.md` for session data and analysis.

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

### Reference implementation

- `references/implementation-python.md` — A clean Python reference implementation of all four core modules plus the four optional perception modules. Not required reading — the SKILL.md alone is sufficient. Provided for developers who prefer reading code over prose. Zero dependencies beyond Python standard library; jieba is optional (falls back to regex when absent).

### Architecture

- `references/emotion-architecture-layers.md` — 情绪三层架构模型。Layer 1 classify → Layer 2 Processor → Layer 3 Heartbeat。AffectMapper vs SedonaMethod 对比框架，模因提取 vs 根因分析区分，衰减曲线归属。

### Training

- `references/training-guide.md` — **自定义情绪模型搭建指南（唯一权威版本）**。面向 Agent 的端到端作业文档。覆盖：① 接口协议（classify 返回格式、is_valid_model 校验逻辑、dict_path 实例化机制）；② **dominant 标签白名单**（enrich_legacy_fields 识别的正负面集合，避免无声判中性）；③ Agent 对话工作流（引导用户定义维度 → 选择模板 → 生成 → 验证）；④ 三套完整模板（平铺/SedonaMethod 三层/V-A 坐标映射）；⑤ 配套词典规范；⑥ 验证脚本；⑦ 常见陷阱。**此文件为唯一权威版本，飞书文档与其对齐。**
- `references/affect-mapper-model.md` — AffectMapper 圆环情绪模型实现参考。基于 DUTIR 七维离散输出 → 加权映射至 V/A 连续空间。零外部依赖，完整 Classifier 实现模板，含验证示例与扩展建议。
- `references/emotion-model-registry-pitfalls.md` — EmotionModelRegistry 设计漏洞与运行时排查：`__init__()` 不自动 discover、`_get_or_create()` 硬编码 dict_path 参数、6 阶段冒烟测试方法论，附验证脚本模板。

### Platform examples

- `examples/claude-code.md` — Integration guide for Claude Code: CLAUDE.md injection, state persistence, hook point
- `examples/cursor.md` — Integration guide for Cursor: .cursorrules injection, session-scoped state
- `examples/generic-agent.md` — Integration guide for any LLM agent: system prompt template, manual state tracking, minimal JSON persistence

### External integration references

- `references/homerail-voice-consciousness-integration.md` — Architecture analysis: integrating consciousness contour (P0-P5) with homerail's voice-first DAG orchestration for cross-agent identity continuity. Covers DAG node injection, runtime voice broadcasting via Voice Surface, and cross-DAG narrative persistence.

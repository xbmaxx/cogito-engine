# Plugin Deployment Architecture

Cogito Engine's Hermes plugin has a **dual-path deployment** from install.py.
Understanding both paths is essential for debugging installation issues.

## Two Deployment Paths

### Path A: `_install_hermes()` — Hermes Plugin

```
Source:  REPO_ROOT / "adapters/"
Target:  ~/.hermes/plugins/hermes_consciousness/  (global)
         — or —
         ~/.hermes/profiles/<name>/plugins/hermes_consciousness/  (profile)
```

Installed via `shutil.copytree(REPO_ROOT / "adapters", plugin_dir, dirs_exist_ok=True)`.

**What it installs:** `plugin.yaml`, `hermes_adapter.py`, `__init__.py`, and
all platform adapter files (`hook_entry.py`, `claude_code_adapter.py`, …).

### Path B: `bootstrap_engine()` — Core Engine

```
Source:  REPO_ROOT / "cogito_core/"
Target:  ~/.cogito/cogito_core/
```

Installed via `shutil.copytree(src_core, dst_core)`.

**What it installs:** All `.py` modules + `data/emotion_dict.json` + `version.txt`.

## Import Resolution at Runtime

The plugin's `__init__.py` inserts the plugin directory first in `sys.path`:

```python
_PLUGIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_PLUGIN_DIR))
```

Then imports from `cogito_core`:

```python
from cogito_core.persistence import set_cogito_home as _set_persistence_home
```

**Resolution order:**
1. `~/.hermes/plugins/hermes_consciousness/cogito_core/` (plugin-local, via `sys.path[0]`)
2. `~/.cogito/cogito_core/` (global, if on `sys.path`)
3. Any other `cogito_core` on `sys.path`

When a plugin-local `cogito_core/` exists (even if incomplete), it takes
priority over the `bootstrap_engine()` copy at `~/.cogito/`.

## Common Deployment Gaps

### Missing `data/` in plugin-local `cogito_core/`

If `cogito_core/` was manually assembled in the plugin directory (e.g. only
copying `.py` files), the `data/emotion_dict.json` (2.8 MB, 27,350 entries)
will be absent.

**Code path that fails:**
```python
# emotion_classifier.py L52-54
dict_path = str(Path(__file__).parent / "data" / "emotion_dict.json")
```

**Symptom:** `EmotionClassifier 字典加载失败` in agent.log; all sentiment
outputs are `neutral 0.500`.

**Fix:** Create a `data/` symlink inside the plugin's `cogito_core/`:
```bash
cd ~/.hermes/plugins/hermes_consciousness
ln -s ../data cogito_core/data
```

### Duplicated files across root and `cogito_core/`

The plugin directory sometimes duplicates `.py` files at both
`plugins/hermes_consciousness/` (root) and
`plugins/hermes_consciousness/cogito_core/` (subdirectory). Because
`sys.path.insert(0, plugin_dir)` makes `import cogito_core.X` resolve to
the subdirectory, the root-level copies are dead code.

**Diagnosis:** Compare the two locations:
```bash
echo "Root level:  $(ls *.py 2>/dev/null | wc -l) .py files"
echo "cogito_core: $(ls cogito_core/*.py 2>/dev/null | wc -l) .py files"
```

### Verification Checklist

After deploying (or suspecting a deployment issue), run:

```bash
# 1. Plugin enabled?
hermes plugins list | grep hermes_consciousness

# 2. Load errors?
grep 'Failed to load.*hermes_consciousness' ~/.hermes/logs/agent.log

# 3. Registration?
grep 'HermesAdapter 已注册' ~/.hermes/logs/agent.log | tail -1

# 4. Hook registration?
grep 'hook 注册完成' ~/.hermes/logs/agent.log | tail -1

# 5. File count (expect ~21+ .py files in cogito_core/)
find ~/.hermes/plugins/hermes_consciousness/cogito_core -maxdepth 1 -name '*.py' | wc -l

# 6. Data file?
ls -la ~/.hermes/plugins/hermes_consciousness/cogito_core/data/emotion_dict.json

# 7. Version consistency?
echo "plugin: $(grep '^version:' ~/.hermes/plugins/hermes_consciousness/plugin.yaml)"
echo "engine: $(cat ~/.hermes/plugins/hermes_consciousness/cogito_core/version.txt 2>/dev/null || echo 'missing')"
echo "skill:  $(grep '^version:' ~/.hermes/skills/cogito-engine/SKILL.md | head -1)"

# 8. Import test
cd ~/.hermes/plugins/hermes_consciousness && python3 -c "
import sys; sys.path.insert(0, '.')
from cogito_core.emotion_classifier import EmotionClassifier
ec = EmotionClassifier()
print('DUTIR available:', ec.is_available())
if ec.is_available():
    r = ec.classify('测试消息')
    print('  classify OK:', r.get('dominant', '?'))
"
```

## Profile-Specific Install

When running with a specific Hermes profile, the plugin is installed at
`~/.hermes/profiles/<name>/plugins/hermes_consciousness/`, NOT the global
`~/.hermes/plugins/` path. The global installation remains stale if one
exists.

```bash
# Install to a specific profile
python3 install.py --platform hermes --hermes-profile <name>

# List available profiles
python3 install.py --list-profiles
```

If the user has multiple profiles and ran `install.py` without
`--hermes-profile`, the global path gets the update while the active
profile's plugin dir stays on the old version.

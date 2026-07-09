#!/bin/bash
# Cogito Engine — 将 repo 核心文件同步到所有运行时目录
# 用法: bash scripts/sync-all.sh

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_CORE="$REPO_DIR/cogito_core"
COGITO_CORE="$HOME/.cogito/cogito_core"
PLUGIN_DIR="$HOME/.hermes/plugins/hermes_consciousness"
SKILL_CORE="$HOME/.hermes/skills/cogito-engine/cogito_core"
SKILL_MD="$HOME/.hermes/skills/cogito-engine"

FILES=(
    engine.py env_sensor.py session_reflector.py context_window.py
    emotion_classifier.py narrative_store.py keyframe_extractor.py
    text_emotion.py ticker.py focus_stack.py temporal.py self_perception.py
)

echo "Syncing repo → runtime..."
mkdir -p "$COGITO_CORE" "$PLUGIN_DIR" "$SKILL_CORE"

for f in "${FILES[@]}"; do
    [ -f "$REPO_CORE/$f" ] || continue
    cp "$REPO_CORE/$f" "$COGITO_CORE/$f"
    cp "$REPO_CORE/$f" "$PLUGIN_DIR/$f"
    cp "$REPO_CORE/$f" "$SKILL_CORE/$f"
    echo "  $f"
done

# data/emotion_dict.json
if [ -f "$REPO_CORE/data/emotion_dict.json" ]; then
    mkdir -p "$COGITO_CORE/data" "$PLUGIN_DIR/data" "$SKILL_CORE/data"
    cp "$REPO_CORE/data/emotion_dict.json" "$COGITO_CORE/data/"
    cp "$REPO_CORE/data/emotion_dict.json" "$PLUGIN_DIR/data/"
    cp "$REPO_CORE/data/emotion_dict.json" "$SKILL_CORE/data/"
    echo "  data/emotion_dict.json"
fi

# SKILL.md
if [ -f "$REPO_DIR/SKILL.md" ]; then
    cp "$REPO_DIR/SKILL.md" "$SKILL_MD/SKILL.md"
    echo "  SKILL.md"
fi

echo ""
echo "Done. Run 'bash scripts/check-sync.sh' to verify."

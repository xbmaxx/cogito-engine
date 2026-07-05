#!/bin/bash
# Cogito Engine sync checker — pre-commit hook
# 确保 repo 修改已同步到 .cogito / plugin / skill 三个运行时目录。
# 安装: ln -sf ../../scripts/check-sync.sh .git/hooks/pre-commit

set -euo pipefail

REPO_DIR="$(git rev-parse --show-toplevel)"
REPO_CORE="$REPO_DIR/cogito_core"
COGITO_CORE="$HOME/.cogito/cogito_core"
PLUGIN_DIR="$HOME/.hermes/plugins/hermes_consciousness"
SKILL_CORE="$HOME/.hermes/skills/cogito-engine/cogito_core"

FILES=(
    engine.py
    env_sensor.py
    session_reflector.py
    context_window.py
    emotion_classifier.py
    narrative_store.py
    keyframe_extractor.py
    text_emotion.py
    ticker.py
    focus_stack.py
    temporal.py
    self_perception.py
)

RED='\033[31m'
GREEN='\033[32m'
YELLOW='\033[33m'
NC='\033[0m'

MISMATCH=0
MISSING=0

for f in "${FILES[@]}"; do
    repo_file="$REPO_CORE/$f"
    if [ ! -f "$repo_file" ]; then
        continue  # 不在 repo 中，跳过
    fi

    repo_md5=$(md5 -q "$repo_file" 2>/dev/null || echo "MISSING")

    for target_dir in "$COGITO_CORE" "$PLUGIN_DIR" "$SKILL_CORE"; do
        target_file="$target_dir/$f"
        if [ ! -f "$target_file" ]; then
            echo -e "${RED}✗ MISSING${NC} $f 不在 $target_dir/"
            MISSING=1
            continue
        fi
        target_md5=$(md5 -q "$target_file" 2>/dev/null)
        if [ "$repo_md5" != "$target_md5" ]; then
            echo -e "${RED}✗ MISMATCH${NC} $f: repo ≠ $(basename "$(dirname "$target_dir")")"
            MISMATCH=1
        fi
    done
done

# 检查 data/emotion_dict.json
DATA_FILE="data/emotion_dict.json"
repo_data="$REPO_CORE/$DATA_FILE"
if [ -f "$repo_data" ]; then
    repo_data_md5=$(md5 -q "$repo_data")
    for target_dir in "$COGITO_CORE" "$PLUGIN_DIR" "$SKILL_CORE"; do
        target_data="$target_dir/$DATA_FILE"
        if [ ! -f "$target_data" ]; then
            echo -e "${RED}✗ MISSING${NC} $DATA_FILE 不在 $target_dir/"
            MISSING=1
            continue
        fi
        target_data_md5=$(md5 -q "$target_data")
        if [ "$repo_data_md5" != "$target_data_md5" ]; then
            echo -e "${RED}✗ MISMATCH${NC} $DATA_FILE: repo ≠ $(basename "$(dirname "$target_dir")")"
            MISMATCH=1
        fi
    done
fi

# 检查 SKILL.md frontmatter version vs version.txt
VERSION_TXT=$(cat "$REPO_CORE/version.txt" 2>/dev/null || echo "unknown")
SKILL_MD="$REPO_DIR/SKILL.md"
if [ -f "$SKILL_MD" ]; then
    SKILL_VERSION=$(grep "^version:" "$SKILL_MD" | head -1 | sed 's/version: *//')
    if [ "$SKILL_VERSION" != "$VERSION_TXT" ]; then
        echo -e "${RED}✗ VERSION MISMATCH${NC} SKILL.md=$SKILL_VERSION ≠ version.txt=$VERSION_TXT"
        MISMATCH=1
    fi
fi

if [ $MISSING -eq 1 ] || [ $MISMATCH -eq 1 ]; then
    echo ""
    echo -e "${YELLOW}修复方法：${NC}"
    echo "  cd $REPO_DIR && bash scripts/sync-all.sh"
    echo ""
    echo -e "${YELLOW}或者跳过检查（不推荐）：${NC}"
    echo "  git commit --no-verify ..."
    exit 1
fi

echo -e "${GREEN}✓${NC} 所有文件已同步"
exit 0

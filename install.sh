#!/usr/bin/env bash
set -euo pipefail

# ── Cogito Engine installer ────────────────────────────────────────────────
# Usage: ./install.sh [--update] [--platform <name>] [--dry-run]
# ────────────────────────────────────────────────────────────────────────────

MIN_PYTHON="3.9"

check_python() {
    if command -v python3 &>/dev/null; then
        local ver
        ver=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
        local major minor
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -gt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -ge 9 ]; }; then
            echo "✓ Python $ver detected"
            return 0
        fi
        echo "✗ Python $ver found, but $MIN_PYTHON+ is required"
        return 1
    fi
    echo "✗ python3 not found"
    return 1
}

# ── Check Python version ──
echo "==> Checking Python..."
check_python || exit 1

# ── Install dependencies (if requirements.txt exists) ──
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REQ_FILE="$SCRIPT_DIR/requirements.txt"

# COGITO_HOME defaults to ~/.cogito
COGITO_HOME="${COGITO_HOME:-$HOME/.cogito}"

if [ -f "$REQ_FILE" ]; then
    echo "==> Installing Python dependencies..."
    python3 -m pip install -r "$REQ_FILE" --quiet 2>&1 || {
        echo "⚠ pip install failed (non-fatal, core uses stdlib)"
    }
fi

# ── Run install.py ──
echo "==> Running Cogito Engine installer..."
cd "$SCRIPT_DIR"
python3 install.py "$@"

echo ""
echo "Done. Restart your agent."

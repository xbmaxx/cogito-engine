"""Cogito Engine – Hermes Plugin entry point."""

import sys
from pathlib import Path

# Ensure cogito_core is importable from ~/.cogito
sys.path.insert(0, str(Path.home() / ".cogito"))

from .hermes_adapter import HermesAdapter


def register(ctx):
    """Called by Hermes when the plugin is loaded."""
    adapter = HermesAdapter()
    adapter.register(ctx)

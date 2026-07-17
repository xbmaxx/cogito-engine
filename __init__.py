"""Hermes plugin entry point for Cogito Engine (hermes_consciousness).

Hermes requires a package-level ``register(ctx)`` function. The actual
adapter lives in ``hermes_adapter.HermesAdapter``; we instantiate a single
instance here and delegate ``register`` to it.
"""
from __future__ import annotations

import logging
from pathlib import Path
import sys

logger = logging.getLogger(__name__)

# Ensure ~/.cogito is on sys.path so `from cogito_core...` resolves,
# matching the install.py bootstrap convention.
_cogito_root = str(Path.home() / ".cogito")
if _cogito_root not in sys.path:
    sys.path.insert(0, _cogito_root)

from .hermes_adapter import HermesAdapter  # noqa: E402

# Module-level singleton. Hermes calls register(ctx) once at load time.
_adapter: HermesAdapter | None = None


def get_adapter() -> HermesAdapter:
    global _adapter
    if _adapter is None:
        _adapter = HermesAdapter()
    return _adapter


def register(ctx) -> None:
    """Hermes plugin registration entry point."""
    get_adapter().register(ctx)
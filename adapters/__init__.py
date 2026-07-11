"""Cogito Engine – Hermes Plugin entry point."""

import sys
from pathlib import Path

# Ensure cogito_core is importable from the plugin directory itself
# (Hermes loads __init__.py via importlib; sys.path may not include it)
_THIS_DIR = str(Path(__file__).resolve().parent)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# Ensure cogito_core is also importable from ~/.cogito (legacy installs)
_COGITO_DIR = str(Path.home() / ".cogito")
if _COGITO_DIR not in sys.path:
    sys.path.insert(0, _COGITO_DIR)

# Redirect all persistence to Hermes's memory directory (before any engine import)
from cogito_core.persistence import set_cogito_home as _set_persistence_home
_set_persistence_home(str(Path.home() / ".hermes" / "memory"))

from cogito_core import narrative_store
narrative_store.set_cogito_home(str(Path.home() / ".hermes" / "memory"))

# session_reflector uses a module-level _COGITO_HOME without setter
import cogito_core.session_reflector as _sr
_sr._COGITO_HOME = Path.home() / ".hermes" / "memory"

from .hermes_adapter import HermesAdapter


def register(ctx):
    """Called by Hermes when the plugin is loaded."""
    adapter = HermesAdapter()
    adapter.register(ctx)

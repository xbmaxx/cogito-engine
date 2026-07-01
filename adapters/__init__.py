"""Cogito Engine – Hermes Plugin entry point."""

from .hermes_adapter import HermesAdapter


def register(ctx):
    """Called by Hermes when the plugin is loaded."""
    adapter = HermesAdapter()
    adapter.register(ctx)

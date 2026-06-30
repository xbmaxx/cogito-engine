"""Cogito Engine – Hermes Plugin entry point."""

from .hermes_adapter import HermesConsciousnessAdapter


def register(ctx):
    """Called by Hermes when the plugin is loaded."""
    adapter = HermesConsciousnessAdapter()
    adapter.register(ctx)

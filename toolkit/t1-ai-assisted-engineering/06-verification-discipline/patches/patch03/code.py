"""Feature-flag lookup for the rollout system.

Flags arrive as raw values from an external config source (environment
variables, a remote config service returning JSON-as-strings) where they
are not guaranteed to already be Python bools.
"""

from __future__ import annotations


def is_feature_enabled(config: dict, key: str) -> bool:
    """Return whether the named feature flag is enabled."""
    return bool(config.get(key, False))

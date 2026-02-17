"""
js_bridge.py - Helpers to register Python functions on window.HelwanAPI
Creates the namespace once and registers functions with backward compat.
"""

import anvil.js


def _ensure_namespace():
    """Ensure window.HelwanAPI exists."""
    try:
        api = anvil.js.window.HelwanAPI
        if not api:
            anvil.js.window.HelwanAPI = anvil.js.window.Object()
    except Exception:
        anvil.js.window.HelwanAPI = anvil.js.window.Object()


def register_bridges(bridges):
    """
    Register Python functions on window.HelwanAPI + window (backward compat).

    Args:
        bridges: dict of {name: callable}
    """
    _ensure_namespace()
    for name in bridges:
        fn = bridges[name]
        # HelwanAPI.xxx
        try:
            anvil.js.window.HelwanAPI[name] = fn
        except Exception:
            pass
        # window.xxx (backward compat)
        try:
            anvil.js.window[name] = fn
        except Exception:
            pass

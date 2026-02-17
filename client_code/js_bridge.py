"""
js_bridge.py - مساعدات لتسجيل دوال Python على window.HelwanAPI
===============================================================
يُنشئ الـ namespace مرة واحدة ويُسجل الدوال مع backward compat.
"""

import anvil.js


def _ensure_namespace():
    """Ensure window.HelwanAPI exists."""
    try:
        if not anvil.js.window.HelwanAPI:
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
    for name, fn in bridges.items():
        setattr(anvil.js.window.HelwanAPI, name, fn)  # HelwanAPI.xxx
        setattr(anvil.js.window, name, fn)             # window.xxx (backward compat)

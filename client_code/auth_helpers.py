"""
auth_helpers - Shared authentication utility for all forms
==========================================================
Centralizes auth token retrieval so every form uses the same logic.
"""

import anvil.js


def get_auth_token():
    """Get auth token from sessionStorage with localStorage fallback.

    Checks sessionStorage first for 'auth_token'. If not found, falls back
    to localStorage. When a token is recovered from localStorage, it is
    copied into sessionStorage so subsequent calls are faster.

    Returns:
        str or None: The auth token, or None if not found.
    """
    try:
        token = anvil.js.window.sessionStorage.getItem('auth_token')
        if not token:
            token = anvil.js.window.localStorage.getItem('auth_token')
            if token:
                try:
                    anvil.js.window.sessionStorage.setItem('auth_token', token)
                except Exception:
                    pass
        return token
    except Exception:
        return None

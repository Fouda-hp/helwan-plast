"""
auth_helpers - Shared authentication utility for all forms
==========================================================
Centralizes auth token retrieval so every form uses the same logic.
"""

import anvil.js
import anvil.server
import time

# In-memory cache for validate_token result (avoids repeated server calls)
_token_cache = {'result': None, 'ts': 0, 'token': None}
_CACHE_TTL = 30  # seconds


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


def validate_token_cached(token=None):
    """Validate token with 30-second client-side cache.

    Returns the same dict as anvil.server.call('validate_token', token).
    Multiple forms calling this within 30s will only hit the server once.
    """
    if token is None:
        token = get_auth_token()
    if not token:
        return {'valid': False}

    now = time.time()
    if (_token_cache['token'] == token and
            _token_cache['result'] is not None and
            (now - _token_cache['ts']) < _CACHE_TTL):
        return _token_cache['result']

    try:
        result = anvil.server.call('validate_token', token)
    except Exception:
        return {'valid': False}

    _token_cache['result'] = result
    _token_cache['ts'] = now
    _token_cache['token'] = token
    return result


def clear_token_cache():
    """Clear the validation cache (call on logout)."""
    _token_cache['result'] = None
    _token_cache['ts'] = 0
    _token_cache['token'] = None

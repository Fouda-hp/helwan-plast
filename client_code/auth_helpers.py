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
_CACHE_TTL = 10  # seconds (reduced from 30 for tighter role/permission checks)

# توكن يُمرَّر قبل فتح لوحة المحاسب (نفس عملية البايثون) — يقرأه AccountantForm
_accountant_token = None


def set_accountant_token(token):
    """استدعِه من لوحة الأدمن قبل open_form('AccountantForm') ليمرّر التوكن."""
    global _accountant_token
    _accountant_token = token


def get_accountant_token():
    """لوحة المحاسب تقرأ منه إن لم تجد التوكن في التخزين."""
    return _accountant_token


def get_auth_token():
    """Get auth token from sessionStorage (primary) with one-way migration from localStorage.

    Security hardening:
    - Prefer sessionStorage only.
    - If an old token is found in localStorage, copy it to sessionStorage then remove it.
    """
    try:
        token = anvil.js.window.sessionStorage.getItem('auth_token')
        if not token:
            legacy = anvil.js.window.localStorage.getItem('auth_token')
            if legacy:
                token = legacy
                try:
                    anvil.js.window.sessionStorage.setItem('auth_token', token)
                    anvil.js.window.localStorage.removeItem('auth_token')
                except Exception:
                    pass
        if not token:
            try:
                w = anvil.js.window.top if anvil.js.window.top else anvil.js.window
                if w and w != anvil.js.window:
                    token = w.sessionStorage.getItem('auth_token')
            except Exception:
                pass
        if not token:
            try:
                w = anvil.js.window.parent if anvil.js.window.parent else anvil.js.window
                if w and w != anvil.js.window:
                    token = w.sessionStorage.getItem('auth_token')
            except Exception:
                pass
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

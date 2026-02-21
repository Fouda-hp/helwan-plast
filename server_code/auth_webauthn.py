"""
auth_webauthn.py - WebAuthn / Passkeys (Biometric Authentication)
=================================================================
Allows users to register and authenticate using fingerprint, Face ID,
or device PIN via the WebAuthn standard.

Requires: pip install webauthn  (py_webauthn >= 2.0)
Install in Anvil: Settings → Python Packages → add 'webauthn'

Flow:
  1. User logs in with email + password (existing flow)
  2. Instead of OTP, user authenticates with biometric (if registered)
  3. Server verifies the credential and creates a session
"""

import anvil.server
import anvil.tables as tables
from anvil.tables import app_tables
import json
import time
import logging
from datetime import datetime, timedelta

# --- py_webauthn imports ---
# These will fail if 'webauthn' is not installed via Anvil's Python Packages
try:
    from webauthn import (
        generate_registration_options,
        verify_registration_response,
        generate_authentication_options,
        verify_authentication_response,
        options_to_json,
        base64url_to_bytes,
    )
    from webauthn.helpers.structs import (
        AuthenticatorSelectionCriteria,
        ResidentKeyRequirement,
        UserVerificationRequirement,
        PublicKeyCredentialDescriptor,
        AuthenticatorTransport,
    )
    from webauthn.helpers.cose import COSEAlgorithmIdentifier
    WEBAUTHN_AVAILABLE = True
except ImportError:
    WEBAUTHN_AVAILABLE = False

# --- Local imports ---
try:
    from .auth_sessions import create_session, validate_session
except ImportError:
    from auth_sessions import create_session, validate_session
try:
    from .auth_utils import get_utc_now
except ImportError:
    from auth_utils import get_utc_now
try:
    from .auth_audit import log_audit
except ImportError:
    from auth_audit import log_audit

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────
RP_NAME = "Helwan Plast ERP"
CHALLENGE_EXPIRY_SECONDS = 300  # 5 minutes

# Challenge storage — persistent via webauthn_credentials table (type='challenge').
# Using the database ensures challenges survive across workers / uplinks.
# Each challenge row is cleaned up after use or after TTL expiry.
_challenges = {}  # kept as quick local cache (same-worker fast path)


# ── Helper ──────────────────────────────────────────────────────

def _get_rp_id():
    """Extract the Relying Party ID from the app origin (hostname only)."""
    try:
        origin = anvil.server.get_app_origin()
        if origin:
            from urllib.parse import urlparse
            hostname = urlparse(origin).hostname
            if hostname:
                return hostname
    except Exception:
        pass
    logger.error("Cannot determine RP ID: app origin unavailable. WebAuthn will fail.")
    raise RuntimeError("WebAuthn RP ID could not be determined from app origin.")


def _get_origin():
    """Get the origin URL (scheme + host only, NO path)."""
    try:
        origin = anvil.server.get_app_origin()
        if origin:
            from urllib.parse import urlparse
            parsed = urlparse(origin)
            # WebAuthn origin = scheme + hostname (no path, no trailing slash)
            if parsed.scheme and parsed.hostname:
                return f"{parsed.scheme}://{parsed.hostname}"
    except Exception:
        pass
    logger.error("Cannot determine origin: app origin unavailable. WebAuthn will fail.")
    raise RuntimeError("WebAuthn origin could not be determined from app origin.")


def _b64url_decode(s):
    """Decode base64url string (with or without padding) to bytes."""
    import base64
    s = str(s)
    # Add padding if needed
    s += '=' * (4 - len(s) % 4) if len(s) % 4 else ''
    return base64.urlsafe_b64decode(s)


def _cleanup_expired_challenges():
    """Remove expired challenges from memory and database."""
    now = time.time()
    # Clean memory cache
    expired = [k for k, v in _challenges.items() if now > v.get('expires', 0)]
    for k in expired:
        del _challenges[k]
    # Clean database challenges (older than 10 minutes)
    try:
        cutoff = get_utc_now() - timedelta(minutes=10)
        for row in app_tables.webauthn_credentials.search(
            is_active=False, nickname='__challenge__'
        ):
            try:
                if row['created_at'] and row['created_at'] < cutoff:
                    row.delete()
            except Exception:
                pass
    except Exception:
        pass


def _store_challenge(user_email, challenge_bytes, challenge_type):
    """Store challenge in both memory and database for cross-worker reliability."""
    import base64
    challenge_b64 = base64.b64encode(challenge_bytes).decode('ascii')
    expires = time.time() + CHALLENGE_EXPIRY_SECONDS

    # Memory cache (fast path if same worker)
    _challenges[user_email] = {
        'challenge': challenge_bytes,
        'type': challenge_type,
        'expires': expires,
    }

    # Database persistence (cross-worker reliability)
    try:
        # Remove any existing challenge for this user
        for old in app_tables.webauthn_credentials.search(
            user_email=user_email, nickname='__challenge__', is_active=False
        ):
            old.delete()

        app_tables.webauthn_credentials.add_row(
            credential_id='__challenge__',
            user_email=user_email,
            public_key=challenge_b64,           # challenge bytes as base64
            sign_count=0,
            created_at=get_utc_now(),
            last_used=None,
            transports=json.dumps({'type': challenge_type, 'expires': expires}),
            nickname='__challenge__',
            is_active=False,                     # never treated as a real credential
        )
    except Exception as e:
        logger.warning("Failed to persist challenge to DB: %s", e)


def _retrieve_challenge(user_email, expected_type):
    """
    Retrieve and consume challenge. Tries memory first, then database.
    Returns challenge bytes or None.
    """
    import base64

    # Try memory cache first (fast path)
    stored = _challenges.pop(user_email, None)
    if stored and stored.get('type') == expected_type and time.time() <= stored['expires']:
        # Also clean up DB row
        try:
            for row in app_tables.webauthn_credentials.search(
                user_email=user_email, nickname='__challenge__', is_active=False
            ):
                row.delete()
        except Exception:
            pass
        return stored['challenge']

    # Fallback: try database (different worker scenario)
    try:
        row = app_tables.webauthn_credentials.get(
            user_email=user_email, nickname='__challenge__', is_active=False
        )
        if row:
            meta = json.loads(row['transports'] or '{}')
            challenge_b64 = row['public_key']
            ch_type = meta.get('type', '')
            ch_expires = meta.get('expires', 0)

            # Delete the row (consume the challenge)
            row.delete()

            if ch_type == expected_type and time.time() <= ch_expires:
                return base64.b64decode(challenge_b64)
            else:
                logger.warning("Challenge expired or type mismatch for %s", user_email)
                return None
        return None
    except Exception as e:
        logger.warning("Failed to retrieve challenge from DB for %s: %s", user_email, e)
        return None


def _require_webauthn():
    """Check if py_webauthn library is available."""
    if not WEBAUTHN_AVAILABLE:
        return {
            'success': False,
            'error': 'WebAuthn library not installed. Please add "webauthn" in Anvil Settings → Python Packages.'
        }
    return None


# ── Check if user has registered passkeys ──────────────────────

@anvil.server.callable
def webauthn_has_passkey(email):
    """
    Check if a user has any registered WebAuthn credentials.
    Called during login flow to show the biometric button.
    """
    if not email:
        return False
    try:
        email = str(email).strip().lower()
        credentials = list(app_tables.webauthn_credentials.search(
            user_email=email, is_active=True
        ))
        return len(credentials) > 0
    except Exception as e:
        logger.warning("webauthn_has_passkey error: %s", e)
        return False


# ── Registration (تسجيل بصمة جديدة) ───────────────────────────

@anvil.server.callable
def webauthn_register_start(token):
    """
    Step 1 of registration: Generate options for the browser.
    User must be authenticated (has valid session token).
    Returns: {success, options (JSON string)}
    """
    err = _require_webauthn()
    if err:
        return err

    session = validate_session(token)
    if not session:
        return {'success': False, 'error': 'Invalid session. Please log in again.'}

    user_email = session['email']
    user = app_tables.users.get(email=user_email)
    if not user:
        return {'success': False, 'error': 'User not found.'}

    _cleanup_expired_challenges()

    # Get existing credentials to exclude (prevent re-registration of same key)
    try:
        existing = list(app_tables.webauthn_credentials.search(
            user_email=user_email, is_active=True
        ))
        exclude_creds = []
        for cred in existing:
            try:
                exclude_creds.append(
                    PublicKeyCredentialDescriptor(
                        id=_b64url_decode(cred['credential_id']),
                    )
                )
            except Exception:
                pass
    except Exception:
        exclude_creds = []

    try:
        options = generate_registration_options(
            rp_id=_get_rp_id(),
            rp_name=RP_NAME,
            user_id=user_email.encode('utf-8'),
            user_name=user_email,
            user_display_name=user.get('full_name') or user_email,
            exclude_credentials=exclude_creds,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )

        # Store challenge for verification (Step 2) — persistent
        _store_challenge(user_email, options.challenge, 'register')

        options_json = options_to_json(options)
        logger.info("WebAuthn registration started for: %s", user_email)

        return {'success': True, 'options': options_json}

    except Exception as e:
        logger.error("WebAuthn register_start error: %s", e)
        return {'success': False, 'error': 'Failed to generate registration options.'}


@anvil.server.callable
def webauthn_register_complete(token, credential_json, device_info=None):
    """
    Step 2 of registration: Verify the browser's response and store credential.
    device_info: optional dict with {browser, os, device_type} from client.
    Returns: {success, message}
    """
    err = _require_webauthn()
    if err:
        return err

    session = validate_session(token)
    if not session:
        return {'success': False, 'error': 'Invalid session. Please log in again.'}

    user_email = session['email']

    # Retrieve stored challenge (memory or database)
    challenge_bytes = _retrieve_challenge(user_email, 'register')
    if not challenge_bytes:
        return {'success': False, 'error': 'No pending registration. Please start again.'}

    try:
        verification = verify_registration_response(
            credential=credential_json,
            expected_challenge=challenge_bytes,
            expected_rp_id=_get_rp_id(),
            expected_origin=_get_origin(),
        )

        # Extract transports from the credential JSON if available
        transports = ['internal']  # default: platform authenticator
        try:
            parsed = json.loads(credential_json) if isinstance(credential_json, str) else credential_json
            if 'response' in parsed and 'transports' in parsed['response']:
                transports = parsed['response']['transports']
        except Exception:
            pass

        # Build nickname from device info
        nickname = 'Passkey'
        if device_info and isinstance(device_info, dict):
            parts = []
            if device_info.get('browser'):
                parts.append(str(device_info['browser']))
            if device_info.get('os'):
                parts.append(str(device_info['os']))
            if parts:
                nickname = ' - '.join(parts)

        # Convert bytes to base64url strings for database storage
        import base64
        cred_id_raw = verification.credential_id
        pub_key_raw = verification.credential_public_key
        # py_webauthn >= 2.0 returns bytes; convert to base64url string
        if isinstance(cred_id_raw, bytes):
            cred_id_str = base64.urlsafe_b64encode(cred_id_raw).rstrip(b'=').decode('ascii')
        else:
            cred_id_str = str(cred_id_raw)
        if isinstance(pub_key_raw, bytes):
            pub_key_str = base64.urlsafe_b64encode(pub_key_raw).rstrip(b'=').decode('ascii')
        else:
            pub_key_str = str(pub_key_raw)
        sign_count_val = int(verification.sign_count) if verification.sign_count else 0

        # Store the credential
        app_tables.webauthn_credentials.add_row(
            credential_id=cred_id_str,
            user_email=user_email,
            public_key=pub_key_str,
            sign_count=sign_count_val,
            created_at=get_utc_now(),
            last_used=None,
            transports=json.dumps(transports),
            nickname=nickname,
            is_active=True,
        )

        log_audit(
            'WEBAUTHN_REGISTER', 'webauthn_credentials', cred_id_str,
            None, {'user_email': user_email, 'device': nickname}, user_email, ''
        )

        logger.info("WebAuthn credential registered for: %s (device: %s)", user_email, nickname)
        return {'success': True, 'message': 'Passkey registered successfully!'}

    except Exception as e:
        logger.error("WebAuthn register_complete error: %s", e)
        return {'success': False, 'error': 'Registration verification failed. Please try again.'}


# ── Authentication (تسجيل دخول بالبصمة) ────────────────────────

@anvil.server.callable
def webauthn_auth_start(email):
    """
    Step 1 of authentication: Generate challenge for the browser.
    Called after password is verified, before OTP.
    Returns: {success, has_passkey, options (JSON string)}
    """
    err = _require_webauthn()
    if err:
        return err

    if not email:
        return {'success': False, 'error': 'Email is required.'}

    email = str(email).strip().lower()

    # Find user's credentials
    try:
        credentials = list(app_tables.webauthn_credentials.search(
            user_email=email, is_active=True
        ))
    except Exception:
        credentials = []

    if len(credentials) == 0:
        return {'success': False, 'has_passkey': False}

    _cleanup_expired_challenges()

    try:
        allow_creds = []
        for cred in credentials:
            try:
                transports = json.loads(cred['transports'] or '[]')
                transport_enums = []
                for t in transports:
                    try:
                        transport_enums.append(AuthenticatorTransport(t))
                    except (ValueError, KeyError):
                        pass
                allow_creds.append(
                    PublicKeyCredentialDescriptor(
                        id=_b64url_decode(cred['credential_id']),
                        transports=transport_enums if transport_enums else None,
                    )
                )
            except Exception:
                pass

        if not allow_creds:
            return {'success': False, 'has_passkey': False}

        options = generate_authentication_options(
            rp_id=_get_rp_id(),
            allow_credentials=allow_creds,
            user_verification=UserVerificationRequirement.REQUIRED,
        )

        _store_challenge(email, options.challenge, 'authenticate')

        options_json = options_to_json(options)
        logger.info("WebAuthn authentication started for: %s", email)

        return {
            'success': True,
            'has_passkey': True,
            'options': options_json,
        }

    except Exception as e:
        logger.error("WebAuthn auth_start error: %s", e)
        return {'success': False, 'error': 'Failed to generate authentication options.'}


@anvil.server.callable
def webauthn_auth_complete(email, assertion_json):
    """
    Step 2 of authentication: Verify the assertion and create a session.
    Returns: {success, token, user}
    """
    err = _require_webauthn()
    if err:
        return err

    if not email:
        return {'success': False, 'error': 'Email is required.'}

    email = str(email).strip().lower()

    # Retrieve stored challenge (memory or database)
    challenge_bytes = _retrieve_challenge(email, 'authenticate')
    if not challenge_bytes:
        return {'success': False, 'error': 'No pending authentication. Please try again.'}

    # Parse assertion to find credential ID
    try:
        parsed = json.loads(assertion_json) if isinstance(assertion_json, str) else assertion_json
        cred_id = parsed.get('id')
    except Exception:
        return {'success': False, 'error': 'Invalid assertion format.'}

    if not cred_id:
        return {'success': False, 'error': 'Missing credential ID.'}

    # Find the credential in our database
    try:
        cred_row = app_tables.webauthn_credentials.get(
            credential_id=cred_id,
            user_email=email,
            is_active=True,
        )
    except Exception:
        cred_row = None

    if not cred_row:
        return {'success': False, 'error': 'Unknown credential.'}

    try:
        verification = verify_authentication_response(
            credential=assertion_json,
            expected_challenge=challenge_bytes,
            expected_rp_id=_get_rp_id(),
            expected_origin=_get_origin(),
            credential_public_key=_b64url_decode(cred_row['public_key']),
            credential_current_sign_count=int(cred_row['sign_count'] or 0),
        )

        # Update sign count + last_used
        cred_row.update(
            sign_count=int(verification.new_sign_count) if verification.new_sign_count else 0,
            last_used=get_utc_now(),
        )

        # Verify user is still active
        user = app_tables.users.get(email=email)
        if not user:
            return {'success': False, 'error': 'User not found.'}
        if not user['is_active'] or not user['is_approved']:
            return {'success': False, 'error': 'Account is disabled.'}

        # Update last login
        user.update(
            login_attempts=0,
            locked_until=None,
            last_login=get_utc_now(),
        )

        # Delete old sessions and create new one (same as complete_login)
        for old_session in app_tables.sessions.search(user_email=email):
            old_session.delete()

        from .auth_sessions import create_session as _create_session
        ip = ''
        try:
            from .AuthManager import get_client_ip
            ip = get_client_ip()
        except Exception:
            pass

        token = _create_session(email, user['role'], ip, '')

        if not token:
            return {'success': False, 'error': 'Session creation failed.'}

        # Audit log
        user_display = (user.get('full_name') or '').strip() or email
        log_audit(
            'LOGIN_WEBAUTHN', 'users', user.get('user_id', ''),
            None, {'email': email, 'method': 'passkey'},
            email, ip,
            user_name=user_display,
            action_description='تسجيل دخول بالبصمة - ' + user_display
        )

        logger.info("WebAuthn login successful for: %s", email)

        return {
            'success': True,
            'token': token,
            'user': {
                'email': user['email'],
                'full_name': user.get('full_name', ''),
                'role': user['role'],
                'phone': user.get('phone', ''),
            }
        }

    except Exception as e:
        logger.error("WebAuthn auth_complete error for %s: %s", email, e)
        return {'success': False, 'error': 'Authentication verification failed.'}


# ── Management ──────────────────────────────────────────────────

@anvil.server.callable
def webauthn_list_credentials(token):
    """List all registered passkeys for the current user."""
    session = validate_session(token)
    if not session:
        return {'success': False, 'error': 'Invalid session.'}

    user_email = session['email']
    try:
        creds = list(app_tables.webauthn_credentials.search(
            user_email=user_email, is_active=True
        ))
        result = []
        for c in creds:
            result.append({
                'credential_id': c['credential_id'][:16] + '...',
                'nickname': c['nickname'] or 'Passkey',
                'created_at': str(c['created_at'] or ''),
                'last_used': str(c['last_used'] or 'Never'),
            })
        return {'success': True, 'credentials': result}
    except Exception as e:
        return {'success': False, 'error': 'An error occurred. Please try again later.'}


@anvil.server.callable
def webauthn_remove_credential(token, credential_id_prefix):
    """Remove (deactivate) a registered passkey."""
    session = validate_session(token)
    if not session:
        return {'success': False, 'error': 'Invalid session.'}

    user_email = session['email']
    try:
        creds = list(app_tables.webauthn_credentials.search(
            user_email=user_email, is_active=True
        ))
        for c in creds:
            if c['credential_id'].startswith(credential_id_prefix):
                c.update(is_active=False)
                log_audit(
                    'WEBAUTHN_REMOVE', 'webauthn_credentials', c['credential_id'],
                    None, {'user_email': user_email}, user_email, ''
                )
                return {'success': True, 'message': 'Passkey removed.'}
        return {'success': False, 'error': 'Credential not found.'}
    except Exception as e:
        return {'success': False, 'error': 'An error occurred. Please try again later.'}


# ── Admin Management (Admin-only) ───────────────────────────────

def _is_admin_session(token):
    """Validate session and check admin role. Returns session dict or None."""
    session = validate_session(token)
    if not session:
        return None
    if (session.get('role') or '').strip().lower() != 'admin':
        return None
    return session


@anvil.server.callable
def webauthn_admin_list_credentials(token, user_email):
    """Admin: List all registered passkeys for any user by email."""
    admin = _is_admin_session(token)
    if not admin:
        return {'success': False, 'error': 'Admin access required.', 'credentials': []}

    try:
        creds = list(app_tables.webauthn_credentials.search(
            user_email=user_email, is_active=True
        ))
        result = []
        for c in creds:
            cred_id = c['credential_id'] or ''
            result.append({
                'credential_id': cred_id[:16],
                'credential_id_display': cred_id[:16] + '...' if len(cred_id) > 16 else cred_id,
                'nickname': c['nickname'] or 'Passkey',
                'created_at': str(c['created_at'] or ''),
                'last_used': str(c['last_used'] or 'Never'),
            })
        return {'success': True, 'credentials': result}
    except Exception as e:
        return {'success': False, 'error': 'An error occurred. Please try again later.', 'credentials': []}


@anvil.server.callable
def webauthn_admin_remove_credential(token, user_email, credential_id_prefix):
    """Admin: Remove (deactivate) a passkey for any user."""
    admin = _is_admin_session(token)
    if not admin:
        return {'success': False, 'error': 'Admin access required.'}

    try:
        creds = list(app_tables.webauthn_credentials.search(
            user_email=user_email, is_active=True
        ))
        for c in creds:
            if c['credential_id'] and c['credential_id'].startswith(credential_id_prefix):
                c.update(is_active=False)
                log_audit(
                    'WEBAUTHN_ADMIN_REMOVE', 'webauthn_credentials', c['credential_id'],
                    None, {'user_email': user_email, 'admin': admin['email']},
                    admin['email'], ''
                )
                return {'success': True, 'message': 'Passkey removed.'}
        return {'success': False, 'error': 'Credential not found.'}
    except Exception as e:
        return {'success': False, 'error': 'An error occurred. Please try again later.'}

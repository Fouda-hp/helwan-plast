"""
auth_totp.py - منطق TOTP (تطبيق المصادقة)
يُستورد من AuthManager؛ لا يعتمد على AuthManager لتجنب استيراد دائري.
"""

import json
import base64
import hashlib
import io
import logging
import secrets
from datetime import datetime, timedelta
from anvil.tables import app_tables

try:
    from .auth_utils import get_utc_now
except ImportError:
    from auth_utils import get_utc_now

logger = logging.getLogger(__name__)


def _generate_backup_codes(count=8):
    """Generate a set of single-use backup codes (24-char hex each, 96-bit entropy)."""
    return [secrets.token_hex(12) for _ in range(count)]


def _hash_backup_code(code):
    """SHA-256 hash a backup code for safe storage."""
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()


def verify_backup_code_impl(user_email, code):
    """
    التحقق من كود احتياطي (backup code) واستهلاكه.
    يُرجع True إذا الكود صحيح (يُستخدم مرة واحدة فقط).
    """
    try:
        user = app_tables.users.get(email=user_email)
        if not user:
            return False
        stored = user.get('totp_backup_codes')
        if not stored:
            return False
        try:
            hashes = json.loads(stored)
        except (json.JSONDecodeError, TypeError):
            return False
        if not isinstance(hashes, list):
            return False
        code_hash = _hash_backup_code(code)
        if code_hash in hashes:
            hashes.remove(code_hash)  # استخدام مرة واحدة
            user.update(totp_backup_codes=json.dumps(hashes))
            logger.info("Backup code used for %s, remaining: %d", user_email, len(hashes))
            return True
        return False
    except Exception as e:
        logger.error("Backup code verify error: %s", e)
        return False


_totp_attempt_tracker = {}  # {email: {'count': int, 'window_start': float}}
_TOTP_MAX_ATTEMPTS = 5
_TOTP_WINDOW_SECONDS = 60

def verify_totp_for_user(user_email, token):
    """التحقق من كود TOTP من تطبيق المصادقة، أو كود احتياطي. مع حماية من brute force."""
    import time
    try:
        # --- Rate limiting on TOTP attempts ---
        now = time.time()
        tracker = _totp_attempt_tracker.get(user_email)
        if tracker:
            if now - tracker['window_start'] < _TOTP_WINDOW_SECONDS:
                if tracker['count'] >= _TOTP_MAX_ATTEMPTS:
                    logger.warning("TOTP rate limit exceeded for %s", user_email)
                    return False
            else:
                # Reset window
                _totp_attempt_tracker[user_email] = {'count': 0, 'window_start': now}

        import pyotp
        user = app_tables.users.get(email=user_email)
        if not user:
            return False
        secret = user.get('totp_secret')
        if not secret:
            return False
        totp = pyotp.TOTP(secret)
        code = str(token).strip().replace(' ', '')
        # Try TOTP first
        if totp.verify(code, valid_window=1):
            # Reset attempts on success
            _totp_attempt_tracker.pop(user_email, None)
            return True
        # If TOTP fails, try as backup code
        if verify_backup_code_impl(user_email, code):
            _totp_attempt_tracker.pop(user_email, None)
            return True
        # Track failed attempt
        if user_email not in _totp_attempt_tracker:
            _totp_attempt_tracker[user_email] = {'count': 0, 'window_start': now}
        _totp_attempt_tracker[user_email]['count'] += 1
        return False
    except Exception as e:
        logger.error("TOTP verify error: %s", e)
        return False


def setup_totp_start_impl(user_email):
    """
    بدء تفعيل TOTP (بعد التحقق من الجلسة في AuthManager).
    يُرجع: dict مع success, provisioning_uri, qr_base64, secret أو message خطأ.
    """
    try:
        import pyotp
        import qrcode
        user = app_tables.users.get(email=user_email)
        if not user:
            return {'success': False, 'message': 'User not found'}
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=user_email, issuer_name='Helwan Plast')
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        qr_base64 = base64.b64encode(buf.getvalue()).decode()
        pending_key = 'pending_totp_' + user_email.replace('@', '_at_').replace('.', '_')
        try:
            old = app_tables.settings.get(setting_key=pending_key)
            if old:
                old.delete()
        except Exception as _e:
            logger.debug("Suppressed: %s", _e)
        expires_at = (get_utc_now() + timedelta(minutes=10)).isoformat()
        app_tables.settings.add_row(
            setting_key=pending_key,
            setting_value=json.dumps({'secret': secret, 'expires_at': expires_at}),
            setting_type='json',
            description='Pending TOTP setup',
            updated_at=get_utc_now()
        )
        return {'success': True, 'provisioning_uri': uri, 'qr_base64': qr_base64, 'secret': secret}
    except Exception as e:
        logger.error("TOTP setup start error: %s", e)
        return {'success': False, 'message': str(e)}


def setup_totp_confirm_impl(user_email, code):
    """
    تأكيد تفعيل TOTP (بعد التحقق من الجلسة في AuthManager).
    يُرجع: dict مع success و message.
    """
    try:
        import pyotp
        code = str(code or '').strip().replace(' ', '')
        if len(code) != 6:
            return {'success': False, 'message': 'Enter the 6-digit code from your app'}
        pending_key = 'pending_totp_' + user_email.replace('@', '_at_').replace('.', '_')
        setting = app_tables.settings.get(setting_key=pending_key)
        if not setting or not setting.get('setting_value'):
            return {'success': False, 'message': 'Setup expired or not started. Please start again.'}
        try:
            data = json.loads(setting['setting_value']) if isinstance(setting['setting_value'], str) else setting['setting_value']
            secret = data.get('secret')
            expires_at = data.get('expires_at')
            if expires_at and get_utc_now() > datetime.fromisoformat(expires_at.replace('Z', '+00:00')):
                setting.delete()
                return {'success': False, 'message': 'Setup expired. Please start again.'}
        except Exception:
            secret = getattr(setting, 'setting_value', None) or (setting.get('setting_value') if isinstance(setting, dict) else None)
        if not secret:
            return {'success': False, 'message': 'Setup expired or not started. Please start again.'}
        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=1):
            return {'success': False, 'message': 'Invalid code. Try again.'}
        user = app_tables.users.get(email=user_email)
        if not user:
            setting.delete()
            return {'success': False, 'message': 'User not found'}
        # Generate backup codes and store hashed versions
        backup_codes = _generate_backup_codes()
        hashed_codes = [_hash_backup_code(c) for c in backup_codes]
        user.update(
            totp_secret=secret,
            totp_backup_codes=json.dumps(hashed_codes)
        )
        setting.delete()
        logger.info("TOTP enabled for %s with %d backup codes", user_email, len(backup_codes))
        return {
            'success': True,
            'message': 'Authenticator app enabled. Save your backup codes!',
            'backup_codes': backup_codes,
        }
    except Exception as e:
        logger.error("TOTP confirm error: %s", e)
        return {'success': False, 'message': str(e)}

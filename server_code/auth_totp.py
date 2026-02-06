"""
auth_totp.py - منطق TOTP (تطبيق المصادقة)
يُستورد من AuthManager؛ لا يعتمد على AuthManager لتجنب استيراد دائري.
"""

import json
import base64
import io
import logging
from datetime import datetime, timedelta
from anvil.tables import app_tables

logger = logging.getLogger(__name__)


def verify_totp_for_user(user_email, token):
    """التحقق من كود TOTP من تطبيق المصادقة."""
    try:
        import pyotp
        user = app_tables.users.get(email=user_email)
        if not user:
            return False
        secret = user.get('totp_secret')
        if not secret:
            return False
        totp = pyotp.TOTP(secret)
        return totp.verify(str(token).strip().replace(' ', ''), valid_window=1)
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
        except Exception:
            pass
        expires_at = (datetime.now() + timedelta(minutes=10)).isoformat()
        app_tables.settings.add_row(
            setting_key=pending_key,
            setting_value=json.dumps({'secret': secret, 'expires_at': expires_at}),
            setting_type='json',
            description='Pending TOTP setup',
            updated_at=datetime.now()
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
            if expires_at and datetime.now() > datetime.fromisoformat(expires_at.replace('Z', '+00:00')):
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
        user.update(totp_secret=secret)
        setting.delete()
        return {'success': True, 'message': 'Authenticator app enabled. Use it at next login.'}
    except Exception as e:
        logger.error("TOTP confirm error: %s", e)
        return {'success': False, 'message': str(e)}

"""
auth_helpers.py — دوال مساعدة للمصادقة (تحقق، تشفير، جلسات أساسية، IP).
يُستورد في AuthManager ولا يغيّر أي سلوك.
"""
import re
import secrets
import uuid
from datetime import datetime
import anvil.server
from anvil.tables import app_tables

from auth_config import (
    logger,
    PBKDF2_ITERATIONS,
    PASSWORD_HISTORY_COUNT,
)


def validate_email(email):
    """التحقق من صحة البريد الإلكتروني"""
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False
    if len(email) > 254 or '..' in email:
        return False
    return True


def hash_password(password):
    """تشفير كلمة المرور (PBKDF2)"""
    import hashlib
    salt = secrets.token_hex(32)
    key = hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), salt.encode('utf-8'), PBKDF2_ITERATIONS
    )
    return f"{salt}:{key.hex()}"


def verify_password(password, stored_hash):
    """التحقق من كلمة المرور (يدعم PBKDF2 و SHA-256 القديم)"""
    if not stored_hash:
        return False
    try:
        import hashlib
        if ':' in stored_hash:
            salt, hash_value = stored_hash.split(':', 1)
            key = hashlib.pbkdf2_hmac(
                'sha256', password.encode('utf-8'), salt.encode('utf-8'), PBKDF2_ITERATIONS
            )
            return secrets.compare_digest(key.hex(), hash_value)
        old_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        return secrets.compare_digest(old_hash, stored_hash)
    except Exception as e:
        logger.error("Password verification error: %s", e)
        return False


def upgrade_password_hash(user, password):
    """ترقية هاش كلمة المرور من SHA-256 إلى PBKDF2"""
    try:
        stored_hash = user.get('password_hash')
        if stored_hash and ':' not in stored_hash:
            new_hash = hash_password(password)
            user.update(password_hash=new_hash)
            logger.info("Password hash upgraded for user: %s", user.get('email'))
            return True
    except Exception as e:
        logger.error("Error upgrading password hash: %s", e)
    return False


def add_to_password_history(user_email, password_hash):
    """إضافة كلمة المرور لسجل التاريخ"""
    try:
        app_tables.password_history.add_row(
            history_id=str(uuid.uuid4()),
            user_email=user_email,
            password_hash=password_hash,
            created_at=datetime.now()
        )
        history = list(app_tables.password_history.search(user_email=user_email))
        history.sort(key=lambda x: x['created_at'], reverse=True)
        for old in history[PASSWORD_HISTORY_COUNT:]:
            old.delete()
        return True
    except Exception as e:
        logger.error("Failed to add password to history: %s", e)
        return False


def check_password_history(user_email, new_password):
    """التحقق من عدم تكرار كلمة المرور"""
    try:
        for record in app_tables.password_history.search(user_email=user_email):
            if verify_password(new_password, record['password_hash']):
                return False, f"Cannot reuse any of your last {PASSWORD_HISTORY_COUNT} passwords"
        return True, "Password is valid"
    except Exception as e:
        logger.error("Password history check error: %s", e)
        return True, "Check passed"


def generate_session_token():
    """توليد رمز جلسة آمن"""
    return secrets.token_urlsafe(64)


def generate_otp():
    """توليد OTP من 6 أرقام"""
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])


def get_client_ip():
    """الحصول على IP العميل من سياق الطلب"""
    try:
        context = anvil.server.context
        if hasattr(context, 'client') and context.client and hasattr(context.client, 'ip'):
            return context.client.ip or 'unknown'
    except Exception:
        pass
    return 'unknown'

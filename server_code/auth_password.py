"""
auth_password.py - تشفير كلمات المرور وسجل كلمات المرور السابقة (PBKDF2)
"""

import hashlib
import secrets
import uuid
import logging
from datetime import datetime
from anvil.tables import app_tables

from .auth_constants import PBKDF2_ITERATIONS, PASSWORD_HISTORY_COUNT
from .auth_utils import get_utc_now

logger = logging.getLogger(__name__)


def hash_password(password):
    salt = secrets.token_hex(32)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), PBKDF2_ITERATIONS)
    return f"{salt}:{key.hex()}"


def verify_password(password, stored_hash):
    if not stored_hash:
        return False
    try:
        if ':' in stored_hash:
            salt, hash_value = stored_hash.split(':', 1)
            key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), PBKDF2_ITERATIONS)
            return secrets.compare_digest(key.hex(), hash_value)
        old_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        return secrets.compare_digest(old_hash, stored_hash)
    except Exception as e:
        logger.error("Password verification error: %s", e)
        return False


def upgrade_password_hash(user, password):
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
    try:
        app_tables.password_history.add_row(
            history_id=str(uuid.uuid4()),
            user_email=user_email,
            password_hash=password_hash,
            created_at=get_utc_now()
        )
        history = list(app_tables.password_history.search(user_email=user_email))
        history.sort(key=lambda x: x['created_at'], reverse=True)
        if len(history) > PASSWORD_HISTORY_COUNT:
            for old in history[PASSWORD_HISTORY_COUNT:]:
                old.delete()
        return True
    except Exception as e:
        logger.error("Failed to add password to history: %s", e)
        return False


def check_password_history(user_email, new_password):
    try:
        history = list(app_tables.password_history.search(user_email=user_email))
        for record in history:
            if verify_password(new_password, record['password_hash']):
                return False, f"Cannot reuse any of your last {PASSWORD_HISTORY_COUNT} passwords"
        return True, "Password is valid"
    except Exception as e:
        logger.error("Password history check error: %s", e)
        return True, "Check passed"

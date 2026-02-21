import anvil.users
# anvil.files not used here; removed to avoid posixpath.getcwd() errors in some environments
"""
auth_sessions.py - إدارة الجلسات (إنشاء، التحقق، إنهاء، تنظيف)
مع تشفير التوكن في قاعدة البيانات (hash فقط) + تنظيف تلقائي مجدول
V4.0 - Fixed timezone-aware datetime comparisons
"""

import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from anvil.tables import app_tables

try:
    from .auth_constants import SESSION_DURATION_MINUTES, MAX_SESSIONS_PER_USER
except ImportError:
    from auth_constants import SESSION_DURATION_MINUTES, MAX_SESSIONS_PER_USER
try:
    from .auth_utils import get_utc_now, make_aware
except ImportError:
    from auth_utils import get_utc_now, make_aware

logger = logging.getLogger(__name__)


def _hash_token(token):
    """تشفير التوكن باستخدام SHA-256 للتخزين في قاعدة البيانات"""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def generate_session_token():
    return secrets.token_urlsafe(64)


def create_session(user_email, role, ip_address=None, user_agent=None):
    token = generate_session_token()
    token_hash = _hash_token(token)
    expires = get_utc_now() + timedelta(minutes=SESSION_DURATION_MINUTES)
    ip = ip_address or 'unknown'
    try:
        active_sessions = list(app_tables.sessions.search(user_email=user_email, is_active=True))
        now = get_utc_now()
        valid_sessions = [s for s in active_sessions if make_aware(s['expires_at']) > now]
        for s in active_sessions:
            if make_aware(s['expires_at']) <= now:
                s.update(is_active=False)
        if len(valid_sessions) >= MAX_SESSIONS_PER_USER:
            valid_sessions.sort(key=lambda s: s['created_at'])
            valid_sessions[0].update(is_active=False)
        app_tables.sessions.add_row(
            session_token=token_hash,
            user_email=user_email,
            user_role=role,
            created_at=get_utc_now(),
            expires_at=expires,
            ip_address=ip,
            user_agent=user_agent or 'unknown',
            is_active=True
        )
        logger.info("Session created for %s from IP %s", user_email, ip)
        return token  # يُرجع التوكن الأصلي للمستخدم (الـ hash فقط في DB)
    except Exception as e:
        logger.error("Session creation error: %s", e)
        return None


def validate_session(token):
    if not token:
        return None
    try:
        token_hash = _hash_token(token)
        session = app_tables.sessions.get(session_token=token_hash, is_active=True)

        if not session:
            return None
        expires_at = session.get('expires_at')
        if expires_at is not None:
            try:
                if get_utc_now() > make_aware(expires_at):
                    session.update(is_active=False)
                    return None
            except (TypeError, ValueError):
                logger.warning("Invalid expires_at format for session: %s", session.get('user_email', 'unknown'))
        user = app_tables.users.get(email=session['user_email'])
        if not user:
            session.update(is_active=False)
            return None
        if not user['is_active'] or not user['is_approved']:
            session.update(is_active=False)
            return None
        # Sliding expiration - تمديد الجلسة عند كل استخدام ناجح
        try:
            new_expires = get_utc_now() + timedelta(minutes=SESSION_DURATION_MINUTES)
            session.update(expires_at=new_expires)
        except Exception as e:
            logger.warning("Failed to extend session for %s: %s", session['user_email'], e)
        return {
            'email': session['user_email'],
            'role': user['role'],
            'full_name': user.get('full_name', ''),
            'phone': user.get('phone', ''),
            'is_active': user['is_active'],
            'is_approved': user['is_approved'],
            'created': session['created_at'],
            'expires': session['expires_at']
        }
    except Exception as e:
        logger.error("Session validation error: %s", e)
        return None


def destroy_session(token):
    if not token:
        return False
    try:
        token_hash = _hash_token(token)
        session = app_tables.sessions.get(session_token=token_hash)

        # Legacy token fallback removed for security.
        # All sessions must use hashed tokens.

        if session:
            session.update(is_active=False)
            return True
        return False
    except Exception as e:
        logger.error("Session destruction error: %s", e)
        return False


def cleanup_expired_sessions():
    """تنظيف الجلسات المنتهية - يمكن استدعاؤها يدوياً أو عبر Scheduler"""
    try:
        import anvil.tables.query as q
        now = get_utc_now()
        # Use DB-level filter to reduce data transfer
        expired_sessions = list(app_tables.sessions.search(
            is_active=True,
            expires_at=q.less_than(now)
        ))
        cleaned = 0
        for s in expired_sessions:
            try:
                s.update(is_active=False)
                cleaned += 1
            except Exception:
                pass  # Skip individual failures
        if cleaned > 0:
            logger.info("Cleaned up %d expired sessions", cleaned)
        return cleaned
    except Exception as e:
        logger.error("Cleanup sessions error: %s", e)
        return 0


def purge_old_sessions(days=30):
    """
    حذف نهائي للسيشنز القديمة غير النشطة (is_active=False) التي مضى عليها أكثر من days يوم.
    يُستدعى من scheduled_session_cleanup أو يدوياً لمنع تراكم السيشنز في قاعدة البيانات.
    """
    try:
        import anvil.tables.query as q
        cutoff = get_utc_now() - timedelta(days=days)
        old_sessions = list(app_tables.sessions.search(
            is_active=False,
            expires_at=q.less_than(cutoff)
        ))
        purged = 0
        for s in old_sessions:
            try:
                s.delete()
                purged += 1
            except Exception:
                pass
        if purged > 0:
            logger.info("Purged %d old inactive sessions (older than %d days)", purged, days)
        return purged
    except Exception as e:
        logger.error("Purge old sessions error: %s", e)
        return 0

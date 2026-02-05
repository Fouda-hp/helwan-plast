"""
auth_sessions.py - إدارة الجلسات (إنشاء، التحقق، إنهاء، تنظيف)
"""

import secrets
import logging
from datetime import datetime, timedelta
from anvil.tables import app_tables

from .auth_constants import SESSION_DURATION_MINUTES, MAX_SESSIONS_PER_USER

logger = logging.getLogger(__name__)


def generate_session_token():
    return secrets.token_urlsafe(64)


def create_session(user_email, role, ip_address=None, user_agent=None):
    token = generate_session_token()
    expires = datetime.now() + timedelta(minutes=SESSION_DURATION_MINUTES)
    ip = ip_address or 'unknown'
    try:
        active_sessions = list(app_tables.sessions.search(user_email=user_email, is_active=True))
        now = datetime.now()
        valid_sessions = [s for s in active_sessions if s['expires_at'] > now]
        for s in active_sessions:
            if s['expires_at'] <= now:
                s.update(is_active=False)
        if len(valid_sessions) >= MAX_SESSIONS_PER_USER:
            valid_sessions.sort(key=lambda s: s['created_at'])
            valid_sessions[0].update(is_active=False)
        app_tables.sessions.add_row(
            session_token=token,
            user_email=user_email,
            user_role=role,
            created_at=datetime.now(),
            expires_at=expires,
            ip_address=ip,
            user_agent=user_agent or 'unknown',
            is_active=True
        )
        logger.info("Session created for %s from IP %s", user_email, ip)
        return token
    except Exception as e:
        logger.error("Session creation error: %s", e)
        return None


def validate_session(token):
    if not token:
        return None
    try:
        session = app_tables.sessions.get(session_token=token, is_active=True)
        if not session:
            return None
        expires_at = session.get('expires_at')
        if expires_at is not None:
            try:
                if datetime.now() > expires_at:
                    session.update(is_active=False)
                    return None
            except (TypeError, ValueError):
                pass
        user = app_tables.users.get(email=session['user_email'])
        if not user:
            session.update(is_active=False)
            return None
        if not user['is_active'] or not user['is_approved']:
            session.update(is_active=False)
            return None
        return {
            'email': session['user_email'],
            'role': user['role'],
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
        session = app_tables.sessions.get(session_token=token)
        if session:
            session.update(is_active=False)
            return True
        return False
    except Exception as e:
        logger.error("Session destruction error: %s", e)
        return False


def cleanup_expired_sessions():
    try:
        now = datetime.now()
        for s in app_tables.sessions.search(is_active=True):
            if s.get('expires_at') and s['expires_at'] < now:
                s.update(is_active=False)
    except Exception as e:
        logger.error("Cleanup sessions error: %s", e)

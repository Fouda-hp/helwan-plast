import anvil.users
import anvil.files
from anvil.files import data_files
"""
notifications.py - نظام الإشعارات (Enterprise / SaaS)
====================================================
جدول notifications: id, user_email, type, payload, created_at, read_at (nullable).
يُستدعى تلقائياً عند: إنشاء/تعديل عرض، إنشاء عقد، موافقة/رفض مستخدم، Backup/Restore.
"""

import uuid
import json
import logging
from datetime import datetime

from anvil.tables import app_tables
from anvil.tables import order_by as anvil_order_by
import anvil.server

logger = logging.getLogger(__name__)

# استيراد AuthManager متوافق مع Anvil (نسبي أو مطلق)
try:
    from . import AuthManager
except ImportError:
    import AuthManager


def create_notification(user_email, notif_type, payload):
    """
    إنشاء إشعار لمستخدم.
    payload: dict يُحوَّل إلى JSON ويُخزَّن في عمود payload.
    """
    if not user_email or not str(user_email).strip():
        return
    try:
        app_tables.notifications.add_row(
            id=str(uuid.uuid4()),
            user_email=str(user_email).strip().lower(),
            type=str(notif_type),
            payload=json.dumps(payload, ensure_ascii=False, default=str),
            created_at=datetime.now(),
            read_at=None
        )
    except Exception as e:
        logger.warning("Failed to create notification for %s: %s", user_email, e)


def _user_email_from_token(token_or_email):
    if not token_or_email:
        return None
    # ⛔ لا يتم قبول البريد كتوكن - يجب التحقق من الجلسة دائماً
    result = AuthManager.validate_token(token_or_email)
    if result and result.get('valid') and result.get('user'):
        return (result.get('user', {}).get('email') or '').strip().lower()
    return None


@anvil.server.callable
def get_user_notifications(token_or_email, limit=50, unread_only=False):
    """جلب إشعارات المستخدم الحالي (من الأحدث للأقدم)."""
    user_email = _user_email_from_token(token_or_email)
    if not user_email:
        return {'success': False, 'data': [], 'message': 'Authentication required'}
    try:
        limit = max(1, min(200, int(limit) if limit is not None else 50))
        try:
            rows = list(app_tables.notifications.search(user_email=user_email, order_by=[anvil_order_by('created_at', False)]))
        except Exception:
            rows = list(app_tables.notifications.search(user_email=user_email))
            rows.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
        if unread_only:
            rows = [r for r in rows if r.get('read_at') is None]
        rows = rows[:limit]
        data = []
        for r in rows:
            try:
                pl = json.loads(r['payload']) if isinstance(r.get('payload'), str) else (r.get('payload') or {})
            except (json.JSONDecodeError, TypeError):
                pl = {}
            data.append({
                'id': r['id'],
                'type': r.get('type', ''),
                'payload': pl,
                'created_at': r.get('created_at').isoformat() if r.get('created_at') else None,
                'read_at': r.get('read_at').isoformat() if r.get('read_at') else None,
            })
        return {'success': True, 'data': data}
    except Exception as e:
        return {'success': False, 'data': [], 'message': str(e)}


@anvil.server.callable
def mark_notification_read(notification_id, token_or_email):
    """تعليم إشعار كمقروء."""
    user_email = _user_email_from_token(token_or_email)
    if not user_email:
        return {'success': False, 'message': 'Authentication required'}
    try:
        row = app_tables.notifications.get(id=notification_id, user_email=user_email)
        if row:
            row.update(read_at=datetime.now())
        return {'success': True}
    except Exception as e:
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def clear_all_notifications(token_or_email):
    """تفريغ قائمة الإشعارات (تعليم الكل كمقروء للاحتفاظ بالسجل)."""
    user_email = _user_email_from_token(token_or_email)
    if not user_email:
        return {'success': False, 'message': 'Authentication required'}
    try:
        now = datetime.now()
        for row in app_tables.notifications.search(user_email=user_email, read_at=None):
            row.update(read_at=now)
        return {'success': True}
    except Exception as e:
        return {'success': False, 'message': str(e)}

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

try:
    from .auth_utils import get_utc_now
except ImportError:
    from auth_utils import get_utc_now
from anvil.tables import order_by as anvil_order_by
import anvil.server

logger = logging.getLogger(__name__)

# استيراد AuthManager متوافق مع Anvil (نسبي أو مطلق)
try:
    from . import AuthManager
except ImportError:
    import AuthManager

try:
    from . import auth_email
except ImportError:
    import auth_email


def _get_admin_emails():
    """قائمة بريد كل الأدمن النشطين (لإرسال إشعار لكل أدمن عند أي إجراء)."""
    try:
        admins = list(app_tables.users.search(role='admin', is_active=True))
        return [str(a.get('email', '')).strip().lower() for a in admins if a.get('email')]
    except Exception as e:
        logger.warning("Failed to get admin emails: %s", e)
        return []


def _send_notification_email(user_email, notif_type, payload):
    """إرسال بريد إلكتروني عند إنشاء إشعار (fire-and-forget)."""
    try:
        if not user_email or not str(user_email).strip():
            return
        msg_en = payload.get('message_en', '') if isinstance(payload, dict) else ''
        msg_ar = payload.get('message_ar', '') if isinstance(payload, dict) else ''
        if not msg_en and not msg_ar:
            msg_en = f'Notification: {notif_type}'
        subject = f'Helwan Plast - {msg_en[:80]}' if msg_en else f'Helwan Plast - {msg_ar[:80]}'
        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0; text-align: center;">Helwan Plast</h1>
            </div>
            <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                <p style="font-size: 16px; color: #333; direction: ltr;">{msg_en}</p>
                <p style="font-size: 16px; color: #333; direction: rtl; text-align: right;">{msg_ar}</p>
                <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                <p style="font-size: 12px; color: #999; text-align: center;">Helwan Plast Notification System</p>
            </div>
        </div>
        """
        auth_email.send_email_smtp(str(user_email).strip(), subject, html_body)
    except Exception as e:
        logger.warning("Notification email failed for %s: %s", user_email, e)


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
            created_at=get_utc_now(),
            read_at=None
        )
        _send_notification_email(user_email, notif_type, payload)
    except Exception as e:
        logger.warning("Failed to create notification for %s: %s", user_email, e)


def create_notification_for_all_admins(notif_type, payload):
    """
    إنشاء إشعار لكل الأدمن — حتى يظهر كل إجراء (ولو طفيف) عند كل أدمن.
    يُستدعى تلقائياً من سجل التدقيق أو من دوال الحفظ/التعديل.
    """
    admin_emails = _get_admin_emails()
    for email in admin_emails:
        try:
            app_tables.notifications.add_row(
                id=str(uuid.uuid4()),
                user_email=email,
                type=str(notif_type),
                payload=json.dumps(payload, ensure_ascii=False, default=str),
                created_at=get_utc_now(),
                read_at=None
            )
            _send_notification_email(email, notif_type, payload)
        except Exception as e:
            logger.warning("Failed to create admin notification for %s: %s", email, e)


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
            row.update(read_at=get_utc_now())
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
        now = get_utc_now()
        for row in app_tables.notifications.search(user_email=user_email, read_at=None):
            row.update(read_at=now)
        return {'success': True}
    except Exception as e:
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def delete_all_my_notifications(token_or_email):
    """حذف كل إشعارات المستخدم الحالي من الجدول (مسح كامل للقائمة)."""
    user_email = _user_email_from_token(token_or_email)
    if not user_email:
        return {'success': False, 'message': 'Authentication required', 'deleted_count': 0}
    try:
        rows = list(app_tables.notifications.search(user_email=user_email))
        count = 0
        for row in rows:
            row.delete()
            count += 1
        logger.info("Deleted %s notifications for user %s", count, user_email)
        return {'success': True, 'deleted_count': count}
    except Exception as e:
        logger.warning("delete_all_my_notifications: %s", e)
        return {'success': False, 'message': str(e), 'deleted_count': 0}


@anvil.server.callable
def delete_notification(notification_id, token_or_email):
    """حذف إشعار واحد من الجدول (للمستخدم الحالي فقط)."""
    user_email = _user_email_from_token(token_or_email)
    if not user_email:
        return {'success': False, 'message': 'Authentication required'}
    if not notification_id or not str(notification_id).strip():
        return {'success': False, 'message': 'Notification ID required'}
    try:
        row = app_tables.notifications.get(id=str(notification_id).strip(), user_email=user_email)
        if row:
            row.delete()
            return {'success': True}
        return {'success': False, 'message': 'Notification not found or access denied'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_all_notifications_admin(token_or_email, limit=50):
    """جلب كل الإشعارات (لكل المستخدمين) — للأدمن فقط."""
    user_email = _user_email_from_token(token_or_email)
    if not user_email:
        return {'success': False, 'data': [], 'message': 'Authentication required'}
    # Verify admin
    is_admin = AuthManager.is_admin(token_or_email) or AuthManager.is_admin_by_email(user_email)
    if not is_admin:
        return {'success': False, 'data': [], 'message': 'Admin access required'}
    try:
        limit = max(1, min(200, int(limit) if limit is not None else 50))
        try:
            rows = list(app_tables.notifications.search(order_by=[anvil_order_by('created_at', False)]))
        except Exception:
            rows = list(app_tables.notifications.search())
            rows.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
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
                'user_email': r.get('user_email', ''),
                'created_at': r.get('created_at').isoformat() if r.get('created_at') else None,
                'read_at': r.get('read_at').isoformat() if r.get('read_at') else None,
            })
        return {'success': True, 'data': data}
    except Exception as e:
        return {'success': False, 'data': [], 'message': str(e)}

import anvil.users
# anvil.files removed to avoid posixpath.getcwd() errors at app load (e.g. login)
"""
notifications.py - نظام الإشعارات (Enterprise / SaaS)
====================================================
جدول notifications: id, user_email, type, payload, created_at, read_at (nullable).
يُستدعى تلقائياً عند: إنشاء/تعديل عرض، إنشاء عقد، موافقة/رفض مستخدم، Backup/Restore.
"""

import uuid
import json
import html as _html_mod
import logging
from datetime import datetime, timedelta

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
    """
    إرسال بريد إلكتروني عند إنشاء إشعار.
    ⚠️ يتم الإرسال فقط لإشعارات المتابعة (follow-up) — باقي الأنواع تظهر في الجرس فقط.
    """
    try:
        # === Only send emails for follow-up notifications ===
        if notif_type not in ('followup_set', 'followup_overdue', 'followup_snoozed', 'followup_completed'):
            return

        if not user_email or not str(user_email).strip():
            return

        if not isinstance(payload, dict):
            payload = {}

        qn = _html_mod.escape(str(payload.get('quotation_number', '')))
        client_name = _html_mod.escape(str(payload.get('client_name', '') or 'N/A'))
        fu_date = _html_mod.escape(str(payload.get('follow_up_date', '') or 'N/A'))
        created_by = _html_mod.escape(str(payload.get('created_by', '') or 'N/A'))

        # Build subject
        if notif_type == 'followup_set':
            subject_en = f'Follow-Up Set - Quotation #{qn} - {client_name}'
            title_en = 'New Follow-Up Created'
            title_ar = 'تم إنشاء متابعة جديدة'
        elif notif_type == 'followup_overdue':
            subject_en = f'Follow-Up OVERDUE - Quotation #{qn} - {client_name}'
            title_en = 'Follow-Up Overdue!'
            title_ar = 'متابعة متأخرة!'
        elif notif_type == 'followup_snoozed':
            subject_en = f'Follow-Up Snoozed - Quotation #{qn}'
            title_en = 'Follow-Up Snoozed'
            title_ar = 'تم تأجيل المتابعة'
        elif notif_type == 'followup_completed':
            subject_en = f'Follow-Up Completed - Quotation #{qn}'
            title_en = 'Follow-Up Completed'
            title_ar = 'تم إتمام المتابعة'
        else:
            subject_en = f'Helwan Plast - Follow-Up #{qn}'
            title_en = 'Follow-Up Notification'
            title_ar = 'إشعار متابعة'

        subject = f'Helwan Plast - {subject_en}'

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #B8860B 0%, #DAA520 50%, #FFD700 100%); padding: 20px; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0; text-align: center; text-shadow: 0 1px 3px rgba(0,0,0,0.3);">Helwan Plast</h1>
                <p style="color: rgba(255,255,255,0.9); margin: 8px 0 0; text-align: center; font-size: 14px;">{title_en} / {title_ar}</p>
            </div>
            <div style="background: #ffffff; padding: 30px; border: 1px solid #e0e0e0;">
                <table style="width: 100%; border-collapse: collapse; font-size: 15px;">
                    <tr>
                        <td style="padding: 10px 12px; font-weight: bold; color: #555; border-bottom: 1px solid #f0f0f0; width: 160px;">Quotation # / رقم العرض</td>
                        <td style="padding: 10px 12px; color: #333; border-bottom: 1px solid #f0f0f0; font-weight: 600;">{qn}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px 12px; font-weight: bold; color: #555; border-bottom: 1px solid #f0f0f0;">Client / العميل</td>
                        <td style="padding: 10px 12px; color: #333; border-bottom: 1px solid #f0f0f0; font-weight: 600;">{client_name}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px 12px; font-weight: bold; color: #555; border-bottom: 1px solid #f0f0f0;">Follow-Up Date / تاريخ المتابعة</td>
                        <td style="padding: 10px 12px; color: #333; border-bottom: 1px solid #f0f0f0; font-weight: 600;">{fu_date}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px 12px; font-weight: bold; color: #555; border-bottom: 1px solid #f0f0f0;">Created By / أنشأها</td>
                        <td style="padding: 10px 12px; color: #333; border-bottom: 1px solid #f0f0f0; font-weight: 600;">{created_by}</td>
                    </tr>
                </table>
            </div>
            <div style="background: #f8f9fa; padding: 16px; border-radius: 0 0 10px 10px; border: 1px solid #e0e0e0; border-top: none;">
                <p style="font-size: 12px; color: #999; text-align: center; margin: 0;">Helwan Plast Notification System</p>
            </div>
        </div>
        """
        auth_email.send_email_smtp(str(user_email).strip(), subject, html_body)
    except Exception as e:
        logger.warning("Notification email failed for %s: %s", user_email, e)


def _dedup_key(notif_type, payload_json):
    """مفتاح مختصر لمنع التكرار — يعتمد على النوع + أهم الحقول فقط."""
    try:
        pl = json.loads(payload_json) if isinstance(payload_json, str) else (payload_json or {})
    except Exception:
        pl = {}
    # لإشعارات الـ audit: المقارنة بالـ action فقط (مش الـ record_id الكامل)
    if notif_type == 'audit_action':
        return notif_type + '|' + str(pl.get('action', ''))
    # لباقي الأنواع: المقارنة بأول 3 قيم من الـ payload
    keys = sorted(pl.keys())[:3]
    parts = [notif_type]
    for k in keys:
        parts.append(str(k) + '=' + str(pl.get(k, ''))[:50])
    return '|'.join(parts)


def _is_duplicate_notification(user_email, notif_type, payload_json, seconds=60):
    """تحقق من عدم وجود إشعار مشابه خلال آخر N ثانية (منع التكرار)."""
    try:
        import anvil.tables.query as q
        new_key = _dedup_key(notif_type, payload_json)
        cutoff = get_utc_now() - timedelta(seconds=seconds)
        # Filter by created_at in the DB query to reduce data transfer
        recent = app_tables.notifications.search(
            user_email=user_email,
            type=notif_type,
            created_at=q.greater_than_or_equal_to(cutoff)
        )
        for r in recent:
            existing_key = _dedup_key(notif_type, r.get('payload'))
            if existing_key == new_key:
                return True
        return False
    except Exception:
        return False


def create_notification(user_email, notif_type, payload):
    """
    إنشاء إشعار لمستخدم.
    payload: dict يُحوَّل إلى JSON ويُخزَّن في عمود payload.
    """
    if not user_email or not str(user_email).strip():
        return
    try:
        email = str(user_email).strip().lower()
        payload_json = json.dumps(payload, ensure_ascii=False, default=str)
        if _is_duplicate_notification(email, notif_type, payload_json):
            return
        app_tables.notifications.add_row(
            id=str(uuid.uuid4()),
            user_email=email,
            type=str(notif_type),
            payload=payload_json,
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
    payload_json = json.dumps(payload, ensure_ascii=False, default=str)
    for email in admin_emails:
        try:
            if _is_duplicate_notification(email, notif_type, payload_json):
                continue
            app_tables.notifications.add_row(
                id=str(uuid.uuid4()),
                user_email=email,
                type=str(notif_type),
                payload=payload_json,
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
def get_unread_notification_count(token_or_email):
    """Return ONLY the unread count (lightweight endpoint for badge polling)."""
    user_email = _user_email_from_token(token_or_email)
    if not user_email:
        return {'success': False, 'count': 0}
    try:
        # Use len() on search result which is more efficient than iteration
        results = app_tables.notifications.search(user_email=user_email, read_at=None)
        count = min(len(results), 999)
        return {'success': True, 'count': count}
    except Exception as e:
        return {'success': False, 'count': 0, 'message': str(e)}


@anvil.server.callable
def get_user_notifications(token_or_email, limit=50, unread_only=False):
    """جلب إشعارات المستخدم الحالي (من الأحدث للأقدم)."""
    user_email = _user_email_from_token(token_or_email)
    if not user_email:
        return {'success': False, 'data': [], 'message': 'Authentication required'}
    try:
        limit = max(1, min(200, int(limit) if limit is not None else 50))
        rows = []
        try:
            search_iter = app_tables.notifications.search(user_email=user_email, order_by=[anvil_order_by('created_at', ascending=False)])
            for r in search_iter:
                if unread_only and r.get('read_at') is not None:
                    continue
                rows.append(r)
                if len(rows) >= limit:
                    break
        except Exception:
            # Fallback: load limited batch, sort, then slice
            _all = []
            for r in app_tables.notifications.search(user_email=user_email):
                if unread_only and r.get('read_at') is not None:
                    continue
                _all.append(r)
                if len(_all) >= limit * 5:
                    break
            _all.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
            rows = _all[:limit]
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
    """تعليم إشعار كمقروء (الأدمن يمكنه تعديل أي إشعار)."""
    user_email = _user_email_from_token(token_or_email)
    if not user_email:
        return {'success': False, 'message': 'Authentication required'}
    try:
        row = app_tables.notifications.get(id=notification_id, user_email=user_email)
        if not row:
            # Admin can mark any notification as read
            if AuthManager.is_admin(token_or_email):
                row = app_tables.notifications.get(id=notification_id)
        if row:
            row.update(read_at=get_utc_now())
            return {'success': True}
        return {'success': False, 'message': 'Notification not found or access denied'}
    except Exception as e:
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def mark_notification_unread(notification_id, token_or_email):
    """تعليم إشعار كغير مقروء (الأدمن يمكنه تعديل أي إشعار)."""
    user_email = _user_email_from_token(token_or_email)
    if not user_email:
        return {'success': False, 'message': 'Authentication required'}
    try:
        row = app_tables.notifications.get(id=notification_id, user_email=user_email)
        if not row:
            # Admin can mark any notification as unread
            if AuthManager.is_admin(token_or_email):
                row = app_tables.notifications.get(id=notification_id)
        if row:
            row.update(read_at=None)
            return {'success': True}
        return {'success': False, 'message': 'Notification not found or access denied'}
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
def delete_all_notifications_admin(token_or_email):
    """حذف كل الإشعارات من الجدول — للأدمن فقط."""
    user_email = _user_email_from_token(token_or_email)
    if not user_email:
        return {'success': False, 'message': 'Authentication required', 'deleted_count': 0}
    if not AuthManager.is_admin(token_or_email):
        return {'success': False, 'message': 'Admin access required', 'deleted_count': 0}
    try:
        rows = list(app_tables.notifications.search())
        count = 0
        for row in rows:
            row.delete()
            count += 1
        logger.info("Admin %s deleted all notifications (%s rows)", user_email, count)
        return {'success': True, 'deleted_count': count}
    except Exception as e:
        logger.warning("delete_all_notifications_admin: %s", e)
        return {'success': False, 'message': str(e), 'deleted_count': 0}


@anvil.server.callable
def delete_notification(notification_id, token_or_email):
    """حذف إشعار واحد من الجدول (الأدمن يمكنه حذف أي إشعار)."""
    user_email = _user_email_from_token(token_or_email)
    if not user_email:
        return {'success': False, 'message': 'Authentication required'}
    if not notification_id or not str(notification_id).strip():
        return {'success': False, 'message': 'Notification ID required'}
    try:
        nid = str(notification_id).strip()
        row = app_tables.notifications.get(id=nid, user_email=user_email)
        if not row and AuthManager.is_admin(token_or_email):
            row = app_tables.notifications.get(id=nid)
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
    is_admin = AuthManager.is_admin(token_or_email)
    if not is_admin:
        return {'success': False, 'data': [], 'message': 'Admin access required'}
    try:
        limit = max(1, min(200, int(limit) if limit is not None else 50))
        rows = []
        try:
            search_iter = app_tables.notifications.search(order_by=[anvil_order_by('created_at', ascending=False)])
            for r in search_iter:
                rows.append(r)
                if len(rows) >= limit:
                    break
        except Exception:
            _all = []
            for r in app_tables.notifications.search():
                _all.append(r)
                if len(_all) >= limit * 5:
                    break
            _all.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
            rows = _all[:limit]
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

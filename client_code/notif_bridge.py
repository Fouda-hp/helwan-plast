"""
notif_bridge - Shared notification bridge for all forms
========================================================
Registers JS-Python bridges for the global notification bell.
Call register_notif_bridges() from any form's __init__ to enable
the notification bell on that page.
"""

import anvil.js
import anvil.server

try:
    from . import auth_helpers
except ImportError:
    import auth_helpers


def _get_token():
    return auth_helpers.get_auth_token()


def _is_admin():
    try:
        role = anvil.js.window.sessionStorage.getItem('user_role')
        return role == 'admin'
    except Exception:
        return False


def _get_all_notifications():
    """Fetch notifications — admin gets ALL, normal user gets own."""
    token = _get_token()
    if not token:
        return {'success': False, 'data': []}
    try:
        if _is_admin():
            res = anvil.server.call('get_all_notifications_admin', token, 50)
        else:
            res = anvil.server.call('get_user_notifications', token, 50, False)

        if not res or not res.get('success'):
            return res or {'success': False, 'data': []}

        # Transform data to UI-friendly format
        lang = 'en'
        try:
            lang = anvil.js.window.localStorage.getItem('hp_language') or 'en'
        except Exception:
            pass

        notifications = []
        for item in (res.get('data') or []):
            payload = item.get('payload') or {}
            msg_key = 'message_ar' if lang == 'ar' else 'message_en'
            # For audit_action, show full detail from action_description (action + table + record)
            notif_type = item.get('type', '')
            if notif_type == 'audit_action':
                description = (payload.get('action_description') or '').strip() or payload.get(msg_key, '') or payload.get('message_en', '') or _type_label(notif_type, payload, lang)
            else:
                description = payload.get(msg_key, '') or payload.get('message_en', '') or _type_label(notif_type, payload, lang)
            ts = (item.get('created_at') or '').replace('T', ' ')[:19]
            notifications.append({
                'id': item.get('id', ''),
                'timestamp': ts,
                'action_description': description,
                'action': notif_type,
                'read_at': item.get('read_at'),
                'user_email': item.get('user_email', ''),
            })
        return {'success': True, 'notifications': notifications}
    except Exception as e:
        return {'success': False, 'data': [], 'message': str(e)}


def _type_label(notif_type, payload, lang):
    """Generate human-readable label from notification type."""
    # audit_action: use stored action_description, or build from action + table + record
    if notif_type == 'audit_action':
        desc = (payload.get('action_description') or '').strip()
        if desc:
            return desc
        action = payload.get('action', '')
        table = payload.get('table_name', '')
        record_id = payload.get('record_id', '')
        parts = [action] if action else []
        if table:
            parts.append(table)
        if record_id:
            parts.append(str(record_id))
        return ' - '.join(parts) if parts else ('Audit action' if lang == 'en' else 'إجراء تدقيق')
    labels = {
        'quotation_saved': ('Quotation saved', 'تم حفظ عرض سعر'),
        'contract_saved': ('Contract saved', 'تم حفظ عقد'),
        'followup_set': ('Follow-up set', 'تم تعيين متابعة'),
        'followup_overdue': ('Follow-up overdue', 'متابعة متأخرة'),
        'user_approved': ('User approved', 'تمت الموافقة على مستخدم'),
        'user_rejected': ('User rejected', 'تم رفض مستخدم'),
        'backup_created': ('Backup created', 'تم إنشاء نسخة احتياطية'),
        'backup_restored': ('Backup restored', 'تمت استعادة نسخة احتياطية'),
    }
    pair = labels.get(notif_type, (notif_type, notif_type))
    base = pair[1] if lang == 'ar' else pair[0]
    qn = payload.get('quotation_number', '')
    if qn:
        base += f' #{qn}'
    return base


def _delete_one_notification(notification_id):
    token = _get_token()
    if not token:
        return {'success': False}
    return anvil.server.call('delete_notification', notification_id, token)


def _delete_all_notifications():
    token = _get_token()
    if not token:
        return {'success': False}
    if _is_admin():
        return anvil.server.call('delete_all_notifications_admin', token)
    return anvil.server.call('delete_all_my_notifications', token)


def _mark_notification_read(notification_id):
    token = _get_token()
    if not token:
        return {'success': False}
    return anvil.server.call('mark_notification_read', notification_id, token)


def _mark_notification_unread(notification_id):
    token = _get_token()
    if not token:
        return {'success': False}
    return anvil.server.call('mark_notification_unread', notification_id, token)


def register_notif_bridges():
    """Register JS bridges and fire event so notification-bell.js can fetch.

    Safe to call multiple times — bridges are re-bound (idempotent) but
    the CustomEvent is only dispatched once per page load to avoid
    redundant notification fetches.
    """
    try:
        anvil.js.window.__hpNotifGetAll = _get_all_notifications
        anvil.js.window.__hpNotifDeleteOne = _delete_one_notification
        anvil.js.window.__hpNotifDeleteAll = _delete_all_notifications
        anvil.js.window.__hpNotifMarkRead = _mark_notification_read
        anvil.js.window.__hpNotifMarkUnread = _mark_notification_unread
        # Only fire the ready event once per page to avoid duplicate fetches
        if not getattr(anvil.js.window, '__hpNotifBridgeReady', False):
            anvil.js.window.__hpNotifBridgeReady = True
            anvil.js.window.dispatchEvent(
                anvil.js.window.CustomEvent.new('hp-notif-bridge-ready')
            )
    except Exception:
        pass

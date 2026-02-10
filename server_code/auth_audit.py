"""
auth_audit.py - سجل التدقيق المفصل
==================================
- تسجيل كل عملية باسم المستخدم (الاسم الكامل) والوصف الدقيق والتوقيت
- دعم user_name و action_description في جدول audit_log
"""

from anvil.tables import app_tables
from datetime import datetime
import json

try:
    from .auth_utils import get_utc_now
except ImportError:
    from auth_utils import get_utc_now
import uuid
import logging

logger = logging.getLogger(__name__)

# تسميات عربية/إنجليزية للأحداث للوصف الواضح
ACTION_LABELS = {
    'LOGIN': 'تسجيل دخول',
    'LOGOUT': 'تسجيل خروج',
    'REGISTER_PENDING': 'طلب تسجيل جديد (بانتظار التحقق)',
    'EMAIL_VERIFIED': 'التحقق من البريد الإلكتروني',
    'ACCOUNT_LOCKED': 'قفل الحساب',
    'CREATE': 'إنشاء',
    'UPDATE': 'تعديل',
    'SOFT_DELETE': 'حذف (ناعم)',
    'RESTORE': 'استعادة',
    'IMPORT': 'استيراد بيانات',
    'APPROVE_USER': 'الموافقة على مستخدم',
    'REJECT_USER': 'رفض مستخدم',
    'UPDATE_ROLE': 'تحديث صلاحية مستخدم',
    'RESET_PASSWORD': 'إعادة تعيين كلمة المرور',
    'CHANGE_PASSWORD': 'تغيير كلمة المرور',
    'PASSWORD_RESET': 'إكمال إعادة تعيين كلمة المرور',
    'SETUP_ADMIN': 'إعداد أدمن',
    'EMERGENCY_ADMIN_UPGRADE': 'ترقية طوارئ لأدمن',
    'EMERGENCY_ADMIN_CREATED': 'إنشاء أدمن طوارئ',
    'FAILED_EMERGENCY_RESET': 'فشل إعادة تعيين طوارئ',
    'CREATE_SETTING': 'إنشاء إعداد',
    'UPDATE_SETTING': 'تحديث إعداد',
    'DELETE_USER_PERMANENTLY': 'حذف مستخدم نهائياً',
    'BACKUP_EXPORT': 'تحميل نسخة احتياطية',
    'BACKUP_SCHEDULED': 'نسخة احتياطية مجدولة',
    'BACKUP_RESTORE': 'استعادة نسخة احتياطية',
    'UPDATE_PAYMENT_STATUS': 'تحديث حالة دفعة',
    'ADD_CLIENT_NOTE': 'إضافة ملاحظة عميل',
    'DELETE_CLIENT_NOTE': 'حذف ملاحظة عميل',
    'UPDATE_CLIENT_TAGS': 'تحديث وسوم عميل',
    'SET_FOLLOWUP': 'تعيين متابعة عرض سعر',
    'SNOOZE_FOLLOWUP': 'تأجيل متابعة',
    'COMPLETE_FOLLOWUP': 'إتمام متابعة',
}

TABLE_LABELS = {
    'users': 'المستخدمين',
    'clients': 'العملاء',
    'quotations': 'العروض السعرية',
    'contracts': 'العقود',
    'settings': 'الإعدادات',
    'backup': 'النسخ الاحتياطي',
}


def get_user_name_for_audit(user_email):
    """جلب الاسم الكامل للمستخدم من البريد (للعرض في سجل التدقيق)."""
    if not user_email or not str(user_email).strip():
        return None
    try:
        user = app_tables.users.get(email=str(user_email).strip().lower())
        if user and user.get('full_name'):
            return str(user['full_name']).strip()
        return str(user_email).strip()
    except Exception:
        return str(user_email).strip() if user_email else None


def build_action_description(action, table_name, record_id, custom=None):
    """بناء وصف مقروء للعملية: من فعل + الجدول + المعرف."""
    if custom:
        return str(custom)[:500]  # حد معقول للطول
    action_ar = ACTION_LABELS.get(action, action)
    table_ar = TABLE_LABELS.get(table_name, table_name or '')
    parts = [action_ar]
    if table_ar:
        parts.append(table_ar)
    if record_id is not None and str(record_id).strip():
        parts.append(str(record_id))
    return ' - '.join(parts) if parts else action or '—'


def log_audit(action, table_name, record_id, old_data, new_data,
              user_email=None, ip_address=None, user_name=None, action_description=None):
    """
    تسجيل العملية في سجل التدقيق مع الاسم الكامل ووصف واضح وتوقيت دقيق.

    - user_name: الاسم الكامل للمستخدم (إن لم يُمرَّر يُستخرج من user_email إن وُجد).
    - action_description: وصف مقروء للعملية (إن لم يُمرَّر يُبنى تلقائياً من action/table/record).
    """
    try:
        if user_name is None and user_email:
            user_name = get_user_name_for_audit(user_email)
        if not user_name and user_email:
            user_name = str(user_email).strip()
        # لا نعرض كلمة "system" — من نفّذ الإجراء اسمه يظهر؛ إن لم يُعرف نعرض "—"
        if not user_name or (user_name and str(user_name).strip().lower() == 'system'):
            user_name = "—"

        desc = build_action_description(action, table_name, record_id, action_description)

        row_data = {
            'log_id': str(uuid.uuid4()),
            'timestamp': get_utc_now(),
            'user_email': (user_email or '').strip() or '',
            'action': action or '',
            'table_name': table_name or '',
            'record_id': str(record_id)[:100] if record_id else None,
            'old_data': json.dumps(old_data, default=str, ensure_ascii=False)[:10000] if old_data else None,
            'new_data': json.dumps(new_data, default=str, ensure_ascii=False)[:10000] if new_data else None,
            'ip_address': (ip_address or 'unknown').strip()[:100],
        }
        try:
            row_data['user_name'] = (user_name or "—").strip()[:200]
            row_data['action_description'] = (desc or '').strip()[:500]
        except Exception as e:
            logger.warning("Could not set user_name/action_description in audit: %s", e)
        try:
            app_tables.audit_log.add_row(**row_data)
        except Exception as col_err:
            if 'user_name' in str(col_err) or 'action_description' in str(col_err):
                row_data.pop('user_name', None)
                row_data.pop('action_description', None)
                app_tables.audit_log.add_row(**row_data)
            else:
                raise
        # إشعار لكل الأدمن عند أي إجراء (ولو طفيف)
        try:
            from . import notifications as notif_mod
            notif_mod.create_notification_for_all_admins('audit_action', {
                'action_description': desc,
                'action': action,
                'table_name': table_name or '',
                'record_id': str(record_id)[:100] if record_id else None,
                'user_name': row_data.get('user_name', '—')
            })
        except Exception as notif_e:
            logger.debug("Notify admins after audit: %s", notif_e)
    except Exception as e:
        logger.error("Audit log error: %s", e)

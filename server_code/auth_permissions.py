"""
auth_permissions.py - التحقق من الصلاحيات (أدوار، أدمن، صلاحيات مخصصة)
يُستورد من AuthManager ويُستخدم من QuotationManager أيضاً.
"""

import json
import logging
import anvil.server
from anvil.tables import app_tables

# استيراد يعمل داخل الحزمة (.) أو كوحدة مستقلة في Anvil
try:
    from .auth_constants import ROLES
    from .auth_sessions import validate_session
except ImportError:
    from auth_constants import ROLES
    from auth_sessions import validate_session

logger = logging.getLogger(__name__)


@anvil.server.callable
def check_permission(token, action):
    """
    التحقق من صلاحية المستخدم لإجراء معين.
    """
    session = validate_session(token)
    if not session:
        return False
    role = session.get('role', '')
    role_permissions = ROLES.get(role, [])
    if 'all' in role_permissions:
        return True
    if action in role_permissions:
        return True
    user = app_tables.users.get(email=session['email'])
    if user and user.get('custom_permissions'):
        try:
            custom = json.loads(user['custom_permissions'])
            if action in custom:
                return True
        except (json.JSONDecodeError, TypeError):
            pass
    return False


def is_admin_by_email(email):
    """التحقق من أن المستخدم أدمن بالبريد الإلكتروني."""
    if not email:
        return False
    user = app_tables.users.get(email=email.lower())
    if not user:
        return False
    return user['role'] == 'admin' and user['is_active'] and user['is_approved']


@anvil.server.callable
def is_admin(token):
    """التحقق من أن المستخدم أدمن (توكن جلسة صالح فقط)."""
    if not token:
        return False
    session = validate_session(token)
    if not session:
        return False
    return (session.get('role') or '').strip().lower() == 'admin'


def require_admin(token):
    """
    التحقق من صلاحية الأدمن. يُرجع (is_admin: bool, error_dict أو None).
    ملاحظة أمنية: يقبل توكن جلسة صالح فقط (لا يقبل email أو user_id).
    """
    if not token:
        return False, {'success': False, 'message': 'Admin access required'}
    if is_admin(token):
        return True, None
    return False, {'success': False, 'message': 'Admin access required'}


def require_permission(token, permission):
    """التحقق من صلاحية معينة. يُرجع (allowed: bool, error_dict أو None)."""
    if not check_permission(token, permission):
        return False, {'success': False, 'message': f'Permission denied: {permission}'}
    return True, None


# =========================================================
# Centralized permission functions — الدوال الموحدة (token-only)
# تُستخدم من كل server modules بدلاً من التعريفات المحلية المكررة
# =========================================================

def require_authenticated(token):
    """
    التحقق من صلاحية الجلسة (token فقط).
    يُرجع: (is_valid: bool, user_email: str, error_dict أو None)
    """
    if not token:
        return False, None, {'success': False, 'message': 'Authentication required'}
    session = validate_session(token)
    if not session:
        return False, None, {'success': False, 'message': 'Invalid or expired session'}
    return True, session.get('email', 'unknown'), None


def require_permission_full(token, permission):
    """
    التحقق من صلاحية معينة مع بيانات المستخدم (token-only).
    يُرجع: (is_valid: bool, user_email: str, error_dict أو None)
    ملاحظة: لا يستخدم is_admin_by_email — فقط token-based checks.
    """
    is_valid, user_email, error = require_authenticated(token)
    if not is_valid:
        return False, None, error
    if is_admin(token):
        return True, user_email, None
    if check_permission(token, permission):
        return True, user_email, None
    return False, user_email, {'success': False, 'message': f'Permission denied: {permission} access required'}

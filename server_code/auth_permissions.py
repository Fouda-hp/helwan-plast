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
def is_admin(token_or_email):
    """التحقق من أن المستخدم أدمن (توكن أو بريد)."""
    if not token_or_email:
        return False
    if '@' in str(token_or_email):
        return is_admin_by_email(token_or_email)
    session = validate_session(token_or_email)
    if session and session.get('role') == 'admin':
        return True
    return False


def require_admin(token_or_email):
    """
    التحقق من صلاحية الأدمن. يُرجع (is_admin: bool, error_dict أو None).
    """
    if not token_or_email:
        return False, {'success': False, 'message': 'Admin access required'}
    if is_admin(token_or_email):
        return True, None
    session = validate_session(token_or_email)
    if session and session.get('email') and is_admin_by_email(session['email']):
        return True, None
    try:
        user_by_id = app_tables.users.get(user_id=token_or_email)
        if user_by_id and user_by_id['role'] == 'admin' and user_by_id['is_active'] and user_by_id['is_approved']:
            return True, None
    except Exception:
        pass
    return False, {'success': False, 'message': 'Admin access required'}


def require_permission(token, permission):
    """التحقق من صلاحية معينة. يُرجع (allowed: bool, error_dict أو None)."""
    if not check_permission(token, permission):
        return False, {'success': False, 'message': f'Permission denied: {permission}'}
    return True, None

"""
shared_utils.py - دوال مشتركة لتجنب تكرار الكود
=================================================
يجمع الدوال المساعدة المتكررة في عدة modules:
- get_client_ip_safe: جلب IP العميل مع معالجة الأخطاء
- log_audit_safe: تسجيل التدقيق مع معالجة الأخطاء
- parse_date: تحويل تاريخ ISO لكائن date
- to_datetime: تحويل أي قيمة تاريخ/وقت لـ datetime
- parse_json_field: تحويل JSON string من قاعدة البيانات
- contracts_search_active: البحث في العقود مع استبعاد المحذوفة
- contracts_get_active: جلب عقد واحد مع استبعاد المحذوف
"""

import json
import logging
from datetime import datetime, date

from anvil.tables import app_tables

try:
    from .auth_utils import get_utc_now
except ImportError:
    from auth_utils import get_utc_now

logger = logging.getLogger(__name__)


# =========================================================
# IP & Audit Helpers
# =========================================================

def get_client_ip_safe():
    """جلب IP العميل مع معالجة الأخطاء. يُرجع 'unknown' في حالة الفشل."""
    try:
        try:
            from . import AuthManager
        except ImportError:
            import AuthManager
        return AuthManager.get_client_ip()
    except Exception:
        return 'unknown'


def log_audit_safe(action, table_name, record_id, old_data, new_data,
                   user_email='system', ip_address=None):
    """تسجيل التدقيق مع معالجة الأخطاء. لا يرفع استثناء أبداً."""
    try:
        try:
            from . import AuthManager
        except ImportError:
            import AuthManager
        AuthManager.log_audit(action, table_name, record_id,
                              old_data, new_data, user_email, ip_address)
    except Exception as e:
        logger.warning("Audit log error in shared_utils: %s", e)


# =========================================================
# Date / Time Helpers
# =========================================================

def parse_date(date_str):
    """Parse ISO date string to date object. Returns None on failure."""
    if not date_str or not str(date_str).strip():
        return None
    try:
        parts = str(date_str).strip().split('T')[0].split('-')
        if len(parts) >= 3:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        pass
    return None


def to_datetime(val):
    """
    Convert date/datetime/str to naive datetime for safe comparison.
    Always strips timezone info to prevent offset-naive vs offset-aware errors.
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.replace(tzinfo=None)
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day)
    try:
        dt = datetime.fromisoformat(str(val).replace('Z', '+00:00'))
        return dt.replace(tzinfo=None)
    except Exception:
        return None


# =========================================================
# JSON Helpers
# =========================================================

def parse_json_field(row, field_name):
    """Parse a JSON string field from a DB row. Returns [] or '' on failure."""
    try:
        val = row.get(field_name)
        if val and isinstance(val, str) and val.strip():
            return json.loads(val)
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return [] if field_name.endswith('_json') else ''


# =========================================================
# Contract Search Helper (shared by 3+ modules)
# =========================================================

_contracts_has_is_deleted = None


def _ensure_contracts_column_check():
    """Check once whether contracts table has is_deleted column."""
    global _contracts_has_is_deleted
    if _contracts_has_is_deleted is None:
        try:
            cols = [col['name'] for col in app_tables.contracts.list_columns()]
            _contracts_has_is_deleted = 'is_deleted' in cols
        except Exception:
            _contracts_has_is_deleted = False


def contracts_search_active(**kwargs):
    """البحث في جدول العقود مع استبعاد is_deleted=True تلقائياً."""
    _ensure_contracts_column_check()
    if _contracts_has_is_deleted:
        kwargs['is_deleted'] = False
    return app_tables.contracts.search(**kwargs)


def contracts_get_active(**kwargs):
    """جلب عقد واحد مع استبعاد المحذوف — بديل آمن لـ app_tables.contracts.get()."""
    _ensure_contracts_column_check()
    if _contracts_has_is_deleted:
        kwargs['is_deleted'] = False
    return app_tables.contracts.get(**kwargs)


# =========================================================
# Standardized Response Helpers
# =========================================================

def success_response(data=None, message=None):
    """Build a standardized success response dict."""
    resp = {'success': True}
    if message:
        resp['message'] = message
    if data is not None:
        resp['data'] = data
    return resp


def error_response(message, code=None):
    """Build a standardized error response dict."""
    resp = {'success': False, 'message': str(message)}
    if code:
        resp['code'] = code
    return resp


# Generic error messages — never expose internal details to client
_GENERIC_ERRORS = {
    'default': 'An error occurred. Please try again later.',
    'save': 'Failed to save data. Please try again.',
    'delete': 'Failed to delete record. Please try again.',
    'load': 'Failed to load data. Please try again.',
    'export': 'Failed to export data. Please try again.',
    'auth': 'Authentication error. Please log in again.',
    'permission': 'Permission denied.',
    'not_found': 'Record not found.',
    'import': 'Failed to import data. Please check the file format.',
}


def safe_error(e, logger_ref=None, context='default', log_msg=None):
    """
    Log the real exception but return a generic safe message to the client.
    Usage:  return safe_error(e, logger, 'save', 'save_quotation failed')
    """
    msg = _GENERIC_ERRORS.get(context, _GENERIC_ERRORS['default'])
    if logger_ref:
        logger_ref.exception(log_msg or "Error [%s]: %s", context, e)
    return {'success': False, 'message': msg}


# =========================================================
# Bounded Table Search (防止 full table scans)
# =========================================================

# Default max rows to load from a single table scan
MAX_TABLE_ROWS = 10000


def bounded_search(table, max_rows=MAX_TABLE_ROWS, **filters):
    """
    Search a table with a safety limit to prevent unbounded full-table scans.
    Returns a list (not a lazy iterator) capped at max_rows.
    Usage: rows = bounded_search(app_tables.users, max_rows=500, is_active=True)
    """
    results = table.search(**filters)
    rows = []
    for i, row in enumerate(results):
        if i >= max_rows:
            logger.warning(
                "bounded_search: hit %d row limit on table search (filters=%s)",
                max_rows, list(filters.keys())
            )
            break
        rows.append(row)
    return rows


def bounded_count(table, max_count=MAX_TABLE_ROWS, **filters):
    """
    Count rows in a table with a safety cap.
    More efficient than len(table.search()) for large tables.
    Returns min(actual_count, max_count).
    """
    try:
        results = table.search(**filters)
        return min(len(results), max_count)
    except Exception:
        return -1


# =========================================================
# Safe numeric conversion
# =========================================================

def safe_float(val, default=0.0):
    """Convert a value to float safely, returning default on failure."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_int(val, default=0):
    """Convert a value to int safely, returning default on failure."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

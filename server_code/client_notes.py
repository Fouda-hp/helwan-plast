"""
client_notes.py - ملاحظات ووسوم العملاء
========================================
- إضافة/حذف ملاحظات مرتبطة بالعميل (JSON في عمود notes_json)
- إدارة الوسوم/العلامات (JSON في عمود tags_json)
- تدقيق كامل لكل عملية
"""

import anvil.server
from anvil.tables import app_tables
import json
import uuid
import logging

try:
    from .auth_utils import get_utc_now
except ImportError:
    from auth_utils import get_utc_now

try:
    from . import AuthManager
except ImportError:
    import AuthManager

try:
    from . import notifications as notifications_module
except ImportError:
    import notifications as notifications_module

logger = logging.getLogger(__name__)

# =========================================================
# Centralized permission helpers (من auth_permissions.py)
# =========================================================
try:
    from .auth_permissions import require_authenticated as _require_authenticated
    from .auth_permissions import require_permission_full as _require_permission
except ImportError:
    from auth_permissions import require_authenticated as _require_authenticated
    from auth_permissions import require_permission_full as _require_permission


# Use shared helpers to avoid code duplication
try:
    from .shared_utils import get_client_ip_safe as _get_client_ip
    from .shared_utils import log_audit_safe as _log_audit
except ImportError:
    from shared_utils import get_client_ip_safe as _get_client_ip
    from shared_utils import log_audit_safe as _log_audit


def _get_user_name(user_email):
    try:
        user = app_tables.users.get(email=str(user_email).strip().lower())
        if user and user.get('full_name'):
            return str(user['full_name']).strip()
    except Exception as _e:
        logger.debug("Suppressed: %s", _e)
    return str(user_email).split('@')[0] if user_email else 'Unknown'


def _parse_json_field(row, field_name):
    """Parse a JSON string field from a row, returning default empty structure."""
    try:
        val = row.get(field_name)
        if val and isinstance(val, str) and val.strip():
            return json.loads(val)
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass
    return [] if field_name.endswith('_json') else ''


# =========================================================
# Notes CRUD
# =========================================================
@anvil.server.callable
def add_client_note(client_code, text, token_or_email=None):
    """إضافة ملاحظة لعميل"""
    is_valid, user_email, error = _require_permission(token_or_email, 'edit')
    if not is_valid:
        return error

    if not client_code or not str(client_code).strip():
        return {'success': False, 'message': 'Client code required'}
    if not text or not str(text).strip():
        return {'success': False, 'message': 'Note text required'}

    client_code = str(client_code).strip()
    text = str(text).strip()[:2000]  # limit note length

    try:
        row = app_tables.clients.get(**{'Client Code': client_code})
        if not row:
            return {'success': False, 'message': 'Client not found'}

        notes = _parse_json_field(row, 'notes_json')
        if not isinstance(notes, list):
            notes = []

        author_name = _get_user_name(user_email)
        note = {
            'id': str(uuid.uuid4()),
            'text': text,
            'author_email': user_email,
            'author_name': author_name,
            'created_at': get_utc_now().isoformat()
        }
        notes.insert(0, note)  # newest first

        row.update(
            notes_json=json.dumps(notes, ensure_ascii=False, default=str),
            updated_by=user_email,
            updated_at=get_utc_now()
        )

        _log_audit('ADD_CLIENT_NOTE', 'clients', client_code, None,
                    {'note_id': note['id'], 'text': text[:100]},
                    user_email, _get_client_ip())

        return {'success': True, 'note': note}

    except Exception as e:
        logger.exception("add_client_note error: %s", e)
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def delete_client_note(client_code, note_id, token_or_email=None):
    """حذف ملاحظة من عميل"""
    is_valid, user_email, error = _require_permission(token_or_email, 'edit')
    if not is_valid:
        return error

    client_code = str(client_code).strip()
    note_id = str(note_id).strip()

    try:
        row = app_tables.clients.get(**{'Client Code': client_code})
        if not row:
            return {'success': False, 'message': 'Client not found'}

        notes = _parse_json_field(row, 'notes_json')
        if not isinstance(notes, list):
            return {'success': False, 'message': 'No notes found'}

        old_notes = list(notes)

        # Find the note to check ownership
        target_note = None
        for n in notes:
            if n.get('id') == note_id:
                target_note = n
                break

        if not target_note:
            return {'success': False, 'message': 'Note not found'}

        # Only author or admin can delete
        is_admin = AuthManager.is_admin(token_or_email)
        if not is_admin and target_note.get('author_email') != user_email:
            return {'success': False, 'message': 'You can only delete your own notes'}

        notes = [n for n in notes if n.get('id') != note_id]

        row.update(
            notes_json=json.dumps(notes, ensure_ascii=False, default=str),
            updated_by=user_email,
            updated_at=get_utc_now()
        )

        _log_audit('DELETE_CLIENT_NOTE', 'clients', client_code,
                    {'note_id': note_id}, None,
                    user_email, _get_client_ip())

        return {'success': True}

    except Exception as e:
        logger.exception("delete_client_note error: %s", e)
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_client_notes(client_code, token_or_email=None):
    """جلب ملاحظات العميل"""
    is_valid, user_email, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error

    try:
        row = app_tables.clients.get(**{'Client Code': str(client_code).strip()})
        if not row:
            return {'success': False, 'message': 'Client not found', 'notes': []}

        notes = _parse_json_field(row, 'notes_json')
        if not isinstance(notes, list):
            notes = []

        return {'success': True, 'notes': notes}

    except Exception as e:
        logger.exception("get_client_notes error: %s", e)
        return {'success': False, 'message': str(e), 'notes': []}


# =========================================================
# Tags CRUD
# =========================================================
@anvil.server.callable
def set_client_tags(client_code, tags, token_or_email=None):
    """تعيين وسوم العميل (استبدال كامل)"""
    is_valid, user_email, error = _require_permission(token_or_email, 'edit')
    if not is_valid:
        return error

    client_code = str(client_code).strip()

    try:
        row = app_tables.clients.get(**{'Client Code': client_code})
        if not row:
            return {'success': False, 'message': 'Client not found'}

        # Validate and clean tags
        if not isinstance(tags, (list, tuple)):
            tags = []
        clean_tags = []
        for t in tags:
            t_str = str(t).strip()
            if t_str and len(t_str) <= 50 and t_str not in clean_tags:
                clean_tags.append(t_str)
        clean_tags = clean_tags[:20]  # max 20 tags per client

        old_tags = _parse_json_field(row, 'tags_json')

        row.update(
            tags_json=json.dumps(clean_tags, ensure_ascii=False),
            updated_by=user_email,
            updated_at=get_utc_now()
        )

        _log_audit('UPDATE_CLIENT_TAGS', 'clients', client_code,
                    {'tags': old_tags}, {'tags': clean_tags},
                    user_email, _get_client_ip())

        # Invalidate tags cache so get_all_tags picks up the change
        _tags_cache_mgr.invalidate('all_tags')

        return {'success': True, 'tags': clean_tags}

    except Exception as e:
        logger.exception("set_client_tags error: %s", e)
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


try:
    from .cache_manager import tags_cache as _tags_cache_mgr
except ImportError:
    from cache_manager import tags_cache as _tags_cache_mgr

@anvil.server.callable
def get_all_tags(token_or_email=None):
    """جلب كل الوسوم المستخدمة عبر كل العملاء (cached 30s via TTLCache)"""
    is_valid, user_email, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error

    cached = _tags_cache_mgr.get('all_tags')
    if cached is not None:
        return cached

    try:
        all_tags = set()
        for row in app_tables.clients.search(is_deleted=False):
            tags = _parse_json_field(row, 'tags_json')
            if isinstance(tags, list):
                for t in tags:
                    if t and str(t).strip():
                        all_tags.add(str(t).strip())

        result = {'success': True, 'tags': sorted(list(all_tags))}
        _tags_cache_mgr.set('all_tags', result)
        return result

    except Exception as e:
        logger.exception("get_all_tags error: %s", e)
        return {'success': False, 'message': str(e), 'tags': []}


@anvil.server.callable
def get_client_with_notes_and_tags(client_code, token_or_email=None):
    """جلب بيانات العميل مع الملاحظات والوسوم"""
    is_valid, user_email, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error

    try:
        row = app_tables.clients.get(**{'Client Code': str(client_code).strip()})
        if not row:
            return {'success': False, 'message': 'Client not found'}

        notes = _parse_json_field(row, 'notes_json')
        if not isinstance(notes, list):
            notes = []

        tags = _parse_json_field(row, 'tags_json')
        if not isinstance(tags, list):
            tags = []

        client_data = {
            'client_code': row['Client Code'],
            'client_name': row.get('Client Name', ''),
            'company': row.get('Company', ''),
            'phone': row.get('Phone', ''),
            'country': row.get('Country', ''),
            'address': row.get('Address', ''),
            'email': row.get('Email', ''),
            'sales_rep': row.get('Sales Rep', ''),
            'source': row.get('Source', ''),
            'date': row.get('Date').isoformat() if row.get('Date') else None,
            'notes': notes,
            'tags': tags,
        }

        return {'success': True, 'client': client_data}

    except Exception as e:
        logger.exception("get_client_with_notes_and_tags error: %s", e)
        return {'success': False, 'message': 'An error occurred. Please try again later.'}

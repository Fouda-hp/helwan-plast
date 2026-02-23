"""
accounting_suppliers.py - Suppliers & Service Suppliers CRUD
============================================================
Extracted from accounting.py for better maintainability.
- Suppliers: Material suppliers (raw materials, machines)
- Service Suppliers: Shipping, transport, customs clearance, insurance
"""

import anvil.server
from anvil.tables import app_tables
import uuid
import logging

try:
    from .auth_utils import get_utc_now
except ImportError:
    from auth_utils import get_utc_now

try:
    from .auth_permissions import require_permission_full as _require_permission
except ImportError:
    from auth_permissions import require_permission_full as _require_permission

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utility helpers (duplicated from accounting.py to avoid circular imports)
# ---------------------------------------------------------------------------
def _uuid():
    return str(uuid.uuid4())


def _safe_str(val, default=''):
    if val is None:
        return default
    return str(val).strip()


def _row_to_dict(row, columns):
    """Convert an Anvil table row to a plain dict with the given column names."""
    from datetime import datetime, date
    d = {}
    for col in columns:
        try:
            val = row.get(col)
        except Exception:
            val = None
        if isinstance(val, (datetime, date)):
            d[col] = val.isoformat()
        else:
            d[col] = val
    return d


# ===========================================================================
# SUPPLIERS CRUD
# ===========================================================================
SUPPLIER_COLS = [
    'id', 'name', 'company', 'phone', 'email', 'country',
    'address', 'tax_id', 'notes', 'is_active', 'created_at', 'updated_at',
]


@anvil.server.callable
def get_suppliers(search='', token_or_email=None):
    """Return list of active suppliers, optionally filtered by search term."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        import anvil.tables.query as q
        base_query = {'is_active': True}
        search_query = None
        search_lower = _safe_str(search).strip().lower()

        if search_lower:
             search_query = q.any_of(
                name=q.ilike(f"%{search_lower}%"),
                company=q.ilike(f"%{search_lower}%"),
                phone=q.ilike(f"%{search_lower}%"),
                email=q.ilike(f"%{search_lower}%"),
                country=q.ilike(f"%{search_lower}%")
             )

        if search_query:
            rows = app_tables.suppliers.search(search_query, **base_query)
        else:
            rows = app_tables.suppliers.search(**base_query)

        results = []
        for r in rows:
            results.append(_row_to_dict(r, SUPPLIER_COLS))

        results.sort(key=lambda s: s.get('name', ''))
        return {'success': True, 'data': results, 'count': len(results)}
    except Exception as e:
        logger.exception("get_suppliers error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def add_supplier(data, token_or_email=None):
    """Create a new supplier."""
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    name = _safe_str(data.get('name'))
    if not name:
        return {'success': False, 'message': 'Supplier name is required'}
    now = get_utc_now()
    sid = _uuid()
    try:
        app_tables.suppliers.add_row(
            id=sid,
            name=name,
            company=_safe_str(data.get('company')),
            phone=_safe_str(data.get('phone')),
            email=_safe_str(data.get('email')),
            country=_safe_str(data.get('country')),
            address=_safe_str(data.get('address')),
            tax_id=_safe_str(data.get('tax_id')),
            notes=_safe_str(data.get('notes')),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        logger.info("Supplier %s created by %s", sid, user_email)
        return {'success': True, 'id': sid}
    except Exception as e:
        logger.exception("add_supplier error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def update_supplier(supplier_id, data, token_or_email=None):
    """Update an existing supplier."""
    is_valid, user_email, error = _require_permission(token_or_email, 'edit')
    if not is_valid:
        return error
    try:
        row = app_tables.suppliers.get(id=supplier_id)
        if not row:
            return {'success': False, 'message': 'Supplier not found'}
        updates = {}
        for field in ['name', 'company', 'phone', 'email', 'country', 'address', 'tax_id', 'notes']:
            if field in data:
                updates[field] = _safe_str(data[field])
        updates['updated_at'] = get_utc_now()
        row.update(**updates)
        logger.info("Supplier %s updated by %s", supplier_id, user_email)
        return {'success': True}
    except Exception as e:
        logger.exception("update_supplier error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def delete_supplier(supplier_id, token_or_email=None):
    """Soft-delete a supplier (set is_active=False)."""
    is_valid, user_email, error = _require_permission(token_or_email, 'delete')
    if not is_valid:
        return error
    try:
        row = app_tables.suppliers.get(id=supplier_id)
        if not row:
            return {'success': False, 'message': 'Supplier not found'}
        row.update(is_active=False, updated_at=get_utc_now())
        logger.info("Supplier %s soft-deleted by %s", supplier_id, user_email)
        return {'success': True}
    except Exception as e:
        logger.exception("delete_supplier error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_suppliers_list_simple(token_or_email=None):
    """Return simple list of active suppliers for dropdown/selection."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        suppliers = []
        for r in app_tables.suppliers.search(is_active=True):
            suppliers.append({
                'id': r.get('id', ''),
                'name': _safe_str(r.get('name', '')),
                'company': _safe_str(r.get('company', '')),
            })
        return {'success': True, 'data': suppliers}
    except Exception as e:
        logger.exception("get_suppliers_list_simple error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


# ===========================================================================
# SERVICE SUPPLIERS (موردين الخدمات - شحن، نقل، تخليص جمركي)
# ===========================================================================
SERVICE_SUPPLIER_COLS = [
    'id', 'name', 'company', 'phone', 'email', 'country',
    'address', 'tax_id', 'notes', 'service_type', 'is_active', 'created_at', 'updated_at',
]

VALID_SERVICE_TYPES = ('shipping', 'transport', 'customs_clearance', 'insurance', 'other')


@anvil.server.callable
def get_service_suppliers(search='', service_type=None, token_or_email=None):
    """Return list of active service suppliers, optionally filtered by search term and/or service_type."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        try:
            base_query = {'is_active': True}
            if service_type and service_type in VALID_SERVICE_TYPES:
                base_query['service_type'] = service_type
            rows = list(app_tables.service_suppliers.search(**base_query))
        except Exception:
            try:
                rows = list(app_tables.service_suppliers.search())
            except Exception:
                rows = []

        search_lower = _safe_str(search).strip().lower()
        results = []
        for r in rows:
            d = _row_to_dict(r, SERVICE_SUPPLIER_COLS)
            if search_lower:
                haystack = ' '.join([
                    _safe_str(d.get('name', '')),
                    _safe_str(d.get('company', '')),
                    _safe_str(d.get('phone', '')),
                    _safe_str(d.get('email', '')),
                    _safe_str(d.get('country', '')),
                ]).lower()
                if search_lower not in haystack:
                    continue
            results.append(d)
        results.sort(key=lambda s: s.get('name', ''))
        return {'success': True, 'data': results, 'count': len(results)}
    except Exception as e:
        logger.exception("get_service_suppliers error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def add_service_supplier(data, token_or_email=None):
    """Create a new service supplier."""
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    name = _safe_str(data.get('name'))
    if not name:
        return {'success': False, 'message': 'Supplier name is required'}
    stype = _safe_str(data.get('service_type', 'other')).lower()
    if stype not in VALID_SERVICE_TYPES:
        stype = 'other'
    now = get_utc_now()
    sid = _uuid()
    try:
        app_tables.service_suppliers.add_row(
            id=sid,
            name=name,
            company=_safe_str(data.get('company')),
            phone=_safe_str(data.get('phone')),
            email=_safe_str(data.get('email')),
            country=_safe_str(data.get('country')),
            address=_safe_str(data.get('address')),
            tax_id=_safe_str(data.get('tax_id')),
            notes=_safe_str(data.get('notes')),
            service_type=stype,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        logger.info("Service supplier %s (%s) created by %s", sid, stype, user_email)
        return {'success': True, 'id': sid}
    except Exception as e:
        logger.exception("add_service_supplier error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def update_service_supplier(supplier_id, data, token_or_email=None):
    """Update an existing service supplier."""
    is_valid, user_email, error = _require_permission(token_or_email, 'edit')
    if not is_valid:
        return error
    try:
        row = app_tables.service_suppliers.get(id=supplier_id)
        if not row:
            return {'success': False, 'message': 'Service supplier not found'}
        updates = {}
        for field in ['name', 'company', 'phone', 'email', 'country', 'address', 'tax_id', 'notes']:
            if field in data:
                updates[field] = _safe_str(data[field])
        if 'service_type' in data:
            stype = _safe_str(data['service_type']).lower()
            updates['service_type'] = stype if stype in VALID_SERVICE_TYPES else 'other'
        updates['updated_at'] = get_utc_now()
        row.update(**updates)
        logger.info("Service supplier %s updated by %s", supplier_id, user_email)
        return {'success': True}
    except Exception as e:
        logger.exception("update_service_supplier error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def delete_service_supplier(supplier_id, token_or_email=None):
    """Soft-delete a service supplier (set is_active=False)."""
    is_valid, user_email, error = _require_permission(token_or_email, 'delete')
    if not is_valid:
        return error
    try:
        row = app_tables.service_suppliers.get(id=supplier_id)
        if not row:
            return {'success': False, 'message': 'Service supplier not found'}
        row.update(is_active=False, updated_at=get_utc_now())
        logger.info("Service supplier %s soft-deleted by %s", supplier_id, user_email)
        return {'success': True}
    except Exception as e:
        logger.exception("delete_service_supplier error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_service_suppliers_list_simple(token_or_email=None):
    """Return a simple list of active service suppliers for dropdowns (id, name, service_type)."""
    is_valid, _, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        rows = app_tables.service_suppliers.search(is_active=True)
        result = []
        for r in rows:
            result.append({
                'id': r.get('id', ''),
                'name': r.get('name', ''),
                'service_type': r.get('service_type', ''),
            })
        return {'success': True, 'data': result}
    except Exception as e:
        logger.exception("get_service_suppliers_list_simple error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}

"""
client_timeline.py - التايم لاين الشامل للعميل
================================================
- تجميع كل الأحداث (عروض، عقود، مدفوعات، ملاحظات) في تايم لاين واحد
- عرض إحصائيات ملخصة للعميل
"""

import anvil.server
from anvil.tables import app_tables
import anvil.tables.query as q
import json
import logging
from datetime import datetime, date

try:
    from .auth_utils import get_utc_now
except ImportError:
    from auth_utils import get_utc_now

try:
    from . import AuthManager
except ImportError:
    import AuthManager

# Centralized permission helpers (من auth_permissions.py)
try:
    from .auth_permissions import require_permission_full as _require_permission
except ImportError:
    from auth_permissions import require_permission_full as _require_permission

logger = logging.getLogger(__name__)

# Helper: البحث في العقود مع استبعاد المحذوفة (soft delete)
_contracts_has_is_deleted = None

def _contracts_search_active(**kwargs):
    """البحث في جدول العقود مع استبعاد is_deleted=True تلقائياً."""
    global _contracts_has_is_deleted
    if _contracts_has_is_deleted is None:
        try:
            cols = [col['name'] for col in app_tables.contracts.list_columns()]
            _contracts_has_is_deleted = 'is_deleted' in cols
        except Exception:
            _contracts_has_is_deleted = False
    if _contracts_has_is_deleted:
        kwargs['is_deleted'] = False
    return app_tables.contracts.search(**kwargs)


def _safe_isoformat(val):
    """Convert date/datetime to ISO string safely."""
    if val is None:
        return None
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    return str(val)


def _parse_json(val):
    """Parse JSON string, return empty list on failure."""
    if not val or not isinstance(val, str):
        return []
    try:
        result = json.loads(val)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _to_datetime(val):
    """Convert date/datetime to naive datetime for safe comparison.

    Always strips timezone info so all values are offset-naive,
    preventing 'can't compare offset-naive and offset-aware' errors.
    """
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.replace(tzinfo=None)
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day)
    # Try parsing string
    try:
        dt = datetime.fromisoformat(str(val).replace('Z', '+00:00'))
        return dt.replace(tzinfo=None)
    except Exception:
        return None


def _date_only(val):
    """Return date string (YYYY-MM-DD) from any date/datetime value."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime('%Y-%m-%d')
    if isinstance(val, date):
        return val.isoformat()
    s = str(val)
    # Strip time portion if present (e.g. "2026-02-07T00:00:00")
    if 'T' in s:
        return s.split('T')[0]
    return s[:10] if len(s) >= 10 else s


def _parse_price(val):
    """Parse a price value that may be string with commas."""
    if val is None or val == '':
        return 0.0
    try:
        if isinstance(val, (int, float)):
            return float(val)
        s = str(val).replace(',', '').replace('،', '').strip()
        return float(s) if s else 0.0
    except (TypeError, ValueError):
        return 0.0


@anvil.server.callable
def get_client_detail(client_code, token_or_email=None):
    """جلب بيانات العميل مع إحصائيات ملخصة"""
    is_valid, user_email, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error

    try:
        client_code = str(client_code).strip()
        row = app_tables.clients.get(**{'Client Code': client_code})
        if not row:
            return {'success': False, 'message': 'Client not found'}

        # Basic client data
        client = {
            'client_code': row['Client Code'],
            'client_name': row.get('Client Name', ''),
            'company': row.get('Company', ''),
            'phone': row.get('Phone', ''),
            'country': row.get('Country', ''),
            'address': row.get('Address', ''),
            'email': row.get('Email', ''),
            'sales_rep': row.get('Sales Rep', ''),
            'source': row.get('Source', ''),
            'date': _safe_isoformat(row.get('Date')),
            'notes': _parse_json(row.get('notes_json')),
            'tags': _parse_json(row.get('tags_json')),
        }

        # Quotation stats
        quotations = list(app_tables.quotations.search(**{'Client Code': client_code, 'is_deleted': False}))
        total_quotations = len(quotations)
        total_value = 0
        q_numbers = []
        last_activity = _to_datetime(row.get('Date'))

        for quot in quotations:
            q_numbers.append(quot.get('Quotation#'))
            agreed = _parse_price(quot.get('Agreed Price'))
            total_value += agreed
            q_dt = _to_datetime(quot.get('Date') or quot.get('created_at'))
            if q_dt and (last_activity is None or q_dt > last_activity):
                last_activity = q_dt

        # Contract stats - batch load (N+1 fix: single query instead of per-quotation)
        total_contracts = 0
        total_contract_value = 0
        valid_qns = [qn for qn in q_numbers if qn is not None]
        if valid_qns:
            try:
                all_contracts = list(_contracts_search_active(quotation_number=q.any_of(*valid_qns)))
            except Exception:
                all_contracts = []
            contracts_by_qn = {c['quotation_number']: c for c in all_contracts}
        else:
            contracts_by_qn = {}
        for qn in valid_qns:
            c = contracts_by_qn.get(qn)
            if not c:
                continue
            total_contracts += 1
            total_contract_value += _parse_price(c.get('total_price'))
            c_dt = _to_datetime(c.get('created_at'))
            if c_dt and (last_activity is None or c_dt > last_activity):
                last_activity = c_dt

        # Currency based on country
        country = (row.get('Country') or '').strip().lower()
        is_egypt = country in ('مصر', 'egypt', 'eg', 'مصري')
        currency = 'ج.م' if is_egypt else '$'

        stats = {
            'total_quotations': total_quotations,
            'total_value': round(total_value, 2),
            'total_contracts': total_contracts,
            'total_contract_value': round(total_contract_value, 2),
            'last_activity': _date_only(last_activity),
        }

        return {'success': True, 'client': client, 'stats': stats, 'currency': currency}

    except Exception as e:
        logger.exception("get_client_detail error: %s", e)
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_client_timeline(client_code, type_filter=None, page=1, page_size=20, token_or_email=None):
    """جلب التايم لاين الشامل للعميل"""
    is_valid, user_email, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error

    try:
        client_code = str(client_code).strip()
        page = max(1, int(page) if page else 1)
        page_size = max(1, min(50, int(page_size) if page_size else 20))

        # Determine currency from client country
        client_row = app_tables.clients.get(**{'Client Code': client_code})
        country = (client_row.get('Country') or '').strip().lower() if client_row else ''
        is_egypt = country in ('مصر', 'egypt', 'eg', 'مصري')
        cur = 'ج.م' if is_egypt else '$'

        events = []

        # 1. Quotations
        try:
            quotations = list(app_tables.quotations.search(**{'Client Code': client_code, 'is_deleted': False}))
            q_numbers = []
            for quot in quotations:
                qn = quot.get('Quotation#')
                q_numbers.append(qn)
                q_date = quot.get('Date') or quot.get('created_at')
                agreed = _parse_price(quot.get('Agreed Price'))

                events.append({
                    'date': _safe_isoformat(q_date),
                    'type': 'quotation',
                    'summary_en': f'Quotation #{qn} - {quot.get("Model", "")} - {agreed:,.0f} {cur}',
                    'summary_ar': f'عرض سعر #{qn} - {quot.get("Model", "")} - {agreed:,.0f} {cur}',
                    'detail_id': str(qn),
                    'detail_type': 'quotation',
                })
        except Exception as e:
            logger.warning("Timeline quotations error: %s", e)

        # 2. Contracts - batch load (N+1 fix: single query instead of per-quotation)
        try:
            valid_qns = [qn for qn in q_numbers if qn is not None]
            if valid_qns:
                try:
                    all_contracts = list(_contracts_search_active(quotation_number=q.any_of(*valid_qns)))
                except Exception:
                    all_contracts = []
                contracts_by_qn = {c['quotation_number']: c for c in all_contracts}
            else:
                contracts_by_qn = {}

            for qn in valid_qns:
                c = contracts_by_qn.get(qn)
                if not c:
                    continue
                c_date = c.get('created_at')
                cn = c.get('contract_number', '')
                tp = _parse_price(c.get('total_price'))

                events.append({
                    'date': _safe_isoformat(c_date),
                    'type': 'contract',
                    'summary_en': f'Contract {cn} created - {tp:,.0f} {cur}',
                    'summary_ar': f'عقد {cn} تم إنشاؤه - {tp:,.0f} {cur}',
                    'detail_id': cn,
                    'detail_type': 'contract',
                })

                # 3. Payments from contract
                payments = _parse_json(c.get('payments_json'))
                for i, p in enumerate(payments):
                    p_date = p.get('date') or p.get('paid_date')
                    status = p.get('status', '')
                    if status == 'paid':
                        amt = _parse_price(p.get('amount') or p.get('value'))
                        label_en = p.get('label_en', f'Installment {i+1}')
                        label_ar = p.get('label_ar', f'الدفعة {i+1}')
                        events.append({
                            'date': p.get('paid_date') or p_date or _safe_isoformat(c_date),
                            'type': 'payment',
                            'summary_en': f'Payment received: {label_en} - {amt:,.0f} {cur} (Contract {cn})',
                            'summary_ar': f'دفعة مستلمة: {label_ar} - {amt:,.0f} {cur} (عقد {cn})',
                            'detail_id': cn,
                            'detail_type': 'contract',
                        })
        except Exception as e:
            logger.warning("Timeline contracts error: %s", e)

        # 4. Notes from client
        try:
            row = client_row
            if row:
                notes = _parse_json(row.get('notes_json'))
                for n in notes:
                    events.append({
                        'date': n.get('created_at', ''),
                        'type': 'note',
                        'summary_en': f'Note by {n.get("author_name", "Unknown")}: {(n.get("text", ""))[:80]}',
                        'summary_ar': f'ملاحظة بواسطة {n.get("author_name", "غير معروف")}: {(n.get("text", ""))[:80]}',
                        'detail_id': n.get('id', ''),
                        'detail_type': 'note',
                    })
        except Exception as e:
            logger.warning("Timeline notes error: %s", e)

        # Apply type filter
        if type_filter and type_filter != 'all':
            events = [e for e in events if e['type'] == type_filter]

        # Sort by date (newest first)
        def sort_key(ev):
            d = ev.get('date', '')
            if not d:
                return ''
            return str(d)

        events.sort(key=sort_key, reverse=True)

        # Paginate
        total = len(events)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        page_events = events[start:start + page_size]

        return {
            'success': True,
            'data': page_events,
            'total': total,
            'total_pages': total_pages,
            'page': page,
        }

    except Exception as e:
        logger.exception("get_client_timeline error: %s", e)
        return {'success': False, 'message': str(e), 'data': [], 'total': 0, 'total_pages': 0}

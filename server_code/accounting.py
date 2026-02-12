"""
accounting.py - نظام المحاسبة المتكامل (القيد المزدوج)
======================================================
Double-entry accounting system for Helwan Plast.
- Chart of Accounts (شجرة الحسابات)
- General Ledger (دفتر الأستاذ العام) — immutable
- Suppliers CRUD (الموردين)
- Purchase Invoices (فواتير المشتريات)
- Import Costs (تكاليف الاستيراد)
- Expenses (المصروفات)
- Inventory (المخزون)
- Financial Reports: Trial Balance, Income Statement, Balance Sheet, Contract Profitability
"""

import anvil.server
from anvil.tables import app_tables
from datetime import datetime, date, timedelta
import json
import uuid
import logging

try:
    from . import AuthManager
except ImportError:
    import AuthManager

try:
    from .auth_utils import get_utc_now
except ImportError:
    from auth_utils import get_utc_now

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auth helpers (mirroring QuotationManager pattern)
# ---------------------------------------------------------------------------
def _require_authenticated(token_or_email):
    """Validate that the user is logged in. Returns (is_valid, user_email, error_dict)."""
    if not token_or_email:
        return False, None, {'success': False, 'message': 'Authentication required'}
    result = AuthManager.validate_token(token_or_email)
    if result and result.get('valid'):
        user = result.get('user', {})
        return True, user.get('email', 'unknown'), None
    return False, None, {'success': False, 'message': 'Invalid or expired session'}


def _require_permission(token_or_email, permission):
    """Validate that the user has a specific permission. Returns (is_valid, user_email, error_dict)."""
    is_valid, user_email, error = _require_authenticated(token_or_email)
    if not is_valid:
        return False, None, error
    if AuthManager.is_admin(token_or_email) or AuthManager.is_admin_by_email(token_or_email):
        return True, user_email, None
    if AuthManager.check_permission(token_or_email, permission):
        return True, user_email, None
    return False, user_email, {'success': False, 'message': f'Permission denied: {permission} access required'}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------
def _uuid():
    return str(uuid.uuid4())


def _round2(val):
    """Round to 2 decimal places, coerce to float safely."""
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return 0.0


def _safe_str(val, default=''):
    if val is None:
        return default
    return str(val).strip()


def _safe_date(val):
    """Accept ISO string or date/datetime, return date object or None."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    try:
        return datetime.strptime(str(val)[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _row_to_dict(row, columns):
    """Convert an Anvil table row to a plain dict with the given column names."""
    d = {}
    for col in columns:
        val = row.get(col)
        if isinstance(val, (datetime, date)):
            d[col] = val.isoformat()
        else:
            d[col] = val
    return d


# ===========================================================================
# 1. CHART OF ACCOUNTS
# ===========================================================================
ACCOUNT_COLS = ['code', 'name_en', 'name_ar', 'account_type', 'parent_code', 'is_active', 'created_at']

DEFAULT_ACCOUNTS = [
    # Assets
    ('1000', 'Cash',               'النقدية',           'asset',    None),
    ('1010', 'Bank',               'البنك',             'asset',    '1000'),
    ('1011', 'Bank - CIB',         'بنك CIB',          'asset',    '1010'),
    ('1012', 'Bank - NBE',         'البنك الأهلي',      'asset',    '1010'),
    ('1013', 'Bank - QNB',         'بنك QNB',          'asset',    '1010'),
    ('1100', 'Accounts Receivable','ذمم مدينة',         'asset',    None),
    ('1200', 'Inventory',          'المخزون',           'asset',    None),
    ('1210', 'Purchase in Transit','مشتريات في الطريق', 'asset',    '1200'),
    # Liabilities
    ('2000', 'Accounts Payable',   'ذمم دائنة',         'liability', None),
    ('2100', 'Tax Payable',        'ضريبة مستحقة',      'liability', None),
    # Equity
    ('3000', "Owner's Equity",     'حقوق الملكية',      'equity',   None),
    ('3100', 'Retained Earnings',  'أرباح محتجزة',      'equity',   None),
    # Revenue
    ('4000', 'Sales Revenue',      'إيرادات المبيعات',  'revenue',  None),
    ('4100', 'Other Revenue',      'إيرادات أخرى',      'revenue',  None),
    # COGS / Import
    ('5000', 'Cost of Goods Sold', 'تكلفة البضاعة المباعة', 'expense', None),
    ('5100', 'Import Costs',       'تكاليف الاستيراد',  'expense',  None),
    # Operating Expenses
    ('6000', 'Rent',               'الإيجار',           'expense',  None),
    ('6010', 'Utilities',          'المرافق',           'expense',  None),
    ('6020', 'Salaries',           'الرواتب',           'expense',  None),
    ('6030', 'Office Supplies',    'مستلزمات مكتبية',   'expense',  None),
    ('6040', 'Travel',             'السفر',             'expense',  None),
    ('6050', 'Maintenance',        'الصيانة',           'expense',  None),
    ('6090', 'Other Expenses',     'مصروفات أخرى',      'expense',  None),
]

# Map bank names to account codes
BANK_ACCOUNT_MAP = {
    'cash': '1000',
    'bank': '1010',
    'cib': '1011',
    'nbe': '1012',
    'qnb': '1013',
}


def _resolve_payment_account(payment_method):
    """Resolve payment method string to the correct account code.
    Supports: cash, bank, cib, nbe, qnb, or a direct account code like '1011'.
    """
    if not payment_method:
        return '1000'
    method = _safe_str(payment_method).lower().strip()
    # Direct account code
    if method in BANK_ACCOUNT_MAP:
        return BANK_ACCOUNT_MAP[method]
    # Check if it's a valid account code directly (e.g., '1011')
    if _validate_account_exists(method):
        return method
    # Default fallback
    return '1010' if 'bank' in method else '1000'


@anvil.server.callable
def get_chart_of_accounts(token_or_email=None):
    """Return the full chart of accounts as a list of dicts."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        rows = app_tables.chart_of_accounts.search()
        accounts = [_row_to_dict(r, ACCOUNT_COLS) for r in rows]
        accounts.sort(key=lambda a: a.get('code', ''))
        return {'success': True, 'accounts': accounts}
    except Exception as e:
        logger.exception("get_chart_of_accounts error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def add_account(code, name_en, name_ar, account_type, parent_code=None, token_or_email=None):
    """Add a single account to the chart of accounts."""
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    code = _safe_str(code)
    if not code or not name_en:
        return {'success': False, 'message': 'Account code and English name are required'}
    if account_type not in ('asset', 'liability', 'equity', 'revenue', 'expense'):
        return {'success': False, 'message': f'Invalid account_type: {account_type}'}
    try:
        existing = app_tables.chart_of_accounts.get(code=code)
        if existing:
            return {'success': False, 'message': f'Account code {code} already exists'}
        app_tables.chart_of_accounts.add_row(
            code=code,
            name_en=_safe_str(name_en),
            name_ar=_safe_str(name_ar),
            account_type=account_type,
            parent_code=_safe_str(parent_code) or None,
            is_active=True,
            created_at=get_utc_now(),
        )
        logger.info("Account %s created by %s", code, user_email)
        return {'success': True, 'code': code}
    except Exception as e:
        logger.exception("add_account error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable("seed_accounts")
def seed_default_accounts(token_or_email=None):
    """Seed the chart of accounts with the default Helwan Plast accounts. Skips existing codes."""
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    created = 0
    skipped = 0
    try:
        for code, name_en, name_ar, acct_type, parent in DEFAULT_ACCOUNTS:
            existing = app_tables.chart_of_accounts.get(code=code)
            if existing:
                skipped += 1
                continue
            app_tables.chart_of_accounts.add_row(
                code=code,
                name_en=name_en,
                name_ar=name_ar,
                account_type=acct_type,
                parent_code=parent,
                is_active=True,
                created_at=get_utc_now(),
            )
            created += 1
        logger.info("seed_default_accounts: created=%d skipped=%d by %s", created, skipped, user_email)
        return {'success': True, 'created': created, 'skipped': skipped}
    except Exception as e:
        logger.exception("seed_default_accounts error")
        return {'success': False, 'message': str(e)}


# ===========================================================================
# 2. GENERAL LEDGER (immutable double-entry)
# ===========================================================================
LEDGER_COLS = [
    'id', 'transaction_id', 'date', 'account_code', 'debit', 'credit',
    'description', 'reference_type', 'reference_id', 'created_by', 'created_at',
]


def _validate_account_exists(code):
    """Return True if the account code exists and is active."""
    acct = app_tables.chart_of_accounts.get(code=code)
    return acct is not None and acct.get('is_active', True)


def post_journal_entry(entry_date, entries, description, ref_type, ref_id, user_email):
    """
    Core double-entry posting function (internal, not callable directly).

    Parameters
    ----------
    entry_date : date or str
        The accounting date for the entry.
    entries : list[dict]
        Each dict has keys: account_code, debit (float), credit (float).
    description : str
        Narrative for the transaction.
    ref_type : str
        One of: sales_invoice, purchase_invoice, expense, payment, journal.
    ref_id : str
        The ID of the source document.
    user_email : str
        Who is posting.

    Returns
    -------
    dict  {'success': True, 'transaction_id': ...} or {'success': False, 'message': ...}
    """
    if not entries or len(entries) < 2:
        return {'success': False, 'message': 'Journal entry must have at least 2 lines'}

    total_debit = 0.0
    total_credit = 0.0
    for e in entries:
        d = _round2(e.get('debit', 0))
        c = _round2(e.get('credit', 0))
        if d < 0 or c < 0:
            return {'success': False, 'message': 'Debit and credit amounts must be non-negative'}
        if d > 0 and c > 0:
            return {'success': False, 'message': 'A single line cannot have both debit and credit'}
        if d == 0 and c == 0:
            return {'success': False, 'message': 'A line must have either a debit or credit amount'}
        total_debit += d
        total_credit += c

    # Fundamental accounting equation check
    if abs(total_debit - total_credit) > 0.005:
        return {
            'success': False,
            'message': f'Debits ({total_debit:.2f}) must equal credits ({total_credit:.2f})',
        }

    # Validate all account codes exist
    for e in entries:
        if not _validate_account_exists(e['account_code']):
            return {'success': False, 'message': f"Account code {e['account_code']} not found or inactive"}

    parsed_date = _safe_date(entry_date)
    if parsed_date is None:
        return {'success': False, 'message': 'Invalid date for journal entry'}

    transaction_id = _uuid()
    now = get_utc_now()

    try:
        for e in entries:
            app_tables.ledger.add_row(
                id=_uuid(),
                transaction_id=transaction_id,
                date=parsed_date,
                account_code=e['account_code'],
                debit=_round2(e.get('debit', 0)),
                credit=_round2(e.get('credit', 0)),
                description=_safe_str(description),
                reference_type=_safe_str(ref_type),
                reference_id=_safe_str(ref_id),
                created_by=_safe_str(user_email),
                created_at=now,
            )
        logger.info("Journal entry %s posted (%d lines) by %s", transaction_id, len(entries), user_email)
        return {'success': True, 'transaction_id': transaction_id}
    except Exception as e:
        logger.exception("post_journal_entry error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def create_journal_entry(entry_date, entries, description, ref_type='journal', ref_id='', token_or_email=None):
    """Callable wrapper around post_journal_entry for manual journal entries."""
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    if not ref_id:
        ref_id = f"JE-{_uuid()[:8]}"
    return post_journal_entry(entry_date, entries, description, ref_type, ref_id, user_email)


@anvil.server.callable
def get_ledger_entries(account_code=None, date_from=None, date_to=None, ref_type=None, token_or_email=None):
    """Query ledger entries with optional filters."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        # Build search kwargs to filter at DB level
        search_kwargs = {}
        if account_code:
            search_kwargs['account_code'] = account_code
        if ref_type:
            search_kwargs['reference_type'] = ref_type

        d_from = _safe_date(date_from)
        d_to = _safe_date(date_to)
        results = []

        for r in app_tables.ledger.search(**search_kwargs):
            if d_from or d_to:
                row_date = r.get('date')
                if isinstance(row_date, datetime):
                    row_date = row_date.date()
                if d_from and row_date and row_date < d_from:
                    continue
                if d_to and row_date and row_date > d_to:
                    continue
            results.append(_row_to_dict(r, LEDGER_COLS))

        results.sort(key=lambda x: (x.get('date', ''), x.get('created_at', '')))
        return {'success': True, 'entries': results, 'count': len(results)}
    except Exception as e:
        logger.exception("get_ledger_entries error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_account_balance(account_code, as_of_date=None, token_or_email=None):
    """
    Calculate the balance for a single account up to as_of_date.
    Assets/Expenses: debit-normal (balance = sum(debit) - sum(credit))
    Liabilities/Equity/Revenue: credit-normal (balance = sum(credit) - sum(debit))
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        acct = app_tables.chart_of_accounts.get(code=account_code)
        if not acct:
            return {'success': False, 'message': f'Account {account_code} not found'}

        cutoff = _safe_date(as_of_date)
        total_debit = 0.0
        total_credit = 0.0

        for r in app_tables.ledger.search(account_code=account_code):
            row_date = r.get('date')
            if isinstance(row_date, datetime):
                row_date = row_date.date()
            if cutoff and row_date and row_date > cutoff:
                continue
            total_debit += _round2(r.get('debit', 0))
            total_credit += _round2(r.get('credit', 0))

        acct_type = acct.get('account_type', '')
        if acct_type in ('asset', 'expense'):
            balance = _round2(total_debit - total_credit)
        else:
            balance = _round2(total_credit - total_debit)

        return {
            'success': True,
            'account_code': account_code,
            'account_type': acct_type,
            'total_debit': _round2(total_debit),
            'total_credit': _round2(total_credit),
            'balance': balance,
        }
    except Exception as e:
        logger.exception("get_account_balance error")
        return {'success': False, 'message': str(e)}


# ===========================================================================
# 3. SUPPLIERS CRUD
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
        rows = list(app_tables.suppliers.search(is_active=True))
        results = []
        search_lower = _safe_str(search).lower()
        for r in rows:
            if search_lower:
                searchable = ' '.join([
                    _safe_str(r.get('name')),
                    _safe_str(r.get('company')),
                    _safe_str(r.get('phone')),
                    _safe_str(r.get('email')),
                    _safe_str(r.get('country')),
                ]).lower()
                if search_lower not in searchable:
                    continue
            results.append(_row_to_dict(r, SUPPLIER_COLS))
        results.sort(key=lambda s: s.get('name', ''))
        return {'success': True, 'suppliers': results, 'count': len(results)}
    except Exception as e:
        logger.exception("get_suppliers error")
        return {'success': False, 'message': str(e)}


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
        return {'success': False, 'message': str(e)}


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
        return {'success': False, 'message': str(e)}


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
        return {'success': False, 'message': str(e)}


# ===========================================================================
# 4. PURCHASE INVOICES
# ===========================================================================
PURCHASE_INVOICE_COLS = [
    'id', 'invoice_number', 'supplier_id', 'date', 'due_date', 'items_json',
    'subtotal', 'tax_amount', 'total', 'paid_amount', 'status', 'notes',
    'machine_code', 'contract_number', 'created_by', 'created_at', 'updated_at',
]


def _generate_invoice_number():
    """Generate next purchase invoice number as PI-YYYY-NNNN."""
    year = datetime.now().year
    prefix = f"PI-{year}-"
    max_seq = 0
    try:
        for r in app_tables.purchase_invoices.search():
            inv_num = _safe_str(r.get('invoice_number'))
            if inv_num.startswith(prefix):
                try:
                    seq = int(inv_num[len(prefix):])
                    if seq > max_seq:
                        max_seq = seq
                except (ValueError, TypeError):
                    pass
    except Exception as _e:
        logger.debug("Suppressed: %s", _e)
    return f"{prefix}{max_seq + 1:04d}"


@anvil.server.callable
def get_purchase_invoices(status=None, search='', token_or_email=None):
    """Return purchase invoices, optionally filtered by status and search."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        # Filter at DB level when status is provided, stream instead of list()
        search_kwargs = {}
        if status:
            search_kwargs['status'] = status
        rows = app_tables.purchase_invoices.search(**search_kwargs)
        results = []
        search_lower = _safe_str(search).lower()
        for r in rows:
            if search_lower:
                searchable = ' '.join([
                    _safe_str(r.get('invoice_number')),
                    _safe_str(r.get('supplier_id')),
                    _safe_str(r.get('machine_code')),
                    _safe_str(r.get('notes')),
                ]).lower()
                if search_lower not in searchable:
                    continue
            d = _row_to_dict(r, PURCHASE_INVOICE_COLS)
            # Parse items_json for convenience
            try:
                d['items'] = json.loads(d.get('items_json') or '[]')
            except (json.JSONDecodeError, TypeError):
                d['items'] = []
            results.append(d)
        results.sort(key=lambda x: x.get('date', ''), reverse=True)
        return {'success': True, 'invoices': results, 'count': len(results)}
    except Exception as e:
        logger.exception("get_purchase_invoices error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def create_purchase_invoice(data, token_or_email=None):
    """
    Create a new purchase invoice in draft status.

    data keys: supplier_id, date, due_date, items (list of dicts), tax_amount,
               notes, machine_code, contract_number
    Each item: {description, quantity, unit_price, total}
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    supplier_id = _safe_str(data.get('supplier_id'))
    if not supplier_id:
        return {'success': False, 'message': 'Supplier is required'}

    items = data.get('items', [])
    if not items:
        return {'success': False, 'message': 'At least one line item is required'}

    # Calculate totals from line items
    subtotal = 0.0
    for item in items:
        line_total = _round2(item.get('total', 0))
        if line_total == 0:
            qty = _round2(item.get('quantity', 0))
            up = _round2(item.get('unit_price', 0))
            line_total = _round2(qty * up)
            item['total'] = line_total
        subtotal += line_total

    tax_amount = _round2(data.get('tax_amount', 0))
    total = _round2(subtotal + tax_amount)
    inv_id = _uuid()
    inv_number = _generate_invoice_number()
    now = get_utc_now()

    try:
        app_tables.purchase_invoices.add_row(
            id=inv_id,
            invoice_number=inv_number,
            supplier_id=supplier_id,
            date=_safe_date(data.get('date')) or date.today(),
            due_date=_safe_date(data.get('due_date')),
            items_json=json.dumps(items, ensure_ascii=False, default=str),
            subtotal=_round2(subtotal),
            tax_amount=tax_amount,
            total=total,
            paid_amount=0.0,
            status='draft',
            notes=_safe_str(data.get('notes')),
            machine_code=_safe_str(data.get('machine_code')) or None,
            contract_number=_safe_str(data.get('contract_number')) or None,
            created_by=user_email,
            created_at=now,
            updated_at=now,
        )
        logger.info("Purchase invoice %s created by %s", inv_number, user_email)
        return {'success': True, 'id': inv_id, 'invoice_number': inv_number}
    except Exception as e:
        logger.exception("create_purchase_invoice error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def post_purchase_invoice(invoice_id, token_or_email=None):
    """
    Post a draft purchase invoice: creates ledger entries.
    DR Inventory (1200) or COGS (5000)  — total
    CR Accounts Payable (2000)          — total
    If tax: DR Tax Payable (2100)       — tax_amount
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    try:
        row = app_tables.purchase_invoices.get(id=invoice_id)
        if not row:
            return {'success': False, 'message': 'Purchase invoice not found'}
        if row.get('status') != 'draft':
            return {'success': False, 'message': f"Cannot post invoice with status '{row.get('status')}'. Only draft invoices can be posted."}

        total = _round2(row.get('total', 0))
        subtotal = _round2(row.get('subtotal', 0))
        tax_amount = _round2(row.get('tax_amount', 0))

        if total <= 0:
            return {'success': False, 'message': 'Invoice total must be greater than zero'}

        # Build journal entries
        inv_date = row.get('date') or date.today()
        entries = []

        # Debit: Inventory for the subtotal (pre-tax cost of goods)
        entries.append({'account_code': '1200', 'debit': subtotal, 'credit': 0})

        # Debit: Tax Payable if there is tax (input VAT / recoverable tax)
        if tax_amount > 0:
            entries.append({'account_code': '2100', 'debit': tax_amount, 'credit': 0})

        # Credit: Accounts Payable for the full total
        entries.append({'account_code': '2000', 'debit': 0, 'credit': total})

        inv_number = row.get('invoice_number', invoice_id)
        result = post_journal_entry(
            inv_date, entries,
            f"Purchase invoice {inv_number} posted",
            'purchase_invoice', invoice_id, user_email,
        )
        if not result.get('success'):
            return result

        row.update(status='posted', updated_at=get_utc_now())
        logger.info("Purchase invoice %s posted by %s", inv_number, user_email)
        return {'success': True, 'transaction_id': result['transaction_id']}
    except Exception as e:
        logger.exception("post_purchase_invoice error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def create_contract_purchase(contract_number, fob_cost, cylinder_cost, supplier_id,
                             currency='USD', token_or_email=None):
    """
    PART 1: Contract → Purchase Invoice auto-generation.
    When a contract is created, call this to:
    1) Create a Purchase Invoice from FOB + Cylinder cost
    2) Post journal: DR Inventory (1200), CR Accounts Payable (2000)
    3) Create inventory item linked to the contract
    4) Link purchase invoice back to the contract

    Returns: {success, invoice_id, invoice_number, inventory_id, transaction_id}
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error

    fob_cost = _round2(fob_cost)
    cylinder_cost = _round2(cylinder_cost)
    if fob_cost <= 0:
        return {'success': False, 'message': 'FOB cost must be greater than zero'}
    if not supplier_id:
        return {'success': False, 'message': 'Supplier is required'}
    if not contract_number:
        return {'success': False, 'message': 'Contract number is required'}

    try:
        # Verify supplier exists
        supplier = app_tables.suppliers.get(id=supplier_id)
        if not supplier:
            return {'success': False, 'message': 'Supplier not found'}

        # Build line items
        items = [{'description': 'FOB Cost (Machine)', 'quantity': 1, 'unit_price': fob_cost, 'total': fob_cost}]
        if cylinder_cost > 0:
            items.append({'description': 'Cylinder Cost', 'quantity': 1, 'unit_price': cylinder_cost, 'total': cylinder_cost})

        subtotal = _round2(fob_cost + cylinder_cost)

        # Create purchase invoice in draft then post it
        inv_id = _uuid()
        inv_number = _generate_invoice_number()
        now = get_utc_now()
        today = date.today()

        app_tables.purchase_invoices.add_row(
            id=inv_id,
            invoice_number=inv_number,
            supplier_id=supplier_id,
            date=today,
            due_date=None,
            items_json=json.dumps(items, ensure_ascii=False, default=str),
            subtotal=subtotal,
            tax_amount=0.0,
            total=subtotal,
            paid_amount=0.0,
            status='draft',
            notes=f"Auto-generated from contract {contract_number} | Currency: {currency}",
            machine_code=None,
            contract_number=contract_number,
            created_by=user_email,
            created_at=now,
            updated_at=now,
        )

        # Post the invoice immediately (DR Inventory, CR AP)
        entries = [
            {'account_code': '1200', 'debit': subtotal, 'credit': 0},
            {'account_code': '2000', 'debit': 0, 'credit': subtotal},
        ]
        je_result = post_journal_entry(
            today, entries,
            f"Purchase from contract {contract_number} - {inv_number}",
            'purchase_invoice', inv_id, user_email,
        )
        if not je_result.get('success'):
            # Rollback: delete the draft invoice
            try:
                row = app_tables.purchase_invoices.get(id=inv_id)
                if row:
                    row.delete()
            except Exception:
                pass
            return je_result

        # Mark invoice as posted
        inv_row = app_tables.purchase_invoices.get(id=inv_id)
        if inv_row:
            inv_row.update(status='posted', updated_at=get_utc_now())

        # Create inventory item linked to this purchase — starts as in_transit
        inv_item_id = _uuid()
        app_tables.inventory.add_row(
            id=inv_item_id,
            machine_code=contract_number,
            description=f"Machine for contract {contract_number}",
            purchase_invoice_id=inv_id,
            contract_number=None,  # Not sold yet — will be set when sale is recorded
            purchase_cost=subtotal,
            import_costs_total=0.0,
            total_cost=subtotal,
            selling_price=0.0,
            status='in_transit',
            location='',
            notes=f"FOB: {fob_cost}, Cylinders: {cylinder_cost}",
            created_at=now,
            updated_at=now,
        )

        # Update contract row with purchase_invoice_id
        try:
            contract_row = app_tables.contracts.get(contract_number=contract_number)
            if contract_row:
                contract_row.update(
                    fob_cost=fob_cost,
                    cylinder_cost=cylinder_cost,
                    supplier_id=supplier_id,
                    purchase_invoice_id=inv_id,
                    currency=_safe_str(currency) or 'USD',
                    updated_at=get_utc_now(),
                )
        except Exception as e:
            logger.warning("Could not update contract with purchase info: %s", e)

        logger.info("Contract purchase created: %s -> %s by %s", contract_number, inv_number, user_email)
        return {
            'success': True,
            'invoice_id': inv_id,
            'invoice_number': inv_number,
            'inventory_id': inv_item_id,
            'transaction_id': je_result['transaction_id'],
            'total': subtotal,
        }
    except Exception as e:
        logger.exception("create_contract_purchase error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_contract_payable_status(contract_number=None, token_or_email=None):
    """
    Get payable tracking for a contract or all contracts.
    Returns: total, paid, remaining, payment_history per contract.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error

    try:
        if contract_number:
            invoices = list(app_tables.purchase_invoices.search(contract_number=contract_number))
        else:
            # Get all purchase invoices that have a contract_number
            invoices = [r for r in app_tables.purchase_invoices.search() if r.get('contract_number')]

        results = []
        for inv in invoices:
            inv_id = inv.get('id')
            total = _round2(inv.get('total', 0))
            paid = _round2(inv.get('paid_amount', 0))
            remaining = _round2(total - paid)

            # Get payment history from ledger
            payment_history = []
            for entry in app_tables.ledger.search(reference_id=inv_id, reference_type='payment'):
                if _round2(entry.get('debit', 0)) > 0 and entry.get('account_code') == '2000':
                    payment_history.append({
                        'date': entry.get('date').isoformat() if entry.get('date') else '',
                        'amount': _round2(entry.get('debit', 0)),
                        'description': entry.get('description', ''),
                        'transaction_id': entry.get('transaction_id', ''),
                    })

            # Get import costs for this invoice
            import_costs = []
            import_total = 0.0
            for ic in app_tables.import_costs.search(purchase_invoice_id=inv_id):
                ic_amt = _round2(ic.get('amount', 0))
                import_costs.append({
                    'type': ic.get('cost_type', ''),
                    'amount': ic_amt,
                    'description': ic.get('description', ''),
                    'date': ic.get('date').isoformat() if ic.get('date') else '',
                })
                import_total += ic_amt

            results.append({
                'contract_number': inv.get('contract_number', ''),
                'invoice_number': inv.get('invoice_number', ''),
                'invoice_id': inv_id,
                'supplier_id': inv.get('supplier_id', ''),
                'total': total,
                'paid': paid,
                'remaining': remaining,
                'status': inv.get('status', ''),
                'import_costs': import_costs,
                'import_total': _round2(import_total),
                'landed_cost': _round2(total + import_total),
                'payment_history': payment_history,
            })

        return {'success': True, 'contracts': results, 'count': len(results)}
    except Exception as e:
        logger.exception("get_contract_payable_status error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def record_supplier_payment(invoice_id, amount, payment_method, payment_date, token_or_email=None):
    """
    Record a payment against a purchase invoice.
    DR Accounts Payable (2000)
    CR Cash (1000) or Bank (1010/1011/1012/1013)
    Supports multiple banks: cash, bank, cib, nbe, qnb, or direct account code.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error

    amount = _round2(amount)
    if amount <= 0:
        return {'success': False, 'message': 'Payment amount must be greater than zero'}

    try:
        row = app_tables.purchase_invoices.get(id=invoice_id)
        if not row:
            return {'success': False, 'message': 'Purchase invoice not found'}
        if row.get('status') in ('draft', 'cancelled'):
            return {'success': False, 'message': f"Cannot record payment for invoice with status '{row.get('status')}'"}

        current_paid = _round2(row.get('paid_amount', 0))
        total = _round2(row.get('total', 0))
        if current_paid + amount > total + 0.005:
            return {'success': False, 'message': f'Payment of {amount:.2f} exceeds remaining balance of {total - current_paid:.2f}'}

        # Determine cash/bank account — supports multiple banks
        cash_account = _resolve_payment_account(payment_method)
        parsed_date = _safe_date(payment_date) or date.today()

        entries = [
            {'account_code': '2000', 'debit': amount, 'credit': 0},
            {'account_code': cash_account, 'debit': 0, 'credit': amount},
        ]
        inv_number = row.get('invoice_number', invoice_id)
        result = post_journal_entry(
            parsed_date, entries,
            f"Payment for purchase invoice {inv_number} ({payment_method})",
            'payment', invoice_id, user_email,
        )
        if not result.get('success'):
            return result

        new_paid = _round2(current_paid + amount)
        new_status = 'paid' if abs(new_paid - total) < 0.005 else 'partial'
        row.update(paid_amount=new_paid, status=new_status, updated_at=get_utc_now())

        logger.info("Supplier payment %.2f for %s by %s", amount, inv_number, user_email)
        return {'success': True, 'paid_amount': new_paid, 'status': new_status, 'transaction_id': result['transaction_id']}
    except Exception as e:
        logger.exception("record_supplier_payment error")
        return {'success': False, 'message': str(e)}


# ===========================================================================
# 5. IMPORT COSTS
# ===========================================================================
IMPORT_COST_COLS = ['id', 'purchase_invoice_id', 'cost_type', 'description', 'amount', 'date',
                    'created_by', 'created_at', 'contract_number', 'payment_account']

VALID_COST_TYPES = ('shipping', 'customs', 'insurance', 'clearance', 'transport', 'other')


@anvil.server.callable
def add_import_cost(purchase_invoice_id, cost_type, amount, description='',
                    cost_date=None, payment_method='cash', contract_number=None,
                    token_or_email=None):
    """
    Add an import cost linked to a purchase invoice.
    CRITICAL: Import costs are part of Landed Cost, NOT period expenses.

    If inventory is NOT sold yet (in_transit / in_stock):
        DR 1200 Inventory — increases inventory (landed cost)
        CR Cash/Bank (selected account)

    If inventory is ALREADY SOLD:
        Import costs are blocked. Late costs after sale must be posted
        manually as adjustments.

    payment_method: cash, bank, cib, nbe, qnb, or direct account code
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error

    amount = _round2(amount)
    if amount <= 0:
        return {'success': False, 'message': 'Import cost amount must be greater than zero'}
    if cost_type not in VALID_COST_TYPES:
        return {'success': False, 'message': f'Invalid cost_type. Must be one of: {", ".join(VALID_COST_TYPES)}'}

    try:
        inv_row = app_tables.purchase_invoices.get(id=purchase_invoice_id)
        if not inv_row:
            return {'success': False, 'message': 'Purchase invoice not found'}

        # Auto-detect contract_number from the invoice if not provided
        if not contract_number:
            contract_number = inv_row.get('contract_number')

        # Check if related inventory item is already sold
        inv_items = list(app_tables.inventory.search(purchase_invoice_id=purchase_invoice_id))
        sold_items = [it for it in inv_items if it.get('status') == 'sold']
        if sold_items:
            return {
                'success': False,
                'message': 'Cannot add import costs: machine is already sold. '
                           'Use a manual COGS adjustment entry instead.',
            }

        parsed_date = _safe_date(cost_date) or date.today()
        cost_id = _uuid()
        credit_account = _resolve_payment_account(payment_method)

        # Resolve the inventory account from chart of accounts (not hardcoded)
        inventory_account = '1200'
        acct_check = app_tables.chart_of_accounts.get(code=inventory_account)
        if not acct_check or not acct_check.get('is_active', True):
            return {'success': False, 'message': f'Inventory account {inventory_account} not found or inactive'}

        # Ledger entry: DR Inventory (landed cost), CR Cash/Bank
        entries = [
            {'account_code': inventory_account, 'debit': amount, 'credit': 0},
            {'account_code': credit_account, 'debit': 0, 'credit': amount},
        ]
        je_result = post_journal_entry(
            parsed_date, entries,
            f"Import cost ({cost_type}) for {contract_number or purchase_invoice_id}: {description}",
            'import_cost', cost_id, user_email,
        )
        if not je_result.get('success'):
            return je_result

        app_tables.import_costs.add_row(
            id=cost_id,
            purchase_invoice_id=purchase_invoice_id,
            cost_type=cost_type,
            description=_safe_str(description),
            amount=amount,
            date=parsed_date,
            created_by=user_email,
            created_at=get_utc_now(),
            contract_number=_safe_str(contract_number) or None,
            payment_account=credit_account,
        )

        # Update linked inventory items — recalculate landed cost
        _update_inventory_import_totals(purchase_invoice_id)

        logger.info("Import cost %s (%.2f) added to %s by %s [DR %s, CR %s]",
                     cost_type, amount, purchase_invoice_id, user_email,
                     inventory_account, credit_account)
        return {'success': True, 'id': cost_id, 'transaction_id': je_result['transaction_id']}
    except Exception as e:
        logger.exception("add_import_cost error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_import_costs(purchase_invoice_id, token_or_email=None):
    """Return all import costs for a specific purchase invoice."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        rows = list(app_tables.import_costs.search(purchase_invoice_id=purchase_invoice_id))
        costs = [_row_to_dict(r, IMPORT_COST_COLS) for r in rows]
        total = _round2(sum(c.get('amount', 0) for c in costs))
        return {'success': True, 'costs': costs, 'total': total}
    except Exception as e:
        logger.exception("get_import_costs error")
        return {'success': False, 'message': str(e)}


def _update_inventory_import_totals(purchase_invoice_id):
    """Recalculate import_costs_total and total_cost for inventory items linked to a purchase invoice."""
    try:
        cost_rows = list(app_tables.import_costs.search(purchase_invoice_id=purchase_invoice_id))
        import_total = _round2(sum(_round2(r.get('amount', 0)) for r in cost_rows))

        inv_items = list(app_tables.inventory.search(purchase_invoice_id=purchase_invoice_id))
        for item in inv_items:
            purchase_cost = _round2(item.get('purchase_cost', 0))
            item.update(
                import_costs_total=import_total,
                total_cost=_round2(purchase_cost + import_total),
                updated_at=get_utc_now(),
            )
    except Exception as e:
        logger.warning("_update_inventory_import_totals error: %s", e)


# ===========================================================================
# 6. EXPENSES
# ===========================================================================
EXPENSE_COLS = [
    'id', 'date', 'category', 'description', 'amount', 'payment_method',
    'reference', 'account_code', 'status', 'created_by', 'created_at',
]

VALID_EXPENSE_CATEGORIES = ('rent', 'utilities', 'salaries', 'office', 'travel', 'maintenance', 'other')
VALID_PAYMENT_METHODS = ('cash', 'bank', 'check')

# Map expense categories to default account codes
CATEGORY_ACCOUNT_MAP = {
    'rent': '6000',
    'utilities': '6010',
    'salaries': '6020',
    'office': '6030',
    'travel': '6040',
    'maintenance': '6050',
    'other': '6090',
}


@anvil.server.callable
def get_expenses(date_from=None, date_to=None, category=None, token_or_email=None):
    """Query expenses with optional filters."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        # Filter at DB level where possible, stream instead of list()
        search_kwargs = {}
        if category:
            search_kwargs['category'] = category
        rows = app_tables.expenses.search(**search_kwargs)
        results = []
        d_from = _safe_date(date_from)
        d_to = _safe_date(date_to)

        for r in rows:
            if r.get('status') == 'cancelled':
                continue
            row_date = r.get('date')
            if isinstance(row_date, datetime):
                row_date = row_date.date()
            if d_from and row_date and row_date < d_from:
                continue
            if d_to and row_date and row_date > d_to:
                continue
            results.append(_row_to_dict(r, EXPENSE_COLS))

        results.sort(key=lambda x: x.get('date', ''), reverse=True)
        total_amount = _round2(sum(_round2(x.get('amount', 0)) for x in results))
        return {'success': True, 'expenses': results, 'count': len(results), 'total_amount': total_amount}
    except Exception as e:
        logger.exception("get_expenses error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def add_expense(data, token_or_email=None):
    """
    Record an expense.
    DR Expense Account (from category mapping or explicit account_code)
    CR Cash (1000) / Bank (1010) / Cash (1000 for check)
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error

    amount = _round2(data.get('amount', 0))
    if amount <= 0:
        return {'success': False, 'message': 'Expense amount must be greater than zero'}

    category = _safe_str(data.get('category')).lower()
    if category and category not in VALID_EXPENSE_CATEGORIES:
        return {'success': False, 'message': f'Invalid category. Must be one of: {", ".join(VALID_EXPENSE_CATEGORIES)}'}

    payment_method = _safe_str(data.get('payment_method', 'cash')).lower()
    if payment_method not in VALID_PAYMENT_METHODS:
        return {'success': False, 'message': f'Invalid payment method. Must be one of: {", ".join(VALID_PAYMENT_METHODS)}'}

    # Determine the expense account code
    account_code = _safe_str(data.get('account_code'))
    if not account_code:
        account_code = CATEGORY_ACCOUNT_MAP.get(category, '6090')

    parsed_date = _safe_date(data.get('date')) or date.today()
    expense_id = _uuid()

    # Determine credit account — supports multiple banks
    credit_account = _resolve_payment_account(payment_method)

    entries = [
        {'account_code': account_code, 'debit': amount, 'credit': 0},
        {'account_code': credit_account, 'debit': 0, 'credit': amount},
    ]

    try:
        desc = _safe_str(data.get('description'))
        je_result = post_journal_entry(
            parsed_date, entries,
            f"Expense ({category}): {desc}",
            'expense', expense_id, user_email,
        )
        if not je_result.get('success'):
            return je_result

        app_tables.expenses.add_row(
            id=expense_id,
            date=parsed_date,
            category=category,
            description=desc,
            amount=amount,
            payment_method=payment_method,
            reference=_safe_str(data.get('reference')) or None,
            account_code=account_code,
            status='posted',
            created_by=user_email,
            created_at=get_utc_now(),
        )
        logger.info("Expense %s (%.2f, %s) created by %s", expense_id, amount, category, user_email)
        return {'success': True, 'id': expense_id, 'transaction_id': je_result['transaction_id']}
    except Exception as e:
        logger.exception("add_expense error")
        return {'success': False, 'message': str(e)}


# ===========================================================================
# 7. INVENTORY
# ===========================================================================
INVENTORY_COLS = [
    'id', 'machine_code', 'description', 'purchase_invoice_id', 'contract_number',
    'purchase_cost', 'import_costs_total', 'total_cost', 'selling_price',
    'status', 'location', 'notes', 'created_at', 'updated_at',
]


@anvil.server.callable
def receive_inventory(item_id, location='', token_or_email=None):
    """
    Mark an inventory item as received (in_transit → in_stock).
    No P&L impact — this is just a status change.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'edit')
    if not is_valid:
        return error
    try:
        row = app_tables.inventory.get(id=item_id)
        if not row:
            return {'success': False, 'message': 'Inventory item not found'}
        current_status = row.get('status', '')
        if current_status not in ('in_transit', 'reserved'):
            return {'success': False, 'message': f"Cannot receive item with status '{current_status}'. Must be 'in_transit'."}
        updates = {'status': 'in_stock', 'updated_at': get_utc_now()}
        if location:
            updates['location'] = _safe_str(location)
        row.update(**updates)
        logger.info("Inventory %s received (in_stock) by %s", item_id, user_email)
        return {'success': True, 'status': 'in_stock'}
    except Exception as e:
        logger.exception("receive_inventory error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_bank_accounts(token_or_email=None):
    """Return list of cash/bank accounts for payment dropdowns."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        accounts = []
        for r in app_tables.chart_of_accounts.search(is_active=True):
            code = r.get('code', '')
            # Include cash and all bank sub-accounts
            if code == '1000' or (code.startswith('101') and len(code) == 4):
                accounts.append({
                    'code': code,
                    'name_en': r.get('name_en', ''),
                    'name_ar': r.get('name_ar', ''),
                })
        accounts.sort(key=lambda a: a.get('code', ''))
        return {'success': True, 'accounts': accounts}
    except Exception as e:
        logger.exception("get_bank_accounts error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def migrate_import_costs_to_inventory(token_or_email=None):
    """
    MIGRATION: Fix previously posted import costs that debited 5100 (expense)
    instead of 1200 (inventory).

    For each import cost that was posted with DR 5100:
    1) Post adjusting entry: DR 1200, CR 5100 (move from expense to inventory)
    2) Update inventory item totals

    This is a ONE-TIME migration. Safe to run multiple times (idempotent).
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error

    try:
        migrated = 0
        skipped = 0
        errors = []

        for ic in app_tables.import_costs.search():
            cost_id = ic.get('id')
            amount = _round2(ic.get('amount', 0))
            if amount <= 0:
                skipped += 1
                continue

            # Check if this cost was posted to 5100 (old logic)
            old_entries = list(app_tables.ledger.search(reference_id=cost_id, account_code='5100'))
            if not old_entries:
                skipped += 1
                continue

            # Already has a migration entry? (check for import_cost_migration type)
            migration_entries = list(app_tables.ledger.search(
                reference_id=f"MIG-{cost_id}", reference_type='import_cost_migration'))
            if migration_entries:
                skipped += 1
                continue

            # Post adjusting entry: DR 1200 Inventory, CR 5100 Import Costs
            adj_entries = [
                {'account_code': '1200', 'debit': amount, 'credit': 0},
                {'account_code': '5100', 'debit': 0, 'credit': amount},
            ]
            adj_date = ic.get('date') or date.today()
            adj_result = post_journal_entry(
                adj_date, adj_entries,
                f"Migration: reclassify import cost {cost_id} from expense to inventory",
                'import_cost_migration', f"MIG-{cost_id}", user_email,
            )
            if adj_result.get('success'):
                migrated += 1
                # Update inventory totals
                pi_id = ic.get('purchase_invoice_id')
                if pi_id:
                    _update_inventory_import_totals(pi_id)
            else:
                errors.append(f"{cost_id}: {adj_result.get('message', 'unknown')}")

        logger.info("Import cost migration: %d migrated, %d skipped, %d errors by %s",
                     migrated, skipped, len(errors), user_email)
        return {
            'success': True,
            'migrated': migrated,
            'skipped': skipped,
            'errors': errors,
        }
    except Exception as e:
        logger.exception("migrate_import_costs_to_inventory error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_inventory(status=None, search='', token_or_email=None):
    """Return inventory items, optionally filtered by status and search term."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        # Filter at DB level when status is provided, stream instead of list()
        search_kwargs = {}
        if status:
            search_kwargs['status'] = status
        rows = app_tables.inventory.search(**search_kwargs)
        results = []
        search_lower = _safe_str(search).lower()
        for r in rows:
            if search_lower:
                searchable = ' '.join([
                    _safe_str(r.get('machine_code')),
                    _safe_str(r.get('description')),
                    _safe_str(r.get('location')),
                    _safe_str(r.get('contract_number')),
                ]).lower()
                if search_lower not in searchable:
                    continue
            results.append(_row_to_dict(r, INVENTORY_COLS))
        results.sort(key=lambda x: x.get('machine_code', ''))
        return {'success': True, 'items': results, 'count': len(results)}
    except Exception as e:
        logger.exception("get_inventory error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def add_inventory_item(data, token_or_email=None):
    """Add a new inventory item (machine)."""
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error

    machine_code = _safe_str(data.get('machine_code'))
    if not machine_code:
        return {'success': False, 'message': 'Machine code is required'}

    purchase_cost = _round2(data.get('purchase_cost', 0))
    import_costs_total = _round2(data.get('import_costs_total', 0))
    item_id = _uuid()
    now = get_utc_now()

    try:
        app_tables.inventory.add_row(
            id=item_id,
            machine_code=machine_code,
            description=_safe_str(data.get('description')),
            purchase_invoice_id=_safe_str(data.get('purchase_invoice_id')) or None,
            contract_number=_safe_str(data.get('contract_number')) or None,
            purchase_cost=purchase_cost,
            import_costs_total=import_costs_total,
            total_cost=_round2(purchase_cost + import_costs_total),
            selling_price=_round2(data.get('selling_price', 0)),
            status=_safe_str(data.get('status', 'in_stock')),
            location=_safe_str(data.get('location')) or None,
            notes=_safe_str(data.get('notes')),
            created_at=now,
            updated_at=now,
        )
        logger.info("Inventory item %s (%s) created by %s", item_id, machine_code, user_email)
        return {'success': True, 'id': item_id}
    except Exception as e:
        logger.exception("add_inventory_item error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def update_inventory_item(item_id, data, token_or_email=None):
    """Update an existing inventory item."""
    is_valid, user_email, error = _require_permission(token_or_email, 'edit')
    if not is_valid:
        return error
    try:
        row = app_tables.inventory.get(id=item_id)
        if not row:
            return {'success': False, 'message': 'Inventory item not found'}

        updates = {}
        for field in ['machine_code', 'description', 'location', 'notes', 'status']:
            if field in data:
                updates[field] = _safe_str(data[field])
        for field in ['purchase_cost', 'import_costs_total', 'selling_price']:
            if field in data:
                updates[field] = _round2(data[field])

        # Recalculate total_cost if cost fields changed
        pc = updates.get('purchase_cost', _round2(row.get('purchase_cost', 0)))
        ic = updates.get('import_costs_total', _round2(row.get('import_costs_total', 0)))
        updates['total_cost'] = _round2(pc + ic)
        updates['updated_at'] = get_utc_now()

        row.update(**updates)
        logger.info("Inventory item %s updated by %s", item_id, user_email)
        return {'success': True}
    except Exception as e:
        logger.exception("update_inventory_item error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def sell_inventory(item_id, contract_number, selling_price, sale_date=None,
                   token_or_email=None):
    """
    Record the sale of an inventory item (mark as sold).
    Only items with status 'in_stock' can be sold.
    COGS = Landed Cost (purchase_cost + import_costs_total = total_cost).

    Creates two journal entries:
    1) DR COGS (5000), CR Inventory (1200) — for total_cost (landed cost)
    2) DR Accounts Receivable (1100), CR Sales Revenue (4000) — for selling_price
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error

    selling_price = _round2(selling_price)
    if selling_price <= 0:
        return {'success': False, 'message': 'Selling price must be greater than zero'}
    if not contract_number:
        return {'success': False, 'message': 'Contract number is required'}

    try:
        row = app_tables.inventory.get(id=item_id)
        if not row:
            return {'success': False, 'message': 'Inventory item not found'}
        if row.get('status') == 'sold':
            return {'success': False, 'message': 'Item is already sold'}
        if row.get('status') == 'in_transit':
            return {'success': False, 'message': 'Item is still in transit. Receive it first before selling.'}

        # Landed cost = purchase_cost + import_costs_total
        total_cost = _round2(row.get('total_cost', 0))
        sale_day = _safe_date(sale_date) or date.today()

        # Entry 1: Record cost of goods sold (COGS = Landed Cost)
        if total_cost > 0:
            cogs_entries = [
                {'account_code': '5000', 'debit': total_cost, 'credit': 0},
                {'account_code': '1200', 'debit': 0, 'credit': total_cost},
            ]
            cogs_result = post_journal_entry(
                sale_day, cogs_entries,
                f"COGS for {row.get('machine_code', item_id)} — contract {contract_number}",
                'sales_invoice', item_id, user_email,
            )
            if not cogs_result.get('success'):
                return cogs_result

        # Entry 2: Record sales revenue
        sales_entries = [
            {'account_code': '1100', 'debit': selling_price, 'credit': 0},
            {'account_code': '4000', 'debit': 0, 'credit': selling_price},
        ]
        sales_result = post_journal_entry(
            sale_day, sales_entries,
            f"Sale of {row.get('machine_code', item_id)} — contract {contract_number}",
            'sales_invoice', item_id, user_email,
        )
        if not sales_result.get('success'):
            return sales_result

        gross_profit = _round2(selling_price - total_cost)
        margin = _round2((gross_profit / selling_price * 100) if selling_price else 0)

        row.update(
            contract_number=_safe_str(contract_number),
            selling_price=selling_price,
            status='sold',
            updated_at=get_utc_now(),
        )
        logger.info("Inventory %s sold to contract %s (revenue %.2f, COGS %.2f, profit %.2f) by %s",
                     item_id, contract_number, selling_price, total_cost, gross_profit, user_email)
        return {
            'success': True,
            'gross_profit': gross_profit,
            'margin_pct': margin,
            'landed_cost': total_cost,
            'revenue': selling_price,
        }
    except Exception as e:
        logger.exception("sell_inventory error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def link_inventory_to_contract(item_id, contract_number, selling_price, token_or_email=None):
    """
    Backward-compatible alias for sell_inventory.
    Link an inventory item to a sales contract (mark as sold).
    """
    return sell_inventory(item_id, contract_number, selling_price, token_or_email=token_or_email)


# ===========================================================================
# 8. FINANCIAL REPORTS
# ===========================================================================

def _get_all_balances(as_of_date=None):
    """
    Internal helper: compute balances for all accounts up to as_of_date.
    Returns dict: {account_code: {'debit': ..., 'credit': ..., 'balance': ..., 'type': ...}}
    """
    cutoff = _safe_date(as_of_date)
    accounts = {}

    # Load chart of accounts
    for acct in app_tables.chart_of_accounts.search(is_active=True):
        code = acct.get('code')
        accounts[code] = {
            'code': code,
            'name_en': acct.get('name_en', ''),
            'name_ar': acct.get('name_ar', ''),
            'type': acct.get('account_type', ''),
            'total_debit': 0.0,
            'total_credit': 0.0,
            'balance': 0.0,
        }

    # Sum ledger entries (iterate, don't load all into memory)
    try:
        for entry in app_tables.ledger.search():
            code = entry.get('account_code')
            if code not in accounts:
                continue
            row_date = entry.get('date')
            if isinstance(row_date, datetime):
                row_date = row_date.date()
            if cutoff and row_date and row_date > cutoff:
                continue
            accounts[code]['total_debit'] += _round2(entry.get('debit', 0))
            accounts[code]['total_credit'] += _round2(entry.get('credit', 0))
    except Exception as e:
        logger.warning("_get_all_balances ledger scan error: %s", e)

    # Calculate balances based on account type
    for code, info in accounts.items():
        d = info['total_debit']
        c = info['total_credit']
        if info['type'] in ('asset', 'expense'):
            info['balance'] = _round2(d - c)
        else:
            info['balance'] = _round2(c - d)
        info['total_debit'] = _round2(d)
        info['total_credit'] = _round2(c)

    return accounts


@anvil.server.callable
def get_trial_balance(as_of_date=None, token_or_email=None):
    """
    Generate trial balance as of a given date.
    Returns list of accounts with debit/credit columns that should balance.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        accounts = _get_all_balances(as_of_date)
        rows = []
        total_debit = 0.0
        total_credit = 0.0

        for code in sorted(accounts.keys()):
            info = accounts[code]
            if info['total_debit'] == 0 and info['total_credit'] == 0:
                continue  # Skip zero-activity accounts
            bal = info['balance']
            # In trial balance, show debit/credit balance columns
            if info['type'] in ('asset', 'expense'):
                tb_debit = bal if bal >= 0 else 0
                tb_credit = abs(bal) if bal < 0 else 0
            else:
                tb_credit = bal if bal >= 0 else 0
                tb_debit = abs(bal) if bal < 0 else 0

            rows.append({
                'code': code,
                'name_en': info['name_en'],
                'name_ar': info['name_ar'],
                'type': info['type'],
                'debit': _round2(tb_debit),
                'credit': _round2(tb_credit),
            })
            total_debit += tb_debit
            total_credit += tb_credit

        return {
            'success': True,
            'rows': rows,
            'total_debit': _round2(total_debit),
            'total_credit': _round2(total_credit),
            'is_balanced': abs(total_debit - total_credit) < 0.01,
            'as_of_date': as_of_date,
        }
    except Exception as e:
        logger.exception("get_trial_balance error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_income_statement(date_from, date_to, token_or_email=None):
    """
    Generate income statement (Profit & Loss) for a period.
    Revenue accounts (4xxx) minus Expense accounts (5xxx, 6xxx).
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    if not date_from or not date_to:
        return {'success': False, 'message': 'Both date_from and date_to are required'}

    try:
        d_from = _safe_date(date_from)
        d_to = _safe_date(date_to)

        # Aggregate by account for the period
        acct_totals = {}
        for entry in app_tables.ledger.search():
            row_date = entry.get('date')
            if isinstance(row_date, datetime):
                row_date = row_date.date()
            if row_date is None:
                continue
            if row_date < d_from or row_date > d_to:
                continue
            code = entry.get('account_code', '')
            if code not in acct_totals:
                acct_totals[code] = {'debit': 0.0, 'credit': 0.0}
            acct_totals[code]['debit'] += _round2(entry.get('debit', 0))
            acct_totals[code]['credit'] += _round2(entry.get('credit', 0))

        # Load account metadata
        acct_meta = {}
        for acct in app_tables.chart_of_accounts.search(is_active=True):
            acct_meta[acct.get('code')] = {
                'name_en': acct.get('name_en', ''),
                'name_ar': acct.get('name_ar', ''),
                'type': acct.get('account_type', ''),
            }

        revenue_items = []
        total_revenue = 0.0
        cogs_items = []
        total_cogs = 0.0
        expense_items = []
        total_expenses = 0.0

        for code, totals in sorted(acct_totals.items()):
            meta = acct_meta.get(code, {})
            acct_type = meta.get('type', '')
            d = totals['debit']
            c = totals['credit']

            if acct_type == 'revenue':
                bal = _round2(c - d)
                if bal != 0:
                    revenue_items.append({
                        'code': code, 'name_en': meta.get('name_en', ''),
                        'name_ar': meta.get('name_ar', ''), 'amount': bal,
                    })
                    total_revenue += bal
            elif acct_type == 'expense':
                bal = _round2(d - c)
                if bal != 0:
                    # Separate COGS (5xxx) from operating expenses (6xxx)
                    if code.startswith('5'):
                        cogs_items.append({
                            'code': code, 'name_en': meta.get('name_en', ''),
                            'name_ar': meta.get('name_ar', ''), 'amount': bal,
                        })
                        total_cogs += bal
                    else:
                        expense_items.append({
                            'code': code, 'name_en': meta.get('name_en', ''),
                            'name_ar': meta.get('name_ar', ''), 'amount': bal,
                        })
                        total_expenses += bal

        gross_profit = _round2(total_revenue - total_cogs)
        net_profit = _round2(gross_profit - total_expenses)

        return {
            'success': True,
            'date_from': str(d_from),
            'date_to': str(d_to),
            'revenue': {'items': revenue_items, 'total': _round2(total_revenue)},
            'cogs': {'items': cogs_items, 'total': _round2(total_cogs)},
            'gross_profit': gross_profit,
            'expenses': {'items': expense_items, 'total': _round2(total_expenses)},
            'net_profit': net_profit,
        }
    except Exception as e:
        logger.exception("get_income_statement error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_balance_sheet(as_of_date, token_or_email=None):
    """
    Generate balance sheet as of a given date.
    Assets = Liabilities + Equity (+ Retained Earnings from P&L)
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    if not as_of_date:
        return {'success': False, 'message': 'as_of_date is required'}

    try:
        accounts = _get_all_balances(as_of_date)
        asset_items = []
        total_assets = 0.0
        liability_items = []
        total_liabilities = 0.0
        equity_items = []
        total_equity = 0.0

        # Calculate retained earnings (revenue - expenses up to as_of_date)
        retained = 0.0

        for code in sorted(accounts.keys()):
            info = accounts[code]
            bal = info['balance']
            if bal == 0 and info['total_debit'] == 0 and info['total_credit'] == 0:
                continue

            item = {
                'code': code,
                'name_en': info['name_en'],
                'name_ar': info['name_ar'],
                'balance': bal,
            }

            if info['type'] == 'asset':
                asset_items.append(item)
                total_assets += bal
            elif info['type'] == 'liability':
                liability_items.append(item)
                total_liabilities += bal
            elif info['type'] == 'equity':
                equity_items.append(item)
                total_equity += bal
            elif info['type'] == 'revenue':
                retained += bal  # Revenue increases retained earnings
            elif info['type'] == 'expense':
                retained -= bal  # Expenses decrease retained earnings

        # Add retained earnings to equity
        retained = _round2(retained)
        if retained != 0:
            equity_items.append({
                'code': 'RE',
                'name_en': 'Current Period Earnings',
                'name_ar': 'ارباح الفترة الحالية',
                'balance': retained,
            })
            total_equity += retained

        total_liabilities_equity = _round2(total_liabilities + total_equity)

        return {
            'success': True,
            'as_of_date': str(_safe_date(as_of_date)),
            'assets': {'items': asset_items, 'total': _round2(total_assets)},
            'liabilities': {'items': liability_items, 'total': _round2(total_liabilities)},
            'equity': {'items': equity_items, 'total': _round2(total_equity)},
            'total_liabilities_equity': total_liabilities_equity,
            'is_balanced': abs(total_assets - total_liabilities_equity) < 0.01,
        }
    except Exception as e:
        logger.exception("get_balance_sheet error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_contract_profitability(contract_number=None, token_or_email=None):
    """
    PART 4: Detailed profitability report per contract.
    For each contract:
      - Purchase Cost (FOB + Cylinders)
      - Import Expenses breakdown (shipping, customs, etc.)
      - Total Landed Cost = Purchase Cost + Import Expenses
      - Sale Revenue
      - Gross Profit = Revenue - Landed Cost
    VAT does NOT reduce profit (goes to liability account 2100).
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        if contract_number:
            items = list(app_tables.inventory.search(contract_number=contract_number))
            if not items:
                # Also check unsold items that were created for this contract
                items = list(app_tables.inventory.search(machine_code=contract_number))
        else:
            items = list(app_tables.inventory.search(status='sold'))

        results = []
        grand_cost = 0.0
        grand_revenue = 0.0
        grand_import = 0.0

        for item in items:
            purchase_cost = _round2(item.get('purchase_cost', 0))
            import_total = _round2(item.get('import_costs_total', 0))
            total_cost = _round2(item.get('total_cost', 0))
            selling_price = _round2(item.get('selling_price', 0))
            gross_profit = _round2(selling_price - total_cost)
            margin = _round2((gross_profit / selling_price * 100) if selling_price else 0)

            # Get detailed import cost breakdown
            import_breakdown = []
            pi_id = item.get('purchase_invoice_id')
            if pi_id:
                for ic in app_tables.import_costs.search(purchase_invoice_id=pi_id):
                    import_breakdown.append({
                        'type': ic.get('cost_type', ''),
                        'description': ic.get('description', ''),
                        'amount': _round2(ic.get('amount', 0)),
                        'date': ic.get('date').isoformat() if ic.get('date') else '',
                        'payment_account': ic.get('payment_account', ''),
                    })

            # Get tax info from purchase invoice
            tax_amount = 0.0
            if pi_id:
                pi = app_tables.purchase_invoices.get(id=pi_id)
                if pi:
                    tax_amount = _round2(pi.get('tax_amount', 0))

            results.append({
                'machine_code': item.get('machine_code', ''),
                'description': item.get('description', ''),
                'contract_number': item.get('contract_number', ''),
                'status': item.get('status', ''),
                'purchase_cost': purchase_cost,
                'import_costs': import_total,
                'import_breakdown': import_breakdown,
                'tax_amount': tax_amount,
                'total_landed_cost': total_cost,
                'selling_price': selling_price,
                'gross_profit': gross_profit,
                'margin_pct': margin,
            })
            grand_cost += total_cost
            grand_revenue += selling_price
            grand_import += import_total

        grand_profit = _round2(grand_revenue - grand_cost)
        grand_margin = _round2((grand_profit / grand_revenue * 100) if grand_revenue else 0)

        return {
            'success': True,
            'contracts': results,
            'summary': {
                'total_purchase_cost': _round2(grand_cost - grand_import),
                'total_import_costs': _round2(grand_import),
                'total_landed_cost': _round2(grand_cost),
                'total_revenue': _round2(grand_revenue),
                'total_profit': grand_profit,
                'overall_margin_pct': grand_margin,
            },
        }
    except Exception as e:
        logger.exception("get_contract_profitability error")
        return {'success': False, 'message': str(e)}


# ===========================================================================
# 10. MISSING CALLABLES (client-server alignment)
# ===========================================================================

@anvil.server.callable
def delete_expense(expense_id, token_or_email=None):
    """Delete an expense record."""
    is_valid, user_email, error = _require_permission(token_or_email, 'delete')
    if not is_valid:
        return error
    try:
        row = app_tables.expenses.get(id=expense_id)
        if not row:
            return {'success': False, 'message': 'Expense not found'}
        row.update(status='cancelled', updated_at=get_utc_now())
        logger.info("Expense %s cancelled by %s", expense_id, user_email)
        return {'success': True}
    except Exception as e:
        logger.exception("delete_expense error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def delete_inventory_item(item_id, token_or_email=None):
    """Delete an inventory item (only if not sold)."""
    is_valid, user_email, error = _require_permission(token_or_email, 'delete')
    if not is_valid:
        return error
    try:
        row = app_tables.inventory.get(id=item_id)
        if not row:
            return {'success': False, 'message': 'Inventory item not found'}
        if row.get('status') == 'sold':
            return {'success': False, 'message': 'Cannot delete a sold item'}
        row.delete()
        logger.info("Inventory item %s deleted by %s", item_id, user_email)
        return {'success': True}
    except Exception as e:
        logger.exception("delete_inventory_item error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_landed_cost(purchase_invoice_id=None, contract_number=None, token_or_email=None):
    """
    Calculate landed cost for a specific purchase invoice or contract.
    Landed Cost = FOB + Cylinders + All Import Expenses
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        # Find the purchase invoice
        pi = None
        if purchase_invoice_id:
            pi = app_tables.purchase_invoices.get(id=purchase_invoice_id)
        elif contract_number:
            pi = app_tables.purchase_invoices.get(contract_number=contract_number)

        if not pi:
            return {'success': False, 'message': 'Purchase invoice not found'}

        pi_id = pi.get('id')
        subtotal = _round2(pi.get('subtotal', 0))

        # Sum all import costs
        import_costs = list(app_tables.import_costs.search(purchase_invoice_id=pi_id))
        import_total = _round2(sum(_round2(ic.get('amount', 0)) for ic in import_costs))

        landed_cost = _round2(subtotal + import_total)

        breakdown = {
            'purchase_cost': subtotal,
            'import_costs': {},
            'import_total': import_total,
            'landed_cost': landed_cost,
        }
        for ic in import_costs:
            ct = ic.get('cost_type', 'other')
            breakdown['import_costs'].setdefault(ct, 0.0)
            breakdown['import_costs'][ct] = _round2(breakdown['import_costs'][ct] + _round2(ic.get('amount', 0)))

        return {'success': True, **breakdown}
    except Exception as e:
        logger.exception("get_landed_cost error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_contracts_list_simple(token_or_email=None):
    """Return simple list of contracts for dropdown/selection."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        contracts = []
        for r in app_tables.quotations.search(is_deleted=False):
            contract_num = r.get('Contract#') or r.get('contract_number')
            if not contract_num:
                continue
            contracts.append({
                'contract_number': str(contract_num),
                'client_name': _safe_str(r.get('Client Name', '')),
                'quotation_number': str(r.get('Quotation#', '')),
            })
        return {'success': True, 'contracts': contracts}
    except Exception as e:
        logger.exception("get_contracts_list_simple error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def update_purchase_invoice(invoice_id, data, token_or_email=None):
    """Update a draft purchase invoice."""
    is_valid, user_email, error = _require_permission(token_or_email, 'edit')
    if not is_valid:
        return error
    try:
        row = app_tables.purchase_invoices.get(id=invoice_id)
        if not row:
            return {'success': False, 'message': 'Purchase invoice not found'}
        if row.get('status') != 'draft':
            return {'success': False, 'message': 'Only draft invoices can be edited'}

        updates = {}
        if 'supplier_id' in data:
            updates['supplier_id'] = _safe_str(data['supplier_id'])
        if 'date' in data:
            updates['date'] = _safe_date(data['date']) or row.get('date')
        if 'due_date' in data:
            updates['due_date'] = _safe_date(data['due_date'])
        if 'notes' in data:
            updates['notes'] = _safe_str(data['notes'])
        if 'machine_code' in data:
            updates['machine_code'] = _safe_str(data['machine_code'])
        if 'items' in data:
            items = data['items']
            subtotal = 0.0
            for item in items:
                line_total = _round2(item.get('total', 0))
                if line_total == 0:
                    qty = _round2(item.get('quantity', 0))
                    up = _round2(item.get('unit_price', 0))
                    line_total = _round2(qty * up)
                    item['total'] = line_total
                subtotal += line_total
            tax_amount = _round2(data.get('tax_amount', row.get('tax_amount', 0)))
            updates['items_json'] = json.dumps(items, ensure_ascii=False, default=str)
            updates['subtotal'] = _round2(subtotal)
            updates['tax_amount'] = tax_amount
            updates['total'] = _round2(subtotal + tax_amount)

        updates['updated_at'] = get_utc_now()
        row.update(**updates)
        logger.info("Purchase invoice %s updated by %s", invoice_id, user_email)
        return {'success': True}
    except Exception as e:
        logger.exception("update_purchase_invoice error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def delete_purchase_invoice(invoice_id, token_or_email=None):
    """Delete a draft purchase invoice."""
    is_valid, user_email, error = _require_permission(token_or_email, 'delete')
    if not is_valid:
        return error
    try:
        row = app_tables.purchase_invoices.get(id=invoice_id)
        if not row:
            return {'success': False, 'message': 'Purchase invoice not found'}
        if row.get('status') != 'draft':
            return {'success': False, 'message': 'Only draft invoices can be deleted'}
        row.delete()
        logger.info("Purchase invoice %s deleted by %s", invoice_id, user_email)
        return {'success': True}
    except Exception as e:
        logger.exception("delete_purchase_invoice error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def record_invoice_payment(invoice_id, amount, method='cash', notes='', token_or_email=None):
    """Record payment for a purchase invoice (alias for record_supplier_payment)."""
    payment_date = str(date.today())
    return record_supplier_payment(invoice_id, amount, method, payment_date, token_or_email)


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
        return {'success': True, 'suppliers': suppliers}
    except Exception as e:
        logger.exception("get_suppliers_list_simple error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_invoice_details(invoice_id, token_or_email=None):
    """Get detailed purchase invoice with import costs."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        row = app_tables.purchase_invoices.get(id=invoice_id)
        if not row:
            return {'success': False, 'message': 'Purchase invoice not found'}

        d = _row_to_dict(row, PURCHASE_INVOICE_COLS)
        try:
            d['items'] = json.loads(d.get('items_json') or '[]')
        except (json.JSONDecodeError, TypeError):
            d['items'] = []

        # Get import costs
        import_costs = []
        try:
            for ic in app_tables.import_costs.search(purchase_invoice_id=invoice_id):
                import_costs.append(_row_to_dict(ic, IMPORT_COST_COLS))
        except Exception as _e:
            logger.debug("Suppressed: %s", _e)
        d['import_costs'] = import_costs

        # Get supplier name
        try:
            supplier = app_tables.suppliers.get(id=d.get('supplier_id'))
            d['supplier_name'] = _safe_str(supplier.get('name', '')) if supplier else ''
        except Exception:
            d['supplier_name'] = ''

        return {'success': True, 'invoice': d}
    except Exception as e:
        logger.exception("get_invoice_details error")
        return {'success': False, 'message': str(e)}

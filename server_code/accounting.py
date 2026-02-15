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

try:
    from . import pdf_reports
except ImportError:
    import pdf_reports

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
        try:
            val = row.get(col)
        except Exception:
            val = None  # Column may not exist yet
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
    ('1210', 'Inventory in Transit', 'مخزون في الطريق', 'asset',    '1200'),
    # Liabilities
    ('2000', 'Accounts Payable',   'ذمم دائنة',         'liability', None),
    ('2100', 'VAT Payable',         'ضريبة مخرجات مستحقة', 'liability', None),   # Output VAT (sales)
    ('2110', 'VAT Input Recoverable', 'ضريبة مدخلات قابلة للاسترداد', 'asset', None),  # Input VAT (purchases)
    # Equity
    ('3000', "Owner's Equity",     'حقوق الملكية',      'equity',   None),
    ('3100', 'Retained Earnings',  'أرباح محتجزة',      'equity',   None),
    # Revenue
    ('4000', 'Sales Revenue',      'إيرادات المبيعات',  'revenue',  None),
    ('4100', 'Other Revenue',      'إيرادات أخرى',      'revenue',  None),
    ('4110', 'Exchange Gain',      'أرباح فروق العملة',  'revenue',  '4100'),
    # COGS / Import
    ('5000', 'Cost of Goods Sold', 'تكلفة البضاعة المباعة', 'expense', None),
    # 5100 DEPRECATED for new posting: import costs post to 1200 (Inventory) only. Kept for migration reclassification.
    ('5100', 'Import Costs',       'تكاليف الاستيراد',  'expense',  None),
    # Operating Expenses
    ('6000', 'Rent',               'الإيجار',           'expense',  None),
    ('6010', 'Utilities',          'المرافق',           'expense',  None),
    ('6020', 'Salaries',           'الرواتب',           'expense',  None),
    ('6030', 'Office Supplies',    'مستلزمات مكتبية',   'expense',  None),
    ('6040', 'Travel',             'السفر',             'expense',  None),
    ('6050', 'Maintenance',        'الصيانة',           'expense',  None),
    ('6090', 'Other Expenses',     'مصروفات أخرى',      'expense',  None),
    ('6110', 'Exchange Loss',      'خسائر فروق العملة',  'expense',  None),
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


def _get_rate_to_egp(currency_code):
    """Return exchange rate to EGP for the given currency. EGP or missing => 1.0."""
    if not currency_code or _safe_str(currency_code).upper() == 'EGP':
        return 1.0
    try:
        r = app_tables.currency_exchange_rates.get(currency_code=_safe_str(currency_code).upper())
        if r and r.get('rate_to_egp'):
            return _round2(float(r.get('rate_to_egp', 1)))
    except Exception:
        pass
    return 1.0


# ---------------------------------------------------------------------------
# EGP-ONLY LEDGER: Currency conversion (raises if rate missing for non-EGP)
# ---------------------------------------------------------------------------
def convert_to_egp(amount, currency_code, exchange_rate=None):
    """
    Convert amount to EGP. All ledger entries MUST be in EGP.

    Rules:
    - If currency is EGP (or missing/blank) → return amount unchanged.
    - If exchange_rate is provided and > 0 → use it (rate = EGP per 1 unit of currency).
    - Else fetch from currency_exchange_rates table.
    - If rate missing or <= 0 for non-EGP → raise ValueError (callers return error dict).

    Returns: float (amount in EGP, rounded to 2 decimals).
    """
    amount = _round2(amount)
    code = _safe_str(currency_code or 'EGP').upper()
    if not code or code == 'EGP':
        return amount
    if exchange_rate is not None and float(exchange_rate) > 0:
        return _round2(amount * _round2(float(exchange_rate)))
    rate = _get_rate_to_egp(code)
    if rate <= 0:
        raise ValueError(f"Exchange rate for {code} is missing or invalid. Ledger is EGP-only.")
    return _round2(amount * rate)


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
# AUDIT: EGP-ONLY LEDGER & JOURNAL INTEGRITY (see convert_to_egp, post_* flows)
# ===========================================================================
# post_purchase_invoice: Amounts converted to EGP via invoice exchange_rate or stored EGP.
#   Duplicate post prevented (ledger ref_type=purchase_invoice, ref_id=invoice_id).
#   VAT on purchases -> 2110 (VAT Input Recoverable). Journal balanced.
# add_import_cost: amount converted to EGP (currency_code, exchange_rate) before post & save.
# record_supplier_payment: Converts to EGP; balanced.
# record_customer_collection: Converts to EGP; balanced.
# create_contract_purchase: USD->EGP at entry; posts EGP only.
# sell_inventory: total_cost & selling_price assumed EGP; balanced.
# add_expense: Optional currency; converted to EGP before post.
# Account 5100 (Import Costs): DEPRECATED for new posting; import costs post to 1200 or 1210.
# TRANSIT MODEL: New post_purchase_invoice posts to 1210 (Inventory in Transit). When received,
# move_purchase_to_inventory moves 1210 → 1200. import costs: DR 1210 if not received, DR 1200 if received.
# purchase_invoices table: add column inventory_moved (boolean, default False). False = in transit, True = moved to inventory.
# Legacy: Invoices already posted to 1200 are NOT auto-migrated; they remain as-is. Only new postings use 1210.
# ===========================================================================

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


def _ensure_vat_accounts():
    """Ensure VAT accounts 2100 (Output) and 2110 (Input) exist. Auto-create if missing."""
    for code, name_en, name_ar, acct_type, parent in [
        ('2100', 'VAT Payable', 'ضريبة مخرجات مستحقة', 'liability', None),
        ('2110', 'VAT Input Recoverable', 'ضريبة مدخلات قابلة للاسترداد', 'asset', None),
    ]:
        if app_tables.chart_of_accounts.get(code=code):
            continue
        try:
            app_tables.chart_of_accounts.add_row(
                code=code, name_en=name_en, name_ar=name_ar,
                account_type=acct_type, parent_code=parent,
                is_active=True, created_at=get_utc_now(),
            )
            logger.info("VAT account %s auto-created", code)
        except Exception as e:
            logger.warning("Could not create account %s: %s", code, e)


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
        One of: sales_invoice, purchase_invoice, expense, payment, journal,
        import_cost, import_cost_migration, customer_collection.
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
        
        # Add date filtering to search_kwargs if present
        if d_from or d_to:
            import anvil.tables.query as q
            date_constraints = []
            if d_from:
                date_constraints.append(q.greater_than_or_equal_to(d_from))
            if d_to:
                date_constraints.append(q.less_than_or_equal_to(d_to))
            
            if len(date_constraints) == 1:
                search_kwargs['date'] = date_constraints[0]
            elif len(date_constraints) > 1:
                search_kwargs['date'] = q.all_of(*date_constraints)

        results = []
        for r in app_tables.ledger.search(**search_kwargs):
            results.append(_row_to_dict(r, LEDGER_COLS))

        results.sort(key=lambda x: (x.get('date', ''), x.get('created_at', '')))
        return {'success': True, 'data': results, 'count': len(results)}
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
        import anvil.tables.query as q
        # Filter at DB level
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
        # Iterating
        for r in rows:
            results.append(_row_to_dict(r, SUPPLIER_COLS))
            
        results.sort(key=lambda s: s.get('name', ''))
        return {'success': True, 'data': results, 'count': len(results)}
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
    'machine_code', 'contract_number', 'machine_config_json',
    'created_by', 'created_at', 'updated_at',
    'currency_code', 'total_egp', 'supplier_amount_egp', 'exchange_rate_usd_to_egp', 'original_amount',
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


def _register_posted_purchase_invoice(invoice_id, user_email):
    """
    DB-level duplicate protection: record that this invoice is being posted.
    Returns True if registered (or registry table not present); False if already posted.
    """
    try:
        tbl = app_tables.posted_purchase_invoice_ids
    except AttributeError:
        return True
    try:
        existing = list(tbl.search(invoice_id=invoice_id))
        if existing:
            return False
        tbl.add_row(invoice_id=invoice_id, posted_at=get_utc_now(), created_by=_safe_str(user_email))
        return True
    except Exception as e:
        err = str(e).lower()
        if 'unique' in err or 'duplicate' in err or 'constraint' in err:
            return False
        logger.warning("posted_purchase_invoice_ids register: %s", e)
        return True


def _unregister_posted_purchase_invoice(invoice_id):
    """Remove registry entry on rollback (e.g. post_journal_entry failed)."""
    try:
        for r in app_tables.posted_purchase_invoice_ids.search(invoice_id=invoice_id):
            r.delete()
    except Exception:
        pass


@anvil.server.callable
def get_purchase_invoices(status=None, search='', token_or_email=None):
    """Return purchase invoices, optionally filtered by status and search."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        import anvil.tables.query as q
        # Filter at DB level when status is provided, stream instead of list()
        search_kwargs = {}
        if status:
            search_kwargs['status'] = status
        
        search_lower = _safe_str(search).strip().lower()
        search_query = None
        if search_lower:
             # Search invoice_number, supplier_id (exact?), machine_code, notes
             search_query = q.any_of(
                invoice_number=q.ilike(f"%{search_lower}%"),
                supplier_id=q.ilike(f"%{search_lower}%"), # ID usually exact, but ilike matches string
                machine_code=q.ilike(f"%{search_lower}%"),
                notes=q.ilike(f"%{search_lower}%")
             )

        if search_query:
            rows = app_tables.purchase_invoices.search(search_query, **search_kwargs)
        else:
            rows = app_tables.purchase_invoices.search(**search_kwargs)

        results = []
        
        for r in rows:
            # Manual filtering removed as DB does it
            # if search_lower: ... continue

            d = _row_to_dict(r, PURCHASE_INVOICE_COLS)
            # Parse items_json for convenience
            try:
                d['items'] = json.loads(d.get('items_json') or '[]')
            except (json.JSONDecodeError, TypeError):
                d['items'] = []
            # Add supplier_name for display
            try:
                supplier = app_tables.suppliers.get(id=d.get('supplier_id'))
                d['supplier_name'] = _safe_str(supplier.get('name', '')) if supplier else ''
            except Exception:
                d['supplier_name'] = ''
            # Parse machine_config_json into dict for frontend
            try:
                d['machine_config'] = json.loads(d.get('machine_config_json') or '{}')
            except (json.JSONDecodeError, TypeError):
                d['machine_config'] = {}
            # Alias paid_amount -> paid for frontend consistency
            d['paid'] = d.get('paid_amount', 0)
            # Exchange rate for payment modal (invoice in USD → EGP conversion)
            try:
                ex = r.get('exchange_rate_usd_to_egp')
                d['exchange_rate_usd_to_egp'] = _round2(float(ex)) if ex not in (None, '') else None
            except (TypeError, ValueError):
                d['exchange_rate_usd_to_egp'] = None
            results.append(d)
        results.sort(key=lambda x: x.get('date', ''), reverse=True)
        return {'success': True, 'data': results, 'count': len(results)}
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

    # Accept both 'items' and 'line_items' keys from frontend
    items = data.get('items') or data.get('line_items', [])

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
    # Supplier liability only: do NOT include import costs in invoice total (EGP-only ledger; import costs attach to inventory)
    fob_with_cyl = _round2(data.get('fob_with_cylinders', 0))
    total = _round2(fob_with_cyl + subtotal + tax_amount)
    # Currency: enforce explicit currency; no NULL so USD is never posted as EGP
    currency_code = _safe_str(data.get('currency_code') or 'EGP').strip().upper() or 'EGP'
    if data.get('original_amount') is not None and not _safe_str(data.get('currency_code') or '').strip():
        return {'success': False, 'message': 'currency_code is required when original_amount is provided.'}
    if currency_code != 'EGP':
        ex = data.get('exchange_rate_usd_to_egp') or data.get('exchange_rate')
        try:
            ex_val = float(ex) if ex not in (None, '') else 0
        except (TypeError, ValueError):
            ex_val = 0
        if not ex_val or ex_val <= 0:
            return {'success': False, 'message': 'For non-EGP invoice, exchange_rate must be set and greater than zero.'}
    inv_id = _uuid()
    inv_number = _generate_invoice_number()
    now = get_utc_now()

    # Build machine config JSON from new Calculator-style fields
    machine_config = {}
    for cfg_key in ('condition', 'machine_type', 'colors', 'machine_width',
                     'material', 'winder', 'optionals', 'cylinders',
                     'fob_standard', 'fob_with_cylinders'):
        val = data.get(cfg_key)
        if val is not None and val != '' and val != []:
            machine_config[cfg_key] = val
    machine_config_str = json.dumps(machine_config, ensure_ascii=False) if machine_config else None

    try:
        # Base row data
        row_data = dict(
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
        # Try adding machine_config_json column (may not exist yet)
        if machine_config_str:
            row_data['machine_config_json'] = machine_config_str
        # currency_code: always set (default EGP) so posting never assumes NULL = EGP
        row_data['currency_code'] = currency_code[:3]
        # Optional: exchange rate and EGP-only fields (reference; ledger posts EGP only)
        ex_rate = data.get('exchange_rate_usd_to_egp') or data.get('exchange_rate')
        if ex_rate is not None and ex_rate != '':
            try:
                row_data['exchange_rate_usd_to_egp'] = _round2(float(ex_rate))
            except (TypeError, ValueError):
                pass
        try:
            app_tables.purchase_invoices.add_row(**row_data)
        except Exception as col_err:
            err_str = str(col_err)
            row_data.pop('exchange_rate_usd_to_egp', None)
            row_data.pop('currency_code', None)
            for k in ('original_amount', 'exchange_rate', 'total_egp'):
                row_data.pop(k, None)
            if 'machine_config' in err_str:
                row_data.pop('machine_config_json', None)
            app_tables.purchase_invoices.add_row(**row_data)
        # Optional columns (reference only): currency_code (required for posting), original_amount, exchange_rate, total_egp
        try:
            inv_row = app_tables.purchase_invoices.get(id=inv_id)
            opts = {'currency_code': currency_code[:3]}
            if data.get('original_amount') is not None:
                opts['original_amount'] = _round2(float(data.get('original_amount')))
            if ex_rate:
                opts['exchange_rate'] = _round2(float(ex_rate))
            if data.get('total_egp') is not None:
                opts['total_egp'] = _round2(float(data.get('total_egp')))
            elif opts.get('exchange_rate') and opts.get('exchange_rate') > 0:
                opts['total_egp'] = _round2(total * opts['exchange_rate'])
            if opts:
                inv_row.update(**opts)
        except Exception:
            pass

        # Save import costs if provided (amount_egp + paid_amount for pay screen)
        inv_rate = ex_rate
        if inv_rate is None or _round2(float(inv_rate or 0)) <= 0:
            inv_rate = _get_rate_to_egp('USD')
        import_costs = data.get('import_costs', [])
        for ic in import_costs:
            ic_amount = _round2(ic.get('amount', 0))
            if ic_amount > 0:
                curr = _safe_str(ic.get('currency') or 'USD').upper()[:3]
                amount_egp = _round2(ic_amount * (float(inv_rate) if curr == 'USD' else 1))
                ic_row = dict(
                    id=_uuid(),
                    purchase_invoice_id=inv_id,
                    cost_type=_safe_str(ic.get('cost_type', 'other')),
                    amount=ic_amount,
                    description=_safe_str(ic.get('description', '')),
                    date=_safe_date(data.get('date')) or date.today(),
                    payment_method=_safe_str(ic.get('payment_method', 'cash')),
                    payment_account=_resolve_payment_account(ic.get('payment_method', 'cash')),
                    created_at=now,
                    amount_egp=amount_egp,
                    paid_amount=0.0,
                )
                if curr:
                    ic_row['currency'] = curr
                try:
                    app_tables.import_costs.add_row(**ic_row)
                except Exception as ic_err:
                    for k in ('currency', 'amount_egp', 'paid_amount'):
                        ic_row.pop(k, None)
                    try:
                        app_tables.import_costs.add_row(**ic_row)
                    except Exception:
                        logger.warning("Could not save import cost: %s", ic_err)

        logger.info("Purchase invoice %s created by %s", inv_number, user_email)
        return {'success': True, 'id': inv_id, 'invoice_number': inv_number}
    except Exception as e:
        logger.exception("create_purchase_invoice error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def post_purchase_invoice(invoice_id, token_or_email=None):
    """
    Post a draft purchase invoice: only the supplier (machine) portion goes to AP.
    All amounts are converted to EGP before posting (ledger is EGP-only).
    Transit model: machine not yet received → DR 1210 (Inventory in Transit), not 1200.
    Import costs are posted separately (add_import_cost → DR 1210 or 1200 per inventory_moved).
    DR 1210 Inventory in Transit — supplier cost (total minus import costs minus tax) in EGP
    DR 2110 VAT Input Recoverable — tax_amount in EGP (if exists)
    CR 2000 Accounts Payable — supplier_amount_egp (unchanged).
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

        # Prevent duplicate posting
        existing = list(app_tables.ledger.search(reference_type='purchase_invoice', reference_id=invoice_id))
        if existing:
            return {'success': False, 'message': 'This invoice has already been posted. Duplicate posting is not allowed.'}

        total = _round2(row.get('total', 0))
        tax_amount = _round2(row.get('tax_amount', 0))
        if total <= 0:
            return {'success': False, 'message': 'Invoice total must be greater than zero'}

        # EGP-only ledger: use total_egp when stored; else convert using exchange rate
        stored_total_egp = row.get('total_egp')
        try:
            stored_total_egp = _round2(float(stored_total_egp)) if stored_total_egp not in (None, '') else None
        except (TypeError, ValueError):
            stored_total_egp = None
        inv_rate = row.get('exchange_rate_usd_to_egp') or row.get('exchange_rate')
        try:
            inv_rate = float(inv_rate) if inv_rate not in (None, '') else 0
        except (TypeError, ValueError):
            inv_rate = 0
        # Require explicit currency (no silent default to EGP to avoid posting USD as EGP)
        currency_code = _safe_str(row.get('currency_code') or '').strip().upper()
        if not currency_code:
            return {'success': False, 'message': 'currency_code is required. Set currency (e.g. EGP) on the invoice before posting.'}
        if currency_code != 'EGP' and (not inv_rate or inv_rate <= 0) and (stored_total_egp is None or stored_total_egp <= 0):
            return {'success': False, 'message': 'Exchange rate required for non-EGP invoice. Set exchange_rate_usd_to_egp or total_egp.'}
        if stored_total_egp is not None and stored_total_egp > 0:
            total_egp = stored_total_egp
            tax_egp = _round2(tax_amount * (stored_total_egp / total)) if total else stored_total_egp
        elif inv_rate and inv_rate > 0:
            total_egp = convert_to_egp(total, 'USD', inv_rate)
            tax_egp = convert_to_egp(tax_amount, 'USD', inv_rate)
        else:
            total_egp = total
            tax_egp = tax_amount

        # Import costs: use amount_egp when present (new rows); else convert amount by currency (legacy)
        import_costs_total_egp = 0.0
        for ic in app_tables.import_costs.search(purchase_invoice_id=invoice_id):
            amt_egp = ic.get('amount_egp')
            if amt_egp is not None and _round2(amt_egp) > 0:
                import_costs_total_egp += _round2(amt_egp)
                continue
            amt = _round2(ic.get('amount', 0))
            if amt <= 0:
                continue
            curr = _safe_str(ic.get('currency') or ic.get('original_currency') or 'EGP').upper()
            try:
                import_costs_total_egp += convert_to_egp(amt, curr, inv_rate if curr == 'USD' else None)
            except ValueError as ve:
                return {'success': False, 'message': str(ve)}
        import_costs_total_egp = _round2(import_costs_total_egp)

        # Lock supplier liability at post time: compute once, store, use for CR 2000 only
        supplier_amount_egp = _round2(total_egp - import_costs_total_egp)
        if supplier_amount_egp <= 0:
            return {'success': False, 'message': 'Supplier amount (total minus import costs) must be greater than zero'}

        _ensure_vat_accounts()
        if not _validate_account_exists('2110'):
            return {'success': False, 'message': 'Account 2110 (VAT Input Recoverable) not found. Run seed_default_accounts or add it.'}
        if not _validate_account_exists('1210'):
            return {'success': False, 'message': 'Account 1210 (Inventory in Transit) not found. Run seed_default_accounts or add it.'}
        if not _validate_account_exists('2000'):
            return {'success': False, 'message': 'Account 2000 (Accounts Payable) not found.'}

        # DB-level duplicate protection: register before posting (fails if already posted)
        if not _register_posted_purchase_invoice(invoice_id, user_email):
            return {'success': False, 'message': 'This invoice has already been posted. Duplicate posting is not allowed.'}

        inv_date = row.get('date') or date.today()
        entries = []

        cost_to_inventory_egp = _round2(supplier_amount_egp - tax_egp)
        if cost_to_inventory_egp > 0:
            entries.append({'account_code': '1210', 'debit': cost_to_inventory_egp, 'credit': 0})
        if tax_egp > 0:
            entries.append({'account_code': '2110', 'debit': tax_egp, 'credit': 0})
        entries.append({'account_code': '2000', 'debit': 0, 'credit': supplier_amount_egp})

        inv_number = row.get('invoice_number', invoice_id)
        result = post_journal_entry(
            inv_date, entries,
            f"Purchase invoice {inv_number} posted (EGP)",
            'purchase_invoice', invoice_id, user_email,
        )
        if not result.get('success'):
            _unregister_posted_purchase_invoice(invoice_id)
            return result

        update_data = {'status': 'posted', 'updated_at': get_utc_now(), 'supplier_amount_egp': supplier_amount_egp}
        try:
            row.update(**update_data)
        except Exception as col_err:
            if 'supplier_amount_egp' in str(col_err):
                row.update(status='posted', updated_at=update_data['updated_at'])
            else:
                raise
        # inventory_moved: optional column (default False). Do not set here; legacy invoices have no column.
        try:
            row.update(inventory_moved=False)
        except Exception:
            pass
        logger.info("Purchase invoice %s posted (EGP) to 1210 by %s", inv_number, user_email)
        return {'success': True, 'transaction_id': result['transaction_id']}
    except ValueError as ve:
        return {'success': False, 'message': str(ve)}
    except Exception as e:
        logger.exception("post_purchase_invoice error")
        return {'success': False, 'message': str(e)}


def _sum_1210_balance_for_invoice(invoice_id):
    """
    Sum (debit - credit) on account 1210 for this purchase invoice = net transit balance.
    Uses balance per entry (not debit only) so reversals/adjustments are correct.
    Includes:
    - post_purchase_invoice: reference_type=purchase_invoice, reference_id=invoice_id
    - add_import_cost: reference_type=import_cost, reference_id=invoice_id (so included in first loop)
    - pay_import_cost: reference_type=import_cost_payment, reference_id=cost_id (per-cost loop)
    """
    total = 0.0
    # All 1210 entries with reference_id=invoice_id (purchase_invoice post + import_cost entries)
    for entry in app_tables.ledger.search(account_code='1210', reference_id=invoice_id):
        total += _round2(entry.get('debit', 0)) - _round2(entry.get('credit', 0))
    # pay_import_cost uses reference_id=cost_id; include those for this invoice's costs
    for ic in app_tables.import_costs.search(purchase_invoice_id=invoice_id):
        cost_id = ic.get('id')
        if not cost_id:
            continue
        for entry in app_tables.ledger.search(account_code='1210', reference_type='import_cost_payment', reference_id=cost_id):
            total += _round2(entry.get('debit', 0)) - _round2(entry.get('credit', 0))
    return _round2(total)


@anvil.server.callable
def move_purchase_to_inventory(invoice_id, token_or_email=None):
    """
    Move a posted purchase from 1210 (Inventory in Transit) to 1200 (Inventory).
    Validates: invoice status is posted, inventory_moved is False.
    total_transit_cost = sum(debit - credit) on 1210 for this invoice (purchase_invoice + import_cost + import_cost_payment refs).
    Posts: DR 1200 = total_transit_cost, CR 1210 = total_transit_cost.
    Sets purchase_invoices.inventory_moved = True.
    Idempotent: second call returns error (invoice already moved); no duplicate journal entries possible.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    try:
        row = app_tables.purchase_invoices.get(id=invoice_id)
        if not row:
            return {'success': False, 'message': 'Purchase invoice not found'}
        if row.get('status') != 'posted':
            return {'success': False, 'message': f"Invoice must be posted. Current status: '{row.get('status')}'."}
        # Idempotency: second call must return error; no duplicate JEs
        if row.get('inventory_moved'):
            return {'success': False, 'message': 'Invoice already moved to inventory. Duplicate move is not allowed.'}

        total_transit_cost = _sum_1210_balance_for_invoice(invoice_id)
        if total_transit_cost <= 0:
            return {'success': False, 'message': 'No transit balance (1210) found for this invoice. Cannot move.'}

        if not _validate_account_exists('1200'):
            return {'success': False, 'message': 'Account 1200 (Inventory) not found.'}
        if not _validate_account_exists('1210'):
            return {'success': False, 'message': 'Account 1210 (Inventory in Transit) not found.'}

        inv_date = row.get('date') or date.today()
        inv_number = row.get('invoice_number', invoice_id)
        entries = [
            {'account_code': '1200', 'debit': total_transit_cost, 'credit': 0},
            {'account_code': '1210', 'debit': 0, 'credit': total_transit_cost},
        ]
        result = post_journal_entry(
            inv_date, entries,
            f"Move to inventory: {inv_number} (transit → stock)",
            'purchase_invoice', invoice_id, user_email,
        )
        if not result.get('success'):
            return result

        try:
            row.update(inventory_moved=True, updated_at=get_utc_now())
        except Exception as col_err:
            if 'inventory_moved' in str(col_err):
                logger.warning("purchase_invoices.inventory_moved column missing: %s", col_err)
            else:
                raise

        logger.info("Purchase invoice %s moved to inventory (1200) by %s, amount %.2f EGP", inv_number, user_email, total_transit_cost)
        return {'success': True, 'transaction_id': result['transaction_id'], 'total_transit_cost': total_transit_cost}
    except Exception as e:
        logger.exception("move_purchase_to_inventory error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def create_contract_purchase(contract_number, fob_cost, cylinder_cost, supplier_id,
                             currency='USD', token_or_email=None, exchange_rate=0):
    """
    PART 1: Contract → Purchase Invoice auto-generation (New Order flow).
    When a contract is created with pricing mode "New Order", call this to:
    1) Convert FOB costs (USD) to EGP using the quotation's exchange rate
    2) Create a Purchase Invoice with separate Machine & Cylinder line items
    3) Post journal: DR 1210 (Inventory in Transit), CR Accounts Payable (2000) — in EGP
    4) Create inventory item linked to the contract
    5) Link purchase invoice back to the contract

    Args:
        fob_cost: Machine FOB cost in USD
        cylinder_cost: Cylinder cost in USD
        exchange_rate: Exchange rate from quotation (EGP per 1 USD)

    Returns: {success, invoice_id, invoice_number, inventory_id, transaction_id}
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error

    fob_cost = _round2(fob_cost)
    cylinder_cost = _round2(cylinder_cost)
    exchange_rate = float(exchange_rate or 0)

    if fob_cost <= 0:
        return {'success': False, 'message': 'تكلفة FOB للماكينة يجب أن تكون أكبر من صفر | FOB cost must be > 0'}
    if not supplier_id:
        return {'success': False, 'message': 'المورد مطلوب | Supplier is required'}
    if not contract_number:
        return {'success': False, 'message': 'رقم العقد مطلوب | Contract number is required'}
    if exchange_rate <= 0:
        return {'success': False, 'message': 'سعر الصرف يجب أن يكون أكبر من صفر | Exchange rate must be > 0'}

    try:
        # Verify supplier exists
        supplier = app_tables.suppliers.get(id=supplier_id)
        if not supplier:
            return {'success': False, 'message': 'المورد غير موجود | Supplier not found'}

        # Convert USD to EGP
        fob_cost_egp = _round2(fob_cost * exchange_rate)
        cylinder_cost_egp = _round2(cylinder_cost * exchange_rate)

        # Build line items with both USD and EGP details
        items = [{
            'description': f'Machine FOB Cost (${fob_cost:,.2f} x {exchange_rate:.2f})',
            'quantity': 1,
            'unit_price_usd': fob_cost,
            'unit_price': fob_cost_egp,
            'total': fob_cost_egp,
        }]
        if cylinder_cost > 0:
            items.append({
                'description': f'Cylinder Cost (${cylinder_cost:,.2f} x {exchange_rate:.2f})',
                'quantity': 1,
                'unit_price_usd': cylinder_cost,
                'unit_price': cylinder_cost_egp,
                'total': cylinder_cost_egp,
            })

        subtotal_egp = _round2(fob_cost_egp + cylinder_cost_egp)

        # Create purchase invoice in draft then post it
        inv_id = _uuid()
        inv_number = _generate_invoice_number()
        now = get_utc_now()
        today = date.today()

        notes_text = (
            f"Auto-generated from contract {contract_number} | "
            f"Currency: {currency} | Exchange Rate: {exchange_rate:.2f} | "
            f"Machine FOB: ${fob_cost:,.2f} | Cylinders: ${cylinder_cost:,.2f}"
        )

        app_tables.purchase_invoices.add_row(
            id=inv_id,
            invoice_number=inv_number,
            supplier_id=supplier_id,
            date=today,
            due_date=None,
            items_json=json.dumps(items, ensure_ascii=False, default=str),
            subtotal=subtotal_egp,
            tax_amount=0.0,
            total=subtotal_egp,
            paid_amount=0.0,
            status='draft',
            notes=notes_text,
            machine_code=None,
            contract_number=contract_number,
            created_by=user_email,
            created_at=now,
            updated_at=now,
        )
        try:
            inv_row0 = app_tables.purchase_invoices.get(id=inv_id)
            inv_row0.update(
                currency_code=_safe_str(currency or 'USD').upper()[:3],
                exchange_rate_usd_to_egp=_round2(exchange_rate),
                total_egp=subtotal_egp,
            )
        except Exception:
            pass

        # DB-level duplicate protection
        if not _register_posted_purchase_invoice(inv_id, user_email):
            try:
                app_tables.purchase_invoices.get(id=inv_id).delete()
            except Exception:
                pass
            return {'success': False, 'message': 'Duplicate posting not allowed.'}

        # Post the invoice immediately: Transit model — DR 1210 (Inventory in Transit), CR 2000
        if not _validate_account_exists('1210'):
            _unregister_posted_purchase_invoice(inv_id)
            try:
                app_tables.purchase_invoices.get(id=inv_id).delete()
            except Exception:
                pass
            return {'success': False, 'message': 'Account 1210 (Inventory in Transit) not found. Run seed_default_accounts.'}
        entries = [
            {'account_code': '1210', 'debit': subtotal_egp, 'credit': 0},
            {'account_code': '2000', 'debit': 0, 'credit': subtotal_egp},
        ]
        je_result = post_journal_entry(
            today, entries,
            f"Purchase from contract {contract_number} - {inv_number} (Rate: {exchange_rate:.2f})",
            'purchase_invoice', inv_id, user_email,
        )
        if not je_result.get('success'):
            _unregister_posted_purchase_invoice(inv_id)
            try:
                row = app_tables.purchase_invoices.get(id=inv_id)
                if row:
                    row.delete()
            except Exception:
                pass
            return je_result

        # Mark invoice as posted; lock supplier liability at post time
        inv_row = app_tables.purchase_invoices.get(id=inv_id)
        if inv_row:
            update_data = {'status': 'posted', 'updated_at': get_utc_now(), 'supplier_amount_egp': subtotal_egp}
            try:
                inv_row.update(**update_data)
            except Exception as col_err:
                if 'supplier_amount_egp' in str(col_err):
                    inv_row.update(status='posted', updated_at=update_data['updated_at'])
                else:
                    raise
            try:
                inv_row.update(inventory_moved=False)
            except Exception:
                pass

        # Create inventory item linked to this purchase — starts as in_transit
        inv_item_id = _uuid()
        app_tables.inventory.add_row(
            id=inv_item_id,
            machine_code=contract_number,
            description=f"Machine for contract {contract_number}",
            purchase_invoice_id=inv_id,
            contract_number=None,  # Not sold yet — will be set when sale is recorded
            purchase_cost=subtotal_egp,
            import_costs_total=0.0,
            total_cost=subtotal_egp,
            selling_price=0.0,
            status='in_transit',
            location='',
            notes=f"FOB: ${fob_cost:,.2f} = {fob_cost_egp:,.2f} EGP | Cylinders: ${cylinder_cost:,.2f} = {cylinder_cost_egp:,.2f} EGP | Rate: {exchange_rate:.2f}",
            created_at=now,
            updated_at=now,
        )

        # Update contract row with purchase_invoice_id and cost data
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

        logger.info("Contract purchase created: %s -> %s (EGP %.2f, rate %.2f) by %s",
                     contract_number, inv_number, subtotal_egp, exchange_rate, user_email)
        return {
            'success': True,
            'invoice_id': inv_id,
            'invoice_number': inv_number,
            'inventory_id': inv_item_id,
            'transaction_id': je_result['transaction_id'],
            'total_usd': _round2(fob_cost + cylinder_cost),
            'total_egp': subtotal_egp,
            'exchange_rate': exchange_rate,
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

            # Supplier balance from ledger (authoritative)
            posted_supplier = 0.0
            paid_from_ledger = 0.0
            for entry in app_tables.ledger.search(account_code='2000', reference_id=inv_id, reference_type='purchase_invoice'):
                posted_supplier += _round2(entry.get('credit', 0))
            for entry in app_tables.ledger.search(account_code='2000', reference_id=inv_id, reference_type='payment'):
                paid_from_ledger += _round2(entry.get('debit', 0))
            remaining = _round2(posted_supplier - paid_from_ledger)
            paid = paid_from_ledger

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

            # Get import costs for this invoice (use amount_egp when present)
            import_costs = []
            import_total = 0.0
            for ic in app_tables.import_costs.search(purchase_invoice_id=inv_id):
                ic_amt = _round2(ic.get('amount_egp') or ic.get('amount', 0))
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
                'landed_cost': _round2(posted_supplier + import_total) if posted_supplier else _round2((inv.get('supplier_amount_egp') or total) + import_total),
                'payment_history': payment_history,
            })

        return {'success': True, 'data': results, 'count': len(results)}
    except Exception as e:
        logger.exception("get_contract_payable_status error")
        return {'success': False, 'message': str(e)}


def _get_supplier_remaining_egp(invoice_id):
    """Return remaining AP (2000) liability for this invoice from ledger (credits - debits)."""
    posted = 0.0
    paid = 0.0
    for entry in app_tables.ledger.search(account_code='2000', reference_id=invoice_id, reference_type='purchase_invoice'):
        posted += _round2(entry.get('credit', 0))
    for entry in app_tables.ledger.search(account_code='2000', reference_id=invoice_id, reference_type='payment'):
        paid += _round2(entry.get('debit', 0))
    return _round2(posted - paid)


@anvil.server.callable
def get_supplier_remaining_egp(invoice_id, token_or_email=None):
    """Return remaining payable (EGP) for a purchase invoice from ledger. For payment modal (amount/percentage)."""
    is_valid, _, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        remaining = _get_supplier_remaining_egp(invoice_id)
        return {'success': True, 'remaining_egp': remaining}
    except Exception as e:
        logger.exception("get_supplier_remaining_egp error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def record_supplier_payment(invoice_id, amount, payment_method, payment_date,
                            currency_code='EGP', exchange_rate=None, notes='', token_or_email=None,
                            percentage=None, is_paid_in_full=False):
    """
    Record a payment against a purchase invoice. FX is recognized on EVERY payment (partial or full).

    Policy:
    1) liability_slice_egp = portion of remaining being cleared (book value).
    2) payment_egp = actual amount paid converted at payment rate.
    3) fx_diff = liability_slice_egp - payment_egp → CR 4110 (gain) or DR 6110 (loss).
    4) Post: DR 2000 = liability_slice_egp, CR Bank = payment_egp; then 4110/6110 if fx_diff != 0.

    - amount: payment amount in currency_code (actual cash paid).
    - percentage: optional; liability_slice_egp = remaining_egp * (pct/100). If amount also given, payment_egp from amount+rate.
    - is_paid_in_full: liability_slice_egp = remaining_egp (clear all). payment_egp from amount+rate.
    - exchange_rate: سعر الصرف عند الدفع (payment rate). Invoice rate used for liability_slice when paying in foreign currency by amount.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error

    amount_in = _round2(amount) if amount is not None else 0
    pct = None
    if percentage is not None:
        try:
            pct = _round2(float(percentage))
            if pct < 0 or pct > 100:
                return {'success': False, 'message': 'Percentage must be between 0 and 100'}
        except (TypeError, ValueError):
            return {'success': False, 'message': 'Invalid percentage'}

    if not is_paid_in_full and pct is None and amount_in <= 0:
        return {'success': False, 'message': 'Payment amount must be greater than zero (or use percentage / paid in full)'}

    try:
        row = app_tables.purchase_invoices.get(id=invoice_id)
        if not row:
            return {'success': False, 'message': 'Purchase invoice not found'}
        if row.get('status') in ('draft', 'cancelled'):
            return {'success': False, 'message': f"Cannot record payment for invoice with status '{row.get('status')}'"}

        remaining_egp = _get_supplier_remaining_egp(invoice_id)
        if remaining_egp <= 0:
            return {'success': False, 'message': 'No remaining balance to pay for this invoice'}
        if is_paid_in_full and amount_in <= 0:
            return {'success': False, 'message': 'For settlement in full, enter the actual payment amount'}

        currency_code = _safe_str(currency_code or 'EGP').upper()
        # Payment rate (سعر الصرف عند الدفع)
        if currency_code == 'EGP':
            payment_rate = 1.0
        else:
            payment_rate = _round2(exchange_rate) if exchange_rate is not None and float(exchange_rate or 0) > 0 else _get_rate_to_egp(currency_code)
            if payment_rate <= 0:
                return {'success': False, 'message': f'سعر صرف غير صالح لعملة {currency_code} | Invalid exchange rate for {currency_code}'}

        # FIX 2: Percentage + foreign currency — require amount (no silent EGP treatment)
        if currency_code != 'EGP' and pct is not None and amount_in <= 0:
            return {'success': False, 'message': 'Amount is required when paying in foreign currency with percentage.'}

        # Invoice rate (for liability_slice when paying in foreign currency by amount)
        try:
            invoice_rate = _round2(float(row.get('exchange_rate_usd_to_egp') or 0)) if (row.get('exchange_rate_usd_to_egp') is not None and row.get('exchange_rate_usd_to_egp') != '') else 0.0
        except (TypeError, ValueError):
            invoice_rate = 0.0
        # FIX 1: Foreign-currency payment by amount — require valid invoice rate (no 1.0 fallback)
        if currency_code != 'EGP' and pct is None and not is_paid_in_full:
            if invoice_rate <= 0:
                return {'success': False, 'message': 'Invoice exchange rate is required for foreign-currency payment by amount.'}

        # 1) liability_slice_egp = portion of remaining being cleared (book value)
        if is_paid_in_full:
            liability_slice_egp = remaining_egp
        elif pct is not None:
            liability_slice_egp = _round2(remaining_egp * (pct / 100.0))
            if liability_slice_egp <= 0:
                return {'success': False, 'message': 'Resulting payment amount is zero'}
            liability_slice_egp = min(liability_slice_egp, remaining_egp)
        else:
            # Pay by amount
            if currency_code == 'EGP':
                liability_slice_egp = _round2(amount_in)
            else:
                # Book value of this payment = amount in foreign * invoice rate
                liability_slice_egp = _round2(amount_in * invoice_rate)
            liability_slice_egp = min(liability_slice_egp, remaining_egp)
            if liability_slice_egp <= 0:
                return {'success': False, 'message': 'Payment amount must be greater than zero'}

        # 2) payment_egp = actual amount paid at payment rate
        if is_paid_in_full or (pct is not None and amount_in > 0):
            payment_egp = amount_in * payment_rate if currency_code != 'EGP' else amount_in
            payment_egp = _round2(payment_egp)
        elif pct is not None:
            payment_egp = liability_slice_egp
        else:
            payment_egp = amount_in * payment_rate if currency_code != 'EGP' else amount_in
            payment_egp = _round2(payment_egp)

        # 3) FX difference per payment
        fx_diff = _round2(liability_slice_egp - payment_egp)

        cash_account = _resolve_payment_account(payment_method)
        if not _validate_account_exists(cash_account):
            return {'success': False, 'message': f'Payment account {cash_account} not found or inactive'}
        if not _validate_account_exists('2000'):
            return {'success': False, 'message': 'Account 2000 not found'}

        parsed_date = _safe_date(payment_date) or date.today()
        desc = f"Payment for purchase invoice {row.get('invoice_number', invoice_id)}"
        if is_paid_in_full:
            desc += " (تسوية كاملة)"
        if currency_code != 'EGP':
            desc += f" — {amount_in:,.2f} {currency_code} @ {payment_rate} = {payment_egp:,.2f} EGP"
        if notes:
            desc += f" — {notes}"

        # 4) Entries: DR 2000 = liability_slice_egp, CR Bank = payment_egp; then 4110/6110 if fx_diff != 0
        entries = [
            {'account_code': '2000', 'debit': liability_slice_egp, 'credit': 0},
            {'account_code': cash_account, 'debit': 0, 'credit': payment_egp},
        ]
        if fx_diff > 0:
            if not _validate_account_exists('4110'):
                return {'success': False, 'message': 'Account 4110 (Exchange Gain) not found. Run seed_default_accounts.'}
            entries.append({'account_code': '4110', 'debit': 0, 'credit': fx_diff})
        elif fx_diff < 0:
            if not _validate_account_exists('6110'):
                return {'success': False, 'message': 'Account 6110 (Exchange Loss) not found. Run seed_default_accounts.'}
            entries.append({'account_code': '6110', 'debit': -fx_diff, 'credit': 0})

        result = post_journal_entry(
            parsed_date, entries, desc,
            'payment', invoice_id, user_email,
        )
        if not result.get('success'):
            return result

        current_paid = _round2(row.get('paid_amount', 0))
        new_paid = _round2(current_paid + liability_slice_egp)
        new_remaining = remaining_egp - liability_slice_egp
        # FIX 3: Rounding tolerance — treat residual < 0.01 as zero
        if abs(new_remaining) < 0.01:
            new_remaining = 0.0
        new_status = 'paid' if _round2(new_remaining) <= 0 else 'partial'
        row.update(paid_amount=new_paid, status=new_status, updated_at=get_utc_now())

        logger.info("Supplier payment liability_slice=%.2f payment_egp=%.2f fx_diff=%.2f for %s by %s", liability_slice_egp, payment_egp, fx_diff, row.get('invoice_number'), user_email)
        return {'success': True, 'paid_amount': new_paid, 'status': new_status, 'transaction_id': result['transaction_id'], 'amount_egp': liability_slice_egp}
    except Exception as e:
        logger.exception("record_supplier_payment error")
        return {'success': False, 'message': str(e)}


# ===========================================================================
# 5. IMPORT COSTS (EGP-only; attached to inventory; extensible types)
# ===========================================================================
IMPORT_COST_COLS = ['id', 'purchase_invoice_id', 'cost_type', 'description', 'amount', 'date',
                    'created_by', 'created_at', 'contract_number', 'payment_account', 'currency']

# Extensible: use import_cost_types table when present; else this default list
DEFAULT_IMPORT_COST_TYPES = [
    {'id': 'TAX', 'name': 'Tax', 'default_account': None, 'is_active': True},
    {'id': 'FREIGHT', 'name': 'Freight', 'default_account': None, 'is_active': True},
    {'id': 'CUSTOMS', 'name': 'Customs', 'default_account': None, 'is_active': True},
    {'id': 'FEES', 'name': 'Fees', 'default_account': None, 'is_active': True},
    {'id': 'OTHER', 'name': 'Other', 'default_account': None, 'is_active': True},
]

VALID_COST_TYPES = ('shipping', 'customs', 'insurance', 'clearance', 'transport', 'other')


def _get_import_cost_types_table():
    """Return import_cost_types table if it exists."""
    try:
        return getattr(app_tables, 'import_cost_types', None)
    except Exception:
        return None


@anvil.server.callable
def get_import_cost_types(token_or_email=None):
    """Return list of import cost types (from table or built-in). Extensible without code change."""
    is_valid, _, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        tbl = _get_import_cost_types_table()
        if tbl is not None:
            rows = list(tbl.search(is_active=True)) if hasattr(tbl, 'search') else []
            if rows:
                return {'success': True, 'types': [{'id': r.get('id'), 'name': r.get('name'), 'default_account': r.get('default_account')} for r in rows]}
        return {'success': True, 'types': [{'id': t['id'], 'name': t['name'], 'default_account': t.get('default_account')} for t in DEFAULT_IMPORT_COST_TYPES]}
    except Exception as e:
        logger.exception("get_import_cost_types error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def seed_import_cost_types(token_or_email=None):
    """Seed import_cost_types table with TAX, FREIGHT, CUSTOMS, FEES, OTHER. Idempotent."""
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    tbl = _get_import_cost_types_table()
    if tbl is None:
        return {'success': False, 'message': 'Table import_cost_types does not exist'}
    try:
        created = 0
        for t in DEFAULT_IMPORT_COST_TYPES:
            tid = t['id']
            existing = tbl.get(id=tid) if hasattr(tbl, 'get') else None
            if existing:
                continue
            try:
                tbl.add_row(id=tid, name=t['name'], default_account=t.get('default_account'), is_active=True)
                created += 1
            except Exception as col_err:
                logger.warning("seed_import_cost_types add %s: %s", tid, col_err)
        return {'success': True, 'created': created}
    except Exception as e:
        logger.exception("seed_import_cost_types error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def add_import_cost(purchase_invoice_id=None, cost_type=None, amount=None, description='',
                    cost_date=None, payment_method='cash', contract_number=None, token_or_email=None,
                    currency_code='EGP', exchange_rate=None,
                    inventory_id=None, cost_type_id=None, original_amount=None, payment_account=None):
    """
    Add an import cost attached to an inventory item (machine). EGP-only ledger.
    Transit model: if invoice.inventory_moved is False → DR 1210 (Inventory in Transit), CR payment_account.
    If invoice.inventory_moved is True → DR 1200 (Inventory), CR payment_account.
    Never post import cost to 2000. Recalculates landed cost on inventory row.
    Legacy (positional): add_import_cost(purchase_invoice_id, cost_type, amount, description=..., ...).
    New (keywords): inventory_id, cost_type_id, description, original_amount, payment_account.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error

    if original_amount is None and amount is not None:
        original_amount = amount
    if not inventory_id and not purchase_invoice_id:
        return {'success': False, 'message': 'Either inventory_id or purchase_invoice_id is required'}

    amount_in = _round2(original_amount if original_amount is not None else 0)
    if amount_in <= 0:
        return {'success': False, 'message': 'Import cost amount must be greater than zero'}

    cost_type_name = None
    if cost_type_id:
        tbl = _get_import_cost_types_table()
        if tbl and hasattr(tbl, 'get'):
            row = tbl.get(id=cost_type_id)
            if row and row.get('is_active', True):
                cost_type_name = row.get('name') or cost_type_id
            else:
                return {'success': False, 'message': f'Cost type {cost_type_id} not found or inactive'}
        else:
            cost_type_name = cost_type_id
    if not cost_type_name and cost_type:
        if cost_type not in VALID_COST_TYPES:
            return {'success': False, 'message': f'Invalid cost_type. Must be one of: {", ".join(VALID_COST_TYPES)}'}
        cost_type_name = cost_type
    if not cost_type_name:
        cost_type_name = 'other'

    # Enforce: non-EGP requires exchange rate (avoid mixed currency in ledger)
    curr = _safe_str(currency_code or 'EGP').upper()
    if curr and curr != 'EGP':
        rate = exchange_rate if exchange_rate is not None and _round2(float(exchange_rate or 0)) > 0 else _get_rate_to_egp(curr)
        if rate <= 0:
            return {'success': False, 'message': f'Exchange rate required for currency {curr}. Ledger is EGP-only.'}
    try:
        amount_egp = convert_to_egp(amount_in, currency_code or 'EGP', exchange_rate)
    except ValueError as ve:
        return {'success': False, 'message': str(ve)}

    inv_item = None
    pi_id = purchase_invoice_id
    inv_id = inventory_id

    try:
        if inv_id:
            inv_item = app_tables.inventory.get(id=inv_id)
            if not inv_item:
                return {'success': False, 'message': 'Inventory item not found'}
            if inv_item.get('status') == 'sold':
                return {'success': False, 'message': 'Cannot add import costs: machine is already sold. Use a manual COGS adjustment.'}
            pi_id = inv_item.get('purchase_invoice_id')
        else:
            inv_row = app_tables.purchase_invoices.get(id=pi_id)
            if not inv_row:
                return {'success': False, 'message': 'Purchase invoice not found'}
            if not contract_number:
                contract_number = inv_row.get('contract_number')
            inv_items = list(app_tables.inventory.search(purchase_invoice_id=pi_id))
            sold_items = [it for it in inv_items if it.get('status') == 'sold']
            if sold_items:
                return {'success': False, 'message': 'Cannot add import costs: machine is already sold.'}
            inv_item = inv_items[0] if inv_items else None
            if inv_item:
                inv_id = inv_item.get('id')

        credit_account = payment_account
        if not credit_account:
            credit_account = _resolve_payment_account(payment_method)
        if not _validate_account_exists(credit_account):
            return {'success': False, 'message': f'Payment account {credit_account} not found or inactive'}

        # Transit model: DR 1210 if not yet received, DR 1200 if already moved to inventory
        inv_row = app_tables.purchase_invoices.get(id=pi_id) if pi_id else None
        inventory_moved = bool(inv_row and inv_row.get('inventory_moved'))
        if inventory_moved:
            if not _validate_account_exists('1200'):
                return {'success': False, 'message': 'Account 1200 (Inventory) not found or inactive'}
            debit_account = '1200'
        else:
            if not _validate_account_exists('1210'):
                return {'success': False, 'message': 'Account 1210 (Inventory in Transit) not found or inactive'}
            debit_account = '1210'

        parsed_date = _safe_date(cost_date) or date.today()
        cost_id = _uuid()
        desc_text = _safe_str(description) or f"Import cost ({cost_type_name})"

        entries = [
            {'account_code': debit_account, 'debit': amount_egp, 'credit': 0},
            {'account_code': credit_account, 'debit': 0, 'credit': amount_egp},
        ]
        # reference_id=invoice_id so move_purchase_to_inventory can sum 1210 by invoice in one place
        je_result = post_journal_entry(
            parsed_date, entries,
            f"Import cost ({cost_type_name}): {desc_text}",
            'import_cost', pi_id, user_email,
        )
        if not je_result.get('success'):
            return je_result

        row_data = dict(
            id=cost_id,
            purchase_invoice_id=pi_id,
            cost_type=cost_type or cost_type_name.lower()[:20],
            description=desc_text,
            amount=amount_egp,
            date=parsed_date,
            created_by=user_email,
            created_at=get_utc_now(),
            contract_number=_safe_str(contract_number) or (inv_item.get('contract_number') if inv_item else None),
            payment_account=credit_account,
        )
        try:
            row_data['currency'] = 'EGP'
        except Exception:
            pass
        if inv_id:
            try:
                row_data['inventory_id'] = inv_id
            except Exception:
                pass
        if cost_type_id:
            try:
                row_data['cost_type_id'] = cost_type_id
            except Exception:
                pass
        try:
            row_data['original_currency'] = _safe_str(currency_code or 'EGP').upper()
            row_data['original_amount'] = amount_in
            row_data['exchange_rate'] = _round2(exchange_rate) if exchange_rate is not None else (exchange_rate or _get_rate_to_egp(currency_code or 'EGP'))
            row_data['amount_egp'] = amount_egp
        except Exception:
            pass

        try:
            app_tables.import_costs.add_row(**row_data)
        except Exception as col_err:
            err_str = str(col_err).lower()
            for key in ('currency', 'inventory_id', 'cost_type_id', 'original_currency', 'original_amount', 'exchange_rate', 'amount_egp'):
                row_data.pop(key, None)
            try:
                app_tables.import_costs.add_row(**row_data)
            except Exception:
                raise

        _update_inventory_import_totals(inventory_id=inv_id, purchase_invoice_id=pi_id)

        logger.info("Import cost %s (%.2f EGP) added by %s [DR %s, CR %s]", cost_type_name, amount_egp, user_email, debit_account, credit_account)
        return {'success': True, 'id': cost_id, 'transaction_id': je_result['transaction_id'], 'amount_egp': amount_egp}
    except ValueError as ve:
        return {'success': False, 'message': str(ve)}
    except Exception as e:
        logger.exception("add_import_cost error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_import_costs(purchase_invoice_id=None, inventory_id=None, token_or_email=None):
    """Return import costs for a purchase invoice or an inventory item. One of the IDs required."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    if not purchase_invoice_id and not inventory_id:
        return {'success': False, 'message': 'Either purchase_invoice_id or inventory_id is required'}
    try:
        if inventory_id:
            try:
                rows = list(app_tables.import_costs.search(inventory_id=inventory_id))
            except Exception:
                inv = app_tables.inventory.get(id=inventory_id)
                pi_id = inv.get('purchase_invoice_id') if inv else None
                rows = list(app_tables.import_costs.search(purchase_invoice_id=pi_id)) if pi_id else []
        else:
            rows = list(app_tables.import_costs.search(purchase_invoice_id=purchase_invoice_id))
        cols = list(IMPORT_COST_COLS) + ['amount_egp', 'original_amount', 'original_currency', 'exchange_rate', 'cost_type_id', 'inventory_id']
        costs = []
        for r in rows:
            d = _row_to_dict(r, IMPORT_COST_COLS)
            for c in cols:
                if c not in d and r.get(c) is not None:
                    d[c] = r.get(c)
            costs.append(d)
        total = _round2(sum(_round2(c.get('amount_egp') or c.get('amount', 0)) for c in costs))
        return {'success': True, 'costs': costs, 'total': total}
    except Exception as e:
        logger.exception("get_import_costs error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_import_costs_for_payment(purchase_invoice_id, token_or_email=None):
    """Return import cost rows for the Pay Import Costs screen: id, cost_type, description, amount_egp, paid_amount, remaining_egp, payment_account."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    if not purchase_invoice_id:
        return {'success': False, 'message': 'purchase_invoice_id is required'}
    try:
        inv = app_tables.purchase_invoices.get(id=purchase_invoice_id)
        if not inv:
            return {'success': False, 'message': 'Purchase invoice not found'}
        try:
            inv_rate = _round2(float(inv.get('exchange_rate_usd_to_egp') or 0)) if inv.get('exchange_rate_usd_to_egp') else _get_rate_to_egp('USD')
        except (TypeError, ValueError):
            inv_rate = _get_rate_to_egp('USD')
        if not inv_rate or inv_rate <= 0:
            inv_rate = _get_rate_to_egp('USD')
        rows = list(app_tables.import_costs.search(purchase_invoice_id=purchase_invoice_id))
        result = []
        for r in rows:
            amt_egp = r.get('amount_egp')
            if amt_egp is None or _round2(amt_egp) <= 0:
                amt = _round2(r.get('amount', 0))
                curr = _safe_str(r.get('currency') or 'EGP').upper()
                amt_egp = _round2(amt * (inv_rate if curr == 'USD' else 1))
            else:
                amt_egp = _round2(amt_egp)
            paid = _round2(r.get('paid_amount') or 0)
            remaining = _round2(amt_egp - paid)
            result.append({
                'id': r.get('id'),
                'cost_type': r.get('cost_type', ''),
                'description': _safe_str(r.get('description', '')),
                'amount_egp': amt_egp,
                'paid_amount': paid,
                'remaining_egp': remaining,
                'payment_account': r.get('payment_account') or _resolve_payment_account('cash'),
            })
        return {'success': True, 'costs': result}
    except Exception as e:
        logger.exception("get_import_costs_for_payment error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def pay_import_cost(import_cost_id, amount_egp, payment_method, payment_date, token_or_email=None):
    """
    Pay (part or all) of an import cost. Transit model: DR 1210 if invoice not yet received, DR 1200 if received. CR cash/bank.
    amount_egp: amount in EGP to pay (partial or full).
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    amount_egp = _round2(float(amount_egp or 0))
    if amount_egp <= 0:
        return {'success': False, 'message': 'Amount must be greater than zero'}
    payment_date = _safe_date(payment_date) or date.today()
    try:
        row = app_tables.import_costs.get(id=import_cost_id)
        if not row:
            return {'success': False, 'message': 'Import cost not found'}
        amt_egp = row.get('amount_egp')
        if amt_egp is None or _round2(amt_egp) <= 0:
            inv_id = row.get('purchase_invoice_id')
            inv = app_tables.purchase_invoices.get(id=inv_id) if inv_id else None
            rate = _round2(float(inv.get('exchange_rate_usd_to_egp') or 0)) if inv and inv.get('exchange_rate_usd_to_egp') else _get_rate_to_egp('USD')
            amt = _round2(row.get('amount', 0))
            curr = _safe_str(row.get('currency') or 'EGP').upper()
            amt_egp = _round2(amt * (rate if curr == 'USD' else 1))
        else:
            amt_egp = _round2(amt_egp)
        paid = _round2(row.get('paid_amount') or 0)
        remaining = _round2(amt_egp - paid)
        if amount_egp > remaining:
            return {'success': False, 'message': f'Pay amount ({amount_egp}) cannot exceed remaining ({remaining})'}
        credit_account = _resolve_payment_account(payment_method)
        if not _validate_account_exists(credit_account):
            return {'success': False, 'message': f'Payment account {credit_account} not found or inactive'}

        pi_id = row.get('purchase_invoice_id')
        inv_row = app_tables.purchase_invoices.get(id=pi_id) if pi_id else None
        inventory_moved = bool(inv_row and inv_row.get('inventory_moved'))
        if inventory_moved:
            if not _validate_account_exists('1200'):
                return {'success': False, 'message': 'Account 1200 (Inventory) not found'}
            debit_account = '1200'
        else:
            if not _validate_account_exists('1210'):
                return {'success': False, 'message': 'Account 1210 (Inventory in Transit) not found'}
            debit_account = '1210'

        cost_type_name = row.get('cost_type', 'import cost')
        desc = f"Import cost payment ({cost_type_name}): {_safe_str(row.get('description', ''))}"
        entries = [
            {'account_code': debit_account, 'debit': amount_egp, 'credit': 0},
            {'account_code': credit_account, 'debit': 0, 'credit': amount_egp},
        ]
        je_result = post_journal_entry(
            payment_date, entries, desc, 'import_cost_payment', import_cost_id, user_email,
        )
        if not je_result.get('success'):
            return je_result
        new_paid = _round2(paid + amount_egp)
        try:
            row.update(paid_amount=new_paid)
        except Exception as upd_err:
            logger.warning("Could not update import_costs.paid_amount: %s", upd_err)
        _update_inventory_import_totals(purchase_invoice_id=row.get('purchase_invoice_id'))
        logger.info("Import cost %s paid %.2f EGP by %s [DR %s, CR %s]", import_cost_id, amount_egp, user_email, debit_account, credit_account)
        return {'success': True, 'transaction_id': je_result.get('transaction_id'), 'paid_amount': new_paid}
    except Exception as e:
        logger.exception("pay_import_cost error")
        return {'success': False, 'message': str(e)}


def _update_inventory_import_totals(purchase_invoice_id=None, inventory_id=None):
    """
    Recalculate import_costs_total and total_cost (EGP). Guarantee: total_cost = purchase_cost + import_costs_total.
    Call with either purchase_invoice_id (legacy) or inventory_id (new).
    """
    try:
        if inventory_id:
            try:
                cost_rows = list(app_tables.import_costs.search(inventory_id=inventory_id))
            except Exception:
                inv_item = app_tables.inventory.get(id=inventory_id)
                purchase_invoice_id = inv_item.get('purchase_invoice_id') if inv_item else None
                cost_rows = list(app_tables.import_costs.search(purchase_invoice_id=purchase_invoice_id)) if purchase_invoice_id else []
            import_total = _round2(sum(_round2(r.get('amount_egp') or r.get('amount', 0)) for r in cost_rows))
            item = app_tables.inventory.get(id=inventory_id)
            if item:
                purchase_cost = _round2(item.get('purchase_cost', 0))
                item.update(
                    import_costs_total=import_total,
                    total_cost=_round2(purchase_cost + import_total),
                    updated_at=get_utc_now(),
                )
            return
        if purchase_invoice_id:
            cost_rows = list(app_tables.import_costs.search(purchase_invoice_id=purchase_invoice_id))
            import_total = _round2(sum(_round2(r.get('amount_egp') or r.get('amount', 0)) for r in cost_rows))
            for item in app_tables.inventory.search(purchase_invoice_id=purchase_invoice_id):
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
        return {'success': True, 'data': results, 'count': len(results), 'total_amount': total_amount}
    except Exception as e:
        logger.exception("get_expenses error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def add_expense(data, token_or_email=None):
    """
    Record an expense. Ledger is EGP-only: if data.currency is provided and not EGP,
    amount is converted to EGP before posting. Stored amount is always EGP.
    DR Expense Account (from category or account_code)
    CR Cash (1000) / Bank (1010) etc.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error

    amount_in = _round2(data.get('amount', 0))
    if amount_in <= 0:
        return {'success': False, 'message': 'Expense amount must be greater than zero'}

    currency_code = _safe_str(data.get('currency') or 'EGP').upper()
    try:
        amount_egp = convert_to_egp(amount_in, currency_code, data.get('exchange_rate'))
    except ValueError as ve:
        return {'success': False, 'message': str(ve)}

    category = _safe_str(data.get('category')).lower()
    if category and category not in VALID_EXPENSE_CATEGORIES:
        return {'success': False, 'message': f'Invalid category. Must be one of: {", ".join(VALID_EXPENSE_CATEGORIES)}'}

    payment_method = _safe_str(data.get('payment_method', 'cash')).lower()
    if payment_method not in VALID_PAYMENT_METHODS:
        return {'success': False, 'message': f'Invalid payment method. Must be one of: {", ".join(VALID_PAYMENT_METHODS)}'}

    account_code = _safe_str(data.get('account_code'))
    if not account_code:
        account_code = CATEGORY_ACCOUNT_MAP.get(category, '6090')
    if not _validate_account_exists(account_code):
        return {'success': False, 'message': f'Expense account {account_code} not found or inactive'}

    credit_account = _resolve_payment_account(payment_method)
    if not _validate_account_exists(credit_account):
        return {'success': False, 'message': f'Payment account {credit_account} not found or inactive'}

    parsed_date = _safe_date(data.get('date')) or date.today()
    expense_id = _uuid()

    entries = [
        {'account_code': account_code, 'debit': amount_egp, 'credit': 0},
        {'account_code': credit_account, 'debit': 0, 'credit': amount_egp},
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
            amount=amount_egp,
            payment_method=payment_method,
            reference=_safe_str(data.get('reference')) or None,
            account_code=account_code,
            status='posted',
            created_by=user_email,
            created_at=get_utc_now(),
        )
        logger.info("Expense %s (%.2f EGP, %s) created by %s", expense_id, amount_egp, category, user_email)
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
    'status', 'location', 'notes', 'machine_config_json', 'created_at', 'updated_at',
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


def _is_cash_bank_account_row(r):
    """Detect cash/bank accounts robustly (supports custom COA trees/codes)."""
    try:
        code = str(r.get('code', '') or '').strip()
        parent = str(r.get('parent_code', '') or '').strip()
        name_en = str(r.get('name_en', '') or '').lower()
        name_ar = str(r.get('name_ar', '') or '')
        account_type = str(r.get('account_type', '') or '').lower()

        # Common accounting structures in this app
        if code == '1000':
            return True
        if code.startswith('101'):
            return True
        if parent in ('1000', '1010') or parent.startswith('101'):
            return True

        # Fallback by naming/type for customized charts
        by_name = (
            ('cash' in name_en) or
            ('bank' in name_en) or
            ('نقد' in name_ar) or
            ('خز' in name_ar) or
            ('بنك' in name_ar)
        )
        normalized_type = account_type.replace(' ', '_').replace('-', '_')
        if by_name and normalized_type in (
            'asset', 'assets', 'current_asset', 'current_assets',
            'cash', 'bank', ''
        ):
            return True

        return False
    except Exception:
        return False


@anvil.server.callable
def get_bank_accounts(token_or_email=None):
    """Return list of cash/bank accounts for payment dropdowns."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        accounts = []
        for r in app_tables.chart_of_accounts.search():
            # بعض السجلات القديمة لا تحتوي is_active؛ نعتبرها فعّالة افتراضياً
            if r.get('is_active', True) is False:
                continue
            if not _is_cash_bank_account_row(r):
                continue
            code = str(r.get('code', '')).strip()
            if not code:
                continue
            accounts.append({
                'code': code,
                'name_en': r.get('name_en', ''),
                'name_ar': r.get('name_ar', ''),
            })
        # إذا دليل الحسابات فاضي أو مفيش نقدية/بنوك — نرجع قائمة افتراضية عشان الدروب داون ما تبقاش فاضية
        if not accounts:
            accounts = [
                {'code': '1000', 'name_en': 'Cash', 'name_ar': 'نقدية'},
                {'code': '1010', 'name_en': 'Bank', 'name_ar': 'بنك'},
            ]
        seen = set()
        deduped = []
        for a in sorted(accounts, key=lambda x: x.get('code', '')):
            c = str(a.get('code', '') or '').strip()
            if not c or c in seen:
                continue
            seen.add(c)
            deduped.append(a)
        return {'success': True, 'accounts': deduped}
    except Exception as e:
        logger.exception("get_bank_accounts error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def backfill_supplier_amount_egp(token_or_email=None):
    """
    MIGRATION: Backfill supplier_amount_egp for already-posted purchase invoices.
    For each posted invoice: supplier_amount_egp = sum(credits on account 2000
    where reference_type='purchase_invoice' and reference_id=invoice_id).
    Safe to run multiple times (idempotent). Do not break legacy invoices.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    try:
        updated = 0
        for inv in app_tables.purchase_invoices.search():
            if inv.get('status') != 'posted':
                continue
            inv_id = inv.get('id')
            if not inv_id:
                continue
            credit_sum = 0.0
            for entry in app_tables.ledger.search(
                    account_code='2000', reference_type='purchase_invoice', reference_id=inv_id):
                credit_sum += _round2(entry.get('credit', 0))
            credit_sum = _round2(credit_sum)
            if credit_sum <= 0:
                continue
            try:
                inv.update(supplier_amount_egp=credit_sum)
                updated += 1
            except Exception as col_err:
                if 'supplier_amount_egp' not in str(col_err):
                    raise
                logger.warning("Column supplier_amount_egp not present; add it to purchase_invoices. %s", col_err)
        logger.info("backfill_supplier_amount_egp: updated %d invoices", updated)
        return {'success': True, 'updated': updated}
    except Exception as e:
        logger.exception("backfill_supplier_amount_egp error")
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
            d = _row_to_dict(r, INVENTORY_COLS)
            # Parse machine_config_json into dict for frontend
            try:
                d['machine_config'] = json.loads(d.get('machine_config_json') or '{}')
            except (json.JSONDecodeError, TypeError):
                d['machine_config'] = {}
            results.append(d)
        results.sort(key=lambda x: x.get('machine_code', ''))
        return {'success': True, 'data': results, 'count': len(results)}
    except Exception as e:
        logger.exception("get_inventory error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_available_inventory_for_contract(token_or_email=None):
    """
    Return inventory items with status 'in_stock' that are NOT yet sold.
    Used in the contract form In Stock flow to pick a machine from inventory.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        rows = app_tables.inventory.search(status='in_stock')
        results = []
        for r in rows:
            results.append({
                'id': r.get('id', ''),
                'machine_code': _safe_str(r.get('machine_code')),
                'description': _safe_str(r.get('description')),
                'purchase_cost': _round2(r.get('purchase_cost', 0)),
                'import_costs_total': _round2(r.get('import_costs_total', 0)),
                'total_cost': _round2(r.get('total_cost', 0)),
                'location': _safe_str(r.get('location')),
                'notes': _safe_str(r.get('notes')),
            })
        results.sort(key=lambda x: x.get('machine_code', ''))
        return {'success': True, 'data': results, 'count': len(results)}
    except Exception as e:
        logger.exception("get_available_inventory_for_contract error")
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

    # Build machine config JSON from Calculator-style fields
    machine_config = {}
    for cfg_key in ('condition', 'machine_type', 'colors', 'machine_width',
                     'material', 'winder', 'optionals', 'cylinders',
                     'fob_standard', 'fob_with_cylinders'):
        val = data.get(cfg_key)
        if val is not None and val != '' and val != []:
            machine_config[cfg_key] = val
    machine_config_str = json.dumps(machine_config, ensure_ascii=False) if machine_config else None

    try:
        row_data = dict(
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
        # Try adding machine_config_json column (may not exist yet)
        if machine_config_str:
            row_data['machine_config_json'] = machine_config_str
        try:
            app_tables.inventory.add_row(**row_data)
        except Exception as col_err:
            # If machine_config_json column doesn't exist, retry without it
            if 'machine_config_json' in str(col_err):
                row_data.pop('machine_config_json', None)
                app_tables.inventory.add_row(**row_data)
                logger.info("machine_config_json column not found in inventory - saved item without it")
            else:
                raise

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

        # Build machine config JSON from Calculator-style fields
        machine_config = {}
        for cfg_key in ('condition', 'machine_type', 'colors', 'machine_width',
                         'material', 'winder', 'optionals', 'cylinders',
                         'fob_standard', 'fob_with_cylinders'):
            val = data.get(cfg_key)
            if val is not None and val != '' and val != []:
                machine_config[cfg_key] = val
        if machine_config:
            updates['machine_config_json'] = json.dumps(machine_config, ensure_ascii=False)

        # Recalculate total_cost if cost fields changed
        pc = updates.get('purchase_cost', _round2(row.get('purchase_cost', 0)))
        ic = updates.get('import_costs_total', _round2(row.get('import_costs_total', 0)))
        updates['total_cost'] = _round2(pc + ic)
        updates['updated_at'] = get_utc_now()

        try:
            row.update(**updates)
        except Exception as col_err:
            # If machine_config_json column doesn't exist, retry without it
            if 'machine_config_json' in str(col_err):
                updates.pop('machine_config_json', None)
                row.update(**updates)
                logger.info("machine_config_json column not found in inventory - updated item without it")
            else:
                raise

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

        # Transit model: COGS comes from 1200 only. Sale allowed only after move to inventory.
        pi_id = row.get('purchase_invoice_id')
        if pi_id:
            inv_row = app_tables.purchase_invoices.get(id=pi_id)
            if inv_row and not inv_row.get('inventory_moved'):
                transit_balance = _sum_1210_balance_for_invoice(pi_id)
                if transit_balance > 0:
                    return {'success': False, 'message': 'Machine not yet received into inventory.'}

        # Landed cost = purchase_cost + import_costs_total (both EGP)
        total_cost = _round2(row.get('total_cost', 0))
        sale_day = _safe_date(sale_date) or date.today()

        if not _validate_account_exists('5000'):
            return {'success': False, 'message': 'Account 5000 (COGS) not found or inactive'}
        if not _validate_account_exists('1200'):
            return {'success': False, 'message': 'Account 1200 (Inventory) not found or inactive'}
        if not _validate_account_exists('1100') or not _validate_account_exists('4000'):
            return {'success': False, 'message': 'Account 1100 or 4000 not found or inactive'}

        # Entry 1: Record cost of goods sold (COGS = Landed Cost)
        # Always post COGS entry even if total_cost is 0, to record inventory removal
        cogs_entries = [
            {'account_code': '5000', 'debit': total_cost, 'credit': 0},
            {'account_code': '1200', 'debit': 0, 'credit': total_cost},
        ]
        if total_cost > 0:
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

def _get_all_balances(as_of_date=None, date_from=None):
    """
    Internal helper: compute balances for all accounts.
    If date_from is given, only entries between date_from and as_of_date are included.
    If only as_of_date is given, all entries up to as_of_date are included.
    Returns dict: {account_code: {'debit': ..., 'credit': ..., 'balance': ..., 'type': ...}}
    """
    cutoff = _safe_date(as_of_date)
    start = _safe_date(date_from)
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
            if start and row_date and row_date < start:
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
def get_trial_balance(date_from=None, date_to=None, token_or_email=None):
    """
    Generate trial balance for a date range (or up to a given date).
    Client sends (date_from, date_to, auth_token).
    Returns list of accounts with debit/credit columns that should balance.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        accounts = _get_all_balances(as_of_date=date_to, date_from=date_from)
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

        # Map rows to match frontend expectations (account_name, account_id, debit, credit)
        data_rows = []
        for r in rows:
            data_rows.append({
                'account_id': r.get('code', ''),
                'account_name': r.get('name_en', '') + (' / ' + r.get('name_ar', '') if r.get('name_ar') else ''),
                'debit': r.get('debit', 0),
                'credit': r.get('credit', 0),
            })
        return {
            'success': True,
            'data': data_rows,
            'rows': rows,
            'total_debit': _round2(total_debit),
            'total_credit': _round2(total_credit),
            'is_balanced': abs(total_debit - total_credit) < 0.01,
            'date_from': date_from,
            'date_to': date_to,
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

        # Build 'data' structure matching frontend expectations
        data_obj = {
            'revenues': [{'account_name': i.get('name_en',''), 'amount': i.get('amount',0)} for i in revenue_items],
            'expenses': [{'account_name': i.get('name_en',''), 'amount': i.get('amount',0)} for i in (cogs_items + expense_items)],
            'total_revenue': _round2(total_revenue),
            'total_expenses': _round2(total_cogs + total_expenses),
            'net_income': net_profit,
        }
        return {
            'success': True,
            'data': data_obj,
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

        # Build 'data' structure matching frontend expectations
        data_obj = {
            'assets': [{'account_name': i.get('name_en',''), 'amount': i.get('balance',0)} for i in asset_items],
            'liabilities': [{'account_name': i.get('name_en',''), 'amount': i.get('balance',0)} for i in liability_items],
            'equity': [{'account_name': i.get('name_en',''), 'amount': i.get('balance',0)} for i in equity_items],
            'total_assets': _round2(total_assets),
            'total_liabilities': _round2(total_liabilities),
            'total_equity': _round2(total_equity),
        }
        return {
            'success': True,
            'data': data_obj,
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

        # Build 'data' matching frontend: [{contract_number, client_name, revenue, costs, profit, margin}]
        data_list = []
        for r in results:
            data_list.append({
                'contract_number': r.get('contract_number', r.get('machine_code', '')),
                'client_name': r.get('description', ''),
                'revenue': r.get('selling_price', 0),
                'costs': r.get('total_landed_cost', 0),
                'profit': r.get('gross_profit', 0),
                'margin': r.get('margin_pct', 0),
            })
        return {
            'success': True,
            'data': data_list,
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
def get_transit_balance(token_or_email=None):
    """
    Reporting: total balance of account 1210 (Inventory in Transit).
    Sum of debits minus sum of credits. Represents cost of machines not yet received into inventory.
    Supplier balance remains ledger-based from 2000 only. Landed cost = supplier_amount_egp + import_costs.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        debits = 0.0
        credits = 0.0
        for entry in app_tables.ledger.search(account_code='1210'):
            debits += _round2(entry.get('debit', 0))
            credits += _round2(entry.get('credit', 0))
        balance = _round2(debits - credits)
        return {'success': True, 'transit_balance_egp': balance}
    except Exception as e:
        logger.exception("get_transit_balance error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_landed_cost(purchase_invoice_id=None, contract_number=None, token_or_email=None):
    """
    Calculate landed cost for a specific purchase invoice or contract.
    Landed Cost = supplier_amount_egp (or FOB+Cylinders in EGP) + All Import Costs (EGP).
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
                'id': str(contract_num),
                'contract_number': str(contract_num),
                'client_name': _safe_str(r.get('Client Name', '')),
                'quotation_number': str(r.get('Quotation#', '')),
            })
        return {'success': True, 'data': contracts}
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

        # Currency: if updating to non-EGP, exchange_rate required; if original_amount set, currency required
        if data.get('original_amount') is not None and not _safe_str(data.get('currency_code') or row.get('currency_code') or '').strip():
            return {'success': False, 'message': 'currency_code is required when original_amount is set.'}
        if data.get('currency_code') is not None:
            cc = _safe_str(data.get('currency_code')).strip().upper()
            if cc and cc != 'EGP':
                ex = data.get('exchange_rate_usd_to_egp') or data.get('exchange_rate') or row.get('exchange_rate_usd_to_egp') or row.get('exchange_rate')
                try:
                    if not ex or float(ex) <= 0:
                        return {'success': False, 'message': 'For non-EGP invoice, exchange_rate must be greater than zero.'}
                except (TypeError, ValueError):
                    return {'success': False, 'message': 'For non-EGP invoice, exchange_rate must be greater than zero.'}

        updates = {}
        if 'supplier_id' in data:
            updates['supplier_id'] = _safe_str(data['supplier_id'])
        if 'date' in data:
            updates['date'] = _safe_date(data['date']) or row.get('date')
        if 'due_date' in data:
            updates['due_date'] = _safe_date(data['due_date'])
        if 'notes' in data:
            updates['notes'] = _safe_str(data['notes'])
        if data.get('exchange_rate_usd_to_egp') is not None and data.get('exchange_rate_usd_to_egp') != '':
            try:
                updates['exchange_rate_usd_to_egp'] = _round2(float(data['exchange_rate_usd_to_egp']))
            except (TypeError, ValueError):
                pass
        if 'currency_code' in data:
            updates['currency_code'] = _safe_str(data['currency_code']).strip().upper()[:3]
        if 'machine_code' in data:
            updates['machine_code'] = _safe_str(data['machine_code'])
        # Update machine config JSON
        machine_config = {}
        for cfg_key in ('condition', 'machine_type', 'colors', 'machine_width',
                         'material', 'winder', 'optionals', 'cylinders',
                         'fob_standard', 'fob_with_cylinders'):
            val = data.get(cfg_key)
            if val is not None and val != '' and val != []:
                machine_config[cfg_key] = val
        if machine_config:
            updates['machine_config_json'] = json.dumps(machine_config, ensure_ascii=False)
        if 'items' in data or 'line_items' in data:
            items = data.get('items') or data.get('line_items', [])
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
            # Supplier-only total (do NOT include import costs; consistent with create_purchase_invoice)
            fob_with_cyl = _round2(data.get('fob_with_cylinders', 0))
            updates['total'] = _round2(fob_with_cyl + subtotal + tax_amount)

        updates['updated_at'] = get_utc_now()
        try:
            row.update(**updates)
        except Exception as col_err:
            updates.pop('exchange_rate_usd_to_egp', None)
            updates.pop('machine_config_json', None)
            row.update(**updates)

        # Update import costs if provided - delete old ones and re-add (with amount_egp, paid_amount=0)
        if 'import_costs' in data:
            try:
                old_ics = app_tables.import_costs.search(purchase_invoice_id=invoice_id)
                for old_ic in old_ics:
                    old_ic.delete()
            except Exception:
                pass
            inv_row = app_tables.purchase_invoices.get(id=invoice_id)
            inv_rate = (inv_row.get('exchange_rate_usd_to_egp') or _get_rate_to_egp('USD')) if inv_row else _get_rate_to_egp('USD')
            try:
                inv_rate = _round2(float(inv_rate)) if inv_rate else _get_rate_to_egp('USD')
            except (TypeError, ValueError):
                inv_rate = _get_rate_to_egp('USD')
            now = get_utc_now()
            for ic in data.get('import_costs', []):
                ic_amount = _round2(ic.get('amount', 0))
                if ic_amount > 0:
                    curr = _safe_str(ic.get('currency') or 'USD').upper()[:3]
                    amount_egp = _round2(ic_amount * (inv_rate if curr == 'USD' else 1))
                    ic_row = dict(
                        id=_uuid(),
                        purchase_invoice_id=invoice_id,
                        cost_type=_safe_str(ic.get('cost_type', 'other')),
                        amount=ic_amount,
                        description=_safe_str(ic.get('description', '')),
                        date=_safe_date(data.get('date')) or date.today(),
                        payment_method=_safe_str(ic.get('payment_method', 'cash')),
                        payment_account=_resolve_payment_account(ic.get('payment_method', 'cash')),
                        created_at=now,
                        amount_egp=amount_egp,
                        paid_amount=0.0,
                    )
                    if curr:
                        ic_row['currency'] = curr
                    try:
                        app_tables.import_costs.add_row(**ic_row)
                    except Exception as ic_err:
                        for k in ('currency', 'amount_egp', 'paid_amount'):
                            ic_row.pop(k, None)
                        try:
                            app_tables.import_costs.add_row(**ic_row)
                        except Exception:
                            logger.warning("Could not save import cost on update: %s", ic_err)

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
def record_invoice_payment(invoice_id, amount, method='cash', notes='', payment_date=None,
                           currency_code='EGP', exchange_rate=None, token_or_email=None):
    """Record payment for a purchase invoice (alias for record_supplier_payment)."""
    payment_date = _safe_date(payment_date) or date.today()
    return record_supplier_payment(
        invoice_id, amount, method, payment_date,
        currency_code=currency_code, exchange_rate=exchange_rate, notes=notes, token_or_email=token_or_email
    )


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
        # Alias for frontend: line_items
        d['line_items'] = d['items']

        # Parse machine config
        try:
            d['machine_config'] = json.loads(d.get('machine_config_json') or '{}')
        except (json.JSONDecodeError, TypeError):
            d['machine_config'] = {}

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

        # Alias paid_amount -> paid for frontend consistency
        d['paid'] = d.get('paid_amount', 0)

        # سعر الصرف: المُحفوظ مع الفاتورة إن وُجد، وإلا سعر الصرف الحالي
        saved_rate = row.get('exchange_rate_usd_to_egp')
        try:
            saved_rate = float(saved_rate) if saved_rate not in (None, '') else 0
        except (TypeError, ValueError):
            saved_rate = 0
        d['exchange_rate_usd_to_egp'] = saved_rate if saved_rate > 0 else _get_rate_to_egp('USD')

        return {'success': True, 'data': d}
    except Exception as e:
        logger.exception("get_invoice_details error")
        return {'success': False, 'message': str(e)}


# ========================================================================
# MIGRATION: Bulk-import old contracts into the accounting system
# ========================================================================

def _parse_cost_string(val):
    """Parse a cost string like '$15,000.00' or '12500' into float. Returns 0.0 on failure.
    Handles currency symbols ($, EUR, EGP, etc.), commas, and whitespace."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        import re
        cleaned = str(val).strip()
        if not cleaned:
            return 0.0
        # Remove currency symbols and text: $, USD, EUR, EGP, CNY, etc.
        cleaned = re.sub(r'[^\d.\-]', '', cleaned)
        if not cleaned:
            return 0.0
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


@anvil.server.callable
def migrate_old_contracts(supplier_id, currency='USD', dry_run=False, token_or_email=None):
    """
    ONE-TIME MIGRATION: Import old contracts into the accounting system.

    Finds all contracts where purchase_invoice_id is NULL (not yet processed),
    looks up FOB + cylinder cost from the linked quotation, and calls
    create_contract_purchase() for each one.

    Args:
        supplier_id: The default supplier ID for all old contracts
        currency: Currency code (default 'USD')
        dry_run: If True, only preview what would be migrated (no actual changes)
        token_or_email: Auth token

    Returns:
        {success, migrated, skipped, errors, details: [{contract_number, status, ...}]}
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error

    try:
        # Validate supplier exists
        supplier = app_tables.suppliers.get(id=supplier_id)
        if not supplier:
            return {'success': False, 'message': f'Supplier {supplier_id} not found'}

        # Find all contracts without a purchase invoice
        contracts = []
        for c in app_tables.contracts.search():
            pi_id = c.get('purchase_invoice_id')
            if pi_id and _safe_str(pi_id):
                continue  # Already has a purchase invoice
            contracts.append(c)

        if not contracts:
            return {
                'success': True, 'migrated': 0, 'skipped': 0, 'errors': 0,
                'message': 'No unprocessed contracts found',
                'details': []
            }

        migrated = 0
        skipped = 0
        errors = 0
        details = []

        for contract_row in contracts:
            cn = _safe_str(contract_row.get('contract_number'))
            qn = contract_row.get('quotation_number')

            # Try to get cost data from the contract itself first
            fob = _parse_cost_string(contract_row.get('fob_cost'))
            cyl = _parse_cost_string(contract_row.get('cylinder_cost'))

            # If not on contract, look up the quotation
            ex_rate = 0.0
            if qn:
                try:
                    quotation = app_tables.quotations.get(**{'Quotation#': int(qn)})
                    if quotation:
                        ex_rate = float(quotation.get('Exchange Rate') or 0)
                        if fob <= 0:
                            fob_str = quotation.get('Standard Machine FOB cost', '')
                            cyl_str = quotation.get('Machine FOB cost With Cylinders', '')
                            fob_parsed = _parse_cost_string(fob_str)
                            cyl_parsed = _parse_cost_string(cyl_str)
                            # "Machine FOB cost With Cylinders" = FOB + cylinders total
                            # So cylinder_cost = total_with_cyl - fob
                            if fob_parsed > 0:
                                fob = fob_parsed
                                if cyl_parsed > fob_parsed:
                                    cyl = _round2(cyl_parsed - fob_parsed)
                                else:
                                    cyl = 0.0
                            elif cyl_parsed > 0:
                                # Only "with cylinders" value exists, use it as total FOB
                                fob = cyl_parsed
                                cyl = 0.0
                except Exception as e:
                    logger.warning("migrate_old_contracts: quotation lookup for %s failed: %s", cn, e)

            # Skip if no cost data at all
            if fob <= 0:
                details.append({
                    'contract_number': cn,
                    'quotation_number': qn,
                    'status': 'skipped',
                    'reason': 'No FOB cost found in contract or quotation',
                })
                skipped += 1
                continue

            if dry_run:
                details.append({
                    'contract_number': cn,
                    'quotation_number': qn,
                    'status': 'would_migrate',
                    'fob_cost': fob,
                    'cylinder_cost': cyl,
                    'total_usd': _round2(fob + cyl),
                    'exchange_rate': ex_rate,
                    'total_egp': _round2((fob + cyl) * ex_rate) if ex_rate > 0 else 0,
                })
                migrated += 1
                continue

            # Actually create the purchase invoice + journal + inventory
            try:
                result = create_contract_purchase(
                    contract_number=cn,
                    fob_cost=fob,
                    cylinder_cost=cyl,
                    supplier_id=supplier_id,
                    currency=currency,
                    token_or_email=user_email,
                    exchange_rate=ex_rate if ex_rate > 0 else 1.0,
                )
                if result.get('success'):
                    details.append({
                        'contract_number': cn,
                        'quotation_number': qn,
                        'status': 'migrated',
                        'fob_cost': fob,
                        'cylinder_cost': cyl,
                        'total': _round2(fob + cyl),
                        'invoice_number': result.get('invoice_number', ''),
                        'inventory_id': result.get('inventory_id', ''),
                    })
                    migrated += 1
                else:
                    details.append({
                        'contract_number': cn,
                        'quotation_number': qn,
                        'status': 'error',
                        'reason': result.get('message', 'Unknown error'),
                    })
                    errors += 1
            except Exception as e:
                details.append({
                    'contract_number': cn,
                    'quotation_number': qn,
                    'status': 'error',
                    'reason': str(e),
                })
                errors += 1

        mode = 'DRY RUN' if dry_run else 'LIVE'
        logger.info(
            "migrate_old_contracts [%s]: %d migrated, %d skipped, %d errors (supplier=%s) by %s",
            mode, migrated, skipped, errors, supplier_id, user_email
        )

        return {
            'success': True,
            'migrated': migrated,
            'skipped': skipped,
            'errors': errors,
            'total_contracts': len(contracts),
            'dry_run': dry_run,
            'details': details,
        }

    except Exception as e:
        logger.exception("migrate_old_contracts error")
        return {'success': False, 'message': str(e)}


# ===========================================================================
# 11. CURRENCY / EXCHANGE RATES
# ===========================================================================

@anvil.server.callable
def get_exchange_rates(token_or_email=None):
    """Return all exchange rates."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        rates = []
        for r in app_tables.currency_exchange_rates.search():
            rates.append({
                'id': r.get('id', ''),
                'currency_code': r.get('currency_code', ''),
                'rate_to_egp': _round2(r.get('rate_to_egp', 0)),
                'updated_at': r.get('updated_at').isoformat() if r.get('updated_at') else '',
            })
        rates.sort(key=lambda x: x.get('currency_code', ''))
        return {'success': True, 'data': rates}
    except Exception as e:
        logger.exception("get_exchange_rates error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def set_exchange_rate(currency_code, rate_to_egp, token_or_email=None):
    """Set or update an exchange rate."""
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    currency_code = _safe_str(currency_code).upper()
    rate_to_egp = _round2(rate_to_egp)
    if not currency_code or rate_to_egp <= 0:
        return {'success': False, 'message': 'Currency code and valid rate are required'}
    try:
        existing = app_tables.currency_exchange_rates.get(currency_code=currency_code)
        now = get_utc_now()
        if existing:
            existing.update(rate_to_egp=rate_to_egp, updated_at=now)
        else:
            app_tables.currency_exchange_rates.add_row(
                id=_uuid(),
                currency_code=currency_code,
                rate_to_egp=rate_to_egp,
                updated_at=now,
            )
        logger.info("Exchange rate %s = %s EGP set by %s", currency_code, rate_to_egp, user_email)
        return {'success': True}
    except Exception as e:
        logger.exception("set_exchange_rate error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def delete_exchange_rate(currency_code, token_or_email=None):
    """Delete an exchange rate."""
    is_valid, user_email, error = _require_permission(token_or_email, 'delete')
    if not is_valid:
        return error
    try:
        existing = app_tables.currency_exchange_rates.get(currency_code=_safe_str(currency_code).upper())
        if not existing:
            return {'success': False, 'message': 'Rate not found'}
        existing.delete()
        return {'success': True}
    except Exception as e:
        logger.exception("delete_exchange_rate error")
        return {'success': False, 'message': str(e)}


# ---------------------------------------------------------------------------
# RBAC — User permissions query
# ---------------------------------------------------------------------------
@anvil.server.callable
def get_user_permissions(token_or_email=None):
    """Return dict of allowed actions for the current user."""
    is_valid, user_email, error = _require_authenticated(token_or_email)
    if not is_valid:
        return {'success': False, 'can_view': False, 'can_create': False, 'can_edit': False,
                'can_delete': False, 'can_export': False, 'is_admin': False, 'role': 'none'}
    try:
        is_admin = AuthManager.is_admin(token_or_email) or AuthManager.is_admin_by_email(token_or_email)
        user_row = app_tables.users.get(email=user_email)
        role = (user_row.get('role') or 'viewer').strip().lower() if user_row else 'viewer'
        return {
            'success': True,
            'can_view': is_admin or AuthManager.check_permission(token_or_email, 'view'),
            'can_create': is_admin or AuthManager.check_permission(token_or_email, 'create'),
            'can_edit': is_admin or AuthManager.check_permission(token_or_email, 'edit'),
            'can_delete': is_admin or AuthManager.check_permission(token_or_email, 'delete'),
            'can_export': is_admin or AuthManager.check_permission(token_or_email, 'export'),
            'is_admin': is_admin,
            'role': role,
        }
    except Exception as e:
        logger.exception("get_user_permissions error")
        return {'success': False, 'can_view': True, 'can_create': False, 'can_edit': False,
                'can_delete': False, 'can_export': False, 'is_admin': False, 'role': 'viewer'}


# ---------------------------------------------------------------------------
# Enhanced Dashboard Stats (Accounting module)
# ---------------------------------------------------------------------------
_accounting_dashboard_cache = {'data': None, 'timestamp': 0, 'user': None}
_ACCOUNTING_DASHBOARD_CACHE_TTL_SECONDS = 60

@anvil.server.callable
def get_accounting_dashboard_stats(token_or_email=None):
    """Return inventory, purchase invoice, and P&L stats for the dashboard."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        import time as _time
        now_ts = _time.time()
        if (_accounting_dashboard_cache.get('data') is not None
            and _accounting_dashboard_cache.get('user') == user_email
            and (now_ts - _accounting_dashboard_cache.get('timestamp', 0)) < _ACCOUNTING_DASHBOARD_CACHE_TTL_SECONDS):
            return _accounting_dashboard_cache['data']

        now = date.today()
        year = now.year

        # Inventory stats
        inv_count = 0; inv_value = 0.0; inv_in_stock = 0; inv_in_transit = 0; inv_sold = 0
        for item in app_tables.inventory.search():
            inv_count += 1
            status = (item.get('status') or '').strip().lower()
            cost = _round2(item.get('total_cost', 0))
            if status == 'in_stock':
                inv_in_stock += 1; inv_value += cost
            elif status == 'in_transit':
                inv_in_transit += 1; inv_value += cost
            elif status == 'sold':
                inv_sold += 1

        # Purchase invoice stats + top suppliers in one pass
        pi_count = 0; pi_total_value = 0.0; pi_total_paid = 0.0; pi_draft = 0; pi_posted = 0
        supplier_totals = {}
        for pi in app_tables.purchase_invoices.search():
            pi_count += 1
            total_pi = _round2(pi.get('total', 0))
            pi_total_value += total_pi
            pi_total_paid += _round2(pi.get('paid_amount', 0))
            st = (pi.get('status') or '').strip().lower()
            if st == 'draft': pi_draft += 1
            elif st == 'posted': pi_posted += 1
            sid = pi.get('supplier_id', '')
            supplier_totals[sid] = supplier_totals.get(sid, 0) + total_pi
        top_suppliers_raw = sorted(supplier_totals.items(), key=lambda x: x[1], reverse=True)[:5]
        top_suppliers = []
        for sid, total in top_suppliers_raw:
            name = sid
            try:
                s = app_tables.suppliers.get(id=sid)
                if s: name = s.get('name', sid)
            except:
                pass
            top_suppliers.append({'name': name, 'total': _round2(total)})

        # Monthly totals + profitability in one ledger pass (current year)
        monthly_purchases = [0.0] * 12
        monthly_sales = [0.0] * 12
        total_cogs = 0.0; total_revenue = 0.0
        for entry in app_tables.ledger.search():
            d = entry.get('date')
            if not d or not hasattr(d, 'year') or d.year != year:
                continue
            m = d.month - 1
            code = entry.get('account_code', '')
            debit = _round2(entry.get('debit', 0))
            credit = _round2(entry.get('credit', 0))

            if code == '1200':  # Inventory (purchases)
                monthly_purchases[m] += debit
            elif code.startswith('4'):  # Revenue (sales)
                delta = credit - debit
                monthly_sales[m] += delta
                total_revenue += delta
            elif code.startswith('5'):
                total_cogs += debit - credit

        result = {
            'success': True,
            'inventory': {
                'total_count': inv_count, 'total_value': _round2(inv_value),
                'in_stock': inv_in_stock, 'in_transit': inv_in_transit, 'sold': inv_sold,
            },
            'purchase_invoices': {
                'total_count': pi_count, 'total_value': _round2(pi_total_value),
                'total_paid': _round2(pi_total_paid),
                'outstanding': _round2(pi_total_value - pi_total_paid),
                'draft_count': pi_draft, 'posted_count': pi_posted,
            },
            'profitability': {
                'total_revenue': _round2(total_revenue),
                'total_cogs': _round2(total_cogs),
                'gross_profit': _round2(total_revenue - total_cogs),
            },
            'top_suppliers': top_suppliers,
            'monthly_purchases': monthly_purchases,
            'monthly_sales': monthly_sales,
        }

        _accounting_dashboard_cache['data'] = result
        _accounting_dashboard_cache['timestamp'] = now_ts
        _accounting_dashboard_cache['user'] = user_email
        return result
    except Exception as e:
        logger.exception("get_accounting_dashboard_stats error")
        return {'success': False, 'message': str(e)}


# ---------------------------------------------------------------------------
# Data Export — Inventory & Purchase Invoices
# ---------------------------------------------------------------------------
@anvil.server.callable
def export_inventory_data(token_or_email=None):
    """Export all inventory items for Excel/CSV."""
    is_valid, user_email, error = _require_permission(token_or_email, 'export')
    if not is_valid:
        return []
    try:
        data = []
        for r in app_tables.inventory.search():
            data.append({
                'Machine Code': r.get('machine_code', ''),
                'Description': r.get('description', ''),
                'Status': r.get('status', ''),
                'Purchase Cost': _round2(r.get('purchase_cost', 0)),
                'Import Costs': _round2(r.get('import_costs_total', 0)),
                'Total Cost (Landed)': _round2(r.get('total_cost', 0)),
                'Selling Price': _round2(r.get('selling_price', 0)),
                'Location': r.get('location', ''),
                'Contract': r.get('contract_number', ''),
                'Notes': r.get('notes', ''),
            })
        return data
    except Exception as e:
        logger.exception("export_inventory_data error")
        return []


@anvil.server.callable
def export_purchase_invoices_data(token_or_email=None):
    """Export all purchase invoices for Excel/CSV."""
    is_valid, user_email, error = _require_permission(token_or_email, 'export')
    if not is_valid:
        return []
    try:
        data = []
        for r in app_tables.purchase_invoices.search():
            supplier_name = ''
            try:
                s = app_tables.suppliers.get(id=r.get('supplier_id'))
                if s: supplier_name = s.get('name', '')
            except:
                pass
            data.append({
                'Invoice Number': r.get('invoice_number', ''),
                'Supplier': supplier_name,
                'Date': str(r.get('date', '')),
                'Due Date': str(r.get('due_date', '')),
                'Machine Code': r.get('machine_code', ''),
                'Subtotal': _round2(r.get('subtotal', 0)),
                'Tax': _round2(r.get('tax_amount', 0)),
                'Total': _round2(r.get('total', 0)),
                'Paid': _round2(r.get('paid_amount', 0)),
                'Status': r.get('status', ''),
                'Contract': r.get('contract_number', ''),
                'Notes': r.get('notes', ''),
            })
        return data
    except Exception as e:
        logger.exception("export_purchase_invoices_data error")
        return []


# ---------------------------------------------------------------------------
# Feature 6: Multi-Currency — Auto-fetch exchange rates from API
# ---------------------------------------------------------------------------
@anvil.server.callable
def fetch_exchange_rates_from_api(token_or_email=None):
    """Auto-fetch exchange rates from open.er-api.com and update the table."""
    is_valid, user_email, error = _require_authenticated(token_or_email)
    if not is_valid:
        return {'success': False, 'message': error}
    try:
        import anvil.http
        resp = anvil.http.request('https://open.er-api.com/v6/latest/USD', json=True)
        if not resp or resp.get('result') != 'success':
            return {'success': False, 'message': 'API returned error'}
        rates = resp.get('rates', {})
        updated_count = 0
        target_currencies = ['EGP', 'EUR', 'GBP', 'SAR', 'AED', 'CNY']
        now = datetime.now()
        for code in target_currencies:
            rate_val = rates.get(code)
            if rate_val is None:
                continue
            try:
                existing = app_tables.currency_exchange_rates.get(currency_code=code)
                if existing:
                    existing['rate_to_usd'] = float(rate_val)
                    existing['updated_at'] = now
                    existing['source'] = 'open.er-api.com'
                else:
                    app_tables.currency_exchange_rates.add_row(
                        currency_code=code,
                        rate_to_usd=float(rate_val),
                        updated_at=now,
                        source='open.er-api.com'
                    )
                updated_count += 1
            except Exception as inner_e:
                logger.warning("Failed to update rate for %s: %s", code, inner_e)
        AuthManager.log_audit('fetch_exchange_rates', 'currency_exchange_rates', 'auto',
                              None, {'currencies_updated': updated_count, 'source': 'open.er-api.com'},
                              user_email)
        return {'success': True, 'message': f'{updated_count} currencies updated',
                'updated_count': updated_count, 'last_updated': now.isoformat()}
    except Exception as e:
        logger.exception("fetch_exchange_rates_from_api error")
        return {'success': False, 'message': str(e)}


# ---------------------------------------------------------------------------
# Feature 5: Export Audit Log (CSV-ready)
# ---------------------------------------------------------------------------
@anvil.server.callable
def export_audit_log(token_or_email=None, filters=None):
    """Export audit logs as list of dicts for CSV/Excel."""
    result = AuthManager.get_audit_logs(token_or_email, limit=5000, offset=0, filters=filters)
    if not result or not result.get('success'):
        return []
    data = []
    for log in result.get('logs', []):
        # Compute diff if old_data and new_data exist
        diff_text = ''
        try:
            old_d = log.get('old_data')
            new_d = log.get('new_data')
            if old_d and new_d:
                if isinstance(old_d, str):
                    old_d = json.loads(old_d)
                if isinstance(new_d, str):
                    new_d = json.loads(new_d)
                if isinstance(old_d, dict) and isinstance(new_d, dict):
                    changes = []
                    all_keys = set(list(old_d.keys()) + list(new_d.keys()))
                    for k in sorted(all_keys):
                        ov = old_d.get(k, '—')
                        nv = new_d.get(k, '—')
                        if str(ov) != str(nv):
                            changes.append(f'{k}: {ov} → {nv}')
                    diff_text = '; '.join(changes)
        except Exception:
            pass
        data.append({
            'Timestamp': log.get('timestamp', ''),
            'User': log.get('user_name', ''),
            'Email': log.get('user_email', ''),
            'Action': log.get('action', ''),
            'Table': log.get('table_name', ''),
            'Record ID': log.get('record_id', ''),
            'Description': log.get('action_description', ''),
            'Changes': diff_text,
        })
    return data


# ---------------------------------------------------------------------------
# Feature 3: Smart Notifications — Daily check for due invoices
# ---------------------------------------------------------------------------
@anvil.server.callable
def run_daily_notification_check(token_or_email=None):
    """Check for due/overdue purchase invoices and create notifications."""
    is_valid, user_email, error = _require_authenticated(token_or_email)
    if not is_valid:
        return {'success': False, 'message': error}
    try:
        now = datetime.now()
        seven_days = now + timedelta(days=7)
        count_due = 0
        count_overdue = 0

        for inv in app_tables.purchase_invoices.search():
            status = (inv.get('status') or '').lower()
            if status in ('paid', 'cancelled'):
                continue
            due_date = inv.get('due_date')
            if not due_date:
                continue
            if isinstance(due_date, str):
                try:
                    due_date = datetime.strptime(due_date, '%Y-%m-%d')
                except Exception:
                    continue

            inv_num = inv.get('invoice_number', '?')
            total_val = _round2(inv.get('total', 0))
            paid_val = _round2(inv.get('paid_amount', 0))
            remaining = _round2(total_val - paid_val)

            if due_date < now:
                # Overdue
                _create_notification_for_admins(
                    'invoice_overdue',
                    f'Invoice {inv_num} is OVERDUE (due {due_date.strftime("%Y-%m-%d")}). Remaining: ${remaining}',
                    {'invoice_number': inv_num, 'due_date': str(due_date.date()),
                     'remaining': remaining}
                )
                count_overdue += 1
            elif due_date <= seven_days:
                # Due soon
                _create_notification_for_admins(
                    'invoice_due_soon',
                    f'Invoice {inv_num} due on {due_date.strftime("%Y-%m-%d")}. Remaining: ${remaining}',
                    {'invoice_number': inv_num, 'due_date': str(due_date.date()),
                     'remaining': remaining}
                )
                count_due += 1

        return {'success': True, 'message': f'Check complete: {count_overdue} overdue, {count_due} due soon',
                'overdue': count_overdue, 'due_soon': count_due}
    except Exception as e:
        logger.exception("run_daily_notification_check error")
        return {'success': False, 'message': str(e)}


def _create_notification_for_admins(notification_type, message, data=None):
    """Create a notification for all admin users."""
    try:
        for user in app_tables.users.search():
            role = (user.get('role') or '').strip().lower()
            if role in ('admin', 'manager'):
                app_tables.notifications.add_row(
                    user_email=user.get('email', ''),
                    type=notification_type,
                    message=message,
                    data=json.dumps(data) if data else '',
                    is_read=False,
                    created_at=datetime.now()
                )
    except Exception as e:
        logger.warning("_create_notification_for_admins error: %s", e)


# ---------------------------------------------------------------------------
# Feature 2: PDF Reports — Purchase Invoice, P&L, Supplier Statement
# ---------------------------------------------------------------------------
@anvil.server.callable
def get_purchase_invoice_pdf_data(invoice_id, token_or_email=None):
    """Get PDF-ready data for a purchase invoice."""
    is_valid, user_email, error = _require_authenticated(token_or_email)
    if not is_valid:
        return {'success': False, 'message': error}
    try:
        inv = app_tables.purchase_invoices.get(id=invoice_id)
        if not inv:
            return {'success': False, 'message': 'Invoice not found'}
        supplier = None
        try:
            supplier = app_tables.suppliers.get(id=inv.get('supplier_id'))
        except Exception:
            pass
        import_costs = []
        try:
            for c in app_tables.import_costs.search(purchase_invoice_id=invoice_id):
                import_costs.append(dict(c))
        except Exception:
            pass
        data = pdf_reports.build_purchase_invoice_pdf_data(
            dict(inv), dict(supplier) if supplier else {}, import_costs
        )
        return {'success': True, 'data': data}
    except Exception as e:
        logger.exception("get_purchase_invoice_pdf_data error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_pnl_report_pdf_data(date_from=None, date_to=None, token_or_email=None):
    """Get P&L report PDF data."""
    is_valid, user_email, error = _require_authenticated(token_or_email)
    if not is_valid:
        return {'success': False, 'message': error}
    try:
        items = [dict(r) for r in app_tables.inventory.search()]
        invoices = [dict(r) for r in app_tables.purchase_invoices.search()]
        data = pdf_reports.build_pnl_report_data(items, invoices, date_from, date_to)
        return {'success': True, 'data': data}
    except Exception as e:
        logger.exception("get_pnl_report_pdf_data error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_supplier_statement_pdf_data(supplier_id, date_from=None, date_to=None, token_or_email=None):
    """Get supplier account statement PDF data."""
    is_valid, user_email, error = _require_authenticated(token_or_email)
    if not is_valid:
        return {'success': False, 'message': error}
    try:
        supplier = app_tables.suppliers.get(id=supplier_id)
        if not supplier:
            return {'success': False, 'message': 'Supplier not found'}
        invoices = [dict(r) for r in app_tables.purchase_invoices.search(supplier_id=supplier_id)]
        data = pdf_reports.build_supplier_statement_data(dict(supplier), invoices, [], date_from, date_to)
        return {'success': True, 'data': data}
    except Exception as e:
        logger.exception("get_supplier_statement_pdf_data error")
        return {'success': False, 'message': str(e)}


# ===========================================================================
# 12. CUSTOMER COLLECTIONS (تحصيل العملاء)
# ===========================================================================

def _get_customer_ar_balance(contract_number):
    """
    Calculate Accounts Receivable balance for a customer (contract) from the ledger ONLY.
    AR Balance = total debit (sales) - total credit (collections) for account 1100.

    Sales: ref_type='sales_invoice', ref_id = inventory item IDs linked to this contract.
    Collections: ref_type='customer_collection', ref_id = contract_number.
    """
    # 1. Find all inventory items linked to this contract
    item_ids = []
    try:
        for item in app_tables.inventory.search(contract_number=contract_number):
            item_ids.append(item.get('id'))
    except Exception:
        pass

    # 2. Sum debits for account 1100 where ref_type='sales_invoice' and ref_id in item_ids
    total_sales = 0.0
    if item_ids:
        for entry in app_tables.ledger.search(account_code='1100', reference_type='sales_invoice'):
            if entry.get('reference_id') in item_ids:
                total_sales += float(entry.get('debit', 0) or 0)

    # 3. Sum credits for account 1100 where ref_type='customer_collection' and ref_id=contract_number
    total_collections = 0.0
    for entry in app_tables.ledger.search(account_code='1100', reference_type='customer_collection'):
        if entry.get('reference_id') == contract_number:
            total_collections += float(entry.get('credit', 0) or 0)

    return _round2(total_sales - total_collections)


@anvil.server.callable
def record_customer_collection(contract_number, amount, payment_method,
                                collection_date=None, notes='',
                                currency_code='EGP', exchange_rate=None, token_or_email=None):
    """
    Record cash collection from a customer. أي مبلغ مسموح (أكثر أو أقل من المستحق — مقسط أو مقدّم).
    DR Cash/Bank (1000/101x)
    CR Accounts Receivable (1100)
    currency_code: EGP (افتراضي) أو USD أو غيرها — يُحوَّل إلى EGP حسب سعر الصرف عند الحاجة.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error

    amount_in = _round2(amount)
    if amount_in <= 0:
        return {'success': False, 'message': 'Collection amount must be greater than zero'}
    if not contract_number:
        return {'success': False, 'message': 'Contract number is required'}

    try:
        contract = app_tables.contracts.get(contract_number=contract_number)
        if not contract:
            return {'success': False, 'message': f'Contract {contract_number} not found'}

        currency_code = _safe_str(currency_code or 'EGP').upper()
        if currency_code == 'EGP':
            amount_egp = amount_in
            rate_used = 1.0
        else:
            rate_used = _round2(exchange_rate) if exchange_rate is not None and float(exchange_rate) > 0 else _get_rate_to_egp(currency_code)
            if rate_used <= 0:
                return {'success': False, 'message': f'سعر صرف غير صالح لعملة {currency_code} | Invalid exchange rate for {currency_code}'}
            amount_egp = _round2(amount_in * rate_used)

        cash_account = _resolve_payment_account(payment_method)
        parsed_date = _safe_date(collection_date) or date.today()
        client_name = contract.get('client_name', contract_number)

        description = f"Customer collection from {client_name} — contract {contract_number}"
        if currency_code != 'EGP':
            description += f" — {amount_in:,.2f} {currency_code} @ {rate_used} = {amount_egp:,.2f} EGP"
        if notes:
            description += f" ({notes})"

        entries = [
            {'account_code': cash_account, 'debit': amount_egp, 'credit': 0},
            {'account_code': '1100', 'debit': 0, 'credit': amount_egp},
        ]
        result = post_journal_entry(
            parsed_date, entries, description,
            'customer_collection', contract_number, user_email,
        )
        if not result.get('success'):
            return result

        try:
            AuthManager.log_audit(
                user_email, 'customer_collection',
                'ledger', result.get('transaction_id', ''),
                None, {'contract': contract_number, 'amount': amount_egp, 'method': payment_method}
            )
        except Exception:
            pass

        ar_balance = _get_customer_ar_balance(contract_number)
        logger.info("Customer collection %.2f EGP (%.2f %s) for contract %s (%s) by %s",
                     amount_egp, amount_in, currency_code, contract_number, payment_method, user_email)
        return {
            'success': True,
            'transaction_id': result.get('transaction_id'),
            'new_balance': _round2(ar_balance),
            'client_name': client_name,
            'amount_egp': amount_egp,
        }
    except Exception as e:
        logger.exception("record_customer_collection error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def post_contract_receivable(contract_number, amount_egp, description=None, token_or_email=None):
    """
    فتح ذمم العقد — تسجيل إيراد العقد (المستحق على العميل) في الدفتر.
    لما العقد يكون عليه دفعات ومفيش تسليم/صنف مخزون، الرصيد بيبقى 0 لأن مفيش قيد مبيعات.
    استدعاء هذه الدالة يسجل: مدين 1100 (ذمم مدينة)، دائن 4000 (إيراد مبيعات) فيصبح الرصيد يظهر حتى يسجل المستخدم التحصيلات.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    amount_egp = _round2(float(amount_egp or 0))
    if amount_egp <= 0:
        return {'success': False, 'message': 'المبلغ يجب أن يكون أكبر من صفر'}
    try:
        contract = app_tables.contracts.get(contract_number=contract_number)
        if not contract:
            return {'success': False, 'message': f'العقد غير موجود: {contract_number}'}
        client_name = contract.get('client_name', contract_number)
        desc = description or f"Contract receivable — {client_name} — {contract_number}"
        entries = [
            {'account_code': '1100', 'debit': amount_egp, 'credit': 0},
            {'account_code': '4000', 'debit': 0, 'credit': amount_egp},
        ]
        result = post_journal_entry(
            date.today(), entries, desc,
            'contract_receivable', contract_number, user_email,
        )
        if not result.get('success'):
            return result
        try:
            AuthManager.log_audit(
                user_email, 'contract_receivable', 'ledger', result.get('transaction_id', ''),
                None, {'contract': contract_number, 'amount': amount_egp}
            )
        except Exception:
            pass
        logger.info("Contract receivable %.2f EGP for %s by %s", amount_egp, contract_number, user_email)
        return {
            'success': True,
            'transaction_id': result.get('transaction_id'),
            'message': 'تم تسجيل إيراد العقد (فتح الذمم)',
        }
    except Exception as e:
        logger.exception("post_contract_receivable error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_contract_total(contract_number, token_or_email=None):
    """إرجاع إجمالي قيمة العقد (للاقتراح عند فتح الذمم)."""
    is_valid, _, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        contract = app_tables.contracts.get(contract_number=contract_number)
        if not contract:
            return {'success': False, 'message': 'العقد غير موجود', 'total_price': None}
        raw = contract.get('total_price') or ''
        try:
            total = _round2(float(str(raw).replace(',', '').strip() or 0))
        except (ValueError, TypeError):
            total = None
        return {'success': True, 'total_price': total}
    except Exception as e:
        logger.exception("get_contract_total error")
        return {'success': False, 'message': str(e), 'total_price': None}


# ===========================================================================
# 13. CUSTOMER / SUPPLIER / TREASURY SUMMARIES
# ===========================================================================

@anvil.server.callable
def get_customer_summary(token_or_email=None):
    """
    Get summary of all customers (grouped by client_name from contracts).
    For each customer:
      - opening_balance (from opening_balances table)
      - total_sales (DR on account 1100, ref_type='sales_invoice')
      - total_collections (CR on account 1100, ref_type='customer_collection')
      - current_balance = opening_balance + total_sales - total_collections
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error

    try:
        # 1. Build map: client_name -> [contract_numbers]
        client_contracts = {}
        for c in app_tables.contracts.search():
            cname = c.get('client_name', '').strip()
            cnum = c.get('contract_number', '')
            if not cname or not cnum:
                continue
            if cname not in client_contracts:
                client_contracts[cname] = []
            client_contracts[cname].append(cnum)

        # 2. Build map: contract_number -> [inventory item_ids]
        contract_items = {}
        for item in app_tables.inventory.search():
            cn = item.get('contract_number', '')
            if cn:
                if cn not in contract_items:
                    contract_items[cn] = []
                contract_items[cn].append(item.get('id'))

        # 3. Load all AR ledger entries (account 1100) at once for efficiency
        ar_sales = {}                  # item_id -> debit total (sales from sell_inventory)
        ar_contract_receivable = {}     # contract_number -> debit total (فتح ذمم العقد)
        ar_collections = {}             # contract_number -> credit total (collections)

        for entry in app_tables.ledger.search(account_code='1100'):
            ref_type = entry.get('reference_type', '')
            ref_id = entry.get('reference_id', '')
            if ref_type == 'sales_invoice':
                ar_sales[ref_id] = ar_sales.get(ref_id, 0) + float(entry.get('debit', 0) or 0)
            elif ref_type == 'contract_receivable':
                ar_contract_receivable[ref_id] = ar_contract_receivable.get(ref_id, 0) + float(entry.get('debit', 0) or 0)
            elif ref_type == 'customer_collection':
                ar_collections[ref_id] = ar_collections.get(ref_id, 0) + float(entry.get('credit', 0) or 0)

        # 4. Load opening balances
        opening_map = {}
        try:
            for ob in app_tables.opening_balances.search(type='customer'):
                opening_map[ob.get('name', '')] = float(ob.get('opening_balance', 0) or 0)
        except Exception:
            pass  # Table may not exist yet

        # 5. Build summary per customer
        result = []
        grand_sales = 0
        grand_collections = 0
        grand_opening = 0

        for client_name, contracts_list in sorted(client_contracts.items()):
            opening = opening_map.get(client_name, 0)

            # Total sales: (1) debits from sell_inventory (item_id) + (2) debits from فتح ذمم العقد (contract_number)
            total_sales = 0
            for cn in contracts_list:
                for item_id in contract_items.get(cn, []):
                    total_sales += ar_sales.get(item_id, 0)
                total_sales += ar_contract_receivable.get(cn, 0)

            # Total collections: sum credits for all contract numbers
            total_collections = 0
            for cn in contracts_list:
                total_collections += ar_collections.get(cn, 0)

            current_balance = _round2(opening + total_sales - total_collections)

            result.append({
                'client_name': client_name,
                'contracts': contracts_list,
                'contract_count': len(contracts_list),
                'opening_balance': _round2(opening),
                'total_sales': _round2(total_sales),
                'total_collections': _round2(total_collections),
                'current_balance': current_balance,
            })

            grand_sales += total_sales
            grand_collections += total_collections
            grand_opening += opening

        return {
            'success': True,
            'data': result,
            'totals': {
                'opening': _round2(grand_opening),
                'sales': _round2(grand_sales),
                'collections': _round2(grand_collections),
                'balance': _round2(grand_opening + grand_sales - grand_collections),
            },
            'count': len(result),
        }
    except Exception as e:
        logger.exception("get_customer_summary error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_supplier_summary(token_or_email=None):
    """
    Get summary of all suppliers.
    For each supplier:
      - opening_balance (from opening_balances table)
      - total_purchases (CR on account 2000, ref_type='purchase_invoice')
      - total_payments (DR on account 2000, ref_type='payment')
      - current_balance = opening_balance + total_purchases - total_payments
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error

    try:
        # 1. Build map: supplier_id -> supplier_name
        suppliers = {}
        for s in app_tables.suppliers.search():
            sid = s.get('id', '')
            sname = s.get('name', '')
            if sid and sname:
                suppliers[sid] = sname

        # 2. Build map: supplier_id -> [invoice_ids]
        supplier_invoices = {}
        for inv in app_tables.purchase_invoices.search():
            sid = inv.get('supplier_id', '')
            iid = inv.get('id', '')
            if sid and iid:
                if sid not in supplier_invoices:
                    supplier_invoices[sid] = []
                supplier_invoices[sid].append(iid)

        # 3. Load all AP ledger entries (account 2000) at once
        ap_purchases = {}   # invoice_id -> credit total
        ap_payments = {}    # invoice_id -> debit total

        for entry in app_tables.ledger.search(account_code='2000'):
            ref_type = entry.get('reference_type', '')
            ref_id = entry.get('reference_id', '')
            if ref_type == 'purchase_invoice':
                ap_purchases[ref_id] = ap_purchases.get(ref_id, 0) + float(entry.get('credit', 0) or 0)
            elif ref_type == 'payment':
                ap_payments[ref_id] = ap_payments.get(ref_id, 0) + float(entry.get('debit', 0) or 0)

        # 4. Load opening balances
        opening_map = {}
        try:
            for ob in app_tables.opening_balances.search(type='supplier'):
                opening_map[ob.get('name', '')] = float(ob.get('opening_balance', 0) or 0)
        except Exception:
            pass

        # 5. Build summary per supplier
        result = []
        grand_purchases = 0
        grand_payments = 0
        grand_opening = 0

        for sid, sname in sorted(suppliers.items(), key=lambda x: x[1]):
            opening = opening_map.get(sname, 0)
            invoice_ids = supplier_invoices.get(sid, [])

            total_purchases = 0
            total_payments = 0
            for iid in invoice_ids:
                total_purchases += ap_purchases.get(iid, 0)
                total_payments += ap_payments.get(iid, 0)

            current_balance = _round2(opening + total_purchases - total_payments)

            result.append({
                'supplier_id': sid,
                'supplier_name': sname,
                'invoice_count': len(invoice_ids),
                'opening_balance': _round2(opening),
                'total_purchases': _round2(total_purchases),
                'total_payments': _round2(total_payments),
                'current_balance': current_balance,
            })

            grand_purchases += total_purchases
            grand_payments += total_payments
            grand_opening += opening

        return {
            'success': True,
            'data': result,
            'totals': {
                'opening': _round2(grand_opening),
                'purchases': _round2(grand_purchases),
                'payments': _round2(grand_payments),
                'balance': _round2(grand_opening + grand_purchases - grand_payments),
            },
            'count': len(result),
        }
    except Exception as e:
        logger.exception("get_supplier_summary error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_treasury_summary(token_or_email=None):
    """
    Get treasury/bank account balances from the ledger.
    For each cash/bank account (1000, 1010-1013):
      - opening_balance (from opening_balances table, type='bank')
      - ledger_balance = sum(debit) - sum(credit)
      - current_balance = opening_balance + ledger_balance
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error

    try:
        # 1. Get all cash/bank account codes (code may be int in DB → normalize to string)
        bank_codes = []
        account_names = {}
        for acct in app_tables.chart_of_accounts.search(is_active=True):
            code = str(acct.get('code', '')).strip()
            if code == '1000' or (code.startswith('101') and len(code) == 4):
                bank_codes.append(code)
                account_names[code] = {
                    'name_en': acct.get('name_en', ''),
                    'name_ar': acct.get('name_ar', ''),
                }

        # 2. Calculate balances from ledger
        ledger_balances = {}
        for code in bank_codes:
            total_debit = 0
            total_credit = 0
            for entry in app_tables.ledger.search(account_code=code):
                total_debit += float(entry.get('debit', 0) or 0)
                total_credit += float(entry.get('credit', 0) or 0)
            ledger_balances[code] = _round2(total_debit - total_credit)

        # 3. Load opening balances
        opening_map = {}
        try:
            for ob in app_tables.opening_balances.search(type='bank'):
                opening_map[ob.get('name', '')] = float(ob.get('opening_balance', 0) or 0)
        except Exception:
            pass

        # 4. Build result (include account_name for client display)
        result = []
        grand_total = 0
        for code in sorted(bank_codes):
            opening = opening_map.get(code, 0)
            ledger_bal = ledger_balances.get(code, 0)
            current = _round2(opening + ledger_bal)
            names = account_names.get(code, {})
            name_en = names.get('name_en', '') or names.get('name_ar', '') or code
            name_ar = names.get('name_ar', '') or names.get('name_en', '') or code
            result.append({
                'account_code': code,
                'account_name': name_en,
                'name_en': names.get('name_en', ''),
                'name_ar': names.get('name_ar', ''),
                'opening_balance': _round2(opening),
                'ledger_balance': ledger_bal,
                'current_balance': current,
            })
            grand_total += current

        return {
            'success': True,
            'data': result,
            'accounts': result,
            'grand_total': _round2(grand_total),
        }
    except Exception as e:
        logger.exception("get_treasury_summary error")
        return {'success': False, 'message': str(e)}


CASH_BANK_ACCOUNTS = ('1000', '1010', '1011', '1012', '1013')


@anvil.server.callable
def get_cash_bank_statement(account_code=None, date_from=None, date_to=None, token_or_email=None):
    """
    كشف حساب النقدية والبنك — كل الحركات (مدين/دائن) لحساب نقدية أو بنك ضمن الفترة.
    account_code: اختياري — إن ترك فاضياً يعيد حركات كل الحسابات المصنفة نقدية/بنوك من دليل الحسابات.
    يُرجع قائمة حركات مع الرصيد الجاري (running balance) واسم الحساب.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        if account_code and _safe_str(account_code).strip():
            codes = [_safe_str(account_code).strip()]
        else:
            codes = []
            for acct in app_tables.chart_of_accounts.search():
                # بعض السجلات القديمة لا تحتوي is_active؛ نعتبرها فعّالة افتراضياً
                if acct.get('is_active', True) is False:
                    continue
                if _is_cash_bank_account_row(acct):
                    c = str(acct.get('code', '')).strip()
                    if c:
                        codes.append(c)
            if not codes:
                codes = list(CASH_BANK_ACCOUNTS)
            codes = sorted(set(codes))
        d_from = _safe_date(date_from)
        d_to = _safe_date(date_to)

        account_names = {}
        for acct in app_tables.chart_of_accounts.search():
            c = str(acct.get('code', '')).strip()
            if c in codes:
                account_names[c] = acct.get('name_en', '') or acct.get('name_ar', '') or c

        rows = []
        for r in app_tables.ledger.search():
            c = str(r.get('account_code', '')).strip()
            if c not in codes:
                continue
            row_date = r.get('date')
            if isinstance(row_date, datetime):
                row_date = row_date.date()
            if d_from and row_date and row_date < d_from:
                continue
            if d_to and row_date and row_date > d_to:
                continue
            debit = _round2(r.get('debit', 0) or 0)
            credit = _round2(r.get('credit', 0) or 0)
            rows.append({
                'date': row_date.isoformat() if hasattr(row_date, 'isoformat') else str(row_date),
                'account_code': c,
                'account_name': account_names.get(c, c),
                'description': r.get('description', ''),
                'debit': debit,
                'credit': credit,
                'reference_type': r.get('reference_type', ''),
                'reference_id': r.get('reference_id', ''),
                'created_at': r.get('created_at').isoformat() if r.get('created_at') else '',
            })
        rows.sort(key=lambda x: (x.get('date', ''), x.get('created_at', '')))

        # رصيد جاري (running balance) — للنقدية والبنك: مدين - دائن
        running = {}
        for r in rows:
            c = r['account_code']
            bal = running.get(c, 0) + _round2(r['debit'] - r['credit'])
            running[c] = bal
            r['balance'] = _round2(bal)

        return {'success': True, 'data': rows, 'count': len(rows)}
    except Exception as e:
        logger.exception("get_cash_bank_statement error")
        return {'success': False, 'message': str(e)}


# ===========================================================================
# 14. OPENING BALANCES (أرصدة أول المدة)
# ===========================================================================

@anvil.server.callable
def get_opening_balances(entity_type='', token_or_email=None):
    """
    Get opening balances from the opening_balances table.
    entity_type: 'customer', 'supplier', 'bank', or '' for all.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error

    try:
        result = []
        try:
            rows = app_tables.opening_balances.search()
        except Exception:
            return {'success': True, 'data': [], 'count': 0}

        for r in rows:
            rtype = r.get('type', '')
            if entity_type and rtype != entity_type:
                continue
            result.append({
                'name': r.get('name', ''),
                'type': rtype,
                'opening_balance': float(r.get('opening_balance', 0) or 0),
                'updated_at': str(r.get('updated_at', '')),
                'updated_by': r.get('updated_by', ''),
            })

        return {'success': True, 'data': result, 'count': len(result)}
    except Exception as e:
        logger.exception("get_opening_balances error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def set_opening_balance(name, entity_type, amount, token_or_email=None):
    """
    Set or update an opening balance. Does NOT create a journal entry.
    Only affects the opening_balances table (used in dynamic balance calculations).
    Requires 'edit' permission.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'edit')
    if not is_valid:
        return error

    if not name or not entity_type:
        return {'success': False, 'message': 'Name and type are required'}
    if entity_type not in ('customer', 'supplier', 'bank'):
        return {'success': False, 'message': 'Type must be customer, supplier, or bank'}

    try:
        amount = _round2(float(amount or 0))

        # Try to find existing row
        existing = None
        try:
            for r in app_tables.opening_balances.search(name=name, type=entity_type):
                existing = r
                break
        except Exception:
            pass

        now = get_utc_now()
        if existing:
            existing.update(
                opening_balance=amount,
                updated_at=now,
                updated_by=user_email,
            )
        else:
            app_tables.opening_balances.add_row(
                name=name,
                type=entity_type,
                opening_balance=amount,
                updated_at=now,
                updated_by=user_email,
            )

        # Audit log
        try:
            AuthManager.log_audit(
                user_email, 'set_opening_balance',
                'opening_balances', name,
                None, {'type': entity_type, 'amount': amount}
            )
        except Exception:
            pass

        logger.info("Opening balance set: %s (%s) = %.2f by %s", name, entity_type, amount, user_email)
        return {'success': True}
    except Exception as e:
        logger.exception("set_opening_balance error")
        return {'success': False, 'message': str(e)}

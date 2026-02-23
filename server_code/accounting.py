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
import anvil.tables
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
# Centralized permission helpers (من auth_permissions.py)
# ---------------------------------------------------------------------------
try:
    from .auth_permissions import require_authenticated as _require_authenticated
    from .auth_permissions import require_permission_full as _require_permission
except ImportError:
    from auth_permissions import require_authenticated as _require_authenticated
    from auth_permissions import require_permission_full as _require_permission

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helper: البحث في العقود مع استبعاد المحذوفة (soft delete) — from shared_utils
# ---------------------------------------------------------------------------
try:
    from .shared_utils import contracts_search_active as _contracts_search_active
except ImportError:
    from shared_utils import contracts_search_active as _contracts_search_active

try:
    from .shared_utils import bounded_search as _bounded_search
except ImportError:
    from shared_utils import bounded_search as _bounded_search

# Structured logging — request timing decorator
try:
    from .structured_logging import log_request_timing as _timed
except ImportError:
    try:
        from structured_logging import log_request_timing as _timed
    except ImportError:
        _timed = lambda f: f  # no-op fallback

# ---------------------------------------------------------------------------
# Financial report cache — migrated to thread-safe TTLCache (cache_manager)
# ---------------------------------------------------------------------------
try:
    from .cache_manager import report_cache as _report_cache_mgr
    from .cache_manager import accounting_dashboard_cache as _acct_dash_cache
except ImportError:
    from cache_manager import report_cache as _report_cache_mgr
    from cache_manager import accounting_dashboard_cache as _acct_dash_cache


def _get_report_cache(cache_key, user_email):
    """Return cached data if fresh, else None. Key includes user for isolation."""
    return _report_cache_mgr.get(f"{cache_key}:{user_email}")


def _set_report_cache(cache_key, data, user_email):
    """Store result in cache. Key includes user for isolation."""
    _report_cache_mgr.set(f"{cache_key}:{user_email}", data)


def _invalidate_report_cache():
    """Clear all report caches (call after any ledger write)."""
    _report_cache_mgr.invalidate()

# ---------------------------------------------------------------------------
# Safety caps — prevent unbounded iteration over large tables
# ---------------------------------------------------------------------------
MAX_LEDGER_SCAN = 50_000

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


def _export_period_info(filters):
    """
    Build period label and filename slug from filters for export.
    Returns (period_label, filename_slug).
    period_label: e.g. "From: 2026-01-01 To: 2026-01-31" or "As of: 2026-01-31" or "All data".
    filename_slug: e.g. "2026-01-01_to_2026-01-31" or "as_of_2026-01-31" or "all".
    """
    filters = filters or {}
    date_from = _safe_date(filters.get('date_from'))
    date_to = _safe_date(filters.get('date_to'))
    as_of = _safe_date(filters.get('as_of_date'))
    if date_from and date_to:
        label = "From: {} To: {}".format(date_from.isoformat(), date_to.isoformat())
        slug = "{}_to_{}".format(date_from.isoformat(), date_to.isoformat())
        return label, slug
    if as_of:
        label = "As of: {}".format(as_of.isoformat())
        slug = "as_of_{}".format(as_of.isoformat())
        return label, slug
    if date_from:
        label = "From: {}".format(date_from.isoformat())
        slug = "from_{}".format(date_from.isoformat())
        return label, slug
    if date_to:
        label = "To: {}".format(date_to.isoformat())
        slug = "to_{}".format(date_to.isoformat())
        return label, slug
    return "All data", "all"


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
    ('2010', 'Service Suppliers AP', 'ذمم دائنة - موردين خدمات', 'liability', '2000'),
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
    ('6060', 'Transport',          'النقل',             'expense',  None),
    ('6070', 'Marketing',          'التسويق',           'expense',  None),
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
    """Return exchange rate to EGP for the given currency. EGP or missing => raise ValueError."""
    if not currency_code or _safe_str(currency_code).upper() == 'EGP':
        return 1.0
    cc = _safe_str(currency_code).upper()
    try:
        # Fetch only active rates; pick latest effective_date if multiple exist
        active_rows = list(app_tables.currency_exchange_rates.search(currency_code=cc, is_active=True))
        if active_rows:
            best = max(active_rows, key=lambda r: r.get('effective_date') or datetime.min)
            rate = _round2(float(best.get('rate_to_egp', 0)))
            if rate > 0:
                return rate
    except Exception:
        pass
    raise ValueError(
        f"Exchange rate for {cc} not found in currency_exchange_rates table. "
        f"سعر الصرف غير موجود للعملة {cc}. "
        f"Cannot convert to EGP — add the rate first."
    )


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def add_account(code, name_en, name_ar, account_type, parent_code=None, token_or_email=None):
    """Add a single account to the chart of accounts."""
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    code = _safe_str(code).strip()
    name_en = _safe_str(name_en).strip()
    if not code or not name_en:
        return {'success': False, 'message': 'Account code and English name are required'}
    # Validate account code format: 1-20 chars, alphanumeric + dash/dot only
    import re
    if len(code) > 20:
        return {'success': False, 'message': 'Account code must be 20 characters or less'}
    if not re.match(r'^[A-Za-z0-9.\-]+$', code):
        return {'success': False, 'message': 'Account code can only contain letters, numbers, dots and dashes'}
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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable("seed_accounts")
@anvil.tables.in_transaction
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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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


def _get_account_names_map():
    """Build {code: name_en} map from chart_of_accounts table."""
    try:
        return {r['code']: r.get('name_en', '') for r in app_tables.chart_of_accounts.search(is_active=True)}
    except Exception:
        return {code: name_en for code, name_en, _, _, _ in DEFAULT_ACCOUNTS}


# Tolerance for residual balance comparisons (e.g. treat tiny remainder as zero)
RESIDUAL_TOLERANCE = 0.01


# ===========================================================================
# PERIOD LOCK (accounting_period_locks: year, month, locked, locked_at, locked_by)
# ===========================================================================
def is_period_locked(entry_date):
    """
    Return True if the accounting period for entry_date (year/month) is locked.
    If table accounting_period_locks does not exist, raises so posting is never silently allowed.
    """
    if entry_date is None:
        return False
    d = entry_date.date() if hasattr(entry_date, 'date') else entry_date
    year = d.year if hasattr(d, 'year') else int(str(d)[:4])
    month = d.month if hasattr(d, 'month') else int(str(d)[5:7]) if len(str(d)) >= 7 else 1
    try:
        tbl = app_tables.accounting_period_locks
    except AttributeError:
        raise RuntimeError(
            'Accounting period locks table (accounting_period_locks) is missing. '
            'Create it in Anvil Data Tables with columns: year, month, locked, locked_at, locked_by.'
        )
    for r in tbl.search(year=year, month=month):
        if r.get('locked'):
            return True
    return False


@anvil.server.callable
@anvil.tables.in_transaction
def lock_period(year, month, token_or_email=None):
    """Lock an accounting period (year, month). No posting allowed for that month."""
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    try:
        tbl = app_tables.accounting_period_locks
        existing = list(tbl.search(year=int(year), month=int(month)))
        now = get_utc_now()
        if existing:
            existing[0].update(locked=True, locked_at=now, locked_by=_safe_str(user_email))
        else:
            tbl.add_row(year=int(year), month=int(month), locked=True, locked_at=now, locked_by=_safe_str(user_email))
        return {'success': True}
    except Exception as e:
        logger.exception("lock_period error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
@anvil.tables.in_transaction
def unlock_period(year, month, token_or_email=None):
    """Unlock an accounting period (year, month)."""
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    try:
        tbl = app_tables.accounting_period_locks
        for r in tbl.search(year=int(year), month=int(month)):
            r.update(locked=False, locked_at=get_utc_now(), locked_by=_safe_str(user_email))
        return {'success': True}
    except Exception as e:
        logger.exception("unlock_period error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def close_period(year, month, token_or_email=None):
    """Close (lock) an accounting period. No posting allowed for that month."""
    return lock_period(year, month, token_or_email)


@anvil.server.callable
def reopen_period(year, month, token_or_email=None):
    """Reopen (unlock) an accounting period."""
    return unlock_period(year, month, token_or_email)


@anvil.server.callable
def close_financial_year(year, token_or_email=None, confirm=False):
    """Lock all 12 months of the given year. Prevents any posting to prior year.
    Requires confirm=True to execute (guards against accidental invocation).
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    if not confirm:
        return {
            'success': False,
            'needs_confirmation': True,
            'message': f'This will lock ALL 12 months of year {year}. No entries can be posted to this year afterwards. Pass confirm=True to proceed.',
        }
    try:
        y = int(year)
        tbl = app_tables.accounting_period_locks
        now = get_utc_now()
        for month in range(1, 13):
            existing = list(tbl.search(year=y, month=month))
            if existing:
                existing[0].update(locked=True, locked_at=now, locked_by=_safe_str(user_email))
            else:
                tbl.add_row(year=y, month=month, locked=True, locked_at=now, locked_by=_safe_str(user_email))
        logger.info("Financial year %s closed (all 12 months locked) by %s", year, user_email)
        return {'success': True, 'message': f'Year {year} closed. All months locked.'}
    except Exception as e:
        logger.exception("close_financial_year error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def post_year_end_closing(year, token_or_email=None):
    """
    Post year-end closing journal entry.
    Closes all revenue (4xxx) and expense (5xxx, 6xxx) accounts to Retained Earnings (3100).
    This ensures that Balance Sheet shows cumulative retained earnings correctly,
    and next year's Income Statement starts from zero.

    Entry dated December 31st of the closing year.
    Idempotent: returns error if already posted for this year.

    Steps:
    1) Sum all revenue accounts (credit-normal) → DR each revenue, CR 3100
    2) Sum all expense accounts (debit-normal) → CR each expense, DR 3100
    Net effect on 3100 = net profit (or loss) for the year.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    try:
        y = int(year)
    except (TypeError, ValueError):
        return {'success': False, 'message': 'year must be a valid year (e.g. 2025)'}

    ref_id = f"year_end_{y}"
    # Idempotent check
    try:
        existing = list(app_tables.ledger.search(reference_type='year_end_closing', reference_id=ref_id))
        if existing:
            return {'success': False, 'message': f'Year-end closing for {y} is already posted. Cannot repeat.'}
    except Exception:
        pass

    if not _validate_account_exists('3100'):
        return {'success': False, 'message': 'Account 3100 (Retained Earnings) not found. Run seed_default_accounts or add it.'}

    entry_date = date(y, 12, 31)
    # Note: we do NOT check period lock here because closing IS the final entry for the year.
    # After closing, the user should lock the year via close_financial_year().

    import anvil.tables.query as q
    year_start = date(y, 1, 1)
    year_end = date(y, 12, 31)

    # Load chart of accounts
    acct_meta = {}
    for acct in app_tables.chart_of_accounts.search(is_active=True):
        acct_meta[acct.get('code')] = (acct.get('account_type') or '').strip().lower()

    # Aggregate revenue and expense for the year
    acct_totals = {}
    for _i, entry in enumerate(app_tables.ledger.search(
        date=q.all_of(q.greater_than_or_equal_to(year_start), q.less_than_or_equal_to(year_end))
    )):
        if _i >= MAX_LEDGER_SCAN:
            logger.error("close_year_end ABORTED: ledger scan cap reached (%d). Cannot safely close year with incomplete data.", MAX_LEDGER_SCAN)
            return {'success': False, 'message': f'عدد القيود ({MAX_LEDGER_SCAN:,}+) أكبر من الحد المسموح. لا يمكن إقفال السنة بأرقام ناقصة.'}
        code = entry.get('account_code', '')
        atype = acct_meta.get(code, '')
        if atype not in ('revenue', 'expense'):
            continue
        if code not in acct_totals:
            acct_totals[code] = {'debit': 0.0, 'credit': 0.0, 'type': atype}
        acct_totals[code]['debit'] += _round2(entry.get('debit', 0))
        acct_totals[code]['credit'] += _round2(entry.get('credit', 0))

    entries = []
    net_to_retained = 0.0  # positive = profit, negative = loss

    for code, info in sorted(acct_totals.items()):
        d = _round2(info['debit'])
        c = _round2(info['credit'])
        if info['type'] == 'revenue':
            # Revenue accounts have credit balance; close by debiting them
            bal = _round2(c - d)
            if bal > 0:
                entries.append({'account_code': code, 'debit': bal, 'credit': 0})
                net_to_retained += bal
            elif bal < 0:
                entries.append({'account_code': code, 'debit': 0, 'credit': abs(bal)})
                net_to_retained += bal
        elif info['type'] == 'expense':
            # Expense accounts have debit balance; close by crediting them
            bal = _round2(d - c)
            if bal > 0:
                entries.append({'account_code': code, 'debit': 0, 'credit': bal})
                net_to_retained -= bal
            elif bal < 0:
                entries.append({'account_code': code, 'debit': abs(bal), 'credit': 0})
                net_to_retained -= bal

    if not entries:
        return {'success': True, 'transaction_id': None, 'message': f'No revenue/expense activity in {y}. Nothing to close.', 'net_profit': 0}

    net_to_retained = _round2(net_to_retained)
    # Balance to Retained Earnings (3100)
    if net_to_retained > 0:
        # Profit → CR 3100
        entries.append({'account_code': '3100', 'debit': 0, 'credit': net_to_retained})
    elif net_to_retained < 0:
        # Loss → DR 3100
        entries.append({'account_code': '3100', 'debit': abs(net_to_retained), 'credit': 0})
    else:
        # Break-even: still post to properly close accounts
        entries.append({'account_code': '3100', 'debit': 0, 'credit': 0.01})
        entries.append({'account_code': '3100', 'debit': 0.01, 'credit': 0})

    desc = f"Year-end closing entry for {y} — Net {'Profit' if net_to_retained >= 0 else 'Loss'}: {abs(net_to_retained):,.2f} EGP"
    result = post_journal_entry(entry_date, entries, desc, 'year_end_closing', ref_id, user_email)

    if result.get('success'):
        logger.info("Year-end closing for %s posted (net %.2f) by %s", y, net_to_retained, user_email)
    return {
        'success': result.get('success', False),
        'transaction_id': result.get('transaction_id'),
        'message': result.get('message', desc),
        'net_profit': net_to_retained,
    }


@anvil.server.callable
def get_period_locks(year=None, token_or_email=None):
    """Return list of locked periods. If year given, only that year."""
    is_valid, _, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        tbl = app_tables.accounting_period_locks
        if year is not None:
            rows = list(tbl.search(year=int(year)))
        else:
            rows = list(tbl.search())
        result = [{'year': r.get('year'), 'month': r.get('month'), 'locked': bool(r.get('locked')), 'locked_at': str(r.get('locked_at', '')), 'locked_by': r.get('locked_by', '')} for r in rows]
        return {'success': True, 'data': result}
    except Exception as e:
        logger.exception("get_period_locks error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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


VALID_REFERENCE_TYPES = frozenset({
    'journal', 'treasury', 'purchase_invoice', 'payment',
    'import_cost_payment', 'vat_settlement', 'expense',
    'import_cost_migration', 'sales_invoice', 'customer_collection',
    'contract_receivable', 'opening_balance', 'year_end_closing',
})


def post_journal_entry(entry_date, entries, description, ref_type, ref_id, user_email):
    """
    Core double-entry posting function (internal, not callable directly).

    Parameters
    ----------
    entry_date : date or str
        The accounting date for the entry.
    entries : list[dict]
        Each dict has keys: account_code, debit (float), credit (float).
        Optional per-line: reference_type, reference_id (override default for this line).
    description : str
        Narrative for the transaction.
    ref_type : str
        Default reference_type (e.g. opening_balance, purchase_invoice, payment).
    ref_id : str
        Default reference_id (source document or period id).
    user_email : str
        Who is posting.

    Returns
    -------
    dict  {'success': True, 'transaction_id': ...} or {'success': False, 'message': ...}
    """
    # Validate user_email is provided and non-empty to protect audit trail integrity
    if not user_email or not str(user_email).strip():
        return {'success': False, 'message': 'user_email is required for audit trail'}

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

    if is_period_locked(parsed_date):
        return {'success': False, 'message': 'Accounting period is locked.'}

    if ref_type and ref_type not in VALID_REFERENCE_TYPES:
        return {'success': False, 'message': f"Invalid reference_type '{ref_type}'. Valid types: {sorted(VALID_REFERENCE_TYPES)}"}

    transaction_id = _uuid()
    now = get_utc_now()

    # FIX: Wrap ledger writes in a database transaction so that either ALL lines
    # are written or NONE (atomic). Previously a failure mid-way could leave an
    # unbalanced journal entry in the ledger.
    try:
        @anvil.tables.in_transaction
        def _do_post():
            for e in entries:
                line_ref_type = _safe_str(e.get('reference_type', ref_type))
                line_ref_id = _safe_str(e.get('reference_id', ref_id))
                app_tables.ledger.add_row(
                    id=_uuid(),
                    transaction_id=transaction_id,
                    date=parsed_date,
                    account_code=e['account_code'],
                    debit=_round2(e.get('debit', 0)),
                    credit=_round2(e.get('credit', 0)),
                    description=_safe_str(e.get('description', description)),
                    reference_type=line_ref_type,
                    reference_id=line_ref_id,
                    created_by=_safe_str(user_email),
                    created_at=now,
                )

        _do_post()
        _invalidate_report_cache()
        logger.info("Journal entry %s posted (%d lines) by %s", transaction_id, len(entries), user_email)
        return {'success': True, 'transaction_id': transaction_id}
    except Exception as e:
        logger.exception("post_journal_entry error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        _MAX_LEDGER_ROWS = 10000  # Safety cap — bounded ledger scan
        for i, r in enumerate(app_tables.ledger.search(**search_kwargs)):
            if i >= _MAX_LEDGER_ROWS:
                logger.warning("get_ledger_entries: ledger scan capped at %d rows", _MAX_LEDGER_ROWS)
                break
            results.append(_row_to_dict(r, LEDGER_COLS))

        results.sort(key=lambda x: (x.get('date', ''), x.get('created_at', '')))
        return {'success': True, 'data': results, 'count': len(results)}
    except Exception as e:
        logger.exception("get_ledger_entries error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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

        _MAX_ROWS = 50000  # Safety cap — bounded ledger scan per account
        for i, r in enumerate(app_tables.ledger.search(account_code=account_code)):
            if i >= _MAX_ROWS:
                logger.warning("get_account_balance: ledger scan capped at %d rows for account %s", _MAX_ROWS, account_code)
                break
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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


def _get_account_balance_internal(account_code, as_of_date=None):
    """Internal: ledger-only balance for account (no auth). For validation e.g. transfer sufficient balance."""
    acct = app_tables.chart_of_accounts.get(code=account_code)
    if not acct:
        return None
    cutoff = _safe_date(as_of_date)
    total_debit = 0.0
    total_credit = 0.0
    _MAX_ROWS = 50000  # Safety cap — bounded ledger scan per account
    for i, r in enumerate(app_tables.ledger.search(account_code=account_code)):
        if i >= _MAX_ROWS:
            logger.warning("_get_account_balance_internal: ledger scan capped at %d rows for account %s", _MAX_ROWS, account_code)
            break
        row_date = r.get('date')
        if isinstance(row_date, datetime):
            row_date = row_date.date()
        if cutoff and row_date and row_date > cutoff:
            continue
        total_debit += _round2(r.get('debit', 0))
        total_credit += _round2(r.get('credit', 0))
    acct_type = (acct.get('account_type') or '').strip().lower()
    if acct_type in ('asset', 'expense'):
        return _round2(total_debit - total_credit)
    return _round2(total_credit - total_debit)


# ===========================================================================
# TREASURY TRANSACTIONS (all via post_journal_entry; no direct ledger writes)
# ===========================================================================
LOAN_LIABILITY_ACCOUNT = '2500'
OTHER_INCOME_ACCOUNT = '4800'


def _ensure_loan_account():
    """Ensure account 2500 (Loans / Loan Liability) exists for loan_received transactions."""
    if _validate_account_exists(LOAN_LIABILITY_ACCOUNT):
        return True
    try:
        app_tables.chart_of_accounts.add_row(
            code=LOAN_LIABILITY_ACCOUNT,
            name_en='Loans Payable',
            name_ar='قروض مستحقة',
            account_type='liability',
            parent_code=None,
            is_active=True,
            created_at=get_utc_now(),
        )
        logger.info("Loan account %s auto-created", LOAN_LIABILITY_ACCOUNT)
        return True
    except Exception as e:
        logger.warning("Could not create loan account %s: %s", LOAN_LIABILITY_ACCOUNT, e)
        return False


def _ensure_other_income_account():
    """Ensure account 4800 (Other Income) exists for other_income transactions."""
    if _validate_account_exists(OTHER_INCOME_ACCOUNT):
        return True
    try:
        app_tables.chart_of_accounts.add_row(
            code=OTHER_INCOME_ACCOUNT,
            name_en='Other Income',
            name_ar='إيرادات أخرى',
            account_type='revenue',
            parent_code=None,
            is_active=True,
            created_at=get_utc_now(),
        )
        logger.info("Other income account %s auto-created", OTHER_INCOME_ACCOUNT)
        return True
    except Exception as e:
        logger.warning("Could not create other income account %s: %s", OTHER_INCOME_ACCOUNT, e)
        return False


def _is_cash_or_bank_account(account_code):
    """Return True if account is cash (1000) or bank (1010-1013)."""
    c = _safe_str(account_code or '').strip()
    if c == '1000':
        return True
    if len(c) == 4 and c.startswith('101'):
        return True
    return False


@anvil.server.callable
def create_treasury_transaction(transaction_type, amount, transaction_date, description, from_account=None, to_account=None, token_or_email=None):
    """
    Create a treasury transaction. All entries via post_journal_entry(); no direct ledger writes.
    transaction_type: capital_injection | loan_received | other_income | internal_transfer | cash_withdrawal | bank_deposit
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    amount = _round2(float(amount or 0))
    if amount <= 0:
        return {'success': False, 'message': 'Amount must be greater than zero'}
    transaction_date = _safe_date(transaction_date)
    if not transaction_date:
        return {'success': False, 'message': 'Valid transaction date required'}
    if is_period_locked(transaction_date):
        return {'success': False, 'message': 'Accounting period is locked for this date.'}
    desc = _safe_str(description or '').strip() or transaction_type.replace('_', ' ').title()

    tx_type = _safe_str(transaction_type or '').strip().lower()
    entries = []
    ref_id = f"treasury-{_uuid()[:8]}"

    if tx_type == 'capital_injection':
        to_account = _resolve_payment_account(to_account or 'bank')
        if not _validate_account_exists(to_account):
            return {'success': False, 'message': f'Account {to_account} not found'}
        if not _validate_account_exists('3000'):
            return {'success': False, 'message': 'Account 3000 (Equity) not found'}
        entries = [
            {'account_code': to_account, 'debit': amount, 'credit': 0},
            {'account_code': '3000', 'debit': 0, 'credit': amount},
        ]
        desc = f"Capital injection: {desc}"
    elif tx_type == 'loan_received':
        to_account = _resolve_payment_account(to_account or 'bank')
        if not _validate_account_exists(to_account):
            return {'success': False, 'message': f'Account {to_account} not found'}
        if not _ensure_loan_account():
            return {'success': False, 'message': f'Account {LOAN_LIABILITY_ACCOUNT} (Loans) not found and could not be created'}
        entries = [
            {'account_code': to_account, 'debit': amount, 'credit': 0},
            {'account_code': LOAN_LIABILITY_ACCOUNT, 'debit': 0, 'credit': amount},
        ]
        desc = f"Loan received: {desc}"
    elif tx_type == 'other_income':
        to_account = _resolve_payment_account(to_account or 'bank')
        if not _validate_account_exists(to_account):
            return {'success': False, 'message': f'Account {to_account} not found'}
        if not _ensure_other_income_account():
            return {'success': False, 'message': f'Account {OTHER_INCOME_ACCOUNT} (Other Income) not found and could not be created'}
        entries = [
            {'account_code': to_account, 'debit': amount, 'credit': 0},
            {'account_code': OTHER_INCOME_ACCOUNT, 'debit': 0, 'credit': amount},
        ]
        desc = f"Other income: {desc}"
    elif tx_type == 'internal_transfer':
        from_account = _resolve_payment_account(from_account)
        to_account = _resolve_payment_account(to_account)
        if from_account == to_account:
            return {'success': False, 'message': 'From and To account cannot be the same'}
        if not _validate_account_exists(from_account) or not _validate_account_exists(to_account):
            return {'success': False, 'message': 'From or To account not found'}
        bal = _get_account_balance_internal(from_account, transaction_date)
        if bal is None:
            return {'success': False, 'message': f'Could not get balance for {from_account}'}
        if not _is_cash_or_bank_account(from_account) or not _is_cash_or_bank_account(to_account):
            return {'success': False, 'message': 'Internal transfer only between cash/bank accounts'}
        if bal < amount:
            return {'success': False, 'message': f'Insufficient balance in {from_account}. Available: {_round2(bal)}'}
        entries = [
            {'account_code': from_account, 'debit': 0, 'credit': amount},
            {'account_code': to_account, 'debit': amount, 'credit': 0},
        ]
        desc = f"Internal transfer {from_account} → {to_account}: {desc}"
    elif tx_type == 'cash_withdrawal':
        # Cash withdrawal = internal transfer from bank to cash (NOT an expense).
        # FIX: Previously posted as DR 6090 (expense) which incorrectly reduced net profit.
        # Correct treatment: DR 1000 (Cash), CR from_account (Bank) — balance sheet only.
        from_account = _resolve_payment_account(from_account or 'bank')
        to_account = _resolve_payment_account(to_account or 'cash')
        if not _validate_account_exists(from_account):
            return {'success': False, 'message': f'Account {from_account} not found'}
        if not _validate_account_exists(to_account):
            return {'success': False, 'message': f'Account {to_account} not found'}
        if from_account == to_account:
            return {'success': False, 'message': 'From and To account cannot be the same for withdrawal'}
        bal = _get_account_balance_internal(from_account, transaction_date)
        if bal is not None and bal < amount:
            return {'success': False, 'message': f'Insufficient balance. Available: {_round2(bal)}'}
        entries = [
            {'account_code': to_account, 'debit': amount, 'credit': 0},
            {'account_code': from_account, 'debit': 0, 'credit': amount},
        ]
        desc = f"Cash withdrawal {from_account} → {to_account}: {desc}"
    elif tx_type == 'bank_deposit':
        from_account = _resolve_payment_account(from_account or 'cash')
        to_account = _resolve_payment_account(to_account or 'bank')
        if from_account == to_account:
            return {'success': False, 'message': 'From and To account cannot be the same'}
        if not _is_cash_or_bank_account(from_account) or not _is_cash_or_bank_account(to_account):
            return {'success': False, 'message': 'Bank deposit must be Cash → Bank'}
        if not _validate_account_exists(from_account) or not _validate_account_exists(to_account):
            return {'success': False, 'message': 'From or To account not found'}
        bal = _get_account_balance_internal(from_account, transaction_date)
        if bal is not None and bal < amount:
            return {'success': False, 'message': f'Insufficient cash balance. Available: {_round2(bal)}'}
        entries = [
            {'account_code': from_account, 'debit': 0, 'credit': amount},
            {'account_code': to_account, 'debit': amount, 'credit': 0},
        ]
        desc = f"Bank deposit {from_account} → {to_account}: {desc}"
    else:
        return {'success': False, 'message': f'Invalid transaction_type: {transaction_type}. Allowed: capital_injection, loan_received, other_income, internal_transfer, cash_withdrawal, bank_deposit'}

    result = post_journal_entry(transaction_date, entries, desc, 'treasury', ref_id, user_email)
    if result.get('success'):
        logger.info("Treasury %s %.2f posted by %s", tx_type, amount, user_email)
    return result


# ===========================================================================
# 3. SUPPLIERS & SERVICE SUPPLIERS CRUD
# → Moved to accounting_suppliers.py for maintainability.
#   All @anvil.server.callable functions are registered from that module.
#   Internal references kept via import for backward compatibility.
# ===========================================================================
try:
    from .accounting_suppliers import (
        get_suppliers, add_supplier, update_supplier, delete_supplier,
        get_suppliers_list_simple,
        get_service_suppliers, add_service_supplier, update_service_supplier,
        delete_service_supplier, get_service_suppliers_list_simple,
        SUPPLIER_COLS, SERVICE_SUPPLIER_COLS, VALID_SERVICE_TYPES,
    )
except ImportError:
    from accounting_suppliers import (
        get_suppliers, add_supplier, update_supplier, delete_supplier,
        get_suppliers_list_simple,
        get_service_suppliers, add_service_supplier, update_service_supplier,
        delete_service_supplier, get_service_suppliers_list_simple,
        SUPPLIER_COLS, SERVICE_SUPPLIER_COLS, VALID_SERVICE_TYPES,
    )


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
        # Stream results but only check invoice_number field — no need to load all columns
        for i, r in enumerate(app_tables.purchase_invoices.search()):
            if i >= 50000:
                break  # Safety cap
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
        err_type = type(e).__name__
        if 'unique' in err_type.lower() or 'duplicate' in err_type.lower() or 'constraint' in err_type.lower():
            return False
        logger.warning("posted_purchase_invoice_ids register (BLOCKED — fail-closed): %s", err_type)
        return False


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

        # Pre-fetch all suppliers once to avoid N+1 queries in the loop
        _sup_map = {}
        try:
            for _s in app_tables.suppliers.search():
                _sup_map[_s.get('id', '')] = _safe_str(_s.get('name', ''))
        except Exception:
            pass

        _MAX_INVOICES = 10000  # Safety cap
        for i, r in enumerate(rows):
            if i >= _MAX_INVOICES:
                break
            d = _row_to_dict(r, PURCHASE_INVOICE_COLS)
            # Parse items_json for convenience
            try:
                d['items'] = json.loads(d.get('items_json') or '[]')
            except (json.JSONDecodeError, TypeError):
                d['items'] = []
            # Add supplier_name from pre-fetched map (no N+1)
            d['supplier_name'] = _sup_map.get(d.get('supplier_id', ''), '')
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
            # Transit model: inventory_moved (optional column; safe if missing)
            try:
                d['inventory_moved'] = bool(r.get('inventory_moved'))
            except Exception:
                d['inventory_moved'] = False
            results.append(d)
        results.sort(key=lambda x: x.get('date', ''), reverse=True)
        return {'success': True, 'data': results, 'count': len(results)}
    except Exception as e:
        logger.exception("get_purchase_invoices error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
                ic_svc_sid = _safe_str(ic.get('service_supplier_id') or '')
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
                if ic_svc_sid:
                    ic_row['service_supplier_id'] = ic_svc_sid
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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


def _sum_1210_balance_for_invoice(invoice_id):
    """
    Transit balance per invoice: sum(debit - credit) on 1210 for this invoice.
    No reference_type filter on 1210 — all 1210 activity with reference_id=invoice_id included.
    Also includes 1210 entries with reference_id=cost_id for this invoice's import costs (import_cost_payment).
    """
    total = 0.0
    for entry in app_tables.ledger.search(account_code='1210', reference_id=invoice_id):
        total += _round2(entry.get('debit', 0)) - _round2(entry.get('credit', 0))
    for ic in app_tables.import_costs.search(purchase_invoice_id=invoice_id):
        cost_id = ic.get('id')
        if not cost_id:
            continue
        for entry in app_tables.ledger.search(account_code='1210', reference_id=cost_id):
            total += _round2(entry.get('debit', 0)) - _round2(entry.get('credit', 0))
    return _round2(total)


@anvil.server.callable
def move_purchase_to_inventory(invoice_id, token_or_email=None):
    """
    Move a posted purchase from 1210 (Inventory in Transit) to 1200 (Inventory).
    Validates: invoice status is posted/paid/partial (already posted to ledger), inventory_moved is False.
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
        status = (row.get('status') or '').lower().strip()
        if status not in ('posted', 'paid', 'partial'):
            return {'success': False, 'message': f"Invoice must be posted first (then it can be paid). Current status: '{row.get('status')}'."}
        # Idempotency: second call must return error; no duplicate JEs
        if row.get('inventory_moved'):
            return {'success': False, 'message': 'Invoice already moved to inventory. Duplicate move is not allowed.'}

        total_transit_cost = _sum_1210_balance_for_invoice(invoice_id)
        no_transit_balance = total_transit_cost <= 0
        inv_number = row.get('invoice_number', invoice_id)

        if not no_transit_balance:
            if not _validate_account_exists('1200'):
                return {'success': False, 'message': 'Account 1200 (Inventory) not found.'}
            if not _validate_account_exists('1210'):
                return {'success': False, 'message': 'Account 1210 (Inventory in Transit) not found.'}
            inv_date = row.get('date') or date.today()
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

        # Ensure inventory table has an item for this invoice (create if missing, else set in_stock)
        inv_items = list(app_tables.inventory.search(purchase_invoice_id=invoice_id))
        purchase_cost_egp = _round2(row.get('supplier_amount_egp') or row.get('total_egp') or 0)
        if not purchase_cost_egp and row.get('total') and row.get('exchange_rate_usd_to_egp'):
            try:
                purchase_cost_egp = _round2(float(row.get('total') or 0) * float(row.get('exchange_rate_usd_to_egp') or 0))
            except (TypeError, ValueError):
                pass
        import_total_egp = 0.0
        for ic in app_tables.import_costs.search(purchase_invoice_id=invoice_id):
            if (ic.get('cost_type') or '').lower().strip() == 'vat':
                continue
            import_total_egp += _round2(ic.get('amount_egp') or ic.get('amount', 0))
        import_total_egp = _round2(import_total_egp)
        now = get_utc_now()
        if inv_items:
            for item in inv_items:
                try:
                    item.update(status='in_stock', updated_at=now)
                except Exception as e:
                    logger.warning("Update inventory item status: %s", e)
            _update_inventory_import_totals(purchase_invoice_id=invoice_id)
        else:
            inv_item_id = _uuid()
            machine_code = _safe_str(row.get('machine_code') or row.get('invoice_number') or invoice_id)[:64]
            description = _safe_str(row.get('notes') or f"Machine from {inv_number}")[:500]
            try:
                app_tables.inventory.add_row(
                    id=inv_item_id,
                    machine_code=machine_code,
                    description=description or machine_code,
                    purchase_invoice_id=invoice_id,
                    contract_number=_safe_str(row.get('contract_number')) or None,
                    purchase_cost=purchase_cost_egp,
                    import_costs_total=import_total_egp,
                    total_cost=_round2(purchase_cost_egp + import_total_egp),
                    selling_price=0.0,
                    status='in_stock',
                    location='',
                    notes=f"Moved from transit: {inv_number}",
                    created_at=now,
                    updated_at=now,
                )
            except Exception as col_err:
                if 'machine_config_json' in str(col_err) or 'contract_number' in str(col_err):
                    try:
                        app_tables.inventory.add_row(
                            id=inv_item_id,
                            machine_code=machine_code,
                            description=description or machine_code,
                            purchase_invoice_id=invoice_id,
                            purchase_cost=purchase_cost_egp,
                            import_costs_total=import_total_egp,
                            total_cost=_round2(purchase_cost_egp + import_total_egp),
                            selling_price=0.0,
                            status='in_stock',
                            location='',
                            notes=f"Moved from transit: {inv_number}",
                            created_at=now,
                            updated_at=now,
                        )
                    except Exception:
                        raise
                else:
                    raise
            logger.info("Created inventory item %s for invoice %s (move to inventory)", inv_item_id, inv_number)

        if no_transit_balance:
            logger.info("Purchase invoice %s marked in inventory (no 1210 balance) by %s", inv_number, user_email)
            return {'success': True, 'transaction_id': None, 'total_transit_cost': 0, 'no_1210_balance': True}
        logger.info("Purchase invoice %s moved to inventory (1200) by %s, amount %.2f EGP", inv_number, user_email, total_transit_cost)
        return {'success': True, 'transaction_id': result['transaction_id'], 'total_transit_cost': total_transit_cost}
    except Exception as e:
        logger.exception("move_purchase_to_inventory error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


def _get_supplier_remaining_egp(invoice_id):
    """
    Remaining AP (2000) for this invoice: credits (purchase_invoice) - debits (payment).
    Filters by reference_type so opening_balance lines (reference_id=supplier_name) are
    excluded; payment matching stays invoice-scoped.
    """
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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def record_supplier_payment(invoice_id, amount, payment_method, payment_date,
                            currency_code='EGP', exchange_rate=None, notes='', token_or_email=None,
                            percentage=None, is_paid_in_full=False, bank_fee_egp=None):
    """
    Record a payment against a purchase invoice. FX is recognized on EVERY payment (partial or full).

    Policy:
    1) liability_slice_egp = portion of remaining being cleared (book value).
    2) payment_egp = actual amount paid converted at payment rate.
    3) fx_diff = liability_slice_egp - payment_egp → CR 4110 (gain) or DR 6110 (loss).
    4) Post: DR 2000 = liability_slice_egp, CR Bank = payment_egp; then 4110/6110 if fx_diff != 0.
    5) If bank_fee_egp > 0: DR 6090 (Bank/Other fees), CR Bank = bank_fee_egp. Does NOT affect supplier (2000).

    - amount: payment amount in currency_code (actual cash paid).
    - bank_fee_egp: optional; bank fees in EGP. Added to total debited from bank but does not reduce supplier balance.
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
        if remaining_egp < RESIDUAL_TOLERANCE:  # M-02: tolerance for floating-point residuals
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
        # FIX: Percentage + foreign currency + amount — also require valid invoice_rate for FX calc
        if currency_code != 'EGP' and pct is not None and amount_in > 0:
            if invoice_rate <= 0:
                return {'success': False, 'message': 'Invoice exchange rate is required for foreign-currency percentage payment (for FX gain/loss calculation).'}

        # 1) liability_slice_egp = portion of remaining being cleared (book value)
        if is_paid_in_full:
            liability_slice_egp = remaining_egp
        elif pct is not None:
            liability_slice_egp = _round2(remaining_egp * (pct / 100.0))
            if liability_slice_egp < RESIDUAL_TOLERANCE:  # M-02: tolerance for floating-point residuals
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
            if liability_slice_egp < RESIDUAL_TOLERANCE:  # M-02: tolerance for floating-point residuals
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
        bank_fee = _round2(float(bank_fee_egp or 0))
        if bank_fee < 0:
            bank_fee = 0

        cash_account = _resolve_payment_account(payment_method)
        if not _validate_account_exists(cash_account):
            return {'success': False, 'message': f'Payment account {cash_account} not found or inactive'}
        if not _validate_account_exists('2000'):
            return {'success': False, 'message': 'Account 2000 not found'}

        parsed_date = _safe_date(payment_date) or date.today()
        # Base description (without bank fee or FX — those get per-line descriptions)
        inv_num = row.get('invoice_number', invoice_id)
        base_desc = f"Payment for purchase invoice {inv_num}"
        if is_paid_in_full:
            base_desc += " (تسوية كاملة)"
        if currency_code != 'EGP':
            base_desc += f" — {amount_in:,.2f} {currency_code} @ {payment_rate} = {payment_egp:,.2f} EGP"
        if notes:
            base_desc += f" — {notes}"
        desc = base_desc  # default for AP and main bank lines

        # 4) Entries: DR 2000 = liability_slice_egp, CR Bank = payment_egp; then 4110/6110 if fx_diff != 0; then bank fee if any
        entries = [
            {'account_code': '2000', 'debit': liability_slice_egp, 'credit': 0},
            {'account_code': cash_account, 'debit': 0, 'credit': payment_egp},
        ]
        if fx_diff > 0:
            if not _validate_account_exists('4110'):
                return {'success': False, 'message': 'Account 4110 (Exchange Gain) not found. Run seed_default_accounts.'}
            fx_desc = base_desc + f" — أرباح فروق عملة (FX Gain): {fx_diff:,.2f} EGP"
            entries.append({'account_code': '4110', 'debit': 0, 'credit': fx_diff, 'description': fx_desc})
        elif fx_diff < 0:
            if not _validate_account_exists('6110'):
                return {'success': False, 'message': 'Account 6110 (Exchange Loss) not found. Run seed_default_accounts.'}
            fx_desc = base_desc + f" — خسائر فروق عملة (FX Loss): {-fx_diff:,.2f} EGP"
            entries.append({'account_code': '6110', 'debit': -fx_diff, 'credit': 0, 'description': fx_desc})
        if bank_fee > 0:
            if not _validate_account_exists('6090'):
                return {'success': False, 'message': 'Account 6090 (Other Expenses) not found for bank fees. Run seed_default_accounts.'}
            fee_desc = f"Bank fee for purchase invoice {inv_num} — {bank_fee:,.2f} EGP"
            entries.append({'account_code': '6090', 'debit': bank_fee, 'credit': 0, 'description': fee_desc})
            entries.append({'account_code': cash_account, 'debit': 0, 'credit': bank_fee, 'description': fee_desc})

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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


# ===========================================================================
# 5. IMPORT COSTS (EGP-only; attached to inventory; extensible types)
# ===========================================================================
IMPORT_COST_COLS = ['id', 'purchase_invoice_id', 'cost_type', 'description', 'amount', 'date',
                    'created_by', 'created_at', 'contract_number', 'payment_account', 'currency',
                    'service_supplier_id']

# Extensible: use import_cost_types table when present; else this default list
DEFAULT_IMPORT_COST_TYPES = [
    {'id': 'TAX', 'name': 'Tax', 'default_account': None, 'is_active': True},
    {'id': 'FREIGHT', 'name': 'Freight', 'default_account': None, 'is_active': True},
    {'id': 'CUSTOMS', 'name': 'Customs', 'default_account': None, 'is_active': True},
    {'id': 'FEES', 'name': 'Fees', 'default_account': None, 'is_active': True},
    {'id': 'OTHER', 'name': 'Other', 'default_account': None, 'is_active': True},
]

VALID_COST_TYPES = ('shipping', 'customs', 'insurance', 'clearance', 'transport', 'vat', 'other')

# H-02 FIX: Broader VAT detection — any cost_type containing these keywords → account 2110
VAT_COST_TYPE_KEYWORDS = ('vat', 'tax', 'ضريبة')


def _is_vat_cost_type(cost_type_raw):
    """Check if a cost_type string indicates VAT (broad matching)."""
    ct = (cost_type_raw or '').lower().strip()
    return any(kw in ct for kw in VAT_COST_TYPE_KEYWORDS)


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def add_import_cost(purchase_invoice_id=None, cost_type=None, amount=None, description='',
                    cost_date=None, payment_method='cash', contract_number=None, token_or_email=None,
                    currency_code='EGP', exchange_rate=None,
                    inventory_id=None, cost_type_id=None, original_amount=None, payment_account=None,
                    service_supplier_id=None):
    """
    Add an import cost attached to an inventory item (machine). EGP-only ledger.
    Transit model: if invoice.inventory_moved is False → DR 1210 (Inventory in Transit), CR payment_account.
    If invoice.inventory_moved is True → DR 1200 (Inventory), CR payment_account.
    Never post import cost to 2000. Recalculates landed cost on inventory row.

    If service_supplier_id is provided: posts JE immediately (DR Inventory → CR 2010 Service AP)
    and leaves paid_amount=0 so it can be paid later via pay_import_cost.

    Legacy (positional): add_import_cost(purchase_invoice_id, cost_type, amount, description=..., ...).
    New (keywords): inventory_id, cost_type_id, description, original_amount, payment_account, service_supplier_id.
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

        # Store payment account for when user pays; no JE here — only pay_import_cost posts to ledger (one JE per cost).
        credit_account = payment_account
        if not credit_account:
            credit_account = _resolve_payment_account(payment_method)

        parsed_date = _safe_date(cost_date) or date.today()
        cost_type_normalized = (cost_type or cost_type_name or '').lower().strip()[:20]
        # Avoid duplicate: same invoice, same type, same amount, same date (within last 10 min)
        try:
            cutoff = get_utc_now() - timedelta(minutes=10)
            for existing in app_tables.import_costs.search(purchase_invoice_id=pi_id):
                if _round2(existing.get('amount_egp') or existing.get('amount', 0)) != amount_egp:
                    continue
                if (existing.get('cost_type') or '').lower().strip()[:20] != cost_type_normalized:
                    continue
                ex_date = existing.get('date')
                if ex_date is not None and hasattr(ex_date, 'strftime'):
                    if ex_date != parsed_date:
                        continue
                else:
                    try:
                        if str(ex_date)[:10] != str(parsed_date)[:10]:
                            continue
                    except Exception:
                        continue
                ex_created = existing.get('created_at')
                if ex_created is not None and ex_created >= cutoff:
                    return {
                        'success': True,
                        'id': existing.get('id'),
                        'transaction_id': None,
                        'amount_egp': amount_egp,
                        'duplicate_skipped': True,
                    }
        except Exception as dup_err:
            logger.debug("Duplicate check: %s", dup_err)

        cost_id = _uuid()
        desc_text = _safe_str(description) or f"Import cost ({cost_type_name})"

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
            row_data['paid_amount'] = 0
        except Exception:
            pass

        # Link to service supplier if provided
        if service_supplier_id:
            try:
                ss = app_tables.service_suppliers.get(id=service_supplier_id)
                if not ss or not ss.get('is_active', True):
                    return {'success': False, 'message': 'Service supplier not found or inactive'}
                row_data['service_supplier_id'] = service_supplier_id
            except Exception:
                row_data['service_supplier_id'] = service_supplier_id

        try:
            app_tables.import_costs.add_row(**row_data)
        except Exception as col_err:
            err_str = str(col_err).lower()
            for key in ('currency', 'inventory_id', 'cost_type_id', 'original_currency', 'original_amount', 'exchange_rate', 'amount_egp', 'paid_amount', 'service_supplier_id'):
                row_data.pop(key, None)
            try:
                app_tables.import_costs.add_row(**row_data)
            except Exception:
                raise

        # If service supplier: post JE now (DR Inventory → CR 2010 Service AP)
        # Cost recognized immediately, payment deferred
        je_tid = None
        if service_supplier_id:
            inv_row_for_je = app_tables.purchase_invoices.get(id=pi_id) if pi_id else None
            inventory_moved = bool(inv_row_for_je and inv_row_for_je.get('inventory_moved'))
            debit_acct = '1200' if inventory_moved else '1210'
            credit_acct = '2010'  # Service Suppliers AP
            if not _validate_account_exists(credit_acct):
                # Auto-seed account 2010 if missing
                try:
                    app_tables.chart_of_accounts.add_row(
                        code='2010', name_en='Service Suppliers AP',
                        name_ar='ذمم دائنة - موردين خدمات',
                        account_type='liability', parent_code='2000',
                        is_active=True, created_at=get_utc_now()
                    )
                except Exception:
                    pass
            desc_je = f"Import cost ({cost_type_name}): {desc_text} [Service: {service_supplier_id[:8]}]"
            entries = [
                {'account_code': debit_acct, 'debit': amount_egp, 'credit': 0},
                {'account_code': credit_acct, 'debit': 0, 'credit': amount_egp},
            ]
            je_result = post_journal_entry(
                parsed_date, entries, desc_je, 'import_cost', cost_id, user_email,
                skip_lock_check=False
            )
            if not je_result.get('success'):
                logger.warning("Service supplier JE failed for cost %s: %s", cost_id, je_result.get('message'))
            else:
                je_tid = je_result.get('transaction_id')

        _update_inventory_import_totals(inventory_id=inv_id, purchase_invoice_id=pi_id)
        _recalc_supplier_amount_egp(pi_id)  # H-01: keep invoice row in sync

        logger.info("Import cost %s (%.2f EGP) added by %s%s", cost_type_name, amount_egp, user_email,
                     f" [service_supplier={service_supplier_id}]" if service_supplier_id else "")
        return {'success': True, 'id': cost_id, 'transaction_id': je_tid, 'amount_egp': amount_egp}
    except ValueError as ve:
        return {'success': False, 'message': str(ve)}
    except Exception as e:
        logger.exception("add_import_cost error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
            svc_sid = _safe_str(r.get('service_supplier_id') or '')
            svc_name = ''
            if svc_sid:
                try:
                    svc_row = app_tables.service_suppliers.get(id=svc_sid)
                    if svc_row:
                        svc_name = svc_row.get('name', '')
                except Exception:
                    pass
            result.append({
                'id': r.get('id'),
                'cost_type': r.get('cost_type', ''),
                'description': _safe_str(r.get('description', '')),
                'amount_egp': amt_egp,
                'paid_amount': paid,
                'remaining_egp': remaining,
                'payment_account': r.get('payment_account') or _resolve_payment_account('cash'),
                'service_supplier_id': svc_sid,
                'service_supplier_name': svc_name,
            })
        return {'success': True, 'costs': result}
    except Exception as e:
        logger.exception("get_import_costs_for_payment error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
            if inv and inv.get('exchange_rate_usd_to_egp'):
                rate = _round2(float(inv.get('exchange_rate_usd_to_egp') or 0))
            else:
                return {'success': False, 'message': 'Cannot compute import cost EGP amount: invoice exchange rate is missing. Set the rate on the purchase invoice first. | لا يمكن حساب المبلغ بالجنيه: سعر الصرف غير موجود في الفاتورة.'}
            if rate <= 0:
                return {'success': False, 'message': 'Invoice exchange rate is zero or invalid. Update the purchase invoice exchange rate. | سعر الصرف صفر أو غير صالح.'}
            amt = _round2(row.get('amount', 0))
            curr = _safe_str(row.get('currency') or 'EGP').upper()
            amt_egp = _round2(amt * (rate if curr == 'USD' else 1))
        else:
            amt_egp = _round2(amt_egp)
        paid = _round2(row.get('paid_amount') or 0)
        remaining = _round2(amt_egp - paid)
        if remaining <= 0:
            return {'success': False, 'message': 'هذه التكلفة مدفوعة بالكامل بالفعل | This cost is already fully paid.'}
        if amount_egp > remaining:
            return {'success': False, 'message': f'Pay amount ({amount_egp}) cannot exceed remaining ({remaining})'}
        credit_account = _resolve_payment_account(payment_method)
        if not _validate_account_exists(credit_account):
            return {'success': False, 'message': f'Payment account {credit_account} not found or inactive'}

        pi_id = row.get('purchase_invoice_id')
        svc_sid = None
        try:
            svc_sid = row.get('service_supplier_id')
        except Exception:
            pass

        # If linked to a service supplier: DR 2010 (clear AP) → CR Cash/Bank
        if svc_sid:
            debit_account = '2010'
            if not _validate_account_exists(debit_account):
                return {'success': False, 'message': 'Account 2010 (Service Suppliers AP) not found. Run seed_default_accounts.'}
        else:
            cost_type_raw = (row.get('cost_type') or '').lower().strip()
            is_vat = _is_vat_cost_type(cost_type_raw)
            if is_vat:
                if not _validate_account_exists('2110'):
                    return {'success': False, 'message': 'Account 2110 (VAT Input Recoverable) not found'}
                debit_account = '2110'
            else:
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

        # H-03 FIX: Ledger-level duplicate check — prevent same import cost posted twice
        try:
            existing_ledger = list(app_tables.ledger.search(
                reference_type='import_cost_payment', reference_id=import_cost_id
            ))
            if existing_ledger:
                ledger_total = _round2(sum(_round2(e.get('debit', 0)) for e in existing_ledger))
                if ledger_total >= amt_egp:
                    return {'success': False, 'message': 'This import cost is already fully posted to the ledger. | هذه التكلفة مسجلة بالكامل بالفعل في الدفتر.'}
        except Exception:
            pass  # If ledger search fails, proceed with payment (table-level check is primary)

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
        _recalc_supplier_amount_egp(row.get('purchase_invoice_id'))  # H-01: keep invoice row in sync
        logger.info("Import cost %s paid %.2f EGP by %s [DR %s, CR %s]", import_cost_id, amount_egp, user_email, debit_account, credit_account)
        return {'success': True, 'transaction_id': je_result.get('transaction_id'), 'paid_amount': new_paid}
    except Exception as e:
        logger.exception("pay_import_cost error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def sync_import_costs_paid_amount(token_or_email=None):
    """
    One-time fix: set paid_amount = amount_egp for import costs that have no paid_amount (or 0).
    In this system, add_import_cost always posts DR 1210/1200 CR Bank, so the cost is paid at add time.
    Syncing prevents the UI from showing a remaining amount and avoids recording a duplicate 'pay' later.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'edit')
    if not is_valid:
        return error
    try:
        updated = 0
        for row in app_tables.import_costs.search():
            amt = _round2(row.get('amount_egp') or row.get('amount', 0))
            if amt <= 0:
                continue
            paid = _round2(row.get('paid_amount') or 0)
            if paid >= amt:
                continue
            try:
                row.update(paid_amount=amt)
                updated += 1
            except Exception as e:
                logger.warning("sync_import_costs_paid_amount row %s: %s", row.get('id'), e)
        return {'success': True, 'updated': updated}
    except Exception as e:
        logger.exception("sync_import_costs_paid_amount error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


def _recalc_supplier_amount_egp(purchase_invoice_id):
    """
    H-01 FIX: Recalculate supplier_amount_egp on the purchase invoice row after import costs change.
    supplier_amount_egp = total_egp - sum(non-VAT import costs in EGP).
    Only updates if the invoice is already posted (has supplier_amount_egp set).
    """
    if not purchase_invoice_id:
        return
    try:
        inv = app_tables.purchase_invoices.get(id=purchase_invoice_id)
        if not inv or inv.get('status') != 'posted':
            return  # Only recalculate for posted invoices
        total_egp = _round2(inv.get('total_egp') or 0)
        if total_egp <= 0:
            return
        # Sum non-VAT import costs
        import_costs_egp = 0.0
        for ic in app_tables.import_costs.search(purchase_invoice_id=purchase_invoice_id):
            if _is_vat_cost_type(ic.get('cost_type')):
                continue
            amt = _round2(ic.get('amount_egp') or ic.get('amount', 0))
            if amt > 0:
                import_costs_egp += amt
        new_supplier_amount = _round2(total_egp - import_costs_egp)
        if new_supplier_amount != _round2(inv.get('supplier_amount_egp') or 0):
            try:
                inv.update(supplier_amount_egp=new_supplier_amount, updated_at=get_utc_now())
                logger.info("Recalculated supplier_amount_egp for %s: %.2f → %.2f",
                            inv.get('invoice_number', purchase_invoice_id),
                            _round2(inv.get('supplier_amount_egp') or 0), new_supplier_amount)
            except Exception as col_err:
                if 'supplier_amount_egp' not in str(col_err):
                    raise
    except Exception as e:
        logger.warning("_recalc_supplier_amount_egp error for %s: %s", purchase_invoice_id, e)


def _update_inventory_import_totals(purchase_invoice_id=None, inventory_id=None):
    """
    Recalculate import_costs_total and total_cost (EGP). Guarantee: total_cost = purchase_cost + import_costs_total.
    VAT (cost_type='vat') is excluded from inventory cost — it is posted to 2110 only.
    Call with either purchase_invoice_id (legacy) or inventory_id (new).
    """
    def _amt(r):
        return _round2(r.get('amount_egp') or r.get('amount', 0))

    def _is_vat(r):
        return _is_vat_cost_type(r.get('cost_type'))

    try:
        if inventory_id:
            try:
                cost_rows = list(app_tables.import_costs.search(inventory_id=inventory_id))
            except Exception:
                inv_item = app_tables.inventory.get(id=inventory_id)
                purchase_invoice_id = inv_item.get('purchase_invoice_id') if inv_item else None
                cost_rows = list(app_tables.import_costs.search(purchase_invoice_id=purchase_invoice_id)) if purchase_invoice_id else []
            import_total = _round2(sum(_amt(r) for r in cost_rows if not _is_vat(r)))
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
            import_total = _round2(sum(_amt(r) for r in cost_rows if not _is_vat(r)))
            for item in app_tables.inventory.search(purchase_invoice_id=purchase_invoice_id):
                purchase_cost = _round2(item.get('purchase_cost', 0))
                item.update(
                    import_costs_total=import_total,
                    total_cost=_round2(purchase_cost + import_total),
                    updated_at=get_utc_now(),
                )
    except Exception as e:
        logger.warning("_update_inventory_import_totals error: %s", e)


# VAT report: account 2110 (input) and 2100 (output)
VAT_INPUT_ACCOUNT = '2110'   # VAT Input Recoverable — ضريبة مدخلات قابلة للاسترداد (ليك)
VAT_OUTPUT_ACCOUNT = '2100'  # VAT Payable — ضريبة مخرجات مستحقة (عليك)
DEFAULT_VAT_RATE = 14.0      # 14% VAT-inclusive: vat_amount = price * rate / (100 + rate)


def _get_vat_rate():
    """Return VAT rate (e.g. 14 for 14%). From settings if available, else DEFAULT_VAT_RATE."""
    try:
        tbl = getattr(app_tables, 'settings', None)
        if tbl:
            row = tbl.get(setting_key='vat_rate') if hasattr(tbl, 'get') else None
            if row and row.get('setting_value') is not None:
                return _round2(float(row.get('setting_value')))
    except Exception:
        pass
    return DEFAULT_VAT_RATE


def _vat_balance(account_code, as_of_date=None):
    """Sum (debit - credit) for account up to as_of_date (inclusive). Ledger only."""
    total = 0.0
    for _i, entry in enumerate(app_tables.ledger.search(account_code=account_code)):
        if _i >= MAX_LEDGER_SCAN:
            logger.warning("Ledger scan cap reached (%d) in _vat_balance for account %s", MAX_LEDGER_SCAN, account_code)
            break
        ed = entry.get('date')
        if as_of_date and ed and ed > as_of_date:
            continue
        total += _round2(entry.get('debit', 0) or 0) - _round2(entry.get('credit', 0) or 0)
    return _round2(total)


@anvil.server.callable
def get_vat_report(as_of_date=None, date_from=None, date_to=None, token_or_email=None):
    """
    VAT position report. ليك و عليك عند الضرائب.
    - input_vat (2110): ضريبة مدخلات قابلة للاسترداد — ما ليك (رصيد مدين).
    - output_vat (2100): ضريبة مخرجات مستحقة — ما عليك للدولة (رصيد دائن).
    - net: input_vat - output_vat. موجب = ليك أكثر من عليك؛ سالب = عليك أكثر.
    Optional date_from/date_to: list movements in that period for detail.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        as_of = _safe_date(as_of_date)
        input_balance = _vat_balance(VAT_INPUT_ACCOUNT, as_of)
        output_balance_raw = _vat_balance(VAT_OUTPUT_ACCOUNT, as_of)
        # 2100 is liability: credit - debit = payable. Our _vat_balance returns debit - credit, so for 2100 "balance" as payable = -output_balance_raw.
        output_vat_payable = _round2(-output_balance_raw)  # positive = عليك
        net = _round2(input_balance - output_vat_payable)   # ليك - عليك

        detail = []
        if date_from is not None or date_to is not None:
            d_from = _safe_date(date_from)
            d_to = _safe_date(date_to)
            for acc, label in [(VAT_INPUT_ACCOUNT, 'Input VAT (2110)'), (VAT_OUTPUT_ACCOUNT, 'Output VAT (2100)')]:
                for _i, entry in enumerate(app_tables.ledger.search(account_code=acc)):
                    if _i >= MAX_LEDGER_SCAN:
                        logger.warning("Ledger scan cap reached (%d) in get_vat_report for account %s", MAX_LEDGER_SCAN, acc)
                        break
                    ed = entry.get('date')
                    if ed is None:
                        continue
                    if d_from and ed < d_from:
                        continue
                    if d_to and ed > d_to:
                        continue
                    dr = _round2(entry.get('debit', 0) or 0)
                    cr = _round2(entry.get('credit', 0) or 0)
                    detail.append({
                        'date': str(ed),
                        'account': acc,
                        'account_label': label,
                        'debit': dr,
                        'credit': cr,
                        'description': _safe_str(entry.get('description', '')),
                    })
        detail.sort(key=lambda x: (x['date'], x['account']))

        return {
            'success': True,
            'as_of_date': str(as_of) if as_of else None,
            'input_vat_balance': input_balance,
            'output_vat_balance': output_vat_payable,  # alias: 2100 payable
            'output_vat_payable': output_vat_payable,
            'net_position': net,
            'detail': detail,
        }
    except Exception as e:
        logger.exception("get_vat_report error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def settle_vat_for_period(date_from, date_to, settlement_account=None, token_or_email=None):
    """
    Monthly VAT settlement. Manual action only; period lock applies.
    Uses balances as of date_to (end of period).
    - If output_vat > input_vat: remit net_due to tax authority.
      Post: DR 2100 (output_vat), CR 2110 (input_vat), CR Bank (net_due).
    - If input_vat >= output_vat: clear output with input; remainder stays in 2110 (carry forward).
      Post: DR 2100 (output_vat), CR 2110 (output_vat).
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    d_from = _safe_date(date_from)
    d_to = _safe_date(date_to)
    if not d_to:
        return {'success': False, 'message': 'date_to is required'}
    settlement_account = (settlement_account or '1000').strip()
    if not _validate_account_exists(settlement_account):
        return {'success': False, 'message': f'Settlement account {settlement_account} not found or inactive'}
    if not _validate_account_exists(VAT_INPUT_ACCOUNT) or not _validate_account_exists(VAT_OUTPUT_ACCOUNT):
        return {'success': False, 'message': 'VAT accounts 2110/2100 not found. Run seed_default_accounts.'}
    try:
        input_vat = _vat_balance(VAT_INPUT_ACCOUNT, d_to)
        output_balance_raw = _vat_balance(VAT_OUTPUT_ACCOUNT, d_to)
        output_vat = _round2(-output_balance_raw)  # payable = credit - debit

        if abs(output_vat) < RESIDUAL_TOLERANCE and abs(input_vat) < RESIDUAL_TOLERANCE:
            return {'success': True, 'message': 'No VAT to settle; balances are zero.', 'settled': False}

        # Settlement entry date = date_to (month-end)
        if output_vat > input_vat:
            net_due = _round2(output_vat - input_vat)
            entries = [
                {'account_code': VAT_OUTPUT_ACCOUNT, 'debit': output_vat, 'credit': 0},
                {'account_code': VAT_INPUT_ACCOUNT, 'debit': 0, 'credit': input_vat},
                {'account_code': settlement_account, 'debit': 0, 'credit': net_due},
            ]
            desc = f"VAT settlement: remit {net_due:.2f} EGP to tax authority (output {output_vat:.2f} − input {input_vat:.2f})"
        else:
            # Clear full output with input; remainder in 2110 carries forward
            if output_vat <= 0:
                return {'success': True, 'message': 'Output VAT zero; nothing to clear.', 'settled': False}
            entries = [
                {'account_code': VAT_OUTPUT_ACCOUNT, 'debit': output_vat, 'credit': 0},
                {'account_code': VAT_INPUT_ACCOUNT, 'debit': 0, 'credit': output_vat},
            ]
            carry = _round2(input_vat - output_vat)
            desc = f"VAT settlement: clear output {output_vat:.2f} with input (carry forward 2110: {carry:.2f})"

        ref_id = f"vat_settle_{d_to}_{_uuid()[:8]}"
        result = post_journal_entry(d_to, entries, desc, 'vat_settlement', ref_id, user_email)
        if not result.get('success'):
            return result
        logger.info("VAT settlement for period ending %s by %s", d_to, user_email)
        return {
            'success': True,
            'settled': True,
            'transaction_id': result.get('transaction_id'),
            'input_vat': input_vat,
            'output_vat': output_vat,
            'period_to': str(d_to),
        }
    except Exception as e:
        logger.exception("settle_vat_for_period error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


# ===========================================================================
# 6. EXPENSES
# ===========================================================================
EXPENSE_COLS = [
    'id', 'date', 'category', 'description', 'amount', 'payment_method',
    'reference', 'account_code', 'status', 'created_by', 'created_at',
]

VALID_EXPENSE_CATEGORIES = ('salary', 'rent', 'utilities', 'transport', 'office', 'marketing', 'maintenance', 'other',
                            'salaries', 'travel')  # backward compatibility aliases
VALID_PAYMENT_METHODS = ('cash', 'bank', 'check')

# Map expense categories to default account codes
CATEGORY_ACCOUNT_MAP = {
    'salary': '6020',
    'salaries': '6020',      # backward compatibility
    'rent': '6000',
    'utilities': '6010',
    'transport': '6060',
    'travel': '6040',        # backward compatibility
    'office': '6030',
    'marketing': '6070',
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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        _MAX_ROWS = 10000  # Safety cap — bounded inventory scan
        search_lower = _safe_str(search).lower()
        _scan_count = 0
        for r in rows:
            _scan_count += 1
            if _scan_count > _MAX_ROWS:
                logger.warning("get_inventory: inventory scan capped at %d rows", _MAX_ROWS)
                break
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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        _MAX_ROWS = 5000  # Safety cap — bounded inventory scan
        for i, r in enumerate(rows):
            if i >= _MAX_ROWS:
                logger.warning("get_available_inventory_for_contract: scan capped at %d rows", _MAX_ROWS)
                break
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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def sell_inventory(item_id, contract_number, selling_price, sale_date=None,
                   token_or_email=None, vat_inclusive=True):
    """
    Record the sale of an inventory item (mark as sold).
    Only items with status 'in_stock' can be sold.
    COGS = Landed Cost (purchase_cost + import_costs_total = total_cost).

    Creates two journal entries:
    1) DR COGS (5000), CR Inventory (1200) — for total_cost (landed cost)
    2) DR Accounts Receivable (1100), CR Sales Revenue (4000) — for selling_price

    vat_inclusive: True (default) = selling_price includes VAT.
                   False = selling_price is net; VAT is added on top.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error

    selling_price = _round2(selling_price)
    if selling_price <= 0:
        return {'success': False, 'message': 'Selling price must be greater than zero'}
    if not contract_number:
        return {'success': False, 'message': 'Contract number is required'}

    # --- REVERSE REVENUE DOUBLE-COUNTING GUARD ---
    # Symmetric protection: block sell_inventory if post_contract_receivable
    # already recorded revenue (DR 1100) for this contract_number.
    # The forward guard in post_contract_receivable blocks the opposite order.
    existing_cr = list(app_tables.ledger.search(
        account_code='1100',
        reference_type='contract_receivable',
        reference_id=_safe_str(contract_number),
    ))
    if existing_cr:
        return {
            'success': False,
            'message': (
                f'تنبيه: تم فتح ذمم هذا العقد مسبقاً عبر contract_receivable. '
                f'لا يمكن تسجيل بيع مخزون لتجنب ازدواجية الإيراد. | '
                f'Revenue already opened via contract receivable for contract {contract_number}.'
            ),
        }
    # --- END REVERSE GUARD ---

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
        if not _validate_account_exists(VAT_OUTPUT_ACCOUNT):
            return {'success': False, 'message': 'Account 2100 (VAT Output Payable) not found. Run seed_default_accounts.'}

        # Entry 1: Record cost of goods sold (COGS = Landed Cost). VAT never affects 1200/1210.
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

        # Entry 2: Record sales — DR 1100 (total receivable), CR 4000 (net), CR 2100 (VAT)
        # FIX: Support both VAT-inclusive and VAT-exclusive selling_price.
        # FIX: Gross profit now correctly uses net_revenue (excluding VAT).
        vat_rate = _get_vat_rate()
        if vat_inclusive:
            # selling_price includes VAT: extract VAT from total
            vat_amount = _round2(selling_price * vat_rate / (100 + vat_rate))
            net_revenue = _round2(selling_price - vat_amount)
            total_receivable = selling_price  # customer pays this amount
        else:
            # selling_price is net (VAT-exclusive): add VAT on top
            net_revenue = selling_price
            vat_amount = _round2(selling_price * vat_rate / 100)
            total_receivable = _round2(selling_price + vat_amount)  # customer pays net + VAT

        vat_label = "VAT-incl" if vat_inclusive else "VAT-excl"
        sales_entries = [
            {'account_code': '1100', 'debit': total_receivable, 'credit': 0},
            {'account_code': '4000', 'debit': 0, 'credit': net_revenue},
            {'account_code': VAT_OUTPUT_ACCOUNT, 'debit': 0, 'credit': vat_amount},
        ]
        sales_result = post_journal_entry(
            sale_day, sales_entries,
            f"Sale of {row.get('machine_code', item_id)} — contract {contract_number} ({vat_label})",
            'sales_invoice', item_id, user_email,
        )
        if not sales_result.get('success'):
            return sales_result

        # FIX: Gross profit = Net Revenue (excl VAT) - COGS (landed cost)
        # Previously used selling_price (VAT-inclusive) which overstated profit.
        gross_profit = _round2(net_revenue - total_cost)
        margin = _round2((gross_profit / net_revenue * 100) if net_revenue else 0)

        row.update(
            contract_number=_safe_str(contract_number),
            selling_price=total_receivable,
            status='sold',
            updated_at=get_utc_now(),
        )
        logger.info("Inventory %s sold to contract %s (net_revenue %.2f, total_receivable %.2f, COGS %.2f, profit %.2f) by %s",
                     item_id, contract_number, net_revenue, total_receivable, total_cost, gross_profit, user_email)
        return {
            'success': True,
            'gross_profit': gross_profit,
            'margin_pct': margin,
            'landed_cost': total_cost,
            'net_revenue': net_revenue,
            'vat_amount': vat_amount,
            'total_receivable': total_receivable,
            'revenue': total_receivable,  # backward-compatible key
        }
    except Exception as e:
        logger.exception("sell_inventory error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
    Compute balances for all accounts from ledger (balance sheet and trial balance).
    If date_from is given, only entries between date_from and as_of_date are included.
    If only as_of_date is given, all entries up to as_of_date are included.
    Returns dict: {account_code: {'total_debit', 'total_credit', 'balance', 'type', ...}}.

    Natural balance (strict):
    - ASSET / expense: natural_balance = total_debit - total_credit. Overdraft only if < 0.
    - LIABILITY / equity / revenue: natural_balance = total_credit - total_debit.
    """
    cutoff = _safe_date(as_of_date)
    start = _safe_date(date_from)
    accounts = {}

    # Load chart of accounts; normalize account_type to lowercase for consistent balance sign
    for acct in app_tables.chart_of_accounts.search(is_active=True):
        code = acct.get('code')
        raw_type = (acct.get('account_type') or '').strip()
        accounts[code] = {
            'code': code,
            'name_en': acct.get('name_en', ''),
            'name_ar': acct.get('name_ar', ''),
            'type': raw_type.lower() if raw_type else '',
            'total_debit': 0.0,
            'total_credit': 0.0,
            'balance': 0.0,
        }

    # Aggregate from ledger only: sum(debit) and sum(credit) per account; no reference_type filter.
    # FIX: Use DB-level date filtering instead of full table scan for performance.
    try:
        import anvil.tables.query as q
        search_kwargs = {}
        if start and cutoff:
            search_kwargs['date'] = q.all_of(q.greater_than_or_equal_to(start), q.less_than_or_equal_to(cutoff))
        elif cutoff:
            search_kwargs['date'] = q.less_than_or_equal_to(cutoff)
        elif start:
            search_kwargs['date'] = q.greater_than_or_equal_to(start)

        _scan_truncated = False
        for _i, entry in enumerate(app_tables.ledger.search(**search_kwargs)):
            if _i >= MAX_LEDGER_SCAN:
                logger.warning("Ledger scan cap reached (%d) in _get_all_balances", MAX_LEDGER_SCAN)
                _scan_truncated = True
                break
            code = entry.get('account_code')
            if code not in accounts:
                continue
            d_val = _round2(entry.get('debit', 0))
            c_val = _round2(entry.get('credit', 0))
            accounts[code]['total_debit'] += d_val
            accounts[code]['total_credit'] += c_val
    except Exception as e:
        logger.warning("_get_all_balances ledger scan error: %s", e)

    # Natural balance by category: assets/expenses = debit - credit; rest = credit - debit
    for code, info in accounts.items():
        d = info['total_debit']
        c = info['total_credit']
        if info['type'] in ('asset', 'expense'):
            info['balance'] = _round2(d - c)
        else:
            info['balance'] = _round2(c - d)
        info['total_debit'] = _round2(d)
        info['total_credit'] = _round2(c)

    return accounts, _scan_truncated


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
    # Cache check
    _cache_key = ('trial_balance', str(date_from), str(date_to))
    _cached = _get_report_cache(_cache_key, user_email)
    if _cached is not None:
        return _cached
    try:
        accounts, _truncated = _get_all_balances(as_of_date=date_to, date_from=date_from)
        rows = []
        total_debit = 0.0
        total_credit = 0.0

        for code in sorted(accounts.keys()):
            info = accounts[code]
            if info['total_debit'] == 0 and info['total_credit'] == 0:
                continue  # Skip zero-activity accounts
            bal = info['balance']
            if bal == 0:
                continue  # Do not show as debit or credit when natural balance is zero
            # Trial balance: one column debit, one column credit (never both)
            if info['type'] in ('asset', 'expense'):
                tb_debit = bal if bal > 0 else 0
                tb_credit = abs(bal) if bal < 0 else 0
            else:
                tb_credit = bal if bal > 0 else 0
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
        result = {
            'success': True,
            'data': data_rows,
            'rows': rows,
            'total_debit': _round2(total_debit),
            'total_credit': _round2(total_credit),
            'is_balanced': abs(total_debit - total_credit) < 0.01,
            'date_from': date_from,
            'date_to': date_to,
        }
        if _truncated:
            result['truncated'] = True
            result['warning'] = f'تحذير: تم الوصول للحد الأقصى ({MAX_LEDGER_SCAN:,} قيد). النتائج قد تكون غير مكتملة.'
        _set_report_cache(_cache_key, result, user_email)
        return result
    except Exception as e:
        logger.exception("get_trial_balance error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
    # Cache check
    _cache_key = ('income_statement', str(date_from), str(date_to))
    _cached = _get_report_cache(_cache_key, user_email)
    if _cached is not None:
        return _cached

    try:
        d_from = _safe_date(date_from)
        d_to = _safe_date(date_to)

        # FIX: Use DB-level date filtering instead of full table scan for performance.
        import anvil.tables.query as q
        acct_totals = {}
        search_kwargs = {}
        if d_from and d_to:
            search_kwargs['date'] = q.all_of(q.greater_than_or_equal_to(d_from), q.less_than_or_equal_to(d_to))
        elif d_from:
            search_kwargs['date'] = q.greater_than_or_equal_to(d_from)
        elif d_to:
            search_kwargs['date'] = q.less_than_or_equal_to(d_to)
        _is_truncated = False
        for _i, entry in enumerate(app_tables.ledger.search(**search_kwargs)):
            if _i >= MAX_LEDGER_SCAN:
                logger.warning("Ledger scan cap reached (%d) in get_income_statement", MAX_LEDGER_SCAN)
                _is_truncated = True
                break
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
        result = {
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
        if _is_truncated:
            result['truncated'] = True
            result['warning'] = f'تحذير: تم الوصول للحد الأقصى ({MAX_LEDGER_SCAN:,} قيد). النتائج قد تكون غير مكتملة.'
        _set_report_cache(_cache_key, result, user_email)
        return result
    except Exception as e:
        logger.exception("get_income_statement error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_cash_flow_report(date_from, date_to, token_or_email=None):
    """
    Cash flow from ledger only. Operating: supplier payments (DR 2000), customer receipts (CR 1100), expenses (DR 6xxx).
    Investing: inventory (DR 1200, DR 1210). Financing: capital (CR 3000), loans (CR 2500).
    """
    is_valid, _, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    if not date_from or not date_to:
        return {'success': False, 'message': 'date_from and date_to required'}
    try:
        d_from = _safe_date(date_from)
        d_to = _safe_date(date_to)
        op_totals = {'Supplier payments': 0.0, 'Customer receipts': 0.0, 'Expenses': 0.0}
        inv_totals = {'Inventory (1200)': 0.0, 'Inventory (1210)': 0.0}
        fin_totals = {'Capital / Equity': 0.0, 'Loans received': 0.0}
        # FIX: Use DB-level date filtering instead of full table scan for performance.
        import anvil.tables.query as q
        cf_search = {}
        if d_from and d_to:
            cf_search['date'] = q.all_of(q.greater_than_or_equal_to(d_from), q.less_than_or_equal_to(d_to))
        elif d_from:
            cf_search['date'] = q.greater_than_or_equal_to(d_from)
        elif d_to:
            cf_search['date'] = q.less_than_or_equal_to(d_to)
        for _i, entry in enumerate(app_tables.ledger.search(**cf_search)):
            if _i >= MAX_LEDGER_SCAN:
                logger.warning("Ledger scan cap reached (%d) in get_cash_flow_report", MAX_LEDGER_SCAN)
                break
            code = _safe_str(entry.get('account_code', ''))
            d = _round2(entry.get('debit', 0))
            c = _round2(entry.get('credit', 0))
            if code == '2000' and d > 0:
                op_totals['Supplier payments'] -= d
            elif code == '1100' and c > 0:
                op_totals['Customer receipts'] += c
            elif code.startswith('6') and d > 0:
                op_totals['Expenses'] -= d
            elif code == '1200' and d > 0:
                inv_totals['Inventory (1200)'] -= d
            elif code == '1210' and d > 0:
                inv_totals['Inventory (1210)'] -= d
            elif code == '3000' and c > 0:
                fin_totals['Capital / Equity'] += c
            elif code == LOAN_LIABILITY_ACCOUNT and c > 0:
                fin_totals['Loans received'] += c
        operating = [{'label': k, 'amount': _round2(v)} for k, v in op_totals.items() if _round2(v) != 0]
        investing = [{'label': k, 'amount': _round2(v)} for k, v in inv_totals.items() if _round2(v) != 0]
        financing = [{'label': k, 'amount': _round2(v)} for k, v in fin_totals.items() if _round2(v) != 0]
        sum_op = _round2(sum(x['amount'] for x in operating))
        sum_inv = _round2(sum(x['amount'] for x in investing))
        sum_fin = _round2(sum(x['amount'] for x in financing))
        out = {
            'success': True,
            'date_from': str(d_from),
            'date_to': str(d_to),
            'operating': {'items': operating, 'total': sum_op},
            'investing': {'items': investing, 'total': sum_inv},
            'financing': {'items': financing, 'total': sum_fin},
            'net_change': _round2(sum_op + sum_inv + sum_fin),
        }
        return out
    except Exception as e:
        logger.exception("get_cash_flow_report error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_balance_sheet(as_of_date, token_or_email=None):
    """
    Balance sheet as of a given date. Presentation layer only; no ledger or posting changes.

    For account_type == 'asset':
    - Natural balance = debit - credit (from _get_all_balances).
    - If balance >= 0: show under Assets; add to total_assets.
    - If balance < 0 (credit balance = overdraft): do NOT show under Assets; add one line
      under Liabilities as "{account_name} (Overdraft)" with amount = abs(balance), and add
      that amount to total_liabilities so that Total Assets = Total Liabilities + Equity.

    Liabilities and equity: display as returned (credit - debit); no sign change.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    if not as_of_date:
        return {'success': False, 'message': 'as_of_date is required'}
    # Cache check
    _cache_key = ('balance_sheet', str(as_of_date), '')
    _cached = _get_report_cache(_cache_key, user_email)
    if _cached is not None:
        return _cached

    try:
        accounts, _truncated = _get_all_balances(as_of_date)
        asset_items = []
        total_assets = 0.0
        liability_items = []
        total_liabilities = 0.0
        equity_items = []
        total_equity = 0.0
        overdrafts = []  # asset accounts with balance < 0: show under Liabilities as (Overdraft)

        retained = 0.0

        for code in sorted(accounts.keys()):
            info = accounts[code]
            bal = info['balance']
            if bal == 0 and info['total_debit'] == 0 and info['total_credit'] == 0:
                continue

            if info['type'] == 'asset':
                # Natural balance for assets = debit - credit (already in info['balance'])
                if bal >= 0:
                    asset_items.append({
                        'code': code,
                        'name_en': info['name_en'],
                        'name_ar': info['name_ar'],
                        'balance': _round2(bal),
                    })
                    total_assets += bal
                else:
                    overdrafts.append({
                        'code': code,
                        'name_en': info['name_en'],
                        'name_ar': info['name_ar'],
                        'amount': _round2(abs(bal)),
                    })
            elif info['type'] == 'liability':
                item = {'code': code, 'name_en': info['name_en'], 'name_ar': info['name_ar'], 'balance': bal}
                liability_items.append(item)
                total_liabilities += bal
            elif info['type'] == 'equity':
                item = {'code': code, 'name_en': info['name_en'], 'name_ar': info['name_ar'], 'balance': bal}
                equity_items.append(item)
                total_equity += bal
            elif info['type'] == 'revenue':
                retained += bal
            elif info['type'] == 'expense':
                retained -= bal

        # Add overdrafts under Liabilities (after regular liabilities)
        for od in overdrafts:
            liability_items.append({
                'code': od['code'] + '_od',
                'name_en': (od['name_en'] or '') + ' (Overdraft)',
                'name_ar': (od['name_ar'] or '') + ' (سلفة)',
                'balance': od['amount'],
            })
            total_liabilities += od['amount']

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
        result = {
            'success': True,
            'data': data_obj,
            'as_of_date': str(_safe_date(as_of_date)),
            'assets': {'items': asset_items, 'total': _round2(total_assets)},
            'liabilities': {'items': liability_items, 'total': _round2(total_liabilities)},
            'equity': {'items': equity_items, 'total': _round2(total_equity)},
            'total_liabilities_equity': total_liabilities_equity,
            'is_balanced': abs(total_assets - total_liabilities_equity) < 0.01,
        }
        if _truncated:
            result['truncated'] = True
            result['warning'] = f'تحذير: تم الوصول للحد الأقصى ({MAX_LEDGER_SCAN:,} قيد). النتائج قد تكون غير مكتملة.'
        _set_report_cache(_cache_key, result, user_email)
        return result
    except Exception as e:
        logger.exception("get_balance_sheet error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


# ===========================================================================
# UNIFIED REPORTING ENGINE (ledger-only; no HTML in report logic)
# ===========================================================================
def _normalize_trial_balance(data):
    if not data.get('success') or not data.get('rows'):
        return None
    columns = ['Account', 'Debit', 'Credit']
    rows = []
    for r in data.get('rows', []):
        rows.append({
            'Account': (r.get('name_en') or r.get('name_ar') or r.get('code', '')),
            'Debit': _round2(r.get('debit', 0)),
            'Credit': _round2(r.get('credit', 0)),
        })
    return {'title': 'Trial Balance', 'columns': columns, 'rows': rows, 'summary': {'total_debit': data.get('total_debit', 0), 'total_credit': data.get('total_credit', 0), 'is_balanced': data.get('is_balanced', False)}}


def _normalize_income_statement(data):
    if not data.get('success'):
        return None
    columns = ['Category', 'Account', 'Amount']
    rows = []
    for i in data.get('revenue', {}).get('items', []):
        rows.append({'Category': 'Revenue', 'Account': i.get('name_en', ''), 'Amount': _round2(i.get('amount', 0))})
    for i in data.get('cogs', {}).get('items', []):
        rows.append({'Category': 'COGS', 'Account': i.get('name_en', ''), 'Amount': _round2(i.get('amount', 0))})
    for i in data.get('expenses', {}).get('items', []):
        rows.append({'Category': 'Expense', 'Account': i.get('name_en', ''), 'Amount': _round2(i.get('amount', 0))})
    total_rev = data.get('revenue', {}).get('total', 0)
    total_exp = _round2(data.get('cogs', {}).get('total', 0) + data.get('expenses', {}).get('total', 0))
    net = data.get('net_profit', 0)
    return {'title': 'Income Statement', 'columns': columns, 'rows': rows, 'summary': {'total_revenue': total_rev, 'total_expenses': total_exp, 'net_income': net}}


def _normalize_balance_sheet(data):
    if not data.get('success'):
        return None
    columns = ['Category', 'Account', 'Amount']
    rows = []
    for i in data.get('assets', {}).get('items', []):
        rows.append({'Category': 'Assets', 'Account': i.get('name_en', ''), 'Amount': _round2(i.get('balance', 0))})
    for i in data.get('liabilities', {}).get('items', []):
        rows.append({'Category': 'Liabilities', 'Account': i.get('name_en', ''), 'Amount': _round2(i.get('balance', 0))})
    for i in data.get('equity', {}).get('items', []):
        rows.append({'Category': 'Equity', 'Account': i.get('name_en', ''), 'Amount': _round2(i.get('balance', 0))})
    return {'title': 'Balance Sheet', 'columns': columns, 'rows': rows, 'summary': {'total_assets': data.get('assets', {}).get('total', 0), 'total_liabilities_equity': data.get('total_liabilities_equity', 0), 'is_balanced': data.get('is_balanced', False)}}


def _normalize_cash_flow(data):
    if not data.get('success'):
        return None
    columns = ['Section', 'Label', 'Amount']
    rows = []
    for i in data.get('operating', {}).get('items', []):
        rows.append({'Section': 'Operating', 'Label': i.get('label', ''), 'Amount': _round2(i.get('amount', 0))})
    for i in data.get('investing', {}).get('items', []):
        rows.append({'Section': 'Investing', 'Label': i.get('label', ''), 'Amount': _round2(i.get('amount', 0))})
    for i in data.get('financing', {}).get('items', []):
        rows.append({'Section': 'Financing', 'Label': i.get('label', ''), 'Amount': _round2(i.get('amount', 0))})
    return {'title': 'Cash Flow', 'columns': columns, 'rows': rows, 'summary': {'operating': data.get('operating', {}).get('total', 0), 'investing': data.get('investing', {}).get('total', 0), 'financing': data.get('financing', {}).get('total', 0), 'net_change': data.get('net_change', 0)}}


@anvil.server.callable
def generate_report(report_name, filters, token_or_email=None):
    """
    Central reporting: returns { title, columns, rows, summary }. No HTML. All from ledger.
    report_name: trial_balance | income_statement | balance_sheet | cash_flow | vat_report | supplier_aging | inventory_valuation | fx_report | treasury_summary
    filters: dict with date_from, date_to, as_of_date, etc. as required by each report.
    """
    is_valid, _, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    filters = filters or {}
    report_name = _safe_str(report_name or '').strip().lower()
    try:
        if report_name == 'trial_balance':
            data = get_trial_balance(date_from=filters.get('date_from'), date_to=filters.get('date_to'), token_or_email=token_or_email)
            out = _normalize_trial_balance(data)
        elif report_name == 'income_statement':
            data = get_income_statement(filters.get('date_from'), filters.get('date_to'), token_or_email=token_or_email)
            out = _normalize_income_statement(data)
        elif report_name == 'balance_sheet':
            data = get_balance_sheet(filters.get('as_of_date'), token_or_email=token_or_email)
            out = _normalize_balance_sheet(data)
        elif report_name == 'cash_flow':
            data = get_cash_flow_report(filters.get('date_from'), filters.get('date_to'), token_or_email=token_or_email)
            out = _normalize_cash_flow(data)
        elif report_name == 'treasury_summary':
            data = get_treasury_summary(token_or_email=token_or_email)
            if not data.get('success'):
                return {'success': False, 'message': data.get('message', '')}
            columns = ['Account', 'Current Balance']
            rows = [{'Account': a.get('account_name', ''), 'Current Balance': _round2(a.get('current_balance', 0))} for a in (data.get('data') or data.get('accounts') or [])]
            out = {'title': 'Treasury Summary', 'columns': columns, 'rows': rows, 'summary': {'grand_total': data.get('grand_total', 0)}}
        elif report_name == 'contract_profitability':
            data = get_contract_profitability(contract_number=filters.get('contract_number'), token_or_email=token_or_email)
            if not data.get('success'):
                return {'success': False, 'message': data.get('message', '')}
            data_list = data.get('data', [])
            columns = ['Contract #', 'Client', 'Revenue', 'Costs', 'Profit', 'Margin %']
            rows = [{'Contract #': r.get('contract_number', ''), 'Client': r.get('client_name', ''), 'Revenue': _round2(r.get('revenue', 0)), 'Costs': _round2(r.get('costs', 0)), 'Profit': _round2(r.get('profit', 0)), 'Margin %': _round2(r.get('margin', 0))} for r in data_list]
            out = {'title': 'Contract Profitability', 'columns': columns, 'rows': rows, 'summary': {'total_revenue': data.get('grand_revenue', 0), 'total_cost': data.get('grand_cost', 0), 'grand_profit': data.get('grand_profit', 0)}}
        elif report_name == 'expenses':
            data = get_expenses(date_from=filters.get('date_from'), date_to=filters.get('date_to'), category=filters.get('category'), token_or_email=token_or_email)
            if not data.get('success'):
                return {'success': False, 'message': data.get('message', '')}
            data_list = data.get('data', [])
            columns = ['Date', 'Category', 'Description', 'Amount']
            rows = [{'Date': str(r.get('date', '')), 'Category': r.get('category', ''), 'Description': r.get('description', ''), 'Amount': _round2(r.get('amount', 0))} for r in data_list]
            out = {'title': 'Expenses', 'columns': columns, 'rows': rows, 'summary': {'total_amount': data.get('total_amount', 0), 'count': data.get('count', 0)}}
        elif report_name == 'general_ledger':
            data = get_ledger_entries(account_code=filters.get('account_code'), date_from=filters.get('date_from'), date_to=filters.get('date_to'), token_or_email=token_or_email)
            if not data.get('success'):
                return {'success': False, 'message': data.get('message', '')}
            data_list = data.get('data', [])
            acct_map = _get_account_names_map()
            columns = ['Date', 'Account', 'Description', 'Debit', 'Credit']
            rows = []
            for r in data_list:
                code = r.get('account_code', '')
                label = acct_map.get(code, '')
                rows.append({'Date': str(r.get('date', '')), 'Account': f"{code} - {label}" if label else code, 'Description': r.get('description', ''), 'Debit': _round2(r.get('debit', 0)), 'Credit': _round2(r.get('credit', 0))})
            out = {'title': 'General Ledger', 'columns': columns, 'rows': rows, 'summary': {'count': data.get('count', 0)}}
        elif report_name == 'exchange_rates':
            data = get_exchange_rates(token_or_email=token_or_email)
            if not data.get('success'):
                return {'success': False, 'message': data.get('message', '')}
            data_list = data.get('data', [])
            columns = ['Currency', 'Rate to EGP', 'Last Updated']
            rows = [{'Currency': r.get('currency_code', ''), 'Rate to EGP': _round2(r.get('rate_to_egp', 0)), 'Last Updated': str(r.get('updated_at') or r.get('effective_date') or '')} for r in data_list]
            out = {'title': 'Exchange Rates', 'columns': columns, 'rows': rows, 'summary': {}}
        elif report_name == 'cash_bank_statement':
            data = get_cash_bank_statement(account_code=filters.get('account_code'), date_from=filters.get('date_from'), date_to=filters.get('date_to'), token_or_email=token_or_email)
            if not data.get('success'):
                return {'success': False, 'message': data.get('message', '')}
            data_list = data.get('data', [])
            columns = ['Date', 'Account', 'Description', 'Debit', 'Credit', 'Balance']
            rows = [{'Date': str(r.get('date', '')), 'Account': r.get('account_name', r.get('account_code', '')), 'Description': r.get('description', ''), 'Debit': _round2(r.get('debit', 0)), 'Credit': _round2(r.get('credit', 0)), 'Balance': _round2(r.get('balance', 0))} for r in data_list]
            out = {'title': 'Cash & Bank Statement', 'columns': columns, 'rows': rows, 'summary': {'count': data.get('count', 0)}}
        elif report_name == 'vat_report':
            data = get_vat_report(as_of_date=filters.get('as_of_date'), date_from=filters.get('date_from'), date_to=filters.get('date_to'), token_or_email=token_or_email)
            if not data.get('success'):
                return {'success': False, 'message': data.get('message', '')}
            detail = data.get('detail', [])
            columns = ['Date', 'Account', 'Description', 'Debit', 'Credit']
            rows = [{'Date': r.get('date', ''), 'Account': r.get('account_label', r.get('account', '')), 'Description': r.get('description', ''), 'Debit': _round2(r.get('debit', 0)), 'Credit': _round2(r.get('credit', 0))} for r in detail]
            out = {'title': 'VAT Report', 'columns': columns, 'rows': rows, 'summary': {'input_vat': data.get('input_vat_balance', 0), 'output_vat': data.get('output_vat_payable', 0), 'net': data.get('net_position', 0)}}
        elif report_name == 'opening_balances':
            data = get_opening_balances(entity_type=filters.get('entity_type', ''), token_or_email=token_or_email)
            if not data.get('success'):
                return {'success': False, 'message': data.get('message', '')}
            data_list = data.get('data', [])
            columns = ['Name', 'Type', 'Opening Balance', 'Updated At']
            rows = [{'Name': r.get('name', ''), 'Type': r.get('type', ''), 'Opening Balance': _round2(r.get('opening_balance', 0)), 'Updated At': str(r.get('updated_at', ''))} for r in data_list]
            out = {'title': 'Opening Balances', 'columns': columns, 'rows': rows, 'summary': {'count': data.get('count', 0)}}
        elif report_name == 'advanced_account_statement':
            data = get_advanced_account_statement(
                entity_type=filters.get('entity_type', 'customer'),
                entity_id=filters.get('entity_id'),
                date_from=filters.get('date_from'),
                date_to=filters.get('date_to'),
                invoice_id=filters.get('invoice_id'),
                transaction_type=filters.get('transaction_type'),
                include_aging=bool(filters.get('include_aging')),
                token_or_email=token_or_email,
            )
            if not data.get('success'):
                return {'success': False, 'message': data.get('message', '')}
            summary = {
                'opening_balance': data.get('opening_balance', 0),
                'closing_balance': data.get('closing_balance', 0),
            }
            aging = data.get('aging')
            if aging:
                summary['aging_current'] = aging.get('current', 0)
                summary['aging_30'] = aging.get('30', 0)
                summary['aging_60'] = aging.get('60', 0)
                summary['aging_90_plus'] = aging.get('90+', 0)
                summary['total_outstanding'] = aging.get('total_outstanding', 0)
            if data.get('summary'):
                columns = ['Entity', 'Opening Balance', 'Period Debit', 'Period Credit', 'Closing Balance']
                rows = [
                    {
                        'Entity': r.get('entity_name', ''),
                        'Opening Balance': _round2(r.get('opening_balance', 0)),
                        'Period Debit': _round2(r.get('period_debit', 0)),
                        'Period Credit': _round2(r.get('period_credit', 0)),
                        'Closing Balance': _round2(r.get('closing_balance', 0)),
                    }
                    for r in data['summary']
                ]
            else:
                columns = ['Date', 'Ref Type', 'Ref ID', 'Description', 'Debit', 'Credit', 'Running Balance']
                rows = [
                    {
                        'Date': str(r.get('date', '')) if r.get('date') else '',
                        'Ref Type': r.get('reference_type', ''),
                        'Ref ID': r.get('reference_id', ''),
                        'Description': r.get('description', ''),
                        'Debit': _round2(r.get('debit', 0)),
                        'Credit': _round2(r.get('credit', 0)),
                        'Running Balance': _round2(r.get('balance_after_transaction', 0)),
                    }
                    for r in data.get('rows', [])
                ]
            out = {'title': 'Advanced Account Statement - ' + (data.get('entity_name', '') or 'Statement'), 'columns': columns, 'rows': rows, 'summary': summary}
        else:
            return {'success': False, 'message': f'Unknown report: {report_name}. Supported: trial_balance, income_statement, balance_sheet, cash_flow, treasury_summary, contract_profitability, expenses, general_ledger, exchange_rates, cash_bank_statement, vat_report, opening_balances, advanced_account_statement'}
        if out is None:
            return {'success': False, 'message': 'Report returned no data'}
        return {'success': True, 'report_name': report_name, 'title': out['title'], 'columns': out['columns'], 'rows': out['rows'], 'summary': out.get('summary', {})}
    except Exception as e:
        logger.exception("generate_report error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


def _register_pdf_arabic_font():
    """
    Register the same font used in Contract and Quotation PDFs (Segoe UI / Arial)
    so accounting export PDFs match and Arabic displays correctly (no black squares).
    ContractPrintForm & QuotationPrintForm use: font-family 'Segoe UI', 'Arial', 'Helvetica Neue'.
    """
    import os
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return None
    font_name = 'ExportArabic'
    try:
        if pdfmetrics.getFont(font_name):
            return font_name
    except Exception:
        pass
    candidates = []
    windir = os.environ.get('WINDIR', os.environ.get('SystemRoot', 'C:\\Windows'))
    if windir:
        candidates.append(os.path.join(windir, 'Fonts', 'segoeui.ttf'))
        candidates.append(os.path.join(windir, 'Fonts', 'segoeuil.ttf'))
        candidates.append(os.path.join(windir, 'Fonts', 'arial.ttf'))
        candidates.append(os.path.join(windir, 'Fonts', 'tahoma.ttf'))
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        for name in ('segoeui.ttf', 'DejaVuSans.ttf', 'arial.ttf', 'Arial.ttf'):
            p = os.path.join(base, 'fonts', name)
            if p not in candidates:
                candidates.append(p)
    except Exception:
        pass
    candidates.extend([
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    ])
    for path in candidates:
        if path and os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, path))
                return font_name
            except Exception:
                continue
    return None


def _export_summary_lines(report_name, summary):
    """Build list of (label, value) for report summary to show in PDF/Excel/CSV. Value as number."""
    if not summary or not isinstance(summary, dict):
        return []
    out = []
    if report_name == 'trial_balance':
        out.append(('Total Debit', _round2(summary.get('total_debit', 0))))
        out.append(('Total Credit', _round2(summary.get('total_credit', 0))))
        if summary.get('is_balanced') is not None:
            out.append(('Balanced', 'Yes' if summary.get('is_balanced') else 'No'))
    elif report_name == 'income_statement':
        out.append(('Total Revenue', _round2(summary.get('total_revenue', 0))))
        out.append(('Total Expenses', _round2(summary.get('total_expenses', 0))))
        out.append(('Net Income', _round2(summary.get('net_income', 0))))
    elif report_name == 'balance_sheet':
        out.append(('Total Assets', _round2(summary.get('total_assets', 0))))
        out.append(('Total Liabilities + Equity', _round2(summary.get('total_liabilities_equity', 0))))
        if summary.get('is_balanced') is not None:
            out.append(('Balanced', 'Yes' if summary.get('is_balanced') else 'No'))
    elif report_name == 'cash_flow':
        out.append(('Operating', _round2(summary.get('operating', 0))))
        out.append(('Investing', _round2(summary.get('investing', 0))))
        out.append(('Financing', _round2(summary.get('financing', 0))))
        out.append(('Net Change', _round2(summary.get('net_change', 0))))
    elif report_name == 'advanced_account_statement':
        out.append(('Opening Balance', _round2(summary.get('opening_balance', 0))))
        out.append(('Closing Balance', _round2(summary.get('closing_balance', 0))))
        if 'total_outstanding' in summary:
            out.append(('Total Outstanding', _round2(summary.get('total_outstanding', 0))))
            out.append(('Aging 0-30 days', _round2(summary.get('aging_current', 0))))
            out.append(('Aging 31-60 days', _round2(summary.get('aging_30', 0))))
            out.append(('Aging 61-90 days', _round2(summary.get('aging_60', 0))))
            out.append(('Aging 90+ days', _round2(summary.get('aging_90_plus', 0))))
    else:
        for k, v in summary.items():
            if v is not None and k not in ('is_balanced',):
                out.append((k.replace('_', ' ').title(), _round2(v) if isinstance(v, (int, float)) else v))
    return out


def _pdf_cell_text(val, use_arabic_reshape=True):
    """Prepare cell text for ReportLab: escape XML, optional Arabic reshape for correct display."""
    if val is None:
        return ''
    s = str(val).strip()
    if not s:
        return ''
    has_arabic = any('\u0600' <= c <= '\u06FF' for c in s)
    if has_arabic and use_arabic_reshape:
        try:
            import arabic_reshaper
            from bidi.algorithm import get_display
            s = get_display(arabic_reshaper.reshape(s))
        except Exception:
            pass
    s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    return s


@anvil.server.callable
def export_report(report_name, filters, format='csv', token_or_email=None):
    """
    Export report as csv, excel, or pdf. Uses generate_report for data.
    Every export includes report title and period (From/To or As of) in content and in filename.
    format: 'pdf' | 'excel' | 'csv'
    """
    is_valid, _, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    filters = filters or {}
    res = generate_report(report_name, filters, token_or_email=token_or_email)
    if not res.get('success'):
        return res
    title = res.get('title', 'Report')
    columns = res.get('columns', [])
    rows = res.get('rows', [])
    summary = res.get('summary') or {}
    summary_lines = _export_summary_lines(report_name, summary)
    period_label, filename_slug = _export_period_info(filters)
    base_filename = "{}_{}".format(report_name, filename_slug)
    fmt = _safe_str(format or 'csv').strip().lower()
    try:
        if fmt == 'csv':
            import io
            import csv
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow([title])
            w.writerow([period_label])
            w.writerow([])
            w.writerow(columns)
            for r in rows:
                w.writerow([r.get(col, '') for col in columns])
            if summary_lines:
                w.writerow([])
                w.writerow(['Summary', ''])
                for lbl, val in summary_lines:
                    w.writerow([lbl, val if isinstance(val, str) else '{:,.2f}'.format(val)])
            return {'success': True, 'format': 'csv', 'content': buf.getvalue(), 'filename': "{}.csv".format(base_filename)}
        elif fmt == 'excel':
            try:
                import xlsxwriter
                import io
            except ImportError:
                return {'success': False, 'message': 'xlsxwriter not installed. Use csv or install xlsxwriter.'}
            buf = io.BytesIO()
            wb = xlsxwriter.Workbook(buf, {'in_memory': True})
            ws = wb.add_worksheet((title or 'Report')[:31])
            ws.write(0, 0, title or 'Report')
            ws.write(1, 0, period_label)
            for c, col in enumerate(columns):
                ws.write(2, c, col)
            for r, row in enumerate(rows):
                for c, col in enumerate(columns):
                    ws.write(r + 3, c, row.get(col, ''))
            row_cur = 3 + len(rows)
            if summary_lines:
                row_cur += 1
                ws.write(row_cur, 0, 'Summary')
                row_cur += 1
                for lbl, val in summary_lines:
                    ws.write(row_cur, 0, lbl)
                    ws.write(row_cur, 1, val if isinstance(val, str) else val)
                    row_cur += 1
            wb.close()
            blob = buf.getvalue()
            import base64
            content = base64.b64encode(blob).decode('ascii')
            return {'success': True, 'format': 'excel', 'content': content, 'filename': "{}.xlsx".format(base_filename)}
        elif fmt == 'pdf':
            try:
                from reportlab.lib.pagesizes import letter
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
                from reportlab.lib import colors
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.units import inch
            except ImportError:
                return {'success': False, 'message': 'reportlab not installed. Use csv/excel or install reportlab.'}
            import io
            pdf_font = _register_pdf_arabic_font()
            buf = io.BytesIO()
            doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.5 * inch, rightMargin=0.5 * inch, topMargin=0.5 * inch, bottomMargin=0.5 * inch)
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(name='ExportTitle', parent=styles['Heading1'], fontSize=14, spaceAfter=6)
            period_style = ParagraphStyle(name='ExportPeriod', parent=styles['Normal'], fontSize=10, textColor=colors.grey, spaceAfter=12)
            cell_font = pdf_font or 'Helvetica'
            cell_style = ParagraphStyle(name='ExportCell', fontName=cell_font, fontSize=8, leading=10, wordWrap='CJK')
            header_style = ParagraphStyle(name='ExportHeader', fontName=cell_font, fontSize=9, leading=11, alignment=1)
            story = [Paragraph(title or 'Report', title_style), Paragraph(period_label, period_style)]
            header_row = [Paragraph(_pdf_cell_text(c), header_style) for c in columns]
            data_rows = [[Paragraph(_pdf_cell_text(r.get(col)), cell_style) for col in columns] for r in rows]
            table_data = [header_row] + data_rows
            ncols = len(columns)
            avail_pt = letter[0] - 1.0 * inch
            avail_inch = avail_pt / 72.0
            if ncols <= 2:
                w = avail_pt / ncols
                col_widths = [w] * ncols
            elif ncols == 5:
                fixed_inch = 0.85 + 0.75 + 0.7 + 0.7
                desc_inch = max(1.5, avail_inch - fixed_inch)
                col_widths = [0.85 * inch, 0.75 * inch, desc_inch * inch, 0.7 * inch, 0.7 * inch]
            elif ncols == 6:
                fixed_inch = 0.8 + 0.7 + 0.65 * 3
                desc_inch = max(1.2, avail_inch - fixed_inch)
                col_widths = [0.8 * inch, 0.7 * inch, desc_inch * inch, 0.65 * inch, 0.65 * inch, 0.65 * inch]
            else:
                col_width = avail_pt / ncols if ncols else 1.0 * inch
                col_widths = [max(col_width, 0.6 * inch) for _ in range(ncols)]
            t = Table(table_data, colWidths=col_widths, repeatRows=1)
            style_list = [
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#37474F')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]
            if pdf_font:
                style_list.append(('FONTNAME', (0, 0), (-1, -1), pdf_font))
            t.setStyle(TableStyle(style_list))
            story.append(t)
            if summary_lines:
                summary_style = ParagraphStyle(name='ExportSummaryTitle', fontName=cell_font, fontSize=10, spaceBefore=14, spaceAfter=6)
                story.append(Paragraph('Summary / Totals', summary_style))
                sum_table_data = [['Label', 'Value']] + [[lbl, str(val) if isinstance(val, str) else '{:,.2f} EGP'.format(val)] for lbl, val in summary_lines]
                t_sum = Table(sum_table_data, colWidths=[2.5 * inch, 1.5 * inch])
                sum_style = [
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#37474F')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('FONTSIZE', (0, 0), (-1, -1), 9),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ]
                if pdf_font:
                    sum_style.append(('FONTNAME', (0, 0), (-1, -1), pdf_font))
                t_sum.setStyle(TableStyle(sum_style))
                story.append(t_sum)
            doc.build(story)
            buf.seek(0)
            blob = buf.getvalue()
            import base64
            content = base64.b64encode(blob).decode('ascii')
            return {'success': True, 'format': 'pdf', 'content': content, 'filename': "{}.pdf".format(base_filename)}
        else:
            return {'success': False, 'message': f'Unsupported format: {format}. Use pdf, excel, or csv.'}
    except Exception as e:
        logger.exception("export_report error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


# ===========================================================================
# 9. ACCOUNTING REPORTS (Ledger-Driven, Read-Only)
# ===========================================================================

def _ledger_1210_balance_for_invoice(invoice_id):
    """Net balance (debit - credit) on 1210 for this invoice. Ledger-only."""
    return _sum_1210_balance_for_invoice(invoice_id)


def _ledger_1200_debits_by_invoice():
    """Sum of DR 1200 by invoice_id (reference_type purchase_invoice or import_cost, reference_id=invoice_id)."""
    by_inv = {}
    for _i, e in enumerate(app_tables.ledger.search(account_code='1200')):
        if _i >= MAX_LEDGER_SCAN:
            logger.warning("Ledger scan cap reached (%d) in _ledger_1200_debits_by_invoice", MAX_LEDGER_SCAN)
            break
        rt = _safe_str(e.get('reference_type', ''))
        rid = _safe_str(e.get('reference_id', ''))
        if rt in ('purchase_invoice', 'import_cost') and rid:
            by_inv[rid] = by_inv.get(rid, 0) + _round2(e.get('debit', 0))
    return by_inv


def _ledger_1200_credits_by_item():
    """Sum of CR 1200 by item_id (reference_type sales_invoice, reference_id=item_id)."""
    by_item = {}
    for _i, e in enumerate(app_tables.ledger.search(account_code='1200')):
        if _i >= MAX_LEDGER_SCAN:
            logger.warning("Ledger scan cap reached (%d) in _ledger_1200_credits_by_item", MAX_LEDGER_SCAN)
            break
        if _safe_str(e.get('reference_type', '')) != 'sales_invoice':
            continue
        rid = _safe_str(e.get('reference_id', ''))
        if not rid:
            continue
        by_item[rid] = by_item.get(rid, 0) + _round2(e.get('credit', 0))
    return by_item


def _invoice_ids_with_1210_or_1200():
    """Collect invoice_ids that have 1210 or 1200 ledger activity (for reporting)."""
    out = set()
    for _i, e in enumerate(app_tables.ledger.search(account_code='1210')):
        if _i >= MAX_LEDGER_SCAN:
            logger.warning("Ledger scan cap reached (%d) in _invoice_ids_with_1210_or_1200 (1210)", MAX_LEDGER_SCAN)
            break
        rt = _safe_str(e.get('reference_type', ''))
        rid = _safe_str(e.get('reference_id', ''))
        if rt in ('purchase_invoice', 'import_cost') and rid:
            out.add(rid)
    for _i, e in enumerate(app_tables.ledger.search(account_code='1210', reference_type='import_cost_payment')):
        if _i >= MAX_LEDGER_SCAN:
            logger.warning("Ledger scan cap reached (%d) in _invoice_ids_with_1210_or_1200 (1210 payment)", MAX_LEDGER_SCAN)
            break
        cost_id = _safe_str(e.get('reference_id', ''))
        if not cost_id:
            continue
        try:
            ic = app_tables.import_costs.get(id=cost_id)
            if ic:
                pi_id = ic.get('purchase_invoice_id')
                if pi_id:
                    out.add(pi_id)
        except Exception:
            pass
    for _i, e in enumerate(app_tables.ledger.search(account_code='1200')):
        if _i >= MAX_LEDGER_SCAN:
            logger.warning("Ledger scan cap reached (%d) in _invoice_ids_with_1210_or_1200 (1200)", MAX_LEDGER_SCAN)
            break
        rt = _safe_str(e.get('reference_type', ''))
        rid = _safe_str(e.get('reference_id', ''))
        if rt in ('purchase_invoice', 'import_cost') and rid:
            out.add(rid)
    return out


@anvil.server.callable
def get_inventory_valuation(token_or_email=None):
    """
    Inventory valuation report: Transit (1210) vs Available (1200). Strictly ledger-driven.
    transit_total = sum(debit-credit) on 1210; available_total = sum(debit-credit) on 1200.
    by_invoice: list of {invoice_id, status: "transit"|"available", value_egp}.
    """
    is_valid, _, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        transit_total = 0.0
        available_total = 0.0
        by_invoice = []

        # 1210: net balance per invoice
        invoice_ids = _invoice_ids_with_1210_or_1200()
        for inv_id in invoice_ids:
            bal = _ledger_1210_balance_for_invoice(inv_id)
            if abs(bal) >= RESIDUAL_TOLERANCE:
                transit_total += bal
                by_invoice.append({'invoice_id': inv_id, 'status': 'transit', 'value_egp': _round2(bal)})

        # 1200: net balance per invoice (DR by invoice - CR by items linked to invoice)
        debit_by_inv = _ledger_1200_debits_by_invoice()
        credit_by_item = _ledger_1200_credits_by_item()
        item_to_invoice = {}
        for row in app_tables.inventory.search():
            pi_id = row.get('purchase_invoice_id')
            if pi_id:
                item_to_invoice[row.get('id')] = pi_id
        credit_by_inv = {}
        for item_id, cr in credit_by_item.items():
            inv_id = item_to_invoice.get(item_id)
            if inv_id:
                credit_by_inv[inv_id] = credit_by_inv.get(inv_id, 0) + cr
        for inv_id in set(list(debit_by_inv.keys()) + list(credit_by_inv.keys())):
            avail = _round2(debit_by_inv.get(inv_id, 0) - credit_by_inv.get(inv_id, 0))
            if abs(avail) >= RESIDUAL_TOLERANCE:
                available_total += avail
                by_invoice.append({'invoice_id': inv_id, 'status': 'available', 'value_egp': avail})

        grand_total = _round2(transit_total + available_total)
        return {
            'success': True,
            'transit_total': _round2(transit_total),
            'available_total': _round2(available_total),
            'grand_total': grand_total,
            'by_invoice': by_invoice,
        }
    except Exception as e:
        logger.exception("get_inventory_valuation error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_inventory_detailed(token_or_email=None):
    """
    Detailed inventory valuation per invoice. All numbers from ledger aggregation.
    Returns: supplier_amount_egp (stored at post), import_cost_total (ledger 1210+1200 import refs),
    landed_cost, transit_balance, available_balance, inventory_moved, sold_flag.
    """
    is_valid, _, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        transit_by_inv = {}
        for inv_id in _invoice_ids_with_1210_or_1200():
            transit_by_inv[inv_id] = _ledger_1210_balance_for_invoice(inv_id)
        debit_by_inv = _ledger_1200_debits_by_invoice()
        credit_by_item = _ledger_1200_credits_by_item()
        item_to_invoice = {}
        for row in app_tables.inventory.search():
            if row.get('purchase_invoice_id'):
                item_to_invoice[row.get('id')] = row.get('purchase_invoice_id')
        credit_by_inv = {}
        for item_id, cr in credit_by_item.items():
            inv_id = item_to_invoice.get(item_id)
            if inv_id:
                credit_by_inv[inv_id] = credit_by_inv.get(inv_id, 0) + cr
        available_by_inv = {}
        for inv_id in set(list(debit_by_inv.keys()) + list(credit_by_inv.keys())):
            available_by_inv[inv_id] = _round2(debit_by_inv.get(inv_id, 0) - credit_by_inv.get(inv_id, 0))

        # Import cost total per invoice from ledger (1210 + 1200 where ref_type=import_cost or import_cost_payment)
        import_total_by_inv = {}
        for _i, e in enumerate(app_tables.ledger.search(account_code='1210')):
            if _i >= MAX_LEDGER_SCAN:
                logger.warning("Ledger scan cap reached (%d) in get_inventory_valuation (1210 import)", MAX_LEDGER_SCAN)
                break
            rt, rid = _safe_str(e.get('reference_type', '')), _safe_str(e.get('reference_id', ''))
            amt = _round2(e.get('debit', 0)) - _round2(e.get('credit', 0))
            if rt == 'import_cost' and rid:
                import_total_by_inv[rid] = import_total_by_inv.get(rid, 0) + amt
            if rt == 'import_cost_payment' and rid:
                try:
                    ic = app_tables.import_costs.get(id=rid)
                    if ic and ic.get('purchase_invoice_id'):
                        import_total_by_inv[ic.get('purchase_invoice_id')] = import_total_by_inv.get(ic.get('purchase_invoice_id'), 0) + amt
                except Exception:
                    pass
        for _i, e in enumerate(app_tables.ledger.search(account_code='1200')):
            if _i >= MAX_LEDGER_SCAN:
                logger.warning("Ledger scan cap reached (%d) in get_inventory_valuation (1200 import)", MAX_LEDGER_SCAN)
                break
            rt, rid = _safe_str(e.get('reference_type', '')), _safe_str(e.get('reference_id', ''))
            if rt != 'import_cost':
                continue
            amt = _round2(e.get('debit', 0)) - _round2(e.get('credit', 0))
            if rid:
                import_total_by_inv[rid] = import_total_by_inv.get(rid, 0) + amt

        results = []
        for row in app_tables.purchase_invoices.search():
            inv_id = row.get('id')
            supplier_amount_egp = _round2(row.get('supplier_amount_egp') or 0)
            import_total = _round2(import_total_by_inv.get(inv_id, 0))
            landed_cost = _round2(supplier_amount_egp + import_total)
            transit_balance = _round2(transit_by_inv.get(inv_id, 0))
            available_balance = _round2(available_by_inv.get(inv_id, 0))
            try:
                inv_moved = bool(row.get('inventory_moved'))
            except Exception:
                inv_moved = False
            # sold_flag: 1200 fully credited by COGS for this invoice's items
            sold_flag = abs(available_balance) < RESIDUAL_TOLERANCE and abs(transit_balance) < RESIDUAL_TOLERANCE and landed_cost >= RESIDUAL_TOLERANCE and credit_by_inv.get(inv_id, 0) >= RESIDUAL_TOLERANCE
            results.append({
                'invoice_id': inv_id,
                'supplier_amount_egp': supplier_amount_egp,
                'import_cost_total': import_total,
                'landed_cost': landed_cost,
                'transit_balance': transit_balance,
                'available_balance': available_balance,
                'inventory_moved': inv_moved,
                'sold_flag': sold_flag,
            })
        return {'success': True, 'data': results}
    except Exception as e:
        logger.exception("get_inventory_detailed error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_supplier_aging(as_of_date=None, token_or_email=None):
    """
    Supplier aging report. Ledger account 2000 only.
    Remaining per invoice = sum(CR on 2000 where reference_id=invoice_id) - sum(DR on 2000 where reference_id=invoice_id).
    No reference_type filter — full ledger truth.
    Age buckets: 0_30, 31_60, 61_90, 90_plus by invoice date.
    Exclude invoices where abs(remaining) < 0.01.
    """
    is_valid, _, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        as_of = _safe_date(as_of_date) or date.today()
        remaining = _ledger_2000_remaining_by_invoice()
        invoice_supplier = {}
        invoice_date = {}
        for row in app_tables.purchase_invoices.search():
            inv_id = row.get('id')
            invoice_supplier[inv_id] = row.get('supplier_id')
            d = row.get('date')
            invoice_date[inv_id] = d.date() if hasattr(d, 'date') else _safe_date(str(d)[:10]) if d else as_of

        # Buckets per supplier
        buckets = {}
        for inv_id, rem in remaining.items():
            if abs(rem) < RESIDUAL_TOLERANCE:
                continue
            sup_id = invoice_supplier.get(inv_id) or 'unknown'
            if sup_id not in buckets:
                buckets[sup_id] = {'supplier_id': sup_id, '0_30': 0, '31_60': 0, '61_90': 0, '90_plus': 0, 'total': 0}
            inv_d = invoice_date.get(inv_id) or as_of
            days = (as_of - inv_d).days if hasattr(as_of, '__sub__') else 0
            amt = _round2(rem)
            buckets[sup_id]['total'] += amt
            if days <= 30:
                buckets[sup_id]['0_30'] += amt
            elif days <= 60:
                buckets[sup_id]['31_60'] += amt
            elif days <= 90:
                buckets[sup_id]['61_90'] += amt
            else:
                buckets[sup_id]['90_plus'] += amt
        return {'success': True, 'suppliers': list(buckets.values())}
    except Exception as e:
        logger.exception("get_supplier_aging error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_fx_report_per_invoice(token_or_email=None):
    """
    FX report per invoice. Ledger-only (no stored payment fields).
    paid_egp = sum(CR on cash/bank 1000,1010-1013) - sum(DR on same) where reference_id=invoice_id.
    fx_gain = sum(CR 4110 where reference_id=invoice_id).
    fx_loss = sum(DR 6110 where reference_id=invoice_id).
    Reconciliation: sum(net_fx) over invoices = balance(4110) - balance(6110).
    """
    is_valid, _, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        paid_by_inv = {}
        for _i, e in enumerate(app_tables.ledger.search(reference_type='payment')):
            if _i >= MAX_LEDGER_SCAN:
                logger.warning("Ledger scan cap reached (%d) in get_fx_report_per_invoice (payment)", MAX_LEDGER_SCAN)
                break
            rid = _safe_str(e.get('reference_id', ''))
            if not rid:
                continue
            code = _safe_str(e.get('account_code', ''))
            if code in ('1000', '1010', '1011', '1012', '1013'):
                paid_by_inv[rid] = paid_by_inv.get(rid, 0) + _round2(e.get('credit', 0)) - _round2(e.get('debit', 0))

        fx_gain_by_inv = {}
        for _i, e in enumerate(app_tables.ledger.search(account_code='4110')):
            if _i >= MAX_LEDGER_SCAN:
                logger.warning("Ledger scan cap reached (%d) in get_fx_report_per_invoice (4110)", MAX_LEDGER_SCAN)
                break
            rid = _safe_str(e.get('reference_id', ''))
            if rid:
                fx_gain_by_inv[rid] = fx_gain_by_inv.get(rid, 0) + _round2(e.get('credit', 0))
        fx_loss_by_inv = {}
        for _i, e in enumerate(app_tables.ledger.search(account_code='6110')):
            if _i >= MAX_LEDGER_SCAN:
                logger.warning("Ledger scan cap reached (%d) in get_fx_report_per_invoice (6110)", MAX_LEDGER_SCAN)
                break
            rid = _safe_str(e.get('reference_id', ''))
            if rid:
                fx_loss_by_inv[rid] = fx_loss_by_inv.get(rid, 0) + _round2(e.get('debit', 0))

        results = []
        for row in app_tables.purchase_invoices.search():
            inv_id = row.get('id')
            booked_egp = _round2(row.get('supplier_amount_egp') or 0)
            paid_egp = _round2(paid_by_inv.get(inv_id, 0))
            fx_gain = _round2(fx_gain_by_inv.get(inv_id, 0))
            fx_loss = _round2(fx_loss_by_inv.get(inv_id, 0))
            results.append({
                'invoice_id': inv_id,
                'booked_egp': booked_egp,
                'paid_egp': paid_egp,
                'fx_gain': fx_gain,
                'fx_loss': fx_loss,
                'net_fx': _round2(fx_gain - fx_loss),
            })
        return {'success': True, 'data': results}
    except Exception as e:
        logger.exception("get_fx_report_per_invoice error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


def _ledger_2000_remaining_by_invoice():
    """
    Account 2000 balance per reference_id. Keys may be invoice_id (purchase_invoice/payment)
    or supplier_name (opening_balance). Callers that need per-invoice remaining use
    .get(invoice_id, 0) so opening_balance entries (reference_id=supplier_name) are not
    mixed into invoice-level reconciliation.
    """
    by_inv = {}
    for _i, e in enumerate(app_tables.ledger.search(account_code='2000')):
        if _i >= MAX_LEDGER_SCAN:
            logger.warning("Ledger scan cap reached (%d) in _ledger_2000_remaining_by_invoice", MAX_LEDGER_SCAN)
            break
        rid = _safe_str(e.get('reference_id', ''))
        if not rid:
            continue
        by_inv[rid] = by_inv.get(rid, 0) + _round2(e.get('credit', 0)) - _round2(e.get('debit', 0))
    return by_inv


@anvil.server.callable
def get_unrealized_fx(current_rate_provider, token_or_email=None):
    """
    Unrealized FX valuation: for each open invoice, remaining in original currency at current rate vs remaining_egp.
    Mathematically correct: invoice_rate = supplier_amount_egp / original_amount;
    remaining_original = remaining_egp / invoice_rate; revalued_egp = remaining_original * current_rate.
    DO NOT post journal entries; reporting only.
    """
    is_valid, _, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        remaining_egp_by_inv = _ledger_2000_remaining_by_invoice()

        results = []
        for row in app_tables.purchase_invoices.search():
            inv_id = row.get('id')
            remaining_egp = _round2(remaining_egp_by_inv.get(inv_id, 0))
            if abs(remaining_egp) < RESIDUAL_TOLERANCE:
                continue
            original_amount = _round2(row.get('original_amount') or row.get('total') or 0)
            supplier_egp = _round2(row.get('supplier_amount_egp') or 0)
            if original_amount <= 0:
                results.append({'invoice_id': inv_id, 'remaining_egp': remaining_egp, 'revalued_egp': remaining_egp, 'unrealized_fx': 0})
                continue
            if supplier_egp <= 0:
                results.append({'invoice_id': inv_id, 'remaining_egp': remaining_egp, 'revalued_egp': remaining_egp, 'unrealized_fx': 0})
                continue
            invoice_rate = _round2(supplier_egp / original_amount)
            if invoice_rate <= 0:
                results.append({'invoice_id': inv_id, 'remaining_egp': remaining_egp, 'revalued_egp': remaining_egp, 'unrealized_fx': 0})
                continue
            remaining_original = _round2(remaining_egp / invoice_rate)
            if callable(current_rate_provider):
                rate_info = current_rate_provider(row)
            else:
                rate_info = current_rate_provider
            if hasattr(rate_info, 'get'):
                current_rate = _round2(rate_info.get('current_rate_to_egp') or rate_info.get('exchange_rate') or 0)
            else:
                current_rate = _round2(rate_info[0] if rate_info else 0)
            if current_rate <= 0:
                results.append({'invoice_id': inv_id, 'remaining_egp': remaining_egp, 'revalued_egp': remaining_egp, 'unrealized_fx': 0})
                continue
            revalued_egp = _round2(remaining_original * current_rate)
            unrealized_fx = _round2(revalued_egp - remaining_egp)
            results.append({
                'invoice_id': inv_id,
                'remaining_egp': remaining_egp,
                'revalued_egp': revalued_egp,
                'unrealized_fx': unrealized_fx,
            })
        return {'success': True, 'data': results}
    except Exception as e:
        logger.exception("get_unrealized_fx error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


# ===========================================================================
# 9B. FX RECONCILIATION REPORT
# ===========================================================================

@anvil.server.callable
def get_fx_reconciliation(token_or_email=None):
    """
    FX Reconciliation Report: for each non-EGP purchase invoice, show:
    - Original amount, invoice rate, supplier_amount_egp (book value)
    - Total paid (from ledger DR 2000), remaining
    - Realized FX gain/loss from ledger (sum of 4110 credits - 6110 debits per invoice)
    - Expected FX (sum of liability_slices - sum of actual payments in EGP)
    - Variance (realized vs expected) — should be 0; non-zero means reconciliation error.

    This helps verify that partial payments with different exchange rates are correctly
    tracked and that no FX gain/loss was missed or double-counted.
    """
    is_valid, _, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        results = []
        total_realized_gain = 0.0
        total_realized_loss = 0.0
        total_variance = 0.0

        for inv in app_tables.purchase_invoices.search():
            inv_id = inv.get('id')
            currency = _safe_str(inv.get('currency_code') or '').upper()
            if not currency or currency == 'EGP':
                continue  # Only non-EGP invoices have FX

            original_amount = _round2(inv.get('original_amount') or inv.get('total') or 0)
            supplier_egp = _round2(inv.get('supplier_amount_egp') or 0)
            inv_rate_raw = inv.get('exchange_rate_usd_to_egp') or inv.get('exchange_rate')
            try:
                inv_rate = _round2(float(inv_rate_raw)) if inv_rate_raw not in (None, '') else 0
            except (TypeError, ValueError):
                inv_rate = 0

            # Ledger: AP posted (CR 2000, purchase_invoice) and paid (DR 2000, payment)
            posted_egp = 0.0
            paid_egp = 0.0
            for e in app_tables.ledger.search(account_code='2000', reference_id=inv_id, reference_type='purchase_invoice'):
                posted_egp += _round2(e.get('credit', 0))
            for e in app_tables.ledger.search(account_code='2000', reference_id=inv_id, reference_type='payment'):
                paid_egp += _round2(e.get('debit', 0))
            remaining_egp = _round2(posted_egp - paid_egp)

            # Realized FX: credits to 4110 (gain) and debits to 6110 (loss) for this invoice
            realized_gain = 0.0
            realized_loss = 0.0
            for e in app_tables.ledger.search(account_code='4110', reference_id=inv_id, reference_type='payment'):
                realized_gain += _round2(e.get('credit', 0))
            for e in app_tables.ledger.search(account_code='6110', reference_id=inv_id, reference_type='payment'):
                realized_loss += _round2(e.get('debit', 0))

            # Actual bank payments (CR to cash/bank accounts for this invoice)
            actual_bank_paid = 0.0
            for e in app_tables.ledger.search(reference_id=inv_id, reference_type='payment'):
                code = e.get('account_code', '')
                if code.startswith('100') or code.startswith('101'):
                    actual_bank_paid += _round2(e.get('credit', 0))

            # Expected FX = paid_egp (DR 2000, book value cleared) - actual_bank_paid (actual cash)
            expected_fx = _round2(paid_egp - actual_bank_paid)
            net_realized = _round2(realized_gain - realized_loss)
            variance = _round2(net_realized - expected_fx)

            total_realized_gain += realized_gain
            total_realized_loss += realized_loss
            total_variance += abs(variance)

            if posted_egp > 0 or paid_egp > 0:
                results.append({
                    'invoice_id': inv_id,
                    'invoice_number': inv.get('invoice_number', ''),
                    'currency': currency,
                    'original_amount': original_amount,
                    'invoice_rate': inv_rate,
                    'supplier_amount_egp': supplier_egp,
                    'posted_egp': posted_egp,
                    'paid_egp': paid_egp,
                    'remaining_egp': remaining_egp,
                    'actual_bank_paid': actual_bank_paid,
                    'realized_gain': realized_gain,
                    'realized_loss': realized_loss,
                    'net_realized_fx': net_realized,
                    'expected_fx': expected_fx,
                    'variance': variance,
                    'status': 'OK' if abs(variance) < 0.02 else 'MISMATCH',
                })

        return {
            'success': True,
            'data': results,
            'count': len(results),
            'summary': {
                'total_realized_gain': _round2(total_realized_gain),
                'total_realized_loss': _round2(total_realized_loss),
                'net_realized': _round2(total_realized_gain - total_realized_loss),
                'total_variance': _round2(total_variance),
                'all_reconciled': total_variance < 0.02,
            },
        }
    except Exception as e:
        logger.exception("get_fx_reconciliation error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        # Enforce period lock
        expense_date = row.get('date') or row.get('expense_date') or row.get('created_at')
        if expense_date and is_period_locked(expense_date):
            return {'success': False, 'message': 'Cannot delete expense: accounting period is locked.'}
        row.update(status='cancelled', updated_at=get_utc_now())
        logger.info("Expense %s cancelled by %s", expense_id, user_email)
        return {'success': True}
    except Exception as e:
        logger.exception("delete_expense error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        for _i, entry in enumerate(app_tables.ledger.search(account_code='1210')):
            if _i >= MAX_LEDGER_SCAN:
                logger.warning("Ledger scan cap reached (%d) in get_transit_balance", MAX_LEDGER_SCAN)
                break
            debits += _round2(entry.get('debit', 0))
            credits += _round2(entry.get('credit', 0))
        balance = _round2(debits - credits)
        return {'success': True, 'transit_balance_egp': balance}
    except Exception as e:
        logger.exception("get_transit_balance error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_contracts_list_simple(token_or_email=None):
    """Return simple list of contracts for dropdown/selection."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        contracts = []
        _MAX_ROWS = 10000  # Safety cap — bounded quotations scan
        for i, r in enumerate(app_tables.quotations.search(is_deleted=False)):
            if i >= _MAX_ROWS:
                logger.warning("get_contracts_list_simple: quotations scan capped at %d rows", _MAX_ROWS)
                break
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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def record_invoice_payment(invoice_id, amount, method='cash', notes='', payment_date=None,
                           currency_code='EGP', exchange_rate=None, token_or_email=None):
    """Record payment for a purchase invoice (alias for record_supplier_payment)."""
    payment_date = _safe_date(payment_date) or date.today()
    return record_supplier_payment(
        invoice_id, amount, method, payment_date,
        currency_code=currency_code, exchange_rate=exchange_rate, notes=notes, token_or_email=token_or_email
    )


# get_suppliers_list_simple → moved to accounting_suppliers.py


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

        # Get import costs (include amount_egp so view shows same values as PDF; server stores EGP in amount when amount_egp col missing)
        import_costs = []
        try:
            extra_ic_cols = ['amount_egp', 'original_amount', 'original_currency', 'exchange_rate']
            for ic in app_tables.import_costs.search(purchase_invoice_id=invoice_id):
                dd = _row_to_dict(ic, IMPORT_COST_COLS)
                for c in extra_ic_cols:
                    if c not in dd and ic.get(c) is not None:
                        dd[c] = ic.get(c)
                import_costs.append(dd)
        except Exception as _e:
            logger.debug("Suppressed: %s", _e)
        d['import_costs'] = import_costs

        # Get supplier name
        try:
            supplier = app_tables.suppliers.get(id=d.get('supplier_id'))
            d['supplier_name'] = _safe_str(supplier.get('name', '')) if supplier else ''
        except Exception:
            d['supplier_name'] = ''

        # Alias paid_amount -> paid for frontend consistency (cached on invoice row)
        d['paid'] = d.get('paid_amount', 0)

        # Ledger-based totals (EGP): so display matches actual 2000 liability/payments and fixes wrong cached paid_amount
        try:
            posted_egp = 0.0
            for entry in app_tables.ledger.search(account_code='2000', reference_id=invoice_id, reference_type='purchase_invoice'):
                posted_egp += _round2(entry.get('credit', 0))
            paid_ledger_egp = 0.0
            for entry in app_tables.ledger.search(account_code='2000', reference_id=invoice_id, reference_type='payment'):
                paid_ledger_egp += _round2(entry.get('debit', 0))
            d['total_egp_ledger'] = _round2(posted_egp)
            d['paid_ledger'] = _round2(paid_ledger_egp)
        except Exception as _e:
            logger.debug("Ledger totals for invoice details: %s", _e)
            d['total_egp_ledger'] = None
            d['paid_ledger'] = None

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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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

        # Find all active contracts without a purchase invoice
        contracts = []
        for c in _contracts_search_active():
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
                    'reason': type(e).__name__,
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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
                'currency_code': r.get('currency_code', ''),
                'rate_to_egp': _round2(r.get('rate_to_egp', 0)),
                'updated_at': r.get('effective_date').isoformat() if r.get('effective_date') else '',
            })
        rates.sort(key=lambda x: x.get('currency_code', ''))
        return {'success': True, 'data': rates}
    except Exception as e:
        logger.exception("get_exchange_rates error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        now = get_utc_now()
        # Deactivate any existing active rows for this currency
        for existing in app_tables.currency_exchange_rates.search(currency_code=currency_code, is_active=True):
            existing.update(is_active=False)
        # Add new active row
        app_tables.currency_exchange_rates.add_row(
            currency_code=currency_code,
            rate_to_egp=rate_to_egp,
            effective_date=now,
            created_by=_safe_str(user_email),
            is_active=True,
        )
        logger.info("Exchange rate %s = %s EGP set by %s", currency_code, rate_to_egp, user_email)
        return {'success': True}
    except Exception as e:
        logger.exception("set_exchange_rate error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        is_admin = AuthManager.is_admin(token_or_email)
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
@anvil.server.callable
def get_accounting_dashboard_stats(token_or_email=None):
    """Return inventory, purchase invoice, and P&L stats for the dashboard."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        cache_key = f"acct_dash:{user_email}"
        cached = _acct_dash_cache.get(cache_key)
        if cached is not None:
            return cached

        now = date.today()
        year = now.year

        # NOTE: Protected by _acct_dash_cache (60s TTL) — cold call scans multiple tables.
        # Inventory stats (capped at 50k rows as safety)
        _MAX_SCAN = 50000
        inv_count = 0; inv_value = 0.0; inv_in_stock = 0; inv_in_transit = 0; inv_sold = 0
        for i, item in enumerate(app_tables.inventory.search()):
            if i >= _MAX_SCAN:
                logger.warning("dashboard: inventory scan capped at %d rows", _MAX_SCAN)
                break
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
        for i, pi in enumerate(app_tables.purchase_invoices.search()):
            if i >= _MAX_SCAN:
                logger.warning("dashboard: purchase_invoices scan capped at %d rows", _MAX_SCAN)
                break
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
        # Pre-fetch all suppliers once to avoid N+1 queries (small table, safe)
        _suppliers_map = {}
        try:
            for i, s in enumerate(app_tables.suppliers.search()):
                if i >= 5000:
                    break  # Safety cap for suppliers table
                _suppliers_map[s.get('id', '')] = s.get('name', '')
        except Exception as _sup_err:
            logger.debug("Could not pre-fetch suppliers: %s", _sup_err)
        top_suppliers = []
        for sid, total in top_suppliers_raw:
            name = _suppliers_map.get(sid, sid)
            top_suppliers.append({'name': name, 'total': _round2(total)})

        # Monthly totals + profitability in one ledger pass (current year)
        monthly_purchases = [0.0] * 12
        monthly_sales = [0.0] * 12
        total_cogs = 0.0; total_revenue = 0.0
        for i, entry in enumerate(app_tables.ledger.search()):
            if i >= _MAX_SCAN:
                logger.warning("dashboard: ledger scan capped at %d rows", _MAX_SCAN)
                break
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

        _acct_dash_cache.set(cache_key, result)
        return result
    except Exception as e:
        logger.exception("get_accounting_dashboard_stats error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        _MAX_EXPORT = 20000  # Safety cap for exports
        for i, r in enumerate(app_tables.inventory.search()):
            if i >= _MAX_EXPORT:
                break
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
        # Pre-fetch all suppliers once to avoid N+1 queries
        _sup_map = {}
        try:
            for _s in app_tables.suppliers.search():
                _sup_map[_s.get('id', '')] = _s.get('name', '')
        except Exception:
            pass

        data = []
        _MAX_EXPORT = 20000  # Safety cap for exports
        for i, r in enumerate(app_tables.purchase_invoices.search()):
            if i >= _MAX_EXPORT:
                break
            supplier_name = _sup_map.get(r.get('supplier_id', ''), '')
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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


def _create_notification_for_admins(notification_type, message, data=None):
    """Create a notification for all admin users using the correct notifications module."""
    try:
        from . import notifications as notif_mod
        payload = {
            'message_en': message,
            'message_ar': message,
        }
        if data and isinstance(data, dict):
            payload.update(data)
        notif_mod.create_notification_for_all_admins(notification_type, payload)
    except Exception as e:
        logger.warning("_create_notification_for_admins error: %s", e)


# ---------------------------------------------------------------------------
# Feature 2: PDF Reports — Purchase Invoice, P&L, Supplier Statement
# ---------------------------------------------------------------------------
@anvil.server.callable
def get_purchase_invoice_pdf_data(invoice_id, token_or_email=None):
    """Get PDF-ready data for a purchase invoice (official document with currency, rate, payments, summary)."""
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
        payment_history = []
        try:
            for entry in app_tables.ledger.search(reference_id=invoice_id, reference_type='payment'):
                if entry.get('account_code') == '2000' and _round2(entry.get('debit', 0) or 0) > 0:
                    payment_history.append({
                        'date': entry.get('date'),
                        'amount_egp': _round2(entry.get('debit', 0) or 0),
                        'currency_code': 'EGP',
                        'exchange_rate': 1,
                        'description': _safe_str(entry.get('description', '')),
                    })
        except Exception:
            pass
        payment_history.sort(key=lambda x: (x.get('date') or '',))
        data = pdf_reports.build_purchase_invoice_pdf_data(
            dict(inv), dict(supplier) if supplier else {}, import_costs,
            line_items=None, payment_history=payment_history
        )
        return {'success': True, 'data': data}
    except Exception as e:
        logger.exception("get_purchase_invoice_pdf_data error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_pnl_report_pdf_data(date_from=None, date_to=None, token_or_email=None):
    """Get P&L report PDF data."""
    is_valid, user_email, error = _require_authenticated(token_or_email)
    if not is_valid:
        return {'success': False, 'message': error}
    try:
        _MAX_ROWS = 20000  # Safety cap for P&L report scans
        items = []
        for i, r in enumerate(app_tables.inventory.search()):
            if i >= _MAX_ROWS:
                logger.warning("get_pnl_report_pdf_data: inventory scan capped at %d rows", _MAX_ROWS)
                break
            items.append(dict(r))
        invoices = []
        for i, r in enumerate(app_tables.purchase_invoices.search()):
            if i >= _MAX_ROWS:
                logger.warning("get_pnl_report_pdf_data: purchase_invoices scan capped at %d rows", _MAX_ROWS)
                break
            invoices.append(dict(r))
        data = pdf_reports.build_pnl_report_data(items, invoices, date_from, date_to)
        return {'success': True, 'data': data}
    except Exception as e:
        logger.exception("get_pnl_report_pdf_data error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        for _i, entry in enumerate(app_tables.ledger.search(account_code='1100', reference_type='sales_invoice')):
            if _i >= MAX_LEDGER_SCAN:
                logger.warning("Ledger scan cap reached (%d) in get_contract_total (sales)", MAX_LEDGER_SCAN)
                break
            if entry.get('reference_id') in item_ids:
                total_sales += float(entry.get('debit', 0) or 0)

    # 3. Sum credits for account 1100 where ref_type='customer_collection' and ref_id=contract_number
    total_collections = 0.0
    for _i, entry in enumerate(app_tables.ledger.search(account_code='1100', reference_type='customer_collection')):
        if _i >= MAX_LEDGER_SCAN:
            logger.warning("Ledger scan cap reached (%d) in get_contract_total (collections)", MAX_LEDGER_SCAN)
            break
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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def post_contract_receivable(contract_number, amount_egp, description=None, token_or_email=None):
    """
    فتح ذمم العقد — تسجيل إيراد العقد (المستحق على العميل) في الدفتر.
    لما العقد يكون عليه دفعات ومفيش تسليم/صنف مخزون، الرصيد بيبقى 0 لأن مفيش قيد مبيعات.
    استدعاء هذه الدالة يسجل: مدين 1100 (ذمم مدينة)، دائن 4000 (إيراد مبيعات) فيصبح الرصيد يظهر حتى يسجل المستخدم التحصيلات.
    SAFETY: Prevents double revenue if sell_inventory was already called for this contract.
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

        # --- REVENUE DOUBLE-COUNTING GUARD ---
        # H-04 FIX: Check ledger directly (not just inventory table status) to prevent
        # bypass via soft-deleted inventory items. Search ALL inventory items for this contract
        # (including soft-deleted) and check ledger for sales_invoice entries.
        try:
            all_inv_items = list(app_tables.inventory.search(contract_number=contract_number))
        except Exception:
            all_inv_items = []
        for inv_item in all_inv_items:
            item_id = inv_item.get('id')
            if item_id:
                existing_sales = list(app_tables.ledger.search(
                    account_code='1100', reference_type='sales_invoice', reference_id=item_id
                ))
                if existing_sales:
                    return {
                        'success': False,
                        'message': (
                            f'تنبيه: تم تسجيل إيراد هذا العقد بالفعل عن طريق بيع المخزون. '
                            f'لا يمكن فتح الذمم مرة أخرى لتجنب ازدواجية الإيراد. | '
                            f'Revenue already recorded via inventory sale for contract {contract_number}.'
                        ),
                    }
        existing_receivable = list(app_tables.ledger.search(
            account_code='1100', reference_type='contract_receivable', reference_id=contract_number
        ))
        if existing_receivable:
            return {
                'success': False,
                'message': (
                    f'تم فتح ذمم هذا العقد مسبقاً. لا يمكن التكرار. | '
                    f'Contract receivable already posted for {contract_number}.'
                ),
            }
        # --- END GUARD ---

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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'Failed to calculate contract total.', 'total_price': None}


# ===========================================================================
# 13. CUSTOMER / SUPPLIER / TREASURY SUMMARIES
# ===========================================================================

@anvil.server.callable
def get_customer_summary(token_or_email=None):
    """
    Get summary of all customers (grouped by client_name from contracts).
    Ledger-only: opening = sum(DR-CR) on 1100 where reference_type='opening_balance', by reference_id (client_name).
    current_balance = opening + total_sales - total_collections.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error

    try:
        # 1. Build map: client_name -> [contract_numbers] (active only)
        client_contracts = {}
        for c in _contracts_search_active():
            cname = c.get('client_name', '').strip()
            cnum = c.get('contract_number', '')
            if not cname or not cnum:
                continue
            if cname not in client_contracts:
                client_contracts[cname] = []
            client_contracts[cname].append(cnum)

        # 2. Build map: contract_number -> [inventory item_ids]
        _MAX_ROWS = 10000  # Safety cap — bounded inventory scan
        contract_items = {}
        for i, item in enumerate(app_tables.inventory.search()):
            if i >= _MAX_ROWS:
                logger.warning("get_customer_summary: inventory scan capped at %d rows", _MAX_ROWS)
                break
            cn = item.get('contract_number', '')
            if cn:
                if cn not in contract_items:
                    contract_items[cn] = []
                contract_items[cn].append(item.get('id'))

        # 3. Load all AR ledger entries (account 1100) at once
        _MAX_LEDGER = 50000  # Safety cap — bounded ledger scan
        ar_sales = {}
        ar_contract_receivable = {}
        ar_collections = {}
        opening_map = {}

        for i, entry in enumerate(app_tables.ledger.search(account_code='1100')):
            if i >= _MAX_LEDGER:
                logger.warning("get_customer_summary: ledger(1100) scan capped at %d rows", _MAX_LEDGER)
                break
            ref_type = entry.get('reference_type', '')
            ref_id = entry.get('reference_id', '')
            d = float(entry.get('debit', 0) or 0)
            c = float(entry.get('credit', 0) or 0)
            if ref_type == 'opening_balance':
                key = (ref_id or '').strip()
                opening_map[key] = opening_map.get(key, 0) + (d - c)
            elif ref_type == 'sales_invoice':
                ar_sales[ref_id] = ar_sales.get(ref_id, 0) + d
            elif ref_type == 'contract_receivable':
                ar_contract_receivable[ref_id] = ar_contract_receivable.get(ref_id, 0) + d
            elif ref_type == 'customer_collection':
                ar_collections[ref_id] = ar_collections.get(ref_id, 0) + c

        # 4. Build summary per customer (opening from ledger only)
        result = []
        grand_sales = 0
        grand_collections = 0
        grand_opening = 0

        for client_name, contracts_list in sorted(client_contracts.items()):
            opening = _round2(opening_map.get(client_name, 0))

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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_supplier_summary(token_or_email=None):
    """
    Get summary of all suppliers. Ledger-only: opening = sum(CR-DR) on 2000 where reference_type='opening_balance', by reference_id (supplier name).
    current_balance = opening + total_purchases - total_payments.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error

    try:
        # 1. Build map: supplier_id -> supplier_name
        suppliers = {}
        for i, s in enumerate(app_tables.suppliers.search()):
            if i >= 5000:
                break  # Safety cap for suppliers table
            sid = s.get('id', '')
            sname = s.get('name', '')
            if sid and sname:
                suppliers[sid] = sname

        # 2. Build map: supplier_id -> [invoice_ids]
        _MAX_ROWS = 20000  # Safety cap — bounded purchase_invoices scan
        supplier_invoices = {}
        for i, inv in enumerate(app_tables.purchase_invoices.search()):
            if i >= _MAX_ROWS:
                logger.warning("get_supplier_summary: purchase_invoices scan capped at %d rows", _MAX_ROWS)
                break
            sid = inv.get('supplier_id', '')
            iid = inv.get('id', '')
            if sid and iid:
                if sid not in supplier_invoices:
                    supplier_invoices[sid] = []
                supplier_invoices[sid].append(iid)

        # 3. Load all AP ledger entries (account 2000) at once; opening from ledger (ref_type=opening_balance)
        _MAX_LEDGER = 50000  # Safety cap — bounded ledger scan
        ap_purchases = {}
        ap_payments = {}
        opening_map = {}

        for i, entry in enumerate(app_tables.ledger.search(account_code='2000')):
            if i >= _MAX_LEDGER:
                logger.warning("get_supplier_summary: ledger(2000) scan capped at %d rows", _MAX_LEDGER)
                break
            ref_type = entry.get('reference_type', '')
            ref_id = entry.get('reference_id', '')
            d = float(entry.get('debit', 0) or 0)
            c = float(entry.get('credit', 0) or 0)
            if ref_type == 'opening_balance':
                key = (ref_id or '').strip()
                opening_map[key] = opening_map.get(key, 0) + (c - d)
            elif ref_type == 'purchase_invoice':
                ap_purchases[ref_id] = ap_purchases.get(ref_id, 0) + c
            elif ref_type == 'payment':
                ap_payments[ref_id] = ap_payments.get(ref_id, 0) + d

        # 4. Build summary per supplier (opening from ledger only)
        result = []
        grand_purchases = 0
        grand_payments = 0
        grand_opening = 0

        for sid, sname in sorted(suppliers.items(), key=lambda x: x[1]):
            opening = _round2(opening_map.get(sname, 0))
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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_service_supplier_import_costs(service_supplier_id, token_or_email=None):
    """Return import costs linked to a specific service supplier."""
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    if not service_supplier_id:
        return {'success': False, 'message': 'service_supplier_id is required'}
    try:
        rows = list(app_tables.import_costs.search(service_supplier_id=service_supplier_id))
        costs = []
        for r in rows:
            amt_egp = _round2(r.get('amount_egp') or r.get('amount', 0))
            paid = _round2(r.get('paid_amount') or 0)
            remaining = _round2(amt_egp - paid)
            # Get invoice number
            pi_id = r.get('purchase_invoice_id')
            inv_num = ''
            if pi_id:
                try:
                    pi = app_tables.purchase_invoices.get(id=pi_id)
                    if pi:
                        inv_num = pi.get('invoice_number', '')
                except Exception:
                    pass
            costs.append({
                'id': r.get('id'),
                'cost_type': r.get('cost_type', ''),
                'description': _safe_str(r.get('description', '')),
                'amount_egp': amt_egp,
                'paid_amount': paid,
                'remaining_egp': remaining,
                'invoice_number': inv_num,
                'date': str(r.get('date') or ''),
            })
        return {'success': True, 'data': costs}
    except Exception as e:
        logger.exception("get_service_supplier_import_costs error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_service_supplier_summary(token_or_email=None):
    """
    Get AP summary for all service suppliers.
    Uses account 2010 (Service Suppliers AP) in ledger.
    For each service supplier: total_costs (credits) - total_payments (debits) = current_balance.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    try:
        # 1. Build map: service_supplier_id -> info
        suppliers = {}
        for i, s in enumerate(app_tables.service_suppliers.search()):
            if i >= 5000:
                break
            sid = s.get('id', '')
            if sid:
                suppliers[sid] = {
                    'name': s.get('name', ''),
                    'service_type': s.get('service_type', ''),
                    'is_active': s.get('is_active', True),
                    'phone': s.get('phone', ''),
                    'company': s.get('company', ''),
                }

        # 2. Build map: service_supplier_id -> import_cost_ids
        supplier_costs = {}
        for i, ic in enumerate(app_tables.import_costs.search()):
            if i >= 20000:
                break
            ssid = None
            try:
                ssid = ic.get('service_supplier_id')
            except Exception:
                continue
            if ssid:
                if ssid not in supplier_costs:
                    supplier_costs[ssid] = []
                supplier_costs[ssid].append(ic.get('id'))

        # 3. Load all ledger entries for account 2010
        ap_costs = {}    # cost_id -> total credits (payable created)
        ap_payments = {} # cost_id -> total debits (payments)
        for i, entry in enumerate(app_tables.ledger.search(account_code='2010')):
            if i >= 50000:
                break
            ref_type = entry.get('reference_type', '')
            ref_id = entry.get('reference_id', '')
            d = float(entry.get('debit', 0) or 0)
            c = float(entry.get('credit', 0) or 0)
            if ref_type == 'import_cost':
                ap_costs[ref_id] = ap_costs.get(ref_id, 0) + c
            elif ref_type == 'import_cost_payment':
                ap_payments[ref_id] = ap_payments.get(ref_id, 0) + d

        # 4. Build summary per service supplier
        result = []
        grand_costs = 0
        grand_payments = 0

        for sid, info in sorted(suppliers.items(), key=lambda x: x[1]['name']):
            cost_ids = supplier_costs.get(sid, [])
            total_costs = 0
            total_payments = 0
            for cid in cost_ids:
                total_costs += ap_costs.get(cid, 0)
                total_payments += ap_payments.get(cid, 0)

            current_balance = _round2(total_costs - total_payments)
            result.append({
                'supplier_id': sid,
                'supplier_name': info['name'],
                'service_type': info['service_type'],
                'company': info['company'],
                'phone': info['phone'],
                'is_active': info['is_active'],
                'cost_count': len(cost_ids),
                'total_costs': _round2(total_costs),
                'total_payments': _round2(total_payments),
                'current_balance': current_balance,
            })
            grand_costs += total_costs
            grand_payments += total_payments

        return {
            'success': True,
            'data': result,
            'totals': {
                'costs': _round2(grand_costs),
                'payments': _round2(grand_payments),
                'balance': _round2(grand_costs - grand_payments),
            },
            'count': len(result),
        }
    except Exception as e:
        logger.exception("get_service_supplier_summary error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


# ---------------------------------------------------------------------------
# Advanced Account Statement (ledger-only, read-only)
# ---------------------------------------------------------------------------
def _get_customer_entity_ref_ids(client_name):
    """Return set of reference_ids that belong to this customer (client_name) for ledger 1100."""
    ref_ids = {_safe_str(client_name)}
    client_contracts = []
    for c in _contracts_search_active():
        if _safe_str(c.get('client_name')) == _safe_str(client_name):
            cnum = c.get('contract_number', '')
            if cnum:
                client_contracts.append(cnum)
                ref_ids.add(cnum)
    for item in app_tables.inventory.search():
        if item.get('contract_number', '') in client_contracts:
            iid = item.get('id', '')
            if iid:
                ref_ids.add(iid)
    return ref_ids


def _get_supplier_entity_ref_ids(entity_id):
    """
    entity_id can be supplier_id or supplier name.
    Return (supplier_name, set of reference_ids for this supplier for ledger 2000).
    """
    suppliers = {s.get('id', ''): s.get('name', '') for s in app_tables.suppliers.search()}
    name_to_id = {n: sid for sid, n in suppliers.items() if n}
    invoice_ids = []
    sname = None
    if entity_id in suppliers:
        sname = suppliers[entity_id]
        invoice_ids = [inv.get('id', '') for inv in app_tables.purchase_invoices.search(supplier_id=entity_id) if inv.get('id')]
    elif entity_id in name_to_id:
        sid = name_to_id[entity_id]
        sname = entity_id
        invoice_ids = [inv.get('id', '') for inv in app_tables.purchase_invoices.search(supplier_id=sid) if inv.get('id')]
    else:
        sname = _safe_str(entity_id)
        for inv in app_tables.purchase_invoices.search():
            sid = inv.get('supplier_id', '')
            if suppliers.get(sid) == sname:
                invoice_ids.append(inv.get('id', ''))
    ref_ids = {sname} if sname else set()
    ref_ids.update(invoice_ids)
    return sname, ref_ids


@anvil.server.callable
def get_advanced_account_statement(
    entity_type,
    entity_id=None,
    date_from=None,
    date_to=None,
    invoice_id=None,
    transaction_type=None,
    include_aging=False,
    token_or_email=None,
):
    """
    Advanced Account Statement: ledger-only, read-only.
    entity_type: 'customer' | 'supplier'
    entity_id: specific client/supplier or None for consolidated.
    date_from / date_to: optional period (None = from beginning / to today).
    invoice_id: optional filter by reference_id.
    transaction_type: optional filter by reference_type.
    include_aging: if True, return aging buckets (current, 30, 60, 90+, total_outstanding).
    Returns: success, entity_name, opening_balance, closing_balance, rows, aging?, summary?
    """
    is_valid, _, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error
    entity_type = _safe_str(entity_type or '').strip().lower()
    if entity_type not in ('customer', 'supplier'):
        return {'success': False, 'message': "entity_type must be 'customer' or 'supplier'"}

    account_code = '1100' if entity_type == 'customer' else '2000'
    is_customer = entity_type == 'customer'
    d_from = _safe_date(date_from)
    d_to = _safe_date(date_to)

    try:
        # ---- Entity filter: which reference_ids belong to this entity ----
        entity_name = None
        allowed_ref_ids = None  # None = all (consolidated); set = filter by ref_id
        if entity_id:
            eid = _safe_str(entity_id)
            if is_customer:
                entity_name = eid
                allowed_ref_ids = _get_customer_entity_ref_ids(eid)
            else:
                entity_name, allowed_ref_ids = _get_supplier_entity_ref_ids(eid)
                if not entity_name:
                    entity_name = eid

        # ---- Load all ledger rows for this account (we filter in Python for date/entity) ----
        _MAX_ROWS = 50000  # Safety cap — bounded ledger scan
        all_entries = []
        for i, entry in enumerate(app_tables.ledger.search(account_code=account_code)):
            if i >= _MAX_ROWS:
                logger.warning("get_advanced_account_statement: ledger scan capped at %d rows for account %s", _MAX_ROWS, account_code)
                break
            ref_id = _safe_str(entry.get('reference_id', ''))
            ref_type = _safe_str(entry.get('reference_type', ''))
            if allowed_ref_ids is not None and ref_id not in allowed_ref_ids:
                continue
            if invoice_id is not None and _safe_str(invoice_id) and ref_id != _safe_str(invoice_id):
                continue
            if transaction_type is not None and _safe_str(transaction_type) and ref_type != _safe_str(transaction_type):
                continue
            dt = entry.get('date')
            d = float(entry.get('debit', 0) or 0)
            c = float(entry.get('credit', 0) or 0)
            all_entries.append({
                'id': entry.get('id'),
                'date': dt,
                'reference_type': ref_type,
                'reference_id': ref_id,
                'description': _safe_str(entry.get('description', '')),
                'debit': d,
                'credit': c,
                'created_at': entry.get('created_at'),
            })

        # Sort by date ASC, id ASC
        all_entries.sort(key=lambda x: (x['date'] or '', str(x.get('id') or '')))

        # ---- Opening balance (Mode A: no date_from => 0; Mode B: sum from beginning to date_from - 1) ----
        opening_balance = 0.0
        if d_from is not None:
            for e in all_entries:
                ed = e['date']
                ed_date = ed.date() if hasattr(ed, 'date') else ed
                if ed_date is None:
                    continue
                if ed_date >= d_from:
                    break
                if is_customer:
                    opening_balance += e['debit'] - e['credit']
                else:
                    opening_balance += e['credit'] - e['debit']
        opening_balance = _round2(opening_balance)

        # ---- Period rows: from date_from to date_to (or all if not specified) ----
        period_entries = []
        for e in all_entries:
            ed = e['date']
            ed_date = ed.date() if hasattr(ed, 'date') else ed
            if d_from is not None and ed_date is not None and ed_date < d_from:
                continue
            if d_to is not None and ed_date is not None and ed_date > d_to:
                continue
            period_entries.append(e)

        # ---- Running balance and row output (opening balance row first) ----
        running = opening_balance
        rows = []
        # Opening balance row before transactions (PART 10). Customer: positive = debit; Supplier: positive = credit.
        if is_customer:
            ob_dr = _round2(opening_balance) if opening_balance > 0 else 0
            ob_cr = _round2(-opening_balance) if opening_balance < 0 else 0
        else:
            ob_dr = _round2(-opening_balance) if opening_balance < 0 else 0
            ob_cr = _round2(opening_balance) if opening_balance > 0 else 0
        rows.append({
            'date': '',
            'reference_type': 'opening_balance',
            'reference_id': '',
            'description': 'Opening Balance',
            'debit': ob_dr,
            'credit': ob_cr,
            'balance_after_transaction': opening_balance,
        })
        for e in period_entries:
            if is_customer:
                running += (e['debit'] - e['credit'])
            else:
                running += (e['credit'] - e['debit'])
            running = _round2(running)
            row_date = e['date'] or e.get('created_at')
            rows.append({
                'date': row_date.isoformat() if hasattr(row_date, 'isoformat') else str(row_date or ''),
                'reference_type': e['reference_type'],
                'reference_id': e['reference_id'],
                'description': e['description'],
                'debit': _round2(e['debit']),
                'credit': _round2(e['credit']),
                'balance_after_transaction': running,
            })
        closing_balance = _round2(running) if period_entries else opening_balance

        # ---- Aging (optional): outstanding by invoice date vs today ----
        aging = None
        if include_aging and not (invoice_id or transaction_type):
            # By reference_id (document): outstanding = for customer sum(debit)-sum(credit), for supplier sum(credit)-sum(debit)
            today = date.today()
            by_ref = {}
            for e in all_entries:
                rid = e['reference_id']
                if rid not in by_ref:
                    by_ref[rid] = {'debit': 0, 'credit': 0, 'date': e['date']}
                by_ref[rid]['debit'] += e['debit']
                by_ref[rid]['credit'] += e['credit']
                ed = e['date']
                if ed and (rid not in by_ref or by_ref[rid].get('date') is None or (ed.date() if hasattr(ed, 'date') else ed) < (by_ref[rid]['date'].date() if hasattr(by_ref[rid]['date'], 'date') else by_ref[rid]['date'])):
                    by_ref[rid]['date'] = ed
            current = _round2(0)
            b30 = _round2(0)
            b60 = _round2(0)
            b90 = _round2(0)
            for rid, v in by_ref.items():
                if is_customer:
                    out = _round2(v['debit'] - v['credit'])
                else:
                    out = _round2(v['credit'] - v['debit'])
                if out <= 0:
                    continue
                ed = v['date']
                ed_date = ed.date() if hasattr(ed, 'date') else ed if isinstance(ed, date) else None
                if not ed_date:
                    current = _round2(current + out)
                    continue
                days = (today - ed_date).days
                if days <= 30:
                    current = _round2(current + out)
                elif days <= 60:
                    b30 = _round2(b30 + out)
                elif days <= 90:
                    b60 = _round2(b60 + out)
                else:
                    b90 = _round2(b90 + out)
            total_outstanding = _round2(current + b30 + b60 + b90)
            aging = {
                'current': current,
                '30': b30,
                '60': b60,
                '90+': b90,
                'total_outstanding': total_outstanding,
            }

        # ---- Consolidated: summary per entity ----
        summary = None
        if entity_id is None:
            if is_customer:
                client_contracts = {}
                for c in _contracts_search_active():
                    cname = c.get('client_name', '').strip()
                    cnum = c.get('contract_number', '')
                    if cname and cnum:
                        client_contracts.setdefault(cname, []).append(cnum)
                contract_items = {}
                for item in app_tables.inventory.search():
                    cn = item.get('contract_number', '')
                    if cn:
                        contract_items.setdefault(cn, []).append(item.get('id'))
                entities = [(name, _get_customer_entity_ref_ids(name)) for name in sorted(client_contracts.keys())]
            else:
                suppliers = {}
                for s in app_tables.suppliers.search():
                    sid = s.get('id', '')
                    sname = s.get('name', '')
                    if sid and sname:
                        suppliers[sid] = sname
                supplier_invoices = {}
                for inv in app_tables.purchase_invoices.search():
                    sid = inv.get('supplier_id', '')
                    iid = inv.get('id', '')
                    if sid and iid:
                        supplier_invoices.setdefault(sid, []).append(iid)
                entities = [(suppliers[sid], {suppliers[sid]} | set(supplier_invoices.get(sid, []))) for sid in sorted(suppliers.keys(), key=lambda k: suppliers[k])]

            summary = []
            for ent_name, ref_ids in entities:
                op = 0.0
                period_dr = 0.0
                period_cr = 0.0
                for e in all_entries:
                    if e['reference_id'] not in ref_ids:
                        continue
                    ed = e['date']
                    ed_date = ed.date() if hasattr(ed, 'date') else ed
                    if d_from and ed_date is not None and ed_date < d_from:
                        if is_customer:
                            op += e['debit'] - e['credit']
                        else:
                            op += e['credit'] - e['debit']
                    elif (d_from is None or (ed_date is not None and ed_date >= d_from)) and (d_to is None or (ed_date is not None and ed_date <= d_to)):
                        period_dr += e['debit']
                        period_cr += e['credit']
                op = _round2(op)
                period_dr = _round2(period_dr)
                period_cr = _round2(period_cr)
                if is_customer:
                    closing = _round2(op + period_dr - period_cr)
                else:
                    closing = _round2(op + period_cr - period_dr)
                summary.append({
                    'entity_id': ent_name,
                    'entity_name': ent_name,
                    'opening_balance': op,
                    'period_debit': period_dr,
                    'period_credit': period_cr,
                    'closing_balance': closing,
                })
            rows = []
            opening_balance = _round2(sum(s['opening_balance'] for s in summary))
            closing_balance = _round2(sum(s['closing_balance'] for s in summary))

        out = {
            'success': True,
            'entity_name': entity_name or (entity_type.capitalize() + ' (Consolidated)'),
            'opening_balance': opening_balance,
            'closing_balance': closing_balance,
            'rows': rows,
        }
        if aging is not None:
            out['aging'] = aging
        if summary is not None:
            out['summary'] = summary
        return out
    except Exception as e:
        logger.exception("get_advanced_account_statement error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_treasury_summary(token_or_email=None):
    """
    Get treasury/bank account balances from the ledger only (no opening_balances table).
    For each cash/bank account: current_balance = sum(debit) - sum(credit) from ledger.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'read')
    if not is_valid:
        return error

    try:
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

        _MAX_ROWS = 50000  # Safety cap per account — bounded ledger scan
        ledger_balances = {}
        for code in bank_codes:
            total_debit = 0.0
            total_credit = 0.0
            for i, entry in enumerate(app_tables.ledger.search(account_code=code)):
                if i >= _MAX_ROWS:
                    logger.warning("get_treasury_summary: ledger scan capped at %d rows for account %s", _MAX_ROWS, code)
                    break
                total_debit += float(entry.get('debit', 0) or 0)
                total_credit += float(entry.get('credit', 0) or 0)
            ledger_balances[code] = _round2(total_debit - total_credit)

        result = []
        grand_total = 0.0
        for code in sorted(bank_codes):
            current = ledger_balances.get(code, 0)
            names = account_names.get(code, {})
            name_en = names.get('name_en', '') or names.get('name_ar', '') or code
            result.append({
                'account_code': code,
                'account_name': name_en,
                'name_en': names.get('name_en', ''),
                'name_ar': names.get('name_ar', ''),
                'opening_balance': 0,
                'ledger_balance': current,
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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        pre_entries = {}
        _MAX_SCAN = 50000  # Safety cap — bounded ledger scan
        _scan_i = 0
        for r in app_tables.ledger.search():
            _scan_i += 1
            if _scan_i > _MAX_SCAN:
                logger.warning("get_cash_bank_statement: ledger scan capped at %d rows", _MAX_SCAN)
                break
            c = str(r.get('account_code', '')).strip()
            if c not in codes:
                continue
            row_date = r.get('date')
            if isinstance(row_date, datetime):
                row_date = row_date.date()
            if d_from and row_date and row_date < d_from:
                pre_entries[c] = pre_entries.get(c, 0) + _round2((r.get('debit', 0) or 0) - (r.get('credit', 0) or 0))
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

        opening_label = 'رصيد بداية المدة / Opening balance'
        for c in codes:
            pre_bal = pre_entries.get(c, 0)
            balance_start = _round2(pre_bal)
            if balance_start == 0:
                continue
            ob_date = (d_from.isoformat() if d_from and hasattr(d_from, 'isoformat') else str(d_from)) if d_from else '2000-01-01'
            rows.append({
                'date': ob_date,
                'account_code': c,
                'account_name': account_names.get(c, c),
                'description': opening_label,
                'debit': balance_start if balance_start > 0 else 0,
                'credit': -balance_start if balance_start < 0 else 0,
                'reference_type': 'opening_balance',
                'reference_id': '',
                'created_at': '',
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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


# ===========================================================================
# 14. OPENING BALANCES (أرصدة أول المدة)
# ===========================================================================
# AUDIT: Opening balances were stored in opening_balances table and added
# separately in Treasury, Bank Statement, Customer/Supplier summaries (hybrid).
# post_opening_balances() uses post_journal_entry (no direct app_tables.ledger writes).
# Reports aggregate ledger balances without filtering by reference_type, except
# get_customer_summary / get_supplier_summary which filter by reference_type='opening_balance'
# only to break down opening per customer/supplier (sub-ledger); main balances are ledger-only.

def _get_account_type(account_code):
    """Return account_type (lowercase) for account_code from chart_of_accounts, or ''."""
    acct = app_tables.chart_of_accounts.get(code=account_code)
    if not acct:
        return ''
    return (acct.get('account_type') or '').strip().lower()


@anvil.server.callable
def post_opening_balances(financial_year, token_or_email=None):
    """
    Post opening balances as a single journal entry dated January 1st of the financial year.
    Reads from opening_balances table; creates one balanced JE in the ledger.
    - type=bank, name=account_code: DR (asset) or CR (liability/overdraft) per account type.
    - type=customer: DR 1100 (Accounts Receivable), reference_id=name for sub-ledger.
    - type=supplier: CR 2000 (Accounts Payable), reference_id=name for sub-ledger.
    Balancing amount goes to 3000 (Owner's Equity / Opening Equity).
    Idempotent: returns error if this financial_year was already posted (reference_type=opening_balance, reference_id=str(financial_year)).
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error
    try:
        year = int(financial_year)
    except (TypeError, ValueError):
        return {'success': False, 'message': 'financial_year must be a valid year (e.g. 2026)'}
    entry_date = date(year, 1, 1)
    if is_period_locked(entry_date):
        return {'success': False, 'message': 'Accounting period for that date is locked.'}
    ref_id = str(year)
    try:
        for r in app_tables.ledger.search(reference_type='opening_balance', reference_id=ref_id):
            return {'success': False, 'message': f'Opening balances for {year} are already posted. Do not post again.'}
    except Exception:
        pass
    if not _validate_account_exists('3000'):
        return {'success': False, 'message': 'Account 3000 (Owner\'s Equity) not found. Run seed_default_accounts.'}

    try:
        rows = list(app_tables.opening_balances.search())
    except Exception:
        rows = []
    lines = []
    total_debit = 0.0
    total_credit = 0.0

    for r in rows:
        entity_type = (r.get('type') or '').strip().lower()
        name = (r.get('name') or '').strip()
        amount = _round2(float(r.get('opening_balance', 0) or 0))
        if amount == 0:
            continue
        if entity_type == 'bank':
            if not name:
                continue
            acct_type = _get_account_type(name)
            if not _validate_account_exists(name):
                continue
            if acct_type in ('asset', 'expense'):
                if amount > 0:
                    lines.append({'account_code': name, 'debit': amount, 'credit': 0, 'reference_id': ref_id})
                    total_debit += amount
                else:
                    lines.append({'account_code': name, 'debit': 0, 'credit': abs(amount), 'reference_id': ref_id})
                    total_credit += abs(amount)
            else:
                if amount > 0:
                    lines.append({'account_code': name, 'debit': 0, 'credit': amount, 'reference_id': ref_id})
                    total_credit += amount
                else:
                    lines.append({'account_code': name, 'debit': abs(amount), 'credit': 0, 'reference_id': ref_id})
                    total_debit += abs(amount)
        elif entity_type == 'customer':
            if not _validate_account_exists('1100'):
                continue
            if amount < 0:
                return {'success': False, 'message': f'Customer opening balance for "{name}" is negative ({amount}). Use a positive amount or adjust manually.'}
            lines.append({'account_code': '1100', 'debit': amount, 'credit': 0, 'reference_id': name or ref_id})
            total_debit += amount
        elif entity_type == 'supplier':
            if not _validate_account_exists('2000'):
                continue
            if amount < 0:
                return {'success': False, 'message': f'Supplier opening balance for "{name}" is negative ({amount}). Use a positive amount or adjust manually.'}
            lines.append({'account_code': '2000', 'debit': 0, 'credit': amount, 'reference_id': name or ref_id})
            total_credit += amount

    diff = _round2(total_debit - total_credit)
    if abs(diff) > 0.005:
        # Balance to 3000 (Opening Equity): excess debits -> CR 3000; excess credits -> DR 3000
        lines.append({
            'account_code': '3000',
            'debit': abs(diff) if diff < 0 else 0,
            'credit': diff if diff > 0 else 0,
            'reference_id': ref_id,
        })
        if diff > 0:
            total_credit += diff
        else:
            total_debit += abs(diff)
    if abs(total_debit - total_credit) > 0.01:
        return {'success': False, 'message': 'Opening balances do not balance. Check amounts.'}
    if not lines:
        return {'success': True, 'transaction_id': None, 'message': 'No non-zero opening balances to post.'}

    entries_for_je = []
    for line in lines:
        e = {
            'account_code': line['account_code'],
            'debit': _round2(line.get('debit', 0)),
            'credit': _round2(line.get('credit', 0)),
        }
        if line.get('reference_id') is not None and str(line.get('reference_id', '')).strip() != ref_id:
            e['reference_type'] = 'opening_balance'
            e['reference_id'] = _safe_str(line.get('reference_id', ref_id))
        entries_for_je.append(e)

    desc = f'Opening balances as at 1 Jan {year}'
    result = post_journal_entry(entry_date, entries_for_je, desc, 'opening_balance', ref_id, user_email)
    if result.get('success'):
        logger.info("Opening balances for %s posted (transaction %s) by %s", year, result.get('transaction_id'), user_email)
    return result


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


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
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def delete_opening_balance(name, entity_type, token_or_email=None):
    """Delete an opening balance row from the opening_balances table."""
    user_email = _require_permission(token_or_email, 'manage_opening_balances', fallback_action='admin')
    try:
        deleted = False
        for r in app_tables.opening_balances.search(name=name, type=entity_type):
            r.delete()
            deleted = True

        if not deleted:
            return {'success': False, 'message': 'Opening balance not found'}

        try:
            _audit(
                user_email, 'delete_opening_balance',
                'opening_balances', name,
                None, {'type': entity_type}
            )
        except Exception:
            pass

        logger.info("Opening balance deleted: %s (%s) by %s", name, entity_type, user_email)
        return {'success': True}
    except Exception as e:
        logger.exception("delete_opening_balance error")
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


# ─────────────────────────────────────────────────────────────────────
# MIGRATION: Fix old payment ledger descriptions
# ─────────────────────────────────────────────────────────────────────

def _migrate_fix_payment_descriptions():
    """
    Auto-run migration: fix old payment ledger entries where ALL lines
    had the same description (including bank fee / FX text on every line).
    Idempotent — only touches records that still have the old format.
    """
    import re
    fixed_count = 0
    skipped = 0

    payment_entries = list(app_tables.ledger.search(reference_type='payment'))
    txn_groups = {}
    for entry in payment_entries:
        txn_id = entry.get('transaction_id', '')
        if txn_id:
            txn_groups.setdefault(txn_id, []).append(entry)

    bank_fee_pattern = re.compile(r'(.*?)\s*[—\-]+\s*Bank fee[:\s]+[\d,]+\.?\d*\s*EGP', re.IGNORECASE)

    for txn_id, entries in txn_groups.items():
        has_bank_fee_issue = False
        for e in entries:
            desc = _safe_str(e.get('description', ''))
            acct = _safe_str(e.get('account_code', ''))
            if acct not in ('6090',) and bank_fee_pattern.search(desc):
                has_bank_fee_issue = True
                break

        if not has_bank_fee_issue:
            skipped += 1
            continue

        sample_desc = _safe_str(entries[0].get('description', ''))
        match = bank_fee_pattern.match(sample_desc)
        if not match:
            skipped += 1
            continue

        base_desc = match.group(1).strip()
        fee_match = re.search(r'Bank fee[:\s]+([\d,]+\.?\d*)\s*EGP', sample_desc, re.IGNORECASE)
        fee_amount_str = fee_match.group(1) if fee_match else '0'

        for e in entries:
            acct = _safe_str(e.get('account_code', ''))
            old_desc = _safe_str(e.get('description', ''))

            if acct == '6090':
                inv_match = re.search(r'(PI-\d{4}-\d{4})', old_desc)
                inv_num = inv_match.group(1) if inv_match else ''
                e.update(description=f"Bank fee for purchase invoice {inv_num} — {fee_amount_str} EGP")
                fixed_count += 1
            elif acct == '4110':
                gain_amount = _round2(float(e.get('credit', 0) or 0))
                e.update(description=base_desc + f" — أرباح فروق عملة (FX Gain): {gain_amount:,.2f} EGP")
                fixed_count += 1
            elif acct == '6110':
                loss_amount = _round2(float(e.get('debit', 0) or 0))
                e.update(description=base_desc + f" — خسائر فروق عملة (FX Loss): {loss_amount:,.2f} EGP")
                fixed_count += 1
            else:
                credit = float(e.get('credit', 0) or 0)
                try:
                    fee_val = float(fee_amount_str.replace(',', ''))
                except (ValueError, TypeError):
                    fee_val = 0
                if fee_val > 0 and acct != '2000' and abs(credit - fee_val) < 0.01:
                    inv_match = re.search(r'(PI-\d{4}-\d{4})', old_desc)
                    inv_num = inv_match.group(1) if inv_match else ''
                    e.update(description=f"Bank fee for purchase invoice {inv_num} — {fee_amount_str} EGP")
                    fixed_count += 1
                elif bank_fee_pattern.search(old_desc):
                    e.update(description=base_desc)
                    fixed_count += 1

    if fixed_count:
        logger.info("Migration: fixed %d ledger descriptions, skipped %d transactions", fixed_count, skipped)


# ─────────────────────────────────────────────────────────────────────
# AUTO-RUN: one-time migration on server module load
# ─────────────────────────────────────────────────────────────────────
try:
    _migrate_fix_payment_descriptions()
except Exception:
    logger.exception("Auto-migration _migrate_fix_payment_descriptions failed (non-fatal)")

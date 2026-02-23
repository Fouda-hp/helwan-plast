"""
sales_invoices.py - إنشاء وعرض فواتير البيع
=============================================
- create_sales_invoice: ينشئ فاتورة بيع من عقد (فاتورة واحدة فقط لكل عقد)
- get_draft_invoice_data: بيانات مسودة الفاتورة للعرض قبل الحفظ
- get_sales_invoice_pdf_data: بيانات الفاتورة كاملة مع بيانات الشركة
- get_sales_invoices_list: قائمة كل الفواتير
- get_contract_invoices: فواتير عقد معين

الجدول المطلوب: sales_invoices
الأعمدة:
  id, invoice_number, contract_number, quotation_number,
  client_name, company, phone, country, address, model,
  total_price, currency,
  created_by, created_at, notes
"""

import anvil.server
import anvil.tables
from anvil.tables import app_tables
import json
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

try:
    from .shared_utils import contracts_get_active as _contracts_get_active
except ImportError:
    from shared_utils import contracts_get_active as _contracts_get_active

try:
    from .QuotationManager import get_setting_value
except ImportError:
    try:
        from QuotationManager import get_setting_value
    except ImportError:
        def get_setting_value(key, default=''):
            try:
                row = app_tables.settings.get(setting_key=key)
                return row['setting_value'] if row else default
            except Exception:
                return default

logger = logging.getLogger(__name__)


def _has_sales_invoices_table():
    try:
        _ = app_tables.sales_invoices
        return True
    except Exception:
        return False


@anvil.tables.in_transaction
def _get_next_invoice_number():
    """Generate next invoice number: INV-YYYY-NNN using atomic counter.
    Uses the counters table with @in_transaction to prevent race conditions
    (same pattern as quotation_numbers.py).
    """
    from datetime import datetime
    year = datetime.now().year
    prefix = f'INV-{year}-'
    counter_key = f'sales_invoice_{year}'

    if not _has_sales_invoices_table():
        return f'{prefix}001'

    # Get max existing number from table (safety net)
    max_num = 0
    try:
        for row in app_tables.sales_invoices.search():
            inv_num = row.get('invoice_number', '') or ''
            if inv_num.startswith(prefix):
                try:
                    num = int(inv_num[len(prefix):])
                    if num > max_num:
                        max_num = num
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass

    # Atomic counter from counters table
    try:
        counter_row = app_tables.counters.get(key=counter_key)
        if counter_row is None:
            next_val = max_num + 1
            app_tables.counters.add_row(key=counter_key, value=next_val)
        else:
            current = counter_row['value'] or 0
            try:
                current = int(current)
            except (ValueError, TypeError):
                current = 0
            next_val = max(current, max_num) + 1
            counter_row['value'] = next_val
    except Exception:
        # Fallback if counters table doesn't exist
        next_val = max_num + 1

    return f'{prefix}{next_val:03d}'


def _get_company_settings():
    """Get company settings for invoice header."""
    return {
        'company_name_ar': get_setting_value('company_name_ar', 'شركة حلوان بلاست ذ.م.م'),
        'company_name_en': get_setting_value('company_name_en', 'Helwan Plast LLC'),
        'company_address_ar': get_setting_value('company_address_ar', 'المنطقة الصناعية الثانية - قطعة ٢٠'),
        'company_address_en': get_setting_value('company_address_en', 'Second Industrial Zone – Plot 20'),
        'company_email': get_setting_value('company_email', 'sales@helwanplast.com'),
        'company_website': get_setting_value('company_website', 'www.helwanplast.com'),
        'quotation_location_ar': get_setting_value('quotation_location_ar', 'القاهرة'),
        'quotation_location_en': get_setting_value('quotation_location_en', 'Cairo'),
    }


def _get_contract_payments_summary(quotation_number):
    """Get payments summary for a contract."""
    payments = []
    total_paid = 0

    try:
        if hasattr(app_tables, 'contract_payments'):
            for row in app_tables.contract_payments.search(quotation_number=int(quotation_number)):
                p = {
                    'amount': row['amount'],
                    'payment_date': row['payment_date'],
                    'payment_method': row['payment_method'],
                    'notes': row.get('notes', ''),
                }
                payments.append(p)
                total_paid += (row['amount'] or 0)
    except Exception as e:
        logger.debug("No contract_payments: %s", e)

    payments.sort(key=lambda x: x.get('payment_date', '') or '')
    return payments, total_paid


def _contract_has_invoice(quotation_number):
    """Check if a contract already has a sales invoice."""
    if not _has_sales_invoices_table():
        return False
    try:
        q_num = int(quotation_number)
        for row in app_tables.sales_invoices.search(quotation_number=q_num):
            return True  # Found at least one
    except Exception:
        pass
    return False


@anvil.server.callable
def get_draft_invoice_data(quotation_number, token_or_email=None):
    """Get contract data for draft invoice preview (not saved yet).
    Returns the same structure as get_sales_invoice_pdf_data but from contract data directly."""
    is_valid, _, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error or {'success': False, 'message': 'Permission denied'}

    try:
        q_num = int(quotation_number)
    except (TypeError, ValueError):
        return {'success': False, 'message': 'Invalid quotation number'}

    # Check if invoice already exists for this contract
    if _contract_has_invoice(q_num):
        return {'success': False, 'message': 'An invoice already exists for this contract. Only one invoice per contract is allowed.'}

    contract = _contracts_get_active(quotation_number=q_num)
    if not contract:
        return {'success': False, 'message': 'Contract not found'}

    try:
        # Parse total price
        tp = contract.get('total_price')
        try:
            total_price = float(str(tp).replace(',', '').replace('،', '').strip()) if tp else 0
        except (TypeError, ValueError):
            total_price = 0

        # Planned installments
        installments = []
        try:
            installments = json.loads(contract.get('payments_json') or '[]')
        except Exception:
            pass

        # Actual payments
        recorded_payments, total_paid = _get_contract_payments_summary(q_num)
        remaining = total_price - total_paid

        return {
            'success': True,
            'data': {
                'invoice_number': None,  # Draft — no number yet
                'contract_number': contract.get('contract_number', ''),
                'quotation_number': q_num,
                'client_name': contract.get('client_name', ''),
                'company': contract.get('company', ''),
                'phone': contract.get('phone', ''),
                'country': contract.get('country', ''),
                'address': contract.get('address', ''),
                'model': contract.get('model', ''),
                'total_price': total_price,
                'currency': contract.get('currency', 'EGP'),
                'created_at': None,  # Draft — no date yet
                'created_by': None,
                'notes': '',
                'installments': installments,
                'recorded_payments': recorded_payments,
                'total_paid': total_paid,
                'remaining': remaining,
            },
            'company': _get_company_settings(),
        }

    except Exception as e:
        logger.error("get_draft_invoice_data error: %s", e)
        return {'success': False, 'message': 'Failed to load draft invoice data'}


@anvil.server.callable
def create_sales_invoice(quotation_number, notes='', token_or_email=None):
    """Create a sales invoice from a contract.
    Only ONE invoice per contract is allowed."""
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error or {'success': False, 'message': 'Permission denied'}

    try:
        q_num = int(quotation_number)
    except (TypeError, ValueError):
        return {'success': False, 'message': 'Invalid quotation number'}

    # ── Duplicate check: one invoice per contract ──
    if _contract_has_invoice(q_num):
        return {'success': False, 'message': 'An invoice already exists for this contract. Only one invoice per contract is allowed.'}

    contract = _contracts_get_active(quotation_number=q_num)
    if not contract:
        return {'success': False, 'message': 'Contract not found'}

    if not _has_sales_invoices_table():
        return {'success': False, 'message': 'sales_invoices table not found. Please create it in Anvil Data Tables.'}

    try:
        invoice_number = _get_next_invoice_number()
        now = get_utc_now()

        tp = contract.get('total_price')
        try:
            total_price = float(str(tp).replace(',', '').replace('،', '').strip()) if tp else 0
        except (TypeError, ValueError):
            total_price = 0

        app_tables.sales_invoices.add_row(
            id=str(uuid.uuid4())[:12],
            invoice_number=invoice_number,
            contract_number=contract['contract_number'],
            quotation_number=q_num,
            client_name=contract.get('client_name', ''),
            company=contract.get('company', ''),
            phone=contract.get('phone', ''),
            country=contract.get('country', ''),
            address=contract.get('address', ''),
            model=contract.get('model', ''),
            total_price=total_price,
            currency=contract.get('currency', 'EGP'),
            created_by=user_email,
            created_at=now.isoformat(),
            notes=str(notes or ''),
        )

        return {
            'success': True,
            'invoice_number': invoice_number,
            'message': f'Invoice {invoice_number} created successfully',
        }

    except Exception as e:
        logger.error("create_sales_invoice error: %s", e)
        return {'success': False, 'message': f'Failed to create invoice: {e}'}


@anvil.server.callable
def get_sales_invoice_pdf_data(invoice_number, token_or_email=None):
    """Get full invoice data for display/print, including company settings and payments."""
    is_valid, _, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error or {'success': False, 'message': 'Permission denied'}

    if not _has_sales_invoices_table():
        return {'success': False, 'message': 'sales_invoices table not found'}

    try:
        inv = app_tables.sales_invoices.get(invoice_number=str(invoice_number))
        if not inv:
            return {'success': False, 'message': 'Invoice not found'}

        q_num = inv['quotation_number']

        # Get planned installments from contract
        installments = []
        contract = _contracts_get_active(quotation_number=q_num)
        if contract:
            try:
                installments = json.loads(contract.get('payments_json') or '[]')
            except Exception:
                pass

        # Get actual payments
        recorded_payments, total_paid = _get_contract_payments_summary(q_num)

        total_price = inv['total_price'] or 0
        remaining = total_price - total_paid

        return {
            'success': True,
            'data': {
                'invoice_number': inv['invoice_number'],
                'contract_number': inv['contract_number'],
                'quotation_number': q_num,
                'client_name': inv['client_name'],
                'company': inv['company'],
                'phone': inv['phone'],
                'country': inv['country'],
                'address': inv['address'],
                'model': inv['model'],
                'total_price': total_price,
                'currency': inv.get('currency', 'EGP'),
                'created_at': inv['created_at'],
                'created_by': inv['created_by'],
                'notes': inv.get('notes', ''),
                'installments': installments,
                'recorded_payments': recorded_payments,
                'total_paid': total_paid,
                'remaining': remaining,
            },
            'company': _get_company_settings(),
        }

    except Exception as e:
        logger.error("get_sales_invoice_pdf_data error: %s", e)
        return {'success': False, 'message': 'Failed to load invoice data'}


@anvil.server.callable
def get_sales_invoices_list(search='', token_or_email=None):
    """Get list of all sales invoices."""
    is_valid, _, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error or {'success': False, 'message': 'Permission denied'}

    if not _has_sales_invoices_table():
        return {'success': True, 'data': []}

    try:
        search_lower = (search or '').strip().lower()
        data = []
        for row in app_tables.sales_invoices.search():
            inv_num = row.get('invoice_number', '') or ''
            client = row.get('client_name', '') or ''
            contract = row.get('contract_number', '') or ''

            if search_lower:
                if (search_lower not in inv_num.lower()
                    and search_lower not in client.lower()
                    and search_lower not in contract.lower()):
                    continue

            data.append({
                'invoice_number': inv_num,
                'contract_number': contract,
                'client_name': client,
                'model': row.get('model', ''),
                'total_price': row.get('total_price', 0),
                'created_at': row.get('created_at', ''),
            })

        data.sort(key=lambda x: x.get('invoice_number', ''), reverse=True)
        return {'success': True, 'data': data}

    except Exception as e:
        logger.error("get_sales_invoices_list error: %s", e)
        return {'success': False, 'message': 'Failed to load invoices list'}


@anvil.server.callable
def get_contract_invoices(quotation_number, token_or_email=None):
    """Get all invoices for a specific contract."""
    is_valid, _, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error or {'success': False, 'message': 'Permission denied'}

    if not _has_sales_invoices_table():
        return {'success': True, 'data': []}

    try:
        q_num = int(quotation_number)
        data = []
        for row in app_tables.sales_invoices.search(quotation_number=q_num):
            data.append({
                'invoice_number': row.get('invoice_number', ''),
                'created_at': row.get('created_at', ''),
                'total_price': row.get('total_price', 0),
            })
        data.sort(key=lambda x: x.get('invoice_number', ''))
        return {'success': True, 'data': data}
    except Exception as e:
        logger.error("get_contract_invoices error: %s", e)
        return {'success': False, 'data': []}

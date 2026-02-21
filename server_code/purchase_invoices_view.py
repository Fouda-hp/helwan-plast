"""
purchase_invoices_view.py - فواتير الشراء (بروفورما → فاتورة فعلية)
================================================================
- get_new_purchase_invoice_data: بيانات إنشاء فاتورة شراء جديدة
- get_quotation_costs: تكاليف FOB من عرض السعر (للربط بعقد)
- save_purchase_invoice_proforma: حفظ البروفورما وتحويلها لفاتورة فعلية
- get_purchase_invoice_view_data: عرض فاتورة محفوظة
- get_supplier_purchase_invoices: فواتير مورد معين

يستخدم جدول purchase_invoices الموجود أصلاً.
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
    from .auth_permissions import require_permission_full as _require_permission
except ImportError:
    from auth_permissions import require_permission_full as _require_permission

try:
    from .shared_utils import contracts_get_active as _contracts_get_active
    from .shared_utils import contracts_search_active as _contracts_search_active
except ImportError:
    from shared_utils import contracts_get_active as _contracts_get_active
    from shared_utils import contracts_search_active as _contracts_search_active

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


def _parse_cost(val):
    """Parse cost value to float."""
    if val is None or val == '':
        return 0.0
    try:
        return float(str(val).replace(',', '').replace('،', '').strip())
    except (TypeError, ValueError):
        return 0.0


def _get_next_pi_number():
    """Generate next purchase invoice number: PI-YYYY-NNNN"""
    from datetime import datetime
    year = datetime.now().year
    prefix = f'PI-{year}-'
    max_num = 0

    try:
        for row in app_tables.purchase_invoices.search():
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

    return f'{prefix}{(max_num + 1):04d}'


@anvil.server.callable
def get_new_purchase_invoice_data(supplier_id, token_or_email=None):
    """Get data needed for creating a new proforma purchase invoice."""
    is_valid, _, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error or {'success': False, 'message': 'Permission denied'}

    try:
        # Get supplier info
        supplier = app_tables.suppliers.get(id=str(supplier_id))
        if not supplier:
            return {'success': False, 'message': 'Supplier not found'}

        supplier_data = {
            'id': supplier['id'],
            'name': supplier.get('name', ''),
            'company': supplier.get('company', ''),
            'phone': supplier.get('phone', ''),
            'email': supplier.get('email', ''),
            'country': supplier.get('country', ''),
        }

        # Get all contracts for dropdown
        contracts_list = []
        try:
            for c in _contracts_search_active():
                contracts_list.append({
                    'contract_number': c.get('contract_number', ''),
                    'quotation_number': c.get('quotation_number'),
                    'client_name': c.get('client_name', ''),
                    'model': c.get('model', ''),
                })
        except Exception as e:
            logger.debug("Error loading contracts: %s", e)

        return {
            'success': True,
            'supplier': supplier_data,
            'contracts': contracts_list,
            'company': _get_company_settings(),
        }

    except Exception as e:
        logger.error("get_new_purchase_invoice_data error: %s", e)
        return {'success': False, 'message': 'Failed to load data'}


@anvil.server.callable
def get_quotation_costs(quotation_number, token_or_email=None):
    """Get FOB costs and machine config from a quotation (for contract-linked invoices)."""
    is_valid, _, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error or {'success': False, 'message': 'Permission denied'}

    try:
        q_num = int(quotation_number)
    except (TypeError, ValueError):
        return {'success': False, 'message': 'Invalid quotation number'}

    try:
        q_row = app_tables.quotations.get(**{'Quotation#': q_num})
        if not q_row:
            return {'success': False, 'message': 'Quotation not found'}

        fob_standard = _parse_cost(q_row.get('Standard Machine FOB cost'))
        fob_with_cylinders = _parse_cost(q_row.get('Machine FOB cost With Cylinders'))
        cylinder_cost = fob_with_cylinders - fob_standard if fob_with_cylinders > fob_standard else 0
        exchange_rate = _parse_cost(q_row.get('Exchange Rate'))

        # Get machine config fields
        machine_config = {
            'model': q_row.get('Model', ''),
            'colors': q_row.get('Colors', ''),
            'width': q_row.get('Machine Width', ''),
            'material': q_row.get('Material', ''),
            'winder': q_row.get('Winder', ''),
        }

        return {
            'success': True,
            'fob_standard': fob_standard,
            'fob_with_cylinders': fob_with_cylinders,
            'cylinder_cost': cylinder_cost,
            'exchange_rate': exchange_rate,
            'machine_config': machine_config,
        }

    except Exception as e:
        logger.error("get_quotation_costs error: %s", e)
        return {'success': False, 'message': 'Failed to load quotation costs'}


@anvil.server.callable
def save_purchase_invoice_proforma(data, token_or_email=None):
    """Save a proforma purchase invoice to DB.
    data = {
        supplier_id, acid_number, contract_number (optional),
        quotation_number (optional), fob_standard, fob_with_cylinders,
        discount, date, notes, machine_config
    }
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error or {'success': False, 'message': 'Permission denied'}

    supplier_id = data.get('supplier_id')
    acid_number = (data.get('acid_number') or '').strip()

    if not supplier_id:
        return {'success': False, 'message': 'Supplier is required'}
    if not acid_number:
        return {'success': False, 'message': 'ACID Number is required'}

    fob_standard = _parse_cost(data.get('fob_standard', 0))
    fob_with_cylinders = _parse_cost(data.get('fob_with_cylinders', 0))
    discount = _parse_cost(data.get('discount', 0))
    # fob_with_cylinders already includes fob_standard + cylinder cost
    amount_due = fob_with_cylinders - discount

    contract_number = data.get('contract_number', '') or ''
    quotation_number = data.get('quotation_number')
    if quotation_number:
        try:
            quotation_number = int(quotation_number)
        except (TypeError, ValueError):
            quotation_number = None

    inv_date = data.get('date') or ''
    notes = data.get('notes', '') or ''
    machine_config = data.get('machine_config') or {}

    # Build items list for compatibility with existing purchase_invoices table
    items = [
        {'description': 'Standard Machine FOB', 'amount': fob_standard},
        {'description': 'Cylinders Cost', 'amount': fob_with_cylinders - fob_standard if fob_with_cylinders > fob_standard else 0},
    ]
    if discount > 0:
        items.append({'description': 'Discount', 'amount': -discount})

    try:
        invoice_number = _get_next_pi_number()
        now = get_utc_now()

        app_tables.purchase_invoices.add_row(
            id=str(uuid.uuid4())[:12],
            invoice_number=invoice_number,
            supplier_id=str(supplier_id),
            date=inv_date,
            contract_number=contract_number,
            machine_code=acid_number,
            items_json=json.dumps(items, ensure_ascii=False),
            machine_config_json=json.dumps(machine_config, ensure_ascii=False),
            subtotal=fob_with_cylinders,
            tax_amount=0,
            total=amount_due,
            total_egp=amount_due,
            paid_amount=0,
            status='draft',
            currency_code='USD',
            notes=notes,
            created_by=user_email,
            created_at=now,
            updated_at=now,
        )

        return {
            'success': True,
            'invoice_number': invoice_number,
            'message': f'Invoice {invoice_number} saved successfully',
        }

    except Exception as e:
        logger.error("save_purchase_invoice_proforma error: %s", e)
        return {'success': False, 'message': f'Failed to save invoice: {e}'}


@anvil.server.callable
def get_purchase_invoice_view_data(invoice_number, token_or_email=None):
    """Get full purchase invoice data for view/print/PDF."""
    is_valid, _, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error or {'success': False, 'message': 'Permission denied'}

    try:
        inv = app_tables.purchase_invoices.get(invoice_number=str(invoice_number))
        if not inv:
            return {'success': False, 'message': 'Invoice not found'}

        # Get supplier name
        supplier_name = ''
        supplier_company = ''
        supplier_phone = ''
        supplier_country = ''
        try:
            sup = app_tables.suppliers.get(id=inv['supplier_id'])
            if sup:
                supplier_name = sup.get('name', '')
                supplier_company = sup.get('company', '')
                supplier_phone = sup.get('phone', '')
                supplier_country = sup.get('country', '')
        except Exception:
            pass

        # Parse items
        items = []
        try:
            items = json.loads(inv.get('items_json') or '[]')
        except Exception:
            pass

        # Parse machine config
        machine_config = {}
        try:
            machine_config = json.loads(inv.get('machine_config_json') or '{}')
        except Exception:
            pass

        # Calculate FOB / Cylinders / Discount from items
        fob_standard = 0
        cylinder_cost = 0
        discount = 0
        for item in items:
            desc = (item.get('description') or '').lower()
            amt = _parse_cost(item.get('amount', 0))
            if 'fob' in desc and 'cylinder' not in desc:
                fob_standard = amt
            elif 'cylinder' in desc:
                cylinder_cost = amt
            elif 'discount' in desc:
                discount = abs(amt)

        fob_with_cylinders = fob_standard + cylinder_cost
        amount_due = inv.get('total', 0) or 0

        created_at = inv.get('created_at')
        if hasattr(created_at, 'isoformat'):
            created_at = created_at.isoformat()
        else:
            created_at = str(created_at or '')

        return {
            'success': True,
            'data': {
                'invoice_number': inv['invoice_number'],
                'acid_number': inv.get('machine_code', ''),
                'contract_number': inv.get('contract_number', ''),
                'supplier_id': inv.get('supplier_id', ''),
                'supplier_name': supplier_name,
                'supplier_company': supplier_company,
                'supplier_phone': supplier_phone,
                'supplier_country': supplier_country,
                'date': inv.get('date', ''),
                'fob_standard': fob_standard,
                'fob_with_cylinders': fob_with_cylinders,
                'cylinder_cost': cylinder_cost,
                'discount': discount,
                'amount_due': amount_due,
                'currency': inv.get('currency_code', 'USD'),
                'status': inv.get('status', 'draft'),
                'paid_amount': inv.get('paid_amount', 0) or 0,
                'machine_config': machine_config,
                'notes': inv.get('notes', ''),
                'created_at': created_at,
                'created_by': inv.get('created_by', ''),
            },
            'company': _get_company_settings(),
        }

    except Exception as e:
        logger.error("get_purchase_invoice_view_data error: %s", e)
        return {'success': False, 'message': 'Failed to load invoice data'}


@anvil.server.callable
def get_supplier_purchase_invoices(supplier_id, token_or_email=None):
    """Get all purchase invoices for a specific supplier."""
    is_valid, _, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error or {'success': False, 'message': 'Permission denied'}

    try:
        data = []
        for row in app_tables.purchase_invoices.search(supplier_id=str(supplier_id)):
            data.append({
                'invoice_number': row.get('invoice_number', ''),
                'status': row.get('status', 'draft'),
                'total': row.get('total', 0),
                'date': row.get('date', ''),
            })
        data.sort(key=lambda x: x.get('invoice_number', ''), reverse=True)
        return {'success': True, 'data': data}
    except Exception as e:
        logger.error("get_supplier_purchase_invoices error: %s", e)
        return {'success': False, 'data': []}

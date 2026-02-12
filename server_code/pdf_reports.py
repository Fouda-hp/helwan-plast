"""
pdf_reports.py - PDF Data Builders for Purchase Invoices, P&L, Supplier Statements
==================================================================================
Returns structured data dicts consumed by client-side HTML templates for print/PDF.
"""
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def format_number(num):
    try:
        if num is None:
            return "0"
        return "{:,.2f}".format(float(num))
    except (ValueError, TypeError):
        return str(num)


def build_purchase_invoice_pdf_data(invoice_row, supplier_row, import_costs, line_items=None):
    """
    Build PDF-ready data for a single purchase invoice.
    """
    inv = invoice_row or {}
    sup = supplier_row or {}
    subtotal = float(inv.get('subtotal', 0) or 0)
    tax = float(inv.get('tax_amount', 0) or 0)
    total = float(inv.get('total', 0) or 0)
    paid = float(inv.get('paid_amount', 0) or 0)

    costs_list = []
    import_total = 0
    for c in (import_costs or []):
        amt = float(c.get('amount', 0) or 0)
        import_total += amt
        costs_list.append({
            'type': c.get('cost_type', ''),
            'amount': format_number(amt),
            'description': c.get('description', ''),
            'date': str(c.get('cost_date', '')),
        })

    return {
        'invoice_number': inv.get('invoice_number', ''),
        'date': str(inv.get('date', '')),
        'due_date': str(inv.get('due_date', '')),
        'status': inv.get('status', ''),
        'machine_code': inv.get('machine_code', ''),
        'contract_number': inv.get('contract_number', ''),
        'notes': inv.get('notes', ''),
        'supplier': {
            'name': sup.get('name', ''),
            'contact': sup.get('contact_person', ''),
            'email': sup.get('email', ''),
            'phone': sup.get('phone', ''),
            'country': sup.get('country', ''),
        },
        'subtotal': format_number(subtotal),
        'tax': format_number(tax),
        'total': format_number(total),
        'paid': format_number(paid),
        'remaining': format_number(total - paid),
        'import_costs': costs_list,
        'import_total': format_number(import_total),
        'landed_cost': format_number(total + import_total),
        'print_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }


def build_pnl_report_data(inventory_items, purchase_invoices, date_from=None, date_to=None):
    """
    Build Profit & Loss report data.
    Revenue from sold items minus COGS (landed cost).
    """
    total_revenue = 0
    total_cogs = 0
    items_detail = []

    for item in (inventory_items or []):
        status = (item.get('status') or '').lower()
        if status != 'sold':
            continue
        selling = float(item.get('selling_price', 0) or 0)
        cost = float(item.get('total_cost', 0) or 0)
        profit = selling - cost
        total_revenue += selling
        total_cogs += cost
        items_detail.append({
            'machine_code': item.get('machine_code', ''),
            'contract': item.get('contract_number', ''),
            'selling_price': format_number(selling),
            'landed_cost': format_number(cost),
            'profit': format_number(profit),
            'profit_pct': '{:.1f}%'.format((profit / selling * 100) if selling else 0),
        })

    gross_profit = total_revenue - total_cogs
    return {
        'date_from': str(date_from or ''),
        'date_to': str(date_to or ''),
        'total_revenue': format_number(total_revenue),
        'total_cogs': format_number(total_cogs),
        'gross_profit': format_number(gross_profit),
        'margin_pct': '{:.1f}%'.format((gross_profit / total_revenue * 100) if total_revenue else 0),
        'items': items_detail,
        'item_count': len(items_detail),
        'print_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }


def build_supplier_statement_data(supplier_row, invoices, payments, date_from=None, date_to=None):
    """
    Build supplier account statement data.
    """
    sup = supplier_row or {}
    total_invoiced = 0
    total_paid = 0
    invoice_list = []

    for inv in (invoices or []):
        t = float(inv.get('total', 0) or 0)
        p = float(inv.get('paid_amount', 0) or 0)
        total_invoiced += t
        total_paid += p
        invoice_list.append({
            'invoice_number': inv.get('invoice_number', ''),
            'date': str(inv.get('date', '')),
            'total': format_number(t),
            'paid': format_number(p),
            'remaining': format_number(t - p),
            'status': inv.get('status', ''),
        })

    return {
        'supplier': {
            'name': sup.get('name', ''),
            'contact': sup.get('contact_person', ''),
            'email': sup.get('email', ''),
            'country': sup.get('country', ''),
        },
        'date_from': str(date_from or ''),
        'date_to': str(date_to or ''),
        'total_invoiced': format_number(total_invoiced),
        'total_paid': format_number(total_paid),
        'balance': format_number(total_invoiced - total_paid),
        'invoices': invoice_list,
        'print_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
    }

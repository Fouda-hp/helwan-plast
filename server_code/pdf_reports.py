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


def build_purchase_invoice_pdf_data(invoice_row, supplier_row, import_costs, line_items=None, payment_history=None):
    """
    Build PDF-ready data for a single purchase invoice (official document).
    Each amount has currency and exchange_rate; summary separates supplier vs costs; includes payment details.
    """
    inv = invoice_row or {}
    sup = supplier_row or {}
    subtotal = float(inv.get('subtotal', 0) or 0)
    tax = float(inv.get('tax_amount', 0) or 0)
    total = float(inv.get('total', 0) or 0)
    paid = float(inv.get('paid_amount', 0) or 0)
    if subtotal == 0 and total > 0:
        subtotal = total

    # If currency_code not stored (e.g. old/draft invoice) but exchange rate is set, treat as USD
    _cc = (inv.get('currency_code') or '').strip().upper()[:3]
    _rate = float(inv.get('exchange_rate_usd_to_egp') or 0)
    if _cc:
        inv_currency = _cc
    elif _rate > 0:
        inv_currency = 'USD'
    else:
        inv_currency = 'EGP'
    inv_rate = _rate if inv_currency == 'USD' and _rate > 0 else (1.0 if inv_currency == 'EGP' else _rate or 1.0)

    costs_list = []
    import_total = 0.0
    for c in (import_costs or []):
        amt_egp = float(c.get('amount_egp') or c.get('amount', 0) or 0)
        import_total += amt_egp
        curr = (c.get('original_currency') or c.get('currency') or 'EGP').upper()[:3]
        rate = float(c.get('exchange_rate') or 0) if curr != 'EGP' else 1.0
        if curr == 'EGP':
            rate = 1.0
        costs_list.append({
            'type': c.get('cost_type', ''),
            'amount': format_number(amt_egp),
            'amount_egp': amt_egp,
            'currency': curr,
            'exchange_rate': format_number(rate) if rate else '1',
            'description': c.get('description', ''),
            'date': str(c.get('cost_date', '')),
        })

    payments_list = []
    for p in (payment_history or []):
        amt = float(p.get('amount_egp', p.get('amount', 0)) or 0)
        curr = (p.get('currency_code') or 'EGP').upper()[:3]
        rate = float(p.get('exchange_rate') or 1) if curr != 'EGP' else 1.0
        payments_list.append({
            'date': str(p.get('date', '')),
            'amount': format_number(amt),
            'amount_egp': amt,
            'currency': curr,
            'exchange_rate': format_number(rate) if rate else '1',
            'description': p.get('description', ''),
        })

    supplier_total_egp = total  # invoice total in EGP (stored/converted)
    landed_egp = supplier_total_egp + import_total

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
        'invoice_currency': inv_currency,
        'invoice_exchange_rate': format_number(inv_rate) if inv_rate else '1',
        'subtotal': format_number(subtotal),
        'tax': format_number(tax),
        'total': format_number(total),
        'paid': format_number(paid),
        'remaining': format_number(total - paid),
        'import_costs': costs_list,
        'import_total': format_number(import_total),
        'landed_cost': format_number(landed_egp),
        'payment_history': payments_list,
        'summary': {
            'supplier_total_egp': format_number(supplier_total_egp),
            'import_costs_total_egp': format_number(import_total),
            'landed_cost_egp': format_number(landed_egp),
        },
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

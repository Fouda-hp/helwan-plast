"""
routing.py - Central hash-based routing table
Used by LoginForm, LauncherForm and AdminPanel instead of duplicate if-elif chains.
"""

# Routing table: hash -> Form name
ROUTES = {
    '#launcher':          'LauncherForm',
    '#calculator':        'CalculatorForm',
    '#clients':           'ClientListForm',
    '#database':          'DatabaseForm',
    '#admin':             'AdminPanel',
    '#import':            'DataImportForm',
    '#quotation-print':   'QuotationPrintForm',
    '#contract-print':    'ContractPrintForm',
    '#contract-new':      'ContractPrintForm',
    '#contract-edit':     'ContractEditForm',
    '#payment-dashboard': 'PaymentDashboardForm',
    '#invoice-manager':   'InvoiceManagerForm',
    '#follow-ups':        'FollowUpDashboardForm',
    '#login':             'LoginForm',
    # Accounting sub-forms
    '#accountant':        'AccountantForm',
    '#customer-summary':  'CustomerSummaryForm',
    '#inventory':         'InventoryForm',
    '#purchase-invoices': 'PurchaseInvoicesForm',
    '#suppliers':         'SuppliersForm',
    '#supplier-summary':  'SupplierSummaryForm',
}

# Admin-only routes (list instead of set for Skulpt compatibility)
ADMIN_ONLY = [
    '#admin', '#accountant', '#customer-summary',
    '#inventory', '#purchase-invoices', '#suppliers', '#supplier-summary',
]

# Prefix-based routes (e.g. #client-detail-123)
PREFIX_ROUTES = {
    '#client-detail': 'ClientDetailForm',
}

# Default form
DEFAULT_FORM = 'LauncherForm'


def resolve_route(hash_val):
    """
    Determine the Form for the given hash.
    Returns: (form_name, is_admin_only)
    """
    if not hash_val or hash_val == '#':
        return DEFAULT_FORM, False

    # Exact match first
    form = ROUTES.get(hash_val)
    if form:
        is_admin = hash_val in ADMIN_ONLY
        return form, is_admin

    # Prefix match (e.g., #client-detail-XYZ)
    for prefix in PREFIX_ROUTES:
        if hash_val.startswith(prefix):
            fname = PREFIX_ROUTES[prefix]
            is_admin = prefix in ADMIN_ONLY
            return fname, is_admin

    return DEFAULT_FORM, False

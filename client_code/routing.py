"""
routing.py - جدول التوجيه المركزي (Hash-based routing)
=====================================================
يُستخدم من LoginForm و LauncherForm بدلاً من if-elif chains مكررة.
"""

# جدول التوجيه: hash → اسم الـ Form
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
    '#follow-ups':        'FollowUpDashboardForm',
    '#login':             'LoginForm',
}

# مسارات تتطلب صلاحية أدمن
ADMIN_ONLY = {'#admin'}

# مسارات تبدأ بـ prefix (مثل #client-detail-123)
PREFIX_ROUTES = {
    '#client-detail': 'ClientDetailForm',
}

# الصفحة الافتراضية
DEFAULT_FORM = 'LauncherForm'


def resolve_route(hash_val):
    """
    يُحدد الـ Form المناسب للـ hash.
    يُرجع: (form_name: str, is_admin_only: bool)
    """
    if not hash_val or hash_val == '#':
        return DEFAULT_FORM, False

    # Exact match first
    form = ROUTES.get(hash_val)
    if form:
        return form, hash_val in ADMIN_ONLY

    # Prefix match (e.g., #client-detail-XYZ)
    for prefix, form_name in PREFIX_ROUTES.items():
        if hash_val.startswith(prefix):
            return form_name, prefix in ADMIN_ONLY

    return DEFAULT_FORM, False

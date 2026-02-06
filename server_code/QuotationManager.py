import anvil.google.auth, anvil.google.drive, anvil.google.mail
from anvil.google.drive import app_files
import anvil.secrets
"""
QuotationManager.py - إدارة العملاء والعروض السعرية
====================================================
الميزات:
- الترقيم التلقائي للعملاء والعروض
- حفظ اسم العميل في جدول العروض مباشرة
- سجل التدقيق مع IP Address
- تحسين استعلامات N+1
- التحقق من الصلاحيات في دوال الحذف
- استخدام نظام logging بدلاً من print
"""

import anvil.server
from anvil.tables import app_tables
from datetime import datetime
import json
import uuid
import logging
import csv
import io

# استيراد الدوال المشتركة من AuthManager
from . import AuthManager

# =========================================================
# إعداد نظام التسجيل (Logging)
# =========================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =========================================================
# استخدام دالة log_audit من AuthManager (موحدة)
# =========================================================
def log_audit(action, table_name, record_id, old_data, new_data, user_email='system', ip_address=None):
    """
    استخدام دالة التدقيق الموحدة من AuthManager
    """
    AuthManager.log_audit(action, table_name, record_id, old_data, new_data, user_email, ip_address)


def get_client_ip():
    """
    الحصول على IP Address
    """
    return AuthManager.get_client_ip()


# =========================================================
# دوال مساعدة للتحقق من الصلاحيات
# =========================================================
def _require_authenticated(token_or_email):
    """
    التحقق من أن المستخدم مسجل دخول (أي دور ما عدا viewer)
    يُرجع tuple: (is_valid, user_email, error_response)
    """
    if not token_or_email:
        return False, None, {'success': False, 'message': 'Authentication required'}

    # محاولة التحقق من الجلسة (token)
    result = AuthManager.validate_token(token_or_email)
    if result and result.get('valid'):
        user = result.get('user', {})
        return True, user.get('email', 'unknown'), None

    # محاولة التحقق بالبريد الإلكتروني
    if '@' in str(token_or_email):
        from anvil.tables import app_tables as _at
        user_row = _at.users.get(email=str(token_or_email).strip().lower())
        if user_row and user_row.get('is_active') and user_row.get('is_approved'):
            return True, str(token_or_email).strip().lower(), None

    return False, None, {'success': False, 'message': 'Invalid or expired session'}


def _require_permission(token_or_email, permission):
    """
    التحقق من أن المستخدم لديه صلاحية معينة
    يُرجع tuple: (is_valid, user_email, error_response)
    """
    is_valid, user_email, error = _require_authenticated(token_or_email)
    if not is_valid:
        return False, None, error

    # الأدمن لديه كل الصلاحيات
    if AuthManager.is_admin(token_or_email) or AuthManager.is_admin_by_email(token_or_email):
        return True, user_email, None

    # التحقق من الصلاحية المطلوبة
    if AuthManager.check_permission(token_or_email, permission):
        return True, user_email, None

    return False, user_email, {'success': False, 'message': f'Permission denied: {permission} access required'}


def check_delete_permission(token_or_email):
    """
    التحقق من صلاحية الحذف
    """
    # الأدمن لديه صلاحية كاملة
    if AuthManager.is_admin(token_or_email) or AuthManager.is_admin_by_email(token_or_email):
        return True, None

    # التحقق من صلاحية delete
    if token_or_email and AuthManager.check_permission(token_or_email, 'delete'):
        return True, None

    return False, {'success': False, 'message': 'Permission denied: delete access required'}


# =========================================================
# دوال الترقيم التلقائي
# =========================================================
@anvil.server.callable
def get_next_client_code():
    """
    الحصول على رمز العميل التالي
    يُستخدم عند تحميل الصفحة أو زر NEW
    """
    return _get_next_number('clients', 'Client Code')


@anvil.server.callable
def get_next_quotation_number():
    """
    الحصول على رقم العرض التالي
    يُستخدم عند تحميل الصفحة أو زر NEW
    """
    return _get_next_number('quotations', 'Quotation#')


@anvil.server.callable
def get_or_create_client_code(client_name, phone):
    """
    البحث عن عميل بالهاتف أو إنشاء رمز جديد
    الهاتف يجب أن يكون فريداً
    """
    if not phone:
        return None

    phone = str(phone).strip()
    client_name = str(client_name).strip() if client_name else ""

    logger.info(f"Checking phone='{phone}'")

    # البحث بالهاتف فقط (باستثناء المحذوف)
    row = app_tables.clients.get(Phone=phone, is_deleted=False)

    if row:
        code = str(row["Client Code"])
        logger.info(f"Existing phone found, client_code={code}")
        return code

    # هاتف جديد -> عميل جديد
    new_code = _get_next_number('clients', 'Client Code')
    logger.info(f"New phone, generated client_code={new_code}")
    return str(new_code)


@anvil.server.callable
def get_quotation_number_if_needed(current_number, model):
    """
    الحصول على رقم العرض إذا لزم الأمر
    يُستدعى من JavaScript عند بناء كود النموذج
    """
    if current_number:
        logger.info(f"Quotation number already exists: {current_number}")
        return int(current_number)

    if not model:
        logger.info("No model provided")
        return None

    new_q = _get_next_number('quotations', 'Quotation#')
    logger.info(f"Generated new quotation number: {new_q}")
    return int(new_q)


import threading
_number_locks = {
    'clients': threading.Lock(),
    'quotations': threading.Lock(),
}


def _get_next_number(table_name, column_name):
    """
    توليد الرقم التالي بشكل آمن مع Locking لمنع Race Conditions
    يبحث عن القيمة القصوى ويضيف 1
    """
    lock = _number_locks.get(table_name, threading.Lock())
    with lock:
        table = getattr(app_tables, table_name)
        max_val = 0

        for row in table.search():
            val = row[column_name]
            if val is not None:
                try:
                    num = int(val) if isinstance(val, str) else val
                    if num > max_val:
                        max_val = num
                except (ValueError, TypeError):
                    pass

        next_val = max_val + 1
        logger.info(f"{table_name}.{column_name}: max={max_val}, next={next_val}")
        return next_val


# =========================================================
# دوال التحقق المساعدة
# =========================================================
def safe_strip(v):
    """تنظيف النص"""
    return str(v).strip() if v not in (None, "") else ""


def safe_int(v):
    """تحويل آمن لـ int"""
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def safe_float(v):
    """تحويل آمن لـ float"""
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def yes_no(v):
    """تحويل bool إلى YES/NO"""
    return "YES" if v else "NO"


@anvil.server.callable
def phone_exists(phone, exclude_client_code=None):
    """التحقق من وجود الهاتف (باستثناء المحذوف)"""
    phone = safe_strip(phone)
    if not phone:
        return False

    if exclude_client_code is not None:
        exclude_client_code = str(exclude_client_code)

    rows = app_tables.clients.search(Phone=phone, is_deleted=False)
    for r in rows:
        if exclude_client_code is not None and str(r['Client Code']) == exclude_client_code:
            continue
        return True

    return False


@anvil.server.callable
def client_exists(client_code):
    """التحقق من وجود العميل (غير محذوف)"""
    if not client_code:
        return False

    client_code_str = str(client_code)
    row = app_tables.clients.get(**{"Client Code": client_code_str})
    return row is not None and not row.get('is_deleted', False)


@anvil.server.callable
def quotation_exists(quotation_number):
    """التحقق من وجود العرض (غير محذوف)"""
    if not quotation_number:
        return False

    quotation_int = safe_int(quotation_number)
    if quotation_int is None:
        return False

    row = app_tables.quotations.get(**{"Quotation#": quotation_int})
    return row is not None and not row.get('is_deleted', False)


# =========================================================
# دالة الحفظ الرئيسية
# =========================================================
@anvil.server.callable
def save_quotation(form_data, user_email='system', token_or_email=None):
    """
    دالة الحفظ الرئيسية مع الترقيم التلقائي وسجل التدقيق
    يتطلب مستخدم مسجل دخول بصلاحية create أو edit (ما عدا viewer)
    """
    # ===== التحقق من الصلاحيات =====
    auth_key = token_or_email or user_email
    if auth_key == 'system':
        return {'success': False, 'message': 'Authentication required. Please log in.'}

    is_valid, verified_email, error = _require_permission(auth_key, 'create')
    if not is_valid:
        # حاول صلاحية edit أيضاً (للتعديل)
        is_valid, verified_email, error = _require_permission(auth_key, 'edit')
        if not is_valid:
            is_valid, verified_email, error = _require_permission(auth_key, 'edit_own')
            if not is_valid:
                return error

    # استخدم الإيميل المُتحقق منه بدلاً من المُمرر
    user_email = verified_email or user_email

    ip_address = get_client_ip()
    logger.info(f"Received form_data for save from {user_email}")

    # استخراج البيانات
    client_code_raw = form_data.get('Client Code')
    quotation_number_raw = form_data.get('Quotation#')
    model = safe_strip(form_data.get('Model'))
    client_name = safe_strip(form_data.get('Client Name'))

    client_code = str(client_code_raw) if client_code_raw else None
    quotation_number = safe_int(quotation_number_raw)

    # اكتشاف العميل الحالي vs الجديد
    existing_client_row = None
    if client_code:
        existing_client_row = app_tables.clients.get(**{"Client Code": str(client_code)})
        if existing_client_row and existing_client_row.get('is_deleted', False):
            existing_client_row = None

    is_existing_client = existing_client_row is not None
    is_new_client = not is_existing_client

    is_quotation = bool(
        safe_strip(form_data.get('Model')) and
        safe_strip(form_data.get('Quotation#'))
    )

    is_new_quotation = is_quotation and (not quotation_number or not quotation_exists(quotation_number))

    # التحقق من بيانات العميل (فقط إذا كان عميل جديد)
    missing = []

    if is_new_client:
        if not safe_strip(form_data.get('Client Name')):
            missing.append("Client Name")
        if not safe_strip(form_data.get('Company')):
            missing.append("Company")
        if not safe_strip(form_data.get('Phone')):
            missing.append("Phone")

        if missing:
            return {
                "success": False,
                "message": "Missing Client Data:\n" + "\n".join(missing)
            }

    # التحقق من بيانات العرض
    if is_quotation:
        q_missing = []
        if not form_data.get('Given Price'):
            q_missing.append("Given Price")
        if not form_data.get('Agreed Price'):
            q_missing.append("Agreed Price")

        if q_missing:
            return {
                "success": False,
                "message": "Quotation missing data:\n" + "\n".join(q_missing)
            }

    # التحقق من الهاتف
    phone = safe_strip(form_data.get('Phone'))

    if phone:
        phone_row = app_tables.clients.get(Phone=phone, is_deleted=False)

        if phone_row:
            if is_existing_client:
                if phone_row != existing_client_row:
                    return {"success": False, "message": "Phone already exists for another client"}
            else:
                return {"success": False, "message": "Phone already exists"}

    # التحقق من الأسعار
    if is_quotation:
        given = safe_float(form_data.get('Given Price'))
        agreed = safe_float(form_data.get('Agreed Price'))

        if given is None or agreed is None:
            return {
                "success": False,
                "message": "Given Price and Agreed Price must be valid numbers"
            }

        if agreed > given:
            return {
                "success": False,
                "message": f"Agreed Price ({agreed:,.0f}) cannot be greater than Given Price ({given:,.0f})"
            }

        is_overseas = bool(form_data.get('Overseas clients'))

        if is_overseas:
            overseas_price = safe_float(form_data.get('overseas_price'))

            if overseas_price is None or overseas_price <= 0:
                return {"success": False, "message": "Overseas price is missing or invalid"}

            if agreed < overseas_price:
                return {
                    "success": False,
                    "message": f"Agreed Price ({agreed:,.0f}) must not be less than Overseas Price ({overseas_price:,.0f})"
                }
        else:
            in_stock_price = safe_float(form_data.get('In Stock'))
            new_order_price = safe_float(form_data.get('New Order'))

            if in_stock_price is None or in_stock_price <= 0:
                return {"success": False, "message": "In Stock price is missing or invalid"}

            if new_order_price is None or new_order_price <= 0:
                return {"success": False, "message": "New Order price is missing or invalid"}

            pricing_mode = safe_strip(form_data.get('Pricing Mode'))

            if agreed < new_order_price and not pricing_mode:
                return {
                    "success": False,
                    "code": "SELECT_PRICING_MODE",
                    "message": "Please select pricing mode"
                }

            if pricing_mode == "In Stock":
                if agreed < in_stock_price:
                    return {
                        "success": False,
                        "message": f"Agreed Price ({agreed:,.0f}) must not be less than In Stock price ({in_stock_price:,.0f})"
                    }

            elif pricing_mode == "New Order":
                if agreed < new_order_price:
                    return {
                        "success": False,
                        "message": f"Agreed Price ({agreed:,.0f}) must not be less than New Order price ({new_order_price:,.0f})"
                    }

                if agreed > in_stock_price:
                    return {
                        "success": False,
                        "message": f"For New Order mode, Agreed Price ({agreed:,.0f}) cannot exceed In Stock price ({in_stock_price:,.0f})"
                    }

    # الترقيم التلقائي من السيرفر
    if is_new_client:
        client_code = str(_get_next_number('clients', 'Client Code'))

    if is_new_quotation and is_quotation:
        quotation_number = _get_next_number('quotations', 'Quotation#')

    logger.info(f"Saving: client_code={client_code}, quotation_number={quotation_number}")

    # الحفظ مع التدقيق
    client_action = save_client_data(client_code, form_data, is_new_client, user_email, ip_address)

    quotation_action = None
    if is_quotation:
        # الحصول على اسم العميل لحفظه مع العرض
        if not client_name and existing_client_row:
            client_name = existing_client_row.get('Client Name', '')

        quotation_action = save_quotation_data(
            client_code,
            quotation_number,
            form_data,
            is_new_quotation,
            user_email,
            ip_address,
            client_name  # تمرير اسم العميل
        )

    actions = [a for a in (client_action, quotation_action) if a]

    return {
        "success": True,
        "message": " + ".join(actions),
        "client_code": client_code,
        "quotation_number": quotation_number if is_quotation else None
    }


# =========================================================
# دوال الحفظ مع التدقيق
# =========================================================
def save_client_data(client_code, form_data, is_new, user_email='system', ip_address=None):
    """حفظ أو تحديث بيانات العميل مع التدقيق"""

    date_value = form_data.get('Date')
    if date_value and isinstance(date_value, str):
        try:
            date_value = datetime.strptime(date_value, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            date_value = datetime.now().date()
    elif not date_value:
        date_value = datetime.now().date()

    data = {
        'Client Code': str(client_code),
        'Date': date_value,
        'Client Name': safe_strip(form_data.get('Client Name')),
        'Company': safe_strip(form_data.get('Company')),
        'Phone': safe_strip(form_data.get('Phone')),
        'Country': safe_strip(form_data.get('Country')),
        'Address': safe_strip(form_data.get('Address')),
        'Email': safe_strip(form_data.get('Email')),
        'Sales Rep': safe_strip(form_data.get('sales_rep') or form_data.get('Sales Rep')),
        'Source': safe_strip(form_data.get('Source')),
        'is_deleted': False,
        'updated_by': user_email,
        'updated_at': datetime.now()
    }

    if is_new:
        data['created_by'] = user_email
        data['created_at'] = datetime.now()
        app_tables.clients.add_row(**data)
        log_audit('CREATE', 'clients', client_code, None, data, user_email, ip_address)
        return "Added Client"

    row = app_tables.clients.get(**{"Client Code": str(client_code)})
    if row:
        # Get column names safely (handle both dict and object formats)
        try:
            columns = app_tables.clients.list_columns()
            column_names = [c['name'] if isinstance(c, dict) else c.name for c in columns]
        except (AttributeError, TypeError):
            column_names = list(data.keys())

        old_data = {k: row[k] for k in data.keys() if k in column_names}
        row.update(**data)
        log_audit('UPDATE', 'clients', client_code, old_data, data, user_email, ip_address)
    return "Updated Client"


def save_quotation_data(client_code, quotation_number, form_data, is_new, user_email='system', ip_address=None, client_name=''):
    """حفظ أو تحديث بيانات العرض مع التدقيق"""

    date_value = form_data.get('Date')
    if date_value and isinstance(date_value, str):
        try:
            date_value = datetime.strptime(date_value, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            date_value = datetime.now().date()
    elif not date_value:
        date_value = datetime.now().date()

    data = {
        'Client Code': str(client_code),
        'Quotation#': int(quotation_number),
        'Date': date_value,
        'Client Name': client_name or safe_strip(form_data.get('Client Name')),  # حفظ اسم العميل
        'Notes': safe_strip(form_data.get('Notes')),

        'Model': safe_strip(form_data.get('Model')),
        'Machine type': safe_strip(form_data.get('machine_type')),
        'Number of colors': safe_int(form_data.get('Number of colors')),
        'Machine width': safe_int(form_data.get('Machine width')),
        'Material': safe_strip(form_data.get('Material')),
        'Winder': safe_strip(form_data.get('Winder')),

        'Video inspection': yes_no(form_data.get('Video inspection')),
        'PLC': yes_no(form_data.get('PLC')),
        'Slitter': yes_no(form_data.get('Slitter')),
        'Pneumatic Unwind': yes_no(form_data.get('Pneumatic Unwind')),
        'Hydraulic Station Unwind': yes_no(form_data.get('Hydraulic Station Unwind')),
        'Pneumatic Rewind': yes_no(form_data.get('Pneumatic Rewind')),
        'Surface Rewind': yes_no(form_data.get('Surface Rewind')),

        'Given Price': safe_float(form_data.get('Given Price')),
        'Agreed Price': safe_float(form_data.get('Agreed Price')),
        "Standard Machine FOB cost": safe_strip(form_data.get("std_price")),
        "Machine FOB cost With Cylinders": safe_strip(form_data.get("price_with_cylinders")),
        'FOB price for over seas clients': safe_float(form_data.get('overseas_price')),
        'Exchange Rate': safe_float(form_data.get('exchange_rate')),
        'In Stock': safe_float(form_data.get('In Stock')),
        'New Order': safe_float(form_data.get('New Order')),
        'Pricing Mode': safe_strip(form_data.get('Pricing Mode')),

        'is_deleted': False,
        'updated_by': user_email,
        'updated_at': datetime.now()
    }

    # إضافة بيانات الأسطوانات
    for i in range(1, 13):
        data[f'Size in CM{i}'] = safe_strip(form_data.get(f'Size in CM{i}'))
        data[f"Count{i}"] = safe_strip(form_data.get(f"Count{i}"))
        data[f'Cost{i}'] = safe_strip(form_data.get(f'Cost{i}'))

    if is_new:
        data['created_by'] = user_email
        data['created_at'] = datetime.now()
        app_tables.quotations.add_row(**data)
        log_audit('CREATE', 'quotations', quotation_number, None, data, user_email, ip_address)
        return "Added Quotation"

    row = app_tables.quotations.get(**{"Quotation#": int(quotation_number)})
    if not row:
        raise Exception("Quotation not found")

    old_data = {}
    for k in data.keys():
        try:
            old_data[k] = row[k]
        except (KeyError, AttributeError):
            pass

    row.update(**data)
    log_audit('UPDATE', 'quotations', quotation_number, old_data, data, user_email, ip_address)
    return "Updated Quotation"


# =========================================================
# الحذف الناعم (مع التحقق من الصلاحيات)
# =========================================================
@anvil.server.callable
def soft_delete_client(client_code, token_or_email='admin'):
    """حذف عميل (يتطلب صلاحية الحذف)"""

    # التحقق من الصلاحية
    has_permission, error = check_delete_permission(token_or_email)
    if not has_permission:
        return error

    ip_address = get_client_ip()
    user_email = token_or_email if '@' in str(token_or_email) else 'admin'

    row = app_tables.clients.get(**{"Client Code": str(client_code)})
    if not row:
        return {"success": False, "message": "Client not found"}

    old_data = {"is_deleted": row.get('is_deleted', False)}

    row.update(
        is_deleted=True,
        deleted_at=datetime.now(),
        deleted_by=user_email
    )

    log_audit('SOFT_DELETE', 'clients', client_code, old_data, {"is_deleted": True}, user_email, ip_address)

    return {"success": True, "message": "Client deleted successfully"}


@anvil.server.callable
def soft_delete_quotation(quotation_number, token_or_email='admin'):
    """حذف عرض (يتطلب صلاحية الحذف)"""

    # التحقق من الصلاحية
    has_permission, error = check_delete_permission(token_or_email)
    if not has_permission:
        return error

    ip_address = get_client_ip()
    user_email = token_or_email if '@' in str(token_or_email) else 'admin'

    row = app_tables.quotations.get(**{"Quotation#": int(quotation_number)})
    if not row:
        return {"success": False, "message": "Quotation not found"}

    old_data = {"is_deleted": row.get('is_deleted', False)}

    row.update(
        is_deleted=True,
        deleted_at=datetime.now(),
        deleted_by=user_email
    )

    log_audit('SOFT_DELETE', 'quotations', quotation_number, old_data, {"is_deleted": True}, user_email, ip_address)

    return {"success": True, "message": "Quotation deleted successfully"}


@anvil.server.callable
def restore_client(client_code, token_or_email='admin'):
    """استعادة عميل محذوف (يتطلب صلاحية الحذف)"""

    has_permission, error = check_delete_permission(token_or_email)
    if not has_permission:
        return error

    ip_address = get_client_ip()
    user_email = token_or_email if '@' in str(token_or_email) else 'admin'

    row = app_tables.clients.get(**{"Client Code": str(client_code)})
    if not row:
        return {"success": False, "message": "Client not found"}

    row.update(
        is_deleted=False,
        deleted_at=None,
        deleted_by=None
    )

    log_audit('RESTORE', 'clients', client_code, {"is_deleted": True}, {"is_deleted": False}, user_email, ip_address)

    return {"success": True, "message": "Client restored successfully"}


@anvil.server.callable
def restore_quotation(quotation_number, token_or_email='admin'):
    """استعادة عرض محذوف (يتطلب صلاحية الحذف)"""

    has_permission, error = check_delete_permission(token_or_email)
    if not has_permission:
        return error

    ip_address = get_client_ip()
    user_email = token_or_email if '@' in str(token_or_email) else 'admin'

    row = app_tables.quotations.get(**{"Quotation#": int(quotation_number)})
    if not row:
        return {"success": False, "message": "Quotation not found"}

    row.update(
        is_deleted=False,
        deleted_at=None,
        deleted_by=None
    )

    log_audit('RESTORE', 'quotations', quotation_number, {"is_deleted": True}, {"is_deleted": False}, user_email, ip_address)

    return {"success": True, "message": "Quotation restored successfully"}


# =========================================================
# دوال الاسترجاع مع تحسين N+1 والترتيب
# =========================================================
@anvil.server.callable
def get_all_quotations(page=1, per_page=20, search='', include_deleted=False, token_or_email=None):
    """الحصول على العروض مع الترقيم والبحث - محسّن لمشكلة N+1"""
    is_valid, _, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return {"data": [], "page": 1, "per_page": per_page, "total": 0, "total_pages": 0}

    all_rows = list(app_tables.quotations.search())

    # تصفية المحذوف
    if not include_deleted:
        all_rows = [r for r in all_rows if not r.get('is_deleted', False)]

    # جلب جميع العملاء مرة واحدة (حل مشكلة N+1)
    all_clients = list(app_tables.clients.search())
    clients_dict = {str(c['Client Code']): c for c in all_clients}

    # فلتر البحث
    if search:
        search = search.lower()
        filtered = []
        for r in all_rows:
            client_code = str(r.get('Client Code', ''))
            client = clients_dict.get(client_code)

            # البحث في اسم العميل المحفوظ في العرض أو في جدول العملاء
            client_name = (r.get('Client Name') or '').lower()
            if not client_name and client:
                client_name = (client.get('Client Name') or '').lower()

            # البحث في الشركة من الـ quotation أو من جدول العملاء
            company = (r.get('Company') or '').lower()
            if not company and client:
                company = (client.get('Company') or '').lower()

            # البحث في التليفون من الـ quotation أو من جدول العملاء
            phone = (r.get('Phone') or '').lower()
            if not phone and client:
                phone = (client.get('Phone') or '').lower()

            # البحث في البلد
            country = (r.get('Country') or '').lower()
            if not country and client:
                country = (client.get('Country') or '').lower()

            if (search in client_name or
                search in company or
                search in phone or
                search in country or
                search in str(r.get('Quotation#', '')) or
                search in str(r.get('Model', '')).lower() or
                search in (r.get('Notes') or '').lower()):
                filtered.append(r)
        all_rows = filtered

    # ترتيب تصاعدي حسب رقم العرض
    all_rows.sort(key=lambda x: x.get('Quotation#') or 0, reverse=False)

    total = len(all_rows)
    total_pages = (total + per_page - 1) // per_page

    start = (page - 1) * per_page
    end = start + per_page
    page_rows = all_rows[start:end]

    rows = []
    for r in page_rows:
        client_code = r.get('Client Code') or ''
        client = clients_dict.get(str(client_code))

        # استخدام اسم العميل من العرض أو من جدول العملاء
        client_name = r.get('Client Name') or ''
        if not client_name and client:
            client_name = client.get('Client Name', '')

        # استخدام البيانات من الـ quotation أو من جدول العملاء
        company = r.get('Company') or (client.get('Company', '') if client else '')
        phone = r.get('Phone') or (client.get('Phone', '') if client else '')
        country = r.get('Country') or (client.get('Country', '') if client else '')
        address = r.get('Address') or (client.get('Address', '') if client else '')
        email = r.get('Email') or (client.get('Email', '') if client else '')
        sales_rep = r.get('Sales Rep') or (client.get('Sales Rep', '') if client else '')
        source = r.get('Source') or (client.get('Source', '') if client else '')

        row_data = {
            "Client Code": client_code,
            "Quotation#": r["Quotation#"],
            "Date": r["Date"].isoformat() if r.get("Date") else "",
            "Client Name": client_name,
            "Company": company,
            "Phone": phone,
            "Country": country,
            "Address": address,
            "Email": email,
            "Sales Rep": sales_rep,
            "Source": source,
            "Given Price": r.get("Given Price", ""),
            "Agreed Price": r.get("Agreed Price", ""),
            "Notes": r.get("Notes", ""),
            "Model": r.get("Model", ""),
            "Machine type": r.get("Machine type", ""),
            "Number of colors": r.get("Number of colors", ""),
            "Machine width": r.get("Machine width", ""),
            "Material": r.get("Material", ""),
            "Winder": r.get("Winder", ""),
            "Video inspection": r.get("Video inspection", ""),
            "PLC": r.get("PLC", ""),
            "Slitter": r.get("Slitter", ""),
            "Pneumatic Unwind": r.get("Pneumatic Unwind", ""),
            "Hydraulic Station Unwind": r.get("Hydraulic Station Unwind", ""),
            "Pneumatic Rewind": r.get("Pneumatic Rewind", ""),
            "Surface Rewind": r.get("Surface Rewind", ""),
            "Standard Machine FOB cost": r.get("Standard Machine FOB cost", ""),
            "Machine FOB cost With Cylinders": r.get("Machine FOB cost With Cylinders", ""),
            "FOB price for over seas clients": r.get("FOB price for over seas clients", ""),
            "Exchange Rate": r.get("Exchange Rate", ""),
            "In Stock": r.get("In Stock", ""),
            "New Order": r.get("New Order", ""),
            "Pricing Mode": r.get("Pricing Mode", ""),
            "Overseas clients": r.get("Overseas clients", ""),
            "Contract": r.get("Contract", ""),
            "Expected delivery time": r["Expected delivery time"].isoformat() if r.get("Expected delivery time") else "",
            "is_deleted": r.get("is_deleted", False)
        }

        for i in range(1, 13):
            row_data[f"Size in CM{i}"] = r.get(f"Size in CM{i}", "")
            row_data[f"Count{i}"] = r.get(f"Count{i}", "")
            row_data[f"Cost{i}"] = r.get(f"Cost{i}", "")

        rows.append(row_data)

    return {
        "data": rows,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages
    }


@anvil.server.callable
def get_all_clients(page=1, per_page=20, search='', include_deleted=False, token_or_email=None):
    """الحصول على العملاء مع الترقيم والبحث"""
    is_valid, _, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return {"data": [], "page": 1, "per_page": per_page, "total": 0, "total_pages": 0}

    all_rows = list(app_tables.clients.search())

    # تصفية المحذوف
    if not include_deleted:
        all_rows = [r for r in all_rows if not r.get('is_deleted', False)]

    # فلتر البحث
    if search:
        search = search.lower()
        all_rows = [r for r in all_rows if (
            search in (r['Client Name'] or '').lower() or
            search in (r['Company'] or '').lower() or
            search in (r['Phone'] or '').lower() or
            search in str(r['Client Code']).lower()
        )]

    # ترتيب حسب رمز العميل (تنازلي)
    all_rows.sort(key=lambda x: int(x['Client Code']) if str(x['Client Code']).isdigit() else 0, reverse=True)

    total = len(all_rows)
    total_pages = (total + per_page - 1) // per_page

    start = (page - 1) * per_page
    end = start + per_page
    page_rows = all_rows[start:end]

    rows = []
    for r in page_rows:
        rows.append({
            "Client Code": r["Client Code"],
            "Client Name": r["Client Name"],
            "Company": r["Company"],
            "Phone": r["Phone"],
            "Country": r["Country"],
            "Address": r["Address"],
            "Email": r["Email"],
            "Sales Rep": r["Sales Rep"],
            "Source": r["Source"],
            "Date": r.get("Date").isoformat() if r.get("Date") and hasattr(r.get("Date"), 'isoformat') else str(r.get("Date") or ""),
            "is_deleted": r.get("is_deleted", False)
        })

    return {
        "data": rows,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages
    }


# =========================================================
# دوال التصدير
# =========================================================
@anvil.server.callable
def export_clients_data(include_deleted=False, token_or_email=None):
    """تصدير جميع بيانات العملاء لـ CSV/Excel - يتطلب صلاحية export"""
    is_valid, _, error = _require_permission(token_or_email, 'export')
    if not is_valid:
        return []

    all_rows = list(app_tables.clients.search())

    if not include_deleted:
        all_rows = [r for r in all_rows if not r.get('is_deleted', False)]

    data = []
    for r in all_rows:
        data.append({
            "Client Code": r["Client Code"],
            "Client Name": r["Client Name"],
            "Company": r["Company"],
            "Phone": r["Phone"],
            "Country": r["Country"],
            "Address": r["Address"],
            "Email": r["Email"],
            "Sales Rep": r["Sales Rep"],
            "Source": r["Source"],
            "Date": str(r["Date"] or "")
        })

    return data


@anvil.server.callable
def export_quotations_data(include_deleted=False, token_or_email=None):
    """تصدير جميع بيانات العروض لـ CSV/Excel - محسّن - يتطلب صلاحية export"""
    is_valid, _, error = _require_permission(token_or_email, 'export')
    if not is_valid:
        return []

    all_rows = list(app_tables.quotations.search())

    if not include_deleted:
        all_rows = [r for r in all_rows if not r.get('is_deleted', False)]

    # جلب جميع العملاء مرة واحدة
    all_clients = list(app_tables.clients.search())
    clients_dict = {str(c['Client Code']): c for c in all_clients}

    data = []
    for r in all_rows:
        client_code = str(r.get('Client Code', ''))
        client = clients_dict.get(client_code)

        # استخدام اسم العميل من العرض أو من جدول العملاء
        client_name = r.get('Client Name') or ''
        if not client_name and client:
            client_name = client.get('Client Name', '')

        row_data = {
            "Quotation#": r["Quotation#"],
            "Date": str(r["Date"] or ""),
            "Client Code": client_code,
            "Client Name": client_name,
            "Company": (client.get("Company") or "") if client else "",
            "Phone": (client.get("Phone") or "") if client else "",
            "Model": r["Model"],
            "Machine type": r["Machine type"],
            "Number of colors": r["Number of colors"],
            "Machine width": r["Machine width"],
            "Material": r["Material"],
            "Winder": r["Winder"],
            "Given Price": r["Given Price"],
            "Agreed Price": r["Agreed Price"],
            "In Stock": r["In Stock"],
            "New Order": r["New Order"],
            "Notes": r["Notes"]
        }
        data.append(row_data)

    return data


# =========================================================
# إحصائيات لوحة التحكم
# =========================================================
@anvil.server.callable
def get_dashboard_stats(token_or_email=None):
    """الحصول على إحصائيات لوحة التحكم - يتطلب صلاحية view"""
    is_valid, _, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return {"total_clients": 0, "total_quotations": 0, "total_value": 0,
                "this_month_quotations": 0, "this_month_value": 0,
                "deleted_clients": 0, "deleted_quotations": 0}

    clients = list(app_tables.clients.search())
    quotations = list(app_tables.quotations.search())

    active_clients = [c for c in clients if not c.get('is_deleted', False)]
    active_quotations = [q for q in quotations if not q.get('is_deleted', False)]

    total_agreed = sum(q['Agreed Price'] or 0 for q in active_quotations)

    # هذا الشهر
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    this_month_quotations = [
        q for q in active_quotations
        if q['Date'] and q['Date'] >= month_start.date()
    ]

    this_month_value = sum(q['Agreed Price'] or 0 for q in this_month_quotations)

    return {
        "total_clients": len(active_clients),
        "total_quotations": len(active_quotations),
        "total_value": total_agreed,
        "this_month_quotations": len(this_month_quotations),
        "this_month_value": this_month_value,
        "deleted_clients": len(clients) - len(active_clients),
        "deleted_quotations": len(quotations) - len(active_quotations)
    }


# =========================================================
# دوال استيراد البيانات (للأدمن فقط)
# =========================================================
def _normalize_client_row(row):
    """تحويل الصف لاستخدام أسماء أعمدة موحدة للعملاء"""
    mapping = {
        'Client Name :': 'Client Name',
        'Company:': 'Company',
        'Country :': 'Country',
        'Adress :': 'Address',
        'Email :': 'Email',
        'Sales Rep :': 'Sales Rep',
        'Source :': 'Source',
    }
    normalized = {}
    for key, value in row.items():
        new_key = mapping.get(key, key.strip())
        normalized[new_key] = value
    return normalized


@anvil.server.callable
def import_csv(file, token_or_email=None):
    """
    استيراد عملاء من ملف CSV واحد.
    يتطلب صلاحية أدمن (مرّر التوكن أو الإيميل من الجلسة).
    الملف: عمود أول سطر = عناوين، باقي الأسطر = بيانات.
    """
    if not token_or_email:
        return {'success': False, 'msg': 'يجب تسجيل الدخول كأدمن لاستيراد CSV'}

    # حد أقصى لحجم الملف: 10 ميجابايت
    MAX_CSV_SIZE = 10 * 1024 * 1024  # 10MB
    try:
        raw = file.get_bytes()
        if len(raw) > MAX_CSV_SIZE:
            return {'success': False, 'msg': f'حجم الملف ({len(raw) // (1024*1024)}MB) يتجاوز الحد الأقصى (10MB)'}
        text = raw.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        data_list = [dict(row) for row in reader]
    except Exception as e:
        logger.exception("import_csv parse: %s", e)
        return {'success': False, 'msg': f'خطأ في قراءة الملف: {e}'}
    if not data_list:
        return {'success': False, 'msg': 'الملف لا يحتوي على صفوف'}
    result = import_clients_data(data_list, token_or_email)
    if isinstance(result, dict) and 'success' in result and result.get('success'):
        msg = result.get('message', result.get('msg', 'تم الاستيراد'))
        return {'success': True, 'msg': msg, 'skipped_values': result.get('errors', [])}
    return {'success': False, 'msg': result.get('message', result.get('msg', 'فشل الاستيراد')) if isinstance(result, dict) else str(result)}


@anvil.server.callable
def import_clients_data(data_list, token_or_email):
    """
    استيراد بيانات العملاء من CSV/Excel
    يتطلب صلاحية الأدمن
    يستورد كل الأعمدة الموجودة ديناميكياً
    """
    # التحقق من صلاحية الأدمن باستخدام require_admin الموحدة
    is_authorized, error = AuthManager.require_admin(token_or_email)
    if not is_authorized:
        return error

    ip_address = get_client_ip()
    user_email = token_or_email if '@' in str(token_or_email) else 'admin'

    imported = 0
    errors = []

    # الحصول على أسماء الأعمدة الموجودة في جدول clients
    try:
        table_columns = [col.name for col in app_tables.clients.list_columns()]
    except (AttributeError, TypeError):
        table_columns = []

    for i, original_row in enumerate(data_list):
        try:
            # تحويل أسماء الأعمدة
            row = _normalize_client_row(original_row)

            client_code = row.get('Client Code')
            if not client_code:
                client_code = str(_get_next_number('clients', 'Client Code'))

            # التحقق من عدم وجود العميل
            existing = app_tables.clients.get(**{"Client Code": str(client_code)})
            if existing:
                errors.append(f"Row {i+1}: Client Code {client_code} already exists")
                continue

            # التحقق من الهاتف
            phone = safe_strip(row.get('Phone'))
            if phone:
                phone_exists_row = app_tables.clients.get(Phone=phone, is_deleted=False)
                if phone_exists_row:
                    errors.append(f"Row {i+1}: Phone {phone} already exists")
                    continue

            # بناء البيانات ديناميكياً
            data = {
                'Client Code': str(client_code),
                'Date': datetime.now().date(),
                'is_deleted': False,
                'created_by': user_email,
                'created_at': datetime.now(),
                'updated_by': user_email,
                'updated_at': datetime.now()
            }

            # إضافة كل الأعمدة الموجودة في الـ CSV
            for col_name, col_value in row.items():
                # تخطي الأعمدة الخاصة
                if col_name in ['Client Code', 'Date', 'is_deleted', 'created_by', 'created_at', 'updated_by', 'updated_at']:
                    continue

                # التحقق من وجود العمود في الجدول
                if table_columns and col_name not in table_columns:
                    continue  # تخطي الأعمدة غير الموجودة في الجدول

                # تنظيف القيمة
                data[col_name] = safe_strip(col_value)

            app_tables.clients.add_row(**data)
            imported += 1

        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")

    log_audit('IMPORT', 'clients', None, None,
              {'imported': imported, 'errors': len(errors)}, user_email, ip_address)

    return {
        'success': True,
        'message': f'Imported {imported} clients',
        'imported': imported,
        'errors': errors
    }


def _clean_price(value):
    """تنظيف قيمة السعر من العملة والفواصل - ترجع 0 بدلاً من None"""
    if not value or value == '-' or value == 'FREE' or str(value).strip() == '':
        return 0.0  # Anvil number columns don't accept None
    value = str(value)
    # إزالة العملة والمسافات والرموز
    value = value.replace('ج.م.', '').replace('\u200f', '').replace('$', '').replace(' ', '')
    value = value.replace('‏', '')  # Remove RTL mark
    # إزالة الفواصل كفاصل آلاف
    value = value.replace(',', '')
    # محاولة التحويل
    try:
        result = float(value) if value.strip() else 0.0
        return result
    except (ValueError, TypeError):
        return 0.0


def _map_column_name(key):
    """تحويل أسماء الأعمدة القديمة للجديدة"""
    mapping = {
        'Quotation #': 'Quotation#',
        'Date :': 'Date',
        'Client Name :': 'Client Name',
        'Company:': 'Company',
        'Country :': 'Country',
        'Adress :': 'Address',
        'Email :': 'Email',
        'Sales Rep :': 'Sales Rep',
        'Source :': 'Source',
        'Given Price :': 'Given Price',
        'Agreed Price ': 'Agreed Price',
        'Modle  :': 'Model',
        'machine type': 'Machine type',
        'Standard Machine FOB cost': 'Standard Machine FOB cost',
        ' Machine FOB cost With Cylinders': 'Machine FOB cost With Cylinders',
        'FOB price for over seas clients': 'FOB price for over seas clients',
        ' In Stock ': 'In Stock',
        ' New Order ': 'New Order',
        'Haydrolic Staion Unwind': 'Hydraulic Station Unwind',
        'over seas clients': 'Overseas Client',
        # Cylinder columns (first one has no number)
        'Size in CM': 'Size in CM1',
        'Count': 'Count1',
        ' Cost ': 'Cost1',
    }
    return mapping.get(key, key.strip())


def _normalize_row(row):
    """تحويل الصف لاستخدام أسماء أعمدة موحدة"""
    normalized = {}
    for key, value in row.items():
        new_key = _map_column_name(key)
        normalized[new_key] = value
    return normalized


def _is_price_column(col_name):
    """التحقق إذا كان العمود يحتوي على سعر (رقم)"""
    # هذه الأعمدة تُخزن كنص في الجدول وليس كرقم
    text_columns = [
        'Standard Machine FOB cost',
        'Machine FOB cost With Cylinders',
    ]
    if col_name in text_columns:
        return False

    # أعمدة الـ Cost للأسطوانات أيضاً تُخزن كنص
    if col_name.startswith('Cost') and any(c.isdigit() for c in col_name):
        return False

    col_lower = col_name.lower()
    price_keywords = ['price', 'stock', 'order', 'rate', 'exchange']
    return any(keyword in col_lower for keyword in price_keywords)


@anvil.server.callable
def import_quotations_data(data_list, token_or_email):
    """
    استيراد بيانات العروض من CSV/Excel
    يتطلب صلاحية الأدمن
    يستورد كل الأعمدة الموجودة ديناميكياً
    """
    # التحقق من صلاحية الأدمن باستخدام require_admin الموحدة
    is_authorized, error = AuthManager.require_admin(token_or_email)
    if not is_authorized:
        return error

    ip_address = get_client_ip()
    user_email = token_or_email if '@' in str(token_or_email) else 'admin'

    imported = 0
    errors = []

    # الحصول على أسماء الأعمدة الموجودة في جدول quotations
    try:
        table_columns = [col.name for col in app_tables.quotations.list_columns()]
    except (AttributeError, TypeError):
        table_columns = []

    for i, original_row in enumerate(data_list):
        try:
            # تحويل أسماء الأعمدة
            row = _normalize_row(original_row)

            quotation_number = safe_int(row.get('Quotation#'))
            if not quotation_number:
                quotation_number = _get_next_number('quotations', 'Quotation#')

            # التحقق من عدم وجود العرض
            existing = app_tables.quotations.get(**{"Quotation#": int(quotation_number)})
            if existing:
                errors.append(f"Row {i+1}: Quotation# {quotation_number} already exists")
                continue

            # بناء البيانات ديناميكياً - استيراد كل الأعمدة
            data = {
                'Quotation#': int(quotation_number),
                'is_deleted': False,
                'created_by': user_email,
                'created_at': datetime.now(),
                'updated_by': user_email,
                'updated_at': datetime.now()
            }

            # إضافة كل الأعمدة الموجودة في الـ CSV
            for col_name, col_value in row.items():
                # تخطي الأعمدة الخاصة
                if col_name in ['Quotation#', 'is_deleted', 'created_by', 'created_at', 'updated_by', 'updated_at']:
                    continue

                # التحقق من وجود العمود في الجدول
                if table_columns and col_name not in table_columns:
                    continue  # تخطي الأعمدة غير الموجودة في الجدول

                # تنظيف القيمة حسب نوعها
                if _is_price_column(col_name):
                    # تنظيف الأسعار - دائماً رقم (0 للقيم الفارغة)
                    cleaned_value = _clean_price(col_value)
                    if cleaned_value is not None:
                        data[col_name] = float(cleaned_value)
                    else:
                        data[col_name] = 0.0
                elif col_name == 'Number of colors' or col_name == 'Machine width':
                    # الأرقام الصحيحة
                    int_val = safe_int(col_value)
                    if int_val is not None:
                        data[col_name] = int_val
                elif col_name == 'Date' or col_name == 'Expected delivery time':
                    # تحويل التاريخ من النص
                    if col_value and str(col_value).strip():
                        try:
                            # محاولة تحويل من تنسيق DD-MM-YYYY
                            date_str = str(col_value).strip()
                            if '-' in date_str:
                                parts = date_str.split('-')
                                if len(parts) == 3:
                                    if len(parts[2]) == 4:  # DD-MM-YYYY
                                        data[col_name] = datetime.strptime(date_str, '%d-%m-%Y').date()
                                    else:  # YYYY-MM-DD
                                        data[col_name] = datetime.strptime(date_str, '%Y-%m-%d').date()
                                else:
                                    # تاريخ غير صالح - استخدم None للـ Expected delivery time
                                    if col_name == 'Expected delivery time':
                                        data[col_name] = None
                                    else:
                                        data[col_name] = datetime.now().date()
                            else:
                                if col_name == 'Expected delivery time':
                                    data[col_name] = None
                                else:
                                    data[col_name] = datetime.now().date()
                        except (ValueError, TypeError):
                            if col_name == 'Expected delivery time':
                                data[col_name] = None
                            else:
                                data[col_name] = datetime.now().date()
                    else:
                        # القيمة فارغة
                        if col_name == 'Expected delivery time':
                            data[col_name] = None  # يمكن أن يكون فارغاً
                        else:
                            data[col_name] = datetime.now().date()
                else:
                    # النصوص العادية
                    data[col_name] = safe_strip(col_value)

            app_tables.quotations.add_row(**data)
            imported += 1

        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")

    log_audit('IMPORT', 'quotations', None, None,
              {'imported': imported, 'errors': len(errors)}, user_email, ip_address)

    return {
        'success': True,
        'message': f'Imported {imported} quotations',
        'imported': imported,
        'errors': errors
    }


# =========================================================
# PDF Export Functions
# =========================================================

def get_setting_value(key, default=None):
    """جلب قيمة إعداد من جدول settings"""
    try:
        setting = app_tables.settings.get(setting_key=key)
        if setting:
            return setting['setting_value']
        return default
    except Exception:
        return default


def get_user_info(email):
    """جلب معلومات المستخدم (الاسم ورقم الهاتف)"""
    try:
        user = app_tables.users.get(email=email)
        if user:
            return {
                'name': user['full_name'] or 'N/A',
                'phone': user['phone'] or 'N/A',
                'email': user['email'] or 'N/A'
            }
        return {'name': 'N/A', 'phone': 'N/A', 'email': 'N/A'}
    except Exception:
        return {'name': 'N/A', 'phone': 'N/A', 'email': 'N/A'}


def get_user_info_by_name(full_name):
    """جلب معلومات المستخدم بناءً على الاسم الكامل (للـ Sales Rep). يستخدم search لأن full_name قد لا يكون فريداً."""
    try:
        if not full_name or not str(full_name).strip():
            return {'name': 'N/A', 'phone': 'N/A', 'email': 'N/A'}
        name = str(full_name).strip()
        rows = list(app_tables.users.search(full_name=name))
        user = rows[0] if rows else None
        if user:
            return {
                'name': user.get('full_name') or 'N/A',
                'phone': user.get('phone') or 'N/A',
                'email': user.get('email') or 'N/A'
            }
        return {'name': name, 'phone': 'N/A', 'email': 'N/A'}
    except Exception as e:
        logger.debug(f"get_user_info_by_name({full_name}): {e}")
        return {'name': (full_name or 'N/A'), 'phone': 'N/A', 'email': 'N/A'}


def get_machine_specs(model):
    """جلب المواصفات الفنية للماكينة حسب الموديل"""
    try:
        specs = app_tables.machine_specs.get(model=model)
        if specs:
            return dict(specs)
        return None
    except Exception:
        return None


def format_number(num):
    """تنسيق الأرقام بالفواصل"""
    try:
        if num is None:
            return "0"
        return "{:,.0f}".format(float(num))
    except (ValueError, TypeError):
        return str(num)


def format_date_ar(date_obj):
    """تنسيق التاريخ بالعربي"""
    if not date_obj:
        return ""
    months_ar = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
                 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
    try:
        return f"{date_obj.day} {months_ar[date_obj.month - 1]}"
    except (AttributeError, IndexError):
        return str(date_obj)


def format_date_en(date_obj):
    """تنسيق التاريخ بالإنجليزي"""
    if not date_obj:
        return ""
    months_en = ['January', 'February', 'March', 'April', 'May', 'June',
                 'July', 'August', 'September', 'October', 'November', 'December']
    try:
        return f"{date_obj.day} {months_en[date_obj.month - 1]}"
    except (AttributeError, IndexError):
        return str(date_obj)


@anvil.server.callable
def get_quotation_pdf_data(quotation_number, user_email, auth_token=None):
    """
    جلب كل البيانات اللازمة لتصدير عرض السعر كـ PDF.
    يتطلب auth_token صالح ومطابق للبريد.
    """
    # التحقق من التوكن إلزامي
    if not auth_token:
        return {'success': False, 'message': 'Authentication required'}
    try:
        result = AuthManager.validate_token(auth_token)
        if not result.get('valid') or (result.get('user', {}).get('email') or '').strip().lower() != (user_email or '').strip().lower():
            return {'success': False, 'message': 'Unauthorized'}
    except Exception as e:
        logger.warning(f"get_quotation_pdf_data auth check: {e}")
        return {'success': False, 'message': 'Unauthorized'}
    try:
        # جلب بيانات عرض السعر
        quotation = app_tables.quotations.get(**{'Quotation#': quotation_number})
        if not quotation:
            return {'success': False, 'message': 'Quotation not found'}

        q_data = dict(quotation)

        # جلب معلومات المستخدم اللي سجل الدخول (للرجوع)
        user_info = get_user_info(user_email)
        
        # جلب معلومات السيلز ريب من الكوتيشن (للهيدر)
        sales_rep_name = q_data.get('Sales Rep', '').strip()
        if sales_rep_name:
            sales_rep_info = get_user_info_by_name(sales_rep_name)
        else:
            sales_rep_info = user_info  # fallback to logged-in user

        # جلب إعدادات الشركة
        company_settings = {
            'company_name_ar': get_setting_value('company_name_ar', 'شركة حلوان بلاست ذ.م.م'),
            'company_name_en': get_setting_value('company_name_en', 'Helwan Plast LLC'),
            'company_address_ar': get_setting_value('company_address_ar', 'المنطقة الصناعية الثانية - قطعة ٢٠'),
            'company_address_en': get_setting_value('company_address_en', 'Second Industrial Zone – Plot 20'),
            'company_email': get_setting_value('company_email', 'sales@helwanplast.com'),
            'company_website': get_setting_value('company_website', 'www.helwanplast.com'),
            'quotation_location_ar': get_setting_value('quotation_location_ar', 'القاهرة'),
            'quotation_location_en': get_setting_value('quotation_location_en', 'Cairo'),
            'warranty_months': get_setting_value('warranty_months', '12'),
            'validity_days': get_setting_value('validity_days', '15'),
            'down_payment_percent': get_setting_value('down_payment_percent', '40'),
            'before_shipping_percent': get_setting_value('before_shipping_percent', '30'),
            'before_delivery_percent': get_setting_value('before_delivery_percent', '30'),
            'country_origin_ar': get_setting_value('country_origin_ar', 'الصين'),
            'country_origin_en': get_setting_value('country_origin_en', 'China'),
            'anilox_type_ar': get_setting_value('anilox_type_ar', 'انيلوكس سيراميك'),
            'anilox_type_en': get_setting_value('anilox_type_en', 'Ceramic anilox'),
            'belt_max_machine_speed': get_setting_value('belt_max_machine_speed', 120),
            'belt_max_print_speed': get_setting_value('belt_max_print_speed', 120),
            'belt_print_length': get_setting_value('belt_print_length', '300mm - 1300mm'),
            'gear_max_machine_speed': get_setting_value('gear_max_machine_speed', 100),
            'gear_max_print_speed': get_setting_value('gear_max_print_speed', 80),
            'gear_print_length': get_setting_value('gear_print_length', '240mm - 1000mm'),
            'single_winder_roll_dia': get_setting_value('single_winder_roll_dia', 1200),
            'double_winder_roll_dia': get_setting_value('double_winder_roll_dia', 800),
            'dryer_capacity': get_setting_value('dryer_capacity', '2.2kw air blower × 2 units'),
            'main_motor_power': get_setting_value('main_motor_power', '5 HP'),
        }

        # جلب إعدادات جدول المواصفات الفنية
        tech_specs_raw = get_setting_value('technical_specs', '{}')
        try:
            tech_specs_settings = json.loads(tech_specs_raw) if isinstance(tech_specs_raw, str) else tech_specs_raw
        except Exception:
            tech_specs_settings = {}

        # جلب المواصفات الفنية للماكينة
        model = q_data.get('Model', '')
        machine_specs = get_machine_specs(model)

        # تجهيز السلندرات
        cylinders = []
        for i in range(1, 13):
            size = q_data.get(f'Size in CM{i}')
            count = q_data.get(f'Count{i}')
            if size and count:
                cylinders.append({'size': size, 'count': count})

        # حساب المبالغ المالية
        total_price = float(q_data.get('Agreed Price') or 0)
        down_percent = float(company_settings['down_payment_percent'])
        shipping_percent = float(company_settings['before_shipping_percent'])
        delivery_percent = float(company_settings['before_delivery_percent'])

        down_amount = total_price * (down_percent / 100)
        shipping_amount = total_price * (shipping_percent / 100)
        delivery_amount = total_price * (delivery_percent / 100)

        # تجهيز البيانات النهائية
        pdf_data = {
            # معلومات المستخدم اللي سجل الدخول
            'user_name': user_info['name'],
            'user_phone': user_info['phone'],
            
            # معلومات السيلز ريب (للهيدر)
            'sales_rep_name': sales_rep_info['name'],
            'sales_rep_phone': sales_rep_info['phone'],
            'sales_rep_email': sales_rep_info['email'],

            # معلومات الشركة
            'company': company_settings,

            # معلومات عرض السعر
            'quotation_number': q_data.get('Quotation#', ''),
            'quotation_date': q_data.get('Date'),
            'quotation_date_ar': format_date_ar(q_data.get('Date')),
            'quotation_date_en': format_date_en(q_data.get('Date')),

            # معلومات العميل
            'client_name': q_data.get('Client Name', ''),
            'client_company': q_data.get('Company', ''),
            'client_phone': q_data.get('Phone', ''),
            'client_address': q_data.get('Address', ''),

            # معلومات الماكينة
            'model': model,
            'machine_type': q_data.get('Machine type', ''),
            'colors_count': q_data.get('Number of colors', ''),
            'machine_width': q_data.get('Machine width', ''),
            'winder': q_data.get('Winder', ''),
            'material': q_data.get('Material', ''),
            'video_inspection': q_data.get('Video inspection', 'NO'),
            'plc': q_data.get('PLC', 'NO'),
            'slitter': q_data.get('Slitter', 'NO'),

            # Unwind/Rewind options
            'pneumatic_unwind': q_data.get('Pneumatic Unwind', 'NO'),
            'hydraulic_station_unwind': q_data.get('Hydraulic Station Unwind', 'NO'),
            'pneumatic_rewind': q_data.get('Pneumatic Rewind', 'NO'),
            'surface_rewind': q_data.get('Surface Rewind', 'NO'),

            # المواصفات الفنية
            'machine_specs': machine_specs,

            # السلندرات
            'cylinders': cylinders,

            # المعلومات المالية
            'total_price': format_number(total_price),
            'total_price_raw': total_price,
            'pricing_mode': q_data.get('Pricing Mode', ''),
            'down_payment_percent': down_percent,
            'down_payment_amount': format_number(down_amount),
            'before_shipping_percent': shipping_percent,
            'before_shipping_amount': format_number(shipping_amount),
            'before_delivery_percent': delivery_percent,
            'before_delivery_amount': format_number(delivery_amount),

            # التسليم
            'delivery_location': q_data.get('Address', ''),
            'expected_delivery': q_data.get('Expected delivery time'),
            'expected_delivery_formatted': str(q_data.get('Expected delivery time') or ''),

            # إعدادات جدول المواصفات الفنية
            'tech_specs_settings': tech_specs_settings,
        }

        return {'success': True, 'data': pdf_data}

    except Exception as e:
        logger.error(f"Error getting quotation PDF data: {e}")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_all_template_settings(token_or_email=None):
    """جلب كل إعدادات القالب - يتطلب مستخدم مسجل"""
    is_valid, _, error = _require_authenticated(token_or_email)
    if not is_valid:
        return {'success': False, 'message': 'Authentication required', 'settings': {}}
    try:
        settings = {}
        for row in app_tables.settings.search():
            settings[row['setting_key']] = row['setting_value']
        return {'success': True, 'settings': settings}
    except Exception as e:
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def save_machine_specs(specs_data, token_or_email=None):
    """حفظ المواصفات الفنية للماكينة (يتطلب صلاحية أدمن). مرّر token_or_email من العميل."""
    if not token_or_email:
        return {'success': False, 'message': 'Authentication required'}
    is_authorized, error = AuthManager.require_admin(token_or_email)
    if not is_authorized:
        return error if isinstance(error, dict) else {'success': False, 'message': 'Permission denied'}
    try:
        model = specs_data.get('model')
        if not model:
            return {'success': False, 'message': 'Model is required'}

        existing = app_tables.machine_specs.get(model=model)
        if existing:
            existing.update(**specs_data)
        else:
            app_tables.machine_specs.add_row(**specs_data)

        return {'success': True, 'message': 'Machine specs saved'}
    except Exception as e:
        logger.exception("save_machine_specs error")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_all_machine_specs(token_or_email=None):
    """جلب كل المواصفات الفنية - يتطلب مستخدم مسجل"""
    is_valid, _, error = _require_authenticated(token_or_email)
    if not is_valid:
        return {'success': False, 'message': 'Authentication required', 'specs': []}
    try:
        specs = []
        for row in app_tables.machine_specs.search():
            specs.append(dict(row))
        return {'success': True, 'specs': specs}
    except Exception as e:
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def export_quotation_excel(quotation_number, token_or_email=None):
    """Export quotation data as Excel file with full formatting - يتطلب صلاحية export"""
    is_valid, _, error = _require_permission(token_or_email, 'export')
    if not is_valid:
        return {'success': False, 'message': 'Permission denied: export access required'}
    try:
        import io
        import xlsxwriter

        # Get quotation data
        q_data = app_tables.quotations.get(**{'Quotation#': int(quotation_number)})
        if not q_data:
            return {'success': False, 'message': 'Quotation not found'}

        # Get company settings
        def get_setting(key, default=''):
            try:
                setting = app_tables.settings.get(setting_key=key)
                return setting['setting_value'] if setting else default
            except Exception:
                return default

        # Helper function to safely get field value
        def get_field(field_name, default=''):
            try:
                val = q_data[field_name]
                return str(val) if val is not None else default
            except Exception:
                return default

        def is_yes(field_name):
            val = str(get_field(field_name, '')).upper()
            return val in ['YES', 'TRUE', '1', 'نعم']

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        # Create worksheet
        worksheet = workbook.add_worksheet('Quotation')
        
        # Formats
        title_fmt = workbook.add_format({
            'bold': True, 'font_size': 16, 'align': 'center', 'valign': 'vcenter',
            'font_color': '#1565c0', 'bottom': 2
        })
        header_fmt = workbook.add_format({
            'bold': True, 'font_size': 12, 'bg_color': '#1565c0', 'font_color': 'white',
            'align': 'center', 'valign': 'vcenter', 'border': 1
        })
        section_fmt = workbook.add_format({
            'bold': True, 'font_size': 11, 'bg_color': '#e3f2fd', 'font_color': '#1565c0',
            'align': 'right', 'valign': 'vcenter', 'border': 1
        })
        label_fmt = workbook.add_format({
            'bold': True, 'font_size': 10, 'bg_color': '#f5f5f5',
            'align': 'right', 'valign': 'vcenter', 'border': 1
        })
        value_fmt = workbook.add_format({
            'font_size': 10, 'align': 'center', 'valign': 'vcenter', 'border': 1
        })
        price_fmt = workbook.add_format({
            'font_size': 12, 'bold': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'num_format': '#,##0', 'font_color': '#2e7d32'
        })
        cyl_header_fmt = workbook.add_format({
            'bold': True, 'font_size': 10, 'bg_color': '#fff3e0',
            'align': 'center', 'valign': 'vcenter', 'border': 1
        })

        # Set column widths
        worksheet.set_column(0, 0, 5)   # #
        worksheet.set_column(1, 1, 35)  # Label
        worksheet.set_column(2, 2, 30)  # Value
        worksheet.set_column(3, 3, 15)  # Extra
        worksheet.set_column(4, 4, 15)  # Extra

        row = 0
        
        # === HEADER ===
        company_name = get_setting('company_name_en', 'Helwan Plast')
        worksheet.merge_range(row, 0, row, 4, company_name, title_fmt)
        row += 1
        worksheet.merge_range(row, 0, row, 4, f"Quotation #{quotation_number}", header_fmt)
        row += 2

        # === CLIENT INFO ===
        worksheet.merge_range(row, 0, row, 4, "Client Information", section_fmt)
        row += 1
        
        client_info = [
            ('Client Name', get_field('Client Name', '')),
            ('Company', get_field('Company', '')),
            ('Phone', get_field('Phone', '')),
            ('Country', get_field('Country', '')),
            ('Date', str(get_field('Date', ''))),
        ]
        for label, value in client_info:
            if value and value != 'None':
                worksheet.write(row, 1, label, label_fmt)
                worksheet.write(row, 2, value, value_fmt)
                row += 1
        row += 1

        # === MACHINE DETAILS ===
        worksheet.merge_range(row, 0, row, 4, "Machine Details", section_fmt)
        row += 1
        
        machine_details = [
            ('Model', get_field('Model', '')),
            ('Machine Type', get_field('Machine type', '')),
            ('Number of Colors', get_field('Number of colors', '')),
            ('Machine Width', f"{get_field('Machine width', '')} cm"),
            ('Winder', get_field('Winder', '')),
            ('Material', get_field('Material', '')),
        ]
        for label, value in machine_details:
            if value and value != 'None' and value != ' cm':
                worksheet.write(row, 1, label, label_fmt)
                worksheet.write(row, 2, value, value_fmt)
                row += 1
        row += 1

        # === TECHNICAL SPECS ===
        worksheet.merge_range(row, 0, row, 4, "Technical Specifications", section_fmt)
        row += 1
        
        # Calculate specs values
        winder = str(get_field('Winder', '')).upper()
        is_double = 'DOUBLE' in winder
        model = str(get_field('Model', '')).upper()
        is_belt = 'METAL' not in model
        machine_width = float(get_field('Machine width', 0) or 0)
        colors = get_field('Number of colors', '')
        
        specs = [
            ('Printing Sides', '2'),
            ('Tension Control Units', '4' if is_double else '2'),
            ('Brake System', '4' if is_double else '2'),
            ('Brake Power', '2' if is_double else '1'),
            ('Web Guiding System', '2' if is_double else '1'),
            ('Maximum Film Width', f"{int(machine_width * 10 + 50)} mm" if machine_width else ''),
            ('Maximum Printing Width', f"{int(machine_width * 10 - 40)} mm" if machine_width else ''),
            ('Print Length Range', '300mm-1300mm' if is_belt else '240mm-1000mm'),
            ('Maximum Roll Diameter', '800 mm' if is_double else '1200 mm'),
            ('Anilox Type', 'Ceramic Anilox' if is_belt else 'Metal Anilox'),
            ('Maximum Machine Speed', '120 m/min' if is_belt else '100 m/min'),
            ('Maximum Printing Speed', '120 m/min' if is_belt else '80 m/min'),
            ('Power Transmission', 'Belt Drive' if is_belt else 'Gear Drive'),
            ('Main Motor Power', get_setting('main_motor_power', '5 HP')),
            ('Dryer Capacity', get_setting('dryer_capacity', '2.2kw air blower × 2 units')),
        ]
        
        # Add yes/no options only if YES
        if is_yes('Video inspection'):
            specs.append(('Video Inspection', 'Yes'))
        if is_yes('PLC'):
            specs.append(('PLC', 'Yes'))
        if is_yes('Slitter'):
            specs.append(('Slitter', 'Yes'))
        
        spec_num = 1
        for label, value in specs:
            if value and value != 'None' and str(value).upper() not in ['NO', 'لا', '']:
                worksheet.write(row, 0, spec_num, value_fmt)
                worksheet.write(row, 1, label, label_fmt)
                worksheet.write(row, 2, value, value_fmt)
                row += 1
                spec_num += 1
        row += 1

        # === CYLINDERS ===
        worksheet.merge_range(row, 0, row, 4, "Printing Cylinders", section_fmt)
        row += 1
        worksheet.write(row, 1, "Size (cm)", cyl_header_fmt)
        worksheet.write(row, 2, "Count", cyl_header_fmt)
        worksheet.write(row, 3, "Cost", cyl_header_fmt)
        row += 1
        
        for i in range(1, 13):
            size = get_field(f'Size in CM{i}', '')
            count = get_field(f'Count{i}', '')
            cost = get_field(f'Cost{i}', '')
            if size and count:
                worksheet.write(row, 1, size, value_fmt)
                worksheet.write(row, 2, count, value_fmt)
                worksheet.write(row, 3, cost, value_fmt)
                row += 1
        row += 1

        # === PRICING ===
        worksheet.merge_range(row, 0, row, 4, "Financial Offer", section_fmt)
        row += 1
        
        pricing_mode = str(get_field('Pricing Mode', '')).upper()
        
        if 'STOCK' in pricing_mode:
            in_stock = get_field('In Stock', '')
            if in_stock:
                worksheet.write(row, 1, "In Stock Price", label_fmt)
                worksheet.write(row, 2, f"{in_stock} EGP", price_fmt)
                row += 1
        else:
            new_order = get_field('New Order', '')
            if new_order:
                worksheet.write(row, 1, "New Order Price", label_fmt)
                worksheet.write(row, 2, f"{new_order} EGP", price_fmt)
                row += 1
        
        agreed = get_field('Agreed Price', '')
        if agreed and agreed != '0':
            worksheet.write(row, 1, "Agreed Price", label_fmt)
            worksheet.write(row, 2, f"{agreed} EGP", price_fmt)
            row += 1

        workbook.close()
        output.seek(0)

        client_name = get_field('Client Name', 'Client').replace(' ', '_')
        filename = f"Quotation_{quotation_number}_{client_name}.xlsx"
        media = anvil.BlobMedia(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            output.read(),
            name=filename
        )

        return {'success': True, 'file': media}

    except Exception as e:
        logger.error(f"Error exporting Excel: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_quotations_list(search='', include_deleted=False, token_or_email=None):
    """
    جلب قائمة العروض للـ dropdown - نسخة مبسطة
    تُستخدم في صفحة طباعة عروض الأسعار - يتطلب صلاحية view
    """
    is_valid, _, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return {'success': False, 'data': [], 'message': 'Permission denied'}
    try:
        all_rows = list(app_tables.quotations.search())

        # تصفية المحذوف
        if not include_deleted:
            all_rows = [r for r in all_rows if not r.get('is_deleted', False)]

        # فلتر البحث
        if search:
            search = search.lower()
            filtered = []
            for r in all_rows:
                client_name = str(r.get('Client Name', '') or '').lower()
                model = str(r.get('Model', '') or '').lower()
                q_num = str(r.get('Quotation#', '') or '').lower()

                if search in client_name or search in model or search in q_num:
                    filtered.append(r)
            all_rows = filtered

        # ترتيب تنازلي حسب رقم العرض
        all_rows.sort(key=lambda x: x.get('Quotation#') or 0, reverse=True)

        # تجهيز البيانات
        data = []
        for r in all_rows:
            data.append({
                'Quotation#': r.get('Quotation#'),
                'Client Name': r.get('Client Name', ''),
                'Model': r.get('Model', ''),
                'Date': r.get('Date').isoformat() if r.get('Date') else '',
                'Agreed Price': r.get('Agreed Price', 0)
            })

        return {'success': True, 'data': data}

    except Exception as e:
        logger.error(f"Error in get_quotations_list: {e}")
        return {'success': False, 'message': str(e), 'data': []}


# =========================================================
# Contract Management Functions
# =========================================================
# Contracts are stored in the 'contracts' table

@anvil.server.callable
def save_contract(contract_data, user_email='system', token_or_email=None):
    """
    Save contract data to contracts table - يتطلب صلاحية create
    """
    auth_key = token_or_email or user_email
    if auth_key == 'system':
        return {'success': False, 'message': 'Authentication required'}
    is_valid, verified_email, error = _require_permission(auth_key, 'create')
    if not is_valid:
        return error
    user_email = verified_email or user_email
    try:
        quotation_number = contract_data.get('quotation_number')
        if not quotation_number:
            return {'success': False, 'message': 'Quotation number is required'}
        
        contract_number = f"C-{quotation_number}"
        payments_json = json.dumps(contract_data.get('payments', []), ensure_ascii=False, default=str)
        ip_address = get_client_ip()
        
        # Try to find existing contract
        try:
            existing = app_tables.contracts.get(contract_number=contract_number)
            if existing:
                # Update existing
                old_data = {'contract_number': contract_number}
                existing.update(
                    client_name=contract_data.get('client_name', ''),
                    company=contract_data.get('company', ''),
                    phone=contract_data.get('phone', ''),
                    country=contract_data.get('country', ''),
                    address=contract_data.get('address', ''),
                    model=contract_data.get('model', ''),
                    colors_count=str(contract_data.get('colors_count', '')),
                    machine_width=str(contract_data.get('machine_width', '')),
                    material=contract_data.get('material', ''),
                    winder_type=contract_data.get('winder_type', ''),
                    price_mode=contract_data.get('price_mode', ''),
                    total_price=str(contract_data.get('total_price', '')),
                    payment_method=contract_data.get('payment_method', 'percentage'),
                    num_payments=contract_data.get('num_payments', 0),
                    payments_json=payments_json,
                    delivery_date=contract_data.get('delivery_date', ''),
                    updated_at=datetime.now()
                )
                logger.info(f"Contract {contract_number} updated by {user_email}")
                log_audit('UPDATE', 'contracts', contract_number, old_data, contract_data, user_email, ip_address)
                return {'success': True, 'message': 'Contract updated', 'contract_number': contract_number}
        except Exception as e:
            logger.warning(f"Contract lookup failed: {e}")
        
        # Create new contract
        try:
            app_tables.contracts.add_row(
                contract_number=contract_number,
                quotation_number=int(quotation_number),
                client_name=contract_data.get('client_name', ''),
                company=contract_data.get('company', ''),
                phone=contract_data.get('phone', ''),
                country=contract_data.get('country', ''),
                address=contract_data.get('address', ''),
                model=contract_data.get('model', ''),
                colors_count=str(contract_data.get('colors_count', '')),
                machine_width=str(contract_data.get('machine_width', '')),
                material=contract_data.get('material', ''),
                winder_type=contract_data.get('winder_type', ''),
                price_mode=contract_data.get('price_mode', ''),
                total_price=str(contract_data.get('total_price', '')),
                payment_method=contract_data.get('payment_method', 'percentage'),
                num_payments=contract_data.get('num_payments', 0),
                payments_json=payments_json,
                delivery_date=contract_data.get('delivery_date', ''),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
            logger.info(f"Contract {contract_number} created by {user_email}")
            log_audit('CREATE', 'contracts', contract_number, None, contract_data, user_email, ip_address)
            return {'success': True, 'message': 'Contract saved', 'contract_number': contract_number}
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error creating contract: {error_msg}")
            
            # Check if table doesn't exist
            if 'contracts' in error_msg.lower() or 'table' in error_msg.lower():
                return {
                    'success': False, 
                    'message': 'يجب إنشاء جدول contracts في Anvil Data Tables أولاً\n\nPlease create "contracts" table in Anvil with columns:\ncontract_number, quotation_number, client_name, company, phone, country, address, model, colors_count, machine_width, material, winder_type, price_mode, total_price, payment_method, num_payments, payments_json, delivery_date, created_at, updated_at'
                }
            return {'success': False, 'message': error_msg}
    
    except Exception as e:
        logger.error(f"Error saving contract: {e}")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_contract(quotation_number, token_or_email=None):
    """
    Get a single contract by quotation number - يتطلب صلاحية view
    """
    is_valid, _, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return {'success': False, 'message': 'Permission denied'}
    try:
        contract_number = f"C-{quotation_number}"
        row = app_tables.contracts.get(contract_number=contract_number)
        
        if row:
            payments = []
            try:
                payments = json.loads(row['payments_json'] or '[]')
            except Exception as e:
                pass
            
            return {'success': True, 'data': {
                'contract_number': row['contract_number'],
                'quotation_number': row['quotation_number'],
                'client_name': row['client_name'],
                'company': row['company'],
                'phone': row['phone'],
                'country': row['country'],
                'address': row['address'],
                'model': row['model'],
                'total_price': row['total_price'],
                'payment_method': row['payment_method'],
                'num_payments': row['num_payments'],
                'payments': payments,
                'delivery_date': row['delivery_date'],
                'created_at': row['created_at'].isoformat() if row['created_at'] else ''
            }}
        else:
            return {'success': False, 'message': 'Contract not found'}
    
    except Exception as e:
        logger.error(f"Error getting contract: {e}")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_contracts_list(search='', token_or_email=None):
    """
    Get list of all contracts - يتطلب صلاحية view
    """
    is_valid, _, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return {'success': False, 'data': [], 'count': 0, 'message': 'Permission denied'}
    try:
        all_rows = list(app_tables.contracts.search())
        
        # Filter by search
        if search:
            search = search.lower()
            all_rows = [r for r in all_rows 
                       if search in str(r.get('client_name', '') or '').lower()
                       or search in str(r.get('contract_number', '') or '').lower()]
        
        # Sort by created_at descending
        all_rows.sort(key=lambda x: x.get('created_at') or datetime.min, reverse=True)
        
        data = []
        for r in all_rows:
            data.append({
                'contract_number': r.get('contract_number'),
                'quotation_number': r.get('quotation_number'),
                'client_name': r.get('client_name'),
                'total_price': r.get('total_price'),
                'num_payments': r.get('num_payments'),
                'delivery_date': r.get('delivery_date'),
                'created_at': r.get('created_at').isoformat() if r.get('created_at') and hasattr(r.get('created_at'), 'isoformat') else ''
            })

        return {'success': True, 'data': data, 'count': len(data)}

    except Exception as e:
        logger.error(f"Error getting contracts list: {e}")
        return {'success': False, 'message': str(e), 'data': []}


# =========================================================
# النسخ الاحتياطي (يدوي + مجدول + Google Drive + استعادة)
# =========================================================
def _get_backup_drive_folder():
    """الحصول على مجلد النسخ الاحتياطية في Google Drive (app_files)."""
    for name in ('Backups', 'Helwan_Plast_Backups', 'backups'):
        folder = getattr(app_files, name, None)
        if folder is not None and hasattr(folder, 'create_file'):
            return folder
    return None


def _encrypt_backup(json_bytes):
    """
    تشفير النسخة الاحتياطية باستخدام AES-like XOR مع مفتاح من Anvil Secrets.
    إذا لم يُعَد المفتاح، يرفع بدون تشفير.
    يُرجع: (encrypted_bytes, is_encrypted)
    """
    try:
        import anvil.secrets as _sec
        key = _sec.get_secret('BACKUP_ENCRYPTION_KEY')
        if not key:
            return json_bytes, False
        import hashlib
        key_bytes = hashlib.sha256(key.encode('utf-8')).digest()
        # XOR encryption with key stretching
        encrypted = bytearray(len(json_bytes))
        for i in range(len(json_bytes)):
            encrypted[i] = json_bytes[i] ^ key_bytes[i % len(key_bytes)]
        # Add magic header to identify encrypted files
        return b'HP_ENC_V1:' + bytes(encrypted), True
    except Exception as e:
        logger.warning("Backup encryption unavailable: %s - uploading unencrypted", e)
        return json_bytes, False


def _decrypt_backup(data_bytes):
    """
    فك تشفير النسخة الاحتياطية.
    يُرجع: decrypted_bytes
    """
    if not data_bytes.startswith(b'HP_ENC_V1:'):
        return data_bytes  # ملف غير مشفر
    try:
        import anvil.secrets as _sec
        key = _sec.get_secret('BACKUP_ENCRYPTION_KEY')
        if not key:
            raise ValueError("BACKUP_ENCRYPTION_KEY not set in Anvil Secrets")
        import hashlib
        key_bytes = hashlib.sha256(key.encode('utf-8')).digest()
        encrypted = data_bytes[len(b'HP_ENC_V1:'):]
        decrypted = bytearray(len(encrypted))
        for i in range(len(encrypted)):
            decrypted[i] = encrypted[i] ^ key_bytes[i % len(key_bytes)]
        return bytes(decrypted)
    except Exception as e:
        logger.error("Backup decryption failed: %s", e)
        raise


def _upload_backup_to_drive(json_bytes, filename):
    """
    تشفير ورفع ملف النسخة الاحتياطية إلى Google Drive تلقائياً.
    يُرجع: (success: bool, message: str)
    """
    try:
        folder = _get_backup_drive_folder()
        if folder is None:
            return False, 'لم يتم العثور على مجلد Backups في Google Drive. أضف مجلداً باسم Backups أو Helwan_Plast_Backups من Anvil → Google Drive.'
        # تشفير قبل الرفع
        upload_bytes, is_encrypted = _encrypt_backup(json_bytes)
        content_type = 'application/octet-stream' if is_encrypted else 'application/json'
        upload_filename = filename + '.enc' if is_encrypted else filename
        folder.create_file(upload_filename, content_bytes=upload_bytes, content_type=content_type)
        enc_msg = " (مشفر)" if is_encrypted else ""
        return True, f'تم الرفع إلى Google Drive{enc_msg}: {upload_filename}'
    except Exception as e:
        logger.exception("Upload backup to Drive: %s", e)
        return False, str(e)


def _row_to_dict(row, exclude_keys=None):
    """تحويل صف جدول إلى dict مع استبعاد مفاتيح حساسة."""
    exclude_keys = exclude_keys or set()
    try:
        d = dict(row)
        for k in list(d.keys()):
            if k in exclude_keys:
                d.pop(k, None)
        return d
    except Exception:
        return {}


def _build_backup_payload():
    """
    بناء محتوى النسخة الاحتياطية (بدون تحقق صلاحية).
    يُستخدم من create_backup (يدوي) و run_scheduled_backup (مجدول).
    يُرجع: (backup_dict, json_bytes, filename)
    """
    export_time = datetime.now()
    export_date_str = export_time.strftime('%Y-%m-%d %H:%M:%S')
    filename_date = export_time.strftime('%Y%m%d_%H%M')
    backup = {
        'export_date': export_date_str,
        'app': 'Helwan_Plast',
        'version': 1,
        'clients': [],
        'quotations': [],
        'contracts': [],
        'machine_specs': [],
        'settings': []
    }
    sensitive_setting_keys = ('pending_totp_', 'password', 'secret', 'totp_')
    for row in app_tables.clients.search():
        backup['clients'].append(_row_to_dict(row))
    for row in app_tables.quotations.search():
        backup['quotations'].append(_row_to_dict(row))
    try:
        for row in app_tables.contracts.search():
            backup['contracts'].append(_row_to_dict(row))
    except Exception:
        backup['contracts'] = []
    try:
        for row in app_tables.machine_specs.search():
            backup['machine_specs'].append(_row_to_dict(row))
    except Exception:
        backup['machine_specs'] = []
    for row in app_tables.settings.search():
        key = (row.get('setting_key') or '').lower()
        if any(s in key for s in sensitive_setting_keys):
            continue
        backup['settings'].append({
            'setting_key': row.get('setting_key'),
            'setting_value': row.get('setting_value'),
            'setting_type': row.get('setting_type')
        })
    json_bytes = json.dumps(backup, ensure_ascii=False, indent=2, default=str).encode('utf-8')
    filename = f"Helwan_Plast_backup_{filename_date}.json"
    return backup, json_bytes, filename


@anvil.server.background_task
def run_scheduled_backup():
    """
    نسخة احتياطية مجدولة (تُستدعى تلقائياً يوم 1 ويوم 16 من كل شهر).
    تحفظ الملف في جدول scheduled_backups، ترفعه إلى Google Drive، وتُسجّل في سجل التدقيق.
    """
    try:
        backup, json_bytes, filename = _build_backup_payload()
        media = anvil.BlobMedia('application/json', json_bytes, name=filename)
        try:
            app_tables.scheduled_backups.add_row(
                created_at=datetime.now(),
                filename=filename,
                backup_media=media
            )
        except Exception as tbl_err:
            logger.warning("scheduled_backups table add_row failed (table or column may be missing): %s", tbl_err)
        drive_ok, drive_msg = _upload_backup_to_drive(json_bytes, filename)
        if drive_ok:
            logger.info("Backup uploaded to Google Drive: %s", filename)
        else:
            logger.warning("Backup not uploaded to Drive: %s", drive_msg)
        AuthManager.log_audit(
            'BACKUP_SCHEDULED', 'backup', filename,
            None, {'export_date': backup['export_date'], 'source': 'scheduled', 'drive_uploaded': drive_ok},
            user_email='scheduled', ip_address='system',
            user_name='نظام (مجدول)',
            action_description=f"نسخة احتياطية مجدولة - {filename}" + (" + Google Drive" if drive_ok else "")
        )
        logger.info("Scheduled backup completed: %s", filename)
    except Exception as e:
        logger.exception("Scheduled backup failed: %s", e)


@anvil.server.callable
def list_scheduled_backups(token_or_email):
    """قائمة النسخ الاحتياطية المجدولة (للأدمن). تُرجع آخر 50 نسخة."""
    is_authorized, error = AuthManager.require_admin(token_or_email)
    if not is_authorized:
        return error if isinstance(error, dict) else {'success': False, 'message': 'Permission denied'}
    try:
        rows = list(app_tables.scheduled_backups.search())
        rows.sort(key=lambda r: r.get('created_at') or datetime.min, reverse=True)
        data = []
        for r in rows[:50]:
            data.append({
                'created_at': r['created_at'].isoformat() if r.get('created_at') else '',
                'filename': r.get('filename', ''),
            })
        return {'success': True, 'data': data}
    except Exception as e:
        logger.exception("list_scheduled_backups: %s", e)
        return {'success': False, 'message': str(e), 'data': []}


@anvil.server.callable
def get_scheduled_backup_file(token_or_email, filename, created_at_iso):
    """
    تحميل ملف نسخة احتياطية مجدولة (للأدمن).
    filename و created_at_iso كما يردان من list_scheduled_backups.
    """
    is_authorized, error = AuthManager.require_admin(token_or_email)
    if not is_authorized:
        return error if isinstance(error, dict) else {'success': False, 'message': 'Permission denied'}
    if not filename or not created_at_iso:
        return {'success': False, 'message': 'Missing filename or created_at'}
    try:
        from datetime import datetime as dt
        created = dt.fromisoformat(created_at_iso.replace('Z', '+00:00'))
    except Exception:
        return {'success': False, 'message': 'Invalid created_at format'}
    try:
        rows = list(app_tables.scheduled_backups.search())
        norm_iso = created_at_iso.replace('Z', '+00:00').strip()
        for r in rows:
            if r.get('filename') != filename:
                continue
            r_created = r.get('created_at')
            if not r_created:
                continue
            r_iso = r_created.isoformat()
            if r_iso == norm_iso or r_iso.replace('+00:00', 'Z') == created_at_iso.strip():
                media = r.get('backup_media')
                if media:
                    return {'success': True, 'file': media, 'filename': filename}
                return {'success': False, 'message': 'Backup file not found'}
        return {'success': False, 'message': 'Backup not found'}
    except Exception as e:
        logger.exception("get_scheduled_backup_file: %s", e)
        return {'success': False, 'message': str(e)}
    

@anvil.server.callable
def create_backup(token_or_email):
    """
    إنشاء نسخة احتياطية من البيانات الأساسية (عملاء، عروض، عقود، إعدادات، مواصفات مكائن).
    للأدمن فقط. يُرجع ملف JSON للتحميل.
    """
    is_authorized, error = AuthManager.require_admin(token_or_email)
    if not is_authorized:
        return error if isinstance(error, dict) else {'success': False, 'message': 'Permission denied'}

    ip_address = get_client_ip()
    user_email = token_or_email if '@' in str(token_or_email) else None
    if not user_email and token_or_email:
        try:
            s = AuthManager.validate_token(token_or_email)
            if s.get('valid') and s.get('user'):
                user_email = s['user'].get('email', '')
        except Exception as e:
            pass
    user_email = user_email or 'admin'

    try:
        backup, json_bytes, filename = _build_backup_payload()
        media = anvil.BlobMedia('application/json', json_bytes, name=filename)
        drive_ok, drive_msg = _upload_backup_to_drive(json_bytes, filename)
        AuthManager.log_audit(
            'BACKUP_EXPORT', 'backup', filename,
            None, {'export_date': backup['export_date'], 'tables': list(backup.keys()), 'drive_uploaded': drive_ok},
            user_email=user_email, ip_address=ip_address,
            action_description=f"تحميل نسخة احتياطية - {filename}" + (" + Google Drive" if drive_ok else "")
        )
        return {'success': True, 'file': media, 'filename': filename, 'drive_uploaded': drive_ok, 'drive_message': drive_msg if not drive_ok else None}
    except Exception as e:
        logger.exception("create_backup error")
        return {'success': False, 'message': str(e)}


def _parse_backup_value(v):
    """تحويل قيمة من JSON النسخة الاحتياطية إلى نوع صحيح (date, datetime)."""
    if v is None:
        return None
    if isinstance(v, str) and v.strip():
        try:
            if 'T' in v or ' ' in v:
                return datetime.fromisoformat(v.replace('Z', '+00:00')[:26])
            if len(v) == 10 and v[4] == '-' and v[7] == '-':
                return datetime.strptime(v, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
    return v


@anvil.server.callable
def restore_backup(token_or_email, backup_media):
    """
    استعادة كاملة من نسخة احتياطية (Restore Point).
    للأدمن فقط. backup_media: ملف النسخة (BlobMedia أو من التحميل).
    يستبدل: العملاء، العروض، العقود، الإعدادات، مواصفات المكائن.
    لا يمس: المستخدمين، الجلسات، سجل التدقيق.
    """
    is_authorized, error = AuthManager.require_admin(token_or_email)
    if not is_authorized:
        return error if isinstance(error, dict) else {'success': False, 'message': 'Permission denied'}
    if not backup_media:
        return {'success': False, 'message': 'لم يُرفع ملف النسخة الاحتياطية'}
    try:
        raw = backup_media.get_bytes()
        data = json.loads(raw.decode('utf-8'))
    except Exception as e:
        logger.exception("restore_backup parse: %s", e)
        return {'success': False, 'message': f'ملف غير صالح: {e}'}
    if data.get('app') != 'Helwan_Plast' or data.get('version') != 1:
        return {'success': False, 'message': 'ملف نسخة احتياطية غير متوافق (يجب أن يكون من Helwan_Plast)'}
    ip_address = get_client_ip()
    user_email = 'admin'
    if token_or_email and '@' in str(token_or_email):
        user_email = token_or_email
    else:
        try:
            s = AuthManager.validate_token(token_or_email)
            if s.get('valid') and s.get('user'):
                user_email = s['user'].get('email', '')
        except Exception as e:
            pass
    stats = {'clients': 0, 'quotations': 0, 'contracts': 0, 'settings': 0, 'machine_specs': 0}
    try:
        def clear_table(table):
            for row in list(table.search()):
                row.delete()
        def restore_table(table, items, key_convert=None):
            key_convert = key_convert or (lambda x: x)
            restored = 0
            for item in items:
                row_data = {}
                for k, v in item.items():
                    if k is None or (v is None and k != 'setting_key'):
                        continue
                    row_data[key_convert(k)] = _parse_backup_value(v)
                if row_data:
                    try:
                        table.add_row(**row_data)
                        restored += 1
                    except Exception as add_err:
                        logger.warning("restore skip row %s: %s", list(row_data.keys())[:3], add_err)
            return restored

        # ===== نسخة احتياطية من البيانات الحالية قبل الحذف (Safety Net) =====
        pre_restore_backup = {}
        try:
            pre_restore_backup['clients'] = [_row_to_dict(r) for r in app_tables.clients.search()]
            pre_restore_backup['quotations'] = [_row_to_dict(r) for r in app_tables.quotations.search()]
            try:
                pre_restore_backup['contracts'] = [_row_to_dict(r) for r in app_tables.contracts.search()]
            except Exception:
                pre_restore_backup['contracts'] = []
            try:
                pre_restore_backup['machine_specs'] = [_row_to_dict(r) for r in app_tables.machine_specs.search()]
            except Exception:
                pre_restore_backup['machine_specs'] = []
        except Exception as snap_err:
            logger.error("Could not create pre-restore snapshot: %s", snap_err)
            return {'success': False, 'message': f'فشل إنشاء نقطة استعادة آمنة: {snap_err}'}

        # ===== بدء الاستعادة =====
        restore_failed = False
        try:
            clear_table(app_tables.clients)
            stats['clients'] = restore_table(app_tables.clients, data.get('clients', []))
        except Exception as e:
            logger.error("Failed restoring clients: %s", e)
            restore_failed = True

        if restore_failed:
            # ===== Rollback: إعادة البيانات القديمة =====
            logger.critical("Restore FAILED - rolling back to pre-restore state")
            try:
                clear_table(app_tables.clients)
                restore_table(app_tables.clients, pre_restore_backup.get('clients', []))
            except Exception as rb_err:
                logger.critical("ROLLBACK FAILED for clients: %s", rb_err)
            return {'success': False, 'message': 'فشلت الاستعادة - تم استرجاع البيانات السابقة'}

        clear_table(app_tables.quotations)
        stats['quotations'] = restore_table(app_tables.quotations, data.get('quotations', []))
        clear_table(app_tables.quotations)
        restore_table(app_tables.quotations, data.get('quotations', []))
        stats['quotations'] = len(data.get('quotations', []))
        try:
            clear_table(app_tables.contracts)
            restore_table(app_tables.contracts, data.get('contracts', []))
            stats['contracts'] = len(data.get('contracts', []))
        except Exception as e:
            logger.warning("restore contracts: %s", e)
        for item in data.get('settings', []):
            sk = item.get('setting_key')
            if not sk:
                continue
            try:
                existing = app_tables.settings.get(setting_key=sk)
                if existing:
                    existing.update(setting_value=item.get('setting_value'), setting_type=item.get('setting_type', 'text'))
                else:
                    app_tables.settings.add_row(setting_key=sk, setting_value=item.get('setting_value'), setting_type=item.get('setting_type', 'text'))
                stats['settings'] += 1
            except Exception as e:
                logger.warning("restore setting %s: %s", sk, e)
        try:
            clear_table(app_tables.machine_specs)
            restore_table(app_tables.machine_specs, data.get('machine_specs', []))
            stats['machine_specs'] = len(data.get('machine_specs', []))
        except Exception as e:
            logger.warning("restore machine_specs: %s", e)
        AuthManager.log_audit(
            'BACKUP_RESTORE', 'backup', data.get('export_date', ''),
            None, stats,
            user_email=user_email, ip_address=ip_address,
            action_description=f"استعادة من نسخة احتياطية - {data.get('export_date', '')} - عملاء:{stats['clients']} عروض:{stats['quotations']}"
        )
        return {'success': True, 'message': 'تمت الاستعادة بنجاح', 'stats': stats}
    except Exception as e:
        logger.exception("restore_backup: %s", e)
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def list_drive_backups(token_or_email):
    """قائمة ملفات النسخ الاحتياطية في مجلد Google Drive (للأدمن)."""
    is_authorized, error = AuthManager.require_admin(token_or_email)
    if not is_authorized:
        return error if isinstance(error, dict) else {'success': False, 'message': 'Permission denied', 'data': []}
    try:
        folder = _get_backup_drive_folder()
        if folder is None:
            return {'success': False, 'message': 'لم يتم العثور على مجلد Backups في Google Drive', 'data': []}
        files = []
        file_list = list(folder.list_files()) if hasattr(folder, 'list_files') else getattr(folder, 'files', [])
        for f in file_list:
            title = getattr(f, 'name', None) or getattr(f, 'title', None) or str(f)
            if title and (title.endswith('.json') or 'backup' in title.lower()):
                files.append({'filename': title})
        files.sort(key=lambda x: x['filename'], reverse=True)
        return {'success': True, 'data': files[:100]}
    except Exception as e:
        logger.exception("list_drive_backups: %s", e)
        return {'success': False, 'message': str(e), 'data': []}


@anvil.server.callable
def restore_backup_from_drive(token_or_email, filename):
    """
    استعادة من نسخة احتياطية مخزنة في Google Drive (بالاسم).
    للأدمن فقط.
    """
    is_authorized, error = AuthManager.require_admin(token_or_email)
    if not is_authorized:
        return error if isinstance(error, dict) else {'success': False, 'message': 'Permission denied'}
    if not filename:
        return {'success': False, 'message': 'اسم الملف مطلوب'}
    try:
        folder = _get_backup_drive_folder()
        if folder is None:
            return {'success': False, 'message': 'لم يتم العثور على مجلد Backups في Google Drive'}
        f = folder.get(filename)
        if f is None:
            return {'success': False, 'message': f'الملف غير موجود: {filename}'}
        raw = f.get_bytes()
        media = anvil.BlobMedia('application/json', raw, name=filename)
        return restore_backup(token_or_email, media)
    except Exception as e:
        logger.exception("restore_backup_from_drive: %s", e)
        return {'success': False, 'message': str(e)}

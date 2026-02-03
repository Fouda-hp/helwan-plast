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


def _get_next_number(table_name, column_name):
    """
    توليد الرقم التالي بشكل آمن
    يبحث عن القيمة القصوى ويضيف 1
    """
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
def save_quotation(form_data, user_email='system'):
    """
    دالة الحفظ الرئيسية مع الترقيم التلقائي وسجل التدقيق
    """
    ip_address = get_client_ip()
    logger.info("Received form_data for save")

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
def get_all_quotations(page=1, per_page=20, search='', include_deleted=False):
    """الحصول على العروض مع الترقيم والبحث - محسّن لمشكلة N+1"""

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
def get_all_clients(page=1, per_page=20, search='', include_deleted=False):
    """الحصول على العملاء مع الترقيم والبحث"""

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
            "Date": r["Date"].isoformat() if isinstance(r["Date"], datetime) else str(r["Date"] or ""),
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
def export_clients_data(include_deleted=False):
    """تصدير جميع بيانات العملاء لـ CSV/Excel"""

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
def export_quotations_data(include_deleted=False):
    """تصدير جميع بيانات العروض لـ CSV/Excel - محسّن"""

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
            "Company": client["Company"] if client else "",
            "Phone": client["Phone"] if client else "",
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
def get_dashboard_stats():
    """الحصول على إحصائيات لوحة التحكم"""

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
                'phone': user['phone'] or 'N/A'
            }
        return {'name': 'N/A', 'phone': 'N/A'}
    except Exception:
        return {'name': 'N/A', 'phone': 'N/A'}


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
def get_quotation_pdf_data(quotation_number, user_email):
    """
    جلب كل البيانات اللازمة لتصدير عرض السعر كـ PDF
    """
    try:
        # جلب بيانات عرض السعر
        quotation = app_tables.quotations.get(**{'Quotation#': quotation_number})
        if not quotation:
            return {'success': False, 'message': 'Quotation not found'}

        q_data = dict(quotation)

        # جلب معلومات المستخدم (الاسم والهاتف للهيدر)
        user_info = get_user_info(user_email)

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
        }

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
            # معلومات المستخدم (للهيدر)
            'user_name': user_info['name'],
            'user_phone': user_info['phone'],

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
            'video_inspection': q_data.get('Video inspection', 'NO'),
            'plc': q_data.get('PLC', 'NO'),
            'slitter': q_data.get('Slitter', 'NO'),

            # المواصفات الفنية
            'machine_specs': machine_specs,

            # السلندرات
            'cylinders': cylinders,

            # المعلومات المالية
            'total_price': format_number(total_price),
            'total_price_raw': total_price,
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
        }

        return {'success': True, 'data': pdf_data}

    except Exception as e:
        logger.error(f"Error getting quotation PDF data: {e}")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_all_template_settings():
    """جلب كل إعدادات القالب"""
    try:
        settings = {}
        for row in app_tables.settings.search():
            settings[row['setting_key']] = row['setting_value']
        return {'success': True, 'settings': settings}
    except Exception as e:
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def save_machine_specs(specs_data):
    """حفظ المواصفات الفنية للماكينة"""
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
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_all_machine_specs():
    """جلب كل المواصفات الفنية"""
    try:
        specs = []
        for row in app_tables.machine_specs.search():
            specs.append(dict(row))
        return {'success': True, 'specs': specs}
    except Exception as e:
        return {'success': False, 'message': str(e)}

"""
quotation_numbers.py - الترقيم التلقائي للعملاء والعروض (ذرّي بدون دوبليكيت)
================================================================================
السيرفر هو المصدر الوحيد للأرقام (Single Source of Truth).
يستخدم جدول counters + Transaction لمنع أي تكرار حتى مع طلبات متزامنة (Race Conditions).
لا يوجد table.search() على الجدول الكامل؛ الأداء ثابت O(1) لكل طلب.
"""

import logging
from anvil.tables import app_tables
from anvil import tables as anvil_tables
import anvil.server

logger = logging.getLogger(__name__)

# مفاتيح العدّادات في جدول counters (نص فريد لكل نوع ترقيم)
COUNTER_CLIENTS = "clients_next"
COUNTER_QUOTATIONS = "quotations_next"


def _seed_initial_value(counter_key):
    """
    عند إنشاء عداد جديد: نزرعه من القيمة العظمى في الجدول الفعلي (إن وُجدت بيانات)
    حتى لا يتداخل الرقم مع أرقام موجودة مسبقاً.
    يُرجع: int (القيمة الابتدائية للعداد، 1 على الأقل).
    """
    max_val = 0
    try:
        if counter_key == COUNTER_CLIENTS:
            for row in app_tables.clients.search():
                v = row.get("Client Code")
                if v is not None:
                    try:
                        n = int(v) if isinstance(v, str) else v
                        if n > max_val:
                            max_val = n
                    except (ValueError, TypeError):
                        pass
        elif counter_key == COUNTER_QUOTATIONS:
            for row in app_tables.quotations.search():
                v = row.get("Quotation#")
                if v is not None:
                    try:
                        n = int(v) if isinstance(v, str) else v
                        if n > max_val:
                            max_val = n
                    except (ValueError, TypeError):
                        pass
    except Exception as e:
        logger.warning("_seed_initial_value(%s): %s; using 1", counter_key, e)
    return max(1, max_val + 1)


@anvil.server.callable
@anvil_tables.in_transaction
def get_next_number_atomic(counter_key):
    """
    ترجع الرقم التالي وتحدّث العداد بشكل ذري لمنع أي دوبليكيت.
    تستخدم Transaction بحيث: قراءة العداد → زيادة → كتابة، كلها في نفس المعاملة،
    وإذا تعارضت مع طلب آخر تُعاد المحاولة تلقائياً (حتى 5 مرات) من قبل Anvil.
    النتيجة: لا يوجد دوبليكيت حتى مع آلاف الطلبات المتزامنة.
    """
    row = app_tables.counters.get(key=counter_key)
    if row is None:
        # إنشاء العداد لأول مرة مع قيمة ابتدائية من الجدول الفعلي (أو 1)
        initial = _seed_initial_value(counter_key)
        app_tables.counters.add_row(key=counter_key, value=initial)
        logger.info("Counter created: key=%s, initial_value=%s", counter_key, initial)
        return initial
    current = row["value"]
    if current is None:
        current = 0
    try:
        next_val = int(current) + 1
    except (ValueError, TypeError):
        next_val = 1
    row["value"] = next_val
    logger.info("Next number generated: key=%s, previous=%s, next=%s", counter_key, current, next_val)
    return next_val


# ========== دوال الترقيم المعرّضة للعميل (كلها تستدعي العداد الذرّي فقط) ==========


@anvil.server.callable
def get_next_client_code():
    """الحصول على رمز العميل التالي. الرقم من السيرفر فقط."""
    return get_next_number_atomic(COUNTER_CLIENTS)


@anvil.server.callable
def get_next_quotation_number():
    """الحصول على رقم العرض التالي. الرقم من السيرفر فقط."""
    return get_next_number_atomic(COUNTER_QUOTATIONS)


@anvil.server.callable
def get_or_create_client_code(client_name, phone):
    """البحث عن عميل بالهاتف أو إنشاء رمز جديد من السيرفر."""
    if not phone:
        return None
    phone = str(phone).strip()
    client_name = str(client_name).strip() if client_name else ""
    logger.info("Checking phone='%s'", phone)
    row = app_tables.clients.get(Phone=phone, is_deleted=False)
    if row:
        code = str(row["Client Code"])
        logger.info("Existing phone found, client_code=%s", code)
        return code
    new_code = get_next_number_atomic(COUNTER_CLIENTS)
    logger.info("New phone, generated client_code=%s", new_code)
    return str(new_code)


@anvil.server.callable
def get_quotation_number_if_needed(current_number, model):
    """الحصول على رقم العرض إذا لزم الأمر (من العميل عند بناء النموذج). الرقم من السيرفر فقط."""
    if current_number:
        try:
            return int(current_number)
        except (ValueError, TypeError):
            pass
    if not model:
        return None
    return get_next_number_atomic(COUNTER_QUOTATIONS)

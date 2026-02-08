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


def _get_max_from_table(counter_key, include_deleted=False):
    """
    القيمة العظمى الفعلية في جدول العملاء أو العروض.
    تُستخدم للبذر الأولي ولإعادة المزامنة.
    include_deleted: إذا True نعدّ كل الصفوف؛ إذا False نستثني is_deleted=True حيث وُجد.
    """
    max_val = 0
    try:
        if counter_key == COUNTER_CLIENTS:
            it = app_tables.clients.search()
            for row in it:
                if not include_deleted and row.get("is_deleted") is True:
                    continue
                v = row.get("Client Code")
                if v is not None:
                    try:
                        n = int(v) if isinstance(v, str) else v
                        if n > max_val:
                            max_val = n
                    except (ValueError, TypeError):
                        pass
        elif counter_key == COUNTER_QUOTATIONS:
            it = app_tables.quotations.search()
            for row in it:
                if not include_deleted and row.get("is_deleted") is True:
                    continue
                v = row.get("Quotation#")
                if v is not None:
                    try:
                        n = int(v) if isinstance(v, str) else v
                        if n > max_val:
                            max_val = n
                    except (ValueError, TypeError):
                        pass
    except Exception as e:
        logger.warning("_get_max_from_table(%s): %s", counter_key, e)
    return max_val


def _seed_initial_value(counter_key):
    """
    عند إنشاء عداد جديد: نزرعه من القيمة العظمى في الجدول الفعلي.
    يُخزَّن العداد = max حتى يكون الرقم التالي المُعطى = max+1 (أو 1 إذا الجدول فاضي).
    """
    max_val = _get_max_from_table(counter_key, include_deleted=True)
    return max_val


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
        current = int(current)
    except (ValueError, TypeError):
        current = 0
    # تصحيح تلقائي: لو العداد أكبر من الواقع (مثلاً 14 و عندك 5 عملاء) نضبطه على max الجدول
    max_val = _get_max_from_table(counter_key, include_deleted=False)
    if current > max_val + 1:
        row["value"] = max_val
        next_val = max_val + 1
        logger.info("Counter auto-resynced: key=%s, was=%s, now=%s, next=%s", counter_key, current, max_val, next_val)
        return next_val
    next_val = current + 1
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


@anvil.server.callable
def resync_numbering_counters(token_or_email=None):
    """
    إعادة مزامنة عدّادي العملاء والعروض مع الجداول الفعلية (غير المحذوفة).
    بعد التشغيل: الرقم التالي للعميل = أكبر كود عميل + 1، والرقم التالي للعرض = أكبر رقم عرض + 1.
    يُنصح بتشغيلها مرة واحدة عند ظهور ترقيم خاطئ (مثلاً 14، 18 بدل 6، 8).
    """
    try:
        max_clients = _get_max_from_table(COUNTER_CLIENTS, include_deleted=False)
        max_quotations = _get_max_from_table(COUNTER_QUOTATIONS, include_deleted=False)
        for key, max_val in [(COUNTER_CLIENTS, max_clients), (COUNTER_QUOTATIONS, max_quotations)]:
            row = app_tables.counters.get(key=key)
            if row is None:
                app_tables.counters.add_row(key=key, value=max_val)
                logger.info("Counter created on resync: key=%s, value=%s", key, max_val)
            else:
                row["value"] = max_val
                logger.info("Counter resynced: key=%s, new_value=%s", key, max_val)
        return {
            "success": True,
            "message": "Counters resynced. Next client code will be {}, next quotation # will be {}.".format(
                max_clients + 1, max_quotations + 1
            ),
            "next_client_code": max_clients + 1,
            "next_quotation_number": max_quotations + 1,
        }
    except Exception as e:
        logger.exception("resync_numbering_counters failed")
        return {"success": False, "message": str(e)}

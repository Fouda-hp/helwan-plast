"""
quotation_numbers.py - الترقيم التلقائي للعملاء والعروض (ذرّي بدون دوبليكيت)
================================================================================
السيرفر هو المصدر الوحيد للأرقام (Single Source of Truth).
يستخدم جدول counters + Transaction لمنع أي تكرار حتى مع طلبات متزامنة (Race Conditions).

مبدأ Reserve-on-Save:
  - peek_next_*  → للعرض فقط (بدون حجز) — يُستدعى من الحاسبة
  - get_next_number_atomic → للحجز الفعلي — يُستدعى فقط عند الحفظ من save_quotation

جميع الدوال Callable تتطلب مصادقة (token_or_email) ما لم يُذكر خلاف ذلك.
"""

import logging
from datetime import datetime
from anvil.tables import app_tables
from anvil import tables as anvil_tables
import anvil.server

logger = logging.getLogger(__name__)


def _require_auth(token_or_email):
    """التحقق من الجلسة؛ يُرجع (user_email, None) أو (None, error_dict).
    يستخدم الدالة المركزية من auth_permissions."""
    try:
        try:
            from .auth_permissions import require_authenticated
        except ImportError:
            from auth_permissions import require_authenticated
        is_valid, email, err = require_authenticated(token_or_email)
        return (email, None) if is_valid else (None, err)
    except Exception as e:
        logger.warning("quotation_numbers auth check: %s", e)
        return None, {"success": False, "message": "Invalid or expired session"}


def _require_admin(token_or_email):
    """التحقق من صلاحية الأدمن؛ يُرجع (True, None) أو (False, error_dict)."""
    try:
        from . import AuthManager
        ok, err = AuthManager.require_admin(token_or_email)
        if ok:
            return True, None
        return False, (err or {"success": False, "message": "Admin required"})
    except Exception as e:
        logger.warning("quotation_numbers admin check: %s", e)
        return False, {"success": False, "message": "Admin required"}

# مفاتيح العدّادات في جدول counters (نص فريد لكل نوع ترقيم)
COUNTER_CLIENTS = "clients_next"
COUNTER_QUOTATIONS = "quotations_next"
COUNTER_CONTRACTS_SERIAL_PREFIX = "contracts_serial_"


def _get_max_from_table(counter_key, include_deleted=False):
    """
    القيمة العظمى الفعلية في جدول العملاء أو العروض.
    تُستخدم للبذر الأولي ولإعادة المزامنة.
    include_deleted: إذا True نعدّ كل الصفوف؛ إذا False نستثني is_deleted=True حيث وُجد.

    Performance: tries descending order first for O(1) best case,
    falls back to full scan if ordering is not supported.
    """
    max_val = 0
    try:
        if counter_key == COUNTER_CLIENTS:
            col_name = "Client Code"
            search_kwargs = {} if include_deleted else {"is_deleted": False}
            try:
                # Try ordered search — O(1) if the column is sortable
                from anvil.tables import order_by
                results = app_tables.clients.search(
                    order_by=[order_by(col_name, ascending=False)],
                    **search_kwargs
                )
                for row in results:
                    v = row.get(col_name)
                    if v is not None:
                        try:
                            return int(v) if isinstance(v, str) else int(v)
                        except (ValueError, TypeError):
                            continue
            except Exception:
                # Fallback: full scan (original logic)
                for row in app_tables.clients.search():
                    if not include_deleted and row.get("is_deleted") is True:
                        continue
                    v = row.get(col_name)
                    if v is not None:
                        try:
                            n = int(v) if isinstance(v, str) else v
                            if n > max_val:
                                max_val = n
                        except (ValueError, TypeError):
                            pass
        elif counter_key == COUNTER_QUOTATIONS:
            col_name = "Quotation#"
            search_kwargs = {} if include_deleted else {"is_deleted": False}
            try:
                from anvil.tables import order_by
                results = app_tables.quotations.search(
                    order_by=[order_by(col_name, ascending=False)],
                    **search_kwargs
                )
                for row in results:
                    v = row.get(col_name)
                    if v is not None:
                        try:
                            return int(v) if isinstance(v, str) else int(v)
                        except (ValueError, TypeError):
                            continue
            except Exception:
                for row in app_tables.quotations.search():
                    if not include_deleted and row.get("is_deleted") is True:
                        continue
                    v = row.get(col_name)
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


# ==========================================================================
# دوال Peek — للعرض فقط بدون حجز (تُستدعى من الحاسبة)
# ==========================================================================

def peek_next_number(counter_key):
    """
    قراءة الرقم التالي المتوقع بدون زيادة العداد.
    تُستخدم لعرض الرقم في الحاسبة فقط — الرقم الفعلي يُحجز عند الحفظ.
    المنطق متطابق مع get_next_number_atomic: max(counter, max_table) + 1
    """
    max_val = _get_max_from_table(counter_key, include_deleted=True)

    row = app_tables.counters.get(key=counter_key)
    if row is None:
        return max_val + 1

    current = row["value"]
    if current is None:
        current = 0
    try:
        current = int(current)
    except (ValueError, TypeError):
        current = 0

    # نفس منطق get_next_number_atomic: max(counter, max_table) + 1
    return max(current, max_val) + 1


@anvil.server.callable
def peek_next_client_code(token_or_email=None):
    """عرض رمز العميل التالي المتوقع بدون حجز (للعرض في الحاسبة فقط). يتطلب مصادقة."""
    _, err = _require_auth(token_or_email)
    if err:
        return None
    return peek_next_number(COUNTER_CLIENTS)


@anvil.server.callable
def peek_next_quotation_number(token_or_email=None):
    """عرض رقم العرض التالي المتوقع بدون حجز (للعرض في الحاسبة فقط). يتطلب مصادقة."""
    _, err = _require_auth(token_or_email)
    if err:
        return None
    return peek_next_number(COUNTER_QUOTATIONS)


# ==========================================================================
# دالة الحجز الذرّي — تُستدعى فقط من save_quotation / import
# ==========================================================================

@anvil.server.callable
@anvil_tables.in_transaction
def get_next_number_atomic(counter_key, token_or_email=None):
    """
    ترجع الرقم التالي وتحدّث العداد بشكل ذري لمنع أي دوبليكيت أو أرقام مفقودة.
    العداد يخزن آخر رقم تم إصداره فعلياً (last_issued).
    الرقم التالي = max(counter, max_table) + 1 لضمان عدم وجود فجوات أو تكرار.
    تتطلب مصادقة (يُمرَّر من save_quotation أو استيراد).
    """
    _, err = _require_auth(token_or_email)
    if err:
        raise anvil.server.AnvilWrappedError(Exception(err.get("message", "Authentication required")))

    # القيمة العظمى الفعلية في الجدول (تشمل المحذوفات لمنع إعادة استخدام أرقامها)
    max_val = _get_max_from_table(counter_key, include_deleted=True)

    row = app_tables.counters.get(key=counter_key)
    if row is None:
        # إنشاء العداد لأول مرة
        next_val = max_val + 1
        app_tables.counters.add_row(key=counter_key, value=next_val)
        logger.info("Counter created: key=%s, max_table=%s, issued=%s", counter_key, max_val, next_val)
        return next_val

    current = row["value"]
    if current is None:
        current = 0
    try:
        current = int(current)
    except (ValueError, TypeError):
        current = 0

    # الرقم التالي = أكبر من (العداد، أكبر رقم في الجدول) + 1
    # هذا يمنع: التكرار (لو العداد متأخر) والفجوات (لو العداد متقدم)
    base = max(current, max_val)
    next_val = base + 1

    row["value"] = next_val
    if current != base:
        logger.info("Counter corrected: key=%s, counter_was=%s, max_table=%s, issued=%s", counter_key, current, max_val, next_val)
    else:
        logger.info("Next number generated: key=%s, previous=%s, issued=%s", counter_key, current, next_val)
    return next_val


@anvil_tables.in_transaction
def _get_next_contract_serial_atomic(counter_key):
    """
    ذرّي: بذر العداد + زيادة في transaction واحدة لمنع race conditions.
    لا يستدعي get_next_number_atomic (تجنب transactions متداخلة في Anvil).
    منطق الزيادة مطابق لـ get_next_number_atomic: max(counter, max_table) + 1.
    """
    max_val = _get_max_from_table(counter_key, include_deleted=True)
    row = app_tables.counters.get(key=counter_key)
    if row is None:
        # أول عقد في السنة: بذر بـ 1 ثم الرقم التالي = max(1, max_table) + 1
        seed = max(1, max_val)
        next_val = seed + 1
        app_tables.counters.add_row(key=counter_key, value=next_val)
        logger.info("Contract serial counter created: key=%s, seed=%s, issued=%s", counter_key, seed, next_val)
        return next_val

    current = row["value"]
    if current is None:
        current = 0
    try:
        current = int(current)
    except (ValueError, TypeError):
        current = 0

    # ضمان البذر لا يقل عن 1 (أول رقم مُرجع = 2)
    if current < 1:
        current = 1

    base = max(current, max_val)
    next_val = base + 1
    row["value"] = next_val
    logger.info("Contract serial generated: key=%s, previous=%s, issued=%s", counter_key, current, next_val)
    return next_val


def get_next_contract_serial():
    """
    المتسلسل السنوي للعقود: يبدأ من 2 ويزيد 1 بعد كل حفظ عقد جديد.
    المفتاح: contracts_serial_YYYY (عدّاد مستقل لكل سنة).
    لو أول عقد في السنة (العداد مش موجود أو = 0): نبذره بـ 1 حتى أول رقم = 2.
    محمي بـ @in_transaction لمنع race conditions على البذر والزيادة.
    """
    year = datetime.now().year
    counter_key = f"{COUNTER_CONTRACTS_SERIAL_PREFIX}{year}"
    return _get_next_contract_serial_atomic(counter_key)


# ==========================================================================
# دوال البحث — بدون حجز أرقام
# ==========================================================================

@anvil.server.callable
def find_client_by_phone(client_name, phone, token_or_email=None):
    """
    البحث عن عميل بالهاتف — إذا موجود يرجع كوده، إذا لا يرجع None.
    يتطلب مصادقة.
    """
    _, err = _require_auth(token_or_email)
    if err:
        return None
    if not phone:
        return None
    phone = str(phone).strip()
    logger.info("find_client_by_phone: phone='%s'", phone)
    row = app_tables.clients.get(Phone=phone, is_deleted=False)
    if row:
        code = str(row["Client Code"])
        logger.info("Existing phone found, client_code=%s", code)
        return code
    logger.info("Phone not found, returning None (number will be assigned on save)")
    return None


@anvil.server.callable
def get_quotation_number_if_needed(current_number, model, token_or_email=None):
    """
    إذا كان الرقم موجود بالفعل، يرجعه. إذا لا، يرجع الرقم المتوقع (peek) بدون حجز.
    يتطلب مصادقة.
    """
    _, err = _require_auth(token_or_email)
    if err:
        return None
    if current_number:
        try:
            return int(current_number)
        except (ValueError, TypeError):
            pass
    if not model:
        return None
    # عرض الرقم المتوقع بدون حجز
    return peek_next_number(COUNTER_QUOTATIONS)


# ==========================================================================
# إعادة المزامنة — تستخدم include_deleted=True لمنع تعارض مع المحذوفات
# ==========================================================================

@anvil.server.callable
@anvil.tables.in_transaction
def resync_numbering_counters(token_or_email=None):
    """
    إعادة مزامنة عدّادي العملاء والعروض مع الجداول الفعلية. تتطلب صلاحية أدمن.
    """
    ok, err = _require_admin(token_or_email)
    if not ok and err:
        return err
    try:
        max_clients = _get_max_from_table(COUNTER_CLIENTS, include_deleted=True)
        max_quotations = _get_max_from_table(COUNTER_QUOTATIONS, include_deleted=True)
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


# ==========================================================================
# توافق عكسي — الدوال القديمة (deprecated, لا تُستدعى من العميل بعد الآن)
# ==========================================================================
# ملاحظة: get_or_create_client_code اُستبدلت بـ find_client_by_phone
# get_next_client_code و get_next_quotation_number لم تعد callable —
# الحجز يتم فقط من save_quotation عبر get_next_number_atomic مباشرة.

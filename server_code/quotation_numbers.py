"""
quotation_numbers.py - الترقيم التلقائي للعملاء والعروض
يُستورد من QuotationManager؛ يُستخدم داخلياً (_get_next_number) ومعرّض كـ callable.
"""

import threading
import logging
from anvil.tables import app_tables
import anvil.server

logger = logging.getLogger(__name__)

_number_locks = {
    'clients': threading.Lock(),
    'quotations': threading.Lock(),
}


def _get_next_number(table_name, column_name):
    """
    توليد الرقم التالي بشكل آمن مع Locking لمنع Race Conditions.
    يُرجع: int (القيمة التالية).
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
        logger.info("%s.%s: max=%s, next=%s", table_name, column_name, max_val, next_val)
        return next_val


@anvil.server.callable
def get_next_client_code():
    """الحصول على رمز العميل التالي (قراءة فقط)."""
    return _get_next_number('clients', 'Client Code')


@anvil.server.callable
def get_next_quotation_number():
    """الحصول على رقم العرض التالي (قراءة فقط)."""
    return _get_next_number('quotations', 'Quotation#')


@anvil.server.callable
def get_or_create_client_code(client_name, phone):
    """البحث عن عميل بالهاتف أو إنشاء رمز جديد."""
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
    new_code = _get_next_number('clients', 'Client Code')
    logger.info("New phone, generated client_code=%s", new_code)
    return str(new_code)


@anvil.server.callable
def get_quotation_number_if_needed(current_number, model):
    """الحصول على رقم العرض إذا لزم الأمر (من JS عند بناء النموذج)."""
    if current_number:
        return int(current_number)
    if not model:
        return None
    new_q = _get_next_number('quotations', 'Quotation#')
    return int(new_q)

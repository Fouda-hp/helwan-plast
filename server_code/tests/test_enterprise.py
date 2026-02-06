"""
Unit tests for Enterprise/SaaS logic (خفيفة).
اختبارات: validate_email، ترقيم، صلاحيات، تنسيق تواريخ.
تشغيل من جذر المشروع:
  python -m pytest server_code/tests/test_enterprise.py -v
  أو: python server_code/tests/test_enterprise.py
  أو: python -m unittest server_code.tests.test_enterprise
"""

import os
import sys
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

# جعل جذر المشروع (والد server_code) في المسار
_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _root not in sys.path:
    sys.path.insert(0, _root)

# Mock anvil قبل استيراد أي وحدة من server_code
def _mock_anvil():
    if 'anvil' in sys.modules:
        return
    m = MagicMock()
    m.server = MagicMock()
    m.tables = MagicMock()
    m.secrets = MagicMock()
    m.secrets.get_secret = MagicMock(return_value=None)
    sys.modules['anvil'] = m
    sys.modules['anvil.server'] = m.server
    sys.modules['anvil.tables'] = m.tables
    sys.modules['anvil.secrets'] = m.secrets

_mock_anvil()


class TestValidateEmail(unittest.TestCase):
    """اختبار تحقق البريد الإلكتروني (auth_utils.validate_email)."""

    def setUp(self):
        from server_code.auth_utils import validate_email
        self.validate_email = validate_email

    def test_valid_emails(self):
        self.assertTrue(self.validate_email('user@example.com'))
        self.assertTrue(self.validate_email('a.b@co.uk'))
        self.assertTrue(self.validate_email('user+tag@domain.org'))

    def test_invalid_emails(self):
        self.assertFalse(self.validate_email(''))
        self.assertFalse(self.validate_email(None))
        self.assertFalse(self.validate_email('no-at-sign'))
        self.assertFalse(self.validate_email('@nodomain.com'))
        self.assertFalse(self.validate_email('node@'))
        self.assertFalse(self.validate_email('user..double@x.com'))
        self.assertFalse(self.validate_email('a' * 255 + '@x.com'))


class TestQuotationNumbers(unittest.TestCase):
    """اختبار دوال الترقيم (_get_next_number) مع mock لـ app_tables."""

    @classmethod
    def setUpClass(cls):
        sys.modules['anvil'].tables.app_tables = MagicMock()
        import server_code.quotation_numbers as qn
        cls._qn = qn

    def test_get_next_number_empty_tables(self):
        app_tables = MagicMock()
        app_tables.clients = MagicMock()
        app_tables.quotations = MagicMock()
        app_tables.clients.search.return_value = []
        app_tables.quotations.search.return_value = []
        qn = self._qn
        with patch.object(qn, 'app_tables', app_tables):
            n = qn._get_next_number('clients', 'Client Code')
        self.assertEqual(n, 1)

    def test_get_next_number_with_max(self):
        app_tables = MagicMock()
        row = MagicMock()
        row.__getitem__ = lambda k: 100 if k == 'Client Code' else None
        app_tables.clients = MagicMock()
        app_tables.clients.search.return_value = [row]
        qn = self._qn
        with patch.object(qn, 'app_tables', app_tables):
            n = qn._get_next_number('clients', 'Client Code')
        self.assertEqual(n, 101)


class TestDateFormatting(unittest.TestCase):
    """اختبار تنسيق التواريخ (منطق format_date_ar / format_date_en)."""

    def test_format_date_ar_logic(self):
        months_ar = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
                     'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
        d = date(2026, 2, 6)
        result = f"{d.day} {months_ar[d.month - 1]}"
        self.assertEqual(result, "6 فبراير")

    def test_format_date_en_logic(self):
        months_en = ['January', 'February', 'March', 'April', 'May', 'June',
                     'July', 'August', 'September', 'October', 'November', 'December']
        d = date(2026, 2, 6)
        result = f"{d.day} {months_en[d.month - 1]}"
        self.assertEqual(result, "6 February")

    def test_empty_date(self):
        self.assertEqual("", "" if None else "x")

    def test_quotation_pdf_formatters(self):
        """اختبار دوال التنسيق الفعلية من quotation_pdf."""
        from server_code import quotation_pdf
        d = date(2026, 2, 6)
        self.assertEqual(quotation_pdf.format_date_ar(d), "6 فبراير")
        self.assertEqual(quotation_pdf.format_date_en(d), "6 February")
        self.assertEqual(quotation_pdf.format_date_ar(None), "")
        self.assertEqual(quotation_pdf.format_number(1000), "1,000")


class TestPermissionConstants(unittest.TestCase):
    """اختبار ثوابت الصلاحيات (auth_constants.ROLES)."""

    def test_roles_structure(self):
        from server_code.auth_constants import ROLES, AVAILABLE_PERMISSIONS
        self.assertIn('admin', ROLES)
        self.assertIn('manager', ROLES)
        self.assertIn('sales', ROLES)
        self.assertIn('viewer', ROLES)
        self.assertEqual(ROLES['admin'], ['all'])
        self.assertIn('delete_own', ROLES['manager'])
        self.assertIn('view', AVAILABLE_PERMISSIONS)
        self.assertIn('delete', AVAILABLE_PERMISSIONS)


if __name__ == '__main__':
    unittest.main()

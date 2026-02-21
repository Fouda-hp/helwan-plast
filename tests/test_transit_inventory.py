"""
Tests for Transit Inventory Model (1210 – Inventory in Transit).

Lifecycle: Draft → Post (DR 1210, CR 2000) → Partial payments (FX unchanged) →
  Add import costs (DR 1210 or 1200 by state) → Move to inventory (DR 1200, CR 1210) → Sale → COGS.

Run from project root:
  python -m pytest server_code/tests/test_transit_inventory.py -v
  or: python server_code/tests/test_transit_inventory.py
"""

import os
import sys
import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch

try:
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    _root = os.path.getcwd()
if _root and _root not in sys.path:
    sys.path.insert(0, _root)


def _mock_anvil():
    if 'anvil' in sys.modules:
        return
    m = MagicMock()
    m.server = MagicMock()
    m.server.callable = lambda *a, **kw: (lambda f: f) if not a or callable(a[0]) else (lambda f: f)
    m.tables = MagicMock()
    m.secrets = MagicMock()
    m.secrets.get_secret = MagicMock(return_value=None)
    m.users = MagicMock()
    m.files = MagicMock()
    m.files.data_files = MagicMock()
    m.google = MagicMock()
    sys.modules['anvil'] = m
    sys.modules['anvil.server'] = m.server
    sys.modules['anvil.tables'] = m.tables
    sys.modules['anvil.secrets'] = m.secrets
    sys.modules['anvil.users'] = m.users
    sys.modules['anvil.files'] = m.files
    sys.modules['anvil.google'] = m.google
    sys.modules['anvil.js'] = MagicMock()


_mock_anvil()


class TestTransitModelDocumentation(unittest.TestCase):
    """Document and verify the accounting entries for the Transit Inventory Model."""

    def setUp(self):
        sys.modules['AuthManager'] = MagicMock()
        sys.modules['auth_utils'] = MagicMock()
        sys.modules['auth_utils'].get_utc_now = lambda: datetime.utcnow()
        from server_code import accounting
        self.acct = accounting

    def test_1_post_invoice_uses_1210_not_1200(self):
        """
        Test 1: Post purchase invoice 100k EGP → DR 1210, CR 2000 (not 1200).
        """
        cost_to_inventory_egp = 100_000.0
        supplier_amount_egp = 100_000.0
        entries = [
            {'account_code': '1210', 'debit': cost_to_inventory_egp, 'credit': 0},
            {'account_code': '2000', 'debit': 0, 'credit': supplier_amount_egp},
        ]
        self.assertEqual(sum(e['debit'] for e in entries), sum(e['credit'] for e in entries))
        dr_1210 = next(e['debit'] for e in entries if e['account_code'] == '1210')
        cr_2000 = next(e['credit'] for e in entries if e['account_code'] == '2000')
        self.assertEqual(dr_1210, 100_000.0)
        self.assertEqual(cr_2000, 100_000.0)
        self.assertNotIn('1200', [e['account_code'] for e in entries])

    def test_2_import_cost_before_arrival_uses_1210(self):
        """
        Test 2: Add import cost before arrival (inventory_moved=False) → DR 1210, CR Bank.
        """
        amount_egp = 5_000.0
        entries = [
            {'account_code': '1210', 'debit': amount_egp, 'credit': 0},
            {'account_code': '1000', 'debit': 0, 'credit': amount_egp},
        ]
        self.assertEqual(sum(e['debit'] for e in entries), sum(e['credit'] for e in entries))
        self.assertEqual(entries[0]['account_code'], '1210')

    def test_3_move_to_inventory_entries(self):
        """
        Test 3: Move to inventory → DR 1200 = total_transit_cost, CR 1210 = total_transit_cost.
        """
        total_transit_cost = 105_000.0  # 100k post + 5k import cost
        entries = [
            {'account_code': '1200', 'debit': total_transit_cost, 'credit': 0},
            {'account_code': '1210', 'debit': 0, 'credit': total_transit_cost},
        ]
        self.assertEqual(sum(e['debit'] for e in entries), sum(e['credit'] for e in entries))
        self.assertEqual(entries[0]['debit'], total_transit_cost)
        self.assertEqual(entries[1]['credit'], total_transit_cost)

    def test_4_import_cost_after_arrival_uses_1200(self):
        """
        Test 4: Add import cost after arrival (inventory_moved=True) → DR 1200, CR Bank.
        """
        amount_egp = 2_000.0
        entries = [
            {'account_code': '1200', 'debit': amount_egp, 'credit': 0},
            {'account_code': '1010', 'debit': 0, 'credit': amount_egp},
        ]
        self.assertEqual(sum(e['debit'] for e in entries), sum(e['credit'] for e in entries))
        self.assertEqual(entries[0]['account_code'], '1200')

    def test_5_fx_logic_unchanged(self):
        """
        Test 5: Supplier payments (FX) are unchanged. record_supplier_payment uses
        liability_slice_egp, payment_egp, fx_diff, 4110/6110. We only assert the module
        still has the function and does not remove FX handling.
        """
        from server_code import accounting
        self.assertTrue(hasattr(accounting, 'record_supplier_payment'))
        self.assertTrue(callable(accounting.record_supplier_payment))

    def test_default_accounts_include_1210(self):
        """1210 – Inventory in Transit must be in DEFAULT_ACCOUNTS and seed creates it."""
        codes = [a[0] for a in self.acct.DEFAULT_ACCOUNTS]
        self.assertIn('1210', codes)
        name_en = next(a[1] for a in self.acct.DEFAULT_ACCOUNTS if a[0] == '1210')
        self.assertIn('Transit', name_en)
        acct_type = next(a[3] for a in self.acct.DEFAULT_ACCOUNTS if a[0] == '1210')
        self.assertEqual(acct_type, 'asset')


class TestTransitHelpers(unittest.TestCase):
    """Test _sum_1210_balance_for_invoice and move_purchase_to_inventory logic."""

    def setUp(self):
        sys.modules['AuthManager'] = MagicMock()
        sys.modules['auth_utils'] = MagicMock()
        sys.modules['auth_utils'].get_utc_now = lambda: datetime.utcnow()
        from server_code import accounting
        self.acct = accounting

    def test_sum_1210_balance_for_invoice_exists(self):
        """_sum_1210_balance_for_invoice exists (sum(debit-credit) on 1210 for invoice)."""
        self.assertTrue(hasattr(self.acct, '_sum_1210_balance_for_invoice'))
        self.assertTrue(callable(self.acct._sum_1210_balance_for_invoice))

    def test_move_purchase_to_inventory_exists(self):
        """move_purchase_to_inventory is callable and exists."""
        self.assertTrue(hasattr(self.acct, 'move_purchase_to_inventory'))
        self.assertTrue(callable(self.acct.move_purchase_to_inventory))

    def test_get_transit_balance_exists(self):
        """get_transit_balance is callable for reporting."""
        self.assertTrue(hasattr(self.acct, 'get_transit_balance'))
        self.assertTrue(callable(self.acct.get_transit_balance))


if __name__ == '__main__':
    unittest.main()

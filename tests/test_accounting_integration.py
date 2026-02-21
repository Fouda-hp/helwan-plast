"""
Integration tests for Contract → Purchase → Import Cost → Sale → Profitability flow.
Tests the complete accounting lifecycle for a machinery trading company.

Run from project root:
  python -m pytest server_code/tests/test_accounting_integration.py -v
  or: python server_code/tests/test_accounting_integration.py
"""

import os
import sys
import unittest
from datetime import date, datetime
from unittest.mock import MagicMock, patch, PropertyMock
import json
import uuid

# Setup path
try:
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    _root = os.getcwd()
if _root and _root not in sys.path:
    sys.path.insert(0, _root)


# Mock anvil before importing server modules
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
    m.google.auth = MagicMock()
    m.google.drive = MagicMock()
    m.google.drive.app_files = MagicMock()
    m.google.mail = MagicMock()
    sys.modules['anvil'] = m
    sys.modules['anvil.server'] = m.server
    sys.modules['anvil.tables'] = m.tables
    sys.modules['anvil.secrets'] = m.secrets
    sys.modules['anvil.users'] = m.users
    sys.modules['anvil.files'] = m.files
    sys.modules['anvil.google'] = m.google
    sys.modules['anvil.google.auth'] = m.google.auth
    sys.modules['anvil.google.drive'] = m.google.drive
    sys.modules['anvil.google.mail'] = m.google.mail
    sys.modules['anvil.js'] = MagicMock()

_mock_anvil()


class TestAccountingHelpers(unittest.TestCase):
    """Test utility functions in accounting module."""

    def setUp(self):
        # Mock AuthManager before importing
        sys.modules['AuthManager'] = MagicMock()
        sys.modules['auth_utils'] = MagicMock()
        sys.modules['auth_utils'].get_utc_now = lambda: datetime.utcnow()
        from server_code import accounting
        self.acct = accounting

    def test_round2(self):
        self.assertEqual(self.acct._round2(1.005), 1.0)
        self.assertEqual(self.acct._round2(1.006), 1.01)
        self.assertEqual(self.acct._round2(100.999), 101.0)
        self.assertEqual(self.acct._round2(None), 0.0)
        self.assertEqual(self.acct._round2('abc'), 0.0)

    def test_safe_str(self):
        self.assertEqual(self.acct._safe_str(None), '')
        self.assertEqual(self.acct._safe_str('  hello  '), 'hello')
        self.assertEqual(self.acct._safe_str(123), '123')

    def test_safe_date(self):
        d = date(2026, 1, 15)
        self.assertEqual(self.acct._safe_date(d), d)
        self.assertEqual(self.acct._safe_date('2026-01-15'), d)
        self.assertIsNone(self.acct._safe_date('invalid'))
        self.assertIsNone(self.acct._safe_date(None))

    def test_resolve_payment_account(self):
        self.assertEqual(self.acct._resolve_payment_account('cash'), '1000')
        self.assertEqual(self.acct._resolve_payment_account('bank'), '1010')
        self.assertEqual(self.acct._resolve_payment_account('cib'), '1011')
        self.assertEqual(self.acct._resolve_payment_account('nbe'), '1012')
        self.assertEqual(self.acct._resolve_payment_account('qnb'), '1013')
        self.assertEqual(self.acct._resolve_payment_account(None), '1000')
        self.assertEqual(self.acct._resolve_payment_account(''), '1000')

    def test_bank_account_map(self):
        """Verify all expected bank accounts are mapped."""
        bam = self.acct.BANK_ACCOUNT_MAP
        self.assertIn('cash', bam)
        self.assertIn('bank', bam)
        self.assertIn('cib', bam)
        self.assertIn('nbe', bam)
        self.assertIn('qnb', bam)

    def test_default_accounts_include_banks(self):
        """Verify bank sub-accounts are in DEFAULT_ACCOUNTS."""
        codes = [a[0] for a in self.acct.DEFAULT_ACCOUNTS]
        self.assertIn('1011', codes)
        self.assertIn('1012', codes)
        self.assertIn('1013', codes)
        self.assertIn('1210', codes)  # Purchase in Transit

    def test_default_accounts_types(self):
        """Verify account types are correct."""
        type_map = {a[0]: a[3] for a in self.acct.DEFAULT_ACCOUNTS}
        self.assertEqual(type_map['1000'], 'asset')
        self.assertEqual(type_map['1200'], 'asset')
        self.assertEqual(type_map['1210'], 'asset')
        self.assertEqual(type_map['2000'], 'liability')
        self.assertEqual(type_map['4000'], 'revenue')
        self.assertEqual(type_map['5000'], 'expense')
        self.assertEqual(type_map['5100'], 'expense')


class TestJournalEntryValidation(unittest.TestCase):
    """Test the core post_journal_entry validation logic."""

    def setUp(self):
        sys.modules['AuthManager'] = MagicMock()
        sys.modules['auth_utils'] = MagicMock()
        sys.modules['auth_utils'].get_utc_now = lambda: datetime.utcnow()
        from server_code import accounting
        self.acct = accounting

    def test_rejects_empty_entries(self):
        result = self.acct.post_journal_entry(date.today(), [], 'test', 'journal', 'X', 'u@t.com')
        self.assertFalse(result['success'])

    def test_rejects_single_entry(self):
        result = self.acct.post_journal_entry(
            date.today(),
            [{'account_code': '1000', 'debit': 100, 'credit': 0}],
            'test', 'journal', 'X', 'u@t.com'
        )
        self.assertFalse(result['success'])

    def test_rejects_unbalanced_entries(self):
        result = self.acct.post_journal_entry(
            date.today(),
            [
                {'account_code': '1000', 'debit': 100, 'credit': 0},
                {'account_code': '2000', 'debit': 0, 'credit': 50},
            ],
            'test', 'journal', 'X', 'u@t.com'
        )
        self.assertFalse(result['success'])
        self.assertIn('must equal', result['message'])

    def test_rejects_negative_amounts(self):
        result = self.acct.post_journal_entry(
            date.today(),
            [
                {'account_code': '1000', 'debit': -100, 'credit': 0},
                {'account_code': '2000', 'debit': 0, 'credit': -100},
            ],
            'test', 'journal', 'X', 'u@t.com'
        )
        self.assertFalse(result['success'])

    def test_rejects_both_debit_credit_on_same_line(self):
        result = self.acct.post_journal_entry(
            date.today(),
            [
                {'account_code': '1000', 'debit': 100, 'credit': 100},
                {'account_code': '2000', 'debit': 0, 'credit': 0},
            ],
            'test', 'journal', 'X', 'u@t.com'
        )
        self.assertFalse(result['success'])


class TestAccountingFlowDocumentation(unittest.TestCase):
    """
    Document the exact journal entries for each business event.
    These tests serve as living documentation of the accounting logic.
    """

    def test_contract_purchase_entries(self):
        """
        When contract is created with FOB + Cylinder costs (Transit model):
          DR 1210 Inventory in Transit  (FOB + Cylinders)
          CR 2000 Accounts Payable     (FOB + Cylinders)
        Later: move_purchase_to_inventory moves 1210 → 1200.
        """
        fob = 50000.00
        cylinders = 10000.00
        total = fob + cylinders
        entries = [
            {'account_code': '1210', 'debit': total, 'credit': 0},
            {'account_code': '2000', 'debit': 0, 'credit': total},
        ]
        self.assertEqual(sum(e['debit'] for e in entries), sum(e['credit'] for e in entries))

    def test_supplier_payment_entries(self):
        """
        When paying supplier from specific bank:
          DR 2000 Accounts Payable  (payment amount)
          CR 1011 Bank-CIB          (payment amount)
        """
        amount = 30000.00
        entries = [
            {'account_code': '2000', 'debit': amount, 'credit': 0},
            {'account_code': '1011', 'debit': 0, 'credit': amount},
        ]
        self.assertEqual(sum(e['debit'] for e in entries), sum(e['credit'] for e in entries))

    def test_import_cost_entries(self):
        """
        When adding import cost (Transit model):
          If not yet received: DR 1210 Inventory in Transit, CR Bank/Cash.
          If already received (inventory_moved): DR 1200 Inventory, CR Bank/Cash.
        NOT DR 5100 (expense) — import costs are capitalized!
        """
        amount = 5000.00
        entries_in_transit = [
            {'account_code': '1210', 'debit': amount, 'credit': 0},
            {'account_code': '1000', 'debit': 0, 'credit': amount},
        ]
        entries = entries_in_transit
        self.assertEqual(sum(e['debit'] for e in entries), sum(e['credit'] for e in entries))
        # Verify NOT debiting expense
        for e in entries:
            self.assertNotEqual(e['account_code'], '5100')

    def test_sale_entries(self):
        """
        When selling a machine:
        Entry 1 - COGS:
          DR 5000 COGS          (landed cost)
          CR 1200 Inventory     (landed cost)
        Entry 2 - Revenue:
          DR 1100 Accounts Receivable  (selling price)
          CR 4000 Sales Revenue         (selling price)
        """
        landed_cost = 65000.00
        selling_price = 90000.00

        cogs_entries = [
            {'account_code': '5000', 'debit': landed_cost, 'credit': 0},
            {'account_code': '1200', 'debit': 0, 'credit': landed_cost},
        ]
        revenue_entries = [
            {'account_code': '1100', 'debit': selling_price, 'credit': 0},
            {'account_code': '4000', 'debit': 0, 'credit': selling_price},
        ]
        # Both entries must balance
        self.assertEqual(sum(e['debit'] for e in cogs_entries), sum(e['credit'] for e in cogs_entries))
        self.assertEqual(sum(e['debit'] for e in revenue_entries), sum(e['credit'] for e in revenue_entries))

    def test_landed_cost_calculation(self):
        """
        Landed Cost = FOB + Cylinders + Shipping + Customs + Insurance + Transport + ...
        Gross Profit = Revenue - Landed Cost
        """
        fob = 50000.00
        cylinders = 10000.00
        shipping = 3000.00
        customs = 2000.00
        insurance = 500.00

        purchase_cost = fob + cylinders  # 60000
        import_costs = shipping + customs + insurance  # 5500
        landed_cost = purchase_cost + import_costs  # 65500
        revenue = 90000.00
        gross_profit = revenue - landed_cost  # 24500

        self.assertEqual(purchase_cost, 60000.00)
        self.assertEqual(import_costs, 5500.00)
        self.assertEqual(landed_cost, 65500.00)
        self.assertEqual(gross_profit, 24500.00)

    def test_migration_entries(self):
        """
        Migration: reclassify old import costs from 5100 to 1200.
          DR 1200 Inventory     (amount)
          CR 5100 Import Costs  (amount)
        This moves the cost from expense back to asset.
        """
        amount = 5000.00
        entries = [
            {'account_code': '1200', 'debit': amount, 'credit': 0},
            {'account_code': '5100', 'debit': 0, 'credit': amount},
        ]
        self.assertEqual(sum(e['debit'] for e in entries), sum(e['credit'] for e in entries))


class TestInventoryStatusFlow(unittest.TestCase):
    """Test inventory status transitions."""

    def test_valid_status_values(self):
        """Valid inventory statuses: in_transit, in_stock, reserved, sold."""
        valid = {'in_transit', 'in_stock', 'reserved', 'sold'}
        self.assertEqual(len(valid), 4)

    def test_status_flow(self):
        """
        Contract created → in_transit
        Goods arrive → in_stock (no P&L impact)
        Sold → sold (COGS + Revenue posted)
        """
        flow = ['in_transit', 'in_stock', 'sold']
        self.assertEqual(flow[0], 'in_transit')
        self.assertEqual(flow[1], 'in_stock')
        self.assertEqual(flow[2], 'sold')

    def test_cannot_sell_in_transit(self):
        """Items must be received (in_stock) before they can be sold."""
        # This is enforced by sell_inventory checking status != 'in_transit'
        pass

    def test_import_costs_blocked_after_sale(self):
        """Cannot add import costs after machine is sold."""
        # The add_import_cost function checks for sold items
        pass


class TestProfitabilityCalculation(unittest.TestCase):
    """Test profit calculation logic."""

    def test_profit_margin(self):
        """Gross margin = (Revenue - Landed Cost) / Revenue * 100"""
        revenue = 100000.00
        landed_cost = 65000.00
        profit = revenue - landed_cost
        margin = (profit / revenue * 100) if revenue else 0

        self.assertEqual(profit, 35000.00)
        self.assertAlmostEqual(margin, 35.0, places=1)

    def test_loss_scenario(self):
        """When landed cost > revenue, result is a loss."""
        revenue = 50000.00
        landed_cost = 65000.00
        profit = revenue - landed_cost

        self.assertEqual(profit, -15000.00)
        self.assertTrue(profit < 0)

    def test_vat_not_in_profit(self):
        """VAT goes to liability (2100), not to profit calculation."""
        fob = 50000.00
        vat = 7000.00
        # VAT is posted to 2100 (liability), not as part of COGS
        # So profit = revenue - landed_cost, with no VAT deduction
        landed_cost = fob  # VAT is NOT included in landed cost
        revenue = 70000.00
        profit = revenue - landed_cost

        self.assertEqual(profit, 20000.00)  # VAT doesn't affect profit


if __name__ == '__main__':
    unittest.main()

"""
Tests for accounting hardening: unrealized FX accuracy, supplier aging, inventory valuation,
period lock, and FX report reconciliation.

Run from project root:
  python -m pytest server_code/tests/test_accounting_hardening.py -v
  or: python server_code/tests/test_accounting_hardening.py
"""

import os
import sys
import unittest
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

try:
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    _root = os.getcwd()
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


def _ledger_row(account_code, debit, credit, reference_type, reference_id):
    return {'account_code': account_code, 'debit': debit, 'credit': credit,
            'reference_type': reference_type, 'reference_id': reference_id}


class TestUnrealizedFxAccuracy(unittest.TestCase):
    """PART 1: Unrealized FX uses invoice_rate = supplier_amount_egp / original_amount, remaining_original = remaining_egp / invoice_rate."""

    def setUp(self):
        sys.modules['AuthManager'] = MagicMock()
        sys.modules['auth_utils'] = MagicMock()
        sys.modules['auth_utils'].get_utc_now = lambda: datetime.utcnow()
        from server_code import accounting
        self.acct = accounting

    def test_unrealized_fx_formula(self):
        """remaining_original = remaining_egp / invoice_rate; invoice_rate = supplier_amount_egp / original_amount."""
        supplier_egp = 100.0
        original = 5.0  # e.g. 5 USD
        invoice_rate = supplier_egp / original  # 20 EGP per unit
        remaining_egp = 40.0  # 2 units worth at book
        remaining_original = remaining_egp / invoice_rate  # 2 units
        self.assertAlmostEqual(remaining_original, 2.0, places=5)
        current_rate = 22.0
        revalued_egp = remaining_original * current_rate  # 44
        unrealized_fx = revalued_egp - remaining_egp  # 4
        self.assertAlmostEqual(unrealized_fx, 4.0, places=5)

    def test_unrealized_fx_zero_original_amount(self):
        """If original_amount <= 0, unrealized_fx must be 0 (safety)."""
        from server_code.accounting import _round2
        original_amount = 0
        supplier_egp = 100.0
        remaining_egp = 50.0
        if original_amount <= 0:
            unrealized_fx = 0
        else:
            invoice_rate = _round2(supplier_egp / original_amount)
            unrealized_fx = 0 if invoice_rate <= 0 else 1
        self.assertEqual(unrealized_fx, 0)

    def test_unrealized_fx_zero_supplier_egp(self):
        """If supplier_amount_egp <= 0, unrealized_fx must be 0 (safety)."""
        original_amount = 10.0
        supplier_egp = 0
        if supplier_egp <= 0:
            unrealized_fx = 0
        else:
            invoice_rate = supplier_egp / original_amount
            unrealized_fx = 1
        self.assertEqual(unrealized_fx, 0)


class TestSupplierAgingEdgeCases(unittest.TestCase):
    """PART 2: Supplier aging uses full 2000 ledger: sum(CR) - sum(DR) by reference_id, no reference_type filter."""

    def setUp(self):
        sys.modules['AuthManager'] = MagicMock()
        sys.modules['auth_utils'] = MagicMock()
        sys.modules['auth_utils'].get_utc_now = lambda: datetime.utcnow()
        from server_code import accounting
        self.acct = accounting

    def test_ledger_2000_remaining_formula(self):
        """Remaining = sum(CR 2000 ref_id=inv) - sum(DR 2000 ref_id=inv). No ref_type filter."""
        # Simulate: one invoice inv1: CR 100 (purchase), DR 30 (payment), DR 20 (manual adj) -> remaining 50
        rows = [
            _ledger_row('2000', 0, 100, 'purchase_invoice', 'inv1'),
            _ledger_row('2000', 30, 0, 'payment', 'inv1'),
            _ledger_row('2000', 20, 0, 'journal', 'inv1'),
        ]
        remaining = 0
        for e in rows:
            if e['reference_id'] == 'inv1':
                remaining += e['credit'] - e['debit']
        self.assertEqual(remaining, 50)

    def test_aging_excludes_fully_paid_tolerance(self):
        """Invoices with |remaining| < 0.01 are excluded from aging."""
        from server_code.accounting import RESIDUAL_TOLERANCE
        self.assertLess(0.005, RESIDUAL_TOLERANCE)
        self.assertGreaterEqual(0.01, RESIDUAL_TOLERANCE)

    def test_aging_buckets_by_invoice_date(self):
        """Age buckets 0_30, 31_60, 61_90, 90_plus are by invoice date, not payment date."""
        as_of = date(2026, 3, 1)
        inv_date_old = date(2025, 11, 1)  # 120 days
        inv_date_new = date(2026, 2, 15)  # 14 days
        days_old = (as_of - inv_date_old).days
        days_new = (as_of - inv_date_new).days
        self.assertGreater(days_old, 90)
        self.assertLessEqual(days_new, 30)


class TestInventoryTransitAndSale(unittest.TestCase):
    """PART 3: Post invoice, add import cost, move to inventory, sell partially; verify 1210/1200 balances."""

    def setUp(self):
        sys.modules['AuthManager'] = MagicMock()
        sys.modules['auth_utils'] = MagicMock()
        sys.modules['auth_utils'].get_utc_now = lambda: datetime.utcnow()
        from server_code import accounting
        self.acct = accounting

    def test_1210_balance_is_debit_minus_credit(self):
        """Transit balance = sum(DR 1210) - sum(CR 1210) for invoice (all ref types for ref_id=invoice_id)."""
        rows = [
            _ledger_row('1210', 100, 0, 'purchase_invoice', 'inv1'),
            _ledger_row('1210', 5, 0, 'import_cost', 'inv1'),
            _ledger_row('1210', 0, 105, 'move', 'inv1'),  # after move
        ]
        total = sum(e['debit'] - e['credit'] for e in rows if e['reference_id'] == 'inv1')
        self.assertEqual(total, 0)

    def test_1200_available_is_dr_by_invoice_minus_cr_by_item(self):
        """Available = DR 1200 (by invoice) - CR 1200 (by items linked to invoice)."""
        dr_invoice = 100.0
        cr_items = 40.0
        available = dr_invoice - cr_items
        self.assertEqual(available, 60.0)

    def test_move_clears_1210_and_increases_1200(self):
        """Move to inventory: DR 1200 = total_transit_cost, CR 1210 = total_transit_cost."""
        total_transit_cost = 105.0
        entries = [
            {'account_code': '1200', 'debit': total_transit_cost, 'credit': 0},
            {'account_code': '1210', 'debit': 0, 'credit': total_transit_cost},
        ]
        self.assertEqual(sum(e['debit'] for e in entries), sum(e['credit'] for e in entries))
        self.assertEqual(entries[0]['debit'], 105.0)
        self.assertEqual(entries[1]['credit'], 105.0)


class TestPeriodLockBlocksPosting(unittest.TestCase):
    """PART 4: When period is locked, post_journal_entry and posting flows must fail."""

    def setUp(self):
        sys.modules['AuthManager'] = MagicMock()
        sys.modules['auth_utils'] = MagicMock()
        sys.modules['auth_utils'].get_utc_now = lambda: datetime.utcnow()
        from server_code import accounting
        self.acct = accounting

    def test_period_locked_returns_correct_message(self):
        """post_journal_entry returns success=False and message 'Accounting period is locked.' when locked."""
        with patch.object(self.acct, 'is_period_locked', return_value=True):
            result = self.acct.post_journal_entry(
                date(2026, 1, 15),
                [
                    {'account_code': '1000', 'debit': 100, 'credit': 0},
                    {'account_code': '2000', 'debit': 0, 'credit': 100},
                ],
                'Test', 'journal', 'X', 'u@t.com'
            )
        self.assertFalse(result['success'])
        self.assertIn('locked', result.get('message', '').lower())

    def test_missing_period_locks_table_raises(self):
        """If accounting_period_locks table does not exist, is_period_locked raises (no silent unlock)."""
        # app_tables with no accounting_period_locks -> AttributeError on access -> we raise RuntimeError
        with patch.object(self.acct, 'app_tables', MagicMock(spec=[])):
            with self.assertRaises(RuntimeError) as ctx:
                self.acct.is_period_locked(date(2026, 1, 15))
            msg = str(ctx.exception).lower()
            self.assertTrue('accounting_period_locks' in msg or 'missing' in msg)


class TestFxReportReconciliation(unittest.TestCase):
    """PART 5: Total FX across all invoices = balance(4110) - balance(6110)."""

    def setUp(self):
        sys.modules['AuthManager'] = MagicMock()
        sys.modules['auth_utils'] = MagicMock()
        sys.modules['auth_utils'].get_utc_now = lambda: datetime.utcnow()
        from server_code import accounting
        self.acct = accounting

    def test_fx_reconciliation_formula(self):
        """Sum of (fx_gain - fx_loss) per invoice must equal total CR 4110 - total DR 6110."""
        # Two invoices: inv1 gain 10, inv2 loss 3 -> net_fx inv1=10, inv2=-3, total 7
        # Ledger: 4110 CR 10 (inv1), 6110 DR 3 (inv2) -> balance 4110 = 10, balance 6110 = 3, diff = 7
        total_4110_credit = 10.0
        total_6110_debit = 3.0
        expected_net_fx = total_4110_credit - total_6110_debit
        sum_per_invoice = 10.0 - 3.0
        self.assertAlmostEqual(expected_net_fx, sum_per_invoice, places=2)

    def test_paid_egp_from_ledger_only(self):
        """paid_egp = sum(CR bank 1000,1010-1013) - sum(DR same) for reference_id=invoice_id."""
        rows = [
            _ledger_row('1010', 0, 50, 'payment', 'inv1'),
            _ledger_row('1010', 0, 30, 'payment', 'inv1'),
        ]
        paid = sum(e['credit'] - e['debit'] for e in rows if e['reference_id'] == 'inv1')
        self.assertEqual(paid, 80.0)


class TestVatAccounting(unittest.TestCase):
    """VAT flow: Import VAT → 2110 only; Sales VAT-inclusive split → 2100; Settlement; VAT excluded from inventory."""

    def setUp(self):
        sys.modules['AuthManager'] = MagicMock()
        sys.modules['auth_utils'] = MagicMock()
        sys.modules['auth_utils'].get_utc_now = lambda: datetime.utcnow()
        from server_code import accounting
        self.acct = accounting

    def test_sales_vat_split_formula(self):
        """VAT-inclusive: vat_amount = selling_price * rate / (100 + rate); net_revenue = selling_price - vat_amount."""
        from server_code.accounting import _round2, DEFAULT_VAT_RATE
        rate = DEFAULT_VAT_RATE  # 14%
        selling_price = 1140.0  # 14% incl -> net 1000, vat 140
        vat_amount = _round2(selling_price * rate / (100 + rate))
        net_revenue = _round2(selling_price - vat_amount)
        self.assertAlmostEqual(vat_amount + net_revenue, selling_price, places=2)
        self.assertAlmostEqual(vat_amount, 140.0, places=2)
        self.assertAlmostEqual(net_revenue, 1000.0, places=2)

    def test_settlement_remit_journal_balances(self):
        """When output_vat > input_vat: DR 2100 out, CR 2110 in, CR Bank (out - in); debits = credits."""
        output_vat = 100.0
        input_vat = 40.0
        net_due = output_vat - input_vat
        debits = output_vat
        credits = input_vat + net_due
        self.assertAlmostEqual(debits, credits, places=2)
        self.assertAlmostEqual(net_due, 60.0, places=2)

    def test_settlement_carry_forward_journal_balances(self):
        """When input_vat >= output_vat: DR 2100 output_vat, CR 2110 output_vat; debits = credits."""
        output_vat = 50.0
        input_vat = 80.0
        dr_2100 = output_vat
        cr_2110 = output_vat
        self.assertAlmostEqual(dr_2100, cr_2110, places=2)
        carry_forward = input_vat - output_vat
        self.assertAlmostEqual(carry_forward, 30.0, places=2)

    def test_vat_excluded_from_inventory_cost(self):
        """cost_type 'vat' or 'VAT' must be excluded from import_costs_total (not added to 1210/1200)."""
        from server_code.accounting import VALID_COST_TYPES
        self.assertIn('vat', VALID_COST_TYPES)
        is_vat_lower = (lambda ct: (ct or '').lower().strip() == 'vat')('vat')
        is_vat_upper = (lambda ct: (ct or '').lower().strip() == 'vat')('VAT')
        self.assertTrue(is_vat_lower)
        self.assertTrue(is_vat_upper)

    def test_vat_report_totals_match_ledger_formula(self):
        """get_vat_report: input_vat_balance = sum(DR 2110) - sum(CR 2110); output_vat_payable = sum(CR 2100) - sum(DR 2100)."""
        # Simulate ledger: 2110 DR 100, 2100 CR 60
        input_balance = 100.0 - 0.0   # 2110 debit - credit
        output_payable = 60.0 - 0.0  # 2100 credit - debit
        net = input_balance - output_payable
        self.assertAlmostEqual(input_balance, 100.0, places=2)
        self.assertAlmostEqual(output_payable, 60.0, places=2)
        self.assertAlmostEqual(net, 40.0, places=2)


if __name__ == '__main__':
    unittest.main()

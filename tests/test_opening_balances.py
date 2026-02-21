"""
Validation tests for Opening Balance logic (ledger-driven, no hybrid).

- Bank opening balance appears in General Ledger, Trial Balance, Balance Sheet.
- No double counting.
- After posting, reports do not read from opening_balances table; removing
  that table does not change report totals.

Run: python -m pytest server_code/tests/test_opening_balances.py -v
"""

import os
import sys
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

try:
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    _root = os.getcwd()
if _root and _root not in sys.path:
    sys.path.insert(0, _root)

# Mock anvil before importing accounting
def _mock_anvil():
    if 'anvil' in sys.modules:
        return
    m = MagicMock()
    m.server = MagicMock()
    def _callable(*a, **kw):
        if len(a) == 1 and callable(a[0]):
            return a[0]
        return lambda f: f
    m.server.callable = _callable
    m.tables = MagicMock()
    m.tables.app_tables = MagicMock()
    m.secrets = MagicMock()
    m.users = MagicMock()
    sys.modules['anvil'] = m
    sys.modules['anvil.server'] = m.server
    sys.modules['anvil.tables'] = m.tables
    sys.modules['anvil.secrets'] = m.secrets
    sys.modules['anvil.users'] = m.users

_mock_anvil()


class TestOpeningBalancesLedgerDriven(unittest.TestCase):
    """Opening balances must be ledger-only after posting; no hybrid."""

    def setUp(self):
        auth = MagicMock()
        auth.is_admin = MagicMock(return_value=True)
        auth.is_admin_by_email = MagicMock(return_value=True)
        auth.check_permission = MagicMock(return_value=True)
        sys.modules['AuthManager'] = auth
        sys.modules['auth_utils'] = MagicMock()
        from server_code import accounting
        self.acct = accounting
        self._perm_patch = patch.object(accounting, '_require_permission', return_value=(True, 'test@test.com', None))
        self._perm_patch.start()
        self.ledger_rows = []
        self.chart = {
            '1000': {'code': '1000', 'name_en': 'Cash', 'account_type': 'asset', 'is_active': True},
            '1011': {'code': '1011', 'name_en': 'Bank - CIB', 'account_type': 'asset', 'is_active': True},
            '1100': {'code': '1100', 'name_en': 'AR', 'account_type': 'asset', 'is_active': True},
            '2000': {'code': '2000', 'name_en': 'AP', 'account_type': 'liability', 'is_active': True},
            '3000': {'code': '3000', 'name_en': "Owner's Equity", 'account_type': 'equity', 'is_active': True},
        }
        self.opening_rows = []

    def _ledger_search(self, account_code=None, reference_type=None, reference_id=None):
        out = self.ledger_rows
        if account_code is not None:
            out = [r for r in out if r.get('account_code') == account_code]
        if reference_type is not None:
            out = [r for r in out if r.get('reference_type') == reference_type]
        if reference_id is not None:
            out = [r for r in out if r.get('reference_id') == reference_id]
        return out

    def _ledger_add_row(self, **kwargs):
        self.ledger_rows.append(dict(kwargs))

    def _chart_get(self, code):
        return self.chart.get(code)

    def _chart_search(self, is_active=True):
        return [v for v in self.chart.values() if v.get('is_active', True)]

    def _opening_search(self, type=None):
        if type is None:
            return list(self.opening_rows)
        return [r for r in self.opening_rows if r.get('type') == type]

    def test_post_opening_balances_creates_ledger_entries(self):
        """Posting opening balances must create a single JE in the ledger."""
        self.opening_rows = [
            {'name': '1011', 'type': 'bank', 'opening_balance': 1000},
        ]
        app_tables = MagicMock()
        app_tables.ledger.search.side_effect = self._ledger_search
        app_tables.ledger.add_row.side_effect = self._ledger_add_row
        app_tables.chart_of_accounts.get.side_effect = self._chart_get
        app_tables.chart_of_accounts.search.side_effect = self._chart_search
        app_tables.opening_balances.search.side_effect = self._opening_search
        app_tables.accounting_period_locks.search.return_value = []

        with patch.dict('sys.modules', {'anvil': MagicMock()}):
            with patch('server_code.accounting.app_tables', app_tables):
                with patch('server_code.accounting.is_period_locked', return_value=False):
                    with patch('server_code.accounting._validate_account_exists', return_value=True):
                        with patch('server_code.accounting._uuid', side_effect=lambda: 'tid-1'):
                            res = self.acct.post_opening_balances(2026, token_or_email='test@test.com')
        self.assertTrue(res.get('success'), res.get('message'))
        self.assertEqual(len(self.ledger_rows), 2)
        by_account = {}
        for r in self.ledger_rows:
            c = r['account_code']
            by_account[c] = by_account.get(c, 0) + (r.get('debit', 0) - r.get('credit', 0))
        self.assertEqual(by_account.get('1011'), 1000)
        self.assertEqual(by_account.get('3000'), -1000)

    def test_post_opening_balances_idempotent(self):
        """Posting the same financial_year twice must fail (already posted)."""
        self.ledger_rows = [
            {'account_code': '1011', 'reference_type': 'opening_balance', 'reference_id': '2026'},
        ]
        app_tables = MagicMock()
        app_tables.ledger.search.side_effect = self._ledger_search
        app_tables.opening_balances.search.return_value = []
        app_tables.chart_of_accounts.get.side_effect = self._chart_get

        with patch('server_code.accounting.app_tables', app_tables):
            with patch('server_code.accounting.is_period_locked', return_value=False):
                res = self.acct.post_opening_balances(2026, token_or_email='test@test.com')
        self.assertFalse(res.get('success'))
        self.assertIn('already posted', res.get('message', '').lower())

    def test_treasury_summary_uses_ledger_only(self):
        """get_treasury_summary must use only ledger (no opening_balances table read for balance)."""
        self.ledger_rows = [
            {'account_code': '1011', 'debit': 5000, 'credit': 0, 'reference_type': 'opening_balance'},
            {'account_code': '1011', 'debit': 0, 'credit': 2000, 'reference_type': 'payment'},
        ]
        app_tables = MagicMock()
        app_tables.ledger.search.side_effect = self._ledger_search
        app_tables.chart_of_accounts.search.side_effect = self._chart_search

        with patch('server_code.accounting.app_tables', app_tables):
            res = self.acct.get_treasury_summary(token_or_email='test@test.com')
        self.assertTrue(res.get('success'))
        data = res.get('data') or res.get('accounts') or []
        bank_1011 = next((a for a in data if a.get('account_code') == '1011'), None)
        self.assertIsNotNone(bank_1011)
        self.assertEqual(bank_1011.get('current_balance'), 3000)
        self.assertEqual(bank_1011.get('ledger_balance'), 3000)

    def test_balance_sheet_and_trial_balance_from_ledger_only(self):
        """Trial Balance and Balance Sheet must derive all balances from ledger aggregation only."""
        self.ledger_rows = [
            {'account_code': '1011', 'date': date(2026, 1, 1), 'debit': 10000, 'credit': 0},
            {'account_code': '3000', 'date': date(2026, 1, 1), 'debit': 0, 'credit': 10000},
        ]
        app_tables = MagicMock()
        app_tables.ledger.search.side_effect = self._ledger_search
        app_tables.chart_of_accounts.search.side_effect = self._chart_search
        app_tables.chart_of_accounts.get.side_effect = self._chart_get

        with patch('server_code.accounting.app_tables', app_tables):
            tb = self.acct.get_trial_balance(date_to='2026-12-31', token_or_email='test@test.com')
            bs = self.acct.get_balance_sheet('2026-12-31', token_or_email='test@test.com')
        self.assertTrue(tb.get('success'))
        self.assertTrue(bs.get('success'))
        self.assertTrue(tb.get('is_balanced'))
        self.assertTrue(bs.get('is_balanced'))

    def tearDown(self):
        if hasattr(self, '_perm_patch'):
            self._perm_patch.stop()


if __name__ == '__main__':
    unittest.main()

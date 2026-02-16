"""
Tests for Treasury transactions, internal transfers validation, and period locking.

Run from project root:
  python -m pytest server_code/tests/test_treasury_period.py -v
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


def _mock_anvil():
    if 'anvil' in sys.modules:
        return
    m = MagicMock()
    m.server = MagicMock()
    def _callable(*args):
        if len(args) == 1 and callable(args[0]):
            return args[0]  # @callable def f
        return lambda f: f   # @callable("name") def f
    m.server.callable = _callable
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
    sys.modules['anvil.js'] = MagicMock()

_mock_anvil()


class TestTreasuryValidation(unittest.TestCase):
    """Treasury: same account, insufficient balance, period lock."""

    def setUp(self):
        sys.modules['AuthManager'] = MagicMock()
        sys.modules['auth_utils'] = MagicMock()
        from datetime import datetime
        sys.modules['auth_utils'].get_utc_now = lambda: datetime.utcnow()
        from server_code import accounting
        self.acct = accounting

    def test_internal_transfer_same_account_rejected(self):
        """From and To cannot be the same for internal_transfer."""
        with patch.object(self.acct, '_require_permission', return_value=(True, 'u@x.com', None)):
            with patch.object(self.acct, '_validate_account_exists', return_value=True):
                res = self.acct.create_treasury_transaction(
                    'internal_transfer', 100, '2026-01-15', 'Test',
                    from_account='1000', to_account='1000', token_or_email='token',
                )
        self.assertFalse(res['success'])
        self.assertIn('same', res['message'].lower())

    def test_internal_transfer_insufficient_balance_rejected(self):
        """Internal transfer fails when from-account balance < amount."""
        with patch.object(self.acct, '_require_permission', return_value=(True, 'u@x.com', None)):
            with patch.object(self.acct, '_validate_account_exists', return_value=True):
                with patch.object(self.acct, '_get_account_balance_internal', return_value=50.0):
                    with patch.object(self.acct, '_is_cash_or_bank_account', return_value=True):
                        res = self.acct.create_treasury_transaction(
                            'internal_transfer', 100, '2026-01-15', 'Test',
                            from_account='1000', to_account='1010', token_or_email='token',
                        )
        self.assertFalse(res['success'])
        self.assertIn('Insufficient', res['message'])

    def test_period_locked_treasury_rejected(self):
        """create_treasury_transaction fails when period is locked for transaction date."""
        with patch.object(self.acct, '_require_permission', return_value=(True, 'u@x.com', None)):
            with patch.object(self.acct, 'is_period_locked', return_value=True):
                res = self.acct.create_treasury_transaction(
                    'capital_injection', 100, '2026-01-15', 'Test',
                    to_account='1000', token_or_email='token',
                )
        self.assertFalse(res['success'])
        self.assertIn('locked', res['message'].lower())

    def test_invalid_transaction_type_rejected(self):
        """Invalid transaction_type returns error."""
        with patch.object(self.acct, '_require_permission', return_value=(True, 'u@x.com', None)):
            res = self.acct.create_treasury_transaction(
                'invalid_type', 100, '2026-01-15', 'Test', token_or_email='token',
            )
        self.assertFalse(res['success'])
        self.assertIn('Invalid', res['message'])


class TestPeriodLock(unittest.TestCase):
    """Period close/reopen and get_period_locks."""

    def setUp(self):
        sys.modules['AuthManager'] = MagicMock()
        sys.modules['auth_utils'] = MagicMock()
        from datetime import datetime
        sys.modules['auth_utils'].get_utc_now = lambda: datetime.utcnow()
        from server_code import accounting
        self.acct = accounting

    def test_close_period_requires_permission(self):
        """close_period returns error when permission denied."""
        with patch.object(self.acct, '_require_permission', return_value=(False, None, {'success': False, 'message': 'Forbidden'})):
            res = self.acct.close_period(2026, 1, 'bad_token')
        self.assertFalse(res['success'])

    def test_get_period_locks_requires_permission(self):
        """get_period_locks returns error when permission denied."""
        with patch.object(self.acct, '_require_permission', return_value=(False, None, {'success': False, 'message': 'Forbidden'})):
            res = self.acct.get_period_locks(2026, 'bad_token')
        self.assertFalse(res['success'])


class TestPostJournalEntryPeriodLock(unittest.TestCase):
    """post_journal_entry rejects posting when period is locked."""

    def setUp(self):
        sys.modules['AuthManager'] = MagicMock()
        sys.modules['auth_utils'] = MagicMock()
        from datetime import datetime
        sys.modules['auth_utils'].get_utc_now = lambda: datetime.utcnow()
        from server_code import accounting
        self.acct = accounting

    def test_posting_rejected_when_period_locked(self):
        """When is_period_locked(entry_date) is True, post_journal_entry returns error."""
        with patch.object(self.acct, 'is_period_locked', return_value=True):
            res = self.acct.post_journal_entry(
                date(2026, 1, 15),
                [
                    {'account_code': '1000', 'debit': 100, 'credit': 0},
                    {'account_code': '2000', 'debit': 0, 'credit': 100},
                ],
                'Test', 'journal', 'X', 'u@x.com',
            )
        self.assertFalse(res['success'])
        self.assertIn('locked', res['message'].lower())

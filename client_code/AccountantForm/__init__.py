"""
AccountantForm - Main Accounting Dashboard
===========================================
- Trial Balance
- Income Statement
- Balance Sheet
- Contract Profitability
- Expenses tracking
- General Ledger
- Navigation to Suppliers, Inventory, Purchase Invoices
"""

from ._anvil_designer import AccountantFormTemplate
from anvil import *
import anvil.server
import anvil.js
import logging

try:
    from ..auth_helpers import get_auth_token
except ImportError:
    from auth_helpers import get_auth_token

try:
    from ..notif_bridge import register_notif_bridges
except ImportError:
    from notif_bridge import register_notif_bridges

logger = logging.getLogger(__name__)


class AccountantForm(AccountantFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Auth
        self._token = get_auth_token()

        # JS Bridges - Reports
        anvil.js.window.pyGetTrialBalance = self.get_trial_balance
        anvil.js.window.pyGetIncomeStatement = self.get_income_statement
        anvil.js.window.pyGetBalanceSheet = self.get_balance_sheet
        anvil.js.window.pyGetContractProfitability = self.get_contract_profitability
        anvil.js.window.pyGetExpenses = self.get_expenses
        anvil.js.window.pyAddExpense = self.add_expense
        anvil.js.window.pyDeleteExpense = self.delete_expense
        anvil.js.window.pyGetLedgerEntries = self.get_ledger_entries
        anvil.js.window.pySeedAccounts = self.seed_accounts

        # JS Bridges - Navigation
        anvil.js.window.pyOpenSuppliers = self.open_suppliers
        anvil.js.window.pyOpenInventory = self.open_inventory
        anvil.js.window.pyOpenPurchaseInvoices = self.open_purchase_invoices
        anvil.js.window.pyGoBack = self.go_back

        register_notif_bridges()

    def _auth(self):
        return self._token or get_auth_token()

    # --- Reports ---
    def get_trial_balance(self, date_from='', date_to=''):
        return anvil.server.call('get_trial_balance', date_from, date_to, self._auth())

    def get_income_statement(self, date_from='', date_to=''):
        return anvil.server.call('get_income_statement', date_from, date_to, self._auth())

    def get_balance_sheet(self, as_of_date=''):
        return anvil.server.call('get_balance_sheet', as_of_date, self._auth())

    def get_contract_profitability(self):
        return anvil.server.call('get_contract_profitability', self._auth())

    def get_expenses(self, date_from='', date_to='', category=''):
        return anvil.server.call('get_expenses', date_from, date_to, category, self._auth())

    def add_expense(self, data):
        return anvil.server.call('add_expense', data, self._auth())

    def delete_expense(self, expense_id):
        return anvil.server.call('delete_expense', expense_id, self._auth())

    def get_ledger_entries(self, account_id='', date_from='', date_to=''):
        return anvil.server.call('get_ledger_entries', account_id, date_from, date_to, self._auth())

    def seed_accounts(self):
        return anvil.server.call('seed_accounts', self._auth())

    # --- Navigation ---
    def open_suppliers(self):
        open_form('SuppliersForm')

    def open_inventory(self):
        open_form('InventoryForm')

    def open_purchase_invoices(self):
        open_form('PurchaseInvoicesForm')

    def go_back(self):
        open_form('AdminPanel')

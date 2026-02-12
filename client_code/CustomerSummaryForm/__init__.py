"""
CustomerSummaryForm - Customer Accounts Summary
=================================================
- View all customers with AR balances
- Record customer collections (cash/bank)
- Opening balance display
- Dynamic balance from ledger
"""

from ._anvil_designer import CustomerSummaryFormTemplate
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


class CustomerSummaryForm(CustomerSummaryFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Auth
        self._token = get_auth_token()

        # JS Bridges
        anvil.js.window.pyGetCustomerSummary = self.get_customer_summary
        anvil.js.window.pyRecordCollection = self.record_collection
        anvil.js.window.pyGetBankAccounts = self.get_bank_accounts
        anvil.js.window.pyGoBack = self.go_back

        register_notif_bridges()

    def _auth(self):
        return self._token or get_auth_token()

    def get_customer_summary(self):
        return anvil.server.call('get_customer_summary', self._auth())

    def record_collection(self, contract_number, amount, payment_method,
                          collection_date='', notes=''):
        return anvil.server.call('record_customer_collection',
                                 contract_number, amount, payment_method,
                                 collection_date, notes, self._auth())

    def get_bank_accounts(self):
        return anvil.server.call('get_bank_accounts', self._auth())

    def go_back(self):
        open_form('AccountantForm')

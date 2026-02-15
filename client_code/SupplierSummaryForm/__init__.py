"""
SupplierSummaryForm - Supplier Accounts Summary
=================================================
- View all suppliers with AP balances
- Opening balance display
- Dynamic balance from ledger
"""

from ._anvil_designer import SupplierSummaryFormTemplate
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


class SupplierSummaryForm(SupplierSummaryFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Auth
        self._token = get_auth_token()

        # JS Bridges
        anvil.js.window.pyGetSupplierSummary = self.get_supplier_summary
        anvil.js.window.pyGoBack = self.go_back

        register_notif_bridges()

    def _auth(self):
        return self._token or get_auth_token()

    def get_supplier_summary(self):
        return anvil.server.call('get_supplier_summary', self._auth())

    def go_back(self):
        token = self._auth()
        try:
            if token:
                anvil.js.window.sessionStorage.setItem('auth_token', token)
        except Exception:
            pass
        open_form('AccountantForm', auth_token=token)
        return True

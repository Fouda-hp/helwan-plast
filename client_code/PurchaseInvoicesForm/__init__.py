"""
PurchaseInvoicesForm - Purchase Invoices with Import Costing
============================================================
- Create, view, edit purchase invoices
- Dynamic line items
- Import costs (shipping, customs, insurance)
- Record payments
- Auto-calculate totals
"""

from ._anvil_designer import PurchaseInvoicesFormTemplate
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


class PurchaseInvoicesForm(PurchaseInvoicesFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Auth
        self._token = get_auth_token()

        # JS Bridges
        anvil.js.window.pyGetPurchaseInvoices = self.get_purchase_invoices
        anvil.js.window.pyCreatePurchaseInvoice = self.create_purchase_invoice
        anvil.js.window.pyUpdatePurchaseInvoice = self.update_purchase_invoice
        anvil.js.window.pyDeletePurchaseInvoice = self.delete_purchase_invoice
        anvil.js.window.pyRecordInvoicePayment = self.record_invoice_payment
        anvil.js.window.pyGetSuppliersList = self.get_suppliers_list
        anvil.js.window.pyAddImportCost = self.add_import_cost
        anvil.js.window.pyGetInvoiceDetails = self.get_invoice_details
        anvil.js.window.pyGoBack = self.go_back

        register_notif_bridges()

    def _auth(self):
        return self._token or get_auth_token()

    def get_purchase_invoices(self, status='', search=''):
        return anvil.server.call('get_purchase_invoices', status, search, self._auth())

    def create_purchase_invoice(self, data):
        return anvil.server.call('create_purchase_invoice', data, self._auth())

    def update_purchase_invoice(self, invoice_id, data):
        return anvil.server.call('update_purchase_invoice', invoice_id, data, self._auth())

    def delete_purchase_invoice(self, invoice_id):
        return anvil.server.call('delete_purchase_invoice', invoice_id, self._auth())

    def record_invoice_payment(self, invoice_id, amount, method, notes):
        return anvil.server.call('record_invoice_payment', invoice_id, amount, method, notes, self._auth())

    def get_suppliers_list(self):
        return anvil.server.call('get_suppliers_list_simple', self._auth())

    def add_import_cost(self, invoice_id, cost_type, amount, notes):
        return anvil.server.call('add_import_cost', invoice_id, cost_type, amount, notes, self._auth())

    def get_invoice_details(self, invoice_id):
        return anvil.server.call('get_invoice_details', invoice_id, self._auth())

    def go_back(self):
        open_form('AdminPanel')

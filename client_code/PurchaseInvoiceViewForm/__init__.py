from ._anvil_designer import PurchaseInvoiceViewFormTemplate
from anvil import *
import anvil.server
import anvil.js


class PurchaseInvoiceViewForm(PurchaseInvoiceViewFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # JS bridges
        anvil.js.window.pyGetNewPurchaseInvoiceData = self.get_new_purchase_invoice_data
        anvil.js.window.pyGetQuotationCosts = self.get_quotation_costs
        anvil.js.window.pySavePurchaseInvoiceProforma = self.save_purchase_invoice_proforma
        anvil.js.window.pyGetPurchaseInvoiceViewData = self.get_purchase_invoice_view_data
        anvil.js.window.pyPurchaseGoBack = self.go_back

    def _auth(self):
        return anvil.js.window.sessionStorage.getItem('auth_token') or None

    def get_new_purchase_invoice_data(self, supplier_id):
        """Load supplier + company data for new proforma."""
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_new_purchase_invoice_data', supplier_id, auth)

    def get_quotation_costs(self, quotation_number):
        """Load FOB costs from quotation (when linking to contract)."""
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_quotation_costs', quotation_number, auth)

    def save_purchase_invoice_proforma(self, data):
        """Save proforma → assigns PI number."""
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('save_purchase_invoice_proforma', data, auth)

    def get_purchase_invoice_view_data(self, invoice_number):
        """Load saved invoice for view/print/PDF."""
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_purchase_invoice_view_data', invoice_number, auth)

    def go_back(self):
        from anvil.js.window import location
        location.hash = '#invoice-manager'

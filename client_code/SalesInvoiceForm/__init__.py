from ._anvil_designer import SalesInvoiceFormTemplate
from anvil import *
import anvil.server
import anvil.js


class SalesInvoiceForm(SalesInvoiceFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # JS bridges
        anvil.js.window.pyGetInvoicePdfData = self.get_invoice_pdf_data
        anvil.js.window.pyGetDraftInvoiceData = self.get_draft_invoice_data
        anvil.js.window.pySaveSalesInvoice = self.save_sales_invoice
        anvil.js.window.pyGoBack = self.go_back

    def _auth(self):
        return anvil.js.window.sessionStorage.getItem('auth_token') or None

    def get_invoice_pdf_data(self, invoice_number):
        """Load a saved invoice from DB."""
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_sales_invoice_pdf_data', invoice_number, auth)

    def get_draft_invoice_data(self, quotation_number):
        """Load contract data for draft invoice preview (not saved yet)."""
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_draft_invoice_data', quotation_number, auth)

    def save_sales_invoice(self, quotation_number, notes=''):
        """Save draft invoice to DB — assigns serial number."""
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('create_sales_invoice', quotation_number, notes, auth)

    def go_back(self):
        from anvil.js.window import location
        location.hash = '#invoice-manager'

from ._anvil_designer import SalesInvoiceFormTemplate
from anvil import *
import anvil.server
import anvil.js


class SalesInvoiceForm(SalesInvoiceFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # JS bridges
        anvil.js.window.pyGetInvoicePdfData = self.get_invoice_pdf_data
        anvil.js.window.pyGoBack = self.go_back

    def _auth(self):
        return anvil.js.window.sessionStorage.getItem('auth_token') or None

    def get_invoice_pdf_data(self, invoice_number):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_sales_invoice_pdf_data', invoice_number, auth)

    def go_back(self):
        from anvil.js.window import location
        location.hash = '#invoice-manager'

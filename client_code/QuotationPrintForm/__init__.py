from ._anvil_designer import QuotationPrintFormTemplate
from anvil import *
import anvil.server
import anvil.js

class QuotationPrintForm(QuotationPrintFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Expose functions to JavaScript
        anvil.js.window.loadQuotationForPrint = self.load_quotation_for_print
        anvil.js.window.searchQuotationsForPrint = self.search_quotations_for_print
        anvil.js.window.getQuotationPdfData = self.get_quotation_pdf_data
        anvil.js.window.getAllSettings = self.get_all_settings

    def load_quotation_for_print(self, quotation_number):
        """Load quotation data for print preview"""
        try:
            user_email = anvil.js.window.sessionStorage.getItem('user_email') or ''
            result = anvil.server.call('get_quotation_pdf_data', int(quotation_number), user_email)
            return result
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def search_quotations_for_print(self, query=''):
        """Search quotations"""
        try:
            result = anvil.server.call('get_quotations_list', query, include_deleted=False)
            return result
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def get_quotation_pdf_data(self, quotation_number):
        """Get full quotation data for PDF"""
        try:
            user_email = anvil.js.window.sessionStorage.getItem('user_email') or ''
            result = anvil.server.call('get_quotation_pdf_data', int(quotation_number), user_email)
            return result
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def get_all_settings(self):
        """Get all template settings"""
        try:
            result = anvil.server.call('get_all_settings')
            return result
        except Exception as e:
            return {'success': False, 'message': str(e)}

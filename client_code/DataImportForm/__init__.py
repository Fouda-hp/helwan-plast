"""
DataImportForm - صفحة استيراد البيانات (للأدمن فقط)
===================================================
- استيراد بيانات العملاء من CSV/Excel
- استيراد بيانات العروض من CSV/Excel
- معاينة البيانات قبل الاستيراد
- تقرير الأخطاء والنتائج
"""

from ._anvil_designer import DataImportFormTemplate
from anvil import *
import anvil.server
import anvil.js


class DataImportForm(DataImportFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Get user email from session
        self.user_email = ''
        self._get_user_email()

        # Setup JavaScript bridge functions
        anvil.js.window.pyImportClients = self.import_clients
        anvil.js.window.pyImportQuotations = self.import_quotations

    def _get_user_email(self):
        """Get user email from session"""
        try:
            token = anvil.js.window.sessionStorage.getItem('auth_token')
            if token:
                result = anvil.server.call('validate_token', token)
                if result.get('valid'):
                    self.user_email = result['user']['email']
        except:
            pass

    def import_clients(self, data):
        """Import clients data"""
        return anvil.server.call('import_clients_data', data, self.user_email)

    def import_quotations(self, data):
        """Import quotations data"""
        return anvil.server.call('import_quotations_data', data, self.user_email)

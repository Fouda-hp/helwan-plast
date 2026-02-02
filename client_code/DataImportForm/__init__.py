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

        # Get auth token and user email from session
        self.auth_token = ''
        self.user_email = ''
        self._get_auth_info()

        # Setup JavaScript bridge functions
        anvil.js.window.pyImportClients = self.import_clients
        anvil.js.window.pyImportQuotations = self.import_quotations

        # Listen for hash changes
        anvil.js.window.addEventListener("hashchange", self.on_hash_change)

    def on_hash_change(self, event):
        """Handle hash changes for navigation"""
        self.check_route()

    def check_route(self):
        """Handle routing"""
        hash_val = anvil.js.window.location.hash
        if hash_val == "#admin":
            open_form('AdminPanel')
        elif hash_val == "#launcher":
            open_form('LauncherForm')
        elif hash_val == "#calculator":
            open_form('CalculatorForm')
        elif hash_val == "#login" or hash_val == "":
            open_form('LoginForm')

    def _get_auth_info(self):
        """Get auth token and user email from session"""
        try:
            self.auth_token = anvil.js.window.sessionStorage.getItem('auth_token') or ''
            if self.auth_token:
                result = anvil.server.call('validate_token', self.auth_token)
                if result.get('valid'):
                    self.user_email = result['user']['email']
        except Exception as e:
            print(f"Error getting auth info: {e}")

    def import_clients(self, data):
        """Import clients data - sends both token and email for verification"""
        # Try with token first, fallback to email
        if self.auth_token:
            return anvil.server.call('import_clients_data', data, self.auth_token)
        elif self.user_email:
            return anvil.server.call('import_clients_data', data, self.user_email)
        else:
            return {'success': False, 'message': 'Not authenticated. Please login again.'}

    def import_quotations(self, data):
        """Import quotations data - sends both token and email for verification"""
        # Try with token first, fallback to email
        if self.auth_token:
            return anvil.server.call('import_quotations_data', data, self.auth_token)
        elif self.user_email:
            return anvil.server.call('import_quotations_data', data, self.user_email)
        else:
            return {'success': False, 'message': 'Not authenticated. Please login again.'}

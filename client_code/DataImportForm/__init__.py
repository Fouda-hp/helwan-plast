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
import anvil.google.auth, anvil.google.drive
from anvil.google.drive import app_files
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
        anvil.js.window.pyGoBack = self.go_back

        # Listen for hash changes
        anvil.js.window.addEventListener("hashchange", self.on_hash_change)

    def on_hash_change(self, event):
        """Handle hash changes for navigation"""
        self.check_route()

    def check_route(self):
        """التوجيه حسب الـ hash (مصدر واحد: shared.routing)"""
        hash_val = anvil.js.window.location.hash or ""
        if not hash_val or hash_val == "#":
            hash_val = "#login"
        from shared.routing import open_route
        open_route(hash_val)

    def _get_auth_info(self):
        """Get auth token and user email from session"""
        try:
            self.auth_token = anvil.js.window.sessionStorage.getItem('auth_token') or ''
            self.user_email = anvil.js.window.sessionStorage.getItem('user_email') or ''

            print(f"DEBUG: auth_token exists: {bool(self.auth_token)}")
            print(f"DEBUG: user_email from storage: {self.user_email}")

            # إذا لم يكن هناك email في localStorage، نحاول الحصول عليه من الـ token
            if self.auth_token and not self.user_email:
                result = anvil.server.call('validate_token', self.auth_token)
                if result.get('valid'):
                    self.user_email = result['user']['email']
                    print(f"DEBUG: user_email from token validation: {self.user_email}")
        except Exception as e:
            print(f"Error getting auth info: {e}")

    def import_clients(self, data):
        """Import clients data - sends both token and email for verification"""
        print(f"DEBUG import_clients: token={bool(self.auth_token)}, email={self.user_email}")

        # استخدام الـ email مباشرة لأنه أكثر موثوقية
        if self.user_email:
            print(f"DEBUG: Using email for auth: {self.user_email}")
            return anvil.server.call('import_clients_data', data, self.user_email)
        elif self.auth_token:
            print(f"DEBUG: Using token for auth")
            return anvil.server.call('import_clients_data', data, self.auth_token)
        else:
            return {'success': False, 'message': 'Not authenticated. Please login again.'}

    def import_quotations(self, data):
        """Import quotations data - sends both token and email for verification"""
        print(f"DEBUG import_quotations: token={bool(self.auth_token)}, email={self.user_email}")

        # استخدام الـ email مباشرة لأنه أكثر موثوقية
        if self.user_email:
            print(f"DEBUG: Using email for auth: {self.user_email}")
            return anvil.server.call('import_quotations_data', data, self.user_email)
        elif self.auth_token:
            print(f"DEBUG: Using token for auth")
            return anvil.server.call('import_quotations_data', data, self.auth_token)
        else:
            return {'success': False, 'message': 'Not authenticated. Please login again.'}

    def go_back(self):
        """Navigate back to AdminPanel"""
        open_form('AdminPanel')

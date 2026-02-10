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
import anvil.users
import anvil.google.auth, anvil.google.drive
from anvil.google.drive import app_files
import anvil.server
import anvil.js
import logging

try:
    from ..notif_bridge import register_notif_bridges
except ImportError:
    from notif_bridge import register_notif_bridges

logger = logging.getLogger(__name__)


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

        # Notification bridges
        register_notif_bridges()

        # Listen for hash changes
        anvil.js.window.addEventListener("hashchange", self.on_hash_change)

    def on_hash_change(self, event):
        """Handle hash changes for navigation"""
        self.check_route()

    def _user_is_admin(self):
        """التحقق من السيرفر أن المستخدم الحالي أدمن."""
        try:
            token = anvil.js.window.sessionStorage.getItem('auth_token') or anvil.js.window.localStorage.getItem('auth_token')
            if not token:
                return False
            result = anvil.server.call('validate_token', token)
            if not result.get('valid') or not result.get('user'):
                return False
            return (result.get('user', {}).get('role') or '').strip().lower() == 'admin'
        except Exception:
            return False

    def check_route(self):
        """Handle routing"""
        hash_val = (anvil.js.window.location.hash or '').strip()
        if hash_val == "#admin":
            if not self._user_is_admin():
                anvil.js.window.location.hash = '#launcher'
                open_form('LauncherForm')
                return
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
            self.user_email = anvil.js.window.sessionStorage.getItem('user_email') or ''

            # إذا لم يكن هناك email في sessionStorage، نحاول الحصول عليه من الـ token
            if self.auth_token and not self.user_email:
                result = anvil.server.call('validate_token', self.auth_token)
                if result.get('valid'):
                    self.user_email = result['user']['email']
        except Exception as e:
            logger.debug("Error getting auth info: %s", e)

    def import_clients(self, data):
        """Import clients data - sends both token and email for verification"""
        if self.user_email:
            return anvil.server.call('import_clients_data', data, self.user_email)
        elif self.auth_token:
            return anvil.server.call('import_clients_data', data, self.auth_token)
        else:
            return {'success': False, 'message': 'Not authenticated. Please login again.'}

    def import_quotations(self, data):
        """Import quotations data - sends both token and email for verification"""
        if self.user_email:
            return anvil.server.call('import_quotations_data', data, self.user_email)
        elif self.auth_token:
            return anvil.server.call('import_quotations_data', data, self.auth_token)
        else:
            return {'success': False, 'message': 'Not authenticated. Please login again.'}

    def go_back(self):
        """Navigate back to AdminPanel"""
        open_form('AdminPanel')

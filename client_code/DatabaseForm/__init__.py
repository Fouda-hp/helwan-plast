"""
DatabaseForm - صفحة عرض قاعدة البيانات (للقراءة فقط)
=====================================================
- عرض جميع الجداول (العملاء والعروض)
- تصدير البيانات إلى Excel/CSV
- للقراءة فقط - لا يمكن التعديل
"""

from ._anvil_designer import DatabaseFormTemplate
from anvil import *
import anvil.users
import anvil.google.auth, anvil.google.drive
from anvil.google.drive import app_files
import anvil.server
import anvil.js
from ..auth_helpers import get_auth_token


class DatabaseForm(DatabaseFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Setup JavaScript bridge functions
        anvil.js.window.pyGetClients = self.get_clients
        anvil.js.window.pyGetQuotations = self.get_quotations
        anvil.js.window.pyExportClients = self.export_clients
        anvil.js.window.pyExportQuotations = self.export_quotations

    def _auth(self):
        return get_auth_token()

    def get_clients(self, page, per_page, search, include_deleted):
        """Get clients data"""
        return anvil.server.call('get_all_clients', page, per_page, search, include_deleted, self._auth())

    def get_quotations(self, page, per_page, search, include_deleted):
        """Get quotations data"""
        return anvil.server.call('get_all_quotations', page, per_page, search, include_deleted, self._auth())

    def export_clients(self, include_deleted):
        """Export clients data"""
        return anvil.server.call('export_clients_data', include_deleted, self._auth())

    def export_quotations(self, include_deleted):
        """Export quotations data"""
        return anvil.server.call('export_quotations_data', include_deleted, self._auth())

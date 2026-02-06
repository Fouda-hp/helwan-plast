"""
ClientListForm - صفحة عرض العملاء (للقراءة فقط)
=================================================
- عرض جميع العملاء مع البحث والترقيم
- تصدير البيانات إلى Excel/CSV
- للقراءة فقط - لا يمكن التعديل
"""

from ._anvil_designer import ClientListFormTemplate
from anvil import *
import anvil.users
import anvil.google.auth, anvil.google.drive
from anvil.google.drive import app_files
import anvil.server
import anvil.js


class ClientListForm(ClientListFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Setup JavaScript bridge functions
        anvil.js.window.pyGetClients = self.get_clients
        anvil.js.window.pyExportClients = self.export_clients

    def _auth(self):
        return anvil.js.window.sessionStorage.getItem('auth_token') or anvil.js.window.sessionStorage.getItem('user_email') or None

    def get_clients(self, page, per_page, search, include_deleted):
        """Get clients data"""
        return anvil.server.call('get_all_clients', page, per_page, search, include_deleted, self._auth())

    def export_clients(self, include_deleted):
        """Export clients data"""
        return anvil.server.call('export_clients_data', include_deleted, self._auth())

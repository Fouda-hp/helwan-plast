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
from ..auth_helpers import get_auth_token

try:
    from ..notif_bridge import register_notif_bridges
except ImportError:
    from notif_bridge import register_notif_bridges


class ClientListForm(ClientListFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Setup JavaScript bridge functions
        anvil.js.window.pyGetClients = self.get_clients
        anvil.js.window.pyExportClients = self.export_clients
        anvil.js.window.pyGetAllTags = self.get_all_tags
        anvil.js.window.pyNavigateToClient = self.navigate_to_client

        # Notification bridges
        register_notif_bridges()

    def _auth(self):
        return get_auth_token()

    def get_clients(self, page, per_page, search, include_deleted):
        """Get clients data"""
        return anvil.server.call('get_all_clients', page, per_page, search, include_deleted, self._auth())

    def export_clients(self, include_deleted):
        """Export clients data"""
        return anvil.server.call('export_clients_data', include_deleted, self._auth())

    def get_all_tags(self):
        """Get all unique tags across clients"""
        return anvil.server.call('get_all_tags', self._auth())

    def navigate_to_client(self, client_code):
        """Navigate to client detail page"""
        anvil.js.window.location.hash = '#client-detail?code=' + str(client_code)

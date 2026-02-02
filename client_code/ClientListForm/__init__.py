"""
ClientListForm - صفحة عرض العملاء (للقراءة فقط)
=================================================
- عرض جميع العملاء مع البحث والترقيم
- تصدير البيانات إلى Excel/CSV
- للقراءة فقط - لا يمكن التعديل
"""

from ._anvil_designer import ClientListFormTemplate
from anvil import *
import anvil.server
import anvil.js


class ClientListForm(ClientListFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Setup JavaScript bridge functions
        anvil.js.window.pyGetClients = self.get_clients
        anvil.js.window.pyExportClients = self.export_clients

    def get_clients(self, page, per_page, search, include_deleted):
        """Get clients data"""
        return anvil.server.call('get_all_clients', page, per_page, search, include_deleted)

    def export_clients(self, include_deleted):
        """Export clients data"""
        return anvil.server.call('export_clients_data', include_deleted)

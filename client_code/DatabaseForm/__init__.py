"""
DatabaseForm - صفحة عرض قاعدة البيانات (للقراءة فقط)
=====================================================
- عرض عروض الأسعار (Quotations)
- تصدير البيانات إلى CSV
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

try:
    from ..notif_bridge import register_notif_bridges
except ImportError:
    from notif_bridge import register_notif_bridges


class DatabaseForm(DatabaseFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Setup JavaScript bridge functions
        anvil.js.window.pyGetQuotations = self.get_quotations
        anvil.js.window.pyExportQuotations = self.export_quotations
        anvil.js.window.pySetFollowup = self.set_followup_db

        # Notification bridges
        register_notif_bridges()

    def _auth(self):
        return get_auth_token()

    def get_quotations(self, page, per_page, search, include_deleted):
        """Get quotations data"""
        return anvil.server.call('get_all_quotations', page, per_page, search, include_deleted, self._auth())

    def export_quotations(self, include_deleted):
        """Export quotations data"""
        return anvil.server.call('export_quotations_data', include_deleted, self._auth())

    def set_followup_db(self, quotation_number, follow_up_date):
        """Set follow-up date for a quotation"""
        return anvil.server.call('set_followup', quotation_number, follow_up_date, self._auth())

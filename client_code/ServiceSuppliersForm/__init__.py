"""
ServiceSuppliersForm - Service Suppliers Management
=====================================================
- View, add, edit, delete service suppliers (shipping, transport, customs, etc.)
- Search and filter by service type
- View AP balance summary per supplier
- i18n support (EN/AR)
"""

from ._anvil_designer import ServiceSuppliersFormTemplate
from anvil import *
import anvil.server
import anvil.js
import logging

try:
    from ..auth_helpers import get_auth_token
except ImportError:
    from auth_helpers import get_auth_token

try:
    from ..notif_bridge import register_notif_bridges
except ImportError:
    from notif_bridge import register_notif_bridges

logger = logging.getLogger(__name__)


class ServiceSuppliersForm(ServiceSuppliersFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Auth
        self._token = get_auth_token()

        # JS Bridges
        anvil.js.window.pyGetServiceSuppliers = self.get_service_suppliers
        anvil.js.window.pyAddServiceSupplier = self.add_service_supplier
        anvil.js.window.pyUpdateServiceSupplier = self.update_service_supplier
        anvil.js.window.pyDeleteServiceSupplier = self.delete_service_supplier
        anvil.js.window.pyGetServiceSupplierSummary = self.get_service_supplier_summary
        anvil.js.window.pyGoBack = self.go_back

        register_notif_bridges()

    def _auth(self):
        return self._token or get_auth_token()

    def get_service_suppliers(self, search='', service_type=None):
        return anvil.server.call('get_service_suppliers', search, service_type, self._auth())

    def add_service_supplier(self, data):
        return anvil.server.call('add_service_supplier', data, self._auth())

    def update_service_supplier(self, supplier_id, data):
        return anvil.server.call('update_service_supplier', supplier_id, data, self._auth())

    def delete_service_supplier(self, supplier_id):
        return anvil.server.call('delete_service_supplier', supplier_id, self._auth())

    def get_service_supplier_summary(self):
        return anvil.server.call('get_service_supplier_summary', self._auth())

    def go_back(self):
        try:
            anvil.js.window.location.hash = '#accountant'
            anvil.js.window.localStorage.setItem('hp_last_page', '#accountant')
        except Exception:
            pass
        open_form('AccountantForm')
        return True

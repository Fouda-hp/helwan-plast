"""
SuppliersForm - Suppliers Management
=====================================
- View, add, edit, delete suppliers
- Search and filter suppliers
- i18n support (EN/AR)
"""

from ._anvil_designer import SuppliersFormTemplate
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


class SuppliersForm(SuppliersFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Auth
        self._token = get_auth_token()

        # JS Bridges
        anvil.js.window.pyGetSuppliers = self.get_suppliers
        anvil.js.window.pyAddSupplier = self.add_supplier
        anvil.js.window.pyUpdateSupplier = self.update_supplier
        anvil.js.window.pyDeleteSupplier = self.delete_supplier
        anvil.js.window.pyGoBack = self.go_back

        register_notif_bridges()

    def _auth(self):
        return self._token or get_auth_token()

    def get_suppliers(self, search=''):
        return anvil.server.call('get_suppliers', search, self._auth())

    def add_supplier(self, data):
        return anvil.server.call('add_supplier', data, self._auth())

    def update_supplier(self, supplier_id, data):
        return anvil.server.call('update_supplier', supplier_id, data, self._auth())

    def delete_supplier(self, supplier_id):
        return anvil.server.call('delete_supplier', supplier_id, self._auth())

    def go_back(self):
        open_form('AdminPanel')

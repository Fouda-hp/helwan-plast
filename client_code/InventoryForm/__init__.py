"""
InventoryForm - Inventory / Stock Management
=============================================
- View inventory items with status filters (In Stock, Reserved, Sold)
- Add new inventory items
- Update items and link to contracts
- Track profit/loss per item
"""

from ._anvil_designer import InventoryFormTemplate
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


class InventoryForm(InventoryFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Auth
        self._token = get_auth_token()

        # JS Bridges
        anvil.js.window.pyGetInventory = self.get_inventory
        anvil.js.window.pyAddInventoryItem = self.add_inventory_item
        anvil.js.window.pyUpdateInventoryItem = self.update_inventory_item
        anvil.js.window.pyLinkToContract = self.link_inventory_to_contract
        anvil.js.window.pyDeleteInventoryItem = self.delete_inventory_item
        anvil.js.window.pyGetContractsList = self.get_contracts_list
        anvil.js.window.pyGoBack = self.go_back

        register_notif_bridges()

    def _auth(self):
        return self._token or get_auth_token()

    def get_inventory(self, status='', search=''):
        return anvil.server.call('get_inventory', status, search, self._auth())

    def add_inventory_item(self, data):
        return anvil.server.call('add_inventory_item', data, self._auth())

    def update_inventory_item(self, item_id, data):
        return anvil.server.call('update_inventory_item', item_id, data, self._auth())

    def link_inventory_to_contract(self, item_id, contract_id, selling_price):
        return anvil.server.call('link_inventory_to_contract', item_id, contract_id, selling_price, self._auth())

    def delete_inventory_item(self, item_id):
        return anvil.server.call('delete_inventory_item', item_id, self._auth())

    def get_contracts_list(self):
        return anvil.server.call('get_contracts_list_simple', self._auth())

    def go_back(self):
        open_form('AdminPanel')

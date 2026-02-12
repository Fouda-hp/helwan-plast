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

        # JS Bridges — existing
        anvil.js.window.pyGetInventory = self.get_inventory
        anvil.js.window.pyAddInventoryItem = self.add_inventory_item
        anvil.js.window.pyUpdateInventoryItem = self.update_inventory_item
        anvil.js.window.pyLinkToContract = self.link_inventory_to_contract
        anvil.js.window.pyDeleteInventoryItem = self.delete_inventory_item
        anvil.js.window.pyGetContractsList = self.get_contracts_list
        anvil.js.window.pyGoBack = self.go_back

        # JS Bridges — new (receive, sell, landed cost, profitability)
        anvil.js.window.pyReceiveInventory = self.receive_inventory
        anvil.js.window.pySellInventory = self.sell_inventory
        anvil.js.window.pyGetLandedCost = self.get_landed_cost
        anvil.js.window.pyGetContractProfitability = self.get_contract_profitability

        register_notif_bridges()

    def _auth(self):
        return self._token or get_auth_token()

    # --- Inventory CRUD ---
    def get_inventory(self, status='', search=''):
        return anvil.server.call('get_inventory', status, search, self._auth())

    def add_inventory_item(self, data):
        return anvil.server.call('add_inventory_item', data, self._auth())

    def update_inventory_item(self, item_id, data):
        return anvil.server.call('update_inventory_item', item_id, data, self._auth())

    def delete_inventory_item(self, item_id):
        return anvil.server.call('delete_inventory_item', item_id, self._auth())

    # --- Status Transitions ---
    def receive_inventory(self, item_id, location=''):
        """Mark item as received: in_transit → in_stock (no P&L impact)."""
        return anvil.server.call('receive_inventory', item_id, location, self._auth())

    def sell_inventory(self, item_id, contract_number, selling_price, sale_date=None):
        """Record sale: posts COGS (DR 5000, CR 1200) and Revenue (DR 1100, CR 4000)."""
        return anvil.server.call('sell_inventory', item_id, contract_number,
                                 selling_price, sale_date, self._auth())

    def link_inventory_to_contract(self, item_id, contract_id, selling_price):
        """Backward-compatible: same as sell_inventory."""
        return anvil.server.call('link_inventory_to_contract', item_id, contract_id,
                                 selling_price, self._auth())

    # --- Reports ---
    def get_landed_cost(self, purchase_invoice_id):
        """Get landed cost breakdown for an inventory item's purchase invoice."""
        return anvil.server.call('get_landed_cost', purchase_invoice_id, None, self._auth())

    def get_contract_profitability(self, contract_number=None):
        """Get profitability report: revenue - landed cost per contract."""
        return anvil.server.call('get_contract_profitability', contract_number, self._auth())

    # --- Lookups ---
    def get_contracts_list(self):
        return anvil.server.call('get_contracts_list_simple', self._auth())

    def go_back(self):
        open_form('AdminPanel')

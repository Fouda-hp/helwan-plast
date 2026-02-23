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

        # JS Bridge — Calculator settings for machine config
        anvil.js.window.pyGetCalculatorSettings = self.get_calculator_settings

        # JS Bridge — RBAC permissions
        anvil.js.window.pyGetPermissions = self.get_permissions

        # JS Bridges — new (receive, sell, landed cost, profitability, opening balance)
        anvil.js.window.pyReceiveInventory = self.receive_inventory
        anvil.js.window.pySellInventory = self.sell_inventory
        anvil.js.window.pyGetLandedCost = self.get_landed_cost
        anvil.js.window.pyGetContractProfitability = self.get_contract_profitability
        anvil.js.window.pyAddOpeningBalance = self.add_opening_balance

        register_notif_bridges()

    def _auth(self):
        return self._token or get_auth_token()

    # --- Inventory CRUD ---
    def get_inventory(self, status='', search='', item_type=None):
        return anvil.server.call('get_inventory', status, search, self._auth(), item_type)

    def add_inventory_item(self, data):
        return anvil.server.call('add_inventory_item', data, self._auth())

    def add_opening_balance(self, data):
        """Create opening balance: machine + cylinders + import costs + journal entry."""
        return anvil.server.call('add_opening_balance_inventory', data, self._auth())

    def update_inventory_item(self, item_id, data):
        return anvil.server.call('update_inventory_item', item_id, data, self._auth())

    def delete_inventory_item(self, item_id):
        return anvil.server.call('delete_inventory_item', item_id, self._auth())

    # --- Status Transitions ---
    def receive_inventory(self, item_id, location=''):
        """Mark item as received: in_transit → in_stock (no P&L impact)."""
        return anvil.server.call('receive_inventory', item_id, location, self._auth())

    def sell_inventory(self, item_id, contract_number, selling_price, sale_date=None, quantity_to_sell=None):
        """Record sale: posts COGS (DR 5000, CR 1200) and Revenue (DR 1100, CR 4000)."""
        kwargs = dict(token_or_email=self._auth())
        if quantity_to_sell is not None:
            kwargs['quantity_to_sell'] = int(quantity_to_sell)
        return anvil.server.call('sell_inventory', item_id, contract_number,
                                 selling_price, sale_date, **kwargs)

    def link_inventory_to_contract(self, item_id, contract_id, selling_price, quantity_to_sell=None):
        """Link to contract. For cylinders, pass quantity_to_sell for partial sales."""
        kwargs = dict(token_or_email=self._auth())
        if quantity_to_sell is not None:
            kwargs['quantity_to_sell'] = int(quantity_to_sell)
        return anvil.server.call('link_inventory_to_contract', item_id, contract_id,
                                 selling_price, **kwargs)

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

    def get_calculator_settings(self):
        """Fetch calculator settings for machine config pricing."""
        try:
            return anvil.server.call('get_calculator_settings', self._auth())
        except Exception as e:
            logger.warning("Could not load calculator settings: %s", e)
            return {'success': False, 'message': str(e)}

    def get_permissions(self):
        """Get RBAC permissions for the current user."""
        try:
            return anvil.server.call('get_user_permissions', self._auth())
        except Exception as e:
            logger.warning("Could not load permissions: %s", e)
            return {'success': False, 'can_view': True, 'can_create': False,
                    'can_edit': False, 'can_delete': False, 'is_admin': False, 'role': 'viewer'}

    def go_back(self):
        try:
            anvil.js.window.location.hash = '#admin'
            anvil.js.window.localStorage.setItem('hp_last_page', '#admin')
        except Exception:
            pass
        open_form('AdminPanel')
        return True

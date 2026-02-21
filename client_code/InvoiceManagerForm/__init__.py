from ._anvil_designer import InvoiceManagerFormTemplate
from anvil import *
import anvil.server
import anvil.js
from ..auth_helpers import get_auth_token


class InvoiceManagerForm(InvoiceManagerFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # JS bridges
        anvil.js.window.pyGetClients = self.get_clients
        anvil.js.window.pyGetSuppliers = self.get_suppliers
        anvil.js.window.pyGetContracts = self.get_contracts

    def _auth(self):
        return get_auth_token()

    def get_clients(self, search=''):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_all_clients', 1, 500, search, False, auth)

    def get_suppliers(self, search=''):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_suppliers', search, auth)

    def get_contracts(self):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_contracts_list_simple', auth)

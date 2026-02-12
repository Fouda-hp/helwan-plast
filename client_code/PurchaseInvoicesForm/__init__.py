"""
PurchaseInvoicesForm - Purchase Invoices with Import Costing
============================================================
- Create, view, edit purchase invoices
- Dynamic line items
- Import costs (shipping, customs, insurance)
- Record payments
- Auto-calculate totals
"""

from ._anvil_designer import PurchaseInvoicesFormTemplate
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


class PurchaseInvoicesForm(PurchaseInvoicesFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Auth
        self._token = get_auth_token()

        # JS Bridges — existing
        anvil.js.window.pyGetPurchaseInvoices = self.get_purchase_invoices
        anvil.js.window.pyCreatePurchaseInvoice = self.create_purchase_invoice
        anvil.js.window.pyUpdatePurchaseInvoice = self.update_purchase_invoice
        anvil.js.window.pyDeletePurchaseInvoice = self.delete_purchase_invoice
        anvil.js.window.pyRecordInvoicePayment = self.record_invoice_payment
        anvil.js.window.pyGetSuppliersList = self.get_suppliers_list
        anvil.js.window.pyAddImportCost = self.add_import_cost
        anvil.js.window.pyGetInvoiceDetails = self.get_invoice_details
        anvil.js.window.pyGoBack = self.go_back

        # JS Bridges — Calculator settings for machine config
        anvil.js.window.pyGetCalculatorSettings = self.get_calculator_settings

        # JS Bridges — new (multiple banks, posting, payable status, contract purchase)
        anvil.js.window.pyPostPurchaseInvoice = self.post_purchase_invoice
        anvil.js.window.pyRecordSupplierPayment = self.record_supplier_payment
        anvil.js.window.pyGetBankAccounts = self.get_bank_accounts
        anvil.js.window.pyGetContractPayableStatus = self.get_contract_payable_status
        anvil.js.window.pyGetImportCosts = self.get_import_costs
        anvil.js.window.pyGetLandedCost = self.get_landed_cost
        anvil.js.window.pyCreateContractPurchase = self.create_contract_purchase
        anvil.js.window.pyGetContractsList = self.get_contracts_list

        register_notif_bridges()

    def _auth(self):
        return self._token or get_auth_token()

    # --- Purchase Invoices CRUD ---
    def get_purchase_invoices(self, status='', search=''):
        return anvil.server.call('get_purchase_invoices', status, search, self._auth())

    def create_purchase_invoice(self, data):
        return anvil.server.call('create_purchase_invoice', data, self._auth())

    def update_purchase_invoice(self, invoice_id, data):
        return anvil.server.call('update_purchase_invoice', invoice_id, data, self._auth())

    def delete_purchase_invoice(self, invoice_id):
        return anvil.server.call('delete_purchase_invoice', invoice_id, self._auth())

    def post_purchase_invoice(self, invoice_id):
        """Post a draft invoice → creates journal entries (DR Inventory, CR AP)."""
        return anvil.server.call('post_purchase_invoice', invoice_id, self._auth())

    # --- Payments (with multiple bank support) ---
    def record_invoice_payment(self, invoice_id, amount, method='cash', notes=''):
        """Legacy: record payment with method string."""
        return anvil.server.call('record_invoice_payment', invoice_id, amount, method, notes, self._auth())

    def record_supplier_payment(self, invoice_id, amount, payment_method, payment_date):
        """Record payment with specific bank account (cash/cib/nbe/qnb or account code)."""
        return anvil.server.call('record_supplier_payment', invoice_id, amount,
                                 payment_method, payment_date, self._auth())

    def get_bank_accounts(self):
        """Get list of cash/bank accounts for payment dropdown."""
        return anvil.server.call('get_bank_accounts', self._auth())

    # --- Import Costs ---
    def add_import_cost(self, invoice_id, cost_type, amount, description='',
                        cost_date=None, payment_method='cash'):
        """Add import cost: DR Inventory (1200), CR selected bank/cash."""
        return anvil.server.call('add_import_cost', invoice_id, cost_type, amount,
                                 description, cost_date, payment_method, None, self._auth())

    def get_import_costs(self, invoice_id):
        """Get all import costs for a purchase invoice."""
        return anvil.server.call('get_import_costs', invoice_id, self._auth())

    def get_landed_cost(self, purchase_invoice_id):
        """Calculate landed cost = FOB + Cylinders + all import costs."""
        return anvil.server.call('get_landed_cost', purchase_invoice_id, None, self._auth())

    # --- Contract Purchase (Procurement Layer) ---
    def create_contract_purchase(self, contract_number, fob_cost, cylinder_cost,
                                 supplier_id, currency='USD'):
        """
        Create Purchase Invoice for a contract.
        Called from accounting panel — NOT from contract form.
        Posts: DR 1200 Inventory, CR 2000 Accounts Payable.
        Creates inventory item (status: in_transit).
        """
        return anvil.server.call('create_contract_purchase', contract_number,
                                 fob_cost, cylinder_cost, supplier_id, currency, self._auth())

    # --- Payable Tracking ---
    def get_contract_payable_status(self, contract_number=None):
        """Get payable status: total, paid, remaining, payment history."""
        return anvil.server.call('get_contract_payable_status', contract_number, self._auth())

    # --- Lookups ---
    def get_contracts_list(self):
        """Get contracts list for dropdown (select which contract to create purchase for)."""
        return anvil.server.call('get_contracts_list_simple', self._auth())

    # --- Suppliers & Details ---
    def get_suppliers_list(self):
        return anvil.server.call('get_suppliers_list_simple', self._auth())

    def get_invoice_details(self, invoice_id):
        return anvil.server.call('get_invoice_details', invoice_id, self._auth())

    def get_calculator_settings(self):
        """Fetch calculator settings (machine prices, adjustments, cylinder prices) from server."""
        try:
            return anvil.server.call('get_calculator_settings', self._auth())
        except Exception as e:
            logger.warning("Could not load calculator settings: %s", e)
            return {'success': False, 'message': str(e)}

    def go_back(self):
        open_form('AdminPanel')

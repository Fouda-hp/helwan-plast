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

        # JS Bridge — RBAC permissions
        anvil.js.window.pyGetPermissions = self.get_permissions

        # JS Bridges — new (multiple banks, posting, payable status, contract purchase)
        anvil.js.window.pyPostPurchaseInvoice = self.post_purchase_invoice
        anvil.js.window.pyMovePurchaseToInventory = self.move_purchase_to_inventory
        anvil.js.window.pyRecordSupplierPayment = self.record_supplier_payment
        anvil.js.window.pyGetSupplierRemainingEgp = self.get_supplier_remaining_egp
        anvil.js.window.pyGetBankAccounts = self.get_bank_accounts
        anvil.js.window.pyGetExchangeRates = self.get_exchange_rates
        anvil.js.window.pyGetContractPayableStatus = self.get_contract_payable_status
        anvil.js.window.pyGetImportCosts = self.get_import_costs
        anvil.js.window.pyGetImportCostsForPayment = self.get_import_costs_for_payment
        anvil.js.window.pyPayImportCost = self.pay_import_cost
        anvil.js.window.pyGetImportCostTypes = self.get_import_cost_types
        anvil.js.window.pyGetLandedCost = self.get_landed_cost
        anvil.js.window.pyCreateContractPurchase = self.create_contract_purchase
        anvil.js.window.pyGetContractsList = self.get_contracts_list

        # JS Bridge — PDF Reports
        anvil.js.window.pyGetPurchaseInvoicePdfData = self.get_purchase_invoice_pdf_data

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
        """Post a draft invoice → DR 1210, CR 2000 (Transit model)."""
        return anvil.server.call('post_purchase_invoice', invoice_id, self._auth())

    def move_purchase_to_inventory(self, invoice_id):
        """Move posted invoice from 1210 (Transit) to 1200 (Inventory). Idempotent."""
        return anvil.server.call('move_purchase_to_inventory', invoice_id, self._auth())

    # --- Payments (with multiple bank support) ---
    def record_invoice_payment(self, invoice_id, amount, method='cash', notes=''):
        """Legacy: record payment with method string."""
        return anvil.server.call('record_invoice_payment', invoice_id, amount, method, notes, self._auth())

    def record_supplier_payment(self, invoice_id, amount, payment_method, payment_date,
                               currency_code='EGP', exchange_rate=None, notes='',
                               percentage=None, is_paid_in_full=False):
        """تسجيل دفعة للمورد — مبلغ أو نسبة، سعر صرف عند الدفع، تسوية كاملة (فروق عملة 4110/6110)."""
        return anvil.server.call(
            'record_supplier_payment', invoice_id, amount, payment_method, payment_date,
            currency_code=currency_code, exchange_rate=exchange_rate, notes=notes,
            percentage=percentage, is_paid_in_full=is_paid_in_full, token_or_email=self._auth()
        )

    def get_supplier_remaining_egp(self, invoice_id):
        """المتبقي للمورد بالجنيه من الدفتر (لشاشة الدفع)."""
        return anvil.server.call('get_supplier_remaining_egp', invoice_id, self._auth())

    def get_bank_accounts(self):
        """Get list of cash/bank accounts for payment dropdown."""
        return anvil.server.call('get_bank_accounts', self._auth())

    def get_exchange_rates(self):
        """Get exchange rates for currency dropdown (دفع/استلام بعملة أخرى)."""
        return anvil.server.call('get_exchange_rates', self._auth())

    # --- Import Costs ---
    def add_import_cost(self, invoice_id, cost_type, amount, description='',
                        cost_date=None, payment_method='cash'):
        """Add import cost: DR Inventory (1200), CR selected bank/cash."""
        return anvil.server.call('add_import_cost', invoice_id, cost_type, amount,
                                 description, cost_date, payment_method, None, self._auth())

    def get_import_costs(self, invoice_id, inventory_id=None):
        """Get import costs for a purchase invoice or inventory item."""
        return anvil.server.call('get_import_costs', invoice_id, inventory_id, self._auth())

    def get_import_costs_for_payment(self, purchase_invoice_id):
        """Get import cost rows for Pay Import Costs screen (amount_egp, paid_amount, remaining_egp)."""
        return anvil.server.call('get_import_costs_for_payment', purchase_invoice_id, self._auth())

    def pay_import_cost(self, import_cost_id, amount_egp, payment_method, payment_date):
        """Pay (partial or full) an import cost. DR 1200, CR cash/bank."""
        return anvil.server.call('pay_import_cost', import_cost_id, amount_egp, payment_method, payment_date, self._auth())

    def get_import_cost_types(self):
        """Get extensible import cost types (from table or built-in)."""
        return anvil.server.call('get_import_cost_types', self._auth())

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

    def get_permissions(self):
        """Get RBAC permissions for the current user."""
        try:
            return anvil.server.call('get_user_permissions', self._auth())
        except Exception as e:
            logger.warning("Could not load permissions: %s", e)
            return {'success': False, 'can_view': True, 'can_create': False,
                    'can_edit': False, 'can_delete': False, 'is_admin': False, 'role': 'viewer'}

    def get_purchase_invoice_pdf_data(self, invoice_id):
        """Get PDF-ready data for a purchase invoice."""
        try:
            return anvil.server.call('get_purchase_invoice_pdf_data', invoice_id, self._auth())
        except Exception as e:
            logger.warning("PDF data error: %s", e)
            return {'success': False, 'message': str(e)}

    def go_back(self):
        try:
            anvil.js.window.location.hash = '#admin'
            anvil.js.window.localStorage.setItem('hp_last_page', '#admin')
        except Exception:
            pass
        open_form('AdminPanel')
        return True

from ._anvil_designer import InvoiceManagerFormTemplate
from anvil import *
import anvil.server
import anvil.js
from ..auth_helpers import get_auth_token


class InvoiceManagerForm(InvoiceManagerFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # JS bridges — data tabs
        anvil.js.window.pyGetClients = self.get_clients
        anvil.js.window.pyGetSuppliers = self.get_suppliers
        anvil.js.window.pyGetContracts = self.get_contracts
        anvil.js.window.pyGetQuotations = self.get_quotations

        # JS bridges — contract detail & payments
        anvil.js.window.pyGetContractDetail = self.get_contract_detail
        anvil.js.window.pyGetContractPayments = self.get_contract_payments
        anvil.js.window.pyRecordPayment = self.record_payment

        # JS bridges — sales invoices
        anvil.js.window.pyCreateSalesInvoice = self.create_sales_invoice
        anvil.js.window.pyGetContractInvoices = self.get_contract_invoices

        # JS bridges — purchase invoices (supplier history)
        anvil.js.window.pyGetSupplierPurchaseInvoices = self.get_supplier_purchase_invoices
        anvil.js.window.pyAddSupplier = self.add_supplier

        # JS bridges — service suppliers
        anvil.js.window.pyGetServiceSuppliers = self.get_service_suppliers
        anvil.js.window.pyAddServiceSupplier = self.add_service_supplier
        anvil.js.window.pyGetServiceSupplierImportCosts = self.get_service_supplier_import_costs

    def _auth(self):
        return get_auth_token()

    # ── Data tab loaders ──

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

    def get_contracts(self, search=''):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_contracts_list', search, auth)

    def get_quotations(self, search=''):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_all_quotations', 1, 500, search, False, auth)

    # ── Contract detail & payments ──

    def get_contract_detail(self, quotation_number):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_contract', quotation_number, auth)

    def get_contract_payments(self, quotation_number):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_contract_payments', quotation_number, auth)

    def record_payment(self, quotation_number, amount, payment_date,
                       payment_method, installment_index, notes):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('record_contract_payment',
                                 quotation_number, amount, payment_date,
                                 payment_method, installment_index, notes, auth)

    # ── Sales invoices ──

    def create_sales_invoice(self, quotation_number, notes=''):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('create_sales_invoice', quotation_number, notes, auth)

    def get_contract_invoices(self, quotation_number):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_contract_invoices', quotation_number, auth)

    # ── Purchase invoices (supplier history) ──

    def get_supplier_purchase_invoices(self, supplier_id):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_supplier_purchase_invoices', supplier_id, auth)

    def add_supplier(self, data):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('add_supplier', data, auth)

    # ── Service suppliers ──

    def get_service_suppliers(self, search='', service_type=None):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_service_suppliers', search, service_type, auth)

    def add_service_supplier(self, data):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('add_service_supplier', data, auth)

    def get_service_supplier_import_costs(self, service_supplier_id):
        auth = self._auth()
        if not auth:
            return {'success': False, 'message': 'Not authenticated'}
        return anvil.server.call('get_service_supplier_import_costs', service_supplier_id, auth)

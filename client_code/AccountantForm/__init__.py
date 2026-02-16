"""
AccountantForm - Main Accounting Dashboard
===========================================
- Trial Balance
- Income Statement
- Balance Sheet
- Contract Profitability
- Expenses tracking
- General Ledger
- Navigation to Suppliers, Inventory, Purchase Invoices
"""

from ._anvil_designer import AccountantFormTemplate
from anvil import *
import anvil.server
import anvil.js
import logging

try:
    from ..auth_helpers import get_auth_token, get_accountant_token
except ImportError:
    from auth_helpers import get_auth_token, get_accountant_token

try:
    from ..notif_bridge import register_notif_bridges
except ImportError:
    from notif_bridge import register_notif_bridges

logger = logging.getLogger(__name__)


def _get_token_from_window():
    """اقرأ التوكن من نافذة JS إن وضعه الأدمن قبل فتح لوحة المحاسب."""
    try:
        return getattr(anvil.js.window, '__hpAccountantAuthToken', None) or None
    except Exception:
        return None


def _sync_token_to_storage(token):
    """اكتب التوكن في sessionStorage فقط (hardening)."""
    try:
        if token:
            anvil.js.window.sessionStorage.setItem('auth_token', token)
            try:
                anvil.js.window.localStorage.removeItem('auth_token')
            except Exception:
                pass
    except Exception:
        pass


class AccountantForm(AccountantFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Auth — من المعامل، أو من auth_helpers (الأدمن حفظه قبل الفتح)، أو من النافذة أو التخزين
        self._token = (
            properties.get('auth_token')
            or get_accountant_token()
            or _get_token_from_window()
            or get_auth_token()
        )
        if self._token:
            _sync_token_to_storage(self._token)

        # JS Bridges - Reports
        anvil.js.window.pyGetTrialBalance = self.get_trial_balance
        anvil.js.window.pyGetIncomeStatement = self.get_income_statement
        anvil.js.window.pyGetBalanceSheet = self.get_balance_sheet
        anvil.js.window.pyGetContractProfitability = self.get_contract_profitability
        anvil.js.window.pyGetExpenses = self.get_expenses
        anvil.js.window.pyAddExpense = self.add_expense
        anvil.js.window.pyDeleteExpense = self.delete_expense
        anvil.js.window.pyGetLedgerEntries = self.get_ledger_entries
        anvil.js.window.pySeedAccounts = self.seed_accounts

        # JS Bridges - New: Payable tracking, bank accounts, migration
        anvil.js.window.pyGetContractPayableStatus = self.get_contract_payable_status
        anvil.js.window.pyGetBankAccounts = self.get_bank_accounts
        anvil.js.window.pyGetChartOfAccounts = self.get_chart_of_accounts
        anvil.js.window.pyGetAccountBalance = self.get_account_balance
        anvil.js.window.pyMigrateImportCosts = self.migrate_import_costs
        anvil.js.window.pyMigrateOldContracts = self.migrate_old_contracts

        # JS Bridges - Currency / Exchange Rates
        anvil.js.window.pyGetExchangeRates = self.get_exchange_rates
        anvil.js.window.pySetExchangeRate = self.set_exchange_rate
        anvil.js.window.pyDeleteExchangeRate = self.delete_exchange_rate

        # JS Bridges - Navigation
        anvil.js.window.pyOpenSuppliers = self.open_suppliers
        anvil.js.window.pyOpenInventory = self.open_inventory
        anvil.js.window.pyOpenPurchaseInvoices = self.open_purchase_invoices
        anvil.js.window.pyOpenCustomerSummary = self.open_customer_summary
        anvil.js.window.pyOpenSupplierSummary = self.open_supplier_summary
        anvil.js.window.pyGoBack = self.go_back

        # JS Bridges - Treasury & Opening Balances
        anvil.js.window.pyGetTreasurySummary = self.get_treasury_summary
        anvil.js.window.pyGetOpeningBalances = self.get_opening_balances
        anvil.js.window.pySetOpeningBalance = self.set_opening_balance
        anvil.js.window.pyPostOpeningBalances = self.post_opening_balances
        anvil.js.window.pyGetCashBankStatement = self.get_cash_bank_statement
        anvil.js.window.pyGetVatReport = self.get_vat_report
        anvil.js.window.pySettleVatForPeriod = self.settle_vat_for_period
        anvil.js.window.pyCreateTreasuryTransaction = self.create_treasury_transaction
        anvil.js.window.pyGetCashFlowReport = self.get_cash_flow_report
        anvil.js.window.pyGenerateReport = self.generate_report
        anvil.js.window.pyExportReport = self.export_report
        anvil.js.window.pyGetAdvancedAccountStatement = self.get_advanced_account_statement
        anvil.js.window.pyGetCustomerSummary = self.get_customer_summary
        anvil.js.window.pyGetSupplierSummary = self.get_supplier_summary
        anvil.js.window.pyGetPeriodLocks = self.get_period_locks
        anvil.js.window.pyClosePeriod = self.close_period
        anvil.js.window.pyReopenPeriod = self.reopen_period
        anvil.js.window.pyCloseFinancialYear = self.close_financial_year

        register_notif_bridges()
        self.add_event_handler('show', self._on_show)

    def _on_show(self, **event_args):
        """عند ظهور النموذج: نسخ التوكن، وتعرّيف دوال JS عامة (switchTab, navTo, ...) حتى تعمل الأزرار حتى لو لم تُنفَّذ سكربتات القالب."""
        try:
            anvil.js.window.eval("""
                (function(){
                    try {
                        var t = window.sessionStorage && window.sessionStorage.getItem('auth_token');
                        if (!t && window.top && window.top !== window) {
                            t = (window.top.sessionStorage && window.top.sessionStorage.getItem('auth_token'))
                                || (window.top.localStorage && window.top.localStorage.getItem('auth_token'));
                        }
                        if (!t && window.parent && window.parent !== window) {
                            t = (window.parent.sessionStorage && window.parent.sessionStorage.getItem('auth_token'))
                                || (window.parent.localStorage && window.parent.localStorage.getItem('auth_token'));
                        }
                        if (t && window.sessionStorage) {
                            window.sessionStorage.setItem('auth_token', t);
                            if (window.localStorage) window.localStorage.setItem('auth_token', t);
                        }
                    } catch (e) {}
                })();
            """)
            self._token = get_auth_token() or self._token
        except Exception:
            pass
        self._inject_js_globals()

    def _inject_js_globals(self):
        """حقن دوال JS عامة (switchTab, navTo, goBack, ...) على window حتى تعمل onclick حتى لو لم تُنفَّذ سكربتات القالب."""
        try:
            anvil.js.window.eval("""
                (function(){
                    if (typeof window.switchTab !== 'function') {
                        var cashbankAccountsPopulated = false;
                        window.switchTab = async function(el) {
                            if (!el || !el.getAttribute) return;
                            document.querySelectorAll('.sub-tab').forEach(function(t) { t.classList.remove('active'); });
                            document.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.remove('active'); });
                            el.classList.add('active');
                            var tab = el.getAttribute('data-tab');
                            var panel = document.getElementById('panel-' + tab);
                            if (panel) panel.classList.add('active');
                            if (tab === 'cashbank') {
                                if (!cashbankAccountsPopulated && typeof window.populateCashBankAccounts === 'function') {
                                    await window.populateCashBankAccounts();
                                    cashbankAccountsPopulated = true;
                                }
                                var toEl = document.getElementById('cashbankTo');
                                if (toEl && !toEl.value) toEl.value = new Date().toISOString().slice(0, 10);
                            }
                            if (tab === 'opening' && typeof window.populateOpeningBalanceAccounts === 'function') {
                                await window.populateOpeningBalanceAccounts();
                            }
                            if (tab === 'advstmt' && typeof window.populateAdvStmtEntities === 'function') {
                                await window.populateAdvStmtEntities();
                            }
                        };
                    }
                    if (typeof window.navTo !== 'function') {
                        window.navTo = function(page) {
                            if (page === 'suppliers' && window.pyOpenSuppliers) window.pyOpenSuppliers();
                            else if (page === 'inventory' && window.pyOpenInventory) window.pyOpenInventory();
                            else if (page === 'invoices' && window.pyOpenPurchaseInvoices) window.pyOpenPurchaseInvoices();
                        };
                    }
                    if (typeof window.openCustomerSummary !== 'function') {
                        window.openCustomerSummary = function() { if (window.pyOpenCustomerSummary) window.pyOpenCustomerSummary(); };
                    }
                    if (typeof window.openSupplierSummary !== 'function') {
                        window.openSupplierSummary = function() { if (window.pyOpenSupplierSummary) window.pyOpenSupplierSummary(); };
                    }
                    if (typeof window.goBack !== 'function') {
                        window.goBack = function() {
                            if (window.pyGoBack) window.pyGoBack();
                            else if (window.location && window.location.hash !== undefined) window.location.hash = '#admin';
                        };
                    }
                    if (typeof window.t !== 'function') {
                        window.t = function(en, ar) {
                            try {
                                var lang = (window.localStorage && window.localStorage.getItem('hp_language')) || 'en';
                                return lang === 'ar' ? ar : en;
                            } catch (e) { return en; }
                        };
                    }
                    if (typeof window.fmt !== 'function') {
                        window.fmt = function(n) {
                            return (n != null && !isNaN(n)) ? Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '';
                        };
                    }
                    if (typeof window.populateAdvStmtEntities !== 'function') {
                        window.populateAdvStmtEntities = async function() {
                            var entityType = document.getElementById('advStmtEntityType');
                            var entitySelect = document.getElementById('advStmtEntity');
                            if (!entityType || !entitySelect) return;
                            entitySelect.innerHTML = '<option value="">All (Consolidated)</option>';
                            var isCustomer = entityType.value === 'customer';
                            if (typeof (isCustomer ? window.pyGetCustomerSummary : window.pyGetSupplierSummary) !== 'function') return;
                            try {
                                var res = await (isCustomer ? window.pyGetCustomerSummary() : window.pyGetSupplierSummary());
                                if (res && res.success) {
                                    var data = res.data || [];
                                    data.forEach(function(r) {
                                        var id = isCustomer ? (r.client_name || '') : (r.supplier_id || r.supplier_name || '');
                                        var name = isCustomer ? (r.client_name || '') : (r.supplier_name || r.supplier_id || '');
                                        if (id || name) {
                                            var opt = document.createElement('option');
                                            opt.value = id;
                                            opt.textContent = name;
                                            entitySelect.appendChild(opt);
                                        }
                                    });
                                }
                            } catch (e) {}
                        };
                    }
                    if (typeof window.loadAdvancedStatement !== 'function') {
                        window.loadAdvancedStatement = async function() {
                            var tbody = document.getElementById('advStmtBody');
                            var entityType = document.getElementById('advStmtEntityType');
                            var entitySelect = document.getElementById('advStmtEntity');
                            var fromEl = document.getElementById('advStmtFrom');
                            var toEl = document.getElementById('advStmtTo');
                            var invoiceEl = document.getElementById('advStmtInvoice');
                            var txTypeEl = document.getElementById('advStmtTxType');
                            var agingEl = document.getElementById('advStmtAging');
                            if (!tbody || typeof window.pyGetAdvancedAccountStatement !== 'function') return;
                            var t = window.t || function(en) { return en; };
                            var fmt = window.fmt || function(n) { return (n != null && !isNaN(n)) ? Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : ''; };
                            function esc(s) {
                                if (s == null || s === undefined) return '';
                                var x = String(s);
                                return x.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
                            }
                            tbody.innerHTML = '<tr><td colspan="7" class="empty-msg">' + t('Loading...', 'جاري التحميل...') + '</td></tr>';
                            var filters = {};
                            filters.entity_type = entityType ? entityType.value : 'customer';
                            filters.entity_id = entitySelect && entitySelect.value ? entitySelect.value : null;
                            filters.date_from = fromEl && fromEl.value ? fromEl.value : null;
                            filters.date_to = toEl && toEl.value ? toEl.value : null;
                            filters.invoice_id = invoiceEl && invoiceEl.value ? invoiceEl.value : null;
                            filters.transaction_type = txTypeEl && txTypeEl.value ? txTypeEl.value : null;
                            filters.include_aging = agingEl ? agingEl.checked : false;
                            try {
                                var res = await window.pyGetAdvancedAccountStatement(filters);
                                if (res && res.success) {
                                    var titleEl = document.getElementById('advStmtTitle');
                                    if (titleEl) titleEl.textContent = 'Advanced Account Statement - ' + (res.entity_name || '');
                                    var ob = parseFloat(res.opening_balance) || 0;
                                    var cb = parseFloat(res.closing_balance) || 0;
                                    var openEl = document.getElementById('advStmtOpening');
                                    var closeEl = document.getElementById('advStmtClosing');
                                    if (openEl) openEl.textContent = fmt(ob);
                                    if (closeEl) closeEl.textContent = fmt(cb);
                                    var agingRow = document.getElementById('advStmtAgingRow');
                                    if (res.aging && agingRow) {
                                        agingRow.style.display = '';
                                        var a = res.aging;
                                        var cur = document.getElementById('advStmtAgingCurrent'); if (cur) cur.textContent = fmt(a.current);
                                        var a30 = document.getElementById('advStmtAging30'); if (a30) a30.textContent = fmt(a['30']);
                                        var a60 = document.getElementById('advStmtAging60'); if (a60) a60.textContent = fmt(a['60']);
                                        var a90 = document.getElementById('advStmtAging90'); if (a90) a90.textContent = fmt(a['90+']);
                                        var tot = document.getElementById('advStmtAgingTotal'); if (tot) tot.textContent = fmt(a.total_outstanding);
                                    } else if (agingRow) agingRow.style.display = 'none';
                                    if (res.summary && res.summary.length) {
                                        var html = '';
                                        res.summary.forEach(function(r) {
                                            html += '<tr><td></td><td></td><td>' + esc(r.entity_name) + '</td><td>Summary</td>';
                                            html += '<td class="text-right">' + fmt(r.period_debit) + '</td><td class="text-right">' + fmt(r.period_credit) + '</td>';
                                            html += '<td class="text-right">' + fmt(r.closing_balance) + '</td></tr>';
                                        });
                                        tbody.innerHTML = html;
                                    } else {
                                        var rows = res.rows || [];
                                        if (rows.length === 0) {
                                            tbody.innerHTML = '<tr><td colspan="7" class="empty-msg">No transactions in period</td></tr>';
                                        } else {
                                            var html = '';
                                            rows.forEach(function(r) {
                                                var d = r.date ? (typeof r.date === 'string' ? r.date : (r.date.year + '-' + String(r.date.month).padStart(2,'0') + '-' + String(r.date.day).padStart(2,'0'))) : '';
                                                html += '<tr><td>' + esc(d) + '</td><td>' + esc(r.reference_type) + '</td><td>' + esc(r.reference_id) + '</td><td>' + esc(r.description) + '</td>';
                                                html += '<td class="text-right">' + fmt(r.debit) + '</td><td class="text-right">' + fmt(r.credit) + '</td><td class="text-right">' + fmt(r.balance_after_transaction) + '</td></tr>';
                                            });
                                            tbody.innerHTML = html;
                                        }
                                    }
                                } else {
                                    tbody.innerHTML = '<tr><td colspan="7" class="empty-msg">' + esc(res ? res.message : 'Error') + '</td></tr>';
                                }
                            } catch (err) {
                                tbody.innerHTML = '<tr><td colspan="7" class="empty-msg">' + esc(err && err.message ? err.message : String(err)) + '</td></tr>';
                            }
                        };
                    }
                    setTimeout(function() {
                        var advStmtEntityTypeEl = document.getElementById('advStmtEntityType');
                        if (advStmtEntityTypeEl && !advStmtEntityTypeEl._advStmtListener) {
                            advStmtEntityTypeEl._advStmtListener = true;
                            advStmtEntityTypeEl.addEventListener('change', function() {
                                if (window.populateAdvStmtEntities) window.populateAdvStmtEntities();
                            });
                        }
                    }, 300);
                })();
            """)
        except Exception:
            pass

    def _auth(self):
        """استخدم التوكن من التخزين أو من النموذج أو من auth_helpers (الأدمن)."""
        token = get_auth_token() or self._token or get_accountant_token() or _get_token_from_window()
        if token:
            _sync_token_to_storage(token)
        return token

    # --- Financial Reports ---
    def get_trial_balance(self, date_from='', date_to=''):
        return anvil.server.call('get_trial_balance', date_from, date_to, self._auth())

    def get_income_statement(self, date_from='', date_to=''):
        return anvil.server.call('get_income_statement', date_from, date_to, self._auth())

    def get_balance_sheet(self, as_of_date=''):
        return anvil.server.call('get_balance_sheet', as_of_date, self._auth())

    def get_contract_profitability(self, contract_number=None):
        """Enhanced: shows purchase cost, import breakdown, landed cost, revenue, gross profit."""
        return anvil.server.call('get_contract_profitability', contract_number, self._auth())

    # --- Payable Tracking ---
    def get_contract_payable_status(self, contract_number=None):
        """Per-contract: total, paid, remaining, payment history, import costs."""
        return anvil.server.call('get_contract_payable_status', contract_number, self._auth())

    # --- Accounts ---
    def get_bank_accounts(self):
        """Cash + all bank sub-accounts for dropdowns."""
        return anvil.server.call('get_bank_accounts', self._auth())

    def get_chart_of_accounts(self):
        return anvil.server.call('get_chart_of_accounts', self._auth())

    def get_account_balance(self, account_code, as_of_date=''):
        return anvil.server.call('get_account_balance', account_code, as_of_date, self._auth())

    # --- Expenses ---
    def get_expenses(self, date_from='', date_to='', category=''):
        return anvil.server.call('get_expenses', date_from, date_to, category, self._auth())

    def add_expense(self, data):
        return anvil.server.call('add_expense', data, self._auth())

    def delete_expense(self, expense_id):
        return anvil.server.call('delete_expense', expense_id, self._auth())

    # --- Ledger ---
    def get_ledger_entries(self, account_id='', date_from='', date_to=''):
        # السيرفر يتوقّع: account_code, date_from, date_to, ref_type, token_or_email — لا نمرّر التوكن مكان ref_type
        return anvil.server.call(
            'get_ledger_entries',
            account_id,
            date_from,
            date_to,
            None,  # ref_type
            self._auth(),
        )

    # --- Setup ---
    def seed_accounts(self):
        """Seed default accounts (now includes bank sub-accounts 1011/1012/1013)."""
        return anvil.server.call('seed_accounts', self._auth())

    def migrate_import_costs(self):
        """ONE-TIME: reclassify old import costs from 5100 to 1200 Inventory."""
        return anvil.server.call('migrate_import_costs_to_inventory', self._auth())

    def migrate_old_contracts(self, supplier_id, currency='USD', dry_run=False):
        """ONE-TIME: import old contracts into accounting system."""
        return anvil.server.call('migrate_old_contracts', supplier_id, currency, dry_run, self._auth())

    # --- Currency ---
    def get_exchange_rates(self):
        return anvil.server.call('get_exchange_rates', self._auth())

    def set_exchange_rate(self, currency_code, rate_to_egp):
        return anvil.server.call('set_exchange_rate', currency_code, rate_to_egp, self._auth())

    def delete_exchange_rate(self, currency_code):
        return anvil.server.call('delete_exchange_rate', currency_code, self._auth())

    # --- Treasury & Opening Balances ---
    def get_treasury_summary(self):
        return anvil.server.call('get_treasury_summary', self._auth())

    def get_opening_balances(self, entity_type=''):
        return anvil.server.call('get_opening_balances', entity_type, self._auth())

    def set_opening_balance(self, name, entity_type, amount):
        return anvil.server.call('set_opening_balance', name, entity_type, amount, self._auth())

    def post_opening_balances(self, financial_year):
        """Post opening balances from opening_balances table as one JE to ledger (Jan 1 of year). Idempotent: fails if already posted."""
        return anvil.server.call('post_opening_balances', financial_year, self._auth())

    def get_cash_bank_statement(self, account_code=None, date_from=None, date_to=None):
        """كشف حساب النقدية والبنك — كل الحركات بالمبالغ والتواريخ."""
        return anvil.server.call(
            'get_cash_bank_statement', account_code, date_from, date_to, self._auth()
        )

    def get_vat_report(self, as_of_date=None, date_from=None, date_to=None):
        """تقرير الضريبة: ليك (2110) وعليك (2100) والرصيد الصافي."""
        return anvil.server.call(
            'get_vat_report', as_of_date, date_from, date_to, self._auth()
        )

    def settle_vat_for_period(self, date_from, date_to, settlement_account=None):
        """تسوية الضريبة لفترة (يدوي). يلتزم بقفل الفترة."""
        return anvil.server.call(
            'settle_vat_for_period', date_from, date_to, settlement_account, self._auth()
        )

    def create_treasury_transaction(self, transaction_type, amount, transaction_date, description, from_account=None, to_account=None):
        return anvil.server.call(
            'create_treasury_transaction', transaction_type, amount, transaction_date, description, from_account, to_account, self._auth()
        )

    def get_cash_flow_report(self, date_from, date_to):
        return anvil.server.call('get_cash_flow_report', date_from, date_to, self._auth())

    def generate_report(self, report_name, filters):
        return anvil.server.call('generate_report', report_name, filters, self._auth())

    def export_report(self, report_name, filters, format='csv'):
        return anvil.server.call('export_report', report_name, filters, format, self._auth())

    def get_advanced_account_statement(self, filters):
        """Ledger-only advanced account statement. filters: entity_type, entity_id, date_from, date_to, invoice_id, transaction_type, include_aging."""
        filters = filters or {}
        return anvil.server.call(
            'get_advanced_account_statement',
            filters.get('entity_type', 'customer'),
            filters.get('entity_id'),
            filters.get('date_from'),
            filters.get('date_to'),
            filters.get('invoice_id'),
            filters.get('transaction_type'),
            bool(filters.get('include_aging')),
            self._auth(),
        )

    def get_customer_summary(self):
        return anvil.server.call('get_customer_summary', self._auth())

    def get_supplier_summary(self):
        return anvil.server.call('get_supplier_summary', self._auth())

    def get_period_locks(self, year=None):
        return anvil.server.call('get_period_locks', year, self._auth())

    def close_period(self, year, month):
        return anvil.server.call('close_period', year, month, self._auth())

    def reopen_period(self, year, month):
        return anvil.server.call('reopen_period', year, month, self._auth())

    def close_financial_year(self, year):
        return anvil.server.call('close_financial_year', year, self._auth())

    # --- Navigation ---
    def open_suppliers(self):
        open_form('SuppliersForm')

    def open_inventory(self):
        open_form('InventoryForm')

    def open_purchase_invoices(self):
        open_form('PurchaseInvoicesForm')

    def open_customer_summary(self):
        open_form('CustomerSummaryForm')

    def open_supplier_summary(self):
        open_form('SupplierSummaryForm')

    def go_back(self):
        try:
            anvil.js.window.location.hash = '#admin'
        except Exception:
            pass
        open_form('AdminPanel')
        return True

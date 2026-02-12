# -*- coding: utf-8 -*-
"""
FULL SCENARIO VERIFICATION TEST
================================
Simulates the complete lifecycle with actual numbers.
Run:  python server_code/tests/test_full_scenario.py
"""

import os
import sys
import unittest
from datetime import date, datetime
from unittest.mock import MagicMock
import json
import uuid
import io

# Force UTF-8 output (only when running locally, skip in Anvil's DummyStdout)
try:
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass

# Setup path
try:
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    _root = os.getcwd()
if _root and _root not in sys.path:
    sys.path.insert(0, _root)


# ============================================================
# In-memory database mock (replaces app_tables)
# ============================================================
class InMemoryTable:
    def __init__(self, name):
        self.name = name
        self._rows = []

    def add_row(self, **kwargs):
        row = InMemoryRow(kwargs, self)
        self._rows.append(row)
        return row

    def search(self, **filters):
        results = []
        for row in self._rows:
            match = True
            for k, v in filters.items():
                if row.get(k) != v:
                    match = False
                    break
            if match:
                results.append(row)
        return results

    def get(self, **filters):
        for row in self._rows:
            match = True
            for k, v in filters.items():
                if row.get(k) != v:
                    match = False
                    break
            if match:
                return row
        return None

    def clear(self):
        self._rows = []


class InMemoryRow:
    def __init__(self, data, table):
        self._data = dict(data)
        self._table = table

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]

    def update(self, **kwargs):
        self._data.update(kwargs)

    def delete(self):
        self._table._rows = [r for r in self._table._rows if r is not self]


tables = {
    'chart_of_accounts': InMemoryTable('chart_of_accounts'),
    'ledger': InMemoryTable('ledger'),
    'suppliers': InMemoryTable('suppliers'),
    'purchase_invoices': InMemoryTable('purchase_invoices'),
    'import_costs': InMemoryTable('import_costs'),
    'inventory': InMemoryTable('inventory'),
    'expenses': InMemoryTable('expenses'),
    'quotations': InMemoryTable('quotations'),
    'contracts': InMemoryTable('contracts'),
}


class _AppTablesProxy:
    def __getattr__(self, name):
        if name in tables:
            return tables[name]
        raise AttributeError(f"No table named '{name}'")


# ============================================================
# Mock anvil modules
# ============================================================
def _setup_mocks():
    mock_anvil = MagicMock()
    mock_server = MagicMock()

    # callable decorator: just return the function as-is
    def _callable_decorator(*args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            return args[0]
        def wrapper(fn):
            return fn
        return wrapper

    mock_server.callable = _callable_decorator
    mock_anvil.server = mock_server

    mock_tables = MagicMock()
    mock_tables.app_tables = _AppTablesProxy()
    mock_anvil.tables = mock_tables
    mock_anvil.secrets = MagicMock()
    mock_anvil.secrets.get_secret = MagicMock(return_value=None)
    mock_anvil.users = MagicMock()
    mock_anvil.files = MagicMock()
    mock_anvil.files.data_files = MagicMock()
    mock_anvil.google = MagicMock()
    mock_anvil.google.auth = MagicMock()
    mock_anvil.google.drive = MagicMock()
    mock_anvil.google.drive.app_files = MagicMock()
    mock_anvil.google.mail = MagicMock()
    mock_anvil.js = MagicMock()

    sys.modules['anvil'] = mock_anvil
    sys.modules['anvil.server'] = mock_server
    sys.modules['anvil.tables'] = mock_tables
    sys.modules['anvil.secrets'] = mock_anvil.secrets
    sys.modules['anvil.users'] = mock_anvil.users
    sys.modules['anvil.files'] = mock_anvil.files
    sys.modules['anvil.google'] = mock_anvil.google
    sys.modules['anvil.google.auth'] = mock_anvil.google.auth
    sys.modules['anvil.google.drive'] = mock_anvil.google.drive
    sys.modules['anvil.google.mail'] = mock_anvil.google.mail
    sys.modules['anvil.js'] = mock_anvil.js

    # Mock AuthManager
    mock_auth = MagicMock()
    mock_auth.validate_token = MagicMock(return_value={'valid': True, 'user': {'email': 'test@helwan.com'}})
    mock_auth.is_admin = MagicMock(return_value=True)
    mock_auth.is_admin_by_email = MagicMock(return_value=True)
    mock_auth.check_permission = MagicMock(return_value=True)
    sys.modules['AuthManager'] = mock_auth

    # Mock auth_utils
    mock_auth_utils = MagicMock()
    mock_auth_utils.get_utc_now = lambda: datetime.utcnow()
    sys.modules['auth_utils'] = mock_auth_utils


_setup_mocks()

from server_code import accounting

# Patch to use our in-memory tables
accounting.app_tables = _AppTablesProxy()

# Patch AuthManager
_mock_auth_mgr = MagicMock()
_mock_auth_mgr.validate_token = MagicMock(return_value={'valid': True, 'user': {'email': 'test@helwan.com'}})
_mock_auth_mgr.is_admin = MagicMock(return_value=True)
_mock_auth_mgr.is_admin_by_email = MagicMock(return_value=True)
_mock_auth_mgr.check_permission = MagicMock(return_value=True)
accounting.AuthManager = _mock_auth_mgr
accounting.get_utc_now = lambda: datetime.utcnow()


class TestFullScenario(unittest.TestCase):

    def setUp(self):
        for t in tables.values():
            t.clear()
        result = accounting.seed_default_accounts('test@helwan.com')
        self.assertTrue(result['success'], f"Seed failed: {result}")
        tables['suppliers'].add_row(
            id='SUP-001', name='Shanghai Machinery Co.',
            contact='Zhang Wei', email='zhang@shanghai-mach.com',
            phone='+86-21-5555-1234', is_active=True,
        )
        tables['contracts'].add_row(
            contract_number='C - Q2026-001 / 1 - 2026',
            quotation_number='Q2026-001',
            fob_cost=None, cylinder_cost=None, supplier_id=None,
            purchase_invoice_id=None, currency=None, updated_at=None,
        )

    # ================================================================
    # 1) ZERO dependency on currency_manager
    # ================================================================
    def test_01_no_currency_manager_dependency(self):
        """Verify accounting.py has ZERO references to currency_manager."""
        import inspect
        source = inspect.getsource(accounting)
        self.assertNotIn('currency_manager', source)
        self.assertNotIn('convert_to_egp', source)
        self.assertNotIn('ExchangeRate', source)
        self.assertNotIn('currency_convert', source)
        print("\n[PASS] 1) ZERO dependency on currency_manager confirmed")
        print("   - No imports of currency_manager")
        print("   - No convert_to_egp function")
        print("   - No exchange_rate logic in accounting engine")

    # ================================================================
    # 2) EGP-only ledger
    # ================================================================
    def test_02_ledger_is_egp_only(self):
        """Verify post_journal_entry has NO currency parameter."""
        import inspect
        sig = inspect.signature(accounting.post_journal_entry)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ['entry_date', 'entries', 'description', 'ref_type', 'ref_id', 'user_email'])
        self.assertNotIn('currency', params)
        self.assertNotIn('exchange_rate', params)
        result = accounting.post_journal_entry(
            date.today(),
            [{'account_code': '1000', 'debit': 100, 'credit': 0},
             {'account_code': '2000', 'debit': 0, 'credit': 100}],
            'Test EGP', 'journal', 'TEST-01', 'test@helwan.com'
        )
        self.assertTrue(result['success'])
        entry = tables['ledger']._rows[0]
        self.assertNotIn('currency', entry._data)
        self.assertNotIn('exchange_rate', entry._data)

        print("\n[PASS] 2) All ledger postings are EGP-only confirmed")
        print(f"   post_journal_entry({', '.join(params)})")
        print(f"   Ledger row keys: {sorted(entry._data.keys())}")
        print("   NO currency column, NO exchange_rate column")
        print("   Reports aggregate debit/credit directly (single currency)")

    # ================================================================
    # 3) 1200 vs 1210 usage
    # ================================================================
    def test_03_inventory_account_usage(self):
        """Verify 1210 exists but is NOT used in postings."""
        codes = [a[0] for a in accounting.DEFAULT_ACCOUNTS]
        self.assertIn('1210', codes)
        self.assertIn('1200', codes)

        # Read the actual source file to check
        src_path = os.path.join(_root, 'server_code', 'accounting.py')
        with open(src_path, 'r', encoding='utf-8') as f:
            source = f.read()

        # create_contract_purchase uses 1200
        # Find the function and check it
        import re
        ccp_match = re.search(r'def create_contract_purchase\(.*?\n(?=\n@|\ndef )', source, re.DOTALL)
        self.assertIsNotNone(ccp_match, "create_contract_purchase not found")
        ccp_src = ccp_match.group(0)
        self.assertIn("'1200'", ccp_src, "create_contract_purchase should use 1200")
        self.assertNotIn("'1210'", ccp_src, "create_contract_purchase should NOT use 1210")

        # add_import_cost uses 1200
        aic_match = re.search(r'def add_import_cost\(.*?\n(?=\n@|\ndef )', source, re.DOTALL)
        self.assertIsNotNone(aic_match, "add_import_cost not found")
        aic_src = aic_match.group(0)
        self.assertIn("inventory_account = '1200'", aic_src)
        self.assertNotIn("'1210'", aic_src)

        # sell_inventory uses 1200
        si_match = re.search(r'def sell_inventory\(.*?\n(?=\n@|\ndef )', source, re.DOTALL)
        self.assertIsNotNone(si_match, "sell_inventory not found")
        si_src = si_match.group(0)
        self.assertIn("'1200'", si_src)
        self.assertNotIn("'1210'", si_src)

        print("\n[PASS] 3) Inventory account usage:")
        print("   - 1200 (Inventory): Used for ALL postings")
        print("     * create_contract_purchase: DR 1200, CR 2000")
        print("     * add_import_cost: DR 1200, CR Cash/Bank")
        print("     * sell_inventory: DR 5000, CR 1200")
        print("   - 1210 (Purchase in Transit): Defined in chart of accounts ONLY")
        print("     * Available for future manual journal entries")
        print("     * NOT used by any automated posting function")

    # ================================================================
    # 4) Full scenario with actual numbers
    # ================================================================
    def test_04_full_scenario(self):
        tables['ledger'].clear()

        print("\n" + "=" * 70)
        print("FULL SCENARIO SIMULATION")
        print("=" * 70)

        # STEP 1: Create Contract Purchase (FOB 60,000)
        print("\n--- STEP 1: Create Contract Purchase (FOB 60,000) ---")
        result = accounting.create_contract_purchase(
            'C - Q2026-001 / 1 - 2026', 60000.00, 0.00, 'SUP-001', 'USD', 'test@helwan.com')
        self.assertTrue(result['success'], f"create_contract_purchase failed: {result}")
        invoice_id = result['invoice_id']
        inventory_id = result['inventory_id']
        print(f"   Invoice: {result['invoice_number']}, Total: {result['total']:,.2f}")
        print(f"   Journal: DR 1200 Inventory 60,000 / CR 2000 AP 60,000")

        inv_item = tables['inventory'].get(id=inventory_id)
        self.assertEqual(inv_item.get('status'), 'in_transit')
        self.assertEqual(inv_item.get('purchase_cost'), 60000.00)
        self.assertEqual(inv_item.get('total_cost'), 60000.00)
        print(f"   Inventory status: {inv_item.get('status')}, total_cost: {inv_item.get('total_cost'):,.2f}")
        self._print_ledger("After Step 1")

        # STEP 2: Add Import Cost (shipping 5,000 - cash)
        print("\n--- STEP 2: Add Import Cost (shipping 5,000 via cash) ---")
        result = accounting.add_import_cost(
            invoice_id, 'shipping', 5000.00, 'Ocean freight Shanghai-Alexandria',
            '2026-02-10', 'cash', None, 'test@helwan.com')
        self.assertTrue(result['success'], f"add_import_cost shipping failed: {result}")
        print(f"   Journal: DR 1200 Inventory 5,000 / CR 1000 Cash 5,000")
        inv_item = tables['inventory'].get(id=inventory_id)
        self.assertEqual(inv_item.get('import_costs_total'), 5000.00)
        self.assertEqual(inv_item.get('total_cost'), 65000.00)
        print(f"   Inventory import_costs_total: {inv_item.get('import_costs_total'):,.2f}")
        print(f"   Inventory total_cost: {inv_item.get('total_cost'):,.2f}")
        self._print_ledger("After Step 2")

        # STEP 3: Add Import Cost (customs 3,000 - NBE)
        print("\n--- STEP 3: Add Import Cost (customs 3,000 via NBE) ---")
        result = accounting.add_import_cost(
            invoice_id, 'customs', 3000.00, 'Customs clearance fees',
            '2026-02-11', 'nbe', None, 'test@helwan.com')
        self.assertTrue(result['success'], f"add_import_cost customs failed: {result}")
        print(f"   Journal: DR 1200 Inventory 3,000 / CR 1012 NBE 3,000")
        inv_item = tables['inventory'].get(id=inventory_id)
        self.assertEqual(inv_item.get('import_costs_total'), 8000.00)
        self.assertEqual(inv_item.get('total_cost'), 68000.00)
        print(f"   Inventory import_costs_total: {inv_item.get('import_costs_total'):,.2f}")
        print(f"   Inventory total_cost (LANDED COST): {inv_item.get('total_cost'):,.2f}")
        self._print_ledger("After Step 3")

        # STEP 4: Partial Supplier Payment (30,000 via CIB)
        print("\n--- STEP 4: Partial Supplier Payment (30,000 via CIB) ---")
        result = accounting.record_supplier_payment(
            invoice_id, 30000.00, 'cib', '2026-02-12', 'test@helwan.com')
        self.assertTrue(result['success'], f"record_supplier_payment failed: {result}")
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['paid_amount'], 30000.00)
        print(f"   Journal: DR 2000 AP 30,000 / CR 1011 CIB 30,000")
        print(f"   Invoice status: {result['status']}, paid: {result['paid_amount']:,.2f}")
        self._print_ledger("After Step 4")

        # STEP 5: Receive Inventory (no journal entry)
        print("\n--- STEP 5: Receive Inventory (in_transit -> in_stock) ---")
        ledger_before = len(tables['ledger']._rows)
        result = accounting.receive_inventory(inventory_id, 'Alexandria Warehouse', 'test@helwan.com')
        self.assertTrue(result['success'], f"receive_inventory failed: {result}")
        self.assertEqual(result['status'], 'in_stock')
        ledger_after = len(tables['ledger']._rows)
        self.assertEqual(ledger_before, ledger_after, "receive should NOT create ledger entries")
        print(f"   Status: in_transit -> in_stock")
        print(f"   NO journal entry (no P&L impact)")
        print(f"   Ledger entries unchanged: {ledger_after}")

        # STEP 6: Sell at 90,000
        print("\n--- STEP 6: Sell at 90,000 ---")
        result = accounting.sell_inventory(
            inventory_id, 'C - Q2026-001 / 1 - 2026', 90000.00, '2026-02-15', 'test@helwan.com')
        self.assertTrue(result['success'], f"sell_inventory failed: {result}")
        self.assertEqual(result['landed_cost'], 68000.00)
        self.assertEqual(result['revenue'], 90000.00)
        self.assertEqual(result['gross_profit'], 22000.00)
        print(f"   COGS Journal: DR 5000 COGS 68,000 / CR 1200 Inventory 68,000")
        print(f"   Revenue Journal: DR 1100 AR 90,000 / CR 4000 Revenue 90,000")
        print(f"   Landed Cost: {result['landed_cost']:,.2f}")
        print(f"   Revenue: {result['revenue']:,.2f}")
        print(f"   Gross Profit: {result['gross_profit']:,.2f}")
        print(f"   Margin: {result['margin_pct']:.1f}%")

        # === PRINT ALL REPORTS ===
        self._print_ledger("FINAL COMPLETE LEDGER")

        # TRIAL BALANCE
        print("\n   === TRIAL BALANCE ===")
        tb = accounting.get_trial_balance(token_or_email='test@helwan.com')
        self.assertTrue(tb['success'])
        self.assertTrue(tb['is_balanced'],
                        f"Trial balance NOT balanced! DR={tb['total_debit']}, CR={tb['total_credit']}")
        print(f"   {'Code':<8} {'Account':<30} {'Debit':>12} {'Credit':>12}")
        print(f"   {'-'*8} {'-'*30} {'-'*12} {'-'*12}")
        bal_map = {}
        for r in tb['rows']:
            if r['debit'] > 0 or r['credit'] > 0:
                print(f"   {r['code']:<8} {r['name_en']:<30} {r['debit']:>12,.2f} {r['credit']:>12,.2f}")
                bal_map[r['code']] = r
        print(f"   {'-'*8} {'-'*30} {'-'*12} {'-'*12}")
        print(f"   {'TOTALS':<39} {tb['total_debit']:>12,.2f} {tb['total_credit']:>12,.2f}")
        print(f"   Balanced: {'YES' if tb['is_balanced'] else 'NO'}")

        # TB assertions
        self.assertEqual(bal_map.get('1000', {}).get('credit', 0), 5000.00)
        self.assertEqual(bal_map.get('1011', {}).get('credit', 0), 30000.00)
        self.assertEqual(bal_map.get('1012', {}).get('credit', 0), 3000.00)
        self.assertEqual(bal_map.get('1100', {}).get('debit', 0), 90000.00)
        self.assertEqual(bal_map.get('2000', {}).get('credit', 0), 30000.00)
        self.assertEqual(bal_map.get('4000', {}).get('credit', 0), 90000.00)
        self.assertEqual(bal_map.get('5000', {}).get('debit', 0), 68000.00)

        # INCOME STATEMENT
        # API returns: revenue.total, cogs.total, gross_profit, expenses.total, net_profit
        print("\n   === INCOME STATEMENT (2026) ===")
        inc = accounting.get_income_statement('2026-01-01', '2026-12-31', token_or_email='test@helwan.com')
        self.assertTrue(inc['success'])
        rev_total = inc['revenue']['total']
        cogs_total = inc['cogs']['total']
        gross_profit = inc['gross_profit']
        opex_total = inc['expenses']['total']
        net_profit = inc['net_profit']
        self.assertEqual(rev_total, 90000.00)
        self.assertEqual(cogs_total, 68000.00)
        self.assertEqual(gross_profit, 22000.00)
        self.assertEqual(opex_total, 0.00)  # No operating expenses in this scenario
        self.assertEqual(net_profit, 22000.00)
        print(f"   Revenue:")
        for r in inc['revenue']['items']:
            print(f"     {r['code']} {r['name_en']:<30} {r['amount']:>12,.2f}")
        print(f"   {'Total Revenue':<38} {rev_total:>12,.2f}")
        print(f"   COGS:")
        for r in inc['cogs']['items']:
            print(f"     {r['code']} {r['name_en']:<30} {r['amount']:>12,.2f}")
        print(f"   {'Total COGS':<38} {cogs_total:>12,.2f}")
        print(f"   {'GROSS PROFIT':<38} {gross_profit:>12,.2f}")
        print(f"   Operating Expenses:")
        for r in inc['expenses']['items']:
            print(f"     {r['code']} {r['name_en']:<30} {r['amount']:>12,.2f}")
        print(f"   {'Total OpEx':<38} {opex_total:>12,.2f}")
        print(f"   {'='*52}")
        print(f"   {'NET PROFIT':<38} {net_profit:>12,.2f}")

        # BALANCE SHEET
        # API returns: assets.items/.total, liabilities.items/.total, equity.items/.total
        print("\n   === BALANCE SHEET (as of 2026-12-31) ===")
        bs = accounting.get_balance_sheet('2026-12-31', token_or_email='test@helwan.com')
        self.assertTrue(bs['success'])
        a_total = bs['assets']['total']
        l_total = bs['liabilities']['total']
        e_total = bs['equity']['total']
        print(f"   ASSETS:")
        for a in bs['assets']['items']:
            print(f"     {a['code']} {a['name_en']:<30} {a['balance']:>12,.2f}")
        print(f"   {'Total Assets':<38} {a_total:>12,.2f}")
        print(f"   LIABILITIES:")
        for li in bs['liabilities']['items']:
            print(f"     {li['code']} {li['name_en']:<30} {li['balance']:>12,.2f}")
        print(f"   {'Total Liabilities':<38} {l_total:>12,.2f}")
        print(f"   EQUITY (incl. Retained Earnings):")
        for eq in bs['equity']['items']:
            print(f"     {eq['code']} {eq['name_en']:<30} {eq['balance']:>12,.2f}")
        print(f"   {'Total Equity':<38} {e_total:>12,.2f}")
        print(f"   {'='*52}")
        print(f"   A = L + E: {a_total:,.2f} = {l_total:,.2f} + {e_total:,.2f}")
        self.assertTrue(bs['is_balanced'], f"Balance sheet NOT balanced!")

        # BS assertions
        # Assets: AR 90,000 - Cash 5,000 - CIB 30,000 - NBE 3,000 + Inventory 0 = 52,000
        self.assertEqual(a_total, 52000.00, f"Assets: expected 52,000 got {a_total}")
        # Liabilities: AP 30,000
        self.assertEqual(l_total, 30000.00, f"Liabilities: expected 30,000 got {l_total}")
        # Equity: Retained Earnings = Net Profit = 22,000
        self.assertEqual(e_total, 22000.00, f"Equity: expected 22,000 got {e_total}")

        print("\n   [PASS] Full scenario verified with all reports balanced")

    # ================================================================
    # 5) Idempotency: seed_accounts
    # ================================================================
    def test_05_seed_accounts_idempotent(self):
        print("\n--- IDEMPOTENCY: seed_accounts ---")
        initial_count = len(tables['chart_of_accounts']._rows)
        print(f"   After 1st seed: {initial_count} accounts")

        result = accounting.seed_default_accounts('test@helwan.com')
        self.assertTrue(result['success'])
        self.assertEqual(result['created'], 0, "Second seed should create 0")
        self.assertEqual(result['skipped'], initial_count)
        after = len(tables['chart_of_accounts']._rows)
        self.assertEqual(initial_count, after)
        print(f"   After 2nd seed: {after} accounts (created=0, skipped={result['skipped']})")

        result3 = accounting.seed_default_accounts('test@helwan.com')
        self.assertEqual(result3['created'], 0)
        after3 = len(tables['chart_of_accounts']._rows)
        self.assertEqual(initial_count, after3)
        print(f"   After 3rd seed: {after3} accounts (created=0, skipped={result3['skipped']})")
        print(f"   [PASS] seed_accounts is IDEMPOTENT - no duplicates")

    # ================================================================
    # 5) Idempotency: migrate_import_costs
    # ================================================================
    def test_06_migrate_import_costs_idempotent(self):
        print("\n--- IDEMPOTENCY: migrate_import_costs ---")
        old_cost_id = 'OLD-IC-001'
        tables['import_costs'].add_row(
            id=old_cost_id, purchase_invoice_id='OLD-PI-001',
            cost_type='shipping', amount=2000.00, date=date(2025, 12, 15),
            description='Old shipping cost', created_by='old@helwan.com',
            created_at=datetime.utcnow(),
        )
        tables['ledger'].add_row(
            id='OLD-LE-001', transaction_id='OLD-TXN-001', date=date(2025, 12, 15),
            account_code='5100', debit=2000.00, credit=0.0,
            description='Old import cost', reference_type='import_cost',
            reference_id=old_cost_id, created_by='old@helwan.com',
            created_at=datetime.utcnow(),
        )
        tables['ledger'].add_row(
            id='OLD-LE-002', transaction_id='OLD-TXN-001', date=date(2025, 12, 15),
            account_code='1000', debit=0.0, credit=2000.00,
            description='Old import cost', reference_type='import_cost',
            reference_id=old_cost_id, created_by='old@helwan.com',
            created_at=datetime.utcnow(),
        )
        ledger_before = len(tables['ledger']._rows)
        print(f"   Ledger entries before migration: {ledger_before}")

        result1 = accounting.migrate_import_costs_to_inventory('test@helwan.com')
        self.assertTrue(result1['success'], f"Migration failed: {result1}")
        self.assertEqual(result1['migrated'], 1)
        ledger_after1 = len(tables['ledger']._rows)
        print(f"   After 1st migration: {ledger_after1} entries (migrated={result1['migrated']})")

        result2 = accounting.migrate_import_costs_to_inventory('test@helwan.com')
        self.assertTrue(result2['success'])
        self.assertEqual(result2['migrated'], 0, "2nd migration should migrate 0")
        ledger_after2 = len(tables['ledger']._rows)
        self.assertEqual(ledger_after1, ledger_after2, "No new ledger entries on 2nd run")
        print(f"   After 2nd migration: {ledger_after2} entries (migrated=0, skipped={result2['skipped']})")

        result3 = accounting.migrate_import_costs_to_inventory('test@helwan.com')
        self.assertEqual(result3['migrated'], 0)
        ledger_after3 = len(tables['ledger']._rows)
        self.assertEqual(ledger_after1, ledger_after3)
        print(f"   After 3rd migration: {ledger_after3} entries (migrated=0)")
        print(f"   [PASS] migrate_import_costs is IDEMPOTENT - no duplicate entries")

    # ================================================================
    # Helper
    # ================================================================
    def _print_ledger(self, title="LEDGER"):
        print(f"\n   {title}:")
        print(f"   {'Date':<12} {'Account':<8} {'Debit':>12} {'Credit':>12} {'Description'}")
        print(f"   {'-'*12} {'-'*8} {'-'*12} {'-'*12} {'-'*40}")
        for row in tables['ledger']._rows:
            d = row.get('date', '')
            if isinstance(d, date):
                d = d.isoformat()
            acct = row.get('account_code', '')
            debit = row.get('debit', 0)
            credit = row.get('credit', 0)
            desc = (row.get('description', '') or '')[:50]
            if debit > 0 or credit > 0:
                print(f"   {str(d):<12} {acct:<8} {debit:>12,.2f} {credit:>12,.2f} {desc}")
        total_dr = sum(r.get('debit', 0) for r in tables['ledger']._rows)
        total_cr = sum(r.get('credit', 0) for r in tables['ledger']._rows)
        print(f"   {'-'*12} {'-'*8} {'-'*12} {'-'*12}")
        print(f"   {'TOTALS':<21} {total_dr:>12,.2f} {total_cr:>12,.2f}")


if __name__ == '__main__':
    unittest.main(verbosity=2)

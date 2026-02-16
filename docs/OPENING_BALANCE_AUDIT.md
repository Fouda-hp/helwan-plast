# Opening Balance Audit & Correction

## PART 1 — Audit (before fix)

- **opening_balances table:** Exists (name, type, opening_balance, updated_at, updated_by). Used for bank, customer, supplier.
- **Cash & Bank (Treasury):** `get_treasury_summary` used `opening_balance + ledger_balance` → **inconsistency**.
- **Bank statement:** `get_cash_bank_statement` used `opening_map + pre_bal` and prepended synthetic "Opening balance" row → **inconsistency**.
- **Customer summary:** `get_customer_summary` used `opening_balance + total_sales - total_collections` from table → **inconsistency**.
- **Supplier summary:** `get_supplier_summary` used `opening_balance + total_purchases - total_payments` from table → **inconsistency**.
- **Trial Balance / Balance Sheet:** Already ledger-only via `_get_all_balances(ledger)` — no opening_balances read. **OK.**

**Conclusion:** Reports were adding opening balance separately (hybrid). Ledger was bypassed for opening amounts.

## PART 2 — Correction applied

1. **`post_opening_balances(financial_year)`** uses **`post_journal_entry`** only (does not write directly to `app_tables.ledger`). It:
   - Reads `opening_balances` table.
   - Builds an entries list and calls `post_journal_entry` to create a **single** journal entry dated **1 Jan** of the financial year.
   - type=bank (name=account code): DR if asset and amount>0, CR if overdraft; CR if liability and amount>0.
   - type=customer: DR 1100, reference_id=name (for sub-ledger).
   - type=supplier: CR 2000, reference_id=name.
   - Balancing amount to **3000 (Opening Equity)**. JE is fully balanced.
   - Idempotent: returns error if this year already posted.

2. **Hybrid logic removed:**
   - `get_treasury_summary`: uses only ledger; `current_balance = ledger_balance`.
   - `get_cash_bank_statement`: balance at start of period = ledger only (`pre_entries`); no opening_balances read.
   - `get_customer_summary`: opening from ledger (1100, reference_type='opening_balance', by reference_id).
   - `get_supplier_summary`: opening from ledger (2000, reference_type='opening_balance', by reference_id).

3. **`get_opening_balances` / `set_opening_balance`:** Still exist for UI to manage rows in `opening_balances` table. After user runs **Post Opening Balances**, all report totals come from ledger only.

## PART 3 — Validation tests

- `server_code/tests/test_opening_balances.py`:
  - Bank opening appears in ledger after `post_opening_balances`; Trial Balance and Balance Sheet use ledger only.
  - No double counting.
  - Idempotent: second post for same year fails.
  - Treasury summary uses ledger only (no opening_balances table for balance).

## PART 4 — Result

- Opening balances are visible in General Ledger once posted.
- Trial Balance and Balance Sheet match ledger exactly.
- No artificial "Opening Balance" addition in reports; all from ledger aggregation.
- Bank overdraft logic unchanged (balance sheet presentation already handles overdraft as liability).

**Ledger aggregation:** Trial Balance, Balance Sheet, Treasury, and bank statement aggregate from the ledger **without** filtering by `reference_type`. Only get_customer_summary and get_supplier_summary filter by `reference_type='opening_balance'` when computing **opening per customer/supplier** (sub-ledger breakdown); their main totals are still from full ledger.

**1100 / 2000 opening lines and reconciliation:** Opening balance lines use `reference_id` = **customer name** (1100) or **supplier name** (2000) only — one line per entity, grouped by that name for sub-ledger display. Payment matching uses `reference_type` in `('purchase_invoice', 'payment')` and `reference_id` = **invoice_id**. So invoice-level remaining and payment history never include opening_balance rows; reconciliation logic is unchanged.

**Not modified:** FX, VAT, period lock, payment posting, inventory logic.

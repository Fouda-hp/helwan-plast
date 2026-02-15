# Accounting Reports and Period Lock

## System context

- **Ledger**: EGP-only. All amounts in reports are from ledger aggregation unless stated (e.g. `supplier_amount_egp` stored at posting).
- **Purchase invoices**: Post to **1210** (Inventory in Transit); **move_purchase_to_inventory** moves to **1200** (Available Inventory).
- **Supplier liability**: Ledger account **2000** only (no invoice-table balance shortcuts).
- **FX**: Differences posted per payment to **4110** (gain) / **6110** (loss). `supplier_amount_egp` stored at posting.
- **inventory_moved**: Boolean on purchase_invoices; used in reports where needed.

---

## 1. Inventory Valuation Report (Transit vs Available)

**Function:** `get_inventory_valuation()`

**Purpose:** Separate valuation of Inventory in Transit (1210) and Available Inventory (1200), strictly from the ledger.

**Output:**
- `transit_total`: Net balance (debit − credit) on account **1210**.
- `available_total`: Net balance (debit − credit) on account **1200**.
- `grand_total`: transit_total + available_total.
- `by_invoice`: List of `{ invoice_id, status: "transit" | "available", value_egp }`.

**Logic:**
- **Transit:** For each invoice that has 1210 activity, `value_egp = _sum_1210_balance_for_invoice(invoice_id)` (debit − credit). Invoices are derived from ledger (reference_type purchase_invoice / import_cost / import_cost_payment with mapping via import_costs where needed).
- **Available:** DR 1200 grouped by invoice (reference_type purchase_invoice or import_cost, reference_id = invoice_id). CR 1200 grouped by item (reference_type sales_invoice, reference_id = item_id); item → invoice via inventory.purchase_invoice_id. Per-invoice available = sum(DR 1200 for invoice) − sum(CR 1200 for items linked to that invoice).
- Invoices with balance below tolerance (0.01) are excluded from `by_invoice`. Legacy invoices without 1210 are included only if they have 1200 balance.

**No hardcoded totals;** all from ledger (and inventory only for item → invoice mapping).

---

## 2. Detailed Inventory Valuation (Per Machine / Per Invoice)

**Function:** `get_inventory_detailed()`

**Purpose:** Per-invoice breakdown for reporting and reconciliation.

**Per invoice returned:**
- `supplier_amount_egp`: From purchase_invoices (stored at posting).
- `import_cost_total`: Sum of import-related movements on 1210 and 1200 (reference_type import_cost / import_cost_payment, with cost_id → invoice via import_costs).
- `landed_cost`: supplier_amount_egp + import_cost_total.
- `transit_balance`: Net 1210 for this invoice (ledger).
- `available_balance`: Net 1200 for this invoice (DR by invoice − CR by items linked to invoice).
- `inventory_moved`: From purchase_invoices (optional column).
- `sold_flag`: True when 1200 is fully credited (COGS) for this invoice’s items (ledger-driven).

All numeric values use ledger aggregation except `supplier_amount_egp` and `inventory_moved`, which are stored on the invoice.

---

## 3. Supplier Aging Report

**Function:** `get_supplier_aging(as_of_date=None)`

**Default:** `as_of_date` = today.

**Output:** `suppliers`: list of `{ supplier_id, 0_30, 31_60, 61_90, 90_plus, total }` (amounts in EGP).

**Logic:**
- **Remaining per invoice:** From ledger **2000** only (full ledger truth; no reference_type filter):  
  `remaining = sum(CR on 2000 where reference_id=invoice_id) − sum(DR on 2000 where reference_id=invoice_id)`.
- **Age buckets:** Based on **invoice date** (purchase_invoices.date), not payment date. Days = as_of_date − invoice_date → 0–30, 31–60, 61–90, 90+.
- **Tolerance:** Invoices with `|remaining| < 0.01` are treated as fully paid and excluded.
- Amounts are aggregated by supplier_id (from purchase_invoices).

---

## 4. FX Report per Invoice

**Function:** `get_fx_report_per_invoice()`

**Output:** List of `{ invoice_id, booked_egp, paid_egp, fx_gain, fx_loss, net_fx }`.

**Logic:**
- **booked_egp:** Stored `supplier_amount_egp` on purchase_invoices (set at posting).
- **paid_egp:** From ledger: sum of **CR** on bank/cash accounts (1000, 1010, 1011, 1012, 1013) where reference_type=payment and reference_id=invoice_id (minus debits on same).
- **fx_gain:** Sum of credits on account **4110** for that invoice (reference_id=invoice_id, reference_type=payment).
- **fx_loss:** Sum of debits on account **6110** for that invoice.
- **net_fx:** fx_gain − fx_loss.

All paid_egp, fx_gain, fx_loss from ledger only.

---

## 5. Unrealized FX Valuation (Open Liabilities)

**Function:** `get_unrealized_fx(current_rate_provider)`

**Purpose:** Theoretical FX revaluation of **open** supplier balances at a current rate. Reporting only; **no journal entries** are posted.

**Logic (mathematically correct and stable):**
- **remaining_egp:** From ledger 2000: sum(CR) − sum(DR) per reference_id (invoice_id). No reference_type filter — full ledger truth.
- Only open invoices (|remaining_egp| ≥ 0.01) are included.
- **invoice_rate:** `invoice_rate = supplier_amount_egp / original_amount` (strict; do not approximate by ratio original/supplier_egp).
- **Remaining in original currency:** `remaining_original = remaining_egp / invoice_rate`.
- **current_rate_provider:** Callable(invoice_row) or dict-like returning current rate to EGP. Revalued EGP = remaining_original × current_rate.
- **unrealized_fx:** revalued_egp − remaining_egp.
- **Safety:** If original_amount ≤ 0, supplier_amount_egp ≤ 0, or invoice_rate ≤ 0 → unrealized_fx = 0 for that row.

**Output:** List of `{ invoice_id, remaining_egp, revalued_egp, unrealized_fx }`.

**Schema:** Relies on purchase_invoices: `original_amount`, `supplier_amount_egp`. If any guard fails, unrealized_fx is 0.

---

## 6. Period Lock (Accounting Period Lock)

**Table:** `accounting_period_locks` (create in Anvil Data Tables)

| Column    | Type    | Description        |
|----------|--------|--------------------|
| year     | int    | Accounting year    |
| month    | int    | Accounting month   |
| locked   | bool   | True = locked      |
| locked_at| datetime | When locked     |
| locked_by| string | User who locked    |

**Functions:**
- **lock_period(year, month):** Sets locked=True for that year/month (creates row if needed).
- **unlock_period(year, month):** Sets locked=False for that year/month.
- **is_period_locked(date):** Returns True if the year/month of `date` is locked. **If the table does not exist,** raises `RuntimeError` (do not silently allow posting).

**Enforcement:**
- **post_journal_entry** checks `is_period_locked(entry_date)` at the start (after parsing the entry date). If the period is locked, it returns `{'success': False, 'message': 'Accounting period is locked.'}` and **does not post** any lines.
- All posting flows (post_purchase_invoice, record_supplier_payment, add_import_cost, move_purchase_to_inventory, sell_inventory, expense posting, create_journal_entry) go through post_journal_entry, so they are all blocked for locked periods.
- **Draft operations** (create/update draft invoice, etc.) are not blocked; only **posting** is blocked.

---

## 7. Safety Rules (Summary)

- All report totals use **ledger aggregation**; no recalculating balances from invoice.total or paid_amount.
- **\_round2** used consistently for amounts.
- **RESIDUAL_TOLERANCE (0.01)** used for treating tiny residuals as zero and excluding fully paid invoices from aging.
- Existing FX logic (record_supplier_payment, 4110/6110) is unchanged; reports only read ledger and stored fields.
- Reports are **read-only**; no posting.
- Period lock affects only **posting** (journal entries); draft create/update is unaffected.

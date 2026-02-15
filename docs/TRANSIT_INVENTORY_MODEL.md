# Transit Inventory Model (1210 – Inventory in Transit)

## Overview

Purchase invoices for imported machines are now posted to **1210 (Inventory in Transit)** until the machine is received. When received, **move_purchase_to_inventory** moves the balance from 1210 to **1200 (Inventory)**. This keeps the ledger correct: cost sits in 1210 while in transit and in 1200 only after receipt.

## Lifecycle

1. **Draft** → Create purchase invoice (draft).
2. **Post** → `post_purchase_invoice`: DR 1210, DR 2110 (if VAT), CR 2000. `supplier_amount_egp` unchanged.
3. **Partial payments** → `record_supplier_payment`: FX logic unchanged (4110/6110, liability_slice_egp, payment_egp).
4. **Import costs (before arrival)** → `add_import_cost`: DR 1210, CR Bank/Cash.
5. **Move to inventory** → `move_purchase_to_inventory(invoice_id)`: DR 1200, CR 1210 (full accumulated amount). Sets `inventory_moved = True`.
6. **Import costs (after arrival)** → `add_import_cost`: DR 1200, CR Bank/Cash.
7. **Sale** → `sell_inventory`: Allowed only when `inventory_moved == True` (or legacy invoice with no 1210 balance). COGS: DR 5000, CR 1200.

## Schema: purchase_invoices

Add column (in Anvil Data Tables):

| Column           | Type    | Default | Description                                      |
|------------------|---------|--------|--------------------------------------------------|
| inventory_moved   | boolean | False  | False = in transit (cost in 1210); True = moved to inventory (1200). |

If the column is missing, code uses `row.get('inventory_moved', False)`. New postings set `inventory_moved=False` when the column exists. `get_purchase_invoices` returns `inventory_moved` (with try/except so missing column does not break).

## UI

- **Purchase Invoices list**: When status is *Posted* and `inventory_moved` is false, a green **"Move to inventory" / "نقل للمخزون"** button is shown. Clicking it calls `move_purchase_to_inventory(invoice_id)` and refreshes the list.

## move_purchase_to_inventory — review checks

- **total_transit_cost** is **sum(debit − credit)** on account 1210 for this invoice, not sum(debit only). So reversals or credits are correctly netted.
- **Import cost entries** are included in the transit sum: `add_import_cost` posts with **reference_id = invoice_id** (and reference_type = `import_cost`), so all 1210 entries for this invoice can be summed together; `pay_import_cost` uses reference_id = cost_id and is included via a per–import-cost loop.
- **Idempotent**: second call returns error *"Invoice already moved to inventory. Duplicate move is not allowed."* (because `inventory_moved` is True). No duplicate journal entries are posted.

## New / updated server functions

- **move_purchase_to_inventory(invoice_id)**  
  Validates: status = posted, inventory_moved = False. total_transit_cost = sum(debit − credit) on 1210 for this invoice (purchase_invoice + import_cost + import_cost_payment refs). Posts DR 1200 / CR 1210, sets inventory_moved = True. Idempotent: second call returns error, no duplicate JEs.

- **get_transit_balance()**  
  Returns total balance of account 1210 (debits − credits) for reporting.

## Default account

- **1210 – Inventory in Transit** (مخزون في الطريق), type: Asset, parent: 1200.  
  Created by `seed_default_accounts` if missing.

## Legacy invoices

Invoices already posted to 1200 are **not** auto-migrated. They remain as-is. Only **new** postings use 1210. Sale is allowed for legacy invoices (no 1210 balance) without requiring inventory_moved.

## Reporting

- **Supplier balance**: Ledger-based from 2000 only (unchanged).
- **Landed cost**: supplier_amount_egp + import_costs (unchanged).
- **Transit balance**: Use `get_transit_balance()` or sum of 1210 for open invoices where inventory_moved = False.

## Tests

- `server_code/tests/test_transit_inventory.py`: Documents and verifies entries for Tests 1–5 (post 1210, import cost before/after, move, FX unchanged).
- `server_code/tests/test_full_scenario.py`: Updated for transit model (Step 5a: move_purchase_to_inventory; journal prints use 1210 where applicable).

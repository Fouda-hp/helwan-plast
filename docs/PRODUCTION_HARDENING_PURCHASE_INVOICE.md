# Production Hardening: Purchase Invoice & Ledger (EGP-Only)

## Summary of Risk Elimination

| Risk | Mitigation |
|------|------------|
| Runtime subtraction of import costs from supplier liability | **Lock at post time:** `supplier_amount_egp` computed once in `post_purchase_invoice`, stored on `purchase_invoices`, used for CR 2000. Reporting uses stored value or ledger. |
| NULL currency defaulting to EGP (USD posted as EGP) | **Explicit currency required:** Post rejects missing `currency_code`. Create/update set default `EGP` and validate non-EGP requires `exchange_rate` > 0. |
| Duplicate posting only blocked in app | **DB-level protection:** Registry table `posted_purchase_invoice_ids` (unique `invoice_id`). Register before posting; duplicate insert fails. |
| Legacy posted invoices without stored supplier amount | **Backfill migration:** `backfill_supplier_amount_egp()` sets `supplier_amount_egp` from ledger (sum credits 2000 per invoice). |

---

## 1. Exact Schema Changes

### 1.1 Table: `purchase_invoices`

- **Add column:** `supplier_amount_egp` (number, optional for backward compat).
  - Meaning: Supplier liability (CR 2000) at post time in EGP. Set when invoice is posted; never derived at runtime from `total_egp - import_costs`.
- **Enforce in app (recommended in DB if your backend allows):**
  - `currency_code`: NOT NULL, default `'EGP'`.
  - All invoice creation/update paths set `currency_code` (default EGP when not provided).

### 1.2 Table: `posted_purchase_invoice_ids` (new)

- **Purpose:** DB-level duplicate protection for purchase invoice posting. Ledger has multiple rows per invoice (1200, 2110, 2000), so a unique constraint on `(reference_type, reference_id)` on the ledger would allow only one line per invoice; hence a separate registry table.
- **Columns:**
  - `invoice_id` (string) — **unique**, references `purchase_invoices.id`
  - `posted_at` (datetime)
  - `created_by` (string, optional)
- **Constraint:** Unique on `invoice_id`. Application inserts one row per posted invoice; second insert for same `invoice_id` fails.

---

## 2. Migration Code

### 2.1 Backfill `supplier_amount_egp` (already in `server_code/accounting.py`)

- **Callable:** `backfill_supplier_amount_egp(token_or_email=None)`
- **Logic:** For each `purchase_invoices` row with `status='posted'`:
  - `supplier_amount_egp` = sum of `credit` on `ledger` where `account_code='2000'`, `reference_type='purchase_invoice'`, `reference_id=invoice_id`.
  - Update row with `supplier_amount_egp`; if column missing, log and continue (no break for legacy).
- **When to run:** Once after adding column `supplier_amount_egp` to `purchase_invoices`. Safe to run multiple times (idempotent).

### 2.2 Pre-migration: Set `currency_code` on existing rows (optional)

- If you add NOT NULL on `currency_code`, first backfill NULLs:  
  `UPDATE purchase_invoices SET currency_code = 'EGP' WHERE currency_code IS NULL;`  
  (Or in Anvil: one-time script that updates rows where `currency_code` is missing to `'EGP'`.)

---

## 3. Modified Functions

| Function | Change |
|---------|--------|
| `post_purchase_invoice` | Require explicit `currency_code` (no default to EGP). Compute `supplier_amount_egp` once; store on row; use for CR 2000 only. Call `_register_posted_purchase_invoice` before posting; `_unregister_posted_purchase_invoice` on failure. Update row with `supplier_amount_egp` after success. |
| `create_contract_purchase` | Set `currency_code`, `exchange_rate_usd_to_egp`, `total_egp` on invoice row. Register in `posted_purchase_invoice_ids` before posting; unregister on JE failure. Set `supplier_amount_egp=subtotal_egp` when marking posted. |
| `create_purchase_invoice` | Set `currency_code` (default `'EGP'`) on row. Validate: if `original_amount` provided, require `currency_code`; if `currency_code != 'EGP'`, require `exchange_rate` > 0. |
| `update_purchase_invoice` | Validate: `original_amount` requires `currency_code`; non-EGP requires `exchange_rate` > 0. Allow updating `currency_code`. |
| `get_contract_payable_status` | `landed_cost` fallback when no ledger credits: use `inv.get('supplier_amount_egp') or total` + import_total (no runtime subtraction). |
| **New** `_register_posted_purchase_invoice(invoice_id, user_email)` | Inserts into `posted_purchase_invoice_ids`; returns False if already present or duplicate. |
| **New** `_unregister_posted_purchase_invoice(invoice_id)` | Deletes registry row (rollback when post fails). |
| **New** `backfill_supplier_amount_egp(token_or_email=None)` | Server callable migration to backfill `supplier_amount_egp` from ledger. |

---

## 4. Removed Runtime Logic

- **Removed:** Using `amount_to_ap_egp = total_egp - import_costs_total_egp` only at post time and then discarding it.  
  **Now:** Same formula used once at post time, result stored as `supplier_amount_egp` and used for the CR 2000 entry; no later code derives “supplier amount” from `total_egp - import_costs`.
- **Removed:** Defaulting `currency_code` to `'EGP'` when NULL at post time.  
  **Now:** Post rejects when `currency_code` is missing; create/update always set a value (default EGP when not provided).

---

## 5. Safety Audit (Step 4)

After modifications:

1. **Supplier balance from ledger only:**  
   `get_supplier_summary` and `get_contract_payable_status` use ledger (account 2000) for credits/debits. No use of `total_egp - import_costs` for balance.

2. **Import costs never affect 2000:**  
   Import costs are posted via `add_import_cost` (DR 1200, CR Bank/Cash). Only `post_purchase_invoice` credits 2000, using `supplier_amount_egp` (no import cost in that amount).

3. **All journal entries EGP:**  
   Post uses `total_egp`/stored EGP or `convert_to_egp`; non-EGP requires valid rate or stored `total_egp`; CR 2000 is `supplier_amount_egp` in EGP.

4. **Legacy data:**  
   Backfill sets `supplier_amount_egp` from existing ledger. If column is missing, update is skipped and no exception breaks the flow. Ledger duplicate check remains; registry table is additive.

5. **No runtime subtraction for supplier liability:**  
   Reporting/balance use `supplier_amount_egp` or ledger; no code path computes “supplier amount” as `total_egp - import_costs` after post.

---

## 6. Deployment Checklist

1. Add column `supplier_amount_egp` to `purchase_invoices` (number).
2. Add table `posted_purchase_invoice_ids` with `invoice_id` (unique), `posted_at`, `created_by`.
3. Deploy server code (accounting.py with all changes).
4. Run `backfill_supplier_amount_egp` once (admin or server call).
5. (Optional) Set `currency_code = 'EGP'` on any existing rows where it is NULL; then add NOT NULL default in DB if desired.

---

*Document generated as part of final production hardening. Ledger remains EGP-only; supplier liability is locked at post time; currency and duplicate posting are enforced.*

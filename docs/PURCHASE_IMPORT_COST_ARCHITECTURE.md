# Purchase & Import Cost Architecture (EGP-Only Ledger)

## 1. Architecture Summary

- **Ledger**: EGP only. All journal entries use EGP amounts.
- **Purchase invoice**: Represents **supplier liability only** (machine/value from supplier). Does NOT include import costs in total. Stores optional `currency_code`, `original_amount`, `exchange_rate`, `total_egp` for reference; posting uses EGP only.
- **Import costs**: Attached to **inventory items** (machines), not to supplier payable. Each import cost has a type (from `import_cost_types` table), description, original + EGP amount, payment account. Posting: DR 1200 Inventory, CR payment account (Bank/Cash) — EGP only.
- **Inventory**: `purchase_cost` (= purchase_cost_egp), `import_costs_total` (= import_costs_total_egp), `total_cost` (= total_cost_egp). Landed cost = purchase_cost_egp + SUM(import_costs.amount_egp).
- **Backward compatibility**: Existing `import_costs.purchase_invoice_id` and lookup by purchase_invoice_id remain supported; new flows use `inventory_id` when table has the column.

---

## 2. Table Changes

### 2.1 purchase_invoices (add optional columns)

| Column            | Type   | Description |
|-------------------|--------|-------------|
| currency_code     | string | e.g. USD, EGP (reference) |
| original_amount   | number | Amount in original currency (reference) |
| exchange_rate     | number | Rate to EGP (e.g. USD→EGP) |
| total_egp         | number | Supplier portion in EGP (for posting) |

Existing: `total`, `exchange_rate_usd_to_egp` kept. When `total_egp` is set it is used for posting; else `total` + `exchange_rate_usd_to_egp` used as today.

### 2.2 import_cost_types (new table)

| Column          | Type    | Description |
|-----------------|---------|-------------|
| id              | string  | UUID |
| name            | string  | TAX, FREIGHT, CUSTOMS, FEES, OTHER |
| default_account | string  | optional, for reporting |
| is_active       | boolean | default True |

Seed: TAX, FREIGHT, CUSTOMS, FEES, OTHER.

### 2.3 import_costs (add columns, keep legacy)

| Column           | Type   | Description |
|------------------|--------|-------------|
| inventory_id     | string | FK to inventory.id (required for new flow) |
| cost_type_id     | string | FK to import_cost_types.id (optional; else cost_type string) |
| description      | text   | required |
| original_currency| string | e.g. USD, EGP |
| original_amount  | number | as entered |
| exchange_rate    | number | to EGP |
| amount_egp       | number | converted; ledger uses this only |
| payment_account  | string | account code (e.g. 1000, 1010) |

Existing: `purchase_invoice_id`, `cost_type` (string), `amount`, `date`, etc. kept. When `inventory_id` and `amount_egp` exist they are used; else legacy `amount` and `purchase_invoice_id` used.

### 2.4 inventory (no schema change)

Already has `purchase_cost`, `import_costs_total`, `total_cost`. Treated as EGP. Alias in code/docs: purchase_cost_egp, import_costs_total_egp, total_cost_egp.

---

## 3. Migration Notes

- **Existing import_costs**: Keep `purchase_invoice_id` and `amount`. Code supports both: if `inventory_id` is present use it for recalc; else resolve inventory by `purchase_invoice_id` and sum by invoice. Optional migration script can set `inventory_id` from `purchase_invoice_id` (one inventory per invoice) and set `amount_egp` = `amount` for existing rows.
- **Existing purchase_invoices**: No change required. Posting continues to use `total` and `exchange_rate_usd_to_egp` when `total_egp` is not set.
- **import_cost_types**: If table does not exist, code uses built-in list DEFAULT_IMPORT_COST_TYPES. When table exists, seed_import_cost_types() fills it.

---

## 4. New Functions

- `get_import_cost_types()` — returns list from table or built-in.
- `seed_import_cost_types()` — seeds import_cost_types table if exists.
- `add_import_cost(..., inventory_id=..., cost_type_id=..., description=..., original_amount=..., currency_code=..., exchange_rate=..., payment_account=...)` — new signature; keeps legacy `purchase_invoice_id` + `cost_type` string for backward compat.

---

## 5. Modified Functions

- `create_purchase_invoice`: Optionally set currency_code, original_amount, exchange_rate, total_egp. Do NOT add import_costs to invoice total (total = fob + subtotal + tax only when new structure used; legacy preserved).
- `post_purchase_invoice`: Use total_egp when set; else current logic. Reject mixed currency; reject missing rate for non-EGP.
- `add_import_cost`: Accept inventory_id (preferred) or purchase_invoice_id. Accept cost_type_id or cost_type string. Store original_* and amount_egp when columns exist. Post EGP only. Recalc by inventory_id or purchase_invoice_id.
- `get_import_costs`: Accept inventory_id or purchase_invoice_id.
- `_update_inventory_import_totals`: Accept inventory_id or purchase_invoice_id; sum import costs by that key; update affected inventory row(s).

---

## 6. Data Integrity

- Ledger: only EGP amounts; convert_to_egp() used before any post; missing rate for non-EGP raises.
- Supplier liability: never includes import costs; posting uses total_egp (or total minus import_costs when legacy).
- Import costs: always DR 1200 CR payment_account; never CR 2000.
- Inventory landed cost: recalculated after add/edit/delete import cost; total_cost = purchase_cost + import_costs_total.
- Duplicate post: prevented for purchase_invoice. Negative amounts and unbalanced entries rejected in post_journal_entry.

---

## 7. Final Code Blocks (Summary)

- **get_import_cost_types**: Returns list from `app_tables.import_cost_types` if table exists and has rows; else returns `DEFAULT_IMPORT_COST_TYPES` (TAX, FREIGHT, CUSTOMS, FEES, OTHER).
- **seed_import_cost_types**: Idempotent seed of `import_cost_types` table; skips existing ids.
- **add_import_cost**: Signature supports both legacy `(purchase_invoice_id, cost_type, amount, description, ...)` and new keywords `inventory_id`, `cost_type_id`, `original_amount`, `payment_account`. Converts to EGP via `convert_to_egp`; posts DR 1200 CR payment_account; stores `amount` (legacy) and optionally `amount_egp`, `original_currency`, `original_amount`, `exchange_rate`, `inventory_id`, `cost_type_id`; calls `_update_inventory_import_totals(inventory_id=..., purchase_invoice_id=...)`.
- **get_import_costs**: Accepts `purchase_invoice_id` or `inventory_id`; returns costs with `amount_egp` when present.
- **_update_inventory_import_totals**: Accepts `inventory_id` or `purchase_invoice_id`; sums `amount_egp` or `amount`; updates inventory `import_costs_total` and `total_cost`.
- **create_purchase_invoice**: `total = fob_with_cyl + subtotal + tax_amount` (no import costs in total). Optional columns `currency_code`, `original_amount`, `exchange_rate`, `total_egp` set when provided.
- **post_purchase_invoice**: Uses `total_egp` when stored; else converts using `exchange_rate_usd_to_egp`. Rejects non-EGP invoice when exchange rate missing. Supplier liability = total_egp minus import_costs_total_egp (legacy) or total_egp when total already excludes import costs.

---

## 8. UI Requirements (Implemented)

- **Import Costs section**: Cost type (dropdown; legacy options + optional load from `get_import_cost_types`), Description, Currency, Original Amount, Exchange Rate, Payment method/account. EGP amount shown in details view (amount_egp or converted).
- **Summary panel** (invoice details): Purchase Cost (EGP), Total Import Costs (EGP), Landed Cost (EGP). Supplier payable shown separately (does not include import costs).
- **Client bridges**: `pyGetImportCostTypes`, `pyGetImportCosts(invoice_id, inventory_id=None)`.

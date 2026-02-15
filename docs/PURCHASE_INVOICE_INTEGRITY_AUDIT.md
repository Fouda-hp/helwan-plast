# Purchase Invoice & Import Cost Integrity Audit

## 1. Supplier liability (CR 2000) calculation

### 1.1 Is supplier liability ever calculated as total_egp minus import_costs?

**Yes, always.**  
**File:** `server_code/accounting.py`  
**Lines:** 952–965

```python
# Import costs: convert each to EGP when summing ...
import_costs_total_egp = 0.0
for ic in app_tables.import_costs.search(purchase_invoice_id=invoice_id):
    amt = _round2(ic.get('amount', 0))
    ...
    import_costs_total_egp += convert_to_egp(amt, curr, inv_rate if curr == 'USD' else None)
...
amount_to_ap_egp = _round2(total_egp - import_costs_total_egp)
```

- **Every** post uses `amount_to_ap_egp = total_egp - import_costs_total_egp`. There is no path that credits 2000 with a stored supplier-only amount without this subtraction.

### 1.2 Scenarios where this occurs

- **Legacy invoices:** `total` (and optionally `total_egp`) may include import costs in the stored total; at post we subtract linked import costs to get supplier-only → correct.
- **New invoices (create_purchase_invoice):** `total = fob_with_cyl + subtotal + tax_amount` (no import costs) — **lines 787–788**. So `total` is already supplier-only. At post we still compute `import_costs_total_egp` from DB and subtract. If there are no import cost rows, `import_costs_total_egp = 0`, so `amount_to_ap_egp = total_egp`. If import costs were added later via `add_import_cost`, we subtract them → correct.

So the same formula is used for both legacy and new; for new invoices with no import costs the subtraction is zero.

### 1.3 Recommendation: store supplier_amount_egp

- **Recommendation:** Persist **supplier_amount_egp** (or **amount_to_ap_egp**) on the purchase invoice at **post** time (and optionally at create when total is already supplier-only). Use this stored value for:
  - Posting (credit 2000) instead of recomputing from `total_egp - import_costs_total_egp`.
  - Any reporting that should show “supplier payable” for that invoice.
- **Benefit:** No dependence on runtime sum of `import_costs`; avoids drift if import costs are linked by `inventory_id` only or rows are added/removed after post.
- **Migration:** For already-posted invoices, one-time backfill: for each posted invoice, set `supplier_amount_egp` = sum(credit) on ledger for that invoice on account 2000, ref_type `purchase_invoice`. New posts then write this value when creating the journal entry.

---

## 2. New invoices: supplier-only amount and runtime subtraction

- **create_purchase_invoice** (lines 787–788): `total = fob_with_cyl + subtotal + tax_amount` (import costs **not** included). So new invoices **do** store a supplier-only total.
- **post_purchase_invoice** still does runtime subtraction of import costs (lines 952–965). So:
  - **New invoices with zero import costs:** subtraction is 0; effective supplier amount = total_egp. No logical error.
  - **New invoices with import costs added later:** subtraction is correct.
- **Conclusion:** New invoices do **not** require subtraction for correctness when there are no import costs; the current code still performs the subtraction (which is redundant in that case but correct). Storing `supplier_amount_egp` at post would remove this dependency and make intent explicit.

---

## 3. Purchase invoice currency handling

### 3.1 If currency_code != 'EGP'

**File:** `server_code/accounting.py` — **post_purchase_invoice** (lines 938–941, 928–950).

- **Is exchange_rate mandatory?**  
  **Yes, at post time.** If `currency_code != 'EGP'` and there is no usable rate, posting is rejected:
  - Line 939: `currency_code = _safe_str(row.get('currency_code') or 'EGP').upper()`
  - Lines 940–941: `if currency_code != 'EGP' and not inv_rate: return {'success': False, 'message': '...'}`  
  So for non-EGP we require `exchange_rate_usd_to_egp` or `exchange_rate` (or we reject).

- **Is total_egp mandatory?**  
  **No.** If we have a valid exchange rate we can convert `total` to EGP at post (lines 945–946). `total_egp` is optional and used when present (lines 942–944).

- **Is total_egp always computed and stored before posting?**  
  **No.** It is only set in **create_purchase_invoice** when the caller sends `total_egp` or when we have `exchange_rate` and set `total_egp = total * exchange_rate` (lines 845–858). So many invoices can have `total_egp` = NULL and we compute at post from `total` + rate.

### 3.2 Can an invoice exist with currency_code=USD, exchange_rate=NULL, total_egp=NULL?

**Yes.** Columns can be missing or NULL. Then at **post**:

- Line 939: `currency_code` defaults to `'EGP'` if NULL/missing → **risk:** a USD invoice with no `currency_code` is treated as EGP.
- Line 934: `inv_rate` is 0 if both `exchange_rate_usd_to_egp` and `exchange_rate` are NULL/missing.
- Lines 940–941: We only reject when `currency_code != 'EGP'` **and** `not inv_rate`. So if `currency_code` is not set we never reject and fall through to line 948–949: `total_egp = total`, `tax_egp = tax_amount` → **USD amounts are posted as EGP (mixed currency in ledger).**

**Risk:** USD invoice with no `currency_code` and no rate → posted as EGP.

**Safeguard (see below):** On post, require either (a) `currency_code == 'EGP'`, or (b) valid `exchange_rate`/`exchange_rate_usd_to_egp`; and when rate is missing, reject even if `currency_code` is missing (treat missing as non-EGP when total looks foreign), or require `total_egp` to be set for non-EGP.

---

## 4. Import costs data integrity

### 4.1 Is amount_egp always stored for new entries?

**File:** `server_code/accounting.py` — **add_import_cost** (lines 1486–1531).

- We always compute `amount_egp` and put it in `row_data` (lines 1514–1516). We also set `row_data['amount'] = amount_egp` (line 1492).
- We then try `app_tables.import_costs.add_row(**row_data)`. If that fails (e.g. no column `amount_egp`), we pop optional columns including `amount_egp` and retry (lines 1522–1529). So **when the table has no `amount_egp` column, new rows are stored with only `amount`** (which holds the EGP value). So semantically the value is EGP; the column name is just `amount`.

**Answer:** `amount_egp` is stored when the column exists; otherwise we store the same value in `amount`. New rows do **not** store a non-EGP value in `amount` — we always convert and put EGP in `amount` (and optionally in `amount_egp`).

### 4.2 Can a row exist with only 'amount' and no 'amount_egp'?

**Yes**, when the `import_costs` table has no `amount_egp` column. Then after the retry we only have `amount` (and that value is EGP). So “only amount, no amount_egp” is possible; the value is still EGP.

### 4.3 Recalculation fallback and new rows

**_update_inventory_import_totals** (lines 1588, 1600):  
`import_total = _round2(sum(_round2(r.get('amount_egp') or r.get('amount', 0)) for r in cost_rows))`.

- Fallback is `r.get('amount', 0)` when `amount_egp` is missing. Used for both legacy rows (only `amount`) and new rows when `amount_egp` column doesn’t exist (we still set `amount` = EGP). So new rows don’t “skip” conversion: we convert before save and store EGP in `amount` (and in `amount_egp` when the column exists).

**post_purchase_invoice** (lines 954–960):  
When summing import costs for supplier liability it uses **only** `ic.get('amount', 0)` and `convert_to_egp(amt, curr, ...)`. It does **not** use `ic.get('amount_egp')`. So:

- If a row has `amount_egp` and `amount` in EGP, we still treat `amount` by currency and convert again (for EGP that’s no change).
- If a row had `amount` in USD and `amount_egp` in EGP, we would incorrectly use `amount` and convert again. So **risk:** double conversion or wrong currency if `amount` and `amount_egp` get out of sync. **Recommendation:** In post_purchase_invoice, when summing import costs, use `ic.get('amount_egp')` when present, and only fall back to `convert_to_egp(ic.get('amount'), curr, ...)` when `amount_egp` is missing (legacy).

### 4.4 Validation to enforce

- **add_import_cost:** For `currency_code != 'EGP'`, require `exchange_rate` or a successful rate lookup; `convert_to_egp` already raises if rate is missing. So we already enforce “non-EGP ⇒ rate” at conversion time. We could add an explicit check before conversion and return a clear error.
- **amount_egp must always be saved:** In code we always set `amount_egp` in `row_data` when the column exists; when it doesn’t we store EGP in `amount`. To “enforce” that amount_egp is saved: (1) ensure DB has `amount_egp` column, and (2) in add_import_cost, after add_row, if the table supports it, require that either `amount_egp` or (for legacy tables) `amount` is present and non-negative. No change needed for logic — only for schema and optional checks.

---

## 5. Supplier balance calculation

### 5.1 When displaying vendor balance: ledger vs invoice table?

- **get_supplier_summary** (lines 3992–4089): Uses **ledger only**. For each supplier it gets invoice IDs from `purchase_invoices`, then sums CR on 2000 (ref_type `purchase_invoice`) and DR on 2000 (ref_type `payment`). So supplier balance is **derived from ledger (account 2000)**.
- **get_contract_payable_status** (lines 1178–1234): Uses **invoice table**: `total = inv.get('total')`, `paid = inv.get('paid_amount')`, `remaining = total - paid`. So contract-level “payable” is **from the invoice table**, not from the ledger.

### 5.2 Inconsistency risks if invoice table is used

- **get_contract_payable_status:** If `total` on the invoice is wrong (e.g. includes import costs after **update_purchase_invoice**), then `remaining` and displayed “landed_cost” (total + import_total) are wrong. So:
  - **Risk 1:** `update_purchase_invoice` (lines 2818–2822) sets `updates['total'] = fob_with_cyl + subtotal + import_costs_total + tax_amount`, i.e. **total includes import costs**. That contradicts create_purchase_invoice (supplier-only total) and makes “remaining” and “landed_cost” inconsistent with ledger and with design.
  - **Risk 2:** Payment history is taken from ledger (1204–1210), but “total” and “remaining” are from the invoice table → mix of ledger and table can be inconsistent.

**Correction:** For contract/vendor balance and remaining amount, compute from ledger (account 2000) per invoice:  
`posted_supplier_amount` = sum(credit) for ref_type=`purchase_invoice`, ref_id=inv_id, account 2000;  
`paid` = sum(debit) for ref_type=`payment`, ref_id=inv_id, account 2000;  
`remaining` = posted_supplier_amount - paid.  
Optionally keep invoice-table total for display but label it clearly (e.g. “Invoice total (supplier only)” only when total is kept supplier-only).

### 5.3 Partial payments and journal

- **record_supplier_payment** (lines 1262–1311): Updates ledger (DR 2000, CR bank/cash) and then updates **invoice row** `paid_amount` and `status` (1304–1308). So partial payments **do** update the vendor balance via **journal entries**; the invoice’s `paid_amount` is a cache. Supplier balance in **get_supplier_summary** is correct because it uses the ledger. The only place that can be wrong is **get_contract_payable_status** when it uses invoice total/paid instead of ledger.

---

## 6. Duplicate protection (post_purchase_invoice)

### 6.1 Can post_purchase_invoice be executed twice for the same invoice_id?

**No, not successfully.**  
**File:** `server_code/accounting.py` lines 917–921:

```python
existing = list(app_tables.ledger.search(reference_type='purchase_invoice', reference_id=invoice_id))
if existing:
    return {'success': False, 'message': 'This invoice has already been posted. Duplicate posting is not allowed.'}
```

So the second call returns an error and does not create new entries.

### 6.2 Is there a unique ledger reference constraint in the DB?

Not from the codebase; Anvil table schema is not defined here. So there is **no** DB-level unique constraint on (reference_type, reference_id) for the ledger — duplicate prevention is **application-only**.

### 6.3 Hard safeguard

- **Current:** Application check is sufficient to prevent duplicate posts in normal use.
- **Hardening:** Add a **unique constraint** on the ledger table on `(reference_type, reference_id)` when `reference_type = 'purchase_invoice'` (or a composite unique index), so the DB rejects a second insert for the same invoice. If the schema is managed outside code, document this as required. Alternatively, add a **posted_at** or **ledger_transaction_id** on `purchase_invoices` and treat “already posted” as immutable (and optionally use it in the duplicate check).

---

## 7. Full integrity audit — scenarios and references

### 7.1 Mixed currency in ledger

| Scenario | File:Line | Finding |
|----------|----------|--------|
| USD invoice, no currency_code, no rate | accounting.py:938–949 | `currency_code` defaults to EGP; `total_egp = total` → USD posted as EGP. **Risk.** |
| Non-EGP invoice, rate missing | accounting.py:940–941 | Post rejected. **Safe.** |
| Import cost in USD, rate missing | accounting.py:1432–1434, 202–220 | `convert_to_egp` raises; add_import_cost returns error. **Safe.** |

### 7.2 Supplier liability inaccuracy

| Scenario | File:Line | Finding |
|----------|----------|--------|
| total includes import costs (legacy or after update) | 2818–2822, 965 | Post still uses total_egp - import_costs_total_egp → correct supplier amount. **Safe.** |
| Import costs linked only by inventory_id | 954 | We sum by `purchase_invoice_id`. If an import cost has no purchase_invoice_id (only inventory_id), it is **not** included in the subtraction → **supplier liability too high.** **Risk** if new flow uses only inventory_id. |
| Stale total on invoice | 1198–1200 (get_contract_payable_status) | Remaining = total - paid from invoice table; can disagree with ledger. **Risk for display.** |

### 7.3 Landed cost inconsistency

| Scenario | File:Line | Finding |
|----------|----------|--------|
| _update_inventory_import_totals by purchase_invoice_id | 1598–1607 | Sums import_costs by purchase_invoice_id; updates all inventory for that invoice. **Consistent.** |
| _update_inventory_import_totals by inventory_id | 1581–1596 | Sums by inventory_id (or fallback to purchase_invoice_id); updates that item. **Consistent.** |
| New import cost row without amount_egp column | 1522–1529 | We store EGP in `amount`; recalculation uses amount_egp or amount. **Consistent.** |
| get_contract_payable_status landed_cost | 1236 | `landed_cost = total + import_total`. If total includes import (after update), double count. **Risk.** |

### 7.4 Legacy fallback corrupting new data

| Scenario | File:Line | Finding |
|----------|----------|--------|
| post_purchase_invoice import sum | 954–960 | Uses only `amount` + convert_to_egp; does not use `amount_egp`. New rows with amount_egp set could be double-converted if `amount` were ever left in USD. Currently we set amount=amount_egp so **no corruption**; but logic should prefer amount_egp when present. |
| update_purchase_invoice total | 2818–2822 | Puts import costs back into total → **new data (supplier-only total) overwritten with legacy-style total.** **Risk.** |

---

## 8. Summary of required corrections

1. **post_purchase_invoice:** When summing import costs, use `ic.get('amount_egp')` when present; only use `convert_to_egp(ic.get('amount'), curr, ...)` for legacy rows (no amount_egp).
2. **post_purchase_invoice (currency):** When `currency_code` is missing/NULL, treat as ambiguous: require either a valid exchange rate or an explicit `total_egp` before posting (or reject with a clear message).
3. **update_purchase_invoice:** Do **not** include import costs in `total`. Set `total = fob_with_cyl + subtotal + tax_amount` (same as create_purchase_invoice) so invoice total stays supplier-only.
4. **get_contract_payable_status:** Compute `remaining` (and optionally “total” for display) from ledger (account 2000) per invoice instead of from invoice total/paid_amount; or keep both and label “from ledger” vs “from invoice”.
5. **Optional:** Store `supplier_amount_egp` on the invoice at post time and use it for the CR 2000 amount and for any “supplier payable” display.
6. **Optional:** Enforce at create/update that when `currency_code != 'EGP'`, either `exchange_rate` or `total_egp` is set; and document/add DB unique constraint for (reference_type, reference_id) for ledger to harden duplicate protection.

---

## 9. Safeguards implemented (code changes)

1. **post_purchase_invoice (accounting.py)**  
   - Import cost sum: use `amount_egp` when present; only use `convert_to_egp(amount, curr, ...)` for legacy rows.  
   - Currency: require exchange rate or stored total_egp when `currency_code != 'EGP'`.

2. **update_purchase_invoice (accounting.py)**  
   - `total` set to `fob_with_cyl + subtotal + tax_amount` only (import costs no longer included).

3. **get_contract_payable_status (accounting.py)**  
   - `posted_supplier` and `paid_from_ledger` computed from ledger (account 2000, by reference_id and reference_type).  
   - `remaining` = posted_supplier - paid_from_ledger; `paid` = paid_from_ledger.  
   - `landed_cost` = posted_supplier + import_total (or total + import_total when not yet posted).  
   - Import cost amount uses `amount_egp` when present.

4. **add_import_cost (accounting.py)**  
   - Explicit check: when `currency_code != 'EGP'`, require a valid exchange rate (from parameter or table) and return a clear error otherwise.

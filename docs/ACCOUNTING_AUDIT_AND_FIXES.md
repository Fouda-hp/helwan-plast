# Accounting Audit and EGP-Only Ledger Fixes

## 1. Structured Audit Report

### post_purchase_invoice
| Check | Result |
|-------|--------|
| Non-EGP posting risk | **ISSUE**: Invoice total/tax/import sums could be stored in USD; posted as-is → mixed currency in ledger. |
| Mixed-currency totals | **ISSUE**: total from row + import_costs from table could mix USD/EGP. |
| Journal balancing | OK (debit = credit). |
| Account existence | 1200, 2000 validated implicitly via post_journal_entry; 2100 used for tax (wrong account). |
| Duplicate posting | **ISSUE**: No check; same invoice could be posted twice. |

### add_import_cost
| Check | Result |
|-------|--------|
| Non-EGP posting risk | **ISSUE**: amount posted as-is; no currency conversion. |
| Mixed-currency | N/A (single amount). |
| Journal balancing | OK. |
| Account existence | 1200 and payment account validated. |
| Duplicate posting | N/A (multiple costs per invoice allowed). |

### record_supplier_payment
| Check | Result |
|-------|--------|
| Non-EGP posting | OK — converts to EGP via rate. |
| Balancing | OK. |
| Account existence | Via post_journal_entry. |

### record_customer_collection
| Check | Result |
|-------|--------|
| Non-EGP posting | OK — converts to EGP. |
| Balancing | OK. |

### create_contract_purchase
| Check | Result |
|-------|--------|
| Non-EGP posting | OK — converts USD to EGP at entry; posts EGP only. |
| Balancing | OK. |

### sell_inventory
| Check | Result |
|-------|--------|
| Non-EGP posting | Assumed EGP (total_cost, selling_price). |
| Balancing | OK. |
| Account existence | Not explicitly validated before post. |

### add_expense
| Check | Result |
|-------|--------|
| Non-EGP posting | **ISSUE**: No currency; amount posted as-is (assumed EGP). |
| Balancing | OK. |
| Account existence | Not explicitly validated. |

---

## 2. List of Detected Issues

1. **post_purchase_invoice**: Invoice totals (and import cost sums) could be in USD; no conversion to EGP before posting → mixed currency in ledger.
2. **post_purchase_invoice**: No duplicate-post check → same invoice could be posted more than once.
3. **post_purchase_invoice**: VAT on purchases used account 2100 (Tax Payable). Required: VAT input → 2110 (asset), VAT output → 2100 (liability).
4. **add_import_cost**: Amount posted and stored without currency conversion → non-EGP risk.
5. **add_expense**: No currency parameter; no conversion to EGP when expense is in another currency.
6. **Account 5100**: Used only in migration (reclassification); no clear deprecation note; import costs correctly post to 1200.
7. **Missing account validation**: add_expense and sell_inventory did not explicitly validate account existence before building entries.
8. **Inventory cost integrity**: total_cost = purchase_cost + import_costs_total must be enforced in EGP; _update_inventory_import_totals recalculates but did not document EGP expectation.

---

## 3. Exact Code Modifications

### 3.1 New helper: `convert_to_egp(amount, currency_code, exchange_rate=None)`
- **File**: `server_code/accounting.py`
- **Location**: After `_get_rate_to_egp`.
- **Behavior**: EGP → return amount; else use provided exchange_rate or fetch from `currency_exchange_rates`; if rate missing for non-EGP → raise `ValueError`.

### 3.2 Chart of Accounts
- **DEFAULT_ACCOUNTS**: 2100 renamed to "VAT Payable" (ضريبة مخرجات مستحقة); added 2110 "VAT Input Recoverable" (ضريبة مدخلات قابلة للاسترداد), type asset. Comment added for 5100: deprecated for new posting; import costs post to 1200 only.

### 3.3 New helper: `_ensure_vat_accounts()`
- Creates 2100 and 2110 if missing (idempotent). Called from `post_purchase_invoice` before posting.

### 3.4 post_purchase_invoice
- Duplicate-post check: search ledger for `reference_type='purchase_invoice'`, `reference_id=invoice_id`; if any, return error.
- EGP conversion: if `row.exchange_rate_usd_to_egp` > 0, treat total and tax_amount as USD and convert to EGP; else use as EGP.
- Import costs: sum import_costs with per-row currency; each amount converted to EGP via `convert_to_egp(amount, ic.currency or 'EGP', ...)`.
- VAT: tax line posts to **2110** (VAT Input Recoverable) instead of 2100.
- Account validation: _validate_account_exists for 2110, 1200, 2000 before building entries.
- All journal amounts use EGP values only.

### 3.5 add_import_cost
- New parameters: `currency_code='EGP'`, `exchange_rate=None`.
- Convert amount to EGP with `convert_to_egp(amount_in, currency_code, exchange_rate)`; use `amount_egp` for journal and for stored `amount` (ledger and DB store EGP).
- Validate payment account and 1200 exist before posting.
- Optional: store `currency='EGP'` on import_costs row if column exists (try/except).

### 3.6 add_expense
- Optional `data.currency` and `data.exchange_rate`: if currency not EGP, convert amount to EGP before posting and before saving; stored amount = EGP.
- Validate expense account and payment account exist before posting.

### 3.7 sell_inventory
- Validate accounts 5000, 1200, 1100, 4000 exist before posting.

### 3.8 _update_inventory_import_totals
- Docstring updated: total_cost = purchase_cost + import_costs_total; all amounts in EGP; import cost amounts stored in EGP by add_import_cost.

### 3.9 Audit block comment
- Added at top of ledger section: short audit summary (EGP-only, duplicate prevention, VAT 2110, 5100 deprecated).

---

## 4. Final Corrected Functions (Summary)

| Function | Change summary |
|----------|----------------|
| **convert_to_egp** | New. Converts to EGP; raises if rate missing for non-EGP. |
| **_ensure_vat_accounts** | New. Ensures 2100, 2110 exist. |
| **post_purchase_invoice** | Duplicate check; EGP conversion for total/tax and import_costs; VAT → 2110; account validation. |
| **add_import_cost** | currency_code, exchange_rate; convert to EGP; store EGP; validate accounts. |
| **add_expense** | Optional currency/exchange_rate; convert to EGP; validate accounts; store amount_egp. |
| **sell_inventory** | Validate 5000, 1200, 1100, 4000 before post. |
| **_update_inventory_import_totals** | Docstring: EGP guarantee. |
| **post_journal_entry** | No change (already rejects negative, unbalanced, invalid accounts). |

---

## 5. Architectural Improvements

- **EGP-only ledger**: All journal entries are created in EGP. `convert_to_egp` is used in post_purchase_invoice, add_import_cost, add_expense; record_supplier_payment and record_customer_collection already converted; create_contract_purchase already posts EGP.
- **No mixed-currency posting**: Invoice posting converts totals and import cost sums to EGP; import costs and expenses convert before post and save.
- **VAT separation**: Purchase VAT → 2110 (VAT Input Recoverable, asset); 2100 reserved for output VAT (liability). Both accounts ensured by _ensure_vat_accounts.
- **5100**: Explicitly deprecated for new posting; only migration uses it (reclass DR 1200 CR 5100). New import costs post only to 1200.
- **Data safety**: Duplicate purchase-invoice post rejected; negative amounts and unbalanced entries rejected in post_journal_entry; account existence validated in post_purchase_invoice, add_import_cost, add_expense, sell_inventory.
- **Inventory cost integrity**: total_cost = purchase_cost + import_costs_total; amounts stored in EGP; _update_inventory_import_totals recalculates safely after import cost changes.
- **Backward compatibility**: No DB schema changes required; optional currency on expenses and import_costs; existing data (EGP or legacy USD) handled via conversion at post time; 2110 auto-created if missing.

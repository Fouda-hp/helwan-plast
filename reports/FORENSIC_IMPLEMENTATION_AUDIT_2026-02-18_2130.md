# Forensic Implementation Audit — Helwan Plast ERP

**Date**: 2026-02-18 21:30 UTC
**Scope**: Full-depth forensic analysis of all server, client, and JS code
**Method**: Line-by-line trace of every financial function, auth callable, data path, and bridge

---

## Executive Summary

The Helwan Plast ERP is a sophisticated Anvil-based system with 270+ server callables, double-entry accounting, multi-currency support, and custom authentication. The codebase demonstrates strong architectural thinking (transit inventory model, atomic numbering, period locking). However, **8 critical issues** exist primarily around exchange rate fallback logic (silent 1.0 rate), authentication bypass paths, and contract serial atomicity. These must be addressed before the system handles significant financial volume.

---

## Severity Breakdown

| Severity | Count |
|----------|-------|
| CRITICAL | 8 |
| HIGH | 7 |
| MEDIUM | 20 |
| LOW | 2 |
| **TOTAL** | **37** |

---

## CRITICAL Issues

### C-01: Exchange Rate Fallback Returns 1.0 for Missing Rates
- **File**: `server_code/accounting.py`
- **Function**: `_get_rate_to_egp()`
- **Lines**: 251-261
- **Problem**: Function returns `1.0` when no exchange rate is found in `currency_exchange_rates` table. This means any USD, EUR, or CNY amount with a missing rate is silently posted to the EGP ledger at 1:1.
- **Consequence**: A $50,000 USD invoice would post as 50,000 EGP instead of ~2,500,000 EGP (at ~50 rate). Accounts Payable understated by 98%. Balance sheet and P&L corrupted.
- **Fix**: Replace `return 1.0` with `raise ValueError(f"No exchange rate found for {currency_code}")`. Add logging when fallback is triggered. Audit all existing ledger entries where rate=1.0 was used.

### C-02: Legacy Import Cost FX Fallback in post_purchase_invoice
- **File**: `server_code/accounting.py`
- **Function**: `post_purchase_invoice()`
- **Lines**: 1547-1558
- **Problem**: When summing legacy import costs, if an import cost is in USD but `inv_rate` is 0, `convert_to_egp()` falls through to `_get_rate_to_egp()` which returns 1.0. The `if curr == 'USD' else None` logic passes None for non-USD, which also triggers fallback.
- **Consequence**: Import costs calculated incorrectly, `supplier_amount_egp` derivation wrong, AP balance incorrect.
- **Fix**: Require explicit exchange rate for all non-EGP import costs. Reject posting if rate is 0 or missing.

### C-03: Legacy pay_import_cost USD Fallback
- **File**: `server_code/accounting.py`
- **Function**: `pay_import_cost()`
- **Lines**: 2599-2606
- **Problem**: If legacy import cost has no `amount_egp` column, fallback uses `inv.exchange_rate_usd_to_egp`. If invoice rate is 0, falls back to `_get_rate_to_egp('USD')` which returns 1.0.
- **Consequence**: USD import costs posted at 1:1 to EGP ledger.
- **Fix**: Reject payment if exchange rate cannot be determined. Never silently default to 1.0.

### C-04: FX Calculation Bypass with Percentage Payment + Zero Invoice Rate
- **File**: `server_code/accounting.py`
- **Function**: `record_supplier_payment()`
- **Lines**: 2145-2172
- **Problem**: When paying by percentage (pct parameter), the `invoice_rate > 0` check (line 2150) is SKIPPED. The percentage path (line 2162) calculates `liability_slice_egp = remaining_egp * pct` using book value, ignoring actual FX conversion.
- **Consequence**: If invoice has zero rate but payment is percentage-based, FX gain/loss calculation is incorrect. Supplier may be over/underpaid.
- **Fix**: Add `if invoice_rate <= 0 and currency_code != 'EGP': raise ValueError(...)` before the percentage branch.

### C-05: Negative Opening Balances Accepted Without Validation
- **File**: `server_code/accounting.py`
- **Function**: `post_opening_balances()`
- **Lines**: 7191-7213
- **Problem**: `amount = _round2(float(r.get('opening_balance', 0) or 0))` accepts negative values. Lines 7200-7213 process negative amounts by flipping debit/credit, but the semantic meaning changes (a negative customer balance means they overpaid, but the code posts it as a liability).
- **Consequence**: Wrong account classification. Negative customer balance posted as liability instead of credit balance on AR.
- **Fix**: Validate `amount >= 0` and reject negatives with clear error message. If credit balances are needed, add explicit direction field.

### C-06: disable_totp Takes User Email as Client Parameter
- **File**: `server_code/AuthManager.py`
- **Function**: `disable_totp()`
- **Lines**: 408-421
- **Problem**: Function accepts `user_email` as a client-supplied parameter. An authenticated non-admin user's token is validated, then the function checks if the session email matches the target email. This is correct for self-service. BUT: the admin check (line 414) allows ANY admin to disable ANY user's TOTP by passing a different email.
- **Consequence**: Admin compromise allows disabling MFA for all users, enabling account takeover cascade.
- **Fix**: For non-admin path, extract email from the validated session (not from parameter). For admin path, add audit logging and require confirmation.

### C-07: Emergency Admin Function — Single Secret Key Escalation
- **File**: `server_code/AuthManager.py`
- **Function**: `reset_admin_password_emergency()`
- **Lines**: 1829-1924
- **Problem**: Function creates new admin accounts (line 1874) or upgrades existing users to admin (line 1905) using only a secret key from Anvil Secrets. If key is compromised, unlimited admin accounts can be created.
- **Consequence**: Complete system compromise with a single secret. No rate limiting on emergency function. No approval workflow.
- **Fix**: Add time-limited tokens (expire after 1 use), IP restriction, require manual DB confirmation step, and alert existing admins on any emergency reset.

### C-08: Contract Serial Numbering Uses Non-Atomic Function
- **File**: `server_code/QuotationManager.py`
- **Function**: `save_contract()` → `_get_next_contract_serial_from_table()`
- **Lines**: 2323, 2669-2687
- **Problem**: `_get_next_contract_serial_from_table()` does a full table scan to find max serial, then returns max+1. This is NOT wrapped in `@anvil.tables.in_transaction`. Two concurrent saves can get the same serial number.
- **Consequence**: Duplicate contract numbers (e.g., two "C - 150 / 6 - 2026"). Breaks uniqueness, confuses accounting, invoice linking fails.
- **Fix**: Use `_get_next_contract_serial_atomic()` from `quotation_numbers.py` (line 191) which IS properly wrapped in `@in_transaction`.

---

## HIGH Issues

### H-01: NULL supplier_amount_egp Drift
- **File**: `server_code/accounting.py`
- **Function**: `post_purchase_invoice()`
- **Lines**: 1547-1564
- **Problem**: `supplier_amount_egp = total_egp - import_costs_total_egp`. If import cost entries have NULL amounts (silently skipped at line 1549-1551), the sum is incomplete. After posting, adding more import costs changes effective cost but `supplier_amount_egp` in invoice row stays stale.
- **Consequence**: Invoice table shows different AP than ledger account 2000. Aging reports inconsistent.
- **Fix**: Recalculate `supplier_amount_egp` on every import cost add/pay. Add reconciliation check.

### H-02: VAT Account 2110 vs 1210 Swap Risk
- **File**: `server_code/accounting.py`
- **Function**: `pay_import_cost()`
- **Lines**: 2621-2636
- **Problem**: Only costs with `cost_type == 'vat'` (exact string match) are posted to account 2110. If user enters VAT as a regular import cost (e.g., cost_type='customs_vat' or 'shipping_and_vat'), it goes to 1210 instead of 2110.
- **Consequence**: VAT Input Recoverable (2110) understated. Inventory in Transit (1210) overstated. VAT returns filed incorrectly.
- **Fix**: Add fuzzy matching or whitelist for VAT-related cost types. Validate cost_type against allowed values.

### H-03: Duplicate Import Cost Posting via Reference Types
- **File**: `server_code/accounting.py`
- **Function**: `post_purchase_invoice()`
- **Lines**: 1510-1512
- **Problem**: Duplicate check filters by `reference_type='purchase_invoice'`. Import costs use `reference_type='import_cost_payment'`. Same cost could appear in ledger under both reference types.
- **Consequence**: Double-counting of costs. Inventory inflated.
- **Fix**: Cross-check all reference types for the same invoice_id before posting.

### H-04: Revenue Double-Counting Guard Fragile
- **File**: `server_code/accounting.py`
- **Function**: `post_contract_receivable()`
- **Lines**: 6365-6383
- **Problem**: Guard checks inventory table `status='sold'`. If inventory item is soft-deleted, guard is bypassed — revenue can be posted again.
- **Consequence**: Revenue recorded twice for same contract. P&L overstated.
- **Fix**: Check ledger entries (account 4000 + contract reference) instead of inventory table status.

### H-05: Silent Unique Constraint Errors in Posted Invoice Registry
- **File**: `server_code/accounting.py`
- **Function**: `_register_posted_purchase_invoice()`
- **Lines**: 1236-1240
- **Problem**: Non-unique-constraint exceptions (e.g., timeout, permission) cause `return True` (success), falsely allowing duplicate posting.
- **Consequence**: Same purchase invoice posted twice to ledger. AP doubled.
- **Fix**: Only return True on actual success. Return False on any exception, then investigate.

### H-06: Export Functions Expose Full PII
- **File**: `server_code/QuotationManager.py`
- **Function**: `export_clients_data()`, `export_quotations_data()`, `export_contracts_data()`
- **Lines**: 1031-1110, 2889-2926
- **Problem**: Any user with 'export' permission can download ALL client phones, emails, addresses with no per-user filtering or data minimization.
- **Consequence**: PII exposure risk. GDPR/data protection non-compliance.
- **Fix**: Add role-based data filtering. Redact sensitive fields for non-admin exports. Add export audit logging.

### H-07: Admin Token/Email Parameter Confusion
- **File**: `server_code/AuthManager.py`
- **Function**: Multiple functions (`approve_user`, `reject_user`, etc.)
- **Lines**: 1087-1112
- **Problem**: Parameter `token_or_email` accepts both formats. `require_admin()` only validates tokens. If email is passed, auth check fails silently but `admin_email` is derived from the parameter string (line 1112: `if '@' in str(token_or_email)`).
- **Consequence**: Inconsistent auth behavior. Audit trails may show raw tokens instead of emails.
- **Fix**: Standardize all callable parameters to accept only tokens. Extract email from validated session.

---

## MEDIUM Issues

### M-01: Weak Period Lock in post_purchase_invoice
- **File**: `accounting.py` | **Function**: `post_purchase_invoice()` | **Lines**: 1580
- **Problem**: Uses invoice date OR today as fallback. No explicit period lock check before posting.
- **Fix**: Add `if is_period_locked(inv_date): return error` before any ledger writes.

### M-02: Partial Payment Rounding Edge Case
- **File**: `accounting.py` | **Function**: `pay_import_cost()` | **Lines**: 2610-2614
- **Problem**: If remaining = 0.001 (rounding artifact), user cannot pay. No tolerance check.
- **Fix**: Add tolerance: `if remaining < 0.01: treat as paid`.

### M-03: FX Audit Trail Missing
- **File**: `accounting.py` | **Function**: `create_contract_purchase()` | **Lines**: 1814-1871
- **Problem**: Exchange rate stored at posting but no audit trail of rate used vs. payment rate.
- **Fix**: Log exchange rate source and timestamp in ledger entry metadata.

### M-04: Inventory Pre-Move Sale Possible
- **File**: `accounting.py` | **Function**: `sell_inventory()` | **Lines**: 3501-3507
- **Problem**: If 1210 balance = 0 (transit cleared), sale allowed even if `inventory_moved=False`.
- **Fix**: Require explicit `inventory_moved=True` before sale, regardless of balance.

### M-05: 1210 Balance Includes Partial Import Costs
- **File**: `accounting.py` | **Function**: `move_purchase_to_inventory()` | **Lines**: 1664
- **Problem**: Sums all 1210 activity including partial import cost payments. May move less than total cost.
- **Fix**: Validate that all import costs are fully paid before moving.

### M-06: Journal Balance Tolerance is Absolute (0.005)
- **File**: `accounting.py` | **Function**: `post_journal_entry()` | **Lines**: 711
- **Problem**: Fixed tolerance regardless of transaction size. 0.006 EGP imbalance on 10M transaction rejected.
- **Fix**: Use percentage-based tolerance (e.g., 0.001% of max(debits, credits)).

### M-07: No Reference Type Validation
- **File**: `accounting.py` | **Function**: `post_journal_entry()` | **Lines**: 739-750
- **Problem**: Any string accepted as reference_type. Typos break duplicate detection queries.
- **Fix**: Validate against whitelist of allowed reference types.

### M-08: _round2 Returns Silent Zero on NULL/Error
- **File**: `accounting.py` | **Function**: `_round2()` | **Lines**: 110-115
- **Problem**: Returns 0.0 for NULL/text inputs. Cumulative zeros can mask missing data.
- **Fix**: Log warning when fallback to 0.0 is used. Consider raising for critical calculations.

### M-09: Month Parsing Fragility in Period Lock
- **File**: `accounting.py` | **Function**: `is_period_locked()` | **Lines**: 427
- **Problem**: `int(str(d)[5:7])` assumes ISO format. Non-standard dates crash ungracefully.
- **Fix**: Use `d.month` attribute only, remove string parsing fallback.

### M-10: VAT Account Creation Silent Failure
- **File**: `accounting.py` | **Function**: `_ensure_vat_accounts()` | **Lines**: 658-666
- **Problem**: If VAT account creation fails, only logs warning. Later postings crash with confusing error.
- **Fix**: Raise error immediately if required accounts cannot be created.

### M-11: Retry Logic Masks Constraint Errors
- **File**: `accounting.py` | **Function**: `move_purchase_to_inventory()` | **Lines**: 1737-1758
- **Problem**: Retry on column error may succeed despite different root cause (e.g., duplicate key).
- **Fix**: Check error type precisely before retrying.

### M-12: N+1 Customer AR Query Pattern
- **File**: `accounting.py` | **Function**: `_get_customer_ar_balance()` | **Lines**: 6234-6263
- **Problem**: 3 full-table scans per contract (inventory + 2x ledger). 1000 contracts = 300k scans.
- **Fix**: Single ledger query with aggregation. Pre-compute AR balances.

### M-13: Full Ledger Scan in Balance Calculation
- **File**: `accounting.py` | **Function**: `_get_all_balances()` | **Lines**: 3607-3700
- **Problem**: Loads ALL ledger entries up to cutoff date, filters in Python.
- **Fix**: Add account_code filtering at DB query level. Consider materialized balance snapshots.

### M-14: Repeated VAT Report Scans
- **File**: `accounting.py` | **Function**: `get_vat_report()` | **Lines**: 2791-2798
- **Problem**: Loops over accounts, each searching ALL entries. Date filtering in Python, not DB.
- **Fix**: Use DB-level date query with account_code filter.

### M-15: Break-Even Year-End Creates Unnecessary Entries
- **File**: `accounting.py` | **Function**: `post_year_end_closing()` | **Lines**: 614-616
- **Problem**: Posts two 0.01 entries to 3100 as workaround for break-even.
- **Fix**: Skip entry creation if net_to_retained == 0.

### M-16: Expired Sessions Not Auto-Cleaned
- **File**: `server_code/auth_sessions.py` | **Lines**: 130-144
- **Problem**: `cleanup_expired_sessions()` exists but no scheduler calls it. Stale sessions accumulate.
- **Fix**: Add scheduled task or call cleanup on each login.

### M-17: Rate Limit Fail-Open
- **File**: `server_code/auth_rate_limit.py` | **Lines**: 55
- **Problem**: Returns `True` (allow) on any exception. DB issues disable rate limiting.
- **Fix**: Return `False` (deny) on error. Fail-closed is more secure.

### M-18: OTP Timing Side-Channel
- **File**: `server_code/AuthManager.py` | **Lines**: 305-342
- **Problem**: No constant-time comparison for OTP verification. DB lookup timing varies.
- **Fix**: Use `secrets.compare_digest()` for hash comparison. Add constant delay.

### M-19: Restore Function Clears Audit Trail
- **File**: `server_code/QuotationManager.py` | **Lines**: 707
- **Problem**: `row.update(deleted_at=None, deleted_by=None)` erases who deleted and when.
- **Fix**: Keep deletion history. Add `restored_at`, `restored_by` fields instead of clearing.

### M-20: Soft-Delete Email Case Sensitivity
- **File**: `server_code/QuotationManager.py` | **Lines**: 641
- **Problem**: Email comparison uses `.lower()` but `created_by` may not be normalized at write time.
- **Fix**: Normalize email to lowercase at save time (both created_by and updated_by).

---

## LOW Issues

### L-01: Phone Sanitization Silent
- **File**: `QuotationManager.py` | **Lines**: 267-273
- **Problem**: Invalid phone characters stripped silently instead of rejected.
- **Fix**: Return validation error to user.

### L-02: Client Name Redundancy
- **File**: `QuotationManager.py` | **Lines**: 538, 599
- **Problem**: Client name stored in quotation row. Gets stale if client name changes.
- **Fix**: Store only Client Code. Lookup name at query time.

---

## Mathematical Validation Summary

| Function | Debits | Credits | Balanced |
|----------|--------|---------|----------|
| post_purchase_invoice | DR 1210 + DR 2110 | CR 2000 | YES: cost + tax = total |
| pay_import_cost | DR 1210/1200/2110 | CR Bank | YES: single amount |
| record_supplier_payment | DR 2000 + DR 6110 | CR Bank + CR 4110 | YES: complex but balanced |
| record_customer_collection | DR Bank | CR 1100 | YES |
| create_contract_purchase | DR 1210 | CR 2000 | YES |
| sell_inventory (COGS) | DR 5000 | CR 1200 | YES |
| sell_inventory (Sales) | DR 1100 | CR 4000 + CR 2100 | YES |
| move_purchase_to_inventory | DR 1200 | CR 1210 | YES |
| post_opening_balances | DR/CR per type | CR/DR 3000 | YES (with caveats on negatives) |
| post_year_end_closing | DR Revenue, CR Expense | CR/DR 3100 | YES |
| create_treasury_transaction | DR/CR per type | CR/DR counterpart | YES (via post_journal_entry) |

**All debit/credit entries are mathematically balanced.** The 0.005 tolerance in `post_journal_entry` ensures rounding doesn't cause rejection.

---

## Concurrency Analysis

| Function | Protection | Status |
|----------|------------|--------|
| Quotation numbering | `@in_transaction` + max() | SAFE |
| Contract serial | Non-atomic scan | VULNERABLE (C-08) |
| Journal entry posting | `@in_transaction` wrapper | SAFE |
| Purchase invoice registry | Registry table + check | MOSTLY SAFE (H-05 edge case) |
| Move to inventory | `inventory_moved` flag check | SAFE (idempotent) |
| Supplier payment | Remaining balance check | RACE POSSIBLE (check-then-act gap) |

---

## Performance Bottlenecks

| Function | Issue | Impact at 100k Rows |
|----------|-------|---------------------|
| `_get_all_balances()` | Full ledger scan | ~5-10s per call |
| `_get_customer_ar_balance()` | N+1 per contract | ~30s for 500 contracts |
| `get_vat_report()` | Repeated scans per account | ~3-5s per call |
| `get_supplier_aging()` | Nested loops over invoices | ~10s for 200 invoices |
| `_get_next_contract_serial_from_table()` | Full contracts scan | ~1s (acceptable) |

---

## Audit Metadata

- **Total Python files analyzed**: 31 server modules + 24 client modules = 55
- **Total JavaScript files analyzed**: 16
- **Total functions traced**: 270+ server callables + 50+ helpers + 30+ JS bridges
- **Timestamp**: 2026-02-18T21:30:00Z
- **Auditor**: Claude Opus 4.6 (Forensic ERP Audit Agent)

# Verification Audit: record_supplier_payment (FX Logic)

**Scope:** Correctness and edge-case safety of the updated FX logic. No design changes.  
**File:** `server_code/accounting.py`.

---

## STEP 1 — INVOICE RATE SAFETY

When payment currency is foreign (e.g. USD), `liability_slice_egp = amount_in × invoice_rate`.

### 1) What happens if invoice_rate is NULL?

**Code path (lines 1438–1444):**

```1438:1444:server_code/accounting.py
        # Invoice rate (for liability_slice when paying in foreign currency by amount)
        try:
            invoice_rate = _round2(float(row.get('exchange_rate_usd_to_egp') or 0)) if row.get('exchange_rate_usd_to_egp') else _get_rate_to_egp(currency_code)
        except (TypeError, ValueError):
            invoice_rate = _get_rate_to_egp(currency_code)
        if invoice_rate <= 0:
            invoice_rate = _get_rate_to_egp(currency_code)
```

- If `row.get('exchange_rate_usd_to_egp')` is **None** or falsy: the ternary uses **`_get_rate_to_egp(currency_code)`**.
- **`_get_rate_to_egp`** (lines 188–198) returns **1.0** when the currency table has no row or no `rate_to_egp`:

```188:198:server_code/accounting.py
def _get_rate_to_egp(currency_code):
    """Return exchange rate to EGP for the given currency. EGP or missing => 1.0."""
    ...
    return 1.0
```

So when the invoice rate is NULL, **invoice_rate becomes 1.0** (fallback). There is **no** rejection of the payment; liability_slice is computed with a wrong rate (1.0 for USD).

### 2) What happens if invoice_rate = 0?

- First assignment can yield `_round2(float(0))` = **0.0**.
- Then `if invoice_rate <= 0: invoice_rate = _get_rate_to_egp(currency_code)` → again **1.0** for USD if table rate is missing.
- So **0 is replaced by 1.0**; again no validation that blocks the payment.

### 3) Is there a validation that prevents payment when invoice_rate is missing?

**No.** There is no check that `invoice_rate > 0` (or that it was actually taken from the invoice) before using it for foreign-currency “pay by amount”. The code only falls back to `_get_rate_to_egp`, which can return 1.0.

**Conclusion (Step 1):** If the invoice has no or zero `exchange_rate_usd_to_egp` and the currency table has no valid rate, the system uses **1.0** and does **not** prevent the payment. This is an edge-case risk.

---

## STEP 2 — OVERPAYMENT PROTECTION

### 1) Confirm liability_slice_egp is capped at remaining_egp.

**Yes.** Explicit cap in all branches:

- **is_paid_in_full:** `liability_slice_egp = remaining_egp` (line 1448) — equals remaining, no excess.
- **pct:** `liability_slice_egp = min(liability_slice_egp, remaining_egp)` (line 1454).
- **Pay by amount:** `liability_slice_egp = min(liability_slice_egp, remaining_egp)` (line 1471).

**Lines:** 1448, 1454, 1471.

### 2) Confirm system prevents reducing 2000 below zero.

- 2000 is **debited** by `liability_slice_egp` only (line 1495).
- `liability_slice_egp` is always ≤ `remaining_egp` (capped as above).
- `remaining_egp` is the current ledger balance for this invoice (credits − debits on 2000). So **DR 2000 = liability_slice_egp** never exceeds the current balance; 2000 cannot go negative for this invoice.

### 3) Confirm fx_diff cannot cause imbalance.

Entries (lines 1494–1506):

- DR 2000 = `liability_slice_egp`
- CR Bank = `payment_egp`
- If `fx_diff > 0`: CR 4110 = `fx_diff`
- If `fx_diff < 0`: DR 6110 = `-fx_diff`

**Definition:** `fx_diff = liability_slice_egp - payment_egp` (line 1476).

So:
- Total DR = `liability_slice_egp` + max(0, `-fx_diff`) = `liability_slice_egp` + max(0, `payment_egp - liability_slice_egp`).
- Total CR = `payment_egp` + max(0, `fx_diff`) = `payment_egp` + max(0, `liability_slice_egp - payment_egp`).

Algebra: Total DR = Total CR (both = `liability_slice_egp` + `payment_egp` − min(liability_slice_egp, payment_egp) in the two cases). So **every payment’s journal is balanced**; fx_diff does not create imbalance.

---

## STEP 3 — PERCENTAGE PAYMENT SAFETY

### 1) If percentage-only payment is used: is foreign currency allowed? How is payment_rate handled? Could FX be silently skipped?

**Code (lines 1465–1471):**

```1465:1471:server_code/accounting.py
        if is_paid_in_full or (pct is not None and amount_in > 0):
            payment_egp = amount_in * payment_rate if currency_code != 'EGP' else amount_in
            payment_egp = _round2(payment_egp)
        elif pct is not None:
            payment_egp = liability_slice_egp
        else:
```

- **Percentage-only** = `pct` set and **amount_in == 0** (or not provided). Then we take **`elif pct is not None`** and set **`payment_egp = liability_slice_egp`** (line 1470).
- So **payment_egp** is set from the **liability slice**, not from any amount × payment_rate. **payment_rate** (and hence foreign currency) is **not** used for the bank credit in this branch.
- So **fx_diff = liability_slice_egp − payment_egp = 0** → **no FX is posted**.

So:
- Foreign currency is “allowed” in the sense that the API accepts it, but for percentage-only (no amount) the system **ignores** it and treats the payment as EGP for the same value as the slice.
- **payment_rate** is not used when `pct` is set and `amount_in` is 0.
- **FX is silently skipped** in that path: we always get fx_diff = 0.

### 2) Confirm percentage path cannot create hidden FX inconsistencies.

- If the user **actually** pays in foreign currency (e.g. USD) but only sends percentage (no amount), the system credits **Bank with liability_slice_egp (EGP)** and posts **no** 4110/6110. So we record “paid in EGP” and no FX. That is **consistent** only if the payment was really in EGP. If it was in USD, we have a **conceptual** inconsistency (wrong cash amount and no FX), but the **ledger** is still balanced (DR 2000 = CR Bank).
- So the percentage-only path does **not** create a **double-entry** imbalance, but it **can** create a **reporting/economic** inconsistency if the user paid in foreign currency and the UI sends only percentage.

---

## STEP 4 — MULTIPLE PARTIAL PAYMENTS TEST

**Scenario:** Invoice 1000 USD at rate 30 → **30,000 EGP** (CR 2000).  
Payments:

- Payment 1: 400 USD at rate 32  
- Payment 2: 300 USD at rate 29  
- Payment 3: 300 USD at rate 31  

**Payment 1 (400 USD @ 32)**  
- remaining_egp = 30,000. invoice_rate = 30, payment_rate = 32.  
- liability_slice_egp = min(400×30, 30,000) = **12,000**.  
- payment_egp = 400×32 = **12,800**.  
- fx_diff = 12,000 − 12,800 = **−800** (loss → DR 6110 800).  
- Remaining after: 30,000 − 12,000 = **18,000**.

**Payment 2 (300 USD @ 29)**  
- remaining_egp = 18,000.  
- liability_slice_egp = min(300×30, 18,000) = **9,000**.  
- payment_egp = 300×29 = **8,700**.  
- fx_diff = 9,000 − 8,700 = **+300** (gain → CR 4110 300).  
- Remaining after: 18,000 − 9,000 = **9,000**.

**Payment 3 (300 USD @ 31)**  
- remaining_egp = 9,000.  
- liability_slice_egp = min(300×30, 9,000) = **9,000**.  
- payment_egp = 300×31 = **9,300**.  
- fx_diff = 9,000 − 9,300 = **−300** (loss → DR 6110 300).  
- Remaining after: 9,000 − 9,000 = **0**.

**Total FX:** −800 + 300 − 300 = **−800 EGP** (net loss).

**Economic check:** Book liability = 30,000 EGP. Cash paid = 12,800 + 8,700 + 9,300 = **30,800 EGP**. Overpayment = 800 EGP → loss 800. **Matches.**

**Final remaining:** **0.**

---

## STEP 5 — LEDGER BALANCE VALIDATION

After all three payments:

- **Account 2000:** CR 30,000 − DR 12,000 − DR 9,000 − DR 9,000 = **0**. ✓  
- **Bank:** CR 12,800 + 8,700 + 9,300 = **30,800** (total paid at payment rates). ✓  
- **4110:** CR 300 (gain). **6110:** DR 800 + 300 = 1,100 (loss). Net FX = 300 − 1,100 = −800. ✓  
- **Each payment:**  
  - P1: DR 12,000 + 800 = 12,800, CR 12,800. ✓  
  - P2: DR 9,000 = 9,000, CR 8,700 + 300 = 9,000. ✓  
  - P3: DR 9,000 + 300 = 9,300, CR 9,300. ✓  

So: 2000 ends at 0; bank reflects total paid at payment rates; 4110/6110 reflect cumulative FX; every payment’s debits = credits.

---

## STEP 6 — ROUNDING SAFETY

### 1) Are values rounded consistently (e.g. _round2)?

**Yes.** Used for:  
amount_in (1403), pct (1407), payment_rate (1434), invoice_rate (1440), liability_slice_egp (1450, 1456, 1467, 1470), payment_egp (1467, 1473), fx_diff (1476), and new_remaining for status (1518).  
**`_round2`** is defined at lines 77–81 and returns round(float(val), 2) or 0.0 on error.

### 2) Could rounding leave small residual balance on 2000?

- liability_slice_egp is rounded and capped at remaining_egp. So each debit to 2000 is a rounded value.  
- **Theoretical:** e.g. remaining_egp = 10,000.01; user pays by amount such that liability_slice_egp = _round2(amount_in × invoice_rate) = 10,000.00; then new_remaining = 0.01. So a **tiny residual** (e.g. 0.01) can remain on the ledger until another payment clears it. So **yes**, rounding can leave a small residual.

### 3) Is there a tolerance threshold?

**No.** There is no logic that treats “remaining &lt; 0.01” (or similar) as zero and forces a final clearing entry. Status becomes ‘paid’ when `_round2(new_remaining) <= 0` (line 1518), so 0.01 would still be ‘partial’.

---

## OUTPUT SUMMARY

### A) Confirmation of safety

- **Overpayment:** liability_slice_egp is always capped at remaining_egp (lines 1454, 1471; and 1448 by definition).  
- **2000 balance:** DR 2000 never exceeds current remaining; 2000 cannot go negative for the invoice.  
- **Journal balance:** Every payment’s entries (2000, Bank, 4110/6110) are balanced; fx_diff does not break double entry.  
- **Rounding:** All relevant amounts go through _round2.  
- **Multiple partial payments:** Simulated 3-payment scenario shows correct liability slices, payment_egp, fx_diff, final remaining, and total FX matches economic FX.

### B) Discovered edge-case risks

1. **Invoice rate NULL/zero:** If `exchange_rate_usd_to_egp` is missing or 0, code falls back to `_get_rate_to_egp(currency_code)`, which can return **1.0**. No validation blocks payment; liability_slice for foreign “pay by amount” can be wrong (lines 1438–1444, 188–198).  
2. **Percentage-only + foreign currency:** When only percentage is sent (no amount), payment_egp = liability_slice_egp, so fx_diff = 0 and **FX is never posted**. payment_rate is not used. If the user actually paid in USD, cash and FX would be misstated (lines 1469–1470).  
3. **Small residual from rounding:** No tolerance; rounding can leave a small remaining balance (e.g. 0.01) on 2000 with status still ‘partial’ (no automatic zero-out).

### C) Recommended minor hardening (optional)

1. **Invoice rate for foreign “pay by amount”:** After computing `invoice_rate`, if `currency_code != 'EGP'` and `invoice_rate <= 0` (or after fallback still 0), **reject** the payment with a clear message (e.g. “Invoice exchange rate is required for foreign-currency payment by amount”) unless you intentionally allow table fallback.  
2. **Percentage + foreign:** In UI or API contract: when currency is not EGP, require **amount** (and payment rate) so that payment_egp and FX are computed. Alternatively, in backend: if `pct is not None` and `currency_code != 'EGP'` and `amount_in <= 0`, return an error like “Amount is required when paying in foreign currency with percentage.”  
3. **Residual tolerance (optional):** If desired, when `0 < remaining_egp < 0.01` (or another threshold), treat as zero for status and optionally allow a “rounding” clearing entry. Not required for correctness.

### D) Exact file and line references

| Topic | File | Lines |
|-------|------|--------|
| _round2 | server_code/accounting.py | 77–81 |
| _get_rate_to_egp (returns 1.0 fallback) | server_code/accounting.py | 188–198 |
| invoice_rate computation and fallback | server_code/accounting.py | 1438–1444 |
| liability_slice_egp (full / pct / amount), cap | server_code/accounting.py | 1446–1473 |
| payment_egp (incl. percentage-only = liability_slice) | server_code/accounting.py | 1465–1474 |
| fx_diff | server_code/accounting.py | 1476 |
| entries (2000, Bank, 4110/6110) | server_code/accounting.py | 1494–1506 |
| new_remaining, status | server_code/accounting.py | 1516–1518 |

---

*End of verification audit.*

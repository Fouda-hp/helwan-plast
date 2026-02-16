# FX Difference Handling in Supplier Payments — Strict Audit

**Scope:** `record_supplier_payment`, `_get_supplier_remaining_egp`, and related ledger posting.  
**Code reference:** `server_code/accounting.py`.

---

## STEP 1 — REMAINING CALCULATION

### 1) Does `_get_supplier_remaining_egp(invoice_id)` calculate remaining strictly from ledger account 2000?

**Yes.** Remaining is computed only from ledger entries on account `2000` for this invoice.

**Code:**

```1356:1364:server_code/accounting.py
def _get_supplier_remaining_egp(invoice_id):
    """Return remaining AP (2000) liability for this invoice from ledger (credits - debits)."""
    posted = 0.0
    paid = 0.0
    for entry in app_tables.ledger.search(account_code='2000', reference_id=invoice_id, reference_type='purchase_invoice'):
        posted += _round2(entry.get('credit', 0))
    for entry in app_tables.ledger.search(account_code='2000', reference_id=invoice_id, reference_type='payment'):
        paid += _round2(entry.get('debit', 0))
    return _round2(posted - paid)
```

- **Credits** on `2000` with `reference_type='purchase_invoice'` = initial liability (from posting).
- **Debits** on `2000` with `reference_type='payment'` = payments.
- **Remaining** = `posted - paid` (no other source).

---

### 2) Confirm it does NOT use `invoice.total` or `supplier_amount_egp` directly for balance.

**Confirmed.** The function does not read `purchase_invoices` at all. It uses only:

- `app_tables.ledger.search(account_code='2000', reference_id=invoice_id, reference_type='purchase_invoice')` for credits,
- `app_tables.ledger.search(account_code='2000', reference_id=invoice_id, reference_type='payment')` for debits.

So balance is **ledger-only**; `invoice.total` and `supplier_amount_egp` are not used for the remaining calculation.

---

## STEP 2 — PARTIAL PAYMENT FX

### 1) When a partial payment occurs at a different exchange rate: is FX difference calculated immediately?

**No.** FX is not calculated for partial payments.

**Code:** FX entries are added only inside `if is_paid_in_full:`:

```1464:1475:server_code/accounting.py
        # Forex: when paid in full, book difference to 4110 (gain) or 6110 (loss)
        if is_paid_in_full:
            diff = _round2(remaining_egp - payment_egp)
            if diff > 0:
                ...
                entries.append({'account_code': '4110', 'debit': 0, 'credit': diff})
            elif diff < 0:
                ...
                entries.append({'account_code': '6110', 'debit': -diff, 'credit': 0})
```

For non–paid-in-full (partial or percentage), only these entries are posted (lines 1461–1464):

```1461:1464:server_code/accounting.py
        entries = [
            {'account_code': '2000', 'debit': debit_2000, 'credit': 0},
            {'account_code': cash_account, 'debit': 0, 'credit': payment_egp},
        ]
```

No 4110/6110; so **no FX is calculated on partial payments**.

---

### 2) Or is FX only calculated when `is_paid_in_full = true`?

**Yes.** FX (4110/6110) is posted **only when `is_paid_in_full` is True** (same block as above, lines 1465–1474).

---

### 3) If FX is not calculated for partial payments, explain accounting inconsistency risk.

- **Liability (2000)** is reduced by `payment_egp` = amount paid converted at **payment** rate Y.
- **Initial liability** was posted at **invoice** rate X (`supplier_amount_egp`).
- So we mix “EGP at rate X” (initial credit) with “EGP at rate Y” (each payment debit) in the same account, with no FX recognition until final settlement.

**Risks:**

1. **P&L timing:** FX gain/loss is recognized only on final settlement, not when each partial payment occurs. P&L and period-end reporting are distorted (e.g. all FX in one period instead of spread over payment dates).
2. **Mixed-rate remaining:** “Remaining” is arithmetically correct in EGP but is a mix of (original EGP at X) minus (payments at Y1, Y2, …). It does not represent “unpaid portion at original rate” or “unpaid portion at current rate” in a clean way.
3. **Final-settlement FX is only for the last chunk:** When `is_paid_in_full` is True, `diff = remaining_egp - payment_egp` is the FX on **that** remaining balance vs **this** payment. So we only ever book FX for the final payment’s slice, not for earlier partial payments. Earlier partial payments at different rates never get a 4110/6110 entry.

---

## STEP 3 — CORRECT FX FORMULA

### 1) Does the system: reduce 2000 by original EGP equivalent of paid USD; compare with actual EGP paid; post difference to 4110 or 6110?

**Not in that sense.** It does **not** compute “original EGP equivalent of paid USD” (i.e. (paid_USD / total_USD) * supplier_amount_egp).

**What it does (when `is_paid_in_full`):**

- **Reduces 2000** by the **full remaining balance** (ledger remaining), not by “original EGP of paid amount.”
- **Compares** that **remaining_egp** (from ledger: credits − debits on 2000) to **payment_egp** (amount paid converted at **payment** rate Y).
- **Posts** the difference to 4110 or 6110.

So:

- It does **not** use “original EGP equivalent of paid USD.”
- It uses: **remaining EGP (from ledger)** and **actual EGP paid (at payment rate)** and posts **diff = remaining_egp − payment_egp** to 4110/6110.

---

### 2) Or does it use percentage × remaining EGP?

**Only for the *amount* of the payment when paying by percentage**, not for the FX formula itself.

- **Percentage path** (lines 1435–1438): `payment_egp = remaining_egp * (pct / 100)`, `debit_2000 = payment_egp`. So we reduce 2000 by that EGP amount. **No 4110/6110** unless `is_paid_in_full` is True.
- **FX formula** (when `is_paid_in_full`): always `diff = remaining_egp - payment_egp` (line 1466). So it does **not** use “percentage × remaining EGP” as the FX; it uses **remaining_egp** (full remaining) and **payment_egp** (actual payment in EGP at payment rate).

**Exact formula used (code):**

```1466:server_code/accounting.py
            diff = _round2(remaining_egp - payment_egp)
```

Where:

- `remaining_egp` = `_get_supplier_remaining_egp(invoice_id)` = sum(credits 2000, ref invoice) − sum(debits 2000, ref payment).
- `payment_egp` = amount paid in foreign currency × payment exchange rate (or amount if EGP), see lines 1431–1432.

So: **FX = (ledger remaining on 2000) − (actual EGP paid at payment rate)**. No allocation by “original EGP of paid USD” and no percentage in the FX formula.

---

## STEP 4 — MULTIPLE PARTIAL PAYMENTS

### 1) Is FX difference calculated per payment?

**No.** 4110/6110 are only posted when `is_paid_in_full` is True (see STEP 2). So FX is **not** calculated per partial payment.

---

### 2) Or only on final settlement?

**Yes.** FX is only posted on the payment that has **is_paid_in_full = True** (final settlement). That is the only place where `diff = remaining_egp - payment_egp` is computed and 4110/6110 are appended to `entries` (lines 1465–1474).

---

### 3) Could accumulated FX differences be distorted?

**Yes.**

- Each partial payment reduces 2000 by **payment_egp** (at that payment’s rate). So the **remaining** after several partials is:  
  `supplier_amount_egp - (payment1_egp + payment2_egp + ...)`  
  where each `payment_i_egp` is at that payment’s rate. So “remaining” is a mixed-rate EGP number.
- On final settlement we book **one** FX amount: `diff = remaining_egp - payment_egp`. That is the FX on **clearing this remaining balance** at the **last** payment rate. We do **not** book FX for the earlier partial payments.
- So:
  - **Distortion 1:** FX from earlier partial payments (at different rates) is never recognized; only the last chunk’s FX is.
  - **Distortion 2:** If the user never checks “paid in full” and always pays by amount/percentage until the balance is zero, we **never** post to 4110/6110, so total FX on the invoice is never recognized in the P&L.

---

## STEP 5 — OUTPUT

### A) Current implemented FX logic

| Aspect | Implementation |
|--------|----------------|
| **Remaining** | Ledger-only: sum(CR 2000, ref_type=invoice) − sum(DR 2000, ref_type=payment). No use of `invoice.total` or `supplier_amount_egp`. |
| **When FX is posted** | Only when `is_paid_in_full` is True. |
| **FX formula** | `diff = remaining_egp - payment_egp`. If diff > 0 → CR 4110 (gain). If diff < 0 → DR 6110 (loss). |
| **Partial payments** | DR 2000 = payment_egp, CR bank = payment_egp. No 4110/6110. |
| **Percentage payment** | payment_egp = remaining_egp × (pct/100); same posting as partial (no FX unless is_paid_in_full). |

**Relevant code lines:**

- Remaining: **1356–1364** (`_get_supplier_remaining_egp`).
- Payment amount logic: **1427–1444** (payment_egp, debit_2000 for is_paid_in_full / percentage / amount).
- Journal entries: **1461–1464** (2000 + bank).
- FX branch: **1465–1474** (diff, 4110, 6110 only if is_paid_in_full).

---

### B) Identified accounting weaknesses

1. **No FX on partial payments:** Partial payments at a different rate than the invoice do not post to 4110/6110. FX is recognized only on final settlement when “paid in full” is used.
2. **FX only on “paid in full” flag:** If the user settles the balance completely using partial/percentage payments and never checks “paid in full,” no FX is ever posted, even though economic FX occurred.
3. **Single FX amount at settlement:** When `is_paid_in_full` is used, the booked FX is only for (remaining at that moment − last payment in EGP). FX on all previous partial payments is never booked.
4. **Mixed-rate remaining:** Remaining is a mix of original EGP (at invoice rate) and prior payments (at their rates). It is correct as a ledger balance but not as “unpaid at original rate” or “unpaid at current rate” for strict FX allocation.

---

### C) Recommended correction (if FX per payment is required)

**Option 1 — FX per payment (recommended for strict accounting):**

- For **every** payment (partial or full):
  - Allocate a “slice” of the liability being settled:
    - Either by **amount in invoice currency** (e.g. paid_USD), then original_egp_slice = (paid_USD / invoice_total_USD) * supplier_amount_egp,
    - Or by **percentage of remaining** in EGP (current behaviour: payment_egp = remaining_egp × pct/100), and treat that as the “liability slice” in EGP.
  - Compute **payment_egp** = amount paid at **payment** rate (already done).
  - FX for this payment = **liability_slice_egp − payment_egp** (or equivalent), post to 4110/6110.
  - Post: DR 2000 = liability_slice_egp (or payment_egp if you keep 2000 in “payment EGP” and adjust with 4110/6110 to match liability), CR bank = payment_egp, and DR/CR 6110/4110 for diff.

**Option 2 — Keep “FX only on settlement,” but fix “no FX if never paid in full”:**

- When **remaining_egp** becomes zero (or below a tiny threshold) after a payment, treat it as settlement and book `diff = previous_remaining_egp - payment_egp` to 4110/6110 even if the user did not check “paid in full.” That way, when the invoice is fully paid by a series of partials, FX is at least booked once (on the last payment that brings remaining to zero).

**Option 3 — Document and keep current behaviour:**

- If policy is “FX only at final settlement and only when user explicitly selects paid in full,” document it and add a warning in UI when remaining is zero but “paid in full” was never used (suggest one final “paid in full” payment of 0 or run a periodic FX true-up).

---

### D) Exact code lines (reference)

| Item | File | Lines |
|------|------|--------|
| `_get_supplier_remaining_egp` (ledger-only remaining) | `server_code/accounting.py` | 1356–1364 |
| `record_supplier_payment` signature (percentage, is_paid_in_full) | `server_code/accounting.py` | 1381–1384 |
| remaining_egp from ledger | `server_code/accounting.py` | 1416 |
| payment_egp / debit_2000 (is_paid_in_full vs percentage vs amount) | `server_code/accounting.py` | 1427–1444 |
| Base entries (2000, bank) | `server_code/accounting.py` | 1461–1464 |
| FX diff and 4110/6110 (only if is_paid_in_full) | `server_code/accounting.py` | 1465–1474 |
| Initial CR 2000 at post (supplier_amount_egp) | `server_code/accounting.py` | 1053 |

---

*End of audit.*

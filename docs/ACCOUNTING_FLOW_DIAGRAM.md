# Accounting Flow Diagram (EGP Ledger)

Ledger is EGP-only. Key accounts: **1210** (Inventory in Transit), **1200** (Inventory), **2000** (Accounts Payable), **2110** (VAT Input Recoverable), **2100** (VAT Output Payable), **4110** (FX Gain), **6110** (FX Loss), **5000** (COGS), **4000** (Revenue), **1100** (Receivables), **1000/1010–1013** (Cash/Bank).

**VAT rules:** VAT never affects 1210/1200 or 2000. Import VAT → 2110 only. Sales VAT (VAT-inclusive price split) → 2100. Monthly settlement remits net (output − input) to tax authority.

---

## 1. Post Purchase Invoice

```
    DR  1210  Inventory in Transit     supplier cost (EGP)
    CR  2000  Accounts Payable         supplier_amount_egp
```

- **1210** increases (transit).
- **2000** increases (liability).
- **No VAT here** — supplier invoice amount only. Import VAT is recorded separately (see 3b).

---

## 2. Partial Payment (Supplier)

```
    DR  2000  Accounts Payable         liability_slice_egp
    CR  Bank (1000/1010–1013)          payment_egp
    [If FX:]
    CR  4110  Exchange Gain            fx_diff (if gain)
    or
    DR  6110  Exchange Loss            |fx_diff| (if loss)
```

- **2000** decreases.
- **Bank** decreases.
- **4110** or **6110** records realized FX per payment.

---

## 3a. Import Cost (non-VAT) — Before Arrival (Transit)

```
    DR  1210  Inventory in Transit     cost_egp
    CR  Bank (1000/1010–1013)          cost_egp
```

- **1210** increases (still in transit). Applies to shipping, customs, insurance, clearance, other — **not** VAT.

## 3b. Import VAT (Input VAT) — At Customs

```
    DR  2110  VAT Input Recoverable    vat_egp
    CR  Bank (1000/1010–1013)          vat_egp
```

- **2110** increases. VAT is **never** posted to 1210/1200; it does **not** affect `import_costs_total` or inventory `total_cost`.

---

## 4. Move to Inventory

```
    DR  1200  Inventory                total_transit_cost (sum 1210 for invoice)
    CR  1210  Inventory in Transit     total_transit_cost
```

- **1210** → **1200** (transit balance for that invoice cleared into available).

---

## 5. Import Cost — After Arrival

```
    DR  1200  Inventory                 cost_egp
    CR  Bank (1000/1010–1013)          cost_egp
```

- **1200** increases (landed cost).

---

## 6. Sale (COGS & Revenue; VAT-inclusive)

```
    DR  5000  Cost of Goods Sold       total_cost (landed)
    CR  1200  Inventory                total_cost

    DR  1100  Accounts Receivable      selling_price (full VAT-incl)
    CR  4000  Revenue                  net_revenue = selling_price − vat_amount
    CR  2100  VAT Output Payable       vat_amount = selling_price × rate/(100+rate)
```

- **1200** decreases (inventory sold). VAT never affects 1200/1210.
- **1100** receives full selling price; **4000** gets net revenue; **2100** receives output VAT (e.g. 14%).

---

## 7. VAT Settlement (Month-end, Manual)

```
  If output_vat > input_vat (remit to tax authority):
    DR  2100  VAT Output Payable       output_vat
    CR  2110  VAT Input Recoverable   input_vat
    CR  Bank (1000/1010–1013)          net_due = output_vat − input_vat

  If input_vat ≥ output_vat (clear output; carry forward input):
    DR  2100  VAT Output Payable      output_vat
    CR  2110  VAT Input Recoverable   output_vat
```

- Balances as of period end (`date_to`). Period lock applies. Does not modify original VAT transactions.

---

## 8. Unrealized FX (Report Only)

- **No posting.**
- Report: for each open invoice, remaining_egp from **2000**; remaining in original currency at invoice rate; revalue at current rate; unrealized_fx = revalued_egp − remaining_egp.

---

## Flow Overview (Arrows)

```
  Post Purchase Invoice     Partial Payment         Move to Inventory
  ─────────────────────     ───────────────         ──────────────────
        1210 ↑                   2000 ↓                    1210 ↓
        2000 ↑                   Bank ↓                    1200 ↑
                                4110 ↑ or 6110 ↑

  Import (transit)           Import VAT               Import (arrived)       Sale
  ─────────────────          ───────────              ─────────────────      ─────
        1210 ↑                    2110 ↑                    1200 ↑                 1200 ↓
        Bank ↓                    Bank ↓                     Bank ↓                  5000 ↑
                                                                                     1100 ↑
                                                                                     4000 ↑
                                                                                     2100 ↑
```

- **1210** is filled by: post purchase invoice, import cost (non-VAT) before arrival. **Never** by VAT.
- **1210** is cleared by: move to inventory (→ **1200**).
- **2110** is filled by: import cost type VAT only. Cleared by VAT settlement.
- **2100** is filled by: sales (VAT-inclusive split). Cleared by VAT settlement (and Bank when remitting).
- **2000** is increased by: post purchase invoice; decreased by: supplier payments (and FX hits **4110**/**6110**).
- **1200** is increased by: move from 1210, import cost (non-VAT) after arrival; decreased by: COGS on sale (**5000**).

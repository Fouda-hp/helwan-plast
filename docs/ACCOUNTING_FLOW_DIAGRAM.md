# Accounting Flow Diagram (EGP Ledger)

Ledger is EGP-only. Key accounts: **1210** (Inventory in Transit), **1200** (Inventory), **2000** (Accounts Payable), **4110** (FX Gain), **6110** (FX Loss), **5000** (COGS), **4000** (Revenue), **1100** (Receivables), **1000/1010–1013** (Cash/Bank).

---

## 1. Post Purchase Invoice

```
    DR  1210  Inventory in Transit     supplier cost (EGP)
    DR  2110  VAT Input (optional)     if VAT
    CR  2000  Accounts Payable         supplier_amount_egp
```

- **1210** increases (transit).
- **2000** increases (liability).

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

## 3. Import Cost — Before Arrival (Transit)

```
    DR  1210  Inventory in Transit     cost_egp
    CR  Bank (1000/1010–1013)          cost_egp
```

- **1210** increases (still in transit).

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

## 6. Sale (COGS & Revenue)

```
    DR  5000  Cost of Goods Sold       total_cost (landed)
    CR  1200  Inventory                total_cost

    DR  1100  Accounts Receivable      selling_price
    CR  4000  Revenue                  selling_price
```

- **1200** decreases (inventory sold).
- **5000** (COGS) and **4000** (revenue) record P&L.

---

## 7. Unrealized FX (Report Only)

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

  Import (transit)           Import (arrived)       Sale
  ─────────────────          ─────────────────      ─────
        1210 ↑                    1200 ↑                 1200 ↓
        Bank ↓                    Bank ↓                  5000 ↑
                                                         1100 ↑
                                                         4000 ↑
```

- **1210** is filled by: post purchase invoice, import cost before arrival.
- **1210** is cleared by: move to inventory (→ **1200**).
- **2000** is increased by: post purchase invoice; decreased by: supplier payments (and FX hits **4110**/**6110**).
- **1200** is increased by: move from 1210, import cost after arrival; decreased by: COGS on sale (**5000**).

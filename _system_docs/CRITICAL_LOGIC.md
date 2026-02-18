# Critical Business Logic — Helwan Plast ERP

## 1. Pricing Logic

### Two-Tier Pricing System
- **Overseas Clients** (FOB price in USD): Direct dollar pricing, no In Stock/New Order
- **Domestic Clients** (EGP): Prices derived from FOB × Exchange Rate

### Pricing Mode (domestic only)
| Mode | Description | Price Field |
|---|---|---|
| `In Stock` | Machine available in local inventory | `In Stock` (EGP) |
| `New Order` | Machine ordered from supplier | `New Order` (EGP) |
| `Overseas` | FOB direct sale | `FOB price for over seas clients` (USD) |

### Price Calculation Flow (machine_pricing.js)
1. User selects: Machine Type → Colors → Width → Material → Options
2. `buildModelCode()` generates model code string
3. `calculateAll()` computes:
   - Base Machine Price (USD) from `machine_prices.json`
   - Material Adjustment
   - Winder Adjustment
   - Optional feature adjustments
   - Cylinder costs (from cylinders.js)
4. Results stored in `window.STATE`:
   - `baseMachineUSD` — base FOB
   - `overseasUSD` — total FOB for overseas
   - `localInStockEGP` — FOB × Exchange Rate × In Stock markup
   - `localNewOrderEGP` — FOB × Exchange Rate × New Order markup

### Agreed Price Validation (server-side, QuotationManager.py lines 355-415)
- Agreed Price ≤ Given Price (always)
- Overseas: Agreed Price ≥ Overseas Price
- Domestic: In Stock and New Order prices must be > 0
- New Order mode: Agreed Price ≤ In Stock price

## 2. Accounting Rules

### Chart of Accounts (COA)
- Double-entry accounting system
- Accounts organized by type: Asset, Liability, Equity, Revenue, Expense
- Journal entries must balance (total debits = total credits)

### Contract Financial Flow
1. **New Order**: Contract save → auto-create purchase invoice → auto-receive inventory → auto-sell → COGS + Revenue posted
2. **In Stock**: Contract save → sell existing inventory → COGS + Revenue posted
3. **Overseas**: Contract save only (no supplier/inventory accounting)

### Period Locking
- Periods can be closed to prevent backdated entries
- Closed periods can be reopened by admin
- Financial year close posts year-end closing entries
- Opening balances carried forward automatically

### Treasury Transactions
- Cash and bank account tracking
- Supplier payments recorded against invoices
- Customer collections recorded against contracts
- Exchange rate differences tracked per transaction

## 3. Notification Deduplication

### System (notifications.py)
- Each notification has a unique composite key
- Before creating: check if identical notification exists for same user
- Prevents duplicate alerts for same event
- Admin can clear all notifications globally

### Client-Side (notification-bell.js)
- Polls server for unread count via `window.__hpNotifGetUnreadCount`
- Toast shown only for NEW notifications (tracks last seen count)
- Bell badge updates independently from dropdown content

## 4. Payment Schedule Logic

### Payment Methods
- **Percentage**: Each payment is X% of total contract value
- **Amount**: Each payment is a fixed amount in currency

### Validation Rules (ContractPrintForm)
- Sum of all payments must equal total contract value
- Each payment date must be in the future
- No duplicate dates allowed
- Minimum 1 payment, maximum 12

### Overseas Payment Defaults
- 30% down payment upon contract signing
- 70% before shipping
- Currency: USD

## 5. Auto-Numbering Logic (quotation_numbers.py)

### Client Codes
- Format: Sequential number
- Atomic: `get_next_number_atomic()` computes `max(counter, max_table_value) + 1`
- Prevents gaps and duplicates even under concurrent access

### Quotation Numbers
- Same atomic mechanism
- Counter stored in `app_tables.settings`
- Falls back to max value in quotations table if counter is behind

## 6. Backup/Restore (quotation_backup.py)

- Backs up quotations and clients tables to Google Drive
- Scheduled backups with retention policy
- Restore overwrites current data (admin-only)
- Uses JSON serialization for table data

## 7. Exchange Rate Logic

### Storage
- `app_tables.exchange_rates` (currency_code, rate, date)
- Calculator form uses `Exchange Rate` field per quotation

### Pricing Impact
- Domestic EGP prices = USD FOB × Exchange Rate
- Exchange rate changes trigger full recalculation via `window.updateExchangeRate()`
- Rate stored per quotation at save time (snapshot, not live)

## 8. Statement Opening Balances

### Rules (accounting.py)
- Opening balances posted as journal entries at period start
- Each account can have one opening balance entry
- Balances must net to zero across all accounts (debits = credits)
- Admin can set, modify, or delete individual opening balances
- `post_opening_balances()` creates journal entries from saved balances

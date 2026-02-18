# Decision Log — Helwan Plast ERP

Architectural decisions and their rationale.

---

## 1. Why Hash-Based Routing

**Decision**: Use `location.hash` for page navigation instead of standard URL routing.

**Rationale**:
- Anvil framework constraint — Anvil apps are single-page applications
- Hash changes don't cause full page reloads
- Anvil's built-in routing system maps hashes to form classes
- No server roundtrip for navigation — instant form switching
- Deep linking supported: users can bookmark `#calculator` or `#admin`

**Trade-off**: URLs look like `app.com/#calculator` instead of `app.com/calculator`

---

## 2. Why JS-Side Pricing Calculation

**Decision**: Machine pricing calculations run entirely in JavaScript (`machine_pricing.js`), not on the server.

**Rationale**:
- Real-time feedback: prices update instantly as user changes options
- No network latency — each dropdown change would require server roundtrip otherwise
- Complex calculation with many variables (machine type, colors, width, material, winder, options, cylinders)
- Exchange rate changes trigger instant recalculation
- Settings loaded once from server via `applyCalculatorSettingsFromPython()`

**Trade-off**: Pricing logic is duplicated (JS calculates, server validates). Server-side validation in `QuotationManager.py` ensures integrity.

---

## 3. Why JS-Python Bridge Pattern

**Decision**: Use a bridge pattern where Python sets functions on `window` object and JS calls them, and vice versa.

**Rationale**:
- Skulpt (Python-to-JS compiler) cannot directly interact with native JS APIs
- `anvil.js.window` provides the interop layer
- JS UI code (event handlers, DOM manipulation) is more natural in native JS
- Python handles business logic, server calls, and data processing
- Bridge allows each language to do what it does best

**Pattern**:
```
Python registers: anvil.js.window.callPythonSave = self._save
JS calls:         await window.callPythonSave?.()
```

**Trade-off**: Functions must be registered in `form_show` event. If form hasn't loaded yet, JS calls return undefined (hence `?.()` optional chaining).

---

## 4. Why Current Accounting Structure

**Decision**: Full double-entry accounting with COA, journal entries, period locks, and automated COGS/Revenue posting.

**Rationale**:
- Manufacturing business needs proper cost tracking (raw materials → finished goods)
- Supplier payments in multiple currencies (USD, EUR, CNY) require FX tracking
- Period locking prevents backdated entries that would invalidate reports
- Auto-posting on contract save ensures accounting is always in sync with sales
- Trial balance, income statement, balance sheet generated from journal entries

**Key Design**:
- New Order contracts auto-create: Purchase Invoice → Receive Inventory → Sell → COGS + Revenue
- In Stock contracts: Sell existing inventory → COGS + Revenue
- Overseas contracts: No supplier accounting (direct sale)

---

## 5. Why Custom Authentication (Not Anvil Users)

**Decision**: Build custom auth system instead of using Anvil's built-in `anvil.users`.

**Rationale**:
- Need for multi-factor: Password + TOTP + WebAuthn + Email OTP
- Role-based access control with granular permissions
- User approval workflow (admin must approve new registrations)
- Rate limiting and audit logging requirements
- Session management with configurable TTL
- Emergency admin recovery procedures

**Trade-off**: Significant code complexity (11 auth modules). But provides enterprise-grade security.

---

## 6. Why Client-Side PDF Export

**Decision**: PDF generation uses `html2canvas` + `jsPDF` in the browser, not server-side rendering.

**Rationale**:
- WYSIWYG: PDF matches exactly what user sees on screen
- No server load for PDF generation
- Complex HTML/CSS layouts render correctly (tables, grids, Arabic text)
- Instant export — no server roundtrip

**Exception**: Server-side PDF reports (`pdf_reports.py` using ReportLab) used for financial reports that need precise formatting.

---

## 7. Why Separate Print Forms (QuotationPrintForm / ContractPrintForm)

**Decision**: Dedicated forms for print/PDF instead of reusing the calculator form.

**Rationale**:
- Print layout is fundamentally different from edit layout
- A4 page sizing needs precise CSS control
- Multiple pages (specs, payment schedule, terms) need page break management
- Bilingual support (Arabic/English) with RTL/LTR switching
- Clean separation: edit form focuses on data entry, print form on presentation

---

## 8. Why BroadcastChannel for Settings Sync

**Decision**: Use `BroadcastChannel` API to sync calculator settings across browser tabs.

**Rationale**:
- Multiple users or tabs may have the calculator open simultaneously
- When admin updates machine prices, all open calculators should refresh
- BroadcastChannel is lightweight and built into modern browsers
- No WebSocket server needed

**Trade-off**: Only works within same browser origin. Cross-device sync requires server notification (handled by notification system).

---

## 9. Why Atomic Auto-Numbering

**Decision**: Use atomic `max(counter, max_table) + 1` pattern for quotation and client code numbering.

**Rationale**:
- Concurrent users could generate duplicate numbers with simple increment
- Server-side counter in `app_tables.settings` provides sequence
- Fallback to max table value ensures no gaps even if counter resets
- Atomic operation prevents race conditions

---

## 10. Why Google Drive for Backups

**Decision**: Use Google Drive (via Anvil's Google integration) for backup storage.

**Rationale**:
- Anvil has built-in Google Drive integration
- No additional infrastructure needed
- Familiar to users (can browse backups in Drive)
- Scheduled backups with retention policy
- Restore available from admin panel

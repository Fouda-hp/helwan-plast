# System Overview — Helwan Plast ERP

## Architecture

- **Framework**: Anvil (Python-based web framework)
- **Client Runtime**: Skulpt (Python-to-JS compiler in browser)
- **Server Runtime**: Python 3 on Anvil cloud
- **Database**: Anvil Data Tables (PostgreSQL-backed)
- **Deployment**: Anvil Git push (`ssh://anvil.works:2222/`)

## Technology Stack

| Layer | Technology |
|---|---|
| Server Logic | Python 3 (anvil.server) |
| Client Logic | Python (Skulpt) + JavaScript |
| UI Forms | Anvil HtmlTemplate components |
| PDF Export | html2canvas + jsPDF (client-side) |
| PDF Reports | ReportLab (server-side, via pdf_reports.py) |
| Auth | Custom: Password + TOTP + WebAuthn + Email OTP |
| i18n | Custom JS (i18n.js) — Arabic/English |
| Real-time Sync | BroadcastChannel API (settings across tabs) |

## Data Flow

```
User Action
  → JS Event Handler (theme/assets/*.js)
    → window.collectFormData() — collects DOM → dict
    → window.callPythonSave() — JS-to-Python bridge
      → Anvil Client Python (__init__.py)
        → anvil.server.call('function_name', data)
          → Server Python (QuotationManager.py / accounting.py)
            → app_tables.quotations.add_row(data)
            → Return {success, message}
          ← Response
        ← Update UI
      ← Show alert
    ← Done
```

## Routing Model

- **Type**: Hash-based routing (Anvil framework)
- **Router**: `client_code/routing.py`
- **Hash Targets**:
  - `#launcher` — Main menu (LauncherForm)
  - `#calculator` — Pricing calculator (CalculatorForm)
  - `#admin` — Admin panel (AdminPanel)
  - `#login` — Login page (LoginForm)
  - `#accountant` — Accounting dashboard (AccountantForm)
  - `#clients` — Client list (ClientListForm)
  - `#database` — Database view (DatabaseForm)
  - `#followup` — Follow-up dashboard (FollowUpDashboardForm)
  - `#payments` — Payment dashboard (PaymentDashboardForm)
  - `#inventory` — Inventory management (InventoryForm)
  - `#invoices` — Purchase invoices (PurchaseInvoicesForm)
  - `#suppliers` — Suppliers management (SuppliersForm)
  - `#contract-print` — Contract print form (ContractPrintForm)
  - `#quotation-print` — Quotation print form (QuotationPrintForm)

## JS-Python Bridge Model

### Python → JS (client code calling window functions)
```python
# In client_code/SomeForm/__init__.py
anvil.js.window.functionName(args)
anvil.js.window.document.getElementById('id')
```

### JS → Python (JS calling Python methods)
```javascript
// In theme/assets/Calculator/ui.js
const result = await window.callPythonSave?.();
// window.callPythonSave is set by client Python code
```

### Bridge Registration Pattern
```python
# Python sets a function on the window object
anvil.js.window.callPythonSave = self._save_handler
anvil.js.window.getClientsForOverlay = self._get_clients
```

## Module Groups

### Server-Side
- **Auth Chain**: AuthManager → auth_sessions, auth_password, auth_totp, auth_webauthn, auth_email, auth_rate_limit, auth_audit, auth_utils, auth_constants, auth_permissions
- **Business Logic**: QuotationManager, accounting, quotation_pdf, quotation_numbers, quotation_backup, pdf_reports
- **Features**: notifications, client_notes, client_timeline, followup_reminders

### Client-Side
- **Forms**: 19 form components (each with `__init__.py` + `form_template.yaml`)
- **Bridges**: js_bridge.py, notif_bridge.py, auth_helpers.py, routing.py

### JavaScript
- **Calculator** (9 files): core_v2, utils, form, ui, clients, quotations, machine_pricing, cylinders, colors_change_patch
- **Global** (7 files): global-loading, i18n, button-lock, notification-bell, notification-system, admin-panel, webauthn-helper

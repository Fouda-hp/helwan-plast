# AI Context — Helwan Plast ERP

Guidelines for AI agents working on this codebase.

---

## Architectural Constraints

### Skulpt Runtime (Client-Side)
- Client Python runs in Skulpt (Python-to-JS compiler), NOT CPython
- **Cannot** import server modules in client code: `from server_code.module import func` will FAIL
- **Cannot** use `import` for standard library modules not supported by Skulpt
- Must use `anvil.server.call('function_name', args)` to call server functions
- Format strings: `"{:,.0f}".format(n)` works; f-strings work in recent Skulpt

### Anvil Framework Rules
- Each form is a directory: `FormName/__init__.py` + `FormName/form_template.yaml`
- `form_template.yaml` contains HTML, CSS, and inline `<script>` blocks
- Forms are registered automatically via directory presence — no manual registration needed
- `anvil.yaml` defines database schema (`db_schema`), services, and dependencies
- `auto_create_missing_columns: false` — columns must be defined in `anvil.yaml` before use

### Database
- Tables defined in `anvil.yaml` under `db_schema`
- Adding a column requires editing `anvil.yaml` (type: string/number/bool/date/datetime)
- Row access: `app_tables.table_name.get(column=value)` or `.search()`
- No raw SQL — use Anvil's query API (`anvil.tables.query`)

---

## Forbidden Refactors

### DO NOT rename or remove:
- `window.callPythonSave` — Save button bridge, used in ui.js line 28
- `window.collectFormData` — Form data collection, defined in form.js
- `window.resetFormToNew` — Form reset, defined in core_v2.js
- `window.calculateAll` — Price recalculation, defined in machine_pricing.js
- `window.buildModelCode` — Model code builder, defined in machine_pricing.js
- `window.applyCalculatorSettingsFromPython` — Settings bridge
- `window.initDefaultValues` — Form initialization
- `window.showAlert` / `window.hideAlert` — Alert system
- `window.showLoadingOverlay` / `window.hideLoadingOverlay` — Loading system
- `window.i18n` — Internationalization singleton
- Any `window.__hpNotif*` functions — Notification bridge
- Any `window.py*` functions — Python bridge registrations

### DO NOT modify:
- `server_code/accounting.py` financial calculation logic without full audit
- `server_code/QuotationManager.py` save validation logic (lines 355-415)
- Authentication chain (AuthManager → auth_*.py modules)
- Period lock enforcement in accounting
- Auto-numbering atomic logic in quotation_numbers.py

---

## Bridge Rules

### Python → JS Pattern
```python
# Always use anvil.js.window
anvil.js.window.functionName(arg1, arg2)

# DOM access
el = anvil.js.window.document.getElementById('elementId')
el.textContent = "value"
```

### JS → Python Pattern
```javascript
// Functions set on window by Python client code
const result = await window.callPythonSave?.();
// Optional chaining (?.) is standard — function may not be set yet

// Direct Anvil server call from JS (rare)
anvil.call(server, 'function_name', args)
```

### Bridge Registration (in client __init__.py)
```python
def form_show(self, **event_args):
    anvil.js.window.callPythonSave = self._handle_save
    anvil.js.window.getClientsForOverlay = self._get_clients_for_overlay
```

---

## Routing Rules

- Hash-based: `location.hash = "#page-name"`
- Router in `client_code/routing.py` maps hashes to form classes
- Changing hash triggers Anvil form switch — NO manual DOM manipulation needed
- Each form has `form_show` event handler for initialization

---

## Naming Conventions

### Python
- Server modules: `snake_case.py` (e.g., `quotation_pdf.py`)
- Exception: `AuthManager.py`, `QuotationManager.py` (PascalCase — main orchestrators)
- Server callables: `snake_case` (e.g., `get_all_quotations`)
- Form directories: `PascalCase` (e.g., `CalculatorForm/`)

### JavaScript
- Files: `kebab-case.js` (e.g., `global-loading.js`) or `snake_case.js` (e.g., `core_v2.js`)
- Calculator files: `snake_case.js`
- Window functions: `camelCase` (e.g., `window.callPythonSave`)

### Database Columns
- Mixed naming: some `PascalCase` (`Client Name`), some `snake_case` (`is_deleted`)
- Column names include spaces: `Overseas clients`, `Machine type`, `Number of colors`
- Must match exactly in Python code and YAML schema

---

## CSS Rules

### form_template.yaml CSS
- CSS is embedded in the `html` property of `form_template.yaml`
- Some properties use `!important` — inline styles may be overridden
- Print styles: `@media print` sections control PDF export appearance
- PDF export uses `pdf-export-mode` class for sizing

### Theme CSS
- `theme.css` — Global styles
- `responsive.css` — Mobile breakpoints
- Both loaded via `standard-page.html`

---

## Testing

- Server tests in `server_code/tests/`
- Tests use Anvil's testing framework
- Run via Anvil's test runner (not pytest directly)
- Test files: accounting hardening, integration, enterprise, scenarios, opening balances, transit inventory, treasury period

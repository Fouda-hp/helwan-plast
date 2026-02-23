# File Index — Helwan Plast ERP

## Directory Tree

```
Helwan_Plast/
├── __init__.py                          # Anvil package init (sets module paths)
├── anvil.yaml                           # Master config: tables, services, dependencies
├── README.md                            # Project README
├── LICENSE.txt                          # License
│
├── server_code/
│   ├── requirements.txt                 # Python dependencies
│   ├── AUTH_STRUCTURE.md                # Auth architecture documentation
│   │
│   ├── AuthManager.py                   # Authentication orchestrator (67 callables)
│   ├── auth_audit.py                    # Audit logging (log_audit)
│   ├── auth_constants.py                # Auth constants (session TTL, OTP length)
│   ├── auth_email.py                    # Email sending (SMTP, approval emails)
│   ├── auth_password.py                 # Password hashing (argon2/bcrypt)
│   ├── auth_permissions.py              # Permission checks (check_permission, is_admin)
│   ├── auth_rate_limit.py               # Rate limiting (IP-based)
│   ├── auth_sessions.py                 # Session management (create/validate/destroy)
│   ├── auth_totp.py                     # TOTP 2FA (setup, verify, backup codes)
│   ├── auth_utils.py                    # Utilities (get_utc_now, validate_email)
│   ├── auth_webauthn.py                 # WebAuthn/Passkey support (9 callables)
│   │
│   ├── QuotationManager.py              # Quotation/Contract CRUD (65+ callables)
│   ├── accounting.py                    # Full accounting module (100+ callables)
│   ├── accounting_suppliers.py          # Suppliers & Service Suppliers CRUD (extracted)
│   ├── quotation_pdf.py                 # PDF data builder for quotations
│   ├── quotation_numbers.py             # Auto-numbering (client codes, quotation#)
│   ├── quotation_backup.py              # Backup/restore to Google Drive
│   ├── pdf_reports.py                   # ReportLab PDF generation
│   ├── purchase_invoices_view.py        # Purchase invoice view callables
│   ├── sales_invoices.py               # Sales invoice management
│   │
│   ├── notifications.py                 # Notification system (9 callables)
│   ├── client_notes.py                  # Client notes & tags (6 callables)
│   ├── client_timeline.py               # Client timeline (2 callables)
│   ├── followup_reminders.py            # Follow-up reminders (6 callables)
│   ├── monitoring.py                    # Health check & metrics endpoints
│   │
│   ├── shared_utils.py                  # Shared utilities (bounded_search, contracts_search)
│   ├── cache_manager.py                 # Thread-safe TTL cache manager
│   ├── structured_logging.py            # Structured logging & request timing
│   │
│   ├── fonts/dejavu-sans/               # DejaVuSans fonts for PDF rendering
│   └── tests/                           # Test suite (7 test files)
│
├── client_code/
│   ├── routing.py                       # Hash-based form router
│   ├── js_bridge.py                     # JS bridge utilities
│   ├── notif_bridge.py                  # Notification bridge (Python ↔ JS)
│   ├── auth_helpers.py                  # Auth token validation helper
│   │
│   ├── LoginForm/                       # Login/Register/Password Reset
│   ├── LauncherForm/                    # Main menu + TOTP/WebAuthn setup
│   ├── CalculatorForm/                  # Pricing calculator (main form)
│   ├── QuotationPrintForm/              # Quotation PDF preview/export
│   ├── ContractPrintForm/               # Contract PDF preview/export
│   ├── ContractEditForm/                # Contract editing
│   ├── AdminPanel/                      # Admin dashboard
│   ├── AccountantForm/                  # Accounting dashboard
│   ├── ClientListForm/                  # Client listing/search
│   ├── ClientDetailForm/                # Client detail + notes + timeline
│   ├── CustomerSummaryForm/             # Customer financial summary
│   ├── SupplierSummaryForm/             # Supplier financial summary
│   ├── SuppliersForm/                   # Supplier CRUD
│   ├── DatabaseForm/                    # Database browser
│   ├── DataImportForm/                  # CSV data import
│   ├── FollowUpDashboardForm/           # Follow-up reminders dashboard
│   ├── InvoiceManagerForm/              # Invoice manager (sales + service suppliers)
│   ├── InventoryForm/                   # Inventory management
│   ├── PaymentDashboardForm/            # Payment tracking dashboard
│   ├── PurchaseInvoicesForm/            # Purchase invoice management
│   ├── PurchaseInvoiceViewForm/         # Purchase invoice detail view
│   ├── SalesInvoiceForm/               # Sales invoice management
│   └── ServiceSuppliersForm/           # Service suppliers CRUD
│
├── theme/
│   ├── parameters.yaml                  # Theme variables
│   ├── templates.yaml                   # Template definitions
│   └── assets/
│       ├── standard-page.html           # Base HTML template (loads all JS)
│       ├── theme.css                    # Global theme styles
│       ├── responsive.css               # Mobile responsive styles
│       ├── robots.txt                   # SEO robots
│       ├── machine_prices.json          # Machine pricing data
│       ├── helwan_logo.png              # Company logos
│       ├── helwan_logo-logo.png
│       ├── flexo_logo.png
│       ├── admin.png
│       │
│       ├── global-loading.js            # Loading overlay system
│       ├── i18n.js                      # Internationalization (AR/EN)
│       ├── button-lock.js               # Double-click prevention
│       ├── notification-bell.js         # Notification bell UI
│       ├── notification-system.js       # Notification fallback system
│       ├── admin-panel.js               # Admin panel JS
│       ├── webauthn-helper.js           # WebAuthn client helper
│       │
│       └── Calculator/
│           ├── core_v2.js               # Form initialization, reset
│           ├── utils.js                 # Utilities (debug, debounce, timers)
│           ├── form.js                  # collectFormData() — DOM → dict
│           ├── ui.js                    # UI handlers (save, alerts, modals)
│           ├── clients.js               # Client search overlay
│           ├── quotations.js            # Quotation search overlay
│           ├── machine_pricing.js       # Price calculation engine
│           ├── cylinders.js             # Cylinder pricing/validation
│           └── colors_change_patch.js   # Color change event handler
│
├── docs/                                # Accounting & architecture docs (14 files)
├── _archive/                            # Archived stale documentation (22 files)
├── _system_audit/                       # Audit reports from this cleanup
├── _system_docs/                        # THIS documentation set
└── .auto-claude/                        # AI development framework (specs, worktrees)
```

## Module Dependency Chains

### Authentication Chain
```
AuthManager.py
  ├── auth_constants.py
  ├── auth_utils.py
  ├── auth_password.py
  ├── auth_sessions.py
  ├── auth_totp.py
  ├── auth_webauthn.py
  ├── auth_email.py
  ├── auth_rate_limit.py
  ├── auth_audit.py
  └── auth_permissions.py
```

### Business Logic Chain
```
QuotationManager.py
  ├── AuthManager (token validation)
  ├── quotation_backup (Google Drive backup)
  └── accounting (contract save triggers accounting)
        ├── AuthManager (permission checks)
        ├── accounting_suppliers (Suppliers & Service Suppliers CRUD)
        ├── cache_manager (thread-safe TTL caches)
        └── pdf_reports (PDF generation)

quotation_pdf.py (standalone, called from client)
quotation_numbers.py (standalone, called from client)
purchase_invoices_view.py → accounting (journal entries)
sales_invoices.py → accounting (journal entries)
monitoring.py → auth_permissions, cache_manager
```

### Feature Modules (standalone)
```
notifications.py    → app_tables only
client_notes.py     → app_tables only
client_timeline.py  → app_tables only
followup_reminders.py → app_tables only
```

## JavaScript Load Order

All JS files are loaded via `standard-page.html` in this order:
1. `global-loading.js` — Loading overlay (immediate)
2. `i18n.js` — Internationalization
3. `button-lock.js` — Double-click prevention
4. `notification-system.js` — Notification fallback
5. `notification-bell.js` — Notification bell
6. `webauthn-helper.js` — WebAuthn
7. `admin-panel.js` — Admin panel
8. `Calculator/utils.js` — Utilities
9. `Calculator/form.js` — Form data collection
10. `Calculator/core_v2.js` — Core initialization
11. `Calculator/ui.js` — UI interactions
12. `Calculator/clients.js` — Client overlay
13. `Calculator/quotations.js` — Quotation overlay
14. `Calculator/machine_pricing.js` — Pricing engine
15. `Calculator/cylinders.js` — Cylinder pricing
16. `Calculator/colors_change_patch.js` — Color patch

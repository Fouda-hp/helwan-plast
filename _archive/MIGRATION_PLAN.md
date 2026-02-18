# خطة تحويل نظام Helwan Plast من Anvil إلى تطبيق مستقل
# Helwan Plast Migration Plan: Anvil → Standalone Application

---

## الفهرس (Table of Contents)

1. [نظرة عامة (Overview)](#1-نظرة-عامة)
2. [الهندسة المعمارية (Architecture)](#2-الهندسة-المعمارية)
3. [قاعدة البيانات (Database Schema)](#3-قاعدة-البيانات)
4. [الـ API Endpoints](#4-الـ-api-endpoints)
5. [شاشات Flutter](#5-شاشات-flutter)
6. [تطبيق سطح المكتب Electron](#6-تطبيق-سطح-المكتب-electron)
7. [الأمان والصلاحيات (Security)](#7-الأمان-والصلاحيات)
8. [النشر والتوزيع (Deployment)](#8-النشر-والتوزيع)
9. [خطة التنفيذ المرحلية (Phased Execution)](#9-خطة-التنفيذ-المرحلية)
10. [التكاليف والمتطلبات (Costs)](#10-التكاليف-والمتطلبات)
11. [المخاطر والحلول البديلة (Risks)](#11-المخاطر-والحلول-البديلة)

---

## 1. نظرة عامة

### الوضع الحالي
- **الإطار**: Anvil Framework (Python full-stack)
- **عدد الشاشات**: 19 شاشة
- **عدد الـ API endpoints**: ~170+ callable function
- **جداول قاعدة البيانات**: 27 جدول
- **اللغات**: عربي + إنجليزي (RTL support)
- **المصادقة**: OTP (Email/SMS/WhatsApp) + TOTP (Authenticator App)
- **المحاسبة**: نظام قيد مزدوج كامل (Double-entry accounting)

### الهدف
تحويل النظام إلى تطبيق مستقل يعمل على:
- ✅ Windows (exe)
- ✅ macOS (dmg)
- ✅ Android (APK - بدون Play Store)
- ✅ iOS (IPA - بدون App Store)
- ✅ سيرفر مركزي واحد لكل البيانات
- ✅ عمل متزامن من أكثر من جهاز
- ✅ استخدام داخلي للشركة فقط

### التقنيات المختارة

| المكون | التقنية | السبب |
|--------|---------|-------|
| **Mobile App** | Flutter (Dart) | كود واحد لـ Android + iOS + Desktop |
| **Desktop App** | Flutter Desktop (Windows/macOS) | نفس الكود بدون Electron overhead |
| **Backend API** | FastAPI (Python) | سريع، Python (نفس لغة الكود الحالي)، async |
| **Database** | PostgreSQL | مجاني، يتحمل ضغط، دعم JSON |
| **ORM** | SQLAlchemy 2.0 + Alembic | مرونة عالية + migrations |
| **Auth** | JWT + pyotp | Stateless tokens + TOTP |
| **Caching** | Redis (اختياري) | تسريع الـ cache |
| **File Storage** | Local + Google Drive API | نسخ احتياطية |
| **PDF** | WeasyPrint أو ReportLab | توليد PDF في السيرفر |
| **Excel** | openpyxl | تصدير Excel |

---

## 2. الهندسة المعمارية

### الرسم العام
```
┌─────────────────────────────────────────────────────┐
│                    الأجهزة (Clients)                  │
│                                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ Windows  │  │ Android  │  │  macOS   │           │
│  │ Flutter  │  │ Flutter  │  │ Flutter  │           │
│  │ Desktop  │  │  Mobile  │  │ Desktop  │           │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘           │
│       │              │              │                 │
│       └──────────────┼──────────────┘                 │
│                      │                                │
│              HTTPS / REST API                         │
│                      │                                │
│       ┌──────────────┴──────────────┐                │
│       │     FastAPI Backend         │                │
│       │     (Python 3.11+)          │                │
│       │                             │                │
│       │  ┌─────────┐ ┌──────────┐  │                │
│       │  │  Auth   │ │ Business │  │                │
│       │  │ Module  │ │  Logic   │  │                │
│       │  └────┬────┘ └────┬─────┘  │                │
│       │       │            │        │                │
│       │  ┌────┴────────────┴─────┐  │                │
│       │  │    SQLAlchemy ORM     │  │                │
│       │  └───────────┬───────────┘  │                │
│       └──────────────┼──────────────┘                │
│                      │                                │
│       ┌──────────────┴──────────────┐                │
│       │      PostgreSQL 16          │                │
│       │      (27 Tables)            │                │
│       └─────────────────────────────┘                │
└─────────────────────────────────────────────────────┘
```

### هيكل المشروع
```
helwan-plast/
├── backend/                        # FastAPI Backend
│   ├── app/
│   │   ├── main.py                # FastAPI app entry
│   │   ├── config.py              # Settings & environment
│   │   ├── database.py            # DB connection & session
│   │   │
│   │   ├── models/                # SQLAlchemy Models (27 tables)
│   │   │   ├── user.py
│   │   │   ├── session.py
│   │   │   ├── client.py
│   │   │   ├── quotation.py
│   │   │   ├── contract.py
│   │   │   ├── accounting.py
│   │   │   ├── notification.py
│   │   │   └── ...
│   │   │
│   │   ├── schemas/               # Pydantic Request/Response
│   │   │   ├── auth.py
│   │   │   ├── client.py
│   │   │   ├── quotation.py
│   │   │   └── ...
│   │   │
│   │   ├── routers/               # API Endpoints
│   │   │   ├── auth.py            # 14 endpoints
│   │   │   ├── users.py           # 11 endpoints
│   │   │   ├── clients.py         # 10 endpoints
│   │   │   ├── quotations.py      # 13 endpoints
│   │   │   ├── contracts.py       # 11 endpoints
│   │   │   ├── calculator.py      # 9 endpoints
│   │   │   ├── accounting.py      # 17 endpoints
│   │   │   ├── payments.py        # 10 endpoints
│   │   │   ├── inventory.py       # 9 endpoints
│   │   │   ├── suppliers.py       # 7 endpoints
│   │   │   ├── purchase_invoices.py # 10 endpoints
│   │   │   ├── followups.py       # 6 endpoints
│   │   │   ├── notifications.py   # 7 endpoints
│   │   │   ├── settings.py        # 14 endpoints
│   │   │   ├── audit.py           # 3 endpoints
│   │   │   ├── import_export.py   # 8 endpoints
│   │   │   └── backup.py          # 7 endpoints
│   │   │
│   │   ├── services/              # Business Logic
│   │   │   ├── auth_service.py
│   │   │   ├── otp_service.py
│   │   │   ├── totp_service.py
│   │   │   ├── quotation_service.py
│   │   │   ├── calculator_engine.py
│   │   │   ├── accounting_service.py
│   │   │   ├── notification_service.py
│   │   │   ├── pdf_service.py
│   │   │   └── backup_service.py
│   │   │
│   │   ├── middleware/            # Middleware
│   │   │   ├── auth_middleware.py
│   │   │   ├── rate_limiter.py
│   │   │   └── audit_logger.py
│   │   │
│   │   └── utils/                 # Utilities
│   │       ├── password.py
│   │       ├── numbering.py
│   │       └── email.py
│   │
│   ├── alembic/                   # DB Migrations
│   ├── tests/                     # Backend Tests
│   ├── requirements.txt
│   └── Dockerfile
│
├── flutter_app/                   # Flutter App (Mobile + Desktop)
│   ├── lib/
│   │   ├── main.dart
│   │   ├── app.dart
│   │   │
│   │   ├── config/
│   │   │   ├── routes.dart
│   │   │   ├── theme.dart
│   │   │   └── constants.dart
│   │   │
│   │   ├── l10n/                  # Translations (EN/AR)
│   │   │   ├── app_en.arb
│   │   │   └── app_ar.arb
│   │   │
│   │   ├── models/                # Data Models
│   │   │   ├── user.dart
│   │   │   ├── client.dart
│   │   │   ├── quotation.dart
│   │   │   ├── contract.dart
│   │   │   └── ...
│   │   │
│   │   ├── services/              # API Client
│   │   │   ├── api_client.dart
│   │   │   ├── auth_service.dart
│   │   │   ├── quotation_service.dart
│   │   │   └── ...
│   │   │
│   │   ├── providers/             # State Management (Riverpod)
│   │   │   ├── auth_provider.dart
│   │   │   ├── calculator_provider.dart
│   │   │   └── ...
│   │   │
│   │   ├── screens/               # 19 Screens
│   │   │   ├── login/
│   │   │   ├── launcher/
│   │   │   ├── calculator/
│   │   │   ├── quotation_print/
│   │   │   ├── contract/
│   │   │   ├── database/
│   │   │   ├── clients/
│   │   │   ├── client_detail/
│   │   │   ├── payments/
│   │   │   ├── followups/
│   │   │   ├── admin/
│   │   │   ├── accounting/
│   │   │   ├── inventory/
│   │   │   ├── suppliers/
│   │   │   ├── purchase_invoices/
│   │   │   └── data_import/
│   │   │
│   │   └── widgets/               # Reusable Components
│   │       ├── search_bar.dart
│   │       ├── data_table.dart
│   │       ├── pagination.dart
│   │       ├── notification_bell.dart
│   │       ├── loading_overlay.dart
│   │       └── language_switcher.dart
│   │
│   ├── android/
│   ├── ios/
│   ├── windows/
│   ├── macos/
│   └── pubspec.yaml
│
├── docker-compose.yml             # PostgreSQL + FastAPI
└── README.md
```

---

## 3. قاعدة البيانات

### خريطة التحويل: Anvil Tables → PostgreSQL

#### 3.1 جداول المصادقة والأمان (Auth & Security)

**users**
```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(512) NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    phone           VARCHAR(50),
    role            VARCHAR(20) NOT NULL DEFAULT 'viewer',  -- admin|manager|sales|viewer
    is_active       BOOLEAN DEFAULT TRUE,
    is_approved     BOOLEAN DEFAULT FALSE,
    email_verified  BOOLEAN DEFAULT FALSE,
    otp_method      VARCHAR(20) DEFAULT 'email',  -- email|sms|whatsapp
    totp_secret     VARCHAR(255),
    totp_backup_codes TEXT,  -- JSON array of hashed codes
    login_attempts  INTEGER DEFAULT 0,
    locked_until    TIMESTAMP,
    custom_permissions JSONB,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW(),
    created_by      VARCHAR(255),
    updated_by      VARCHAR(255)
);
```

**sessions**
```sql
CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash      VARCHAR(128) NOT NULL UNIQUE,
    user_id         UUID REFERENCES users(id),
    user_email      VARCHAR(255),
    user_role       VARCHAR(20),
    ip_address      VARCHAR(45),
    user_agent      TEXT,
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    expires_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_sessions_token ON sessions(token_hash);
CREATE INDEX idx_sessions_user ON sessions(user_id);
```

**otp_codes**
```sql
CREATE TABLE otp_codes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_email      VARCHAR(255) NOT NULL,
    code_hash       VARCHAR(128) NOT NULL,
    purpose         VARCHAR(30) NOT NULL,  -- verification|2fa|password_reset|password_change
    is_used         BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    expires_at      TIMESTAMP NOT NULL
);
CREATE INDEX idx_otp_email ON otp_codes(user_email, purpose);
```

**password_history**
```sql
CREATE TABLE password_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_email      VARCHAR(255) NOT NULL,
    password_hash   VARCHAR(512) NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW()
);
```

**rate_limits**
```sql
CREATE TABLE rate_limits (
    id              SERIAL PRIMARY KEY,
    ip_address      VARCHAR(45) NOT NULL,
    endpoint        VARCHAR(100) NOT NULL,
    request_count   INTEGER DEFAULT 1,
    window_start    TIMESTAMP DEFAULT NOW(),
    blocked_until   TIMESTAMP,
    UNIQUE(ip_address, endpoint)
);
```

**pending_passwords**
```sql
CREATE TABLE pending_passwords (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) NOT NULL,
    password_hash   VARCHAR(512) NOT NULL,
    expires_at      TIMESTAMP NOT NULL
);
```

#### 3.2 جداول العملاء والعروض (Clients & Quotations)

**clients**
```sql
CREATE TABLE clients (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_code     VARCHAR(20) UNIQUE NOT NULL,  -- e.g. "C-0001"
    date            DATE,
    client_name     VARCHAR(255),
    company         VARCHAR(255),
    phone           VARCHAR(50),
    country         VARCHAR(100),
    address         TEXT,
    email           VARCHAR(255),
    sales_rep       VARCHAR(255),
    source          VARCHAR(100),
    notes_json      JSONB DEFAULT '[]',
    tags_json       JSONB DEFAULT '[]',
    is_deleted      BOOLEAN DEFAULT FALSE,
    deleted_at      TIMESTAMP,
    deleted_by      VARCHAR(255),
    created_by      VARCHAR(255),
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_by      VARCHAR(255),
    updated_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_clients_code ON clients(client_code);
CREATE INDEX idx_clients_phone ON clients(phone);
CREATE INDEX idx_clients_deleted ON clients(is_deleted);
```

**quotations**
```sql
CREATE TABLE quotations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quotation_number    VARCHAR(20) UNIQUE NOT NULL,  -- e.g. "Q-0001"
    client_code         VARCHAR(20) REFERENCES clients(client_code),
    date                DATE,
    client_name         VARCHAR(255),
    company             VARCHAR(255),
    phone               VARCHAR(50),

    -- Machine specifications
    model               VARCHAR(100),
    machine_type        VARCHAR(100),
    number_of_colors    INTEGER,
    machine_width       VARCHAR(50),
    material            VARCHAR(100),
    winder              VARCHAR(100),

    -- Options (booleans)
    video_inspection    BOOLEAN DEFAULT FALSE,
    plc                 BOOLEAN DEFAULT FALSE,
    slitter             BOOLEAN DEFAULT FALSE,
    pneumatic_unwind    BOOLEAN DEFAULT FALSE,
    hydraulic_station_unwind BOOLEAN DEFAULT FALSE,
    pneumatic_rewind    BOOLEAN DEFAULT FALSE,
    surface_rewind      BOOLEAN DEFAULT FALSE,

    -- Pricing
    given_price         DECIMAL(15,2),
    agreed_price        DECIMAL(15,2),
    standard_machine_fob DECIMAL(15,2),
    machine_fob_with_cylinders DECIMAL(15,2),
    fob_overseas        DECIMAL(15,2),
    exchange_rate       DECIMAL(10,4),
    in_stock            BOOLEAN DEFAULT FALSE,
    new_order           BOOLEAN DEFAULT TRUE,
    pricing_mode        VARCHAR(50),
    overseas_client     BOOLEAN DEFAULT FALSE,

    -- Cylinder data (JSON array, up to 12 entries)
    cylinders_data      JSONB DEFAULT '[]',
    -- Each entry: {size_cm, count, cost}

    -- Follow-up
    follow_up_date      DATE,
    follow_up_status    VARCHAR(20),  -- pending|completed

    -- Soft delete
    is_deleted          BOOLEAN DEFAULT FALSE,
    deleted_at          TIMESTAMP,
    deleted_by          VARCHAR(255),

    created_by          VARCHAR(255),
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_by          VARCHAR(255),
    updated_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_quotations_number ON quotations(quotation_number);
CREATE INDEX idx_quotations_client ON quotations(client_code);
CREATE INDEX idx_quotations_deleted ON quotations(is_deleted);
CREATE INDEX idx_quotations_followup ON quotations(follow_up_date, follow_up_status);
```

**contracts**
```sql
CREATE TABLE contracts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    serial_number       VARCHAR(30) UNIQUE NOT NULL,  -- e.g. "HP-2026-001"
    quotation_number    VARCHAR(20) REFERENCES quotations(quotation_number),
    contract_date       DATE,
    client_code         VARCHAR(20) REFERENCES clients(client_code),
    fob_cost_usd        DECIMAL(15,2),
    cylinder_cost_usd   DECIMAL(15,2),
    payment_schedule    JSONB DEFAULT '[]',
    -- Each entry: {date, amount, method, status}
    payment_status      VARCHAR(20) DEFAULT 'pending',  -- pending|partial|paid
    sales_rep_email     VARCHAR(255),
    notes               TEXT,
    delivery_date       DATE,

    is_deleted          BOOLEAN DEFAULT FALSE,
    deleted_at          TIMESTAMP,
    deleted_by          VARCHAR(255),
    created_by          VARCHAR(255),
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_by          VARCHAR(255),
    updated_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_contracts_serial ON contracts(serial_number);
CREATE INDEX idx_contracts_quotation ON contracts(quotation_number);
```

**contract_lifecycle_history**
```sql
CREATE TABLE contract_lifecycle_history (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contract_id     UUID REFERENCES contracts(id),
    event_type      VARCHAR(50),
    event_data      JSONB,
    created_by      VARCHAR(255),
    created_at      TIMESTAMP DEFAULT NOW()
);
```

#### 3.3 جداول المحاسبة (Accounting)

**chart_of_accounts**
```sql
CREATE TABLE chart_of_accounts (
    code            VARCHAR(10) PRIMARY KEY,
    name_en         VARCHAR(255) NOT NULL,
    name_ar         VARCHAR(255),
    account_type    VARCHAR(20) NOT NULL,  -- asset|liability|equity|revenue|expense
    parent_code     VARCHAR(10) REFERENCES chart_of_accounts(code),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW()
);
```

**ledger** (دفتر الأستاذ - غير قابل للتعديل)
```sql
CREATE TABLE ledger (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id  VARCHAR(50) NOT NULL,
    date            DATE NOT NULL,
    account_code    VARCHAR(10) REFERENCES chart_of_accounts(code),
    debit           DECIMAL(15,2) DEFAULT 0,
    credit          DECIMAL(15,2) DEFAULT 0,
    description     TEXT,
    reference_type  VARCHAR(50),  -- contract|purchase_invoice|expense|opening|closing
    reference_id    VARCHAR(50),
    created_by      VARCHAR(255),
    created_at      TIMESTAMP DEFAULT NOW()
    -- NO UPDATE allowed (immutable ledger)
);
CREATE INDEX idx_ledger_account ON ledger(account_code);
CREATE INDEX idx_ledger_date ON ledger(date);
CREATE INDEX idx_ledger_ref ON ledger(reference_type, reference_id);
CREATE INDEX idx_ledger_txn ON ledger(transaction_id);
```

**suppliers**
```sql
CREATE TABLE suppliers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_name   VARCHAR(255) NOT NULL,
    bank_account    VARCHAR(100),
    bank_name       VARCHAR(100),
    address         TEXT,
    contact_person  VARCHAR(255),
    phone           VARCHAR(50),
    email           VARCHAR(255),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

**purchase_invoices**
```sql
CREATE TABLE purchase_invoices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number  VARCHAR(30) UNIQUE NOT NULL,
    supplier_id     UUID REFERENCES suppliers(id),
    invoice_date    DATE,
    due_date        DATE,
    currency_code   VARCHAR(3) DEFAULT 'USD',
    exchange_rate   DECIMAL(10,4),
    subtotal        DECIMAL(15,2),
    tax_amount      DECIMAL(15,2) DEFAULT 0,
    total           DECIMAL(15,2),
    total_egp       DECIMAL(15,2),
    paid_amount     DECIMAL(15,2) DEFAULT 0,
    status          VARCHAR(20) DEFAULT 'draft',  -- draft|posted|paid
    inventory_moved BOOLEAN DEFAULT FALSE,
    is_posted       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

**import_costs**
```sql
CREATE TABLE import_costs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_invoice_id UUID REFERENCES purchase_invoices(id),
    cost_type           VARCHAR(50) NOT NULL,
    amount              DECIMAL(15,2),
    original_currency   VARCHAR(3),
    exchange_rate       DECIMAL(10,4),
    amount_egp          DECIMAL(15,2),
    cost_date           DATE,
    description         TEXT,
    paid_amount         DECIMAL(15,2) DEFAULT 0,
    status              VARCHAR(20) DEFAULT 'unpaid',
    created_at          TIMESTAMP DEFAULT NOW()
);
```

**inventory**
```sql
CREATE TABLE inventory (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchase_invoice_id UUID REFERENCES purchase_invoices(id),
    item_code           VARCHAR(50),
    quantity_received   INTEGER,
    unit_cost_egp       DECIMAL(15,2),
    total_cost_egp      DECIMAL(15,2),
    import_costs_egp    DECIMAL(15,2) DEFAULT 0,
    status              VARCHAR(20) DEFAULT 'in_stock',  -- in_stock|reserved|sold
    contract_id         UUID REFERENCES contracts(id),
    created_at          TIMESTAMP DEFAULT NOW()
);
```

**expenses**
```sql
CREATE TABLE expenses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date            DATE NOT NULL,
    category        VARCHAR(100),
    amount          DECIMAL(15,2),
    currency_code   VARCHAR(3) DEFAULT 'EGP',
    exchange_rate   DECIMAL(10,4) DEFAULT 1,
    amount_egp      DECIMAL(15,2),
    description     TEXT,
    created_by      VARCHAR(255),
    created_at      TIMESTAMP DEFAULT NOW()
);
```

**currency_exchange_rates**
```sql
CREATE TABLE currency_exchange_rates (
    id              SERIAL PRIMARY KEY,
    currency_code   VARCHAR(3) NOT NULL,
    rate_to_egp     DECIMAL(10,4) NOT NULL,
    last_updated    TIMESTAMP DEFAULT NOW(),
    UNIQUE(currency_code)
);
```

**accounting_period_locks**
```sql
CREATE TABLE accounting_period_locks (
    id              SERIAL PRIMARY KEY,
    year            INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    locked          BOOLEAN DEFAULT FALSE,
    locked_at       TIMESTAMP,
    locked_by       VARCHAR(255),
    UNIQUE(year, month)
);
```

**opening_balances**
```sql
CREATE TABLE opening_balances (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_code    VARCHAR(10) REFERENCES chart_of_accounts(code),
    as_of_date      DATE,
    debit           DECIMAL(15,2) DEFAULT 0,
    credit          DECIMAL(15,2) DEFAULT 0,
    created_by      VARCHAR(255),
    created_at      TIMESTAMP DEFAULT NOW()
);
```

#### 3.4 جداول النظام (System)

**settings**
```sql
CREATE TABLE settings (
    setting_key     VARCHAR(100) PRIMARY KEY,
    setting_value   TEXT,
    setting_type    VARCHAR(20) DEFAULT 'string',  -- string|json|number|boolean
    description     TEXT,
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

**machine_specs**
```sql
CREATE TABLE machine_specs (
    id              SERIAL PRIMARY KEY,
    model_name      VARCHAR(100) NOT NULL,
    spec_key        VARCHAR(100) NOT NULL,
    spec_value      TEXT,
    created_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(model_name, spec_key)
);
```

**counters** (ترقيم ذري)
```sql
CREATE TABLE counters (
    counter_key     VARCHAR(50) PRIMARY KEY,
    next_value      INTEGER NOT NULL DEFAULT 1
);
-- Advisory locks في PostgreSQL بدل Anvil transactions
```

**audit_log**
```sql
CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp       TIMESTAMP DEFAULT NOW(),
    user_email      VARCHAR(255),
    user_name       VARCHAR(255),
    action          VARCHAR(50) NOT NULL,
    table_name      VARCHAR(100),
    record_id       VARCHAR(100),
    old_data        JSONB,
    new_data        JSONB,
    action_description TEXT,
    ip_address      VARCHAR(45)
);
CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX idx_audit_user ON audit_log(user_email);
CREATE INDEX idx_audit_action ON audit_log(action);
```

**notifications**
```sql
CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_email      VARCHAR(255) NOT NULL,
    type            VARCHAR(50) NOT NULL,
    payload         JSONB,
    created_at      TIMESTAMP DEFAULT NOW(),
    read_at         TIMESTAMP
);
CREATE INDEX idx_notif_user ON notifications(user_email, read_at);
```

**follow_up_reminders** (جدول مستقل بدل الحقل في quotations)
```sql
CREATE TABLE follow_up_reminders (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    quotation_number VARCHAR(20) REFERENCES quotations(quotation_number),
    follow_up_date  DATE NOT NULL,
    status          VARCHAR(20) DEFAULT 'pending',  -- pending|completed|snoozed
    notes           TEXT,
    created_by      VARCHAR(255),
    created_at      TIMESTAMP DEFAULT NOW(),
    completed_at    TIMESTAMP,
    snoozed_to      DATE
);
CREATE INDEX idx_followup_date ON follow_up_reminders(follow_up_date, status);
```

**client_timeline**
```sql
CREATE TABLE client_timeline (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_code     VARCHAR(20) REFERENCES clients(client_code),
    event_type      VARCHAR(50),  -- quotation|contract|note|followup
    event_data      JSONB,
    created_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_timeline_client ON client_timeline(client_code);
```

**scheduled_backups**
```sql
CREATE TABLE scheduled_backups (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    backup_date     TIMESTAMP DEFAULT NOW(),
    file_name       VARCHAR(255),
    file_size       BIGINT,
    status          VARCHAR(20),  -- completed|failed
    created_at      TIMESTAMP DEFAULT NOW()
);
```

---

## 4. الـ API Endpoints

### 4.1 المصادقة (Auth) — `/api/v1/auth/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| POST | `/login` | `login_user` | تسجيل الدخول |
| POST | `/register` | `register_user` | تسجيل مستخدم جديد |
| POST | `/logout` | `logout_user` | تسجيل الخروج |
| POST | `/verify-login-otp` | `verify_login_otp` | التحقق من OTP تسجيل الدخول |
| POST | `/resend-login-otp` | `resend_login_otp` | إعادة إرسال OTP تسجيل الدخول |
| POST | `/verify-registration-otp` | `verify_registration_otp` | تفعيل الحساب |
| POST | `/resend-verification-otp` | `resend_verification_otp` | إعادة إرسال تفعيل |
| POST | `/request-password-reset` | `request_password_reset` | طلب استعادة كلمة المرور |
| POST | `/verify-password-reset-otp` | `verify_password_reset_otp` | التحقق من OTP الاستعادة |
| POST | `/complete-password-reset` | `complete_password_reset` | إتمام استعادة كلمة المرور |
| POST | `/change-password` | `change_own_password` | تغيير كلمة المرور |
| GET | `/validate-token` | `validate_token` | فحص صلاحية التوكن |
| GET | `/check-admin-exists` | `check_admin_exists` | هل يوجد أدمن؟ |
| POST | `/setup-admin` | `setup_initial_admin` | إعداد الأدمن الأولي |

### 4.2 TOTP — `/api/v1/auth/totp/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| POST | `/setup-start` | `setup_totp_start` | بدء تفعيل المصادقة الثنائية |
| POST | `/setup-confirm` | `setup_totp_confirm` | تأكيد التفعيل بالكود |
| POST | `/disable` | `disable_totp` | إلغاء المصادقة الثنائية |
| GET | `/status` | `user_has_totp_enabled` | حالة المصادقة |
| POST | `/verify-backup` | `verify_backup_code` | استخدام كود احتياطي |

### 4.3 إدارة المستخدمين (Users) — `/api/v1/users/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| GET | `/pending` | `get_pending_users` | المستخدمين المعلقين |
| GET | `/` | `get_all_users` | كل المستخدمين |
| GET | `/active-dropdown` | `get_active_users_for_dropdown` | قائمة للاختيار |
| POST | `/{id}/approve` | `approve_user` | الموافقة على مستخدم |
| POST | `/{id}/reject` | `reject_user` | رفض مستخدم |
| PUT | `/{id}/role` | `update_user_role` | تغيير الصلاحية |
| PUT | `/{id}/otp-method` | `update_user_otp_method` | تغيير طريقة OTP |
| POST | `/{id}/reset-password` | `reset_user_password` | إعادة تعيين كلمة المرور |
| POST | `/{id}/toggle-active` | `toggle_user_active` | تعطيل/تفعيل الحساب |
| DELETE | `/{id}` | (permanent delete) | حذف نهائي |
| POST | `/clear-rate-limit` | `clear_my_rate_limit` | مسح حد الطلبات |

### 4.4 العملاء (Clients) — `/api/v1/clients/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| GET | `/` | `get_all_clients` | قائمة العملاء (paginated) |
| GET | `/{code}` | (client detail) | تفاصيل عميل |
| GET | `/{code}/timeline` | `get_client_timeline` | تاريخ العميل |
| GET | `/search-by-phone` | `find_client_by_phone` | بحث بالهاتف |
| GET | `/next-code` | `peek_next_client_code` | الكود التالي |
| DELETE | `/{code}` | `soft_delete_client` | حذف (soft) |
| POST | `/{code}/restore` | `restore_client` | استرجاع |
| POST | `/{code}/notes` | `add_client_note` | إضافة ملاحظة |
| DELETE | `/{code}/notes/{note_id}` | `delete_client_note` | حذف ملاحظة |
| PUT | `/{code}/tags` | `update_client_tags` | تحديث التاجات |
| GET | `/export` | `export_clients_data` | تصدير CSV |

### 4.5 العروض (Quotations) — `/api/v1/quotations/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| GET | `/` | `get_all_quotations` | كل العروض (paginated) |
| GET | `/list` | `get_quotations_list` | قائمة مبسطة |
| GET | `/available-for-contract` | `get_quotations_list_without_contract` | عروض بدون عقد |
| GET | `/next-number` | `peek_next_quotation_number` | الرقم التالي |
| POST | `/` | `save_quotation` | حفظ عرض جديد |
| GET | `/{number}` | (quotation detail) | تفاصيل عرض |
| GET | `/{number}/pdf-data` | `get_quotation_pdf_data` | بيانات PDF |
| GET | `/{number}/excel` | `export_quotation_excel` | تصدير Excel |
| DELETE | `/{number}` | `soft_delete_quotation` | حذف (soft) |
| POST | `/{number}/restore` | `restore_quotation` | استرجاع |
| GET | `/export` | `export_quotations_data` | تصدير CSV |
| POST | `/resync-counters` | `resync_counters` | مزامنة العدادات |

### 4.6 العقود (Contracts) — `/api/v1/contracts/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| GET | `/` | `get_contracts_list` | كل العقود |
| GET | `/simple` | `get_contracts_list_simple` | قائمة مبسطة |
| GET | `/next-serial` | `get_next_contract_serial_preview` | الرقم التسلسلي التالي |
| POST | `/` | `save_contract` | إنشاء عقد |
| GET | `/{serial}` | `get_contract` | تفاصيل عقد |
| PUT | `/{serial}` | `update_contract` | تعديل عقد |
| DELETE | `/{serial}` | `delete_contract` | حذف عقد |
| GET | `/{serial}/payable-status` | `get_contract_payable_status` | حالة المدفوعات |
| POST | `/{serial}/purchase` | `create_contract_purchase` | إنشاء فاتورة شراء |

### 4.7 الحاسبة (Calculator) — `/api/v1/calculator/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| GET | `/settings` | `get_calculator_settings` | كل إعدادات الحاسبة |
| GET | `/machine-config` | `get_all_machine_specs` | مواصفات الماكينات |
| GET | `/machine-prices` | `get_machine_prices` | أسعار الماكينات |
| PUT | `/machine-prices` | `save_machine_prices` | تحديث أسعار الماكينات |
| GET | `/machine-specs` | `get_all_machine_specs` | مواصفات المحركات |
| PUT | `/machine-specs` | `save_machine_specs` | تحديث المواصفات |
| GET | `/template-settings` | `get_all_template_settings` | إعدادات القوالب |

### 4.8 المتابعات (Follow-ups) — `/api/v1/followups/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| GET | `/dashboard` | `get_followup_dashboard` | لوحة المتابعات |
| POST | `/` | `set_followup` | إنشاء متابعة |
| POST | `/{id}/snooze` | `snooze_followup` | تأجيل |
| POST | `/{id}/complete` | `complete_followup` | إتمام |
| GET | `/check-overdue` | `check_overdue_followups` | فحص المتأخرة |

### 4.9 المحاسبة (Accounting) — `/api/v1/accounting/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| GET | `/chart-of-accounts` | `get_chart_of_accounts` | دليل الحسابات |
| POST | `/accounts` | `add_account` | إضافة حساب |
| POST | `/seed-accounts` | `seed_accounts` | تهيئة الحسابات الافتراضية |
| POST | `/journal-entry` | `create_journal_entry` | إدخال قيد |
| GET | `/ledger` | `get_ledger_entries` | دفتر الأستاذ |
| GET | `/balance/{code}` | `get_account_balance` | رصيد حساب |
| POST | `/treasury` | `create_treasury_transaction` | حركة خزينة |
| GET | `/trial-balance` | `get_trial_balance` | ميزان المراجعة |
| GET | `/income-statement` | `get_income_statement` | قائمة الدخل |
| GET | `/balance-sheet` | `get_balance_sheet` | المركز المالي |
| GET | `/contract-profitability` | `get_contract_profitability` | ربحية العقود |
| POST | `/period/lock` | `lock_period` | قفل فترة |
| POST | `/period/unlock` | `unlock_period` | فتح فترة |
| POST | `/period/close` | `close_period` | إغلاق فترة |
| GET | `/period-locks` | `get_period_locks` | حالة الفترات |
| POST | `/year-end-close` | `close_financial_year` | إغلاق سنة |
| POST | `/year-end-post` | `post_year_end_closing` | ترحيل الإغلاق |

### 4.10 المدفوعات (Payments) — `/api/v1/payments/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| GET | `/dashboard` | `get_payment_dashboard_data` | لوحة المدفوعات |
| PUT | `/{id}/status` | `update_payment_status` | تحديث حالة دفعة |
| GET | `/customer-summary` | `get_customer_summary` | ملخص حسابات العملاء |
| GET | `/supplier-summary` | `get_supplier_summary` | ملخص حسابات الموردين |
| GET | `/opening-balances` | `get_opening_balances` | الأرصدة الافتتاحية |
| POST | `/opening-balances` | `set_opening_balance` | تعيين رصيد افتتاحي |
| POST | `/supplier-payment` | `record_supplier_payment` | تسجيل دفعة لمورد |
| POST | `/import-cost-payment` | `pay_import_cost` | دفع مصاريف استيراد |

### 4.11 المخزون (Inventory) — `/api/v1/inventory/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| GET | `/` | `get_inventory` | قائمة المخزون |
| POST | `/` | `add_inventory_item` | إضافة صنف |
| PUT | `/{id}` | `update_inventory_item` | تعديل صنف |
| DELETE | `/{id}` | `delete_inventory_item` | حذف صنف |
| POST | `/{id}/receive` | `receive_inventory` | استلام |
| POST | `/{id}/sell` | `sell_inventory` | بيع |
| POST | `/{id}/link-contract` | `link_inventory_to_contract` | ربط بعقد |
| GET | `/for-contract/{contract_id}` | `get_available_inventory_for_contract` | متاح لعقد |
| GET | `/export` | `export_inventory_data` | تصدير |

### 4.12 الموردين (Suppliers) — `/api/v1/suppliers/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| GET | `/` | `get_suppliers` | قائمة الموردين |
| GET | `/simple` | `get_suppliers_list_simple` | قائمة مبسطة |
| POST | `/` | `add_supplier` | إضافة مورد |
| PUT | `/{id}` | `update_supplier` | تعديل مورد |
| DELETE | `/{id}` | `delete_supplier` | حذف مورد |
| GET | `/{id}/remaining` | `get_supplier_remaining_egp` | المبلغ المتبقي |

### 4.13 فواتير الشراء (Purchase Invoices) — `/api/v1/purchase-invoices/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| GET | `/` | `get_purchase_invoices` | قائمة الفواتير |
| POST | `/` | `create_purchase_invoice` | إنشاء فاتورة |
| PUT | `/{id}` | `update_purchase_invoice` | تعديل |
| DELETE | `/{id}` | `delete_purchase_invoice` | حذف |
| POST | `/{id}/post` | `post_purchase_invoice` | ترحيل للدفتر |
| POST | `/{id}/move-to-inventory` | `move_purchase_to_inventory` | نقل للمخزون |
| GET | `/{id}/import-costs` | `get_import_costs` | مصاريف الاستيراد |
| POST | `/{id}/import-costs` | `add_import_cost` | إضافة مصروف |
| GET | `/{id}/pdf-data` | `get_invoice_details` | بيانات PDF |

### 4.14 الإشعارات (Notifications) — `/api/v1/notifications/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| GET | `/` | `get_user_notifications` | إشعاراتي |
| GET | `/unread-count` | `get_unread_notification_count` | عدد غير المقروءة |
| PUT | `/{id}/read` | `mark_notification_read` | تعليم كمقروء |
| DELETE | `/{id}` | `delete_notification` | حذف إشعار |
| DELETE | `/all` | `delete_all_my_notifications` | حذف الكل |
| GET | `/admin/all` | `get_all_notifications_admin` | كل الإشعارات (أدمن) |

### 4.15 الإعدادات (Settings) — `/api/v1/settings/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| GET | `/` | `get_all_settings` | كل الإعدادات |
| GET | `/{key}` | `get_setting_value` | قيمة إعداد |
| PUT | `/{key}` | `update_setting` | تحديث إعداد |
| GET | `/exchange-rates` | `get_exchange_rates` | أسعار الصرف |
| POST | `/exchange-rates` | `set_exchange_rate` | تعيين سعر صرف |
| DELETE | `/exchange-rates/{date}` | `delete_exchange_rate` | حذف سعر |
| POST | `/exchange-rates/fetch` | `fetch_exchange_rates_from_api` | جلب من API خارجي |
| GET | `/import-cost-types` | `get_import_cost_types` | أنواع المصاريف |
| POST | `/seed-cost-types` | `seed_import_cost_types` | تهيئة أنواع المصاريف |

### 4.16 سجل المراجعة (Audit) — `/api/v1/audit/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| GET | `/` | `get_audit_logs` | سجل المراجعة (paginated) |
| GET | `/export` | `export_audit_log` | تصدير CSV |

### 4.17 استيراد/تصدير (Import/Export) — `/api/v1/data/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| POST | `/import/clients` | `import_clients_data` | استيراد عملاء |
| POST | `/import/quotations` | `import_quotations_data` | استيراد عروض |
| GET | `/export/clients` | `export_clients_data` | تصدير عملاء |
| GET | `/export/quotations` | `export_quotations_data` | تصدير عروض |
| GET | `/export/contracts` | `export_contracts_data` | تصدير عقود |
| GET | `/export/inventory` | `export_inventory_data` | تصدير مخزون |

### 4.18 النسخ الاحتياطي (Backup) — `/api/v1/backup/`

| Method | Endpoint | Anvil Origin | Purpose |
|--------|----------|-------------|---------|
| POST | `/create` | `create_backup` | إنشاء نسخة |
| GET | `/list` | `list_drive_backups` | قائمة النسخ |
| POST | `/restore` | `restore_backup_from_drive` | استعادة من Drive |
| GET | `/scheduled` | `list_scheduled_backups` | النسخ المجدولة |

---

## 5. شاشات Flutter

### 5.1 خريطة الشاشات (19 شاشة)

| # | الشاشة | الملف | الوصف | الصلاحية |
|---|--------|-------|-------|----------|
| 1 | **Login** | `login_screen.dart` | تسجيل دخول + تسجيل + استعادة + OTP | عام |
| 2 | **Launcher** | `launcher_screen.dart` | القائمة الرئيسية | مسجل دخول |
| 3 | **Calculator** | `calculator_screen.dart` | حاسبة الأسعار | مسجل دخول |
| 4 | **Quotation Print** | `quotation_print_screen.dart` | طباعة عرض سعر | مسجل دخول |
| 5 | **Contract Print** | `contract_print_screen.dart` | إنشاء وطباعة عقد | مسجل دخول |
| 6 | **Contract Edit** | `contract_edit_screen.dart` | تعديل عقد | مسجل دخول |
| 7 | **Database** | `database_screen.dart` | قاعدة بيانات العروض | مسجل دخول |
| 8 | **Client List** | `client_list_screen.dart` | قائمة العملاء | مسجل دخول |
| 9 | **Client Detail** | `client_detail_screen.dart` | تفاصيل عميل + ملاحظات + تاريخ | مسجل دخول |
| 10 | **Payment Dashboard** | `payment_dashboard_screen.dart` | لوحة المدفوعات | مسجل دخول |
| 11 | **Follow-ups** | `followup_screen.dart` | لوحة المتابعات | مسجل دخول |
| 12 | **Admin Dashboard** | `admin_screen.dart` (8 tabs) | لوحة الأدمن | أدمن فقط |
| 13 | **Accountant** | `accountant_screen.dart` | التقارير المالية | أدمن فقط |
| 14 | **Inventory** | `inventory_screen.dart` | إدارة المخزون | أدمن فقط |
| 15 | **Customer Summary** | `customer_summary_screen.dart` | حسابات العملاء (AR) | أدمن فقط |
| 16 | **Supplier Summary** | `supplier_summary_screen.dart` | حسابات الموردين (AP) | أدمن فقط |
| 17 | **Suppliers** | `suppliers_screen.dart` | إدارة الموردين | أدمن فقط |
| 18 | **Purchase Invoices** | `purchase_invoices_screen.dart` | فواتير الشراء | أدمن فقط |
| 19 | **Data Import** | `data_import_screen.dart` | استيراد CSV | أدمن فقط |

### 5.2 المكونات المشتركة (Shared Widgets)

| المكون | الملف | الوصف |
|--------|-------|-------|
| **SearchBar** | `search_bar.dart` | بحث نصي مع زر مسح |
| **PaginatedTable** | `paginated_table.dart` | جدول بيانات مع ترقيم صفحات |
| **NotificationBell** | `notification_bell.dart` | جرس إشعارات مع dropdown |
| **LoadingOverlay** | `loading_overlay.dart` | شاشة تحميل (hand animation) |
| **LanguageSwitcher** | `language_switcher.dart` | تبديل EN/AR |
| **ConfirmDialog** | `confirm_dialog.dart` | نافذة تأكيد |
| **ToastNotification** | `toast.dart` | رسائل نجاح/خطأ |
| **DropdownOverlay** | `dropdown_overlay.dart` | قائمة اختيار مع بحث |
| **DatePicker** | `date_picker.dart` | اختيار تاريخ |
| **FormField** | `form_field.dart` | حقل إدخال موحد |
| **StatusBadge** | `status_badge.dart` | شارة حالة (ملون) |
| **StatsCard** | `stats_card.dart` | كارت إحصائيات |

### 5.3 State Management (Riverpod)

```dart
// Providers الرئيسية
authProvider          // حالة المستخدم + التوكن
calculatorProvider    // إعدادات الحاسبة + البيانات الحالية
quotationsProvider    // قائمة العروض + بحث + pagination
clientsProvider       // قائمة العملاء + بحث
contractsProvider     // قائمة العقود
paymentsProvider      // لوحة المدفوعات
followupsProvider     // المتابعات
notificationsProvider // الإشعارات + عدد غير المقروءة
settingsProvider      // الإعدادات العامة
accountingProvider    // التقارير المالية
inventoryProvider     // المخزون
suppliersProvider     // الموردين
localeProvider        // اللغة الحالية (EN/AR)
```

### 5.4 التصميم والثيم

```dart
// ألوان النظام (من standard-page.html الحالي)
primaryBlue:    #1976d2  // الأزرار الرئيسية
successGreen:   #4caf50  // نجاح
warningOrange:  #ff9800  // تحذير
dangerRed:      #f44336  // خطأ/حذف
infoPurple:     #9c27b0  // معلومات
background:     #f5f5f5  // خلفية
cardWhite:      #ffffff  // البطاقات

// الخطوط
arabicFont: 'Cairo' or 'Tajawal'  // للعربي
englishFont: 'Roboto'              // للإنجليزي
```

---

## 6. تطبيق سطح المكتب (Flutter Desktop)

### لماذا Flutter Desktop بدل Electron؟
| المعيار | Flutter Desktop | Electron |
|---------|----------------|----------|
| **حجم التطبيق** | ~20 MB | ~150 MB |
| **استهلاك الذاكرة** | ~50 MB | ~300 MB |
| **الأداء** | أصلي (native) | بطيء (Chromium) |
| **كود مشترك** | 100% مع Mobile | كود منفصل |
| **صعوبة التطوير** | واحدة | مضاعفة |

### التوزيع
- **Windows**: ملف `.exe` + مجلد (portable) أو MSIX installer
- **macOS**: ملف `.app` (unsigned - لاستخدام داخلي)

### خطوات البناء
```bash
# Windows
flutter build windows --release
# الناتج: build/windows/x64/runner/Release/

# macOS
flutter build macos --release
# الناتج: build/macos/Build/Products/Release/helwan_plast.app
```

---

## 7. الأمان والصلاحيات

### 7.1 نظام المصادقة

```
المصادقة الحالية (Anvil):
  Token → sessionStorage → validate_token() → sessions table

المصادقة الجديدة (FastAPI):
  JWT Access Token (15 min) + Refresh Token (30 days)
  → Authorization: Bearer <token>
  → Refresh when expired
  → Stored in Flutter secure_storage
```

### 7.2 JWT Structure
```json
{
  "sub": "user@email.com",
  "user_id": "uuid",
  "role": "admin",
  "permissions": ["all"],
  "exp": 1700000000,
  "iat": 1699999000
}
```

### 7.3 الأدوار والصلاحيات

| الدور | الصلاحيات |
|-------|----------|
| **admin** | كل شيء |
| **manager** | عرض، إنشاء، تعديل، تصدير، حذف ما أنشأه |
| **sales** | عرض، إنشاء، تعديل ما أنشأه |
| **viewer** | عرض فقط |

### 7.4 إجراءات أمنية مهمة

1. **PBKDF2** (100,000 iterations) لتخزين كلمات المرور
2. **Rate Limiting**: 15 طلب / 15 دقيقة لـ auth endpoints
3. **Session Max**: 5 جلسات متزامنة لكل مستخدم
4. **Account Lockout**: 5 محاولات خاطئة → قفل 30 دقيقة
5. **Password History**: منع إعادة استخدام آخر 5 كلمات مرور
6. **OTP Expiry**: 10 دقائق
7. **HTTPS**: إلزامي لكل الـ API calls
8. **Audit Trail**: تسجيل كل عملية CRUD

---

## 8. النشر والتوزيع

### 8.1 السيرفر (Backend)

**الخيار 1: VPS (مُوصى به)**
```
مقدم الخدمة: Hetzner أو DigitalOcean
المواصفات: 2 vCPU, 4 GB RAM, 80 GB SSD
التكلفة: ~$7-15/شهر
النظام: Ubuntu 22.04 LTS

المكونات:
├── Docker + Docker Compose
│   ├── FastAPI (Gunicorn + Uvicorn workers)
│   ├── PostgreSQL 16
│   ├── Redis (cache - اختياري)
│   └── Nginx (reverse proxy + SSL)
└── Certbot (Let's Encrypt SSL)
```

**الخيار 2: سيرفر داخلي (On-Premise)**
```
المتطلبات: أي جهاز كمبيوتر داخل الشبكة
المواصفات: 4 GB RAM, 50 GB مساحة
التكلفة: $0 (الكهرباء فقط)
الشرط: يجب أن يكون الجهاز شغال دائماً

المكونات: نفس Docker Compose
الوصول: عبر IP داخلي (192.168.x.x)
ملاحظة: لن يعمل خارج شبكة الشركة
```

### 8.2 التطبيقات

**Android (APK)**
```bash
flutter build apk --release
# الناتج: build/app/outputs/flutter-apk/app-release.apk
# التوزيع: إرسال APK عبر WhatsApp أو USB أو رابط تحميل داخلي
# الحجم: ~20-30 MB
```

**iOS (IPA)**
```
الخيار 1: Apple Enterprise Certificate ($299/سنة)
  → توزيع IPA مباشر على أجهزة الشركة

الخيار 2: TestFlight (مجاني مع Apple Developer $99/سنة)
  → يمكن إضافة 10,000 مستخدم
  → التطبيق يحتاج تجديد كل 90 يوم

الخيار 3: بدون iOS حالياً
  → استخدام Android فقط للموبايل
  → يمكن إضافة iOS لاحقاً
```

**Windows (exe)**
```bash
flutter build windows --release
# التوزيع: مجلد مضغوط أو NSIS installer
# الحجم: ~20 MB
# لا يحتاج توقيع لاستخدام داخلي
```

**macOS (app)**
```bash
flutter build macos --release
# التوزيع: ملف .app مباشر
# الحجم: ~25 MB
# ملاحظة: المستخدم يحتاج يعمل Right-click → Open أول مرة (unsigned)
```

### 8.3 بيئة التشغيل (Environment Variables)

```env
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/helwan_plast

# JWT
JWT_SECRET_KEY=<random-64-char-string>
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=15
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# Email (SMTP)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your@gmail.com
SMTP_PASSWORD=app-password

# Twilio (SMS/WhatsApp - اختياري)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
TWILIO_WHATSAPP_FROM=

# Admin
ADMIN_EMAIL=mohamedadelfouda@helwanplast.com
EMERGENCY_SECRET_KEY=<secret>

# Backup
BACKUP_ENCRYPTION_KEY=<fernet-key>
GOOGLE_DRIVE_CREDENTIALS=<path-to-credentials.json>
```

---

## 9. خطة التنفيذ المرحلية

### المرحلة 1: الأساس (3-4 أسابيع)
> **الهدف**: Backend يعمل + شاشة Login تعمل

| المهمة | الأيام | التفاصيل |
|--------|--------|----------|
| إعداد مشروع FastAPI | 2 | هيكل المشروع + Docker + PostgreSQL |
| نقل الـ Database Schema | 3 | 27 جدول + Alembic migrations |
| نقل بيانات Anvil الحالية | 2 | سكريبت تحويل من Anvil → PostgreSQL |
| Auth API (14 endpoints) | 4 | Login, Register, OTP, TOTP, JWT |
| Users API (11 endpoints) | 2 | CRUD + Approval workflow |
| إعداد مشروع Flutter | 2 | هيكل + packages + theme |
| شاشة Login (Flutter) | 3 | Login + Register + OTP + Reset |
| شاشة Launcher (Flutter) | 1 | القائمة الرئيسية |
| **اختبار شامل** | 2 | Integration testing |

**الناتج**: تطبيق يسجل دخول ويعرض القائمة الرئيسية

---

### المرحلة 2: العمليات الأساسية (4-5 أسابيع)
> **الهدف**: حاسبة + عروض + عقود

| المهمة | الأيام | التفاصيل |
|--------|--------|----------|
| Calculator API (9 endpoints) | 2 | Settings + Machine specs |
| Calculator Engine (Python) | 3 | نقل الـ pricing logic من JS → Python service |
| شاشة Calculator (Flutter) | 5 | كل الحقول + الحسابات الآنية |
| Quotations API (12 endpoints) | 3 | CRUD + Search + Export |
| شاشة Quotation Print (Flutter) | 3 | عرض + طباعة + PDF |
| Contracts API (11 endpoints) | 3 | CRUD + Payment schedule |
| شاشة Contract Print (Flutter) | 4 | إنشاء + تعديل + طباعة |
| شاشة Contract Edit (Flutter) | 2 | تعديل العقود |
| PDF Generation (WeasyPrint) | 3 | قوالب PDF عربي/إنجليزي |
| **اختبار شامل** | 3 | End-to-end testing |

**الناتج**: التطبيق يحسب أسعار، يحفظ عروض، ينشئ عقود

---

### المرحلة 3: العملاء والمتابعات (3 أسابيع)
> **الهدف**: إدارة عملاء كاملة + متابعات + مدفوعات

| المهمة | الأيام | التفاصيل |
|--------|--------|----------|
| Clients API (10 endpoints) | 2 | CRUD + Timeline + Notes + Tags |
| شاشة Client List (Flutter) | 2 | قائمة + بحث + pagination |
| شاشة Client Detail (Flutter) | 3 | تفاصيل + timeline + notes + tags |
| شاشة Database (Flutter) | 2 | قاعدة بيانات العروض |
| Follow-ups API (6 endpoints) | 1 | CRUD + Snooze + Complete |
| شاشة Follow-ups (Flutter) | 2 | لوحة المتابعات |
| Payments API (10 endpoints) | 2 | Dashboard + Status + Summary |
| شاشة Payment Dashboard (Flutter) | 3 | لوحة المدفوعات + charts |
| Notifications API (7 endpoints) | 1 | CRUD + Bell |
| Notification Bell (Flutter) | 1 | جرس + dropdown |
| **اختبار شامل** | 2 | Integration testing |

**الناتج**: إدارة عملاء كاملة مع متابعات وإشعارات

---

### المرحلة 4: لوحة الأدمن والمحاسبة (4-5 أسابيع)
> **الهدف**: أدمن + محاسبة + مخزون + موردين

| المهمة | الأيام | التفاصيل |
|--------|--------|----------|
| Settings API (14 endpoints) | 2 | الإعدادات العامة |
| Audit API (3 endpoints) | 1 | سجل المراجعة |
| شاشة Admin Dashboard (Flutter) | 5 | 8 tabs: dashboard, users, clients, quotations, settings, audit |
| Accounting API (17 endpoints) | 4 | COA + Ledger + Reports |
| شاشة Accountant (Flutter) | 4 | التقارير المالية |
| Suppliers API (7 endpoints) | 1 | CRUD الموردين |
| شاشة Suppliers (Flutter) | 2 | إدارة الموردين |
| Purchase Invoices API (10 endpoints) | 3 | فواتير الشراء + Landed cost |
| شاشة Purchase Invoices (Flutter) | 3 | إنشاء + تعديل + دفع |
| Inventory API (9 endpoints) | 2 | المخزون |
| شاشة Inventory (Flutter) | 2 | إدارة المخزون |
| شاشة Customer Summary (Flutter) | 2 | حسابات العملاء AR |
| شاشة Supplier Summary (Flutter) | 2 | حسابات الموردين AP |
| **اختبار شامل** | 3 | Full system testing |

**الناتج**: النظام كامل بكل الشاشات

---

### المرحلة 5: التنقيح والنشر (2-3 أسابيع)
> **الهدف**: تطبيق جاهز للتوزيع

| المهمة | الأيام | التفاصيل |
|--------|--------|----------|
| Import/Export API (8 endpoints) | 2 | استيراد/تصدير CSV+Excel |
| شاشة Data Import (Flutter) | 2 | استيراد CSV |
| Backup API (7 endpoints) | 2 | نسخ احتياطي |
| RTL/Arabic polish | 2 | مراجعة شاملة للتصميم العربي |
| Build Windows exe | 1 | بناء التطبيق |
| Build macOS app | 1 | بناء التطبيق |
| Build Android APK | 1 | بناء التطبيق |
| Deploy Backend (VPS) | 2 | Docker + SSL + Domain |
| ترحيل البيانات | 2 | نقل البيانات الحالية من Anvil |
| اختبار شامل على كل الأجهزة | 3 | Windows + macOS + Android |
| **إصلاح bugs** | 3 | Bug fixes |

**الناتج**: تطبيق جاهز للاستخدام اليومي

---

### ملخص الجدول الزمني

| المرحلة | المدة | الناتج |
|---------|-------|--------|
| 1. الأساس | 3-4 أسابيع | Login + Launcher يعمل |
| 2. العمليات | 4-5 أسابيع | Calculator + Quotations + Contracts |
| 3. العملاء | 3 أسابيع | Clients + Followups + Payments |
| 4. الأدمن | 4-5 أسابيع | Admin + Accounting + Inventory |
| 5. التنقيح | 2-3 أسابيع | Build + Deploy + Polish |
| **المجموع** | **16-20 أسبوع** | **نظام كامل** |

> ⚠️ **ملاحظة**: الجدول يفترض مطور واحد بدوام كامل. مع مطورين اثنين (Flutter + Backend) يمكن تقليصه لـ 10-12 أسبوع.

---

## 10. التكاليف والمتطلبات

### 10.1 تكاليف التشغيل الشهرية

| البند | التكلفة | ملاحظة |
|-------|---------|--------|
| VPS (سيرفر) | $7-15/شهر | Hetzner CX22 أو DigitalOcean |
| Domain | $1/شهر | (اختياري - يمكن استخدام IP مباشر) |
| SSL | $0 | Let's Encrypt مجاني |
| Twilio SMS | $0.0079/رسالة | اختياري - يمكن استخدام Email فقط |
| **المجموع** | **$7-16/شهر** | |

### 10.2 تكاليف لمرة واحدة (اختياري)

| البند | التكلفة | ملاحظة |
|-------|---------|--------|
| Apple Developer Account | $99/سنة | فقط لو عايز iOS |
| Google Play (لو حبيت لاحقاً) | $25 مرة واحدة | مش مطلوب حالياً |
| Code Signing (Windows) | $0 | مش مطلوب لاستخدام داخلي |

### 10.3 بدون أي تكلفة (On-Premise)

| البند | التكلفة |
|-------|---------|
| سيرفر داخلي (أي كمبيوتر) | $0 |
| PostgreSQL | $0 (open source) |
| FastAPI | $0 (open source) |
| Flutter | $0 (open source) |
| SSL (self-signed) | $0 |
| **المجموع** | **$0/شهر** |

> ⚠️ On-Premise لن يعمل خارج شبكة الشركة إلا بإعداد VPN.

---

## 11. المخاطر والحلول البديلة

### 11.1 المخاطر

| المخاطرة | الاحتمال | الأثر | الحل |
|----------|----------|-------|------|
| فقدان بيانات أثناء الترحيل | متوسط | عالي | نسخة احتياطية قبل الترحيل + تشغيل متوازي |
| Calculator logic معقدة | عالي | متوسط | نقل الـ JS engine كما هو في الخلفية أو تحويله تدريجياً |
| iOS بدون Apple Account | مؤكد | منخفض | Android فقط حالياً + إضافة iOS لاحقاً |
| تعطل السيرفر | منخفض | عالي | نسخ احتياطي يومي + Docker restart policy |
| أخطاء في المحاسبة | متوسط | عالي | Unit tests مكثفة + مقارنة مع الأرقام الحالية |

### 11.2 استراتيجية الترحيل

```
الأسبوع 1-8:   بناء النظام الجديد
الأسبوع 9-12:  تشغيل متوازي (النظامين معاً)
الأسبوع 12+:   الانتقال الكامل للنظام الجديد
```

1. **لا نوقف النظام القديم** حتى النظام الجديد يكون مختبر 100%
2. **نكتب سكريبت ترحيل** ينقل كل البيانات من Anvil → PostgreSQL
3. **نقارن الأرقام** (عدد العملاء، العروض، الأرصدة) للتأكد
4. **نشغل النظامين** لمدة أسبوعين بالتوازي قبل الانتقال

### 11.3 خطة B (لو Flutter صعب)

لو Flutter Desktop كان فيه مشاكل على Windows/macOS:
- **الحل**: استخدام Tauri (Rust + WebView) بدل Flutter Desktop
- Tauri حجمه أصغر (~3 MB) ويستخدم WebView النظام
- يحتاج كتابة الـ frontend بـ React/Vue بدل Flutter
- المدة تزيد ~4 أسابيع

---

## الخلاصة

### ماذا سيتغير؟
| الحالي | الجديد |
|--------|--------|
| يعمل في المتصفح فقط | تطبيق مستقل (exe/apk/app) |
| يعتمد على Anvil servers | سيرفر خاص (أنت تتحكم فيه) |
| مستخدم واحد في كل مرة | عدة مستخدمين متزامنين |
| لا يعمل على الموبايل | يعمل على Android (وiOS لاحقاً) |
| بطيء (Skulpt compiler) | سريع (Flutter native) |
| لا يعمل offline | يمكن إضافة offline cache لاحقاً |

### ماذا لن يتغير؟
- كل الوظائف الحالية (19 شاشة) ستنتقل كما هي
- نفس الصلاحيات (admin/manager/sales/viewer)
- نفس نظام المصادقة (OTP + TOTP)
- نفس المحاسبة (قيد مزدوج)
- نفس التصميم والألوان
- البيانات الحالية ستُنقل بالكامل

---

> 📝 **هذه الخطة قابلة للتعديل. يرجى مراجعتها وإبداء الملاحظات قبل البدء في التنفيذ.**
>
> **التاريخ**: فبراير 2026
> **المُعد**: Claude AI Assistant

# Data Schema — Helwan Plast (Anvil)

كل الجداول اللي التطبيق بيستخدمها. لازم تبقى منشأة في **Anvil → Data → Data Tables**. لو جدول ناقص، أنشئه من **+ Add New Table** وضيف الأعمدة حسب الجدول تحت.

---

## جدول ناقص (يجب إنشاؤه يدوياً)

### `accounting_period_locks`

**الغرض:** تأمين الفترات المحاسبية (شهر/سنة). لو الفترة مقفولة، الترحيل والدفع ممنوع.

| العمود      | النوع في Anvil | وصف |
|------------|-----------------|-----|
| `year`     | **number**      | السنة (مثلاً 2026) |
| `month`    | **number**      | الشهر (1–12) |
| `locked`   | **boolean**     | true = الفترة مقفولة |
| `locked_at`| **datetime**   | وقت القفل |
| `locked_by`| **string**      | بريد المستخدم اللي قفل |

**ملاحظة:** الجدول يبدأ فاضي = لا فترة مقفولة. لو حابب تقفل شهر معيّن، أضف صف بـ year, month, locked=true.

---

## بقية الجداول (مرجع)

التطبيق بيستخدم الجداول دي. أسماؤها في `schema_export.TABLE_NAMES`. الأعمدة المذكورة هنا من استعمال الكود؛ ممكن يكون عندك أعمدة إضافية.

| الجدول | أعمدة رئيسية (من الكود) |
|--------|--------------------------|
| **audit_log** | timestamp, user_email, action, details, ... |
| **chart_of_accounts** | code, name_en, name_ar, account_type, parent_code, is_active, created_at |
| **clients** | Client Code, Phone, is_deleted, ... |
| **contracts** | quotation_number, contract_number, ... |
| **counters** | name, value, ... |
| **currency_exchange_rates** | currency_code, rate_to_egp, updated_at (أو id) |
| **expenses** | id, date, category, description, amount, payment_method, account_code, status, created_by, created_at |
| **import_costs** | id, purchase_invoice_id, cost_type, amount, amount_egp, paid_amount, inventory_id, ... |
| **inventory** | id, machine_code, purchase_invoice_id, contract_number, status, purchase_cost, total_cost, selling_price, ... |
| **ledger** | id, transaction_id, date, account_code, debit, credit, description, reference_type, reference_id, created_by, created_at |
| **machine_specs** | model, ... |
| **notifications** | id, user_email, type, payload, created_at, read_at |
| **opening_balances** | name, type, account_code?, amount?, ... |
| **otp_codes** | user_email, purpose, code, ... |
| **password_history** | user_email, ... |
| **pending_passwords** | user_email, ... |
| **posted_purchase_invoice_ids** | invoice_id, ... (منع الترحيل المزدوج) |
| **purchase_invoices** | id, invoice_number, supplier_id, date, total, paid_amount, status, supplier_amount_egp, currency_code, exchange_rate_usd_to_egp, original_amount, inventory_moved, contract_number, machine_code, items_json, ... |
| **quotations** | Quotation#, Client Code, ... |
| **rate_limits** | ip_address, endpoint, ... |
| **scheduled_backups** | ... |
| **sessions** | session_token, user_email, expires_at, is_active, ... |
| **settings** | setting_key, setting_value, setting_type, ... |
| **suppliers** | id, name, is_active, ... |
| **users** | email, full_name, role, is_approved, is_active, ... |

---

## تصدير السكيما من التطبيق

الدالة `export_schema()` في `server_code/schema_export.py` تجمع أسماء وأنواع أعمدة كل الجداول اللي في `TABLE_NAMES`. لو جدول مش موجود في Anvil، التصدير يتخطاه ولا يوقف. بعد ما تنشئ `accounting_period_locks` وتنشر التطبيق، التصدير هيشمل الجدول الجديد.

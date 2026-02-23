# Data Schema — Helwan Plast (Anvil)

كل الجداول اللي التطبيق بيستخدمها. لازم تبقى منشأة في **Anvil → Data → Data Tables**. لو جدول ناقص، أنشئه من **+ Add New Table** وضيف الأعمدة حسب الجدول تحت.

---

## `accounting_period_locks` (موجود في anvil.yaml)

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

## أعمدة مطلوبة لجدول `purchase_invoices` (فواتير بالدولار والطباعة)

لو فواتير الشراء بالدولار أو الطباعة/PDF بتيجي غلط، تأكد إن جدول **purchase_invoices** فيه الأعمدة دي في Anvil:

| العمود | النوع في Anvil | وصف |
|--------|-----------------|-----|
| **currency_code** | string | عملة الفاتورة: `EGP` أو `USD`. لو ناقص، النظام يعتبر الفاتورة جنيه. |
| **exchange_rate_usd_to_egp** | number | سعر صرف الدولار للجنيه (مثلاً 48.30). مطلوب لو الفاتورة USD. |
| **total_egp** | number | إجمالي الفاتورة بالجنيه (يُحسب تلقائياً عند الحفظ لو دخلت سعر الصرف). |
| **supplier_amount_egp** | number | مبلغ المورد بالجنيه (يُملأ عند الترحيل). |
| **inventory_moved** | boolean | اختياري: هل تم نقل الصنف من العبور للمخزون. |
| **machine_config_json** | string | اختياري: تفاصيل الماكينة (JSON). |

لو عمود من دول ناقص، أضفه من **Anvil → Data → purchase_invoices → Add Column**.

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
| **purchase_invoices** | id, invoice_number, supplier_id, date, total, paid_amount, status, supplier_amount_egp, **currency_code**, **exchange_rate_usd_to_egp**, **total_egp**, original_amount, inventory_moved, contract_number, machine_code, machine_config_json, items_json, ... |
| **quotations** | Quotation#, Client Code, ... |
| **rate_limits** | ip_address, endpoint, ... |
| **scheduled_backups** | ... |
| **sessions** | session_token, user_email, expires_at, is_active, ... |
| **settings** | setting_key, setting_value, setting_type, ... |
| **suppliers** | id, name, company, phone, email, country, address, tax_id, notes, is_active, created_at, updated_at |
| **service_suppliers** | id, name, company, phone, email, country, address, tax_id, notes, service_type, is_active, created_at, updated_at |
| **users** | email, full_name, role, is_approved, is_active, ... |

---

## بالظبط إيه الناقص؟ (أي جدول — أي عمود — أي كود)

التفاصيل اللي تحت من مراجعة الكود. لو عمود مذكور هنا مش موجود في Anvil، أضفه (أو الكود هيستخدم fallback/يتخطى ويحتمل سلوك غلط).

| الجدول | العمود الناقص / الملاحظة | النوع | الكود اللي بيستخدمه |
|--------|---------------------------|-------|----------------------|
| **purchase_invoices** | `currency_code` | string | `accounting.py`: create_purchase_invoice (يحمّل)، post_purchase_invoice، update_purchase_invoice، get_purchase_invoices؛ pdf_reports.build_purchase_invoice_pdf_data. لو ناقص → الفاتورة تُعتبر EGP. |
| **purchase_invoices** | `exchange_rate_usd_to_egp` | number | نفس الدوال أعلاه + record_supplier_payment. لو ناقص → تحويل USD→EGP غلط أو معدوم. |
| **purchase_invoices** | `total_egp` | number | create_purchase_invoice (يحمّل عند وجود سعر صرف)، post_purchase_invoice، create_contract_purchase؛ pdf_reports (عرض المبلغ بالجنيه). لو ناقص → الطباعة/PDF ممكن تظهر مبالغ غلط. |
| **purchase_invoices** | `supplier_amount_egp` | number | post_purchase_invoice، create_contract_purchase (يحمّل). لو ناقص → الترحيل يحاول يحدّث والكود يتعامل مع الخطأ. |
| **purchase_invoices** | `inventory_moved` | boolean | move_purchase_to_inventory، get_purchase_invoices؛ التقارير (عبور/مخزون). الكود يتعامل مع غياب العمود (try/except). |
| **purchase_invoices** | `machine_config_json` | string | create_purchase_invoice (يحمّل)، get_purchase_invoices (يقرأ). لو ناقص → add_row يتخطاه عند الخطأ. |
| **purchase_invoices** | `exchange_rate` | number | create_purchase_invoice يكتبه في inv_row.update(opts) مع total_egp؛ post يقرأ row.get('exchange_rate'). اختياري لو exchange_rate_usd_to_egp موجود. |
| **purchase_invoices** | `original_amount` | number | اختياري؛ يُحمّل في create/update. |
| **posted_purchase_invoice_ids** | `invoice_id` | string (فريد) | accounting.py: _register_posted_purchase_invoice (add_row)، post_purchase_invoice (تحقق من تكرار). |
| **posted_purchase_invoice_ids** | `posted_at`, `created_by` | datetime, string | _register_posted_purchase_invoice. |
| **import_costs** | `currency` | string | add_import_cost (يحمّل). لو ناقص → add_row يتخطى عند الخطأ. |
| **import_costs** | `amount_egp` | number | add_import_cost؛ get_import_costs؛ pdf_reports. لو ناقص → يُستنتج من amount أو يبقى 0. |
| **import_costs** | `paid_amount` | number | add_import_cost (يحمّل 0). شاشة دفع تكاليف الاستيراد. |
| **import_costs** | `original_currency`, `original_amount`, `exchange_rate` | string, number, number | add_import_cost (يحمّل)؛ pdf_reports (عرض العملة وسعر الصرف). |
| **import_costs** | `inventory_id`, `cost_type_id` | string | add_import_cost (ربط بمخزون/نوع تكلفة). اختياري. |
| **import_costs** | عمود التاريخ | — | الكود يكتب `date`؛ pdf_reports يقرأ `cost_date`. لو تاريخ التكلفة في PDF فاضي، إما أضف عمود `cost_date` واملأه من `date` أو غيّر القالب لاستخدام `date`. |
| **ledger** | كل الأعمدة في LEDGER_COLS | — | post_journal_entry: id, transaction_id, date, account_code, debit, credit, description, reference_type, reference_id, created_by, created_at. |
| **chart_of_accounts** | code, name_en, name_ar, account_type, parent_code, is_active, created_at | — | add_account، seed_default_accounts، _ensure_vat_accounts؛ get_chart_of_accounts (ACCOUNT_COLS). |
| **suppliers** | id, name, company, phone, email, country, address, tax_id, notes, is_active, created_at, updated_at | — | add_supplier؛ update_supplier؛ get_suppliers (SUPPLIER_COLS). |
| **expenses** | id, date, category, description, amount, payment_method, reference, account_code, status, created_by, created_at | — | add_expense. |
| **inventory** | id, machine_code, description, purchase_invoice_id, contract_number, purchase_cost, import_costs_total, total_cost, selling_price, status, location, notes, machine_config_json, created_at, updated_at | — | add_inventory_item؛ create_contract_purchase؛ move_purchase_to_inventory؛ get_inventory (INVENTORY_COLS). |
| **currency_exchange_rates** | currency_code (مفتاح)، rate_to_egp, updated_at، واختياري id | — | _get_rate_to_egp (get بـ currency_code)；set_exchange_rate (add_row/update)；get_exchange_rates. |
| **opening_balances** | name, type, opening_balance, updated_at, updated_by | — | set_opening_balance (add_row/update)；get_opening_balances؛ get_customer_balance_summary؛ get_supplier_summary؛ get_treasury_summary. **ملاحظة:** الكود يستخدم `opening_balance` وليس `amount` أو `account_code`. |
| **accounting_period_locks** | year, month, locked, locked_at, locked_by | — | lock_period، unlock_period. الجدول مذكور أعلاه كجدول يُنشأ يدوياً. |
| **contracts** | contract_number، ولو استخدمت: fob_cost, cylinder_cost, supplier_id, purchase_invoice_id, currency, updated_at | — | create_contract_purchase (يحدّث العقد). |
| **import_cost_types** (إن وُجد) | id, name, default_account, is_active | — | seed_import_cost_types. |

---

## تصدير السكيما من التطبيق

الدالة `export_schema()` في `server_code/schema_export.py` تجمع أسماء وأنواع أعمدة كل الجداول اللي في `TABLE_NAMES`. لو جدول مش موجود في Anvil، التصدير يتخطاه ولا يوقف. بعد ما تنشئ `accounting_period_locks` وتنشر التطبيق، التصدير هيشمل الجدول الجديد.

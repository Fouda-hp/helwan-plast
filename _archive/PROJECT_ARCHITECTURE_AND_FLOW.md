# هيكل مشروع Helwan Plast وطريقة الربط بين الأجزاء

هذا الملف يشرح المشروع بالكامل وطريقة ربط المكونات ببعضها لتسهيل التعديلات جزءًا جزءًا.

---

## 1. نوع المشروع والمنصة

- **التطبيق:** نظام **Helwan Plast** (حلوان بلاست) — إدارة عملاء، عروض أسعار، عقود، طباعة، محاسبة، مخزون، متابعات.
- **المنصة:** [Anvil](https://anvil.works) — تطبيق ويب full-stack يُبنى بـ Python (واجهة + سيرفر).
- **نقطة الدخول:** من `anvil.yaml`: `startup: { module: LoginForm, type: form }` — أي التطبيق يبدأ من **LoginForm**.

---

## 2. الهيكل العام للمجلدات

```
Helwan_Plast - Copy/
├── anvil.yaml              # إعدادات التطبيق، الجداول (db_schema)، الخدمات، الصفحة الافتراضية
├── client_code/            # النماذج (Forms) — واجهة المستخدم
│   ├── LoginForm/          # تسجيل الدخول والتسجيل وإعداد الأدمن
│   ├── LauncherForm/       # الصفحة الرئيسية بعد الدخول — التوجيه حسب الـ hash
│   ├── CalculatorForm/     # حاسبة العروض (ربط مع JS في theme)
│   ├── ClientListForm/     # قائمة العملاء
│   ├── ClientDetailForm/    # تفاصيل عميل + ملاحظات + تايم لاين
│   ├── DatabaseForm/       # قاعدة البيانات (عروض/عملاء)
│   ├── QuotationPrintForm/  # طباعة عرض سعر
│   ├── ContractPrintForm/  # طباعة عقد
│   ├── ContractEditForm/   # تعديل عقد
│   ├── PaymentDashboardForm/ # لوحة المدفوعات
│   ├── FollowUpDashboardForm/ # لوحة المتابعات
│   ├── AdminPanel/         # لوحة الأدمن (مستخدمون، إعدادات، نسخ احتياطي، استيراد، محاسبة...)
│   ├── DataImportForm/     # استيراد CSV
│   ├── AccountantForm/      # نقطة دخول المحاسبة (موردون، فواتير، مخزون، تقارير)
│   ├── SuppliersForm/      # الموردون
│   ├── PurchaseInvoicesForm/ # فواتير المشتريات
│   ├── InventoryForm/      # المخزون
│   ├── CustomerSummaryForm/ # ملخص العملاء (محاسبة)
│   ├── SupplierSummaryForm/ # ملخص الموردين (محاسبة)
│   ├── auth_helpers.py     # تحقق من التوكن (عميل)
│   └── notif_bridge.py     # جسر الإشعارات للـ JS
├── server_code/            # المنطق على السيرفر — دوال تُستدعى من العميل
│   ├── AuthManager.py      # تسجيل دخول، جلسات، صلاحيات، إعدادات، تدقيق
│   ├── QuotationManager.py # عملاء، عروض، عقود، نسخ احتياطي، استيراد، PDF عروض
│   ├── quotation_numbers.py # ترقيم عملاء وعروض (counters)
│   ├── quotation_pdf.py    # بناء بيانات PDF لعرض السعر (يُستدعى من QuotationManager)
│   ├── quotation_backup.py # منطق النسخ الاحتياطي (يُستدعى من QuotationManager)
│   ├── notifications.py   # إشعارات (إنشاء، قراءة، حذف)
│   ├── followup_reminders.py # متابعات العروض (تعيين، تأجيل، إتمام، لوحة)
│   ├── client_notes.py     # ملاحظات ووسوم العملاء
│   ├── client_timeline.py  # تايم لاين العميل (عروض، عقود، ملاحظات)
│   ├── accounting.py       # محاسبة: حسابات، قيود، موردون، فواتير مشتريات، مخزون، تقارير، PDF
│   ├── pdf_reports.py      # بناء بيانات PDF (فواتير مشتريات، P&L، كشف مورد) — يُستدعى من accounting
│   ├── access_policy.py    # سياسة الوصول
│   ├── auth_*.py           # مصادقة: constants, utils, email, password, sessions, rate_limit, audit, totp, permissions
│   └── tests/              # اختبارات وحدة
└── theme/
    └── assets/             # أصول الواجهة (HTML, JS)
        ├── Calculator/     # حاسبة العروض (form.js, quotations.js, clients.js, core_v2.js, ...)
        ├── i18n.js         # ترجمة
        ├── notification-bell.js
        └── ...
```

---

## 3. مسار المستخدم (من الدخول حتى الصفحات)

1. **بدء التطبيق** → يفتح **LoginForm** (من `anvil.yaml`).
2. **LoginForm:**
   - إن وُجدت جلسة صالحة (sessionStorage/localStorage) → يوجّه حسب الدور: أدمن → `#admin`، غير أدمن → `#launcher`.
   - التوجيه يتم بتغيير `location.hash` ثم الاستجابة لـ `hashchange` فتح **LauncherForm** أو **AdminPanel** أو غيرهما.
3. **LauncherForm** (الصفحة الرئيسية بعد الدخول):
   - يقرأ `window.location.hash` ويوجّه:
     - `#calculator` → CalculatorForm  
     - `#clients` → ClientListForm  
     - `#database` → DatabaseForm  
     - `#admin` → AdminPanel (بعد التحقق أن المستخدم أدمن)  
     - `#import` → DataImportForm  
     - `#quotation-print` → QuotationPrintForm  
     - `#contract-print` / `#contract-new` → ContractPrintForm  
     - `#contract-edit` → ContractEditForm  
     - `#payment-dashboard` → PaymentDashboardForm  
     - `#client-detail...` → ClientDetailForm  
     - `#follow-ups` → FollowUpDashboardForm  
     - `#login` → LoginForm  
   - يحفظ آخر hash في `localStorage` (مثلاً `hp_last_page`) لاستعادته عند الـ refresh.
4. من **AdminPanel** يمكن فتح: LauncherForm، CalculatorForm، DataImportForm، LoginForm، AccountantForm، SuppliersForm، InventoryForm، PurchaseInvoicesForm.
5. من **AccountantForm** يمكن فتح: SuppliersForm، InventoryForm، PurchaseInvoicesForm، CustomerSummaryForm، SupplierSummaryForm، AdminPanel.

**ملخص:** التوجيه يعتمد على **hash** في الرابط؛ كل نموذج يفتح نموذجًا آخر عبر `open_form('FormName')`.

---

## 4. الربط بين العميل (Client) والسيرفر (Server)

- في Anvil، الكود في **client_code** يعمل في المتصفح، والكود في **server_code** يعمل على سيرفر Anvil.
- الاستدعاء من العميل إلى السيرفر يكون دوماً عبر:
  ```python
  anvil.server.call('function_name', arg1, arg2, ...)
  ```
- على السيرفر، أي دالة يُراد استدعاؤها من العميل **يجب** أن تكون معرّفة ومُعلّمة بـ:
  ```python
  @anvil.server.callable
  def function_name(...):
  ```
- **مهم:** اسم الدالة في `anvil.server.call('...')` يجب أن يطابق اسم الدالة المعرّفة على السيرفر.

### 4.1 أين توجد الدوال القابلة للاستدعاء (callable)؟

| الملف (server_code) | أمثلة دوال |
|---------------------|------------|
| **AuthManager.py** | `login_user`, `validate_token`, `get_all_settings`, `update_setting`, `get_audit_logs`, `get_machine_prices`, `save_machine_prices`, `approve_user`, `reject_user`, ... |
| **QuotationManager.py** | `save_quotation`, `get_all_clients`, `get_all_quotations`, `save_contract`, `get_contract`, `get_quotation_pdf_data`, `import_clients_data`, `create_backup`, `get_payment_dashboard_data`, ... |
| **quotation_numbers.py** | `peek_next_client_code`, `peek_next_quotation_number`, `get_quotation_number_if_needed`, `resync_numbering_counters`, `find_client_by_phone` |
| **notifications.py** | `get_user_notifications`, `mark_notification_read`, `delete_notification`, `clear_all_notifications`, ... |
| **followup_reminders.py** | `get_followup_dashboard`, `snooze_followup`, `complete_followup`, `get_quotations_for_followup`, `check_overdue_followups` — **ملاحظة:** `set_followup` يُستدعى من العميل لكنها **ليست** مُعلّمة بـ `@anvil.server.callable` في الكود الحالي (يُفضّل إضافتها). |
| **client_notes.py** | `get_client_notes`, `add_client_note`, `set_client_tags`, `get_client_with_notes_and_tags`, ... |
| **client_timeline.py** | `get_client_detail`, `get_client_timeline` |
| **accounting.py** | `get_chart_of_accounts`, `get_suppliers`, `create_purchase_invoice`, `get_inventory`, `get_customer_summary`, `get_supplier_summary`, ... (ومئات الدوال الأخرى للمحاسبة والتقارير) |

### 4.2 من يستدعي ماذا (أمثلة)

- **LoginForm** → `login_user`, `validate_token`, `register_user`, `approve_user`, ... (AuthManager).
- **CalculatorForm** → `peek_next_client_code`, `peek_next_quotation_number`, `get_quotation_number_if_needed`, `find_client_by_phone`, `save_quotation`, `get_all_quotations`, `get_all_clients`, `get_active_users_for_dropdown`, `get_calculator_settings` (quotation_numbers + QuotationManager + AuthManager).
- **QuotationPrintForm** / **ContractPrintForm** → `get_quotation_pdf_data`, `get_contract`, `save_contract`, ... (QuotationManager).
- **ClientDetailForm** / **DatabaseForm** / **FollowUpDashboardForm** → `set_followup`, `get_followup_dashboard`, ... (followup_reminders)، وملاحظات العميل من client_notes، وتايم لاين من client_timeline.
- **AdminPanel** → إعدادات، مستخدمون، تدقيق، نسخ احتياطي، استيراد، محاسبة (AuthManager، QuotationManager، notifications، accounting).
- **AccountantForm** و **SuppliersForm** و **PurchaseInvoicesForm** و **InventoryForm** و **CustomerSummaryForm** و **SupplierSummaryForm** → دوال من **accounting.py**.

---

## 5. الجداول (Data Tables) في anvil.yaml

التطبيق يعتمد على جداول Anvil التالية (يجب أن تكون منشأة ومطابقة للـ schema في المشروع):

- **المصادقة والمستخدمون:** `users`, `sessions`, `otp_codes`, `password_history`, `pending_passwords`, `rate_limits`
- **العملاء والعروض والعقود:** `clients`, `quotations`, `contracts`
- **الترقيم:** `counters`
- **النظام:** `settings`, `audit_log`, `notifications`, `machine_specs`, `scheduled_backups`
- **المحاسبة والمخزون:** `chart_of_accounts`, `ledger`, `opening_balances`, `suppliers`, `purchase_invoices`, `import_costs`, `inventory`, `expenses`, `currency_exchange_rates`, `files`

تعديل أي عمود أو جدول جديد يجب أن يُنعكس في **anvil.yaml** ثم في الكود الذي يقرأ/يكتب هذا الجدول (غالباً في server_code).

---

## 6. الحاسبة (Calculator) والـ Theme (JS)

- **CalculatorForm** (Python) يعرض واجهة الحاسبة ويُعرّف **جسورًا** للـ JS عبر `anvil.js.window`:
  - مثلاً: `getNextClientCode`, `getNextQuotationNumber`, `callPythonSave`, `getQuotationsForOverlay`, `getClientsForOverlay`, `getActiveUsersForDropdown`, ...
- هذه الدوال في Python تستدعي بدورها `anvil.server.call(...)` للترقيم والحفظ وجلب العروض/العملاء والإعدادات.
- ملفات الـ **theme/assets/Calculator/** (مثل `form.js`, `quotations.js`, `clients.js`, `core_v2.js`) تحتوي منطق الواجهة وجمع البيانات؛ `collectFormData` في JS يجمع الحقول ويرسلها عبر `callPythonSave` للحفظ على السيرفر.
- إعدادات الحاسبة وأسعار الماكينات تأتي من السيرفر (AuthManager: `get_calculator_settings`, `get_machine_prices`, `save_machine_prices`، وQuotationManager للعروض/العملاء).

---

## 7. المصادقة والصلاحيات

- **الجلسة:** بعد تسجيل الدخول يُعاد `token` ويُحفظ في `sessionStorage` (وغالباً `localStorage`) مع `user_email`, `user_role`, `user_name`.
- معظم استدعاءات السيرفر تُمرّر `token_or_email` (أو من العميل يُمرَّر التوكن أو الإيميل) للتحقق.
- **التحقق على السيرفر:** عبر `AuthManager.validate_token`, `AuthManager.is_admin`, `AuthManager.check_permission`.
- **الأدوار:** admin, manager, sales, viewer (التفاصيل في `ROLES_AND_PERMISSIONS.md`).
- العمليات الحساسة (مثل استيراد، نسخ احتياطي، إدارة مستخدمين، إعدادات) تتطلب أدمن أو صلاحية محددة (انظر نفس الملف).

---

## 8. عند التعديل جزءًا جزءًا — نقاط مهمة

1. **تعديل واجهة (Form):**  
   - عدّل في `client_code/FormName/` (غالباً `__init__.py` و/أو `_anvil_designer.py`).  
   - إذا كان النموذج يفتح نموذجًا آخر، ابحث عن `open_form('...')` في نفس الملف.

2. **تعديل منطق سيرفر (دالة موجودة):**  
   - ابحث عن اسم الدالة في `server_code` (مثلاً `grep "def function_name" server_code/`).  
   - عدّل الدالة في الملف المناسب؛ تأكد أن التوقيع (البارامترات) يطابق ما يُستدعى من العميل في `anvil.server.call('function_name', ...)`.

3. **إضافة دالة سيرفر جديدة يُستدعى منها من العميل:**  
   - أضف الدالة في الملف المناسب في `server_code`.  
   - ضع فوقها `@anvil.server.callable`.  
   - من العميل استدعِها بـ `anvil.server.call('new_function_name', ...)`.

4. **تعديل التوجيه (Routing):**  
   - التوجيه حسب الـ hash في **LauncherForm** و **LoginForm** (دالة `check_route` وما يربط بـ `hashchange`).  
   - إضافة صفحة جديدة: أضف شرطًا لـ hash جديد و`open_form('NewForm')` ثم أنشئ النموذج في client_code.

5. **تعديل الجداول:**  
   - حدّث `db_schema` في **anvil.yaml** ثم أي كود في **server_code** يقرأ/يكتب هذا الجدول (غالباً `app_tables.table_name`).

6. **تعديل الحاسبة (الواجهة أو الحقول):**  
   - Python: **CalculatorForm** والجسور في `__init__.py`.  
   - JS: **theme/assets/Calculator/** (form.js وملفات أخرى).  
   - أي حقل جديد يجب أن يُجمَع في `collectFormData` (أو ما يعادله) ويُرسل عند الحفظ.

7. **ملاحظة:** الدالة **set_followup** في `followup_reminders.py` مُستدعاة من العميل لكنها **بدون** `@anvil.server.callable` في الكود الحالي؛ إن كانت المتابعات لا تعمل من الواجهة، أضف `@anvil.server.callable` فوق `set_followup`.

---

## 9. ملفات مرجعية إضافية في المشروع

- **README.md** — تشغيل التطبيق، الجداول المطلوبة، الإعدادات والأسرار، الاختبارات.
- **SECRETS.md** — قائمة الأسرار (Anvil Secrets) المطلوبة.
- **ROLES_AND_PERMISSIONS.md** — الأدوار والصلاحيات بالتفصيل.
- **CURRENT_PROJECT_STATUS_REPORT.md** — تقرير الربط بين العميل والسيرفر وحالة الدوال.
- **OTP_CHANNEL_SETUP.md** — إعداد قناة OTP (email/sms/whatsapp).

باستخدام هذا الملف يمكنك تتبع أي جزء تريد تغييره والملف/النموذج المسؤول عنه وطريقة ربطه بباقي النظام.

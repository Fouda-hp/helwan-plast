# تقرير موقف المشروع الحالي — هل يوجد كود فاشل أو دوال غير شغالة؟

**تاريخ التقرير:** 8 فبراير 2026

---

## 1. ملخص سريع

| السؤال | الجواب |
|--------|--------|
| **هل في كود بيفشل؟** | لا يوجد كود واضح يفشل عند التشغيل العادي. توجد نقطة واحدة محتملة (استيراد البيانات بالإيميل فقط) مُوضَّحة أدناه. |
| **هل في دالة مش شغالة؟** | لا. كل الدوال المستدعاة من الواجهة لها مقابل `@anvil.server.callable` على السيرفر، والربط بين العميل والسيرفر متسق. |

---

## 2. موقف المشروع الحالي (أهم المكونات)

### 2.1 الترقيم (Counters)
- جدول **counters** موجود في **anvil.yaml** (key, value).
- **get_next_number_atomic**، **get_next_client_code**، **get_next_quotation_number**، **get_or_create_client_code**، **get_quotation_number_if_needed** كلها معرّفة ومرتبطة من **CalculatorForm** والـ **QuotationManager** — تعمل كما يُتوقَّع.

### 2.2 الإشعارات (Notifications)
- **get_user_notifications**، **mark_notification_read**، **clear_all_notifications**، **delete_all_my_notifications**، **delete_notification** كلها callable على السيرفر.
- لوحة الأدمن تستدعي **getMyNotifications**، **deleteAllMyNotifications**، **deleteOneNotification** ومرتبطة بالدوال أعلاه — لا يوجد استدعاء لدالة غير موجودة.

### 2.3 التدقيق (Audit)
- **log_audit** تُستدعى من **QuotationManager** و **AuthManager**؛ **get_audit_logs** معرّفة ومربوطة من **AdminPanel** — تعمل.
- عرض الاسم بدل الإيميل وعدم عرض "system" مُنفَّذ في **auth_audit** و **get_audit_logs** والواجهة.

### 2.4 المصادقة والصلاحيات
- **validate_token**، **login_user**، **register_user**، **approve_user**، **reject_user**، **update_user_role**، **logout_user**، **reset_admin_password_emergency**، دوال OTP ونسيان كلمة المرور، **clear_my_rate_limit** — كلها موجودة ومستدعاة من **LoginForm** أو **AdminPanel** أو **LauncherForm** بشكل متسق.

### 2.5 العملاء والعروض والعقود
- **get_all_clients**، **get_all_quotations**، **save_quotation**، **soft_delete_***، **restore_***، **export_*** — مربوطة من **CalculatorForm**، **AdminPanel**، **DatabaseForm**، **ClientListForm**، **QuotationPrintForm**، **ContractPrintForm**.
- **save_contract**، **get_contract**، **get_quotations_list**، **get_quotation_pdf_data**، **export_quotation_excel** — مستدعاة من **ContractPrintForm** و **QuotationPrintForm** ولا يوجد استدعاء لدالة غير معرّفة.

### 2.6 النسخ الاحتياطي والإعدادات
- **create_backup**، **list_scheduled_backups**، **get_scheduled_backup_file**، **restore_backup**، **list_drive_backups**، **restore_backup_from_drive** — كلها callable ومربوطة من **AdminPanel**.
- **get_all_settings**، **update_setting**، **get_setting**، **get_machine_prices**، **save_machine_prices**، **get_machine_config**، **save_machine_config** — موجودة ومستدعاة من الواجهة.

### 2.7 الاستيراد
- **import_csv**، **import_clients_data**، **import_quotations_data** — معرّفة في **QuotationManager** ومستدعاة من **DataImportForm** و **ImportCSV**.
- **ملاحظة أمان:** في **DataImportForm** يتم استدعاء الاستيراد أحياناً بـ **user_email** وأحياناً بـ **auth_token**. السيرفر يستخدم **require_admin(token_or_email)** الذي يقبل الإيميل أيضاً. من ناحية أمان يُفضّل أن يرسل العميل **auth_token** دائماً للتحقق من الجلسة؛ إن وُجد **auth_token** في النموذج فيُفضّل استخدامه أولاً (وهذا منوط بكيفية تعبئة **DataImportForm**).

---

## 3. تحقق من الربط عميل ↔ سيرفر

تمت مراجعة استدعاءات **anvil.server.call('...')** من:
- **AdminPanel**، **LoginForm**، **LauncherForm**، **CalculatorForm**، **QuotationPrintForm**، **ContractPrintForm**، **DataImportForm**، **DatabaseForm**، **ClientListForm**، **ImportCSV**

وكل اسم دالة مستدعاة له مقابل **@anvil.server.callable** في:
- **server_code/notifications.py**
- **server_code/quotation_numbers.py**
- **server_code/QuotationManager.py**
- **server_code/AuthManager.py**

**النتيجة:** لا يوجد استدعاء لدالة غير موجودة؛ لا توجد دالة "مش شغالة" بسبب غياب التعريف.

---

## 4. نقاط قد تسبب فشلاً في ظروف معينة (ليست أخطاء كود ثابتة)

| # | الوصف | التوصية |
|---|--------|----------|
| 1 | **جدول counters غير منشأ في Anvil** | عند أول نشر للتطبيق بعد إضافة جدول **counters**، يجب إنشاء الجدول من واجهة Anvil Data Tables (أو أن يُنشأ تلقائياً من الـ schema). إن لم يُنشأ الجدول، **get_next_number_atomic** سيفشل عند أول استدعاء. |
| 2 | **استيراد البيانات بالإيميل فقط** | إذا فتح المستخدم **DataImportForm** ولم يُضبط **auth_token** (مثلاً اعتماداً على **user_email** فقط)، **require_admin** قد يقبل الإيميل إن كان أدمن. من ناحية أمان: التأكد أن الاستيراد يعمل فقط بعد تسجيل دخول صحيح وأن العميل يرسل **auth_token** عند توفره. |
| 3 | **إشعارات لكل أدمن عند كل audit** | مع كثرة الإجراءات يزداد عدد صفوف **notifications** بسرعة. هذا لا يسبب "فشل" دوال، لكن قد يبطئ الاستعلامات أو يملأ التخزين. يمكن لاحقاً تخفيف الإشعارات (مثلاً إجراءات مهمة فقط أو ملخص دوري). |

---

## 5. خلاصة

- **موقف المشروع:** مستقر؛ الترقيم، الإشعارات (بما فيها المسح الكامل وحذف إشعار واحد)، التدقيق، المصادقة، العملاء، العروض، العقود، النسخ الاحتياطي، والإعدادات مربوطة ولا يوجد كود يبدو أنه "يفشل" أو دالة "مش شغالة" بسبب غياب تعريف أو ربط خاطئ.
- **كود بيفشل؟** لا يوجد بشكل واضح؛ فقط التأكد من وجود جدول **counters** في Anvil بعد النشر.
- **دالة مش شغالة؟** لا؛ كل الاستدعاءات من الواجهة لها دوال callable مطابقة على السيرفر.

---
*تمت المراجعة بناءً على تتبع الاستدعاءات والربط بين العميل والسيرفر.*

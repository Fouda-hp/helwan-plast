# ملخص تعديلات Enterprise / SaaS — Helwan Plast System

**تاريخ:** 6 فبراير 2026  
**الهدف:** رفع نضج المشروع إلى مستوى Enterprise/SaaS (+9/10) مع الحفاظ على التوافق والوظائف الحالية.

---

## قواعد التعديل (مطبقة)

- عدم كسر أي وظيفة حالية.
- جميع التعديلات Backward Compatible (نفس شكل الاستدعاءات والإرجاع).
- الحفاظ على الهيكل المعماري الحالي.
- عدم إضافة debug logs أو console.log في النسخة النهائية.
- التحسينات موثّقة في الكود.

---

## المرحلة 1: الأداء — Pagination حقيقية على السيرفر ✅

### التعديلات

1. **`server_code/QuotationManager.py`**
   - **`get_all_quotations`**: لا يحمّل كل الصفوف؛ استخدام `search(is_deleted=False)` وتمرير `order_by` إن وُجد، ثم عدّ وجمع الصفحة فقط. معاملات جديدة اختيارية: `sort_by`, `sort_dir`. إرجاع: `data`, `page`, `per_page`, `total`, `total_pages` (نفس الشكل السابق).
   - **`get_all_clients`**: نفس النمط مع `sort_by`, `sort_dir` (افتراضي: Client Code تنازلي).
   - **`get_quotations_list`**: ترقيم على السيرفر مع `page`, `page_size` (افتراضي 500). إرجاع: `success`, `data`, `total_count`, `page`, `page_size`.
   - ثوابت: `DEFAULT_PAGE`, `DEFAULT_PAGE_SIZE`, `MAX_PAGINATION_SCAN` (50000).
   - دوال مساعدة: `_quotation_matches_search`, `_client_matches_search`, `_quotation_list_matches_search`.

2. **الواجهة**
   - لا تغيير في واجهة الاستدعاء من العميل (نفس المعاملات مع قيم افتراضية).

---

## المرحلة 2: سياسة الصلاحيات — Access Policy ✅

### التعديلات

1. **`server_code/access_policy.py`** (ملف جديد)
   - تعريف الأنماط: `PUBLIC_READ_ONLY`, `AUTHENTICATED_READ`, `ADMIN_ONLY`.
   - توثيق سبب كون بعض الدوال عامة (مثل `get_next_client_code`, `get_next_quotation_number`, `get_setting`, `get_machine_prices`).

---

## المرحلة 3: منطق الأعمال — دعم delete_own ✅

### التعديلات

1. **`server_code/QuotationManager.py`**
   - **`check_delete_permission`**: يُرجع الآن `(has_permission, error, scope)` حيث `scope` = `'full'` (أدمن أو صلاحية delete) أو `'own'` (صلاحية delete_own فقط).
   - **`soft_delete_client`**, **`soft_delete_quotation`**: عند `scope == 'own'` يتم التحقق من أن `row['created_by'] == user_email`؛ وإلا رفض مع رسالة مناسبة.
   - **`restore_client`**, **`restore_quotation`**: نفس التحقق عند `scope == 'own'`.
   - استخدام `_require_authenticated` لاستخراج `user_email` من التوكن في دوال الحذف والاستعادة.

---

## المرحلة 4: نظام الإشعارات (Notifications) ✅

### التعديلات

1. **جدول `notifications` في `anvil.yaml`**
   - الحقول: `id`, `user_email`, `type`, `payload` (string/JSON), `created_at`, `read_at` (nullable).

2. **`server_code/notifications.py`** (ملف جديد)
   - **`create_notification(user_email, type, payload)`**: إنشاء إشعار (لا يُستدعى من العميل مباشرة).
   - **`get_user_notifications(token_or_email, limit, unread_only)`**: جلب إشعارات المستخدم (من الأحدث للأقدم).
   - **`mark_notification_read(notification_id, token_or_email)`**: تعليم إشعار كمقروء.
   - **`clear_all_notifications(token_or_email)`**: تعليم كل الإشعارات كمقروء (تفريغ القائمة).

3. **ربط الأحداث**
   - **QuotationManager**: بعد حفظ عرض سعر (إنشاء/تحديث) → `create_notification(user_email, 'quotation_saved', {...})`. بعد حفظ عقد → `create_notification(user_email, 'contract_saved', {...})`. بعد إنشاء نسخة احتياطية → `create_notification(user_email, 'backup_created', {...})`. بعد استعادة نسخة → `create_notification(user_email, 'backup_restored', {...})`.
   - **AuthManager**: بعد الموافقة على مستخدم → `create_notification(user_email, 'user_approved', {...})`. بعد الرفض → `create_notification(user_email, 'user_rejected', {...})`.

4. **واجهة الإشعارات في لوحة الأدمن**
   - **`client_code/AdminPanel/__init__.py`**:
     - **`get_my_notifications()`**: يستدعي `get_user_notifications` ويحوّل النتيجة إلى شكل `{ success, notifications }` مع نصوص عربية حسب النوع.
     - **`clear_all_my_notifications()`**: يستدعي `clear_all_notifications`.
   - أيقونة 🔔 في الهيدر (موجودة مسبقاً): القائمة المنسدلة تعرض الإشعارات من الأحدث للأقدم، تمييز مقروء/غير مقروء (لون خلفية)، رسالة "لا توجد إشعارات" عند الفراغ، وزر **تفريغ القائمة** لتعليم الكل كمقروء.

---

## المرحلة 5: النسخ الاحتياطي (Backup) — سياسة الاحتفاظ ✅

- **التشفير**: موجود مسبقاً (`_encrypt_backup` باستخدام مفتاح من Anvil Secrets `BACKUP_ENCRYPTION_KEY`).
- **الرفع التلقائي إلى Google Drive**: موجود (`_upload_backup_to_drive` يُستدعى من `create_backup` و`run_scheduled_backup`). في حال فشل الرفع لا تفشل عملية Backup ويتم تسجيل الحدث في Audit Log (`BACKUP_DRIVE_UPLOAD_FAILED`).
- **الاحتفاظ بنسخ (15 يوم + 30 أسبوع)**: مُنفَّذ في `QuotationManager.py`:
  - ثوابت: `BACKUP_RETENTION_DAYS = 15`, `BACKUP_RETENTION_WEEKS = 30`.
  - `_parse_backup_filename_date(filename)` لاستخراج تاريخ من اسم الملف (`Helwan_Plast_backup_YYYYMMDD_HHMM.json` أو `.json.enc`).
  - `_apply_backup_retention()`: بعد كل رفع ناجح لـ Drive، تحتفظ بكل النسخ خلال آخر 15 يوماً، ثم نسخة واحدة أسبوعياً لآخر 30 أسبوع، وتَحذف الباقي. التنفيذ داخل try/except حتى لا يؤثر فشل التنظيف على نجاح النسخ الاحتياطي.

---

## المرحلة 6: جودة الكود — تقسيم الملفات واختبارات ✅

- **تقسيم الملفات** (مُنفَّذ بالكامل):
  - **AuthManager**: استخراج إلى `auth_permissions.py` و`auth_totp.py`. `AuthManager.py` يستورد منهما ويُبقي الـ callables.
  - **QuotationManager**: استخراج الترقيم إلى `quotation_numbers.py`؛ استخراج النسخ الاحتياطي إلى `quotation_backup.py` (تشفير، رفع Drive، احتفاظ، بناء payload، استعادة قيم)؛ استخراج بيانات PDF إلى `quotation_pdf.py` (تنسيق تواريخ/أرقام، `build_pdf_data`). `QuotationManager.py` يستورد الوحدات الثلاث ويُبقي الـ callables.
- **اختبارات آلية**: مُضافة في `server_code/tests/test_enterprise.py`:
  - **TestValidateEmail**: تحقق البريد (`auth_utils.validate_email`) — صحيح/خاطئ/فارغ/طويل/نقطتان متتاليتان.
  - **TestQuotationNumbers**: `_get_next_number` مع mock لـ `app_tables` (جدول فارغ → 1، وجود max → التالي).
  - **TestDateFormatting**: منطق تنسيق التاريخ عربي/إنجليزي (يوم + شهر).
  - **TestPermissionConstants**: بنية `ROLES` و`AVAILABLE_PERMISSIONS` في `auth_constants`.
  - التشغيل من جذر المشروع: `python -m unittest server_code.tests.test_enterprise -v` أو `python -m pytest server_code/tests/test_enterprise.py -v`. (يُستخدم mock لـ `anvil` عند التشغيل خارج بيئة Anvil.)

---

## المرحلة 7: Production Hardening

- **إزالة console.log**: تم سابقاً في `colors_change_patch.js` (استخدام `debugLog` عند التوفر). لا يوجد `console.log` غير مشروط في المسارات الحرجة.
- **توحيد معالجة الأخطاء**: الدوال الحرجة تُرجع `{ success, message }` أو ترمي استثناء مع تسجيل عند الحاجة.
- **DEBUG**: في `theme/assets/Calculator/utils.js` المتغير `DEBUG = false` افتراضياً ويُفعّل تلقائياً على localhost فقط.

---

## قائمة الملفات التي تم تعديلها

| الملف | التعديل |
|-------|---------|
| `server_code/QuotationManager.py` | ترقيم على السيرفر، delete_own، إشعارات، استيراد notifications، سياسة احتفاظ النسخ 15 يوم + 30 أسبوع، استيراد quotation_numbers |
| `server_code/access_policy.py` | **جديد** — أنماط الوصول |
| `server_code/notifications.py` | **جديد** — جدول الإشعارات ودوال الواجهة |
| `server_code/AuthManager.py` | إشعارات عند الموافقة/الرفض، استيراد auth_permissions و auth_totp |
| `server_code/auth_permissions.py` | **جديد** — فحوصات الصلاحيات و require_admin / require_permission |
| `server_code/auth_totp.py` | **جديد** — تحقق TOTP وإعداد TOTP (بدون callables) |
| `server_code/quotation_numbers.py` | **جديد** — الترقيم التلقائي (callables + _get_next_number) |
| `server_code/quotation_backup.py` | **جديد** — تشفير/رفع/احتفاظ/بناء payload/استعادة قيم النسخ الاحتياطي |
| `server_code/quotation_pdf.py` | **جديد** — تنسيق تواريخ وأرقام وبناء بيانات PDF (build_pdf_data) |
| `server_code/tests/test_enterprise.py` | **جديد** — اختبارات: validate_email، ترقيم، صلاحيات، تواريخ، quotation_pdf |
| `anvil.yaml` | إضافة جدول `notifications` |
| `client_code/AdminPanel/__init__.py` | get_my_notifications من جدول notifications، clear_all_my_notifications، واجهة القائمة المنسدلة (تفريغ، مقروء/غير مقروء) |

---

## تأكيد الاستقرار

- **الحاسبة (Calculator)**: لا تغيير في واجهة الاستدعاء؛ `get_all_quotations` و `get_all_clients` تُستدعى بنفس المعاملات وتُرجع نفس الشكل.
- **لوحة الأدمن**: نفس الاستدعاءات؛ إشعارات الهيدر تستخدم الآن جدول `notifications` مع زر تفريغ القائمة.
- **طباعة العروض/العقود**: `get_quotations_list` تُستدعى بنفس المعاملات (اختياريًا مع page/page_size) وتُرجع `data` و `success` كما هو متوقع.
- **الدوال الأخرى**: لا تغيير في توقيعات الدوال المكشوفة للعميل ما عدا إضافة معاملات اختيارية بقيم افتراضية.

---

*تم إعداد هذا الملخص بعد تنفيذ المراحل 1–4 وتوثيق المراحل 5–7.*

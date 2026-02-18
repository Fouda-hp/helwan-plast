# تقرير الفحص الشامل — نظام Helwan Plast ERP
**التاريخ:** 2026-02-17
**المراجع:** Claude Opus 4.6
**النطاق:** 35 ملف مصدري (11 سيرفر + 17 عميل + 3 JavaScript + 4 مساعد)
**الملفات غير الموجودة:** `calculator-settings.js`, `route-recovery.js` — لم يتم العثور عليها في المشروع

---

## ملخص تنفيذي

تم فحص كافة الملفات المطلوبة بشكل منهجي. النظام يظهر مستوى جيداً من الهندسة الأمنية (token-based auth, OTP, TOTP, rate limiting, audit logging) لكن يحتوي على عدد من المشكلات التي تتراوح بين حرجة ومنخفضة. أبرز المخاوف تتعلق بتوافقية Skulpt/Anvil مع f-strings، واستخدام `eval` في جانب العميل، وبعض مشاكل سلامة البيانات في المحاسبة.

| الخطورة | العدد |
|---------|-------|
| CRITICAL (حرج) | 8 |
| HIGH (عالي) | 12 |
| MEDIUM (متوسط) | 18 |
| LOW (منخفض) | 14 |
| **الإجمالي** | **52** |

---

## 1. المشكلات الحرجة (CRITICAL)

### C-01: استخدام مكثف لـ f-strings غير متوافقة مع Skulpt
**الخطورة:** CRITICAL — تعطل التطبيق بالكامل
**الملفات المتأثرة:**
- `server_code/AuthManager.py` — سطور 120, 121, 130, 149, 154, 177, 226-261, 267, 268, 270, 274, 301, 434-447, 475, 478, 503, 525, 673, 727
- `server_code/accounting.py` — سطور 239, 450, 480, 560
- `server_code/quotation_numbers.py` — سطر 234
- `server_code/client_timeline.py` — سطور 221-223, 252-253, 265-266, 270-271, 287-288
- `server_code/followup_reminders.py` — سطور 122-123, 389-390
- `server_code/notifications.py` — سطور 71-96 (HTML template)
- `client_code/ContractPrintForm/__init__.py` — سطور 146, 151, 153-154
- `client_code/ContractEditForm/__init__.py` — سطور 84-86, 139

**الوصف:** Skulpt (مترجم Python في Anvil client-side) لا يدعم f-strings بالكامل. كود السيرفر في Anvil يعمل بـ CPython فالـ f-strings آمنة هناك، لكن أي كود client-side يستخدم f-strings سيفشل في بعض إصدارات Skulpt. ملفات السيرفر آمنة نسبياً لأنها تعمل على CPython، لكن ملفات العميل (`ContractPrintForm`, `ContractEditForm`) تحتوي على f-strings وهذا خطر.

**التوصية:** استبدال كل f-strings في ملفات `client_code/` بـ `str.format()` أو `%` formatting.

---

### C-02: استخدام `eval()` في جانب العميل — خطر XSS
**الخطورة:** CRITICAL — ثغرة أمنية
**الملفات المتأثرة:**
- `client_code/LauncherForm/__init__.py` — سطور 161-169 (`_inject_notification_system`), 175-188 (`_sync_auth_token_to_frame`), 192-283 (`_inject_totp_link`)
- `client_code/AdminPanel/__init__.py` — سطور 35-64, 178-191 (`_force_dashboard_reload`)
- `client_code/AccountantForm/__init__.py` — سطور 58-83, 158-176 (`_on_show`)
- `client_code/ContractEditForm/__init__.py` — سطر 73

**الوصف:** استخدام `anvil.js.window.eval()` لحقن كود JavaScript يفتح الباب أمام هجمات XSS إذا تم تمرير بيانات المستخدم بدون تنظيف. بينما الكود الحالي يحقن سلاسل ثابتة (hardcoded)، النمط نفسه خطير ويصعب صيانته.

**التوصية:** استبدال `eval()` بإنشاء عناصر DOM برمجياً عبر `document.createElement()` و `addEventListener()`.

---

### C-03: `get_otp_channel` callable بدون مصادقة
**الخطورة:** CRITICAL — تسريب معلومات
**الملف:** `server_code/AuthManager.py` — سطر 76
**الوصف:** الدالة `get_otp_channel` مُزيّنة بـ `@anvil.server.callable` لكنها لا تتحقق من أي مصادقة. أي شخص يمكنه استدعاء `anvil.server.call('get_otp_channel', 'admin@company.com')` لمعرفة طريقة المصادقة المستخدمة (email/sms/whatsapp) لأي مستخدم، مما يسهل هجمات الهندسة الاجتماعية.

**التوصية:** إضافة التحقق من المصادقة أو إزالة `@anvil.server.callable`.

---

### C-04: `phone_exists` و `client_exists` و `quotation_exists` بدون مصادقة
**الخطورة:** CRITICAL — تسريب بيانات
**الملف:** `server_code/QuotationManager.py` — سطور 139, 158, 169
**الوصف:** ثلاث دوال `@anvil.server.callable` بدون أي تحقق من المصادقة. يمكن لأي مستخدم غير مسجل دخوله التحقق من وجود أرقام هواتف أو أكواد عملاء أو أرقام عروض في النظام (User/Data Enumeration).

**التوصية:** إضافة `_require_authenticated(token_or_email)` لكل دالة.

---

### C-05: `_invalidate_dashboard_cache` callable بدون مصادقة
**الخطورة:** CRITICAL — هجمة حرمان خدمة (DoS)
**الملف:** `server_code/followup_reminders.py` — سطر 75
**الوصف:** الدالة `_invalidate_dashboard_cache` مُزيّنة بـ `@anvil.server.callable` (بدون مصادقة!) — يمكن لأي شخص إبطال الكاش بشكل متكرر مما يزيد الحمل على السيرفر.

**التوصية:** إزالة `@anvil.server.callable` (الدالة تُستدعى داخلياً فقط).

---

### C-06: `clear_my_rate_limit` يتطلب مصادقة ضعيفة
**الخطورة:** CRITICAL — تجاوز Rate Limiting
**الملف:** `server_code/AuthManager.py` — سطور 511-529
**الوصف:** دالة `clear_my_rate_limit` تسمح لأي مستخدم مصادق بمسح حدود المعدل الخاصة به. هذا يلغي الغرض من Rate Limiting تماماً — مهاجم لديه حساب يمكنه تنفيذ هجمات brute force بلا حدود.

**التوصية:** تقييد الدالة للأدمن فقط أو إزالتها من callable.

---

### C-07: `verify_backup_code` يقبل email مباشر بدون token
**الخطورة:** CRITICAL — تجاوز المصادقة
**الملف:** `server_code/AuthManager.py` — سطور 401-405
**الوصف:** الدالة `verify_backup_code(email, code)` تقبل بريد إلكتروني مباشرة وتتحقق من backup code بدون أي مصادقة مسبقة. مهاجم يعرف البريد يمكنه تجربة backup codes (8 hex chars = 4 bytes = 4.3 مليار احتمال، لكن بدون rate limiting على هذه الدالة تحديداً).

**التوصية:** إضافة rate limiting خاص بالدالة وتسجيل المحاولات الفاشلة.

---

### C-08: عدم وجود Transaction في عمليات المحاسبة الحساسة
**الخطورة:** CRITICAL — سلامة بيانات مالية
**الملف:** `server_code/accounting.py`
**الوصف:** بينما `post_journal_entry` يستخدم `@anvil.tables.in_transaction` (سطر 678)، عمليات أخرى مثل `seed_default_accounts` (سطر 290) و `lock_period`/`unlock_period` (سطور 386-418) لا تستخدم transactions. في حالة فشل جزئي أثناء `seed_default_accounts`، قد تنشأ شجرة حسابات غير مكتملة.

**التوصية:** لف العمليات التي تعدل صفوف متعددة في `@anvil.tables.in_transaction`.

---

## 2. المشكلات العالية (HIGH)

### H-01: `set` literal في `routing.py` — غير متوافق مع Skulpt
**الخطورة:** HIGH
**الملف:** `client_code/routing.py` — سطر 24
```python
ADMIN_ONLY = set(['#admin'])
```
**الوصف:** بعض إصدارات Skulpt لا تدعم `set()` constructor بشكل كامل. الأفضل استخدام قائمة أو dict.

**التوصية:** استبدال بـ `ADMIN_ONLY = ['#admin']` واستخدام `in` للفحص.

---

### H-02: `q.any_of` بدلاً من `q.any_of` الصحيحة في client_timeline
**الخطورة:** HIGH — خطأ وقت التشغيل
**الملف:** `server_code/client_timeline.py` — سطور 152, 234
```python
all_contracts = list(app_tables.contracts.search(quotation_number=q.any_of(*valid_qns)))
```
**الوصف:** المتغير `q` هنا يشير إلى آخر عنصر في حلقة `for q in quotations` (سطر 138) وليس إلى `anvil.tables.query`. هذا سيسبب خطأ `AttributeError` لأن الصف (row) ليس له method `any_of`.

**التوصية:** استخدام `import anvil.tables.query as q_module` واستبدال `q.any_of` بـ `q_module.any_of`.

---

### H-03: كاش الداشبورد مشترك بين المستخدمين
**الخطورة:** HIGH — تسريب بيانات بين المستخدمين
**الملف:** `server_code/followup_reminders.py` — سطور 40-41
**الوصف:** `_dashboard_cache` هو متغير على مستوى الوحدة (module-level). في Anvil، وحدات السيرفر تشترك في نفس العملية (process) بين المستخدمين. الكاش يخزن `user` لكن إذا طلب مستخدمان نفس `filter_status` خلال 90 ثانية، المستخدم الثاني قد يحصل على بيانات الأول.

**ملاحظة:** الكود يتحقق من `user` (سطر 240) مما يقلل المشكلة، لكن في Anvil free/personal tier قد يكون هناك process واحد فقط.

**التوصية:** استخدام `anvil.server.session` للكاش بدلاً من متغيرات module-level.

---

### H-04: عدم تحقق `ContractEditForm` من صلاحيات الأدمن
**الخطورة:** HIGH — تجاوز صلاحيات
**الملف:** `client_code/ContractEditForm/__init__.py`
**الوصف:** صفحة تعديل العقود لا تتحقق من صلاحيات المستخدم في جانب العميل. أي مستخدم يعرف الرابط `#contract-edit` يمكنه فتح الصفحة. التحقق يتم فقط على السيرفر عند الحفظ.

**التوصية:** إضافة فحص صلاحيات في `__init__` مشابه لما في `AdminPanel`.

---

### H-05: `innerHTML +=` في ContractPrintForm يسبب إعادة بناء DOM
**الخطورة:** HIGH — أداء سيئ ومخاطر أمنية
**الملف:** `client_code/ContractPrintForm/__init__.py` — سطر 154
```python
select.innerHTML += f'<option value="{q_num}">{option_text}</option>'
```
**الوصف:** استخدام `innerHTML +=` في حلقة يعيد تحليل وبناء كل HTML في كل تكرار. بالإضافة لذلك، رغم أن القيم تمر بـ `_h()` (HTML escape)، النمط نفسه خطير.

**التوصية:** استخدام `document.createElement('option')` و `appendChild()`.

---

### H-06: التوكن يُكتب في localStorage في AccountantForm
**الخطورة:** HIGH — ضعف أمني
**الملف:** `client_code/AccountantForm/__init__.py` — سطر 172
```python
if (window.localStorage) window.localStorage.setItem('auth_token', t);
```
**الوصف:** بينما بقية النظام انتقل إلى sessionStorage فقط (أكثر أماناً)، `AccountantForm._on_show` يكتب التوكن في localStorage مما يجعله متاحاً حتى بعد إغلاق المتصفح.

**التوصية:** حذف سطر `localStorage.setItem('auth_token', t)`.

---

### H-07: `resync_numbering_counters` بدون Transaction
**الخطورة:** HIGH — race condition
**الملف:** `server_code/quotation_numbers.py` — سطور 288-317
**الوصف:** دالة إعادة المزامنة تقرأ القيمة العظمى من الجدول ثم تحدث العداد في خطوتين منفصلتين. إذا تم حفظ سجل جديد بين القراءة والتحديث، قد يفقد العداد رقماً.

**التوصية:** لف العملية في `@anvil.tables.in_transaction`.

---

### H-08: عدم تنظيف المدخلات في `add_account`
**الخطورة:** HIGH — injection
**الملف:** `server_code/accounting.py` — سطور 260-287
**الوصف:** `account_type` يتم التحقق منه ضد قائمة محددة (جيد)، لكن `code` و `name_en` و `name_ar` و `parent_code` يتم تنظيفها فقط بـ `_safe_str` (strip فقط). لا يوجد تحقق من طول السلسلة أو محتواها.

**التوصية:** إضافة تحقق من الطول والأحرف المسموحة لكل حقل.

---

### H-09: `_get_contract_serial_atomic` يبدأ من 2 دائماً
**الخطورة:** HIGH — منطق أعمال خاطئ
**الملف:** `server_code/quotation_numbers.py` — سطور 191-223
**الوصف:** عند إنشاء أول عقد في السنة، يتم بذر العداد بـ 1 ثم الرقم التالي = 2. لكن التعليق يقول "يبدأ من 2" (سطر 228). إذا كان المطلوب أن يبدأ من 1، فالمنطق خاطئ.

**التوصية:** مراجعة متطلبات العمل وتوثيق القرار بوضوح.

---

### H-10: `LoginForm.clear_rate_limit` بدون مصادقة
**الخطورة:** HIGH
**الملف:** `client_code/LoginForm/__init__.py` — سطور 360-368
**الوصف:** الدالة تستدعي `clear_my_rate_limit` بدون تمرير token. بينما السيرفر يتحقق (ضعيفاً)، هذا يعني أن زر مسح Rate Limit متاح لأي شخص على صفحة تسجيل الدخول.

---

### H-11: `_send_notification_email` تعرض HTML بدون escape
**الخطورة:** HIGH — Stored XSS عبر البريد
**الملف:** `server_code/notifications.py` — سطور 93-123
**الوصف:** المتغيرات `qn`, `client_name`, `fu_date`, `created_by` تُدرج مباشرة في HTML template بدون HTML escaping. إذا أدخل مستخدم اسم عميل يحتوي `<script>`, سيتم تنفيذه في بريد المستلم.

**التوصية:** إضافة HTML escaping لكل المتغيرات قبل إدراجها في القالب.

---

### H-12: `admin-panel.js` يستخدم `innerHTML` مع بيانات مستخدم
**الخطورة:** HIGH — XSS
**الملف:** `theme/assets/admin-panel.js` — سطور 27-31
```javascript
toast.innerHTML = '<span class="icon">' + icons[type] + '</span>' +
  '<div class="content"><div class="title">' + title + '</div>' +
  '<div class="message">' + message + '</div></div>';
```
**الوصف:** `title` و `message` يُدرجان في `innerHTML` بدون escaping.

**التوصية:** استخدام `textContent` بدلاً من `innerHTML` للرسائل.

---

## 3. المشكلات المتوسطة (MEDIUM)

### M-01: `notification-system.js` — `showNotification` يستخدم innerHTML بدون escape
**الملف:** `theme/assets/notification-system.js` — سطر 21
**الوصف:** `msg` يُدرج في `innerHTML` مباشرة. مشابه لـ H-12.

---

### M-02: `notification-bell.js` — كود مضغوط وصعب الصيانة
**الملف:** `theme/assets/notification-bell.js`
**الوصف:** الملف بأكمله في سطور قليلة بدون فراغات. صعب القراءة والصيانة والمراجعة الأمنية.

**التوصية:** إعادة تنسيق الكود مع تعليقات.

---

### M-03: عدم وجود timeout لاستدعاءات السيرفر في جانب العميل
**الملفات:** جميع ملفات `client_code/`
**الوصف:** استدعاءات `anvil.server.call()` لا تحتوي على timeout. إذا تعطل السيرفر، واجهة المستخدم ستتجمد بلا نهاية.

**التوصية:** استخدام `anvil.server.call_s()` مع timeout أو عرض مؤشر تحميل.

---

### M-04: `client_notes.py` — `get_client_with_notes_and_tags` قد يفشل
**الملف:** `server_code/client_notes.py` — سطر 309
```python
'date': row.get('Date').isoformat() if row.get('Date') else None,
```
**الوصف:** إذا كان `row.get('Date')` يرجع قيمة ليست `None` ولكنها ليست كائن date/datetime (مثلاً string)، سيفشل `.isoformat()`.

**التوصية:** استخدام `_safe_isoformat` المُعرّفة في `client_timeline.py`.

---

### M-05: متغيرات كاش على مستوى الوحدة في QuotationManager
**الملف:** `server_code/QuotationManager.py` — سطور 705-711
**الوصف:** `_payment_dashboard_cache` و `_dashboard_stats_cache` مشتركان بين كل الطلبات (مثل H-03).

---

### M-06: `get_all_tags` يحمل كل العملاء
**الملف:** `server_code/client_notes.py` — سطور 257-276
**الوصف:** الدالة تبحث في كل صفوف العملاء لجمع الوسوم. مع نمو البيانات، هذا سيكون بطيئاً جداً.

**التوصية:** إنشاء جدول منفصل للوسوم أو كاش.

---

### M-07: `get_followup_dashboard` يحمل كل العروض
**الملف:** `server_code/followup_reminders.py` — سطر 255
**الوصف:** `app_tables.quotations.search(is_deleted=False)` يحمل كل العروض في الذاكرة. مع آلاف العروض، هذا سيكون بطيئاً.

---

### M-08: `check_overdue_followups` لا يحد من عدد الإشعارات
**الملف:** `server_code/followup_reminders.py` — سطور 352-401
**الوصف:** كل استدعاء ينشئ إشعاراً لكل متابعة متأخرة لكل أدمن. إذا كان هناك 100 متابعة متأخرة و 3 أدمن = 300 إشعار + 300 بريد.

---

### M-09: عدم وجود حد لعدد الجلسات في cleanup
**الملف:** `server_code/AuthManager.py`
**الوصف:** `MAX_SESSIONS_PER_USER` مُعرّف في الثوابت لكن لم يتضح من الكود المقروء أنه يتم تطبيقه عند إنشاء جلسات جديدة.

---

### M-10: DataImportForm يبني routing يدوياً
**الملف:** `client_code/DataImportForm/__init__.py` — سطور 66-87
**الوصف:** بدلاً من استخدام `routing.resolve_route()` المركزي، تكتب سلسلة `if-elif` يدوية. هذا يسبب تكراراً وعدم اتساق.

**التوصية:** استخدام `resolve_route()` من `routing.py`.

---

### M-11: `_validate_e164` تقبل أرقام بدون + ثم تضيفها
**الملف:** `server_code/AuthManager.py` — سطور 92-99
**الوصف:** الدالة تنظف الرقم ثم تضيف `+` إذا لم يكن موجوداً. هذا قد يحول رقماً محلياً (مثل `01234567890`) إلى `+01234567890` الذي ليس E.164 صالحاً لكنه يمر من regex.

---

### M-12: عدم تسجيل محاولات الدخول الفاشلة بالتفصيل
**الملف:** `server_code/AuthManager.py`
**الوصف:** محاولات الدخول الفاشلة تُسجل فقط عبر `login_attempts` counter في جدول المستخدمين. لا يوجد سجل تفصيلي بالتاريخ والـ IP لكل محاولة فاشلة.

---

### M-13: `notification-bell.js` يفحص تسجيل الدخول من localStorage
**الملف:** `theme/assets/notification-bell.js` — سطر 3
```javascript
return!!(sessionStorage.getItem('auth_token')||localStorage.getItem('auth_token'));
```
**الوصف:** بقية النظام انتقل إلى sessionStorage فقط، لكن الجرس لا يزال يتحقق من localStorage.

---

### M-14: `auth_permissions.py` — f-string في `require_permission`
**الملف:** `server_code/auth_permissions.py` — سطر 83
```python
return False, {'success': False, 'message': f'Permission denied: {permission}'}
```
**الوصف:** آمنة على السيرفر (CPython) لكن لو تم استيرادها في العميل ستفشل.

---

### M-15: `accounting.py` — `post_year_end_closing` يضيف قيود 0.01 عند break-even
**الملف:** `server_code/accounting.py` — سطور 557-558
**الوصف:** عند عدم وجود ربح أو خسارة، يُضاف قيد 0.01 مدين ودائن. هذا يخلق قيوداً مصطنعة في دفتر الأستاذ.

---

### M-16: عدم وجود تحقق من صلاحيات `check_admin_exists`
**الملف:** `client_code/LoginForm/__init__.py` — سطر 217
**الوصف:** الدالة تستدعي `anvil.server.call('check_admin_exists')` بدون أي مصادقة. هذا يكشف معلومة عن وجود أدمن أو عدمه.

---

### M-17: `QuotationPrintForm.populate_dropdown` لا يستخدم HTML escape
**الملف:** `client_code/QuotationPrintForm/__init__.py` — سطور 113-119
**الوصف:** يستخدم `document.createElement` و `textContent` (آمن) لكن `opt.value` يُعيّن بدون escape.

---

### M-18: `is_period_locked` يبحث بدلاً من get
**الملف:** `server_code/accounting.py` — سطر 379
**الوصف:** يستخدم `tbl.search(year=year, month=month)` بدلاً من `tbl.get()`. إذا وُجدت صفوف مكررة، يتحقق فقط من أول صف مقفل. لكن `search` أبطأ من `get`.

---

## 4. المشكلات المنخفضة (LOW)

### L-01: تكرار كود التحقق من الأدمن عبر عدة Forms
**الملفات:** `LoginForm`, `LauncherForm`, `AdminPanel`, `DataImportForm`
**الوصف:** كل form يعرّف `_user_is_admin()` بنفسه. يجب نقلها إلى `auth_helpers.py`.

---

### L-02: `posixpath.getcwd` workaround في AuthManager
**الملف:** `server_code/AuthManager.py` — سطور 1-8
**الوصف:** workaround لخلل في بيئة Anvil. يجب توثيقه بشكل أفضل أو التحقق من إصلاحه.

---

### L-03: `logging.basicConfig` يُستدعى مرتين
**الملفات:** `server_code/AuthManager.py` (سطر 28), `server_code/QuotationManager.py` (سطر 73), `server_code/accounting.py` (سطر 51)
**الوصف:** `basicConfig` يجب أن يُستدعى مرة واحدة فقط. الاستدعاءات اللاحقة لا تأثير لها (في CPython) لكنها تشير إلى عدم تنسيق.

---

### L-04: `client_timeline.py` — `_to_datetime` يزيل timezone
**الملف:** `server_code/client_timeline.py` — سطور 54-71
**الوصف:** التعليق يشرح السبب (تجنب مقارنة aware/naive)، لكن هذا يفقد معلومات المنطقة الزمنية. أفضل تحويل كل التواريخ إلى UTC بدلاً من إزالة timezone.

---

### L-05: `ContractPrintForm.__init__` — نص مشفر (encoding issue)
**الملف:** `client_code/ContractPrintForm/__init__.py` — سطور 38-39, 78-96
**الوصف:** تعليقات عربية تظهر كنص مشفر (mojibake). هذا يشير لمشكلة encoding في الملف.

---

### L-06: `js_bridge.py` — `register_bridges` يتخطى الأخطاء بصمت
**الملف:** `client_code/js_bridge.py` — سطور 31-38
**الوصف:** أي خطأ في تسجيل bridge يُتخطى بصمت. قد يكون من الأفضل تسجيله على الأقل.

---

### L-07: `auth_helpers._token_cache` — cache lifetime قصير جداً
**الملف:** `client_code/auth_helpers.py` — سطر 13
**الوصف:** `_CACHE_TTL = 30` ثانية. هذا قد يكون قصيراً جداً مما يسبب استدعاءات سيرفر متكررة عند التنقل بين الصفحات.

---

### L-08: `notif_bridge._is_admin` تتحقق من sessionStorage فقط
**الملف:** `client_code/notif_bridge.py` — سطور 23-27
**الوصف:** التحقق من `user_role` في sessionStorage يمكن تعديله من جانب العميل. لكن هذا لأغراض العرض فقط (الأمان يتم على السيرفر).

---

### L-09: `AdminPanel._delayed_admin_check` — setTimeout مع lambda
**الملف:** `client_code/AdminPanel/__init__.py` — سطر 105
```python
anvil.js.window.setTimeout(lambda: self._delayed_admin_check(self._retry_count), next_delay)
```
**الوصف:** استخدام `lambda` مع `setTimeout` في Skulpt قد يكون غير مستقر. الأفضل استخدام function reference.

---

### L-10: `QuotationManager` — `MAX_PAGINATION_SCAN = 50000`
**الملف:** `server_code/QuotationManager.py` — سطر 702
**الوصف:** الثابت مُعرّف لكن لم يُستخدم في الكود المقروء. إما أنه يُستخدم لاحقاً في الملف أو أنه dead code.

---

### L-11: `accounting.py` — `_export_period_info` تكرار كود
**الملف:** `server_code/accounting.py` — سطور 90-117
**الوصف:** الدالة تتحقق من `date_from`, `date_to`, `as_of` بأربع حالات. يمكن تبسيطها.

---

### L-12: عدم وجود type hints
**الملفات:** جميع ملفات السيرفر
**الوصف:** لا يوجد type hints مما يصعب الصيانة والمراجعة. (Anvil/Skulpt لا يدعمها بالكامل لكنها مفيدة للتوثيق).

---

### L-13: `followup_reminders.py` — `import time` في نطاق الدالة
**الملف:** `server_code/followup_reminders.py` — سطر 236
```python
import time as _time
```
**الوصف:** `time` يتم استيراده داخل الدالة بينما هو مستخدم أيضاً على مستوى الوحدة (سطر 342 يستخدم `_time.time()` المعرف على مستوى الوحدة أعلاه). هذا تكرار غير ضروري.

---

### L-14: `client_timeline.py` — `_parse_price` تقبل الفاصلة العربية
**الملف:** `server_code/client_timeline.py` — سطر 96
```python
s = str(val).replace(',', '').replace('،', '').strip()
```
**الوصف:** جيد — يتعامل مع الفاصلة العربية. لكن لا يتعامل مع الفاصلة كفاصل عشري (شائع في بعض البلدان العربية).

---

## 5. ملخص حسب الوحدة

| الوحدة | CRITICAL | HIGH | MEDIUM | LOW |
|--------|----------|------|--------|-----|
| `server_code/AuthManager.py` | 3 | 1 | 2 | 2 |
| `server_code/auth_permissions.py` | 0 | 0 | 1 | 0 |
| `server_code/auth_totp.py` | 0 | 0 | 0 | 0 |
| `server_code/auth_utils.py` | 0 | 0 | 0 | 0 |
| `server_code/QuotationManager.py` | 1 | 0 | 1 | 1 |
| `server_code/quotation_numbers.py` | 0 | 2 | 0 | 0 |
| `server_code/accounting.py` | 1 | 1 | 2 | 1 |
| `server_code/client_timeline.py` | 0 | 1 | 0 | 2 |
| `server_code/client_notes.py` | 0 | 0 | 1 | 0 |
| `server_code/followup_reminders.py` | 1 | 0 | 2 | 1 |
| `server_code/notifications.py` | 0 | 1 | 0 | 0 |
| `client_code/LoginForm` | 0 | 1 | 1 | 0 |
| `client_code/LauncherForm` | 1* | 0 | 0 | 0 |
| `client_code/AdminPanel` | 1* | 0 | 0 | 1 |
| `client_code/CalculatorForm` | 0 | 0 | 0 | 0 |
| `client_code/ContractPrintForm` | 1* | 1 | 0 | 1 |
| `client_code/ContractEditForm` | 0 | 1 | 0 | 0 |
| `client_code/routing.py` | 0 | 1 | 0 | 0 |
| `client_code/js_bridge.py` | 0 | 0 | 0 | 1 |
| `client_code/auth_helpers.py` | 0 | 0 | 0 | 1 |
| `client_code/notif_bridge.py` | 0 | 0 | 0 | 1 |
| `client_code/QuotationPrintForm` | 0 | 0 | 1 | 0 |
| `client_code/ClientListForm` | 0 | 0 | 0 | 0 |
| `client_code/ClientDetailForm` | 0 | 0 | 0 | 0 |
| `client_code/DatabaseForm` | 0 | 0 | 0 | 0 |
| `client_code/DataImportForm` | 0 | 0 | 1 | 0 |
| `client_code/PaymentDashboardForm` | 0 | 0 | 0 | 0 |
| `client_code/FollowUpDashboardForm` | 0 | 0 | 0 | 0 |
| `client_code/AccountantForm` | 0 | 1 | 0 | 0 |
| `theme/assets/notification-system.js` | 0 | 0 | 1 | 0 |
| `theme/assets/notification-bell.js` | 0 | 0 | 2 | 0 |
| `theme/assets/admin-panel.js` | 0 | 1 | 0 | 0 |

\* = مُحتسبة تحت C-01 (f-strings) أو C-02 (eval) المشتركة

---

## 6. النقاط الإيجابية

1. **نظام المصادقة متين:** Token-based, OTP, TOTP, rate limiting, account lockout, password history
2. **سجل التدقيق شامل:** كل عملية حساسة تُسجل مع IP والبريد والتاريخ
3. **نظام الترقيم الذري:** `get_next_number_atomic` يستخدم `@in_transaction` بشكل صحيح لمنع التكرار
4. **فصل واضح بين الوحدات:** auth_constants, auth_sessions, auth_permissions, auth_totp, auth_utils, auth_email
5. **القيد المزدوج في المحاسبة:** `post_journal_entry` يتحقق من توازن المدين والدائن
6. **HTML escaping:** `_h()` function في `ContractPrintForm` و `QuotationPrintForm`
7. **الحذف الناعم (Soft Delete):** مع إمكانية الاستعادة وفحص الصلاحيات
8. **نظام الإشعارات:** متكامل مع البريد الإلكتروني والجرس في الواجهة
9. **Routing مركزي:** في `routing.py` (رغم أن بعض الصفحات لا تستخدمه)
10. **تحقق من الأسعار:** `save_quotation` يتحقق من منطقية الأسعار (agreed <= given)

---

## 7. التوصيات الأولوية القصوى

1. **إصلاح C-03, C-04, C-05:** إضافة مصادقة للدوال callable المكشوفة
2. **إصلاح C-06, C-07:** تقييد `clear_my_rate_limit` و حماية `verify_backup_code`
3. **إصلاح H-02:** تصحيح خطأ `q.any_of` في `client_timeline.py`
4. **إصلاح H-06:** إزالة كتابة التوكن في localStorage من AccountantForm
5. **إصلاح H-11:** إضافة HTML escaping لقوالب البريد الإلكتروني
6. **مراجعة C-01:** استبدال f-strings في ملفات client_code
7. **مراجعة C-02:** تقليل استخدام eval() واستبداله بـ DOM APIs

---

*نهاية التقرير*

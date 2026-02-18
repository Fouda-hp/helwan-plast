# تقرير تصحيح المشروع (Debug Report) — Helwan Plast

**تاريخ الفحص:** 2026-02-05

---

## ملخص

تم فحص المشروع (Client، Server، Theme) والتحقق من الاستدعاءات والاستيرادات. **تم إصلاح المشاكل الحرجة التالية.**

---

## مشاكل تم إصلاحها

### 1. دالة سيرفر مفقودة: `import_csv`
- **المشكلة:** نموذج `ImportCSV` يستدعي `anvil.server.call("import_csv", file)` بينما الدالة غير موجودة على السيرفر.
- **الإصلاح:** تمت إضافة دالة `import_csv(file, token_or_email=None)` في `QuotationManager.py` تقوم بقراءة ملف CSV واستدعاء `import_clients_data`. يتطلب تسجيل دخول أدمن.
- **العميل:** تم تحديث `ImportCSV/__init__.py` ليمرّر `auth` (من sessionStorage) عند استدعاء `import_csv`.

### 2. استدعاء `get_all_settings` بدون مصادقة
- **المشكلة:** `QuotationPrintForm` و `ContractPrintForm` يستدعيان `get_all_settings()` بدون أي معامل، بينما السيرفر يتوقع `get_all_settings(token_or_email)` ويطلب صلاحية أدمن.
- **الإصلاح:** تم تعديل الدالتين في كلا النموذجين لتمرير `auth` (من sessionStorage: auth_token أو user_email) عند استدعاء `get_all_settings`.

---

## فحوصات تمت (بدون أخطاء)

| الفحص | النتيجة |
|--------|---------|
| Linter (ReadLints) | لا توجد أخطاء |
| استدعاءات السيرفر الأخرى | موجودة ومطابقة (مثل `get_quotations_list`, `save_contract`, `export_quotation_excel`, `get_quotation_pdf_data`, `import_clients_data`, `import_quotations_data`, إلخ) |
| Schema الجداول في `anvil.yaml` | الجداول المستخدمة في الكود (clients, quotations, contracts, settings, scheduled_backups, users, audit_log, ...) معرفة |
| نظام الإشعارات (بديل alert) | مُحقَن من LauncherForm و i18n.js |
| استخدام `Notification()` في ContractPrintForm | من Anvil (صحيح) |
| استخدام `@handle("import_btn", "click")` في ImportCSV | من `anvil import *` (صحيح) |

---

## ملاحظات وتوصيات

### 1. صلاحية الإعدادات في نماذج الطباعة
- بعد الإصلاح، تحميل الإعدادات في QuotationPrintForm و ContractPrintForm يعتمد على `get_all_settings(auth)` الذي **يتطلب أدمن** على السيرفر.
- إذا كان مستخدمون غير أدمن يحتاجون لفتح طباعة العروض/العقود ويريدون رؤية إعدادات (مثل سعر الصرف)، يمكن لاحقاً إضافة دالة سيرفر مثل `get_template_settings()` تعيد إعدادات للعرض فقط بدون اشتراط أدمن.

### 2. استيراد CSV (ImportCSV)
- استيراد CSV يعمل الآن فقط **بعد تسجيل الدخول كأدمن** وتمرير التوكن/الإيميل. إذا فُتح النموذج بدون جلسة، سيرجع السيرفر: "يجب تسجيل الدخول كأدمن لاستيراد CSV".

### 3. تشغيل Python محلياً
- لم يتم تشغيل `python -m py_compile` بنجاح بسبب مسار المشروع (مسافات وحروف عربية) في بيئة الـ shell. يُفضّل تشغيل فحص الصياغة يدوياً من مجلد المشروع:
  - `python -m py_compile server_code/QuotationManager.py`
  - `python -m py_compile server_code/AuthManager.py`
  - ونفس الشيء لملفات الـ client إن أردت.

### 4. الاعتماديات
- `server_code/requirements.txt` يحتوي على: reportlab, arabic-reshaper, python-bidi, xlsxwriter, pyotp, qrcode — مناسبة للمشروع.

---

## خلاصة

- **مشكلتان حرجتان** تم حلهما: إضافة `import_csv` على السيرفر وتمرير المصادقة لـ `get_all_settings` في نماذج الطباعة وتمرير المصادقة لـ `import_csv` من العميل.
- لا توجد أخطاء من الـ linter في المشروع.
- باقي الاستدعاءات والجداول متسقة مع الكود الحالي.

إذا ظهرت رسائل خطأ في Anvil أو المتصفح بعد النشر، أرسل نص الخطأ واسم النموذج/الدالة لمراجعتها.

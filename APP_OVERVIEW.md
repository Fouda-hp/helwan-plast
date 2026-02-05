# نظرة عامة على تطبيق Helwan Plast

## الوصف

تطبيق ويب مبني على **Anvil** لإدارة الحسابات (عملاء، عروض أسعار، عقود)، حاسبة تكاليف، واستيراد/تصدير البيانات. يشمل مصادقة مستخدمين، أدوار وصلاحيات، وتحقق ثنائي (OTP / TOTP).

## الهيكل الرئيسي

| المسار | الوظيفة |
|--------|---------|
| `client_code/` | نماذج الواجهة (Forms): اللانشر، تسجيل الدخول، الكالكتور، قائمة العملاء، قاعدة البيانات، الاستيراد، طباعة العروض والعقود، لوحة الأدمن |
| `client_code/LauncherForm/__init__.py` | **توحيد التوجيه**: `ROUTE_MAP`, `open_route()`, `get_restore_and_save_js()` (النماذج الأخرى تستورد منها لتجنب ModuleNotFoundError في Anvil) |
| `server_code/AuthManager.py` | المصادقة والتفويض وإدارة المستخدمين والإعدادات (يستورد من `auth_config` و `auth_helpers`) |
| `server_code/auth_config.py` | ثوابت المصادقة ومفتاح الطوارئ وصلاحيات الأدوار |
| `server_code/auth_helpers.py` | دوال مساعدة: تحقق بريد، تشفير كلمات مرور، OTP أساسي، IP العميل |
| `server_code/defaults.py` | **مصدر واحد للقيم الافتراضية**: إعدادات الكالكتور والإعدادات الأولى |
| `server_code/QuotationManager.py` | إدارة العروض والعقود والاستيراد/التصدير |
| `theme/assets/` | قوالب HTML/CSS وملفات JS للكالكتور واللانشر |

## التوجيه (Routing)

- التطبيق يعتمد على **hash** في الرابط (مثل `#launcher`, `#calculator`, `#admin`).
- الخريطة الموحدة ودوال التوجيه معرّفة في **`client_code/LauncherForm/__init__.py`** (`ROUTE_MAP`, `open_route()`, `get_restore_and_save_js()`)، والنماذج الأخرى تستوردها بـ `from LauncherForm import open_route` لأن Anvil لا يعامل مجلد `shared` كوحدة عميل.
- النماذج التي تتعامل مع التنقل: LauncherForm، LoginForm، DataImportForm، AdminPanel.

## المصادقة والأمان

- **جلسات**: مخزنة في قاعدة البيانات؛ مدة الجلسة وعدد الجلسات لكل مستخدم من `auth_config`.
- **كلمات المرور**: PBKDF2 (مع دعم ترقية من SHA-256 القديم)؛ سجل كلمات مرور سابقة لمنع إعادة الاستخدام.
- **مفتاح الطوارئ**: في بيئة الإنتاج يجب تعيين `EMERGENCY_KEY` في Anvil Secrets؛ لا يُستخدم مفتاح افتراضي في الإنتاج. تعيين السرّ `ENVIRONMENT` إلى `production` (أو `prod`/`true`/`1`) في Anvil Secrets يمنع استخدام المفتاح الافتراضي ويجعل دوال الطوارئ ترجع "Emergency key not configured" إن لم يُعيّن `EMERGENCY_KEY`.

## الإعدادات الافتراضية

- مصدر القيم الافتراضية للإعدادات (سعر الصرف، أسعار الأسطوانات، الشحن، الضريبة، إلخ): **`server_code/defaults.py`** → `get_default_settings()`.
- تُستخدم عند إنشاء أول أدمن أو عند عمليات الطوارئ التي تنشئ إعدادات.

## تعطيل الـ console في الإنتاج

- في القالب (مثل `theme/assets/standard-page.html`) يُنفَّذ سكربت يعطل `console.log` و `info` و `warn` و `debug` عندما:
  - يكون `document.documentElement.getAttribute('data-hp-env') === 'production'`، أو
  - `window.HP_DISABLE_CONSOLE === true`.
- لتفعيل التعطيل في الإنتاج: ضع على عنصر `<html>` السمة `data-hp-env="production"` أو عيّن `HP_DISABLE_CONSOLE = true` قبل تحميل الصفحة.

## ملفات إضافية

- `PROJECT_REVIEW_REPORT.md`: تقرير مراجعة المشروع والتحسينات.
- `OTP_CHANNEL_SETUP.md`: إعداد قنوات OTP (بريد، SMS، واتساب).
- `PERFORMANCE_NOTES.md`: ملاحظات أداء إن وُجدت.

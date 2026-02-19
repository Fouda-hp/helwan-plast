# هيكل النظام — Server Code Modules

تم تقسيم الكود إلى وحدات منفصلة لسهولة الصيانة مع الإبقاء على نفس الواجهة (جميع الاستدعاءات تعمل كما هي).

## وحدات المصادقة (Auth)

| الملف | المحتوى |
|--------|---------|
| **auth_constants.py** | الثوابت: محاولات الدخول، مدة الجلسة، Rate Limit، الصلاحيات (ROLES, AVAILABLE_PERMISSIONS)، البريد والسري الطوارئ. |
| **auth_utils.py** | `get_utc_now`, `make_aware`, `get_client_ip`, `validate_email`. |
| **auth_email.py** | `send_email_smtp`, `send_approval_email`, `EMAIL_SERVICE_AVAILABLE`. HTML escaping على بيانات المستخدم. |
| **auth_password.py** | `hash_password`, `verify_password`, `upgrade_password_hash`, `add_to_password_history`, `check_password_history`. Fail-closed on errors. |
| **auth_sessions.py** | `generate_session_token`, `create_session`, `validate_session`, `destroy_session`, `cleanup_expired_sessions`, **`purge_old_sessions`** (حذف نهائي للسيشنز القديمة). |
| **auth_totp.py** | `verify_totp_for_user` (TOTP + backup codes)، rate limit بـ **IP:email** composite key. Backup codes 96-bit. |
| **auth_rate_limit.py** | `check_rate_limit`. |
| **auth_permissions.py** | `check_permission`, `is_admin`, `require_admin`, `require_permission`, `require_authenticated`. |
| **auth_audit.py** | `log_audit` (مفصل)، `get_user_name_for_audit`, `build_action_description`. Truncation warning على البيانات الكبيرة. |
| **auth_webauthn.py** | WebAuthn/Passkeys. RuntimeError بدل hardcoded domain fallback. |
| **AuthManager.py** | يستورد من كل الوحدات ويحتوي على كل دوال الـ `@anvil.server.callable`. Structured logging مفعّل عند الـ startup. |

## وحدات البنية التحتية (Infrastructure)

| الملف | المحتوى |
|--------|---------|
| **shared_utils.py** | دوال مشتركة: `get_client_ip_safe`, `log_audit_safe`, `parse_date`, `to_datetime`, `parse_json_field`, `contracts_search_active`, `contracts_get_active`, `success_response`, `error_response`, `safe_float`, `safe_int`. |
| **cache_manager.py** | `TTLCache` — thread-safe مع LRU eviction. Instances: `dashboard_cache`, `tags_cache`, `report_cache`, `fx_rate_cache`, `accounting_dashboard_cache`, `payment_dashboard_cache`, `dashboard_stats_cache`. |
| **monitoring.py** | `health_check` (أي مستخدم authenticated)، `get_system_metrics` (admin only). فحص DB latency، cache stats، table counts. |
| **structured_logging.py** | `JSONFormatter`, `CorrelationFilter`, `log_request_timing` decorator، `setup_structured_logging()`. JSON output + correlation IDs per request. |

## وحدات الأعمال (Business)

| الملف | المحتوى |
|--------|---------|
| **QuotationManager.py** | إدارة العملاء والعروض والعقود والمدفوعات. Dashboard stats مع TTLCache. |
| **accounting.py** | نظام محاسبة القيد المزدوج. Report cache + accounting dashboard مع TTLCache. |
| **notifications.py** | نظام الإشعارات مع DB-level dedup. |
| **client_notes.py** | ملاحظات ووسوم العملاء. Tags cache مع TTLCache. |
| **client_timeline.py** | الجدول الزمني للعميل. يستورد من shared_utils. |
| **followup_reminders.py** | تذكيرات المتابعة. Dashboard cache مع TTLCache. |
| **quotation_pdf.py** | توليد PDF للعروض. `_safe_float` لمنع crashes. |
| **quotation_numbers.py** | ترقيم ذري (atomic) للعروض والعقود. ORDER BY DESC optimization. |
| **quotation_backup.py** | النسخ الاحتياطي. |

## الاختبارات

| الملف | المحتوى |
|--------|---------|
| **tests/test_integration_security.py** | 25+ unit tests: TTLCache, shared_utils, TOTP rate limit, cache instances. |
| **tests/test_e2e_monitoring.py** | E2E tests: structured logging JSON output, correlation IDs, session purge, cache lifecycle, monitoring structure, concurrent cache operations. |
| **tests/test_full_scenario.py** | Full lifecycle scenario test. |
| **tests/test_accounting_*.py** | Accounting integration/hardening tests. |

## سجل التدقيق المفصل

- في **anvil.yaml** تمت إضافة عمودين لجدول `audit_log`: **user_name** (الاسم الكامل)، **action_description** (وصف العملية مقروء).
- كل عملية تُسجَّل الآن مع: التوقيت، البريد، الاسم الكامل، وصف العملية (مثل "تسجيل دخول"، "إنشاء - العملاء - 123")، الجدول، المعرف، القديم/الجديد، عنوان الـ IP.
- عرض السجل: `get_audit_logs` يُرجع `user_name` و `action_description` لكل سطر؛ يمكن عرضهما في لوحة الأدمن.

## النسخ الاحتياطي

- **الدالة:** `create_backup(token_or_email)` في `QuotationManager.py` (للأدمن فقط).
- **المحتوى:** عملاء، عروض، عقود، مواصفات مكائن، إعدادات (بدون مفاتيح حساسة مثل TOTP/كلمات مرور).
- **التحميل:** من لوحة الأدمن عبر رابط "نسخة احتياطية" في الشريط العلوي؛ يتم تنزيل ملف JSON بالتاريخ والوقت في الاسم.

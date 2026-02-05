# هيكل وحدة المصادقة (Auth)

تم تقسيم `AuthManager.py` إلى وحدات منفصلة لسهولة الصيانة مع الإبقاء على نفس الواجهة (جميع الاستدعاءات من `AuthManager` تعمل كما هي).

## الوحدات

| الملف | المحتوى |
|--------|---------|
| **auth_constants.py** | الثوابت: محاولات الدخول، مدة الجلسة، Rate Limit، الصلاحيات (ROLES, AVAILABLE_PERMISSIONS)، البريد والسري الطوارئ. |
| **auth_utils.py** | `get_utc_now`, `make_aware`, `get_client_ip`, `validate_email`. |
| **auth_email.py** | `send_email_smtp`, `send_approval_email`, `EMAIL_SERVICE_AVAILABLE`. |
| **auth_password.py** | `hash_password`, `verify_password`, `upgrade_password_hash`, `add_to_password_history`, `check_password_history`. |
| **auth_sessions.py** | `generate_session_token`, `create_session`, `validate_session`, `destroy_session`, `cleanup_expired_sessions`. |
| **auth_rate_limit.py** | `check_rate_limit`. |
| **auth_audit.py** | `log_audit` (مفصل: user_name, action_description)، `get_user_name_for_audit`, `build_action_description`. |
| **AuthManager.py** | يستورد من الوحدات أعلاه ويحتوي على كل دوال الـ `@anvil.server.callable` (تسجيل، دخول، OTP، TOTP، إدارة المستخدمين، الإعدادات، سجل التدقيق، إلخ). |

## سجل التدقيق المفصل

- في **anvil.yaml** تمت إضافة عمودين لجدول `audit_log`: **user_name** (الاسم الكامل)، **action_description** (وصف العملية مقروء).
- كل عملية تُسجَّل الآن مع: التوقيت، البريد، الاسم الكامل، وصف العملية (مثل "تسجيل دخول"، "إنشاء - العملاء - 123")، الجدول، المعرف، القديم/الجديد، عنوان الـ IP.
- عرض السجل: `get_audit_logs` يُرجع `user_name` و `action_description` لكل سطر؛ يمكن عرضهما في لوحة الأدمن.

## النسخ الاحتياطي

- **الدالة:** `create_backup(token_or_email)` في `QuotationManager.py` (للأدمن فقط).
- **المحتوى:** عملاء، عروض، عقود، مواصفات مكائن، إعدادات (بدون مفاتيح حساسة مثل TOTP/كلمات مرور).
- **التحميل:** من لوحة الأدمن عبر رابط "نسخة احتياطية" في الشريط العلوي؛ يتم تنزيل ملف JSON بالتاريخ والوقت في الاسم.

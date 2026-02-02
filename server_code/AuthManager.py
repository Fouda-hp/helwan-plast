"""
AuthManager.py - نظام المصادقة والتفويض الآمن
==============================================
الميزات:
- تشفير كلمات المرور باستخدام PBKDF2 (بديل آمن لـ bcrypt)
- إدارة الجلسات في قاعدة البيانات (بدلاً من الذاكرة)
- التحكم في الصلاحيات حسب الأدوار
- قفل الحساب بعد محاولات فاشلة
- Rate Limiting للحماية من الهجمات
- تسجيل التدقيق مع IP Address
- التحقق المتقدم من صحة البريد الإلكتروني
"""

import anvil.server
from anvil.tables import app_tables
from datetime import datetime, timedelta
import hashlib
import secrets
import json
import uuid
import re
import logging

# =========================================================
# إعداد نظام التسجيل (Logging)
# =========================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =========================================================
# الثوابت والإعدادات
# =========================================================
MAX_LOGIN_ATTEMPTS = 5           # عدد المحاولات قبل القفل
LOCKOUT_DURATION_MINUTES = 30    # مدة القفل بالدقائق
SESSION_DURATION_HOURS = 24      # مدة الجلسة بالساعات
RATE_LIMIT_WINDOW_MINUTES = 15   # نافذة Rate Limiting
RATE_LIMIT_MAX_REQUESTS = 100    # الحد الأقصى للطلبات في النافذة
PBKDF2_ITERATIONS = 100000       # عدد التكرارات للتشفير (أكثر أماناً)

# صلاحيات الأدوار
ROLES = {
    'admin': ['all'],
    'manager': ['view', 'create', 'edit', 'export', 'delete_own'],
    'sales': ['view', 'create', 'edit_own'],
    'viewer': ['view']
}

# الصلاحيات المتاحة للتخصيص
AVAILABLE_PERMISSIONS = [
    'view',           # عرض البيانات
    'create',         # إنشاء بيانات جديدة
    'edit',           # تعديل أي بيانات
    'edit_own',       # تعديل بياناته فقط
    'delete',         # حذف أي بيانات
    'delete_own',     # حذف بياناته فقط
    'export',         # تصدير البيانات
    'import',         # استيراد البيانات
    'manage_users',   # إدارة المستخدمين
    'view_audit',     # عرض سجل التدقيق
    'manage_settings' # إدارة الإعدادات
]


# =========================================================
# التحقق من صحة البريد الإلكتروني (محسّن)
# =========================================================
def validate_email(email):
    """
    التحقق من صحة البريد الإلكتروني باستخدام regex متقدم
    """
    if not email:
        return False

    # نمط regex للتحقق من صحة البريد الإلكتروني
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    if not re.match(pattern, email):
        return False

    # التحقق من الطول
    if len(email) > 254:
        return False

    # التحقق من عدم وجود نقطتين متتاليتين
    if '..' in email:
        return False

    return True


# =========================================================
# تشفير كلمات المرور (PBKDF2 - أكثر أماناً من SHA-256)
# =========================================================
def hash_password(password):
    """
    تشفير كلمة المرور باستخدام PBKDF2
    أكثر أماناً من SHA-256 العادي
    """
    # توليد ملح عشوائي 32 بايت
    salt = secrets.token_hex(32)

    # استخدام PBKDF2 مع SHA-256
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        PBKDF2_ITERATIONS
    )

    # تحويل المفتاح إلى hex
    hash_value = key.hex()

    # إرجاع الملح والهاش معاً
    return f"{salt}:{hash_value}"


def verify_password(password, stored_hash):
    """
    التحقق من كلمة المرور
    """
    if not stored_hash or ':' not in stored_hash:
        return False

    try:
        salt, hash_value = stored_hash.split(':', 1)

        # إعادة حساب الهاش
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            PBKDF2_ITERATIONS
        )

        check_hash = key.hex()

        # مقارنة آمنة (ثابتة الوقت)
        return secrets.compare_digest(check_hash, hash_value)
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


# =========================================================
# إدارة الجلسات (في قاعدة البيانات)
# =========================================================
def generate_session_token():
    """توليد رمز جلسة آمن"""
    return secrets.token_urlsafe(64)


def create_session(user_email, role, ip_address=None, user_agent=None):
    """
    إنشاء جلسة جديدة في قاعدة البيانات
    """
    token = generate_session_token()
    expires = datetime.now() + timedelta(hours=SESSION_DURATION_HOURS)

    try:
        app_tables.sessions.add_row(
            session_token=token,
            user_email=user_email,
            user_role=role,
            created_at=datetime.now(),
            expires_at=expires,
            ip_address=ip_address or 'unknown',
            user_agent=user_agent or 'unknown',
            is_active=True
        )

        logger.info(f"Session created for {user_email}")
        return token
    except Exception as e:
        logger.error(f"Session creation error: {e}")
        return None


def validate_session(token):
    """
    التحقق من صحة الجلسة
    """
    if not token:
        return None

    try:
        # البحث عن الجلسة في قاعدة البيانات
        session = app_tables.sessions.get(
            session_token=token,
            is_active=True
        )

        if not session:
            return None

        # التحقق من انتهاء الصلاحية
        if datetime.now() > session['expires_at']:
            # حذف الجلسة المنتهية
            session.update(is_active=False)
            return None

        return {
            'email': session['user_email'],
            'role': session['user_role'],
            'created': session['created_at'],
            'expires': session['expires_at']
        }
    except Exception as e:
        logger.error(f"Session validation error: {e}")
        return None


def destroy_session(token):
    """
    إنهاء الجلسة (تسجيل الخروج)
    """
    if not token:
        return False

    try:
        session = app_tables.sessions.get(session_token=token)
        if session:
            session.update(is_active=False)
            return True
        return False
    except Exception as e:
        logger.error(f"Session destruction error: {e}")
        return False


def cleanup_expired_sessions():
    """
    تنظيف الجلسات المنتهية (يُستدعى دورياً)
    """
    try:
        expired = list(app_tables.sessions.search(is_active=True))
        count = 0
        for session in expired:
            if session['expires_at'] and datetime.now() > session['expires_at']:
                session.update(is_active=False)
                count += 1

        if count > 0:
            logger.info(f"Cleaned up {count} expired sessions")
    except Exception as e:
        logger.error(f"Session cleanup error: {e}")


# =========================================================
# Rate Limiting (حماية من الهجمات)
# =========================================================
def check_rate_limit(ip_address, endpoint='general'):
    """
    التحقق من Rate Limit
    يعود True إذا كان الطلب مسموح، False إذا كان محظور
    """
    if not ip_address:
        ip_address = 'unknown'

    try:
        now = datetime.now()
        window_start = now - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)

        # البحث عن سجل Rate Limit
        record = app_tables.rate_limits.get(
            ip_address=ip_address,
            endpoint=endpoint
        )

        if record:
            # التحقق من الحظر
            if record['blocked_until'] and now < record['blocked_until']:
                return False

            # التحقق من النافذة الزمنية
            if record['window_start'] and record['window_start'] > window_start:
                # داخل النافذة - زيادة العداد
                new_count = (record['request_count'] or 0) + 1

                if new_count > RATE_LIMIT_MAX_REQUESTS:
                    # حظر لمدة ساعة
                    record.update(
                        request_count=new_count,
                        blocked_until=now + timedelta(hours=1)
                    )
                    logger.warning(f"Rate limit exceeded for IP: {ip_address}")
                    return False

                record.update(request_count=new_count)
            else:
                # بداية نافذة جديدة
                record.update(
                    request_count=1,
                    window_start=now,
                    blocked_until=None
                )
        else:
            # إنشاء سجل جديد
            app_tables.rate_limits.add_row(
                ip_address=ip_address,
                endpoint=endpoint,
                request_count=1,
                window_start=now,
                blocked_until=None
            )

        return True
    except Exception as e:
        logger.error(f"Rate limit check error: {e}")
        return True  # السماح في حالة الخطأ


# =========================================================
# تسجيل التدقيق (مع IP Address)
# =========================================================
def log_audit(action, table_name, record_id, old_data, new_data, user_email=None, ip_address=None):
    """
    تسجيل العملية في سجل التدقيق
    """
    try:
        app_tables.audit_log.add_row(
            log_id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            user_email=user_email or 'system',
            action=action,
            table_name=table_name,
            record_id=str(record_id) if record_id else None,
            old_data=json.dumps(old_data, default=str) if old_data else None,
            new_data=json.dumps(new_data, default=str) if new_data else None,
            ip_address=ip_address or 'unknown'
        )
    except Exception as e:
        logger.error(f"Audit log error: {e}")


# =========================================================
# الحصول على IP Address
# =========================================================
def get_client_ip():
    """
    الحصول على IP Address للعميل
    """
    try:
        # في Anvil، يمكن الحصول على IP من headers
        import anvil.server
        return anvil.server.request.remote_addr or 'unknown'
    except:
        return 'unknown'


# =========================================================
# تسجيل مستخدم جديد
# =========================================================
@anvil.server.callable
def register_user(email, password, full_name, phone=None):
    """
    تسجيل مستخدم جديد (في انتظار موافقة الأدمن)
    """
    ip_address = get_client_ip()

    # التحقق من Rate Limit
    if not check_rate_limit(ip_address, 'register'):
        return {'success': False, 'message': 'Too many requests. Please try again later.'}

    # تنظيف المدخلات
    email = str(email or '').strip().lower()
    full_name = str(full_name or '').strip()
    phone = str(phone or '').strip() if phone else None

    # التحقق من صحة البريد الإلكتروني
    if not validate_email(email):
        return {'success': False, 'message': 'Invalid email address format'}

    # التحقق من كلمة المرور
    if not password or len(password) < 8:
        return {'success': False, 'message': 'Password must be at least 8 characters'}

    # التحقق من قوة كلمة المرور
    if not re.search(r'[A-Z]', password):
        return {'success': False, 'message': 'Password must contain at least one uppercase letter'}

    if not re.search(r'[a-z]', password):
        return {'success': False, 'message': 'Password must contain at least one lowercase letter'}

    if not re.search(r'\d', password):
        return {'success': False, 'message': 'Password must contain at least one number'}

    # التحقق من الاسم
    if not full_name or len(full_name) < 2:
        return {'success': False, 'message': 'Full name is required (at least 2 characters)'}

    # التحقق من عدم وجود البريد مسبقاً
    existing = app_tables.users.get(email=email)
    if existing:
        return {'success': False, 'message': 'Email already registered'}

    # إنشاء المستخدم
    user_id = str(uuid.uuid4())
    password_hash = hash_password(password)

    try:
        app_tables.users.add_row(
            user_id=user_id,
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            phone=phone,
            role='viewer',  # الدور الافتراضي
            is_approved=False,
            is_active=True,
            created_at=datetime.now(),
            login_attempts=0,
            custom_permissions=None
        )

        # تسجيل في Audit Log
        log_audit('REGISTER', 'users', user_id, None,
                  {'email': email, 'full_name': full_name},
                  email, ip_address)

        logger.info(f"New user registered: {email}")

        return {
            'success': True,
            'message': 'Registration successful! Please wait for admin approval.'
        }
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return {'success': False, 'message': 'Registration failed. Please try again.'}


# =========================================================
# تسجيل الدخول
# =========================================================
@anvil.server.callable
def login_user(email, password):
    """
    تسجيل دخول المستخدم
    """
    ip_address = get_client_ip()

    # التحقق من Rate Limit
    if not check_rate_limit(ip_address, 'login'):
        return {'success': False, 'message': 'Too many login attempts. Please try again later.'}

    email = str(email or '').strip().lower()

    if not email or not password:
        return {'success': False, 'message': 'Email and password are required'}

    # البحث عن المستخدم
    user = app_tables.users.get(email=email)

    if not user:
        # عدم الكشف عن وجود البريد
        return {'success': False, 'message': 'Invalid email or password'}

    # التحقق من القفل
    if user['locked_until'] and user['locked_until'] > datetime.now():
        remaining = (user['locked_until'] - datetime.now()).seconds // 60
        return {
            'success': False,
            'message': f'Account locked. Try again in {remaining} minutes.'
        }

    # التحقق من تفعيل الحساب
    if not user['is_active']:
        return {'success': False, 'message': 'Account is deactivated. Contact admin.'}

    # التحقق من الموافقة
    if not user['is_approved']:
        return {'success': False, 'message': 'Account pending admin approval'}

    # التحقق من كلمة المرور
    if not verify_password(password, user['password_hash']):
        # زيادة عداد المحاولات الفاشلة
        attempts = (user['login_attempts'] or 0) + 1

        if attempts >= MAX_LOGIN_ATTEMPTS:
            user.update(
                login_attempts=attempts,
                locked_until=datetime.now() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            )
            log_audit('ACCOUNT_LOCKED', 'users', user['user_id'], None,
                      {'email': email, 'attempts': attempts}, email, ip_address)
            return {
                'success': False,
                'message': f'Account locked for {LOCKOUT_DURATION_MINUTES} minutes due to too many failed attempts.'
            }

        user.update(login_attempts=attempts)
        remaining = MAX_LOGIN_ATTEMPTS - attempts
        return {
            'success': False,
            'message': f'Invalid password. {remaining} attempts remaining.'
        }

    # نجاح تسجيل الدخول
    user.update(
        login_attempts=0,
        locked_until=None,
        last_login=datetime.now()
    )

    # إنشاء جلسة جديدة
    token = create_session(email, user['role'], ip_address)

    if not token:
        return {'success': False, 'message': 'Session creation failed. Please try again.'}

    # تسجيل في Audit Log
    log_audit('LOGIN', 'users', user['user_id'], None,
              {'email': email}, email, ip_address)

    logger.info(f"User logged in: {email}")

    return {
        'success': True,
        'message': 'Login successful',
        'token': token,
        'user': {
            'email': user['email'],
            'full_name': user['full_name'],
            'role': user['role'],
            'phone': user.get('phone', '')
        }
    }


# =========================================================
# تسجيل الخروج
# =========================================================
@anvil.server.callable
def logout_user(token):
    """
    تسجيل خروج المستخدم
    """
    ip_address = get_client_ip()
    session = validate_session(token)

    if session:
        log_audit('LOGOUT', 'users', None, None,
                  {'email': session['email']}, session['email'], ip_address)
        destroy_session(token)
        logger.info(f"User logged out: {session['email']}")

    return {'success': True}


# =========================================================
# التحقق من الجلسة
# =========================================================
@anvil.server.callable
def validate_token(token):
    """
    التحقق من صحة الجلسة وإرجاع معلومات المستخدم
    """
    session = validate_session(token)

    if not session:
        return {'valid': False}

    user = app_tables.users.get(email=session['email'])

    if not user or not user['is_active'] or not user['is_approved']:
        destroy_session(token)
        return {'valid': False}

    return {
        'valid': True,
        'user': {
            'email': user['email'],
            'full_name': user['full_name'],
            'role': user['role'],
            'phone': user.get('phone', '')
        }
    }


# =========================================================
# التحقق من الصلاحيات
# =========================================================
@anvil.server.callable
def check_permission(token, action):
    """
    التحقق من صلاحية المستخدم لإجراء معين
    """
    session = validate_session(token)

    if not session:
        return False

    role = session.get('role', '')

    # الحصول على صلاحيات الدور
    role_permissions = ROLES.get(role, [])

    # التحقق من الصلاحية
    if 'all' in role_permissions:
        return True

    if action in role_permissions:
        return True

    # التحقق من الصلاحيات المخصصة
    user = app_tables.users.get(email=session['email'])
    if user and user.get('custom_permissions'):
        try:
            custom = json.loads(user['custom_permissions'])
            if action in custom:
                return True
        except:
            pass

    return False


@anvil.server.callable
def is_admin(token):
    """
    التحقق من أن المستخدم أدمن
    """
    # أولاً: التحقق من الجلسة
    session = validate_session(token)
    if session and session.get('role') == 'admin':
        return True

    # ثانياً: إذا كان token هو email (fallback)
    if token and '@' in str(token):
        user = app_tables.users.get(email=token.lower())
        return user and user['role'] == 'admin' and user['is_active'] and user['is_approved']

    return False


def is_admin_by_email(email):
    """
    التحقق من أن المستخدم أدمن بالبريد الإلكتروني
    """
    if not email:
        return False
    user = app_tables.users.get(email=email.lower())
    return user and user['role'] == 'admin' and user['is_active'] and user['is_approved']


def require_admin(token_or_email):
    """
    دالة مساعدة للتحقق من صلاحية الأدمن
    تعود tuple: (is_admin, error_response)
    """
    if is_admin(token_or_email) or is_admin_by_email(token_or_email):
        return True, None
    return False, {'success': False, 'message': 'Admin access required'}


def require_permission(token, permission):
    """
    دالة مساعدة للتحقق من صلاحية معينة
    """
    if not check_permission(token, permission):
        return False, {'success': False, 'message': f'Permission denied: {permission}'}
    return True, None


# =========================================================
# وظائف الأدمن
# =========================================================
@anvil.server.callable
def get_pending_users(token_or_email):
    """
    الحصول على المستخدمين في انتظار الموافقة
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error

    users = []
    for user in app_tables.users.search(is_approved=False, is_active=True):
        users.append({
            'user_id': user['user_id'],
            'email': user['email'],
            'full_name': user['full_name'],
            'phone': user.get('phone', ''),
            'created_at': user['created_at'].isoformat() if user['created_at'] else ''
        })

    return {'success': True, 'users': users}


@anvil.server.callable
def approve_user(token_or_email, user_id, role='viewer', custom_permissions=None):
    """
    الموافقة على مستخدم وتعيين دوره وصلاحياته
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error

    ip_address = get_client_ip()
    user = app_tables.users.get(user_id=user_id)

    if not user:
        return {'success': False, 'message': 'User not found'}

    if role not in ROLES:
        return {'success': False, 'message': 'Invalid role'}

    # تحويل الصلاحيات المخصصة إلى JSON
    permissions_json = None
    if custom_permissions and isinstance(custom_permissions, list):
        # التحقق من صحة الصلاحيات
        valid_permissions = [p for p in custom_permissions if p in AVAILABLE_PERMISSIONS]
        if valid_permissions:
            permissions_json = json.dumps(valid_permissions)

    admin_email = token_or_email if '@' in str(token_or_email) else 'admin'

    user.update(
        is_approved=True,
        role=role,
        custom_permissions=permissions_json,
        approved_by=admin_email,
        approved_at=datetime.now()
    )

    log_audit('APPROVE_USER', 'users', user_id, None, {
        'email': user['email'],
        'role': role,
        'custom_permissions': permissions_json,
        'approved_by': admin_email
    }, admin_email, ip_address)

    logger.info(f"User approved: {user['email']} with role {role}")

    return {'success': True, 'message': 'User approved successfully'}


@anvil.server.callable
def reject_user(token_or_email, user_id):
    """
    رفض تسجيل مستخدم
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error

    ip_address = get_client_ip()
    user = app_tables.users.get(user_id=user_id)

    if not user:
        return {'success': False, 'message': 'User not found'}

    email = user['email']
    admin_email = token_or_email if '@' in str(token_or_email) else 'admin'

    user.delete()

    log_audit('REJECT_USER', 'users', user_id, None, {
        'email': email,
        'rejected_by': admin_email
    }, admin_email, ip_address)

    logger.info(f"User rejected: {email}")

    return {'success': True, 'message': 'User rejected'}


@anvil.server.callable
def get_all_users(token_or_email):
    """
    الحصول على جميع المستخدمين
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error

    users = []
    for user in app_tables.users.search():
        users.append({
            'user_id': user['user_id'],
            'email': user['email'],
            'full_name': user['full_name'],
            'phone': user.get('phone', ''),
            'role': user['role'],
            'is_approved': user['is_approved'],
            'is_active': user['is_active'],
            'custom_permissions': user.get('custom_permissions'),
            'created_at': user['created_at'].isoformat() if user['created_at'] else '',
            'last_login': user['last_login'].isoformat() if user['last_login'] else 'Never'
        })

    return {'success': True, 'users': users}


@anvil.server.callable
def update_user_role(token_or_email, user_id, new_role, custom_permissions=None):
    """
    تحديث دور المستخدم وصلاحياته
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error

    if new_role not in ROLES:
        return {'success': False, 'message': 'Invalid role'}

    ip_address = get_client_ip()
    user = app_tables.users.get(user_id=user_id)

    if not user:
        return {'success': False, 'message': 'User not found'}

    admin_email = token_or_email if '@' in str(token_or_email) else 'admin'
    old_role = user['role']
    old_permissions = user.get('custom_permissions')

    # تحويل الصلاحيات المخصصة إلى JSON
    permissions_json = None
    if custom_permissions and isinstance(custom_permissions, list):
        valid_permissions = [p for p in custom_permissions if p in AVAILABLE_PERMISSIONS]
        if valid_permissions:
            permissions_json = json.dumps(valid_permissions)

    user.update(
        role=new_role,
        custom_permissions=permissions_json
    )

    log_audit('UPDATE_ROLE', 'users', user_id,
              {'role': old_role, 'custom_permissions': old_permissions},
              {'role': new_role, 'custom_permissions': permissions_json, 'updated_by': admin_email},
              admin_email, ip_address)

    return {'success': True, 'message': 'Role updated successfully'}


@anvil.server.callable
def toggle_user_active(token_or_email, user_id):
    """
    تفعيل/تعطيل حساب مستخدم
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error

    ip_address = get_client_ip()
    user = app_tables.users.get(user_id=user_id)

    if not user:
        return {'success': False, 'message': 'User not found'}

    admin_email = token_or_email if '@' in str(token_or_email) else 'admin'

    # منع الأدمن من تعطيل نفسه
    if user['email'] == admin_email:
        return {'success': False, 'message': 'Cannot deactivate your own account'}

    new_status = not user['is_active']
    user.update(is_active=new_status)

    # إنهاء جميع جلسات المستخدم إذا تم تعطيله
    if not new_status:
        for session in app_tables.sessions.search(user_email=user['email'], is_active=True):
            session.update(is_active=False)

    action = 'ACTIVATE_USER' if new_status else 'DEACTIVATE_USER'
    log_audit(action, 'users', user_id, None, {
        'email': user['email'],
        'by': admin_email
    }, admin_email, ip_address)

    status_text = 'activated' if new_status else 'deactivated'
    return {'success': True, 'message': f'User {status_text} successfully'}


@anvil.server.callable
def reset_user_password(token_or_email, user_id, new_password):
    """
    إعادة تعيين كلمة مرور مستخدم
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error

    if not new_password or len(new_password) < 8:
        return {'success': False, 'message': 'Password must be at least 8 characters'}

    ip_address = get_client_ip()
    user = app_tables.users.get(user_id=user_id)

    if not user:
        return {'success': False, 'message': 'User not found'}

    admin_email = token_or_email if '@' in str(token_or_email) else 'admin'

    user.update(
        password_hash=hash_password(new_password),
        login_attempts=0,
        locked_until=None
    )

    log_audit('RESET_PASSWORD', 'users', user_id, None, {
        'email': user['email'],
        'by': admin_email
    }, admin_email, ip_address)

    return {'success': True, 'message': 'Password reset successfully'}


@anvil.server.callable
def change_own_password(token, old_password, new_password):
    """
    تغيير كلمة المرور الخاصة
    """
    session = validate_session(token)

    if not session:
        return {'success': False, 'message': 'Session expired. Please login again.'}

    ip_address = get_client_ip()
    user = app_tables.users.get(email=session['email'])

    if not user:
        return {'success': False, 'message': 'User not found'}

    if not verify_password(old_password, user['password_hash']):
        return {'success': False, 'message': 'Current password is incorrect'}

    if not new_password or len(new_password) < 8:
        return {'success': False, 'message': 'New password must be at least 8 characters'}

    user.update(password_hash=hash_password(new_password))

    log_audit('CHANGE_PASSWORD', 'users', user['user_id'], None,
              {'email': user['email']}, user['email'], ip_address)

    return {'success': True, 'message': 'Password changed successfully'}


# =========================================================
# إعداد الأدمن الأول
# =========================================================
@anvil.server.callable
def check_admin_exists():
    """
    التحقق من وجود أدمن
    """
    try:
        existing_admin = app_tables.users.get(role='admin')
        return {'exists': existing_admin is not None}
    except:
        return {'exists': False}


@anvil.server.callable
def setup_initial_admin(email, password, full_name, phone=None):
    """
    إنشاء أول حساب أدمن (يعمل فقط إذا لم يكن هناك أدمن)
    """
    ip_address = get_client_ip()

    try:
        # التحقق من عدم وجود أدمن
        existing_admin = app_tables.users.get(role='admin')
        if existing_admin:
            return {'success': False, 'message': 'Admin account already exists'}

        # التحقق من المدخلات
        email = str(email or '').strip().lower()

        if not validate_email(email):
            return {'success': False, 'message': 'Invalid email address format'}

        if not password or len(password) < 8:
            return {'success': False, 'message': 'Password must be at least 8 characters'}

        user_id = str(uuid.uuid4())

        app_tables.users.add_row(
            user_id=user_id,
            email=email,
            password_hash=hash_password(password),
            full_name=full_name or 'Administrator',
            phone=phone,
            role='admin',
            is_approved=True,
            is_active=True,
            created_at=datetime.now(),
            login_attempts=0,
            custom_permissions=None
        )

        # إنشاء الإعدادات الافتراضية
        _initialize_default_settings()

        log_audit('SETUP_ADMIN', 'users', user_id, None,
                  {'email': email}, email, ip_address)

        logger.info(f"Initial admin created: {email}")

        return {'success': True, 'message': 'Admin account created successfully'}

    except Exception as e:
        logger.error(f"Admin setup error: {e}")
        return {'success': False, 'message': f'Error: {str(e)}'}


def _initialize_default_settings():
    """
    إنشاء الإعدادات الافتراضية
    """
    default_settings = [
        {
            'key': 'exchange_rate',
            'value': '47.5',
            'type': 'number',
            'description': 'Exchange Rate (USD to EGP)'
        },
        {
            'key': 'cylinder_prices',
            'value': json.dumps({
                '80': 3.49, '100': 3.59, '120': 4.05,
                '130': 4.5, '140': 5.026, '160': 5.4
            }),
            'type': 'json',
            'description': 'Cylinder prices per CM'
        },
        {
            'key': 'default_cylinder_sizes',
            'value': json.dumps([25, 30, 35, 40, 45, 50, 60]),
            'type': 'json',
            'description': 'Default cylinder sizes'
        },
        {
            'key': 'shipping_sea',
            'value': '3200',
            'type': 'number',
            'description': 'Sea shipping cost (USD)'
        },
        {
            'key': 'ths_cost',
            'value': '1000',
            'type': 'number',
            'description': 'THS cost (USD)'
        },
        {
            'key': 'clearance_expenses',
            'value': '1400',
            'type': 'number',
            'description': 'Clearance expenses (USD)'
        },
        {
            'key': 'tax_rate',
            'value': '0.15',
            'type': 'number',
            'description': 'Tax rate (decimal)'
        },
        {
            'key': 'bank_commission',
            'value': '0.0132',
            'type': 'number',
            'description': 'Bank commission rate (decimal)'
        }
    ]

    for setting in default_settings:
        existing = app_tables.settings.get(setting_key=setting['key'])
        if not existing:
            app_tables.settings.add_row(
                setting_key=setting['key'],
                setting_value=setting['value'],
                setting_type=setting['type'],
                description=setting['description'],
                updated_by='system',
                updated_at=datetime.now()
            )


# =========================================================
# إدارة الإعدادات (للأدمن فقط)
# =========================================================
@anvil.server.callable
def get_all_settings(token_or_email):
    """
    الحصول على جميع الإعدادات
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error

    settings = []
    for setting in app_tables.settings.search():
        settings.append({
            'key': setting['setting_key'],
            'value': setting['setting_value'],
            'type': setting['setting_type'],
            'description': setting['description'],
            'updated_by': setting.get('updated_by', ''),
            'updated_at': setting['updated_at'].isoformat() if setting.get('updated_at') else ''
        })

    return {'success': True, 'settings': settings}


@anvil.server.callable
def update_setting(token_or_email, key, value):
    """
    تحديث إعداد معين
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error

    ip_address = get_client_ip()
    admin_email = token_or_email if '@' in str(token_or_email) else 'admin'

    setting = app_tables.settings.get(setting_key=key)

    if not setting:
        return {'success': False, 'message': 'Setting not found'}

    old_value = setting['setting_value']

    setting.update(
        setting_value=str(value),
        updated_by=admin_email,
        updated_at=datetime.now()
    )

    log_audit('UPDATE_SETTING', 'settings', key,
              {'value': old_value},
              {'value': value, 'updated_by': admin_email},
              admin_email, ip_address)

    return {'success': True, 'message': 'Setting updated successfully'}


@anvil.server.callable
def get_setting(key):
    """
    الحصول على قيمة إعداد معين (متاح للجميع)
    """
    setting = app_tables.settings.get(setting_key=key)

    if not setting:
        return None

    value = setting['setting_value']
    setting_type = setting['setting_type']

    # تحويل القيمة حسب النوع
    if setting_type == 'number':
        try:
            return float(value)
        except:
            return value
    elif setting_type == 'json':
        try:
            return json.loads(value)
        except:
            return value
    elif setting_type == 'bool':
        return value.lower() in ('true', '1', 'yes')

    return value


# =========================================================
# سجل التدقيق
# =========================================================
@anvil.server.callable
def get_audit_logs(token_or_email, limit=100, offset=0, filters=None):
    """
    الحصول على سجلات التدقيق
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error

    all_logs = list(app_tables.audit_log.search())

    # ترتيب تنازلي حسب التاريخ
    all_logs.sort(key=lambda x: x['timestamp'] or datetime.min, reverse=True)

    # تطبيق الفلاتر
    if filters:
        if filters.get('action'):
            all_logs = [l for l in all_logs if l['action'] == filters['action']]
        if filters.get('user_email'):
            all_logs = [l for l in all_logs if l['user_email'] == filters['user_email']]
        if filters.get('table_name'):
            all_logs = [l for l in all_logs if l['table_name'] == filters['table_name']]

    total = len(all_logs)
    page_logs = all_logs[offset:offset + limit]

    logs = []
    for log in page_logs:
        logs.append({
            'log_id': log['log_id'],
            'timestamp': log['timestamp'].isoformat() if log['timestamp'] else '',
            'user_email': log['user_email'],
            'action': log['action'],
            'table_name': log['table_name'],
            'record_id': log['record_id'],
            'old_data': log['old_data'],
            'new_data': log['new_data'],
            'ip_address': log.get('ip_address', 'N/A')
        })

    return {
        'success': True,
        'logs': logs,
        'total': total,
        'limit': limit,
        'offset': offset
    }


# =========================================================
# الحصول على الصلاحيات المتاحة
# =========================================================
@anvil.server.callable
def get_available_permissions():
    """
    الحصول على قائمة الصلاحيات المتاحة
    """
    return {
        'success': True,
        'permissions': AVAILABLE_PERMISSIONS,
        'roles': list(ROLES.keys())
    }

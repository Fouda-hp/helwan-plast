import anvil.users
import anvil.files
from anvil.files import data_files
"""
AuthManager.py - نظام المصادقة والتفويض الآمن (واجهة موحدة)
============================================================
يستورد الثوابت والدوال المساعدة من الوحدات المنفصلة ويُبقي كل الـ callables هنا.
"""

import anvil.server
from anvil.tables import app_tables
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import json
import uuid
import re
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== استيراد من الوحدات المنظمة ==========
from . import auth_constants
from .auth_constants import (
    MAX_LOGIN_ATTEMPTS, LOCKOUT_DURATION_MINUTES, SESSION_DURATION_MINUTES,
    MAX_SESSIONS_PER_USER, RATE_LIMIT_WINDOW_MINUTES, RATE_LIMIT_MAX_REQUESTS,
    PBKDF2_ITERATIONS, PASSWORD_HISTORY_COUNT, OTP_EXPIRY_MINUTES,
    ADMIN_NOTIFICATION_EMAIL, EMERGENCY_SECRET_KEY, ROLES, AVAILABLE_PERMISSIONS
)
from .auth_utils import get_utc_now, make_aware, get_client_ip, validate_email
from .auth_email import send_email_smtp, send_approval_email, EMAIL_SERVICE_AVAILABLE
from .auth_password import hash_password, verify_password, upgrade_password_hash, add_to_password_history, check_password_history
from .auth_sessions import generate_session_token, create_session, validate_session, destroy_session, cleanup_expired_sessions
from .auth_rate_limit import check_rate_limit
# استيراد مطلق متوافق مع Anvil (الوحدة قد لا تُحمّل كـ Helwan_Plast.auth_permissions)
try:
    from .auth_permissions import check_permission, is_admin, is_admin_by_email, require_admin, require_permission
except ImportError:
    from auth_permissions import check_permission, is_admin, is_admin_by_email, require_admin, require_permission
try:
    from . import auth_totp
except ImportError:
    import auth_totp

# =========================================================
# OTP Generation and Verification
# =========================================================
def generate_otp():
  """توليد رمز OTP من 6 أرقام"""
  return ''.join([str(secrets.randbelow(10)) for _ in range(6)])


def _get_global_otp_channel():
  """قناة OTP الافتراضية من الإعدادات (بدون اعتبار يوزر معين)"""
  try:
    s = app_tables.settings.get(setting_key='otp_channel')
    if s and s.get('setting_value'):
      ch = str(s['setting_value']).strip().lower()
      if ch in ('email', 'sms', 'whatsapp'):
        return ch
  except Exception as e:
    pass
  return 'email'


@anvil.server.callable
def get_otp_channel(user_email=None):
  """
  قراءة قناة إرسال OTP: إن وُجد user_email وله otp_method (email|sms|whatsapp) نستخدمها،
  وإلا القناة العامة من الإعدادات. authenticator لا يُستخدم هنا (يُعالج في تسجيل الدخول).
  """
  if user_email:
    user = app_tables.users.get(email=user_email)
    if user:
      um = (user.get('otp_method') or '').strip().lower()
      if um in ('email', 'sms', 'whatsapp'):
        return um
  return _get_global_otp_channel()


def send_otp_sms(phone_number, otp, purpose='verification'):
  """
  إرسال OTP عبر SMS (Twilio).
  يتطلب في Anvil Secrets: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
  """
  try:
    import anvil.http
    sid = anvil.secrets.get_secret('TWILIO_ACCOUNT_SID')
    token = anvil.secrets.get_secret('TWILIO_AUTH_TOKEN')
    from_num = anvil.secrets.get_secret('TWILIO_FROM_NUMBER')
    if not sid or not token or not from_num:
      logger.warning("Twilio secrets not set. OTP SMS skipped.")
      return False
    # تطبيع رقم الجوال (إضافة + إن لم يكن)
    to = str(phone_number).strip()
    if not to.startswith('+'):
      to = '+' + to
    body = f"Helwan Plast: Your verification code is {otp}. Valid for {OTP_EXPIRY_MINUTES} minutes."
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    import base64
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    anvil.http.request(
      url,
      method="POST",
      data={"To": to, "From": from_num, "Body": body},
      headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"}
    )
    logger.info(f"OTP SMS sent to {to}")
    return True
  except Exception as e:
    logger.error(f"Send OTP SMS error: {e}")
    return False


def send_otp(user_email, user_name, otp, purpose='verification', force_channel=None):
  """
  إرسال OTP عبر القناة: إن وُجد force_channel (مثلاً 'email') نستخدمها،
  وإلا قناة المستخدم أو القناة العامة.
  """
  if force_channel == 'email':
    return send_otp_email(user_email, user_name, otp, purpose)
  channel = get_otp_channel(user_email)
  if channel == 'sms':
    user = app_tables.users.get(email=user_email)
    phone = user.get('phone') if user else None
    if not phone or not str(phone).strip():
      logger.warning(f"No phone for {user_email}, falling back to email for OTP")
      return send_otp_email(user_email, user_name, otp, purpose)
    return send_otp_sms(phone, otp, purpose)
  if channel == 'whatsapp':
    # نفس SMS عبر Twilio WhatsApp (رقم From يبدأ بـ whatsapp:)
    user = app_tables.users.get(email=user_email)
    phone = user.get('phone') if user else None
    if not phone or not str(phone).strip():
      logger.warning(f"No phone for {user_email}, falling back to email for OTP")
      return send_otp_email(user_email, user_name, otp, purpose)
    try:
      import anvil.http
      sid = anvil.secrets.get_secret('TWILIO_ACCOUNT_SID')
      token = anvil.secrets.get_secret('TWILIO_AUTH_TOKEN')
      from_wa = anvil.secrets.get_secret('TWILIO_WHATSAPP_FROM')  # e.g. whatsapp:+14155238886
      if not sid or not token or not from_wa:
        return send_otp_email(user_email, user_name, otp, purpose)
      to = str(phone).strip()
      if not to.startswith('whatsapp:'):
        to = 'whatsapp:+' + to.lstrip('+')
      body = f"Helwan Plast: Your code is {otp}. Valid {OTP_EXPIRY_MINUTES} min."
      url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
      import base64
      auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
      anvil.http.request(
        url,
        method="POST",
        data={"To": to, "From": from_wa, "Body": body},
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"}
      )
      logger.info(f"OTP WhatsApp sent to {to}")
      return True
    except Exception as e:
      logger.error(f"WhatsApp OTP error: {e}")
      return send_otp_email(user_email, user_name, otp, purpose)
  # email (default)
  return send_otp_email(user_email, user_name, otp, purpose)


def send_otp_email(user_email, user_name, otp, purpose='verification'):
  """
    إرسال OTP عبر البريد الإلكتروني
    purpose: 'verification' | '2fa' | 'password_reset'
    """
  if not EMAIL_SERVICE_AVAILABLE:
    logger.warning("Email service not available. Skipping OTP email.")
    return False

  try:
    purposes = {
      'verification': {
        'subject': '🔐 Email Verification - Helwan Plast',
        'title': 'Email Verification',
        'message': 'Please use the following code to verify your email address:'
      },
      '2fa': {
        'subject': '🔐 Login Verification - Helwan Plast',
        'title': 'Two-Factor Authentication',
        'message': 'Please use the following code to complete your login:'
      },
      'password_reset': {
        'subject': '🔐 Password Reset - Helwan Plast',
        'title': 'Password Reset Request',
        'message': 'Please use the following code to reset your password:'
      }
    }

    p = purposes.get(purpose, purposes['verification'])

    html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0; text-align: center;">Helwan Plast System</h1>
            </div>

            <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                <h2 style="color: #1976d2; margin-top: 0;">{p['title']}</h2>

                <p style="font-size: 16px; color: #333;">Dear <strong>{user_name}</strong>,</p>

                <p style="font-size: 16px; color: #333;">{p['message']}</p>

                <div style="background: #e3f2fd; padding: 20px; border-radius: 10px; margin: 25px 0; text-align: center;">
                    <span style="font-size: 36px; font-weight: bold; letter-spacing: 8px; color: #1976d2;">{otp}</span>
                </div>

                <div style="background: #fff3e0; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0; font-size: 14px; color: #e65100;">
                        <strong>⚠️ Important:</strong> This code will expire in {OTP_EXPIRY_MINUTES} minutes. Do not share this code with anyone.
                    </p>
                </div>

                <p style="font-size: 14px; color: #666;">
                    If you did not request this code, please ignore this email.
                </p>

                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">

                <p style="font-size: 12px; color: #999; text-align: center;">
                    Best regards,<br>
                    <strong>Mohamed Adel - Helwan Plast System</strong>
                </p>
            </div>
        </div>
        """

    # استخدام SMTP بدلاً من Anvil Email
    result = send_email_smtp(user_email, p['subject'], html_body)

    if result:
      logger.info(f"OTP email sent to {user_email} for {purpose}")
      return True
    else:
      logger.error(f"Failed to send OTP email to {user_email}")
      return False

  except Exception as e:
    logger.error(f"Failed to send OTP email to {user_email}: {e}")
    return False


def store_otp(user_email, otp, purpose='verification'):
  """
    حفظ OTP في قاعدة البيانات
    """
  try:
    # حذف أي OTP قديم لنفس المستخدم والغرض
    old_otps = list(app_tables.otp_codes.search(user_email=user_email, purpose=purpose))
    for old in old_otps:
      old.delete()

      # إضافة OTP جديد (مُشفّر بـ SHA-256)
    otp_hash = hashlib.sha256(str(otp).encode('utf-8')).hexdigest()
    app_tables.otp_codes.add_row(
      otp_id=str(uuid.uuid4()),
      user_email=user_email,
      otp_code=otp_hash,
      purpose=purpose,
      created_at=datetime.now(),
      expires_at=datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES),
      is_used=False
    )
    return True
  except Exception as e:
    logger.error(f"Failed to store OTP: {e}")
    return False


def verify_otp(user_email, otp, purpose='verification'):
  """
    التحقق من صحة OTP
    """
  try:
    # البحث عن OTP باستخدام hash (SHA-256) للمقارنة
    otp_hash = hashlib.sha256(str(otp).encode('utf-8')).hexdigest()
    otp_records = list(app_tables.otp_codes.search(
      user_email=user_email,
      otp_code=otp_hash,
      purpose=purpose,
      is_used=False
    ))
    # Fallback: دعم OTP القديم (plaintext) خلال فترة الانتقال
    if not otp_records:
        otp_records = list(app_tables.otp_codes.search(
          user_email=user_email,
          otp_code=str(otp),
          purpose=purpose,
          is_used=False
        ))

    if not otp_records:
      return False, "Invalid or expired code"

    otp_record = otp_records[0]

    # التحقق من انتهاء الصلاحية
    expires_at = otp_record['expires_at']
    if expires_at:
      # تحويل التواريخ للمقارنة الصحيحة
      now = get_utc_now()
      expires_at = make_aware(expires_at)
      if now > expires_at:
        otp_record.delete()
        return False, "Code has expired"

        # تحديث كمستخدم
    otp_record.update(is_used=True)

    return True, "Code verified successfully"

  except Exception as e:
    logger.error(f"OTP verification error: {e}")
    return False, f"Verification failed: {str(e)}"


# =========================================================
# TOTP (Authenticator App) - طريقة مجانية 100% بدل الإيميل/SMS
# =========================================================
def _get_totp_secret_for_user(user):
  """قراءة أو توليد secret لـ TOTP (لا يحفظه)."""
  try:
    import pyotp
    secret = user.get('totp_secret')
    if secret:
      return secret
    return pyotp.random_base32()
  except Exception:
    return None


def verify_totp_for_user(user_email, token):
  """التحقق من كود TOTP (مُستدعى من AuthManager؛ التنفيذ في auth_totp)."""
  return auth_totp.verify_totp_for_user(user_email, token)


@anvil.server.callable
def user_has_totp_enabled(auth_token):
  """يرجع True إذا المستخدم الحالي فعّل تطبيق المصادقة."""
  res = validate_token(auth_token)
  if not res.get('valid'):
    return False
  user = app_tables.users.get(email=res['user']['email'])
  return bool(user and user.get('totp_secret'))


@anvil.server.callable
def setup_totp_start(auth_token):
  """بدء تفعيل تطبيق المصادقة (Authenticator). يتطلب تسجيل دخول."""
  if not auth_token or (isinstance(auth_token, str) and not auth_token.strip()):
    return {'success': False, 'message': 'NO_TOKEN'}
  res = validate_token(auth_token)
  if not res.get('valid'):
    return {'success': False, 'message': 'SESSION_EXPIRED'}
  user_email = res.get('user', {}).get('email')
  if not user_email:
    return {'success': False, 'message': 'User not found'}
  return auth_totp.setup_totp_start_impl(user_email)


@anvil.server.callable
def setup_totp_confirm(auth_token, code):
  """تأكيد تفعيل تطبيق المصادقة بالكود من التطبيق."""
  res = validate_token(auth_token)
  if not res.get('valid'):
    return {'success': False, 'message': 'Please log in first'}
  user_email = res.get('user', {}).get('email')
  if not user_email:
    return {'success': False, 'message': 'User not found'}
  return auth_totp.setup_totp_confirm_impl(user_email, code)


@anvil.server.callable
def disable_totp(user_email, auth_token):
  """إلغاء تفعيل تطبيق المصادقة (نفس المستخدم أو أدمن)."""
  user = app_tables.users.get(email=user_email)
  if not user:
    return {'success': False, 'message': 'User not found'}
  if require_admin(auth_token)[0]:
    user.update(totp_secret=None)
    return {'success': True, 'message': 'Authenticator disabled'}
  res = validate_token(auth_token)
  if res.get('valid') and res.get('user', {}).get('email') == user_email:
    user.update(totp_secret=None)
    return {'success': True, 'message': 'Authenticator disabled'}
  return {'success': False, 'message': 'Not authorized'}


def send_admin_notification_email(new_user_email, new_user_name, new_user_phone):
  """
    إرسال إيميل للأدمن عند تسجيل مستخدم جديد
    """
  if not EMAIL_SERVICE_AVAILABLE:
    logger.warning("Email service not available. Skipping admin notification.")
    return False

  try:
    subject = "🔔 New User Registration - Helwan Plast System"
    html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #ff9800 0%, #f57c00 100%); padding: 20px; border-radius: 10px 10px 0 0;">
                <h1 style="color: white; margin: 0; text-align: center;">🔔 New Registration Request</h1>
            </div>

            <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                <h2 style="color: #1976d2; margin-top: 0;">A new user is waiting for approval</h2>

                <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #1976d2;">
                    <p style="margin: 10px 0; font-size: 15px;"><strong>Name:</strong> {new_user_name}</p>
                    <p style="margin: 10px 0; font-size: 15px;"><strong>Email:</strong> {new_user_email}</p>
                    <p style="margin: 10px 0; font-size: 15px;"><strong>Phone:</strong> {new_user_phone or 'Not provided'}</p>
                    <p style="margin: 10px 0; font-size: 15px;"><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                </div>

                <div style="background: #fff3e0; padding: 15px; border-radius: 8px; margin: 20px 0;">
                    <p style="margin: 0; font-size: 14px; color: #e65100;">
                        <strong>⚠️ Action Required:</strong> Please log in to the Admin Panel to approve or reject this user.
                    </p>
                </div>

                <div style="text-align: center; margin-top: 25px;">
                    <a href="https://helwan-plast.anvil.app" style="display: inline-block; padding: 12px 30px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
                        Go to Admin Panel
                    </a>
                </div>

                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">

                <p style="font-size: 12px; color: #999; text-align: center;">
                    This is an automated notification from Helwan Plast System
                </p>
            </div>
        </div>
        """

    # استخدام SMTP بدلاً من Anvil Email
    result = send_email_smtp(ADMIN_NOTIFICATION_EMAIL, subject, html_body)

    if result:
      logger.info(f"Admin notification email sent for new user: {new_user_email}")
      return True
    else:
      logger.error(f"Failed to send admin notification email")
      return False

  except Exception as e:
    logger.error(f"Failed to send admin notification email: {e}")
    return False


# =========================================================
# Rate Limiting - check_rate_limit مستورد من auth_rate_limit
# =========================================================

@anvil.server.callable
def clear_rate_limits(token_or_email=None):
    """
    مسح كل سجلات Rate Limit - للاستخدام الإداري فقط
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error
    try:
        count = 0
        for record in app_tables.rate_limits.search():
            record.delete()
            count += 1
        logger.info(f"Cleared {count} rate limit records")
        return {'success': True, 'message': f'Cleared {count} records'}
    except Exception as e:
        logger.error(f"Error clearing rate limits: {e}")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def clear_my_rate_limit(token_or_email=None):
    """
    مسح Rate Limit للـ IP الحالي - يتطلب مصادقة
    """
    if token_or_email:
        session = validate_session(token_or_email)
        if not session:
            return {'success': False, 'message': 'Authentication required'}
    try:
        ip_address = get_client_ip()
        count = 0
        for record in app_tables.rate_limits.search(ip_address=ip_address):
            record.delete()
            count += 1
        logger.info(f"Cleared {count} rate limit records for IP: {ip_address}")
        return {'success': True, 'message': f'Rate limit cleared'}
    except Exception as e:
        logger.error(f"Error clearing rate limit: {e}")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def reset_user_login_attempts(email, token_or_email=None):
  """
  إعادة تعيين محاولات تسجيل الدخول للمستخدم - يتطلب صلاحية أدمن
  """
  is_authorized, error = require_admin(token_or_email)
  if not is_authorized:
    return error
  try:
    user = app_tables.users.get(email=email)
    if user:
      user.update(login_attempts=0, locked_until=None)
      return {'success': True, 'message': 'Login attempts reset'}
    return {'success': False, 'message': 'User not found'}
  except Exception as e:
    return {'success': False, 'message': str(e)}


# =========================================================
# تسجيل التدقيق (مفصل: اسم المستخدم + وصف العملية + التوقيت)
# =========================================================
def log_audit(action, table_name, record_id, old_data, new_data, user_email=None, ip_address=None, user_name=None, action_description=None):
  """تسجيل العملية في سجل التدقيق (الواجهة الموحدة - التنفيذ في auth_audit)."""
  from . import auth_audit
  auth_audit.log_audit(action, table_name, record_id, old_data, new_data,
                      user_email=user_email, ip_address=ip_address,
                      user_name=user_name, action_description=action_description)


# =========================================================
# الحصول على IP Address
# =========================================================
def get_client_ip():
  """
    الحصول على IP Address للعميل
    ملاحظة: anvil.server.request غير متاح في server callable functions
    لذلك نستخدم anvil.server.context للحصول على معلومات العميل
    """
  try:
    # محاولة الحصول على IP من call context
    context = anvil.server.context
    if hasattr(context, 'client') and context.client:
      client = context.client
      if hasattr(client, 'ip'):
        return client.ip or 'unknown'
    # إذا لم يتوفر، نرجع قيمة افتراضية
    return 'unknown'
  except Exception:
    return 'unknown'


# =========================================================
# تسجيل مستخدم جديد
# =========================================================
@anvil.server.callable
def register_user(email, password, full_name, phone=None):
    """
    تسجيل مستخدم جديد - الخطوة الأولى (إرسال OTP للتحقق من البريد)
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
        # إذا كان المستخدم موجود ولكن لم يتحقق من إيميله بعد
        if not existing.get('email_verified', True):
            # إعادة إرسال OTP (أول تسجيل = إيميل افتراضي)
            otp = generate_otp()
            store_otp(email, otp, 'verification')
            send_otp(email, full_name, otp, 'verification', force_channel='email')
        # رسالة موحدة لمنع User Enumeration
        return {
            'success': True,
            'requires_verification': True,
            'message': 'If this email is valid, a verification code has been sent'
        }

    # إنشاء المستخدم (غير مُتحقق منه)
    user_id = str(uuid.uuid4())
    password_hash_value = hash_password(password)

    try:
        app_tables.users.add_row(
            user_id=user_id,
            email=email,
            password_hash=password_hash_value,
            full_name=full_name,
            phone=phone,
            role='viewer',  # الدور الافتراضي
            is_approved=False,
            is_active=True,
            email_verified=False,  # غير مُتحقق من الإيميل بعد
            created_at=datetime.now(),
            login_attempts=0,
            custom_permissions=None
        )

        # إضافة كلمة المرور لسجل كلمات المرور
        add_to_password_history(email, password_hash_value)

        # إرسال OTP للتحقق من البريد (أول مرة تسجيل = إيميل افتراضي)
        otp = generate_otp()
        store_otp(email, otp, 'verification')
        email_sent = send_otp(email, full_name, otp, 'verification', force_channel='email')

        # تسجيل في Audit Log
        log_audit('REGISTER_PENDING', 'users', user_id, None,
                  {'email': email, 'full_name': full_name},
                  email, ip_address)

        logger.info(f"New user registration started: {email}")

        if email_sent:
            return {
                'success': True,
                'requires_verification': True,
                'message': 'Please check your email for verification code'
            }
        else:
            # في حالة فشل إرسال الإيميل، نُكمل التسجيل مباشرة
            return complete_registration_without_verification(email)

    except Exception as e:
        logger.error(f"Registration error: {e}")
        return {'success': False, 'message': 'Registration failed. Please try again.'}


@anvil.server.callable
def verify_registration_otp(email, otp):
    """
    التحقق من OTP وإتمام التسجيل
    """
    email = str(email or '').strip().lower()

    # التحقق من OTP
    is_valid, message = verify_otp(email, otp, 'verification')

    if not is_valid:
        return {'success': False, 'message': message}

    # تحديث المستخدم كمُتحقق منه
    user = app_tables.users.get(email=email)
    if not user:
        return {'success': False, 'message': 'User not found'}

    user.update(email_verified=True)

    ip_address = get_client_ip()

    # تسجيل في Audit Log
    log_audit('EMAIL_VERIFIED', 'users', user['user_id'], None,
              {'email': email}, email, ip_address)

    # إرسال إيميل للأدمن
    send_admin_notification_email(email, user['full_name'], user.get('phone'))

    logger.info(f"Email verified and registration completed: {email}")

    return {
        'success': True,
        'message': 'Email verified! Your registration is pending admin approval.'
    }


def complete_registration_without_verification(email):
    """
    إتمام التسجيل بدون التحقق من الإيميل (في حالة فشل إرسال الإيميل)
    """
    user = app_tables.users.get(email=email)
    if user:
        user.update(email_verified=True)
        send_admin_notification_email(email, user['full_name'], user.get('phone'))

    return {
        'success': True,
        'message': 'Registration successful! Please wait for admin approval.'
    }


@anvil.server.callable
def resend_verification_otp(email):
    """
    إعادة إرسال OTP للتحقق من البريد
    """
    ip_address = get_client_ip()

    if not check_rate_limit(ip_address, 'resend_otp'):
        return {'success': False, 'message': 'Too many requests. Please wait a few minutes.'}

    email = str(email or '').strip().lower()

    user = app_tables.users.get(email=email)
    if not user:
        return {'success': False, 'message': 'Email not found'}

    if user.get('email_verified', True):
        return {'success': False, 'message': 'Email already verified'}

    otp = generate_otp()
    store_otp(email, otp, 'verification')
    send_otp(email, user['full_name'], otp, 'verification', force_channel='email')

    return {'success': True, 'message': 'Verification code sent'}


# =========================================================
# تسجيل الدخول (مع Two-Factor Authentication)
# =========================================================
@anvil.server.callable
def login_user(email, password):
    """
    تسجيل دخول المستخدم - الخطوة الأولى
    يتحقق من البريد وكلمة المرور ثم يرسل OTP
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

    # التحقق من التحقق من الإيميل
    # المستخدمون الذين تمت الموافقة عليهم (is_approved=True) يُعتبرون مُتحققين تلقائياً
    email_verified = user.get('email_verified')
    if email_verified is None or (not email_verified and user.get('is_approved')):
        # المستخدم قديم أو معتمد - تحديث الحقل ليكون True
        user.update(email_verified=True)
        email_verified = True

    if not email_verified:
        return {'success': False, 'message': 'Please verify your email first'}

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

    # كلمة المرور صحيحة - ترقية الهاش إذا كان قديماً
    upgrade_password_hash(user, password)

    # إذا المستخدم مفعّل عنده تطبيق المصادقة (TOTP) - لا نرسل إيميل، نطلب كود من التطبيق فقط (مجاني)
    if user.get('totp_secret'):
        logger.info(f"2FA via Authenticator app for: {email}")
        return {
            'success': True,
            'requires_2fa': True,
            'use_authenticator': True,
            'message': 'Enter the 6-digit code from your authenticator app'
        }

    # أول دخول للمستخدم (لم يسجل دخول من قبل) = إرسال OTP بالإيميل افتراضياً
    first_login = user.get('last_login') is None
    force_email = first_login

    # إرسال OTP للتحقق الثنائي (إيميل أو SMS/WhatsApp حسب إعداد المستخدم أو العام)
    otp = generate_otp()
    store_otp(email, otp, '2fa')
    email_sent = send_otp(email, user['full_name'], otp, '2fa', force_channel='email' if force_email else None)

    if email_sent:
        logger.info(f"2FA OTP sent to: {email}")
        return {'success': True, 'requires_2fa': True, 'use_authenticator': False, 'message': 'Verification code sent to your email'}
    else:
        logger.error(f"Failed to send 2FA OTP to: {email}")
        return {'success': False, 'message': 'Failed to send verification code. Please try again later.'}


@anvil.server.callable
def verify_login_otp(email, otp):
    """
    التحقق من OTP أو كود تطبيق المصادقة وإتمام تسجيل الدخول
    """
    ip_address = get_client_ip()
    email = str(email or '').strip().lower()
    user = app_tables.users.get(email=email)
    if not user:
        return {'success': False, 'message': 'User not found'}

    # إذا المستخدم مفعّل عنده تطبيق المصادقة (TOTP) نتحقق من الكود من التطبيق
    if user.get('totp_secret'):
        if verify_totp_for_user(email, otp):
            return complete_login(user, ip_address)
        # فشل أول محاولة: إرسال كود جديد على الإيميل والمحاولة التالية تكون بالإيميل
        otp_new = generate_otp()
        store_otp(email, otp_new, '2fa')
        send_otp_email(email, user['full_name'], otp_new, '2fa')
        return {
            'success': False,
            'fallback_to_email': True,
            'message': 'Invalid or expired code. A new code was sent to your email. Please check your email and try again.'
        }

    # التحقق من OTP المرسل (إيميل/SMS)
    is_valid, message = verify_otp(email, otp, '2fa')
    if not is_valid:
        # فشل أول محاولة: إرسال كود جديد على الإيميل والمحاولة التالية تكون بالإيميل
        otp_new = generate_otp()
        store_otp(email, otp_new, '2fa')
        send_otp_email(email, user['full_name'], otp_new, '2fa')
        return {
            'success': False,
            'fallback_to_email': True,
            'message': 'Invalid or expired code. A new code was sent to your email. Please check your email and try again.'
        }

    return complete_login(user, ip_address)


def complete_login(user, ip_address):
    """
    إتمام تسجيل الدخول بعد التحقق من 2FA
    """
    email = user['email']

    # نجاح تسجيل الدخول
    user.update(
        login_attempts=0,
        locked_until=None,
        last_login=datetime.now()
    )

    # ملاحظة: ترقية كلمة المرور من التشفير القديم تتم تلقائياً عند التحقق من كلمة المرور
    # في دالة login_user بعد verify_password الناجح
    # لا يمكن الترقية هنا لأننا لا نملك كلمة المرور الأصلية

    # حذف جميع الجلسات القديمة لهذا المستخدم
    for old_session in app_tables.sessions.search(user_email=email):
        old_session.delete()

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


@anvil.server.callable
def resend_login_otp(email):
    """
    إعادة إرسال OTP لتسجيل الدخول
    """
    ip_address = get_client_ip()

    if not check_rate_limit(ip_address, 'resend_otp'):
        return {'success': False, 'message': 'Too many requests. Please wait a few minutes.'}

    email = str(email or '').strip().lower()

    user = app_tables.users.get(email=email)
    if not user:
        return {'success': False, 'message': 'Email not found'}

    otp = generate_otp()
    store_otp(email, otp, '2fa')
    send_otp(email, user['full_name'], otp, '2fa')

    return {'success': True, 'message': 'Verification code sent'}


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

    # تمديد الجلسة عند كل استخدام (sliding expiration) حتى لا تنتهي أثناء الاستخدام
    try:
        from .auth_sessions import _hash_token
        token_hash = _hash_token(token)
        session_row = app_tables.sessions.get(session_token=token_hash, is_active=True)
        # Fallback: دعم التوكنات القديمة (بدون hash)
        if not session_row:
            session_row = app_tables.sessions.get(session_token=token, is_active=True)
        if session_row:
            session_row.update(expires_at=datetime.now() + timedelta(minutes=SESSION_DURATION_MINUTES))
    except Exception as e:
        pass

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
# وظائف الأدمن (الصلاحيات من auth_permissions)
# =========================================================
@anvil.server.callable
def debug_admin_check(token_or_email):
    """
    Debug function to check admin access - للتشخيص (يتطلب صلاحية أدمن)
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return {'success': False, 'message': 'Admin access required'}

    result = {
        'token_received': token_or_email[:50] if token_or_email else 'None',
        'session_valid': False,
        'user_found': False,
        'is_admin_result': True
    }

    session = validate_session(token_or_email)
    if session:
        result['session_valid'] = True

    if token_or_email and '@' in str(token_or_email):
        user = app_tables.users.get(email=str(token_or_email).lower())
        if user:
            result['user_found'] = True

    return result


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

    user_email = user['email']
    user_name = user['full_name']

    user.update(
        is_approved=True,
        role=role,
        custom_permissions=permissions_json,
        approved_by=admin_email,
        approved_at=datetime.now()
    )

    log_audit('APPROVE_USER', 'users', user_id, None, {
        'email': user_email,
        'role': role,
        'custom_permissions': permissions_json,
        'approved_by': admin_email
    }, admin_email, ip_address)

    logger.info(f"User approved: {user_email} with role {role}")

    try:
        try:
            from . import notifications as notif_mod
        except ImportError:
            import notifications as notif_mod
        notif_mod.create_notification(user_email, 'user_approved', {'role': role, 'approved_by': admin_email})
    except Exception:
        pass

    # إرسال إيميل للمستخدم
    email_sent = send_approval_email(user_email, user_name, role, approved=True)

    return {
        'success': True,
        'message': 'User approved successfully' + (' (email sent)' if email_sent else ' (email notification failed)')
    }


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

    user_email = user['email']
    user_name = user['full_name']
    admin_email = token_or_email if '@' in str(token_or_email) else 'admin'

    try:
        try:
            from . import notifications as notif_mod
        except ImportError:
            import notifications as notif_mod
        notif_mod.create_notification(user_email, 'user_rejected', {'rejected_by': admin_email})
    except Exception:
        pass

    # إرسال إيميل للمستخدم قبل الحذف
    email_sent = send_approval_email(user_email, user_name, '', approved=False)

    user.delete()

    log_audit('REJECT_USER', 'users', user_id, None, {
        'email': user_email,
        'rejected_by': admin_email
    }, admin_email, ip_address)

    logger.info(f"User rejected: {user_email}")

    return {
        'success': True,
        'message': 'User rejected' + (' (email sent)' if email_sent else ' (email notification failed)')
    }


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
            'last_login': user['last_login'].isoformat() if user['last_login'] else 'Never',
            'otp_method': (user.get('otp_method') or '').strip().lower() or ''
        })

    return {'success': True, 'users': users}


@anvil.server.callable
def update_user_otp_method(token_or_email, user_email, method):
    """
    تحديث طريقة OTP للمستخدم (للأدمن فقط).
    method: '' (افتراضي/عام) | 'email' | 'sms' | 'whatsapp' | 'authenticator'
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error
    method = (method or '').strip().lower()
    if method and method not in ('email', 'sms', 'whatsapp', 'authenticator'):
        return {'success': False, 'message': 'Invalid OTP method'}
    user = app_tables.users.get(email=user_email)
    if not user:
        return {'success': False, 'message': 'User not found'}
    user.update(otp_method=method if method else None)
    return {'success': True, 'message': 'OTP method updated'}


@anvil.server.callable
def get_active_users_for_dropdown(token_or_email=None):
    """
    الحصول على أسماء المستخدمين النشطين فقط لاستخدامها في dropdown
    يتطلب مستخدم مسجل دخول
    """
    if not token_or_email:
        return {'success': False, 'message': 'Authentication required', 'users': []}

    # التحقق من أن المستخدم مسجل دخول
    result = validate_token(token_or_email) if not ('@' in str(token_or_email)) else None
    if result and not result.get('valid'):
        return {'success': False, 'message': 'Invalid session', 'users': []}
    elif not result and '@' in str(token_or_email):
        user_check = app_tables.users.get(email=str(token_or_email).strip().lower())
        if not user_check or not user_check.get('is_active') or not user_check.get('is_approved'):
            return {'success': False, 'message': 'Invalid user', 'users': []}

    try:
        users = []
        for user in app_tables.users.search(is_active=True, is_approved=True):
            full_name = user.get('full_name', '').strip()
            if full_name:
                users.append({
                    'name': full_name,
                    'email': user['email']
                })
        
        # Sort by name
        users.sort(key=lambda x: x['name'])
        return {'success': True, 'users': users}
    except Exception as e:
        logger.error(f"Error getting active users: {e}")
        return {'success': False, 'message': str(e), 'users': []}


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
def request_password_change(token, old_password, new_password):
    """
    طلب تغيير كلمة المرور - الخطوة الأولى (إرسال OTP)
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

    # التحقق من قوة كلمة المرور
    if not re.search(r'[A-Z]', new_password):
        return {'success': False, 'message': 'Password must contain at least one uppercase letter'}

    if not re.search(r'[a-z]', new_password):
        return {'success': False, 'message': 'Password must contain at least one lowercase letter'}

    if not re.search(r'\d', new_password):
        return {'success': False, 'message': 'Password must contain at least one number'}

    # التحقق من سجل كلمات المرور
    is_valid, message = check_password_history(user['email'], new_password)
    if not is_valid:
        return {'success': False, 'message': message}

    # حفظ كلمة المرور الجديدة مؤقتاً
    store_pending_password(user['email'], hash_password(new_password))

    # إرسال OTP للتحقق
    otp = generate_otp()
    store_otp(user['email'], otp, 'password_change')
    email_sent = send_otp(user['email'], user['full_name'], otp, 'password_reset')

    if email_sent:
        return {
            'success': True,
            'requires_verification': True,
            'message': 'Verification code sent to your email'
        }
    else:
        # في حالة فشل إرسال الإيميل، نُكمل التغيير مباشرة
        return complete_password_change(user['email'])


def store_pending_password(email, password_hash):
    """
    حفظ كلمة المرور الجديدة مؤقتاً حتى التحقق من OTP
    """
    try:
        # حذف أي كلمة مرور معلقة سابقة
        old_pending = list(app_tables.pending_passwords.search(user_email=email))
        for old in old_pending:
            old.delete()

        # حفظ كلمة المرور الجديدة
        app_tables.pending_passwords.add_row(
            pending_id=str(uuid.uuid4()),
            user_email=email,
            new_password_hash=password_hash,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)
        )
        return True
    except Exception as e:
        logger.error(f"Failed to store pending password: {e}")
        return False


@anvil.server.callable
def verify_password_change_otp(email, otp):
    """
    التحقق من OTP وإتمام تغيير كلمة المرور
    """
    email = str(email or '').strip().lower()

    # التحقق من OTP
    is_valid, message = verify_otp(email, otp, 'password_change')

    if not is_valid:
        return {'success': False, 'message': message}

    return complete_password_change(email)


def complete_password_change(email):
    """
    إتمام تغيير كلمة المرور بعد التحقق من OTP
    """
    ip_address = get_client_ip()

    user = app_tables.users.get(email=email)
    if not user:
        return {'success': False, 'message': 'User not found'}

    # الحصول على كلمة المرور الجديدة المعلقة
    pending = app_tables.pending_passwords.get(user_email=email)
    if not pending:
        return {'success': False, 'message': 'No pending password change found'}

    # التحقق من انتهاء الصلاحية
    if datetime.now() > pending['expires_at']:
        pending.delete()
        return {'success': False, 'message': 'Password change request has expired'}

    new_password_hash = pending['new_password_hash']

    # تحديث كلمة المرور
    user.update(password_hash=new_password_hash)

    # إضافة إلى سجل كلمات المرور
    add_to_password_history(email, new_password_hash)

    # حذف كلمة المرور المعلقة
    pending.delete()

    # إنهاء جميع الجلسات القديمة (إجبار إعادة تسجيل الدخول)
    for session in app_tables.sessions.search(user_email=email):
        session.update(is_active=False)

    log_audit('CHANGE_PASSWORD', 'users', user['user_id'], None,
              {'email': email}, email, ip_address)

    return {'success': True, 'message': 'Password changed successfully. Please login again.'}


@anvil.server.callable
def change_own_password(token, old_password, new_password):
    """
    تغيير كلمة المرور الخاصة (للتوافق مع الإصدارات القديمة)
    يُعيد التوجيه إلى request_password_change
    """
    return request_password_change(token, old_password, new_password)


# =========================================================
# إعادة تعيين كلمة المرور (Forgot Password)
# =========================================================
@anvil.server.callable
def request_password_reset(email):
    """
    طلب إعادة تعيين كلمة المرور - إرسال OTP للمستخدم
    """
    ip_address = get_client_ip()

    # التحقق من Rate Limit
    if not check_rate_limit(ip_address, 'password_reset'):
        return {'success': False, 'message': 'Too many requests. Please try again later.'}

    email = str(email or '').strip().lower()

    if not validate_email(email):
        return {'success': False, 'message': 'Invalid email address'}

    # البحث عن المستخدم
    user = app_tables.users.get(email=email)

    if not user:
        # لا نكشف أن البريد غير موجود (للأمان)
        return {'success': False, 'message': 'If this email exists, a verification code will be sent.'}

    # التحقق من أن الحساب نشط
    if not user['is_active']:
        return {'success': False, 'message': 'Account is deactivated. Contact admin.'}

    # إرسال OTP للمستخدم
    otp = generate_otp()
    store_otp(email, otp, 'password_reset')
    email_sent = send_otp(email, user['full_name'], otp, 'password_reset')

    if email_sent:
        logger.info(f"Password reset OTP sent to: {email}")
        return {
            'success': True,
            'message': 'Verification code sent to your email'
        }
    else:
        return {
            'success': False,
            'message': 'Failed to send verification code. Please try again.'
        }


@anvil.server.callable
def verify_password_reset_otp(email, otp):
    """
    التحقق من OTP لإعادة تعيين كلمة المرور
    """
    email = str(email or '').strip().lower()

    # التحقق من OTP
    is_valid, message = verify_otp(email, otp, 'password_reset')

    if not is_valid:
        return {'success': False, 'message': message}

    # OTP صحيح - السماح بتعيين كلمة مرور جديدة
    # نحفظ علامة تسمح بإعادة تعيين كلمة المرور
    store_otp(email, 'VERIFIED_RESET', 'password_reset_verified')

    return {
        'success': True,
        'message': 'Code verified successfully'
    }


@anvil.server.callable
def complete_password_reset(email, new_password):
    """
    إتمام إعادة تعيين كلمة المرور بعد التحقق من OTP
    """
    ip_address = get_client_ip()
    email = str(email or '').strip().lower()

    # التحقق من أن المستخدم تحقق من OTP
    verified_records = list(app_tables.otp_codes.search(
        user_email=email,
        purpose='password_reset_verified',
        is_used=False
    ))

    if not verified_records:
        return {'success': False, 'message': 'Please verify your email first'}

    # حذف سجل التحقق
    for record in verified_records:
        record.delete()

    # التحقق من كلمة المرور الجديدة
    if not new_password or len(new_password) < 8:
        return {'success': False, 'message': 'Password must be at least 8 characters'}

    # التحقق من قوة كلمة المرور
    if not re.search(r'[A-Z]', new_password):
        return {'success': False, 'message': 'Password must contain at least one uppercase letter'}

    if not re.search(r'[a-z]', new_password):
        return {'success': False, 'message': 'Password must contain at least one lowercase letter'}

    if not re.search(r'\d', new_password):
        return {'success': False, 'message': 'Password must contain at least one number'}

    # البحث عن المستخدم
    user = app_tables.users.get(email=email)
    if not user:
        return {'success': False, 'message': 'User not found'}

    # التحقق من سجل كلمات المرور
    is_valid, message = check_password_history(email, new_password)
    if not is_valid:
        return {'success': False, 'message': message}

    # تحديث كلمة المرور
    new_hash = hash_password(new_password)
    user.update(
        password_hash=new_hash,
        login_attempts=0,
        locked_until=None
    )

    # إضافة إلى سجل كلمات المرور
    add_to_password_history(email, new_hash)

    # إنهاء جميع الجلسات القديمة
    for session in app_tables.sessions.search(user_email=email):
        session.update(is_active=False)

    log_audit('PASSWORD_RESET', 'users', user['user_id'], None,
              {'email': email}, email, ip_address)

    logger.info(f"Password reset completed for: {email}")

    return {
        'success': True,
        'message': 'Password reset successfully! Please login with your new password.'
    }


# =========================================================
# إعداد الأدمن الأول
# =========================================================
@anvil.server.callable
def check_admin_exists():
    """
    التحقق من وجود أدمن
    """
    try:
        # استخدام search بدلاً من get لتجنب خطأ "More than one row"
        existing_admins = list(app_tables.users.search(role='admin'))
        return {'exists': len(existing_admins) > 0}
    except Exception as e:
        logger.error(f"Error checking admin exists: {e}")
        return {'exists': False}


@anvil.server.callable
def diagnose_admin_access(email, token=None):
    """
    تشخيص مشكلة صلاحيات الأدمن - يتطلب صلاحية أدمن
    تُرجع معلومات مفصلة للتصحيح
    """
    is_authorized, error = require_admin(token)
    if not is_authorized:
        return error if isinstance(error, dict) else {'success': False, 'message': 'Admin access required'}
    result = {
        'email_check': None,
        'user_found': False,
        'user_details': None,
        'session_check': None,
        'is_admin_check': False,
        'recommendations': []
    }

    # التحقق من المستخدم بالبريد
    if email:
        user = app_tables.users.get(email=email.lower())
        if user:
            result['user_found'] = True
            result['user_details'] = {
                'email': user['email'],
                'role': user['role'],
                'is_active': user['is_active'],
                'is_approved': user['is_approved']
            }

            # التحقق من المشاكل
            if user['role'] != 'admin':
                result['recommendations'].append(f"User role is '{user['role']}', not 'admin'")
            if not user['is_active']:
                result['recommendations'].append("User is NOT active")
            if not user['is_approved']:
                result['recommendations'].append("User is NOT approved")

            # التحقق النهائي
            result['is_admin_check'] = (
                user['role'] == 'admin' and
                user['is_active'] and
                user['is_approved']
            )
        else:
            result['recommendations'].append(f"No user found with email: {email}")

    # التحقق من الـ token
    if token:
        session = validate_session(token)
        if session:
            result['session_check'] = {
                'valid': True,
                'email': session.get('email'),
                'role': session.get('role'),
                'expires': str(session.get('expires'))
            }
        else:
            result['session_check'] = {'valid': False}
            result['recommendations'].append("Session token is invalid or expired")

    return result


@anvil.server.callable
def fix_admin_user(email, secret_key):
    """
    إصلاح حساب الأدمن - تأكيد أنه is_active و is_approved
    يتطلب مفتاح سري من Anvil Secrets (لا يعمل بدون إعداده)
    """
    ip_address = get_client_ip()

    # التحقق من أن المفتاح مُعَد أصلاً
    if not EMERGENCY_SECRET_KEY:
        logger.critical(f"fix_admin_user called but EMERGENCY_KEY not configured. IP: {ip_address}")
        return {'success': False, 'message': 'Emergency access is disabled. Set EMERGENCY_KEY in Anvil Secrets.'}

    # Rate Limiting لمنع Brute Force
    if not check_rate_limit(ip_address, 'emergency_admin'):
        logger.warning(f"Rate limit exceeded on fix_admin_user from IP: {ip_address}")
        return {'success': False, 'message': 'Too many attempts. Please try again later.'}

    if secret_key != EMERGENCY_SECRET_KEY:
        log_audit('FAILED_EMERGENCY_FIX', 'users', None, None,
                  {'email': email, 'reason': 'Invalid secret key'}, email or 'unknown', ip_address)
        return {'success': False, 'message': 'Invalid secret key'}

    email = str(email or '').strip().lower()
    user = app_tables.users.get(email=email)

    if not user:
        return {'success': False, 'message': 'User not found'}

    if user['role'] != 'admin':
        return {'success': False, 'message': 'This user is not an admin'}

    # إصلاح الحساب
    user.update(
        is_active=True,
        is_approved=True,
        email_verified=True,
        login_attempts=0,
        locked_until=None
    )

    logger.info(f"Admin user fixed: {email}")
    return {
        'success': True,
        'message': 'Admin user fixed successfully',
        'user': {
            'email': user['email'],
            'role': user['role'],
            'is_active': user['is_active'],
            'is_approved': user['is_approved']
        }
    }


@anvil.server.callable
def reset_admin_password_emergency(email, new_password, secret_key):
    """
    إعادة تعيين كلمة مرور الأدمن (للطوارئ فقط)
    تتطلب مفتاح سري من Anvil Secrets (لا يعمل بدون إعداده)

    إذا لم يكن المستخدم موجوداً، سيتم إنشاء حساب أدمن جديد
    """
    ip_address = get_client_ip()

    try:
        # التحقق من أن المفتاح مُعَد أصلاً
        if not EMERGENCY_SECRET_KEY:
            logger.critical(f"reset_admin_password_emergency called but EMERGENCY_KEY not configured. IP: {ip_address}")
            return {'success': False, 'message': 'Emergency access is disabled. Set EMERGENCY_KEY in Anvil Secrets.'}

        # Rate Limiting لمنع Brute Force
        if not check_rate_limit(ip_address, 'emergency_admin'):
            logger.warning(f"Rate limit exceeded on emergency reset from IP: {ip_address}")
            return {'success': False, 'message': 'Too many attempts. Please try again later.'}

        # التحقق من المفتاح السري
        if secret_key != EMERGENCY_SECRET_KEY:
            log_audit('FAILED_EMERGENCY_RESET', 'users', None, None,
                      {'email': email, 'reason': 'Invalid secret key'}, email, ip_address)
            return {'success': False, 'message': 'Invalid secret key'}

        # التحقق من كلمة المرور الجديدة (نفس متطلبات التسجيل العادي)
        if not new_password or len(new_password) < 8:
            return {'success': False, 'message': 'Password must be at least 8 characters'}
        if not re.search(r'[A-Z]', new_password):
            return {'success': False, 'message': 'Password must contain at least one uppercase letter'}
        if not re.search(r'[a-z]', new_password):
            return {'success': False, 'message': 'Password must contain at least one lowercase letter'}
        if not re.search(r'[0-9]', new_password):
            return {'success': False, 'message': 'Password must contain at least one digit'}

        email = str(email or '').strip().lower()

        if not validate_email(email):
            return {'success': False, 'message': 'Invalid email address format'}

        # البحث عن المستخدم
        user = app_tables.users.get(email=email)

        if not user:
            # إذا لم يكن المستخدم موجوداً، أنشئ حساب أدمن جديد
            user_id = str(uuid.uuid4())

            app_tables.users.add_row(
                user_id=user_id,
                email=email,
                password_hash=hash_password(new_password),
                full_name='Administrator',
                phone=None,
                role='admin',
                is_approved=True,
                is_active=True,
                created_at=datetime.now(),
                login_attempts=0,
                custom_permissions=None
            )

            # إنشاء الإعدادات الافتراضية
            _initialize_default_settings()

            log_audit('EMERGENCY_ADMIN_CREATED', 'users', user_id, None,
                      {'email': email}, email, ip_address)

            logger.info(f"Emergency admin created: {email}")

            return {'success': True, 'message': 'Admin account created successfully. You can now login.'}

        # تحديث المستخدم الموجود ليكون أدمن (مع كلمة المرور الجديدة)
        old_role = user['role']
        user.update(
            password_hash=hash_password(new_password),
            role='admin',  # ترقية لأدمن
            login_attempts=0,
            locked_until=None,
            is_active=True,
            is_approved=True
        )

        # إنشاء الإعدادات الافتراضية إذا لم تكن موجودة
        _initialize_default_settings()

        log_audit('EMERGENCY_ADMIN_UPGRADE', 'users', user['user_id'], None,
                  {'email': email, 'old_role': old_role}, email, ip_address)

        logger.info(f"Emergency admin upgrade/reset for: {email} (was: {old_role})")

        return {'success': True, 'message': 'Account upgraded to admin successfully. You can now login.'}

    except Exception as e:
        logger.error(f"Emergency password reset error: {e}")
        return {'success': False, 'message': f'Error: {str(e)}'}


@anvil.server.callable
def setup_initial_admin(email, password, full_name, phone=None):
    """
    إنشاء أول حساب أدمن (يعمل فقط إذا لم يكن هناك أدمن)
    """
    ip_address = get_client_ip()

    try:
        # التحقق من عدم وجود أدمن
        existing_admins = list(app_tables.users.search(role='admin'))
        if existing_admins:
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
    الحصول على جميع الإعدادات كـ dictionary
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error

    settings = {}
    for setting in app_tables.settings.search():
        key = setting['setting_key']
        value = setting['setting_value']
        setting_type = setting.get('setting_type', 'text')
        
        # تحويل القيمة حسب النوع
        if setting_type == 'number':
            try:
                value = float(value)
            except (ValueError, TypeError):
                pass
        elif setting_type == 'json':
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                pass
        elif setting_type == 'bool':
            value = str(value).lower() in ('true', '1', 'yes')
        
        settings[key] = value

    return {'success': True, 'settings': settings}


@anvil.server.callable
def update_setting(token_or_email, key, value):
    """
    تحديث أو إنشاء إعداد معين (upsert)
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error

    ip_address = get_client_ip()
    admin_email = token_or_email if '@' in str(token_or_email) else 'admin'

    setting = app_tables.settings.get(setting_key=key)

    if not setting:
        # إنشاء الإعداد إذا لم يكن موجوداً
        sv = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        stype = 'json' if isinstance(value, (dict, list)) else 'text'
        app_tables.settings.add_row(
            setting_key=key,
            setting_value=sv,
            setting_type=stype,
            description=f'Auto-created setting: {key}',
            updated_by=admin_email,
            updated_at=datetime.now()
        )
        log_audit('CREATE_SETTING', 'settings', key,
                  None,
                  {'value': value, 'created_by': admin_email},
                  admin_email, ip_address)
        return {'success': True, 'message': 'Setting created successfully'}

    old_value = setting['setting_value']
    new_value = value
    if setting.get('setting_type') == 'json' and isinstance(value, (dict, list)):
        new_value = json.dumps(value)
    else:
        new_value = str(value)

    setting.update(
        setting_value=new_value,
        updated_by=admin_email,
        updated_at=datetime.now()
    )

    log_audit('UPDATE_SETTING', 'settings', key,
              {'value': old_value},
              {'value': value, 'updated_by': admin_email},
              admin_email, ip_address)

    return {'success': True, 'message': 'Setting updated successfully'}


@anvil.server.callable
def get_setting(key, token_or_email=None):
    """
    الحصول على قيمة إعداد معين - يتطلب مصادقة
    """
    if token_or_email:
        session = validate_session(token_or_email)
        if not session:
            return None
    setting = app_tables.settings.get(setting_key=key)

    if not setting:
        return None

    value = setting['setting_value']
    setting_type = setting['setting_type']

    # تحويل القيمة حسب النوع
    if setting_type == 'number':
        try:
            return float(value)
        except (ValueError, TypeError):
            return value
    elif setting_type == 'json':
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    elif setting_type == 'bool':
        return value.lower() in ('true', '1', 'yes')

    return value


@anvil.server.callable
def get_calculator_settings(token_or_email=None):
    """
    جلب كل إعدادات الكالكتور في استدعاء واحد.
    متاحة لأدوار: admin و manager فقط.
    """
    if not token_or_email:
        return {'success': False, 'message': 'المصادقة مطلوبة. يرجى تسجيل الدخول.'}
    session = validate_session(token_or_email)
    user_email = None
    if session and session.get('email'):
        user_email = session['email']
    elif token_or_email and '@' in str(token_or_email):
        u = app_tables.users.get(email=str(token_or_email).strip().lower())
        if u and u.get('is_active') and u.get('is_approved'):
            user_email = u['email']
    if not user_email:
        return {'success': False, 'message': 'جلسة غير صالحة أو منتهية. يرجى تسجيل الدخول مرة أخرى.'}
    user_row = app_tables.users.get(email=user_email)
    if not user_row:
        return {'success': False, 'message': 'المستخدم غير موجود.'}
    role = (user_row.get('role') or '').strip().lower()
    if role not in ('admin', 'manager'):
        return {'success': False, 'message': 'صلاحية غير كافية: يتطلب دور مدير نظام أو مدير للوصول إلى إعدادات الحاسبة.'}
    result = {
        'exchangeRate': None,
        'shipping_sea': None,
        'ths_cost': None,
        'clearance_expenses': None,
        'tax_rate': None,
        'bank_commission': None,
        'config': None,
        'priceOptions': None,
        'cylinderPrices': None
    }
    try:
        result['exchangeRate'] = get_setting('exchange_rate')
        result['shipping_sea'] = get_setting('shipping_sea')
        result['ths_cost'] = get_setting('ths_cost')
        result['clearance_expenses'] = get_setting('clearance_expenses')
        result['tax_rate'] = get_setting('tax_rate')
        result['bank_commission'] = get_setting('bank_commission')
        cfg = get_machine_config()
        if cfg and cfg.get('success') and cfg.get('config'):
            result['config'] = cfg['config']
        pr = get_machine_prices()
        if pr:
            if pr.get('options'):
                result['priceOptions'] = pr['options']
                logger.info("get_calculator_settings: priceOptions types=%s", pr['options'].get('types'))
                logger.info("get_calculator_settings: priceOptions typeColorWidths=%s",
                           {t: {c: ws for c, ws in cv.items()} for t, cv in (pr['options'].get('typeColorWidths') or {}).items()})
            else:
                logger.warning("get_calculator_settings: NO priceOptions returned from get_machine_prices")
            if pr.get('prices'):
                result['machinePrices'] = pr['prices']
                # Log the widths available for each type/color
                for mtype, by_color in pr['prices'].items():
                    if isinstance(by_color, dict):
                        for color, by_width in by_color.items():
                            if isinstance(by_width, dict):
                                logger.info("get_calculator_settings: prices[%s][%s] widths=%s", mtype, color, list(by_width.keys()))
            else:
                logger.warning("get_calculator_settings: NO prices returned from get_machine_prices")
        cp = get_setting('cylinder_prices')
        if cp and isinstance(cp, dict):
            result['cylinderPrices'] = cp
        result['success'] = True
        return result
    except Exception as e:
        logger.error(f"get_calculator_settings error: {e}")
        result['success'] = False
        result['message'] = str(e)
        return result


def _normalize_prices_keys(prices):
    """تطبيع مفاتيح الأسعار إلى نص (لضمان توافق مع الكالكتور). البنية: type -> color -> width -> price."""
    if not prices or not isinstance(prices, dict):
        return prices
    out = {}
    for mtype, by_color in prices.items():
        if not isinstance(by_color, dict):
            out[str(mtype)] = by_color
            continue
        out[str(mtype)] = {}
        for color, by_width in by_color.items():
            if not isinstance(by_width, dict):
                out[str(mtype)][str(color)] = by_width
                continue
            out[str(mtype)][str(color)] = {
                str(w): (float(p) if p is not None else 0) for w, p in by_width.items()
            }
    return out


def _options_from_machine_prices(prices):
    """
    استخراج الخيارات المتاحة للكالكتور من جدول الأسعار (فقط المقاسات ذات سعر > 0).
    يرجع: types, typeColors[type], typeColorWidths[type][color] — كل المفاتيح نصوص.
    """
    if not prices or not isinstance(prices, dict):
        return {'types': [], 'typeColors': {}, 'typeColorWidths': {}}
    types = []
    type_colors = {}
    type_color_widths = {}
    for mtype, by_color in prices.items():
        if not by_color or not isinstance(by_color, dict):
            continue
        mtype_str = str(mtype)
        colors_with_price = []
        type_color_widths[mtype_str] = {}
        for color, by_width in by_color.items():
            if not by_width or not isinstance(by_width, dict):
                continue
            widths_with_price = [str(w) for w, p in by_width.items() if p is not None and float(p) > 0]
            if widths_with_price:
                color_str = str(color)
                colors_with_price.append(color_str)
                type_color_widths[mtype_str][color_str] = sorted(widths_with_price, key=lambda x: int(x) if str(x).isdigit() else 0)
        if colors_with_price:
            types.append(mtype_str)
            type_colors[mtype_str] = sorted(colors_with_price, key=lambda x: int(x) if str(x).isdigit() else 0)
    return {'types': types, 'typeColors': type_colors, 'typeColorWidths': type_color_widths}


@anvil.server.callable
def get_machine_prices(token_or_email=None):
    """
    المصدر الأساسي لجميع أسعار المكن. يرجع الأسعار + خيارات الدروب داون (فقط مقاسات سعرها > 0).
    يتطلب مصادقة اختيارية.
    """
    if token_or_email:
        session = validate_session(token_or_email)
        if not session:
            return {'prices': {}, 'priceOptions': {}}
    default_prices = {
        "Metal anilox": {
            "4": {"80": 15000, "100": 16000, "120": 17500},
            "6": {"80": 25000, "100": 26000, "120": 29000},
            "8": {"80": 29000, "100": 32000, "120": 33000}
        },
        "Ceramic anilox Single Doctor Blade": {
            "4": {"80": 18000, "100": 19000, "120": 20500},
            "6": {"80": 28000, "100": 29000, "120": 32000},
            "8": {"80": 32000, "100": 35000, "120": 36000}
        },
        "Ceramic anilox Chamber Doctor Blade": {
            "4": {"80": 21168, "100": 22960, "120": 25252},
            "6": {"80": 32752, "100": 34940, "120": 39128},
            "8": {"80": 38336, "100": 42920, "120": 45504}
        }
    }
    try:
        setting = app_tables.settings.get(setting_key='machine_prices')
        if setting and setting['setting_value']:
            try:
                prices = json.loads(setting['setting_value'])
                logger.info("get_machine_prices: loaded from DB (setting_key='machine_prices'), types=%s", list(prices.keys()) if isinstance(prices, dict) else 'not dict')
            except json.JSONDecodeError:
                logger.warning("get_machine_prices: DB JSON parse error, using defaults")
                prices = default_prices
        else:
            logger.info("get_machine_prices: no DB setting found (setting=%s), using defaults with 80/100/120/140/160",
                       'exists but empty' if setting else 'does not exist')
            prices = default_prices
        prices = _normalize_prices_keys(prices)
        options = _options_from_machine_prices(prices)
        return {'success': True, 'prices': prices, 'options': options}
    except Exception as e:
        logger.error(f"Error getting machine prices: {e}")
        prices = _normalize_prices_keys(default_prices)
        options = _options_from_machine_prices(prices)
        return {'success': True, 'prices': prices, 'options': options}


@anvil.server.callable
def diagnose_calculator_prices(token_or_email):
    """تشخيص: عرض محتوى جدول الأسعار والخيارات المولّدة (للأدمن فقط)."""
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error if isinstance(error, dict) else {'success': False, 'message': 'Permission denied'}
    result = {}
    try:
        setting = app_tables.settings.get(setting_key='machine_prices')
        if setting and setting['setting_value']:
            raw = setting['setting_value']
            result['raw_setting_length'] = len(raw)
            try:
                prices = json.loads(raw)
                result['parsed_ok'] = True
                # عرض المفاتيح (type > color > width)
                summary = {}
                for mtype, by_color in prices.items():
                    if isinstance(by_color, dict):
                        summary[str(mtype)] = {}
                        for color, by_width in by_color.items():
                            if isinstance(by_width, dict):
                                summary[str(mtype)][str(color)] = {str(w): v for w, v in by_width.items()}
                result['prices_summary'] = summary
                normalized = _normalize_prices_keys(prices)
                options = _options_from_machine_prices(normalized)
                result['generated_options'] = options
            except json.JSONDecodeError as e:
                result['parsed_ok'] = False
                result['parse_error'] = str(e)
        else:
            result['setting_exists'] = bool(setting)
            result['setting_value_empty'] = True
            result['using_defaults'] = True
        # عرض الكونفيج القديم أيضاً
        config_setting = app_tables.settings.get(setting_key='machine_config')
        if config_setting and config_setting['setting_value']:
            try:
                result['machine_config'] = json.loads(config_setting['setting_value'])
            except Exception:
                result['machine_config'] = 'parse error'
        else:
            result['machine_config'] = 'not set (using defaults: 80,100,120)'
        result['success'] = True
    except Exception as e:
        result['success'] = False
        result['error'] = str(e)
    return result


@anvil.server.callable
def save_machine_prices(token_or_email, prices):
    """
    حفظ أسعار المكن في السيرفر
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error
    
    try:
        ip_address = get_client_ip()
        admin_email = token_or_email if '@' in str(token_or_email) else 'admin'
        
        setting = app_tables.settings.get(setting_key='machine_prices')
        old_value = None
        
        if setting:
            old_value = setting['setting_value']
            setting.update(
                setting_value=json.dumps(prices),
                setting_type='json',
                updated_by=admin_email,
                updated_at=datetime.now()
            )
        else:
            app_tables.settings.add_row(
                setting_key='machine_prices',
                setting_value=json.dumps(prices),
                setting_type='json',
                description='Machine prices configuration',
                updated_by=admin_email,
                updated_at=datetime.now()
            )
        
        log_audit('UPDATE_SETTING', 'settings', 'machine_prices',
                  {'value': old_value} if old_value else None,
                  {'value': 'machine_prices_updated', 'updated_by': admin_email},
                  admin_email, ip_address)
        
        return {'success': True, 'message': 'Machine prices saved successfully'}
    except Exception as e:
        logger.error(f"Error saving machine prices: {e}")
        return {'success': False, 'message': str(e)}


@anvil.server.callable
def get_machine_config():
    """
    الحصول على إعدادات المكن (الأنواع، الألوان، العروض)
    """
    default_config = {
        'types': [
            "Metal anilox",
            "Ceramic anilox Single Doctor Blade",
            "Ceramic anilox Chamber Doctor Blade"
        ],
        'colors': ["4", "6", "8"],
        'widths': ["80", "100", "120"]
    }
    
    try:
        setting = app_tables.settings.get(setting_key='machine_config')
        if setting and setting['setting_value']:
            try:
                config = json.loads(setting['setting_value'])
                return {'success': True, 'config': config}
            except json.JSONDecodeError:
                pass
        
        return {'success': True, 'config': default_config}
    except Exception as e:
        logger.error(f"Error getting machine config: {e}")
        return {'success': True, 'config': default_config}


@anvil.server.callable
def save_machine_config(token_or_email, config):
    """
    حفظ إعدادات المكن (الأنواع، الألوان، العروض)
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error
    
    try:
        ip_address = get_client_ip()
        admin_email = token_or_email if '@' in str(token_or_email) else 'admin'
        
        setting = app_tables.settings.get(setting_key='machine_config')
        old_value = None
        
        if setting:
            old_value = setting['setting_value']
            setting.update(
                setting_value=json.dumps(config),
                setting_type='json',
                updated_by=admin_email,
                updated_at=datetime.now()
            )
        else:
            app_tables.settings.add_row(
                setting_key='machine_config',
                setting_value=json.dumps(config),
                setting_type='json',
                description='Machine configuration (types, colors, widths)',
                updated_by=admin_email,
                updated_at=datetime.now()
            )
        
        # Also update machine prices to include new types/colors/widths
        prices_setting = app_tables.settings.get(setting_key='machine_prices')
        if prices_setting and prices_setting['setting_value']:
            try:
                prices = json.loads(prices_setting['setting_value'])
                updated = False
                
                # Add new types with default prices
                for machine_type in config.get('types', []):
                    if machine_type not in prices:
                        prices[machine_type] = {}
                        updated = True
                    
                    # Add new colors for each type
                    for color in config.get('colors', []):
                        if color not in prices[machine_type]:
                            prices[machine_type][color] = {}
                            updated = True
                        
                        # Add new widths for each color
                        for width in config.get('widths', []):
                            if width not in prices[machine_type][color]:
                                # Default price based on type and size
                                base_price = 15000
                                if 'Ceramic' in machine_type:
                                    base_price = 18000
                                    if 'Chamber' in machine_type:
                                        base_price = 21000
                                
                                color_mult = 1 + (int(color) - 4) * 0.3
                                width_mult = 1 + (int(width) - 80) * 0.01
                                default_price = int(base_price * color_mult * width_mult)
                                prices[machine_type][color][width] = default_price
                                updated = True
                
                if updated:
                    prices_setting.update(
                        setting_value=json.dumps(prices),
                        updated_by=admin_email,
                        updated_at=datetime.now()
                    )
            except json.JSONDecodeError:
                pass
        
        log_audit('UPDATE_SETTING', 'settings', 'machine_config',
                  {'value': old_value} if old_value else None,
                  {'value': 'machine_config_updated', 'updated_by': admin_email},
                  admin_email, ip_address)
        
        return {'success': True, 'message': 'Machine configuration saved successfully'}
    except Exception as e:
        logger.error(f"Error saving machine config: {e}")
        return {'success': False, 'message': str(e)}


# =========================================================
# سجل التدقيق
# =========================================================
@anvil.server.callable
def get_my_audit_logs(token_or_email, limit=50):
    """
    إرجاع إشعارات (سجل تدقيق) للمستخدم الحالي فقط — للأيقونة في لوحة الأدمن.
    ترتيب من الأحدث إلى الأقدم.
    """
    if not token_or_email:
        return {'success': False, 'notifications': []}
    session = validate_session(token_or_email)
    user_email = None
    if session and session.get('email'):
        user_email = session['email']
    elif token_or_email and '@' in str(token_or_email):
        u = app_tables.users.get(email=str(token_or_email).strip().lower())
        if u and u.get('is_active') and u.get('is_approved'):
            user_email = u['email']
    if not user_email:
        return {'success': False, 'notifications': []}
    try:
        my_logs = list(app_tables.audit_log.search(user_email=user_email))
        my_logs.sort(key=lambda x: x['timestamp'] or datetime.min, reverse=True)
        notifications = []
        for log in my_logs[:limit]:
            notifications.append({
                'timestamp': log['timestamp'].isoformat() if log.get('timestamp') else '',
                'action': log.get('action', ''),
                'action_description': log.get('action_description', ''),
                'table_name': log.get('table_name', ''),
                'record_id': str(log.get('record_id', ''))
            })
        return {'success': True, 'notifications': notifications}
    except Exception as e:
        logger.error("get_my_audit_logs: %s", e)
        return {'success': False, 'notifications': []}


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
            user_filter = filters['user_email'].lower()
            all_logs = [l for l in all_logs if l['user_email'] and user_filter in l['user_email'].lower()]
        if filters.get('table_name'):
            all_logs = [l for l in all_logs if l['table_name'] == filters['table_name']]
        if filters.get('date_from'):
            try:
                date_from = datetime.strptime(filters['date_from'], '%Y-%m-%d')
                all_logs = [l for l in all_logs if l['timestamp'] and l['timestamp'] >= date_from]
            except ValueError:
                pass
        if filters.get('date_to'):
            try:
                date_to = datetime.strptime(filters['date_to'], '%Y-%m-%d')
                # Add one day to include the entire end date
                date_to = date_to.replace(hour=23, minute=59, second=59)
                all_logs = [l for l in all_logs if l['timestamp'] and l['timestamp'] <= date_to]
            except ValueError:
                pass

    total = len(all_logs)
    page_logs = all_logs[offset:offset + limit]

    logs = []
    for log in page_logs:
        logs.append({
            'log_id': log['log_id'],
            'timestamp': log['timestamp'].isoformat() if log['timestamp'] else '',
            'user_email': log.get('user_email', ''),
            'user_name': log.get('user_name', ''),
            'action_description': log.get('action_description', ''),
            'action': log.get('action', ''),
            'table_name': log.get('table_name', ''),
            'record_id': log.get('record_id', ''),
            'old_data': log.get('old_data', ''),
            'new_data': log.get('new_data', ''),
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


# =========================================================
# حذف المستخدم نهائياً
# =========================================================
@anvil.server.callable
def delete_user_permanently(token_or_email, user_id):
    """
    حذف مستخدم نهائياً من جميع السجلات
    يتطلب صلاحيات أدمن
    """
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error

    ip_address = get_client_ip()
    admin_email = token_or_email if '@' in str(token_or_email) else 'admin'

    user = app_tables.users.get(user_id=user_id)

    if not user:
        return {'success': False, 'message': 'User not found'}

    user_email = user['email']

    # منع حذف الأدمن نفسه
    session = validate_session(token_or_email)
    if session and session.get('email') == user_email:
        return {'success': False, 'message': 'Cannot delete your own account'}

    # منع حذف آخر أدمن في النظام
    if user['role'] == 'admin':
        admin_count = len(list(app_tables.users.search(role='admin', is_active=True)))
        if admin_count <= 1:
            return {'success': False, 'message': 'Cannot delete the last admin account'}

    try:
        # حذف جميع الجلسات
        for session in app_tables.sessions.search(user_email=user_email):
            session.delete()

        # حذف سجل كلمات المرور
        for history in app_tables.password_history.search(user_email=user_email):
            history.delete()

        # حذف OTP codes
        for otp in app_tables.otp_codes.search(user_email=user_email):
            otp.delete()

        # حذف pending passwords
        for pending in app_tables.pending_passwords.search(user_email=user_email):
            pending.delete()

        # تسجيل في Audit Log قبل الحذف
        log_audit('DELETE_USER_PERMANENTLY', 'users', user_id, {
            'email': user_email,
            'full_name': user['full_name'],
            'role': user['role']
        }, None, admin_email, ip_address)

        # حذف المستخدم
        user.delete()

        logger.info(f"User permanently deleted: {user_email} by {admin_email}")

        return {
            'success': True,
            'message': f'User {user_email} has been permanently deleted'
        }

    except Exception as e:
        logger.error(f"Error deleting user permanently: {e}")
        return {'success': False, 'message': f'Error: {str(e)}'}


# =========================================================
# Audit Log Cleanup (Auto-delete logs older than 15 days)
# =========================================================
@anvil.server.callable
def cleanup_old_audit_logs(days=15, token_or_email=None):
    """
    حذف سجلات التدقيق القديمة (أكثر من 15 يوم)
    يمكن استدعاؤها يدوياً أو عبر scheduled task
    """
    # السماح بالاستدعاء الداخلي (بدون token) من auto_cleanup أو scheduled tasks
    if token_or_email is not None:
        is_authorized, error = require_admin(token_or_email)
        if not is_authorized:
            return error
    try:
        cutoff_date = get_utc_now() - timedelta(days=days)
        deleted_count = 0

        for log in app_tables.audit_log.search():
            log_timestamp = log['timestamp']
            if log_timestamp:
                # تحويل للمقارنة
                if log_timestamp.tzinfo is None:
                    log_timestamp = log_timestamp.replace(tzinfo=timezone.utc)
                if log_timestamp < cutoff_date:
                    log.delete()
                    deleted_count += 1

        logger.info(f"Audit log cleanup: deleted {deleted_count} records older than {days} days")
        return {
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Deleted {deleted_count} old audit log records'
        }

    except Exception as e:
        logger.error(f"Error cleaning up audit logs: {e}")
        return {'success': False, 'message': f'Error: {str(e)}'}


def auto_cleanup_audit_logs():
    """
    تنظيف تلقائي للـ Audit Log - يُستدعى عند بدء التطبيق
    """
    try:
        cleanup_old_audit_logs(15)
    except Exception as e:
        logger.error(f"Auto cleanup error: {e}")


# تشغيل التنظيف التلقائي عند تحميل الموديول
try:
    auto_cleanup_audit_logs()
except Exception as e:
    logger.error(f"Module load cleanup error: {e}")


# =========================================================
# Session Activity Check (for auto-logout)
# =========================================================
@anvil.server.callable
def check_session_activity(token):
    """
    التحقق من نشاط الجلسة وتحديث وقت النشاط
    يُستدعى دورياً من العميل
    """
    session = validate_session(token)

    if not session:
        return {'valid': False, 'message': 'Session expired'}

    try:
        # تحديث وقت آخر نشاط - استخدام hash للبحث في DB
        from .auth_sessions import _hash_token
        token_hash = _hash_token(token)
        session_record = app_tables.sessions.get(session_token=token_hash)
        if session_record:
            # تمديد الجلسة إذا كان المستخدم نشطاً
            new_expires = datetime.now() + timedelta(minutes=SESSION_DURATION_MINUTES)
            session_record.update(
                expires_at=new_expires,
                last_activity=datetime.now()
            )

        return {
            'valid': True,
            'expires_in_minutes': SESSION_DURATION_MINUTES,
            'message': 'Session refreshed'
        }
    except Exception as e:
        logger.error(f"Session activity check error: {e}")
        return {'valid': True}  # لا نُنهي الجلسة في حالة خطأ


@anvil.server.callable
def get_session_info(token):
    """
    الحصول على معلومات الجلسة الحالية
    """
    session = validate_session(token)

    if not session:
        return {'valid': False}

    try:
        from .auth_sessions import _hash_token
        token_hash = _hash_token(token)
        session_record = app_tables.sessions.get(session_token=token_hash)
        if session_record:
            remaining = (session_record['expires_at'] - datetime.now()).total_seconds() / 60

            return {
                'valid': True,
                'remaining_minutes': max(0, int(remaining)),
                'expires_at': session_record['expires_at'].isoformat(),
                'session_timeout_minutes': SESSION_DURATION_MINUTES
            }
    except (KeyError, AttributeError, TypeError):
        pass

    return {'valid': True}


# =========================================================
# تنظيف الجلسات المنتهية تلقائياً (Scheduler)
# =========================================================
@anvil.server.background_task
def scheduled_session_cleanup():
    """
    مهمة مجدولة لتنظيف الجلسات المنتهية.
    يجب إعدادها في Anvil Scheduler لتعمل كل ساعة.
    Anvil → Background Tasks → Add Task → scheduled_session_cleanup → Every hour
    """
    try:
        cleaned = cleanup_expired_sessions()
        logger.info(f"Scheduled session cleanup completed: {cleaned} sessions cleaned")
        return {'success': True, 'cleaned': cleaned}
    except Exception as e:
        logger.error(f"Scheduled session cleanup error: {e}")
        return {'success': False, 'error': str(e)}


@anvil.server.callable
def manual_session_cleanup(token_or_email):
    """تنظيف يدوي للجلسات المنتهية (للأدمن فقط)"""
    is_authorized, error = require_admin(token_or_email)
    if not is_authorized:
        return error if isinstance(error, dict) else {'success': False, 'message': 'Permission denied'}
    cleaned = cleanup_expired_sessions()
    return {'success': True, 'message': f'تم تنظيف {cleaned} جلسة منتهية'}

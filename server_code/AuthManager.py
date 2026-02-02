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
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import json
import uuid
import re
import logging


def get_utc_now():
  """الحصول على الوقت الحالي بـ UTC timezone"""
  return datetime.now(timezone.utc)


def make_aware(dt):
  """تحويل datetime naive إلى aware (UTC)"""
  if dt is None:
    return None
  if dt.tzinfo is None:
    return dt.replace(tzinfo=timezone.utc)
  return dt

# محاولة استيراد خدمة البريد الإلكتروني
try:
  import anvil.email
  EMAIL_SERVICE_AVAILABLE = True
except ImportError:
  EMAIL_SERVICE_AVAILABLE = False

# =========================================================
# إعداد نظام التسجيل (Logging) - يجب أن يكون أولاً
# =========================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================================================
# Gmail SMTP Configuration
# =========================================================
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_EMAIL = "mohamedadelfouda@gmail.com"
SMTP_PASSWORD = "mcum qlob fscc fctb"

def get_smtp_credentials():
  """الحصول على بيانات SMTP"""
  return SMTP_EMAIL, SMTP_PASSWORD

def send_email_smtp(to_email, subject, html_body):
  """
  إرسال إيميل عبر Gmail SMTP
  """
  smtp_email, smtp_password = get_smtp_credentials()

  if not smtp_email or not smtp_password:
    logger.error("SMTP credentials not configured")
    return False

  try:
    # إنشاء الرسالة
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"Helwan Plast System <{smtp_email}>"
    msg['To'] = to_email

    # إضافة HTML body
    html_part = MIMEText(html_body, 'html', 'utf-8')
    msg.attach(html_part)

    # الاتصال بـ SMTP server وإرسال الإيميل
    logger.info(f"Attempting to send email via SMTP to {to_email}")
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
      server.set_debuglevel(0)
      server.starttls()
      server.login(smtp_email, smtp_password)
      server.sendmail(smtp_email, to_email, msg.as_string())

    logger.info(f"Email sent successfully via SMTP to {to_email}")
    return True

  except smtplib.SMTPAuthenticationError as e:
    logger.error(f"SMTP Authentication failed: {e}")
    return False
  except smtplib.SMTPException as e:
    logger.error(f"SMTP Error: {e}")
    return False
  except Exception as e:
    logger.error(f"Failed to send email via SMTP to {to_email}: {type(e).__name__}: {e}")
    return False


# =========================================================
# الثوابت والإعدادات
# =========================================================
MAX_LOGIN_ATTEMPTS = 5           # عدد المحاولات قبل القفل
LOCKOUT_DURATION_MINUTES = 30    # مدة القفل بالدقائق
SESSION_DURATION_MINUTES = 60    # مدة الجلسة بالدقائق (60 دقيقة = ساعة واحدة)
RATE_LIMIT_WINDOW_MINUTES = 15   # نافذة Rate Limiting
RATE_LIMIT_MAX_REQUESTS = 100    # الحد الأقصى للطلبات في النافذة
PBKDF2_ITERATIONS = 100000       # عدد التكرارات للتشفير (أكثر أماناً)
PASSWORD_HISTORY_COUNT = 5       # عدد كلمات المرور السابقة للتحقق منها
OTP_EXPIRY_MINUTES = 10          # مدة صلاحية OTP

# Admin Email for Notifications - يُقرأ من Environment Variables
try:
  import anvil.secrets
  ADMIN_NOTIFICATION_EMAIL = anvil.secrets.get_secret('ADMIN_EMAIL') or "mohamedadelfouda@helwanplast.com"
  EMERGENCY_SECRET_KEY = anvil.secrets.get_secret('EMERGENCY_KEY') or "HELWAN_RESET_2024"
except:
  ADMIN_NOTIFICATION_EMAIL = "mohamedadelfouda@helwanplast.com"
  EMERGENCY_SECRET_KEY = "HELWAN_RESET_2024"

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
# وظائف إرسال البريد الإلكتروني
# =========================================================
def send_approval_email(user_email, user_name, role, approved=True):
  """
    إرسال بريد إلكتروني للمستخدم عند الموافقة أو الرفض
    """
  if not EMAIL_SERVICE_AVAILABLE:
    logger.warning("Email service not available. Skipping email notification.")
    return False

  try:
    if approved:
      subject = "Account Approved - Helwan Plast System"
      html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0; text-align: center;">Helwan Plast System</h1>
                </div>

                <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #2e7d32; margin-top: 0;">🎉 Account Approved!</h2>

                    <p style="font-size: 16px; color: #333;">Dear <strong>{user_name}</strong>,</p>

                    <p style="font-size: 16px; color: #333;">
                        Your account has been approved! You can now log in to the Helwan Plast System.
                    </p>

                    <div style="background: #e8f5e9; padding: 15px; border-radius: 8px; margin: 20px 0;">
                        <p style="margin: 0; font-size: 14px; color: #2e7d32;">
                            <strong>Your Role:</strong> {role.capitalize()}
                        </p>
                    </div>

                    <p style="font-size: 14px; color: #666;">
                        If you have any questions, please contact the administrator.
                    </p>

                    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">

                    <p style="font-size: 12px; color: #999; text-align: center;">
                        Best regards,<br>
                        <strong>Mohamed Adel - Helwan Plast</strong>
                    </p>
                </div>
            </div>
            """
    else:
      subject = "Account Status Update - Helwan Plast System"
      html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 10px 10px 0 0;">
                    <h1 style="color: white; margin: 0; text-align: center;">Helwan Plast System</h1>
                </div>

                <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 10px 10px;">
                    <h2 style="color: #c62828; margin-top: 0;">Account Registration Status</h2>

                    <p style="font-size: 16px; color: #333;">Dear <strong>{user_name}</strong>,</p>

                    <p style="font-size: 16px; color: #333;">
                        We regret to inform you that your account registration request has been declined.
                    </p>

                    <div style="background: #ffebee; padding: 15px; border-radius: 8px; margin: 20px 0;">
                        <p style="margin: 0; font-size: 14px; color: #c62828;">
                            If you believe this was a mistake, please contact the administrator for more information.
                        </p>
                    </div>

                    <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">

                    <p style="font-size: 12px; color: #999; text-align: center;">
                        Best regards,<br>
                        <strong>Mohamed Adel - Helwan Plast</strong>
                    </p>
                </div>
            </div>
            """

    # استخدام SMTP بدلاً من Anvil Email
    result = send_email_smtp(user_email, subject, html_body)

    if result:
      logger.info(f"Email sent to {user_email}: {'Approval' if approved else 'Rejection'}")
      return True
    else:
      logger.error(f"Failed to send email to {user_email}")
      return False

  except Exception as e:
    logger.error(f"Failed to send email to {user_email}: {e}")
    return False


# =========================================================
# OTP Generation and Verification
# =========================================================
def generate_otp():
  """توليد رمز OTP من 6 أرقام"""
  return ''.join([str(secrets.randbelow(10)) for _ in range(6)])


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

      # إضافة OTP جديد
    app_tables.otp_codes.add_row(
      otp_id=str(uuid.uuid4()),
      user_email=user_email,
      otp_code=otp,
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
    # البحث عن OTP باستخدام search بدلاً من get لتجنب أخطاء "More than one row"
    otp_records = list(app_tables.otp_codes.search(
      user_email=user_email,
      otp_code=otp,
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
    يدعم كلمات المرور القديمة (SHA-256) والجديدة (PBKDF2)
    """
  if not stored_hash:
    return False

  try:
    # التحقق من نوع التشفير
    if ':' in stored_hash:
      # تشفير PBKDF2 الجديد (salt:hash)
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
    else:
      # تشفير SHA-256 القديم (للتوافق مع كلمات المرور السابقة)
      old_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
      return secrets.compare_digest(old_hash, stored_hash)

  except Exception as e:
    logger.error(f"Password verification error: {e}")
    return False


def upgrade_password_hash(user, password):
  """
    ترقية كلمة المرور من SHA-256 القديم إلى PBKDF2 الجديد
    يتم استدعاؤها تلقائياً عند تسجيل الدخول الناجح
    """
  try:
    stored_hash = user['password_hash']

    # إذا كانت كلمة المرور بالتشفير القديم (بدون :)
    if stored_hash and ':' not in stored_hash:
      # إعادة تشفير كلمة المرور بالطريقة الجديدة
      new_hash = hash_password(password)
      user.update(password_hash=new_hash)
      logger.info(f"Password hash upgraded for user: {user['email']}")
      return True
  except Exception as e:
    logger.error(f"Error upgrading password hash: {e}")

  return False


# =========================================================
# Password History (منع تكرار كلمات المرور)
# =========================================================
def add_to_password_history(user_email, password_hash):
  """
    إضافة كلمة المرور إلى سجل كلمات المرور السابقة
    """
  try:
    app_tables.password_history.add_row(
      history_id=str(uuid.uuid4()),
      user_email=user_email,
      password_hash=password_hash,
      created_at=datetime.now()
    )

    # حذف كلمات المرور القديمة إذا تجاوزت الحد
    history = list(app_tables.password_history.search(user_email=user_email))
    history.sort(key=lambda x: x['created_at'], reverse=True)

    if len(history) > PASSWORD_HISTORY_COUNT:
      for old in history[PASSWORD_HISTORY_COUNT:]:
        old.delete()

    return True
  except Exception as e:
    logger.error(f"Failed to add password to history: {e}")
    return False


def check_password_history(user_email, new_password):
  """
    التحقق من أن كلمة المرور الجديدة ليست مستخدمة سابقاً
    Returns: (is_valid, message)
    """
  try:
    history = list(app_tables.password_history.search(user_email=user_email))

    for record in history:
      if verify_password(new_password, record['password_hash']):
        return False, f"Cannot reuse any of your last {PASSWORD_HISTORY_COUNT} passwords"

    return True, "Password is valid"
  except Exception as e:
    logger.error(f"Password history check error: {e}")
    return True, "Check passed"  # السماح في حالة الخطأ


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
  expires = datetime.now() + timedelta(minutes=SESSION_DURATION_MINUTES)

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

      # جلب المستخدم الحالي من جدول users
      # هذا يضمن أن أي تغيير في الـ role أو الحالة يُطبق فوراً
    user = app_tables.users.get(email=session['user_email'])

    if not user:
      # المستخدم تم حذفه - إبطال الجلسة
      session.update(is_active=False)
      return None

      # التحقق من أن المستخدم مفعل ومعتمد
    if not user['is_active'] or not user['is_approved']:
      # المستخدم غير مفعل أو غير معتمد - إبطال الجلسة
      session.update(is_active=False)
      return None

    return {
      'email': session['user_email'],
      'role': user['role'],  # استخدام الـ role الحالي من users table
      'is_active': user['is_active'],
      'is_approved': user['is_approved'],
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
            # إعادة إرسال OTP
            otp = generate_otp()
            store_otp(email, otp, 'verification')
            send_otp_email(email, full_name, otp, 'verification')
            return {
                'success': True,
                'requires_verification': True,
                'message': 'Verification code resent to your email'
            }
        return {'success': False, 'message': 'Email already registered'}

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

        # إرسال OTP للتحقق من البريد
        otp = generate_otp()
        store_otp(email, otp, 'verification')
        email_sent = send_otp_email(email, full_name, otp, 'verification')

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
    send_otp_email(email, user['full_name'], otp, 'verification')

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

    # كلمة المرور صحيحة - إرسال OTP للتحقق الثنائي
    otp = generate_otp()
    store_otp(email, otp, '2fa')
    email_sent = send_otp_email(email, user['full_name'], otp, '2fa')

    if email_sent:
        logger.info(f"2FA OTP sent to: {email}")
        return {
            'success': True,
            'requires_2fa': True,
            'message': 'Verification code sent to your email'
        }
    else:
        # في حالة فشل إرسال الإيميل، نرجع خطأ بدلاً من السماح بالدخول
        logger.error(f"Failed to send 2FA OTP to: {email}")
        return {
            'success': False,
            'message': 'Failed to send verification code. Please try again later.'
        }


@anvil.server.callable
def verify_login_otp(email, otp):
    """
    التحقق من OTP وإتمام تسجيل الدخول
    """
    ip_address = get_client_ip()
    email = str(email or '').strip().lower()

    # التحقق من OTP
    is_valid, message = verify_otp(email, otp, '2fa')

    if not is_valid:
        return {'success': False, 'message': message}

    # البحث عن المستخدم
    user = app_tables.users.get(email=email)
    if not user:
        return {'success': False, 'message': 'User not found'}

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

    # ترقية كلمة المرور من التشفير القديم إلى الجديد (إذا لزم الأمر)
    upgrade_password_hash(user, user['password_hash'])

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
    send_otp_email(email, user['full_name'], otp, '2fa')

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
def is_admin(token_or_email):
    """
    التحقق من أن المستخدم أدمن
    يدعم: token الجلسة أو البريد الإلكتروني

    الآن validate_session يتحقق من is_active و is_approved تلقائياً
    """
    if not token_or_email:
        return False

    # أولاً: إذا كان بريد إلكتروني، تحقق مباشرة
    if '@' in str(token_or_email):
        return is_admin_by_email(token_or_email)

    # ثانياً: التحقق من الجلسة في قاعدة البيانات
    # validate_session يتحقق من is_active و is_approved تلقائياً
    session = validate_session(token_or_email)
    if session and session.get('role') == 'admin':
        return True

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

    تدعم:
    - token الجلسة
    - البريد الإلكتروني
    - user_id
    """
    if not token_or_email:
        logger.warning("require_admin: No token or email provided")
        return False, {'success': False, 'message': 'Admin access required'}

    token_preview = str(token_or_email)[:30] if token_or_email else 'None'
    logger.info(f"require_admin checking: {token_preview}...")

    # الطريقة 1: استخدام is_admin الموحدة (تدعم token و email)
    if is_admin(token_or_email):
        logger.info("Admin access granted via is_admin()")
        return True, None

    # الطريقة 2: محاولة استخراج البريد من الجلسة والتحقق منه
    session = validate_session(token_or_email)
    if session and session.get('email'):
        email = session['email']
        logger.info(f"Found session with email: {email}")
        if is_admin_by_email(email):
            logger.info("Admin access granted via session email")
            return True, None

    # الطريقة 3: محاولة إيجاد المستخدم بالـ token كـ user_id (للحالات الخاصة)
    try:
        user_by_id = app_tables.users.get(user_id=token_or_email)
        if user_by_id and user_by_id['role'] == 'admin' and user_by_id['is_active'] and user_by_id['is_approved']:
            logger.info("Admin access granted via user_id")
            return True, None
    except Exception:
        pass

    logger.warning(f"Admin access denied for: {token_preview}...")
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
def debug_admin_check(token_or_email):
    """
    Debug function to check admin access - للتشخيص
    """
    result = {
        'token_received': token_or_email[:50] if token_or_email else 'None',
        'session_valid': False,
        'session_data': None,
        'user_found': False,
        'user_data': None,
        'is_admin_result': False
    }

    # Check session
    session = validate_session(token_or_email)
    if session:
        result['session_valid'] = True
        result['session_data'] = session

    # Check if email
    if token_or_email and '@' in str(token_or_email):
        user = app_tables.users.get(email=str(token_or_email).lower())
        if user:
            result['user_found'] = True
            result['user_data'] = {
                'email': user['email'],
                'role': user['role'],
                'is_active': user['is_active'],
                'is_approved': user['is_approved']
            }

    # Check is_admin
    result['is_admin_result'] = is_admin(token_or_email)

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
    email_sent = send_otp_email(user['email'], user['full_name'], otp, 'password_reset')

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
    email_sent = send_otp_email(email, user['full_name'], otp, 'password_reset')

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
    except:
        return {'exists': False}


@anvil.server.callable
def diagnose_admin_access(email, token=None):
    """
    تشخيص مشكلة صلاحيات الأدمن
    تُرجع معلومات مفصلة للتصحيح
    """
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
    يتطلب مفتاح سري من Environment Variables
    """
    if secret_key != EMERGENCY_SECRET_KEY:
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
    تتطلب مفتاح سري من Environment Variables

    إذا لم يكن المستخدم موجوداً، سيتم إنشاء حساب أدمن جديد
    """
    ip_address = get_client_ip()

    try:
        # التحقق من المفتاح السري
        if secret_key != EMERGENCY_SECRET_KEY:
            log_audit('FAILED_EMERGENCY_RESET', 'users', None, None,
                      {'email': email, 'reason': 'Invalid secret key'}, email, ip_address)
            return {'success': False, 'message': 'Invalid secret key'}

        # التحقق من كلمة المرور الجديدة
        if not new_password or len(new_password) < 6:
            return {'success': False, 'message': 'Password must be at least 6 characters'}

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
        # تحديث وقت آخر نشاط
        session_record = app_tables.sessions.get(session_token=token)
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
        session_record = app_tables.sessions.get(session_token=token)
        if session_record:
            remaining = (session_record['expires_at'] - datetime.now()).total_seconds() / 60

            return {
                'valid': True,
                'remaining_minutes': max(0, int(remaining)),
                'expires_at': session_record['expires_at'].isoformat(),
                'session_timeout_minutes': SESSION_DURATION_MINUTES
            }
    except:
        pass

    return {'valid': True}

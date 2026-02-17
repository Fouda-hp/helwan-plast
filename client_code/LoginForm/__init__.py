"""
LoginForm - صفحة تسجيل الدخول والتسجيل
======================================
- تسجيل الدخول
- تسجيل مستخدم جديد (مع رقم التليفون)
- إعداد الأدمن الأولي
"""

from ._anvil_designer import LoginFormTemplate
from anvil import *
import anvil.users
import anvil.google.auth, anvil.google.drive
from anvil.google.drive import app_files
import anvil.server
import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables
import anvil.js
import json
import logging

try:
    from ..auth_helpers import validate_token_cached
except ImportError:
    from auth_helpers import validate_token_cached

logger = logging.getLogger(__name__)


class LoginForm(LoginFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Expose Python functions to JavaScript
        anvil.js.window.loginUser = self.login_user
        anvil.js.window.registerUser = self.register_user
        anvil.js.window.setupAdmin = self.setup_admin
        anvil.js.window.checkAdminExists = self.check_admin_exists
        anvil.js.window.resetAdminPassword = self.reset_admin_password
        # New OTP verification functions
        anvil.js.window.verifyLoginOtp = self.verify_login_otp
        anvil.js.window.resendLoginOtp = self.resend_login_otp
        anvil.js.window.verifyRegistrationOtp = self.verify_registration_otp
        anvil.js.window.resendVerificationOtp = self.resend_verification_otp

        # Forgot Password functions
        anvil.js.window.requestPasswordReset = self.request_password_reset
        anvil.js.window.verifyPasswordResetOtp = self.verify_password_reset_otp
        anvil.js.window.completePasswordReset = self.complete_password_reset

        # Rate Limit Clear function
        anvil.js.window.clearRateLimit = self.clear_rate_limit

        # Check if user is already logged in (auto-login)
        self.check_existing_session()

        # Check route on load
        self.check_route()

        # Listen for hash changes
        anvil.js.window.addEventListener("hashchange", self.on_hash_change)

    def check_existing_session(self):
        """Check if user has valid session (sessionStorage primary; migrate/remove legacy localStorage token)."""
        try:
            auth_token = anvil.js.window.sessionStorage.getItem('auth_token')
            user_email = anvil.js.window.sessionStorage.getItem('user_email')
            user_role = anvil.js.window.sessionStorage.getItem('user_role')

            # One-way migration from legacy localStorage token, then remove it
            if not auth_token:
                legacy_token = anvil.js.window.localStorage.getItem('auth_token')
                if legacy_token:
                    auth_token = legacy_token
                    anvil.js.window.sessionStorage.setItem('auth_token', auth_token)
                    anvil.js.window.localStorage.removeItem('auth_token')
            if not user_email:
                user_email = anvil.js.window.localStorage.getItem('user_email')
                if user_email:
                    anvil.js.window.sessionStorage.setItem('user_email', user_email)
                    anvil.js.window.localStorage.removeItem('user_email')
            if not user_role:
                user_role = anvil.js.window.localStorage.getItem('user_role')
                if user_role:
                    anvil.js.window.sessionStorage.setItem('user_role', user_role)
                    anvil.js.window.localStorage.removeItem('user_role')
            user_name = anvil.js.window.sessionStorage.getItem('user_name') or anvil.js.window.localStorage.getItem('user_name')
            if user_name:
                anvil.js.window.sessionStorage.setItem('user_name', user_name)
                anvil.js.window.localStorage.removeItem('user_name')

            # Only check if we have saved credentials
            if auth_token and user_email:
                # Validate the token with the server (cached)
                result = validate_token_cached(auth_token)
                if result.get('valid'):
                    # لا نغيّر الـ hash إذا المستخدم كان على صفحة معيّنة (مثلاً بعد الـ refresh)
                    current_hash = (anvil.js.window.location.hash or '').strip()
                    if not current_hash or current_hash == '#' or current_hash == '#login':
                        if user_role == 'admin':
                            anvil.js.window.location.hash = '#admin'
                        else:
                            anvil.js.window.location.hash = '#launcher'
                else:
                    # Token expired or invalid, clear storage
                    self.clear_auth_storage()
        except Exception as e:
            logger.debug("Auto-login check error: %s", e)
            self.clear_auth_storage()

    def clear_auth_storage(self):
        """Clear all auth-related sessionStorage (and localStorage for cleanup)"""
        try:
            for key in ('auth_token', 'user_email', 'user_name', 'user_role'):
                anvil.js.window.sessionStorage.removeItem(key)
                anvil.js.window.localStorage.removeItem(key)
        except Exception:
            pass

    def on_hash_change(self, event):
        self.check_route()

    def check_route(self):
        hash_val = (anvil.js.window.location.hash or '').strip() or '#launcher'

        if hash_val == "#login":
            return  # نبقى على صفحة تسجيل الدخول (تجنب حلقة LauncherForm ↔ LoginForm)
        if hash_val == "#launcher":
            open_form('LauncherForm')
        elif hash_val == "#calculator":
            open_form('CalculatorForm')
        elif hash_val == "#admin":
            if not self._user_is_admin():
                anvil.js.window.location.hash = '#launcher'
                open_form('LauncherForm')
                return
            open_form('AdminPanel')
        elif hash_val == "#import":
            open_form('DataImportForm')
        elif hash_val == "#quotation-print":
            open_form('QuotationPrintForm')
        elif hash_val == "#contract-print":
            open_form('ContractPrintForm')
        elif hash_val == "#contract-new":
            open_form('ContractPrintForm')
        elif hash_val == "#contract-edit":
            open_form('ContractEditForm')
        elif hash_val == "#payment-dashboard":
            open_form('PaymentDashboardForm')
        elif hash_val.startswith("#client-detail"):
            open_form('ClientDetailForm')
        elif hash_val == "#follow-ups":
            open_form('FollowUpDashboardForm')
        else:
            open_form('LauncherForm')

    def _user_is_admin(self):
        """التحقق من السيرفر أن المستخدم الحالي أدمن (مع cache)."""
        try:
            token = anvil.js.window.sessionStorage.getItem('auth_token')
            if not token:
                return False
            result = validate_token_cached(token)
            if not result.get('valid') or not result.get('user'):
                return False
            return (result.get('user', {}).get('role') or '').strip().lower() == 'admin'
        except Exception:
            return False

    # =========================================
    # Bridge functions for JavaScript
    # =========================================
    def login_user(self, email, password):
        """
        Login user - called from JavaScript
        تسجيل دخول المستخدم
        """
        try:
            result = anvil.server.call('login_user', email, password)

            # حفظ معلومات المستخدم في localStorage للحفاظ على الجلسة (وكل النوافذ/الإطارات)
            if result.get('success') and result.get('user'):
                user = result['user']
                token = result.get('token', '')
                self._save_auth_everywhere(
                    user_email=user.get('email', ''),
                    user_name=user.get('full_name', ''),
                    user_role=user.get('role', ''),
                    auth_token=token
                )

            return result
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}

    def register_user(self, email, password, full_name, phone=None):
        """
        Register user - called from JavaScript
        تسجيل مستخدم جديد مع رقم التليفون
        """
        try:
            result = anvil.server.call('register_user', email, password, full_name, phone)
            if result is None:
                return {'success': False, 'message': 'Server returned empty response'}
            return result
        except Exception as e:
            logger.debug("register_user error: %s", e)
            return {'success': False, 'message': f'Error: {str(e)}'}

    def setup_admin(self, email, password, full_name, phone=None):
        """
        Setup initial admin - called from JavaScript
        إعداد الأدمن الأولي مع رقم التليفون
        """
        try:
            result = anvil.server.call('setup_initial_admin', email, password, full_name, phone)
            return result
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}

    def check_admin_exists(self):
        """
        Check if admin exists - called from JavaScript
        التحقق من وجود أدمن
        """
        try:
            result = anvil.server.call('check_admin_exists')
            return result
        except Exception as e:
            return {'exists': True}  # Default to true for safety

    def reset_admin_password(self, email, new_password, secret_key):
        """
        Emergency admin password reset - called from JavaScript
        إعادة تعيين كلمة مرور الأدمن (للطوارئ)
        """
        try:
            result = anvil.server.call('reset_admin_password_emergency', email, new_password, secret_key)
            return result
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}

    # =========================================
    # OTP Verification functions
    # =========================================
    def verify_login_otp(self, email, otp):
        """
        Verify OTP for 2FA login
        التحقق من OTP لتسجيل الدخول
        """
        try:
            result = anvil.server.call('verify_login_otp', email, otp)

            # حفظ معلومات المستخدم إذا نجح التحقق (وكل النوافذ/الإطارات)
            if result.get('success') and result.get('user'):
                user = result['user']
                token = result.get('token', '')
                self._save_auth_everywhere(
                    user_email=user.get('email', ''),
                    user_name=user.get('full_name', ''),
                    user_role=user.get('role', ''),
                    auth_token=token
                )

            return result
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}

    def _save_auth_everywhere(self, user_email='', user_name='', user_role='', auth_token=''):
        """حفظ التوكن في sessionStorage فقط + بيانات المستخدم (بدون auth_token في localStorage)."""
        try:
            ss = anvil.js.window.sessionStorage
            ls = anvil.js.window.localStorage
            if ss:
                ss.setItem('user_email', user_email or '')
                ss.setItem('user_name', user_name or '')
                ss.setItem('user_role', user_role or '')
                if auth_token:
                    ss.setItem('auth_token', auth_token)
            # localStorage: تنظيف كامل — لا نحفظ أي بيانات auth هناك (أمان)
            if ls:
                ls.removeItem('auth_token')
                ls.removeItem('user_email')
                ls.removeItem('user_name')
                ls.removeItem('user_role')
            # حفظ أيضاً في الإطار الأعلى إن وُجد
            try:
                if anvil.js.window.top and anvil.js.window.top != anvil.js.window:
                    top_ss = anvil.js.window.top.sessionStorage
                    if top_ss:
                        top_ss.setItem('user_email', user_email or '')
                        top_ss.setItem('user_name', user_name or '')
                        top_ss.setItem('user_role', user_role or '')
                        if auth_token:
                            top_ss.setItem('auth_token', auth_token)
            except Exception:
                pass
        except Exception:
            pass

    def resend_login_otp(self, email):
        """
        Resend OTP for 2FA login
        إعادة إرسال OTP لتسجيل الدخول
        """
        try:
            result = anvil.server.call('resend_login_otp', email)
            return result
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}

    def verify_registration_otp(self, email, otp):
        """
        Verify OTP for email verification
        التحقق من OTP للتسجيل
        """
        try:
            result = anvil.server.call('verify_registration_otp', email, otp)
            return result
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}

    def resend_verification_otp(self, email):
        """
        Resend verification OTP
        إعادة إرسال OTP للتحقق من البريد
        """
        try:
            result = anvil.server.call('resend_verification_otp', email)
            return result
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}

    # =========================================
    # Forgot Password functions
    # =========================================
    def request_password_reset(self, email):
        """
        Request password reset - sends OTP to email
        طلب إعادة تعيين كلمة المرور
        """
        try:
            result = anvil.server.call('request_password_reset', email)
            return result
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}

    def verify_password_reset_otp(self, email, otp):
        """
        Verify OTP for password reset
        التحقق من OTP لإعادة تعيين كلمة المرور
        """
        try:
            result = anvil.server.call('verify_password_reset_otp', email, otp)
            return result
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}

    def complete_password_reset(self, email, new_password):
        """
        Complete password reset with new password
        إتمام إعادة تعيين كلمة المرور
        """
        try:
            result = anvil.server.call('complete_password_reset', email, new_password)
            return result
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}

    def clear_rate_limit(self):
        """
        مسح Rate Limit للـ IP الحالي
        """
        try:
            result = anvil.server.call('clear_my_rate_limit')
            return result
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}

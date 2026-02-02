"""
LoginForm - صفحة تسجيل الدخول والتسجيل
======================================
- تسجيل الدخول
- تسجيل مستخدم جديد (مع رقم التليفون)
- إعداد الأدمن الأولي
"""

from ._anvil_designer import LoginFormTemplate
from anvil import *
import anvil.google.auth, anvil.google.drive
from anvil.google.drive import app_files
import anvil.server
import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables
import anvil.js


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

        # Check route on load
        self.check_route()

        # Listen for hash changes
        anvil.js.window.addEventListener("hashchange", self.on_hash_change)

    def on_hash_change(self, event):
        self.check_route()

    def check_route(self):
        hash_val = anvil.js.window.location.hash

        if hash_val == "#launcher":
            open_form('LauncherForm')
        elif hash_val == "#calculator":
            open_form('CalculatorForm')
        elif hash_val == "#admin":
            open_form('AdminPanel')
        elif hash_val == "#import":
            open_form('DataImportForm')

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

            # حفظ معلومات المستخدم في sessionStorage إذا نجح تسجيل الدخول
            if result.get('success') and result.get('user'):
                user = result['user']
                anvil.js.window.sessionStorage.setItem('user_email', user.get('email', ''))
                anvil.js.window.sessionStorage.setItem('user_name', user.get('full_name', ''))
                anvil.js.window.sessionStorage.setItem('user_role', user.get('role', ''))

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
            return result
        except Exception as e:
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

            # حفظ معلومات المستخدم إذا نجح التحقق
            if result.get('success') and result.get('user'):
                user = result['user']
                anvil.js.window.sessionStorage.setItem('user_email', user.get('email', ''))
                anvil.js.window.sessionStorage.setItem('user_name', user.get('full_name', ''))
                anvil.js.window.sessionStorage.setItem('user_role', user.get('role', ''))

            return result
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}

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

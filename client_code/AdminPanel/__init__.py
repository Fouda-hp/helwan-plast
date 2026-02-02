"""
AdminPanel - لوحة تحكم الأدمن
============================
- إدارة المستخدمين والصلاحيات
- عرض سجل التدقيق
- إدارة الإعدادات (سعر الصرف، أسعار الأسطوانات)
- تصدير واستيراد البيانات
"""

from ._anvil_designer import AdminPanelTemplate
from anvil import *
import anvil.server
import anvil.js
import json


class AdminPanel(AdminPanelTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # متغيرات المستخدم الحالي
        self.current_user = None
        self.user_email = ''
        self.user_name = ''

        # التحقق من الجلسة وتحميل بيانات المستخدم
        self._load_user_info()

        # Check route
        self.check_route()
        anvil.js.window.addEventListener("hashchange", self.on_hash_change)

        # Setup JS bridges
        self._setup_js_bridges()

    def _load_user_info(self):
        """تحميل معلومات المستخدم الحالي"""
        try:
            token = self.get_token()
            if token:
                result = anvil.server.call('validate_token', token)
                if result.get('valid'):
                    self.current_user = result['user']
                    self.user_email = self.current_user.get('email', '')
                    self.user_name = self.current_user.get('full_name', '')
        except Exception as e:
            print(f"Error loading user info: {e}")

    def _setup_js_bridges(self):
        """إعداد الجسور مع JavaScript"""
        # معلومات المستخدم
        anvil.js.window.getCurrentUserName = self.get_user_name
        anvil.js.window.getCurrentUserEmail = self.get_user_email
        anvil.js.window.getCurrentUserRole = self.get_user_role

        # Dashboard
        anvil.js.window.getDashboardStats = self.get_dashboard_stats

        # User Management
        anvil.js.window.getPendingUsers = self.get_pending_users
        anvil.js.window.getAllUsers = self.get_all_users
        anvil.js.window.approveUser = self.approve_user
        anvil.js.window.approveUserWithRole = self.approve_user  # Alias for JS
        anvil.js.window.approveUserWithPermissions = self.approve_user_with_permissions
        anvil.js.window.rejectUser = self.reject_user
        anvil.js.window.rejectUserAPI = self.reject_user  # For new approval modal
        anvil.js.window.updateUserRole = self.update_user_role
        anvil.js.window.updateUserRoleWithPermissions = self.update_user_role_with_permissions
        anvil.js.window.toggleUserActive = self.toggle_user_active
        anvil.js.window.resetUserPassword = self.reset_user_password
        anvil.js.window.getAvailablePermissions = self.get_available_permissions

        # Audit Logs
        anvil.js.window.getAuditLogs = self.get_audit_logs

        # Clients & Quotations
        anvil.js.window.getAllClients = self.get_all_clients
        anvil.js.window.getAllQuotations = self.get_all_quotations
        anvil.js.window.softDeleteClient = self.soft_delete_client
        anvil.js.window.softDeleteQuotation = self.soft_delete_quotation
        anvil.js.window.restoreClient = self.restore_client
        anvil.js.window.restoreQuotation = self.restore_quotation

        # Export
        anvil.js.window.exportClientsData = self.export_clients_data
        anvil.js.window.exportQuotationsData = self.export_quotations_data

        # Settings
        anvil.js.window.getAllSettings = self.get_all_settings
        anvil.js.window.updateSetting = self.update_setting
        anvil.js.window.getSetting = self.get_setting

        # Navigation
        anvil.js.window.openDataImport = self.open_data_import
        anvil.js.window.logoutUser = self.logout_user

        # Debug
        anvil.js.window.debugAdminCheck = self.debug_admin_check

    # =========================================================
    # التوجيه
    # =========================================================
    def on_hash_change(self, event):
        self.check_route()

    def check_route(self):
        hash_val = anvil.js.window.location.hash
        if hash_val == "#launcher":
            open_form('LauncherForm')
        elif hash_val == "#calculator":
            open_form('CalculatorForm')
        elif hash_val == "#import":
            open_form('DataImportForm')
        elif hash_val == "#login" or hash_val == "":
            open_form('LoginForm')

    # =========================================================
    # معلومات المستخدم
    # =========================================================
    def get_email(self):
        """Get user email from session storage"""
        return anvil.js.window.sessionStorage.getItem('user_email') or self.user_email

    def get_token(self):
        """Get auth token from session storage"""
        return anvil.js.window.sessionStorage.getItem('auth_token')

    def get_auth(self):
        """Get email for auth (more reliable than token)"""
        # استخدام الإيميل مباشرة لأنه أكثر موثوقية
        email = self.get_email()
        if email:
            return email
        # fallback للـ token
        return self.get_token()

    def get_user_name(self):
        """الحصول على اسم المستخدم"""
        if self.user_name:
            return self.user_name
        return anvil.js.window.sessionStorage.getItem('user_name') or 'Admin'

    def get_user_email(self):
        """الحصول على بريد المستخدم"""
        return self.get_email()

    def get_user_role(self):
        """الحصول على دور المستخدم"""
        if self.current_user:
            return self.current_user.get('role', 'admin')
        return anvil.js.window.sessionStorage.getItem('user_role') or 'admin'

    # =========================================================
    # Dashboard
    # =========================================================
    def get_dashboard_stats(self):
        return anvil.server.call('get_dashboard_stats')

    # =========================================================
    # User Management
    # =========================================================
    def get_pending_users(self):
        return anvil.server.call('get_pending_users', self.get_auth())

    def get_all_users(self):
        return anvil.server.call('get_all_users', self.get_auth())

    def get_available_permissions(self):
        """الحصول على الصلاحيات المتاحة"""
        return anvil.server.call('get_available_permissions')

    def approve_user(self, user_id, role):
        return anvil.server.call('approve_user', self.get_auth(), user_id, role)

    def approve_user_with_permissions(self, user_id, role, permissions):
        """الموافقة على مستخدم مع صلاحيات مخصصة"""
        return anvil.server.call('approve_user', self.get_auth(), user_id, role, permissions)

    def reject_user(self, user_id):
        return anvil.server.call('reject_user', self.get_auth(), user_id)

    def update_user_role(self, user_id, new_role):
        return anvil.server.call('update_user_role', self.get_auth(), user_id, new_role)

    def update_user_role_with_permissions(self, user_id, new_role, permissions):
        """تحديث دور المستخدم مع صلاحيات مخصصة"""
        return anvil.server.call('update_user_role', self.get_auth(), user_id, new_role, permissions)

    def toggle_user_active(self, user_id):
        return anvil.server.call('toggle_user_active', self.get_auth(), user_id)

    def reset_user_password(self, user_id, new_password):
        return anvil.server.call('reset_user_password', self.get_auth(), user_id, new_password)

    # =========================================================
    # Audit Logs
    # =========================================================
    def get_audit_logs(self, limit, offset, filters):
        return anvil.server.call('get_audit_logs', self.get_auth(), limit, offset, filters)

    # =========================================================
    # Clients & Quotations
    # =========================================================
    def get_all_clients(self, page, per_page, search, include_deleted):
        return anvil.server.call('get_all_clients', page, per_page, search, include_deleted)

    def get_all_quotations(self, page, per_page, search, include_deleted):
        return anvil.server.call('get_all_quotations', page, per_page, search, include_deleted)

    def soft_delete_client(self, client_code):
        return anvil.server.call('soft_delete_client', client_code, self.get_auth())

    def soft_delete_quotation(self, quotation_number):
        return anvil.server.call('soft_delete_quotation', quotation_number, self.get_auth())

    def restore_client(self, client_code):
        return anvil.server.call('restore_client', client_code, self.get_auth())

    def restore_quotation(self, quotation_number):
        return anvil.server.call('restore_quotation', quotation_number, self.get_auth())

    # =========================================================
    # Export
    # =========================================================
    def export_clients_data(self, include_deleted):
        return anvil.server.call('export_clients_data', include_deleted)

    def export_quotations_data(self, include_deleted):
        return anvil.server.call('export_quotations_data', include_deleted)

    # =========================================================
    # Settings Management (سعر الصرف، أسعار الأسطوانات)
    # =========================================================
    def get_all_settings(self):
        """الحصول على جميع الإعدادات"""
        return anvil.server.call('get_all_settings', self.get_auth())

    def update_setting(self, key, value):
        """تحديث إعداد معين"""
        return anvil.server.call('update_setting', self.get_auth(), key, value)

    def get_setting(self, key):
        """الحصول على قيمة إعداد معين"""
        return anvil.server.call('get_setting', key)

    # =========================================================
    # Navigation
    # =========================================================
    def open_data_import(self):
        """فتح صفحة استيراد البيانات"""
        try:
            from ..DataImportForm import DataImportForm
            open_form("DataImportForm")
        except Exception as e:
            alert(f"Error opening DataImportForm: {e}")

    # =========================================================
    # Debug
    # =========================================================
    def debug_admin_check(self):
        """Debug function to check admin access"""
        return anvil.server.call('debug_admin_check', self.get_auth())

    # =========================================================
    # Logout
    # =========================================================
    def logout_user(self):
        token = self.get_token()
        if token:
            try:
                anvil.server.call('logout_user', token)
            except:
                pass
        anvil.js.window.sessionStorage.clear()
        return True

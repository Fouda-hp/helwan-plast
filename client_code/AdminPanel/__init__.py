from ._anvil_designer import AdminPanelTemplate
from anvil import *
import anvil.server
import anvil.js


class AdminPanel(AdminPanelTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Check route
        self.check_route()
        anvil.js.window.addEventListener("hashchange", self.on_hash_change)

        # Setup JS bridges
        anvil.js.window.getDashboardStats = self.get_dashboard_stats
        anvil.js.window.getPendingUsers = self.get_pending_users
        anvil.js.window.getAllUsers = self.get_all_users
        anvil.js.window.approveUser = self.approve_user
        anvil.js.window.rejectUser = self.reject_user
        anvil.js.window.updateUserRole = self.update_user_role
        anvil.js.window.toggleUserActive = self.toggle_user_active
        anvil.js.window.resetUserPassword = self.reset_user_password
        anvil.js.window.getAuditLogs = self.get_audit_logs
        anvil.js.window.getAllClients = self.get_all_clients
        anvil.js.window.getAllQuotations = self.get_all_quotations
        anvil.js.window.softDeleteClient = self.soft_delete_client
        anvil.js.window.softDeleteQuotation = self.soft_delete_quotation
        anvil.js.window.restoreClient = self.restore_client
        anvil.js.window.restoreQuotation = self.restore_quotation
        anvil.js.window.exportClientsData = self.export_clients_data
        anvil.js.window.exportQuotationsData = self.export_quotations_data
        anvil.js.window.logoutUser = self.logout_user

    def on_hash_change(self, event):
        self.check_route()

    def check_route(self):
        hash_val = anvil.js.window.location.hash
        if hash_val == "#launcher":
            open_form('LauncherForm')
        elif hash_val == "#calculator":
            open_form('CalculatorForm')
        elif hash_val == "#login" or hash_val == "":
            open_form('LoginForm')

    def get_email(self):
        """Get user email from session storage"""
        return anvil.js.window.sessionStorage.getItem('user_email')

    def get_token(self):
        """Get auth token from session storage"""
        return anvil.js.window.sessionStorage.getItem('auth_token')

    def get_auth(self):
        """Get token or email for auth - email as fallback"""
        token = self.get_token()
        if token:
            return token
        return self.get_email()

    # Dashboard
    def get_dashboard_stats(self):
        return anvil.server.call('get_dashboard_stats')

    # User Management - Use email as fallback for auth
    def get_pending_users(self):
        return anvil.server.call('get_pending_users', self.get_auth())

    def get_all_users(self):
        return anvil.server.call('get_all_users', self.get_auth())

    def approve_user(self, user_id, role):
        return anvil.server.call('approve_user', self.get_auth(), user_id, role)

    def reject_user(self, user_id):
        return anvil.server.call('reject_user', self.get_auth(), user_id)

    def update_user_role(self, user_id, new_role):
        return anvil.server.call('update_user_role', self.get_auth(), user_id, new_role)

    def toggle_user_active(self, user_id):
        return anvil.server.call('toggle_user_active', self.get_auth(), user_id)

    def reset_user_password(self, user_id, new_password):
        return anvil.server.call('reset_user_password', self.get_auth(), user_id, new_password)

    # Audit Logs
    def get_audit_logs(self, limit, offset, filters):
        return anvil.server.call('get_audit_logs', self.get_auth(), limit, offset, filters)

    # Clients & Quotations
    def get_all_clients(self, page, per_page, search, include_deleted):
        return anvil.server.call('get_all_clients', page, per_page, search, include_deleted)

    def get_all_quotations(self, page, per_page, search, include_deleted):
        return anvil.server.call('get_all_quotations', page, per_page, search, include_deleted)

    def soft_delete_client(self, client_code):
        email = self.get_email()
        return anvil.server.call('soft_delete_client', client_code, email)

    def soft_delete_quotation(self, quotation_number):
        email = self.get_email()
        return anvil.server.call('soft_delete_quotation', quotation_number, email)

    def restore_client(self, client_code):
        email = self.get_email()
        return anvil.server.call('restore_client', client_code, email)

    def restore_quotation(self, quotation_number):
        email = self.get_email()
        return anvil.server.call('restore_quotation', quotation_number, email)

    # Export
    def export_clients_data(self, include_deleted):
        return anvil.server.call('export_clients_data', include_deleted)

    def export_quotations_data(self, include_deleted):
        return anvil.server.call('export_quotations_data', include_deleted)

    # Logout
    def logout_user(self):
        token = self.get_token()
        if token:
            try:
                anvil.server.call('logout_user', token)
            except:
                pass
        anvil.js.window.sessionStorage.clear()
        return True

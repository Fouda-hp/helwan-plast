from ._anvil_designer import LoginFormTemplate
from anvil import *
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

    # =========================================
    # Bridge functions for JavaScript
    # =========================================
    def login_user(self, email, password):
        """Login user - called from JavaScript"""
        try:
            result = anvil.server.call('login_user', email, password)
            return result
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}

    def register_user(self, email, password, full_name):
        """Register user - called from JavaScript"""
        try:
            result = anvil.server.call('register_user', email, password, full_name)
            return result
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}

    def setup_admin(self, email, password, full_name):
        """Setup initial admin - called from JavaScript"""
        try:
            result = anvil.server.call('setup_initial_admin', email, password, full_name)
            return result
        except Exception as e:
            return {'success': False, 'message': f'Error: {str(e)}'}

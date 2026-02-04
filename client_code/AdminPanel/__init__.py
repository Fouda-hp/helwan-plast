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
import anvil.google.auth, anvil.google.drive
from anvil.google.drive import app_files
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
        self._inject_admin_panel_enhancements()

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
        anvil.js.window.deleteUser = self.delete_user

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

    def _inject_admin_panel_enhancements(self):
        """حقن تحسينات واجهة الأدمن بدون تعديل القالب"""
        js_code = """
        (function() {
          function buildNavItem(id) {
            var item = document.createElement('a');
            item.className = 'nav-item';
            item.id = id;
            item.href = '#';
            item.innerHTML = '<svg viewBox="0 0 24 24"><path d="M5 20h14v-2H5v2zM12 2l-5.5 5.5 1.42 1.42L11 6.34V16h2V6.34l3.08 3.08 1.42-1.42L12 2z"/></svg><span>Data Import</span>';
            item.onclick = function(e) {
              e.preventDefault();
              e.stopPropagation();
              if (window.openDataImport) window.openDataImport();
            };
            return item;
          }

          function insertDataImportNav() {
            var topNav = document.querySelector('.header-row-nav');
            if (topNav && !document.getElementById('navDataImportTop')) {
              var settingsItem = topNav.querySelector('.nav-item[data-panel="settings"]');
              var item = buildNavItem('navDataImportTop');
              if (settingsItem && settingsItem.parentNode) {
                settingsItem.parentNode.insertBefore(item, settingsItem);
              } else {
                topNav.appendChild(item);
              }
            }

            var mobileMenu = document.getElementById('mobileMenu');
            if (mobileMenu && !document.getElementById('navDataImportMobile')) {
              var mobileSettings = mobileMenu.querySelector('.nav-item[data-panel="settings"]');
              var mobileItem = buildNavItem('navDataImportMobile');
              if (mobileSettings && mobileSettings.parentNode) {
                mobileSettings.parentNode.insertBefore(mobileItem, mobileSettings);
              } else {
                mobileMenu.appendChild(mobileItem);
              }
            }
          }

          function patchSaveSetting() {
            if (!window.saveSetting || window.saveSetting.__patched) return;
            var original = window.saveSetting;
            window.saveSetting = async function(key, isPercent) {
              var result = await original(key, isPercent);
              if (key === 'exchange_rate') {
                var input = document.getElementById('setting_exchange_rate');
                if (input && input.value) {
                  localStorage.setItem('exchange_rate', String(input.value));
                }
              }
              return result;
            };
            window.saveSetting.__patched = true;
          }

          function normalizeValues(values) {
            if (!values) return [];
            if (Array.isArray(values)) return values;
            if (typeof values === 'string') {
              return values
                .split(/\\n|,/)
                .map(function(v) { return v.trim(); })
                .filter(Boolean);
            }
            return [];
          }

          function getDefaultSpecs() {
            return [
              { label_ar: 'الموديل', label_en: 'Model', source: 'field', values: ['model'], active: true },
              { label_ar: 'عدد الألوان', label_en: 'Number of Colors', source: 'field', values: ['colors_display'], active: true },
              { label_ar: 'أوجه الطباعة', label_en: 'Printing Sides', source: 'field', values: ['printing_sides'], active: true },
              { label_ar: 'وحدات التحكم في الشد', label_en: 'Tension Control Units', source: 'field', values: ['tension_units'], active: true },
              { label_ar: 'نظام الفرامل', label_en: 'Brake System', source: 'field', values: ['brake_system'], active: true },
              { label_ar: 'قوة الفرامل', label_en: 'Brake Power', source: 'field', values: ['brake_power'], active: true },
              { label_ar: 'نظام توجيه الخامة', label_en: 'Web Guiding System', source: 'field', values: ['web_guiding'], active: true },
              { label_ar: 'أقصى عرض للفيلم', label_en: 'Maximum Film Width', source: 'field', values: ['max_film_width'], active: true },
              { label_ar: 'أقصى عرض للطباعة', label_en: 'Maximum Printing Width', source: 'field', values: ['max_print_width'], active: true },
              { label_ar: 'طول الطباعة', label_en: 'Printing Length', source: 'field', values: ['print_length'], active: true },
              { label_ar: 'أقصى قطر للرول', label_en: 'Maximum Roll Diameter', source: 'field', values: ['max_roll_diameter'], active: true },
              { label_ar: 'نوع الأنيلوكس', label_en: 'Anilox Type', source: 'field', values: ['anilox_display'], active: true },
              { label_ar: 'أقصى سرعة للماكينة', label_en: 'Maximum Machine Speed', source: 'field', values: ['max_machine_speed'], active: true },
              { label_ar: 'أقصى سرعة للطباعة', label_en: 'Maximum Printing Speed', source: 'field', values: ['max_print_speed'], active: true },
              { label_ar: 'قدرة المجفف', label_en: 'Dryer Capacity', source: 'field', values: ['dryer_capacity'], active: true },
              { label_ar: 'طريقة نقل القدرة', label_en: 'Power Transmission Method', source: 'field', values: ['drive_display'], active: true },
              { label_ar: 'قدرة الموتور الرئيسي', label_en: 'Main Motor Power', source: 'field', values: ['main_motor_power'], active: true },
              { label_ar: 'الفحص بالفيديو', label_en: 'Video Inspection', source: 'yes_no', values: ['video_inspection'], active: true },
              { label_ar: 'PLC', label_en: 'PLC', source: 'yes_no', values: ['plc'], active: true },
              { label_ar: 'سليتر', label_en: 'Slitter', source: 'yes_no', values: ['slitter'], active: true }
            ];
          }

          function normalizeTechSpecs(raw) {
            if (Array.isArray(raw)) return raw.map(function(s) {
              return {
                id: s.id || String(Date.now() + Math.random()),
                label_ar: s.label_ar || '',
                label_en: s.label_en || '',
                source: s.source || 'field',
                values: normalizeValues(s.values),
                active: s.active !== false
              };
            });

            var defaults = getDefaultSpecs();
            if (raw && typeof raw === 'object') {
              return defaults.map(function(def, index) {
                var key = 'tech_spec_' + (index + 1);
                var saved = raw[key] || {};
                return {
                  id: saved.id || String(index + 1),
                  label_ar: saved.label_ar || def.label_ar,
                  label_en: saved.label_en || def.label_en,
                  source: saved.source || def.source,
                  values: normalizeValues(saved.values || saved.value_keys || def.values),
                  active: saved.active !== false
                };
              });
            }
            return defaults;
          }

          function buildSpecRow(spec, index) {
            var valuesText = (spec.values || []).join('\\n');
            return '' +
              '<tr data-tech-spec-row data-spec-id=\"' + spec.id + '\">' +
              '<td style=\"padding:8px;border:1px solid #ddd;text-align:center;font-weight:bold;\">' + (index + 1) + '</td>' +
              '<td style=\"padding:8px;border:1px solid #ddd;\"><input type=\"text\" class=\"tech-label-ar\" value=\"' + (spec.label_ar || '') + '\" style=\"width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;\" dir=\"rtl\"></td>' +
              '<td style=\"padding:8px;border:1px solid #ddd;\"><input type=\"text\" class=\"tech-label-en\" value=\"' + (spec.label_en || '') + '\" style=\"width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;\"></td>' +
              '<td style=\"padding:8px;border:1px solid #ddd;\">' +
                '<select class=\"tech-source\" style=\"width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;\">' +
                  '<option value=\"field\"' + (spec.source === 'field' ? ' selected' : '') + '>From Field</option>' +
                  '<option value=\"fixed\"' + (spec.source === 'fixed' ? ' selected' : '') + '>Fixed Value</option>' +
                  '<option value=\"yes_no\"' + (spec.source === 'yes_no' ? ' selected' : '') + '>Yes/No Field</option>' +
                '</select>' +
              '</td>' +
              '<td style=\"padding:8px;border:1px solid #ddd;\">' +
                '<textarea class=\"tech-values\" rows=\"2\" style=\"width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;\" placeholder=\"Multiple values, one per line\">' + valuesText + '</textarea>' +
              '</td>' +
              '<td style=\"padding:8px;border:1px solid #ddd;text-align:center;\">' +
                '<input type=\"checkbox\" class=\"tech-active\"' + (spec.active ? ' checked' : '') + ' style=\"width:20px;height:20px;\">' +
              '</td>' +
              '<td style=\"padding:8px;border:1px solid #ddd;text-align:center;\">' +
                '<button class=\"btn-sm delete\" onclick=\"removeTechSpecRow(\\'' + spec.id + '\\')\">Delete</button>' +
              '</td>' +
              '</tr>';
          }

          async function enhanceTechSpecsSettings() {
            var container = document.getElementById('settingsContent');
            if (!container) return;

            var heading = Array.from(container.querySelectorAll('h4')).find(function(h) {
              return h.textContent && h.textContent.indexOf('Technical Specifications Table Settings') !== -1;
            });
            if (!heading) return;

            var section = heading.closest('div');
            if (!section) return;

            var result = await window.getAllSettings();
            if (!result || !result.success) return;

            var settings = result.settings || {};
            var rawSpecs = settings.technical_specs ? JSON.parse(settings.technical_specs) : null;
            var specsList = normalizeTechSpecs(rawSpecs);

            var tableHtml = '' +
              '<h4 style=\"margin:0 0 10px;color:#1565c0;\">📋 Technical Specifications Table Settings</h4>' +
              '<p style=\"margin:0 0 15px;color:#666;font-size:13px;\">Configure labels, sources, and multiple values per row.</p>' +
              '<div style=\"background:#fff;padding:15px;border-radius:8px;overflow-x:auto;\">' +
                '<table style=\"width:100%;border-collapse:collapse;font-size:13px;\">' +
                  '<thead><tr style=\"background:#f5f5f5;\">' +
                    '<th style=\"padding:10px;border:1px solid #ddd;text-align:center;\">#</th>' +
                    '<th style=\"padding:10px;border:1px solid #ddd;\">Label (AR)</th>' +
                    '<th style=\"padding:10px;border:1px solid #ddd;\">Label (EN)</th>' +
                    '<th style=\"padding:10px;border:1px solid #ddd;\">Value Source</th>' +
                    '<th style=\"padding:10px;border:1px solid #ddd;\">Values</th>' +
                    '<th style=\"padding:10px;border:1px solid #ddd;text-align:center;\">Active</th>' +
                    '<th style=\"padding:10px;border:1px solid #ddd;text-align:center;\">Actions</th>' +
                  '</tr></thead>' +
                  '<tbody id=\"techSpecsBody\">' +
                    specsList.map(buildSpecRow).join('') +
                  '</tbody>' +
                '</table>' +
              '</div>' +
              '<div style=\"margin-top:15px;display:flex;gap:10px;justify-content:center;\">' +
                '<button class=\"action-btn\" onclick=\"addTechSpecRow()\">➕ Add Row</button>' +
                '<button class=\"action-btn green\" onclick=\"saveTechSpecs()\" style=\"padding:12px 30px;background:#4caf50;\">💾 Save All Technical Specs</button>' +
              '</div>';

            section.innerHTML = tableHtml;

            window.addTechSpecRow = function() {
              var tbody = document.getElementById('techSpecsBody');
              if (!tbody) return;
              var spec = { id: String(Date.now()), label_ar: '', label_en: '', source: 'field', values: [], active: true };
              tbody.insertAdjacentHTML('beforeend', buildSpecRow(spec, tbody.children.length));
            };

            window.removeTechSpecRow = function(id) {
              var row = container.querySelector('[data-spec-id=\"' + id + '\"]');
              if (row && row.parentNode) row.parentNode.removeChild(row);
            };

            window.saveTechSpecs = async function() {
              var rows = container.querySelectorAll('[data-tech-spec-row]');
              var specsData = [];
              rows.forEach(function(row) {
                var labelAr = row.querySelector('.tech-label-ar');
                var labelEn = row.querySelector('.tech-label-en');
                var source = row.querySelector('.tech-source');
                var values = row.querySelector('.tech-values');
                var active = row.querySelector('.tech-active');

                specsData.push({
                  id: row.getAttribute('data-spec-id'),
                  label_ar: labelAr ? labelAr.value : '',
                  label_en: labelEn ? labelEn.value : '',
                  source: source ? source.value : 'field',
                  values: normalizeValues(values ? values.value : ''),
                  active: active ? active.checked : true
                });
              });

              try {
                var result = await window.updateSetting('technical_specs', JSON.stringify(specsData));
                if (result && result.success) {
                  if (window.showNotification) {
                    window.showNotification('success', 'Saved!', 'Technical Specifications saved successfully');
                  } else {
                    alert('Technical Specifications saved successfully');
                  }
                } else {
                  alert(result ? result.message : 'Error saving settings');
                }
              } catch (e) {
                alert('Error saving: ' + e);
              }
            };
          }

          function patchLoadSettings() {
            if (!window.loadSettings || window.loadSettings.__patched) return;
            var original = window.loadSettings;
            window.loadSettings = async function() {
              await original();
              setTimeout(enhanceTechSpecsSettings, 50);
            };
            window.loadSettings.__patched = true;
          }

          function run() {
            insertDataImportNav();
            patchSaveSetting();
            patchLoadSettings();
          }

          if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', run);
          } else {
            setTimeout(run, 0);
          }
        })();
        """
        anvil.js.window.eval(js_code)

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
        """Get user email from localStorage (with sessionStorage fallback)"""
        email = anvil.js.window.localStorage.getItem('user_email')
        if not email:
            # Fallback to sessionStorage for backwards compatibility
            email = anvil.js.window.sessionStorage.getItem('user_email')
            if email:
                # Migrate to localStorage
                anvil.js.window.localStorage.setItem('user_email', email)
        return email or self.user_email

    def get_token(self):
        """Get auth token from localStorage (with sessionStorage fallback)"""
        token = anvil.js.window.localStorage.getItem('auth_token')
        if not token:
            # Fallback to sessionStorage for backwards compatibility
            token = anvil.js.window.sessionStorage.getItem('auth_token')
            if token:
                # Migrate to localStorage
                anvil.js.window.localStorage.setItem('auth_token', token)
        return token

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
        return anvil.js.window.localStorage.getItem('user_name') or 'Admin'

    def get_user_email(self):
        """الحصول على بريد المستخدم"""
        return self.get_email()

    def get_user_role(self):
        """الحصول على دور المستخدم"""
        if self.current_user:
            return self.current_user.get('role', 'admin')
        return anvil.js.window.localStorage.getItem('user_role') or 'admin'

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

    def delete_user(self, user_id):
        """حذف مستخدم نهائياً"""
        return anvil.server.call('delete_user_permanently', self.get_auth(), user_id)

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
        auth = self.get_auth()
        print(f"get_all_settings called with auth: {auth}")
        if not auth:
            return {'success': False, 'message': 'Not authenticated. Please login again.'}
        return anvil.server.call('get_all_settings', auth)

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
        anvil.js.window.localStorage.clear()
        return True

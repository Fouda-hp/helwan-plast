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
        anvil.js.window.getMachinePrices = self.get_machine_prices
        anvil.js.window.saveMachinePrices = self.save_machine_prices
        anvil.js.window.getMachineConfig = self.get_machine_config
        anvil.js.window.saveMachineConfig = self.save_machine_config

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
            // Override saveSetting completely to fix sync issues
            window.saveSetting = async function(key, isPercent) {
              var input = document.getElementById('setting_' + key);
              if (!input) {
                if (window.showNotification) {
                  window.showNotification('error', 'Error', 'Input field not found for: ' + key);
                }
                return;
              }

              var value = parseFloat(input.value);
              if (isNaN(value)) {
                if (window.showNotification) {
                  window.showNotification('error', 'Error', 'Please enter a valid number');
                } else {
                  alert('Please enter a valid number');
                }
                return;
              }

              if (isPercent) {
                value = value / 100;
              }

              try {
                var result = await window.updateSetting(key, value);
                if (result && result.success) {
                  // Sync to localStorage for important settings
                  if (key === 'exchange_rate') {
                    localStorage.setItem('exchange_rate', String(input.value));
                    // Dispatch storage event for other tabs
                    window.dispatchEvent(new StorageEvent('storage', {
                      key: 'exchange_rate',
                      newValue: String(input.value)
                    }));
                  }
                  
                  if (window.showNotification) {
                    window.showNotification('success', 'Saved!', key + ' updated successfully');
                  }
                } else {
                  if (window.showNotification) {
                    window.showNotification('error', 'Error', result ? result.message : 'Error saving setting');
                  } else {
                    alert(result ? result.message : 'Error saving setting');
                  }
                }
              } catch (e) {
                if (window.showNotification) {
                  window.showNotification('error', 'Error', 'Error saving setting: ' + e);
                } else {
                  alert('Error saving setting: ' + e);
                }
              }
            };

            // Also override saveSettingText for text fields
            window.saveSettingText = async function(key) {
              var input = document.getElementById('setting_' + key);
              if (!input) return;

              var value = input.value.trim();
              if (!value) {
                if (window.showNotification) {
                  window.showNotification('error', 'Error', 'Please enter a value');
                } else {
                  alert('Please enter a value');
                }
                return;
              }

              try {
                var result = await window.updateSetting(key, value);
                if (result && result.success) {
                  if (window.showNotification) {
                    window.showNotification('success', 'Saved!', key + ' updated successfully');
                  }
                } else {
                  if (window.showNotification) {
                    window.showNotification('error', 'Error', result ? result.message : 'Error saving setting');
                  } else {
                    alert(result ? result.message : 'Error saving setting');
                  }
                }
              } catch (e) {
                if (window.showNotification) {
                  window.showNotification('error', 'Error', 'Error saving setting: ' + e);
                } else {
                  alert('Error saving setting: ' + e);
                }
              }
            };
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
              { id: '1', label_ar: 'الموديل', label_en: 'Model', source: 'field', values: ['model'], active: true },
              { id: '2', label_ar: 'عدد الألوان', label_en: 'Number of Colors', source: 'field', values: ['colors_display'], active: true },
              { id: '3', label_ar: 'أوجه الطباعة', label_en: 'Printing Sides', source: 'field', values: ['printing_sides'], active: true },
              { id: '4', label_ar: 'وحدات التحكم في الشد', label_en: 'Tension Control Units', source: 'field', values: ['tension_units'], active: true },
              { id: '5', label_ar: 'نظام الفرامل', label_en: 'Brake System', source: 'field', values: ['brake_system'], active: true },
              { id: '6', label_ar: 'قوة الفرامل', label_en: 'Brake Power', source: 'field', values: ['brake_power'], active: true },
              { id: '7', label_ar: 'نظام توجيه الخامة (النوع المتأرجح)', label_en: 'Web Guiding System (Oscillating Type)', source: 'field', values: ['web_guiding'], active: true },
              { id: '8', label_ar: 'أقصى عرض للفيلم', label_en: 'Maximum Film Width', source: 'field', values: ['max_film_width'], active: true },
              { id: '9', label_ar: 'أقصى عرض للطباعة', label_en: 'Maximum Printing Width', source: 'field', values: ['max_print_width'], active: true },
              { id: '10', label_ar: 'الحد الأدنى والأقصى لطول الطباعة', label_en: 'Minimum and Maximum Printing Length', source: 'field', values: ['print_length'], active: true },
              { id: '11', label_ar: 'أقصى قطر للرول', label_en: 'Maximum Roll Diameter', source: 'field', values: ['max_roll_diameter'], active: true },
              { id: '12', label_ar: 'نوع الأنيلوكس', label_en: 'Anilox Type', source: 'field', values: ['anilox_display'], active: true },
              { id: '13', label_ar: 'أقصى سرعة للماكينة', label_en: 'Maximum Machine Speed', source: 'field', values: ['max_machine_speed'], active: true },
              { id: '14', label_ar: 'أقصى سرعة للطباعة', label_en: 'Maximum Printing Speed', source: 'field', values: ['max_print_speed'], active: true },
              { id: '15', label_ar: 'قدرة المجفف', label_en: 'Dryer Capacity', source: 'field', values: ['dryer_capacity'], active: true },
              { id: '16', label_ar: 'طريقة نقل القدرة', label_en: 'Power Transmission Method', source: 'field', values: ['drive_display'], active: true },
              { id: '17', label_ar: 'قدرة الموتور الرئيسي', label_en: 'Main Motor Power', source: 'field', values: ['main_motor_power'], active: true },
              { id: '18', label_ar: 'الفحص بالفيديو', label_en: 'Video Inspection', source: 'yes_no', values: ['video_inspection'], active: true },
              { id: '19', label_ar: 'PLC', label_en: 'PLC', source: 'yes_no', values: ['plc'], active: true },
              { id: '20', label_ar: 'سليتر', label_en: 'Slitter', source: 'yes_no', values: ['slitter'], active: true }
            ];
          }
          
          // Available field keys for dropdown
          function getAvailableFields() {
            return [
              { key: 'model', label: 'Model (from quotation)' },
              { key: 'colors_display', label: 'Number of Colors (calculated)' },
              { key: 'printing_sides', label: 'Printing Sides (fixed: 2)' },
              { key: 'tension_units', label: 'Tension Control Units (winder based)' },
              { key: 'brake_system', label: 'Brake System (winder based)' },
              { key: 'brake_power', label: 'Brake Power (winder based)' },
              { key: 'web_guiding', label: 'Web Guiding (winder based)' },
              { key: 'max_film_width', label: 'Max Film Width (width*10+50)' },
              { key: 'max_print_width', label: 'Max Print Width (width*10-40)' },
              { key: 'print_length', label: 'Print Length (belt/gear)' },
              { key: 'max_roll_diameter', label: 'Max Roll Diameter (winder based)' },
              { key: 'anilox_display', label: 'Anilox Type (metal/ceramic)' },
              { key: 'max_machine_speed', label: 'Max Machine Speed (belt/gear)' },
              { key: 'max_print_speed', label: 'Max Print Speed (belt/gear)' },
              { key: 'dryer_capacity', label: 'Dryer Capacity (from settings)' },
              { key: 'drive_display', label: 'Power Transmission (belt/gear)' },
              { key: 'main_motor_power', label: 'Main Motor Power (from settings)' },
              { key: 'video_inspection', label: 'Video Inspection (yes/no)' },
              { key: 'plc', label: 'PLC (yes/no)' },
              { key: 'slitter', label: 'Slitter (yes/no)' }
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

          // Get condition fields for custom rules
          function getConditionFields() {
            return [
              { key: 'winder_type', label: 'Winder Type (Single/Double)' },
              { key: 'drive_type', label: 'Drive Type (Belt/Gear)' },
              { key: 'anilox_type', label: 'Anilox Type (Metal/Ceramic)' },
              { key: 'colors_count', label: 'Colors Count' },
              { key: 'machine_width', label: 'Machine Width' },
              { key: 'video_inspection', label: 'Video Inspection (Yes/No)' },
              { key: 'plc', label: 'PLC (Yes/No)' },
              { key: 'slitter', label: 'Slitter (Yes/No)' }
            ];
          }
          
          function buildSpecRow(spec, index) {
            var valuesText = (spec.values || []).join('\\n');
            var fieldOptions = getAvailableFields().map(function(f) {
              var selected = (spec.values && spec.values.indexOf(f.key) !== -1) ? ' selected' : '';
              return '<option value=\"' + f.key + '\"' + selected + '>' + f.label + '</option>';
            }).join('');
            
            var conditionOptions = getConditionFields().map(function(f) {
              var selected = (spec.condition_field === f.key) ? ' selected' : '';
              return '<option value=\"' + f.key + '\"' + selected + '>' + f.label + '</option>';
            }).join('');
            
            var isCustom = spec.source === 'custom';
            var customStyle = isCustom ? '' : 'display:none;';
            var fieldStyle = isCustom ? 'display:none;' : '';
            
            return '' +
              '<tr data-tech-spec-row data-spec-id=\"' + spec.id + '\" data-index=\"' + index + '\">' +
              '<td style=\"padding:8px;border:1px solid #ddd;text-align:center;font-weight:bold;min-width:40px;\" class=\"spec-row-num\">' + (index + 1) + '</td>' +
              '<td style=\"padding:8px;border:1px solid #ddd;text-align:center;min-width:80px;\">' +
                '<div style=\"display:flex;flex-direction:column;gap:4px;align-items:center;\">' +
                  '<button class=\"move-btn\" onclick=\"moveSpecRow(\\'' + spec.id + '\\', -1)\" title=\"Move Up\" style=\"padding:4px 8px;font-size:12px;cursor:pointer;border:1px solid #ccc;border-radius:4px;background:#fff;\">⬆️</button>' +
                  '<button class=\"move-btn\" onclick=\"moveSpecRow(\\'' + spec.id + '\\', 1)\" title=\"Move Down\" style=\"padding:4px 8px;font-size:12px;cursor:pointer;border:1px solid #ccc;border-radius:4px;background:#fff;\">⬇️</button>' +
                '</div>' +
              '</td>' +
              '<td style=\"padding:8px;border:1px solid #ddd;\"><input type=\"text\" class=\"tech-label-ar\" value=\"' + (spec.label_ar || '') + '\" style=\"width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;\" dir=\"rtl\"></td>' +
              '<td style=\"padding:8px;border:1px solid #ddd;\"><input type=\"text\" class=\"tech-label-en\" value=\"' + (spec.label_en || '') + '\" style=\"width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;\"></td>' +
              '<td style=\"padding:8px;border:1px solid #ddd;\">' +
                '<select class=\"tech-source\" onchange=\"toggleCustomRule(this)\" style=\"width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;\">' +
                  '<option value=\"field\"' + (spec.source === 'field' ? ' selected' : '') + '>From Field</option>' +
                  '<option value=\"fixed\"' + (spec.source === 'fixed' ? ' selected' : '') + '>Fixed Value</option>' +
                  '<option value=\"yes_no\"' + (spec.source === 'yes_no' ? ' selected' : '') + '>Yes/No Field (hidden if No)</option>' +
                  '<option value=\"custom\"' + (spec.source === 'custom' ? ' selected' : '') + '>Custom Rule (If-Then)</option>' +
                '</select>' +
              '</td>' +
              '<td style=\"padding:8px;border:1px solid #ddd;\">' +
                '<div class=\"field-inputs\" style=\"' + fieldStyle + '\">' +
                  '<select class=\"tech-field-select\" style=\"width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;margin-bottom:4px;\">' +
                    '<option value=\"\">-- Select Field --</option>' +
                    fieldOptions +
                  '</select>' +
                  '<textarea class=\"tech-values\" rows=\"2\" style=\"width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;\" placeholder=\"Field key or fixed value\">' + valuesText + '</textarea>' +
                '</div>' +
                '<div class=\"custom-rule-inputs\" style=\"' + customStyle + 'font-size:12px;\">' +
                  '<div style=\"margin-bottom:6px;\">' +
                    '<label style=\"display:block;color:#666;margin-bottom:2px;\">IF field:</label>' +
                    '<select class=\"condition-field\" style=\"width:100%;padding:4px;border:1px solid #ddd;border-radius:4px;\">' +
                      '<option value=\"\">-- Select Condition --</option>' +
                      conditionOptions +
                    '</select>' +
                  '</div>' +
                  '<div style=\"margin-bottom:6px;\">' +
                    '<label style=\"display:block;color:#666;margin-bottom:2px;\">Equals:</label>' +
                    '<input type=\"text\" class=\"condition-value\" value=\"' + (spec.condition_value || '') + '\" placeholder=\"e.g. Double, Belt, Yes\" style=\"width:100%;padding:4px;border:1px solid #ddd;border-radius:4px;\">' +
                  '</div>' +
                  '<div style=\"margin-bottom:6px;\">' +
                    '<label style=\"display:block;color:#666;margin-bottom:2px;\">THEN value:</label>' +
                    '<input type=\"text\" class=\"then-value\" value=\"' + (spec.then_value || '') + '\" placeholder=\"Value if true\" style=\"width:100%;padding:4px;border:1px solid #ddd;border-radius:4px;\">' +
                  '</div>' +
                  '<div>' +
                    '<label style=\"display:block;color:#666;margin-bottom:2px;\">ELSE value:</label>' +
                    '<input type=\"text\" class=\"else-value\" value=\"' + (spec.else_value || '') + '\" placeholder=\"Value if false\" style=\"width:100%;padding:4px;border:1px solid #ddd;border-radius:4px;\">' +
                  '</div>' +
                '</div>' +
              '</td>' +
              '<td style=\"padding:8px;border:1px solid #ddd;text-align:center;\">' +
                '<input type=\"checkbox\" class=\"tech-active\"' + (spec.active ? ' checked' : '') + ' style=\"width:20px;height:20px;\">' +
              '</td>' +
              '<td style=\"padding:8px;border:1px solid #ddd;text-align:center;\">' +
                '<button class=\"btn-sm delete\" onclick=\"removeTechSpecRow(\\'' + spec.id + '\\')\" style=\"padding:6px 12px;background:#f44336;color:#fff;border:none;border-radius:4px;cursor:pointer;\">🗑️</button>' +
              '</td>' +
              '</tr>';
          }
          
          window.toggleCustomRule = function(select) {
            var row = select.closest('tr');
            var fieldInputs = row.querySelector('.field-inputs');
            var customInputs = row.querySelector('.custom-rule-inputs');
            if (select.value === 'custom') {
              fieldInputs.style.display = 'none';
              customInputs.style.display = 'block';
            } else {
              fieldInputs.style.display = 'block';
              customInputs.style.display = 'none';
            }
          };

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
              '<p style=\"margin:0 0 15px;color:#666;font-size:13px;\">Configure, reorder, add or delete rows. Items with Yes/No source will be hidden from quotation if value is No.</p>' +
              '<div style=\"background:#fff;padding:15px;border-radius:8px;overflow-x:auto;\">' +
                '<table style=\"width:100%;border-collapse:collapse;font-size:13px;\" id=\"techSpecsTable\">' +
                  '<thead><tr style=\"background:#f5f5f5;\">' +
                    '<th style=\"padding:10px;border:1px solid #ddd;text-align:center;width:40px;\">#</th>' +
                    '<th style=\"padding:10px;border:1px solid #ddd;text-align:center;width:80px;\">Order</th>' +
                    '<th style=\"padding:10px;border:1px solid #ddd;\">Label (AR)</th>' +
                    '<th style=\"padding:10px;border:1px solid #ddd;\">Label (EN)</th>' +
                    '<th style=\"padding:10px;border:1px solid #ddd;\">Value Source</th>' +
                    '<th style=\"padding:10px;border:1px solid #ddd;\">Field / Values</th>' +
                    '<th style=\"padding:10px;border:1px solid #ddd;text-align:center;\">Active</th>' +
                    '<th style=\"padding:10px;border:1px solid #ddd;text-align:center;\">Delete</th>' +
                  '</tr></thead>' +
                  '<tbody id=\"techSpecsBody\">' +
                    specsList.map(buildSpecRow).join('') +
                  '</tbody>' +
                '</table>' +
              '</div>' +
              '<div style=\"margin-top:15px;display:flex;gap:10px;justify-content:center;flex-wrap:wrap;\">' +
                '<button class=\"action-btn\" onclick=\"addTechSpecRow()\" style=\"padding:10px 20px;background:#2196f3;color:#fff;border:none;border-radius:6px;cursor:pointer;\">➕ Add New Row</button>' +
                '<button class=\"action-btn\" onclick=\"resetTechSpecs()\" style=\"padding:10px 20px;background:#ff9800;color:#fff;border:none;border-radius:6px;cursor:pointer;\">🔄 Reset to Defaults</button>' +
                '<button class=\"action-btn green\" onclick=\"saveTechSpecs()\" style=\"padding:12px 30px;background:#4caf50;color:#fff;border:none;border-radius:6px;cursor:pointer;\">💾 Save All</button>' +
              '</div>';

            section.innerHTML = tableHtml;

            // Function to update row numbers after reorder
            function updateRowNumbers() {
              var rows = document.querySelectorAll('#techSpecsBody tr[data-tech-spec-row]');
              rows.forEach(function(row, index) {
                var numCell = row.querySelector('.spec-row-num');
                if (numCell) numCell.textContent = String(index + 1);
                row.setAttribute('data-index', index);
              });
            }
            
            window.addTechSpecRow = function() {
              var tbody = document.getElementById('techSpecsBody');
              if (!tbody) return;
              var spec = { id: String(Date.now()), label_ar: '', label_en: '', source: 'field', values: [], active: true };
              tbody.insertAdjacentHTML('beforeend', buildSpecRow(spec, tbody.children.length));
              updateRowNumbers();
              
              // Scroll to new row
              var newRow = tbody.lastElementChild;
              if (newRow) newRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
            };

            window.removeTechSpecRow = function(id) {
              var row = container.querySelector('[data-spec-id=\"' + id + '\"]');
              if (row && row.parentNode) {
                if (confirm('Are you sure you want to delete this row?')) {
                  row.parentNode.removeChild(row);
                  updateRowNumbers();
                }
              }
            };
            
            window.moveSpecRow = function(id, direction) {
              var tbody = document.getElementById('techSpecsBody');
              if (!tbody) return;
              
              var row = tbody.querySelector('[data-spec-id=\"' + id + '\"]');
              if (!row) return;
              
              if (direction === -1 && row.previousElementSibling) {
                // Move up
                tbody.insertBefore(row, row.previousElementSibling);
              } else if (direction === 1 && row.nextElementSibling) {
                // Move down
                tbody.insertBefore(row.nextElementSibling, row);
              }
              
              updateRowNumbers();
            };
            
            window.resetTechSpecs = function() {
              if (!confirm('Reset to default specifications? This will overwrite your current settings.')) return;
              
              var tbody = document.getElementById('techSpecsBody');
              if (!tbody) return;
              
              var defaults = getDefaultSpecs();
              tbody.innerHTML = defaults.map(buildSpecRow).join('');
              
              if (window.showNotification) {
                window.showNotification('info', 'Reset', 'Specifications reset to defaults. Click Save to apply.');
              }
            };
            
            // Auto-fill value from dropdown selection
            document.addEventListener('change', function(e) {
              if (e.target && e.target.classList.contains('tech-field-select')) {
                var row = e.target.closest('tr');
                if (row) {
                  var textarea = row.querySelector('.tech-values');
                  if (textarea && e.target.value) {
                    textarea.value = e.target.value;
                  }
                }
              }
            });

            window.saveTechSpecs = async function() {
              var rows = container.querySelectorAll('[data-tech-spec-row]');
              var specsData = [];
              rows.forEach(function(row) {
                var labelAr = row.querySelector('.tech-label-ar');
                var labelEn = row.querySelector('.tech-label-en');
                var source = row.querySelector('.tech-source');
                var values = row.querySelector('.tech-values');
                var active = row.querySelector('.tech-active');
                
                // Custom rule fields
                var conditionField = row.querySelector('.condition-field');
                var conditionValue = row.querySelector('.condition-value');
                var thenValue = row.querySelector('.then-value');
                var elseValue = row.querySelector('.else-value');

                var specData = {
                  id: row.getAttribute('data-spec-id'),
                  label_ar: labelAr ? labelAr.value : '',
                  label_en: labelEn ? labelEn.value : '',
                  source: source ? source.value : 'field',
                  values: normalizeValues(values ? values.value : ''),
                  active: active ? active.checked : true
                };
                
                // Add custom rule fields if source is custom
                if (source && source.value === 'custom') {
                  specData.condition_field = conditionField ? conditionField.value : '';
                  specData.condition_value = conditionValue ? conditionValue.value : '';
                  specData.then_value = thenValue ? thenValue.value : '';
                  specData.else_value = elseValue ? elseValue.value : '';
                }
                
                specsData.push(specData);
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
              setTimeout(addMachinePricesSection, 100);
              setTimeout(addMachineConfigSection, 200);
            };
            window.loadSettings.__patched = true;
          }

          // ==========================================
          // Machine Prices Section
          // ==========================================
          async function addMachinePricesSection() {
            var container = document.getElementById('settingsContent');
            if (!container) return;
            
            // Check if already added
            if (document.getElementById('machinePricesSection')) return;
            
            // Load machine prices from server
            var pricesResult = null;
            try {
              if (window.getMachinePrices) {
                pricesResult = await window.getMachinePrices();
              }
            } catch(e) {
              console.error('Error loading machine prices:', e);
            }
            
            var prices = pricesResult && pricesResult.prices ? pricesResult.prices : {
              "Metal anilox": {"4": {"80": 15000, "100": 16000, "120": 17500}, "6": {"80": 25000, "100": 26000, "120": 29000}, "8": {"80": 29000, "100": 32000, "120": 33000}},
              "Ceramic anilox Single Doctor Blade": {"4": {"80": 18000, "100": 19000, "120": 20500}, "6": {"80": 28000, "100": 29000, "120": 32000}, "8": {"80": 32000, "100": 35000, "120": 36000}},
              "Ceramic anilox Chamber Doctor Blade": {"4": {"80": 21168, "100": 22960, "120": 25252}, "6": {"80": 32752, "100": 34940, "120": 39128}, "8": {"80": 38336, "100": 42920, "120": 45504}}
            };
            
            // Find the exchange rate section and add machine prices after it
            var firstGrid = container.querySelector('div[style*="grid-template-columns"]');
            if (!firstGrid) return;
            
            // Find the left column (Exchange Rate)
            var leftCol = firstGrid.querySelector('div[style*="background:#f8f9fa"]');
            if (!leftCol) return;
            
            // Create machine prices HTML
            var html = '<div id="machinePricesSection" style="background:#fff3e0;padding:20px;border-radius:12px;margin-top:20px;border:2px solid #ff9800;">';
            html += '<h4 style="margin:0 0 15px;color:#e65100;">🏭 Machine Prices (USD)</h4>';
            
            var machineTypes = [
              { key: "Metal anilox", label: "Metal Anilox", color: "#90caf9" },
              { key: "Ceramic anilox Single Doctor Blade", label: "Ceramic Single Doctor", color: "#a5d6a7" },
              { key: "Ceramic anilox Chamber Doctor Blade", label: "Ceramic Chamber Doctor", color: "#ce93d8" }
            ];
            
            var colors = ["4", "6", "8"];
            var widths = ["80", "100", "120"];
            
            machineTypes.forEach(function(type) {
              html += '<div style="background:' + type.color + ';padding:12px;border-radius:8px;margin-bottom:12px;">';
              html += '<h5 style="margin:0 0 10px;color:#333;">' + type.label + '</h5>';
              
              // Table for this machine type
              html += '<table style="width:100%;border-collapse:collapse;background:#fff;border-radius:6px;overflow:hidden;font-size:13px;">';
              html += '<thead><tr style="background:#f5f5f5;">';
              html += '<th style="padding:8px;border:1px solid #ddd;text-align:center;">Colors \\\\ Width</th>';
              widths.forEach(function(w) {
                html += '<th style="padding:8px;border:1px solid #ddd;text-align:center;">' + w + ' cm</th>';
              });
              html += '</tr></thead><tbody>';
              
              colors.forEach(function(c) {
                html += '<tr>';
                html += '<td style="padding:8px;border:1px solid #ddd;text-align:center;background:#f9f9f9;font-weight:bold;">' + c + ' Colors</td>';
                widths.forEach(function(w) {
                  var price = prices[type.key] && prices[type.key][c] && prices[type.key][c][w] ? prices[type.key][c][w] : 0;
                  var inputId = 'mp_' + type.key.replace(/\\s+/g, '_') + '_' + c + '_' + w;
                  html += '<td style="padding:4px;border:1px solid #ddd;text-align:center;">';
                  html += '<input type="number" id="' + inputId + '" value="' + price + '" style="width:80px;padding:4px;border:1px solid #ccc;border-radius:4px;text-align:center;" data-machine="' + type.key + '" data-colors="' + c + '" data-width="' + w + '">';
                  html += '</td>';
                });
                html += '</tr>';
              });
              
              html += '</tbody></table></div>';
            });
            
            html += '<div style="margin-top:15px;text-align:center;">';
            html += '<button class="action-btn" onclick="saveMachinePricesAll()" style="padding:12px 30px;background:#ff9800;border:none;color:#fff;font-weight:bold;border-radius:8px;cursor:pointer;">💾 Save All Machine Prices</button>';
            html += '</div></div>';
            
            // Insert after exchange rate section
            leftCol.insertAdjacentHTML('afterend', html);
          }
          
          window.saveMachinePricesAll = async function() {
            var prices = {};
            var inputs = document.querySelectorAll('#machinePricesSection input[type="number"]');
            
            inputs.forEach(function(input) {
              var machine = input.getAttribute('data-machine');
              var colors = input.getAttribute('data-colors');
              var width = input.getAttribute('data-width');
              var value = parseFloat(input.value) || 0;
              
              if (!prices[machine]) prices[machine] = {};
              if (!prices[machine][colors]) prices[machine][colors] = {};
              prices[machine][colors][width] = value;
            });
            
            try {
              if (window.saveMachinePrices) {
                var result = await window.saveMachinePrices(prices);
                if (result && result.success) {
                  if (window.showNotification) {
                    window.showNotification('success', 'Saved!', 'Machine prices saved successfully');
                  } else {
                    alert('Machine prices saved successfully!');
                  }
                } else {
                  alert(result ? result.message : 'Error saving prices');
                }
              } else {
                alert('Save function not available. Please refresh the page.');
              }
            } catch(e) {
              alert('Error saving: ' + e);
            }
          };

          // ==========================================
          // Audit Log Filters Enhancement
          // ==========================================
          function enhanceAuditLogPanel() {
            var auditPanel = document.getElementById('audit-panel');
            if (!auditPanel) return;
            
            var panelBody = auditPanel.querySelector('.panel-body');
            if (!panelBody) return;
            
            // Check if filters already added
            if (document.getElementById('auditFilters')) return;
            
            // Create filters HTML
            var filtersHtml = '<div id="auditFilters" style="margin-bottom:20px;background:#f8f9fa;padding:15px;border-radius:10px;">';
            filtersHtml += '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;align-items:end;">';
            
            // Date From
            filtersHtml += '<div class="form-group" style="margin:0;">';
            filtersHtml += '<label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">From Date</label>';
            filtersHtml += '<input type="date" id="auditDateFrom" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:6px;">';
            filtersHtml += '</div>';
            
            // Date To
            filtersHtml += '<div class="form-group" style="margin:0;">';
            filtersHtml += '<label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">To Date</label>';
            filtersHtml += '<input type="date" id="auditDateTo" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:6px;">';
            filtersHtml += '</div>';
            
            // User Filter
            filtersHtml += '<div class="form-group" style="margin:0;">';
            filtersHtml += '<label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">User</label>';
            filtersHtml += '<input type="text" id="auditUserFilter" placeholder="Filter by user..." style="width:100%;padding:8px;border:1px solid #ddd;border-radius:6px;">';
            filtersHtml += '</div>';
            
            // Action Filter
            filtersHtml += '<div class="form-group" style="margin:0;">';
            filtersHtml += '<label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">Action</label>';
            filtersHtml += '<select id="auditActionFilter" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:6px;">';
            filtersHtml += '<option value="">All Actions</option>';
            filtersHtml += '<option value="CREATE">CREATE</option>';
            filtersHtml += '<option value="UPDATE">UPDATE</option>';
            filtersHtml += '<option value="SOFT_DELETE">DELETE</option>';
            filtersHtml += '<option value="RESTORE">RESTORE</option>';
            filtersHtml += '<option value="LOGIN">LOGIN</option>';
            filtersHtml += '<option value="LOGOUT">LOGOUT</option>';
            filtersHtml += '<option value="IMPORT">IMPORT</option>';
            filtersHtml += '</select>';
            filtersHtml += '</div>';
            
            // Table Filter
            filtersHtml += '<div class="form-group" style="margin:0;">';
            filtersHtml += '<label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">Table</label>';
            filtersHtml += '<select id="auditTableFilter" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:6px;">';
            filtersHtml += '<option value="">All Tables</option>';
            filtersHtml += '<option value="clients">Clients</option>';
            filtersHtml += '<option value="quotations">Quotations</option>';
            filtersHtml += '<option value="contracts">Contracts</option>';
            filtersHtml += '<option value="users">Users</option>';
            filtersHtml += '<option value="settings">Settings</option>';
            filtersHtml += '</select>';
            filtersHtml += '</div>';
            
            filtersHtml += '</div>'; // End grid
            
            // Filter buttons
            filtersHtml += '<div style="margin-top:12px;display:flex;gap:10px;">';
            filtersHtml += '<button class="action-btn" onclick="applyAuditFilters()" style="padding:8px 20px;">🔍 Apply Filters</button>';
            filtersHtml += '<button class="filter-btn" onclick="clearAuditFilters()" style="padding:8px 20px;">Clear</button>';
            filtersHtml += '</div>';
            
            filtersHtml += '</div>'; // End filters container
            
            // Insert filters before content
            var auditContent = document.getElementById('auditContent');
            if (auditContent) {
              panelBody.insertAdjacentHTML('afterbegin', filtersHtml);
            }
          }
          
          window.applyAuditFilters = async function() {
            var dateFrom = document.getElementById('auditDateFrom').value;
            var dateTo = document.getElementById('auditDateTo').value;
            var userFilter = document.getElementById('auditUserFilter').value.toLowerCase();
            var actionFilter = document.getElementById('auditActionFilter').value;
            var tableFilter = document.getElementById('auditTableFilter').value;
            
            var container = document.getElementById('auditContent');
            container.innerHTML = '<div class="loading-spinner"><div class="spinner"></div></div>';
            
            try {
              var filters = {};
              if (dateFrom) filters.date_from = dateFrom;
              if (dateTo) filters.date_to = dateTo;
              if (actionFilter) filters.action = actionFilter;
              if (tableFilter) filters.table_name = tableFilter;
              if (userFilter) filters.user_email = userFilter;
              
              var result = await window.getAuditLogs(100, 0, filters);
              if (!result.success) {
                container.innerHTML = '<div class="empty-state"><h4>' + result.message + '</h4></div>';
                return;
              }
              
              var logs = result.logs || [];
              
              // Client-side filtering for user (partial match)
              if (userFilter) {
                logs = logs.filter(function(l) {
                  return l.user_email && l.user_email.toLowerCase().includes(userFilter);
                });
              }
              
              if (logs.length === 0) {
                container.innerHTML = '<div class="empty-state"><h4>No logs found</h4><p>Try different filters</p></div>';
                return;
              }
              
              var html = '<table class="data-table"><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Table</th><th>Record ID</th></tr></thead><tbody>';
              logs.forEach(function(l) {
                var actionClass = '';
                if (l.action === 'CREATE') actionClass = 'style="color:#2e7d32;"';
                else if (l.action === 'UPDATE') actionClass = 'style="color:#1565c0;"';
                else if (l.action === 'SOFT_DELETE') actionClass = 'style="color:#c62828;"';
                else if (l.action === 'RESTORE') actionClass = 'style="color:#f57f17;"';
                
                html += '<tr>';
                html += '<td>' + l.timestamp.replace('T', ' ').substring(0, 19) + '</td>';
                html += '<td>' + l.user_email + '</td>';
                html += '<td ' + actionClass + '><strong>' + l.action + '</strong></td>';
                html += '<td>' + l.table_name + '</td>';
                html += '<td>' + (l.record_id || '-') + '</td>';
                html += '</tr>';
              });
              html += '</tbody></table>';
              container.innerHTML = html;
            } catch (e) {
              container.innerHTML = '<div class="empty-state"><h4>Error loading logs</h4></div>';
            }
          };
          
          window.clearAuditFilters = function() {
            document.getElementById('auditDateFrom').value = '';
            document.getElementById('auditDateTo').value = '';
            document.getElementById('auditUserFilter').value = '';
            document.getElementById('auditActionFilter').value = '';
            document.getElementById('auditTableFilter').value = '';
            window.loadAuditLogs();
          };

          // ==========================================
          // Dynamic Machine Configuration
          // ==========================================
          async function addMachineConfigSection() {
            var container = document.getElementById('settingsContent');
            if (!container) return;
            
            // Check if already added
            if (document.getElementById('machineConfigSection')) return;
            
            // Find the machine prices section
            var machinePricesSection = document.getElementById('machinePricesSection');
            if (!machinePricesSection) return;
            
            // Create config section HTML
            var html = '<div id="machineConfigSection" style="background:#e8f5e9;padding:20px;border-radius:12px;margin-top:20px;border:2px solid #4caf50;">';
            html += '<h4 style="margin:0 0 15px;color:#2e7d32;">⚙️ Machine Configuration (Add New Types/Sizes)</h4>';
            
            // Add new machine type
            html += '<div style="background:#fff;padding:15px;border-radius:8px;margin-bottom:15px;">';
            html += '<h5 style="margin:0 0 10px;">➕ Add New Machine Type</h5>';
            html += '<div style="display:flex;gap:10px;align-items:end;">';
            html += '<div style="flex:1;">';
            html += '<label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">Machine Type Name</label>';
            html += '<input type="text" id="newMachineTypeName" placeholder="e.g. Ceramic anilox Double Doctor Blade" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:6px;">';
            html += '</div>';
            html += '<button class="action-btn" onclick="addNewMachineType()" style="padding:8px 16px;white-space:nowrap;">➕ Add Type</button>';
            html += '</div>';
            html += '</div>';
            
            // Add new color count
            html += '<div style="background:#fff;padding:15px;border-radius:8px;margin-bottom:15px;">';
            html += '<h5 style="margin:0 0 10px;">🎨 Add New Color Count</h5>';
            html += '<div style="display:flex;gap:10px;align-items:end;">';
            html += '<div style="flex:1;">';
            html += '<label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">Color Count</label>';
            html += '<input type="number" id="newColorCount" placeholder="e.g. 10" min="1" max="20" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:6px;">';
            html += '</div>';
            html += '<button class="action-btn" onclick="addNewColorCount()" style="padding:8px 16px;white-space:nowrap;">➕ Add Color</button>';
            html += '</div>';
            html += '</div>';
            
            // Add new width
            html += '<div style="background:#fff;padding:15px;border-radius:8px;">';
            html += '<h5 style="margin:0 0 10px;">📐 Add New Machine Width</h5>';
            html += '<div style="display:flex;gap:10px;align-items:end;">';
            html += '<div style="flex:1;">';
            html += '<label style="font-size:12px;color:#666;display:block;margin-bottom:4px;">Width (cm)</label>';
            html += '<input type="number" id="newMachineWidth" placeholder="e.g. 140" min="50" max="300" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:6px;">';
            html += '</div>';
            html += '<button class="action-btn" onclick="addNewMachineWidth()" style="padding:8px 16px;white-space:nowrap;">➕ Add Width</button>';
            html += '</div>';
            html += '</div>';
            
            html += '</div>';
            
            // Insert after machine prices section
            machinePricesSection.insertAdjacentHTML('afterend', html);
          }
          
          window.addNewMachineType = async function() {
            var nameInput = document.getElementById('newMachineTypeName');
            var name = nameInput.value.trim();
            
            if (!name) {
              alert('Please enter a machine type name');
              return;
            }
            
            // Get current machine config
            var result = await window.getMachineConfig ? await window.getMachineConfig() : {success: false};
            var config = result.success ? result.config : {
              types: ["Metal anilox", "Ceramic anilox Single Doctor Blade", "Ceramic anilox Chamber Doctor Blade"],
              colors: ["4", "6", "8"],
              widths: ["80", "100", "120"]
            };
            
            // Check if already exists
            if (config.types.indexOf(name) !== -1) {
              alert('This machine type already exists');
              return;
            }
            
            // Add new type
            config.types.push(name);
            
            // Save config
            if (window.saveMachineConfig) {
              var saveResult = await window.saveMachineConfig(config);
              if (saveResult.success) {
                nameInput.value = '';
                window.showNotification('success', 'Added!', 'New machine type added. Refresh Settings to see changes.');
                // Reload settings panel
                setTimeout(function() { window.loadSettings(); }, 500);
              } else {
                alert(saveResult.message || 'Error saving');
              }
            }
          };
          
          window.addNewColorCount = async function() {
            var input = document.getElementById('newColorCount');
            var count = input.value.trim();
            
            if (!count || isNaN(count)) {
              alert('Please enter a valid color count');
              return;
            }
            
            // Get current config
            var result = await window.getMachineConfig ? await window.getMachineConfig() : {success: false};
            var config = result.success ? result.config : {
              types: ["Metal anilox", "Ceramic anilox Single Doctor Blade", "Ceramic anilox Chamber Doctor Blade"],
              colors: ["4", "6", "8"],
              widths: ["80", "100", "120"]
            };
            
            // Check if already exists
            if (config.colors.indexOf(count) !== -1) {
              alert('This color count already exists');
              return;
            }
            
            // Add and sort
            config.colors.push(count);
            config.colors.sort(function(a, b) { return parseInt(a) - parseInt(b); });
            
            // Save config
            if (window.saveMachineConfig) {
              var saveResult = await window.saveMachineConfig(config);
              if (saveResult.success) {
                input.value = '';
                window.showNotification('success', 'Added!', 'New color count added. Refresh Settings to see changes.');
                setTimeout(function() { window.loadSettings(); }, 500);
              } else {
                alert(saveResult.message || 'Error saving');
              }
            }
          };
          
          window.addNewMachineWidth = async function() {
            var input = document.getElementById('newMachineWidth');
            var width = input.value.trim();
            
            if (!width || isNaN(width)) {
              alert('Please enter a valid width');
              return;
            }
            
            // Get current config
            var result = await window.getMachineConfig ? await window.getMachineConfig() : {success: false};
            var config = result.success ? result.config : {
              types: ["Metal anilox", "Ceramic anilox Single Doctor Blade", "Ceramic anilox Chamber Doctor Blade"],
              colors: ["4", "6", "8"],
              widths: ["80", "100", "120"]
            };
            
            // Check if already exists
            if (config.widths.indexOf(width) !== -1) {
              alert('This width already exists');
              return;
            }
            
            // Add and sort
            config.widths.push(width);
            config.widths.sort(function(a, b) { return parseInt(a) - parseInt(b); });
            
            // Save config
            if (window.saveMachineConfig) {
              var saveResult = await window.saveMachineConfig(config);
              if (saveResult.success) {
                input.value = '';
                window.showNotification('success', 'Added!', 'New width added. Refresh Settings to see changes.');
                setTimeout(function() { window.loadSettings(); }, 500);
              } else {
                alert(saveResult.message || 'Error saving');
              }
            }
          };

          // Patch loadAuditLogs to add filters
          function patchLoadAuditLogs() {
            var origAuditLogs = window.loadAuditLogs;
            if (!origAuditLogs || origAuditLogs.__patched) return;
            
            window.loadAuditLogs = async function(page) {
              await origAuditLogs(page);
              setTimeout(enhanceAuditLogPanel, 100);
            };
            window.loadAuditLogs.__patched = true;
          }

          function run() {
            insertDataImportNav();
            patchSaveSetting();
            patchLoadSettings();
            patchLoadAuditLogs();
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

    def get_machine_prices(self):
        """الحصول على أسعار المكن"""
        return anvil.server.call('get_machine_prices')

    def save_machine_prices(self, prices):
        """حفظ أسعار المكن"""
        return anvil.server.call('save_machine_prices', self.get_auth(), prices)

    def get_machine_config(self):
        """الحصول على إعدادات المكن (الأنواع، الألوان، العروض)"""
        return anvil.server.call('get_machine_config')

    def save_machine_config(self, config):
        """حفظ إعدادات المكن"""
        return anvil.server.call('save_machine_config', self.get_auth(), config)

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

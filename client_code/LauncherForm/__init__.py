"""
LauncherForm - صفحة الإطلاق الرئيسية
====================================
- التوجيه حسب الـ hash
- روابط للصفحات المختلفة
"""

from ._anvil_designer import LauncherFormTemplate
from anvil import *
import anvil.google.auth, anvil.google.drive
from anvil.google.drive import app_files
import anvil.server
import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables
import anvil.js


class LauncherForm(LauncherFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Expose logout function to JavaScript
        anvil.js.window.logoutUserFromLauncher = self.logout_user

        # TOTP (تطبيق المصادقة - مجاني)
        anvil.js.window.setupTotpStart = self.setup_totp_start
        anvil.js.window.setupTotpConfirm = self.setup_totp_confirm
        anvil.js.window.userHasTotpEnabled = self.user_has_totp_enabled

        # نفحص الـ hash مرة واحدة عند التحميل
        self.check_route()

        # نربط listener بطريقة صحيحة
        anvil.js.window.addEventListener("hashchange", self.on_hash_change)

    def get_token(self):
        """Get auth token from localStorage"""
        return anvil.js.window.localStorage.getItem('auth_token')

    def setup_totp_start(self):
        """بدء تفعيل تطبيق المصادقة (Authenticator)"""
        return anvil.server.call('setup_totp_start', self.get_token())

    def setup_totp_confirm(self, code):
        """تأكيد تفعيل تطبيق المصادقة بالكود من التطبيق"""
        return anvil.server.call('setup_totp_confirm', self.get_token(), code)

    def user_has_totp_enabled(self):
        """هل المستخدم الحالي فعّل تطبيق المصادقة؟ (لإخفاء الرابط بعد التفعيل)"""
        return anvil.server.call('user_has_totp_enabled', self.get_token())

    def logout_user(self):
        """تسجيل الخروج"""
        token = self.get_token()
        if token:
            try:
                anvil.server.call('logout_user', token)
            except:
                pass
        anvil.js.window.localStorage.clear()
        return True

    def on_hash_change(self, event):
        """معالجة تغيير الـ hash"""
        self.check_route()

    def check_route(self):
        """التحقق من المسار والتوجيه"""
        hash_val = anvil.js.window.location.hash

        if hash_val == "#calculator":
            open_form('CalculatorForm')
        elif hash_val == "#clients":
            open_form('ClientListForm')
        elif hash_val == "#database":
            open_form('DatabaseForm')
        elif hash_val == "#admin":
            open_form('AdminPanel')
        elif hash_val == "#import":
            open_form('DataImportForm')
        elif hash_val == "#quotation-print":
            open_form('QuotationPrintForm')
        elif hash_val == "#contract-print":
            open_form('ContractPrintForm')

    def form_show(self, **event_args):
        """عند عرض النموذج"""
        self.route()
        self._inject_totp_link()

    def _inject_totp_link(self):
        """رابط التطبيق ظاهر افتراضياً في القالب؛ نربط النقر ونخفيه فقط إذا المستخدم فعّل المصادقة"""
        js = r"""
        (function() {
          if (window._totpLinkInjected) return;
          window._totpLinkInjected = true;
          function startTotpSetup() {
            if (!window.setupTotpStart || typeof window.setupTotpStart !== 'function') {
              alert('Please refresh the page and try again.');
              return;
            }
            var p = window.setupTotpStart();
            if (!p || typeof p.then !== 'function') {
              alert('Setup is not available. Please refresh the page.');
              return;
            }
            p.then(function(r) {
              if (!r || !r.success) {
                alert(r && r.message ? r.message : 'Failed to start setup');
                return;
              }
              var modal = document.getElementById('totpSetupModal');
              if (!modal) {
                modal = document.createElement('div');
                modal.id = 'totpSetupModal';
                modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:99999;';
                modal.innerHTML = '<div style="background:#fff;padding:24px;border-radius:12px;max-width:320px;text-align:center;">' +
                  '<h4 style="margin:0 0 12px;">Enable Authenticator</h4>' +
                  '<p style="font-size:13px;color:#666;margin:0 0 12px;">Scan QR with Google Authenticator or similar app</p>' +
                  '<div id="totpQrContainer"></div>' +
                  '<p id="totpSecretText" style="font-size:11px;word-break:break-all;margin:8px 0;"></p>' +
                  '<input type="text" id="totpCodeInput" placeholder="000000" maxlength="6" style="width:120px;padding:8px;font-size:18px;text-align:center;margin:8px 0;">' +
                  '<br><button id="totpConfirmBtn" style="padding:8px 20px;background:#1976d2;color:#fff;border:none;border-radius:8px;cursor:pointer;">Confirm</button>' +
                  ' <button id="totpCancelBtn" style="padding:8px 16px;background:#999;color:#fff;border:none;border-radius:8px;cursor:pointer;">Cancel</button>' +
                  '<p id="totpSetupMessage" style="margin-top:12px;font-size:13px;"></p></div>';
                modal.onclick = function(ev) { if (ev.target === modal) modal.style.display = 'none'; };
                document.body.appendChild(modal);
                document.getElementById('totpCancelBtn').onclick = function() { modal.style.display = 'none'; };
                document.getElementById('totpConfirmBtn').onclick = function() {
                  var code = document.getElementById('totpCodeInput').value.trim();
                  if (code.length !== 6) { document.getElementById('totpSetupMessage').textContent = 'Enter 6 digits'; return; }
                  var p2 = window.setupTotpConfirm && window.setupTotpConfirm(code);
                  if (p2 && typeof p2.then === 'function') {
                    p2.then(function(res) {
                      var msg = document.getElementById('totpSetupMessage');
                      msg.textContent = res && res.message ? res.message : '';
                      if (res && res.success) {
                        msg.style.color = 'green';
                        var w = document.getElementById('totpLinkWrap');
                        if (w) w.style.display = 'none';
                        setTimeout(function() { modal.style.display = 'none'; }, 1500);
                      } else { msg.style.color = 'red'; }
                    }).catch(function(err) { alert('Error: ' + (err && err.message ? err.message : err)); });
                  }
                };
              }
              document.getElementById('totpQrContainer').innerHTML = '<img src="data:image/png;base64,' + r.qr_base64 + '" alt="QR" style="max-width:200px;">';
              document.getElementById('totpSecretText').textContent = 'Or enter key: ' + (r.secret || '');
              document.getElementById('totpCodeInput').value = '';
              document.getElementById('totpSetupMessage').textContent = '';
              modal.style.display = 'flex';
            }).catch(function(err) { alert('Error: ' + (err && err.message ? err.message : err)); });
          }
          function attachAndMaybeHide() {
            var wrap = document.getElementById('totpLinkWrap');
            if (wrap && window.userHasTotpEnabled && typeof window.userHasTotpEnabled === 'function') {
              var p = window.userHasTotpEnabled();
              if (p && typeof p.then === 'function') {
                p.then(function(hasTotp) { if (hasTotp) wrap.style.display = 'none'; }).catch(function() {});
              }
            }
            document.body.addEventListener('click', function(e) {
              var t = e.target;
              if (!t) return;
              var link = t.id === 'launcherTotpLink' ? t : (t.closest && t.closest('#launcherTotpLink'));
              if (!link) return;
              e.preventDefault();
              e.stopPropagation();
              startTotpSetup();
              return false;
            }, true);
          }
          function run() {
            if (document.getElementById('totpLinkWrap')) {
              attachAndMaybeHide();
            } else {
              setTimeout(run, 200);
            }
          }
          run();
        })();
        """
        try:
            anvil.js.window.eval(js)
        except Exception:
            pass

    def route(self, **event_args):
        """التوجيه حسب الـ hash"""
        h = anvil.js.window.location.hash

        if h == "#clients":
            # فتح صفحة العملاء (للقراءة فقط)
            try:
                from ..ClientListForm import ClientListForm
                open_form("ClientListForm")
            except Exception as e:
                alert(f"Error opening ClientListForm: {e}")

        elif h == "#database":
            # فتح صفحة قاعدة البيانات (للقراءة فقط)
            try:
                from ..DatabaseForm import DatabaseForm
                open_form("DatabaseForm")
            except Exception as e:
                alert(f"Error opening DatabaseForm: {e}")

        elif h == "#calculator":
            # فتح الحاسبة
            try:
                open_form("CalculatorForm")
            except Exception as e:
                alert(f"Error opening CalculatorForm: {e}")

        elif h == "#admin":
            # فتح لوحة التحكم (للأدمن فقط)
            try:
                open_form("AdminPanel")
            except Exception as e:
                alert(f"Error opening AdminPanel: {e}")

        elif h == "#import":
            # فتح صفحة الاستيراد (للأدمن فقط)
            try:
                from ..DataImportForm import DataImportForm
                open_form("DataImportForm")
            except Exception as e:
                alert(f"Error opening DataImportForm: {e}")

        elif h == "#quotation-print":
            # فتح صفحة طباعة عروض الأسعار
            try:
                open_form("QuotationPrintForm")
            except Exception as e:
                alert(f"Error opening QuotationPrintForm: {e}")

        elif h == "#contract-print":
            # فتح صفحة طباعة العقود
            try:
                open_form("ContractPrintForm")
            except Exception as e:
                alert(f"Error opening ContractPrintForm: {e}")

        # لا نفتح LauncherForm مرة أخرى لتجنب الحلقة اللانهائية

    # =========================================================
    # أحداث الأزرار (إذا كانت موجودة في الواجهة)
    # =========================================================
    def btn_calculator_click(self, **event_args):
        """فتح الحاسبة"""
        anvil.js.window.location.hash = "#calculator"
        open_form("CalculatorForm")

    def btn_clients_click(self, **event_args):
        """فتح صفحة العملاء"""
        anvil.js.window.location.hash = "#clients"
        try:
            open_form("ClientListForm")
        except:
            pass

    def btn_database_click(self, **event_args):
        """فتح صفحة قاعدة البيانات"""
        anvil.js.window.location.hash = "#database"
        try:
            open_form("DatabaseForm")
        except:
            pass

    def btn_admin_click(self, **event_args):
        """فتح لوحة التحكم"""
        anvil.js.window.location.hash = "#admin"
        try:
            open_form("AdminPanel")
        except:
            pass

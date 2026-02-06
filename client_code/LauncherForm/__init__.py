"""
LauncherForm - صفحة الإطلاق الرئيسية
====================================
- التوجيه حسب الـ hash
- روابط للصفحات المختلفة
"""

from ._anvil_designer import LauncherFormTemplate
from anvil import *
import anvil.users
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

        # Expose logout and token for JavaScript (TOTP and hash routing)
        anvil.js.window.logoutUserFromLauncher = self.logout_user
        anvil.js.window.launcherGetAuthToken = self.get_token

        # TOTP (تطبيق المصادقة - مجاني)
        anvil.js.window.setupTotpStart = self.setup_totp_start
        anvil.js.window.setupTotpConfirm = self.setup_totp_confirm
        anvil.js.window.userHasTotpEnabled = self.user_has_totp_enabled

        # نفحص الـ hash مرة واحدة عند التحميل
        self.check_route()

        # نربط listener بطريقة صحيحة
        anvil.js.window.addEventListener("hashchange", self.on_hash_change)

    def get_token(self):
        """Get auth token from sessionStorage (جلسة تنتهي عند إغلاق التاب)"""
        return anvil.js.window.sessionStorage.getItem('auth_token')

    def setup_totp_start(self, token=None):
        """بدء تفعيل تطبيق المصادقة (Authenticator). يُفضّل تمرير token من JS من نفس الصفحة."""
        auth_token = token if token is not None else self.get_token()
        return anvil.server.call('setup_totp_start', auth_token)

    def setup_totp_confirm(self, code, token=None):
        """تأكيد تفعيل تطبيق المصادقة بالكود من التطبيق"""
        auth_token = token if token is not None else self.get_token()
        return anvil.server.call('setup_totp_confirm', auth_token, code)

    def user_has_totp_enabled(self, token=None):
        """هل المستخدم الحالي فعّل تطبيق المصادقة؟ (لإخفاء الرابط بعد التفعيل)"""
        auth_token = token if token is not None else self.get_token()
        return anvil.server.call('user_has_totp_enabled', auth_token)

    def logout_user(self):
        """تسجيل الخروج"""
        token = self.get_token()
        if token:
            try:
                anvil.server.call('logout_user', token)
            except Exception:
                pass
        try:
            for k in ('auth_token', 'user_email', 'user_name', 'user_role'):
                anvil.js.window.sessionStorage.removeItem(k)
                anvil.js.window.localStorage.removeItem(k)
        except Exception:
            pass
        return True

    def on_hash_change(self, event):
        """معالجة تغيير الـ hash"""
        self.check_route()

    def check_route(self):
        """التحقق من المسار والتوجيه — استعادة آخر صفحة بعد الـ refresh"""
        try:
            # استعادة آخر صفحة من localStorage عند الـ refresh (بدون تغيير الـ hash حتى لا يُستدعى check_route مرتين)
            anvil.js.window.eval("""
                (function() {
                    var h = (window.location && window.location.hash) || '';
                    if (!h || h === '#') {
                        var saved = (window.localStorage && window.localStorage.getItem('hp_last_page')) || '';
                        if (saved && saved.indexOf('#') === 0 && window.location) window.location.hash = saved;
                    }
                    h = (window.location && window.location.hash) || '#launcher';
                    if (window.localStorage) window.localStorage.setItem('hp_last_page', h);
                })();
            """)
        except Exception:
            pass
        try:
            hash_val = anvil.js.window.location.hash or "#launcher"
        except Exception:
            hash_val = "#launcher"
        if not hash_val or hash_val == "#":
            hash_val = "#launcher"

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
        elif hash_val == "#login":
            open_form('LoginForm')

    def form_show(self, **event_args):
        """عند عرض النموذج — تخفيف: مزامنة التوكن فوراً، تأجيل TOTP حتى لا يثقل التحميل"""
        self._inject_notification_system()
        self._sync_auth_token_to_frame()
        try:
            anvil.js.window.eval("if (window.localStorage) window.localStorage.setItem('hp_last_page', '#launcher');")
        except Exception:
            pass
        self.route()
        self._inject_totp_link()

    def _inject_notification_system(self):
        """ضمان وجود نظام الإشعارات (بديل عن alert البراوزر) — يعمل حتى قبل تحميل i18n."""
        try:
            anvil.js.window.eval("""
(function() {
  if (window._hpNotificationSystemReady) return;
  window._hpNotificationSystemReady = true;
  var c = document.getElementById('notificationContainer');
  if (!c) {
    c = document.createElement('div');
    c.id = 'notificationContainer';
    c.style.cssText = 'position:fixed;top:20px;right:20px;z-index:999999;display:flex;flex-direction:column;gap:8px;max-width:360px;pointer-events:none;';
    c.innerHTML = '<style>#notificationContainer .hp-t{pointer-events:auto;padding:12px 16px;border-radius:8px;box-shadow:0 4px 20px rgba(0,0,0,0.15);border-left:4px solid #667eea;background:#fff;}#notificationContainer .hp-t.suc{border-left-color:#4caf50;}#notificationContainer .hp-t.err{border-left-color:#f44336;}#notificationContainer .hp-t.warn{border-left-color:#ff9800;}#notificationContainer .hp-t.inf{border-left-color:#2196f3;}</style>';
    document.body.appendChild(c);
  }
  if (!window.showNotification) {
    window.showNotification = function(type, title, msg) {
      var el = document.createElement('div');
      el.className = 'hp-t ' + (type === 'success' ? 'suc' : type === 'error' ? 'err' : type === 'warning' ? 'warn' : 'inf');
      el.innerHTML = (title ? '<strong style="display:block;margin-bottom:4px;">' + title + '</strong>' : '') + (msg || '');
      c.appendChild(el);
      setTimeout(function() { if (el.parentNode) el.parentNode.removeChild(el); }, 4500);
    };
  }
  if (!window.showConfirm) {
    window.showConfirm = function(msg, title) {
      return new Promise(function(resolve) {
        var b = document.createElement('div');
        b.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999999;display:flex;align-items:center;justify-content:center;';
        b.innerHTML = '<div style="background:#fff;padding:24px;border-radius:12px;max-width:400px;box-shadow:0 8px 32px rgba(0,0,0,0.2);"><div style="font-weight:600;margin-bottom:12px;">' + (title || 'تأكيد') + '</div><div style="margin-bottom:20px;">' + (msg || '').replace(/</g,'&lt;') + '</div><div style="display:flex;gap:10px;justify-content:flex-end;"><button id="hpCnNo" style="padding:10px 20px;border:1px solid #ccc;border-radius:8px;background:#fff;cursor:pointer;">لا</button><button id="hpCnYes" style="padding:10px 20px;border:none;border-radius:8px;background:#1976d2;color:#fff;cursor:pointer;">نعم</button></div></div>';
        b.onclick = function(ev) { if (ev.target === b) { document.body.removeChild(b); resolve(false); } };
        document.body.appendChild(b);
        document.getElementById('hpCnYes').onclick = function() { document.body.removeChild(b); resolve(true); };
        document.getElementById('hpCnNo').onclick = function() { document.body.removeChild(b); resolve(false); };
      });
    };
  }
  if (!window.showPrompt) {
    window.showPrompt = function(msg, def, title) {
      return new Promise(function(resolve) {
        var b = document.createElement('div');
        var id = 'hpInp' + Date.now();
        b.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999999;display:flex;align-items:center;justify-content:center;';
        b.innerHTML = '<div style="background:#fff;padding:24px;border-radius:12px;max-width:400px;box-shadow:0 8px 32px rgba(0,0,0,0.2);">' + (title ? '<div style="font-weight:600;margin-bottom:12px;">' + title + '</div>' : '') + '<div style="margin-bottom:12px;">' + (msg || '').replace(/</g,'&lt;') + '</div><input type="text" id="' + id + '" value="' + (def != null ? String(def).replace(/"/g,'&quot;') : '') + '" style="width:100%;padding:10px;border:1px solid #ccc;border-radius:8px;margin-bottom:16px;box-sizing:border-box;"><div style="display:flex;gap:10px;justify-content:flex-end;"><button id="hpPmCancel" style="padding:10px 20px;border:1px solid #ccc;border-radius:8px;background:#fff;cursor:pointer;">إلغاء</button><button id="hpPmOk" style="padding:10px 20px;border:none;border-radius:8px;background:#1976d2;color:#fff;cursor:pointer;">موافق</button></div></div>';
        b.onclick = function(ev) { if (ev.target === b) { document.body.removeChild(b); resolve(null); } };
        document.body.appendChild(b);
        document.getElementById('hpPmOk').onclick = function() { var v = document.getElementById(id).value; document.body.removeChild(b); resolve(v); };
        document.getElementById('hpPmCancel').onclick = function() { document.body.removeChild(b); resolve(null); };
      });
    };
  }
})();
""")
        except Exception:
            pass

    def _sync_auth_token_to_frame(self):
        """نسخ الـ token من sessionStorage (النافذة الرئيسية) إلى إطار الصفحة الحالي"""
        js = r"""
        (function() {
          try {
            var tok = (window.sessionStorage && window.sessionStorage.getItem('auth_token')) || null;
            if (!tok && window.top && window.top !== window && window.top.sessionStorage)
              tok = window.top.sessionStorage.getItem('auth_token');
            if (tok && window.sessionStorage) window.sessionStorage.setItem('auth_token', tok);
          } catch(e) {}
        })();
        """
        try:
            anvil.js.window.eval(js)
        except Exception:
            pass

    def _inject_totp_link(self):
        """رابط التطبيق ظاهر افتراضياً في القالب؛ نربط النقر ونخفيه فقط إذا المستخدم فعّل المصادقة"""
        js = r"""
        (function() {
          if (window._totpLinkInjected) return;
          window._totpLinkInjected = true;
          function startTotpSetup() {
            if (!window.setupTotpStart || typeof window.setupTotpStart !== 'function') {
              if (window.showNotification) window.showNotification('error', '', 'Please refresh the page and try again.');
              return;
            }
            var tok = (window.launcherGetAuthToken && window.launcherGetAuthToken()) || null;
            var p = window.setupTotpStart(tok);
            if (!p || typeof p.then !== 'function') {
              if (window.showNotification) window.showNotification('error', '', 'Setup is not available. Please refresh the page.');
              return;
            }
            p.then(function(r) {
              if (!r || !r.success) {
                if (window.showNotification) window.showNotification('error', '', r && r.message ? r.message : 'Failed to start setup');
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
                  var _tok = (window.launcherGetAuthToken && window.launcherGetAuthToken()) || null;
                  var p2 = window.setupTotpConfirm && window.setupTotpConfirm(code, _tok);
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
                    }).catch(function(err) { if (window.showNotification) window.showNotification('error', '', 'Error: ' + (err && err.message ? err.message : err)); });
                  }
                };
              }
              document.getElementById('totpQrContainer').innerHTML = '<img src="data:image/png;base64,' + r.qr_base64 + '" alt="QR" style="max-width:200px;">';
              document.getElementById('totpSecretText').textContent = 'Or enter key: ' + (r.secret || '');
              document.getElementById('totpCodeInput').value = '';
              document.getElementById('totpSetupMessage').textContent = '';
              modal.style.display = 'flex';
            }).catch(function(err) { if (window.showNotification) window.showNotification('error', '', 'Error: ' + (err && err.message ? err.message : err)); });
          }
          function attachAndMaybeHide() {
            var wrap = document.getElementById('totpLinkWrap');
            if (wrap && window.userHasTotpEnabled && typeof window.userHasTotpEnabled === 'function') {
              var _t = (window.launcherGetAuthToken && window.launcherGetAuthToken()) || null;
              var p = window.userHasTotpEnabled(_t);
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
                try: anvil.js.window.showNotification('error', '', str(e))
                except Exception: pass

        elif h == "#database":
            # فتح صفحة قاعدة البيانات (للقراءة فقط)
            try:
                from ..DatabaseForm import DatabaseForm
                open_form("DatabaseForm")
            except Exception as e:
                try: anvil.js.window.showNotification('error', '', str(e))
                except Exception: pass

        elif h == "#calculator":
            # فتح الحاسبة
            try:
                open_form("CalculatorForm")
            except Exception as e:
                try: anvil.js.window.showNotification('error', '', str(e))
                except Exception: pass

        elif h == "#admin":
            # فتح لوحة التحكم (للأدمن فقط)
            try:
                open_form("AdminPanel")
            except Exception as e:
                try: anvil.js.window.showNotification('error', '', str(e))
                except Exception: pass

        elif h == "#import":
            # فتح صفحة الاستيراد (للأدمن فقط)
            try:
                from ..DataImportForm import DataImportForm
                open_form("DataImportForm")
            except Exception as e:
                try: anvil.js.window.showNotification('error', '', str(e))
                except Exception: pass

        elif h == "#quotation-print":
            # فتح صفحة طباعة عروض الأسعار
            try:
                open_form("QuotationPrintForm")
            except Exception as e:
                try: anvil.js.window.showNotification('error', '', str(e))
                except Exception: pass

        elif h == "#contract-print":
            # فتح صفحة طباعة العقود
            try:
                open_form("ContractPrintForm")
            except Exception as e:
                try: anvil.js.window.showNotification('error', '', str(e))
                except Exception: pass

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
        except Exception:
            pass

    def btn_database_click(self, **event_args):
        """فتح صفحة قاعدة البيانات"""
        anvil.js.window.location.hash = "#database"
        try:
            open_form("DatabaseForm")
        except Exception:
            pass

    def btn_admin_click(self, **event_args):
        """فتح لوحة التحكم"""
        anvil.js.window.location.hash = "#admin"
        try:
            open_form("AdminPanel")
        except Exception:
            pass

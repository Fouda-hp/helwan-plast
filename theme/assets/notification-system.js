/**
 * notification-system.js — نظام الإشعارات (بديل عن alert/confirm/prompt)
 * يُحمّل من LauncherForm._inject_notification_system()
 */
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
  function _esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
  if (!window.showNotification) {
    window.showNotification = function(type, title, msg) {
      var el = document.createElement('div');
      el.className = 'hp-t ' + (type === 'success' ? 'suc' : type === 'error' ? 'err' : type === 'warning' ? 'warn' : 'inf');
      el.innerHTML = (title ? '<strong style="display:block;margin-bottom:4px;">' + _esc(title) + '</strong>' : '') + _esc(msg || '');
      c.appendChild(el);
      setTimeout(function() { if (el.parentNode) el.parentNode.removeChild(el); }, 4500);
    };
  }
  if (!window.showConfirm) {
    window.showConfirm = function(msg, title) {
      return new Promise(function(resolve) {
        var b = document.createElement('div');
        b.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999999;display:flex;align-items:center;justify-content:center;';
        b.innerHTML = '<div style="background:#fff;padding:24px;border-radius:12px;max-width:400px;box-shadow:0 8px 32px rgba(0,0,0,0.2);"><div style="font-weight:600;margin-bottom:12px;">' + (title || '\u062a\u0623\u0643\u064a\u062f') + '</div><div style="margin-bottom:20px;">' + (msg || '').replace(/</g,'&lt;') + '</div><div style="display:flex;gap:10px;justify-content:flex-end;"><button id="hpCnNo" style="padding:10px 20px;border:1px solid #ccc;border-radius:8px;background:#fff;cursor:pointer;">\u0644\u0627</button><button id="hpCnYes" style="padding:10px 20px;border:none;border-radius:8px;background:#1976d2;color:#fff;cursor:pointer;">\u0646\u0639\u0645</button></div></div>';
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
        b.innerHTML = '<div style="background:#fff;padding:24px;border-radius:12px;max-width:400px;box-shadow:0 8px 32px rgba(0,0,0,0.2);">' + (title ? '<div style="font-weight:600;margin-bottom:12px;">' + title + '</div>' : '') + '<div style="margin-bottom:12px;">' + (msg || '').replace(/</g,'&lt;') + '</div><input type="text" id="' + id + '" value="' + (def != null ? String(def).replace(/"/g,'&quot;') : '') + '" style="width:100%;padding:10px;border:1px solid #ccc;border-radius:8px;margin-bottom:16px;box-sizing:border-box;"><div style="display:flex;gap:10px;justify-content:flex-end;"><button id="hpPmCancel" style="padding:10px 20px;border:1px solid #ccc;border-radius:8px;background:#fff;cursor:pointer;">\u0625\u0644\u063a\u0627\u0621</button><button id="hpPmOk" style="padding:10px 20px;border:none;border-radius:8px;background:#1976d2;color:#fff;cursor:pointer;">\u0645\u0648\u0627\u0641\u0642</button></div></div>';
        b.onclick = function(ev) { if (ev.target === b) { document.body.removeChild(b); resolve(null); } };
        document.body.appendChild(b);
        document.getElementById('hpPmOk').onclick = function() { var v = document.getElementById(id).value; document.body.removeChild(b); resolve(v); };
        document.getElementById('hpPmCancel').onclick = function() { document.body.removeChild(b); resolve(null); };
      });
    };
  }
})();

/**
 * Global Notification Bell - Helwan Plast
 * ========================================
 * Floating bell icon on all pages (after login).
 * - Normal users see their own notifications
 * - Admins see ALL users' notifications
 *
 * Depends on Python bridges registered by notif_bridge.register_notif_bridges():
 *   window.__hpNotifGetAll()
 *   window.__hpNotifDeleteOne(id)
 *   window.__hpNotifDeleteAll()
 */
(function () {
  'use strict';

  // Allow re-init on full page reload (Anvil may reload the page)
  if (window.__hpNotifBellInit && window.__hpNotifBellTimers) return;
  window.__hpNotifBellInit = true;

  var BELL_ID = 'hp-global-notif-bell';
  var DROPDOWN_ID = 'hp-notif-dropdown';
  var BADGE_ID = 'hp-notif-badge';
  var REFRESH_MS = 60000;
  var CHECK_MS = 2000;
  var _dropdownOpen = false;
  var _cachedData = null;

  function log(msg) {
    try { console.log('[HP-Bell] ' + msg); } catch(e) {}
  }

  function getLang() {
    try { return localStorage.getItem('hp_language') || 'en'; } catch (e) { return 'en'; }
  }

  function isLoggedIn() {
    try {
      return !!(sessionStorage.getItem('auth_token') || localStorage.getItem('auth_token'));
    } catch (e) { return false; }
  }

  function isAdmin() {
    try { return sessionStorage.getItem('user_role') === 'admin'; } catch (e) { return false; }
  }

  var L = {
    en: {
      title: 'Notifications',
      deleteAll: 'Delete All',
      empty: 'No notifications',
      loading: 'Loading...',
      error: 'Error loading notifications'
    },
    ar: {
      title: '\u0627\u0644\u0625\u0634\u0639\u0627\u0631\u0627\u062a',
      deleteAll: '\u062d\u0630\u0641 \u0627\u0644\u0643\u0644',
      empty: '\u0644\u0627 \u062a\u0648\u062c\u062f \u0625\u0634\u0639\u0627\u0631\u0627\u062a',
      loading: '\u062c\u0627\u0631\u064a \u0627\u0644\u062a\u062d\u0645\u064a\u0644...',
      error: '\u062e\u0637\u0623 \u0641\u064a \u062a\u062d\u0645\u064a\u0644 \u0627\u0644\u0625\u0634\u0639\u0627\u0631\u0627\u062a'
    }
  };

  function t(key) {
    var lang = getLang();
    return (L[lang] || L.en)[key] || (L.en)[key] || key;
  }

  // ===== Create Bell =====
  function createBell() {
    if (!isLoggedIn()) {
      log('createBell: not logged in, skipping');
      return;
    }

    // Remove any existing bell first (clean slate)
    var existing = document.getElementById(BELL_ID);
    if (existing) existing.remove();

    var wrap = document.createElement('div');
    wrap.id = BELL_ID;

    var btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute('aria-label', 'Notifications');
    btn.innerHTML = '&#128276;';
    btn.style.cssText = 'cursor:pointer;';
    btn.__hpBellBound = true;
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      log('bell clicked!');
      toggleDropdown();
    });

    var badge = document.createElement('span');
    badge.id = BADGE_ID;
    badge.style.cssText = 'display:none;position:absolute;top:-4px;right:-4px;background:#f44336;color:#fff;font-size:10px;font-weight:700;min-width:18px;height:18px;border-radius:9px;align-items:center;justify-content:center;padding:0 4px;box-sizing:border-box;';
    badge.textContent = '0';

    wrap.appendChild(btn);
    wrap.appendChild(badge);

    // Try to place inside AdminPanel header-user-section (next to user name)
    var headerUserSection = document.querySelector('.header-user-section');
    if (headerUserSection) {
      wrap.classList.add('hp-notif-inline');
      wrap.style.cssText = 'position:relative;display:inline-flex;align-items:center;margin-right:6px;z-index:9998;';
      btn.style.cssText = 'width:38px;height:38px;border-radius:50%;border:none;background:rgba(255,255,255,0.15);color:#FFD700;font-size:18px;cursor:pointer;display:flex;align-items:center;justify-content:center;text-shadow:0 0 8px rgba(255,215,0,0.6);';
      headerUserSection.insertBefore(wrap, headerUserSection.firstChild);
      log('createBell: placed INLINE in header-user-section');
    } else {
      // Fixed position top-right for all other pages
      wrap.classList.add('hp-notif-fixed');
      wrap.style.cssText = 'position:fixed;top:16px;right:16px;z-index:999999;';
      btn.style.cssText = 'width:44px;height:44px;border-radius:50%;border:none;background:linear-gradient(135deg,#B8860B 0%,#DAA520 50%,#FFD700 100%);color:#fff;font-size:20px;cursor:pointer;box-shadow:0 4px 15px rgba(218,165,32,0.45);display:flex;align-items:center;justify-content:center;';
      document.body.appendChild(wrap);
      log('createBell: placed FIXED on body (top-right)');
    }
  }

  // ===== Ensure Bell Exists =====
  function ensureBell() {
    if (!isLoggedIn()) {
      var bell = document.getElementById(BELL_ID);
      if (bell) bell.remove();
      var dd = document.getElementById(DROPDOWN_ID);
      if (dd) dd.remove();
      return;
    }

    var bell = document.getElementById(BELL_ID);
    var headerUserSection = document.querySelector('.header-user-section');

    if (bell && document.body.contains(bell)) {
      // Bell exists — ensure click handler is properly bound
      var btn = bell.querySelector('button');
      if (btn && !btn.__hpBellBound) {
        btn.__hpBellBound = true;
        btn.addEventListener('click', function(e) {
          e.preventDefault();
          e.stopPropagation();
          toggleDropdown();
        });
      }
      // Check if bell should move between inline/fixed
      if (headerUserSection && bell.classList.contains('hp-notif-fixed')) {
        createBell(); // Recreates in correct position
      } else if (!headerUserSection && bell.classList.contains('hp-notif-inline')) {
        createBell(); // Recreates in correct position
      }
    } else {
      // Bell missing — create it
      createBell();
    }
  }

  // ===== Dropdown =====
  function toggleDropdown() {
    var existing = document.getElementById(DROPDOWN_ID);
    if (existing) {
      existing.remove();
      _dropdownOpen = false;
      document.removeEventListener('click', closeOnOutside);
      return;
    }
    showDropdown();
  }

  function showDropdown() {
    // Remove any stale dropdown first
    var old = document.getElementById(DROPDOWN_ID);
    if (old) old.remove();

    var dd = document.createElement('div');
    dd.id = DROPDOWN_ID;

    // Header
    var header = document.createElement('div');
    header.className = 'hp-notif-header';
    header.innerHTML = '<span>' + t('title') + '</span>';

    var delAllBtn = document.createElement('button');
    delAllBtn.textContent = t('deleteAll');
    delAllBtn.className = 'hp-notif-delete-all';
    delAllBtn.onclick = function (e) {
      e.stopPropagation();
      if (!window.__hpNotifDeleteAll) return;
      var p = window.__hpNotifDeleteAll();
      if (p && typeof p.then === 'function') {
        p.then(function () {
          renderList(dd, []);
          updateBadge(0);
        });
      }
    };
    header.appendChild(delAllBtn);
    dd.appendChild(header);

    // Body
    var body = document.createElement('div');
    body.className = 'hp-notif-body';
    body.innerHTML = '<div class="hp-notif-empty">' + t('loading') + '</div>';
    dd.appendChild(body);

    // Position dropdown relative to bell
    var bellEl = document.getElementById(BELL_ID);
    if (bellEl && bellEl.classList.contains('hp-notif-inline')) {
      dd.classList.add('hp-notif-dropdown-header');
      bellEl.appendChild(dd);
    } else {
      dd.classList.add('hp-notif-dropdown-fixed');
      document.body.appendChild(dd);
    }
    _dropdownOpen = true;

    // Close on outside click (with small delay to prevent immediate close)
    setTimeout(function () {
      document.addEventListener('click', closeOnOutside);
    }, 50);

    // Fetch
    fetchAndRender(dd);
  }

  function closeOnOutside(e) {
    var dd = document.getElementById(DROPDOWN_ID);
    var bell = document.getElementById(BELL_ID);
    if (dd && !dd.contains(e.target) && bell && !bell.contains(e.target)) {
      dd.remove();
      _dropdownOpen = false;
      document.removeEventListener('click', closeOnOutside);
    }
  }

  function fetchAndRender(dd) {
    if (!window.__hpNotifGetAll) {
      var body = dd.querySelector('.hp-notif-body');
      if (body) body.innerHTML = '<div class="hp-notif-empty">' + t('empty') + '</div>';
      return;
    }
    try {
      var p = window.__hpNotifGetAll();
      if (p && typeof p.then === 'function') {
        p.then(function (res) {
          var list = (res && res.success && res.notifications) ? res.notifications : [];
          _cachedData = list;
          renderList(dd, list);
          updateBadge(countUnread(list));
        }).catch(function () {
          var body = dd.querySelector('.hp-notif-body');
          if (body) body.innerHTML = '<div class="hp-notif-empty">' + t('error') + '</div>';
        });
      }
    } catch (e) {
      var body = dd.querySelector('.hp-notif-body');
      if (body) body.innerHTML = '<div class="hp-notif-empty">' + t('error') + '</div>';
    }
  }

  function renderList(dd, list) {
    var body = dd.querySelector('.hp-notif-body');
    if (!body) return;

    if (!list || list.length === 0) {
      body.innerHTML = '<div class="hp-notif-empty">' + t('empty') + '</div>';
      return;
    }

    var html = '';
    var showAdmin = isAdmin();
    list.forEach(function (n) {
      var bg = n.read_at ? '' : ' hp-notif-unread';
      var nid = (n.id || '').replace(/"/g, '&quot;');
      var ts = n.timestamp || '';
      var desc = n.action_description || n.action || '-';
      if (desc.length > 100) desc = desc.substring(0, 97) + '...';
      var userLine = '';
      if (showAdmin && n.user_email) {
        userLine = '<div class="hp-notif-user">' + n.user_email + '</div>';
      }
      html += '<div class="hp-notif-row' + bg + '" data-nid="' + nid + '">';
      html += '<div class="hp-notif-content">';
      html += '<div class="hp-notif-ts">' + ts + '</div>';
      html += userLine;
      html += '<div class="hp-notif-desc">' + desc + '</div>';
      html += '</div>';
      html += '<button class="hp-notif-del" title="Delete">&#10005;</button>';
      html += '</div>';
    });
    body.innerHTML = html;

    // Attach delete handlers
    body.querySelectorAll('.hp-notif-del').forEach(function (btn) {
      var row = btn.closest('.hp-notif-row');
      var nid = row && row.getAttribute('data-nid');
      if (!nid || !window.__hpNotifDeleteOne) return;
      btn.onclick = function (e) {
        e.stopPropagation();
        var p2 = window.__hpNotifDeleteOne(nid);
        if (p2 && typeof p2.then === 'function') {
          p2.then(function (r) {
            if (r && r.success && row.parentNode) {
              row.remove();
              var remaining = body.querySelectorAll('.hp-notif-row');
              if (remaining.length === 0) {
                body.innerHTML = '<div class="hp-notif-empty">' + t('empty') + '</div>';
              }
              updateBadge(remaining.length);
            }
          });
        }
      };
    });
  }

  function countUnread(list) {
    var c = 0;
    if (!list) return 0;
    list.forEach(function (n) { if (!n.read_at) c++; });
    return c;
  }

  function updateBadge(count) {
    var badge = document.getElementById(BADGE_ID);
    if (!badge) return;
    if (count > 0) {
      badge.textContent = count > 99 ? '99+' : String(count);
      badge.style.display = 'flex';
    } else {
      badge.style.display = 'none';
    }
  }

  // ===== Background Refresh =====
  function refreshBadge() {
    if (!isLoggedIn() || !window.__hpNotifGetAll) return;
    try {
      var p = window.__hpNotifGetAll();
      if (p && typeof p.then === 'function') {
        p.then(function (res) {
          var list = (res && res.success && res.notifications) ? res.notifications : [];
          _cachedData = list;
          updateBadge(countUnread(list));
        }).catch(function () {});
      }
    } catch (e) {}
  }

  // ===== Init =====
  function init() {
    if (!document.body) { setTimeout(init, 200); return; }

    log('init: starting, logged=' + isLoggedIn());
    ensureBell();

    // Try initial fetch
    if (window.__hpNotifGetAll) {
      refreshBadge();
    }

    // Fast check: ensure bell exists every 2s (handles form navigation)
    window.__hpNotifBellTimers = true;
    setInterval(function () {
      ensureBell();
    }, CHECK_MS);

    // Slower refresh: update badge count every 60s
    setInterval(function () {
      if (isLoggedIn()) {
        refreshBadge();
      }
    }, REFRESH_MS);
  }

  // Listen for bridge ready event (fired by Python form init)
  window.addEventListener('hp-notif-bridge-ready', function () {
    log('hp-notif-bridge-ready event received');
    // Small delay to let Anvil finish rendering form HTML
    setTimeout(function () {
      ensureBell();
      refreshBadge();
    }, 500);
  });

  // Public API
  window.refreshNotificationBell = refreshBadge;
  window.toggleNotifDropdown = toggleDropdown;

  log('script loaded, readyState=' + document.readyState);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { setTimeout(init, 500); });
  } else {
    setTimeout(init, 500);
  }
})();

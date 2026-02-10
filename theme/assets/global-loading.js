/**
 * نظام التحميل الموحد - Helwan Plast
 * ====================================
 * يدعم 3 لودر: "hand" (اليد) و "spinner" (دوائر) و "code" (كود)
 *
 * التحكم:
 *   localStorage.setItem('hp_loader_type', 'hand')     ← لودر اليد (الافتراضي)
 *   localStorage.setItem('hp_loader_type', 'spinner')   ← لودر الدوائر
 *   localStorage.setItem('hp_loader_type', 'code')      ← لودر الكود
 *
 *   window.showLoadingOverlay()  ← إظهار يدوي
 *   window.hideLoadingOverlay()  ← إخفاء يدوي
 *   window.setLoaderType('hand' | 'spinner' | 'code') ← تغيير النوع وقت التشغيل
 */
(function () {
  'use strict';

  if (window.__hpLoadingInit) return;
  window.__hpLoadingInit = true;

  var OVERLAY_ID = 'hp-global-loading-overlay';
  var MAX_SHOW_MS = 45000;
  var showTime = 0;

  // ===== Loader Type Config =====
  function getLoaderType() {
    try { return localStorage.getItem('hp_loader_type') || 'hand'; }
    catch (e) { return 'hand'; }
  }

  // ===== HTML Templates =====
  var LOADERS = {
    hand:
      '<div class="hp-loader hp-loader-hand">' +
        '<div class="hand-loader">' +
          '<div class="hand-finger"></div><div class="hand-finger"></div>' +
          '<div class="hand-finger"></div><div class="hand-finger"></div>' +
          '<div class="hand-palm"></div><div class="hand-thumb"></div>' +
        '</div>' +
      '</div>',

    spinner:
      '<div class="hp-loader hp-loader-spinner">' +
        '<div class="hp-spinner-dots">' +
          '<div class="hp-dot"></div>' +
          '<div class="hp-dot"></div>' +
          '<div class="hp-dot"></div>' +
        '</div>' +
      '</div>',

    code:
      '<div class="hp-loader hp-loader-code">' +
        '<div class="hp-code-loader">' +
          '<span>&lt;</span>' +
          '<span>LOADING...</span>' +
          '<span>/&gt;</span>' +
        '</div>' +
      '</div>'
  };

  // ===== Overlay =====
  function getOverlay() {
    try {
      if (!document.body) return null;
      var el = document.getElementById(OVERLAY_ID);
      if (!el) {
        el = document.createElement('div');
        el.id = OVERLAY_ID;
        el.className = 'hp-loading-overlay';
        document.body.appendChild(el);
      }
      // Always update inner HTML to match current loader type
      var type = getLoaderType();
      var currentType = el.getAttribute('data-loader');
      if (currentType !== type) {
        el.innerHTML = LOADERS[type] || LOADERS.hand;
        el.setAttribute('data-loader', type);
      }
      return el;
    } catch (err) {
      return null;
    }
  }

  function show() {
    try {
      var o = getOverlay();
      if (o) {
        o.classList.add('show');
        if (showTime === 0) showTime = Date.now();
      }
    } catch (err) {}
  }

  function hide() {
    try {
      showTime = 0;
      var o = document.getElementById(OVERLAY_ID);
      if (o) o.classList.remove('show');
    } catch (err) {}
  }

  // ===== Spinner Detection =====
  function hasSpinner() {
    try {
      var el = document.querySelector && document.querySelector('.anvil-spinner');
      if (!el) return false;
      if (!el.isConnected) return false;
      if (el.offsetParent === null) return false;
      var p = el.parentElement;
      var steps = 0;
      while (p && p !== document.body && steps < 15) {
        var s = window.getComputedStyle(p);
        if (s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) < 0.05)
          return false;
        p = p.parentElement;
        steps++;
      }
      return true;
    } catch (err) {
      return false;
    }
  }

  // ===== Tick =====
  function tick() {
    try {
      if (!document.body) return;
      var overlay = document.getElementById(OVERLAY_ID);
      if (overlay && overlay.classList.contains('show') && showTime > 0) {
        if (Date.now() - showTime > MAX_SHOW_MS) {
          hide();
          return;
        }
      }
      if (hasSpinner()) show();
      else hide();
    } catch (err) {
      hide();
    }
  }

  // ===== Start (MutationObserver + fallback) =====
  var _tickTimer = 0;
  var DEBOUNCE_MS = 80;

  function debouncedTick() {
    if (_tickTimer) return;
    _tickTimer = setTimeout(function () {
      _tickTimer = 0;
      tick();
    }, DEBOUNCE_MS);
  }

  function start() {
    try {
      if (!document.body) { setTimeout(start, 100); return; }

      // Primary: MutationObserver on document.body
      if (typeof MutationObserver !== 'undefined') {
        var observer = new MutationObserver(debouncedTick);
        observer.observe(document.body, {
          childList: true,
          subtree: true,
          attributes: true,
          attributeFilter: ['class', 'style', 'hidden']
        });
      }

      // Safety-net fallback at low frequency
      setInterval(tick, 2000);

      // Initial check
      tick();
    } catch (err) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { setTimeout(start, 200); });
  } else {
    setTimeout(start, 200);
  }

  // ===== Public API =====
  window.showLoadingOverlay = show;
  window.hideLoadingOverlay = hide;
  window.setLoaderType = function (type) {
    if (type !== 'hand' && type !== 'spinner' && type !== 'code') return;
    try { localStorage.setItem('hp_loader_type', type); } catch (e) {}
    // Force rebuild overlay with new type
    var el = document.getElementById(OVERLAY_ID);
    if (el) el.removeAttribute('data-loader');
  };
  window.getLoaderType = getLoaderType;
})();

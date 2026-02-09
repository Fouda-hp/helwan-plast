/**
 * لودر اليد - خفيف جداً، بدون MutationObserver.
 * يظهر اليد عندما Anvil يعرض التحميل، ويخفيها عندما ينتهي (أو بعد وقت أقصى).
 */
(function () {
  'use strict';

  if (window.__hpLoadingInit) return;
  window.__hpLoadingInit = true;

  var OVERLAY_ID = 'hp-global-loading-overlay';
  var MAX_SHOW_MS = 45000;
  var showTime = 0;

  var HAND_HTML =
    '<div class="hand-loader">' +
    '<div class="hand-finger"></div><div class="hand-finger"></div>' +
    '<div class="hand-finger"></div><div class="hand-finger"></div>' +
    '<div class="hand-palm"></div><div class="hand-thumb"></div></div>';

  function getOverlay() {
    try {
      if (!document.body) return null;
      var el = document.getElementById(OVERLAY_ID);
      if (el) return el;
      el = document.createElement('div');
      el.id = OVERLAY_ID;
      el.className = 'hand-loader-wrapper fullscreen';
      el.innerHTML = HAND_HTML;
      document.body.appendChild(el);
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

  /**
   * التحميل شغال = السبينر موجود وفي الـ layout (أو حاويه ظاهر).
   * لو السبينر اتمسح من الـ DOM أو حاويه display:none أو مخفي = نختفي.
   */
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

  function tick() {
    try {
      if (!document.body) return;
      var overlay = document.getElementById(OVERLAY_ID);
      if (overlay && overlay.classList.contains('show') && showTime > 0) {
        var elapsed = Date.now() - showTime;
        if (elapsed > MAX_SHOW_MS) {
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

  function start() {
    try {
      if (!document.body) {
        setTimeout(start, 100);
        return;
      }
      setInterval(tick, 300);
      tick();
    } catch (err) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      setTimeout(start, 200);
    });
  } else {
    setTimeout(start, 200);
  }

  window.showLoadingOverlay = show;
  window.hideLoadingOverlay = hide;
})();

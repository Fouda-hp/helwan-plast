/**
 * شاشة التحميل الموحدة - لودر اليد. آمن ولا يعطل الصفحة.
 */
(function () {
  'use strict';

  var HAND_LOADER_HTML =
    '<div class="hand-loader">' +
      '<div class="hand-finger"></div><div class="hand-finger"></div>' +
      '<div class="hand-finger"></div><div class="hand-finger"></div>' +
      '<div class="hand-palm"></div><div class="hand-thumb"></div>' +
    '</div>';

  var OVERLAY_ID = 'hp-global-loading-overlay';

  function getOrCreateOverlay() {
    try {
      var el = document.getElementById(OVERLAY_ID);
      if (el) return el;
      if (!document.body) return null;
      el = document.createElement('div');
      el.id = OVERLAY_ID;
      el.className = 'hand-loader-wrapper fullscreen';
      el.innerHTML = HAND_LOADER_HTML;
      document.body.appendChild(el);
      return el;
    } catch (e) {
      return null;
    }
  }

  function showOurOverlay() {
    try {
      var overlay = getOrCreateOverlay();
      if (overlay) overlay.classList.add('show');
    } catch (e) {}
  }

  function hideOurOverlay() {
    try {
      var overlay = document.getElementById(OVERLAY_ID);
      if (overlay) overlay.classList.remove('show');
    } catch (e) {}
  }

  function findAnvilSpinner() {
    try {
      var doc = document;
      if (!doc || !doc.querySelector) return null;
      return doc.querySelector('.anvil-spinner') || doc.querySelector('[class*="anvil-spinner"]') || null;
    } catch (e) {
      return null;
    }
  }

  function isLoadingActive() {
    try {
      if (findAnvilSpinner()) return true;
      return false;
    } catch (e) {
      return false;
    }
  }

  function checkAndSync() {
    try {
      if (!document.body) return;
      if (isLoadingActive()) {
        showOurOverlay();
      } else {
        hideOurOverlay();
      }
    } catch (e) {}
  }

  function init() {
    try {
      if (!document.body) {
        setTimeout(init, 50);
        return;
      }
      getOrCreateOverlay();
      var obs = document.body;
      if (obs && window.MutationObserver) {
        var observer = new MutationObserver(function () {
          checkAndSync();
        });
        observer.observe(obs, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style'] });
      }
      setInterval(checkAndSync, 250);
      checkAndSync();
    } catch (e) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      setTimeout(init, 0);
    });
  } else {
    setTimeout(init, 0);
  }

  try {
    window.showLoadingOverlay = showOurOverlay;
    window.hideLoadingOverlay = hideOurOverlay;
  } catch (e) {}
})();

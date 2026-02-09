/**
 * شاشة التحميل الموحدة - اليد فقط. تظهر أثناء التحميل وتختفي عند الانتهاء.
 * نعتمد على overlay واحد نتحكم فيه، ونكشف انتهاء التحميل بدقة.
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
    var el = document.getElementById(OVERLAY_ID);
    if (el) return el;
    el = document.createElement('div');
    el.id = OVERLAY_ID;
    el.className = 'hand-loader-wrapper fullscreen';
    el.innerHTML = HAND_LOADER_HTML;
    document.body.appendChild(el);
    return el;
  }

  function showOurOverlay() {
    var overlay = getOrCreateOverlay();
    overlay.classList.add('show');
  }

  function hideOurOverlay() {
    var overlay = document.getElementById(OVERLAY_ID);
    if (overlay) overlay.classList.remove('show');
  }

  function findAnvilSpinner() {
    var doc = document;
    var el = doc.querySelector('.anvil-spinner') || doc.querySelector('[class*="anvil-spinner"]');
    if (el) return el;
    try {
      if (window.parent && window.parent.document && window.parent.document !== doc)
        return window.parent.document.querySelector('.anvil-spinner') || window.parent.document.querySelector('[class*="anvil-spinner"]');
    } catch (e) {}
    return null;
  }

  /** هل الـ overlay (حاوية السبينر) ظاهر فعلاً؟ لو مخفي = انتهى التحميل */
  function isAnvilOverlayVisible() {
    var spinner = findAnvilSpinner();
    if (!spinner || !spinner.parentElement) return false;
    var el = spinner.parentElement;
    var style = window.getComputedStyle(el);
    if (style.display === 'none') return false;
    if (style.visibility === 'hidden') return false;
    if (parseFloat(style.opacity) < 0.05) return false;
    var r = el.getBoundingClientRect();
    if (r.width < 50 || r.height < 50) return false;
    return true;
  }

  /** هل في overlay ثابت آخر (غير بتاعنا) يغطي الشاشة وظاهر؟ */
  function hasVisibleFullscreenOverlay() {
    var all = document.querySelectorAll('body *');
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      if (el.id === OVERLAY_ID) continue;
      var style = window.getComputedStyle(el);
      if (style.position !== 'fixed') continue;
      if (style.display === 'none' || style.visibility === 'hidden') continue;
      if (parseFloat(style.opacity) < 0.05) continue;
      var z = parseInt(style.zIndex, 10);
      if (isNaN(z) || z < 1000) continue;
      var r = el.getBoundingClientRect();
      if (r.width >= window.innerWidth * 0.7 && r.height >= window.innerHeight * 0.7)
        return true;
    }
    return false;
  }

  /** التحميل شغال = سبينر موجود وحاويتو ظاهرة، أو في overlay تاني ظاهر */
  function isLoadingActive() {
    if (findAnvilSpinner() && isAnvilOverlayVisible()) return true;
    if (hasVisibleFullscreenOverlay()) return true;
    return false;
  }

  function checkAndSync() {
    if (isLoadingActive()) {
      showOurOverlay();
    } else {
      hideOurOverlay();
    }
  }

  var observer = new MutationObserver(function () {
    checkAndSync();
  });

  function init() {
    getOrCreateOverlay();
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class', 'style'] });
    setInterval(checkAndSync, 100);
    checkAndSync();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.showLoadingOverlay = showOurOverlay;
  window.hideLoadingOverlay = hideOurOverlay;
})();

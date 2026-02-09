/**
 * Global loading - يعرض لودر اليد بدل النقاط/الدائرة الزرقاء في كل النظام.
 * الطريقة: نحقن اليد داخل نفس الـ overlay اللي Anvil بيستخدمه، أو نعرض overlay خاص بنا.
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
  var INJECTED_MARKER = 'hp-hand-injected';

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

  /** أي overlay ثابت ظاهر يغطي معظم الشاشة = شاشة تحميل. لو مخفي (انتهى التحميل) لا نعتبره */
  function scanForFullscreenOverlay() {
    var all = document.querySelectorAll('body *');
    for (var i = 0; i < all.length; i++) {
      var el = all[i];
      if (el.id === OVERLAY_ID) continue;
      var style = window.getComputedStyle(el);
      if (style.position !== 'fixed') continue;
      if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) continue;
      var z = parseInt(style.zIndex, 10);
      if (isNaN(z) || z < 1000) continue;
      var r = el.getBoundingClientRect();
      if (r.width >= window.innerWidth * 0.8 && r.height >= window.innerHeight * 0.8)
        return true;
    }
    return false;
  }

  /** إما نجد سبينر Anvil (.anvil-spinner أو عنصر بداخله) أو أي overlay ثابت يغطي الشاشة */
  function findAnvilLoadingContainer() {
    var doc = document;
    var sel = doc.querySelector('.anvil-spinner');
    if (sel && sel.parentElement) return sel.parentElement;
    sel = doc.querySelector('[class*="anvil-spinner"]');
    if (sel && sel.parentElement) return sel.parentElement;
    sel = doc.querySelector('[class*="loading"]');
    if (sel) {
      var style = window.getComputedStyle(sel);
      if (style.position === 'fixed' && (style.zIndex !== 'auto' && parseInt(style.zIndex, 10) > 1000))
        return sel;
    }
    return null;
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

  /** حقن لودر اليد داخل الـ overlay الأصلي لـ Anvil */
  function injectHandIntoAnvilOverlay() {
    var container = findAnvilLoadingContainer();
    if (!container) return false;
    if (container.getAttribute(INJECTED_MARKER)) return true;
    var spinner = findAnvilSpinner();
    if (spinner) {
      spinner.style.setProperty('display', 'none', 'important');
      spinner.style.setProperty('visibility', 'hidden', 'important');
    }
    var wrap = document.createElement('div');
    wrap.className = 'hand-loader-wrapper';
    wrap.style.cssText = 'display:flex;align-items:center;justify-content:center;position:absolute;inset:0;';
    wrap.innerHTML = HAND_LOADER_HTML;
    container.appendChild(wrap);
    container.setAttribute(INJECTED_MARKER, '1');
    container.style.display = 'flex';
    container.style.alignItems = 'center';
    container.style.justifyContent = 'center';
    return true;
  }

  function checkAndSync() {
    var spinner = findAnvilSpinner();
    var container = spinner ? findAnvilLoadingContainer() : null;
    var anyOverlay = scanForFullscreenOverlay();
    if (spinner || container) {
      if (injectHandIntoAnvilOverlay()) return;
      showOurOverlay();
      if (spinner) {
        spinner.style.setProperty('display', 'none', 'important');
        spinner.style.setProperty('visibility', 'hidden', 'important');
      }
    } else if (anyOverlay) {
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
    setInterval(checkAndSync, 150);
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

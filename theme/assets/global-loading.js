/**
 * لودر اليد - خفيف جداً، بدون MutationObserver حتى لا يثقل الصفحة.
 */
(function () {
  'use strict';

  var OVERLAY_ID = 'hp-global-loading-overlay';
  var HAND_HTML =
    '<div class="hand-loader">' +
    '<div class="hand-finger"></div><div class="hand-finger"></div>' +
    '<div class="hand-finger"></div><div class="hand-finger"></div>' +
    '<div class="hand-palm"></div><div class="hand-thumb"></div></div>';

  function getOverlay() {
    if (!document.body) return null;
    var el = document.getElementById(OVERLAY_ID);
    if (el) return el;
    el = document.createElement('div');
    el.id = OVERLAY_ID;
    el.className = 'hand-loader-wrapper fullscreen';
    el.innerHTML = HAND_HTML;
    document.body.appendChild(el);
    return el;
  }

  function show() {
    try {
      var o = getOverlay();
      if (o) o.classList.add('show');
    } catch (err) {}
  }

  function hide() {
    try {
      var o = document.getElementById(OVERLAY_ID);
      if (o) o.classList.remove('show');
    } catch (err) {}
  }

  function hasSpinner() {
    try {
      return !!(document.querySelector && document.querySelector('.anvil-spinner'));
    } catch (err) {
      return false;
    }
  }

  function tick() {
    try {
      if (!document.body) return;
      if (hasSpinner()) show();
      else hide();
    } catch (err) {}
  }

  function start() {
    try {
      if (!document.body) {
        setTimeout(start, 100);
        return;
      }
      setInterval(tick, 500);
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

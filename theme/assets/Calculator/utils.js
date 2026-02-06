// ===============================
// utils.js - Shared utilities (loaded FIRST)
// Unifies: debounce, showLoading, halfUpRound, debug logging
// ===============================

(function () {
  "use strict";

  if (window.__utilsLoaded) return;
  window.__utilsLoaded = true;

  // ----------------------------------------
  // Debug Flag - set to false in production
  // ----------------------------------------
  var DEBUG = false;
  try {
    // Auto-detect: enable debug in Anvil development mode
    if (window.location && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')) {
      DEBUG = true;
    }
  } catch (e) {}

  window.HP_DEBUG = DEBUG;

  window.debugLog = function () {
    if (DEBUG && typeof console !== 'undefined' && console.log) {
      console.log.apply(console, arguments);
    }
  };

  window.debugWarn = function () {
    if (DEBUG && typeof console !== 'undefined' && console.warn) {
      console.warn.apply(console, arguments);
    }
  };

  window.debugError = function () {
    if (typeof console !== 'undefined' && console.error) {
      console.error.apply(console, arguments);
    }
  };

  // ----------------------------------------
  // Debounce - unified (prevents duplicate calls)
  // ----------------------------------------
  window.debounce = function (fn, delay) {
    var timer = null;
    delay = delay || 300;
    return function () {
      var context = this;
      var args = arguments;
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        fn.apply(context, args);
        timer = null;
      }, delay);
    };
  };

  // ----------------------------------------
  // halfUpRound - unified (banker's rounding)
  // ----------------------------------------
  window.halfUpRound = function (v) {
    return Math.floor(v + 0.5);
  };

  // ----------------------------------------
  // showLoading - unified skeleton UI
  // ----------------------------------------
  window.showLoading = function (container) {
    if (!container) return;
    var html = '<div class="skeleton-container">';
    for (var i = 0; i < 5; i++) {
      html += '<div class="skeleton-row"><div class="skeleton-cell"></div><div class="skeleton-cell"></div><div class="skeleton-cell short"></div></div>';
    }
    html += '</div>';
    container.innerHTML = html;
  };

  // ----------------------------------------
  // showAlert - unified notification
  // ----------------------------------------
  if (typeof window.showAlert !== 'function') {
    window.showAlert = function (type, msg) {
      window.debugLog("[ALERT:" + type + "]", msg);
    };
  }

  // ----------------------------------------
  // Safe interval management (prevents memory leaks)
  // ----------------------------------------
  var _managedIntervals = [];
  var _managedTimeouts = [];

  window.safeSetInterval = function (fn, delay, maxRuns) {
    maxRuns = maxRuns || 0; // 0 = unlimited
    var runCount = 0;
    var id = setInterval(function () {
      runCount++;
      try {
        fn();
      } catch (e) {
        window.debugError("Interval error:", e);
      }
      if (maxRuns > 0 && runCount >= maxRuns) {
        clearInterval(id);
        var idx = _managedIntervals.indexOf(id);
        if (idx !== -1) _managedIntervals.splice(idx, 1);
      }
    }, delay);
    _managedIntervals.push(id);
    return id;
  };

  window.safeSetTimeout = function (fn, delay) {
    var id = setTimeout(function () {
      try {
        fn();
      } catch (e) {
        window.debugError("Timeout error:", e);
      }
      var idx = _managedTimeouts.indexOf(id);
      if (idx !== -1) _managedTimeouts.splice(idx, 1);
    }, delay);
    _managedTimeouts.push(id);
    return id;
  };

  window.cleanupAllTimers = function () {
    _managedIntervals.forEach(function (id) { clearInterval(id); });
    _managedTimeouts.forEach(function (id) { clearTimeout(id); });
    _managedIntervals = [];
    _managedTimeouts = [];
    window.debugLog("All managed timers cleaned up");
  };

  // Cleanup on page unload
  window.addEventListener('beforeunload', function () {
    window.cleanupAllTimers();
  });

  window.debugLog("utils.js loaded");
})();

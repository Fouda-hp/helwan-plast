/**
 * Prevent double submission: disable button while async action runs.
 * Usage: onclick="withButtonLock(this, function(){ return myAsyncAction(); })"
 */
(function () {
  if (window.withButtonLock) return;
  window.withButtonLock = function (btn, fn) {
    if (!btn || (btn.tagName && btn.tagName.toLowerCase() !== 'button' && btn.tagName.toLowerCase() !== 'input')) return Promise.resolve();
    if (btn.disabled) return Promise.resolve();
    var originalText = btn.textContent || btn.value || '';
    var loadingText = (btn.getAttribute && btn.getAttribute('data-loading-text')) || '...';
    btn.disabled = true;
    if (btn.textContent !== undefined) btn.textContent = loadingText;
    else if (btn.value !== undefined) btn.value = loadingText;
    var p = Promise.resolve(typeof fn === 'function' ? fn() : fn);
    return p.finally(function () {
      btn.disabled = false;
      if (btn.textContent !== undefined) btn.textContent = originalText;
      else if (btn.value !== undefined) btn.value = originalText;
    });
  };
})();

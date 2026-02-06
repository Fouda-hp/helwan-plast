// ===============================
// Colors Change Handler (ENHANCED)
// ===============================
(function() {

  function waitForElements() {
    const colorsSelect = document.getElementById("Number of colors");
    const widthSelect = document.getElementById("Machine width");

    if (!colorsSelect || !widthSelect) {
      if (waitForElements._retries === undefined) waitForElements._retries = 0;
      if (++waitForElements._retries < 50) {
        setTimeout(waitForElements, 100);
      }
      return;
    }

    if (typeof window.debugLog === 'function') window.debugLog("Colors change handler attached");

    // Add event listener with high priority
    colorsSelect.addEventListener("change", function() {
      const newColorsValue = this.value;
      if (typeof window.debugLog === 'function') window.debugLog("Colors changed to:", newColorsValue);

      if (!newColorsValue) return;

      // Force re-initialization
      window.cylindersInitialized = false;
      window.clearCylinderStyling?.();

      // Re-init table with new colors
      setTimeout(() => {
        window.initCylinderTable?.(newColorsValue);

        // Recalculate
        const widthValue = widthSelect.value;
        if (widthValue) {
          window.calculateCylinders?.(parseInt(widthValue), parseInt(newColorsValue));
        }
      }, 50);

    }, false);
  }

  waitForElements();
})();
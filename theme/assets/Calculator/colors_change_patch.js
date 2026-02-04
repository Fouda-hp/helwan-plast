// ===============================
// Colors Change Handler (ENHANCED)
// ===============================
(function() {

  function waitForElements() {
    const colorsSelect = document.getElementById("Number of colors");
    const widthSelect = document.getElementById("Machine width");

    if (!colorsSelect || !widthSelect) {
      setTimeout(waitForElements, 100);
      return;
    }

    console.log("🎨 Colors change handler attached");

    // Add event listener with high priority
    colorsSelect.addEventListener("change", function() {
      const newColorsValue = this.value;
      console.log("🔄 Colors changed to:", newColorsValue);

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
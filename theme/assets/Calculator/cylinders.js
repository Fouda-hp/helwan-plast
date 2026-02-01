// ===============================
// cylinders.js (COMPLETE FIX)
// ===============================

// 🔒 Prevent double loading
if (typeof window.__cylindersLoaded !== 'undefined') {
  console.warn("⚠️ cylinders.js already loaded - skipping");
} else {

  window.__cylindersLoaded = true;

  const CM_PRICES = {80:3.49,100:3.59,120:4.05,130:4.5,140:5.026,160:5.4};
  const DEFAULT_SIZES = [25,30,35,40,45,50,60];

  // 🔁 Central pricing trigger
  function triggerFullRecalculation() {
    if (window.LOADING_FROM_QUOTATION) return;
    if (typeof window.calculateAll === "function") {
      window.calculateAll();
    }
  }

  window.initCylinderTable = function (colorsValue) {
    if (window.LOADING_FROM_QUOTATION) return;

    console.log("🔄 Initializing cylinder table with colors:", colorsValue);

    for (let i = 1; i <= 12; i++) {
      const s = document.getElementById(`Size in CM${i}`);
      const c = document.getElementById(`Count${i}`);
      if (!s || !c) continue;

      if (i <= DEFAULT_SIZES.length) {
        s.value = DEFAULT_SIZES[i - 1];
        c.value = colorsValue || "";
      } else {
        s.value = "";
        c.value = "";
      }

      // Clear any error styling
      s.style.border = "";
      s.style.background = "";
      c.style.border = "";
      c.style.background = "";
    }

    // Immediately calculate after init
    const widthValue = document.getElementById("Machine width")?.value;
    if (widthValue && colorsValue) {
      triggerFullRecalculation();
    }
  };

  window.clearCylinderStyling = function() {
    for (let i = 1; i <= 12; i++) {
      const sizeInput = document.getElementById(`Size in CM${i}`);
      const countInput = document.getElementById(`Count${i}`);

      if (sizeInput) {
        sizeInput.style.border = "";
        sizeInput.style.background = "";
      }

      if (countInput) {
        countInput.style.border = "";
        countInput.style.background = "";
      }
    }
  };

  window.calculateCylinders = function (machineWidth, colorsValue) {
    console.log("💰 Calculating cylinders - Width:", machineWidth, "Colors:", colorsValue);

    let totalCost = 0;
    let totalCount = 0;

    const pricePerCM = CM_PRICES[machineWidth] || 0;
    const colorCount = parseInt(colorsValue || 0, 10);

    if (!pricePerCM) {
      console.warn("⚠️ No price found for width:", machineWidth);
      return;
    }

    for (let i = 1; i <= 12; i++) {
      const s = document.getElementById(`Size in CM${i}`);
      const c = document.getElementById(`Count${i}`);
      const costEl = s?.closest("tr")?.querySelector("td:last-child input");
      if (!s || !c || !costEl) continue;

      const size = parseFloat(s.value);
      const count = parseInt(c.value);

      if (!size || !count) {
        costEl.value = "";
        continue;
      }

      // 🔥 SPECIAL HANDLING FOR 40cm
      if (size === 40) {
        totalCount += count;

        if (count <= colorCount) {
          costEl.value = "FREE";
          console.log(`  Row ${i}: 40cm × ${count} = FREE (≤ ${colorCount})`);
        } else {
          const excessCount = count - colorCount;
          const rowCost = size * excessCount * pricePerCM;
          costEl.value = rowCost.toFixed(2);
          totalCost += rowCost;
          console.log(`  Row ${i}: 40cm × ${excessCount} (excess) = ${rowCost.toFixed(2)}`);
        }
        continue;
      }

      // Normal calculation for other sizes
      const rowCost = size * count * pricePerCM;
      costEl.value = rowCost.toFixed(2);
      totalCost += rowCost;
      totalCount += count;

      console.log(`  Row ${i}: ${size}cm × ${count} = ${rowCost.toFixed(2)}`);
    }

    window.STATE.cylindersUSD = Math.round(totalCost);
    window.STATE.cylindersCount = totalCount;

    const totalRow = document.querySelector(".total-row");
    if (totalRow) {
      totalRow.children[1].innerText = totalCount || "-";
      if (totalRow.children[2]) {
        totalRow.children[2].innerText = window.STATE.cylindersUSD.toLocaleString("en-US");
      }
    }

    console.log("✅ Total Count:", totalCount, "Total Cost:", window.STATE.cylindersUSD);
  };

  // ===============================
  // Validation Functions
  // ===============================

  function checkDuplicateSizes() {
    const sizes = new Map();
    let hasDuplicate = false;

    for (let i = 1; i <= 12; i++) {
      const input = document.getElementById(`Size in CM${i}`);
      if (!input) continue;

      const value = input.value.trim();

      input.style.border = "";
      input.style.background = "";

      if (!value) continue;

      if (sizes.has(value)) {
        const firstRow = sizes.get(value);
        const firstInput = document.getElementById(`Size in CM${firstRow}`);

        if (firstInput) {
          firstInput.style.border = "2px solid #c00000";
          firstInput.style.background = "#ffcccc";
        }

        input.style.border = "2px solid #c00000";
        input.style.background = "#ffcccc";
        hasDuplicate = true;
      } else {
        sizes.set(value, i);
      }
    }

    return hasDuplicate;
  }

  function validateCount(input, expectedCount) {
    if (!input) return;

    const value = input.value.trim();

    input.style.border = "";
    input.style.background = "";

    if (!value) return;

    const count = parseInt(value);

    if (!isNaN(count) && count !== expectedCount) {
      input.style.border = "2px solid #ff6600";
      input.style.background = "#ffe6cc";
    }
  }

  function validateAllCounts() {
    const colorsInput = document.getElementById("Number of colors");
    if (!colorsInput || !colorsInput.value) return;

    const expectedCount = parseInt(colorsInput.value);

    for (let i = 1; i <= 12; i++) {
      const countInput = document.getElementById(`Count${i}`);
      const sizeInput = document.getElementById(`Size in CM${i}`);

      if (sizeInput && sizeInput.value.trim()) {
        validateCount(countInput, expectedCount);
      }
    }
  }

  // ===============================
  // Init Validation
  // ===============================
  (function initCylinderValidation() {

    function init() {
      for (let i = 1; i <= 12; i++) {
        const sizeInput = document.getElementById(`Size in CM${i}`);
        const countInput = document.getElementById(`Count${i}`);

        if (!sizeInput || !countInput) {
          setTimeout(init, 100);
          return;
        }

        sizeInput.addEventListener("input", () => {
          checkDuplicateSizes();
          triggerFullRecalculation();
        });
        sizeInput.addEventListener("input", () => {
          checkDuplicateSizes();
          triggerFullRecalculation();
        });


        sizeInput.addEventListener("blur", () => {
          if (checkDuplicateSizes()) {
            showAlert(
              "error",
              "⚠️ Duplicate size detected!\n\n" +
              "Each size can only be entered once.\n" +
              "Please use different sizes or adjust the count."
            );
          }
        });

        countInput.addEventListener("input", () => {
          const colorsInput = document.getElementById("Number of colors");
          if (colorsInput && colorsInput.value) {
            validateCount(countInput, parseInt(colorsInput.value));
          }

          const colorsValue = document.getElementById("Number of colors")?.value;
          const widthValue = document.getElementById("Machine width")?.value;
          if (colorsValue && widthValue) {
            console.log("🔄 Recalculating from count input...");
            triggerFullRecalculation();
          }
        });

        countInput.addEventListener("blur", () => {
          const colorsValue = document.getElementById("Number of colors")?.value;
          const widthValue = document.getElementById("Machine width")?.value;
          if (colorsValue && widthValue) {
            console.log("🔄 Recalculating from count blur...");
            triggerFullRecalculation();
          }
        });
      }

      const colorsInput = document.getElementById("Number of colors");
      if (colorsInput) {
        colorsInput.addEventListener("change", () => {
          validateAllCounts();
        });
      }
    }

    init();
  })();

} // Close the guard
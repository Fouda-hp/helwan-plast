// ===============================
// ui.js
// ===============================

(function () {
  if (window.__uiLoaded) return;
  window.__uiLoaded = true;

  // ----------------------------------------
  // Helpers
  // ----------------------------------------
  function byId(id) {
    return document.getElementById(id);
  }

  function updateWinderOptionsByMaterial(material) {
    const winderSelect = document.getElementById("Winder");
    const winderUI = document.querySelector('.ui-select[data-target="Winder"]');

    if (!winderSelect || !winderUI) return;

    const options = winderUI.querySelectorAll(".ui-option");

    if (material === "PE") {
      // PE → Single + Double
      options.forEach(opt => {
        opt.style.display = "block";
      });
    } else {
      // Non-PE → Single only
      options.forEach(opt => {
        if (opt.dataset.value === "Single") {
          opt.style.display = "block";
        } else {
          opt.style.display = "none";
        }
      });

      // Force value = Single
      winderSelect.value = "Single";
      window.updateCustomSelect("Winder", "Single");
    }
  }

  // ----------------------------------------
  // Close custom selects on outside click
  // ----------------------------------------
  document.addEventListener("click", function (e) {
    document.querySelectorAll(".ui-select").forEach(select => {
      if (!select.contains(e.target)) {
        select.classList.remove("open");
      }
    });
  });

  // ----------------------------------------
  // Event delegation: أي نقر على .ui-select-trigger أو .ui-option يعمل حتى لو initCustomSelects ما ربطش
  // ----------------------------------------
  document.addEventListener("click", function (e) {
    var trigger = e.target && e.target.closest && e.target.closest(".ui-select-trigger");
    if (trigger) {
      var select = trigger.closest(".ui-select");
      if (select) {
        select.classList.toggle("open");
        e.stopPropagation();
      }
      return;
    }
    var option = e.target && e.target.closest && e.target.closest(".ui-option");
    if (option) {
      var sel = option.closest(".ui-select");
      if (sel) {
        var valueBox = sel.querySelector(".ui-select-value");
        var options = sel.querySelectorAll(".ui-option");
        var realSelect = byId(sel.dataset.target);
        if (valueBox && realSelect) {
          options.forEach(function (o) { o.classList.remove("selected"); });
          option.classList.add("selected");
          valueBox.textContent = option.textContent;
          realSelect.value = option.dataset.value || "";
          realSelect.dispatchEvent(new Event("change"));
          if (sel.dataset.target === "Material") {
            updateWinderOptionsByMaterial(option.dataset.value);
          }
          sel.classList.remove("open");
        }
        e.preventDefault();
        e.stopPropagation();
      }
    }
  }, true);

  // ----------------------------------------
  // Custom select logic (ربط مباشر - يستخدم كـ reinit أيضاً)
  // ----------------------------------------
  function initCustomSelects() {
    document.querySelectorAll(".ui-select").forEach(select => {
      if (select.dataset.eventsAttached) return; // تجنب تكرار الأحداث
      select.dataset.eventsAttached = "1";

      const trigger = select.querySelector(".ui-select-trigger");
      const valueBox = select.querySelector(".ui-select-value");
      const options = select.querySelectorAll(".ui-option");
      const realSelect = byId(select.dataset.target);

      if (!trigger || !realSelect) return;

      trigger.onclick = (e) => {
        select.classList.toggle("open");
        e.stopPropagation();
      };

      options.forEach(option => {
        option.onclick = (e) => {
          options.forEach(o => o.classList.remove("selected"));
          option.classList.add("selected");

          valueBox.textContent = option.textContent;
          realSelect.value = option.dataset.value;
          realSelect.dispatchEvent(new Event("change"));

          if (select.dataset.target === "Material") {
            updateWinderOptionsByMaterial(option.dataset.value);
          }

          select.classList.remove("open");
          e.stopPropagation();
        };
      });
    });
  }

  // ----------------------------------------
  // Auto numbering on first load
  // ----------------------------------------
  (function waitForInitialAutoNumbering(retries) {
    retries = retries || 0;
    if (
      typeof window.initDefaultValues === "function" &&
      typeof window.getNextClientCode === "function" &&
      typeof window.getNextQuotationNumber === "function"
    ) {
      window.initDefaultValues();
    } else if (retries < 50) {
      setTimeout(function() { waitForInitialAutoNumbering(retries + 1); }, 100);
    }
  })();

  // ----------------------------------------
  // Update custom select programmatically
  // ----------------------------------------
  window.updateCustomSelect = function (selectId, value) {
    if (!value) return;

    const realSelect = byId(selectId);
    if (!realSelect) return;

    realSelect.value = String(value);

    const customSelect = document.querySelector(
      `.ui-select[data-target="${selectId}"]`
    );
    if (!customSelect) return;

    const valueBox = customSelect.querySelector(".ui-select-value");
    const options = customSelect.querySelectorAll(".ui-option");

    options.forEach(option => {
      if (option.dataset.value === String(value)) {
        option.classList.add("selected");
        valueBox.textContent = option.textContent;
      } else {
        option.classList.remove("selected");
      }
    });
  };

  // ----------------------------------------
  // showOkModal defined after IIFE (line ~365) with smart type detection
  // ----------------------------------------

  window.showPricingModeModal = function (onSelect) {
    let modal = document.getElementById("pricingModeModal");

    if (!modal) {
      modal = document.createElement("div");
      modal.id = "pricingModeModal";
      modal.innerHTML = `
      <div class="modal-backdrop">
        <div class="modal-box pricing-modal">
          <h3>Pricing Mode</h3>
          <p>Please select pricing mode</p>

          <div class="pricing-actions">
            <button data-mode="In Stock">In Stock</button>
            <button data-mode="New Order">New Order</button>
          </div>
        </div>
      </div>
    `;
      document.body.appendChild(modal);

      modal.querySelectorAll(".pricing-actions button").forEach(btn => {
        btn.onclick = () => {
          modal.remove();
          onSelect(btn.dataset.mode);
        };
      });
    }
  };

  // ----------------------------------------
  // Hover effect for quotation rows
  // ----------------------------------------
  function attachQuotationRowHover() {
    const list = byId("quotationList");
    if (!list) return;

    list.addEventListener("mouseover", e => {
      const tr = e.target.closest("tr");
      if (tr) tr.classList.add("hover");
    });

    list.addEventListener("mouseout", e => {
      const tr = e.target.closest("tr");
      if (tr) tr.classList.remove("hover");
    });
  }

  // ----------------------------------------
  // Buttons: NEW / SAVE / HOME
  // ----------------------------------------
  function initButtons() {
    const btnNew  = byId("btn_new");
    const btnSave = byId("btn_save");
    const btnHome = byId("home_btn");


    if (btnNew) {
      btnNew.onclick = async () => {
        await window.resetFormToNew?.();

        showAlert(
          "success",
          "System is ready for data entry.\n" +
          "Client Code and Quotation Number have been generated automatically."
        );
      };
    }

    if (btnSave) {
      btnSave.onclick = async () => {

        const pricingInput = document.getElementById("Pricing_Mode");

        // 🧠 لو مفيش اختيار حالي → افتح المودال دايمًا
        if (!pricingInput.value) {
          window.showPricingModeModal(async mode => {
            pricingInput.value = mode;

            const result = await window.callPythonSave?.();

            if (result?.success) {
              showAlert("success", "Saved successfully");
              window.resetFormToNew?.();
            } else if (result?.message) {
              showAlert("error", result.message);
            } else {
              showAlert("error", "Save failed – no response from server.");
            }
          });
          return;
        }

        // 🔁 لو فيه اختيار (كوتيشن قديم) → برضه اسأل اليوزر
        pricingInput.value = "";

        window.showPricingModeModal(async mode => {
          pricingInput.value = mode;

          const result = await window.callPythonSave?.();

          if (result?.success) {
            showAlert("success", "Saved successfully");
            window.resetFormToNew?.();
          } else if (result?.message) {
            showAlert("error", result.message);
          } else {
            showAlert("error", "Save failed – no response from server.");
          }
        });
      };
    }


    // 🏠 Home Button
    if (btnHome) {
      btnHome.onclick = () => {
        location.hash = "#launcher";
      };
    }
  } // ✅ قفل الـ function هنا

  // ----------------------------------------
  // INIT (انتظار ظهور .ui-select ثم ربط الأحداث - لو الصفحة لسه مش محمّلة)
  // ----------------------------------------
  function tryInitCustomSelects() {
    if (document.querySelectorAll(".ui-select").length > 0) {
      initCustomSelects();
      const materialSelect = document.getElementById("Material");
      if (materialSelect) {
        updateWinderOptionsByMaterial(materialSelect.value);
      }
      return true;
    }
    return false;
  }
  if (!tryInitCustomSelects()) {
    var attempts = 0;
    var t = setInterval(function() {
      attempts++;
      if (tryInitCustomSelects() || attempts >= 25) {
        clearInterval(t);
      }
    }, 300);
  }
  window.reinitCalculatorDropdowns = initCustomSelects;

  attachQuotationRowHover();
  initButtons();

})(); // ✅ قفل الـ IIFE

function showAlert(type, message) {
  var overlay = document.getElementById("alertOverlay");
  if (!overlay) return;
  var modal   = overlay.querySelector(".alert-modal");
  var msgBox  = document.getElementById("alertMessage");
  var typeBox = modal ? modal.querySelector(".alert-type") : null;
  if (!modal || !msgBox) return;

  modal.className = "alert-modal alert-" + type;
  if (typeBox) typeBox.textContent = type.toUpperCase();
  msgBox.textContent = message;

  overlay.style.display = "flex";
}
window.showAlert = showAlert;

function hideAlert() {
  var el = document.getElementById("alertOverlay");
  if (el) el.style.display = "none";
}
window.hideAlert = hideAlert;
// =====================================
// Smart Alias -> Auto Alert Type Selector
// =====================================
window.showOkModal = function (msg) {

  let type = "error"; // default

  if (!msg || typeof msg !== "string") {
    showAlert("error", "Unknown error occurred.");
    return;
  }

  const text = msg.toLowerCase();

  // ===== Success keywords =====
  if (
    text.includes("saved") ||
    text.includes("success") ||
    text.includes("completed") ||
    text.includes("done")
  ) {
    type = "success";
  }

    // ===== Info keywords =====
  else if (
    text.includes("loading") ||
    text.includes("loaded") ||
    text.includes("updated") ||
    text.includes("calculat") ||
    text.includes("please wait")
  ) {
    type = "info";
  }

    // ===== Error keywords (explicit) =====
  else if (
    text.includes("error") ||
    text.includes("missing") ||
    text.includes("invalid") ||
    text.includes("duplicate") ||
    text.includes("required") ||
    text.includes("failed")
  ) {
    type = "error";
  }

  showAlert(type, msg);
};

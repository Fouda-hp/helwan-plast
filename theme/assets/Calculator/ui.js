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
  // Custom select logic
  // ----------------------------------------
  function initCustomSelects() {
    document.querySelectorAll(".ui-select").forEach(select => {
      const trigger = select.querySelector(".ui-select-trigger");
      const valueBox = select.querySelector(".ui-select-value");
      const options = select.querySelectorAll(".ui-option");
      const realSelect = byId(select.dataset.target);

      if (!trigger || !realSelect) return;

      trigger.onclick = () => {
        select.classList.toggle("open");
      };

      options.forEach(option => {
        option.onclick = () => {
          options.forEach(o => o.classList.remove("selected"));
          option.classList.add("selected");

          valueBox.textContent = option.textContent;
          realSelect.value = option.dataset.value;
          realSelect.dispatchEvent(new Event("change"));

          if (select.dataset.target === "Material") {
            updateWinderOptionsByMaterial(option.dataset.value);
          }

          select.classList.remove("open");
        };
      });
    });
  }

  // ----------------------------------------
  // Auto numbering on first load
  // ----------------------------------------
  (function waitForInitialAutoNumbering() {
    if (
      typeof window.initDefaultValues === "function" &&
      typeof window.getNextClientCode === "function" &&
      typeof window.getNextQuotationNumber === "function"
    ) {
      window.initDefaultValues();
    } else {
      setTimeout(waitForInitialAutoNumbering, 100);
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
  // OK modal
  // ----------------------------------------
  window.showOkModal = function (message) {
    let modal = byId("okModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "okModal";
      modal.innerHTML = `
        <div class="modal-backdrop">
          <div class="modal-box">
            <p id="okModalMsg"></p>
            <button id="okModalBtn">OK</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
      modal.querySelector("#okModalBtn").onclick = () => modal.remove();
    }
    modal.querySelector("#okModalMsg").innerText = message;
  };

  window.showPricingModeModal = function (onSelect) {
    let modal = document.getElementById("pricingModeModal");

    if (!modal) {
      modal = document.createElement("div");
      modal.id = "pricingModeModal";
      modal.innerHTML = `
      <div class="modal-backdrop">
        <div class="modal-box">
          <p>Please select pricing mode</p>
          <div style="display:flex; gap:12px; justify-content:center; margin-top:16px">
            <button id="btnInStock">In Stock</button>
            <button id="btnNewOrder">New Order</button>
          </div>
        </div>
      </div>
    `;
      document.body.appendChild(modal);
    }

    modal.querySelector("#btnInStock").onclick = () => {
      modal.remove();
      onSelect("In Stock");
    };

    modal.querySelector("#btnNewOrder").onclick = () => {
      modal.remove();
      onSelect("New Order");
    };
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

    let pricingModeHandled = false;

    if (btnNew) {
      btnNew.onclick = async () => {
        await window.resetFormToNew?.();
        pricingModeHandled = false;

        showAlert(
          "success",
          "System is ready for data entry.\n" +
          "Client Code and Quotation Number have been generated automatically."
        );
      };
    }

    if (btnSave) {
      btnSave.onclick = async () => {
        const result = await window.callPythonSave?.();

        if (result?.success) {
          pricingModeHandled = false;
          showAlert(
            "success",
            "Saved successfully");
          window.resetFormToNew?.();
          return;
        }

        if (result?.code === "SELECT_PRICING_MODE") {
          if (pricingModeHandled) {
            showAlert(
              "error",
              "Pricing mode selection failed.\nPlease try again."
            );
            return;
          }

          pricingModeHandled = true;

          window.showPricingModeModal(async mode => {
            const pricingInput = document.getElementById("Pricing_Mode");
            pricingInput.value = mode;

            const retryResult = await window.callPythonSave?.();

            if (retryResult?.success) {
              pricingModeHandled = false;
              window.showAlert(
                "success",
                "Saved successfully");
              window.resetFormToNew?.();
            } else if (retryResult?.message) {
              pricingModeHandled = false;
              showAlert(
                "success",
                retryResult.message);
            }
          });

          return;
        }

        if (result?.message) {
          showAlert(
            "error",
            result.message);
        }
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
  // INIT
  // ----------------------------------------
  initCustomSelects();
  attachQuotationRowHover();
  initButtons();

  // Sync winder on first load
  const materialSelect = document.getElementById("Material");
  if (materialSelect) {
    updateWinderOptionsByMaterial(materialSelect.value);
  }

})(); // ✅ قفل الـ IIFE

function showAlert(type, message) {
  const overlay = document.getElementById("alertOverlay");
  const modal   = overlay.querySelector(".alert-modal");
  const msgBox  = document.getElementById("alertMessage");
  const typeBox = modal.querySelector(".alert-type");

  modal.className = "alert-modal alert-" + type;
  typeBox.textContent = type.toUpperCase();
  msgBox.textContent = message;

  overlay.style.display = "flex";
}

function hideAlert() {
  document.getElementById("alertOverlay").style.display = "none";
}
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

// ===============================
// core.js
// ===============================
if (typeof window.debugLog !== 'function') window.debugLog = function () {};
if (typeof window.debugError !== 'function') window.debugError = function () {};

// Bridge Anvil
window.anvil = window.anvil || anvil;
window.__autoNumbersInitialized = false;

// -------------------------------
// Global States
// -------------------------------
window.CYLINDER_STATE = { mode: "idle" };
window.cylindersInitialized = false;
window.LOADING_FROM_QUOTATION = false;

window.STATE = {
  modelReady: false,
  baseMachineUSD: 0,
  machineWithCylUSD: 0,
  cylindersUSD: 0,
  cylindersCount: 0,
  overseasUSD: 0,
  localInStockEGP: 0,
  localNewOrderEGP: 0
};

// -------------------------------
// Helpers
// -------------------------------
function setTodayDate() {
  const dateInput = document.getElementById("Date");
  if (!dateInput) return;

  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");

  dateInput.value = `${yyyy}-${mm}-${dd}`;
}

// -------------------------------
// Init default values
// -------------------------------
window.initDefaultValues = async function () {
  try {
    const cc = document.getElementById("client_code");
    const qn = document.getElementById("Quotation#");

    if (cc && typeof window.getNextClientCode === "function") {
      cc.value = await window.getNextClientCode();
    }

    if (qn && typeof window.getNextQuotationNumber === "function") {
      qn.value = await window.getNextQuotationNumber();
    }

    setTodayDate();

    const totalRow = document.querySelector(".total-row");
    if (totalRow) {
      totalRow.children[1].innerText = "-";
      if (totalRow.children[2]) totalRow.children[2].innerText = "-";
    }

  } catch (e) {
    window.debugError("Init default values error:", e);
  }
};

// -------------------------------
// Wait for Python bridges
// -------------------------------
function waitForAutoNumbering() {
  if (
    typeof window.getNextClientCode === "function" &&
    typeof window.getNextQuotationNumber === "function"
  ) {
    if (!window.__autoNumbersInitialized) {
      window.__autoNumbersInitialized = true;
      window.initDefaultValues();
    }
  } else {
    setTimeout(waitForAutoNumbering, 100);
  }
}


document.addEventListener("DOMContentLoaded", () => {
  window.debugLog("core.js loaded");
  waitForAutoNumbering();
});

// -------------------------------
// Reset form (FIXED)
// -------------------------------
window.resetFormToNew = async function () {

  const manualIds = [
    "model_code",
    "Client Name",
    "Company",
    "Phone",
    "Country",
    "Address",
    "Email",
    "sales_rep",
    "Source",
    "Given Price",
    "Agreed Price",
    "Notes"
  ];
  const machinePriceIds = [
    "std_price",
    "price_with_cylinders",
    "overseas_price",
    "local_price",
    "new_order_price"
  ];

  machinePriceIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });

  manualIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });

  document.querySelectorAll("input[type='checkbox']").forEach(cb => {
    cb.checked = false;
  });

  document.querySelectorAll(".ui-select").forEach(sel => {
    const valueBox = sel.querySelector(".ui-select-value");
    if (valueBox) valueBox.textContent = "Select...";
    sel.querySelectorAll(".ui-option").forEach(o => o.classList.remove("selected"));
  });

  // 🔥 Clear cylinders (FIXED)
  for (let i = 1; i <= 12; i++) {
    const sizeInput  = document.getElementById(`Size in CM${i}`);
    const countInput = document.getElementById(`Count${i}`);

    if (sizeInput)  {
      sizeInput.value  = "";
      sizeInput.style.border = "";
      sizeInput.style.background = "";
    }

    if (countInput) {
      countInput.value = "";
      countInput.style.border = "";
      countInput.style.background = "";
    }

    // Clear cost by finding the readonly input in the same row
    if (sizeInput) {
      const row = sizeInput.closest("tr");
      if (row) {
        const costInput = row.querySelector("td:last-child input[readonly]");
        if (costInput) costInput.value = "";
      }
    }
  }

  // 🔥 Reset STATE
  window.STATE = {
    modelReady: false,
    baseMachineUSD: 0,
    machineWithCylUSD: 0,
    cylindersUSD: 0,
    cylindersCount: 0,
    cylindersCost: 0,
    overseasUSD: 0,
    localInStockEGP: 0,
    localNewOrderEGP: 0
  };

  // 🔥 Clear total row
  const totalRow = document.querySelector(".total-row");
  if (totalRow) {
    totalRow.children[1].innerText = "-";
    if (totalRow.children[2]) totalRow.children[2].innerText = "-";
  }

  // 🔥 Reset Pricing Mode
  const pricingMode = document.getElementById("Pricing_Mode");
  if (pricingMode) pricingMode.value = "";

  // 🔥 Reset cylinders flag
  window.cylindersInitialized = false;

  await window.initDefaultValues?.();
  setTodayDate();

  showAlert(
    "success",
    "System is ready for data entry.\n" +
    "Client Code and Quotation Number have been generated automatically."
  );
};
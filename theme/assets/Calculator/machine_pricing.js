// ========================================
// machine_pricing.js
// ========================================

(function () {
  if (window.__machinePricingLoaded) return;
  window.__machinePricingLoaded = true;

  const EXCHANGE_RATE = 47.5;

  const CONFIG = {
    SHIPPING_SEA: 3200,
    THS: 1000,
    EXPENSES_CLEARANCE: 1400,
    TAX_RATE: 0.15,
    BANK_COMMISSION: 0.0132
  };

  const machineType = document.getElementById("machine_type");
  const colors      = document.getElementById("Number of colors");
  const width       = document.getElementById("Machine width");
  const material    = document.getElementById("Material");
  const winder      = document.getElementById("Winder");

  window.modelInput = document.getElementById("model_code");
  const quotationInput = document.getElementById("Quotation#");

  const unw1 = document.getElementById("Pneumatic Unwind");
  const unw2 = document.getElementById("Hydraulic Station Unwind") || { checked:false };
  const rew1 = document.getElementById("Pneumatic Rewind");
  const rew2 = document.getElementById("Surface Rewind");

  const exchangeInput = document.getElementById("exchange_rate");
  if (exchangeInput) exchangeInput.value = EXCHANGE_RATE.toFixed(2);

  // ----------------------------------------
  // Helpers
  // ----------------------------------------

  function halfUpRound(v) {
    return Math.floor(v + 0.5);
  }

  function mapMachineType(v) {
    v = String(v || "").toLowerCase();
    if (v.includes("metal")) return "Metal anilox";
    if (v.includes("single")) return "Ceramic anilox Single Doctor Blade";
    if (v.includes("chamber")) return "Ceramic anilox Chamber Doctor Blade";
    return "";
  }

  function mapWinder(v) {
    v = String(v || "").toLowerCase();
    if (v.includes("single")) return "Single";
    if (v.includes("double")) return "Double";
    return "";
  }

  function getAniloxCode() {
    if (machineType.value === "Metal anilox") return "M";
    if (machineType.value === "Ceramic anilox Single Doctor Blade") return "C";
    if (machineType.value === "Ceramic anilox Chamber Doctor Blade") return "CC";
    return "";
  }

  function getMaterialWinderCode() {
    const m = material.value;
    const w = winder.value;
    if (m === "PE" && w === "Single") return "S";
    if (m === "PE" && w === "Double") return "D";
    if (m === "PP" && w === "Single") return "PS";
    if (m === "Nonwoven" && w === "Single") return "PS";
    if (m === "Paper to 100g") return "PP";
    if (m === "Paper to 200g") return "HS";
    if (m === "Paper to 300g") return "SS";
    return "";
  }

  function getUnwindRewindCode() {
    let u = "", r = "";
    if (unw1.checked) u = "P";
    if (unw2.checked) u = "H";
    if (rew1.checked) r = "P";
    if (rew2.checked) r = "S";
    return u + r;
  }

  function allowed() {
    return material.value === "PE" && winder.value === "Single";
  }

  function validate(cb) {
    if (!allowed()) {
      cb.checked = false;
      showModal("Selection Not Allowed", "Options allowed only when Material is PE and Winder is Single");
      return false;
    }
    return true;
  }

  function exclusive(a, b) {
    if (a.checked && b.checked) {
      b.checked = false;
      showModal("Conflict", "These options are mutually exclusive");
    }
  }

  function showModal(title, message) {
    let modal = document.getElementById("customModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "customModal";
      modal.innerHTML = `
        <div class="modal-backdrop">
          <div class="modal-box">
            <h3 id="modalTitle"></h3>
            <p id="modalMessage"></p>
            <button id="modalBtn">OK</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
      modal.querySelector("#modalBtn").onclick = () => modal.remove();
    }
    modal.querySelector("#modalTitle").innerText = title;
    modal.querySelector("#modalMessage").innerText = message;
  }

  // ----------------------------------------
  // Machine prices JSON
  // ----------------------------------------

  let MACHINE_PRICES = {};
  fetch("_/theme/machine_prices.json")
    .then(r => r.json())
    .then(d => MACHINE_PRICES = d);

  function getMachineBasePrice() {
    return MACHINE_PRICES?.[machineType.value]?.[colors.value]?.[width.value] || 0;
  }

  function getMaterialAdjustment() {
    return {
      PP: 9000,
      Nonwoven: 4000,
      "Paper to 100g": 1500,
      "Paper to 200g": 4750,
      "Paper to 300g": 11050
    }[material.value] || 0;
  }

  function getWinderAdjustment() {
    return winder.value === "Single" ? -4000 : 0;
  }

  function getOptionalAdjustment() {
    let t = 0;
    if (document.getElementById("Video inspection")?.checked) t += 4000;
    if (document.getElementById("PLC")?.checked) t += 1800;
    if (document.getElementById("Slitter")?.checked) t += 800;
    if (unw1.checked) t += 750;
    if (unw2.checked) t += 1500;
    if (rew1.checked) t += 750;
    if (rew2.checked) t += 3250;
    return t;
  }

  function isModelReady() {
    return machineType.value && colors.value && width.value && material.value && winder.value;
  }

  function clearPrices() {
    Object.keys(window.STATE).forEach(k => window.STATE[k] = 0);
    ["std_price","price_with_cylinders","overseas_price","local_price","new_order_price"]
      .forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = "";
      });
  }

  // ----------------------------------------
  // Core Calculations
  // ----------------------------------------

  window.buildModelCode = function () {
    if (!isModelReady()) return clearPrices();

    const an = getAniloxCode();
    const mw = getMaterialWinderCode();
    if (!an || !mw) return clearPrices();

    const ex = getUnwindRewindCode();
    const suffix = ex.length === 2 ? ex : mw + ex;

    modelInput.value = `SH${colors.value}-${width.value * 10}${an}/${suffix}`;
    calculateAll();
    tryGetQuotationNumber();
  };

  async function tryGetQuotationNumber() {
    if (!modelInput.value) return;
    if (quotationInput.value) return;
    if (window.QUOTATION_LOCKED) return;

    window.QUOTATION_LOCKED = true;

    try {
      const qNum = await window.anvil.server.call(
        "get_quotation_number_if_needed",
        quotationInput.value,
        modelInput.value
      );
      if (qNum) quotationInput.value = qNum;
    } catch (e) {
      console.error("Quotation number error:", e);
    }
  }

  window.calculateAll = function () {
    if (!isModelReady()) {
      window.calculateCylinders?.();
      return;
    }

    if (!window.cylindersInitialized && !window.LOADING_FROM_QUOTATION) {
      window.initCylinderTable?.(colors.value);
      window.cylindersInitialized = true;
    }

    window.STATE.baseMachineUSD =
      getMachineBasePrice() +
      getMaterialAdjustment() +
      getWinderAdjustment() +
      getOptionalAdjustment();

    window.calculateCylinders?.(parseInt(width.value), parseInt(colors.value));

    window.STATE.machineWithCylUSD =
      window.STATE.baseMachineUSD + window.STATE.cylindersUSD;

    window.STATE.overseasUSD =
      halfUpRound(window.STATE.machineWithCylUSD * 1.12);

    const baseUSD =
      CONFIG.SHIPPING_SEA +
      CONFIG.THS +
      (window.STATE.machineWithCylUSD *
       (1 + CONFIG.TAX_RATE + CONFIG.BANK_COMMISSION)) +
      CONFIG.EXPENSES_CLEARANCE;

    const egp = baseUSD * EXCHANGE_RATE;

    window.STATE.localInStockEGP =
      Math.round(egp * (colors.value == 4 ? 1.28 : 1.25));

    window.STATE.localNewOrderEGP =
      Math.round(egp * (colors.value == 4 ? 1.22 : 1.20));

    document.getElementById("std_price").value =
      window.STATE.baseMachineUSD.toLocaleString("en-US",{style:"currency",currency:"USD"});

    document.getElementById("price_with_cylinders").value =
      window.STATE.machineWithCylUSD.toLocaleString("en-US",{style:"currency",currency:"USD"});

    document.getElementById("overseas_price").value =
      window.STATE.overseasUSD.toLocaleString("en-US",{style:"currency",currency:"USD"});

    document.getElementById("local_price").value =
      window.STATE.localInStockEGP.toLocaleString("en-US");

    document.getElementById("new_order_price").value =
      window.STATE.localNewOrderEGP.toLocaleString("en-US");
  };

  // ----------------------------------------
  // Events
  // ----------------------------------------

  ["Video inspection","PLC","Slitter"].forEach(id => {
    const cb = document.getElementById(id);
    if (cb) cb.addEventListener("change", () => isModelReady() && calculateAll());
  });

  [unw1, unw2, rew1, rew2].forEach(cb => {
    if (!cb) return;
    cb.addEventListener("change", () => {
      if (!validate(cb)) return;
      if (cb === unw1) exclusive(unw1, unw2);
      if (cb === unw2) exclusive(unw2, unw1);
      if (cb === rew1) exclusive(rew1, rew2);
      if (cb === rew2) exclusive(rew2, rew1);
      if (isModelReady()) calculateAll();
      buildModelCode();
    });
  });

  [machineType, colors, width, material, winder].forEach(el => {
    if (el) el.addEventListener("change", buildModelCode);
  });

})();
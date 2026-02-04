<script>
  // bridge Anvil JS API
  const anvil = window.anvil;

(function initClientCodeAuto() {
  const nameInput  = document.getElementById("Client Name");
  const phoneInput = document.getElementById("Phone");
  const codeInput  = document.getElementById("client_code");

  if (!nameInput || !phoneInput || !codeInput) return;

  let LOCK = false;

  async function tryGetClientCode() {
    if (!nameInput.value || !phoneInput.value) return;
    if (codeInput.value) return;

    try {
      const code = await anvil.callable.get_or_create_client_code(
        nameInput.value,
        phoneInput.value
      );

      if (code) {
        codeInput.value = code;
      }
    } catch (e) {
      console.error("Client code error:", e);
    }
  }


  nameInput.addEventListener("blur", tryGetClientCode);
  phoneInput.addEventListener("blur", tryGetClientCode);
})();


document.addEventListener("click", function (e) {
  document.querySelectorAll(".ui-select").forEach(select => {
    if (!select.contains(e.target)) {
      select.classList.remove("open");
    }
  });
});

document.querySelectorAll(".ui-select").forEach(select => {
  const trigger = select.querySelector(".ui-select-trigger");
  const valueBox = select.querySelector(".ui-select-value");
  const options = select.querySelectorAll(".ui-option");
  const realSelect = document.getElementById(select.dataset.target);

  trigger.addEventListener("click", () => {
    select.classList.toggle("open");
  });

  options.forEach(option => {
    option.addEventListener("click", () => {
      options.forEach(o => o.classList.remove("selected"));
      option.classList.add("selected");

      valueBox.textContent = option.textContent;
      realSelect.value = option.dataset.value;

      realSelect.dispatchEvent(new Event("change"));
      select.classList.remove("open");
    });
  });
});
window.initDefaultValues = async function () {
  try {
    // Client Code
    const nextClientCode = await window.anvil.server.call("get_next_client_code");
    const cc = document.getElementById("client_code");
    if (cc) cc.value = nextClientCode;

    // Quotation #
    const nextQuotation = await window.anvil.server.call("get_next_quotation_number");
    const qn = document.getElementById("Quotation#");
    if (qn) qn.value = nextQuotation;

    // Total reset
    const totalCell = document.querySelector(".total-row td:last-child");
    if (totalCell) totalCell.innerText = "0";

  } catch (err) {
    console.error("Init default values error:", err);
  }
};

// ✅ Helper: Update Custom Select from Value
function updateCustomSelect(selectId, value) {
  const realSelect = document.getElementById(selectId);
  if (!realSelect || !value) return;

  // Set hidden select
  realSelect.value = String(value);

  // Update custom UI
  const customSelect = document.querySelector(`.ui-select[data-target="${selectId}"]`);
  if (!customSelect) return;

  const valueBox = customSelect.querySelector(".ui-select-value");
  const options = customSelect.querySelectorAll(".ui-option");

  // Find and select the right option
  let found = false;
  options.forEach(option => {
    if (option.dataset.value === String(value)) {
      option.classList.add("selected");
      valueBox.textContent = option.textContent;
      found = true;
    } else {
      option.classList.remove("selected");
    }
  });

  if (!found) {
    // Reset to placeholder if not found
    const placeholder = realSelect.querySelector('option[value=""]');
    if (placeholder && valueBox) {
      valueBox.textContent = "Select...";
    }
  }
}

window.CYLINDER_STATE = { mode: "idle" };

function showOkModal(message) {
  let modal = document.getElementById("okModal");
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
}

(function initNewButton(){
  const btnNew = document.getElementById("btn_new");
  if (!btnNew) return;

  btnNew.addEventListener("click", async () => {

    document.querySelectorAll("input, select, textarea").forEach(el => {
      if (el.type === "checkbox") el.checked = false;
      else if (!el.hasAttribute("readonly")) el.value = "";
    });

    document.querySelectorAll(".ui-select").forEach(sel => {
      const valueBox = sel.querySelector(".ui-select-value");
      if (valueBox) valueBox.textContent = "Select...";
      sel.querySelectorAll(".ui-option").forEach(o => o.classList.remove("selected"));
    });

    await window.initDefaultValues();

    CYLINDER_STATE.mode = "idle";
    STATE.cylindersUSD = 0;
    STATE.cylindersCount = 0;
    window.cylindersInitialized = false;

    const totalRow = document.querySelector(".total-row");
    if (totalRow) totalRow.children[1].innerText = "-";

    showAlert(
      "success",
      "A new quotation is ready. All previous data has been cleared.");
  });
})();



const totalRow = document.querySelector(".total-row");
if (totalRow) {
  totalRow.children[1].innerText = "-";
}


window.cylindersInitialized = false;
let LOADING_FROM_QUOTATION = false;

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

const STATE = {
  modelReady: false,
  baseMachineUSD: 0,
  machineWithCylUSD: 0,
  cylindersUSD: 0,
  cylindersCount: 0,
  overseasUSD: 0,
  localInStockEGP: 0,
  localNewOrderEGP: 0
};

window.loadQuotationFromOverlay = window.loadQuotationFromOverlay || null;

(function () {
  if (window.__machineCalculatorLoaded) return;
  window.__machineCalculatorLoaded = true;

  const homeBtn = document.getElementById("home_btn");
  if (homeBtn) homeBtn.onclick = () => location.hash = "#launcher";

  const EXCHANGE_RATE = 47.5;
  const CONFIG = {
    SHIPPING_SEA: 3200,
    THS: 1000,
    EXPENSES_CLEARANCE: 1400,
    TAX_RATE: 0.15,
    BANK_COMMISSION: 0.0132
  };

  const exchangeInput = document.getElementById("exchange_rate");
  if (exchangeInput) exchangeInput.value = EXCHANGE_RATE.toFixed(2);

  const machineType = document.getElementById("machine_type");
  const colors      = document.getElementById("Number of colors");
  const width       = document.getElementById("Machine width");
  const material    = document.getElementById("Material");
  const winder      = document.getElementById("Winder");
  window.modelInput = document.getElementById("model_code");  
  const quotationInput = document.getElementById("Quotation#");
  window.QUOTATION_LOCKED = false;


  const unw1 = document.getElementById("Pneumatic Unwind");
  const unw2 = document.getElementById("Hydraulic Station Unwind") || { checked:false };
  const rew1 = document.getElementById("Pneumatic Rewind");
  const rew2 = document.getElementById("Surface Rewind");

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
        </div>`;
      document.body.appendChild(modal);
      modal.querySelector("#modalBtn").onclick = () => modal.remove();
    }
    modal.querySelector("#modalTitle").innerText = title;
    modal.querySelector("#modalMessage").innerText = message;
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

  function halfUpRound(v) {
    return Math.floor(v + 0.5);
  }

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

  ["Video inspection", "PLC", "Slitter"].forEach(id => {
    const cb = document.getElementById(id);
    if (!cb) return;
    cb.addEventListener("change", () => {
      if (isModelReady()) calculateAll();
    });
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

  function isModelReady() {
    return machineType.value && colors.value && width.value && material.value && winder.value;
  }

  function clearPrices() {
    Object.keys(STATE).forEach(k => STATE[k] = 0);
    ["std_price","price_with_cylinders","overseas_price","local_price","new_order_price"]
      .forEach(id => document.getElementById(id).value = "");
  }

  function buildModelCode() {
    if (!isModelReady()) return clearPrices();

    const an = getAniloxCode();
    const mw = getMaterialWinderCode();
    if (!an || !mw) return clearPrices();

    const ex = getUnwindRewindCode();
    const suffix = ex.length === 2 ? ex : mw + ex;

    modelInput.value = `SH${colors.value}-${width.value * 10}${an}/${suffix}`;
    calculateAll();
    // 🔥 هنا بقى نطلب رقم الكوتيشن
    tryGetQuotationNumber();
  }
  async function tryGetQuotationNumber() {
    if (!modelInput.value) return;
    if (quotationInput.value) return; // موجود خلاص
    if (QUOTATION_LOCKED) return;

    QUOTATION_LOCKED = true;

    try {
      const qNum = await anvil.server.call(
        "get_quotation_number_if_needed",
        quotationInput.value,
        modelInput.value
      );

      if (qNum) {
        quotationInput.value = qNum;
      }
    } catch (e) {
      console.error("Quotation number error:", e);
    }
  }

  window.buildModelCode = buildModelCode;
  window.calculateAll = calculateAll;

  const CM_PRICES = {80:3.49,100:3.59,120:4.05,130:4.5,140:5.026,160:5.4};
  const DEFAULT_SIZES = [25,30,35,40,45,50,60];

  function initCylinderTable() {
    if (LOADING_FROM_QUOTATION) return;

    for (let i = 1; i <= 12; i++) {
      const s = document.getElementById(`Size in CM${i}`);
      const c = document.getElementById(`Count${i}`);
      if (!s || !c) continue;

      if (i <= DEFAULT_SIZES.length) {
        s.value = DEFAULT_SIZES[i-1];
        c.value = colors.value || "";
      } else {
        s.value = "";
        c.value = "";
      }
    }
  }
  window.QUOTATION_LOCKED = false;


  async function onModelReady() {
    const qInput = document.getElementById("Quotation#");
    if (!modelInput.value) return;
    if (qInput.value) return;
    if (window.QUOTATION_LOCKED) return;

    window.QUOTATION_LOCKED = true;

    try {
      const qNum = await anvil.callable.get_quotation_number_if_needed(
        qInput.value,
        modelInput.value
      );

      if (qNum) qInput.value = qNum;
    } catch (e) {
      console.error(e);
    }
  }

  modelInput.addEventListener("input", onModelReady);



  for (let i = 1; i <= 12; i++) {
    const s = document.getElementById(`Size in CM${i}`);
    const c = document.getElementById(`Count${i}`);
    if (s) s.addEventListener("input", calculateAll);
    if (c) c.addEventListener("input", calculateAll);
  }

  function calculateCylinders() {
    let totalCostRaw = 0;
    let totalCount = 0;

    const machineWidth = parseInt(width.value, 10);
    const pricePerCM = CM_PRICES[machineWidth] || 0;
    const colorCount = parseInt(colors.value || 0, 10);

    for (let i = 1; i <= 12; i++) {
      const sizeInput  = document.getElementById(`Size in CM${i}`);
      const countInput = document.getElementById(`Count${i}`);
      const costInput  = sizeInput?.closest("tr")?.querySelector("td:last-child input");

      if (!sizeInput || !countInput || !costInput) continue;

      const size  = parseFloat(sizeInput.value);
      const count = parseInt(countInput.value);

      if (!size || !count || !pricePerCM) {
        costInput.value = "";
        continue;
      }

      let effectiveCount = count;
      let rowCost = 0;

      if (size === 40) {
        if (count <= colorCount) {
          costInput.value = "FREE";
          totalCount += count;
          continue;
        } else {
          effectiveCount = count - colorCount;
        }
      }

      rowCost = size * effectiveCount * pricePerCM;
      costInput.value = rowCost.toFixed(2);
      totalCostRaw += rowCost;
      totalCount += count;
    }

    STATE.cylindersUSD = halfUpRound(totalCostRaw);
    STATE.cylindersCount = totalCount;

    const totalRow = document.querySelector(".total-row");
    if (totalRow) {
      totalRow.children[1].innerText = totalCount > 0 ? totalCount : "-";
    }

    const totalCell = document.querySelector(".total-row td:last-child");
    if (totalCell) {
      totalCell.innerText = STATE.cylindersUSD.toLocaleString("en-US");
    }
  }
  window.calculateCylinders = calculateCylinders;

  function calculateAll() {
    if (!isModelReady()) {
      calculateCylinders();
      return;
    }

    if (!window.cylindersInitialized && !LOADING_FROM_QUOTATION) {
      initCylinderTable();
      window.cylindersInitialized = true;
    }

    STATE.baseMachineUSD =
      getMachineBasePrice() +
      getMaterialAdjustment() +
      getWinderAdjustment() +
      getOptionalAdjustment();

    calculateCylinders();

    STATE.machineWithCylUSD = STATE.baseMachineUSD + STATE.cylindersUSD;
    STATE.overseasUSD = halfUpRound(STATE.machineWithCylUSD * 1.12);

    const baseUSD =
      CONFIG.SHIPPING_SEA +
      CONFIG.THS +
      (STATE.machineWithCylUSD * (1 + CONFIG.TAX_RATE + CONFIG.BANK_COMMISSION)) +
      CONFIG.EXPENSES_CLEARANCE;

    const egp = baseUSD * EXCHANGE_RATE;
    STATE.localInStockEGP = Math.round(egp * (colors.value == 4 ? 1.28 : 1.25));
    STATE.localNewOrderEGP = Math.round(egp * (colors.value == 4 ? 1.22 : 1.20));

    document.getElementById("std_price").value =
      STATE.baseMachineUSD.toLocaleString("en-US",{style:"currency",currency:"USD"});
    document.getElementById("price_with_cylinders").value =
      STATE.machineWithCylUSD.toLocaleString("en-US",{style:"currency",currency:"USD"});
    document.getElementById("overseas_price").value =
      STATE.overseasUSD.toLocaleString("en-US",{style:"currency",currency:"USD"});
    document.getElementById("local_price").value =
      STATE.localInStockEGP.toLocaleString("en-US");
    document.getElementById("new_order_price").value =
      STATE.localNewOrderEGP.toLocaleString("en-US");
  }

  [machineType,colors,width,material,winder].forEach(e=>{
    if (e) e.addEventListener("change", buildModelCode);
  });

})();

(function initQuotationOverlay() {
  if (window.__quotationOverlayLoaded) return;
  window.__quotationOverlayLoaded = true;

  function byId(id) {
    return document.getElementById(id);
  }

  function tryInit() {
    const overlay  = byId("quotationOverlay");
    const closeBtn = byId("btnCloseOverlay");
    const list     = byId("quotationList");
    const openBtn  = byId("btn_search_quotation");

    if (!overlay || !openBtn || !list) {
      setTimeout(tryInit, 100);
      return;
    }

    function showOverlay() {
      overlay.style.display = "flex";
    }

    function hideOverlay() {
      overlay.style.display = "none";
    }

    if (closeBtn) closeBtn.onclick = hideOverlay;

    openBtn.onclick = async () => {
      list.innerHTML = "";

      const data = await window.getQuotationsForOverlay?.();
      if (!data || !data.length) {
        alert("No quotations found");
        return;
      }

      data.forEach(r => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${r["Client Name"] || ""}</td>
          <td>${r["Quotation#"] || ""}</td>
          <td>${r["Date"] || ""}</td>
        `;

        tr.ondblclick = () => {
          window.loadQuotationFromOverlay?.(r);
          hideOverlay();
        };

        list.appendChild(tr);
      });

      showOverlay();
    };
  }

  tryInit();
})();

function getField(record, names) {
  for (let n of names) {
    if (record[n] !== undefined && record[n] !== null) {
      return record[n];
    }
  }
  return "";
}

function getCylinderValue(record, base, i) {
  const keys = [
    `${base}${i}`,
    `${base} ${i}`,
    `${base}_${i}`,
    `${base}-${i}`,
    `${base} (${i})`
  ];

  for (let k of keys) {
    const val = record[k];
    if (val !== undefined && val !== null && val !== "") {
      return val;
    }
  }
  return "";
}

window.loadQuotationFromOverlay = function (record) {
  if (!record) return;

  function set(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value ?? "";
  }

  function setSelect(id, value) {
    if (!value) return;
    updateCustomSelect(id, value);  // ✅ استخدام Helper
  }

  function setCheckbox(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    const v = String(value || "").trim().toUpperCase();
    el.checked = (v === "YES");
  }

  // Client Data
  set("client_code", record["Client Code"]);
  set("Quotation#", record["Quotation#"]);
  set("Date", record["Date"]);
  set("Client Name", record["Client Name"]);
  set("Company", record["Company"]);
  set("Phone", record["Phone"]);
  set("Country", record["Country"]);
  set("Address", record["Address"]);
  set("Email", record["Email"]);
  set("sales_rep", record["Sales Rep"]);
  set("Source", record["Source"]);
  set("Given Price", record["Given Price"]);
  set("Agreed Price", record["Agreed Price"]);
  set("Notes", record["Notes"]);

  // Machine - ✅ استخدام updateCustomSelect
  const machineTypeValue = record["machine type"] ?? record["Machine type"] ?? record["machine_type"] ?? "";
  setSelect("machine_type", mapMachineType(machineTypeValue));
  setSelect("Number of colors", record["Number of colors"]);
  setSelect("Machine width", record["Machine width"]);
  setSelect("Material", record["Material"]);
  setSelect("Winder", mapWinder(record["Winder"]));

  // Optional Checkboxes
  setCheckbox("Video inspection", record["Video inspection"]);
  setCheckbox("PLC", record["PLC"]);
  setCheckbox("Slitter", record["Slitter"]);
  setCheckbox("Pneumatic Unwind", record["Pneumatic Unwind"]);
  setCheckbox("Hydraulic Station Unwind", record["Hydraulic Station Unwind"]);
  setCheckbox("Pneumatic Rewind", record["Pneumatic Rewind"]);
  setCheckbox("Surface Rewind", record["Surface Rewind"]);

  // Cylinders
  LOADING_FROM_QUOTATION = true;
  window.cylindersInitialized = false;

  for (let i = 1; i <= 12; i++) {
    const sEl = document.getElementById(`Size in CM${i}`);
    const cEl = document.getElementById(`Count${i}`);
    if (sEl) sEl.value = "";
    if (cEl) cEl.value = "";
  }

  setTimeout(() => {
    for (let i = 1; i <= 12; i++) {
      const size  = getCylinderValue(record, "Size in CM", i);
      const count = getCylinderValue(record, "Count", i);

      const sEl = document.getElementById(`Size in CM${i}`);
      const cEl = document.getElementById(`Count${i}`);

      if (sEl && size) sEl.value = size;
      if (cEl && count) cEl.value = count;
    }

    window.cylindersInitialized = true;
    LOADING_FROM_QUOTATION = false;

    buildModelCode();
    calculateAll();
  }, 400);
};

(function initClientSearchOverlay() {
  if (window.__clientSearchOverlayLoaded) return;
  window.__clientSearchOverlayLoaded = true;

  function byId(id) {
    return document.getElementById(id);
  }

  function tryInit() {
    const overlay  = byId("clientOverlay");
    const closeBtn = byId("btnCloseClientOverlay");
    const list     = byId("clientList");
    const openBtn  = byId("btn_search_client");

    if (!overlay || !openBtn || !list) {
      setTimeout(tryInit, 100);
      return;
    }

    function showOverlay() {
      overlay.style.display = "flex";
    }

    function hideOverlay() {
      overlay.style.display = "none";
    }

    if (closeBtn) closeBtn.onclick = hideOverlay;

    openBtn.onclick = async () => {
      list.innerHTML = "";

      const data = await window.getClientsForOverlay?.();
      if (!data || !data.length) {
        alert("No clients found");
        return;
      }

      data.forEach(r => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${r["Client Code"] || ""}</td>
          <td>${r["Client Name"] || ""}</td>
          <td>${r["Company"] || ""}</td>
          <td>${r["Phone"] || ""}</td>
        `;

        tr.ondblclick = () => {
          window.loadClientFromOverlay?.(r);
          hideOverlay();
        };

        list.appendChild(tr);
      });

      showOverlay();
    };
  }

  tryInit();
})();

window.loadClientFromOverlay = function (record) {
  if (!record) return;

  function set(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value ?? "";
  }

  set("client_code", record["Client Code"]);
  set("Client Name", record["Client Name"]);
  set("Company", record["Company"]);
  set("Phone", record["Phone"]);
  set("Country", record["Country"]);
  set("Address", record["Address"]);
  set("Email", record["Email"]);
  set("sales_rep", record["Sales Rep"]);
  set("Source", record["Source"]);
};

(function initSaveButton() {
  const saveBtn = document.getElementById("btn_save");
  if (!saveBtn) return;

  saveBtn.addEventListener("click", async () => {
    console.log("💾 Save clicked");

    try {
      const res = await window.callPythonSave?.();

      // 🔴 لو مفيش رد
      if (!res) {
        alert("No response from server.");
        return;
      }

      // 🔴 فشل فالديشن (سعر أقل / بيانات ناقصة / أي خطأ)
      if (res.success === false) {
        // رسالة واضحة بالسعر المرجعي

        showAlert(
          "error",
          res.message || "Validation error occurred");

        // ⛔ مهم: مفيش NEW
        // ⛔ مفيش Reset
        return;
      }

      // ✅ نجح الحفظ
      showAlert(
        "error",
        "Quotation saved successfully ✅");

      // ✅ يمسح الفورم بس في حالة النجاح الحقيقي
      document.getElementById("btn_new")?.click();

    } catch (err) {
      console.error("Save error:", err);
      alert("An error occurred while saving.");
    }
  });
})();



// ========================================
// 🔥 STEP 2: REPLACE THE ENTIRE collectFormData SECTION
// Find "(function initPricingMode()" and replace EVERYTHING inside it
// ========================================

(function initPricingMode() {
  const overseasCheckbox = document.getElementById("Overseas clients");
  const pricingModeRow = document.getElementById("pricing_mode_row");

  if (overseasCheckbox && pricingModeRow) {
    overseasCheckbox.addEventListener("change", () => {
      pricingModeRow.style.display = overseasCheckbox.checked ? "none" : "grid";
    });
  }

  window.collectFormData = function () {

    function getValue(id) {
      const el = document.getElementById(id);
      if (!el) return null;
      if (el.type === "checkbox") return el.checked;
      return el.value || null;
    }

    function cleanNumber(value) {
      if (!value) return null;
      if (value === "FREE") return 0;
      const cleaned = String(value).replace(/[$,\s]/g, "");
      const num = parseFloat(cleaned);
      return isNaN(num) ? null : num;
    }

    const data = {
      'Client Code': getValue('client_code'),
      'Quotation#': getValue('Quotation#'),
      'Date': getValue('Date'),
      'Client Name': getValue('Client Name'),
      'Company': getValue('Company'),
      'Phone': getValue('Phone'),
      'Country': getValue('Country'),
      'Address': getValue('Address'),
      'Email': getValue('Email'),
      'Sales Rep': getValue('sales_rep'),
      'Source': getValue('Source'),

      'Given Price': cleanNumber(getValue('Given Price')),
      'Agreed Price': cleanNumber(getValue('Agreed Price')),
      'Notes': getValue('Notes'),

      'Model': getValue('model_code'),
      'Machine type': getValue('machine_type'),
      'Number of colors': getValue('Number of colors'),
      'Machine width': getValue('Machine width'),
      'Material': getValue('Material'),
      'Winder': getValue('Winder'),

      'Video inspection': getValue('Video inspection'),
      'PLC': getValue('PLC'),
      'Slitter': getValue('Slitter'),
      'Pneumatic Unwind': getValue('Pneumatic Unwind'),
      'Hydraulic Station Unwind': getValue('Hydraulic Station Unwind'),
      'Pneumatic Rewind': getValue('Pneumatic Rewind'),
      'Surface Rewind': getValue('Surface Rewind'),

      'Standard Machine FOB cost': cleanNumber(getValue('std_price')),
      'Machine FOB cost With Cylinders': cleanNumber(getValue('price_with_cylinders')),
      'FOB price for over seas clients': cleanNumber(getValue('overseas_price')),
      'Exchange Rate': cleanNumber(getValue('exchange_rate')),
      'In Stock': cleanNumber(getValue('local_price')),
      'New Order': cleanNumber(getValue('new_order_price')),

      'Overseas clients': getValue('Overseas clients'),
      'Pricing Mode': getValue('Pricing Mode'),
    };

    for (let i = 1; i <= 12; i++) {
      data[`Size in CM${i}`] = getValue(`Size in CM${i}`);
      data[`Count${i}`] = getValue(`Count${i}`);

      const sizeInput = document.getElementById(`Size in CM${i}`);
      if (sizeInput) {
        const row = sizeInput.closest("tr");
        const costInput = row?.querySelector("td:last-child input");
        if (costInput) {
          data[`Cost${i}`] = cleanNumber(costInput.value);
        }
      }
    }

    console.log("📦 Collected data:", data);
    return data;
  };
  document.addEventListener("DOMContentLoaded", () => {
    window.initDefaultValues?.();
  });

})();

</script>
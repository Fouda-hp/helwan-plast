// ========================================
// quotations.js
// ========================================

(function () {
  if (window.__quotationsLoaded) return;
  window.__quotationsLoaded = true;

  window.loadQuotationFromOverlay = window.loadQuotationFromOverlay || null;
  window.LOADING_FROM_QUOTATION = false;
  window.QUOTATION_LOCKED = false;

  // ----------------------------------------
  // Helpers
  // ----------------------------------------

  function byId(id) {
    return document.getElementById(id);
  }

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
      const v = record[k];
      if (v !== undefined && v !== null && v !== "") {
        return v;
      }
    }
    return "";
  }

  function setValue(id, value) {
    const el = byId(id);
    if (el) el.value = value ?? "";
  }

  function setCheckbox(id, value) {
    const el = byId(id);
    if (!el) return;
    const v = String(value || "").trim().toUpperCase();
    el.checked = (v === "YES" || v === "TRUE");
  }

  function setSelect(id, value) {
    if (!value) return;
    if (window.updateCustomSelect) {
      window.updateCustomSelect(id, value);
    } else {
      const el = byId(id);
      if (el) el.value = value;
    }
  }

  // ----------------------------------------
  // Load quotation into form
  // ----------------------------------------

  window.loadQuotationFromOverlay = function (record) {
    if (!record) return;

    window.LOADING_FROM_QUOTATION = true;
    window.cylindersInitialized = false;

    // -------- Client data
    setValue("client_code", record["Client Code"]);
    setValue("Quotation#", record["Quotation#"]);
    setValue("Date", record["Date"]);
    setValue("Client Name", record["Client Name"]);
    setValue("Company", record["Company"]);
    setValue("Phone", record["Phone"]);
    setValue("Country", record["Country"]);
    setValue("Address", record["Address"]);
    setValue("Email", record["Email"]);
    setValue("sales_rep", record["Sales Rep"]);
    setValue("Source", record["Source"]);
    setValue("Given Price", record["Given Price"]);
    setValue("Agreed Price", record["Agreed Price"]);
    setValue("Notes", record["Notes"]);

    // -------- Machine selects
    const machineTypeValue =
      record["machine type"] ??
      record["Machine type"] ??
      record["machine_type"] ??
      "";

    setSelect("machine_type", window.mapMachineType?.(machineTypeValue) || machineTypeValue);
    setSelect("Number of colors", record["Number of colors"]);
    setSelect("Machine width", record["Machine width"]);
    setSelect("Material", record["Material"]);
    setSelect("Winder", window.mapWinder?.(record["Winder"]) || record["Winder"]);

    // -------- Options
    [
      "Video inspection",
      "PLC",
      "Slitter",
      "Pneumatic Unwind",
      "Hydraulic Station Unwind",
      "Pneumatic Rewind",
      "Surface Rewind"
    ].forEach(id => setCheckbox(id, record[id]));

    // -------- Clear cylinders first
    for (let i = 1; i <= 12; i++) {
      setValue(`Size in CM${i}`, "");
      setValue(`Count${i}`, "");
    }

    // -------- Fill cylinders (delayed to avoid race with calculator)
    setTimeout(() => {
      for (let i = 1; i <= 12; i++) {
        const size  = getCylinderValue(record, "Size in CM", i);
        const count = getCylinderValue(record, "Count", i);
        if (size) setValue(`Size in CM${i}`, size);
        if (count) setValue(`Count${i}`, count);
      }

      window.cylindersInitialized = true;
      window.LOADING_FROM_QUOTATION = false;

      window.buildModelCode?.();
      window.calculateAll?.();
    }, 300);
  };

  // ----------------------------------------
  // Quotation overlay (search)
  // ----------------------------------------

  (function initQuotationOverlay() {

    function tryInit() {
      const overlay  = byId("quotationOverlay");
      const closeBtn = byId("btnCloseOverlay");
      const list     = byId("quotationList");
      const openBtn  = byId("btn_search_quotation");

      if (!overlay || !list || !openBtn) {
        setTimeout(tryInit, 100);
        return;
      }

      function show() {
        overlay.style.display = "flex";
      }

      function hide() {
        overlay.style.display = "none";
      }

      if (closeBtn) closeBtn.onclick = hide;

      openBtn.onclick = async () => {
        list.innerHTML = "";

        const data = await window.getQuotationsForOverlay?.();
        if (!data || !data.length) {
          showAlert(
            "error",
            "Validation Error",
            "Missing required data. Please check inputs."
          );

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
            window.loadQuotationFromOverlay(r);
            hide();
          };
          list.appendChild(tr);
        });

        show();
      };
    }

    tryInit();
  })();

})();

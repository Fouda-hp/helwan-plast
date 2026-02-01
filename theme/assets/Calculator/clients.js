// ========================================
// clients.js  (Anvil-safe pattern)
// ========================================

(function () {
  if (window.__clientsLoaded) return;
  window.__clientsLoaded = true;

  // ----------------------------------------
  // Helpers
  // ----------------------------------------
  function byId(id) {
    return document.getElementById(id);
  }

  function setValue(id, value) {
    const el = byId(id);
    if (el) el.value = value ?? "";
  }

  // ----------------------------------------
  // Auto client code (name + phone)
  // ----------------------------------------
  function initClientAutoCode() {
    const nameInput  = byId("Client Name");
    const phoneInput = byId("Phone");
    const codeInput  = byId("client_code");

    if (!nameInput || !phoneInput || !codeInput) {
      setTimeout(initClientAutoCode, 100);
      return;
    }

    async function tryGetClientCode() {
      if (!nameInput.value || !phoneInput.value) return;
      if (codeInput.value) return;

      try {
        const code = await window.getClientCodeFromServer?.(
          nameInput.value,
          phoneInput.value
        );
        if (code) codeInput.value = code;
      } catch (e) {
        console.error("Client code error:", e);
      }
    }

    nameInput.addEventListener("blur", tryGetClientCode);
    phoneInput.addEventListener("blur", tryGetClientCode);
  }

  initClientAutoCode();

  // ----------------------------------------
  // Load client from overlay
  // ----------------------------------------
  window.loadClientFromOverlay = function (record) {
    if (!record) return;

    setValue("client_code", record["Client Code"]);
    setValue("Client Name", record["Client Name"]);
    setValue("Company", record["Company"]);
    setValue("Phone", record["Phone"]);
    setValue("Country", record["Country"]);
    setValue("Address", record["Address"]);
    setValue("Email", record["Email"]);
    setValue("sales_rep", record["Sales Rep"]);
    setValue("Source", record["Source"]);
  };

  // ----------------------------------------
  // Client search overlay
  // ----------------------------------------
  (function initClientOverlay() {

    function tryInit() {
      const overlay  = byId("clientOverlay");
      const closeBtn = byId("btnCloseClientOverlay");
      const list     = byId("clientList");
      const openBtn  = byId("btn_search_client");

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

        const data = await window.getClientsForOverlay?.();
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
            <td>${r["Client Code"] || ""}</td>
            <td>${r["Client Name"] || ""}</td>
            <td>${r["Company"] || ""}</td>
            <td>${r["Phone"] || ""}</td>
          `;
          tr.ondblclick = () => {
            window.loadClientFromOverlay(r);
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

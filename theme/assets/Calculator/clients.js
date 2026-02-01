// ========================================
// clients.js - WITH SEARCH, PAGINATION & LOADING
// ========================================

(function () {
  if (window.__clientsLoaded) return;
  window.__clientsLoaded = true;

  // Pagination state
  var currentPage = 1;
  var totalPages = 1;
  var searchQuery = '';
  var allClients = [];

  // ----------------------------------------
  // Helpers
  // ----------------------------------------
  function byId(id) {
    return document.getElementById(id);
  }

  function setValue(id, value) {
    var el = byId(id);
    if (el) el.value = value ?? "";
  }

  // ----------------------------------------
  // Loading indicator
  // ----------------------------------------
  function showLoading(container) {
    container.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:40px;"><div style="display:inline-block;width:30px;height:30px;border:3px solid #e0e0e0;border-top-color:#667eea;border-radius:50%;animation:spin 0.8s linear infinite;"></div><p style="margin-top:10px;color:#666;">Loading...</p></td></tr>';
  }

  // ----------------------------------------
  // Search & Filter
  // ----------------------------------------
  function filterClients(data, query) {
    if (!query) return data;
    query = query.toLowerCase();
    return data.filter(function(r) {
      var name = (r["Client Name"] || "").toLowerCase();
      var company = (r["Company"] || "").toLowerCase();
      var phone = (r["Phone"] || "").toLowerCase();
      var code = String(r["Client Code"] || "").toLowerCase();
      return name.indexOf(query) !== -1 ||
             company.indexOf(query) !== -1 ||
             phone.indexOf(query) !== -1 ||
             code.indexOf(query) !== -1;
    });
  }

  function renderClientList(data, list, page) {
    var perPage = 10;
    var filtered = filterClients(data, searchQuery);
    totalPages = Math.ceil(filtered.length / perPage) || 1;
    currentPage = Math.min(page, totalPages);

    var start = (currentPage - 1) * perPage;
    var pageData = filtered.slice(start, start + perPage);

    list.innerHTML = "";

    if (pageData.length === 0) {
      list.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:30px;color:#666;">No clients found</td></tr>';
      return;
    }

    pageData.forEach(function(r) {
      var tr = document.createElement("tr");
      tr.innerHTML =
        '<td>' + (r["Client Code"] || "") + '</td>' +
        '<td>' + (r["Client Name"] || "") + '</td>' +
        '<td>' + (r["Company"] || "") + '</td>' +
        '<td>' + (r["Phone"] || "") + '</td>';
      tr.style.cursor = "pointer";
      tr.ondblclick = function() {
        window.loadClientFromOverlay(r);
        hideOverlay();
      };
      list.appendChild(tr);
    });

    updatePagination();
  }

  function updatePagination() {
    var pagination = byId("clientPagination");
    if (!pagination) return;

    pagination.innerHTML =
      '<button ' + (currentPage <= 1 ? 'disabled' : '') + ' onclick="window.clientPrevPage()">Prev</button>' +
      '<span style="padding:0 15px;">Page ' + currentPage + ' of ' + totalPages + '</span>' +
      '<button ' + (currentPage >= totalPages ? 'disabled' : '') + ' onclick="window.clientNextPage()">Next</button>';
  }

  window.clientPrevPage = function() {
    if (currentPage > 1) {
      renderClientList(allClients, byId("clientList"), currentPage - 1);
    }
  };

  window.clientNextPage = function() {
    if (currentPage < totalPages) {
      renderClientList(allClients, byId("clientList"), currentPage + 1);
    }
  };

  window.searchClientsOverlay = function(query) {
    searchQuery = query;
    renderClientList(allClients, byId("clientList"), 1);
  };

  // ----------------------------------------
  // Overlay control
  // ----------------------------------------
  function hideOverlay() {
    var overlay = byId("clientOverlay");
    if (overlay) overlay.style.display = "none";
  }

  // ----------------------------------------
  // Auto client code (name + phone)
  // ----------------------------------------
  function initClientAutoCode() {
    var nameInput = byId("Client Name");
    var phoneInput = byId("Phone");
    var codeInput = byId("client_code");

    if (!nameInput || !phoneInput || !codeInput) {
      setTimeout(initClientAutoCode, 100);
      return;
    }

    async function tryGetClientCode() {
      if (!nameInput.value || !phoneInput.value) return;
      if (codeInput.value) return;

      try {
        var code = await window.getClientCodeFromServer?.(
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
      var overlay = byId("clientOverlay");
      var closeBtn = byId("btnCloseClientOverlay");
      var list = byId("clientList");
      var openBtn = byId("btn_search_client");
      var searchInput = byId("clientSearchInput");

      if (!overlay || !list || !openBtn) {
        setTimeout(tryInit, 100);
        return;
      }

      // Add search input if not exists
      if (!searchInput) {
        var header = overlay.querySelector(".overlay-header") || overlay.querySelector("h3")?.parentNode;
        if (header) {
          var searchDiv = document.createElement("div");
          searchDiv.style.cssText = "margin:15px 0;";
          searchDiv.innerHTML = '<input type="text" id="clientSearchInput" placeholder="Search clients..." style="width:100%;padding:10px 15px;border:2px solid #e0e0e0;border-radius:8px;font-size:14px;">';
          header.appendChild(searchDiv);

          // Add pagination container
          var paginationDiv = document.createElement("div");
          paginationDiv.id = "clientPagination";
          paginationDiv.style.cssText = "text-align:center;padding:15px;border-top:1px solid #eee;";
          overlay.querySelector(".overlay-content")?.appendChild(paginationDiv) ||
            overlay.appendChild(paginationDiv);
        }
      }

      // Search input event
      var newSearchInput = byId("clientSearchInput");
      if (newSearchInput) {
        newSearchInput.oninput = function() {
          window.searchClientsOverlay(this.value);
        };
      }

      function show() {
        overlay.style.display = "flex";
      }

      if (closeBtn) closeBtn.onclick = hideOverlay;

      openBtn.onclick = async function() {
        show();
        showLoading(list);
        searchQuery = '';
        if (newSearchInput) newSearchInput.value = '';

        try {
          var result = await window.getClientsForOverlay?.();

          if (!result || (result.data && result.data.length === 0) || (Array.isArray(result) && result.length === 0)) {
            list.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:30px;color:#666;">No clients found</td></tr>';
            return;
          }

          // Handle both old format (array) and new format (object with data)
          allClients = result.data || result;

          // Sort by Client Code ascending
          allClients.sort(function(a, b) {
            var codeA = parseInt(a["Client Code"]) || 0;
            var codeB = parseInt(b["Client Code"]) || 0;
            return codeA - codeB;
          });

          renderClientList(allClients, list, 1);
        } catch (e) {
          console.error("Error loading clients:", e);
          list.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:30px;color:#c62828;">Error loading clients</td></tr>';
        }
      };
    }

    tryInit();
  })();

})();

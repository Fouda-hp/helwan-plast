// ========================================
// clients.js - WITH SEARCH, PAGINATION & LOADING
// ========================================
if (typeof window.debugError !== 'function') window.debugError = function () {};

(function () {
  if (window.__clientsLoaded) return;
  window.__clientsLoaded = true;

  // Pagination state
  var currentPage = 1;
  var totalPages = 1;
  var searchQuery = '';
  var allClients = [];
  var ROWS_PER_PAGE = 10;

  // ----------------------------------------
  // Helpers
  // ----------------------------------------
  function byId(id) {
    return document.getElementById(id);
  }

  // Use shared debounce from utils.js
  var debounce = window.debounce || function(fn, delay) {
    var timer;
    return function() { var c=this,a=arguments; clearTimeout(timer); timer=setTimeout(function(){fn.apply(c,a);},delay||300); };
  };

  function setValue(id, value) {
    var el = byId(id);
    if (el) el.value = value ?? "";
  }

  // ----------------------------------------
  // Loading indicator (Skeleton Loading)
  // ----------------------------------------
  function showLoading(container) {
    var skeletonRows = '';
    for (var i = 0; i < 5; i++) {
      skeletonRows += `
        <tr class="skeleton-row">
          <td style="padding:12px 15px;border-bottom:1px solid #eee;">
            <div class="skeleton-box" style="width:60px;height:18px;background:linear-gradient(90deg,#f0f0f0 25%,#e0e0e0 50%,#f0f0f0 75%);background-size:200% 100%;animation:skeleton-shimmer 1.5s infinite;border-radius:4px;"></div>
          </td>
          <td style="padding:12px 15px;border-bottom:1px solid #eee;">
            <div class="skeleton-box" style="width:150px;height:18px;background:linear-gradient(90deg,#f0f0f0 25%,#e0e0e0 50%,#f0f0f0 75%);background-size:200% 100%;animation:skeleton-shimmer 1.5s infinite;border-radius:4px;"></div>
          </td>
        </tr>`;
    }
    container.innerHTML = skeletonRows;

    // Add skeleton animation keyframes if not exists
    if (!document.getElementById('skeleton-styles')) {
      var style = document.createElement('style');
      style.id = 'skeleton-styles';
      style.textContent = '@keyframes skeleton-shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}';
      document.head.appendChild(style);
    }
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
      var email = (r["Email"] || "").toLowerCase();
      return name.indexOf(query) !== -1 ||
             company.indexOf(query) !== -1 ||
             phone.indexOf(query) !== -1 ||
             code.indexOf(query) !== -1 ||
             email.indexOf(query) !== -1;
    });
  }

  function renderClientList(data, list, page) {
    var filtered = filterClients(data, searchQuery);
    totalPages = Math.ceil(filtered.length / ROWS_PER_PAGE) || 1;
    currentPage = Math.min(page, totalPages);

    var start = (currentPage - 1) * ROWS_PER_PAGE;
    var pageData = filtered.slice(start, start + ROWS_PER_PAGE);

    list.innerHTML = "";

    if (pageData.length === 0) {
      list.innerHTML = '<tr><td colspan="2" style="text-align:center;padding:30px;color:#666;">No clients found</td></tr>';
      updatePagination();
      return;
    }

    pageData.forEach(function(r) {
      var tr = document.createElement("tr");
      tr.innerHTML =
        '<td style="padding:12px 15px;border-bottom:1px solid #eee;">' + (r["Client Code"] || "") + '</td>' +
        '<td style="padding:12px 15px;border-bottom:1px solid #eee;">' + (r["Client Name"] || "") + '</td>';
      tr.style.cursor = "pointer";
      tr.style.transition = "background 0.2s";
      tr.onmouseover = function() { this.style.background = "#f5f5f5"; };
      tr.onmouseout = function() { this.style.background = ""; };
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

    var prevDisabled = currentPage <= 1 ? 'disabled style="opacity:0.5;cursor:not-allowed;"' : '';
    var nextDisabled = currentPage >= totalPages ? 'disabled style="opacity:0.5;cursor:not-allowed;"' : '';

    pagination.innerHTML =
      '<button ' + prevDisabled + ' onclick="window.clientPrevPage()" style="padding:8px 20px;background:#4a90d9;color:#fff;border:none;border-radius:5px;cursor:pointer;margin-right:10px;">◀ Prev</button>' +
      '<span style="font-size:14px;color:#666;">Page ' + currentPage + ' of ' + totalPages + '</span>' +
      '<button ' + nextDisabled + ' onclick="window.clientNextPage()" style="padding:8px 20px;background:#4a90d9;color:#fff;border:none;border-radius:5px;cursor:pointer;margin-left:10px;">Next ▶</button>';
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
        window.debugError("Client code error:", e);
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
    // Use special function for sales_rep dropdown\n    if (window.setSalesRepValue) {\n      window.setSalesRepValue(record["Sales Rep"]);\n    } else {\n      setValue("sales_rep", record["Sales Rep"]);\n    }
    setValue("Source", record["Source"]);
  };

  // ----------------------------------------
  // Rebuild overlay structure
  // ----------------------------------------
  function rebuildOverlay(overlay) {
    var qoBody = overlay.querySelector(".qo-body");
    if (!qoBody) return;

    // Clear existing content and rebuild
    qoBody.innerHTML = '';

    // Search container - centered at top
    var searchContainer = document.createElement("div");
    searchContainer.className = "search-wrapper";

    searchContainer.innerHTML = `
  <div class="search-box">
    <span class="search-icon">🔍</span>
    <input 
      type="text" 
      id="clientSearchInput" 
      placeholder="Search by client name"
    >
  </div>
`;

    qoBody.appendChild(searchContainer);


    // Table container - NO scroll
    var tableContainer = document.createElement("div");
    tableContainer.style.cssText = "width:100%;";
    tableContainer.innerHTML = `
      <table class="qo-table" style="width:100%;border-collapse:collapse;">
        <thead>
          <tr style="background:#4a90d9;color:#fff;">
            <th style="padding:12px 15px;text-align:left;">Client Code</th>
            <th style="padding:12px 15px;text-align:left;">Client Name</th>
          </tr>
        </thead>
        <tbody id="clientList"></tbody>
      </table>
    `;
    qoBody.appendChild(tableContainer);

    // Pagination container - centered at bottom
    var paginationContainer = document.createElement("div");
    paginationContainer.id = "clientPagination";
    paginationContainer.style.cssText = "text-align:center;padding:20px 0;margin-top:15px;border-top:1px solid #eee;";
    qoBody.appendChild(paginationContainer);

    // Style the modal for better appearance
    var modal = overlay.querySelector(".qo-modal");
    if (modal) {
      modal.style.cssText = "background:#fff;border-radius:15px;width:90%;max-width:600px;max-height:90vh;display:flex;flex-direction:column;box-shadow:0 25px 50px rgba(0,0,0,0.3);";
    }

    var header = overlay.querySelector(".qo-header");
    if (header) {
      header.style.cssText = "padding:20px 25px;background:linear-gradient(135deg,#4a90d9,#667eea);color:#fff;border-radius:15px 15px 0 0;display:flex;justify-content:space-between;align-items:center;";
    }

    qoBody.style.cssText = "padding:25px;flex:1;overflow:hidden;";
  }

  // ----------------------------------------
  // Client search overlay
  // ----------------------------------------
  (function initClientOverlay() {

    function tryInit() {
      var overlay = byId("clientOverlay");
      var closeBtn = byId("btnCloseClientOverlay");
      var openBtn = byId("btn_search_client");

      if (!overlay || !openBtn) {
        setTimeout(tryInit, 100);
        return;
      }

      // Rebuild overlay structure
      rebuildOverlay(overlay);

      var list = byId("clientList");
      var searchInput = byId("clientSearchInput");

      // Search input event with debounce (300ms delay)
      if (searchInput) {
        var debouncedSearch = debounce(function(value) {
          window.searchClientsOverlay(value);
        }, 300);

        searchInput.oninput = function() {
          debouncedSearch(this.value);
        };
        searchInput.onfocus = function() {
          this.style.borderColor = "#667eea";
        };
        searchInput.onblur = function() {
          this.style.borderColor = "#4a90d9";
        };
      }

      function show() {
        overlay.style.display = "flex";
      }

      if (closeBtn) closeBtn.onclick = hideOverlay;

      // Close on backdrop click
      overlay.onclick = function(e) {
        if (e.target === overlay || e.target.classList.contains("qo-backdrop")) {
          hideOverlay();
        }
      };

      openBtn.onclick = async function() {
        show();
        if (list) showLoading(list);
        searchQuery = '';
        if (searchInput) searchInput.value = '';

        try {
          var result = await window.getClientsForOverlay?.();
          if (!result) {
            if (list) list.innerHTML = '<tr><td colspan="2" style="text-align:center;padding:30px;color:#c62828;">Error loading clients</td></tr>';
            return;
          }
          if (result.success === false && result.message) {
            if (list) list.innerHTML = '<tr><td colspan="2" style="text-align:center;padding:30px;color:#c62828;">' + (result.message || 'Error loading clients') + '</td></tr>';
            return;
          }

          // Handle both old format (array) and new format (object with data)
          allClients = result.data || result;
          if (!Array.isArray(allClients)) {
            if (list) list.innerHTML = '<tr><td colspan="2" style="text-align:center;padding:30px;color:#666;">No clients found</td></tr>';
            return;
          }
          if (allClients.length === 0) {
            if (list) list.innerHTML = '<tr><td colspan="2" style="text-align:center;padding:30px;color:#666;">No clients found</td></tr>';
            return;
          }

          // Sort by Client Code ascending
          allClients.sort(function(a, b) {
            var codeA = parseInt(a["Client Code"]) || 0;
            var codeB = parseInt(b["Client Code"]) || 0;
            return codeA - codeB;
          });

          if (list) renderClientList(allClients, list, 1);
        } catch (e) {
          window.debugError("Error loading clients:", e);
          if (list) list.innerHTML = '<tr><td colspan="2" style="text-align:center;padding:30px;color:#c62828;">Error loading clients</td></tr>';
        }
      };
    }

    tryInit();
  })();

})();

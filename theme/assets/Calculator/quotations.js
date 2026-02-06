// ========================================
// quotations.js - WITH SEARCH, PAGINATION & LOADING
// ========================================

(function () {
  if (window.__quotationsLoaded) return;
  window.__quotationsLoaded = true;

  window.loadQuotationFromOverlay = window.loadQuotationFromOverlay || null;
  window.LOADING_FROM_QUOTATION = false;
  window.QUOTATION_LOCKED = false;

  // Pagination state
  var currentPage = 1;
  var totalPages = 1;
  var searchQuery = '';
  var allQuotations = [];
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

  function getField(record, names) {
    for (var i = 0; i < names.length; i++) {
      if (record[names[i]] !== undefined && record[names[i]] !== null) {
        return record[names[i]];
      }
    }
    return "";
  }

  function getCylinderValue(record, base, i) {
    var keys = [
      base + i,
      base + " " + i,
      base + "_" + i,
      base + "-" + i,
      base + " (" + i + ")"
    ];
    for (var j = 0; j < keys.length; j++) {
      var v = record[keys[j]];
      if (v !== undefined && v !== null && v !== "") {
        return v;
      }
    }
    return "";
  }

  function setValue(id, value) {
    var el = byId(id);
    if (el) el.value = value ?? "";
  }

  function setCheckbox(id, value) {
    var el = byId(id);
    if (!el) return;
    var v = String(value || "").trim().toUpperCase();
    el.checked = (v === "YES" || v === "TRUE");
  }

  function setSelect(id, value) {
    if (!value) return;
    if (window.updateCustomSelect) {
      window.updateCustomSelect(id, value);
    } else {
      var el = byId(id);
      if (el) el.value = value;
    }
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
          <td style="padding:12px 15px;border-bottom:1px solid #eee;">
            <div class="skeleton-box" style="width:80px;height:18px;background:linear-gradient(90deg,#f0f0f0 25%,#e0e0e0 50%,#f0f0f0 75%);background-size:200% 100%;animation:skeleton-shimmer 1.5s infinite;border-radius:4px;"></div>
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
  function filterQuotations(data, query) {
    if (!query) return data;
    query = query.toLowerCase();
    return data.filter(function(r) {
      var name = (r["Client Name"] || r["client_name"] || "").toLowerCase();
      var company = (r["Company"] || "").toLowerCase();
      var qNum = String(r["Quotation#"] || "").toLowerCase();
      var model = (r["Model"] || "").toLowerCase();
      var clientCode = String(r["Client Code"] || r["client_code"] || "").toLowerCase();
      return name.indexOf(query) !== -1 ||
             company.indexOf(query) !== -1 ||
             qNum.indexOf(query) !== -1 ||
             model.indexOf(query) !== -1 ||
             clientCode.indexOf(query) !== -1;
    });
  }

  function renderQuotationList(data, list, page) {
    var filtered = filterQuotations(data, searchQuery);
    totalPages = Math.ceil(filtered.length / ROWS_PER_PAGE) || 1;
    currentPage = Math.min(page, totalPages);

    var start = (currentPage - 1) * ROWS_PER_PAGE;
    var pageData = filtered.slice(start, start + ROWS_PER_PAGE);

    list.innerHTML = "";

    if (pageData.length === 0) {
      list.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:30px;color:#666;">No quotations found</td></tr>';
      updatePagination();
      return;
    }

    pageData.forEach(function(r) {
      var tr = document.createElement("tr");
      var clientName = r["Client Name"] || r["client_name"] || "";
      tr.innerHTML =
        '<td style="padding:12px 15px;border-bottom:1px solid #eee;">' + (r["Quotation#"] || "") + '</td>' +
        '<td style="padding:12px 15px;border-bottom:1px solid #eee;">' + clientName + '</td>' +
        '<td style="padding:12px 15px;border-bottom:1px solid #eee;">' + (r["Date"] || "") + '</td>';
      tr.style.cursor = "pointer";
      tr.style.transition = "background 0.2s";
      tr.onmouseover = function() { this.style.background = "#f5f5f5"; };
      tr.onmouseout = function() { this.style.background = ""; };
      tr.ondblclick = function() {
        window.loadQuotationFromOverlay(r);
        hideOverlay();
      };
      list.appendChild(tr);
    });

    updatePagination();
  }

  function updatePagination() {
    var pagination = byId("quotationPagination");
    if (!pagination) return;

    var prevDisabled = currentPage <= 1 ? 'disabled style="opacity:0.5;cursor:not-allowed;"' : '';
    var nextDisabled = currentPage >= totalPages ? 'disabled style="opacity:0.5;cursor:not-allowed;"' : '';

    pagination.innerHTML = `
  <button ${prevDisabled} class="qo-page-btn" onclick="window.quotationPrevPage()">◀ Prev</button>
  <span class="qo-page-info">Page ${currentPage} of ${totalPages}</span>
  <button ${nextDisabled} class="qo-page-btn" onclick="window.quotationNextPage()">Next ▶</button>
`;
}    


  window.quotationPrevPage = function() {
    if (currentPage > 1) {
      renderQuotationList(allQuotations, byId("quotationList"), currentPage - 1);
    }
  };

  window.quotationNextPage = function() {
    if (currentPage < totalPages) {
      renderQuotationList(allQuotations, byId("quotationList"), currentPage + 1);
    }
  };

  window.searchQuotationsOverlay = function(query) {
    searchQuery = query;
    renderQuotationList(allQuotations, byId("quotationList"), 1);
  };

  // ----------------------------------------
  // Load quotation into form
  // ----------------------------------------
  window.loadQuotationFromOverlay = function (record) {
    if (!record) return;
    // #region agent log
    fetch('http://127.0.0.1:7242/ingest/8b3fb622-0491-4420-8d50-0b29370f6f0d',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'quotations.js:loadQuotationFromOverlay',message:'load quotation',data:{quotationNum:record["Quotation#"]||record["quotation_number"],clientCode:record["Client Code"]||record["client_code"]},timestamp:Date.now(),sessionId:'debug-session',hypothesisId:'H4'})}).catch(function(){});
    // #endregion
    window.LOADING_FROM_QUOTATION = true;
    window.cylindersInitialized = false;

    // Client data
    setValue("client_code", record["Client Code"]);
    setValue("Quotation#", record["Quotation#"]);
    setValue("Date", record["Date"]);
    setValue("Client Name", record["Client Name"]);
    setValue("Company", record["Company"]);
    setValue("Phone", record["Phone"]);
    setValue("Country", record["Country"]);
    setValue("Address", record["Address"]);
    setValue("Email", record["Email"]);
    // Use special function for sales_rep dropdown\n    if (window.setSalesRepValue) {\n      window.setSalesRepValue(record["Sales Rep"]);\n    } else {\n      setValue("sales_rep", record["Sales Rep"]);\n    }
    setValue("Source", record["Source"]);
    setValue("Given Price", record["Given Price"]);
    setValue("Agreed Price", record["Agreed Price"]);
    setValue("Notes", record["Notes"]);

    // Machine selects
    var machineTypeValue =
      record["machine type"] ??
      record["Machine type"] ??
      record["machine_type"] ??
      "";

    setSelect("machine_type", window.mapMachineType?.(machineTypeValue) || machineTypeValue);
    setSelect("Number of colors", record["Number of colors"]);
    setSelect("Machine width", record["Machine width"]);
    setSelect("Material", record["Material"]);
    setSelect("Winder", window.mapWinder?.(record["Winder"]) || record["Winder"]);

    // Options
    [
      "Video inspection",
      "PLC",
      "Slitter",
      "Pneumatic Unwind",
      "Hydraulic Station Unwind",
      "Pneumatic Rewind",
      "Surface Rewind"
    ].forEach(function(id) { setCheckbox(id, record[id]); });

    // Clear cylinders first
    for (var i = 1; i <= 12; i++) {
      setValue("Size in CM" + i, "");
      setValue("Count" + i, "");
    }

    // Fill cylinders (delayed)
    setTimeout(function() {
      for (var i = 1; i <= 12; i++) {
        var size = getCylinderValue(record, "Size in CM", i);
        var count = getCylinderValue(record, "Count", i);
        if (size) setValue("Size in CM" + i, size);
        if (count) setValue("Count" + i, count);
      }

      window.cylindersInitialized = true;
      window.LOADING_FROM_QUOTATION = false;

      window.buildModelCode?.();
      window.calculateAll?.();
    }, 300);
  };

  // ----------------------------------------
  // Overlay control
  // ----------------------------------------
  function hideOverlay() {
    var overlay = byId("quotationOverlay");
    if (overlay) overlay.style.display = "none";
  }

  // ----------------------------------------
  // Rebuild overlay structure
  // ----------------------------------------
    function rebuildOverlay(overlay) {
      var qoBody = overlay.querySelector(".qo-body");
      if (!qoBody) return;

      qoBody.innerHTML = '';

      /* ================= SEARCH ================= */
      var searchContainer = document.createElement("div");
      searchContainer.style.cssText = `
    display:flex;
    justify-content:center;
    margin:15px 0 25px;
  `;

      searchContainer.innerHTML = `
    <div class="qo-search-box">
      <span class="search-icon">🔍</span>
      <input type="text" id="quotationSearchInput" placeholder="Search here">
    </div>
  `;

      qoBody.appendChild(searchContainer);

      /* ================= TABLE ================= */
      var tableWrapper = document.createElement("div");
      tableWrapper.className = "qo-table-wrapper";

      tableWrapper.innerHTML = `
  <table class="qo-table">
    <thead>
      <tr>
        <th>Quotation #</th>
        <th>Client Name</th>
        <th>Date</th>
      </tr>
    </thead>
    <tbody id="quotationList"></tbody>
  </table>
`;

      qoBody.appendChild(tableWrapper);


      /* ================= PAGINATION ================= */
      var paginationContainer = document.createElement("div");
      paginationContainer.id = "quotationPagination";
      paginationContainer.style.cssText = `
    display:flex;
    justify-content:center;
    align-items:center;
    gap:20px;
    padding:18px 0;
    margin-top:20px;
    border-top:1px solid #eee;
  `;
      qoBody.appendChild(paginationContainer);

      /* ================= MODAL STYLE ================= */
      var modal = overlay.querySelector(".qo-modal");
      if (modal) {
        modal.style.cssText = `
      background:#fff;
      border-radius:15px;
      width:90%;
      max-width:700px;
      max-height:90vh;
      display:flex;
      flex-direction:column;
      box-shadow:0 25px 50px rgba(0,0,0,0.3);
    `;
      }

      var header = overlay.querySelector(".qo-header");
      if (header) {
        header.style.cssText = `
      padding:20px 25px;
      background:linear-gradient(135deg,#4a90d9,#667eea);
      color:#fff;
      border-radius:15px 15px 0 0;
      display:flex;
      justify-content:space-between;
      align-items:center;
    `;
      }

      qoBody.style.cssText = "padding:25px;flex:1;overflow:hidden;";
    }

  // ----------------------------------------
  // Quotation overlay (search)
  // ----------------------------------------
  (function initQuotationOverlay() {

    function tryInit() {
      var overlay = byId("quotationOverlay");
      var closeBtn = byId("btnCloseOverlay");
      var openBtn = byId("btn_search_quotation");

      if (!overlay || !openBtn) {
        setTimeout(tryInit, 100);
        return;
      }

      // Rebuild overlay structure
      rebuildOverlay(overlay);

      var list = byId("quotationList");
      var searchInput = byId("quotationSearchInput");

      // Search input event with debounce (300ms delay)
      if (searchInput) {
        var debouncedSearch = debounce(function(value) {
          window.searchQuotationsOverlay(value);
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

        // #region agent log
        fetch('http://127.0.0.1:7242/ingest/8b3fb622-0491-4420-8d50-0b29370f6f0d',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'quotations.js:getQuotationsForOverlay',message:'calling getQuotationsForOverlay',data:{},timestamp:Date.now(),sessionId:'debug-session',hypothesisId:'H1'})}).catch(function(){});
        // #endregion
        try {
          var result = await window.getQuotationsForOverlay?.();

          // #region agent log
          fetch('http://127.0.0.1:7242/ingest/8b3fb622-0491-4420-8d50-0b29370f6f0d',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'quotations.js:getQuotationsForOverlay',message:'result received',data:{hasData:!!result,dataLen:(result&&result.data)?result.data.length:(Array.isArray(result)?result.length:0)},timestamp:Date.now(),sessionId:'debug-session',hypothesisId:'H1'})}).catch(function(){});
          // #endregion
          if (!result || (result.data && result.data.length === 0) || (Array.isArray(result) && result.length === 0)) {
            if (list) list.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:30px;color:#666;">No quotations found</td></tr>';
            return;
          }

          allQuotations = result.data || result;

          // Sort by Quotation# ascending
          allQuotations.sort(function(a, b) {
            var numA = parseInt(a["Quotation#"]) || 0;
            var numB = parseInt(b["Quotation#"]) || 0;
            return numA - numB;
          });

          if (list) renderQuotationList(allQuotations, list, 1);
        } catch (e) {
          window.debugError("Error loading quotations:", e);
          if (list) list.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:30px;color:#c62828;">Error loading quotations</td></tr>';
        }
      };
    }

    tryInit();
  })();

})();


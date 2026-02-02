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

  // ----------------------------------------
  // Helpers
  // ----------------------------------------
  function byId(id) {
    return document.getElementById(id);
  }

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
  // Loading indicator
  // ----------------------------------------
  function showLoading(container) {
    container.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:40px;"><div style="display:inline-block;width:30px;height:30px;border:3px solid #e0e0e0;border-top-color:#667eea;border-radius:50%;animation:spin 0.8s linear infinite;"></div><p style="margin-top:10px;color:#666;">Loading...</p></td></tr>';
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
    var perPage = 10;
    var filtered = filterQuotations(data, searchQuery);
    totalPages = Math.ceil(filtered.length / perPage) || 1;
    currentPage = Math.min(page, totalPages);

    var start = (currentPage - 1) * perPage;
    var pageData = filtered.slice(start, start + perPage);

    list.innerHTML = "";

    if (pageData.length === 0) {
      list.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:30px;color:#666;">No quotations found</td></tr>';
      return;
    }

    pageData.forEach(function(r) {
      var tr = document.createElement("tr");
      // Get client name from multiple possible fields
      var clientName = r["Client Name"] || r["client_name"] || "";
      // Hide Client Code, show only Quotation#, Client Name, Date
      tr.innerHTML =
        '<td>' + (r["Quotation#"] || "") + '</td>' +
        '<td>' + clientName + '</td>' +
        '<td>' + (r["Date"] || "") + '</td>';
      tr.style.cursor = "pointer";
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

    pagination.innerHTML =
      '<button ' + (currentPage <= 1 ? 'disabled' : '') + ' onclick="window.quotationPrevPage()">Prev</button>' +
      '<span style="padding:0 15px;">Page ' + currentPage + ' of ' + totalPages + '</span>' +
      '<button ' + (currentPage >= totalPages ? 'disabled' : '') + ' onclick="window.quotationNextPage()">Next</button>';
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
    setValue("sales_rep", record["Sales Rep"]);
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
  // Quotation overlay (search)
  // ----------------------------------------
  (function initQuotationOverlay() {

    function tryInit() {
      var overlay = byId("quotationOverlay");
      var closeBtn = byId("btnCloseOverlay");
      var list = byId("quotationList");
      var openBtn = byId("btn_search_quotation");
      var searchInput = byId("quotationSearchInput");

      if (!overlay || !list || !openBtn) {
        setTimeout(tryInit, 100);
        return;
      }

      // Add search input and pagination if not exists
      if (!searchInput) {
        var qoBody = overlay.querySelector(".qo-body");
        if (qoBody) {
          // Create search div at top
          var searchDiv = document.createElement("div");
          searchDiv.style.cssText = "margin-bottom:15px;width:100%;";
          searchDiv.innerHTML = '<input type="text" id="quotationSearchInput" placeholder="Search by client name..." style="width:100%;padding:10px 15px;border:2px solid #e0e0e0;border-radius:8px;font-size:14px;">';
          qoBody.insertBefore(searchDiv, qoBody.firstChild);

          // Create scrollable table container
          var tableWrapper = document.createElement("div");
          tableWrapper.style.cssText = "max-height:45vh;overflow-y:auto;width:100%;";
          var table = qoBody.querySelector(".qo-table");
          if (table) {
            tableWrapper.appendChild(table);
            qoBody.appendChild(tableWrapper);
          }

          // Update table header to hide Client Code
          var thead = table?.querySelector("thead tr");
          if (thead) {
            thead.innerHTML = '<th>Quotation #</th><th>Client Name</th><th>Date</th>';
          }

          // Add pagination container at bottom
          var paginationDiv = document.createElement("div");
          paginationDiv.id = "quotationPagination";
          paginationDiv.style.cssText = "text-align:center;padding:15px;border-top:1px solid #eee;margin-top:10px;";
          qoBody.appendChild(paginationDiv);
        }
      }

      // Search input event
      var newSearchInput = byId("quotationSearchInput");
      if (newSearchInput) {
        newSearchInput.oninput = function() {
          window.searchQuotationsOverlay(this.value);
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
        var searchInp = byId("quotationSearchInput");
        if (searchInp) searchInp.value = '';

        try {
          var result = await window.getQuotationsForOverlay?.();

          if (!result || (result.data && result.data.length === 0) || (Array.isArray(result) && result.length === 0)) {
            list.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:30px;color:#666;">No quotations found</td></tr>';
            return;
          }

          // Handle both old format (array) and new format (object with data)
          allQuotations = result.data || result;

          // Sort by Quotation# ascending
          allQuotations.sort(function(a, b) {
            var numA = parseInt(a["Quotation#"]) || 0;
            var numB = parseInt(b["Quotation#"]) || 0;
            return numA - numB;
          });

          renderQuotationList(allQuotations, list, 1);
        } catch (e) {
          console.error("Error loading quotations:", e);
          list.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:30px;color:#c62828;">Error loading quotations</td></tr>';
        }
      };
    }

    tryInit();
  })();

})();

// ========================================
// machine_pricing.js - محدث مع تحميل الإعدادات من السيرفر
// ========================================
if (typeof window.debugLog !== 'function') window.debugLog = function () {};

(function () {
  if (window.__machinePricingLoaded) return;
  window.__machinePricingLoaded = true;

  // ----------------------------------------
  // الإعدادات - يتم تحميلها من السيرفر
  // القيم الافتراضية تُستخدم إذا فشل التحميل
  // ----------------------------------------
  let EXCHANGE_RATE = 47.5;  // قيمة افتراضية
  let CONFIG = {
    SHIPPING_SEA: 3200,
    THS: 1000,
    EXPENSES_CLEARANCE: 1400,
    TAX_RATE: 0.15,
    BANK_COMMISSION: 0.0132
  };

  // تحميل الإعدادات من السيرفر — استدعاء واحد بدل 6 (أخف على الشبكة)
  var _settingsLoading = false; // Race condition guard
  async function loadSettingsFromServer() {
    if (_settingsLoading) return; // منع التحميل المتكرر
    _settingsLoading = true;
    try {
      var auth = (typeof sessionStorage !== 'undefined' && (sessionStorage.getItem('auth_token') || sessionStorage.getItem('user_email'))) || null;
      const data = await window.anvil?.server?.call('get_calculator_settings', auth);
      if (!data || data.success === false) return;
      if (data.exchangeRate != null && !isNaN(data.exchangeRate)) {
        EXCHANGE_RATE = parseFloat(data.exchangeRate);
        var exEl = document.getElementById("exchange_rate");
        if (exEl) exEl.value = EXCHANGE_RATE.toFixed(2);
      }
      if (data.shipping_sea != null && !isNaN(data.shipping_sea)) CONFIG.SHIPPING_SEA = parseFloat(data.shipping_sea);
      if (data.ths_cost != null && !isNaN(data.ths_cost)) CONFIG.THS = parseFloat(data.ths_cost);
      if (data.clearance_expenses != null && !isNaN(data.clearance_expenses)) CONFIG.EXPENSES_CLEARANCE = parseFloat(data.clearance_expenses);
      if (data.tax_rate != null && !isNaN(data.tax_rate)) CONFIG.TAX_RATE = parseFloat(data.tax_rate);
      if (data.bank_commission != null && !isNaN(data.bank_commission)) CONFIG.BANK_COMMISSION = parseFloat(data.bank_commission);
      if (data.config && data.config.types && data.config.types.length) updateMachineTypeDropdown(data.config.types);
      if (data.config && data.config.colors && data.config.colors.length) updateColorsDropdown(data.config.colors);
      if (data.config && data.config.widths && data.config.widths.length) updateWidthsDropdown(data.config.widths);
      if (typeof window.calculateAll === 'function') window.calculateAll();
      window._settingsLoaded = true;
    } catch (e) {
      window.debugWarn('Could not load settings from server, using defaults:', e);
    } finally {
      _settingsLoading = false;
    }
  }

  // تعريض الدالة لتحديث الإعدادات (سعر الصرف وغيره) عند فتح الكالكتور
  window.loadSettingsFromServer = loadSettingsFromServer;

  // تحميل الإعدادات عند بدء التشغيل - من السيرفر مباشرة
  window._settingsLoaded = false;
  loadSettingsFromServer();

  // ----------------------------------------
  // عناصر الواجهة
  // ----------------------------------------
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
  // دوال مساعدة
  // ----------------------------------------

  // استخدام halfUpRound الموحدة من utils.js مع fallback
  var halfUpRound = window.halfUpRound || function(v) { return Math.floor(v + 0.5); };

  function mapMachineType(v) {
    v = String(v || "").toLowerCase();
    if (v.includes("metal")) return "Metal anilox";
    // Handle both "Doctor" and "Doctore" (typo in old data)
    if (v.includes("single") && (v.includes("doctor") || v.includes("ceramic")))
      return "Ceramic anilox Single Doctor Blade";
    if (v.includes("chamber") && (v.includes("doctor") || v.includes("ceramic")))
      return "Ceramic anilox Chamber Doctor Blade";
    // Fallback for partial matches
    if (v.includes("single")) return "Ceramic anilox Single Doctor Blade";
    if (v.includes("chamber")) return "Ceramic anilox Chamber Doctor Blade";
    return "";
  }

  function mapWinder(v) {
    v = String(v || "").toLowerCase();
    // Handle "single winder", "single", etc.
    if (v.includes("single")) return "Single";
    // Handle "double winder", "double", etc.
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
  // أسعار الآلات - من السيرفر
  // ----------------------------------------

  let MACHINE_PRICES = {
    // Default prices (fallback)
    "Metal anilox": {"4": {"80": 15000, "100": 16000, "120": 17500}, "6": {"80": 25000, "100": 26000, "120": 29000}, "8": {"80": 29000, "100": 32000, "120": 33000}},
    "Ceramic anilox Single Doctor Blade": {"4": {"80": 18000, "100": 19000, "120": 20500}, "6": {"80": 28000, "100": 29000, "120": 32000}, "8": {"80": 32000, "100": 35000, "120": 36000}},
    "Ceramic anilox Chamber Doctor Blade": {"4": {"80": 21168, "100": 22960, "120": 25252}, "6": {"80": 32752, "100": 34940, "120": 39128}, "8": {"80": 38336, "100": 42920, "120": 45504}}
  };
  
  // خيارات الدروب داون من جدول الأسعار (فقط مقاسات سعرها > 0)
  var PRICE_OPTIONS = { types: [], typeColors: {}, typeColorWidths: {} };

  function refreshColorsAndWidthsFromOptions() {
    var t = (machineType && machineType.value) || '';
    var c = (colors && colors.value) || '';
    var opts = PRICE_OPTIONS;
    if (opts.typeColors[t] && opts.typeColors[t].length) {
      updateColorsDropdown(opts.typeColors[t]);
      if (opts.typeColors[t].indexOf(c) === -1) colors.value = opts.typeColors[t][0] || '';
      c = colors.value || opts.typeColors[t][0];
    }
    if (t && c && opts.typeColorWidths[t] && opts.typeColorWidths[t][c] && opts.typeColorWidths[t][c].length) {
      updateWidthsDropdown(opts.typeColorWidths[t][c]);
    }
  }

  // تطبيع المفاتيح لـ string حتى لا يفشل البحث عند إضافة مقاس جديد (مفتاح رقمي من السيرفر)
  function normalizePricesKeys(p) {
    if (!p || typeof p !== 'object') return p;
    var out = {};
    Object.keys(p).forEach(function(k) {
      var key = String(k);
      out[key] = p[k] != null && typeof p[k] === 'object' && !Array.isArray(p[k]) ? normalizePricesKeys(p[k]) : p[k];
    });
    return out;
  }

  // Load machine prices from server — المصدر الوحيد لـ Standard Machine FOB cost وخيارات الدروب داون
  var _pricesLoading = false; // Race condition guard
  async function loadMachinePricesFromServer() {
    if (_pricesLoading) return; // منع التحميل المتكرر
    _pricesLoading = true;
    try {
      var call = (window.anvil && window.anvil.server && window.anvil.server.call) || (window.top && window.top.anvil && window.top.anvil.server && window.top.anvil.server.call);
      if (!call) return;
      var result = await call('get_machine_prices');
      if (result && result.success && result.prices) {
        MACHINE_PRICES = normalizePricesKeys(result.prices);
        if (result.options && result.options.types && result.options.types.length > 0) {
          PRICE_OPTIONS = result.options;
          updateMachineTypeDropdown(PRICE_OPTIONS.types);
          refreshColorsAndWidthsFromOptions();
        }
        // recalc مرة واحدة فقط بدلاً من 3 مرات (إصلاح Race Condition)
        if (typeof window.calculateAll === 'function') window.calculateAll();
      }
    } catch(e) {
      window.debugWarn('Could not load machine prices from server, using defaults:', e);
    } finally {
      _pricesLoading = false;
    }
  }

  // احتياطي: إذا لم نجد options من الأسعار نحمّل الكونفيج القديم
  async function loadMachineConfigFromServer() {
    if (PRICE_OPTIONS.types && PRICE_OPTIONS.types.length > 0) return;
    try {
      const result = await window.anvil?.server?.call('get_machine_config');
      if (result && result.success && result.config) {
        var config = result.config;
        if (config.types && config.types.length > 0) updateMachineTypeDropdown(config.types);
        if (config.colors && config.colors.length > 0) updateColorsDropdown(config.colors);
        if (config.widths && config.widths.length > 0) updateWidthsDropdown(config.widths);
      }
    } catch(e) {
      window.debugWarn('Could not load machine config from server:', e);
    }
  }

  function updateMachineTypeDropdown(types) {
    const typeList = (types || []).map(function(t) { return String(t); });
    const select = document.getElementById('machine_type');
    if (select) {
      const currentValue = select.value;
      select.innerHTML = '<option value=""></option>';
      typeList.forEach(function(type) {
        const option = document.createElement('option');
        option.value = type;
        option.textContent = type;
        select.appendChild(option);
      });
      if (typeList.indexOf(currentValue) !== -1) select.value = currentValue;
    }
    const uiSelect = document.querySelector('.ui-select[data-target="machine_type"]');
    if (uiSelect) {
      const menu = uiSelect.querySelector('.ui-select-menu');
      if (menu) {
        menu.innerHTML = '';
        typeList.forEach(function(type) {
          const div = document.createElement('div');
          div.className = 'ui-option';
          div.setAttribute('data-value', type);
          div.textContent = type;
          menu.appendChild(div);
        });
        rebindUiSelectHandlers(uiSelect, 'machine_type');
      }
    }
  }

  function updateColorsDropdown(colors) {
    const colorList = (colors || []).map(function(c) { return String(c); });
    const select = document.getElementById('Number of colors');
    if (select) {
      const currentValue = select.value;
      select.innerHTML = '<option value=""></option>';
      colorList.forEach(function(color) {
        const option = document.createElement('option');
        option.value = color;
        option.textContent = color;
        select.appendChild(option);
      });
      if (colorList.indexOf(currentValue) !== -1) select.value = currentValue;
    }
    const uiSelect = document.querySelector('.ui-select[data-target="Number of colors"]');
    if (uiSelect) {
      const menu = uiSelect.querySelector('.ui-select-menu');
      if (menu) {
        menu.innerHTML = '';
        colorList.forEach(function(color) {
          const div = document.createElement('div');
          div.className = 'ui-option';
          div.setAttribute('data-value', color);
          div.textContent = color;
          menu.appendChild(div);
        });
        rebindUiSelectHandlers(uiSelect, 'Number of colors');
      }
    }
  }

  function updateWidthsDropdown(widths) {
    // Normalize to strings (السيرفر قد يرجع أرقاماً أو نصوصاً)
    const widthList = (widths || []).map(function(w) { return String(w); });
    const select = document.getElementById('Machine width');
    if (select) {
      const currentValue = String(select.value || '');
      select.innerHTML = '<option value=""></option>';
      widthList.forEach(function(w) {
        const option = document.createElement('option');
        option.value = w;
        option.textContent = w;
        select.appendChild(option);
      });
      if (widthList.indexOf(currentValue) !== -1) {
        select.value = currentValue;
      }
    }
    const uiSelect = document.querySelector('.ui-select[data-target="Machine width"]');
    if (uiSelect) {
      const menu = uiSelect.querySelector('.ui-select-menu');
      if (menu) {
        menu.innerHTML = '';
        widthList.forEach(function(w) {
          const div = document.createElement('div');
          div.className = 'ui-option';
          div.setAttribute('data-value', w);
          div.textContent = w;
          menu.appendChild(div);
        });
        rebindUiSelectHandlers(uiSelect, 'Machine width');
      }
    }
  }

  function rebindUiSelectHandlers(uiSelect, targetId) {
    const trigger = uiSelect.querySelector('.ui-select-trigger');
    const menu = uiSelect.querySelector('.ui-select-menu');
    const valueSpan = uiSelect.querySelector('.ui-select-value');
    const hiddenSelect = document.getElementById(targetId);
    
    // Toggle menu
    trigger.onclick = (e) => {
      e.stopPropagation();
      // Close other open selects
      document.querySelectorAll('.ui-select.open').forEach(s => {
        if (s !== uiSelect) s.classList.remove('open');
      });
      uiSelect.classList.toggle('open');
    };
    
    // Option selection
    menu.querySelectorAll('.ui-option').forEach(opt => {
      opt.onclick = () => {
        const value = opt.getAttribute('data-value');
        valueSpan.textContent = opt.textContent;
        if (hiddenSelect) {
          hiddenSelect.value = value;
          hiddenSelect.dispatchEvent(new Event('change'));
        }
        menu.querySelectorAll('.ui-option').forEach(o => o.classList.remove('selected'));
        opt.classList.add('selected');
        uiSelect.classList.remove('open');
      };
    });
  }

  // Close dropdowns on outside click
  document.addEventListener('click', () => {
    document.querySelectorAll('.ui-select.open').forEach(s => s.classList.remove('open'));
  });

  // عند تغيير النوع أو اللون: تحديث خيارات الألوان/المقاسات من جدول الأسعار (المقاس سعره 0 لا يظهر)
  if (machineType) machineType.addEventListener('change', refreshColorsAndWidthsFromOptions);
  if (colors) colors.addEventListener('change', refreshColorsAndWidthsFromOptions);

  // تعريض تحميل إعدادات المكن من السيرفر (أنواع الماكينة، الألوان، المقاسات) لاستدعائها عند فتح الكالكتور
  window.loadMachineConfigFromServer = loadMachineConfigFromServer;

  /**
   * تطبيق إعدادات جُلبت من بايثون (السيرفر) - الكالكتور يعتمد على هذا عندما لا تعمل استدعاءات السيرفر من JS
   * data: { exchangeRate, config: { types, colors, widths }, shipping_sea, ths_cost, clearance_expenses, tax_rate, bank_commission }
   */
  window.applyCalculatorSettingsFromPython = function(data) {
    if (!data) return;
    try {
      if (typeof data.exchangeRate !== 'undefined' && data.exchangeRate != null && !isNaN(parseFloat(data.exchangeRate))) {
        EXCHANGE_RATE = parseFloat(data.exchangeRate);
        var exEl = document.getElementById("exchange_rate");
        if (exEl) {
          exEl.value = EXCHANGE_RATE.toFixed(2);
          exEl.dispatchEvent(new Event('input', { bubbles: true }));
        }
      }
      if (data.shipping_sea != null && !isNaN(data.shipping_sea)) CONFIG.SHIPPING_SEA = parseFloat(data.shipping_sea);
      if (data.ths_cost != null && !isNaN(data.ths_cost)) CONFIG.THS = parseFloat(data.ths_cost);
      if (data.clearance_expenses != null && !isNaN(data.clearance_expenses)) CONFIG.EXPENSES_CLEARANCE = parseFloat(data.clearance_expenses);
      if (data.tax_rate != null && !isNaN(data.tax_rate)) CONFIG.TAX_RATE = parseFloat(data.tax_rate);
      if (data.bank_commission != null && !isNaN(data.bank_commission)) CONFIG.BANK_COMMISSION = parseFloat(data.bank_commission);
      var c = data.config;
      var opts = data.priceOptions;
      if (data.cylinderPrices && window.applyCylinderPricesMap) {
        window.applyCylinderPricesMap(data.cylinderPrices);
      }
      if (data.machinePrices && typeof data.machinePrices === 'object') {
        MACHINE_PRICES = normalizePricesKeys(data.machinePrices);
      }
      if (opts && opts.types && opts.types.length) {
        PRICE_OPTIONS = opts;
        updateMachineTypeDropdown(opts.types);
        refreshColorsAndWidthsFromOptions();
      } else if (c && c.types && c.types.length) {
        updateMachineTypeDropdown(c.types);
        if (c.colors && c.colors.length) updateColorsDropdown(c.colors);
        if (c.widths && c.widths.length) updateWidthsDropdown(c.widths);
      }
      if (typeof window.calculateAll === 'function') window.calculateAll();
      window._settingsLoaded = true;
    } catch (e) {
      window.debugWarn('applyCalculatorSettingsFromPython error:', e);
    }
  };

  // عند التحميل: تطبيق إعدادات بايثون إن وُجدت (من النافذة الحالية أو top)
  function tryApplyStoredSettings() {
    var stored = window.__calculatorSettingsFromPython || (window.top && window.top !== window && window.top.__calculatorSettingsFromPython);
    if (!stored) return;
    try {
      var d = typeof stored === 'string' ? JSON.parse(stored) : stored;
      window.applyCalculatorSettingsFromPython(d);
    } catch (e) {}
  }
  // محاولة تطبيق الإعدادات مع حد أقصى للمحاولات (إصلاح Memory Leak)
  var _settingsApplied = false;
  function tryApplyOnce() {
    if (_settingsApplied) return;
    tryApplyStoredSettings();
    if (window._settingsLoaded) _settingsApplied = true;
  }
  tryApplyOnce();
  (window.safeSetTimeout || setTimeout)(tryApplyOnce, 400);
  (window.safeSetTimeout || setTimeout)(tryApplyOnce, 1200);
  (window.safeSetTimeout || setTimeout)(tryApplyOnce, 2500);

  // تحميل الأسعار والكونفيج بعد الإعدادات — تأخير كافٍ حتى يكون الـ DOM جاهزاً
  (window.safeSetTimeout || setTimeout)(loadMachinePricesFromServer, 600);
  (window.safeSetTimeout || setTimeout)(loadMachineConfigFromServer, 900);
  // بعد تحميل الأسعار: إعادة تطبيق إعدادات بايثون ثم إعادة حساب
  (window.safeSetTimeout || setTimeout)(function() {
    var d = window.__calculatorSettingsFromPython || (window.top && window.top !== window && window.top.__calculatorSettingsFromPython);
    if (window.applyCalculatorSettingsFromPython && d) try { window.applyCalculatorSettingsFromPython(d); } catch(e) {}
    if (typeof window.calculateAll === 'function') window.calculateAll();
  }, 2000);

  function getMachineBasePrice() {
    var doc = document;
    var mtEl = doc.getElementById('machine_type');
    var colEl = doc.getElementById('Number of colors');
    var widEl = doc.getElementById('Machine width');
    var t = (mtEl && mtEl.value) || (machineType && machineType.value);
    var c = (colEl && colEl.value) || (colors && colors.value);
    var w = (widEl && widEl.value) || (width && width.value);
    if (!t || !c || !w) return 0;
    var byType = MACHINE_PRICES[t] || MACHINE_PRICES[String(t)];
    if (!byType) {
      var typeKey = Object.keys(MACHINE_PRICES || {}).find(function(k) { return String(k) === String(t); });
      byType = typeKey ? MACHINE_PRICES[typeKey] : null;
    }
    if (!byType) return 0;
    var byColor = byType[c] != null ? byType[c] : (byType[String(c)] != null ? byType[String(c)] : null);
    if (byColor == null) {
      var colorKey = Object.keys(byType).find(function(k) { return String(k) === String(c); });
      byColor = colorKey != null ? byType[colorKey] : null;
    }
    if (!byColor || typeof byColor !== 'object') return 0;
    var val = byColor[w] != null ? byColor[w] : (byColor[String(w)] != null ? byColor[String(w)] : null);
    if (val == null) {
      var widthKey = Object.keys(byColor).find(function(k) { return String(k) === String(w); });
      val = widthKey != null ? byColor[widthKey] : null;
    }
    if (val == null || isNaN(parseFloat(val))) return 0;
    return parseFloat(val);
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
  // دالة الحصول على سعر الصرف الحالي
  // ----------------------------------------
  window.getExchangeRate = function() {
    return EXCHANGE_RATE;
  };

  // دالة لتحديث سعر الصرف (يمكن استدعاؤها من الأدمن)
  window.updateExchangeRate = function(newRate) {
    if (newRate && !isNaN(newRate)) {
      EXCHANGE_RATE = parseFloat(newRate);
      const exchangeInput = document.getElementById("exchange_rate");
      if (exchangeInput) exchangeInput.value = EXCHANGE_RATE.toFixed(2);
      window.debugLog('Exchange rate updated to:', EXCHANGE_RATE);
      if (isModelReady()) {
        calculateAll();
      }
    }
  };

  window.addEventListener('storage', function(event) {
    if (event.key === 'exchange_rate') {
      window.updateExchangeRate(event.newValue);
    }
  });

  // تحديث الإعدادات كل 5 دقائق فقط (تقليل الحمل — الإعدادات لا تتغير كثيراً)
  // حد أقصى 48 مرة (4 ساعات) لمنع Memory Leak
  (window.safeSetInterval || setInterval)(function() {
    if (window.anvil?.server?.call) {
      loadSettingsFromServer();
    }
  }, 300000, 48);

  // ----------------------------------------
  // الحسابات الأساسية
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
    } finally {
      window.QUOTATION_LOCKED = false;
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
  // الأحداث
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

  // Export mapping functions to window for use in quotations.js
  window.mapMachineType = mapMachineType;
  window.mapWinder = mapWinder;

})();

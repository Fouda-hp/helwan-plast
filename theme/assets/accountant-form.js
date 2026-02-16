(function() {
  if (!window.withButtonLock) {
    window.withButtonLock = function(btn, fn) {
      if (!btn || btn.disabled) return Promise.resolve();
      var orig = btn.textContent || btn.value || ''; var loading = btn.getAttribute('data-loading-text') || '...';
      btn.disabled = true; if (btn.textContent !== undefined) btn.textContent = loading; else if (btn.value !== undefined) btn.value = loading;
      return Promise.resolve(typeof fn === 'function' ? fn() : fn).finally(function() { btn.disabled = false; if (btn.textContent !== undefined) btn.textContent = orig; else if (btn.value !== undefined) btn.value = orig; });
    };
  }
  var lang = localStorage.getItem('hp_language') || 'en';
  var isAr = lang === 'ar';
  function t(en, ar) { return isAr ? ar : en; }
  function fmt(n) { return (n || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}); }
  function fmtCurr(n) { return fmt(n) + (isAr ? ' ج.م' : ' EGP'); }
  function setText(id, text) { var el = document.getElementById(id); if (el) el.textContent = text; }

  function applyI18n() {
    setText('pageTitle', t('Accountant Dashboard', 'لوحة المحاسب'));
    setText('btnBack', t('Back', 'رجوع'));
    setText('btnSeed', t('Setup Accounts', 'تهيئة الحسابات'));
    setText('navSuppliers', t('Suppliers', 'الموردين'));
    setText('navInventory', t('Inventory', 'المخازن'));
    setText('navInvoices', t('Purchase Invoices', 'فواتير الشراء'));
    setText('navCustomerAccounts', t('Customer Accounts', 'حسابات العملاء'));
    setText('navSupplierAccounts', t('Supplier Accounts', 'حسابات الموردين'));
    var tabLabels = {
      trial: t('Trial Balance', 'ميزان المراجعة'),
      income: t('Income Statement', 'قائمة الدخل'),
      balance: t('Balance Sheet', 'الميزانية العمومية'),
      profitability: t('Contract Profitability', 'ربحية العقود'),
      expenses: t('Expenses', 'المصروفات'),
      ledger: t('General Ledger', 'دفتر الاستاذ'),
      treasury: t('Treasury', 'الخزينة'),
      cashbank: t('Cash/Bank Statement', 'كشف النقدية والبنك'),
      vat: t('VAT Report', 'تقرير الضريبة'),
      opening: t('Opening Balances', 'ارصدة افتتاحية'),
      advstmt: t('Advanced Statement', 'كشف حساب متقدم')
    };
    document.querySelectorAll('.sub-tab').forEach(function(tab) {
      var key = tab.getAttribute('data-tab');
      if (tabLabels[key]) tab.textContent = tabLabels[key];
    });
    var wrapper = document.querySelector('.acc-wrapper'); if (wrapper && isAr) wrapper.style.direction = 'rtl';
    /* Treasury & Opening Balances i18n */
    var el;
    el = document.getElementById('btnLoadTreasury'); if (el) el.textContent = t('Load Treasury', 'تحميل الخزينة');
    el = document.getElementById('treasuryTitle'); if (el) el.textContent = t('Treasury - Bank & Cash Balances', 'الخزينة - ارصدة البنوك والنقدية');
    el = document.getElementById('cashbankTitle'); if (el) el.textContent = t('Cash & Bank Statement', 'كشف حساب النقدية والبنك');
    el = document.getElementById('btnLoadCashBank'); if (el) el.textContent = t('Load', 'تحميل');
    el = document.getElementById('lblCashbankAccount'); if (el) el.textContent = t('Account', 'الحساب');
    el = document.getElementById('optCashbankAll'); if (el) el.textContent = t('All (Cash & Banks)', 'الكل (النقدية والبنوك)');
    el = document.getElementById('trAcctName'); if (el) el.textContent = t('Account', 'الحساب');
    el = document.getElementById('trOpenBal'); if (el) el.textContent = t('Opening Balance', 'الرصيد الافتتاحي');
    el = document.getElementById('trLedgerBal'); if (el) el.textContent = t('Ledger Balance', 'رصيد الدفتر');
    el = document.getElementById('trCurrBal'); if (el) el.textContent = t('Current Balance', 'الرصيد الحالي');
    el = document.getElementById('openingFormTitle'); if (el) el.textContent = t('Set Opening Balance', 'تعيين الرصيد الافتتاحي');
    el = document.getElementById('lblObName'); if (el) el.textContent = t('Account', 'الحساب');
    var obSel = document.getElementById('obName'); if (obSel && obSel.options[0]) obSel.options[0].textContent = t('Select account...', 'اختر حساباً...');
    el = document.getElementById('lblObType'); if (el) el.textContent = t('Type', 'النوع');
    el = document.getElementById('lblObAmount'); if (el) el.textContent = t('Opening Balance', 'الرصيد الافتتاحي');
    el = document.getElementById('btnSetOb'); if (el) el.textContent = t('Set Balance', 'تعيين الرصيد');
    el = document.getElementById('btnLoadOb'); if (el) el.textContent = t('Load Balances', 'تحميل الارصدة');
    el = document.getElementById('openingTitle'); if (el) el.textContent = t('Opening Balances', 'ارصدة افتتاحية');
    el = document.getElementById('obThName'); if (el) el.textContent = t('Name', 'الاسم');
    el = document.getElementById('obThType'); if (el) el.textContent = t('Type', 'النوع');
    el = document.getElementById('obThAmount'); if (el) el.textContent = t('Opening Balance', 'الرصيد الافتتاحي');
    el = document.getElementById('obPostHint'); if (el) el.textContent = t('Post opening balances to the General Ledger (one journal entry dated 1 Jan). After posting, they appear in Ledger, Trial Balance, and Cash & Bank Statement.', 'ترحيل الأرصدة الافتتاحية إلى دفتر الأستاذ (قيد واحد بتاريخ 1 يناير). بعد الترحيل تظهر في الليدجر والميزان المراجع وكشف البنك.');
    el = document.getElementById('lblObYear'); if (el) el.textContent = t('Financial year', 'السنة المالية');
    el = document.getElementById('transfersDescHint'); if (el) el.textContent = t('Add a description for the transaction so it appears in the ledger (e.g. transfer from cash to bank).', 'أضف وصفاً للمعاملة لظهوره في الدفتر (مثال: تحويل من الصندوق إلى البنك).');
    el = document.getElementById('lblTransferDesc'); if (el) el.textContent = t('Description (transaction)', 'وصف المعاملة');
    el = document.getElementById('periodMonthHint'); if (el) el.textContent = t('You can lock or unlock each month individually (Lock / Unlock button next to each month).', 'يمكنك قفل أو فتح كل شهر على حدة (زر Lock / Unlock بجانب كل شهر).');
    el = document.getElementById('btnPostOb'); if (el) el.textContent = t('Post to Ledger', 'ترحيل إلى الدفتر');
  }

  var cashbankAccountsPopulated = false;
  window.switchTab = async function(el) {
    document.querySelectorAll('.sub-tab').forEach(function(t) { t.classList.remove('active'); });
    document.querySelectorAll('.tab-panel').forEach(function(p) { p.classList.remove('active'); });
    el.classList.add('active');
    var tab = el.getAttribute('data-tab');
    document.getElementById('panel-' + tab).classList.add('active');
    if (tab === 'cashbank') {
      if (!cashbankAccountsPopulated && window.populateCashBankAccounts) {
        await populateCashBankAccounts();
      }
      var toEl = document.getElementById('cashbankTo');
      if (toEl && !toEl.value) toEl.value = new Date().toISOString().slice(0, 10);
    }
    if (tab === 'opening' && window.populateOpeningBalanceAccounts) {
      await populateOpeningBalanceAccounts();
    }
    if (tab === 'advstmt' && window.populateAdvStmtEntities) {
      await populateAdvStmtEntities();
    }
  };

  window.navTo = function(page) {
    if (page === 'suppliers' && window.pyOpenSuppliers) window.pyOpenSuppliers();
    else if (page === 'inventory' && window.pyOpenInventory) window.pyOpenInventory();
    else if (page === 'invoices' && window.pyOpenPurchaseInvoices) window.pyOpenPurchaseInvoices();
  };

  window.openCustomerSummary = function() {
    if (window.pyOpenCustomerSummary) window.pyOpenCustomerSummary();
  };
  window.openSupplierSummary = function() {
    if (window.pyOpenSupplierSummary) window.pyOpenSupplierSummary();
  };

  window.goBack = function() {
    if (window.pyGoBack) window.pyGoBack();
    else window.location.hash = '#admin';
  };

  window.seedAccounts = async function() {
    var ok = await (window.showConfirm || function(m) { return Promise.resolve(confirm(m)); })(t('Initialize the chart of accounts? This will create default accounts if they do not exist.', 'تهيئة دليل الحسابات؟ سيتم انشاء الحسابات الافتراضية اذا لم تكن موجودة.'));
    if (!ok) return;
    try {
      var res = await window.pySeedAccounts();
      if (res && res.success) {
        if (window.showNotification) window.showNotification('success', '', t('Accounts initialized', 'تم تهيئة الحسابات'));
      } else {
        if (window.showNotification) window.showNotification('error', '', res ? res.message : 'Error');
      }
    } catch (err) {
      if (window.showNotification) window.showNotification('error', '', String(err));
    }
  };

  /* === Trial Balance === */
  window.loadTrialBalance = async function() {
    var tbody = document.getElementById('trialBody');
    if (!tbody) return;
    if (typeof window.pyGetTrialBalance !== 'function') { if (window.showNotification) window.showNotification('error', '', t('App not ready. Go back and open again.', 'التطبيق غير جاهز. ارجع وافتح مرة أخرى.')); return; }
    var from = (document.getElementById('trialFrom') && document.getElementById('trialFrom').value) || '';
    var to = (document.getElementById('trialTo') && document.getElementById('trialTo').value) || '';
    tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">' + t('Loading...', 'جاري التحميل...') + '</td></tr>';
    try {
      var res = await window.pyGetTrialBalance(from, to);
      if (res && res.success) {
        var data = res.data || [];
        if (data.length === 0) { tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">' + t('No data', 'لا توجد بيانات') + '</td></tr>'; return; }
        var html = '';
        var totalDebit = 0, totalCredit = 0;
        data.forEach(function(row) {
          var d = parseFloat(row.debit || 0); var c = parseFloat(row.credit || 0);
          totalDebit += d; totalCredit += c;
          html += '<tr><td>' + (row.account_name || '') + '</td><td class="text-right">' + (d > 0 ? fmtCurr(d) : '-') + '</td><td class="text-right">' + (c > 0 ? fmtCurr(c) : '-') + '</td></tr>';
        });
        html += '<tr class="total-row"><td><strong>' + t('Total', 'الاجمالي') + '</strong></td><td class="text-right"><strong>' + fmtCurr(totalDebit) + '</strong></td><td class="text-right"><strong>' + fmtCurr(totalCredit) + '</strong></td></tr>';
        tbody.innerHTML = html;
      } else {
        tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">' + (res ? res.message : 'Error') + '</td></tr>';
      }
    } catch (err) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">' + (err && err.message ? err.message : String(err)) + '</td></tr>';
    }
  };

  /* === Income Statement === */
  window.loadIncomeStatement = async function() {
    var tbody = document.getElementById('incomeBody');
    if (!tbody) return;
    if (typeof window.pyGetIncomeStatement !== 'function') { if (window.showNotification) window.showNotification('error', '', t('App not ready. Go back and open again.', 'التطبيق غير جاهز. ارجع وافتح مرة أخرى.')); return; }
    var from = (document.getElementById('incomeFrom') && document.getElementById('incomeFrom').value) || '';
    var to = (document.getElementById('incomeTo') && document.getElementById('incomeTo').value) || '';
    tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">' + t('Loading...', 'جاري التحميل...') + '</td></tr>';
    try {
      var res = await window.pyGetIncomeStatement(from, to);
      if (res && res.success) {
        var data = res.data || {};
        var revenues = data.revenues || [];
        var expenses = data.expenses || [];
        var totalRevenue = parseFloat(data.total_revenue || 0);
        var totalExpense = parseFloat(data.total_expenses || 0);
        var netIncome = parseFloat(data.net_income || 0);
        var summaryHtml = '';
        summaryHtml += '<div class="summary-box"><div class="label">' + t('Total Revenue', 'اجمالي الايرادات') + '</div><div class="value text-green">' + fmtCurr(totalRevenue) + '</div></div>';
        summaryHtml += '<div class="summary-box"><div class="label">' + t('Total Expenses', 'اجمالي المصروفات') + '</div><div class="value text-red">' + fmtCurr(totalExpense) + '</div></div>';
        summaryHtml += '<div class="summary-box"><div class="label">' + t('Net Income', 'صافي الدخل') + '</div><div class="value" style="color:' + (netIncome >= 0 ? '#2e7d32' : '#c62828') + ';">' + fmtCurr(netIncome) + '</div></div>';
        var sumEl = document.getElementById('incomeSummary'); if (sumEl) sumEl.innerHTML = summaryHtml;
        var html = '';
        if (revenues.length > 0) {
          revenues.forEach(function(r) { html += '<tr><td>' + t('Revenue', 'ايرادات') + '</td><td>' + (r.account_name || '') + '</td><td class="text-right text-green">' + fmtCurr(r.amount) + '</td></tr>'; });
          html += '<tr class="total-row"><td></td><td><strong>' + t('Total Revenue', 'اجمالي الايرادات') + '</strong></td><td class="text-right text-green"><strong>' + fmtCurr(totalRevenue) + '</strong></td></tr>';
        }
        if (expenses.length > 0) {
          expenses.forEach(function(e) { html += '<tr><td>' + t('Expense', 'مصروفات') + '</td><td>' + (e.account_name || '') + '</td><td class="text-right text-red">' + fmtCurr(e.amount) + '</td></tr>'; });
          html += '<tr class="total-row"><td></td><td><strong>' + t('Total Expenses', 'اجمالي المصروفات') + '</strong></td><td class="text-right text-red"><strong>' + fmtCurr(totalExpense) + '</strong></td></tr>';
        }
        html += '<tr class="total-row"><td></td><td><strong>' + t('Net Income', 'صافي الدخل') + '</strong></td><td class="text-right" style="color:' + (netIncome >= 0 ? '#2e7d32' : '#c62828') + ';"><strong>' + fmtCurr(netIncome) + '</strong></td></tr>';
        tbody.innerHTML = html || '<tr><td colspan="3" class="empty-msg">' + t('No data', 'لا توجد بيانات') + '</td></tr>';
      } else {
        tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">' + (res ? res.message : 'Error') + '</td></tr>';
      }
    } catch (err) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">' + (err && err.message ? err.message : String(err)) + '</td></tr>';
    }
  };

  /* === Balance Sheet === */
  window.loadBalanceSheet = async function() {
    var tbody = document.getElementById('balanceBody');
    if (!tbody) return;
    if (typeof window.pyGetBalanceSheet !== 'function') { if (window.showNotification) window.showNotification('error', '', t('App not ready. Go back and open again.', 'التطبيق غير جاهز. ارجع وافتح مرة أخرى.')); return; }
    var asOf = (document.getElementById('balanceDate') && document.getElementById('balanceDate').value) || '';
    tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">' + t('Loading...', 'جاري التحميل...') + '</td></tr>';
    try {
      var res = await window.pyGetBalanceSheet(asOf);
      if (res && res.success) {
        var subEl = document.getElementById('balanceSubtitle');
        if (subEl) subEl.textContent = t('All amounts in EGP', 'جميع المبالغ بالجنيه المصري');
        var data = res.data || {};
        var assets = data.assets || [];
        var liabilities = data.liabilities || [];
        var equity = data.equity || [];
        var html = '';
        if (assets.length > 0) {
          assets.forEach(function(a) { html += '<tr><td>' + t('Assets', 'اصول') + '</td><td>' + (a.account_name || '') + '</td><td class="text-right">' + fmtCurr(a.amount) + '</td></tr>'; });
          html += '<tr class="total-row"><td></td><td><strong>' + t('Total Assets', 'اجمالي الاصول') + '</strong></td><td class="text-right"><strong>' + fmtCurr(data.total_assets || 0) + '</strong></td></tr>';
        }
        if (liabilities.length > 0) {
          liabilities.forEach(function(l) { html += '<tr><td>' + t('Liabilities', 'التزامات') + '</td><td>' + (l.account_name || '') + '</td><td class="text-right">' + fmtCurr(l.amount) + '</td></tr>'; });
          html += '<tr class="total-row"><td></td><td><strong>' + t('Total Liabilities', 'اجمالي الالتزامات') + '</strong></td><td class="text-right"><strong>' + fmtCurr(data.total_liabilities || 0) + '</strong></td></tr>';
        }
        if (equity.length > 0) {
          equity.forEach(function(e) { html += '<tr><td>' + t('Equity', 'حقوق الملكية') + '</td><td>' + (e.account_name || '') + '</td><td class="text-right">' + fmtCurr(e.amount) + '</td></tr>'; });
          html += '<tr class="total-row"><td></td><td><strong>' + t('Total Equity', 'اجمالي حقوق الملكية') + '</strong></td><td class="text-right"><strong>' + fmtCurr(data.total_equity || 0) + '</strong></td></tr>';
        }
        tbody.innerHTML = html || '<tr><td colspan="3" class="empty-msg">' + t('No data', 'لا توجد بيانات') + '</td></tr>';
      } else {
        tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">' + (res ? res.message : 'Error') + '</td></tr>';
      }
    } catch (err) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">' + (err && err.message ? err.message : String(err)) + '</td></tr>';
    }
  };

  /* === Contract Profitability === */
  window.loadProfitability = async function() {
    var tbody = document.getElementById('profitBody');
    if (!tbody) return;
    if (typeof window.pyGetContractProfitability !== 'function') { if (window.showNotification) window.showNotification('error', '', t('App not ready. Go back and open again.', 'التطبيق غير جاهز. ارجع وافتح مرة أخرى.')); return; }
    tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">' + t('Loading...', 'جاري التحميل...') + '</td></tr>';
    try {
      var res = await window.pyGetContractProfitability();
      if (res && res.success) {
        var data = res.data || [];
        if (data.length === 0) { tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">' + t('No data', 'لا توجد بيانات') + '</td></tr>'; return; }
        var totalRev = 0, totalCost = 0, totalProfit = 0;
        var html = '';
        data.forEach(function(c) {
          var rev = parseFloat(c.revenue || 0);
          var cost = parseFloat(c.costs || 0);
          var profit = parseFloat(c.profit || (rev - cost));
          var margin = rev > 0 ? ((profit / rev) * 100).toFixed(1) : '0.0';
          totalRev += rev; totalCost += cost; totalProfit += profit;
          html += '<tr>';
          html += '<td><strong>' + (c.contract_number || '') + '</strong></td>';
          html += '<td>' + (c.client_name || '') + '</td>';
          html += '<td class="text-right">' + fmtCurr(rev) + '</td>';
          html += '<td class="text-right">' + fmtCurr(cost) + '</td>';
          html += '<td class="text-right" style="color:' + (profit >= 0 ? '#2e7d32' : '#c62828') + ';font-weight:600;">' + fmtCurr(profit) + '</td>';
          html += '<td class="text-right">' + margin + '%</td>';
          html += '</tr>';
        });
        var totalMargin = totalRev > 0 ? ((totalProfit / totalRev) * 100).toFixed(1) : '0.0';
        html += '<tr class="total-row"><td colspan="2"><strong>' + t('Total', 'الاجمالي') + '</strong></td><td class="text-right"><strong>' + fmtCurr(totalRev) + '</strong></td><td class="text-right"><strong>' + fmtCurr(totalCost) + '</strong></td><td class="text-right" style="color:' + (totalProfit >= 0 ? '#2e7d32' : '#c62828') + ';"><strong>' + fmtCurr(totalProfit) + '</strong></td><td class="text-right"><strong>' + totalMargin + '%</strong></td></tr>';
        tbody.innerHTML = html;
        var summaryHtml = '';
        summaryHtml += '<div class="summary-box"><div class="label">' + t('Total Revenue', 'اجمالي الايرادات') + '</div><div class="value text-green">' + fmtCurr(totalRev) + '</div></div>';
        summaryHtml += '<div class="summary-box"><div class="label">' + t('Total Costs', 'اجمالي التكاليف') + '</div><div class="value text-red">' + fmtCurr(totalCost) + '</div></div>';
        summaryHtml += '<div class="summary-box"><div class="label">' + t('Total Profit', 'اجمالي الربح') + '</div><div class="value" style="color:' + (totalProfit >= 0 ? '#2e7d32' : '#c62828') + ';">' + fmtCurr(totalProfit) + '</div></div>';
        summaryHtml += '<div class="summary-box"><div class="label">' + t('Avg Margin', 'متوسط الهامش') + '</div><div class="value">' + totalMargin + '%</div></div>';
        var sumEl = document.getElementById('profitSummary'); if (sumEl) sumEl.innerHTML = summaryHtml;
      } else {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">' + (res ? res.message : 'Error') + '</td></tr>';
      }
    } catch (err) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">' + (err && err.message ? err.message : String(err)) + '</td></tr>';
    }
  };

  /* === Expenses === */
  window.addExpense = async function() {
    var date = document.getElementById('expDate').value;
    var category = document.getElementById('expCategory').value;
    var amount = parseFloat(document.getElementById('expAmount').value) || 0;
    var desc = document.getElementById('expDesc').value.trim();
    if (!date || amount <= 0) {
      if (window.showNotification) window.showNotification('error', '', t('Date and amount are required', 'التاريخ والمبلغ مطلوبين'));
      return;
    }
    try {
      var res = await window.pyAddExpense({ date: date, category: category, amount: amount, description: desc });
      if (res && res.success) {
        if (window.showNotification) window.showNotification('success', '', t('Expense added', 'تم اضافة المصروف'));
        document.getElementById('expAmount').value = '0';
        document.getElementById('expDesc').value = '';
        loadExpenses();
      } else {
        if (window.showNotification) window.showNotification('error', '', res ? res.message : 'Error');
      }
    } catch (err) {
      if (window.showNotification) window.showNotification('error', '', String(err));
    }
  };

  window.loadExpenses = async function() {
    var tbody = document.getElementById('expBody');
    if (!tbody) return;
    if (typeof window.pyGetExpenses !== 'function') { if (window.showNotification) window.showNotification('error', '', t('App not ready. Go back and open again.', 'التطبيق غير جاهز. ارجع وافتح مرة أخرى.')); return; }
    var from = (document.getElementById('expFrom') && document.getElementById('expFrom').value) || '';
    var to = (document.getElementById('expTo') && document.getElementById('expTo').value) || '';
    var cat = (document.getElementById('expFilterCat') && document.getElementById('expFilterCat').value) || '';
    tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">' + t('Loading...', 'جاري التحميل...') + '</td></tr>';
    try {
      var res = await window.pyGetExpenses(from, to, cat);
      if (res && res.success) {
        var data = res.data || [];
        if (data.length === 0) { tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">' + t('No expenses found', 'لا توجد مصروفات') + '</td></tr>'; return; }
        var html = '';
        var total = 0;
        data.forEach(function(e) {
          var amt = parseFloat(e.amount || 0);
          total += amt;
          html += '<tr><td>' + (e.date || '').substring(0, 10) + '</td><td>' + (e.category || '') + '</td><td>' + (e.description || '') + '</td><td class="text-right">' + fmt(amt) + '</td><td><button class="btn-delete" onclick="withButtonLock(this, function(){ return delExpense(\'' + e.id + '\'); })" data-loading-text="...">' + t('Del', 'حذف') + '</button></td></tr>';
        });
        html += '<tr class="total-row"><td colspan="3"><strong>' + t('Total', 'الاجمالي') + '</strong></td><td class="text-right"><strong>' + fmt(total) + '</strong></td><td></td></tr>';
        tbody.innerHTML = html;
        var expSum = document.getElementById('expSummary'); if (expSum) expSum.innerHTML = '<div class="summary-box"><div class="label">' + t('Total Expenses', 'اجمالي المصروفات') + '</div><div class="value text-red">' + fmt(total) + '</div></div><div class="summary-box"><div class="label">' + t('Count', 'العدد') + '</div><div class="value">' + data.length + '</div></div>';
      } else {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">' + (res ? res.message : 'Error') + '</td></tr>';
      }
    } catch (err) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">' + (err && err.message ? err.message : String(err)) + '</td></tr>';
    }
  };

  window.delExpense = async function(id) {
    var ok = await (window.showConfirm || function(m) { return Promise.resolve(confirm(m)); })(t('Delete this expense?', 'حذف هذا المصروف؟'));
    if (!ok) return;
    try {
      var res = await window.pyDeleteExpense(id);
      if (res && res.success) {
        if (window.showNotification) window.showNotification('success', '', t('Deleted', 'تم الحذف'));
        loadExpenses();
      } else {
        if (window.showNotification) window.showNotification('error', '', res ? res.message : 'Error');
      }
    } catch (err) {
      if (window.showNotification) window.showNotification('error', '', String(err));
    }
  };

  /* === General Ledger === */
  window.loadLedger = async function() {
    var tbody = document.getElementById('ledgerBody');
    if (!tbody) return;
    if (typeof window.pyGetLedgerEntries !== 'function') { if (window.showNotification) window.showNotification('error', '', t('App not ready. Go back and open again.', 'التطبيق غير جاهز. ارجع وافتح مرة أخرى.')); return; }
    var accountId = (document.getElementById('ledgerAccount') && document.getElementById('ledgerAccount').value) || '';
    var from = (document.getElementById('ledgerFrom') && document.getElementById('ledgerFrom').value) || '';
    var to = (document.getElementById('ledgerTo') && document.getElementById('ledgerTo').value) || '';
    tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">' + t('Loading...', 'جاري التحميل...') + '</td></tr>';
    try {
      var res = await window.pyGetLedgerEntries(accountId, from, to);
      if (res && res.success) {
        var data = res.data || [];
        if (data.length === 0) { tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">' + t('No entries found', 'لا توجد قيود') + '</td></tr>'; return; }
        var html = '';
        var balance = 0;
        data.forEach(function(entry) {
          var d = parseFloat(entry.debit || 0);
          var c = parseFloat(entry.credit || 0);
          balance += d - c;
          html += '<tr>';
          html += '<td>' + (entry.date || '').substring(0, 10) + '</td>';
          html += '<td>' + (entry.account_name || '') + '</td>';
          html += '<td>' + (entry.description || '') + '</td>';
          html += '<td class="text-right">' + (d > 0 ? fmt(d) : '-') + '</td>';
          html += '<td class="text-right">' + (c > 0 ? fmt(c) : '-') + '</td>';
          html += '<td class="text-right" style="font-weight:600;">' + fmt(balance) + '</td>';
          html += '</tr>';
        });
        tbody.innerHTML = html;
      } else {
        var msg = (res && res.message) ? res.message : 'Error';
        if (msg === 'Authentication required' || msg.indexOf('Authentication') !== -1) {
          msg = t('Session expired or not logged in. Please go Back and sign in again.', 'انتهت الجلسة أو لم يتم تسجيل الدخول. من فضلك ارجع وسجّل الدخول مرة أخرى.');
        }
        tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">' + msg + '</td></tr>';
      }
    } catch (err) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">' + (err && err.message ? err.message : String(err)) + '</td></tr>';
    }
  };

  /* Populate account dropdowns from full chart of accounts */
  async function populateLedgerAccounts() {
    try {
      var items = [];

      if (window.pyGetChartOfAccounts) {
        var chartRes = await window.pyGetChartOfAccounts();
        if (chartRes && chartRes.success && Array.isArray(chartRes.accounts)) {
          items = chartRes.accounts
            .filter(function(a){ return a && a.code; })
            .map(function(a){
              return {
                id: a.code,
                label: (a.code || '') + ' - ' + (a.name_en || a.name_ar || a.code)
              };
            });
        }
      }

      // fallback for older shape from trial balance
      if (!items.length && window.pyGetTrialBalance) {
        var res = await window.pyGetTrialBalance('', '');
        var arr = (res && (res.data || res.rows || res.entries)) || [];
        if (Array.isArray(arr)) {
          items = arr.map(function(a) {
            var id = a.account_id || a.account_code || a.code || '';
            var label = a.account_name || a.name_en || a.name_ar || id;
            return { id: id, label: label };
          }).filter(function(x){ return x.id; });
        }
      }

      var seen = {};
      items = items.filter(function(x){
        if (!x.id || seen[x.id]) return false;
        seen[x.id] = true;
        return true;
      }).sort(function(a,b){ return String(a.id).localeCompare(String(b.id)); });

      var ledgerSel = document.getElementById('ledgerAccount');
      if (ledgerSel) {
        var ledgerOpts = '<option value="">' + t('All Accounts', 'كل الحسابات') + '</option>';
        items.forEach(function(a) {
          ledgerOpts += '<option value="' + a.id + '">' + a.label + '</option>';
        });
        ledgerSel.innerHTML = ledgerOpts;
      }

      var obSel = document.getElementById('obName');
      if (obSel) {
        var obOpts = '<option value="">' + t('Select account...', 'اختر حساباً...') + '</option>';
        items.forEach(function(a) {
          obOpts += '<option value="' + a.id + '">' + a.label + '</option>';
        });
        obSel.innerHTML = obOpts;
      }
    } catch (err) { /* ignore */ }
  }

  // Set default dates (only if elements exist)
  var today = new Date().toISOString().substring(0, 10);
  var yearStart = new Date().getFullYear() + '-01-01';
  function setDateIfExists(id, val) { var el = document.getElementById(id); if (el) el.value = val; }
  setDateIfExists('trialFrom', yearStart);
  setDateIfExists('trialTo', today);
  setDateIfExists('incomeFrom', yearStart);
  setDateIfExists('incomeTo', today);
  setDateIfExists('balanceDate', today);
  setDateIfExists('expDate', today);
  setDateIfExists('expFrom', yearStart);
  setDateIfExists('expTo', today);
  setDateIfExists('ledgerFrom', yearStart);
  setDateIfExists('ledgerTo', today);

  /* === Currency / Exchange Rates === */
  window.saveCurrRate = async function() {
    var code = document.getElementById('currCode').value;
    var rate = parseFloat(document.getElementById('currRate').value) || 0;
    if (!code || rate <= 0) {
      if (window.showNotification) window.showNotification('error', '', t('Currency and valid rate are required', 'العملة وسعر صرف صحيح مطلوبين'));
      return;
    }
    try {
      var res = await window.pySetExchangeRate(code, rate);
      if (res && res.success) {
        if (window.showNotification) window.showNotification('success', '', t('Rate saved', 'تم حفظ سعر الصرف'));
        document.getElementById('currRate').value = '0';
        loadCurrencyRates();
      } else {
        if (window.showNotification) window.showNotification('error', '', res ? res.message : 'Error');
      }
    } catch (err) {
      if (window.showNotification) window.showNotification('error', '', String(err));
    }
  };

  window.loadCurrencyRates = async function() {
    var tbody = document.getElementById('currBody');
    if (!tbody) return;
    if (typeof window.pyGetExchangeRates !== 'function') return;
    tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">' + t('Loading...', 'جاري التحميل...') + '</td></tr>';
    try {
      var res = await window.pyGetExchangeRates();
      if (res && res.success) {
        var data = res.data || [];
        if (data.length === 0) { tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">' + t('No rates set', 'لا توجد اسعار صرف') + '</td></tr>'; return; }
        var html = '';
        data.forEach(function(r) {
          html += '<tr><td><strong>' + r.currency_code + '</strong></td>';
          html += '<td class="text-right">' + fmt(r.rate_to_egp) + '</td>';
          html += '<td>' + (r.updated_at || '').substring(0, 10) + '</td>';
          html += '<td><button class="btn-delete" onclick="withButtonLock(this, function(){ return delCurrRate(\'' + r.currency_code + '\'); })" data-loading-text="...">' + t('Del', 'حذف') + '</button></td></tr>';
        });
        tbody.innerHTML = html;
      } else {
        tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">' + (res ? res.message : 'Error') + '</td></tr>';
      }
    } catch (err) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">' + (err && err.message ? err.message : String(err)) + '</td></tr>';
    }
  };

  window.delCurrRate = async function(code) {
    var ok = await (window.showConfirm || function(m) { return Promise.resolve(confirm(m)); })(t('Delete rate for ' + code + '?', 'حذف سعر ' + code + '؟'));
    if (!ok) return;
    try {
      var res = await window.pyDeleteExchangeRate(code);
      if (res && res.success) {
        if (window.showNotification) window.showNotification('success', '', t('Rate deleted', 'تم حذف سعر الصرف'));
        loadCurrencyRates();
      } else {
        if (window.showNotification) window.showNotification('error', '', res ? res.message : 'Error');
      }
    } catch (err) {
      if (window.showNotification) window.showNotification('error', '', String(err));
    }
  };


  /* === Treasury === */
  window.loadTreasury = async function() {
    var tbody = document.getElementById('treasuryBody');
    if (!tbody) return;
    if (typeof window.pyGetTreasurySummary !== 'function') return;
    tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">' + t('Loading...', 'جاري التحميل...') + '</td></tr>';
    try {
      var res = await window.pyGetTreasurySummary();
      if (res && res.success) {
        var data = res.data || [];
        if (data.length === 0) { tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">' + t('No treasury accounts found', 'لا توجد حسابات خزينة') + '</td></tr>'; return; }
        var html = '';
        var totalOpen = 0, totalLedger = 0, totalCurr = 0;
        data.forEach(function(row) {
          var ob = parseFloat(row.opening_balance || 0);
          var lb = parseFloat(row.ledger_balance || 0);
          var cb = parseFloat(row.current_balance || 0);
          totalOpen += ob; totalLedger += lb; totalCurr += cb;
          html += '<tr><td>' + (row.account_name || '') + '</td>';
          html += '<td class="text-right">' + fmt(ob) + '</td>';
          html += '<td class="text-right">' + fmt(lb) + '</td>';
          html += '<td class="text-right" style="font-weight:600;color:' + (cb >= 0 ? '#2e7d32' : '#c62828') + ';">' + fmt(cb) + '</td></tr>';
        });
        html += '<tr class="total-row"><td><strong>' + t('Total', 'الاجمالي') + '</strong></td><td class="text-right"><strong>' + fmt(totalOpen) + '</strong></td><td class="text-right"><strong>' + fmt(totalLedger) + '</strong></td><td class="text-right"><strong>' + fmt(totalCurr) + '</strong></td></tr>';
        tbody.innerHTML = html;
        var summaryHtml = '';
        summaryHtml += '<div class="summary-box"><div class="label">' + t('Total Opening', 'اجمالي الافتتاحي') + '</div><div class="value">' + fmt(totalOpen) + '</div></div>';
        summaryHtml += '<div class="summary-box"><div class="label">' + t('Total Ledger', 'اجمالي الدفتر') + '</div><div class="value">' + fmt(totalLedger) + '</div></div>';
        summaryHtml += '<div class="summary-box"><div class="label">' + t('Total Current', 'اجمالي الحالي') + '</div><div class="value" style="color:' + (totalCurr >= 0 ? '#2e7d32' : '#c62828') + ';">' + fmt(totalCurr) + '</div></div>';
        var ts = document.getElementById('treasurySummary'); if (ts) ts.innerHTML = summaryHtml;
      } else {
        tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">' + (res ? res.message : 'Error') + '</td></tr>';
      }
    } catch (err) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">' + (err && err.message ? err.message : String(err)) + '</td></tr>';
    }
  };

  /* === Cash/Bank Statement === */
  var defaultBankAccounts = [{ code: '1000', name_en: 'Cash', name_ar: 'نقدية' }, { code: '1010', name_en: 'Bank', name_ar: 'بنك' }];
  function isCashOrBankCode(code) {
    code = String(code || '');
    return code === '1000' || (code.indexOf('101') === 0 && code.length === 4);
  }
  function isCashOrBankAccount(a) {
    if (!a) return false;
    var code = String(a.code || '');
    var nameEn = String(a.name_en || '').toLowerCase();
    var nameAr = String(a.name_ar || '');
    var acctType = String(a.account_type || '').toLowerCase();
    var parent = String(a.parent_code || '');

    if (isCashOrBankCode(code)) return true;
    if (parent === '1000' || parent === '1010' || parent.indexOf('101') === 0) return true;

    var byName =
      nameEn.indexOf('cash') !== -1 ||
      nameEn.indexOf('bank') !== -1 ||
      nameAr.indexOf('نقد') !== -1 ||
      nameAr.indexOf('خز') !== -1 ||
      nameAr.indexOf('بنك') !== -1;

    return byName && (acctType === 'asset' || acctType === '');
  }
  async function populateCashBankAccounts() {
    var sel = document.getElementById('cashbankAccount');
    if (!sel) return;
    var firstOpt = sel.options[0];
    var firstHtml = firstOpt ? firstOpt.outerHTML : '<option value="" id="optCashbankAll">All (Cash &amp; Banks)</option>';
    var list = defaultBankAccounts;
    try {
      var res = window.pyGetBankAccounts ? await window.pyGetBankAccounts() : null;
      if (res && res.success && res.accounts && res.accounts.length) {
        list = res.accounts;
      } else if (window.pyGetChartOfAccounts) {
        var chartRes = await window.pyGetChartOfAccounts();
        if (chartRes && chartRes.success && chartRes.accounts && chartRes.accounts.length) {
          list = chartRes.accounts.filter(function(a) { return isCashOrBankAccount(a); });
          if (list.length) list.sort(function(a,b) { return String(a.code || '').localeCompare(String(b.code || '')); });
        }
      }
    } catch (e) {}
    if (!list.length) list = defaultBankAccounts.slice();
    sel.innerHTML = firstHtml;
    list.forEach(function(a) {
      var code = String(a.code || '');
      var opt = document.createElement('option');
      opt.value = code;
      opt.textContent = (a.name_en || a.name_ar || code) + ' (' + code + ')';
      sel.appendChild(opt);
    });
    cashbankAccountsPopulated = true;
  }
  window.populateCashBankAccounts = populateCashBankAccounts;

  window.loadCashBankStatement = async function() {
    var tbody = document.getElementById('cashbankBody');
    if (!tbody) return;
    if (typeof window.pyGetCashBankStatement !== 'function') { if (window.showNotification) window.showNotification('error', '', t('App not ready. Go back and open again.', 'التطبيق غير جاهز. ارجع وافتح مرة أخرى.')); return; }
    var fromEl = document.getElementById('cashbankFrom');
    var toEl = document.getElementById('cashbankTo');
    if (fromEl && !fromEl.value) {
      var d = new Date();
      fromEl.value = new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10);
    }
    if (toEl && !toEl.value) toEl.value = new Date().toISOString().slice(0, 10);
    var accountCode = (document.getElementById('cashbankAccount') && document.getElementById('cashbankAccount').value) || '';
    var fromVal = (fromEl && fromEl.value) || '';
    var toVal = (toEl && toEl.value) || '';
    tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">' + t('Loading...', 'جاري التحميل...') + '</td></tr>';
    try {
      var res = await window.pyGetCashBankStatement(accountCode || null, fromVal || null, toVal || null);
      if (res && res.success) {
        var data = res.data || [];
        if (data.length === 0) {
          tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">' + t('No movements in this period', 'لا توجد حركات في هذه الفترة') + '</td></tr>';
          return;
        }
        var html = '';
        data.forEach(function(row) {
          html += '<tr>';
          html += '<td>' + (row.date || '').toString().substring(0, 10) + '</td>';
          html += '<td>' + (row.account_name || row.account_code || '') + '</td>';
          html += '<td>' + (row.description || '') + '</td>';
          html += '<td class="text-right">' + fmt(row.debit) + '</td>';
          html += '<td class="text-right">' + fmt(row.credit) + '</td>';
          html += '<td class="text-right" style="font-weight:600;">' + fmt(row.balance) + '</td></tr>';
        });
        tbody.innerHTML = html;
      } else {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">' + (res ? res.message : 'Error') + '</td></tr>';
      }
    } catch (err) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="empty-msg">' + (err && err.message ? err.message : String(err)) + '</td></tr>';
    }
  };

  /* === Opening Balances === */
  var openingAccountsPopulated = false;
  var defaultObAccounts = [{ code: '1000', name_en: 'Cash', name_ar: 'نقدية' }, { code: '1010', name_en: 'Bank', name_ar: 'بنك' }];
  async function populateOpeningBalanceAccounts() {
    if (openingAccountsPopulated) return;
    var sel = document.getElementById('obName');
    if (!sel) return;
    var firstHtml = '<option value="">' + t('Select account...', 'اختر حساباً...') + '</option>';
    var list = defaultObAccounts.slice();
    try {
      if (window.pyGetChartOfAccounts) {
        var chartRes = await window.pyGetChartOfAccounts();
        if (chartRes && chartRes.success && chartRes.accounts && chartRes.accounts.length) {
          list = chartRes.accounts.slice();
          list.sort(function(a,b) { return String(a.code || '').localeCompare(String(b.code || '')); });
        }
      }

      // fallback
      if ((!list || !list.length) && window.pyGetBankAccounts) {
        var res = await window.pyGetBankAccounts();
        if (res && res.success && res.accounts && res.accounts.length) {
          list = res.accounts;
        }
      }
    } catch (e) {}
    if (!list.length) list = defaultObAccounts.slice();
    sel.innerHTML = firstHtml;
    list.forEach(function(a) {
      var code = String(a.code || '');
      var opt = document.createElement('option');
      opt.value = code;
      opt.textContent = (a.name_en || a.name_ar || code) + ' (' + code + ')';
      sel.appendChild(opt);
    });
    openingAccountsPopulated = true;
  }
  window.populateOpeningBalanceAccounts = populateOpeningBalanceAccounts;

  window.setOpeningBalance = async function() {
    var name = document.getElementById('obName').value.trim();
    var amount = parseFloat(document.getElementById('obAmount').value) || 0;
    if (!name) {
      if (window.showNotification) window.showNotification('error', '', t('Select an account', 'اختر حساباً'));
      return;
    }
    var code = String(name);
    var type = (code === '1000') ? 'cash' : 'bank';
    try {
      var res = await window.pySetOpeningBalance(name, type, amount);
      if (res && res.success) {
        if (window.showNotification) window.showNotification('success', '', t('Opening balance set', 'تم تعيين الرصيد الافتتاحي'));
        document.getElementById('obName').value = '';
        document.getElementById('obAmount').value = '0';
        loadOpeningBalances();
      } else {
        if (window.showNotification) window.showNotification('error', '', res ? res.message : 'Error');
      }
    } catch (err) {
      if (window.showNotification) window.showNotification('error', '', String(err));
    }
  };

  window.loadVatReport = async function() {
    var summaryEl = document.getElementById('vatSummary');
    var tbody = document.getElementById('vatDetailBody');
    if (!summaryEl || !tbody) return;
    if (typeof window.pyGetVatReport !== 'function') { if (window.showNotification) window.showNotification('error', '', 'VAT report not available'); return; }
    summaryEl.innerHTML = ''; summaryEl.style.display = 'flex';
    tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">' + t('Loading...', 'جاري التحميل...') + '</td></tr>';
    var asOf = document.getElementById('vatAsOf') ? document.getElementById('vatAsOf').value : '';
    var from = document.getElementById('vatFrom') ? document.getElementById('vatFrom').value : '';
    var to = document.getElementById('vatTo') ? document.getElementById('vatTo').value : '';
    try {
      var res = await window.pyGetVatReport(asOf || null, from || null, to || null);
      if (res && res.success) {
        var inputVat = parseFloat(res.input_vat_balance || 0);
        var outputVat = parseFloat(res.output_vat_payable || 0);
        var net = parseFloat(res.net_position || 0);
        summaryEl.innerHTML = '<div style="padding:12px 20px;background:#e8f5e9;border-radius:8px;"><strong>' + t('Input VAT (recoverable)', 'ضريبة مدخلات - ليك') + ':</strong> ' + fmtCurr(inputVat) + '</div>' +
          '<div style="padding:12px 20px;background:#ffebee;border-radius:8px;"><strong>' + t('Output VAT (payable)', 'ضريبة مخرجات - عليك') + ':</strong> ' + fmtCurr(outputVat) + '</div>' +
          '<div style="padding:12px 20px;background:#e3f2fd;border-radius:8px;"><strong>' + t('Net position', 'الرصيد الصافي') + ':</strong> ' + fmtCurr(net) + (net >= 0 ? ' (' + t('recoverable', 'قابل للاسترداد') + ')' : ' (' + t('payable', 'مستحق') + ')') + '</div>';
        var detail = res.detail || [];
        if (detail.length === 0) { tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">' + t('No movements in selected period', 'لا توجد حركات في الفترة المحددة') + '</td></tr>'; return; }
        var html = '';
        detail.forEach(function(row) {
          html += '<tr><td>' + (row.date || '') + '</td><td>' + (row.account_label || row.account || '') + '</td><td>' + (row.description || '') + '</td><td class="text-right">' + fmt(row.debit) + '</td><td class="text-right">' + fmt(row.credit) + '</td></tr>';
        });
        tbody.innerHTML = html;
      } else {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">' + (res ? res.message : 'Error') + '</td></tr>';
      }
    } catch (err) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty-msg">' + (err && err.message ? err.message : String(err)) + '</td></tr>';
    }
  };

  window.settleVatForPeriod = async function() {
    var fromEl = document.getElementById('vatFrom');
    var toEl = document.getElementById('vatTo');
    var accEl = document.getElementById('vatSettleAccount');
    if (!fromEl || !toEl || !toEl.value) { if (window.showNotification) window.showNotification('error', '', t('Set From and To dates for the period to settle.', 'حدد تاريخ From و To لفترة التسوية.')); return; }
    if (typeof window.pySettleVatForPeriod !== 'function') { if (window.showNotification) window.showNotification('error', '', 'Settle VAT not available'); return; }
    try {
      var res = await window.pySettleVatForPeriod(fromEl.value, toEl.value, accEl ? accEl.value : null);
      if (res && res.success) {
        if (window.showNotification) window.showNotification('success', '', res.message || (res.settled ? t('VAT settled.', 'تمت تسوية الضريبة.') : 'OK'));
        if (window.loadVatReport) loadVatReport();
      } else {
        if (window.showNotification) window.showNotification('error', '', res ? res.message : 'Error');
      }
    } catch (err) {
      if (window.showNotification) window.showNotification('error', '', String(err));
    }
  };

  window.postOpeningBalancesToLedger = async function() {
    var yearEl = document.getElementById('obYear');
    var year = yearEl ? parseInt(yearEl.value, 10) : new Date().getFullYear();
    if (!year || year < 2020 || year > 2030) {
      if (window.showNotification) window.showNotification('error', '', t('Enter a valid year (2020–2030)', 'أدخل سنة صحيحة (2020–2030)'));
      return;
    }
    if (typeof window.pyPostOpeningBalances !== 'function') {
      if (window.showNotification) window.showNotification('error', '', t('Post Opening Balances not available', 'ترحيل الأرصدة الافتتاحية غير متاح'));
      return;
    }
    try {
      var res = await window.pyPostOpeningBalances(year);
      if (res && res.success) {
        if (window.showNotification) window.showNotification('success', '', res.message || t('Opening balances posted to ledger. They will now appear in General Ledger and Cash & Bank Statement.', 'تم ترحيل الأرصدة الافتتاحية إلى الدفتر. ستظهر في دفتر الأستاذ وكشف البنك.'));
      } else {
        if (window.showNotification) window.showNotification('error', '', res ? res.message : 'Error');
      }
    } catch (err) {
      if (window.showNotification) window.showNotification('error', '', String(err && err.message ? err.message : err));
    }
  };

  window.loadOpeningBalances = async function() {
    var tbody = document.getElementById('openingBody');
    if (!tbody) return;
    if (typeof window.pyGetOpeningBalances !== 'function') return;
    tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">' + t('Loading...', 'جاري التحميل...') + '</td></tr>';
    try {
      var res = await window.pyGetOpeningBalances();
      if (res && res.success) {
        var data = res.data || [];
        if (data.length === 0) { tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">' + t('No opening balances set', 'لا توجد ارصدة افتتاحية') + '</td></tr>'; return; }
        var html = '';
        data.forEach(function(row) {
          var amt = parseFloat(row.opening_balance || row.amount || 0);
          html += '<tr><td>' + (row.name || '') + '</td>';
          html += '<td>' + (row.type || '') + '</td>';
          html += '<td class="text-right" style="font-weight:600;">' + fmt(amt) + '</td>';
          html += '<td><button class="btn-delete" data-n="' + (row.name || '') + '" data-t="' + (row.type || '') + '" onclick="var _b=this;withButtonLock(_b, function(){ return delOpeningBalance(_b.dataset.n, _b.dataset.t); })" data-loading-text="...">' + t('Del', 'حذف') + '</button></td></tr>';
        });
        tbody.innerHTML = html;
      } else {
        tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">' + (res ? res.message : 'Error') + '</td></tr>';
      }
    } catch (err) {
      if (tbody) tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">' + (err && err.message ? err.message : String(err)) + '</td></tr>';
    }
  };

  window.populateAdvStmtEntities = async function() {
    var entityType = document.getElementById('advStmtEntityType');
    var entitySelect = document.getElementById('advStmtEntity');
    if (!entityType || !entitySelect) return;
    entitySelect.innerHTML = '<option value="">All (Consolidated)</option>';
    var isCustomer = entityType.value === 'customer';
    if (typeof (isCustomer ? window.pyGetCustomerSummary : window.pyGetSupplierSummary) !== 'function') return;
    try {
      var res = await (isCustomer ? window.pyGetCustomerSummary() : window.pyGetSupplierSummary());
      if (res && res.success) {
        var data = res.data || [];
        data.forEach(function(r) {
          var id = isCustomer ? (r.client_name || '') : (r.supplier_id || r.supplier_name || '');
          var name = isCustomer ? (r.client_name || '') : (r.supplier_name || r.supplier_id || '');
          if (id || name) {
            var opt = document.createElement('option');
            opt.value = id;
            opt.textContent = name;
            entitySelect.appendChild(opt);
          }
        });
      }
    } catch (e) {}
  };

  window.loadAdvancedStatement = async function() {
    var tbody = document.getElementById('advStmtBody');
    var entityType = document.getElementById('advStmtEntityType');
    var entitySelect = document.getElementById('advStmtEntity');
    var fromEl = document.getElementById('advStmtFrom');
    var toEl = document.getElementById('advStmtTo');
    var invoiceEl = document.getElementById('advStmtInvoice');
    var txTypeEl = document.getElementById('advStmtTxType');
    var agingEl = document.getElementById('advStmtAging');
    if (!tbody || typeof window.pyGetAdvancedAccountStatement !== 'function') return;
    tbody.innerHTML = '<tr><td colspan="7" class="empty-msg">' + t('Loading...', 'جاري التحميل...') + '</td></tr>';
    var filters = {};
    filters['entity_type'] = entityType ? entityType.value : 'customer';
    filters['entity_id'] = entitySelect && entitySelect.value ? entitySelect.value : null;
    filters['date_from'] = fromEl && fromEl.value ? fromEl.value : null;
    filters['date_to'] = toEl && toEl.value ? toEl.value : null;
    filters['invoice_id'] = invoiceEl && invoiceEl.value ? invoiceEl.value : null;
    filters['transaction_type'] = txTypeEl && txTypeEl.value ? txTypeEl.value : null;
    filters['include_aging'] = agingEl ? agingEl.checked : false;
    function esc(s) {
      if (s == null || s === undefined) return '';
      var x = String(s);
      return x.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    try {
      var res = await window.pyGetAdvancedAccountStatement(filters);
      if (res && res.success) {
        document.getElementById('advStmtTitle').textContent = 'Advanced Account Statement - ' + (res.entity_name || '');
        var fmt = window.fmt || function(n) { return (n != null && !isNaN(n)) ? Number(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : ''; };
        var ob = parseFloat(res.opening_balance) || 0;
        var cb = parseFloat(res.closing_balance) || 0;
        var openEl = document.getElementById('advStmtOpening');
        var closeEl = document.getElementById('advStmtClosing');
        if (openEl) openEl.textContent = fmt(ob);
        if (closeEl) closeEl.textContent = fmt(cb);
        var agingRow = document.getElementById('advStmtAgingRow');
        if (res.aging && agingRow) {
          agingRow.style.display = '';
          var a = res.aging;
          if (document.getElementById('advStmtAgingCurrent')) document.getElementById('advStmtAgingCurrent').textContent = fmt(a.current);
          if (document.getElementById('advStmtAging30')) document.getElementById('advStmtAging30').textContent = fmt(a['30']);
          if (document.getElementById('advStmtAging60')) document.getElementById('advStmtAging60').textContent = fmt(a['60']);
          if (document.getElementById('advStmtAging90')) document.getElementById('advStmtAging90').textContent = fmt(a['90+']);
          if (document.getElementById('advStmtAgingTotal')) document.getElementById('advStmtAgingTotal').textContent = fmt(a.total_outstanding);
        } else if (agingRow) agingRow.style.display = 'none';
        if (res.summary && res.summary.length) {
          var html = '';
          res.summary.forEach(function(r) {
            html += '<tr><td></td><td></td><td>' + esc(r.entity_name) + '</td><td>Summary</td>';
            html += '<td class="text-right">' + fmt(r.period_debit) + '</td><td class="text-right">' + fmt(r.period_credit) + '</td>';
            html += '<td class="text-right">' + fmt(r.closing_balance) + '</td></tr>';
          });
          tbody.innerHTML = html;
        } else {
          var rows = res.rows || [];
          if (rows.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-msg">No transactions in period</td></tr>';
          } else {
            var html = '';
            rows.forEach(function(r) {
              var d = r.date ? (typeof r.date === 'string' ? r.date : (r.date.year + '-' + String(r.date.month).padStart(2,'0') + '-' + String(r.date.day).padStart(2,'0')) : '');
              html += '<tr><td>' + esc(d) + '</td><td>' + esc(r.reference_type) + '</td><td>' + esc(r.reference_id) + '</td><td>' + esc(r.description) + '</td>';
              html += '<td class="text-right">' + fmt(r.debit) + '</td><td class="text-right">' + fmt(r.credit) + '</td><td class="text-right">' + fmt(r.balance_after_transaction) + '</td></tr>';
            });
            tbody.innerHTML = html;
          }
        }
      } else {
        tbody.innerHTML = '<tr><td colspan="7" class="empty-msg">' + esc(res ? res.message : 'Error') + '</td></tr>';
      }
    } catch (err) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty-msg">' + esc(err && err.message ? err.message : String(err)) + '</td></tr>';
    }
  };

  var advStmtEntityTypeEl = document.getElementById('advStmtEntityType');
  if (advStmtEntityTypeEl) advStmtEntityTypeEl.addEventListener('change', function() {
    if (window.populateAdvStmtEntities) populateAdvStmtEntities();
  });

  window.submitInternalTransfer = async function() {
    var fromCode = document.getElementById('transferFrom') && document.getElementById('transferFrom').value;
    var toCode = document.getElementById('transferTo') && document.getElementById('transferTo').value;
    var amount = parseFloat(document.getElementById('transferAmount') && document.getElementById('transferAmount').value) || 0;
    var d = document.getElementById('transferDate') && document.getElementById('transferDate').value;
    var desc = (document.getElementById('transferDesc') && document.getElementById('transferDesc').value) || 'Internal transfer';
    if (!fromCode || !toCode) { if (window.showNotification) window.showNotification('error', '', t('Select From and To accounts', 'اختر من وحساب الوجهة')); return; }
    if (fromCode === toCode) { if (window.showNotification) window.showNotification('error', '', t('From and To must be different', 'من والوجهة يجب أن يكونا مختلفين')); return; }
    if (amount <= 0) { if (window.showNotification) window.showNotification('error', '', t('Enter amount', 'أدخل المبلغ')); return; }
    if (!d) { if (window.showNotification) window.showNotification('error', '', t('Select date', 'اختر التاريخ')); return; }
    if (typeof window.pyCreateTreasuryTransaction !== 'function') { if (window.showNotification) window.showNotification('error', '', 'Treasury not available'); return; }
    try {
      var res = await window.pyCreateTreasuryTransaction('internal_transfer', amount, d, desc, fromCode, toCode);
      if (res && res.success) {
        if (window.showNotification) window.showNotification('success', '', t('Transfer recorded', 'تم تسجيل التحويل'));
        if (window.loadTreasury) loadTreasury();
      } else {
        if (window.showNotification) window.showNotification('error', '', res ? res.message : 'Error');
      }
    } catch (err) {
      if (window.showNotification) window.showNotification('error', '', String(err && err.message ? err.message : err));
    }
  };

  window.loadCashFlow = async function() {
    var fromEl = document.getElementById('cashflowFrom');
    var toEl = document.getElementById('cashflowTo');
    var tbody = document.getElementById('cashflowBody');
    if (!tbody || !fromEl || !toEl) return;
    if (typeof window.pyGetCashFlowReport !== 'function') return;
    tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">' + t('Loading...', 'جاري التحميل...') + '</td></tr>';
    try {
      var res = await window.pyGetCashFlowReport(fromEl.value, toEl.value);
      if (res && res.success) {
        var rows = [];
        (res.operating && res.operating.items || []).forEach(function(i) { rows.push({ section: 'Operating', label: i.label, amount: i.amount }); });
        (res.investing && res.investing.items || []).forEach(function(i) { rows.push({ section: 'Investing', label: i.label, amount: i.amount }); });
        (res.financing && res.financing.items || []).forEach(function(i) { rows.push({ section: 'Financing', label: i.label, amount: i.amount }); });
        if (rows.length === 0) { tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">' + t('No data in period', 'لا توجد بيانات') + '</td></tr>'; return; }
        var html = '';
        rows.forEach(function(r) {
          html += '<tr><td>' + (r.section || '') + '</td><td>' + (r.label || '') + '</td><td class="text-right">' + fmt(r.amount) + '</td></tr>';
        });
        tbody.innerHTML = html;
      } else {
        tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">' + (res ? res.message : 'Error') + '</td></tr>';
      }
    } catch (err) {
      tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">' + String(err && err.message ? err.message : err) + '</td></tr>';
    }
  };

  window.exportReport = async function(reportName, format) {
    var filters = {};
    if (reportName === 'trial_balance') {
      var fromEl = document.getElementById('trialFrom'); var toEl = document.getElementById('trialTo');
      if (fromEl) filters.date_from = fromEl.value; if (toEl) filters.date_to = toEl.value;
    } else if (reportName === 'income_statement') {
      var fromEl = document.getElementById('incomeFrom'); var toEl = document.getElementById('incomeTo');
      if (fromEl) filters.date_from = fromEl.value; if (toEl) filters.date_to = toEl.value;
    } else if (reportName === 'cash_flow') {
      var fromEl = document.getElementById('cashflowFrom'); var toEl = document.getElementById('cashflowTo');
      if (fromEl) filters.date_from = fromEl.value; if (toEl) filters.date_to = toEl.value;
    } else if (reportName === 'balance_sheet') {
      var d = document.getElementById('balanceDate');
      if (d) filters.as_of_date = d.value;
    } else if (reportName === 'contract_profitability') {
      filters = {};
    } else if (reportName === 'expenses') {
      var fromEl = document.getElementById('expFrom'); var toEl = document.getElementById('expTo'); var catEl = document.getElementById('expFilterCat');
      if (fromEl) filters.date_from = fromEl.value; if (toEl) filters.date_to = toEl.value; if (catEl && catEl.value) filters.category = catEl.value;
    } else if (reportName === 'general_ledger') {
      var accEl = document.getElementById('ledgerAccount'); var fromEl = document.getElementById('ledgerFrom'); var toEl = document.getElementById('ledgerTo');
      if (accEl && accEl.value) filters.account_code = accEl.value; if (fromEl) filters.date_from = fromEl.value; if (toEl) filters.date_to = toEl.value;
    } else if (reportName === 'exchange_rates' || reportName === 'treasury_summary') {
      filters = {};
    } else if (reportName === 'cash_bank_statement') {
      var accEl = document.getElementById('cashbankAccount'); var fromEl = document.getElementById('cashbankFrom'); var toEl = document.getElementById('cashbankTo');
      if (accEl && accEl.value) filters.account_code = accEl.value; if (fromEl) filters.date_from = fromEl.value; if (toEl) filters.date_to = toEl.value;
    } else if (reportName === 'vat_report') {
      var asOf = document.getElementById('vatAsOf'); var fromEl = document.getElementById('vatFrom'); var toEl = document.getElementById('vatTo');
      if (asOf && asOf.value) filters.as_of_date = asOf.value; if (fromEl) filters.date_from = fromEl.value; if (toEl) filters.date_to = toEl.value;
    } else if (reportName === 'opening_balances') {
      filters = {};
    } else if (reportName === 'advanced_account_statement') {
      var et = document.getElementById('advStmtEntityType');
      var ent = document.getElementById('advStmtEntity');
      var fromEl = document.getElementById('advStmtFrom');
      var toEl = document.getElementById('advStmtTo');
      var inv = document.getElementById('advStmtInvoice');
      var tx = document.getElementById('advStmtTxType');
      var aging = document.getElementById('advStmtAging');
      if (et) filters.entity_type = et.value;
      if (ent && ent.value) filters.entity_id = ent.value;
      if (fromEl && fromEl.value) filters.date_from = fromEl.value;
      if (toEl && toEl.value) filters.date_to = toEl.value;
      if (inv && inv.value) filters.invoice_id = inv.value;
      if (tx && tx.value) filters.transaction_type = tx.value;
      if (aging) filters.include_aging = aging.checked;
    }
    if (typeof window.pyExportReport !== 'function') { if (window.showNotification) window.showNotification('error', '', 'Export not available'); return; }
    try {
      var res = await window.pyExportReport(reportName, filters, format);
      if (res && res.success && res.content) {
        var filename = res.filename || reportName + (format === 'pdf' ? '.pdf' : format === 'excel' ? '.xlsx' : '.csv');
        if (format === 'csv' && typeof res.content === 'string') {
          var a = document.createElement('a');
          a.href = 'data:text/csv;charset=utf-8,' + encodeURIComponent(res.content);
          a.download = filename;
          a.click();
        } else if ((format === 'pdf' || format === 'excel') && typeof res.content === 'string' && res.content.length > 0) {
          try {
            var b64 = res.content.replace(/\s/g, '');
            var bin = atob(b64);
            var arr = new Uint8Array(bin.length);
            for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
            var mime = format === 'pdf' ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
            var blob = new Blob([arr], { type: mime });
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = filename;
            a.click();
            URL.revokeObjectURL(url);
          } catch (e) {
            if (window.showNotification) window.showNotification('error', '', 'Download failed: ' + (e && e.message ? e.message : String(e)));
          }
        } else {
          if (window.showNotification) window.showNotification('info', '', t('Download may start; check browser.', 'قد يبدأ التحميل؛ تحقق من المتصفح.'));
        }
      } else {
        if (window.showNotification) window.showNotification('error', '', res ? res.message : 'Export failed');
      }
    } catch (err) {
      if (window.showNotification) window.showNotification('error', '', String(err && err.message ? err.message : err));
    }
  };

  window.loadPeriodLocks = async function() {
    var yearEl = document.getElementById('periodYear');
    var tbody = document.getElementById('periodBody');
    if (!tbody || typeof window.pyGetPeriodLocks !== 'function') return;
    var year = yearEl ? parseInt(yearEl.value, 10) : new Date().getFullYear();
    tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">' + t('Loading...', 'جاري التحميل...') + '</td></tr>';
    try {
      var res = await window.pyGetPeriodLocks(year);
      if (res && res.success) {
        var data = res.data || [];
        var months = [1,2,3,4,5,6,7,8,9,10,11,12];
        var byMonth = {};
        data.forEach(function(r) {
          if (r.year === year) byMonth[r.month] = r.locked;
        });
        var html = '';
        months.forEach(function(m) {
          var locked = byMonth[m];
          html += '<tr><td>' + year + '</td><td>' + m + '</td><td>' + (locked ? t('Locked', 'مقفل') : t('Open', 'مفتوح')) + '</td><td>';
          html += locked
            ? '<button class="btn-small" data-y="' + year + '" data-m="' + m + '" onclick="var _b=this;withButtonLock(_b, function(){ return reopenPeriod(_b.dataset.y, _b.dataset.m); })" data-loading-text="...">' + t('Unlock', 'فتح') + '</button>'
            : '<button class="btn-small" data-y="' + year + '" data-m="' + m + '" onclick="var _b=this;withButtonLock(_b, function(){ return lockPeriod(_b.dataset.y, _b.dataset.m); })" data-loading-text="...">' + t('Lock', 'قفل') + '</button>';
          html += '</td></tr>';
        });
        tbody.innerHTML = html;
      } else {
        tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">' + (res ? res.message : 'Error') + '</td></tr>';
      }
    } catch (err) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">' + String(err && err.message ? err.message : err) + '</td></tr>';
    }
  };

  window.lockPeriod = async function(y, m) {
    if (typeof window.pyClosePeriod !== 'function') return;
    try {
      var res = await window.pyClosePeriod(parseInt(y,10), parseInt(m,10));
      if (res && res.success) { if (window.showNotification) window.showNotification('success', '', t('Period locked', 'تم قفل الفترة')); if (window.loadPeriodLocks) loadPeriodLocks(); }
      else { if (window.showNotification) window.showNotification('error', '', res ? res.message : 'Error'); }
    } catch (e) { if (window.showNotification) window.showNotification('error', '', String(e)); }
  };

  window.reopenPeriod = async function(y, m) {
    if (typeof window.pyReopenPeriod !== 'function') return;
    try {
      var res = await window.pyReopenPeriod(parseInt(y,10), parseInt(m,10));
      if (res && res.success) { if (window.showNotification) window.showNotification('success', '', t('Period reopened', 'تم فتح الفترة')); if (window.loadPeriodLocks) loadPeriodLocks(); }
      else { if (window.showNotification) window.showNotification('error', '', res ? res.message : 'Error'); }
    } catch (e) { if (window.showNotification) window.showNotification('error', '', String(e)); }
  };

  window.closeFinancialYear = async function() {
    var yearEl = document.getElementById('periodYear');
    var year = yearEl ? parseInt(yearEl.value, 10) : new Date().getFullYear();
    if (typeof window.pyCloseFinancialYear !== 'function') return;
    try {
      var res = await window.pyCloseFinancialYear(year);
      if (res && res.success) { if (window.showNotification) window.showNotification('success', '', res.message || t('Year closed', 'تم إقفال السنة')); if (window.loadPeriodLocks) loadPeriodLocks(); }
      else { if (window.showNotification) window.showNotification('error', '', res ? res.message : 'Error'); }
    } catch (e) { if (window.showNotification) window.showNotification('error', '', String(e)); }
  };

  window.delOpeningBalance = async function(name, type) {
    var ok = await (window.showConfirm || function(m) { return Promise.resolve(confirm(m)); })(t('Delete opening balance for ' + name + '?', 'حذف الرصيد الافتتاحي لـ ' + name + '؟'));
    if (!ok) return;
    try {
      var res = await window.pyDeleteOpeningBalance(name, type);
      if (res && res.success) {
        if (window.showNotification) window.showNotification('success', '', t('Deleted', 'تم الحذف'));
        loadOpeningBalances();
      } else {
        if (window.showNotification) window.showNotification('error', '', res ? res.message : 'Error');
      }
    } catch (err) {
      if (window.showNotification) window.showNotification('error', '', String(err));
    }
  };

  function waitForBridge() {
    if (window.pyGetTrialBalance && window.pyGetLedgerEntries) {
      applyI18n();
      populateLedgerAccounts();
      if (window.pyGetExchangeRates) loadCurrencyRates();
      if (window.pyGetTreasurySummary) loadTreasury();
      if (window.pyGetOpeningBalances) loadOpeningBalances();
      if (window.populateCashBankAccounts) populateCashBankAccounts();
      if (window.populateOpeningBalanceAccounts) populateOpeningBalanceAccounts();
    } else {
      setTimeout(waitForBridge, 200);
    }
  }
  setTimeout(waitForBridge, 300);
})();

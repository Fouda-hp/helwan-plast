
  (function() {
  // State
  var currentPanel = 'dashboard';
  var clientsPage = 1;
  var quotationsPage = 1;
  var contractsPage = 1;
  var auditPage = 1;
  var selectedUserId = null;
  var searchTimeout = null;
  var pendingUsersData = {};
  var _restoreClientAPI = window.restoreClient;
  var _restoreQuotationAPI = window.restoreQuotation;

  // XSS Protection: escape user data before inserting into HTML
  function escapeHtml(s){if(s==null)return'';return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');}

  // Per-action async busy flags to prevent double-click
  var _adminBusy = {};
  async function withBusy(actionKey, fn) {
    if (_adminBusy[actionKey]) return;
    _adminBusy[actionKey] = true;
    try { return await fn(); }
    finally { _adminBusy[actionKey] = false; }
  }

  // ============================================
  // NOTIFICATION SYSTEM
  // ============================================
  window.showNotification = function(type, title, message, duration) {
  duration = duration || 5000;
  var container = document.getElementById('notificationContainer');
  if (!container) return;

  var icons = { 'success': '✓', 'error': '✕', 'warning': '⚠', 'info': 'ℹ' };

  var toast = document.createElement('div');
  toast.className = 'notification-toast ' + type;
  toast.innerHTML =
  '<span class="icon">' + icons[type] + '</span>' +
  '<div class="content">' +
  '<div class="title">' + escapeHtml(title) + '</div>' +
  '<div class="message">' + escapeHtml(message) + '</div>' +
  '</div>' +
  '<button class="close-btn" onclick="this.parentElement.remove()">×</button>';

  container.appendChild(toast);

  setTimeout(function() {
  if (toast.parentElement) {
  toast.style.animation = 'slideOut 0.3s ease';
  setTimeout(function() { if (toast.parentElement) toast.remove(); }, 300);
  }
  }, duration);
  };

  // ============================================
  // INIT
  // ============================================
  function init() {
  if (window.__adminPanelInitDone) return;
  window.__adminPanelInitDone = true;

  console.log('=== Initializing Admin Panel ===');

  // Check panels exist
  console.log('Checking panels:');
  var panels = ['dashboard', 'pending', 'users', 'clients', 'quotations', 'contracts', 'settings', 'audit'];
  panels.forEach(function(name) {
  var panel = document.getElementById(name + '-panel');
  if (panel) {
  console.log('✓ Panel exists:', name);
  } else {
  console.error('✗ Panel MISSING:', name);
  }
  });

  initUser();
  initNavigation();
  setupLogoutButton();

  console.log('Waiting for Python bridge...');
  setTimeout(function() {
  console.log('Loading dashboard...');
  if (window.loadDashboard) {
  window.loadDashboard();
  } else {
  console.warn('loadDashboard not available yet');
  }
  }, 500);
  }

  // Test function - can be called from console
  window.testPanel = function(panelName) {
  console.log('=== Testing panel:', panelName);

  // Hide all
  document.querySelectorAll('.panel').forEach(function(p) {
  p.classList.remove('active');
  p.style.display = 'none';
  });

  // Show target
  var panel = document.getElementById(panelName + '-panel');
  if (panel) {
  panel.classList.add('active');
  panel.style.display = 'block';
  console.log('✓ Panel shown successfully');
  } else {
  console.error('✗ Panel not found');
  }
  };

  function initUser() {
  var name = sessionStorage.getItem('user_name') || localStorage.getItem('user_name') || 'Admin';
  var userNameEl = document.getElementById('userName');
  if (userNameEl) {
  userNameEl.textContent = name;
  }
  }

  // ============================================
  // NAVIGATION
  // ============================================
  function initNavigation() {
  if (window.__adminNavInitDone) return;
  window.__adminNavInitDone = true;

  console.log('Setting up navigation...');

  // Get all nav items
  var navItems = document.querySelectorAll('.nav-item[data-panel]');
  console.log('Found nav items:', navItems.length);

  navItems.forEach(function(item) {
  var panel = item.getAttribute('data-panel');
  console.log('Setting up nav item for panel:', panel);

  // Remove any existing listeners
  item.onclick = null;

  // Add event listener
  item.addEventListener('click', function(e) {
  e.preventDefault();
  e.stopPropagation();

  console.log('>>> NAV ITEM CLICKED:', panel);

  // Update active states on ALL nav items
  document.querySelectorAll('.nav-item[data-panel]').forEach(function(i) {
  i.classList.remove('active');
  });

  // Add active to current item and its mobile counterpart
  document.querySelectorAll('.nav-item[data-panel="' + panel + '"]').forEach(function(i) {
  i.classList.add('active');
  });

  // Hide all panels
  document.querySelectorAll('.panel').forEach(function(p) {
  p.classList.remove('active');
  p.style.display = 'none';
  });

  // Show selected panel
  var panelEl = document.getElementById(panel + '-panel');
  if (panelEl) {
  panelEl.classList.add('active');
  panelEl.style.display = 'block';
  console.log('>>> Panel shown:', panel);
  } else {
  console.error('>>> Panel NOT found:', panel + '-panel');
  }

  currentPanel = panel;

  // Load data
  console.log('>>> Loading data for:', panel);
  try {
  if (panel === 'dashboard') loadDashboard();
  else if (panel === 'pending') loadPendingUsers();
  else if (panel === 'users') loadAllUsers();
  else if (panel === 'clients') loadClients();
  else if (panel === 'quotations') loadQuotations();
  else if (panel === 'contracts') loadContracts();
  else if (panel === 'audit') loadAuditLogs();
  else if (panel === 'settings') loadSettings();
  } catch(err) {
  console.error('>>> Error loading panel data:', err);
  }

  // Close mobile menu
  var mobileMenu = document.getElementById('mobileMenu');
  if (mobileMenu) {
  mobileMenu.classList.remove('open');
  }
  });
  });

  console.log('Navigation setup complete!');
  }

  // ============================================
  // LAUNCHER
  // ============================================
  window.goToLauncher = function() {
  console.log('Navigating to launcher...');
  window.location.hash = '#launcher';
  };

  // ============================================
  // DASHBOARD
  // ============================================
  window.loadDashboard = async function() {
  function setStatText(id, value) {
  var el = document.getElementById(id);
  if (el) el.textContent = value;
  }

  try {
  if (!window.getDashboardStats) {
  console.log('Waiting for bridge functions...');
  setTimeout(loadDashboard, 500);
  return;
  }

  // Parallel fetch: all 3 calls fire at once, then we apply results
  var statsP = window.getDashboardStats();
  var pendingP = window.getPendingUsers ? window.getPendingUsers() : Promise.resolve(null);
  var acctP = window.getAccountingDashboardStats ? window.getAccountingDashboardStats() : Promise.resolve(null);

  var results = await Promise.all([
    statsP.catch(function(e){ console.error('Stats error:', e); return null; }),
    pendingP.catch(function(e){ console.error('Pending error:', e); return null; }),
    acctP.catch(function(e){ console.error('Acct error:', e); return null; })
  ]);

  var stats = results[0];
  var pending = results[1];
  var acct = results[2];

  if (stats) {
  setStatText('statClients', (stats.total_clients || 0).toLocaleString());
  setStatText('statQuotations', (stats.total_quotations || 0).toLocaleString());
  setStatText('statValue', (stats.total_value || 0).toLocaleString());
  setStatText('statMonthly', (stats.this_month_quotations || 0).toLocaleString());
  }

  if (pending && pending.success && pending.users) {
  setStatText('pendingBadge', pending.users.length);
  }

  if (acct && acct.success) {
    var inv = acct.inventory || {};
    var pi = acct.purchase_invoices || {};
    var prof = acct.profitability || {};
    setStatText('statInventory', (inv.total_count || 0).toLocaleString());
    setStatText('statPurchaseInv', (pi.total_count || 0).toLocaleString());
    setStatText('statCOGS', '$' + (prof.total_cogs || 0).toLocaleString());
    setStatText('statProfit', '$' + (prof.gross_profit || 0).toLocaleString());
    var profEl = document.getElementById('statProfit');
    if (profEl) profEl.style.color = (prof.gross_profit || 0) >= 0 ? '#2e7d32' : '#c62828';
    renderDashCharts(acct);
  }

  } catch (e) {
  console.error('Dashboard error:', e);
  setStatText('statClients', '0');
  setStatText('statQuotations', '0');
  setStatText('statValue', '0');
  setStatText('statMonthly', '0');
  }
};
function renderDashCharts(acct) {
  try {
    var mp = acct.monthly_purchases || [];
    var ms = acct.monthly_sales || [];
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    var purchData = months.map(function(_,i){ return mp[i] || 0; });
    var salesData = months.map(function(_,i){ return ms[i] || 0; });
    var ctx1 = document.getElementById('chartPurchSales');
    if (ctx1 && typeof Chart !== 'undefined') {
      if (window._chartPS) window._chartPS.destroy();
      window._chartPS = new Chart(ctx1, {type:'bar',data:{labels:months,datasets:[{label:'Purchases',data:purchData,backgroundColor:'rgba(102,126,234,0.7)'},{label:'Sales',data:salesData,backgroundColor:'rgba(76,175,80,0.7)'}]},options:{responsive:true,plugins:{legend:{position:'bottom'}},scales:{y:{beginAtZero:true}}}});
    }
    var ts = acct.top_suppliers || [];
    var ctx2 = document.getElementById('chartTopSuppliers');
    if (ctx2 && typeof Chart !== 'undefined' && ts.length > 0) {
      if (window._chartTS) window._chartTS.destroy();
      var colors = ['#667eea','#764ba2','#ff9800','#4caf50','#f44336'];
      window._chartTS = new Chart(ctx2, {type:'doughnut',data:{labels:ts.map(function(s){return s.name;}),datasets:[{data:ts.map(function(s){return s.total;}),backgroundColor:colors.slice(0,ts.length)}]},options:{responsive:true,plugins:{legend:{position:'bottom'}}}});
    }
  } catch(ce) { console.log('Chart render error:', ce); }
}

  // ============================================
  // PENDING USERS
  // ============================================
  window.loadPendingUsers = async function() {
  var container = document.getElementById('pendingContent');
  container.innerHTML = '<div style="text-align:center;padding:30px;"><div class="hp-code-loader" style="font-size:1.5em;font-weight:900;"><span>&lt;</span><span>LOADING...</span><span>/&gt;</span></div></div>';

  try {
  var result = await window.getPendingUsers();
  if (!result.success) {
  container.innerHTML = '<div class="empty-state"><h4>' + escapeHtml(result.message) + '</h4></div>';
  return;
  }

  if (result.users.length === 0) {
  container.innerHTML = '<div class="empty-state"><h4>No pending approvals</h4><p>All users have been reviewed</p></div>';
  pendingUsersData = {};
  return;
  }

  pendingUsersData = {};
  result.users.forEach(function(u) { pendingUsersData[u.user_id] = u; });

  var html = '<div class="table-scroll"><table class="data-table"><thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Registered</th><th>Actions</th></tr></thead><tbody>';
  result.users.forEach(function(u) {
  html += '<tr>';
  html += '<td>' + escapeHtml(u.full_name) + '</td>';
  html += '<td>' + escapeHtml(u.email) + '</td>';
  html += '<td>' + escapeHtml(u.phone || '-') + '</td>';
  html += '<td>' + escapeHtml(u.created_at.split('T')[0]) + '</td>';
  html += '<td class="actions">';
  html += '<button class="btn-sm approve" data-action="approve" data-uid="' + escapeHtml(u.user_id) + '" style="background:#e8f5e9;color:#2e7d32;">✓ Approve</button>';
  html += '<button class="btn-sm reject" data-action="reject" data-uid="' + escapeHtml(u.user_id) + '">✕ Reject</button>';
  html += '</td></tr>';
  });
  html += '</tbody></table></div>';
  container.innerHTML = html;
  container.querySelectorAll('[data-action]').forEach(function(btn){
    btn.addEventListener('click', function(){
      var action = this.getAttribute('data-action');
      var uid = this.getAttribute('data-uid');
      if(action==='approve') showApprovalModal(uid);
      else if(action==='reject') rejectUserAction(uid);
    });
  });
  } catch (e) {
  console.error('loadPendingUsers:', e);
  container.innerHTML = '<div class="empty-state"><h4>Error loading users</h4></div>';
  }
  };

  // ============================================
  // APPROVAL MODAL FUNCTIONS
  // ============================================
  window.showApprovalModal = function(userId) {
  var user = pendingUsersData[userId];
  if (!user) {
  showNotification('error', 'Error', 'User data not found');
  return;
  }
  selectedUserId = userId;
  document.getElementById('approvalUserName').textContent = user.full_name;
  document.getElementById('approvalUserEmail').textContent = user.email;
  document.getElementById('approvalUserPhone').textContent = user.phone || 'Not provided';
  document.getElementById('approvalUserDate').textContent = user.created_at.split('T')[0];
  document.getElementById('approvalRole').value = 'sales';
  updateRolePermissions();
  document.getElementById('approvalModal').classList.add('show');
  };

  window.updateRolePermissions = function() {
  var role = document.getElementById('approvalRole').value;
  var permissions = {
  'viewer': ['View all records'],
  'sales': ['View all records', 'Create new records', 'Edit own records'],
  'manager': ['View all records', 'Create records', 'Edit all records', 'Export data', 'Delete own records'],
  'admin': ['Full access to all features', 'Manage users', 'System settings', 'Audit logs']
  };
  var list = document.getElementById('rolePermissionsList');
  list.innerHTML = '';
  (permissions[role] || []).forEach(function(perm) {
  list.innerHTML += '<li>' + perm + '</li>';
  });
  };

  window.confirmApproval = async function() {
  await withBusy('approve', async function() {
    var role = document.getElementById('approvalRole').value;
    closeModal('approvalModal');
    showNotification('info', 'Processing', 'Approving user...');

    try {
    var result = await window.approveUserWithRole(selectedUserId, role);
    if (result.success) {
    showNotification('success', 'User Approved!', 'Role: ' + role.charAt(0).toUpperCase() + role.slice(1));
    loadPendingUsers();
    loadDashboard();
    } else {
    showNotification('error', 'Error', result.message);
    }
    } catch (e) {
    console.error('confirmApproval:', e);
    showNotification('error', 'Error', 'Failed to approve user');
    }
  });
  };

  window.rejectUserAction = async function(userId) {
  var user = pendingUsersData[userId];
  var userName = user ? user.full_name : 'this user';
  if (!confirm('Are you sure you want to reject ' + userName + '?\nThis action cannot be undone.')) return;

  await withBusy('reject_' + userId, async function() {
    showNotification('info', 'Processing', 'Rejecting user...');
    try {
    var result = await window.rejectUserAPI(userId);
    if (result.success) {
    showNotification('success', 'User Rejected', userName + ' has been removed');
    loadPendingUsers();
    loadDashboard();
    } else {
    showNotification('error', 'Error', result.message);
    }
    } catch (e) {
    console.error('rejectUserAction:', e);
    showNotification('error', 'Error', 'Failed to reject user');
    }
  });
  };

  // ============================================
  // ALL USERS
  // ============================================
  window.loadAllUsers = async function() {
  var container = document.getElementById('usersContent');
  container.innerHTML = '<div style="text-align:center;padding:30px;"><div class="hp-code-loader" style="font-size:1.5em;font-weight:900;"><span>&lt;</span><span>LOADING...</span><span>/&gt;</span></div></div>';

  try {
  var result = await window.getAllUsers();
  if (!result.success) {
  container.innerHTML = '<div class="empty-state"><h4>' + escapeHtml(result.message) + '</h4></div>';
  return;
  }

  if (result.users.length === 0) {
  container.innerHTML = '<div class="empty-state"><h4>No users found</h4></div>';
  return;
  }

  var html = '<div class="table-scroll"><table class="data-table"><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Last Login</th><th>OTP</th><th>Passkey</th><th>Actions</th></tr></thead><tbody>';
  result.users.forEach(function(u) {
  var status = u.is_approved ? (u.is_active ? 'active' : 'inactive') : 'pending';
  html += '<tr>';
  html += '<td>' + escapeHtml(u.full_name) + '</td>';
  html += '<td>' + escapeHtml(u.email) + '</td>';
  html += '<td>' + escapeHtml(u.role) + '</td>';
  html += '<td><span class="status ' + status + '">' + status.charAt(0).toUpperCase() + status.slice(1) + '</span></td>';
  html += '<td>' + escapeHtml(u.last_login === 'Never' ? 'Never' : u.last_login.split('T')[0]) + '</td>';
  var om = (u.otp_method || '');
  html += '<td><select class="otp-method-select" data-email="' + escapeHtml(u.email || '') + '" onchange="updateUserOtpMethod(this)" style="padding:6px;border:1px solid #ddd;border-radius:6px;font-size:13px;min-width:120px;">';
  html += '<option value=""' + (om === '' ? ' selected' : '') + '>Default</option>';
  html += '<option value="email"' + (om === 'email' ? ' selected' : '') + '>Email</option>';
  html += '<option value="sms"' + (om === 'sms' ? ' selected' : '') + '>SMS</option>';
  html += '<option value="whatsapp"' + (om === 'whatsapp' ? ' selected' : '') + '>WhatsApp</option>';
  html += '<option value="authenticator"' + (om === 'authenticator' ? ' selected' : '') + '>Authenticator</option>';
  html += '</select></td>';
  html += '<td><button class="btn-sm edit" data-action="passkey" data-email="' + escapeHtml(u.email || '') + '" data-name="' + escapeHtml(u.full_name) + '" style="white-space:nowrap;">🔐 Passkeys</button></td>';
  html += '<td class="actions">';
  html += '<button class="btn-sm edit" data-action="role" data-uid="' + escapeHtml(u.user_id) + '" data-role="' + escapeHtml(u.role) + '">Role</button>';
  html += '<button class="btn-sm edit" data-action="password" data-uid="' + escapeHtml(u.user_id) + '">Password</button>';
  if (u.is_approved) {
  html += '<button class="btn-sm ' + (u.is_active ? 'reject' : 'approve') + '" data-action="toggle" data-uid="' + escapeHtml(u.user_id) + '">' + (u.is_active ? 'Disable' : 'Enable') + '</button>';
  }
  html += '<button class="btn-sm reject" data-action="deleteuser" data-uid="' + escapeHtml(u.user_id) + '" data-name="' + escapeHtml(u.full_name) + '">Delete</button>';
  html += '</td></tr>';
  });
  html += '</tbody></table></div>';
  container.innerHTML = html;
  container.querySelectorAll('[data-action]').forEach(function(btn){
    btn.addEventListener('click', function(){
      var action = this.getAttribute('data-action');
      var uid = this.getAttribute('data-uid');
      if(action==='role') showRoleModal(uid, this.getAttribute('data-role'));
      else if(action==='password') showPasswordModal(uid);
      else if(action==='toggle') toggleActive(uid);
      else if(action==='deleteuser') confirmDeleteUser(uid, this.getAttribute('data-name'));
      else if(action==='passkey') showPasskeyModal(this.getAttribute('data-email'), this.getAttribute('data-name'));
    });
  });
  } catch (e) {
  console.error('loadAllUsers:', e);
  container.innerHTML = '<div class="empty-state"><h4>Error loading users</h4></div>';
  }
  };

  window.updateUserOtpMethod = async function(selectEl) {
  var email = selectEl.getAttribute('data-email');
  var method = (selectEl.value || '').trim();
  if (!email) return;
  if (!window.updateUserOtpMethodAPI) { if (window.showNotification) showNotification('error', 'Error', 'Bridge not ready'); return; }
  try {
  var r = await window.updateUserOtpMethodAPI(email, method);
  if (r && r.success) { if (window.showNotification) showNotification('success', 'Saved', 'OTP method updated'); }
  else { if (window.showNotification) showNotification('error', 'Error', r && r.message ? r.message : 'Failed'); }
  } catch (e) { if (window.showNotification) showNotification('error', 'Error', e.message || 'Failed'); }
  };

  window.showRoleModal = function(userId, currentRole) {
  selectedUserId = userId;
  document.getElementById('newRole').value = currentRole;
  document.getElementById('roleModal').classList.add('show');
  };

  window.showPasswordModal = function(userId) {
  selectedUserId = userId;
  document.getElementById('newPassword').value = '';
  document.getElementById('passwordModal').classList.add('show');
  };

  window.closeModal = function(id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('show');
    if (el.id === 'passkeyModal') el.style.display = 'none';
  };

  window.confirmRoleChange = async function() {
  await withBusy('roleChange', async function() {
    var role = document.getElementById('newRole').value;
    try {
    var result = await window.updateUserRole(selectedUserId, role);
    closeModal('roleModal');
    if (result.success) {
    loadAllUsers();
    } else {
    (window.showNotification&&window.showNotification('error','',result.message));
    }
    } catch (e) {
    console.error('confirmRoleChange:', e);
    closeModal('roleModal');
    (window.showNotification&&window.showNotification('error','','Failed to change role'));
    }
  });
  };

  window.confirmPasswordReset = async function() {
  var password = document.getElementById('newPassword').value;
  if (password.length < 6) {
  if(window.showNotification)window.showNotification('error','','Password must be at least 6 characters');
  return;
  }
  await withBusy('passwordReset', async function() {
    try {
    var result = await window.resetUserPassword(selectedUserId, password);
    closeModal('passwordModal');
    if (result.success) {
    if(window.showNotification)window.showNotification('success','','Password reset successfully');
    } else {
    (window.showNotification&&window.showNotification('error','',result.message));
    }
    } catch (e) {
    console.error('confirmPasswordReset:', e);
    closeModal('passwordModal');
    (window.showNotification&&window.showNotification('error','','Failed to reset password'));
    }
  });
  };

  window.toggleActive = async function(userId) {
  await withBusy('toggle_' + userId, async function() {
    try {
    var result = await window.toggleUserActive(userId);
    if (result.success) {
    loadAllUsers();
    } else {
    (window.showNotification&&window.showNotification('error','',result.message));
    }
    } catch (e) {
    console.error('toggleActive:', e);
    (window.showNotification&&window.showNotification('error','','Failed to toggle user status'));
    }
  });
  };

  window.confirmDeleteUser = function(userId, userName) {
  if (confirm('Are you sure you want to DELETE user "' + userName + '"?\nThis will permanently remove the user and all their data. This action cannot be undone!')) {
  deleteUserPermanently(userId);
  }
  };

  window.deleteUserPermanently = async function(userId) {
  await withBusy('deleteUser_' + userId, async function() {
    try {
    var result = await window.deleteUser(userId);
    if (result.success) {
    showNotification('success', 'User Deleted', 'User has been permanently deleted');
    loadAllUsers();
    loadDashboard();
    } else {
    (window.showNotification&&window.showNotification('error','',result.message));
    }
    } catch (e) {
    console.error('deleteUserPermanently:', e);
    (window.showNotification?window.showNotification('error','','Error deleting user: ' + e.message):null);
    }
  });
  };

  // ============================================
  // PASSKEY MANAGEMENT (Admin → Users)
  // ============================================
  var _passkeyUserEmail = '';

  window.showPasskeyModal = async function(email, userName) {
    _passkeyUserEmail = email;
    // Create modal if not exists
    var modal = document.getElementById('passkeyModal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'passkeyModal';
      modal.style.cssText = 'display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:9999;align-items:center;justify-content:center;';
      modal.innerHTML =
        '<div style="max-width:600px;width:95%;background:#fff;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,0.3);overflow:hidden;">' +
          '<div class="modal-header">' +
            '<h3 id="passkeyModalTitle">🔐 Passkeys</h3>' +
            '<button class="modal-close" onclick="closeModal(\'passkeyModal\')">&times;</button>' +
          '</div>' +
          '<div class="modal-body">' +
            '<div style="background:#e3f2fd;padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:14px;">' +
              '<strong>User:</strong> <span id="passkeyUserInfo">-</span>' +
            '</div>' +
            '<div id="passkeyListContent" style="min-height:60px;"><div style="text-align:center;padding:20px;color:#999;">Loading...</div></div>' +
            '<div style="margin-top:16px;padding-top:16px;border-top:1px solid #e0e0e0;">' +
              '<button class="action-btn" id="registerPasskeyBtn" onclick="registerPasskeyForUser()" style="width:100%;">' +
                '<span style="font-size:18px;">🖐️</span> Register New Passkey (Fingerprint / Face ID)' +
              '</button>' +
              '<p style="margin-top:8px;font-size:12px;color:#999;text-align:center;">' +
                'Note: This registers a passkey on YOUR current device for this user\'s account.' +
              '</p>' +
            '</div>' +
          '</div>' +
          '<div class="modal-footer">' +
            '<button class="filter-btn" onclick="closeModal(\'passkeyModal\')">Close</button>' +
          '</div>' +
        '</div>';
      // Close when clicking overlay background
      modal.addEventListener('click', function(e) { if (e.target === modal) closeModal('passkeyModal'); });
      document.body.appendChild(modal);
    }
    document.getElementById('passkeyUserInfo').textContent = (userName || '') + ' (' + email + ')';
    modal.style.display = 'flex';
    loadPasskeyList(email);
  };

  window.loadPasskeyList = async function(email) {
    var container = document.getElementById('passkeyListContent');
    if (!container) return;
    container.innerHTML = '<div style="text-align:center;padding:20px;color:#999;">Loading passkeys...</div>';

    try {
      if (!window.listUserPasskeys) {
        container.innerHTML = '<div style="text-align:center;padding:20px;color:#e53935;">Bridge not ready. Please refresh the page.</div>';
        return;
      }
      var result = await window.listUserPasskeys(email);
      if (!result || !result.success) {
        container.innerHTML = '<div style="text-align:center;padding:20px;color:#999;">No passkeys found or error: ' + escapeHtml((result && result.error) || 'Unknown') + '</div>';
        return;
      }
      var creds = result.credentials || [];
      if (creds.length === 0) {
        container.innerHTML = '<div style="text-align:center;padding:24px;color:#999;">' +
          '<div style="font-size:40px;margin-bottom:8px;">🔑</div>' +
          '<p>No passkeys registered for this user.</p>' +
          '<p style="font-size:12px;">Register a passkey below to enable biometric login.</p>' +
        '</div>';
        return;
      }
      var html = '<div style="font-size:13px;color:#666;margin-bottom:8px;">' + creds.length + ' passkey(s) registered:</div>';
      html += '<div style="display:flex;flex-direction:column;gap:10px;">';
      creds.forEach(function(c, idx) {
        html += '<div style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;background:#f8f9fa;border-radius:10px;border:1px solid #e0e0e0;">';
        html += '<div style="display:flex;align-items:center;gap:12px;">';
        html += '<span style="font-size:24px;">🔐</span>';
        html += '<div>';
        html += '<div style="font-weight:600;font-size:14px;">' + escapeHtml(c.nickname || 'Passkey ' + (idx + 1)) + '</div>';
        html += '<div style="font-size:12px;color:#999;">Created: ' + escapeHtml(c.created_at ? c.created_at.split('.')[0] : '-') + '</div>';
        html += '<div style="font-size:12px;color:#999;">Last used: ' + escapeHtml(c.last_used === 'Never' || !c.last_used ? 'Never' : c.last_used.split('.')[0]) + '</div>';
        html += '</div></div>';
        html += '<button class="btn-sm reject" data-credprefix="' + escapeHtml(c.credential_id || '') + '" onclick="removeUserPasskeyAction(this)" style="white-space:nowrap;">🗑️ Remove</button>';
        html += '</div>';
      });
      html += '</div>';
      container.innerHTML = html;
    } catch (e) {
      console.error('loadPasskeyList:', e);
      container.innerHTML = '<div style="text-align:center;padding:20px;color:#e53935;">Error loading passkeys: ' + escapeHtml(e.message || 'Unknown') + '</div>';
    }
  };

  window.registerPasskeyForUser = async function() {
    var btn = document.getElementById('registerPasskeyBtn');
    if (!btn) return;
    var origText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span style="font-size:18px;">⏳</span> Waiting for biometric prompt...';

    try {
      if (!window.registerPasskey) {
        showNotification('error', 'Error', 'Passkey bridge not ready. Refresh the page.');
        return;
      }
      var result = await window.registerPasskey();
      if (result && result.success) {
        showNotification('success', 'Success', 'Passkey registered successfully!');
        loadPasskeyList(_passkeyUserEmail);
      } else {
        var errMsg = (result && (result.error || result.message)) || 'Registration failed';
        if (errMsg.indexOf('cancelled') !== -1) {
          showNotification('warning', 'Cancelled', 'Passkey registration was cancelled.');
        } else {
          showNotification('error', 'Error', errMsg);
        }
      }
    } catch (e) {
      console.error('registerPasskeyForUser:', e);
      showNotification('error', 'Error', 'Failed to register passkey: ' + (e.message || 'Unknown error'));
    } finally {
      btn.disabled = false;
      btn.innerHTML = origText;
    }
  };

  window.removeUserPasskeyAction = async function(btnEl) {
    var credPrefix = btnEl.getAttribute('data-credprefix');
    if (!credPrefix) return;
    if (!confirm('Are you sure you want to remove this passkey? The user will not be able to use it for biometric login anymore.')) return;

    btnEl.disabled = true;
    btnEl.textContent = '...';
    try {
      if (!window.removeUserPasskey) {
        showNotification('error', 'Error', 'Bridge not ready');
        return;
      }
      var result = await window.removeUserPasskey(_passkeyUserEmail, credPrefix);
      if (result && result.success) {
        showNotification('success', 'Removed', 'Passkey removed successfully');
        loadPasskeyList(_passkeyUserEmail);
      } else {
        showNotification('error', 'Error', (result && result.error) || 'Failed to remove passkey');
        btnEl.disabled = false;
        btnEl.textContent = '🗑️ Remove';
      }
    } catch (e) {
      console.error('removeUserPasskeyAction:', e);
      showNotification('error', 'Error', 'Failed: ' + (e.message || 'Unknown'));
      btnEl.disabled = false;
      btnEl.textContent = '🗑️ Remove';
    }
  };

  // ============================================
  // CLIENTS
  // ============================================
  window.loadClients = async function(page) {
  clientsPage = page || 1;
  var container = document.getElementById('clientsContent');
  container.innerHTML = '<div style="text-align:center;padding:30px;"><div class="hp-code-loader" style="font-size:1.5em;font-weight:900;"><span>&lt;</span><span>LOADING...</span><span>/&gt;</span></div></div>';

  var search = document.getElementById('clientSearch').value;
  var showDeleted = document.getElementById('showDeletedClients').checked;

  try {
  var result = await window.getAllClients(clientsPage, 15, search, showDeleted);
  renderClientsTable(result, container);
  } catch (e) {
  container.innerHTML = '<div class="empty-state"><h4>Error loading clients</h4></div>';
  }
  };

  function renderClientsTable(result, container) {
  result.data.sort(function(a, b) {
  return Number(a['Client Code']) - Number(b['Client Code']);
  });
  if (result.data.length === 0) {
  container.innerHTML = '<div class="empty-state"><h4>No clients found</h4></div>';
  return;
  }

  var html = '<div class="table-scroll"><table class="data-table"><thead><tr><th>Code</th><th>Name</th><th>Company</th><th>Phone</th><th>Country</th><th>Status</th><th>Actions</th></tr></thead><tbody>';
  result.data.forEach(function(c) {
  var status = c.is_deleted ? 'deleted' : 'active';
  html += '<tr>';
  html += '<td>' + escapeHtml(c['Client Code']) + '</td>';
  html += '<td>' + escapeHtml(c['Client Name']) + '</td>';
  html += '<td>' + escapeHtml(c['Company']) + '</td>';
  html += '<td>' + escapeHtml(c['Phone']) + '</td>';
  html += '<td>' + escapeHtml(c['Country'] || '-') + '</td>';
  html += '<td><span class="status ' + status + '">' + status.charAt(0).toUpperCase() + status.slice(1) + '</span></td>';
  html += '<td class="actions">';
  if (c.is_deleted) {
  html += '<button class="btn-sm restore" data-action="restoreclient" data-code="' + escapeHtml(c['Client Code']) + '">Restore</button>';
  } else {
  html += '<button class="btn-sm delete" data-action="deleteclient" data-code="' + escapeHtml(c['Client Code']) + '">Delete</button>';
  }
  html += '</td></tr>';
  });
  html += '</tbody></table></div>';

  html += '<div class="pagination">';
  html += '<button ' + (result.page <= 1 ? 'disabled' : '') + ' data-action="pageclients" data-page="' + (result.page - 1) + '">Previous</button>';
  html += '<span class="page-info">Page ' + result.page + ' of ' + result.total_pages + ' (' + result.total + ' items)</span>';
  html += '<button ' + (result.page >= result.total_pages ? 'disabled' : '') + ' data-action="pageclients" data-page="' + (result.page + 1) + '">Next</button>';
  html += '</div>';

  container.innerHTML = html;
  container.querySelectorAll('[data-action]').forEach(function(btn){
    btn.addEventListener('click', function(){
      var action = this.getAttribute('data-action');
      if(action==='restoreclient') restoreClient(this.getAttribute('data-code'));
      else if(action==='deleteclient') deleteClient(this.getAttribute('data-code'));
      else if(action==='pageclients') loadClients(parseInt(this.getAttribute('data-page')));
    });
  });
  }

  window.searchClients = function() {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(function() { loadClients(1); }, 300);
  };

  window.deleteClient = async function(code) {
  if (!confirm('Delete this client?')) return;
  await withBusy('deleteClient_' + code, async function() {
    try {
    var result = await window.softDeleteClient(code);
    if (result.success) {
    loadClients(clientsPage);
    } else {
    (window.showNotification&&window.showNotification('error','',result.message));
    }
    } catch (e) {
    console.error('deleteClient:', e);
    (window.showNotification&&window.showNotification('error','','Failed to delete client'));
    }
  });
  };

  window.restoreClient = async function(code) {
  await withBusy('restoreClient_' + code, async function() {
    try {
    var result = _restoreClientAPI ? await _restoreClientAPI(code) : { success: false, message: 'Bridge not ready' };
    if (result.success) {
    loadClients(clientsPage);
    } else {
    (window.showNotification&&window.showNotification('error','',result.message));
    }
    } catch (e) {
    console.error('restoreClient:', e);
    (window.showNotification&&window.showNotification('error','','Failed to restore client'));
    }
  });
  };

  window.exportClients = async function() {
  var showDeleted = document.getElementById('showDeletedClients').checked;
  var data = await window.exportClientsData(showDeleted);
  downloadCSV(data, 'clients_export.csv');
  };

  // ============================================
  // QUOTATIONS
  // ============================================
  window.loadQuotations = async function(page) {
  quotationsPage = page || 1;
  var container = document.getElementById('quotationsContent');
  container.innerHTML = '<div style="text-align:center;padding:30px;"><div class="hp-code-loader" style="font-size:1.5em;font-weight:900;"><span>&lt;</span><span>LOADING...</span><span>/&gt;</span></div></div>';

  var search = document.getElementById('quotationSearch').value;
  var showDeleted = document.getElementById('showDeletedQuotations').checked;

  try {
  var result = await window.getAllQuotations(quotationsPage, 15, search, showDeleted);
  renderQuotationsTable(result, container);
  } catch (e) {
  container.innerHTML = '<div class="empty-state"><h4>Error loading quotations</h4></div>';
  }
  };

  function renderQuotationsTable(result, container) {
  if (result.data.length === 0) {
  container.innerHTML = '<div class="empty-state"><h4>No quotations found</h4></div>';
  return;
  }

  var html = '<div class="table-scroll"><table class="data-table"><thead><tr><th>#</th><th>Date</th><th>Client</th><th>Model</th><th>Agreed Price</th><th>Status</th><th>Actions</th></tr></thead><tbody>';
  result.data.forEach(function(q) {
  var status = q.is_deleted ? 'deleted' : 'active';
  html += '<tr>';
  html += '<td>' + escapeHtml(q['Quotation#']) + '</td>';
  html += '<td>' + escapeHtml(q['Date']) + '</td>';
  html += '<td>' + escapeHtml(q['Client Name']) + '</td>';
  html += '<td>' + escapeHtml(q['Model'] || '-') + '</td>';
  html += '<td>' + (q['Agreed Price'] ? escapeHtml(q['Agreed Price'].toLocaleString()) : '-') + '</td>';
  html += '<td><span class="status ' + status + '">' + status.charAt(0).toUpperCase() + status.slice(1) + '</span></td>';
  html += '<td class="actions">';
  if (q.is_deleted) {
  html += '<button class="btn-sm restore" data-action="restorequot" data-num="' + escapeHtml(q['Quotation#']) + '">Restore</button>';
  } else {
  html += '<button class="btn-sm delete" data-action="deletequot" data-num="' + escapeHtml(q['Quotation#']) + '">Delete</button>';
  }
  html += '</td></tr>';
  });
  html += '</tbody></table></div>';

  html += '<div class="pagination">';
  html += '<button ' + (result.page <= 1 ? 'disabled' : '') + ' data-action="pagequots" data-page="' + (result.page - 1) + '">Previous</button>';
  html += '<span class="page-info">Page ' + result.page + ' of ' + result.total_pages + ' (' + result.total + ' items)</span>';
  html += '<button ' + (result.page >= result.total_pages ? 'disabled' : '') + ' data-action="pagequots" data-page="' + (result.page + 1) + '">Next</button>';
  html += '</div>';

  container.innerHTML = html;
  container.querySelectorAll('[data-action]').forEach(function(btn){
    btn.addEventListener('click', function(){
      var action = this.getAttribute('data-action');
      if(action==='restorequot') restoreQuotation(parseInt(this.getAttribute('data-num')));
      else if(action==='deletequot') deleteQuotation(parseInt(this.getAttribute('data-num')));
      else if(action==='pagequots') loadQuotations(parseInt(this.getAttribute('data-page')));
    });
  });
  }

  window.searchQuotations = function() {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(function() { loadQuotations(1); }, 300);
  };

  window.deleteQuotation = async function(num) {
  if (!confirm('Delete this quotation?')) return;
  await withBusy('deleteQuot_' + num, async function() {
    try {
    var result = await window.softDeleteQuotation(num);
    if (result.success) {
    loadQuotations(quotationsPage);
    } else {
    (window.showNotification&&window.showNotification('error','',result.message));
    }
    } catch (e) {
    console.error('deleteQuotation:', e);
    (window.showNotification&&window.showNotification('error','','Failed to delete quotation'));
    }
  });
  };

  window.restoreQuotation = async function(num) {
  await withBusy('restoreQuot_' + num, async function() {
    try {
    var result = _restoreQuotationAPI ? await _restoreQuotationAPI(num) : { success: false, message: 'Bridge not ready' };
    if (result.success) {
    loadQuotations(quotationsPage);
    } else {
    (window.showNotification&&window.showNotification('error','',result.message));
    }
    } catch (e) {
    console.error('restoreQuotation:', e);
    (window.showNotification&&window.showNotification('error','','Failed to restore quotation'));
    }
  });
  };

  window.exportQuotations = async function() {
  var showDeleted = document.getElementById('showDeletedQuotations').checked;
  var data = await window.exportQuotationsData(showDeleted);
  downloadCSV(data, 'quotations_export.csv');
  };

  // ============================================
  // CONTRACTS
  // ============================================
  window.loadContracts = async function(page) {
  contractsPage = page || 1;
  var container = document.getElementById('contractsContent');
  if (!container) return;
  container.innerHTML = '<div style="text-align:center;padding:30px;"><div class="hp-code-loader" style="font-size:1.5em;font-weight:900;"><span>&lt;</span><span>LOADING...</span><span>/&gt;</span></div></div>';
  var search = document.getElementById('contractSearch') ? document.getElementById('contractSearch').value : '';
  try {
  var result = await window.getAllContracts(contractsPage, 15, search);
  if (!result || typeof result !== 'object') {
  container.innerHTML = '<div class="empty-state"><h4>Error loading contracts</h4></div>';
  return;
  }
  if (!Array.isArray(result.data)) result.data = [];
  renderContractsTable(result, container);
  } catch (e) {
  container.innerHTML = '<div class="empty-state"><h4>Error loading contracts</h4></div>';
  }
  };
  function renderContractsTable(result, container) {
  if (!result || !Array.isArray(result.data) || result.data.length === 0) {
  container.innerHTML = '<div class="empty-state"><h4>No contracts found</h4></div>';
  return;
  }
  function formatPrice(v) {
  if (v == null || v === '') return '-';
  var s = String(v).replace(/,|،/g, '');
  var n = parseFloat(s);
  if (isNaN(n)) return '-';
  return n.toLocaleString();
  }
  function formatPaymentsSchedule(payments) {
  if (!payments || !payments.length) return '-';
  return payments.map(function(p) {
  var d = (p.date || '').toString().split('T')[0] || '-';
  var a = p.amount != null && p.amount !== '' ? formatPrice(p.amount) : (p.value != null ? p.value + '%' : '-');
  return escapeHtml(d + ': ' + a);
  }).join(' | ');
  }
  var lifecycleBg = {'draft':'#e3f2fd','negotiation':'#fff3e0','signed':'#e8f5e9','in_progress':'#e1f5fe','delivered':'#f3e5f5','closed':'#e0e0e0','cancelled':'#ffebee'};
  var lifecycleColor = {'draft':'#1565c0','negotiation':'#ef6c00','signed':'#2e7d32','in_progress':'#0277bd','delivered':'#7b1fa2','closed':'#616161','cancelled':'#c62828'};
  var html = '<div class="table-scroll"><table class="data-table"><thead><tr><th>Contract #</th><th>Quotation #</th><th>Client</th><th>Total Price</th><th>#</th><th>Payment schedule (date: amount)</th><th>Delivery Date</th><th>Created</th><th>Lifecycle</th><th>Actions</th></tr></thead><tbody>';
  result.data.forEach(function(c) {
  var ls = c.lifecycle_status || 'draft';
  html += '<tr>';
  html += '<td>' + escapeHtml(c.contract_number || '-') + '</td>';
  html += '<td>' + escapeHtml(c.quotation_number != null ? c.quotation_number : '-') + '</td>';
  html += '<td>' + escapeHtml(c.client_name || '-') + '</td>';
  html += '<td>' + escapeHtml(formatPrice(c.total_price)) + '</td>';
  html += '<td>' + escapeHtml(c.num_payments != null ? c.num_payments : '-') + '</td>';
  html += '<td style="max-width:320px;font-size:12px;">' + (c.payments ? formatPaymentsSchedule(c.payments) : '-') + '</td>';
  html += '<td>' + escapeHtml(c.delivery_date || '-') + '</td>';
  html += '<td>' + escapeHtml(c.created_at ? String(c.created_at).split('T')[0] : '-') + '</td>';
  html += '<td><span style="padding:3px 8px;border-radius:12px;font-size:11px;font-weight:600;background:' + (lifecycleBg[ls]||'#e3f2fd') + ';color:' + (lifecycleColor[ls]||'#1565c0') + '">' + escapeHtml(ls) + '</span></td>';
  html += '<td class="actions"><button style="padding:4px 10px;border:none;border-radius:4px;cursor:pointer;background:#667eea;color:#fff;font-size:12px;margin-right:4px;" data-action="timeline" data-contract="' + escapeHtml(c.contract_number) + '">Timeline</button><button class="btn-sm delete" data-action="deletecontract" data-quotnum="' + escapeHtml(c.quotation_number != null ? c.quotation_number : '') + '">Delete</button></td>';
  html += '</tr>';
  });
  html += '</tbody></table></div>';
  html += '<div class="pagination">';
  var totalPages = result.total_pages != null ? result.total_pages : 1;
  var totalCount = result.total != null ? result.total : 0;
  html += '<button ' + (result.page <= 1 ? 'disabled' : '') + ' data-action="pagecontracts" data-page="' + (result.page - 1) + '">Previous</button>';
  html += '<span class="page-info">Page ' + result.page + ' of ' + totalPages + ' (' + totalCount + ' items)</span>';
  html += '<button ' + (result.page >= totalPages ? 'disabled' : '') + ' data-action="pagecontracts" data-page="' + (result.page + 1) + '">Next</button>';
  html += '</div>';
  container.innerHTML = html;
  container.querySelectorAll('[data-action]').forEach(function(btn){
    btn.addEventListener('click', function(){
      var action = this.getAttribute('data-action');
      if(action==='timeline') showContractTimeline(this.getAttribute('data-contract'));
      else if(action==='deletecontract') deleteContractRow(parseInt(this.getAttribute('data-quotnum')));
      else if(action==='pagecontracts') loadContracts(parseInt(this.getAttribute('data-page')));
    });
  });
  }
  window.searchContracts = function() {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(function() { loadContracts(1); }, 300);
  };
  window.exportContracts = async function() {
  var data = await window.exportContractsData();
  if (data && data.length) downloadCSV(data, 'contracts_export.csv');
  else if (window.showNotification) showNotification('info', 'Export', 'No contracts to export');
  };

  window.deleteContractRow = async function(quotationNumber) {
  if (!confirm('حذف هذا العقد بالكامل من الجدول؟ لا يمكن التراجع.')) return;
  await withBusy('deleteContract_' + quotationNumber, async function() {
    try {
    var result = await window.deleteContractAdmin(quotationNumber);
    if (result && result.success) {
    if (window.showNotification) showNotification('success', 'تم', result.message || 'تم حذف العقد');
    loadContracts(contractsPage);
    if (window.loadDashboard) loadDashboard();
    } else {
    if (window.showNotification) showNotification('error', 'خطأ', result ? (result.message || result.message_en || '') : 'فشل الحذف');
    }
    } catch (e) {
    console.error('deleteContractRow:', e);
    if (window.showNotification) showNotification('error', 'خطأ', e.message || 'فشل الحذف');
    }
  });
  };

  // ============================================
  // AUDIT LOG
  // ============================================
  window.loadAuditLogs = async function(page) {
  auditPage = page || 1;
  var container = document.getElementById('auditContent');
  container.innerHTML = '<div style="text-align:center;padding:30px;"><div class="hp-code-loader" style="font-size:1.5em;font-weight:900;"><span>&lt;</span><span>LOADING...</span><span>/&gt;</span></div></div>';

  try {
  var result = await window.getAuditLogs(50, (auditPage - 1) * 50, null);
  if (!result.success) {
  container.innerHTML = '<div class="empty-state"><h4>' + escapeHtml(result.message) + '</h4></div>';
  return;
  }

  if (result.logs.length === 0) {
  container.innerHTML = '<div class="empty-state"><h4>No audit logs found</h4></div>';
  return;
  }

  var html = '<div class="table-scroll"><table class="data-table"><thead><tr><th>Time</th><th>User</th><th>Action</th><th>Table</th><th>Record ID</th></tr></thead><tbody>';
  result.logs.forEach(function(l) {
  html += '<tr>';
  html += '<td>' + escapeHtml(l.timestamp.replace('T', ' ').substring(0, 19)) + '</td>';
  html += '<td>' + escapeHtml(l.user_email) + '</td>';
  html += '<td>' + escapeHtml(l.action) + '</td>';
  html += '<td>' + escapeHtml(l.table_name) + '</td>';
  html += '<td>' + escapeHtml(l.record_id || '-') + '</td>';
  html += '</tr>';
  });
  html += '</tbody></table></div>';

  container.innerHTML = html;
  } catch (e) {
  console.error('loadAuditLogs:', e);
  container.innerHTML = '<div class="empty-state"><h4>Error loading audit logs</h4></div>';
  }
  };

  // ============================================
  // SETTINGS
  // ============================================
  window.loadSettings = async function() {
  var container = document.getElementById('settingsContent');
  container.innerHTML = '<div style="text-align:center;padding:30px;"><div class="hp-code-loader" style="font-size:1.5em;font-weight:900;"><span>&lt;</span><span>LOADING...</span><span>/&gt;</span></div></div>';

  try {
  if (!window.getAllSettings) {
  container.innerHTML = '<div class="empty-state"><h4>System is loading, please wait...</h4></div>';
  setTimeout(loadSettings, 1000);
  return;
  }

  var result = await window.getAllSettings();
  if (!result || !result.success) {
  var errorMsg = result ? result.message : 'Error loading settings';
  container.innerHTML = '<div class="empty-state"><h4>' + escapeHtml(errorMsg) + '</h4></div>';
  return;
  }

  var settings = result.settings || {};

  var html = '<div class="settings-grid" style="display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start;">';

  // Exchange Rate Section
  html += '<div style="background:#f8f9fa;padding:20px;border-radius:12px;">';
  html += '<h4 style="margin:0 0 15px;">💱 Exchange Rate</h4>';
  html += '<div class="form-group" style="margin-bottom:0;">';
  html += '<label>USD to EGP Rate</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="number" step="0.01" id="setting_exchange_rate" value="' + (settings.exchange_rate || 47.5) + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSetting(\'exchange_rate\')">Save</button>';
  html += '</div></div></div>';

  // Shipping & Expenses Section
  html += '<div style="background:#f8f9fa;padding:20px;border-radius:12px;">';
  html += '<h4 style="margin:0 0 15px;">🚢 Shipping & Expenses (USD)</h4>';

  html += '<div class="form-group">';
  html += '<label>Sea Shipping Cost</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="number" step="1" id="setting_shipping_sea" value="' + (settings.shipping_sea || 3200) + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSetting(\'shipping_sea\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group">';
  html += '<label>THS Cost</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="number" step="1" id="setting_ths_cost" value="' + (settings.ths_cost || 1000) + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSetting(\'ths_cost\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group">';
  html += '<label>Clearance Expenses</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="number" step="1" id="setting_clearance_expenses" value="' + (settings.clearance_expenses || 1400) + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSetting(\'clearance_expenses\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group">';
  html += '<label>Tax Rate (%)</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="number" step="0.01" id="setting_tax_rate" value="' + ((settings.tax_rate || 0.15) * 100) + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSetting(\'tax_rate\', true)">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group" style="margin-bottom:0;">';
  html += '<label>Bank Commission (%)</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="number" step="0.001" id="setting_bank_commission" value="' + ((settings.bank_commission || 0.0132) * 100) + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSetting(\'bank_commission\', true)">Save</button>';
  html += '</div></div>';

  html += '</div>';

  html += '</div>'; // End grid

  // ==========================================
  // 📄 Quotation PDF Template Settings
  // ==========================================
  html += '<div style="background:#e8f5e9;padding:20px;border-radius:12px;margin-top:20px;border:2px solid #4caf50;">';
  html += '<h4 style="margin:0 0 15px;color:#2e7d32;">📄 Quotation PDF Template Settings</h4>';

  // Company Info
  html += '<div style="background:#fff;padding:15px;border-radius:8px;margin-bottom:15px;">';
  html += '<h5 style="margin:0 0 10px;color:#1a1a2e;">🏢 Company Information</h5>';

  html += '<div class="form-group">';
  html += '<label>Company Name (Arabic)</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="text" id="setting_company_name_ar" value="' + escapeHtml(settings.company_name_ar || 'شركة حلوان بلاست ذ.م.م') + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;" dir="rtl">';
  html += '<button class="action-btn" onclick="saveSettingText(\'company_name_ar\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group">';
  html += '<label>Company Name (English)</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="text" id="setting_company_name_en" value="' + escapeHtml(settings.company_name_en || 'Helwan Plast LLC') + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSettingText(\'company_name_en\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group">';
  html += '<label>Company Address (Arabic)</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="text" id="setting_company_address_ar" value="' + escapeHtml(settings.company_address_ar || 'المنطقة الصناعية الثانية - قطعة ٢٠') + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;" dir="rtl">';
  html += '<button class="action-btn" onclick="saveSettingText(\'company_address_ar\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group">';
  html += '<label>Company Address (English)</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="text" id="setting_company_address_en" value="' + escapeHtml(settings.company_address_en || 'Second Industrial Zone – Plot 20') + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSettingText(\'company_address_en\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group">';
  html += '<label>Company Email</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="email" id="setting_company_email" value="' + escapeHtml(settings.company_email || 'sales@helwanplast.com') + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSettingText(\'company_email\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group" style="margin-bottom:0;">';
  html += '<label>Company Website</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="text" id="setting_company_website" value="' + escapeHtml(settings.company_website || 'www.helwanplast.com') + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSettingText(\'company_website\')">Save</button>';
  html += '</div></div>';

  html += '</div>'; // End Company Info

  // Quotation Defaults
  html += '<div style="background:#fff;padding:15px;border-radius:8px;margin-bottom:15px;">';
  html += '<h5 style="margin:0 0 10px;color:#1a1a2e;">📋 Quotation Defaults</h5>';

  html += '<div class="form-group">';
  html += '<label>Quotation Location (Arabic)</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="text" id="setting_quotation_location_ar" value="' + escapeHtml(settings.quotation_location_ar || 'القاهرة') + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;" dir="rtl">';
  html += '<button class="action-btn" onclick="saveSettingText(\'quotation_location_ar\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group">';
  html += '<label>Quotation Location (English)</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="text" id="setting_quotation_location_en" value="' + escapeHtml(settings.quotation_location_en || 'Cairo') + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSettingText(\'quotation_location_en\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group">';
  html += '<label>Warranty Period (months)</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="number" id="setting_warranty_months" value="' + (settings.warranty_months || 12) + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSetting(\'warranty_months\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group" style="margin-bottom:0;">';
  html += '<label>Quotation Validity (days)</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="number" id="setting_validity_days" value="' + (settings.validity_days || 15) + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSetting(\'validity_days\')">Save</button>';
  html += '</div></div>';

  html += '</div>'; // End Quotation Defaults

  // Payment Terms
  html += '<div style="background:#fff;padding:15px;border-radius:8px;margin-bottom:15px;">';
  html += '<h5 style="margin:0 0 10px;color:#1a1a2e;">💰 Payment Terms (%)</h5>';

  html += '<div class="form-group">';
  html += '<label>Down Payment %</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="number" id="setting_down_payment_percent" value="' + (settings.down_payment_percent || 40) + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSetting(\'down_payment_percent\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group">';
  html += '<label>Before Shipping %</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="number" id="setting_before_shipping_percent" value="' + (settings.before_shipping_percent || 30) + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSetting(\'before_shipping_percent\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group" style="margin-bottom:0;">';
  html += '<label>Before Delivery %</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="number" id="setting_before_delivery_percent" value="' + (settings.before_delivery_percent || 30) + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSetting(\'before_delivery_percent\')">Save</button>';
  html += '</div></div>';

  html += '</div>'; // End Payment Terms

  // Machine Defaults
  html += '<div style="background:#fff;padding:15px;border-radius:8px;">';
  html += '<h5 style="margin:0 0 10px;color:#1a1a2e;">⚙️ Machine Defaults</h5>';

  html += '<div class="form-group">';
  html += '<label>Country of Origin (Arabic)</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="text" id="setting_country_origin_ar" value="' + escapeHtml(settings.country_origin_ar || 'الصين') + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;" dir="rtl">';
  html += '<button class="action-btn" onclick="saveSettingText(\'country_origin_ar\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group">';
  html += '<label>Country of Origin (English)</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="text" id="setting_country_origin_en" value="' + escapeHtml(settings.country_origin_en || 'China') + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSettingText(\'country_origin_en\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group">';
  html += '<label>Anilox Type (Arabic)</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="text" id="setting_anilox_type_ar" value="' + escapeHtml(settings.anilox_type_ar || 'انيلوكس سيراميك') + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;" dir="rtl">';
  html += '<button class="action-btn" onclick="saveSettingText(\'anilox_type_ar\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group">';
  html += '<label>Anilox Type (English)</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="text" id="setting_anilox_type_en" value="' + escapeHtml(settings.anilox_type_en || 'Ceramic anilox') + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSettingText(\'anilox_type_en\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group">';
  html += '<label>Brake Power - Single Winder</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="text" id="setting_single_winder_brake_power" value="' + escapeHtml(settings.single_winder_brake_power || '1 pc (10kg) + 1 pc (5kg)') + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSettingText(\'single_winder_brake_power\')">Save</button>';
  html += '</div></div>';

  html += '<div class="form-group" style="margin-bottom:0;">';
  html += '<label>Brake Power - Double Winder</label>';
  html += '<div style="display:flex;gap:10px;align-items:center;">';
  html += '<input type="text" id="setting_double_winder_brake_power" value="' + escapeHtml(settings.double_winder_brake_power || '2 pc (10kg) + 2 pc (5kg)') + '" style="flex:1;padding:10px;border:1px solid #ddd;border-radius:6px;">';
  html += '<button class="action-btn" onclick="saveSettingText(\'double_winder_brake_power\')">Save</button>';
  html += '</div></div>';

html += '</div>'; // End Machine Defaults

  html += '</div>'; // End Quotation PDF Template Settings

  // Technical Specifications Section
  html += '<div style="background:#e3f2fd;padding:20px;border-radius:12px;margin-top:20px;border:2px solid #2196f3;">';
  html += '<h4 style="margin:0 0 10px;color:#1565c0;">📋 Technical Specifications Table Settings</h4>';
  html += '<p style="margin:0 0 15px;color:#666;font-size:13px;">Configure which fields appear in the Technical Specifications table.</p>';

  // Get saved tech specs
  var savedTechSpecs = {};
  try {
  if (settings.technical_specs) {
  savedTechSpecs = JSON.parse(settings.technical_specs);
  }
  } catch(e) { console.error('parse technical_specs:', e); savedTechSpecs = {}; }

  html += '<div style="background:#fff;padding:15px;border-radius:8px;overflow-x:auto;">';
  html += '<table style="width:100%;border-collapse:collapse;font-size:13px;">';
  html += '<thead><tr style="background:#f5f5f5;">';
  html += '<th style="padding:10px;border:1px solid #ddd;text-align:center;">#</th>';
  html += '<th style="padding:10px;border:1px solid #ddd;">Label (AR)</th>';
  html += '<th style="padding:10px;border:1px solid #ddd;">Label (EN)</th>';
  html += '<th style="padding:10px;border:1px solid #ddd;">Value Source</th>';
  html += '<th style="padding:10px;border:1px solid #ddd;text-align:center;">Active</th>';
  html += '</tr></thead><tbody>';

  var techSpecs = [
  {num: 1, ar: 'الموديل', en: 'Model', field: 'model'},
  {num: 2, ar: 'عدد الألوان', en: 'Number of Colors', field: 'colors_count'},
  {num: 3, ar: 'نوع الطباعة', en: 'Printing Sides', field: 'printing_sides'},
  {num: 4, ar: 'وحدات التحكم في الشد', en: 'Tension Control Units', field: 'tension_control'},
  {num: 5, ar: 'وحدات الكورونا', en: 'Corona Units', field: 'corona_units'},
  {num: 6, ar: 'نظام التحكم في مسجل الطباعة', en: 'Print Register Control', field: 'print_register'},
  {num: 7, ar: 'سكاكين الدكتور', en: 'Doctor Blades', field: 'doctor_blades'},
  {num: 8, ar: 'نوع رولات الانيلوكس', en: 'Anilox Type', field: 'anilox_type'},
  {num: 9, ar: 'مراقبة الطباعة بالفيديو', en: 'Video Inspection', field: 'video_inspection'},
  {num: 10, ar: 'PLC', en: 'PLC', field: 'plc'},
  {num: 11, ar: 'HMI شاشة', en: 'HMI Screen', field: 'hmi_screen'},
  {num: 12, ar: 'سليتر', en: 'Slitter', field: 'slitter'},
  {num: 13, ar: 'قدرة المجفف', en: 'Dryer Capacity', field: 'dryer_capacity'},
  {num: 14, ar: 'الموتورات', en: 'Motors', field: 'motors'},
  {num: 15, ar: 'سرعة الماكينة', en: 'Machine Speed', field: 'machine_speed'},
  {num: 16, ar: 'عرض الطباعة', en: 'Printing Width', field: 'printing_width'},
  {num: 17, ar: 'قطر الرول الأم', en: 'Parent Roll Diameter', field: 'roll_diameter'},
  {num: 18, ar: 'قطر البوبينة', en: 'Bobbin Diameter', field: 'bobbin_diameter'},
  {num: 19, ar: 'سمك المادة', en: 'Material Thickness', field: 'material_thickness'},
  {num: 20, ar: 'الوندر', en: 'Winder', field: 'winder'}
  ];

  techSpecs.forEach(function(spec) {
  var key = 'tech_spec_' + spec.num;
  var savedSpec = savedTechSpecs[key] || {};
  var isActive = savedSpec.active !== false;
  var valueSource = savedSpec.source || 'field';
  var labelAr = savedSpec.label_ar || spec.ar;
  var labelEn = savedSpec.label_en || spec.en;

  html += '<tr>';
  html += '<td style="padding:8px;border:1px solid #ddd;text-align:center;font-weight:bold;">' + spec.num + '</td>';
  html += '<td style="padding:8px;border:1px solid #ddd;"><input type="text" id="tech_' + spec.num + '_label_ar" value="' + escapeHtml(labelAr) + '" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;" dir="rtl"></td>';
  html += '<td style="padding:8px;border:1px solid #ddd;"><input type="text" id="tech_' + spec.num + '_label_en" value="' + escapeHtml(labelEn) + '" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;"></td>';
  html += '<td style="padding:8px;border:1px solid #ddd;">';
  html += '<select id="tech_' + spec.num + '_source" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">';
  html += '<option value="field"' + (valueSource === 'field' ? ' selected' : '') + '>From Quotation Field</option>';
  html += '<option value="fixed"' + (valueSource === 'fixed' ? ' selected' : '') + '>Fixed Value</option>';
  html += '<option value="yes_no"' + (valueSource === 'yes_no' ? ' selected' : '') + '>Yes/No Field</option>';
  html += '</select></td>';
  html += '<td style="padding:8px;border:1px solid #ddd;text-align:center;">';
  html += '<input type="checkbox" id="tech_' + spec.num + '_active"' + (isActive ? ' checked' : '') + ' style="width:20px;height:20px;">';
  html += '</td></tr>';
  });

  html += '</tbody></table></div>';

  html += '<div style="margin-top:15px;text-align:center;">';
  html += '<button class="action-btn green" onclick="saveTechSpecs()" style="padding:12px 30px;background:#4caf50;">💾 Save All Technical Specs</button>';
  html += '</div></div>';

  container.innerHTML = html;
  } catch (e) {
  console.error('Settings error:', e);
  container.innerHTML = '<div class="empty-state"><h4>Error loading settings</h4></div>';
  }
  };

  window.saveSettingText = async function(key) {
  var input = document.getElementById('setting_' + key);
  if (!input) return;

  var value = input.value.trim();
  if (!value) {
  (window.showNotification?window.showNotification('error','','Please enter a value'):null);
  return;
  }

  try {
  var result = await window.updateSetting(key, value);
  if (result && result.success) {
  showNotification('success', 'Saved!', key + ' updated successfully');
  } else {
  (window.showNotification?window.showNotification('error','',result ? result.message : 'Error saving setting'):null);
  }
  } catch (e) {
  (window.showNotification?window.showNotification('error','','Error saving setting: ' + e):null);
  }
  };

  window.saveTechSpecs = async function() {
  var specsData = {};

  for (var i = 1; i <= 20; i++) {
  var labelAr = document.getElementById('tech_' + i + '_label_ar');
  var labelEn = document.getElementById('tech_' + i + '_label_en');
  var source = document.getElementById('tech_' + i + '_source');
  var active = document.getElementById('tech_' + i + '_active');

  if (labelAr && labelEn && source && active) {
  specsData['tech_spec_' + i] = {
  label_ar: labelAr.value,
  label_en: labelEn.value,
  source: source.value,
  active: active.checked
  };
  }
  }

  try {
  var result = await window.updateSetting('technical_specs', JSON.stringify(specsData));
  if (result && result.success) {
  showNotification('success', 'Saved!', 'Technical Specifications saved successfully');
  } else {
  (window.showNotification?window.showNotification('error','',result ? result.message : 'Error saving settings'):null);
  }
  } catch (e) {
  (window.showNotification?window.showNotification('error','','Error saving: ' + e):null);
  }
  };

  window.saveSetting = async function(key, isPercent) {
  var input = document.getElementById('setting_' + key);
  if (!input) return;

  var value = parseFloat(input.value);
  if (isNaN(value)) {
  (window.showNotification?window.showNotification('error','','Please enter a valid number'):null);
  return;
  }

  if (isPercent) {
  value = value / 100;
  }

  try {
  var result = await window.updateSetting(key, value);
  if (result && result.success) {
  if(window.showNotification)window.showNotification('success','','Setting saved successfully!');
  } else {
  (window.showNotification?window.showNotification('error','',result ? result.message : 'Error saving setting'):null);
  }
  } catch (e) {
  (window.showNotification?window.showNotification('error','','Error saving setting: ' + e):null);
  }
  };

  // ============================================
  // CSV EXPORT
  // ============================================
  function downloadCSV(data, filename) {
  if (!data || data.length === 0) {
  (window.showNotification?window.showNotification('error','','No data to export'):null);
  return;
  }

  var headers = Object.keys(data[0]);
  var csv = headers.join(',') + '\n';

  data.forEach(function(row) {
  var values = headers.map(function(h) {
  var val = row[h] || '';
  if (typeof val === 'string' && (val.includes(',') || val.includes('"'))) {
  val = '"' + val.replace(/"/g, '""') + '"';
  }
  return val;
  });
  csv += values.join(',') + '\n';
  });

  var blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
  var link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  }

  // ============================================
  // MOBILE MENU
  // ============================================
  window.toggleMobileMenu = function() {
  var menu = document.getElementById('mobileMenu');
  if (menu) menu.classList.toggle('open');
  };

  // ============================================
  // LANGUAGE
  // ============================================
  window.toggleAdminLanguage = function() {
  var currentLang = localStorage.getItem('hp_language') || 'en';
  var newLang = currentLang === 'en' ? 'ar' : 'en';
  localStorage.setItem('hp_language', newLang);

  if (newLang === 'ar') {
  document.body.classList.add('rtl');
  document.documentElement.dir = 'rtl';
  document.getElementById('langFlag').textContent = '🇬🇧';
  document.getElementById('langText').textContent = 'English';
  } else {
  document.body.classList.remove('rtl');
  document.documentElement.dir = 'ltr';
  document.getElementById('langFlag').textContent = '🇸🇦';
  document.getElementById('langText').textContent = 'العربية';
  }

  if (currentPanel === 'dashboard') loadDashboard();
  else if (currentPanel === 'pending') loadPendingUsers();
  else if (currentPanel === 'users') loadAllUsers();
  else if (currentPanel === 'clients') loadClients();
  else if (currentPanel === 'quotations') loadQuotations();
  else if (currentPanel === 'contracts') loadContracts();
  else if (currentPanel === 'settings') loadSettings();
  else if (currentPanel === 'audit') loadAuditLogs();
  if (window.updateBackupNavLabel) window.updateBackupNavLabel();
  };

  // ============================================
  // LOGOUT
  // ============================================
  window.handleLogout = async function() {
  if (!confirm('Are you sure you want to logout?')) return;

  try {
  if (window.logoutUser) {
  await window.logoutUser();
  }
  localStorage.clear();
  sessionStorage.clear();
  window.location.hash = '#login';
  } catch (e) {
  console.error('Logout error:', e);
  localStorage.clear();
  window.location.hash = '#login';
  }
  };

  // Connect logout button
  function setupLogoutButton() {
  var logoutBtn = document.getElementById('logoutBtn');
  if (logoutBtn) {
  logoutBtn.onclick = handleLogout;
  }
  }

  // ============================================
  // AUTO-INIT
  // ============================================
  if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function() {
  init();
  });
  } else {
  setTimeout(function() {
  init();
  }, 100);
  }

  })();


window.showContractTimeline = async function(contractNum) {
  try {
    if (!window.getContractTimeline) { alert('Not available'); return; }
    var res = await window.getContractTimeline(contractNum);
    if (!res || !res.success) { alert(res ? res.message : 'Error'); return; }
    var states = res.all_states || [];
    var current = res.current_status || 'draft';
    var transitions = res.valid_transitions || [];
    var history = res.data || [];
    var html = '<div style="padding:20px;max-width:600px;"><h3>Contract ' + escapeHtml(contractNum) + ' - Lifecycle</h3>';
    // Stepper
    html += '<div style="display:flex;gap:4px;margin:16px 0;flex-wrap:wrap;">';
    var stateColors = {draft:'#1565c0',negotiation:'#ef6c00',signed:'#2e7d32',in_progress:'#0277bd',delivered:'#7b1fa2',closed:'#616161',cancelled:'#c62828'};
    states.forEach(function(s) {
      var isCurrent = (s === current);
      var bg = isCurrent ? (stateColors[s]||'#667eea') : '#e0e0e0';
      var color = isCurrent ? '#fff' : '#666';
      html += '<span style="padding:6px 12px;border-radius:16px;font-size:12px;font-weight:600;background:' + bg + ';color:' + color + ';">' + escapeHtml(s) + '</span>';
    });
    html += '</div>';
    // Timeline
    if (history.length > 0) {
      html += '<div style="margin:16px 0;border-left:3px solid #667eea;padding-left:16px;">';
      history.forEach(function(h) {
        html += '<div style="margin-bottom:12px;"><strong style="color:#667eea;">' + escapeHtml(h.from) + ' → ' + escapeHtml(h.to) + '</strong><br><span style="font-size:12px;color:#666;">' + escapeHtml((h.date||'').split('T')[0]) + ' by ' + escapeHtml(h.user||'') + '</span>';
        if (h.notes) html += '<br><span style="font-size:12px;color:#999;">' + escapeHtml(h.notes) + '</span>';
        html += '</div>';
      });
      html += '</div>';
    }
    // Transition buttons
    if (transitions.length > 0) {
      html += '<div style="margin-top:16px;"><strong>Change status to:</strong><div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap;">';
      transitions.forEach(function(t) {
        html += '<button style="padding:6px 14px;border:none;border-radius:6px;cursor:pointer;background:' + (stateColors[t]||'#667eea') + ';color:#fff;font-size:12px;" data-action="changestatus" data-contract="' + escapeHtml(contractNum) + '" data-status="' + escapeHtml(t) + '">' + escapeHtml(t) + '</button>';
      });
      html += '</div></div>';
    }
    html += '</div>';
    // Show in a simple modal
    var overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:99999;display:flex;align-items:center;justify-content:center;';
    overlay.onclick = function(e) { if (e.target === overlay) overlay.remove(); };
    var modal = document.createElement('div');
    modal.style.cssText = 'background:#fff;border-radius:12px;max-height:80vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,0.2);';
    modal.innerHTML = html;
    modal.querySelectorAll('[data-action="changestatus"]').forEach(function(btn){
      btn.addEventListener('click', function(){
        changeContractStatus(this.getAttribute('data-contract'), this.getAttribute('data-status'));
      });
    });
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
  } catch(e) { console.error('showContractTimeline:', e); alert('Error: ' + e); }
};
window.changeContractStatus = async function(contractNum, newStatus) {
  var notes = prompt('Notes for this change (optional):') || '';
  try {
    var res = await window.updateContractLifecycle(contractNum, newStatus, notes);
    if (res && res.success) {
      alert(res.message || 'Status updated');
      document.querySelectorAll('div[style*="position:fixed"]').forEach(function(el) { el.remove(); });
      if (window.loadContracts) loadContracts();
    } else {
      alert(res ? res.message : 'Error');
    }
  } catch(e) { alert('Error: ' + e); }
};

window.exportAuditCSV = async function() {
  try {
    if (!window.exportAuditLogs) { alert('Export not available'); return; }
    var data = await window.exportAuditLogs({});
    if (!data || data.length === 0) { alert('No audit logs to export'); return; }
    var headers = Object.keys(data[0]);
    var csv = '\uFEFF' + headers.join(',') + '\n';
    data.forEach(function(row) {
      csv += headers.map(function(h) {
        return '"' + String(row[h]||'').replace(/"/g,'""') + '"';
      }).join(',') + '\n';
    });
    var blob = new Blob([csv], {type:'text/csv;charset=utf-8'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'audit_log_' + new Date().toISOString().slice(0,10) + '.csv';
    a.click();
  } catch(e) { alert('Export error: ' + e); }
};
window.exportInventoryExcel = async function() {
  try {
    if (!window.exportInventoryData) { alert('Not available'); return; }
    var data = await window.exportInventoryData();
    if (!data || data.length === 0) { alert('No inventory data'); return; }
    var headers = Object.keys(data[0]);
    var csv = '\uFEFF' + headers.join(',') + '\n';
    data.forEach(function(row) {
      csv += headers.map(function(h) {
        return '"' + String(row[h]||'').replace(/"/g,'""') + '"';
      }).join(',') + '\n';
    });
    var blob = new Blob([csv], {type:'text/csv;charset=utf-8'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'inventory_' + new Date().toISOString().slice(0,10) + '.csv';
    a.click();
  } catch(e) { alert('Export error: ' + e); }
};
window.exportPurchaseInvoicesExcel = async function() {
  try {
    if (!window.exportPurchaseInvoicesData) { alert('Not available'); return; }
    var data = await window.exportPurchaseInvoicesData();
    if (!data || data.length === 0) { alert('No data'); return; }
    var headers = Object.keys(data[0]);
    var csv = '\uFEFF' + headers.join(',') + '\n';
    data.forEach(function(row) {
      csv += headers.map(function(h) {
        return '"' + String(row[h]||'').replace(/"/g,'""') + '"';
      }).join(',') + '\n';
    });
    var blob = new Blob([csv], {type:'text/csv;charset=utf-8'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'purchase_invoices_' + new Date().toISOString().slice(0,10) + '.csv';
    a.click();
  } catch(e) { alert('Export error: ' + e); }
};
window.runDailyCheck = async function() {
  try {
    if (!window.runDailyNotificationCheck) { alert('Not available'); return; }
    var r = await window.runDailyNotificationCheck();
    if (r && r.success) {
      alert(r.message || 'Check complete');
    } else {
      alert(r && r.message ? r.message : 'Check failed');
    }
  } catch(e) { alert('Error: ' + e); }
};
window.autoFetchRates = async function() {
  try {
    if (!window.fetchExchangeRates) { alert('Not available'); return; }
    var r = await window.fetchExchangeRates();
    if (r && r.success) {
      alert(r.message || 'Rates updated!');
      if (window.loadSettings) loadSettings();
    } else {
      alert(r && r.message ? r.message : 'Failed to fetch rates');
    }
  } catch(e) { alert('Error: ' + e); }
};


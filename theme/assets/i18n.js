/**
 * i18n.js - Internationalization System for Helwan Plast
 * Supports: English (en) and Arabic (ar)
 * Features: RTL support, localStorage persistence, dynamic translation
 */

(function() {
  'use strict';

  // ============================================
  // TRANSLATIONS
  // ============================================
  const translations = {
    en: {
      // Common
      save: 'Save',
      cancel: 'Cancel',
      delete: 'Delete',
      edit: 'Edit',
      add: 'Add',
      search: 'Search',
      refresh: 'Refresh',
      export: 'Export',
      import: 'Import',
      loading: 'Loading...',
      error: 'Error',
      success: 'Success',
      warning: 'Warning',
      info: 'Info',
      yes: 'Yes',
      no: 'No',
      confirm: 'Confirm',
      close: 'Close',
      back: 'Back',
      next: 'Next',
      previous: 'Previous',
      submit: 'Submit',
      reset: 'Reset',
      clear: 'Clear',
      select: 'Select',
      all: 'All',
      none: 'None',
      actions: 'Actions',
      status: 'Status',
      date: 'Date',
      name: 'Name',
      email: 'Email',
      phone: 'Phone',
      password: 'Password',
      role: 'Role',
      active: 'Active',
      inactive: 'Inactive',
      pending: 'Pending',
      approved: 'Approved',
      rejected: 'Rejected',
      deleted: 'Deleted',

      // Login Page
      login_title: 'Welcome Back',
      login_subtitle: 'Sign in to your account',
      login_email_placeholder: 'Enter your email',
      login_password_placeholder: 'Enter your password',
      login_button: 'Sign In',
      login_register_link: "Don't have an account? Register",
      login_forgot_password: 'Forgot Password?',
      login_error_invalid: 'Invalid email or password',
      login_error_pending: 'Account pending approval',
      login_error_inactive: 'Account is deactivated',

      // Register Page
      register_title: 'Create Account',
      register_subtitle: 'Join Helwan Plast System',
      register_name_placeholder: 'Full Name',
      register_email_placeholder: 'Email Address',
      register_phone_placeholder: 'Phone Number (optional)',
      register_password_placeholder: 'Password (min 8 characters)',
      register_confirm_placeholder: 'Confirm Password',
      register_button: 'Create Account',
      register_login_link: 'Already have an account? Sign In',
      register_success: 'Registration successful! Please wait for admin approval.',
      register_error_exists: 'Email already registered',
      register_error_password: 'Passwords do not match',

      // Admin Panel
      admin_title: 'Admin Panel',
      admin_subtitle: 'Helwan Plast System',
      admin_welcome: "Welcome back! Here's what's happening today.",

      // Sidebar Navigation
      nav_main: 'Main',
      nav_dashboard: 'Dashboard',
      nav_user_management: 'User Management',
      nav_pending_approvals: 'Pending Approvals',
      nav_all_users: 'All Users',
      nav_data_management: 'Data Management',
      nav_clients: 'Clients',
      nav_quotations: 'Quotations',
      nav_system: 'System',
      nav_settings: 'Settings',
      nav_audit_log: 'Audit Log',
      nav_tools: 'Tools',
      nav_data_import: 'Data Import',
      nav_application: 'Application',
      nav_go_to_launcher: 'Go to Launcher',
      nav_logout: 'Logout',

      // Dashboard
      dashboard_total_clients: 'Total Clients',
      dashboard_total_quotations: 'Total Quotations',
      dashboard_total_value: 'Total Value (EGP)',
      dashboard_this_month: 'This Month Quotations',

      // Pending Users
      pending_title: 'Pending User Approvals',
      pending_no_approvals: 'No pending approvals',
      pending_all_reviewed: 'All users have been reviewed',
      pending_registered: 'Registered',
      pending_approve: 'Approve',
      pending_reject: 'Reject',

      // Approval Modal
      approval_title: 'Approve User',
      approval_select_role: 'Select Role for this User',
      approval_role_viewer: 'Viewer (Read Only)',
      approval_role_sales: 'Sales (Create & Edit Own)',
      approval_role_manager: 'Manager (Full except Admin)',
      approval_role_admin: 'Admin (Full Access)',
      approval_permissions: 'Role Permissions:',
      approval_confirm: 'Approve User',
      approval_success: 'User Approved!',
      approval_processing: 'Approving user...',

      // Rejection
      reject_confirm: 'Are you sure you want to reject {name}?\nThis action cannot be undone.',
      reject_success: 'User Rejected',
      reject_removed: '{name} has been removed',
      reject_processing: 'Rejecting user...',

      // All Users
      users_title: 'All Users',
      users_no_users: 'No users found',
      users_last_login: 'Last Login',
      users_never: 'Never',
      users_change_role: 'Change User Role',
      users_reset_password: 'Reset Password',
      users_new_password: 'New Password',
      users_password_placeholder: 'Enter new password (min 6 characters)',
      users_password_min: 'Password must be at least 6 characters',
      users_password_success: 'Password reset successfully',
      users_disable: 'Disable',
      users_enable: 'Enable',

      // Clients
      clients_title: 'Clients Management',
      clients_search: 'Search clients...',
      clients_show_deleted: 'Show Deleted',
      clients_export: 'Export Excel',
      clients_no_clients: 'No clients found',
      clients_code: 'Code',
      clients_company: 'Company',
      clients_country: 'Country',
      clients_restore: 'Restore',
      clients_delete_confirm: 'Delete this client?',

      // Quotations
      quotations_title: 'Quotations Management',
      quotations_search: 'Search quotations...',
      quotations_show_deleted: 'Show Deleted',
      quotations_export: 'Export Excel',
      quotations_no_quotations: 'No quotations found',
      quotations_model: 'Model',
      quotations_agreed_price: 'Agreed Price',
      quotations_delete_confirm: 'Delete this quotation?',

      // Settings
      settings_title: 'System Settings',
      settings_exchange_rate: 'Exchange Rate',
      settings_usd_egp: 'USD to EGP Rate',
      settings_shipping: 'Shipping & Expenses (USD)',
      settings_sea_shipping: 'Sea Shipping Cost',
      settings_ths_cost: 'THS Cost',
      settings_clearance: 'Clearance Expenses',
      settings_tax_rate: 'Tax Rate (%)',
      settings_bank_commission: 'Bank Commission (%)',
      settings_cylinder_prices: 'Cylinder Prices (USD per cm)',
      settings_width: 'Width',
      settings_saved: 'Setting saved successfully!',
      settings_invalid: 'Please enter a valid number',

      // Audit Log
      audit_title: 'Audit Log',
      audit_no_logs: 'No audit logs found',
      audit_time: 'Time',
      audit_user: 'User',
      audit_action: 'Action',
      audit_table: 'Table',
      audit_record: 'Record ID',

      // Pagination
      pagination_page: 'Page',
      pagination_of: 'of',
      pagination_items: 'items',

      // Notifications
      notif_processing: 'Processing',
      notif_error_loading: 'Error loading data',

      // Launcher
      launcher_title: 'Helwan Plast',
      launcher_subtitle: 'Quotation Management System',
      launcher_calculator: 'Price Calculator',
      launcher_calculator_desc: 'Calculate prices for printing jobs',
      launcher_admin: 'Admin Panel',
      launcher_admin_desc: 'Manage users, clients and quotations',

      // Calculator
      calc_title: 'Price Calculator',
      calc_client_info: 'Client Information',
      calc_product_specs: 'Product Specifications',
      calc_pricing: 'Pricing',
      calc_summary: 'Summary',
      calc_new_quotation: 'New Quotation',
      calc_save_quotation: 'Save Quotation',
      calc_print: 'Print',
      calc_client_name: 'Client Name',
      calc_client_code: 'Client Code',
      calc_select_client: 'Select Client',
      calc_new_client: 'New Client',

      // Language
      language: 'Language',
      lang_english: 'English',
      lang_arabic: 'العربية',
    },

    ar: {
      // Common
      save: 'حفظ',
      cancel: 'إلغاء',
      delete: 'حذف',
      edit: 'تعديل',
      add: 'إضافة',
      search: 'بحث',
      refresh: 'تحديث',
      export: 'تصدير',
      import: 'استيراد',
      loading: 'جاري التحميل...',
      error: 'خطأ',
      success: 'نجاح',
      warning: 'تحذير',
      info: 'معلومة',
      yes: 'نعم',
      no: 'لا',
      confirm: 'تأكيد',
      close: 'إغلاق',
      back: 'رجوع',
      next: 'التالي',
      previous: 'السابق',
      submit: 'إرسال',
      reset: 'إعادة تعيين',
      clear: 'مسح',
      select: 'اختيار',
      all: 'الكل',
      none: 'لا شيء',
      actions: 'الإجراءات',
      status: 'الحالة',
      date: 'التاريخ',
      name: 'الاسم',
      email: 'البريد الإلكتروني',
      phone: 'الهاتف',
      password: 'كلمة المرور',
      role: 'الدور',
      active: 'نشط',
      inactive: 'غير نشط',
      pending: 'قيد الانتظار',
      approved: 'موافق عليه',
      rejected: 'مرفوض',
      deleted: 'محذوف',

      // Login Page
      login_title: 'مرحباً بعودتك',
      login_subtitle: 'سجّل دخولك للمتابعة',
      login_email_placeholder: 'أدخل بريدك الإلكتروني',
      login_password_placeholder: 'أدخل كلمة المرور',
      login_button: 'تسجيل الدخول',
      login_register_link: 'ليس لديك حساب؟ سجّل الآن',
      login_forgot_password: 'نسيت كلمة المرور؟',
      login_error_invalid: 'البريد الإلكتروني أو كلمة المرور غير صحيحة',
      login_error_pending: 'الحساب في انتظار موافقة المسؤول',
      login_error_inactive: 'الحساب معطّل',

      // Register Page
      register_title: 'إنشاء حساب',
      register_subtitle: 'انضم لنظام حلوان بلاست',
      register_name_placeholder: 'الاسم بالكامل',
      register_email_placeholder: 'البريد الإلكتروني',
      register_phone_placeholder: 'رقم الهاتف (اختياري)',
      register_password_placeholder: 'كلمة المرور (8 أحرف على الأقل)',
      register_confirm_placeholder: 'تأكيد كلمة المرور',
      register_button: 'إنشاء الحساب',
      register_login_link: 'لديك حساب بالفعل؟ سجّل دخولك',
      register_success: 'تم التسجيل بنجاح! يرجى انتظار موافقة المسؤول.',
      register_error_exists: 'البريد الإلكتروني مسجّل مسبقاً',
      register_error_password: 'كلمتا المرور غير متطابقتين',

      // Admin Panel
      admin_title: 'لوحة التحكم',
      admin_subtitle: 'نظام حلوان بلاست',
      admin_welcome: 'مرحباً بعودتك! إليك ما يحدث اليوم.',

      // Sidebar Navigation
      nav_main: 'الرئيسية',
      nav_dashboard: 'لوحة المعلومات',
      nav_user_management: 'إدارة المستخدمين',
      nav_pending_approvals: 'طلبات الانتظار',
      nav_all_users: 'جميع المستخدمين',
      nav_data_management: 'إدارة البيانات',
      nav_clients: 'العملاء',
      nav_quotations: 'عروض الأسعار',
      nav_system: 'النظام',
      nav_settings: 'الإعدادات',
      nav_audit_log: 'سجل العمليات',
      nav_tools: 'الأدوات',
      nav_data_import: 'استيراد البيانات',
      nav_application: 'التطبيق',
      nav_go_to_launcher: 'الذهاب للقائمة',
      nav_logout: 'تسجيل الخروج',

      // Dashboard
      dashboard_total_clients: 'إجمالي العملاء',
      dashboard_total_quotations: 'إجمالي عروض الأسعار',
      dashboard_total_value: 'إجمالي القيمة (ج.م)',
      dashboard_this_month: 'عروض هذا الشهر',

      // Pending Users
      pending_title: 'طلبات تسجيل المستخدمين',
      pending_no_approvals: 'لا توجد طلبات انتظار',
      pending_all_reviewed: 'تمت مراجعة جميع المستخدمين',
      pending_registered: 'تاريخ التسجيل',
      pending_approve: 'موافقة',
      pending_reject: 'رفض',

      // Approval Modal
      approval_title: 'الموافقة على المستخدم',
      approval_select_role: 'اختر الدور لهذا المستخدم',
      approval_role_viewer: 'مشاهد (قراءة فقط)',
      approval_role_sales: 'مبيعات (إنشاء وتعديل الخاص)',
      approval_role_manager: 'مدير (كل شيء ما عدا الإدارة)',
      approval_role_admin: 'مسؤول (صلاحيات كاملة)',
      approval_permissions: 'صلاحيات الدور:',
      approval_confirm: 'الموافقة على المستخدم',
      approval_success: 'تمت الموافقة!',
      approval_processing: 'جاري الموافقة...',

      // Rejection
      reject_confirm: 'هل أنت متأكد من رفض {name}؟\nلا يمكن التراجع عن هذا الإجراء.',
      reject_success: 'تم الرفض',
      reject_removed: 'تم إزالة {name}',
      reject_processing: 'جاري الرفض...',

      // All Users
      users_title: 'جميع المستخدمين',
      users_no_users: 'لا يوجد مستخدمون',
      users_last_login: 'آخر دخول',
      users_never: 'لم يسجل دخول',
      users_change_role: 'تغيير دور المستخدم',
      users_reset_password: 'إعادة تعيين كلمة المرور',
      users_new_password: 'كلمة المرور الجديدة',
      users_password_placeholder: 'أدخل كلمة المرور الجديدة (6 أحرف على الأقل)',
      users_password_min: 'كلمة المرور يجب أن تكون 6 أحرف على الأقل',
      users_password_success: 'تم إعادة تعيين كلمة المرور بنجاح',
      users_disable: 'تعطيل',
      users_enable: 'تفعيل',

      // Clients
      clients_title: 'إدارة العملاء',
      clients_search: 'البحث في العملاء...',
      clients_show_deleted: 'عرض المحذوفين',
      clients_export: 'تصدير Excel',
      clients_no_clients: 'لا يوجد عملاء',
      clients_code: 'الكود',
      clients_company: 'الشركة',
      clients_country: 'الدولة',
      clients_restore: 'استعادة',
      clients_delete_confirm: 'هل تريد حذف هذا العميل؟',

      // Quotations
      quotations_title: 'إدارة عروض الأسعار',
      quotations_search: 'البحث في العروض...',
      quotations_show_deleted: 'عرض المحذوفين',
      quotations_export: 'تصدير Excel',
      quotations_no_quotations: 'لا توجد عروض أسعار',
      quotations_model: 'الموديل',
      quotations_agreed_price: 'السعر المتفق عليه',
      quotations_delete_confirm: 'هل تريد حذف هذا العرض؟',

      // Settings
      settings_title: 'إعدادات النظام',
      settings_exchange_rate: 'سعر الصرف',
      settings_usd_egp: 'سعر الدولار مقابل الجنيه',
      settings_shipping: 'الشحن والمصاريف (دولار)',
      settings_sea_shipping: 'تكلفة الشحن البحري',
      settings_ths_cost: 'تكلفة THS',
      settings_clearance: 'مصاريف التخليص',
      settings_tax_rate: 'نسبة الضريبة (%)',
      settings_bank_commission: 'عمولة البنك (%)',
      settings_cylinder_prices: 'أسعار الأسطوانات (دولار/سم)',
      settings_width: 'العرض',
      settings_saved: 'تم حفظ الإعداد بنجاح!',
      settings_invalid: 'الرجاء إدخال رقم صحيح',

      // Audit Log
      audit_title: 'سجل العمليات',
      audit_no_logs: 'لا توجد سجلات',
      audit_time: 'الوقت',
      audit_user: 'المستخدم',
      audit_action: 'الإجراء',
      audit_table: 'الجدول',
      audit_record: 'رقم السجل',

      // Pagination
      pagination_page: 'صفحة',
      pagination_of: 'من',
      pagination_items: 'عنصر',

      // Notifications
      notif_processing: 'جاري المعالجة',
      notif_error_loading: 'خطأ في تحميل البيانات',

      // Launcher
      launcher_title: 'حلوان بلاست',
      launcher_subtitle: 'نظام إدارة عروض الأسعار',
      launcher_calculator: 'حاسبة الأسعار',
      launcher_calculator_desc: 'حساب أسعار أعمال الطباعة',
      launcher_admin: 'لوحة التحكم',
      launcher_admin_desc: 'إدارة المستخدمين والعملاء والعروض',

      // Calculator
      calc_title: 'حاسبة الأسعار',
      calc_client_info: 'بيانات العميل',
      calc_product_specs: 'مواصفات المنتج',
      calc_pricing: 'التسعير',
      calc_summary: 'الملخص',
      calc_new_quotation: 'عرض سعر جديد',
      calc_save_quotation: 'حفظ العرض',
      calc_print: 'طباعة',
      calc_client_name: 'اسم العميل',
      calc_client_code: 'كود العميل',
      calc_select_client: 'اختر العميل',
      calc_new_client: 'عميل جديد',

      // Language
      language: 'اللغة',
      lang_english: 'English',
      lang_arabic: 'العربية',
    }
  };

  // ============================================
  // i18n CLASS
  // ============================================
  class I18n {
    constructor() {
      this.currentLang = localStorage.getItem('hp_language') || 'en';
      this.listeners = [];
    }

    // Get current language
    getLang() {
      return this.currentLang;
    }

    // Set language
    setLang(lang) {
      if (lang !== 'en' && lang !== 'ar') return;

      this.currentLang = lang;
      localStorage.setItem('hp_language', lang);

      // Update document direction
      document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
      document.documentElement.lang = lang;

      // Add/remove RTL class
      if (lang === 'ar') {
        document.body.classList.add('rtl');
      } else {
        document.body.classList.remove('rtl');
      }

      // Notify listeners
      this.listeners.forEach(fn => fn(lang));

      // Dispatch event for other scripts
      window.dispatchEvent(new CustomEvent('languageChanged', { detail: { lang } }));
    }

    // Toggle language
    toggleLang() {
      this.setLang(this.currentLang === 'en' ? 'ar' : 'en');
    }

    // Get translation
    t(key, replacements = {}) {
      let text = translations[this.currentLang][key] || translations['en'][key] || key;

      // Replace placeholders like {name}
      Object.keys(replacements).forEach(k => {
        text = text.replace(new RegExp(`\\{${k}\\}`, 'g'), replacements[k]);
      });

      return text;
    }

    // Check if RTL
    isRTL() {
      return this.currentLang === 'ar';
    }

    // Add language change listener
    onLangChange(callback) {
      this.listeners.push(callback);
    }

    // Remove listener
    offLangChange(callback) {
      this.listeners = this.listeners.filter(fn => fn !== callback);
    }

    // Initialize - call on page load
    init() {
      this.setLang(this.currentLang);
    }

    // Get language switcher HTML
    getSwitcherHTML(style = 'dropdown') {
      const isAr = this.currentLang === 'ar';

      if (style === 'button') {
        return `
          <button class="lang-switch-btn" onclick="window.i18n.toggleLang()" title="${this.t('language')}">
            <span class="lang-icon">🌐</span>
            <span class="lang-text">${isAr ? 'EN' : 'ع'}</span>
          </button>
        `;
      }

      return `
        <div class="lang-switcher">
          <select onchange="window.i18n.setLang(this.value)" class="lang-select">
            <option value="en" ${!isAr ? 'selected' : ''}>🇬🇧 English</option>
            <option value="ar" ${isAr ? 'selected' : ''}>🇸🇦 العربية</option>
          </select>
        </div>
      `;
    }
  }

  // ============================================
  // CSS FOR RTL AND LANGUAGE SWITCHER
  // ============================================
  const rtlStyles = `
    /* RTL Base Styles */
    html[dir="rtl"] {
      direction: rtl;
    }

    body.rtl {
      text-align: right;
    }

    /* RTL Sidebar */
    body.rtl .sidebar {
      left: auto;
      right: 0;
    }

    body.rtl .main-content {
      padding-left: 32px;
      padding-right: calc(260px + 32px);
    }

    body.rtl .nav-item {
      border-left: none;
      border-right: 3px solid transparent;
    }

    body.rtl .nav-item.active {
      border-right-color: #667eea;
    }

    body.rtl .nav-item svg {
      margin-right: 0;
      margin-left: 12px;
    }

    body.rtl .nav-item .badge {
      margin-left: 0;
      margin-right: auto;
    }

    body.rtl .user-avatar {
      margin-right: 0;
      margin-left: 10px;
    }

    /* RTL Tables */
    body.rtl .data-table th,
    body.rtl .data-table td {
      text-align: right;
    }

    body.rtl .data-table .actions {
      flex-direction: row-reverse;
    }

    /* RTL Forms */
    body.rtl .search-box svg {
      left: auto;
      right: 14px;
    }

    body.rtl .search-box input {
      padding-left: 16px;
      padding-right: 44px;
    }

    body.rtl .form-group label {
      text-align: right;
    }

    /* RTL Modals */
    body.rtl .modal-header {
      flex-direction: row-reverse;
    }

    body.rtl .modal-footer {
      flex-direction: row-reverse;
    }

    /* RTL Notifications */
    body.rtl #notificationContainer {
      right: auto;
      left: 20px;
    }

    body.rtl .notification-toast {
      border-left: none;
      border-right: 4px solid #667eea;
      flex-direction: row-reverse;
    }

    body.rtl .notification-toast.success { border-right-color: #4caf50; }
    body.rtl .notification-toast.error { border-right-color: #f44336; }
    body.rtl .notification-toast.warning { border-right-color: #ff9800; }
    body.rtl .notification-toast.info { border-right-color: #2196f3; }

    @keyframes slideInRTL {
      from { transform: translateX(-100%); opacity: 0; }
      to { transform: translateX(0); opacity: 1; }
    }

    body.rtl .notification-toast {
      animation: slideInRTL 0.3s ease;
    }

    /* RTL Stats Grid */
    body.rtl .stat-card {
      text-align: right;
    }

    /* RTL Page Header */
    body.rtl .page-header {
      flex-direction: row-reverse;
    }

    /* RTL Toolbar */
    body.rtl .toolbar {
      flex-direction: row-reverse;
    }

    /* RTL Pagination */
    body.rtl .pagination {
      flex-direction: row-reverse;
    }

    /* Language Switcher Styles */
    .lang-switch-btn {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 8px 12px;
      background: rgba(255,255,255,0.1);
      border: 1px solid rgba(255,255,255,0.2);
      border-radius: 8px;
      color: #fff;
      cursor: pointer;
      font-size: 14px;
      transition: all 0.2s ease;
    }

    .lang-switch-btn:hover {
      background: rgba(255,255,255,0.2);
    }

    .lang-select {
      padding: 8px 12px;
      border: 2px solid #e0e0e0;
      border-radius: 8px;
      background: white;
      font-size: 14px;
      cursor: pointer;
      outline: none;
    }

    .lang-select:focus {
      border-color: #667eea;
    }

    /* Login Page Language Switcher */
    .login-lang-switcher {
      position: absolute;
      top: 20px;
      right: 20px;
    }

    body.rtl .login-lang-switcher {
      right: auto;
      left: 20px;
    }

    /* Responsive RTL */
    @media (max-width: 768px) {
      body.rtl .sidebar {
        transform: translateX(100%);
      }

      body.rtl .sidebar.open {
        transform: translateX(0);
      }

      body.rtl .main-content {
        padding-right: 20px;
        padding-left: 20px;
      }
    }

    @media (min-width: 1024px) {
      body.rtl .main-content {
        margin-left: 0;
        margin-right: 260px;
      }
    }
  `;

  // Inject RTL styles
  const styleSheet = document.createElement('style');
  styleSheet.textContent = rtlStyles;
  document.head.appendChild(styleSheet);

  // Create and export i18n instance
  window.i18n = new I18n();

  // Auto-init when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => window.i18n.init());
  } else {
    window.i18n.init();
  }

})();


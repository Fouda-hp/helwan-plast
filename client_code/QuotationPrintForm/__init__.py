from ._anvil_designer import QuotationPrintFormTemplate
from anvil import *
import anvil.users
import anvil.server
import anvil.js
import logging

try:
    from ..notif_bridge import register_notif_bridges
except ImportError:
    from notif_bridge import register_notif_bridges

logger = logging.getLogger(__name__)


def _h(value):
  """HTML-escape a value to prevent XSS injection"""
  if value is None:
    return ''
  s = str(value)
  return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#x27;')


class QuotationPrintForm(QuotationPrintFormTemplate):
  def __init__(self, **properties):
    self.init_components(**properties)

    # State
    self.current_lang = 'ar'
    self.current_data = None
    self.all_quotations = []
    self.custom_delivery_date = ''  # User-entered delivery date

    # Expose functions to JavaScript
    anvil.js.window.loadQuotationForPrint = self.load_quotation_for_print
    anvil.js.window.searchQuotationsForPrint = self.search_quotations_for_print
    anvil.js.window.getQuotationPdfData = self.get_quotation_pdf_data
    anvil.js.window.getAllSettings = self.get_all_settings

    # UI Functions
    anvil.js.window.goBackToLauncher = self.go_back
    anvil.js.window.loadSelectedQuotation = self.load_selected_quotation
    anvil.js.window.filterQuotations = self.filter_quotations
    anvil.js.window.switchLanguage = self.switch_language
    anvil.js.window.printQuotation = self.print_quotation
    anvil.js.window.exportPDF = self.export_pdf
    anvil.js.window.exportExcel = self.export_excel
    anvil.js.window.updateDeliveryDate = self.update_delivery_date

    # Notification bridges
    register_notif_bridges()

  def _show_msg(self, msg, typ='error'):
    """عرض رسالة من نظام التطبيق بدل alert البراوزر"""
    try:
      anvil.js.window.showNotification(typ, '', str(msg))
    except Exception:
      pass

  def form_show(self, **event_args):
    """Called when the form is shown - initialize after HTML is rendered"""
    self.init_page()

  def init_page(self):
    """Initialize the page"""
    # Auto-detect language from localStorage
    saved_lang = anvil.js.window.localStorage.getItem('hp_language')
    if saved_lang in ['ar', 'en']:
      self.current_lang = saved_lang
      self.update_language_buttons()

    # Load quotations list
    self.load_quotations_list()

  def update_language_buttons(self):
    """Update language button states"""
    btn_ar = anvil.js.window.document.getElementById('btnArabic')
    btn_en = anvil.js.window.document.getElementById('btnEnglish')
    if btn_ar and btn_en:
      if self.current_lang == 'ar':
        btn_ar.classList.add('active')
        btn_en.classList.remove('active')
      else:
        btn_ar.classList.remove('active')
        btn_en.classList.add('active')

  def go_back(self):
    """Go back to launcher"""
    anvil.js.window.location.hash = '#launcher'

  def load_quotations_list(self):
    """Load all quotations for dropdown"""
    try:
      auth = anvil.js.window.sessionStorage.getItem('auth_token') or anvil.js.window.sessionStorage.getItem('user_email') or None
      result = anvil.server.call('get_quotations_list', '', False, auth)
      if result and result.get('success'):
        self.all_quotations = result.get('data', [])
        self.populate_dropdown(self.all_quotations)
    except Exception as e:
      logger.debug("Error loading quotations: %s", e)

  def populate_dropdown(self, quotations):
    """Populate the quotation dropdown"""
    select = anvil.js.window.document.getElementById('quotationSelect')
    if not select:
      return

    # Clear and add default option
    select.innerHTML = f'<option value="">-- Select Quotation ({len(quotations)}) --</option>'

    # Add quotations: عرض "اسم العميل - اسم الشركة" من الجدول
    for q in quotations:
      opt = anvil.js.window.document.createElement('option')
      opt.value = str(q.get('Quotation#', ''))
      client_name = q.get('Client Name', '') or 'N/A'
      company = q.get('Company', '') or ''
      client_display = f"{client_name} - {company}".strip(' - ') if company else client_name
      opt.textContent = f"#{q.get('Quotation#', '')} - {client_display} - {q.get('Model', '')}"
      select.appendChild(opt)

  def filter_quotations(self):
    """Filter quotations based on search input"""
    search_input = anvil.js.window.document.getElementById('searchInput')
    if not search_input:
      return

    query = str(search_input.value).lower()

    if not query:
      self.populate_dropdown(self.all_quotations)
      return

    filtered = []
    for q in self.all_quotations:
      num = str(q.get('Quotation#', '')).lower()
      name = str(q.get('Client Name', '')).lower()
      company = str(q.get('Company', '')).lower()
      model = str(q.get('Model', '')).lower()
      if query in num or query in name or query in company or query in model:
        filtered.append(q)

    self.populate_dropdown(filtered)

  def load_selected_quotation(self):
    """Load the selected quotation"""
    select = anvil.js.window.document.getElementById('quotationSelect')
    if not select or not select.value:
      # Show empty state
      empty_state = anvil.js.window.document.getElementById('emptyState')
      template_content = anvil.js.window.document.getElementById('templateContent')
      if empty_state:
        empty_state.style.display = 'block'
      if template_content:
        template_content.style.display = 'none'
      return

    quotation_number = int(select.value)

    # Hide empty state, show loading
    empty_state = anvil.js.window.document.getElementById('emptyState')
    template_content = anvil.js.window.document.getElementById('templateContent')
    if empty_state:
      empty_state.style.display = 'none'
    if template_content:
      template_content.style.display = 'block'
      template_content.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;padding:60px 20px;">' + (str(anvil.js.window.HAND_LOADER_HTML) if anvil.js.window.HAND_LOADER_HTML else 'Loading...') + '</div>'

    try:
      user_email = anvil.js.window.sessionStorage.getItem('user_email') or ''
      auth_token = anvil.js.window.sessionStorage.getItem('auth_token') or None
      result = anvil.server.call('get_quotation_pdf_data', quotation_number, user_email, auth_token)

      if result and result.get('success'):
        self.current_data = result.get('data')
        self.render_template()
      else:
        err_msg = _h(result.get("message", "Failed to load") if result else "Server returned empty response")
        template_content.innerHTML = f'<div class="empty-state"><h3>Error</h3><p>{err_msg}</p></div>'
    except Exception as e:
      template_content.innerHTML = f'<div class="empty-state"><h3>Error</h3><p>{_h(str(e))}</p></div>'

  def switch_language(self, lang):
    """Switch display language"""
    self.current_lang = lang
    self.update_language_buttons()

    if self.current_data:
      self.render_template()

  def update_delivery_date(self):
    """Update delivery date from input field and re-render"""
    delivery_input = anvil.js.window.document.getElementById('deliveryDateInput')
    if delivery_input:
      self.custom_delivery_date = str(delivery_input.value).strip()
      if self.current_data:
        self.render_template()

  def render_template(self):
    """Render the quotation template - 3 pages without page breaks"""
    if not self.current_data:
      return

    data = self.current_data
    c = data.get('company', {})
    is_ar = (self.current_lang == 'ar')

    # Get machine model, machine type, and material for conditional logic
    model = str(data.get('model', '')).upper()
    machine_type_str = str(data.get('machine_type', '') or data.get('model', '')).upper()
    material = str(data.get('material', '')).upper()
    plc_value = str(data.get('plc', '')).upper()
    # Gear only when machine_type is Metal Anilox and material is NOT Nonwoven; else Belt
    is_metal_anilox = 'METAL' in machine_type_str
    is_nonwoven = 'NONWOVEN' in material

    # Determine machine type prefix - use machine_type field not model
    machine_type_base = data.get('machine_type', '') or data.get('model', '')
    machine_type_display = f"Flexo Stack With {machine_type_base}" if not is_ar else f"فليكسو ستاك مع {machine_type_base}"

    # Determine Winder Type based on Unwind/Rewind checkboxes
    def get_winder_type():
      unwind_options = []
      rewind_options = []

      # Check Unwind options
      if str(data.get('pneumatic_unwind', '')).upper() in ['YES', 'TRUE', '1']:
        unwind_options.append('Pneumatic Unwind' if not is_ar else 'فك هوائي')
      if str(data.get('hydraulic_station_unwind', '')).upper() in ['YES', 'TRUE', '1']:
        unwind_options.append('Hydraulic Station Unwind' if not is_ar else 'فك هيدروليك')

      # Check Rewind options
      if str(data.get('pneumatic_rewind', '')).upper() in ['YES', 'TRUE', '1']:
        rewind_options.append('Pneumatic Rewind' if not is_ar else 'لف هوائي')
      if str(data.get('surface_rewind', '')).upper() in ['YES', 'TRUE', '1']:
        rewind_options.append('Surface Rewind' if not is_ar else 'لف سطحي')

      # Build winder type string
      if not unwind_options and not rewind_options:
        return 'Central' if not is_ar else 'مركزي'

      parts = []
      if unwind_options:
        parts.append(', '.join(unwind_options))
      if rewind_options:
        parts.append(', '.join(rewind_options))

      return ' / '.join(parts)

    winder_type_display = get_winder_type()

    # ==================== PAGE 1 ====================
    html = f'<div class="template-page {"" if is_ar else "ltr"}">'

    # Header
    html += '<div class="header">'
    html += '<div class="header-right">'
    html += f'<div class="location-date">{_h(c.get("quotation_location_ar" if is_ar else "quotation_location_en", ""))} / {_h(data.get("quotation_date_ar" if is_ar else "quotation_date_en", ""))}</div>'
    html += f'<div class="address">{_h(c.get("company_address_ar" if is_ar else "company_address_en", ""))}</div>'
    html += f'<div class="contact">{_h(data.get("sales_rep_phone", ""))}</div>'
    html += f'<div class="contact">{_h(data.get("sales_rep_email", ""))}</div>'
    html += '</div>'
    html += '<div class="header-left">'
    html += '<img src="_/theme/helwan_logo.png" class="logo" alt="Logo">'
    html += f'<div class="company-name">{_h(c.get("company_name_ar" if is_ar else "company_name_en", ""))}</div>'
    html += f'<div class="website">{_h(c.get("company_website", ""))}</div>'
    html += '</div>'
    html += '</div>'

    # Quotation Info
    html += '<div class="quotation-info">'
    html += f'<div class="quotation-number">{"عرض سعر رقم" if is_ar else "Quotation No.:"} <span>{data.get("quotation_number", "")}</span></div>'
    client_name = data.get("client_name", "") or ""
    company = data.get("client_company", "") or ""
    client_display = f"{client_name} - {company}".strip(" - ") if company else client_name
    html += f'<div class="client-info">{"السادة - شركة /" if is_ar else "To: / Company:"} <span>{_h(client_display)}</span></div>'
    html += f'<div class="greeting">{"تحية طيبة وبعد،" if is_ar else "Dear Sir/Madam,"}</div>'
    intro = 'نحن نتشرف بتقديم عرض السعر التالي لماكينة الطباعة طبقاً للمواصفات الموضحة أدناه:' if is_ar else 'We are pleased to submit our quotation for the following printing machine in accordance with the specifications detailed below:'
    html += f'<div class="intro-text">{intro}</div>'
    html += '</div>'

    # Machine Details
    html += f'<div class="section-title">{"تفاصيل الماكينة :" if is_ar else "Machine Details"}</div>'
    html += '<table class="details-table">'

    # Both Arabic and English: label (th) on left, value (td) on right
    if is_ar:
      html += f'<tr><th>نوع الماكينة :</th><td>{machine_type_display}</td></tr>'
      html += f'<tr><th>الموديل :</th><td>{data.get("model", "")}</td></tr>'
      html += f'<tr><th>بلد المنشأ :</th><td>{c.get("country_origin_ar", "")}</td></tr>'
      html += f'<tr><th>عدد الألوان :</th><td>{data.get("colors_count", "")}</td></tr>'
      html += f'<tr><th>الوندر :</th><td>{data.get("winder", "")}</td></tr>'
      html += f'<tr><th>نوع الوندر :</th><td>{winder_type_display}</td></tr>'
      html += f'<tr><th>عرض الماكينة :</th><td>{data.get("machine_width", "")} سم</td></tr>'
    else:
      # English: label on far left, value next to it
      html += f'<tr><th>Machine Type:</th><td>{machine_type_display}</td></tr>'
      html += f'<tr><th>Model:</th><td>{data.get("model", "")}</td></tr>'
      html += f'<tr><th>Country of Origin:</th><td>{c.get("country_origin_en", "")}</td></tr>'
      html += f'<tr><th>Number of Colors:</th><td>{data.get("colors_count", "")}</td></tr>'
      html += f'<tr><th>Winder:</th><td>{data.get("winder", "")}</td></tr>'
      html += f'<tr><th>Winder Type:</th><td>{winder_type_display}</td></tr>'
      html += f'<tr><th>Machine Width:</th><td>{data.get("machine_width", "")} CM</td></tr>'
    html += '</table>'

    # ==================== 17 SPECIFICATIONS ====================
    html += f'<div class="section-title">{"المواصفات الفنية:" if is_ar else "Technical Specifications:"}</div>'
    html += '<ol class="specs-list" style="font-size: 14px; line-height: 1.8; padding-right: 18px; padding-left: 18px; white-space: normal; word-break: break-word;">'

    # Helper: Belt/Gear drive for item 13 (uses is_metal_anilox, is_nonwoven from above)
    def get_drive_type():
      if is_metal_anilox and not is_nonwoven:
        return ('نقل الحركه من الموتور الرئيسي لأجزاء الماكينة عن طريق التروس' if is_ar else 'Gear drive',
                'نقل الحركه من الموتور الرئيسي إلى مكونات الماكينة عبر التروس لضمان عمر أطول، تقليل الأعطال، وتمكين التشغيل بسرعة عالية وهدوء مع تصميم غير معقد' if is_ar else 'Power transmission from the main motor to machine components via Gear drive to ensure longer service life, reduce breakdowns, and enable high-speed, quiet operation with a non-complex gear design')
      else:
        return ('نقل الحركه من الموتور الرئيسي لأجزاء الماكينة عن طريق السيور' if is_ar else 'Belt drive',
                'نقل الحركه من الموتور الرئيسي إلى مكونات الماكينة عبر السيور لضمان عمر أطول، تقليل الأعطال، وتمكين التشغيل بسرعة عالية وهدوء مع تصميم غير معقد' if is_ar else 'Power transmission from the main motor to machine components via Belt drive to ensure longer service life, reduce breakdowns, and enable high-speed, quiet operation with a non-complex gear design')

    # Helper function for item 7 (color registration)
    def get_color_registration():
      is_plc_yes = plc_value in ['YES', 'TRUE', '1', 'نعم']
      if is_plc_yes:
        return ('ضبط تسجيل الألوان الأفقي والرأسي أوتوماتيكياً أثناء التشغيل' if is_ar else 'Automatically horizontal and vertical color registration adjustment during operation')
      else:
        return ('ضبط تسجيل الألوان الأفقي والرأسي يدوياً أثناء التشغيل' if is_ar else 'Manual horizontal and vertical color registration adjustment during operation')

    drive_type, drive_desc = get_drive_type()
    color_reg = get_color_registration()

    # 17 Specifications
    specs_en = [
        "Heavy-duty cast iron frame, stable and vibration-resistant",
        "Automatic web tension control units suitable for different material weights, thicknesses, and flexibility, with manual adjustment option",
        "Web guiding (oscillating) units to ensure accurate print centering on the substrate and smooth rewinding of printed material",
        "Rollers and cylinders laser-treated for heavy-duty operation and extended service life",
        "Automatic machine stop sensors in case of film breakage or material run-out",
        "Printing cylinder pressure applied via hydraulic oil system to avoid pneumatic pressure issues and reduce electrical consumption caused by repeated air compressor operation",
        color_reg if not is_ar else color_reg,
        "Integrated overhead lifting cranes to facilitate loading and unloading of rolls and printing cylinders, saving time, labor, and effort",
        "Suitable for solvent-based and water-based inks",
        "Delta (Taiwan) inverters",
        "Safety alarm before machine start-up to prevent injuries",
        "Hot air drying units with extended web path to ensure complete ink drying, in addition to inter-color drying units",
        drive_desc if not is_ar else drive_desc,
        "Integrated lubrication pumps to ensure balanced oil distribution to all components, smooth operation, and protection of all moving parts",
        "Separate rewind motors with independent control to allow operation with different flexibility and thicknesses of materials",
        "Air-shaft unwind/rewind cylinders, in addition to one extra mechanical shaft to enable operation with any core size",
        "Double-sided printing capability"
    ]

    specs_ar = [
        "هيكل من الحديد الزهر الثقيل، ثابت ومقاوم للاهتزازات",
        "وحدات تحكم أوتوماتيكية في شد الخامة مناسبة لأوزان وسماكات ومرونات مختلفة، مع خيار الضبط اليدوي",
        "وحدات توجيه الخامة (المتأرجحة) لضمان دقة توسيط الطباعة على الخامة وإعادة لف سلسة للمادة المطبوعة",
        "الأسطوانات معالجة بالليزر للتشغيل الشاق وإطالة عمر الخدمة",
        "مستشعرات إيقاف أوتوماتيكي للماكينة في حالة انقطاع الفيلم أو نفاد الخامة",
        "ضغط أسطوانة الطباعة يتم عبر نظام الزيت الهيدروليكي لتجنب مشاكل الضغط الهوائي وتقليل استهلاك الكهرباء الناتج عن تشغيل ضاغط الهواء المتكرر",
        get_color_registration(),
        "رافعات علويه مدمجة لتسهيل تحميل وتفريغ الرولات وأسطوانات الطباعة، مما يوفر الوقت والجهد والعمالة",
        "مناسبة لأحبار المذيبات والأحبار المائية",
        "إنفرترات دلتا (تايواني)",
        "إنذار أمان قبل بدء تشغيل الماكينة لمنع الإصابات",
        "وحدات تجفيف بالهواء الساخن مع مسار خامة ممتد لضمان جفاف الحبر الكامل، بالإضافة إلى وحدات تجفيف بين الألوان",
        get_drive_type()[1],
        "مضخات تشحيم مدمجة لضمان توزيع متوازن للزيت على جميع المكونات، تشغيل سلس، وحماية جميع الأجزاء المتحركة",
        "مواتير إعادة لف منفصلة بتحكم مستقل للسماح بالتشغيل مع مرونات وسماكات مختلفة للخامات",
        "أسطوانات فك/لف بشافت هوائي، بالإضافة إلى شافت ميكانيكي إضافي لتمكين التشغيل مع أي حجم كور",
        "إمكانية الطباعة على الوجهين"
    ]

    specs = specs_ar if is_ar else specs_en
    for i, spec in enumerate(specs, 1):
      html += f'<li>{spec}</li>'

    html += '</ol>'
    html += '</div>'  # End Page 1

    # ==================== PAGE 2 - Technical Table ====================
    html += f'<div class="template-page page-break-before {"" if is_ar else "ltr"}">'

    # Header (repeated)
    html += '<div class="header">'
    html += '<div class="header-right">'
    html += f'<div class="location-date">{_h(c.get("quotation_location_ar" if is_ar else "quotation_location_en", ""))} / {_h(data.get("quotation_date_ar" if is_ar else "quotation_date_en", ""))}</div>'
    html += f'<div class="address">{_h(c.get("company_address_ar" if is_ar else "company_address_en", ""))}</div>'
    html += f'<div class="contact">{_h(data.get("sales_rep_phone", ""))}</div>'
    html += f'<div class="contact">{_h(data.get("sales_rep_email", ""))}</div>'
    html += '</div>'
    html += '<div class="header-left">'
    html += '<img src="_/theme/helwan_logo.png" class="logo" alt="Logo">'
    html += f'<div class="company-name">{_h(c.get("company_name_ar" if is_ar else "company_name_en", ""))}</div>'
    html += f'<div class="website">{_h(c.get("company_website", ""))}</div>'
    html += '</div>'
    html += '</div>'

    html += f'<div class="section-title">{"جدول المواصفات الفنية:" if is_ar else "General Specifications:"}</div>'

    # ==================== CALCULATE TABLE VALUES ====================
    # Get values from quotation data
    winder_type = str(data.get('winder', '')).upper()
    is_double_winder = 'DOUBLE' in winder_type
    try:
      _colors = data.get('colors_count', 0)
      colors_count = int(_colors) if _colors not in (None, '') else 0
    except (TypeError, ValueError):
      colors_count = 0
    try:
      _mw = data.get('machine_width', 0)
      machine_width = float(_mw) if _mw not in (None, '') else 0.0
    except (TypeError, ValueError):
      machine_width = 0.0

    # Determine if Belt or Gear drive (is_metal_anilox, is_nonwoven already set above)
    is_belt_drive = not (is_metal_anilox and not is_nonwoven)

    # Get settings values with defaults
    belt_max_machine_speed = int(c.get('belt_max_machine_speed', 150))
    belt_max_print_speed = int(c.get('belt_max_print_speed', 120))
    belt_print_length = c.get('belt_print_length', '300mm - 1300mm')
    gear_max_machine_speed = int(c.get('gear_max_machine_speed', 100))
    gear_max_print_speed = int(c.get('gear_max_print_speed', 80))
    gear_print_length = c.get('gear_print_length', '240mm - 1000mm')
    single_winder_roll_dia = int(c.get('single_winder_roll_dia', 1200))
    double_winder_roll_dia = int(c.get('double_winder_roll_dia', 800))
    single_winder_brake_power = c.get('single_winder_brake_power', '1 pc (10kg) + 1 pc (5kg)')
    double_winder_brake_power = c.get('double_winder_brake_power', '2 pc (10kg) + 2 pc (5kg)')
    dryer_capacity = c.get('dryer_capacity', '2.2kw air blower × 2 units')
    main_motor_power = c.get('main_motor_power', '5 HP')

    # Helper: convert English digits to Arabic digits
    def to_ar(val):
      """Convert 0-9 to ٠-٩"""
      ar_digits = {'0': '٠', '1': '١', '2': '٢', '3': '٣', '4': '٤', '5': '٥', '6': '٦', '7': '٧', '8': '٨', '9': '٩'}
      return ''.join(ar_digits.get(ch, ch) for ch in str(val))

    # Calculate values based on rules
    # Number of Colors format
    if colors_count == 8:
      colors_display = "8+0, 7+1, 6+2, 5+3, 4+4 reverse printing" if not is_ar else f"{to_ar('8+0')}، {to_ar('7+1')}، {to_ar('6+2')}، {to_ar('5+3')}، {to_ar('4+4')} طباعة عكسية"
    elif colors_count == 6:
      colors_display = "6+0, 5+1, 4+2, 3+3 reverse printing" if not is_ar else f"{to_ar('6+0')}، {to_ar('5+1')}، {to_ar('4+2')}، {to_ar('3+3')} طباعة عكسية"
    elif colors_count == 4:
      colors_display = "4+0, 3+1, 2+2 reverse printing" if not is_ar else f"{to_ar('4+0')}، {to_ar('3+1')}، {to_ar('2+2')} طباعة عكسية"
    else:
      colors_display = str(colors_count) if not is_ar else to_ar(colors_count)

    # Values based on winder type (double=4/2, single=2/1)
    tension_units = 4 if is_double_winder else 2
    brake_system = 4 if is_double_winder else 2
    brake_power = double_winder_brake_power if is_double_winder else single_winder_brake_power
    web_guiding = 2 if is_double_winder else 1

    # Width calculations
    max_film_width = int(machine_width * 10 + 50)
    max_print_width = int(machine_width * 10 - 40)

    # Printing length based on drive type (from settings)
    print_length = belt_print_length if is_belt_drive else gear_print_length

    # Roll diameter based on winder (from settings)
    max_roll_diameter = double_winder_roll_dia if is_double_winder else single_winder_roll_dia

    # Anilox type
    anilox_display = ("Metal Anilox" if not is_ar else "انيلوكس معدني") if is_metal_anilox else ("Ceramic Anilox" if not is_ar else "انيلوكس سيراميك")

    # Speed based on drive type (from settings)
    max_machine_speed = belt_max_machine_speed if is_belt_drive else gear_max_machine_speed
    max_print_speed = belt_max_print_speed if is_belt_drive else gear_max_print_speed

    # Drive type display
    drive_display = ("Belt Drive" if not is_ar else "سيور") if is_belt_drive else ("Gear Drive" if not is_ar else "تروس")

    # Yes/No fields
    def yes_no_value(field_name):
      val = str(data.get(field_name, '')).upper()
      if val in ['YES', 'TRUE', '1', 'نعم']:
        return 'Yes' if not is_ar else 'نعم'
      return 'No' if not is_ar else 'لا'

    def is_yes_value(field_name):
      val = str(data.get(field_name, '')).upper()
      return val in ['YES', 'TRUE', '1', 'نعم']

    def normalize_values(values):
      if values is None:
        return []
      if isinstance(values, list):
        return [str(v).strip() for v in values if str(v).strip()]
      if isinstance(values, str):
        parts = []
        for chunk in values.replace(',', '\n').split('\n'):
          chunk = chunk.strip()
          if chunk:
            parts.append(chunk)
        return parts
      return []

    def default_specs():
      return [
        {'label_ar': 'الموديل', 'label_en': 'Model', 'source': 'field', 'values': ['model'], 'active': True},
        {'label_ar': 'عدد الألوان', 'label_en': 'Number of Colors', 'source': 'field', 'values': ['colors_display'], 'active': True},
        {'label_ar': 'أوجه الطباعة', 'label_en': 'Printing Sides', 'source': 'field', 'values': ['printing_sides'], 'active': True},
        {'label_ar': 'وحدات التحكم في الشد', 'label_en': 'Tension Control Units', 'source': 'field', 'values': ['tension_units'], 'active': True},
        {'label_ar': 'نظام الفرامل', 'label_en': 'Brake System', 'source': 'field', 'values': ['brake_system'], 'active': True},
        {'label_ar': 'قوة الفرامل', 'label_en': 'Brake Power', 'source': 'field', 'values': ['brake_power'], 'active': True},
        {'label_ar': 'نظام توجيه الخامة (النوع المتأرجح)', 'label_en': 'Web Guiding System (Oscillating Type)', 'source': 'field', 'values': ['web_guiding'], 'active': True},
        {'label_ar': 'أقصى عرض للفيلم', 'label_en': 'Maximum Film Width', 'source': 'field', 'values': ['max_film_width'], 'active': True},
        {'label_ar': 'أقصى عرض للطباعة', 'label_en': 'Maximum Printing Width', 'source': 'field', 'values': ['max_print_width'], 'active': True},
        {'label_ar': 'الحد الأدنى والأقصى لطول الطباعة', 'label_en': 'Minimum and Maximum Printing Length', 'source': 'field', 'values': ['print_length'], 'active': True},
        {'label_ar': 'أقصى قطر للرول', 'label_en': 'Maximum Roll Diameter', 'source': 'field', 'values': ['max_roll_diameter'], 'active': True},
        {'label_ar': 'نوع الأنيلوكس', 'label_en': 'Anilox Type', 'source': 'field', 'values': ['anilox_display'], 'active': True},
        {'label_ar': 'أقصى سرعة للماكينة', 'label_en': 'Maximum Machine Speed', 'source': 'field', 'values': ['max_machine_speed'], 'active': True},
        {'label_ar': 'أقصى سرعة للطباعة', 'label_en': 'Maximum Printing Speed', 'source': 'field', 'values': ['max_print_speed'], 'active': True},
        {'label_ar': 'قدرة المجفف', 'label_en': 'Dryer Capacity', 'source': 'field', 'values': ['dryer_capacity'], 'active': True},
        {'label_ar': 'طريقة نقل القدرة', 'label_en': 'Power Transmission Method', 'source': 'field', 'values': ['drive_display'], 'active': True},
        {'label_ar': 'قدرة الموتور الرئيسي', 'label_en': 'Main Motor Power', 'source': 'field', 'values': ['main_motor_power'], 'active': True},
        {'label_ar': 'الفحص بالفيديو', 'label_en': 'Video Inspection', 'source': 'yes_no', 'values': ['video_inspection'], 'active': True},
        {'label_ar': 'PLC', 'label_en': 'PLC', 'source': 'yes_no', 'values': ['plc'], 'active': True},
        {'label_ar': 'سليتر', 'label_en': 'Slitter', 'source': 'yes_no', 'values': ['slitter'], 'active': True},
      ]

    def normalize_specs(raw):
      defaults = default_specs()
      if isinstance(raw, list) and len(raw) > 0:
        first_item = raw[0] if raw else {}
        if first_item.get('label_en') or first_item.get('label_ar'):
          specs = []
          for spec in raw:
            if not spec.get('label_en') and not spec.get('label_ar'):
              continue
            specs.append({
              'label_ar': spec.get('label_ar', ''),
              'label_en': spec.get('label_en', ''),
              'source': spec.get('source', 'field'),
              'values': normalize_values(spec.get('values')),
              'active': spec.get('active', True) is not False,
            })
          return specs if specs else defaults
        return defaults
      if isinstance(raw, dict) and len(raw) > 0:
        first_key = next(iter(raw.keys()), None)
        if first_key and first_key.startswith('tech_spec_'):
          specs = []
          for i, default in enumerate(defaults, 1):
            saved = raw.get(f'tech_spec_{i}', {})
            if isinstance(saved, dict):
              specs.append({
                'label_ar': saved.get('label_ar', default['label_ar']),
                'label_en': saved.get('label_en', default['label_en']),
                'source': saved.get('source', default['source']),
                'values': normalize_values(saved.get('values') or saved.get('value_keys') or default['values']),
                'active': saved.get('active', True) is not False,
              })
            else:
              specs.append(default)
          return specs
      return defaults

    # Get tech_specs_settings from database
    tech_specs_settings = data.get('tech_specs_settings', None)
    specs_list = normalize_specs(tech_specs_settings)

    # Arabic brake power formatting
    def ar_brake_power(bp_str):
      """Convert '2 pc (10kg) + 2 pc (5kg)' to '٢ قطعة (١٠ كجم) + ٢ قطعة (٥ كجم)'"""
      import re
      parts = str(bp_str).split('+')
      ar_parts = []
      for part in parts:
        part = part.strip()
        m = re.match(r'(\d+)\s*pc\s*\((\d+)kg\)', part)
        if m:
          ar_parts.append(f"{to_ar(m.group(1))} قطعة ({to_ar(m.group(2))} كجم)")
        else:
          ar_parts.append(to_ar(part))
      return ' + '.join(ar_parts)

    # Arabic dryer capacity formatting
    def ar_dryer(dc_str):
      """Convert '2.2kw air blower × 2 units' to '٢.٢ كيلو وات تجفيف هوائي × ٢'"""
      import re
      m = re.match(r'([\d.]+)kw\s*air\s*blower\s*[×x]\s*(\d+)\s*units?', str(dc_str), re.IGNORECASE)
      if m:
        return f"{to_ar(m.group(1))} كيلو وات تجفيف هوائي × {to_ar(m.group(2))}"
      return to_ar(dc_str)

    # Arabic print length formatting
    def ar_print_length(pl_str):
      """Convert '300mm - 1300mm' to '٣٠٠ مم - ١٣٠٠ مم'"""
      import re
      m = re.match(r'(\d+)\s*mm\s*-\s*(\d+)\s*mm', str(pl_str), re.IGNORECASE)
      if m:
        return f"{to_ar(m.group(1))} مم - {to_ar(m.group(2))} مم"
      return to_ar(pl_str)

    if is_ar:
      value_map = {
        'model': data.get('model', '-'),
        'colors_display': colors_display,
        'printing_sides': to_ar('2'),
        'tension_units': f"{to_ar(tension_units)} قطعة",
        'brake_system': f"{to_ar(brake_system)} قطعة",
        'brake_power': ar_brake_power(brake_power),
        'web_guiding': f"{to_ar(web_guiding)} قطعة",
        'max_film_width': f"{to_ar(max_film_width)} مم",
        'max_print_width': f"{to_ar(max_print_width)} مم",
        'print_length': ar_print_length(print_length),
        'max_roll_diameter': f"{to_ar(max_roll_diameter)} مم",
        'anilox_display': anilox_display,
        'max_machine_speed': f"{to_ar(max_machine_speed)} متر في الدقيقة",
        'max_print_speed': f"{to_ar(max_print_speed)} متر في الدقيقة",
        'dryer_capacity': ar_dryer(dryer_capacity),
        'drive_display': drive_display,
        'main_motor_power': f"{to_ar(main_motor_power.replace('HP', '').replace('hp', '').strip())} حصان",
      }
    else:
      value_map = {
        'model': data.get('model', '-'),
        'colors_display': colors_display,
        'printing_sides': '2',
        'tension_units': str(tension_units),
        'brake_system': str(brake_system),
        'brake_power': brake_power,
        'web_guiding': str(web_guiding),
        'max_film_width': f"{max_film_width} mm",
        'max_print_width': f"{max_print_width} mm",
        'print_length': print_length,
        'max_roll_diameter': f"{max_roll_diameter} mm",
        'anilox_display': anilox_display,
        'max_machine_speed': f"{max_machine_speed} m/min",
        'max_print_speed': f"{max_print_speed} m/min",
        'dryer_capacity': dryer_capacity,
        'drive_display': drive_display,
        'main_motor_power': main_motor_power,
      }

    def resolve_value(key):
      if key in value_map:
        return value_map[key]
      return data.get(key, '')

    html += '<table class="tech-table">'
    row_num = 1
    for spec in specs_list:
      if not spec.get('active', True):
        continue
      label = spec.get('label_ar', '') if is_ar else spec.get('label_en', '')
      source = spec.get('source', 'field')
      values = normalize_values(spec.get('values'))
      if source == 'fixed':
        value_parts = values or ['-']
        value_text = '<br>'.join(value_parts)
      elif source == 'yes_no':
        if not values:
          continue
        show_row = any(is_yes_value(v) for v in values)
        if not show_row:
          continue
        value_text = 'نعم' if is_ar else 'Yes'
      elif source == 'custom':
        condition_field = spec.get('condition_field', '')
        condition_value = str(spec.get('condition_value', '')).upper().strip()
        then_value = spec.get('then_value', '')
        else_value = spec.get('else_value', '')
        condition_map = {
          'winder_type': winder_type,
          'drive_type': 'BELT' if is_belt_drive else 'GEAR',
          'anilox_type': 'METAL' if is_metal_anilox else 'CERAMIC',
          'colors_count': str(colors_count),
          'machine_width': str(int(machine_width)),
          'video_inspection': 'YES' if is_yes_value('video_inspection') else 'NO',
          'plc': 'YES' if is_yes_value('plc') else 'NO',
          'slitter': 'YES' if is_yes_value('slitter') else 'NO',
        }
        actual_value = str(condition_map.get(condition_field, '')).upper().strip()
        condition_values = [v.strip().upper() for v in condition_value.split(',')]
        if actual_value in condition_values:
          value_text = then_value
        else:
          value_text = else_value
        if not value_text:
          continue
      else:
        value_parts = []
        for key in values:
          resolved = resolve_value(key)
          if resolved not in [None, '']:
            value_parts.append(str(resolved))
        value_text = '<br>'.join(value_parts) if value_parts else '-'
      value_upper = str(value_text).strip().upper()
      if value_upper in ['NO', 'لا', 'N/A', '-', '']:
        continue
      val_style = ' style="text-align:right;"' if is_ar else ''
      html += f'<tr><td class="row-num">{row_num}</td><th>{label}</th><td class="value"{val_style}>{value_text}</td></tr>'
      row_num += 1
    html += '</table>'

    # Cylinders - 2 columns, 12 rows fixed (border only on filled rows)
    cylinders = data.get('cylinders', [])
    html += f'<div class="section-title">{"سلندرات الطباعة :" if is_ar else "Printing Cylinders:"}</div>'
    html += '<table class="cylinders-table" style="width: 50%;">'
    html += f'<tr><th>{"مقاس" if is_ar else "Size"}</th><th>{"عدد" if is_ar else "Count"}</th></tr>'
    for i in range(12):
      if i < len(cylinders):
        cyl = cylinders[i]
        size = cyl.get("size", "")
        count = cyl.get("count", "")
        html += f'<tr><td style="border: 1px solid #ddd;">{size}</td><td style="border: 1px solid #ddd;">{count}</td></tr>'
      else:
        html += '<tr><td style="border: none;"></td><td style="border: none;"></td></tr>'
    html += '</table>'

    html += '</div>'  # End Page 2

    # ==================== PAGE 3 - Financial ====================
    html += f'<div class="template-page page-break-before {"" if is_ar else "ltr"}">'

    # Header (repeated)
    html += '<div class="header">'
    html += '<div class="header-right">'
    html += f'<div class="location-date">{_h(c.get("quotation_location_ar" if is_ar else "quotation_location_en", ""))} / {_h(data.get("quotation_date_ar" if is_ar else "quotation_date_en", ""))}</div>'
    html += f'<div class="address">{_h(c.get("company_address_ar" if is_ar else "company_address_en", ""))}</div>'
    html += f'<div class="contact">{_h(data.get("sales_rep_phone", ""))}</div>'
    html += f'<div class="contact">{_h(data.get("sales_rep_email", ""))}</div>'
    html += '</div>'
    html += '<div class="header-left">'
    html += '<img src="_/theme/helwan_logo.png" class="logo" alt="Logo">'
    html += f'<div class="company-name">{_h(c.get("company_name_ar" if is_ar else "company_name_en", ""))}</div>'
    html += f'<div class="website">{_h(c.get("company_website", ""))}</div>'
    html += '</div>'
    html += '</div>'

    html += f'<div class="section-title">{"العرض المالي:" if is_ar else "Financial Offer:"}</div>'

    # Get pricing mode
    pricing_mode = str(data.get('pricing_mode', '')).upper()
    is_in_stock = 'STOCK' in pricing_mode

    html += '<div class="financial-box">'
    html += f'<div class="total-price">{data.get("total_price", "")} {"ج.م" if is_ar else "EGP"}</div>'
    price_note = 'السعر شامل التوريد والتركيب والضمان' if is_ar else 'The price includes: supply, installation, and warranty'
    html += f'<div class="price-notes">{price_note}</div>'

    html += f'<div class="section-title">{"طريقة الدفع:" if is_ar else "Payment Terms:"}</div>'
    if is_in_stock:
      html += '<ul class="payment-list-simple" style="list-style: disc; padding-left: 25px; font-size: 14px; line-height: 1.8;">'
      html += f'<li>{"مقدم تعاقد" if is_ar else "Down Payment"}</li>'
      html += f'<li>{"الدفع قبل الشحن" if is_ar else "Payment before shipping"}</li>'
      html += '</ul>'
    else:
      html += '<table class="payment-table">'
      html += f'<tr><th>{"مقدم تعاقد" if is_ar else "Down Payment"}</th><td>{data.get("down_payment_percent", "")}%</td><td class="amount">{data.get("down_payment_amount", "")} {"ج.م" if is_ar else "EGP"}</td></tr>'
      html += f'<tr><th>{"قبل الشحن" if is_ar else "Before Shipping"}</th><td>{data.get("before_shipping_percent", "")}%</td><td class="amount">{data.get("before_shipping_amount", "")} {"ج.م" if is_ar else "EGP"}</td></tr>'
      html += f'<tr><th>{"قبل التسليم" if is_ar else "Before Delivery"}</th><td>{data.get("before_delivery_percent", "")}%</td><td class="amount">{data.get("before_delivery_amount", "")} {"ج.م" if is_ar else "EGP"}</td></tr>'
      html += '</table>'

    html += '</div>'

    # Delivery & Warranty
    html += '<div class="info-grid">'
    html += '<div class="info-box">'
    html += f'<h4>{"التسليم :" if is_ar else "Delivery:"}</h4>'
    html += f'<p>{"مكان التسليم :" if is_ar else "Place of delivery:"} <span class="highlight">{data.get("delivery_location", "-")}</span></p>'
    if is_in_stock:
      delivery_time = "بضاعه حاضره" if is_ar else "In Stock"
    else:
      if self.custom_delivery_date:
        delivery_time = self.custom_delivery_date
      else:
        delivery_time = data.get("expected_delivery_formatted", "-")
    html += f'<p>{"وقت التسليم المتوقع :" if is_ar else "Expected delivery time:"} <span class="highlight">{delivery_time}</span></p>'
    html += '</div>'

    html += '<div class="info-box">'
    html += f'<h4>{"الضمان وخدمة ما بعد البيع:" if is_ar else "Warranty & After-Sales Service:"}</h4>'
    warranty_text = f'يسري الضمان لمدة <strong>{c.get("warranty_months", "")}</strong> شهر ضد عيوب الصناعة' if is_ar else f'The warranty is valid for <strong>{c.get("warranty_months", "")}</strong> months against manufacturing defects'
    html += f'<p>{warranty_text}</p>'
    html += '</div>'
    html += '</div>'

    # Notes
    html += '<div class="notes-section">'
    html += f'<h4>{"ملاحظات:" if is_ar else "Notes:"}</h4>'
    html += '<div class="notes-list">'
    note1 = f'عرض السعر ساري لمدة {c.get("validity_days", "")} يوم من تاريخ عرض السعر' if is_ar else f'This quotation is valid for {c.get("validity_days", "")} days from the quotation date'
    note2 = 'يتم تعديل السعر في حالة ارتفاع سعر صرف الدولار بقيمة تزيد عن ٥٠ قرش' if is_ar else 'The price may be adjusted in case of an increase in the USD exchange rate exceeding EGP 0.50'
    note3 = 'هذا العرض استرشادي وغير ملزم إلا بعد توقيع العقد النهائي' if is_ar else 'This quotation is indicative and non-binding until the final contract is signed'
    html += f'<p>• {note1}</p>'
    html += f'<p>• {note2}</p>'
    html += f'<p>• {note3}</p>'
    html += '</div>'
    html += '</div>'

    # Footer
    html += '<div class="template-footer">'
    html += f'<div class="regards">{"وتفضلوا بقبول وافر الاحترام،،،" if is_ar else "Yours faithfully,"}</div>'
    html += f'<div class="company">{c.get("company_name_ar" if is_ar else "company_name_en", "")}</div>'
    html += '</div>'

    html += '</div>'  # End Page 3

    # Update content
    template_content = anvil.js.window.document.getElementById('templateContent')
    if template_content:
      template_content.innerHTML = html

  def print_quotation(self):
    """Print the quotation"""
    if not self.current_data:
      self._show_msg('Please select a quotation first')
      return
    anvil.js.window.print()

  def export_pdf(self):
    """Export quotation as PDF - direct download"""
    if not self.current_data:
      self._show_msg('Please select a quotation first')
      return

    def sanitize_filename(value):
      value = str(value or '').strip()
      value = value.replace('/', '-').replace('\\', '-').replace(':', '-')
      value = value.replace('*', '-').replace('?', '').replace('"', '')
      value = value.replace('<', '').replace('>', '').replace('|', '-')
      return value or 'unknown'

    q_num = sanitize_filename(self.current_data.get('quotation_number', 'quotation'))
    client_name = sanitize_filename(self.current_data.get('client_name', 'Client'))
    model_name = sanitize_filename(self.current_data.get('model', 'Model'))
    filename = f"{q_num} - {client_name} - {model_name}.pdf"
    filename_js = filename.replace("\\", "\\\\").replace("'", "\\'")

    js_code = f"""
        (async function() {{
            const element = document.getElementById('templateContent');
            if (!element || !element.innerHTML.trim()) {{
                if (window.showNotification) window.showNotification('error', '', 'No content to export. Please select a quotation first.');
                return;
            }}

            // Load libraries
            function loadScript(url) {{
                return new Promise((resolve, reject) => {{
                    if (document.querySelector('script[src="' + url + '"]')) {{
                        resolve();
                        return;
                    }}
                    const script = document.createElement('script');
                    script.src = url;
                    script.onload = resolve;
                    script.onerror = reject;
                    document.head.appendChild(script);
                }});
            }}

            try {{
                await loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js');
                await loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js');

                const {{ jsPDF }} = window.jspdf;
                const pdf = new jsPDF('p', 'mm', 'a4');
                const pages = element.querySelectorAll('.template-page');

                if (pages.length === 0) {{
                    if (window.showNotification) window.showNotification('error', '', 'No pages found to export');
                    return;
                }}

                for (let i = 0; i < pages.length; i++) {{
                    const page = pages[i];

                    // Capture page as canvas
                    const canvas = await html2canvas(page, {{
                        scale: 2,
                        useCORS: true,
                        allowTaint: true,
                        backgroundColor: '#ffffff',
                        logging: false,
                        width: page.scrollWidth,
                        height: page.scrollHeight
                    }});

                    const imgData = canvas.toDataURL('image/jpeg', 0.95);
                    const imgWidth = 210; // A4 width in mm
                    const imgHeight = (canvas.height * imgWidth) / canvas.width;

                    if (i > 0) {{
                        pdf.addPage();
                    }}

                    pdf.addImage(imgData, 'JPEG', 0, 0, imgWidth, imgHeight);
                }}

                pdf.save('{filename_js}');

            }} catch (error) {{
                console.error('PDF Export Error:', error);
                if (window.showNotification) window.showNotification('error', '', 'Error exporting PDF: ' + error.message);
            }}
        }})();
    """
    anvil.js.window.eval(js_code)

  def export_excel(self):
    """Export quotation data as Excel file"""
    if not self.current_data:
      self._show_msg('Please select a quotation first')
      return

    data = self.current_data
    q_num = data.get('quotation_number', 'quotation')
    client_name = data.get('client_name', '').replace(' ', '_')

    try:
      auth = anvil.js.window.sessionStorage.getItem('auth_token') or anvil.js.window.sessionStorage.getItem('user_email') or None
      result = anvil.server.call('export_quotation_excel', q_num, auth)
      if result.get('success'):
        media = result.get('file')
        if media:
          anvil.media.download(media)
      else:
        self._show_msg(result.get('message', 'Unknown error'))
    except Exception as e:
      self._show_msg(str(e))

  # Server call wrappers
  def load_quotation_for_print(self, quotation_number):
    """Load quotation data for print preview"""
    try:
      user_email = anvil.js.window.sessionStorage.getItem('user_email') or ''
      auth_token = anvil.js.window.sessionStorage.getItem('auth_token') or None
      result = anvil.server.call('get_quotation_pdf_data', int(quotation_number), user_email, auth_token)
      return result
    except Exception as e:
      return {'success': False, 'message': str(e)}

  def search_quotations_for_print(self, query=''):
    """Search quotations"""
    try:
      auth = anvil.js.window.sessionStorage.getItem('auth_token') or anvil.js.window.sessionStorage.getItem('user_email') or None
      result = anvil.server.call('get_quotations_list', query, False, auth)
      return result
    except Exception as e:
      return {'success': False, 'message': str(e)}

  def get_quotation_pdf_data(self, quotation_number):
    """Get full quotation data for PDF"""
    try:
      user_email = anvil.js.window.sessionStorage.getItem('user_email') or ''
      auth_token = anvil.js.window.sessionStorage.getItem('auth_token') or None
      result = anvil.server.call('get_quotation_pdf_data', int(quotation_number), user_email, auth_token)
      return result
    except Exception as e:
      return {'success': False, 'message': str(e)}

  def get_all_settings(self):
    """Get all template settings (يُمرّر التوكن لتحميل الإعدادات)"""
    try:
      auth = anvil.js.window.sessionStorage.getItem('auth_token') or anvil.js.window.sessionStorage.getItem('user_email') or None
      result = anvil.server.call('get_all_settings', auth)
      return result
    except Exception as e:
      return {'success': False, 'message': str(e)}

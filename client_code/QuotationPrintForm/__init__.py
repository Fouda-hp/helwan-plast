from ._anvil_designer import QuotationPrintFormTemplate
from anvil import *
import anvil.server
import anvil.js

class QuotationPrintForm(QuotationPrintFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # State
        self.current_lang = 'ar'
        self.current_data = None
        self.all_quotations = []

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
            result = anvil.server.call('get_quotations_list', '', include_deleted=False)
            if result and result.get('success'):
                self.all_quotations = result.get('data', [])
                self.populate_dropdown(self.all_quotations)
        except Exception as e:
            print(f'Error loading quotations: {e}')

    def populate_dropdown(self, quotations):
        """Populate the quotation dropdown"""
        select = anvil.js.window.document.getElementById('quotationSelect')
        if not select:
            return

        # Clear and add default option
        select.innerHTML = f'<option value="">-- Select Quotation ({len(quotations)}) --</option>'

        # Add quotations
        for q in quotations:
            opt = anvil.js.window.document.createElement('option')
            opt.value = str(q.get('Quotation#', ''))
            opt.textContent = f"#{q.get('Quotation#', '')} - {q.get('Client Name', 'N/A')} - {q.get('Model', '')}"
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
            model = str(q.get('Model', '')).lower()
            if query in num or query in name or query in model:
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
            template_content.innerHTML = '<div class="loading"><div class="spinner"></div><p>Loading...</p></div>'

        try:
            user_email = anvil.js.window.localStorage.getItem('user_email') or ''
            result = anvil.server.call('get_quotation_pdf_data', quotation_number, user_email)

            if result and result.get('success'):
                self.current_data = result.get('data')
                self.render_template()
            else:
                template_content.innerHTML = f'<div class="empty-state"><h3>Error</h3><p>{result.get("message", "Failed to load")}</p></div>'
        except Exception as e:
            template_content.innerHTML = f'<div class="empty-state"><h3>Error</h3><p>{str(e)}</p></div>'

    def switch_language(self, lang):
        """Switch display language"""
        self.current_lang = lang
        self.update_language_buttons()

        if self.current_data:
            self.render_template()

    def render_template(self):
        """Render the quotation template - 3 pages without page breaks"""
        if not self.current_data:
            return

        data = self.current_data
        c = data.get('company', {})
        is_ar = (self.current_lang == 'ar')

        # Get machine model and material for conditional logic
        model = str(data.get('model', '')).upper()
        material = str(data.get('material', '')).upper()
        plc_value = str(data.get('plc', '')).upper()

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
        html += f'<div class="location-date">{c.get("quotation_location_ar" if is_ar else "quotation_location_en", "")} / {data.get("quotation_date_ar" if is_ar else "quotation_date_en", "")}</div>'
        html += f'<div class="address">{c.get("company_address_ar" if is_ar else "company_address_en", "")}</div>'
        html += f'<div class="contact">{data.get("user_phone", "")}</div>'
        html += f'<div class="contact">{c.get("company_email", "")}</div>'
        html += '</div>'
        html += '<div class="header-left">'
        html += '<img src="_/theme/helwan_logo.png" class="logo" alt="Logo">'
        html += f'<div class="company-name">{c.get("company_name_ar" if is_ar else "company_name_en", "")}</div>'
        html += f'<div class="website">{c.get("company_website", "")}</div>'
        html += '</div>'
        html += '</div>'

        # Quotation Info
        html += '<div class="quotation-info">'
        html += f'<div class="quotation-number">{"عرض سعر رقم" if is_ar else "Quotation No.:"} <span>{data.get("quotation_number", "")}</span></div>'
        html += f'<div class="client-info">{"السادة - شركة /" if is_ar else "To: / Company:"} <span>{data.get("client_name", "")}</span></div>'
        html += f'<div class="greeting">{"تحية طيبة وبعد،" if is_ar else "Dear Sir/Madam,"}</div>'
        intro = 'نحن نتشرف بتقديم عرض السعر التالي لماكينة الطباعة طبقاً للمواصفات الموضحة أدناه:' if is_ar else 'We are pleased to submit our quotation for the following printing machine in accordance with the specifications detailed below:'
        html += f'<div class="intro-text">{intro}</div>'
        html += '</div>'

        # Machine Details
        html += f'<div class="section-title">{"تفاصيل الماكينة :" if is_ar else "Machine Details"}</div>'
        html += '<table class="details-table">'
        html += f'<tr><th>{"نوع الماكينة :" if is_ar else "Machine Type:"}</th><td>{machine_type_display}</td></tr>'
        html += f'<tr><th>{"الموديل :" if is_ar else "Model:"}</th><td>{data.get("model", "")}</td></tr>'
        html += f'<tr><th>{"بلد المنشأ :" if is_ar else "Country of Origin:"}</th><td>{c.get("country_origin_ar" if is_ar else "country_origin_en", "")}</td></tr>'
        html += f'<tr><th>{"عدد الألوان :" if is_ar else "Number of Colors:"}</th><td>{data.get("colors_count", "")}</td></tr>'
        html += f'<tr><th>{"الوندر :" if is_ar else "Winder:"}</th><td>{data.get("winder", "")}</td></tr>'
        html += f'<tr><th>{"نوع الوندر :" if is_ar else "Winder Type:"}</th><td>{winder_type_display}</td></tr>'
        html += f'<tr><th>{"عرض الماكينة :" if is_ar else "Machine Width:"}</th><td>{data.get("machine_width", "")} {"سم" if is_ar else "CM"}</td></tr>'
        html += '</table>'

        # ==================== 17 SPECIFICATIONS ====================
        html += f'<div class="section-title">{"المواصفات الفنية:" if is_ar else "Technical Specifications:"}</div>'
        html += '<ol class="specs-list" style="font-size: 13px; line-height: 2; padding-right: 20px; padding-left: 20px;">'

        # Helper function to determine Belt/Gear drive for item 13
        def get_drive_type():
            is_metal_anilox = 'METAL' in model
            is_nonwoven = 'NONWOVEN' in material
            # Belt drive if: Ceramic anilox OR NONWOVEN material
            # Gear drive if: Metal anilox AND NOT NONWOVEN
            if is_metal_anilox and not is_nonwoven:
                return ('نقل القدرة من الموتور الرئيسي لأجزاء الماكينة عن طريق الجيربوكس' if is_ar else 'Gear drive',
                        'نقل القدرة من الموتور الرئيسي إلى مكونات الماكينة عبر نظام الجير لضمان عمر أطول، تقليل الأعطال، وتمكين التشغيل بسرعة عالية وهدوء مع تصميم غير معقد' if is_ar else 'Power transmission from the main motor to machine components via Gear drive to ensure longer service life, reduce breakdowns, and enable high-speed, quiet operation with a non-complex gear design')
            else:
                return ('نقل القدرة من الموتور الرئيسي لأجزاء الماكينة عن طريق السيور' if is_ar else 'Belt drive',
                        'نقل القدرة من الموتور الرئيسي إلى مكونات الماكينة عبر السيور لضمان عمر أطول، تقليل الأعطال، وتمكين التشغيل بسرعة عالية وهدوء مع تصميم غير معقد' if is_ar else 'Power transmission from the main motor to machine components via Belt drive to ensure longer service life, reduce breakdowns, and enable high-speed, quiet operation with a non-complex gear design')

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
            "الرولات والأسطوانات معالجة بالليزر للتشغيل الشاق وإطالة عمر الخدمة",
            "مستشعرات إيقاف أوتوماتيكي للماكينة في حالة انقطاع الفيلم أو نفاد الخامة",
            "ضغط أسطوانة الطباعة يتم عبر نظام الزيت الهيدروليكي لتجنب مشاكل الضغط الهوائي وتقليل استهلاك الكهرباء الناتج عن تشغيل ضاغط الهواء المتكرر",
            get_color_registration(),
            "رافعات سقفية مدمجة لتسهيل تحميل وتفريغ الرولات وأسطوانات الطباعة، مما يوفر الوقت والجهد والعمالة",
            "مناسبة لأحبار المذيبات والأحبار المائية",
            "إنفرترات دلتا (تايوان)",
            "إنذار أمان قبل بدء تشغيل الماكينة لمنع الإصابات",
            "وحدات تجفيف بالهواء الساخن مع مسار خامة ممتد لضمان جفاف الحبر الكامل، بالإضافة إلى وحدات تجفيف بين الألوان",
            get_drive_type()[1],
            "مضخات تشحيم مدمجة لضمان توزيع متوازن للزيت على جميع المكونات، تشغيل سلس، وحماية جميع الأجزاء المتحركة",
            "موتورات إعادة لف منفصلة بتحكم مستقل للسماح بالتشغيل مع مرونات وسماكات مختلفة للخامات",
            "أسطوانات فك/لف بشافت هوائي، بالإضافة إلى شافت ميكانيكي إضافي لتمكين التشغيل مع أي حجم كور",
            "إمكانية الطباعة على الوجهين"
        ]

        specs = specs_ar if is_ar else specs_en
        for i, spec in enumerate(specs, 1):
            html += f'<li>{spec}</li>'

        html += '</ol>'
        html += '</div>'  # End Page 1

        # ==================== PAGE 2 - Technical Table ====================
        html += f'<div class="template-page {"" if is_ar else "ltr"}">'

        # Header (repeated)
        html += '<div class="header">'
        html += '<div class="header-right">'
        html += f'<div class="location-date">{c.get("quotation_location_ar" if is_ar else "quotation_location_en", "")} / {data.get("quotation_date_ar" if is_ar else "quotation_date_en", "")}</div>'
        html += f'<div class="address">{c.get("company_address_ar" if is_ar else "company_address_en", "")}</div>'
        html += f'<div class="contact">{data.get("user_phone", "")}</div>'
        html += '</div>'
        html += '<div class="header-left">'
        html += '<img src="_/theme/helwan_logo.png" class="logo" alt="Logo">'
        html += f'<div class="company-name">{c.get("company_name_ar" if is_ar else "company_name_en", "")}</div>'
        html += '</div>'
        html += '</div>'

        html += f'<div class="section-title">{"جدول المواصفات الفنية:" if is_ar else "Technical Specifications Table:"}</div>'

        # ==================== CALCULATE TABLE VALUES ====================
        # Get values from quotation data
        winder_type = str(data.get('winder', '')).upper()
        is_double_winder = 'DOUBLE' in winder_type
        colors_count = int(data.get('colors_count', 0) or 0)
        machine_width = float(data.get('machine_width', 0) or 0)

        # Determine if Belt or Gear drive
        is_metal_anilox = 'METAL' in model
        is_nonwoven = 'NONWOVEN' in material
        is_belt_drive = not (is_metal_anilox and not is_nonwoven)

        # Get settings values with defaults
        belt_max_machine_speed = int(c.get('belt_max_machine_speed', 120))
        belt_max_print_speed = int(c.get('belt_max_print_speed', 120))
        belt_print_length = c.get('belt_print_length', '300mm - 1300mm')
        gear_max_machine_speed = int(c.get('gear_max_machine_speed', 100))
        gear_max_print_speed = int(c.get('gear_max_print_speed', 80))
        gear_print_length = c.get('gear_print_length', '240mm - 1000mm')
        single_winder_roll_dia = int(c.get('single_winder_roll_dia', 1200))
        double_winder_roll_dia = int(c.get('double_winder_roll_dia', 800))
        dryer_capacity = c.get('dryer_capacity', '2.2kw air blower × 2 units')
        main_motor_power = c.get('main_motor_power', '5 HP')

        # Calculate values based on rules
        # Number of Colors format
        if colors_count == 8:
            colors_display = "8+0, 7+1, 6+2, 5+3, 4+4 reverse printing" if not is_ar else "8+0، 7+1، 6+2، 5+3، 4+4 طباعة عكسية"
        elif colors_count == 6:
            colors_display = "6+0, 5+1, 4+2, 3+3 reverse printing" if not is_ar else "6+0، 5+1، 4+2، 3+3 طباعة عكسية"
        elif colors_count == 4:
            colors_display = "4+0, 3+1, 2+2 reverse printing" if not is_ar else "4+0، 3+1، 2+2 طباعة عكسية"
        else:
            colors_display = str(colors_count)

        # Values based on winder type (double=4/2, single=2/1)
        tension_units = 4 if is_double_winder else 2
        brake_system = 4 if is_double_winder else 2
        brake_power = 2 if is_double_winder else 1
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
        drive_display = ("Belt Drive" if not is_ar else "سيور") if is_belt_drive else ("Gear Drive" if not is_ar else "جيربوكس")

        # Yes/No fields
        def yes_no(field_name):
            val = str(data.get(field_name, '')).upper()
            if val in ['YES', 'TRUE', '1', 'نعم']:
                return 'Yes' if not is_ar else 'نعم'
            return 'No' if not is_ar else 'لا'

        # Build specs table with calculated values
        table_specs = [
            {'en': 'Model', 'ar': 'الموديل', 'value': data.get('model', '-')},
            {'en': 'Number of Colors', 'ar': 'عدد الألوان', 'value': colors_display},
            {'en': 'Printing Sides', 'ar': 'أوجه الطباعة', 'value': '2'},
            {'en': 'Tension Control Units', 'ar': 'وحدات التحكم في الشد', 'value': str(tension_units)},
            {'en': 'Brake System', 'ar': 'نظام الفرامل', 'value': str(brake_system)},
            {'en': 'Brake Power', 'ar': 'قوة الفرامل', 'value': str(brake_power)},
            {'en': 'Web Guiding System (Oscillating Type)', 'ar': 'نظام توجيه الخامة (النوع المتأرجح)', 'value': str(web_guiding)},
            {'en': 'Maximum Film Width', 'ar': 'أقصى عرض للفيلم', 'value': f"{max_film_width} mm"},
            {'en': 'Maximum Printing Width', 'ar': 'أقصى عرض للطباعة', 'value': f"{max_print_width} mm"},
            {'en': 'Minimum and Maximum Printing Length', 'ar': 'الحد الأدنى والأقصى لطول الطباعة', 'value': print_length},
            {'en': 'Maximum Roll Diameter', 'ar': 'أقصى قطر للرول', 'value': f"{max_roll_diameter} mm"},
            {'en': 'Anilox Type', 'ar': 'نوع الأنيلوكس', 'value': anilox_display},
            {'en': 'Maximum Machine Speed', 'ar': 'أقصى سرعة للماكينة', 'value': f"{max_machine_speed} m/min"},
            {'en': 'Maximum Printing Speed', 'ar': 'أقصى سرعة للطباعة', 'value': f"{max_print_speed} m/min"},
            {'en': 'Dryer Capacity', 'ar': 'قدرة المجفف', 'value': dryer_capacity},
            {'en': 'Power Transmission Method', 'ar': 'طريقة نقل القدرة', 'value': drive_display},
            {'en': 'Main Motor Power', 'ar': 'قدرة الموتور الرئيسي', 'value': main_motor_power},
            {'en': 'Video Inspection', 'ar': 'الفحص بالفيديو', 'value': yes_no('video_inspection')},
            {'en': 'PLC', 'ar': 'PLC', 'value': yes_no('plc')},
            {'en': 'Slitter', 'ar': 'السليتر', 'value': yes_no('slitter')},
        ]

        html += '<table class="tech-table">'
        for i, spec in enumerate(table_specs, 1):
            label = spec['ar'] if is_ar else spec['en']
            html += f'<tr><td class="row-num">{i}</td><th>{label}</th><td class="value">{spec["value"]}</td></tr>'
        html += '</table>'

        # Cylinders - 2 columns, 12 rows fixed (border only on filled rows)
        cylinders = data.get('cylinders', [])
        html += f'<div class="section-title">{"سلندرات الطباعة :" if is_ar else "Printing Cylinders:"}</div>'
        html += '<table class="cylinders-table" style="width: 50%;">'
        html += f'<tr><th>{"مقاس" if is_ar else "Size"}</th><th>{"عدد" if is_ar else "Count"}</th></tr>'

        # Always show 12 rows - border only on filled rows
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
        html += f'<div class="template-page {"" if is_ar else "ltr"}">'

        # Header (repeated)
        html += '<div class="header">'
        html += '<div class="header-right">'
        html += f'<div class="location-date">{c.get("quotation_location_ar" if is_ar else "quotation_location_en", "")} / {data.get("quotation_date_ar" if is_ar else "quotation_date_en", "")}</div>'
        html += f'<div class="address">{c.get("company_address_ar" if is_ar else "company_address_en", "")}</div>'
        html += f'<div class="contact">{data.get("user_phone", "")}</div>'
        html += '</div>'
        html += '<div class="header-left">'
        html += '<img src="_/theme/helwan_logo.png" class="logo" alt="Logo">'
        html += f'<div class="company-name">{c.get("company_name_ar" if is_ar else "company_name_en", "")}</div>'
        html += '</div>'
        html += '</div>'

        html += f'<div class="section-title">{"العرض المالي:" if is_ar else "Financial Offer:"}</div>'

        html += '<div class="financial-box">'
        html += f'<div class="total-price">{data.get("total_price", "")} {"ج.م" if is_ar else "EGP"}</div>'
        price_note = 'السعر شامل التوريد والتركيب والضمان' if is_ar else 'The price includes: supply, installation, and warranty'
        html += f'<div class="price-notes">{price_note}</div>'

        html += f'<div class="section-title">{"طريقة الدفع:" if is_ar else "Payment Terms:"}</div>'
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
        html += f'<p>{"وقت التسليم المتوقع :" if is_ar else "Expected delivery time:"} <span class="highlight">{data.get("expected_delivery_formatted", "-")}</span></p>'
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
            alert('Please select a quotation first')
            return
        anvil.js.window.print()

    def export_pdf(self):
        """Export quotation as PDF using html2pdf.js"""
        if not self.current_data:
            alert('Please select a quotation first')
            return

        # Get quotation number for filename
        q_num = self.current_data.get('quotation_number', 'quotation')
        client_name = self.current_data.get('client_name', '').replace(' ', '_')
        filename = f"Quotation_{q_num}_{client_name}.pdf"

        # Use html2pdf.js to generate PDF
        js_code = f"""
        (function() {{
            var element = document.getElementById('templateContent');
            if (!element) {{
                alert('No content to export');
                return;
            }}

            // Check if html2pdf is loaded
            if (typeof html2pdf === 'undefined') {{
                // Load html2pdf.js dynamically
                var script = document.createElement('script');
                script.src = 'https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js';
                script.onload = function() {{
                    generatePDF();
                }};
                document.head.appendChild(script);
            }} else {{
                generatePDF();
            }}

            function generatePDF() {{
                var opt = {{
                    margin: 10,
                    filename: '{filename}',
                    image: {{ type: 'jpeg', quality: 0.98 }},
                    html2canvas: {{ scale: 2, useCORS: true }},
                    jsPDF: {{ unit: 'mm', format: 'a4', orientation: 'portrait' }},
                    pagebreak: {{ mode: ['css', 'legacy'] }}
                }};

                html2pdf().set(opt).from(element).save();
            }}
        }})();
        """
        anvil.js.window.eval(js_code)

    def export_excel(self):
        """Export quotation data as Excel file"""
        if not self.current_data:
            alert('Please select a quotation first')
            return

        data = self.current_data
        q_num = data.get('quotation_number', 'quotation')
        client_name = data.get('client_name', '').replace(' ', '_')

        # Call server to generate Excel
        try:
            result = anvil.server.call('export_quotation_excel', q_num)
            if result.get('success'):
                # Download the file
                media = result.get('file')
                if media:
                    anvil.media.download(media)
            else:
                alert(f"Error: {result.get('message', 'Unknown error')}")
        except Exception as e:
            alert(f"Error exporting Excel: {str(e)}")

    # Server call wrappers
    def load_quotation_for_print(self, quotation_number):
        """Load quotation data for print preview"""
        try:
            user_email = anvil.js.window.localStorage.getItem('user_email') or ''
            result = anvil.server.call('get_quotation_pdf_data', int(quotation_number), user_email)
            return result
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def search_quotations_for_print(self, query=''):
        """Search quotations"""
        try:
            result = anvil.server.call('get_quotations_list', query, include_deleted=False)
            return result
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def get_quotation_pdf_data(self, quotation_number):
        """Get full quotation data for PDF"""
        try:
            user_email = anvil.js.window.localStorage.getItem('user_email') or ''
            result = anvil.server.call('get_quotation_pdf_data', int(quotation_number), user_email)
            return result
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def get_all_settings(self):
        """Get all template settings"""
        try:
            result = anvil.server.call('get_all_settings')
            return result
        except Exception as e:
            return {'success': False, 'message': str(e)}

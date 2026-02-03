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

        # Initialize
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
            user_email = anvil.js.window.sessionStorage.getItem('user_email') or ''
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
        """Render the quotation template"""
        if not self.current_data:
            return

        data = self.current_data
        c = data.get('company', {})
        is_ar = (self.current_lang == 'ar')

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
        html += f'<tr><th>{"نوع الماكينة :" if is_ar else "Machine Type:"}</th><td>{data.get("machine_type", "Flexo Stack")}</td></tr>'
        html += f'<tr><th>{"الموديل :" if is_ar else "Model:"}</th><td>{data.get("model", "")}</td></tr>'
        html += f'<tr><th>{"بلد المنشأ :" if is_ar else "Country of Origin:"}</th><td>{c.get("country_origin_ar" if is_ar else "country_origin_en", "")}</td></tr>'
        html += f'<tr><th>{"عدد الألوان :" if is_ar else "Number of Colors:"}</th><td>{data.get("colors_count", "")}</td></tr>'
        html += f'<tr><th>{"الوندر :" if is_ar else "Winder:"}</th><td>{data.get("winder", "")}</td></tr>'
        html += f'<tr><th>{"عرض الماكينة :" if is_ar else "Machine Width:"}</th><td>{data.get("machine_width", "")} {"سم" if is_ar else "CM"}</td></tr>'
        html += '</table>'

        html += '</div>'  # End Page 1

        # Page 2 - Technical Specs
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

        html += f'<div class="section-title">{"المواصفات الفنية:" if is_ar else "Technical Specifications:"}</div>'

        html += '<table class="tech-table">'
        html += f'<tr><td class="row-num">1</td><th>{"الموديل" if is_ar else "Model"}</th><td class="value">{data.get("model", "")}</td></tr>'
        html += f'<tr><td class="row-num">2</td><th>{"عدد الألوان" if is_ar else "Number of Colors"}</th><td class="value">{data.get("colors_count", "")}</td></tr>'
        html += f'<tr><td class="row-num">3</td><th>{"نوع الانيلوكس" if is_ar else "Anilox Type"}</th><td class="value">{c.get("anilox_type_ar" if is_ar else "anilox_type_en", "")}</td></tr>'
        html += f'<tr><td class="row-num">4</td><th>{"مراقبة الطباعة بالفيديو" if is_ar else "Video Inspection"}</th><td class="value">{data.get("video_inspection", "NO")}</td></tr>'
        html += f'<tr><td class="row-num">5</td><th>PLC</th><td class="value">{data.get("plc", "NO")}</td></tr>'
        html += f'<tr><td class="row-num">6</td><th>{"سليتر" if is_ar else "Slitter"}</th><td class="value">{data.get("slitter", "NO")}</td></tr>'
        html += '</table>'

        # Cylinders
        cylinders = data.get('cylinders', [])
        if cylinders:
            html += f'<div class="section-title">{"سلندرات الطباعة :" if is_ar else "Printing Cylinders:"}</div>'
            html += '<table class="cylinders-table">'
            html += f'<tr><th>{"مقاس" if is_ar else "Size"}</th><th>{"عدد" if is_ar else "Count"}</th></tr>'
            for cyl in cylinders:
                html += f'<tr><td>{cyl.get("size", "")}</td><td>{cyl.get("count", "")}</td></tr>'
            html += '</table>'

        html += '</div>'  # End Page 2

        # Page 3 - Financial
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
        """Export quotation as PDF"""
        if not self.current_data:
            alert('Please select a quotation first')
            return
        alert('Use Print (Ctrl+P) and select "Save as PDF" as the printer')
        anvil.js.window.print()

    # Server call wrappers
    def load_quotation_for_print(self, quotation_number):
        """Load quotation data for print preview"""
        try:
            user_email = anvil.js.window.sessionStorage.getItem('user_email') or ''
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
            user_email = anvil.js.window.sessionStorage.getItem('user_email') or ''
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

from ._anvil_designer import ContractPrintFormTemplate
from anvil import *
import anvil.server
import anvil.js
import json

class ContractPrintForm(ContractPrintFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # State
        self.current_lang = 'ar'
        self.current_data = None
        self.all_quotations = []
        self.payment_data = []  # Store payment schedule
        self.payment_method = 'percentage'  # percentage or amount

        # Expose functions to JavaScript
        anvil.js.window.loadQuotationForPrint = self.load_quotation_for_print
        anvil.js.window.searchQuotationsForPrint = self.search_quotations_for_print
        anvil.js.window.getAllSettings = self.get_all_settings

        # UI Functions
        anvil.js.window.goBackToLauncher = self.go_back
        anvil.js.window.loadSelectedQuotation = self.load_selected_quotation
        anvil.js.window.filterQuotations = self.filter_quotations
        anvil.js.window.switchLanguage = self.switch_language
        anvil.js.window.printContract = self.print_contract
        anvil.js.window.exportPDF = self.export_pdf
        anvil.js.window.exportExcel = self.export_excel

        # Payment Modal Functions
        anvil.js.window.openPaymentModal = self.open_payment_modal
        anvil.js.window.closePaymentModal = self.close_payment_modal
        anvil.js.window.updatePaymentRows = self.update_payment_rows
        anvil.js.window.updatePaymentMethod = self.update_payment_method
        anvil.js.window.savePayments = self.save_payments
        anvil.js.window.calculateTotalPercentage = self.calculate_total_percentage

    def form_show(self, **event_args):
        self.init_page()

    def init_page(self):
        saved_lang = anvil.js.window.localStorage.getItem('hp_language')
        if saved_lang in ['ar', 'en']:
            self.current_lang = saved_lang
            self.update_language_buttons()
        self.load_quotations_list()

    def update_language_buttons(self):
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
        anvil.js.window.location.hash = '#launcher'

    def load_quotations_list(self):
        try:
            result = anvil.server.call('get_quotations_list', '', include_deleted=False)
            if result and result.get('success'):
                self.all_quotations = result.get('data', [])
                self.populate_dropdown(self.all_quotations)
        except Exception as e:
            print(f'Error loading quotations: {e}')

    def populate_dropdown(self, quotations):
        select = anvil.js.window.document.getElementById('quotationSelect')
        if not select:
            return
        select.innerHTML = f'<option value="">-- Select Quotation ({len(quotations)}) --</option>'
        for q in quotations:
            q_num = q.get('Quotation#', '')
            client = q.get('Client Name', '')
            model = q.get('Model', '')
            option_text = f"#{q_num} - {client} - {model}"
            select.innerHTML += f'<option value="{q_num}">{option_text}</option>'

    def filter_quotations(self):
        search_input = anvil.js.window.document.getElementById('searchInput')
        if not search_input:
            return
        query = str(search_input.value).lower().strip()
        if not query:
            self.populate_dropdown(self.all_quotations)
            return
        filtered = []
        for q in self.all_quotations:
            q_num = str(q.get('Quotation#', ''))
            client = str(q.get('Client Name', '')).lower()
            model = str(q.get('Model', '')).lower()
            if query in q_num or query in client or query in model:
                filtered.append(q)
        self.populate_dropdown(filtered)

    def load_selected_quotation(self):
        select = anvil.js.window.document.getElementById('quotationSelect')
        if not select or not select.value:
            return
        q_num = int(select.value)
        result = self.load_quotation_for_print(q_num)
        if result and result.get('success'):
            self.current_data = result.get('data', {})
            self.render_contract()
            # Update total in payment modal
            total = self.current_data.get('total_price', 0)
            total_el = anvil.js.window.document.getElementById('totalContractAmount')
            if total_el:
                total_el.textContent = f"{total:,.2f}"

    def switch_language(self, lang):
        self.current_lang = lang
        anvil.js.window.localStorage.setItem('hp_language', lang)
        self.update_language_buttons()
        if self.current_data:
            self.render_contract()

    # ==================== Payment Modal ====================
    def open_payment_modal(self):
        if not self.current_data:
            alert('Please select a quotation first')
            return
        overlay = anvil.js.window.document.getElementById('paymentModalOverlay')
        if overlay:
            overlay.classList.add('active')
            self.update_payment_rows()

    def close_payment_modal(self):
        overlay = anvil.js.window.document.getElementById('paymentModalOverlay')
        if overlay:
            overlay.classList.remove('active')

    def update_payment_method(self):
        radios = anvil.js.window.document.querySelectorAll('input[name="paymentMethod"]')
        for r in radios:
            if r.checked:
                self.payment_method = r.value
                break
        # Update header
        header = anvil.js.window.document.getElementById('valueHeader')
        if header:
            header.textContent = 'Percentage %' if self.payment_method == 'percentage' else 'Amount'
        self.update_payment_rows()

    def update_payment_rows(self):
        num_input = anvil.js.window.document.getElementById('numPayments')
        tbody = anvil.js.window.document.getElementById('paymentsTableBody')
        if not num_input or not tbody:
            return
        
        num = int(num_input.value or 3)
        num = max(1, min(12, num))
        
        is_ar = self.current_lang == 'ar'
        rows_html = ''
        
        labels = {
            1: ('الدفعة المقدمة', 'Down Payment'),
            2: ('القسط الثاني', 'Installment 2'),
            3: ('القسط الثالث', 'Installment 3'),
            4: ('القسط الرابع', 'Installment 4'),
            5: ('القسط الخامس', 'Installment 5'),
            6: ('القسط السادس', 'Installment 6'),
            7: ('القسط السابع', 'Installment 7'),
            8: ('القسط الثامن', 'Installment 8'),
            9: ('القسط التاسع', 'Installment 9'),
            10: ('القسط العاشر', 'Installment 10'),
            11: ('القسط الحادي عشر', 'Installment 11'),
            12: ('القسط الثاني عشر', 'Installment 12'),
        }
        
        placeholder = '%' if self.payment_method == 'percentage' else 'Amount'
        
        for i in range(1, num + 1):
            label = labels.get(i, (f'القسط {i}', f'Installment {i}'))
            label_text = label[0] if is_ar else label[1]
            
            # Get saved value if exists
            saved_val = ''
            saved_date = ''
            if len(self.payment_data) >= i:
                saved_val = self.payment_data[i-1].get('value', '')
                saved_date = self.payment_data[i-1].get('date', '')
            
            rows_html += f'''
            <tr>
                <td><strong>{label_text}</strong></td>
                <td><input type="number" class="payment-value" data-index="{i}" 
                    value="{saved_val}" placeholder="{placeholder}" 
                    oninput="window.calculateTotalPercentage()"></td>
                <td><input type="date" class="payment-date" data-index="{i}" value="{saved_date}"></td>
            </tr>
            '''
        
        tbody.innerHTML = rows_html

    def calculate_total_percentage(self):
        if self.payment_method != 'percentage':
            return
        inputs = anvil.js.window.document.querySelectorAll('.payment-value')
        total = 0
        for inp in inputs:
            val = float(inp.value or 0)
            total += val
        total_el = anvil.js.window.document.getElementById('totalPercentage')
        if total_el:
            total_el.textContent = str(int(total))
            if total == 100:
                total_el.style.color = '#4caf50'
            elif total > 100:
                total_el.style.color = '#f44336'
            else:
                total_el.style.color = '#666'

    def save_payments(self):
        value_inputs = anvil.js.window.document.querySelectorAll('.payment-value')
        date_inputs = anvil.js.window.document.querySelectorAll('.payment-date')
        
        self.payment_data = []
        total_price = float(self.current_data.get('total_price', 0) or 0)
        
        labels_ar = ['الدفعة المقدمة', 'القسط الثاني', 'القسط الثالث', 'القسط الرابع', 
                     'القسط الخامس', 'القسط السادس', 'القسط السابع', 'القسط الثامن',
                     'القسط التاسع', 'القسط العاشر', 'القسط الحادي عشر', 'القسط الثاني عشر']
        labels_en = ['Down Payment', 'Installment 2', 'Installment 3', 'Installment 4',
                     'Installment 5', 'Installment 6', 'Installment 7', 'Installment 8',
                     'Installment 9', 'Installment 10', 'Installment 11', 'Installment 12']
        
        for i, (val_inp, date_inp) in enumerate(zip(value_inputs, date_inputs)):
            val = float(val_inp.value or 0)
            date_val = str(date_inp.value or '')
            
            if val > 0:
                if self.payment_method == 'percentage':
                    amount = total_price * val / 100
                    percentage = val
                else:
                    amount = val
                    percentage = (val / total_price * 100) if total_price > 0 else 0
                
                self.payment_data.append({
                    'index': i + 1,
                    'label_ar': labels_ar[i] if i < len(labels_ar) else f'القسط {i+1}',
                    'label_en': labels_en[i] if i < len(labels_en) else f'Installment {i+1}',
                    'value': val,
                    'percentage': percentage,
                    'amount': amount,
                    'date': date_val,
                    'method': self.payment_method
                })
        
        self.close_payment_modal()
        if self.current_data:
            self.render_contract()

    # ==================== Render Contract ====================
    def render_contract(self):
        if not self.current_data:
            return
        
        empty_state = anvil.js.window.document.getElementById('emptyState')
        template_content = anvil.js.window.document.getElementById('templateContent')
        
        if empty_state:
            empty_state.style.display = 'none'
        if template_content:
            template_content.style.display = 'block'
            html = self.generate_contract_html()
            template_content.innerHTML = html

    def generate_contract_html(self):
        data = self.current_data
        is_ar = self.current_lang == 'ar'
        
        # Get settings
        try:
            settings_result = anvil.server.call('get_all_settings')
            c = settings_result.get('settings', {}) if settings_result.get('success') else {}
        except:
            c = {}
        
        html = ''
        dir_class = '' if is_ar else 'ltr'
        
        # ==================== PAGE 1 - Contract Info ====================
        html += f'<div class="template-page {dir_class}">'
        
        # Header
        html += '<div class="header">'
        html += '<div class="header-right">'
        html += f'<div style="font-size:14px;color:#333;">{c.get("quotation_location_ar" if is_ar else "quotation_location_en", "")} / {data.get("quotation_date_ar" if is_ar else "quotation_date_en", "")}</div>'
        html += f'<div style="font-size:13px;color:#666;">{c.get("company_address_ar" if is_ar else "company_address_en", "")}</div>'
        html += '</div>'
        html += '<div class="header-left">'
        html += '<img src="_/theme/helwan_logo.png" class="logo" alt="Logo">'
        html += f'<div class="company-name">{c.get("company_name_ar" if is_ar else "company_name_en", "")}</div>'
        html += '</div>'
        html += '</div>'
        
        # Contract Title
        contract_title = 'عقد توريد ماكينة طباعة فلكسو' if is_ar else 'Flexo Printing Machine Supply Contract'
        html += f'<div style="text-align:center;margin:20px 0;"><h2 style="color:var(--primary-color);">{contract_title}</h2></div>'
        
        # Contract Number
        q_num = data.get('quotation_number', '')
        contract_num_label = 'رقم العقد:' if is_ar else 'Contract No:'
        html += f'<div style="font-size:16px;font-weight:bold;margin-bottom:15px;">{contract_num_label} <span style="color:var(--accent-color);">C-{q_num}</span></div>'
        
        # Client Info Section
        client_title = 'بيانات العميل (الطرف الثاني):' if is_ar else 'Client Information (Second Party):'
        html += f'<div class="section-title">{client_title}</div>'
        html += '<table class="details-table">'
        
        client_fields = [
            ('الاسم' if is_ar else 'Name', data.get('client_name', '')),
            ('الشركة' if is_ar else 'Company', data.get('company', '')),
            ('الهاتف' if is_ar else 'Phone', data.get('phone', '')),
            ('الدولة' if is_ar else 'Country', data.get('country', '')),
            ('العنوان' if is_ar else 'Address', data.get('address', '')),
        ]
        
        for label, value in client_fields:
            if value:
                html += f'<tr><th>{label}</th><td>{value}</td></tr>'
        html += '</table>'
        
        # Machine Details
        machine_title = 'تفاصيل الماكينة:' if is_ar else 'Machine Details:'
        html += f'<div class="section-title">{machine_title}</div>'
        html += '<table class="details-table">'
        
        machine_fields = [
            ('الموديل' if is_ar else 'Model', data.get('model', '')),
            ('عدد الألوان' if is_ar else 'Number of Colors', data.get('colors_count', '')),
            ('عرض الماكينة' if is_ar else 'Machine Width', f"{data.get('machine_width', '')} cm"),
            ('نوع الخامة' if is_ar else 'Material', data.get('material', '')),
            ('نوع اللفاف' if is_ar else 'Winder Type', data.get('winder_type', '')),
        ]
        
        for label, value in machine_fields:
            if value and value != ' cm':
                html += f'<tr><th>{label}</th><td>{value}</td></tr>'
        html += '</table>'
        
        html += '</div>'  # End Page 1
        
        # ==================== PAGE 2 - Technical Specs ====================
        html += f'<div class="template-page page-break-before {dir_class}">'
        
        # Header repeated
        html += '<div class="header">'
        html += '<div class="header-right">'
        html += f'<div style="font-size:14px;color:#333;">{c.get("quotation_location_ar" if is_ar else "quotation_location_en", "")}</div>'
        html += '</div>'
        html += '<div class="header-left">'
        html += '<img src="_/theme/helwan_logo.png" class="logo" alt="Logo">'
        html += '</div>'
        html += '</div>'
        
        # Technical Specifications
        specs_title = 'المواصفات الفنية:' if is_ar else 'Technical Specifications:'
        html += f'<div class="section-title">{specs_title}</div>'
        
        # Add tech specs similar to quotation (simplified)
        html += '<table class="tech-table">'
        
        winder_type = str(data.get('winder_type', '')).upper()
        is_double_winder = 'DOUBLE' in winder_type
        model = str(data.get('model', '')).upper()
        is_belt_drive = 'METAL' not in model
        machine_width = float(data.get('machine_width', 0) or 0)
        
        specs = [
            ('أوجه الطباعة' if is_ar else 'Printing Sides', '2'),
            ('أقصى عرض للفيلم' if is_ar else 'Max Film Width', f"{int(machine_width * 10 + 50)} mm" if machine_width else ''),
            ('أقصى عرض للطباعة' if is_ar else 'Max Print Width', f"{int(machine_width * 10 - 40)} mm" if machine_width else ''),
            ('نوع الأنيلوكس' if is_ar else 'Anilox Type', ('انيلوكس سيراميك' if is_ar else 'Ceramic Anilox') if is_belt_drive else ('انيلوكس معدني' if is_ar else 'Metal Anilox')),
            ('طريقة نقل القدرة' if is_ar else 'Power Transmission', ('سيور' if is_ar else 'Belt Drive') if is_belt_drive else ('جيربوكس' if is_ar else 'Gear Drive')),
        ]
        
        row_num = 1
        for label, value in specs:
            if value:
                html += f'<tr><td class="row-num">{row_num}</td><th>{label}</th><td class="value">{value}</td></tr>'
                row_num += 1
        html += '</table>'
        
        html += '</div>'  # End Page 2
        
        # ==================== PAGE 3 - Financial & Payments ====================
        html += f'<div class="template-page page-break-before {dir_class}">'
        
        # Header repeated
        html += '<div class="header">'
        html += '<div class="header-right">'
        html += f'<div style="font-size:14px;color:#333;">{c.get("quotation_location_ar" if is_ar else "quotation_location_en", "")}</div>'
        html += '</div>'
        html += '<div class="header-left">'
        html += '<img src="_/theme/helwan_logo.png" class="logo" alt="Logo">'
        html += '</div>'
        html += '</div>'
        
        # Financial Section
        financial_title = 'القيمة المالية للعقد:' if is_ar else 'Contract Value:'
        html += f'<div class="section-title">{financial_title}</div>'
        
        html += '<div class="financial-box">'
        total_price = data.get('total_price', 0)
        currency = 'ج.م' if is_ar else 'EGP'
        html += f'<div class="total-price">{total_price:,.0f} {currency}</div>'
        
        price_note = 'القيمة شاملة التوريد والتركيب والضمان' if is_ar else 'Price includes supply, installation, and warranty'
        html += f'<div style="text-align:center;font-size:12px;color:#666;">{price_note}</div>'
        html += '</div>'
        
        # Payment Schedule
        if self.payment_data:
            payment_title = 'جدول الدفعات:' if is_ar else 'Payment Schedule:'
            html += f'<div class="section-title">{payment_title}</div>'
            
            html += '<table class="payment-schedule-table">'
            html += '<tr>'
            html += f'<th>{"#"}</th>'
            html += f'<th>{"البند" if is_ar else "Description"}</th>'
            html += f'<th>{"النسبة %" if is_ar else "Percentage %"}</th>'
            html += f'<th>{"المبلغ" if is_ar else "Amount"}</th>'
            html += f'<th>{"التاريخ" if is_ar else "Date"}</th>'
            html += '</tr>'
            
            for i, payment in enumerate(self.payment_data):
                label = payment.get('label_ar' if is_ar else 'label_en', '')
                percentage = payment.get('percentage', 0)
                amount = payment.get('amount', 0)
                date = payment.get('date', '')
                
                html += f'<tr>'
                html += f'<td>{i + 1}</td>'
                html += f'<td style="text-align:{"right" if is_ar else "left"};font-weight:bold;">{label}</td>'
                html += f'<td>{percentage:.1f}%</td>'
                html += f'<td>{amount:,.0f} {currency}</td>'
                html += f'<td>{date}</td>'
                html += f'</tr>'
            
            html += '</table>'
        
        # Terms & Conditions
        terms_title = 'الشروط والأحكام:' if is_ar else 'Terms & Conditions:'
        html += f'<div class="section-title">{terms_title}</div>'
        
        warranty_months = c.get('warranty_months', '12')
        
        terms = [
            f'مدة الضمان: {warranty_months} شهر' if is_ar else f'Warranty Period: {warranty_months} months',
            'يشمل الضمان جميع قطع الغيار والصيانة' if is_ar else 'Warranty covers all spare parts and maintenance',
            'التركيب والتدريب مجاني' if is_ar else 'Installation and training are free',
        ]
        
        html += '<ul style="font-size:12px;line-height:1.8;">'
        for term in terms:
            html += f'<li>{term}</li>'
        html += '</ul>'
        
        # Signatures
        html += '<div style="margin-top:40px;display:flex;justify-content:space-between;">'
        
        party1 = 'الطرف الأول (البائع)' if is_ar else 'First Party (Seller)'
        party2 = 'الطرف الثاني (المشتري)' if is_ar else 'Second Party (Buyer)'
        signature = 'التوقيع:' if is_ar else 'Signature:'
        
        html += f'''
        <div style="text-align:center;">
            <div style="font-weight:bold;margin-bottom:10px;">{party1}</div>
            <div>{c.get("company_name_ar" if is_ar else "company_name_en", "")}</div>
            <div style="margin-top:50px;border-top:1px solid #333;padding-top:5px;">{signature}</div>
        </div>
        <div style="text-align:center;">
            <div style="font-weight:bold;margin-bottom:10px;">{party2}</div>
            <div>{data.get('client_name', '')}</div>
            <div style="margin-top:50px;border-top:1px solid #333;padding-top:5px;">{signature}</div>
        </div>
        '''
        html += '</div>'
        
        html += '</div>'  # End Page 3
        
        return html

    # ==================== Export Functions ====================
    def print_contract(self):
        anvil.js.window.print()

    def export_pdf(self):
        js_code = """
        (function() {
            var content = document.getElementById('templateContent');
            if (!content) { alert('No content to export'); return; }
            
            var printWin = window.open('', '_blank');
            printWin.document.write('<html><head><title>Contract</title>');
            printWin.document.write('<style>');
            printWin.document.write(document.querySelector('style').innerHTML);
            printWin.document.write('body { margin: 0; padding: 20px; }');
            printWin.document.write('.controls-bar { display: none !important; }');
            printWin.document.write('</style></head><body>');
            printWin.document.write(content.innerHTML);
            printWin.document.write('</body></html>');
            printWin.document.close();
            
            setTimeout(function() {
                printWin.print();
            }, 500);
        })();
        """
        anvil.js.window.eval(js_code)

    def export_excel(self):
        if not self.current_data:
            alert('Please select a quotation first')
            return
        # Reuse the quotation excel export
        try:
            q_num = self.current_data.get('quotation_number', 0)
            result = anvil.server.call('export_quotation_excel', q_num)
            if result.get('success'):
                media = result.get('file')
                if media:
                    anvil.media.download(media)
            else:
                alert(f"Error: {result.get('message', 'Unknown error')}")
        except Exception as e:
            alert(f"Error exporting Excel: {str(e)}")

    # ==================== Server Calls ====================
    def load_quotation_for_print(self, quotation_number):
        try:
            user_email = anvil.js.window.localStorage.getItem('user_email') or ''
            result = anvil.server.call('get_quotation_pdf_data', int(quotation_number), user_email)
            return result
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def search_quotations_for_print(self, query=''):
        try:
            result = anvil.server.call('get_quotations_list', query, include_deleted=False)
            return result
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def get_all_settings(self):
        try:
            result = anvil.server.call('get_all_settings')
            return result
        except Exception as e:
            return {'success': False, 'message': str(e)}

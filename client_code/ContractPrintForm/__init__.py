from ._anvil_designer import ContractPrintFormTemplate
from anvil import *
import anvil.server
import anvil.js
import json
from datetime import datetime, date

class ContractPrintForm(ContractPrintFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # State
        self.current_lang = 'ar'
        self.current_data = None
        self.all_quotations = []
        self.payment_data = []  # Store payment schedule
        self.payment_method = 'percentage'  # percentage or amount
        self.delivery_date = ''  # Expected delivery date

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
        anvil.js.window.updateDeliveryDate = self.update_delivery_date

        # Payment Modal Functions
        anvil.js.window.openPaymentModal = self.open_payment_modal
        anvil.js.window.closePaymentModal = self.close_payment_modal
        anvil.js.window.updatePaymentRows = self.update_payment_rows
        anvil.js.window.updatePaymentMethod = self.update_payment_method
        anvil.js.window.savePayments = self.save_payments
        anvil.js.window.calculateTotalPercentage = self.calculate_total_percentage
        anvil.js.window.saveContract = self.save_contract

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
            try:
                total = float(total) if total else 0
            except:
                total = 0
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

    def update_delivery_date(self):
        """Update delivery date from input"""
        delivery_input = anvil.js.window.document.getElementById('deliveryDateInput')
        if delivery_input:
            self.delivery_date = str(delivery_input.value or '')
            if self.current_data:
                self.render_contract()

    def validate_payments(self):
        """Validate payment data like VBA code"""
        is_ar = self.current_lang == 'ar'
        value_inputs = anvil.js.window.document.querySelectorAll('.payment-value')
        date_inputs = anvil.js.window.document.querySelectorAll('.payment-date')
        
        total_price = float(self.current_data.get('total_price', 0) or 0)
        dates_used = []
        total_value = 0
        today = date.today()
        
        for i, (val_inp, date_inp) in enumerate(zip(value_inputs, date_inputs)):
            val = float(val_inp.value or 0)
            date_str = str(date_inp.value or '')
            
            # Check if date is empty
            if not date_str:
                msg = f'من فضلك أدخل تاريخ صحيح للدفعة رقم {i+1}' if is_ar else f'Please enter a valid date for installment {i+1}'
                alert(msg)
                return False
            
            # Parse and validate date
            try:
                payment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except:
                msg = f'تاريخ غير صحيح للدفعة رقم {i+1}' if is_ar else f'Invalid date for installment {i+1}'
                alert(msg)
                return False
            
            # Check date not before today
            if payment_date < today:
                msg = f'تاريخ الدفعة رقم {i+1} لا يمكن أن يكون قبل تاريخ اليوم' if is_ar else f'Installment {i+1} date cannot be earlier than today'
                alert(msg)
                return False
            
            # Check for duplicate dates
            if date_str in dates_used:
                msg = 'تاريخ مكرر! من فضلك أدخل تاريخ مختلف لكل دفعة' if is_ar else 'Duplicate date! Please provide a unique date for each installment'
                alert(msg)
                return False
            dates_used.append(date_str)
            
            total_value += val
        
        # Validate totals
        if self.payment_method == 'percentage':
            if round(total_value, 2) != 100:
                msg = f'إجمالي النسب غير صحيح!\nالإجمالي المطلوب: 100%\nالإجمالي المدخل: {total_value}%' if is_ar else f'Total percentage is incorrect!\nRequired: 100%\nEntered: {total_value}%'
                alert(msg)
                return False
        else:
            if round(total_value, 2) != round(total_price, 2):
                diff = abs(total_price - total_value)
                msg = f'المبالغ المدخلة لا تطابق إجمالي قيمة العقد!\nقيمة العقد: {total_price:,.2f}\nالإجمالي المدخل: {total_value:,.2f}\nالفرق: {diff:,.2f}' if is_ar else f'Amounts do not match contract value!\nContract: {total_price:,.2f}\nEntered: {total_value:,.2f}\nDifference: {diff:,.2f}'
                alert(msg)
                return False
        
        return True

    def save_payments(self):
        """Save payment data with validation"""
        # Validate first
        if not self.validate_payments():
            return
        
        value_inputs = anvil.js.window.document.querySelectorAll('.payment-value')
        date_inputs = anvil.js.window.document.querySelectorAll('.payment-date')
        
        self.payment_data = []
        total_price = float(self.current_data.get('total_price', 0) or 0)
        
        labels_ar = ['مقدم تعاقد', 'الدفعة الثانية', 'الدفعة الثالثة', 'الدفعة الرابعة', 
                     'الدفعة الخامسة', 'الدفعة السادسة', 'الدفعة السابعة', 'الدفعة الثامنة',
                     'الدفعة التاسعة', 'الدفعة العاشرة', 'الدفعة الحادية عشر', 'الدفعة الثانية عشر']
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
                    'label_ar': labels_ar[i] if i < len(labels_ar) else f'الدفعة {i+1}',
                    'label_en': labels_en[i] if i < len(labels_en) else f'Installment {i+1}',
                    'value': val,
                    'percentage': percentage,
                    'amount': amount,
                    'date': date_val,
                    'method': self.payment_method
                })
        
        self.close_payment_modal()
        
        # Show success message
        is_ar = self.current_lang == 'ar'
        msg = 'تم حفظ بيانات الدفعات بنجاح' if is_ar else 'Payment data saved successfully'
        Notification(msg, style='success').show()
        
        if self.current_data:
            self.render_contract()

    def save_contract(self):
        """Save complete contract data to database"""
        if not self.current_data:
            alert('Please select a quotation first')
            return
        
        if not self.payment_data:
            is_ar = self.current_lang == 'ar'
            alert('من فضلك أدخل بيانات الدفعات أولاً' if is_ar else 'Please enter payment data first')
            return
        
        # Get delivery date
        delivery_input = anvil.js.window.document.getElementById('deliveryDateInput')
        delivery_date = str(delivery_input.value) if delivery_input else ''
        
        # Prepare contract data
        contract_data = {
            'quotation_number': self.current_data.get('quotation_number'),
            'client_name': self.current_data.get('client_name'),
            'company': self.current_data.get('company'),
            'phone': self.current_data.get('phone'),
            'country': self.current_data.get('country'),
            'address': self.current_data.get('address'),
            'model': self.current_data.get('model'),
            'colors_count': self.current_data.get('colors_count'),
            'machine_width': self.current_data.get('machine_width'),
            'material': self.current_data.get('material'),
            'winder_type': self.current_data.get('winder_type'),
            'price_mode': self.current_data.get('price_mode'),
            'total_price': self.current_data.get('total_price'),
            'currency': self.current_data.get('currency'),
            'payment_method': self.payment_method,
            'num_payments': len(self.payment_data),
            'payments': self.payment_data,
            'delivery_date': delivery_date,
            'contract_date': date.today().isoformat(),
            'language': self.current_lang
        }
        
        try:
            result = anvil.server.call('save_contract', contract_data)
            if result.get('success'):
                is_ar = self.current_lang == 'ar'
                msg = 'تم حفظ بيانات العقد بنجاح' if is_ar else 'Contract saved successfully'
                Notification(msg, style='success').show()
            else:
                alert(f"Error: {result.get('message', 'Unknown error')}")
        except Exception as e:
            alert(f"Error saving contract: {str(e)}")

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
        
        # Safe get for numeric values
        def safe_float(val, default=0):
            try:
                return float(val) if val else default
            except:
                return default
        
        # Get delivery date
        delivery_input = anvil.js.window.document.getElementById('deliveryDateInput')
        delivery_date = str(delivery_input.value) if delivery_input and delivery_input.value else ''
        
        q_num = data.get('quotation_number', '')
        total_price = safe_float(data.get('total_price', 0))
        currency = 'ج.م' if is_ar else 'EGP'
        
        # ==================== PAGE 1 - Contract Info ====================
        html += f'<div class="template-page {dir_class}">'
        
        # Header
        html += '<div class="header">'
        html += '<div class="header-right">'
        html += f'<div style="font-size:14px;color:#333;">{c.get("quotation_location_ar" if is_ar else "quotation_location_en", "القاهرة" if is_ar else "Cairo")}</div>'
        html += f'<div style="font-size:13px;color:#666;">{c.get("company_address_ar" if is_ar else "company_address_en", "")}</div>'
        html += '</div>'
        html += '<div class="header-left">'
        html += '<img src="_/theme/helwan_logo.png" class="logo" alt="Logo" style="max-width:120px;">'
        html += f'<div class="company-name">{c.get("company_name_ar" if is_ar else "company_name_en", "حلوان بلاست" if is_ar else "Helwan Plast")}</div>'
        html += '</div>'
        html += '</div>'
        
        # Contract Title
        contract_title = 'عقد توريد ماكينة طباعة فلكسو' if is_ar else 'Flexo Printing Machine Supply Contract'
        html += f'<div style="text-align:center;margin:25px 0;"><h2 style="color:var(--primary-color);font-size:22px;border-bottom:3px solid var(--accent-color);display:inline-block;padding-bottom:10px;">{contract_title}</h2></div>'
        
        # Contract Info Box
        html += '<div style="display:flex;justify-content:space-between;margin-bottom:20px;background:#f8f9fa;padding:15px;border-radius:8px;">'
        html += f'<div><strong>{"رقم العقد" if is_ar else "Contract No"}:</strong> <span style="color:var(--accent-color);font-size:18px;font-weight:bold;">C-{q_num}</span></div>'
        html += f'<div><strong>{"التاريخ" if is_ar else "Date"}:</strong> {date.today().strftime("%Y-%m-%d")}</div>'
        if delivery_date:
            html += f'<div><strong>{"تاريخ التسليم المتوقع" if is_ar else "Expected Delivery"}:</strong> {delivery_date}</div>'
        html += '</div>'
        
        # First Party (Seller)
        first_party_title = 'الطرف الأول (البائع):' if is_ar else 'First Party (Seller):'
        html += f'<div class="section-title">{first_party_title}</div>'
        html += '<table class="details-table">'
        html += f'<tr><th>{"الاسم" if is_ar else "Name"}</th><td>{c.get("company_name_ar" if is_ar else "company_name_en", "حلوان بلاست" if is_ar else "Helwan Plast")}</td></tr>'
        html += f'<tr><th>{"العنوان" if is_ar else "Address"}</th><td>{c.get("company_address_ar" if is_ar else "company_address_en", "")}</td></tr>'
        html += '</table>'
        
        # Second Party (Client)
        client_title = 'الطرف الثاني (المشتري):' if is_ar else 'Second Party (Buyer):'
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
        machine_title = 'موضوع العقد (تفاصيل الماكينة):' if is_ar else 'Subject of Contract (Machine Details):'
        html += f'<div class="section-title">{machine_title}</div>'
        html += '<table class="details-table">'
        
        machine_width = safe_float(data.get('machine_width', 0))
        machine_fields = [
            ('الموديل' if is_ar else 'Model', data.get('model', '')),
            ('عدد الألوان' if is_ar else 'Number of Colors', str(data.get('colors_count', '')) if data.get('colors_count') else ''),
            ('عرض الماكينة' if is_ar else 'Machine Width', f"{machine_width} cm" if machine_width else ''),
            ('نوع الخامة' if is_ar else 'Material', data.get('material', '')),
            ('نوع اللفاف' if is_ar else 'Winder Type', data.get('winder_type', '')),
        ]
        
        for label, value in machine_fields:
            if value and value != '0 cm' and value != ' cm':
                html += f'<tr><th>{label}</th><td>{value}</td></tr>'
        html += '</table>'
        
        html += '</div>'  # End Page 1
        
        # ==================== PAGE 2 - Technical Specs ====================
        html += f'<div class="template-page page-break-before {dir_class}">'
        
        # Header repeated
        html += '<div class="header">'
        html += '<div class="header-right">'
        html += f'<div style="font-size:14px;color:#333;">{"عقد رقم" if is_ar else "Contract No"}: C-{q_num}</div>'
        html += '</div>'
        html += '<div class="header-left">'
        html += '<img src="_/theme/helwan_logo.png" class="logo" alt="Logo" style="max-width:80px;">'
        html += '</div>'
        html += '</div>'
        
        # Technical Specifications
        specs_title = 'المواصفات الفنية:' if is_ar else 'Technical Specifications:'
        html += f'<div class="section-title">{specs_title}</div>'
        
        html += '<table class="tech-table">'
        
        winder_type = str(data.get('winder_type', '') or '').upper()
        is_double_winder = 'DOUBLE' in winder_type
        model = str(data.get('model', '') or '').upper()
        is_belt_drive = 'METAL' not in model
        
        specs = [
            ('أوجه الطباعة' if is_ar else 'Printing Sides', '2'),
            ('أقصى عرض للفيلم' if is_ar else 'Max Film Width', f"{int(machine_width * 10 + 50)} mm" if machine_width else ''),
            ('أقصى عرض للطباعة' if is_ar else 'Max Print Width', f"{int(machine_width * 10 - 40)} mm" if machine_width else ''),
            ('نوع الأنيلوكس' if is_ar else 'Anilox Type', ('انيلوكس سيراميك' if is_ar else 'Ceramic Anilox') if is_belt_drive else ('انيلوكس معدني' if is_ar else 'Metal Anilox')),
            ('طريقة نقل القدرة' if is_ar else 'Power Transmission', ('سيور' if is_ar else 'Belt Drive') if is_belt_drive else ('جيربوكس' if is_ar else 'Gear Drive')),
            ('أقصى سرعة للماكينة' if is_ar else 'Max Machine Speed', '120 m/min' if is_belt_drive else '100 m/min'),
        ]
        
        row_num = 1
        for label, value in specs:
            if value:
                html += f'<tr><td class="row-num" style="width:40px;text-align:center;background:#f5f5f5;">{row_num}</td><th style="width:40%;">{label}</th><td class="value">{value}</td></tr>'
                row_num += 1
        html += '</table>'
        
        html += '</div>'  # End Page 2
        
        # ==================== PAGE 3 - Financial & Payments ====================
        html += f'<div class="template-page page-break-before {dir_class}">'
        
        # Header repeated
        html += '<div class="header">'
        html += '<div class="header-right">'
        html += f'<div style="font-size:14px;color:#333;">{"عقد رقم" if is_ar else "Contract No"}: C-{q_num}</div>'
        html += '</div>'
        html += '<div class="header-left">'
        html += '<img src="_/theme/helwan_logo.png" class="logo" alt="Logo" style="max-width:80px;">'
        html += '</div>'
        html += '</div>'
        
        # Financial Section
        financial_title = 'القيمة المالية للعقد:' if is_ar else 'Contract Value:'
        html += f'<div class="section-title">{financial_title}</div>'
        
        html += '<div class="financial-box" style="background:linear-gradient(135deg,#667eea11,#764ba211);border:2px solid var(--accent-color);">'
        html += f'<div class="total-price" style="font-size:28px;color:var(--accent-color);">{total_price:,.0f} {currency}</div>'
        
        price_note = 'القيمة شاملة التوريد والتركيب والتشغيل والتدريب والضمان' if is_ar else 'Price includes supply, installation, commissioning, training and warranty'
        html += f'<div style="text-align:center;font-size:12px;color:#666;margin-top:10px;">{price_note}</div>'
        html += '</div>'
        
        # Payment Schedule
        if self.payment_data:
            payment_title = 'جدول الدفعات:' if is_ar else 'Payment Schedule:'
            html += f'<div class="section-title">{payment_title}</div>'
            
            html += '<table class="payment-schedule-table" style="border:2px solid var(--accent-color);">'
            html += '<tr style="background:linear-gradient(135deg,#667eea,#764ba2);color:white;">'
            html += f'<th style="color:white;padding:10px;">{"#"}</th>'
            html += f'<th style="color:white;padding:10px;">{"البند" if is_ar else "Description"}</th>'
            html += f'<th style="color:white;padding:10px;">{"النسبة" if is_ar else "Percentage"}</th>'
            html += f'<th style="color:white;padding:10px;">{"المبلغ" if is_ar else "Amount"}</th>'
            html += f'<th style="color:white;padding:10px;">{"التاريخ" if is_ar else "Date"}</th>'
            html += '</tr>'
            
            for i, payment in enumerate(self.payment_data):
                label = payment.get('label_ar' if is_ar else 'label_en', '')
                percentage = payment.get('percentage', 0)
                amount = payment.get('amount', 0)
                pdate = payment.get('date', '')
                bg = '#f8f9fa' if i % 2 == 0 else 'white'
                
                html += f'<tr style="background:{bg};">'
                html += f'<td style="padding:8px;font-weight:bold;">{i + 1}</td>'
                html += f'<td style="padding:8px;text-align:{"right" if is_ar else "left"};font-weight:bold;">{label}</td>'
                html += f'<td style="padding:8px;">{percentage:.1f}%</td>'
                html += f'<td style="padding:8px;font-weight:bold;color:var(--accent-color);">{amount:,.0f} {currency}</td>'
                html += f'<td style="padding:8px;">{pdate}</td>'
                html += f'</tr>'
            
            # Total row
            html += f'<tr style="background:#667eea22;font-weight:bold;">'
            html += f'<td colspan="2" style="padding:10px;text-align:{"right" if is_ar else "left"};">{"الإجمالي" if is_ar else "Total"}</td>'
            html += f'<td style="padding:10px;">100%</td>'
            html += f'<td style="padding:10px;color:var(--accent-color);font-size:16px;">{total_price:,.0f} {currency}</td>'
            html += f'<td></td>'
            html += f'</tr>'
            
            html += '</table>'
        
        # Delivery Date
        if delivery_date:
            html += f'<div style="margin:20px 0;padding:15px;background:#e8f5e9;border-radius:8px;border-right:4px solid #4caf50;">'
            html += f'<strong>{"تاريخ التسليم المتوقع" if is_ar else "Expected Delivery Date"}:</strong> {delivery_date}'
            html += '</div>'
        
        # Terms & Conditions
        terms_title = 'الشروط والأحكام:' if is_ar else 'Terms & Conditions:'
        html += f'<div class="section-title">{terms_title}</div>'
        
        warranty_months = c.get('warranty_months', '12')
        
        terms = [
            f'{"مدة الضمان" if is_ar else "Warranty Period"}: {warranty_months} {"شهر" if is_ar else "months"}',
            'يشمل الضمان جميع قطع الغيار والصيانة الدورية' if is_ar else 'Warranty covers all spare parts and periodic maintenance',
            'التركيب والتشغيل والتدريب مجاني' if is_ar else 'Installation, commissioning and training are free',
            'يلتزم الطرف الثاني بالسداد في المواعيد المحددة' if is_ar else 'Second party commits to payment on scheduled dates',
        ]
        
        html += '<ul style="font-size:12px;line-height:2;background:#f8f9fa;padding:15px 30px;border-radius:8px;">'
        for term in terms:
            html += f'<li style="margin-bottom:5px;">{term}</li>'
        html += '</ul>'
        
        # Signatures
        html += '<div style="margin-top:50px;display:flex;justify-content:space-around;padding-top:20px;">'
        
        party1 = 'الطرف الأول (البائع)' if is_ar else 'First Party (Seller)'
        party2 = 'الطرف الثاني (المشتري)' if is_ar else 'Second Party (Buyer)'
        signature = 'التوقيع' if is_ar else 'Signature'
        
        html += f'''
        <div style="text-align:center;min-width:200px;">
            <div style="font-weight:bold;margin-bottom:10px;font-size:14px;color:var(--primary-color);">{party1}</div>
            <div style="margin-bottom:5px;">{c.get("company_name_ar" if is_ar else "company_name_en", "حلوان بلاست" if is_ar else "Helwan Plast")}</div>
            <div style="margin-top:60px;border-top:2px solid #333;padding-top:8px;font-size:12px;">{signature}</div>
        </div>
        <div style="text-align:center;min-width:200px;">
            <div style="font-weight:bold;margin-bottom:10px;font-size:14px;color:var(--primary-color);">{party2}</div>
            <div style="margin-bottom:5px;">{data.get('client_name', '')}</div>
            <div style="margin-top:60px;border-top:2px solid #333;padding-top:8px;font-size:12px;">{signature}</div>
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

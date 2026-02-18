from ._anvil_designer import ContractPrintFormTemplate
from anvil import *
import anvil.users
import anvil.server
import anvil.js
import json
import logging
import re
from datetime import datetime, date

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


class ContractPrintForm(ContractPrintFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # State
        self.current_lang = 'ar'
        self.current_data = None
        self.all_quotations = []
        self.payment_data = []
        self.payment_method = 'percentage'
        self.delivery_date = ''
        self.display_contract_number = None  # ط±ظ‚ظ… ط§ظ„ط¹ظ‚ط¯ ط§ظ„ظ…ط­ظپظˆط¸
        self.preview_contract_serial = None  # ط§ظ„ظ…طھط³ظ„ط³ظ„ ط§ظ„طھط§ظ„ظٹ ظ…ظ† ط¬ط¯ظˆظ„ ط§ظ„ط¹ظ‚ظˆط¯ (ظ„ظ„ظ…ط¹ط§ظٹظ†ط©)

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
        anvil.js.window.handleSavePayments = self._handle_save_payments_click
        anvil.js.window.calculateTotalPercentage = self.calculate_total_percentage
        anvil.js.window.saveContract = self.save_contract
        anvil.js.window.deleteContract = self.delete_contract
        anvil.js.window.validateNumPayments = self.validate_num_payments

        # Supplier bridge for auto-invoice
        anvil.js.window.pyGetSuppliersListForContract = self.get_suppliers_list
        # Inventory bridge for in-stock flow
        anvil.js.window.loadAvailableInventory = self.load_available_inventory

        # Notification bridges
        register_notif_bridges()

    def _show_msg(self, msg, typ='error'):
        """ط¹ط±ط¶ ط±ط³ط§ظ„ط© ظ…ظ† ط§ظ„ظ†ط¸ط§ظ… ظپظ‚ط· (ط¨ط¯ظˆظ† alert ط§ظ„ط¨ط±ط§ظˆط²ط±)."""
        s = str(msg).strip() or ('ط®ط·ط£' if self.current_lang == 'ar' else 'Error')
        try:
            if anvil.js.window.showNotification:
                anvil.js.window.showNotification(typ, '', s)
        except Exception:
            pass
        try:
            Notification(s).show()
        except Exception:
            pass

    def _validate_delivery_date(self):
        """ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ط¥ط¯ط®ط§ظ„ طھط§ط±ظٹط® ط§ظ„طھط³ظ„ظٹظ… â€” ط¥ط¬ط¨ط§ط±ظٹ ظپظ‚ط· ط¹ظ†ط¯ Save Contract / Update ظˆظ„ظٹط³ ط¹ظ†ط¯ ط­ظپط¸ ط§ظ„ط¯ظپط¹ط§طھ ظ…ظ† ظ†ط§ظپط°ط© ط¥ط¯ط§ط±ط© ط§ظ„ط¯ظپط¹ط§طھ."""
        delivery_input = anvil.js.window.document.getElementById('deliveryDateInput')
        delivery_val = (delivery_input.value or '').strip() if delivery_input else ''
        if not delivery_val:
            is_ar = self.current_lang == 'ar'
            msg_ar = 'طھط§ط±ظٹط® ط§ظ„طھط³ظ„ظٹظ… (Expected Delivery Date) ظ…ط·ظ„ظˆط¨. ظ…ظ† ظپط¶ظ„ظƒ ط£ط¯ط®ظ„ طھط§ط±ظٹط® ط§ظ„طھط³ظ„ظٹظ… ظ‚ط¨ظ„ ط§ظ„ط­ظپط¸ ط£ظˆ طھط£ظƒظٹط¯ ط§ظ„ط¯ظپط¹ط§طھ.'
            msg_en = 'Expected Delivery Date is required. Please enter the delivery date before saving or confirming payments.'
            return False, msg_ar, msg_en
        return True, None, None

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
        """ط¹ظ‚ط¯ ط¬ط¯ظٹط¯: ظپظ‚ط· ط§ظ„ط¹ط±ظˆط¶ ط§ظ„طھظٹ ظ„ظ… ظٹظڈظ†ط´ط£ ظ„ظ‡ط§ ط¹ظ‚ط¯. ط؛ظٹط± ط°ظ„ظƒ: ظƒظ„ ط§ظ„ط¹ط±ظˆط¶ (ظ„ظ„طھظˆط§ظپظ‚ ظ…ط¹ ط§ظ„ط±ظˆط§ط¨ط· ط§ظ„ظ‚ط¯ظٹظ…ط©)."""
        try:
            anvil.js.window.showLoadingOverlay()
        except Exception:
            pass
        try:
            auth = anvil.js.window.sessionStorage.getItem('auth_token') or None
            try:
                hash_val = (anvil.js.window.location.hash or '').strip()
            except Exception:
                hash_val = ''
            if hash_val == '#contract-new':
                result = anvil.server.call('get_quotations_list_without_contract', '', auth)
            else:
                result = anvil.server.call('get_quotations_list', '', False, auth)
            if result and result.get('success'):
                self.all_quotations = result.get('data', [])
                self.populate_dropdown(self.all_quotations)
        except Exception as e:
            logger.debug("Error loading quotations: %s", e)
        finally:
            try:
                anvil.js.window.hideLoadingOverlay()
            except Exception:
                pass

    def populate_dropdown(self, quotations):
        select = anvil.js.window.document.getElementById('quotationSelect')
        if not select:
            return
        opts = ['<option value="">-- Select Quotation (' + str(_h(len(quotations))) + ') --</option>']
        for quot in quotations:
            q_num = _h(quot.get('Quotation#', ''))
            client_name = _h(quot.get('Client Name', ''))
            company = _h(quot.get('Company', ''))
            client_display = (str(client_name) + ' - ' + str(company)).strip(' - ') if company else client_name
            model = _h(quot.get('Model', ''))
            option_text = '#' + str(q_num) + ' - ' + str(client_display) + ' - ' + str(model)
            opts.append('<option value="' + str(q_num) + '">' + str(option_text) + '</option>')
        select.innerHTML = ''.join(opts)

    def filter_quotations(self):
        search_input = anvil.js.window.document.getElementById('searchInput')
        if not search_input:
            return
        query = str(search_input.value).lower().strip()
        if not query:
            self.populate_dropdown(self.all_quotations)
            return
        filtered = [q for q in self.all_quotations 
                    if query in str(q.get('Quotation#', '')).lower() 
                    or query in str(q.get('Client Name', '')).lower()
                    or query in str(q.get('Company', '')).lower()
                    or query in str(q.get('Model', '')).lower()]
        self.populate_dropdown(filtered)

    def load_selected_quotation(self):
        select = anvil.js.window.document.getElementById('quotationSelect')
        if not select or not select.value:
            return
        try:
            q_num = int(select.value)
        except (ValueError, TypeError):
            self._show_msg('Invalid quotation number selected')
            return
        try:
            anvil.js.window.showLoadingOverlay()
        except Exception:
            pass
        try:
            result = self.load_quotation_for_print(q_num)
            if result and result.get('success'):
                self.current_data = result.get('data', {})
                self.display_contract_number = None
                self.preview_contract_serial = None
                try:
                    auth = anvil.js.window.sessionStorage.getItem('auth_token') or None
                    contract_res = anvil.server.call('get_contract', q_num, auth)
                    if contract_res and contract_res.get('success') and contract_res.get('data'):
                        self.display_contract_number = contract_res['data'].get('contract_number')
                    else:
                    # ط¬ظ„ط¨ ط§ظ„ظ…طھط³ظ„ط³ظ„ ط§ظ„طھط§ظ„ظٹ ظ…ظ† ط¬ط¯ظˆظ„ ط§ظ„ط¹ظ‚ظˆط¯ ظ„ظ„ظ…ط¹ط§ظٹظ†ط© (ظ…ظƒط§ظ† ط§ظ„ط´ط±ط·ط©)
                    preview_res = anvil.server.call('get_next_contract_serial_preview', auth)
                    if preview_res and preview_res.get('success'):
                        self.preview_contract_serial = preview_res.get('next_serial', 2)
            except Exception:
                pass
            self.render_template()
            # Update pricing mode UI based on quotation data
            pricing_mode = self.current_data.get('pricing_mode', '') or ''
            try:
                anvil.js.window.updatePricingModeUI(pricing_mode)
            except Exception:
                pass
            # Update total in payment modal - remove commas from formatted price
            total_str = str(self.current_data.get('total_price', 0) or 0).replace(',', '').replace('طŒ', '')
            try:
                total = float(total_str) if total_str else 0
            except Exception:
                total = 0
            total_el = anvil.js.window.document.getElementById('totalContractAmount')
            if total_el:
                total_el.textContent = "{:,.2f}".format(total)
            # Also trigger calculation to update entered/remaining
            self.calculate_total_percentage()
        except Exception as e:
            self._show_msg(str(e))
        finally:
            try:
                anvil.js.window.hideLoadingOverlay()
            except Exception:
                pass

    def switch_language(self, lang):
        self.current_lang = lang
        anvil.js.window.localStorage.setItem('hp_language', lang)
        self.update_language_buttons()
        if self.current_data:
            self.render_template()

    def update_delivery_date(self):
        delivery_input = anvil.js.window.document.getElementById('deliveryDateInput')
        if delivery_input:
            self.delivery_date = str(delivery_input.value or '')
            if self.current_data:
                self.render_template()

    # ==================== Payment Modal ====================
    def validate_num_payments(self):
        """Validate number of payments input - must be 1-12"""
        num_input = anvil.js.window.document.getElementById('numPayments')
        if not num_input:
            return False
        
        val = str(num_input.value or '').strip()
        is_ar = self.current_lang == 'ar'
        
        # Check if empty or contains non-numeric characters
        if not val or not val.isdigit():
            msg = 'ط¹ط¯ط¯ ط§ظ„ط¯ظپط¹ط§طھ ظٹط¬ط¨ ط£ظ† ظٹظƒظˆظ† ط±ظ‚ظ… ظ…ظ† 1 ط¥ظ„ظ‰ 12' if is_ar else 'Number of payments must be a number from 1 to 12'
            self._show_msg(msg)
            num_input.value = 3
            return False
        
        num = int(val)
        if num < 1 or num > 12:
            msg = 'ط¹ط¯ط¯ ط§ظ„ط¯ظپط¹ط§طھ ظٹط¬ط¨ ط£ظ† ظٹظƒظˆظ† ظ…ظ† 1 ط¥ظ„ظ‰ 12 ظپظ‚ط·' if is_ar else 'Number of payments must be between 1 and 12 only'
            self._show_msg(msg)
            num_input.value = max(1, min(12, num))
            return False
        
        return True

    def open_payment_modal(self):
        if not self.current_data:
            self._show_msg('Please select a quotation first')
            return
        overlay = anvil.js.window.document.getElementById('paymentModalOverlay')
        if overlay:
            overlay.classList.add('active')
            self.update_payment_rows()
            self.calculate_total_percentage()

    def close_payment_modal(self):
        overlay = anvil.js.window.document.getElementById('paymentModalOverlay')
        if overlay:
            overlay.classList.remove('active')
        err_el = anvil.js.window.document.getElementById('paymentModalError')
        if err_el:
            err_el.style.display = 'none'
            err_el.innerHTML = ''

    def _handle_save_payments_click(self):
        """ظٹط³طھط¯ط¹ظ‰ ظ…ظ† ط²ط± ط§ظ„ط­ظپط¸ ظپظٹ ظ†ط§ظپط°ط© ط§ظ„ط¯ظپط¹ط§طھ â€” ظٹط¹ط±ط¶ ط§ظ„ط±ط³ط§ظ„ط© ط¯ط§ط®ظ„ ط§ظ„ظ†ط§ظپط°ط© ظˆظ…ظ† ط®ظ„ط§ظ„ ط¥ط´ط¹ط§ط± ط§ظ„ظ†ط¸ط§ظ… ط¥ظ† ظپط´ظ„ ط§ظ„ط­ظپط¸."""
        result = self.save_payments()
        err_el = anvil.js.window.document.getElementById('paymentModalError')
        if err_el:
            if result and result.get('success'):
                err_el.style.display = 'none'
                err_el.innerHTML = ''
            else:
                msg = (result or {}).get('message') or ('ط­ط¯ط« ط®ط·ط£' if self.current_lang == 'ar' else 'An error occurred')
                err_el.textContent = msg
                err_el.style.display = 'block'
                try:
                    Notification(msg).show()
                except Exception:
                    pass

    def update_payment_method(self):
        radios = anvil.js.window.document.querySelectorAll('input[name="paymentMethod"]')
        for r in radios:
            if r.checked:
                self.payment_method = r.value
                break
        header = anvil.js.window.document.getElementById('valueHeader')
        if header:
            is_ar = self.current_lang == 'ar'
            if self.payment_method == 'percentage':
                header.textContent = 'ط§ظ„ظ†ط³ط¨ط© % / Percentage'
            else:
                header.textContent = 'ط§ظ„ظ…ط¨ظ„ط؛ / Amount'
        self.update_payment_rows()
        self.calculate_total_percentage()  # Recalculate when method changes

    def update_payment_rows(self):
        num_input = anvil.js.window.document.getElementById('numPayments')
        tbody = anvil.js.window.document.getElementById('paymentsTableBody')
        if not num_input or not tbody:
            return
        
        # Validate the number
        val = str(num_input.value or '').strip()
        if not val or not val.isdigit():
            num = 3
            num_input.value = 3
        else:
            num = int(val)
            if num < 1 or num > 12:
                is_ar = self.current_lang == 'ar'
                msg = 'ط¹ط¯ط¯ ط§ظ„ط¯ظپط¹ط§طھ ظٹط¬ط¨ ط£ظ† ظٹظƒظˆظ† ظ…ظ† 1 ط¥ظ„ظ‰ 12 ظپظ‚ط·' if is_ar else 'Number of payments must be between 1 and 12 only'
                self._show_msg(msg)
                num = max(1, min(12, num))
                num_input.value = num
        
        is_ar = self.current_lang == 'ar'
        rows_html = ''
        
        labels = {
            1: ('ظ…ظ‚ط¯ظ… طھط¹ط§ظ‚ط¯', 'Down Payment'),
            2: ('ط§ظ„ط¯ظپط¹ط© ط§ظ„ط«ط§ظ†ظٹط©', 'Installment 2'),
            3: ('ط§ظ„ط¯ظپط¹ط© ط§ظ„ط«ط§ظ„ط«ط©', 'Installment 3'),
            4: ('ط§ظ„ط¯ظپط¹ط© ط§ظ„ط±ط§ط¨ط¹ط©', 'Installment 4'),
            5: ('ط§ظ„ط¯ظپط¹ط© ط§ظ„ط®ط§ظ…ط³ط©', 'Installment 5'),
            6: ('ط§ظ„ط¯ظپط¹ط© ط§ظ„ط³ط§ط¯ط³ط©', 'Installment 6'),
            7: ('ط§ظ„ط¯ظپط¹ط© ط§ظ„ط³ط§ط¨ط¹ط©', 'Installment 7'),
            8: ('ط§ظ„ط¯ظپط¹ط© ط§ظ„ط«ط§ظ…ظ†ط©', 'Installment 8'),
            9: ('ط§ظ„ط¯ظپط¹ط© ط§ظ„طھط§ط³ط¹ط©', 'Installment 9'),
            10: ('ط§ظ„ط¯ظپط¹ط© ط§ظ„ط¹ط§ط´ط±ط©', 'Installment 10'),
            11: ('ط§ظ„ط¯ظپط¹ط© ط§ظ„ط­ط§ط¯ظٹط© ط¹ط´ط±', 'Installment 11'),
            12: ('ط§ظ„ط¯ظپط¹ط© ط§ظ„ط«ط§ظ†ظٹط© ط¹ط´ط±', 'Installment 12'),
        }
        
        placeholder = '%' if self.payment_method == 'percentage' else 'Amount'
        
        for i in range(1, num + 1):
            label = labels.get(i, ('ط§ظ„ط¯ظپط¹ط© ' + str(i), 'Installment ' + str(i)))
            label_text = str(label[0]) + ' / ' + str(label[1])
            
            saved_val = ''
            saved_date = ''
            if len(self.payment_data) >= i:
                saved_val = self.payment_data[i-1].get('value', '')
                saved_date = self.payment_data[i-1].get('date', '')
            
            bg_color = '#f8f9fa' if i % 2 == 0 else 'white'
            rows_html += (
                '<tr style="background:' + str(bg_color) + ';">'
                '<td style="padding:10px;"><strong>' + str(label_text) + '</strong></td>'
                '<td style="padding:10px;"><input type="number" class="payment-value" data-index="' + str(i) + '" '
                'value="' + str(saved_val) + '" placeholder="' + str(placeholder) + '" '
                'oninput="window.calculateTotalPercentage()" '
                'style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px;text-align:center;"></td>'
                '<td style="padding:10px;"><input type="date" class="payment-date" data-index="' + str(i) + '" value="' + str(saved_date) + '"'
                ' style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px;"></td>'
                '</tr>'
            )
        
        tbody.innerHTML = rows_html
        # Recalculate totals after updating rows
        self.calculate_total_percentage()

    def calculate_total_percentage(self):
        inputs = anvil.js.window.document.querySelectorAll('.payment-value')
        total_entered = 0
        for inp in inputs:
            val = float(inp.value or 0)
            total_entered += val
        
        # Get total contract amount (remove commas from formatted numbers)
        def safe_float(val):
            if val is None:
                return 0.0
            val_str = str(val).replace(',', '').replace('طŒ', '').strip()
            try:
                return float(val_str) if val_str else 0.0
            except Exception:
                return 0.0
        
        total_contract = safe_float(self.current_data.get('total_price', 0)) if self.current_data else 0
        
        total_el = anvil.js.window.document.getElementById('totalPercentage')
        total_unit = anvil.js.window.document.getElementById('totalUnit')
        entered_el = anvil.js.window.document.getElementById('enteredAmount')
        remaining_el = anvil.js.window.document.getElementById('remainingAmount')
        is_ar = self.current_lang == 'ar'
        
        if self.payment_method == 'percentage':
            # Calculate amounts from percentages
            entered_amount = total_contract * total_entered / 100
            remaining_amount = total_contract - entered_amount
            
            if total_el:
                total_el.textContent = "{:.1f}".format(total_entered)
                if total_unit:
                    total_unit.textContent = '%'
                # Color based on percentage
                if round(total_entered, 1) == 100:
                    total_el.style.color = '#4caf50'  # Green when 100%
                elif total_entered > 100:
                    total_el.style.color = '#f44336'  # Red when over 100%
                else:
                    total_el.style.color = '#ff9800'  # Orange when under 100%

            if entered_el:
                currency = 'ط¬.ظ…' if is_ar else 'EGP'
                entered_el.textContent = "{:,.0f}".format(entered_amount) + ' ' + currency
                entered_el.style.color = '#2196F3'

            if remaining_el:
                currency = 'ط¬.ظ…' if is_ar else 'EGP'
                remaining_el.textContent = "{:,.0f}".format(remaining_amount) + ' ' + currency
                if remaining_amount == 0:
                    remaining_el.style.color = '#4caf50'  # Green when done
                elif remaining_amount < 0:
                    remaining_el.style.color = '#f44336'  # Red when over
                else:
                    remaining_el.style.color = '#ff9800'  # Orange when remaining
        else:
            # Amount mode
            remaining_amount = total_contract - total_entered
            
            if total_el:
                currency = 'ط¬.ظ…' if is_ar else 'EGP'
                total_el.textContent = "{:,.0f}".format(total_entered)
                if total_unit:
                    total_unit.textContent = currency
                # Color based on amount
                if round(total_entered, 0) == round(total_contract, 0):
                    total_el.style.color = '#4caf50'  # Green when exact
                elif total_entered > total_contract:
                    total_el.style.color = '#f44336'  # Red when over
                else:
                    total_el.style.color = '#ff9800'  # Orange when under

            if entered_el:
                currency = 'ط¬.ظ…' if is_ar else 'EGP'
                entered_el.textContent = "{:,.0f}".format(total_entered) + ' ' + currency
                entered_el.style.color = '#2196F3'

            if remaining_el:
                currency = 'ط¬.ظ…' if is_ar else 'EGP'
                remaining_el.textContent = "{:,.0f}".format(remaining_amount) + ' ' + currency
                if remaining_amount == 0:
                    remaining_el.style.color = '#4caf50'
                elif remaining_amount < 0:
                    remaining_el.style.color = '#f44336'
                else:
                    remaining_el.style.color = '#ff9800'

    def validate_payments(self):
        is_ar = self.current_lang == 'ar'
        value_inputs = anvil.js.window.document.querySelectorAll('.payment-value')
        date_inputs = anvil.js.window.document.querySelectorAll('.payment-date')
        
        # Remove commas from formatted price
        price_str = str(self.current_data.get('total_price', 0) or 0).replace(',', '').replace('طŒ', '')
        try:
            total_price = float(price_str) if price_str else 0
        except Exception:
            total_price = 0
        today = date.today()
        errors = []
        dates_used = []
        last_date = None
        total_value = 0
        
        for i, (val_inp, date_inp) in enumerate(zip(value_inputs, date_inputs)):
            val = float(val_inp.value or 0)
            date_str = (str(date_inp.value or '')).strip()
            payment_date = None
            
            # طھط§ط±ظٹط® ظ†ط§ظ‚طµ: ظ„ظˆ ظپظٹظ‡ ظ‚ظٹظ…ط© ظˆظ…ظپظٹط´ طھط§ط±ظٹط®
            if val > 0 and not date_str:
                errors.append(
                    ('طھط§ط±ظٹط® ط§ظ„ط¯ظپط¹ط© ط±ظ‚ظ… ' + str(i+1) + ' ظ†ط§ظ‚طµ') if is_ar else ('Date for installment ' + str(i+1) + ' is missing')
                )
            # ط¯ظپط¹ط© ظ†ط§ظ‚طµط©: ظ„ظˆ ظپظٹظ‡ طھط§ط±ظٹط® ظˆظ…ظپظٹط´ ظ‚ظٹظ…ط©
            if date_str and val <= 0:
                errors.append(
                    ('ظ‚ظٹظ…ط© ط§ظ„ط¯ظپط¹ط© ط±ظ‚ظ… ' + str(i+1) + ' ظ†ط§ظ‚طµط©') if is_ar else ('Value for installment ' + str(i+1) + ' is missing')
                )
            
            if date_str:
                try:
                    payment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                except Exception:
                    errors.append(
                        ('طھط§ط±ظٹط® ط؛ظٹط± طµط­ظٹط­ ظ„ظ„ط¯ظپط¹ط© ط±ظ‚ظ… ' + str(i+1)) if is_ar else ('Invalid date for installment ' + str(i+1))
                    )
                else:
                    if payment_date < today:
                        errors.append(
                            ('طھط§ط±ظٹط® ط§ظ„ط¯ظپط¹ط© ط±ظ‚ظ… ' + str(i+1) + ' ظ„ط§ ظٹظ…ظƒظ† ط£ظ† ظٹظƒظˆظ† ظ‚ط¨ظ„ ط§ظ„ظٹظˆظ…') if is_ar else ('Date for installment ' + str(i+1) + ' cannot be before today')
                        )
                    if date_str in dates_used:
                        errors.append(
                            'طھط§ط±ظٹط® ظ…ظƒط±ط± â€” ظ„ط§ ظٹظ…ظƒظ† طھظƒط±ط§ط± ظ†ظپط³ ط§ظ„طھط§ط±ظٹط® ظ„ط£ظƒط«ط± ظ…ظ† ط¯ظپط¹ط©' if is_ar else 'Duplicate date â€” each installment must have a different date'
                        )
                    dates_used.append(date_str)
                    # ط¯ظپط¹ط© ظ„ط§ط­ظ‚ط© ظ„ط§ طھظƒظˆظ† ط£ظ‚ط¯ظ… ظ…ظ† ط£ظٹ ط¯ظپط¹ط© ط³ط§ط¨ظ‚ط©
                    if last_date is not None and payment_date < last_date:
                        errors.append(
                            ('طھط§ط±ظٹط® ط§ظ„ط¯ظپط¹ط© ط±ظ‚ظ… ' + str(i+1) + ' ظ„ط§ ظٹظ…ظƒظ† ط£ظ† ظٹظƒظˆظ† ظ‚ط¨ظ„ طھط§ط±ظٹط® ط§ظ„ط¯ظپط¹ط© ط§ظ„ط³ط§ط¨ظ‚ط©') if is_ar else ('Date for installment ' + str(i+1) + ' cannot be before previous installment')
                        )
                    if payment_date is not None:
                        last_date = payment_date
            
            total_value += val
        
        if self.payment_method == 'percentage':
            if round(total_value, 2) != 100:
                errors.append(
                    ('ط¥ط¬ظ…ط§ظ„ظٹ ط§ظ„ظ†ط³ط¨ = ' + str(total_value) + '% â€" ظٹط¬ط¨ ط£ظ† ظٹظƒظˆظ† 100%') if is_ar else ('Total = ' + str(total_value) + '% â€" must be 100%')
                )
        else:
            if round(total_value, 0) != round(total_price, 0):
                diff = abs(total_price - total_value)
                errors.append(
                    ('ط¥ط¬ظ…ط§ظ„ظٹ ط§ظ„ظ…ط¨ط§ظ„ط؛ (' + "{:,.0f}".format(total_value) + ') ظ„ط§ ظٹط³ط§ظˆظٹ ظ‚ظٹظ…ط© ط§ظ„ط¹ظ‚ط¯ (' + "{:,.0f}".format(total_price) + ') â€" ط§ظ„ظپط±ظ‚ ' + "{:,.0f}".format(diff)) if is_ar else ('Total (' + "{:,.0f}".format(total_value) + ') does not match contract (' + "{:,.0f}".format(total_price) + ') â€" diff ' + "{:,.0f}".format(diff))
                )
        
        if errors:
            full_msg = '\n'.join(errors) if is_ar else '\n'.join(errors)
            return False, full_msg
        return True, ''

    def save_payments(self):
        """ظٹط­ظپط¸ ط¨ظٹط§ظ†ط§طھ ط§ظ„ط¯ظپط¹ط§طھ ظˆظٹط±ط¬ط¹ {success: True} ط£ظˆ {success: False, message: '...'}."""
        is_ar = self.current_lang == 'ar'
        try:
            if not self.current_data:
                msg = ('ط§ظ„ظ†ط§ظ‚طµ: ظ…ظ† ظپط¶ظ„ظƒ ط§ط®طھط± ط¹ط±ط¶ط§ظ‹ ط£ظˆ ط¹ظ‚ط¯ط§ظ‹ ط£ظˆظ„ط§ظ‹ ط«ظ… ط§ظپطھط­ ط¥ط¯ط§ط±ط© ط§ظ„ط¯ظپط¹ط§طھ ظ…ط±ط© ط£ط®ط±ظ‰.'
                       if is_ar else 'Missing: Please select a quotation or contract first, then open Manage Payments again.')
                return {'success': False, 'message': msg}
            # طھط§ط±ظٹط® ط§ظ„طھط³ظ„ظٹظ… ط؛ظٹط± ظ…ط·ظ„ظˆط¨ ط¹ظ†ط¯ ط­ظپط¸ ط§ظ„ط¯ظپط¹ط§طھ ظ…ظ† ط§ظ„ظ†ط§ظپط°ط© â€” ظ…ط·ظ„ظˆط¨ ظپظ‚ط· ط¹ظ†ط¯ Save Contract
            valid, validation_msg = self.validate_payments()
            if not valid:
                return {'success': False, 'message': validation_msg or ('ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ط§ظ„ط¨ظٹط§ظ†ط§طھ ظپط´ظ„' if is_ar else 'Validation failed')}

            value_inputs = anvil.js.window.document.querySelectorAll('.payment-value')
            date_inputs = anvil.js.window.document.querySelectorAll('.payment-date')
            if not value_inputs or not date_inputs:
                msg = ('ط§ظ„ظ†ط§ظ‚طµ: ظ„ظ… ظٹطھظ… ط§ظ„ط¹ط«ظˆط± ط¹ظ„ظ‰ ط­ظ‚ظˆظ„ ط§ظ„ط¯ظپط¹ط§طھ. ط£ط¹ط¯ ظپطھط­ ظ†ط§ظپط°ط© ط¥ط¯ط§ط±ط© ط§ظ„ط¯ظپط¹ط§طھ.'
                       if is_ar else 'Missing: Payment fields not found. Please reopen Manage Payments.')
                return {'success': False, 'message': msg}

            self.payment_data = []
            price_str = str(self.current_data.get('total_price', 0) or 0).replace(',', '').replace('طŒ', '')
            try:
                total_price = float(price_str) if price_str else 0
            except Exception:
                total_price = 0

            labels_ar = ['ظ…ظ‚ط¯ظ… طھط¹ط§ظ‚ط¯', 'ط§ظ„ط¯ظپط¹ط© ط§ظ„ط«ط§ظ†ظٹط©', 'ط§ظ„ط¯ظپط¹ط© ط§ظ„ط«ط§ظ„ط«ط©', 'ط§ظ„ط¯ظپط¹ط© ط§ظ„ط±ط§ط¨ط¹ط©',
                         'ط§ظ„ط¯ظپط¹ط© ط§ظ„ط®ط§ظ…ط³ط©', 'ط§ظ„ط¯ظپط¹ط© ط§ظ„ط³ط§ط¯ط³ط©', 'ط§ظ„ط¯ظپط¹ط© ط§ظ„ط³ط§ط¨ط¹ط©', 'ط§ظ„ط¯ظپط¹ط© ط§ظ„ط«ط§ظ…ظ†ط©',
                         'ط§ظ„ط¯ظپط¹ط© ط§ظ„طھط§ط³ط¹ط©', 'ط§ظ„ط¯ظپط¹ط© ط§ظ„ط¹ط§ط´ط±ط©', 'ط§ظ„ط¯ظپط¹ط© ط§ظ„ط­ط§ط¯ظٹط© ط¹ط´ط±', 'ط§ظ„ط¯ظپط¹ط© ط§ظ„ط«ط§ظ†ظٹط© ط¹ط´ط±']
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
                        'label_ar': labels_ar[i] if i < len(labels_ar) else ('ط§ظ„ط¯ظپط¹ط© ' + str(i+1)),
                        'label_en': labels_en[i] if i < len(labels_en) else ('Installment ' + str(i+1)),
                        'value': val,
                        'percentage': percentage,
                        'amount': amount,
                        'date': date_val,
                        'method': self.payment_method
                    })

            self.close_payment_modal()
            Notification('طھظ… ط­ظپط¸ ط§ظ„ط¯ظپط¹ط§طھ' if is_ar else 'Payments saved', style='success').show()

            if self.current_data:
                self.render_template()
            return {'success': True}
        except Exception as e:
            err_msg = str(e) if e else ('ط®ط·ط£ ط؛ظٹط± ظ…طھظˆظ‚ط¹' if is_ar else 'Unexpected error')
            return {'success': False, 'message': ('ط®ط·ط£ ط¹ظ†ط¯ ط§ظ„ط­ظپط¸: ' + err_msg) if is_ar else ('Error while saving: ' + err_msg)}

    def get_suppliers_list(self):
        """Get suppliers list for the supplier dropdown in contract form."""
        try:
            auth = anvil.js.window.sessionStorage.getItem('auth_token') or ''
            return anvil.server.call('get_suppliers_list_simple', auth)
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def load_available_inventory(self):
        """Load available (in_stock) inventory items for the inventory picker dropdown."""
        try:
            auth = anvil.js.window.sessionStorage.getItem('auth_token') or ''
            result = anvil.server.call('get_available_inventory_for_contract', auth)
            if result and result.get('success'):
                sel = anvil.js.window.document.getElementById('contractInventorySelect')
                if sel:
                    opts = '<option value="">-- Select Machine --</option>'
                    for item in (result.get('data') or []):
                        item_id = _h(item.get('id', ''))
                        desc = _h(item.get('description', ''))
                        code = _h(item.get('machine_code', ''))
                        cost = item.get('total_cost', 0) or 0
                        label = str(code) + ' - ' + str(desc) + ' (Cost: ' + "{:,.0f}".format(cost) + ' EGP)'
                        opts += '<option value="' + str(item_id) + '" data-cost="' + str(cost) + '">' + str(label) + '</option>'
                    sel.innerHTML = opts
        except Exception as e:
            logger.debug("Error loading inventory: %s", e)

    def save_contract(self):
        if not self.current_data:
            self._show_msg('Please select a quotation first')
            return

        if not self.payment_data:
            is_ar = self.current_lang == 'ar'
            self._show_msg('ظ…ظ† ظپط¶ظ„ظƒ ط£ط¯ط®ظ„ ط¨ظٹط§ظ†ط§طھ ط§ظ„ط¯ظپط¹ط§طھ ط£ظˆظ„ط§ظ‹' if is_ar else 'Please enter payment data first')
            return
        ok, msg_ar, msg_en = self._validate_delivery_date()
        if not ok:
            self._show_msg(msg_ar if self.current_lang == 'ar' else msg_en)
            return

        delivery_input = anvil.js.window.document.getElementById('deliveryDateInput')
        delivery_date = str(delivery_input.value) if delivery_input else ''

        # ط¨ظٹط§ظ†ط§طھ ط§ظ„ط¹ط±ط¶ ظ…ظ† get_quotation_pdf_data طھط³طھط®ط¯ظ… client_company, client_phone, client_address
        # ظˆظ€ company ظپظٹ current_data ظ‚ط¯ طھظƒظˆظ† ظ‚ط§ظ…ظˆط³ ط¥ط¹ط¯ط§ط¯ط§طھ ظˆظ„ظٹط³طھ ط§ط³ظ… ط§ظ„ط´ط±ظƒط©
        company_val = self.current_data.get('client_company') or ''
        if not company_val and isinstance(self.current_data.get('company'), str):
            company_val = self.current_data.get('company', '')
        phone_val = self.current_data.get('client_phone') or self.current_data.get('phone') or ''
        address_val = self.current_data.get('client_address') or self.current_data.get('address') or ''
        country_val = self.current_data.get('country') or ''
        q_num = self.current_data.get('quotation_number')
        if q_num is not None and q_num != '':
            try:
                q_num = int(q_num)
            except (TypeError, ValueError):
                pass

        # Determine pricing mode and collect relevant data
        pricing_mode = str(self.current_data.get('pricing_mode', '') or '')
        is_ar = self.current_lang == 'ar'

        supplier_id = ''
        currency = 'USD'
        inventory_item_id = ''

        if pricing_mode == 'New Order':
            # New Order: require supplier selection
            try:
                supplier_el = anvil.js.window.document.getElementById('contractSupplierSelect')
                if supplier_el:
                    supplier_id = str(supplier_el.value or '')
                currency_el = anvil.js.window.document.getElementById('contractCurrencySelect')
                if currency_el:
                    currency = str(currency_el.value or 'USD')
            except Exception:
                pass
            if not supplier_id:
                self._show_msg(
                    'ظ…ظ† ظپط¶ظ„ظƒ ط§ط®طھط± ط§ظ„ظ…ظˆط±ط¯ (Supplier) ط£ظˆظ„ط§ظ‹ ظ„ط£ظ† ظ†ظˆط¹ ط§ظ„ط³ط¹ط± "ط·ظ„ط¨ ط¬ط¯ظٹط¯"'
                    if is_ar else
                    'Please select a Supplier first â€” pricing mode is "New Order"'
                )
                return
        elif pricing_mode == 'In Stock':
            # In Stock: require inventory selection
            try:
                inv_el = anvil.js.window.document.getElementById('contractInventorySelect')
                if inv_el:
                    inventory_item_id = str(inv_el.value or '')
            except Exception:
                pass
            if not inventory_item_id:
                self._show_msg(
                    'ظ…ظ† ظپط¶ظ„ظƒ ط§ط®طھط± ط§ظ„ظ…ط§ظƒظٹظ†ط© ظ…ظ† ط§ظ„ظ…ط®ط²ظˆظ† ط£ظˆظ„ط§ظ‹ ظ„ط£ظ† ظ†ظˆط¹ ط§ظ„ط³ط¹ط± "ظ…ظ† ط§ظ„ظ…ط®ط²ظˆظ†"'
                    if is_ar else
                    'Please select a machine from Inventory â€” pricing mode is "In Stock"'
                )
                return

        contract_data = {
            'quotation_number': q_num,
            'client_name': self.current_data.get('client_name', ''),
            'company': str(company_val),
            'phone': str(phone_val),
            'country': str(country_val),
            'address': str(address_val),
            'model': str(self.current_data.get('model', '')),
            'colors_count': str(self.current_data.get('colors_count', '')),
            'machine_width': str(self.current_data.get('machine_width', '')),
            'material': str(self.current_data.get('material', '')),
            'winder_type': str(self.current_data.get('winder', '')),
            'price_mode': pricing_mode,
            'total_price': self.current_data.get('total_price') or self.current_data.get('total_price_raw', 0),
            'payment_method': self.payment_method,
            'num_payments': len(self.payment_data),
            'payments': self.payment_data,
            'delivery_date': delivery_date,
            'language': self.current_lang,
            # New Order fields
            'supplier_id': supplier_id if supplier_id else None,
            'currency': currency,
            # In Stock fields
            'inventory_item_id': inventory_item_id if inventory_item_id else None,
            # FOB data from quotation (for New Order auto-invoice)
            'fob_cost_usd': self.current_data.get('fob_cost_usd', ''),
            'fob_with_cylinders_usd': self.current_data.get('fob_with_cylinders_usd', ''),
            'exchange_rate': self.current_data.get('exchange_rate', 0),
        }
        
        try:
            anvil.js.window.showLoadingOverlay()
        except Exception:
            pass
        try:
            user_email = anvil.js.window.sessionStorage.getItem('user_email') or 'system'
            auth = anvil.js.window.sessionStorage.getItem('auth_token') or user_email
            result = anvil.server.call('save_contract', contract_data, user_email, auth)
            if result and result.get('success'):
                self.display_contract_number = result.get('contract_number')
                if self.current_data:
                    self.render_template()
                # Build success message with accounting details
                acct_msg = ''
                if result.get('purchase_invoice_number'):
                    inv_num = result['purchase_invoice_number']
                    acct_msg = (' | ظپط§طھظˆط±ط© ط´ط±ط§ط،: ' + str(inv_num)) if is_ar else (' | Purchase Invoice: ' + str(inv_num))
                elif result.get('inventory_sold'):
                    acct_msg = ' | طھظ… ط±ط¨ط· ط§ظ„ظ…ط§ظƒظٹظ†ط© ظ…ظ† ط§ظ„ظ…ط®ط²ظˆظ† ظˆطھط³ط¬ظٹظ„ ط§ظ„ط¨ظٹط¹' if is_ar else ' | Inventory item sold & linked'
                base_msg = 'طھظ… ط­ظپط¸ ط§ظ„ط¹ظ‚ط¯ ط¨ظ†ط¬ط§ط­' if is_ar else 'Contract saved'
                Notification(base_msg + acct_msg, style='success').show()
                # Show accounting warning if applicable
                if result.get('accounting_warning'):
                    self._show_msg(result['accounting_warning'], 'warning')
            elif result and result.get('already_exists'):
                # ط±ط¨ط· ط§ظ„ط±ط³ط§ظ„ط© ط¨ظ„ط؛ط© ط§ظ„ظ†ظ…ظˆط°ط¬ (ط²ط± ط§ظ„ظ„ط؛ط© ظپظٹ ط§ظ„ط¹ظ‚ط¯)
                is_ar = self.current_lang == 'ar'
                msg = result.get('message') if is_ar else result.get('message_en', result.get('message', ''))
                self._show_msg(msg or ('ط§ظ„ط¹ظ‚ط¯ ظ„ظ‡ط°ط§ ط§ظ„ط¹ط±ط¶ طھظ… ط¥ظ†ط´ط§ط¤ظ‡ ظ…ط³ط¨ظ‚ط§ظ‹.' if is_ar else 'This contract for this quotation was already created before.'))
            else:
                err_msg = result.get('message', 'Unknown error') if result else 'Server returned empty response'
                self._show_msg(err_msg)
        except Exception as e:
            detail = str(e)
            is_ar = self.current_lang == 'ar'
            if is_ar:
                msg = 'ط§ظ„ظ…ط´ظƒظ„ط©: ظپط´ظ„ ط­ظپط¸ ط§ظ„ط¹ظ‚ط¯. طھظپط§طµظٹظ„: ' + str(detail)
            else:
                msg = 'Save failed. Details: ' + str(detail)
            self._show_msg(msg)
        finally:
            try:
                anvil.js.window.hideLoadingOverlay()
            except Exception:
                pass

    def delete_contract(self):
        """ط­ط°ظپ ط§ظ„ط¹ظ‚ط¯ ظˆط¨ظٹظ†ط§طھظ‡ ط¨ط§ظ„ظƒط§ظ…ظ„ ظ…ظ† ط§ظ„ط¬ط¯ظˆظ„ (ظٹطھط·ظ„ط¨ طµظ„ط§ط­ظٹط© delete)"""
        if not self.current_data:
            is_ar = self.current_lang == 'ar'
            self._show_msg('ط§ط®طھط± ط¹ط±ط¶ط§ظ‹ ط£ظˆظ„ط§ظ‹' if is_ar else 'Please select a quotation first')
            return
        q_num = self.current_data.get('quotation_number')
        try:
            q_num = int(q_num) if q_num not in (None, '') else None
        except (TypeError, ValueError):
            q_num = None
        if q_num is None:
            is_ar = self.current_lang == 'ar'
            self._show_msg('ط±ظ‚ظ… ط§ظ„ط¹ط±ط¶ ط؛ظٹط± طµط§ظ„ط­' if is_ar else 'Invalid quotation number')
            return
        try:
            auth = anvil.js.window.sessionStorage.getItem('auth_token') or None
            result = anvil.server.call('delete_contract', q_num, auth)
            is_ar = self.current_lang == 'ar'
            if result and result.get('success'):
                self.current_data = None
                self.payment_data = []
                self.display_contract_number = None
                empty_state = anvil.js.window.document.getElementById('emptyState')
                template_content = anvil.js.window.document.getElementById('templateContent')
                if empty_state:
                    empty_state.style.display = 'block'
                if template_content:
                    template_content.style.display = 'none'
                self.load_quotations_list()
                msg = result.get('message') if is_ar else result.get('message_en', result.get('message', ''))
                self._show_msg(msg or ('طھظ… ط­ط°ظپ ط§ظ„ط¹ظ‚ط¯ ظˆط¨ظٹظ†ط§طھظ‡ ط¨ط§ظ„ظƒط§ظ…ظ„' if is_ar else 'Contract and all its data have been deleted'), typ='success')
            else:
                err = result.get('message') if is_ar else result.get('message_en', result.get('message', '')) if result else 'Unknown error'
                self._show_msg(err)
        except Exception as e:
            is_ar = self.current_lang == 'ar'
            self._show_msg(('ظپط´ظ„ ط§ظ„ط­ط°ظپ: ' + str(e)) if is_ar else ('Delete failed: ' + str(e)))

    # ==================== RENDER TEMPLATE (Same as Quotation) ====================
    def render_template(self):
        """Render the contract template - SAME as quotation but with 'Contract' title"""
        if not self.current_data:
            return

        # Hide empty state, show template
        empty_state = anvil.js.window.document.getElementById('emptyState')
        template_content = anvil.js.window.document.getElementById('templateContent')
        if empty_state:
            empty_state.style.display = 'none'
        if template_content:
            template_content.style.display = 'block'

        data = self.current_data
        c = data.get('company', {})
        is_ar = (self.current_lang == 'ar')

        # Get machine details
        model = str(data.get('model', '')).upper()
        machine_type_str = str(data.get('machine_type', '') or data.get('model', '')).upper()
        material = str(data.get('material', '')).upper()
        plc_value = str(data.get('plc', '')).upper()
        machine_type_base = data.get('machine_type', '') or data.get('model', '')
        machine_type_display = ('Flexo Stack With ' + str(machine_type_base)) if not is_ar else ('ظپظ„ظٹظƒط³ظˆ ط³طھط§ظƒ ظ…ط¹ ' + str(machine_type_base))

        # Winder type
        def get_winder_type():
            unwind_options = []
            rewind_options = []
            if str(data.get('pneumatic_unwind', '')).upper() in ['YES', 'TRUE', '1']:
                unwind_options.append('Pneumatic Unwind' if not is_ar else 'ظپظƒ ظ‡ظˆط§ط¦ظٹ')
            if str(data.get('hydraulic_station_unwind', '')).upper() in ['YES', 'TRUE', '1']:
                unwind_options.append('Hydraulic Station Unwind' if not is_ar else 'ظپظƒ ظ‡ظٹط¯ط±ظˆظ„ظٹظƒ')
            if str(data.get('pneumatic_rewind', '')).upper() in ['YES', 'TRUE', '1']:
                rewind_options.append('Pneumatic Rewind' if not is_ar else 'ظ„ظپ ظ‡ظˆط§ط¦ظٹ')
            if str(data.get('surface_rewind', '')).upper() in ['YES', 'TRUE', '1']:
                rewind_options.append('Surface Rewind' if not is_ar else 'ظ„ظپ ط³ط·ط­ظٹ')
            if not unwind_options and not rewind_options:
                return 'Central' if not is_ar else 'ظ…ط±ظƒط²ظٹ'
            parts = []
            if unwind_options:
                parts.append(', '.join(unwind_options))
            if rewind_options:
                parts.append(', '.join(rewind_options))
            return ' / '.join(parts)

        winder_type_display = get_winder_type()
        q_num = data.get('quotation_number', '')

        # ط±ظ‚ظ… ط§ظ„ط¹ظ‚ط¯: C - ط±ظ‚ظ… ط§ظ„ظƒظˆطھظٹط´ظ† / ظ…طھط³ظ„ط³ظ„ (ظ…ظ† ط¬ط¯ظˆظ„ CONTRACTS) - ط§ظ„ط³ظ†ط©
        contract_display = getattr(self, 'display_contract_number', None) or data.get('contract_number')
        year = date.today().year
        if not contract_display and q_num:
            serial = getattr(self, 'preview_contract_serial', None) or 2
            contract_display = 'C - ' + str(q_num) + ' / ' + str(serial) + ' - ' + str(year)
        contract_display = contract_display or (('C - ' + str(q_num) + ' / ' + str(getattr(self, 'preview_contract_serial', None) or 2) + ' - ' + str(year)) if q_num else "")
        # طھط­ظˆظٹظ„ ط§ظ„طھظ†ط³ظٹظ‚ ط§ظ„ظ‚ط¯ظٹظ… C-8 ط¥ظ„ظ‰ ط§ظ„طھظ†ط³ظٹظ‚ ط§ظ„ط¬ط¯ظٹط¯ (ط§ظ„ظ…طھط³ظ„ط³ظ„ ظ…ظ† ط§ظ„ط¬ط¯ظˆظ„ ط£ظˆ 2)
        if contract_display and re.match(r'^C-\d+$', str(contract_display).strip()):
            old_num = str(contract_display).strip().replace('C-', '')
            serial = getattr(self, 'preview_contract_serial', None) or 2
            contract_display = 'C - ' + str(old_num) + ' / ' + str(serial) + ' - ' + str(year)

        # ==================== PAGE 1 ====================
        html = '<div class="template-page ' + ('' if is_ar else 'ltr') + '">'

        # Header
        html += '<div class="header">'
        html += '<div class="header-right">'
        html += '<div class="location-date">' + str(_h(c.get("quotation_location_ar" if is_ar else "quotation_location_en", ""))) + ' / ' + str(_h(data.get("quotation_date_ar" if is_ar else "quotation_date_en", ""))) + '</div>'
        html += '<div class="address">' + str(_h(c.get("company_address_ar" if is_ar else "company_address_en", ""))) + '</div>'
        html += '<div class="contact">' + str(_h(data.get("sales_rep_phone", ""))) + '</div>'
        html += '<div class="contact">' + str(_h(data.get("sales_rep_email", ""))) + '</div>'
        html += '</div>'
        html += '<div class="header-left">'
        html += '<img src="_/theme/helwan_logo.png" class="logo" alt="Logo">'
        html += '<div class="company-name">' + str(_h(c.get("company_name_ar" if is_ar else "company_name_en", ""))) + '</div>'
        html += '<div class="website">' + str(_h(c.get("company_website", ""))) + '</div>'
        html += '</div>'
        html += '</div>'

        # Contract Info (ط±ظ‚ظ… ط§ظ„ط¹ظ‚ط¯ ط¨ط§ظ„طھظ†ط³ظٹظ‚: C - ط±ظ‚ظ… ط§ظ„ظƒظˆطھظٹط´ظ† / ظ…طھط³ظ„ط³ظ„ - ط§ظ„ط³ظ†ط©)
        html += '<div class="quotation-info">'
        html += '<div class="quotation-number">' + ('ط¹ظ‚ط¯ ط±ظ‚ظ…' if is_ar else 'Contract No.:') + ' <span>' + str(_h(contract_display)) + '</span></div>'
        client_name = data.get("client_name", "") or ""
        company = data.get("client_company", "") or ""
        client_display = (str(client_name) + ' - ' + str(company)).strip(" - ") if company else client_name
        html += '<div class="client-info">' + ('ط§ظ„ط³ط§ط¯ط© - ط´ط±ظƒط© /' if is_ar else 'To: / Company:') + ' <span>' + str(_h(client_display)) + '</span></div>'
        html += '<div class="greeting">' + ('طھط­ظٹط© ط·ظٹط¨ط© ظˆط¨ط¹ط¯طŒ' if is_ar else 'Dear Sir/Madam,') + '</div>'
        intro = 'طھظ… ط§ظ„ط§طھظپط§ظ‚ ط¨ظٹظ† ط§ظ„ط·ط±ظپظٹظ† ط¹ظ„ظ‰ طھظˆط±ظٹط¯ ظ…ط§ظƒظٹظ†ط© ط§ظ„ط·ط¨ط§ط¹ط© ط§ظ„طھط§ظ„ظٹط© ط·ط¨ظ‚ط§ظ‹ ظ„ظ„ظ…ظˆط§طµظپط§طھ ط§ظ„ظ…ظˆط¶ط­ط© ط£ط¯ظ†ط§ظ‡:' if is_ar else 'Both parties have agreed to supply the following printing machine according to the specifications detailed below:'
        html += '<div class="intro-text">' + str(intro) + '</div>'
        html += '</div>'

        # Machine Details (Same as Quotation)
        html += '<div class="section-title">' + ('طھظپط§طµظٹظ„ ط§ظ„ظ…ط§ظƒظٹظ†ط© :' if is_ar else 'Machine Details') + '</div>'
        html += '<table class="details-table">'
        
        if is_ar:
            html += '<tr><th>ظ†ظˆط¹ ط§ظ„ظ…ط§ظƒظٹظ†ط© :</th><td>' + str(machine_type_display) + '</td></tr>'
            html += '<tr><th>ط§ظ„ظ…ظˆط¯ظٹظ„ :</th><td>' + str(data.get("model", "")) + '</td></tr>'
            html += '<tr><th>ط¨ظ„ط¯ ط§ظ„ظ…ظ†ط´ط£ :</th><td>' + str(c.get("country_origin_ar", "")) + '</td></tr>'
            html += '<tr><th>ط¹ط¯ط¯ ط§ظ„ط£ظ„ظˆط§ظ† :</th><td>' + str(data.get("colors_count", "")) + '</td></tr>'
            html += '<tr><th>ط§ظ„ظˆظ†ط¯ط± :</th><td>' + str(data.get("winder", "")) + '</td></tr>'
            html += '<tr><th>ظ†ظˆط¹ ط§ظ„ظˆظ†ط¯ط± :</th><td>' + str(winder_type_display) + '</td></tr>'
            html += '<tr><th>ط¹ط±ط¶ ط§ظ„ظ…ط§ظƒظٹظ†ط© :</th><td>' + str(data.get("machine_width", "")) + ' ط³ظ…</td></tr>'
        else:
            html += '<tr><th>Machine Type:</th><td>' + str(machine_type_display) + '</td></tr>'
            html += '<tr><th>Model:</th><td>' + str(data.get("model", "")) + '</td></tr>'
            html += '<tr><th>Country of Origin:</th><td>' + str(c.get("country_origin_en", "")) + '</td></tr>'
            html += '<tr><th>Number of Colors:</th><td>' + str(data.get("colors_count", "")) + '</td></tr>'
            html += '<tr><th>Winder:</th><td>' + str(data.get("winder", "")) + '</td></tr>'
            html += '<tr><th>Winder Type:</th><td>' + str(winder_type_display) + '</td></tr>'
            html += '<tr><th>Machine Width:</th><td>' + str(data.get("machine_width", "")) + ' CM</td></tr>'
        html += '</table>'

        # ==================== 17 SPECIFICATIONS (Same as Quotation - FULL VERSION) ====================
        html += '<div class="section-title">' + ('ط§ظ„ظ…ظˆط§طµظپط§طھ ط§ظ„ظپظ†ظٹط©:' if is_ar else 'Technical Specifications:') + '</div>'
        html += '<ol class="specs-list" style="font-size: 14px; line-height: 1.8; padding-right: 18px; padding-left: 18px; white-space: normal; word-break: break-word;">'

        # Helper function to determine Belt/Gear drive for item 13
        def get_drive_type():
            is_metal_anilox = 'METAL' in machine_type_str
            is_nonwoven = 'NONWOVEN' in material
            # Belt drive if: Ceramic anilox OR NONWOVEN material
            # Gear drive if: Metal anilox AND NOT NONWOVEN
            if is_metal_anilox and not is_nonwoven:
                return ('ظ†ظ‚ظ„ ط§ظ„ط­ط±ظƒظ‡ ظ…ظ† ط§ظ„ظ…ظˆطھظˆط± ط§ظ„ط±ط¦ظٹط³ظٹ ظ„ط£ط¬ط²ط§ط، ط§ظ„ظ…ط§ظƒظٹظ†ط© ط¹ظ† ط·ط±ظٹظ‚ ط§ظ„طھط±ظˆط³' if is_ar else 'Gear drive',
                        'ظ†ظ‚ظ„ ط§ظ„ط­ط±ظƒظ‡ ظ…ظ† ط§ظ„ظ…ظˆطھظˆط± ط§ظ„ط±ط¦ظٹط³ظٹ ط¥ظ„ظ‰ ظ…ظƒظˆظ†ط§طھ ط§ظ„ظ…ط§ظƒظٹظ†ط© ط¹ط¨ط± ط§ظ„طھط±ظˆط³ ظ„ط¶ظ…ط§ظ† ط¹ظ…ط± ط£ط·ظˆظ„طŒ طھظ‚ظ„ظٹظ„ ط§ظ„ط£ط¹ط·ط§ظ„طŒ ظˆطھظ…ظƒظٹظ† ط§ظ„طھط´ط؛ظٹظ„ ط¨ط³ط±ط¹ط© ط¹ط§ظ„ظٹط© ظˆظ‡ط¯ظˆط، ظ…ط¹ طھطµظ…ظٹظ… ط؛ظٹط± ظ…ط¹ظ‚ط¯' if is_ar else 'Power transmission from the main motor to machine components via Gear drive to ensure longer service life, reduce breakdowns, and enable high-speed, quiet operation with a non-complex gear design')
            else:
                return ('ظ†ظ‚ظ„ ط§ظ„ط­ط±ظƒظ‡ ظ…ظ† ط§ظ„ظ…ظˆطھظˆط± ط§ظ„ط±ط¦ظٹط³ظٹ ظ„ط£ط¬ط²ط§ط، ط§ظ„ظ…ط§ظƒظٹظ†ط© ط¹ظ† ط·ط±ظٹظ‚ ط§ظ„ط³ظٹظˆط±' if is_ar else 'Belt drive',
                        'ظ†ظ‚ظ„ ط§ظ„ط­ط±ظƒظ‡ ظ…ظ† ط§ظ„ظ…ظˆطھظˆط± ط§ظ„ط±ط¦ظٹط³ظٹ ط¥ظ„ظ‰ ظ…ظƒظˆظ†ط§طھ ط§ظ„ظ…ط§ظƒظٹظ†ط© ط¹ط¨ط± ط§ظ„ط³ظٹظˆط± ظ„ط¶ظ…ط§ظ† ط¹ظ…ط± ط£ط·ظˆظ„طŒ طھظ‚ظ„ظٹظ„ ط§ظ„ط£ط¹ط·ط§ظ„طŒ ظˆطھظ…ظƒظٹظ† ط§ظ„طھط´ط؛ظٹظ„ ط¨ط³ط±ط¹ط© ط¹ط§ظ„ظٹط© ظˆظ‡ط¯ظˆط، ظ…ط¹ طھطµظ…ظٹظ… ط؛ظٹط± ظ…ط¹ظ‚ط¯' if is_ar else 'Power transmission from the main motor to machine components via Belt drive to ensure longer service life, reduce breakdowns, and enable high-speed, quiet operation with a non-complex gear design')

        # Helper function for item 7 (color registration)
        def get_color_registration():
            is_plc_yes = plc_value in ['YES', 'TRUE', '1', 'ظ†ط¹ظ…']
            if is_plc_yes:
                return ('ط¶ط¨ط· طھط³ط¬ظٹظ„ ط§ظ„ط£ظ„ظˆط§ظ† ط§ظ„ط£ظپظ‚ظٹ ظˆط§ظ„ط±ط£ط³ظٹ ط£ظˆطھظˆظ…ط§طھظٹظƒظٹط§ظ‹ ط£ط«ظ†ط§ط، ط§ظ„طھط´ط؛ظٹظ„' if is_ar else 'Automatically horizontal and vertical color registration adjustment during operation')
            else:
                return ('ط¶ط¨ط· طھط³ط¬ظٹظ„ ط§ظ„ط£ظ„ظˆط§ظ† ط§ظ„ط£ظپظ‚ظٹ ظˆط§ظ„ط±ط£ط³ظٹ ظٹط¯ظˆظٹط§ظ‹ ط£ط«ظ†ط§ط، ط§ظ„طھط´ط؛ظٹظ„' if is_ar else 'Manual horizontal and vertical color registration adjustment during operation')

        drive_type, drive_desc = get_drive_type()
        color_reg = get_color_registration()

        # 17 Specifications - FULL VERSION (same as Quotation)
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
            "ظ‡ظٹظƒظ„ ظ…ظ† ط§ظ„ط­ط¯ظٹط¯ ط§ظ„ط²ظ‡ط± ط§ظ„ط«ظ‚ظٹظ„طŒ ط«ط§ط¨طھ ظˆظ…ظ‚ط§ظˆظ… ظ„ظ„ط§ظ‡طھط²ط§ط²ط§طھ",
            "ظˆط­ط¯ط§طھ طھط­ظƒظ… ط£ظˆطھظˆظ…ط§طھظٹظƒظٹط© ظپظٹ ط´ط¯ ط§ظ„ط®ط§ظ…ط© ظ…ظ†ط§ط³ط¨ط© ظ„ط£ظˆط²ط§ظ† ظˆط³ظ…ط§ظƒط§طھ ظˆظ…ط±ظˆظ†ط§طھ ظ…ط®طھظ„ظپط©طŒ ظ…ط¹ ط®ظٹط§ط± ط§ظ„ط¶ط¨ط· ط§ظ„ظٹط¯ظˆظٹ",
            "ظˆط­ط¯ط§طھ طھظˆط¬ظٹظ‡ ط§ظ„ط®ط§ظ…ط© (ط§ظ„ظ…طھط£ط±ط¬ط­ط©) ظ„ط¶ظ…ط§ظ† ط¯ظ‚ط© طھظˆط³ظٹط· ط§ظ„ط·ط¨ط§ط¹ط© ط¹ظ„ظ‰ ط§ظ„ط®ط§ظ…ط© ظˆط¥ط¹ط§ط¯ط© ظ„ظپ ط³ظ„ط³ط© ظ„ظ„ظ…ط§ط¯ط© ط§ظ„ظ…ط·ط¨ظˆط¹ط©",
            "ط§ظ„ط£ط³ط·ظˆط§ظ†ط§طھ ظ…ط¹ط§ظ„ط¬ط© ط¨ط§ظ„ظ„ظٹط²ط± ظ„ظ„طھط´ط؛ظٹظ„ ط§ظ„ط´ط§ظ‚ ظˆط¥ط·ط§ظ„ط© ط¹ظ…ط± ط§ظ„ط®ط¯ظ…ط©",
            "ظ…ط³طھط´ط¹ط±ط§طھ ط¥ظٹظ‚ط§ظپ ط£ظˆطھظˆظ…ط§طھظٹظƒظٹ ظ„ظ„ظ…ط§ظƒظٹظ†ط© ظپظٹ ط­ط§ظ„ط© ط§ظ†ظ‚ط·ط§ط¹ ط§ظ„ظپظٹظ„ظ… ط£ظˆ ظ†ظپط§ط¯ ط§ظ„ط®ط§ظ…ط©",
            "ط¶ط؛ط· ط£ط³ط·ظˆط§ظ†ط© ط§ظ„ط·ط¨ط§ط¹ط© ظٹطھظ… ط¹ط¨ط± ظ†ط¸ط§ظ… ط§ظ„ط²ظٹطھ ط§ظ„ظ‡ظٹط¯ط±ظˆظ„ظٹظƒظٹ ظ„طھط¬ظ†ط¨ ظ…ط´ط§ظƒظ„ ط§ظ„ط¶ط؛ط· ط§ظ„ظ‡ظˆط§ط¦ظٹ ظˆطھظ‚ظ„ظٹظ„ ط§ط³طھظ‡ظ„ط§ظƒ ط§ظ„ظƒظ‡ط±ط¨ط§ط، ط§ظ„ظ†ط§طھط¬ ط¹ظ† طھط´ط؛ظٹظ„ ط¶ط§ط؛ط· ط§ظ„ظ‡ظˆط§ط، ط§ظ„ظ…طھظƒط±ط±",
            get_color_registration(),
            "ط±ط§ظپط¹ط§طھ ط¹ظ„ظˆظٹظ‡ ظ…ط¯ظ…ط¬ط© ظ„طھط³ظ‡ظٹظ„ طھط­ظ…ظٹظ„ ظˆطھظپط±ظٹط؛ ط§ظ„ط±ظˆظ„ط§طھ ظˆط£ط³ط·ظˆط§ظ†ط§طھ ط§ظ„ط·ط¨ط§ط¹ط©طŒ ظ…ظ…ط§ ظٹظˆظپط± ط§ظ„ظˆظ‚طھ ظˆط§ظ„ط¬ظ‡ط¯ ظˆط§ظ„ط¹ظ…ط§ظ„ط©",
            "ظ…ظ†ط§ط³ط¨ط© ظ„ط£ط­ط¨ط§ط± ط§ظ„ظ…ط°ظٹط¨ط§طھ ظˆط§ظ„ط£ط­ط¨ط§ط± ط§ظ„ظ…ط§ط¦ظٹط©",
            "ط¥ظ†ظپط±طھط±ط§طھ ط¯ظ„طھط§ (طھط§ظٹظˆط§ظ†ظٹ)",
            "ط¥ظ†ط°ط§ط± ط£ظ…ط§ظ† ظ‚ط¨ظ„ ط¨ط¯ط، طھط´ط؛ظٹظ„ ط§ظ„ظ…ط§ظƒظٹظ†ط© ظ„ظ…ظ†ط¹ ط§ظ„ط¥طµط§ط¨ط§طھ",
            "ظˆط­ط¯ط§طھ طھط¬ظپظٹظپ ط¨ط§ظ„ظ‡ظˆط§ط، ط§ظ„ط³ط§ط®ظ† ظ…ط¹ ظ…ط³ط§ط± ط®ط§ظ…ط© ظ…ظ…طھط¯ ظ„ط¶ظ…ط§ظ† ط¬ظپط§ظپ ط§ظ„ط­ط¨ط± ط§ظ„ظƒط§ظ…ظ„طŒ ط¨ط§ظ„ط¥ط¶ط§ظپط© ط¥ظ„ظ‰ ظˆط­ط¯ط§طھ طھط¬ظپظٹظپ ط¨ظٹظ† ط§ظ„ط£ظ„ظˆط§ظ†",
            get_drive_type()[1],
            "ظ…ط¶ط®ط§طھ طھط´ط­ظٹظ… ظ…ط¯ظ…ط¬ط© ظ„ط¶ظ…ط§ظ† طھظˆط²ظٹط¹ ظ…طھظˆط§ط²ظ† ظ„ظ„ط²ظٹطھ ط¹ظ„ظ‰ ط¬ظ…ظٹط¹ ط§ظ„ظ…ظƒظˆظ†ط§طھطŒ طھط´ط؛ظٹظ„ ط³ظ„ط³طŒ ظˆط­ظ…ط§ظٹط© ط¬ظ…ظٹط¹ ط§ظ„ط£ط¬ط²ط§ط، ط§ظ„ظ…طھط­ط±ظƒط©",
            "ظ…ظˆط§طھظٹط± ط¥ط¹ط§ط¯ط© ظ„ظپ ظ…ظ†ظپطµظ„ط© ط¨طھط­ظƒظ… ظ…ط³طھظ‚ظ„ ظ„ظ„ط³ظ…ط§ط­ ط¨ط§ظ„طھط´ط؛ظٹظ„ ظ…ط¹ ظ…ط±ظˆظ†ط§طھ ظˆط³ظ…ط§ظƒط§طھ ظ…ط®طھظ„ظپط© ظ„ظ„ط®ط§ظ…ط§طھ",
            "ط£ط³ط·ظˆط§ظ†ط§طھ ظپظƒ/ظ„ظپ ط¨ط´ط§ظپطھ ظ‡ظˆط§ط¦ظٹطŒ ط¨ط§ظ„ط¥ط¶ط§ظپط© ط¥ظ„ظ‰ ط´ط§ظپطھ ظ…ظٹظƒط§ظ†ظٹظƒظٹ ط¥ط¶ط§ظپظٹ ظ„طھظ…ظƒظٹظ† ط§ظ„طھط´ط؛ظٹظ„ ظ…ط¹ ط£ظٹ ط­ط¬ظ… ظƒظˆط±",
            "ط¥ظ…ظƒط§ظ†ظٹط© ط§ظ„ط·ط¨ط§ط¹ط© ط¹ظ„ظ‰ ط§ظ„ظˆط¬ظ‡ظٹظ†"
        ]

        specs = specs_ar if is_ar else specs_en
        for i, spec in enumerate(specs, 1):
            html += '<li>' + str(spec) + '</li>'

        html += '</ol>'
        html += '</div>'  # End Page 1

        # ==================== PAGE 2 - Technical Table (Same as Quotation) ====================
        html += '<div class="template-page page-break-before ' + ('' if is_ar else 'ltr') + '">'

        # Header (repeated)
        html += '<div class="header">'
        html += '<div class="header-right">'
        html += '<div class="location-date">' + str(_h(c.get("quotation_location_ar" if is_ar else "quotation_location_en", ""))) + ' / ' + str(_h(data.get("quotation_date_ar" if is_ar else "quotation_date_en", ""))) + '</div>'
        html += '<div class="address">' + str(_h(c.get("company_address_ar" if is_ar else "company_address_en", ""))) + '</div>'
        html += '<div class="contact">' + str(_h(data.get("sales_rep_phone", ""))) + '</div>'
        html += '<div class="contact">' + str(_h(data.get("sales_rep_email", ""))) + '</div>'
        html += '</div>'
        html += '<div class="header-left">'
        html += '<img src="_/theme/helwan_logo.png" class="logo" alt="Logo">'
        html += '<div class="company-name">' + str(_h(c.get("company_name_ar" if is_ar else "company_name_en", ""))) + '</div>'
        html += '<div class="website">' + str(_h(c.get("company_website", ""))) + '</div>'
        html += '</div>'
        html += '</div>'

        html += '<div class="section-title">' + ('ط¬ط¯ظˆظ„ ط§ظ„ظ…ظˆط§طµظپط§طھ ط§ظ„ظپظ†ظٹط©:' if is_ar else 'General Specifications:') + '</div>'

        # Calculate table values
        winder_type = str(data.get('winder', '')).upper()
        is_double_winder = 'DOUBLE' in winder_type
        colors_count = int(data.get('colors_count', 0) or 0)
        machine_width = float(data.get('machine_width', 0) or 0)
        is_metal_anilox = 'METAL' in machine_type_str
        is_nonwoven = 'NONWOVEN' in material
        is_belt_drive = not (is_metal_anilox and not is_nonwoven)

        # Get settings values
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
        dryer_capacity = c.get('dryer_capacity', '2.2kw air blower أ— 2 units')
        main_motor_power = c.get('main_motor_power', '5 HP')

        # Helper: convert English digits to Arabic digits
        def to_ar(val):
            ar_digits = {'0': 'ظ ', '1': 'ظ،', '2': 'ظ¢', '3': 'ظ£', '4': 'ظ¤', '5': 'ظ¥', '6': 'ظ¦', '7': 'ظ§', '8': 'ظ¨', '9': 'ظ©'}
            return ''.join(ar_digits.get(ch, ch) for ch in str(val))

        # Calculate values - Number of Colors format (same as Quotation)
        if colors_count == 8:
            colors_display = "8+0, 7+1, 6+2, 5+3, 4+4 reverse printing" if not is_ar else (str(to_ar('8+0')) + 'طŒ ' + str(to_ar('7+1')) + 'طŒ ' + str(to_ar('6+2')) + 'طŒ ' + str(to_ar('5+3')) + 'طŒ ' + str(to_ar('4+4')) + ' ط·ط¨ط§ط¹ط© ط¹ظƒط³ظٹط©')
        elif colors_count == 6:
            colors_display = "6+0, 5+1, 4+2, 3+3 reverse printing" if not is_ar else (str(to_ar('6+0')) + 'طŒ ' + str(to_ar('5+1')) + 'طŒ ' + str(to_ar('4+2')) + 'طŒ ' + str(to_ar('3+3')) + ' ط·ط¨ط§ط¹ط© ط¹ظƒط³ظٹط©')
        elif colors_count == 4:
            colors_display = "4+0, 3+1, 2+2 reverse printing" if not is_ar else (str(to_ar('4+0')) + 'طŒ ' + str(to_ar('3+1')) + 'طŒ ' + str(to_ar('2+2')) + ' ط·ط¨ط§ط¹ط© ط¹ظƒط³ظٹط©')
        else:
            colors_display = str(colors_count) if not is_ar else to_ar(colors_count)

        tension_units = 4 if is_double_winder else 2
        brake_system = 4 if is_double_winder else 2
        brake_power = double_winder_brake_power if is_double_winder else single_winder_brake_power
        web_guiding = 2 if is_double_winder else 1
        max_film_width = int(machine_width * 10 + 50)
        max_print_width = int(machine_width * 10 - 40)
        print_length = belt_print_length if is_belt_drive else gear_print_length
        max_roll_diameter = double_winder_roll_dia if is_double_winder else single_winder_roll_dia
        anilox_display = ("Metal Anilox" if not is_ar else "ط§ظ†ظٹظ„ظˆظƒط³ ظ…ط¹ط¯ظ†ظٹ") if is_metal_anilox else ("Ceramic Anilox" if not is_ar else "ط§ظ†ظٹظ„ظˆظƒط³ ط³ظٹط±ط§ظ…ظٹظƒ")
        max_machine_speed = belt_max_machine_speed if is_belt_drive else gear_max_machine_speed
        max_print_speed = belt_max_print_speed if is_belt_drive else gear_max_print_speed
        drive_display = ("Belt Drive" if not is_ar else "ط³ظٹظˆط±") if is_belt_drive else ("Gear Drive" if not is_ar else "طھط±ظˆط³")

        def yes_no(field):
            val = str(data.get(field, '')).upper()
            if val in ['YES', 'TRUE', '1', 'ظ†ط¹ظ…']:
                return 'ظ†ط¹ظ…' if is_ar else 'Yes'
            return None  # Hide if No

        # Build specs table - using same dynamic logic as QuotationPrintForm
        def yes_no_value(field_name):
            val = str(data.get(field_name, '')).upper()
            if val in ['YES', 'TRUE', '1', 'ظ†ط¹ظ…']:
                return 'ظ†ط¹ظ…' if is_ar else 'Yes'
            return None

        def is_yes_value(field_name):
            val = str(data.get(field_name, '')).upper()
            return val in ['YES', 'TRUE', '1', 'ظ†ط¹ظ…']

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
                {'label_ar': 'ط§ظ„ظ…ظˆط¯ظٹظ„', 'label_en': 'Model', 'source': 'field', 'values': ['model'], 'active': True},
                {'label_ar': 'ط¹ط¯ط¯ ط§ظ„ط£ظ„ظˆط§ظ†', 'label_en': 'Number of Colors', 'source': 'field', 'values': ['colors_display'], 'active': True},
                {'label_ar': 'ط£ظˆط¬ظ‡ ط§ظ„ط·ط¨ط§ط¹ط©', 'label_en': 'Printing Sides', 'source': 'field', 'values': ['printing_sides'], 'active': True},
                {'label_ar': 'ظˆط­ط¯ط§طھ ط§ظ„طھط­ظƒظ… ظپظٹ ط§ظ„ط´ط¯', 'label_en': 'Tension Control Units', 'source': 'field', 'values': ['tension_units'], 'active': True},
                {'label_ar': 'ظ†ط¸ط§ظ… ط§ظ„ظپط±ط§ظ…ظ„', 'label_en': 'Brake System', 'source': 'field', 'values': ['brake_system'], 'active': True},
                {'label_ar': 'ظ‚ظˆط© ط§ظ„ظپط±ط§ظ…ظ„', 'label_en': 'Brake Power', 'source': 'field', 'values': ['brake_power'], 'active': True},
                {'label_ar': 'ظ†ط¸ط§ظ… طھظˆط¬ظٹظ‡ ط§ظ„ط®ط§ظ…ط© (ط§ظ„ظ†ظˆط¹ ط§ظ„ظ…طھط£ط±ط¬ط­)', 'label_en': 'Web Guiding System (Oscillating Type)', 'source': 'field', 'values': ['web_guiding'], 'active': True},
                {'label_ar': 'ط£ظ‚طµظ‰ ط¹ط±ط¶ ظ„ظ„ظپظٹظ„ظ…', 'label_en': 'Maximum Film Width', 'source': 'field', 'values': ['max_film_width'], 'active': True},
                {'label_ar': 'ط£ظ‚طµظ‰ ط¹ط±ط¶ ظ„ظ„ط·ط¨ط§ط¹ط©', 'label_en': 'Maximum Printing Width', 'source': 'field', 'values': ['max_print_width'], 'active': True},
                {'label_ar': 'ط§ظ„ط­ط¯ ط§ظ„ط£ط¯ظ†ظ‰ ظˆط§ظ„ط£ظ‚طµظ‰ ظ„ط·ظˆظ„ ط§ظ„ط·ط¨ط§ط¹ط©', 'label_en': 'Minimum and Maximum Printing Length', 'source': 'field', 'values': ['print_length'], 'active': True},
                {'label_ar': 'ط£ظ‚طµظ‰ ظ‚ط·ط± ظ„ظ„ط±ظˆظ„', 'label_en': 'Maximum Roll Diameter', 'source': 'field', 'values': ['max_roll_diameter'], 'active': True},
                {'label_ar': 'ظ†ظˆط¹ ط§ظ„ط£ظ†ظٹظ„ظˆظƒط³', 'label_en': 'Anilox Type', 'source': 'field', 'values': ['anilox_display'], 'active': True},
                {'label_ar': 'ط£ظ‚طµظ‰ ط³ط±ط¹ط© ظ„ظ„ظ…ط§ظƒظٹظ†ط©', 'label_en': 'Maximum Machine Speed', 'source': 'field', 'values': ['max_machine_speed'], 'active': True},
                {'label_ar': 'ط£ظ‚طµظ‰ ط³ط±ط¹ط© ظ„ظ„ط·ط¨ط§ط¹ط©', 'label_en': 'Maximum Printing Speed', 'source': 'field', 'values': ['max_print_speed'], 'active': True},
                {'label_ar': 'ظ‚ط¯ط±ط© ط§ظ„ظ…ط¬ظپظپ', 'label_en': 'Dryer Capacity', 'source': 'field', 'values': ['dryer_capacity'], 'active': True},
                {'label_ar': 'ط·ط±ظٹظ‚ط© ظ†ظ‚ظ„ ط§ظ„ظ‚ط¯ط±ط©', 'label_en': 'Power Transmission Method', 'source': 'field', 'values': ['drive_display'], 'active': True},
                {'label_ar': 'ظ‚ط¯ط±ط© ط§ظ„ظ…ظˆطھظˆط± ط§ظ„ط±ط¦ظٹط³ظٹ', 'label_en': 'Main Motor Power', 'source': 'field', 'values': ['main_motor_power'], 'active': True},
                {'label_ar': 'ط§ظ„ظپط­طµ ط¨ط§ظ„ظپظٹط¯ظٹظˆ', 'label_en': 'Video Inspection', 'source': 'yes_no', 'values': ['video_inspection'], 'active': True},
                {'label_ar': 'PLC', 'label_en': 'PLC', 'source': 'yes_no', 'values': ['plc'], 'active': True},
                {'label_ar': 'ط³ظ„ظٹطھط±', 'label_en': 'Slitter', 'source': 'yes_no', 'values': ['slitter'], 'active': True},
            ]

        def normalize_specs(raw):
            defaults = default_specs()
            
            # If raw is a valid list with proper structure, use it (supports reordering)
            if isinstance(raw, list) and len(raw) > 0:
                # Validate that the list has proper label structure
                first_item = raw[0] if raw else {}
                if first_item.get('label_en') or first_item.get('label_ar'):
                    specs = []
                    for spec in raw:
                        # Skip invalid items
                        if not spec.get('label_en') and not spec.get('label_ar'):
                            continue
                        specs.append({
                            'label_ar': spec.get('label_ar', ''),
                            'label_en': spec.get('label_en', ''),
                            'source': spec.get('source', 'field'),
                            'values': normalize_values(spec.get('values')),
                            'active': spec.get('active', True) is not False,
                            'condition_field': spec.get('condition_field', ''),
                            'condition_value': spec.get('condition_value', ''),
                            'then_value': spec.get('then_value', ''),
                            'else_value': spec.get('else_value', ''),
                        })
                    return specs if specs else defaults
                # Invalid structure, use defaults
                return defaults

            # If raw is a dict with tech_spec_N keys (old format)
            if isinstance(raw, dict) and len(raw) > 0:
                first_key = next(iter(raw.keys()), None)
                if first_key and first_key.startswith('tech_spec_'):
                    specs = []
                    for i, default in enumerate(defaults, 1):
                        saved = raw.get('tech_spec_' + str(i), {})
                        if isinstance(saved, dict):
                            specs.append({
                                'label_ar': saved.get('label_ar', default['label_ar']),
                                'label_en': saved.get('label_en', default['label_en']),
                                'source': saved.get('source', default['source']),
                                'values': normalize_values(saved.get('values') or saved.get('value_keys') or default['values']),
                                'active': saved.get('active', True) is not False,
                                'condition_field': saved.get('condition_field', ''),
                                'condition_value': saved.get('condition_value', ''),
                                'then_value': saved.get('then_value', ''),
                                'else_value': saved.get('else_value', ''),
                            })
                        else:
                            specs.append(default)
                    return specs
            
            # Default: return hardcoded defaults
            return defaults

        # Get tech_specs_settings from database
        tech_specs_settings = data.get('tech_specs_settings', None)
        specs_list = normalize_specs(tech_specs_settings)

        # Arabic brake power formatting
        def ar_brake_power(bp_str):
            import re
            parts = str(bp_str).split('+')
            ar_parts = []
            for part in parts:
                part = part.strip()
                m = re.match(r'(\d+)\s*pc\s*\((\d+)kg\)', part)
                if m:
                    ar_parts.append(str(to_ar(m.group(1))) + ' ظ‚ط·ط¹ط© (' + str(to_ar(m.group(2))) + ' ظƒط¬ظ…)')
                else:
                    ar_parts.append(to_ar(part))
            return ' + '.join(ar_parts)

        # Arabic dryer capacity formatting
        def ar_dryer(dc_str):
            import re
            m = re.match(r'([\d.]+)kw\s*air\s*blower\s*[أ—x]\s*(\d+)\s*units?', str(dc_str), re.IGNORECASE)
            if m:
                return str(to_ar(m.group(1))) + ' ظƒظٹظ„ظˆ ظˆط§طھ طھط¬ظپظٹظپ ظ‡ظˆط§ط¦ظٹ أ— ' + str(to_ar(m.group(2)))
            return to_ar(dc_str)

        # Arabic print length formatting
        def ar_print_length(pl_str):
            import re
            m = re.match(r'(\d+)\s*mm\s*-\s*(\d+)\s*mm', str(pl_str), re.IGNORECASE)
            if m:
                return str(to_ar(m.group(1))) + ' ظ…ظ… - ' + str(to_ar(m.group(2))) + ' ظ…ظ…'
            return to_ar(pl_str)

        if is_ar:
            value_map = {
                'model': data.get('model', '-'),
                'colors_display': colors_display,
                'printing_sides': to_ar('2'),
                'tension_units': str(to_ar(tension_units)) + ' ظ‚ط·ط¹ط©',
                'brake_system': str(to_ar(brake_system)) + ' ظ‚ط·ط¹ط©',
                'brake_power': ar_brake_power(brake_power),
                'web_guiding': str(to_ar(web_guiding)) + ' ظ‚ط·ط¹ط©',
                'max_film_width': str(to_ar(max_film_width)) + ' ظ…ظ…',
                'max_print_width': str(to_ar(max_print_width)) + ' ظ…ظ…',
                'print_length': ar_print_length(print_length),
                'max_roll_diameter': str(to_ar(max_roll_diameter)) + ' ظ…ظ…',
                'anilox_display': anilox_display,
                'max_machine_speed': str(to_ar(max_machine_speed)) + ' ظ…طھط± ظپظٹ ط§ظ„ط¯ظ‚ظٹظ‚ط©',
                'max_print_speed': str(to_ar(max_print_speed)) + ' ظ…طھط± ظپظٹ ط§ظ„ط¯ظ‚ظٹظ‚ط©',
                'dryer_capacity': ar_dryer(dryer_capacity),
                'drive_display': drive_display,
                'main_motor_power': str(to_ar(main_motor_power.replace('HP', '').replace('hp', '').strip())) + ' ط­طµط§ظ†',
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
                'max_film_width': str(max_film_width) + ' mm',
                'max_print_width': str(max_print_width) + ' mm',
                'print_length': print_length,
                'max_roll_diameter': str(max_roll_diameter) + ' mm',
                'anilox_display': anilox_display,
                'max_machine_speed': str(max_machine_speed) + ' m/min',
                'max_print_speed': str(max_print_speed) + ' m/min',
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
                value_text = 'ظ†ط¹ظ…' if is_ar else 'Yes'
            elif source == 'custom':
                condition_field = spec.get('condition_field', '')
                condition_value = str(spec.get('condition_value', '')).upper().strip()
                then_value = spec.get('then_value', '')
                else_value = spec.get('else_value', '')
                
                winder_type_val = str(data.get('winder', '')).upper()
                condition_map = {
                    'winder_type': winder_type_val,
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

            # DYNAMIC: Hide any row where value is "No" or "ظ„ط§" or empty
            value_upper = str(value_text).strip().upper()
            if value_upper in ['NO', 'ظ„ط§', 'N/A', '-', '']:
                continue

            val_style = ' style="text-align:right;"' if is_ar else ''
            html += '<tr><td class="row-num">' + str(row_num) + '</td><th>' + str(label) + '</th><td class="value"' + str(val_style) + '>' + str(value_text) + '</td></tr>'
            row_num += 1
        html += '</table>'

        # Cylinders - centered table
        cylinders = data.get('cylinders', [])
        html += '<div class="section-title">' + ('ط³ظ„ظ†ط¯ط±ط§طھ ط§ظ„ط·ط¨ط§ط¹ط© :' if is_ar else 'Printing Cylinders:') + '</div>'
        html += '<div style="display: flex; justify-content: center;">'
        html += '<table class="cylinders-table" style="width: 50%; margin: 0 auto;">'
        html += '<tr><th style="background:#f5f5f5; padding:8px; border:1px solid #ddd;">' + ('ظ…ظ‚ط§ط³' if is_ar else 'Size') + '</th><th style="background:#f5f5f5; padding:8px; border:1px solid #ddd;">' + ('ط¹ط¯ط¯' if is_ar else 'Count') + '</th></tr>'
        for i in range(12):
            if i < len(cylinders):
                cyl = cylinders[i]
                size = cyl.get("size", "")
                count = cyl.get("count", "")
                html += '<tr><td style="border: 1px solid #ddd; padding:6px; text-align:center;">' + str(size) + '</td><td style="border: 1px solid #ddd; padding:6px; text-align:center;">' + str(count) + '</td></tr>'
            else:
                html += '<tr><td style="border: none;"></td><td style="border: none;"></td></tr>'
        html += '</table>'
        html += '</div>'
        html += '</div>'  # End Page 2

        # ==================== PAGE 3 - Financial + Payments ====================
        html += '<div class="template-page page-break-before ' + ('' if is_ar else 'ltr') + '">'

        # Header (repeated)
        html += '<div class="header">'
        html += '<div class="header-right">'
        html += '<div class="location-date">' + str(_h(c.get("quotation_location_ar" if is_ar else "quotation_location_en", ""))) + ' / ' + str(_h(data.get("quotation_date_ar" if is_ar else "quotation_date_en", ""))) + '</div>'
        html += '<div class="address">' + str(_h(c.get("company_address_ar" if is_ar else "company_address_en", ""))) + '</div>'
        html += '<div class="contact">' + str(_h(data.get("sales_rep_phone", ""))) + '</div>'
        html += '<div class="contact">' + str(_h(data.get("sales_rep_email", ""))) + '</div>'
        html += '</div>'
        html += '<div class="header-left">'
        html += '<img src="_/theme/helwan_logo.png" class="logo" alt="Logo">'
        html += '<div class="company-name">' + str(_h(c.get("company_name_ar" if is_ar else "company_name_en", ""))) + '</div>'
        html += '<div class="website">' + str(_h(c.get("company_website", ""))) + '</div>'
        html += '</div>'
        html += '</div>'

        html += '<div class="section-title">' + ('ط§ظ„ظ‚ظٹظ…ط© ط§ظ„ظ…ط§ظ„ظٹط©:' if is_ar else 'Contract Value:') + '</div>'

        html += '<div class="financial-box">'
        total_price = data.get("total_price", "")
        html += '<div class="total-price">' + str(total_price) + ' ' + ('ط¬.ظ…' if is_ar else 'EGP') + '</div>'
        html += '</div>'

        # Payment Schedule
        if self.payment_data:
            html += '<div class="section-title">' + ('ط¬ط¯ظˆظ„ ط§ظ„ط¯ظپط¹ط§طھ:' if is_ar else 'Payment Schedule:') + '</div>'
            html += '<table class="payment-table" style="width:100%;">'
            html += '<tr style="background:#667eea;color:white;">'
            html += '<th style="padding:10px;color:white;">#</th>'
            html += '<th style="padding:10px;color:white;">' + ('ط§ظ„ط¨ظ†ط¯' if is_ar else 'Description') + '</th>'
            html += '<th style="padding:10px;color:white;">' + ('ط§ظ„ظ†ط³ط¨ط©' if is_ar else '%') + '</th>'
            html += '<th style="padding:10px;color:white;">' + ('ط§ظ„ظ…ط¨ظ„ط؛' if is_ar else 'Amount') + '</th>'
            html += '<th style="padding:10px;color:white;">' + ('ط§ظ„طھط§ط±ظٹط®' if is_ar else 'Date') + '</th>'
            html += '</tr>'
            
            currency = 'ط¬.ظ…' if is_ar else 'EGP'
            for i, p in enumerate(self.payment_data):
                label = p.get('label_ar' if is_ar else 'label_en', '')
                bg = '#f8f9fa' if i % 2 == 0 else 'white'
                html += '<tr style="background:' + str(bg) + ';">'
                html += '<td style="padding:8px;text-align:center;">' + str(i+1) + '</td>'
                html += '<td style="padding:8px;">' + str(label) + '</td>'
                html += '<td style="padding:8px;text-align:center;">' + "{:.1f}".format(p.get("percentage", 0)) + '%</td>'
                html += '<td style="padding:8px;text-align:center;">' + "{:,.0f}".format(p.get("amount", 0)) + ' ' + str(currency) + '</td>'
                html += '<td style="padding:8px;text-align:center;">' + str(p.get("date", "")) + '</td>'
                html += '</tr>'
            html += '</table>'

        # Delivery
        html += '<div class="info-grid">'
        html += '<div class="info-box">'
        html += '<h4>' + ('ط§ظ„طھط³ظ„ظٹظ… :' if is_ar else 'Delivery:') + '</h4>'
        html += '<p>' + ('ظ…ظƒط§ظ† ط§ظ„طھط³ظ„ظٹظ… :' if is_ar else 'Delivery location:') + ' <span class="highlight">' + str(data.get("delivery_location", "-")) + '</span></p>'
        delivery_time = self.delivery_date if self.delivery_date else data.get("expected_delivery_formatted", "-")
        html += '<p>' + ('طھط§ط±ظٹط® ط§ظ„طھط³ظ„ظٹظ… ط§ظ„ظ…طھظˆظ‚ط¹ :' if is_ar else 'Expected delivery:') + ' <span class="highlight">' + str(delivery_time) + '</span></p>'
        html += '</div>'

        html += '<div class="info-box">'
        html += '<h4>' + ('ط§ظ„ط¶ظ…ط§ظ†:' if is_ar else 'Warranty:') + '</h4>'
        warranty_text = ('ظٹط³ط±ظٹ ط§ظ„ط¶ظ…ط§ظ† ظ„ظ…ط¯ط© <strong>' + str(c.get("warranty_months", "12")) + '</strong> ط´ظ‡ط±') if is_ar else ('Warranty: <strong>' + str(c.get("warranty_months", "12")) + '</strong> months')
        html += '<p>' + str(warranty_text) + '</p>'
        support_text = 'ط¯ط¹ظ… ظپظ†ظٹ ظƒط§ظ…ظ„ ظ…ط¹ طھظˆط§ظپط± ظ‚ط·ط¹ ط§ظ„ط؛ظٹط§ط± ط¹ظ†ط¯ ط§ظ„ط·ظ„ط¨' if is_ar else 'Full technical support with spare parts availability upon request'
        html += '<p style="margin-top:8px; color:#555;">' + str(support_text) + '</p>'
        html += '</div>'
        html += '</div>'

        # Signatures
        html += '<div style="margin-top:40px;display:flex;justify-content:space-around;">'
        html += (
            '<div style="text-align:center;min-width:200px;">'
            '<div style="font-weight:bold;margin-bottom:10px;">' + ('ط§ظ„ط·ط±ظپ ط§ظ„ط£ظˆظ„' if is_ar else 'First Party') + '</div>'
            '<div>' + str(_h(c.get("company_name_ar" if is_ar else "company_name_en", ""))) + '</div>'
            '<div style="margin-top:60px;border-top:1px solid #333;padding-top:5px;">' + ('ط§ظ„طھظˆظ‚ظٹط¹' if is_ar else 'Signature') + '</div>'
            '</div>'
            '<div style="text-align:center;min-width:200px;">'
            '<div style="font-weight:bold;margin-bottom:10px;">' + ('ط§ظ„ط·ط±ظپ ط§ظ„ط«ط§ظ†ظٹ' if is_ar else 'Second Party') + '</div>'
            '<div>' + str(_h(client_display)) + '</div>'
            '<div style="margin-top:60px;border-top:1px solid #333;padding-top:5px;">' + ('ط§ظ„طھظˆظ‚ظٹط¹' if is_ar else 'Signature') + '</div>'
            '</div>'
        )
        html += '</div>'
        html += '</div>'  # End Page 3

        # Update content
        if template_content:
            template_content.innerHTML = html

    # ==================== Export Functions ====================
    def print_contract(self):
        if not self.current_data:
            self._show_msg('Please select a quotation first')
            return
        anvil.js.window.print()

    def export_pdf(self):
        if not self.current_data:
            self._show_msg('Please select a quotation first')
            return
        q_num = self.current_data.get('quotation_number', '')
        client = (self.current_data.get('client_name') or '').replace(' ', '_')
        # طھظ†ط¸ظٹظپ ط§ط³ظ… ط§ظ„ظ…ظ„ظپ: ط¥ط²ط§ظ„ط© ط£ظٹ ط£ط­ط±ظپ ط؛ظٹط± ط¢ظ…ظ†ط© ظ‚ط¨ظ„ ط¥ط¯ط®ط§ظ„ظ‡ ظپظٹ eval (ظ…ظ†ط¹ ط­ظ‚ظ† JS)
        safe_client = ''.join(c for c in client if c.isalnum() or c in ('_', '-'))[:80]
        safe_q = str(q_num).strip()[:20]
        filename = 'Contract_C-' + str(safe_q) + '_' + str(safe_client or 'contract') + '.pdf'
        js_code = """
        (async function() {
            const element = document.getElementById('templateContent');
            if (!element) { if (window.showNotification) window.showNotification('error', '', 'No content'); return; }

            function loadScript(url) {
                return new Promise((resolve, reject) => {
                    if (document.querySelector('script[src="' + url + '"]')) { resolve(); return; }
                    const script = document.createElement('script');
                    script.src = url;
                    script.onload = resolve;
                    script.onerror = reject;
                    document.head.appendChild(script);
                });
            }

            try {
                await loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js');
                await loadScript('https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js');

                // Force desktop rendering for PDF capture
                element.classList.add('pdf-export-mode');
                await new Promise(r => setTimeout(r, 100));

                const { jsPDF } = window.jspdf;
                const pdf = new jsPDF('p', 'mm', 'a4');
                const pages = element.querySelectorAll('.template-page');

                for (let i = 0; i < pages.length; i++) {
                    const canvas = await html2canvas(pages[i], {
                        scale: 2, useCORS: true, backgroundColor: '#ffffff'
                    });
                    const imgData = canvas.toDataURL('image/jpeg', 0.95);
                    const imgWidth = 210;
                    const imgHeight = (canvas.height * imgWidth) / canvas.width;
                    if (i > 0) pdf.addPage();
                    pdf.addImage(imgData, 'JPEG', 0, 0, imgWidth, imgHeight);
                }

                element.classList.remove('pdf-export-mode');
                pdf.save('""" + str(filename) + """');
            } catch (error) {
                element.classList.remove('pdf-export-mode');
                if (window.showNotification) window.showNotification('error', '', 'Error: ' + error.message);
            }
        })();
        """
        anvil.js.window.eval(js_code)

    def export_excel(self):
        if not self.current_data:
            self._show_msg('Please select a quotation first')
            return
        try:
            q_num = self.current_data.get('quotation_number', 0)
            auth = anvil.js.window.sessionStorage.getItem('auth_token') or None
            result = anvil.server.call('export_quotation_excel', q_num, auth)
            if result.get('success'):
                media = result.get('file')
                if media:
                    anvil.media.download(media)
            else:
                self._show_msg(result.get('message', 'Error'))
        except Exception as e:
            self._show_msg(str(e))

    # ==================== Server Calls ====================
    def load_quotation_for_print(self, quotation_number):
        try:
            user_email = anvil.js.window.sessionStorage.getItem('user_email') or ''
            auth_token = anvil.js.window.sessionStorage.getItem('auth_token') or None
            result = anvil.server.call('get_quotation_pdf_data', int(quotation_number), user_email, auth_token)
            return result
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def search_quotations_for_print(self, query=''):
        try:
            auth = anvil.js.window.sessionStorage.getItem('auth_token') or None
            result = anvil.server.call('get_quotations_list', query, False, auth)
            return result
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def get_all_settings(self):
        try:
            auth = anvil.js.window.sessionStorage.getItem('auth_token') or None
            result = anvil.server.call('get_all_settings', auth)
            return result
        except Exception as e:
            return {'success': False, 'message': str(e)}


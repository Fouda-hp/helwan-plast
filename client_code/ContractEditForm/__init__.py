"""
ContractEditForm - صفحة تعديل عقد قديم
======================================
- القائمة من جدول العقود فقط
- زر الحفظ = Update (تحديث نفس السطر، نفس السيريال)
- التحقق من تاريخ التسليم إجباري
"""
from ._anvil_designer import ContractEditFormTemplate
from ..ContractPrintForm import ContractPrintForm
from anvil import Notification
import anvil.js
import anvil.server


class ContractEditForm(ContractEditFormTemplate, ContractPrintForm):
    def __init__(self, **properties):
        ContractPrintForm.__init__(self, **properties)
        anvil.js.window.saveContract = self.update_contract
        anvil.js.window.deleteContract = self.delete_contract

    def init_page(self):
        saved_lang = anvil.js.window.localStorage.getItem('hp_language')
        if saved_lang in ['ar', 'en']:
            self.current_lang = saved_lang
            self.update_language_buttons()
        self.load_contracts_list()
        self._set_update_button_label()
        self._inject_delete_button()

    def _set_update_button_label(self):
        try:
            doc = anvil.js.window.document
            btn = doc.querySelector('button[onclick*="saveContract"]')
            if btn:
                btn.textContent = ('تحديث' if self.current_lang == 'ar' else 'Update')
        except Exception:
            pass

    def _get_auth_token(self):
        """نفس منطق التوكن في الأدمن: sessionStorage ثم localStorage مع نسخ للجلسة."""
        token = anvil.js.window.sessionStorage.getItem('auth_token')
        if not token:
            token = anvil.js.window.localStorage.getItem('auth_token')
            if token:
                try:
                    anvil.js.window.sessionStorage.setItem('auth_token', token)
                except Exception:
                    pass
        return token

    def load_quotations_list(self):
        self.load_contracts_list()

    def load_contracts_list(self):
        try:
            auth = self._get_auth_token()
            result = anvil.server.call('get_contracts_list', '', auth, 1, 500)
            if result and result.get('success'):
                self.all_contracts = result.get('data', [])
                self._populate_contracts_dropdown()
            else:
                self.all_contracts = []
                self._populate_contracts_dropdown()
        except Exception as e:
            self.all_contracts = []
            self._populate_contracts_dropdown()

    def _populate_contracts_dropdown(self):
        select = anvil.js.window.document.getElementById('quotationSelect')
        if not select:
            try:
                anvil.js.window._contractEditRetryPopulate = self._populate_contracts_dropdown
                anvil.js.window.eval("setTimeout(function(){ try { if (window._contractEditRetryPopulate) window._contractEditRetryPopulate(); } catch(e){} }, 150);")
            except Exception:
                pass
            return
        is_ar = self.current_lang == 'ar'
        select.innerHTML = '<option value="">-- ' + ('اختر عقداً' if is_ar else 'Select Contract') + ' --</option>'
        for c in self.all_contracts:
            cnum = (c.get('contract_number') or '').strip()
            qnum = c.get('quotation_number')
            client = (c.get('client_name') or '').strip()
            if not cnum and qnum is not None:
                cnum = 'C - ' + str(qnum) + ' / ? - ?'
            option_text = str(cnum) + ' - ' + str(client)
            select.innerHTML += '<option value="' + str(qnum) + '">' + str(option_text) + '</option>'

    def load_selected_quotation(self):
        self.load_selected_contract()

    def load_selected_contract(self):
        select = anvil.js.window.document.getElementById('quotationSelect')
        if not select or not select.value:
            return
        try:
            q_num = int(select.value)
        except (ValueError, TypeError):
            self._show_msg('Invalid selection')
            return
        auth = self._get_auth_token()
        contract_res = anvil.server.call('get_contract', q_num, auth)
        if not contract_res or not contract_res.get('success'):
            self._show_msg(contract_res.get('message', 'Contract not found') if contract_res else 'Error')
            return
        pdf_res = self.load_quotation_for_print(q_num)
        if not pdf_res or not pdf_res.get('success'):
            self._show_msg('Could not load quotation data')
            return
        contract_data = contract_res.get('data', {})
        pdf_data = pdf_res.get('data', {})
        pdf_data['quotation_number'] = q_num
        pdf_data['client_name'] = contract_data.get('client_name') or pdf_data.get('client_name', '')
        pdf_data['client_company'] = contract_data.get('company') or pdf_data.get('client_company', '')
        pdf_data['total_price'] = contract_data.get('total_price') or pdf_data.get('total_price', '')
        pdf_data['contract_number'] = contract_data.get('contract_number', '')
        self.current_data = pdf_data
        self.display_contract_number = contract_data.get('contract_number')
        self.payment_data = list(contract_data.get('payments', []))
        self.payment_method = (contract_data.get('payment_method') or 'percentage').strip() or 'percentage'
        num_payments_el = anvil.js.window.document.getElementById('numPayments')
        if num_payments_el and self.payment_data:
            num_payments_el.value = str(len(self.payment_data))
        radios = anvil.js.window.document.querySelectorAll('input[name="paymentMethod"]')
        for r in radios:
            if r and str(r.value) == self.payment_method:
                r.checked = True
                break
        delivery_el = anvil.js.window.document.getElementById('deliveryDateInput')
        if delivery_el:
            delivery_el.value = contract_data.get('delivery_date') or ''
        self.render_template()
        total_str = str(self.current_data.get('total_price', 0) or 0).replace(',', '').replace('،', '')
        try:
            total = float(total_str) if total_str else 0
        except Exception:
            total = 0
        total_el = anvil.js.window.document.getElementById('totalContractAmount')
        if total_el:
            total_el.textContent = "{:,.2f}".format(total)
        self.calculate_total_percentage()

    def update_contract(self):
        if not self.current_data:
            is_ar = self.current_lang == 'ar'
            self._show_msg('اختر عقداً أولاً' if is_ar else 'Please select a contract first')
            return
        if not self.payment_data:
            is_ar = self.current_lang == 'ar'
            self._show_msg('من فضلك أدخل بيانات الدفعات أولاً' if is_ar else 'Please enter payment data first')
            return
        ok, msg_ar, msg_en = self._validate_delivery_date()
        if not ok:
            self._show_msg(msg_ar if self.current_lang == 'ar' else msg_en)
            return
        delivery_input = anvil.js.window.document.getElementById('deliveryDateInput')
        delivery_date = str(delivery_input.value) if delivery_input else ''
        company_val = self.current_data.get('client_company') or ''
        if not company_val and isinstance(self.current_data.get('company'), str):
            company_val = self.current_data.get('company', '')
        phone_val = self.current_data.get('client_phone') or self.current_data.get('phone') or ''
        address_val = self.current_data.get('client_address') or self.current_data.get('address') or ''
        country_val = self.current_data.get('country') or ''
        q_num = self.current_data.get('quotation_number')
        try:
            q_num = int(q_num) if q_num not in (None, '') else None
        except (TypeError, ValueError):
            q_num = None
        if q_num is None:
            self._show_msg('Invalid quotation number')
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
            'price_mode': str(self.current_data.get('pricing_mode', '')),
            'total_price': self.current_data.get('total_price') or self.current_data.get('total_price_raw', 0),
            'payment_method': self.payment_method,
            'num_payments': len(self.payment_data),
            'payments': self.payment_data,
            'delivery_date': delivery_date,
            'language': self.current_lang
        }
        try:
            user_email = anvil.js.window.sessionStorage.getItem('user_email') or 'system'
            auth = anvil.js.window.sessionStorage.getItem('auth_token') or user_email
            result = anvil.server.call('update_contract', contract_data, user_email, auth)
            if result and result.get('success'):
                is_ar = self.current_lang == 'ar'
                self.display_contract_number = result.get('contract_number')
                if self.current_data:
                    self.render_template()
                Notification('تم تحديث العقد بنجاح' if is_ar else 'Contract updated', style='success').show()
            else:
                err = result.get('message', 'Unknown error') if result else 'Unknown error'
                self._show_msg(err)
        except Exception as e:
            is_ar = self.current_lang == 'ar'
            self._show_msg('فشل التحديث: ' + str(e) if is_ar else 'Update failed: ' + str(e))

    def _inject_delete_button(self):
        """Inject a Delete button next to Update button (admin-only on server)"""
        try:
            anvil.js.window.eval("""
            (function(){
                var updateBtn = document.querySelector('button[onclick*="saveContract"]');
                if (!updateBtn || document.getElementById('deleteContractBtn')) return;
                var delBtn = document.createElement('button');
                delBtn.id = 'deleteContractBtn';
                delBtn.type = 'button';
                delBtn.style.cssText = 'background:#c00000;color:#fff;border:none;padding:10px 24px;border-radius:8px;font-weight:bold;font-size:15px;cursor:pointer;margin-left:12px;margin-right:12px;';
                delBtn.textContent = (localStorage.getItem('hp_language') === 'ar') ? 'حذف العقد' : 'Delete Contract';
                delBtn.onclick = function(){
                    var lang = localStorage.getItem('hp_language') || 'en';
                    var msg = lang === 'ar' ? 'هل أنت متأكد من حذف هذا العقد وكل بياناته؟ لا يمكن التراجع!' : 'Are you sure you want to delete this contract and all its data? This cannot be undone!';
                    if (confirm(msg)) {
                        if (window.deleteContract) window.deleteContract();
                    }
                };
                updateBtn.parentNode.insertBefore(delBtn, updateBtn.nextSibling);
            })();
            """)
        except Exception:
            pass

    def delete_contract(self):
        """Delete the selected contract (admin-only, checked on server)"""
        if not self.current_data:
            is_ar = self.current_lang == 'ar'
            self._show_msg('اختر عقداً أولاً' if is_ar else 'Please select a contract first')
            return
        q_num = self.current_data.get('quotation_number')
        try:
            q_num = int(q_num) if q_num not in (None, '') else None
        except (TypeError, ValueError):
            q_num = None
        if q_num is None:
            self._show_msg('Invalid contract')
            return
        try:
            auth = self._get_auth_token()
            result = anvil.server.call('delete_contract', q_num, auth)
            is_ar = self.current_lang == 'ar'
            if result and result.get('success'):
                Notification(result.get('message', 'Deleted') if is_ar else result.get('message_en', 'Contract deleted'), style='success').show()
                self.current_data = None
                self.payment_data = []
                # Reload contracts list
                self.load_contracts_list()
                # Clear template display
                template_content = anvil.js.window.document.getElementById('templateContent')
                if template_content:
                    template_content.innerHTML = ''
                    template_content.style.display = 'none'
                empty_state = anvil.js.window.document.getElementById('emptyState')
                if empty_state:
                    empty_state.style.display = 'block'
            else:
                msg = result.get('message', 'Delete failed') if result else 'Delete failed'
                if 'permission' in msg.lower() or 'denied' in msg.lower():
                    msg = 'ارجع للأدمن' if is_ar else 'Contact admin for permission'
                self._show_msg(msg)
        except Exception as e:
            is_ar = self.current_lang == 'ar'
            self._show_msg('فشل الحذف: ' + str(e) if is_ar else 'Delete failed: ' + str(e))

    def filter_quotations(self):
        search_input = anvil.js.window.document.getElementById('searchInput')
        if not search_input:
            return
        query = str(search_input.value).lower().strip()
        if not query:
            self._populate_contracts_dropdown()
            return
        filtered = [c for c in self.all_contracts
                    if query in str(c.get('contract_number', '')).lower()
                    or query in str(c.get('client_name', '')).lower()]
        select = anvil.js.window.document.getElementById('quotationSelect')
        if not select:
            return
        is_ar = self.current_lang == 'ar'
        select.innerHTML = '<option value="">-- ' + ('اختر عقداً' if is_ar else 'Select Contract') + ' --</option>'
        for c in filtered:
            cnum = (c.get('contract_number') or '').strip()
            qnum = c.get('quotation_number')
            client = (c.get('client_name') or '').strip()
            option_text = str(cnum) + ' - ' + str(client)
            select.innerHTML += '<option value="' + str(qnum) + '">' + str(option_text) + '</option>'

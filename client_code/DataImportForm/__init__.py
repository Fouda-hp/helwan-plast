"""
DataImportForm - صفحة استيراد البيانات (للأدمن فقط)
===================================================
- استيراد بيانات العملاء من CSV/Excel
- استيراد بيانات العروض من CSV/Excel
- معاينة البيانات قبل الاستيراد
- تقرير الأخطاء والنتائج
"""

from ._anvil_designer import DataImportFormTemplate
from anvil import *
import anvil.server
import anvil.js
import json


class DataImportForm(DataImportFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # بيانات الاستيراد
        self.import_data = []
        self.import_type = 'clients'  # أو 'quotations'
        self.user_email = ''

        # الحصول على بريد المستخدم
        self._get_user_email()

    def _get_user_email(self):
        """الحصول على بريد المستخدم من الجلسة"""
        try:
            token = anvil.js.window.sessionStorage.getItem('auth_token')
            if token:
                result = anvil.server.call('validate_token', token)
                if result.get('valid'):
                    self.user_email = result['user']['email']
        except:
            pass

    # =========================================================
    # اختيار نوع الاستيراد
    # =========================================================
    def btn_clients_click(self, **event_args):
        """اختيار استيراد العملاء"""
        self.import_type = 'clients'
        self.btn_clients.role = 'primary'
        self.btn_quotations.role = 'secondary'
        self._update_template_info()

    def btn_quotations_click(self, **event_args):
        """اختيار استيراد العروض"""
        self.import_type = 'quotations'
        self.btn_clients.role = 'secondary'
        self.btn_quotations.role = 'primary'
        self._update_template_info()

    def _update_template_info(self):
        """تحديث معلومات القالب"""
        if self.import_type == 'clients':
            self.template_info.content = '''
            <div style="background:#e3f2fd;padding:15px;border-radius:8px;margin:10px 0;">
                <h4 style="margin:0 0 10px 0;">📋 Clients CSV Template</h4>
                <p style="margin:5px 0;font-size:13px;">Required columns:</p>
                <code style="display:block;background:#fff;padding:10px;border-radius:4px;font-size:12px;">
                Client Name, Company, Phone, Country, Address, Email, Sales Rep, Source
                </code>
                <p style="margin:10px 0 0 0;font-size:12px;color:#666;">
                * Client Code will be auto-generated if not provided<br>
                * Phone must be unique
                </p>
            </div>
            '''
        else:
            self.template_info.content = '''
            <div style="background:#f3e5f5;padding:15px;border-radius:8px;margin:10px 0;">
                <h4 style="margin:0 0 10px 0;">📊 Quotations CSV Template</h4>
                <p style="margin:5px 0;font-size:13px;">Required columns:</p>
                <code style="display:block;background:#fff;padding:10px;border-radius:4px;font-size:12px;">
                Client Code, Client Name, Model, Machine type, Number of colors, Machine width,
                Material, Winder, Given Price, Agreed Price
                </code>
                <p style="margin:10px 0 0 0;font-size:12px;color:#666;">
                * Quotation# will be auto-generated if not provided<br>
                * Client Code must exist in clients table
                </p>
            </div>
            '''

    # =========================================================
    # تحميل الملف
    # =========================================================
    def file_loader_change(self, file, **event_args):
        """معالجة الملف المحمل"""
        if not file:
            return

        try:
            # قراءة محتوى الملف
            content = file.get_bytes().decode('utf-8-sig')

            # تحليل CSV
            self.import_data = self._parse_csv(content)

            if not self.import_data:
                alert('No valid data found in file')
                return

            # عرض المعاينة
            self._show_preview()

            # تفعيل زر الاستيراد
            self.btn_import.enabled = True

            self.status_label.text = f'✅ Loaded {len(self.import_data)} rows'
            self.status_label.foreground = '#2e7d32'

        except Exception as e:
            alert(f'Error reading file: {str(e)}')
            self.status_label.text = f'❌ Error: {str(e)}'
            self.status_label.foreground = '#c62828'

    def _parse_csv(self, content):
        """تحليل محتوى CSV"""
        lines = content.strip().split('\n')
        if len(lines) < 2:
            return []

        # العناوين
        headers = [h.strip().strip('"') for h in lines[0].split(',')]

        data = []
        for line in lines[1:]:
            if not line.strip():
                continue

            # تحليل السطر (مع معالجة الفواصل داخل علامات الاقتباس)
            values = self._parse_csv_line(line)

            if len(values) >= len(headers):
                row = {}
                for i, h in enumerate(headers):
                    row[h] = values[i] if i < len(values) else ''
                data.append(row)

        return data

    def _parse_csv_line(self, line):
        """تحليل سطر CSV مع معالجة علامات الاقتباس"""
        values = []
        current = ''
        in_quotes = False

        for char in line:
            if char == '"':
                in_quotes = not in_quotes
            elif char == ',' and not in_quotes:
                values.append(current.strip().strip('"'))
                current = ''
            else:
                current += char

        values.append(current.strip().strip('"'))
        return values

    def _show_preview(self):
        """عرض معاينة البيانات"""
        if not self.import_data:
            self.preview_container.content = '<p>No data to preview</p>'
            return

        # عرض أول 5 صفوف
        preview_data = self.import_data[:5]
        headers = list(preview_data[0].keys())[:8]  # أول 8 أعمدة

        html = '''
        <style>
            .preview-table { width:100%; border-collapse:collapse; font-size:12px; }
            .preview-table th { background:#667eea; color:white; padding:8px; text-align:left; }
            .preview-table td { padding:6px 8px; border-bottom:1px solid #eee; }
        </style>
        <h4 style="margin:10px 0;">📋 Preview (first 5 rows)</h4>
        <div style="overflow-x:auto;">
        <table class="preview-table">
            <thead><tr>
        '''

        for h in headers:
            html += f'<th>{h}</th>'

        html += '</tr></thead><tbody>'

        for row in preview_data:
            html += '<tr>'
            for h in headers:
                val = str(row.get(h, ''))[:30]  # اقتصار على 30 حرف
                html += f'<td>{val}</td>'
            html += '</tr>'

        html += '</tbody></table></div>'
        html += f'<p style="color:#666;font-size:12px;margin-top:10px;">Total rows: {len(self.import_data)}</p>'

        self.preview_container.content = html

    # =========================================================
    # تنفيذ الاستيراد
    # =========================================================
    def btn_import_click(self, **event_args):
        """تنفيذ الاستيراد"""
        if not self.import_data:
            alert('No data to import')
            return

        # تأكيد
        if not confirm(f'Import {len(self.import_data)} rows to {self.import_type}?'):
            return

        try:
            self.status_label.text = '⏳ Importing...'
            self.btn_import.enabled = False

            # استدعاء دالة الاستيراد
            if self.import_type == 'clients':
                result = anvil.server.call(
                    'import_clients_data',
                    self.import_data,
                    self.user_email
                )
            else:
                result = anvil.server.call(
                    'import_quotations_data',
                    self.import_data,
                    self.user_email
                )

            if result.get('success'):
                imported = result.get('imported', 0)
                errors = result.get('errors', [])

                # عرض النتيجة
                self._show_import_result(imported, errors)

                self.status_label.text = f'✅ Imported {imported} rows'
                self.status_label.foreground = '#2e7d32'

            else:
                alert(f'Import failed: {result.get("message", "Unknown error")}')
                self.status_label.text = f'❌ {result.get("message", "Failed")}'
                self.status_label.foreground = '#c62828'

        except Exception as e:
            alert(f'Import error: {str(e)}')
            self.status_label.text = f'❌ Error: {str(e)}'
            self.status_label.foreground = '#c62828'

        finally:
            self.btn_import.enabled = True

    def _show_import_result(self, imported, errors):
        """عرض نتيجة الاستيراد"""
        html = f'''
        <div style="background:#e8f5e9;padding:15px;border-radius:8px;margin:10px 0;">
            <h4 style="margin:0;color:#2e7d32;">✅ Import Complete</h4>
            <p style="margin:10px 0;">Successfully imported: <strong>{imported}</strong> rows</p>
        '''

        if errors:
            html += f'''
            <div style="background:#fff;padding:10px;border-radius:4px;margin-top:10px;">
                <p style="margin:0 0 5px 0;color:#c62828;">⚠️ Errors ({len(errors)}):</p>
                <ul style="margin:0;padding-left:20px;font-size:12px;max-height:150px;overflow-y:auto;">
            '''
            for err in errors[:20]:  # أول 20 خطأ
                html += f'<li style="color:#c62828;">{err}</li>'

            if len(errors) > 20:
                html += f'<li>... and {len(errors) - 20} more errors</li>'

            html += '</ul></div>'

        html += '</div>'
        self.result_container.content = html

    # =========================================================
    # تنزيل القالب
    # =========================================================
    def btn_download_template_click(self, **event_args):
        """تنزيل قالب CSV"""
        if self.import_type == 'clients':
            headers = 'Client Code,Client Name,Company,Phone,Country,Address,Email,Sales Rep,Source'
            sample = ',John Doe,ABC Company,01234567890,Egypt,Cairo Address,john@email.com,Sales Person,Website'
            filename = 'clients_template.csv'
        else:
            headers = 'Client Code,Client Name,Model,Machine type,Number of colors,Machine width,Material,Winder,Given Price,Agreed Price,Notes'
            sample = '1,John Doe,SH4-600M/S,Metal anilox,4,60,PE,Single,100000,95000,Sample note'
            filename = 'quotations_template.csv'

        csv_content = f'{headers}\\n{sample}'

        anvil.js.window.eval(f'''
            var blob = new Blob(["{csv_content}"], {{type: 'text/csv;charset=utf-8;'}});
            var link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = '{filename}';
            link.click();
        ''')

    def btn_back_click(self, **event_args):
        """العودة"""
        from ..AdminPanel import AdminPanel
        open_form('AdminPanel')

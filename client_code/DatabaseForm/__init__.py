"""
DatabaseForm - صفحة عرض قاعدة البيانات (للقراءة فقط)
=====================================================
- عرض جميع الجداول (العملاء والعروض)
- تصدير البيانات إلى Excel/CSV
- للقراءة فقط - لا يمكن التعديل
"""

from ._anvil_designer import DatabaseFormTemplate
from anvil import *
import anvil.server
import anvil.js


class DatabaseForm(DatabaseFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # الجدول الحالي
        self.current_table = 'clients'
        self.current_page = 1
        self.per_page = 15
        self.total_pages = 1
        self.search_query = ''

        # تحميل البيانات
        self.load_data()

    # =========================================================
    # تحميل البيانات
    # =========================================================
    def load_data(self):
        """تحميل البيانات حسب الجدول المحدد"""
        try:
            if self.current_table == 'clients':
                result = anvil.server.call(
                    'get_all_clients',
                    page=self.current_page,
                    per_page=self.per_page,
                    search=self.search_query,
                    include_deleted=False
                )
            else:
                result = anvil.server.call(
                    'get_all_quotations',
                    page=self.current_page,
                    per_page=self.per_page,
                    search=self.search_query,
                    include_deleted=False
                )

            self.total_pages = result.get('total_pages', 1)
            self.update_table(result.get('data', []))
            self.update_pagination_info()

        except Exception as e:
            alert(f'Error loading data: {str(e)}')

    def update_table(self, data):
        """تحديث الجدول"""
        if self.current_table == 'clients':
            self._render_clients_table(data)
        else:
            self._render_quotations_table(data)

    def _render_clients_table(self, data):
        """عرض جدول العملاء"""
        html = '''
        <style>
            .db-table { width:100%; border-collapse:collapse; font-size:13px; }
            .db-table th { background:#667eea; color:white; padding:12px 8px; text-align:left; position:sticky; top:0; }
            .db-table td { padding:10px 8px; border-bottom:1px solid #eee; }
            .db-table tr:hover { background:#f5f5f5; }
            .db-table tr:nth-child(even) { background:#fafafa; }
        </style>
        <div style="max-height:400px; overflow-y:auto;">
        <table class="db-table">
            <thead>
                <tr>
                    <th>Code</th>
                    <th>Client Name</th>
                    <th>Company</th>
                    <th>Phone</th>
                    <th>Country</th>
                    <th>Email</th>
                    <th>Sales Rep</th>
                    <th>Source</th>
                </tr>
            </thead>
            <tbody>
        '''

        if not data:
            html += '<tr><td colspan="8" style="text-align:center;padding:40px;color:#666;">No clients found</td></tr>'
        else:
            for row in data:
                html += f'''
                <tr>
                    <td><strong>{row.get('Client Code', '')}</strong></td>
                    <td>{row.get('Client Name', '')}</td>
                    <td>{row.get('Company', '')}</td>
                    <td>{row.get('Phone', '')}</td>
                    <td>{row.get('Country', '')}</td>
                    <td>{row.get('Email', '')}</td>
                    <td>{row.get('Sales Rep', '')}</td>
                    <td>{row.get('Source', '')}</td>
                </tr>
                '''

        html += '</tbody></table></div>'
        self.table_container.content = html

    def _render_quotations_table(self, data):
        """عرض جدول العروض"""
        html = '''
        <style>
            .db-table { width:100%; border-collapse:collapse; font-size:13px; }
            .db-table th { background:#764ba2; color:white; padding:12px 8px; text-align:left; position:sticky; top:0; }
            .db-table td { padding:10px 8px; border-bottom:1px solid #eee; }
            .db-table tr:hover { background:#f5f5f5; }
            .db-table tr:nth-child(even) { background:#fafafa; }
            .price { color:#2e7d32; font-weight:bold; }
        </style>
        <div style="max-height:400px; overflow-y:auto;">
        <table class="db-table">
            <thead>
                <tr>
                    <th>Q#</th>
                    <th>Date</th>
                    <th>Client</th>
                    <th>Model</th>
                    <th>Colors</th>
                    <th>Width</th>
                    <th>Given Price</th>
                    <th>Agreed Price</th>
                </tr>
            </thead>
            <tbody>
        '''

        if not data:
            html += '<tr><td colspan="8" style="text-align:center;padding:40px;color:#666;">No quotations found</td></tr>'
        else:
            for row in data:
                given = row.get('Given Price') or 0
                agreed = row.get('Agreed Price') or 0
                html += f'''
                <tr>
                    <td><strong>{row.get('Quotation#', '')}</strong></td>
                    <td>{row.get('Date', '')}</td>
                    <td>{row.get('Client Name', '')}</td>
                    <td>{row.get('Model', '')}</td>
                    <td>{row.get('Number of colors', '')}</td>
                    <td>{row.get('Machine width', '')}</td>
                    <td class="price">{given:,.0f}</td>
                    <td class="price">{agreed:,.0f}</td>
                </tr>
                '''

        html += '</tbody></table></div>'
        self.table_container.content = html

    def update_pagination_info(self):
        """تحديث معلومات الترقيم"""
        self.page_info.text = f'Page {self.current_page} of {self.total_pages}'
        self.btn_prev.enabled = self.current_page > 1
        self.btn_next.enabled = self.current_page < self.total_pages

    # =========================================================
    # أحداث الأزرار
    # =========================================================
    def btn_clients_click(self, **event_args):
        """عرض جدول العملاء"""
        self.current_table = 'clients'
        self.current_page = 1
        self.search_query = ''
        self.search_input.text = ''
        self.btn_clients.role = 'primary'
        self.btn_quotations.role = 'secondary'
        self.load_data()

    def btn_quotations_click(self, **event_args):
        """عرض جدول العروض"""
        self.current_table = 'quotations'
        self.current_page = 1
        self.search_query = ''
        self.search_input.text = ''
        self.btn_clients.role = 'secondary'
        self.btn_quotations.role = 'primary'
        self.load_data()

    def btn_search_click(self, **event_args):
        """البحث"""
        self.search_query = self.search_input.text or ''
        self.current_page = 1
        self.load_data()

    def btn_prev_click(self, **event_args):
        """الصفحة السابقة"""
        if self.current_page > 1:
            self.current_page -= 1
            self.load_data()

    def btn_next_click(self, **event_args):
        """الصفحة التالية"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_data()

    def btn_export_click(self, **event_args):
        """تصدير البيانات"""
        try:
            if self.current_table == 'clients':
                data = anvil.server.call('export_clients_data', include_deleted=False)
                filename = 'clients_export.csv'
            else:
                data = anvil.server.call('export_quotations_data', include_deleted=False)
                filename = 'quotations_export.csv'

            if not data:
                alert('No data to export')
                return

            csv_content = self._convert_to_csv(data)

            # تحميل الملف
            anvil.js.window.eval(f'''
                var blob = new Blob([`{csv_content}`], {{type: 'text/csv;charset=utf-8;'}});
                var link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = '{filename}';
                link.click();
            ''')

            alert('Export completed!')

        except Exception as e:
            alert(f'Export error: {str(e)}')

    def btn_back_click(self, **event_args):
        """العودة"""
        from ..LauncherForm import LauncherForm
        open_form('LauncherForm')

    # =========================================================
    # دوال مساعدة
    # =========================================================
    def _convert_to_csv(self, data):
        """تحويل البيانات إلى CSV"""
        if not data:
            return ''

        headers = list(data[0].keys())
        csv_lines = [','.join(headers)]

        for row in data:
            values = []
            for h in headers:
                val = str(row.get(h, '') or '').replace('"', '""').replace('\n', ' ')
                values.append(f'"{val}"')
            csv_lines.append(','.join(values))

        return '\n'.join(csv_lines)

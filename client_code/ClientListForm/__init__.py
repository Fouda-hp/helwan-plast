"""
ClientListForm - صفحة عرض العملاء (للقراءة فقط)
=================================================
- عرض جميع العملاء مع البحث والترقيم
- تصدير البيانات إلى Excel/CSV
- للقراءة فقط - لا يمكن التعديل
"""

from ._anvil_designer import ClientListFormTemplate
from anvil import *
import anvil.server
import anvil.js


class ClientListForm(ClientListFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # متغيرات الصفحة
        self.current_page = 1
        self.per_page = 20
        self.total_pages = 1
        self.search_query = ''

        # تحميل البيانات عند فتح الصفحة
        self.load_clients()

    # =========================================================
    # تحميل البيانات
    # =========================================================
    def load_clients(self):
        """تحميل بيانات العملاء من السيرفر"""
        try:
            result = anvil.server.call(
                'get_all_clients',
                page=self.current_page,
                per_page=self.per_page,
                search=self.search_query,
                include_deleted=False
            )

            self.total_pages = result.get('total_pages', 1)
            self.update_table(result.get('data', []))
            self.update_pagination_info()

        except Exception as e:
            alert(f'Error loading clients: {str(e)}')

    def update_table(self, data):
        """تحديث جدول العملاء"""
        # إنشاء HTML للجدول
        html = '''
        <table class="data-table">
            <thead>
                <tr>
                    <th>Code</th>
                    <th>Client Name</th>
                    <th>Company</th>
                    <th>Phone</th>
                    <th>Country</th>
                    <th>Email</th>
                    <th>Sales Rep</th>
                </tr>
            </thead>
            <tbody>
        '''

        if not data:
            html += '<tr><td colspan="7" style="text-align:center;padding:30px;">No clients found</td></tr>'
        else:
            for row in data:
                html += f'''
                <tr>
                    <td>{row.get('Client Code', '')}</td>
                    <td>{row.get('Client Name', '')}</td>
                    <td>{row.get('Company', '')}</td>
                    <td>{row.get('Phone', '')}</td>
                    <td>{row.get('Country', '')}</td>
                    <td>{row.get('Email', '')}</td>
                    <td>{row.get('Sales Rep', '')}</td>
                </tr>
                '''

        html += '</tbody></table>'

        # تحديث العنصر
        self.table_container.content = html

    def update_pagination_info(self):
        """تحديث معلومات الترقيم"""
        self.page_info.text = f'Page {self.current_page} of {self.total_pages}'
        self.btn_prev.enabled = self.current_page > 1
        self.btn_next.enabled = self.current_page < self.total_pages

    # =========================================================
    # أحداث الأزرار
    # =========================================================
    def btn_search_click(self, **event_args):
        """البحث"""
        self.search_query = self.search_input.text or ''
        self.current_page = 1
        self.load_clients()

    def btn_prev_click(self, **event_args):
        """الصفحة السابقة"""
        if self.current_page > 1:
            self.current_page -= 1
            self.load_clients()

    def btn_next_click(self, **event_args):
        """الصفحة التالية"""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_clients()

    def btn_export_click(self, **event_args):
        """تصدير البيانات"""
        try:
            data = anvil.server.call('export_clients_data', include_deleted=False)

            if not data:
                alert('No data to export')
                return

            # تحويل إلى CSV
            csv_content = self._convert_to_csv(data)

            # تحميل الملف
            anvil.js.window.eval(f'''
                var blob = new Blob([`{csv_content}`], {{type: 'text/csv;charset=utf-8;'}});
                var link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = 'clients_export.csv';
                link.click();
            ''')

            alert('Export completed!')

        except Exception as e:
            alert(f'Export error: {str(e)}')

    def btn_back_click(self, **event_args):
        """العودة للصفحة الرئيسية"""
        from ..LauncherForm import LauncherForm
        open_form('LauncherForm')

    # =========================================================
    # دوال مساعدة
    # =========================================================
    def _convert_to_csv(self, data):
        """تحويل البيانات إلى CSV"""
        if not data:
            return ''

        # العناوين
        headers = list(data[0].keys())
        csv_lines = [','.join(headers)]

        # البيانات
        for row in data:
            values = []
            for h in headers:
                val = str(row.get(h, '') or '').replace('"', '""')
                values.append(f'"{val}"')
            csv_lines.append(','.join(values))

        return '\n'.join(csv_lines)

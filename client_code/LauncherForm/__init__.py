"""
LauncherForm - صفحة الإطلاق الرئيسية
====================================
- التوجيه حسب الـ hash
- روابط للصفحات المختلفة
"""

from ._anvil_designer import LauncherFormTemplate
from anvil import *
import anvil.google.auth, anvil.google.drive
from anvil.google.drive import app_files
import anvil.server
import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables
import anvil.js


class LauncherForm(LauncherFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # نفحص الـ hash مرة واحدة عند التحميل
        self.check_route()

        # نربط listener بطريقة صحيحة
        anvil.js.window.addEventListener("hashchange", self.on_hash_change)

    def on_hash_change(self, event):
        """معالجة تغيير الـ hash"""
        self.check_route()

    def check_route(self):
        """التحقق من المسار والتوجيه"""
        hash_val = anvil.js.window.location.hash

        if hash_val == "#calculator":
            open_form('CalculatorForm')
        elif hash_val == "#clients":
            open_form('ClientListForm')
        elif hash_val == "#database":
            open_form('DatabaseForm')
        elif hash_val == "#admin":
            open_form('AdminPanel')
        elif hash_val == "#import":
            open_form('DataImportForm')

    def form_show(self, **event_args):
        """عند عرض النموذج"""
        self.route()

    def route(self, **event_args):
        """التوجيه حسب الـ hash"""
        h = anvil.js.window.location.hash

        if h == "#clients":
            # فتح صفحة العملاء (للقراءة فقط)
            try:
                from ..ClientListForm import ClientListForm
                open_form("ClientListForm")
            except Exception as e:
                alert(f"Error opening ClientListForm: {e}")

        elif h == "#database":
            # فتح صفحة قاعدة البيانات (للقراءة فقط)
            try:
                from ..DatabaseForm import DatabaseForm
                open_form("DatabaseForm")
            except Exception as e:
                alert(f"Error opening DatabaseForm: {e}")

        elif h == "#calculator":
            # فتح الحاسبة
            try:
                open_form("CalculatorForm")
            except Exception as e:
                alert(f"Error opening CalculatorForm: {e}")

        elif h == "#admin":
            # فتح لوحة التحكم (للأدمن فقط)
            try:
                open_form("AdminPanel")
            except Exception as e:
                alert(f"Error opening AdminPanel: {e}")

        elif h == "#import":
            # فتح صفحة الاستيراد (للأدمن فقط)
            try:
                from ..DataImportForm import DataImportForm
                open_form("DataImportForm")
            except Exception as e:
                alert(f"Error opening DataImportForm: {e}")

        # لا نفتح LauncherForm مرة أخرى لتجنب الحلقة اللانهائية

    # =========================================================
    # أحداث الأزرار (إذا كانت موجودة في الواجهة)
    # =========================================================
    def btn_calculator_click(self, **event_args):
        """فتح الحاسبة"""
        anvil.js.window.location.hash = "#calculator"
        open_form("CalculatorForm")

    def btn_clients_click(self, **event_args):
        """فتح صفحة العملاء"""
        anvil.js.window.location.hash = "#clients"
        try:
            open_form("ClientListForm")
        except:
            pass

    def btn_database_click(self, **event_args):
        """فتح صفحة قاعدة البيانات"""
        anvil.js.window.location.hash = "#database"
        try:
            open_form("DatabaseForm")
        except:
            pass

    def btn_admin_click(self, **event_args):
        """فتح لوحة التحكم"""
        anvil.js.window.location.hash = "#admin"
        try:
            open_form("AdminPanel")
        except:
            pass

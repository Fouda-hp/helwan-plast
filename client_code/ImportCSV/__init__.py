from ._anvil_designer import ImportCSVTemplate
from anvil import *
import anvil.google.auth, anvil.google.drive
from anvil.google.drive import app_files
import anvil.server
import anvil.js


class ImportCSV(ImportCSVTemplate):

  def __init__(self, **properties):
    self.init_components(**properties)
    self.file_loader_1.text = "اختار ملف CSV"

  def file_loader_1_change(self, **event_args):
    if self.file_loader_1.file:
      self.file_loader_1.text = self.file_loader_1.file.name
    else:
      self.file_loader_1.text = "اختار ملف CSV"

  @handle("import_btn", "click")
  def import_btn_click(self, **event_args):
    file = self.file_loader_1.file

    if not file:
      file = self.file_loader_1.file

    if not file:
      try: anvil.js.window.showNotification('warning', '', "اختار ملف CSV الأول")
      except Exception: pass
      return

    auth = anvil.js.window.sessionStorage.getItem('auth_token') or anvil.js.window.sessionStorage.getItem('user_email') or None
    result = anvil.server.call("import_csv", file, auth)

    if result.get("success"):
      msg = result.get("msg", "")
      skipped = result.get("skipped_values", [])
      if skipped:
        msg += "\n\nقيم لم يتم إدخالها:\n" + "\n".join(skipped)
      try: anvil.js.window.showNotification('success', 'تم', msg)
      except Exception: pass
    else:
      try: anvil.js.window.showNotification('error', 'خطأ', result.get('msg', ''))
      except Exception: pass
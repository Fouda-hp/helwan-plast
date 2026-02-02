from ._anvil_designer import ImportCSVTemplate
from anvil import *
import anvil.google.auth, anvil.google.drive
from anvil.google.drive import app_files
import anvil.server


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
     alert("اختار ملف CSV الأول")
     return

    result = anvil.server.call("import_csv", file)

    if result.get("success"):
      msg = result.get("msg", "")
      skipped = result.get("skipped_values", [])
      if skipped:
        msg += "\n\nقيم لم يتم إدخالها:\n" + "\n".join(skipped)
      alert(f"✅ {msg}")
    else:
      alert(f"❌ {result.get('msg')}")
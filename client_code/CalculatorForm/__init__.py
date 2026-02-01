from ._anvil_designer import CalculatorFormTemplate
from anvil.tables import app_tables
import anvil.js
import anvil.server
import anvil


class CalculatorForm(CalculatorFormTemplate):

  # =================================================
  # INIT
  # =================================================
  def __init__(self, **properties):
    self.init_components(**properties)

    # ---------- JS bridges (auto numbering)
    anvil.js.window.getNextClientCode = self.get_next_client_code_js
    anvil.js.window.getNextQuotationNumber = self.get_next_quotation_number_js

    # ---------- Overlays & save
    anvil.js.window.getQuotationsForOverlay = self.get_quotations_for_overlay
    anvil.js.window.getQuotationHeaders = self.get_quotation_headers
    anvil.js.window.getClientsForOverlay = self.get_clients_for_overlay
    anvil.js.window.callPythonSave = self.save_button_click

    # ---------- Load from overlays
    anvil.js.window.loadQuotationFromOverlay = self._load_quotation_from_js
    anvil.js.window.loadClientFromOverlay = self._load_client_from_js

    # ---------- Event handlers
    for c in self.get_components():
      if getattr(c, "name", None) == "model_code":
        c.add_event_handler("change", self.on_model_change)
      if getattr(c, "name", None) == "Client Name":
        c.add_event_handler("change", self.on_client_name_change)

  # =================================================
  # JS → PYTHON BRIDGES
  # =================================================
  def get_next_client_code_js(self):
    return anvil.server.call("get_next_client_code")

  def get_next_quotation_number_js(self):
    return anvil.server.call("get_next_quotation_number")

  def _load_quotation_from_js(self, data):
    self.load_quotation(data)

  def _load_client_from_js(self, data):
    self.load_client(data)

  # =================================================
  # HELPERS
  # =================================================
  def find_component(self, name):
    for c in self.get_components():
      if getattr(c, "name", None) == name:
        return c
    return None

  # =================================================
  # AUTO CLIENT CODE
  # =================================================
  def on_client_name_change(self, **event_args):
    code = self.find_component("client_code")
    if code and code.text:
      return

    name_c = self.find_component("Client Name")
    phone_c = self.find_component("Phone")

    if not name_c or not phone_c:
      return

    name = (name_c.text or "").strip()
    phone = (phone_c.text or "").strip()

    if name and phone:
      try:
        new_code = anvil.server.call("get_or_create_client_code", name, phone)
        if new_code:
          code.text = str(new_code)
      except Exception:
        pass

  # =================================================
  # AUTO QUOTATION NUMBER
  # =================================================
  def on_model_change(self, **event_args):
    model = self.find_component("model_code")
    qn = self.find_component("Quotation#")

    if not model or not qn or qn.text:
      return

    try:
      next_no = anvil.server.call(
        "get_quotation_number_if_needed",
        qn.text,
        model.text
      )
      if next_no is not None:
        qn.text = str(next_no)
    except Exception:
      pass

  # =================================================
  # SAVE
  # =================================================
  def save_button_click(self, **event_args):
    try:
      form_data = dict(anvil.js.window.collectFormData())
    except Exception as e:
      return {"success": False, "message": str(e)}

    return self._save_to_server(form_data)

  def _save_to_server(self, form_data):
    try:
      return anvil.server.call("save_quotation", form_data)
    except Exception as e:
      return {"success": False, "message": str(e)}

  # =================================================
  # OVERLAYS
  # =================================================
  def get_quotation_headers(self):
    return [c.name for c in app_tables.quotations.columns]

  def get_quotations_for_overlay(self):
    return anvil.server.call("get_all_quotations")

  def get_clients_for_overlay(self):
    return anvil.server.call("get_all_clients")

  # =================================================
  # LOAD DATA
  # =================================================
  def load_client(self, data):
    if not data:
      return
    for k, v in data.items():
      c = self.find_component(k)
      if c and hasattr(c, "text"):
        c.text = v or ""

  def load_quotation(self, data):
    if not data:
      return
    for k, v in data.items():
      c = self.find_component(k)
      if c:
        if hasattr(c, "checked"):
          c.checked = (v == "YES")
        elif hasattr(c, "text"):
          c.text = v or ""

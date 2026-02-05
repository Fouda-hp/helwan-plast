from ._anvil_designer import CalculatorFormTemplate
import anvil.google.auth, anvil.google.drive
from anvil.google.drive import app_files
from anvil.tables import app_tables
import anvil.js
import anvil.server
import anvil
import json


class CalculatorForm(CalculatorFormTemplate):

  # =================================================
  # INIT
  # =================================================
  def __init__(self, **properties):
    self.init_components(**properties)
    
    # ---------- Bind form_show event to load settings
    self.add_event_handler('show', self.form_show)

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
    
    # ---------- Get active users for Sales Rep dropdown
    anvil.js.window.getActiveUsersForDropdown = self.get_active_users_for_dropdown

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
      # Get user email from sessionStorage (جلسة تنتهي عند إغلاق التاب)
      user_email = anvil.js.window.sessionStorage.getItem('user_email') or 'system'
      return anvil.server.call("save_quotation", form_data, user_email)
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

  def get_active_users_for_dropdown(self):
    return anvil.server.call("get_active_users_for_dropdown")

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

  def form_show(self, **event_args):
    """جلب كل الإعدادات من السيرفر في استدعاء واحد وتمريرها للصفحة."""
    try:
      # استدعاء واحد بدل 7 — تقليل ثقل الشبكة
      data = anvil.server.call("get_calculator_settings")
      if not data:
        data = {}
      settings_payload = {}
      if data.get("exchangeRate") is not None:
        try:
          settings_payload["exchangeRate"] = float(str(data["exchangeRate"]).replace(",", "."))
        except (ValueError, TypeError):
          pass
      for key in ["shipping_sea", "ths_cost", "clearance_expenses", "tax_rate", "bank_commission"]:
        val = data.get(key)
        if val is not None:
          try:
            settings_payload[key] = float(val) if isinstance(val, (int, float)) else float(str(val).replace(",", "."))
          except (ValueError, TypeError):
            pass
      if data.get("config"):
        settings_payload["config"] = data["config"]
      if data.get("priceOptions"):
        settings_payload["priceOptions"] = data["priceOptions"]
      json_str = json.dumps(settings_payload, default=str)
      escaped = json_str.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
      try:
        set_global = 'var _p = JSON.parse("%s"); window.__calculatorSettingsFromPython = _p; if (window.top && window.top !== window) window.top.__calculatorSettingsFromPython = _p;' % escaped
        anvil.js.window.eval(set_global)
      except Exception:
        pass
      apply_js = (
        "var _d = (window.__calculatorSettingsFromPython || (window.top && window.top.__calculatorSettingsFromPython));"
        "var _apply = function() { if (window.applyCalculatorSettingsFromPython && _d) { try { window.applyCalculatorSettingsFromPython(_d); } catch(e) {} } };"
        "setTimeout(_apply, 150); setTimeout(_apply, 500); setTimeout(_apply, 1200);"
      )
      anvil.js.window.eval(apply_js)
      anvil.js.window.eval(
        "var _r=function(){ if (window.reinitCalculatorDropdowns) window.reinitCalculatorDropdowns(); };"
        "setTimeout(_r, 250); setTimeout(_r, 800);"
      )
    except Exception as e:
      print("CalculatorForm form_show error:", e)

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

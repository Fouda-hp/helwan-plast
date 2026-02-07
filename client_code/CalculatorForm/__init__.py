from ._anvil_designer import CalculatorFormTemplate
import anvil.js
import anvil.server
import anvil
import json
import logging

logger = logging.getLogger(__name__)


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
    anvil.js.window.getClientsForOverlay = self.get_clients_for_overlay
    anvil.js.window.callPythonSave = self.save_button_click

    # ---------- Load from overlays
    # ملاحظة: loadQuotationFromOverlay و loadClientFromOverlay
    # يتم تعريفهما في quotations.js و clients.js (التنفيذ الكامل مع DOM/cylinders/checkboxes)
    # لذلك لا نُعيد تعريفهما هنا لتجنب التعارض

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
      except Exception as e:
        logger.debug("Auto client code error: %s", e)

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
    except Exception as e:
      logger.debug("Auto quotation number error: %s", e)

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
      user_email = anvil.js.window.sessionStorage.getItem('user_email') or 'system'
      auth = anvil.js.window.sessionStorage.getItem('auth_token') or user_email
      return anvil.server.call("save_quotation", form_data, user_email, auth)
    except Exception as e:
      return {"success": False, "message": str(e)}

  # =================================================
  # OVERLAYS
  # =================================================
  def get_quotations_for_overlay(self):
    auth = anvil.js.window.sessionStorage.getItem('auth_token') or anvil.js.window.sessionStorage.getItem('user_email')
    return anvil.server.call("get_all_quotations", 1, 20, '', False, auth)

  def get_clients_for_overlay(self):
    auth = anvil.js.window.sessionStorage.getItem('auth_token') or anvil.js.window.sessionStorage.getItem('user_email')
    return anvil.server.call("get_all_clients", 1, 20, '', False, auth)

  def get_active_users_for_dropdown(self):
    auth = anvil.js.window.sessionStorage.getItem('auth_token') or anvil.js.window.sessionStorage.getItem('user_email')
    return anvil.server.call("get_active_users_for_dropdown", auth)

  # =================================================
  # FORM SHOW - LOAD SETTINGS
  # =================================================
  def form_show(self, **event_args):
    """جلب كل الإعدادات من السيرفر في استدعاء واحد وتمريرها للصفحة."""
    try:
      ls = anvil.js.window.localStorage
      if ls:
        ls.setItem('hp_last_page', '#calculator')
    except Exception:
      pass
    try:
      auth = anvil.js.window.sessionStorage.getItem('auth_token') or anvil.js.window.sessionStorage.getItem('user_email')
      logger.info("CalculatorForm form_show: auth=%s", auth[:12] + '...' if auth and len(auth) > 12 else auth)
      data = anvil.server.call("get_calculator_settings", auth)
      logger.info("CalculatorForm form_show: success=%s, has_priceOptions=%s, has_machinePrices=%s, message=%s",
                  data.get('success') if data else None,
                  bool(data.get('priceOptions')) if data else False,
                  bool(data.get('machinePrices')) if data else False,
                  data.get('message', '') if data else 'no data')
      if not data or data.get("success") is False:
        logger.warning("CalculatorForm: get_calculator_settings failed: %s", data.get('message') if data else 'no data')
        data = {} if not data else {k: v for k, v in data.items() if k not in ("success", "message")}
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
      # المصدر الوحيد: جدول Machine Prices (USD) — لا نستخدم config الثابت
      if data.get("priceOptions"):
        settings_payload["priceOptions"] = data["priceOptions"]
        logger.info("form_show: priceOptions types=%s, typeColorWidths keys=%s",
                    data["priceOptions"].get("types"),
                    {t: {c: ws for c, ws in cv.items()}
                     for t, cv in (data["priceOptions"].get("typeColorWidths") or {}).items()})
      else:
        logger.warning("form_show: NO priceOptions in server response!")
      if data.get("machinePrices") is not None:
        settings_payload["machinePrices"] = data["machinePrices"]
        logger.info("form_show: machinePrices types=%s", list(data["machinePrices"].keys()) if isinstance(data["machinePrices"], dict) else 'not dict')
      else:
        logger.warning("form_show: NO machinePrices in server response!")
      if data.get("cylinderPrices") is not None:
        settings_payload["cylinderPrices"] = data["cylinderPrices"]
      # تمرير البيانات مباشرة عبر anvil.js بدون eval
      try:
        json_str = json.dumps(settings_payload, default=str)
        parsed = anvil.js.window.JSON.parse(json_str)
        anvil.js.window.__calculatorSettingsFromPython = parsed
        try:
          if anvil.js.window.top and anvil.js.window.top != anvil.js.window:
            anvil.js.window.top.__calculatorSettingsFromPython = parsed
        except Exception:
          pass
      except Exception:
        pass
      # تطبيق الإعدادات مع تقليل عدد الاستدعاءات (2 بدل 5) وإزالة التكرار
      apply_js = (
        "var _d = (window.__calculatorSettingsFromPython || (window.top && window.top.__calculatorSettingsFromPython));"
        "if(_d){console.log('[CALC] Settings from Python:',JSON.stringify({hasPriceOptions:!!_d.priceOptions,hasMachinePrices:!!_d.machinePrices,priceOptionTypes:_d.priceOptions?_d.priceOptions.types:null,typeColorWidths:_d.priceOptions?_d.priceOptions.typeColorWidths:null}));}"
        "else{console.warn('[CALC] NO settings from Python!');}"
        "var _applied = false;"
        "var _apply = function() { if (_applied) return; if (window.applyCalculatorSettingsFromPython && _d) { try { _applied = true; window.applyCalculatorSettingsFromPython(_d); if (window.calculateAll) setTimeout(window.calculateAll, 50); } catch(e) { _applied = false; console.error('[CALC] apply error:', e); } } };"
        "var _rDone = false;"
        "var _r = function() { if (_rDone) return; if (window.reinitCalculatorDropdowns) { _rDone = true; window.reinitCalculatorDropdowns(); } };"
        "setTimeout(_apply, 300); setTimeout(_apply, 2000);"
        "setTimeout(_r, 500); setTimeout(_r, 2000);"
      )
      anvil.js.window.eval(apply_js)
    except Exception as e:
      logger.debug("CalculatorForm form_show error: %s", e)

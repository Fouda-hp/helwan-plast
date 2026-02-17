from ._anvil_designer import CalculatorFormTemplate
import anvil.js
import anvil.server
import anvil
import json
import logging

try:
    from ..notif_bridge import register_notif_bridges
except ImportError:
    from notif_bridge import register_notif_bridges

logger = logging.getLogger(__name__)


class CalculatorForm(CalculatorFormTemplate):

  # =================================================
  # INIT
  # =================================================
  def __init__(self, **properties):
    self.init_components(**properties)

    # ---------- Bind form_show event to load settings
    self.add_event_handler('show', self.form_show)

    # ---------- JS bridges (auto numbering — peek فقط بدون حجز)
    anvil.js.window.getNextClientCode = self.peek_next_client_code_js
    anvil.js.window.getNextQuotationNumber = self.peek_next_quotation_number_js
    anvil.js.window.resyncNumberingCounters = self.resync_numbering_counters_js
    anvil.js.window.getClientCodeFromServer = self.find_client_by_phone_js

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

    # ---------- Notification bridges
    register_notif_bridges()

  # =================================================
  # JS → PYTHON BRIDGES
  # =================================================
  def _get_auth(self):
    return anvil.js.window.sessionStorage.getItem('auth_token')

  def peek_next_client_code_js(self):
    """عرض رمز العميل التالي المتوقع بدون حجز (للعرض فقط)."""
    return anvil.server.call("peek_next_client_code", self._get_auth())

  def peek_next_quotation_number_js(self):
    """عرض رقم العرض التالي المتوقع بدون حجز (للعرض فقط)."""
    return anvil.server.call("peek_next_quotation_number", self._get_auth())

  def resync_numbering_counters_js(self):
    """إعادة مزامنة الترقيم مع الجداول (عميل 6، عرض 8 إذا عندك 5 عملاء و 7 عروض)."""
    return anvil.server.call("resync_numbering_counters", self._get_auth())

  def find_client_by_phone_js(self, name, phone):
    """البحث عن عميل بالتليفون — يرجع كوده لو موجود، أو None."""
    return anvil.server.call("find_client_by_phone", name, phone, self._get_auth())

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
        auth = self._get_auth()
        existing_code = anvil.server.call("find_client_by_phone", name, phone, auth)
        if existing_code:
          code.text = str(existing_code)
        else:
          peek_code = anvil.server.call("peek_next_client_code", auth)
          if peek_code:
            code.text = str(peek_code)
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
        model.text,
        self._get_auth()
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
      auth = self._get_auth()
      if not auth:
        return {"success": False, "message": "Not authenticated. Please login again."}
      return anvil.server.call("save_quotation", form_data, user_email, auth)
    except Exception as e:
      return {"success": False, "message": str(e)}

  # =================================================
  # OVERLAYS
  # =================================================
  def get_quotations_for_overlay(self):
    auth = self._get_auth()
    if not auth:
      return {"success": False, "message": "Not authenticated", "data": []}
    return anvil.server.call("get_all_quotations", 1, 20, '', False, auth)

  def get_clients_for_overlay(self):
    auth = self._get_auth()
    if not auth:
      return {"success": False, "message": "Not authenticated", "data": []}
    return anvil.server.call("get_all_clients", 1, 20, '', False, auth)

  def get_active_users_for_dropdown(self):
    auth = self._get_auth()
    if not auth:
      return {"success": False, "message": "Not authenticated", "users": []}
    return anvil.server.call("get_active_users_for_dropdown", auth)

  # =================================================
  # Settings application helper (بدون eval)
  # =================================================
  def _apply_settings_with_retry(self, parsed):
    """تطبيق إعدادات الحاسبة مع retry عبر setTimeout — بدون eval."""
    try:
      w = anvil.js.window
      # Direct call first (إذا الدالة متاحة فوراً)
      try:
        fn = getattr(w, 'applyCalculatorSettingsFromPython', None)
        if fn and parsed:
          fn(parsed)
          calc_fn = getattr(w, 'calculateAll', None)
          if calc_fn:
            w.setTimeout(calc_fn, 50)
          logger.info("Settings applied directly (no retry needed)")
      except Exception as e:
        logger.warning("Direct apply failed (%s), scheduling retries", e)

      # Retry with setTimeout (الدوال قد لا تكون جاهزة بعد)
      def _make_apply_fn():
        applied = [False]
        def _try_apply():
          if applied[0]:
            return
          try:
            fn = getattr(w, 'applyCalculatorSettingsFromPython', None)
            data = getattr(w, '__calculatorSettingsFromPython', None)
            if fn and data:
              applied[0] = True
              fn(data)
              calc_fn = getattr(w, 'calculateAll', None)
              if calc_fn:
                w.setTimeout(calc_fn, 50)
          except Exception:
            applied[0] = False
        return _try_apply

      def _make_reinit_fn():
        done = [False]
        def _try_reinit():
          if done[0]:
            return
          try:
            fn = getattr(w, 'reinitCalculatorDropdowns', None)
            if fn:
              done[0] = True
              fn()
          except Exception:
            pass
        return _try_reinit

      apply_fn = _make_apply_fn()
      reinit_fn = _make_reinit_fn()
      for delay in [300, 1000, 2000, 4000]:
        w.setTimeout(apply_fn, delay)
      for delay in [500, 2000]:
        w.setTimeout(reinit_fn, delay)
    except Exception as e:
      logger.debug("_apply_settings_with_retry error: %s", e)

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
      auth = self._get_auth()
      logger.info("CalculatorForm form_show: auth=%s", auth[:12] + '...' if auth and len(auth) > 12 else auth)
      if not auth:
        logger.warning("CalculatorForm form_show: missing auth token")
        return
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
      # تعديلات الأسعار والنسب (من Settings)
      for adj_key in ["materialAdjustments", "winderAdjustment", "optionalAdjustments"]:
        if data.get(adj_key) is not None:
          settings_payload[adj_key] = data[adj_key]
      # نسب الربح (Markups)
      markups = {}
      for mk in ["markup_overseas", "markup_local_instock_4color", "markup_local_instock_other",
                  "markup_local_neworder_4color", "markup_local_neworder_other"]:
        val = data.get(mk)
        if val is not None:
          try:
            markups[mk.replace("markup_", "")] = float(val)
          except (ValueError, TypeError):
            pass
      if markups:
        settings_payload["markups"] = markups
      # تمرير البيانات مباشرة عبر anvil.js بدون eval
      logger.info("form_show: settings_payload keys=%s, has priceOptions=%s", list(settings_payload.keys()), bool(settings_payload.get("priceOptions")))
      try:
        json_str = json.dumps(settings_payload, default=str)
        parsed = anvil.js.window.JSON.parse(json_str)
        anvil.js.window.__calculatorSettingsFromPython = parsed
        logger.info("form_show: __calculatorSettingsFromPython SET on anvil.js.window")
        try:
          if anvil.js.window.top and anvil.js.window.top != anvil.js.window:
            anvil.js.window.top.__calculatorSettingsFromPython = parsed
        except Exception:
          pass
      except Exception as e:
        logger.error("form_show: FAILED to set __calculatorSettingsFromPython: %s", e)
      # تطبيق الإعدادات بدون eval — Python مباشر مع retry عبر setTimeout
      self._apply_settings_with_retry(parsed)
    except Exception as e:
      logger.debug("CalculatorForm form_show error: %s", e)

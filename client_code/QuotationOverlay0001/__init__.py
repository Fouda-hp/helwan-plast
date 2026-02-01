from ._anvil_designer import QuotationOverlay0001Template
from anvil import *
import anvil.server

class QuotationOverlay0001(QuotationOverlay0001Template):
  def __init__(self, **properties):
    self.init_components(**properties)
    self.repeating_panel_1.items = anvil.server.call("get_all_quotations")

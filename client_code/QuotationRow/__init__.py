from ._anvil_designer import QuotationRowTemplate
from anvil import *

class QuotationRow(QuotationRowTemplate):

  def __init__(self, **properties):
    self.init_components(**properties)

  def form_double_click(self, **event_args):
    self.parent.raise_event(
      "x-close-alert",
      value=self.item
    )

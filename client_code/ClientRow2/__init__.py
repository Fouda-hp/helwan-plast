from ._anvil_designer import ClientRow2Template
from anvil import *
import anvil.server
import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables


class ClientRow2(ClientRow2Template):
  def __init__(self, **properties):
    # Set Form properties and Data Bindings.
    self.init_components(**properties)

  def form_show(self, **event_args):
    self.lbl_client_code.text = self.item['Client Code']
    self.lbl_client_name.text = self.item['Client Name']
    self.lbl_company.text = self.item['Company']
    self.lbl_phone.text = self.item['Phone']
    # Any code you write here will run before the form opens.

from ._anvil_designer import ClientListFormTemplate
from anvil import *
import anvil.server
import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables


class ClientListForm(ClientListFormTemplate):
  def __init__(self, **properties):
    # Set Form properties and Data Bindings.
    self.init_components(**properties)

  def form_show(self, **event_args):
    self.load_clients()
  
  def load_clients(self):
    self.repeating_panel_clients.items = app_tables.CLIENTS.search()
    # Any code you write here will run before the form opens.

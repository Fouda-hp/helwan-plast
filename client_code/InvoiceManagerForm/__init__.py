from ._anvil_designer import InvoiceManagerFormTemplate
from anvil import *
import anvil.server
import anvil.js
from ..auth_helpers import get_auth_token


class InvoiceManagerForm(InvoiceManagerFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

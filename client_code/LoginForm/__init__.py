from ._anvil_designer import LoginFormTemplate
from anvil import *
import anvil.server
import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables
import anvil.js

class LoginForm(LoginFormTemplate):
  def __init__(self, **properties):
    self.init_components(**properties)

    # افحص الهـاش أول ما الفورم يفتح
    self.check_route()

    # اسمع أي تغيير في الـ URL
    anvil.js.window.addEventListener("hashchange", self.on_hash_change)

  def on_hash_change(self, event):
    self.check_route()

  def check_route(self):
    hash_val = anvil.js.window.location.hash

    if hash_val == "#launcher":
      open_form('LauncherForm')

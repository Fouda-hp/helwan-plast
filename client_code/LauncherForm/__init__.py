from ._anvil_designer import LauncherFormTemplate
from anvil import *
import anvil.server
import anvil.tables as tables
import anvil.tables.query as q
from anvil.tables import app_tables
import anvil.js

class LauncherForm(LauncherFormTemplate):
  def __init__(self, **properties):
    self.init_components(**properties)

    # نفحص الـ hash مرة واحدة عند التحميل
    self.check_route()

    # نربط listener بطريقة صحيحة
    anvil.js.window.addEventListener("hashchange", self.on_hash_change)

  def on_hash_change(self, event):
    self.check_route()

  def check_route(self):
    hash_val = anvil.js.window.location.hash

    if hash_val == "#calculator":
      open_form('CalculatorForm')
      
  def form_show(self, **event_args):
    self.route()
  
  def route(self, **event_args):
    h = anvil.js.window.location.hash
  
    if h == "#clients":
      open_form("ClientListForm")
  
    elif h == "#database":
      open_form("DatabaseForm")
  
    elif h == "#calculator":
      open_form("CalculatorForm")
  
    else:
      open_form("LauncherForm")

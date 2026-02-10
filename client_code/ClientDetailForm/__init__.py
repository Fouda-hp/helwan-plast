"""
ClientDetailForm - صفحة تفاصيل العميل مع التايم لاين والملاحظات والوسوم
=======================================================================
"""

from ._anvil_designer import ClientDetailFormTemplate
from anvil import *
import anvil.server
import anvil.js


class ClientDetailForm(ClientDetailFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Bridge functions for JavaScript
        anvil.js.window.pyGetClientDetail = self.get_client_detail
        anvil.js.window.pyGetClientTimeline = self.get_client_timeline
        anvil.js.window.pyAddClientNote = self.add_client_note
        anvil.js.window.pyDeleteClientNote = self.delete_client_note
        anvil.js.window.pySetClientTags = self.set_client_tags
        anvil.js.window.pyGetAllTags = self.get_all_tags
        anvil.js.window.pyGoBack = self.go_back

    def _auth(self):
        token = anvil.js.window.sessionStorage.getItem('auth_token')
        if not token:
            token = anvil.js.window.localStorage.getItem('auth_token')
            if token:
                try:
                    anvil.js.window.sessionStorage.setItem('auth_token', token)
                except Exception:
                    pass
        return token

    def get_client_detail(self, client_code):
        return anvil.server.call('get_client_detail', client_code, self._auth())

    def get_client_timeline(self, client_code, type_filter, page, page_size):
        return anvil.server.call('get_client_timeline', client_code, type_filter, page, page_size, self._auth())

    def add_client_note(self, client_code, text):
        return anvil.server.call('add_client_note', client_code, text, self._auth())

    def delete_client_note(self, client_code, note_id):
        return anvil.server.call('delete_client_note', client_code, note_id, self._auth())

    def set_client_tags(self, client_code, tags):
        return anvil.server.call('set_client_tags', client_code, tags, self._auth())

    def get_all_tags(self):
        return anvil.server.call('get_all_tags', self._auth())

    def go_back(self):
        anvil.js.window.location.hash = '#clients'

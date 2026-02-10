"""
FollowUpDashboardForm - لوحة تذكيرات المتابعة
================================================
"""

from ._anvil_designer import FollowUpDashboardFormTemplate
from anvil import *
import anvil.server
import anvil.js
from ..auth_helpers import get_auth_token


class FollowUpDashboardForm(FollowUpDashboardFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Bridge functions
        anvil.js.window.pyGetFollowupDashboard = self.get_dashboard
        anvil.js.window.pySetFollowup = self.set_followup
        anvil.js.window.pySnoozeFollowup = self.snooze_followup
        anvil.js.window.pyCompleteFollowup = self.complete_followup
        anvil.js.window.pyCheckOverdue = self.check_overdue
        anvil.js.window.pyGoBack = self.go_back

    def _auth(self):
        return get_auth_token()

    def get_dashboard(self, filter_status):
        return anvil.server.call('get_followup_dashboard', self._auth(), filter_status)

    def set_followup(self, quotation_number, follow_up_date):
        return anvil.server.call('set_followup', quotation_number, follow_up_date, self._auth())

    def snooze_followup(self, quotation_number, snooze_days):
        return anvil.server.call('snooze_followup', quotation_number, snooze_days, self._auth())

    def complete_followup(self, quotation_number):
        return anvil.server.call('complete_followup', quotation_number, self._auth())

    def check_overdue(self):
        return anvil.server.call('check_overdue_followups', self._auth())

    def go_back(self):
        anvil.js.window.location.hash = '#launcher'

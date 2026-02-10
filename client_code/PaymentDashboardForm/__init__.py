"""
PaymentDashboardForm - Payment Tracking Dashboard
==================================================
- View all contracts with payment schedules
- Track paid/due/overdue payments
- Update payment status
- Statistics cards and charts
- Overdue alerts
- Export payment schedule
"""
from ._anvil_designer import PaymentDashboardFormTemplate
from anvil import *
import anvil.server
import anvil.js
from ..auth_helpers import get_auth_token

try:
    from ..notif_bridge import register_notif_bridges
except ImportError:
    from notif_bridge import register_notif_bridges


class PaymentDashboardForm(PaymentDashboardFormTemplate):
    def __init__(self, **properties):
        self.init_components(**properties)

        # Bridge functions for JavaScript
        anvil.js.window.pyGetContractsList = self.get_contracts_list
        anvil.js.window.pyGetPaymentDashboardData = self.get_payment_dashboard_data
        anvil.js.window.pyUpdatePaymentStatus = self.update_payment_status
        anvil.js.window.pyExportPaymentSchedule = self.export_payment_schedule
        anvil.js.window.pyGoBack = self.go_back

        # Notification bridges
        register_notif_bridges()

    def _auth(self):
        return get_auth_token()

    def get_contracts_list(self, search='', page=1, page_size=20):
        return anvil.server.call('get_contracts_list', search, self._auth(), page, page_size)

    def get_payment_dashboard_data(self):
        return anvil.server.call('get_payment_dashboard_data', self._auth())

    def update_payment_status(self, quotation_number, payment_index, new_status, paid_date=None):
        return anvil.server.call('update_payment_status',
                                  quotation_number, payment_index, new_status, paid_date, self._auth())

    def export_payment_schedule(self):
        try:
            result = anvil.server.call('export_payment_schedule_excel', self._auth())
            if result and result.get('success') and result.get('file'):
                anvil.media.download(result['file'])
                return {'success': True}
            return result or {'success': False, 'message': 'No file returned'}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    def go_back(self):
        anvil.js.window.location.hash = '#launcher'

# ContractEditForm - نفس واجهة العقود مع زر Update وقائمة العقود
# يُعاد استخدام قالب ContractPrintForm.
from anvil import *
try:
    from ..ContractPrintForm._anvil_designer import ContractPrintFormTemplate
    ContractEditFormTemplate = ContractPrintFormTemplate
except Exception:
    from anvil import ColumnPanel
    class ContractEditFormTemplate(ColumnPanel):
        def init_components(self, **properties):
            pass

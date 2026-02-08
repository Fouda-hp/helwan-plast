# ContractEditForm - نفس واجهة العقود مع زر Update وقائمة العقود
# يُعاد استخدام قالب ContractPrintForm. يجب أن يكون Template صنفاً فرعياً وليس alias
# حتى لا يظهر نفس الصنف مرتين في MRO (يسبب TypeError: Inconsistent precedences in type hierarchy).
from anvil import *
try:
    from ..ContractPrintForm._anvil_designer import ContractPrintFormTemplate

    class ContractEditFormTemplate(ContractPrintFormTemplate):
        """صنف فرعي مميز للواجهة حتى يكون تسلسل الوراثة متسقاً مع ContractPrintForm."""
        pass
except Exception:
    from anvil import ColumnPanel

    class ContractEditFormTemplate(ColumnPanel):
        def init_components(self, **properties):
            pass

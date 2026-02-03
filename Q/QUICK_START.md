# 🚀 تعليمات التثبيت والتشغيل السريع

## التثبيت

### 1. تثبيت المكتبة الأساسية (مطلوبة)
```bash
pip install reportlab
```

### 2. تثبيت مكتبات العربي (اختياري - للنص العربي الصحيح)
```bash
pip install arabic-reshaper python-bidi
```

**ملاحظة**: إذا كنت تستخدم Anvil، فقد تحتاج إضافة `--break-system-packages`:
```bash
pip install reportlab --break-system-packages
pip install arabic-reshaper python-bidi --break-system-packages
```

---

## الاستخدام السريع

### تشغيل مع البيانات الافتراضية
```bash
python quotation_generator.py
```

سيتم إنشاء ملفين PDF:
- `quotation_arabic_[timestamp].pdf` - النسخة العربية
- `quotation_english_[timestamp].pdf` - النسخة الإنجليزية

---

## تعديل البيانات

### في Python Script
```python
from quotation_generator import QuotationData, generate_quotations

# إنشاء كائن البيانات
data = QuotationData()

# تعديل البيانات
data.client_name_ar = "اسم العميل الجديد"
data.client_name_en = "New Client Name"
data.total_price = "3,500,000"

# إنشاء PDF
arabic_file, english_file = generate_quotations(data)
```

### في Anvil Server Module
```python
import anvil.server
from quotation_generator import QuotationData, generate_quotations

@anvil.server.callable
def create_quotation(client_data):
    data = QuotationData()
    
    # تعبئة من البيانات المستلمة
    data.client_name_ar = client_data.get('client_name_ar')
    data.total_price = client_data.get('total_price')
    # ... إلخ
    
    return generate_quotations(data)
```

---

## الملفات المهمة

| الملف | الوصف |
|------|-------|
| `quotation_generator.py` | الملف الرئيسي - استخدمه في مشروعك |
| `example_usage.py` | أمثلة عملية للاستخدام |
| `README.md` | دليل كامل ومفصل |
| `VARIABLES_REFERENCE.md` | قائمة كاملة بجميع المتغيرات |
| `QUICK_START.md` | هذا الملف |

---

## اختبار سريع

```python
# اختبار بسيط
from quotation_generator import QuotationData, generate_quotations

data = QuotationData()
data.client_name_ar = "شركة اختبار"
data.quotation_number = "TEST-001"

arabic, english = generate_quotations(data)
print(f"تم الإنشاء: {arabic}")
```

---

## المساعدة

- **للتعليمات الكاملة**: اقرأ `README.md`
- **لقائمة المتغيرات**: اقرأ `VARIABLES_REFERENCE.md`
- **للأمثلة العملية**: شغّل `example_usage.py`

---

## نصائح

✅ **افعل**:
- استخدم الفواصل في الأرقام: `"2,150,000"`
- غيّر النسخة العربية والإنجليزية معاً
- اختبر الكود قبل الإنتاج

❌ **لا تفعل**:
- لا تنسى استخدام علامات التنصيص للقيم النصية
- لا تستخدم أرقام بدون فواصل للمبالغ الكبيرة
- لا تعدّل الملف الأساسي إذا كنت تستخدمه في مشاريع متعددة

---

**بالتوفيق! 🎉**

# مولد عروض الأسعار - Quotation Generator

## نظرة عامة

هذا المشروع يوفر نظام احترافي لإنشاء عروض أسعار بصيغة PDF باللغتين العربية والإنجليزية. تم تصميمه للعمل مع **Anvil** وأي نظام آخر.

## المميزات

✅ **تصميم احترافي**: تخطيط نظيف ومرتب يشبه عروض الأسعار الحقيقية  
✅ **دعم كامل للعربي والإنجليزي**: ملفات منفصلة لكل لغة  
✅ **سهل التعديل**: جميع المتغيرات في مكان واحد  
✅ **كود نظيف**: تعليقات عربية شاملة وكود منظم  
✅ **جاهز للإنتاج**: يمكن دمجه مباشرة مع Anvil  

---

## المتطلبات

### المكتبات الأساسية (مطلوبة):
```bash
pip install reportlab
```

### المكتبات الاختيارية (للعربي الصحيح):
```bash
pip install arabic-reshaper python-bidi
```

**ملاحظة**: الكود يعمل بدون المكتبات الاختيارية، لكن النص العربي سيظهر بشكل أفضل معها.

---

## طريقة الاستخدام

### 1. الاستخدام الأساسي (مع البيانات الافتراضية)

```python
from quotation_generator import generate_quotations

# إنشاء عروض أسعار باستخدام البيانات الافتراضية
arabic_file, english_file = generate_quotations()

print(f"تم إنشاء: {arabic_file}")
print(f"تم إنشاء: {english_file}")
```

### 2. الاستخدام المتقدم (مع بيانات مخصصة)

```python
from quotation_generator import QuotationData, generate_quotations

# إنشاء كائن البيانات
data = QuotationData()

# تعديل البيانات حسب الحاجة
data.client_name_ar = "شركة العميل الجديد"
data.client_name_en = "New Client Company"
data.total_price = "3,500,000"
data.quotation_number = "123"

# إنشاء عروض الأسعار
arabic_file, english_file = generate_quotations(data)
```

### 3. الاستخدام مع Anvil

في Anvil Server Code:

```python
import anvil.pdf
from quotation_generator import QuotationData, generate_quotations

@anvil.server.callable
def create_quotation_pdfs(client_data):
    """
    دالة تُستدعى من Anvil لإنشاء عروض الأسعار
    
    Parameters:
    -----------
    client_data : dict
        قاموس يحتوي على بيانات العميل والماكينة
    
    Returns:
    --------
    tuple : (arabic_pdf_media, english_pdf_media)
        ملفات PDF كـ Anvil Media Objects
    """
    
    # إنشاء كائن البيانات
    data = QuotationData()
    
    # تعبئة البيانات من Anvil
    data.client_name_ar = client_data.get('client_name_ar', data.client_name_ar)
    data.client_name_en = client_data.get('client_name_en', data.client_name_en)
    data.total_price = client_data.get('total_price', data.total_price)
    data.machine_model = client_data.get('machine_model', data.machine_model)
    # ... وهكذا لباقي الحقول
    
    # إنشاء عروض الأسعار
    arabic_file, english_file = generate_quotations(data)
    
    # تحويل إلى Anvil Media Objects
    with open(arabic_file, 'rb') as f:
        arabic_pdf = anvil.pdf.PDFRenderer(f.read())
    
    with open(english_file, 'rb') as f:
        english_pdf = anvil.pdf.PDFRenderer(f.read())
    
    return arabic_pdf, english_pdf
```

---

## تعديل البيانات

جميع البيانات القابلة للتعديل موجودة في كلاس `QuotationData`. إليك شرح للحقول الرئيسية:

### بيانات الشركة
```python
data.company_name_ar = "شركة حلوان بلاست ذ.م.م"
data.company_name_en = "Helwan Plast LLC"
data.company_address_ar = "المنطقة الصناعية الثانية - قطعة ٢٠"
data.company_address_en = "Second Industrial Zone – Plot 20"
data.company_phone = "01050332771"
data.company_email = "sales@helwanplast.com"
data.company_website = "www.helwanplast.com"
```

### بيانات العميل
```python
data.client_name_ar = "محمود - حكيم بلاست"
data.client_name_en = "Mahmoud - Hakim Plast"
```

### بيانات عرض السعر
```python
data.quotation_number = "5"
data.quotation_date = "15 مايو"
data.quotation_date_en = "15 May"
data.quotation_location = "القاهرة"
data.quotation_location_en = "Cairo"
```

### مواصفات الماكينة
```python
data.machine_model = "SH4-1000CC/D"
data.country_origin_ar = "الصين"
data.country_origin_en = "China"
data.colors_count = "4"
data.machine_width = "100"  # سم
```

### الأسعار والدفع
```python
data.total_price = "2,150,000"  # جنيه
data.down_payment_percent = "40"
data.down_payment_amount = "860,000"
data.before_shipping_percent = "30"
data.before_shipping_amount = "645,000"
data.before_delivery_percent = "30"
data.before_delivery_amount = "645,000"
```

### سلندرات الطباعة
```python
data.printing_cylinders = [
    {"size": "25", "count": "4"},
    {"size": "30", "count": "4"},
    {"size": "35", "count": "4"},
    # ... المزيد
]
```

---

## البنية والتنظيم

```
📁 Project Root
│
├── 📄 quotation_generator.py     # الملف الرئيسي
│   ├── 📦 QuotationData          # كلاس البيانات (عدل هنا!)
│   ├── 🔧 Helper Functions       # دوال مساعدة
│   ├── 📄 create_english_quotation  # توليد PDF إنجليزي
│   ├── 📄 create_arabic_quotation   # توليد PDF عربي
│   └── 🚀 generate_quotations    # الدالة الرئيسية
│
├── 📄 README.md                  # هذا الملف
└── 📄 example_usage.py           # أمثلة الاستخدام
```

---

## الدوال الرئيسية

### `QuotationData()`
كلاس يحتوي على جميع بيانات عرض السعر. أنشئ كائن منه وعدّل القيم.

### `generate_quotations(data=None)`
الدالة الرئيسية لتوليد عروض الأسعار.

**Parameters:**
- `data` (QuotationData, optional): بيانات عرض السعر. إذا لم يتم توفيرها، سيتم استخدام البيانات الافتراضية.

**Returns:**
- `tuple`: (arabic_filename, english_filename) - أسماء ملفات PDF المُنشأة

### `prepare_arabic_text(text)`
تجهيز النص العربي للعرض بشكل صحيح في PDF.

### `draw_header(c, data, is_arabic=True)`
رسم ترويسة عرض السعر.

### `draw_footer(c, page_num, is_arabic=True)`
رسم تذييل الصفحة.

---

## أمثلة عملية

### مثال 1: تغيير بيانات العميل فقط

```python
from quotation_generator import QuotationData, generate_quotations

data = QuotationData()
data.client_name_ar = "شركة النور للتجارة"
data.client_name_en = "Al Nour Trading Company"
data.quotation_number = "2024-001"

arabic_file, english_file = generate_quotations(data)
```

### مثال 2: تغيير السعر وشروط الدفع

```python
from quotation_generator import QuotationData, generate_quotations

data = QuotationData()
data.total_price = "5,000,000"
data.down_payment_percent = "50"
data.down_payment_amount = "2,500,000"
data.before_shipping_percent = "25"
data.before_shipping_amount = "1,250,000"
data.before_delivery_percent = "25"
data.before_delivery_amount = "1,250,000"

arabic_file, english_file = generate_quotations(data)
```

### مثال 3: تغيير مواصفات الماكينة

```python
from quotation_generator import QuotationData, generate_quotations

data = QuotationData()
data.machine_model = "SH6-1200CC/D"
data.colors_count = "6"
data.machine_width = "120"
data.max_film_width = "1250"
data.max_printing_width = "1160"

arabic_file, english_file = generate_quotations(data)
```

---

## نصائح للصيانة

### 1. إضافة حقل جديد

لإضافة حقل جديد للبيانات:

1. أضفه في `QuotationData.__init__()`:
```python
def __init__(self):
    # ... الحقول الموجودة
    self.new_field_ar = "القيمة بالعربي"
    self.new_field_en = "Value in English"
```

2. استخدمه في دالة الإنشاء:
```python
c.drawString(2*cm, y_position, data.new_field_en)
```

### 2. تعديل التصميم

لتعديل الألوان، الخطوط، أو المسافات:

```python
# تغيير لون الخط الذهبي
c.setStrokeColor(colors.HexColor("#FFD700"))  # غيّر هذا اللون

# تغيير حجم الخط
c.setFont("Helvetica-Bold", 14)  # غيّر الحجم

# تغيير المسافات
y_position -= 0.5*cm  # غيّر المسافة
```

### 3. إضافة صفحة جديدة

```python
# في نهاية الصفحة
draw_footer(c, page_num, is_arabic=False)
c.showPage()
page_num += 1

# بداية صفحة جديدة
y_position = draw_header(c, data, is_arabic=False)
```

---

## استكشاف الأخطاء

### المشكلة: النص العربي لا يظهر بشكل صحيح

**الحل**: ثبّت المكتبات الاختيارية:
```bash
pip install arabic-reshaper python-bidi --break-system-packages
```

### المشكلة: الخط العربي لا يظهر

**الحل**: تأكد من وجود خط عربي في النظام:
```python
# في generate_quotations()
pdfmetrics.registerFont(TTFont('Arabic', 'path/to/arabic/font.ttf'))
```

### المشكلة: الصفحة ممتلئة والنص يتجاوز الحدود

**الحل**: أضف فحص لنهاية الصفحة:
```python
if y_position < 3*cm:
    draw_footer(c, page_num, is_arabic=False)
    c.showPage()
    page_num += 1
    y_position = draw_header(c, data, is_arabic=False)
```

---

## التكامل مع Anvil

### الخطوة 1: رفع الملف إلى Anvil

1. افتح مشروعك في Anvil
2. اذهب إلى Server Modules
3. أضف ملف Python جديد
4. انسخ محتوى `quotation_generator.py`

### الخطوة 2: إنشاء دالة Server Callable

```python
@anvil.server.callable
def generate_quotation(client_data):
    from quotation_generator import QuotationData, generate_quotations
    
    data = QuotationData()
    # املأ البيانات من client_data
    
    return generate_quotations(data)
```

### الخطوة 3: الاستدعاء من Client

```python
# في Client Code
arabic_pdf, english_pdf = anvil.server.call('generate_quotation', {
    'client_name_ar': 'اسم العميل',
    'total_price': '2000000',
    # ... باقي البيانات
})
```

---

## الترخيص والدعم

هذا الكود مفتوح المصدر ومتاح للاستخدام والتعديل.

للاستفسارات أو الدعم:
- راجع التعليقات داخل الكود
- جميع التعليقات بالعربي لسهولة الفهم

---

## التحديثات المستقبلية

خطط التطوير:
- [ ] إضافة دعم لصور الشركة (Logo)
- [ ] إضافة رموز QR
- [ ] دعم ملفات Excel كمدخلات
- [ ] واجهة ويب بسيطة
- [ ] قوالب متعددة

---

**تم بناؤه بواسطة Claude - 2026**

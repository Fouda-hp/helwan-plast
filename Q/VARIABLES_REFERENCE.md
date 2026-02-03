# 📋 مرجع المتغيرات - Variables Reference

## نظرة عامة

هذا الملف يحتوي على قائمة شاملة بجميع المتغيرات القابلة للتعديل في مولد عروض الأسعار.  
**كل المتغيرات موجودة في كلاس `QuotationData` في ملف `quotation_generator.py`**

---

## 🏢 بيانات الشركة - Company Information

### `company_name_ar`
- **النوع**: str
- **الافتراضي**: `"شركة حلوان بلاست ذ.م.م"`
- **الوصف**: اسم الشركة بالعربية
- **مثال**: `data.company_name_ar = "شركة التقنية المتقدمة"`

### `company_name_en`
- **النوع**: str
- **الافتراضي**: `"Helwan Plast LLC"`
- **الوصف**: اسم الشركة بالإنجليزية
- **مثال**: `data.company_name_en = "Advanced Tech LLC"`

### `company_address_ar`
- **النوع**: str
- **الافتراضي**: `"المنطقة الصناعية الثانية - قطعة ٢٠"`
- **الوصف**: عنوان الشركة بالعربية
- **مثال**: `data.company_address_ar = "المنطقة الصناعية الخامسة - قطعة 15"`

### `company_address_en`
- **النوع**: str
- **الافتراضي**: `"Second Industrial Zone – Plot 20"`
- **الوصف**: عنوان الشركة بالإنجليزية
- **مثال**: `data.company_address_en = "Fifth Industrial Zone – Plot 15"`

### `company_phone`
- **النوع**: str
- **الافتراضي**: `"01050332771"`
- **الوصف**: رقم هاتف الشركة
- **مثال**: `data.company_phone = "01234567890"`

### `company_email`
- **النوع**: str
- **الافتراضي**: `"sales@helwanplast.com"`
- **الوصف**: البريد الإلكتروني للشركة
- **مثال**: `data.company_email = "info@mycompany.com"`

### `company_website`
- **النوع**: str
- **الافتراضي**: `"www.helwanplast.com"`
- **الوصف**: موقع الشركة الإلكتروني
- **مثال**: `data.company_website = "www.advancedtech.com"`

---

## 👤 بيانات العميل - Client Information

### `client_name_ar`
- **النوع**: str
- **الافتراضي**: `"محمود - حكيم بلاست"`
- **الوصف**: اسم العميل بالعربية
- **مثال**: `data.client_name_ar = "شركة النور للتجارة"`

### `client_name_en`
- **النوع**: str
- **الافتراضي**: `"Mahmoud - Hakim Plast"`
- **الوصف**: اسم العميل بالإنجليزية
- **مثال**: `data.client_name_en = "Al Nour Trading Co."`

---

## 📄 بيانات عرض السعر - Quotation Information

### `quotation_number`
- **النوع**: str
- **الافتراضي**: `"5"`
- **الوصف**: رقم عرض السعر
- **مثال**: `data.quotation_number = "2024-001"`

### `quotation_date`
- **النوع**: str
- **الافتراضي**: `"15 مايو"`
- **الوصف**: تاريخ عرض السعر بالعربية
- **مثال**: `data.quotation_date = "١ فبراير"`

### `quotation_date_en`
- **النوع**: str
- **الافتراضي**: `"15 May"`
- **الوصف**: تاريخ عرض السعر بالإنجليزية
- **مثال**: `data.quotation_date_en = "1 February"`

### `quotation_location`
- **النوع**: str
- **الافتراضي**: `"القاهرة"`
- **الوصف**: موقع إصدار عرض السعر بالعربية
- **مثال**: `data.quotation_location = "الإسكندرية"`

### `quotation_location_en`
- **النوع**: str
- **الافتراضي**: `"Cairo"`
- **الوصف**: موقع إصدار عرض السعر بالإنجليزية
- **مثال**: `data.quotation_location_en = "Alexandria"`

---

## 🔧 مواصفات الماكينة الأساسية - Basic Machine Specifications

### `machine_model`
- **النوع**: str
- **الافتراضي**: `"SH4-1000CC/D"`
- **الوصف**: موديل الماكينة
- **مثال**: `data.machine_model = "SH6-1200CC/D"`

### `country_origin_ar`
- **النوع**: str
- **الافتراضي**: `"الصين"`
- **الوصف**: بلد المنشأ بالعربية
- **مثال**: `data.country_origin_ar = "ألمانيا"`

### `country_origin_en`
- **النوع**: str
- **الافتراضي**: `"China"`
- **الوصف**: بلد المنشأ بالإنجليزية
- **مثال**: `data.country_origin_en = "Germany"`

### `colors_count`
- **النوع**: str
- **الافتراضي**: `"4"`
- **الوصف**: عدد الألوان
- **مثال**: `data.colors_count = "6"`

### `winder_type_ar`
- **النوع**: str
- **الافتراضي**: `"وحدة فرد وإعادة لف مزدوجة"`
- **الوصف**: نوع الوندر بالعربية
- **مثال**: `data.winder_type_ar = "وحدة فرد منفردة"`

### `winder_type_en`
- **النوع**: str
- **الافتراضي**: `"Double winder"`
- **الوصف**: نوع الوندر بالإنجليزية
- **مثال**: `data.winder_type_en = "Single winder"`

### `winder_position_ar`
- **النوع**: str
- **الافتراضي**: `"مركزي"`
- **الوصف**: موضع الوندر بالعربية
- **مثال**: `data.winder_position_ar = "جانبي"`

### `winder_position_en`
- **النوع**: str
- **الافتراضي**: `"Central"`
- **الوصف**: موضع الوندر بالإنجليزية
- **مثال**: `data.winder_position_en = "Side"`

### `machine_width`
- **النوع**: str
- **الافتراضي**: `"100"`
- **الوصف**: عرض الماكينة بالسنتيمتر
- **مثال**: `data.machine_width = "120"`

---

## ⚙️ المواصفات الفنية التفصيلية - Detailed Technical Specifications

### `printing_colors`
- **النوع**: str
- **الافتراضي**: `"4+0, 3+1, 2+2 reverse printing"`
- **الوصف**: أوضاع الطباعة المتاحة
- **مثال**: `data.printing_colors = "6+0, 5+1, 4+2"`

### `printing_sides`
- **النوع**: str
- **الافتراضي**: `"2"`
- **الوصف**: عدد أوجه الطباعة
- **مثال**: `data.printing_sides = "1"`

### `tension_control_units`
- **النوع**: str
- **الافتراضي**: `"4"`
- **الوصف**: عدد وحدات التحكم في الشد
- **مثال**: `data.tension_control_units = "6"`

### `brake_system`
- **النوع**: str
- **الافتراضي**: `"4"`
- **الوصف**: عدد وحدات نظام الفرامل
- **مثال**: `data.brake_system = "6"`

### `brake_power`
- **النوع**: str
- **الافتراضي**: `"2 pc (10kg) + 2 pc (5kg)"`
- **الوصف**: قدرة الفرامل
- **مثال**: `data.brake_power = "4 pc (15kg)"`

### `web_guiding_system`
- **النوع**: str
- **الافتراضي**: `"2 pcs"`
- **الوصف**: عدد وحدات نظام المحاذاة
- **مثال**: `data.web_guiding_system = "3 pcs"`

### `max_film_width`
- **النوع**: str
- **الافتراضي**: `"1050"`
- **الوصف**: أقصى عرض للفيلم بالمليمتر
- **مثال**: `data.max_film_width = "1250"`

### `max_printing_width`
- **النوع**: str
- **الافتراضي**: `"960"`
- **الوصف**: أقصى عرض للطباعة بالمليمتر
- **مثال**: `data.max_printing_width = "1160"`

### `min_max_printing_length`
- **النوع**: str
- **الافتراضي**: `"300mm-1300mm"`
- **الوصف**: أقل وأقصى طول للطباعة
- **مثال**: `data.min_max_printing_length = "250mm-1500mm"`

### `max_roll_diameter`
- **النوع**: str
- **الافتراضي**: `"800"`
- **الوصف**: أقصى قطر للبكر بالمليمتر
- **مثال**: `data.max_roll_diameter = "1000"`

### `anilox_type_ar`
- **النوع**: str
- **الافتراضي**: `"انيلوكس سيراميك"`
- **الوصف**: نوع الانيلوكس بالعربية
- **مثال**: `data.anilox_type_ar = "انيلوكس معدني"`

### `anilox_type_en`
- **النوع**: str
- **الافتراضي**: `"Ceramic anilox"`
- **الوصف**: نوع الانيلوكس بالإنجليزية
- **مثال**: `data.anilox_type_en = "Metal anilox"`

### `max_machine_speed`
- **النوع**: str
- **الافتراضي**: `"120"`
- **الوصف**: أقصى سرعة للماكينة بالمتر/دقيقة
- **مثال**: `data.max_machine_speed = "150"`

### `max_printing_speed`
- **النوع**: str
- **الافتراضي**: `"100"`
- **الوصف**: أقصى سرعة طباعة بالمتر/دقيقة
- **مثال**: `data.max_printing_speed = "120"`

### `dryer_capacity`
- **النوع**: str
- **الافتراضي**: `"2.2kw air blower *2 unit"`
- **الوصف**: قدرة المجفف
- **مثال**: `data.dryer_capacity = "3.0kw air blower *2 unit"`

### `power_transmission_ar`
- **النوع**: str
- **الافتراضي**: `"Belt drive"`
- **الوصف**: طريقة نقل الحركة بالعربية
- **مثال**: `data.power_transmission_ar = "Gear drive"`

### `power_transmission_en`
- **النوع**: str
- **الافتراضي**: `"Belt drive"`
- **الوصف**: طريقة نقل الحركة بالإنجليزية
- **مثال**: `data.power_transmission_en = "Gear drive"`

### `main_motor_power`
- **النوع**: str
- **الافتراضي**: `"5"`
- **الوصف**: قدرة الموتور الرئيسي بالحصان
- **مثال**: `data.main_motor_power = "7.5"`

---

## 📊 سلندرات الطباعة - Printing Cylinders

### `printing_cylinders`
- **النوع**: list of dict
- **الافتراضي**: 
```python
[
    {"size": "25", "count": "4"},
    {"size": "30", "count": "4"},
    {"size": "35", "count": "4"},
    {"size": "40", "count": "4"},
    {"size": "45", "count": "4"},
    {"size": "50", "count": "4"},
    {"size": "60", "count": "4"},
]
```
- **الوصف**: قائمة بمقاسات وأعداد سلندرات الطباعة
- **مثال**: 
```python
data.printing_cylinders = [
    {"size": "20", "count": "4"},
    {"size": "28", "count": "4"},
    {"size": "35", "count": "4"},
]
```

---

## 💰 الأسعار وشروط الدفع - Pricing and Payment Terms

### `total_price`
- **النوع**: str
- **الافتراضي**: `"2,150,000"`
- **الوصف**: السعر الإجمالي بالجنيه المصري
- **مثال**: `data.total_price = "5,000,000"`
- **ملاحظة**: استخدم الفواصل للآلاف

### `down_payment_percent`
- **النوع**: str
- **الافتراضي**: `"40"`
- **الوصف**: نسبة المقدم من السعر
- **مثال**: `data.down_payment_percent = "50"`

### `down_payment_amount`
- **النوع**: str
- **الافتراضي**: `"860,000"`
- **الوصف**: مبلغ المقدم بالجنيه
- **مثال**: `data.down_payment_amount = "2,500,000"`
- **ملاحظة**: يجب أن يتطابق مع النسبة

### `before_shipping_percent`
- **النوع**: str
- **الافتراضي**: `"30"`
- **الوصف**: نسبة الدفعة قبل الشحن
- **مثال**: `data.before_shipping_percent = "25"`

### `before_shipping_amount`
- **النوع**: str
- **الافتراضي**: `"645,000"`
- **الوصف**: مبلغ الدفعة قبل الشحن
- **مثال**: `data.before_shipping_amount = "1,250,000"`

### `before_delivery_percent`
- **النوع**: str
- **الافتراضي**: `"30"`
- **الوصف**: نسبة الدفعة قبل التسليم
- **مثال**: `data.before_delivery_percent = "25"`

### `before_delivery_amount`
- **النوع**: str
- **الافتراضي**: `"645,000"`
- **الوصف**: مبلغ الدفعة قبل التسليم
- **مثال**: `data.before_delivery_amount = "1,250,000"`

---

## 🚚 التسليم - Delivery

### `delivery_location_ar`
- **النوع**: str
- **الافتراضي**: `"العاشر من رمضان"`
- **الوصف**: مكان التسليم بالعربية
- **مثال**: `data.delivery_location_ar = "المنطقة الصناعية السادسة"`

### `delivery_location_en`
- **النوع**: str
- **الافتراضي**: `"10th of Ramadan City"`
- **الوصف**: مكان التسليم بالإنجليزية
- **مثال**: `data.delivery_location_en = "6th Industrial Zone"`

### `delivery_time_ar`
- **النوع**: str
- **الافتراضي**: `"يتم تحديده لاحقاً"`
- **الوصف**: وقت التسليم المتوقع بالعربية
- **مثال**: `data.delivery_time_ar = "90 يوم من تاريخ التعاقد"`

### `delivery_time_en`
- **النوع**: str
- **الافتراضي**: `"To be determined"`
- **الوصف**: وقت التسليم المتوقع بالإنجليزية
- **مثال**: `data.delivery_time_en = "90 days from contract date"`

---

## 🛡️ الضمان - Warranty

### `warranty_period`
- **النوع**: str
- **الافتراضي**: `"12"`
- **الوصف**: فترة الضمان بالأشهر
- **مثال**: `data.warranty_period = "24"`

---

## ⏰ صلاحية العرض - Quotation Validity

### `validity_days`
- **النوع**: str
- **الافتراضي**: `"15"`
- **الوصف**: عدد أيام صلاحية عرض السعر
- **مثال**: `data.validity_days = "30"`

---

## 📝 أمثلة سريعة

### مثال 1: تغيير بيانات أساسية
```python
data = QuotationData()
data.client_name_ar = "شركة جديدة"
data.quotation_number = "2024-100"
data.total_price = "3,000,000"
```

### مثال 2: تغيير مواصفات الماكينة
```python
data = QuotationData()
data.machine_model = "SH6-1200CC/D"
data.colors_count = "6"
data.max_machine_speed = "150"
```

### مثال 3: تغيير شروط الدفع
```python
data = QuotationData()
data.down_payment_percent = "50"
data.down_payment_amount = "1,500,000"
data.before_shipping_percent = "25"
data.before_shipping_amount = "750,000"
```

---

## 💡 نصائح

1. **استخدم الفواصل**: عند كتابة الأرقام الكبيرة، استخدم الفواصل (مثل: `"2,150,000"`)

2. **التناسق**: تأكد من تطابق النسب المئوية مع المبالغ:
   ```python
   # صحيح
   data.total_price = "1,000,000"
   data.down_payment_percent = "40"
   data.down_payment_amount = "400,000"  # 40% من مليون
   ```

3. **الترجمة**: عند تغيير قيمة، غيّر النسخة العربية والإنجليزية معاً:
   ```python
   data.client_name_ar = "شركة النور"
   data.client_name_en = "Al Nour Company"
   ```

4. **السلندرات**: يمكنك إضافة أو حذف مقاسات حسب الحاجة:
   ```python
   data.printing_cylinders = [
       {"size": "25", "count": "2"},  # عدد أقل
       {"size": "30", "count": "6"},  # عدد أكثر
   ]
   ```

---

## 🔍 البحث السريع

للبحث عن متغير معين:
- في ويندوز: اضغط `Ctrl + F`
- في ماك: اضغط `Cmd + F`
- ابحث عن اسم المتغير أو وصفه

---

**آخر تحديث**: فبراير 2026

"""
أمثلة استخدام مولد عروض الأسعار
==================================

هذا الملف يحتوي على أمثلة عملية لكيفية استخدام quotation_generator
"""

from quotation_generator import QuotationData, generate_quotations


# ==============================================================================
# مثال 1: الاستخدام الأساسي مع البيانات الافتراضية
# ==============================================================================

def example_1_basic_usage():
    """
    أبسط طريقة للاستخدام - إنشاء عروض أسعار بالبيانات الافتراضية
    """
    print("="*60)
    print("مثال 1: الاستخدام الأساسي")
    print("="*60)
    
    arabic_file, english_file = generate_quotations()
    
    print(f"\n✓ تم إنشاء عرض السعر بالعربية: {arabic_file}")
    print(f"✓ تم إنشاء عرض السعر بالإنجليزية: {english_file}")


# ==============================================================================
# مثال 2: تخصيص بيانات العميل
# ==============================================================================

def example_2_custom_client():
    """
    تغيير بيانات العميل فقط
    """
    print("\n" + "="*60)
    print("مثال 2: تخصيص بيانات العميل")
    print("="*60)
    
    # إنشاء كائن البيانات
    data = QuotationData()
    
    # تعديل بيانات العميل
    data.client_name_ar = "شركة النور للتجارة والصناعة"
    data.client_name_en = "Al Nour Trading and Industry Co."
    data.quotation_number = "2024-001"
    
    # إنشاء عروض الأسعار
    arabic_file, english_file = generate_quotations(data)
    
    print(f"\n✓ تم إنشاء عرض سعر للعميل: {data.client_name_ar}")
    print(f"✓ رقم العرض: {data.quotation_number}")


# ==============================================================================
# مثال 3: تخصيص السعر وشروط الدفع
# ==============================================================================

def example_3_custom_pricing():
    """
    تعديل السعر وشروط الدفع
    """
    print("\n" + "="*60)
    print("مثال 3: تخصيص السعر وشروط الدفع")
    print("="*60)
    
    data = QuotationData()
    
    # تغيير السعر الإجمالي
    data.total_price = "5,000,000"
    
    # تغيير شروط الدفع (50% - 25% - 25%)
    data.down_payment_percent = "50"
    data.down_payment_amount = "2,500,000"
    data.before_shipping_percent = "25"
    data.before_shipping_amount = "1,250,000"
    data.before_delivery_percent = "25"
    data.before_delivery_amount = "1,250,000"
    
    arabic_file, english_file = generate_quotations(data)
    
    print(f"\n✓ السعر الإجمالي: {data.total_price} جنيه")
    print(f"✓ مقدم: {data.down_payment_percent}% ({data.down_payment_amount} جنيه)")


# ==============================================================================
# مثال 4: تخصيص مواصفات الماكينة
# ==============================================================================

def example_4_custom_machine():
    """
    تعديل مواصفات الماكينة
    """
    print("\n" + "="*60)
    print("مثال 4: تخصيص مواصفات الماكينة")
    print("="*60)
    
    data = QuotationData()
    
    # تغيير موديل الماكينة
    data.machine_model = "SH6-1200CC/D"
    data.colors_count = "6"
    data.machine_width = "120"
    
    # تغيير المواصفات الفنية
    data.max_film_width = "1250"
    data.max_printing_width = "1160"
    data.max_machine_speed = "150"
    data.max_printing_speed = "120"
    
    arabic_file, english_file = generate_quotations(data)
    
    print(f"\n✓ الموديل: {data.machine_model}")
    print(f"✓ عدد الألوان: {data.colors_count}")
    print(f"✓ العرض: {data.machine_width} سم")


# ==============================================================================
# مثال 5: تخصيص شامل (جميع البيانات)
# ==============================================================================

def example_5_full_customization():
    """
    تخصيص شامل لجميع البيانات
    """
    print("\n" + "="*60)
    print("مثال 5: تخصيص شامل")
    print("="*60)
    
    data = QuotationData()
    
    # بيانات الشركة
    data.company_name_ar = "شركة التقنية المتقدمة ذ.م.م"
    data.company_name_en = "Advanced Technology LLC"
    data.company_phone = "01234567890"
    data.company_email = "info@advtech.com"
    
    # بيانات العميل
    data.client_name_ar = "مصنع الأمل للبلاستيك"
    data.client_name_en = "Al Amal Plastic Factory"
    
    # بيانات عرض السعر
    data.quotation_number = "ADV-2024-055"
    data.quotation_date = "١ فبراير"
    data.quotation_date_en = "1 February"
    
    # مواصفات الماكينة
    data.machine_model = "SH8-1500CC/D"
    data.colors_count = "8"
    data.machine_width = "150"
    
    # السعر
    data.total_price = "8,500,000"
    data.down_payment_amount = "2,550,000"
    data.before_shipping_amount = "2,975,000"
    data.before_delivery_amount = "2,975,000"
    
    # التسليم
    data.delivery_location_ar = "المنطقة الصناعية السادسة"
    data.delivery_location_en = "6th Industrial Zone"
    data.delivery_time_ar = "90 يوم من تاريخ التعاقد"
    data.delivery_time_en = "90 days from contract date"
    
    arabic_file, english_file = generate_quotations(data)
    
    print(f"\n✓ تم إنشاء عرض سعر كامل ومخصص")
    print(f"✓ الشركة: {data.company_name_ar}")
    print(f"✓ العميل: {data.client_name_ar}")
    print(f"✓ رقم العرض: {data.quotation_number}")


# ==============================================================================
# مثال 6: إنشاء عدة عروض أسعار دفعة واحدة
# ==============================================================================

def example_6_batch_generation():
    """
    إنشاء عدة عروض أسعار لعملاء مختلفين
    """
    print("\n" + "="*60)
    print("مثال 6: إنشاء عدة عروض أسعار")
    print("="*60)
    
    # قائمة العملاء
    clients = [
        {
            "name_ar": "شركة الفجر",
            "name_en": "Al Fajr Company",
            "quote_num": "2024-100",
            "price": "2,000,000"
        },
        {
            "name_ar": "مصنع الرواد",
            "name_en": "Al Rowad Factory",
            "quote_num": "2024-101",
            "price": "2,500,000"
        },
        {
            "name_ar": "شركة المستقبل",
            "name_en": "Al Mostaqbal Co.",
            "quote_num": "2024-102",
            "price": "3,000,000"
        }
    ]
    
    # إنشاء عرض سعر لكل عميل
    for i, client in enumerate(clients, 1):
        print(f"\nجاري إنشاء عرض رقم {i} من {len(clients)}...")
        
        data = QuotationData()
        data.client_name_ar = client["name_ar"]
        data.client_name_en = client["name_en"]
        data.quotation_number = client["quote_num"]
        data.total_price = client["price"]
        
        # حساب شروط الدفع بناءً على السعر
        total = int(client["price"].replace(",", ""))
        data.down_payment_amount = f"{int(total * 0.4):,}"
        data.before_shipping_amount = f"{int(total * 0.3):,}"
        data.before_delivery_amount = f"{int(total * 0.3):,}"
        
        arabic_file, english_file = generate_quotations(data)
        
        print(f"  ✓ {client['name_ar']} - رقم العرض: {client['quote_num']}")


# ==============================================================================
# مثال 7: استخدام في دالة (مثل Anvil Server Function)
# ==============================================================================

def create_quotation_for_client(client_data):
    """
    دالة يمكن استخدامها كـ Server Callable في Anvil
    
    Parameters:
    -----------
    client_data : dict
        قاموس يحتوي على بيانات العميل
        
    Returns:
    --------
    tuple : (arabic_file, english_file)
        مسارات ملفات PDF
    """
    # إنشاء كائن البيانات
    data = QuotationData()
    
    # تعبئة البيانات من القاموس
    # استخدام .get() للحصول على القيمة الافتراضية إذا لم تكن موجودة
    data.client_name_ar = client_data.get('client_name_ar', data.client_name_ar)
    data.client_name_en = client_data.get('client_name_en', data.client_name_en)
    data.quotation_number = client_data.get('quotation_number', data.quotation_number)
    data.total_price = client_data.get('total_price', data.total_price)
    data.machine_model = client_data.get('machine_model', data.machine_model)
    
    # يمكن إضافة المزيد من الحقول حسب الحاجة
    
    # إنشاء عروض الأسعار
    return generate_quotations(data)


def example_7_function_usage():
    """
    مثال على استخدام الدالة المخصصة
    """
    print("\n" + "="*60)
    print("مثال 7: استخدام دالة مخصصة")
    print("="*60)
    
    # بيانات العميل (كما لو جاءت من نموذج Anvil)
    client_info = {
        'client_name_ar': 'شركة الأهرام للصناعات',
        'client_name_en': 'Al Ahram Industries',
        'quotation_number': 'AH-2024-001',
        'total_price': '4,200,000',
        'machine_model': 'SH5-1100CC/D'
    }
    
    # إنشاء عروض الأسعار
    arabic_file, english_file = create_quotation_for_client(client_info)
    
    print(f"\n✓ تم إنشاء عرض السعر من خلال الدالة المخصصة")
    print(f"✓ العميل: {client_info['client_name_ar']}")


# ==============================================================================
# مثال 8: تخصيص سلندرات الطباعة
# ==============================================================================

def example_8_custom_cylinders():
    """
    تخصيص عدد ومقاسات سلندرات الطباعة
    """
    print("\n" + "="*60)
    print("مثال 8: تخصيص سلندرات الطباعة")
    print("="*60)
    
    data = QuotationData()
    
    # إنشاء قائمة مخصصة من السلندرات
    data.printing_cylinders = [
        {"size": "20", "count": "4"},
        {"size": "25", "count": "4"},
        {"size": "28", "count": "4"},
        {"size": "32", "count": "4"},
        {"size": "38", "count": "4"},
        {"size": "42", "count": "4"},
        {"size": "48", "count": "4"},
        {"size": "55", "count": "4"},
        {"size": "65", "count": "4"},
    ]
    
    arabic_file, english_file = generate_quotations(data)
    
    print(f"\n✓ تم إنشاء عرض سعر بـ {len(data.printing_cylinders)} مقاس سلندر")


# ==============================================================================
# الدالة الرئيسية - تشغيل جميع الأمثلة
# ==============================================================================

def run_all_examples():
    """
    تشغيل جميع الأمثلة بالتتابع
    """
    print("\n" + "🚀 " + "="*58)
    print("تشغيل جميع أمثلة مولد عروض الأسعار")
    print("="*60 + "\n")
    
    try:
        example_1_basic_usage()
        example_2_custom_client()
        example_3_custom_pricing()
        example_4_custom_machine()
        example_5_full_customization()
        example_6_batch_generation()
        example_7_function_usage()
        example_8_custom_cylinders()
        
        print("\n" + "="*60)
        print("✅ تم تنفيذ جميع الأمثلة بنجاح!")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ حدث خطأ: {str(e)}")
        import traceback
        traceback.print_exc()


# ==============================================================================
# نقطة الدخول
# ==============================================================================

if __name__ == "__main__":
    """
    عند تشغيل هذا الملف مباشرة، سيتم تنفيذ جميع الأمثلة
    
    لتشغيل مثال واحد فقط:
    python example_usage.py
    
    ثم في Python Console:
    >>> from example_usage import example_1_basic_usage
    >>> example_1_basic_usage()
    """
    
    # تشغيل جميع الأمثلة
    run_all_examples()
    
    # أو يمكنك تشغيل مثال واحد فقط:
    # example_1_basic_usage()
    # example_5_full_customization()

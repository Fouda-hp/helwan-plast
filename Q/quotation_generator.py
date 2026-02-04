"""
مولد عروض الأسعار - Quotation Generator
========================================
هذا الملف يقوم بإنشاء عروض أسعار احترافية بالعربية والإنجليزية
للاستخدام مع Anvil أو أي نظام آخر

المتطلبات:
- reportlab فقط
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from datetime import datetime

# محاولة استيراد مكتبات العربي، إذا لم تكن موجودة نستخدم بديل
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    ARABIC_SUPPORT = True
except ImportError:
    ARABIC_SUPPORT = False
    print("تحذير: مكتبات العربي غير متوفرة. سيتم استخدام نسخة مبسطة.")


# ==============================================================================
# قسم المتغيرات - Variables Section
# ==============================================================================
# هنا تضع كل المتغيرات اللي هتتغير من عرض سعر للتاني
# يمكنك تعديل القيم هنا بسهولة أو استقبالها من Anvil

class QuotationData:
    """
    كلاس يحتوي على جميع بيانات عرض السعر
    يمكن تعديل القيم هنا أو استقبالها من الخارج
    """
    
    def __init__(self):
        # ====================
        # بيانات الشركة
        # ====================
        self.company_name_ar = "شركة حلوان بلاست ذ.م.م"
        self.company_name_en = "Helwan Plast LLC"
        self.company_address_ar = "المنطقة الصناعية الثانية - قطعة ٢٠"
        self.company_address_en = "Second Industrial Zone – Plot 20"
        self.company_phone = "01050332771"
        self.company_email = "sales@helwanplast.com"
        self.company_website = "www.helwanplast.com"
        
        # ====================
        # بيانات العميل
        # ====================
        self.client_name_ar = "محمود - حكيم بلاست"
        self.client_name_en = "Mahmoud - Hakim Plast"
        
        # ====================
        # بيانات عرض السعر
        # ====================
        self.quotation_number = "5"
        self.quotation_date = "15 مايو"  # للعربي
        self.quotation_date_en = "15 May"  # للإنجليزي
        self.quotation_location = "القاهرة"
        self.quotation_location_en = "Cairo"
        
        # ====================
        # مواصفات الماكينة
        # ====================
        self.machine_model = "SH4-1000CC/D"
        self.country_origin_ar = "الصين"
        self.country_origin_en = "China"
        self.colors_count = "4"
        self.winder_type_ar = "وحدة فرد وإعادة لف مزدوجة"
        self.winder_type_en = "Double winder"
        self.winder_position_ar = "مركزي"
        self.winder_position_en = "Central"
        self.machine_width = "100"  # سم
        
        # ====================
        # المواصفات الفنية
        # ====================
        self.printing_colors = "4+0, 3+1, 2+2 reverse printing"
        self.printing_sides = "2"
        self.tension_control_units = "4"
        self.brake_system = "4"
        self.brake_power = "2 pc (10kg) + 2 pc (5kg)"
        self.web_guiding_system = "2 pcs"
        self.max_film_width = "1050"  # MM
        self.max_printing_width = "960"  # MM
        self.min_max_printing_length = "300mm-1300mm"
        self.max_roll_diameter = "800"  # MM
        self.anilox_type_ar = "انيلوكس سيراميك"
        self.anilox_type_en = "Ceramic anilox"
        self.max_machine_speed = "120"  # m/min
        self.max_printing_speed = "100"  # m/min
        self.dryer_capacity = "2.2kw air blower *2 unit"
        self.power_transmission_ar = "Belt drive"
        self.power_transmission_en = "Belt drive"
        self.main_motor_power = "5"  # HP
        
        # ====================
        # سلندرات الطباعة
        # ====================
        self.printing_cylinders = [
            {"size": "25", "count": "4"},
            {"size": "30", "count": "4"},
            {"size": "35", "count": "4"},
            {"size": "40", "count": "4"},
            {"size": "45", "count": "4"},
            {"size": "50", "count": "4"},
            {"size": "60", "count": "4"},
        ]
        
        # ====================
        # الأسعار والدفع
        # ====================
        self.total_price = "2,150,000"  # جنيه
        self.down_payment_percent = "40"
        self.down_payment_amount = "860,000"
        self.before_shipping_percent = "30"
        self.before_shipping_amount = "645,000"
        self.before_delivery_percent = "30"
        self.before_delivery_amount = "645,000"
        
        # ====================
        # التسليم
        # ====================
        self.delivery_location_ar = "العاشر من رمضان"
        self.delivery_location_en = "10th of Ramadan City"
        self.delivery_time_ar = "يتم تحديده لاحقاً"
        self.delivery_time_en = "To be determined"
        
        # ====================
        # الضمان
        # ====================
        self.warranty_period = "12"  # شهر
        
        # ====================
        # صلاحية العرض
        # ====================
        self.validity_days = "15"


# ==============================================================================
# دوال المساعدة - Helper Functions
# ==============================================================================

def prepare_arabic_text(text):
    """
    تجهيز النص العربي للعرض بشكل صحيح في PDF
    """
    if not text:
        return ""
    
    if ARABIC_SUPPORT:
        reshaped_text = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped_text)
        return bidi_text
    else:
        # نسخة مبسطة بدون إعادة تشكيل - للاختبار فقط
        # في الإنتاج، يفضل تثبيت المكتبات
        return text


def draw_header(c, data, is_arabic=True):
    """
    رسم ترويسة عرض السعر
    """
    width, height = A4
    
    if is_arabic:
        # الترويسة بالعربي
        c.setFont("Arabic", 10)
        
        # التاريخ والموقع (يمين الصفحة)
        location_date = f"{data.quotation_location} / {data.quotation_date}"
        c.drawRightString(width - 2*cm, height - 2*cm, prepare_arabic_text(location_date))
        
        # العنوان (يمين الصفحة)
        address = prepare_arabic_text(data.company_address_ar)
        c.drawRightString(width - 2*cm, height - 2.5*cm, address)
        
        # رقم الهاتف
        c.drawRightString(width - 2*cm, height - 3*cm, data.company_phone)
        
        # البريد الإلكتروني
        c.setFont("Helvetica", 10)
        c.drawRightString(width - 2*cm, height - 3.5*cm, data.company_email)
        
        # اسم الشركة والموقع (يسار الصفحة)
        c.setFont("Arabic-Bold", 11)
        company_name = prepare_arabic_text(data.company_name_ar)
        c.drawString(2*cm, height - 2*cm, company_name)
        
        c.setFont("Helvetica", 10)
        c.drawString(2*cm, height - 2.5*cm, data.company_website)
        
        # خط فاصل
        c.setStrokeColor(colors.HexColor("#FFD700"))
        c.setLineWidth(2)
        c.line(2*cm, height - 4*cm, width - 2*cm, height - 4*cm)
        
        # عنوان عرض السعر
        c.setFont("Arabic-Bold", 14)
        quotation_title = prepare_arabic_text(f"عرض سعر رقم {data.quotation_number}")
        c.drawRightString(width - 2*cm, height - 5*cm, quotation_title)
        
        # اسم العميل
        c.setFont("Arabic", 11)
        client_line = prepare_arabic_text(f"السادة - شركة / {data.client_name_ar}")
        c.drawRightString(width - 2*cm, height - 6*cm, client_line)
        
        # التحية
        greeting = prepare_arabic_text("تحية طيبة وبعد،")
        c.drawRightString(width - 2*cm, height - 6.8*cm, greeting)
        
    else:
        # الترويسة بالإنجليزي
        c.setFont("Helvetica", 10)
        
        # التاريخ والموقع (يسار الصفحة)
        c.drawString(2*cm, height - 2*cm, f"{data.quotation_location_en} / {data.quotation_date_en}")
        
        # العنوان
        c.drawString(2*cm, height - 2.5*cm, data.company_address_en)
        
        # رقم الهاتف
        c.drawString(2*cm, height - 3*cm, data.company_phone)
        
        # البريد الإلكتروني
        c.drawString(2*cm, height - 3.5*cm, f"Email: {data.company_email}")
        
        # اسم الشركة والموقع (يمين الصفحة)
        c.setFont("Helvetica-Bold", 11)
        c.drawRightString(width - 2*cm, height - 2*cm, data.company_name_en)
        
        c.setFont("Helvetica", 10)
        c.drawRightString(width - 2*cm, height - 2.5*cm, f"Website: {data.company_website}")
        
        # خط فاصل
        c.setStrokeColor(colors.HexColor("#FFD700"))
        c.setLineWidth(2)
        c.line(2*cm, height - 4*cm, width - 2*cm, height - 4*cm)
        
        # عنوان عرض السعر
        c.setFont("Helvetica-Bold", 14)
        c.drawString(2*cm, height - 5*cm, f"Quotation No.: {data.quotation_number}")
        
        # اسم العميل
        c.setFont("Helvetica", 11)
        c.drawString(2*cm, height - 6*cm, f"Company / To: {data.client_name_en}")
        
        # التحية
        c.drawString(2*cm, height - 6.8*cm, "Dear Sir/Madam,")
    
    return height - 7.5*cm  # موقع Y للبدء في الكتابة بعد الترويسة


def draw_footer(c, page_num, is_arabic=True):
    """
    رسم تذييل الصفحة
    """
    width, height = A4
    
    # خط فاصل
    c.setStrokeColor(colors.HexColor("#FFD700"))
    c.setLineWidth(1)
    c.line(2*cm, 2*cm, width - 2*cm, 2*cm)
    
    # رقم الصفحة
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.grey)
    if is_arabic:
        page_text = prepare_arabic_text(f"صفحة {page_num}")
        c.drawCentredString(width/2, 1.5*cm, page_text)
    else:
        c.drawCentredString(width/2, 1.5*cm, f"Page {page_num}")


# ==============================================================================
# دوال إنشاء صفحات عرض السعر
# ==============================================================================

def create_english_quotation(filename, data):
    """
    إنشاء عرض السعر بالإنجليزية
    """
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    page_num = 1
    
    # ==================
    # الصفحة الأولى
    # ==================
    
    # رسم الترويسة
    y_position = draw_header(c, data, is_arabic=False)
    
    # المقدمة
    c.setFont("Helvetica", 10)
    intro = "We are pleased to submit our quotation for the following printing machine in accordance with"
    c.drawString(2*cm, y_position, intro)
    y_position -= 0.5*cm
    c.drawString(2*cm, y_position, "the specifications detailed below:")
    y_position -= 1*cm
    
    # تفاصيل الماكينة
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y_position, "Machine Details")
    y_position -= 0.7*cm
    
    c.setFont("Helvetica", 10)
    machine_details = [
        ("Machine Type:", "Flexo Stack With Ceramic anilox Chamber Doctor Blade"),
        ("Model:", data.machine_model),
        ("Country of Origin:", data.country_origin_en),
        ("Number of Colors:", data.colors_count),
        ("Winder:", data.winder_type_en),
        ("Winder Type:", data.winder_position_en),
        ("Machine Width:", f"{data.machine_width} CM"),
    ]
    
    for label, value in machine_details:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(2*cm, y_position, label)
        c.setFont("Helvetica", 10)
        c.drawString(5*cm, y_position, value)
        y_position -= 0.5*cm
    
    y_position -= 0.5*cm
    
    # المواصفات العامة
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y_position, "General Specifications:")
    y_position -= 0.7*cm
    
    c.setFont("Helvetica", 9)
    general_specs = [
        "1- Heavy-duty cast iron frame, stable and vibration-resistant",
        "2- Automatic web tension control units suitable for different material weights, thicknesses, and",
        "   flexibility, with manual adjustment option",
        "3- Web guiding (oscillating) units to ensure accurate print centering on the substrate and smooth",
        "   rewinding of printed material",
        "4- Rollers and cylinders laser-treated for heavy-duty operation and extended service life",
        "5- Separate rewind motors with independent control to allow operation with different flexibility",
        "   and thicknesses",
        "6- Air-shaft unwind/rewind cylinders, in addition to one extra mechanical shaft",
        "7- Double-sided printing capability",
        "8- Printing cylinder pressure applied via hydraulic oil system to avoid pneumatic issues",
        "9- Manual horizontal and vertical color registration adjustment during operation",
        "10- Integrated overhead lifting cranes to facilitate loading and unloading of rolls and cylinders",
    ]
    
    for spec in general_specs:
        c.drawString(2.3*cm, y_position, spec)
        y_position -= 0.4*cm
        
        if y_position < 3*cm:  # إذا وصلنا لنهاية الصفحة
            draw_footer(c, page_num, is_arabic=False)
            c.showPage()
            page_num += 1
            y_position = draw_header(c, data, is_arabic=False)
            c.setFont("Helvetica", 9)
    
    # المواصفات المتبقية
    remaining_specs = [
        "11- Suitable for solvent-based and water-based inks",
        "12- Delta (Taiwan) inverters",
        "13- Safety alarm before machine start-up to prevent injuries",
        "14- Hot air drying units with extended web path to ensure complete ink drying",
        "15- Power transmission from the main motor to machine components via Belt drive",
        "16- Integrated lubrication pumps to ensure balanced oil distribution to all components",
        "17- Automatic machine stop sensors in case of film breakage or material run-out",
    ]
    
    for spec in remaining_specs:
        c.drawString(2.3*cm, y_position, spec)
        y_position -= 0.4*cm
        
        if y_position < 3*cm:
            draw_footer(c, page_num, is_arabic=False)
            c.showPage()
            page_num += 1
            y_position = draw_header(c, data, is_arabic=False)
            c.setFont("Helvetica", 9)
    
    draw_footer(c, page_num, is_arabic=False)
    c.showPage()
    page_num += 1
    
    # ==================
    # الصفحة الثانية - المواصفات الفنية
    # ==================
    
    y_position = draw_header(c, data, is_arabic=False)
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y_position, "Technical Specifications:")
    y_position -= 1*cm
    
    c.setFont("Helvetica", 9)
    tech_specs = [
        ("1- Model", data.machine_model),
        ("2- Number of Colors", data.printing_colors),
        ("3- Printing Sides", data.printing_sides),
        ("4- Tension Control Units", f"{data.tension_control_units} PCS"),
        ("5- Brake System", f"{data.brake_system} PCS"),
        ("6- Brake Power", data.brake_power),
        ("7- Web Guiding System (Oscillating Type)", data.web_guiding_system),
        ("8- Maximum Film Width", f"{data.max_film_width} MM"),
        ("9- Maximum Printing Width", f"{data.max_printing_width} MM"),
        ("10- Minimum and Maximum Printing Length", data.min_max_printing_length),
        ("11- Maximum Roll Diameter", f"{data.max_roll_diameter} MM"),
        ("12- Anilox Type", data.anilox_type_en),
        ("13- Maximum Machine Speed", f"{data.max_machine_speed} m/min"),
        ("14- Maximum Printing Speed", f"{data.max_printing_speed} m/min"),
        ("15- Dryer Capacity", data.dryer_capacity),
        ("16- Power Transmission Method", data.power_transmission_en),
        ("17- Main Motor Power", f"{data.main_motor_power} HP"),
        ("18- Video inspection", "NO"),
        ("19- PLC", "NO"),
        ("20- Slitter", "NO"),
    ]
    
    for label, value in tech_specs:
        c.drawString(2.3*cm, y_position, label)
        c.drawString(10*cm, y_position, value)
        y_position -= 0.5*cm
        
        if y_position < 3*cm:
            draw_footer(c, page_num, is_arabic=False)
            c.showPage()
            page_num += 1
            y_position = draw_header(c, data, is_arabic=False)
            c.setFont("Helvetica", 9)
    
    y_position -= 1*cm
    
    # سلندرات الطباعة
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y_position, "Printing Cylinders:")
    y_position -= 0.8*cm
    
    # رأس الجدول
    c.setFont("Helvetica-Bold", 10)
    c.drawString(2.5*cm, y_position, "Size")
    c.drawString(6*cm, y_position, "Count")
    y_position -= 0.3*cm
    
    # خط تحت الرأس
    c.setLineWidth(0.5)
    c.line(2.3*cm, y_position, 8*cm, y_position)
    y_position -= 0.5*cm
    
    # البيانات
    c.setFont("Helvetica", 10)
    for i, cylinder in enumerate(data.printing_cylinders, 1):
        c.drawString(2.3*cm, y_position, f"{i}-")
        c.drawString(3*cm, y_position, cylinder["size"])
        c.drawString(6*cm, y_position, cylinder["count"])
        y_position -= 0.5*cm
    
    draw_footer(c, page_num, is_arabic=False)
    c.showPage()
    page_num += 1
    
    # ==================
    # الصفحة الثالثة - العرض المالي
    # ==================
    
    y_position = draw_header(c, data, is_arabic=False)
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y_position, "Financial Offer:")
    y_position -= 0.8*cm
    
    c.setFont("Helvetica", 10)
    c.drawString(2*cm, y_position, f"Machine price including printing cylinders: {data.total_price} EGP")
    y_position -= 0.5*cm
    c.drawString(2*cm, y_position, "The price includes: supply, installation, and warranty")
    y_position -= 1.2*cm
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y_position, "Payment Terms:")
    y_position -= 0.8*cm
    
    # جدول الدفع
    c.setFont("Helvetica-Bold", 10)
    c.drawString(2.5*cm, y_position, "Payment Stage")
    c.drawString(10*cm, y_position, "Percentage")
    c.drawString(13.5*cm, y_position, "Amount (EGP)")
    y_position -= 0.3*cm
    
    c.setLineWidth(0.5)
    c.line(2.3*cm, y_position, width - 2*cm, y_position)
    y_position -= 0.5*cm
    
    c.setFont("Helvetica", 10)
    payment_terms = [
        ("Down payment", f"{data.down_payment_percent}%", data.down_payment_amount),
        ("Payment before shipping", f"{data.before_shipping_percent}%", data.before_shipping_amount),
        ("Payment before delivery", f"{data.before_delivery_percent}%", data.before_delivery_amount),
    ]
    
    for stage, percent, amount in payment_terms:
        c.drawString(2.5*cm, y_position, stage)
        c.drawString(10*cm, y_position, percent)
        c.drawString(13.5*cm, y_position, amount)
        y_position -= 0.5*cm
    
    y_position -= 1*cm
    
    # التسليم
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y_position, "Delivery:")
    y_position -= 0.8*cm
    
    c.setFont("Helvetica", 10)
    c.drawString(2*cm, y_position, f"Place of delivery: {data.delivery_location_en}")
    y_position -= 0.5*cm
    c.drawString(2*cm, y_position, f"Expected delivery time: {data.delivery_time_en}")
    y_position -= 1.2*cm
    
    # الضمان
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y_position, "Warranty & After-Sales Service:")
    y_position -= 0.8*cm
    
    c.setFont("Helvetica", 10)
    warranty_text = f"The warranty is valid for {data.warranty_period} months against manufacturing defects, starting from the delivery"
    c.drawString(2*cm, y_position, warranty_text)
    y_position -= 0.5*cm
    c.drawString(2*cm, y_position, "date. The warranty does not cover consumable parts or misuse.")
    y_position -= 0.5*cm
    c.drawString(2*cm, y_position, "Full technical support with spare parts availability upon request")
    y_position -= 1.2*cm
    
    # ملاحظات
    c.setFont("Helvetica-Bold", 12)
    c.drawString(2*cm, y_position, "Notes:")
    y_position -= 0.8*cm
    
    c.setFont("Helvetica", 9)
    notes = [
        f"- This quotation is valid for {data.validity_days} days from the quotation date",
        "- The price may be adjusted in case of an increase in the USD exchange rate exceeding EGP 0.50",
        "- Delivery time may be extended in cases of force majeure or international shipping delays",
        "- This quotation is indicative and non-binding until the final contract is signed",
        "- The price does not include: electrical connections, external wiring, cables, circuit breakers, or",
        "  any connections outside the machine",
    ]
    
    for note in notes:
        c.drawString(2.3*cm, y_position, note)
        y_position -= 0.5*cm
    
    y_position -= 1*cm
    
    # الختام
    c.setFont("Helvetica", 11)
    c.drawString(2*cm, y_position, "Yours faithfully,")
    y_position -= 0.7*cm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(2*cm, y_position, data.company_name_en)
    
    draw_footer(c, page_num, is_arabic=False)
    c.save()


def create_arabic_quotation(filename, data):
    """
    إنشاء عرض السعر بالعربية
    """
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4
    page_num = 1
    
    # ==================
    # الصفحة الأولى
    # ==================
    
    # رسم الترويسة
    y_position = draw_header(c, data, is_arabic=True)
    
    # المقدمة
    c.setFont("Arabic", 10)
    intro = prepare_arabic_text("نحن نتشرف بتقديم عرض السعر التالي لماكينة الطباعة طبقاً للمواصفات الموضحة أدناه:")
    c.drawRightString(width - 2*cm, y_position, intro)
    y_position -= 1*cm
    
    # تفاصيل الماكينة
    c.setFont("Arabic-Bold", 12)
    c.drawRightString(width - 2*cm, y_position, prepare_arabic_text("تفاصيل الماكينة:"))
    y_position -= 0.7*cm
    
    c.setFont("Arabic", 10)
    machine_details = [
        ("نوع الماكينة:", "فليكسو بانيلوكس سيراميك وسكينة دكتور"),
        ("الموديل:", data.machine_model),
        ("بلد المنشأ:", data.country_origin_ar),
        ("عدد الألوان:", f"{data.colors_count} لون"),
        ("الوندر:", data.winder_type_ar),
        ("نوع الوندر:", data.winder_position_ar),
        ("عرض الماكينة:", f"{data.machine_width} سم"),
    ]
    
    for label, value in machine_details:
        c.setFont("Arabic-Bold", 10)
        label_text = prepare_arabic_text(label)
        c.drawRightString(width - 2*cm, y_position, label_text)
        
        c.setFont("Arabic", 10)
        # للقيم المختلطة (عربي وإنجليزي)
        if label == "الموديل:":
            c.drawRightString(width - 6*cm, y_position, value)
        else:
            value_text = prepare_arabic_text(value)
            c.drawRightString(width - 6*cm, y_position, value_text)
        
        y_position -= 0.5*cm
    
    y_position -= 0.5*cm
    
    # المواصفات العامة
    c.setFont("Arabic-Bold", 12)
    c.drawRightString(width - 2*cm, y_position, prepare_arabic_text("المواصفات العامة:"))
    y_position -= 0.7*cm
    
    c.setFont("Arabic", 9)
    general_specs_ar = [
        "جسم قوي من الحديد الزهر، ثابت ومقاوم للاهتزاز - 1",
        "وحدات للتحكم في الشد بشكل أوتوماتيكي بما يتناسب مع وزن وسمك ومرونة الخامات - 2",
        "مع إمكانية التحكم اليدوي",
        "وحدات هزاز للتأكد من توسيط الطباعة على سطح الخامة وإعادة لف الخامة - 3",
        "المطبوعة بشكل منتظم",
        "درافيل وسلندرات معالجة بالليزر لخدمة شاقة وعمر أطول - 4",
        "موتورات منفصلة لإعادة اللف والتحكم بها بشكل منفصل لإتاحة تشغيل خامات - 5",
        "بمرونة وسماكات مختلفة",
        "سلندرات البكر نفخ هواء، بالإضافة إلى سلندر إضافي عادي للتمكن من تشغيل أي مقاس كور - 6",
        "إمكانية الطباعة على الوجهين - 7",
        "كبس سلندرات الطباعة عن طريق ضغط زيت الهيدروليك لتفادي مشاكل الكبس الهوائي - 8",
        "إمكانية تعديل تسجيل الألوان بشكل يدوي أفقياً ورأسياً أثناء التشغيل - 9",
        "أوناش رفع علوية مدمجة بالماكينة لتسهيل رفع وتنزيل البكر وسلندرات الطباعة - 10",
    ]
    
    for spec in general_specs_ar:
        spec_text = prepare_arabic_text(spec)
        c.drawRightString(width - 2.3*cm, y_position, spec_text)
        y_position -= 0.4*cm
        
        if y_position < 3*cm:
            draw_footer(c, page_num, is_arabic=True)
            c.showPage()
            page_num += 1
            y_position = draw_header(c, data, is_arabic=True)
            c.setFont("Arabic", 9)
    
    # المواصفات المتبقية
    remaining_specs_ar = [
        "يمكن استخدام أحبار زيتية أو مائية - 11",
        "انفرترات دلتا تايواني - 12",
        "إنذار قبل تشغيل الماكينة لتفادي الإصابات - 13",
        "وحدات تجفيف بالهواء الساخن ومسار طويل للخامة لضمان التجفيف الكامل للأحبار - 14",
        "نقل الحركة من الموتور الرئيسي لأجزاء الماكينة عن طريق السيور - 15",
        "مضخات تزييت مدمجة بالماكينة لضمان وصول الزيت لجميع الأجزاء بشكل متوازن - 16",
        "حساسات توقف الماكينة أوتوماتيكياً عند انقطاع أو نفاذ الفيلم - 17",
    ]
    
    for spec in remaining_specs_ar:
        spec_text = prepare_arabic_text(spec)
        c.drawRightString(width - 2.3*cm, y_position, spec_text)
        y_position -= 0.4*cm
        
        if y_position < 3*cm:
            draw_footer(c, page_num, is_arabic=True)
            c.showPage()
            page_num += 1
            y_position = draw_header(c, data, is_arabic=True)
            c.setFont("Arabic", 9)
    
    draw_footer(c, page_num, is_arabic=True)
    c.showPage()
    page_num += 1
    
    # ==================
    # الصفحة الثانية - المواصفات الفنية
    # ==================
    
    y_position = draw_header(c, data, is_arabic=True)
    
    c.setFont("Arabic-Bold", 12)
    c.drawRightString(width - 2*cm, y_position, prepare_arabic_text("المواصفات الفنية:"))
    y_position -= 1*cm
    
    c.setFont("Arabic", 9)
    tech_specs_ar = [
        ("الموديل - 1", data.machine_model),
        ("عدد الألوان - 2", "4+0, 3+1, 2+2 طباعة معكوسة"),
        ("أوجه الطباعة - 3", "٢"),
        ("وحدات الشد - 4", "٤ قطعة"),
        ("نظام البريك - 5", "٤ قطعة"),
        ("قدرة البريك - 6", "2 pc (10kg) + 2 pc (5kg)"),
        ("نظام المحاذاة (الهزاز) - 7", "قطعتين"),
        ("أقصى عرض للفيلم - 8", f"{data.max_film_width} مم"),
        ("أقصى عرض للطباعة - 9", f"{data.max_printing_width} مم"),
        ("أقل وأقصى طول للطباعة - 10", data.min_max_printing_length),
        ("أقصى قطر للبكر - 11", f"{data.max_roll_diameter} مم"),
        ("نوع الانيلوكس - 12", data.anilox_type_ar),
        ("أقصى سرعة للماكينة - 13", f"{data.max_machine_speed} م/دقيقة"),
        ("أقصى سرعة طباعة - 14", f"{data.max_printing_speed} م/دقيقة"),
        ("قدرة المجفف - 15", data.dryer_capacity),
        ("طريقة نقل الحركة - 16", "سيور"),
        ("قدرة الموتور الرئيسي - 17", f"{data.main_motor_power} حصان"),
        ("مراقبة الطباعة بالفيديو - 18", "لا"),
        ("PLC - 19", "لا"),
        ("سليتر - 20", "لا"),
    ]
    
    for label, value in tech_specs_ar:
        label_text = prepare_arabic_text(label)
        c.drawRightString(width - 2.3*cm, y_position, label_text)
        
        # للقيم المختلطة
        if isinstance(value, str) and any(char.isdigit() or char.isalpha() for char in value if ord(char) < 128):
            # قيمة تحتوي على أرقام أو حروف إنجليزية
            if "مم" in value or "م/دقيقة" in value or "حصان" in value or "قطعة" in value or "قطعتين" in value:
                value_text = prepare_arabic_text(value)
                c.drawRightString(width - 10*cm, y_position, value_text)
            else:
                c.drawRightString(width - 10*cm, y_position, value)
        else:
            value_text = prepare_arabic_text(str(value))
            c.drawRightString(width - 10*cm, y_position, value_text)
        
        y_position -= 0.5*cm
        
        if y_position < 3*cm:
            draw_footer(c, page_num, is_arabic=True)
            c.showPage()
            page_num += 1
            y_position = draw_header(c, data, is_arabic=True)
            c.setFont("Arabic", 9)
    
    y_position -= 1*cm
    
    # سلندرات الطباعة
    c.setFont("Arabic-Bold", 12)
    c.drawRightString(width - 2*cm, y_position, prepare_arabic_text("سلندرات الطباعة:"))
    y_position -= 0.8*cm
    
    # رأس الجدول
    c.setFont("Arabic-Bold", 10)
    c.drawRightString(width - 2.5*cm, y_position, prepare_arabic_text("مقاس"))
    c.drawRightString(width - 6*cm, y_position, prepare_arabic_text("عدد"))
    y_position -= 0.3*cm
    
    # خط تحت الرأس
    c.setLineWidth(0.5)
    c.line(width - 8*cm, y_position, width - 2.3*cm, y_position)
    y_position -= 0.5*cm
    
    # البيانات
    c.setFont("Arabic", 10)
    for i, cylinder in enumerate(data.printing_cylinders, 1):
        c.drawRightString(width - 2.3*cm, y_position, prepare_arabic_text(f"{i} -"))
        c.drawRightString(width - 3.5*cm, y_position, cylinder["size"])
        c.drawRightString(width - 6*cm, y_position, prepare_arabic_text(cylinder["count"]))
        y_position -= 0.5*cm
    
    draw_footer(c, page_num, is_arabic=True)
    c.showPage()
    page_num += 1
    
    # ==================
    # الصفحة الثالثة - العرض المالي
    # ==================
    
    y_position = draw_header(c, data, is_arabic=True)
    
    c.setFont("Arabic-Bold", 12)
    c.drawRightString(width - 2*cm, y_position, prepare_arabic_text("العرض المالي:"))
    y_position -= 0.8*cm
    
    c.setFont("Arabic", 10)
    price_text = prepare_arabic_text(f"سعر الماكينة شامل السلندرات: {data.total_price} ج.م")
    c.drawRightString(width - 2*cm, y_position, price_text)
    y_position -= 0.5*cm
    
    inclusion_text = prepare_arabic_text("السعر شامل التوريد والتركيب والضمان")
    c.drawRightString(width - 2*cm, y_position, inclusion_text)
    y_position -= 1.2*cm
    
    c.setFont("Arabic-Bold", 12)
    c.drawRightString(width - 2*cm, y_position, prepare_arabic_text("طريقة الدفع:"))
    y_position -= 0.8*cm
    
    # جدول الدفع
    c.setFont("Arabic-Bold", 10)
    c.drawRightString(width - 2.5*cm, y_position, prepare_arabic_text("مرحلة الدفع"))
    c.drawRightString(width - 10*cm, y_position, prepare_arabic_text("النسبة"))
    c.drawRightString(width - 13.5*cm, y_position, prepare_arabic_text("المبلغ (ج.م)"))
    y_position -= 0.3*cm
    
    c.setLineWidth(0.5)
    c.line(width - 16*cm, y_position, width - 2.3*cm, y_position)
    y_position -= 0.5*cm
    
    c.setFont("Arabic", 10)
    payment_terms_ar = [
        ("مقدم تعاقد", f"{data.down_payment_percent}%", data.down_payment_amount),
        ("دفعة قبل الشحن", f"{data.before_shipping_percent}%", data.before_shipping_amount),
        ("دفعة قبل التسليم", f"{data.before_delivery_percent}%", data.before_delivery_amount),
    ]
    
    for stage, percent, amount in payment_terms_ar:
        stage_text = prepare_arabic_text(stage)
        c.drawRightString(width - 2.5*cm, y_position, stage_text)
        c.drawRightString(width - 10*cm, y_position, percent)
        c.drawRightString(width - 13.5*cm, y_position, amount)
        y_position -= 0.5*cm
    
    y_position -= 1*cm
    
    # التسليم
    c.setFont("Arabic-Bold", 12)
    c.drawRightString(width - 2*cm, y_position, prepare_arabic_text("التسليم:"))
    y_position -= 0.8*cm
    
    c.setFont("Arabic", 10)
    delivery_place = prepare_arabic_text(f"مكان التسليم: {data.delivery_location_ar}")
    c.drawRightString(width - 2*cm, y_position, delivery_place)
    y_position -= 0.5*cm
    
    delivery_time = prepare_arabic_text(f"وقت التسليم المتوقع: {data.delivery_time_ar}")
    c.drawRightString(width - 2*cm, y_position, delivery_time)
    y_position -= 1.2*cm
    
    # الضمان
    c.setFont("Arabic-Bold", 12)
    c.drawRightString(width - 2*cm, y_position, prepare_arabic_text("الضمان وخدمة ما بعد البيع:"))
    y_position -= 0.8*cm
    
    c.setFont("Arabic", 10)
    warranty1 = prepare_arabic_text(f"يسري الضمان لمدة {data.warranty_period} شهر ضد عيوب الصناعة، ويبدأ من تاريخ التسليم،")
    c.drawRightString(width - 2*cm, y_position, warranty1)
    y_position -= 0.5*cm
    
    warranty2 = prepare_arabic_text("ولا يشمل الأجزاء الاستهلاكية أو سوء الاستخدام.")
    c.drawRightString(width - 2*cm, y_position, warranty2)
    y_position -= 0.5*cm
    
    support = prepare_arabic_text("دعم فني كامل مع توافر قطع الغيار عند الطلب")
    c.drawRightString(width - 2*cm, y_position, support)
    y_position -= 1.2*cm
    
    # ملاحظات
    c.setFont("Arabic-Bold", 12)
    c.drawRightString(width - 2*cm, y_position, prepare_arabic_text("ملاحظات:"))
    y_position -= 0.8*cm
    
    c.setFont("Arabic", 9)
    notes_ar = [
        f"عرض السعر ساري لمدة {data.validity_days} يوم من تاريخ عرض السعر -",
        "يتم تعديل السعر في حالة ارتفاع سعر صرف الدولار بقيمة تزيد عن 50 قرش -",
        "قد تزيد مدة التوريد في حالات القوة القاهرة أو تأخير الشحن الدولي -",
        "هذا العرض استرشادي وغير ملزم إلا بعد توقيع العقد النهائي -",
        "السعر لا يشمل التوصيلات الكهربائية أو أي توصيلات أو كابلات أو قواطع -",
        "خارج الماكينة",
    ]
    
    for note in notes_ar:
        note_text = prepare_arabic_text(note)
        c.drawRightString(width - 2.3*cm, y_position, note_text)
        y_position -= 0.5*cm
    
    y_position -= 1*cm
    
    # الختام
    c.setFont("Arabic", 11)
    closing = prepare_arabic_text("وتفضلوا بقبول وافر الاحترام،،،")
    c.drawRightString(width - 2*cm, y_position, closing)
    y_position -= 0.7*cm
    
    c.setFont("Arabic-Bold", 11)
    company = prepare_arabic_text(data.company_name_ar)
    c.drawRightString(width - 2*cm, y_position, company)
    
    draw_footer(c, page_num, is_arabic=True)
    c.save()


# ==============================================================================
# الدالة الرئيسية
# ==============================================================================

def generate_quotations(data=None):
    """
    الدالة الرئيسية لتوليد عروض الأسعار
    
    Parameters:
    -----------
    data : QuotationData, optional
        بيانات عرض السعر. إذا لم يتم توفيرها، سيتم استخدام البيانات الافتراضية
    
    Returns:
    --------
    tuple : (arabic_filename, english_filename)
        أسماء ملفات PDF المُنشأة
    """
    
    # إذا لم يتم تمرير بيانات، استخدم البيانات الافتراضية
    if data is None:
        data = QuotationData()
    
    # تسجيل الخطوط العربية
    try:
        # محاولة تحميل خط عربي من النظام
        pdfmetrics.registerFont(TTFont('Arabic', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
        pdfmetrics.registerFont(TTFont('Arabic-Bold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
    except:
        print("تحذير: لم يتم العثور على الخط العربي. سيتم استخدام الخط الافتراضي.")
    
    # إنشاء أسماء الملفات
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    arabic_filename = f"/mnt/user-data/outputs/quotation_arabic_{timestamp}.pdf"
    english_filename = f"/mnt/user-data/outputs/quotation_english_{timestamp}.pdf"
    
    # إنشاء عروض الأسعار
    print("جاري إنشاء عرض السعر بالعربية...")
    create_arabic_quotation(arabic_filename, data)
    print(f"تم إنشاء عرض السعر بالعربية: {arabic_filename}")
    
    print("\nجاري إنشاء عرض السعر بالإنجليزية...")
    create_english_quotation(english_filename, data)
    print(f"تم إنشاء عرض السعر بالإنجليزية: {english_filename}")
    
    return arabic_filename, english_filename


# ==============================================================================
# نقطة الدخول للبرنامج
# ==============================================================================

if __name__ == "__main__":
    """
    عند تشغيل الملف مباشرة، سيتم إنشاء عروض أسعار باستخدام البيانات الافتراضية
    
    للاستخدام مع Anvil أو من كود آخر:
    1. استورد QuotationData
    2. أنشئ كائن وعدّل القيم
    3. استدعي generate_quotations(data)
    
    مثال:
    ------
    from quotation_generator import QuotationData, generate_quotations
    
    data = QuotationData()
    data.client_name_ar = "شركة جديدة"
    data.total_price = "3,000,000"
    
    arabic_file, english_file = generate_quotations(data)
    """
    
    # إنشاء عروض أسعار باستخدام البيانات الافتراضية
    arabic_pdf, english_pdf = generate_quotations()
    
    print("\n" + "="*60)
    print("تم إنشاء عروض الأسعار بنجاح!")
    print("="*60)
    print(f"\nعرض السعر بالعربية: {arabic_pdf}")
    print(f"عرض السعر بالإنجليزية: {english_pdf}")

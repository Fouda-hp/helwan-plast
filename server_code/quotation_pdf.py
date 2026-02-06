"""
quotation_pdf.py - تنسيق التواريخ والأرقام وبناء بيانات PDF لعرض السعر
يُستورد من QuotationManager؛ لا يحتوي على callables.
"""


def format_number(num):
    """تنسيق الأرقام بالفواصل"""
    try:
        if num is None:
            return "0"
        return "{:,.0f}".format(float(num))
    except (ValueError, TypeError):
        return str(num)


def format_date_ar(date_obj):
    """تنسيق التاريخ بالعربي"""
    if not date_obj:
        return ""
    months_ar = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
                 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر']
    try:
        return f"{date_obj.day} {months_ar[date_obj.month - 1]}"
    except (AttributeError, IndexError):
        return str(date_obj)


def format_date_en(date_obj):
    """تنسيق التاريخ بالإنجليزي"""
    if not date_obj:
        return ""
    months_en = ['January', 'February', 'March', 'April', 'May', 'June',
                 'July', 'August', 'September', 'October', 'November', 'December']
    try:
        return f"{date_obj.day} {months_en[date_obj.month - 1]}"
    except (AttributeError, IndexError):
        return str(date_obj)


def build_pdf_data(q_data, user_info, sales_rep_info, company_settings, machine_specs, tech_specs_settings):
    """
    بناء قاموس pdf_data من بيانات العرض والمستخدم والإعدادات.
    يُستدعى من QuotationManager.get_quotation_pdf_data بعد جلب كل البيانات.
    """
    model = q_data.get('Model', '')
    cylinders = []
    for i in range(1, 13):
        size = q_data.get(f'Size in CM{i}')
        count = q_data.get(f'Count{i}')
        if size and count:
            cylinders.append({'size': size, 'count': count})

    total_price = float(q_data.get('Agreed Price') or 0)
    down_percent = float(company_settings['down_payment_percent'])
    shipping_percent = float(company_settings['before_shipping_percent'])
    delivery_percent = float(company_settings['before_delivery_percent'])

    down_amount = total_price * (down_percent / 100)
    shipping_amount = total_price * (shipping_percent / 100)
    delivery_amount = total_price * (delivery_percent / 100)

    pdf_data = {
        'user_name': user_info['name'],
        'user_phone': user_info['phone'],
        'sales_rep_name': sales_rep_info['name'],
        'sales_rep_phone': sales_rep_info['phone'],
        'sales_rep_email': sales_rep_info['email'],
        'company': company_settings,
        'quotation_number': q_data.get('Quotation#', ''),
        'quotation_date': q_data.get('Date'),
        'quotation_date_ar': format_date_ar(q_data.get('Date')),
        'quotation_date_en': format_date_en(q_data.get('Date')),
        'client_name': q_data.get('Client Name', ''),
        'client_company': q_data.get('Company', ''),
        'client_phone': q_data.get('Phone', ''),
        'client_address': q_data.get('Address', ''),
        'model': model,
        'machine_type': q_data.get('Machine type', ''),
        'colors_count': q_data.get('Number of colors', ''),
        'machine_width': q_data.get('Machine width', ''),
        'winder': q_data.get('Winder', ''),
        'material': q_data.get('Material', ''),
        'video_inspection': q_data.get('Video inspection', 'NO'),
        'plc': q_data.get('PLC', 'NO'),
        'slitter': q_data.get('Slitter', 'NO'),
        'pneumatic_unwind': q_data.get('Pneumatic Unwind', 'NO'),
        'hydraulic_station_unwind': q_data.get('Hydraulic Station Unwind', 'NO'),
        'pneumatic_rewind': q_data.get('Pneumatic Rewind', 'NO'),
        'surface_rewind': q_data.get('Surface Rewind', 'NO'),
        'machine_specs': machine_specs,
        'cylinders': cylinders,
        'total_price': format_number(total_price),
        'total_price_raw': total_price,
        'pricing_mode': q_data.get('Pricing Mode', ''),
        'down_payment_percent': down_percent,
        'down_payment_amount': format_number(down_amount),
        'before_shipping_percent': shipping_percent,
        'before_shipping_amount': format_number(shipping_amount),
        'before_delivery_percent': delivery_percent,
        'before_delivery_amount': format_number(delivery_amount),
        'delivery_location': q_data.get('Address', ''),
        'expected_delivery': q_data.get('Expected delivery time'),
        'expected_delivery_formatted': str(q_data.get('Expected delivery time') or ''),
        'tech_specs_settings': tech_specs_settings,
    }
    return pdf_data

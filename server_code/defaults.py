"""
defaults.py — مصدر واحد للقيم الافتراضية (إعدادات التطبيق والكالكتور).
يُستورد في AuthManager عند تهيئة الإعدادات الافتراضية.
"""
import json


def get_default_settings():
    """
    قائمة الإعدادات الافتراضية (تُستخدم عند إنشاء أول أدمن أو طوارئ).
    البنية: قائمة من dicts، كل عنصر: key, value, type, description.
    """
    return [
        {'key': 'exchange_rate', 'value': '47.5', 'type': 'number', 'description': 'Exchange Rate (USD to EGP)'},
        {
            'key': 'cylinder_prices',
            'value': json.dumps({'80': 3.49, '100': 3.59, '120': 4.05, '130': 4.5, '140': 5.026, '160': 5.4}),
            'type': 'json',
            'description': 'Cylinder prices per CM',
        },
        {
            'key': 'default_cylinder_sizes',
            'value': json.dumps([25, 30, 35, 40, 45, 50, 60]),
            'type': 'json',
            'description': 'Default cylinder sizes',
        },
        {'key': 'shipping_sea', 'value': '3200', 'type': 'number', 'description': 'Sea shipping cost (USD)'},
        {'key': 'ths_cost', 'value': '1000', 'type': 'number', 'description': 'THS cost (USD)'},
        {'key': 'clearance_expenses', 'value': '1400', 'type': 'number', 'description': 'Clearance expenses (USD)'},
        {'key': 'tax_rate', 'value': '0.15', 'type': 'number', 'description': 'Tax rate (decimal)'},
        {'key': 'bank_commission', 'value': '0.0132', 'type': 'number', 'description': 'Bank commission rate (decimal)'},
    ]

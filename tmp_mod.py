import os

filepath = r"D:\OneDrive - Helwan Plast6\Printer\Mohamed\Cursor\Final\Helwan_Plast - Copy\client_code\AccountantFormorm_template.yaml"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

with open(filepath + ".bak", "w", encoding="utf-8") as f:
    f.write(content)

print("Original lines:", content.count(chr(10)) + 1)
changes = []
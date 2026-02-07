# رفع ملف QuotationPrintForm/__init__.py فقط إلى Anvil (عبر Git)
# شغّل من مجلد المشروع (Helwan_Plast) من Cursor Terminal أو PowerShell

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 1) إضافة الملف الصحيح فقط
git add client_code/QuotationPrintForm/__init__.py

# 2) عمل commit (إن لم يكن موجوداً)
git diff --cached --quiet; if (-not $?) { git commit -m "Fix: QuotationPrintForm indentation (SyntaxError unindent)" }

# 3) دفع إلى الريموت (ستُطلب منك كلمة المرور أو المصادقة)
git push origin master

Write-Host ""
Write-Host "بعد النجاح: افتح Anvil Editor -> Version Control -> Pull لسحب الملف."
Write-Host ""

# أسرار Anvil (Anvil Secrets) — Helwan Plast System

يتم ضبط الأسرار من واجهة Anvil: **App → Secrets**.

---

## أسرار مطلوبة أو موصى بها

| المفتاح | الوصف | مطلوب |
|---------|--------|--------|
| **ADMIN_EMAIL** | بريد الأدمن للإشعارات (مثلاً عند طلبات الموافقة، الطوارئ). | موصى به (افتراضي: mohamedadelfouda@helwanplast.com) |
| **EMERGENCY_KEY** | مفتاح سري لاستعادة كلمة مرور الأدمن في الطوارئ. إن لم يُضبط تُعطّل نقاط نهاية الطوارئ. | موصى به للأمان |
| **BACKUP_ENCRYPTION_KEY** | مفتاح لتشفير النسخ الاحتياطية قبل رفعها إلى Google Drive. إن لم يُضبط تُرفع النسخ بدون تشفير. | اختياري (موصى به للإنتاج) |

---

## أسرار OTP (SMS / WhatsApp)

| المفتاح | الوصف |
|---------|--------|
| **TWILIO_ACCOUNT_SID** | Account SID من Twilio |
| **TWILIO_AUTH_TOKEN** | Auth Token من Twilio |
| **TWILIO_FROM_NUMBER** | رقم المرسل (SMS) |
| **TWILIO_WHATSAPP_FROM** | (اختياري) رقم/حساب WhatsApp للمرسل |

للتفاصيل: `OTP_CHANNEL_SETUP.md`.

---

## ملاحظات

- لا ترفع ملفات تحتوي على قيم هذه الأسرار إلى Git.
- في بيئة الإنتاج يُفضّل ضبط كل من `EMERGENCY_KEY` و`BACKUP_ENCRYPTION_KEY`.

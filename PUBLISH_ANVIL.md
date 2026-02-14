# رفع التطبيق على Anvil (نشر / Publish)

يمكنك استخدام **Git for Windows** (أو أي عميل Git) لدفع التعديلات إلى GitHub؛ ثم في Anvil تسحب التحديثات (Pull) وتنشر (Publish). لا يوجد رفع مباشر إلى Anvil — المسار دائماً: جهازك → GitHub → Anvil (Pull ثم Publish).

---

## الطريقة 1: المشروع مربوط بـ Git (GitHub)

1. **دفع التعديلات من جهازك إلى GitHub**
   - من مجلد المشروع استخدم **Git for Windows** (Git Bash أو CMD) أو Terminal في Cursor:
   ```bash
   git add .
   git commit -m "Fix: pass auth in Calculator + debug instrumentation"
   git push origin master
   ```

2. **فتح Anvil ومزامنة المشروع**
   - ادخل إلى [Anvil Editor](https://anvil.works/build) وسجّل الدخول.
   - افتح تطبيق Helwan Plast (إذا كان مستنسخاً من نفس المستودع).
   - من **Version Control** (أو **Git**) اختر **Pull** أو **Sync** لسحب آخر التعديلات من GitHub.

3. **النشر (Publish)**
   - اضغط زر **Publish** أعلى اليمين في المحرر.
   - اختر البيئة (مثل Public) ثم **Publish This App**.
   - الرابط سيظهر بعد النشر (مثل `https://....anvil.app`).

---

## الطريقة 2: المشروع غير مربوط بـ Git بعد

1. **رفع المشروع إلى GitHub**
   - أنشئ مستودعاً جديداً على GitHub (إن لم يكن موجوداً).
   - من مجلد المشروع:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin master
   ```

2. **استنساخ التطبيق في Anvil من GitHub**
   - من [Anvil Editor](https://anvil.works/build): **Clone from GitHub** (تحت Blank App).
   - أدخل رابط المستودع (مثل `https://github.com/YOUR_USERNAME/YOUR_REPO`).
   - اختر طريقة المصادقة (GitHub credentials) ثم **Clone App**.

3. **النشر**
   - بعد فتح التطبيق في Anvil: **Run** للتجربة ثم **Publish** للنشر على الرابط العام.

---

## الطريقة 3: فتح المشروع من مجلد محلي (بدون Git)

- محرر Anvil يعمل أساساً من السحابة أو من مستودع Git.
- لا يوجد زر "فتح مجلد محلي" لرفع مجلد OneDrive مباشرة.
- الخيار العملي: استخدام **الطريقة 1 أو 2** (دفع الكود إلى GitHub ثم Clone/Pull في Anvil).

---

## ملخص سريع

| الخطوة | أين |
|--------|-----|
| دفع الكود | Git for Windows (Git Bash) أو Cursor/Terminal: `git push origin master` |
| سحب التعديلات في Anvil | Anvil Editor → Version Control → Pull |
| تشغيل للتجربة | Anvil Editor → **Run** |
| نشر على الإنترنت | Anvil Editor → **Publish** |

بعد النشر، الرابط يكون من نوع:  
`https://YOUR_APP_ID.anvil.app`

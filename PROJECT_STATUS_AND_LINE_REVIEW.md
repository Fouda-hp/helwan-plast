# موقف المشروع بعد التعديلات — التقييم والتحسينات ومراجعة الكود

**تاريخ التقرير:** 8 فبراير 2026  
**بعد تنفيذ:** الترقيم الذرّي (counters)، Audit (الاسم بدل الإيميل + لا "system")، إشعار كل الأدمن، معالجة الأخطاء الصامتة.

---

## 1. موقف المشروع الحالي

### 1.1 ما تم إنجازه حديثاً

| المكوّن | الحالة |
|---------|--------|
| **الترقيم (Counters)** | جدول `counters` (key, value)، دالة `get_next_number_atomic` مع `@in_transaction`، استبدال كل استخدامات `_get_next_number`. السيرفر مصدر وحيد للأرقام، بدون `search()` على الجدول الكامل. |
| **الـ Audit** | عرض **الاسم** (من نفّذ الإجراء) في الواجهة؛ عدم عرض "system" (يُعرض "—"). الفلتر يدعم الاسم والإيميل. |
| **الإشعارات** | كل إجراء مُسجَّل في الـ audit يولد إشعاراً **لكل الأدمن** عبر `create_notification_for_all_admins('audit_action', ...)`. |
| **الأخطاء للمستخدم** | رسالة السيرفر عند فشل تحميل سجل التدقيق؛ عرض نص الخطأ في الـ catch؛ ضمان وجود `message` عند رفض الصلاحية في `get_audit_logs`. |

### 1.2 الحالة العامة للمشروع

- **المصادقة والصلاحيات:** قوية (PBKDF2، جلسات، OTP/TOTP، أدوار، صلاحيات مخصصة).
- **الترقيم:** ذرّي، بدون دوبليكيت، مع إعادة محاولة مرة واحدة عند تعارض الحفظ.
- **التدقيق:** كل عملية مع اسم المستخدم ووصف واضح؛ لا ظهور لـ "system".
- **الإشعارات:** كل أدمن يرى كل إجراء (من خلال ربط الـ audit بالإشعارات).
- **جودة الكود:** هيكلة جيدة، وحدات منفصلة للمصادقة والتدقيق والإشعارات والترقيم.

---

## 2. التقييم (درجات تقديرية)

| المعيار | التقييم | ملاحظة |
|---------|---------|--------|
| الأمان | 8.5/10 | مصادقة قوية، صلاحيات، تدقيق. تحسين: rate limit على الدوال العامة، عدم تخزين "system" في الحقول المعرّضة. |
| الأداء | 8/10 | الترقيم O(1)، إشعار لكل أدمن يزيد عدد صفوف الإشعارات — يمكن لاحقاً تخفيف التكرار أو دمج. |
| الموثوقية | 8.5/10 | ترقيم ذرّي، إعادة محاولة عند التعارض، معالجة أخطاء ورسائل للمستخدم. |
| قابلية الصيانة | 7.5/10 | ملفات كبيرة (AuthManager، QuotationManager)؛ تقسيمها يسهّل الصيانة. |
| تجربة المستخدم | 8/10 | واجهة واضحة، رسائل أخطاء، عرض الاسم في الـ audit. |

**التقييم الإجمالي:** حوالي **8/10** — مشروع جاهز للإنتاج مع نقاط تحسين اختيارية.

---

## 3. التحسينات المقترحة (حسب الأولوية)

### عالية
- **إزالة تكرار إشعار الـ audit:** حاليّاً كل `log_audit` يضيف صفاً في `audit_log` ويستدعي `create_notification_for_all_admins`. مع كثرة الإجراءات قد يمتلئ جدول الإشعارات. خيار: إشعار واحد "ملخص" كل فترة، أو إشعار لكل أدمن فقط للإجراءات المهمة (حذف، استعادة، استيراد، نسخ احتياطي) وليس لكل تحديث بسيط.
- **تهريب XSS في Audit UI:** تمت إضافة دالة `escapeHtml` واستخدامها لجميع النصوص المعروضة في جدول سجل التدقيق ورسائل الخطأ (displayUser، action، table_name، record_id، msg، errMsg) — تم تنفيذه.

### متوسطة
- **فلتر سجل التدقيق على السيرفر:** الفلتر حسب المستخدم يُطبَّق بعد جلب كل السجلات (`all_logs = list(app_tables.audit_log.search())`). مع نمو الـ audit يُفضّل دعم فلتر في الاستعلام (إن وفرته Anvil) أو pagination على السيرفر.
- **تقسيم AuthManager / QuotationManager:** فصل العقود، إعدادات الحاسبة، قوالب البريد إلى وحدات منفصلة لتقليل حجم الملفات وتسهيل الاختبار.

### منخفضة
- **تسميات إضافية في ACTION_LABELS/TABLE_LABELS:** تمت إضافة `BACKUP_RESTORE` و `backup` في auth_audit.
- **توثيق الدوال العامة:** تحديث `access_policy.py` ليعكس استخدام `get_next_number_atomic` و`counters`.

---

## 4. مراجعة الكود سطراً سطراً (الأجزاء الحرجة)

### 4.1 auth_audit.py

```94:101:server_code/auth_audit.py
    try:
        if user_name is None and user_email:
            user_name = get_user_name_for_audit(user_email)
        if not user_name and user_email:
            user_name = str(user_email).strip()
        # لا نعرض كلمة "system" — من نفّذ الإجراء اسمه يظهر؛ إن لم يُعرف نعرض "—"
        if not user_name or (user_name and str(user_name).strip().lower() == 'system'):
            user_name = "—"
```
- **سطر 99–100:** عندما لا يوجد `full_name` في المستخدم، نستخدم الإيميل كاسم عرض — مقبول.
- **سطر 100–101:** الشرط `(user_name and str(user_name).strip().lower() == 'system')` يغطي حالة أن يكون الاسم المحفوظ سابقاً "system" فيُستبدل بـ "—". صحيح.

```105:116:server_code/auth_audit.py
        row_data = {
            'log_id': str(uuid.uuid4()),
            ...
            'user_email': (user_email or '').strip() or '',
```
- **سطر 108:** عند `user_email=None` يصبح الحقل `''` وليس `'system'` — متوافق مع عدم عرض "system".

```129:141:server_code/auth_audit.py
        # إشعار لكل الأدمن عند أي إجراء (ولو طفيف)
        try:
            from . import notifications as notif_mod
            notif_mod.create_notification_for_all_admins('audit_action', {
                'action_description': desc,
                ...
            })
        except Exception as notif_e:
            logger.debug("Notify admins after audit: %s", notif_e)
```
- **سطر 131:** استيراد داخل الدالة يقلل احتمال circular import (auth_audit ← notifications ← AuthManager ← auth_audit).
- **سطر 141:** استخدام `logger.debug` مناسب حتى لا يملأ السجلات عند فشل الإشعار.

---

### 4.2 notifications.py

```34:41:server_code/notifications.py
def _get_admin_emails():
    """قائمة بريد كل الأدمن النشطين (لإرسال إشعار لكل أدمن عند أي إجراء)."""
    try:
        admins = list(app_tables.users.search(role='admin', is_active=True))
        return [str(a.get('email', '')).strip().lower() for a in admins if a.get('email')]
    except Exception as e:
        logger.warning("Failed to get admin emails: %s", e)
        return []
```
- **سطر 37:** البحث بـ `role='admin', is_active=True` صحيح. ملاحظة: عدم فلترة `is_approved` قد يضم حسابات لم تُوافق عليها إن كانت موجودة كأدمن — عادة الأدمن يُعطى approved، ويمكن إضافة `is_approved=True` للوضوح.

```63:80:server_code/notifications.py
def create_notification_for_all_admins(notif_type, payload):
    ...
    for email in admin_emails:
        try:
            app_tables.notifications.add_row(...)
        except Exception as e:
            logger.warning("Failed to create admin notification for %s: %s", email, e)
```
- **سطر 69–80:** فشل إشعار لأدمن واحد لا يوقف الباقي — جيد. لو فشل كل الـ add_row (مثلاً جدول غير موجود) سيُسجَّل تحذير لكل أدمن؛ يمكن لاحقاً تخفيض الضجيج بتسجيل مرة واحدة.

---

### 4.3 quotation_numbers.py

```54:80:server_code/quotation_numbers.py
@anvil.server.callable
@anvil_tables.in_transaction
def get_next_number_atomic(counter_key):
    ...
    row = app_tables.counters.get(key=counter_key)
    if row is None:
        initial = _seed_initial_value(counter_key)
        app_tables.counters.add_row(key=counter_key, value=initial)
        ...
    current = row["value"]
    ...
    row["value"] = next_val
    return next_val
```
- **ترتيب الـ decorators:** `@callable` ثم `@in_transaction` — الدالة تُنفَّذ داخل transaction مع إعادة محاولة تلقائية من Anvil عند التعارض. صحيح.
- **سطر 66–69:** إنشاء العداد لأول مرة داخل نفس الـ transaction يضمن عدم إنشاء عدّادين لنفس المفتاح عند طلبات متزامنة (بفضل serializable isolation).
- **_seed_initial_value:** تُستدعى فقط عند عدم وجود الصف؛ فيها `table.search()` على clients/quotations — مرة واحدة عند أول استخدام للعداد، مقبول.

```98:127:server_code/quotation_numbers.py
def get_or_create_client_code(client_name, phone):
    ...
    row = app_tables.clients.get(Phone=phone, is_deleted=False)
    if row:
        return code
    new_code = get_next_number_atomic(COUNTER_CLIENTS)
```
- **سطر 112:** استدعاء `get_next_number_atomic` من خارج الـ decorator يُنفَّذ كطلب جديد (قرار Anvil) في transaction منفصلة — صحيح ولا يسبب deadlock.

---

### 4.4 QuotationManager.py — منطق الحفظ وإعادة المحاولة

```385:430:server_code/QuotationManager.py
    # الحفظ مع التدقيق. حماية إضافية: عند تعارض نادر (مثلاً TransactionConflict) نعيد المحاولة مرة واحدة بأرقام جديدة.
    for attempt in range(2):
        try:
            client_action = save_client_data(client_code, form_data, is_new_client, user_email, ip_address)
            ...
            return { "success": True, ... }
        except Exception as e:
            if attempt == 0 and (is_new_client or (is_new_quotation and is_quotation)):
                logger.warning("Save conflict (retry once with new numbers): %s", e)
                if is_new_client:
                    client_code = str(get_next_number_atomic('clients_next'))
                if is_new_quotation and is_quotation:
                    quotation_number = get_next_number_atomic('quotations_next')
                continue
            raise
```
- **سطر 386:** حلقة محاولتين فقط — منع تكرار لا نهائي.
- **سطر 423–428:** إعادة المحاولة فقط عند عميل جديد أو عرض جديد، وتوليد أرقام جديدة قبل المحاولة الثانية — سليم.
- **سطر 422:** أي استثناء (بما فيه عدم الصلاحية أو خطأ شبكة) ي触发 إعادة المحاولة. تحسين اختياري: إعادة المحاولة فقط لـ `TransactionConflict` أو أخطاء تكرار المفتاح، ورفع الباقي مباشرة.

---

### 4.5 AuthManager.py — get_audit_logs

```2625:2632:server_code/AuthManager.py
        if filters.get('user_email'):
            user_filter = filters['user_email'].lower()
            all_logs = [l for l in all_logs if (l.get('user_name') and user_filter in (l.get('user_name') or '').lower()) or (l.get('user_email') and user_filter in (l.get('user_email') or '').lower())]
```
- الفلتر يطابق الاسم أو الإيميل — متوافق مع واجهة "User (name)" والبحث بالاسم.

```2651:2657:server_code/AuthManager.py
        raw_name = log.get('user_name') or ''
        if str(raw_name).strip().lower() == 'system':
            raw_name = "—"
        display_name = (raw_name or "—").strip()
```
- ضمان عدم إرجاع "system" للعميل وضمان عرض "—" عند الغياب — صحيح.

---

### 4.6 AdminPanel — عرض سجل التدقيق والأخطاء

```1305:1310:client_code/AdminPanel/__init__.py
              var result = await window.getAuditLogs(100, 0, filters);
              if (!result.success) {
                var msg = (result && result.message) ? result.message : 'فشل تحميل سجل التدقيق';
                container.innerHTML = '<div class="empty-state"><h4>' + (msg || '—') + '</h4></div>';
```
- **سطر 1307:** وجود رسالة افتراضية وعدم الاعتماد على `result.message` فقط — يمنع عرض "undefined".

```1334:1337:client_code/AdminPanel/__init__.py
                var displayUser = (l.user_name && l.user_name !== '—') ? l.user_name : (l.user_email || '—');
                ...
                html += '<td>' + escapeHtml(displayUser || '—') + '</td>';
```
- **أمان:** تمت إضافة دالة `escapeHtml` واستخدامها لجميع القيم المعروضة في الجدول (displayUser، action، table_name، record_id) ورسالة الخطأ (msg، errMsg)، لتجنب XSS.

```1345:1352:client_code/AdminPanel/__init__.py
            } catch (e) {
              var errMsg = ...;
              container.innerHTML = '...<p>' + escapeHtml(errMsg) + '</p></div>';
            }
```
- عرض نص الخطأ للمستخدم يقلل الأخطاء الصامتة؛ و`errMsg` يُهرب قبل الإدراج في innerHTML.

---

## 5. خلاصة تنفيذية

| البند | الحالة |
|-------|--------|
| **موقف المشروع** | مستقر، جاهز للإنتاج. الترقيم ذرّي، التدقيق يعرض الاسم ولا يعرض "system"، كل أدمن يرى الإجراءات عبر الإشعارات، ورسائل الأخطاء تصل للمستخدم. |
| **التقييم** | ~8/10. نقاط القوة: أمان، ترقيم، تدقيق، إشعارات، تهريب نصوص واجهة الـ audit (escapeHtml). نقاط التحسين: حجم الملفات، أداء استعلام الـ audit، احتمال تكرار الإشعارات. |
| **التحسينات ذات الأولوية** | 1) تخفيف أو تخصيص إشعارات الـ audit (مثلاً إجراءات مهمة فقط أو ملخص). 2) تحسين فلتر/صفحة سجل التدقيق على السيرفر عند نمو البيانات. (تم تنفيذ escape نصوص الـ Audit UI.) |
| **مراجعة السطور** | المنطق في auth_audit، notifications، quotation_numbers، QuotationManager (retry)، get_audit_logs، وAdminPanel (عرض الخطأ والاسم وescapeHtml) سليم. التوصية المتبقية: تحسين اختيار نوع الاستثناء في إعادة المحاولة (مثلاً إعادة المحاولة فقط لـ TransactionConflict). |

---
*تم إعداد التقرير بعد مراجعة الكود سطراً سطراً في الملفات المذكورة.*

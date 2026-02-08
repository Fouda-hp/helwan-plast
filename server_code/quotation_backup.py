"""
quotation_backup.py - دوال النسخ الاحتياطي والاستعادة والاحتفاظ
يُستورد من QuotationManager؛ لا يحتوي على callables.
"""

import json
import logging
from datetime import datetime, date

import anvil
from anvil.google.drive import app_files
from anvil.tables import app_tables

try:
    from .auth_utils import get_utc_now
except ImportError:
    from auth_utils import get_utc_now

logger = logging.getLogger(__name__)

# سياسة الاحتفاظ: آخر 15 يوم كاملة + آخر 30 أسبوع (نسخة واحدة أسبوعياً)
BACKUP_RETENTION_DAYS = 15
BACKUP_RETENTION_WEEKS = 30


def get_backup_drive_folder():
    """الحصول على مجلد النسخ الاحتياطية في Google Drive (app_files)."""
    for name in ('Backups', 'Helwan_Plast_Backups', 'backups', 'backup', 'Backup'):
        folder = getattr(app_files, name, None)
        if folder is not None:
            if hasattr(folder, 'create_file'):
                return folder
            # بعض إصدارات Anvil تُرجع كائن بدون create_file - نجرب إرجاعه
            logger.info("app_files.%s found (type=%s) but no create_file. Trying anyway.", name, type(folder).__name__)
            return folder
    # طباعة المتاح للتصحيح
    available = [a for a in dir(app_files) if not a.startswith('_')]
    logger.warning("No backup folder found. Available app_files: %s", available)
    return None


def _get_fernet():
    """بناء Fernet من مفتاح Anvil Secrets (مفتاح Fernet base64url أو كلمة مرور)."""
    import base64
    import hashlib
    try:
        import anvil.secrets as _sec
        key = _sec.get_secret('BACKUP_ENCRYPTION_KEY')
    except Exception:
        return None
    if not key:
        return None
    try:
        from cryptography.fernet import Fernet
        raw = key.encode('utf-8') if isinstance(key, str) else key
        if len(raw) == 44:
            return Fernet(key if isinstance(key, str) else key.decode('utf-8'))
        digest = hashlib.sha256(raw).digest()
        b64 = base64.urlsafe_b64encode(digest)
        return Fernet(b64.decode('ascii'))
    except Exception:
        return None


def encrypt_backup(json_bytes):
    """
    تشفير النسخة الاحتياطية باستخدام Fernet (AES-128-CBC + HMAC).
    المفتاح من Anvil Secrets BACKUP_ENCRYPTION_KEY (إما مفتاح Fernet base64 أو كلمة مرور).
    يُرجع: (encrypted_bytes, is_encrypted)
    """
    try:
        fernet = _get_fernet()
        if not fernet:
            return json_bytes, False
        encrypted = fernet.encrypt(json_bytes)
        return b'HP_ENC_V2:' + encrypted, True
    except Exception as e:
        logger.warning("Backup encryption unavailable: %s - uploading unencrypted", e)
        return json_bytes, False


def decrypt_backup(data_bytes):
    """
    فك تشفير النسخة الاحتياطية (يدعم V1 قديم و V2 Fernet).
    يُرجع: decrypted_bytes
    """
    if data_bytes.startswith(b'HP_ENC_V2:'):
        try:
            fernet = _get_fernet()
            if not fernet:
                raise ValueError("BACKUP_ENCRYPTION_KEY not set in Anvil Secrets")
            return fernet.decrypt(data_bytes[len(b'HP_ENC_V2:'):])
        except Exception as e:
            logger.error("Backup decryption failed: %s", e)
            raise
    if not data_bytes.startswith(b'HP_ENC_V1:'):
        return data_bytes
    try:
        import anvil.secrets as _sec
        import hashlib
        key = _sec.get_secret('BACKUP_ENCRYPTION_KEY')
        if not key:
            raise ValueError("BACKUP_ENCRYPTION_KEY not set in Anvil Secrets")
        key_bytes = hashlib.sha256(key.encode('utf-8')).digest()
        encrypted = data_bytes[len(b'HP_ENC_V1:'):]
        decrypted = bytearray(len(encrypted))
        for i in range(len(encrypted)):
            decrypted[i] = encrypted[i] ^ key_bytes[i % len(key_bytes)]
        return bytes(decrypted)
    except Exception as e:
        logger.error("Backup decryption (V1) failed: %s", e)
        raise


def upload_backup_to_drive(json_bytes, filename):
    """
    تشفير ورفع ملف النسخة الاحتياطية إلى Google Drive.
    يُرجع: (success: bool, message: str)
    """
    try:
        folder = get_backup_drive_folder()
        if folder is None:
            return False, 'لم يتم العثور على مجلد Backups في Google Drive. أضف مجلداً باسم Backups أو Helwan_Plast_Backups من Anvil → Google Drive.'
        upload_bytes, is_encrypted = encrypt_backup(json_bytes)
        content_type = 'application/octet-stream' if is_encrypted else 'application/json'
        upload_filename = filename + '.enc' if is_encrypted else filename
        logger.info("Uploading backup to Drive: %s (folder type: %s, size: %d bytes)", upload_filename, type(folder).__name__, len(upload_bytes))
        try:
            folder.create_file(upload_filename, content_bytes=upload_bytes, content_type=content_type)
        except AttributeError:
            # بعض إصدارات Anvil تستخدم أسماء مختلفة للطريقة
            import anvil.google.drive
            media = anvil.BlobMedia(content_type, upload_bytes, name=upload_filename)
            folder.add_file(media)
        except TypeError as te:
            # محاولة بمعاملات مختلفة
            logger.warning("create_file TypeError: %s - trying alternative signature", te)
            import anvil
            media = anvil.BlobMedia(content_type, upload_bytes, name=upload_filename)
            folder.create_file(upload_filename, media)
        enc_msg = " (مشفر)" if is_encrypted else ""
        return True, f'تم الرفع إلى Google Drive{enc_msg}: {upload_filename}'
    except Exception as e:
        logger.exception("Upload backup to Drive: %s", e)
        return False, str(e)


def parse_backup_filename_date(filename):
    """
    استخراج تاريخ النسخة من اسم الملف: Helwan_Plast_backup_YYYYMMDD_HHMM.json أو .json.enc
    يُرجع: date أو None
    """
    if not filename or 'Helwan_Plast_backup_' not in filename:
        return None
    try:
        base = filename.replace('.enc', '').replace('.json', '').strip()
        parts = base.split('_')
        for i, p in enumerate(parts):
            if len(p) == 8 and p.isdigit():
                y, m, d = int(p[:4]), int(p[4:6]), int(p[6:8])
                if 1 <= m <= 12 and 1 <= d <= 31:
                    return date(y, m, d)
        return None
    except (ValueError, TypeError, IndexError):
        return None


def apply_backup_retention():
    """
    تطبيق سياسة الاحتفاظ على ملفات النسخ في Google Drive:
    - الاحتفاظ بكل النسخ خلال آخر 15 يوماً.
    - من يوم 16 حتى نهاية 30 أسبوع: نسخة واحدة أسبوعياً (الأحدث في كل أسبوع).
    - حذف ما تبقى.
    """
    try:
        folder = get_backup_drive_folder()
        if folder is None:
            return
        file_list = list(folder.list_files()) if hasattr(folder, 'list_files') else getattr(folder, 'files', [])
        entries = []
        for f in file_list:
            name = getattr(f, 'name', None) or getattr(f, 'title', None) or str(f)
            if not name or ('Helwan_Plast_backup_' not in name or (not name.endswith('.json') and not name.endswith('.json.enc'))):
                continue
            d = parse_backup_filename_date(name)
            if d is None:
                continue
            entries.append((f, name, d))
        if not entries:
            return
        today = date.today()
        keep_names = set()
        within_days = [(f, n, d) for f, n, d in entries if (today - d).days <= BACKUP_RETENTION_DAYS]
        for _, n, _ in within_days:
            keep_names.add(n)
        beyond_days = [(f, n, d) for f, n, d in entries if BACKUP_RETENTION_DAYS < (today - d).days <= BACKUP_RETENTION_DAYS + BACKUP_RETENTION_WEEKS * 7]
        beyond_days.sort(key=lambda x: x[2], reverse=True)
        week_kept = {}
        for f, n, d in beyond_days:
            w = (d.year, d.isocalendar()[1])
            if w not in week_kept:
                week_kept[w] = n
                keep_names.add(n)
            if len(week_kept) >= BACKUP_RETENTION_WEEKS:
                break
        deleted = 0
        for f, n, d in entries:
            if n in keep_names:
                continue
            try:
                if hasattr(f, 'delete'):
                    f.delete()
                    deleted += 1
            except Exception as e:
                logger.warning("Backup retention: could not delete %s: %s", n, e)
        if deleted:
            logger.info("Backup retention: deleted %d old file(s) from Drive", deleted)
    except Exception as e:
        logger.warning("Backup retention failed (backup itself succeeded): %s", e)


def row_to_dict(row, exclude_keys=None):
    """تحويل صف جدول إلى dict مع استبعاد مفاتيح حساسة."""
    exclude_keys = exclude_keys or set()
    try:
        d = dict(row)
        for k in list(d.keys()):
            if k in exclude_keys:
                d.pop(k, None)
        return d
    except Exception:
        return {}


def build_backup_payload():
    """
    بناء محتوى النسخة الاحتياطية (بدون تحقق صلاحية).
    يُرجع: (backup_dict, json_bytes, filename)
    """
    export_time = get_utc_now()
    export_date_str = export_time.strftime('%Y-%m-%d %H:%M:%S')
    filename_date = export_time.strftime('%Y%m%d_%H%M')
    backup = {
        'export_date': export_date_str,
        'app': 'Helwan_Plast',
        'version': 1,
        'clients': [],
        'quotations': [],
        'contracts': [],
        'machine_specs': [],
        'settings': []
    }
    sensitive_setting_keys = ('pending_totp_', 'password', 'secret', 'totp_')
    for row in app_tables.clients.search():
        backup['clients'].append(row_to_dict(row))
    for row in app_tables.quotations.search():
        backup['quotations'].append(row_to_dict(row))
    try:
        for row in app_tables.contracts.search():
            backup['contracts'].append(row_to_dict(row))
    except Exception:
        backup['contracts'] = []
    try:
        for row in app_tables.machine_specs.search():
            backup['machine_specs'].append(row_to_dict(row))
    except Exception:
        backup['machine_specs'] = []
    for row in app_tables.settings.search():
        key = (row.get('setting_key') or '').lower()
        if any(s in key for s in sensitive_setting_keys):
            continue
        backup['settings'].append({
            'setting_key': row.get('setting_key'),
            'setting_value': row.get('setting_value'),
            'setting_type': row.get('setting_type')
        })
    json_bytes = json.dumps(backup, ensure_ascii=False, indent=2, default=str).encode('utf-8')
    filename = f"Helwan_Plast_backup_{filename_date}.json"
    return backup, json_bytes, filename


def parse_backup_value(v):
    """تحويل قيمة من JSON النسخة الاحتياطية إلى نوع صحيح (date, datetime)."""
    if v is None:
        return None
    if isinstance(v, str) and v.strip():
        try:
            if 'T' in v or ' ' in v:
                return datetime.fromisoformat(v.replace('Z', '+00:00')[:26])
            if len(v) == 10 and v[4] == '-' and v[7] == '-':
                return datetime.strptime(v, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            pass
    return v

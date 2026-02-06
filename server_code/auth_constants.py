"""
auth_constants.py - ثوابت وإعدادات المصادقة والتفويض
"""

import logging

logger = logging.getLogger(__name__)

# ========== قفل الحساب والجلسات ==========
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 30
SESSION_DURATION_MINUTES = 60
MAX_SESSIONS_PER_USER = 5
RATE_LIMIT_WINDOW_MINUTES = 15
RATE_LIMIT_MAX_REQUESTS = 500
PBKDF2_ITERATIONS = 100000
PASSWORD_HISTORY_COUNT = 5
OTP_EXPIRY_MINUTES = 10

# ========== البريد والسري الطوارئ ==========
try:
    import anvil.secrets
    ADMIN_NOTIFICATION_EMAIL = anvil.secrets.get_secret('ADMIN_EMAIL') or "mohamedadelfouda@helwanplast.com"
    _emergency_key = anvil.secrets.get_secret('EMERGENCY_KEY')
    if not _emergency_key:
        logger.critical("EMERGENCY_KEY not set in Anvil Secrets! Emergency endpoints DISABLED.")
        EMERGENCY_SECRET_KEY = None
    else:
        EMERGENCY_SECRET_KEY = _emergency_key
except Exception as e:
    logger.critical("Failed to load secrets: %s - Emergency endpoints DISABLED.", e)
    ADMIN_NOTIFICATION_EMAIL = "mohamedadelfouda@helwanplast.com"
    EMERGENCY_SECRET_KEY = None

# ========== صلاحيات الأدوار ==========
ROLES = {
    'admin': ['all'],
    'manager': ['view', 'create', 'edit', 'export', 'delete_own'],
    'sales': ['view', 'create', 'edit_own'],
    'viewer': ['view']
}

AVAILABLE_PERMISSIONS = [
    'view', 'create', 'edit', 'edit_own', 'delete', 'delete_own',
    'export', 'import', 'manage_users', 'view_audit', 'manage_settings'
]

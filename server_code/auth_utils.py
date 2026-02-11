"""
auth_utils.py - دوال مساعدة للمصادقة (وقت، IP، تحقق البريد)
"""

import re
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_utc_now():
    return datetime.now(timezone.utc)


def make_aware(dt):
    if dt is None:
        return None
    if getattr(dt, 'tzinfo', None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def get_client_ip():
    try:
        import anvil.server
        context = anvil.server.context
        if hasattr(context, 'client') and context.client:
            client = context.client
            if hasattr(client, 'ip') and client.ip:
                return client.ip
    except Exception as e:
        logger.debug("Suppressed: %s", e)
    return 'unknown'


def validate_email(email):
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False
    if len(email) > 254:
        return False
    if '..' in email:
        return False
    return True

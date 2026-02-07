"""
auth_rate_limit.py - التحقق من حد الطلبات (Rate Limiting)
V4.0 - Fixed timezone-aware datetime comparisons
"""

import logging
from datetime import datetime, timedelta
from anvil.tables import app_tables

from .auth_constants import RATE_LIMIT_WINDOW_MINUTES, RATE_LIMIT_MAX_REQUESTS
from .auth_utils import get_utc_now, make_aware

logger = logging.getLogger(__name__)


def check_rate_limit(ip_address, endpoint='general'):
    if not ip_address:
        ip_address = 'unknown'
    try:
        now = get_utc_now()
        window_start = now - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)
        records = list(app_tables.rate_limits.search(ip_address=ip_address, endpoint=endpoint))
        record = records[0] if records else None
        if record:
            blocked_until = record.get('blocked_until')
            if blocked_until and now < make_aware(blocked_until):
                return False
            rec_window = record.get('window_start')
            if rec_window is not None and make_aware(rec_window) > window_start:
                new_count = (record.get('request_count') or 0) + 1
                if new_count > RATE_LIMIT_MAX_REQUESTS:
                    record.update(request_count=new_count, blocked_until=now + timedelta(hours=1))
                    logger.warning("Rate limit exceeded for IP: %s", ip_address)
                    return False
                record.update(request_count=new_count)
            else:
                record.update(request_count=1, window_start=now, blocked_until=None)
        else:
            app_tables.rate_limits.add_row(
                ip_address=ip_address,
                endpoint=endpoint,
                request_count=1,
                window_start=now,
                blocked_until=None
            )
        return True
    except Exception as e:
        logger.error("Rate limit check error: %s", e, exc_info=True)
        return True

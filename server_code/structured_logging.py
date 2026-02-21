"""
structured_logging.py - JSON Structured Logging with Correlation IDs
====================================================================
Provides:
- JSONFormatter: formats log records as JSON for easier parsing/searching
- CorrelationFilter: adds a request_id to every log record for tracing
- setup_structured_logging(): configures the root logger with JSON output
- get_correlation_id / set_correlation_id: per-request tracing

Usage (once at app startup):
    from server_code.structured_logging import setup_structured_logging
    setup_structured_logging()

All existing logger.info/warning/error calls automatically output JSON
with timestamp, level, module, message, and correlation_id fields.
"""

import json
import logging
import threading
import uuid
import time
import functools

# Thread-local storage for correlation ID (per-request tracing)
_local = threading.local()


# =========================================================
# Correlation ID management
# =========================================================

def get_correlation_id():
    """Get the current request's correlation ID, or generate one."""
    cid = getattr(_local, 'correlation_id', None)
    if not cid:
        cid = str(uuid.uuid4())[:8]
        _local.correlation_id = cid
    return cid


def set_correlation_id(cid=None):
    """Set a correlation ID for the current request. Auto-generates if None."""
    _local.correlation_id = cid or str(uuid.uuid4())[:8]
    return _local.correlation_id


def clear_correlation_id():
    """Clear the correlation ID (call at end of request)."""
    _local.correlation_id = None


# =========================================================
# JSON Formatter
# =========================================================

class JSONFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects.
    Fields: timestamp, level, module, function, message, correlation_id, extra.
    """

    def format(self, record):
        log_entry = {
            'ts': self.formatTime(record, '%Y-%m-%dT%H:%M:%S'),
            'level': record.levelname,
            'module': record.module,
            'func': record.funcName,
            'line': record.lineno,
            'msg': record.getMessage(),
            'cid': getattr(record, 'correlation_id', get_correlation_id()),
        }

        # Include exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry['exc'] = self.formatException(record.exc_info)

        # Include any extra fields passed via logger.info('msg', extra={...})
        for key in ('user_email', 'ip_address', 'action', 'duration_ms',
                     'table_name', 'record_id', 'status_code'):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, ensure_ascii=False, default=str)


# =========================================================
# Correlation ID Filter (auto-adds cid to every record)
# =========================================================

class CorrelationFilter(logging.Filter):
    """Adds correlation_id to every log record."""

    def filter(self, record):
        record.correlation_id = get_correlation_id()
        return True


# =========================================================
# Request timing decorator
# =========================================================

def log_request_timing(func):
    """
    Decorator that logs the execution time of a callable function.
    Adds duration_ms to the log entry.
    Uses functools.wraps to preserve original function signature —
    critical for Anvil's @anvil.server.callable argument matching.
    """
    logger = logging.getLogger(func.__module__)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        cid = set_correlation_id()
        t0 = time.time()
        try:
            result = func(*args, **kwargs)
            duration_ms = round((time.time() - t0) * 1000, 1)
            logger.info(
                "callable %s completed in %sms",
                func.__name__, duration_ms,
                extra={'duration_ms': duration_ms, 'action': func.__name__}
            )
            return result
        except Exception as e:
            duration_ms = round((time.time() - t0) * 1000, 1)
            logger.error(
                "callable %s failed after %sms: %s",
                func.__name__, duration_ms, e,
                extra={'duration_ms': duration_ms, 'action': func.__name__}
            )
            raise
        finally:
            clear_correlation_id()

    return wrapper


# =========================================================
# Setup function
# =========================================================

def setup_structured_logging(level=logging.INFO, json_output=True):
    """
    Configure the root logger for structured logging.

    Args:
        level: Logging level (default INFO)
        json_output: If True, use JSON formatter. If False, use standard format
                     (useful for local development readability).
    """
    root = logging.getLogger()

    # Remove existing handlers to avoid duplication
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.addFilter(CorrelationFilter())

    if json_output:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(module)s.%(funcName)s:%(lineno)d '
            '[cid=%(correlation_id)s] %(message)s'
        ))

    root.addHandler(handler)
    root.setLevel(level)

    # Suppress noisy third-party loggers
    for noisy in ('urllib3', 'requests', 'google', 'anvil'):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root.info("Structured logging initialized (json=%s)", json_output)

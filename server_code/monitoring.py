"""
monitoring.py - Health Check & Metrics Endpoint
================================================
Provides:
- health_check: callable that returns system health (DB, cache, sessions, auth)
- get_system_metrics: callable that returns operational metrics for admin dashboard
- HTTP endpoints for external monitoring dashboard:
  - GET /api/health?token=<session_token>         → quick health (any authenticated user)
  - GET /api/metrics?token=<admin_session_token>  → detailed metrics (admin only)

Usage:
  anvil.server.call('health_check')           → quick health status (any authenticated user)
  anvil.server.call('get_system_metrics', t)   → detailed metrics (admin only)
  External: https://YOUR_APP.anvil.app/api/health?token=SESSION_TOKEN
"""

import anvil.server
from anvil.tables import app_tables
import logging
import time
import json

try:
    from .auth_utils import get_utc_now
except ImportError:
    from auth_utils import get_utc_now

try:
    from .auth_permissions import require_authenticated as _require_authenticated
    from .auth_permissions import require_permission_full as _require_permission
except ImportError:
    from auth_permissions import require_authenticated as _require_authenticated
    from auth_permissions import require_permission_full as _require_permission

try:
    from .cache_manager import (
        dashboard_cache, tags_cache, report_cache,
        fx_rate_cache, accounting_dashboard_cache,
        payment_dashboard_cache, dashboard_stats_cache,
    )
except ImportError:
    from cache_manager import (
        dashboard_cache, tags_cache, report_cache,
        fx_rate_cache, accounting_dashboard_cache,
        payment_dashboard_cache, dashboard_stats_cache,
    )

logger = logging.getLogger(__name__)


# =========================================================
# Internal helpers
# =========================================================

def _safe_table_count(table, **filters):
    """Count rows in a table safely. Returns -1 on error."""
    try:
        return len(table.search(**filters))
    except Exception:
        return -1


def _check_db_health():
    """Quick DB connectivity check by reading one setting row."""
    try:
        t0 = time.time()
        _ = app_tables.settings.search()
        latency_ms = round((time.time() - t0) * 1000, 1)
        return {'status': 'ok', 'latency_ms': latency_ms}
    except Exception as e:
        return {'status': 'error', 'error': 'Database health check failed'}


def _cache_stats():
    """Collect size stats from all cache instances."""
    caches = {
        'dashboard': dashboard_cache,
        'tags': tags_cache,
        'reports': report_cache,
        'fx_rates': fx_rate_cache,
        'accounting_dashboard': accounting_dashboard_cache,
        'payment_dashboard': payment_dashboard_cache,
        'dashboard_stats': dashboard_stats_cache,
    }
    return {name: {'size': c.size(), 'ttl': c._ttl, 'max_size': c._max_size}
            for name, c in caches.items()}


# =========================================================
# Public callables
# =========================================================

@anvil.server.callable
def health_check(token_or_email=None):
    """
    Quick health check — returns system status.
    Any authenticated user can call this.
    """
    is_valid, user_email, error = _require_authenticated(token_or_email)
    if not is_valid:
        return error

    try:
        db = _check_db_health()
        active_sessions = _safe_table_count(app_tables.sessions, is_active=True)

        return {
            'success': True,
            'status': 'healthy' if db['status'] == 'ok' else 'degraded',
            'timestamp': get_utc_now().isoformat(),
            'components': {
                'database': db,
                'active_sessions': active_sessions,
                'caches': _cache_stats(),
            }
        }
    except Exception as e:
        logger.error("health_check error: %s", e)
        return {
            'success': False,
            'status': 'unhealthy',
            'error': 'Health check failed. Check server logs.',
            'timestamp': get_utc_now().isoformat(),
        }


@anvil.server.callable
def get_system_metrics(token_or_email=None):
    """
    Detailed system metrics — admin only.
    Returns table row counts, cache stats, session info.
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'admin')
    if not is_valid:
        return error

    try:
        t0 = time.time()

        # Table stats
        tables = {
            'users': _safe_table_count(app_tables.users),
            'users_active': _safe_table_count(app_tables.users, is_active=True),
            'sessions_active': _safe_table_count(app_tables.sessions, is_active=True),
            'clients': _safe_table_count(app_tables.clients, is_deleted=False),
        }

        # Optional tables (may not exist in all environments)
        optional = {
            'quotations': 'quotations',
            'contracts': 'contracts',
            'notifications': 'notifications',
            'audit_log': 'audit_log',
            'ledger': 'ledger',
            'inventory': 'inventory',
            'suppliers': 'suppliers',
        }
        for key, table_name in optional.items():
            try:
                tbl = getattr(app_tables, table_name, None)
                if tbl:
                    tables[key] = len(tbl.search())
            except Exception:
                tables[key] = -1

        elapsed_ms = round((time.time() - t0) * 1000, 1)

        return {
            'success': True,
            'timestamp': get_utc_now().isoformat(),
            'collection_time_ms': elapsed_ms,
            'tables': tables,
            'caches': _cache_stats(),
            'database': _check_db_health(),
        }
    except Exception as e:
        logger.exception("get_system_metrics error: %s", e)
        return {'success': False, 'message': 'Failed to collect system metrics.'}


# =========================================================
# HTTP Endpoints for External Monitoring Dashboard
# =========================================================

def _json_response(data, status=200):
    """Create a JSON HTTP response with CORS headers."""
    return anvil.server.HttpResponse(
        status=status,
        body=json.dumps(data, ensure_ascii=False, default=str),
        headers={
            'Content-Type': 'application/json; charset=utf-8',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
        }
    )


@anvil.server.http_endpoint('/api/health', methods=['GET', 'OPTIONS'])
def http_health_check(**params):
    """
    External health check endpoint.
    Usage: GET /api/health?token=<session_token>
    """
    if anvil.server.request.method == 'OPTIONS':
        return _json_response({})

    token = params.get('token', '')
    if not token:
        return _json_response({'success': False, 'message': 'Token required'}, 401)

    result = health_check(token)
    status = 200 if result.get('success') else 503
    return _json_response(result, status)


@anvil.server.http_endpoint('/api/metrics', methods=['GET', 'OPTIONS'])
def http_system_metrics(**params):
    """
    External system metrics endpoint (admin only).
    Usage: GET /api/metrics?token=<admin_session_token>
    """
    if anvil.server.request.method == 'OPTIONS':
        return _json_response({})

    token = params.get('token', '')
    if not token:
        return _json_response({'success': False, 'message': 'Token required'}, 401)

    result = get_system_metrics(token)
    status = 200 if result.get('success') else 403
    return _json_response(result, status)

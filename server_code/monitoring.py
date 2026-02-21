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
import secrets as _secrets

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
    from .auth_constants import MONITORING_API_KEY
except ImportError:
    try:
        from auth_constants import MONITORING_API_KEY
    except ImportError:
        MONITORING_API_KEY = None

try:
    from .cache_manager import (
        dashboard_cache, tags_cache, report_cache,
        fx_rate_cache, accounting_dashboard_cache,
        payment_dashboard_cache, dashboard_stats_cache,
    )
except ImportError:
    try:
        from cache_manager import (
            dashboard_cache, tags_cache, report_cache,
            fx_rate_cache, accounting_dashboard_cache,
            payment_dashboard_cache, dashboard_stats_cache,
        )
    except Exception:
        # Fallback: dummy caches if cache_manager unavailable
        class _DummyCache:
            def get(self, k): return None
            def set(self, k, v): pass
            def invalidate(self): pass
        dashboard_cache = tags_cache = report_cache = _DummyCache()
        fx_rate_cache = accounting_dashboard_cache = _DummyCache()
        payment_dashboard_cache = dashboard_stats_cache = _DummyCache()

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


def _get_monitoring_key():
    """Get monitoring API key: Anvil Secrets first, then settings table."""
    if MONITORING_API_KEY:
        return MONITORING_API_KEY
    try:
        row = app_tables.settings.get(setting_key='monitoring_api_key')
        if row:
            return row['setting_value'] or None
    except Exception:
        pass
    return None


def _check_monitoring_auth(token):
    """Check if token is a valid monitoring API key or session token.
    Returns (is_valid, user_email, error_dict_or_None)."""
    if not token:
        return False, None, {'success': False, 'message': 'Token required'}
    api_key = _get_monitoring_key()
    if api_key and _secrets.compare_digest(str(token), str(api_key)):
        return True, 'monitoring@system', None
    return _require_authenticated(token)


# =========================================================
# Public callables
# =========================================================

@anvil.server.callable
def health_check(token_or_email=None):
    """
    Quick health check — returns system status.
    Accepts monitoring API key (permanent) or session token.
    """
    is_valid, user_email, error = _check_monitoring_auth(token_or_email)
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
    Detailed system metrics — admin only (or monitoring API key).
    Returns table row counts, cache stats, session info.
    """
    is_valid, user_email, error = _check_monitoring_auth(token_or_email)
    if not is_valid:
        # Fall back to admin session check
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


@anvil.server.callable
def generate_monitoring_api_key(token):
    """Generate a new monitoring API key (admin only). Saves to settings table."""
    is_valid, user_email, error = _require_permission(token, 'admin')
    if not is_valid:
        return error
    new_key = _secrets.token_urlsafe(32)
    try:
        row = app_tables.settings.get(setting_key='monitoring_api_key')
        if row:
            row.update(setting_value=new_key, updated_by=user_email, updated_at=get_utc_now())
        else:
            app_tables.settings.add_row(
                setting_key='monitoring_api_key',
                setting_value=new_key,
                setting_type='text',
                description='Permanent API key for external monitoring',
                updated_by=user_email,
                updated_at=get_utc_now(),
            )
        logger.info("Monitoring API key generated by %s", user_email)
        return {'success': True, 'api_key': new_key}
    except Exception as e:
        logger.error("generate_monitoring_api_key error: %s", e)
        return {'success': False, 'message': 'Failed to generate API key.'}


@anvil.server.callable
def revoke_monitoring_api_key(token):
    """Revoke the monitoring API key (admin only)."""
    is_valid, user_email, error = _require_permission(token, 'admin')
    if not is_valid:
        return error
    try:
        row = app_tables.settings.get(setting_key='monitoring_api_key')
        if row:
            row.delete()
            logger.info("Monitoring API key revoked by %s", user_email)
        return {'success': True, 'message': 'API key revoked.'}
    except Exception as e:
        logger.error("revoke_monitoring_api_key error: %s", e)
        return {'success': False, 'message': 'Failed to revoke API key.'}


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


try:
    @anvil.server.http_endpoint('/api/health', enable_cors=True)
    def http_health_check(**params):
        """
        External health check endpoint.
        Usage: GET /api/health?token=<session_token>
        """
        token = params.get('token', '')
        if not token:
            return _json_response({'success': False, 'message': 'Token required'}, 401)

        result = health_check(token)
        status = 200 if result.get('success') else 503
        return _json_response(result, status)


    @anvil.server.http_endpoint('/api/metrics', enable_cors=True)
    def http_system_metrics(**params):
        """
        External system metrics endpoint (admin only).
        Usage: GET /api/metrics?token=<admin_session_token>
        """
        token = params.get('token', '')
        if not token:
            return _json_response({'success': False, 'message': 'Token required'}, 401)

        result = get_system_metrics(token)
        status = 200 if result.get('success') else 403
        return _json_response(result, status)
except Exception as _http_err:
    logger.warning("HTTP endpoints could not be registered: %s", _http_err)

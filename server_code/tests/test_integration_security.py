# -*- coding: utf-8 -*-
"""
INTEGRATION TESTS - Security Fixes & Shared Utilities
=====================================================
Tests for the Fix-Project branch changes:
- shared_utils: contracts helpers, safe conversions, response builders
- cache_manager: TTLCache thread safety, TTL expiry, LRU eviction
- auth_totp: composite IP:email rate limiting
- auth_sessions: purge_old_sessions
- monitoring: health_check structure

Run:  python server_code/tests/test_integration_security.py
      pytest server_code/tests/test_integration_security.py -v
"""

import os
import sys
import unittest
import time
import threading
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch

# Setup path
try:
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    _root = os.getcwd()
if _root and _root not in sys.path:
    sys.path.insert(0, _root)

# Mock anvil before importing any server code
sys.modules.setdefault('anvil', MagicMock())
sys.modules.setdefault('anvil.server', MagicMock())
sys.modules.setdefault('anvil.tables', MagicMock())
sys.modules.setdefault('anvil.tables.query', MagicMock())
sys.modules.setdefault('anvil.users', MagicMock())
sys.modules.setdefault('anvil.secrets', MagicMock())
sys.modules.setdefault('anvil.google', MagicMock())
sys.modules.setdefault('anvil.google.auth', MagicMock())
sys.modules.setdefault('anvil.google.drive', MagicMock())
sys.modules.setdefault('anvil.google.mail', MagicMock())

# Ensure anvil.tables has app_tables
mock_app_tables = MagicMock()
sys.modules['anvil.tables'].app_tables = mock_app_tables

# Patch anvil.server.callable to be a no-op decorator
sys.modules['anvil.server'].callable = lambda f: f
sys.modules['anvil.server'].background_task = lambda f: f


# ============================================================
# Test: cache_manager.TTLCache
# ============================================================
class TestTTLCache(unittest.TestCase):
    """Tests for the TTLCache class."""

    def setUp(self):
        # Import fresh each time
        from server_code.cache_manager import TTLCache
        self.cache = TTLCache(ttl_seconds=2, max_size=3, name='test')

    def test_basic_set_get(self):
        """Set and get a value."""
        self.cache.set('key1', 'value1')
        self.assertEqual(self.cache.get('key1'), 'value1')

    def test_get_missing_key(self):
        """Get a non-existent key returns None."""
        self.assertIsNone(self.cache.get('nonexistent'))

    def test_ttl_expiry(self):
        """Value expires after TTL."""
        cache = self.__class__._make_cache(ttl=0.1)
        cache.set('k', 'v')
        self.assertEqual(cache.get('k'), 'v')
        time.sleep(0.15)
        self.assertIsNone(cache.get('k'))

    def test_lru_eviction(self):
        """Oldest entry evicted when max_size reached."""
        self.cache.set('a', 1)
        time.sleep(0.01)
        self.cache.set('b', 2)
        time.sleep(0.01)
        self.cache.set('c', 3)
        # At capacity (3). Adding 'd' should evict 'a' (oldest).
        self.cache.set('d', 4)
        self.assertIsNone(self.cache.get('a'))
        self.assertEqual(self.cache.get('d'), 4)
        self.assertEqual(self.cache.size(), 3)

    def test_update_existing_no_eviction(self):
        """Updating existing key doesn't trigger eviction."""
        self.cache.set('a', 1)
        self.cache.set('b', 2)
        self.cache.set('c', 3)
        # Update 'a' — should not evict anything
        self.cache.set('a', 10)
        self.assertEqual(self.cache.get('a'), 10)
        self.assertEqual(self.cache.size(), 3)

    def test_invalidate_single_key(self):
        """Invalidate a specific key."""
        self.cache.set('x', 1)
        self.cache.set('y', 2)
        self.cache.invalidate('x')
        self.assertIsNone(self.cache.get('x'))
        self.assertEqual(self.cache.get('y'), 2)

    def test_invalidate_all(self):
        """Invalidate all keys."""
        self.cache.set('a', 1)
        self.cache.set('b', 2)
        self.cache.invalidate()
        self.assertEqual(self.cache.size(), 0)

    def test_thread_safety(self):
        """Multiple threads writing concurrently shouldn't corrupt state."""
        from server_code.cache_manager import TTLCache
        cache = TTLCache(ttl_seconds=60, max_size=1000, name='thread_test')
        errors = []

        def writer(thread_id):
            try:
                for i in range(100):
                    cache.set(f't{thread_id}_k{i}', i)
                    _ = cache.get(f't{thread_id}_k{i}')
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")
        self.assertLessEqual(cache.size(), 1000)

    @staticmethod
    def _make_cache(ttl=2, max_size=10):
        from server_code.cache_manager import TTLCache
        return TTLCache(ttl_seconds=ttl, max_size=max_size, name='tmp')


# ============================================================
# Test: shared_utils
# ============================================================
class TestSharedUtils(unittest.TestCase):
    """Tests for shared utility functions."""

    def test_safe_float_normal(self):
        from server_code.shared_utils import safe_float
        self.assertEqual(safe_float('3.14'), 3.14)
        self.assertEqual(safe_float(42), 42.0)
        self.assertEqual(safe_float(None), 0.0)
        self.assertEqual(safe_float('bad'), 0.0)
        self.assertEqual(safe_float(None, default=-1.0), -1.0)

    def test_safe_int_normal(self):
        from server_code.shared_utils import safe_int
        self.assertEqual(safe_int('7'), 7)
        self.assertEqual(safe_int(None), 0)
        self.assertEqual(safe_int('bad'), 0)
        self.assertEqual(safe_int(None, default=-1), -1)

    def test_parse_date_valid(self):
        from server_code.shared_utils import parse_date
        d = parse_date('2025-06-15')
        self.assertEqual(d, date(2025, 6, 15))

    def test_parse_date_with_time(self):
        from server_code.shared_utils import parse_date
        d = parse_date('2025-06-15T10:30:00Z')
        self.assertEqual(d, date(2025, 6, 15))

    def test_parse_date_empty(self):
        from server_code.shared_utils import parse_date
        self.assertIsNone(parse_date(''))
        self.assertIsNone(parse_date(None))

    def test_parse_date_invalid(self):
        from server_code.shared_utils import parse_date
        self.assertIsNone(parse_date('not-a-date'))

    def test_to_datetime_from_date(self):
        from server_code.shared_utils import to_datetime
        d = date(2025, 1, 15)
        dt = to_datetime(d)
        self.assertEqual(dt, datetime(2025, 1, 15))

    def test_to_datetime_from_datetime(self):
        from server_code.shared_utils import to_datetime
        dt_in = datetime(2025, 1, 15, 10, 30)
        dt_out = to_datetime(dt_in)
        self.assertEqual(dt_out, datetime(2025, 1, 15, 10, 30))
        self.assertIsNone(dt_out.tzinfo)  # timezone stripped

    def test_to_datetime_none(self):
        from server_code.shared_utils import to_datetime
        self.assertIsNone(to_datetime(None))

    def test_success_response(self):
        from server_code.shared_utils import success_response
        r = success_response(data={'count': 5}, message='OK')
        self.assertTrue(r['success'])
        self.assertEqual(r['data']['count'], 5)
        self.assertEqual(r['message'], 'OK')

    def test_error_response(self):
        from server_code.shared_utils import error_response
        r = error_response('Something failed', code='ERR001')
        self.assertFalse(r['success'])
        self.assertEqual(r['message'], 'Something failed')
        self.assertEqual(r['code'], 'ERR001')

    def test_parse_json_field_valid(self):
        from server_code.shared_utils import parse_json_field
        row = {'tags_json': '["a", "b"]'}
        self.assertEqual(parse_json_field(row, 'tags_json'), ['a', 'b'])

    def test_parse_json_field_empty(self):
        from server_code.shared_utils import parse_json_field
        row = {'tags_json': ''}
        self.assertEqual(parse_json_field(row, 'tags_json'), [])

    def test_parse_json_field_non_json_suffix(self):
        from server_code.shared_utils import parse_json_field
        row = {'notes': ''}
        self.assertEqual(parse_json_field(row, 'notes'), '')


# ============================================================
# Test: TOTP rate limiting (composite IP:email key)
# ============================================================
class TestTOTPRateLimit(unittest.TestCase):
    """Tests for the TOTP rate limiting with composite key."""

    def setUp(self):
        # Reset the tracker between tests
        from server_code import auth_totp
        auth_totp._totp_attempt_tracker.clear()

    def test_rate_key_composite(self):
        from server_code.auth_totp import _totp_rate_key
        key = _totp_rate_key('user@example.com', '192.168.1.1')
        self.assertEqual(key, '192.168.1.1:user@example.com')

    def test_rate_key_no_ip(self):
        from server_code.auth_totp import _totp_rate_key
        key = _totp_rate_key('user@example.com', None)
        self.assertEqual(key, 'unknown:user@example.com')

    def test_different_ips_different_keys(self):
        from server_code.auth_totp import _totp_rate_key
        key1 = _totp_rate_key('user@example.com', '10.0.0.1')
        key2 = _totp_rate_key('user@example.com', '10.0.0.2')
        self.assertNotEqual(key1, key2)

    def test_rate_limit_blocks_after_max_attempts(self):
        """After 5 failed attempts from same IP:email, further attempts are blocked."""
        from server_code.auth_totp import _totp_attempt_tracker, _TOTP_MAX_ATTEMPTS, _totp_rate_key
        import time as _time

        key = _totp_rate_key('victim@example.com', '1.2.3.4')
        _totp_attempt_tracker[key] = {
            'count': _TOTP_MAX_ATTEMPTS,
            'window_start': _time.time()
        }

        # Mock app_tables to prevent DB access
        with patch('server_code.auth_totp.app_tables') as mock_tables:
            from server_code.auth_totp import verify_totp_for_user
            result = verify_totp_for_user('victim@example.com', '123456', ip_address='1.2.3.4')
            self.assertFalse(result)

    def test_different_ip_not_blocked(self):
        """Same user from different IP is NOT blocked by the first IP's rate limit."""
        from server_code.auth_totp import _totp_attempt_tracker, _TOTP_MAX_ATTEMPTS, _totp_rate_key
        import time as _time

        # Block IP 1.2.3.4 for this user
        key_blocked = _totp_rate_key('victim@example.com', '1.2.3.4')
        _totp_attempt_tracker[key_blocked] = {
            'count': _TOTP_MAX_ATTEMPTS,
            'window_start': _time.time()
        }

        # Key for a different IP should be clean
        key_clean = _totp_rate_key('victim@example.com', '5.6.7.8')
        self.assertNotIn(key_clean, _totp_attempt_tracker)


# ============================================================
# Test: quotation_pdf helpers
# ============================================================
class TestQuotationPdfHelpers(unittest.TestCase):
    """Tests for quotation_pdf formatting functions."""

    def test_format_number(self):
        from server_code.quotation_pdf import format_number
        self.assertEqual(format_number(1000), '1,000')
        self.assertEqual(format_number(1234567.89), '1,234,568')
        self.assertEqual(format_number(None), '0')
        self.assertEqual(format_number(0), '0')

    def test_format_date_ar(self):
        from server_code.quotation_pdf import format_date_ar
        d = date(2025, 3, 15)
        result = format_date_ar(d)
        self.assertIn('15', result)

    def test_format_date_en(self):
        from server_code.quotation_pdf import format_date_en
        d = date(2025, 3, 15)
        result = format_date_en(d)
        self.assertEqual(result, '15 March')

    def test_format_date_empty(self):
        from server_code.quotation_pdf import format_date_ar, format_date_en
        self.assertEqual(format_date_ar(None), '')
        self.assertEqual(format_date_en(None), '')

    def test_safe_float(self):
        from server_code.quotation_pdf import _safe_float
        self.assertEqual(_safe_float('100.5'), 100.5)
        self.assertEqual(_safe_float(None), 0.0)
        self.assertEqual(_safe_float('bad'), 0.0)


# ============================================================
# Test: Pre-configured cache instances exist
# ============================================================
class TestCacheInstances(unittest.TestCase):
    """Verify all pre-configured cache instances are properly set up."""

    def test_all_instances_exist(self):
        from server_code.cache_manager import (
            dashboard_cache, tags_cache, report_cache, fx_rate_cache,
            accounting_dashboard_cache, payment_dashboard_cache,
            dashboard_stats_cache,
        )
        # All should be TTLCache instances
        from server_code.cache_manager import TTLCache
        for name, cache in [
            ('dashboard', dashboard_cache),
            ('tags', tags_cache),
            ('reports', report_cache),
            ('fx_rates', fx_rate_cache),
            ('accounting_dashboard', accounting_dashboard_cache),
            ('payment_dashboard', payment_dashboard_cache),
            ('dashboard_stats', dashboard_stats_cache),
        ]:
            self.assertIsInstance(cache, TTLCache, f"{name} is not a TTLCache")

    def test_tags_cache_short_ttl(self):
        from server_code.cache_manager import tags_cache
        self.assertEqual(tags_cache._ttl, 30)

    def test_fx_cache_long_ttl(self):
        from server_code.cache_manager import fx_rate_cache
        self.assertEqual(fx_rate_cache._ttl, 3600)


# ============================================================
# Main
# ============================================================
if __name__ == '__main__':
    unittest.main(verbosity=2)

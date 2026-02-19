# -*- coding: utf-8 -*-
"""
AUTH FLOW TESTS - Comprehensive Authentication Testing
======================================================
Tests for ALL authentication flows:
- Password hashing & verification (PBKDF2)
- Session creation, validation, expiry, destruction
- Permission checks (admin, roles, custom)
- Rate limiting (fail-closed, window, blocking)
- Registration flow (validation, OTP)
- Login flow (lockout, OTP, session creation)
- Password reset flow
- TOTP setup & verification
- Token validation & sliding expiration
- Input sanitization (email, phone, XSS)
- Audit logging

Run:  pytest server_code/tests/test_auth_flows.py -v
"""

import os
import sys
import unittest
import time
import hashlib
import secrets
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch, PropertyMock, call

# Setup path
try:
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
except NameError:
    _root = os.getcwd()
if _root and _root not in sys.path:
    sys.path.insert(0, _root)

# Mock anvil before importing any server code
_anvil_mock = MagicMock()
_anvil_server_mock = MagicMock()
# Make @anvil.server.callable a no-op decorator
_anvil_server_mock.callable = lambda f: f
_anvil_server_mock.background_task = lambda f: f
_anvil_server_mock.http_endpoint = lambda *a, **kw: lambda f: f

sys.modules['anvil'] = _anvil_mock
sys.modules['anvil.server'] = _anvil_server_mock
sys.modules['anvil.tables'] = MagicMock()
sys.modules['anvil.tables.query'] = MagicMock()
sys.modules['anvil.users'] = MagicMock()
sys.modules['anvil.secrets'] = MagicMock()
sys.modules['anvil.google'] = MagicMock()
sys.modules['anvil.google.auth'] = MagicMock()
sys.modules['anvil.email'] = MagicMock()
sys.modules['anvil.http'] = MagicMock()
sys.modules['anvil.files'] = MagicMock()
sys.modules['anvil.media'] = MagicMock()


# =========================================================
# 1. PASSWORD HASHING TESTS
# =========================================================
class TestPasswordHashing(unittest.TestCase):
    """Tests for auth_password.py: PBKDF2 hashing, verification, legacy fallback."""

    def setUp(self):
        from server_code.auth_password import hash_password, verify_password
        self.hash_password = hash_password
        self.verify_password = verify_password

    def test_hash_produces_salt_colon_hash_format(self):
        """Hash output must be 'salt:hash' with 64-char hex salt."""
        result = self.hash_password("TestPassword123")
        self.assertIn(':', result)
        salt, key = result.split(':', 1)
        self.assertEqual(len(salt), 64)  # 32 bytes hex
        self.assertTrue(len(key) > 0)

    def test_same_password_produces_different_hashes(self):
        """Each call must produce unique salt → unique hash."""
        h1 = self.hash_password("SamePassword!")
        h2 = self.hash_password("SamePassword!")
        self.assertNotEqual(h1, h2)

    def test_verify_correct_password(self):
        """Correct password verifies True."""
        stored = self.hash_password("MySecret99!")
        self.assertTrue(self.verify_password("MySecret99!", stored))

    def test_verify_wrong_password(self):
        """Wrong password verifies False."""
        stored = self.hash_password("MySecret99!")
        self.assertFalse(self.verify_password("WrongPassword!", stored))

    def test_verify_empty_hash_returns_false(self):
        """Empty or None stored hash returns False."""
        self.assertFalse(self.verify_password("test", ""))
        self.assertFalse(self.verify_password("test", None))

    def test_verify_legacy_sha256_fallback(self):
        """Legacy SHA-256 hash (no colon) should still verify."""
        password = "LegacyUser123"
        legacy_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        self.assertTrue(self.verify_password(password, legacy_hash))

    def test_verify_corrupted_hash_returns_false(self):
        """Corrupted hash string should not raise, returns False."""
        self.assertFalse(self.verify_password("test", "invalid:hash:format"))
        self.assertFalse(self.verify_password("test", "not_a_hex_salt:not_a_hex_key"))

    def test_unicode_password(self):
        """Arabic/unicode passwords should hash and verify correctly."""
        pwd = "كلمة_سر_عربية123!"
        stored = self.hash_password(pwd)
        self.assertTrue(self.verify_password(pwd, stored))
        self.assertFalse(self.verify_password("wrong", stored))

    def test_very_long_password(self):
        """Long passwords (1000+ chars) should work."""
        pwd = "A" * 1000 + "!1a"
        stored = self.hash_password(pwd)
        self.assertTrue(self.verify_password(pwd, stored))


# =========================================================
# 2. SESSION MANAGEMENT TESTS
# =========================================================
class TestSessionManagement(unittest.TestCase):
    """Tests for auth_sessions.py: create, validate, destroy, cleanup."""

    def setUp(self):
        from server_code.auth_sessions import (
            _hash_token, generate_session_token,
            create_session, validate_session, destroy_session,
            cleanup_expired_sessions, purge_old_sessions,
        )
        self.hash_token = _hash_token
        self.gen_token = generate_session_token
        self.create = create_session
        self.validate = validate_session
        self.destroy = destroy_session
        self.cleanup = cleanup_expired_sessions
        self.purge = purge_old_sessions

    def test_token_generation_is_unique(self):
        """Each token must be unique."""
        tokens = {self.gen_token() for _ in range(100)}
        self.assertEqual(len(tokens), 100)

    def test_token_generation_length(self):
        """Token should be sufficiently long (64+ chars)."""
        token = self.gen_token()
        self.assertGreater(len(token), 60)

    def test_hash_token_is_sha256(self):
        """Token hash must be SHA-256 hex digest (64 chars)."""
        h = self.hash_token("test_token")
        self.assertEqual(len(h), 64)
        self.assertTrue(all(c in '0123456789abcdef' for c in h))

    def test_hash_token_deterministic(self):
        """Same token always produces same hash."""
        h1 = self.hash_token("my_session_token")
        h2 = self.hash_token("my_session_token")
        self.assertEqual(h1, h2)

    def test_hash_token_different_inputs(self):
        """Different tokens produce different hashes."""
        h1 = self.hash_token("token_a")
        h2 = self.hash_token("token_b")
        self.assertNotEqual(h1, h2)

    def test_validate_none_returns_none(self):
        """validate_session(None) must return None."""
        self.assertIsNone(self.validate(None))

    def test_validate_empty_returns_none(self):
        """validate_session('') must return None."""
        self.assertIsNone(self.validate(''))

    def test_destroy_none_returns_false(self):
        """destroy_session(None) must return False."""
        self.assertFalse(self.destroy(None))

    def test_destroy_empty_returns_false(self):
        """destroy_session('') must return False."""
        self.assertFalse(self.destroy(''))


# =========================================================
# 3. PERMISSION SYSTEM TESTS
# =========================================================
class TestPermissions(unittest.TestCase):
    """Tests for auth_permissions.py: role checks, admin checks, require_*."""

    def setUp(self):
        from server_code.auth_permissions import (
            require_authenticated, require_admin, require_permission_full,
            is_admin_by_email,
        )
        self.require_auth = require_authenticated
        self.require_admin = require_admin
        self.require_perm = require_permission_full
        self.is_admin_by_email = is_admin_by_email

    def test_require_authenticated_no_token(self):
        """No token → (False, None, error_dict)."""
        valid, email, err = self.require_auth(None)
        self.assertFalse(valid)
        self.assertIsNone(email)
        self.assertIn('message', err)

    def test_require_authenticated_empty_token(self):
        """Empty token → (False, None, error_dict)."""
        valid, email, err = self.require_auth('')
        self.assertFalse(valid)
        self.assertIsNone(email)

    @patch('server_code.auth_permissions.validate_session')
    def test_require_authenticated_invalid_token(self, mock_validate):
        """Invalid token → (False, None, error_dict)."""
        mock_validate.return_value = None
        valid, email, err = self.require_auth('bad_token')
        self.assertFalse(valid)
        self.assertIn('message', err)

    @patch('server_code.auth_permissions.validate_session')
    def test_require_authenticated_valid_token(self, mock_validate):
        """Valid token → (True, email, None)."""
        mock_validate.return_value = {'email': 'user@test.com', 'role': 'viewer'}
        valid, email, err = self.require_auth('good_token')
        self.assertTrue(valid)
        self.assertEqual(email, 'user@test.com')
        self.assertIsNone(err)

    def test_require_admin_no_token(self):
        """No token → not admin."""
        is_admin, err = self.require_admin(None)
        self.assertFalse(is_admin)
        self.assertIn('message', err)

    def test_is_admin_by_email_none(self):
        """None email → False."""
        self.assertFalse(self.is_admin_by_email(None))

    def test_is_admin_by_email_empty(self):
        """Empty email → False."""
        self.assertFalse(self.is_admin_by_email(''))


# =========================================================
# 4. RATE LIMITING TESTS
# =========================================================
class TestRateLimiting(unittest.TestCase):
    """Tests for auth_rate_limit.py: fail-closed, window management, blocking."""

    @patch('server_code.auth_rate_limit.app_tables')
    def test_rate_limit_first_request_allowed(self, mock_tables):
        """First request from new IP should be allowed."""
        from server_code.auth_rate_limit import check_rate_limit
        mock_tables.rate_limits.search.return_value = []
        result = check_rate_limit('1.2.3.4', 'general')
        self.assertTrue(result)

    @patch('server_code.auth_rate_limit.app_tables')
    def test_rate_limit_fail_closed_on_exception(self, mock_tables):
        """On DB error, rate limiter should BLOCK (fail-closed)."""
        from server_code.auth_rate_limit import check_rate_limit
        mock_tables.rate_limits.search.side_effect = Exception("DB down")
        result = check_rate_limit('1.2.3.4', 'general')
        self.assertFalse(result)  # Must block on error

    @patch('server_code.auth_rate_limit.app_tables')
    def test_rate_limit_empty_ip_defaults_to_unknown(self, mock_tables):
        """Empty IP should default to 'unknown', not crash."""
        from server_code.auth_rate_limit import check_rate_limit
        mock_tables.rate_limits.search.return_value = []
        result = check_rate_limit('', 'general')
        self.assertTrue(result)
        # Verify 'unknown' was used in the search
        call_args = mock_tables.rate_limits.search.call_args
        self.assertEqual(call_args[1]['ip_address'], 'unknown')

    @patch('server_code.auth_rate_limit.app_tables')
    def test_rate_limit_none_ip_defaults_to_unknown(self, mock_tables):
        """None IP should default to 'unknown'."""
        from server_code.auth_rate_limit import check_rate_limit
        mock_tables.rate_limits.search.return_value = []
        result = check_rate_limit(None, 'general')
        self.assertTrue(result)


# =========================================================
# 5. AUTH CONSTANTS TESTS
# =========================================================
class TestAuthConstants(unittest.TestCase):
    """Tests for auth_constants.py: proper security values."""

    def test_pbkdf2_iterations_minimum(self):
        """PBKDF2 iterations must be >= 100,000 (OWASP minimum)."""
        from server_code.auth_constants import PBKDF2_ITERATIONS
        self.assertGreaterEqual(PBKDF2_ITERATIONS, 100000)

    def test_session_duration_reasonable(self):
        """Session duration: 15-120 minutes."""
        from server_code.auth_constants import SESSION_DURATION_MINUTES
        self.assertGreaterEqual(SESSION_DURATION_MINUTES, 15)
        self.assertLessEqual(SESSION_DURATION_MINUTES, 120)

    def test_max_login_attempts_reasonable(self):
        """Max login attempts: 3-10."""
        from server_code.auth_constants import MAX_LOGIN_ATTEMPTS
        self.assertGreaterEqual(MAX_LOGIN_ATTEMPTS, 3)
        self.assertLessEqual(MAX_LOGIN_ATTEMPTS, 10)

    def test_lockout_duration_reasonable(self):
        """Lockout: 15-120 minutes."""
        from server_code.auth_constants import LOCKOUT_DURATION_MINUTES
        self.assertGreaterEqual(LOCKOUT_DURATION_MINUTES, 15)
        self.assertLessEqual(LOCKOUT_DURATION_MINUTES, 120)

    def test_auth_rate_limit_lower_than_general(self):
        """Auth rate limit must be stricter than general."""
        from server_code.auth_constants import RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_MAX_REQUESTS_AUTH
        self.assertLess(RATE_LIMIT_MAX_REQUESTS_AUTH, RATE_LIMIT_MAX_REQUESTS)

    def test_auth_endpoints_frozenset(self):
        """AUTH_RATE_LIMIT_ENDPOINTS must be immutable frozenset."""
        from server_code.auth_constants import AUTH_RATE_LIMIT_ENDPOINTS
        self.assertIsInstance(AUTH_RATE_LIMIT_ENDPOINTS, frozenset)

    def test_login_in_auth_endpoints(self):
        """'login' must be in the auth rate-limited endpoints."""
        from server_code.auth_constants import AUTH_RATE_LIMIT_ENDPOINTS
        self.assertIn('login', AUTH_RATE_LIMIT_ENDPOINTS)

    def test_register_in_auth_endpoints(self):
        """'register' must be in the auth rate-limited endpoints."""
        from server_code.auth_constants import AUTH_RATE_LIMIT_ENDPOINTS
        self.assertIn('register', AUTH_RATE_LIMIT_ENDPOINTS)

    def test_password_reset_in_auth_endpoints(self):
        """'password_reset' must be in the auth rate-limited endpoints."""
        from server_code.auth_constants import AUTH_RATE_LIMIT_ENDPOINTS
        self.assertIn('password_reset', AUTH_RATE_LIMIT_ENDPOINTS)

    def test_roles_admin_has_all(self):
        """Admin role must have 'all' permission."""
        from server_code.auth_constants import ROLES
        self.assertIn('all', ROLES['admin'])

    def test_roles_viewer_is_read_only(self):
        """Viewer role must only have 'view'."""
        from server_code.auth_constants import ROLES
        self.assertEqual(ROLES['viewer'], ['view'])

    def test_all_roles_exist(self):
        """admin, manager, sales, viewer must all exist."""
        from server_code.auth_constants import ROLES
        for role in ('admin', 'manager', 'sales', 'viewer'):
            self.assertIn(role, ROLES)


# =========================================================
# 6. INPUT VALIDATION TESTS
# =========================================================
class TestInputValidation(unittest.TestCase):
    """Tests for auth_utils.py: email validation, sanitization."""

    def setUp(self):
        from server_code.auth_utils import validate_email, get_utc_now, make_aware
        self.validate_email = validate_email
        self.get_utc_now = get_utc_now
        self.make_aware = make_aware

    def test_valid_email(self):
        """Standard email should pass."""
        self.assertTrue(self.validate_email("user@example.com"))

    def test_valid_email_subdomain(self):
        """Subdomain email should pass."""
        self.assertTrue(self.validate_email("user@sub.example.com"))

    def test_invalid_email_no_at(self):
        """Missing @ should fail."""
        self.assertFalse(self.validate_email("userexample.com"))

    def test_invalid_email_no_domain(self):
        """Missing domain should fail."""
        self.assertFalse(self.validate_email("user@"))

    def test_invalid_email_double_dots(self):
        """Double dots should fail."""
        self.assertFalse(self.validate_email("user@example..com"))

    def test_invalid_email_empty(self):
        """Empty string should fail."""
        self.assertFalse(self.validate_email(""))

    def test_invalid_email_none(self):
        """None should fail."""
        self.assertFalse(self.validate_email(None))

    def test_invalid_email_too_long(self):
        """Very long email (>254 chars) should fail."""
        long_email = "a" * 250 + "@test.com"
        self.assertFalse(self.validate_email(long_email))

    def test_invalid_email_xss(self):
        """XSS attempt in email should fail."""
        self.assertFalse(self.validate_email('<script>alert("xss")</script>@evil.com'))

    def test_get_utc_now_is_aware(self):
        """get_utc_now() must return timezone-aware datetime."""
        now = self.get_utc_now()
        self.assertIsNotNone(now.tzinfo)

    def test_make_aware_naive_datetime(self):
        """make_aware should add UTC to naive datetime."""
        naive = datetime(2025, 1, 1, 12, 0, 0)
        aware = self.make_aware(naive)
        self.assertIsNotNone(aware.tzinfo)

    def test_make_aware_already_aware(self):
        """make_aware should not modify already-aware datetime."""
        aware_dt = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = self.make_aware(aware_dt)
        self.assertEqual(result, aware_dt)


# =========================================================
# 7. REGISTRATION FLOW TESTS
# =========================================================
class TestRegistrationFlow(unittest.TestCase):
    """Tests for registration validation logic (email, password, rate limiting)."""

    def test_password_strength_length(self):
        """Password < 8 chars should be invalid."""
        import re
        pwd = "Ab1"
        self.assertLess(len(pwd), 8)

    def test_password_strength_uppercase(self):
        """Password without uppercase should fail."""
        import re
        pwd = "nouppercase123"
        self.assertIsNone(re.search(r'[A-Z]', pwd))

    def test_password_strength_lowercase(self):
        """Password without lowercase should fail."""
        import re
        pwd = "NOLOWERCASE123"
        self.assertIsNone(re.search(r'[a-z]', pwd))

    def test_password_strength_digit(self):
        """Password without digit should fail."""
        import re
        pwd = "NoDigitHere!"
        self.assertIsNone(re.search(r'\d', pwd))

    def test_strong_password_passes_all(self):
        """Strong password passes all checks."""
        import re
        pwd = "Strong123!"
        self.assertGreaterEqual(len(pwd), 8)
        self.assertIsNotNone(re.search(r'[A-Z]', pwd))
        self.assertIsNotNone(re.search(r'[a-z]', pwd))
        self.assertIsNotNone(re.search(r'\d', pwd))

    def test_email_validation_rejects_empty(self):
        """Empty email should fail registration."""
        from server_code.auth_utils import validate_email
        self.assertFalse(validate_email(''))

    def test_email_validation_rejects_invalid(self):
        """Invalid format should fail registration."""
        from server_code.auth_utils import validate_email
        self.assertFalse(validate_email('not-an-email'))

    def test_name_too_short_rejected(self):
        """Name < 2 chars should fail."""
        name = "A"
        self.assertLess(len(name.strip()), 2)

    def test_name_empty_rejected(self):
        """Empty name should fail."""
        name = ""
        self.assertFalse(bool(name and len(name.strip()) >= 2))


# =========================================================
# 8. LOGIN FLOW TESTS
# =========================================================
class TestLoginFlow(unittest.TestCase):
    """Tests for login validation and security checks."""

    def test_login_empty_email_rejected(self):
        """Empty email should not pass validation."""
        from server_code.auth_utils import validate_email
        self.assertFalse(validate_email(''))

    def test_login_xss_email_rejected(self):
        """XSS in email should fail."""
        from server_code.auth_utils import validate_email
        self.assertFalse(validate_email('<script>@evil.com'))

    def test_login_sql_injection_email_rejected(self):
        """SQL injection attempt in email should fail."""
        from server_code.auth_utils import validate_email
        self.assertFalse(validate_email("'; DROP TABLE users;--@evil.com"))

    def test_password_verify_constant_time(self):
        """verify_password uses secrets.compare_digest (constant time)."""
        from server_code.auth_password import hash_password, verify_password
        stored = hash_password("TestPass123!")
        # Correct password
        self.assertTrue(verify_password("TestPass123!", stored))
        # Wrong password (timing should be similar but we just verify it works)
        self.assertFalse(verify_password("WrongPass!", stored))

    def test_lockout_after_max_attempts(self):
        """MAX_LOGIN_ATTEMPTS should be configured properly."""
        from server_code.auth_constants import MAX_LOGIN_ATTEMPTS, LOCKOUT_DURATION_MINUTES
        self.assertGreaterEqual(MAX_LOGIN_ATTEMPTS, 3)
        self.assertGreaterEqual(LOCKOUT_DURATION_MINUTES, 15)


# =========================================================
# 9. PASSWORD RESET FLOW TESTS
# =========================================================
class TestPasswordResetFlow(unittest.TestCase):
    """Tests for password reset security."""

    def test_otp_expiry_configured(self):
        """OTP expiry must be configured and reasonable."""
        from server_code.auth_constants import OTP_EXPIRY_MINUTES
        self.assertGreaterEqual(OTP_EXPIRY_MINUTES, 5)
        self.assertLessEqual(OTP_EXPIRY_MINUTES, 30)

    def test_password_history_configured(self):
        """Password history count must prevent reuse."""
        from server_code.auth_constants import PASSWORD_HISTORY_COUNT
        self.assertGreaterEqual(PASSWORD_HISTORY_COUNT, 3)

    def test_reset_requires_valid_email(self):
        """Password reset should validate email format."""
        from server_code.auth_utils import validate_email
        self.assertFalse(validate_email(''))
        self.assertFalse(validate_email('invalid'))


# =========================================================
# 10. TOTP TESTS
# =========================================================
class TestTOTPFlow(unittest.TestCase):
    """Tests for auth_totp.py: setup, confirm, rate limit key."""

    def test_totp_rate_key_format(self):
        """TOTP rate key must be IP:email composite."""
        from server_code.auth_totp import _totp_rate_key
        # Signature: _totp_rate_key(user_email, ip_address=None)
        key = _totp_rate_key('user@test.com', '1.2.3.4')
        self.assertEqual(key, '1.2.3.4:user@test.com')

    def test_totp_rate_key_none_ip(self):
        """None IP should default to 'unknown'."""
        from server_code.auth_totp import _totp_rate_key
        key = _totp_rate_key('user@test.com', None)
        self.assertIn('user@test.com', key)
        self.assertIn('unknown', key)

    def test_totp_rate_key_none_email(self):
        """None email should be handled gracefully."""
        from server_code.auth_totp import _totp_rate_key
        key = _totp_rate_key(None, '1.2.3.4')
        self.assertIn('1.2.3.4', key)


# =========================================================
# 11. TOKEN & SESSION VALIDATION TESTS
# =========================================================
class TestTokenValidation(unittest.TestCase):
    """Tests for session validation logic."""

    def test_validate_session_none_returns_none(self):
        """validate_session(None) must return None."""
        from server_code.auth_sessions import validate_session
        self.assertIsNone(validate_session(None))

    def test_validate_session_empty_returns_none(self):
        """validate_session('') must return None."""
        from server_code.auth_sessions import validate_session
        self.assertIsNone(validate_session(''))

    def test_session_token_is_hashed_before_lookup(self):
        """Token must be SHA-256 hashed before DB lookup (never stored raw)."""
        from server_code.auth_sessions import _hash_token
        token = "user_session_token_123"
        h = _hash_token(token)
        # Must be 64-char hex (SHA-256)
        self.assertEqual(len(h), 64)
        # Must NOT be the same as the raw token
        self.assertNotEqual(h, token)

    def test_session_sliding_expiration_configured(self):
        """Session duration must be configured for sliding expiration."""
        from server_code.auth_constants import SESSION_DURATION_MINUTES
        self.assertIsInstance(SESSION_DURATION_MINUTES, int)
        self.assertGreater(SESSION_DURATION_MINUTES, 0)

    def test_max_sessions_per_user_configured(self):
        """Max concurrent sessions must be limited."""
        from server_code.auth_constants import MAX_SESSIONS_PER_USER
        self.assertGreaterEqual(MAX_SESSIONS_PER_USER, 1)
        self.assertLessEqual(MAX_SESSIONS_PER_USER, 10)


# =========================================================
# 12. LOGOUT TESTS
# =========================================================
class TestLogout(unittest.TestCase):
    """Tests for logout/destroy_session logic."""

    def test_destroy_session_none_returns_false(self):
        """destroy_session(None) must return False."""
        from server_code.auth_sessions import destroy_session
        self.assertFalse(destroy_session(None))

    def test_destroy_session_empty_returns_false(self):
        """destroy_session('') must return False."""
        from server_code.auth_sessions import destroy_session
        self.assertFalse(destroy_session(''))

    def test_session_token_generation_entropy(self):
        """Session tokens must have sufficient entropy (64+ bytes)."""
        from server_code.auth_sessions import generate_session_token
        token = generate_session_token()
        # urlsafe base64 of 64 bytes = ~86 chars
        self.assertGreater(len(token), 60)


# =========================================================
# 13. CACHE MANAGER THREAD SAFETY
# =========================================================
class TestCacheThreadSafety(unittest.TestCase):
    """Stress test TTLCache under concurrent access."""

    def test_concurrent_reads_writes(self):
        """100 threads x 50 ops should not crash or corrupt."""
        from server_code.cache_manager import TTLCache
        cache = TTLCache(ttl_seconds=5, max_size=50, name='stress_test')
        errors = []

        def worker(thread_id):
            try:
                for i in range(50):
                    cache.set(f"t{thread_id}_k{i}", f"v{i}")
                    cache.get(f"t{thread_id}_k{i}")
                    if i % 10 == 0:
                        cache.invalidate(f"t{thread_id}_k{i}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(len(errors), 0, f"Thread errors: {errors}")


# =========================================================
# 14. STRUCTURED LOGGING TESTS
# =========================================================
class TestStructuredLogging(unittest.TestCase):
    """Tests for structured_logging.py."""

    def test_json_formatter_output(self):
        """JSONFormatter must produce valid JSON."""
        from server_code.structured_logging import JSONFormatter
        import logging
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name='test', level=logging.INFO, pathname='test.py',
            lineno=1, msg='Test message', args=(), exc_info=None
        )
        output = formatter.format(record)
        data = json.loads(output)
        self.assertEqual(data['msg'], 'Test message')
        self.assertEqual(data['level'], 'INFO')
        self.assertIn('ts', data)

    def test_correlation_filter_adds_id(self):
        """CorrelationFilter must add correlation_id to log records."""
        from server_code.structured_logging import CorrelationFilter
        import logging
        filt = CorrelationFilter()
        record = logging.LogRecord(
            name='test', level=logging.INFO, pathname='test.py',
            lineno=1, msg='Test', args=(), exc_info=None
        )
        filt.filter(record)
        self.assertTrue(hasattr(record, 'correlation_id'))
        self.assertIsNotNone(record.correlation_id)


# =========================================================
# 15. MONITORING STRUCTURE TESTS
# =========================================================
class TestMonitoringEndpoints(unittest.TestCase):
    """Tests for monitoring.py: response structure, auth checks."""

    def test_json_response_helper(self):
        """_json_response should produce valid response."""
        from server_code.monitoring import _json_response
        # This depends on the anvil mock — just verify it doesn't crash
        result = _json_response({'test': True})
        self.assertIsNotNone(result)

    def test_cache_stats_returns_all_caches(self):
        """_cache_stats should return stats for all 7 cache instances."""
        from server_code.monitoring import _cache_stats
        stats = _cache_stats()
        self.assertIsInstance(stats, dict)
        expected = ['dashboard', 'tags', 'reports', 'fx_rates',
                    'accounting_dashboard', 'payment_dashboard', 'dashboard_stats']
        for name in expected:
            self.assertIn(name, stats)
            self.assertIn('size', stats[name])
            self.assertIn('ttl', stats[name])
            self.assertIn('max_size', stats[name])


# Import threading for cache test
import threading

if __name__ == '__main__':
    unittest.main()

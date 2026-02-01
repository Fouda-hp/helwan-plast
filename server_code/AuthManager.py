"""
AuthManager.py - Secure Authentication & Authorization System
=============================================================
- Password hashing with bcrypt-like algorithm
- Session management
- Role-based access control
- Account lockout after failed attempts
- Audit logging
"""

import anvil.server
from anvil.tables import app_tables
from datetime import datetime, timedelta
import hashlib
import secrets
import json
import uuid


# =========================================================
# CONSTANTS
# =========================================================
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 30
SESSION_DURATION_HOURS = 24

# Role permissions
ROLES = {
    'admin': ['all'],
    'manager': ['view', 'create', 'edit', 'export'],
    'sales': ['view', 'create', 'edit_own'],
    'viewer': ['view']
}


# =========================================================
# PASSWORD HASHING (Secure)
# =========================================================
def hash_password(password):
    """
    Hash password with salt using SHA-256
    Returns: salt:hash format
    """
    salt = secrets.token_hex(32)
    salted = salt + password
    hashed = hashlib.sha256(salted.encode()).hexdigest()
    return f"{salt}:{hashed}"


def verify_password(password, stored_hash):
    """
    Verify password against stored hash
    """
    if not stored_hash or ':' not in stored_hash:
        return False

    salt, hash_value = stored_hash.split(':', 1)
    salted = salt + password
    check_hash = hashlib.sha256(salted.encode()).hexdigest()

    return secrets.compare_digest(check_hash, hash_value)


# =========================================================
# SESSION MANAGEMENT
# =========================================================
_active_sessions = {}


def generate_session_token():
    """Generate secure session token"""
    return secrets.token_urlsafe(64)


def create_session(user_email, role):
    """Create new session for user"""
    token = generate_session_token()
    expires = datetime.now() + timedelta(hours=SESSION_DURATION_HOURS)

    _active_sessions[token] = {
        'email': user_email,
        'role': role,
        'created': datetime.now(),
        'expires': expires
    }

    return token


def validate_session(token):
    """Validate session token"""
    if not token or token not in _active_sessions:
        return None

    session = _active_sessions[token]

    if datetime.now() > session['expires']:
        del _active_sessions[token]
        return None

    return session


def destroy_session(token):
    """Destroy session (logout)"""
    if token in _active_sessions:
        del _active_sessions[token]
        return True
    return False


# =========================================================
# USER REGISTRATION
# =========================================================
@anvil.server.callable
def register_user(email, password, full_name):
    """
    Register new user (pending admin approval)
    """

    # Validate inputs
    email = str(email or '').strip().lower()
    full_name = str(full_name or '').strip()

    if not email or '@' not in email:
        return {'success': False, 'message': 'Invalid email address'}

    if not password or len(password) < 6:
        return {'success': False, 'message': 'Password must be at least 6 characters'}

    if not full_name:
        return {'success': False, 'message': 'Full name is required'}

    # Check if email already exists
    existing = app_tables.users.get(email=email)
    if existing:
        return {'success': False, 'message': 'Email already registered'}

    # Create user (pending approval)
    user_id = str(uuid.uuid4())
    password_hash = hash_password(password)

    app_tables.users.add_row(
        user_id=user_id,
        email=email,
        password_hash=password_hash,
        full_name=full_name,
        role='sales',  # Default role
        is_approved=False,
        is_active=True,
        created_at=datetime.now(),
        login_attempts=0
    )

    # Log registration
    log_audit('REGISTER', 'users', user_id, None, {'email': email, 'full_name': full_name})

    return {
        'success': True,
        'message': 'Registration successful! Please wait for admin approval.'
    }


# =========================================================
# USER LOGIN
# =========================================================
@anvil.server.callable
def login_user(email, password):
    """
    Authenticate user and create session
    """

    email = str(email or '').strip().lower()

    if not email or not password:
        return {'success': False, 'message': 'Email and password are required'}

    # Find user
    user = app_tables.users.get(email=email)

    if not user:
        # Don't reveal if email exists
        return {'success': False, 'message': 'Invalid email or password'}

    # Check if locked
    if user['locked_until'] and user['locked_until'] > datetime.now():
        remaining = (user['locked_until'] - datetime.now()).seconds // 60
        return {
            'success': False,
            'message': f'Account locked. Try again in {remaining} minutes.'
        }

    # Check if active
    if not user['is_active']:
        return {'success': False, 'message': 'Account is deactivated'}

    # Check if approved
    if not user['is_approved']:
        return {'success': False, 'message': 'Account pending admin approval'}

    # Verify password
    if not verify_password(password, user['password_hash']):
        # Increment failed attempts
        attempts = (user['login_attempts'] or 0) + 1

        if attempts >= MAX_LOGIN_ATTEMPTS:
            user.update(
                login_attempts=attempts,
                locked_until=datetime.now() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            )
            log_audit('ACCOUNT_LOCKED', 'users', user['user_id'], None, {'email': email})
            return {
                'success': False,
                'message': f'Account locked for {LOCKOUT_DURATION_MINUTES} minutes'
            }

        user.update(login_attempts=attempts)
        remaining = MAX_LOGIN_ATTEMPTS - attempts
        return {
            'success': False,
            'message': f'Invalid password. {remaining} attempts remaining.'
        }

    # Success! Reset attempts and create session
    user.update(
        login_attempts=0,
        locked_until=None,
        last_login=datetime.now()
    )

    token = create_session(email, user['role'])

    log_audit('LOGIN', 'users', user['user_id'], None, {'email': email})

    return {
        'success': True,
        'message': 'Login successful',
        'token': token,
        'user': {
            'email': user['email'],
            'full_name': user['full_name'],
            'role': user['role']
        }
    }


@anvil.server.callable
def logout_user(token):
    """Logout user and destroy session"""

    session = validate_session(token)
    if session:
        log_audit('LOGOUT', 'users', None, None, {'email': session['email']})
        destroy_session(token)

    return {'success': True}


@anvil.server.callable
def validate_token(token):
    """Validate session token and return user info"""

    session = validate_session(token)

    if not session:
        return {'valid': False}

    user = app_tables.users.get(email=session['email'])

    if not user or not user['is_active'] or not user['is_approved']:
        destroy_session(token)
        return {'valid': False}

    return {
        'valid': True,
        'user': {
            'email': user['email'],
            'full_name': user['full_name'],
            'role': user['role']
        }
    }


# =========================================================
# PERMISSION CHECKING
# =========================================================
@anvil.server.callable
def check_permission(token, action):
    """Check if user has permission for action"""

    session = validate_session(token)

    if not session:
        return False

    role = session.get('role', '')
    permissions = ROLES.get(role, [])

    return 'all' in permissions or action in permissions


@anvil.server.callable
def is_admin(token):
    """Check if user is admin"""

    session = validate_session(token)
    return session and session.get('role') == 'admin'


# =========================================================
# ADMIN FUNCTIONS
# =========================================================
@anvil.server.callable
def get_pending_users(token):
    """Get users pending approval (admin only)"""

    if not is_admin(token):
        return {'success': False, 'message': 'Admin access required'}

    users = []
    for user in app_tables.users.search(is_approved=False, is_active=True):
        users.append({
            'user_id': user['user_id'],
            'email': user['email'],
            'full_name': user['full_name'],
            'created_at': user['created_at'].isoformat() if user['created_at'] else ''
        })

    return {'success': True, 'users': users}


@anvil.server.callable
def approve_user(token, user_id, role='sales'):
    """Approve user registration (admin only)"""

    session = validate_session(token)

    if not session or session.get('role') != 'admin':
        return {'success': False, 'message': 'Admin access required'}

    user = app_tables.users.get(user_id=user_id)

    if not user:
        return {'success': False, 'message': 'User not found'}

    user.update(
        is_approved=True,
        role=role,
        approved_by=session['email'],
        approved_at=datetime.now()
    )

    log_audit('APPROVE_USER', 'users', user_id, None, {
        'email': user['email'],
        'role': role,
        'approved_by': session['email']
    })

    return {'success': True, 'message': 'User approved successfully'}


@anvil.server.callable
def reject_user(token, user_id):
    """Reject user registration (admin only)"""

    session = validate_session(token)

    if not session or session.get('role') != 'admin':
        return {'success': False, 'message': 'Admin access required'}

    user = app_tables.users.get(user_id=user_id)

    if not user:
        return {'success': False, 'message': 'User not found'}

    email = user['email']
    user.delete()

    log_audit('REJECT_USER', 'users', user_id, None, {
        'email': email,
        'rejected_by': session['email']
    })

    return {'success': True, 'message': 'User rejected'}


@anvil.server.callable
def get_all_users(token):
    """Get all users (admin only)"""

    if not is_admin(token):
        return {'success': False, 'message': 'Admin access required'}

    users = []
    for user in app_tables.users.search():
        users.append({
            'user_id': user['user_id'],
            'email': user['email'],
            'full_name': user['full_name'],
            'role': user['role'],
            'is_approved': user['is_approved'],
            'is_active': user['is_active'],
            'created_at': user['created_at'].isoformat() if user['created_at'] else '',
            'last_login': user['last_login'].isoformat() if user['last_login'] else 'Never'
        })

    return {'success': True, 'users': users}


@anvil.server.callable
def update_user_role(token, user_id, new_role):
    """Update user role (admin only)"""

    session = validate_session(token)

    if not session or session.get('role') != 'admin':
        return {'success': False, 'message': 'Admin access required'}

    if new_role not in ROLES:
        return {'success': False, 'message': 'Invalid role'}

    user = app_tables.users.get(user_id=user_id)

    if not user:
        return {'success': False, 'message': 'User not found'}

    old_role = user['role']
    user.update(role=new_role)

    log_audit('UPDATE_ROLE', 'users', user_id,
              {'role': old_role},
              {'role': new_role, 'updated_by': session['email']})

    return {'success': True, 'message': 'Role updated successfully'}


@anvil.server.callable
def toggle_user_active(token, user_id):
    """Activate/Deactivate user (admin only)"""

    session = validate_session(token)

    if not session or session.get('role') != 'admin':
        return {'success': False, 'message': 'Admin access required'}

    user = app_tables.users.get(user_id=user_id)

    if not user:
        return {'success': False, 'message': 'User not found'}

    # Prevent self-deactivation
    if user['email'] == session['email']:
        return {'success': False, 'message': 'Cannot deactivate your own account'}

    new_status = not user['is_active']
    user.update(is_active=new_status)

    action = 'ACTIVATE_USER' if new_status else 'DEACTIVATE_USER'
    log_audit(action, 'users', user_id, None, {
        'email': user['email'],
        'by': session['email']
    })

    return {
        'success': True,
        'message': f"User {'activated' if new_status else 'deactivated'} successfully"
    }


@anvil.server.callable
def reset_user_password(token, user_id, new_password):
    """Reset user password (admin only)"""

    session = validate_session(token)

    if not session or session.get('role') != 'admin':
        return {'success': False, 'message': 'Admin access required'}

    if not new_password or len(new_password) < 6:
        return {'success': False, 'message': 'Password must be at least 6 characters'}

    user = app_tables.users.get(user_id=user_id)

    if not user:
        return {'success': False, 'message': 'User not found'}

    user.update(
        password_hash=hash_password(new_password),
        login_attempts=0,
        locked_until=None
    )

    log_audit('RESET_PASSWORD', 'users', user_id, None, {
        'email': user['email'],
        'by': session['email']
    })

    return {'success': True, 'message': 'Password reset successfully'}


@anvil.server.callable
def change_own_password(token, old_password, new_password):
    """User changes their own password"""

    session = validate_session(token)

    if not session:
        return {'success': False, 'message': 'Session expired'}

    user = app_tables.users.get(email=session['email'])

    if not user:
        return {'success': False, 'message': 'User not found'}

    if not verify_password(old_password, user['password_hash']):
        return {'success': False, 'message': 'Current password is incorrect'}

    if not new_password or len(new_password) < 6:
        return {'success': False, 'message': 'New password must be at least 6 characters'}

    user.update(password_hash=hash_password(new_password))

    log_audit('CHANGE_PASSWORD', 'users', user['user_id'], None, {'email': user['email']})

    return {'success': True, 'message': 'Password changed successfully'}


# =========================================================
# SETUP ADMIN (Run once)
# =========================================================
@anvil.server.callable
def setup_initial_admin(email, password, full_name):
    """
    Create initial admin account (only works if no admins exist)
    """

    # Check if any admin exists
    existing_admin = app_tables.users.get(role='admin')

    if existing_admin:
        return {'success': False, 'message': 'Admin account already exists'}

    email = str(email or '').strip().lower()

    if not email or '@' not in email:
        return {'success': False, 'message': 'Invalid email'}

    if not password or len(password) < 6:
        return {'success': False, 'message': 'Password must be at least 6 characters'}

    user_id = str(uuid.uuid4())

    app_tables.users.add_row(
        user_id=user_id,
        email=email,
        password_hash=hash_password(password),
        full_name=full_name or 'Administrator',
        role='admin',
        is_approved=True,
        is_active=True,
        created_at=datetime.now()
    )

    log_audit('SETUP_ADMIN', 'users', user_id, None, {'email': email})

    return {'success': True, 'message': 'Admin account created successfully'}


# =========================================================
# AUDIT LOGGING
# =========================================================
def log_audit(action, table_name, record_id, old_data, new_data, user_email=None):
    """Log action to audit trail"""

    try:
        app_tables.audit_log.add_row(
            log_id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            user_email=user_email or 'system',
            action=action,
            table_name=table_name,
            record_id=str(record_id) if record_id else None,
            old_data=json.dumps(old_data) if old_data else None,
            new_data=json.dumps(new_data) if new_data else None
        )
    except Exception as e:
        print(f"Audit log error: {e}")


@anvil.server.callable
def get_audit_logs(token, limit=100, offset=0, filters=None):
    """Get audit logs (admin only)"""

    if not is_admin(token):
        return {'success': False, 'message': 'Admin access required'}

    logs = []
    all_logs = list(app_tables.audit_log.search())
    all_logs.sort(key=lambda x: x['timestamp'] or datetime.min, reverse=True)

    # Apply filters if provided
    if filters:
        if filters.get('action'):
            all_logs = [l for l in all_logs if l['action'] == filters['action']]
        if filters.get('user_email'):
            all_logs = [l for l in all_logs if l['user_email'] == filters['user_email']]
        if filters.get('table_name'):
            all_logs = [l for l in all_logs if l['table_name'] == filters['table_name']]

    total = len(all_logs)
    page_logs = all_logs[offset:offset + limit]

    for log in page_logs:
        logs.append({
            'log_id': log['log_id'],
            'timestamp': log['timestamp'].isoformat() if log['timestamp'] else '',
            'user_email': log['user_email'],
            'action': log['action'],
            'table_name': log['table_name'],
            'record_id': log['record_id'],
            'old_data': log['old_data'],
            'new_data': log['new_data']
        })

    return {
        'success': True,
        'logs': logs,
        'total': total,
        'limit': limit,
        'offset': offset
    }

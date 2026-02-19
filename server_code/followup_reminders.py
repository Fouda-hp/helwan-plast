"""
followup_reminders.py - نظام تذكيرات المتابعة للعروض السعرية
=============================================================
- تعيين تاريخ متابعة لعرض سعر
- تأجيل المتابعة (1/3/7 أيام)
- إتمام المتابعة
- لوحة المتابعات مع إحصائيات
"""

import anvil.server
from anvil.tables import app_tables
import anvil.tables.query as q
import json
import logging
from datetime import datetime, date, timedelta

try:
    from .auth_utils import get_utc_now
except ImportError:
    from auth_utils import get_utc_now

try:
    from . import AuthManager
except ImportError:
    import AuthManager

try:
    from . import notifications as notifications_module
except ImportError:
    import notifications as notifications_module

logger = logging.getLogger(__name__)

# Centralized permission helpers (من auth_permissions.py)
try:
    from .auth_permissions import require_permission_full as _require_permission
except ImportError:
    from auth_permissions import require_permission_full as _require_permission

# Thread-safe cache for dashboard data (replaces ad-hoc global dict)
try:
    from .cache_manager import dashboard_cache as _dashboard_cache_mgr
except ImportError:
    from cache_manager import dashboard_cache as _dashboard_cache_mgr


# Use shared helpers to avoid code duplication
try:
    from .shared_utils import get_client_ip_safe as _get_client_ip
    from .shared_utils import log_audit_safe as _log_audit
    from .shared_utils import parse_date as _parse_date
except ImportError:
    from shared_utils import get_client_ip_safe as _get_client_ip
    from shared_utils import log_audit_safe as _log_audit
    from shared_utils import parse_date as _parse_date


# =========================================================
# Follow-up CRUD
# =========================================================
def _invalidate_dashboard_cache():
    _dashboard_cache_mgr.invalidate()

@anvil.server.callable
def set_followup(quotation_number, follow_up_date, token_or_email=None):
    """تعيين تاريخ متابعة لعرض سعر"""
    is_valid, user_email, error = _require_permission(token_or_email, 'edit')
    if not is_valid:
        return error
    _invalidate_dashboard_cache()

    try:
        qn = int(quotation_number)
        row = app_tables.quotations.get(**{'Quotation#': qn})
        if not row:
            return {'success': False, 'message': 'Quotation not found'}

        fu_date = _parse_date(follow_up_date)
        if not fu_date:
            return {'success': False, 'message': 'Invalid follow-up date'}

        old_data = {
            'follow_up_date': row.get('follow_up_date', ''),
            'follow_up_status': row.get('follow_up_status', ''),
        }

        row.update(
            follow_up_date=str(fu_date),
            follow_up_status='pending',
            updated_by=user_email,
            updated_at=get_utc_now()
        )

        _log_audit('SET_FOLLOWUP', 'quotations', str(qn), old_data,
                    {'follow_up_date': str(fu_date), 'follow_up_status': 'pending'},
                    user_email, _get_client_ip())

        # Notify the sales rep + all admins (with email for follow-ups)
        client_name = row.get('Client Name', '') or ''
        fu_payload = {
            'quotation_number': qn,
            'client_name': client_name,
            'follow_up_date': str(fu_date),
            'created_by': user_email,
            'message_en': f'Follow-up set for Quotation #{qn} ({client_name}) on {fu_date} by {user_email}',
            'message_ar': f'تم تعيين متابعة لعرض سعر #{qn} ({client_name}) في {fu_date} بواسطة {user_email}',
        }
        try:
            # Notify the sales rep
            sales_rep_email = row.get('Sales Rep', '') or row.get('Email', '')
            if sales_rep_email and '@' in str(sales_rep_email):
                notifications_module.create_notification(sales_rep_email, 'followup_set', fu_payload)
            # Also notify the user who created it (if different from sales rep)
            if user_email and user_email != sales_rep_email:
                notifications_module.create_notification(user_email, 'followup_set', fu_payload)
            # Notify all admins
            notifications_module.create_notification_for_all_admins('followup_set', fu_payload)
        except Exception as _e:
            logger.debug("Suppressed: %s", _e)

        return {'success': True, 'follow_up_date': str(fu_date), 'follow_up_status': 'pending'}

    except Exception as e:
        logger.exception("set_followup error: %s", e)
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def snooze_followup(quotation_number, snooze_days, token_or_email=None):
    """تأجيل متابعة (1/3/7 أيام)"""
    is_valid, user_email, error = _require_permission(token_or_email, 'edit')
    if not is_valid:
        return error
    _invalidate_dashboard_cache()

    try:
        snooze_days = int(snooze_days)
        if snooze_days not in (1, 3, 7):
            return {'success': False, 'message': 'Invalid snooze period (1, 3, or 7 days)'}

        qn = int(quotation_number)
        row = app_tables.quotations.get(**{'Quotation#': qn})
        if not row:
            return {'success': False, 'message': 'Quotation not found'}

        current_date = _parse_date(row.get('follow_up_date', ''))
        if not current_date:
            current_date = date.today()

        new_date = max(date.today(), current_date) + timedelta(days=snooze_days)

        old_data = {
            'follow_up_date': row.get('follow_up_date', ''),
            'follow_up_status': row.get('follow_up_status', ''),
        }

        row.update(
            follow_up_date=str(new_date),
            follow_up_status='snoozed',
            updated_by=user_email,
            updated_at=get_utc_now()
        )

        _log_audit('SNOOZE_FOLLOWUP', 'quotations', str(qn), old_data,
                    {'follow_up_date': str(new_date), 'follow_up_status': 'snoozed', 'snooze_days': snooze_days},
                    user_email, _get_client_ip())

        return {'success': True, 'follow_up_date': str(new_date), 'follow_up_status': 'snoozed'}

    except Exception as e:
        logger.exception("snooze_followup error: %s", e)
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def complete_followup(quotation_number, token_or_email=None):
    """إتمام متابعة"""
    is_valid, user_email, error = _require_permission(token_or_email, 'edit')
    if not is_valid:
        return error
    _invalidate_dashboard_cache()

    try:
        qn = int(quotation_number)
        row = app_tables.quotations.get(**{'Quotation#': qn})
        if not row:
            return {'success': False, 'message': 'Quotation not found'}

        old_data = {
            'follow_up_date': row.get('follow_up_date', ''),
            'follow_up_status': row.get('follow_up_status', ''),
        }

        row.update(
            follow_up_status='completed',
            updated_by=user_email,
            updated_at=get_utc_now()
        )

        _log_audit('COMPLETE_FOLLOWUP', 'quotations', str(qn), old_data,
                    {'follow_up_status': 'completed'},
                    user_email, _get_client_ip())

        return {'success': True, 'follow_up_status': 'completed'}

    except Exception as e:
        logger.exception("complete_followup error: %s", e)
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_followup_dashboard(token_or_email=None, filter_status='all'):
    """لوحة المتابعات مع إحصائيات"""
    is_valid, user_email, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error

    # Check thread-safe cache
    cache_key = f"dashboard:{user_email}:{filter_status}"
    cached = _dashboard_cache_mgr.get(cache_key)
    if cached is not None:
        return cached

    try:
        today = date.today()
        week_later = today + timedelta(days=7)

        overdue_count = 0
        today_count = 0
        upcoming_count = 0
        completed_count = 0
        data = []

        # Scan quotations with follow_up_date (DB-level filter to skip None dates)
        search_kwargs = {'is_deleted': False, 'follow_up_date': q.not_(None)}
        if filter_status == 'completed':
            search_kwargs['follow_up_status'] = 'completed'
        for row in app_tables.quotations.search(**search_kwargs):
            fu_date_str = row.get('follow_up_date', '')
            if not fu_date_str or not str(fu_date_str).strip():
                continue

            fu_date = _parse_date(fu_date_str)
            if not fu_date:
                continue

            fu_status = (row.get('follow_up_status', '') or '').strip().lower()
            if not fu_status:
                fu_status = 'pending'

            # Calculate days until/since
            delta = (fu_date - today).days

            # Categorize
            category = 'upcoming'
            if fu_status == 'completed':
                completed_count += 1
                category = 'completed'
            elif fu_date < today:
                overdue_count += 1
                category = 'overdue'
            elif fu_date == today:
                today_count += 1
                category = 'today'
            elif fu_date <= week_later:
                upcoming_count += 1
                category = 'upcoming'
            else:
                upcoming_count += 1
                category = 'upcoming'

            # Apply filter
            if filter_status and filter_status != 'all':
                if filter_status == 'overdue' and category != 'overdue':
                    continue
                elif filter_status == 'today' and category != 'today':
                    continue
                elif filter_status == 'upcoming' and category not in ('today', 'upcoming'):
                    continue
                elif filter_status == 'completed' and category != 'completed':
                    continue

            agreed = 0
            try:
                agreed = float(row.get('Agreed Price') or 0)
            except (TypeError, ValueError):
                pass

            data.append({
                'quotation_number': row.get('Quotation#'),
                'client_name': row.get('Client Name', ''),
                'client_code': row.get('Client Code', ''),
                'company': row.get('Company', ''),
                'agreed_price': agreed,
                'model': row.get('Model', ''),
                'follow_up_date': str(fu_date),
                'follow_up_status': fu_status,
                'category': category,
                'days_until': delta,
                'sales_rep': row.get('Sales Rep', ''),
            })
            if len(data) >= 500:
                break  # Cap to avoid unbounded memory

        # Sort: overdue first (most overdue), then today, then upcoming (nearest first)
        def sort_key(item):
            cat_order = {'overdue': 0, 'today': 1, 'upcoming': 2, 'completed': 3}
            return (cat_order.get(item['category'], 9), item['days_until'])

        data.sort(key=sort_key)

        result = {
            'success': True,
            'stats': {
                'overdue_count': overdue_count,
                'today_count': today_count,
                'upcoming_count': upcoming_count,
                'completed_count': completed_count,
            },
            'data': data[:200],
        }

        # Update thread-safe cache
        _dashboard_cache_mgr.set(cache_key, result)

        return result

    except Exception as e:
        logger.exception("get_followup_dashboard error: %s", e)
        return {'success': False, 'message': 'Failed to load follow-up dashboard. Please try again.', 'stats': {}, 'data': []}


_MAX_OVERDUE_NOTIFICATIONS = 20  # limit per run to avoid email flood

@anvil.server.callable
def check_overdue_followups(token_or_email=None):
    """فحص المتابعات المتأخرة وإرسال إشعارات (max 20 per run)"""
    is_valid, user_email, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error

    try:
        today = date.today()
        notified = 0

        for row in app_tables.quotations.search(is_deleted=False):
            if notified >= _MAX_OVERDUE_NOTIFICATIONS:
                break

            fu_date_str = row.get('follow_up_date', '')
            fu_status = (row.get('follow_up_status', '') or '').strip().lower()

            if not fu_date_str or fu_status == 'completed':
                continue

            fu_date = _parse_date(fu_date_str)
            if not fu_date or fu_date >= today:
                continue

            # This follow-up is overdue
            days_overdue = (today - fu_date).days
            qn = row.get('Quotation#')
            client_name = row.get('Client Name', '')

            # Notify all admins
            sales_rep = row.get('Sales Rep', '') or row.get('updated_by', '') or ''
            try:
                notifications_module.create_notification_for_all_admins(
                    'followup_overdue',
                    {
                        'quotation_number': qn,
                        'client_name': client_name,
                        'days_overdue': days_overdue,
                        'follow_up_date': str(fu_date),
                        'created_by': sales_rep,
                        'message_en': f'Overdue follow-up: Quotation #{qn} ({client_name}) - {days_overdue} days overdue',
                        'message_ar': f'متابعة متأخرة: عرض سعر #{qn} ({client_name}) - متأخر {days_overdue} يوم',
                    }
                )
                notified += 1
            except Exception as _e:
                logger.debug("Suppressed: %s", _e)

        return {'success': True, 'notified': notified, 'capped': notified >= _MAX_OVERDUE_NOTIFICATIONS}

    except Exception as e:
        logger.exception("check_overdue_followups error: %s", e)
        return {'success': False, 'message': 'An error occurred. Please try again later.'}


@anvil.server.callable
def get_quotations_for_followup(token_or_email=None, search=''):
    """جلب العروض المتاحة لإضافة متابعة (بدون متابعة نشطة)"""
    is_valid, user_email, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error

    try:
        search_lower = (search or '').strip().lower()
        results = []

        for row in app_tables.quotations.search(is_deleted=False):
            # Skip quotations that already have active follow-ups
            fu_status = (row.get('follow_up_status', '') or '').strip().lower()
            if fu_status in ('pending', 'snoozed'):
                fu_date = _parse_date(row.get('follow_up_date', ''))
                if fu_date:
                    continue

            qn = row.get('Quotation#', '')
            client_name = row.get('Client Name', '')
            company = row.get('Company', '')
            model = row.get('Model', '')

            # Apply search filter
            if search_lower:
                searchable = f"{qn} {client_name} {company} {model}".lower()
                if search_lower not in searchable:
                    continue

            results.append({
                'quotation_number': qn,
                'client_name': client_name,
                'company': company,
                'model': model,
            })

            if len(results) >= 50:
                break

        return {'success': True, 'data': results}

    except Exception as e:
        logger.exception("get_quotations_for_followup error: %s", e)
        return {'success': False, 'message': 'Failed to load follow-up data. Please try again.', 'data': []}

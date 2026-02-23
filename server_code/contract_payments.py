"""
contract_payments.py - تسجيل ومتابعة الدفعات الفعلية للعقود
==========================================================
يسجل الدفعات الفعلية (مبلغ حر أو مرتبط بدفعة معينة) في جدول contract_payments.

الجدول المطلوب: contract_payments
الأعمدة:
  - id: text (UUID)
  - contract_number: text
  - quotation_number: number
  - amount: number
  - payment_date: text (ISO date)
  - payment_method: text (cash/bank_transfer/check)
  - installment_index: number (nullable, -1 = free payment)
  - notes: text
  - created_by: text (user email)
  - created_at: text (ISO datetime)
"""

import anvil.server
from anvil.tables import app_tables
import json
import uuid
import logging

try:
    from .auth_utils import get_utc_now
except ImportError:
    from auth_utils import get_utc_now

try:
    from .auth_permissions import require_permission_full as _require_permission
    from .auth_permissions import require_authenticated as _require_authenticated
except ImportError:
    from auth_permissions import require_permission_full as _require_permission
    from auth_permissions import require_authenticated as _require_authenticated

try:
    from .shared_utils import contracts_get_active as _contracts_get_active
except ImportError:
    from shared_utils import contracts_get_active as _contracts_get_active

logger = logging.getLogger(__name__)


def _has_contract_payments_table():
    """Check if contract_payments table exists."""
    try:
        _ = app_tables.contract_payments
        return True
    except Exception:
        return False


@anvil.server.callable
def record_contract_payment(quotation_number, amount, payment_date,
                            payment_method='cash', installment_index=-1,
                            notes='', token_or_email=None):
    """
    Record an actual payment against a contract.
    installment_index: -1 means free payment (not tied to a specific installment)
    """
    is_valid, user_email, error = _require_permission(token_or_email, 'create')
    if not is_valid:
        return error or {'success': False, 'message': 'Permission denied'}

    # Validate
    try:
        q_num = int(quotation_number)
    except (TypeError, ValueError):
        return {'success': False, 'message': 'Invalid quotation number'}

    try:
        amount_val = float(str(amount).replace(',', '').replace('،', '').strip())
    except (TypeError, ValueError):
        return {'success': False, 'message': 'Invalid amount'}

    if amount_val <= 0:
        return {'success': False, 'message': 'Amount must be greater than 0'}

    # Check contract exists
    contract = _contracts_get_active(quotation_number=q_num)
    if not contract:
        return {'success': False, 'message': 'Contract not found'}

    contract_number = contract['contract_number']

    if not _has_contract_payments_table():
        return {'success': False, 'message': 'contract_payments table not found. Please create it in Anvil Data Tables.'}

    try:
        payment_id = str(uuid.uuid4())[:12]
        now = get_utc_now()

        app_tables.contract_payments.add_row(
            id=payment_id,
            contract_number=contract_number,
            quotation_number=q_num,
            amount=amount_val,
            payment_date=str(payment_date or ''),
            payment_method=str(payment_method or 'cash'),
            installment_index=int(installment_index) if installment_index is not None else -1,
            notes=str(notes or ''),
            created_by=user_email,
            created_at=now.isoformat(),
        )

        # Auto-update contract lifecycle status based on payments
        _auto_update_lifecycle(contract, q_num)

        # Return updated summary
        return _build_payment_summary(q_num, contract)

    except Exception as e:
        logger.error("record_contract_payment error: %s", e)
        return {'success': False, 'message': f'Failed to record payment: {e}'}


@anvil.server.callable
def get_contract_payments(quotation_number, token_or_email=None):
    """
    Get all recorded payments for a contract.
    Returns payments list + summary (total_paid, remaining).
    """
    is_valid, _, error = _require_permission(token_or_email, 'view')
    if not is_valid:
        return error or {'success': False, 'message': 'Permission denied'}

    try:
        q_num = int(quotation_number)
    except (TypeError, ValueError):
        return {'success': False, 'message': 'Invalid quotation number'}

    contract = _contracts_get_active(quotation_number=q_num)
    if not contract:
        return {'success': False, 'message': 'Contract not found'}

    return _build_payment_summary(q_num, contract)


@anvil.server.callable
def delete_contract_payment(payment_id, token_or_email=None):
    """Delete a recorded payment by ID."""
    is_valid, user_email, error = _require_permission(token_or_email, 'delete')
    if not is_valid:
        return error or {'success': False, 'message': 'Permission denied'}

    if not _has_contract_payments_table():
        return {'success': False, 'message': 'contract_payments table not found'}

    try:
        row = app_tables.contract_payments.get(id=str(payment_id))
        if not row:
            return {'success': False, 'message': 'Payment not found'}

        q_num = row['quotation_number']
        row.delete()

        contract = _contracts_get_active(quotation_number=q_num)
        return _build_payment_summary(q_num, contract)

    except Exception as e:
        logger.error("delete_contract_payment error: %s", e)
        return {'success': False, 'message': 'Failed to delete payment'}


def _auto_update_lifecycle(contract, quotation_number):
    """Auto-update contract lifecycle based on payment status.
    - First payment → in_progress
    - Fully paid (remaining ≤ 0) → delivered
    """
    try:
        current_status = (contract.get('lifecycle_status') or 'negotiation').strip().lower()

        # Calculate total price
        tp = contract.get('total_price') or 0
        try:
            total_price = float(str(tp).replace(',', '').replace('،', '').strip()) if tp else 0
        except (TypeError, ValueError):
            total_price = 0

        # Calculate total paid
        total_paid = 0
        if _has_contract_payments_table():
            for row in app_tables.contract_payments.search(quotation_number=int(quotation_number)):
                total_paid += row['amount'] or 0

        remaining = total_price - total_paid

        # Determine new status
        new_status = None
        if remaining <= 0 and total_paid > 0 and current_status in ('negotiation', 'signed', 'in_progress'):
            new_status = 'delivered'
        elif total_paid > 0 and current_status in ('negotiation', 'signed'):
            new_status = 'in_progress'

        if new_status and new_status != current_status:
            import json
            history_raw = contract.get('status_history_json') or '[]'
            try:
                history = json.loads(history_raw) if isinstance(history_raw, str) else (history_raw or [])
            except Exception:
                history = []
            history.append({
                'from': current_status,
                'to': new_status,
                'date': get_utc_now().isoformat(),
                'user': 'system',
                'notes': 'Auto-updated by payment'
            })
            contract['lifecycle_status'] = new_status
            contract['status_history_json'] = json.dumps(history)
            logger.info("Contract %s auto-updated: %s → %s", contract.get('contract_number'), current_status, new_status)
    except Exception as e:
        logger.error("_auto_update_lifecycle error: %s", e)


def _build_payment_summary(quotation_number, contract):
    """Build payment summary for a contract."""
    # Get total price
    tp = contract.get('total_price') if contract else 0
    try:
        total_price = float(str(tp).replace(',', '').replace('،', '').strip()) if tp else 0
    except (TypeError, ValueError):
        total_price = 0

    # Get recorded payments
    recorded = []
    if _has_contract_payments_table():
        try:
            for row in app_tables.contract_payments.search(quotation_number=int(quotation_number)):
                recorded.append({
                    'id': row['id'],
                    'amount': row['amount'],
                    'payment_date': row['payment_date'],
                    'payment_method': row['payment_method'],
                    'installment_index': row['installment_index'],
                    'notes': row['notes'],
                    'created_by': row['created_by'],
                    'created_at': row['created_at'],
                })
        except Exception as e:
            logger.error("Error fetching contract_payments: %s", e)

    # Sort by date
    recorded.sort(key=lambda x: x.get('payment_date', '') or '')

    total_paid = sum(p.get('amount', 0) or 0 for p in recorded)
    remaining = total_price - total_paid

    return {
        'success': True,
        'payments': recorded,
        'summary': {
            'total_price': total_price,
            'total_paid': total_paid,
            'remaining': remaining,
            'payment_count': len(recorded),
        }
    }

import anvil.users
# anvil.files removed to avoid posixpath.getcwd() errors at app load (e.g. login)
import anvil.secrets
from anvil.tables import app_tables
import json
import logging

logger = logging.getLogger(__name__)

# All app tables (must exist in Anvil Data Tables). Include accounting_period_locks for period lock.
TABLE_NAMES = [
  "quotations",
  "clients",
  "contracts",
  "counters",
  "audit_log",
  "users",
  "machine_specs",
  "settings",
  "sessions",
  "otp_codes",
  "password_history",
  "pending_passwords",
  "rate_limits",
  "notifications",
  "scheduled_backups",
  "chart_of_accounts",
  "ledger",
  "suppliers",
  "purchase_invoices",
  "posted_purchase_invoice_ids",
  "import_costs",
  "inventory",
  "expenses",
  "currency_exchange_rates",
  "opening_balances",
  "accounting_period_locks",
]

def export_schema():
  """Export column names and types for all tables. Skips tables that do not exist yet."""
  schema = {}

  for table_name in TABLE_NAMES:
    try:
      table = getattr(app_tables, table_name)
    except AttributeError:
      schema[table_name] = []  # Table not created in Anvil yet
      continue
    schema[table_name] = []
    try:
      for col in table.list_columns():
        schema[table_name].append({
          "name": col["name"],
          "type": col["type"]
        })
    except Exception as e:
      logger.warning("Schema export skip %s: %s", table_name, e)

  logger.debug("Schema export: %s", json.dumps(schema, indent=2, default=str))
  return schema

import anvil.users
import anvil.files
from anvil.files import data_files
import anvil.google.auth, anvil.google.drive, anvil.google.mail
from anvil.google.drive import app_files
import anvil.secrets
from anvil.tables import app_tables
import json
import logging

logger = logging.getLogger(__name__)

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
]

def export_schema():
  schema = {}

  for table_name in TABLE_NAMES:
    table = getattr(app_tables, table_name)
    schema[table_name] = []

    for col in table.list_columns():
      schema[table_name].append({
        "name": col["name"],
        "type": col["type"]
      })

  logger.debug("Schema export: %s", json.dumps(schema, indent=2, default=str))

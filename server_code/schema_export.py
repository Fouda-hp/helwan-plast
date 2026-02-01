from anvil.tables import app_tables
import json

TABLE_NAMES = [
  "quotations",
  "clients",
  # زوّد أي جدول تاني هنا
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

  print(json.dumps(schema, indent=2, default=str))

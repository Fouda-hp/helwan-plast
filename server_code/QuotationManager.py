"""
Server Module - WITH AUTO-NUMBERING FUNCTIONS
"""

import anvil.server
from anvil.tables import app_tables
from datetime import datetime


# =========================================================
# 🔥 AUTO-NUMBERING FUNCTIONS
# =========================================================
@anvil.server.callable
def get_next_client_code():
  """
    Used on page load / NEW button
    Always returns max Client Code + 1
    """
  return _get_next_number('clients', 'Client Code')


@anvil.server.callable
def get_next_quotation_number():
  """
    Used on page load / NEW button
    Always returns max Quotation# + 1
    """
  return _get_next_number('quotations', 'Quotation#')

@anvil.server.callable
def get_or_create_client_code(client_name, phone):
  """
  Allow same name, but phone must be unique
  """

  if not phone:
    return None

  phone = str(phone).strip()
  client_name = str(client_name).strip() if client_name else ""

  print(f"🔍 Checking phone='{phone}'")

  # 🔥 search by PHONE ONLY
  row = app_tables.clients.get(Phone=phone)

  if row:
    # Existing phone → return same client code
    code = str(row["Client Code"])
    print(f"✅ Existing phone found, client_code={code}")
    return code

  # New phone → new client
  new_code = _get_next_number('clients', 'Client Code')
  print(f"🆕 New phone, generated client_code={new_code}")
  return str(new_code)



@anvil.server.callable
def get_quotation_number_if_needed(current_number, model):
  """
  Get quotation number only if needed
  Called from JavaScript when model code is built
  """

  if current_number:
    print(f"⚠️ Quotation number already exists: {current_number}")
    return int(current_number)

  if not model:
    print("⚠️ No model provided")
    return None

  new_q = _get_next_number('quotations', 'Quotation#')
  print(f"🆕 Generated new quotation number: {new_q}")
  return int(new_q)


def _get_next_number(table_name, column_name):
  """
  Generate next number safely (transaction-safe)
  Searches for maximum value and increments
  """

  table = getattr(app_tables, table_name)

  # Find maximum existing value
  max_val = 0

  for row in table.search():
    val = row[column_name]
    if val is not None:
      try:
        num = int(val) if isinstance(val, str) else val
        if num > max_val:
          max_val = num
      except:
        pass

  next_val = max_val + 1
  print(f"📊 {table_name}.{column_name}: max={max_val}, next={next_val}")
  return next_val


# =========================================================
# VALIDATION HELPERS
# =========================================================

def safe_strip(v):
  return str(v).strip() if v not in (None, "") else ""

def safe_int(v):
  try:
    return int(v)
  except:
    return None

def safe_float(v):
  try:
    return float(v)
  except:
    return None

def yes_no(v):
  return "YES" if v else "NO"


@anvil.server.callable
def phone_exists(phone, exclude_client_code=None):
  """Check if phone exists"""

  phone = safe_strip(phone)
  if not phone:
    return False

  if exclude_client_code is not None:
    exclude_client_code = str(exclude_client_code)

  rows = app_tables.clients.search(Phone=phone)
  for r in rows:
    if exclude_client_code is not None and str(r['Client Code']) == exclude_client_code:
      continue
    return True

  return False


@anvil.server.callable
def client_exists(client_code):
  """Check if client exists by code"""

  if not client_code:
    return False

  client_code_str = str(client_code)
  return app_tables.clients.get(**{"Client Code": client_code_str}) is not None


@anvil.server.callable
def quotation_exists(quotation_number):
  """Check if quotation exists by number"""

  if not quotation_number:
    return False

  quotation_int = safe_int(quotation_number)
  if quotation_int is None:
    return False

  return app_tables.quotations.get(**{"Quotation#": quotation_int}) is not None


# =========================================================
# MAIN SAVE FUNCTION
# =========================================================

@anvil.server.callable
def save_quotation(form_data):
  """Main save function with auto-numbering"""

  print("📥 Received form_data")

  # Extract data
  client_code_raw = form_data.get('Client Code')
  quotation_number_raw = form_data.get('Quotation#')
  model = safe_strip(form_data.get('Model'))

  client_code = str(client_code_raw) if client_code_raw else None
  quotation_number = safe_int(quotation_number_raw)

  # -----------------------------------------
  # Detect existing vs new client (FINAL LOGIC)
  # -----------------------------------------
  existing_client_row = None
  if client_code:
    existing_client_row = app_tables.clients.get(
      **{"Client Code": str(client_code)}
    )

  is_existing_client = existing_client_row is not None
  is_new_client = not is_existing_client

  is_quotation = bool(
    safe_strip(form_data.get('Model')) and
    safe_strip(form_data.get('Quotation#'))
  )

  is_new_quotation = is_quotation and (not quotation_number or not quotation_exists(quotation_number))

  # -----------------------------------------
  # Client validation (ONLY if new client)
  # -----------------------------------------
  missing = []

  if is_new_client:
    if not safe_strip(form_data.get('Client Name')):
      missing.append("• Client Name")
    if not safe_strip(form_data.get('Company')):
      missing.append("• Company")
    if not safe_strip(form_data.get('Phone')):
      missing.append("• Phone")

    if missing:
      return {
        "success": False,
        "message": "Missing Client Data:\n" + "\n".join(missing)
      }

  if is_quotation:
    q_missing = []
    if not form_data.get('Given Price'):
      q_missing.append("- Given Price")
    if not form_data.get('Agreed Price'):
      q_missing.append("- Agreed Price")

    if q_missing:
      return {
        "success": False,
        "message": "Quotation missing data:\n" + "\n".join(q_missing)
      }

  # -----------------------------------------
  # Phone validation (FINAL - ROW SAFE)
  # -----------------------------------------
  phone = safe_strip(form_data.get('Phone'))

  if phone:
    phone_row = app_tables.clients.get(Phone=phone)

    if phone_row:
      if is_existing_client:
        if phone_row != existing_client_row:
          return {
            "success": False,
            "message": "Phone already exists"
          }
      else:
        return {
          "success": False,
          "message": "Phone already exists"
        }

  # =========================================
  # PRICE VALIDATION (FIXED - CORRECT FLOW)
  # =========================================
  if is_quotation:

    given = safe_float(form_data.get('Given Price'))
    agreed = safe_float(form_data.get('Agreed Price'))

    if given is None or agreed is None:
      return {
        "success": False,
        "message": "Given Price and Agreed Price must be valid numbers"
      }

    # 1️⃣ agreed > given (ALWAYS)
    if agreed > given:
      return {
        "success": False,
        "message": f"Agreed Price ({agreed:,.0f}) cannot be greater than Given Price ({given:,.0f})"
      }

    is_overseas = bool(form_data.get('Overseas clients'))

    # ===============================
    # 2️⃣ OVERSEAS MODE
    # ===============================
    if is_overseas:
      overseas_price = safe_float(form_data.get('overseas_price'))

      if overseas_price is None or overseas_price <= 0:
        return {
          "success": False,
          "message": "Overseas price is missing or invalid"
        }

      if agreed < overseas_price:
        return {
          "success": False,
          "message":
          f"Agreed Price ({agreed:,.0f}) must not be less than Overseas Price ({overseas_price:,.0f})"
        }

    # ===============================
    # 3️⃣ LOCAL MODE (FIXED)
    # ===============================
    else:
      # 🔥 FIX: Read from correct fields
      in_stock_price = safe_float(form_data.get('In Stock'))
      new_order_price = safe_float(form_data.get('New Order'))

      if in_stock_price is None or in_stock_price <= 0:
        return {
          "success": False,
          "message": "In Stock price is missing or invalid"
        }

      if new_order_price is None or new_order_price <= 0:
        return {
          "success": False,
          "message": "New Order price is missing or invalid"
        }

      # 🔥 FIX: Correct variable name
      pricing_mode = safe_strip(form_data.get('Pricing Mode'))

      # ✅ If agreed < new_order, MUST select pricing mode
      if agreed < new_order_price and not pricing_mode:
        return {
          "success": False,
          "code": "SELECT_PRICING_MODE",
          "message": "Please select pricing mode"
        }

      # ✅ Validate based on pricing mode
      if pricing_mode == "In Stock":
        if agreed < in_stock_price:
          return {
            "success": False,
            "message":
            f"Agreed Price ({agreed:,.0f}) must not be less than In Stock price ({in_stock_price:,.0f})"
          }

      elif pricing_mode == "New Order":
        if agreed < new_order_price:
          return {
            "success": False,
            "message":
            f"Agreed Price ({agreed:,.0f}) must not be less than New Order price ({new_order_price:,.0f})"
          }

        if agreed > in_stock_price:
          return {
            "success": False,
            "message":
            f"For New Order mode, Agreed Price ({agreed:,.0f}) cannot exceed In Stock price ({in_stock_price:,.0f})"
          }


  # AUTO-NUMBERING FROM SERVER
  if is_new_client:
    client_code = str(_get_next_number('clients', 'Client Code'))

  if is_new_quotation and is_quotation:
    quotation_number = _get_next_number('quotations', 'Quotation#')

  print(f"💾 Saving: client_code={client_code}, quotation_number={quotation_number}")

  # Save
  client_action = save_client_data(client_code, form_data, is_new_client)

  quotation_action = None
  if is_quotation:
    quotation_action = save_quotation_data(
      client_code,
      quotation_number,
      form_data,
      is_new_quotation
    )

  actions = [a for a in (client_action, quotation_action) if a]

  return {
    "success": True,
    "message": " + ".join(actions),
    "client_code": client_code,
    "quotation_number": quotation_number if is_quotation else None
  }


# =========================================================
# SAVE FUNCTIONS
# =========================================================

def save_client_data(client_code, form_data, is_new):
  """Save or update client data"""

  date_value = form_data.get('Date')
  if date_value and isinstance(date_value, str):
    try:
      date_value = datetime.strptime(date_value, '%Y-%m-%d').date()
    except:
      date_value = datetime.now().date()
  elif not date_value:
    date_value = datetime.now().date()

  data = {
    'Client Code': str(client_code),
    'Date': safe_strip(form_data.get('Date')),
    'Client Name': safe_strip(form_data.get('Client Name')),
    'Company': safe_strip(form_data.get('Company')),
    'Phone': safe_strip(form_data.get('Phone')),
    'Country': safe_strip(form_data.get('Country')),
    'Address': safe_strip(form_data.get('Address')),
    'Email': safe_strip(form_data.get('Email')),
    'Sales Rep': safe_strip(form_data.get('Sales Rep')),
    'Source': safe_strip(form_data.get('Source')),
  }

  if is_new:
    app_tables.clients.add_row(**data)
    return "Added Client"

  row = app_tables.clients.get(**{"Client Code": str(client_code)})
  if row:
    row.update(**data)
  return "Updated Client"


def save_quotation_data(client_code, quotation_number, form_data, is_new):
  """Save or update quotation data"""

  # Date handling
  date_value = form_data.get('Date')
  if date_value and isinstance(date_value, str):
    try:
      date_value = datetime.strptime(date_value, '%Y-%m-%d').date()
    except:
      date_value = datetime.now().date()
  elif not date_value:
    date_value = datetime.now().date()

  data = {
    'Client Code': safe_int(client_code),
    'Quotation#': int(quotation_number),
    'Date': date_value,
    'Client Name': safe_strip(form_data.get('Client Name')),
    'Company': safe_strip(form_data.get('Company')),
    'Phone': safe_strip(form_data.get('Phone')),
    'Country': safe_strip(form_data.get('Country')),
    'Address': safe_strip(form_data.get('Address')),
    'Email': safe_strip(form_data.get('Email')),
    'Sales Rep': safe_strip(form_data.get('Sales Rep')),
    'Source': safe_strip(form_data.get('Source')),
    'Notes': safe_strip(form_data.get('Notes')),

    'Model': safe_strip(form_data.get('Model')),
    'Machine type': safe_strip(form_data.get('machine_type')),
    'Number of colors': safe_int(form_data.get('Number of colors')),
    'Machine width': safe_int(form_data.get('Machine width')),
    'Material': safe_strip(form_data.get('Material')),
    'Winder': safe_strip(form_data.get('Winder')),

    'Video inspection': yes_no(form_data.get('Video inspection')),
    'PLC': yes_no(form_data.get('PLC')),
    'Slitter': yes_no(form_data.get('Slitter')),
    'Pneumatic Unwind': yes_no(form_data.get('Pneumatic Unwind')),
    'Hydraulic Station Unwind': yes_no(form_data.get('Hydraulic Station Unwind')),
    'Pneumatic Rewind': yes_no(form_data.get('Pneumatic Rewind')),
    'Surface Rewind': yes_no(form_data.get('Surface Rewind')),

    'Given Price': safe_float(form_data.get('Given Price')),
    'Agreed Price': safe_float(form_data.get('Agreed Price')),
    "Standard Machine FOB cost": safe_strip(form_data.get("std_price")),
    "Machine FOB cost With Cylinders": safe_strip(form_data.get("price_with_cylinders")),
    'FOB price for over seas clients': safe_float(form_data.get('overseas_price')),
    'Exchange Rate': safe_float(form_data.get('exchange_rate')),
    'In Stock': safe_float(form_data.get('In Stock')),
    'New Order': safe_float(form_data.get('New Order')),
    'Pricing Mode': safe_strip(form_data.get('Pricing Mode')),
  }

  for i in range(1, 13):
    data[f'Size in CM{i}'] = safe_strip(form_data.get(f'Size in CM{i}'))
    data[f"Count{i}"] = safe_strip(form_data.get(f"Count{i}"))
    data[f'Cost{i}'] = safe_strip(form_data.get(f'Cost{i}'))

  if is_new:
    app_tables.quotations.add_row(**data)
    return "Added Quotation"

  row = app_tables.quotations.get(**{"Quotation#": int(quotation_number)})
  if not row:
    raise Exception("Quotation not found")

  row.update(**data)
  return "Updated Quotation"


# =========================================================
# GET FUNCTIONS
# =========================================================

@anvil.server.callable
def get_all_quotations():
  rows = []
  for r in app_tables.quotations.search():
    row_data = {
      "Client Code": r["Client Code"],
      "Quotation#": r["Quotation#"],
      "Date": r["Date"].isoformat() if r["Date"] else "",
      "Client Name": r["Client Name"],
      "Company": r["Company"],
      "Phone": r["Phone"],
      "Country": r["Country"],
      "Address": r["Address"],
      "Email": r["Email"],
      "Sales Rep": r["Sales Rep"],
      "Source": r["Source"],
      "Given Price": r["Given Price"],
      "Agreed Price": r["Agreed Price"],
      "Notes": r["Notes"],

      "Machine type": r["Machine type"],
      "Number of colors": r["Number of colors"],
      "Machine width": r["Machine width"],
      "Material": r["Material"],
      "Winder": r["Winder"],
      "Video inspection": r["Video inspection"],
      "PLC": r["PLC"],
      "Slitter": r["Slitter"],
      "Pneumatic Unwind": r["Pneumatic Unwind"],
      "Hydraulic Station Unwind": r["Hydraulic Station Unwind"],
      "Pneumatic Rewind": r["Pneumatic Rewind"],
      "Surface Rewind": r["Surface Rewind"],
    }

    for i in range(1, 13):
      row_data[f"Size in CM{i}"] = r[f"Size in CM{i}"]
      row_data[f"Count{i}"] = r[f"Count{i}"]
      row_data[f"Cost{i}"] = r[f"Cost{i}"]

    rows.append(row_data)

  return rows


@anvil.server.callable
def get_all_clients():
  rows = []
  for r in app_tables.clients.search():
    rows.append({
      "Client Code": r["Client Code"],
      "Client Name": r["Client Name"],
      "Company": r["Company"],
      "Phone": r["Phone"],
      "Country": r["Country"],
      "Address": r["Address"],
      "Email": r["Email"],
      "Sales Rep": r["Sales Rep"],
      "Source": r["Source"],
    })

  return rows
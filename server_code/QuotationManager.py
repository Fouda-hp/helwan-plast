"""
Server Module - WITH AUTO-NUMBERING, AUDIT TRAIL & SOFT DELETE
===============================================================
"""

import anvil.server
from anvil.tables import app_tables
from datetime import datetime
import json
import uuid


# =========================================================
# AUDIT LOGGING HELPER
# =========================================================
def log_audit(action, table_name, record_id, old_data, new_data, user_email='system'):
    """Log action to audit trail"""
    try:
        app_tables.audit_log.add_row(
            log_id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            user_email=user_email,
            action=action,
            table_name=table_name,
            record_id=str(record_id) if record_id else None,
            old_data=json.dumps(old_data, default=str) if old_data else None,
            new_data=json.dumps(new_data, default=str) if new_data else None
        )
    except Exception as e:
        print(f"Audit log error: {e}")


# =========================================================
# AUTO-NUMBERING FUNCTIONS
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

    print(f"Checking phone='{phone}'")

    # Search by PHONE ONLY (exclude deleted)
    row = app_tables.clients.get(Phone=phone, is_deleted=False)

    if row:
        code = str(row["Client Code"])
        print(f"Existing phone found, client_code={code}")
        return code

    # New phone -> new client
    new_code = _get_next_number('clients', 'Client Code')
    print(f"New phone, generated client_code={new_code}")
    return str(new_code)


@anvil.server.callable
def get_quotation_number_if_needed(current_number, model):
    """
    Get quotation number only if needed
    Called from JavaScript when model code is built
    """
    if current_number:
        print(f"Quotation number already exists: {current_number}")
        return int(current_number)

    if not model:
        print("No model provided")
        return None

    new_q = _get_next_number('quotations', 'Quotation#')
    print(f"Generated new quotation number: {new_q}")
    return int(new_q)


def _get_next_number(table_name, column_name):
    """
    Generate next number safely (transaction-safe)
    Searches for maximum value and increments
    """
    table = getattr(app_tables, table_name)

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
    print(f"{table_name}.{column_name}: max={max_val}, next={next_val}")
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
    """Check if phone exists (exclude deleted)"""
    phone = safe_strip(phone)
    if not phone:
        return False

    if exclude_client_code is not None:
        exclude_client_code = str(exclude_client_code)

    rows = app_tables.clients.search(Phone=phone, is_deleted=False)
    for r in rows:
        if exclude_client_code is not None and str(r['Client Code']) == exclude_client_code:
            continue
        return True

    return False


@anvil.server.callable
def client_exists(client_code):
    """Check if client exists by code (not deleted)"""
    if not client_code:
        return False

    client_code_str = str(client_code)
    row = app_tables.clients.get(**{"Client Code": client_code_str})
    return row is not None and not row.get('is_deleted', False)


@anvil.server.callable
def quotation_exists(quotation_number):
    """Check if quotation exists by number (not deleted)"""
    if not quotation_number:
        return False

    quotation_int = safe_int(quotation_number)
    if quotation_int is None:
        return False

    row = app_tables.quotations.get(**{"Quotation#": quotation_int})
    return row is not None and not row.get('is_deleted', False)


# =========================================================
# MAIN SAVE FUNCTION
# =========================================================
@anvil.server.callable
def save_quotation(form_data, user_email='system'):
    """Main save function with auto-numbering and audit trail"""

    print("Received form_data")

    # Extract data
    client_code_raw = form_data.get('Client Code')
    quotation_number_raw = form_data.get('Quotation#')
    model = safe_strip(form_data.get('Model'))

    client_code = str(client_code_raw) if client_code_raw else None
    quotation_number = safe_int(quotation_number_raw)

    # Detect existing vs new client
    existing_client_row = None
    if client_code:
        existing_client_row = app_tables.clients.get(**{"Client Code": str(client_code)})
        if existing_client_row and existing_client_row.get('is_deleted', False):
            existing_client_row = None

    is_existing_client = existing_client_row is not None
    is_new_client = not is_existing_client

    is_quotation = bool(
        safe_strip(form_data.get('Model')) and
        safe_strip(form_data.get('Quotation#'))
    )

    is_new_quotation = is_quotation and (not quotation_number or not quotation_exists(quotation_number))

    # Client validation (ONLY if new client)
    missing = []

    if is_new_client:
        if not safe_strip(form_data.get('Client Name')):
            missing.append("Client Name")
        if not safe_strip(form_data.get('Company')):
            missing.append("Company")
        if not safe_strip(form_data.get('Phone')):
            missing.append("Phone")

        if missing:
            return {
                "success": False,
                "message": "Missing Client Data:\n" + "\n".join(missing)
            }

    if is_quotation:
        q_missing = []
        if not form_data.get('Given Price'):
            q_missing.append("Given Price")
        if not form_data.get('Agreed Price'):
            q_missing.append("Agreed Price")

        if q_missing:
            return {
                "success": False,
                "message": "Quotation missing data:\n" + "\n".join(q_missing)
            }

    # Phone validation
    phone = safe_strip(form_data.get('Phone'))

    if phone:
        phone_row = app_tables.clients.get(Phone=phone, is_deleted=False)

        if phone_row:
            if is_existing_client:
                if phone_row != existing_client_row:
                    return {"success": False, "message": "Phone already exists"}
            else:
                return {"success": False, "message": "Phone already exists"}

    # PRICE VALIDATION
    if is_quotation:
        given = safe_float(form_data.get('Given Price'))
        agreed = safe_float(form_data.get('Agreed Price'))

        if given is None or agreed is None:
            return {
                "success": False,
                "message": "Given Price and Agreed Price must be valid numbers"
            }

        if agreed > given:
            return {
                "success": False,
                "message": f"Agreed Price ({agreed:,.0f}) cannot be greater than Given Price ({given:,.0f})"
            }

        is_overseas = bool(form_data.get('Overseas clients'))

        if is_overseas:
            overseas_price = safe_float(form_data.get('overseas_price'))

            if overseas_price is None or overseas_price <= 0:
                return {"success": False, "message": "Overseas price is missing or invalid"}

            if agreed < overseas_price:
                return {
                    "success": False,
                    "message": f"Agreed Price ({agreed:,.0f}) must not be less than Overseas Price ({overseas_price:,.0f})"
                }
        else:
            in_stock_price = safe_float(form_data.get('In Stock'))
            new_order_price = safe_float(form_data.get('New Order'))

            if in_stock_price is None or in_stock_price <= 0:
                return {"success": False, "message": "In Stock price is missing or invalid"}

            if new_order_price is None or new_order_price <= 0:
                return {"success": False, "message": "New Order price is missing or invalid"}

            pricing_mode = safe_strip(form_data.get('Pricing Mode'))

            if agreed < new_order_price and not pricing_mode:
                return {
                    "success": False,
                    "code": "SELECT_PRICING_MODE",
                    "message": "Please select pricing mode"
                }

            if pricing_mode == "In Stock":
                if agreed < in_stock_price:
                    return {
                        "success": False,
                        "message": f"Agreed Price ({agreed:,.0f}) must not be less than In Stock price ({in_stock_price:,.0f})"
                    }

            elif pricing_mode == "New Order":
                if agreed < new_order_price:
                    return {
                        "success": False,
                        "message": f"Agreed Price ({agreed:,.0f}) must not be less than New Order price ({new_order_price:,.0f})"
                    }

                if agreed > in_stock_price:
                    return {
                        "success": False,
                        "message": f"For New Order mode, Agreed Price ({agreed:,.0f}) cannot exceed In Stock price ({in_stock_price:,.0f})"
                    }

    # AUTO-NUMBERING FROM SERVER
    if is_new_client:
        client_code = str(_get_next_number('clients', 'Client Code'))

    if is_new_quotation and is_quotation:
        quotation_number = _get_next_number('quotations', 'Quotation#')

    print(f"Saving: client_code={client_code}, quotation_number={quotation_number}")

    # Save with audit
    client_action = save_client_data(client_code, form_data, is_new_client, user_email)

    quotation_action = None
    if is_quotation:
        quotation_action = save_quotation_data(
            client_code,
            quotation_number,
            form_data,
            is_new_quotation,
            user_email
        )

    actions = [a for a in (client_action, quotation_action) if a]

    return {
        "success": True,
        "message": " + ".join(actions),
        "client_code": client_code,
        "quotation_number": quotation_number if is_quotation else None
    }


# =========================================================
# SAVE FUNCTIONS WITH AUDIT
# =========================================================
def save_client_data(client_code, form_data, is_new, user_email='system'):
    """Save or update client data with audit"""

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
        'Date': date_value,
        'Client Name': safe_strip(form_data.get('Client Name')),
        'Company': safe_strip(form_data.get('Company')),
        'Phone': safe_strip(form_data.get('Phone')),
        'Country': safe_strip(form_data.get('Country')),
        'Address': safe_strip(form_data.get('Address')),
        'Email': safe_strip(form_data.get('Email')),
        'Sales Rep': safe_strip(form_data.get('Sales Rep')),
        'Source': safe_strip(form_data.get('Source')),
        'is_deleted': False,
        'updated_by': user_email,
        'updated_at': datetime.now()
    }

    if is_new:
        data['created_by'] = user_email
        data['created_at'] = datetime.now()
        app_tables.clients.add_row(**data)
        log_audit('CREATE', 'clients', client_code, None, data, user_email)
        return "Added Client"

    row = app_tables.clients.get(**{"Client Code": str(client_code)})
    if row:
        old_data = {k: row[k] for k in data.keys() if k in [c.name for c in app_tables.clients.list_columns()]}
        row.update(**data)
        log_audit('UPDATE', 'clients', client_code, old_data, data, user_email)
    return "Updated Client"


def save_quotation_data(client_code, quotation_number, form_data, is_new, user_email='system'):
    """Save or update quotation data with audit"""

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
        'Quotation#': int(quotation_number),
        'Date': date_value,
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

        'is_deleted': False,
        'updated_by': user_email,
        'updated_at': datetime.now()
    }

    for i in range(1, 13):
        data[f'Size in CM{i}'] = safe_strip(form_data.get(f'Size in CM{i}'))
        data[f"Count{i}"] = safe_strip(form_data.get(f"Count{i}"))
        data[f'Cost{i}'] = safe_strip(form_data.get(f'Cost{i}'))

    if is_new:
        data['created_by'] = user_email
        data['created_at'] = datetime.now()
        app_tables.quotations.add_row(**data)
        log_audit('CREATE', 'quotations', quotation_number, None, data, user_email)
        return "Added Quotation"

    row = app_tables.quotations.get(**{"Quotation#": int(quotation_number)})
    if not row:
        raise Exception("Quotation not found")

    old_data = {}
    for k in data.keys():
        try:
            old_data[k] = row[k]
        except:
            pass

    row.update(**data)
    log_audit('UPDATE', 'quotations', quotation_number, old_data, data, user_email)
    return "Updated Quotation"


# =========================================================
# SOFT DELETE (Admin Only)
# =========================================================
@anvil.server.callable
def soft_delete_client(client_code, user_email='admin'):
    """Soft delete a client (admin only)"""

    row = app_tables.clients.get(**{"Client Code": str(client_code)})
    if not row:
        return {"success": False, "message": "Client not found"}

    old_data = {"is_deleted": row.get('is_deleted', False)}

    row.update(
        is_deleted=True,
        deleted_at=datetime.now(),
        deleted_by=user_email
    )

    log_audit('SOFT_DELETE', 'clients', client_code, old_data, {"is_deleted": True}, user_email)

    return {"success": True, "message": "Client deleted successfully"}


@anvil.server.callable
def soft_delete_quotation(quotation_number, user_email='admin'):
    """Soft delete a quotation (admin only)"""

    row = app_tables.quotations.get(**{"Quotation#": int(quotation_number)})
    if not row:
        return {"success": False, "message": "Quotation not found"}

    old_data = {"is_deleted": row.get('is_deleted', False)}

    row.update(
        is_deleted=True,
        deleted_at=datetime.now(),
        deleted_by=user_email
    )

    log_audit('SOFT_DELETE', 'quotations', quotation_number, old_data, {"is_deleted": True}, user_email)

    return {"success": True, "message": "Quotation deleted successfully"}


@anvil.server.callable
def restore_client(client_code, user_email='admin'):
    """Restore a soft-deleted client (admin only)"""

    row = app_tables.clients.get(**{"Client Code": str(client_code)})
    if not row:
        return {"success": False, "message": "Client not found"}

    row.update(
        is_deleted=False,
        deleted_at=None,
        deleted_by=None
    )

    log_audit('RESTORE', 'clients', client_code, {"is_deleted": True}, {"is_deleted": False}, user_email)

    return {"success": True, "message": "Client restored successfully"}


@anvil.server.callable
def restore_quotation(quotation_number, user_email='admin'):
    """Restore a soft-deleted quotation (admin only)"""

    row = app_tables.quotations.get(**{"Quotation#": int(quotation_number)})
    if not row:
        return {"success": False, "message": "Quotation not found"}

    row.update(
        is_deleted=False,
        deleted_at=None,
        deleted_by=None
    )

    log_audit('RESTORE', 'quotations', quotation_number, {"is_deleted": True}, {"is_deleted": False}, user_email)

    return {"success": True, "message": "Quotation restored successfully"}


# =========================================================
# GET FUNCTIONS WITH PAGINATION & SEARCH
# =========================================================
@anvil.server.callable
def get_all_quotations(page=1, per_page=20, search='', include_deleted=False):
    """Get quotations with pagination and search"""

    all_rows = list(app_tables.quotations.search())

    # Filter deleted
    if not include_deleted:
        all_rows = [r for r in all_rows if not r.get('is_deleted', False)]

    # Search filter
    if search:
        search = search.lower()
        filtered = []
        for r in all_rows:
            client = app_tables.clients.get(**{"Client Code": str(r['Client Code'])})
            client_name = client['Client Name'].lower() if client and client['Client Name'] else ''
            company = client['Company'].lower() if client and client['Company'] else ''

            if (search in client_name or
                search in company or
                search in str(r.get('Quotation#', '')) or
                search in str(r.get('Model', '')).lower()):
                filtered.append(r)
        all_rows = filtered

    # Sort by date desc
    all_rows.sort(key=lambda x: x.get('Date') or datetime.min.date(), reverse=True)

    total = len(all_rows)
    total_pages = (total + per_page - 1) // per_page

    start = (page - 1) * per_page
    end = start + per_page
    page_rows = all_rows[start:end]

    rows = []
    for r in page_rows:
        # Get client data
        client = app_tables.clients.get(**{"Client Code": str(r['Client Code'])})

        row_data = {
            "Client Code": r["Client Code"],
            "Quotation#": r["Quotation#"],
            "Date": r["Date"].isoformat() if r["Date"] else "",
            "Client Name": client["Client Name"] if client else "",
            "Company": client["Company"] if client else "",
            "Phone": client["Phone"] if client else "",
            "Country": client["Country"] if client else "",
            "Address": client["Address"] if client else "",
            "Email": client["Email"] if client else "",
            "Sales Rep": client["Sales Rep"] if client else "",
            "Source": client["Source"] if client else "",
            "Given Price": r["Given Price"],
            "Agreed Price": r["Agreed Price"],
            "Notes": r["Notes"],
            "Model": r["Model"],
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
            "is_deleted": r.get("is_deleted", False)
        }

        for i in range(1, 13):
            row_data[f"Size in CM{i}"] = r[f"Size in CM{i}"]
            row_data[f"Count{i}"] = r[f"Count{i}"]
            row_data[f"Cost{i}"] = r[f"Cost{i}"]

        rows.append(row_data)

    return {
        "data": rows,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages
    }


@anvil.server.callable
def get_all_clients(page=1, per_page=20, search='', include_deleted=False):
    """Get clients with pagination and search"""

    all_rows = list(app_tables.clients.search())

    # Filter deleted
    if not include_deleted:
        all_rows = [r for r in all_rows if not r.get('is_deleted', False)]

    # Search filter
    if search:
        search = search.lower()
        all_rows = [r for r in all_rows if (
            search in (r['Client Name'] or '').lower() or
            search in (r['Company'] or '').lower() or
            search in (r['Phone'] or '').lower() or
            search in str(r['Client Code']).lower()
        )]

    # Sort by client code
    all_rows.sort(key=lambda x: int(x['Client Code']) if x['Client Code'].isdigit() else 0, reverse=True)

    total = len(all_rows)
    total_pages = (total + per_page - 1) // per_page

    start = (page - 1) * per_page
    end = start + per_page
    page_rows = all_rows[start:end]

    rows = []
    for r in page_rows:
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
            "Date": r["Date"].isoformat() if isinstance(r["Date"], datetime) else str(r["Date"] or ""),
            "is_deleted": r.get("is_deleted", False)
        })

    return {
        "data": rows,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages
    }


# =========================================================
# EXPORT FUNCTIONS
# =========================================================
@anvil.server.callable
def export_clients_data(include_deleted=False):
    """Export all clients data for CSV/Excel"""

    all_rows = list(app_tables.clients.search())

    if not include_deleted:
        all_rows = [r for r in all_rows if not r.get('is_deleted', False)]

    data = []
    for r in all_rows:
        data.append({
            "Client Code": r["Client Code"],
            "Client Name": r["Client Name"],
            "Company": r["Company"],
            "Phone": r["Phone"],
            "Country": r["Country"],
            "Address": r["Address"],
            "Email": r["Email"],
            "Sales Rep": r["Sales Rep"],
            "Source": r["Source"],
            "Date": str(r["Date"] or "")
        })

    return data


@anvil.server.callable
def export_quotations_data(include_deleted=False):
    """Export all quotations data for CSV/Excel"""

    all_rows = list(app_tables.quotations.search())

    if not include_deleted:
        all_rows = [r for r in all_rows if not r.get('is_deleted', False)]

    data = []
    for r in all_rows:
        client = app_tables.clients.get(**{"Client Code": str(r['Client Code'])})

        row_data = {
            "Quotation#": r["Quotation#"],
            "Date": str(r["Date"] or ""),
            "Client Code": r["Client Code"],
            "Client Name": client["Client Name"] if client else "",
            "Company": client["Company"] if client else "",
            "Phone": client["Phone"] if client else "",
            "Model": r["Model"],
            "Machine type": r["Machine type"],
            "Number of colors": r["Number of colors"],
            "Machine width": r["Machine width"],
            "Material": r["Material"],
            "Winder": r["Winder"],
            "Given Price": r["Given Price"],
            "Agreed Price": r["Agreed Price"],
            "In Stock": r["In Stock"],
            "New Order": r["New Order"],
            "Notes": r["Notes"]
        }
        data.append(row_data)

    return data


# =========================================================
# STATISTICS (For Admin Dashboard)
# =========================================================
@anvil.server.callable
def get_dashboard_stats():
    """Get statistics for admin dashboard"""

    clients = list(app_tables.clients.search())
    quotations = list(app_tables.quotations.search())

    active_clients = [c for c in clients if not c.get('is_deleted', False)]
    active_quotations = [q for q in quotations if not q.get('is_deleted', False)]

    total_agreed = sum(q['Agreed Price'] or 0 for q in active_quotations)

    # This month
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    this_month_quotations = [
        q for q in active_quotations
        if q['Date'] and q['Date'] >= month_start.date()
    ]

    this_month_value = sum(q['Agreed Price'] or 0 for q in this_month_quotations)

    return {
        "total_clients": len(active_clients),
        "total_quotations": len(active_quotations),
        "total_value": total_agreed,
        "this_month_quotations": len(this_month_quotations),
        "this_month_value": this_month_value,
        "deleted_clients": len(clients) - len(active_clients),
        "deleted_quotations": len(quotations) - len(active_quotations)
    }

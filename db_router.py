"""
db_router.py
────────────
Manages per-company database connections.

Platform DB  → YOUR MySQL (configured via PLATFORM_DB_URI env var in app.py)
Customer DB  → Separate MySQL database on the SAME VPS, one per company.
               Name pattern:  erp_<company_id_lowercase>
               URI built from env vars: VPS_MYSQL_HOST/PORT/USER/PASSWORD

Every company that registers gets its own isolated MySQL database created
automatically. No SQLite, no cloud storage — everything stays on the VPS.

Environment variables
─────────────────────
VPS_MYSQL_HOST      MySQL host              (default: 127.0.0.1)
VPS_MYSQL_PORT      MySQL port              (default: 3306)
VPS_MYSQL_USER      MySQL user              (default: root)
VPS_MYSQL_PASSWORD  MySQL password          (default: "")

Usage in routes
───────────────
    from db_router import get_customer_session, close_customer_session
    session = get_customer_session(company_id)
    users   = session.query(CompanyUser).all()
    close_customer_session(company_id)
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.exc import PendingRollbackError, OperationalError
from sqlalchemy.orm import sessionmaker, scoped_session
from customer_models import customer_db   # exposes .metadata (plain SQLAlchemy Base)

# ─────────────────────────────────────────────────────────────────────────────
# MySQL connection settings for customer databases on this VPS
# ─────────────────────────────────────────────────────────────────────────────
VPS_MYSQL_HOST     = os.environ.get("VPS_MYSQL_HOST",     "127.0.0.1")
VPS_MYSQL_PORT     = os.environ.get("VPS_MYSQL_PORT",     "3306")
VPS_MYSQL_USER     = os.environ.get("VPS_MYSQL_USER",     "root")
VPS_MYSQL_PASSWORD = os.environ.get("VPS_MYSQL_PASSWORD", "")

# ─────────────────────────────────────────────────────────────────────────────
# In-process cache:  { company_id → scoped_session factory }
# ─────────────────────────────────────────────────────────────────────────────
_engine_cache:  dict = {}
_session_cache: dict = {}


def _db_name(company_id) -> str:
    """Return the MySQL database name for a company."""
    return f"erp_{str(company_id).lower()}"


def _build_uri(company_id: str) -> str:
    """Build the mysql+pymysql URI for a company's dedicated database."""
    db_name = _db_name(company_id)
    pwd     = VPS_MYSQL_PASSWORD
    return (
        f"mysql+pymysql://{VPS_MYSQL_USER}:{pwd}"
        f"@{VPS_MYSQL_HOST}:{VPS_MYSQL_PORT}/{db_name}"
    )


def _create_database_if_missing(company_id: str):
    """
    Issue CREATE DATABASE IF NOT EXISTS on the VPS MySQL server.
    Uses a root-level connection (no database selected).
    """
    db_name = _db_name(company_id)
    root_uri = (
        f"mysql+pymysql://{VPS_MYSQL_USER}:{VPS_MYSQL_PASSWORD}"
        f"@{VPS_MYSQL_HOST}:{VPS_MYSQL_PORT}/"
    )
    engine = create_engine(root_uri)
    try:
        with engine.connect() as conn:
            conn.execute(text(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            ))
            conn.commit()
    finally:
        engine.dispose()


CUSTOMER_SCHEMA_PATCHES = [
    # company_users
    "ALTER TABLE company_users ADD COLUMN field_permissions JSON",
    "ALTER TABLE company_users ADD COLUMN editable_fields JSON",
    "ALTER TABLE company_users ADD COLUMN permission_overrides JSON",
    "ALTER TABLE company_users ADD COLUMN is_gst_registered BOOLEAN DEFAULT FALSE",

    # company_role_permissions
    "ALTER TABLE company_role_permissions ADD COLUMN field_permissions_json TEXT NULL",
    
    # cash_transactions & bank_transactions
    "ALTER TABLE cash_transactions ADD COLUMN party_name VARCHAR(255) NULL",
    "ALTER TABLE cash_transactions ADD COLUMN applied_ref_type VARCHAR(20)",
    "ALTER TABLE cash_transactions ADD COLUMN applied_ref_id INTEGER",
    "ALTER TABLE cash_transactions ADD COLUMN applied_ci_id INTEGER",
    "ALTER TABLE cash_transactions ADD COLUMN applied_ci_ids_json TEXT",
    "ALTER TABLE cash_transactions ADD COLUMN applied_breakdown_json TEXT",
    "ALTER TABLE bank_transactions ADD COLUMN party_name VARCHAR(255) NULL",
    "ALTER TABLE bank_transactions ADD COLUMN applied_ref_type VARCHAR(20)",
    "ALTER TABLE bank_transactions ADD COLUMN applied_ref_id INTEGER",
    "ALTER TABLE bank_transactions ADD COLUMN applied_ci_id INTEGER",
    "ALTER TABLE bank_transactions ADD COLUMN applied_ci_ids_json TEXT",
    "ALTER TABLE bank_transactions ADD COLUMN applied_breakdown_json TEXT",
    
    # clients
    "ALTER TABLE clients ADD COLUMN client_id VARCHAR(20) UNIQUE NULL",
    "ALTER TABLE clients ADD COLUMN alternate_phone VARCHAR(20) NULL",
    "ALTER TABLE clients ADD COLUMN website VARCHAR(255) NULL",
    "ALTER TABLE clients ADD COLUMN aadhar_number VARCHAR(12) NULL",
    "ALTER TABLE clients ADD COLUMN aadhar_front_file VARCHAR(255) NULL",
    "ALTER TABLE clients ADD COLUMN aadhar_back_file VARCHAR(255) NULL",
    "ALTER TABLE clients ADD COLUMN pan_front_file VARCHAR(255) NULL",
    "ALTER TABLE clients ADD COLUMN pan_back_file VARCHAR(255) NULL",
    "ALTER TABLE clients ADD COLUMN statement_cutoff DATETIME NULL",
    "ALTER TABLE clients ADD COLUMN invoice_statement_cutoff DATETIME NULL",
    "ALTER TABLE clients ADD COLUMN invoice_opening_balance FLOAT DEFAULT 0",
    
    # invoices
    "ALTER TABLE invoices ADD COLUMN docket_no VARCHAR(50) NULL",
    "ALTER TABLE invoices ADD COLUMN submit_token VARCHAR(64) NULL",
    "ALTER TABLE invoices ADD COLUMN created_by VARCHAR(100) NULL",
    "ALTER TABLE invoices ADD COLUMN updated_by VARCHAR(100) NULL",
    "ALTER TABLE invoices ADD COLUMN discount FLOAT DEFAULT 0.0",
    "ALTER TABLE invoices ADD COLUMN resale_charges FLOAT DEFAULT 0.0",
    "ALTER TABLE invoices ADD COLUMN resale_reason VARCHAR(200) NULL",
    "ALTER TABLE invoices ADD COLUMN resale_date DATE NULL",
    "ALTER TABLE invoices ADD COLUMN resale_notes TEXT NULL",
    "ALTER TABLE invoices ADD COLUMN has_resale BOOLEAN DEFAULT FALSE",

    # customer_invoices
    "ALTER TABLE customer_invoices ADD COLUMN billing_address TEXT NULL",
    "ALTER TABLE customer_invoices ADD COLUMN shipping_address TEXT NULL",
    "ALTER TABLE customer_invoices ADD COLUMN client_gstin VARCHAR(50) NULL",
    "ALTER TABLE customer_invoices ADD COLUMN client_state VARCHAR(100) NULL",
    "ALTER TABLE customer_invoices ADD COLUMN payment_terms VARCHAR(100) NULL",
    "ALTER TABLE customer_invoices ADD COLUMN terms TEXT NULL",
    "ALTER TABLE customer_invoices ADD COLUMN cgst_total FLOAT NOT NULL DEFAULT 0.0",
    "ALTER TABLE customer_invoices ADD COLUMN sgst_total FLOAT NOT NULL DEFAULT 0.0",
    "ALTER TABLE customer_invoices ADD COLUMN igst_total FLOAT NOT NULL DEFAULT 0.0",

    # customer_invoice_items
    "ALTER TABLE customer_invoice_items ADD COLUMN stock_item_id INTEGER NULL",
    "ALTER TABLE customer_invoice_items ADD COLUMN item_code VARCHAR(50) NULL",
    "ALTER TABLE customer_invoice_items ADD COLUMN item_name VARCHAR(200) NULL",
    "ALTER TABLE customer_invoice_items ADD COLUMN hsn VARCHAR(20) NULL",
    "ALTER TABLE customer_invoice_items ADD COLUMN unit VARCHAR(20) DEFAULT 'pcs'",
    "ALTER TABLE customer_invoice_items ADD COLUMN rate FLOAT DEFAULT 0.0",
    "ALTER TABLE customer_invoice_items ADD COLUMN discount_percent FLOAT DEFAULT 0.0",

    # cheques
    "ALTER TABLE cheques ADD COLUMN invoice_id INTEGER NULL",
    "ALTER TABLE cheques ADD COLUMN purchase_invoice_id INTEGER NULL",

    # company_manifests
    "ALTER TABLE company_manifests ADD COLUMN generated_at DATETIME NULL",
    "ALTER TABLE company_manifests ADD COLUMN generated_by VARCHAR(100) NULL",
    "ALTER TABLE company_manifests ADD COLUMN status VARCHAR(50) DEFAULT 'Generated'",
    "ALTER TABLE company_manifests ADD COLUMN stock_deducted BOOLEAN DEFAULT FALSE",

    # manifest_entries
    "ALTER TABLE manifest_entries ADD COLUMN generated_at DATETIME NULL",
    "ALTER TABLE manifest_entries ADD COLUMN generated_by VARCHAR(100) NULL",
    "ALTER TABLE manifest_entries ADD COLUMN dispatched_at DATETIME NULL",
    "ALTER TABLE manifest_entries ADD COLUMN dispatched_by VARCHAR(100) NULL",
    "ALTER TABLE manifest_entries ADD COLUMN status VARCHAR(50) DEFAULT 'Pending'",
    "ALTER TABLE manifest_entries ADD COLUMN item_type VARCHAR(50) NULL",

    # estimates & estimate_items
    "ALTER TABLE estimates ADD COLUMN client_name VARCHAR(200) NULL",
    "ALTER TABLE estimates ADD COLUMN client_address TEXT NULL",
    "ALTER TABLE estimates ADD COLUMN client_gstin VARCHAR(50) NULL",
    "ALTER TABLE estimates ADD COLUMN client_state VARCHAR(100) NULL",
    "ALTER TABLE estimates ADD COLUMN payment_terms VARCHAR(100) NULL",
    "ALTER TABLE estimates ADD COLUMN delivery_terms VARCHAR(100) NULL",
    "ALTER TABLE estimates ADD COLUMN cgst_total FLOAT DEFAULT 0.0",
    "ALTER TABLE estimates ADD COLUMN sgst_total FLOAT DEFAULT 0.0",
    "ALTER TABLE estimates ADD COLUMN igst_total FLOAT DEFAULT 0.0",
    "ALTER TABLE estimates ADD COLUMN created_by VARCHAR(100) NULL",
    "ALTER TABLE estimates ADD COLUMN updated_by VARCHAR(100) NULL",
    "ALTER TABLE estimates ADD COLUMN version INTEGER DEFAULT 1",
    "ALTER TABLE estimate_items ADD COLUMN stock_item_id INTEGER NULL",
    "ALTER TABLE estimate_items ADD COLUMN item_code VARCHAR(50) NULL",
    "ALTER TABLE estimate_items ADD COLUMN item_name VARCHAR(200) NULL",
    "ALTER TABLE estimate_items ADD COLUMN hsn VARCHAR(20) NULL",
    "ALTER TABLE estimate_items ADD COLUMN unit VARCHAR(20) DEFAULT 'pcs'",
    "ALTER TABLE estimate_items ADD COLUMN discount_percent FLOAT DEFAULT 0.0",
    "ALTER TABLE estimate_items ADD COLUMN taxable_amount FLOAT DEFAULT 0.0",
    "ALTER TABLE estimate_items ADD COLUMN gst_percent FLOAT DEFAULT 0.0",
    "ALTER TABLE estimate_items ADD COLUMN cgst_amount FLOAT DEFAULT 0.0",
    "ALTER TABLE estimate_items ADD COLUMN sgst_amount FLOAT DEFAULT 0.0",
    "ALTER TABLE estimate_items ADD COLUMN igst_amount FLOAT DEFAULT 0.0",
    "ALTER TABLE estimate_items ADD COLUMN total_amount FLOAT DEFAULT 0.0",

    # purchase_invoices
    "ALTER TABLE purchase_invoices ADD COLUMN supplier_address TEXT NULL",
    "ALTER TABLE purchase_invoices ADD COLUMN supplier_gstin VARCHAR(50) NULL",
    "ALTER TABLE purchase_invoices ADD COLUMN supplier_state VARCHAR(100) NULL",
    "ALTER TABLE purchase_invoices ADD COLUMN supplier_phone VARCHAR(50) NULL",
    "ALTER TABLE purchase_invoices ADD COLUMN supplier_email VARCHAR(100) NULL",
    "ALTER TABLE purchase_invoices ADD COLUMN reference_po_no VARCHAR(100) NULL",
    "ALTER TABLE purchase_invoices ADD COLUMN cgst_total FLOAT DEFAULT 0.0",
    "ALTER TABLE purchase_invoices ADD COLUMN sgst_total FLOAT DEFAULT 0.0",
    "ALTER TABLE purchase_invoices ADD COLUMN igst_total FLOAT DEFAULT 0.0",
    "ALTER TABLE purchase_invoices ADD COLUMN terms TEXT NULL",
    "ALTER TABLE purchase_invoices ADD COLUMN created_by VARCHAR(100) NULL",
    "ALTER TABLE purchase_invoices ADD COLUMN updated_by VARCHAR(100) NULL",

    # purchase_invoice_items
    "ALTER TABLE purchase_invoice_items ADD COLUMN item_code VARCHAR(50) NULL",
    "ALTER TABLE purchase_invoice_items ADD COLUMN item_name VARCHAR(200) NULL",
    "ALTER TABLE purchase_invoice_items ADD COLUMN rate FLOAT DEFAULT 0.0",
    "ALTER TABLE purchase_invoice_items ADD COLUMN taxable_amount FLOAT DEFAULT 0.0",
    "ALTER TABLE purchase_invoice_items ADD COLUMN source_invoice_id VARCHAR(50) NULL",
    "ALTER TABLE purchase_invoice_items ADD COLUMN carrier_ref VARCHAR(100) NULL",
    "ALTER TABLE purchase_invoice_items ADD COLUMN consignee_name VARCHAR(200) NULL",
    "ALTER TABLE purchase_invoice_items ADD COLUMN other_charges FLOAT DEFAULT 0.0",
    "ALTER TABLE purchase_invoice_items ADD COLUMN resale_charges FLOAT DEFAULT 0.0",

    # stock_items
    "ALTER TABLE stock_items ADD COLUMN shipper_name VARCHAR(200) NULL",

    # stock_purchase_history
    "ALTER TABLE stock_purchase_history ADD COLUMN awb_no VARCHAR(50) NULL",
    "ALTER TABLE stock_purchase_history ADD COLUMN weight FLOAT DEFAULT 0.0",
    "ALTER TABLE stock_purchase_history ADD COLUMN length FLOAT DEFAULT 0.0",
    "ALTER TABLE stock_purchase_history ADD COLUMN width FLOAT DEFAULT 0.0",
    "ALTER TABLE stock_purchase_history ADD COLUMN height FLOAT DEFAULT 0.0",
    "ALTER TABLE stock_purchase_history ADD COLUMN source VARCHAR(100) NULL",
    "ALTER TABLE stock_purchase_history ADD COLUMN destination VARCHAR(100) NULL",

    # suppliers
    "ALTER TABLE suppliers ADD COLUMN supplier_id VARCHAR(20) NULL",
    "ALTER TABLE suppliers ADD COLUMN aadhar_number VARCHAR(12) NULL",
    "ALTER TABLE suppliers ADD COLUMN statement_cutoff DATETIME NULL",

    # whatsapp_logs
    "ALTER TABLE whatsapp_logs ADD COLUMN manifest_id INTEGER NULL",
    "ALTER TABLE whatsapp_logs ADD COLUMN manual_link TEXT NULL",

    # ── Multi-Currency & Localized Tax Patches ──────────────────────────────────
    # purchase_invoices
    "ALTER TABLE purchase_invoices ADD COLUMN currency VARCHAR(10) DEFAULT 'INR'",
    "ALTER TABLE purchase_invoices ADD COLUMN exchange_rate FLOAT DEFAULT 1.0",
    "ALTER TABLE purchase_invoices ADD COLUMN base_subtotal FLOAT DEFAULT 0.0",
    "ALTER TABLE purchase_invoices ADD COLUMN base_tax_amount FLOAT DEFAULT 0.0",
    "ALTER TABLE purchase_invoices ADD COLUMN base_grand_total FLOAT DEFAULT 0.0",
    "ALTER TABLE purchase_invoices ADD COLUMN base_paid_amount FLOAT DEFAULT 0.0",
    "ALTER TABLE purchase_invoices ADD COLUMN base_balance FLOAT DEFAULT 0.0",
    "ALTER TABLE purchase_invoices ADD COLUMN tax_regime VARCHAR(50) DEFAULT 'GST'",
    "ALTER TABLE purchase_invoices ADD COLUMN tax_type VARCHAR(50) DEFAULT 'Domestic'",

    # purchase_invoice_items
    "ALTER TABLE purchase_invoice_items ADD COLUMN base_rate FLOAT DEFAULT 0.0",
    "ALTER TABLE purchase_invoice_items ADD COLUMN base_taxable_amount FLOAT DEFAULT 0.0",
    "ALTER TABLE purchase_invoice_items ADD COLUMN base_total_amount FLOAT DEFAULT 0.0",

    # customer_invoices
    "ALTER TABLE customer_invoices ADD COLUMN currency VARCHAR(10) DEFAULT 'INR'",
    "ALTER TABLE customer_invoices ADD COLUMN exchange_rate FLOAT DEFAULT 1.0",
    "ALTER TABLE customer_invoices ADD COLUMN base_subtotal FLOAT DEFAULT 0.0",
    "ALTER TABLE customer_invoices ADD COLUMN base_tax_amount FLOAT DEFAULT 0.0",
    "ALTER TABLE customer_invoices ADD COLUMN base_grand_total FLOAT DEFAULT 0.0",
    "ALTER TABLE customer_invoices ADD COLUMN tax_regime VARCHAR(50) DEFAULT 'GST'",

    # customer_invoice_items
    "ALTER TABLE customer_invoice_items ADD COLUMN base_rate FLOAT DEFAULT 0.0",
    "ALTER TABLE customer_invoice_items ADD COLUMN base_taxable_amount FLOAT DEFAULT 0.0",
    "ALTER TABLE customer_invoice_items ADD COLUMN base_total_amount FLOAT DEFAULT 0.0",

    # estimates
    "ALTER TABLE estimates ADD COLUMN currency VARCHAR(10) DEFAULT 'INR'",
    "ALTER TABLE estimates ADD COLUMN exchange_rate FLOAT DEFAULT 1.0",
    "ALTER TABLE estimates ADD COLUMN base_subtotal FLOAT DEFAULT 0.0",
    "ALTER TABLE estimates ADD COLUMN base_tax_amount FLOAT DEFAULT 0.0",
    "ALTER TABLE estimates ADD COLUMN base_grand_total FLOAT DEFAULT 0.0",
    "ALTER TABLE estimates ADD COLUMN tax_regime VARCHAR(50) DEFAULT 'GST'",

    # stock_purchase_history
    "ALTER TABLE stock_purchase_history ADD COLUMN currency VARCHAR(10) DEFAULT 'INR'",
    "ALTER TABLE stock_purchase_history ADD COLUMN exchange_rate FLOAT DEFAULT 1.0",
    "ALTER TABLE stock_purchase_history ADD COLUMN base_purchase_rate FLOAT DEFAULT 0.0",

    # suppliers & clients
    "ALTER TABLE suppliers ADD COLUMN currency VARCHAR(10) NULL",
    "ALTER TABLE suppliers ADD COLUMN trn_number VARCHAR(50) NULL",
    "ALTER TABLE suppliers ADD COLUMN tax_regime VARCHAR(50) NULL",
    "ALTER TABLE clients ADD COLUMN currency VARCHAR(10) NULL",
    "ALTER TABLE clients ADD COLUMN trn_number VARCHAR(50) NULL",
    "ALTER TABLE clients ADD COLUMN tax_regime VARCHAR(50) NULL",

    # workshop items & brand deduction
    "ALTER TABLE stock_items ADD COLUMN brand VARCHAR(100) NULL",
    "ALTER TABLE workshop_estimate_items ADD COLUMN brand VARCHAR(100) NULL",
    "ALTER TABLE workshop_part_issues ADD COLUMN brand VARCHAR(100) NULL",
    "ALTER TABLE workshop_part_issues ADD COLUMN item_type VARCHAR(30) DEFAULT 'Part'",
]


def _ensure_customer_schema(engine):
    """Run idempotent ALTER TABLE statements on a customer database engine."""
    with engine.connect() as conn:
        for stmt in CUSTOMER_SCHEMA_PATCHES:
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass


def _get_or_create(company_id: str):
    """
    Build (or return cached) scoped_session factory for a company.
    Creates the MySQL database and all customer tables on first call.
    """
    if company_id not in _engine_cache:
        # 1. Make sure the database exists on this VPS
        _create_database_if_missing(company_id)

        # 2. Build engine pointed at that database
        uri    = _build_uri(company_id)
        engine = create_engine(
            uri, 
            pool_pre_ping=True,   
            pool_recycle=3600,    
            pool_size=10,
            max_overflow=20,
        )

        # 3. Create all customer tables if they don't exist yet
        customer_db.metadata.create_all(engine)
        _ensure_customer_schema(engine)

        factory = scoped_session(sessionmaker(bind=engine))
        _engine_cache[company_id]  = engine
        _session_cache[company_id] = factory

    return _session_cache[company_id]


def get_customer_session(company_id: str, db_session=None):
    """
    Return a SQLAlchemy session bound to this company's MySQL database.

    db_session is accepted for API compatibility but is no longer needed
    (the URI is always derived from the company_id + env vars).
    """
    factory = _get_or_create(company_id)
    return factory()


def close_customer_session(company_id: str):
    """Remove the scoped session for this company (call on teardown / after restore)."""
    if company_id in _session_cache:
        _session_cache[company_id].remove()


def get_customer_session_with_retry(company_id: str, max_retries: int = 1):
    """
    Same as get_customer_session(), but self-heals a session that was left
    broken by a previous request that never got torn down cleanly — e.g.
    the gunicorn worker was hard-killed mid-request by --timeout or an OOM
    kill, so teardown_request never ran and never rolled it back.

    This does one cheap `SELECT 1` on the session to surface a broken
    transaction or dead connection here, where it can be healed, instead of
    letting the caller's real query fail deeper in a route.

    - PendingRollbackError (transaction left open and marked invalid):
      roll back and retry. Nothing has been committed yet at this point,
      so discarding the transaction is always safe.
    - OperationalError with a dead-connection code (2006/2013, "MySQL
      server has gone away"): dispose this company's cached engine and
      session so the next attempt rebuilds them from scratch, then retry.
    - Anything else is a real error and is re-raised as-is; this function
      only recovers from the two specific "session got poisoned by
      something outside this request" failure modes.
    """
    last_error = None
    for attempt in range(max_retries + 1):
        session = get_customer_session(company_id)
        try:
            session.execute(text("SELECT 1"))
            return session
        except PendingRollbackError as e:
            last_error = e
            try:
                session.rollback()
            except Exception:
                pass
        except OperationalError as e:
            last_error = e
            if "2006" in str(e) or "2013" in str(e) or "gone away" in str(e):
                if company_id in _session_cache:
                    _session_cache[company_id].remove()
                    del _session_cache[company_id]
                if company_id in _engine_cache:
                    _engine_cache[company_id].dispose()
                    del _engine_cache[company_id]
            else:
                raise
    # Exhausted retries — surface the last real error rather than a fresh
    # session that we already know is still broken.
    raise last_error


def init_customer_db_for_company(company, platform_session=None):
    """
    Called immediately after a new company registers.
    Creates the dedicated MySQL database and all customer tables.
    The `company` object and `platform_session` arguments are accepted for
    backwards compatibility but only company.company_id is used.
    """
    company_id = company.company_id if hasattr(company, "company_id") else company
    factory    = _get_or_create(company_id)
    return factory


def dispose_all():
    """Dispose all cached engines (call on app shutdown)."""
    for engine in _engine_cache.values():
        engine.dispose()
    _engine_cache.clear()
    _session_cache.clear()


# Add these functions to db_router.py

def get_platform_engine():
    """Get the platform database engine (for running migrations on platform DB)"""
    from sqlalchemy import create_engine
    import os
    
    platform_db_uri = os.environ.get(
        "PLATFORM_DB_URI",
        "mysql+pymysql://root@localhost/qiyadah_erp"
    )
    return create_engine(platform_db_uri)


def get_target_companies(target_type="all", target_db="", where_clause=""):
    """
    Get list of target companies based on filters.
    Returns list of company objects.
    """
    from platform_models import Company, db
    
    query = Company.query.filter_by(is_active=True)
    
    # Apply custom WHERE clause if provided
    if where_clause:
        try:
            query = query.filter(text(where_clause))
        except Exception as e:
            print(f"Warning: Could not apply custom WHERE clause: {e}")
    
    companies = query.all()
    
    # Filter by target_db if specified
    if target_db == "customer":
        # Return all customer companies (all active companies)
        return companies
    elif target_db == "platform":
        # Return empty list - platform DB is handled separately
        return []
    else:
        # Return all companies for customer DB migrations
        return companies


def filter_companies_by_table(companies, table_name):
    """
    Filter companies based on whether they have the specified table.
    This is useful for targeted migrations.
    """
    from sqlalchemy import inspect
    
    filtered = []
    for company in companies:
        try:
            engine = _engine_cache.get(company.company_id)
            if engine is None:
                _get_or_create(company.company_id)
                engine = _engine_cache[company.company_id]
            
            inspector = inspect(engine)
            if table_name in inspector.get_table_names():
                filtered.append(company)
        except Exception:
            # If we can't check, include it anyway
            filtered.append(company)
    
    return filtered

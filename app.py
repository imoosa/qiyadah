from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().with_name('.env'))
# BI DASHBOARD UPDATE: NET PROFIT = TOTAL BILLED - PURCHASES - EXPENSES; EXPENSE KPI INCLUDED
from flask import Flask, render_template, render_template_string, request, redirect, url_for, session, flash, jsonify, send_file, send_from_directory
from flask import abort
from datetime import date, datetime, timedelta
import random
import hashlib
import secrets
from functools import wraps
import os
import json
import re
import math
import pandas as pd
from werkzeug.utils import secure_filename
import io
import base64
from flask import url_for
import base64
from difflib import SequenceMatcher
import hmac
import razorpay
from sqlalchemy import text, func, and_, or_
from platform_models import db, SubscriptionPlan, RegisteredUser, Company, PaymentTransaction
import time
import threading
from customer_models import (
    CompanyUser, Client, StockItem,
    Invoice, InvoiceItem,
    Estimate, EstimateItem,
    PurchaseInvoice, PurchaseInvoiceItem, StockPurchaseHistory,
    CashTransaction, Loan, LoanRepayment,
    BankAccount, BankTransaction, Expense, Supplier, SupplierBrand,
    PriceList, RateLookup, Cheque, CompanyRolePermission, PurchasePayment, WhatsAppLog, StatementClosing,
    DeletedInvoiceLog, CustomerInvoice, CustomerInvoiceItem, ChartOfAccount, JournalEntry, JournalEntryLine,
    BankReconciliation, BankReconciliationItem, FixedAsset )
from db_router import get_customer_session, get_customer_session_with_retry, init_customer_db_for_company
from backup_utils import BACKUP_DESTINATIONS
import permissions as perms_module
from permissions import (
    get_field_permissions,
    can_edit_field,
    can_view_field,
    INVOICE_FIELDS,
    DEFAULT_FIELD_PERMISSIONS,
    HARD_LOCKED_EDIT,
)
from erp_routes import register_erp_routes
from flask_mail import Mail, Message
from utils.ai_assistant import QiyadahAIAssistant
from utils.intent_router import *
from utils.self_learning_ai import SelfLearningAssetAI
from sqlalchemy.exc import OperationalError
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum
import calendar
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("FLASK_SECRET_KEY not set in environment")

# --- timezone helpers (server runs in UTC; business timezone is IST) ---
from datetime import timezone as _timezone

IST = _timezone(timedelta(hours=5, minutes=30))

class PeriodType(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"

def to_ist(dt):
    """Convert a datetime to IST for display. Assumes naive datetimes are UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_timezone.utc)
    return dt.astimezone(IST)

def today_ist():
    """Current calendar date in IST. Use this instead of date.today() everywhere."""
    return datetime.now(_timezone.utc).astimezone(IST).date()

app.jinja_env.filters['ist'] = to_ist
# --- end timezone helpers ---

app.config['MAIL_SERVER'] = 'smtp.hostinger.com'
app.config['MAIL_PORT'] = 465
app.config['MAIL_USE_TLS'] = False
app.config['MAIL_USE_SSL'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
app.config['MAIL_DEFAULT_SENDER'] = 'support@magnustic.com'
app.config['SESSION_COOKIE_MAX_SIZE'] = 4000


mail = Mail(app)
_ai_assistant = QiyadahAIAssistant(model_name="llama3.2")


_submission_lock = threading.Lock()
_SUBMISSION_TTL_SECONDS = 120 

def send_otp_email(to_email, otp_code):
    # Get company logo path (for the current company)
    company_id = get_current_company()
    company = Company.query.filter_by(company_id=company_id).first()
    
    # Try to get logo from company settings first
    logo_base64 = None
    if company and company.logo_filename:
        logo_path = os.path.join('static', 'company_logos', company.logo_filename)
        if os.path.exists(logo_path):
            with open(logo_path, 'rb') as f:
                logo_base64 = base64.b64encode(f.read()).decode('utf-8')
    
    # Fallback to default Magnustic logo
    if not logo_base64:
        default_logo_path = os.path.join('static', 'logo.png')
        if os.path.exists(default_logo_path):
            with open(default_logo_path, 'rb') as f:
                logo_base64 = base64.b64encode(f.read()).decode('utf-8')
    
    # If no logo found, use a text placeholder
    logo_html = f'''
    <div style="background: #1a237e; color: white; padding: 12px 24px; border-radius: 6px; display: inline-block; font-weight: bold; font-size: 20px; letter-spacing: 1px;">
        MAGNUSTIC ERP
    </div>
    ''' if not logo_base64 else f'''
    <img src="data:image/png;base64,{logo_base64}" alt="Magnustic Logo" style="max-width: 180px; height: auto;">
    '''
    
    # Get company name for personalization
    company_name = company.company_name if company else "Magnustic ERP"
    
    msg = Message(
        subject=f"Verify your email — {company_name}",
        recipients=[to_email],
        sender=app.config['MAIL_DEFAULT_SENDER']
    )
    
    msg.html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: Arial, Helvetica, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f9fafb; color: #333;">
        <table width="100%" cellpadding="0" cellspacing="0" style="background: #ffffff; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); padding: 40px 30px;">
            <tr>
                <td style="text-align: center; padding-bottom: 20px;">
                    {logo_html}
                </td>
            </tr>
            <tr>
                <td style="padding: 10px 0;">
                    <h2 style="color: #1a237e; font-size: 22px; margin: 0 0 8px 0;">Verification Code</h2>
                    <p style="color: #666; font-size: 14px; margin: 0;">Use this code to complete your login</p>
                </td>
            </tr>
            <tr>
                <td style="padding: 20px 0;">
                    <p style="font-size: 15px; color: #444; margin: 0 0 10px 0;">Dear Valued User,</p>
                    <p style="font-size: 15px; color: #444; margin: 0 0 20px 0;">Your verification code for {company_name} is:</p>
                    
                    <div style="background: #f5f7fa; padding: 18px; text-align: center; border-radius: 8px; border: 2px dashed #1a237e; margin: 10px 0 20px 0;">
                        <span style="font-size: 32px; font-weight: 700; color: #1a237e; letter-spacing: 6px; font-family: 'Courier New', monospace;">
                            {otp_code}
                        </span>
                    </div>
                    
                    <p style="font-size: 14px; color: #666; margin: 0 0 5px 0;">
                        <strong>⏱️ This code expires in 10 minutes</strong>
                    </p>
                    <p style="font-size: 13px; color: #888; margin: 0 0 20px 0;">
                        For security, please do not share this code with anyone.
                    </p>
                </td>
            </tr>
            <tr>
                <td style="padding: 15px 0; border-top: 1px solid #e5e7eb;">
                    <p style="font-size: 14px; color: #555; margin: 0 0 4px 0;">
                        Thank you for choosing <strong style="color: #1a237e;">{company_name}</strong>.
                    </p>
                    <p style="font-size: 14px; color: #555; margin: 0 0 4px 0;">
                        We appreciate your trust in us.
                    </p>
                </td>
            </tr>
            <tr>
                <td style="padding: 10px 0 0 0; border-top: 1px solid #e5e7eb;">
                    <p style="font-size: 14px; color: #555; margin: 10px 0 0 0;">
                        Best regards,<br>
                        <strong style="color: #1a237e; font-size: 15px;">Team Magnustic</strong>
                    </p>
                </td>
            </tr>
            <tr>
                <td style="padding: 20px 0 0 0; text-align: center; border-top: 1px solid #e5e7eb;">
                    <p style="font-size: 12px; color: #999; margin: 0;">
                        © 2026 {company_name}. All rights reserved.
                    </p>
                    <p style="font-size: 12px; color: #999; margin: 4px 0 0 0;">
                        <a href="https://www.magnustic.com" style="color: #1a237e; text-decoration: none;">www.magnustic.com</a>
                    </p>
                    <p style="font-size: 11px; color: #bbb; margin: 8px 0 0 0;">
                        This is an automated message, please do not reply to this email.
                    </p>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    
    # Plain text fallback
    msg.body = f"""
    {company_name} - Verification Code
    
    Dear Valued User,
    
    Your verification code is: {otp_code}
    This code expires in 10 minutes.
    
    For security, please do not share this code with anyone.
    
    Thank you for choosing {company_name}.
    
    Best regards,
    Team Magnustic
    www.magnustic.com
    """
    
    mail.send(msg)
   

def _generate_and_send_otp(email):
    try:
        otp = f"{secrets.randbelow(1000000):06d}"
        session["otp_email"]   = email
        session["otp_hash"]    = hashlib.sha256(otp.encode()).hexdigest()
        session["otp_expires"] = (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        
        # Try to send email with error handling
        try:
            send_otp_email(email, otp)
            print(f"[OK] OTP sent to {email}: {otp}")
        except Exception as e:
            print(f"[ERROR] Failed to send OTP email: {e}")
            # For testing, we can still allow login with a fallback
            # Store the OTP in session anyway so user can see it in logs
            flash(f"Email sending failed. For testing, your OTP is: {otp}", "warning")
    except Exception as e:
        print(f"[ERROR] Error in _generate_and_send_otp: {e}")
        flash("Error sending verification code. Please try again.", "error")

def _finish_owner_login(reg_user):
    # Each successful login starts with an explicit company choice.
    session.clear()
    # Check if lifetime maintenance fee is due (trigger reminder once a day on owner login)
    try:
        is_lifetime = (
            getattr(reg_user, "plan_duration", "") == "lifetime" or
            getattr(reg_user, "subscription_plan", "") == "lifetime" or
            (reg_user.companies and any(getattr(c, "plan_duration", "") == "lifetime" or c.subscription_plan == "lifetime" for c in reg_user.companies))
        )
        if is_lifetime:
            today = today_ist()
            due_date = getattr(reg_user, "maintenance_due_date", None)
            if not due_date or due_date <= today:
                last_prompt = getattr(reg_user, "last_maintenance_prompt_date", None)
                if last_prompt != today:
                    reg_user.last_maintenance_prompt_date = today
                    db.session.commit()
                    session["lifetime_maintenance_due"] = True
                    session["maintenance_amount"] = 2500
                    flash("🔔 Lifetime License Reminder: Your annual maintenance fee of ₹2,500 is due. Click below to pay and keep cloud backups & WhatsApp services active.", "warning")
    except Exception as e:
        print(f"⚠ Error in lifetime maintenance check: {e}")

    companies = get_owner_companies(reg_user.email)
    if len(companies) == 0:
        session["user"] = {"user_id": reg_user.user_id, "email": reg_user.email,
                            "full_name": reg_user.full_name, "role": reg_user.role,
                            "company_id": None}
        return redirect(url_for("onboard_company"))
    else:
        session["pending_login_email"] = reg_user.email
        session["pending_login_type"] = "owner"
        return redirect(url_for("select_company"))

@app.template_filter('from_json')
def from_json_filter(value):
    """Parse JSON string to Python object in templates"""
    if not value:
        return {}
    try:
        return json.loads(value)
    except (ValueError, TypeError, json.JSONDecodeError):
        return {}

# Also add a filter for JSON parsing with default
@app.template_filter('json_loads')
def json_loads_filter(value, default=None):
    """Parse JSON string to Python object in templates"""
    if not value:
        return default or {}
    try:
        return json.loads(value)
    except (ValueError, TypeError, json.JSONDecodeError):
        return default or {}

import currency_service
from tax_service import tax_profile, apply_company_tax, billing_rate, split_tax

def company_currency_symbol():
    company = get_company_by_id(get_current_company())
    return currency_service.get_currency_info(tax_profile(company)['currency'])['symbol']


@app.template_filter('format_currency')
def format_currency_filter(value, currency_code=None, show_symbol=True):
    """Format an amount according to currency rules (symbol and decimals)."""
    company = get_company_by_id(get_current_company()) if not currency_code else None
    code = currency_code or tax_profile(company)["currency"]
    return currency_service.format_currency_amount(value, code, show_symbol=show_symbol)


# ── Database Configuration ────────────────────────────────────────────────────
PLATFORM_DB_URI = os.environ.get("PLATFORM_DB_URI", "mysql+pymysql://root@localhost/qiyadah_erp")
from platform_bootstrap import ensure_platform_database
ensure_platform_database(PLATFORM_DB_URI)
app.config["SQLALCHEMY_DATABASE_URI"] = PLATFORM_DB_URI
app.config["SQLALCHEMY_BINDS"] = {}           
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,  
    "pool_recycle": 3600,   
    "pool_size": 10,
    "max_overflow": 20,
}
db.init_app(app)

@app.before_request
def _fk_on():
    pass  # MySQL enforces FK by default; no PRAGMA needed

with app.app_context():
    db.create_all()

    # ── Patch existing companies table for new columns ─────────────────────
    # db.create_all() only creates tables that don't exist yet — it never
    # alters a `companies` table that's already there, so a new column added
    # to the Company model (like credit_limit_action) silently does nothing
    # on every database except a brand new one. This app has no migration
    # framework for the platform DB (schema_migrations further down is
    # per-tenant customer DBs only), so patch it in here directly, checking
    # first so this is a no-op once the column actually exists.
    try:
        from sqlalchemy import inspect as _sa_inspect
        _existing_cols = {c["name"] for c in _sa_inspect(db.engine).get_columns("companies")}
        if "credit_limit_action" not in _existing_cols:
            db.session.execute(text(
                "ALTER TABLE companies ADD COLUMN credit_limit_action "
                "VARCHAR(10) NOT NULL DEFAULT 'warn'"
            ))
            db.session.commit()
            print("✅ Added missing companies.credit_limit_action column")
        
        # Multi-currency & regional tax columns
        for col_name, col_type in [
            ("branch_name", "VARCHAR(100) NULL"),
            ("currency", "VARCHAR(10) NOT NULL DEFAULT 'INR'"),
            ("currency_symbol", "VARCHAR(10) NOT NULL DEFAULT '₹'"),
            ("country", "VARCHAR(100) NOT NULL DEFAULT 'India'"),
            ("tax_regime", "VARCHAR(50) NOT NULL DEFAULT 'GST'"),
            ("tax_id_label", "VARCHAR(50) NOT NULL DEFAULT 'GSTIN'"),
        ]:
            if col_name not in _existing_cols:
                try:
                    db.session.execute(text(f"ALTER TABLE companies ADD COLUMN {col_name} {col_type}"))
                    db.session.commit()
                    print(f"✅ Added missing companies.{col_name} column")
                except Exception as _ce:
                    db.session.rollback()
                    print(f"⚠ Could not add companies.{col_name}: {_ce}")
    except Exception as e:
        db.session.rollback()
        print(f"⚠  Could not verify/add companies multi-currency columns: {e}")


# ── Create tables and seed on first startup ────────────────────────────────────
with app.app_context():
    # Only create platform tables - customer DBs are created per-company
    db.create_all()

UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads', 'purchase_invoices')
ALLOWED_EXTENSIONS = {
    'png',
    'jpg',
    'jpeg',
    'pdf',
    'tiff',
    'bmp',
    'xlsx',
    'xls'
}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── Company logo uploads (served from /static so no extra route is needed) ──
LOGO_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'company_logos')
ALLOWED_LOGO_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
os.makedirs(LOGO_UPLOAD_FOLDER, exist_ok=True)

ID_DOCS_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'invoice_docs')
ALLOWED_ID_DOC_EXTENSIONS = {'png', 'jpg', 'jpeg'}
os.makedirs(ID_DOCS_UPLOAD_FOLDER, exist_ok=True)
CLIENT_DOCS_UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'client_docs')
os.makedirs(CLIENT_DOCS_UPLOAD_FOLDER, exist_ok=True)

def allowed_logo_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_LOGO_EXTENSIONS

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def allowed_id_doc_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_ID_DOC_EXTENSIONS
# ── Helper / Auth ─────────────────────────────────────────────────────────────
from auth_utils import hash_password, verify_password


# Add this after the existing template filters in app.py

def wordize_number(n):
    """Convert a number to words (Indian English)."""
    if n is None:
        return "Zero"
    n = int(abs(n))
    if n == 0:
        return "Zero"
    
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
            "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
            "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    
    def words_under_hundred(n):
        if n < 20:
            return ones[n]
        return tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")
    
    def words_under_thousand(n):
        if n < 100:
            return words_under_hundred(n)
        return ones[n // 100] + " Hundred" + (" " + words_under_hundred(n % 100) if n % 100 else "")
    
    def words_under_lakh(n):
        if n < 1000:
            return words_under_thousand(n)
        return words_under_hundred(n // 1000) + " Thousand" + (" " + words_under_thousand(n % 1000) if n % 1000 else "")
    
    def words_under_crore(n):
        if n < 100000:
            return words_under_lakh(n)
        return words_under_hundred(n // 100000) + " Lakh" + (" " + words_under_lakh(n % 100000) if n % 100000 else "")
    
    def words_under_arab(n):
        if n < 10000000:
            return words_under_crore(n)
        return words_under_hundred(n // 10000000) + " Crore" + (" " + words_under_crore(n % 10000000) if n % 10000000 else "")
    
    return words_under_arab(n)

@app.template_filter('wordize')
def wordize_filter(value):
    """Jinja2 filter to convert numbers to words."""
    return wordize_number(value)

def generate_next_user_id():
    """Next USRxxx id, derived from the highest existing numeric suffix —
    NOT from RegisteredUser.query.count(). Count-based generation breaks the
    moment any user is deleted: count() drops, but the highest issued id
    doesn't, so count()+1 collides with an id that still exists."""
    max_num = 0
    for (uid,) in RegisteredUser.query.with_entities(RegisteredUser.user_id).all():
        if uid and uid.startswith("USR"):
            try:
                max_num = max(max_num, int(uid[3:]))
            except ValueError:
                continue
    return f"USR{max_num + 1:03d}"



# ADD (whole function, new)
def save_client_id_doc(file_storage, client_id, doc_label, old_filename=None):
    """Same contract as save_shipper_id_doc(), but for the permanent copy that
    lives on a credit client's own record (static/client_docs/) instead of a
    single booking's (static/invoice_docs/). client_id here is Client.client_id
    (e.g. 'ACM001'), not the numeric PK, so filenames stay readable."""
    if not file_storage or not file_storage.filename:
        return old_filename
    if not allowed_id_doc_file(file_storage.filename):
        flash(f"{doc_label.upper()} file must be a PNG or JPG image.")
        return old_filename
    ext = file_storage.filename.rsplit('.', 1)[1].lower()
    new_filename = secure_filename(f"{client_id}_{doc_label}.{ext}")
    if old_filename and old_filename != new_filename:
        old_path = os.path.join(CLIENT_DOCS_UPLOAD_FOLDER, old_filename)
        if os.path.exists(old_path):
            os.remove(old_path)
    file_storage.save(os.path.join(CLIENT_DOCS_UPLOAD_FOLDER, new_filename))
    return new_filename


def _save_client_id_docs(cdb, client_row, form_files):
    """Handles all 4 client ID-doc uploads for a Client row and commits.
    Shared by client_new() and client_edit() so the save logic can't drift."""
    client_row.aadhar_front_file = save_client_id_doc(
        form_files.get("aadhar_front_file"), client_row.client_id, "aadhar_front", client_row.aadhar_front_file)
    client_row.aadhar_back_file = save_client_id_doc(
        form_files.get("aadhar_back_file"), client_row.client_id, "aadhar_back", client_row.aadhar_back_file)
    client_row.pan_front_file = save_client_id_doc(
        form_files.get("pan_front_file"), client_row.client_id, "pan_front", client_row.pan_front_file)
    client_row.pan_back_file = save_client_id_doc(
        form_files.get("pan_back_file"), client_row.client_id, "pan_back", client_row.pan_back_file)
    cdb.commit()

def _next_numbered_id(session, column, prefix, pad=3, extra_filters=None):
    """
    Safe replacement for count()-based ID generation (e.g. `f"CUST-{count+1:03d}"`).
    That pattern breaks two ways: (1) after any row for this prefix is deleted,
    count() drops but the highest issued number doesn't, so count()+1 collides
    with an id that still exists; (2) under two near-simultaneous requests
    (double-submit, two tabs), both read the same count before either commits,
    so both compute the same next id and the second INSERT fails with a
    duplicate-key IntegrityError.

    This finds the highest existing numeric suffix among ids starting with
    `prefix` and returns prefix + (max + 1). It fixes the delete problem
    outright. It reduces but does not eliminate the race — two truly
    simultaneous requests can still read the same max before either commits.
    For routes with meaningful concurrent-write risk, pair this with a
    retry-on-IntegrityError loop at the call site (catch, session.rollback(),
    regenerate the id, retry once or twice).
    """
    q = session.query(column).filter(column.like(f"{prefix}%"))
    if extra_filters:
        q = q.filter(*extra_filters)
    max_num = 0
    for (val,) in q.all():
        if not val:
            continue
        tail = val[len(prefix):]
        try:
            max_num = max(max_num, int(tail))
        except ValueError:
            continue
    return f"{prefix}{max_num + 1:0{pad}d}"


def _company_name_prefix(company_name, chars=3, from_end=False):
    """
    Derive a 3-letter id prefix from the company name, letters only
    (spaces/punctuation stripped), lowercased.
    from_end=False -> first N letters  (used for supplier ids)
    from_end=True  -> last N letters   (used for client ids)
    e.g. "Demo"      -> "dem" (supplier) / "emo" (client)
         "Magnustic" -> "mag" (supplier) / "tic" (client)
    Falls back to "co" + letters if the name has fewer than `chars` letters.
    """
    letters = "".join(ch for ch in (company_name or "") if ch.isalpha())
    if not letters:
        letters = "co"
    if len(letters) < chars:
        letters = letters.ljust(chars, "x")
    seg = letters[-chars:] if from_end else letters[:chars]
    return seg.lower()


def get_current_user():
    try:
        from flask import has_request_context, session
        if has_request_context():
            return session.get("user", {})
    except Exception:
        pass
    return {}
 
 
def resolve_user_names(cdb, raw_values):
    """
    Map a set of created_by/updated_by strings (normally emails, but a
    couple of old code paths fell back to storing full_name instead) to
    {raw_value: {"name": ..., "email": ...}}.
 
    Lookup order: CompanyUser (employees, this company's own db) first,
    then RegisteredUser (owners, main platform db). Anything that matches
    neither is shown as-is with no email line (covers deleted users, or
    rows where a name was stored directly instead of an email).
    """
    raw_values = {v for v in raw_values if v}
    if not raw_values:
        return {}
 
    name_map = {}
    remaining = set(raw_values)
 
    emp_rows = cdb.query(CompanyUser.email, CompanyUser.full_name).filter(
        CompanyUser.email.in_(remaining)
    ).all()
    for email, full_name in emp_rows:
        name_map[email] = {"name": full_name, "email": email}
        remaining.discard(email)
 
    if remaining:
        owner_rows = RegisteredUser.query.with_entities(
            RegisteredUser.email, RegisteredUser.full_name
        ).filter(RegisteredUser.email.in_(remaining)).all()
        for email, full_name in owner_rows:
            name_map[email] = {"name": full_name, "email": email}
            remaining.discard(email)
 
    for v in remaining:
        name_map[v] = {"name": v, "email": None}
 
    return name_map


def log_audit_event(cdb, company_id, entity_type, entity_id, action, details=""):
    """Safely log an audit event for entity creations, updates, or conversions."""
    try:
        user_info = session.get("user", {}) if "session" in globals() and session else {}
        username = user_info.get("username") or user_info.get("email") or "system"
        app.logger.info(f"[AUDIT] [{company_id}] {username} {action} {entity_type} #{entity_id}: {details}")
    except Exception:
        pass


@app.template_filter('nl2br')
def nl2br_filter(s):
    """Convert newlines in text to HTML <br> tags safely."""
    if not s:
        return ""
    from markupsafe import Markup, escape
    return Markup("<br>".join(escape(str(s)).splitlines()))


@app.context_processor
def inject_user():
    return {
        "user": session.get("user", {}),
    }

@app.context_processor
def inject_today():
    """Inject today's date for the subscription banner and other uses"""
    # Named distinctly from the many routes that pass their own
    # today=str(...)/isoformat() kwarg into render_template() for
    # date-input defaults. Those route-level kwargs are for form
    # fields; this one is exclusively for the subscription banner
    # in base.html and must never be shadowed by a string.
    return {"subscription_today": today_ist()}

@app.context_processor
def inject_company_settings():
    company_id = get_current_company()
    is_gst = True  # default safe
    co = None
    show_expiry_popup = False
    expiry_info = {}
    today = today_ist()

    if company_id:
        try:
            co = Company.query.filter_by(company_id=company_id).first()
        except Exception:
            co = None
        if co and hasattr(co, 'is_gst_registered'):
            is_gst = bool(co.is_gst_registered)

        # ── Plan Expiry Daily Pop Check (1 month before expiry date or expired) ──
        if co and co.subscription_end and not (co.owner and co.owner.payment_status == 'trial'):
            try:
                days_left = (co.subscription_end - today).days
                if days_left <= 30:
                    # Trigger once per day on login/session
                    if session.get("last_expiry_popup_date") != str(today):
                        session["last_expiry_popup_date"] = str(today)
                        session["show_expiry_popup"] = True

                    show_expiry_popup = bool(session.get("show_expiry_popup", False))
                    expiry_info = {
                        "days_left": days_left,
                        "expiry_date": co.subscription_end.strftime("%d %b %Y"),
                        "company_name": co.company_name,
                        "company_id": co.company_id,
                        "plan_id": co.subscription_plan or "starter",
                        "plan_name": (co.subscription_plan or "Starter").title(),
                        "is_expired": (days_left < 0),
                        "is_trial": (co.subscription_plan == "trial")
                    }
            except Exception as e:
                print(f"⚠ Expiry notice error: {e}")

    logo_url = None
    if co and getattr(co, 'logo_filename', None):
        logo_url = url_for('static', filename=f'company_logos/{co.logo_filename}')

    base_currency = tax_profile(co)['currency']
    currency_symbol = currency_service.get_currency_info(base_currency).get('symbol', base_currency)
    tax_regime = tax_profile(co)['regime']
    tax_id_label = getattr(co, 'tax_id_label', 'GSTIN') or 'GSTIN'

    return {
        'is_gst_registered': is_gst,
        'company': co,
        'company_logo_url': logo_url,
        'show_expiry_popup': show_expiry_popup,
        'expiry_info': expiry_info,
        'base_currency': base_currency,
        'currency_symbol': currency_symbol,
        'number_locale': 'en-IN' if base_currency == 'INR' else 'en-US',
        'currency_info': currency_service.get_currency_info,
        'tax_regime': tax_regime,
        'tax_id_label': tax_profile(co)['id_label'],
        'billing_tax': tax_profile(co),
        'tax_profile': tax_profile,
        'supported_currencies': currency_service.get_all_currencies_list(),
        'fmt_curr': lambda amt, curr=None: currency_service.format_currency_amount(amt, curr or base_currency),
        'curr_sym': lambda curr=None: currency_service.get_currency_info(curr or base_currency).get('symbol', ''),
    }

@app.route("/api/dismiss-expiry-popup", methods=["POST"])
def dismiss_expiry_popup():
    session.pop("show_expiry_popup", None)
    return jsonify({"status": "ok"})


# ── Currency & Exchange Rate Endpoints ────────────────────────────────────────

@app.route("/api/currency/list", methods=["GET"])
def api_currency_list():
    """Return all supported currencies with symbols, names, and flags."""
    return jsonify({
        "success": True,
        "currencies": currency_service.get_all_currencies_list()
    })


@app.route("/api/currency/exchange-rate", methods=["GET"])
def api_currency_exchange_rate():
    """
    Get live exchange rate between two currencies.
    Query params: from=USD&to=INR (defaults: from=USD, to=Company Base Currency)
    """
    company_id = get_current_company()
    co = Company.query.filter_by(company_id=company_id).first() if company_id else None
    base_curr = (getattr(co, "currency", None) or "INR").upper()

    from_curr = request.args.get("from", "USD").upper().strip()
    to_curr = request.args.get("to", base_curr).upper().strip()

    rate = currency_service.get_exchange_rate(from_curr, to_curr)
    return jsonify({
        "success": True,
        "from": from_curr,
        "to": to_curr,
        "rate": rate,
        "timestamp": time.time()
    })

def get_current_company():
    return session.get("active_company_id") or session.get("user", {}).get("company_id")

@app.context_processor
def inject_field_permissions():
    """Inject field-level permission helpers for templates"""
    user = get_current_user()
    role = user.get("role", "employee")
    user_id = user.get("user_id")
    company_id = get_current_company()
    
    # Get CDB for permission lookups
    cdb = None
    if company_id:
        try:
            cdb = get_customer_session(company_id)
        except:
            pass
    
    def _can_edit_field(field_group):
        return can_edit_field(role, field_group, user_id, company_id, cdb)
    
    def _can_view_field(field_group):
        return can_view_field(role, field_group, user_id, company_id, cdb)
    
    return {
        "can_edit_field": _can_edit_field,
        "can_view_field": _can_view_field,
        "is_owner": role in ("owner", "super_admin"),
        "field_permissions": get_field_permissions(role, user_id, company_id, cdb)
    }

@app.errorhandler(OperationalError)
def handle_db_operational_error(e):
    """Handle stale database connections by retrying once"""
    # Check if it's a connection-related error
    if "2006" in str(e) or "2013" in str(e) or "MySQL server has gone away" in str(e):
        # Clear any problematic sessions
        from db_router import _engine_cache, _session_cache
        for company_id in list(_session_cache.keys()):
            try:
                _session_cache[company_id].remove()
            except:
                pass
            # Recreate the engine
            if company_id in _engine_cache:
                _engine_cache[company_id].dispose()
                del _engine_cache[company_id]
        
        flash("Database connection was re-established. Please try again.", "info")
        return redirect(request.url)
    raise e

@app.errorhandler(404)
def handle_not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({"error": "Not found"}), 404
    return render_template("errors/404.html"), 404

@app.errorhandler(403)
def handle_forbidden(e):
    if request.path.startswith('/api/'):
        return jsonify({"error": "Forbidden"}), 403
    return render_template("errors/403.html"), 403

@app.errorhandler(500)
def handle_server_error(e):
    if request.path.startswith('/api/'):
        return jsonify({"error": "Internal server error"}), 500
    return render_template("errors/500.html"), 500

@app.before_request
def _clear_stale_customer_session():
    """
    Defense against the one case teardown_request can't cover: if the
    gunicorn worker handling a previous request was hard-killed mid-request
    (a --timeout hit on a slow query, or an OOM kill), teardown_request
    never runs, and that company's cached session is left mid-transaction
    for whatever request happens to land on this worker next.
    """
    company_id = get_current_company()
    if not company_id:
        return
    
    try:
        from db_router import _session_cache
        factory = _session_cache.get(company_id)
        if factory is None:
            return
        factory().rollback()
    except Exception:
        pass

@app.teardown_request
def _rollback_customer_session_on_error(exc):
    """
    db_router caches one SQLAlchemy session per company_id and reuses it
    across requests. If any commit on that session fails — an IntegrityError,
    a stale overnight connection, a bad form value, anything — and nothing
    calls rollback() on it, the session is left mid-transaction.

    teardown_request runs after every request — success or failure — and
    unconditionally rolls back the current company's SESSION (not creating
    a new one, but using the cached one). rollback() on a session with no
    open transaction is a harmless no-op.
    """
    company_id = get_current_company()
    if not company_id:
        return
    
    try:
        from db_router import _session_cache
        factory = _session_cache.get(company_id)
        if factory is None:
            return  # nothing cached for this company — nothing to roll back
        factory().rollback()
    except Exception:
        # Don't let cleanup itself take down the error response.
        pass

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            # For API/AJAX requests, return JSON 401 instead of HTML redirect
            if (request.path.startswith('/api/') or
                    request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
                    request.accept_mimetypes.best == 'application/json'):
                return jsonify({'success': False, 'error': 'Session expired. Please refresh the page and login again.', 'redirect': '/login'}), 401
            flash("Please login to continue")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    decorated._requires_login = True
    return decorated



def owner_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if user.get("role") not in ["owner", "super_admin"]:
            flash("Only company owner can access this page")
            return safe_redirect_after_denial()
        return f(*args, **kwargs)
    return decorated

def super_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if user.get("role") != "super_admin":
            flash("Super admin access required")
            return safe_redirect_after_denial()
        return f(*args, **kwargs)
    return decorated


# ── Re-authentication gate for destructive (delete) actions ────────────────
def _current_session_password_hash():
    """Password hash for whoever is logged into THIS session — owners/
    super-admins live in RegisteredUser (platform db), employees live in
    CompanyUser (per-company db). Returns None if it can't be resolved,
    which verify_admin_password() below treats as 'deny'."""
    user = get_current_user()
    user_id = user.get("user_id")
    if not user_id:
        return None
    if user.get("role") in ("owner", "super_admin"):
        reg_user = RegisteredUser.query.filter_by(user_id=user_id).first()
        return reg_user.password_hash if reg_user else None
    company_id = get_current_company()
    if not company_id:
        return None
    try:
        cdb = get_customer_session(company_id)
        emp = cdb.query(CompanyUser).filter_by(user_id=user_id).first()
        return emp.password_hash if emp else None
    except Exception:
        return None

def verify_admin_password(password):
    """Re-check the submitted password against the logged-in user's OWN
    password. This is a re-authentication step, not a role check — role
    (@owner_required / @super_admin_required) still decides WHO can reach
    the route at all; this decides whether the correct password was
    re-entered right before something gets deleted."""
    if not password:
        return False
    hashed = _current_session_password_hash()
    if not hashed:
        return False
    return verify_password(password, hashed)

def require_admin_password(f):
    """Blocks a destructive route unless the logged-in user's password was
    re-submitted correctly on THIS request. Deletion never happens on a
    bare GET (an old link click carries no password) — it always bounces
    back with an error instead. Works for both normal form posts (flash +
    redirect) and JSON/DELETE-style API calls (jsonify error)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        password = request.form.get("admin_password")
        if password is None and request.is_json:
            password = (request.get_json(silent=True) or {}).get("admin_password")

        if not verify_admin_password(password):
            wants_json = (
                request.is_json
                or request.method == "DELETE"
                or "application/json" in request.headers.get("Accept", "")
            )
            if wants_json:
                return jsonify({"success": False, "message": "Incorrect password — nothing was deleted."}), 403
            flash("Incorrect password — nothing was deleted.", "error")
            return redirect(request.referrer or url_for("dashboard"))
        return f(*args, **kwargs)
    return decorated


MODULE_LANDING_ENDPOINT = {
    "dashboard":         "dashboard",
    "analytics":         "reports_dashboard",
    "clients":           "client_list",
    "suppliers":         "supplier_list",
    "estimates":         "estimate_list",
    "sales_orders":      "sales_order_list",
    "delivery_challans": "delivery_challan_list",
    "customer_invoices": "customer_invoice_list",
    "purchase_orders":   "purchase_order_list",
    "stock":             "inventory_list",
    
    
    "invoices":          "customer_invoice_list",
    "purchase":          "purchase_invoice_list",
    "creditors":         "creditors_list",
    "debtors":           "debtors_list",
    "expenses":          "expenses",
    "cash":              "cash_in_hand",
    "bank":              "bank_accounts",
    "cheques":           "cheques",
    "loans":             "loan_accounts",
    "receipts_payments": "receipt_new",
    "backup":            "backup",
}


# Preferred "home" module per role — tried before the generic scan below.
ROLE_HOME_MODULE = {
    "employee": "invoices",   # sales lands on their booking invoices, not clients
}


def safe_redirect_after_denial():
    """Where to send someone after an access check fails. NEVER redirects
    back to 'dashboard' blindly — if the person can't see the dashboard
    either, that would just loop forever. Tries the role's preferred home
    module first, then the first module they can view at all, then a
    permission-free 'no access' page."""
    role = get_current_user().get("role")
    home_module = ROLE_HOME_MODULE.get(role)
    if home_module and has_permission(home_module, "view"):
        return redirect(url_for(MODULE_LANDING_ENDPOINT[home_module]))
    for module, endpoint in MODULE_LANDING_ENDPOINT.items():
        if has_permission(module, "view"):
            return redirect(url_for(endpoint))
    return redirect(url_for("no_access"))


@app.route("/no-access")
@login_required
def no_access():
    return render_template("no_access.html")


# ── Module permissions (view/create/edit only — no delete) ───────────────────
def get_effective_permissions(user=None):
    """Full view/create/edit matrix for the current (or given) user.
    Owners and super_admin get None back, which callers should treat as
    'everything allowed' — they never go through the matrix."""
    user = user or get_current_user()
    role = user.get("role")
    if role in ("owner", "super_admin"):
        return None
    company_id = get_current_company()
    if not company_id:
        return perms_module.default_permissions_for(role)
    cdb = get_customer_session(company_id)
    return perms_module.get_effective_permissions(
        role, company_id, user.get("user_id"), cdb,
        CompanyRolePermission, CompanyUser,
    )

def has_permission(module, action="view"):
    user = get_current_user()
    if user.get("role") in ("owner", "super_admin"):
        return True
    perms = get_effective_permissions(user)
    return bool(perms.get(module, {}).get(action, False))


def require_permission(module, action="view", method_actions=None):
    """Gate a route on a (module, action) pair. Pass method_actions={'POST': 'create'}
    etc. when a single route handles both showing a form (view) and submitting it
    (create/edit) so each HTTP method is checked against the right action."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            act = action
            if method_actions and request.method in method_actions:
                act = method_actions[request.method]
            if not has_permission(module, act):
                flash("You don't have permission to access this.")
                return safe_redirect_after_denial()
            return f(*args, **kwargs)
        return decorated
    return decorator


@app.context_processor
def inject_permission_helper():
    return {"can": has_permission}

@app.context_processor
def inject_today_global():
    """Inject today's date in IST for all templates"""
    t = today_ist()
    return {
        'today_ist': today_ist,
        'today_str': t.isoformat(),
        'today_display': t.strftime('%d %b %Y'),
        'today_year': t.year,
        'today_month': t.month,
        'today_day': t.day,
        'timedelta': timedelta,
    }

def _get_awb(invoice):
    """Extract docket_no from invoice.terms JSON. Returns '' if absent."""
    try:
        if invoice.terms:
            meta = json.loads(invoice.terms)
            return meta.get("docket_no", "")
    except Exception:
        pass
    return ""

def _get_shipment_meta(invoice):
    """
    Pull the AWB/consignee/destination/carrier-ref block out of invoice.terms
    JSON in one shot, for statement rows that need all four instead of just
    the AWB. "Consignee" here is meta['receiver_name'] — the actual receiving
    party captured on the booking form — not to be confused with
    meta['shipper_name'], which is the sender and has no place on a debtor
    statement (the debtor is the party being billed/received from, not shipped
    to, but receiver_name is what the statement is meant to surface here).
    Returns a dict of empty strings if terms is missing or unparseable.
    """
    empty = {
        "awb": "", "consignee": "", "destination": "", "carrier_ref": "",
        "carrier": "", "chrg_wt": 0, "act_wt": 0, "vol_wt": 0, "other_charges": 0,
        "per_kg": 0,
    }
    try:
        if invoice and invoice.terms:
            if isinstance(invoice.terms, dict):
                meta = invoice.terms
            else:
                meta = json.loads(invoice.terms)
            packages = meta.get("packages") or []
            chrg_wt = 0.0
            act_wt  = 0.0
            vol_wt  = 0.0
            for p in packages:
                if isinstance(p, dict):
                    try:
                        chrg_wt += float(p.get("chg_weight") or 0)
                    except (ValueError, TypeError):
                        pass
                    try:
                        act_wt += float(p.get("weight") or 0)
                    except (ValueError, TypeError):
                        pass
                    try:
                        vol_wt += float(p.get("vol_weight") or 0)
                    except (ValueError, TypeError):
                        pass
            
            # Prioritize the exact rate per kg locked in at booking generation time
            per_kg = 0.0
            if meta.get("freight_rate_per_kg") is not None and str(meta.get("freight_rate_per_kg")).strip() != "":
                try:
                    per_kg = float(meta.get("freight_rate_per_kg"))
                except (ValueError, TypeError):
                    per_kg = 0.0
            elif meta.get("freight_rate") is not None and str(meta.get("freight_rate")).strip() != "":
                try:
                    per_kg = float(meta.get("freight_rate"))
                except (ValueError, TypeError):
                    per_kg = 0.0
            elif packages and isinstance(packages[0], dict) and packages[0].get("rate") is not None and str(packages[0].get("rate")).strip() != "":
                try:
                    per_kg = float(packages[0].get("rate"))
                except (ValueError, TypeError):
                    per_kg = 0.0
            
            if not per_kg:
                try:
                    freight_amount = float(meta.get("freight", 0) or 0)
                    freight_weight = float(meta.get("freight_billing_weight", 0) or meta.get("freight_weight", 0) or chrg_wt or 0)
                    per_kg = round(freight_amount / freight_weight, 2) if freight_weight > 0 else 0.0
                except (ValueError, TypeError):
                    per_kg = 0.0

            other_charges = 0.0
            try:
                other_charges = float(meta.get("other", 0) or 0)
            except (ValueError, TypeError):
                other_charges = 0.0

            return {
                "awb":           str(meta.get("docket_no", "") or meta.get("awb", "") or meta.get("awb_number", "") or ""),
                "consignee":     str(meta.get("receiver_name", "") or getattr(invoice, "contact_person", "") or ""),
                "destination":   str(meta.get("destination", "") or meta.get("dest", "") or ""),
                "carrier_ref":   str(meta.get("carrier_ref", "") or meta.get("reference_number", "") or meta.get("reference_no", "") or ""),
                "carrier":       str(meta.get("carrier", "") or meta.get("service", "") or ""),
                "chrg_wt":       chrg_wt,
                "act_wt":        act_wt,
                "vol_wt":        vol_wt,
                "other_charges": other_charges,
                "per_kg":        per_kg,
            }
    except Exception:
        pass
    return empty

def _purchase_shipment_summary(items):
    """
    A PurchaseInvoice can carry several line items, each its own AWB/dest/
    carrier-ref (docket_no, destination, carrier_ref, party_name on
    PurchaseInvoiceItem) — unlike a sales Invoice, there's no single
    shipment per row here. Rather than silently picking the first item and
    hiding the rest, this joins the distinct values with ", " so a
    multi-AWB purchase invoice shows all of them; single-AWB invoices (the
    common case) render exactly as if there were one field.
    party_name is used as the consignor stand-in — it's the customer tied
    to that AWB, not a formal "consignor" field, since no such column
    exists on the purchase side.
    """
    def _joined(attr):
        vals = []
        for it in items:
            v = (getattr(it, attr, None) or "").strip()
            if v and v not in vals:
                vals.append(v)
        return ", ".join(vals)

    return {
        "awb":         _joined("docket_no"),
        "consignor":   _joined("party_name"),
        "consignee":   _joined("consignee_name"),
        "destination": _joined("destination"),
        "carrier_ref": _joined("carrier_ref"),
    }

def _purchase_shipment_rows(items):
    """
    One dict per distinct shipment on a purchase invoice, instead of
    _purchase_shipment_summary's comma-joined single string — lets the
    statement show each AWB/consignee on its own row.
    """
    rows, seen = [], set()
    for it in items:
        awb = (getattr(it, "docket_no", None) or "").strip()
        consignee = (getattr(it, "consignee_name", None) or "").strip()
        destination = (getattr(it, "destination", None) or "").strip()
        carrier_ref = (getattr(it, "carrier_ref", None) or "").strip()   # -> statement "Reference No."
        carrier = (getattr(it, "courier_name", None) or "").strip()      # -> statement "Service"
        weight = getattr(it, "weight_kg", None) or 0
        other_charges = getattr(it, "other_charges", None) or 0
        taxable = getattr(it, "taxable_value", None) or 0
        per_kg = round(taxable / weight, 2) if weight > 0 else 0
        key = (awb, consignee, destination, carrier_ref)
        if key == ("", "", "", "") or key in seen:
            continue
        seen.add(key)
        rows.append({
            "awb": awb, "consignee": consignee, "destination": destination, "carrier_ref": carrier_ref,
            "carrier": carrier,
            # PurchaseInvoiceItem only stores one weight_kg (no chrg/act/vol split like the
            # client-side package JSON does), so charge and actual weight both read from it
            # and volumetric weight has no source -> always blank on this side.
            "chrg_wt": weight, "act_wt": weight, "vol_wt": 0,
            "other_charges": other_charges, "per_kg": per_kg,
        })
    return rows or [{"awb": "", "consignee": "", "destination": "", "carrier_ref": "",
                      "carrier": "", "chrg_wt": 0, "act_wt": 0, "vol_wt": 0, "other_charges": 0,
                      "per_kg": 0}]


# ── Seed Data ─────────────────────────────────────────────────────────────────
RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
if not (RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET):
    print("[WARN] RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not set in .env; online payments disabled.")
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

SUBSCRIPTION_PLANS_DATA = {
    "trial": {
        "name": "14-Day Free Trial",
        "price": "0",
        "price_1yr": "0",
        "price_3yr": "0",
        "price_lifetime": "0",
        "billing_period": "14_days",
        "max_companies": "1",
        "max_users": "3",
        "features": (
            "Full ERP Feature Access, "
            "1 Company & Branch, "
            "Up to 3 Team Users, "
            "Business Dashboard, "
            "Sales Invoicing & GST Bills, "
            "Inventory Management, "
            "Bank & Cash Flow Ledger, "
            "WhatsApp Notifications, "
            "Automated Cloud Backups, "
            "AI Business Assistant"
        ),
    },

    "starter": {
        "name": "Starter Plan",
        "price": "7999",
        "price_1yr": "7999",
        "price_3yr": "17999",
        "price_lifetime": "24999",
        "billing_period": "yearly",
        "max_companies": "1",
        "max_users": "5",
        "features": (
            "1 Company / Branch, "
            "Up to 5 Team Seats, "
            "Business Dashboard, "
            "Sales Invoicing & GST Bills, "
            "Inventory Management, "
            "Bank & Cash Flow Ledger, "
            "WhatsApp Notifications, "
            "Automated Cloud Backups, "
            "AI Business Assistant"
        ),
    },

    "business": {
        "name": "Business Plan",
        "price": "14999",
        "price_1yr": "14999",
        "price_3yr": "34999",
        "price_lifetime": "49999",
        "billing_period": "yearly",
        "max_companies": "3",
        "max_users": "15",
        "features": (
            "Up to 3 Companies / Branches, "
            "Up to 15 Team Seats, "
            "Business Dashboard, "
            "Sales Invoicing & GST Bills, "
            "Inventory Management, "
            "Bank & Cash Flow Ledger, "
            "WhatsApp Notifications, "
            "Automated Cloud Backups, "
            "AI Business Assistant"
        ),
    },

    "growth": {
        "name": "Growth Plan",
        "price": "29999",
        "price_1yr": "29999",
        "price_3yr": "69999",
        "price_lifetime": "99999",
        "billing_period": "yearly",
        "max_companies": "7",
        "max_users": "35",
        "features": (
            "Up to 7 Companies / Branches, "
            "Up to 35 Team Seats, "
            "Business Dashboard, "
            "Sales Invoicing & GST Bills, "
            "Inventory Management, "
            "Bank & Cash Flow Ledger, "
            "WhatsApp Notifications, "
            "Automated Cloud Backups, "
            "AI Business Assistant"
        ),
    },

    "enterprise": {
        "name": "Enterprise Plan",
        "price": "59999",
        "price_1yr": "59999",
        "price_3yr": "139999",
        "price_lifetime": "199999",
        "billing_period": "yearly",
        "max_companies": "15",
        "max_users": "100",
        "features": (
            "Up to 15 Companies / Branches, "
            "Up to 100 Team Seats, "
            "Business Dashboard, "
            "Sales Invoicing & GST Bills, "
            "Inventory Management, "
            "Bank & Cash Flow Ledger, "
            "WhatsApp Notifications, "
            "Automated Cloud Backups, "
            "AI Business Assistant, "
            "Dedicated Account Manager"
        ),
    },

    "unlimited": {
        "name": "Unlimited Scale Plan",
        "price": "99999",
        "price_1yr": "99999",
        "price_3yr": "229999",
        "price_lifetime": "Custom",
        "billing_period": "yearly",
        "max_companies": "Unlimited",
        "max_users": "Unlimited",
        "features": (
            "Unlimited Companies & Branches, "
            "Unlimited Team Seats, "
            "Business Dashboard, "
            "Sales Invoicing & GST Bills, "
            "Inventory Management, "
            "Bank & Cash Flow Ledger, "
            "WhatsApp Notifications, "
            "Automated Cloud Backups, "
            "AI Business Assistant, "
            "Dedicated Account Manager & Priority Support"
        ),
    },
}

PLAN_PRICING = {
    "trial": {"1_year": 0, "3_years": 0, "lifetime": 0},
    "starter": {"1_year": 7999, "3_years": 17999, "lifetime": 24999},
    "business": {"1_year": 14999, "3_years": 34999, "lifetime": 49999},
    "growth": {"1_year": 29999, "3_years": 69999, "lifetime": 99999},
    "enterprise": {"1_year": 59999, "3_years": 139999, "lifetime": 199999},
    "unlimited": {"1_year": 99999, "3_years": 229999, "lifetime": 0},
    "lifetime_maintenance": {"1_year": 2500, "3_years": 2500, "lifetime": 2500},
}

from plan_catalog import PUBLIC_PLANS
SUBSCRIPTION_PLANS_DATA.update(PUBLIC_PLANS)
PLAN_PRICING.update({key: {'1_year': int(p['price_1yr']), '3_years': int(p['price_3yr'])}
                     for key, p in PUBLIC_PLANS.items()})

def calculate_plan_price(plan_id, duration="1_year", custom_yearly_amount=None):
    if custom_yearly_amount is not None:
        try:
            c_amt = float(custom_yearly_amount)
            if c_amt > 0:
                if duration == "3_years":
                    return c_amt * 3
                return c_amt
        except (ValueError, TypeError):
            pass
    if plan_id == "trial":
        return 0
    if plan_id == "lifetime_maintenance":
        return 2500
    return PLAN_PRICING.get(plan_id, {}).get(duration, 0)


def seed_database():
    """Insert initial plans, users and sample data if the DB is empty."""
    # Ensure platform columns exist
    alter_stmts = [
        "ALTER TABLE registered_users ADD COLUMN last_trial_notice_date DATE NULL",
        "ALTER TABLE registered_users ADD COLUMN last_trial_email_date DATE NULL",
        "ALTER TABLE subscription_plans ADD COLUMN max_branches INTEGER NULL",
        "ALTER TABLE subscription_plans ADD COLUMN price_1yr VARCHAR(50)",
        "ALTER TABLE subscription_plans ADD COLUMN price_3yr VARCHAR(50)",
        "ALTER TABLE subscription_plans ADD COLUMN price_lifetime VARCHAR(50)",
        "ALTER TABLE registered_users ADD COLUMN plan_duration VARCHAR(20) DEFAULT '1_year'",
        "ALTER TABLE registered_users ADD COLUMN custom_yearly_amount NUMERIC(10,2) NULL",
        "ALTER TABLE registered_users ADD COLUMN maintenance_due_date DATE NULL",
        "ALTER TABLE registered_users ADD COLUMN last_maintenance_paid_at DATE NULL",
        "ALTER TABLE registered_users ADD COLUMN last_maintenance_prompt_date DATE NULL",
        "ALTER TABLE companies ADD COLUMN plan_duration VARCHAR(20) DEFAULT '1_year'",
        "ALTER TABLE companies ADD COLUMN custom_yearly_amount NUMERIC(10,2) NULL",
        "ALTER TABLE companies ADD COLUMN maintenance_due_date DATE NULL",
        "ALTER TABLE companies ADD COLUMN last_maintenance_paid_at DATE NULL",
    ]
    for stmt in alter_stmts:
        try:
            db.session.execute(text(stmt))
            db.session.commit()
        except Exception:
            db.session.rollback()

    # ── Subscription Plans (Platform DB) ─────────────────────────────────────
    # Keep legacy and private plans referenced by existing customers.
    for plan_id, data in SUBSCRIPTION_PLANS_DATA.items():
        plan = SubscriptionPlan.query.get(plan_id)
        if not plan:
            plan = SubscriptionPlan(id=plan_id)
            db.session.add(plan)
        plan.name = data["name"]
        plan.price = data["price"]
        plan.price_1yr = data.get("price_1yr", data["price"])
        plan.price_3yr = data.get("price_3yr", "")
        plan.price_lifetime = data.get("price_lifetime", "")
        plan.max_companies = data["max_companies"]
        plan.max_users = data["max_users"]
        plan.max_branches = data.get("max_branches")
        plan.features = data.get("features", "")
    db.session.commit()
    print("[OK] Subscription plans synced.")

    # ── Registered Users (Platform DB) ──────────────────────────────────────
    if RegisteredUser.query.count() == 0:
        demo = RegisteredUser(
            user_id="USR001",
            email="demo@demo.com",
            password_hash=hash_password("Demo@123"),
            full_name="Demo User",
            phone="9999999999",
            role="owner",
            subscription_plan="unified",
            created_at=date(2024, 1, 1),
            is_active=True,
            email_verified=True,
            must_change_password=False,
        )
        db.session.add(demo)
        db.session.commit()
        print("[OK] Demo user seeded.")

     # ── Super Admin (Platform DB) ────────────────────────────────────────────
    if RegisteredUser.query.filter_by(role="super_admin").count() == 0:
        bootstrap_password = os.environ.get("SUPER_ADMIN_PASSWORD")
        if bootstrap_password:
            username = os.environ.get("SUPER_ADMIN_USERNAME", "qiyadah").strip().lower()
            if RegisteredUser.query.filter_by(email=username).first():
                raise RuntimeError("Super-admin bootstrap username is already in use")
            admin = RegisteredUser(
                user_id="ADMIN001", email=username,
                password_hash=hash_password(bootstrap_password), full_name="Qiyadah",
                role="super_admin", is_active=True, email_verified=True,
                must_change_password=True,
            )
            db.session.add(admin)
            db.session.commit()
            print("[OK] Qiyadah super admin created; password change required.")
        else:
            print("[INFO] No super admin configured. Set SUPER_ADMIN_PASSWORD for first-time setup.")

    # ── Companies (Platform DB) ─────────────────────────────────────────────
    if Company.query.count() == 0:
        comp1 = Company(
            company_id="DEMO001",
            company_name="Demo Company",
            owner_email="demo@demo.com",
            subscription_plan="unified",
            subscription_start=date(2024, 1, 1),
            subscription_end=date(2030, 1, 1),
            max_companies_allowed="5",
            max_users_per_company="20",
            gst_number="27AAABC1234F1Z",
            address="Mumbai, Maharashtra",
            phone="9876543210",
            created_at=date(2024, 1, 1),
            is_active=True,
        )
        db.session.add(comp1)
        db.session.commit()
        print("[OK] Demo company seeded.")
    
    print("[OK] Platform database seeding complete.")

def _ensure_payment_ledger_columns(cdb):
    """One-time, idempotent schema patch: adds the applied_ref_type /
    applied_ref_id / applied_ci_id columns to cash_transactions and
    bank_transactions if they don't exist yet (db.create_all() only
    creates brand-new tables — it never ALTERs existing ones). Safe to
    call on every startup: each ALTER is wrapped so an existing column
    just no-ops instead of crashing the app.
    """
    from sqlalchemy import text
    statements = [
        "ALTER TABLE cash_transactions ADD COLUMN applied_ref_type VARCHAR(20)",
        "ALTER TABLE cash_transactions ADD COLUMN applied_ref_id INTEGER",
        "ALTER TABLE cash_transactions ADD COLUMN applied_ci_id INTEGER",
        "ALTER TABLE cash_transactions ADD COLUMN applied_ci_ids_json TEXT",
        "ALTER TABLE cash_transactions ADD COLUMN applied_breakdown_json TEXT",
        "ALTER TABLE bank_transactions ADD COLUMN applied_ref_type VARCHAR(20)",
        "ALTER TABLE bank_transactions ADD COLUMN applied_ref_id INTEGER",
        "ALTER TABLE bank_transactions ADD COLUMN applied_ci_id INTEGER",
        "ALTER TABLE bank_transactions ADD COLUMN applied_ci_ids_json TEXT",
        "ALTER TABLE bank_transactions ADD COLUMN applied_breakdown_json TEXT",
        "ALTER TABLE company_users ADD COLUMN field_permissions JSON",
        "ALTER TABLE company_users ADD COLUMN editable_fields JSON",
        "ALTER TABLE company_users ADD COLUMN permission_overrides JSON",
    ]
    for stmt in statements:
        try:
            cdb.execute(text(stmt))
            cdb.commit()
        except Exception:
            # Column already exists (or table doesn't exist yet on a brand
            # new company DB, where create_all() already created it with
            # the new columns) — either way, nothing to do.
            cdb.rollback()

    try:
        cdb.execute(text("UPDATE company_users SET permission_overrides = '{\"analytics\": {\"view\": true}}' WHERE role = 'bi_developer' AND (permission_overrides IS NULL OR permission_overrides = '' OR permission_overrides = '{}')"))
        cdb.commit()
    except Exception:
        cdb.rollback()


def seed_customer_database(company_id):
    """Seed customer data for a specific company in its own database."""
    from db_router import get_customer_session
    
    cdb = get_customer_session(company_id, db_session=db.session)

    _ensure_payment_ledger_columns(cdb)
    
    # ── Company Users ───────────────────────────────────────────────────────
    if cdb.query(CompanyUser).count() == 0:
        # Get company info to know the owner
        company = Company.query.filter_by(company_id=company_id).first()
        owner_reg = RegisteredUser.query.filter_by(email=company.owner_email).first()
        
        users = [
            CompanyUser(
                user_id="EMP001",
                company_id=company_id,
                email=company.owner_email,
                password_hash=hash_password("Demo@123"),
                full_name=owner_reg.full_name if owner_reg else "Demo User",
                role="owner",
                department="Management",
                phone=company.phone,
                is_active=True,
                created_at=today_ist()
            ),
        ]

        cdb.add_all(users)
        cdb.commit()
        print(f"✔  Company users seeded for {company_id}")

    # ── Clients ─────────────────────────────────────────────────────────────
    if cdb.query(Client).count() == 0 and company_id == "DEMO001":
        clients = [
            Client(company_id=company_id, name="ABC Electronics", client_type="Customer",
                   phone="9876543220", status="Active", created_at=today_ist()),
            Client(company_id=company_id, name="XYZ Traders", client_type="Customer",
                   phone="9876543221", status="Active", created_at=today_ist()),
            Client(company_id=company_id, name="PQR Solutions", client_type="Business",
                   phone="9876543222", status="Active", created_at=today_ist()),
            Client(company_id=company_id, name="Reliance Industries", phone="9876543210",
                   pending=0, last_payment=date(2024, 1, 22), status="Paid"),
            Client(company_id=company_id, name="Tata Consultancy", phone="9876543211",
                   pending=89500, last_payment=date(2024, 1, 5), status="Pending"),
            Client(company_id=company_id, name="Infosys Ltd", phone="9876543212",
                   pending=86000, last_payment=date(2024, 1, 18), status="Active"),
        ]
        cdb.add_all(clients)
        cdb.commit()
        print(f"✔  Clients seeded for {company_id}")

    # ── Stock Items ─────────────────────────────────────────────────────────
    if cdb.query(StockItem).count() == 0 and company_id == "DEMO001":
        items = [
            StockItem(company_id=company_id, code="PROD001", name="LED TV 43 inch",
                      category="Electronics", quantity=25, unit="pcs", unit_price=35000,
                      reorder_level=10, last_updated=date(2024, 1, 20)),
            StockItem(company_id=company_id, code="PROD002", name="Smartphone X",
                      category="Electronics", quantity=50, unit="pcs", unit_price=25000,
                      reorder_level=20, last_updated=date(2024, 1, 20)),
        ]
        cdb.add_all(items)
        cdb.commit()
        print(f"✔  Stock items seeded for {company_id}")

    # Close the session
    from db_router import close_customer_session
    close_customer_session(company_id)


# ── Plan helper ───────────────────────────────────────────────────────────────
def get_plan(plan_id):
    p = SubscriptionPlan.query.get(plan_id)
    if not p:
        if plan_id in SUBSCRIPTION_PLANS_DATA:
            d = SUBSCRIPTION_PLANS_DATA[plan_id]
            return {
                "id": plan_id,
                "name": d["name"],
                "price": d["price"],
                "price_1yr": d.get("price_1yr", d["price"]),
                "price_3yr": d.get("price_3yr", ""),
                "price_lifetime": d.get("price_lifetime", ""),
                "max_branches": d.get("max_branches"),
                "max_companies": d["max_companies"],
                "max_users_per_company": d["max_users"],
                "features": [f.strip() for f in d["features"].split(",") if f.strip()],
            }
        return {}
    return {
        "id": p.id,
        "name": p.name,
        "price": p.price,
        "price_1yr": p.price_1yr or p.price,
        "price_3yr": p.price_3yr or "",
        "price_lifetime": p.price_lifetime or "",
        "max_branches": p.max_branches,
        "max_companies": p.max_companies,
        "max_users_per_company": p.max_users,
        "features": [f.strip() for f in p.features.split(",") if f.strip()] if p.features else [],
    }

def get_all_plans():
    # Public registration never exposes private negotiated or legacy plans.
    return {pid: get_plan(pid) for pid in (*PUBLIC_PLANS, 'trial')}


# ── Company helpers ───────────────────────────────────────────────────────────
def get_company_by_id(company_id):
    return Company.query.filter_by(company_id=company_id).first()

def get_owner_companies(owner_email):
    return Company.query.filter_by(owner_email=owner_email, is_active=True).all()

def get_owner_user_stats(owner_email):
    """
    Distinct active users across ALL companies owned by this owner.
    CompanyUser rows live in each company's own separate database, so this
    opens every one of the owner's company DBs and dedupes by email.
    Returns (current_count, max_users, existing_emails_set).
    """
    companies = get_owner_companies(owner_email)
    emails = set()
    for c in companies:
        try:
            _cdb = get_customer_session(c.company_id)
            rows = _cdb.query(CompanyUser).filter_by(is_active=True).all()
            for r in rows:
                if r.email:
                    emails.add(r.email.strip().lower())
        except Exception as e:
            print(f"⚠  Could not read users for {c.company_id}: {e}")

    plan = get_plan(companies[0].subscription_plan) if companies else {}
    max_u = plan.get("max_users_per_company", "Unlimited")
    owner = RegisteredUser.query.filter_by(email=owner_email).first()
    if owner and owner.custom_max_users is not None:
        max_u = str(owner.custom_max_users)
    return len(emails), max_u, emails

@dataclass
class DashboardFilters:
    """Comprehensive filter object for BI dashboards"""
    company_id: str
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    period_type: PeriodType = PeriodType.MONTHLY
    employee_id: Optional[str] = None  # was Optional[int]; created_by stores email
    country: Optional[str] = None
    client_id: Optional[int] = None
    supplier_id: Optional[int] = None
    category: Optional[str] = None
    compare_from: Optional[date] = None
    compare_to: Optional[date] = None
    
    def to_dict(self) -> dict:
        return {
            'company_id': self.company_id,
            'from_date': self.from_date.isoformat() if self.from_date else None,
            'to_date': self.to_date.isoformat() if self.to_date else None,
            'period_type': self.period_type.value,
            'employee_id': self.employee_id,
            'country': self.country,
            'client_id': self.client_id,
            'supplier_id': self.supplier_id,
            'category': self.category,
            'compare_from': self.compare_from.isoformat() if self.compare_from else None,
            'compare_to': self.compare_to.isoformat() if self.compare_to else None,
        }

def parse_filters_from_request(request_args: dict, company_id: str) -> DashboardFilters:
    """Parse dashboard filters from request parameters"""
    filters = DashboardFilters(company_id=company_id)
    
    # Date filters
    if request_args.get('from_date'):
        try:
            filters.from_date = date.fromisoformat(request_args['from_date'])
        except ValueError:
            pass
    
    if request_args.get('to_date'):
        try:
            filters.to_date = date.fromisoformat(request_args['to_date'])
        except ValueError:
            pass
    
    # Period type
    period_type = request_args.get('period_type', 'monthly')
    try:
        filters.period_type = PeriodType(period_type)
    except ValueError:
        filters.period_type = PeriodType.MONTHLY
    
    # Employee filter
    filters.employee_id = request_args.get('employee_id', '').strip() or None
    
    # Country filter
    filters.country = request_args.get('country', '').strip() or None
    
    # Client/Supplier filters
    if request_args.get('client_id'):
        try:
            filters.client_id = int(request_args['client_id'])
        except ValueError:
            pass
    
    if request_args.get('supplier_id'):
        try:
            filters.supplier_id = int(request_args['supplier_id'])
        except ValueError:
            pass
    
    # Category filter
    filters.category = request_args.get('category', '').strip() or None
    
    # Comparison period
    if request_args.get('compare_from'):
        try:
            filters.compare_from = date.fromisoformat(request_args['compare_from'])
        except ValueError:
            pass
    
    if request_args.get('compare_to'):
        try:
            filters.compare_to = date.fromisoformat(request_args['compare_to'])
        except ValueError:
            pass
    
    return filters

def get_period_range(filters: DashboardFilters) -> tuple:
    """Get the date range based on period type"""
    today = today_ist()
    
    if filters.from_date and filters.to_date:
        return filters.from_date, filters.to_date
    
    if filters.period_type == PeriodType.DAILY:
        return today, today
    elif filters.period_type == PeriodType.WEEKLY:
        # Start of week (Monday)
        start = today - timedelta(days=today.weekday())
        return start, today
    elif filters.period_type == PeriodType.MONTHLY:
        start = today.replace(day=1)
        return start, today
    elif filters.period_type == PeriodType.QUARTERLY:
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        start = today.replace(month=quarter_month, day=1)
        return start, today
    elif filters.period_type == PeriodType.YEARLY:
        start = today.replace(month=1, day=1)
        return start, today
    else:
        # Default to last 30 days
        start = today - timedelta(days=30)
        return start, today

def get_previous_period_range(filters: DashboardFilters) -> tuple:
    """Get the previous period for comparison"""
    from_date, to_date = get_period_range(filters)
    days_diff = (to_date - from_date).days + 1
    prev_to = from_date - timedelta(days=1)
    prev_from = prev_to - timedelta(days=days_diff - 1)
    return prev_from, prev_to

def get_period_labels(filters: DashboardFilters) -> List[str]:
    """Generate period labels for charts"""
    from_date, to_date = get_period_range(filters)
    labels = []
    current = from_date
    
    if filters.period_type == PeriodType.DAILY:
        while current <= to_date:
            labels.append(current.strftime('%d %b'))
            current += timedelta(days=1)
    elif filters.period_type == PeriodType.WEEKLY:
        # Group by week
        current_week = current.isocalendar()[1]
        while current <= to_date:
            week_end = current + timedelta(days=6 - current.weekday())
            if week_end > to_date:
                week_end = to_date
            labels.append(f"Week {current_week}")
            current = week_end + timedelta(days=1)
            current_week += 1
    elif filters.period_type == PeriodType.MONTHLY:
        while current <= to_date:
            labels.append(current.strftime('%b %Y'))
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
    elif filters.period_type == PeriodType.QUARTERLY:
        while current <= to_date:
            quarter = (current.month - 1) // 3 + 1
            labels.append(f"Q{quarter} {current.year}")
            if current.month <= 9:
                current = current.replace(month=current.month + 3)
            else:
                current = current.replace(year=current.year + 1, month=1)
    elif filters.period_type == PeriodType.YEARLY:
        while current <= to_date:
            labels.append(str(current.year))
            current = current.replace(year=current.year + 1)
    else:
        # CUSTOM (and any unknown type): month buckets, matching
        # get_revenue_profit_chart_data()'s own CUSTOM handling exactly —
        # these two functions must produce the same number of entries or
        # the chart's labels and data arrays go out of sync.
        while current <= to_date:
            labels.append(current.strftime('%b %Y'))
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
    
    return labels

def _normalize_name_tokens(name):
    norm = re.sub(r'[^a-z0-9\s]', '', (name or '').lower()).strip()
    norm = re.sub(r'\s+', ' ', norm)
    tokens = [t for t in norm.split(' ') if len(t) > 1]
    return norm, tokens

def _name_similarity_score(name_a, name_b):
    """Order-independent, typo-tolerant similarity between two client names.
    Catches word-order swaps ('afsar sheikh mohammed' vs 'mohammed afsar sheikh')
    and single-letter typos ('shekh' vs 'sheikh', 'apsar' vs 'afsar')."""
    norm_a, tokens_a = _normalize_name_tokens(name_a)
    norm_b, tokens_b = _normalize_name_tokens(name_b)
    if not norm_a or not norm_b:
        return 0.0
    full_ratio = SequenceMatcher(None, norm_a, norm_b).ratio()
    best_token_ratio = 0.0
    for ta in tokens_a:
        for tb in tokens_b:
            r = 1.0 if ta == tb else SequenceMatcher(None, ta, tb).ratio()
            best_token_ratio = max(best_token_ratio, r)
    # weight token match slightly lower than full match so a single shared
    # common word (e.g. only "mohammed") doesn't score as high as a real dupe
    return max(full_ratio, best_token_ratio * 0.9)

def _find_similar_clients(cdb, company_id, name, exclude_pk=None):
    if not name or not name.strip():
        return []
    q = cdb.query(Client).filter_by(company_id=company_id)
    if exclude_pk:
        q = q.filter(Client.id != exclude_pk)
    matches = []
    for c in q.all():
        score = _name_similarity_score(name, c.name)
        if score >= 0.72:
            matches.append({
                "id": c.id, "name": c.name,
                "phone": c.phone or "", "city": c.city or "",
                "status": c.status or "Active",
                "score": round(score, 2),
            })
    matches.sort(key=lambda m: -m["score"])
    return matches[:8]

def check_company_limit(company_id, user_type="user"):
    company = get_company_by_id(company_id)
    if not company:
        return False, "Company not found"
    plan = get_plan(company.subscription_plan)
    if user_type == "user":
        # Seat cap is owner-wide (across all of the owner's companies),
        # not per company.
        current, max_u, _ = get_owner_user_stats(company.owner_email)
        try:
            max_u = int(max_u)
            if current >= max_u:
                return False, f"Maximum {max_u} users allowed across all your companies under your {plan['name']}. Please upgrade."
        except (ValueError, TypeError):
            pass  # "Unlimited"
    return True, "OK"

def check_new_company_limit(owner_email, company_name=None, branch_name=None):
    comps = get_owner_companies(owner_email)
    if not comps:
        return True, "OK"
    plan = get_plan(comps[0].subscription_plan)
    max_c = plan.get("max_companies", 2)
    owner = RegisteredUser.query.filter_by(email=owner_email).first()
    if owner and owner.custom_max_companies is not None:
        max_c = owner.custom_max_companies
    if plan.get('max_branches') is not None and company_name is not None:
        from plan_catalog import check_location_limits
        return check_location_limits(comps, company_name, branch_name, max_c, plan['max_branches'])
    try:
        max_c = int(max_c)
        if len(comps) >= max_c:
            return False, f"Your {plan['name']} allows up to {max_c} companies. Please upgrade."
    except (ValueError, TypeError):
        pass  # "Unlimited"
    return True, "OK"


def get_cdb():
    """
    Return a customer-database session for the currently active company.
    Use this everywhere you previously used db.session for customer tables.

    Goes through get_customer_session_with_retry(), which self-heals a
    session left broken by a previous request that never got torn down
    (e.g. a killed gunicorn worker) — a PendingRollbackError or dead
    connection here gets rolled back / rebuilt and retried once, instead
    of surfacing as a 500 on this request.

    Example:
        cdb = get_cdb()
        clients = cdb.query(Client).filter_by(company_id=company_id).all()
    """
    company_id = get_current_company()
    if not company_id:
        return None
    return get_customer_session_with_retry(company_id)

def _first_or_404(obj):
    """Replacement for Flask-SQLAlchemy's first_or_404() for plain SQLAlchemy queries."""
    if obj is None:
        from flask import abort
        abort(404)
    return obj

_MULTI_WORD_COUNTRIES = [
    'NEW ZELAND', 'NEW ZEALAND', 'SOUTH AFRICA', 'SOUTH KOREA', 'NORTH KOREA',
    'SAUDI ARABIA', 'UNITED KINGDOM', 'UNITED STATES', 'UNITED ARAB EMIRATES',
    'CZECH REPUBLIC', 'COSTA RICA', 'SRI LANKA', 'HONG KONG', 'PUERTO RICO',
    'EL SALVADOR', 'DOMINICAN REPUBLIC',
]


def get_employee_companies(email):
    results = []
    active_company_id = session.get("active_company_id")
    for comp in Company.query.filter_by(is_active=True).all():
        if getattr(comp, "hidden_on_mobile", False):
            continue
        try:
            _cdb = get_customer_session(comp.company_id)
            emp = _cdb.query(CompanyUser).filter_by(email=email, is_active=True).first()
            if emp:
                comp.emp_role = emp.role
                comp.emp_user_id = emp.user_id
                comp.is_active_selection = (comp.company_id == active_company_id)
                results.append(comp)
        except Exception:
            continue
    return results



# ============================================================
# KPI DATA FUNCTIONS
# ============================================================

def get_kpi_data(cdb, company_id, from_date, to_date, prev_from, prev_to, filters):
    """Calculate all KPI values with period-over-period comparisons"""
    
    # --- OPERATIONAL METRICS (Subject to all filters) ---
    billed = get_period_billed(cdb, company_id, from_date, to_date, filters)
    purchases = get_period_purchases(cdb, company_id, from_date, to_date, filters)
    gross_profit = billed - purchases
    gross_margin = (gross_profit / billed * 100) if billed > 0 else 0
    
    prev_billed = get_period_billed(cdb, company_id, prev_from, prev_to, filters)
    prev_purchases = get_period_purchases(cdb, company_id, prev_from, prev_to, filters)
    prev_gross_profit = prev_billed - prev_purchases
    
    employee_count = get_employee_count(cdb, company_id, filters)
    bookings = get_sales_invoice_count(cdb, company_id, from_date, to_date, filters)
    prev_bookings = get_sales_invoice_count(cdb, company_id, prev_from, prev_to, filters)
    
    # --- GLOBAL METRICS (Date-only filters — not affected by Client/Employee) ---
    # DashboardFilters is defined above in this same file; no import needed.
    global_filters = DashboardFilters(company_id=company_id)
    
    global_billed = get_period_billed(cdb, company_id, from_date, to_date, global_filters)
    global_purchases = get_period_purchases(cdb, company_id, from_date, to_date, global_filters)
    global_expenses = get_period_expenses(cdb, company_id, from_date, to_date, global_filters)
    global_profit = global_billed - global_purchases - global_expenses
    global_profit_margin = (global_profit / global_billed * 100) if global_billed > 0 else 0
    prev_global_billed = get_period_billed(cdb, company_id, prev_from, prev_to, global_filters)
    prev_global_purchases = get_period_purchases(cdb, company_id, prev_from, prev_to, global_filters)
    prev_global_expenses = get_period_expenses(cdb, company_id, prev_from, prev_to, global_filters)
    prev_global_profit = prev_global_billed - prev_global_purchases - prev_global_expenses
    
    from utils.query_engine import get_receivables_intelligence
    rec_intel = get_receivables_intelligence(cdb, company_id, from_date, to_date, prev_from, prev_to, filters)

    return {
        'revenue': {
            'value': round(billed, 2),
            'change': ((billed - prev_billed) / prev_billed * 100) if prev_billed > 0 else 0,
            'label': 'Total Sales',
            'icon': '📈', 'color': 'blue'
        },
        'purchases': {
            'value': round(purchases, 2),
            'change': ((purchases - prev_purchases) / prev_purchases * 100) if prev_purchases > 0 else 0,
            'label': 'Purchase',
            'icon': '🛒', 'color': 'orange'
        },
        'gross_profit': {
            'value': round(gross_profit, 2),
            'change': (((gross_profit) - (prev_gross_profit)) / (prev_gross_profit) * 100) if (prev_gross_profit) > 0 else 0,
            'label': 'Gross Margin',
            'icon': '💎', 'color': 'green'
        },
        'expenses': {
            'value': round(global_expenses, 2),
            'change': ((global_expenses - prev_global_expenses) / prev_global_expenses * 100) if prev_global_expenses > 0 else 0,
            'label': 'Company Expenses',
            'icon': '💸', 'color': 'red',
            'global_only': True
        },
        'profit': {
            'value': round(global_profit, 2),
            'change': ((global_profit - prev_global_profit) / prev_global_profit * 100) if prev_global_profit > 0 else 0,
            'label': 'Net Profit',
            'icon': '🏦', 'color': 'indigo',
            'global_only': True
        },
        'margin': {
            'value': round(global_profit_margin, 1),
            'change': 0,
            'label': 'Net Margin %',
            'icon': '📊', 'color': 'teal', 'is_percentage': True,
            'global_only': True
        },
        'revenue_per_employee': {
            'value': round(billed / employee_count, 2) if employee_count > 0 else 0,
            'change': 0,
            'label': 'Revenue/Employee',
            'icon': '👤', 'color': 'purple'
        },
        'pending_balance': {
            'value': round(rec_intel['total_live_outstanding'], 2),
            'change': round(rec_intel['outstanding_change_pct'], 1),
            'period_pending_added': round(rec_intel['period_pending_added'], 2),
            'label': 'Total Outstanding',
            'icon': '⏳', 'color': 'orange'
        },
        'total_bookings': {
            'value': bookings,
            'change': ((bookings - prev_bookings) / prev_bookings * 100) if prev_bookings > 0 else 0,
            'label': 'Invoices / Jobs',
            'icon': '📋', 'color': 'blue'
        },
        'gst_payable': {
            'value': round(get_period_gst_output(cdb, company_id, from_date, to_date, filters), 2),
            'change': 0,
            'label': 'GST Collected (Output)',
            'icon': '🧾', 'color': 'red'
        }
    }

def get_finance_snapshot(cdb, company_id, from_date, to_date):
    """
    Returns company-wide cash/bank position for the given date window.
    These numbers are NEVER filtered by client or employee.

    cash_in_hand   – running balance of all CashTransactions up to to_date
    bank_balance   – sum of current BankAccount.balance (live, from BankAccount table)
    period_expense – company expenses booked within from_date..to_date
    period_cash_in – cash inflows within from_date..to_date
    period_cash_out– cash outflows within from_date..to_date
    """
    # ── Cash in Hand (all-time running balance up to to_date) ──────────────
    all_cash = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        CashTransaction.date <= to_date
    ).all()
    cash_income  = sum(t.amount or 0 for t in all_cash if t.type == 'income')
    cash_expense = sum(t.amount or 0 for t in all_cash if t.type == 'expense')
    cash_in_hand = cash_income - cash_expense

    # ── Bank Balance (current live balance, not date-filtered) ─────────────
    bank_accounts = cdb.query(BankAccount).filter_by(
        company_id=company_id, status='Active'
    ).all()
    bank_balance = sum(acc.balance or 0 for acc in bank_accounts)

    # ── Period Expense (date-filtered, no client/employee filter) ──────────
    period_expense = sum(
        exp.amount or 0
        for exp in cdb.query(Expense).filter(
            Expense.company_id == company_id,
            Expense.date >= from_date,
            Expense.date <= to_date
        ).all()
    )

    # ── Period Cash flows ──────────────────────────────────────────────────
    period_cash_txns = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        CashTransaction.date >= from_date,
        CashTransaction.date <= to_date
    ).all()
    period_cash_in  = sum(t.amount or 0 for t in period_cash_txns if t.type == 'income')
    period_cash_out = sum(t.amount or 0 for t in period_cash_txns if t.type == 'expense')

    return {
        'cash_in_hand': round(cash_in_hand, 2),
        'bank_balance': round(bank_balance, 2),
        'period_expense': round(period_expense, 2),
        'period_cash_in': round(period_cash_in, 2),
        'period_cash_out': round(period_cash_out, 2),
    }


def _invoice_country(inv):
    """Safely extract destination country from Invoice.terms JSON blob"""
    if not inv.terms:
        return None
    try:
        meta = json.loads(inv.terms)
        dest = meta.get('destination')
        return dest.strip() if dest else None
    except (ValueError, TypeError):
        return None

def get_period_billed(cdb, company_id, from_date, to_date, filters):
    """Gross billed sales amount for the period across active customer invoices (Product Sales & Workshop Repairs).
    
    Includes GST (billing KPI). Excludes Void/Draft/Cancelled.
    """
    q_ci = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.invoice_date >= from_date,
        CustomerInvoice.invoice_date <= to_date,
        CustomerInvoice.status.notin_(['Void', 'Draft', 'Cancelled'])
    )
    if getattr(filters, 'client_id', None):
        q_ci = q_ci.filter(CustomerInvoice.client_id == filters.client_id)
    if getattr(filters, 'employee_id', None):
        q_ci = q_ci.filter(CustomerInvoice.created_by == filters.employee_id)
    if getattr(filters, 'category', None):
        q_ci = q_ci.filter(CustomerInvoice.invoice_category == filters.category)
    ci_invoices = q_ci.all()
    if ci_invoices:
        return sum(float(inv.grand_total or 0) for inv in ci_invoices)

    query = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.date >= from_date,
        Invoice.date <= to_date,
        Invoice.status.notin_(['Void', 'Draft', 'Cancelled'])
    )
    if getattr(filters, 'client_id', None):
        query = query.filter(Invoice.client_id == filters.client_id)
    if getattr(filters, 'employee_id', None):
        query = query.filter(Invoice.created_by == filters.employee_id)
    invoices = query.all()
    if getattr(filters, 'country', None):
        invoices = [inv for inv in invoices if _invoice_country(inv) == filters.country]
    return sum(float(inv.grand_total or 0) for inv in invoices)

def get_period_revenue(cdb, company_id, from_date, to_date, filters):
    """Taxable Sales Revenue (subtotal excl. GST) for the period."""
    q_ci = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.invoice_date >= from_date,
        CustomerInvoice.invoice_date <= to_date,
        CustomerInvoice.status.notin_(['Void', 'Draft', 'Cancelled'])
    )
    if getattr(filters, 'client_id', None):
        q_ci = q_ci.filter(CustomerInvoice.client_id == filters.client_id)
    if getattr(filters, 'employee_id', None):
        q_ci = q_ci.filter(CustomerInvoice.created_by == filters.employee_id)
    if getattr(filters, 'category', None):
        q_ci = q_ci.filter(CustomerInvoice.invoice_category == filters.category)
    ci_invoices = q_ci.all()
    if ci_invoices:
        return sum(float(inv.subtotal or 0) for inv in ci_invoices)

    query = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.date >= from_date,
        Invoice.date <= to_date,
        Invoice.status.notin_(['Void', 'Draft', 'Cancelled'])
    )
    if getattr(filters, 'client_id', None):
        query = query.filter(Invoice.client_id == filters.client_id)
    if getattr(filters, 'employee_id', None):
        query = query.filter(Invoice.created_by == filters.employee_id)
    invoices = query.all()
    if getattr(filters, 'country', None):
        invoices = [inv for inv in invoices if _invoice_country(inv) == filters.country]
    return sum(float(inv.subtotal or 0) for inv in invoices)

def get_period_gst_output(cdb, company_id, from_date, to_date, filters):
    """GST collected on sales for the period (Output Tax)."""
    q_ci = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.invoice_date >= from_date,
        CustomerInvoice.invoice_date <= to_date,
        CustomerInvoice.status.notin_(['Void', 'Draft', 'Cancelled'])
    )
    if getattr(filters, 'client_id', None):
        q_ci = q_ci.filter(CustomerInvoice.client_id == filters.client_id)
    if getattr(filters, 'employee_id', None):
        q_ci = q_ci.filter(CustomerInvoice.created_by == filters.employee_id)
    if getattr(filters, 'category', None):
        q_ci = q_ci.filter(CustomerInvoice.invoice_category == filters.category)
    ci_invoices = q_ci.all()
    if ci_invoices:
        return sum(float(inv.tax_amount or 0) for inv in ci_invoices)

    query = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.date >= from_date,
        Invoice.date <= to_date,
        Invoice.status.notin_(['Void', 'Draft', 'Cancelled'])
    )
    return sum(float(inv.tax_amount or 0) for inv in query.all())

def get_period_purchases(cdb, company_id, from_date, to_date, filters):
    """Get total purchase / direct procurement cost for the period."""
    query = cdb.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.date >= from_date,
        PurchaseInvoice.date <= to_date,
        PurchaseInvoice.status.notin_(['Void', 'Draft', 'Cancelled'])
    )
    if getattr(filters, 'supplier_id', None):
        query = query.filter(PurchaseInvoice.supplier_id == filters.supplier_id)
    return sum(float(pur.grand_total or 0) for pur in query.all())

def get_period_expenses(cdb, company_id, from_date, to_date, filters):
    """Get expenses for a specific period with filters"""
    query = cdb.query(Expense).filter(
        Expense.company_id == company_id,
        Expense.date >= from_date,
        Expense.date <= to_date
    )
    
    if getattr(filters, 'category', None):
        query = query.filter(Expense.category == filters.category)

    if getattr(filters, 'employee_id', None):
        emp = cdb.query(CompanyUser).filter(
            CompanyUser.company_id == company_id,
            CompanyUser.email == filters.employee_id
        ).first()
        possible_created_by = {filters.employee_id}
        if emp and emp.full_name:
            possible_created_by.add(emp.full_name)
        query = query.filter(Expense.created_by.in_(possible_created_by))
    
    return sum(float(exp.amount or 0) for exp in query.all())

def get_employee_count(cdb, company_id, filters):
    """Get count of active employees"""
    query = cdb.query(CompanyUser).filter(
        CompanyUser.company_id == company_id,
        CompanyUser.is_active == True,
        CompanyUser.role != 'owner'
    )
    return query.count()

def get_pending_balance(cdb, company_id, filters):
    """Get pending balance with filters."""
    from utils.query_engine import _compute_client_live_outstanding, _compute_outstanding_for_all_clients
    if filters and getattr(filters, 'client_id', None):
        client = cdb.query(Client).filter_by(
            id=filters.client_id, company_id=company_id
        ).first()
        if client:
            return _compute_client_live_outstanding(cdb, company_id, client)
        return 0.0
    all_bals = _compute_outstanding_for_all_clients(cdb, company_id)
    return sum(b for b in all_bals.values() if b > 0)

def get_sales_invoice_count(cdb, company_id, from_date, to_date, filters):
    """Get sales invoice / job card count for a period."""
    q_ci = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.invoice_date >= from_date,
        CustomerInvoice.invoice_date <= to_date,
        CustomerInvoice.status.notin_(['Void', 'Draft', 'Cancelled']),
    )
    if getattr(filters, 'client_id', None):
        q_ci = q_ci.filter(CustomerInvoice.client_id == filters.client_id)
    if getattr(filters, 'employee_id', None):
        q_ci = q_ci.filter(CustomerInvoice.created_by == filters.employee_id)
    if getattr(filters, 'category', None):
        q_ci = q_ci.filter(CustomerInvoice.invoice_category == filters.category)
    ci_cnt = q_ci.count()
    if ci_cnt > 0:
        return ci_cnt

    query = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.date >= from_date,
        Invoice.date <= to_date,
        Invoice.status.notin_(['Void', 'Draft', 'Cancelled']),
    )
    if getattr(filters, 'client_id', None):
        query = query.filter(Invoice.client_id == filters.client_id)
    if getattr(filters, 'employee_id', None):
        query = query.filter(Invoice.created_by == filters.employee_id)
    if not getattr(filters, 'country', None):
        return query.count()

    invoices = query.all()
    return sum(1 for inv in invoices if _invoice_country(inv) == filters.country)

# ============================================================
# CHART DATA FUNCTIONS
# ============================================================

def get_revenue_profit_chart_data(cdb, company_id, from_date, to_date, filters):
    """Get revenue and profit trend data"""
    labels = []
    revenue_data = []
    profit_data = []
    purchase_data = []
    booking_data = []
    margin_data = []
    
    current = from_date
    while current <= to_date:
        # Determine period end
        if filters.period_type == PeriodType.DAILY:
            period_end = current
        elif filters.period_type == PeriodType.WEEKLY:
            period_end = current + timedelta(days=6 - current.weekday())
            if period_end > to_date:
                period_end = to_date
        elif filters.period_type == PeriodType.MONTHLY:
            if current.month == 12:
                period_end = current.replace(year=current.year + 1, month=1) - timedelta(days=1)
            else:
                period_end = current.replace(month=current.month + 1, day=1) - timedelta(days=1)
            if period_end > to_date:
                period_end = to_date
        elif filters.period_type == PeriodType.QUARTERLY:
            quarter_end_month = ((current.month - 1) // 3 + 1) * 3
            if quarter_end_month > 12:
                quarter_end_month = 12
            period_end = current.replace(month=quarter_end_month, day=1)
            if period_end.month == 12:
                period_end = period_end.replace(day=31)
            else:
                period_end = period_end.replace(month=period_end.month + 1, day=1) - timedelta(days=1)
            if period_end > to_date:
                period_end = to_date
        elif filters.period_type == PeriodType.YEARLY:
            period_end = current.replace(month=12, day=31)
            if period_end > to_date:
                period_end = to_date
        else:
            if current.month == 12:
                period_end = current.replace(year=current.year + 1, month=1) - timedelta(days=1)
            else:
                period_end = current.replace(month=current.month + 1, day=1) - timedelta(days=1)
            if period_end > to_date:
                period_end = to_date
        
        billed = get_period_billed(cdb, company_id, current, period_end, filters)
        bookings = get_sales_invoice_count(cdb, company_id, current, period_end, filters)
        pur = get_period_purchases(cdb, company_id, current, period_end, filters)
        exp = get_period_expenses(cdb, company_id, current, period_end, filters)

        prof = billed - pur - exp
        margin = (prof / billed * 100) if billed > 0 else 0
        
        # Format label
        if filters.period_type == PeriodType.DAILY:
            labels.append(current.strftime('%d %b'))
        elif filters.period_type == PeriodType.WEEKLY:
            labels.append(f"Week {current.isocalendar()[1]}")
        elif filters.period_type == PeriodType.MONTHLY:
            labels.append(current.strftime('%b %Y'))
        elif filters.period_type == PeriodType.QUARTERLY:
            quarter = (current.month - 1) // 3 + 1
            labels.append(f"Q{quarter} {current.year}")
        elif filters.period_type == PeriodType.YEARLY:
            labels.append(str(current.year))
        else:
            labels.append(current.strftime('%b %Y'))
        
        revenue_data.append(round(billed, 2))
        purchase_data.append(round(pur, 2))
        profit_data.append(round(prof, 2))
        booking_data.append(bookings)
        margin_data.append(round(margin, 1))
        
        # Move to next period
        if filters.period_type == PeriodType.DAILY:
            current = period_end + timedelta(days=1)
        elif filters.period_type == PeriodType.WEEKLY:
            current = period_end + timedelta(days=1)
        elif filters.period_type == PeriodType.MONTHLY:
            if period_end.month == 12:
                current = period_end.replace(year=period_end.year + 1, month=1, day=1)
            else:
                current = period_end.replace(month=period_end.month + 1, day=1)
        elif filters.period_type == PeriodType.QUARTERLY:
            if period_end.month == 12:
                current = period_end.replace(year=period_end.year + 1, month=1, day=1)
            else:
                current = period_end.replace(month=period_end.month + 1, day=1)
        elif filters.period_type == PeriodType.YEARLY:
            current = period_end.replace(year=period_end.year + 1, month=1, day=1)
        else:
            if period_end.month == 12:
                current = period_end.replace(year=period_end.year + 1, month=1, day=1)
            else:
                current = period_end.replace(month=period_end.month + 1, day=1)
    
    return {
        'labels': labels,
        'revenue': revenue_data,
        'purchases': purchase_data,
        'profit': profit_data,
        'bookings': booking_data,
        'margin': margin_data
    }

def get_sales_purchase_comparison(cdb, company_id, from_date, to_date, filters):
    """Get sales vs purchase comparison data"""
    sales_data = []
    purchase_data = []
    labels = []
    
    current = from_date
    while current <= to_date:
        if current.month == 12:
            period_end = current.replace(year=current.year + 1, month=1) - timedelta(days=1)
        else:
            period_end = current.replace(month=current.month + 1, day=1) - timedelta(days=1)
        if period_end > to_date:
            period_end = to_date
        
        sales = get_period_billed(cdb, company_id, current, period_end, filters)
        purchases = get_period_purchases(cdb, company_id, current, period_end, filters)
        
        sales_data.append(round(sales, 2))
        purchase_data.append(round(purchases, 2))
        labels.append(current.strftime('%b %Y'))
        
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    
    return {
        'labels': labels,
        'sales': sales_data,
        'purchases': purchase_data
    }

def get_top_countries_chart_data(cdb, company_id, from_date, to_date, filters):
    """Get top revenue streams / business categories by sales amount."""
    ci_query = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.invoice_date >= from_date,
        CustomerInvoice.invoice_date <= to_date,
        CustomerInvoice.status.notin_(['Void', 'Draft', 'Cancelled'])
    )
    if getattr(filters, 'client_id', None):
        ci_query = ci_query.filter(CustomerInvoice.client_id == filters.client_id)
    if getattr(filters, 'employee_id', None):
        ci_query = ci_query.filter(CustomerInvoice.created_by == filters.employee_id)
    ci_invoices = ci_query.all()
    
    cat_map = {
        'product_sale': 'Product Sales & Parts',
        'workshop_repair': 'Workshop Repair & Service',
        'logistics': 'Logistics & Freight'
    }

    if ci_invoices:
        categories = {}
        for inv in ci_invoices:
            raw_cat = (inv.invoice_category or 'product_sale').lower().strip()
            cat_label = cat_map.get(raw_cat, raw_cat.replace('_', ' ').title())
            categories[cat_label] = categories.get(cat_label, 0.0) + float(inv.grand_total or 0)
        
        sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:10]
        return {
            'labels': [c[0] for c in sorted_cats],
            'values': [round(c[1], 2) for c in sorted_cats]
        }

    # Fallback to destination countries if only legacy bookings exist
    invoices = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.date >= from_date,
        Invoice.date <= to_date,
        Invoice.status.notin_(['Void', 'Draft', 'Cancelled'])
    ).all()
    countries = {}
    for inv in invoices:
        dest = _invoice_country(inv) or 'Domestic Sales'
        countries[dest] = countries.get(dest, 0.0) + float(inv.grand_total or 0)
    sorted_countries = sorted(countries.items(), key=lambda x: x[1], reverse=True)[:10]
    return {
        'labels': [c[0] for c in sorted_countries],
        'values': [round(c[1], 2) for c in sorted_countries]
    }

def get_top_employees_chart_data(cdb, company_id, from_date, to_date, filters):
    """Get top employees by revenue generated"""
    employees = cdb.query(CompanyUser).filter(
        CompanyUser.company_id == company_id,
        CompanyUser.is_active == True
    ).all()
    
    employee_data = []
    for emp in employees:
        emp_filters = DashboardFilters(
            company_id=company_id,
            employee_id=emp.email,
            from_date=from_date,
            to_date=to_date,
            country=getattr(filters, 'country', None),
        )
        revenue = get_period_billed(cdb, company_id, from_date, to_date, emp_filters)
        if revenue > 0:
            employee_data.append({
                'name': emp.full_name or emp.email,
                'revenue': round(revenue, 2),
                'booking_count': get_sales_invoice_count(cdb, company_id, from_date, to_date, emp_filters)
            })
    
    employee_data.sort(key=lambda x: x['revenue'], reverse=True)
    top_employees = employee_data[:10]
    
    return {
        'labels': [e['name'] for e in top_employees],
        'revenue': [e['revenue'] for e in top_employees],
        'counts': [e['booking_count'] for e in top_employees]
    }

def get_profit_breakdown_chart_data(cdb, company_id, from_date, to_date, filters):
    """Get profit breakdown by category (COGS vs Operating Expenses vs Net Profit)."""
    revenue = get_period_billed(cdb, company_id, from_date, to_date, filters)
    purchases = get_period_purchases(cdb, company_id, from_date, to_date, filters)
    expenses = get_period_expenses(cdb, company_id, from_date, to_date, filters)
    net_profit = revenue - purchases - expenses

    categories = {
        'COGS (Purchases)': round(purchases, 2),
        'Operating Expenses': round(expenses, 2),
        'Net Profit': round(net_profit, 2)
    }

    return {
        'labels': list(categories.keys()),
        'values': list(categories.values()),
        'colors': ['#F59E0B', '#EF4444', '#059669'],
        'revenue': round(revenue, 2)
    }

def get_monthly_trends_chart_data(cdb, company_id, from_date, to_date, filters):
    """Get multi-line monthly trends"""
    current_date = to_date
    labels = []
    revenue_data = []
    purchase_data = []
    profit_data = []
    booking_data = []
    
    for _ in range(12):
        month_start = current_date.replace(day=1)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1) - timedelta(days=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)
        
        rev = get_period_revenue(cdb, company_id, month_start, month_end, filters)
        pur = get_period_purchases(cdb, company_id, month_start, month_end, filters)
        exp = get_period_expenses(cdb, company_id, month_start, month_end, filters)
        bookings = get_sales_invoice_count(cdb, company_id, month_start, month_end, filters)
        
        labels.append(month_start.strftime('%b %Y'))
        revenue_data.append(round(rev, 2))
        purchase_data.append(round(pur, 2))
        profit_data.append(round(rev - pur - exp, 2))
        booking_data.append(bookings)
        
        current_date = month_start - timedelta(days=1)
    
    return {
        'labels': labels[::-1],
        'revenue': revenue_data[::-1],
        'purchases': purchase_data[::-1],
        'profit': profit_data[::-1],
        'bookings': booking_data[::-1]
    }

def get_invoice_status_chart_data(cdb, company_id, from_date, to_date, filters):
    """Get sales invoice / job status distribution"""
    ci_invoices = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.invoice_date >= from_date,
        CustomerInvoice.invoice_date <= to_date,
        CustomerInvoice.status.notin_(['Void', 'Draft', 'Cancelled'])
    ).all()
    
    status_counts = {
        'Paid': 0,
        'Partial': 0,
        'Pending': 0,
        'Draft': 0
    }
    
    if ci_invoices:
        for inv in ci_invoices:
            st = (inv.status or 'Pending').title()
            status_counts[st] = status_counts.get(st, 0) + 1
    else:
        invoices = cdb.query(Invoice).filter(
            Invoice.company_id == company_id,
            Invoice.date >= from_date,
            Invoice.date <= to_date,
            Invoice.status.notin_(['Void', 'Draft', 'Cancelled'])
        ).all()
        for inv in invoices:
            st = (inv.status or 'Pending').title()
            status_counts[st] = status_counts.get(st, 0) + 1
    
    labels = [k for k, v in status_counts.items() if v > 0]
    values = [v for k, v in status_counts.items() if v > 0]
    colors = ['#059669', '#D97706', '#DC2626', '#6B7280', '#9CA3AF']
    
    return {
        'labels': labels,
        'values': values,
        'colors': colors[:len(labels)]
    }

def get_payment_methods_chart_data(cdb, company_id, from_date, to_date, filters):
    """Get payment methods distribution"""
    cash_txns = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        CashTransaction.type == 'income',
        CashTransaction.date >= from_date,
        CashTransaction.date <= to_date
    ).all()
    
    bank_txns = cdb.query(BankTransaction).filter(
        BankTransaction.company_id == company_id,
        BankTransaction.type == 'credit',
        BankTransaction.date >= from_date,
        BankTransaction.date <= to_date
    ).all()
    
    total_cash = sum(float(t.amount or 0) for t in cash_txns)
    
    online_amount = 0
    cheque_amount = 0
    other_amount = 0
    
    for txn in bank_txns:
        mode = str(txn.transaction_mode or '').lower()
        if 'online' in mode or 'upi' in mode or 'neft' in mode or 'rtgs' in mode or 'transfer' in mode:
            online_amount += float(txn.amount or 0)
        elif 'cheque' in mode or 'check' in mode:
            cheque_amount += float(txn.amount or 0)
        else:
            other_amount += float(txn.amount or 0)
    
    return {
        'labels': ['Cash', 'Online/UPI/Bank', 'Cheque', 'Other'],
        'values': [round(total_cash, 2), round(online_amount, 2), round(cheque_amount, 2), round(other_amount, 2)],
        'colors': ['#059669', '#2563EB', '#D97706', '#6B7280']
    }

# ============================================================
# TABLE DATA FUNCTIONS
# ============================================================

def get_summary_table_data(cdb, company_id, from_date, to_date, filters):
    """Get summary table data for the dashboard (Top Clients & Suppliers)."""
    from utils.query_engine import _compute_client_live_outstanding
    # ── CLIENT DATA ──────────────────────────────────────────────────────────
    clients = cdb.query(Client).filter(
        Client.company_id == company_id,
        Client.status != 'Deleted'
    ).all()

    client_data = []
    for client in clients:
        client_filters = DashboardFilters(
            company_id=company_id,
            client_id=client.id,
            from_date=from_date,
            to_date=to_date,
            employee_id=getattr(filters, 'employee_id', None),
            country=getattr(filters, 'country', None),
        )
        revenue = get_period_billed(cdb, company_id, from_date, to_date, client_filters)
        if revenue > 0:
            client_data.append({
                'name': client.name,
                'revenue': round(revenue, 2),
                'booking_count': get_sales_invoice_count(cdb, company_id, from_date, to_date, client_filters),
                'pending': round(_compute_client_live_outstanding(cdb, company_id, client), 2),
                'status': client.status or 'Active'
            })

    client_data.sort(key=lambda x: x['revenue'], reverse=True)
    client_data = client_data[:10]

    # ── SUPPLIER DATA ─────────────────────────────────────────────────────────
    suppliers = cdb.query(Supplier).filter(
        Supplier.company_id == company_id,
        Supplier.status != 'Deleted'
    ).order_by(Supplier.name).all()

    supplier_data = []
    for supplier in suppliers:
        purchased = cdb.query(PurchaseInvoice).filter(
            PurchaseInvoice.company_id == company_id,
            PurchaseInvoice.supplier_id == supplier.id,
            PurchaseInvoice.date >= from_date,
            PurchaseInvoice.date <= to_date,
            PurchaseInvoice.status.notin_(['Void', 'Draft', 'Cancelled'])
        ).all()
        total_purchased = sum(float(p.grand_total or 0) for p in purchased)
        
        pending_payable = cdb.query(PurchaseInvoice).filter(
            PurchaseInvoice.company_id == company_id,
            PurchaseInvoice.supplier_id == supplier.id,
            PurchaseInvoice.status.notin_(['Paid', 'Void', 'Draft', 'Cancelled'])
        ).all()
        total_pending = sum(float(p.balance or 0) for p in pending_payable)

        if total_purchased > 0 or total_pending > 0:
            supplier_data.append({
                'name': supplier.name,
                'total_purchased': round(total_purchased, 2),
                'pending': round(total_pending, 2),
                'status': supplier.status or 'Active'
            })

    supplier_data.sort(key=lambda x: x['total_purchased'], reverse=True)

    return {
        'headers': ['Client', 'Total Sales', 'Invoices / Jobs', 'Pending (Receivable)', 'Status'],
        'rows': client_data,
        'supplier_headers': ['Supplier', 'Total Purchased (Period)', 'Pending Payable', 'Status'],
        'supplier_rows': supplier_data
    }


def get_detailed_table_data(cdb, company_id, from_date, to_date, filters):
    """Get detailed transaction-level data (most recent 50 sales & repair invoices)."""
    q_ci = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.invoice_date >= from_date,
        CustomerInvoice.invoice_date <= to_date,
        CustomerInvoice.status.notin_(['Void', 'Draft', 'Cancelled'])
    )
    if getattr(filters, 'client_id', None):
        q_ci = q_ci.filter(CustomerInvoice.client_id == filters.client_id)
    if getattr(filters, 'employee_id', None):
        q_ci = q_ci.filter(CustomerInvoice.created_by == filters.employee_id)
    if getattr(filters, 'category', None):
        q_ci = q_ci.filter(CustomerInvoice.invoice_category == filters.category)
    
    ci_invoices = q_ci.order_by(CustomerInvoice.invoice_date.desc()).limit(50).all()
    
    rows = []
    if ci_invoices:
        cat_display = {
            'product_sale': 'Product Sale',
            'workshop_repair': 'Workshop Repair',
            'logistics': 'Logistics & Freight'
        }
        for inv in ci_invoices:
            c_name = inv.client_name or (inv.client_obj.name if inv.client_obj else '—')
            cat_label = cat_display.get(inv.invoice_category, (inv.invoice_category or 'Sale').replace('_', ' ').title())
            rows.append({
                'invoice_id': inv.invoice_number,
                'date': inv.invoice_date.strftime('%d %b %Y') if inv.invoice_date else '—',
                'client': c_name,
                'category': cat_label,
                'amount': round(float(inv.grand_total or 0), 2),
                'status': inv.status or 'Pending',
                'created_by': inv.created_by or '—'
            })
    else:
        q_inv = cdb.query(Invoice).filter(
            Invoice.company_id == company_id,
            Invoice.date >= from_date,
            Invoice.date <= to_date,
            Invoice.status.notin_(['Void', 'Draft', 'Cancelled'])
        )
        if getattr(filters, 'client_id', None):
            q_inv = q_inv.filter(Invoice.client_id == filters.client_id)
        if getattr(filters, 'employee_id', None):
            q_inv = q_inv.filter(Invoice.created_by == filters.employee_id)
        
        invoices = q_inv.order_by(Invoice.date.desc()).limit(50).all()
        for inv in invoices:
            client_name = inv.client_obj.name if inv.client_obj else (inv.contact_person or '—')
            rows.append({
                'invoice_id': inv.invoice_id,
                'date': inv.date.strftime('%d %b %Y') if inv.date else '—',
                'client': client_name,
                'category': 'Sales Booking',
                'amount': round(float(inv.grand_total or 0), 2),
                'status': inv.status or 'Pending',
                'created_by': inv.created_by or '—'
            })
    
    return {
        'headers': ['Invoice #', 'Date', 'Client', 'Category', 'Amount', 'Status', 'Created By'],
        'rows': rows
    }

# ============================================================
# COMPARISON FUNCTIONS
# ============================================================

def get_period_over_period_comparison(cdb, company_id, from_date, to_date, prev_from, prev_to, filters):
    """Get period-over-period comparison data"""
    current = {
        'revenue': get_period_billed(cdb, company_id, from_date, to_date, filters),
        'purchases': get_period_purchases(cdb, company_id, from_date, to_date, filters),
        'expenses': get_period_expenses(cdb, company_id, from_date, to_date, filters),
        'bookings': get_sales_invoice_count(cdb, company_id, from_date, to_date, filters)
    }
    
    previous = {
        'revenue': get_period_billed(cdb, company_id, prev_from, prev_to, filters),
        'purchases': get_period_purchases(cdb, company_id, prev_from, prev_to, filters),
        'expenses': get_period_expenses(cdb, company_id, prev_from, prev_to, filters),
        'bookings': get_sales_invoice_count(cdb, company_id, prev_from, prev_to, filters)
    }
    
    current['profit'] = current['revenue'] - current['purchases'] - current['expenses']
    previous['profit'] = previous['revenue'] - previous['purchases'] - previous['expenses']
    
    return {
        'current_period': {
            'from': from_date.strftime('%d %b %Y'),
            'to': to_date.strftime('%d %b %Y')
        },
        'previous_period': {
            'from': prev_from.strftime('%d %b %Y'),
            'to': prev_to.strftime('%d %b %Y')
        },
        'metrics': {
            'Total Sales': {
                'current': round(current['revenue'], 2),
                'previous': round(previous['revenue'], 2),
                'change_pct': ((current['revenue'] - previous['revenue']) / previous['revenue'] * 100) if previous['revenue'] > 0 else 0
            },
            'Purchases': {
                'current': round(current['purchases'], 2),
                'previous': round(previous['purchases'], 2),
                'change_pct': ((current['purchases'] - previous['purchases']) / previous['purchases'] * 100) if previous['purchases'] > 0 else 0
            },
            'Expenses': {
                'current': round(current['expenses'], 2),
                'previous': round(previous['expenses'], 2),
                'change_pct': ((current['expenses'] - previous['expenses']) / previous['expenses'] * 100) if previous['expenses'] > 0 else 0
            },
            'Profit': {
                'current': round(current['profit'], 2),
                'previous': round(previous['profit'], 2),
                'change_pct': ((current['profit'] - previous['profit']) / previous['profit'] * 100) if previous['profit'] > 0 else 0
            },
            'Bookings': {
                'current': current['bookings'],
                'previous': previous['bookings'],
                'change_pct': ((current['bookings'] - previous['bookings']) / previous['bookings'] * 100) if previous['bookings'] > 0 else 0
            }
        }
    }

def get_year_over_year_comparison(cdb, company_id, from_date, to_date, filters):
    """Get year-over-year comparison data"""
    # Get current year data
    current_year = to_date.year
    current_start = date(current_year, 1, 1)
    current_end = to_date
    
    # Get previous year data (same period)
    prev_year = current_year - 1
    prev_start = date(prev_year, 1, 1)
    prev_end = date(prev_year, to_date.month, to_date.day)
    
    current_revenue = get_period_billed(cdb, company_id, current_start, current_end, filters)
    prev_revenue = get_period_billed(cdb, company_id, prev_start, prev_end, filters)
    
    # Monthly breakdown for YoY comparison
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    current_monthly = []
    prev_monthly = []
    
    for month in range(1, 13):
        month_start = date(current_year, month, 1)
        if month == 12:
            month_end = date(current_year, month, 31)
        else:
            month_end = date(current_year, month + 1, 1) - timedelta(days=1)
        
        if month_end > to_date:
            month_end = to_date
        
        current_rev = get_period_billed(cdb, company_id, month_start, month_end, filters)
        current_monthly.append(round(current_rev, 2))
        
        prev_month_start = date(prev_year, month, 1)
        if month == 12:
            prev_month_end = date(prev_year, month, 31)
        else:
            prev_month_end = date(prev_year, month + 1, 1) - timedelta(days=1)
        
        if prev_month_end > to_date:
            prev_month_end = to_date
        
        prev_rev = get_period_billed(cdb, company_id, prev_month_start, prev_month_end, filters)
        prev_monthly.append(round(prev_rev, 2))
    
    return {
        'current_year': current_year,
        'previous_year': prev_year,
        'current_total': round(current_revenue, 2),
        'previous_total': round(prev_revenue, 2),
        'yoy_growth': ((current_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 0,
        'months': months,
        'current_monthly': current_monthly,
        'previous_monthly': prev_monthly
    }



def get_party_name(client_id=None, supplier_id=None, form=None, fallback_name=None):
    """
    Single source of truth for getting the correct party name for transactions.
    Ensures consistency across receipts, payments, and booking edits.
    
    Args:
        client_id: The client ID (for receipts/debtors)
        supplier_id: The supplier ID (for payments/creditors)
        form: The request form object (for cash/walk-in bookings)
        fallback_name: A fallback name if all else fails
    
    Returns:
        The correct party name string
    """
    cdb = get_cdb()
    company_id = get_current_company()
    
    # Priority 1: If we have a client_id, get the exact name from Client table
    if client_id:
        client = cdb.query(Client).filter_by(id=client_id, company_id=company_id).first()
        if client:
            return client.name
    
    # Priority 2: If we have a supplier_id, get the exact name from Supplier table
    if supplier_id:
        supplier = cdb.query(Supplier).filter_by(id=supplier_id, company_id=company_id).first()
        if supplier:
            return supplier.name
    
    # Priority 3: For cash/walk-in bookings, get from form
    if form:
        shipper_name = form.get("shipper_name", "").strip()
        if shipper_name:
            return shipper_name
        # Alternative: customer_name field
        customer_name = form.get("customer_name", "").strip()
        if customer_name:
            return customer_name
        # Alternative: client_name field
        client_name = form.get("client_name", "").strip()
        if client_name:
            return client_name
        # Alternative: party_name field
        party_name = form.get("party_name", "").strip()
        if party_name:
            return party_name
    
    # Priority 4: Use fallback
    if fallback_name:
        return fallback_name
    
    # Last resort: return a generic name
    return "Unknown Party"

def _supplier_closing_balance(cdb, company_id, s):
    """Live running balance exactly as the supplier statement page computes
    it: opening balance + Σ(grand_total − paid_amount) across purchase invoices."""
    total = s.opening_balance or 0
    for inv in cdb.query(PurchaseInvoice).filter_by(company_id=company_id, supplier_id=s.id).all():
        total += (inv.grand_total or 0) - (inv.paid_amount or 0)
    return total


def _supplier_close_statement(cdb, company_id, s, action, scope="till_yesterday", as_of_date=None):
    """Archives the supplier's current live ledger into StatementClosing,
    then marks the closed PurchaseInvoice rows as fully paid (so the
    payable, which is driven directly off PurchaseInvoice.paid_amount/
    balance, nets to zero for the closed period) and moves the statement
    cutoff forward so the next statement load starts blank (action=
    'cleared') or with just the carried-forward balance (action=
    'carried_forward'). Invoices are kept for GST/audit — only
    paid_amount/balance/status change, same fields a normal payment
    update would touch.

    `as_of_date`: the LAST date to include in the archived/closed
    statement — same semantics as _client_close_statement's as_of_date.
    If not given, derived from `scope` (only relevant for action=
    'cleared'): 'till_yesterday' (default) -> yesterday; 'complete' ->
    today. Clamped so it can't precede the day before the existing
    statement_cutoff, or fall after today.
    Returns the amount that was payable at closing time."""
    today = today_ist()

    if as_of_date is None:
        if action == "cleared" and scope == "complete":
            as_of_date = today
        else:
            as_of_date = today - timedelta(days=1)

    if as_of_date > today:
        as_of_date = today
    if s.statement_cutoff:
        floor_date = s.statement_cutoff.date() - timedelta(days=1)
        if as_of_date < floor_date:
            as_of_date = floor_date

    archive_until = as_of_date + timedelta(days=1)  # exclusive upper bound

    ledger, total_debit, total_credit, closing = _build_supplier_ledger(
        cdb, company_id, s, since=s.statement_cutoff, until=archive_until)

    cdb.add(StatementClosing(
        company_id=company_id,
        entity_type="supplier",
        entity_id=s.id,
        entity_name=s.name,
        action=action,
        closing_balance=closing,
        total_debit=total_debit,
        total_credit=total_credit,
        ledger_snapshot=json.dumps(ledger, default=str),
        closed_by=session.get("username", "unknown"),
        closed_at=datetime.utcnow(),
    ))

    closed_invoices_q = cdb.query(PurchaseInvoice).filter_by(
        company_id=company_id, supplier_id=s.id
    ).filter(PurchaseInvoice.date < archive_until)
    if s.statement_cutoff:
        closed_invoices_q = closed_invoices_q.filter(
            PurchaseInvoice.date >= s.statement_cutoff.date())
    for inv in closed_invoices_q.all():
        if (inv.balance or 0) != 0 or (inv.paid_amount or 0) != (inv.grand_total or 0):
            inv.paid_amount = inv.grand_total or 0
            inv.balance = 0
            inv.status = "Paid"

    s.statement_cutoff = datetime.combine(archive_until, datetime.min.time())
    s.opening_balance = closing if action == "carried_forward" else 0
    s.payable = s.opening_balance
    return closing


# Add this helper function near other company helpers (around line 200)
# ── Add this helper function near other company helpers ──
def is_gst_number_taken(gst_number, exclude_company_id=None):
    """
    Check if a GST number is already used by ANY company (global uniqueness).
    Only checks ACTIVE companies.
    """
    if not gst_number or not gst_number.strip():
        return False
    
    query = Company.query.filter(
        func.lower(Company.gst_number) == func.lower(gst_number.strip()),
        Company.is_active == True
    )
    if exclude_company_id:
        query = query.filter(Company.company_id != exclude_company_id)
    return query.first() is not None

def is_company_name_taken(owner_email, company_name, exclude_company_id=None, branch_name=""):
    """
    Check if a company and branch name are already taken by the SAME owner.
    Only checks ACTIVE companies.
    """
    query = Company.query.filter(
        Company.owner_email == owner_email,
        func.lower(Company.company_name) == func.lower(company_name.strip()),
        func.lower(func.coalesce(Company.branch_name, "")) == func.lower((branch_name or "").strip()),
        Company.is_active == True
    )
    if exclude_company_id:
        query = query.filter(Company.company_id != exclude_company_id)
    return query.first() is not None


# ─────────────────────────────────────────────────────────────────────────────
# ── Auth Routes ───────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for("apps_hub"))
    return redirect(url_for("login"))

@app.route("/api/ai-chat", methods=["POST"])
@login_required
def api_ai_chat():
    """
    Chat endpoint for the ERP AI assistant. company_id is ALWAYS taken
    from the server-side session (get_current_company()) — the request
    body is never trusted for it, so there is no way for the client to
    ask about a different company's data by editing the payload.
    """
    payload = request.get_json(silent=True) or {}
    user_message = (payload.get("message") or "").strip()

    if not user_message:
        return jsonify({"response": "Please type a question.", "source": "error"}), 400
    if len(user_message) > 500:
        return jsonify({"response": "That's a bit long — please ask in under 500 characters.",
                         "source": "error"}), 400

    company_id = get_current_company()

    result = _ai_assistant.chat(
        user_message=user_message,
        company_id=company_id,
        has_permission=has_permission,   # your existing permissions.py-backed function
    )

    return jsonify(result)


@app.route("/api/ai-chat/clear", methods=["POST"])
@login_required
def api_ai_chat_clear():
    """Clears the assistant's short conversational memory (not DB data)."""
    _ai_assistant.clear_context()
    return jsonify({"ok": True})

@app.route("/health")
def health_check():
    """Health check endpoint to warm up database connections"""
    try:
        # Try a simple query on platform DB
        db.session.execute(text("SELECT 1")).fetchone()
        
        # Try customer DB if company is active
        company_id = get_current_company()
        if company_id:
            cdb = get_cdb()
            if cdb:
                cdb.execute(text("SELECT 1")).fetchone()
        
        return jsonify({"status": "healthy"})
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500

@app.route("/sw.js")
def service_worker():
    response = send_from_directory("static", "sw.js")
    response.headers["Content-Type"] = "application/javascript"
    # Grants the SW control over "/" and below, even though the file
    # itself lives under /static — required since scope defaults to
    # the serving directory otherwise.
    response.headers["Service-Worker-Allowed"] = "/"
    return response

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        # Super-admin / registered-user login
        reg_user = RegisteredUser.query.filter_by(email=email, is_active=True).first()
        if reg_user and verify_password(password, reg_user.password_hash):
            if reg_user.role == "super_admin":
                session.clear()
                if reg_user.must_change_password:
                    session["pending_password_change_email"] = reg_user.email
                    return redirect(url_for("force_change_password"))
                session["user"] = {
                    "user_id": reg_user.user_id, "email": reg_user.email,
                    "full_name": reg_user.full_name, "role": "super_admin",
                    "company_id": None,
                }
                return redirect(url_for("admin_dashboard"))

            # Owner: If email is not verified, require 6-digit OTP verification
            if not reg_user.email_verified:
                _generate_and_send_otp(reg_user.email)
                flash(f"Please enter the 6-digit verification code sent to {reg_user.email}.", "warning")
                return redirect(url_for("verify_otp"))
            elif reg_user.must_change_password:
                session["pending_password_change_email"] = reg_user.email
                return redirect(url_for("force_change_password"))
            return _finish_owner_login(reg_user)

        # Company employee login — search each company's DB
        emp_matches = []  # list of (company_id, CompanyUser row)
        for comp in Company.query.filter_by(is_active=True).all():
            try:
                _cdb = get_customer_session(comp.company_id)
                _emp = _cdb.query(CompanyUser).filter_by(email=email, is_active=True).first()
                if _emp and verify_password(password, _emp.password_hash):
                    emp_matches.append((comp.company_id, _emp))
            except Exception:
                continue

        if emp_matches:
            session.clear()
            session["pending_login_email"] = email
            session["pending_login_type"] = "employee"
            session["pending_login_company_ids"] = [cid for cid, emp in emp_matches]
            return redirect(url_for("select_company"))

        flash("Invalid email or password")
    return render_template("login.html")

@app.route("/company/update-terms", methods=["POST"])
@login_required
@owner_required
def update_company_terms():
    company_id = get_current_company()
    company    = get_company_by_id(company_id)
    if company:
        company.terms_footer   = request.form.get("terms_footer", "").strip() or None
        company.terms_annexure = request.form.get("terms_annexure", "").strip() or None

        # ── Terms Visibility (per print format) ──
        company.show_terms_customer_invoice = "show_terms_customer_invoice" in request.form
        company.show_terms_performa_invoice = "show_terms_performa_invoice" in request.form

        db.session.commit()
        flash("Invoice terms updated.")
    return redirect(url_for("company_settings"))

@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    email = session.get("otp_email")
    if not email:
        return redirect(url_for("login"))

    if request.method == "POST":
        entered = request.form.get("otp", "").strip()
        expires = session.get("otp_expires")
        if not expires or datetime.utcnow() > datetime.fromisoformat(expires):
            flash("Verification code has expired. Please click Resend Code to receive a new one.", "error")
            return redirect(url_for("verify_otp"))
        if hashlib.sha256(entered.encode()).hexdigest() != session.get("otp_hash"):
            flash("Incorrect verification code. Please check and try again.", "error")
            return redirect(url_for("verify_otp"))

        reg_user = RegisteredUser.query.filter_by(email=email).first()
        if not reg_user:
            flash("User account not found. Please log in again.", "error")
            return redirect(url_for("login"))

        reg_user.email_verified = True
        reg_user.must_change_password = False
        db.session.commit()
        session.pop("otp_email", None)
        session.pop("otp_hash", None)
        session.pop("otp_expires", None)

        flash("Email verified successfully! Welcome to Qiyadah ERP.", "success")
        return _finish_owner_login(reg_user)

    return render_template("verify_otp.html", email=email)


@app.route("/verify-otp/resend")
def resend_otp():
    email = session.get("otp_email")
    if email:
        _generate_and_send_otp(email)
        flash("A new 6-digit verification code has been sent to your email.", "success")
    return redirect(url_for("verify_otp"))


@app.route("/force-change-password", methods=["GET", "POST"])
def force_change_password():
    email = session.get("pending_password_change_email")
    if not email:
        return redirect(url_for("login"))
    reg_user = RegisteredUser.query.filter_by(email=email, is_active=True).first()
    if not reg_user:
        return redirect(url_for("login"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters", "error")
            return redirect(url_for("force_change_password"))
        if password != confirm:
            flash("Passwords don't match", "error")
            return redirect(url_for("force_change_password"))

        reg_user.password_hash = hash_password(password)
        reg_user.must_change_password = False
        db.session.commit()
        session.pop("pending_password_change_email", None)
        if reg_user.role == "super_admin":
            session.clear()
            session["user"] = {"user_id": reg_user.user_id, "email": reg_user.email,
                "full_name": reg_user.full_name, "role": "super_admin", "company_id": None}
            return redirect(url_for("admin_dashboard"))
        return _finish_owner_login(reg_user)

    return render_template("force_change_password.html", email=email)

@app.route("/account-setup", methods=["GET", "POST"])
def account_setup():
    return redirect(url_for("verify_otp"))


@app.route("/account-setup/resend")
def resend_account_setup_otp():
    return redirect(url_for("resend_otp"))

@app.route("/company/add", methods=["GET", "POST"])
@login_required
@owner_required
def add_new_company():
    
    company_id = get_current_company()
    user = get_current_user()
    
    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        branch_name = request.form.get("branch_name", "").strip()
        if len(branch_name) > 100:
            flash("Branch name must be 100 characters or fewer.", "error")
            return redirect(url_for("add_new_company"))
        gst_number = request.form.get("gst_number", "")
        address = request.form.get("address", "")
        phone = request.form.get("phone", "")
        
        if not company_name:
            flash("Company name is required")
            return redirect(url_for("add_new_company"))
        
        if is_company_name_taken(user.get("email"), company_name, branch_name=branch_name):
            flash("This company and branch already exist. Please use a different branch name.", "error")
            return redirect(url_for("add_new_company"))
        
        # ── Check if GST number is already used by ANY company ──
        if gst_number and is_gst_number_taken(gst_number):
            flash(f"GST number '{gst_number}' is already registered to another active company. Please check and try again.", "error")
            return redirect(url_for("add_new_company"))

        # Check if user can add more companies based on their plan
        can_add, message = check_new_company_limit(user.get("email"), company_name, branch_name)
        if not can_add:
            flash(message)
            return redirect(url_for("company_settings"))
        
        # Create new company
        new_company_id = _next_numbered_id(db.session, Company.company_id, "QIY_")
        
        # Get user's plan
        reg_user = RegisteredUser.query.filter_by(email=user.get("email")).first()
        plan = reg_user.subscription_plan if reg_user else None
        plan_obj = SubscriptionPlan.query.get(plan) or SubscriptionPlan.query.order_by(SubscriptionPlan.id).first()

        is_gst = request.form.get('is_gst_registered', '1') == '1'
        gst_number = request.form.get('gst_number', '').strip() if is_gst else None
        
        new_company = Company(
            company_id=new_company_id,
            company_name=company_name,
            branch_name=branch_name or None,
            owner_email=user.get("email"),
            subscription_plan=plan,
            subscription_start=today_ist(),
            subscription_end=today_ist() + timedelta(days=365),
            max_companies_allowed=plan_obj.max_companies,
            max_users_per_company=plan_obj.max_users,
            gst_number=gst_number if is_gst else '',
            address=address,
            phone=phone,
            created_at=today_ist(),
            is_active=True,
            is_gst_registered=is_gst,
            awb_prefix=(request.form.get("awb_prefix", "AHL") or "AHL").strip().upper(),
            awb_start=int(request.form.get("awb_start", 81000) or 81000),
        )
        try:
            apply_company_tax(new_company, request.form)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("add_new_company"))
        db.session.add(new_company)
        db.session.commit()

        # ── Create dedicated VPS MySQL database and all customer tables ────────
        init_customer_db_for_company(new_company)

        # ── Create the owner as first CompanyUser in the new customer DB ───────
        cdb = get_customer_session(new_company_id)
        validate_company_role_assignment(get_company_by_id(company_id), request.form.get("role", "employee"))
        emp_id    = _next_numbered_id(cdb, CompanyUser.user_id, "EMP")
        new_emp   = CompanyUser(
            user_id=emp_id,
            company_id=new_company_id,
            email=user.get("email"),
            password_hash=hash_password(request.form.get("password", "Temp@123")),
            full_name=user.get("full_name", ""),
            role="owner",
            department="Management",
            phone=phone,
            is_active=True,
            created_at=today_ist(),
        )
        cdb.add(new_emp)
        cdb.commit()

        flash(f"Company '{company_name}' created successfully! A dedicated database has been provisioned.")
        return redirect(url_for("dashboard"))
    
    # GET request - show the form with user's plan information
    user = get_current_user()
    reg_user = RegisteredUser.query.filter_by(email=user.get("email")).first()
    plan_key = reg_user.subscription_plan if reg_user else None
    plan_obj = SubscriptionPlan.query.get(plan_key) or SubscriptionPlan.query.order_by(SubscriptionPlan.id).first()
    
    # Get current companies count for this owner
    account_companies = Company.query.filter_by(owner_email=user.get("email"), is_active=True).all()
    companies_count = (len({c.company_name.strip().casefold() for c in account_companies})
                       if plan_obj.max_branches is not None else len(account_companies))
    max_companies_allowed = plan_obj.max_companies
    
    # Parse max companies (handle "Unlimited" string)
    if max_companies_allowed == "Unlimited":
        max_companies = None
        remaining_companies = "Unlimited"
        can_add_more = True
    else:
        max_companies = int(max_companies_allowed)
        remaining_companies = max(0, max_companies - companies_count)
        can_add_more = remaining_companies > 0
        if plan_obj.max_branches is not None:
            can_add_more = can_add_more or sum(bool(c.branch_name) for c in account_companies) < plan_obj.max_branches
    
    plan_config = {
        "name": plan_obj.name,
        "price": plan_obj.price,
        "max_companies": plan_obj.max_companies,
        "max_users": plan_obj.max_users,
        "features": plan_obj.features.split(",") if plan_obj.features else [],
        "companies_used": companies_count,
        "remaining_companies": remaining_companies,
        "max_companies_int": max_companies,
        "can_add_more": can_add_more,
    }
    
    return render_template(
                "add_company.html",
                plan_config=plan_config,
                current_count=companies_count,
                max_companies=plan_obj.max_companies if plan_obj.max_companies == "Unlimited" else int(plan_obj.max_companies),
                can_add=can_add_more,
                awb_prefix="AHL",
                awb_start=81000,
            )

@app.route("/select-company", methods=["GET", "POST"])
def select_company():
    if "user" in session:
        current_role = session["user"].get("role")
        login_type = "owner" if current_role in ("owner", "super_admin") else "employee"
        pending_email = session["user"].get("email")
    else:
        login_type = session.get("pending_login_type", "owner")
        pending_email = session.get("pending_login_email")
    
    if not pending_email:
        return redirect(url_for("login"))

    if request.method == "POST":
        company_id = request.form.get("company_id")

        if login_type == "employee":
            allowed_ids = session.get("pending_login_company_ids")
            if allowed_ids is not None and company_id not in allowed_ids:
                flash("Invalid company selection.")
                return redirect(url_for("select_company"))
            comp = get_company_by_id(company_id)
            emp = None
            if comp and comp.is_active:
                _cdb = get_customer_session(company_id)
                emp = _cdb.query(CompanyUser).filter_by(
                    email=pending_email, company_id=company_id, is_active=True
                ).first()
            if emp:
                session["user"] = {
                    "user_id": emp.user_id, "email": emp.email,
                    "full_name": emp.full_name, "role": emp.role,
                    "company_id": company_id,
                }
                session["active_company_id"] = company_id
                session.pop("pending_login_email", None)
                session.pop("pending_login_type", None)
                session.pop("pending_login_company_ids", None)
                return redirect(url_for("apps_hub"))
            flash("Invalid company selection.")

        else:  # owner (existing logic, unchanged)
            company = get_company_by_id(company_id)
            if company and company.is_active and company.owner_email == pending_email:
                reg_user = RegisteredUser.query.filter_by(email=pending_email).first()
                session["user"] = {
                    "email": reg_user.email, "full_name": reg_user.full_name,
                    "role": reg_user.role, "user_id": reg_user.user_id,
                }
                session["active_company_id"] = company_id
                session.pop("pending_login_email", None)
                session.pop("pending_login_type", None)
                return redirect(url_for("apps_hub"))
            flash("Invalid company selection.")

    # GET — build the list to render
    if login_type == "employee":
        companies = get_employee_companies(pending_email)
        allowed_ids = session.get("pending_login_company_ids")
        if allowed_ids is not None:
            companies = [company for company in companies if company.company_id in allowed_ids]
        first_emp = None
        if companies:
            _cdb = get_customer_session(companies[0].company_id)
            first_emp = _cdb.query(CompanyUser).filter_by(email=pending_email, is_active=True).first()
        user = {
            "full_name": first_emp.full_name if first_emp else pending_email,
            "email": pending_email,
            "role": first_emp.role if first_emp else "employee",
        }
        owner_user_count = owner_max_users = None
    else:
        companies = get_owner_companies(pending_email)
        user = get_current_user() or {"full_name": pending_email, "email": pending_email, "role": "owner"}
        owner_user_count, owner_max_users, _ = get_owner_user_stats(pending_email)

    return render_template("select_company.html", companies=companies, user=user,
                           owner_user_count=owner_user_count, owner_max_users=owner_max_users)


@app.route("/company/toggle-mobile-visibility/<company_id>", methods=["POST"])
def toggle_company_mobile_visibility(company_id):
    """Owner-only: show/hide one of their companies everywhere (desktop AND
    mobile) on the Select Company screen.

    No @login_required/@owner_required here on purpose: an owner picking
    between multiple companies reaches this page via session["pending_login_email"]
    BEFORE session["user"] is ever set, so those decorators would 404/redirect
    every single time this button is clicked. Auth is handled manually below,
    mirroring select_company()'s own two-path logic.
    """
    if "user" in session:
        user = get_current_user()
        if user.get("role") not in ("owner", "super_admin"):
            flash("Only company owner can access this page")
            return safe_redirect_after_denial()
        owner_email = user.get("email", "")
    else:
        if session.get("pending_login_type", "owner") != "owner":
            flash("Please login to continue")
            return redirect(url_for("login"))
        owner_email = session.get("pending_login_email") or ""
        if not owner_email:
            flash("Please login to continue")
            return redirect(url_for("login"))

    company = Company.query.filter_by(company_id=company_id, owner_email=owner_email).first()
    if not company:
        flash("Company not found.")
        return redirect(url_for("select_company"))
    company.hidden_on_mobile = not company.hidden_on_mobile
    db.session.commit()
    flash(f"{company.company_name} is now {'hidden' if company.hidden_on_mobile else 'visible'}.")
    return redirect(url_for("select_company"))


@app.route("/switch-company/<company_id>")
@login_required
def switch_company(company_id):
    user = get_current_user()
    company = get_company_by_id(company_id)
    if not company:
        flash("Company not found.")
        return redirect(url_for("dashboard"))

    if user.get("role") in ("owner", "super_admin") and company.owner_email == user.get("email"):
        session["active_company_id"] = company_id
        session["user"]["company_id"] = company_id
        flash(f"Switched to {company.company_name}")
        return redirect(url_for("apps_hub"))

    # Non-owner: must have an active CompanyUser row in the target company
    cdb = get_customer_session(company_id)
    emp = cdb.query(CompanyUser).filter_by(
        email=user.get("email"), company_id=company_id, is_active=True
    ).first()
    if emp:
        session["active_company_id"] = company_id
        session["user"]["company_id"] = company_id
        session["user"]["role"] = emp.role
        session["user"]["user_id"] = emp.user_id
        flash(f"Switched to {company.company_name}")
    else:
        flash("You don't have access to that company.")
    return redirect(url_for("apps_hub"))

@app.route("/onboarding/create-company", methods=["GET", "POST"])
@login_required
def onboard_company():
    """
    First-login step for accounts created by the super admin (register_client).
    The RegisteredUser already exists with no Company yet — this is where the
    client sets up their own company profile (GST, AWB numbering, etc).
    """
    user = get_current_user()
    email = user.get("email")

    reg_user = RegisteredUser.query.filter_by(email=email).first()
    if not reg_user:
        return redirect(url_for("login"))

    # If they already have a company, this step is done — don't let them repeat it
    existing = get_owner_companies(email)
    if existing:
        session["active_company_id"] = existing[0].company_id
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        if not company_name:
            flash("Company name is required", "error")
            return redirect(url_for("onboard_company"))
        
        is_gst     = request.form.get("is_gst_registered", "1") == "1"
        gst_number = request.form.get('gst_number', '').strip() if is_gst else None
        
        branch_name = request.form.get("branch_name", "").strip()
        if len(branch_name) > 100:
            flash("Branch name must be 100 characters or fewer.", "error")
            return redirect(url_for("onboard_company"))
        if is_company_name_taken(email, company_name, branch_name=branch_name):
            flash(f"A company named '{company_name}' already exists. Please choose a different name.", "error")
            return redirect(url_for("onboard_company"))

        if gst_number and is_gst_number_taken(gst_number):
            flash(f"GST number '{gst_number}' is already registered to another active company. Please check and try again.", "error")
            return redirect(url_for("onboard_company"))
        
        is_gst     = request.form.get("is_gst_registered", "1") == "1"
        gst_number = request.form.get("gst_number", "").strip() if is_gst else ""
        address    = request.form.get("address", "").strip()
        phone      = request.form.get("phone", reg_user.phone or "").strip()
        awb_prefix = (request.form.get("awb_prefix", "AHL") or "AHL").strip().upper()
        awb_start  = int(request.form.get("awb_start", 81000) or 81000)

        plan_obj = SubscriptionPlan.query.get(reg_user.subscription_plan) or SubscriptionPlan.query.order_by(SubscriptionPlan.id).first()
        end_days = 730 if plan_obj.id == "custom" else 365

        new_company_id = _next_numbered_id(db.session, Company.company_id, "QIY_")

        # ── NEW: Use custom plan values if available ───────────────────────
        max_companies = plan_obj.max_companies
        max_users = plan_obj.max_users
        
        # Override with custom values if this user has them
        if plan_obj.id == "custom":
            if reg_user.custom_max_companies:
                max_companies = str(reg_user.custom_max_companies)
            if reg_user.custom_max_users:
                max_users = str(reg_user.custom_max_users)

        new_company = Company(
            company_id=new_company_id,
            company_name=company_name,
            owner_email=email,
            branch_name=branch_name or None,
            subscription_plan=plan_obj.id,
            subscription_start=today_ist(),
            subscription_end=today_ist() + timedelta(days=end_days),
            max_companies_allowed=max_companies,
            max_users_per_company=max_users,
            gst_number=gst_number,
            address=address,
            phone=phone,
            created_at=today_ist(),
            is_active=True,
            is_gst_registered=is_gst,
            storage_type="cloud",
            awb_prefix=awb_prefix,
            awb_start=awb_start,
        )
        try:
            apply_company_tax(new_company, request.form)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("onboard_company"))
        db.session.add(new_company)
        db.session.commit()

        init_customer_db_for_company(new_company)

        # Owner becomes the first CompanyUser — reuse their existing password,
        # don't ask for a second one.
        try:
            cdb = get_customer_session(new_company_id)
            new_emp = CompanyUser(
                user_id="EMP001",
                company_id=new_company_id,
                email=email,
                password_hash=reg_user.password_hash,
                full_name=reg_user.full_name,
                role="owner",
                department="Management",
                phone=phone,
                is_active=True,
                created_at=today_ist(),
            )
            cdb.add(new_emp)
            cdb.commit()
        except Exception as e:
            cdb.rollback()
            print(f"⚠  Could not create CompanyUser for {new_company_id}: {e}")

        session["active_company_id"] = new_company_id
        session["user"]["company_id"] = new_company_id
        flash(f"Company '{company_name}' created. Welcome to Qiyadah ERP!", "success")
        return redirect(url_for("dashboard"))

    return render_template("onboard_company.html", user=reg_user, awb_prefix="AHL", awb_start=81000)


# ═════════════════════════════════════════════════════════════════════════
# ── Razorpay Payment Gateway Integration ────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════

@app.route("/api/payment/create-order", methods=["POST"])
def create_payment_order():
    try:
        data = request.get_json() or {}
        plan_id = data.get("plan_id")
        duration = data.get("duration", "1_year")
        email = data.get("email", "").strip().lower()
        company_id = data.get("company_id", "").strip()

        if not email and "user" in session and session["user"].get("email"):
            email = session["user"]["email"]
        if not company_id and "active_company_id" in session:
            company_id = session["active_company_id"]

        custom_amount = None
        signed_in = get_current_user() or {}
        payer = RegisteredUser.query.filter_by(email=signed_in.get('email')).first() if signed_in else None
        if payer and payer.email == email and payer.subscription_plan == plan_id:
            custom_amount = payer.custom_yearly_amount
        private_plan = bool(payer and payer.email == email and payer.subscription_plan == plan_id)
        if plan_id not in (*PUBLIC_PLANS, 'trial', 'lifetime_maintenance') and not private_plan:
            return jsonify(status='error', message='Choose a public plan or sign in to renew your assigned plan.'), 400
        if (plan_id in PUBLIC_PLANS or str(plan_id).startswith('custom_')) and duration not in ('1_year', '3_years'):
            return jsonify(status='error', message='Choose a 1- or 3-year term.'), 400
        if company_id:
            payer_company = Company.query.filter_by(company_id=company_id, owner_email=email).first()
            if not payer or payer.email != email or not payer_company:
                return jsonify(status='error', message='Company does not belong to the signed-in payer.'), 403

        trial_payer = RegisteredUser.query.filter_by(email=email, payment_status='trial').first()
        if trial_payer and trial_payer.subscription_plan in PUBLIC_PLANS and (not payer or payer.email != email):
            return jsonify(status='error', message='Sign in to continue your saved trial plan.'), 401
        if payer and payer.payment_status == 'trial' and payer.subscription_plan in PUBLIC_PLANS:
            # Trial conversion always uses the plan, term and amount saved at signup.
            if email != payer.email or plan_id != payer.subscription_plan or duration != payer.plan_duration:
                return jsonify(status='error', message='Use your saved trial plan and billing term.'), 400
            amount = float(payer.amount_total)
        else:
            amount = calculate_plan_price(plan_id, duration, custom_yearly_amount=custom_amount)
        if amount <= 0 and plan_id != "trial":
            return jsonify({"status": "error", "message": "Invalid amount for plan/duration or custom contact required."}), 400

        if plan_id == "trial":
            return jsonify({"status": "trial", "message": "14-Day Free Trial requires no payment."})

        amount_paise = int(amount * 100)
        tx_id = "TXN_" + secrets.token_hex(6).upper()

        order_payload = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": tx_id,
            "payment_capture": 1,
            "notes": {
                "plan_id": plan_id,
                "duration": duration,
                "email": email,
                "company_id": company_id
            }
        }
        rp_order = razorpay_client.order.create(data=order_payload)

        # Log PaymentTransaction in platform DB
        txn = PaymentTransaction(
            transaction_id=tx_id,
            user_email=email or (session.get("user", {}).get("email") if "user" in session else "guest@magnustic.com"),
            company_id=company_id if company_id else None,
            plan_id=plan_id,
            duration=duration,
            amount=amount,
            currency="INR",
            razorpay_order_id=rp_order["id"],
            status="created",
            created_at=datetime.utcnow()
        )
        db.session.add(txn)
        db.session.commit()

        return jsonify({
            "status": "success",
            "key_id": RAZORPAY_KEY_ID,
            "order_id": rp_order["id"],
            "amount": amount,
            "amount_paise": amount_paise,
            "currency": "INR",
            "transaction_id": tx_id
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/payment/verify", methods=["POST"])
def verify_payment():
    try:
        data = request.get_json() or {}
        razorpay_order_id = data.get("razorpay_order_id")
        razorpay_payment_id = data.get("razorpay_payment_id")
        razorpay_signature = data.get("razorpay_signature")
        transaction_id = data.get("transaction_id")
        plan_id = data.get("plan_id")
        duration = data.get("duration", "1_year")
        email = data.get("email", "").strip().lower()
        company_id = data.get("company_id", "").strip()

        if not (razorpay_order_id and razorpay_payment_id and razorpay_signature):
            return jsonify({"status": "error", "message": "Missing payment signature details."}), 400

        # Verify HMAC SHA256 signature
        msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
        generated_signature = hmac.new(
            RAZORPAY_KEY_SECRET.encode("utf-8"),
            msg,
            hashlib.sha256
        ).hexdigest()

        if generated_signature != razorpay_signature:
            if transaction_id:
                txn = PaymentTransaction.query.filter_by(transaction_id=transaction_id).first()
                if txn:
                    txn.status = "failed"
                    txn.error_reason = "Signature mismatch"
                    db.session.commit()
            return jsonify({"status": "error", "message": "Payment signature verification failed."}), 400

        # Update PaymentTransaction to success
        txn = None
        if transaction_id:
            txn = PaymentTransaction.query.filter_by(transaction_id=transaction_id).first()
        if not txn and razorpay_order_id:
            txn = PaymentTransaction.query.filter_by(razorpay_order_id=razorpay_order_id).first()

        if not txn or txn.razorpay_order_id != razorpay_order_id:
            return jsonify(status='error', message='Payment order not found.'), 400
        # Grant only the product and account recorded on the server-created order.
        plan_id, duration, email, company_id = txn.plan_id, txn.duration, txn.user_email, txn.company_id
        if txn:
            txn.razorpay_payment_id = razorpay_payment_id
            txn.razorpay_signature = razorpay_signature
            txn.status = "success"
            db.session.commit()

        # Calculate new validity
        plan_obj = SubscriptionPlan.query.get(plan_id)
        days = 365
        if duration == "3_years":
            days = 365 * 3
        elif duration == "lifetime":
            days = 365 * 100

        new_end_date = today_ist() + timedelta(days=days)

        # Update in-session user / owner if logged in
        if not email and "user" in session and session["user"].get("email"):
            email = session["user"]["email"]

        if plan_id == "lifetime_maintenance":
            session.pop("lifetime_maintenance_due", None)
            session.pop("maintenance_amount", None)
            next_maint_date = today_ist() + timedelta(days=365)
            if email:
                reg_user = RegisteredUser.query.filter_by(email=email).first()
                if reg_user:
                    reg_user.last_maintenance_paid_at = today_ist()
                    reg_user.maintenance_due_date = next_maint_date
                    if txn:
                        reg_user.amount_paid = float(reg_user.amount_paid or 0) + float(txn.amount or 0)
                    comps = Company.query.filter_by(owner_email=email).all()
                    for c in comps:
                        c.last_maintenance_paid_at = today_ist()
                        c.maintenance_due_date = next_maint_date
                    db.session.commit()
            elif company_id:
                comp = Company.query.filter_by(company_id=company_id).first()
                if comp:
                    comp.last_maintenance_paid_at = today_ist()
                    comp.maintenance_due_date = next_maint_date
                    db.session.commit()

            return jsonify({
                "status": "success",
                "message": "Annual Maintenance fee (₹2,500) paid successfully! Your lifetime ERP license is active.",
                "plan_id": plan_id,
                "duration": duration,
                "valid_until": next_maint_date.strftime("%Y-%m-%d")
            })

        if email:
            reg_user = RegisteredUser.query.filter_by(email=email).first()
            if reg_user:
                reg_user.subscription_plan = plan_id
                reg_user.plan_duration = duration
                reg_user.payment_status = "paid"
                if duration == "lifetime":
                    reg_user.maintenance_due_date = today_ist() + timedelta(days=365)
                    reg_user.last_maintenance_paid_at = today_ist()
                if txn:
                    reg_user.amount_paid = float(reg_user.amount_paid or 0) + float(txn.amount or 0)
                db.session.commit()

                # Update all companies owned by this owner
                comps = Company.query.filter_by(owner_email=email).all()
                for c in comps:
                    c.subscription_plan = plan_id
                    c.plan_duration = duration
                    c.subscription_start = today_ist()
                    c.subscription_end = new_end_date
                    if duration == "lifetime":
                        c.maintenance_due_date = today_ist() + timedelta(days=365)
                        c.last_maintenance_paid_at = today_ist()
                    if plan_obj:
                        c.max_companies_allowed = plan_obj.max_companies
                        c.max_users_per_company = plan_obj.max_users
                db.session.commit()

        elif company_id:
            comp = Company.query.filter_by(company_id=company_id).first()
            if comp:
                comp.subscription_plan = plan_id
                comp.plan_duration = duration
                comp.subscription_start = today_ist()
                comp.subscription_end = new_end_date
                if duration == "lifetime":
                    comp.maintenance_due_date = today_ist() + timedelta(days=365)
                    comp.last_maintenance_paid_at = today_ist()
                if plan_obj:
                    comp.max_companies_allowed = plan_obj.max_companies
                    comp.max_users_per_company = plan_obj.max_users
                db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Payment verified and subscription activated successfully!",
            "plan_id": plan_id,
            "duration": duration,
            "valid_until": new_end_date.strftime("%Y-%m-%d")
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # ── Pull owner / account fields ───────────────────────────────────────
        email            = request.form.get("email", "").strip().lower()
        password         = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        full_name        = request.form.get("full_name", "").strip()
        phone            = request.form.get("phone", "").strip()
        plan_key         = request.form.get("subscription_plan", "trial")
        billing_duration = request.form.get("billing_duration", "1_year")
        rzp_payment_id   = request.form.get("razorpay_payment_id", "").strip()
        rzp_order_id     = request.form.get("razorpay_order_id", "").strip()
        rzp_signature    = request.form.get("razorpay_signature", "").strip()
        awb_prefix = request.form.get("awb_prefix", "AHL").strip().upper() or "AHL"
        awb_start  = int(request.form.get("awb_start", 81000) or 81000)
        # ── Pull primary company fields ───────────────────────────────────────
        company_name     = request.form.get("company_name", "").strip()
        address          = request.form.get("address", request.form.get("company_address_1", "")).strip()
        company_phone    = request.form.get("company_phone_1", phone).strip()
        is_gst           = request.form.get("is_gst_registered", "1") in ("1", "true", "True", True)
        raw_tax_number   = (request.form.get('gst_number') or request.form.get('tax_registration_number') or '').strip()
        gst_number       = raw_tax_number if (is_gst and raw_tax_number) else None

        # ── Extra companies (from hidden JSON field) ──────────────────────────
        extra_companies_raw = request.form.get("extra_companies", "[]")
        try:
            extra_companies = json.loads(extra_companies_raw)
            if not isinstance(extra_companies, list):
                extra_companies = []
        except (ValueError, TypeError):
            extra_companies = []

        # ── Validations ───────────────────────────────────────────────────────
        if not email:
            flash("Email is required", "error")
            return redirect(url_for("register"))

        if RegisteredUser.query.filter_by(email=email).first():
            flash("An account with this email already exists", "error")
            return redirect(url_for("register"))

        if password != confirm_password:
            flash("Passwords do not match", "error")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must be at least 8 characters", "error")
            return redirect(url_for("register"))

        if not company_name:
            flash("Company name is required", "error")
            return redirect(url_for("register"))

        if plan_key not in PUBLIC_PLANS or billing_duration not in ('1_year', '3_years'):
            flash("Choose an available plan and billing duration.", "error")
            return redirect(url_for('register'))

        # ── Plan lookup ───────────────────────────────────────────────────────
        plan_obj = SubscriptionPlan.query.get(plan_key) or SubscriptionPlan.query.get("trial") or SubscriptionPlan.query.order_by(SubscriptionPlan.id).first()
        if not plan_obj:
            flash("No subscription plans are configured. Contact support.", "error")
            return redirect(url_for("register"))

        # Determine validity days and payment status
        paid_txn = PaymentTransaction.query.filter_by(razorpay_order_id=rzp_order_id,
            razorpay_payment_id=rzp_payment_id, user_email=email, plan_id=plan_key,
            duration=billing_duration, status='success').first() if rzp_payment_id else None
        is_paid = bool(paid_txn)
        if plan_key == "trial" or not is_paid:
            end_days = 14
            payment_status = "trial"
            amount_paid = 0
        else:
            payment_status = "paid"
            if billing_duration == "3_years":
                end_days = 365 * 3
            elif billing_duration == "lifetime":
                end_days = 365 * 100
            else:
                end_days = 365
            amount_paid = calculate_plan_price(plan_key, billing_duration)

        # ── Check extra companies don't exceed plan limit ─────────────────────
        max_c = plan_obj.max_companies
        try:
            max_c_int = int(max_c)
            total_requested = 1 + len(extra_companies)
            if total_requested > max_c_int:
                flash(
                    f"Your {plan_obj.name} allows up to {max_c_int} "
                    f"{'company' if max_c_int == 1 else 'companies'}. "
                    f"You requested {total_requested}.",
                    "error"
                )
                return redirect(url_for("register"))
        except (ValueError, TypeError):
            pass  # "Unlimited" — no cap

        # ── Create RegisteredUser (platform DB) ───────────────────────────────
        user_id = generate_next_user_id()

        new_user = RegisteredUser(
            user_id=user_id,
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            phone=phone,
            role="owner",
            subscription_plan=plan_obj.id,
            plan_duration=billing_duration,
            must_change_password=False,
            email_verified=False,
            maintenance_due_date=(today_ist() + timedelta(days=365)) if (is_paid and billing_duration == "lifetime") else None,
            last_maintenance_paid_at=today_ist() if (is_paid and billing_duration == "lifetime") else None,
            created_at=today_ist(),
            is_active=True,
            payment_status=payment_status,
            amount_paid=amount_paid,
            amount_total=calculate_plan_price(plan_key, billing_duration),
        )
        db.session.add(new_user)
        db.session.flush()  # get id without committing

        # ── Helper: create one Company record + its customer DB ───────────────
        def _create_company(c_name, c_address, c_phone, c_gst_registered, c_gst_number, c_awb_prefix="AHL", c_awb_start=81000, tax_data=None):
            if is_company_name_taken(email, c_name):
                raise ValueError(f"Company name '{c_name}' is already taken. Please choose a different name.")
            
            # ── Check if Tax / GST number is already used by ANY company ──
            if c_gst_number and is_gst_number_taken(c_gst_number):
                raise ValueError(f"Tax registration number '{c_gst_number}' is already registered to another active company. Please check and try again.")
            c_id       = _next_numbered_id(db.session, Company.company_id, "QIY_")

            company = Company(
                company_id=c_id,
                company_name=c_name,
                owner_email=email,
                subscription_plan=plan_obj.id,
                plan_duration=billing_duration,
                subscription_start=today_ist(),
                subscription_end=today_ist() + timedelta(days=end_days),
                maintenance_due_date=(today_ist() + timedelta(days=365)) if (is_paid and billing_duration == "lifetime") else None,
                last_maintenance_paid_at=today_ist() if (is_paid and billing_duration == "lifetime") else None,
                max_companies_allowed=plan_obj.max_companies,
                max_users_per_company=plan_obj.max_users,
                address=c_address,
                phone=c_phone or phone,
                gst_number = c_gst_number if c_gst_registered else None,
                is_gst_registered=c_gst_registered,
                created_at=today_ist(),
                is_active=True,
                storage_type="cloud",
                awb_prefix=c_awb_prefix,
                awb_start=c_awb_start,
            )
            apply_company_tax(company, tax_data or request.form)
            db.session.add(company)
            db.session.flush()  # make company_id available before commit

            return c_id

        # ── Create primary company ─────────────────────────────────────────────
        try:
            primary_company_id = _create_company(
                company_name, address, company_phone, is_gst, gst_number,
                awb_prefix, awb_start
            )
        except ValueError as e:
            flash(str(e), "error")
            return redirect(url_for("register"))

        # ── Create extra companies ────────────────────────────────────────────
        extra_company_ids = []
        for ec in extra_companies:
            ec_name = ec.get("name", "").strip()
            if not ec_name:
                continue
            try:
                ec_is_reg = bool(ec.get("is_gst_registered", True))
                ec_tax_num = (ec.get("gst_number") or ec.get("tax_registration_number") or "").strip()
                ec_id = _create_company(
                    ec_name,
                    ec.get("address", ""),
                    ec.get("phone", ""),
                    ec_is_reg,
                    ec_tax_num if ec_is_reg else None,
                    (ec.get("awb_prefix", "") or "AHL").strip().upper() or "AHL",
                    int(ec.get("awb_start", 81000) or 81000),
                    tax_data=ec,
                )
                extra_company_ids.append(ec_id)
            except ValueError as e:
                flash(str(e), "error")
                return redirect(url_for("register"))

        # ── Commit all platform records at once ───────────────────────────────
        db.session.commit()

        # ── Bootstrap customer databases ──────────────────────────────────────
        all_company_ids = [primary_company_id] + extra_company_ids

        for c_id in all_company_ids:
            try:
                company_obj = Company.query.filter_by(company_id=c_id).first()
                init_customer_db_for_company(company_obj)
            except Exception as e:
                print(f"⚠  Could not init customer DB for {c_id}: {e}")

        # ── Create owner as CompanyUser in primary company's DB ───────────────
        try:
            cdb       = get_customer_session(primary_company_id)
            emp_id    = _next_numbered_id(cdb, CompanyUser.user_id, "EMP")

            new_emp = CompanyUser(
                user_id=emp_id,
                company_id=primary_company_id,
                email=email,
                password_hash=hash_password(password),
                full_name=full_name,
                role="owner",
                department="Management",
                phone=phone,
                is_active=True,
                created_at=today_ist(),
            )
            cdb.add(new_emp)
            cdb.commit()
        except Exception as e:
            cdb.rollback()
            print(f"⚠  Could not create CompanyUser for {primary_company_id}: {e}")

        # ── Also add owner as CompanyUser in any extra company DBs ────────────
        for c_id in extra_company_ids:
            try:
                cdb       = get_customer_session(c_id)
                emp_id    = _next_numbered_id(cdb, CompanyUser.user_id, "EMP")
                extra_emp = CompanyUser(
                    user_id=emp_id,
                    company_id=c_id,
                    email=email,
                    password_hash=hash_password(password),
                    full_name=full_name,
                    role="owner",
                    department="Management",
                    phone=phone,
                    is_active=True,
                    created_at=today_ist(),
                )
                cdb.add(extra_emp)
                cdb.commit()
            except Exception as e:
                cdb.rollback()
                print(f"⚠  Could not create CompanyUser for {c_id}: {e}")

        total = len(all_company_ids)
        _generate_and_send_otp(email)
        flash(
            f"Registration successful! A 6-digit verification code has been sent to {email}.",
            "success"
        )
        return redirect(url_for("verify_otp"))

    return render_template("register.html", plans=get_all_plans())

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─────────────────────────────────────────────────────────────────────────────
# ── Dashboard ─────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────


def _ensure_export_history_table(cdb):
    """Create the export_history table in the company DB if it doesn't exist yet."""
    cdb.execute(text("""
        CREATE TABLE IF NOT EXISTS export_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            company_id VARCHAR(64) NOT NULL,
            export_type VARCHAR(20) NOT NULL,
            sales_from DATE NULL,
            sales_to DATE NULL,
            purchase_from DATE NULL,
            purchase_to DATE NULL,
            filename VARCHAR(255) NOT NULL,
            exported_by VARCHAR(255) NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """))
    cdb.commit()


def _log_export_history(cdb, company_id, export_type, sales_from_date, sales_to_date,
                         purchase_from_date, purchase_to_date, filename, exported_by):
    try:
        _ensure_export_history_table(cdb)
        cdb.execute(
            text("""
                INSERT INTO export_history
                    (company_id, export_type, sales_from, sales_to, purchase_from, purchase_to, filename, exported_by)
                VALUES
                    (:company_id, :export_type, :sales_from, :sales_to, :purchase_from, :purchase_to, :filename, :exported_by)
            """),
            {
                "company_id": company_id,
                "export_type": export_type,
                "sales_from": sales_from_date,
                "sales_to": sales_to_date,
                "purchase_from": purchase_from_date,
                "purchase_to": purchase_to_date,
                "filename": filename,
                "exported_by": exported_by,
            },
        )
        cdb.commit()
    except Exception as e:
        # Never let history logging break the actual export/download.
        print(f"Could not log export history: {e}")
        cdb.rollback()


def _get_export_history(cdb, company_id, limit=15):
    try:
        _ensure_export_history_table(cdb)
        rows = cdb.execute(
            text("""
                SELECT export_type, sales_from, sales_to, purchase_from, purchase_to,
                       filename, exported_by, created_at
                FROM export_history
                WHERE company_id = :company_id
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"company_id": company_id, "limit": limit},
        ).mappings().all()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Could not load export history: {e}")
        return []


@app.route("/reports/export-selector")
@login_required
@require_permission("analytics", "view")
def export_selector():
    """
    Standalone page for picking a date range and metric (sales / purchase /
    both) before exporting. Independent of reports_dashboard() / 
    report_dashboard.html — this only feeds query params into the existing
    export_reports_excel() route below via a plain GET form.
    """
    company_id = get_current_company()
    company = get_company_by_id(company_id)
    if not company:
        flash("Company not found")
        return redirect(url_for("logout"))

    cdb = get_cdb()
    history = _get_export_history(cdb, company_id) if cdb else []

    default_from = today_ist().replace(day=1).strftime("%Y-%m-%d")
    default_to = today_ist().strftime("%Y-%m-%d")

    return render_template(
        "export_selector.html",
        active="export_selector",
        company=company,
        default_from=default_from,
        default_to=default_to,
        history=history,
    )


@app.route("/reports/export-excel")
@login_required
@require_permission("analytics", "view")
def export_reports_excel():
    """
    Export Sales, Purchase, and Pending (receivables + payables) to a single
    multi-sheet Excel file. Pending is computed from Invoice.balance /
    PurchaseInvoice.balance directly rather than the cached Client.pending /
    Supplier.payable fields, so the export always matches what the individual
    invoices actually say — no risk of it drifting from a stale cache field.
    Pending Receivable/Payable are filtered by invoice date using the same
    Sales/Purchase date range as the rest of the export (by choice — an
    unpaid invoice outside the selected range won't appear, even though it
    may still be owed today).

    Query params:
      - sales_from / sales_to: date range for Sales
      - purchase_from / purchase_to: date range for Purchase
      - type: 'sales', 'purchase', or 'both' (default: 'both')
      - from / to: legacy fallback (applies to both)
    """
    company_id = get_current_company()
    company = get_company_by_id(company_id)
    if not company:
        flash("Company not found")
        return redirect(url_for("logout"))

    cdb = get_cdb()
    if not cdb:
        flash("Could not connect to company database")
        return redirect(url_for("logout"))

    # ── Parse export type ────────────────────────────────────────────────────────
    export_type = request.args.get("type", "both").strip().lower()
    if export_type not in ("sales", "purchase", "both"):
        export_type = "both"

    # ── Parse Sales date range ──────────────────────────────────────────────────
    sales_from_str = request.args.get("sales_from", request.args.get("from", "")).strip()
    sales_to_str = request.args.get("sales_to", request.args.get("to", "")).strip()

    date_parse_warnings = []

    try:
        sales_from_date = datetime.strptime(sales_from_str, "%Y-%m-%d").date() if sales_from_str else None
    except ValueError:
        sales_from_date = None
        date_parse_warnings.append(f"Sales 'from' date '{sales_from_str}' was not understood and was ignored.")
    try:
        sales_to_date = datetime.strptime(sales_to_str, "%Y-%m-%d").date() if sales_to_str else None
    except ValueError:
        sales_to_date = None
        date_parse_warnings.append(f"Sales 'to' date '{sales_to_str}' was not understood and was ignored.")

    # ── Parse Purchase date range ────────────────────────────────────────────────
    purchase_from_str = request.args.get("purchase_from", request.args.get("from", "")).strip()
    purchase_to_str = request.args.get("purchase_to", request.args.get("to", "")).strip()

    try:
        purchase_from_date = datetime.strptime(purchase_from_str, "%Y-%m-%d").date() if purchase_from_str else None
    except ValueError:
        purchase_from_date = None
        date_parse_warnings.append(f"Purchase 'from' date '{purchase_from_str}' was not understood and was ignored.")
    try:
        purchase_to_date = datetime.strptime(purchase_to_str, "%Y-%m-%d").date() if purchase_to_str else None
    except ValueError:
        purchase_to_date = None
        date_parse_warnings.append(f"Purchase 'to' date '{purchase_to_str}' was not understood and was ignored.")

    if date_parse_warnings:
        flash(
            "Some date filters couldn't be applied, so those sheets were exported unfiltered: "
            + " ".join(date_parse_warnings),
            "error",
        )

    # ── Legacy fallback: if no sales-specific dates, use from/to ───────────────
    legacy_from_str = request.args.get("from", "").strip()
    legacy_to_str = request.args.get("to", "").strip()
    if sales_from_date is None and sales_to_date is None and (legacy_from_str or legacy_to_str):
        try:
            sales_from_date = datetime.strptime(legacy_from_str, "%Y-%m-%d").date() if legacy_from_str else None
        except ValueError:
            pass
        try:
            sales_to_date = datetime.strptime(legacy_to_str, "%Y-%m-%d").date() if legacy_to_str else None
        except ValueError:
            pass
    if purchase_from_date is None and purchase_to_date is None and (legacy_from_str or legacy_to_str):
        try:
            purchase_from_date = datetime.strptime(legacy_from_str, "%Y-%m-%d").date() if legacy_from_str else None
        except ValueError:
            pass
        try:
            purchase_to_date = datetime.strptime(legacy_to_str, "%Y-%m-%d").date() if legacy_to_str else None
        except ValueError:
            pass

    # ── Helper: apply date filters to a query ──────────────────────────────────
    def apply_date_filters(query, date_column, from_date, to_date):
        if from_date:
            query = query.filter(date_column >= from_date)
        if to_date:
            query = query.filter(date_column <= to_date)
        return query

    # ── Sales ────────────────────────────────────────────────────────────────────
    sales_rows = []
    sales_df = None
    if export_type in ("sales", "both"):
        ci_q = cdb.query(CustomerInvoice).filter(CustomerInvoice.company_id == company_id)
        ci_q = apply_date_filters(ci_q, CustomerInvoice.invoice_date, sales_from_date, sales_to_date)
        ci_invoices = ci_q.order_by(CustomerInvoice.invoice_date.asc()).all()

        sales_q = cdb.query(Invoice).filter(Invoice.company_id == company_id)
        sales_q = apply_date_filters(sales_q, Invoice.date, sales_from_date, sales_to_date)
        sales_invoices = sales_q.order_by(Invoice.date.asc()).all()

        clients_by_id = {c.id: c for c in cdb.query(Client).filter_by(company_id=company_id).all()}

        for ci in ci_invoices:
            client = clients_by_id.get(ci.client_id) if ci.client_id else None
            cust_name = ci.client_name or (client.name if client else "Walk-in Customer")
            phone = client.phone if client else ""
            category_label = "Product Sales" if ci.invoice_category == "product_sale" else "Workshop Repair" if ci.invoice_category == "workshop_repair" else (ci.invoice_category or "Direct Sales").replace('_', ' ').title()
            
            subtotal = float(ci.subtotal or 0)
            tax_amount = float(ci.tax_amount or 0)
            grand_total = float(ci.grand_total or 0)
            paid_amount = float(ci.paid_amount or 0)
            balance = float(ci.balance if ci.balance is not None else (grand_total - paid_amount))
            
            sales_rows.append({
                "Invoice No":   ci.invoice_number,
                "Category":     category_label,
                "Date":         ci.invoice_date.strftime("%Y-%m-%d") if ci.invoice_date else "",
                "Due Date":     ci.due_date.strftime("%Y-%m-%d") if ci.due_date else "",
                "Client":       cust_name,
                "Phone":        phone,
                "Subtotal":     round(subtotal, 2),
                "Tax":          round(tax_amount, 2),
                "Grand Total":  round(grand_total, 2),
                "Paid":         round(paid_amount, 2),
                "Balance":      round(balance, 2),
                "Status":       ci.status or "Pending",
            })

        for inv in sales_invoices:
            client = clients_by_id.get(inv.client_id)
            subtotal = float(inv.subtotal or 0)
            tax_amount = float(inv.tax_amount or 0)
            grand_total = float(inv.grand_total or 0)
            paid_amount = float(inv.paid_amount or 0)
            balance = float(getattr(inv, 'balance', 0) or (grand_total - paid_amount))
            
            sales_rows.append({
                "Invoice No":   inv.invoice_id,
                "Category":     "General",
                "Date":         inv.date.strftime("%Y-%m-%d") if inv.date else "",
                "Due Date":     inv.due_date.strftime("%Y-%m-%d") if inv.due_date else "",
                "Client":       client.name if client else (inv.contact_person or "—"),
                "Phone":        client.phone if client else (inv.phone or ""),
                "Subtotal":     round(subtotal, 2),
                "Tax":          round(tax_amount, 2),
                "Grand Total":  round(grand_total, 2),
                "Paid":         round(paid_amount, 2),
                "Balance":      round(balance, 2),
                "Status":       inv.status or "Pending",
            })
        sales_df = pd.DataFrame(sales_rows, columns=[
            "Invoice No", "Category", "Date", "Due Date", "Client", "Phone",
            "Subtotal", "Tax", "Grand Total", "Paid", "Balance", "Status",
        ])

    # ── Purchase ─────────────────────────────────────────────────────────────────
    purchase_rows = []
    purchase_df = None
    if export_type in ("purchase", "both"):
        purchase_q = cdb.query(PurchaseInvoice).filter(PurchaseInvoice.company_id == company_id)
        purchase_q = apply_date_filters(purchase_q, PurchaseInvoice.date, purchase_from_date, purchase_to_date)
        purchase_invoices = purchase_q.order_by(PurchaseInvoice.date.asc()).all()

        suppliers_by_id = {s.id: s for s in cdb.query(Supplier).filter_by(company_id=company_id).all()}

        for pur in purchase_invoices:
            supplier = suppliers_by_id.get(pur.supplier_id)
            purchase_rows.append({
                "Invoice No":       pur.invoice_id,
                "Supplier Invoice #": pur.invoice_number or "",
                "Date":             pur.date.strftime("%Y-%m-%d") if pur.date else "",
                "Due Date":         pur.due_date.strftime("%Y-%m-%d") if pur.due_date else "",
                "Supplier":         supplier.name if supplier else (pur.supplier_name or "—"),
                "Phone":            supplier.phone if supplier else "",
                "Subtotal":         round(float(pur.subtotal or 0), 2),
                "Tax":              round(float(pur.tax_amount or 0), 2),
                "Grand Total":      round(float(pur.grand_total or 0), 2),
                "Paid":             round(float(pur.paid_amount or 0), 2),
                "Balance":          round(float(pur.balance or 0), 2),
                "Status":           pur.status,
            })
        purchase_df = pd.DataFrame(purchase_rows, columns=[
            "Invoice No", "Supplier Invoice #", "Date", "Due Date", "Supplier", "Phone",
            "Subtotal", "Tax", "Grand Total", "Paid", "Balance", "Status",
        ])

    # ── Pending: Receivables (unpaid/partial sales) ─────────────────────────
    # Filtered by invoice date, same range as the Sales sheet (sales_from_date/
    # sales_to_date) — this is a deliberate choice: it means an unpaid invoice
    # from outside the selected range will NOT show up here even though it's
    # still owed today. If you want total outstanding exposure regardless of
    # period, remove this date filter and query all unpaid invoices instead.
    receivable_rows = []
    receivable_df = None
    if export_type in ("sales", "both"):
        receivable_q = cdb.query(Invoice).filter(Invoice.company_id == company_id)
        receivable_q = apply_date_filters(receivable_q, Invoice.date, sales_from_date, sales_to_date)
        all_sales = receivable_q.all()
        clients_by_id = {c.id: c for c in cdb.query(Client).filter_by(company_id=company_id).all()}
        for inv in all_sales:
            bal = round(float(inv.balance or 0), 2)
            if bal > 0:
                client = clients_by_id.get(inv.client_id)
                receivable_rows.append({
                    "Invoice No":  inv.invoice_id,
                    "Date":        inv.date.strftime("%Y-%m-%d") if inv.date else "",
                    "Client":      client.name if client else (inv.contact_person or "—"),
                    "Phone":       client.phone if client else (inv.phone or ""),
                    "Grand Total": round(float(inv.grand_total or 0), 2),
                    "Paid":        round(float(inv.paid_amount or 0), 2),
                    "Balance Due": bal,
                })
        receivable_df = pd.DataFrame(receivable_rows, columns=[
            "Invoice No", "Date", "Client", "Phone", "Grand Total", "Paid", "Balance Due",
        ])
        total_receivable = round(sum(r["Balance Due"] for r in receivable_rows), 2)
    else:
        total_receivable = 0

    # ── Pending: Payables (unpaid/partial purchases) ────────────────────────
    # Filtered by invoice date, same range as the Purchase sheet — see the
    # note above Pending: Receivables for the tradeoff this implies.
    payable_rows = []
    payable_df = None
    if export_type in ("purchase", "both"):
        payable_q = cdb.query(PurchaseInvoice).filter(PurchaseInvoice.company_id == company_id)
        payable_q = apply_date_filters(payable_q, PurchaseInvoice.date, purchase_from_date, purchase_to_date)
        all_purchases = payable_q.all()
        suppliers_by_id = {s.id: s for s in cdb.query(Supplier).filter_by(company_id=company_id).all()}
        for pur in all_purchases:
            bal = round(float(pur.balance or 0), 2)
            if bal > 0:
                supplier = suppliers_by_id.get(pur.supplier_id)
                payable_rows.append({
                    "Invoice No":  pur.invoice_id,
                    "Date":        pur.date.strftime("%Y-%m-%d") if pur.date else "",
                    "Supplier":    supplier.name if supplier else (pur.supplier_name or "—"),
                    "Phone":       supplier.phone if supplier else "",
                    "Grand Total": round(float(pur.grand_total or 0), 2),
                    "Paid":        round(float(pur.paid_amount or 0), 2),
                    "Balance Due": bal,
                })
        payable_df = pd.DataFrame(payable_rows, columns=[
            "Invoice No", "Date", "Supplier", "Phone", "Grand Total", "Paid", "Balance Due",
        ])
        total_payable = round(sum(p["Balance Due"] for p in payable_rows), 2)
    else:
        total_payable = 0

    # ── Write workbook ───────────────────────────────────────────────────────
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # Sales sheet
        if sales_df is not None and not sales_df.empty:
            sales_df.to_excel(writer, sheet_name="Sales", index=False)
        elif sales_df is not None:
            # Empty sheet with headers
            sales_df.to_excel(writer, sheet_name="Sales", index=False)

        # Purchase sheet
        if purchase_df is not None and not purchase_df.empty:
            purchase_df.to_excel(writer, sheet_name="Purchase", index=False)
        elif purchase_df is not None:
            purchase_df.to_excel(writer, sheet_name="Purchase", index=False)

        # Pending sheets
        if receivable_df is not None and not receivable_df.empty:
            receivable_df.to_excel(writer, sheet_name="Pending - Receivable", index=False)
        elif receivable_df is not None:
            receivable_df.to_excel(writer, sheet_name="Pending - Receivable", index=False)

        if payable_df is not None and not payable_df.empty:
            payable_df.to_excel(writer, sheet_name="Pending - Payable", index=False)
        elif payable_df is not None:
            payable_df.to_excel(writer, sheet_name="Pending - Payable", index=False)

        from openpyxl.styles import Font, PatternFill

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")

        # Apply formatting to all sheets
        sheet_df_map = {
            "Sales": sales_df,
            "Purchase": purchase_df,
            "Pending - Receivable": receivable_df,
            "Pending - Payable": payable_df,
        }

        for sheet_name, df in sheet_df_map.items():
            if df is None or sheet_name not in writer.sheets:
                continue
            ws = writer.sheets[sheet_name]
            # Only apply header formatting if there's at least one row
            if not df.empty:
                for col_idx, col_name in enumerate(df.columns, start=1):
                    cell = ws.cell(row=1, column=col_idx)
                    cell.font = header_font
                    cell.fill = header_fill
                    max_len = max([len(str(col_name))] + [len(str(v)) for v in df[col_name].astype(str)]) if len(df) else len(str(col_name))
                    ws.column_dimensions[cell.column_letter].width = min(max(max_len + 3, 12), 40)
                ws.freeze_panes = "A2"

        # Totals row under each pending sheet
        if "Pending - Receivable" in writer.sheets and receivable_df is not None:
            rec_ws = writer.sheets["Pending - Receivable"]
            rec_total_row = len(receivable_df) + 3
            rec_ws.cell(row=rec_total_row, column=6, value="Total Receivable:").font = Font(bold=True)
            rec_ws.cell(row=rec_total_row, column=7, value=total_receivable).font = Font(bold=True)

        if "Pending - Payable" in writer.sheets and payable_df is not None:
            pay_ws = writer.sheets["Pending - Payable"]
            pay_total_row = len(payable_df) + 3
            pay_ws.cell(row=pay_total_row, column=6, value="Total Payable:").font = Font(bold=True)
            pay_ws.cell(row=pay_total_row, column=7, value=total_payable).font = Font(bold=True)

    buf.seek(0)

    # ── Build filename ──────────────────────────────────────────────────────
    # Show date ranges in filename
    parts = []
    if export_type in ("sales", "both") and (sales_from_date or sales_to_date):
        from_str = sales_from_date.strftime("%Y%m%d") if sales_from_date else "start"
        to_str = sales_to_date.strftime("%Y%m%d") if sales_to_date else "end"
        parts.append(f"Sales_{from_str}-{to_str}")
    if export_type in ("purchase", "both") and (purchase_from_date or purchase_to_date):
        from_str = purchase_from_date.strftime("%Y%m%d") if purchase_from_date else "start"
        to_str = purchase_to_date.strftime("%Y%m%d") if purchase_to_date else "end"
        parts.append(f"Purchase_{from_str}-{to_str}")

    suffix = "_".join(parts) if parts else "all_time"
    filename = f"{company.company_name.replace(' ', '_')}_{export_type.title()}_{suffix}.xlsx"

    _log_export_history(
        cdb, company_id, export_type,
        sales_from_date, sales_to_date,
        purchase_from_date, purchase_to_date,
        filename, get_current_user().get("email"),
    )

    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/reports-dashboard")
@login_required
@require_permission("analytics", "view")
def reports_dashboard():
    
    company_id = get_current_company()
    company = get_company_by_id(company_id)
    
    if not company:
        flash("Company not found")
        return redirect(url_for("logout"))
    
    cdb = get_cdb()
    if not cdb:
        flash("Could not connect to company database")
        return redirect(url_for("logout"))
    
    # Set default dates (current month)
    from_date = today_ist().replace(day=1)
    to_date = today_ist()
    
    # Get initial data for the template
    # Cash in Hand
    cash_transactions = cdb.query(CashTransaction).filter_by(company_id=company_id).all()
    cash_balance = sum(t.amount for t in cash_transactions if t.type == 'income') - \
                   sum(t.amount for t in cash_transactions if t.type == 'expense')
    
    # Bank Balance
    bank_accounts = cdb.query(BankAccount).filter_by(company_id=company_id, status='Active').all()
    bank_balance = sum(acc.balance for acc in bank_accounts)
    
    # Total Revenue (current month)
    sales_ci = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.invoice_date >= from_date,
        CustomerInvoice.invoice_date <= to_date,
        CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft'])
    ).all()
    sales_invoices = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.date >= from_date,
        Invoice.date <= to_date,
        Invoice.status.notin_(['Cancelled', 'Void', 'Draft'])
    ).all()
    total_revenue = sum(float(inv.grand_total or 0) for inv in sales_ci) + sum(float(inv.grand_total or 0) for inv in sales_invoices)
    
    # Total Purchases (current month)
    purchase_invoices = cdb.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.date >= from_date,
        PurchaseInvoice.date <= to_date
    ).all()
    total_purchases = sum(float(pur.grand_total or 0) for pur in purchase_invoices)
    
    # Profit
    profit = total_revenue - total_purchases
    
    # Pending Amount
    all_ci = cdb.query(CustomerInvoice).filter_by(company_id=company_id).all()
    all_invoices = cdb.query(Invoice).filter_by(company_id=company_id).all()
    pending_amount = _total_outstanding(cdb, company_id)
    
    # Cash flow for period
    period_cash_income = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        CashTransaction.type == 'income',
        CashTransaction.date >= from_date,
        CashTransaction.date <= to_date
    ).all()
    period_cash_expense = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        CashTransaction.type == 'expense',
        CashTransaction.date >= from_date,
        CashTransaction.date <= to_date
    ).all()
    cash_inflow_period = sum(t.amount for t in period_cash_income)
    cash_outflow_period = sum(t.amount for t in period_cash_expense)
    cash_net_period = cash_inflow_period - cash_outflow_period
    
    # Chart Data (Last 6 months)
    chart_labels = []
    revenue_data = []
    purchase_data = []
    profit_trend = []
    profit_labels = []
    
    for i in range(5, -1, -1):
        month_date = today_ist().replace(day=1) - timedelta(days=30 * i)
        month_start = month_date.replace(day=1)
        if month_date.month == 12:
            month_end = month_date.replace(day=31)
        else:
            month_end = month_date.replace(month=month_date.month + 1, day=1) - timedelta(days=1)
        
        month_label = month_date.strftime('%b %Y')
        chart_labels.append(month_label)
        
        month_revenue_ci = sum(
            float(inv.grand_total or 0) for inv in cdb.query(CustomerInvoice).filter(
                CustomerInvoice.company_id == company_id,
                CustomerInvoice.invoice_date >= month_start,
                CustomerInvoice.invoice_date <= month_end,
                CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft'])
            ).all()
        )
        month_revenue_legacy = sum(
            float(inv.grand_total or 0) for inv in cdb.query(Invoice).filter(
                Invoice.company_id == company_id,
                Invoice.date >= month_start,
                Invoice.date <= month_end,
                Invoice.status.notin_(['Cancelled', 'Void', 'Draft'])
            ).all()
        )
        month_revenue = month_revenue_ci + month_revenue_legacy
        revenue_data.append(month_revenue / 100000)

        month_purchases = sum(
            float(pur.grand_total or 0) for pur in cdb.query(PurchaseInvoice).filter(
                PurchaseInvoice.company_id == company_id,
                PurchaseInvoice.date >= month_start,
                PurchaseInvoice.date <= month_end
            ).all()
        )
        purchase_data.append(month_purchases / 100000)

        month_profit = month_revenue - month_purchases
        profit_trend.append(month_profit / 1000)
        profit_labels.append(month_label)
    
    # Status counts for all customer invoices
    unified_all_invoices = []
    for ci in all_ci:
        st = ci.status or 'Pending'
        unified_all_invoices.append({
            "id": ci.invoice_number,
            "date": ci.invoice_date,
            "due_date": ci.due_date,
            "customer": ci.client_name or (ci.client_obj.name if ci.client_obj else "Direct Customer"),
            "destination": ci.client_state or (ci.invoice_category.replace('_', ' ').title() if ci.invoice_category else "Direct"),
            "total": float(ci.grand_total or 0),
            "balance": float(ci.balance if ci.balance is not None else (float(ci.grand_total or 0) - float(ci.paid_amount or 0))),
            "status": st
        })
    for inv in all_invoices:
        st = inv.status or 'Pending'
        meta = {}
        if inv.terms:
            try:
                meta = json.loads(inv.terms)
            except Exception:
                pass
        unified_all_invoices.append({
            "id": inv.invoice_id,
            "date": inv.date,
            "due_date": inv.due_date,
            "customer": inv.client_obj.name if inv.client_obj else (inv.contact_person or "—"),
            "destination": meta.get("destination", "Domestic"),
            "total": float(inv.grand_total or 0),
            "balance": float(getattr(inv, 'balance', 0) or 0),
            "status": st
        })

    status_counts = {
        "delivered": sum(1 for i in unified_all_invoices if i["status"].lower() == "paid"),
        "in_transit": sum(1 for i in unified_all_invoices if i["status"].lower() in ["partial", "partially paid", "partially_paid"]),
        "pending": sum(1 for i in unified_all_invoices if i["status"].lower() not in ["paid", "partial", "partially paid", "partially_paid", "draft", "void", "cancelled"]),
        "draft": sum(1 for i in unified_all_invoices if i["status"].lower() == "draft"),
        "total": len(unified_all_invoices)
    }
    
    # Payment methods breakdown
    cash_txns = cdb.query(CashTransaction).filter_by(company_id=company_id, type='income').all()
    bank_txns = cdb.query(BankTransaction).filter_by(company_id=company_id, type='credit').all()
    
    payment_methods = {
        "Cash": sum(t.amount for t in cash_txns),
        "Online/UPI": sum(t.amount for t in bank_txns if t.transaction_mode == "Online"),
        "Cheque": sum(t.amount for t in bank_txns if t.transaction_mode == "Cheque"),
    }
    
    # Top clients
    clients = cdb.query(Client).filter_by(company_id=company_id).all()
    top_clients_data = []
    for client in clients[:15]:
        c_ci = cdb.query(CustomerInvoice).filter(
            CustomerInvoice.company_id == company_id,
            CustomerInvoice.client_id == client.id,
            CustomerInvoice.status.notin_(['Void', 'Cancelled', 'Draft'])
        ).all()
        c_legacy = cdb.query(Invoice).filter(
            Invoice.company_id == company_id,
            Invoice.client_id == client.id,
            Invoice.status.notin_(['Void', 'Cancelled', 'Draft'])
        ).all()
        total_billed = sum(float(inv.grand_total or 0) for inv in c_ci) + sum(float(inv.grand_total or 0) for inv in c_legacy)
        pending = _client_outstanding(cdb, company_id, client)
        top_clients_data.append({
            "name": client.name,
            "total_billed": total_billed,
            "pending": pending,
            "shipment_count": len(c_ci) + len(c_legacy)
        })
    top_clients_data.sort(key=lambda x: x["total_billed"], reverse=True)
    top_clients_data = top_clients_data[:5]
    
    # Recent shipments/invoices (last 10)
    unified_all_invoices.sort(key=lambda x: x["date"] if x["date"] else date.min, reverse=True)
    recent_shipments = []
    for inv in unified_all_invoices[:10]:
        st_lower = inv["status"].lower()
        status_label = "Paid" if st_lower == "paid" else "Partial" if st_lower in ["partial", "partially paid", "partially_paid"] else "Draft" if st_lower == "draft" else "Pending"
        status_class = "delivered" if st_lower == "paid" else "transit" if st_lower in ["partial", "partially paid", "partially_paid"] else "pending"
        recent_shipments.append({
            "docket_no": inv["id"],
            "customer_name": inv["customer"],
            "destination": inv["destination"],
            "total": inv["total"],
            "status": inv["status"],
            "status_label": status_label,
            "status_class": status_class
        })
    
    # Recent payments
    recent_payments = []
    for txn in cash_txns[:10]:
        recent_payments.append({
            "date": txn.date.strftime("%d %b %Y"),
            "customer": txn.description[:30],
            "invoice_id": txn.reference or "—",
            "amount": txn.amount,
            "mode": "Cash"
        })
    for txn in bank_txns[:5]:
        recent_payments.append({
            "date": txn.date.strftime("%d %b %Y"),
            "customer": txn.description[:30],
            "invoice_id": txn.reference or "—",
            "amount": txn.amount,
            "mode": txn.transaction_mode or "Bank"
        })
    recent_payments.sort(key=lambda x: x['date'], reverse=True)
    recent_payments = recent_payments[:10]
    
    # Pending invoices
    pending_invoices = []
    for inv in unified_all_invoices:
        if inv["balance"] > 0:
            pending_invoices.append({
                "invoice_id": inv["id"],
                "customer": inv["customer"],
                "date": inv["date"].strftime("%d %b %Y") if inv["date"] else "—",
                "due_date": inv["due_date"].strftime("%d %b %Y") if inv["due_date"] else "—",
                "balance": inv["balance"]
            })
    pending_invoices = pending_invoices[:10]
    
    kpi = {
        "cash_balance": cash_balance,
        "bank_balance": bank_balance,
        "total_revenue": total_revenue,
        "total_purchases": total_purchases,
        "profit": profit,
        "pending_amount": pending_amount,
        "cash_inflow_period": cash_inflow_period,
        "cash_outflow_period": cash_outflow_period,
        "cash_net_period": cash_net_period,
    }
    
    return render_template("report_dashboard.html",
                         company=company,
                         kpi=kpi,
                         from_date=from_date.strftime('%Y-%m-%d'),
                         to_date=to_date.strftime('%Y-%m-%d'),
                         chart_labels=chart_labels,
                         revenue_data=revenue_data,
                         purchase_data=purchase_data,
                         profit_labels=profit_labels,
                         profit_trend=profit_trend,
                         cash_inflow_period=cash_inflow_period,
                         cash_outflow_period=cash_outflow_period,
                         cash_net_period=cash_net_period,
                         top_clients_data=top_clients_data,
                         status_counts=status_counts,
                         payment_methods=payment_methods,
                         recent_shipments=recent_shipments,
                         recent_payments=recent_payments,
                         pending_invoices=pending_invoices,
                         total_shipments=status_counts["total"])

@app.route("/dashboard")
@login_required
@require_permission("dashboard", "view")
def dashboard():
    """Redirect dashboard to Apps Hub"""
    return redirect(url_for("apps_hub"))



@app.route("/api/dashboard-data")
@login_required
@require_permission("dashboard", "view")
def api_dashboard_data():
    """API endpoint for dashboard data with date filters"""
    cdb = get_cdb()
    company_id = get_current_company()
    
    from_date_str = request.args.get('from_date', '')
    to_date_str = request.args.get('to_date', '')
    
    if not from_date_str:
        from_date = date(2000, 1, 1)
    else:
        from_date = date.fromisoformat(from_date_str)
    
    if not to_date_str:
        to_date = today_ist()
    else:
        to_date = date.fromisoformat(to_date_str)
    
    # Cash in Hand (all time, not filtered by date)
    cash_transactions = cdb.query(CashTransaction).filter_by(company_id=company_id).all()
    cash_balance = sum(t.amount for t in cash_transactions if t.type == 'income') - \
                   sum(t.amount for t in cash_transactions if t.type == 'expense')
    
    # Bank Balance (all time, not filtered by date)
    bank_accounts = cdb.query(BankAccount).filter_by(company_id=company_id, status='Active').all()
    bank_balance = sum(acc.balance for acc in bank_accounts)
    
    # ── FILTERED: Exclude Void and Draft invoices ──────────────────────────────
    # Filtered Sales Invoices (exclude Void and Draft)
    sales_invoices = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.date >= from_date,
        Invoice.date <= to_date,
        Invoice.status.notin_(['Void', 'Draft'])  # ← EXCLUDE Void and Draft
    ).all()
    total_revenue = sum(inv.grand_total or 0 for inv in sales_invoices)
    
    # Filtered Purchase Invoices
    purchase_invoices = cdb.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.date >= from_date,
        PurchaseInvoice.date <= to_date,
        PurchaseInvoice.status.notin_(['Void', 'Draft'])  # ← EXCLUDE Void and Draft
    ).all()
    total_purchases = sum(pur.grand_total or 0 for pur in purchase_invoices)
    
    # ── Expenses for period ─────────────────────────────────────────────────────
    period_expenses = cdb.query(Expense).filter(
        Expense.company_id == company_id,
        Expense.date >= from_date,
        Expense.date <= to_date
    ).all()
    total_expenses = sum(exp.amount or 0 for exp in period_expenses)
    
    gross_profit = total_revenue - total_purchases
    net_profit = gross_profit - total_expenses
    
    # ── Pending Amount: Only from non-Void, non-Draft invoices ────────────────
    all_active_invoices = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.status.notin_(['Void', 'Draft'])  # ← EXCLUDE Void and Draft
    ).all()
    pending_amount = _total_outstanding(cdb, company_id)
    
    # Cash flow for period (exclude Void/Draft invoices from payment calculations)
    period_cash_income = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        CashTransaction.type == 'income',
        CashTransaction.date >= from_date,
        CashTransaction.date <= to_date
    ).all()
    period_cash_expense = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        CashTransaction.type == 'expense',
        CashTransaction.date >= from_date,
        CashTransaction.date <= to_date
    ).all()
    cash_inflow_period = sum(t.amount for t in period_cash_income)
    cash_outflow_period = sum(t.amount for t in period_cash_expense)
    
    # Chart data (last 6 months) - EXCLUDE Void and Draft
    chart_labels = []
    revenue_data = []
    purchase_data = []
    expense_data = []
    profit_trend = []
    profit_labels = []
    
    for i in range(5, -1, -1):
        month_date = today_ist().replace(day=1) - timedelta(days=30 * i)
        month_start = month_date.replace(day=1)
        if month_date.month == 12:
            month_end = month_date.replace(day=31)
        else:
            month_end = month_date.replace(month=month_date.month + 1, day=1) - timedelta(days=1)
        
        month_label = month_date.strftime('%b %Y')
        chart_labels.append(month_label)
        
        # Monthly Revenue - EXCLUDE Void and Draft
        month_revenue = sum(
            inv.grand_total or 0 for inv in cdb.query(Invoice).filter(
                Invoice.company_id == company_id,
                Invoice.date >= month_start,
                Invoice.date <= month_end,
                Invoice.status.notin_(['Void', 'Draft'])  # ← EXCLUDE Void and Draft
            ).all()
        )
        revenue_data.append(month_revenue / 100000)
        
        # Monthly Purchases - EXCLUDE Void and Draft
        month_purchases = sum(
            pur.grand_total or 0 for pur in cdb.query(PurchaseInvoice).filter(
                PurchaseInvoice.company_id == company_id,
                PurchaseInvoice.date >= month_start,
                PurchaseInvoice.date <= month_end,
                PurchaseInvoice.status.notin_(['Void', 'Draft'])  # ← EXCLUDE Void and Draft
            ).all()
        )
        purchase_data.append(month_purchases / 100000)
        
        # Monthly Expenses
        month_expenses = sum(
            exp.amount or 0 for exp in cdb.query(Expense).filter(
                Expense.company_id == company_id,
                Expense.date >= month_start,
                Expense.date <= month_end
            ).all()
        )
        expense_data.append(month_expenses / 100000)
        
        if i <= 5:
            profit_labels.append(month_label)
            month_net_profit = (month_revenue - month_purchases) - month_expenses
            profit_trend.append(month_net_profit / 1000)
    
    # Top clients (exclude Void and Draft invoices)
    clients = cdb.query(Client).filter_by(company_id=company_id).all()
    top_clients_data = []
    for client in clients[:10]:
        client_invoices = cdb.query(Invoice).filter(
            Invoice.company_id == company_id,
            Invoice.client_id == client.id,
            Invoice.status.notin_(['Void', 'Draft'])  # ← EXCLUDE Void and Draft
        ).all()
        total_billed = sum(inv.grand_total or 0 for inv in client_invoices)
        pending = _client_outstanding(cdb, company_id, client)
        top_clients_data.append({
            "name": client.name,
            "total_billed": total_billed,
            "pending": pending,
            "status": client.status or "Active"
        })
    top_clients_data.sort(key=lambda x: x["total_billed"], reverse=True)
    top_clients_data = top_clients_data[:5]
    
    # Recent invoices (exclude Void and Draft)
    recent_invoices_raw = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.status.notin_(['Void', 'Draft'])  # ← EXCLUDE Void and Draft
    ).order_by(Invoice.date.desc()).limit(10).all()
    recent_invoices_data = []
    for inv in recent_invoices_raw:
        client_name = inv.client_obj.name if inv.client_obj else (inv.contact_person or "—")
        total = inv.grand_total or 0
        balance = getattr(inv, 'balance', 0) or 0
        if balance <= 0:
            status = "Paid"
        elif inv.status == "Partial":
            status = "Partial"
        else:
            status = "Pending"
        recent_invoices_data.append({
            "id": inv.invoice_id,
            "customer": client_name,
            "date": inv.date.strftime("%d %b %Y") if inv.date else "—",
            "total": total,
            "status": status
        })
    
    # Low stock
    stock_items = cdb.query(StockItem).filter_by(company_id=company_id).all()
    low_stock_items = []
    for item in stock_items:
        reorder = item.reorder_level or 10
        if item.quantity <= reorder and item.quantity > 0:
            low_stock_items.append({
                "code": item.code,
                "name": item.name,
                "quantity": item.quantity,
                "reorder_level": reorder
            })
    low_stock_items = low_stock_items[:8]
    
    return jsonify({
        "kpi": {
            "cash_balance": cash_balance,
            "bank_balance": bank_balance,
            "total_revenue": total_revenue,
            "total_purchases": total_purchases,
            "total_expenses": total_expenses,
            "gross_profit": gross_profit,
            "net_profit": net_profit,
            "pending_amount": pending_amount,
            "cash_inflow_period": cash_inflow_period,
            "cash_outflow_period": cash_outflow_period,
            "cash_net_period": cash_inflow_period - cash_outflow_period,
        },
        "chart_labels": chart_labels,
        "revenue_data": revenue_data,
        "purchase_data": purchase_data,
        "expense_data": expense_data,
        "profit_labels": profit_labels,
        "profit_trend": profit_trend,
        "top_clients": top_clients_data,
        "recent_invoices": recent_invoices_data,
        "low_stock": low_stock_items,
    })

@app.context_processor
def inject_bi_navigation():
    endpoint = (request.endpoint or "").lower()
    is_bi = endpoint in (
        "bi_intelligence",
        "bi_dashboard",
        "bi_executive",
        "bi_departments",
        "bi_explore",
        "bi_builder",
        "reports_dashboard",
        "bi_predictive",
        "bi_warehouse",
        "hr_bi_intelligence",
    ) or endpoint.startswith("bi_") or endpoint.startswith("api_bi_")
    return {
        "use_bi_navigation": is_bi,
        "is_bi_section": is_bi,
    }


@app.route("/bi-intelligence")
@login_required
@require_permission("analytics", "view")
def bi_intelligence():
    """Unified entry point for Qiyadah BI Intelligence."""
    company_id = get_current_company()
    company = get_company_by_id(company_id)
    if not company:
        flash("Company not found")
        return redirect(url_for("logout"))
    return render_template(
        "bi_intelligence.html",
        company=company,
        active="bi_intelligence",
    )


@app.route("/bi-executive")
@login_required
@require_permission("analytics", "view")
def bi_executive():
    """Company-wide executive dashboard backed by the canonical v1 engine."""
    if get_current_user().get("role") not in ("owner", "super_admin"):
        abort(403)
    company = get_company_by_id(get_current_company())
    if not company:
        abort(404)
    return render_template("bi_executive.html", company=company, active="bi_intelligence")


@app.route("/bi-dashboard/finance")
@login_required
@require_permission("analytics", "view")
def bi_finance_dashboard():
    """Business Intelligence Dashboard"""
    cdb = get_cdb()
    company_id = get_current_company()
    
    # Get employees for filter
    employees = cdb.query(CompanyUser).filter(
        CompanyUser.company_id == company_id,
        CompanyUser.is_active == True,
        CompanyUser.role != 'owner'
    ).order_by(CompanyUser.full_name).all()

    # Get clients for client-wise dashboard filtering. The dashboard's
    # booking/revenue helpers already support DashboardFilters.client_id,
    # so this only supplies the selectable client list to the UI.
    clients = cdb.query(Client).filter(
        Client.company_id == company_id
    ).order_by(Client.name).all()
    
    # Get countries from invoice terms
    invoices = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.terms.isnot(None)
    ).all()
    
    countries = set()
    for inv in invoices:
        if inv.terms:
            try:
                meta = json.loads(inv.terms)
                dest = meta.get('destination')
                if dest and dest.strip():
                    countries.add(dest.strip())
            except:
                pass
    
    # Get expense categories
    categories = cdb.query(Expense.category.distinct()).filter(
        Expense.company_id == company_id
    ).all()
    categories = [c[0] for c in categories if c[0]]
    
    # Set default dates (current month)
    today = today_ist()
    from_date = today.replace(day=1)
    
    return render_template(
        "bi_dashboard.html",
        employees=employees,
        clients=clients,
        countries=sorted(countries),
        categories=sorted(categories),
        from_date=from_date.strftime('%Y-%m-%d'),
        to_date=today.strftime('%Y-%m-%d'),
        active='bi_dashboard'
    )

@app.route("/api/bi/dashboard")
@login_required
@require_permission("analytics", "view")
def api_bi_dashboard():
    """Comprehensive BI dashboard data endpoint"""
    cdb = get_cdb()
    company_id = get_current_company()
    
    # Parse filters
    filters = parse_filters_from_request(request.args, company_id)
    from_date, to_date = get_period_range(filters)
    prev_from, prev_to = get_previous_period_range(filters)
    
    # Build response
    response = {
        'filters': filters.to_dict(),
        'kpi': {},
        'charts': {},
        'tables': {},
        'comparisons': {},
    }
    
    # ----- KPI DATA -----
    kpi_data = get_kpi_data(cdb, company_id, from_date, to_date, prev_from, prev_to, filters)
    response['kpi'] = kpi_data
    
    # ----- FINANCE SNAPSHOT (date-only, no client/employee filter) -----
    response['finance'] = get_finance_snapshot(cdb, company_id, from_date, to_date)
    
    # ----- RECEIVABLES & OUTSTANDING INTELLIGENCE (Responds to date, client, employee, country) -----
    from utils.query_engine import get_receivables_intelligence
    response['receivables'] = get_receivables_intelligence(cdb, company_id, from_date, to_date, prev_from, prev_to, filters)
    
    # ----- CHART DATA -----
    # Revenue & Profit Trends
    response['charts']['revenue_profit'] = get_revenue_profit_chart_data(
        cdb, company_id, from_date, to_date, filters
    )
    # BUGFIX: period_labels used to come from get_period_labels(), which buckets
    # months by naive "same day next month" arithmetic (e.g. 31 Jul -> 31 Aug).
    # get_revenue_profit_chart_data() buckets using actual period_end/to_date
    # capping instead. For a custom range like 31-07-2026 to 26-08-2026 these
    # two produced a DIFFERENT NUMBER of buckets (1 vs 2), so the chart's
    # x-axis labels and its data arrays were out of sync — this is why the
    # Revenue & Profit Trend chart looked wrong compared to the KPI cards.
    # Reusing this chart's own labels guarantees the two always match.
    response['period_labels'] = response['charts']['revenue_profit']['labels']
    
    # Sales vs Purchase Comparison
    response['charts']['sales_purchase'] = get_sales_purchase_comparison(
        cdb, company_id, from_date, to_date, filters
    )
    
    # Top Countries
    response['charts']['top_countries'] = get_top_countries_chart_data(
        cdb, company_id, from_date, to_date, filters
    )
    
    # Top Employees
    response['charts']['top_employees'] = get_top_employees_chart_data(
        cdb, company_id, from_date, to_date, filters
    )
    
    # Profit Breakdown by Category
    response['charts']['profit_breakdown'] = get_profit_breakdown_chart_data(
        cdb, company_id, from_date, to_date, filters
    )
    
    # Monthly Trends (Multi-line)
    response['charts']['monthly_trends'] = get_monthly_trends_chart_data(
        cdb, company_id, from_date, to_date, filters
    )
    
    # Booking Status Distribution
    response['charts']['booking_status'] = get_invoice_status_chart_data(
        cdb, company_id, from_date, to_date, filters
    )
    
    # Payment Method Distribution
    response['charts']['payment_methods'] = get_payment_methods_chart_data(
        cdb, company_id, from_date, to_date, filters
    )
    
    # ----- TABLE DATA -----
    response['tables']['summary'] = get_summary_table_data(
        cdb, company_id, from_date, to_date, filters
    )
    
    response['tables']['detailed'] = get_detailed_table_data(
        cdb, company_id, from_date, to_date, filters
    )
    
    # ----- COMPARISONS -----
    response['comparisons']['period_over_period'] = get_period_over_period_comparison(
        cdb, company_id, from_date, to_date, prev_from, prev_to, filters
    )
    
    response['comparisons']['year_over_year'] = get_year_over_year_comparison(
        cdb, company_id, from_date, to_date, filters
    )
    
    return jsonify(response)


@app.route("/api/bi/company-analysis")
@login_required
@require_permission("analytics", "view")
def api_bi_company_analysis():
    """
    Returns a comprehensive 20-point deep diagnostic analysis of the company
    for the executive audit modal dialog.
    """
    try:
        from utils.query_engine import get_company_deep_analysis
        company_id = get_current_company()
        analysis = get_company_deep_analysis(company_id)
        return jsonify(analysis)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


# ── Price List Routes ─────────────────────────────────────────────────────────


# ── Shipping Rate Calculator & Quick Quote ────────────────────────────────────


def _describe_packages(packages_data):
    """Human-readable item description built from a booking's package names,
    e.g. 'Box x2, Envelope x1'. The auto-generated purchase line used to set
    description=docket_no, which just duplicated the AWB/Docket column on
    the Purchases screens — this gives the Item column something real to
    show instead. Falls back to 'Courier Freight' when packages carry no
    name at all.
    """
    counts = {}
    for p in packages_data:
        name = (p.get("name") or p.get("type") or "").strip()
        if not name:
            continue
        qty = p.get("qty") or 1
        counts[name] = counts.get(name, 0) + qty
    if not counts:
        return "Courier Freight"
    parts = []
    for name, qty in counts.items():
        qty_disp = int(qty) if qty == int(qty) else qty
        parts.append(f"{name} x{qty_disp}")
    return ", ".join(parts)


def _repair_purchase_item_descriptions(cdb, company_id):
    """
    One-off data repair, NOT part of normal request flow.

    Older auto-generated PurchaseInvoiceItem rows have description ==
    docket_no (a bug in _sync_auto_purchase_invoice_line, now fixed for new/
    edited lines) — which made the "Item" column on Purchases just repeat
    the AWB/Docket column instead of showing what was actually shipped
    (box/envelope/etc). This walks every purchase item that's linked back
    to a booking (source_invoice_id set), re-derives the description from
    that booking's package names via _describe_packages(), and updates it
    in place. Only touches rows whose description currently equals their
    own docket_no (or the linked booking's invoice_id) so manually-edited
    descriptions are left alone. Safe to run more than once.
    """
    fixed = []
    items = (
        cdb.query(PurchaseInvoiceItem)
        .filter(PurchaseInvoiceItem.source_invoice_id.isnot(None))
        .all()
    )
    for item in items:
        booking = cdb.query(Invoice).filter_by(id=item.source_invoice_id).first()
        if not booking:
            continue
        if item.description not in (item.docket_no, booking.invoice_id):
            continue  # description was edited or already fixed — leave it
        try:
            meta = json.loads(booking.terms) if booking.terms else {}
        except (ValueError, TypeError):
            meta = {}
        packages_data = meta.get("packages") or []
        new_description = _describe_packages(packages_data)
        if new_description and new_description != item.description:
            fixed.append((item.docket_no or booking.invoice_id, item.description, new_description))
            item.description = new_description
    if fixed:
        cdb.commit()
    return fixed


@app.route("/admin/repair-purchase-item-descriptions")
@login_required
def repair_purchase_item_descriptions():
    cdb = get_cdb()
    company_id = get_current_company()
    fixed = _repair_purchase_item_descriptions(cdb, company_id)
    if fixed:
        flash(f"Repaired {len(fixed)} purchase item description{'s' if len(fixed)!=1 else ''}: " +
              "; ".join(f"{docket} ({old} → {new})" for docket, old, new in fixed[:20]) +
              (" …" if len(fixed) > 20 else ""), "success")
    else:
        flash("No purchase item descriptions needed repair.", "info")
    return redirect(url_for("purchase_invoice_list"))


CASH_CLIENT_ID = "CASH"


# Add this function near the top of app.py (around line 600, after _get_or_create_cash_client)

def _get_or_create_cash_client(cdb, company_id, shipper_name):
    """
    Get or create a cash client record for a walk-in customer.
    Creates ONE client per unique shipper_name so we can track repeat
    cash customers and their stock history.
    """
    if not shipper_name or not shipper_name.strip():
        # Fallback to generic cash client
        return _get_or_create_generic_cash_client(cdb, company_id)
    
    # Normalize and clean the name
    shipper_name = shipper_name.strip()
    
    # Check if this cash client already exists
    cash_client = cdb.query(Client).filter_by(
        company_id=company_id,
        name=shipper_name,
        client_type="Cash-Only"  # Special type to filter out of debtors
    ).first()
    
    if cash_client:
        return cash_client
    
    # Create a new cash client
    company_obj = Company.query.filter_by(company_id=company_id).first()
    client_prefix = _company_name_prefix(company_obj.company_name if company_obj else "", from_end=True)
    
    # Generate a unique client_id with 'CASH' prefix
    cash_client_id = _next_numbered_id(
        cdb, Client.client_id, 
        f"{client_prefix}CASH",  # e.g., "demCASH001"
        extra_filters=[Client.company_id == company_id]
    )
    
    cash_client = Client(
        client_id=cash_client_id,
        company_id=company_id,
        name=shipper_name,
        client_type="Cash-Only",  # This filters them out of debtors list
        status="Active",
        pending=0.0,  # Cash clients don't have pending balances
        opening_balance=0.0,
        credit_limit=0,
        created_at=today_ist(),
        notes=f"Cash/Walk-in customer - created on {today_ist().strftime('%d %b %Y')}"
    )
    cdb.add(cash_client)
    cdb.flush()
    
    return cash_client


def _get_or_create_generic_cash_client(cdb, company_id):
    """
    Fallback: returns the shared CASH placeholder client.
    Used when no shipper_name is provided.
    """
    cash_client = cdb.query(Client).filter_by(
        company_id=company_id, 
        client_type="Cash-Only",
        name="Cash / Walk-in"  # The generic one
    ).first()
    
    if not cash_client:
        cash_client = Client(
            client_id="CASH001",  # Simple fixed ID for the generic one
            company_id=company_id,
            name="Cash / Walk-in",
            client_type="Cash-Only",
            status="Active",
            pending=0.0,
            opening_balance=0.0,
            created_at=today_ist(),
            notes="Generic cash/walk-in customer (no name provided)"
        )
        cdb.add(cash_client)
        cdb.flush()
    
    return cash_client



@app.route("/company/permissions/fields/<role>", methods=["POST"])
@login_required
@owner_required
def save_field_permissions(role):
    if role not in ("employee", "accountant", "manager"):
        flash("Invalid role")
        return redirect(url_for("company_settings"))
    
    company_id = get_current_company()
    cdb = get_customer_session(company_id)
    
    row = cdb.query(CompanyRolePermission).filter_by(company_id=company_id, role=role).first()
    if not row:
        row = CompanyRolePermission(company_id=company_id, role=role)
        cdb.add(row)
    
    field_perms = {}
    for field_key in INVOICE_FIELDS:
        edit_val = request.form.get(f"field__{field_key}__edit", "0")
        try:
            edit_val = int(edit_val)
        except ValueError:
            edit_val = 0
        
        view = edit_val >= 1
        edit = edit_val == 2
        
        field_perms[field_key] = {
            "view": view,
            "edit": edit
        }
    
    # Apply hard-locked restrictions
    if role in HARD_LOCKED_EDIT:
        for locked_group in HARD_LOCKED_EDIT[role]:
            if locked_group in field_perms:
                field_perms[locked_group]["edit"] = False
                field_perms[locked_group]["view"] = True
    
    row.field_permissions_json = json.dumps(field_perms)
    row.updated_at = datetime.utcnow()
    cdb.commit()
    
    flash(f"Field permissions for {role.title()} updated")
    return redirect(url_for("company_settings"))


@app.route("/company/permissions/fields/user/<user_id>", methods=["POST"])
@login_required
@owner_required
def save_user_field_permissions(user_id):
    company_id = get_current_company()
    cdb = get_customer_session(company_id)
    cu = cdb.query(CompanyUser).filter_by(user_id=user_id, company_id=company_id).first()
    if not cu:
        flash("User not found")
        return redirect(url_for("company_settings"))
    if cu.role in ("owner", "super_admin"):
        flash("Owner access can't be limited this way")
        return redirect(url_for("company_settings"))

    field_perms = {}
    for field_key in INVOICE_FIELDS:
        edit_val = request.form.get(f"field__{field_key}__edit", "0")
        try:
            edit_val = int(edit_val)
        except ValueError:
            edit_val = 0
        
        view = edit_val >= 1
        edit = edit_val == 2
        
        field_perms[field_key] = {
            "view": view,
            "edit": edit
        }
    
    # Apply hard-locked restrictions
    if cu.role in HARD_LOCKED_EDIT:
        for locked_group in HARD_LOCKED_EDIT[cu.role]:
            if locked_group in field_perms:
                field_perms[locked_group]["edit"] = False
                field_perms[locked_group]["view"] = True

    cu.field_permissions = json.dumps(field_perms)
    cdb.commit()
    flash(f"Field access updated for {cu.full_name}")
    return redirect(url_for("company_settings"))

@app.route("/inventory/clear_party_stock", methods=["POST"])
@login_required
@owner_required
def inventory_clear_party_stock():
    company_id = get_current_company()
    if not company_id:
        return redirect(url_for('login'))
    cdb = get_customer_session(company_id)

    party_name    = (request.form.get("party_name") or "").strip()
    is_cash       = request.form.get("is_cash") == "1"
    client_id_raw = request.form.get("client_id")
    client_id     = int(client_id_raw) if client_id_raw and client_id_raw.isdigit() else None

    if not party_name:
        flash("No party specified.", "danger")
        return redirect(url_for('inventory_list'))
    if not is_cash and not client_id:
        flash("Missing party reference — could not clear stock.", "danger")
        return redirect(url_for('inventory_list'))

    user_email = session.get('user', {}).get('email', '')

    if is_cash:
        items = cdb.query(StockItem).filter_by(company_id=company_id, client_id=None).all()
    else:
        items = cdb.query(StockItem).filter_by(company_id=company_id, client_id=client_id).all()
    item_ids = {i.id: i for i in items}

    if not item_ids:
        flash(f"'{party_name}' had no outstanding stock to clear.", "info")
        return redirect(url_for('inventory_list'))

    hist_rows = cdb.query(StockPurchaseHistory).filter(
        StockPurchaseHistory.stock_item_id.in_(item_ids.keys()),
        StockPurchaseHistory.awb_no.isnot(None),
    ).all()

    dispatched = {(h.stock_item_id, h.awb_no) for h in hist_rows if h.movement_type == "OUT"}
    outstanding = [
        h for h in hist_rows
        if h.movement_type != "OUT" and (h.stock_item_id, h.awb_no) not in dispatched
    ]

    # Cash StockItem rows are shared across shippers, so only close out the
    # AWBs that actually belong to THIS party — matched via the booking
    # invoice's shipper_name, same as inventory_list() does.
    if is_cash:
        refs = {h.reference for h in outstanding if h.reference}
        invoices_by_ref = {
            inv.invoice_id: inv
            for inv in cdb.query(Invoice).filter(
                Invoice.invoice_id.in_(refs), Invoice.company_id == company_id
            ).all()
        } if refs else {}

        def matches(h):
            inv = invoices_by_ref.get(h.reference)
            if not inv:
                return False
            try:
                meta = json.loads(inv.terms) if inv.terms else {}
            except Exception:
                meta = {}
            return (meta.get("shipper_name") or "").strip() == party_name

        outstanding = [h for h in outstanding if matches(h)]

    cleared_count = 0
    for h in outstanding:
        cdb.add(StockPurchaseHistory(
            stock_item_id=h.stock_item_id,
            purchase_invoice_id=None,
            quantity=-(h.quantity or 0),
            purchase_rate=0,
            movement_type="OUT",
            purchase_date=today_ist(),
            reference=f"Manual clear by {user_email}",
            awb_no=h.awb_no,   # must match the outstanding row's AWB exactly —
                                # this is what Package Log's exclusion check needs
        ))
        item = item_ids.get(h.stock_item_id)
        if item and (item.quantity or 0) > 0:
            item.quantity = max(0, (item.quantity or 0) - (h.quantity or 0))
            item.last_updated = today_ist()
        cleared_count += 1

    cdb.commit()

    if cleared_count:
        flash(f"Cleared stock for '{party_name}' — {cleared_count} package(s) closed out.", "success")
    else:
        flash(f"'{party_name}' had no outstanding stock to clear.", "info")

    return redirect(url_for('inventory_list'))



# ─────────────────────────────────────────────────────────────────────────────
# ── Clients ───────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_client(c, outstanding=None, booking_count=None):
    """Return a dict whose keys match what clients.html / client_form.html expect.

    `outstanding`: pass a live-computed total (opening_balance + all unpaid
    invoices - receipts) to show the real current dues. If omitted, falls
    back to the cached c.pending field (balance-carry-forward, only reset
    on statement close/shift — NOT the same as total outstanding).
    `booking_count`: number of non-Void/Cancelled bookings for this client —
    used by the delete-confirmation modal so it can warn about how much
    history is attached before a client is removed from the list."""
    return {
        # identity
        "id":              c.id,
        "client_id":       c.client_id or "—",
        "client_name":     c.name,
        "client_type":     c.client_type     or "Business",
        "contact_person":  c.contact_person  or "",
        # contact
        "phone":           c.phone           or "",
        "alternate_phone": c.alternate_phone or "",
        "email":           c.email           or "",
        "website":         c.website         or "",
        # address
        "address_line1":   c.address_line1   or "",
        "address_line2":   c.address_line2   or "",
        "city":            c.city            or "",
        "state":           c.state           or "",
        "pincode":         c.pincode         or "",
        "country":         c.country         or "India",
        # GST & tax
        "gst_number":      c.gst_number      or "",
        "pan_number":      c.pan_number      or "",
        "aadhar_number":   c.aadhar_number   or "",
        "aadhar_front_file": c.aadhar_front_file or "",
        "aadhar_back_file":  c.aadhar_back_file  or "",
        "pan_front_file":    c.pan_front_file    or "",
        "pan_back_file":     c.pan_back_file     or "",
        "gst_type":        c.gst_type        or "Regular",
        # financial
        "credit_limit":    c.credit_limit    or 0.0,
        "credit_days":     c.credit_days     or 30,
        "outstanding":     outstanding if outstanding is not None else (c.pending or 0.0),
        "booking_count":   booking_count if booking_count is not None else 0,
        "opening_balance": c.opening_balance or 0.0,
        "last_payment":    c.last_payment,
        # status
        "status":          c.status          or "Active",
        "notes":           c.notes           or "",
        "created_at":      c.created_at,
    }


def _compute_outstanding_for_clients(cdb, company_id, client_rows):
    """Live outstanding per client: opening_balance + invoices since cutoff
    - receipts since cutoff. This is the ONE formula for "how much does this
    client owe" — client_list(), client_view(), and every dashboard/report
    KPI must call this instead of summing Invoice.balance across a client's
    bookings. Booking balances and this number drift apart (opening
    balances, receipts not tied 1:1 to one invoice, credit notes), and that
    drift was the "chaos" of showing two different pending figures for the
    same client.
    MUST exclude Void/Cancelled/Draft invoices from total_invoiced — matches
    _debtor_summary() and _build_client_ledger(), both of which already
    exclude them.
    Returns {client_id: outstanding_float}."""
    client_ids = [c.id for c in client_rows]
    invoiced_by_client = dict(
        cdb.query(Invoice.client_id, func.sum(Invoice.grand_total))
           .filter(Invoice.company_id == company_id, Invoice.client_id.in_(client_ids),
                   Invoice.status.notin_(['Cancelled', 'Void', 'Draft']))
           .group_by(Invoice.client_id).all()
    ) if client_ids else {}

    # Aggregate cash receipts normalized by trimmed lowercase party name
    cash_by_norm_name = {}
    for name, amt in cdb.query(CashTransaction.party_name, func.sum(CashTransaction.amount))\
                       .filter(CashTransaction.company_id == company_id,
                               CashTransaction.category.in_(["Receipt", "Adjustment"]),
                               or_(CashTransaction.reference != "WRITE-OFF", CashTransaction.reference.is_(None)))\
                       .group_by(CashTransaction.party_name).all():
        if name:
            k = name.strip().lower()
            cash_by_norm_name[k] = cash_by_norm_name.get(k, 0.0) + float(amt or 0)

    # Aggregate bank receipts (credits) normalized by trimmed lowercase party name
    bank_by_norm_name = {}
    for name, amt in cdb.query(BankTransaction.party_name, func.sum(BankTransaction.amount))\
                       .filter(BankTransaction.company_id == company_id, BankTransaction.type == "credit")\
                       .group_by(BankTransaction.party_name).all():
        if name:
            k = name.strip().lower()
            bank_by_norm_name[k] = bank_by_norm_name.get(k, 0.0) + float(amt or 0)

    result = {}
    for c in client_rows:
        cutoff_date = c.statement_cutoff.date() if c.statement_cutoff else None
        c_norm = (c.name or "").strip().lower()
        if cutoff_date:
            total_invoiced = float(
                cdb.query(func.sum(Invoice.grand_total))
                   .filter(Invoice.company_id == company_id, Invoice.client_id == c.id,
                           Invoice.status.notin_(['Cancelled', 'Void', 'Draft']),
                           Invoice.date >= cutoff_date).scalar() or 0
            )
            cash_received = float(
                cdb.query(func.sum(CashTransaction.amount))
                   .filter(CashTransaction.company_id == company_id,
                           func.lower(func.trim(CashTransaction.party_name)) == c_norm,
                           CashTransaction.category.in_(["Receipt", "Adjustment"]),
                           or_(CashTransaction.reference != "WRITE-OFF", CashTransaction.reference.is_(None)),
                           CashTransaction.date >= cutoff_date).scalar() or 0
            )
            bank_received = float(
                cdb.query(func.sum(BankTransaction.amount))
                   .filter(BankTransaction.company_id == company_id,
                           func.lower(func.trim(BankTransaction.party_name)) == c_norm,
                           BankTransaction.type == "credit", BankTransaction.date >= cutoff_date).scalar() or 0
            )
        else:
            total_invoiced = float(invoiced_by_client.get(c.id, 0) or 0)
            cash_received = float(cash_by_norm_name.get(c_norm, 0.0))
            bank_received = float(bank_by_norm_name.get(c_norm, 0.0))

        result[c.id] = (c.opening_balance or 0) + total_invoiced - cash_received - bank_received
    return result


def _client_outstanding(cdb, company_id, client):
    """Single-client convenience wrapper around _compute_outstanding_for_clients."""
    return _compute_outstanding_for_clients(cdb, company_id, [client]).get(client.id, 0.0)


def _total_outstanding(cdb, company_id):
    """Sum of every active client's live outstanding dues (positive dues only) —
    matches the Clients page and Debtors summary exactly.
    Excludes Cash-Only/Supplier client types without customer ledger dues."""
    client_rows = cdb.query(Client).filter(
        Client.company_id == company_id,
        Client.status != "Deleted",
        ~Client.client_type.in_(["Supplier", "Cash-Only"]),
    ).all()
    outstanding_map = _compute_outstanding_for_clients(cdb, company_id, client_rows)
    return sum(val for val in outstanding_map.values() if val > 0)


@app.route("/clients/check_similar")
@login_required
def client_check_similar():
    cdb = get_cdb()
    company_id = get_current_company()
    name = request.args.get("name", "")
    exclude_pk = request.args.get("exclude_id", type=int)
    matches = _find_similar_clients(cdb, company_id, name, exclude_pk=exclude_pk)
    return jsonify({"matches": matches})

@app.route("/clients")
@login_required
@require_permission("clients", "view")
def client_list():
    cdb = get_cdb()
    company_id    = get_current_company()
    filter_status = request.args.get("status", "All")

    # Same debtor population as _total_outstanding()/_compute_outstanding_for_clients —
    # a blacklist, not a whitelist, so a blank/typo'd/unlisted client_type
    # (e.g. an edit that posted an empty field) still shows up here instead
    # of silently counting toward dashboard/booking totals while being
    # invisible on this page.
    query = cdb.query(Client).filter(
        Client.company_id == company_id,
        ~Client.client_type.in_(["Supplier", "Both", "Cash-Only"]),
        Client.status != "Deleted",
    )
    if filter_status != "All":
        query = query.filter_by(status=filter_status)

    client_rows = query.all()
    client_ids  = [c.id for c in client_rows]

    # Live totals — same formula as the debtor statement's closing balance:
    # opening_balance + invoices since cutoff − receipts since cutoff.
    # Shared with client_view() and every dashboard/report "Pending Amount"
    # KPI via _compute_outstanding_for_clients, so this number can't drift
    # from what those pages show for the same client.
    outstanding_by_id = _compute_outstanding_for_clients(cdb, company_id, client_rows)

    # Booking count per client — shown in the delete-confirmation modal so
    # deleting a client with live history isn't a silent one-click action.
    booking_count_by_id = dict(
        cdb.query(Invoice.client_id, func.count(Invoice.id))
           .filter(Invoice.company_id == company_id, Invoice.client_id.in_(client_ids),
                   Invoice.status.notin_(['Cancelled', 'Void', 'Draft']))
           .group_by(Invoice.client_id).all()
    ) if client_ids else {}

    clients = [_normalize_client(c, outstanding=outstanding_by_id.get(c.id, 0.0),
                                  booking_count=booking_count_by_id.get(c.id, 0))
               for c in client_rows]

    return render_template("clients.html", clients=clients, current_status=filter_status)

@app.route("/clients/<int:client_pk>/remove", methods=["POST"])
@login_required
@owner_required
@require_admin_password
def client_remove(client_pk):
    """
    Soft-delete: removes the client from the Clients list only. Every
    invoice, manifest entry, stock item, and ledger row that references
    this client_id is left untouched — they keep resolving to this same
    row, it just no longer shows up in client_list(). Never a hard DELETE:
    that would violate the FK every invoice/purchase/stock row holds.
    """
    cdb = get_cdb()
    company_id = get_current_company()
    c = _first_or_404(cdb.query(Client).filter_by(id=client_pk, company_id=company_id).first())
    c.status = "Deleted"
    cdb.commit()
    flash(f"'{c.name}' removed from the client list. Their bookings and ledger history are unaffected.")
    return redirect(url_for("client_list"))


@app.route("/clients/<int:client_pk>/restore", methods=["POST"])
@login_required
@owner_required
def client_restore(client_pk):
    """Undo client_remove(). Since the delete only ever flipped `status`
    to "Deleted" and never touched any related row, restoring is just
    flipping it back — every booking, estimate, customer invoice, and the
    debtor statement were still pointing at this client_id the whole time,
    so they reappear automatically. Reached from client_form.html's
    "restore this client instead" prompt when a new client's name exactly
    matches one that was previously deleted.
    """
    cdb = get_cdb()
    company_id = get_current_company()
    c = _first_or_404(cdb.query(Client).filter_by(id=client_pk, company_id=company_id).first())
    if c.status != "Deleted":
        flash(f"'{c.name}' isn't deleted — nothing to restore.", "info")
        return redirect(url_for("client_view", client_pk=client_pk))
    c.status = "Active"
    cdb.commit()
    flash(f"'{c.name}' restored — their bookings, estimates, customer invoices, and debtor statement are all back exactly as they were.")
    return redirect(url_for("client_view", client_pk=client_pk))

# /clients/new  ── template links here for new client
@app.route("/clients/new", methods=["GET", "POST"])
@login_required
@require_permission("clients", "view", method_actions={'POST': 'create'})
def client_new():
    cdb = get_cdb()
    company_id = get_current_company()
    if request.method == "POST":
        f = request.form
        name = f.get("client_name", "").strip()

        # ── Catch re-creating a client that already exists ─────────────────
        # client_remove() never deletes the row — it only flips status to
        # "Deleted" (see its docstring). Every booking, estimate, customer
        # invoice, and the debtor statement still point at that same
        # client_id. Silently creating a second Client row for the same
        # name here would split the history in two. Give the user a choice
        # instead of guessing for them:
        #   - match is Deleted   → offer Restore vs. create-anyway
        #   - match is Active    → offer "go to that client" vs. create-anyway
        # `force_new=1` (set by client_form.html's "create separate new
        # client anyway" button) skips this and creates a genuinely new,
        # unrelated client.
        if name and not f.get("force_new"):
            existing = cdb.query(Client).filter(
                Client.company_id == company_id,
                func.lower(Client.name) == name.lower(),
            ).first()
            if existing:
                return render_template(
                    "client_form.html",
                    form_data=f,
                    existing_match={
                        "id":        existing.id,
                        "name":      existing.name,
                        "client_id": existing.client_id,
                        "deleted":   existing.status == "Deleted",
                    },
                )

        # GST uniqueness check (per company)
        gst = f.get("gst_number", "").strip().upper()
        if gst:
            existing_gst = cdb.query(Client).filter_by(
                company_id=company_id, gst_number=gst
            ).first()
            if existing_gst:
                flash(f"GST number {gst} is already registered to client '{existing_gst.name}'. Please check and try again.", "error")
                return render_template("client_form.html", form_data=f)

        company_obj = Company.query.filter_by(company_id=company_id).first()
        client_prefix = _company_name_prefix(company_obj.company_name if company_obj else "", from_end=True)
        new_client_id = _next_numbered_id(cdb, Client.client_id, client_prefix, extra_filters=[Client.company_id == company_id])

        new_client = Client(
            client_id       = new_client_id,
            company_id      = company_id,
            name            = f.get("client_name", "").strip(),
            client_type     = f.get("client_type", "Business"),
            contact_person  = f.get("contact_person", "").strip(),
            phone           = f.get("phone", "").strip(),
            alternate_phone = f.get("alternate_phone", "").strip(),
            email           = f.get("email", "").strip().lower(),
            website         = f.get("website", "").strip(),
            address_line1   = f.get("address_line1", "").strip(),
            address_line2   = f.get("address_line2", "").strip(),
            city            = f.get("city", "").strip(),
            state           = f.get("state", "").strip(),
            pincode         = f.get("pincode", "").strip(),
            country         = f.get("country", "India").strip(),
            gst_number      = gst or None,
            pan_number      = f.get("pan_number", "").strip().upper() or None,
            aadhar_number   = f.get("aadhar_number", "").strip() or None,
            gst_type        = f.get("gst_type", "Regular"),
            credit_limit    = float(f.get("credit_limit", 0) or 0),
            credit_days     = int(f.get("credit_days", 30) or 30),
            pending         = float(f.get("opening_balance", 0) or 0),
            opening_balance = float(f.get("opening_balance", 0) or 0),
            status          = f.get("status", "Active"),
            notes           = f.get("notes", "").strip(),
            created_at      = today_ist(),
        )
        cdb.add(new_client)
        cdb.commit()
        _save_client_id_docs(cdb, new_client, request.files)
        flash(f"Client '{new_client.name}' added successfully!")
        return redirect(url_for("client_list"))
    return render_template("client_form.html", form_data={})


# Keep /clients/add as an alias so old links still work
@app.route("/clients/add", methods=["GET", "POST"])
@login_required
@require_permission("clients", "create")
def client_add():
    return client_new()


# /clients/<id>  ── view detail (template links here with 👁️)
@app.route("/clients/<int:client_pk>")
@login_required
@require_permission("clients", "view")
def client_view(client_pk):
    cdb = get_cdb()
    company_id = get_current_company()
    c = _first_or_404(cdb.query(Client).filter_by(id=client_pk, company_id=company_id).first())
    # Use the same live outstanding formula as client_list() — falling back
    # to the cached c.pending field here was showing a different number on
    # this page than on the clients list for the same client.
    client = _normalize_client(c, outstanding=_client_outstanding(cdb, company_id, c))
    invoices = cdb.query(Invoice).filter_by(company_id=company_id, client_id=c.id).filter(Invoice.status != "Draft").order_by(Invoice.date.desc()).all()
    # Orders feature retired — client_detail.html isn't uploaded here, so still
    # passing orders=[] rather than dropping the kwarg, to avoid breaking that
    # template if it references `orders` directly. Safe to remove once that
    # template's Orders section is also cleaned up.
    orders   = []
    return render_template("client_detail.html", client=client, invoices=invoices, orders=orders)

def _build_client_ledger(cdb, company_id, c, since=None, until=None):
    """Builds the debtor ledger for a client. `since` (a datetime) is the
    statement cutoff — only invoices/receipts dated ON or AFTER its date are
    included, and the opening line reflects the carried-forward balance as
    of that cutoff instead of the original account-opening balance. `until`
    (a date, exclusive) is only passed when archiving a statement being
    closed today — it caps the archive at everything dated BEFORE today, so
    today's entries stay live and land in the new statement instead of the
    one being closed."""
    since_date = since.date() if since else None

    # Full-detail statement (client page): every booking shows as its own
    # line, regardless of whether it's since been grouped into a customer
    # invoice — customer invoices are not shown on this statement at all,
    # so there's nothing to dedupe against.
    invoices_q = cdb.query(Invoice).filter_by(company_id=company_id, client_id=c.id)
    invoices_q = invoices_q.filter(Invoice.status.notin_(['Cancelled', 'Void', 'Draft']))
    if since_date:
        invoices_q = invoices_q.filter(Invoice.date >= since_date)
    if until:
        invoices_q = invoices_q.filter(Invoice.date < until)
    invoices = invoices_q.order_by(Invoice.date.asc()).all()

    # Real payment events — same reasoning as debtor_statement(): a
    # transaction's own date/amount, not the invoice's date and a
    # back-computed grand_total-minus-balance figure that hid advance
    # payments and multi-part payments entirely.
    cash_txns_q = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        func.lower(CashTransaction.party_name) == func.lower(c.name)
    ).filter(CashTransaction.category.in_(["Receipt", "Adjustment"]))
    # The write-off/carry-forward adjustment row itself is the mechanism
    # that produces this cutoff — it must never appear as a ledger line,
    # otherwise every "new" statement would open with a phantom credit.
    cash_txns_q = cash_txns_q.filter(or_(CashTransaction.reference != "WRITE-OFF", CashTransaction.reference.is_(None)))
    if since_date:
        cash_txns_q = cash_txns_q.filter(CashTransaction.date >= since_date)
    if until:
        cash_txns_q = cash_txns_q.filter(CashTransaction.date < until)
    cash_txns = cash_txns_q.all()

    bank_txns_q = cdb.query(BankTransaction).filter(
        BankTransaction.company_id == company_id,
        func.lower(BankTransaction.party_name) == func.lower(c.name)
    ).filter(BankTransaction.type == "credit")
    if since_date:
        bank_txns_q = bank_txns_q.filter(BankTransaction.date >= since_date)
    if until:
        bank_txns_q = bank_txns_q.filter(BankTransaction.date < until)
    bank_txns = bank_txns_q.all()

    events = []

    ledger = []
    running_balance = c.opening_balance or 0.0

    # Opening balance / balance carried forward. When `since` is set, this
    # is a carried-forward balance and its date must be the first day of
    # THIS statement (the cutoff date) — not the client's original
    # created_at — otherwise the statement's displayed "from" date is wrong.
    if running_balance:
        ledger.append({
            "date": since.date() if since else (c.created_at or today_ist()),
            "type": "Balance Carried Forward" if since else "Opening Balance",
            "ref": "—",
            "awb": "", "consignee": "", "destination": "", "carrier_ref": "", "carrier": "",
            "chrg_wt": 0, "act_wt": 0, "vol_wt": 0,
            "grand_total": 0, "other_charges": 0, "billing_amount": 0,
            "debit": running_balance,
            "credit": 0,
            "balance": running_balance,
            "status": "",
            "id": None,
        })

    for inv in invoices:
        ship = _get_shipment_meta(inv)
        grand_total = inv.grand_total or 0
        events.append({
            "date": inv.date,
            "type": "Invoice",
            "ref": inv.invoice_id,
            "awb": ship["awb"],
            "consignee": ship["consignee"],
            "destination": ship["destination"],
            "carrier_ref": ship["carrier_ref"],
            "carrier": ship["carrier"],
            "chrg_wt": ship["chrg_wt"],
            "act_wt": ship["act_wt"],
            "vol_wt": ship["vol_wt"],
            "grand_total": grand_total - ship["other_charges"],
            "other_charges": ship["other_charges"],
            "billing_amount": grand_total,
            "per_kg": ship.get("per_kg", 0),
            "debit": grand_total,
            "credit": 0,
            "status": inv.status,
            "id": inv.invoice_id,
            "_sort": 0,
        })

    blank_shipment = {"awb": "", "consignee": "", "destination": "", "carrier_ref": "", "carrier": "",
                       "chrg_wt": 0, "act_wt": 0, "vol_wt": 0,
                       "grand_total": 0, "other_charges": 0, "billing_amount": 0,
                       "per_kg": 0}

    for ct in cash_txns:
        ref = ct.reference or ""
        events.append({
            "date": ct.date,
            "type": "Payment Received",
            "ref": "—" if ref == "ADVANCE" else ref,
            **blank_shipment,
            "debit": 0, "credit": ct.amount or 0, "status": "",
            "id": ref or None, "_sort": 1,
        })

    for bt in bank_txns:
        ref = bt.reference or ""
        events.append({
            "date": bt.date, "type": "Payment Received",
            "ref": "—" if ref == "ADVANCE" else ref,
            **blank_shipment,
            "debit": 0, "credit": bt.amount or 0, "status": "",
            "id": ref or None, "_sort": 1,
        })

    events.sort(key=lambda e: (e["date"] or date.min, e["_sort"]))
    for e in events:
        running_balance += (e["debit"] or 0) - (e["credit"] or 0)
        e["balance"] = running_balance
        del e["_sort"]
        ledger.append(e)

    total_debit = sum(r["debit"] for r in ledger)
    total_credit = sum(r["credit"] for r in ledger)

    return ledger, total_debit, total_credit, running_balance


@app.route("/clients/<int:client_pk>/statement")
@login_required
@require_permission("clients", "view")
def client_statement(client_pk):
    """Statement view for a client (debtor-style ledger)"""
    cdb = get_cdb()
    company_id = get_current_company()
    c = _first_or_404(cdb.query(Client).filter_by(id=client_pk, company_id=company_id).first())

    ledger, total_debit, total_credit, running_balance = _build_client_ledger(
        cdb, company_id, c, since=c.statement_cutoff)

    archives = (cdb.query(StatementClosing)
                .filter_by(company_id=company_id, entity_type="client", entity_id=c.id)
                .order_by(StatementClosing.closed_at.desc())
                .all())

    return render_template("ledger_statement.html",
                           entity=_normalize_client(c),
                           company=get_company_by_id(company_id),
                           ledger=ledger,
                           total_debit=total_debit,
                           total_credit=total_credit,
                           closing_balance=running_balance,
                           mode="debtor",
                           nav_active="clients",
                           back_url=f"/clients/{client_pk}",
                           archive_base_url=f"/clients/{client_pk}",
                           archives=archives,
                           archived=False,
                           today=today_ist().strftime("%d %b %Y"))


@app.route("/clients/<int:client_pk>/statement/archive/<int:archive_id>")
@login_required
@require_permission("clients", "view")
def client_statement_archive(client_pk, archive_id):
    """Prints a frozen old statement exactly as it looked at the moment the
    outstanding was cleared/shifted — recomputing from live data would drift
    if invoices are edited later, so this reads the saved snapshot instead."""
    cdb = get_cdb()
    company_id = get_current_company()
    c = _first_or_404(cdb.query(Client).filter_by(id=client_pk, company_id=company_id).first())
    archive = _first_or_404(cdb.query(StatementClosing).filter_by(
        id=archive_id, company_id=company_id, entity_type="client", entity_id=client_pk).first())

    return render_template("ledger_statement.html",
                           entity=_normalize_client(c),
                           company=get_company_by_id(company_id),
                           ledger=json.loads(archive.ledger_snapshot or "[]"),
                           total_debit=archive.total_debit,
                           total_credit=archive.total_credit,
                           closing_balance=archive.closing_balance,
                           mode="debtor",
                           nav_active="clients",
                           back_url=f"/clients/{client_pk}/statement",
                           archived=True,
                           archived_at=archive.closed_at,
                           today=today_ist().strftime("%d %b %Y"))

# /clients/<id>/edit
@app.route("/clients/<int:client_pk>/edit", methods=["GET", "POST"])
@login_required
@require_permission("clients", "view", method_actions={'POST': 'edit'})
def client_edit(client_pk):
    cdb = get_cdb()
    company_id = get_current_company()
    c          = _first_or_404(cdb.query(Client).filter_by(id=client_pk, company_id=company_id).first())
    if request.method == "POST":
        f   = request.form
        gst = f.get("gst_number", "").strip().upper()

        # GST uniqueness: check no OTHER client has the same GST
        if gst:
            existing_gst = cdb.query(Client).filter(
                Client.company_id == company_id,
                Client.gst_number == gst,
                Client.id != c.id
            ).first()
            if existing_gst:
                flash(f"GST number {gst} is already registered to client '{existing_gst.name}'.", "error")
                return render_template("client_form.html", client=_normalize_client(c), form_data=f)

        c.name            = f.get("client_name", c.name).strip()
        c.client_type     = f.get("client_type",     c.client_type)
        c.contact_person  = f.get("contact_person",  c.contact_person or "").strip()
        c.phone           = f.get("phone",            c.phone or "").strip()
        c.alternate_phone = f.get("alternate_phone",  c.alternate_phone or "").strip()
        c.email           = f.get("email",            c.email or "").strip().lower()
        c.website         = f.get("website",          c.website or "").strip()
        c.address_line1   = f.get("address_line1",    c.address_line1 or "").strip()
        c.address_line2   = f.get("address_line2",    c.address_line2 or "").strip()
        c.city            = f.get("city",             c.city or "").strip()
        c.state           = f.get("state",            c.state or "").strip()
        c.pincode         = f.get("pincode",          c.pincode or "").strip()
        c.country         = f.get("country",          c.country or "India").strip()
        c.gst_number      = gst or None
        c.pan_number      = f.get("pan_number",  c.pan_number or "").strip().upper() or None
        c.aadhar_number   = f.get("aadhar_number", c.aadhar_number or "").strip() or None
        c.gst_type        = f.get("gst_type",    c.gst_type)
        c.credit_limit    = float(f.get("credit_limit",    c.credit_limit    or 0) or 0)
        c.credit_days     = int(f.get("credit_days",       c.credit_days     or 30) or 30)
        c.opening_balance = float(f.get("opening_balance", c.opening_balance or 0) or 0)
        c.status          = f.get("status", c.status)
        c.notes           = f.get("notes",   c.notes or "").strip()
        cdb.commit()
        _save_client_id_docs(cdb, c, request.files)
        flash(f"Client '{c.name}' updated successfully!")
        return redirect(url_for("client_list"))
    return render_template("client_form.html", client=_normalize_client(c), form_data={})


def _client_closing_balance(cdb, company_id, c):
    """Live running balance exactly as the client statement page computes it:
    opening balance + all invoice totals − all recorded receipts (cash + bank)."""
    total_invoiced = sum(
        inv.grand_total or 0
        for inv in cdb.query(Invoice).filter_by(company_id=company_id, client_id=c.id)
                       .filter(Invoice.status.notin_(['Cancelled', 'Void', 'Draft'])).all()
    )
    cash_received = sum(
        t.amount or 0
        for t in cdb.query(CashTransaction).filter_by(
            company_id=company_id, party_name=c.name, category="Receipt").all()
    )
    bank_received = sum(
        t.amount or 0
        for t in cdb.query(BankTransaction).filter_by(
            company_id=company_id, party_name=c.name
        ).filter(BankTransaction.type == "credit").all()
    )
    return (c.opening_balance or 0) + total_invoiced - cash_received - bank_received


def _client_close_statement(cdb, company_id, c, action, scope="till_yesterday", as_of_date=None):
    """Archives the client's current live ledger into StatementClosing (so
    it can be printed later exactly as it stood), then moves the statement
    cutoff forward so the next statement load starts blank (action=
    'cleared') or with just the carried-forward balance (action=
    'carried_forward').

    `as_of_date`: the LAST date to include in the archived/closed
    statement. Everything dated ON or BEFORE it is archived; everything
    AFTER it stays live and becomes the first entries of the new
    statement (whose "Balance Carried Forward" date is as_of_date + 1
    day). Lets someone carry forward through, say, 30 June even though
    today is 5 July — the 1–5 July bills stay live in the new statement.
    If not given, it's derived from `scope` (only relevant for
    action='cleared'):
      - 'till_yesterday' (default): as_of_date = yesterday — today's
        entries stay live.
      - 'complete': as_of_date = today — nothing stays live.
    Clamped so it can never be before the day preceding the current
    statement_cutoff (which would resurrect already-archived entries)
    or after today (can't close a future date).
    Returns the amount that was outstanding at closing time."""
    today = today_ist()

    if as_of_date is None:
        if action == "cleared" and scope == "complete":
            as_of_date = today
        else:
            as_of_date = today - timedelta(days=1)

    if as_of_date > today:
        as_of_date = today
    if c.statement_cutoff:
        floor_date = c.statement_cutoff.date() - timedelta(days=1)
        if as_of_date < floor_date:
            as_of_date = floor_date

    archive_until = as_of_date + timedelta(days=1)  # exclusive upper bound

    ledger, total_debit, total_credit, closing = _build_client_ledger(
        cdb, company_id, c, since=c.statement_cutoff, until=archive_until)

    cdb.add(StatementClosing(
        company_id=company_id,
        entity_type="client",
        entity_id=c.id,
        entity_name=c.name,
        action=action,
        closing_balance=closing,
        total_debit=total_debit,
        total_credit=total_credit,
        ledger_snapshot=json.dumps(ledger, default=str),
        closed_by=session.get("username", "unknown"),
        closed_at=datetime.utcnow(),
    ))

    c.statement_cutoff = datetime.combine(archive_until, datetime.min.time())
    c.opening_balance = closing if action == "carried_forward" else 0
    c.pending = c.opening_balance
    return closing


# /clients/<id>/delete  ── kept at the old URL/template link so nothing else
# breaks, but this NO LONGER deletes the client row. Deleting Invoice rows
# would violate GST retention and break every FK pointing at invoices.id
# (purchase invoice lines, WhatsApp logs, cheques). This now archives the old
# statement and clears the live statement/outstanding — the client record
# and invoice history stay, viewable via the archived statement link.
@app.route("/clients/<int:client_pk>/delete", methods=["GET", "POST"])
@login_required
@owner_required
@require_admin_password
def client_delete(client_pk):
    cdb = get_cdb()
    company_id = get_current_company()
    c          = _first_or_404(cdb.query(Client).filter_by(id=client_pk, company_id=company_id).first())
    scope = request.args.get("scope", "till_yesterday")
    if scope not in ("complete", "till_yesterday"):
        scope = "till_yesterday"
    amount = _client_close_statement(cdb, company_id, c, action="cleared", scope=scope)
    cdb.commit()
    if amount:
        if scope == "complete":
            flash(f"Outstanding of {company_currency_symbol()} {amount:,.2f} cleared for '{c.name}', including today's entries. Old statement archived — client record and invoices were kept.")
        else:
            flash(f"Outstanding of {company_currency_symbol()} {amount:,.2f} cleared for '{c.name}' up to yesterday. Old statement archived — today's entries remain in the new statement.")
    else:
        flash(f"'{c.name}' had no outstanding to clear.")
    return redirect(url_for("client_list"))


# /clients/<id>/shift-to-opening  ── archives the itemised ledger the same
# way as above, but carries the amount forward as a single opening_balance
# figure instead of writing it off to zero. Defaults to yesterday, but an
# explicit ?as_of=YYYY-MM-DD lets the user pick an earlier cutoff (e.g.
# carry forward through 30 June even though today is 5 July) — anything
# after that date stays live in the new statement regardless.
@app.route("/clients/<int:client_pk>/shift-to-opening", methods=["GET", "POST"])
@login_required
@owner_required
@require_admin_password
def client_shift_to_opening(client_pk):
    cdb = get_cdb()
    company_id = get_current_company()
    c          = _first_or_404(cdb.query(Client).filter_by(id=client_pk, company_id=company_id).first())
    as_of_date = None
    as_of_raw = request.args.get("as_of")
    if as_of_raw:
        try:
            as_of_date = datetime.strptime(as_of_raw, "%Y-%m-%d").date()
        except ValueError:
            as_of_date = None
    amount = _client_close_statement(cdb, company_id, c, action="carried_forward", as_of_date=as_of_date)
    cdb.commit()
    flash(f"{company_currency_symbol()} {amount:,.2f} carried forward as opening balance for '{c.name}', as of "
          f"{(c.statement_cutoff - timedelta(days=1)).strftime('%d %b %Y')}. New statement starts "
          f"{c.statement_cutoff.strftime('%d %b %Y')}; entries from then on stay live.")
    return redirect(url_for("client_list"))


# ─────────────────────────────────────────────────────────────────────────────
# ── Stock / Inventory (Standard ERP Product Master & Stock Ledger) ───────────
# ─────────────────────────────────────────────────────────────────────────────


@app.route("/inventory")
@login_required
@require_permission("stock", "view")
def inventory_list():
    cdb = get_customer_session(get_current_company())
    company_id = get_current_company()

    items = cdb.query(StockItem).filter_by(company_id=company_id).order_by(StockItem.name.asc()).all()

    total_products = len(items)
    total_stock_qty = 0.0
    total_valuation = 0.0
    low_stock_count = 0
    out_of_stock_count = 0
    categories_set = set()

    for item in items:
        qty = float(item.quantity or 0.0)
        cost = float(item.purchase_rate or item.last_purchase_rate or item.unit_price or 0.0)
        reorder = float(item.reorder_level or 10.0)

        total_stock_qty += qty
        total_valuation += (qty * cost)

        if qty <= 0:
            out_of_stock_count += 1
        elif qty <= reorder:
            low_stock_count += 1

        if item.category and item.category.strip():
            categories_set.add(item.category.strip())

    categories = sorted(list(categories_set))
    today_date = today_ist().strftime("%Y-%m-%d")

    return render_template("inventory.html",
        items=items,
        total_products=total_products,
        total_stock_qty=total_stock_qty,
        total_valuation=total_valuation,
        low_stock_count=low_stock_count,
        out_of_stock_count=out_of_stock_count,
        categories=categories,
        today_date=today_date
    )


@app.route("/inventory/new", methods=["GET", "POST"])
@app.route("/inventory/add", methods=["GET", "POST"])
@login_required
@require_permission("stock", "create")
def inventory_add():
    """Create a new product in master inventory with opening stock / direct inward (Way 2)"""
    cdb = get_customer_session(get_current_company())
    company_id = get_current_company()

    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        if not code:
            code = _next_numbered_id(cdb, StockItem.code, "PROD-", extra_filters=[StockItem.company_id == company_id])

        name = request.form.get("name", "").strip()
        category = request.form.get("category", "Finished Goods").strip()
        hsn = request.form.get("hsn", "").strip()
        unit = request.form.get("unit", "pcs").strip()

        try:
            quantity = float(request.form.get("quantity", 0))
        except ValueError:
            quantity = 0.0

        try:
            reorder_level = float(request.form.get("reorder_level", 10))
        except ValueError:
            reorder_level = 10.0

        try:
            purchase_rate = float(request.form.get("purchase_rate", 0))
        except ValueError:
            purchase_rate = 0.0

        try:
            selling_price = float(request.form.get("selling_price", 0))
        except ValueError:
            selling_price = 0.0

        try:
            gst_percent = billing_rate(get_company_by_id(company_id), request.form.get("gst_percent"))
        except ValueError:
            gst_percent = billing_rate(get_company_by_id(company_id))

        margin_percent = 0.0
        if purchase_rate > 0:
            margin_percent = ((selling_price - purchase_rate) / purchase_rate) * 100.0

        item = StockItem(
            company_id=company_id,
            code=code,
            name=name,
            category=category,
            quantity=quantity,
            unit=unit,
            unit_price=selling_price,
            purchase_rate=purchase_rate,
            last_purchase_rate=purchase_rate,
            avg_purchase_rate=purchase_rate,
            selling_price=selling_price,
            gst_percent=gst_percent,
            margin_percent=margin_percent,
            reorder_level=reorder_level,
            hsn=hsn,
            last_updated=today_ist().date(),
        )
        cdb.add(item)
        cdb.flush()

        # If opening stock > 0, record in StockPurchaseHistory as IN
        if quantity > 0:
            cdb.add(StockPurchaseHistory(
                stock_item_id=item.id,
                quantity=quantity,
                purchase_rate=purchase_rate,
                gst_percent=gst_percent,
                purchase_date=today_ist().date(),
                movement_type="IN",
                reference="Opening Stock / Direct Inward"
            ))

        cdb.commit()
        flash(f"Product '{item.name}' ({item.code}) created with {quantity} {unit} stock!", "success")
        return redirect(url_for("inventory_list"))

    return render_template("inventory_form.html", item=None)


@app.route("/inventory/edit/<int:item_pk>", methods=["GET", "POST"])
@login_required
@require_permission("stock", "edit")
def inventory_edit(item_pk):
    """Edit product master details"""
    cdb = get_customer_session(get_current_company())
    company_id = get_current_company()
    item = _first_or_404(cdb.query(StockItem).filter_by(id=item_pk, company_id=company_id).first())

    if request.method == "POST":
        old_qty = float(item.quantity or 0.0)

        item.name = request.form.get("name", item.name).strip()
        item.category = request.form.get("category", item.category).strip()
        item.hsn = request.form.get("hsn", item.hsn).strip()
        item.unit = request.form.get("unit", item.unit).strip()

        try:
            new_qty = float(request.form.get("quantity", item.quantity))
        except ValueError:
            new_qty = old_qty

        try:
            item.reorder_level = float(request.form.get("reorder_level", item.reorder_level))
        except ValueError:
            pass

        try:
            purchase_rate = float(request.form.get("purchase_rate", item.purchase_rate or 0))
            item.purchase_rate = purchase_rate
            item.last_purchase_rate = purchase_rate
        except ValueError:
            pass

        try:
            selling_price = float(request.form.get("selling_price", item.selling_price or 0))
            item.selling_price = selling_price
            item.unit_price = selling_price
        except ValueError:
            pass

        try:
            item.gst_percent = billing_rate(get_company_by_id(company_id), request.form.get("gst_percent", item.gst_percent))
        except ValueError:
            pass

        if (item.purchase_rate or 0) > 0 and (item.selling_price or 0) > 0:
            item.margin_percent = (((item.selling_price - item.purchase_rate) / item.purchase_rate) * 100.0)

        item.quantity = new_qty
        item.last_updated = today_ist().date()

        # If quantity changed during edit, log ADJUST in ledger
        diff = new_qty - old_qty
        if abs(diff) > 0.0001:
            cdb.add(StockPurchaseHistory(
                stock_item_id=item.id,
                quantity=diff,
                purchase_rate=item.purchase_rate or 0.0,
                gst_percent=item.gst_percent or 0.0,
                purchase_date=today_ist().date(),
                movement_type="ADJUST",
                reference="Manual Inventory Edit"
            ))

        cdb.commit()
        flash(f"Product '{item.name}' ({item.code}) updated successfully!", "success")
        return redirect(url_for("inventory_list"))

    return render_template("inventory_form.html", item=item)


@app.route("/stock/inward", methods=["POST"])
@login_required
@require_permission("stock", "create")
def stock_inward_direct():
    """Direct stock inward (Way 2: No purchase bill required)"""
    cdb = get_customer_session(get_current_company())
    company_id = get_current_company()

    stock_item_id = request.form.get("stock_item_id")
    if not stock_item_id:
        flash("Please select a product for stock inward.", "error")
        return redirect(url_for("inventory_list"))

    item = cdb.query(StockItem).filter_by(id=int(stock_item_id), company_id=company_id).first()
    if not item:
        flash("Product not found.", "error")
        return redirect(url_for("inventory_list"))

    try:
        qty = float(request.form.get("quantity", 0))
    except ValueError:
        qty = 0.0

    if qty <= 0:
        flash("Inward quantity must be greater than 0.", "error")
        return redirect(url_for("inventory_list"))

    try:
        rate = float(request.form.get("purchase_rate", item.purchase_rate or item.unit_price))
    except ValueError:
        rate = float(item.purchase_rate or item.unit_price or 0.0)

    reference = request.form.get("reference", "").strip() or "Direct Inward"
    date_str = request.form.get("inward_date")
    try:
        inward_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else today_ist().date()
    except ValueError:
        inward_date = today_ist().date()

    # Update stock
    item.quantity = (item.quantity or 0.0) + qty
    if rate > 0:
        item.last_purchase_rate = rate
        item.purchase_rate = rate
    item.last_updated = inward_date

    # Log Stock Movement History
    cdb.add(StockPurchaseHistory(
        stock_item_id=item.id,
        quantity=qty,
        purchase_rate=rate,
        gst_percent=item.gst_percent or 0.0,
        purchase_date=inward_date,
        movement_type="IN",
        reference=reference
    ))

    cdb.commit()
    flash(f"Successfully inwarded +{qty} {item.unit} for '{item.name}' ({item.code})!", "success")
    return redirect(url_for("inventory_list"))


@app.route("/stock/adjust", methods=["POST"])
@login_required
@require_permission("stock", "edit")
def stock_adjust():
    """Quick quantity adjustment / audit correction"""
    cdb = get_customer_session(get_current_company())
    company_id = get_current_company()

    if request.is_json:
        data = request.get_json(force=True)
        code = data.get("code", "").strip().upper()
        item = _first_or_404(cdb.query(StockItem).filter_by(company_id=company_id, code=code).first())
        old_qty = float(item.quantity or 0.0)
        new_qty = float(data.get("quantity", item.quantity))
        reason = data.get("reason", "Stock Adjustment")
    else:
        item_id = request.form.get("stock_item_id")
        item = _first_or_404(cdb.query(StockItem).filter_by(id=int(item_id), company_id=company_id).first())
        old_qty = float(item.quantity or 0.0)
        new_qty = float(request.form.get("quantity", old_qty))
        reason = request.form.get("reason", "Stock Adjustment")

    diff = new_qty - old_qty
    item.quantity = new_qty
    item.last_updated = today_ist().date()

    if abs(diff) > 0.0001:
        cdb.add(StockPurchaseHistory(
            stock_item_id=item.id,
            quantity=diff,
            purchase_rate=item.purchase_rate or 0.0,
            gst_percent=item.gst_percent or 0.0,
            purchase_date=today_ist().date(),
            movement_type="ADJUST",
            reference=reason
        ))

    cdb.commit()
    if request.is_json:
        return jsonify({"success": True, "new_quantity": new_qty})
    flash(f"Stock for '{item.name}' adjusted to {new_qty} {item.unit}.", "success")
    return redirect(url_for("inventory_list"))


@app.route("/stock/movements/<item_identifier>")
@login_required
@require_permission("stock", "view")
def stock_movements(item_identifier):
    """Return chronological movement history for a stock item (IN/OUT/ADJUST)"""
    cdb = get_customer_session(get_current_company())
    company_id = get_current_company()

    item = None
    if str(item_identifier).isdigit():
        item = cdb.query(StockItem).filter_by(id=int(item_identifier), company_id=company_id).first()
    if not item:
        item = cdb.query(StockItem).filter_by(code=str(item_identifier).upper(), company_id=company_id).first()

    if not item:
        return jsonify({"error": "Item not found"}), 404

    history = (
        cdb.query(StockPurchaseHistory)
        .filter_by(stock_item_id=item.id)
        .order_by(StockPurchaseHistory.purchase_date.desc(), StockPurchaseHistory.id.desc())
        .all()
    )

    movements = []
    total_in = 0.0
    total_out = 0.0

    for h in history:
        qty = float(h.quantity or 0.0)
        mtype = (h.movement_type or "IN").upper()

        if h.purchase_invoice_id:
            inv = cdb.get(PurchaseInvoice, h.purchase_invoice_id)
            ref = inv.invoice_number or inv.invoice_id if inv else f"PB-{h.purchase_invoice_id}"
            label_type = "Purchase Bill"
            is_in = True
        elif mtype == "OUT" or qty < 0:
            label_type = "Sales Invoice"
            ref = h.reference or "Sales Invoice"
            is_in = False
        elif mtype == "ADJUST":
            label_type = "Adjustment"
            ref = h.reference or "Stock Audit / Adjustment"
            is_in = (qty >= 0)
        else:
            label_type = "Opening Stock" if "opening" in (h.reference or "").lower() else "Direct Inward"
            ref = h.reference or "Direct Inward"
            is_in = True

        if is_in:
            total_in += abs(qty)
        else:
            total_out += abs(qty)

        movements.append({
            "id": h.id,
            "date": h.purchase_date.strftime("%d %b %Y") if h.purchase_date else "—",
            "type": label_type,
            "ref": ref,
            "quantity": qty if (not is_in and qty < 0) else abs(qty),
            "rate": float(h.purchase_rate or 0.0),
            "is_in": is_in,
        })

    return jsonify({
        "id": item.id,
        "code": item.code,
        "name": item.name,
        "unit": item.unit or "pcs",
        "quantity": float(item.quantity or 0.0),
        "total_in": total_in,
        "total_out": total_out,
        "movements": movements,
    })


@app.route("/inventory/delete/<int:item_pk>", methods=["POST"])
@login_required
@require_permission("stock", "delete")
def inventory_delete(item_pk):
    """Delete a product item from inventory"""
    cdb = get_customer_session(get_current_company())
    company_id = get_current_company()
    item = _first_or_404(cdb.query(StockItem).filter_by(id=item_pk, company_id=company_id).first())

    item_name = item.name
    item_code = item.code
    cdb.delete(item)
    cdb.commit()
    flash(f"Product '{item_name}' ({item_code}) deleted.", "info")
    return redirect(url_for("inventory_list"))


@app.route("/api/stock/items")
@login_required
@require_permission("stock", "view")
def api_stock_items():
    """Return JSON array of items for auto-completion in forms"""
    cdb = get_customer_session(get_current_company())
    company_id = get_current_company()
    items = cdb.query(StockItem).filter_by(company_id=company_id).order_by(StockItem.name.asc()).all()
    return jsonify([{
        "id":            item.id,
        "code":          item.code or "",
        "name":          item.name,
        "unit":          item.unit or "pcs",
        "quantity":      float(item.quantity or 0.0),
        "unit_price":    float(item.unit_price or item.selling_price or 0.0),
        "selling_price": float(item.selling_price or item.unit_price or 0.0),
        "purchase_rate": float(item.purchase_rate or item.last_purchase_rate or 0.0),
        "gst_percent":   float(item.gst_percent if item.gst_percent is not None else billing_rate(get_company_by_id(company_id))),
        "hsn":           item.hsn or "",
        "category":      item.category or "",
        "reorder_level": float(item.reorder_level or 10.0),
    } for item in items])


@app.route("/stock/item/<code>")
@login_required
@require_permission("stock", "view")
def stock_item_get(code):
    """Get single stock item by code"""
    cdb = get_customer_session(get_current_company())
    company_id = get_current_company()
    item = _first_or_404(cdb.query(StockItem).filter_by(company_id=company_id, code=code.upper()).first())
    return jsonify({
        "id":            item.id,
        "code":          item.code,
        "name":          item.name,
        "category":      item.category or "",
        "quantity":      float(item.quantity or 0.0),
        "unit":          item.unit or "pcs",
        "unit_price":    float(item.unit_price or item.selling_price or 0.0),
        "selling_price": float(item.selling_price or item.unit_price or 0.0),
        "purchase_rate": float(item.purchase_rate or item.last_purchase_rate or 0.0),
        "reorder_level": float(item.reorder_level or 10.0),
        "hsn":           item.hsn or "",
        "gst_percent":   float(item.gst_percent if item.gst_percent is not None else billing_rate(get_company_by_id(company_id))),
    })


# ── Purchase Invoice Routes ─────────────────────────────────────────────────────────

@app.route("/purchase/list")
@login_required
@require_permission("purchase", "view")
def purchase_invoice_list():
    cdb = get_cdb()
    company_id = get_current_company()
    invoices = cdb.query(PurchaseInvoice).filter_by(company_id=company_id).order_by(PurchaseInvoice.date.desc()).all()

    print("=== Purchase Invoice Debug ===")
    for inv in invoices:
        print(f"ID: {inv.id}, invoice_id: {inv.invoice_id}, supplier: {inv.supplier.name if inv.supplier else 'None'}")
    
    total_amount = sum(p.grand_total for p in invoices)
    total_paid = sum(p.paid_amount for p in invoices)
    total_due = sum(p.balance for p in invoices)

    suppliers = cdb.query(Supplier).filter_by(company_id=company_id, status="Active").order_by(Supplier.name).all()
    stock_items = cdb.query(StockItem).filter_by(company_id=company_id).order_by(StockItem.name).all()
    company = Company.query.filter_by(company_id=company_id).first()
    
    return render_template("purchases.html",
        purchases=invoices,
        total_amount=total_amount,
        total_paid=total_paid,
        total_due=total_due,
        suppliers=suppliers,
        stock_items=stock_items,
        company=company
    )



COURIER_OPTIONS = ["Bluedart", "DHL", "DTDC", "DPD", "FedEx", "Delhivery", "Ecom Express", "India Post", "Other"]
ITEM_TYPE_OPTIONS = ["Box", "Envelope", "Crate", "Pouch", "Carton"]

@app.route("/purchase/delete/<invoice_id>", methods=["POST"])
@login_required
@owner_required
@require_admin_password
def purchase_invoice_delete(invoice_id):
    cdb        = get_cdb()
    company_id = get_current_company()

    invoice = cdb.query(PurchaseInvoice).filter_by(
        invoice_id=invoice_id, company_id=company_id
    ).first()

    if not invoice:
        abort(404)

    if invoice.note_adjustment:
        flash("Cancel the posted credit/debit notes before editing or deleting this invoice.", "warning")
        return redirect(url_for("purchase_invoice_view", invoice_id=invoice_id))

    # ── Reverse stock deductions ──────────────────────────────────────────────
    # When a purchase bill was created, stock was DEDUCTED (OUT movement).
    # Deleting the bill reverses that: add stock back.
    for item in invoice.items:
        if item.stock_item_id and item.quantity:
            stock = cdb.query(StockItem).filter_by(
                id=item.stock_item_id, company_id=company_id
            ).first()
            if stock:
                stock.quantity    = (stock.quantity or 0) + item.quantity
                stock.last_updated = today_ist()

    # ── Reverse supplier payable ──────────────────────────────────────────────
    # Only reverse the UNPAID portion (paid_amount was already deducted from
    # supplier.payable when payments were recorded).
    if invoice.supplier_id:
        supplier = cdb.get(Supplier, invoice.supplier_id)
        if supplier:
            unpaid = invoice.balance or 0
            supplier.payable = max(0, (supplier.payable or 0) - unpaid)

    # cascade="all, delete-orphan" on items + purchase_history handles child rows
    cdb.delete(invoice)
    _reverse_source_journal(cdb, company_id, "purchase_invoice", invoice.id,
                            f"Purchase invoice {invoice.invoice_number or invoice.invoice_id} deleted")
    cdb.commit()

    flash(f"Purchase {invoice_id} deleted and stock restored.")
    return redirect(url_for("purchase_invoice_list"))


@app.route("/api/purchase/scan-bill", methods=["POST"])
@login_required
@require_permission("purchase", "view")
def api_purchase_scan_bill():
    """
    Direct local OCR / PDF bill scanner endpoint.
    Extracts vendor/supplier information, invoice metadata, line items, and financial totals.
    """
    if "bill_file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    file = request.files["bill_file"]
    if not file or not file.filename:
        return jsonify({"success": False, "error": "No file selected"}), 400

    allowed_exts = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
    ext = os.path.splitext(file.filename.lower())[1]
    if ext not in allowed_exts:
        return jsonify({"success": False, "error": "Please upload a PDF or image file (.pdf, .png, .jpg, .jpeg)"}), 400

    try:
        cdb = get_cdb()
        company_id = get_current_company()
        company = Company.query.filter_by(company_id=company_id).first()

        company_info = {
            "company_name": company.company_name if company else "",
            "gst_number": getattr(company, "gst_number", "") or "",
            "state": getattr(company, "state", "Maharashtra") or "Maharashtra",
            "email": company.email if company else ""
        }

        existing_suppliers = cdb.query(Supplier).filter_by(company_id=company_id).all()
        existing_stock_items = cdb.query(StockItem).filter_by(company_id=company_id).all()

        from ocr_parser import parse_purchase_invoice

        parsed_data = parse_purchase_invoice(
            file.stream,
            filename=file.filename,
            company_info=company_info,
            existing_suppliers=existing_suppliers,
            existing_stock_items=existing_stock_items
        )

        # -------------------------------------------------------------------------
        # Ensure every extracted item has an accurate product code:
        # If product already exists in stock: take that product's code (and set stock_item_id)
        # If product does NOT exist in stock: generate sequential PROD-xxx product code
        # -------------------------------------------------------------------------
        prefix = "PROD-"
        existing_codes_q = cdb.query(StockItem.code).filter(
            StockItem.company_id == company_id,
            StockItem.code.like(f"{prefix}%")
        ).all()
        max_num = 0
        for (c_val,) in existing_codes_q:
            if not c_val:
                continue
            tail = c_val[len(prefix):]
            try:
                max_num = max(max_num, int(tail))
            except ValueError:
                continue

        next_code_num = max_num + 1

        stock_by_id = {st.id: st for st in existing_stock_items}
        stock_by_code = {st.code.strip().lower(): st for st in existing_stock_items if st.code}
        stock_by_name = {st.name.strip().lower(): st for st in existing_stock_items if st.name}

        for item in parsed_data.get("items", []):
            st = None
            st_id = item.get("stock_item_id")
            i_code = (item.get("item_code") or "").strip()
            i_name = (item.get("item_name") or "").strip().lower()

            if st_id and st_id in stock_by_id:
                st = stock_by_id[st_id]
            elif i_code and i_code.lower() in stock_by_code:
                st = stock_by_code[i_code.lower()]
            elif i_name and i_name in stock_by_name:
                st = stock_by_name[i_name]
            elif i_name and len(i_name) > 3:
                for k_name, candidate_st in stock_by_name.items():
                    if k_name in i_name or i_name in k_name:
                        st = candidate_st
                        break

            if st:
                # Existing product: adopt product code from stock
                item["stock_item_id"] = st.id
                item["item_code"] = st.code
                item["matched_existing"] = True
                if not item.get("hsn") and st.hsn:
                    item["hsn"] = st.hsn
                if not item.get("unit") and st.unit:
                    item["unit"] = st.unit
            else:
                # New product: generate new product code and show in product code column
                item["stock_item_id"] = None
                item["matched_existing"] = False
                item["item_code"] = f"{prefix}{next_code_num:03d}"
                next_code_num += 1

        # Save scanned file into upload folder so it can be saved with invoice
        filename = secure_filename(f"OCR_{company_id}_{int(datetime.now().timestamp())}_{file.filename}")
        upload_dir = app.config.get("UPLOAD_FOLDER", os.path.join(app.root_path, "uploads", "purchase_invoices"))
        os.makedirs(upload_dir, exist_ok=True)
        filepath = os.path.join(upload_dir, filename)
        file.seek(0)
        file.save(filepath)

        parsed_data["saved_filename"] = filename
        parsed_data["stock_items_list"] = [
            {"id": st.id, "code": st.code, "name": st.name, "hsn": st.hsn or "", "unit": st.unit or "pcs", "rate": float(st.purchase_rate or st.last_purchase_rate or 0.0)}
            for st in existing_stock_items
        ]
        parsed_data["suppliers_list"] = [
            {"id": s.id, "name": s.name, "gstin": (getattr(s, "gst_number", None) or getattr(s, "gstin", None) or ""), "phone": getattr(s, "phone", "") or "", "state": getattr(s, "state", "") or ""}
            for s in existing_suppliers
        ]

        base_currency = (getattr(company, "currency", None) or "INR").upper()
        detected_currency = (parsed_data.get("currency") or "INR").upper()
        exchange_rate = currency_service.get_exchange_rate(detected_currency, base_currency)

        parsed_data["currency"] = detected_currency
        parsed_data["base_currency"] = base_currency
        parsed_data["exchange_rate"] = exchange_rate
        parsed_data["currencies_list"] = currency_service.get_all_currencies_list()

        return jsonify(parsed_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"OCR processing failed: {str(e)}"}), 500


@app.route("/uploads/purchase_invoices/<path:filename>")
@app.route("/purchase/file/<path:filename>")
@login_required
def serve_purchase_invoice_file(filename):
    """Serve uploaded purchase bill PDFs and images safely"""
    from flask import send_from_directory
    upload_dir = app.config.get("UPLOAD_FOLDER", os.path.join(app.root_path, "uploads", "purchase_invoices"))
    if os.path.exists(os.path.join(upload_dir, filename)):
        return send_from_directory(upload_dir, filename)
    if os.path.exists(os.path.join(app.root_path, "uploads", filename)):
        return send_from_directory(os.path.join(app.root_path, "uploads"), filename)
    if os.path.exists(os.path.join(app.root_path, "static", filename)):
        return send_from_directory(os.path.join(app.root_path, "static"), filename)
    abort(404)


@app.route("/purchase/new", methods=["GET", "POST"])
@login_required
@require_permission("purchase", "view", method_actions={'POST': 'create'})
def purchase_invoice_new():
    """Create a new standard ERP purchase bill / invoice"""
    cdb = get_cdb()
    company_id = get_current_company()
    company = Company.query.filter_by(company_id=company_id).first()

    if request.method == "POST":
        invoice_id = request.form.get("invoice_id", "").strip()
        supplier_id_raw = request.form.get("supplier_id", "").strip()
        supplier_id = int(supplier_id_raw) if supplier_id_raw and supplier_id_raw.isdigit() else None
        supplier_name = request.form.get("supplier_name", "").strip()
        supplier_gstin = request.form.get("supplier_gstin", "").strip()
        supplier_state = request.form.get("supplier_state", "").strip()
        supplier_address = request.form.get("supplier_address", "").strip()
        supplier_phone = request.form.get("supplier_phone", "").strip()
        supplier_email = request.form.get("supplier_email", "").strip()
        invoice_number = request.form.get("invoice_number", "").strip()
        reference_po_no = request.form.get("reference_po_no", "").strip()
        date_str = request.form.get("date")
        due_date_str = request.form.get("due_date")
        payment_terms = request.form.get("payment_terms", "Net 30 Days").strip()
        status = request.form.get("status", "Pending").strip()
        terms = request.form.get("terms", "").strip()
        notes = request.form.get("notes", "").strip()
        auto_add_stock = bool(request.form.get("auto_add_stock"))

        inv_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else today_ist().date()
        due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date() if due_date_str else inv_date

        # Ensure invoice_id is unique across purchase_invoices
        if not invoice_id or cdb.query(PurchaseInvoice).filter_by(invoice_id=invoice_id).first():
            prefix = "PB-"
            q = cdb.query(PurchaseInvoice.invoice_id).filter(PurchaseInvoice.invoice_id.like(f"{prefix}%")).all()
            max_num = 0
            for (val,) in q:
                if not val:
                    continue
                tail = val[len(prefix):]
                try:
                    max_num = max(max_num, int(tail))
                except ValueError:
                    continue
            invoice_id = f"{prefix}{max_num + 1:03d}"

        # Auto-create supplier if new name typed
        if not supplier_id and supplier_name:
            sup = cdb.query(Supplier).filter_by(company_id=company_id, name=supplier_name).first()
            if not sup:
                company_obj = Company.query.filter_by(company_id=company_id).first()
                supplier_prefix = _company_name_prefix(company_obj.company_name if company_obj else "", from_end=False)
                new_supplier_id = _next_numbered_id(cdb, Supplier.supplier_id, supplier_prefix, extra_filters=[Supplier.company_id == company_id])
                sup = Supplier(
                    supplier_id=new_supplier_id,
                    company_id=company_id,
                    name=supplier_name,
                    gst_number=supplier_gstin or None,
                    state=supplier_state or None,
                    address_line1=supplier_address or None,
                    phone=supplier_phone or None,
                    email=supplier_email or None,
                    status="Active",
                    created_at=today_ist().date() if hasattr(today_ist(), "date") else today_ist()
                )
                cdb.add(sup)
                cdb.flush()
            supplier_id = sup.id

        # Parse Line Items
        item_codes = request.form.getlist("item_code[]")
        item_names = request.form.getlist("item_name[]")
        hsns = request.form.getlist("hsn[]")
        quantities = request.form.getlist("quantity[]")
        units = request.form.getlist("unit[]")
        rates = request.form.getlist("rate[]")
        discount_percents = request.form.getlist("discount_percent[]")
        gst_percents = request.form.getlist("gst_percent[]")
        stock_item_ids = request.form.getlist("stock_item_id[]")

        subtotal = 0.0
        vat_total = 0.0
        cgst_total = 0.0
        sgst_total = 0.0
        igst_total = 0.0

        company_state = (company.state or "").strip().lower() if company else ""
        s_state = (supplier_state or "").strip().lower()
        is_interstate = bool(company_state and s_state and company_state != s_state)

        # Multi-currency & regional tax parameters
        base_currency = (company.currency if company and company.currency else "INR").strip().upper()
        doc_currency = (request.form.get("currency") or base_currency).strip().upper()
        try:
            exchange_rate = float(request.form.get("exchange_rate") or 1.0)
            if exchange_rate <= 0:
                exchange_rate = 1.0
        except (ValueError, TypeError):
            exchange_rate = 1.0

        if doc_currency == base_currency:
            exchange_rate = 1.0

        tax_regime = tax_profile(company)['regime']
        tax_type = (request.form.get("tax_type") or ("Import" if doc_currency != base_currency else ("IGST" if is_interstate else "CGST_SGST"))).strip()

        purchase_inv = PurchaseInvoice(
            invoice_id=invoice_id,
            company_id=company_id,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            supplier_address=supplier_address,
            supplier_gstin=supplier_gstin,
            supplier_state=supplier_state,
            supplier_phone=supplier_phone,
            supplier_email=supplier_email,
            invoice_number=invoice_number,
            reference_po_no=reference_po_no,
            date=inv_date,
            due_date=due_date,
            currency=doc_currency,
            exchange_rate=exchange_rate,
            tax_regime=tax_regime,
            tax_type=tax_type,
            payment_terms=payment_terms,
            status=status,
            terms=terms,
            notes=notes,
            created_by=session.get("user", {}).get("username") or session.get("user_id"),
        )
        cdb.add(purchase_inv)
        cdb.flush()

        for i in range(len(item_names)):
            name = item_names[i].strip() if i < len(item_names) else ""
            if not name:
                continue
            code = item_codes[i].strip() if i < len(item_codes) else ""
            hsn = hsns[i].strip() if i < len(hsns) else ""
            try:
                qty = float(quantities[i]) if i < len(quantities) and quantities[i] else 1.0
            except ValueError:
                qty = 1.0
            unit = units[i].strip() if i < len(units) and units[i] else "pcs"
            try:
                rate = float(rates[i]) if i < len(rates) and rates[i] else 0.0
            except ValueError:
                rate = 0.0
            try:
                disc_pct = float(discount_percents[i]) if i < len(discount_percents) and discount_percents[i] else 0.0
            except ValueError:
                disc_pct = 0.0
            try:
                gst_pct = float(gst_percents[i]) if i < len(gst_percents) and gst_percents[i] else 0.0
            except ValueError:
                gst_pct = 0.0

            st_id = None
            if i < len(stock_item_ids) and stock_item_ids[i] and stock_item_ids[i].isdigit():
                st_id = int(stock_item_ids[i])

            base_val = qty * rate
            disc_amt = base_val * (disc_pct / 100.0)
            taxable = base_val - disc_amt
            gst_pct = billing_rate(company, gst_percents[i] if i < len(gst_percents) else None)
            tax_amt, cgst_amt, sgst_amt, igst_amt = split_tax(taxable, gst_pct, tax_regime, is_interstate)
            vat_total += tax_amt if tax_regime not in ('GST', 'INDIA_GST') else 0.0

            row_total = taxable + tax_amt

            subtotal += taxable
            cgst_total += cgst_amt
            sgst_total += sgst_amt
            igst_total += igst_amt

            # Line item base currency values (accounting in base currency)
            base_rate = round(rate * exchange_rate, 4)
            base_taxable = round(taxable * exchange_rate, 2)
            base_row_total = round(row_total * exchange_rate, 2)

            # Auto-update stock inventory & resolve stock item
            stock = None
            if auto_add_stock:
                # 1. Prioritize user-specified / edited code
                if code:
                    stock = cdb.query(StockItem).filter_by(code=code, company_id=company_id).first()
                # 2. Fallback to st_id if not found by code
                if not stock and st_id:
                    stock = cdb.query(StockItem).filter_by(id=st_id, company_id=company_id).first()
                # 3. Fallback to name if not found by code/st_id
                if not stock and name:
                    stock = cdb.query(StockItem).filter_by(name=name, company_id=company_id).first()

                if not stock and (name or code):
                    if not code:
                        code = _next_numbered_id(cdb, StockItem.code, "PROD-", extra_filters=[StockItem.company_id == company_id])
                    stock = StockItem(
                        company_id=company_id,
                        code=code,
                        name=name or code,
                        category="Finished Goods",
                        quantity=qty,
                        unit=unit or "pcs",
                        unit_price=base_rate * 1.25,
                        purchase_rate=base_rate,
                        last_purchase_rate=base_rate,
                        avg_purchase_rate=base_rate,
                        selling_price=base_rate * 1.25,
                        gst_percent=gst_pct,
                        reorder_level=10.0,
                        hsn=hsn,
                        last_updated=inv_date
                    )
                    cdb.add(stock)
                    cdb.flush()
                elif stock:
                    stock.quantity = (stock.quantity or 0.0) + qty
                    if base_rate > 0:
                        stock.last_purchase_rate = base_rate
                        stock.purchase_rate = base_rate
                    stock.last_updated = inv_date
                    if not code:
                        code = stock.code

            resolved_stock_id = stock.id if stock else st_id
            resolved_code = code or (stock.code if stock else "")

            pi_item = PurchaseInvoiceItem(
                purchase_invoice_id=purchase_inv.id,
                stock_item_id=resolved_stock_id,
                item_code=resolved_code,
                code=resolved_code,
                item_name=name,
                description=name,
                hsn=hsn,
                quantity=qty,
                unit=unit,
                rate=rate,
                purchase_rate=rate,
                base_rate=base_rate,
                discount_percent=disc_pct,
                taxable_amount=taxable,
                taxable_value=taxable,
                base_taxable_amount=base_taxable,
                gst_percent=gst_pct,
                cgst_amount=cgst_amt,
                sgst_amount=sgst_amt,
                igst_amount=igst_amt,
                total_amount=row_total,
                base_total_amount=base_row_total,
                party_name=supplier_name
            )
            cdb.add(pi_item)

            if stock:
                cdb.add(StockPurchaseHistory(
                    stock_item_id=stock.id,
                    purchase_invoice_id=purchase_inv.id,
                    quantity=qty,
                    purchase_rate=rate,
                    currency=doc_currency,
                    exchange_rate=exchange_rate,
                    base_purchase_rate=base_rate,
                    gst_percent=gst_pct,
                    purchase_date=inv_date,
                    movement_type="IN",
                    reference=purchase_inv.invoice_number or purchase_inv.invoice_id
                ))

        tax_total = cgst_total + sgst_total + igst_total
        grand_total = subtotal + tax_total

        purchase_inv.subtotal = round(subtotal, 2)
        purchase_inv.cgst_total = round(cgst_total, 2)
        purchase_inv.sgst_total = round(sgst_total, 2)
        purchase_inv.igst_total = round(igst_total, 2)
        purchase_inv.tax_amount = round(tax_total, 2)
        purchase_inv.grand_total = round(grand_total, 2)
        purchase_inv.balance = round(grand_total - (purchase_inv.paid_amount or 0.0), 2)

        # Multi-currency Base Currency equivalents
        purchase_inv.base_subtotal = round(purchase_inv.subtotal * exchange_rate, 2)
        purchase_inv.base_tax_amount = round(purchase_inv.tax_amount * exchange_rate, 2)
        purchase_inv.base_grand_total = round(purchase_inv.grand_total * exchange_rate, 2)
        purchase_inv.base_paid_amount = round((purchase_inv.paid_amount or 0.0) * exchange_rate, 2)
        purchase_inv.base_balance = round(purchase_inv.balance * exchange_rate, 2)

        # Handle file upload if any
        if "invoice_file" in request.files and request.files["invoice_file"].filename:
            file = request.files["invoice_file"]
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(f"{purchase_inv.invoice_id}_{file.filename}")
                upload_dir = app.config.get("UPLOAD_FOLDER", os.path.join(app.root_path, "uploads", "purchase_invoices"))
                os.makedirs(upload_dir, exist_ok=True)
                filepath = os.path.join(upload_dir, filename)
                file.save(filepath)
                purchase_inv.file_path = filename
        elif request.form.get("scanned_file_path"):
            purchase_inv.file_path = request.form.get("scanned_file_path").strip()

        if request.form.get("ocr_json_data"):
            purchase_inv.ocr_data = request.form.get("ocr_json_data").strip()

        # Update supplier payable in base currency
        if supplier_id:
            supplier = cdb.get(Supplier, supplier_id)
            if supplier:
                supplier.payable = (supplier.payable or 0.0) + purchase_inv.base_balance
                if not supplier.currency and doc_currency != base_currency:
                    supplier.currency = doc_currency

        _auto_post_purchase_invoice(cdb, company_id, purchase_inv)
        cdb.commit()
        log_audit_event(cdb, company_id, "purchase_invoice", purchase_inv.id, "create", f"Purchase bill {purchase_inv.invoice_id} saved for {purchase_inv.supplier_name}")

        is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.form.get("is_ajax") == "1" or request.is_json
        if is_ajax:
            return jsonify({
                "success": True,
                "invoice_id": purchase_inv.invoice_id,
                "message": f"Purchase bill {purchase_inv.invoice_id} recorded successfully!"
            })

        flash(f"Purchase bill {purchase_inv.invoice_id} recorded successfully!", "success")
        return redirect(url_for("purchase_invoice_view", invoice_id=purchase_inv.invoice_id))

    suppliers = cdb.query(Supplier).filter_by(company_id=company_id, status="Active").order_by(Supplier.name).all()
    stock_items = cdb.query(StockItem).filter_by(company_id=company_id).order_by(StockItem.name).all()
    prefix = "PB-"
    q = cdb.query(PurchaseInvoice.invoice_id).filter(PurchaseInvoice.invoice_id.like(f"{prefix}%")).all()
    max_num = 0
    for (val,) in q:
        if not val:
            continue
        tail = val[len(prefix):]
        try:
            max_num = max(max_num, int(tail))
        except ValueError:
            continue
    default_bill_id = f"{prefix}{max_num + 1:03d}"

    po_id = request.args.get("po_id", type=int)
    prefill_supplier_id = None
    prefill_supplier_name = ""
    prefill_invoice_number = ""
    prefill_po_no = ""
    po_order = None
    if po_id:
        po_order = cdb.query(PurchaseOrder).filter_by(id=po_id, company_id=company_id).first()
        if po_order:
            prefill_supplier_id = po_order.supplier_id
            prefill_supplier_name = po_order.supplier_name
            prefill_po_no = po_order.po_number
            prefill_invoice_number = po_order.reference_no or ""

    return render_template(
        "purchase_new.html",
        is_edit=False,
        invoice=None,
        po_order=po_order,
        suppliers=suppliers,
        stock_items=stock_items,
        default_bill_id=default_bill_id,
        today_date=today_ist().strftime("%Y-%m-%d"),
        company=company,
        prefill_supplier_id=prefill_supplier_id,
        prefill_supplier_name=prefill_supplier_name,
        prefill_invoice_number=prefill_invoice_number,
        prefill_po_no=prefill_po_no,
    )


@app.route("/purchase/edit/<invoice_id>", methods=["GET", "POST"])
@login_required
@require_permission("purchase", "view", method_actions={'POST': 'edit'})
def purchase_invoice_edit(invoice_id):
    """Edit an existing purchase bill"""
    cdb = get_cdb()
    company_id = get_current_company()
    company = Company.query.filter_by(company_id=company_id).first()

    invoice = cdb.query(PurchaseInvoice).filter_by(invoice_id=invoice_id, company_id=company_id).first()
    if not invoice:
        abort(404)

    if invoice.note_adjustment:
        flash("Cancel the posted credit/debit notes before editing or deleting this invoice.", "warning")
        return redirect(url_for("purchase_invoice_view", invoice_id=invoice_id))

    if request.method == "POST":
        supplier_id_raw = request.form.get("supplier_id", "").strip()
        supplier_id = int(supplier_id_raw) if supplier_id_raw and supplier_id_raw.isdigit() else None
        supplier_name = request.form.get("supplier_name", "").strip()
        supplier_gstin = request.form.get("supplier_gstin", "").strip()
        supplier_state = request.form.get("supplier_state", "").strip()
        supplier_address = request.form.get("supplier_address", "").strip()
        supplier_phone = request.form.get("supplier_phone", "").strip()
        supplier_email = request.form.get("supplier_email", "").strip()
        invoice_number = request.form.get("invoice_number", "").strip()
        reference_po_no = request.form.get("reference_po_no", "").strip()
        date_str = request.form.get("date")
        due_date_str = request.form.get("due_date")
        payment_terms = request.form.get("payment_terms", "Net 30 Days").strip()
        status = request.form.get("status", "Pending").strip()
        terms = request.form.get("terms", "").strip()
        notes = request.form.get("notes", "").strip()

        inv_date = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else invoice.date
        due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date() if due_date_str else (invoice.due_date or inv_date)
        # Auto-create or resolve supplier if new name typed
        if not supplier_id and supplier_name:
            sup = cdb.query(Supplier).filter_by(company_id=company_id, name=supplier_name).first()
            if not sup:
                company_obj = Company.query.filter_by(company_id=company_id).first()
                supplier_prefix = _company_name_prefix(company_obj.company_name if company_obj else "", from_end=False)
                new_supplier_id = _next_numbered_id(cdb, Supplier.supplier_id, supplier_prefix, extra_filters=[Supplier.company_id == company_id])
                sup = Supplier(
                    supplier_id=new_supplier_id,
                    company_id=company_id,
                    name=supplier_name,
                    gst_number=supplier_gstin or None,
                    state=supplier_state or None,
                    address_line1=supplier_address or None,
                    phone=supplier_phone or None,
                    email=supplier_email or None,
                    status="Active",
                    created_at=today_ist().date() if hasattr(today_ist(), "date") else today_ist()
                )
                cdb.add(sup)
                cdb.flush()
            supplier_id = sup.id

        company_state = (company.state or "").strip().lower() if company else ""
        s_state = (supplier_state or "").strip().lower()
        is_interstate = bool(company_state and s_state and company_state != s_state)

        # Multi-currency & regional tax parameters
        base_currency = (company.currency if company and company.currency else "INR").strip().upper()
        doc_currency = (request.form.get("currency") or getattr(invoice, 'currency', None) or base_currency).strip().upper()
        try:
            exchange_rate = float(request.form.get("exchange_rate") or getattr(invoice, 'exchange_rate', 1.0) or 1.0)
            if exchange_rate <= 0:
                exchange_rate = 1.0
        except (ValueError, TypeError):
            exchange_rate = 1.0

        if doc_currency == base_currency:
            exchange_rate = 1.0

        tax_regime = tax_profile(company, invoice)['regime']
        tax_type = (request.form.get("tax_type") or getattr(invoice, 'tax_type', None) or ("Import" if doc_currency != base_currency else ("IGST" if is_interstate else "CGST_SGST"))).strip()

        invoice.currency = doc_currency
        invoice.exchange_rate = exchange_rate
        invoice.tax_regime = tax_regime
        invoice.tax_type = tax_type
        invoice.supplier_id = supplier_id
        invoice.supplier_name = supplier_name
        invoice.supplier_address = supplier_address
        invoice.supplier_gstin = supplier_gstin
        invoice.supplier_state = supplier_state
        invoice.supplier_phone = supplier_phone
        invoice.supplier_email = supplier_email
        invoice.invoice_number = invoice_number
        invoice.reference_po_no = reference_po_no
        invoice.date = inv_date
        invoice.due_date = due_date
        invoice.payment_terms = payment_terms
        invoice.status = status
        invoice.terms = terms
        invoice.notes = notes
        invoice.updated_by = session.get("user", {}).get("username") or session.get("user_id")

        cdb.query(PurchaseInvoiceItem).filter_by(purchase_invoice_id=invoice.id).delete()

        # Parse Line Items
        item_codes = request.form.getlist("item_code[]")
        item_names = request.form.getlist("item_name[]")
        hsns = request.form.getlist("hsn[]")
        quantities = request.form.getlist("quantity[]")
        units = request.form.getlist("unit[]")
        rates = request.form.getlist("rate[]")
        discount_percents = request.form.getlist("discount_percent[]")
        gst_percents = request.form.getlist("gst_percent[]")
        stock_item_ids = request.form.getlist("stock_item_id[]")

        subtotal = 0.0
        vat_total = 0.0
        cgst_total = 0.0
        sgst_total = 0.0
        igst_total = 0.0

        company_state = (company.state or "").strip().lower() if company else ""
        s_state = (supplier_state or "").strip().lower()
        is_interstate = bool(company_state and s_state and company_state != s_state)

        for i in range(len(item_names)):
            name = item_names[i].strip() if i < len(item_names) else ""
            if not name:
                continue
            code = item_codes[i].strip() if i < len(item_codes) else ""
            hsn = hsns[i].strip() if i < len(hsns) else ""
            try:
                qty = float(quantities[i]) if i < len(quantities) and quantities[i] else 1.0
            except ValueError:
                qty = 1.0
            unit = units[i].strip() if i < len(units) and units[i] else "pcs"
            try:
                rate = float(rates[i]) if i < len(rates) and rates[i] else 0.0
            except ValueError:
                rate = 0.0
            try:
                disc_pct = float(discount_percents[i]) if i < len(discount_percents) and discount_percents[i] else 0.0
            except ValueError:
                disc_pct = 0.0
            try:
                gst_pct = float(gst_percents[i]) if i < len(gst_percents) and gst_percents[i] else 0.0
            except ValueError:
                gst_pct = 0.0

            st_id = None
            if i < len(stock_item_ids) and stock_item_ids[i] and stock_item_ids[i].isdigit():
                st_id = int(stock_item_ids[i])

            # Resolve stock item: prioritize code
            stock = None
            if code:
                stock = cdb.query(StockItem).filter_by(code=code, company_id=company_id).first()
            if not stock and st_id:
                stock = cdb.query(StockItem).filter_by(id=st_id, company_id=company_id).first()
            if not stock and name:
                stock = cdb.query(StockItem).filter_by(name=name, company_id=company_id).first()

            if stock:
                st_id = stock.id
                if not code:
                    code = stock.code

            base_val = qty * rate
            disc_amt = base_val * (disc_pct / 100.0)
            taxable = base_val - disc_amt
            gst_pct = billing_rate(company, gst_percents[i] if i < len(gst_percents) else None, invoice)
            tax_amt, cgst_amt, sgst_amt, igst_amt = split_tax(taxable, gst_pct, tax_regime, is_interstate)
            vat_total += tax_amt if tax_regime not in ('GST', 'INDIA_GST') else 0.0

            row_total = taxable + tax_amt

            subtotal += taxable
            cgst_total += cgst_amt
            sgst_total += sgst_amt
            igst_total += igst_amt

            base_rate = round(rate * exchange_rate, 4)
            base_taxable = round(taxable * exchange_rate, 2)
            base_row_total = round(row_total * exchange_rate, 2)

            pi_item = PurchaseInvoiceItem(
                purchase_invoice_id=invoice.id,
                stock_item_id=st_id,
                item_code=code,
                code=code,
                item_name=name,
                description=name,
                hsn=hsn,
                quantity=qty,
                unit=unit,
                rate=rate,
                purchase_rate=rate,
                base_rate=base_rate,
                discount_percent=disc_pct,
                taxable_amount=taxable,
                taxable_value=taxable,
                base_taxable_amount=base_taxable,
                gst_percent=gst_pct,
                cgst_amount=cgst_amt,
                sgst_amount=sgst_amt,
                igst_amount=igst_amt,
                total_amount=row_total,
                base_total_amount=base_row_total,
                party_name=supplier_name
            )
            cdb.add(pi_item)

        tax_total = cgst_total + sgst_total + igst_total
        grand_total = subtotal + tax_total

        invoice.subtotal = round(subtotal, 2)
        invoice.cgst_total = round(cgst_total, 2)
        invoice.sgst_total = round(sgst_total, 2)
        invoice.igst_total = round(igst_total, 2)
        invoice.tax_amount = round(tax_total, 2)
        invoice.grand_total = round(grand_total, 2)
        invoice.balance = round(grand_total - (invoice.paid_amount or 0.0), 2)

        # Multi-currency Base Currency equivalents
        invoice.base_subtotal = round(invoice.subtotal * exchange_rate, 2)
        invoice.base_tax_amount = round(invoice.tax_amount * exchange_rate, 2)
        invoice.base_grand_total = round(invoice.grand_total * exchange_rate, 2)
        invoice.base_paid_amount = round((invoice.paid_amount or 0.0) * exchange_rate, 2)
        invoice.base_balance = round(invoice.balance * exchange_rate, 2)

        _replace_purchase_invoice_journal(cdb, company_id, invoice, "Purchase invoice edited")
        cdb.commit()
        flash(f"Purchase bill {invoice_id} updated and accounting re-posted.", "success")
        return redirect(url_for("purchase_invoice_view", invoice_id=invoice_id))

    suppliers = cdb.query(Supplier).filter_by(company_id=company_id, status="Active").order_by(Supplier.name).all()
    stock_items = cdb.query(StockItem).filter_by(company_id=company_id).order_by(StockItem.name).all()
    return render_template(
        "purchase_edit.html",
        is_edit=True,
        invoice=invoice,
        suppliers=suppliers,
        stock_items=stock_items,
        default_bill_id=invoice.invoice_id,
        today_date=today_ist().strftime("%Y-%m-%d"),
        company=company,
    )


@app.route("/purchase/view/<invoice_id>")
@login_required
@require_permission("purchase", "view")
def purchase_invoice_view(invoice_id):
    cdb = get_cdb()
    company_id = get_current_company()
    invoice = cdb.query(PurchaseInvoice).filter_by(invoice_id=invoice_id, company_id=company_id).first()
    if not invoice:
        try:
            invoice = cdb.query(PurchaseInvoice).filter_by(id=int(invoice_id), company_id=company_id).first()
        except Exception:
            pass
    if not invoice:
        abort(404)

    company = Company.query.filter_by(company_id=company_id).first()
    bank_accounts = cdb.query(BankAccount).filter_by(company_id=company_id, status='Active').all()
    return render_template(
        "purchase_view.html",
        invoice=invoice,
        company=company,
        bank_accounts=bank_accounts,
        today_date=today_ist().strftime("%Y-%m-%d"),
    )


@app.route("/purchase/pay/<int:pk>", methods=["POST"])
@login_required
@require_permission("purchase", "edit")
def purchase_make_payment(pk):
    cdb = get_cdb()
    company_id = get_current_company()
    invoice = _first_or_404(cdb.query(PurchaseInvoice).filter_by(id=pk, company_id=company_id).first())

    amount     = float(request.form.get("amount", 0))
    pay_mode   = request.form.get("pay_mode", "Cash")
    narration  = request.form.get("narration", "")
    pay_date_s = request.form.get("pay_date")
    pay_date   = date.fromisoformat(pay_date_s) if pay_date_s else today_ist()
    bank_account_id = request.form.get("bank_account_id", type=int)

    if amount <= 0:
        flash("Invalid payment amount.")
        return redirect(url_for("purchase_invoice_view", invoice_id=invoice.invoice_id))

    if amount > (invoice.balance or 0):
        amount = invoice.balance or 0

    # Non-cash modes need a real bank account to post the debit against —
    # same requirement /payments/save enforces, so this route stays
    # consistent with it instead of silently going nowhere.
    bank_account = None
    if pay_mode.lower() != "cash":
        if not bank_account_id:
            flash("Please select a bank account for non-cash payments.", "error")
            return redirect(url_for("purchase_invoice_view", invoice_id=invoice.invoice_id))
        bank_account = cdb.query(BankAccount).filter_by(
            id=bank_account_id, company_id=company_id, status='Active'
        ).first()
        if not bank_account:
            flash("Selected bank account not found or inactive.", "error")
            return redirect(url_for("purchase_invoice_view", invoice_id=invoice.invoice_id))

    invoice.paid_amount = (invoice.paid_amount or 0) + amount
    invoice.balance     = max(0, (invoice.balance or 0) - amount)

    if invoice.balance <= 0:
        invoice.status = "Paid"
    elif invoice.paid_amount > 0:
        invoice.status = "Partial"

    if invoice.supplier:
        invoice.supplier.payable = max(0, (invoice.supplier.payable or 0) - amount)

    # Kept for backward-compat / audit trail — NOT what creditors, the
    # creditor statement, or the Payments page read from. Those all read
    # CashTransaction/BankTransaction, so the write below is the one that
    # actually makes this payment visible anywhere else in the app.
    pmt = PurchasePayment(
        company_id  = company_id,
        invoice_id  = invoice.id,
        supplier_id = invoice.supplier_id,
        date        = pay_date,
        amount      = amount,
        pay_mode    = pay_mode,
        narration   = narration,
        created_by  = session.get("user", {}).get("user_id")
    )
    cdb.add(pmt)

    supplier_name = invoice.supplier.name if invoice.supplier else ""
    txn_reference = invoice.invoice_number or invoice.invoice_id
    desc = f"Payment made for purchase invoice {txn_reference}"
    if narration:
        desc += f" - {narration}"

    if pay_mode.lower() == "cash":
        cash_txn = CashTransaction(
            company_id=company_id,
            type="expense",
            date=pay_date,
            category="Payment",
            description=desc,
            amount=amount,
            reference=txn_reference,
            notes=f"Payment of {company_currency_symbol()} {amount:,.2f} to supplier via Cash",
            party_name=supplier_name,
            created_by=get_current_user().get('email'),
            applied_ref_type="purchase_invoice",
            applied_ref_id=invoice.id,
        )
        cdb.add(cash_txn)
    else:
        bank_txn = BankTransaction(
            bank_account_id=bank_account.id,
            company_id=company_id,
            type="debit",
            date=pay_date,
            description=desc,
            amount=amount,
            reference=txn_reference,
            transaction_mode=pay_mode.title(),
            notes=narration,
            party_name=supplier_name,
            created_by=get_current_user().get('email'),
            applied_ref_type="purchase_invoice",
            applied_ref_id=invoice.id,
        )
        cdb.add(bank_txn)
        bank_account.balance -= amount

    settlement_txn = cash_txn if pay_mode.lower() == "cash" else bank_txn
    cdb.flush()
    _auto_post_settlement(cdb, company_id, settlement_txn, "payment")
    cdb.commit()
    flash(f"Payment of {company_currency_symbol()} {amount:,.2f} via {pay_mode} recorded and posted to accounts. {narration}")
    return redirect(url_for("purchase_invoice_view", invoice_id=invoice.invoice_id))

# ─────────────────────────────────────────────────────────────────────────────
# ── Invoices ──────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────


TRACKING_STATUS_STAGES = ["Booked", "In Transit", "Out for Delivery", "Delivered"]


def _generate_temp_password(length=10):
    # Avoid visually ambiguous chars (0/O, 1/l/I) since this gets read off-screen and typed by hand
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


@app.route("/company/reset-user-password/<email>", methods=["POST"])
@login_required
@owner_required
def reset_user_password(email):
    """Reset one person's password everywhere they have access — mirrors
    delete_company_user's pattern of walking every one of the owner's
    companies, since the same email can have a separate CompanyUser row
    (and separate password_hash) in each company's own database.
    """
    owner_email = get_current_user().get("email", "").strip().lower()
    owner_companies = get_owner_companies(owner_email)
    email = email.strip().lower()

    temp_password = _generate_temp_password()
    new_hash = hash_password(temp_password)

    reset_in = []
    full_name = None
    for c in owner_companies:
        _cdb = get_customer_session(c.company_id)
        user = _cdb.query(CompanyUser).filter_by(company_id=c.company_id, email=email).first()
        if user and user.role != "owner" and user.is_active:
            user.password_hash = new_hash
            _cdb.commit()
            reset_in.append(c.company_name)
            full_name = full_name or user.full_name

    if reset_in:
        flash(
            f"Password for {full_name or email} reset across: {', '.join(reset_in)}. "
            f"Temporary password: {temp_password} — share this securely, it will not be shown again.",
            "success"
        )
    else:
        flash("Could not reset password — no active non-owner account found for this email.", "error")
    return redirect(url_for("company_settings"))



# ─────────────────────────────────────────────────────────────────────────────
# ── Resale / Return Charges Routes ──────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# ── Customer Invoice (Shipment) ───────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

AWB_PREFIX   = "AHL"
AWB_START    = 81000          # first number: AHL81000
AWB_COUNTER_KEY = "awb_last" # we store the last-used counter in a tiny helper


"""def _next_awb_number(company_id: int) -> str:
    
    # Count how many customer invoices already have an AHL docket number
    existing_count = (
        cdb.query(Invoice)
        .filter(
            Invoice.company_id == company_id,
            Invoice.terms.like("AWB:AHL%"),   # we embed the AWB in terms for storage
        )
        .count()
    )
    # Alternatively, just count all customer-type invoices for this company
    # (simpler and still gapless)
    cust_count = (
        cdb.query(Invoice)
        .filter(
            Invoice.company_id == company_id,
            Invoice.invoice_id.like("CUST-%"),
        )
        .count()
    )
    seq = AWB_START + cust_count
    return f"{AWB_PREFIX}{seq}"""
# Replace the _next_awb_number function in app.py (around line 650)


_FIX_DUPES_TEMPLATE = """
<!doctype html><html><head><title>Duplicate AWB cleanup</title>
<style>
body{font-family:system-ui,sans-serif;padding:24px;color:#111827;background:#F9FAFB;}
table{border-collapse:collapse;width:100%;max-width:900px;background:#fff;}
th,td{border:1px solid #E5E7EB;padding:8px 12px;text-align:left;font-size:14px;}
th{background:#F3F4F6;}
.old{color:#B91C1C;text-decoration:line-through;}
.new{color:#15803D;font-weight:700;}
.warn{background:#FEF3C7;border:1px solid #F59E0B;padding:12px;border-radius:6px;margin-bottom:16px;max-width:900px;}
.btn{display:inline-block;margin-top:16px;padding:10px 18px;background:#DC2626;color:#fff;border:none;border-radius:6px;font-weight:700;cursor:pointer;}
</style></head><body>
<h2>Duplicate AWB cleanup — dry run</h2>
<div class="warn">
This only <b>previews</b> changes — nothing is saved yet. It keeps the
<b>earliest-created</b> invoice on each clashing AWB and reassigns every
newer invoice in that group to the next free AWB.<br><br>
<b>Check before confirming:</b> if a physical AWB label/document already
went out with the old number for any of these, renumbering here will make
the system disagree with the paper. Only click "Apply" once you've verified
these newer invoices haven't actually shipped under the old number.
</div>
{% if changes %}
<table>
<tr><th>Invoice</th><th>Created</th><th>Current AWB</th><th>New AWB</th></tr>
{% for c in changes %}
<tr>
  <td>{{ c.invoice_id }}</td>
  <td>{{ c.created_at }}</td>
  <td class="old">{{ c.old_awb }}</td>
  <td class="new">{{ c.new_awb }}</td>
</tr>
{% endfor %}
</table>
<form method="POST">
  <input type="hidden" name="confirm" value="yes">
  <button class="btn" type="submit" onclick="return confirm('Renumber {{ changes|length }} invoice(s)? This cannot be undone automatically.');">
    Apply — renumber {{ changes|length }} invoice(s)
  </button>
</form>
{% else %}
<p>No duplicate AWBs found for this company. Nothing to fix.</p>
{% endif %}
</body></html>
"""

# ─────────────────────────────────────────────────────────────────────────────
# ── Customer Invoice (Aggregate Bookings) ────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

def _get_next_customer_invoice_number(cdb, company_id, invoice_type="credit"):
    """
    Generate next customer invoice number based on type:
    - Credit: CR-001, CR-002, etc.
    - Cash: CS-001, CS-002, etc.
    """
    prefix = "CR-" if invoice_type == "credit" else "CS-"
    existing = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.invoice_number.like(f"{prefix}%")
    ).all()
    
    max_num = 0
    for inv in existing:
        if inv.invoice_number and inv.invoice_number.startswith(prefix):
            try:
                num = int(inv.invoice_number.split("-")[-1])
                if num > max_num:
                    max_num = num
            except (ValueError, IndexError):
                continue
    return f"{prefix}{max_num + 1:03d}"


def _sales_invoice_query(cdb, company_id):
    # Job-card links also identify repair bills created before categories existed.
    from customer_models import WorkshopJobCard
    linked_repair = cdb.query(WorkshopJobCard.id).filter(
        WorkshopJobCard.company_id == company_id,
        WorkshopJobCard.invoice_id == CustomerInvoice.id,
    ).exists()
    return cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        or_(CustomerInvoice.invoice_category.is_(None),
            CustomerInvoice.invoice_category != "workshop_repair"),
        ~linked_repair,
    )


@app.route("/customer-invoices")
@login_required
@require_permission("invoices", "view")
def customer_invoice_list():
    """List all sales invoices"""
    cdb = get_cdb()
    company_id = get_current_company()
 
    status_filter = request.args.get("status", "All")
    search_query = request.args.get("q", "").strip()
    query = _sales_invoice_query(cdb, company_id)
 
    if status_filter != "All":
        query = query.filter_by(status=status_filter)
 
    if search_query:
        query = query.filter(CustomerInvoice.client_name.ilike(f"%{search_query}%"))
 
    invoices = query.order_by(CustomerInvoice.created_at.desc()).all()
 
    # Calculate totals
    total_amount = sum(inv.grand_total for inv in invoices)
    total_paid = sum(inv.paid_amount for inv in invoices)
    total_balance = sum(inv.balance for inv in invoices)
 
    # Resolve created_by / updated_by (stored as email) -> {name, email}
    raw_ids = set()
    for inv in invoices:
        raw_ids.add(inv.created_by)
        raw_ids.add(inv.updated_by)
    user_names = resolve_user_names(cdb, raw_ids)
 
    return render_template("customer_invoice_list.html",
                         invoices=invoices,
                         total_amount=total_amount,
                         total_paid=total_paid,
                         total_balance=total_balance,
                         current_status=status_filter,
                         current_search=search_query,
                         user_names=user_names,
                         active='customer_invoices')


@app.route("/customer-invoices/new")
@login_required
@require_permission("customer_invoices", "create")
def customer_invoice_new():
    """Create a new standard sales tax invoice"""
    cdb = get_cdb()
    company_id = get_current_company()
    company = Company.query.filter_by(company_id=company_id).first()
    
    count = cdb.query(CustomerInvoice).filter_by(company_id=company_id).count()
    default_invoice_no = f"INV-{count + 1:04d}"
    while cdb.query(CustomerInvoice).filter_by(company_id=company_id, invoice_number=default_invoice_no).first():
        count += 1
        default_invoice_no = f"INV-{count + 1:04d}"
        
    clients = cdb.query(Client).filter_by(company_id=company_id).filter(Client.status != "Deleted").order_by(Client.name.asc()).all()
    stock_items = cdb.query(StockItem).filter(StockItem.company_id == company_id, StockItem.quantity > 0).order_by(StockItem.name.asc()).all()
    
    prefill_client_id = request.args.get("client_id", "")
    prefill_client_name = request.args.get("client_name", "")

    return render_template(
        "customer_invoice_form.html",
        is_edit=False,
        invoice=None,
        default_invoice_no=default_invoice_no,
        today_date=date.today().strftime("%Y-%m-%d"),
        company=company,
        clients=clients,
        stock_items=stock_items,
        prefill_client_id=prefill_client_id,
        prefill_client_name=prefill_client_name,
        active="customer_invoices"
    )


@app.route("/customer-invoices/create", methods=["POST"])
@login_required
@require_permission("customer_invoices", "create")
def customer_invoice_create():
    """Save standard sales tax invoice with product rows and GST breakdown"""
    cdb = get_cdb()
    company_id = get_current_company()
    company = Company.query.filter_by(company_id=company_id).first()

    invoice_number = request.form.get("invoice_number", "").strip()
    if not invoice_number:
        count = cdb.query(CustomerInvoice).filter_by(company_id=company_id).count()
        invoice_number = f"INV-{count + 1:04d}"

    client_id_val = request.form.get("client_id")
    client_id = int(client_id_val) if client_id_val and client_id_val.isdigit() else None
    client_name = request.form.get("client_name", "").strip()
    billing_address = request.form.get("billing_address", "").strip()
    shipping_address = request.form.get("shipping_address", "").strip()
    client_gstin = request.form.get("client_gstin", "").strip()
    client_state = request.form.get("client_state", "").strip()

    invoice_date_str = request.form.get("invoice_date")
    due_date_str = request.form.get("due_date")
    try:
        inv_date = datetime.strptime(invoice_date_str, "%Y-%m-%d").date() if invoice_date_str else date.today()
    except ValueError:
        inv_date = date.today()

    try:
        due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date() if due_date_str else None
    except ValueError:
        due_date = None

    invoice_type = request.form.get("invoice_type", "credit")
    payment_terms = request.form.get("payment_terms", "").strip()
    terms = request.form.get("terms", "").strip()
    notes = request.form.get("notes", "").strip()
    auto_deduct_stock = request.form.get("auto_deduct_stock") == "1"

    # Multi-currency & regional tax parameters
    base_currency = (company.currency if company and company.currency else "INR").strip().upper()
    doc_currency = (request.form.get("currency") or base_currency).strip().upper()
    try:
        exchange_rate = float(request.form.get("exchange_rate") or 1.0)
        if exchange_rate <= 0:
            exchange_rate = 1.0
    except (ValueError, TypeError):
        exchange_rate = 1.0

    if doc_currency == base_currency:
        exchange_rate = 1.0

    tax_regime = tax_profile(company)['regime']

    cust_inv = CustomerInvoice(
        invoice_number=invoice_number,
        company_id=company_id,
        client_id=client_id,
        client_name=client_name,
        billing_address=billing_address,
        shipping_address=shipping_address,
        client_gstin=client_gstin,
        client_state=client_state,
        invoice_date=inv_date,
        due_date=due_date,
        currency=doc_currency,
        exchange_rate=exchange_rate,
        tax_regime=tax_regime,
        invoice_type=invoice_type,
        invoice_category="product_sale",
        status="Pending",
        payment_terms=payment_terms,
        terms=terms,
        notes=notes,
        created_by=session.get("user", {}).get("email", "System"),
    )
    cdb.add(cust_inv)
    cdb.flush()

    subtotal = 0.0
    vat_total = 0.0
    cgst_total = 0.0
    sgst_total = 0.0
    igst_total = 0.0

    item_names = request.form.getlist("item_name[]")
    item_codes = request.form.getlist("item_code[]")
    stock_ids = request.form.getlist("stock_item_id[]")
    hsns = request.form.getlist("hsn[]")
    quantities = request.form.getlist("quantity[]")
    units = request.form.getlist("unit[]")
    rates = request.form.getlist("rate[]")
    discounts = request.form.getlist("discount_percent[]")
    gst_percents = request.form.getlist("gst_percent[]")

    is_interstate = False
    if company and company.state and client_state:
        if company.state.strip().lower() != client_state.strip().lower():
            is_interstate = True

    for i in range(len(item_names)):
        iname = item_names[i].strip() if i < len(item_names) else ""
        if not iname:
            continue

        icode = item_codes[i].strip() if i < len(item_codes) else ""
        sid_val = stock_ids[i] if i < len(stock_ids) else ""
        stock_id = int(sid_val) if sid_val and sid_val.isdigit() else None
        hsn = hsns[i].strip() if i < len(hsns) else ""

        try: qty = float(quantities[i]) if i < len(quantities) and quantities[i] else 1.0
        except ValueError: qty = 1.0
        unit = units[i].strip() if i < len(units) else "pcs"
        try: rate = float(rates[i]) if i < len(rates) and rates[i] else 0.0
        except ValueError: rate = 0.0
        try: disc = float(discounts[i]) if i < len(discounts) and discounts[i] else 0.0
        except ValueError: disc = 0.0
        try: gst = float(gst_percents[i]) if i < len(gst_percents) and gst_percents[i] else 0.0
        except ValueError: gst = 0.0

        line_gross = qty * rate
        line_disc = line_gross * (disc / 100.0)
        taxable = max(0.0, line_gross - line_disc)

        gst = billing_rate(company, gst_percents[i] if i < len(gst_percents) else None)
        line_tax, cgst, sgst, igst = split_tax(taxable, gst, tax_regime, is_interstate)
        vat_total += line_tax if tax_regime not in ('GST', 'INDIA_GST') else 0.0
        total = round(taxable + line_tax, 2)

        subtotal += taxable
        cgst_total += cgst
        sgst_total += sgst
        igst_total += igst

        base_rate = round(rate * exchange_rate, 4)
        base_taxable = round(taxable * exchange_rate, 2)
        base_total = round(total * exchange_rate, 2)

        inv_item = CustomerInvoiceItem(
            customer_invoice_id=cust_inv.id,
            stock_item_id=stock_id,
            item_code=icode,
            item_name=iname,
            item_description=iname,
            hsn=hsn,
            quantity=qty,
            unit=unit,
            rate=rate,
            base_rate=base_rate,
            discount_percent=disc,
            taxable_amount=taxable,
            base_taxable_amount=base_taxable,
            gst_percent=gst,
            cgst_amount=cgst,
            sgst_amount=sgst,
            igst_amount=igst,
            total_amount=total,
            base_total_amount=base_total
        )
        cdb.add(inv_item)

        if auto_deduct_stock:
            stk = None
            if stock_id:
                stk = cdb.query(StockItem).filter_by(id=stock_id, company_id=company_id).first()
            if not stk and icode:
                stk = cdb.query(StockItem).filter_by(code=icode, company_id=company_id).first()
            if not stk and iname:
                stk = cdb.query(StockItem).filter_by(name=iname, company_id=company_id).first()

            if stk:
                stk.quantity = max(0.0, (stk.quantity or 0.0) - qty)
                stk.last_updated = inv_date
                cdb.add(StockPurchaseHistory(
                    stock_item_id=stk.id,
                    quantity=-qty,
                    purchase_rate=rate,
                    currency=doc_currency,
                    exchange_rate=exchange_rate,
                    base_purchase_rate=base_rate,
                    gst_percent=gst,
                    purchase_date=inv_date,
                    movement_type="OUT",
                    reference=cust_inv.invoice_number
                ))

    cust_inv.subtotal = round(subtotal, 2)
    cust_inv.cgst_total = round(cgst_total, 2)
    cust_inv.sgst_total = round(sgst_total, 2)
    cust_inv.igst_total = round(igst_total, 2)
    cust_inv.tax_amount = round(cgst_total + sgst_total + igst_total + vat_total, 2)
    cust_inv.grand_total = round(subtotal + cust_inv.tax_amount, 2)
    cust_inv.balance = cust_inv.grand_total

    # Base Currency equivalents
    cust_inv.base_subtotal = round(cust_inv.subtotal * exchange_rate, 2)
    cust_inv.base_tax_amount = round(cust_inv.tax_amount * exchange_rate, 2)
    cust_inv.base_grand_total = round(cust_inv.grand_total * exchange_rate, 2)

    _auto_post_customer_invoice(cdb, company_id, cust_inv)
    cdb.commit()
    flash(f"✅ Tax Invoice {cust_inv.invoice_number} created successfully and posted to accounts!", "success")
    return redirect(url_for("customer_invoice_view", cust_inv_id=cust_inv.id))


@app.route("/customer-invoices/edit/<int:cust_inv_id>", methods=["GET", "POST"])
@login_required
@require_permission("customer_invoices", "edit")
def customer_invoice_edit(cust_inv_id):
    """Edit an existing standard sales tax invoice"""
    cdb = get_cdb()
    company_id = get_current_company()
    company = Company.query.filter_by(company_id=company_id).first()
    cust_inv = _first_or_404(_sales_invoice_query(cdb, company_id).filter_by(id=cust_inv_id).first())

    if cust_inv.note_adjustment:
        flash("Cancel the posted credit/debit notes before editing or deleting this invoice.", "warning")
        return redirect(url_for("customer_invoice_view", cust_inv_id=cust_inv_id))

    if request.method == "GET":
        clients = cdb.query(Client).filter_by(company_id=company_id).filter(Client.status != "Deleted").order_by(Client.name.asc()).all()
        stock_items = cdb.query(StockItem).filter_by(company_id=company_id).order_by(StockItem.name.asc()).all()
        return render_template(
            "customer_invoice_form.html",
            is_edit=True,
            invoice=cust_inv,
            default_invoice_no=cust_inv.invoice_number,
            today_date=cust_inv.invoice_date.strftime("%Y-%m-%d") if cust_inv.invoice_date else date.today().strftime("%Y-%m-%d"),
            company=company,
            clients=clients,
            stock_items=stock_items,
            active="customer_invoices"
        )

    cust_inv.invoice_number = request.form.get("invoice_number", cust_inv.invoice_number).strip()
    client_id_val = request.form.get("client_id")
    cust_inv.client_id = int(client_id_val) if client_id_val and client_id_val.isdigit() else None
    cust_inv.client_name = request.form.get("client_name", cust_inv.client_name).strip()
    cust_inv.billing_address = request.form.get("billing_address", "").strip()
    cust_inv.shipping_address = request.form.get("shipping_address", "").strip()
    cust_inv.client_gstin = request.form.get("client_gstin", "").strip()
    cust_inv.client_state = request.form.get("client_state", "").strip()

    invoice_date_str = request.form.get("invoice_date")
    due_date_str = request.form.get("due_date")
    try:
        cust_inv.invoice_date = datetime.strptime(invoice_date_str, "%Y-%m-%d").date() if invoice_date_str else date.today()
    except ValueError:
        pass

    try:
        cust_inv.due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date() if due_date_str else None
    except ValueError:
        cust_inv.due_date = None

    # Multi-currency & regional tax parameters
    base_currency = (company.currency if company and company.currency else "INR").strip().upper()
    doc_currency = (request.form.get("currency") or getattr(cust_inv, 'currency', None) or base_currency).strip().upper()
    try:
        exchange_rate = float(request.form.get("exchange_rate") or getattr(cust_inv, 'exchange_rate', 1.0) or 1.0)
        if exchange_rate <= 0:
            exchange_rate = 1.0
    except (ValueError, TypeError):
        exchange_rate = 1.0

    if doc_currency == base_currency:
        exchange_rate = 1.0

    tax_regime = tax_profile(company, cust_inv)['regime']

    cust_inv.currency = doc_currency
    cust_inv.exchange_rate = exchange_rate
    cust_inv.tax_regime = tax_regime
    cust_inv.invoice_type = request.form.get("invoice_type", cust_inv.invoice_type)
    cust_inv.payment_terms = request.form.get("payment_terms", "").strip()
    cust_inv.terms = request.form.get("terms", "").strip()
    cust_inv.notes = request.form.get("notes", "").strip()
    cust_inv.updated_by = session.get("user", {}).get("email", "System")

    cdb.query(CustomerInvoiceItem).filter_by(customer_invoice_id=cust_inv.id).delete()

    subtotal = 0.0
    vat_total = 0.0
    cgst_total = 0.0
    sgst_total = 0.0
    igst_total = 0.0

    item_names = request.form.getlist("item_name[]")
    item_codes = request.form.getlist("item_code[]")
    stock_ids = request.form.getlist("stock_item_id[]")
    hsns = request.form.getlist("hsn[]")
    quantities = request.form.getlist("quantity[]")
    units = request.form.getlist("unit[]")
    rates = request.form.getlist("rate[]")
    discounts = request.form.getlist("discount_percent[]")
    gst_percents = request.form.getlist("gst_percent[]")

    is_interstate = False
    if company and company.state and cust_inv.client_state:
        if company.state.strip().lower() != cust_inv.client_state.strip().lower():
            is_interstate = True

    for i in range(len(item_names)):
        iname = item_names[i].strip() if i < len(item_names) else ""
        if not iname:
            continue

        icode = item_codes[i].strip() if i < len(item_codes) else ""
        sid_val = stock_ids[i] if i < len(stock_ids) else ""
        stock_id = int(sid_val) if sid_val and sid_val.isdigit() else None
        hsn = hsns[i].strip() if i < len(hsns) else ""

        try: qty = float(quantities[i]) if i < len(quantities) and quantities[i] else 1.0
        except ValueError: qty = 1.0
        unit = units[i].strip() if i < len(units) else "pcs"
        try: rate = float(rates[i]) if i < len(rates) and rates[i] else 0.0
        except ValueError: rate = 0.0
        try: disc = float(discounts[i]) if i < len(discounts) and discounts[i] else 0.0
        except ValueError: disc = 0.0
        try: gst = float(gst_percents[i]) if i < len(gst_percents) and gst_percents[i] else 0.0
        except ValueError: gst = 0.0

        line_gross = qty * rate
        line_disc = line_gross * (disc / 100.0)
        taxable = max(0.0, line_gross - line_disc)

        gst = billing_rate(company, gst_percents[i] if i < len(gst_percents) else None, cust_inv)
        line_tax, cgst, sgst, igst = split_tax(taxable, gst, tax_regime, is_interstate)
        vat_total += line_tax if tax_regime not in ('GST', 'INDIA_GST') else 0.0
        total = round(taxable + line_tax, 2)

        subtotal += taxable
        cgst_total += cgst
        sgst_total += sgst
        igst_total += igst

        base_rate = round(rate * exchange_rate, 4)
        base_taxable = round(taxable * exchange_rate, 2)
        base_total = round(total * exchange_rate, 2)

        inv_item = CustomerInvoiceItem(
            customer_invoice_id=cust_inv.id,
            stock_item_id=stock_id,
            item_code=icode,
            item_name=iname,
            item_description=iname,
            hsn=hsn,
            quantity=qty,
            unit=unit,
            rate=rate,
            base_rate=base_rate,
            discount_percent=disc,
            taxable_amount=taxable,
            base_taxable_amount=base_taxable,
            gst_percent=gst,
            cgst_amount=cgst,
            sgst_amount=sgst,
            igst_amount=igst,
            total_amount=total,
            base_total_amount=base_total
        )
        cdb.add(inv_item)

    cust_inv.subtotal = round(subtotal, 2)
    cust_inv.cgst_total = round(cgst_total, 2)
    cust_inv.sgst_total = round(sgst_total, 2)
    cust_inv.igst_total = round(igst_total, 2)
    cust_inv.tax_amount = round(cgst_total + sgst_total + igst_total + vat_total, 2)
    cust_inv.grand_total = round(subtotal + cust_inv.tax_amount, 2)
    cust_inv.balance = max(0.0, cust_inv.grand_total - (cust_inv.paid_amount or 0.0))

    # Base Currency equivalents
    cust_inv.base_subtotal = round(cust_inv.subtotal * exchange_rate, 2)
    cust_inv.base_tax_amount = round(cust_inv.tax_amount * exchange_rate, 2)
    cust_inv.base_grand_total = round(cust_inv.grand_total * exchange_rate, 2)

    _replace_customer_invoice_journal(cdb, company_id, cust_inv, "Sales invoice edited")
    cdb.commit()
    flash(f"✅ Tax Invoice {cust_inv.invoice_number} updated and accounting re-posted!", "success")
    return redirect(url_for("customer_invoice_view", cust_inv_id=cust_inv.id))


@app.route("/customer-invoices/view/<int:cust_inv_id>")
@login_required
@require_permission("invoices", "view")
def customer_invoice_view(cust_inv_id):
    """View a sales invoice"""
    cdb = get_cdb()
    company_id = get_current_company()
    
    cust_inv = _sales_invoice_query(cdb, company_id).filter_by(id=cust_inv_id).first()
    if not cust_inv:
        flash("Sales invoice not found.", "error")
        return redirect(url_for("customer_invoice_list"))
    
    items = cdb.query(CustomerInvoiceItem).filter_by(customer_invoice_id=cust_inv.id).all()

    # ── Load the client from the company DB ──
    client = None
    if cust_inv.client_id:
        client = cdb.query(Client).filter_by(id=cust_inv.client_id, company_id=company_id).first()

    company = Company.query.filter_by(company_id=company_id).first()

    return render_template("customer_invoice_view.html",
                        invoice=cust_inv,
                        items=items,
                        client=client,
                        company=company,
                        active='customer_invoices')


@app.route("/customer-invoices/delete/<int:cust_inv_id>", methods=["POST"])
@login_required
@require_permission("invoices", "delete")
@require_admin_password
def customer_invoice_delete(cust_inv_id):
    """Delete a sales invoice (soft delete - mark as Void)"""
    cdb = get_cdb()
    company_id = get_current_company()
    
    cust_inv = _sales_invoice_query(cdb, company_id).filter_by(id=cust_inv_id).first()
    if not cust_inv:
        flash("Sales invoice not found.", "error")
        return redirect(url_for("customer_invoice_list"))
    
    if cust_inv.note_adjustment:
        flash("Cancel the posted credit/debit notes before editing or deleting this invoice.", "warning")
        return redirect(url_for("customer_invoice_view", cust_inv_id=cust_inv_id))

    cust_inv.status = "Void"
    _reverse_source_journal(cdb, company_id, "sales_invoice", cust_inv.id,
                            f"Sales invoice {cust_inv.invoice_number} voided")
    cdb.commit()
    
    flash(f"Sales invoice {cust_inv.invoice_number} has been voided.", "success")
    return redirect(url_for("customer_invoice_list"))


@app.route("/customer-invoices/print/<int:cust_inv_id>")
@login_required
@require_permission("invoices", "view")
def customer_invoice_print(cust_inv_id):
    """Print a sales invoice - returns HTML for print or PDF download"""
    from xhtml2pdf import pisa
    import io
    
    cdb = get_cdb()
    company_id = get_current_company()
    
    cust_inv = _sales_invoice_query(cdb, company_id).filter_by(id=cust_inv_id).first()
    if not cust_inv:
        flash("Sales invoice not found.", "error")
        return redirect(url_for("customer_invoice_list"))
    
    items = cdb.query(CustomerInvoiceItem).filter_by(customer_invoice_id=cust_inv.id).all()
    company = Company.query.filter_by(company_id=company_id).first()
    
    # ── Load the client from the company DB ──
    client = None
    if cust_inv.client_id:
        client = cdb.query(Client).filter_by(id=cust_inv.client_id, company_id=company_id).first()
    
    # Get action parameter: 'pdf' or 'print'
    action = request.args.get('action', 'pdf')

    # Per-company invoice template choice — falls back to 'classic' for
    # companies that haven't picked one yet (existing rows, new signups
    # before this field was set).
    template_name = f"customer_invoice_pdf_{company.invoice_template or 'classic'}.html" if company else "customer_invoice_pdf_classic.html"

    # Render HTML content
    html_content = render_template(
        template_name,
        invoice=cust_inv,
        items=items,
        client=client,
        company=company,
        company_logo_url=url_for('static', filename=f'company_logos/{company.logo_filename}', _external=True) if company and company.logo_filename else None,
        is_gst_registered=company.is_gst_registered if company else True,
        today=today_ist().strftime("%d %b %Y"),
        action=action
    )
    
    # If action is 'print', return HTML with print styles
    if action == 'print':
        return render_template(
            template_name,
            invoice=cust_inv,
            items=items,
            client=client,
            company=company,
            company_logo_url=url_for('static', filename=f'company_logos/{company.logo_filename}', _external=True) if company and company.logo_filename else None,
            is_gst_registered=company.is_gst_registered if company else True,
            today=today_ist().strftime("%d %b %Y"),
            action='print'
        )
    
    # Default: Generate PDF
    pdf_file = io.BytesIO()
    pisa_status = pisa.CreatePDF(html_content, dest=pdf_file, encoding='UTF-8')
    
    if pisa_status.err:
        flash(f"PDF generation error: {pisa_status.err}", "error")
        return redirect(url_for("customer_invoice_view", cust_inv_id=cust_inv.id))
    
    pdf_file.seek(0)
    
    return send_file(
        pdf_file,
        as_attachment=True,
        download_name=f"Customer_Invoice_{cust_inv.invoice_number}.pdf",
        mimetype="application/pdf"
    )


@app.route("/company/clear-data", methods=["POST"])
@login_required
@owner_required
def company_clear_data():
    """
    Owner-only: hard-delete selected categories of company data so the
    account can start fresh. Company profile, users/permissions, and
    subscription are never touched by this — only the operational data
    categories the owner explicitly ticks.

    Requires the owner's password AND typing DELETE, since this cannot be
    undone. Deletion order respects FK dependencies (children before
    parents); where a booking's auto-generated purchase-invoice line
    references it via source_invoice_id, that reference is nulled rather
    than left dangling.
    """
    company_id = get_current_company()
    if not company_id:
        return redirect(url_for("login"))
    cdb = get_customer_session(company_id)
    user = get_current_user()

    categories = request.form.getlist("categories")
    password = request.form.get("password", "")
    confirm_text = request.form.get("confirm_text", "")

    if confirm_text.strip().upper() != "DELETE":
        flash("Type DELETE (exactly) to confirm. Nothing was removed.", "danger")
        return redirect(url_for("company_settings"))

    reg_user = RegisteredUser.query.filter_by(email=user.get("email")).first()
    if not reg_user or not verify_password(password, reg_user.password_hash):
        flash("Incorrect password. Nothing was removed.", "danger")
        return redirect(url_for("company_settings"))

    if not categories:
        flash("No categories were selected. Nothing was removed.", "info")
        return redirect(url_for("company_settings"))

    ALL_CATEGORIES = ["bookings", "proforma", "purchases", "stock",
                       "parties", "finance", "price_lists", "whatsapp"]
    if "everything" in categories:
        categories = ALL_CATEGORIES

    removed = []
    try:
        if "bookings" in categories:
            inv_ids = [r.id for r in cdb.query(Invoice.id).filter_by(company_id=company_id)]
            if inv_ids:
                cdb.query(PurchaseInvoiceItem).filter(
                    PurchaseInvoiceItem.source_invoice_id.in_(inv_ids)
                ).update({"source_invoice_id": None}, synchronize_session=False)
                cdb.query(InvoiceItem).filter(InvoiceItem.invoice_id.in_(inv_ids)).delete(synchronize_session=False)
            cdb.query(Invoice).filter_by(company_id=company_id).delete(synchronize_session=False)
            removed.append("Bookings")

        if "proforma" in categories:
            est_ids = [r.id for r in cdb.query(Estimate.id).filter_by(company_id=company_id)]
            if est_ids:
                cdb.query(EstimateItem).filter(EstimateItem.estimate_id.in_(est_ids)).delete(synchronize_session=False)
            cdb.query(Estimate).filter_by(company_id=company_id).delete(synchronize_session=False)
            removed.append("Proforma Invoices")

        if "purchases" in categories:
            pi_ids = [r.id for r in cdb.query(PurchaseInvoice.id).filter_by(company_id=company_id)]
            cdb.query(PurchasePayment).filter_by(company_id=company_id).delete(synchronize_session=False)
            if pi_ids:
                cdb.query(PurchaseInvoiceItem).filter(
                    PurchaseInvoiceItem.purchase_invoice_id.in_(pi_ids)
                ).delete(synchronize_session=False)
                cdb.query(StockPurchaseHistory).filter(
                    StockPurchaseHistory.purchase_invoice_id.in_(pi_ids)
                ).delete(synchronize_session=False)
            cdb.query(PurchaseInvoice).filter_by(company_id=company_id).delete(synchronize_session=False)
            removed.append("Purchase Invoices")

        if "stock" in categories:
            stock_ids = [r.id for r in cdb.query(StockItem.id).filter_by(company_id=company_id)]
            if stock_ids:
                cdb.query(StockPurchaseHistory).filter(
                    StockPurchaseHistory.stock_item_id.in_(stock_ids)
                ).delete(synchronize_session=False)
            cdb.query(StockItem).filter_by(company_id=company_id).delete(synchronize_session=False)
            removed.append("Stock")

        if "parties" in categories:
            sup_ids = [r.id for r in cdb.query(Supplier.id).filter_by(company_id=company_id)]
            if sup_ids:
                cdb.query(SupplierBrand).filter(SupplierBrand.supplier_id.in_(sup_ids)).delete(synchronize_session=False)
            cdb.query(Supplier).filter_by(company_id=company_id).delete(synchronize_session=False)
            cdb.query(Client).filter_by(company_id=company_id).delete(synchronize_session=False)
            removed.append("Clients & Suppliers")

        if "finance" in categories:
            loan_ids = [r.id for r in cdb.query(Loan.id).filter_by(company_id=company_id)]
            if loan_ids:
                cdb.query(LoanRepayment).filter(LoanRepayment.loan_id.in_(loan_ids)).delete(synchronize_session=False)
            cdb.query(Cheque).filter_by(company_id=company_id).delete(synchronize_session=False)
            cdb.query(BankTransaction).filter_by(company_id=company_id).delete(synchronize_session=False)
            cdb.query(BankAccount).filter_by(company_id=company_id).delete(synchronize_session=False)
            cdb.query(Loan).filter_by(company_id=company_id).delete(synchronize_session=False)
            cdb.query(CashTransaction).filter_by(company_id=company_id).delete(synchronize_session=False)
            cdb.query(Expense).filter_by(company_id=company_id).delete(synchronize_session=False)
            removed.append("Cash, Bank, Loans & Expenses")

        if "price_lists" in categories:
            cdb.query(RateLookup).filter_by(company_id=company_id).delete(synchronize_session=False)
            cdb.query(PriceList).filter_by(company_id=company_id).delete(synchronize_session=False)
            removed.append("Price Lists")

        if "whatsapp" in categories:
            cdb.query(WhatsAppLog).filter_by(company_id=company_id).delete(synchronize_session=False)
            removed.append("WhatsApp Logs")

        cdb.commit()
        flash(
            f"Cleared: {', '.join(removed)}. Company profile, users and permissions were not touched.",
            "success",
        )
    except Exception as e:
        cdb.rollback()
        print(f"[clear-data] FAILED for company {company_id}: {e}")
        flash(f"Clear-data failed and was rolled back: {e}", "danger")

    return redirect(url_for("company_settings"))


@app.route("/api/suppliers/list")
@login_required
@require_permission("suppliers", "view")
def api_suppliers_list():
    cdb = get_cdb()
    company_id = get_current_company()
    
    # Query the Supplier table (not Client)
    suppliers = cdb.query(Supplier).filter(
        Supplier.company_id == company_id,
        Supplier.status == "Active"
    ).order_by(Supplier.name).all()
    
    return jsonify([{
        "id": s.id,
        "name": s.name,
        "gst": s.gst_number or "",
        "phone": s.phone or "",
        "contact_person": s.contact_person or ""
    } for s in suppliers])


# ── Suppliers ─────────────────────────────────────────────────────────────────
# Add this block in app.py right after client_delete() and before the Stock section.
# Also add  Supplier  to the customer_models import line at the top of app.py.
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_supplier(s, payable=None):
    """Return a dict whose keys match what suppliers.html / supplier_form.html expect.

    `payable`: pass a live-computed total (opening_balance + Σ(grand_total -
    paid_amount) across purchase invoices) to show real current dues. If
    omitted, falls back to the cached s.payable field."""
    return {
        "id":              s.id,
        "client_name":     s.name,               # alias so ledger_statement.html's entity.client_name works for suppliers too
        "client_id":       s.supplier_id or "—",  # same reason, mirrors _normalize_client's client_id
        "supplier_id":     s.supplier_id or "—",
        "name": s.name,
        "supplier_name":   s.name,
        "supplier_type":   s.supplier_type   or "Business",
        "contact_person":  s.contact_person  or "",
        "phone":           s.phone           or "",
        "alternate_phone": s.alternate_phone or "",
        "email":           s.email           or "",
        "website":         s.website         or "",
        "address_line1":   s.address_line1   or "",
        "address_line2":   s.address_line2   or "",
        "city":            s.city            or "",
        "state":           s.state           or "",
        "pincode":         s.pincode         or "",
        "country":         s.country         or "India",
        "gst_number":      s.gst_number      or "",
        "pan_number":      s.pan_number      or "",
        "aadhar_number":   s.aadhar_number   or "",
        "gst_type":        s.gst_type        or "Regular",
        "credit_limit":    s.credit_limit    or 0.0,
        "credit_days":     s.credit_days     or 30,
        "payable":         payable if payable is not None else (s.payable or 0.0),
        "opening_balance": s.opening_balance or 0.0,
        "last_purchase":   s.last_purchase,
        "status":          s.status          or "Active",
        "notes":           s.notes           or "",
        "created_at":      s.created_at,
    }


@app.route("/suppliers")
@login_required
@require_permission("suppliers", "view")
def supplier_list():
    cdb           = get_cdb()
    company_id    = get_current_company()
    filter_status = request.args.get("status", "All")

    query = cdb.query(Supplier).filter_by(company_id=company_id)
    if filter_status != "All":
        query = query.filter_by(status=filter_status)

    supplier_rows = query.all()

    # Live total — same formula as _creditor_summary() / the creditor statement's
    # closing balance: opening_balance + Σ(grand_total) − actual cash/bank
    # payments (CashTransaction/BankTransaction matched by party_name), NOT
    # PurchaseInvoice.paid_amount. paid_amount-only sums silently ignore any
    # advance, unmatched, or split payment that wasn't applied to one specific
    # invoice's balance — same bug already fixed in _creditor_summary() (used
    # by /creditors) and _build_supplier_ledger() (used by the statement page).
    # This was the one place still on the old formula, which is why the
    # Suppliers list Payable could disagree with the statement/ledger balance.
    live_by_supplier = {d["id"]: d["total_pending"] for d in _creditor_summary(company_id)}

    suppliers = [
        _normalize_supplier(s, payable=live_by_supplier.get(s.id, s.opening_balance or 0.0))
        for s in supplier_rows
    ]

    return render_template("suppliers.html", suppliers=suppliers, current_status=filter_status)


@app.route("/suppliers/new", methods=["GET", "POST"])
@login_required
@require_permission("suppliers", "view", method_actions={'POST': 'create'})
def supplier_new():
    cdb        = get_cdb()
    company_id = get_current_company()
    if request.method == "POST":
        f   = request.form
        gst = f.get("gst_number", "").strip().upper()

        if gst:
            existing_gst = cdb.query(Supplier).filter_by(
                company_id=company_id, gst_number=gst
            ).first()
            if existing_gst:
                flash(f"GST number {gst} is already registered to supplier '{existing_gst.name}'. Please check and try again.", "error")
                return render_template("supplier_form.html", form_data=f, existing_brands=f.getlist("brand_name[]"))

        company_obj = Company.query.filter_by(company_id=company_id).first()
        supplier_prefix = _company_name_prefix(company_obj.company_name if company_obj else "", from_end=False)
        new_supplier_id = _next_numbered_id(cdb, Supplier.supplier_id, supplier_prefix, extra_filters=[Supplier.company_id == company_id])

        new_supplier = Supplier(
            supplier_id     = new_supplier_id,
            company_id      = company_id,
            name            = f.get("supplier_name", "").strip(),
            supplier_type   = f.get("supplier_type", "Business"),
            contact_person  = f.get("contact_person", "").strip(),
            phone           = f.get("phone", "").strip(),
            alternate_phone = f.get("alternate_phone", "").strip(),
            email           = f.get("email", "").strip().lower(),
            website         = f.get("website", "").strip(),
            address_line1   = f.get("address_line1", "").strip(),
            address_line2   = f.get("address_line2", "").strip(),
            city            = f.get("city", "").strip(),
            state           = f.get("state", "").strip(),
            pincode         = f.get("pincode", "").strip(),
            country         = f.get("country", "India").strip(),
            gst_number      = gst or None,
            pan_number      = f.get("pan_number", "").strip().upper() or None,
            aadhar_number   = f.get("aadhar_number", "").strip() or None,
            gst_type        = f.get("gst_type", "Regular"),
            credit_limit    = float(f.get("credit_limit", 0) or 0),
            credit_days     = int(f.get("credit_days", 30) or 30),
            payable         = float(f.get("opening_balance", 0) or 0),
            opening_balance = float(f.get("opening_balance", 0) or 0),
            status          = f.get("status", "Active") or "Active",
            notes           = f.get("notes", "").strip(),
            created_at      = today_ist(),
        )
        cdb.add(new_supplier)
        cdb.commit()

        brand_names = [b.strip() for b in f.getlist("brand_name[]") if b.strip()]
        seen = set()
        for b in brand_names:
            key = b.lower()
            if key in seen:
                continue
            seen.add(key)
            cdb.add(SupplierBrand(supplier_id=new_supplier.id, brand_name=b))
        if brand_names:
            cdb.commit()

        flash(f"Supplier '{new_supplier.name}' added successfully!")
        return redirect(url_for("supplier_list"))
    return render_template("supplier_form.html", form_data={}, existing_brands=[])


@app.route("/suppliers/<int:supplier_pk>")
@login_required
@require_permission("suppliers", "view")
def supplier_view(supplier_pk):
    cdb        = get_cdb()
    company_id = get_current_company()
    s          = _first_or_404(cdb.query(Supplier).filter_by(id=supplier_pk, company_id=company_id).first())
    supplier   = _normalize_supplier(s)
    purchases  = cdb.query(PurchaseInvoice).filter_by(company_id=company_id, supplier_id=s.id).order_by(PurchaseInvoice.date.desc()).all()
    return render_template("supplier_detail.html", supplier=supplier, purchases=purchases)

def _build_supplier_ledger(cdb, company_id, s, since=None, until=None):
    """Builds the creditor ledger for a supplier. `since` (a datetime) is the
    statement cutoff — only purchase invoices dated ON or AFTER its date are
    included, and the opening line reflects the carried-forward balance as
    of that cutoff. `until` (a date, exclusive) caps an archive at entries
    dated BEFORE today — same reasoning as _build_client_ledger().

    BUG FIX: payment lines are now built from actual CashTransaction/
    BankTransaction records matched to the supplier by party_name, instead
    of being derived from PurchaseInvoice.paid_amount. Deriving from
    paid_amount meant (1) advance/unmatched/split payments never showed up
    at all, since the loop only ever walked invoices, and (2) multiple
    partial payments against one invoice collapsed into a single line
    stamped with the invoice's date instead of each payment's real date.
    Same fix already applied in creditor_statement() — this brings this
    route in line with it."""
    since_date = since.date() if since else None
    until_date = until.date() if hasattr(until, "date") else until

    invoices_q = cdb.query(PurchaseInvoice).filter_by(company_id=company_id, supplier_id=s.id)
    invoices_q = invoices_q.filter(PurchaseInvoice.status.notin_(['Cancelled', 'Void']))
    if since_date:
        invoices_q = invoices_q.filter(PurchaseInvoice.date >= since_date)
    if until_date:
        invoices_q = invoices_q.filter(PurchaseInvoice.date < until_date)
    invoices = invoices_q.order_by(PurchaseInvoice.date.asc()).all()

    cash_q = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        func.lower(CashTransaction.party_name) == func.lower(s.name)
    ).filter(CashTransaction.category == "Payment")
    if since_date:
        cash_q = cash_q.filter(CashTransaction.date >= since_date)
    if until_date:
        cash_q = cash_q.filter(CashTransaction.date < until_date)

    bank_q = cdb.query(BankTransaction).filter(
        BankTransaction.company_id == company_id,
        func.lower(BankTransaction.party_name) == func.lower(s.name)
    ).filter(BankTransaction.type == "debit")
    if since_date:
        bank_q = bank_q.filter(BankTransaction.date >= since_date)
    if until_date:
        bank_q = bank_q.filter(BankTransaction.date < until_date)

    blank_ship_fields = {
        "awb": "", "consignor": "", "consignee": "", "destination": "",
        "carrier_ref": "", "carrier": "", "chrg_wt": 0, "act_wt": 0, "vol_wt": 0,
        "grand_total": 0, "other_charges": 0, "billing_amount": 0,
    }

    events = []
    for inv in invoices:
        ship_rows = _purchase_shipment_rows(inv.items)
        grand_total = inv.grand_total or 0
        # Other Charges is captured per line item on the purchase side, so the
        # invoice-level figure show alongside Grand Total is the sum across items.
        other_charges = sum(r["other_charges"] for r in ship_rows)
        events.append({
            "date": inv.date,
            "type": "Purchase Invoice",
            "ref": inv.invoice_number or inv.invoice_id,
            "awb": ship_rows[0]["awb"],
            "consignor": "",
            "consignee": ship_rows[0]["consignee"],
            "destination": ship_rows[0]["destination"],
            "carrier_ref": ship_rows[0]["carrier_ref"],
            "carrier": ship_rows[0]["carrier"],
            "chrg_wt": ship_rows[0]["chrg_wt"],
            "act_wt": ship_rows[0]["act_wt"],
            "vol_wt": ship_rows[0]["vol_wt"],
            "grand_total": grand_total,
            "other_charges": other_charges,
            "billing_amount": other_charges + grand_total,
            "per_kg": ship_rows[0].get("per_kg", 0),
            "shipments": ship_rows,
            "debit": 0,
            "credit": grand_total,
            "status": inv.status,
            "id": inv.id,
            "inv_id": inv.invoice_id,
            "_sort": 0,
        })

    for ct in cash_q.all():
        ref = ct.reference or ""
        events.append({
            "date": ct.date,
            "type": "Payment Made",
            "ref": "—" if ref == "ADVANCE" else (ref or "—"),
            **blank_ship_fields,
            "debit": ct.amount or 0,
            "credit": 0,
            "status": "",
            "id": None,
            "inv_id": None,
            "_sort": 1,
        })

    for bt in bank_q.all():
        ref = bt.reference or ""
        events.append({
            "date": bt.date,
            "type": "Payment Made",
            "ref": "—" if ref == "ADVANCE" else (ref or "—"),
            **blank_ship_fields,
            "debit": bt.amount or 0,
            "credit": 0,
            "status": "",
            "id": None,
            "inv_id": None,
            "_sort": 1,
        })

    events.extend(note_statement_events(cdb, company_id, 'debit', s.id, since_date, until_date))

    events.sort(key=lambda e: (e["date"] or date.min, e["_sort"]))

    ledger = []
    running_balance = s.opening_balance or 0.0

    # Opening balance / balance carried forward. Same fix as the client
    # ledger: use the cutoff date, not the supplier's original created_at.
    if running_balance:
        ledger.append({
            "date": since.date() if since else (s.created_at or today_ist()),
            "type": "Balance Carried Forward" if since else "Opening Balance",
            "ref": "—",
            **blank_ship_fields,
            "debit": 0,
            "credit": running_balance,
            "balance": running_balance,
            "status": "",
            "id": None,
            "inv_id": None,
        })

    for e in events:
        running_balance += (e["credit"] or 0) - (e["debit"] or 0)
        e["balance"] = running_balance
        del e["_sort"]
        ledger.append(e)

    total_debit = sum(r["debit"] for r in ledger)
    total_credit = sum(r["credit"] for r in ledger)

    return ledger, total_debit, total_credit, running_balance


@app.route("/suppliers/<int:supplier_pk>/statement")
@login_required
@require_permission("suppliers", "view")
def supplier_statement(supplier_pk):
    """Statement view for a supplier (creditor-style ledger)"""
    cdb = get_cdb()
    company_id = get_current_company()
    s = _first_or_404(cdb.query(Supplier).filter_by(id=supplier_pk, company_id=company_id).first())

    ledger, total_debit, total_credit, running_balance = _build_supplier_ledger(
        cdb, company_id, s, since=s.statement_cutoff)

    archives = (cdb.query(StatementClosing)
                .filter_by(company_id=company_id, entity_type="supplier", entity_id=s.id)
                .order_by(StatementClosing.closed_at.desc())
                .all())

    return render_template("ledger_statement.html",
                           entity=_normalize_supplier(s),
                           company=get_company_by_id(company_id),
                           ledger=ledger,
                           total_debit=total_debit,
                           total_credit=total_credit,
                           closing_balance=running_balance,
                           mode="creditor",
                           nav_active="suppliers",
                           back_url=f"/suppliers/{supplier_pk}",
                           archive_base_url=f"/suppliers/{supplier_pk}",
                           archives=archives,
                           archived=False,
                           today=today_ist().strftime("%d %b %Y"))


@app.route("/suppliers/<int:supplier_pk>/statement/archive/<int:archive_id>")
@login_required
@require_permission("suppliers", "view")
def supplier_statement_archive(supplier_pk, archive_id):
    """Prints a frozen old statement exactly as it looked at the moment the
    payable was cleared/shifted."""
    cdb = get_cdb()
    company_id = get_current_company()
    s = _first_or_404(cdb.query(Supplier).filter_by(id=supplier_pk, company_id=company_id).first())
    archive = _first_or_404(cdb.query(StatementClosing).filter_by(
        id=archive_id, company_id=company_id, entity_type="supplier", entity_id=supplier_pk).first())

    return render_template("ledger_statement.html",
                           entity=_normalize_supplier(s),
                           company=get_company_by_id(company_id),
                           ledger=json.loads(archive.ledger_snapshot or "[]"),
                           total_debit=archive.total_debit,
                           total_credit=archive.total_credit,
                           closing_balance=archive.closing_balance,
                           mode="creditor",
                           nav_active="suppliers",
                           back_url=f"/suppliers/{supplier_pk}/statement",
                           archived=True,
                           archived_at=archive.closed_at,
                           today=today_ist().strftime("%d %b %Y"))

@app.route("/suppliers/<int:supplier_pk>/edit", methods=["GET", "POST"])
@login_required
@require_permission("suppliers", "view", method_actions={'POST': 'edit'})
def supplier_edit(supplier_pk):
    cdb        = get_cdb()
    company_id = get_current_company()
    s          = _first_or_404(cdb.query(Supplier).filter_by(id=supplier_pk, company_id=company_id).first())
    if request.method == "POST":
        f   = request.form
        gst = f.get("gst_number", "").strip().upper()

        if gst:
            existing_gst = cdb.query(Supplier).filter(
                Supplier.company_id == company_id,
                Supplier.gst_number == gst,
                Supplier.id != s.id
            ).first()
            if existing_gst:
                flash(f"GST number {gst} is already registered to supplier '{existing_gst.name}'.", "error")
                return render_template(
                    "supplier_form.html",
                    supplier=_normalize_supplier(s),
                    form_data=f,
                    existing_brands=f.getlist("brand_name[]")
                )

        s.name            = f.get("supplier_name",   s.name).strip()
        s.supplier_type   = f.get("supplier_type",   s.supplier_type)
        s.contact_person  = f.get("contact_person",  s.contact_person  or "").strip()
        s.phone           = f.get("phone",            s.phone           or "").strip()
        s.alternate_phone = f.get("alternate_phone",  s.alternate_phone or "").strip()
        s.email           = f.get("email",            s.email           or "").strip().lower()
        s.website         = f.get("website",          s.website         or "").strip()
        s.address_line1   = f.get("address_line1",    s.address_line1   or "").strip()
        s.address_line2   = f.get("address_line2",    s.address_line2   or "").strip()
        s.city            = f.get("city",             s.city            or "").strip()
        s.state           = f.get("state",            s.state           or "").strip()
        s.pincode         = f.get("pincode",          s.pincode         or "").strip()
        s.country         = f.get("country",          s.country         or "India").strip()
        s.gst_number      = gst or None
        s.pan_number      = f.get("pan_number",       s.pan_number      or "").strip().upper() or None
        s.aadhar_number   = f.get("aadhar_number",    s.aadhar_number   or "").strip() or None
        s.gst_type        = f.get("gst_type",         s.gst_type)
        s.credit_limit    = float(f.get("credit_limit",    s.credit_limit    or 0) or 0)
        s.credit_days     = int(f.get("credit_days",       s.credit_days     or 30) or 30)
        s.opening_balance = float(f.get("opening_balance", s.opening_balance or 0) or 0)
        s.status          = f.get("status", s.status)
        s.notes           = f.get("notes",  s.notes or "").strip()

        # Replace brand list with whatever was submitted (simplest correct
        # behavior for a short add/remove-row UI — no per-row diffing needed)
        cdb.query(SupplierBrand).filter_by(supplier_id=s.id).delete()
        brand_names = [b.strip() for b in f.getlist("brand_name[]") if b.strip()]
        seen = set()
        for b in brand_names:
            key = b.lower()
            if key in seen:
                continue
            seen.add(key)
            cdb.add(SupplierBrand(supplier_id=s.id, brand_name=b))

        cdb.commit()
        flash(f"Supplier '{s.name}' updated successfully!")
        return redirect(url_for("supplier_list"))
    return render_template(
        "supplier_form.html",
        supplier=_normalize_supplier(s),
        form_data={},
        existing_brands=sorted(b.brand_name for b in s.brands)
    )


# /suppliers/<id>/delete  ── kept at the old URL/template link so nothing else
# breaks, but this NO LONGER deletes the supplier row (same reasoning as
# client_delete: invoices are GST records referenced by other FKs). Now
# archives the old statement and clears the payable/statement only.
@app.route("/suppliers/<int:supplier_pk>/delete", methods=["GET", "POST"])
@login_required
@owner_required
@require_admin_password
def supplier_delete(supplier_pk):
    cdb        = get_cdb()
    company_id = get_current_company()
    s          = _first_or_404(cdb.query(Supplier).filter_by(id=supplier_pk, company_id=company_id).first())
    scope = request.args.get("scope", "till_yesterday")
    if scope not in ("complete", "till_yesterday"):
        scope = "till_yesterday"
    amount = _supplier_close_statement(cdb, company_id, s, action="cleared", scope=scope)
    cdb.commit()
    if amount:
        if scope == "complete":
            flash(f"Payable of {company_currency_symbol()} {amount:,.2f} cleared for '{s.name}', including today's entries. Old statement archived — supplier record and purchase invoices were kept.")
        else:
            flash(f"Payable of {company_currency_symbol()} {amount:,.2f} cleared for '{s.name}' up to yesterday. Old statement archived — today's entries remain in the new statement.")
    else:
        flash(f"'{s.name}' had no payable to clear.")
    return redirect(url_for("supplier_list"))


# /suppliers/<id>/shift-to-opening  ── archives the itemised ledger the same
# way as above, but carries the amount forward as a single opening_balance
# figure. Defaults to yesterday, but an explicit ?as_of=YYYY-MM-DD lets the
# user pick an earlier cutoff — anything after that date stays live.
@app.route("/suppliers/<int:supplier_pk>/shift-to-opening", methods=["GET", "POST"])
@login_required
@owner_required
@require_admin_password
def supplier_shift_to_opening(supplier_pk):
    cdb        = get_cdb()
    company_id = get_current_company()
    s          = _first_or_404(cdb.query(Supplier).filter_by(id=supplier_pk, company_id=company_id).first())
    as_of_date = None
    as_of_raw = request.args.get("as_of")
    if as_of_raw:
        try:
            as_of_date = datetime.strptime(as_of_raw, "%Y-%m-%d").date()
        except ValueError:
            as_of_date = None
    amount = _supplier_close_statement(cdb, company_id, s, action="carried_forward", as_of_date=as_of_date)
    cdb.commit()
    flash(f"{company_currency_symbol()} {amount:,.2f} carried forward as opening balance for '{s.name}', as of "
          f"{(s.statement_cutoff - timedelta(days=1)).strftime('%d %b %Y')}. New statement starts "
          f"{s.statement_cutoff.strftime('%d %b %Y')}; entries from then on stay live.")
    return redirect(url_for("supplier_list"))

@app.route("/api/supplier/<int:supplier_pk>/brands")
@login_required
@require_permission("suppliers", "view")
def api_supplier_brands(supplier_pk):
    """Return this supplier's registered brand/courier names for the purchase form's
    dependent courier dropdown. Empty list means 'no brands registered' — the
    frontend falls back to the general COURIER_OPTIONS list in that case."""
    cdb        = get_cdb()
    company_id = get_current_company()
    s = cdb.query(Supplier).filter_by(id=supplier_pk, company_id=company_id).first()
    if not s:
        return jsonify({"brands": []}), 404
    brands = sorted(b.brand_name for b in s.brands)
    return jsonify({"brands": brands})


@app.route("/api/customers/list")
@login_required
@require_permission("clients", "view")
def api_customers_list():
    """Return list of customers (non-supplier clients) for the purchase form dropdown."""
    cdb = get_cdb()
    company_id = get_current_company()
    customers = cdb.query(Client).filter(
        Client.company_id == company_id,
        ~Client.client_type.in_(["Supplier", "Both", "Cash-Only"])
    ).filter(Client.status == "Active").order_by(Client.name).all()

    return jsonify([{
        "id":       c.id,
        "name":     c.name,
        "phone":    c.phone or "",
        "email":    c.email or "",
        "city":     c.city or "",
        "gst":      c.gst_number or "",
        "address":  c.address_line1 or "",
    } for c in customers])

@app.route("/api/stock/items/by-client/<int:client_id>")
@login_required
@require_permission("stock", "view")
def api_stock_items_by_client(client_id):
    """Return stock items that have been previously invoiced to a specific client.
    If no history found, returns ALL stock items."""
    cdb = get_cdb()
    company_id = get_current_company()

    # Find all stock item IDs that appear in invoices for this client
    linked_stock_ids = db.session.query(InvoiceItem.stock_item_id).join(
        Invoice, InvoiceItem.invoice_id == Invoice.id
    ).filter(
        Invoice.company_id == company_id,
        Invoice.client_id  == client_id,
        InvoiceItem.stock_item_id.isnot(None)
    ).distinct().all()

    stock_ids = [row[0] for row in linked_stock_ids if row[0] is not None]

    if not stock_ids:
        # No history - return ALL stock items
        items = cdb.query(StockItem).filter_by(company_id=company_id).order_by(StockItem.name).all()
    else:
        items = cdb.query(StockItem).filter(
            StockItem.company_id == company_id,
            StockItem.id.in_(stock_ids)
        ).order_by(StockItem.name).all()

    return jsonify([{
        "id":            item.id,
        "code":          item.code or "",
        "name":          item.name,
        "unit":          item.unit or "pcs",
        "quantity":      item.quantity,
        "unit_price":    float(item.unit_price or 0),
        "purchase_rate": float(item.purchase_rate or item.last_purchase_rate or 0),
        "gst_percent":   float(item.gst_percent if item.gst_percent is not None else billing_rate(get_company_by_id(company_id))),
        "hsn":           item.hsn or "",
        "category":      item.category or "",
    } for item in items])


# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────


@app.route("/estimate/new", methods=["GET", "POST"])
@login_required
@require_permission("estimates", "view", method_actions={'POST': 'create'})
def estimate_new():
    """Create or edit a product quotation / estimate"""
    cdb = get_cdb()
    company_id = get_current_company()
    company = Company.query.filter_by(company_id=company_id).first()
    
    edit_id = request.args.get("edit")
    is_edit = bool(edit_id)
    estimate = None
    if edit_id:
        estimate = cdb.query(Estimate).filter_by(estimate_id=edit_id, company_id=company_id).first()
        if not estimate:
            try:
                estimate = cdb.query(Estimate).filter_by(id=int(edit_id), company_id=company_id).first()
            except Exception:
                pass

    if request.method == "POST":
        estimate_id = request.form.get("estimate_id", "").strip()
        client_id_raw = request.form.get("client_id", "").strip()
        client_id = int(client_id_raw) if client_id_raw and client_id_raw.isdigit() else None
        client_name = request.form.get("client_name", "").strip()
        client_gstin = request.form.get("client_gstin", "").strip()
        client_state = request.form.get("client_state", "").strip()
        client_address = request.form.get("client_address", "").strip()
        contact_person = request.form.get("contact_person", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        
        estimate_date_str = request.form.get("estimate_date")
        valid_until_str = request.form.get("valid_until")
        payment_terms = request.form.get("payment_terms", "").strip()
        delivery_terms = request.form.get("delivery_terms", "").strip()
        status = request.form.get("status", "Draft").strip()
        terms = request.form.get("terms", "").strip()
        notes = request.form.get("notes", "").strip()

        estimate_date = datetime.strptime(estimate_date_str, "%Y-%m-%d").date() if estimate_date_str else today_ist().date()
        valid_until = datetime.strptime(valid_until_str, "%Y-%m-%d").date() if valid_until_str else None

        if not estimate_id:
            estimate_id = _next_numbered_id(cdb, Estimate.estimate_id, "EST-", extra_filters=[Estimate.company_id == company_id])

        if is_edit and estimate:
            est = estimate
            est.estimate_id = estimate_id
            est.client_id = client_id
            est.client_name = client_name
            est.client_gstin = client_gstin
            est.client_state = client_state
            est.client_address = client_address
            est.contact_person = contact_person
            est.phone = phone
            est.email = email
            est.date = estimate_date
            est.valid_until = valid_until
            est.payment_terms = payment_terms
            est.delivery_terms = delivery_terms
            est.status = status
            est.terms = terms
            est.notes = notes
            est.updated_by = session.get("user", {}).get("username") or session.get("user_id")
            cdb.query(EstimateItem).filter_by(estimate_id=est.id).delete()
        else:
            est = Estimate(
                estimate_id=estimate_id,
                company_id=company_id,
                client_id=client_id,
                client_name=client_name,
                client_gstin=client_gstin,
                client_state=client_state,
                client_address=client_address,
                contact_person=contact_person,
                phone=phone,
                email=email,
                date=estimate_date,
                valid_until=valid_until,
                payment_terms=payment_terms,
                delivery_terms=delivery_terms,
                status=status,
                terms=terms,
                notes=notes,
                created_by=session.get("user", {}).get("username") or session.get("user_id"),
            )
            cdb.add(est)
            cdb.flush()

        # Parse Line Items
        item_codes = request.form.getlist("item_code[]")
        item_names = request.form.getlist("item_name[]")
        hsns = request.form.getlist("hsn[]")
        quantities = request.form.getlist("quantity[]")
        units = request.form.getlist("unit[]")
        rates = request.form.getlist("rate[]")
        discount_percents = request.form.getlist("discount_percent[]")
        gst_percents = request.form.getlist("gst_percent[]")
        stock_item_ids = request.form.getlist("stock_item_id[]")

        subtotal = 0.0
        cgst_total = 0.0
        sgst_total = 0.0
        igst_total = 0.0

        company_state = (company.state or "").strip().lower() if company else ""
        c_state = (client_state or "").strip().lower()
        is_interstate = bool(company_state and c_state and company_state != c_state)

        for i in range(len(item_names)):
            name = item_names[i].strip()
            if not name:
                continue
            code = item_codes[i].strip() if i < len(item_codes) else ""
            hsn = hsns[i].strip() if i < len(hsns) else ""
            try:
                qty = float(quantities[i]) if i < len(quantities) and quantities[i] else 1.0
            except ValueError:
                qty = 1.0
            unit = units[i].strip() if i < len(units) and units[i] else "pcs"
            try:
                rate = float(rates[i]) if i < len(rates) and rates[i] else 0.0
            except ValueError:
                rate = 0.0
            try:
                disc_pct = float(discount_percents[i]) if i < len(discount_percents) and discount_percents[i] else 0.0
            except ValueError:
                disc_pct = 0.0
            try:
                gst_pct = float(gst_percents[i]) if i < len(gst_percents) and gst_percents[i] else 0.0
            except ValueError:
                gst_pct = 0.0
            
            st_id = None
            if i < len(stock_item_ids) and stock_item_ids[i] and stock_item_ids[i].isdigit():
                st_id = int(stock_item_ids[i])

            base_val = qty * rate
            disc_amt = base_val * (disc_pct / 100.0)
            taxable = base_val - disc_amt
            tax_amt = taxable * (gst_pct / 100.0)

            if is_interstate:
                cgst_amt = 0.0
                sgst_amt = 0.0
                igst_amt = tax_amt
            else:
                cgst_amt = tax_amt / 2.0
                sgst_amt = tax_amt / 2.0
                igst_amt = 0.0

            row_total = taxable + tax_amt

            subtotal += taxable
            cgst_total += cgst_amt
            sgst_total += sgst_amt
            igst_total += igst_amt

            item_obj = EstimateItem(
                estimate_id=est.id,
                stock_item_id=st_id,
                item_code=code,
                code=code,
                item_name=name,
                description=name,
                hsn=hsn,
                qty=qty,
                unit=unit,
                rate=rate,
                discount=disc_pct,
                discount_percent=disc_pct,
                taxable_amount=taxable,
                gst_percent=gst_pct,
                cgst_amount=cgst_amt,
                sgst_amount=sgst_amt,
                igst_amount=igst_amt,
                total_amount=row_total,
            )
            cdb.add(item_obj)

        est.subtotal = round(subtotal, 2)
        est.cgst_total = round(cgst_total, 2)
        est.sgst_total = round(sgst_total, 2)
        est.igst_total = round(igst_total, 2)
        est.tax_amount = round(cgst_total + sgst_total + igst_total, 2)
        est.grand_total = round(subtotal + est.tax_amount, 2)

        cdb.commit()
        log_audit_event(cdb, company_id, "estimate", est.id, "update" if is_edit else "create", f"Quotation {est.estimate_id} saved for {est.client_name}")
        flash(f"Quotation {est.estimate_id} saved successfully!", "success")
        return redirect(url_for("estimate_view", estimate_id=est.estimate_id))

    clients = cdb.query(Client).filter_by(company_id=company_id).filter(Client.status != "Deleted").order_by(Client.name).all()
    default_est_no = _next_numbered_id(cdb, Estimate.estimate_id, "EST-", extra_filters=[Estimate.company_id == company_id])
    today_date = today_ist().strftime("%Y-%m-%d")

    return render_template(
        "estimate_form.html",
        is_edit=is_edit,
        estimate=estimate,
        clients=clients,
        default_estimate_no=default_est_no,
        today_date=today_date,
        company=company,
    )


@app.route("/estimate/list")
@login_required
@require_permission("estimates", "view")
def estimate_list():
    cdb = get_cdb()
    company_id = get_current_company()
    filter_status = request.args.get("status", "All")
    query = cdb.query(Estimate).filter_by(company_id=company_id)
    if filter_status != "All":
        query = query.filter_by(status=filter_status)
    estimates = query.order_by(Estimate.date.desc(), Estimate.id.desc()).all()
    return render_template("estimate_list.html", estimates=estimates, current_status=filter_status)


@app.route("/estimate/view/<estimate_id>")
@login_required
@require_permission("estimates", "view")
def estimate_view(estimate_id):
    cdb = get_cdb()
    company_id = get_current_company()
    est = cdb.query(Estimate).filter_by(estimate_id=estimate_id, company_id=company_id).first()
    if not est:
        try:
            est = cdb.query(Estimate).filter_by(id=int(estimate_id), company_id=company_id).first()
        except Exception:
            pass
    if not est:
        flash("Quotation not found.", "error")
        return redirect(url_for("estimate_list"))

    company = Company.query.filter_by(company_id=company_id).first()
    return render_template("estimate_view.html", estimate=est, company=company)


@app.route("/estimate/edit/<estimate_id>", methods=["GET", "POST"])
@login_required
@require_permission("estimates", "edit")
def estimate_edit(estimate_id):
    """Edit quotation route"""
    if request.method == "POST":
        return redirect(url_for("estimate_new", edit=estimate_id))
    return redirect(url_for("estimate_new", edit=estimate_id))


@app.route("/estimate/update", methods=["POST"])
@login_required
@require_permission("estimates", "edit")
def estimate_update():
    estimate_id = request.form.get("edit_estimate_id") or request.form.get("estimate_id")
    return redirect(url_for("estimate_new", edit=estimate_id))


@app.route("/estimate/convert_to_so/<estimate_id>", methods=["POST"])
@login_required
@require_permission("estimates", "create")
def estimate_convert_to_so(estimate_id):
    """Convert Quotation to Sales Order"""
    cdb = get_cdb()
    company_id = get_current_company()
    est = cdb.query(Estimate).filter_by(estimate_id=estimate_id, company_id=company_id).first()
    if not est:
        try:
            est = cdb.query(Estimate).filter_by(id=int(estimate_id), company_id=company_id).first()
        except Exception:
            pass
    if not est:
        flash("Quotation not found.", "error")
        return redirect(url_for("estimate_list"))

    so_no = _next_numbered_id(cdb, SalesOrder.order_no, "SO-", extra_filters=[SalesOrder.company_id == company_id])
    so = SalesOrder(
        order_no=so_no,
        company_id=company_id,
        client_id=est.client_id,
        client_name=est.client_name,
        order_date=today_ist().date(),
        delivery_date=est.valid_until,
        reference_no=f"Quote #{est.estimate_id}",
        status="Confirmed",
        subtotal=est.subtotal or 0.0,
        cgst_total=est.cgst_total or 0.0,
        sgst_total=est.sgst_total or 0.0,
        igst_total=est.igst_total or 0.0,
        tax_amount=est.tax_amount or 0.0,
        grand_total=est.grand_total or 0.0,
        terms=est.terms,
        notes=est.notes,
        created_by=session.get("user", {}).get("username") or session.get("user_id"),
    )
    cdb.add(so)
    cdb.flush()

    for item in est.items:
        so_item = SalesOrderItem(
            sales_order_id=so.id,
            stock_item_id=item.stock_item_id,
            item_code=item.item_code,
            item_name=item.item_name,
            description=item.description or item.item_name,
            hsn=item.hsn,
            quantity=item.qty,
            delivered_qty=0.0,
            unit=item.unit or "pcs",
            rate=item.rate,
            discount_percent=item.discount_percent,
            taxable_amount=item.taxable_amount,
            gst_percent=item.gst_percent,
            cgst_amount=item.cgst_amount,
            sgst_amount=item.sgst_amount,
            igst_amount=item.igst_amount,
            total_amount=item.total_amount,
        )
        cdb.add(so_item)

    est.status = "Converted"
    cdb.commit()
    log_audit_event(cdb, company_id, "sales_order", so.id, "create", f"Converted from Quotation {est.estimate_id}")
    flash(f"Quotation {est.estimate_id} converted to Sales Order {so.order_no} successfully!", "success")
    return redirect(url_for("sales_order_view", order_id=so.id))


@app.route("/estimate/convert_to_invoice/<estimate_id>", methods=["POST"])
@login_required
@require_permission("estimates", "create")
def estimate_convert_to_invoice(estimate_id):
    """Convert Quotation to Sales Tax Invoice"""
    cdb = get_cdb()
    company_id = get_current_company()
    est = cdb.query(Estimate).filter_by(estimate_id=estimate_id, company_id=company_id).first()
    if not est:
        try:
            est = cdb.query(Estimate).filter_by(id=int(estimate_id), company_id=company_id).first()
        except Exception:
            pass
    if not est:
        flash("Quotation not found.", "error")
        return redirect(url_for("estimate_list"))

    inv_no = _next_numbered_id(cdb, CustomerInvoice.invoice_number, "INV-", extra_filters=[CustomerInvoice.company_id == company_id])
    inv = CustomerInvoice(
        invoice_number=inv_no,
        company_id=company_id,
        client_id=est.client_id,
        client_name=est.client_name,
        billing_address=est.client_address,
        shipping_address=est.client_address,
        client_gstin=est.client_gstin,
        client_state=est.client_state,
        invoice_date=today_ist().date(),
        due_date=est.valid_until or today_ist().date(),
        invoice_type="credit",
        status="unpaid",
        payment_terms=est.payment_terms or "Net 30 Days",
        subtotal=est.subtotal or 0.0,
        cgst_total=est.cgst_total or 0.0,
        sgst_total=est.sgst_total or 0.0,
        igst_total=est.igst_total or 0.0,
        tax_amount=est.tax_amount or 0.0,
        grand_total=est.grand_total or 0.0,
        paid_amount=0.0,
        balance=est.grand_total or 0.0,
        terms=est.terms,
        notes=est.notes,
        created_by=session.get("user", {}).get("username") or session.get("user_id"),
    )
    cdb.add(inv)
    cdb.flush()

    for item in est.items:
        ci_item = CustomerInvoiceItem(
            customer_invoice_id=inv.id,
            stock_item_id=item.stock_item_id,
            item_code=item.item_code,
            item_name=item.item_name,
            item_description=item.description or item.item_name,
            hsn=item.hsn,
            quantity=item.qty,
            unit=item.unit or "pcs",
            rate=item.rate,
            discount_percent=item.discount_percent,
            taxable_amount=item.taxable_amount,
            gst_percent=item.gst_percent,
            cgst_amount=item.cgst_amount,
            sgst_amount=item.sgst_amount,
            igst_amount=item.igst_amount,
            total_amount=item.total_amount,
        )
        cdb.add(ci_item)

    est.status = "Converted"
    cdb.commit()
    log_audit_event(cdb, company_id, "customer_invoice", inv.id, "create", f"Converted from Quotation {est.estimate_id}")
    flash(f"Quotation {est.estimate_id} converted to Tax Invoice {inv.invoice_number} successfully!", "success")
    return redirect(url_for("customer_invoice_view", cust_inv_id=inv.id))


@app.route("/estimate/delete/<estimate_id>", methods=["POST"])
@login_required
@owner_required
def estimate_delete(estimate_id):
    """Delete / Void an estimate"""
    cdb = get_cdb()
    company_id = get_current_company()
    est = cdb.query(Estimate).filter_by(estimate_id=estimate_id, company_id=company_id).first()
    if not est:
        try:
            est = cdb.query(Estimate).filter_by(id=int(estimate_id), company_id=company_id).first()
        except Exception:
            pass
    if not est:
        flash("Quotation not found.", "error")
        return redirect(url_for("estimate_list"))

    cdb.query(EstimateItem).filter_by(estimate_id=est.id).delete()
    cdb.delete(est)
    cdb.commit()
    flash(f"Quotation {estimate_id} deleted successfully.", "success")
    return redirect(url_for("estimate_list"))



    

# ── Expenses ──────────────────────────────────────────────────────────────────
EXPENSE_CATEGORIES = [
    "Rent", "Electricity", "Internet", "Salaries", "Fuel",
    "Office Supplies", "Maintenance", "Travel", "Food & Refreshments",
    "Marketing", "Courier Charges", "Bank Charges", "Misc", "Others",
]

@app.route("/expenses")
@login_required
@require_permission("expenses", "view")
def expenses():
    company_id = get_current_company()
    if not company_id:
        return redirect(url_for('login'))
    cdb = get_customer_session(company_id)

    from_date = request.args.get("from_date", today_ist().replace(day=1).isoformat())
    to_date   = request.args.get("to_date",   today_ist().isoformat())

    try:
        fd = date.fromisoformat(from_date)
        td = date.fromisoformat(to_date)
    except ValueError:
        fd = today_ist().replace(day=1)
        td = today_ist()

    rows = (
        cdb.query(Expense)
        .filter(
            Expense.company_id == company_id,
            Expense.date >= fd,
            Expense.date <= td,
        )
        .order_by(Expense.date.desc(), Expense.id.desc())
        .all()
    )

    total = sum(e.amount for e in rows)

    # Category breakdown for chart
    cat_totals = {}
    for e in rows:
        cat_totals[e.category] = cat_totals.get(e.category, 0) + e.amount

    return render_template(
        "expenses.html",
        expenses=rows,
        total=total,
        cat_totals=cat_totals,
        categories=EXPENSE_CATEGORIES,
        from_date=from_date,
        to_date=to_date,
        today_str=today_ist().isoformat(),
        active="expenses",
    )


@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
@require_permission("expenses", "view", method_actions={'POST': 'create'})
def add_expense():
    company_id = get_current_company()
    if not company_id:
        return redirect(url_for('login'))
    cdb = get_customer_session(company_id)
    user = get_current_user()

    if request.method == "POST":
        try:
            expense_date = date.fromisoformat(request.form.get("date", today_ist().isoformat()))
            category = request.form.get("category", "Misc")
            description = request.form.get("description", "").strip()
            amount = float(request.form.get("amount", 0))
            payment_mode = request.form.get("payment_mode", "Cash")
            reference = request.form.get("reference", "").strip()
            
            if amount <= 0:
                flash("Amount must be greater than 0.", "error")
                return redirect(url_for("expenses"))

            # ── 1. CREATE EXPENSE RECORD ──
            exp = Expense(
                company_id=company_id,
                date=expense_date,
                category=category,
                description=description,
                amount=amount,
                payment_mode=payment_mode,
                reference=reference,
                created_by=user.get("full_name", user.get("email")),
            )
            cdb.add(exp)
            cdb.flush()  # Get expense ID
            accounting_txn = None

            # ── 2. DEDUCT FROM CASH IN HAND OR BANK ACCOUNT ──
            if payment_mode.lower() == "cash":
                # Deduct from Cash in Hand
                cash_txn = CashTransaction(
                    company_id=company_id,
                    type="expense",
                    date=expense_date,
                    category=category,
                    description=f"Expense: {description}",
                    amount=amount,
                    reference=reference or f"EXP-{exp.id}",
                    notes=f"Expense recorded - {category}",
                    party_name="Expense",
                    created_by=user.get("full_name", user.get("email"))
                )
                cdb.add(cash_txn)
                accounting_txn = cash_txn
                
            elif payment_mode.lower() in ["bank transfer", "online", "upi", "cheque"]:
                # Deduct from Bank Account
                if not reference:
                    flash("Reference/Transaction ID is required for bank payments.", "error")
                    cdb.rollback()
                    return redirect(url_for("expenses"))
                
                # Find a bank account to deduct from
                # Try to find the specific bank account from reference
                bank_account = None
                
                # First, try to find a bank account matching the reference or bank name
                if reference:
                    # Look for bank account by reference or bank name
                    bank_accounts = cdb.query(BankAccount).filter_by(company_id=company_id, status='Active').all()
                    for acc in bank_accounts:
                        if reference.lower() in acc.account_number.lower() or reference.lower() in acc.bank_name.lower():
                            bank_account = acc
                            break
                
                # If no specific bank found, use the first active bank account
                if not bank_account:
                    bank_account = cdb.query(BankAccount).filter_by(company_id=company_id, status='Active').first()
                    if not bank_account:
                        flash("No active bank account found. Please add a bank account first.", "error")
                        cdb.rollback()
                        return redirect(url_for("expenses"))
                
                # Check if sufficient balance
                if bank_account.balance < amount:
                    flash(f"Insufficient balance in {bank_account.bank_name} - {bank_account.account_name}. Available: {company_currency_symbol()} {bank_account.balance:,.2f}", "error")
                    cdb.rollback()
                    return redirect(url_for("expenses"))
                
                # Deduct from bank account
                bank_txn = BankTransaction(
                    bank_account_id=bank_account.id,
                    company_id=company_id,
                    type="debit",
                    date=expense_date,
                    description=f"Expense: {description}",
                    amount=amount,
                    reference=reference or f"EXP-{exp.id}",
                    transaction_mode=payment_mode.title(),
                    notes=f"Expense recorded - {category}",
                    party_name="Expense",
                    created_by=user.get("full_name", user.get("email"))
                )
                cdb.add(bank_txn)
                accounting_txn = bank_txn
                bank_account.balance -= amount
                bank_account.updated_at = datetime.utcnow()
                
            else:
                # Unknown payment mode - treat as cash
                cash_txn = CashTransaction(
                    company_id=company_id,
                    type="expense",
                    date=expense_date,
                    category=category,
                    description=f"Expense: {description}",
                    amount=amount,
                    reference=reference or f"EXP-{exp.id}",
                    notes=f"Expense recorded - {category} (via {payment_mode})",
                    party_name="Expense",
                    created_by=user.get("full_name", user.get("email"))
                )
                cdb.add(cash_txn)
                accounting_txn = cash_txn

            cdb.flush()
            _auto_post_expense(cdb, company_id, exp, accounting_txn)
            cdb.commit()
            flash(f"✅ Expense of {company_currency_symbol()} {amount:,.2f} recorded successfully and deducted from {'Cash' if payment_mode.lower() == 'cash' else bank_account.bank_name if bank_account else 'Bank'}.", "success")

        except Exception as e:
            cdb.rollback()
            flash(f"Error recording expense: {str(e)}", "error")
            print(f"[expense-error] {e}")
            import traceback
            traceback.print_exc()

        return redirect(url_for("expenses"))

    return redirect(url_for("expenses"))


def _reverse_expense_ledger_effect(cdb, company_id, exp, user):
    """Undo the cash/bank deduction an expense caused, without deleting the
    expense row itself. Mirrors delete_expense's reversal logic so edit can
    reuse it before re-applying the (possibly changed) amount/payment mode."""
    payment_mode = exp.payment_mode.lower() if exp.payment_mode else "cash"
    amount = exp.amount
    expense_date = exp.date

    if payment_mode == "cash":
        cash_txn = CashTransaction(
            company_id=company_id,
            type="income",
            date=expense_date,
            category="Expense Reversal",
            description=f"Reversal (edit): {exp.description}",
            amount=amount,
            reference=f"REV-EDIT-EXP-{exp.id}",
            notes=f"Expense edited - {exp.category}",
            party_name="Expense",
            created_by=user.get("full_name", user.get("email"))
        )
        cdb.add(cash_txn)

    elif payment_mode in ["bank transfer", "online", "upi", "cheque", "card"]:
        bank_txn = cdb.query(BankTransaction).filter(
            BankTransaction.company_id == company_id,
            BankTransaction.type == "debit",
            BankTransaction.reference == str(exp.id)
        ).first()

        if not bank_txn:
            bank_txn = cdb.query(BankTransaction).filter(
                BankTransaction.company_id == company_id,
                BankTransaction.type == "debit",
                BankTransaction.description.like(f"%{exp.description}%"),
                BankTransaction.amount == amount
            ).first()

        if bank_txn and bank_txn.bank_account:
            reverse_txn = BankTransaction(
                bank_account_id=bank_txn.bank_account_id,
                company_id=company_id,
                type="credit",
                date=expense_date,
                description=f"Reversal (edit): {exp.description}",
                amount=amount,
                reference=f"REV-EDIT-EXP-{exp.id}",
                transaction_mode=payment_mode.title(),
                notes=f"Expense edited - {exp.category}",
                party_name="Expense",
                created_by=user.get("full_name", user.get("email"))
            )
            cdb.add(reverse_txn)
            bank_txn.bank_account.balance += amount
            bank_txn.bank_account.updated_at = datetime.utcnow()
        else:
            # No bank txn found - reverse as cash fallback (same as delete_expense)
            cash_txn = CashTransaction(
                company_id=company_id,
                type="income",
                date=expense_date,
                category="Expense Reversal",
                description=f"Reversal (edit, fallback): {exp.description}",
                amount=amount,
                reference=f"REV-EDIT-EXP-{exp.id}",
                notes=f"Expense edited - no bank txn found",
                party_name="Expense",
                created_by=user.get("full_name", user.get("email"))
            )
            cdb.add(cash_txn)
    else:
        cash_txn = CashTransaction(
            company_id=company_id,
            type="income",
            date=expense_date,
            category="Expense Reversal",
            description=f"Reversal (edit): {exp.description}",
            amount=amount,
            reference=f"REV-EDIT-EXP-{exp.id}",
            notes=f"Expense edited - {exp.category} (via {exp.payment_mode})",
            party_name="Expense",
            created_by=user.get("full_name", user.get("email"))
        )
        cdb.add(cash_txn)


@app.route("/expenses/edit/<int:expense_id>", methods=["POST"])
@login_required
@require_permission("expenses", "view", method_actions={'POST': 'edit'})
def edit_expense(expense_id):
    company_id = get_current_company()
    if not company_id:
        return redirect(url_for('login'))
    cdb = get_customer_session(company_id)
    user = get_current_user()

    exp = cdb.query(Expense).filter_by(id=expense_id, company_id=company_id).first()
    if not exp:
        flash("Expense not found.", "error")
        return redirect(url_for("expenses"))

    try:
        new_date = date.fromisoformat(request.form.get("date", exp.date.isoformat()))
        new_category = request.form.get("category", exp.category)
        new_description = request.form.get("description", "").strip()
        new_amount = float(request.form.get("amount", 0))
        new_payment_mode = request.form.get("payment_mode", exp.payment_mode)
        new_reference = request.form.get("reference", "").strip()

        if new_amount <= 0:
            flash("Amount must be greater than 0.", "error")
            return redirect(url_for("expenses"))

        _reverse_source_journal(cdb, company_id, "expense", exp.id, "Expense edited")

        # ── 1. UNDO the old cash/bank effect ──
        _reverse_expense_ledger_effect(cdb, company_id, exp, user)

        # ── 2. UPDATE the expense record ──
        exp.date = new_date
        exp.category = new_category
        exp.description = new_description
        exp.amount = new_amount
        exp.payment_mode = new_payment_mode
        exp.reference = new_reference

        # ── 3. RE-APPLY deduction with the new values ──
        accounting_txn = None
        if new_payment_mode.lower() == "cash":
            cash_txn = CashTransaction(
                company_id=company_id,
                type="expense",
                date=new_date,
                category=new_category,
                description=f"Expense: {new_description}",
                amount=new_amount,
                reference=new_reference or f"EXP-{exp.id}",
                notes=f"Expense recorded - {new_category} (edited)",
                party_name="Expense",
                created_by=user.get("full_name", user.get("email"))
            )
            cdb.add(cash_txn)
            accounting_txn = cash_txn

        elif new_payment_mode.lower() in ["bank transfer", "online", "upi", "cheque"]:
            if not new_reference:
                flash("Reference/Transaction ID is required for bank payments.", "error")
                cdb.rollback()
                return redirect(url_for("expenses"))

            bank_account = None
            bank_accounts = cdb.query(BankAccount).filter_by(company_id=company_id, status='Active').all()
            for acc in bank_accounts:
                if new_reference.lower() in acc.account_number.lower() or new_reference.lower() in acc.bank_name.lower():
                    bank_account = acc
                    break
            if not bank_account:
                bank_account = cdb.query(BankAccount).filter_by(company_id=company_id, status='Active').first()
                if not bank_account:
                    flash("No active bank account found. Please add a bank account first.", "error")
                    cdb.rollback()
                    return redirect(url_for("expenses"))

            if bank_account.balance < new_amount:
                flash(f"Insufficient balance in {bank_account.bank_name} - {bank_account.account_name}. Available: {company_currency_symbol()} {bank_account.balance:,.2f}", "error")
                cdb.rollback()
                return redirect(url_for("expenses"))

            bank_txn = BankTransaction(
                bank_account_id=bank_account.id,
                company_id=company_id,
                type="debit",
                date=new_date,
                description=f"Expense: {new_description}",
                amount=new_amount,
                reference=new_reference or f"EXP-{exp.id}",
                transaction_mode=new_payment_mode.title(),
                notes=f"Expense recorded - {new_category} (edited)",
                party_name="Expense",
                created_by=user.get("full_name", user.get("email"))
            )
            cdb.add(bank_txn)
            accounting_txn = bank_txn
            bank_account.balance -= new_amount
            bank_account.updated_at = datetime.utcnow()

        else:
            cash_txn = CashTransaction(
                company_id=company_id,
                type="expense",
                date=new_date,
                category=new_category,
                description=f"Expense: {new_description}",
                amount=new_amount,
                reference=new_reference or f"EXP-{exp.id}",
                notes=f"Expense recorded - {new_category} (via {new_payment_mode}, edited)",
                party_name="Expense",
                created_by=user.get("full_name", user.get("email"))
            )
            cdb.add(cash_txn)
            accounting_txn = cash_txn

        cdb.flush()
        _auto_post_expense(cdb, company_id, exp, accounting_txn)
        cdb.commit()
        flash(f"✅ Expense updated successfully.", "success")

    except Exception as e:
        cdb.rollback()
        flash(f"Error updating expense: {str(e)}", "error")
        print(f"[expense-edit-error] {e}")
        import traceback
        traceback.print_exc()

    return redirect(url_for("expenses"))


@app.route("/expenses/delete/<int:expense_id>", methods=["POST"])
@login_required
@owner_required
@require_admin_password
def delete_expense(expense_id):
    company_id = get_current_company()
    if not company_id:
        return redirect(url_for('login'))
    cdb = get_customer_session(company_id)
    
    exp = cdb.query(Expense).filter_by(id=expense_id, company_id=company_id).first()
    if not exp:
        flash("Expense not found.", "error")
        return redirect(url_for("expenses"))
    
    try:
        payment_mode = exp.payment_mode.lower() if exp.payment_mode else "cash"
        amount = exp.amount
        expense_date = exp.date
        
        # ── REVERSE THE DEDUCTION ──
        if payment_mode == "cash":
            # Reverse cash deduction - add back to Cash in Hand
            cash_txn = CashTransaction(
                company_id=company_id,
                type="income",  # Reverse: add back
                date=expense_date,
                category="Expense Reversal",
                description=f"Reversal: {exp.description}",
                amount=amount,
                reference=f"REV-EXP-{exp.id}",
                notes=f"Expense deletion reversal - {exp.category}",
                party_name="Expense",
                created_by=get_current_user().get('email')
            )
            cdb.add(cash_txn)
            
        elif payment_mode in ["bank transfer", "online", "upi", "cheque"]:
            # Reverse bank deduction - find the associated transaction
            bank_txn = cdb.query(BankTransaction).filter(
                BankTransaction.company_id == company_id,
                BankTransaction.type == "debit",
                BankTransaction.reference == str(exp.id)
            ).first()
            
            if bank_txn and bank_txn.bank_account:
                # Reverse the bank transaction
                reverse_txn = BankTransaction(
                    bank_account_id=bank_txn.bank_account_id,
                    company_id=company_id,
                    type="credit",  # Reverse: add back
                    date=expense_date,
                    description=f"Reversal: {exp.description}",
                    amount=amount,
                    reference=f"REV-EXP-{exp.id}",
                    transaction_mode=payment_mode.title(),
                    notes=f"Expense deletion reversal - {exp.category}",
                    party_name="Expense",
                    created_by=get_current_user().get('email')
                )
                cdb.add(reverse_txn)
                bank_txn.bank_account.balance += amount
                bank_txn.bank_account.updated_at = datetime.utcnow()
            else:
                # Fallback: try to find by description
                bank_txn = cdb.query(BankTransaction).filter(
                    BankTransaction.company_id == company_id,
                    BankTransaction.type == "debit",
                    BankTransaction.description.like(f"%{exp.description}%"),
                    BankTransaction.amount == amount
                ).first()
                if bank_txn and bank_txn.bank_account:
                    reverse_txn = BankTransaction(
                        bank_account_id=bank_txn.bank_account_id,
                        company_id=company_id,
                        type="credit",
                        date=expense_date,
                        description=f"Reversal: {exp.description}",
                        amount=amount,
                        reference=f"REV-EXP-{exp.id}",
                        transaction_mode=payment_mode.title(),
                        notes=f"Expense deletion reversal - {exp.category}",
                        party_name="Expense",
                        created_by=get_current_user().get('email')
                    )
                    cdb.add(reverse_txn)
                    bank_txn.bank_account.balance += amount
                    bank_txn.bank_account.updated_at = datetime.utcnow()
                else:
                    # No bank transaction found - add as cash reversal as fallback
                    cash_txn = CashTransaction(
                        company_id=company_id,
                        type="income",
                        date=expense_date,
                        category="Expense Reversal",
                        description=f"Reversal (fallback): {exp.description}",
                        amount=amount,
                        reference=f"REV-EXP-{exp.id}",
                        notes=f"Expense deletion reversal - no bank txn found",
                        party_name="Expense",
                        created_by=get_current_user().get('email')
                    )
                    cdb.add(cash_txn)

        # Delete the expense
        _reverse_source_journal(cdb, company_id, "expense", exp.id, "Expense deleted")
        cdb.delete(exp)
        cdb.commit()
        
        flash(f"✅ Expense deleted and cash/bank restored.", "success")
        
    except Exception as e:
        cdb.rollback()
        flash(f"Error deleting expense: {str(e)}", "error")
        print(f"[expense-delete-error] {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for("expenses"))


@app.route("/api/expenses-summary")
@login_required
@require_permission("expenses", "view")
def api_expenses_summary():
    company_id = get_current_company()
    if not company_id:
        return redirect(url_for('login'))
    cdb = get_customer_session(company_id)

    from_date = request.args.get("from_date", today_ist().replace(day=1).isoformat())
    to_date   = request.args.get("to_date",   today_ist().isoformat())

    try:
        fd = date.fromisoformat(from_date)
        td = date.fromisoformat(to_date)
    except ValueError:
        fd = today_ist().replace(day=1)
        td = today_ist()

    rows = cdb.query(Expense).filter(
        Expense.company_id == company_id,
        Expense.date >= fd,
        Expense.date <= td,
    ).all()

    cat_totals = {}
    for e in rows:
        cat_totals[e.category] = cat_totals.get(e.category, 0) + e.amount

    return jsonify({
        "total": sum(e.amount for e in rows),
        "count": len(rows),
        "by_category": cat_totals,
    })


# ─────────────────────────────────────────────────────────────────────────────
# ── Super Admin ───────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/migrations")
@login_required
@super_admin_required
def migrations():
    """Migration panel — list all past migrations across all company DBs."""
    from platform_models import Company
    from db_router import _engine_cache, _get_or_create

    companies = Company.query.filter_by(is_active=True).all()
    history   = []   # list of dicts for the template

    for company in companies:
        try:
            engine = _engine_cache.get(company.company_id)
            if engine is None:
                _get_or_create(company.company_id)
                engine = _engine_cache[company.company_id]

            _ensure_migration_table(engine)

            with engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT label, status, error_msg, applied_at, applied_by FROM schema_migrations ORDER BY applied_at DESC LIMIT 50")
                ).fetchall()

            for row in rows:
                history.append({
                    "company_id":   company.company_id,
                    "company_name": company.company_name,
                    "label":        row[0],
                    "status":       row[1],
                    "error_msg":    row[2],
                    "applied_at":   row[3],
                    "applied_by":   row[4],
                })
        except Exception as e:
            history.append({
                "company_id":   company.company_id,
                "company_name": company.company_name,
                "label":        "— could not read history —",
                "status":       "error",
                "error_msg":    str(e),
                "applied_at":   None,
                "applied_by":   None,
            })

    # Sort all history by applied_at desc
    history.sort(key=lambda x: x["applied_at"] or datetime.min, reverse=True)

    return render_template(
        "migrations.html",
        active="migrations",
        companies=companies,
        history=history,
    )


    return jsonify({"results": results, "summary": summary})

@app.route("/migrations/run", methods=["POST"])
@login_required
@super_admin_required
def run_migration():
    """
    Execute SQL on customer databases only.
    Platform database changes must be done manually.
    """
    from platform_models import Company
    from db_router import _engine_cache, _get_or_create

    data = request.get_json()
    label = (data.get("label") or "").strip()
    sql = (data.get("sql") or "").strip()
    target = data.get("target", "all")
    dry_run = data.get("dry_run", False)
    user_email = get_current_user().get("email", "unknown")

    if not label:
        return jsonify({"error": "Migration label is required"}), 400
    if not sql:
        return jsonify({"error": "SQL is required"}), 400

    # Determine which companies to target
    if target == "all":
        companies = Company.query.filter_by(is_active=True).all()
    else:
        companies = Company.query.filter_by(company_id=target, is_active=True).all()

    results = []

    for company in companies:
        company_id = company.company_id
        result = {
            "company_id": company_id,
            "company_name": company.company_name,
            "status": None,
            "message": "",
            "skipped": False,
        }

        try:
            engine = _engine_cache.get(company_id)
            if engine is None:
                _get_or_create(company_id)
                engine = _engine_cache[company_id]

            _ensure_migration_table(engine)

            # Skip if already applied successfully
            if _already_applied(engine, label):
                result["status"] = "skipped"
                result["message"] = "Already applied — skipped"
                result["skipped"] = True
                results.append(result)
                continue

            if dry_run:
                result["status"] = "dry_run"
                result["message"] = "Dry run — SQL not executed"
                results.append(result)
                continue

            # Run the SQL
            with engine.connect() as conn:
                statements = [s.strip() for s in sql.split(";") if s.strip()]
                for stmt in statements:
                    conn.execute(text(stmt))
                conn.commit()

            _log_migration(engine, label, sql, "success", None, user_email)
            result["status"] = "success"
            result["message"] = "Applied successfully"

        except Exception as e:
            err = str(e)
            try:
                _log_migration(engine, label, sql, "failed", err, user_email)
            except Exception:
                pass
            result["status"] = "failed"
            result["message"] = err

        results.append(result)

    summary = {
        "total": len(results),
        "success": sum(1 for r in results if r["status"] == "success"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "dry_run": sum(1 for r in results if r["status"] == "dry_run"),
    }

    return jsonify({"results": results, "summary": summary})


def _ensure_migration_table(engine):
    """Create migration history table in customer database if it doesn't exist"""
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                label VARCHAR(200) NOT NULL,
                sql_executed TEXT,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                error_msg TEXT,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                applied_by VARCHAR(100)
            )
        """))
        conn.commit()


def _already_applied(engine, label):
    """Check if migration already applied to this customer DB"""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM schema_migrations WHERE label = :label AND status = 'success'"),
            {"label": label}
        ).scalar()
        return result > 0


def _log_migration(engine, label, sql, status, error_msg, applied_by):
    """Log migration to customer database history table"""
    with engine.connect() as conn:
        conn.execute(
            text("""
                INSERT INTO schema_migrations (label, sql_executed, status, error_msg, applied_by)
                VALUES (:label, :sql, :status, :error_msg, :applied_by)
            """),
            {
                "label": label,
                "sql": sql,
                "status": status,
                "error_msg": error_msg,
                "applied_by": applied_by
            }
        )
        conn.commit()

@app.route("/migrations/history")
@login_required
@super_admin_required
def migration_history_all():
    """
    Return combined migration history across ALL active companies as JSON.
    Called by the super_admin page when the Migrations tab is opened.
    """
    from platform_models import Company
    from db_router import _engine_cache, _get_or_create

    companies = Company.query.filter_by(is_active=True).all()
    all_rows  = []

    for company in companies:
        company_id = company.company_id
        try:
            engine = _engine_cache.get(company_id)
            if engine is None:
                _get_or_create(company_id)
                engine = _engine_cache[company_id]

            _ensure_migration_table(engine)

            with engine.connect() as conn:
                rows = conn.execute(
                    text("SELECT label, sql_executed, status, error_msg, applied_at, applied_by FROM schema_migrations ORDER BY applied_at DESC LIMIT 100")
                ).fetchall()

            for r in rows:
                all_rows.append({
                    "company_id":   company_id,
                    "company_name": company.company_name,
                    "label":        r[0],
                    "sql":          r[1],
                    "status":       r[2],
                    "error_msg":    r[3],
                    "applied_at":   r[4].strftime("%d %b %Y %H:%M") if r[4] else "",
                    "applied_by":   r[5],
                    "_sort_key":    r[4].isoformat() if r[4] else "",
                })
        except Exception as e:
            pass  # Skip companies whose DB is unreachable

    # Sort newest first
    all_rows.sort(key=lambda x: x["_sort_key"], reverse=True)
    for row in all_rows:
        del row["_sort_key"]

    return jsonify({"history": all_rows})


@app.route("/migrations/history/<company_id>")
@login_required
@super_admin_required
def migration_history(company_id):
    """Return migration history for one specific company as JSON."""
    from db_router import _engine_cache, _get_or_create

    engine = _engine_cache.get(company_id)
    if engine is None:
        _get_or_create(company_id)
        engine = _engine_cache[company_id]

    _ensure_migration_table(engine)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT label, sql_executed, status, error_msg, applied_at, applied_by FROM schema_migrations ORDER BY applied_at DESC")
        ).fetchall()

    history = [
        {
            "label":      r[0],
            "sql":        r[1],
            "status":     r[2],
            "error_msg":  r[3],
            "applied_at": r[4].strftime("%Y-%m-%d %H:%M:%S") if r[4] else "",
            "applied_by": r[5],
        }
        for r in rows
    ]

    return jsonify({"history": history})

@app.route("/admin/dashboard")
@login_required
@super_admin_required
def admin_dashboard():
    stats = {
        "total_companies":  Company.query.count(),
        "total_users":      0,  # Will calculate differently
        "active_companies": Company.query.filter_by(is_active=True).count(),
        "monthly_revenue":  0,
    }
    
    # Calculate total users across all companies
    companies = Company.query.all()
    for company in companies:
        try:
            cdb = get_customer_session(company.company_id, db_session=db.session)
            user_count = cdb.query(CompanyUser).count()
            stats["total_users"] += user_count
            from db_router import close_customer_session
            close_customer_session(company.company_id)
        except Exception:
            pass
    
    plan_distribution = {}
    for c in companies:
        plan_distribution[c.subscription_plan] = plan_distribution.get(c.subscription_plan, 0) + 1

    # Clients registered by super admin who haven't created their company yet
    all_owners = RegisteredUser.query.filter_by(role="owner").all()
    pending_clients = [u for u in all_owners if not u.has_company]

    stats["pending_setup"] = len(pending_clients)
    stats["total_clients"] = len(all_owners)

    # Users tab: every registered user + how many companies they own
    all_users = RegisteredUser.query.order_by(RegisteredUser.created_at.desc()).all()
    users_data = []
    for u in all_users:
        user_companies = [c for c in companies if c.owner_email == u.email]
        users_data.append({
            'user': u,
            'company_count': len(user_companies),
            'companies': user_companies
        })

    return render_template("super_admin.html",
                           stats=stats,
                           companies=companies,
                           pending_clients=pending_clients,
                           users_data=users_data,
                           total_users=len(all_users),
                           plans=get_all_plans(),
                           plan_distribution=plan_distribution,
                           today=today_ist())


@app.route("/admin/companies")
@login_required
@super_admin_required
def admin_companies():
    return render_template("admin_companies.html", companies=Company.query.all())


@app.route("/admin/company/<company_id>")
@login_required
@super_admin_required
def admin_company_detail(company_id):
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/company/<company_id>/update-plan", methods=["POST"])
@login_required
@super_admin_required
def admin_update_company_plan(company_id):
    plan_id = request.form.get("plan")
    yearly_amt = request.form.get("custom_yearly_amount") or request.form.get("yearly_amount")
    company = get_company_by_id(company_id)
    plan    = SubscriptionPlan.query.get(plan_id)
    
    if not company:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"error": "Company not found"}), 404
        flash("Company not found", "error")
        return redirect(url_for("admin_dashboard"))

    if plan:
        company.subscription_plan     = plan.id
        company.max_companies_allowed = plan.max_companies
        company.max_users_per_company = plan.max_users
        
        if yearly_amt is not None and str(yearly_amt).strip():
            try:
                company.custom_yearly_amount = float(str(yearly_amt).strip())
            except ValueError:
                pass
        
        # Sync to owner
        owner = RegisteredUser.query.filter_by(email=company.owner_email).first()
        if owner:
            owner.subscription_plan = plan.id
            if company.custom_yearly_amount is not None:
                owner.custom_yearly_amount = company.custom_yearly_amount
                
        db.session.commit()
        
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"success": True, "message": f"Company plan updated to {plan.name}"})
        flash(f"Company plan updated to {plan.name}", "success")
        
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/company/<company_id>/renew", methods=["POST"])
@login_required
@super_admin_required
def admin_renew_company(company_id):
    company = get_company_by_id(company_id)
    if not company:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"error": "Company not found"}), 404
        flash("Company not found", "error")
        return redirect(url_for("admin_dashboard"))

    # Renew from today, or from the current expiry if it's still in the future
    start_from = company.subscription_end if (company.subscription_end and company.subscription_end > today_ist()) else today_ist()
    company.subscription_start = company.subscription_start or today_ist()
    company.subscription_end = start_from + timedelta(days=365)
    company.is_active = True
    db.session.commit()
    
    if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
        return jsonify({"success": True, "message": f"{company.company_name} renewed until {company.subscription_end.strftime('%d %b %Y')}"})
        
    flash(f"{company.company_name} renewed until {company.subscription_end.strftime('%d %b %Y')}", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/company/<company_id>/toggle-status", methods=["POST"])
@login_required
@super_admin_required
def admin_toggle_company_status(company_id):
    company = get_company_by_id(company_id)
    if company:
        company.is_active = not company.is_active
        db.session.commit()
        status = "activated" if company.is_active else "suspended"
        if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json:
            return jsonify({"success": True, "is_active": company.is_active, "status": status})
        flash(f"Company {status}", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/company/<company_id>/edit", methods=["POST"])
@login_required
@super_admin_required
def admin_edit_company(company_id):
    company = get_company_by_id(company_id)
    if not company:
        return jsonify({"error": "Company not found"}), 404
    
    try:
        new_name = request.form.get("company_name", company.company_name).strip()
        new_gst = request.form.get("gst_number", "").strip().upper()
        if not new_gst:
            new_gst = None
        
        # Check if another active company has this name (same owner)
        if new_name != company.company_name:
            existing = Company.query.filter(
                func.lower(Company.company_name) == func.lower(new_name),
                Company.owner_email == company.owner_email,
                Company.is_active == True,
                Company.company_id != company_id
            ).first()
            if existing:
                return jsonify({"error": f"Company name '{new_name}' is already taken by another active company."}), 400
        
        # ── Check if another active company has this GST number ──
        if new_gst and new_gst != company.gst_number:
            existing_gst = Company.query.filter(
                func.lower(Company.gst_number) == func.lower(new_gst),
                Company.is_active == True,
                Company.company_id != company_id
            ).first()
            if existing_gst:
                return jsonify({"error": f"GST number '{new_gst}' is already registered to another active company."}), 400
        
        company.company_name = new_name
        company.phone = request.form.get("phone", company.phone)
        company.address = request.form.get("address", company.address)
        company.gst_number = new_gst

        # ── Subscription Plan & Duration ──
        if "subscription_plan" in request.form:
            sub_plan = request.form.get("subscription_plan", "").strip().lower()
            if sub_plan:
                company.subscription_plan = sub_plan

        if "plan_duration" in request.form:
            plan_dur = request.form.get("plan_duration", "").strip().lower()
            if plan_dur:
                company.plan_duration = plan_dur

        # ── Custom Yearly Amount (e.g. ₹2,500/year) ──
        if "custom_yearly_amount" in request.form:
            yearly_amt_str = request.form.get("custom_yearly_amount", "").strip()
            if yearly_amt_str:
                try:
                    company.custom_yearly_amount = float(yearly_amt_str)
                except ValueError:
                    return jsonify({"error": "Invalid custom yearly amount. Must be a numeric value."}), 400
            else:
                company.custom_yearly_amount = None

        # ── Subscription Dates & Maintenance Due Date ──
        if "subscription_start" in request.form:
            start_str = request.form.get("subscription_start", "").strip()
            if start_str:
                try:
                    company.subscription_start = datetime.strptime(start_str, "%Y-%m-%d").date()
                except ValueError:
                    pass

        if "subscription_end" in request.form:
            end_str = request.form.get("subscription_end", "").strip()
            if end_str:
                try:
                    company.subscription_end = datetime.strptime(end_str, "%Y-%m-%d").date()
                except ValueError:
                    pass
            elif not end_str and request.form.get("subscription_plan") == "unlimited":
                company.subscription_end = None

        if "maintenance_due_date" in request.form:
            maint_str = request.form.get("maintenance_due_date", "").strip()
            if maint_str:
                try:
                    company.maintenance_due_date = datetime.strptime(maint_str, "%Y-%m-%d").date()
                except ValueError:
                    pass
            else:
                company.maintenance_due_date = None

        # ── Limits: Max Users & Max Companies ──
        if "max_users_per_company" in request.form:
            max_users = request.form.get("max_users_per_company", "").strip()
            if max_users:
                company.max_users_per_company = max_users

        if "max_companies_allowed" in request.form:
            max_companies = request.form.get("max_companies_allowed", "").strip()
            if max_companies:
                company.max_companies_allowed = max_companies

        # ── Active Status ──
        if "is_active" in request.form:
            is_act_val = request.form.get("is_active", "").strip().lower()
            company.is_active = is_act_val in ("1", "true", "yes", "active")

        # ── Sync to Owner User (RegisteredUser) ──
        owner = RegisteredUser.query.filter_by(email=company.owner_email).first()
        if owner:
            if "subscription_plan" in request.form and request.form.get("subscription_plan", "").strip():
                owner.subscription_plan = company.subscription_plan
            if "plan_duration" in request.form and request.form.get("plan_duration", "").strip():
                owner.plan_duration = company.plan_duration
            if "custom_yearly_amount" in request.form:
                owner.custom_yearly_amount = company.custom_yearly_amount
            if company.maintenance_due_date:
                owner.maintenance_due_date = company.maintenance_due_date

            payment_status = request.form.get("payment_status", "").strip().lower()
            if payment_status:
                owner.payment_status = payment_status

            amount_paid_str = request.form.get("amount_paid", "").strip()
            if amount_paid_str:
                try:
                    owner.amount_paid = float(amount_paid_str)
                except ValueError:
                    pass

            amount_total_str = request.form.get("amount_total", "").strip()
            if amount_total_str:
                try:
                    owner.amount_total = float(amount_total_str)
                except ValueError:
                    pass

            if company.max_users_per_company and company.max_users_per_company.isdigit():
                owner.custom_max_users = int(company.max_users_per_company)
            if company.max_companies_allowed and company.max_companies_allowed.isdigit():
                owner.custom_max_companies = int(company.max_companies_allowed)

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    
@app.route("/admin/user/<user_id>/edit", methods=["POST"])
@login_required
@super_admin_required
def admin_edit_user(user_id):
    user = RegisteredUser.query.filter_by(user_id=user_id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    try:
        # Profile fields
        if "full_name" in request.form:
            user.full_name = request.form.get("full_name", user.full_name).strip()
        if "phone" in request.form:
            user.phone = request.form.get("phone", user.phone).strip()
        if "address" in request.form:
            user.address = request.form.get("address", user.address).strip()

        # Subscription Plan & Duration
        if "subscription_plan" in request.form:
            sub_plan = request.form.get("subscription_plan", "").strip().lower()
            if sub_plan:
                user.subscription_plan = sub_plan

        if "plan_duration" in request.form:
            plan_dur = request.form.get("plan_duration", "").strip().lower()
            if plan_dur:
                user.plan_duration = plan_dur

        # Custom Yearly Renewal Amount
        if "custom_yearly_amount" in request.form:
            yearly_amt_str = request.form.get("custom_yearly_amount", "").strip()
            if yearly_amt_str:
                try:
                    user.custom_yearly_amount = float(yearly_amt_str)
                except ValueError:
                    return jsonify({"error": "Invalid custom yearly amount. Must be a numeric value."}), 400
            else:
                user.custom_yearly_amount = None

        # Maintenance Due Date
        if "maintenance_due_date" in request.form:
            maint_str = request.form.get("maintenance_due_date", "").strip()
            if maint_str:
                try:
                    user.maintenance_due_date = datetime.strptime(maint_str, "%Y-%m-%d").date()
                except ValueError:
                    pass
            else:
                user.maintenance_due_date = None

        # Max Companies & Max Users
        if "max_companies_allowed" in request.form:
            max_companies = request.form.get("max_companies_allowed", "").strip()
            if max_companies and max_companies.isdigit():
                user.custom_max_companies = int(max_companies)
            elif not max_companies:
                user.custom_max_companies = None

        if "max_users_per_company" in request.form:
            max_users = request.form.get("max_users_per_company", "").strip()
            if max_users and max_users.isdigit():
                user.custom_max_users = int(max_users)
            elif not max_users:
                user.custom_max_users = None

        # Account Status
        if "is_active" in request.form:
            is_act_val = request.form.get("is_active", "").strip().lower()
            user.is_active = is_act_val in ("1", "true", "yes", "active")

        # Payment Status & Amounts
        if "payment_status" in request.form:
            pay_status = request.form.get("payment_status", "").strip().lower()
            if pay_status:
                user.payment_status = pay_status

        if "amount_paid" in request.form:
            amt_paid_str = request.form.get("amount_paid", "").strip()
            if amt_paid_str:
                try:
                    user.amount_paid = float(amt_paid_str)
                except ValueError:
                    pass

        if "amount_total" in request.form:
            amt_tot_str = request.form.get("amount_total", "").strip()
            if amt_tot_str:
                try:
                    user.amount_total = float(amt_tot_str)
                except ValueError:
                    pass

        # Subscription Dates (from form)
        sub_start_date = None
        if "subscription_start" in request.form:
            start_str = request.form.get("subscription_start", "").strip()
            if start_str:
                try:
                    sub_start_date = datetime.strptime(start_str, "%Y-%m-%d").date()
                except ValueError:
                    pass

        sub_end_date = None
        if "subscription_end" in request.form:
            end_str = request.form.get("subscription_end", "").strip()
            if end_str:
                try:
                    sub_end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
                except ValueError:
                    pass

        # Synchronize subscription, custom pricing, duration, dates, and limits to all companies owned by this user
        companies = Company.query.filter_by(owner_email=user.email).all()
        for company in companies:
            if user.subscription_plan:
                company.subscription_plan = user.subscription_plan
            if user.plan_duration:
                company.plan_duration = user.plan_duration
            company.custom_yearly_amount = user.custom_yearly_amount
            if user.maintenance_due_date:
                company.maintenance_due_date = user.maintenance_due_date
            if sub_start_date:
                company.subscription_start = sub_start_date
            if sub_end_date:
                company.subscription_end = sub_end_date
            elif user.subscription_plan == "unlimited":
                company.subscription_end = None
            plan_obj = SubscriptionPlan.query.get(user.subscription_plan) if user.subscription_plan else None
            if user.custom_max_companies is not None:
                company.max_companies_allowed = str(user.custom_max_companies)
            elif plan_obj and plan_obj.max_companies:
                company.max_companies_allowed = str(plan_obj.max_companies)

            if user.custom_max_users is not None:
                company.max_users_per_company = str(user.custom_max_users)
            elif plan_obj and plan_obj.max_users:
                company.max_users_per_company = str(plan_obj.max_users)
            company.is_active = user.is_active

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"success": True, "message": "User account & subscription settings updated successfully."})


@app.route("/admin/user/<user_id>/delete", methods=["POST"])
@login_required
@super_admin_required
@require_admin_password
def admin_delete_user(user_id):
    """
    Delete a registered user (owner account) from the platform.
    This removes the user and ALL their companies.
    WARNING: This is permanent and cannot be undone.
    """
    user = RegisteredUser.query.filter_by(user_id=user_id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # Prevent super admin from deleting themselves
    current_user = get_current_user()
    if user.email == current_user.get("email"):
        return jsonify({"error": "You cannot delete your own account"}), 400
    
    try:
        from platform_models import CompanyWhatsAppConfig, BackupRecord, BackupSchedule
        
        # Get all companies owned by this user
        companies = Company.query.filter_by(owner_email=user.email).all()
        company_names = [c.company_name for c in companies]
        
        # Delete each company's related data
        for company in companies:
            # Delete WhatsApp configs
            CompanyWhatsAppConfig.query.filter_by(company_id=company.company_id).delete()
            # Delete backup records
            BackupRecord.query.filter_by(company_id=company.company_id).delete()
            # Delete backup schedules
            BackupSchedule.query.filter_by(company_id=company.company_id).delete()
            # Delete the company
            db.session.delete(company)
        
        # Delete the user
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({
            "success": True, 
            "message": f"User '{user.full_name}' and their {len(companies)} company(ies) have been deleted.",
            "deleted_companies": company_names
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route("/admin/users")
@login_required
@super_admin_required
def admin_users():
    """Users are now a tab inside /admin/dashboard (usersTab) rather than a
    standalone page — kept as a redirect so any old links/bookmarks still work."""
    return redirect(url_for('admin_dashboard'))

@app.route("/admin/company/<company_id>/delete", methods=["POST"])
@login_required
@super_admin_required
@require_admin_password
def admin_delete_company(company_id):
    """
    Delete a company at the platform level. Removes the Company row and its
    platform-side dependents (WhatsApp config, backup records/schedules).
    Does NOT drop the company's own customer database — left in place so it
    can be recovered or archived manually if needed.
    """
    company = get_company_by_id(company_id)
    if not company:
        return jsonify({"error": "Company not found"}), 404

    try:
        from platform_models import BackupRecord, BackupSchedule, CompanyWhatsAppConfig

        CompanyWhatsAppConfig.query.filter_by(company_id=company_id).delete()
        BackupRecord.query.filter_by(company_id=company_id).delete()
        BackupSchedule.query.filter_by(company_id=company_id).delete()

        db.session.delete(company)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

    return jsonify({"success": True})


@app.route("/admin/register-client", methods=["GET", "POST"])
@login_required
@super_admin_required
def register_client():
    """
    Super admin creates a client account directly: full name, address, phone,
    email/login, password, plan, and payment status. No Company is created
    here — the client sets that up themselves on first login
    (see onboard_company).
    """
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        address   = request.form.get("address", "").strip()
        phone     = request.form.get("phone", "").strip()
        email     = request.form.get("email", "").strip().lower()
        password  = request.form.get("password", "")
        plan_key  = request.form.get("subscription_plan", "starter")

        payment_status = request.form.get("payment_status", "pending")
        amount_total   = request.form.get("amount_total", "").strip()
        amount_paid    = request.form.get("amount_paid", "0").strip()

        if not full_name or not email or not password:
            flash("Full name, email and password are required", "error")
            return redirect(url_for("register_client"))

        if RegisteredUser.query.filter_by(email=email).first():
            flash("An account with this email already exists", "error")
            return redirect(url_for("register_client"))

        if len(password) < 8:
            flash("Password must be at least 8 characters", "error")
            return redirect(url_for("register_client"))

        plan_obj = SubscriptionPlan.query.get(plan_key) or SubscriptionPlan.query.order_by(SubscriptionPlan.id).first()
        if not plan_obj:
            flash("No subscription plans are configured. Add a plan before registering clients.", "error")
            return redirect(url_for("register_client"))

        try:
            amount_total_val = float(amount_total) if amount_total else None
        except ValueError:
            amount_total_val = None
        try:
            amount_paid_val = float(amount_paid) if amount_paid else 0.0
        except ValueError:
            amount_paid_val = 0.0

        # Keep status consistent with the amounts actually entered
        if amount_total_val and amount_paid_val >= amount_total_val:
            payment_status = "paid"
        elif amount_paid_val > 0:
            payment_status = "partial"
        else:
            payment_status = "pending"

        user_id = generate_next_user_id()

        # ── NEW: Handle custom plan fields ──────────────────────────────────
        custom_max_companies = None
        custom_max_users = None
        
        if plan_key == "custom":
            custom_max_companies = request.form.get("custom_max_companies", "").strip()
            custom_max_users = request.form.get("custom_max_users", "").strip()
            
            # Validate custom fields
            if not custom_max_companies or not custom_max_users:
                flash("Please enter custom Max Companies and Max Users for the Custom plan.", "error")
                return redirect(url_for("register_client"))
            
            try:
                custom_max_companies = int(custom_max_companies)
                custom_max_users = int(custom_max_users)
                if custom_max_companies < 1 or custom_max_users < 1:
                    flash("Max Companies and Max Users must be at least 1.", "error")
                    return redirect(url_for("register_client"))
            except ValueError:
                flash("Max Companies and Max Users must be valid numbers.", "error")
                return redirect(url_for("register_client"))

        new_user = RegisteredUser(
            user_id=user_id,
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            phone=phone,
            address=address,
            role="owner",
            subscription_plan=plan_obj.id,
            created_at=today_ist(),
            is_active=True,
            payment_status=payment_status,
            amount_total=amount_total_val,
            amount_paid=amount_paid_val,
            registered_by=get_current_user().get("email"),
            registered_at=datetime.utcnow(),
            custom_max_companies=custom_max_companies,
            custom_max_users=custom_max_users,
        )
        db.session.add(new_user)
        db.session.commit()

        flash(
            f"Client '{full_name}' registered. They can log in with {email} — "
            f"they'll be asked to set up their company profile on first login.",
            "success"
        )
        return redirect(url_for("admin_dashboard"))

    return render_template("register_client.html", plans=get_all_plans())


# ─────────────────────────────────────────────────────────────────────────────
# ── Employee Management ───────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/employees")
@login_required
@owner_required
def employee_list():
    cdb = get_cdb()
    company_id = get_current_company()
    employees  = cdb.query(CompanyUser).filter_by(company_id=company_id).all()
    return render_template("employees.html", employees=employees)


@app.route("/employees/add", methods=["GET", "POST"])
@login_required
@owner_required
def employee_add():
    cdb = get_cdb()
    company_id = get_current_company()
    can_add, msg = check_company_limit(company_id, "user")
    if not can_add:
        flash(msg)
        return redirect(url_for("employee_list"))

    if request.method == "POST":
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        emp_id    = _next_numbered_id(cdb, CompanyUser.user_id, "EMP")
        new_emp   = CompanyUser(
            user_id=emp_id, company_id=company_id, email=email,
            password_hash=hash_password(password),
            full_name=request.form.get("full_name", ""),
            role=request.form.get("role", "employee"),
            department=request.form.get("department", ""),
            phone=request.form.get("phone", ""),
            is_active=True, created_at=today_ist(),
        )
        cdb.add(new_emp)
        cdb.commit()
        flash("Employee added!")
        return redirect(url_for("employee_list"))
    return render_template("employee_form.html")


@app.route("/employees/toggle/<user_id>", methods=["POST"])
@login_required
@owner_required
def employee_toggle(user_id):
    cdb = get_cdb()
    company_id = get_current_company()
    emp        = _first_or_404(cdb.query(CompanyUser).filter_by(user_id=user_id, company_id=company_id).first())
    emp.is_active = not emp.is_active
    cdb.commit()
    flash(f"Employee {'activated' if emp.is_active else 'deactivated'}.")
    return redirect(url_for("employee_list"))


# ─────────────────────────────────────────────────────────────────────────────
# ── Product Lookup API ────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/product/<code>")
@login_required
@require_permission("stock", "view")
def api_product_lookup(code):
    cdb = get_cdb()
    company_id = get_current_company()
    code_clean = code.strip().upper()
    item = cdb.query(StockItem).filter_by(company_id=company_id, code=code_clean).first()
    if not item:
        item = cdb.query(StockItem).filter(
            StockItem.company_id == company_id,
            StockItem.name.ilike(f"%{code_clean}%")
        ).first()
    if not item:
        return jsonify({"found": False, "message": f"No product found for '{code}'"}), 404
    return jsonify({
        "found": True, "code": item.code, "name": item.name,
        "rate": item.unit_price, "unit": item.unit or "pcs",
        "category": item.category or "", "stock": item.quantity,
        "hsn": item.hsn or "",
        "low_stock": item.quantity <= item.reorder_level,
    }), 200


@app.route("/api/products/search")
@login_required
@require_permission("stock", "view")
def api_products_search():
    cdb = get_cdb()
    company_id = get_current_company()
    q = request.args.get("q", "").strip().upper()
    if not q:
        return jsonify({"results": []})
    items = cdb.query(StockItem).filter(
        StockItem.company_id == company_id,
        db.or_(StockItem.code.ilike(f"%{q}%"), StockItem.name.ilike(f"%{q}%")),
        StockItem.quantity > 0
    ).order_by(StockItem.name.asc()).limit(8).all()
    return jsonify({"results": [{
        "code": s.code, "name": s.name, "rate": s.unit_price,
        "unit": s.unit or "pcs", "stock": s.quantity, "hsn": s.hsn or "",
    } for s in items]})


# ============================================
# BANK ACCOUNTS & FINANCE ROUTES
# ============================================

# ============================================
# CASH IN HAND ROUTES
# ============================================

@app.route("/cash-in-hand")
@login_required
@require_permission("cash", "view")
def cash_in_hand():
    """Cash in hand tracking"""
    cdb = get_cdb()
    company_id = get_current_company()
    
    # Get filter parameters
    from_date_str = request.args.get('from_date', '')
    to_date_str = request.args.get('to_date', '')
    filter_type = request.args.get('type', 'all')
    
    # Set default dates (last 30 days)
    if not from_date_str:
        from_date = today_ist() - timedelta(days=30)
    else:
        from_date = date.fromisoformat(from_date_str)
    
    if not to_date_str:
        to_date = today_ist()
    else:
        to_date = date.fromisoformat(to_date_str)
    
    # Build query
    query = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        CashTransaction.date >= from_date,
        CashTransaction.date <= to_date
    )
    
    if filter_type != 'all':
        query = query.filter(CashTransaction.type == filter_type)
    
    transactions = query.order_by(CashTransaction.date.desc()).all()
    
    # Calculate totals
    total_inflow = sum(t.amount for t in transactions if t.type == 'income')
    total_outflow = sum(t.amount for t in transactions if t.type == 'expense')
    
    # Calculate current balance (all time)
    all_income = cdb.query(CashTransaction).filter_by(company_id=company_id, type='income').all()
    all_expense = cdb.query(CashTransaction).filter_by(company_id=company_id, type='expense').all()
    current_balance = sum(t.amount for t in all_income) - sum(t.amount for t in all_expense)
    
    # Format transactions for template
    running_balance = 0
    all_transactions = cdb.query(CashTransaction).filter_by(company_id=company_id).order_by(CashTransaction.date.asc()).all()
    
    # Create a dict of running balances
    balance_map = {}
    for t in all_transactions:
        if t.type == 'income':
            running_balance += t.amount
        else:
            running_balance -= t.amount
        balance_map[t.id] = running_balance
    
    transactions_list = []
    for t in transactions:
        transactions_list.append({
            'id': t.id,
            'date': t.date.strftime('%d %b %Y'),
            'type': t.type,
            'category': t.category,
            'description': t.description,
            'amount': t.amount,
            'reference': t.reference or '',
            'notes': t.notes or '',
            'balance_after': balance_map.get(t.id, 0)
        })
    
    return render_template("cash_in_hand.html",
                         active='cash_in_hand',
                         current_balance=current_balance,
                         total_inflow=total_inflow,
                         total_outflow=total_outflow,
                         transactions=transactions_list,
                         from_date=from_date.strftime('%Y-%m-%d'),
                         to_date=to_date.strftime('%Y-%m-%d'),
                         today=today_ist().strftime('%Y-%m-%d'))


@app.route("/api/cash-transaction/save", methods=["POST"])
@login_required
@require_permission("cash", "create")
def save_cash_transaction():
    """Save a cash transaction"""
    company_id = get_current_company()
    data = request.get_json()
    
    try:
        transaction = CashTransaction(
            company_id=company_id,
            type=data.get('type'),
            date=date.fromisoformat(data.get('date')),
            category=data.get('category'),
            description=data.get('description'),
            amount=data.get('amount'),
            reference=data.get('reference', ''),
            notes=data.get('notes', ''),
            created_by=get_current_user().get('email')
        )
        cdb.add(transaction)
        cdb.commit()
        
        return jsonify({'success': True, 'message': 'Transaction saved successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route("/api/cash-transaction/delete/<int:txn_id>", methods=["DELETE"])
@login_required
@owner_required
@require_admin_password
def delete_cash_transaction(txn_id):
    """Delete a cash transaction"""
    cdb = get_cdb()
    company_id = get_current_company()
    transaction = cdb.query(CashTransaction).filter_by(id=txn_id, company_id=company_id).first()
    
    if not transaction:
        return jsonify({'success': False, 'message': 'Transaction not found'}), 404
    
    try:
        cdb.delete(transaction)
        cdb.commit()
        return jsonify({'success': True, 'message': 'Transaction deleted'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

# ============================================
# BANK ACCOUNTS ROUTES
# ============================================

@app.route("/bank-accounts")
@login_required
@require_permission("bank", "view")
def bank_accounts():
    """Bank Accounts management page"""
    cdb = get_cdb()
    company_id = get_current_company()
    bank_accounts = cdb.query(BankAccount).filter_by(company_id=company_id, status='Active').all()
    inactive_accounts = cdb.query(BankAccount).filter_by(company_id=company_id, status='Inactive').all()
    inactive_txn_counts = {
        acc.id: cdb.query(BankTransaction).filter_by(bank_account_id=acc.id).count()
        for acc in inactive_accounts
    }
    
    # Calculate total balance
    total_balance = sum(acc.balance for acc in bank_accounts)
    
    return render_template("bank_accounts.html", 
                         active='bank_accounts',
                         bank_accounts=bank_accounts,
                         inactive_accounts=inactive_accounts,
                         inactive_txn_counts=inactive_txn_counts,
                         total_balance=total_balance)


@app.route("/bank-accounts/add", methods=["POST"])
@login_required
@require_permission("bank", "create")
def add_bank_account():
    """Add a new bank account"""
    cdb = get_cdb()
    company_id = get_current_company()
    
    bank_name = request.form.get("bank_name", "").strip()
    account_name = request.form.get("account_name", "").strip()
    account_number = request.form.get("account_number", "").strip()
    ifsc_code = request.form.get("ifsc_code", "").strip()
    branch = request.form.get("branch", "").strip()
    opening_balance = float(request.form.get("balance", 0) or 0)
    
    if not bank_name or not account_name or not account_number:
        flash("Bank Name, Account Name, and Account Number are required!")
        return redirect(url_for("bank_accounts"))
    
    # Check if account number already exists for this company
    existing = cdb.query(BankAccount).filter_by(company_id=company_id, account_number=account_number).first()
    if existing:
        flash(f"Account number {account_number} already exists!")
        return redirect(url_for("bank_accounts"))
    
    new_account = BankAccount(
        company_id=company_id,
        bank_name=bank_name,
        account_name=account_name,
        account_number=account_number,
        ifsc_code=ifsc_code,
        branch=branch,
        opening_balance=opening_balance,
        balance=opening_balance,
        status='Active',
        created_at=datetime.utcnow()
    )
    
    cdb.add(new_account)
    cdb.flush()  # assigns new_account.id before it's referenced below

    # Add opening balance transaction if opening_balance > 0
    if opening_balance > 0:
        opening_txn = BankTransaction(
            bank_account_id=new_account.id,
            company_id=company_id,
            type='credit',
            date=today_ist(),
            description=f"Opening Balance for {bank_name} - {account_name}",
            amount=opening_balance,
            reference="Opening Balance",
            transaction_mode="Cash",
            created_by=get_current_user().get('email')
        )
        cdb.add(opening_txn)
    
    cdb.commit()
    flash(f"Bank account {bank_name} - {account_name} added successfully!")
    return redirect(url_for("bank_accounts"))


@app.route("/bank-accounts/<int:account_id>/transactions")
@login_required
@require_permission("bank", "view")
def bank_transactions(account_id):
    """View transactions for a specific bank account"""
    cdb = get_cdb()
    company_id = get_current_company()
    account = _first_or_404(cdb.query(BankAccount).filter_by(id=account_id, company_id=company_id).first())
    
    # Get filter parameters - default to ALL TIME (not just 30 days)
    from_date_str = request.args.get('from_date', '')
    to_date_str = request.args.get('to_date', '')
    txn_type = request.args.get('type', 'all')
    
    # Build query - start with ALL transactions
    query = cdb.query(BankTransaction).filter(
        BankTransaction.bank_account_id == account_id,
        BankTransaction.company_id == company_id
    )
    
    # Apply date filters ONLY if provided
    if from_date_str:
        try:
            from_date = date.fromisoformat(from_date_str)
            query = query.filter(BankTransaction.date >= from_date)
        except ValueError:
            pass
    
    if to_date_str:
        try:
            to_date = date.fromisoformat(to_date_str)
            query = query.filter(BankTransaction.date <= to_date)
        except ValueError:
            pass
    
    # If no date filters, show ALL transactions (including opening balance)
    
    if txn_type != 'all':
        query = query.filter(BankTransaction.type == txn_type)
    
    # Get all transactions sorted by date ASC (oldest first for running balance)
    all_transactions = query.order_by(BankTransaction.date.asc(), BankTransaction.id.asc()).all()
    
    # Calculate running balance
    running_balance = 0
    transactions_with_balance = []
    
    for txn in all_transactions:
        if txn.type == 'credit':
            running_balance += txn.amount
        else:
            running_balance -= txn.amount
        
        transactions_with_balance.append({
            'id': txn.id,
            'date': txn.date,
            'type': txn.type,
            'description': txn.description,
            'amount': txn.amount,
            'reference': txn.reference or '',
            'transaction_mode': txn.transaction_mode or '',
            'notes': txn.notes or '',
            'running_balance': running_balance,
            'party_name': txn.party_name or '',
            'created_by': txn.created_by or '',
        })
    
    # Get total credits and debits for the filtered period
    total_credits = sum(t.amount for t in all_transactions if t.type == 'credit')
    total_debits = sum(t.amount for t in all_transactions if t.type == 'debit')
    
    # Get the account's opening balance (first transaction)
    opening_balance_txn = None
    if all_transactions and all_transactions[0].description and 'Opening Balance' in all_transactions[0].description:
        opening_balance_txn = all_transactions[0]
    
    # For the template - show opening balance separately
    opening_balance = account.opening_balance or 0
    current_balance = account.balance or 0
    
    # Get date range for filter display
    if from_date_str:
        display_from = from_date_str
    else:
        # Show the earliest transaction date or the account creation date
        if all_transactions:
            display_from = all_transactions[0].date.strftime('%Y-%m-%d')
        else:
            display_from = account.created_at.strftime('%Y-%m-%d') if account.created_at else today_ist().strftime('%Y-%m-%d')
    
    if to_date_str:
        display_to = to_date_str
    else:
        display_to = today_ist().strftime('%Y-%m-%d')
    
    return render_template("bank_transactions.html",
                         active='bank_accounts',
                         account=account,
                         transactions=transactions_with_balance,
                         total_credits=total_credits,
                         total_debits=total_debits,
                         opening_balance=opening_balance,
                         current_balance=current_balance,
                         from_date=display_from,
                         to_date=display_to,
                         today=today_ist().strftime('%Y-%m-%d'))


@app.route("/bank-accounts/<int:account_id>/add-transaction", methods=["POST"])
@login_required
@require_permission("bank", "create")
def add_bank_transaction(account_id):
    """Add a transaction to a bank account"""
    cdb = get_cdb()
    company_id = get_current_company()
    account = _first_or_404(cdb.query(BankAccount).filter_by(id=account_id, company_id=company_id).first())
    
    txn_type = request.form.get("type")
    date_str = request.form.get("date")
    description = request.form.get("description", "").strip()
    amount = float(request.form.get("amount", 0))
    reference = request.form.get("reference", "").strip()
    transaction_mode = request.form.get("transaction_mode", "Transfer")
    notes = request.form.get("notes", "").strip()
    
    if not description or amount <= 0:
        flash("Description and valid amount are required!")
        return redirect(url_for("bank_transactions", account_id=account_id))
    
    # Create transaction
    transaction = BankTransaction(
        bank_account_id=account.id,
        company_id=company_id,
        type=txn_type,
        date=date.fromisoformat(date_str) if date_str else today_ist(),
        description=description,
        amount=amount,
        reference=reference,
        transaction_mode=transaction_mode,
        notes=notes,
        created_by=get_current_user().get('email')
    )
    cdb.add(transaction)
    
    # Update account balance
    if txn_type == 'credit':
        account.balance += amount
    else:
        account.balance -= amount
    
    account.updated_at = datetime.utcnow()
    
    cdb.commit()
    flash(f"{'Deposit' if txn_type == 'credit' else 'Withdrawal'} of {company_currency_symbol()} {amount:,.2f} recorded successfully!")
    return redirect(url_for("bank_transactions", account_id=account_id))


@app.route("/bank-accounts/<int:account_id>/delete", methods=["GET", "POST"])
@login_required
@owner_required
@require_admin_password
def delete_bank_account(account_id):
    """Delete a bank account (soft delete by setting status to Inactive)"""
    cdb = get_cdb()
    company_id = get_current_company()
    account = _first_or_404(cdb.query(BankAccount).filter_by(id=account_id, company_id=company_id).first())
    
    # Soft delete - just mark as inactive
    account.status = 'Inactive'
    cdb.commit()
    
    flash(f"Bank account {account.bank_name} - {account.account_name} has been deactivated.")
    return redirect(url_for("bank_accounts"))


@app.route("/bank-accounts/<int:account_id>/reactivate", methods=["GET", "POST"])
@login_required
@owner_required
def reactivate_bank_account(account_id):
    """Reactivate a previously deactivated bank account"""
    cdb = get_cdb()
    company_id = get_current_company()
    account = _first_or_404(cdb.query(BankAccount).filter_by(id=account_id, company_id=company_id).first())

    account.status = 'Active'
    cdb.commit()

    flash(f"Bank account {account.bank_name} - {account.account_name} has been reactivated.")
    return redirect(url_for("bank_accounts"))


@app.route("/bank-accounts/<int:account_id>/delete-permanent", methods=["POST"])
@login_required
@owner_required
@require_admin_password
def delete_bank_account_permanent(account_id):
    """Permanently delete a bank account. Only allowed when the account is
    already Inactive and has zero transactions, so a real ledger with history
    can never be wiped by accident."""
    cdb = get_cdb()
    company_id = get_current_company()
    account = _first_or_404(cdb.query(BankAccount).filter_by(id=account_id, company_id=company_id).first())

    if account.status != 'Inactive':
        flash("Deactivate this account before deleting it permanently.")
        return redirect(url_for("bank_accounts"))

    txn_count = cdb.query(BankTransaction).filter_by(bank_account_id=account.id).count()
    name = f"{account.bank_name} - {account.account_name}"
    cdb.delete(account)  # cascade="all, delete-orphan" also removes its BankTransaction rows
    cdb.commit()

    if txn_count > 0:
        flash(f"Bank account {name} and its {txn_count} transaction(s) have been permanently deleted.")
    else:
        flash(f"Bank account {name} has been permanently deleted.")
    return redirect(url_for("bank_accounts"))


@app.route("/bank-accounts/<int:account_id>/transfer", methods=["POST"])
@login_required
@require_permission("bank", "edit")
def bank_transfer(account_id):
    """Transfer money between bank accounts"""
    cdb = get_cdb()
    company_id = get_current_company()
    from_account = _first_or_404(cdb.query(BankAccount).filter_by(id=account_id, company_id=company_id).first())
    
    to_account_id = request.form.get("to_account_id", type=int)
    amount = float(request.form.get("amount", 0))
    date_str = request.form.get("date")
    description = request.form.get("description", "").strip()
    reference = request.form.get("reference", "").strip()
    
    to_account = cdb.query(BankAccount).filter_by(id=to_account_id, company_id=company_id).first()
    
    if not to_account:
        flash("Destination account not found!")
        return redirect(url_for("bank_transactions", account_id=account_id))
    
    if amount <= 0:
        flash("Amount must be greater than 0!")
        return redirect(url_for("bank_transactions", account_id=account_id))
    
    if from_account.balance < amount:
        flash(f"Insufficient balance in {from_account.bank_name} - {from_account.account_name}!")
        return redirect(url_for("bank_transactions", account_id=account_id))
    
    txn_date = date.fromisoformat(date_str) if date_str else today_ist()
    
    # Debit transaction from source account
    debit_txn = BankTransaction(
        bank_account_id=from_account.id,
        company_id=company_id,
        type='debit',
        date=txn_date,
        description=f"Transfer to {to_account.bank_name} - {to_account.account_name}: {description}" if description else f"Transfer to {to_account.bank_name} - {to_account.account_name}",
        amount=amount,
        reference=reference,
        transaction_mode="Transfer",
        notes=f"Transfer from {from_account.bank_name} to {to_account.bank_name}",
        created_by=get_current_user().get('email'),
        party_name=f"{from_account.bank_name} - Transfer"  # ← ADD THIS
    )
    cdb.add(debit_txn)
    from_account.balance -= amount
    
    # Credit transaction to destination account
    credit_txn = BankTransaction(
        bank_account_id=to_account.id,
        company_id=company_id,
        type='credit',
        date=txn_date,
        description=f"Transfer from {from_account.bank_name} - {from_account.account_name}: {description}" if description else f"Transfer from {from_account.bank_name} - {from_account.account_name}",
        amount=amount,
        reference=reference,
        transaction_mode="Transfer",
        notes=f"Transfer from {from_account.bank_name} to {to_account.bank_name}",
        created_by=get_current_user().get('email'),
        party_name=f"{to_account.bank_name} - Transfer"
    )
    cdb.add(credit_txn)
    to_account.balance += amount
    
    from_account.updated_at = datetime.utcnow()
    to_account.updated_at = datetime.utcnow()
    
    cdb.commit()
    flash(f"Transferred {company_currency_symbol()} {amount:,.2f} from {from_account.bank_name} to {to_account.bank_name} successfully!")
    return redirect(url_for("bank_transactions", account_id=account_id))

@app.route("/admin/repair-party-names", methods=["POST"])
@login_required
@owner_required
def repair_party_names():
    """Fix all existing transactions with inconsistent party_name values."""
    cdb = get_cdb()
    company_id = get_current_company()
    
    # Get all clients
    clients = cdb.query(Client).filter_by(company_id=company_id).all()
    client_name_map = {c.name.lower(): c.name for c in clients}
    
    # Fix CashTransactions
    cash_txns = cdb.query(CashTransaction).filter_by(company_id=company_id).all()
    cash_repaired = 0
    for txn in cash_txns:
        if txn.party_name:
            txn_lower = txn.party_name.lower()
            # Try to match with a client
            for client_lower, client_name in client_name_map.items():
                if client_lower in txn_lower or txn_lower in client_lower:
                    if txn.party_name != client_name:
                        txn.party_name = client_name
                        cash_repaired += 1
                    break
    
    # Fix BankTransactions
    bank_txns = cdb.query(BankTransaction).filter_by(company_id=company_id).all()
    bank_repaired = 0
    for txn in bank_txns:
        if txn.party_name:
            txn_lower = txn.party_name.lower()
            for client_lower, client_name in client_name_map.items():
                if client_lower in txn_lower or txn_lower in client_lower:
                    if txn.party_name != client_name:
                        txn.party_name = client_name
                        bank_repaired += 1
                    break
    
    # Fix Suppliers
    suppliers = cdb.query(Supplier).filter_by(company_id=company_id).all()
    supplier_name_map = {s.name.lower(): s.name for s in suppliers}
    
    # Fix CashTransactions for suppliers
    for txn in cash_txns:
        if txn.party_name:
            txn_lower = txn.party_name.lower()
            for sup_lower, sup_name in supplier_name_map.items():
                if sup_lower in txn_lower or txn_lower in sup_lower:
                    if txn.party_name != sup_name:
                        txn.party_name = sup_name
                        cash_repaired += 1
                    break
    
    # Fix BankTransactions for suppliers
    for txn in bank_txns:
        if txn.party_name:
            txn_lower = txn.party_name.lower()
            for sup_lower, sup_name in supplier_name_map.items():
                if sup_lower in txn_lower or txn_lower in sup_lower:
                    if txn.party_name != sup_name:
                        txn.party_name = sup_name
                        bank_repaired += 1
                    break
    
    cdb.commit()
    
    flash(
        f"Repaired {cash_repaired} cash transactions and {bank_repaired} bank transactions. "
        f"Party names are now consistent with client/supplier records.",
        "success"
    )
    return redirect(url_for("company_settings"))

@app.route("/cheques")
@login_required
@require_permission("cheques", "view")
def cheques():
    """Cheque register — record and track cheques received/paid"""
    cdb        = get_cdb()
    company_id = get_current_company()

    all_clients   = cdb.query(Client).filter_by(company_id=company_id).order_by(Client.name).all()
    all_suppliers = cdb.query(Supplier).filter_by(company_id=company_id).order_by(Supplier.name).all()
    bank_accounts = cdb.query(BankAccount).filter_by(company_id=company_id, status='Active').all()

    direction   = request.args.get("direction", "")     # '', 'received', 'paid'
    status      = request.args.get("status", "")        # '', 'Pending', 'Cleared', 'Bounced', 'Cancelled'
    date_from_s = request.args.get("date_from", "")
    date_to_s   = request.args.get("date_to", "")
    date_from   = date.fromisoformat(date_from_s) if date_from_s else None
    date_to     = date.fromisoformat(date_to_s) if date_to_s else None

    q = cdb.query(Cheque).filter_by(company_id=company_id)
    if direction:
        q = q.filter(Cheque.direction == direction)
    if status:
        q = q.filter(Cheque.status == status)
    if date_from:
        q = q.filter(Cheque.cheque_date >= date_from)
    if date_to:
        q = q.filter(Cheque.cheque_date <= date_to)
    cheque_rows = q.order_by(Cheque.cheque_date.desc(), Cheque.id.desc()).all()

    cheque_list = [{
        "id":           c.id,
        "direction":    c.direction,
        "party_name":   c.party_name,
        "cheque_no":    c.cheque_no,
        "cheque_date":  c.cheque_date.strftime("%d %b %Y") if c.cheque_date else "",
        "bank_name":    c.bank_name or "—",
        "amount":       c.amount,
        "narration":    c.narration or "",
        "status":       c.status,
        "cleared_date": c.cleared_date.strftime("%d %b %Y") if c.cleared_date else "",
        "bill_ref":     (c.invoice.invoice_id if c.invoice else
                          (c.purchase_invoice.invoice_number or c.purchase_invoice.invoice_id) if c.purchase_invoice else None),
    } for c in cheque_rows]

    pending_received = sum(c.amount for c in cheque_rows if c.direction == "received" and c.status == "Pending")
    pending_paid     = sum(c.amount for c in cheque_rows if c.direction == "paid" and c.status == "Pending")
    cleared_received = sum(c.amount for c in cheque_rows if c.direction == "received" and c.status == "Cleared")
    cleared_paid     = sum(c.amount for c in cheque_rows if c.direction == "paid" and c.status == "Cleared")
    bounced_count    = sum(1 for c in cheque_rows if c.status == "Bounced")

    # ── Bill-wise + total pending per party, for the "select a party" step ──
    # Reuses the same helpers the Receipts/Payments pages already use, so a
    # client's outstanding invoices (and a supplier's outstanding purchase
    # bills) show up identically here — one source of truth instead of a
    # second copy of the balance logic.
    invoices_json          = _build_invoices_json(company_id, all_clients, _outstanding_invoices_for_client)
    purchase_invoices_json = _build_invoices_json(company_id, all_suppliers, _outstanding_invoices_for_supplier)
    # Live-computed, not the cached client.pending column — this feeds the
    # "select a party" step when recording a receipt, so a stale cached
    # value here directly misleads whoever is allocating the payment.
    _client_outstanding_by_id = _compute_outstanding_for_clients(cdb, company_id, all_clients)
    client_pending_json    = json.dumps({str(c.id): _client_outstanding_by_id.get(c.id, 0.0) for c in all_clients})
    supplier_payable_json  = json.dumps({str(s.id): (s.payable or 0) for s in all_suppliers})

    # ── "Yet to receive / yet to pay" lists ──────────────────────────────────
    debtors   = [d for d in _debtor_summary(company_id) if d["total_pending"] > 0]
    creditors = [c for c in _creditor_summary(company_id) if c["total_pending"] > 0]

    return render_template(
        "cheques.html",
        active='cheques',
        clients=all_clients,
        suppliers=all_suppliers,
        bank_accounts=bank_accounts,
        cheques=cheque_list,
        direction=direction,
        status=status,
        date_from=date_from_s,
        date_to=date_to_s,
        pending_received=pending_received,
        pending_paid=pending_paid,
        cleared_received=cleared_received,
        cleared_paid=cleared_paid,
        bounced_count=bounced_count,
        invoices_json=invoices_json,
        purchase_invoices_json=purchase_invoices_json,
        client_pending_json=client_pending_json,
        supplier_payable_json=supplier_payable_json,
        debtors=debtors,
        creditors=creditors,
        today=str(today_ist()),
    )


@app.route("/cheques/save", methods=["POST"])
@login_required
@require_permission("cheques", "create")
def cheque_save():
    """Record a new cheque (received or paid) — starts life as Pending"""
    cdb        = get_cdb()
    company_id = get_current_company()

    direction   = request.form.get("direction", "received")
    party_type  = request.form.get("party_type", "")
    party_id    = request.form.get("party_id", type=int)
    party_name = get_party_name(
        client_id=party_id if party_type == "client" else None,
        supplier_id=party_id if party_type == "supplier" else None,
        form=request.form,
        fallback_name=request.form.get("party_name", "").strip()
    )
    cheque_no   = request.form.get("cheque_no", "").strip()
    cheque_date_s = request.form.get("cheque_date")
    bank_name   = request.form.get("bank_name", "").strip()
    bank_account_id = request.form.get("bank_account_id", type=int)
    amount      = request.form.get("amount", type=float, default=0)
    narration   = request.form.get("narration", "")

    # ── Apply against a specific bill, or record as a general/advance cheque ──
    # apply_to == "bill" pairs this cheque with one open Invoice (received) or
    # PurchaseInvoice (paid); "advance" leaves both link columns NULL. Either
    # way the cheque itself still starts life as Pending — the linked bill's
    # balance isn't touched until the cheque actually clears (see cheque_clear).
    apply_to        = request.form.get("apply_to", "advance")
    invoice_pk      = request.form.get("invoice_id", type=int)
    purchase_pk     = request.form.get("purchase_invoice_id", type=int)
    linked_invoice_id          = None
    linked_purchase_invoice_id = None

    if not party_name or not cheque_no or amount <= 0 or not cheque_date_s:
        flash("Please fill in party, cheque number, date, and a valid amount.", "error")
        return redirect(url_for("cheques"))

    if apply_to == "bill":
        if direction == "received":
            if not invoice_pk:
                flash("Select which invoice this cheque is against, or switch to a general payment.", "error")
                return redirect(url_for("cheques"))
            bill = cdb.query(Invoice).filter_by(id=invoice_pk, company_id=company_id, client_id=party_id).first()
            if not bill:
                flash("Selected invoice was not found for this client.", "error")
                return redirect(url_for("cheques"))
            if amount > (bill.balance or 0) + 0.01:
                flash(f"Cheque amount ({company_currency_symbol()} {amount:,.2f}) is more than {bill.invoice_id}'s balance ({company_currency_symbol()} {bill.balance or 0:,.2f}).", "error")
                return redirect(url_for("cheques"))
            linked_invoice_id = bill.id
        else:
            if not purchase_pk:
                flash("Select which bill this cheque is against, or switch to a general payment.", "error")
                return redirect(url_for("cheques"))
            bill = cdb.query(PurchaseInvoice).filter_by(id=purchase_pk, company_id=company_id, supplier_id=party_id).first()
            if not bill:
                flash("Selected purchase bill was not found for this supplier.", "error")
                return redirect(url_for("cheques"))
            if amount > (bill.balance or 0) + 0.01:
                flash(f"Cheque amount ({company_currency_symbol()} {amount:,.2f}) is more than bill {bill.invoice_number or bill.invoice_id}'s balance ({company_currency_symbol()} {bill.balance or 0:,.2f}).", "error")
                return redirect(url_for("cheques"))
            linked_purchase_invoice_id = bill.id

    cheque = Cheque(
        company_id=company_id,
        direction=direction,
        party_type=party_type or None,
        party_id=party_id,
        party_name=party_name,
        cheque_no=cheque_no,
        cheque_date=date.fromisoformat(cheque_date_s),
        bank_name=bank_name or None,
        bank_account_id=bank_account_id,
        amount=amount,
        narration=narration,
        status="Pending",
        invoice_id=linked_invoice_id,
        purchase_invoice_id=linked_purchase_invoice_id,
        created_by=get_current_user().get('email'),
    )
    cdb.add(cheque)
    cdb.commit()

    flash(f"Cheque {cheque_no} ({'received from' if direction == 'received' else 'issued to'} {party_name}) recorded as Pending.", "success")
    return redirect(url_for("cheques"))


@app.route("/cheques/<int:cheque_id>/clear", methods=["POST"])
@login_required
@require_permission("cheques", "edit")
def cheque_clear(cheque_id):
    """Mark a cheque as Cleared — this is what actually moves the bank balance"""
    cdb        = get_cdb()
    company_id = get_current_company()

    cheque = cdb.query(Cheque).filter_by(id=cheque_id, company_id=company_id).first()
    if not cheque:
        flash("Cheque not found.", "error")
        return redirect(url_for("cheques"))
    if cheque.status != "Pending":
        flash(f"Only pending cheques can be cleared (this one is {cheque.status}).", "error")
        return redirect(url_for("cheques"))
    if not cheque.bank_account_id:
        flash("Select a bank account for this cheque before clearing it.", "error")
        return redirect(url_for("cheques"))

    bank_account = cdb.query(BankAccount).filter_by(
        id=cheque.bank_account_id, company_id=company_id, status='Active'
    ).first()
    if not bank_account:
        flash("Linked bank account not found or inactive.", "error")
        return redirect(url_for("cheques"))

    cleared_date_s = request.form.get("cleared_date")
    cleared_date   = date.fromisoformat(cleared_date_s) if cleared_date_s else today_ist()

    is_received = cheque.direction == "received"
    bank_txn = BankTransaction(
        bank_account_id=bank_account.id,
        company_id=company_id,
        type="credit" if is_received else "debit",
        date=cleared_date,
        description=f"Cheque {'received from' if is_received else 'paid to'} {cheque.party_name}",
        amount=cheque.amount,
        reference=cheque.cheque_no,
        transaction_mode="Cheque",
        notes=cheque.narration,
        created_by=get_current_user().get('email'),
    )
    cdb.add(bank_txn)
    bank_account.balance += cheque.amount if is_received else -cheque.amount

    cheque.status       = "Cleared"
    cheque.cleared_date = cleared_date
    cdb.flush()
    cheque.bank_txn_id  = bank_txn.id

    # ── Settle the linked bill, if this cheque was applied against one ──────
    # Deliberately happens at CLEAR time, not at save time — a Pending cheque
    # can still bounce, and a bill shouldn't be marked paid off money that
    # hasn't actually landed yet. Same balance/status math as
    # purchase_make_payment() (paid) and receipt_save() (received) use for
    # cash/bank payments, so a cheque settles a bill exactly the same way
    # those do. A general/advance cheque (no invoice_id/purchase_invoice_id)
    # skips this — there's no bill to apply it to.
    if is_received and cheque.invoice_id:
        inv = cdb.query(Invoice).filter_by(id=cheque.invoice_id, company_id=company_id).first()
        if inv:
            apply = min(cheque.amount, inv.balance or 0)
            inv.paid_amount = (inv.paid_amount or 0) + apply
            inv.balance     = max(0, (inv.balance or 0) - apply)
            if inv.balance <= 0:
                inv.status = "Paid"
            elif inv.paid_amount > 0:
                inv.status = "Partial"
            if inv.client_id:
                client = cdb.query(Client).filter_by(id=inv.client_id, company_id=company_id).first()
                if client:
                    client.pending = max(0, (client.pending or 0) - apply)
    elif (not is_received) and cheque.purchase_invoice_id:
        pinv = cdb.query(PurchaseInvoice).filter_by(id=cheque.purchase_invoice_id, company_id=company_id).first()
        if pinv:
            apply = min(cheque.amount, pinv.balance or 0)
            pinv.paid_amount = (pinv.paid_amount or 0) + apply
            pinv.balance     = max(0, (pinv.balance or 0) - apply)
            if pinv.balance <= 0:
                pinv.status = "Paid"
            elif pinv.paid_amount > 0:
                pinv.status = "Partial"
            if pinv.supplier_id:
                supplier = cdb.query(Supplier).filter_by(id=pinv.supplier_id, company_id=company_id).first()
                if supplier:
                    supplier.payable = max(0, (supplier.payable or 0) - apply)

    cdb.commit()

    flash(f"Cheque {cheque.cheque_no} cleared — {company_currency_symbol()} {cheque.amount:,.2f} {'credited to' if is_received else 'debited from'} {bank_account.bank_name}.", "success")
    return redirect(url_for("cheques"))


@app.route("/cheques/<int:cheque_id>/bounce", methods=["POST"])
@login_required
@require_permission("cheques", "edit")
def cheque_bounce(cheque_id):
    """Mark a pending cheque as Bounced"""
    cdb        = get_cdb()
    company_id = get_current_company()

    cheque = cdb.query(Cheque).filter_by(id=cheque_id, company_id=company_id).first()
    if not cheque:
        flash("Cheque not found.", "error")
        return redirect(url_for("cheques"))
    if cheque.status != "Pending":
        flash(f"Only pending cheques can be marked as bounced (this one is {cheque.status}).", "error")
        return redirect(url_for("cheques"))

    cheque.status = "Bounced"
    cdb.commit()
    flash(f"Cheque {cheque.cheque_no} marked as Bounced.", "success")
    return redirect(url_for("cheques"))


@app.route("/cheques/<int:cheque_id>/cancel", methods=["POST"])
@login_required
@require_permission("cheques", "edit")
def cheque_cancel(cheque_id):
    """Cancel a pending cheque (e.g. entered by mistake)"""
    cdb        = get_cdb()
    company_id = get_current_company()

    cheque = cdb.query(Cheque).filter_by(id=cheque_id, company_id=company_id).first()
    if not cheque:
        flash("Cheque not found.", "error")
        return redirect(url_for("cheques"))
    if cheque.status != "Pending":
        flash(f"Only pending cheques can be cancelled (this one is {cheque.status}).", "error")
        return redirect(url_for("cheques"))

    cheque.status = "Cancelled"
    cdb.commit()
    flash(f"Cheque {cheque.cheque_no} cancelled.", "success")
    return redirect(url_for("cheques"))

# ============================================
# LOAN ACCOUNTS ROUTES
# ============================================

@app.route("/loan-accounts")
@login_required
@require_permission("loans", "view")
def loan_accounts():
    """Loan accounts management"""
    cdb = get_cdb()
    company_id = get_current_company()
    
    # Get all loans
    all_loans = cdb.query(Loan).filter_by(company_id=company_id).all()
    
    # Separate by type
    loans_given = []
    loans_taken = []
    
    for loan in all_loans:
        payments = []
        for payment in loan.repayments:
            payments.append({
                'id': payment.id,
                'date': payment.date.strftime('%d %b %Y'),
                'amount': payment.amount,
                'payment_mode': payment.payment_mode,
                'reference': payment.reference or '',
                'notes': payment.notes or ''
            })
        
        loan_dict = {
            'id': loan.id,
            'type': loan.type,
            'party_name': loan.party_name,
            'borrower_name': loan.party_name,
            'lender_name': loan.party_name,
            'loan_date': loan.loan_date.strftime('%d %b %Y'),
            'amount': loan.amount,
            'remaining_amount': loan.remaining_amount,
            'repaid_amount': loan.repaid_amount,
            'repayment_percentage': loan.repayment_percentage,
            'interest_rate': loan.interest_rate,
            'tenure': loan.tenure,
            'emi_amount': loan.emi_amount,
            'purpose': loan.purpose or '',
            'notes': loan.notes or '',
            'status': loan.status,
            'payments': payments
        }
        
        if loan.type == 'given':
            loans_given.append(loan_dict)
        else:
            loans_taken.append(loan_dict)
    
    # Calculate totals
    total_given = sum(l.amount for l in all_loans if l.type == 'given')
    total_taken = sum(l.amount for l in all_loans if l.type == 'taken')
    total_repaid = sum(l.repaid_amount for l in all_loans)
    
    return render_template("loan_accounts.html",
                         active='loan_accounts',
                         loans_given=loans_given,
                         loans_taken=loans_taken,
                         total_given=total_given,
                         total_taken=total_taken,
                         total_repaid=total_repaid,
                         today=today_ist().strftime('%Y-%m-%d'))


@app.route("/api/loan/save", methods=["POST"])
@login_required
@require_permission("loans", "create")
def save_loan():
    """Save a new loan"""
    cdb = get_cdb()
    company_id = get_current_company()
    data = request.get_json()
    
    try:
        loan = Loan(
            company_id=company_id,
            type=data.get('type'),
            party_name=data.get('party_name'),
            loan_date=date.fromisoformat(data.get('loan_date')),
            amount=data.get('amount'),
            interest_rate=data.get('interest_rate', 0),
            tenure=data.get('tenure', 12),
            emi_amount=data.get('emi_amount', 0),
            purpose=data.get('purpose', ''),
            notes=data.get('notes', ''),
            status='Active',
            created_by=get_current_user().get('email')
        )
        cdb.add(loan)
        cdb.commit()
        
        return jsonify({'success': True, 'message': 'Loan saved successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@app.route("/api/loan/repayment/save", methods=["POST"])
@login_required
@require_permission("loans", "create")
def save_loan_repayment():
    """Save a loan repayment"""
    cdb = get_cdb()
    company_id = get_current_company()
    data = request.get_json()
    
    try:
        loan_id = data.get('loan_id')
        loan = cdb.query(Loan).filter_by(id=loan_id, company_id=company_id).first()
        
        if not loan:
            return jsonify({'success': False, 'message': 'Loan not found'}), 404
        
        repayment = LoanRepayment(
            loan_id=loan.id,
            date=date.fromisoformat(data.get('date')),
            amount=data.get('amount'),
            payment_mode=data.get('payment_mode', 'Cash'),
            reference=data.get('reference', ''),
            notes=data.get('notes', '')
        )
        cdb.add(repayment)
        
        # Update loan status if fully repaid
        if loan.remaining_amount - repayment.amount <= 0:
            loan.status = 'Completed'
        
        cdb.commit()
        
        return jsonify({'success': True, 'message': 'Repayment recorded successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

# ============================================
# LEDGER & TRIAL BALANCE ROUTES
# ============================================

@app.route("/ledger")
@login_required
@require_permission("analytics", "view")
def ledger():
    """General Ledger sourced only from the central posted journal."""
    cdb = get_cdb()
    company_id = get_current_company()
    _ensure_journal_tables(cdb)
    _ensure_chart_of_accounts(cdb, company_id)

    from_date_str = request.args.get("from_date", "")
    to_date_str = request.args.get("to_date", "")
    account_id_raw = request.args.get("account_id", "")
    from_date = date.fromisoformat(from_date_str) if from_date_str else None
    to_date = date.fromisoformat(to_date_str) if to_date_str else None
    account_id = int(account_id_raw) if str(account_id_raw).isdigit() else None
    filter_applied = bool(from_date or to_date or account_id)

    q = cdb.query(JournalEntryLine, JournalEntry, ChartOfAccount).join(
        JournalEntry, JournalEntryLine.entry_id == JournalEntry.id
    ).join(
        ChartOfAccount, JournalEntryLine.account_id == ChartOfAccount.id
    ).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.status.in_(("Posted", "Reversed")),
    )
    if from_date:
        q = q.filter(JournalEntry.entry_date >= from_date)
    if to_date:
        q = q.filter(JournalEntry.entry_date <= to_date)
    if account_id:
        q = q.filter(ChartOfAccount.id == account_id)

    raw = q.order_by(JournalEntry.entry_date.asc(), JournalEntry.id.asc(),
                     JournalEntryLine.id.asc()).all()

    ledger_entries = []
    running_balance = Decimal("0.00")
    total_debits = Decimal("0.00")
    total_credits = Decimal("0.00")
    for line, entry, account in raw:
        debit, credit = _money(line.debit), _money(line.credit)
        total_debits += debit
        total_credits += credit
        # For a single account use its normal-balance convention; for the
        # all-account register show the signed debit-minus-credit movement.
        if account_id and account.normal_balance == "Credit":
            running_balance += credit - debit
        else:
            running_balance += debit - credit
        ledger_entries.append({
            "date": entry.entry_date,
            "voucher_type": entry.source_type.replace("_", " ").title(),
            "voucher_no": entry.entry_no,
            "party_name": f"{account.code} · {account.name}",
            "debit": float(debit),
            "credit": float(credit),
            "balance": float(running_balance),
            "type": entry.source_type,
            "reference": entry.reference,
            "description": line.description or entry.narration,
        })

    accounts = cdb.query(ChartOfAccount).filter_by(
        company_id=company_id, is_active=True
    ).order_by(ChartOfAccount.code).all()

    return render_template(
        "ledger.html", ledger_entries=ledger_entries,
        from_date=from_date, to_date=to_date,
        account_type="all", account_id=account_id, accounts=accounts,
        filter_applied=filter_applied,
        total_debits=float(total_debits), total_credits=float(total_credits),
        closing_balance=float(running_balance), active="ledger",
        report_basis="Central posted journal",
    )


@app.route("/trial-balance")
@login_required
@require_permission("analytics", "view")
def trial_balance():
    """Trial Balance derived from posted/reversed journal entries."""
    cdb = get_cdb()
    company_id = get_current_company()
    _ensure_journal_tables(cdb)
    _ensure_chart_of_accounts(cdb, company_id)

    try:
        as_on_date = date.fromisoformat(request.args.get("as_on_date", ""))
    except (TypeError, ValueError):
        as_on_date = today_ist()

    accounts_master = cdb.query(ChartOfAccount).filter_by(
        company_id=company_id, is_active=True
    ).order_by(ChartOfAccount.code).all()

    # SQLAlchemy returns 3 values per row here:
    # (account_id, total_debit, total_credit).
    # Build the mapping explicitly; dict(rows) only accepts 2-item rows.
    journal_sums = cdb.query(
        JournalEntryLine.account_id,
        func.coalesce(func.sum(JournalEntryLine.debit), 0),
        func.coalesce(func.sum(JournalEntryLine.credit), 0),
    ).join(
        JournalEntry, JournalEntryLine.entry_id == JournalEntry.id
    ).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.status.in_(("Posted", "Reversed")),
        JournalEntry.entry_date <= as_on_date,
    ).group_by(JournalEntryLine.account_id).all()

    sums = {
        account_id: (total_debit, total_credit)
        for account_id, total_debit, total_credit in journal_sums
    }

    account_list = []
    total_debits = Decimal("0.00")
    total_credits = Decimal("0.00")
    for acc in accounts_master:
        d, c = sums.get(acc.id, (Decimal("0.00"), Decimal("0.00")))
        d, c = _money(d), _money(c)
        opening = _money(acc.opening_balance)
        if opening:
            if acc.normal_balance == "Debit":
                d += opening
            else:
                c += opening
        net = d - c
        debit_balance = net if net > 0 else Decimal("0.00")
        credit_balance = -net if net < 0 else Decimal("0.00")
        if debit_balance or credit_balance:
            account_list.append({
                "name": f"{acc.code} · {acc.name}",
                "debit": float(debit_balance),
                "credit": float(credit_balance),
            })
            total_debits += debit_balance
            total_credits += credit_balance

    difference = total_debits - total_credits
    return render_template(
        "trial_balance.html", accounts=account_list,
        total_debits=float(total_debits), total_credits=float(total_credits),
        as_on_date=as_on_date, difference=float(difference),
        active="trial_balance", report_basis="Central posted journal",
    )


# ============================================
# REPORTS ROUTES
# ============================================

@app.route("/api/reports/sales-data")
@login_required
@require_permission("analytics", "view")
def api_sales_report_data():
    """API endpoint for sales report data supporting CustomerInvoice and Invoice."""
    cdb = get_cdb()
    if not cdb:
        return jsonify({"error": "Could not connect to company database"}), 500
    
    company_id = get_current_company()
    
    from_date_str = request.args.get('from_date', '')
    to_date_str = request.args.get('to_date', '')
    
    if not from_date_str:
        from_date = date(2000, 1, 1)
    else:
        from_date = date.fromisoformat(from_date_str)
    
    if not to_date_str:
        to_date = today_ist()
    else:
        to_date = date.fromisoformat(to_date_str)
    
    # 1. Fetch CustomerInvoice records
    ci_invoices = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.invoice_date >= from_date,
        CustomerInvoice.invoice_date <= to_date,
        CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft'])
    ).order_by(CustomerInvoice.invoice_date.desc()).all()

    # 2. Fetch legacy Invoice records
    legacy_invoices = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.date >= from_date,
        Invoice.date <= to_date,
        Invoice.status.notin_(['Cancelled', 'Void', 'Draft'])
    ).order_by(Invoice.date.desc()).all()

    unified_invoices = []
    
    for ci in ci_invoices:
        cust_name = ci.client_name
        if not cust_name and ci.client_obj:
            cust_name = ci.client_obj.name
        if not cust_name:
            cust_name = "Walk-in Customer"
        
        category_label = "Product Sales" if ci.invoice_category == "product_sale" else "Workshop Repair" if ci.invoice_category == "workshop_repair" else (ci.invoice_category or "Direct Sales").replace('_', ' ').title()
        
        items_list = []
        for item in ci.items:
            item_desc = item.item_name or item.item_description or item.item_code or "Product Item"
            items_list.append({
                "name": item_desc,
                "qty": float(item.quantity or 0),
                "hsn": item.hsn or ""
            })
            
        grand_total = float(ci.grand_total or 0)
        tax_amount = float(ci.tax_amount or 0)
        subtotal = float(ci.subtotal or (grand_total - tax_amount))
        paid_amount = float(ci.paid_amount or 0)
        balance = float(ci.balance if ci.balance is not None else (grand_total - paid_amount))

        unified_invoices.append({
            "id": ci.invoice_number,
            "date": ci.invoice_date,
            "date_str": ci.invoice_date.strftime('%d %b %Y'),
            "customer": cust_name,
            "destination": ci.client_state or category_label,
            "subtotal": subtotal,
            "tax": tax_amount,
            "total": grand_total,
            "paid": paid_amount,
            "balance": balance,
            "status": ci.status or 'Pending',
            "items": items_list,
            "category": category_label
        })

    for inv in legacy_invoices:
        meta = {}
        if inv.terms:
            try:
                meta = json.loads(inv.terms)
            except Exception:
                pass
        dest = meta.get('destination', 'Domestic')
        cust_name = inv.client_obj.name if inv.client_obj else (inv.contact_person or 'Unknown')
        grand_total = float(inv.grand_total or 0)
        tax_amount = float(inv.tax_amount or 0)
        subtotal = float(inv.subtotal or (grand_total - tax_amount))
        balance = float(getattr(inv, 'balance', 0) or 0)
        paid = grand_total - balance
        
        items_list = []
        for item in getattr(inv, 'items', []):
            item_desc = getattr(item, 'description', None) or getattr(item, 'code', None) or 'Unknown'
            items_list.append({
                "name": item_desc,
                "qty": float(getattr(item, 'qty', 0) or 0),
                "hsn": getattr(item, 'code', '')
            })

        unified_invoices.append({
            "id": inv.invoice_id,
            "date": inv.date,
            "date_str": inv.date.strftime('%d %b %Y') if inv.date else '',
            "customer": cust_name,
            "destination": dest,
            "subtotal": subtotal,
            "tax": tax_amount,
            "total": grand_total,
            "paid": paid,
            "balance": balance,
            "status": inv.status or 'Pending',
            "items": items_list,
            "category": dest
        })

    unified_invoices.sort(key=lambda x: x["date"] if x["date"] else date.min, reverse=True)

    # Calculate totals
    total_revenue = sum(i["total"] for i in unified_invoices)
    total_tax = sum(i["tax"] for i in unified_invoices)
    total_pending = sum(i["balance"] for i in unified_invoices)
    total_received = sum(i["paid"] for i in unified_invoices)
    
    # Monthly trend
    monthly_revenue = {}
    for inv in unified_invoices:
        if inv["date"]:
            month_key = inv["date"].strftime('%b %Y')
            monthly_revenue[month_key] = monthly_revenue.get(month_key, 0.0) + inv["total"]
    
    month_labels = list(monthly_revenue.keys())
    monthly_revenue_data = list(monthly_revenue.values())
    
    # Top destinations / categories
    destinations = {}
    for inv in unified_invoices:
        dest = inv.get('destination') or 'Direct'
        destinations[dest] = destinations.get(dest, 0) + 1
    
    top_destinations = [{'name': k, 'count': v} for k, v in sorted(destinations.items(), key=lambda x: x[1], reverse=True)[:5]]
    
    # Top products from invoice items
    products = {}
    for inv in unified_invoices:
        for item in inv.get('items', []):
            name = item.get('name') or 'General Service'
            products[name] = products.get(name, 0.0) + float(item.get('qty') or 0.0)
    
    top_products = [{'name': k, 'qty': v} for k, v in sorted(products.items(), key=lambda x: x[1], reverse=True)[:5]]
    
    # Top customers
    customers = {}
    for inv in unified_invoices:
        name = inv.get('customer') or 'Unknown'
        customers[name] = customers.get(name, 0.0) + inv["total"]
    
    top_customers = [{'name': k, 'amount': v} for k, v in sorted(customers.items(), key=lambda x: x[1], reverse=True)[:5]]
    
    # Status counts
    paid_count = sum(1 for i in unified_invoices if (i["status"] or '').lower() == 'paid')
    partial_count = sum(1 for i in unified_invoices if (i["status"] or '').lower() in ['partial', 'partially paid', 'partially_paid'])
    pending_count = sum(1 for i in unified_invoices if (i["status"] or '').lower() not in ['paid', 'partial', 'partially paid', 'partially_paid'])
    
    # Invoice list for table
    invoice_list = []
    for inv in unified_invoices[:100]:
        invoice_list.append({
            'id': inv['id'],
            'date': inv['date_str'],
            'customer': inv['customer'],
            'destination': inv['destination'],
            'subtotal': round(inv['subtotal'], 2),
            'tax': round(inv['tax'], 2),
            'total': round(inv['total'], 2),
            'status': inv['status']
        })
    
    return jsonify({
        'total_revenue': round(total_revenue, 2),
        'total_tax': round(total_tax, 2),
        'total_received': round(total_received, 2),
        'total_pending': round(total_pending, 2),
        'total_invoices': len(unified_invoices),
        'month_labels': month_labels,
        'monthly_revenue': [round(v, 2) for v in monthly_revenue_data],
        'top_destinations': top_destinations,
        'top_products': top_products,
        'top_customers': top_customers,
        'paid_count': paid_count,
        'partial_count': partial_count,
        'pending_count': pending_count,
        'invoices': invoice_list
    })


@app.route("/api/reports/purchase-data")
@login_required
@require_permission("analytics", "view")
def api_purchase_report_data():
    """API endpoint for purchase report data"""
    cdb = get_cdb()
    if not cdb:
        return jsonify({"error": "Could not connect to company database"}), 500
    
    company_id = get_current_company()
    
    from_date_str = request.args.get('from_date', '')
    to_date_str = request.args.get('to_date', '')
    
    if not from_date_str:
        from_date = date(2000, 1, 1)   # Show all records by default
    else:
        from_date = date.fromisoformat(from_date_str)
    
    if not to_date_str:
        to_date = today_ist()
    else:
        to_date = date.fromisoformat(to_date_str)

    purchases = cdb.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.date >= from_date,
        PurchaseInvoice.date <= to_date
    ).order_by(PurchaseInvoice.date.desc()).all()
    
    total_amount = sum(float(p.grand_total or 0) for p in purchases)
    total_gst = sum(float(p.tax_amount or 0) for p in purchases)
    total_paid = sum(float(p.paid_amount or 0) for p in purchases)
    total_pending = sum(float(p.balance or 0) for p in purchases)
    
    # Unique supplier count
    supplier_ids = set()
    for p in purchases:
        if p.supplier_id:
            supplier_ids.add(p.supplier_id)
    supplier_count = len(supplier_ids)
    
    # Monthly trend
    monthly_purchases = {}
    for p in purchases:
        month_key = p.date.strftime('%b %Y')
        monthly_purchases[month_key] = monthly_purchases.get(month_key, 0) + float(p.grand_total or 0)
    
    month_labels = list(monthly_purchases.keys())
    monthly_purchases_data = list(monthly_purchases.values())
    
    # Top suppliers
    suppliers = {}
    for p in purchases:
        try:
            name = p.supplier.name if p.supplier else (getattr(p, 'supplier_name', None) or 'Unknown')
        except Exception:
            name = getattr(p, 'supplier_name', None) or 'Unknown'
        suppliers[name] = suppliers.get(name, 0) + float(p.grand_total or 0)
    
    top_suppliers = [{'name': k, 'amount': v} for k, v in sorted(suppliers.items(), key=lambda x: x[1], reverse=True)[:5]]
    
    # Top purchased products
    products = {}
    for p in purchases:
        for item in p.items:
            name = item.description or 'Unknown'
            products[name] = products.get(name, 0) + float(item.quantity or 0)
    
    top_products = [{'name': k, 'qty': v} for k, v in sorted(products.items(), key=lambda x: x[1], reverse=True)[:5]]
    
    # Status counts
    paid_count = sum(1 for p in purchases if p.status == 'Paid')
    partial_count = sum(1 for p in purchases if p.status == 'Partial')
    pending_count = sum(1 for p in purchases if p.status not in ['Paid', 'Partial'])
    
    invoice_list = []
    for p in purchases[:50]:
        try:
            sup_name = p.supplier.name if p.supplier else (getattr(p, 'supplier_name', None) or '—')
        except Exception:
            sup_name = getattr(p, 'supplier_name', None) or '—'
        invoice_list.append({
            'id': p.invoice_id,
            'date': p.date.strftime('%d %b %Y'),
            'supplier': sup_name,
            'subtotal': float(p.subtotal or 0),
            'tax': float(p.tax_amount or 0),
            'total': float(p.grand_total or 0),
            'status': p.status or 'Pending'
        })
    
    return jsonify({
        'total_amount': total_amount,
        'total_gst': total_gst,
        'total_paid': total_paid,
        'total_pending': total_pending,
        'supplier_count': supplier_count,
        'month_labels': month_labels,
        'monthly_purchases': monthly_purchases_data,
        'top_suppliers': top_suppliers,
        'top_products': top_products,
        'paid_count': paid_count,
        'partial_count': partial_count,
        'pending_count': pending_count,
        'invoices': invoice_list
    })

@app.route("/api/reports/stock-data")
@login_required
@require_permission("analytics", "view")
def api_stock_report_data():
    """API endpoint for stock report data - reads directly from StockItem table"""
    cdb = get_cdb()
    if not cdb:
        return jsonify({"error": "Could not connect to company database"}), 500
    
    company_id = get_current_company()
    
    # Get ALL stock items directly from StockItem table
    stock_items = cdb.query(StockItem).filter_by(company_id=company_id).all()
    
    total_items = len(stock_items)
    
    # Calculate total value using purchase_rate or unit_price
    total_value = 0
    in_stock = 0
    low_stock = 0
    out_stock = 0
    
    categories = {}
    stock_list = []
    
    for s in stock_items:
        qty = float(s.quantity or 0)
        price = float(s.purchase_rate or s.unit_price or 0)
        total_value += price * qty
        
        # Status
        reorder = float(s.reorder_level or 10)
        if qty <= 0:
            out_stock += 1
            status = 'out'
            status_label = 'Out of Stock'
        elif qty <= reorder:
            low_stock += 1
            status = 'low'
            status_label = 'Low Stock'
        else:
            in_stock += 1
            status = 'in'
            status_label = 'In Stock'
        
        # Category
        cat = s.category or 'Uncategorized'
        categories[cat] = categories.get(cat, 0) + 1
        
        stock_list.append({
            'code': s.code,
            'name': s.name,
            'category': s.category or '—',
            'quantity': int(qty),
            'price': price,
            'total': price * qty,
            'status': status,
            'status_label': status_label,
            'unit': s.unit or 'pcs',
            'reorder_level': int(reorder)
        })
    
    # Top selling items (from InvoiceItem table - sales data)
    top_selling = {}
    invoices = cdb.query(Invoice).filter_by(company_id=company_id).all()
    for inv in invoices:
        for item in inv.items:
            name = item.description or item.code or 'Unknown'
            top_selling[name] = top_selling.get(name, 0) + float(item.qty or 0)
    
    top_selling_list = [{'name': k, 'qty': v} for k, v in sorted(top_selling.items(), key=lambda x: x[1], reverse=True)[:10]]
    
    return jsonify({
        'total_items': total_items,
        'total_value': total_value,
        'in_stock': in_stock,
        'low_stock': low_stock,
        'out_stock': out_stock,
        'category_count': len(categories),
        'categories': [{'name': k, 'count': v} for k, v in categories.items()],
        'top_selling': top_selling_list,
        'stock_items': stock_list
    })

@app.route("/api/reports/tax-data")
@login_required
@require_permission("analytics", "view")
def api_tax_report_data():
    cdb = get_cdb()
    if not cdb:
        return jsonify({"error": "Could not connect to company database"}), 500

    company_id = get_current_company()
    profile = tax_profile(get_company_by_id(company_id))
    
    from_date_str = request.args.get('from_date', '')
    to_date_str = request.args.get('to_date', '')
    
    if not from_date_str:
        from_date = today_ist().replace(day=1)
    else:
        from_date = date.fromisoformat(from_date_str)
    
    if not to_date_str:
        to_date = today_ist()
    else:
        to_date = date.fromisoformat(to_date_str)
    
    ci_sales = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.invoice_date >= from_date,
        CustomerInvoice.invoice_date <= to_date,
        CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft'])
    ).all()

    legacy_sales = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.date >= from_date,
        Invoice.date <= to_date,
        Invoice.status.notin_(['Cancelled', 'Void', 'Draft'])
    ).all()
    
    purchases = cdb.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.date >= from_date,
        PurchaseInvoice.date <= to_date
    ).all()
    
    output_gst = sum(float(i.tax_amount or 0) for i in ci_sales) + sum(float(i.tax_amount or 0) for i in legacy_sales)
    input_gst = sum(float(p.tax_amount or 0) for p in purchases)
    net_gst = output_gst - input_gst
    
    total_sales = sum(float(i.grand_total or 0) for i in ci_sales) + sum(float(i.grand_total or 0) for i in legacy_sales)
    effective_rate = (net_gst / total_sales * 100) if total_sales > 0 else 0
    
    total_cgst = sum(float(i.cgst_total or 0) for i in ci_sales)
    total_sgst = sum(float(i.sgst_total or 0) for i in ci_sales)
    total_igst = sum(float(i.igst_total or 0) for i in ci_sales)
    legacy_tax = sum(float(i.tax_amount or 0) for i in legacy_sales)
    if profile['is_gst'] and legacy_tax > 0:
        total_cgst += legacy_tax / 2
        total_sgst += legacy_tax / 2
    if profile['is_gst'] and total_cgst == 0 and total_sgst == 0 and total_igst == 0 and output_gst > 0:
        total_cgst = output_gst / 2
        total_sgst = output_gst / 2

    # Monthly GST
    monthly_gst = {}
    for inv in ci_sales:
        if inv.invoice_date:
            month_key = inv.invoice_date.strftime('%b %Y')
            monthly_gst[month_key] = monthly_gst.get(month_key, 0) + float(inv.tax_amount or 0)
    for inv in legacy_sales:
        if inv.date:
            month_key = inv.date.strftime('%b %Y')
            monthly_gst[month_key] = monthly_gst.get(month_key, 0) + float(inv.tax_amount or 0)
    
    # HSN Summary
    hsn_dict = {}
    for inv in ci_sales:
        for item in inv.items:
            hsn = (item.hsn or item.item_code or 'Other')[:8]
            desc = item.item_name or item.item_description or ''
            if hsn not in hsn_dict:
                hsn_dict[hsn] = {'hsn': hsn, 'description': desc, 'quantity': 0, 'value': 0, 'rate': float(item.gst_percent if item.gst_percent is not None else billing_rate(get_company_by_id(company_id))), 'cgst': 0, 'sgst': 0, 'igst': 0, 'total': 0}
            qty = float(item.quantity or 0)
            amount = float(item.taxable_amount or (qty * float(item.rate or 0)))
            item_cgst = float(item.cgst_amount or 0)
            item_sgst = float(item.sgst_amount or 0)
            item_igst = float(item.igst_amount or 0)
            gst = item_cgst + item_sgst + item_igst
            if gst == 0 and amount > 0:
                gst = amount * (float(item.gst_percent if item.gst_percent is not None else billing_rate(get_company_by_id(company_id))) / 100.0)
                item_cgst = gst / 2 if profile['is_gst'] else 0
                item_sgst = gst / 2 if profile['is_gst'] else 0
            hsn_dict[hsn]['quantity'] += qty
            hsn_dict[hsn]['value'] += amount
            hsn_dict[hsn]['cgst'] += item_cgst
            hsn_dict[hsn]['sgst'] += item_sgst
            hsn_dict[hsn]['igst'] += item_igst
            hsn_dict[hsn]['total'] += gst

    for inv in legacy_sales:
        for item in getattr(inv, 'items', []):
            code = getattr(item, 'code', None) or 'Other'
            hsn = code[:8]
            desc = getattr(item, 'description', '')
            if hsn not in hsn_dict:
                hsn_dict[hsn] = {'hsn': hsn, 'description': desc, 'quantity': 0, 'value': 0, 'rate': 0, 'cgst': 0, 'sgst': 0, 'igst': 0, 'total': 0}
            qty = float(getattr(item, 'qty', 0) or 0)
            rate = float(getattr(item, 'rate', 0) or 0)
            amount = qty * rate
            gst = amount * (float(inv.tax_amount or 0) / float(inv.subtotal or 1))
            hsn_dict[hsn]['quantity'] += qty
            hsn_dict[hsn]['value'] += amount
            hsn_dict[hsn]['cgst'] += gst / 2 if profile['is_gst'] else 0
            hsn_dict[hsn]['sgst'] += gst / 2 if profile['is_gst'] else 0
            hsn_dict[hsn]['total'] += gst
    hsn_summary = list(hsn_dict.values())
    if not profile['is_gst']:
        total_cgst = total_sgst = total_igst = 0
        for row in hsn_summary:
            row['cgst'] = row['sgst'] = row['igst'] = 0
    return jsonify({
        'tax_label': profile['label'], 'currency': profile['currency'], 'is_gst': profile['is_gst'],
        'output_gst': round(output_gst, 2),
        'input_gst': round(input_gst, 2),
        'net_gst': round(net_gst, 2),
        'effective_rate': round(effective_rate, 2),
        'month_labels': list(monthly_gst.keys()),
        'monthly_gst': [round(v, 2) for v in monthly_gst.values()],
        'cgst': round(total_cgst, 2),
        'sgst': round(total_sgst, 2),
        'igst': round(total_igst, 2),
        'hsn_summary': hsn_summary
    })


@app.route("/api/reports/financial-data")
@login_required
@require_permission("analytics", "view")
def api_financial_report_data():
    """API endpoint for financial report data"""
    cdb = get_cdb()
    if not cdb:
        return jsonify({"error": "Could not connect to company database"}), 500
    
    company_id = get_current_company()
    
    from_date_str = request.args.get('from_date', '')
    to_date_str = request.args.get('to_date', '')
    
    if not from_date_str:
        from_date = today_ist().replace(day=1)
    else:
        from_date = date.fromisoformat(from_date_str)
    
    if not to_date_str:
        to_date = today_ist()
    else:
        to_date = date.fromisoformat(to_date_str)
    
    # ── INCOME ───────────────────────────────────────────────────────────────
    # 1. Sales Revenue (CustomerInvoice + legacy Invoice)
    ci_sales = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.invoice_date >= from_date,
        CustomerInvoice.invoice_date <= to_date,
        CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft'])
    ).all()
    legacy_sales = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.date >= from_date,
        Invoice.date <= to_date,
        Invoice.status.notin_(['Cancelled', 'Void', 'Draft'])
    ).all()
    sales_income = sum(float(i.grand_total or 0) for i in ci_sales) + sum(float(i.grand_total or 0) for i in legacy_sales)
    
    # 2. Other Income (Cash Transactions - income type)
    other_income = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        CashTransaction.type == 'income',
        CashTransaction.date >= from_date,
        CashTransaction.date <= to_date
    ).all()
    other_income_total = sum(t.amount for t in other_income)
    
    total_income = sales_income + other_income_total
    
    # ── EXPENSES ─────────────────────────────────────────────────────────────
    # 1. Cost of Goods Sold (Purchases)
    purchases = cdb.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.date >= from_date,
        PurchaseInvoice.date <= to_date
    ).all()
    purchase_expense = sum(float(p.grand_total or 0) for p in purchases)
    
    # 2. Operating Expenses (from Expense table)
    operating_expenses = cdb.query(Expense).filter(
        Expense.company_id == company_id,
        Expense.date >= from_date,
        Expense.date <= to_date
    ).all()
    operating_expense_total = sum(e.amount for e in operating_expenses)
    
    # 3. Cash Transaction Expenses
    cash_expenses = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        CashTransaction.type == 'expense',
        CashTransaction.date >= from_date,
        CashTransaction.date <= to_date
    ).all()
    cash_expense_total = sum(t.amount for t in cash_expenses)
    
    # Total Expenses = Purchases + Operating Expenses + Cash Expenses
    total_expenses = purchase_expense + operating_expense_total + cash_expense_total
    
    # ── PROFIT ────────────────────────────────────────────────────────────────
    net_profit = total_income - total_expenses
    profit_margin = (net_profit / total_income * 100) if total_income > 0 else 0
    
    # ── MONTHLY BREAKDOWN ────────────────────────────────────────────────────
    monthly_income = {}
    monthly_expenses = {}
    
    # Monthly income from sales
    for inv in ci_sales:
        if inv.invoice_date:
            month_key = inv.invoice_date.strftime('%b %Y')
            monthly_income[month_key] = monthly_income.get(month_key, 0) + float(inv.grand_total or 0)
    for inv in legacy_sales:
        if inv.date:
            month_key = inv.date.strftime('%b %Y')
            monthly_income[month_key] = monthly_income.get(month_key, 0) + float(inv.grand_total or 0)
    
    # Monthly expenses from purchases
    for p in purchases:
        month_key = p.date.strftime('%b %Y')
        monthly_expenses[month_key] = monthly_expenses.get(month_key, 0) + float(p.grand_total or 0)
    
    # Monthly expenses from Expense table
    for e in operating_expenses:
        month_key = e.date.strftime('%b %Y')
        monthly_expenses[month_key] = monthly_expenses.get(month_key, 0) + e.amount
    
    # Monthly expenses from CashTransaction expenses
    for t in cash_expenses:
        month_key = t.date.strftime('%b %Y')
        monthly_expenses[month_key] = monthly_expenses.get(month_key, 0) + t.amount
    
    all_months = set(monthly_income.keys()) | set(monthly_expenses.keys())
    sorted_months = sorted(all_months, key=lambda x: datetime.strptime(x, '%b %Y'))
    
    monthly_profit = {}
    for m in sorted_months:
        monthly_profit[m] = monthly_income.get(m, 0) - monthly_expenses.get(m, 0)
    
    # ── CASH AND BANK BALANCES ──────────────────────────────────────────────
    # Cash balance from CashTransaction
    all_cash_txns = cdb.query(CashTransaction).filter_by(company_id=company_id).all()
    cash_balance = sum(t.amount for t in all_cash_txns if t.type == 'income') - sum(t.amount for t in all_cash_txns if t.type == 'expense')
    
    # Bank balance
    bank_accounts = cdb.query(BankAccount).filter_by(company_id=company_id, status='Active').all()
    bank_balance = sum(acc.balance for acc in bank_accounts)
    
    # ── EXPENSE BREAKDOWN BY CATEGORY ──────────────────────────────────────
    expense_breakdown = {}
    
    # From Expense table
    for e in operating_expenses:
        expense_breakdown[e.category] = expense_breakdown.get(e.category, 0) + e.amount
    
    # Add purchases as a category
    if purchase_expense > 0:
        expense_breakdown['Purchases (COGS)'] = purchase_expense
    
    # Add cash expenses by category
    for t in cash_expenses:
        cat = t.category or 'Misc'
        expense_breakdown[cat] = expense_breakdown.get(cat, 0) + t.amount
    
    # ── CASH FLOW ENTRIES ────────────────────────────────────────────────────
    cashflow = []
    
    # Income entries
    for inv in ci_sales[:15]:
        cashflow.append({
            'date': inv.invoice_date.strftime('%d %b %Y') if inv.invoice_date else '',
            'type': 'income',
            'category': 'Sales',
            'description': f"Invoice {inv.invoice_number}",
            'amount': float(inv.grand_total or 0),
            'mode': 'Invoice'
        })
    for inv in legacy_sales[:10]:
        cashflow.append({
            'date': inv.date.strftime('%d %b %Y') if inv.date else '',
            'type': 'income',
            'category': 'Sales',
            'description': f"Invoice {inv.invoice_id}",
            'amount': float(inv.grand_total or 0),
            'mode': 'Credit'
        })
    
    # Expense entries from Expense table
    for e in operating_expenses[:20]:
        cashflow.append({
            'date': e.date.strftime('%d %b %Y'),
            'type': 'expense',
            'category': e.category,
            'description': e.description or e.category,
            'amount': e.amount,
            'mode': e.payment_mode or 'Cash'
        })
    
    # Cash transaction expenses
    for t in cash_expenses[:10]:
        cashflow.append({
            'date': t.date.strftime('%d %b %Y'),
            'type': 'expense',
            'category': t.category,
            'description': t.description,
            'amount': t.amount,
            'mode': 'Cash'
        })
    
    cashflow.sort(key=lambda x: x['date'], reverse=True)
    
    return jsonify({
        'total_income': round(total_income, 2),
        'total_expenses': round(total_expenses, 2),
        'net_profit': round(net_profit, 2),
        'profit_margin': round(profit_margin, 2),
        'month_labels': sorted_months,
        'monthly_income': [round(monthly_income.get(m, 0), 2) for m in sorted_months],
        'monthly_expenses': [round(monthly_expenses.get(m, 0), 2) for m in sorted_months],
        'monthly_profit': [round(monthly_profit.get(m, 0), 2) for m in sorted_months],
        'cash_balance': round(cash_balance, 2),
        'bank_balance': round(bank_balance, 2),
        'expense_breakdown': expense_breakdown,
        'cashflow': cashflow
    })

@app.route("/reports/profit-loss")
@login_required
@require_permission("analytics", "view")
def profit_loss():
    """Profit & Loss sourced from Income and Expense journal accounts."""
    cdb = get_cdb()
    company_id = get_current_company()
    _ensure_journal_tables(cdb)
    _ensure_chart_of_accounts(cdb, company_id)

    period = request.args.get("period", "month")
    today = today_ist()
    if period == "quarter":
        first_month = ((today.month - 1) // 3) * 3 + 1
        from_date, to_date = date(today.year, first_month, 1), today
    elif period == "year":
        from_date, to_date = date(today.year, 1, 1), today
    elif period == "custom":
        try: from_date = date.fromisoformat(request.args.get("from_date", ""))
        except (TypeError, ValueError): from_date = today.replace(day=1)
        try: to_date = date.fromisoformat(request.args.get("to_date", ""))
        except (TypeError, ValueError): to_date = today
    else:
        period = "month"
        from_date, to_date = today.replace(day=1), today

    rows = cdb.query(
        ChartOfAccount,
        func.coalesce(func.sum(JournalEntryLine.debit), 0),
        func.coalesce(func.sum(JournalEntryLine.credit), 0),
    ).join(
        JournalEntryLine, JournalEntryLine.account_id == ChartOfAccount.id
    ).join(
        JournalEntry, JournalEntryLine.entry_id == JournalEntry.id
    ).filter(
        ChartOfAccount.company_id == company_id,
        ChartOfAccount.account_type.in_(("Income", "Expense")),
        JournalEntry.company_id == company_id,
        JournalEntry.status.in_(("Posted", "Reversed")),
        JournalEntry.entry_date >= from_date,
        JournalEntry.entry_date <= to_date,
    ).group_by(ChartOfAccount.id).order_by(ChartOfAccount.code).all()

    operating_revenue = Decimal("0.00")
    other_income = Decimal("0.00")
    cogs = Decimal("0.00")
    expense_categories = {}
    for acc, debit, credit in rows:
        d, c = _money(debit), _money(credit)
        if acc.account_type == "Income":
            amount = c - d
            if acc.code == "4300" or "other income" in (acc.account_group or "").lower():
                other_income += amount
            else:
                operating_revenue += amount
        else:
            amount = d - c
            if acc.code in ("5000", "5100") or "cost of goods" in (acc.account_group or "").lower():
                cogs += amount
            else:
                expense_categories[acc.name] = round(float(amount), 2)

    total_expenses = Decimal(str(round(sum(expense_categories.values()), 2)))
    gross_profit = operating_revenue - cogs
    net_profit = gross_profit + other_income - total_expenses
    gross_margin = float(gross_profit / operating_revenue * 100) if operating_revenue else 0
    net_margin = float(net_profit / operating_revenue * 100) if operating_revenue else 0

    return render_template(
        "profit_loss.html", active="profit_loss", period=period,
        from_date=from_date, to_date=to_date,
        total_revenue=float(operating_revenue), cost_of_goods_sold=float(cogs),
        gross_profit=float(gross_profit), other_income=float(other_income),
        expense_categories=expense_categories, total_expenses=float(total_expenses),
        net_profit=float(net_profit), gross_margin=gross_margin,
        net_margin=net_margin, today=today,
        report_basis="Central posted journal",
    )


@app.route("/reports/balance-sheet")
@login_required
@require_permission("analytics", "view")
def balance_sheet():
    """Balance Sheet sourced from Asset/Liability/Equity journal accounts."""
    cdb = get_cdb()
    company_id = get_current_company()
    _ensure_journal_tables(cdb)
    _ensure_chart_of_accounts(cdb, company_id)
    try:
        as_on_date = date.fromisoformat(request.args.get("as_on_date", ""))
    except (TypeError, ValueError):
        as_on_date = today_ist()

    # Aggregate only qualifying journal rows first.  This prevents Draft or
    # future-dated JournalEntryLine rows from surviving an outer join merely
    # because their parent JournalEntry failed the status/date condition.
    journal_totals = cdb.query(
        JournalEntryLine.account_id.label("account_id"),
        func.coalesce(func.sum(JournalEntryLine.debit), 0).label("total_debit"),
        func.coalesce(func.sum(JournalEntryLine.credit), 0).label("total_credit"),
    ).join(
        JournalEntry, JournalEntryLine.entry_id == JournalEntry.id
    ).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.status.in_(("Posted", "Reversed")),
        JournalEntry.entry_date <= as_on_date,
    ).group_by(JournalEntryLine.account_id).subquery()

    rows = cdb.query(
        ChartOfAccount,
        func.coalesce(journal_totals.c.total_debit, 0),
        func.coalesce(journal_totals.c.total_credit, 0),
    ).outerjoin(
        journal_totals, journal_totals.c.account_id == ChartOfAccount.id
    ).filter(
        ChartOfAccount.company_id == company_id,
        ChartOfAccount.account_type.in_(("Asset", "Liability", "Equity")),
        ChartOfAccount.is_active == True,
    ).order_by(ChartOfAccount.code).all()

    assets, liabilities, equity = {}, {}, {}
    for acc, debit, credit in rows:
        d, c = _money(debit), _money(credit)
        opening = _money(acc.opening_balance)
        if opening:
            if acc.normal_balance == "Debit": d += opening
            else: c += opening
        amount = (d - c) if acc.account_type == "Asset" else (c - d)
        if not amount:
            continue
        label = f"{acc.code} · {acc.name}"
        if acc.account_type == "Asset": assets[label] = float(amount)
        elif acc.account_type == "Liability": liabilities[label] = float(amount)
        else: equity[label] = float(amount)

    # Current-period cumulative profit/loss belongs in equity on a balance sheet.
    pnl = cdb.query(
        ChartOfAccount.account_type,
        func.coalesce(func.sum(JournalEntryLine.debit), 0),
        func.coalesce(func.sum(JournalEntryLine.credit), 0),
    ).join(JournalEntryLine, JournalEntryLine.account_id == ChartOfAccount.id
    ).join(JournalEntry, JournalEntryLine.entry_id == JournalEntry.id
    ).filter(
        ChartOfAccount.company_id == company_id,
        ChartOfAccount.account_type.in_(("Income", "Expense")),
        JournalEntry.company_id == company_id,
        JournalEntry.status.in_(("Posted", "Reversed")),
        JournalEntry.entry_date <= as_on_date,
    ).group_by(ChartOfAccount.account_type).all()
    retained = Decimal("0.00")
    for typ, debit, credit in pnl:
        d, c = _money(debit), _money(credit)
        retained += (c - d) if typ == "Income" else -(d - c)
    if retained:
        equity["Current Earnings"] = float(retained)

    total_assets = round(sum(assets.values()), 2)
    total_liabilities = round(sum(liabilities.values()), 2)
    total_equity = round(sum(equity.values()), 2)
    combined = dict(liabilities)
    combined.update(equity)

    return render_template(
        "balance_sheet.html", active="balance_sheet", as_on_date=as_on_date,
        assets=assets, liabilities=combined,
        total_assets=total_assets, total_liabilities=total_liabilities,
        estimated_equity=total_equity,
        total_liabilities_equity=round(total_liabilities + total_equity, 2),
        balance_difference=round(total_assets - total_liabilities - total_equity, 2),
        report_basis="Central posted journal",
    )


@app.route("/reports/cash-flow")
@login_required
@require_permission("analytics", "view")
def cash_flow():
    """Cash Flow sourced from Cash/Bank journal lines."""
    cdb = get_cdb()
    company_id = get_current_company()
    _ensure_journal_tables(cdb)
    _ensure_chart_of_accounts(cdb, company_id)
    today = today_ist()
    try: from_date = date.fromisoformat(request.args.get("from_date", ""))
    except (TypeError, ValueError): from_date = today.replace(day=1)
    try: to_date = date.fromisoformat(request.args.get("to_date", ""))
    except (TypeError, ValueError): to_date = today

    cash_codes = ("1100", "1200")
    q = cdb.query(JournalEntryLine, JournalEntry, ChartOfAccount).join(
        JournalEntry, JournalEntryLine.entry_id == JournalEntry.id
    ).join(
        ChartOfAccount, JournalEntryLine.account_id == ChartOfAccount.id
    ).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.status.in_(("Posted", "Reversed")),
        JournalEntry.entry_date >= from_date,
        JournalEntry.entry_date <= to_date,
        ChartOfAccount.code.in_(cash_codes),
    ).order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc())

    rows = []
    inflow = Decimal("0.00")
    outflow = Decimal("0.00")
    for line, entry, account in q.all():
        debit, credit = _money(line.debit), _money(line.credit)
        inflow += debit
        outflow += credit
        rows.append({
            "date": entry.entry_date,
            "source": account.name,
            "description": line.description or entry.narration,
            "category": entry.source_type.replace("_", " ").title(),
            "inflow": float(debit),
            "outflow": float(credit),
        })

    # Opening cash/bank position = COA opening balances plus all posted
    # cash/bank movements before the selected period.
    cash_accounts = cdb.query(ChartOfAccount).filter(
        ChartOfAccount.company_id == company_id,
        ChartOfAccount.code.in_(cash_codes),
        ChartOfAccount.is_active == True,
    ).all()
    cash_account_ids = [a.id for a in cash_accounts]
    opening_cash = sum((_money(a.opening_balance) for a in cash_accounts), Decimal("0.00"))
    if cash_account_ids:
        prior = cdb.query(
            func.coalesce(func.sum(JournalEntryLine.debit), 0),
            func.coalesce(func.sum(JournalEntryLine.credit), 0),
        ).join(
            JournalEntry, JournalEntryLine.entry_id == JournalEntry.id
        ).filter(
            JournalEntry.company_id == company_id,
            JournalEntry.status.in_(("Posted", "Reversed")),
            JournalEntry.entry_date < from_date,
            JournalEntryLine.account_id.in_(cash_account_ids),
        ).first()
        if prior:
            opening_cash += _money(prior[0]) - _money(prior[1])
    closing_cash = opening_cash + inflow - outflow

    return render_template(
        "cash_flow.html", active="cash_flow",
        from_date=from_date, to_date=to_date, rows=rows,
        total_inflow=float(inflow), total_outflow=float(outflow),
        net_cash_flow=float(inflow - outflow),
        opening_cash_balance=float(opening_cash),
        closing_cash_balance=float(closing_cash),
        report_basis="Central posted journal — Cash and Bank accounts",
    )


# ============================================
# SYNC, SHARE & BACKUP ROUTES
# ============================================

@app.route("/sync")
@login_required
def sync_data():
    """Sync data with cloud"""
    company_id = get_current_company()
    return render_template("sync.html", active='sync')


@app.route("/share")
@login_required
def share_data():
    """Share data with others"""
    company_id = get_current_company()
    return render_template("share.html", active='share')

# ============================================
# OTHER PRODUCTS ROUTES
# ============================================

@app.route("/integrations")
@login_required
def integrations():
    """Third-party integrations"""
    company_id = get_current_company()
    return render_template("integrations.html", active='integrations')

@app.route("/addons")
@login_required
def addons():
    """Add-ons marketplace"""
    company_id = get_current_company()
    return render_template("addons.html", active='addons')

# ============================================
# UTILITIES ROUTES
# ============================================

@app.route("/import")
@login_required
def import_data():
    """Import data from files"""
    company_id = get_current_company()
    return render_template("import.html", active='import')

@app.route("/export")
@login_required
def export_data():
    """Export data to files"""
    company_id = get_current_company()
    return render_template("export.html", active='export')

@app.route("/audit-log")
@login_required
def audit_log():
    """View audit logs"""
    company_id = get_current_company()
    return render_template("audit_log.html", active='audit')

# ─────────────────────────────────────────────────────────────────────────────
# ── Profile ───────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/profile")
@login_required
def profile():
    user = get_current_user()
    return render_template("profile.html", user=user)


# ─────────────────────────────────────────────────────────────────────────────
# ── Company Settings ──────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────


@app.route("/company/settings")
@login_required
@owner_required
def company_settings():
    company_id = get_current_company()
    company = get_company_by_id(company_id)
    owner_email = get_current_user().get("email", "").strip().lower()

    cdb = get_cdb()
    if not cdb:
        flash("Could not connect to company database")
        return redirect(url_for("dashboard"))

    users = cdb.query(CompanyUser).filter_by(company_id=company_id).all()

    owner_companies = get_owner_companies(owner_email)
    from module_access import company_has_hr_access
    company_hr_access = {c.company_id: company_has_hr_access(c) for c in owner_companies}
    hr_available = company_has_hr_access(company)
    owner_user_count, owner_max_users, owner_user_emails = get_owner_user_stats(owner_email)

    user_access_map = {}
    for c in owner_companies:
        try:
            _cdb = get_customer_session(c.company_id)
            for u in _cdb.query(CompanyUser).filter_by(is_active=True).all():
                key = (u.email or "").strip().lower()
                if not key:
                    continue
                entry = user_access_map.setdefault(key, {"full_name": u.full_name, "companies": []})
                entry["companies"].append({
                    "company_id": c.company_id,
                    "company_name": c.company_name,
                    "role": u.role,
                })
        except Exception as e:
            print(f"⚠  Could not read users for {c.company_id}: {e}")

    plans = get_all_plans()

    current_plan = plans.get(company.subscription_plan) if company else None

    # ── Permission matrix data for the "Access" tab ──────────────────────────
    role_permissions = {
        role: perms_module.get_effective_permissions(
            role, company_id, None, cdb, CompanyRolePermission, CompanyUser
        )
        for role in ALLOWED_COMPANY_ROLES
    }
    
    user_permissions = {}
    for u in users:
        if u.role in ("owner", "super_admin"):
            continue
        user_permissions[u.user_id] = perms_module.get_effective_permissions(
            u.role, company_id, u.user_id, cdb, CompanyRolePermission, CompanyUser
        )

    # ── Field-level permissions for the "Access" tab ──────────────────────────
    from permissions import INVOICE_FIELDS, DEFAULT_FIELD_PERMISSIONS, get_field_permissions
    
    # Get field permissions for each role (role defaults)
    role_field_permissions = {}
    for role in ALLOWED_COMPANY_ROLES:
        perms = get_field_permissions(role, None, company_id, cdb)
        # Ensure all fields have view/edit keys
        for key in INVOICE_FIELDS:
            if key not in perms:
                perms[key] = {"view": True, "edit": False}
        role_field_permissions[role] = perms
    
    # Get field permissions for each user (user overrides)
    user_field_permissions = {}
    for u in users:
        if u.role in ("owner", "super_admin"):
            continue
        perms = get_field_permissions(u.role, u.user_id, company_id, cdb)
        for key in INVOICE_FIELDS:
            if key not in perms:
                perms[key] = {"view": True, "edit": False}
        user_field_permissions[u.user_id] = perms

    # ── API Keys ──────────────────────────────────────────────────────────────

    return render_template("company_settings.html",
                           company=company,
                           users=users,
                           plans=plans,
                           current_plan=current_plan,
                           owner_companies=owner_companies,
                           owner_user_count=owner_user_count,
                           owner_max_users=owner_max_users,
                           user_access_map=user_access_map,
                           allowed_roles=ALLOWED_COMPANY_ROLES,
                           hr_roles=perms_module.HR_ROLES if hr_available else {},
                           all_hr_roles=perms_module.HR_ROLES,
                           company_hr_access=company_hr_access,
                           perm_modules=[m for m in perms_module.MODULES if hr_available or m not in perms_module.HR_MODULES],
                           perm_actions=perms_module.ACTIONS,
                           perm_labels=perms_module.MODULE_LABELS,
                           role_permissions=role_permissions,
                           user_permissions=user_permissions,
                           invoice_fields=INVOICE_FIELDS,
                           role_field_permissions=role_field_permissions,
                           user_field_permissions=user_field_permissions,
                           )

def _read_permission_matrix_from_form(previous=None):
    matrix = {}
    from module_access import company_has_hr_access
    hr_available = company_has_hr_access(get_company_by_id(get_current_company()))
    try:
        old = json.loads(previous or '{}')
    except (ValueError, TypeError):
        old = {}
    for module in perms_module.MODULES:
        if module in perms_module.HR_MODULES and not hr_available:
            if any(request.form.get(f"perm__{module}__{a}") == "on" for a in perms_module.ACTIONS):
                abort(403, "HR & Payroll is not included in this company's subscription.")
            if isinstance(old, dict) and module in old:
                matrix[module] = old[module]
            continue
        matrix[module] = {
            action: (request.form.get(f"perm__{module}__{action}") == "on")
            for action in perms_module.ACTIONS
        }
    return matrix


@app.route("/company/permissions/role/<role>", methods=["POST"])
@login_required
@owner_required
def save_role_permissions(role):
    if role not in ("employee", "accountant", "manager"):
        flash("Invalid role")
        return redirect(url_for("company_settings"))
    company_id = get_current_company()
    cdb = get_customer_session(company_id)
    row = cdb.query(CompanyRolePermission).filter_by(company_id=company_id, role=role).first()
    if not row:
        row = CompanyRolePermission(company_id=company_id, role=role)
        cdb.add(row)
    row.permissions_json = json.dumps(_read_permission_matrix_from_form(row.permissions_json))
    row.updated_at = datetime.utcnow()
    cdb.commit()
    flash(f"{role.title()} access updated")
    return redirect(url_for("company_settings"))


@app.route("/company/permissions/user/<user_id>", methods=["POST"])
@login_required
@owner_required
def save_user_permissions(user_id):
    company_id = get_current_company()
    cdb = get_customer_session(company_id)
    cu = cdb.query(CompanyUser).filter_by(user_id=user_id, company_id=company_id).first()
    if not cu:
        flash("User not found")
        return redirect(url_for("company_settings"))
    if cu.role in ("owner", "super_admin"):
        flash("Owner access can't be limited this way")
        return redirect(url_for("company_settings"))
    if cu.role != 'bi_developer' and any(request.form.get(f'perm__analytics__{a}') == 'on' for a in perms_module.ACTIONS):
        abort(403, 'Only a BI Developer can receive Business Intelligence access.')
    cu.permission_overrides = json.dumps(_read_permission_matrix_from_form(cu.permission_overrides))
    cdb.commit()
    flash(f"Access updated for {cu.full_name}")
    return redirect(url_for("company_settings"))

# Add to app.py

@app.route("/settings/whatsapp", methods=["GET", "POST"])
@login_required
@owner_required
def whatsapp_settings():
    from whatsapp_service import encrypt_secret
    from platform_models import WhatsAppTemplate
    import json as _json

    company_id = get_current_company()
    company = get_company_by_id(company_id)
    if not company:
        flash("Company not found")
        return redirect(url_for("dashboard"))

    # (template_key, form field prefix)
    EVENTS = [
        ("invoice_created", "tpl_invoice_created"),
        ("invoice_updated", "tpl_invoice_updated"),
        ("tracking_number_updated", "tpl_tracking_number_updated"),
    ]

    if request.method == "POST":
        raw_key = request.form.get("whatsapp_api_key", "").strip()
        provider = request.form.get("whatsapp_provider", "").strip()
        base_url = request.form.get("whatsapp_base_url", "").strip()
        
        # Save API Key (encrypted)
        if raw_key:
            company.whatsapp_api_key = encrypt_secret(raw_key)
            company.whatsapp_enabled = True
        elif not company.whatsapp_api_key:
            company.whatsapp_enabled = False
        
        # Save provider
        if provider:
            company.whatsapp_provider = provider
        
        # Save Base URL (NEW!)
        if base_url:
            company.whatsapp_base_url = base_url
        elif not base_url and company.whatsapp_provider == 'mobicomm':
            # Set default for MobiCOMM
            company.whatsapp_base_url = 'https://api.dovesoft.io/REST/directApi/message'
        
        # Save Business Number
        business_no = request.form.get("whatsapp_business_no", "").strip()
        if business_no:
            company.whatsapp_business_no = business_no

        # Save Templates — one WhatsAppTemplate row per event. template_name
        # is a free-text Meta/provider template name (must match the approved
        # name exactly). The variable list is fixed (not user-editable) —
        # order here = param order sent to the provider (slot 1, slot 2, ...):
        #   1. receiver_name -> client.name
        #   2. docket_no     -> invoice.docket_no
        #   3. date          -> invoice.date
        #   4. phone         -> company.phone
        HARDCODED_VARS = [
            "{{ receiver.name }}",
            "{{ invoice.docket_no }}",
            "{{ invoice.date }}",
            "{{ company.phone }}",
        ]
        for event_key, prefix in EVENTS:
            tpl_name = request.form.get(f"{prefix}_name", "").strip()

            tpl = WhatsAppTemplate.query.filter_by(
                company_id=company_id, template_key=event_key
            ).first()

            if not tpl_name:
                # Blank name = "not configured" for this event. Deactivate
                # rather than delete, so re-adding the name later doesn't
                # require re-typing anything.
                if tpl:
                    tpl.is_active = False
                continue

            if not tpl:
                tpl = WhatsAppTemplate(company_id=company_id, template_key=event_key, template_name=tpl_name)
                db.session.add(tpl)

            tpl.template_name = tpl_name
            tpl.variables_json = _json.dumps(HARDCODED_VARS)
            tpl.param_count = len(HARDCODED_VARS)
            tpl.is_active = True

        db.session.commit()
        flash("WhatsApp Connect settings saved.")
        return redirect(url_for("whatsapp_settings"))

    # GET: load existing per-event template name to pre-fill the form
    existing = {}
    for event_key, prefix in EVENTS:
        tpl = WhatsAppTemplate.query.filter_by(
            company_id=company_id, template_key=event_key, is_active=True
        ).first()
        existing[event_key] = {
            "prefix": prefix,
            "template_name": tpl.template_name if tpl else "",
        }

    return render_template(
        "settings_whatsapp.html",
        company=company,
        has_key=bool(company.whatsapp_api_key),
        active="whatsapp_settings",
        events=existing,
    )


@app.route("/settings/whatsapp/disconnect", methods=["POST"])
@login_required
@owner_required
def whatsapp_disconnect():
    company_id = get_current_company()
    company = get_company_by_id(company_id)
    if company:
        company.whatsapp_api_key = None
        company.whatsapp_enabled = False
        company.whatsapp_provider = None
        company.whatsapp_base_url = None
        db.session.commit()
        flash("WhatsApp disconnected.")
    return redirect(url_for("whatsapp_settings"))


@app.route("/settings/whatsapp/test", methods=["POST"])
@login_required
@owner_required
def whatsapp_test():
    from whatsapp_service import _send_whatsapp_template as send_whatsapp_template, decrypt_secret
    from datetime import datetime

    company_id = get_current_company()
    company = get_company_by_id(company_id)
    
    if not company or not company.whatsapp_enabled:
        flash("WhatsApp is not configured.")
        return redirect(url_for("whatsapp_settings"))

    test_phone = request.form.get("test_phone", "").strip()
    if not test_phone:
        flash("Please enter a phone number.")
        return redirect(url_for("whatsapp_settings"))

    # Format phone
    test_phone = ''.join(filter(str.isdigit, test_phone))
    if len(test_phone) == 10:
        test_phone = "91" + test_phone

    # Send test using configured template
    template_name = company.whatsapp_template_generate or "alhamamd1001"
    
    result = send_whatsapp_template(
        company=company,
        to_number=test_phone,
        template_name=template_name,
        params=[
            "TEST123",  # docket
            datetime.now().strftime("%d-%b-%Y"),  # date
            company.phone or "9876543210",  # phone
        ]
    )
    
    if result.get('success'):
        flash(f"✅ Test message sent successfully to {test_phone}!")
    else:
        flash(f"❌ Test failed: {result.get('error')}")
    
    return redirect(url_for("whatsapp_settings"))

@app.route("/company/update-info", methods=["POST"])
@login_required
@owner_required
def update_company_info():
    company_id = get_current_company()
    company    = get_company_by_id(company_id)
    if company:
        new_name = request.form.get("company_name", company.company_name).strip()
        branch_name = request.form.get("branch_name", company.branch_name or "").strip()
        if not new_name or len(branch_name) > 100:
            flash("Company name is required and branch name must be 100 characters or fewer.", "error")
            return redirect(url_for("company_settings"))
        if is_company_name_taken(company.owner_email, new_name, company_id, branch_name):
            flash("This company and branch already exist. Please use a different branch name.", "error")
            return redirect(url_for("company_settings"))
        plan = get_plan(company.subscription_plan)
        if plan.get('max_branches') is not None:
            from plan_catalog import check_location_limits
            others = [c for c in get_owner_companies(company.owner_email) if c.company_id != company_id]
            allowed, message = check_location_limits(others, new_name, branch_name,
                                                     plan['max_companies'], plan['max_branches'])
            if not allowed:
                flash(message, 'error')
                return redirect(url_for('company_settings'))
        company.branch_name = branch_name or None
        company.company_name = request.form.get("company_name", company.company_name).strip()
        company.address      = request.form.get("address",      company.address)
        company.phone        = request.form.get("phone",        company.phone)
        company.mobile       = request.form.get("mobile",       company.mobile)
        company.slogan       = request.form.get("slogan",       company.slogan)
        company.website      = request.form.get("website",      company.website)
        company.email        = request.form.get("email",        company.email)
        company.extra_info   = request.form.get("extra_info",   company.extra_info)

        # ── Public tracking page slug ──
        # Normalize so "Acme Logistics!" -> "acme-logistics" instead of rejecting
        # the input outright — most owners won't type a URL-safe string unprompted.
        raw_slug = request.form.get("public_slug", "").strip()
        if raw_slug:
            slug = re.sub(r"[^a-z0-9-]", "-", raw_slug.lower())
            slug = re.sub(r"-+", "-", slug).strip("-")
            existing = Company.query.filter(
                Company.public_slug == slug, Company.id != company.id
            ).first()
            if existing:
                flash(f"The slug '{slug}' is already used by another company — pick a different one. "
                      f"Everything else on this form was still saved.")
            else:
                company.public_slug = slug
        # Blank means "explicitly clear it" — an empty tracking link is not useful,
        # so clearing just disables the public page rather than leaving a broken link live.
        elif "public_slug" in request.form:
            company.public_slug = None

        # ── Address Visibility (per print format) ──
        company.show_address_customer_invoice = "show_address_customer_invoice" in request.form
        company.show_address_performa_invoice = "show_address_performa_invoice" in request.form

        # ── Logo upload ──
        logo_file = request.files.get("logo")
        if logo_file and logo_file.filename:
            if allowed_logo_file(logo_file.filename):
                ext = logo_file.filename.rsplit('.', 1)[1].lower()
                new_filename = f"{company.company_id}.{ext}"
                # Remove any old logo with a different extension so stale files don't pile up
                if getattr(company, 'logo_filename', None) and company.logo_filename != new_filename:
                    old_path = os.path.join(LOGO_UPLOAD_FOLDER, company.logo_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                logo_file.save(os.path.join(LOGO_UPLOAD_FOLDER, new_filename))
                company.logo_filename = new_filename
            else:
                flash("Logo must be a PNG, JPG, or WEBP file.")

        is_gst = request.form.get("is_gst_registered", "1") == "1"
        company.is_gst_registered = is_gst
        company.gst_number = request.form.get('gst_number', '').strip() if is_gst else None

        # Blank is a valid, explicit choice here (means "no AWB prefix"),
        # so we do NOT fall back to the old value like before.
        if "awb_prefix" in request.form:
            company.awb_prefix = request.form.get("awb_prefix", "").strip().upper()
        try:
            company.awb_start = int(request.form.get("awb_start", company.awb_start))
        except (ValueError, TypeError):
            pass

        # ── Credit limit behaviour: 'warn' (flash only) or 'block' (refuse the save) ──
        _credit_action = request.form.get("credit_limit_action", "warn")
        _credit_action = _credit_action if _credit_action in ("warn", "block") else "warn"
        company.credit_limit_action = _credit_action

        # ── Customer invoice PDF template ──
        _invoice_template = request.form.get("invoice_template", "classic")
        _invoice_template = _invoice_template if _invoice_template in ("classic", "modern", "minimal", "tally_style") else "classic"
        company.invoice_template = _invoice_template

        # ── Multi-Currency & Regional Tax Settings ──
        if "currency" in request.form:
            curr_code = request.form.get("currency", "INR").strip().upper()
            company.currency = curr_code
            curr_info = currency_service.get_currency_info(curr_code)
            company.currency_symbol = request.form.get("currency_symbol", "").strip() or curr_info.get("symbol", "₹")

        if "country" in request.form:
            company.country = request.form.get("country", getattr(company, "country", "India") or "India").strip()

        if "tax_regime" in request.form:
            company.tax_regime = request.form.get("tax_regime", "GST").strip()

        if "tax_id_label" in request.form:
            company.tax_id_label = request.form.get("tax_id_label", "GSTIN").strip()

        try:
            apply_company_tax(company, request.form)
        except ValueError as error:
            db.session.rollback()
            flash(str(error), "error")
            return redirect(url_for("company_settings"))
        db.session.commit()

        # ── Verify it actually persisted ──────────────────────────────────────
        # Setting an attribute on an ORM object and committing succeeds even
        # if that attribute isn't a real mapped column — SQLAlchemy just
        # drops it silently, no error. That would look EXACTLY like this
        # setting "not working": the dropdown shows your choice right after
        # saving (because the in-memory object still has it), but it never
        # actually reached the database, so every later request reads the
        # old value back. Forcing a fresh SELECT here catches that instead
        # of pretending the save worked.
        db.session.expire(company, ["credit_limit_action"])
        _persisted_action = getattr(company, "credit_limit_action", None)
        if _persisted_action != _credit_action:
            flash(
                f"Credit limit setting did not save — chose '{_credit_action}' but the "
                f"database still has '{_persisted_action}'. This looks like a missing "
                f"'credit_limit_action' column on the Company table, not a form bug. "
                f"Check platform_models.py / run the migration.",
                "danger",
            )

        # Keep session in sync
        if "user" in session:
            session["user"]["company_name"] = company.company_name
            session.modified = True
        flash("Company information updated successfully.")
    else:
        flash("Company not found.")
    return redirect(url_for("company_settings"))


@app.route("/settings/whatsapp/templates", methods=["GET", "POST"])
@login_required
@owner_required
def whatsapp_template_config():
    from platform_models import WhatsAppTemplate
    from whatsapp_templates import EVENT_DEFS, field_options_for_event, placeholder_for_field
 
    company_id = get_current_company()
    company = get_company_by_id(company_id)
    if not company:
        flash("Company not found")
        return redirect(url_for("dashboard"))
 
    if request.method == "POST":
        for event_key, _label, _desc in EVENT_DEFS:
            prefix = f"tpl_{event_key}_"
            template_name = request.form.get(prefix + "name", "").strip()
            language_code = request.form.get(prefix + "lang", "en").strip() or "en"
            header_type = request.form.get(prefix + "header", "none").strip() or "none"
            field_keys = [f for f in request.form.getlist(prefix + "var") if f]
 
            row = WhatsAppTemplate.query.filter_by(
                company_id=company_id, template_key=event_key
            ).first()
 
            if not template_name:
                # Blank name = "not configuring this event right now."
                # Leave any existing row untouched rather than deleting it.
                continue
 
            # Translate the selected field keys into {{ placeholder }} strings
            # via the SAME catalogue the resolver uses at send time — this is
            # what keeps the dropdown and the actual send logic in sync.
            try:
                placeholders = [placeholder_for_field(event_key, fk) for fk in field_keys]
            except Exception as e:
                flash(f"'{event_key}': {e}")
                continue
 
            if not row:
                row = WhatsAppTemplate(company_id=company_id, template_key=event_key)
                db.session.add(row)
 
            row.template_name = template_name
            row.language_code = language_code
            row.header_type = header_type
            row.param_count = len(placeholders)
            row.variables_json = json.dumps(placeholders) if placeholders else None
            row.is_active = True
 
        db.session.commit()
        flash("WhatsApp template mapping saved.")
        return redirect(url_for("whatsapp_template_config"))
 
    # ── GET: build view data ──────────────────────────────────────────────
    existing = {
        row.template_key: row
        for row in WhatsAppTemplate.query.filter_by(company_id=company_id).all()
    }
 
    events = []
    for event_key, label, desc in EVENT_DEFS:
        row = existing.get(event_key)
        selected_fields = []
        if row and row.variables_json:
            try:
                placeholders = json.loads(row.variables_json)
                # Reverse-lookup each stored placeholder back to its field
                # key so the form can pre-select the right dropdown option.
                opts = field_options_for_event(event_key)
                lookup = {v[1]: k for k, v in opts.items()}
                selected_fields = [lookup.get(p, "") for p in placeholders]
            except (ValueError, TypeError):
                selected_fields = []
 
        events.append({
            "event_key": event_key,
            "label": label,
            "desc": desc,
            "row": row,
            "selected_fields": selected_fields,
            "field_options": field_options_for_event(event_key),
        })
 
    return render_template(
        "admin_whatsapp_templates.html",
        company=company,
        events=events,
        active="whatsapp_settings",
    )

@app.route("/company/change-password", methods=["POST"])
@login_required
@owner_required
def change_company_password():
    current_password = request.form.get("current_password", "")
    new_password      = request.form.get("new_password", "")
    confirm_password  = request.form.get("confirm_password", "")

    if new_password != confirm_password:
        flash("New password and confirmation do not match.", "error")
        return redirect(url_for("company_settings"))
    if len(new_password) < 8:
        flash("New password must be at least 8 characters.", "error")
        return redirect(url_for("company_settings"))

    email = get_current_user().get("email", "").strip().lower()
    reg_user = RegisteredUser.query.filter_by(email=email, is_active=True).first()

    if reg_user:
        if not verify_password(current_password, reg_user.password_hash):
            flash("Current password is incorrect.", "error")
            return redirect(url_for("company_settings"))
        reg_user.password_hash = hash_password(new_password)
        db.session.commit()

        # Keep the matching CompanyUser record(s) in sync across all of this
        # owner's companies, since employee login checks CompanyUser.password_hash.
        for comp in get_owner_companies(email):
            try:
                _cdb = get_customer_session(comp.company_id)
                emp = _cdb.query(CompanyUser).filter_by(email=email).first()
                if emp:
                    emp.password_hash = hash_password(new_password)
                    _cdb.commit()
            except Exception as e:
                # This loop touches OTHER companies' sessions, not the
                # logged-in owner's own company — teardown_request only
                # rolls back get_current_company()'s session, so a failure
                # here on comp.company_id would otherwise poison that
                # company's session for every future request, with nothing
                # to ever clean it up. Must roll back explicitly.
                try:
                    _cdb.rollback()
                except Exception:
                    pass
                print(f"⚠  Could not sync password for {comp.company_id}: {e}")
    else:
        # Fallback: user only exists as a CompanyUser (shouldn't normally reach
        # this owner-only page, but handled defensively).
        cdb = get_cdb()
        company_id = get_current_company()
        emp = cdb.query(CompanyUser).filter_by(company_id=company_id, email=email).first()
        if not emp or not verify_password(current_password, emp.password_hash):
            flash("Current password is incorrect.", "error")
            return redirect(url_for("company_settings"))
        emp.password_hash = hash_password(new_password)
        cdb.commit()

    flash("Password changed successfully.")
    return redirect(url_for("company_settings"))


ALLOWED_COMPANY_ROLES = ["manager", "employee", "accountant", "bi_developer", "hr_admin", "hr_staff", "payroll_officer"]  # owner is reserved


def validate_company_role_assignment(company, role):
    from module_access import company_has_hr_access
    if role not in ALLOWED_COMPANY_ROLES:
        abort(400, "Invalid company role.")
    if role in perms_module.HR_ROLES and not company_has_hr_access(company):
        abort(403, "HR & Payroll is not included in this company's subscription.")

@app.route("/company/add-user", methods=["POST"])
@login_required
@owner_required
def add_company_user():
    owner_email = get_current_user().get("email", "").strip().lower()

    email      = request.form.get("email",     "").strip().lower()
    password   = request.form.get("password",  "")
    full_name  = request.form.get("full_name", "").strip()
    department = request.form.get("department","")
    phone      = request.form.get("phone",     "")

    if not email or not full_name:
        flash("Email and full name are required.")
        return redirect(url_for("company_settings"))

    # Which of the owner's companies should this user get access to?
    # Form sends company_ids[] (checkboxes) and role_<company_id> (per-row select)
    owner_companies = {c.company_id: c for c in get_owner_companies(owner_email)}
    selected_company_ids = [cid for cid in request.form.getlist("company_ids") if cid in owner_companies]
    for cid in selected_company_ids:
        validate_company_role_assignment(owner_companies[cid], request.form.get(f"role_{cid}", "employee"))

    if not selected_company_ids:
        flash("Select at least one company to grant access to.")
        return redirect(url_for("company_settings"))

    # Seat cap is owner-wide: only a brand-new email consumes a seat.
    # Granting an EXISTING user access to another company doesn't cost a seat.
    current_count, max_u, existing_emails = get_owner_user_stats(owner_email)
    is_new_user = email not in existing_emails
    if is_new_user and max_u != "Unlimited":
        try:
            max_u_int = int(max_u)
            if current_count >= max_u_int:
                flash(f"Maximum {max_u_int} users allowed across all your companies under your plan. Please upgrade.")
                return redirect(url_for("company_settings"))
        except (ValueError, TypeError):
            pass  # "Unlimited"

    if is_new_user and not password:
        flash("Password is required to create a new user.")
        return redirect(url_for("company_settings"))

    pw_hash = hash_password(password) if password else None
    granted_to = []

    for cid in selected_company_ids:
        role = request.form.get(f"role_{cid}", "employee")
        if role not in ALLOWED_COMPANY_ROLES:
            role = "employee"

        _cdb = get_customer_session(cid)
        existing = _cdb.query(CompanyUser).filter_by(company_id=cid, email=email).first()

        if existing:
            # Already has access to this company — update role / reactivate / reset password if given
            existing.role = role
            existing.is_active = True
            existing.full_name = full_name or existing.full_name
            if pw_hash:
                existing.password_hash = pw_hash
            _cdb.commit()
        else:
            emp_id    = _next_numbered_id(_cdb, CompanyUser.user_id, "EMP")
            new_overrides = json.dumps({'analytics': {'view': True}}) if role == 'bi_developer' else None
            new_user = CompanyUser(
                user_id=emp_id, company_id=cid,
                email=email, password_hash=pw_hash,
                full_name=full_name, role=role,
                department=department, phone=phone,
                permission_overrides=new_overrides,
                is_active=True, created_at=today_ist()
            )
            _cdb.add(new_user)
            _cdb.commit()

        granted_to.append(owner_companies[cid].company_name)

    flash(f"'{full_name}' now has access to: {', '.join(granted_to)}.")
    return redirect(url_for("company_settings"))


@app.route("/company/revoke-user/<email>/<company_id>")
@login_required
@owner_required
def revoke_company_user(email, company_id):
    """Remove a user's access to ONE specific company (not all of their companies)."""
    owner_email = get_current_user().get("email", "").strip().lower()
    owner_companies = {c.company_id: c for c in get_owner_companies(owner_email)}
    if company_id not in owner_companies:
        flash("Invalid company.")
        return redirect(url_for("company_settings"))

    _cdb = get_customer_session(company_id)
    user = _cdb.query(CompanyUser).filter_by(company_id=company_id, email=email.strip().lower()).first()
    if user and user.role != "owner":
        user.is_active = False
        _cdb.commit()
        flash(f"Access to {owner_companies[company_id].company_name} revoked.")
    else:
        flash("Cannot revoke this user.")
    return redirect(url_for("company_settings"))


@app.route("/company/remove-user/<user_id>")
@login_required
@owner_required
def remove_company_user(user_id):
    cdb = get_cdb()
    company_id = get_current_company()
    user = cdb.query(CompanyUser).filter_by(user_id=user_id, company_id=company_id).first()
    if user and user.role != "owner":
        user.is_active = False
        cdb.commit()
        flash("User removed successfully.")
    else:
        flash("Cannot remove this user.")
    return redirect(url_for("company_settings"))


@app.route("/company/delete-user/<email>", methods=["GET", "POST"])
@login_required
@owner_required
@require_admin_password
def delete_company_user(email):
    """Remove a person's access to ALL of the owner's companies in one go
    (a full 'delete this person' action). Soft-delete only — sets
    is_active=False everywhere, same as revoke_company_user, so we never
    orphan the invoices/orders/etc. that still reference their user_id.
    """
    owner_email = get_current_user().get("email", "").strip().lower()
    owner_companies = get_owner_companies(owner_email)
    email = email.strip().lower()

    removed_from = []
    for c in owner_companies:
        _cdb = get_customer_session(c.company_id)
        user = _cdb.query(CompanyUser).filter_by(company_id=c.company_id, email=email).first()
        if user and user.role != "owner" and user.is_active:
            user.is_active = False
            _cdb.commit()
            removed_from.append(c.company_name)

    if removed_from:
        flash(f"User removed from: {', '.join(removed_from)}.")
    else:
        flash("Cannot remove this user.")
    return redirect(url_for("company_settings"))


@app.route("/company/edit-user-access/<email>", methods=["POST"])
@login_required
@owner_required
def edit_user_access(email):
    """Update a person's company access + role in one submit: check a
    company to grant/keep access (with the chosen role), uncheck one to
    revoke it. Mirrors add_company_user's creation logic for any newly
    checked company, and revoke_company_user's is_active=False for any
    unchecked one that currently has access.
    """
    owner_email = get_current_user().get("email", "").strip().lower()
    owner_companies = {c.company_id: c for c in get_owner_companies(owner_email)}
    email = email.strip().lower()

    selected_company_ids = set(cid for cid in request.form.getlist("company_ids") if cid in owner_companies)
    for cid in selected_company_ids:
        validate_company_role_assignment(owner_companies[cid], request.form.get(f"role_{cid}", "employee"))

    # Find an existing row for this email to copy password_hash/full_name/etc.
    # onto any brand-new company rows we create below.
    template_user = None
    for cid in owner_companies:
        _cdb = get_customer_session(cid)
        u = _cdb.query(CompanyUser).filter_by(company_id=cid, email=email).first()
        if u:
            template_user = u
            break
    if not template_user:
        flash("User not found.")
        return redirect(url_for("company_settings"))
    if template_user.role == "owner":
        flash("Owner access can't be edited this way.")
        return redirect(url_for("company_settings"))

    granted, revoked = [], []
    for cid, c in owner_companies.items():
        _cdb = get_customer_session(cid)
        existing = _cdb.query(CompanyUser).filter_by(company_id=cid, email=email).first()

        if cid in selected_company_ids:
            role = request.form.get(f"role_{cid}", "employee")
            if role not in ALLOWED_COMPANY_ROLES:
                role = "employee"
            if existing:
                if existing.role != "owner":
                    existing.role = role
                    existing.is_active = True
                    if role == 'bi_developer':
                        try:
                            curr_ov = json.loads(existing.permission_overrides or '{}')
                        except (ValueError, TypeError):
                            curr_ov = {}
                        if not curr_ov.get('analytics', {}).get('view'):
                            curr_ov.setdefault('analytics', {})['view'] = True
                            existing.permission_overrides = json.dumps(curr_ov)
                    _cdb.commit()
            else:
                emp_id    = _next_numbered_id(_cdb, CompanyUser.user_id, "EMP")
                new_overrides = json.dumps({'analytics': {'view': True}}) if role == 'bi_developer' else None
                new_user = CompanyUser(
                    user_id=emp_id, company_id=cid,
                    email=email, password_hash=template_user.password_hash,
                    full_name=template_user.full_name, role=role,
                    department=template_user.department, phone=template_user.phone,
                    permission_overrides=new_overrides,
                    is_active=True, created_at=today_ist()
                )
                _cdb.add(new_user)
                _cdb.commit()
            granted.append(c.company_name)
        else:
            if existing and existing.role != "owner" and existing.is_active:
                existing.is_active = False
                _cdb.commit()
                revoked.append(c.company_name)

    parts = []
    if granted:
        parts.append(f"access: {', '.join(granted)}")
    if revoked:
        parts.append(f"revoked: {', '.join(revoked)}")
    flash(f"Updated {template_user.full_name} — " + "; ".join(parts) if parts else "No changes made.")
    return redirect(url_for("company_settings"))


@app.route("/company/upgrade-plan", methods=["POST"])
@login_required
@owner_required
def upgrade_plan():
    # Paid upgrades are applied by the verified payment callback, not a plan-name POST.
    flash("Choose and pay for your new plan from subscription settings, or contact Qiyadah for a private plan.", "info")
    return redirect(url_for("company_settings"))

# ─────────────────────────────────────────────────────────────────────────────
# ── CASH BOOKING PAYMENT POSTING (cash / bank_transfer / upi only) ───────────
# Shared by invoice_customer_save (new booking) and invoice_customer_update
# (booking edit), and called twice when a split payment is used — once per
# leg. Deliberately does NOT accept "cheque" or "credit": cheque was dropped
# from the cash-booking payment options, and credit bookings never reach
# this function — they carry a balance into the debtors ledger instead.



# ─────────────────────────────────────────────────────────────────────────────
# ── DEBTORS & CREDITORS ───────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
def _debtor_summary(company_id):
    cdb = get_cdb()
    
    all_clients = (cdb.query(Client)
                   .filter_by(company_id=company_id)
                   .filter(Client.status != "Deleted")
                   .filter(~Client.client_type.in_(["Supplier", "Cash-Only"]))
                   .order_by(Client.name).all())
    today = today_ist()
    rows = []
    used_booking_ids = _used_booking_ids_in_customer_invoices(cdb, company_id)

    for c in all_clients:
        cutoff_date = c.statement_cutoff.date() if c.statement_cutoff else None
        c_norm = (c.name or "").strip().lower()

        # Exclude Void, Cancelled, and Draft invoices
        inv_q = cdb.query(Invoice).filter_by(company_id=company_id, client_id=c.id)
        inv_q = inv_q.filter(Invoice.status.notin_(['Cancelled', 'Void', 'Draft']))
        if cutoff_date:
            inv_q = inv_q.filter(Invoice.date >= cutoff_date)
        if used_booking_ids:
            inv_q = inv_q.filter(~Invoice.id.in_(used_booking_ids))
        invoices = inv_q.order_by(Invoice.date.desc()).all()
        sales_q = cdb.query(CustomerInvoice).filter_by(company_id=company_id, client_id=c.id).filter(
            CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft']))
        if cutoff_date:
            sales_q = sales_q.filter(CustomerInvoice.invoice_date >= cutoff_date)
        invoices.extend(sales_q.all())
        invoices.sort(key=lambda i: i.invoice_date if isinstance(i, CustomerInvoice) else i.date, reverse=True)
        note_events = note_statement_events(cdb, company_id, 'credit', c.id, cutoff_date)
        note_total = sum(e['credit'] - e['debit'] for e in note_events)

        cash_q = (cdb.query(CashTransaction)
                  .filter(CashTransaction.company_id == company_id,
                          func.lower(func.trim(CashTransaction.party_name)) == c_norm)
                  .filter(CashTransaction.category.in_(["Receipt", "Adjustment"]))
                  .filter(or_(CashTransaction.reference != "WRITE-OFF", CashTransaction.reference.is_(None))))
        if cutoff_date:
            cash_q = cash_q.filter(CashTransaction.date >= cutoff_date)
        cash_received = float(sum(t.amount or 0 for t in cash_q.all()))

        bank_q = (cdb.query(BankTransaction)
                  .filter(BankTransaction.company_id == company_id,
                          func.lower(func.trim(BankTransaction.party_name)) == c_norm)
                  .filter(BankTransaction.type == "credit"))
        if cutoff_date:
            bank_q = bank_q.filter(BankTransaction.date >= cutoff_date)
        bank_received = float(sum(t.amount or 0 for t in bank_q.all()))

        total_invoiced = sum(float(i.grand_total or 0) for i in invoices)
        # Unified live customer ledger balance
        total_pending = (c.opening_balance or 0) + total_invoiced - cash_received - bank_received - note_total

        # If no invoices, still show client — dues can come from opening balance alone
        if not invoices:
            rows.append({
                "id":                c.id,
                "name":              c.name,
                "phone":             c.phone or "",
                "city":              c.city or "",
                "total_invoiced":    0,
                "total_paid":        cash_received + bank_received,
                "total_pending":     total_pending,
                "last_invoice_id":   None,
                "last_awb":          None,
                "last_invoice_date": None,
                "nearest_due_date":  None,
                "nearest_due_amt":   None,
                "last_payment_date": None,
                "last_payment_amt":  None,
                "invoice_count":     0,
                "overdue":           False,
                "status":            "Fully Paid" if total_pending <= 0 else "Has Dues",
            })
            continue

        total_paid = cash_received + bank_received
        last_invoice = invoices[0]
        last_invoice_date = last_invoice.invoice_date if isinstance(last_invoice, CustomerInvoice) else last_invoice.date
        last_invoice_id = last_invoice.invoice_number if isinstance(last_invoice, CustomerInvoice) else last_invoice.invoice_id
        last_awb = None if isinstance(last_invoice, CustomerInvoice) else (_get_awb(last_invoice) or None)

        # Calculate overdue
        unpaid = [i for i in invoices if (float(getattr(i, "balance", 0) or 0)) > 0]
        due_invoices = [i for i in unpaid if getattr(i, "due_date", None)]
        if due_invoices:
            future = [i for i in due_invoices if i.due_date >= today]
            nearest = min(future, key=lambda i: i.due_date) if future else \
                      max(due_invoices, key=lambda i: i.due_date)
            nearest_due_date = nearest.due_date
            nearest_due_amt = float(getattr(nearest, "balance", 0) or 0)
            overdue = nearest_due_date < today if nearest_due_date else False
        else:
            nearest_due_date = None
            nearest_due_amt = None
            overdue = False

        # Last payment — the most recent actual Cash/Bank transaction for this
        # client, not an invoice-date-based guess. (Same class of bug as the
        # statement pages: picking "the invoice with the latest date among
        # paid ones" is neither the date nor necessarily the invoice a
        # payment was last applied to — a receipt can land against an older
        # invoice, or not be tied to one at all.)
        last_cash = (cdb.query(CashTransaction)
                     .filter_by(company_id=company_id, party_name=c.name, category="Receipt")
                     .order_by(CashTransaction.date.desc()).first())
        last_bank = (cdb.query(BankTransaction)
                     .filter_by(company_id=company_id, party_name=c.name)
                     .filter(BankTransaction.type == "credit")
                     .order_by(BankTransaction.date.desc()).first())
        candidates = [t for t in (last_cash, last_bank) if t is not None]
        if candidates:
            last_txn = max(candidates, key=lambda t: t.date)
            last_payment_date = last_txn.date
            last_payment_amt = last_txn.amount or 0
        else:
            last_payment_date = None
            last_payment_amt = None

        rows.append({
            "id":                c.id,
            "name":              c.name,
            "phone":             c.phone or "",
            "city":              c.city or "",
            "total_invoiced":    total_invoiced,
            "total_paid":        total_paid,
            "total_pending":     total_pending,
            "last_invoice_id":   last_invoice_id,
            "last_awb":          last_awb,
            "last_invoice_date": last_invoice_date,
            "nearest_due_date":  nearest_due_date,
            "nearest_due_amt":   nearest_due_amt,
            "last_payment_date": last_payment_date,
            "last_payment_amt":  last_payment_amt,
            "invoice_count":     len(invoices),
            "overdue":           overdue,
            "status":            "Fully Paid" if total_pending <= 0 else "Has Dues",
        })

    rows.sort(key=lambda r: r["name"].lower())
    return rows

def _creditor_summary(company_id):
    cdb = get_cdb()
    suppliers = cdb.query(Supplier).filter(
        Supplier.company_id == company_id
    ).order_by(Supplier.name).all()

    today = today_ist()
    rows = []

    for s in suppliers:
        cutoff_date = s.statement_cutoff.date() if s.statement_cutoff else None

        # 🔴 FIX: Filter out VOID purchase invoices
        inv_q = cdb.query(PurchaseInvoice).filter_by(company_id=company_id, supplier_id=s.id)
        inv_q = inv_q.filter(PurchaseInvoice.status.notin_(['Cancelled', 'Void']))  # ← EXCLUDE VOID
        if cutoff_date:
            inv_q = inv_q.filter(PurchaseInvoice.date >= cutoff_date)
        invoices = inv_q.order_by(PurchaseInvoice.date.desc()).all()

        # BUG FIX: total_pending must be driven off the ACTUAL cash/bank
        # Payment transactions recorded for this supplier — not off each
        # invoice's own paid_amount. A payment that isn't matched exactly to
        # an invoice's balance (an advance, an overpayment, or a payment
        # recorded with no invoice selected) never touches any invoice's
        # paid_amount/balance, so a paid_amount-based sum silently ignores
        # that money entirely and the "outstanding" figure never moves.
        # (Same fix already applied to _debtor_summary above — this brings
        # creditors in line with it.)
        cash_q = (cdb.query(CashTransaction)
                  .filter(CashTransaction.company_id == company_id,
                          func.lower(CashTransaction.party_name) == func.lower(s.name))
                  .filter(CashTransaction.category == "Payment"))
        if cutoff_date:
            cash_q = cash_q.filter(CashTransaction.date >= cutoff_date)
        cash_paid = float(sum(t.amount or 0 for t in cash_q.all()))

        bank_q = (cdb.query(BankTransaction)
                  .filter(BankTransaction.company_id == company_id,
                          func.lower(BankTransaction.party_name) == func.lower(s.name))
                  .filter(BankTransaction.type == "debit"))
        if cutoff_date:
            bank_q = bank_q.filter(BankTransaction.date >= cutoff_date)
        bank_paid = float(sum(t.amount or 0 for t in bank_q.all()))

        note_events = note_statement_events(cdb, company_id, 'debit', s.id, cutoff_date)
        note_total = sum(e['debit'] - e['credit'] for e in note_events)

        if not invoices:
            total_pending = (s.opening_balance or 0) - cash_paid - bank_paid - note_total
            rows.append({
                "id":                s.id,
                "name":              s.name,
                "phone":             s.phone or "",
                "city":              s.city or "",
                "total_pending":     total_pending,
                "last_bill_date":    None,
                "nearest_due_date":  None,
                "nearest_due_amt":   None,
                "last_payment_date": None,
                "last_payment_amt":  None,
                "invoice_count":     0,
                "overdue":           False,
                "status":            "Fully Paid" if total_pending <= 0 else "Has Dues",
            })
            continue

        # total_pending — opening_balance + Σ(grand_total) since cutoff −
        # actual payments made since cutoff, matching the creditor
        # statement's closing balance and correctly reflecting advance /
        # unmatched payments (which don't reduce any single invoice's
        # balance).
        total_invoiced = sum(float(i.grand_total or 0) for i in invoices)
        total_pending = (s.opening_balance or 0) + total_invoiced - cash_paid - bank_paid - note_total
        last_bill_date = invoices[0].date

        # Calculate overdue
        unpaid = [i for i in invoices if (i.balance or 0) > 0]
        due_invoices = [i for i in unpaid if i.due_date]
        if due_invoices:
            future = [i for i in due_invoices if i.due_date >= today]
            nearest = min(future, key=lambda i: i.due_date) if future else \
                      max(due_invoices, key=lambda i: i.due_date)
            nearest_due_date = nearest.due_date
            nearest_due_amt = nearest.balance or 0
            overdue = nearest_due_date < today if nearest_due_date else False
        else:
            nearest_due_date = None
            nearest_due_amt = None
            overdue = False

        # Last payment — real most-recent Cash/Bank transaction, not an
        # invoice-date guess (same fix as _debtor_summary above).
        last_cash = (cdb.query(CashTransaction)
                     .filter(CashTransaction.company_id == company_id,
                             func.lower(CashTransaction.party_name) == func.lower(s.name),
                             CashTransaction.category == "Payment")
                     .order_by(CashTransaction.date.desc()).first())
        last_bank = (cdb.query(BankTransaction)
                     .filter(BankTransaction.company_id == company_id,
                             func.lower(BankTransaction.party_name) == func.lower(s.name),
                             BankTransaction.type == "debit")
                     .order_by(BankTransaction.date.desc()).first())
        candidates = [t for t in (last_cash, last_bank) if t is not None]
        if candidates:
            last_txn = max(candidates, key=lambda t: t.date)
            last_payment_date = last_txn.date
            last_payment_amt = last_txn.amount or 0
        else:
            last_payment_date = None
            last_payment_amt = None

        rows.append({
            "id":                s.id,
            "name":              s.name,
            "phone":             s.phone or "",
            "city":              s.city or "",
            "total_pending":     total_pending,
            "last_bill_date":    last_bill_date,
            "nearest_due_date":  nearest_due_date,
            "nearest_due_amt":   nearest_due_amt,
            "last_payment_date": last_payment_date,
            "last_payment_amt":  last_payment_amt,
            "invoice_count":     len(invoices),
            "overdue":           overdue,
            "status":            "Fully Paid" if total_pending <= 0 else "Has Dues",
        })

    rows.sort(key=lambda r: r["name"].lower())
    return rows

@app.route("/debtors")
@login_required
@require_permission("debtors", "view")
def debtors_list():
    company_id        = get_current_company()
    debtors           = _debtor_summary(company_id)
    total_outstanding = sum(d["total_pending"] for d in debtors)
    overdue_count     = sum(1 for d in debtors if d["overdue"])
    return render_template("debtors.html",
                           debtors=debtors,
                           total_outstanding=total_outstanding,
                           overdue_count=overdue_count)


@app.route("/creditors")
@login_required
@require_permission("creditors", "view")
def creditors_list():
    company_id    = get_current_company()
    creditors     = _creditor_summary(company_id)
    total_payable = sum(c["total_pending"] for c in creditors)
    overdue_count = sum(1 for c in creditors if c["overdue"])
    return render_template("creditors.html",
                           creditors=creditors,
                           total_payable=total_payable,
                           overdue_count=overdue_count)


def _build_customer_invoice_statement_ledger(cdb, company_id, c, since=None, until=None):
    """Builds the DEBTOR-PAGE statement (compiled CustomerInvoice bills
    only) — completely independent of _build_client_ledger()'s raw-booking
    ledger used by the Clients page / credit-limit check. Deliberately NOT
    reconciled against that other ledger: an invoice always appears here at
    its FULL billed amount under its own invoice number, exactly as the
    customer received it, so a customer reading this statement never sees a
    number that doesn't match their bill. Any mismatch between "true"
    booking-level outstanding and this invoice-level outstanding is
    expected and fine — they answer different questions (internal exposure
    vs what's been formally billed). `since`/`until` key off
    CustomerInvoice.invoice_date, i.e. this statement's OWN cutoff
    (c.invoice_statement_cutoff), never the booking-ledger cutoff."""
    since_date = since.date() if since else None

    ci_query = (cdb.query(CustomerInvoice)
                .filter_by(company_id=company_id, client_id=c.id, invoice_type="credit")
                .filter(CustomerInvoice.status != "Void"))
    if since_date:
        ci_query = ci_query.filter(CustomerInvoice.invoice_date >= since_date)
    if until:
        ci_query = ci_query.filter(CustomerInvoice.invoice_date < until)
    customer_invoices = ci_query.order_by(CustomerInvoice.invoice_date.asc()).all()

    cash_q = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        func.lower(CashTransaction.party_name) == func.lower(c.name)
    ).filter(CashTransaction.category.in_(["Receipt", "Adjustment"]))
    cash_q = cash_q.filter(or_(CashTransaction.reference != "WRITE-OFF", CashTransaction.reference.is_(None)))
    if since_date:
        cash_q = cash_q.filter(CashTransaction.date >= since_date)
    if until:
        cash_q = cash_q.filter(CashTransaction.date < until)
    cash_txns = cash_q.all()

    bank_q = cdb.query(BankTransaction).filter(
        BankTransaction.company_id == company_id,
        func.lower(BankTransaction.party_name) == func.lower(c.name)
    ).filter(BankTransaction.type == "credit")
    if since_date:
        bank_q = bank_q.filter(BankTransaction.date >= since_date)
    if until:
        bank_q = bank_q.filter(BankTransaction.date < until)
    bank_txns = bank_q.all()

    events = []

    for ci in customer_invoices:
        items = cdb.query(CustomerInvoiceItem).filter_by(customer_invoice_id=ci.id).order_by(CustomerInvoiceItem.booking_date.asc(), CustomerInvoiceItem.id.asc()).all()
        if items:
            shipments = []
            for item in items:
                shipments.append({
                    "awb": item.docket_no or "",
                    "consignee": item.receiver_name or "",
                    "destination": item.destination or "",
                    "carrier_ref": item.carrier_ref or "",
                    "carrier": item.carrier or "",
                    "chrg_wt": item.weight_kg or 0,
                    "act_wt": item.weight_kg or 0,
                    "vol_wt": 0,
                    "per_kg": item.rate_per_kg or 0,
                    "grand_total": (item.total_amount or 0) - (item.other_charges or 0),
                    "other_charges": item.other_charges or 0,
                    "billing_amount": item.total_amount or 0,
                })
            first_item = shipments[0]
            other_chgs_total = sum(s["other_charges"] for s in shipments)
            total_chrg_wt = sum(s["chrg_wt"] for s in shipments)
            events.append({
                "date": ci.invoice_date,
                "type": "Invoice",
                "ref": ci.invoice_number,
                "id": ci.id,
                "is_customer_invoice": True,
                "payment_mode": "",
                "debit": ci.grand_total or 0,
                "credit": 0,
                "status": ci.status,
                "awb": first_item["awb"] if len(shipments) == 1 else "",
                "consignee": first_item["consignee"] if len(shipments) == 1 else f"{len(shipments)} bookings",
                "destination": first_item["destination"] if len(shipments) == 1 else "",
                "carrier_ref": first_item["carrier_ref"] if len(shipments) == 1 else "",
                "carrier": first_item["carrier"] if len(shipments) == 1 else "",
                "chrg_wt": total_chrg_wt,
                "act_wt": total_chrg_wt,
                "vol_wt": 0,
                "grand_total": (ci.grand_total or 0) - other_chgs_total,
                "other_charges": other_chgs_total,
                "billing_amount": ci.grand_total or 0,
                "per_kg": first_item["per_kg"] if len(shipments) == 1 else 0,
                "shipments": shipments,
                "_sort": 0,
            })
        else:
            booking_ids = []
            try:
                if ci.booking_ids_json:
                    booking_ids = json.loads(ci.booking_ids_json)
            except (ValueError, TypeError):
                booking_ids = []

            inv_list = []
            if booking_ids:
                inv_list = cdb.query(Invoice).filter(
                    Invoice.company_id == company_id,
                    or_(Invoice.id.in_(booking_ids), Invoice.invoice_id.in_([str(b) for b in booking_ids]))
                ).order_by(Invoice.date.asc(), Invoice.id.asc()).all()

            if inv_list:
                shipments = []
                for inv in inv_list:
                    meta = _get_shipment_meta(inv)
                    gt = inv.grand_total or 0
                    shipments.append({
                        "awb": meta["awb"],
                        "consignee": meta["consignee"],
                        "destination": meta["destination"],
                        "carrier_ref": meta["carrier_ref"],
                        "carrier": meta["carrier"],
                        "chrg_wt": meta["chrg_wt"],
                        "act_wt": meta["act_wt"],
                        "vol_wt": meta["vol_wt"],
                        "per_kg": meta.get("per_kg", 0),
                        "grand_total": gt - meta["other_charges"],
                        "other_charges": meta["other_charges"],
                        "billing_amount": gt,
                    })
                first_item = shipments[0]
                other_chgs_total = sum(s["other_charges"] for s in shipments)
                total_chrg_wt = sum(s["chrg_wt"] for s in shipments)
                events.append({
                    "date": ci.invoice_date,
                    "type": "Invoice",
                    "ref": ci.invoice_number,
                    "id": ci.id,
                    "is_customer_invoice": True,
                    "payment_mode": "",
                    "debit": ci.grand_total or 0,
                    "credit": 0,
                    "status": ci.status,
                    "awb": first_item["awb"] if len(shipments) == 1 else "",
                    "consignee": first_item["consignee"] if len(shipments) == 1 else f"{len(shipments)} bookings",
                    "destination": first_item["destination"] if len(shipments) == 1 else "",
                    "carrier_ref": first_item["carrier_ref"] if len(shipments) == 1 else "",
                    "carrier": first_item["carrier"] if len(shipments) == 1 else "",
                    "chrg_wt": total_chrg_wt,
                    "act_wt": total_chrg_wt,
                    "vol_wt": 0,
                    "grand_total": (ci.grand_total or 0) - other_chgs_total,
                    "other_charges": other_chgs_total,
                    "billing_amount": ci.grand_total or 0,
                    "per_kg": first_item["per_kg"] if len(shipments) == 1 else 0,
                    "shipments": shipments,
                    "_sort": 0,
                })
            else:
                booking_count = len(booking_ids)
                events.append({
                    "date": ci.invoice_date,
                    "type": "Invoice",
                    "ref": ci.invoice_number,
                    "id": ci.id,
                    "is_customer_invoice": True,
                    "payment_mode": "",
                    "debit": ci.grand_total or 0,
                    "credit": 0,
                    "status": ci.status,
                    "awb": "",
                    "consignee": f"{booking_count} booking" + ("" if booking_count == 1 else "s") if booking_count else "",
                    "destination": "", "carrier_ref": "", "carrier": "",
                    "chrg_wt": 0, "act_wt": 0, "vol_wt": 0,
                    "grand_total": ci.grand_total or 0,
                    "other_charges": 0,
                    "billing_amount": ci.grand_total or 0,
                    "per_kg": 0,
                    "_sort": 0,
                })

    for ct in cash_txns:
        ref = ct.reference or ""
        events.append({
            "date": ct.date,
            "type": "Payment Received",
            "ref": "—" if ref == "ADVANCE" else ref,
            "payment_mode": "Cash",
            "debit": 0,
            "credit": ct.amount or 0,
            "status": "",
            "awb": "", "consignee": "", "destination": "", "carrier_ref": "", "carrier": "",
            "chrg_wt": 0, "act_wt": 0, "vol_wt": 0,
            "grand_total": 0, "other_charges": 0, "billing_amount": 0,
            "per_kg": 0,
            "_sort": 1,
        })

    for bt in bank_txns:
        ref = bt.reference or ""
        events.append({
            "date": bt.date,
            "type": "Payment Received",
            "ref": "—" if ref == "ADVANCE" else ref,
            "payment_mode": bt.transaction_mode or "Bank Transfer",
            "debit": 0,
            "credit": bt.amount or 0,
            "status": "",
            "awb": "", "consignee": "", "destination": "", "carrier_ref": "", "carrier": "",
            "chrg_wt": 0, "act_wt": 0, "vol_wt": 0,
            "grand_total": 0, "other_charges": 0, "billing_amount": 0,
            "per_kg": 0,
            "_sort": 1,
        })

    events.extend(note_statement_events(cdb, company_id, 'credit', c.id, since_date, until))

    events.sort(key=lambda e: (e["date"] or date.min, e["_sort"]))

    ledger = []
    running_balance = getattr(c, "invoice_opening_balance", None) or 0.0

    if running_balance:
        ledger.append({
            "date": since.date() if since else (c.created_at or today_ist()),
            "type": "Balance Carried Forward" if since else "Opening Balance",
            "ref": "—",
            "payment_mode": "",
            "debit": running_balance,
            "credit": 0,
            "balance": running_balance,
            "status": "",
            "awb": "", "consignee": "", "destination": "", "carrier_ref": "", "carrier": "",
            "chrg_wt": 0, "act_wt": 0, "vol_wt": 0,
            "grand_total": 0, "other_charges": 0, "billing_amount": 0,
            "per_kg": 0,
        })

    for e in events:
        running_balance += (e["debit"] or 0) - (e["credit"] or 0)
        e["balance"] = running_balance
        del e["_sort"]
        ledger.append(e)

    total_debit = sum(r["debit"] for r in ledger)
    total_credit = sum(r["credit"] for r in ledger)

    return ledger, total_debit, total_credit, running_balance


@app.route("/debtors/<int:client_pk>/statement")
@login_required
@require_permission("debtors", "view")
def debtor_statement(client_pk):
    """Short/Standard statement for Debtors (simple format). Runs on its
    OWN cutoff (c.invoice_statement_cutoff / c.invoice_opening_balance) —
    intentionally decoupled from the Clients-page booking ledger's
    statement_cutoff/opening_balance, which is used for internal exposure
    tracking (credit limit etc.) and can legitimately show a different
    outstanding figure. Every invoice shown here is always at its full
    billed amount, matching exactly what the customer was actually sent."""
    cdb = get_cdb()
    company_id = get_current_company()
    c = _first_or_404(cdb.query(Client).filter_by(id=client_pk, company_id=company_id).first())
    _ensure_client_invoice_statement_columns(cdb)

    from_date_str = request.args.get('from_date', '')
    to_date_str = request.args.get('to_date', '')
    from_date = date.fromisoformat(from_date_str) if from_date_str else None
    to_date = date.fromisoformat(to_date_str) if to_date_str else None

    cutoff = getattr(c, "invoice_statement_cutoff", None)
    since = cutoff  # datetime or None, matches _build_customer_invoice_statement_ledger's `since`

    ledger, total_debit, total_credit, running_balance = _build_customer_invoice_statement_ledger(
        cdb, company_id, c, since=since, until=None)

    # from_date/to_date are a display-only filter on top of the ledger
    # already built from the cutoff — applied here rather than pushed into
    # the query so the running balance still reflects everything since the
    # cutoff even when the visible window is narrowed.
    if from_date or to_date:
        filtered = []
        running = getattr(c, "invoice_opening_balance", None) or 0.0
        carried_row = None
        for row in ledger:
            if row["type"] in ("Balance Carried Forward", "Opening Balance"):
                carried_row = row
                continue
            row_date = row["date"]
            if from_date and row_date and row_date < from_date:
                running += (row["debit"] or 0) - (row["credit"] or 0)
                continue
            if to_date and row_date and row_date > to_date:
                continue
            filtered.append(row)
        if carried_row and (not from_date or (carried_row["date"] and carried_row["date"] >= from_date)):
            filtered.insert(0, carried_row)
        elif running:
            filtered.insert(0, {
                **{k: (0 if k in ("debit", "credit") else v) for k, v in (ledger[0] if ledger else {}).items()},
                "date": from_date or (since.date() if since else (c.created_at or today_ist())),
                "type": "Balance Brought Forward",
                "ref": "—", "debit": running, "credit": 0, "balance": running, "status": "",
            })
        ledger = filtered
        total_debit = sum(r["debit"] for r in ledger)
        total_credit = sum(r["credit"] for r in ledger)
        running_balance = ledger[-1]["balance"] if ledger else (getattr(c, "invoice_opening_balance", None) or 0.0)

    archives = (cdb.query(StatementClosing)
                .filter_by(company_id=company_id, entity_type="client_invoice", entity_id=c.id)
                .order_by(StatementClosing.closed_at.desc())
                .all())

    return render_template("debtor_creditor_statement.html",
                           entity=_normalize_client(c),
                           company=get_company_by_id(company_id),
                           ledger=ledger,
                           total_debit=total_debit,
                           total_credit=total_credit,
                           closing_balance=running_balance,
                           mode="debtor",
                           back_url="/debtors",
                           archive_base_url=f"/debtors/{client_pk}",
                           archives=archives,
                           archived=False,
                           today=today_ist().strftime("%d %b %Y"),
                           from_date=from_date_str,
                           to_date=to_date_str)


def _ensure_client_invoice_statement_columns(cdb):
    """One-time, idempotent schema patch for the debtor-statement's own
    cutoff fields (see _build_customer_invoice_statement_ledger). Same
    pattern as _ensure_payment_ledger_columns — db.create_all() never
    ALTERs an existing `clients` table, so this backfills it safely on
    every call; each statement already exists after the first run so the
    ALTER just no-ops."""
    from sqlalchemy import text as _text
    for stmt in (
        "ALTER TABLE clients ADD COLUMN invoice_statement_cutoff DATETIME",
        "ALTER TABLE clients ADD COLUMN invoice_opening_balance FLOAT DEFAULT 0",
    ):
        try:
            cdb.execute(_text(stmt))
            cdb.commit()
        except Exception:
            cdb.rollback()


def _client_close_invoice_statement(cdb, company_id, c, action, scope="till_yesterday", as_of_date=None):
    """Debtor-statement equivalent of _client_close_statement(), but reads
    and writes c.invoice_statement_cutoff / c.invoice_opening_balance —
    the statement's OWN cutoff — never touching c.statement_cutoff /
    c.opening_balance (the booking-ledger cutoff used for credit-limit /
    true_outstanding). Archives under entity_type='client_invoice' so its
    history never mixes with the booking-ledger's archives. See
    _client_close_statement's docstring for the as_of_date/scope
    semantics — identical here."""
    _ensure_client_invoice_statement_columns(cdb)
    today = today_ist()

    if as_of_date is None:
        if action == "cleared" and scope == "complete":
            as_of_date = today
        else:
            as_of_date = today - timedelta(days=1)

    if as_of_date > today:
        as_of_date = today
    existing_cutoff = getattr(c, "invoice_statement_cutoff", None)
    if existing_cutoff:
        floor_date = existing_cutoff.date() - timedelta(days=1)
        if as_of_date < floor_date:
            as_of_date = floor_date

    archive_until = as_of_date + timedelta(days=1)

    ledger, total_debit, total_credit, closing = _build_customer_invoice_statement_ledger(
        cdb, company_id, c, since=existing_cutoff, until=archive_until)

    cdb.add(StatementClosing(
        company_id=company_id,
        entity_type="client_invoice",
        entity_id=c.id,
        entity_name=c.name,
        action=action,
        closing_balance=closing,
        total_debit=total_debit,
        total_credit=total_credit,
        ledger_snapshot=json.dumps(ledger, default=str),
        closed_by=session.get("username", "unknown"),
        closed_at=datetime.utcnow(),
    ))

    c.invoice_statement_cutoff = datetime.combine(archive_until, datetime.min.time())
    c.invoice_opening_balance = closing if action == "carried_forward" else 0
    return closing


@app.route("/debtors/<int:client_pk>/shift-to-opening", methods=["GET", "POST"])
@login_required
@owner_required
@require_admin_password
def debtor_shift_to_opening(client_pk):
    """Carry-forward action for the DEBTOR (invoice) statement only —
    twin of client_shift_to_opening but never touches the booking-ledger
    cutoff, so this can be run independently of (and without disturbing)
    the Clients page's own carry-forward."""
    cdb = get_cdb()
    company_id = get_current_company()
    c = _first_or_404(cdb.query(Client).filter_by(id=client_pk, company_id=company_id).first())
    as_of_str = request.values.get("as_of", "").strip()
    as_of_date = date.fromisoformat(as_of_str) if as_of_str else None
    amount = _client_close_invoice_statement(cdb, company_id, c, action="carried_forward", as_of_date=as_of_date)
    cdb.commit()
    if amount:
        flash(f"{company_currency_symbol()} {amount:,.2f} carried forward as the opening balance on {c.name}'s invoice statement. Old statement archived.")
    else:
        flash(f"'{c.name}' had no invoice-statement balance to carry forward.")
    return redirect(url_for("debtor_statement", client_pk=client_pk))


@app.route("/debtors/<int:client_pk>/close", methods=["GET", "POST"])
@login_required
@owner_required
@require_admin_password
def debtor_close_statement(client_pk):
    """Clear (write off / reset to zero) the DEBTOR invoice statement
    only — twin of client_delete's clear action, scoped to
    invoice_statement_cutoff/invoice_opening_balance."""
    cdb = get_cdb()
    company_id = get_current_company()
    c = _first_or_404(cdb.query(Client).filter_by(id=client_pk, company_id=company_id).first())
    scope = request.args.get("scope", "till_yesterday")
    if scope not in ("complete", "till_yesterday"):
        scope = "till_yesterday"
    amount = _client_close_invoice_statement(cdb, company_id, c, action="cleared", scope=scope)
    cdb.commit()
    if amount:
        flash(f"Invoice statement balance of {company_currency_symbol()} {amount:,.2f} cleared for '{c.name}'. Old statement archived.")
    else:
        flash(f"'{c.name}' had no invoice-statement balance to clear.")
    return redirect(url_for("debtor_statement", client_pk=client_pk))


@app.route("/debtors/<int:client_pk>/statement/archive/<int:archive_id>")
@login_required
@require_permission("debtors", "view")
def debtor_statement_archive(client_pk, archive_id):
    """Frozen old debtor (invoice) statement. entity_type='client_invoice'
    keeps this separate from the Clients-page booking-ledger archives
    (entity_type='client') — the two statements now carry forward
    independently, so their archive histories must not mix either."""
    cdb = get_cdb()
    company_id = get_current_company()
    c = _first_or_404(cdb.query(Client).filter_by(id=client_pk, company_id=company_id).first())
    archive = _first_or_404(cdb.query(StatementClosing).filter_by(
        id=archive_id, company_id=company_id, entity_type="client_invoice", entity_id=client_pk).first())

    return render_template("debtor_creditor_statement.html",
                           entity=_normalize_client(c),
                           company=get_company_by_id(company_id),
                           ledger=json.loads(archive.ledger_snapshot or "[]"),
                           total_debit=archive.total_debit,
                           total_credit=archive.total_credit,
                           closing_balance=archive.closing_balance,
                           mode="debtor",
                           back_url=f"/debtors/{client_pk}/statement",
                           archived=True,
                           archived_at=archive.closed_at,
                           today=today_ist().strftime("%d %b %Y"))


@app.route("/creditors/<int:supplier_pk>/statement")
@login_required
@require_permission("creditors", "view")
def creditor_statement(supplier_pk):
    """Short/Standard statement for Creditors (simple format)"""
    cdb = get_cdb()
    company_id = get_current_company()
    s = _first_or_404(cdb.query(Supplier).filter_by(id=supplier_pk, company_id=company_id).first())

    cutoff_date = s.statement_cutoff.date() if s.statement_cutoff else None

    invoices_q = cdb.query(PurchaseInvoice).filter_by(company_id=company_id, supplier_id=s.id)
    invoices_q = invoices_q.filter(PurchaseInvoice.status.notin_(['Cancelled', 'Void']))
    if cutoff_date:
        invoices_q = invoices_q.filter(PurchaseInvoice.date >= cutoff_date)
    invoices = invoices_q.order_by(PurchaseInvoice.date.asc()).all()

    # BUG FIX: every cash/bank Payment transaction is its own ledger event —
    # with its OWN real date, amount and mode — instead of a "Payment Made"
    # line being *derived* from each invoice's paid_amount. Deriving it from
    # paid_amount meant: (1) a payment recorded as an advance / not matched
    # to a specific invoice's exact remaining balance (overpayment, no
    # invoice selected, amount split across invoices) never showed up on the
    # statement at all — the loop below never saw it because it only walked
    # invoices, and (2) multiple partial payments against the same invoice
    # collapsed into a single line stamped with the invoice's date instead
    # of each payment's real date. Same class of fix already applied to
    # debtor_statement above — this brings creditors in line with it.
    cash_q = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        func.lower(CashTransaction.party_name) == func.lower(s.name)
    ).filter(CashTransaction.category == "Payment")
    if cutoff_date:
        cash_q = cash_q.filter(CashTransaction.date >= cutoff_date)
    cash_txns = cash_q.all()

    bank_q = cdb.query(BankTransaction).filter(
        BankTransaction.company_id == company_id,
        func.lower(BankTransaction.party_name) == func.lower(s.name)
    ).filter(BankTransaction.type == "debit")
    if cutoff_date:
        bank_q = bank_q.filter(BankTransaction.date >= cutoff_date)
    bank_txns = bank_q.all()

    events = []

    for inv in invoices:
        events.append({
            "date": inv.date,
            "type": "Purchase Invoice",
            "ref": inv.invoice_number or inv.invoice_id,
            "payment_mode": "",
            "debit": 0,
            "credit": inv.grand_total or 0,
            "status": inv.status,
            "_sort": 0,
        })

    for ct in cash_txns:
        ref = ct.reference or ""
        events.append({
            "date": ct.date,
            "type": "Payment Made",
            "ref": "—" if ref == "ADVANCE" else ref,
            "payment_mode": "Cash",
            "debit": ct.amount or 0,
            "credit": 0,
            "status": "",
            "_sort": 1,
        })

    for bt in bank_txns:
        ref = bt.reference or ""
        events.append({
            "date": bt.date,
            "type": "Payment Made",
            "ref": "—" if ref == "ADVANCE" else ref,
            "payment_mode": bt.transaction_mode or "Bank Transfer",
            "debit": bt.amount or 0,
            "credit": 0,
            "status": "",
            "_sort": 1,
        })

    events.extend(note_statement_events(cdb, company_id, 'debit', s.id, cutoff_date))

    events.sort(key=lambda e: (e["date"] or date.min, e["_sort"]))

    ledger = []
    running_balance = s.opening_balance or 0.0

    if running_balance:
        ledger.append({
            "date": s.statement_cutoff.date() if s.statement_cutoff else (s.created_at or today_ist()),
            "type": "Balance Carried Forward" if s.statement_cutoff else "Opening Balance",
            "ref": "—",
            "payment_mode": "",
            "debit": 0,
            "credit": running_balance,
            "balance": running_balance,
            "status": "",
        })

    for e in events:
        running_balance += (e["credit"] or 0) - (e["debit"] or 0)
        e["balance"] = running_balance
        del e["_sort"]
        ledger.append(e)

    total_debit = sum(r["debit"] for r in ledger)
    total_credit = sum(r["credit"] for r in ledger)

    archives = (cdb.query(StatementClosing)
                .filter_by(company_id=company_id, entity_type="supplier", entity_id=s.id)
                .order_by(StatementClosing.closed_at.desc())
                .all())

    # Use the SIMPLE template for creditors
    return render_template("debtor_creditor_statement.html",
                           entity=_normalize_supplier(s),
                           company=get_company_by_id(company_id),
                           ledger=ledger,
                           total_debit=total_debit,
                           total_credit=total_credit,
                           closing_balance=running_balance,
                           mode="supplier",
                           back_url="/creditors",
                           archive_base_url=f"/creditors/{supplier_pk}",
                           archives=archives,
                           archived=False,
                           today=today_ist().strftime("%d %b %Y"))


@app.route("/creditors/<int:supplier_pk>/statement/archive/<int:archive_id>")
@login_required
@require_permission("creditors", "view")
def creditor_statement_archive(supplier_pk, archive_id):
    """Frozen old creditor statement — reads the same StatementClosing rows
    the Suppliers-page statement archive uses."""
    cdb = get_cdb()
    company_id = get_current_company()
    s = _first_or_404(cdb.query(Supplier).filter_by(id=supplier_pk, company_id=company_id).first())
    archive = _first_or_404(cdb.query(StatementClosing).filter_by(
        id=archive_id, company_id=company_id, entity_type="supplier", entity_id=supplier_pk).first())

    return render_template("debtor_creditor_statement.html",
                           entity=_normalize_supplier(s),
                           company=get_company_by_id(company_id),
                           ledger=json.loads(archive.ledger_snapshot or "[]"),
                           total_debit=archive.total_debit,
                           total_credit=archive.total_credit,
                           closing_balance=archive.closing_balance,
                           mode="supplier",
                           back_url=f"/creditors/{supplier_pk}/statement",
                           archived=True,
                           archived_at=archive.closed_at,
                           today=today_ist().strftime("%d %b %Y"))


# ─────────────────────────────────────────────────────────────────────────────
# ── Receipts & Payments ───────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

def _outstanding_invoices_for_client(company_id, client_id):
    """Return list of dicts for invoices with a remaining balance for a client.

    BUG FIX: this used to filter `Invoice.status.in_(["Pending", "Partial"])`.
    New invoices default to status "Draft" (see the invoice-creation routes'
    status logic) whenever nothing has been paid yet — which is the normal
    case for a brand-new invoice — so a finalized, fully unpaid invoice sat in
    "Draft" forever and was invisible here, even though the client's total
    pending balance (computed elsewhere from `balance` directly, not status)
    correctly showed the money owed. That's why the receipts page could show
    "₹18,743 pending" for a client and "No outstanding invoices" in the same
    breath. What actually determines whether an invoice needs settling is its
    balance, not its status label, so filter on that instead.
    """
    cdb = get_cdb()
    invs = (cdb.query(Invoice)
            .filter_by(company_id=company_id, client_id=client_id)
            .filter(Invoice.status != "Paid")
            .order_by(Invoice.date.asc())
            .all())
    result = []
    for inv in invs:
        total   = inv.grand_total or 0
        balance = getattr(inv, "balance", None)
        if balance is None:
            balance = total if inv.status != "Paid" else 0
        if balance > 0:
            result.append({
                "id":      inv.id,
                "ref":     inv.invoice_id,
                "date":    inv.date.strftime("%d %b %Y") if inv.date else "",
                "total":   total,
                "balance": balance,
            })
    return result


def _outstanding_invoices_for_supplier(company_id, supplier_id):
    """Return list of dicts for purchase invoices with a remaining balance.

    Balance and status filter now match payment_new()'s live_payable exactly
    (grand_total - paid_amount, excluding Cancelled/Void) so the Step 1
    dropdown total and the Step 2 bill list always sum to the same number.
    Previously this used the stored .balance column and a different status
    filter (only excluding "Paid"), which could silently diverge from the
    dropdown whenever .balance drifted or a Draft/Cancelled/Void invoice
    was involved.
    """
    cdb = get_cdb()
    invs = (cdb.query(PurchaseInvoice)
            .filter_by(company_id=company_id, supplier_id=supplier_id)
            .filter(PurchaseInvoice.status.notin_(['Cancelled', 'Void']))
            .order_by(PurchaseInvoice.date.asc())
            .all())
    result = []
    for inv in invs:
        total   = inv.grand_total or 0
        balance = round(total - (inv.paid_amount or 0) - (inv.note_adjustment or 0), 2)
        if balance > 0:
            result.append({
                "id":      inv.id,
                "ref":     inv.invoice_number or inv.invoice_id,
                "date":    inv.date.strftime("%d %b %Y") if inv.date else "",
                "total":   total,
                "balance": balance,
            })
    return result


def _build_invoices_json(company_id, entities, fetch_fn):
    """Build {entity_id: [invoice list]} dict for JS."""
    data = {}
    for e in entities:
        data[str(e.id)] = fetch_fn(company_id, e.id)
    return json.dumps(data)


# ── Customer-invoice aware receivables (used by the debtor Receipts screen) ──
# Bookings can now be rolled up into a CustomerInvoice (see
# customer_invoice_create). Once that happens the booking must stop being
# separately payable through the raw per-booking picker — otherwise the same
# money could be applied twice, once against the booking and once against
# the customer invoice it belongs to. `_outstanding_invoices_for_client` /
# `_outstanding_invoices_for_supplier` above are left untouched (the Cheques
# page still uses them for plain booking-level cheque linking); everything
# below is additive and only wired into the Receipts screen.

def _used_booking_ids_in_customer_invoices(cdb, company_id):
    """Booking (Invoice) ids already rolled into a live (non-Void) customer
    invoice. Same scan customer_invoice_new/customer_invoice_create already
    do to stop a booking being added to two customer invoices — reused here
    to keep the receipt picker in sync with that rule."""
    ids = set()
    cis = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.status != "Void",
        CustomerInvoice.booking_ids_json.isnot(None),
    ).all()
    for ci in cis:
        try:
            ids.update(json.loads(ci.booking_ids_json))
        except (ValueError, TypeError):
            continue
    return ids


def _build_client_receipt_snapshots(company_id, clients):
    """Per-client KPI snapshot for the Receipts screen, keyed by client id
    (string, for JS lookup): total outstanding for that client, how many
    live credit customer invoices they have, and how many of their
    bookings still haven't been grouped into a customer invoice at all.
    used_booking_ids is computed once for the whole company and reused
    per client instead of re-querying it N times.

    total_outstanding is pulled from _debtor_summary()'s total_pending —
    NOT a raw sum of Invoice.balance across open bookings. That raw sum
    only reflects payments that were explicitly applied to a specific
    booking; an advance/unmatched payment (no invoice selected, or more
    than the selected invoices' balance) never touches any booking's
    balance field, so it was invisible to this card even though the
    Debtors list (_debtor_summary) already nets it out correctly. Reusing
    that same figure here keeps this screen's number identical to the
    Debtors list — no separate, drifting definition of "outstanding"."""
    cdb = get_cdb()
    used_booking_ids = _used_booking_ids_in_customer_invoices(cdb, company_id)
    pending_by_client = {d["id"]: d["total_pending"] for d in _debtor_summary(company_id)}
    snapshots = {}
    for c in clients:
        total_outstanding = round(pending_by_client.get(c.id, 0.0), 2)

        ci_count = (cdb.query(CustomerInvoice)
                    .filter_by(company_id=company_id, client_id=c.id, invoice_type="credit")
                    .filter(CustomerInvoice.status != "Void")
                    .count())

        all_bookings_q = cdb.query(Invoice).filter_by(company_id=company_id, client_id=c.id)
        if used_booking_ids:
            all_bookings_q = all_bookings_q.filter(~Invoice.id.in_(used_booking_ids))
        bookings_pending_ci = all_bookings_q.count()

        snapshots[str(c.id)] = {
            "total_outstanding": total_outstanding,
            "ci_count": ci_count,
            "bookings_pending_ci": bookings_pending_ci,
        }
    return json.dumps(snapshots)


def _receivables_for_client(company_id, client_id):
    """Everything a client can settle a receipt against: outstanding credit
    customer invoices only. Raw bookings (Invoice rows) never appear here
    on their own — a booking becomes payable through the Receipts screen
    only once it's grouped into a CustomerInvoice."""
    cdb = get_cdb()

    rows = []

    cis = (cdb.query(CustomerInvoice)
           .filter_by(company_id=company_id, client_id=client_id, invoice_type="credit")
           .filter(CustomerInvoice.status != "Void")
           .order_by(CustomerInvoice.invoice_date.asc())
           .all())
    for ci in cis:
        total = ci.grand_total or 0
        balance = ci.balance if ci.balance is not None else max(0, total - (ci.paid_amount or 0))
        if balance > 0:
            try:
                booking_count = len(json.loads(ci.booking_ids_json)) if ci.booking_ids_json else 0
            except (ValueError, TypeError):
                booking_count = 0
            rows.append({
                "kind":     "customer_invoice",
                "id":       ci.id,
                "ref":      ci.invoice_number,
                "date":     ci.invoice_date.strftime("%d %b %Y") if ci.invoice_date else "",
                "sort_dt":  ci.invoice_date or date.min,
                "total":    total,
                "balance":  balance,
                "bookings": booking_count,
            })

    rows.sort(key=lambda r: r["sort_dt"])
    for r in rows:
        r.pop("sort_dt", None)
    return rows


def _expand_ci_token(cdb, company_id, entity_id, ci_id, ci_for_booking, touched_ci_ids):
    """Resolve a 'ci:<id>' receipt token into its constituent booking ids,
    oldest booking first (same order the raw per-booking loop already
    applies money in). Records which CustomerInvoice each booking belongs
    to so receipt_save can enrich the ledger narration and, once the main
    loop is done, re-sync the customer invoice's own paid_amount/balance/
    status from what actually landed on its bookings."""
    ci = cdb.query(CustomerInvoice).filter_by(
        id=ci_id, company_id=company_id, client_id=entity_id
    ).first()
    if not ci:
        return []
    touched_ci_ids.add(ci.id)
    try:
        booking_ids = json.loads(ci.booking_ids_json) if ci.booking_ids_json else []
    except (ValueError, TypeError):
        booking_ids = []
    if not booking_ids:
        return []
    bookings = (cdb.query(Invoice)
                .filter(Invoice.id.in_(booking_ids), Invoice.company_id == company_id)
                .order_by(Invoice.date.asc())
                .all())
    expanded = []
    for b in bookings:
        expanded.append(b.id)
        ci_for_booking[b.id] = ci
    return expanded


def _sync_customer_invoice_payment(cdb, company_id, ci):
    """Re-derive a customer invoice's paid_amount/balance/status from the
    current paid_amount of its own constituent bookings. The customer
    invoice is a view over its bookings' payment state, not a separate
    ledger — it must never drift from them."""
    try:
        booking_ids = json.loads(ci.booking_ids_json) if ci.booking_ids_json else []
    except (ValueError, TypeError):
        booking_ids = []
    bookings = (cdb.query(Invoice)
                .filter(Invoice.id.in_(booking_ids), Invoice.company_id == company_id)
                .all()) if booking_ids else []
    ci.paid_amount = sum((b.paid_amount or 0) for b in bookings)
    ci.balance = max(0, (ci.grand_total or 0) - ci.paid_amount)
    if ci.balance <= 0:
        ci.status = "Paid"
    elif ci.paid_amount > 0:
        ci.status = "Partial"
    else:
        ci.status = "Pending"


@app.route("/receipts/new")
@login_required
@require_permission("receipts_payments", "view")
def receipt_new():
    cdb        = get_cdb()
    company_id = get_current_company()
    # Receipts only makes sense against credit clients — a Cash-Only client
    # settles at the time of billing and never carries a balance to receipt
    # against, so it's dropped from this picker entirely (same convention
    # already used for the Clients/credit screens elsewhere in this file).
    all_clients    = (cdb.query(Client)
                       .filter_by(company_id=company_id)
                       .filter(Client.client_type != "Cash-Only")
                       .order_by(Client.name).all())
    bank_accounts  = cdb.query(BankAccount).filter_by(company_id=company_id, status='Active').all()
    selected_id    = request.args.get("client_id", type=int)
    invoices_json  = _build_invoices_json(company_id, all_clients, _receivables_for_client)
    client_kpis_json = _build_client_receipt_snapshots(company_id, all_clients)

    # ── Live-computed pending, not the cached Client.pending column ────────
    # Same fix as payment_new()'s live_payable: Client.pending is mutated by
    # hand at 10+ call sites and can drift. CustomerInvoice(grand_total -
    # paid_amount) is the same source _receivables_for_client already uses
    # for the bill list below, so this keeps the dropdown and the bill list
    # it opens in sync.
    live_pending_rows = (
        cdb.query(
            CustomerInvoice.client_id,
            func.sum(CustomerInvoice.grand_total - CustomerInvoice.paid_amount - CustomerInvoice.note_adjustment)
        )
        .filter(
            CustomerInvoice.company_id == company_id,
            CustomerInvoice.invoice_type == "credit",
            CustomerInvoice.status != "Void",
        )
        .group_by(CustomerInvoice.client_id)
        .all()
    )
    live_pending_by_client = {cid: (total or 0) for cid, total in live_pending_rows}
    for c in all_clients:
        c.live_pending = round(
            (c.opening_balance or 0) + live_pending_by_client.get(c.id, 0), 2
        )

    # Date-wise filter for history
    date_from_str = request.args.get("date_from", "")
    date_to_str   = request.args.get("date_to", "")
    date_from = date.fromisoformat(date_from_str) if date_from_str else None
    date_to   = date.fromisoformat(date_to_str) if date_to_str else None
    has_date_filter = bool(date_from or date_to)

    # Search filter for history — matches reference, description, notes, or exact amount
    search_q = request.args.get("q", "").strip()
    hist_limit = 1000 if (has_date_filter or search_q) else 100

    def _apply_search(query, model):
        if not search_q:
            return query
        like_q = f"%{search_q}%"
        conditions = [
            model.reference.ilike(like_q),
            model.description.ilike(like_q),
            model.notes.ilike(like_q),
            model.party_name.ilike(like_q),
        ]
        try:
            conditions.append(model.amount == float(search_q))
        except ValueError:
            pass
        return query.filter(or_(*conditions))

    # Build receipt history — cash + bank transactions
    history = []
    cash_q = cdb.query(CashTransaction).filter_by(company_id=company_id, category="Receipt")
    if date_from:
        cash_q = cash_q.filter(CashTransaction.date >= date_from)
    if date_to:
        cash_q = cash_q.filter(CashTransaction.date <= date_to)
    cash_q = _apply_search(cash_q, CashTransaction)
    cash_receipts = cash_q.order_by(CashTransaction.date.desc()).limit(hist_limit).all()
    for t in cash_receipts:
        history.append({
            "id":          t.id,
            "txn_type":    "cash",
            "date":        t.date.strftime("%d %b %Y") if t.date else "",
            "sort_date":   t.date or date.min,
            "reference":   t.reference or "—",
            "client":      t.party_name or "—",
            "description": t.description,
            "amount":      t.amount,
            "mode":        "Cash",
            "bank_name":   "Cash in Hand",
            "notes":       t.notes or "",
        })

    bank_q = (cdb.query(BankTransaction)
              .filter_by(company_id=company_id, type="credit"))
              
    if date_from:
        bank_q = bank_q.filter(BankTransaction.date >= date_from)
    if date_to:
        bank_q = bank_q.filter(BankTransaction.date <= date_to)
    bank_q = _apply_search(bank_q, BankTransaction)
    bank_receipts = bank_q.order_by(BankTransaction.date.desc()).limit(hist_limit).all()
    for t in bank_receipts:
        bank_name = ""
        if t.bank_account:
            bank_name = f"{t.bank_account.bank_name} – {t.bank_account.account_name}"
        history.append({
            "id":          t.id,
            "txn_type":    "bank",
            "date":        t.date.strftime("%d %b %Y") if t.date else "",
            "sort_date":   t.date or date.min,
            "reference":   t.reference or "—",
            "client":      t.party_name or "—",
            "description": t.description,
            "amount":      t.amount,
            "mode":        t.transaction_mode or "Bank",
            "bank_name":   bank_name,
            "notes":       t.notes or "",
        })
    history.sort(key=lambda x: x["sort_date"], reverse=True)

    # entities carry a `.live_pending` attribute (set above) —
    # record_receipt.html reads e.live_pending, not e.pending.
    return render_template(
        "record_receipt.html",
        entities=all_clients,
        bank_accounts=bank_accounts,
        invoices_json=invoices_json,
        client_kpis_json=client_kpis_json,
        selected_id=selected_id,
        today=str(today_ist()),
        history=history,
        date_from=date_from_str,
        date_to=date_to_str,
        search_q=search_q,
    )


@app.route("/receipts/save", methods=["POST"])
@login_required
@require_permission("receipts_payments", "create")
def receipt_save():
    cdb         = get_cdb()
    company_id  = get_current_company()
    entity_id   = request.form.get("entity_id", type=int)
    amount      = request.form.get("amount", type=float, default=0)
    narration   = request.form.get("narration", "")
    pay_mode    = request.form.get("pay_mode", "Cash")
    bank_account_id = request.form.get("bank_account_id", type=int)
    txn_date_str = request.form.get("txn_date")
    txn_date    = date.fromisoformat(txn_date_str) if txn_date_str else today_ist()

    if not entity_id or amount <= 0:
        flash("Please select a client and enter a valid amount.", "error")
        return redirect(url_for("receipt_new"))

    client = cdb.query(Client).filter_by(id=entity_id, company_id=company_id).first()
    client_name = get_party_name(client_id=entity_id)

    # Validate bank account required for non-cash
    bank_account = None
    if pay_mode.lower() != "cash":
        if not bank_account_id:
            flash("Please select a bank account for non-cash payments.", "error")
            return redirect(url_for("receipt_new"))
        bank_account = cdb.query(BankAccount).filter_by(
            id=bank_account_id, company_id=company_id, status='Active'
        ).first()
        if not bank_account:
            flash("Selected bank account not found or inactive.", "error")
            return redirect(url_for("receipt_new"))

    # Selected rows arrive as tokens: "ci:<id>" for a customer invoice,
    # "b:<id>" for a raw booking (a bare numeric id is treated as a raw
    # booking too, for backward compatibility with any already-rendered
    # form). A "ci:" token is expanded into its constituent bookings here
    # so the rest of this function — the apply/settle loop, cash/bank
    # ledger writes, client.pending update — runs exactly as it always has,
    # unchanged, regardless of which picker row the money came in against.
    ci_for_booking = {}   # booking Invoice.id -> its CustomerInvoice
    touched_ci_ids = set()
    invoice_ids = []
    for tok in request.form.get("invoice_ids", "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        if tok.startswith("ci:"):
            try:
                ci_id = int(tok.split(":", 1)[1])
            except ValueError:
                continue
            invoice_ids.extend(
                _expand_ci_token(cdb, company_id, entity_id, ci_id, ci_for_booking, touched_ci_ids)
            )
        elif tok.startswith("b:"):
            try:
                invoice_ids.append(int(tok.split(":", 1)[1]))
            except ValueError:
                continue
        else:
            try:
                invoice_ids.append(int(tok))
            except ValueError:
                continue

    # NOTE: deliberately no "if not invoice_ids: auto-apply against every
    # outstanding invoice" fallback here. A receipt with nothing selected in
    # the picker is a random/unreferenced amount — it must be recorded as-is
    # with no bill reference, not silently split across the client's whole
    # outstanding book. See the `remaining > 0` advance block below, which
    # is what actually records it.

    remaining = amount
    settled   = 0

    # Money is applied booking-by-booking (oldest first) so every booking's
    # own paid_amount/balance/status stays accurate. UNLIKE the old version,
    # this no longer writes one ledger row per customer invoice touched —
    # a single receipt submission (one amount, one selection of bills) is
    # ONE cash/bank ledger row, however many bills that amount happened to
    # cover. Splitting CR-001 and CR-002 into two rows just because they're
    # different CustomerInvoice records was the source of the "recorded
    # differently in the statement" confusion — the same 40,000 received in
    # one go must show as one 40,000 line, with both bill numbers in the
    # reference. `breakdown` stays booking-level (not bill-level) because
    # that's what the delete/reversal path needs regardless of whether a
    # booking sits under a CI or is a standalone bill.
    breakdown  = {}   # booking Invoice.id (str) -> amount applied
    ref_labels = []   # ordered, de-duplicated display refs (CI or booking)
    seen_refs  = set()

    for inv_id in invoice_ids:
        if remaining <= 0:
            break
        inv = cdb.query(Invoice).filter_by(id=inv_id, company_id=company_id).first()
        if not inv:
            continue

        inv_balance = getattr(inv, "balance", None)
        if inv_balance is None:
            inv_balance = inv.grand_total or 0

        apply        = min(remaining, inv_balance)
        remaining   -= apply
        inv_balance -= apply
        settled     += apply

        if hasattr(inv, "balance"):
            inv.balance = inv_balance
        if hasattr(inv, "paid_amount"):
            inv.paid_amount = (inv.paid_amount or 0) + apply

        if inv_balance <= 0:
            inv.status = "Paid"
        elif apply > 0:
            inv.status = "Partial"

        if apply > 0:
            breakdown[str(inv.id)] = breakdown.get(str(inv.id), 0.0) + apply
            ci = ci_for_booking.get(inv.id)
            label = ci.invoice_number if ci else inv.invoice_id
            if label not in seen_refs:
                seen_refs.add(label)
                ref_labels.append(label)

    # ── One ledger row for everything actually settled in this submission ──
    if settled > 0:
        if len(ref_labels) <= 3:
            ref_display = ", ".join(ref_labels)
        else:
            ref_display = ", ".join(ref_labels[:3]) + f" +{len(ref_labels) - 3} more"
        desc = f"Payment received against {ref_display} - {narration}".strip(" -")

        # Backward-compatible single-ref fields: only populated when exactly
        # one bill of that kind was touched, so older code paths that read
        # applied_ci_id / applied_ref_id for a single-invoice receipt keep
        # working unchanged. Multi-bill receipts rely on applied_ci_ids_json
        # and applied_breakdown_json instead (both booking-level, so they
        # cover CI-linked and standalone bookings alike).
        single_ci_id = next(iter(touched_ci_ids)) if len(touched_ci_ids) == 1 else None
        single_raw_invoice_id = (
            int(next(iter(breakdown))) if (not touched_ci_ids and len(breakdown) == 1) else None
        )
        if touched_ci_ids and not any(ci_for_booking.get(int(b)) is None for b in breakdown):
            applied_ref_type = "customer_invoice"
        elif not touched_ci_ids:
            applied_ref_type = "invoice"
        else:
            applied_ref_type = "mixed"

        common_kwargs = dict(
            company_id=company_id,
            date=txn_date,
            description=desc,
            amount=settled,
            reference=ref_display,
            party_name=client_name,
            created_by=get_current_user().get('email'),
            applied_ref_type=applied_ref_type,
            applied_ref_id=single_raw_invoice_id,
            applied_ci_id=single_ci_id,
            applied_ci_ids_json=json.dumps(list(touched_ci_ids)) if touched_ci_ids else None,
            applied_breakdown_json=json.dumps(breakdown),
        )
        if pay_mode.lower() == "cash":
            cash_txn = CashTransaction(
                type="income", category="Receipt",
                notes="Payment from client via Cash",
                **common_kwargs,
            )
            cdb.add(cash_txn)
        else:
            bank_txn = BankTransaction(
                bank_account_id=bank_account.id,
                type="credit", transaction_mode=pay_mode.title(),
                notes=narration,
                **common_kwargs,
            )
            cdb.add(bank_txn)
            bank_account.balance += settled

    # Any amount left over after settling the selected bills' balances must
    # still be recorded, not silently dropped. This is a genuinely separate
    # line from the settled amount above — it's the part of what the client
    # paid that wasn't matched to any bill, so keeping it as its own row
    # (rather than folding it into the settled row) is correct, not a
    # duplicate. The Reference/Narration field the user typed (e.g. "Advance
    # against future bill") is used as the reference here — free text is
    # allowed since there's no bill number to fall back on; only when the
    # user left it blank does this fall back to no reference (None), so the
    # history table's `h.reference or "—"` shows nothing rather than a
    # placeholder.
    if remaining > 0:
        advance_ref  = narration.strip() or None
        advance_desc = f"Advance receipt from client (not applied to a specific invoice) - {narration}".strip(" -")
        if pay_mode.lower() == "cash":
            cash_txn = CashTransaction(
                company_id=company_id,
                type="income",
                date=txn_date,
                category="Receipt",
                description=advance_desc,
                amount=remaining,
                reference=advance_ref,
                notes="Unapplied portion of receipt via Cash",
                party_name=client_name,
                created_by=get_current_user().get('email')
            )
            cdb.add(cash_txn)
        else:
            bank_txn = BankTransaction(
                bank_account_id=bank_account.id,
                company_id=company_id,
                type="credit",
                date=txn_date,
                description=advance_desc,
                amount=remaining,
                reference=advance_ref,
                transaction_mode=pay_mode.title(),
                notes=narration,
                party_name=client_name,
                created_by=get_current_user().get('email')
            )
            cdb.add(bank_txn)
            bank_account.balance += remaining

    if client and hasattr(client, "pending") and client.pending:
        client.pending = max(0, (client.pending or 0) - settled)

    # ── UPDATE CLIENT LAST PAYMENT DATE ──────────────────────────────
    if client:
        # Find the most recent payment date from CashTransaction or BankTransaction
        last_cash = cdb.query(CashTransaction).filter_by(
            company_id=company_id,
            party_name=client_name,
            category="Receipt"
        ).order_by(CashTransaction.date.desc()).first()
        
        last_bank = cdb.query(BankTransaction).filter_by(
            company_id=company_id,
            party_name=client_name,
            type="credit"
        ).order_by(BankTransaction.date.desc()).first()
        
        if last_cash and last_bank:
            client.last_payment = last_cash.date if last_cash.date > last_bank.date else last_bank.date
        elif last_cash:
            client.last_payment = last_cash.date
        elif last_bank:
            client.last_payment = last_bank.date    

    # ── Re-sync any customer invoices this receipt touched ───────────────
    # The loop above already updated each underlying booking's own
    # paid_amount/balance/status; pull the customer invoice's totals back
    # in line with that so it never shows a balance its bookings disagree
    # with.
    for ci_id in touched_ci_ids:
        ci = cdb.query(CustomerInvoice).filter_by(id=ci_id, company_id=company_id).first()
        if ci:
            _sync_customer_invoice_payment(cdb, company_id, ci)

    auto_txns = [x for x in cdb.new if isinstance(x, (CashTransaction, BankTransaction))]
    cdb.flush()
    for txn in auto_txns:
        _auto_post_settlement(cdb, company_id, txn, "receipt")
    cdb.commit()

    dest = bank_account.bank_name if bank_account else "Cash in Hand"
    flash(f"Receipt of {company_currency_symbol()} {amount:,.2f} recorded via {pay_mode} → {dest}. {narration}", "success")
    return redirect(url_for("debtors_list"))


@app.route("/payments/new")
@login_required
@require_permission("receipts_payments", "view")
def payment_new():
    cdb        = get_cdb()
    company_id = get_current_company()
    # TODO(Ravi): mirror the client-side "credit only" filter here once
    # there's a confirmed cash-vs-credit marker on Supplier — Client has
    # client_type == "Cash-Only" for this; nothing equivalent exists on
    # Supplier in the current schema, so all suppliers still show for now.
    all_suppliers  = cdb.query(Supplier).filter_by(company_id=company_id).order_by(Supplier.name).all()
    bank_accounts  = cdb.query(BankAccount).filter_by(company_id=company_id, status='Active').all()
    selected_id    = request.args.get("supplier_id", type=int)
    invoices_json  = _build_invoices_json(company_id, all_suppliers, _outstanding_invoices_for_supplier)

    # ── Live-computed payable, not the cached Supplier.payable column ──────
    # Pulled from _creditor_summary()'s total_pending — NOT a raw sum of
    # (grand_total - paid_amount) across purchase invoices. That raw sum
    # only reflects payments explicitly applied to a specific invoice; an
    # advance/unmatched payment (no invoice selected, or more than the
    # selected invoices' balance) never touches any invoice's paid_amount,
    # so it was invisible to this card even though the Creditors list
    # (_creditor_summary) already nets it out correctly. Reusing that same
    # figure here keeps this screen's number identical to the Creditors list.
    live_payable_by_supplier = {d["id"]: d["total_pending"] for d in _creditor_summary(company_id)}
    for sup in all_suppliers:
        sup.live_payable = round(live_payable_by_supplier.get(sup.id, 0.0), 2)

    # Date-wise filter for history
    date_from_str = request.args.get("date_from", "")
    date_to_str   = request.args.get("date_to", "")
    date_from = date.fromisoformat(date_from_str) if date_from_str else None
    date_to   = date.fromisoformat(date_to_str) if date_to_str else None
    has_date_filter = bool(date_from or date_to)

    # Search filter for history — matches reference, description, notes, or exact amount
    search_q = request.args.get("q", "").strip()
    hist_limit = 1000 if (has_date_filter or search_q) else 100

    def _apply_search(query, model):
        if not search_q:
            return query
        like_q = f"%{search_q}%"
        conditions = [
            model.reference.ilike(like_q),
            model.description.ilike(like_q),
            model.notes.ilike(like_q),
            model.party_name.ilike(like_q),
        ]
        try:
            conditions.append(model.amount == float(search_q))
        except ValueError:
            pass
        return query.filter(or_(*conditions))

    # Build payment history — cash + bank transactions
    history = []
    cash_q = cdb.query(CashTransaction).filter_by(company_id=company_id, category="Payment")
    if date_from:
        cash_q = cash_q.filter(CashTransaction.date >= date_from)
    if date_to:
        cash_q = cash_q.filter(CashTransaction.date <= date_to)
    cash_q = _apply_search(cash_q, CashTransaction)
    cash_payments = cash_q.order_by(CashTransaction.date.desc()).limit(hist_limit).all()
    for t in cash_payments:
        history.append({
            "id":          t.id,
            "txn_type":    "cash",
            "date":        t.date.strftime("%d %b %Y") if t.date else "",
            "sort_date":   t.date or date.min,
            "reference":   t.reference or "—",
            "supplier":    t.party_name or "—",
            "description": t.description,
            "amount":      t.amount,
            "mode":        "Cash",
            "bank_name":   "Cash in Hand",
            "notes":       t.notes or "",
        })

    bank_q = (cdb.query(BankTransaction)
              .filter_by(company_id=company_id, type="debit"))
    if date_from:
        bank_q = bank_q.filter(BankTransaction.date >= date_from)
    if date_to:
        bank_q = bank_q.filter(BankTransaction.date <= date_to)
    bank_q = _apply_search(bank_q, BankTransaction)
    bank_payments = bank_q.order_by(BankTransaction.date.desc()).limit(hist_limit).all()
    for t in bank_payments:
        bank_name = ""
        if t.bank_account:
            bank_name = f"{t.bank_account.bank_name} – {t.bank_account.account_name}"
        history.append({
            "id":          t.id,
            "txn_type":    "bank",
            "date":        t.date.strftime("%d %b %Y") if t.date else "",
            "sort_date":   t.date or date.min,
            "reference":   t.reference or "—",
            "supplier":    t.party_name or "—",
            "description": t.description,
            "amount":      t.amount,
            "mode":        t.transaction_mode or "Bank",
            "bank_name":   bank_name,
            "notes":       t.notes or "",
        })
    history.sort(key=lambda x: x["sort_date"], reverse=True)

    return render_template(
        "record_payment.html",
        entities=all_suppliers,
        bank_accounts=bank_accounts,
        invoices_json=invoices_json,
        selected_id=selected_id,
        today=str(today_ist()),
        history=history,
        date_from=date_from_str,
        date_to=date_to_str,
        search_q=search_q,
    )


@app.route("/payments/save", methods=["POST"])
@login_required
@require_permission("receipts_payments", "create")
def payment_save():
    cdb = get_cdb()
    company_id = get_current_company()
    entity_id = request.form.get("entity_id", type=int)
    amount = request.form.get("amount", type=float, default=0)
    invoice_ids = [int(x) for x in request.form.get("invoice_ids", "").split(",") if x.strip()]
    narration = request.form.get("narration", "")
    pay_mode = request.form.get("pay_mode", "Cash")
    bank_account_id = request.form.get("bank_account_id", type=int)
    txn_date_str = request.form.get("txn_date")
    txn_date = date.fromisoformat(txn_date_str) if txn_date_str else today_ist()

    if not entity_id or amount <= 0:
        flash("Please select a supplier and enter a valid amount.", "error")
        return redirect(url_for("payment_new"))

    supplier_entity = cdb.query(Supplier).filter_by(id=entity_id, company_id=company_id).first()
    if not supplier_entity:
        flash("Supplier not found.", "error")
        return redirect(url_for("payment_new"))

    supplier_name = get_party_name(supplier_id=entity_id)

    # Validate bank account required for non-cash
    bank_account = None
    if pay_mode.lower() != "cash":
        if not bank_account_id:
            flash("Please select a bank account for non-cash payments.", "error")
            return redirect(url_for("payment_new"))
        bank_account = cdb.query(BankAccount).filter_by(
            id=bank_account_id, company_id=company_id, status='Active'
        ).first()
        if not bank_account:
            flash("Selected bank account not found or inactive.", "error")
            return redirect(url_for("payment_new"))

    # NOTE: deliberately no auto-fill of every outstanding purchase invoice
    # when nothing is selected. An unselected payment is a random/unreferenced
    # amount and must be recorded as such (see the `remaining > 0` advance
    # block below) — not silently split across the supplier's whole payable book.

    remaining = amount
    settled = 0
    applied_invoice_ids = []

    # ── APPLY PAYMENT TO INVOICES — ONE LEDGER ROW PER SUBMISSION ──
    # Same fix as receipt_save: a single payment submission (one amount,
    # one selection of bills) writes ONE cash/bank row, however many
    # PurchaseInvoices that amount happened to cover. Splitting PINV-001
    # and PINV-002 into two rows just because they're different invoice
    # records is exactly the "recorded differently in the statement"
    # confusion this is fixing. `breakdown` stays invoice-level (there's
    # no CI-style grouping layer on the purchase side) and is what the
    # delete/reversal path uses to peel each invoice back correctly.
    breakdown  = {}   # PurchaseInvoice.id (str) -> amount applied
    ref_labels = []   # ordered, de-duplicated display refs

    for inv_id in invoice_ids:
        if remaining <= 0:
            break
        inv = cdb.query(PurchaseInvoice).filter_by(id=inv_id, company_id=company_id).first()
        if not inv:
            continue

        inv_balance = inv.balance or (inv.grand_total or 0)
        if inv_balance <= 0:
            continue

        apply_amount = min(remaining, inv_balance)
        remaining -= apply_amount
        settled += apply_amount
        applied_invoice_ids.append(inv_id)

        # Update invoice
        inv.balance = inv_balance - apply_amount
        inv.paid_amount = (inv.paid_amount or 0) + apply_amount

        if inv.balance <= 0:
            inv.status = "Paid"
        elif inv.paid_amount > 0:
            inv.status = "Partial"
        else:
            inv.status = "Pending"

        # Update supplier payable
        if inv.supplier:
            inv.supplier.payable = max(0, (inv.supplier.payable or 0) - apply_amount)

        breakdown[str(inv.id)] = breakdown.get(str(inv.id), 0.0) + apply_amount
        txn_reference = inv.invoice_number or inv.invoice_id
        if txn_reference not in ref_labels:
            ref_labels.append(txn_reference)

    # ── One ledger row for everything actually settled in this submission ──
    if settled > 0:
        if len(ref_labels) <= 3:
            ref_display = ", ".join(ref_labels)
        else:
            ref_display = ", ".join(ref_labels[:3]) + f" +{len(ref_labels) - 3} more"
        desc = f"Payment made against {ref_display}"
        if narration:
            desc += f" - {narration}"

        # Single-invoice backward-compat field, same convention as receipts.
        single_invoice_id = int(next(iter(breakdown))) if len(breakdown) == 1 else None

        common_kwargs = dict(
            company_id=company_id,
            date=txn_date,
            description=desc,
            amount=settled,
            reference=ref_display,
            party_name=supplier_name,
            created_by=get_current_user().get('email'),
            applied_ref_type="purchase_invoice",
            applied_ref_id=single_invoice_id,
            applied_breakdown_json=json.dumps(breakdown),
        )
        if pay_mode.lower() == "cash":
            cash_txn = CashTransaction(
                type="expense", category="Payment",
                notes=f"Payment of {company_currency_symbol()} {settled:,.2f} to supplier via Cash",
                **common_kwargs,
            )
            cdb.add(cash_txn)
        else:
            bank_txn = BankTransaction(
                bank_account_id=bank_account.id,
                type="debit", transaction_mode=pay_mode.title(),
                notes=narration,
                **common_kwargs,
            )
            cdb.add(bank_txn)

    # ── ANY LEFTOVER AFTER SETTLING SELECTED INVOICES ──
    # Kept as its own separate row (this is genuinely unmatched money, not
    # a duplicate of the settled row above). Uses whatever the user typed in
    # Reference/Narration as the reference — free text like "Advance against
    # future bill" is allowed since there's no invoice number to fall back
    # on; only when left blank does this fall back to no reference (None),
    # so the history table shows nothing rather than a placeholder.
    if remaining > 0:
        advance_ref  = narration.strip() or None
        advance_desc = f"Advance payment to supplier (not applied to a specific invoice)"
        if narration:
            advance_desc += f" - {narration}"
        if pay_mode.lower() == "cash":
            cash_txn = CashTransaction(
                company_id=company_id,
                type="expense",
                date=txn_date,
                category="Payment",
                description=advance_desc,
                amount=remaining,
                reference=advance_ref,
                notes=f"Unapplied portion of payment via Cash",
                party_name=supplier_name,
                created_by=get_current_user().get('email'),
            )
            cdb.add(cash_txn)
        else:
            bank_txn = BankTransaction(
                bank_account_id=bank_account.id,
                company_id=company_id,
                type="debit",
                date=txn_date,
                description=advance_desc,
                amount=remaining,
                reference=advance_ref,
                transaction_mode=pay_mode.title(),
                notes=narration,
                party_name=supplier_name,
                created_by=get_current_user().get('email'),
            )
            cdb.add(bank_txn)

    # A non-cash payment debits the bank account by the FULL amount
    # entered, regardless of how it was split across invoices/advance.
    if pay_mode.lower() != "cash" and amount > 0:
        bank_account.balance -= amount

    auto_txns = [x for x in cdb.new if isinstance(x, (CashTransaction, BankTransaction))]
    cdb.flush()
    for txn in auto_txns:
        _auto_post_settlement(cdb, company_id, txn, "payment")
    cdb.commit()

    # ── FLASH MESSAGE ──
    dest = bank_account.bank_name if bank_account else "Cash in Hand"
    if settled > 0 and amount - settled > 0:
        flash(f"✅ Payment of {company_currency_symbol()} {amount:,.2f} recorded via {pay_mode} → {dest}. {company_currency_symbol()} {settled:,.2f} applied to invoices, {company_currency_symbol()} {amount - settled:,.2f} recorded as advance/unapplied. {narration}", "success")
    elif settled > 0:
        flash(f"✅ Payment of {company_currency_symbol()} {settled:,.2f} applied to invoices via {pay_mode} → {dest}. {narration}", "success")
    else:
        flash(f"✅ Advance payment of {company_currency_symbol()} {amount:,.2f} recorded via {pay_mode} → {dest}. {narration}", "success")

    return redirect(url_for("creditors_list"))

# ─────────────────────────────────────────────────────────────────────────────
# ── Backup & Restore Routes ───────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/backup")
@login_required
@require_permission("backup", "view")
def backup():
    """Backup management page"""
    company_id = get_current_company()
    
    # Define backup destinations (fallback)
    backup_destinations = {
        "local": "Local Storage",
        "s3": "Amazon S3",
        "gcs": "Google Cloud Storage",
        "ftp": "FTP/SFTP Server",
    }
    
    backups = []
    
    try:
        from backup_utils import list_backups, BACKUP_DESTINATIONS
        backups = list_backups(company_id)
        backup_destinations = BACKUP_DESTINATIONS
    except ImportError as e:
        print(f"Could not import backup_utils: {e}")
        flash("Backup utilities not fully configured. Some features may be limited.", "warning")
    except Exception as e:
        print(f"Error loading backups: {e}")
        flash(f"Error loading backups: {str(e)}", "error")
    
    return render_template("backup.html", 
                         active='backup',
                         backups=backups,
                         backup_destinations=backup_destinations)
                         

@app.route("/backup/create", methods=["POST"])
@login_required
@require_permission("backup", "create")
def create_backup():
    """Create a new backup with optional date range"""
    company_id = get_current_company()
    include_attachments = request.form.get("include_attachments", "true") == "true"
    
    # Get date range from form
    from_date_str = request.form.get("from_date", "").strip()
    to_date_str = request.form.get("to_date", "").strip()
    
    from_date = None
    to_date = None
    
    if from_date_str:
        try:
            from_date = date.fromisoformat(from_date_str)
        except ValueError:
            flash("Invalid from date format. Please use YYYY-MM-DD.", "error")
            return redirect(url_for("backup"))
    
    if to_date_str:
        try:
            to_date = date.fromisoformat(to_date_str)
        except ValueError:
            flash("Invalid to date format. Please use YYYY-MM-DD.", "error")
            return redirect(url_for("backup"))
    
    # Validate date range
    if from_date and to_date and from_date > to_date:
        flash("From date cannot be after to date.", "error")
        return redirect(url_for("backup"))
    
    try:
        from backup_utils import create_company_backup, BACKUP_DESTINATIONS
        
        backup_info = create_company_backup(
            company_id, 
            include_attachments,
            from_date=from_date,
            to_date=to_date
        )
        
        # Build date range message
        date_msg = ""
        if from_date and to_date:
            date_msg = f" (from {from_date.strftime('%d %b %Y')} to {to_date.strftime('%d %b %Y')})"
        elif from_date:
            date_msg = f" (from {from_date.strftime('%d %b %Y')})"
        elif to_date:
            date_msg = f" (up to {to_date.strftime('%d %b %Y')})"
        
        flash(f"Backup created successfully! File size: {backup_info['size_mb']} MB{date_msg}", "success")
        
        # Optionally upload to cloud
        if request.form.get("upload_to_cloud"):
            destination = request.form.get("cloud_destination")
            config = {
                'access_key': request.form.get('access_key'),
                'secret_key': request.form.get('secret_key'),
                'bucket': request.form.get('bucket'),
                'region': request.form.get('region', 'us-east-1')
            }
            from backup_utils import upload_backup_to_cloud
            upload_backup_to_cloud(backup_info['backup_id'], destination, config)
            flash("Backup also uploaded to cloud storage!", "success")
            
    except Exception as e:
        flash(f"Backup failed: {str(e)}", "error")
    
    return redirect(url_for("backup"))

@app.route("/backup/restore/<backup_id>", methods=["POST"])
@login_required
@require_permission("backup", "edit")
def restore_backup(backup_id):
    """Restore from a backup"""
    company_id = get_current_company()
    user = get_current_user()
    
    try:
        from backup_utils import restore_from_backup
        result = restore_from_backup(backup_id, user.get('email'))
        
        flash(f"Restore completed successfully! Company data restored from backup {backup_id}", "success")
        
    except Exception as e:
        flash(f"Restore failed: {str(e)}", "error")
    
    return redirect(url_for("backup"))

@app.route("/backup/download/<backup_id>")
@login_required
@require_permission("backup", "view")
def download_backup(backup_id):
    """Download backup file"""
    company_id = get_current_company()
    
    from platform_models import BackupRecord
    backup = BackupRecord.query.filter_by(backup_id=backup_id, company_id=company_id).first()
    
    if not backup or not os.path.exists(backup.backup_file_path):
        flash("Backup file not found", "error")
        return redirect(url_for("backup"))
    
    return send_file(
        backup.backup_file_path,
        as_attachment=True,
        download_name=f"{backup_id}.zip"
    )

@app.route("/backup/delete/<backup_id>", methods=["POST"])
@login_required
@owner_required
@require_admin_password
def delete_backup_record(backup_id):
    """Delete a backup"""
    company_id = get_current_company()
    
    try:
        from backup_utils import delete_backup
        if delete_backup(backup_id):
            flash("Backup deleted successfully", "success")
        else:
            flash("Backup not found", "error")
    except Exception as e:
        flash(f"Error deleting backup: {str(e)}", "error")
    
    return redirect(url_for("backup"))

@app.route("/backup/schedule", methods=["POST"])
@login_required
@require_permission("backup", "edit")
def schedule_backup():
    """Schedule automatic backups"""
    company_id = get_current_company()
    
    frequency = request.form.get("frequency")
    time_of_day = request.form.get("time_of_day")
    retention_days = request.form.get("retention_days", 30)
    upload_to_cloud = request.form.get("upload_to_cloud") == "true"
    
    from platform_models import BackupSchedule
    
    # Save schedule to database
    schedule = BackupSchedule.query.filter_by(company_id=company_id).first()
    
    if not schedule:
        schedule = BackupSchedule(company_id=company_id)
        db.session.add(schedule)
    
    schedule.frequency = frequency
    schedule.time_of_day = time_of_day
    schedule.retention_days = int(retention_days)
    schedule.upload_to_cloud = upload_to_cloud
    schedule.last_backup = None
    
    # Calculate next backup
    from datetime import datetime, timedelta
    now = datetime.now()
    hour, minute = map(int, time_of_day.split(':'))
    
    if frequency == "daily":
        next_date = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_date <= now:
            next_date += timedelta(days=1)
    elif frequency == "weekly":
        days_ahead = 6 - now.weekday()
        next_date = (now + timedelta(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    elif frequency == "monthly":
        next_date = now.replace(day=1, hour=hour, minute=minute, second=0, microsecond=0)
        if next_date <= now:
            if next_date.month == 12:
                next_date = next_date.replace(year=next_date.year + 1, month=1)
            else:
                next_date = next_date.replace(month=next_date.month + 1)
    else:
        next_date = now + timedelta(days=1)
    
    schedule.next_backup = next_date
    schedule.is_active = True
    
    db.session.commit()
    flash(f"Automatic backup scheduled {frequency} at {time_of_day}", "success")
    
    return redirect(url_for("backup"))

@app.route("/backup/upload-to-cloud/<backup_id>", methods=["POST"])
@login_required
@require_permission("backup", "edit")
def upload_backup_to_cloud_route(backup_id):
    """Upload existing backup to cloud"""
    company_id = get_current_company()
    
    destination = request.form.get("destination")
    config = {
        'access_key': request.form.get('access_key'),
        'secret_key': request.form.get('secret_key'),
        'bucket': request.form.get('bucket'),
        'region': request.form.get('region', 'us-east-1'),
        'host': request.form.get('host'),
        'port': request.form.get('port', 22),
        'username': request.form.get('username'),
        'password': request.form.get('password'),
        'path': request.form.get('path', '/'),
        'credentials_file': request.form.get('credentials_file'),
    }
    
    try:
        from backup_utils import upload_backup_to_cloud
        upload_backup_to_cloud(backup_id, destination, config)
        flash("Backup uploaded to cloud successfully!", "success")
    except Exception as e:
        flash(f"Cloud upload failed: {str(e)}", "error")
    
    return redirect(url_for("backup"))

# Start backup scheduler
try:
    from backup_scheduler import start_backup_scheduler
    start_backup_scheduler()
except Exception as e:
    print(f"Could not start backup scheduler: {e}")


@app.route("/backup/upload", methods=["POST"])
@login_required
@require_permission("backup", "edit")
def upload_backup():
    """
    Upload a backup .zip file and restore it.
    This allows restoring from a downloaded backup file.
    """
    company_id = get_current_company()
    user = get_current_user()
    
    if 'backup_file' not in request.files:
        flash("No file selected", "error")
        return redirect(url_for("backup"))
    
    file = request.files['backup_file']
    if file.filename == '':
        flash("No file selected", "error")
        return redirect(url_for("backup"))
    
    if not file.filename.endswith('.zip'):
        flash("Please upload a .zip backup file", "error")
        return redirect(url_for("backup"))
    
    try:
        from backup_utils import restore_from_uploaded_backup
        
        # Save uploaded file temporarily
        import tempfile
        import os
        
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, file.filename)
        file.save(temp_path)
        
        # Restore from the uploaded file
        result = restore_from_uploaded_backup(
            company_id=company_id, 
            file_path=temp_path,
            user_email=user.get('email', 'unknown')
        )
        
        # Clean up
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        if result and result.get('success'):
            flash(f"✅ Restore completed successfully from {file.filename}", "success")
        else:
            error_msg = result.get('message', 'Unknown error') if result else 'Unknown error'
            flash(f"❌ Restore failed: {error_msg}", "error")
            
    except Exception as e:
        flash(f"❌ Restore failed: {str(e)}", "error")
        print(f"Upload restore error: {e}")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for("backup"))

# ─────────────────────────────────────────────────────────────────────────────
# ── App entry point ───────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
def _find_purchase_invoice_for_reversal(cdb, company_id, txn):
    """Resolve the exact PurchaseInvoice a payment transaction should be
    reversed against. Prefers the structural applied_ref_id column
    (unambiguous, set by every payment recorded after this fix). Falls
    back to matching the display `reference` string against
    invoice_number/invoice_id for transactions recorded before the
    applied_ref_id column existed — never falls back to int(reference),
    since invoice_id/invoice_number are non-numeric strings (e.g.
    "PINV-0001") and that cast just silently failed, which is the bug
    this replaces.
    """
    if txn.applied_ref_type == "purchase_invoice" and txn.applied_ref_id:
        return cdb.query(PurchaseInvoice).filter_by(
            id=txn.applied_ref_id, company_id=company_id
        ).first()
    ref = txn.reference
    if ref and ref != "ADVANCE":
        return cdb.query(PurchaseInvoice).filter(
            PurchaseInvoice.company_id == company_id,
            or_(PurchaseInvoice.invoice_number == ref, PurchaseInvoice.invoice_id == ref)
        ).first()
    return None


@app.route("/payment/delete", methods=["GET", "POST"])
@login_required
@owner_required
@require_admin_password
def delete_payment():
    txn_id = request.args.get("id", type=int)
    txn_type = request.args.get("type", "cash")  # "cash" or "bank"
    company_id = get_current_company()
    cdb = get_cdb()

    if not company_id or not cdb:
        flash("Could not connect to database.", "error")
        return redirect(url_for("payment_new"))

    try:
        # ── 1. Find the transaction (cash or bank) ──
        if txn_type == "bank":
            txn = cdb.query(BankTransaction).filter_by(
                id=txn_id,
                company_id=company_id,
                type='debit'
            ).first()
        else:
            txn = cdb.query(CashTransaction).filter_by(
                id=txn_id,
                company_id=company_id,
                type='expense',
                category='Payment'
            ).first()

        if not txn:
            flash("Payment transaction not found.", "error")
            return redirect(url_for("payment_new"))

        amount = txn.amount
        supplier_name = txn.party_name

        print(f"[ADMIN] Deleting {txn_type} payment: {company_currency_symbol()} {amount} to {supplier_name}")

        # ── 2. Reverse whatever this payment was actually applied to ──
        # A single payment submission that settled several PurchaseInvoices
        # at once (see payment_save) carries its own applied_breakdown_json
        # — {purchase_invoice id: amount} — so every invoice touched gets
        # exactly the amount it received peeled back off. Older/simple rows
        # without a breakdown fall back to the single-invoice resolution.
        breakdown = None
        if getattr(txn, "applied_breakdown_json", None):
            try:
                breakdown = json.loads(txn.applied_breakdown_json)
            except (ValueError, TypeError):
                breakdown = None

        if breakdown:
            supplier_obj = None
            for pinv_id_str, pinv_amount in breakdown.items():
                try:
                    pinv_id = int(pinv_id_str)
                except ValueError:
                    continue
                inv = cdb.query(PurchaseInvoice).filter_by(id=pinv_id, company_id=company_id).first()
                if not inv:
                    continue
                inv.paid_amount = max(0, (inv.paid_amount or 0) - pinv_amount)
                inv.balance = (inv.grand_total or 0) - (inv.paid_amount or 0)
                if inv.balance <= 0:
                    inv.status = "Paid"
                elif inv.paid_amount > 0:
                    inv.status = "Partial"
                else:
                    inv.status = "Pending"
                if supplier_obj is None and inv.supplier_id:
                    supplier_obj = cdb.query(Supplier).filter_by(id=inv.supplier_id, company_id=company_id).first()
            if supplier_obj:
                supplier_obj.payable = (supplier_obj.payable or 0) + amount
            print(f"[ADMIN] Reset {len(breakdown)} invoice(s) from breakdown")
        else:
            inv = _find_purchase_invoice_for_reversal(cdb, company_id, txn)
            if inv:
                inv.paid_amount = max(0, (inv.paid_amount or 0) - amount)
                inv.balance = (inv.grand_total or 0) - (inv.paid_amount or 0)
                if inv.balance <= 0:
                    inv.status = "Paid"
                elif inv.paid_amount > 0:
                    inv.status = "Partial"
                else:
                    inv.status = "Pending"

                # Reset supplier payable
                if inv.supplier_id:
                    supplier = cdb.query(Supplier).filter_by(id=inv.supplier_id, company_id=company_id).first()
                    if supplier:
                        supplier.payable = (supplier.payable or 0) + amount
                print(f"[ADMIN] Reset invoice {inv.invoice_id}")

        # ── 3. If this was a non-cash payment, credit the bank account back ──
        if txn_type == "bank" and getattr(txn, "bank_account", None):
            txn.bank_account.balance += amount

        # ── 4. Delete the transaction ──
        _reverse_settlement_journal(cdb, company_id, txn, "payment", "Payment edited/deleted")
        cdb.delete(txn)
        cdb.commit()

        flash(f"✅ Payment of {company_currency_symbol()} {amount:,.2f} to {supplier_name} has been deleted and reversed.", "success")

    except Exception as e:
        cdb.rollback()
        print(f"[ADMIN] Error deleting payment: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Error deleting payment: {str(e)}", "error")

    return redirect(url_for("payment_new"))


def _find_receivable_for_reversal(cdb, company_id, txn):
    """Resolve the exact (booking) Invoice a receipt transaction should be
    reversed against, plus its parent CustomerInvoice if any (so that can
    be re-synced too). Same applied_ref_id-first, string-fallback approach
    as _find_purchase_invoice_for_reversal — see that function's docstring."""
    if txn.applied_ref_type == "invoice" and txn.applied_ref_id:
        inv = cdb.query(Invoice).filter_by(id=txn.applied_ref_id, company_id=company_id).first()
        ci = None
        if txn.applied_ci_id:
            ci = cdb.query(CustomerInvoice).filter_by(id=txn.applied_ci_id, company_id=company_id).first()
        return inv, ci

    # New-style lumped customer-invoice receipt (one row for the whole
    # invoice, several bookings behind it) — go straight to applied_ci_id
    # instead of falling through to the string-matching fallback below.
    # Same known limitation as the old string-matched CI rows: which
    # specific booking(s) this money landed on isn't recoverable from the
    # transaction alone, so only the CI gets re-synced, not the bookings.
    if txn.applied_ref_type == "customer_invoice" and txn.applied_ci_id:
        ci = cdb.query(CustomerInvoice).filter_by(id=txn.applied_ci_id, company_id=company_id).first()
        return None, ci

    ref = txn.reference
    if not ref or ref == "ADVANCE":
        return None, None

    # Old rows before applied_ref_id existed: reference is either a raw
    # booking invoice_id or a CustomerInvoice invoice_number.
    inv = cdb.query(Invoice).filter_by(company_id=company_id, invoice_id=ref).first()
    if inv:
        return inv, None
    ci = cdb.query(CustomerInvoice).filter_by(company_id=company_id, invoice_number=ref).first()
    if ci:
        # Can't tell which specific booking under this CI the old row
        # belonged to — nothing safe to reverse at the booking level, but
        # the CI itself can still be re-synced after the transaction is
        # gone using whatever the booking totals now say.
        return None, ci
    return None, None


@app.route("/receipt/delete", methods=["GET", "POST"])
@login_required
@owner_required
@require_admin_password
def delete_receipt():
    txn_id = request.args.get("id", type=int)
    txn_type = request.args.get("type", "cash")  # "cash" or "bank"
    company_id = get_current_company()
    cdb = get_cdb()

    if not company_id or not cdb:
        flash("Could not connect to database.", "error")
        return redirect(url_for("receipt_new"))

    try:
        # ── 1. Find the transaction (cash or bank) ──
        if txn_type == "bank":
            txn = cdb.query(BankTransaction).filter_by(
                id=txn_id,
                company_id=company_id,
                type='credit'
            ).first()
        else:
            txn = cdb.query(CashTransaction).filter_by(
                id=txn_id,
                company_id=company_id,
                type='income',
                category='Receipt'
            ).first()

        if not txn:
            flash("Receipt transaction not found.", "error")
            return redirect(url_for("receipt_new"))

        amount = txn.amount
        client_name = txn.party_name

        print(f"[ADMIN] Deleting {txn_type} receipt: {company_currency_symbol()} {amount} from {client_name}")

        # ── 2. Reverse whatever this receipt was actually applied to ──
        # A lumped customer-invoice receipt (one row covering several
        # bookings) carries its own applied_breakdown_json — {booking id:
        # amount} — so every booking gets exactly the amount it received
        # peeled back off, instead of only re-syncing the CustomerInvoice's
        # rolled-up totals. Anything without a breakdown (single-booking
        # receipts, legacy rows) falls back to the existing single-invoice
        # resolution.
        breakdown = None
        if getattr(txn, "applied_breakdown_json", None):
            try:
                breakdown = json.loads(txn.applied_breakdown_json)
            except (ValueError, TypeError):
                breakdown = None

        cis_to_resync = []
        if breakdown:
            client_obj = None
            for booking_id_str, booking_amount in breakdown.items():
                try:
                    booking_id = int(booking_id_str)
                except ValueError:
                    continue
                inv = cdb.query(Invoice).filter_by(id=booking_id, company_id=company_id).first()
                if not inv:
                    continue
                inv.paid_amount = max(0, (inv.paid_amount or 0) - booking_amount)
                inv.balance = (inv.grand_total or 0) - (inv.paid_amount or 0)
                if inv.balance <= 0:
                    inv.status = "Paid"
                elif inv.paid_amount > 0:
                    inv.status = "Partial"
                else:
                    inv.status = "Pending"
                if client_obj is None and inv.client_id:
                    client_obj = cdb.query(Client).filter_by(id=inv.client_id, company_id=company_id).first()
            if client_obj and hasattr(client_obj, "pending"):
                client_obj.pending = (client_obj.pending or 0) + amount

            # A receipt that touched several CustomerInvoices in one
            # submission (see receipt_save) carries applied_ci_ids_json —
            # every one of those needs re-syncing, not just applied_ci_id
            # (which only ever holds a single id, for the old/simple case).
            ci_ids_json = getattr(txn, "applied_ci_ids_json", None)
            if ci_ids_json:
                try:
                    ci_ids = json.loads(ci_ids_json)
                except (ValueError, TypeError):
                    ci_ids = []
                if ci_ids:
                    cis_to_resync = (cdb.query(CustomerInvoice)
                                      .filter(CustomerInvoice.id.in_(ci_ids),
                                              CustomerInvoice.company_id == company_id)
                                      .all())
            elif txn.applied_ci_id:
                single_ci = cdb.query(CustomerInvoice).filter_by(
                    id=txn.applied_ci_id, company_id=company_id
                ).first()
                if single_ci:
                    cis_to_resync = [single_ci]
        else:
            inv, ci = _find_receivable_for_reversal(cdb, company_id, txn)
            if inv:
                inv.paid_amount = max(0, (inv.paid_amount or 0) - amount)
                inv.balance = (inv.grand_total or 0) - (inv.paid_amount or 0)
                if inv.balance <= 0:
                    inv.status = "Paid"
                elif inv.paid_amount > 0:
                    inv.status = "Partial"
                else:
                    inv.status = "Pending"

                client = cdb.query(Client).filter_by(id=inv.client_id, company_id=company_id).first() if inv.client_id else None
                if client and hasattr(client, "pending"):
                    client.pending = (client.pending or 0) + amount
            if ci:
                cis_to_resync = [ci]

        # ── 3. Re-sync every customer invoice this receipt touched ──
        for ci in cis_to_resync:
            _sync_customer_invoice_payment(cdb, company_id, ci)

        # ── 4. If this was a non-cash receipt, debit the bank account back ──
        if txn_type == "bank" and getattr(txn, "bank_account", None):
            txn.bank_account.balance -= amount

        # ── 5. Delete the transaction ──
        _reverse_settlement_journal(cdb, company_id, txn, "receipt", "Receipt edited/deleted")
        cdb.delete(txn)
        cdb.commit()

        flash(f"✅ Receipt of {company_currency_symbol()} {amount:,.2f} from {client_name} has been deleted and reversed.", "success")

    except Exception as e:
        cdb.rollback()
        print(f"[ADMIN] Error deleting receipt: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Error deleting receipt: {str(e)}", "error")

    return redirect(url_for("receipt_new"))


# ═════════════════════════════════════════════════════════════════════════
# EDIT / UPDATE — payment & receipt
#
# Design constraint: the entity (supplier/client) and the set of bills this
# transaction was originally applied to are NOT re-pickable from the edit
# dialog. Re-running the bill picker against a payment that already moved
# money is how ledgers silently drift — the outstanding-balance numbers the
# picker would show have already been changed BY this very transaction.
# Editing therefore reverses this transaction's old effect on those exact
# same bills, then re-applies the (possibly changed) amount to those same
# bills in the same order — the same distribution algorithm payment_save /
# receipt_save already use for a brand-new submission. Date, amount,
# payment mode, bank account and narration are all freely editable; the
# party and the underlying bill selection are not — delete and re-record
# if either of those needs to change.
# ═════════════════════════════════════════════════════════════════════════

@app.route("/payment/edit-data")
@login_required
@require_permission("receipts_payments", "view")
def payment_edit_data():
    cdb = get_cdb()
    company_id = get_current_company()
    txn_id = request.args.get("id", type=int)
    txn_type = request.args.get("type", "cash")

    if txn_type == "bank":
        txn = cdb.query(BankTransaction).filter_by(id=txn_id, company_id=company_id, type='debit').first()
    else:
        txn = cdb.query(CashTransaction).filter_by(id=txn_id, company_id=company_id, type='expense', category='Payment').first()

    if not txn:
        return jsonify({"error": "Payment not found"}), 404

    return jsonify({
        "id": txn.id,
        "type": txn_type,
        "party": txn.party_name,
        "date": txn.date.isoformat() if txn.date else "",
        "amount": txn.amount,
        "mode": "Cash" if txn_type == "cash" else (txn.transaction_mode or "Bank Transfer"),
        "bank_account_id": txn.bank_account_id if txn_type == "bank" else None,
        "narration": txn.notes or "",
        "reference": txn.reference or "",
    })


@app.route("/payment/update", methods=["POST"])
@login_required
@require_permission("receipts_payments", "create")
def payment_update():
    cdb = get_cdb()
    company_id = get_current_company()

    txn_id     = request.form.get("edit_id", type=int)
    txn_type   = request.form.get("edit_type", "cash")
    new_amount = request.form.get("amount", type=float, default=0)
    narration  = request.form.get("narration", "")
    pay_mode   = request.form.get("pay_mode", "Cash")
    bank_account_id = request.form.get("bank_account_id", type=int)
    txn_date_str = request.form.get("txn_date")
    txn_date   = date.fromisoformat(txn_date_str) if txn_date_str else today_ist()

    if not txn_id or new_amount <= 0:
        flash("Please enter a valid amount.", "error")
        return redirect(url_for("payment_new"))

    if txn_type == "bank":
        txn = cdb.query(BankTransaction).filter_by(id=txn_id, company_id=company_id, type='debit').first()
    else:
        txn = cdb.query(CashTransaction).filter_by(id=txn_id, company_id=company_id, type='expense', category='Payment').first()

    if not txn:
        flash("Payment not found.", "error")
        return redirect(url_for("payment_new"))

    old_amount    = txn.amount
    supplier_name = txn.party_name

    old_breakdown = {}
    if getattr(txn, "applied_breakdown_json", None):
        try:
            old_breakdown = json.loads(txn.applied_breakdown_json) or {}
        except (ValueError, TypeError):
            old_breakdown = {}

    # Resolve the supplier this belongs to — via a breakdown invoice first
    # (authoritative), falling back to a name match for advance-only rows.
    supplier_entity = None
    if old_breakdown:
        first_inv = cdb.query(PurchaseInvoice).filter_by(
            id=int(next(iter(old_breakdown))), company_id=company_id
        ).first()
        if first_inv:
            supplier_entity = first_inv.supplier
    if not supplier_entity:
        supplier_entity = cdb.query(Supplier).filter_by(company_id=company_id, name=supplier_name).first()
    if not supplier_entity:
        flash("Could not resolve the original supplier for this payment — please delete and re-record it instead.", "error")
        return redirect(url_for("payment_new"))
    supplier_name = supplier_entity.name

    bank_account = None
    if pay_mode.lower() != "cash":
        if not bank_account_id:
            flash("Please select a bank account for non-cash payments.", "error")
            return redirect(url_for("payment_new"))
        bank_account = cdb.query(BankAccount).filter_by(
            id=bank_account_id, company_id=company_id, status='Active'
        ).first()
        if not bank_account:
            flash("Selected bank account not found or inactive.", "error")
            return redirect(url_for("payment_new"))

    try:
        # ── 1. Fully reverse this transaction's old effect ──
        for pinv_id_str, pinv_amount in old_breakdown.items():
            inv = cdb.query(PurchaseInvoice).filter_by(id=int(pinv_id_str), company_id=company_id).first()
            if not inv:
                continue
            inv.paid_amount = max(0, (inv.paid_amount or 0) - pinv_amount)
            inv.balance = (inv.grand_total or 0) - (inv.paid_amount or 0)
            inv.status = "Paid" if inv.balance <= 0 else ("Partial" if inv.paid_amount > 0 else "Pending")
            if inv.supplier:
                inv.supplier.payable = (inv.supplier.payable or 0) + pinv_amount

        if txn_type == "bank" and getattr(txn, "bank_account", None):
            txn.bank_account.balance += old_amount

        _reverse_settlement_journal(cdb, company_id, txn, "payment", "Payment edited/deleted")
        cdb.delete(txn)
        cdb.flush()

        # ── 2. Re-apply the (possibly changed) amount to the SAME bills,
        #      same order, same distribution logic as a fresh payment ──
        remaining  = new_amount
        settled    = 0
        breakdown  = {}
        ref_labels = []
        for pinv_id_str in old_breakdown.keys():
            if remaining <= 0:
                break
            inv = cdb.query(PurchaseInvoice).filter_by(id=int(pinv_id_str), company_id=company_id).first()
            if not inv:
                continue
            inv_balance = inv.balance or (inv.grand_total or 0)
            if inv_balance <= 0:
                continue
            apply_amount = min(remaining, inv_balance)
            remaining -= apply_amount
            settled   += apply_amount
            inv.balance = inv_balance - apply_amount
            inv.paid_amount = (inv.paid_amount or 0) + apply_amount
            inv.status = "Paid" if inv.balance <= 0 else ("Partial" if inv.paid_amount > 0 else "Pending")
            if inv.supplier:
                inv.supplier.payable = max(0, (inv.supplier.payable or 0) - apply_amount)
            breakdown[pinv_id_str] = breakdown.get(pinv_id_str, 0.0) + apply_amount
            ref = inv.invoice_number or inv.invoice_id
            if ref not in ref_labels:
                ref_labels.append(ref)

        if settled > 0:
            ref_display = ", ".join(ref_labels[:3]) + (f" +{len(ref_labels)-3} more" if len(ref_labels) > 3 else "")
            desc = f"Payment made against {ref_display}"
            if narration:
                desc += f" - {narration}"
            single_invoice_id = int(next(iter(breakdown))) if len(breakdown) == 1 else None
            common_kwargs = dict(
                company_id=company_id, date=txn_date, description=desc, amount=settled,
                reference=ref_display, party_name=supplier_name,
                created_by=get_current_user().get('email'),
                applied_ref_type="purchase_invoice", applied_ref_id=single_invoice_id,
                applied_breakdown_json=json.dumps(breakdown),
            )
            if pay_mode.lower() == "cash":
                cdb.add(CashTransaction(type="expense", category="Payment",
                         notes=f"Payment of {company_currency_symbol()} {settled:,.2f} to supplier via Cash", **common_kwargs))
            else:
                cdb.add(BankTransaction(bank_account_id=bank_account.id, type="debit",
                         transaction_mode=pay_mode.title(), notes=narration, **common_kwargs))

        if remaining > 0:
            advance_ref  = narration.strip() or None
            advance_desc = "Advance payment to supplier (not applied to a specific invoice)"
            if narration:
                advance_desc += f" - {narration}"
            if pay_mode.lower() == "cash":
                cdb.add(CashTransaction(
                    company_id=company_id, type="expense", date=txn_date, category="Payment",
                    description=advance_desc, amount=remaining, reference=advance_ref,
                    notes="Unapplied portion of payment via Cash", party_name=supplier_name,
                    created_by=get_current_user().get('email'),
                ))
            else:
                cdb.add(BankTransaction(
                    bank_account_id=bank_account.id, company_id=company_id, type="debit",
                    date=txn_date, description=advance_desc, amount=remaining, reference=advance_ref,
                    transaction_mode=pay_mode.title(), notes=narration, party_name=supplier_name,
                    created_by=get_current_user().get('email'),
                ))

        if pay_mode.lower() != "cash" and new_amount > 0:
            bank_account.balance -= new_amount

        replacement_txns = [x for x in cdb.new if isinstance(x, (CashTransaction, BankTransaction))]
        cdb.flush()
        for replacement_txn in replacement_txns:
            _auto_post_settlement(cdb, company_id, replacement_txn, "payment")
        cdb.commit()
        flash(f"✅ Payment updated to {company_currency_symbol()} {new_amount:,.2f} via {pay_mode}.", "success")

    except Exception as e:
        cdb.rollback()
        print(f"[EDIT] Error updating payment: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Error updating payment: {str(e)}", "error")

    return redirect(url_for("payment_new"))


@app.route("/receipt/edit-data")
@login_required
@require_permission("receipts_payments", "view")
def receipt_edit_data():
    cdb = get_cdb()
    company_id = get_current_company()
    txn_id = request.args.get("id", type=int)
    txn_type = request.args.get("type", "cash")

    if txn_type == "bank":
        txn = cdb.query(BankTransaction).filter_by(id=txn_id, company_id=company_id, type='credit').first()
    else:
        txn = cdb.query(CashTransaction).filter_by(id=txn_id, company_id=company_id, type='income', category='Receipt').first()

    if not txn:
        return jsonify({"error": "Receipt not found"}), 404

    return jsonify({
        "id": txn.id,
        "type": txn_type,
        "party": txn.party_name,
        "date": txn.date.isoformat() if txn.date else "",
        "amount": txn.amount,
        "mode": "Cash" if txn_type == "cash" else (txn.transaction_mode or "Bank Transfer"),
        "bank_account_id": txn.bank_account_id if txn_type == "bank" else None,
        "narration": txn.notes or "",
        "reference": txn.reference or "",
    })


@app.route("/receipt/update", methods=["POST"])
@login_required
@require_permission("receipts_payments", "create")
def receipt_update():
    cdb = get_cdb()
    company_id = get_current_company()

    txn_id     = request.form.get("edit_id", type=int)
    txn_type   = request.form.get("edit_type", "cash")
    new_amount = request.form.get("amount", type=float, default=0)
    narration  = request.form.get("narration", "")
    pay_mode   = request.form.get("pay_mode", "Cash")
    bank_account_id = request.form.get("bank_account_id", type=int)
    txn_date_str = request.form.get("txn_date")
    txn_date   = date.fromisoformat(txn_date_str) if txn_date_str else today_ist()

    if not txn_id or new_amount <= 0:
        flash("Please enter a valid amount.", "error")
        return redirect(url_for("receipt_new"))

    if txn_type == "bank":
        txn = cdb.query(BankTransaction).filter_by(id=txn_id, company_id=company_id, type='credit').first()
    else:
        txn = cdb.query(CashTransaction).filter_by(id=txn_id, company_id=company_id, type='income', category='Receipt').first()

    if not txn:
        flash("Receipt not found.", "error")
        return redirect(url_for("receipt_new"))

    old_amount  = txn.amount
    client_name = txn.party_name

    old_breakdown = {}
    if getattr(txn, "applied_breakdown_json", None):
        try:
            old_breakdown = json.loads(txn.applied_breakdown_json) or {}
        except (ValueError, TypeError):
            old_breakdown = {}

    old_ci_ids = []
    if getattr(txn, "applied_ci_ids_json", None):
        try:
            old_ci_ids = json.loads(txn.applied_ci_ids_json) or []
        except (ValueError, TypeError):
            old_ci_ids = []
    elif txn.applied_ci_id:
        old_ci_ids = [txn.applied_ci_id]

    # Resolve the client this belongs to — via a breakdown booking first,
    # falling back to a name match for advance-only rows.
    client_entity = None
    if old_breakdown:
        first_inv = cdb.query(Invoice).filter_by(id=int(next(iter(old_breakdown))), company_id=company_id).first()
        if first_inv and first_inv.client_id:
            client_entity = cdb.query(Client).filter_by(id=first_inv.client_id, company_id=company_id).first()
    if not client_entity:
        client_entity = cdb.query(Client).filter_by(company_id=company_id, name=client_name).first()
    if not client_entity:
        flash("Could not resolve the original client for this receipt — please delete and re-record it instead.", "error")
        return redirect(url_for("receipt_new"))
    client_name = client_entity.name

    bank_account = None
    if pay_mode.lower() != "cash":
        if not bank_account_id:
            flash("Please select a bank account for non-cash payments.", "error")
            return redirect(url_for("receipt_new"))
        bank_account = cdb.query(BankAccount).filter_by(
            id=bank_account_id, company_id=company_id, status='Active'
        ).first()
        if not bank_account:
            flash("Selected bank account not found or inactive.", "error")
            return redirect(url_for("receipt_new"))

    try:
        # ── 1. Fully reverse this transaction's old effect ──
        for booking_id_str, booking_amount in old_breakdown.items():
            inv = cdb.query(Invoice).filter_by(id=int(booking_id_str), company_id=company_id).first()
            if not inv:
                continue
            inv.paid_amount = max(0, (inv.paid_amount or 0) - booking_amount)
            inv.balance = (inv.grand_total or 0) - (inv.paid_amount or 0)
            inv.status = "Paid" if inv.balance <= 0 else ("Partial" if inv.paid_amount > 0 else "Pending")
        if old_breakdown and client_entity and hasattr(client_entity, "pending"):
            client_entity.pending = (client_entity.pending or 0) + old_amount

        if txn_type == "bank" and getattr(txn, "bank_account", None):
            txn.bank_account.balance -= old_amount

        _reverse_settlement_journal(cdb, company_id, txn, "receipt", "Receipt edited/deleted")
        cdb.delete(txn)
        cdb.flush()

        # ── 2. Re-apply the (possibly changed) amount to the SAME bookings,
        #      same order, same distribution logic as a fresh receipt ──
        remaining  = new_amount
        settled    = 0
        breakdown  = {}
        ref_labels = []
        for booking_id_str in old_breakdown.keys():
            if remaining <= 0:
                break
            inv = cdb.query(Invoice).filter_by(id=int(booking_id_str), company_id=company_id).first()
            if not inv:
                continue
            inv_balance = getattr(inv, "balance", None)
            if inv_balance is None:
                inv_balance = inv.grand_total or 0
            if inv_balance <= 0:
                continue
            apply_amount = min(remaining, inv_balance)
            remaining -= apply_amount
            settled   += apply_amount
            inv.balance = inv_balance - apply_amount
            inv.paid_amount = (inv.paid_amount or 0) + apply_amount
            inv.status = "Paid" if inv.balance <= 0 else ("Partial" if inv.paid_amount > 0 else "Pending")
            breakdown[booking_id_str] = breakdown.get(booking_id_str, 0.0) + apply_amount
            ref = inv.invoice_id
            if ref not in ref_labels:
                ref_labels.append(ref)

        if settled > 0:
            ref_display = ", ".join(ref_labels[:3]) + (f" +{len(ref_labels)-3} more" if len(ref_labels) > 3 else "")
            desc = f"Payment received against {ref_display} - {narration}".strip(" -")
            single_raw_invoice_id = int(next(iter(breakdown))) if len(breakdown) == 1 else None
            common_kwargs = dict(
                company_id=company_id, date=txn_date, description=desc, amount=settled,
                reference=ref_display, party_name=client_name,
                created_by=get_current_user().get('email'),
                applied_ref_type="invoice", applied_ref_id=single_raw_invoice_id,
                applied_ci_id=(old_ci_ids[0] if len(old_ci_ids) == 1 else None),
                applied_ci_ids_json=json.dumps(old_ci_ids) if old_ci_ids else None,
                applied_breakdown_json=json.dumps(breakdown),
            )
            if pay_mode.lower() == "cash":
                cdb.add(CashTransaction(type="income", category="Receipt",
                         notes="Payment from client via Cash", **common_kwargs))
            else:
                cdb.add(BankTransaction(bank_account_id=bank_account.id, type="credit",
                         transaction_mode=pay_mode.title(), notes=narration, **common_kwargs))
                bank_account.balance += settled

        if remaining > 0:
            advance_ref  = narration.strip() or None
            advance_desc = f"Advance receipt from client (not applied to a specific invoice) - {narration}".strip(" -")
            if pay_mode.lower() == "cash":
                cdb.add(CashTransaction(
                    company_id=company_id, type="income", date=txn_date, category="Receipt",
                    description=advance_desc, amount=remaining, reference=advance_ref,
                    notes="Unapplied portion of receipt via Cash", party_name=client_name,
                    created_by=get_current_user().get('email'),
                ))
            else:
                cdb.add(BankTransaction(
                    bank_account_id=bank_account.id, company_id=company_id, type="credit",
                    date=txn_date, description=advance_desc, amount=remaining, reference=advance_ref,
                    transaction_mode=pay_mode.title(), notes=narration, party_name=client_name,
                    created_by=get_current_user().get('email'),
                ))
                bank_account.balance += remaining

        if client_entity and hasattr(client_entity, "pending") and client_entity.pending:
            client_entity.pending = max(0, (client_entity.pending or 0) - settled)

        # ── 3. Re-sync every customer invoice the OLD breakdown touched —
        #      same CI set, since we reapplied to the same bookings ──
        for ci_id in old_ci_ids:
            ci = cdb.query(CustomerInvoice).filter_by(id=ci_id, company_id=company_id).first()
            if ci:
                _sync_customer_invoice_payment(cdb, company_id, ci)

        cdb.commit()
        flash(f"✅ Receipt updated to {company_currency_symbol()} {new_amount:,.2f} via {pay_mode}.", "success")

    except Exception as e:
        cdb.rollback()
        print(f"[EDIT] Error updating receipt: {e}")
        import traceback
        traceback.print_exc()
        flash(f"Error updating receipt: {str(e)}", "error")

    return redirect(url_for("receipt_new"))
# ═════════════════════════════════════════════════════════════════════════



# ═══════════════════════════════════════════════════════════════════════════════
# Finance Step 2 — Chart of Accounts
# ═══════════════════════════════════════════════════════════════════════════════
_COA_TYPES = ("Asset", "Liability", "Equity", "Income", "Expense")
_COA_NORMAL = {
    "Asset": "Debit",
    "Expense": "Debit",
    "Liability": "Credit",
    "Equity": "Credit",
    "Income": "Credit",
}

# Conservative SME defaults. These are account masters only; no journal entries
# are generated in Step 2.

# ============================================================================
# FINANCE STEPS 12-15
# ============================================================================

def _ensure_finance_step12_15_tables(cdb):
    """Create only the new finance tables; safe for existing company DBs."""
    engine = cdb.get_bind()
    for model in (BankReconciliation, BankReconciliationItem, FixedAsset):
        model.__table__.create(bind=engine, checkfirst=True)


@app.route("/finance/tax-report")
@login_required
@require_permission("finance", "view")
def finance_tax_report():
    """Step 12: Unified GST / VAT Dashboard & Tax Report.
    Combines live sales & purchase invoice tax registers with central-journal tax accounts.
    """
    cdb = get_cdb()
    company_id = get_current_company()
    _ensure_chart_of_accounts(cdb, company_id)

    company = Company.query.filter_by(company_id=company_id).first()
    from tax_service import tax_profile
    profile = tax_profile(company)

    today = today_ist()
    is_calendar_year = (profile.get('country') != 'India')
    if is_calendar_year:
        fy_year = today.year
        fy_start = date(fy_year, 1, 1)
    else:
        fy_year = today.year if today.month >= 4 else today.year - 1
        fy_start = date(fy_year, 4, 1)

    preset = request.args.get("preset", "")
    from_date_str = request.args.get("from_date", "")
    to_date_str = request.args.get("to_date", "")

    if preset == "month":
        from_date = today.replace(day=1)
        to_date = today
    elif preset == "last_month":
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        from_date = last_month_end.replace(day=1)
        to_date = last_month_end
    elif preset == "quarter":
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        from_date = date(today.year, q_start_month, 1)
        to_date = today
    elif preset == "all":
        from_date = date(2020, 1, 1)
        to_date = today
    elif from_date_str:
        try:
            from_date = date.fromisoformat(from_date_str)
        except ValueError:
            from_date = fy_start
        if to_date_str:
            try:
                to_date = date.fromisoformat(to_date_str)
            except ValueError:
                to_date = today
        else:
            to_date = today
    else:
        # Default to the current financial year so sales and tax data are visible immediately
        from_date = fy_start
        if to_date_str:
            try:
                to_date = date.fromisoformat(to_date_str)
            except ValueError:
                to_date = today
        else:
            to_date = today
        preset = "fy"

    # 1. Sales & Output Tax from Invoices
    ci_sales = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.invoice_date >= from_date,
        CustomerInvoice.invoice_date <= to_date,
        CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft'])
    ).all()

    legacy_sales = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.date >= from_date,
        Invoice.date <= to_date,
        Invoice.status.notin_(['Cancelled', 'Void', 'Draft'])
    ).all()

    # 2. Purchases & Input Tax (ITC)
    purchases = cdb.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.date >= from_date,
        PurchaseInvoice.date <= to_date,
        PurchaseInvoice.status.notin_(['Cancelled', 'Void', 'Draft'])
    ).all()

    sales_taxable = sum(float(i.subtotal or 0) for i in ci_sales) + sum(float(i.total or 0) for i in legacy_sales)
    output_tax = sum(float(i.tax_amount or 0) for i in ci_sales) + sum(float(i.tax_amount or 0) for i in legacy_sales)
    output_cgst = sum(float(i.cgst_total or 0) for i in ci_sales)
    output_sgst = sum(float(i.sgst_total or 0) for i in ci_sales)
    output_igst = sum(float(i.igst_total or 0) for i in ci_sales)

    # Item-level IGST aggregation fallback
    item_sales_igst = sum(float(it.igst_amount or 0) for i in ci_sales for it in getattr(i, 'items', []))
    if output_igst == 0 and item_sales_igst > 0:
        output_igst = item_sales_igst

    legacy_tax = sum(float(i.tax_amount or 0) for i in legacy_sales)
    if legacy_tax > 0 and output_cgst == 0 and output_sgst == 0 and output_igst == 0:
        if not profile.get('is_vat'):
            output_cgst += legacy_tax / 2
            output_sgst += legacy_tax / 2

    if output_tax > 0 and output_cgst == 0 and output_sgst == 0 and output_igst == 0 and not profile.get('is_vat'):
        output_cgst = output_tax / 2
        output_sgst = output_tax / 2

    purchase_taxable = sum(float(p.subtotal or 0) for p in purchases)
    input_tax = sum(float(p.tax_amount or 0) for p in purchases)
    input_cgst = sum(float(p.cgst_total or 0) for p in purchases)
    input_sgst = sum(float(p.sgst_total or 0) for p in purchases)
    input_igst = sum(float(p.igst_total or 0) for p in purchases)

    item_pur_igst = sum(float(it.igst_amount or 0) for p in purchases for it in getattr(p, 'items', []))
    if input_igst == 0 and item_pur_igst > 0:
        input_igst = item_pur_igst

    if input_tax > 0 and input_cgst == 0 and input_sgst == 0 and input_igst == 0 and not profile.get('is_vat'):
        input_cgst = input_tax / 2
        input_sgst = input_tax / 2

    net_tax = output_tax - input_tax
    net_cgst = output_cgst - input_cgst
    net_sgst = output_sgst - input_sgst
    net_igst = output_igst - input_igst

    # 3. GCC VAT Specific Box Calculations
    vat_standard_sales = 0.0
    vat_output_standard = 0.0
    vat_zero_rated_sales = 0.0
    vat_exempt_sales = 0.0

    for inv in ci_sales:
        inv_items = getattr(inv, 'items', [])
        if inv_items:
            for it in inv_items:
                r = float(it.gst_percent or 0.0)
                amt = float(it.taxable_amount or (float(it.quantity or 1) * float(it.rate or 0)))
                tax = float(it.cgst_amount or 0) + float(it.sgst_amount or 0) + float(it.igst_amount or 0)
                if tax == 0 and amt > 0 and r > 0:
                    tax = amt * (r / 100.0)
                if r > 0:
                    vat_standard_sales += amt
                    vat_output_standard += tax
                elif getattr(it, 'is_exempt', False):
                    vat_exempt_sales += amt
                else:
                    vat_zero_rated_sales += amt
        else:
            tax = float(inv.tax_amount or 0)
            sub = float(inv.subtotal or 0)
            if tax > 0:
                vat_standard_sales += sub
                vat_output_standard += tax
            else:
                vat_zero_rated_sales += sub

    for inv in legacy_sales:
        tax = float(inv.tax_amount or 0)
        tot = float(inv.total or 0)
        if tax > 0:
            vat_standard_sales += tot
            vat_output_standard += tax
        else:
            vat_zero_rated_sales += tot

    vat_standard_purchases = 0.0
    vat_input_standard = 0.0
    vat_rcm_purchases = 0.0
    vat_rcm_tax = 0.0

    for p in purchases:
        p_tax_type = (getattr(p, 'tax_type', '') or 'Domestic').strip()
        p_tax = float(p.tax_amount or 0)
        p_sub = float(p.subtotal or 0)
        if p_tax_type in ('RCM', 'Import'):
            vat_rcm_purchases += p_sub
            vat_rcm_tax += p_tax
        elif p_tax > 0:
            vat_standard_purchases += p_sub
            vat_input_standard += p_tax
        else:
            vat_standard_purchases += p_sub

    vat_total_output = vat_output_standard + vat_rcm_tax
    vat_total_recoverable_input = vat_input_standard + vat_rcm_tax
    vat_net_due = vat_total_output - vat_total_recoverable_input

    if profile.get('is_vat'):
        output_tax = vat_total_output
        input_tax = vat_total_recoverable_input
        net_tax = vat_net_due
        sales_taxable = vat_standard_sales + vat_zero_rated_sales + vat_exempt_sales
        purchase_taxable = vat_standard_purchases + vat_rcm_purchases

    # 4. Monthly Tax breakdown
    months_dict = {}
    for inv in ci_sales:
        if inv.invoice_date:
            mkey = inv.invoice_date.strftime('%Y-%m')
            mlabel = inv.invoice_date.strftime('%b %Y')
            if mkey not in months_dict:
                months_dict[mkey] = {'label': mlabel, 'sales_taxable': 0.0, 'output_tax': 0.0, 'purchase_taxable': 0.0, 'input_tax': 0.0}
            months_dict[mkey]['sales_taxable'] += float(inv.subtotal or 0)
            months_dict[mkey]['output_tax'] += float(inv.tax_amount or 0)

    for inv in legacy_sales:
        if inv.date:
            mkey = inv.date.strftime('%Y-%m')
            mlabel = inv.date.strftime('%b %Y')
            if mkey not in months_dict:
                months_dict[mkey] = {'label': mlabel, 'sales_taxable': 0.0, 'output_tax': 0.0, 'purchase_taxable': 0.0, 'input_tax': 0.0}
            months_dict[mkey]['sales_taxable'] += float(inv.total or 0)
            months_dict[mkey]['output_tax'] += float(inv.tax_amount or 0)

    for p in purchases:
        if p.date:
            mkey = p.date.strftime('%Y-%m')
            mlabel = p.date.strftime('%b %Y')
            if mkey not in months_dict:
                months_dict[mkey] = {'label': mlabel, 'sales_taxable': 0.0, 'output_tax': 0.0, 'purchase_taxable': 0.0, 'input_tax': 0.0}
            months_dict[mkey]['purchase_taxable'] += float(p.subtotal or 0)
            months_dict[mkey]['input_tax'] += float(p.tax_amount or 0)

    monthly_summary = []
    for mkey in sorted(months_dict.keys(), reverse=True):
        m = months_dict[mkey]
        monthly_summary.append({
            'month': m['label'],
            'sales_taxable': m['sales_taxable'],
            'output_tax': m['output_tax'],
            'purchase_taxable': m['purchase_taxable'],
            'input_tax': m['input_tax'],
            'net_tax': m['output_tax'] - m['input_tax']
        })

    # 5. Rate-wise breakdown
    rates_dict = {}
    for inv in ci_sales:
        for item in getattr(inv, 'items', []):
            r = float(item.gst_percent or 18.0 if not profile.get('is_vat') else profile.get('default_rate', 5))
            if r not in rates_dict:
                rates_dict[r] = {'rate': r, 'sales_taxable': 0.0, 'output_tax': 0.0, 'purchase_taxable': 0.0, 'input_tax': 0.0}
            amt = float(item.taxable_amount or (float(item.quantity or 1) * float(item.rate or 0)))
            tax = float(item.cgst_amount or 0) + float(item.sgst_amount or 0) + float(item.igst_amount or 0)
            if tax == 0 and amt > 0 and r > 0:
                tax = amt * (r / 100.0)
            rates_dict[r]['sales_taxable'] += amt
            rates_dict[r]['output_tax'] += tax

    for p in purchases:
        for item in getattr(p, 'items', []):
            r = float(item.gst_percent or 0.0)
            if r not in rates_dict:
                rates_dict[r] = {'rate': r, 'sales_taxable': 0.0, 'output_tax': 0.0, 'purchase_taxable': 0.0, 'input_tax': 0.0}
            amt = float(item.taxable_amount or getattr(item, 'taxable_value', 0) or (float(item.quantity or 1) * float(getattr(item, 'purchase_rate', 0) or getattr(item, 'rate', 0) or 0)))
            tax = float(item.cgst_amount or 0) + float(item.sgst_amount or 0) + float(item.igst_amount or 0)
            if tax == 0 and amt > 0 and r > 0:
                tax = amt * (r / 100.0)
            rates_dict[r]['purchase_taxable'] += amt
            rates_dict[r]['input_tax'] += tax

    rate_summary = []
    for r in sorted(rates_dict.keys()):
        rd = rates_dict[r]
        rate_summary.append({
            'rate': r,
            'sales_taxable': rd['sales_taxable'],
            'output_tax': rd['output_tax'],
            'purchase_taxable': rd['purchase_taxable'],
            'input_tax': rd['input_tax'],
            'net_tax': rd['output_tax'] - rd['input_tax']
        })

    # 6. HSN / SAC / Commodity Summary
    hsn_dict = {}
    for inv in ci_sales:
        for item in getattr(inv, 'items', []):
            hsn = (item.hsn or getattr(item, 'item_code', None) or 'General')[:8]
            desc = item.item_name or getattr(item, 'item_description', '') or ''
            if hsn not in hsn_dict:
                hsn_dict[hsn] = {'hsn': hsn, 'description': desc, 'quantity': 0, 'value': 0.0, 'rate': float(item.gst_percent or 18.0 if not profile.get('is_vat') else profile.get('default_rate', 5)), 'cgst': 0.0, 'sgst': 0.0, 'igst': 0.0, 'total': 0.0}
            qty = float(item.quantity or 0)
            amount = float(item.taxable_amount or (qty * float(item.rate or 0)))
            item_cgst = float(item.cgst_amount or 0)
            item_sgst = float(item.sgst_amount or 0)
            item_igst = float(item.igst_amount or 0)
            gst = item_cgst + item_sgst + item_igst
            if gst == 0 and amount > 0:
                r_pct = float(item.gst_percent or 18.0 if not profile.get('is_vat') else profile.get('default_rate', 5))
                gst = amount * (r_pct / 100.0)
                if not profile.get('is_vat'):
                    item_cgst = gst / 2
                    item_sgst = gst / 2
                else:
                    item_cgst = gst
            hsn_dict[hsn]['quantity'] += qty
            hsn_dict[hsn]['value'] += amount
            hsn_dict[hsn]['cgst'] += item_cgst
            hsn_dict[hsn]['sgst'] += item_sgst
            hsn_dict[hsn]['igst'] += item_igst
            hsn_dict[hsn]['total'] += gst

    hsn_summary = list(hsn_dict.values())

    # 7. Central Journal Tax Control Accounts (GL Verification)
    tax_codes = ("1500","1501","1502","1503","2200","2201","2202","2203")
    gl_rows = cdb.query(
        ChartOfAccount.code, ChartOfAccount.name,
        func.coalesce(func.sum(JournalEntryLine.debit), 0),
        func.coalesce(func.sum(JournalEntryLine.credit), 0),
    ).join(JournalEntryLine, JournalEntryLine.account_id == ChartOfAccount.id
    ).join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id
    ).filter(
        ChartOfAccount.company_id == company_id,
        ChartOfAccount.code.in_(tax_codes),
        JournalEntry.company_id == company_id,
        JournalEntry.status.in_(("Posted","Reversed")),
        JournalEntry.entry_date >= from_date,
        JournalEntry.entry_date <= to_date,
    ).group_by(ChartOfAccount.id).order_by(ChartOfAccount.code).all()

    gl_report = []
    gl_input_tax = Decimal("0.00")
    gl_output_tax = Decimal("0.00")
    for code, name, debit, credit in gl_rows:
        debit, credit = _money(debit), _money(credit)
        if str(code).startswith("15"):
            amount = debit - credit
            gl_input_tax += amount
            side = "Input"
        else:
            amount = credit - debit
            gl_output_tax += amount
            side = "Output"
        gl_report.append(dict(code=code, name=name, side=side, debit=debit, credit=credit, amount=amount))

    gl_net_tax = gl_output_tax - gl_input_tax

    return render_template("finance_tax_report.html",
        active="finance_tax_report",
        company=company,
        profile=profile,
        is_calendar_year=is_calendar_year,
        from_date=from_date,
        to_date=to_date,
        preset=preset,
        sales_count=len(ci_sales) + len(legacy_sales),
        purchases_count=len(purchases),
        sales_taxable=sales_taxable,
        purchase_taxable=purchase_taxable,
        output_tax=output_tax,
        output_cgst=output_cgst,
        output_sgst=output_sgst,
        output_igst=output_igst,
        input_tax=input_tax,
        input_cgst=input_cgst,
        input_sgst=input_sgst,
        input_igst=input_igst,
        net_tax=net_tax,
        net_cgst=net_cgst,
        net_sgst=net_sgst,
        net_igst=net_igst,
        # GCC VAT specifics
        vat_standard_sales=vat_standard_sales,
        vat_output_standard=vat_output_standard,
        vat_zero_rated_sales=vat_zero_rated_sales,
        vat_exempt_sales=vat_exempt_sales,
        vat_standard_purchases=vat_standard_purchases,
        vat_input_standard=vat_input_standard,
        vat_rcm_purchases=vat_rcm_purchases,
        vat_rcm_tax=vat_rcm_tax,
        vat_net_due=vat_net_due,
        # Summaries
        rate_summary=rate_summary,
        monthly_summary=monthly_summary,
        hsn_summary=hsn_summary,
        gl_rows=gl_report,
        gl_input_tax=float(gl_input_tax),
        gl_output_tax=float(gl_output_tax),
        gl_net_tax=float(gl_net_tax),
        rows=gl_report,  # for backward compatibility
    )


@app.route("/finance/bank-reconciliation", methods=["GET", "POST"])
@login_required
@require_permission("bank", "view")
def bank_reconciliation():
    """Step 13: reconcile ERP bank transactions against a bank statement balance."""
    cdb = get_cdb()
    company_id = get_current_company()
    _ensure_finance_step12_15_tables(cdb)
    accounts = cdb.query(BankAccount).filter_by(company_id=company_id, status="Active").order_by(BankAccount.bank_name).all()
    selected_id = request.values.get("bank_account_id", type=int)
    selected = cdb.query(BankAccount).filter_by(id=selected_id, company_id=company_id).first() if selected_id else None
    statement_date = date.fromisoformat(request.values["statement_date"]) if request.values.get("statement_date") else today_ist()

    if request.method == "POST":
        if not selected:
            flash("Select a bank account.", "error")
            return redirect(url_for("bank_reconciliation"))
        statement_balance = _money(request.form.get("statement_balance"))
        txns = cdb.query(BankTransaction).filter(
            BankTransaction.company_id == company_id,
            BankTransaction.bank_account_id == selected.id,
            BankTransaction.date <= statement_date,
        ).order_by(BankTransaction.date, BankTransaction.id).all()
        cleared_ids = {int(x) for x in request.form.getlist("cleared_transaction_ids") if str(x).isdigit()}
        book_balance = _money(selected.opening_balance)
        for txn in txns:
            amt = _money(txn.amount)
            book_balance += amt if str(txn.type).lower() in ("credit","income","deposit","receipt") else -amt

        rec = BankReconciliation(
            company_id=company_id, bank_account_id=selected.id,
            statement_date=statement_date, statement_balance=statement_balance,
            book_balance=book_balance, difference=statement_balance-book_balance,
            status="Reconciled" if statement_balance == book_balance else "Open",
            notes=(request.form.get("notes") or "").strip() or None,
            created_by=((session.get("user") or {}).get("email") if isinstance(session.get("user"), dict) else None),
            completed_at=datetime.utcnow() if statement_balance == book_balance else None,
        )
        cdb.add(rec); cdb.flush()
        for txn in txns:
            if txn.id in cleared_ids:
                cdb.add(BankReconciliationItem(
                    reconciliation_id=rec.id, bank_transaction_id=txn.id,
                    is_cleared=True, cleared_date=statement_date))
        cdb.commit()
        flash("Bank reconciliation saved.", "success")
        return redirect(url_for("bank_reconciliation", bank_account_id=selected.id))

    transactions = []
    if selected:
        transactions = cdb.query(BankTransaction).filter(
            BankTransaction.company_id == company_id,
            BankTransaction.bank_account_id == selected.id,
            BankTransaction.date <= statement_date,
        ).order_by(BankTransaction.date.desc(), BankTransaction.id.desc()).all()
    history = cdb.query(BankReconciliation).filter_by(company_id=company_id).order_by(
        BankReconciliation.statement_date.desc(), BankReconciliation.id.desc()).limit(20).all()
    return render_template("bank_reconciliation.html", active="bank_reconciliation",
        accounts=accounts, selected=selected, statement_date=statement_date,
        transactions=transactions, history=history)


@app.route("/finance/fixed-assets", methods=["GET", "POST"])
@login_required
@require_permission("finance", "view")
def fixed_assets():
    """Step 14: fixed-asset register with straight-line book value."""
    cdb = get_cdb()
    company_id = get_current_company()
    _ensure_finance_step12_15_tables(cdb)
    if request.method == "POST":
        code = (request.form.get("asset_code") or "").strip()
        name = (request.form.get("name") or "").strip()
        if not code or not name:
            flash("Asset code and name are required.", "error")
            return redirect(url_for("fixed_assets"))
        asset = FixedAsset(
            company_id=company_id, asset_code=code, name=name,
            category=(request.form.get("category") or "").strip() or None,
            purchase_date=date.fromisoformat(request.form["purchase_date"]),
            purchase_cost=_money(request.form.get("purchase_cost")),
            salvage_value=_money(request.form.get("salvage_value")),
            useful_life_months=max(1, int(request.form.get("useful_life_months") or 60)),
            notes=(request.form.get("notes") or "").strip() or None,
        )
        cdb.add(asset); cdb.commit()
        flash("Fixed asset added.", "success")
        return redirect(url_for("fixed_assets"))

    assets = cdb.query(FixedAsset).filter_by(company_id=company_id).order_by(FixedAsset.purchase_date.desc()).all()
    today = today_ist()
    view_rows = []
    for a in assets:
        months = max(0, (today.year-a.purchase_date.year)*12 + today.month-a.purchase_date.month)
        months = min(months, a.useful_life_months)
        depreciable = max(Decimal("0.00"), _money(a.purchase_cost)-_money(a.salvage_value))
        monthly = depreciable / Decimal(a.useful_life_months)
        calc_dep = min(depreciable, monthly * months)
        book_value = _money(a.purchase_cost) - calc_dep
        view_rows.append(dict(asset=a, monthly=monthly, calculated_depreciation=calc_dep, book_value=book_value))
    return render_template("fixed_assets.html", active="fixed_assets", rows=view_rows)


@app.route("/finance/fixed-assets/<int:asset_id>/post-depreciation", methods=["POST"])
@login_required
@require_permission("finance", "view")
def post_asset_depreciation(asset_id):
    cdb = get_cdb()
    company_id = get_current_company()
    _ensure_finance_step12_15_tables(cdb)
    _ensure_chart_of_accounts(cdb, company_id)
    asset = cdb.query(FixedAsset).filter_by(id=asset_id, company_id=company_id).first_or_404()
    amount = _money(request.form.get("amount"))
    if amount <= 0:
        flash("Depreciation amount must be greater than zero.", "error")
        return redirect(url_for("fixed_assets"))
    remaining = max(Decimal("0.00"), _money(asset.purchase_cost)-_money(asset.salvage_value)-_money(asset.accumulated_depreciation))
    amount = min(amount, remaining)
    if amount <= 0:
        flash("This asset is already fully depreciated to its salvage value.", "error")
        return redirect(url_for("fixed_assets"))

    entry = _post_auto_journal(cdb, company_id,
        source_type="asset_depreciation", source_id=f"{asset.id}:{today_ist().isoformat()}",
        entry_date=today_ist(), reference=asset.asset_code,
        narration=f"Depreciation - {asset.name}",
        lines=[
            ("6700", amount, 0, f"Depreciation - {asset.name}", None, None),
            ("1610", 0, amount, f"Accumulated depreciation - {asset.name}", None, None),
        ])
    if entry:
        asset.accumulated_depreciation = _money(asset.accumulated_depreciation) + amount
        cdb.commit()
        flash("Depreciation posted to the journal.", "success")
    else:
        flash("Depreciation for this asset/date is already posted.", "warning")
    return redirect(url_for("fixed_assets"))


@app.route("/finance/dashboard")
@login_required
@require_permission("finance", "view")
def finance_dashboard_view():
    return redirect(url_for("finance_workspace"))


_DEFAULT_COA = (
    ("1000", "Assets", "Asset", "Assets"),
    ("1100", "Cash in Hand", "Asset", "Cash & Cash Equivalents"),
    ("1200", "Bank Accounts", "Asset", "Cash & Cash Equivalents"),
    ("1300", "Accounts Receivable", "Asset", "Receivables"),
    ("1400", "Inventory", "Asset", "Inventory"),
    ("1500", "Input Tax Credit", "Asset", "Tax"),
    ("1600", "Fixed Assets", "Asset", "Fixed Assets"),
    ("1700", "Other Current Assets", "Asset", "Other Assets"),
    ("1800", "Supplier Advances", "Asset", "Advances"),
    ("1710", "Employee Loans & Advances", "Asset", "Other Assets"),
    ("2410", "Salary Payable", "Liability", "Payroll Liabilities"),
    ("2420", "PF Payable", "Liability", "Payroll Liabilities"),
    ("2430", "ESI Payable", "Liability", "Payroll Liabilities"),
    ("2440", "Professional Tax Payable", "Liability", "Payroll Liabilities"),
    ("2450", "TDS Payable", "Liability", "Payroll Liabilities"),
    ("2470", "Other Payroll Deductions Payable", "Liability", "Payroll Liabilities"),
    ("2000", "Liabilities", "Liability", "Liabilities"),
    ("2100", "Accounts Payable", "Liability", "Payables"),
    ("2200", "Output Tax Payable", "Liability", "Tax"),
    ("2300", "Loans Payable", "Liability", "Loans"),
    ("2400", "Other Current Liabilities", "Liability", "Other Liabilities"),
    ("2500", "Customer Advances", "Liability", "Advances"),
    ("3000", "Equity", "Equity", "Equity"),
    ("3100", "Owner's Capital", "Equity", "Capital"),
    ("3200", "Retained Earnings", "Equity", "Retained Earnings"),
    ("4000", "Income", "Income", "Income"),
    ("4100", "Sales Revenue", "Income", "Operating Revenue"),
    ("4200", "Service / Labour Revenue", "Income", "Operating Revenue"),
    ("4300", "Other Income", "Income", "Other Income"),
    ("5000", "Cost of Goods Sold", "Expense", "Cost of Sales"),
    ("5100", "Purchase / Material Cost", "Expense", "Cost of Sales"),
    ("6000", "Operating Expenses", "Expense", "Operating Expenses"),
    ("6100", "Salaries & Wages", "Expense", "Employee Costs"),
    ("6150", "Employer Statutory Contributions", "Expense", "Employee Costs"),
    ("6200", "Rent", "Expense", "Operating Expenses"),
    ("6300", "Utilities", "Expense", "Operating Expenses"),
    ("6400", "Transport & Freight", "Expense", "Operating Expenses"),
    ("6500", "Repairs & Maintenance", "Expense", "Operating Expenses"),
    ("6600", "Bank Charges", "Expense", "Finance Costs"),
    ("6700", "Depreciation", "Expense", "Depreciation"),
    ("6800", "Other Expenses", "Expense", "Other Expenses"),
)


_GCC_COA = (
    ("1000", "Assets", "Asset", "Assets"),
    ("1100", "Cash in Hand", "Asset", "Cash & Cash Equivalents"),
    ("1200", "Bank Accounts", "Asset", "Cash & Cash Equivalents"),
    ("1300", "Accounts Receivable", "Asset", "Receivables"),
    ("1400", "Inventory", "Asset", "Inventory"),
    ("1500", "Recoverable Input VAT", "Asset", "Tax"),
    ("1600", "Fixed Assets", "Asset", "Fixed Assets"),
    ("1700", "Other Current Assets", "Asset", "Other Assets"),
    ("1800", "Supplier Advances", "Asset", "Advances"),
    ("1710", "Employee Loans & Advances", "Asset", "Other Assets"),
    ("2410", "WPS Salary Payable", "Liability", "Payroll Liabilities"),
    ("2420", "End of Service Benefits / Gratuity Payable", "Liability", "Payroll Liabilities"),
    ("2430", "Leave Salary Provision", "Liability", "Payroll Liabilities"),
    ("2440", "Air Ticket Provision", "Liability", "Payroll Liabilities"),
    ("2450", "Employee Deductions Payable", "Liability", "Payroll Liabilities"),
    ("2470", "Other Payroll Liabilities", "Liability", "Payroll Liabilities"),
    ("2000", "Liabilities", "Liability", "Liabilities"),
    ("2100", "Accounts Payable", "Liability", "Payables"),
    ("2200", "Output VAT Payable", "Liability", "Tax"),
    ("2210", "VAT Clearing / FTA Settlement", "Liability", "Tax"),
    ("2300", "Loans Payable", "Liability", "Loans"),
    ("2400", "Other Current Liabilities", "Liability", "Other Liabilities"),
    ("2500", "Customer Advances", "Liability", "Advances"),
    ("3000", "Equity", "Equity", "Equity"),
    ("3100", "Owner's Capital", "Equity", "Capital"),
    ("3200", "Retained Earnings", "Equity", "Retained Earnings"),
    ("4000", "Income", "Income", "Income"),
    ("4100", "Sales Revenue", "Income", "Operating Revenue"),
    ("4200", "Service / Labour Revenue", "Income", "Operating Revenue"),
    ("4300", "Other Income", "Income", "Other Income"),
    ("5000", "Cost of Goods Sold", "Expense", "Cost of Sales"),
    ("5100", "Purchase / Material Cost", "Expense", "Cost of Sales"),
    ("6000", "Operating Expenses", "Expense", "Operating Expenses"),
    ("6100", "Salaries & Wages", "Expense", "Employee Costs"),
    ("6150", "Gratuity & End of Service Expense", "Expense", "Employee Costs"),
    ("6200", "Rent", "Expense", "Operating Expenses"),
    ("6300", "Utilities", "Expense", "Operating Expenses"),
    ("6400", "Transport & Freight", "Expense", "Operating Expenses"),
    ("6500", "Repairs & Maintenance", "Expense", "Operating Expenses"),
    ("6600", "Bank Charges", "Expense", "Finance Costs"),
    ("6700", "Depreciation", "Expense", "Depreciation"),
    ("6800", "Other Expenses", "Expense", "Other Expenses"),
)


def _ensure_chart_of_accounts(cdb, company_id):
    """Create the Step-2 account-master table and idempotently seed defaults.

    Existing operational balances are intentionally NOT copied into opening
    balances here. That mapping belongs to the journal/opening-entry migration
    step, preventing double counting.
    """
    bind = cdb.get_bind()
    ChartOfAccount.__table__.create(bind=bind, checkfirst=True)

    company = Company.query.filter_by(company_id=company_id).first()
    from tax_service import tax_profile
    profile = tax_profile(company) if company else {}
    is_gcc = profile.get('is_vat') or profile.get('country') in (
        'United Arab Emirates', 'Saudi Arabia', 'Kuwait', 'Bahrain', 'Qatar', 'Oman'
    )
    target_coa = _GCC_COA if is_gcc else _DEFAULT_COA

    existing_rows = {
        row.code: row for row in cdb.query(ChartOfAccount)
        .filter_by(company_id=company_id).all()
    }
    created = False
    for code, name, account_type, account_group in target_coa:
        if code in existing_rows:
            if is_gcc and existing_rows[code].is_system:
                if existing_rows[code].name != name:
                    existing_rows[code].name = name
                    created = True
            continue
        cdb.add(ChartOfAccount(
            company_id=company_id,
            code=code,
            name=name,
            account_type=account_type,
            account_group=account_group,
            normal_balance=_COA_NORMAL[account_type],
            opening_balance=0,
            is_system=True,
            is_active=True,
        ))
        created = True
    if created:
        replacement_txns = [x for x in cdb.new if isinstance(x, (CashTransaction, BankTransaction))]
        cdb.flush()
        for replacement_txn in replacement_txns:
            _auto_post_settlement(cdb, company_id, replacement_txn, "receipt")
        cdb.commit()


@app.route("/finance/chart-of-accounts", methods=["GET", "POST"])
@login_required
@require_permission("finance", "view")
def chart_of_accounts():
    cdb = get_cdb()
    company_id = get_current_company()
    if not company_id:
        return redirect(url_for("select_company"))

    _ensure_chart_of_accounts(cdb, company_id)

    if request.method == "POST":
        if not has_permission("finance", "create"):
            abort(403)

        code = (request.form.get("code") or "").strip()
        name = (request.form.get("name") or "").strip()
        account_type = (request.form.get("account_type") or "").strip()
        account_group = (request.form.get("account_group") or "").strip()
        parent_raw = (request.form.get("parent_id") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None

        if not code or not name or account_type not in _COA_TYPES or not account_group:
            flash("Code, account name, type and group are required.", "error")
            return redirect(url_for("chart_of_accounts"))

        duplicate = cdb.query(ChartOfAccount).filter_by(
            company_id=company_id, code=code
        ).first()
        if duplicate:
            flash(f"Account code {code} already exists.", "error")
            return redirect(url_for("chart_of_accounts"))

        parent_id = int(parent_raw) if parent_raw.isdigit() else None
        if parent_id:
            parent = cdb.query(ChartOfAccount).filter_by(
                id=parent_id, company_id=company_id, is_active=True
            ).first()
            if not parent:
                flash("Selected parent account is invalid.", "error")
                return redirect(url_for("chart_of_accounts"))
            if parent.account_type != account_type:
                flash("Parent and child accounts must use the same account type.", "error")
                return redirect(url_for("chart_of_accounts"))

        cdb.add(ChartOfAccount(
            company_id=company_id,
            code=code,
            name=name,
            account_type=account_type,
            account_group=account_group,
            normal_balance=_COA_NORMAL[account_type],
            parent_id=parent_id,
            opening_balance=0,
            is_system=False,
            is_active=True,
            notes=notes,
        ))
        cdb.commit()
        flash(f"Account {code} — {name} created.", "success")
        return redirect(url_for("chart_of_accounts"))

    show_inactive = request.args.get("show_inactive") == "1"
    q = cdb.query(ChartOfAccount).filter_by(company_id=company_id)
    if not show_inactive:
        q = q.filter(ChartOfAccount.is_active.is_(True))
    accounts = q.order_by(ChartOfAccount.code.asc()).all()
    parents = cdb.query(ChartOfAccount).filter_by(
        company_id=company_id, is_active=True
    ).order_by(ChartOfAccount.code.asc()).all()

    company = get_company_by_id(company_id)
    return render_template(
        "chart_of_accounts.html",
        accounts=accounts,
        parents=parents,
        account_types=_COA_TYPES,
        show_inactive=show_inactive,
        company=company,
        active="chart_of_accounts",
    )


@app.route("/finance/chart-of-accounts/<int:account_id>/edit", methods=["POST"])
@login_required
@require_permission("finance", "edit")
def chart_of_accounts_edit(account_id):
    cdb = get_cdb()
    company_id = get_current_company()
    _ensure_chart_of_accounts(cdb, company_id)

    account = cdb.query(ChartOfAccount).filter_by(
        id=account_id, company_id=company_id
    ).first()
    if not account:
        abort(404)

    name = (request.form.get("name") or "").strip()
    account_group = (request.form.get("account_group") or "").strip()
    notes = (request.form.get("notes") or "").strip() or None
    is_active = request.form.get("is_active") == "1"

    if not name or not account_group:
        flash("Account name and group are required.", "error")
        return redirect(url_for("chart_of_accounts"))

    # System account code/type/normal balance are deliberately immutable.
    account.name = name
    account.account_group = account_group
    account.notes = notes
    account.is_active = is_active
    cdb.commit()
    flash(f"Account {account.code} updated.", "success")
    return redirect(url_for("chart_of_accounts"))


# ═══════════════════════════════════════════════════════════════════════════════
# Finance Step 3 — Manual Journal Engine
# ═══════════════════════════════════════════════════════════════════════════════
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

_MONEY_Q = Decimal("0.01")


def _money(value):
    try:
        return Decimal(str(value or "0")).quantize(_MONEY_Q, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid monetary amount.")


def _ensure_journal_tables(cdb):
    """Create journal tables in the active customer DB without touching old data."""
    bind = cdb.get_bind()
    ChartOfAccount.__table__.create(bind=bind, checkfirst=True)
    JournalEntry.__table__.create(bind=bind, checkfirst=True)
    JournalEntryLine.__table__.create(bind=bind, checkfirst=True)


def _next_journal_number(cdb, company_id):
    prefix = f"JV-{today_ist().year}-"
    latest = (
        cdb.query(JournalEntry.entry_no)
        .filter(JournalEntry.company_id == company_id,
                JournalEntry.entry_no.like(prefix + "%"))
        .order_by(JournalEntry.id.desc()).first()
    )
    seq = 1
    if latest and latest[0]:
        try:
            seq = int(latest[0].rsplit("-", 1)[1]) + 1
        except (ValueError, IndexError):
            seq = cdb.query(JournalEntry).filter_by(company_id=company_id).count() + 1
    return f"{prefix}{seq:05d}"


def _validate_journal_lines(cdb, company_id, account_ids, descriptions, debits, credits):
    lines = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    row_count = max(len(account_ids), len(descriptions), len(debits), len(credits))

    for i in range(row_count):
        account_raw = account_ids[i].strip() if i < len(account_ids) else ""
        description = descriptions[i].strip() if i < len(descriptions) else ""
        debit = _money(debits[i] if i < len(debits) else 0)
        credit = _money(credits[i] if i < len(credits) else 0)

        # Completely blank rows are ignored.
        if not account_raw and debit == 0 and credit == 0 and not description:
            continue
        if not account_raw.isdigit():
            raise ValueError(f"Line {i + 1}: select an account.")
        account = cdb.query(ChartOfAccount).filter_by(
            id=int(account_raw), company_id=company_id, is_active=True
        ).first()
        if not account:
            raise ValueError(f"Line {i + 1}: account is invalid or inactive.")
        if debit < 0 or credit < 0:
            raise ValueError(f"Line {i + 1}: amounts cannot be negative.")
        if (debit > 0 and credit > 0) or (debit == 0 and credit == 0):
            raise ValueError(f"Line {i + 1}: enter either a debit or a credit.")
        total_debit += debit
        total_credit += credit
        lines.append((account, description, debit, credit))

    if len(lines) < 2:
        raise ValueError("A journal entry needs at least two lines.")
    if total_debit <= 0:
        raise ValueError("Journal total must be greater than zero.")
    if total_debit != total_credit:
        raise ValueError(
            f"Journal is not balanced. Debit {total_debit:.2f} ≠ Credit {total_credit:.2f}."
        )
    return lines, total_debit, total_credit



def _coa_by_code(cdb, company_id, code):
    _ensure_chart_of_accounts(cdb, company_id)
    account = cdb.query(ChartOfAccount).filter_by(
        company_id=company_id, code=code, is_active=True
    ).first()
    if not account:
        raise ValueError(f"Required Chart of Accounts code {code} is missing or inactive.")
    return account


def _existing_source_journal(cdb, company_id, source_type, source_id):
    return cdb.query(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.source_type == source_type,
        JournalEntry.source_id == str(source_id),
        JournalEntry.status.in_(("Posted", "Draft")),
    ).first()


def _post_auto_journal(cdb, company_id, entry_date, narration, source_type,
                       source_id, reference, rows):
    """Idempotent automatic posting.

    rows = [(account_code, debit, credit, description), ...]
    Money is converted to Decimal, zero rows are removed, and the final entry
    must balance before it can be posted.
    """
    _ensure_journal_tables(cdb)
    existing = _existing_source_journal(cdb, company_id, source_type, source_id)
    if existing:
        return existing

    clean = []
    td = Decimal("0.00")
    tc = Decimal("0.00")
    for code, debit, credit, description in rows:
        d = _money(debit)
        c = _money(credit)
        if d == 0 and c == 0:
            continue
        if d < 0 or c < 0 or (d > 0 and c > 0):
            raise ValueError(f"Invalid automatic journal row for account {code}.")
        account = _coa_by_code(cdb, company_id, code)
        clean.append((account, d, c, description))
        td += d
        tc += c

    if len(clean) < 2 or td <= 0 or td != tc:
        raise ValueError(
            f"Automatic journal for {source_type}:{source_id} is not balanced "
            f"(Debit {td:.2f}, Credit {tc:.2f})."
        )

    actor_obj = get_current_user() or {}
    actor = actor_obj.get("email") or actor_obj.get("full_name") or actor_obj.get("user_id") or "System"
    entry = JournalEntry(
        company_id=company_id,
        entry_no=_next_journal_number(cdb, company_id),
        entry_date=entry_date,
        reference=reference,
        narration=narration,
        source_type=source_type,
        source_id=str(source_id),
        status="Posted",
        created_by=actor,
        posted_by=actor,
        posted_at=datetime.utcnow(),
    )
    cdb.add(entry)
    cdb.flush()
    for account, debit, credit, description in clean:
        cdb.add(JournalEntryLine(
            entry_id=entry.id, account_id=account.id,
            description=description or narration,
            debit=debit, credit=credit,
        ))
    return entry



def _reverse_source_journal(cdb, company_id, source_type, source_id, reason=None):
    """Reverse the currently-active journal for an operational source.

    The original entry is never edited/deleted. A posted equal-and-opposite
    entry is created, then the original is marked Reversed. Calling this more
    than once is safe: once the original is Reversed there is no active source
    journal left to reverse.
    """
    _ensure_journal_tables(cdb)
    original = cdb.query(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.source_type == source_type,
        JournalEntry.source_id == str(source_id),
        JournalEntry.status == "Posted",
    ).order_by(JournalEntry.id.desc()).first()
    if not original:
        return None

    already = cdb.query(JournalEntry).filter(
        JournalEntry.company_id == company_id,
        JournalEntry.reversal_of_id == original.id,
        JournalEntry.status == "Posted",
    ).first()
    if already:
        original.status = "Reversed"
        return already

    actor_obj = get_current_user() or {}
    actor = actor_obj.get("email") or actor_obj.get("full_name") or actor_obj.get("user_id") or "System"
    reversal = JournalEntry(
        company_id=company_id,
        entry_no=_next_journal_number(cdb, company_id),
        entry_date=today_ist(),
        reference=f"REV-{original.entry_no}",
        narration=reason or f"Automatic reversal of {original.entry_no}",
        source_type="reversal",
        source_id=str(original.id),
        status="Posted",
        reversal_of_id=original.id,
        created_by=actor,
        posted_by=actor,
        posted_at=datetime.utcnow(),
    )
    cdb.add(reversal)
    cdb.flush()
    for line in original.lines:
        cdb.add(JournalEntryLine(
            entry_id=reversal.id,
            account_id=line.account_id,
            description=f"Reversal — {line.description or original.narration}",
            debit=_money(line.credit),
            credit=_money(line.debit),
            party_type=line.party_type,
            party_id=line.party_id,
        ))
    original.status = "Reversed"
    original.reversed_at = datetime.utcnow()
    return reversal


def _replace_customer_invoice_journal(cdb, company_id, inv, reason="Sales invoice edited"):
    source_type = "repair_bill" if getattr(inv, "invoice_category", "") == "workshop_repair" else "sales_invoice"
    _reverse_source_journal(cdb, company_id, source_type, inv.id, reason)
    return _auto_post_customer_invoice(cdb, company_id, inv)


def _replace_purchase_invoice_journal(cdb, company_id, inv, reason="Purchase invoice edited"):
    _reverse_source_journal(cdb, company_id, "purchase_invoice", inv.id, reason)
    return _auto_post_purchase_invoice(cdb, company_id, inv)


def _reverse_settlement_journal(cdb, company_id, txn, direction, reason):
    if not txn:
        return None
    source_type = f"{direction}_{'bank' if isinstance(txn, BankTransaction) else 'cash'}"
    return _reverse_source_journal(cdb, company_id, source_type, txn.id, reason)


def _auto_post_customer_invoice(cdb, company_id, inv):
    """Post a product-sale or workshop-repair CustomerInvoice."""
    if not inv or not inv.id:
        return None
    if (inv.status or "").strip().lower() in ("draft", "void", "cancelled", "canceled"):
        return None

    rate = _money(getattr(inv, "exchange_rate", 1) or 1)
    # Prefer stored base-currency values; fall back to document values × rate.
    subtotal = _money(getattr(inv, "base_subtotal", 0) or 0)
    tax = _money(getattr(inv, "base_tax_amount", 0) or 0)
    total = _money(getattr(inv, "base_grand_total", 0) or 0)
    if total == 0:
        subtotal = _money(inv.subtotal) * rate
        tax = _money(inv.tax_amount) * rate
        total = _money(inv.grand_total) * rate

    revenue_code = "4200" if getattr(inv, "invoice_category", "") == "workshop_repair" else "4100"
    label = "Repair Bill" if revenue_code == "4200" else "Sales Invoice"
    return _post_auto_journal(
        cdb, company_id, inv.invoice_date, f"{label} {inv.invoice_number}",
        "repair_bill" if revenue_code == "4200" else "sales_invoice",
        inv.id, inv.invoice_number,
        [
            ("1300", total, 0, f"Receivable — {inv.client_name or inv.invoice_number}"),
            (revenue_code, 0, subtotal, f"{label} revenue"),
            ("2200", 0, tax, "Output tax payable"),
        ],
    )


def _auto_post_purchase_invoice(cdb, company_id, inv):
    if not inv or not inv.id:
        return None
    if (inv.status or "").strip().lower() in ("draft", "void", "cancelled", "canceled"):
        return None

    rate = _money(getattr(inv, "exchange_rate", 1) or 1)
    subtotal = _money(getattr(inv, "base_subtotal", 0) or 0)
    tax = _money(getattr(inv, "base_tax_amount", 0) or 0)
    total = _money(getattr(inv, "base_grand_total", 0) or 0)
    if total == 0:
        subtotal = _money(inv.subtotal) * rate
        tax = _money(inv.tax_amount) * rate
        total = _money(inv.grand_total) * rate

    ref = inv.invoice_number or inv.invoice_id
    return _post_auto_journal(
        cdb, company_id, inv.date, f"Purchase Invoice {ref}",
        "purchase_invoice", inv.id, ref,
        [
            ("5100", subtotal, 0, "Purchase / material cost"),
            ("1500", tax, 0, "Input tax credit"),
            ("2100", 0, total, f"Payable — {inv.supplier_name or ref}"),
        ],
    )


def _auto_post_settlement(cdb, company_id, txn, direction):
    """Post a receipt/payment cash or bank movement.

    direction: 'receipt' or 'payment'. Applied transactions settle AR/AP;
    unapplied amounts go to Customer Advances / Supplier Advances.
    """
    if not txn or not txn.id:
        return None
    is_bank = isinstance(txn, BankTransaction)
    cashbank_code = "1200" if is_bank else "1100"
    amount = _money(txn.amount)
    applied = bool(
        getattr(txn, "applied_ref_type", None)
        or getattr(txn, "applied_ref_id", None)
        or getattr(txn, "applied_breakdown_json", None)
        or getattr(txn, "applied_ci_id", None)
        or getattr(txn, "applied_ci_ids_json", None)
    )
    source_type = f"{direction}_{'bank' if is_bank else 'cash'}"
    if direction == "receipt":
        counterpart = "1300" if applied else "2500"
        rows = [
            (cashbank_code, amount, 0, txn.description),
            (counterpart, 0, amount,
             "Accounts receivable settled" if applied else "Customer advance"),
        ]
    else:
        counterpart = "2100" if applied else "1800"
        rows = [
            (counterpart, amount, 0,
             "Accounts payable settled" if applied else "Supplier advance"),
            (cashbank_code, 0, amount, txn.description),
        ]
    return _post_auto_journal(
        cdb, company_id, txn.date, txn.description, source_type, txn.id,
        txn.reference, rows
    )


def _auto_post_expense(cdb, company_id, exp, txn):
    if not exp or not exp.id or not txn or not txn.id:
        return None
    cashbank_code = "1200" if isinstance(txn, BankTransaction) else "1100"
    amount = _money(exp.amount)
    return _post_auto_journal(
        cdb, company_id, exp.date, f"Expense: {exp.description}",
        "expense", exp.id, exp.reference or f"EXP-{exp.id}",
        [
            ("6800", amount, 0, exp.category or "Expense"),
            (cashbank_code, 0, amount, txn.description),
        ],
    )


@app.route("/finance/journals")
@login_required
@require_permission("finance", "view")
def journal_entries():
    cdb = get_cdb()
    company_id = get_current_company()
    _ensure_chart_of_accounts(cdb, company_id)
    _ensure_journal_tables(cdb)

    status = (request.args.get("status") or "").strip()
    q = cdb.query(JournalEntry).filter_by(company_id=company_id)
    if status in ("Draft", "Posted", "Reversed"):
        q = q.filter(JournalEntry.status == status)
    entries = q.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc()).limit(500).all()

    return render_template(
        "journal_entries.html", entries=entries, status=status,
        active="journal_entries", company=get_company_by_id(company_id)
    )


@app.route("/finance/journals/new", methods=["GET", "POST"])
@login_required
@require_permission("finance", "create")
def journal_entry_new():
    cdb = get_cdb()
    company_id = get_current_company()
    _ensure_chart_of_accounts(cdb, company_id)
    _ensure_journal_tables(cdb)
    accounts = cdb.query(ChartOfAccount).filter_by(
        company_id=company_id, is_active=True
    ).order_by(ChartOfAccount.code).all()

    if request.method == "POST":
        try:
            entry_date = date.fromisoformat(request.form.get("entry_date", ""))
        except (TypeError, ValueError):
            flash("A valid journal date is required.", "error")
            return redirect(url_for("journal_entry_new"))

        narration = (request.form.get("narration") or "").strip()
        reference = (request.form.get("reference") or "").strip() or None
        action = request.form.get("action", "draft")
        if not narration:
            flash("Narration is required.", "error")
            return redirect(url_for("journal_entry_new"))

        try:
            lines, total_debit, total_credit = _validate_journal_lines(
                cdb, company_id,
                request.form.getlist("account_id[]"),
                request.form.getlist("description[]"),
                request.form.getlist("debit[]"),
                request.form.getlist("credit[]"),
            )
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("journal_entry_new"))

        user = session.get("user", {})
        actor = user.get("email") or user.get("full_name") or user.get("user_id")
        entry = JournalEntry(
            company_id=company_id,
            entry_no=_next_journal_number(cdb, company_id),
            entry_date=entry_date,
            reference=reference,
            narration=narration,
            source_type="manual",
            status="Posted" if action == "post" else "Draft",
            created_by=actor,
            posted_by=actor if action == "post" else None,
            posted_at=datetime.utcnow() if action == "post" else None,
        )
        cdb.add(entry)
        cdb.flush()
        for account, description, debit, credit in lines:
            cdb.add(JournalEntryLine(
                entry_id=entry.id, account_id=account.id,
                description=description or narration,
                debit=debit, credit=credit,
            ))
        cdb.commit()
        flash(
            f"{entry.entry_no} {'posted' if entry.status == 'Posted' else 'saved as draft'} "
            f"— Debit {total_debit:.2f} / Credit {total_credit:.2f}.",
            "success"
        )
        return redirect(url_for("journal_entry_view", entry_id=entry.id))

    return render_template(
        "journal_entry_form.html", accounts=accounts, today=today_ist(),
        active="journal_entries", company=get_company_by_id(company_id)
    )


@app.route("/finance/journals/<int:entry_id>")
@login_required
@require_permission("finance", "view")
def journal_entry_view(entry_id):
    cdb = get_cdb()
    company_id = get_current_company()
    _ensure_journal_tables(cdb)
    entry = cdb.query(JournalEntry).filter_by(id=entry_id, company_id=company_id).first()
    if not entry:
        abort(404)
    total_debit = sum((_money(x.debit) for x in entry.lines), Decimal("0.00"))
    total_credit = sum((_money(x.credit) for x in entry.lines), Decimal("0.00"))
    return render_template(
        "journal_entry_view.html", entry=entry,
        total_debit=total_debit, total_credit=total_credit,
        active="journal_entries", company=get_company_by_id(company_id)
    )


@app.route("/finance/journals/<int:entry_id>/post", methods=["POST"])
@login_required
@require_permission("finance", "edit")
def journal_entry_post(entry_id):
    cdb = get_cdb()
    company_id = get_current_company()
    _ensure_journal_tables(cdb)
    entry = cdb.query(JournalEntry).filter_by(id=entry_id, company_id=company_id).first()
    if not entry:
        abort(404)
    if entry.status != "Draft":
        flash("Only draft journals can be posted.", "error")
        return redirect(url_for("journal_entry_view", entry_id=entry.id))

    try:
        _validate_journal_lines(
            cdb, company_id,
            [str(line.account_id) for line in entry.lines],
            [line.description or "" for line in entry.lines],
            [line.debit for line in entry.lines],
            [line.credit for line in entry.lines],
        )
    except ValueError as exc:
        flash(f"Journal cannot be posted: {exc}", "error")
        return redirect(url_for("journal_entry_view", entry_id=entry.id))

    user = session.get("user", {})
    entry.status = "Posted"
    entry.posted_by = user.get("email") or user.get("full_name") or user.get("user_id")
    entry.posted_at = datetime.utcnow()
    cdb.commit()
    flash(f"{entry.entry_no} posted. Posted journals are immutable.", "success")
    return redirect(url_for("journal_entry_view", entry_id=entry.id))


@app.route("/finance/journals/<int:entry_id>/reverse", methods=["POST"])
@login_required
@require_permission("finance", "edit")
def journal_entry_reverse(entry_id):
    cdb = get_cdb()
    company_id = get_current_company()
    _ensure_journal_tables(cdb)
    original = cdb.query(JournalEntry).filter_by(id=entry_id, company_id=company_id).first()
    if not original:
        abort(404)
    if original.status != "Posted":
        flash("Only posted journals can be reversed.", "error")
        return redirect(url_for("journal_entry_view", entry_id=original.id))
    existing = cdb.query(JournalEntry).filter_by(
        company_id=company_id, reversal_of_id=original.id
    ).first()
    if existing:
        flash(f"This journal was already reversed by {existing.entry_no}.", "error")
        return redirect(url_for("journal_entry_view", entry_id=existing.id))

    user = session.get("user", {})
    actor = user.get("email") or user.get("full_name") or user.get("user_id")
    reversal = JournalEntry(
        company_id=company_id,
        entry_no=_next_journal_number(cdb, company_id),
        entry_date=today_ist(),
        reference=f"REV:{original.entry_no}",
        narration=f"Reversal of {original.entry_no}: {original.narration}",
        source_type="reversal",
        source_id=str(original.id),
        status="Posted",
        reversal_of_id=original.id,
        created_by=actor, posted_by=actor,
        posted_at=datetime.utcnow(),
    )
    cdb.add(reversal)
    cdb.flush()
    for line in original.lines:
        cdb.add(JournalEntryLine(
            entry_id=reversal.id, account_id=line.account_id,
            description=f"Reversal: {line.description or original.narration}",
            debit=_money(line.credit), credit=_money(line.debit),
            party_type=line.party_type, party_id=line.party_id,
        ))
    original.status = "Reversed"
    original.reversed_at = datetime.utcnow()
    cdb.commit()
    flash(f"{original.entry_no} reversed with {reversal.entry_no}.", "success")
    return redirect(url_for("journal_entry_view", entry_id=reversal.id))



# Register Standard ERP Routes (Challans, Sales Orders, Purchase Orders)
register_erp_routes(app, login_required, require_permission, get_cdb, get_current_company, resolve_user_names, _auto_post_customer_invoice, _auto_post_purchase_invoice)

from gst_portal import register_gst_portal
register_gst_portal(app, login_required, get_cdb, get_current_company,
                    lambda cid: Company.query.filter_by(company_id=cid).first(), has_permission)

from finance_workspace import register_finance_workspace
from finance_periods import register_finance_periods
register_finance_periods(app, login_required, owner_required, require_permission,
                        get_cdb, get_current_company, get_current_user, today_ist)
from finance_checks import register_finance_checks
register_finance_checks(app, login_required, require_permission, get_cdb,
                        get_current_company, has_permission,
                        _auto_post_customer_invoice, _auto_post_purchase_invoice)
from finance_notes import register_finance_notes, note_statement_events
register_finance_notes(app, login_required, require_permission, get_cdb, get_current_company,
                       has_permission, _post_auto_journal, _reverse_source_journal,
                       lambda db, company: (_ensure_journal_tables(db), _ensure_chart_of_accounts(db, company)))
register_finance_workspace(app, login_required, require_permission, get_cdb,
                           get_current_company, has_permission, today_ist, get_company_by_id)

# Register Phase-1 canonical BI metric engine.
# Existing /api/bi/dashboard stays intact until the Phase-2 dashboard migration.
from bi import register_bi_routes
register_bi_routes(
    app, login_required, require_permission, get_cdb, get_current_company,
    get_current_user, get_company_by_id, has_permission, today_ist,
)

# Register Dedicated CRM, OrderFlow, and Automotive Workshop Suites
from order_erp_routes import register_order_erp_routes
from crm_routes import register_crm_routes
from workshop_routes import register_workshop_routes

register_order_erp_routes(app, login_required, get_cdb, get_current_company, get_current_user, get_company_by_id, has_permission)
register_crm_routes(app, login_required, get_cdb, get_current_company, get_current_user, get_company_by_id)
register_workshop_routes(
    app, login_required, get_cdb, get_current_company, get_current_user,
    get_company_by_id, require_permission,
    auto_post_customer_invoice=_auto_post_customer_invoice,
)


@app.context_processor
def inject_hr_navigation():
    return {
        "use_hr_navigation": bool(
            request.endpoint and (
                request.endpoint == "hr_dashboard" or
                request.endpoint.startswith("hr_")
            )
        )
    }


# Register HR & Payroll Workspace — Phase 1
from hr_workspace import register_hr_workspace
register_hr_workspace(
    app, login_required, require_permission, get_cdb, get_current_company,
    get_current_user, get_company_by_id,
    post_auto_journal=_post_auto_journal,
    ensure_chart_of_accounts=_ensure_chart_of_accounts,
)


from supply_chain_workspace import register_supply_chain_workspace
register_supply_chain_workspace(app, login_required, get_cdb, get_current_company,
                                has_permission, get_company_by_id, today_ist)

# ── Applications Hub (Card-based Workspace Launcher) ──────────────────────────
@app.route("/apps")
@login_required
def apps_hub():
    company_id = get_current_company()
    company = get_company_by_id(company_id)
    user = get_current_user()
    cdb = get_cdb()
    users_count = 0
    try:
        users_count = cdb.query(CompanyUser).filter_by(company_id=company_id, is_active=True).count()
    except Exception:
        pass
    return render_template("apps_hub.html", company=company, user=user, company_users_count=users_count, public_plans=PUBLIC_PLANS, current_plan=get_plan(company.subscription_plan) if company else {})


from module_access import register_module_access
from admin_access import register_admin_access
register_module_access(app, get_current_user, get_current_company, get_customer_session, today_ist)
register_admin_access(app, get_current_user, get_customer_session, today_ist)
from hr_user_access import register_hr_user_access
register_hr_user_access(app, get_current_user, get_current_company, get_customer_session, get_company_by_id)

from trial_subscriptions import register_trial_subscriptions, start_trial_reminders
app.config['PUBLIC_APP_URL'] = os.getenv('PUBLIC_APP_URL', '')
register_trial_subscriptions(app, login_required, get_current_user, today_ist)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        seed_database()  # Only platform data
        start_trial_reminders(app, mail, today_ist)
        
        # Seed customer databases for existing companies
        companies = Company.query.all()
        for company in companies:
            try:
                seed_customer_database(company.company_id)
            except Exception as e:
                print(f"Could not seed customer DB for {company.company_id}: {e}")
    app.run(debug=True, port=5020)
else:
    # When run by Gunicorn / Render, seed after the app is fully loaded
    with app.app_context():
        seed_database()  # Only platform data
        start_trial_reminders(app, mail, today_ist)
        
        # Seed customer databases for existing companies
        companies = Company.query.all()
        for company in companies:
            try:
                seed_customer_database(company.company_id)
            except Exception as e:
                print(f"Could not seed customer DB for {company.company_id}: {e}")

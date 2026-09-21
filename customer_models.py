"""
customer_models.py
──────────────────
CUSTOMER data only — stored in the customer's chosen database
(SQLite local  OR  MySQL cloud).

Uses plain SQLAlchemy (no Flask-SQLAlchemy) because engines are
managed per-company by db_router.py, not by Flask's app context.
"""

from sqlalchemy.orm import DeclarativeBase, relationship as _relationship
from sqlalchemy import (
    Column, Integer, String, Float, Boolean,
    Date, DateTime, Text, ForeignKey,
)
from datetime import datetime, date


class _Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Thin compatibility shim so all the  customer_db.Column / customer_db.Model
# references in the model classes below continue to work unchanged.
# ---------------------------------------------------------------------------
class _CustomerDB:
    Model        = _Base
    metadata     = _Base.metadata
    Column       = staticmethod(Column)
    Integer      = Integer
    String       = String
    Float        = Float
    Boolean      = Boolean
    Date         = Date
    DateTime     = DateTime
    Text         = Text
    ForeignKey   = staticmethod(ForeignKey)
    relationship = staticmethod(_relationship)


customer_db = _CustomerDB()


# ── 4. Company Users ──────────────────────────────────────────────────────────
class CompanyUser(customer_db.Model):
    __tablename__ = "company_users"

    id            = customer_db.Column(customer_db.Integer,    primary_key=True, autoincrement=True)
    user_id       = customer_db.Column(customer_db.String(20),  unique=True, nullable=False)
    company_id    = customer_db.Column(customer_db.String(20),  nullable=False)
    email         = customer_db.Column(customer_db.String(255), nullable=False)
    password_hash = customer_db.Column(customer_db.String(255), nullable=False)
    full_name     = customer_db.Column(customer_db.String(150), nullable=False)
    role          = customer_db.Column(customer_db.String(50),  nullable=False, default="employee")
    department    = customer_db.Column(customer_db.String(100), nullable=True)
    phone         = customer_db.Column(customer_db.String(20),  nullable=True)
    is_active     = customer_db.Column(customer_db.Boolean,     nullable=False, default=True)
    created_at    = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    field_permissions = customer_db.Column(customer_db.Text, nullable=True)
    editable_fields = customer_db.Column(customer_db.Text, nullable=True)
    # Per-user permission overrides on top of the role default, e.g.
    # {"purchase": {"view": true, "create": true, "edit": false}}
    # A key present here always wins over the role's default for that
    # module/action. Absent keys fall back to the role default.
    permission_overrides = customer_db.Column(customer_db.Text, nullable=True)

    def __repr__(self):
        return f"<CompanyUser {self.user_id}>"


# ── 4b. Company Role Permissions ──────────────────────────────────────────────
# One row per (company_id, role). Lets an owner customize what "employee"
# (sales) and "accountant" can view/create/edit in *this* company, on top of
# the built-in defaults in permissions.py. No delete action is stored here —
# deletion is not part of this system.
class CompanyRolePermission(customer_db.Model):
    __tablename__ = "company_role_permissions"

    id               = customer_db.Column(customer_db.Integer,    primary_key=True, autoincrement=True)
    company_id       = customer_db.Column(customer_db.String(20), nullable=False)
    role             = customer_db.Column(customer_db.String(50), nullable=False)  # 'employee' | 'accountant'
    permissions_json = customer_db.Column(customer_db.Text, nullable=True)  # Module permissions
    field_permissions_json = customer_db.Column(customer_db.Text, nullable=True)
    updated_at       = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<CompanyRolePermission {self.company_id}:{self.role}>"


# ── 5. Clients (buyers, suppliers, debtors, creditors) ───────────────────────
class Client(customer_db.Model):
    __tablename__ = "clients"

    id              = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    client_id       = customer_db.Column(customer_db.String(20),  unique=True, nullable=True)
    company_id      = customer_db.Column(customer_db.String(20),  nullable=False)
    name            = customer_db.Column(customer_db.String(200), nullable=False)
    contact_person  = customer_db.Column(customer_db.String(150), nullable=True)
    client_type     = customer_db.Column(customer_db.String(30),  nullable=False, default="Business")
    phone           = customer_db.Column(customer_db.String(20),  nullable=True)
    alternate_phone = customer_db.Column(customer_db.String(20),  nullable=True)
    email           = customer_db.Column(customer_db.String(255), nullable=True)
    website         = customer_db.Column(customer_db.String(255), nullable=True)
    address_line1   = customer_db.Column(customer_db.String(300), nullable=True)
    address_line2   = customer_db.Column(customer_db.String(300), nullable=True)
    city            = customer_db.Column(customer_db.String(100), nullable=True)
    state           = customer_db.Column(customer_db.String(100), nullable=True)
    pincode         = customer_db.Column(customer_db.String(10),  nullable=True)
    country         = customer_db.Column(customer_db.String(100), nullable=False, default="India")
    currency        = customer_db.Column(customer_db.String(10),  nullable=True)
    trn_number      = customer_db.Column(customer_db.String(50),  nullable=True)
    tax_regime      = customer_db.Column(customer_db.String(50),  nullable=True)
    gst_number      = customer_db.Column(customer_db.String(20),  nullable=True)
    pan_number      = customer_db.Column(customer_db.String(15),  nullable=True)
    aadhar_number   = customer_db.Column(customer_db.String(12),  nullable=True)
    # Scanned ID uploads (front/back), stored as filenames under static/client_docs/.
    # These back the "credit customer → docs fetched from client record" flow —
    # cash/walk-in bookings upload their own copies straight onto the invoice instead
    # (see Invoice.terms shipper_aadhar_front_file etc.), since there's no client row.
    aadhar_front_file = customer_db.Column(customer_db.String(255), nullable=True)
    aadhar_back_file  = customer_db.Column(customer_db.String(255), nullable=True)
    pan_front_file    = customer_db.Column(customer_db.String(255), nullable=True)
    pan_back_file     = customer_db.Column(customer_db.String(255), nullable=True)
    gst_type        = customer_db.Column(customer_db.String(30),  nullable=False, default="Regular")
    credit_limit    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    credit_days     = customer_db.Column(customer_db.Integer,     nullable=False, default=30)
    pending         = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    last_payment    = customer_db.Column(customer_db.Date,        nullable=True)
    opening_balance = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    status          = customer_db.Column(customer_db.String(50),  nullable=False, default="Active")
    notes           = customer_db.Column(customer_db.Text,        nullable=True)
    created_at      = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    statement_cutoff = customer_db.Column(customer_db.DateTime,   nullable=True)

    def __repr__(self):
        return f"<Client {self.id} – {self.name}>"

    def to_dict(self):
        return {
            'id': self.id,
            'client_id': self.client_id or f"CLI-{self.id}",
            'company_id': self.company_id,
            'name': self.name,
            'contact_person': self.contact_person or '',
            'client_type': self.client_type or 'Business',
            'phone': self.phone or '',
            'alternate_phone': self.alternate_phone or '',
            'email': self.email or '',
            'address': f"{self.address_line1 or ''} {self.address_line2 or ''}".strip(),
            'city': self.city or '',
            'state': self.state or '',
            'pincode': self.pincode or '',
            'gst_number': self.gst_number or '',
            'pan_number': self.pan_number or '',
            'credit_limit': self.credit_limit or 0.0,
            'credit_days': self.credit_days or 30,
            'pending': self.pending or 0.0,
            'status': self.status or 'Active',
            'notes': self.notes or '',
            'created_at': self.created_at.strftime('%Y-%m-%d') if self.created_at else None
        }

class Supplier(customer_db.Model):
    __tablename__ = "suppliers"
 
    id              = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    supplier_id     = customer_db.Column(customer_db.String(20),  unique=True, nullable=True)
    company_id      = customer_db.Column(customer_db.String(20),  nullable=False)
    name            = customer_db.Column(customer_db.String(200), nullable=False)
    supplier_type   = customer_db.Column(customer_db.String(30),  nullable=False, default="Business")  # Business / Individual
    contact_person  = customer_db.Column(customer_db.String(150), nullable=True)
    phone           = customer_db.Column(customer_db.String(20),  nullable=True)
    alternate_phone = customer_db.Column(customer_db.String(20),  nullable=True)
    email           = customer_db.Column(customer_db.String(255), nullable=True)
    website         = customer_db.Column(customer_db.String(255), nullable=True)
    address_line1   = customer_db.Column(customer_db.String(300), nullable=True)
    address_line2   = customer_db.Column(customer_db.String(300), nullable=True)
    city            = customer_db.Column(customer_db.String(100), nullable=True)
    state           = customer_db.Column(customer_db.String(100), nullable=True)
    pincode         = customer_db.Column(customer_db.String(10),  nullable=True)
    country         = customer_db.Column(customer_db.String(100), nullable=False, default="India")
    currency        = customer_db.Column(customer_db.String(10),  nullable=True)
    trn_number      = customer_db.Column(customer_db.String(50),  nullable=True)
    tax_regime      = customer_db.Column(customer_db.String(50),  nullable=True)
    gst_number      = customer_db.Column(customer_db.String(20),  nullable=True)
    pan_number      = customer_db.Column(customer_db.String(15),  nullable=True)
    aadhar_number   = customer_db.Column(customer_db.String(12),  nullable=True)
    gst_type        = customer_db.Column(customer_db.String(30),  nullable=False, default="Regular")   # Regular / Composition / Unregistered
    credit_limit    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)   # max credit supplier gives us
    credit_days     = customer_db.Column(customer_db.Integer,     nullable=False, default=30)
    payable         = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)   # amount WE owe supplier
    opening_balance = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    last_purchase   = customer_db.Column(customer_db.Date,        nullable=True)
    status          = customer_db.Column(customer_db.String(50),  nullable=False, default="Active")    # Active / Inactive / Blacklisted
    notes           = customer_db.Column(customer_db.Text,        nullable=True)
    created_at      = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    statement_cutoff = customer_db.Column(customer_db.DateTime,   nullable=True)

    brands = customer_db.relationship("SupplierBrand", back_populates="supplier", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Supplier {self.id} – {self.name}>"


# ── 5b. Supplier Brands (courier tie-ups under one supplier, e.g. IMD → Bluedart, DPD, DHL) ──
class SupplierBrand(customer_db.Model):
    __tablename__ = "supplier_brands"

    id          = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    supplier_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey("suppliers.id"), nullable=False)
    brand_name  = customer_db.Column(customer_db.String(100), nullable=False)
    created_at  = customer_db.Column(customer_db.Date, nullable=False, default=date.today)

    supplier = customer_db.relationship("Supplier", back_populates="brands")

    def __repr__(self):
        return f"<SupplierBrand {self.brand_name} (supplier {self.supplier_id})>"


# ── 6. Orders ─────────────────────────────────────────────────────────────────
class Order(customer_db.Model):
    __tablename__ = "orders"

    id          = customer_db.Column(customer_db.Integer,    primary_key=True, autoincrement=True)
    order_id    = customer_db.Column(customer_db.String(30), unique=True, nullable=False)
    company_id  = customer_db.Column(customer_db.String(20), nullable=False)
    client_id   = customer_db.Column(customer_db.Integer,   nullable=True)
    employee_id = customer_db.Column(customer_db.String(20), nullable=True)
    date        = customer_db.Column(customer_db.Date,       nullable=False, default=date.today)
    amount      = customer_db.Column(customer_db.Float,      nullable=False, default=0.0)
    received    = customer_db.Column(customer_db.Float,      nullable=False, default=0.0)
    status      = customer_db.Column(customer_db.String(50), nullable=False, default="Pending")

    def __repr__(self):
        return f"<Order {self.order_id}>"


# ── 7. Stock Items ────────────────────────────────────────────────────────────
class StockItem(customer_db.Model):
    __tablename__ = "stock_items"

    id                 = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    company_id         = customer_db.Column(customer_db.String(20),  nullable=False)
    code               = customer_db.Column(customer_db.String(50),  nullable=False)
    name               = customer_db.Column(customer_db.String(200), nullable=False)
    category           = customer_db.Column(customer_db.String(100), nullable=True)
    quantity           = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    unit               = customer_db.Column(customer_db.String(20),  nullable=True, default="pcs")
    unit_price         = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    reorder_level      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    hsn                = customer_db.Column(customer_db.String(20),  nullable=True)
    last_updated       = customer_db.Column(customer_db.Date,        nullable=True)
    purchase_rate      = customer_db.Column(customer_db.Float,       nullable=True)
    last_purchase_rate = customer_db.Column(customer_db.Float,       nullable=True)
    avg_purchase_rate  = customer_db.Column(customer_db.Float,       nullable=True)
    gst_percent        = customer_db.Column(customer_db.Float,       nullable=True, default=18.0)
    selling_price      = customer_db.Column(customer_db.Float,       nullable=True)
    margin_percent     = customer_db.Column(customer_db.Float,       nullable=True)
    client_id          = customer_db.Column(customer_db.Integer,     nullable=True, default=None)
    item_type          = customer_db.Column(customer_db.String(50),  nullable=True, default=None)
    # Cash/walk-in bookings never get a client_id (see _get_or_create_cash_client
    # in app.py) — this is the only thing that keeps two different walk-in
    # customers' stock of the same item name from merging into one row.
    # Always NULL for credit bookings, where client_id already does the job.
    shipper_name       = customer_db.Column(customer_db.String(200), nullable=True, default=None)
    brand              = customer_db.Column(customer_db.String(100), nullable=True, default=None)

    def __repr__(self):
        return f"<StockItem {self.code} – {self.name}>"

    def to_dict(self):
        return {
            'id': self.id,
            'code': self.code,
            'name': self.name,
            'brand': self.brand or '',
            'category': self.category or '',
            'quantity': self.quantity or 0.0,
            'unit': self.unit or 'pcs',
            'unit_price': self.unit_price or 0.0,
            'selling_price': self.selling_price or self.unit_price or 0.0,
            'gst_percent': self.gst_percent or 18.0,
            'hsn': self.hsn or ''
        }


# ── 8. Invoices ───────────────────────────────────────────────────────────────
class Invoice(customer_db.Model):
    __tablename__ = "invoices"

    id             = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    invoice_id     = customer_db.Column(customer_db.String(30),  unique=True, nullable=False)
    company_id     = customer_db.Column(customer_db.String(20),  nullable=False)
    client_id      = customer_db.Column(customer_db.Integer,     nullable=True)
    date           = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    due_date       = customer_db.Column(customer_db.Date,        nullable=True)
    status         = customer_db.Column(customer_db.String(50),  nullable=False, default="Pending")
    subtotal       = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    tax_amount     = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    grand_total    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    contact_person = customer_db.Column(customer_db.String(150), nullable=True)
    email          = customer_db.Column(customer_db.String(255), nullable=True)
    phone          = customer_db.Column(customer_db.String(20),  nullable=True)
    terms          = customer_db.Column(customer_db.Text,        nullable=True)
    paid_amount    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    balance        = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    # Cumulative settlement discount applied via Record Payment (see
    # invoice_list_record_payment in app.py) — NOT the booking-time discount,
    # which stays in the `terms` JSON blob's "discount" key. This column
    # didn't exist before; app.py was reading/writing it with getattr() as
    # if it were a real column, which meant every value it "stored" here
    # was a plain in-memory Python attribute that vanished the moment the
    # request ended and was never in the invoices table at all. Needs a
    # migration on any existing database — see note below the class.
    discount       = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    created_at     = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)
    resale_charges   = customer_db.Column(customer_db.Float,     nullable=False, default=0.0)
    resale_reason    = customer_db.Column(customer_db.String(200), nullable=True)
    resale_date      = customer_db.Column(customer_db.Date,      nullable=True)
    resale_notes     = customer_db.Column(customer_db.Text,      nullable=True)
    has_resale       = customer_db.Column(customer_db.Boolean,   nullable=False, default=False)
    docket_no      = Column(String(50), nullable=True, index=True)
    submit_token     = customer_db.Column(customer_db.String(64), nullable=True, unique=True, index=True)
    created_by     = customer_db.Column(customer_db.String(100), nullable=True)
    updated_by     = customer_db.Column(customer_db.String(100), nullable=True)

    items = customer_db.relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Invoice {self.invoice_id}>"
    
    @property
    def client_obj(self):
        """Helper to get client object"""
        from sqlalchemy.orm import object_session
        session = object_session(self)
        if session:
            return session.query(Client).filter_by(id=self.client_id).first()
        return None

class DeletedInvoiceLog(_Base):
    __tablename__ = "deleted_invoice_log"
    id            = Column(Integer, primary_key=True)
    company_id    = Column(String(50), nullable=False)
    invoice_id    = Column(String(50))       # the invoice_id string, e.g. "INV-0042"
    awb_no        = Column(String(50))       # the AWB/docket that's now retired
    client_name   = Column(String(255))      # credit client name, if any
    shipper_name  = Column(String(255))      # cash/walk-in name, if any
    grand_total   = Column(Float)
    deleted_by    = Column(String(255))      # email of whoever clicked delete
    deleted_at    = Column(DateTime, default=datetime.utcnow)
    reason        = Column(String(255))      # free text, e.g. "duplicate booking bug"


# ── 21. Customer Invoices (aggregate invoices) ──────────────────────────────
class CustomerInvoice(customer_db.Model):
    """Standard Sales / Tax Invoice"""
    __tablename__ = "customer_invoices"
    
    id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    invoice_number = customer_db.Column(customer_db.String(30), unique=True, nullable=False)
    company_id = customer_db.Column(customer_db.String(20), nullable=False)
    client_id = customer_db.Column(customer_db.Integer, nullable=True)
    client_name = customer_db.Column(customer_db.String(200), nullable=True)
    billing_address = customer_db.Column(customer_db.Text, nullable=True)
    shipping_address = customer_db.Column(customer_db.Text, nullable=True)
    client_gstin = customer_db.Column(customer_db.String(50), nullable=True)
    client_state = customer_db.Column(customer_db.String(100), nullable=True)
    invoice_date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)
    due_date = customer_db.Column(customer_db.Date, nullable=True)
    invoice_type = customer_db.Column(customer_db.String(10), nullable=False, default="credit")  # 'cash' or 'credit'
    status = customer_db.Column(customer_db.String(50), nullable=False, default="Pending")
    payment_terms = customer_db.Column(customer_db.String(100), nullable=True)
    currency = customer_db.Column(customer_db.String(10), nullable=False, default="INR")
    exchange_rate = customer_db.Column(customer_db.Float, nullable=False, default=1.0)
    subtotal = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    tax_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    cgst_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    sgst_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    igst_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    grand_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    base_subtotal = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    base_tax_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    base_grand_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    tax_regime = customer_db.Column(customer_db.String(50), nullable=False, default="GST")
    paid_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    balance = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    terms = customer_db.Column(customer_db.Text, nullable=True)
    notes = customer_db.Column(customer_db.Text, nullable=True)
    created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = customer_db.Column(customer_db.DateTime, nullable=True, onupdate=datetime.utcnow)
    created_by = customer_db.Column(customer_db.String(100), nullable=True)
    updated_by = customer_db.Column(customer_db.String(100), nullable=True)
    
    booking_ids_json = customer_db.Column(customer_db.Text, nullable=True)
    
    items = customer_db.relationship("CustomerInvoiceItem", back_populates="customer_invoice", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<CustomerInvoice {self.invoice_number}>"

    @property
    def client_obj(self):
        from sqlalchemy.orm import object_session
        session = object_session(self)
        if session and self.client_id:
            return session.query(Client).filter_by(id=self.client_id).first()
        return None


class CustomerInvoiceItem(customer_db.Model):
    """Line item within a sales tax invoice"""
    __tablename__ = "customer_invoice_items"
    
    id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    customer_invoice_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey("customer_invoices.id"), nullable=False)
    
    # Standard Product ERP Fields
    stock_item_id = customer_db.Column(customer_db.Integer, nullable=True)
    item_code = customer_db.Column(customer_db.String(50), nullable=True)
    item_name = customer_db.Column(customer_db.String(200), nullable=True)
    item_description = customer_db.Column(customer_db.String(300), nullable=True)
    hsn = customer_db.Column(customer_db.String(20), nullable=True)
    quantity = customer_db.Column(customer_db.Float, nullable=False, default=1.0)
    unit = customer_db.Column(customer_db.String(20), nullable=True, default="pcs")
    rate = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    rate_per_kg = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    weight_kg = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    discount_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    taxable_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    other_charges = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    gst_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    cgst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    sgst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    igst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    total_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    base_rate = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    base_taxable_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    base_total_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)

    # Legacy/Optional booking linkage
    booking_invoice_id = customer_db.Column(customer_db.Integer, nullable=True)
    booking_invoice_ref = customer_db.Column(customer_db.String(30), nullable=True)
    docket_no = customer_db.Column(customer_db.String(50), nullable=True)
    receiver_name = customer_db.Column(customer_db.String(200), nullable=True)
    destination = customer_db.Column(customer_db.String(150), nullable=True)
    carrier = customer_db.Column(customer_db.String(100), nullable=True)
    carrier_ref = customer_db.Column(customer_db.String(100), nullable=True)
    booking_date = customer_db.Column(customer_db.Date, nullable=True)
    
    customer_invoice = customer_db.relationship("CustomerInvoice", back_populates="items")
    
    def __repr__(self):
        return f"<CustomerInvoiceItem {self.item_name or self.item_description or self.docket_no}>"

# ── 19. Price Lists (Shipping Rates) ─────────────────────────────────────────
class PriceList(customer_db.Model):
    __tablename__ = "price_lists"

    id          = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    company_id  = customer_db.Column(customer_db.String(20), nullable=False)
    courier     = customer_db.Column(customer_db.String(50), nullable=False)
    filename    = customer_db.Column(customer_db.String(255), nullable=False)
    file_path   = customer_db.Column(customer_db.String(500), nullable=False)
    rate_data   = customer_db.Column(customer_db.Text, nullable=True)
    is_active   = customer_db.Column(customer_db.Boolean, default=True)
    list_type   = customer_db.Column(customer_db.String(20), nullable=False, default='sales')  
    uploaded_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)
    uploaded_by = customer_db.Column(customer_db.String(100), nullable=True)

    def __repr__(self):
        return f"<PriceList {self.courier} - {self.filename}>"


# ── 20. Rate Lookup Cache ────────────────────────────────────────────────────
class RateLookup(customer_db.Model):
    __tablename__ = "rate_lookups"

    id          = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    company_id  = customer_db.Column(customer_db.String(20), nullable=False)
    courier     = customer_db.Column(customer_db.String(50), nullable=False)
    destination = customer_db.Column(customer_db.String(100), nullable=False)
    weight      = customer_db.Column(customer_db.Float, nullable=False)
    rate        = customer_db.Column(customer_db.Float, nullable=False)
    created_at  = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)
    lookup_count = customer_db.Column(customer_db.Integer, default=1)  # Track usage

    
# ── 8a. Invoice Line Items ────────────────────────────────────────────────────
class InvoiceItem(customer_db.Model):
    __tablename__ = "invoice_items"

    id            = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    invoice_id    = customer_db.Column(customer_db.Integer,     customer_db.ForeignKey("invoices.id"), nullable=False)
    stock_item_id = customer_db.Column(customer_db.Integer,     nullable=True)
    code          = customer_db.Column(customer_db.String(50),  nullable=True)
    description   = customer_db.Column(customer_db.String(300), nullable=False)
    qty           = customer_db.Column(customer_db.Float,       nullable=False, default=1.0)
    rate          = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    discount      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)

    invoice = customer_db.relationship("Invoice", back_populates="items")

    def __repr__(self):
        return f"<InvoiceItem {self.id}>"


# ── 9. Estimates ──────────────────────────────────────────────────────────────
class Estimate(customer_db.Model):
    """Standard Quotation / Estimate"""
    __tablename__ = "estimates"

    id             = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    estimate_id    = customer_db.Column(customer_db.String(30),  unique=True, nullable=False)
    company_id     = customer_db.Column(customer_db.String(20),  nullable=False)
    client_id      = customer_db.Column(customer_db.Integer,     nullable=True)
    client_name    = customer_db.Column(customer_db.String(200), nullable=True)
    client_address = customer_db.Column(customer_db.Text,        nullable=True)
    client_gstin   = customer_db.Column(customer_db.String(50),  nullable=True)
    client_state   = customer_db.Column(customer_db.String(100), nullable=True)
    date           = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    valid_until    = customer_db.Column(customer_db.Date,        nullable=True)
    status         = customer_db.Column(customer_db.String(50),  nullable=False, default="Draft")
    payment_terms  = customer_db.Column(customer_db.String(100), nullable=True)
    delivery_terms = customer_db.Column(customer_db.String(100), nullable=True)
    currency       = customer_db.Column(customer_db.String(10),  nullable=False, default="INR")
    exchange_rate  = customer_db.Column(customer_db.Float,       nullable=False, default=1.0)
    subtotal       = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    tax_amount     = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    cgst_total     = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    sgst_total     = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    igst_total     = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    grand_total    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    base_subtotal  = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    base_tax_amount= customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    base_grand_total= customer_db.Column(customer_db.Float,      nullable=False, default=0.0)
    tax_regime     = customer_db.Column(customer_db.String(50),  nullable=False, default="GST")
    contact_person = customer_db.Column(customer_db.String(150), nullable=True)
    email          = customer_db.Column(customer_db.String(150), nullable=True)
    phone          = customer_db.Column(customer_db.String(30),  nullable=True)
    terms          = customer_db.Column(customer_db.Text,        nullable=True)
    notes          = customer_db.Column(customer_db.Text,        nullable=True)
    created_at     = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)
    created_by     = customer_db.Column(customer_db.String(100), nullable=True)
    updated_by     = customer_db.Column(customer_db.String(100), nullable=True)
    version        = customer_db.Column(customer_db.Integer,     nullable=False, default=1)

    items = customer_db.relationship("EstimateItem", back_populates="estimate", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Estimate {self.estimate_id}>"
    
    @property
    def client_obj(self):
        """Helper to get client object"""
        from sqlalchemy.orm import object_session
        session = object_session(self)
        if session and self.client_id:
            return session.query(Client).filter_by(id=self.client_id).first()
        return None


class EstimateItem(customer_db.Model):
    """Line item within a quotation/estimate"""
    __tablename__ = "estimate_items"

    id               = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    estimate_id      = customer_db.Column(customer_db.Integer,     customer_db.ForeignKey("estimates.id"), nullable=False)
    stock_item_id    = customer_db.Column(customer_db.Integer,     nullable=True)
    item_code        = customer_db.Column(customer_db.String(50),  nullable=True)
    code             = customer_db.Column(customer_db.String(50),  nullable=True)
    item_name        = customer_db.Column(customer_db.String(200), nullable=True)
    description      = customer_db.Column(customer_db.String(300), nullable=False)
    hsn              = customer_db.Column(customer_db.String(20),  nullable=True)
    qty              = customer_db.Column(customer_db.Float,       nullable=False, default=1.0)
    unit             = customer_db.Column(customer_db.String(20),  nullable=True, default="pcs")
    rate             = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    discount         = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    discount_percent = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    taxable_amount   = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    gst_percent      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    cgst_amount      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    sgst_amount      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    igst_amount      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    total_amount     = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)

    estimate = customer_db.relationship("Estimate", back_populates="items")

    def __repr__(self):
        return f"<EstimateItem {self.item_name or self.description} x {self.qty}>"


# ── 10. Purchase Invoices ─────────────────────────────────────────────────────
class PurchaseInvoice(customer_db.Model):
    __tablename__ = "purchase_invoices"

    id             = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    invoice_id     = customer_db.Column(customer_db.String(30),  unique=True, nullable=False)
    company_id     = customer_db.Column(customer_db.String(20),  nullable=False)
    supplier_id    = customer_db.Column(customer_db.Integer,     nullable=True)
    supplier_name  = customer_db.Column(customer_db.String(200), nullable=True)
    supplier_address = customer_db.Column(customer_db.Text,      nullable=True)
    supplier_gstin = customer_db.Column(customer_db.String(50),  nullable=True)
    supplier_state = customer_db.Column(customer_db.String(100), nullable=True)
    supplier_phone = customer_db.Column(customer_db.String(50),  nullable=True)
    supplier_email = customer_db.Column(customer_db.String(100), nullable=True)
    invoice_number = customer_db.Column(customer_db.String(100), nullable=True)
    reference_po_no = customer_db.Column(customer_db.String(100), nullable=True)
    date           = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    due_date       = customer_db.Column(customer_db.Date,        nullable=True)
    currency       = customer_db.Column(customer_db.String(10),  nullable=False, default="INR")
    exchange_rate  = customer_db.Column(customer_db.Float,       nullable=False, default=1.0)
    subtotal       = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    cgst_total     = customer_db.Column(customer_db.Float,       nullable=True, default=0.0)
    sgst_total     = customer_db.Column(customer_db.Float,       nullable=True, default=0.0)
    igst_total     = customer_db.Column(customer_db.Float,       nullable=True, default=0.0)
    tax_amount     = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    grand_total    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    base_subtotal  = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    base_tax_amount= customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    base_grand_total= customer_db.Column(customer_db.Float,      nullable=False, default=0.0)
    base_paid_amount= customer_db.Column(customer_db.Float,      nullable=False, default=0.0)
    base_balance   = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    tax_regime     = customer_db.Column(customer_db.String(50),  nullable=False, default="GST")
    tax_type       = customer_db.Column(customer_db.String(50),  nullable=False, default="Domestic") # Domestic, Import, RCM
    paid_amount    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    balance        = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    status         = customer_db.Column(customer_db.String(50),  nullable=False, default="Pending")
    payment_terms  = customer_db.Column(customer_db.String(100), nullable=True)
    terms          = customer_db.Column(customer_db.Text,        nullable=True)
    notes          = customer_db.Column(customer_db.Text,        nullable=True)
    file_path      = customer_db.Column(customer_db.String(500), nullable=True)
    ocr_data       = customer_db.Column(customer_db.Text,        nullable=True)
    created_by     = customer_db.Column(customer_db.String(100), nullable=True)
    updated_by     = customer_db.Column(customer_db.String(100), nullable=True)
    created_at     = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)

    items            = customer_db.relationship("PurchaseInvoiceItem",  back_populates="purchase_invoice", cascade="all, delete-orphan")
    purchase_history = customer_db.relationship("StockPurchaseHistory", back_populates="purchase_invoice", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<PurchaseInvoice {self.invoice_id}>"
    
    @property
    def supplier(self):
        """Helper to get supplier object"""
        from sqlalchemy.orm import object_session
        session = object_session(self)
        if session:
            return session.query(Supplier).filter_by(id=self.supplier_id).first()
        return None


class PurchaseInvoiceItem(customer_db.Model):
    __tablename__ = "purchase_invoice_items"

    id                  = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    purchase_invoice_id = customer_db.Column(customer_db.Integer,     customer_db.ForeignKey("purchase_invoices.id"), nullable=False)
    stock_item_id       = customer_db.Column(customer_db.Integer,     nullable=True)
    item_code           = customer_db.Column(customer_db.String(50),  nullable=True)
    code                = customer_db.Column(customer_db.String(50),  nullable=True)
    item_name           = customer_db.Column(customer_db.String(200), nullable=True)
    description         = customer_db.Column(customer_db.String(300), nullable=False)
    hsn                 = customer_db.Column(customer_db.String(20),  nullable=True)
    quantity            = customer_db.Column(customer_db.Float,       nullable=False, default=1.0)
    unit                = customer_db.Column(customer_db.String(20),  nullable=True, default="pcs")
    rate                = customer_db.Column(customer_db.Float,       nullable=True, default=0.0)
    purchase_rate       = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    discount_percent    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    taxable_amount      = customer_db.Column(customer_db.Float,       nullable=True, default=0.0)
    taxable_value       = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    gst_percent         = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    cgst_amount         = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    sgst_amount         = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    igst_amount         = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    total_amount        = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    base_rate           = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    base_taxable_amount = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    base_total_amount   = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)

    # ── Logistics-specific particulars (retained for backward compatibility) ─
    docket_no       = customer_db.Column(customer_db.String(100), nullable=True)
    carrier_ref     = customer_db.Column(customer_db.String(100), nullable=True)
    party_name      = customer_db.Column(customer_db.String(200), nullable=True)
    consignee_name  = customer_db.Column(customer_db.String(200), nullable=True)
    destination     = customer_db.Column(customer_db.String(150), nullable=True)
    courier_name    = customer_db.Column(customer_db.String(100), nullable=True)
    weight_kg       = customer_db.Column(customer_db.Float,       nullable=True, default=0.0)
    rate_per_kg     = customer_db.Column(customer_db.Float,       nullable=True, default=0.0)
    other_charges   = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    resale_charges  = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    source_invoice_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey("invoices.id"), nullable=True)

    purchase_invoice = customer_db.relationship("PurchaseInvoice", back_populates="items")

class PurchasePayment(customer_db.Model):
    __tablename__ = "purchase_payments"

    id             = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    company_id     = customer_db.Column(customer_db.String(20),  nullable=False)
    invoice_id     = customer_db.Column(customer_db.Integer,     customer_db.ForeignKey("purchase_invoices.id"), nullable=False)
    supplier_id    = customer_db.Column(customer_db.Integer,     nullable=True)
    date           = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    amount         = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    pay_mode       = customer_db.Column(customer_db.String(30),  nullable=False, default="Cash")
    narration      = customer_db.Column(customer_db.String(300), nullable=True)
    created_at     = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)
    created_by     = customer_db.Column(customer_db.String(50),  nullable=True)

    invoice = customer_db.relationship("PurchaseInvoice", backref="payments")
# ── 11. Stock Purchase History ────────────────────────────────────────────────
class StockPurchaseHistory(customer_db.Model):
    __tablename__ = "stock_purchase_history"

    id                  = customer_db.Column(customer_db.Integer,  primary_key=True, autoincrement=True)
    stock_item_id       = customer_db.Column(customer_db.Integer,  nullable=False)
    purchase_invoice_id = customer_db.Column(customer_db.Integer,
                              customer_db.ForeignKey("purchase_invoices.id"), nullable=True)
    quantity            = customer_db.Column(customer_db.Float,    nullable=False)
    purchase_rate       = customer_db.Column(customer_db.Float,    nullable=False)
    currency            = customer_db.Column(customer_db.String(10), nullable=False, default="INR")
    exchange_rate       = customer_db.Column(customer_db.Float,    nullable=False, default=1.0)
    base_purchase_rate  = customer_db.Column(customer_db.Float,    nullable=False, default=0.0)
    gst_percent         = customer_db.Column(customer_db.Float,    nullable=False, default=0.0)
    purchase_date       = customer_db.Column(customer_db.Date,     nullable=False, default=date.today)
    movement_type       = customer_db.Column(customer_db.String(10), nullable=True, default="IN")
    reference           = customer_db.Column(customer_db.String(100), nullable=True)

    # ── Shipment-level detail (populated when the movement comes from a booking) ──
    awb_no              = customer_db.Column(customer_db.String(50),  nullable=True)
    source              = customer_db.Column(customer_db.String(100), nullable=True)
    destination         = customer_db.Column(customer_db.String(100), nullable=True)
    length              = customer_db.Column(customer_db.Float,       nullable=True)
    width               = customer_db.Column(customer_db.Float,       nullable=True)
    height              = customer_db.Column(customer_db.Float,       nullable=True)
    weight              = customer_db.Column(customer_db.Float,       nullable=True)

    purchase_invoice = customer_db.relationship("PurchaseInvoice", back_populates="purchase_history")


# ── 11b. Statement Closings (archived old statements when outstanding is
# cleared or shifted to opening balance) ─────────────────────────────────────
class StatementClosing(customer_db.Model):
    __tablename__ = "statement_closings"

    id              = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    company_id      = customer_db.Column(customer_db.String(20),  nullable=False)
    entity_type     = customer_db.Column(customer_db.String(20),  nullable=False)   # 'client' | 'supplier'
    entity_id       = customer_db.Column(customer_db.Integer,     nullable=False)
    entity_name     = customer_db.Column(customer_db.String(200), nullable=False)
    action          = customer_db.Column(customer_db.String(20),  nullable=False)   # 'cleared' | 'carried_forward'
    closing_balance = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    total_debit     = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    total_credit    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    ledger_snapshot = customer_db.Column(customer_db.Text,        nullable=True)    # JSON dump of the frozen ledger rows
    closed_by       = customer_db.Column(customer_db.String(50),  nullable=True)
    closed_at       = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<StatementClosing {self.entity_type}:{self.entity_id} {self.action} @ {self.closed_at}>"


# ── 12. Cash Transactions ─────────────────────────────────────────────────────
class CashTransaction(customer_db.Model):
    __tablename__ = "cash_transactions"

    id          = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    company_id  = customer_db.Column(customer_db.String(20),  nullable=False)
    type        = customer_db.Column(customer_db.String(20),  nullable=False)
    date        = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    category    = customer_db.Column(customer_db.String(100), nullable=False)
    description = customer_db.Column(customer_db.String(300), nullable=False)
    amount      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    reference   = customer_db.Column(customer_db.String(100), nullable=True)
    notes       = customer_db.Column(customer_db.Text,        nullable=True)
    party_name  = customer_db.Column(customer_db.String(200), nullable=True)  # client/supplier name at time of transaction
    created_at  = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)
    created_by  = customer_db.Column(customer_db.String(50),  nullable=True)
    applied_ci_ids_json = customer_db.Column(customer_db.Text, nullable=True)

    # ── Structural link back to the invoice this transaction settled ────────
    # `reference` above is a display string (invoice number / "ADVANCE") and
    # is NOT reliable for reversal: it's ambiguous (multiple bookings under
    # one CustomerInvoice share the same reference) and ties parsing logic
    # to formatting. These columns store the real, unambiguous DB id so a
    # payment/receipt can be deleted and correctly un-applied.
    # applied_ref_type: "purchase_invoice" | "invoice" | None (None = advance/unapplied, nothing to reverse)
    # applied_ref_id:   PK of the PurchaseInvoice or (booking) Invoice actually mutated
    # applied_ci_id:    PK of the CustomerInvoice to re-sync after reversal (receipts only, nullable)
    applied_ref_type = customer_db.Column(customer_db.String(20), nullable=True)
    applied_ref_id   = customer_db.Column(customer_db.Integer,    nullable=True)
    applied_ci_id    = customer_db.Column(customer_db.Integer,    nullable=True)

    # JSON map of {booking Invoice.id (str): amount applied to it (float)}.
    # Only set when this single transaction settles money across MULTIPLE
    # bookings under one CustomerInvoice (applied_ref_type ==
    # "customer_invoice") — that's the one case applied_ref_id alone can't
    # describe. Lets a delete/reversal peel the exact amount back off each
    # exact booking instead of only re-syncing the CustomerInvoice's totals.
    applied_breakdown_json = customer_db.Column(customer_db.Text, nullable=True)


# ── 13. Bank Accounts ─────────────────────────────────────────────────────────
class BankAccount(customer_db.Model):
    __tablename__ = "bank_accounts"

    id             = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    company_id     = customer_db.Column(customer_db.String(20),  nullable=False)
    bank_name      = customer_db.Column(customer_db.String(200), nullable=False)
    account_name   = customer_db.Column(customer_db.String(200), nullable=False)
    account_number = customer_db.Column(customer_db.String(50),  nullable=False, unique=True)
    ifsc_code      = customer_db.Column(customer_db.String(20),  nullable=True)
    branch         = customer_db.Column(customer_db.String(200), nullable=True)
    balance        = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    opening_balance= customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    status         = customer_db.Column(customer_db.String(30),  nullable=False, default="Active")
    notes          = customer_db.Column(customer_db.Text,        nullable=True)
    created_at     = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)
    updated_at     = customer_db.Column(customer_db.DateTime,    nullable=True, onupdate=datetime.utcnow)

    transactions = customer_db.relationship("BankTransaction", back_populates="bank_account", cascade="all, delete-orphan")


# ── 14. Bank Transactions ─────────────────────────────────────────────────────
class BankTransaction(customer_db.Model):
    __tablename__ = "bank_transactions"

    id               = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    bank_account_id  = customer_db.Column(customer_db.Integer,     customer_db.ForeignKey("bank_accounts.id"), nullable=False)
    company_id       = customer_db.Column(customer_db.String(20),  nullable=False)
    type             = customer_db.Column(customer_db.String(20),  nullable=False)
    date             = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    description      = customer_db.Column(customer_db.String(300), nullable=False)
    amount           = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    reference        = customer_db.Column(customer_db.String(100), nullable=True)
    transaction_mode = customer_db.Column(customer_db.String(30),  nullable=True)
    notes            = customer_db.Column(customer_db.Text,        nullable=True)
    party_name       = customer_db.Column(customer_db.String(200), nullable=True)  # client/supplier name at time of transaction
    created_at       = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)
    created_by       = customer_db.Column(customer_db.String(50),  nullable=True)
    applied_ci_ids_json = customer_db.Column(customer_db.Text, nullable=True)

    # ── Structural link back to the invoice this transaction settled ────────
    # See CashTransaction above for why this exists — `reference` alone is
    # not safe to reverse a payment/receipt against.
    applied_ref_type = customer_db.Column(customer_db.String(20), nullable=True)
    applied_ref_id   = customer_db.Column(customer_db.Integer,    nullable=True)
    applied_ci_id    = customer_db.Column(customer_db.Integer,    nullable=True)

    # See CashTransaction.applied_breakdown_json — same purpose here.
    applied_breakdown_json = customer_db.Column(customer_db.Text, nullable=True)

    bank_account = customer_db.relationship("BankAccount", back_populates="transactions")


# ── 15. Loans ─────────────────────────────────────────────────────────────────
class Loan(customer_db.Model):
    __tablename__ = "loans"

    id            = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    company_id    = customer_db.Column(customer_db.String(20),  nullable=False)
    type          = customer_db.Column(customer_db.String(20),  nullable=False)
    party_name    = customer_db.Column(customer_db.String(200), nullable=False)
    loan_date     = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    amount        = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    interest_rate = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    tenure        = customer_db.Column(customer_db.Integer,     nullable=False, default=12)
    emi_amount    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    purpose       = customer_db.Column(customer_db.String(300), nullable=True)
    notes         = customer_db.Column(customer_db.Text,        nullable=True)
    status        = customer_db.Column(customer_db.String(30),  nullable=False, default="Active")
    created_at    = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)
    created_by    = customer_db.Column(customer_db.String(50),  nullable=True)

    repayments = customer_db.relationship("LoanRepayment", back_populates="loan", cascade="all, delete-orphan")

    @property
    def repaid_amount(self):
        return sum(r.amount for r in self.repayments)

    @property
    def remaining_amount(self):
        return max(0, self.amount - self.repaid_amount)
    
    @property
    def repayment_percentage(self):
        if self.amount > 0:
            return (self.repaid_amount / self.amount) * 100
        return 0


class LoanRepayment(customer_db.Model):
    __tablename__ = "loan_repayments"

    id           = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    loan_id      = customer_db.Column(customer_db.Integer,     customer_db.ForeignKey("loans.id"), nullable=False)
    date         = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    amount       = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    payment_mode = customer_db.Column(customer_db.String(30),  nullable=False, default="Cash")
    reference    = customer_db.Column(customer_db.String(100), nullable=True)
    notes        = customer_db.Column(customer_db.Text,        nullable=True)
    created_at   = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)

    loan = customer_db.relationship("Loan", back_populates="repayments")


# ── 15b. Cheques ───────────────────────────────────────────────────────────────
# Register of cheques received from clients or issued to suppliers.
# A cheque sits in "Pending" status until it actually clears the bank; only
# clearing creates the real BankTransaction that moves the bank balance.
class Cheque(customer_db.Model):
    __tablename__ = "cheques"

    id              = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    company_id      = customer_db.Column(customer_db.String(20),  nullable=False)
    direction       = customer_db.Column(customer_db.String(10),  nullable=False)   # 'received' | 'paid'
    party_type      = customer_db.Column(customer_db.String(10),  nullable=True)    # 'client' | 'supplier'
    party_id        = customer_db.Column(customer_db.Integer,     nullable=True)
    party_name      = customer_db.Column(customer_db.String(200), nullable=False)
    cheque_no       = customer_db.Column(customer_db.String(30),  nullable=False)
    cheque_date     = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    bank_name       = customer_db.Column(customer_db.String(200), nullable=True)
    bank_account_id = customer_db.Column(customer_db.Integer,     customer_db.ForeignKey("bank_accounts.id"), nullable=True)
    amount          = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    narration       = customer_db.Column(customer_db.String(300), nullable=True)
    status          = customer_db.Column(customer_db.String(20),  nullable=False, default="Pending")  # Pending | Cleared | Bounced | Cancelled
    cleared_date    = customer_db.Column(customer_db.Date,        nullable=True)
    bank_txn_id     = customer_db.Column(customer_db.Integer,     customer_db.ForeignKey("bank_transactions.id"), nullable=True)
    notes           = customer_db.Column(customer_db.Text,        nullable=True)
    created_at      = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)
    created_by      = customer_db.Column(customer_db.String(50),  nullable=True)

    # Optional link to the specific bill this cheque is being applied against.
    # Only one of these is ever set, matching `direction`: invoice_id for a
    # 'received' cheque (against a client's Invoice), purchase_invoice_id for
    # a 'paid' cheque (against a Supplier's PurchaseInvoice). Both stay NULL
    # for a general/advance cheque not tied to any specific bill — the party
    # still gets picked, it just isn't applied against an invoice balance
    # until (and unless) the user links it to one later.
    invoice_id          = customer_db.Column(customer_db.Integer, customer_db.ForeignKey("invoices.id"), nullable=True)
    purchase_invoice_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey("purchase_invoices.id"), nullable=True)

    bank_account = customer_db.relationship("BankAccount")
    invoice          = customer_db.relationship("Invoice", foreign_keys=[invoice_id])
    purchase_invoice = customer_db.relationship("PurchaseInvoice", foreign_keys=[purchase_invoice_id])



# ── 16. Company Manifest ──────────────────────────────────────────────────────
# Tracks boxes received from a shipper client and how they are distributed
# to different courier companies. Saving a manifest DEDUCTS stock from StockItem.
class CompanyManifest(customer_db.Model):
    __tablename__ = "company_manifests"

    id             = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    manifest_id    = customer_db.Column(customer_db.String(30),  unique=True, nullable=False)
    company_id     = customer_db.Column(customer_db.String(20),  nullable=False)
    date           = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    # shipper = the customer who brought boxes in (links to Client.id)
    shipper_client_id   = customer_db.Column(customer_db.Integer, nullable=True)
    shipper_client_name = customer_db.Column(customer_db.String(200), nullable=False)
    # stock item whose qty is deducted (box/parcel stock)
    stock_item_id  = customer_db.Column(customer_db.Integer,     nullable=True)
    total_boxes    = customer_db.Column(customer_db.Integer,     nullable=False, default=0)
    notes          = customer_db.Column(customer_db.Text,        nullable=True)
    created_at     = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)
    created_by     = customer_db.Column(customer_db.String(50),  nullable=True)
    status         = Column(String(20), default='Pending', nullable=False)
    stock_deducted = Column(Boolean, default=False, nullable=False)
    generated_at   = Column(DateTime, nullable=True)
    generated_by   = Column(String(255), nullable=True)

    entries = customer_db.relationship(
        "ManifestEntry", back_populates="manifest", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<CompanyManifest {self.manifest_id}>"


# ── 17. Manifest Entry (courier allocation per manifest) ──────────────────────
class ManifestEntry(customer_db.Model):
    __tablename__ = "manifest_entries"

    id            = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    manifest_id   = customer_db.Column(customer_db.Integer,
                        customer_db.ForeignKey("company_manifests.id"), nullable=False)
    courier_name  = customer_db.Column(customer_db.String(200), nullable=False)
    boxes         = customer_db.Column(customer_db.Integer,     nullable=False, default=0)
    docket_no     = customer_db.Column(customer_db.String(100), nullable=True)
    docket_id     = customer_db.Column(customer_db.Integer,     nullable=True)   # ← ADD
    stock_item_id = customer_db.Column(customer_db.Integer,     nullable=True)
    stock_item_name = customer_db.Column(customer_db.String(200), nullable=True) # ← ADD
    notes         = customer_db.Column(customer_db.Text,        nullable=True)
    item_type = customer_db.Column(customer_db.String(50), nullable=True)
    status        = customer_db.Column(customer_db.String(20),  nullable=False, default='Pending')  # ← ADD: 'Pending' or 'Generated', per box row
    generated_at  = customer_db.Column(customer_db.DateTime,    nullable=True)  # ← ADD
    generated_by  = customer_db.Column(customer_db.String(255), nullable=True)  # ← ADD
    dispatched_at = customer_db.Column(customer_db.DateTime, nullable=True)     # ← ADD: set only by /manifest/entry/<id>/dispatch
    dispatched_by = customer_db.Column(customer_db.String(255), nullable=True)  # ← ADD

    manifest = customer_db.relationship("CompanyManifest", back_populates="entries")

    def __repr__(self):
        return f"<ManifestEntry {self.courier_name} x{self.boxes} [{self.status}]>"


# Expenses
# ── 18. Daily Expenses ────────────────────────────────────────────────────────
class Expense(customer_db.Model):
    __tablename__ = "expenses"

    id          = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    company_id  = customer_db.Column(customer_db.String(20),  nullable=False)
    date        = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    category    = customer_db.Column(customer_db.String(100), nullable=False)
    description = customer_db.Column(customer_db.String(300), nullable=True)
    amount      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    payment_mode= customer_db.Column(customer_db.String(30),  nullable=False, default="Cash")
    reference   = customer_db.Column(customer_db.String(100), nullable=True)
    created_by  = customer_db.Column(customer_db.String(100), nullable=True)
    created_at  = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<Expense {self.id} {self.category} ₹{self.amount}>"


# ── 19. WhatsApp Send Log ──────────────────────────────────────────────────────
# One row per attempted send — transactional (invoice_id set) or campaign
# (campaign_id set). Lives in the customer DB because volume scales with the
# tenant's own message traffic, same tier as Expense/CashTransaction.
class WhatsAppLog(customer_db.Model):
    __tablename__ = "whatsapp_logs"

    id             = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    company_id     = customer_db.Column(customer_db.String(20),  nullable=False)
    template_key   = customer_db.Column(customer_db.String(50),  nullable=True)
    to_phone       = customer_db.Column(customer_db.String(20),  nullable=False)
    invoice_id     = customer_db.Column(customer_db.String(30),  nullable=True)  # set for transactional sends
    manifest_id    = customer_db.Column(customer_db.String(30),  nullable=True)  # set for manifest/AWB sends
    campaign_id    = customer_db.Column(customer_db.String(50),  nullable=True)  # set for bulk campaign sends
    status         = customer_db.Column(customer_db.String(20),  nullable=False, default="pending")  # pending|sent|failed|manual_pending
    provider       = customer_db.Column(customer_db.String(20),  nullable=True)
    provider_msg_id= customer_db.Column(customer_db.String(100), nullable=True)
    error_message  = customer_db.Column(customer_db.Text,        nullable=True)
    attempt_count  = customer_db.Column(customer_db.Integer,     nullable=False, default=0)
    manual_link    = customer_db.Column(customer_db.Text,        nullable=True)  # wa.me link when no API / send failed
    created_at     = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)
    sent_at        = customer_db.Column(customer_db.DateTime,    nullable=True)

    def __repr__(self):
        return f"<WhatsAppLog {self.id} {self.to_phone} {self.status}>"


# ── 22. Delivery Challans (Dispatch / Delivery Note) ─────────────────────────
class DeliveryChallan(customer_db.Model):
    __tablename__ = "delivery_challans"

    id                  = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    challan_no          = customer_db.Column(customer_db.String(30),  unique=True, nullable=False)
    company_id          = customer_db.Column(customer_db.String(20),  nullable=False)
    client_id           = customer_db.Column(customer_db.Integer,     nullable=True)
    client_name         = customer_db.Column(customer_db.String(200), nullable=True)
    challan_date        = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    delivery_date       = customer_db.Column(customer_db.Date,        nullable=True)
    reference_order_no  = customer_db.Column(customer_db.String(100), nullable=True)
    challan_type        = customer_db.Column(customer_db.String(50),  nullable=False, default="Delivery on Sale")
    transporter_name    = customer_db.Column(customer_db.String(150), nullable=True)
    vehicle_no          = customer_db.Column(customer_db.String(50),  nullable=True)
    lr_no               = customer_db.Column(customer_db.String(50),  nullable=True)
    dispatch_from       = customer_db.Column(customer_db.String(255), nullable=True)
    shipping_address    = customer_db.Column(customer_db.Text,        nullable=True)
    status              = customer_db.Column(customer_db.String(50),  nullable=False, default="Draft")
    stock_deducted      = customer_db.Column(customer_db.Boolean,     nullable=False, default=False)
    subtotal            = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    tax_amount          = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    grand_total         = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    terms               = customer_db.Column(customer_db.Text,        nullable=True)
    notes               = customer_db.Column(customer_db.Text,        nullable=True)
    invoiced_invoice_id = customer_db.Column(customer_db.Integer,     nullable=True)
    created_by          = customer_db.Column(customer_db.String(100), nullable=True)
    updated_by          = customer_db.Column(customer_db.String(100), nullable=True)
    created_at          = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)
    updated_at          = customer_db.Column(customer_db.DateTime,    nullable=True, onupdate=datetime.utcnow)

    items = customer_db.relationship("DeliveryChallanItem", back_populates="challan", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<DeliveryChallan {self.challan_no}>"

    @property
    def client_obj(self):
        from sqlalchemy.orm import object_session
        session = object_session(self)
        if session and self.client_id:
            return session.query(Client).filter_by(id=self.client_id).first()
        return None


class DeliveryChallanItem(customer_db.Model):
    __tablename__ = "delivery_challan_items"

    id               = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    challan_id       = customer_db.Column(customer_db.Integer,     customer_db.ForeignKey("delivery_challans.id"), nullable=False)
    stock_item_id    = customer_db.Column(customer_db.Integer,     nullable=True)
    item_code        = customer_db.Column(customer_db.String(50),  nullable=True)
    item_name        = customer_db.Column(customer_db.String(200), nullable=False)
    description      = customer_db.Column(customer_db.String(300), nullable=True)
    hsn              = customer_db.Column(customer_db.String(20),  nullable=True)
    quantity         = customer_db.Column(customer_db.Float,       nullable=False, default=1.0)
    unit             = customer_db.Column(customer_db.String(20),  nullable=True, default="pcs")
    rate             = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    discount_percent = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    taxable_amount   = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    gst_percent      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    cgst_amount      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    sgst_amount      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    igst_amount      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    total_amount     = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)

    challan = customer_db.relationship("DeliveryChallan", back_populates="items")

    def __repr__(self):
        return f"<DeliveryChallanItem {self.item_name} x {self.quantity}>"


# ── 23. Sales Orders (SO) ─────────────────────────────────────────────────────
class SalesOrder(customer_db.Model):
    __tablename__ = "sales_orders"

    id            = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    order_no      = customer_db.Column(customer_db.String(30),  unique=True, nullable=False)
    company_id    = customer_db.Column(customer_db.String(20),  nullable=False)
    client_id     = customer_db.Column(customer_db.Integer,     nullable=True)
    client_name   = customer_db.Column(customer_db.String(200), nullable=True)
    order_date    = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    delivery_date = customer_db.Column(customer_db.Date,        nullable=True)
    reference_no  = customer_db.Column(customer_db.String(100), nullable=True)
    status        = customer_db.Column(customer_db.String(50),  nullable=False, default="Draft")
    subtotal      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    tax_amount    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    cgst_total    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    sgst_total    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    igst_total    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    grand_total   = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    terms         = customer_db.Column(customer_db.Text,        nullable=True)
    notes         = customer_db.Column(customer_db.Text,        nullable=True)
    created_by    = customer_db.Column(customer_db.String(100), nullable=True)
    updated_by    = customer_db.Column(customer_db.String(100), nullable=True)
    created_at    = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)
    updated_at    = customer_db.Column(customer_db.DateTime,    nullable=True, onupdate=datetime.utcnow)

    items = customer_db.relationship("SalesOrderItem", back_populates="sales_order", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SalesOrder {self.order_no}>"

    @property
    def client_obj(self):
        from sqlalchemy.orm import object_session
        session = object_session(self)
        if session and self.client_id:
            return session.query(Client).filter_by(id=self.client_id).first()
        return None
    
    def to_dict(self):
        client = self.client_obj
        from sqlalchemy.orm import object_session
        sess = object_session(self)
        item_list = []
        try:
            if self.items:
                item_list = [item.to_dict() for item in self.items]
        except Exception:
            pass
        if not item_list and sess and self.id:
            try:
                db_items = sess.query(SalesOrderItem).filter_by(sales_order_id=self.id).all()
                item_list = [item.to_dict() for item in db_items]
            except Exception:
                pass

        return {
            'id': self.id,
            'order_no': self.order_no,
            'company_id': self.company_id,
            'client_id': self.client_id,
            'client_name': self.client_name or (client.name if client else ''),
            'client_phone': client.phone if client else '',
            'client_email': client.email if client else '',
            'client_city': client.city if client else '',
            'client_gst': client.gst_number if client else '',
            'order_date': self.order_date.strftime('%Y-%m-%d') if self.order_date else None,
            'delivery_date': self.delivery_date.strftime('%Y-%m-%d') if self.delivery_date else None,
            'reference_no': self.reference_no or '',
            'status': self.status or 'Draft',
            'subtotal': self.subtotal or 0.0,
            'tax_amount': self.tax_amount or 0.0,
            'cgst_total': self.cgst_total or 0.0,
            'sgst_total': self.sgst_total or 0.0,
            'igst_total': self.igst_total or 0.0,
            'grand_total': self.grand_total or 0.0,
            'total_amount': self.grand_total or 0.0,
            'terms': self.terms or '',
            'notes': self.notes or '',
            'created_by': self.created_by or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'item_count': len(item_list),
            'items': item_list
        }


class SalesOrderItem(customer_db.Model):
    __tablename__ = "sales_order_items"

    id               = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    sales_order_id   = customer_db.Column(customer_db.Integer,     customer_db.ForeignKey("sales_orders.id"), nullable=False)
    stock_item_id    = customer_db.Column(customer_db.Integer,     nullable=True)
    item_code        = customer_db.Column(customer_db.String(50),  nullable=True)
    item_name        = customer_db.Column(customer_db.String(200), nullable=False)
    description      = customer_db.Column(customer_db.String(300), nullable=True)
    hsn              = customer_db.Column(customer_db.String(20),  nullable=True)
    quantity         = customer_db.Column(customer_db.Float,       nullable=False, default=1.0)
    delivered_qty    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    unit             = customer_db.Column(customer_db.String(20),  nullable=True, default="pcs")
    rate             = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    discount_percent = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    taxable_amount   = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    gst_percent      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    cgst_amount      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    sgst_amount      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    igst_amount      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    total_amount     = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)

    sales_order = customer_db.relationship("SalesOrder", back_populates="items")

    def __repr__(self):
        return f"<SalesOrderItem {self.item_name} x {self.quantity}>"

    def to_dict(self):
        return {
            'id': self.id,
            'sales_order_id': self.sales_order_id,
            'stock_item_id': self.stock_item_id,
            'item_code': self.item_code or '',
            'item_name': self.item_name,
            'description': self.description or '',
            'hsn': self.hsn or '',
            'quantity': self.quantity or 1.0,
            'delivered_qty': self.delivered_qty or 0.0,
            'unit': self.unit or 'pcs',
            'rate': self.rate or 0.0,
            'discount_percent': self.discount_percent or 0.0,
            'taxable_amount': self.taxable_amount or 0.0,
            'gst_percent': self.gst_percent or 0.0,
            'cgst_amount': self.cgst_amount or 0.0,
            'sgst_amount': self.sgst_amount or 0.0,
            'igst_amount': self.igst_amount or 0.0,
            'total_amount': self.total_amount or 0.0
        }


# ── 24. Purchase Orders (PO) ──────────────────────────────────────────────────
class PurchaseOrder(customer_db.Model):
    __tablename__ = "purchase_orders"

    id                     = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    po_number              = customer_db.Column(customer_db.String(30),  unique=True, nullable=False)
    company_id             = customer_db.Column(customer_db.String(20),  nullable=False)
    supplier_id            = customer_db.Column(customer_db.Integer,     nullable=True)
    supplier_name          = customer_db.Column(customer_db.String(200), nullable=True)
    po_date                = customer_db.Column(customer_db.Date,        nullable=False, default=date.today)
    expected_delivery_date = customer_db.Column(customer_db.Date,        nullable=True)
    reference_no           = customer_db.Column(customer_db.String(100), nullable=True)
    status                 = customer_db.Column(customer_db.String(50),  nullable=False, default="Draft")
    subtotal               = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    tax_amount             = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    cgst_total             = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    sgst_total             = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    igst_total             = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    grand_total            = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    terms                  = customer_db.Column(customer_db.Text,        nullable=True)
    notes                  = customer_db.Column(customer_db.Text,        nullable=True)
    created_by             = customer_db.Column(customer_db.String(100), nullable=True)
    updated_by             = customer_db.Column(customer_db.String(100), nullable=True)
    created_at             = customer_db.Column(customer_db.DateTime,    nullable=False, default=datetime.utcnow)
    updated_at             = customer_db.Column(customer_db.DateTime,    nullable=True, onupdate=datetime.utcnow)

    items = customer_db.relationship("PurchaseOrderItem", back_populates="purchase_order", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<PurchaseOrder {self.po_number}>"

    @property
    def supplier_obj(self):
        from sqlalchemy.orm import object_session
        session = object_session(self)
        if session and self.supplier_id:
            return session.query(Supplier).filter_by(id=self.supplier_id).first()
        return None


class PurchaseOrderItem(customer_db.Model):
    __tablename__ = "purchase_order_items"

    id                = customer_db.Column(customer_db.Integer,     primary_key=True, autoincrement=True)
    purchase_order_id = customer_db.Column(customer_db.Integer,     customer_db.ForeignKey("purchase_orders.id"), nullable=False)
    stock_item_id     = customer_db.Column(customer_db.Integer,     nullable=True)
    item_code         = customer_db.Column(customer_db.String(50),  nullable=True)
    item_name         = customer_db.Column(customer_db.String(200), nullable=False)
    description       = customer_db.Column(customer_db.String(300), nullable=True)
    hsn               = customer_db.Column(customer_db.String(20),  nullable=True)
    quantity          = customer_db.Column(customer_db.Float,       nullable=False, default=1.0)
    received_qty      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    unit              = customer_db.Column(customer_db.String(20),  nullable=True, default="pcs")
    rate              = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    discount_percent  = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    taxable_amount    = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    gst_percent       = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    cgst_amount       = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    sgst_amount       = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    igst_amount       = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)
    total_amount      = customer_db.Column(customer_db.Float,       nullable=False, default=0.0)

    purchase_order = customer_db.relationship("PurchaseOrder", back_populates="items")

    def __repr__(self):
        return f"<PurchaseOrderItem {self.item_name} x {self.quantity}>"


# ═════════════════════════════════════════════════════════════════════════════
# ── ORDERFLOW & CRM SUITE MODELS ─────────────────────────────────────────────
# ═════════════════════════════════════════════════════════════════════════════

class OrderDepartment(customer_db.Model):
    __tablename__ = 'order_departments'

    id          = customer_db.Column(customer_db.String(50), primary_key=True)
    company_id  = customer_db.Column(customer_db.String(50), nullable=False)
    name        = customer_db.Column(customer_db.String(100), nullable=False)
    role_type   = customer_db.Column(customer_db.String(50), nullable=False)
    description = customer_db.Column(customer_db.String(300), nullable=True)
    created_at  = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)
    is_active   = customer_db.Column(customer_db.Boolean, default=True)

    def to_dict(self):
        return {
            'id': self.id,
            'company_id': self.company_id,
            'name': self.name,
            'role_type': self.role_type,
            'description': self.description,
            'is_active': self.is_active,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class OrderFlow(customer_db.Model):
    """
    Dedicated Order Management / Manufacturing Order workflow model.
    Distinct from legacy simple invoice-orders.
    """
    __tablename__ = 'order_flows'

    id               = customer_db.Column(customer_db.String(50), primary_key=True)
    company_id       = customer_db.Column(customer_db.String(50), nullable=False)
    client_id        = customer_db.Column(customer_db.String(50), nullable=True)
    lead_id          = customer_db.Column(customer_db.String(50), nullable=True)
    client_name      = customer_db.Column(customer_db.String(200), nullable=False)
    client_phone     = customer_db.Column(customer_db.String(50), nullable=True)
    client_email     = customer_db.Column(customer_db.String(200), nullable=True)
    item_description = customer_db.Column(customer_db.Text, nullable=False)
    quantity         = customer_db.Column(customer_db.Integer, default=1)
    unit_price       = customer_db.Column(customer_db.Float, default=0.0)
    amount_due       = customer_db.Column(customer_db.Float, default=0.0)
    amount_paid      = customer_db.Column(customer_db.Float, default=0.0)
    status           = customer_db.Column(customer_db.String(50), nullable=False, default='Order Created')
    priority         = customer_db.Column(customer_db.String(20), default='normal')  # low, normal, high, urgent
    partner          = customer_db.Column(customer_db.String(100), nullable=True)
    source           = customer_db.Column(customer_db.String(100), nullable=True)
    notes            = customer_db.Column(customer_db.Text, nullable=True)
    internal_notes   = customer_db.Column(customer_db.Text, nullable=True)
    created_by       = customer_db.Column(customer_db.String(200), nullable=False)
    created_by_dept  = customer_db.Column(customer_db.String(100), nullable=True)
    taken_by         = customer_db.Column(customer_db.String(200), nullable=True)
    approved_by      = customer_db.Column(customer_db.String(200), nullable=True)
    created_at       = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at       = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        balance = (self.amount_due or 0.0) - (self.amount_paid or 0.0)
        return {
            'id': self.id,
            'company_id': self.company_id,
            'client_id': self.client_id,
            'lead_id': self.lead_id,
            'client_name': self.client_name,
            'client_phone': self.client_phone,
            'client_email': self.client_email,
            'item_description': self.item_description,
            'quantity': self.quantity or 1,
            'unit_price': self.unit_price or 0.0,
            'amount_due': self.amount_due or 0.0,
            'amount_paid': self.amount_paid or 0.0,
            'balance': balance,
            'payment_status': 'Paid' if balance <= 0 else ('Amount Pending' if (self.amount_paid or 0) > 0 else 'Unpaid'),
            'status': self.status,
            'priority': self.priority or 'normal',
            'partner': self.partner or '',
            'source': self.source or '',
            'notes': self.notes or '',
            'internal_notes': self.internal_notes or '',
            'created_by': self.created_by or 'System',
            'created_by_dept': self.created_by_dept or '',
            'taken_by': self.taken_by or '',
            'approved_by': self.approved_by or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None
        }


class OrderFlowHistory(customer_db.Model):
    __tablename__ = 'order_flow_history'

    id              = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    order_id        = customer_db.Column(customer_db.String(50), nullable=False)
    status          = customer_db.Column(customer_db.String(50), nullable=False)
    note            = customer_db.Column(customer_db.Text, nullable=True)
    changed_by      = customer_db.Column(customer_db.String(200), nullable=False)
    changed_by_dept = customer_db.Column(customer_db.String(100), nullable=True)
    changed_by_role = customer_db.Column(customer_db.String(50), nullable=True)
    payment_mode    = customer_db.Column(customer_db.String(100), nullable=True)
    payment_ref     = customer_db.Column(customer_db.String(200), nullable=True)
    changed_at      = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'status': self.status,
            'note': self.note or '',
            'changed_by': self.changed_by,
            'changed_by_dept': self.changed_by_dept or '',
            'changed_by_role': self.changed_by_role or '',
            'payment_mode': self.payment_mode or '',
            'payment_ref': self.payment_ref or '',
            'changed_at': self.changed_at.strftime('%Y-%m-%d %H:%M:%S') if self.changed_at else None
        }


class CRMContact(customer_db.Model):
    """Contacts & Key Stakeholders tied to client accounts."""
    __tablename__ = 'crm_contacts'

    id          = customer_db.Column(customer_db.String(50), primary_key=True)
    company_id  = customer_db.Column(customer_db.String(50), nullable=False)
    client_id   = customer_db.Column(customer_db.String(50), nullable=False)
    name        = customer_db.Column(customer_db.String(200), nullable=False)
    designation = customer_db.Column(customer_db.String(100), nullable=True)
    phone       = customer_db.Column(customer_db.String(50), nullable=True)
    email       = customer_db.Column(customer_db.String(200), nullable=True)
    is_primary  = customer_db.Column(customer_db.Boolean, default=False)
    notes       = customer_db.Column(customer_db.Text, nullable=True)
    created_at  = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'company_id': self.company_id,
            'client_id': self.client_id,
            'name': self.name,
            'designation': self.designation or '',
            'phone': self.phone or '',
            'email': self.email or '',
            'is_primary': bool(self.is_primary),
            'notes': self.notes or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


class CRMLead(customer_db.Model):
    """Pre-order sales opportunity in the CRM pipeline."""
    __tablename__ = 'crm_leads'

    id                  = customer_db.Column(customer_db.String(50), primary_key=True)
    company_id          = customer_db.Column(customer_db.String(50), nullable=False)
    client_id           = customer_db.Column(customer_db.String(50), nullable=False)
    client_name         = customer_db.Column(customer_db.String(200), nullable=True)
    title               = customer_db.Column(customer_db.String(200), nullable=False)
    stage               = customer_db.Column(customer_db.String(30), nullable=False, default='New')
    estimated_value     = customer_db.Column(customer_db.Float, default=0.0)
    source              = customer_db.Column(customer_db.String(100), nullable=True)
    expected_close_date = customer_db.Column(customer_db.Date, nullable=True)
    assigned_to         = customer_db.Column(customer_db.String(200), nullable=True)
    notes               = customer_db.Column(customer_db.Text, nullable=True)
    lost_reason         = customer_db.Column(customer_db.String(300), nullable=True)
    converted_order_id  = customer_db.Column(customer_db.String(50), nullable=True)
    created_by          = customer_db.Column(customer_db.String(200), nullable=True)
    created_at          = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at          = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'company_id': self.company_id,
            'client_id': self.client_id,
            'client_name': self.client_name or '',
            'title': self.title,
            'stage': self.stage,
            'estimated_value': self.estimated_value or 0.0,
            'source': self.source or '',
            'expected_close_date': self.expected_close_date.strftime('%Y-%m-%d') if self.expected_close_date else None,
            'assigned_to': self.assigned_to or '',
            'notes': self.notes or '',
            'lost_reason': self.lost_reason or '',
            'converted_order_id': self.converted_order_id or '',
            'created_by': self.created_by or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
        }


class CRMInteraction(customer_db.Model):
    """Touchpoint, activity, call, meeting, task or note."""
    __tablename__ = 'crm_interactions'

    id             = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    company_id     = customer_db.Column(customer_db.String(50), nullable=False)
    client_id      = customer_db.Column(customer_db.String(50), nullable=False)
    lead_id        = customer_db.Column(customer_db.String(50), nullable=True)
    type           = customer_db.Column(customer_db.String(20), nullable=False)  # call, email, meeting, whatsapp, task, note
    title          = customer_db.Column(customer_db.String(200), nullable=True)
    summary        = customer_db.Column(customer_db.Text, nullable=False)
    priority       = customer_db.Column(customer_db.String(20), default='normal')
    status         = customer_db.Column(customer_db.String(20), default='pending')
    due_date       = customer_db.Column(customer_db.Date, nullable=True)
    follow_up_date = customer_db.Column(customer_db.Date, nullable=True)
    follow_up_done = customer_db.Column(customer_db.Boolean, default=False)
    created_by     = customer_db.Column(customer_db.String(200), nullable=False)
    created_at     = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'company_id': self.company_id,
            'client_id': self.client_id,
            'lead_id': self.lead_id,
            'type': self.type,
            'title': self.title or (f"{self.type.title()}: {self.summary[:30]}" if self.summary else self.type.title()),
            'summary': self.summary,
            'priority': self.priority or 'normal',
            'status': self.status or ('completed' if self.follow_up_done else 'pending'),
            'due_date': self.due_date.strftime('%Y-%m-%d') if self.due_date else (self.follow_up_date.strftime('%Y-%m-%d') if self.follow_up_date else None),
            'follow_up_date': self.follow_up_date.strftime('%Y-%m-%d') if self.follow_up_date else None,
            'follow_up_done': bool(self.follow_up_done),
            'created_by': self.created_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


class CRMQuotation(customer_db.Model):
    """Sales Quotation / Price Proposal with line items and order conversion."""
    __tablename__ = 'crm_quotations'

    id                 = customer_db.Column(customer_db.String(50), primary_key=True)
    quote_number       = customer_db.Column(customer_db.String(50), nullable=False)
    company_id         = customer_db.Column(customer_db.String(50), nullable=False)
    client_id          = customer_db.Column(customer_db.String(50), nullable=False)
    client_name        = customer_db.Column(customer_db.String(200), nullable=True)
    lead_id            = customer_db.Column(customer_db.String(50), nullable=True)
    title              = customer_db.Column(customer_db.String(255), nullable=False)
    items_json         = customer_db.Column(customer_db.Text, nullable=True)
    subtotal           = customer_db.Column(customer_db.Float, default=0.0)
    cgst               = customer_db.Column(customer_db.Float, default=0.0)
    sgst               = customer_db.Column(customer_db.Float, default=0.0)
    total_amount       = customer_db.Column(customer_db.Float, default=0.0)
    status             = customer_db.Column(customer_db.String(30), default='Draft')  # Draft, Sent, Accepted, Rejected
    valid_until        = customer_db.Column(customer_db.Date, nullable=True)
    notes              = customer_db.Column(customer_db.Text, nullable=True)
    terms              = customer_db.Column(customer_db.Text, nullable=True)
    converted_order_id = customer_db.Column(customer_db.String(50), nullable=True)
    created_by         = customer_db.Column(customer_db.String(200), nullable=False)
    created_at         = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at         = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        import json
        items = []
        try:
            if self.items_json:
                items = json.loads(self.items_json)
        except Exception:
            items = []

        return {
            'id': self.id,
            'quote_number': self.quote_number,
            'quotation_number': self.quote_number,
            'company_id': self.company_id,
            'client_id': self.client_id,
            'client_name': self.client_name or '',
            'lead_id': self.lead_id,
            'title': self.title,
            'items': items,
            'subtotal': self.subtotal or 0.0,
            'cgst': self.cgst or 0.0,
            'sgst': self.sgst or 0.0,
            'tax_cgst': self.cgst or 0.0,
            'tax_sgst': self.sgst or 0.0,
            'total_amount': self.total_amount or 0.0,
            'status': self.status,
            'valid_until': self.valid_until.strftime('%Y-%m-%d') if self.valid_until else None,
            'quotation_date': self.created_at.strftime('%Y-%m-%d') if self.created_at else None,
            'notes': self.notes or '',
            'terms': self.terms or '',
            'terms_conditions': self.terms or '',
            'converted_order_id': self.converted_order_id or '',
            'created_by': self.created_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
        }


class CRMCommunicationLog(customer_db.Model):
    """WhatsApp, Email and phone communication trail."""
    __tablename__ = 'crm_comm_logs'

    id          = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    company_id  = customer_db.Column(customer_db.String(50), nullable=False)
    client_id   = customer_db.Column(customer_db.String(50), nullable=False)
    channel     = customer_db.Column(customer_db.String(20), nullable=False)  # whatsapp, email, phone
    recipient   = customer_db.Column(customer_db.String(200), nullable=False)
    subject     = customer_db.Column(customer_db.String(255), nullable=True)
    message     = customer_db.Column(customer_db.Text, nullable=False)
    sent_by     = customer_db.Column(customer_db.String(200), nullable=False)
    status      = customer_db.Column(customer_db.String(20), default='sent')
    created_at  = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'company_id': self.company_id,
            'client_id': self.client_id,
            'channel': self.channel,
            'recipient': self.recipient,
            'subject': self.subject or '',
            'message': self.message,
            'sent_by': self.sent_by,
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


class CRMSetting(customer_db.Model):
    """Per-company CRM customization and pipeline rules."""
    __tablename__ = 'crm_settings'

    id          = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    company_id  = customer_db.Column(customer_db.String(50), nullable=False)
    key         = customer_db.Column(customer_db.String(100), nullable=False)
    value_json  = customer_db.Column(customer_db.Text, nullable=True)
    updated_at  = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)




# ══════════════════════════════════════════════════════════════════════════════
# AUTOMOTIVE WORKSHOP & REPAIR MANAGEMENT MODULE MODELS
# ══════════════════════════════════════════════════════════════════════════════

class CustomerVehicle(customer_db.Model):
    """Master record for customer vehicles (2W, 4W, EV, Commercial)."""
    __tablename__ = 'customer_vehicles'

    id                  = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    uuid                = customer_db.Column(customer_db.String(36), unique=True, nullable=False, index=True)
    company_id          = customer_db.Column(customer_db.String(50), nullable=False, index=True)
    client_id           = customer_db.Column(customer_db.Integer, nullable=True, index=True)
    registration_no     = customer_db.Column(customer_db.String(30), nullable=False, index=True)
    vehicle_type        = customer_db.Column(customer_db.String(30), nullable=False, default="Four-Wheeler")
    brand               = customer_db.Column(customer_db.String(100), nullable=False)
    model               = customer_db.Column(customer_db.String(100), nullable=False)
    variant             = customer_db.Column(customer_db.String(100), nullable=True)
    manufacturing_year  = customer_db.Column(customer_db.Integer, nullable=True)
    fuel_type           = customer_db.Column(customer_db.String(30), nullable=True, default="Petrol")
    colour              = customer_db.Column(customer_db.String(50), nullable=True)
    vin_chassis_no      = customer_db.Column(customer_db.String(60), nullable=True)
    engine_no           = customer_db.Column(customer_db.String(60), nullable=True)
    odometer_reading    = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    purchase_date       = customer_db.Column(customer_db.Date, nullable=True)
    insurance_expiry    = customer_db.Column(customer_db.Date, nullable=True)
    pollution_expiry    = customer_db.Column(customer_db.Date, nullable=True)
    warranty_expiry     = customer_db.Column(customer_db.Date, nullable=True)
    status              = customer_db.Column(customer_db.String(30), nullable=False, default="Active")
    notes               = customer_db.Column(customer_db.Text, nullable=True)
    created_at          = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at          = customer_db.Column(customer_db.DateTime, nullable=True, onupdate=datetime.utcnow)

    @property
    def client_obj(self):
        from sqlalchemy.orm import object_session
        sess = object_session(self)
        if sess and self.client_id:
            return sess.query(Client).filter_by(id=self.client_id).first()
        return None

    def to_dict(self):
        client = self.client_obj
        return {
            'id': self.id,
            'uuid': self.uuid,
            'company_id': self.company_id,
            'client_id': self.client_id,
            'client_name': client.name if client else 'Direct Customer',
            'client_phone': client.phone if client else '',
            'client_email': client.email if client else '',
            'registration_no': self.registration_no,
            'vehicle_type': self.vehicle_type,
            'brand': self.brand,
            'model': self.model,
            'variant': self.variant or '',
            'manufacturing_year': self.manufacturing_year,
            'fuel_type': self.fuel_type or 'Petrol',
            'colour': self.colour or '',
            'vin_chassis_no': self.vin_chassis_no or '',
            'engine_no': self.engine_no or '',
            'odometer_reading': self.odometer_reading or 0.0,
            'purchase_date': self.purchase_date.strftime('%Y-%m-%d') if self.purchase_date else None,
            'insurance_expiry': self.insurance_expiry.strftime('%Y-%m-%d') if self.insurance_expiry else None,
            'pollution_expiry': self.pollution_expiry.strftime('%Y-%m-%d') if self.pollution_expiry else None,
            'warranty_expiry': self.warranty_expiry.strftime('%Y-%m-%d') if self.warranty_expiry else None,
            'status': self.status,
            'notes': self.notes or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


class WorkshopJobCard(customer_db.Model):
    """Central Digital Job Card for vehicle repair and service."""
    __tablename__ = 'workshop_job_cards'

    id                      = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    job_card_no             = customer_db.Column(customer_db.String(40), unique=True, nullable=False, index=True)
    company_id              = customer_db.Column(customer_db.String(50), nullable=False, index=True)
    branch_id               = customer_db.Column(customer_db.String(50), nullable=True)
    vehicle_id              = customer_db.Column(customer_db.Integer, nullable=False, index=True)
    client_id               = customer_db.Column(customer_db.Integer, nullable=True, index=True)
    service_advisor         = customer_db.Column(customer_db.String(100), nullable=True)
    assigned_technician     = customer_db.Column(customer_db.String(100), nullable=True)
    bay_name                = customer_db.Column(customer_db.String(50), nullable=True)
    job_type                = customer_db.Column(customer_db.String(50), nullable=False, default="General Service")
    customer_complaints     = customer_db.Column(customer_db.Text, nullable=True)
    initial_inspection_notes= customer_db.Column(customer_db.Text, nullable=True)
    fuel_level              = customer_db.Column(customer_db.String(30), nullable=True, default="50%")
    current_odometer        = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    estimated_delivery_date = customer_db.Column(customer_db.DateTime, nullable=True)
    priority                = customer_db.Column(customer_db.String(20), nullable=False, default="Normal")
    status                  = customer_db.Column(customer_db.String(50), nullable=False, default="Checked In")
    two_wheeler_details     = customer_db.Column(customer_db.Text, nullable=True)  # JSON
    four_wheeler_details    = customer_db.Column(customer_db.Text, nullable=True) # JSON
    total_parts_amount      = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    total_labour_amount     = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    tax_amount              = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    grand_total             = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    invoice_id              = customer_db.Column(customer_db.Integer, nullable=True)
    created_by              = customer_db.Column(customer_db.String(100), nullable=True)
    created_at              = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at              = customer_db.Column(customer_db.DateTime, nullable=True, onupdate=datetime.utcnow)

    @property
    def vehicle_obj(self):
        from sqlalchemy.orm import object_session
        sess = object_session(self)
        if sess and self.vehicle_id:
            return sess.query(CustomerVehicle).filter_by(id=self.vehicle_id).first()
        return None

    @property
    def client_obj(self):
        from sqlalchemy.orm import object_session
        sess = object_session(self)
        if sess and self.client_id:
            return sess.query(Client).filter_by(id=self.client_id).first()
        return None

    def to_dict(self):
        veh = self.vehicle_obj
        cli = self.client_obj
        return {
            'id': self.id,
            'job_card_no': self.job_card_no,
            'company_id': self.company_id,
            'branch_id': self.branch_id or '',
            'vehicle_id': self.vehicle_id,
            'client_id': self.client_id,
            'vehicle_reg': veh.registration_no if veh else 'Unknown',
            'vehicle_model': f"{veh.brand} {veh.model}" if veh else '',
            'vehicle_type': veh.vehicle_type if veh else '',
            'vehicle_uuid': veh.uuid if veh else '',
            'client_name': cli.name if cli else (veh.client_obj.name if (veh and veh.client_obj) else 'Walk-in Customer'),
            'client_phone': cli.phone if cli else (veh.client_obj.phone if (veh and veh.client_obj) else ''),
            'service_advisor': self.service_advisor or '',
            'assigned_technician': self.assigned_technician or 'Unassigned',
            'bay_name': self.bay_name or 'General Bay',
            'job_type': self.job_type,
            'customer_complaints': self.customer_complaints or '',
            'initial_inspection_notes': self.initial_inspection_notes or '',
            'fuel_level': self.fuel_level or '50%',
            'current_odometer': self.current_odometer or 0.0,
            'estimated_delivery_date': self.estimated_delivery_date.strftime('%Y-%m-%d %H:%M') if self.estimated_delivery_date else None,
            'priority': self.priority or 'Normal',
            'status': self.status,
            'total_parts_amount': self.total_parts_amount or 0.0,
            'total_labour_amount': self.total_labour_amount or 0.0,
            'tax_amount': self.tax_amount or 0.0,
            'grand_total': self.grand_total or 0.0,
            'invoice_id': self.invoice_id,
            'created_by': self.created_by or 'Staff',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


class WorkshopInspection(customer_db.Model):
    """Inspection checklist report per Job Card."""
    __tablename__ = 'workshop_inspections'

    id                  = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    job_card_id         = customer_db.Column(customer_db.Integer, nullable=False, index=True)
    vehicle_id          = customer_db.Column(customer_db.Integer, nullable=False, index=True)
    inspector_name      = customer_db.Column(customer_db.String(100), nullable=True)
    overall_condition   = customer_db.Column(customer_db.String(30), default="Good")
    checklist_json      = customer_db.Column(customer_db.Text, nullable=True)
    notes               = customer_db.Column(customer_db.Text, nullable=True)
    created_at          = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        import json
        items = []
        if self.checklist_json:
            try:
                items = json.loads(self.checklist_json)
            except Exception:
                items = []
        return {
            'id': self.id,
            'job_card_id': self.job_card_id,
            'vehicle_id': self.vehicle_id,
            'inspector_name': self.inspector_name or '',
            'overall_condition': self.overall_condition or 'Good',
            'items': items,
            'notes': self.notes or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
        }


class WorkshopEstimate(customer_db.Model):
    """Repair estimate for customer sign-off before work begins."""
    __tablename__ = 'workshop_estimates'

    id              = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    estimate_no     = customer_db.Column(customer_db.String(40), unique=True, nullable=False, index=True)
    job_card_id     = customer_db.Column(customer_db.Integer, nullable=False, index=True)
    company_id      = customer_db.Column(customer_db.String(50), nullable=False)
    subtotal        = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    tax_amount      = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    grand_total     = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    status          = customer_db.Column(customer_db.String(30), nullable=False, default="Draft")
    approval_mode   = customer_db.Column(customer_db.String(50), nullable=True)
    approved_by     = customer_db.Column(customer_db.String(100), nullable=True)
    approved_at     = customer_db.Column(customer_db.DateTime, nullable=True)
    notes           = customer_db.Column(customer_db.Text, nullable=True)
    created_at      = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)

    items = customer_db.relationship("WorkshopEstimateItem", backref="estimate", cascade="all, delete-orphan")

    def to_dict(self):
        from sqlalchemy.orm import object_session
        sess = object_session(self)
        items_list = []
        if self.items:
            items_list = [it.to_dict() for it in self.items]
        elif sess and self.id:
            db_items = sess.query(WorkshopEstimateItem).filter_by(estimate_id=self.id).all()
            items_list = [it.to_dict() for it in db_items]

        return {
            'id': self.id,
            'estimate_no': self.estimate_no,
            'job_card_id': self.job_card_id,
            'company_id': self.company_id,
            'subtotal': self.subtotal or 0.0,
            'tax_amount': self.tax_amount or 0.0,
            'grand_total': self.grand_total or 0.0,
            'status': self.status,
            'approval_mode': self.approval_mode or '',
            'approved_by': self.approved_by or '',
            'approved_at': self.approved_at.strftime('%Y-%m-%d %H:%M:%S') if self.approved_at else None,
            'notes': self.notes or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'items': items_list
        }


class WorkshopEstimateItem(customer_db.Model):
    """Line items within a repair estimate."""
    __tablename__ = 'workshop_estimate_items'

    id                  = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    estimate_id         = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('workshop_estimates.id'), nullable=False)
    item_type           = customer_db.Column(customer_db.String(30), nullable=False, default="Part")
    brand               = customer_db.Column(customer_db.String(100), nullable=True)
    stock_item_id       = customer_db.Column(customer_db.Integer, nullable=True)
    description         = customer_db.Column(customer_db.String(255), nullable=False)
    quantity            = customer_db.Column(customer_db.Float, nullable=False, default=1.0)
    rate                = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    discount_percent    = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    gst_percent         = customer_db.Column(customer_db.Float, nullable=False, default=18.0)
    total_amount        = customer_db.Column(customer_db.Float, nullable=False, default=0.0)

    def to_dict(self):
        return {
            'id': self.id,
            'estimate_id': self.estimate_id,
            'item_type': self.item_type,
            'brand': self.brand or '',
            'stock_item_id': self.stock_item_id,
            'description': self.description,
            'quantity': self.quantity,
            'rate': self.rate,
            'discount_percent': self.discount_percent,
            'gst_percent': self.gst_percent,
            'total_amount': self.total_amount
        }


class WorkshopServiceCatalog(customer_db.Model):
    """Reusable, user-defined service packages: name, price, and what's included. Editable anytime."""
    __tablename__ = 'workshop_service_catalog'

    id           = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    company_id   = customer_db.Column(customer_db.String(20), nullable=False, index=True)
    name         = customer_db.Column(customer_db.String(150), nullable=False)
    amount       = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    inclusions   = customer_db.Column(customer_db.Text, nullable=True)   # what this service covers
    gst_percent  = customer_db.Column(customer_db.Float, nullable=False, default=18.0)
    is_active    = customer_db.Column(customer_db.Boolean, nullable=False, default=True)
    created_at   = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at   = customer_db.Column(customer_db.DateTime, nullable=True, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'amount': self.amount,
            'inclusions': self.inclusions or '', 'gst_percent': self.gst_percent,
            'is_active': self.is_active
        }


class WorkshopTask(customer_db.Model):
    """Actionable repair task within a Job Card assigned to mechanics."""
    __tablename__ = 'workshop_tasks'

    id                  = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    job_card_id         = customer_db.Column(customer_db.Integer, nullable=False, index=True)
    task_name           = customer_db.Column(customer_db.String(200), nullable=False)
    assigned_technician = customer_db.Column(customer_db.String(100), nullable=True)
    status              = customer_db.Column(customer_db.String(30), default="Pending")
    start_time          = customer_db.Column(customer_db.DateTime, nullable=True)
    end_time            = customer_db.Column(customer_db.DateTime, nullable=True)
    notes               = customer_db.Column(customer_db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'job_card_id': self.job_card_id,
            'task_name': self.task_name,
            'assigned_technician': self.assigned_technician or 'Unassigned',
            'status': self.status,
            'start_time': self.start_time.strftime('%Y-%m-%d %H:%M') if self.start_time else None,
            'end_time': self.end_time.strftime('%Y-%m-%d %H:%M') if self.end_time else None,
            'notes': self.notes or ''
        }


class WorkshopPartIssue(customer_db.Model):
    """Tracks parts requested, issued, and consumed from inventory."""
    __tablename__ = 'workshop_part_issues'

    id                  = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    job_card_id         = customer_db.Column(customer_db.Integer, nullable=False, index=True)
    stock_item_id       = customer_db.Column(customer_db.Integer, nullable=True)
    item_type           = customer_db.Column(customer_db.String(30), nullable=False, default="Part")
    brand               = customer_db.Column(customer_db.String(100), nullable=True)
    part_name           = customer_db.Column(customer_db.String(200), nullable=False)
    quantity_requested  = customer_db.Column(customer_db.Float, nullable=False, default=1.0)
    quantity_issued     = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    quantity_consumed   = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    quantity_returned   = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    unit_cost           = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    technician          = customer_db.Column(customer_db.String(100), nullable=True)
    issued_by           = customer_db.Column(customer_db.String(100), nullable=True)
    status              = customer_db.Column(customer_db.String(30), default="Requested")
    created_at          = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'job_card_id': self.job_card_id,
            'stock_item_id': self.stock_item_id,
            'item_type': self.item_type or 'Part',
            'brand': self.brand or '',
            'part_name': self.part_name,
            'quantity_requested': self.quantity_requested,
            'quantity_issued': self.quantity_issued,
            'quantity_consumed': self.quantity_consumed,
            'quantity_returned': self.quantity_returned,
            'unit_cost': self.unit_cost,
            'technician': self.technician or '',
            'issued_by': self.issued_by or '',
            'status': self.status,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }


class WorkshopQualityCheck(customer_db.Model):
    """Quality control supervisor verification."""
    __tablename__ = 'workshop_quality_checks'

    id                  = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    job_card_id         = customer_db.Column(customer_db.Integer, nullable=False, index=True)
    inspector           = customer_db.Column(customer_db.String(100), nullable=True)
    status              = customer_db.Column(customer_db.String(30), default="Pending")
    checklist_json      = customer_db.Column(customer_db.Text, nullable=True)
    rework_notes        = customer_db.Column(customer_db.Text, nullable=True)
    verified_at         = customer_db.Column(customer_db.DateTime, nullable=True)

    def to_dict(self):
        import json
        items = []
        if self.checklist_json:
            try:
                items = json.loads(self.checklist_json)
            except Exception:
                items = []
        return {
            'id': self.id,
            'job_card_id': self.job_card_id,
            'inspector': self.inspector or '',
            'status': self.status,
            'items': items,
            'rework_notes': self.rework_notes or '',
            'verified_at': self.verified_at.strftime('%Y-%m-%d %H:%M:%S') if self.verified_at else None
        }


class VehicleServiceHistory(customer_db.Model):
    """Permanent lifecycle ledger for a vehicle across all visits."""
    __tablename__ = 'vehicle_service_history'

    id                          = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    vehicle_id                  = customer_db.Column(customer_db.Integer, nullable=False, index=True)
    job_card_id                 = customer_db.Column(customer_db.Integer, nullable=True)
    service_date                = customer_db.Column(customer_db.Date, nullable=False, default=date.today)
    odometer                    = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    services_performed          = customer_db.Column(customer_db.Text, nullable=True)
    parts_replaced              = customer_db.Column(customer_db.Text, nullable=True)
    technician                  = customer_db.Column(customer_db.String(100), nullable=True)
    invoice_amount              = customer_db.Column(customer_db.Float, nullable=False, default=0.0)
    next_service_due_date       = customer_db.Column(customer_db.Date, nullable=True)
    next_service_due_odometer   = customer_db.Column(customer_db.Float, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'vehicle_id': self.vehicle_id,
            'job_card_id': self.job_card_id,
            'service_date': self.service_date.strftime('%Y-%m-%d') if self.service_date else None,
            'odometer': self.odometer,
            'services_performed': self.services_performed or '',
            'parts_replaced': self.parts_replaced or '',
            'technician': self.technician or '',
            'invoice_amount': self.invoice_amount,
            'next_service_due_date': self.next_service_due_date.strftime('%Y-%m-%d') if self.next_service_due_date else None,
            'next_service_due_odometer': self.next_service_due_odometer
        }


class WorkshopVehicleServicePlan(customer_db.Model):
    """Customer-selected recurring service interval for one vehicle."""
    __tablename__ = 'workshop_vehicle_service_plans'

    id              = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    company_id      = customer_db.Column(customer_db.String(50), nullable=False, index=True)
    vehicle_id      = customer_db.Column(customer_db.Integer, nullable=False, unique=True, index=True)
    interval_days   = customer_db.Column(customer_db.Integer, nullable=False, default=180)
    interval_km     = customer_db.Column(customer_db.Float, nullable=False, default=10000.0)
    updated_at      = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'vehicle_id': self.vehicle_id,
            'interval_days': self.interval_days or 180,
            'interval_km': self.interval_km or 10000.0,
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S') if self.updated_at else None,
        }


class ServiceReminder(customer_db.Model):
    """Automated service, insurance, and warranty reminders for customers."""
    __tablename__ = 'service_reminders'

    id                  = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    company_id          = customer_db.Column(customer_db.String(50), nullable=False, index=True)
    vehicle_id          = customer_db.Column(customer_db.Integer, nullable=False, index=True)
    client_id           = customer_db.Column(customer_db.Integer, nullable=True)
    reminder_type       = customer_db.Column(customer_db.String(50), default="Next Periodic Service")
    due_date            = customer_db.Column(customer_db.Date, nullable=False)
    due_odometer        = customer_db.Column(customer_db.Float, nullable=True)
    status              = customer_db.Column(customer_db.String(20), default="Pending")
    notes               = customer_db.Column(customer_db.Text, nullable=True)
    created_at          = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        from sqlalchemy.orm import object_session
        sess = object_session(self)
        veh = sess.query(CustomerVehicle).filter_by(id=self.vehicle_id).first() if (sess and self.vehicle_id) else None
        cli = sess.query(Client).filter_by(id=self.client_id).first() if (sess and self.client_id) else None
        return {
            'id': self.id,
            'company_id': self.company_id,
            'vehicle_id': self.vehicle_id,
            'client_id': self.client_id,
            'registration_no': veh.registration_no if veh else '',
            'vehicle_model': f"{veh.brand} {veh.model}" if veh else '',
            'client_name': cli.name if cli else '',
            'client_phone': cli.phone if cli else '',
            'reminder_type': self.reminder_type,
            'due_date': self.due_date.strftime('%Y-%m-%d') if self.due_date else None,
            'due_odometer': self.due_odometer,
            'status': self.status,
            'notes': self.notes or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None
        }

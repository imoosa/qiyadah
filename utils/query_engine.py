"""
query_engine.py  (Qiyadah ERP version)
──────────────────────────────────────────────────────────
Every function takes `company_id` and gets its session via
db_router.get_customer_session(company_id) — the same cached,
per-company session app.py's own routes use (get_cdb()).

We do NOT close the session at the end of each function. app.py's
teardown_request already owns that session's lifecycle (rollback on
error); closing it here would fight that and could poison the session
for whatever route/request touches this company next. If you call this
from a route, just use get_cdb() / get_customer_session(company_id) the
same way the rest of app.py does.

Isolation note: customer_models.py has no Flask-SQLAlchemy `.query`
shortcut — the only way to reach data at all is through the session
requested here, which is physically bound to qiy_<company_id>'s own
MySQL database. company_id filters below are belt-and-suspenders on
top of that, matching the existing column-per-table convention.
"""

import json
from datetime import timedelta, date
from typing import Dict, Any, Optional, List
from sqlalchemy import func, or_

from db_router import get_customer_session
from customer_models import (
    Client, Supplier, Invoice, InvoiceItem, PurchaseInvoice, StockItem,
    CashTransaction, BankAccount, BankTransaction, Loan, Cheque,
    Expense, Estimate, CustomerInvoice,
    CustomerInvoiceItem, PurchaseInvoiceItem, CompanyUser,
)


# ─────────────────────────────────────────────────────────────────────────
# Live outstanding / payable calculation helpers
# ─────────────────────────────────────────────────────────────────────────

def _compute_client_live_outstanding(cdb, company_id: str, client) -> float:
    """
    Live outstanding for a single client: opening_balance + invoices since cutoff - receipts since cutoff.
    Matches app.py _compute_outstanding_for_clients and the Clients page.
    """
    cutoff_date = client.statement_cutoff.date() if client.statement_cutoff else None
    c_norm = (client.name or "").strip().lower()
    
    ci_q = cdb.query(func.sum(CustomerInvoice.grand_total)).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.client_id == client.id,
        CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft']),
    )
    if cutoff_date:
        ci_q = ci_q.filter(CustomerInvoice.invoice_date >= cutoff_date)
    ci_invoiced = float(ci_q.scalar() or 0)

    inv_q = cdb.query(func.sum(Invoice.grand_total)).filter(
        Invoice.company_id == company_id,
        Invoice.client_id == client.id,
        Invoice.status.notin_(['Cancelled', 'Void', 'Draft']),
    )
    if cutoff_date:
        inv_q = inv_q.filter(Invoice.date >= cutoff_date)
    legacy_invoiced = float(inv_q.scalar() or 0)
    
    total_invoiced = ci_invoiced if ci_invoiced > 0 else legacy_invoiced

    cash_q = cdb.query(func.sum(CashTransaction.amount)).filter(
        CashTransaction.company_id == company_id,
        func.lower(func.trim(CashTransaction.party_name)) == c_norm,
        CashTransaction.category.in_(["Receipt", "Adjustment"]),
        or_(CashTransaction.reference != "WRITE-OFF", CashTransaction.reference.is_(None)),
    )
    if cutoff_date:
        cash_q = cash_q.filter(CashTransaction.date >= cutoff_date)
    cash_received = float(cash_q.scalar() or 0)

    bank_q = cdb.query(func.sum(BankTransaction.amount)).filter(
        BankTransaction.company_id == company_id,
        func.lower(func.trim(BankTransaction.party_name)) == c_norm,
        BankTransaction.type == "credit",
    )
    if cutoff_date:
        bank_q = bank_q.filter(BankTransaction.date >= cutoff_date)
    bank_received = float(bank_q.scalar() or 0)

    return round((client.opening_balance or 0) + total_invoiced - cash_received - bank_received, 2)


def _compute_outstanding_for_all_clients(cdb, company_id: str, client_rows=None) -> Dict[int, float]:
    """Computes live outstanding for all clients in batch, exactly matching app.py _compute_outstanding_for_clients."""
    if client_rows is None:
        client_rows = cdb.query(Client).filter(
            Client.company_id == company_id,
            Client.status != "Deleted",
            ~Client.client_type.in_(["Supplier", "Cash-Only"]),
        ).all()
    
    client_ids = [c.id for c in client_rows]
    ci_invoiced_by_client = dict(
        cdb.query(CustomerInvoice.client_id, func.sum(CustomerInvoice.grand_total))
           .filter(CustomerInvoice.company_id == company_id, CustomerInvoice.client_id.in_(client_ids),
                   CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft']))
           .group_by(CustomerInvoice.client_id).all()
    ) if client_ids else {}

    invoiced_by_client = dict(
        cdb.query(Invoice.client_id, func.sum(Invoice.grand_total))
           .filter(Invoice.company_id == company_id, Invoice.client_id.in_(client_ids),
                   Invoice.status.notin_(['Cancelled', 'Void', 'Draft']))
           .group_by(Invoice.client_id).all()
    ) if client_ids else {}

    cash_by_norm_name = {}
    for name, amt in cdb.query(CashTransaction.party_name, func.sum(CashTransaction.amount))\
                       .filter(CashTransaction.company_id == company_id,
                               CashTransaction.category.in_(["Receipt", "Adjustment"]),
                               or_(CashTransaction.reference != "WRITE-OFF", CashTransaction.reference.is_(None)))\
                       .group_by(CashTransaction.party_name).all():
        if name:
            k = name.strip().lower()
            cash_by_norm_name[k] = cash_by_norm_name.get(k, 0.0) + float(amt or 0)

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
            ci_invoiced = float(
                cdb.query(func.sum(CustomerInvoice.grand_total))
                   .filter(CustomerInvoice.company_id == company_id, CustomerInvoice.client_id == c.id,
                           CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft']),
                           CustomerInvoice.invoice_date >= cutoff_date).scalar() or 0
            )
            legacy_invoiced = float(
                cdb.query(func.sum(Invoice.grand_total))
                   .filter(Invoice.company_id == company_id, Invoice.client_id == c.id,
                           Invoice.status.notin_(['Cancelled', 'Void', 'Draft']),
                           Invoice.date >= cutoff_date).scalar() or 0
            )
            total_invoiced = ci_invoiced if ci_invoiced > 0 else legacy_invoiced
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
            total_invoiced = float(ci_invoiced_by_client.get(c.id, 0) or invoiced_by_client.get(c.id, 0) or 0)
            cash_received = float(cash_by_norm_name.get(c_norm, 0.0))
            bank_received = float(bank_by_norm_name.get(c_norm, 0.0))

        result[c.id] = round((c.opening_balance or 0) + total_invoiced - cash_received - bank_received, 2)
    return result


def _compute_supplier_live_payable(cdb, company_id: str, supplier) -> float:
    """Live payable for a single supplier: opening_balance + purchase invoices since cutoff - payments since cutoff."""
    cutoff_date = supplier.statement_cutoff.date() if supplier.statement_cutoff else None
    inv_q = cdb.query(func.sum(PurchaseInvoice.grand_total)).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.supplier_id == supplier.id,
        PurchaseInvoice.status.notin_(['Cancelled', 'Void']),
    )
    if cutoff_date:
        inv_q = inv_q.filter(PurchaseInvoice.date >= cutoff_date)
    total_invoiced = float(inv_q.scalar() or 0)

    cash_q = cdb.query(func.sum(CashTransaction.amount)).filter(
        CashTransaction.company_id == company_id,
        func.lower(CashTransaction.party_name) == func.lower(supplier.name),
        CashTransaction.category == "Payment",
    )
    if cutoff_date:
        cash_q = cash_q.filter(CashTransaction.date >= cutoff_date)
    cash_paid = float(cash_q.scalar() or 0)

    bank_q = cdb.query(func.sum(BankTransaction.amount)).filter(
        BankTransaction.company_id == company_id,
        func.lower(BankTransaction.party_name) == func.lower(supplier.name),
        BankTransaction.type == "debit",
    )
    if cutoff_date:
        bank_q = bank_q.filter(BankTransaction.date >= cutoff_date)
    bank_paid = float(bank_q.scalar() or 0)

    return round((supplier.opening_balance or 0) + total_invoiced - cash_paid - bank_paid, 2)


def _compute_payable_for_all_suppliers(cdb, company_id: str, supplier_rows=None) -> Dict[int, float]:
    """Computes live payable for all suppliers in batch, matching app.py _creditor_summary."""
    if supplier_rows is None:
        supplier_rows = cdb.query(Supplier).filter(
            Supplier.company_id == company_id,
            Supplier.status != "Deleted",
        ).all()
    
    supplier_ids = [s.id for s in supplier_rows]
    invoiced_by_supplier = dict(
        cdb.query(PurchaseInvoice.supplier_id, func.sum(PurchaseInvoice.grand_total))
           .filter(PurchaseInvoice.company_id == company_id, PurchaseInvoice.supplier_id.in_(supplier_ids),
                   PurchaseInvoice.status.notin_(['Cancelled', 'Void']))
           .group_by(PurchaseInvoice.supplier_id).all()
    ) if supplier_ids else {}
    cash_by_name = dict(
        cdb.query(CashTransaction.party_name, func.sum(CashTransaction.amount))
           .filter(CashTransaction.company_id == company_id,
                   CashTransaction.category == "Payment")
           .group_by(CashTransaction.party_name).all()
    )
    bank_by_name = dict(
        cdb.query(BankTransaction.party_name, func.sum(BankTransaction.amount))
           .filter(BankTransaction.company_id == company_id, BankTransaction.type == "debit")
           .group_by(BankTransaction.party_name).all()
    )

    result = {}
    for s in supplier_rows:
        cutoff_date = s.statement_cutoff.date() if s.statement_cutoff else None
        if cutoff_date:
            total_invoiced = float(
                cdb.query(func.sum(PurchaseInvoice.grand_total))
                   .filter(PurchaseInvoice.company_id == company_id, PurchaseInvoice.supplier_id == s.id,
                           PurchaseInvoice.status.notin_(['Cancelled', 'Void']),
                           PurchaseInvoice.date >= cutoff_date).scalar() or 0
            )
            cash_paid = float(
                cdb.query(func.sum(CashTransaction.amount))
                   .filter(CashTransaction.company_id == company_id, CashTransaction.party_name == s.name,
                           CashTransaction.category == "Payment",
                           CashTransaction.date >= cutoff_date).scalar() or 0
            )
            bank_paid = float(
                cdb.query(func.sum(BankTransaction.amount))
                   .filter(BankTransaction.company_id == company_id, BankTransaction.party_name == s.name,
                           BankTransaction.type == "debit",
                           BankTransaction.date >= cutoff_date).scalar() or 0
            )
        else:
            total_invoiced = float(invoiced_by_supplier.get(s.id, 0) or 0)
            cash_paid = 0
            for k, v in cash_by_name.items():
                if k and k.lower() == s.name.lower():
                    cash_paid = float(v or 0)
                    break
            bank_paid = float(bank_by_name.get(s.name, 0) or 0)

        result[s.id] = round((s.opening_balance or 0) + total_invoiced - cash_paid - bank_paid, 2)
    return result


# ─────────────────────────────────────────────────────────────────────────
# Dashboard / overview
# ─────────────────────────────────────────────────────────────────────────

def get_dashboard_summary(company_id: str) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)

    total_clients = cdb.query(Client).filter_by(company_id=company_id).count()
    total_suppliers = cdb.query(Supplier).filter_by(company_id=company_id).count()

    pending_invoices = (
        cdb.query(CustomerInvoice)
        .filter(CustomerInvoice.company_id == company_id, CustomerInvoice.status != "Paid", CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft']))
        .count()
    )
    # Live total receivables across all active clients (matches dashboard & Clients page)
    client_live_map = _compute_outstanding_for_all_clients(cdb, company_id)
    total_receivable = sum(v for v in client_live_map.values() if v > 0)

    # Live total payables across all active suppliers (matches dashboard & Suppliers page)
    supplier_live_map = _compute_payable_for_all_suppliers(cdb, company_id)
    total_payable = sum(v for v in supplier_live_map.values() if v > 0)

    cash_balance = _cash_balance(cdb, company_id)
    bank_balance = (
        cdb.query(func.sum(BankAccount.balance))
        .filter(BankAccount.company_id == company_id, BankAccount.status == "Active")
        .scalar() or 0.0
    )

    this_month_start = date.today().replace(day=1)
    month_sales = (
        cdb.query(func.sum(CustomerInvoice.grand_total))
        .filter(CustomerInvoice.company_id == company_id, CustomerInvoice.invoice_date >= this_month_start, CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft']))
        .scalar() or 0.0
    )

    return {
        "intent": "dashboard_summary",
        "total_clients": total_clients,
        "total_suppliers": total_suppliers,
        "pending_invoices": pending_invoices,
        "total_receivable": round(total_receivable, 2),
        "total_payable": round(total_payable, 2),
        "cash_balance": round(cash_balance, 2),
        "bank_balance": round(bank_balance, 2),
        "this_month_sales": round(month_sales, 2),
    }



# ─────────────────────────────────────────────────────────────────────────
# Clients
# ─────────────────────────────────────────────────────────────────────────

def get_client_detail(company_id: str, identifier: str) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)
    ident = f"%{identifier.strip()}%"
    client = (
        cdb.query(Client)
        .filter(
            Client.company_id == company_id,
            (Client.name.ilike(ident)) |
            (Client.client_id.ilike(ident)) |
            (Client.phone.ilike(ident)),
        )
        .first()
    )
    if not client:
        return {"intent": "client_detail", "found": False, "query": identifier}

    live_outstanding = _compute_client_live_outstanding(cdb, company_id, client)

    return {
        "intent": "client_detail",
        "found": True,
        "name": client.name,
        "client_id": client.client_id,
        "client_type": client.client_type,
        "phone": client.phone,
        "email": client.email,
        "city": client.city,
        "state": client.state,
        "gst_number": client.gst_number,
        "gst_type": client.gst_type,
        "credit_limit": client.credit_limit,
        "credit_days": client.credit_days,
        "pending_amount": live_outstanding,
        "status": client.status,
    }


def get_all_clients_summary(company_id: str) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)
    clients = cdb.query(Client).filter_by(company_id=company_id).all()
    live_map = _compute_outstanding_for_all_clients(cdb, company_id, clients)
    total_pending = sum(v for v in live_map.values() if v > 0)
    active = sum(1 for c in clients if (c.status or "").lower() == "active")
    top_pending_list = []
    for c in clients:
        bal = live_map.get(c.id, 0.0)
        if bal > 0:
            top_pending_list.append({"name": c.name, "pending": bal})
    top_pending_list.sort(key=lambda x: x["pending"], reverse=True)

    return {
        "intent": "all_clients_summary",
        "total_clients": len(clients),
        "active_clients": active,
        "total_pending_receivable": round(total_pending, 2),
        "top_pending": top_pending_list[:10],
    }


# ─────────────────────────────────────────────────────────────────────────
# Suppliers
# ─────────────────────────────────────────────────────────────────────────

def get_supplier_detail(company_id: str, identifier: str) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)
    ident = f"%{identifier.strip()}%"
    supplier = (
        cdb.query(Supplier)
        .filter(
            Supplier.company_id == company_id,
            (Supplier.name.ilike(ident)) |
            (Supplier.supplier_id.ilike(ident)) |
            (Supplier.phone.ilike(ident)),
        )
        .first()
    )
    if not supplier:
        return {"intent": "supplier_detail", "found": False, "query": identifier}

    live_payable = _compute_supplier_live_payable(cdb, company_id, supplier)

    return {
        "intent": "supplier_detail",
        "found": True,
        "name": supplier.name,
        "supplier_id": supplier.supplier_id,
        "supplier_type": supplier.supplier_type,
        "phone": supplier.phone,
        "email": supplier.email,
        "gst_number": supplier.gst_number,
        "gst_type": supplier.gst_type,
        "credit_limit": supplier.credit_limit,
        "payable_amount": live_payable,
        "status": supplier.status,
        "brands": [b.brand_name for b in supplier.brands],
    }


def get_all_suppliers_summary(company_id: str) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)
    suppliers = cdb.query(Supplier).filter_by(company_id=company_id).all()
    live_map = _compute_payable_for_all_suppliers(cdb, company_id, suppliers)
    total_payable = sum(v for v in live_map.values() if v > 0)
    top_payable_list = []
    for s in suppliers:
        bal = live_map.get(s.id, 0.0)
        if bal > 0:
            top_payable_list.append({"name": s.name, "payable": bal})
    top_payable_list.sort(key=lambda x: x["payable"], reverse=True)

    return {
        "intent": "all_suppliers_summary",
        "total_suppliers": len(suppliers),
        "total_payable": round(total_payable, 2),
        "top_payable": top_payable_list[:10],
    }


# ─────────────────────────────────────────────────────────────────────────
# Sales invoices
# ─────────────────────────────────────────────────────────────────────────

def get_invoice_detail(company_id: str, invoice_identifier: str) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)
    ident = f"%{invoice_identifier.strip()}%"
    inv = (
        cdb.query(CustomerInvoice)
        .filter(CustomerInvoice.company_id == company_id, CustomerInvoice.invoice_number.ilike(ident))
        .first()
    )
    if not inv:
        return {"intent": "invoice_detail", "found": False, "query": invoice_identifier}

    client = cdb.query(Client).filter_by(id=inv.client_id).first()
    return {
        "intent": "invoice_detail",
        "found": True,
        "invoice_id": inv.invoice_number,
        "client": client.name if client else "Unknown",
        "date": inv.invoice_date.strftime("%d %b %Y"),
        "status": inv.status,
        "subtotal": inv.subtotal,
        "tax_amount": inv.tax_amount,
        "grand_total": inv.grand_total,
        "paid_amount": inv.paid_amount,
        "balance": inv.balance,
    }



def get_sales_summary(company_id: str, start_date=None, end_date=None, months: int = None) -> Dict[str, Any]:
    """
    Total sales from Qiyadah sales invoices, excluding inactive documents.
    months=None → all-time total. months=N → last N*30 days only.
    """
    cdb = get_customer_session(company_id)
    q = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.status.notin_(['Void', 'Draft', 'Cancelled'])
    )
    period_label = "All-Time"
    if start_date and end_date:
        q = q.filter(CustomerInvoice.invoice_date >= start_date, CustomerInvoice.invoice_date <= end_date)
        period_label = f"{start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}"
    elif months:
        cutoff = date.today() - timedelta(days=30 * months)
        q = q.filter(CustomerInvoice.invoice_date >= cutoff)
        period_label = f"Last {months} Month{'s' if months > 1 else ''}"
    rows = q.all()

    total_sales = sum(inv.grand_total or 0 for inv in rows)
    total_collected = sum(inv.paid_amount or 0 for inv in rows)
    total_pending = sum(inv.balance or 0 for inv in rows)

    return {
        "intent": "sales_summary",
        "period_label": period_label,
        "period_months": months,
        "start_date": start_date.strftime('%Y-%m-%d') if start_date else None,
        "end_date": end_date.strftime('%Y-%m-%d') if end_date else None,
        "invoice_count": len(rows),
        "total_sales": round(total_sales, 2),
        "total_collected": round(total_collected, 2),
        "total_pending": round(total_pending, 2),
        "avg_invoice": round(total_sales / len(rows), 2) if rows else 0.0,
    }



def get_pending_receivables(company_id: str, limit: int = 15) -> Dict[str, Any]:
    """Total pending receivable dues from clients, computed via live customer ledger."""
    cdb = get_customer_session(company_id)
    client_rows = cdb.query(Client).filter(
        Client.company_id == company_id,
        Client.status != "Deleted",
        ~Client.client_type.in_(["Supplier", "Cash-Only"]),
    ).all()
    outstanding_map = _compute_outstanding_for_all_clients(cdb, company_id, client_rows)

    due_clients = []
    for c in client_rows:
        bal = outstanding_map.get(c.id, 0.0)
        if bal > 0:
            due_clients.append({
                "client_id": c.id,
                "client": c.name,
                "balance": round(bal, 2),
                "phone": c.phone or "",
            })
    due_clients.sort(key=lambda x: x["balance"], reverse=True)
    total = sum(d["balance"] for d in due_clients)
    return {
        "intent": "pending_receivables",
        "count": len(due_clients),
        "total_outstanding": round(total, 2),
        "items": due_clients[:limit],
    }


def get_pending_payables(company_id: str, limit: int = 15) -> Dict[str, Any]:
    """Total payable from purchases and breakdown of unpaid supplier bills."""
    cdb = get_customer_session(company_id)
    rows = (
        cdb.query(PurchaseInvoice)
        .filter(PurchaseInvoice.company_id == company_id, PurchaseInvoice.balance > 0, PurchaseInvoice.status.notin_(['Void', 'Draft', 'Cancelled']))
        .order_by(PurchaseInvoice.balance.desc())
        .limit(limit)
        .all()
    )
    total = (
        cdb.query(func.sum(PurchaseInvoice.balance))
        .filter(PurchaseInvoice.company_id == company_id, PurchaseInvoice.balance > 0, PurchaseInvoice.status.notin_(['Void', 'Draft', 'Cancelled']))
        .scalar() or 0.0
    )
    total_count = (
        cdb.query(PurchaseInvoice)
        .filter(PurchaseInvoice.company_id == company_id, PurchaseInvoice.balance > 0, PurchaseInvoice.status.notin_(['Void', 'Draft', 'Cancelled']))
        .count()
    )
    today = date.today()
    overdue_bills = (
        cdb.query(PurchaseInvoice)
        .filter(
            PurchaseInvoice.company_id == company_id,
            PurchaseInvoice.balance > 0,
            PurchaseInvoice.due_date < today,
            PurchaseInvoice.status.notin_(['Void', 'Draft', 'Cancelled'])
        )
        .all()
    )
    # Pre-fetch suppliers for these invoices
    supplier_ids = [p.supplier_id for p in rows if p.supplier_id]
    supplier_map = {}
    if supplier_ids:
        suppliers = cdb.query(Supplier).filter(Supplier.company_id == company_id, Supplier.id.in_(supplier_ids)).all()
        supplier_map = {s.id: s.name for s in suppliers}

    items = []
    for p in rows:
        sup_name = p.supplier_name
        if not sup_name and p.supplier_id in supplier_map:
            sup_name = supplier_map[p.supplier_id]
        if not sup_name and p.supplier_id:
            s_obj = cdb.query(Supplier).filter_by(id=p.supplier_id).first()
            if s_obj:
                sup_name = s_obj.name
        if not sup_name:
            first_item = cdb.query(PurchaseInvoiceItem).filter_by(purchase_invoice_id=p.id).first()
            if first_item and first_item.courier_name:
                sup_name = first_item.courier_name

        items.append({
            "invoice_id": p.invoice_id,
            "supplier": sup_name or (f"Supplier #{p.supplier_id}" if p.supplier_id else "Vendor / Co-Loader"),
            "balance": round(p.balance or 0, 2),
            "due_date": p.due_date.strftime("%d %b %Y") if p.due_date else None,
            "overdue": bool(p.due_date and p.due_date < today),
        })
    return {
        "intent": "pending_payables",
        "count": total_count,
        "total_outstanding": round(total, 2),
        "total_payable": round(total, 2),
        "overdue_count": len(overdue_bills),
        "overdue_amount": round(sum(p.balance or 0 for p in overdue_bills), 2),
        "items": items,
    }


# ─────────────────────────────────────────────────────────────────────────
# GST / Tax
# Mirrors app.py's /api/reports/tax-data endpoint exactly: same status
# exclusion on sales (Cancelled/Void), same tax_amount fields, same
# output_gst - input_gst = net_gst formula. Deliberately NOT reusing the
# HSN-level cgst/sgst/igst split from that endpoint here — that's computed
# per-invoice-item there and isn't worth duplicating for a chat summary;
# cgst/sgst below use the same output_gst/2 approximation the report route
# itself uses (it hardcodes igst to 0 too — an existing simplification in
# tax-data, not something introduced here).
# ─────────────────────────────────────────────────────────────────────────

def get_gst_summary(company_id: str, start_date=None, end_date=None, months: int = None) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)

    sales_q = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft']),
    )
    purchase_q = cdb.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.status.notin_(['Cancelled', 'Void', 'Draft']),
    )

    if start_date and end_date:
        sales_q = sales_q.filter(CustomerInvoice.invoice_date >= start_date, CustomerInvoice.invoice_date <= end_date)
        purchase_q = purchase_q.filter(PurchaseInvoice.date >= start_date, PurchaseInvoice.date <= end_date)
    elif months:
        cutoff = date.today() - timedelta(days=30 * months)
        sales_q = sales_q.filter(CustomerInvoice.invoice_date >= cutoff)
        purchase_q = purchase_q.filter(PurchaseInvoice.date >= cutoff)

    sales = sales_q.all()
    purchases = purchase_q.all()

    output_gst = sum(float(i.tax_amount or 0) for i in sales)
    input_gst = sum(float(p.tax_amount or 0) for p in purchases)
    net_gst = output_gst - input_gst

    period_lbl = f"{start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}" if start_date and end_date else (f"last {months} month(s)" if months else "All-Time")

    return {
        "intent": "gst_summary",
        "period_label": period_lbl,
        "start_date": start_date.strftime('%Y-%m-%d') if start_date else None,
        "end_date": end_date.strftime('%Y-%m-%d') if end_date else None,
        "period_months": months,
        "output_gst": round(output_gst, 2),      # GST collected on sales
        "input_gst": round(input_gst, 2),        # GST paid on purchases
        "net_gst": round(net_gst, 2),
        "net_gst_status": "payable" if net_gst > 0 else ("receivable" if net_gst < 0 else "nil"),
        "cgst": round(sum(float(i.cgst_total or 0) for i in sales), 2),
        "sgst": round(sum(float(i.sgst_total or 0) for i in sales), 2),
        "igst": round(sum(float(i.igst_total or 0) for i in sales), 2),
    }



# ─────────────────────────────────────────────────────────────────────────
# Purchase invoices
# ─────────────────────────────────────────────────────────────────────────

def get_purchase_summary(company_id: str, start_date=None, end_date=None, months: int = None) -> Dict[str, Any]:
    """
    Aggregate purchase totals from PurchaseInvoice — the purchase-side
    mirror of get_sales_summary(). months=None → all-time; months=N →
    last N*30 days only.
    """
    cdb = get_customer_session(company_id)
    q = cdb.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.status.notin_(['Void', 'Draft'])
    )
    if start_date and end_date:
        q = q.filter(PurchaseInvoice.date >= start_date, PurchaseInvoice.date <= end_date)
    elif months:
        cutoff = date.today() - timedelta(days=30 * months)
        q = q.filter(PurchaseInvoice.date >= cutoff)
    rows = q.all()

    total_purchase = sum(p.grand_total or 0 for p in rows)
    total_paid = sum(p.paid_amount or 0 for p in rows)
    total_pending = sum(p.balance or 0 for p in rows)

    return {
        "intent": "purchase_summary",
        "period_months": months,
        "start_date": start_date.strftime('%Y-%m-%d') if start_date else None,
        "end_date": end_date.strftime('%Y-%m-%d') if end_date else None,
        "invoice_count": len(rows),
        "total_purchase": round(total_purchase, 2),
        "total_paid": round(total_paid, 2),
        "total_pending": round(total_pending, 2),
    }


def get_purchase_invoice_detail(company_id: str, identifier: str) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)
    ident = f"%{identifier.strip()}%"
    p = (
        cdb.query(PurchaseInvoice)
        .filter(PurchaseInvoice.company_id == company_id, PurchaseInvoice.invoice_id.ilike(ident))
        .first()
    )
    if not p:
        return {"intent": "purchase_invoice_detail", "found": False, "query": identifier}
    sup_name = p.supplier_name
    if not sup_name and p.supplier_id:
        s_obj = cdb.query(Supplier).filter_by(id=p.supplier_id).first()
        if s_obj:
            sup_name = s_obj.name
    if not sup_name:
        first_item = cdb.query(PurchaseInvoiceItem).filter_by(purchase_invoice_id=p.id).first()
        if first_item and first_item.courier_name:
            sup_name = first_item.courier_name

    return {
        "intent": "purchase_invoice_detail",
        "found": True,
        "invoice_id": p.invoice_id,
        "supplier": sup_name or (f"Supplier #{p.supplier_id}" if p.supplier_id else "Vendor / Co-Loader"),
        "date": p.date.strftime("%d %b %Y"),
        "status": p.status,
        "grand_total": p.grand_total,
        "paid_amount": p.paid_amount,
        "balance": p.balance,
    }


# ─────────────────────────────────────────────────────────────────────────
# Cash / Bank
# CashTransaction.type is 'income' / 'expense' (matches app.py's own
# filters elsewhere, e.g. api_dashboard_data) — NOT 'in' / 'out'.
# ─────────────────────────────────────────────────────────────────────────

def _cash_balance(cdb, company_id: str) -> float:
    income_total = (
        cdb.query(func.sum(CashTransaction.amount))
        .filter(CashTransaction.company_id == company_id, CashTransaction.type == "income")
        .scalar() or 0.0
    )
    expense_total = (
        cdb.query(func.sum(CashTransaction.amount))
        .filter(CashTransaction.company_id == company_id, CashTransaction.type == "expense")
        .scalar() or 0.0
    )
    return income_total - expense_total


def get_cash_summary(company_id: str) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)
    balance = _cash_balance(cdb, company_id)
    this_month_start = date.today().replace(day=1)
    month_out = (
        cdb.query(func.sum(CashTransaction.amount))
        .filter(
            CashTransaction.company_id == company_id,
            CashTransaction.type == "expense",
            CashTransaction.date >= this_month_start,
        ).scalar() or 0.0
    )
    return {
        "intent": "cash_summary",
        "cash_balance": round(balance, 2),
        "this_month_cash_out": round(month_out, 2),
    }


def get_bank_summary(company_id: str) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)
    accounts = cdb.query(BankAccount).filter_by(company_id=company_id, status="Active").all()
    total = sum(a.balance or 0 for a in accounts)
    return {
        "intent": "bank_summary",
        "total_balance": round(total, 2),
        "accounts": [
            {"bank_name": a.bank_name,
             "account_number": a.account_number[-4:].rjust(len(a.account_number), '*'),
             "balance": a.balance} for a in accounts
        ],
    }


# ─────────────────────────────────────────────────────────────────────────
# Expenses
# ─────────────────────────────────────────────────────────────────────────

def get_expenses_summary(company_id: str, start_date=None, end_date=None, months: int = 1) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)
    q = cdb.query(Expense.category, func.sum(Expense.amount)).filter(Expense.company_id == company_id)
    if start_date and end_date:
        q = q.filter(Expense.date >= start_date, Expense.date <= end_date)
    else:
        cutoff = date.today() - timedelta(days=30 * months)
        q = q.filter(Expense.date >= cutoff)
    rows = q.group_by(Expense.category).all()
    total = sum(amt for _, amt in rows)
    return {
        "intent": "expenses_summary",
        "period_months": months,
        "start_date": start_date.strftime('%Y-%m-%d') if start_date else None,
        "end_date": end_date.strftime('%Y-%m-%d') if end_date else None,
        "total_expenses": round(total, 2),
        "by_category": {cat: round(amt, 2) for cat, amt in rows},
    }


# ─────────────────────────────────────────────────────────────────────────
# Stock
# ─────────────────────────────────────────────────────────────────────────

def get_stock_summary(company_id: str) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)
    items = cdb.query(StockItem).filter_by(company_id=company_id).all()
    low_stock = [i for i in items if i.reorder_level and i.quantity <= i.reorder_level]
    total_value = sum((i.quantity or 0) * (i.purchase_rate or 0) for i in items)
    return {
        "intent": "stock_summary",
        "total_items": len(items),
        "low_stock_count": len(low_stock),
        "low_stock_items": [{"name": i.name, "qty": i.quantity, "reorder_level": i.reorder_level} for i in low_stock[:10]],
        "total_stock_value": round(total_value, 2),
    }


def get_stock_item_detail(company_id: str, identifier: str) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)
    ident = f"%{identifier.strip()}%"
    item = (
        cdb.query(StockItem)
        .filter(StockItem.company_id == company_id,
                 (StockItem.name.ilike(ident)) | (StockItem.code.ilike(ident)))
        .first()
    )
    if not item:
        return {"intent": "stock_item_detail", "found": False, "query": identifier}
    return {
        "intent": "stock_item_detail",
        "found": True,
        "name": item.name,
        "code": item.code,
        "category": item.category,
        "quantity": item.quantity,
        "unit": item.unit,
        "purchase_rate": item.purchase_rate,
        "selling_price": item.selling_price,
        "hsn": item.hsn,
        "gst_percent": item.gst_percent,
        "reorder_level": item.reorder_level,
    }


# ─────────────────────────────────────────────────────────────────────────
# Loans & Cheques
# ─────────────────────────────────────────────────────────────────────────

def get_loans_summary(company_id: str) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)
    loans = cdb.query(Loan).filter_by(company_id=company_id, status="Active").all()
    total_outstanding = sum(l.remaining_amount for l in loans)
    return {
        "intent": "loans_summary",
        "active_loans": len(loans),
        "total_outstanding": round(total_outstanding, 2),
        "loans": [{"party_name": l.party_name, "type": l.type, "remaining": round(l.remaining_amount, 2)} for l in loans],
    }


def get_cheques_summary(company_id: str) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)
    pending = cdb.query(Cheque).filter_by(company_id=company_id, status="Pending").all()
    received = [c for c in pending if c.direction == "received"]
    issued = [c for c in pending if c.direction == "paid"]
    return {
        "intent": "cheques_summary",
        "pending_received_count": len(received),
        "pending_received_amount": round(sum(c.amount for c in received), 2),
        "pending_issued_count": len(issued),
        "pending_issued_amount": round(sum(c.amount for c in issued), 2),
    }


# ─────────────────────────────────────────────────────────────────────────
# NEW — Net / Gross profit, bookings, void/cancelled, counts, price list,
# WhatsApp status, user counts.
# ─────────────────────────────────────────────────────────────────────────

from customer_models import PriceList, CompanyUser


def get_client_count(company_id: str) -> Dict[str, Any]:
    """Thin wrapper — reuses get_all_clients_summary's data so the count
    is never computed a second, possibly-inconsistent way."""
    return get_all_clients_summary(company_id)


def get_supplier_count(company_id: str) -> Dict[str, Any]:
    return get_all_suppliers_summary(company_id)


def get_gross_profit_summary(company_id: str, start_date=None, end_date=None, months: int = None) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)

    sales_q = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft']),
    )
    purchase_q = cdb.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.status.notin_(['Cancelled', 'Void', 'Draft']),
    )

    if start_date and end_date:
        sales_q = sales_q.filter(CustomerInvoice.invoice_date >= start_date, CustomerInvoice.invoice_date <= end_date)
        purchase_q = purchase_q.filter(PurchaseInvoice.date >= start_date, PurchaseInvoice.date <= end_date)
    elif months:
        cutoff = date.today() - timedelta(days=30 * months)
        sales_q = sales_q.filter(CustomerInvoice.invoice_date >= cutoff)
        purchase_q = purchase_q.filter(PurchaseInvoice.date >= cutoff)

    total_sales = sum(inv.grand_total or 0 for inv in sales_q.all())
    total_purchase = sum(p.grand_total or 0 for p in purchase_q.all())
    gross_profit = total_sales - total_purchase
    gross_margin_pct = round((gross_profit / total_sales * 100), 2) if total_sales > 0 else 0.0

    return {
        "intent": "gross_profit_summary",
        "period_months": months,
        "start_date": start_date.strftime('%Y-%m-%d') if start_date else None,
        "end_date": end_date.strftime('%Y-%m-%d') if end_date else None,
        "total_sales": round(total_sales, 2),
        "total_purchase": round(total_purchase, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_profit_margin_percent": gross_margin_pct,
    }



def get_net_profit_summary(company_id: str, start_date=None, end_date=None, months: int = None) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)

    sales_q = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft']),
    )
    purchase_q = cdb.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.status.notin_(['Cancelled', 'Void', 'Draft']),
    )
    expense_q = cdb.query(Expense).filter(Expense.company_id == company_id)

    if start_date and end_date:
        sales_q = sales_q.filter(CustomerInvoice.invoice_date >= start_date, CustomerInvoice.invoice_date <= end_date)
        purchase_q = purchase_q.filter(PurchaseInvoice.date >= start_date, PurchaseInvoice.date <= end_date)
        expense_q = expense_q.filter(Expense.date >= start_date, Expense.date <= end_date)
    elif months:
        cutoff = date.today() - timedelta(days=30 * months)
        sales_q = sales_q.filter(CustomerInvoice.invoice_date >= cutoff)
        purchase_q = purchase_q.filter(PurchaseInvoice.date >= cutoff)
        expense_q = expense_q.filter(Expense.date >= cutoff)

    total_sales = sum(inv.grand_total or 0 for inv in sales_q.all())
    total_purchase = sum(p.grand_total or 0 for p in purchase_q.all())
    total_expenses = sum(e.amount or 0 for e in expense_q.all())

    gross_profit = total_sales - total_purchase
    net_profit = gross_profit - total_expenses

    gross_margin_pct = round((gross_profit / total_sales * 100), 2) if total_sales > 0 else 0.0
    net_margin_pct = round((net_profit / total_sales * 100), 2) if total_sales > 0 else 0.0

    return {
        "intent": "net_profit_summary",
        "period_months": months,
        "start_date": start_date.strftime('%Y-%m-%d') if start_date else None,
        "end_date": end_date.strftime('%Y-%m-%d') if end_date else None,
        "total_sales": round(total_sales, 2),
        "total_purchase": round(total_purchase, 2),
        "total_expenses": round(total_expenses, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_profit_margin_percent": gross_margin_pct,
        "net_profit": round(net_profit, 2),
        "net_profit_margin_percent": net_margin_pct,
        "is_profitable": net_profit >= 0,
    }



def get_bookings_list(company_id: str, days: int = 30, limit: int = 20) -> Dict[str, Any]:
    """'Booking' = a sales Invoice row (matches this file's own comment
    elsewhere: sales invoices are also called 'booking invoices'/AWB/docket).
    Excludes Cancelled/Void — see get_void_cancelled_list for those."""
    cdb = get_customer_session(company_id)
    cutoff = date.today() - timedelta(days=days)
    q = (
        cdb.query(Invoice)
        .filter(
            Invoice.company_id == company_id,
            Invoice.date >= cutoff,
            Invoice.status.notin_(['Cancelled', 'Void']),
        )
        .order_by(Invoice.date.desc())
    )
    total_count = q.count()
    rows = q.limit(limit).all()
    return {
        "intent": "bookings_list",
        "period_days": days,
        "total_bookings": total_count,
        "bookings": [
            {
                "invoice_id": inv.invoice_id,
                "date": inv.date.strftime("%d %b %Y"),
                "status": inv.status,
                "grand_total": inv.grand_total,
                "docket_no": inv.docket_no,
            }
            for inv in rows
        ],
    }


def get_void_cancelled_list(company_id: str, days: int = 30, limit: int = 20) -> Dict[str, Any]:
    cdb = get_customer_session(company_id)
    cutoff = date.today() - timedelta(days=days)
    q = (
        cdb.query(Invoice)
        .filter(
            Invoice.company_id == company_id,
            Invoice.date >= cutoff,
            Invoice.status.in_(['Cancelled', 'Void']),
        )
        .order_by(Invoice.date.desc())
    )
    total_count = q.count()
    rows = q.limit(limit).all()
    return {
        "intent": "void_cancelled_list",
        "period_days": days,
        "total_void_cancelled": total_count,
        "items": [
            {
                "invoice_id": inv.invoice_id,
                "date": inv.date.strftime("%d %b %Y"),
                "status": inv.status,
                "grand_total": inv.grand_total,
            }
            for inv in rows
        ],
    }


def get_price_list_status(company_id: str, identifier: str = None) -> Dict[str, Any]:
    """identifier, when given, filters to one courier. Without one,
    returns the most recent upload per courier."""
    cdb = get_customer_session(company_id)
    q = cdb.query(PriceList).filter(PriceList.company_id == company_id)
    if identifier:
        q = q.filter(PriceList.courier.ilike(f"%{identifier.strip()}%"))
    rows = q.order_by(PriceList.uploaded_at.desc()).all()

    if not rows:
        return {"intent": "price_list_status", "found": False, "query": identifier}

    latest_by_courier = {}
    for r in rows:
        if r.courier not in latest_by_courier:
            latest_by_courier[r.courier] = r

    return {
        "intent": "price_list_status",
        "found": True,
        "most_recent_upload": rows[0].uploaded_at.strftime("%d %b %Y %H:%M"),
        "most_recent_courier": rows[0].courier,
        "by_courier": [
            {
                "courier": r.courier,
                "list_type": r.list_type,
                "filename": r.filename,
                "uploaded_at": r.uploaded_at.strftime("%d %b %Y %H:%M"),
                "is_active": r.is_active,
            }
            for r in latest_by_courier.values()
        ],
    }


def get_whatsapp_status(company_id: str) -> Dict[str, Any]:
    """NOTE: uses the platform DB Company model, NOT get_customer_session().
    whatsapp_enabled / whatsapp_api_key live on Company in platform_models,
    not in the per-tenant qiy_<company_id> database — this is the one
    function in this file that deliberately breaks the cdb convention,
    because the data itself lives outside the tenant DB."""
    from platform_models import Company
    company = Company.query.filter_by(company_id=company_id).first()
    if not company:
        return {"intent": "whatsapp_status", "found": False}
    return {
        "intent": "whatsapp_status",
        "found": True,
        "connected": bool(getattr(company, "whatsapp_enabled", False)),
        "has_api_key": bool(getattr(company, "whatsapp_api_key", None)),
    }


def get_user_count_summary(company_id: str) -> Dict[str, Any]:
    """Roles confirmed in app.py: owner, manager, employee, accountant.
    (super_admin is platform-level, not a per-company role — excluded.)"""
    cdb = get_customer_session(company_id)
    users = cdb.query(CompanyUser).filter_by(company_id=company_id).all()

    by_role = {}
    for u in users:
        role = (u.role or "employee").lower()
        by_role[role] = by_role.get(role, 0) + 1

    active_count = sum(1 for u in users if u.is_active)

    return {
        "intent": "user_count_summary",
        "total_users": len(users),
        "active_users": active_count,
        "inactive_users": len(users) - active_count,
        "by_role": by_role,
    }


# ─────────────────────────────────────────────────────────────────────────
# NEW — Extended query functions for full DB coverage
# All functions follow the same pattern: company_id from session,
# deterministic return dict with "intent" key so fallback_format works.
# ─────────────────────────────────────────────────────────────────────────


def get_todays_sales(company_id: str) -> Dict[str, Any]:
    """Sales invoices created today (not Cancelled/Void)."""
    cdb = get_customer_session(company_id)
    today = date.today()
    rows = (
        cdb.query(CustomerInvoice)
        .filter(
            CustomerInvoice.company_id == company_id,
            CustomerInvoice.invoice_date == today,
            CustomerInvoice.status.notin_(["Cancelled", "Void", "Draft"]),
        )
        .order_by(CustomerInvoice.grand_total.desc())
        .all()
    )
    total = sum(inv.grand_total or 0 for inv in rows)
    collected = sum(inv.paid_amount or 0 for inv in rows)
    pending = sum(inv.balance or 0 for inv in rows)
    items = []
    for inv in rows[:15]:
        client = cdb.query(Client).filter_by(id=inv.client_id).first()
        items.append({
            "invoice_id": inv.invoice_number,
            "client": client.name if client else (inv.client_name or "Walk-in"),
            "grand_total": inv.grand_total,
            "status": inv.status,
        })
    return {
        "intent": "todays_sales",
        "date": today.strftime("%d %b %Y"),
        "invoice_count": len(rows),
        "total_sales": round(total, 2),
        "total_collected": round(collected, 2),
        "total_pending": round(pending, 2),
        "items": items,
    }



def get_top_clients_by_sales(company_id: str, limit: int = 10, months: int = None) -> Dict[str, Any]:
    """Top N clients by total invoice grand_total."""
    cdb = get_customer_session(company_id)
    q = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.status.notin_(["Cancelled", "Void", "Draft"]),
        CustomerInvoice.client_id.isnot(None),
    )
    if months:
        cutoff = date.today() - timedelta(days=30 * months)
        q = q.filter(CustomerInvoice.invoice_date >= cutoff)
    rows = q.all()

    agg: Dict[int, Dict] = {}
    for inv in rows:
        cid = inv.client_id
        if cid not in agg:
            agg[cid] = {"client_id": cid, "total_sales": 0.0, "invoice_count": 0}
        agg[cid]["total_sales"] += inv.grand_total or 0
        agg[cid]["invoice_count"] += 1

    ranked = sorted(agg.values(), key=lambda x: x["total_sales"], reverse=True)[:limit]
    # Attach client names
    for entry in ranked:
        client = cdb.query(Client).filter_by(id=entry["client_id"]).first()
        entry["name"] = client.name if client else "Unknown"
        entry["total_sales"] = round(entry["total_sales"], 2)

    return {
        "intent": "top_clients_sales",
        "period_months": months,
        "limit": limit,
        "clients": ranked,
    }



def get_worst_clients_by_sales(company_id: str, limit: int = 10, months: int = None) -> Dict[str, Any]:
    """Lowest revenue/sales clients or inactive clients."""
    cdb = get_customer_session(company_id)
    clients = cdb.query(Client).filter(
        Client.company_id == company_id,
        Client.status != "Deleted",
        ~Client.client_type.in_(["Supplier", "Cash-Only"]),
    ).all()
    
    q = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.status.notin_(["Cancelled", "Void", "Draft"]),
        CustomerInvoice.client_id.isnot(None),
    )
    if months:
        cutoff = date.today() - timedelta(days=30 * months)
        q = q.filter(CustomerInvoice.invoice_date >= cutoff)
    rows = q.all()
    
    sales_map = {}
    inv_count_map = {}
    for inv in rows:
        cid = inv.client_id
        sales_map[cid] = sales_map.get(cid, 0.0) + (inv.grand_total or 0.0)
        inv_count_map[cid] = inv_count_map.get(cid, 0) + 1
        
    client_list = []
    for c in clients:
        s = sales_map.get(c.id, 0.0)
        client_list.append({
            "client_id": c.id,
            "name": c.name,
            "total_sales": round(s, 2),
            "invoice_count": inv_count_map.get(c.id, 0),
            "phone": c.phone or "N/A",
        })
    client_list.sort(key=lambda x: x["total_sales"])
    worst_clients = client_list[:limit]
    
    return {
        "intent": "worst_clients_sales",
        "period_months": months,
        "limit": limit,
        "clients": worst_clients,
    }



def get_top_clients_by_outstanding(company_id: str, limit: int = 10) -> Dict[str, Any]:
    """Top N clients by live pending receivable."""
    cdb = get_customer_session(company_id)
    clients = cdb.query(Client).filter(
        Client.company_id == company_id,
        Client.status != "Deleted",
        ~Client.client_type.in_(["Supplier", "Both", "Cash-Only"]),
    ).all()
    live_map = _compute_outstanding_for_all_clients(cdb, company_id, clients)

    client_list = []
    for c in clients:
        bal = live_map.get(c.id, 0.0)
        if bal > 0:
            client_list.append({
                "name": c.name,
                "phone": c.phone or "N/A",
                "pending": bal,
                "credit_days": c.credit_days or 30,
                "last_payment": c.last_payment.strftime("%d %b %Y") if c.last_payment else None,
            })
    client_list.sort(key=lambda x: x["pending"], reverse=True)
    top_clients = client_list[:limit]

    return {
        "intent": "top_clients_outstanding",
        "limit": limit,
        "clients": top_clients,
        "total_shown": len(top_clients),
    }


def get_overdue_invoices(company_id: str, limit: int = 20) -> Dict[str, Any]:
    """Invoices where due_date < today and balance > 0."""
    cdb = get_customer_session(company_id)
    today = date.today()
    rows = (
        cdb.query(CustomerInvoice)
        .filter(
            CustomerInvoice.company_id == company_id,
            CustomerInvoice.balance > 0,
            CustomerInvoice.due_date < today,
            CustomerInvoice.status.notin_(["Cancelled", "Void", "Draft"]),
        )
        .order_by(CustomerInvoice.due_date.asc())
        .limit(limit)
        .all()
    )
    total_overdue = (
        cdb.query(func.sum(CustomerInvoice.balance))
        .filter(
            CustomerInvoice.company_id == company_id,
            CustomerInvoice.balance > 0,
            CustomerInvoice.due_date < today,
            CustomerInvoice.status.notin_(["Cancelled", "Void", "Draft"]),
        )
        .scalar() or 0.0
    )
    items = []
    for inv in rows:
        client = cdb.query(Client).filter_by(id=inv.client_id).first()
        days_overdue = (today - inv.due_date).days if inv.due_date else 0
        items.append({
            "invoice_id": inv.invoice_number,
            "client": client.name if client else "Unknown",
            "balance": round(inv.balance, 2),
            "due_date": inv.due_date.strftime("%d %b %Y") if inv.due_date else None,
            "days_overdue": days_overdue,
        })
    full_count = cdb.query(CustomerInvoice).filter(CustomerInvoice.company_id == company_id, CustomerInvoice.balance > 0, CustomerInvoice.due_date < today, CustomerInvoice.status.notin_(["Cancelled", "Void", "Draft"])).count()
    return {
        "intent": "overdue_invoices",
        "count": full_count,
        "total_overdue": round(total_overdue, 2),
        "items": items,
    }



def get_todays_expenses(company_id: str) -> Dict[str, Any]:
    """All expenses entered today."""
    cdb = get_customer_session(company_id)
    today = date.today()
    rows = cdb.query(Expense).filter(
        Expense.company_id == company_id,
        Expense.date == today,
    ).order_by(Expense.amount.desc()).all()
    total = sum(e.amount or 0 for e in rows)
    return {
        "intent": "todays_expenses",
        "date": today.strftime("%d %b %Y"),
        "count": len(rows),
        "total_expenses": round(total, 2),
        "items": [
            {"category": e.category, "description": e.description, "amount": e.amount, "payment_mode": e.payment_mode}
            for e in rows
        ],
    }


def get_expenses_by_category(company_id: str, category: str, months: int = 1) -> Dict[str, Any]:
    """Expenses filtered by a specific category (fuel, salary, office, etc.)."""
    cdb = get_customer_session(company_id)
    cutoff = date.today() - timedelta(days=30 * months)
    cat_filter = f"%{category.strip()}%"
    rows = (
        cdb.query(Expense)
        .filter(
            Expense.company_id == company_id,
            Expense.date >= cutoff,
            Expense.category.ilike(cat_filter),
        )
        .order_by(Expense.date.desc())
        .all()
    )
    total = sum(e.amount or 0 for e in rows)
    return {
        "intent": "expenses_category",
        "category": category,
        "period_months": months,
        "count": len(rows),
        "total_expenses": round(total, 2),
        "items": [
            {"date": e.date.strftime("%d %b %Y"), "description": e.description, "amount": e.amount}
            for e in rows[:20]
        ],
    }


def get_todays_cash(company_id: str) -> Dict[str, Any]:
    """Cash income and expense transactions for today."""
    cdb = get_customer_session(company_id)
    today = date.today()
    rows = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        CashTransaction.date == today,
    ).all()
    cash_in = sum(r.amount or 0 for r in rows if r.type == "income")
    cash_out = sum(r.amount or 0 for r in rows if r.type == "expense")
    # Running balance (all time)
    all_income = (
        cdb.query(func.sum(CashTransaction.amount))
        .filter(CashTransaction.company_id == company_id, CashTransaction.type == "income")
        .scalar() or 0.0
    )
    all_expense = (
        cdb.query(func.sum(CashTransaction.amount))
        .filter(CashTransaction.company_id == company_id, CashTransaction.type == "expense")
        .scalar() or 0.0
    )
    return {
        "intent": "todays_cash",
        "date": today.strftime("%d %b %Y"),
        "cash_in_today": round(cash_in, 2),
        "cash_out_today": round(cash_out, 2),
        "net_today": round(cash_in - cash_out, 2),
        "running_balance": round(all_income - all_expense, 2),
        "transaction_count": len(rows),
    }


def get_receipts_payments_summary(company_id: str, months: int = 1) -> Dict[str, Any]:
    """
    Receipts = cash 'income' transactions + bank 'credit' transactions.
    Payments = cash 'expense' transactions + bank 'debit' transactions.
    """
    cdb = get_customer_session(company_id)
    cutoff = date.today() - timedelta(days=30 * months)

    cash_rows = cdb.query(CashTransaction).filter(
        CashTransaction.company_id == company_id,
        CashTransaction.date >= cutoff,
    ).all()
    bank_rows = cdb.query(BankTransaction).filter(
        BankTransaction.company_id == company_id,
        BankTransaction.date >= cutoff,
    ).all()

    cash_receipts = sum(r.amount or 0 for r in cash_rows if r.type == "income")
    cash_payments = sum(r.amount or 0 for r in cash_rows if r.type == "expense")
    bank_receipts = sum(r.amount or 0 for r in bank_rows if r.type == "credit")
    bank_payments = sum(r.amount or 0 for r in bank_rows if r.type == "debit")

    return {
        "intent": "receipts_payments_summary",
        "period_months": months,
        "total_receipts": round(cash_receipts + bank_receipts, 2),
        "total_payments": round(cash_payments + bank_payments, 2),
        "cash_receipts": round(cash_receipts, 2),
        "cash_payments": round(cash_payments, 2),
        "bank_receipts": round(bank_receipts, 2),
        "bank_payments": round(bank_payments, 2),
        "net_flow": round((cash_receipts + bank_receipts) - (cash_payments + bank_payments), 2),
    }


def get_client_statement_summary(company_id: str, identifier: str) -> Dict[str, Any]:
    """Balance summary for a specific client: total invoiced, collected, pending."""
    cdb = get_customer_session(company_id)
    ident = f"%{identifier.strip()}%"
    client = (
        cdb.query(Client)
        .filter(
            Client.company_id == company_id,
            (Client.name.ilike(ident)) | (Client.client_id.ilike(ident)) | (Client.phone.ilike(ident)),
        )
        .first()
    )
    if not client:
        return {"intent": "client_statement", "found": False, "query": identifier}

    invoices = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.client_id == client.id,
        CustomerInvoice.status.notin_(["Cancelled", "Void", "Draft"]),
    ).order_by(CustomerInvoice.invoice_date.desc()).all()

    total_invoiced = sum(inv.grand_total or 0 for inv in invoices)
    total_collected = sum(inv.paid_amount or 0 for inv in invoices)
    total_pending = sum(inv.balance or 0 for inv in invoices)
    overdue = [inv for inv in invoices if inv.due_date and inv.due_date < date.today() and inv.balance > 0]

    return {
        "intent": "client_statement",
        "found": True,
        "name": client.name,
        "phone": client.phone,
        "gst_number": client.gst_number,
        "credit_limit": client.credit_limit,
        "credit_days": client.credit_days,
        "total_invoiced": round(total_invoiced, 2),
        "total_collected": round(total_collected, 2),
        "total_pending": round(total_pending, 2),
        "overdue_count": len(overdue),
        "overdue_amount": round(sum(inv.balance for inv in overdue), 2),
        "last_payment": client.last_payment.strftime("%d %b %Y") if client.last_payment else None,
        "invoice_count": len(invoices),
        "recent_invoices": [
            {
                "invoice_id": inv.invoice_number,
                "date": inv.invoice_date.strftime("%d %b %Y"),
                "grand_total": inv.grand_total,
                "balance": inv.balance,
                "status": inv.status,
            }
            for inv in invoices[:5]
        ],
    }



def get_supplier_statement_summary(company_id: str, identifier: str) -> Dict[str, Any]:
    """Balance summary for a specific supplier."""
    cdb = get_customer_session(company_id)
    ident = f"%{identifier.strip()}%"
    supplier = (
        cdb.query(Supplier)
        .filter(
            Supplier.company_id == company_id,
            (Supplier.name.ilike(ident)) | (Supplier.supplier_id.ilike(ident)) | (Supplier.phone.ilike(ident)),
        )
        .first()
    )
    if not supplier:
        return {"intent": "supplier_statement", "found": False, "query": identifier}

    purchases = cdb.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.supplier_id == supplier.id,
    ).order_by(PurchaseInvoice.date.desc()).all()

    total_purchased = sum(p.grand_total or 0 for p in purchases)
    total_paid = sum(p.paid_amount or 0 for p in purchases)
    total_pending = sum(p.balance or 0 for p in purchases)

    return {
        "intent": "supplier_statement",
        "found": True,
        "name": supplier.name,
        "phone": supplier.phone,
        "gst_number": supplier.gst_number,
        "total_purchased": round(total_purchased, 2),
        "total_paid": round(total_paid, 2),
        "total_pending": round(total_pending, 2),
        "invoice_count": len(purchases),
        "recent_invoices": [
            {
                "invoice_id": p.invoice_id,
                "date": p.date.strftime("%d %b %Y"),
                "grand_total": p.grand_total,
                "balance": p.balance,
                "status": p.status,
            }
            for p in purchases[:5]
        ],
    }


def get_estimate_summary(company_id: str, months: int = 1) -> Dict[str, Any]:
    """Overview of estimates/quotations."""
    cdb = get_customer_session(company_id)
    cutoff = date.today() - timedelta(days=30 * months)
    rows = cdb.query(Estimate).filter(
        Estimate.company_id == company_id,
        Estimate.date >= cutoff,
    ).order_by(Estimate.date.desc()).all()

    by_status: Dict[str, int] = {}
    for e in rows:
        s = e.status or "Draft"
        by_status[s] = by_status.get(s, 0) + 1

    total_value = sum(e.grand_total or 0 for e in rows)
    return {
        "intent": "estimate_summary",
        "period_months": months,
        "count": len(rows),
        "total_value": round(total_value, 2),
        "by_status": by_status,
        "recent": [
            {
                "estimate_id": e.estimate_id,
                "date": e.date.strftime("%d %b %Y"),
                "grand_total": e.grand_total,
                "status": e.status,
            }
            for e in rows[:10]
        ],
    }


def get_estimate_detail(company_id: str, identifier: str) -> Dict[str, Any]:
    """Single estimate detail by estimate ID."""
    cdb = get_customer_session(company_id)
    ident = f"%{identifier.strip()}%"
    est = (
        cdb.query(Estimate)
        .filter(Estimate.company_id == company_id, Estimate.estimate_id.ilike(ident))
        .first()
    )
    if not est:
        return {"intent": "estimate_detail", "found": False, "query": identifier}

    client = cdb.query(Client).filter_by(id=est.client_id).first()
    return {
        "intent": "estimate_detail",
        "found": True,
        "estimate_id": est.estimate_id,
        "client": client.name if client else "Unknown",
        "date": est.date.strftime("%d %b %Y"),
        "valid_until": est.valid_until.strftime("%d %b %Y") if est.valid_until else None,
        "status": est.status,
        "grand_total": round(est.grand_total or 0, 2),
        "tax_amount": round(est.tax_amount or 0, 2),
    }


def get_top_suppliers_by_purchase(company_id: str, limit: int = 10, months: int = None) -> Dict[str, Any]:
    """Top N suppliers by total purchase amount."""
    cdb = get_customer_session(company_id)
    q = cdb.query(PurchaseInvoice).filter(PurchaseInvoice.company_id == company_id)
    if months:
        cutoff = date.today() - timedelta(days=30 * months)
        q = q.filter(PurchaseInvoice.date >= cutoff)
    rows = q.all()

    agg: Dict[str, Dict] = {}
    for p in rows:
        key = p.supplier_name or "Unknown"
        if key not in agg:
            agg[key] = {"name": key, "total_purchase": 0.0, "invoice_count": 0, "total_pending": 0.0}
        agg[key]["total_purchase"] += p.grand_total or 0
        agg[key]["invoice_count"] += 1
        agg[key]["total_pending"] += p.balance or 0

    ranked = sorted(agg.values(), key=lambda x: x["total_purchase"], reverse=True)[:limit]
    for entry in ranked:
        entry["total_purchase"] = round(entry["total_purchase"], 2)
        entry["total_pending"] = round(entry["total_pending"], 2)

    return {
        "intent": "top_suppliers_purchase",
        "period_months": months,
        "limit": limit,
        "suppliers": ranked,
    }


def get_new_clients(company_id: str, months: int = 1) -> Dict[str, Any]:
    """Clients created within the last N months."""
    cdb = get_customer_session(company_id)
    cutoff = date.today() - timedelta(days=30 * months)
    clients = (
        cdb.query(Client)
        .filter(Client.company_id == company_id, Client.created_at >= cutoff)
        .order_by(Client.created_at.desc())
        .all()
    )
    return {
        "intent": "new_clients",
        "period_months": months,
        "count": len(clients),
        "clients": [
            {
                "name": c.name,
                "phone": c.phone,
                "city": c.city,
                "created_at": c.created_at.strftime("%d %b %Y") if c.created_at else None,
                "status": c.status,
            }
            for c in clients[:20]
        ],
    }


def get_customer_invoice_summary(company_id: str, months: int = 1, start_date=None, end_date=None) -> Dict[str, Any]:
    """Posted sales invoices in the requested period."""
    cdb = get_customer_session(company_id)
    cutoff = start_date or date.today() - timedelta(days=30 * months)
    rows = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.invoice_date >= cutoff,
        CustomerInvoice.invoice_date <= (end_date or date.today()),
        CustomerInvoice.status.notin_(["Cancelled", "Void", "Draft"]),
    ).order_by(CustomerInvoice.invoice_date.desc()).all()

    total = sum(r.grand_total or 0 for r in rows)
    collected = sum(r.paid_amount or 0 for r in rows)
    pending = sum(r.balance or 0 for r in rows)
    by_status: Dict[str, int] = {}
    for r in rows:
        s = r.status or "Pending"
        by_status[s] = by_status.get(s, 0) + 1

    return {
        "intent": "customer_invoice_summary",
        "period_months": months,
        "start_date": str(cutoff),
        "end_date": str(end_date or date.today()),
        "count": len(rows),
        "total_value": round(total, 2),
        "total_collected": round(collected, 2),
        "total_pending": round(pending, 2),
        "by_status": by_status,
        "recent": [
            {
                "invoice_number": r.invoice_number,
                "client_name": r.client_name,
                "invoice_date": r.invoice_date.strftime("%d %b %Y"),
                "grand_total": r.grand_total,
                "balance": r.balance,
                "status": r.status,
            }
            for r in rows[:10]
        ],
    }


def get_bank_account_detail(company_id: str, identifier: str) -> Dict[str, Any]:
    """Single bank account detail with recent transactions."""
    cdb = get_customer_session(company_id)
    ident = f"%{identifier.strip()}%"
    account = (
        cdb.query(BankAccount)
        .filter(
            BankAccount.company_id == company_id,
            (BankAccount.bank_name.ilike(ident)) |
            (BankAccount.account_name.ilike(ident)) |
            (BankAccount.account_number.ilike(ident)),
        )
        .first()
    )
    if not account:
        # Return all accounts if no match
        accounts = cdb.query(BankAccount).filter_by(company_id=company_id, status="Active").all()
        return {
            "intent": "bank_account_detail",
            "found": False,
            "query": identifier,
            "accounts": [
                {"bank_name": a.bank_name, "account_name": a.account_name,
                 "balance": a.balance, "status": a.status}
                for a in accounts
            ],
        }

    recent_txns = (
        cdb.query(BankTransaction)
        .filter_by(bank_account_id=account.id)
        .order_by(BankTransaction.date.desc())
        .limit(10)
        .all()
    )
    return {
        "intent": "bank_account_detail",
        "found": True,
        "bank_name": account.bank_name,
        "account_name": account.account_name,
        "account_number": account.account_number[-4:].rjust(len(account.account_number), '*'),
        "ifsc_code": account.ifsc_code,
        "balance": round(account.balance, 2),
        "status": account.status,
        "recent_transactions": [
            {
                "date": t.date.strftime("%d %b %Y"),
                "type": t.type,
                "amount": t.amount,
                "description": t.description,
                "party_name": t.party_name,
            }
            for t in recent_txns
        ],
    }


def get_todays_bookings(company_id: str) -> Dict[str, Any]:
    """Bookings (invoices) created today."""
    cdb = get_customer_session(company_id)
    today = date.today()
    rows = (
        cdb.query(Invoice)
        .filter(Invoice.company_id == company_id, Invoice.date == today)
        .order_by(Invoice.created_at.desc())
        .all()
    )
    total = sum(inv.grand_total or 0 for inv in rows)
    by_status: Dict[str, int] = {}
    for inv in rows:
        s = inv.status or "Pending"
        by_status[s] = by_status.get(s, 0) + 1
    return {
        "intent": "todays_bookings",
        "date": today.strftime("%d %b %Y"),
        "total_bookings": len(rows),
        "total_value": round(total, 2),
        "by_status": by_status,
        "bookings": [
            {
                "invoice_id": inv.invoice_id,
                "docket_no": inv.docket_no,
                "status": inv.status,
                "grand_total": inv.grand_total,
            }
            for inv in rows[:15]
        ],
    }


def get_client_pending_amount(company_id: str, identifier: str) -> Dict[str, Any]:
    """Exact pending balance, credit terms, and unpaid invoices for a specific client."""
    cdb = get_customer_session(company_id)
    ident = f"%{identifier.strip()}%"
    client = (
        cdb.query(Client)
        .filter(
            Client.company_id == company_id,
            (Client.name.ilike(ident)) |
            (Client.client_id.ilike(ident)) |
            (Client.phone.ilike(ident)),
        )
        .first()
    )
    if not client:
        return {"intent": "client_pending_amount", "found": False, "query": identifier}

    unpaid_invoices = (
        cdb.query(CustomerInvoice)
        .filter(
            CustomerInvoice.company_id == company_id,
            CustomerInvoice.client_id == client.id,
            CustomerInvoice.balance > 0,
            CustomerInvoice.status.notin_(["Cancelled", "Void", "Draft"]),
        )
        .order_by(CustomerInvoice.invoice_date.asc())
        .all()
    )

    today = date.today()
    overdue_invoices = [inv for inv in unpaid_invoices if inv.due_date and inv.due_date < today]
    overdue_amount = sum(inv.balance or 0 for inv in overdue_invoices)

    live_outstanding = _compute_client_live_outstanding(cdb, company_id, client)

    return {
        "intent": "client_pending_amount",
        "found": True,
        "name": client.name,
        "client_id": client.client_id,
        "phone": client.phone or "N/A",
        "pending_amount": live_outstanding,
        "credit_limit": round(client.credit_limit or 0, 2),
        "credit_days": client.credit_days or 30,
        "overdue_count": len(overdue_invoices),
        "overdue_amount": round(overdue_amount, 2),
        "unpaid_count": len(unpaid_invoices),
        "last_payment": client.last_payment.strftime("%d %b %Y") if client.last_payment else "No payment recorded",
        "unpaid_invoices": [
            {
                "invoice_id": inv.invoice_number,
                "date": inv.invoice_date.strftime("%d %b %Y"),
                "grand_total": round(inv.grand_total or 0, 2),
                "balance": round(inv.balance or 0, 2),
                "due_date": inv.due_date.strftime("%d %b %Y") if inv.due_date else "-",
                "is_overdue": bool(inv.due_date and inv.due_date < today),
            }
            for inv in unpaid_invoices[:10]
        ],
    }



def get_supplier_payable_amount(company_id: str, identifier: str) -> Dict[str, Any]:
    """Exact payable amount, credit terms, and unpaid bills for a specific supplier."""
    cdb = get_customer_session(company_id)
    ident = f"%{identifier.strip()}%"
    supplier = (
        cdb.query(Supplier)
        .filter(
            Supplier.company_id == company_id,
            (Supplier.name.ilike(ident)) |
            (Supplier.supplier_id.ilike(ident)) |
            (Supplier.phone.ilike(ident)),
        )
        .first()
    )
    if not supplier:
        return {"intent": "supplier_payable_amount", "found": False, "query": identifier}

    unpaid_bills = (
        cdb.query(PurchaseInvoice)
        .filter(
            PurchaseInvoice.company_id == company_id,
            PurchaseInvoice.supplier_id == supplier.id,
            PurchaseInvoice.balance > 0,
            PurchaseInvoice.status.notin_(["Cancelled", "Void", "Draft"]),
        )
        .order_by(PurchaseInvoice.date.asc())
        .all()
    )

    today = date.today()
    overdue_bills = [p for p in unpaid_bills if p.due_date and p.due_date < today]
    live_payable = _compute_supplier_live_payable(cdb, company_id, supplier)

    return {
        "intent": "supplier_payable_amount",
        "found": True,
        "name": supplier.name,
        "supplier_id": supplier.supplier_id,
        "phone": supplier.phone or "N/A",
        "payable_amount": live_payable,
        "credit_limit": round(supplier.credit_limit or 0, 2),
        "credit_days": supplier.credit_days or 30,
        "unpaid_count": len(unpaid_bills),
        "overdue_count": len(overdue_bills),
        "overdue_amount": round(sum(p.balance or 0 for p in overdue_bills), 2),
        "brands": [b.brand_name for b in supplier.brands] if supplier.brands else [],
        "unpaid_bills": [
            {
                "invoice_id": p.invoice_id,
                "invoice_number": p.invoice_number or p.invoice_id,
                "date": p.date.strftime("%d %b %Y"),
                "grand_total": round(p.grand_total or 0, 2),
                "balance": round(p.balance or 0, 2),
                "due_date": p.due_date.strftime("%d %b %Y") if p.due_date else "-",
                "is_overdue": bool(p.due_date and p.due_date < today),
            }
            for p in unpaid_bills[:10]
        ],
    }


def get_party_outstanding(company_id: str, identifier: str) -> Dict[str, Any]:
    """
    Search across both Client and Supplier tables for pending balance / payable amount.
    Handles exact matching, partial names, IDs, and phone numbers.
    """
    client_res = get_client_pending_amount(company_id, identifier)
    supplier_res = get_supplier_payable_amount(company_id, identifier)

    if client_res.get("found") and not supplier_res.get("found"):
        client_res["intent"] = "client_pending_amount"
        client_res["party_type"] = "Client"
        return client_res

    if supplier_res.get("found") and not client_res.get("found"):
        supplier_res["intent"] = "supplier_payable_amount"
        supplier_res["party_type"] = "Supplier"
        return supplier_res

    if client_res.get("found") and supplier_res.get("found"):
        return {
            "intent": "party_outstanding_both",
            "found": True,
            "name": client_res["name"],
            "party_type": "Client & Supplier",
            "client_pending": client_res.get("pending_amount", 0.0),
            "supplier_payable": supplier_res.get("payable_amount", 0.0),
            "client_data": client_res,
            "supplier_data": supplier_res,
        }

    return {"intent": "party_outstanding", "found": False, "query": identifier}


def get_customer_invoice_detail(company_id: str, identifier: str) -> Dict[str, Any]:
    """Single Customer Invoice (consolidated bill) lookup with line items."""
    cdb = get_customer_session(company_id)
    ident = f"%{identifier.strip()}%"
    ci = (
        cdb.query(CustomerInvoice)
        .filter(
            CustomerInvoice.company_id == company_id,
            (CustomerInvoice.invoice_number.ilike(ident)),
        )
        .first()
    )
    if not ci:
        return {"intent": "customer_invoice_detail", "found": False, "query": identifier}

    items = cdb.query(CustomerInvoiceItem).filter_by(customer_invoice_id=ci.id).all()

    return {
        "intent": "customer_invoice_detail",
        "found": True,
        "invoice_number": ci.invoice_number,
        "client_name": ci.client_name or "Unknown",
        "invoice_date": ci.invoice_date.strftime("%d %b %Y") if ci.invoice_date else "-",
        "due_date": ci.due_date.strftime("%d %b %Y") if ci.due_date else "-",
        "invoice_type": ci.invoice_type,
        "status": ci.status,
        "subtotal": round(ci.subtotal or 0, 2),
        "tax_amount": round(ci.tax_amount or 0, 2),
        "grand_total": round(ci.grand_total or 0, 2),
        "paid_amount": round(ci.paid_amount or 0, 2),
        "balance": round(ci.balance or 0, 2),
        "item_count": len(items),
        "items": [
            {
                "item_code": it.item_code or "-",
                "item_name": it.item_name or it.item_description or "Item",
                "quantity": it.quantity or 0,
                "unit": it.unit or "",
                "rate": it.rate or 0,
                "total_amount": round(it.total_amount or 0, 2),
            }
            for it in items[:15]
        ],
    }



def get_general_tax_knowledge(topic: str = "") -> Dict[str, Any]:
    return {"intent": "general_tax_knowledge", "title": "Tax information in Qiyadah",
            "content": "Ask 'GST summary' to inspect tax amounts recorded on sales and purchase invoices. That summary is not a filed return or a confirmed tax liability. Current tax rates, credit eligibility and filing rules are not connected to a live legal source in this assistant; verify them with the official tax authority or your accountant before applying them."}



def get_help_catalog() -> Dict[str, Any]:
    from utils.assistant_catalog import help_catalog
    return help_catalog()



# ─────────────────────────────────────────────────────────────────────────
# Country-wise & Employee-wise Bookings, Sales, Purchase & Profit Analytics
# ─────────────────────────────────────────────────────────────────────────

def _invoice_country(inv) -> Optional[str]:
    """Safely extract destination country from Invoice.terms JSON blob"""
    if not inv or not inv.terms:
        return None
    try:
        meta = json.loads(inv.terms)
        dest = meta.get('destination') or meta.get('country') or meta.get('consignee_country')
        return dest.strip() if dest else None
    except Exception:
        return None


_COUNTRY_ALIASES = {
    "uae": "United Arab Emirates",
    "united arab emirates": "United Arab Emirates",
    "emirates": "United Arab Emirates",
    "dubai": "United Arab Emirates",
    "abu dhabi": "United Arab Emirates",
    "sharjah": "United Arab Emirates",
    "usa": "United States",
    "united states": "United States",
    "us": "United States",
    "america": "United States",
    "uk": "United Kingdom",
    "united kingdom": "United Kingdom",
    "britain": "United Kingdom",
    "england": "United Kingdom",
    "london": "United Kingdom",
    "ksa": "Saudi Arabia",
    "saudi": "Saudi Arabia",
    "saudi arabia": "Saudi Arabia",
    "nz": "New Zealand",
    "new zealand": "New Zealand",
}


def _match_country_name(country_in_db: Optional[str], query_country: Optional[str]) -> bool:
    if not country_in_db or not query_country:
        return False
    c_db = country_in_db.lower().strip()
    q_c = query_country.lower().strip()

    if c_db == q_c or q_c in c_db or c_db in q_c:
        return True

    canon_q = _COUNTRY_ALIASES.get(q_c, q_c).lower()
    canon_db = _COUNTRY_ALIASES.get(c_db, c_db).lower()
    if canon_q == canon_db or canon_q in canon_db or canon_db in canon_q:
        return True

    return False


def get_country_booking_summary(
    company_id: str,
    country: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    months: Optional[int] = None
) -> Dict[str, Any]:
    """
    Analyzes bookings, sales, purchases, and profit for a specific country or all countries.
    Excludes Void & Draft bookings to match BI Dashboard rules.
    """
    cdb = get_customer_session(company_id)

    q = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.status.notin_(['Void', 'Draft'])
    )
    if start_date and end_date:
        q = q.filter(Invoice.date >= start_date, Invoice.date <= end_date)
    elif months:
        cutoff = date.today() - timedelta(days=30 * months)
        q = q.filter(Invoice.date >= cutoff)

    invoices = q.order_by(Invoice.date.desc()).all()

    # If specific country requested
    if country and country.strip().lower() not in ("all", "country wise", "country-wise", "all countries", "summary", "every country", "none"):
        target_country = country.strip()
        matching_invoices = [inv for inv in invoices if _match_country_name(_invoice_country(inv), target_country)]

        canonical_name = _COUNTRY_ALIASES.get(target_country.lower(), target_country.title())

        if not matching_invoices:
            return {
                "intent": "country_bookings_summary",
                "found": False,
                "country": canonical_name,
                "query": target_country,
                "booking_count": 0,
                "total_sales": 0.0,
                "total_purchase": 0.0,
                "profit": 0.0,
                "profit_margin": 0.0,
                "total_collected": 0.0,
                "total_pending": 0.0,
                "start_date": start_date.strftime('%Y-%m-%d') if start_date else None,
                "end_date": end_date.strftime('%Y-%m-%d') if end_date else None,
                "period_months": months,
            }

        inv_ids = [inv.id for inv in matching_invoices]
        total_sales = sum(inv.grand_total or 0 for inv in matching_invoices)
        total_collected = sum(inv.paid_amount or 0 for inv in matching_invoices)
        total_pending = sum(inv.balance or 0 for inv in matching_invoices)

        total_purchase = 0.0
        if inv_ids:
            p_rows = (
                cdb.query(PurchaseInvoiceItem)
                .join(PurchaseInvoice, PurchaseInvoiceItem.purchase_invoice_id == PurchaseInvoice.id)
                .filter(
                    PurchaseInvoice.company_id == company_id,
                    PurchaseInvoice.status.notin_(['Void', 'Draft']),
                    PurchaseInvoiceItem.source_invoice_id.in_(inv_ids)
                )
                .all()
            )
            total_purchase = sum(p.total_amount or 0 for p in p_rows)

        profit = total_sales - total_purchase
        margin = round((profit / total_sales * 100), 1) if total_sales > 0 else 0.0

        sample_country = _invoice_country(matching_invoices[0]) or canonical_name

        client_map: Dict[int, float] = {}
        for inv in matching_invoices:
            if inv.client_id:
                client_map[inv.client_id] = client_map.get(inv.client_id, 0.0) + (inv.grand_total or 0.0)
        top_clients = []
        if client_map:
            for c_id, amt in sorted(client_map.items(), key=lambda x: x[1], reverse=True)[:5]:
                cl = cdb.query(Client).filter_by(id=c_id).first()
                if cl:
                    top_clients.append({"name": cl.name, "amount": round(amt, 2)})

        recent_bookings = []
        for inv in matching_invoices[:5]:
            cl = cdb.query(Client).filter_by(id=inv.client_id).first() if inv.client_id else None
            recent_bookings.append({
                "invoice_id": inv.invoice_id,
                "docket_no": inv.docket_no or "-",
                "date": inv.date.strftime("%d %b %Y"),
                "client": cl.name if cl else "Unknown",
                "amount": round(inv.grand_total or 0.0, 2),
                "status": inv.status
            })

        return {
            "intent": "country_bookings_summary",
            "found": True,
            "country": sample_country,
            "query": target_country,
            "booking_count": len(matching_invoices),
            "total_sales": round(total_sales, 2),
            "total_purchase": round(total_purchase, 2),
            "profit": round(profit, 2),
            "profit_margin": margin,
            "total_collected": round(total_collected, 2),
            "total_pending": round(total_pending, 2),
            "top_clients": top_clients,
            "recent_bookings": recent_bookings,
            "start_date": start_date.strftime('%Y-%m-%d') if start_date else None,
            "end_date": end_date.strftime('%Y-%m-%d') if end_date else None,
            "period_months": months,
        }

    # All countries breakdown
    countries_data: Dict[str, Dict[str, Any]] = {}
    for inv in invoices:
        c_name = _invoice_country(inv)
        if not c_name or c_name.strip() in ("", "Unknown", "-", "N/A"):
            continue
        c_clean = c_name.strip()
        if c_clean not in countries_data:
            countries_data[c_clean] = {
                "country": c_clean,
                "invoices": [],
                "sales": 0.0,
            }
        countries_data[c_clean]["invoices"].append(inv)
        countries_data[c_clean]["sales"] += (inv.grand_total or 0.0)

    breakdown = []
    total_sales_all = 0.0
    total_purchase_all = 0.0
    total_bookings_all = 0

    for c_clean, c_info in countries_data.items():
        c_invs = c_info["invoices"]
        c_inv_ids = [inv.id for inv in c_invs]
        c_sales = c_info["sales"]
        c_purchase = 0.0
        if c_inv_ids:
            p_rows = (
                cdb.query(PurchaseInvoiceItem)
                .join(PurchaseInvoice, PurchaseInvoiceItem.purchase_invoice_id == PurchaseInvoice.id)
                .filter(
                    PurchaseInvoice.company_id == company_id,
                    PurchaseInvoice.status.notin_(['Void', 'Draft']),
                    PurchaseInvoiceItem.source_invoice_id.in_(c_inv_ids)
                )
                .all()
            )
            c_purchase = sum(p.total_amount or 0.0 for p in p_rows)

        c_profit = c_sales - c_purchase
        c_margin = round((c_profit / c_sales * 100), 1) if c_sales > 0 else 0.0

        total_sales_all += c_sales
        total_purchase_all += c_purchase
        total_bookings_all += len(c_invs)

        breakdown.append({
            "country": c_clean,
            "booking_count": len(c_invs),
            "total_sales": round(c_sales, 2),
            "total_purchase": round(c_purchase, 2),
            "profit": round(c_profit, 2),
            "profit_margin": c_margin,
        })

    breakdown.sort(key=lambda x: x["total_sales"], reverse=True)
    overall_profit = total_sales_all - total_purchase_all
    overall_margin = round((overall_profit / total_sales_all * 100), 1) if total_sales_all > 0 else 0.0

    return {
        "intent": "country_bookings_summary",
        "found": True,
        "country": "All Countries",
        "total_countries": len(breakdown),
        "total_bookings": total_bookings_all,
        "total_sales": round(total_sales_all, 2),
        "total_purchase": round(total_purchase_all, 2),
        "profit": round(overall_profit, 2),
        "profit_margin": overall_margin,
        "breakdown": breakdown[:20],
        "start_date": start_date.strftime('%Y-%m-%d') if start_date else None,
        "end_date": end_date.strftime('%Y-%m-%d') if end_date else None,
        "period_months": months,
    }


def get_employee_booking_summary(
    company_id: str,
    employee_identifier: Optional[str] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    months: Optional[int] = None
) -> Dict[str, Any]:
    """
    Analyzes bookings, sales, purchases, and profit by employee or all employees.
    Excludes Void & Draft bookings to match BI Dashboard rules.
    """
    cdb = get_customer_session(company_id)

    employees = cdb.query(CompanyUser).filter(
        CompanyUser.company_id == company_id,
        CompanyUser.is_active == True
    ).all()

    q = cdb.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.status.notin_(['Void', 'Draft'])
    )
    if start_date and end_date:
        q = q.filter(Invoice.date >= start_date, Invoice.date <= end_date)
    elif months:
        cutoff = date.today() - timedelta(days=30 * months)
        q = q.filter(Invoice.date >= cutoff)

    invoices = q.order_by(Invoice.date.desc()).all()

    # If specific employee requested
    if employee_identifier and employee_identifier.strip().lower() not in ("all", "employee wise", "employee-wise", "all employees", "summary", "team", "staff", "performance", "none"):
        ident = employee_identifier.strip().lower()
        matched_emp = None
        for emp in employees:
            if (emp.full_name and ident in emp.full_name.lower()) or (emp.email and ident in emp.email.lower()) or (emp.user_id and ident in emp.user_id.lower()):
                matched_emp = emp
                break

        emp_name = matched_emp.full_name if matched_emp else employee_identifier.strip().title()
        emp_email = matched_emp.email if matched_emp else employee_identifier.strip()

        matching_invoices = [
            inv for inv in invoices
            if (inv.created_by and (
                inv.created_by.lower() == emp_email.lower() or
                (matched_emp and matched_emp.full_name and inv.created_by.lower() == matched_emp.full_name.lower()) or
                ident in inv.created_by.lower()
            ))
        ]

        if not matching_invoices:
            return {
                "intent": "employee_bookings_summary",
                "found": bool(matched_emp),
                "employee_name": emp_name,
                "email": emp_email,
                "role": matched_emp.role if matched_emp else "Employee",
                "booking_count": 0,
                "total_sales": 0.0,
                "total_purchase": 0.0,
                "profit": 0.0,
                "profit_margin": 0.0,
                "total_collected": 0.0,
                "total_pending": 0.0,
                "start_date": start_date.strftime('%Y-%m-%d') if start_date else None,
                "end_date": end_date.strftime('%Y-%m-%d') if end_date else None,
                "period_months": months,
            }

        inv_ids = [inv.id for inv in matching_invoices]
        total_sales = sum(inv.grand_total or 0.0 for inv in matching_invoices)
        total_collected = sum(inv.paid_amount or 0.0 for inv in matching_invoices)
        total_pending = sum(inv.balance or 0.0 for inv in matching_invoices)

        total_purchase = 0.0
        if inv_ids:
            p_rows = (
                cdb.query(PurchaseInvoiceItem)
                .join(PurchaseInvoice, PurchaseInvoiceItem.purchase_invoice_id == PurchaseInvoice.id)
                .filter(
                    PurchaseInvoice.company_id == company_id,
                    PurchaseInvoice.status.notin_(['Void', 'Draft']),
                    PurchaseInvoiceItem.source_invoice_id.in_(inv_ids)
                )
                .all()
            )
            total_purchase = sum(p.total_amount or 0.0 for p in p_rows)

        profit = total_sales - total_purchase
        margin = round((profit / total_sales * 100), 1) if total_sales > 0 else 0.0

        recent_bookings = []
        for inv in matching_invoices[:5]:
            cl = cdb.query(Client).filter_by(id=inv.client_id).first() if inv.client_id else None
            recent_bookings.append({
                "invoice_id": inv.invoice_id,
                "docket_no": inv.docket_no or "-",
                "date": inv.date.strftime("%d %b %Y"),
                "client": cl.name if cl else "Unknown",
                "amount": round(inv.grand_total or 0.0, 2),
                "status": inv.status
            })

        return {
            "intent": "employee_bookings_summary",
            "found": True,
            "employee_name": emp_name,
            "email": emp_email,
            "role": matched_emp.role if matched_emp else "Employee",
            "booking_count": len(matching_invoices),
            "total_sales": round(total_sales, 2),
            "total_purchase": round(total_purchase, 2),
            "profit": round(profit, 2),
            "profit_margin": margin,
            "total_collected": round(total_collected, 2),
            "total_pending": round(total_pending, 2),
            "recent_bookings": recent_bookings,
            "start_date": start_date.strftime('%Y-%m-%d') if start_date else None,
            "end_date": end_date.strftime('%Y-%m-%d') if end_date else None,
            "period_months": months,
        }

    # All employees breakdown
    breakdown = []
    total_sales_all = 0.0
    total_purchase_all = 0.0
    total_bookings_all = 0

    for emp in employees:
        emp_email = emp.email
        emp_name = emp.full_name or emp_email

        emp_invs = [
            inv for inv in invoices
            if inv.created_by and (
                inv.created_by.lower() == emp_email.lower() or
                (emp.full_name and inv.created_by.lower() == emp.full_name.lower())
            )
        ]

        emp_inv_ids = [inv.id for inv in emp_invs]
        emp_sales = sum(inv.grand_total or 0.0 for inv in emp_invs)
        emp_purchase = 0.0
        if emp_inv_ids:
            p_rows = (
                cdb.query(PurchaseInvoiceItem)
                .join(PurchaseInvoice, PurchaseInvoiceItem.purchase_invoice_id == PurchaseInvoice.id)
                .filter(
                    PurchaseInvoice.company_id == company_id,
                    PurchaseInvoice.status.notin_(['Void', 'Draft']),
                    PurchaseInvoiceItem.source_invoice_id.in_(emp_inv_ids)
                )
                .all()
            )
            emp_purchase = sum(p.total_amount or 0.0 for p in p_rows)

        emp_profit = emp_sales - emp_purchase
        emp_margin = round((emp_profit / emp_sales * 100), 1) if emp_sales > 0 else 0.0

        total_sales_all += emp_sales
        total_purchase_all += emp_purchase
        total_bookings_all += len(emp_invs)

        breakdown.append({
            "employee_name": emp_name,
            "email": emp_email,
            "role": emp.role or "Employee",
            "booking_count": len(emp_invs),
            "total_sales": round(emp_sales, 2),
            "total_purchase": round(emp_purchase, 2),
            "profit": round(emp_profit, 2),
            "profit_margin": emp_margin,
        })

    breakdown.sort(key=lambda x: x["total_sales"], reverse=True)
    overall_profit = total_sales_all - total_purchase_all
    overall_margin = round((overall_profit / total_sales_all * 100), 1) if total_sales_all > 0 else 0.0

    return {
        "intent": "employee_bookings_summary",
        "found": True,
        "employee_name": "All Employees",
        "total_employees": len(employees),
        "total_bookings": total_bookings_all,
        "total_sales": round(total_sales_all, 2),
        "total_purchase": round(total_purchase_all, 2),
        "profit": round(overall_profit, 2),
        "profit_margin": overall_margin,
        "breakdown": breakdown,
        "start_date": start_date.strftime('%Y-%m-%d') if start_date else None,
        "end_date": end_date.strftime('%Y-%m-%d') if end_date else None,
        "period_months": months,
    }


def get_company_deep_analysis(company_id: str) -> Dict[str, Any]:
    """
    Computes a comprehensive 15-20 point deep diagnostic executive audit of the company directly from the database:
    1. All-time Sales & Invoices Count
    2. Current Month Sales & Invoices Count
    3. MoM (Month-over-Month) Sales Growth %
    4. Last 3 Months Trend & Average
    5. Last 6 Months Month-by-Month Performance
    6. Direct Cost (Purchases / COGS) & Gross Profit
    7. Operating Expenses & Net Profit
    8. Liquid Funds (Cash in hand + Bank balances)
    9. Accounts Receivable & Collection Efficiency %
    10. Accounts Payable (Vendor Liabilities)
    11. Top Client & Revenue Share %
    12. Client Concentration Risk Analysis (Top 3 Clients %)
    13. Surging Clients (Highest Growth vs Last Month)
    14. Declining / At-Risk Clients (Billing lessened from last month)
    15. Top Revenue Stream / Product & Workshop Category
    16. Top Performing Employee / Sales Lead
    17. Invoice Cancellation / Void Rate
    18. GST Tax Position (Output vs Input)
    19. Overall Company Financial Health Score
    20. Actionable Strategic AI Recommendations
    """
    cdb = get_customer_session(company_id)
    today = date.today()

    # ─────────────────────────────────────────────────────────────
    # 1. All-Time Sales & Invoices
    # ─────────────────────────────────────────────────────────────
    ci_rows = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == company_id,
        CustomerInvoice.status.notin_(['Cancelled', 'Void', 'Draft']),
    ).all()

    if ci_rows:
        valid_invs = ci_rows
        is_customer_invoice_model = True
    else:
        valid_invs = cdb.query(Invoice).filter(
            Invoice.company_id == company_id,
            Invoice.status.notin_(['Cancelled', 'Void', 'Draft']),
        ).all()
        is_customer_invoice_model = False
    
    total_sales_all = sum(float(inv.grand_total or 0.0) for inv in valid_invs)
    total_bookings_all = len(valid_invs)

    # ─────────────────────────────────────────────────────────────
    # 2. Purchases (COGS) & Operating Expenses
    # ─────────────────────────────────────────────────────────────
    purchases_all_rows = cdb.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == company_id,
        PurchaseInvoice.status.notin_(['Void', 'Draft', 'Cancelled'])
    ).all()
    total_purchase_all = sum(float(p.grand_total or 0.0) for p in purchases_all_rows)

    gross_profit_all = total_sales_all - total_purchase_all
    gross_margin_all = round((gross_profit_all / total_sales_all * 100), 1) if total_sales_all > 0 else 0.0

    expenses_all_rows = cdb.query(Expense).filter(Expense.company_id == company_id).all()
    total_expenses_all = sum(float(e.amount or 0.0) for e in expenses_all_rows)
    net_profit_all = gross_profit_all - total_expenses_all
    net_margin_all = round((net_profit_all / total_sales_all * 100), 1) if total_sales_all > 0 else 0.0

    # ─────────────────────────────────────────────────────────────
    # 3. Monthly Buckets for Last 6 Months (3M & 6M Analysis)
    # ─────────────────────────────────────────────────────────────
    import calendar
    months_data = []
    cur_year = today.year
    cur_month = today.month
    cur_day = today.day
    _, cur_max_days = calendar.monthrange(cur_year, cur_month)
    is_full_month = (cur_day >= cur_max_days)

    # Previous month calculations
    prev_month = cur_month - 1
    prev_year = cur_year
    if prev_month == 0:
        prev_month = 12
        prev_year -= 1

    _, prev_max_days = calendar.monthrange(prev_year, prev_month)
    target_prev_day = prev_max_days if is_full_month else min(cur_day, prev_max_days)

    cur_mtd_start = date(cur_year, cur_month, 1)
    cur_mtd_end = today
    prev_mtd_start = date(prev_year, prev_month, 1)
    prev_mtd_end = date(prev_year, prev_month, target_prev_day)

    def _get_inv_date(inv):
        return getattr(inv, 'invoice_date', None) or getattr(inv, 'date', None)

    # Current month MTD invoices (Day 1 to cur_day)
    cur_m_invs = [inv for inv in valid_invs if _get_inv_date(inv) and cur_mtd_start <= _get_inv_date(inv) <= cur_mtd_end]
    cur_m_sales = sum(float(inv.grand_total or 0.0) for inv in cur_m_invs)
    cur_m_bookings = len(cur_m_invs)

    # Previous month comparable MTD invoices (Day 1 to target_prev_day)
    prev_mtd_invs = [inv for inv in valid_invs if _get_inv_date(inv) and prev_mtd_start <= _get_inv_date(inv) <= prev_mtd_end]
    prev_mtd_sales = sum(float(inv.grand_total or 0.0) for inv in prev_mtd_invs)
    prev_mtd_bookings = len(prev_mtd_invs)

    for i in range(5, -1, -1):
        m_offset = cur_month - i
        y_offset = cur_year
        while m_offset <= 0:
            m_offset += 12
            y_offset -= 1
        
        m_start = date(y_offset, m_offset, 1)
        _, m_max_days = calendar.monthrange(y_offset, m_offset)
        
        if i == 0:
            m_end = cur_mtd_end
            m_bucket_invs = cur_m_invs
            m_label = f"{m_start.strftime('%b %Y')} (Day 1-{cur_day})" if not is_full_month else m_start.strftime("%b %Y")
        else:
            m_end = date(y_offset, m_offset, m_max_days)
            m_bucket_invs = [inv for inv in valid_invs if _get_inv_date(inv) and m_start <= _get_inv_date(inv) <= m_end]
            m_label = m_start.strftime("%b %Y")
            
        m_sales = sum(float(inv.grand_total or 0.0) for inv in m_bucket_invs)
        
        # Monthly purchase bills in this window
        m_purch_rows = [p for p in purchases_all_rows if p.date and m_start <= p.date <= m_end]
        m_purchase = sum(float(p.grand_total or 0.0) for p in m_purch_rows)
            
        m_profit = m_sales - m_purchase
        m_margin = round((m_profit / m_sales * 100), 1) if m_sales > 0 else 0.0
        
        months_data.append({
            "month_label": m_label,
            "short_label": m_start.strftime("%b"),
            "start_date": m_start.strftime("%Y-%m-%d"),
            "end_date": m_end.strftime("%Y-%m-%d"),
            "year": y_offset,
            "month": m_offset,
            "bookings": len(m_bucket_invs),
            "sales": round(m_sales, 2),
            "purchase": round(m_purchase, 2),
            "profit": round(m_profit, 2),
            "margin": m_margin,
            "invoices": m_bucket_invs,
        })

    prev_full_month_stats = months_data[-2]
    prev_full_sales = prev_full_month_stats["sales"]
    prev_full_bookings = prev_full_month_stats["bookings"]

    # MoM Growth (Like-for-like date-matched comparison: Current Month Day 1-cur_day vs Previous Month Day 1-target_prev_day)
    mom_sales_growth_pct = 0.0
    if prev_mtd_sales > 0:
        mom_sales_growth_pct = round(((cur_m_sales - prev_mtd_sales) / prev_mtd_sales) * 100, 1)
    elif cur_m_sales > 0:
        mom_sales_growth_pct = 100.0

    mom_booking_growth_pct = 0.0
    if prev_mtd_bookings > 0:
        mom_booking_growth_pct = round(((cur_m_bookings - prev_mtd_bookings) / prev_mtd_bookings) * 100, 1)
    elif cur_m_bookings > 0:
        mom_booking_growth_pct = 100.0

    # 3-Month Summary
    last_3m = months_data[-3:]
    sales_3m = sum(m["sales"] for m in last_3m)
    bookings_3m = sum(m["bookings"] for m in last_3m)
    profit_3m = sum(m["profit"] for m in last_3m)
    avg_sales_3m = round(sales_3m / 3, 2)
    margin_3m = round((profit_3m / sales_3m * 100), 1) if sales_3m > 0 else 0.0

    # 6-Month Summary
    sales_6m = sum(m["sales"] for m in months_data)
    bookings_6m = sum(m["bookings"] for m in months_data)
    profit_6m = sum(m["profit"] for m in months_data)
    avg_sales_6m = round(sales_6m / 6, 2)
    margin_6m = round((profit_6m / sales_6m * 100), 1) if sales_6m > 0 else 0.0

    # ─────────────────────────────────────────────────────────────
    # 4. Client Analysis: Top Clients, Concentration Risk, Surging vs Declining
    # ─────────────────────────────────────────────────────────────
    clients = cdb.query(Client).filter(Client.company_id == company_id, Client.status != "Deleted").all()
    client_map = {c.id: c.name for c in clients}

    client_all_sales = {}
    client_all_counts = {}
    for inv in valid_invs:
        cid = inv.client_id
        if cid:
            client_all_sales[cid] = client_all_sales.get(cid, 0.0) + float(inv.grand_total or 0.0)
            client_all_counts[cid] = client_all_counts.get(cid, 0) + 1

    ranked_clients = sorted(
        [
            {
                "id": cid,
                "name": client_map.get(cid, f"Client #{cid}"),
                "total_sales": round(sales, 2),
                "bookings": client_all_counts.get(cid, 0),
                "share_pct": round((sales / total_sales_all * 100), 1) if total_sales_all > 0 else 0.0,
            }
            for cid, sales in client_all_sales.items()
        ],
        key=lambda x: x["total_sales"],
        reverse=True,
    )

    top_client = ranked_clients[0] if ranked_clients else {"name": "None", "total_sales": 0, "share_pct": 0, "bookings": 0}
    top_3_sales = sum(c["total_sales"] for c in ranked_clients[:3])
    top_3_concentration_pct = round((top_3_sales / total_sales_all * 100), 1) if total_sales_all > 0 else 0.0

    if top_3_concentration_pct > 60:
        concentration_risk_level = "High Concentration Risk"
        concentration_risk_class = "danger"
    elif top_3_concentration_pct > 35:
        concentration_risk_level = "Moderate Concentration"
        concentration_risk_class = "warning"
    else:
        concentration_risk_level = "Well Diversified"
        concentration_risk_class = "success"

    # MoM Client comparison
    cur_m_client_bookings = {}
    cur_m_client_sales = {}
    for inv in cur_m_invs:
        cid = inv.client_id
        if cid:
            cur_m_client_bookings[cid] = cur_m_client_bookings.get(cid, 0) + 1
            cur_m_client_sales[cid] = cur_m_client_sales.get(cid, 0.0) + float(inv.grand_total or 0.0)

    prev_m_client_bookings = {}
    prev_m_client_sales = {}
    for inv in prev_mtd_invs:
        cid = inv.client_id
        if cid:
            prev_m_client_bookings[cid] = prev_m_client_bookings.get(cid, 0) + 1
            prev_m_client_sales[cid] = prev_m_client_sales.get(cid, 0.0) + float(inv.grand_total or 0.0)

    all_active_cids = set(cur_m_client_bookings.keys()) | set(prev_m_client_bookings.keys())
    client_deltas = []
    for cid in all_active_cids:
        cur_b = cur_m_client_bookings.get(cid, 0)
        prev_b = prev_m_client_bookings.get(cid, 0)
        cur_s = cur_m_client_sales.get(cid, 0.0)
        prev_s = prev_m_client_sales.get(cid, 0.0)
        delta_b = cur_b - prev_b
        delta_s = cur_s - prev_s
        client_deltas.append({
            "id": cid,
            "name": client_map.get(cid, f"Client #{cid}"),
            "cur_bookings": cur_b,
            "prev_bookings": prev_b,
            "delta_bookings": delta_b,
            "cur_sales": round(cur_s, 2),
            "prev_sales": round(prev_s, 2),
            "delta_sales": round(delta_s, 2),
        })

    surging_clients = sorted(
        [c for c in client_deltas if c["delta_bookings"] > 0 or c["delta_sales"] > 0],
        key=lambda x: (x["delta_bookings"], x["delta_sales"]),
        reverse=True
    )[:5]

    declining_clients = sorted(
        [c for c in client_deltas if c["delta_bookings"] < 0 or c["delta_sales"] < 0],
        key=lambda x: (x["delta_bookings"], x["delta_sales"])
    )[:5]

    # ─────────────────────────────────────────────────────────────
    # 5. Liquid Funds & Receivables / Payables
    # ─────────────────────────────────────────────────────────────
    cash_in = cdb.query(func.sum(CashTransaction.amount)).filter(
        CashTransaction.company_id == company_id, CashTransaction.type == "income"
    ).scalar() or 0.0
    cash_out = cdb.query(func.sum(CashTransaction.amount)).filter(
        CashTransaction.company_id == company_id, CashTransaction.type == "expense"
    ).scalar() or 0.0
    cash_balance = round(float(cash_in) - float(cash_out), 2)

    bank_accounts = cdb.query(BankAccount).filter(BankAccount.company_id == company_id, BankAccount.status == "Active").all()
    bank_balance = round(sum(float(b.balance or 0.0) for b in bank_accounts), 2)
    total_liquid_funds = round(cash_balance + bank_balance, 2)

    outstanding_map = _compute_outstanding_for_all_clients(cdb, company_id, clients)
    total_receivable = round(sum(bal for bal in outstanding_map.values() if bal > 0), 2)
    debtor_count = sum(1 for bal in outstanding_map.values() if bal > 0)
    
    total_collected = max(0.0, total_sales_all - total_receivable)
    collection_efficiency_pct = round((total_collected / total_sales_all * 100), 1) if total_sales_all > 0 else 100.0

    total_payable = round(sum(float(p.balance or 0.0) for p in purchases_all_rows), 2)

    # ─────────────────────────────────────────────────────────────
    # 6. Category / Revenue Streams & Employee Performance
    # ─────────────────────────────────────────────────────────────
    category_sales = {}
    category_counts = {}
    cat_map = {
        'product_sale': 'Product Sales & Parts',
        'workshop_repair': 'Workshop Repair & Service',
        'logistics': 'Logistics & Freight'
    }
    for inv in valid_invs:
        raw_cat = getattr(inv, 'invoice_category', None)
        if raw_cat:
            c_name = cat_map.get(raw_cat.lower(), raw_cat.replace('_', ' ').title())
        else:
            c_name = (_invoice_country(inv) or "General Sales").strip()
        category_sales[c_name] = category_sales.get(c_name, 0.0) + float(inv.grand_total or 0.0)
        category_counts[c_name] = category_counts.get(c_name, 0) + 1

    top_category = "N/A"
    top_category_sales = 0.0
    top_category_bookings = 0
    if category_sales:
        top_c_tuple = max(category_sales.items(), key=lambda x: x[1])
        top_category = top_c_tuple[0]
        top_category_sales = round(top_c_tuple[1], 2)
        top_category_bookings = category_counts.get(top_category, 0)

    emp_sales = {}
    emp_counts = {}
    for inv in valid_invs:
        creator = (inv.created_by or "Admin").strip()
        emp_sales[creator] = emp_sales.get(creator, 0.0) + float(inv.grand_total or 0.0)
        emp_counts[creator] = emp_counts.get(creator, 0) + 1

    top_employee = "N/A"
    top_employee_sales = 0.0
    top_employee_bookings = 0
    if emp_sales:
        top_emp_tuple = max(emp_sales.items(), key=lambda x: x[1])
        top_employee = top_emp_tuple[0]
        top_employee_sales = round(top_emp_tuple[1], 2)
        top_employee_bookings = emp_counts.get(top_employee, 0)

    # ─────────────────────────────────────────────────────────────
    # 7. Cancellation / Void Rate
    # ─────────────────────────────────────────────────────────────
    if is_customer_invoice_model:
        all_raw_invoices = cdb.query(CustomerInvoice).filter(CustomerInvoice.company_id == company_id).all()
    else:
        all_raw_invoices = cdb.query(Invoice).filter(Invoice.company_id == company_id).all()
    total_raw_count = len(all_raw_invoices)
    void_cancelled_count = sum(1 for inv in all_raw_invoices if inv.status in ['Cancelled', 'Void'])
    cancellation_rate_pct = round((void_cancelled_count / total_raw_count * 100), 1) if total_raw_count > 0 else 0.0

    # ─────────────────────────────────────────────────────────────
    # 8. GST Position (Output vs Input Tax)
    # ─────────────────────────────────────────────────────────────
    output_gst = round(sum(float(inv.tax_amount or 0.0) for inv in valid_invs), 2)
    input_gst = round(sum(float(p.tax_amount or 0.0) for p in purchases_all_rows), 2)
    net_gst_liability = round(output_gst - input_gst, 2)

    # ─────────────────────────────────────────────────────────────
    # 9. Health Score (0 to 100)
    # ─────────────────────────────────────────────────────────────
    health_score = 70
    if gross_margin_all >= 35:
        health_score += 10
    elif gross_margin_all < 15:
        health_score -= 10

    if mom_sales_growth_pct > 0:
        health_score += 10
    elif mom_sales_growth_pct < -15:
        health_score -= 10

    if collection_efficiency_pct >= 85:
        health_score += 10
    elif collection_efficiency_pct < 60:
        health_score -= 15

    if top_3_concentration_pct > 65:
        health_score -= 10
    elif top_3_concentration_pct < 40:
        health_score += 5

    health_score = max(10, min(100, health_score))

    # ─────────────────────────────────────────────────────────────
    # 10. AI Strategic Action Recommendations
    # ─────────────────────────────────────────────────────────────
    recommendations = []
    
    if total_receivable > 0.3 * total_sales_all:
        recommendations.append({
            "type": "warning",
            "title": "High Outstanding Debtors",
            "desc": f"Outstanding client receivables stand at ₹{total_receivable:,.2f} ({100 - collection_efficiency_pct:.1f}% uncollected). Prioritize collections with top {debtor_count} debtor accounts to maximize liquid funds."
        })
    elif collection_efficiency_pct >= 85:
        recommendations.append({
            "type": "success",
            "title": "Healthy Collection Efficiency",
            "desc": f"Your debtor collection efficiency is strong at {collection_efficiency_pct}%. Maintain automated reminders and milestone billing."
        })

    if declining_clients:
        top_churn = declining_clients[0]
        window_txt = f"in first {cur_day} days of last month" if not is_full_month else "last month"
        recommendations.append({
            "type": "danger",
            "title": "Client Retention Alert",
            "desc": f"Client '{top_churn['name']}' volume dropped from {top_churn['prev_bookings']} orders ({window_txt}) down to {top_churn['cur_bookings']} this month. Schedule an account check-in to protect recurring business."
        })

    if top_3_concentration_pct > 50:
        recommendations.append({
            "type": "warning",
            "title": "Client Revenue Diversification",
            "desc": f"Top 3 clients generate {top_3_concentration_pct}% of total sales. Expand outreach across your CRM pipeline to balance customer revenue risk."
        })
    else:
        recommendations.append({
            "type": "success",
            "title": "Solid Revenue Diversification",
            "desc": f"Revenue is well balanced across accounts with the top 3 clients contributing only {top_3_concentration_pct}% of sales."
        })

    if gross_margin_all < 25:
        recommendations.append({
            "type": "danger",
            "title": "Direct Cost & Parts Margin Squeeze",
            "desc": f"Gross profit margin is {gross_margin_all}%. Audit supplier component pricing and workshop labor markups to target 30%+ gross margin."
        })
    else:
        recommendations.append({
            "type": "success",
            "title": "Robust Gross Profit Margin",
            "desc": f"Gross profit margin is running strong at {gross_margin_all}%, providing solid coverage for operating overheads."
        })

    return {
        "status": "success",
        "generated_at": today.strftime("%d %b %Y"),
        "health_score": health_score,
        "points": {
            "total_sales_all": round(total_sales_all, 2),
            "total_bookings_all": total_bookings_all,
            "cur_day": cur_day,
            "target_prev_day": target_prev_day,
            "is_full_month": is_full_month,
            "cur_month_sales": round(cur_m_sales, 2),
            "cur_month_bookings": cur_m_bookings,
            "prev_month_sales": round(prev_mtd_sales, 2),
            "prev_month_bookings": prev_mtd_bookings,
            "prev_full_month_sales": round(prev_full_sales, 2),
            "prev_full_month_bookings": prev_full_bookings,
            "mom_sales_growth_pct": mom_sales_growth_pct,
            "mom_booking_growth_pct": mom_booking_growth_pct,
            
            "sales_3m": round(sales_3m, 2),
            "bookings_3m": bookings_3m,
            "avg_monthly_sales_3m": avg_sales_3m,
            "margin_3m": margin_3m,
            "sales_6m": round(sales_6m, 2),
            "bookings_6m": bookings_6m,
            "avg_monthly_sales_6m": avg_sales_6m,
            "margin_6m": margin_6m,
            "health_score": health_score,
            "monthly_history": [
                {
                    "label": m["month_label"],
                    "short": m["short_label"],
                    "sales": m["sales"],
                    "purchase": m["purchase"],
                    "bookings": m["bookings"],
                    "profit": m["profit"],
                    "margin": m["margin"],
                }
                for m in months_data
            ],

            "total_purchase_all": round(total_purchase_all, 2),
            "gross_profit_all": round(gross_profit_all, 2),
            "gross_margin_all": gross_margin_all,
            "total_expenses_all": round(total_expenses_all, 2),
            "net_profit_all": round(net_profit_all, 2),
            "net_margin_all": net_margin_all,

            "cash_balance": cash_balance,
            "bank_balance": bank_balance,
            "total_liquid_funds": total_liquid_funds,
            "total_receivable": total_receivable,
            "debtor_count": debtor_count,
            "collection_efficiency_pct": collection_efficiency_pct,
            "total_payable": total_payable,

            "top_client": top_client,
            "top_3_concentration_pct": top_3_concentration_pct,
            "concentration_risk_level": concentration_risk_level,
            "concentration_risk_class": concentration_risk_class,
            "surging_clients": surging_clients,
            "declining_clients": declining_clients,

            "top_country": top_category,
            "top_country_sales": top_category_sales,
            "top_country_bookings": top_category_bookings,
            "top_category": top_category,
            "top_category_sales": top_category_sales,
            "top_category_bookings": top_category_bookings,
            "top_employee": top_employee,
            "top_employee_sales": top_employee_sales,
            "top_employee_bookings": top_employee_bookings,
            "cancellation_rate_pct": cancellation_rate_pct,
            "output_gst": output_gst,
            "input_gst": input_gst,
            "net_gst_liability": net_gst_liability,
        },
        "recommendations": recommendations,
    }


def get_company_plan_status(company_id: str) -> Dict[str, Any]:
    """Retrieve the company's active subscription plan details from the platform DB."""
    try:
        from platform_models import Company, SubscriptionPlan
        company = Company.query.filter_by(company_id=company_id).first()
    except Exception:
        company = None

    if not company:
        return {
            "intent": "company_plan_status",
            "found": False,
            "company_id": company_id,
        }

    plan_name = "Standard Plan"
    max_users = "Unlimited"
    max_companies = "1"
    features = ""

    if getattr(company, "plan_obj", None):
        plan_name = company.plan_obj.name or getattr(company, "subscription_plan", "") or "Active Plan"
        max_users = company.plan_obj.max_users
        max_companies = company.plan_obj.max_companies
        features = company.plan_obj.features or ""
    elif getattr(company, "subscription_plan", None):
        try:
            from platform_models import SubscriptionPlan
            plan = SubscriptionPlan.query.filter_by(id=company.subscription_plan).first()
            if plan:
                plan_name = plan.name
                max_users = plan.max_users
                max_companies = plan.max_companies
                features = plan.features or ""
            else:
                plan_name = str(company.subscription_plan).capitalize()
        except Exception:
            plan_name = str(company.subscription_plan).capitalize()

    # User count from customer DB
    active_users = 0
    total_users = 0
    try:
        cdb = get_customer_session(company_id)
        users = cdb.query(CompanyUser).filter_by(company_id=company_id).all()
        active_users = sum(1 for u in users if u.is_active)
        total_users = len(users)
    except Exception:
        pass

    start_str = company.subscription_start.strftime('%d %b %Y') if getattr(company, "subscription_start", None) else "N/A"
    end_str = company.subscription_end.strftime('%d %b %Y') if getattr(company, "subscription_end", None) else "Lifetime / Active"
    duration = str(getattr(company, "plan_duration", "1_year") or "1_year").replace("_", " ").title()

    return {
        "intent": "company_plan_status",
        "found": True,
        "company_id": company_id,
        "company_name": company.company_name,
        "plan_name": plan_name,
        "plan_duration": duration,
        "subscription_start": start_str,
        "subscription_end": end_str,
        "max_users": max_users,
        "max_companies": max_companies,
        "active_users": active_users,
        "total_users": total_users,
        "features": features,
    }


def get_employee_access_guide(company_id: str) -> Dict[str, Any]:
    """Step-by-step guidance on giving access to employees, adding users, and managing role permissions."""
    active_users = 0
    total_users = 0
    roles_summary = {}
    try:
        cdb = get_customer_session(company_id)
        users = cdb.query(CompanyUser).filter_by(company_id=company_id).all()
        active_users = sum(1 for u in users if u.is_active)
        total_users = len(users)
        for u in users:
            r = (u.role or "employee").lower()
            roles_summary[r] = roles_summary.get(r, 0) + 1
    except Exception:
        pass

    return {
        "intent": "employee_access_guide",
        "company_id": company_id,
        "active_users": active_users,
        "total_users": total_users,
        "roles_summary": roles_summary,
    }


def get_change_password_guide(company_id: str) -> Dict[str, Any]:
    """Step-by-step guidance on changing own password or resetting employee passwords."""
    return {
        "intent": "change_password_guide",
        "company_id": company_id,
    }


def get_upgrade_plan_guide(company_id: str) -> Dict[str, Any]:
    """Step-by-step guidance on upgrading subscription plans and pricing."""
    return {
        "intent": "upgrade_plan_guide",
        "company_id": company_id,
    }


def get_company_settings_guide(company_id: str) -> Dict[str, Any]:
    """Step-by-step guidance on configuring company settings, GSTIN, invoice prefix, logo, and terms."""
    return {
        "intent": "company_settings_guide",
        "company_id": company_id,
    }


def get_how_to_workflow_guide(company_id: str, topic: str = "general") -> Dict[str, Any]:
    """Step-by-step operations guides for major ERP workflows."""
    return {
        "intent": "how_to_workflow_guide",
        "topic": topic,
        "company_id": company_id,
    }




def get_receivables_intelligence(cdb, company_id: str, from_date, to_date, prev_from, prev_to, filters=None) -> Dict[str, Any]:
    """
    Computes comprehensive receivables & outstanding intelligence responding to
    date ranges, client, employee, country, and category filters.
    
    Includes:
    1. total_live_outstanding: Current overall (or per-filtered client) live balance.
    2. debtors_count: Number of clients with positive outstanding balance.
    3. period_billed: Total invoiced within the selected date window.
    4. period_collected: Amount collected against period invoices.
    5. period_pending_added: Unpaid balance from invoices generated within selected date window.
    6. prev_period_pending_added: Unpaid balance from invoices in prior date window.
    7. outstanding_change: Net difference in pending added (period - prev_period).
    8. outstanding_change_pct: % growth in pending added.
    9. collection_rate: % of period invoices collected.
    10. top_party_name: Client with highest live outstanding (name & amount).
    11. top_party_amount: Client highest live balance.
    12. top_debtors: Top 5 debtor clients with their live balance.
    """
    def _inv_dest_country(inv):
        if not inv.terms:
            return None
        try:
            meta = json.loads(inv.terms) if isinstance(inv.terms, str) else inv.terms
            dest = meta.get('destination')
            return dest.strip() if dest else None
        except Exception:
            return None

    def _get_filtered_invoices(d_from, d_to):
        q_ci = cdb.query(CustomerInvoice).filter(
            CustomerInvoice.company_id == company_id,
            CustomerInvoice.invoice_date >= d_from,
            CustomerInvoice.invoice_date <= d_to,
            CustomerInvoice.status.notin_(['Void', 'Draft', 'Cancelled'])
        )
        if filters:
            if getattr(filters, 'client_id', None):
                q_ci = q_ci.filter(CustomerInvoice.client_id == filters.client_id)
            if getattr(filters, 'employee_id', None):
                q_ci = q_ci.filter(CustomerInvoice.created_by == filters.employee_id)
            if getattr(filters, 'category', None):
                q_ci = q_ci.filter(CustomerInvoice.invoice_category == filters.category)
        ci_invs = q_ci.all()
        if ci_invs:
            return ci_invs

        q = cdb.query(Invoice).filter(
            Invoice.company_id == company_id,
            Invoice.date >= d_from,
            Invoice.date <= d_to,
            Invoice.status.notin_(['Void', 'Draft', 'Cancelled'])
        )
        if filters:
            if getattr(filters, 'client_id', None):
                q = q.filter(Invoice.client_id == filters.client_id)
            if getattr(filters, 'employee_id', None):
                q = q.filter(Invoice.created_by == filters.employee_id)
        invoices = q.all()
        if filters and getattr(filters, 'country', None):
            c_filter = str(filters.country).strip().lower()
            invoices = [inv for inv in invoices if (_inv_dest_country(inv) or '').strip().lower() == c_filter]
        return invoices

    # 1. Current period invoices
    cur_invoices = _get_filtered_invoices(from_date, to_date)
    period_billed = sum(float(inv.grand_total or 0) for inv in cur_invoices)
    period_pending_added = sum(max(0.0, float(inv.balance if inv.balance is not None else (float(inv.grand_total or 0) - float(inv.paid_amount or 0)))) for inv in cur_invoices)
    period_collected = sum(float(inv.paid_amount or 0) for inv in cur_invoices)
    if period_collected == 0 and period_billed > 0 and period_pending_added < period_billed:
        period_collected = period_billed - period_pending_added

    # 2. Previous period invoices
    prev_invoices = _get_filtered_invoices(prev_from, prev_to)
    prev_period_pending_added = sum(max(0.0, float(inv.balance if inv.balance is not None else (float(inv.grand_total or 0) - float(inv.paid_amount or 0)))) for inv in prev_invoices)
    prev_period_billed = sum(float(inv.grand_total or 0) for inv in prev_invoices)
    prev_period_collected = sum(float(inv.paid_amount or 0) for inv in prev_invoices)
    if prev_period_collected == 0 and prev_period_billed > 0 and prev_period_pending_added < prev_period_billed:
        prev_period_collected = prev_period_billed - prev_period_pending_added

    # 3. Growth / change in pending added
    outstanding_change = round(period_pending_added - prev_period_pending_added, 2)
    if prev_period_pending_added > 0:
        outstanding_change_pct = round(((period_pending_added - prev_period_pending_added) / prev_period_pending_added) * 100, 1)
    elif period_pending_added > 0:
        outstanding_change_pct = 100.0
    else:
        outstanding_change_pct = 0.0

    # 4. Period collection rate
    collection_rate = round((period_collected / period_billed * 100), 1) if period_billed > 0 else 0.0

    # 5. Live ledger total & debtor ranking
    all_clients = cdb.query(Client).filter(
        Client.company_id == company_id,
        Client.status != "Deleted",
        ~Client.client_type.in_(["Supplier", "Cash-Only"]),
    ).all()
    
    balances_by_id = _compute_outstanding_for_all_clients(cdb, company_id, all_clients)
    client_name_by_id = {c.id: c.name for c in all_clients}

    selected_client_id = getattr(filters, 'client_id', None) if filters else None
    if selected_client_id:
        try:
            sel_cid = int(selected_client_id)
            total_live_outstanding = round(balances_by_id.get(sel_cid, 0.0), 2)
            top_party_name = client_name_by_id.get(sel_cid, f'Client #{sel_cid}')
            top_party_amount = total_live_outstanding
            debtors_count = 1 if total_live_outstanding > 0 else 0
            top_debtors = [{"id": sel_cid, "name": top_party_name, "amount": top_party_amount}]
        except (ValueError, TypeError):
            total_live_outstanding = 0.0
            top_party_name = 'None'
            top_party_amount = 0.0
            debtors_count = 0
            top_debtors = []
    else:
        total_live_outstanding = round(sum(b for b in balances_by_id.values() if b > 0), 2)
        sorted_debtors = sorted(
            [{"id": cid, "name": client_name_by_id.get(cid, f"Client #{cid}"), "amount": round(bal, 2)} 
             for cid, bal in balances_by_id.items() if bal > 0],
            key=lambda x: x["amount"],
            reverse=True
        )
        debtors_count = len(sorted_debtors)
        if sorted_debtors:
            top_party_name = sorted_debtors[0]["name"]
            top_party_amount = sorted_debtors[0]["amount"]
            top_debtors = sorted_debtors[:5]
        else:
            top_party_name = "None"
            top_party_amount = 0.0
            top_debtors = []

    return {
        "total_live_outstanding": total_live_outstanding,
        "debtors_count": debtors_count,
        "period_billed": round(period_billed, 2),
        "period_collected": round(period_collected, 2),
        "period_pending_added": round(period_pending_added, 2),
        "prev_period_pending_added": round(prev_period_pending_added, 2),
        "outstanding_change": outstanding_change,
        "outstanding_change_pct": outstanding_change_pct,
        "collection_rate": collection_rate,
        "top_party_name": top_party_name,
        "top_party_amount": round(top_party_amount, 2),
        "top_debtors": top_debtors,
    }




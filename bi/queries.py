from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func

from customer_models import (
    Client,
    CompanyUser,
    CustomerInvoice,
    CustomerInvoiceItem,
    Expense,
    PurchaseInvoice,
    PurchaseInvoiceItem,
    StockItem,
    Supplier,
)


EXCLUDED_STATUSES = ("draft", "void", "cancelled", "canceled")
ZERO = Decimal("0")


def money(value) -> Decimal:
    return Decimal(str(value or 0))


def base_amount(row, base_field: str, native_field: str, base_currency: str) -> Decimal:
    """Return a row amount in company base currency.

    New records already persist base_* values. Older records may contain zero
    in those fields, so a foreign-currency row falls back to native *
    exchange_rate. Base-currency rows use the native amount directly.
    """
    native = money(getattr(row, native_field, 0))
    currency = (getattr(row, "currency", None) or base_currency).upper()
    if currency == (base_currency or "INR").upper():
        return native

    stored_base = money(getattr(row, base_field, 0))
    if stored_base != ZERO or native == ZERO:
        return stored_base

    rate = money(getattr(row, "exchange_rate", 1) or 1)
    if rate <= ZERO:
        rate = Decimal("1")
    return native * rate


def base_balance(row, base_currency: str, purchase: bool = False) -> Decimal:
    if purchase:
        stored = money(getattr(row, "base_balance", 0))
        native = money(getattr(row, "balance", 0))
        currency = (getattr(row, "currency", None) or base_currency).upper()
        if currency != (base_currency or "INR").upper() and (stored != ZERO or native == ZERO):
            return stored
    native = money(getattr(row, "balance", 0))
    currency = (getattr(row, "currency", None) or base_currency).upper()
    if currency == (base_currency or "INR").upper():
        return native
    rate = money(getattr(row, "exchange_rate", 1) or 1)
    if rate <= ZERO:
        rate = Decimal("1")
    return native * rate


def employee_aliases(cdb, company_id: str, employee_id: str | None) -> set[str]:
    if not employee_id:
        return set()
    aliases = {employee_id}
    row = cdb.query(CompanyUser).filter(
        CompanyUser.company_id == company_id,
        ((CompanyUser.email == employee_id) | (CompanyUser.user_id == employee_id))
    ).first()
    if row:
        if row.email:
            aliases.add(row.email)
        if row.user_id:
            aliases.add(row.user_id)
        if row.full_name:
            aliases.add(row.full_name)
    return aliases


def sales_query(cdb, filters, start=None, end=None, include_product_filter=True):
    q = cdb.query(CustomerInvoice).filter(
        CustomerInvoice.company_id == filters.company_id,
        func.lower(func.trim(CustomerInvoice.status)).notin_(EXCLUDED_STATUSES),
    )
    if start is not None:
        q = q.filter(CustomerInvoice.invoice_date >= start)
    if end is not None:
        q = q.filter(CustomerInvoice.invoice_date <= end)
    if filters.client_id:
        q = q.filter(CustomerInvoice.client_id == filters.client_id)
    aliases = employee_aliases(cdb, filters.company_id, filters.employee_id)
    if aliases:
        q = q.filter(CustomerInvoice.created_by.in_(aliases))
    if filters.country:
        q = q.join(Client, Client.id == CustomerInvoice.client_id).filter(
            func.lower(func.trim(Client.country)) == filters.country.strip().lower()
        )
    if include_product_filter and filters.product_category:
        q = q.join(
            CustomerInvoiceItem,
            CustomerInvoiceItem.customer_invoice_id == CustomerInvoice.id,
        ).join(
            StockItem,
            StockItem.id == CustomerInvoiceItem.stock_item_id,
        ).filter(
            func.lower(func.trim(StockItem.category)) == filters.product_category.strip().lower()
        ).distinct()
    return q


def purchase_query(cdb, filters, start=None, end=None, include_product_filter=True):
    q = cdb.query(PurchaseInvoice).filter(
        PurchaseInvoice.company_id == filters.company_id,
        func.lower(func.trim(PurchaseInvoice.status)).notin_(EXCLUDED_STATUSES),
    )
    if start is not None:
        q = q.filter(PurchaseInvoice.date >= start)
    if end is not None:
        q = q.filter(PurchaseInvoice.date <= end)
    if filters.supplier_id:
        q = q.filter(PurchaseInvoice.supplier_id == filters.supplier_id)
    aliases = employee_aliases(cdb, filters.company_id, filters.employee_id)
    if aliases:
        q = q.filter(PurchaseInvoice.created_by.in_(aliases))
    if filters.country:
        q = q.join(Supplier, Supplier.id == PurchaseInvoice.supplier_id).filter(
            func.lower(func.trim(Supplier.country)) == filters.country.strip().lower()
        )
    if include_product_filter and filters.product_category:
        q = q.join(
            PurchaseInvoiceItem,
            PurchaseInvoiceItem.purchase_invoice_id == PurchaseInvoice.id,
        ).join(
            StockItem,
            StockItem.id == PurchaseInvoiceItem.stock_item_id,
        ).filter(
            func.lower(func.trim(StockItem.category)) == filters.product_category.strip().lower()
        ).distinct()
    return q


def expense_query(cdb, filters, start=None, end=None):
    q = cdb.query(Expense).filter(Expense.company_id == filters.company_id)
    if start is not None:
        q = q.filter(Expense.date >= start)
    if end is not None:
        q = q.filter(Expense.date <= end)
    if filters.expense_category:
        q = q.filter(func.lower(func.trim(Expense.category)) == filters.expense_category.strip().lower())
    aliases = employee_aliases(cdb, filters.company_id, filters.employee_id)
    if aliases:
        q = q.filter(Expense.created_by.in_(aliases))
    return q


def stock_query(cdb, filters):
    q = cdb.query(StockItem).filter(StockItem.company_id == filters.company_id)
    if filters.product_category:
        q = q.filter(func.lower(func.trim(StockItem.category)) == filters.product_category.strip().lower())
    return q

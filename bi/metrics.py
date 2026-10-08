from __future__ import annotations

from decimal import Decimal

from customer_models import Client, CompanyUser, StockItem, Supplier

from .queries import base_amount, base_balance, expense_query, money, purchase_query, sales_query, stock_query


ZERO = Decimal("0")


def pct_change(current, previous):
    current = money(current)
    previous = money(previous)
    if previous == ZERO:
        return None
    return float(((current - previous) / abs(previous)) * Decimal("100"))


def _round(value, digits=2):
    if value is None:
        return None
    return round(float(value), digits)


def _allowed(can, *candidates):
    return any(can(module, "view") for module in candidates)


def period_metrics(cdb, filters, base_currency: str, can) -> dict:
    result = {}

    sales_allowed = _allowed(can, "customer_invoices", "invoices")
    purchase_allowed = _allowed(can, "purchase")
    expense_allowed = _allowed(can, "expenses")

    sales = []
    if sales_allowed:
        sales = sales_query(cdb, filters, filters.from_date, filters.to_date).all()
        billed_sales = sum((base_amount(r, "base_grand_total", "grand_total", base_currency) for r in sales), ZERO)
        net_sales = sum((base_amount(r, "base_subtotal", "subtotal", base_currency) for r in sales), ZERO)
        sales_tax = sum((base_amount(r, "base_tax_amount", "tax_amount", base_currency) for r in sales), ZERO)
        count = len(sales)
        result.update({
            "billed_sales": billed_sales,
            "net_sales": net_sales,
            "sales_tax": sales_tax,
            "sales_invoices": count,
            "average_invoice_value": billed_sales / count if count else ZERO,
            "active_customers": len({r.client_id for r in sales if r.client_id is not None}),
        })

    purchases = []
    if purchase_allowed:
        purchases = purchase_query(cdb, filters, filters.from_date, filters.to_date).all()
        result.update({
            "purchase_total": sum((base_amount(r, "base_grand_total", "grand_total", base_currency) for r in purchases), ZERO),
            "purchase_cost": sum((base_amount(r, "base_subtotal", "subtotal", base_currency) for r in purchases), ZERO),
            "purchase_tax": sum((base_amount(r, "base_tax_amount", "tax_amount", base_currency) for r in purchases), ZERO),
            "purchase_invoices": len(purchases),
        })

    if expense_allowed:
        expenses = expense_query(cdb, filters, filters.from_date, filters.to_date).all()
        result["expenses"] = sum((money(r.amount) for r in expenses), ZERO)

    # This is intentionally labelled as an estimate. Period purchases are not
    # the same accounting concept as matched COGS.
    if "net_sales" in result and "purchase_cost" in result:
        result["gross_profit_estimate"] = result["net_sales"] - result["purchase_cost"]
        if "expenses" in result:
            result["net_profit_estimate"] = result["gross_profit_estimate"] - result["expenses"]
            result["net_margin_estimate"] = (
                result["net_profit_estimate"] / result["net_sales"] * Decimal("100")
                if result["net_sales"] else ZERO
            )

    return result


def live_metrics(cdb, filters, base_currency: str, can, today) -> dict:
    result = {}
    sales_allowed = _allowed(can, "customer_invoices", "invoices")
    purchase_allowed = _allowed(can, "purchase")
    stock_allowed = _allowed(can, "stock")

    if sales_allowed:
        # Product category is deliberately excluded for invoice-level balances:
        # an invoice can contain multiple categories and its balance cannot be
        # safely allocated to one category without payment allocation data.
        rows = sales_query(cdb, filters, end=today, include_product_filter=False).all()
        result["receivables"] = sum((max(base_balance(r, base_currency, purchase=False), ZERO) for r in rows), ZERO)

    if purchase_allowed:
        rows = purchase_query(cdb, filters, end=today, include_product_filter=False).all()
        result["payables"] = sum((max(base_balance(r, base_currency, purchase=True), ZERO) for r in rows), ZERO)

    if stock_allowed:
        items = stock_query(cdb, filters).all()
        inventory_value = ZERO
        total_qty = ZERO
        low_stock = 0
        for item in items:
            qty = money(item.quantity)
            total_qty += qty
            cost = money(
                item.avg_purchase_rate
                or item.last_purchase_rate
                or item.purchase_rate
                or item.unit_price
                or 0
            )
            inventory_value += qty * cost
            reorder = money(item.reorder_level)
            if reorder > ZERO and qty <= reorder:
                low_stock += 1
        result.update({
            "inventory_value": inventory_value,
            "inventory_units": total_qty,
            "low_stock_items": low_stock,
        })

    if can("clients", "view"):
        result["total_customers"] = cdb.query(Client).filter_by(company_id=filters.company_id).count()
    if can("suppliers", "view"):
        result["total_suppliers"] = cdb.query(Supplier).filter_by(company_id=filters.company_id).count()

    return result


def serialise_metrics(metrics: dict) -> dict:
    out = {}
    for key, value in metrics.items():
        if isinstance(value, Decimal):
            out[key] = _round(value)
        elif isinstance(value, float):
            out[key] = round(value, 2)
        else:
            out[key] = value
    return out


def comparisons(current: dict, previous: dict) -> dict:
    result = {}
    for key, value in current.items():
        if key not in previous:
            continue
        if isinstance(value, (Decimal, int, float)) and isinstance(previous[key], (Decimal, int, float)):
            result[key] = {
                "current": _round(value),
                "previous": _round(previous[key]),
                "change_pct": None if pct_change(value, previous[key]) is None else round(pct_change(value, previous[key]), 2),
            }
    return result

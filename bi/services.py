from __future__ import annotations

from sqlalchemy import func
from collections import defaultdict
from decimal import Decimal

from customer_models import Client, CompanyUser, Expense, StockItem, Supplier

from .catalog import metric_catalog
from .filters import BIFilters, previous_period
from .metrics import comparisons, live_metrics, period_metrics, serialise_metrics
from .queries import base_amount, expense_query, purchase_query, sales_query


def _can_sales(can):
    return can("customer_invoices", "view") or can("invoices", "view")


def filter_options(cdb, company_id: str, can, base_currency: str) -> dict:
    employees = cdb.query(CompanyUser).filter(
        CompanyUser.company_id == company_id,
        CompanyUser.is_active == True,
        CompanyUser.role != "owner",
    ).order_by(CompanyUser.full_name).all()

    clients = []
    if can("clients", "view") or _can_sales(can):
        clients = cdb.query(Client).filter_by(company_id=company_id).order_by(Client.name).all()

    suppliers = []
    if can("suppliers", "view") or can("purchase", "view"):
        suppliers = cdb.query(Supplier).filter_by(company_id=company_id).order_by(Supplier.name).all()

    countries = sorted({
        (x.country or "").strip()
        for x in [*clients, *suppliers]
        if (x.country or "").strip()
    })

    product_categories = []
    if can("stock", "view") or _can_sales(can) or can("purchase", "view"):
        product_categories = [
            row[0] for row in cdb.query(StockItem.category).filter(
                StockItem.company_id == company_id,
                StockItem.category.isnot(None),
                func.trim(StockItem.category) != "",
            ).distinct().order_by(StockItem.category).all()
        ]

    expense_categories = []
    if can("expenses", "view"):
        expense_categories = [
            row[0] for row in cdb.query(Expense.category).filter(
                Expense.company_id == company_id,
                Expense.category.isnot(None),
                func.trim(Expense.category) != "",
            ).distinct().order_by(Expense.category).all()
        ]

    return {
        "base_currency": base_currency,
        "employees": [{"id": e.email or e.user_id, "user_id": e.user_id, "name": e.full_name} for e in employees],
        "clients": [{"id": c.id, "name": c.name, "country": c.country or ""} for c in clients],
        "suppliers": [{"id": s.id, "name": s.name, "country": s.country or ""} for s in suppliers],
        "countries": countries,
        "product_categories": product_categories,
        "expense_categories": expense_categories,
        "capabilities": {
            "canonical_sales_source": "customer_invoices",
            "canonical_purchase_source": "purchase_invoices",
            "multi_currency_base_normalisation": True,
            "branch_filter": False,
            "data_warehouse": True,
            "predictive_analytics": True,
            "scenario_planning": False,
            "custom_dashboard_builder": True,
            "department_dashboards": True,
            "drill_down": True,
        },
    }


def overview(cdb, filters: BIFilters, can, base_currency: str, today) -> dict:
    current = period_metrics(cdb, filters, base_currency, can)
    prev_from, prev_to = previous_period(filters)
    previous_filters = BIFilters(
        company_id=filters.company_id,
        from_date=prev_from,
        to_date=prev_to,
        employee_id=filters.employee_id,
        country=filters.country,
        client_id=filters.client_id,
        supplier_id=filters.supplier_id,
        product_category=filters.product_category,
        expense_category=filters.expense_category,
    )
    previous = period_metrics(cdb, previous_filters, base_currency, can)
    live = live_metrics(cdb, filters, base_currency, can, today)

    warnings = [
        "Profit metrics are estimates because the current schema does not store matched historical COGS per sales line.",
        "Branch filtering is disabled until canonical sales and purchase transactions store branch_id.",
    ]
    if filters.product_category:
        warnings.append(
            "Product category is not applied to receivables/payables because invoice-level outstanding cannot be allocated safely across mixed-category invoices."
        )

    return {
        "version": "1.0",
        "base_currency": base_currency,
        "filters": filters.to_dict(),
        "previous_period": {"from_date": prev_from.isoformat(), "to_date": prev_to.isoformat()},
        "period": serialise_metrics(current),
        "live": serialise_metrics(live),
        "comparisons": comparisons(current, previous),
        "warnings": warnings,
        "sources": {
            "sales": "customer_invoices",
            "purchases": "purchase_invoices",
            "inventory": "stock_items",
            "expenses": "expenses",
        },
    }


def catalog_payload() -> dict:
    return {
        "version": "1.0",
        "metrics": metric_catalog(),
        "notes": [
            "The metric catalogue is the contract future standard dashboards and the custom dashboard builder will consume.",
            "Each metric declares the filters that are safe to apply to it.",
        ],
    }


def executive(cdb, filters: BIFilters, can, base_currency: str, today) -> dict:
    """Executive presentation data, using the same canonical query and metric rules as v1."""
    result = overview(cdb, filters, can, base_currency, today)
    months = {}

    def bucket(day):
        key = day.strftime("%Y-%m")
        return months.setdefault(key, {"month": key, "sales": 0.0, "purchases": 0.0, "expenses": 0.0})

    customers = defaultdict(Decimal)
    countries = defaultdict(Decimal)
    if _can_sales(can):
        clients = {c.id: c for c in cdb.query(Client).filter_by(company_id=filters.company_id).all()}
        for row in sales_query(cdb, filters, filters.from_date, filters.to_date).all():
            amount = base_amount(row, "base_subtotal", "subtotal", base_currency)
            bucket(row.invoice_date)["sales"] += float(amount)
            client = clients.get(row.client_id)
            if client:
                customers[client.name or "Unnamed customer"] += amount
                countries[(client.country or "Unspecified").strip() or "Unspecified"] += amount
    if can("purchase", "view"):
        for row in purchase_query(cdb, filters, filters.from_date, filters.to_date).all():
            bucket(row.date)["purchases"] += float(base_amount(row, "base_subtotal", "subtotal", base_currency))
    if can("expenses", "view"):
        for row in expense_query(cdb, filters, filters.from_date, filters.to_date).all():
            bucket(row.date)["expenses"] += float(row.amount or 0)

    # A selected month with no transactions still belongs on the axis.
    cursor = filters.from_date.replace(day=1)
    end = filters.to_date.strftime("%Y-%m")
    while cursor.strftime("%Y-%m") <= end:
        key = cursor.strftime("%Y-%m")
        months.setdefault(key, {"month": key, "sales": 0.0, "purchases": 0.0, "expenses": 0.0})
        cursor = cursor.replace(year=cursor.year + 1, month=1) if cursor.month == 12 else cursor.replace(month=cursor.month + 1)
    trend = [dict(v, sales=round(v["sales"], 2), purchases=round(v["purchases"], 2),
                  expenses=round(v["expenses"], 2)) for _, v in sorted(months.items())]
    result["trend"] = trend
    result["top_customers"] = [{"name": k, "value": round(float(v), 2)} for k, v in sorted(customers.items(), key=lambda x: -x[1])[:5]]
    result["countries"] = [{"name": k, "value": round(float(v), 2)} for k, v in sorted(countries.items(), key=lambda x: -x[1])[:5]]
    insights = []
    comparison = result["comparisons"].get("net_sales")
    if comparison and comparison["change_pct"] is not None:
        insights.append({"kind": "up" if comparison["change_pct"] >= 0 else "down",
                         "text": f"Net sales changed {comparison['change_pct']:+.1f}% against the preceding equal-length period."})
    low = result["live"].get("low_stock_items")
    if low:
        insights.append({"kind": "warning", "text": f"{low} stock items are at or below their reorder levels."})
    if result["live"].get("receivables", 0) > 0:
        insights.append({"kind": "info", "text": "Receivables are a current balance, not sales within the selected dates."})
    result["insights"] = insights
    return result

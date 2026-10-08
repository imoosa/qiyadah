from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    label: str
    group: str
    value_type: str
    description: str
    source: str
    supported_filters: tuple[str, ...]
    estimate: bool = False

    def to_dict(self) -> dict:
        data = asdict(self)
        data["supported_filters"] = list(self.supported_filters)
        return data


COMMON_SALES_FILTERS = ("from_date", "to_date", "employee_id", "country", "client_id", "product_category")
COMMON_PURCHASE_FILTERS = ("from_date", "to_date", "employee_id", "country", "supplier_id", "product_category")


METRICS = {
    "billed_sales": MetricDefinition(
        "billed_sales", "Total Billed Sales", "sales", "currency",
        "Sales invoice grand total including tax, normalised into the company's base currency.",
        "customer_invoices", COMMON_SALES_FILTERS,
    ),
    "net_sales": MetricDefinition(
        "net_sales", "Net Sales", "sales", "currency",
        "Sales subtotal excluding tax, normalised into the company's base currency.",
        "customer_invoices", COMMON_SALES_FILTERS,
    ),
    "sales_tax": MetricDefinition(
        "sales_tax", "Output Tax", "tax", "currency",
        "Tax charged on canonical sales invoices in the selected period.",
        "customer_invoices", COMMON_SALES_FILTERS,
    ),
    "sales_invoices": MetricDefinition(
        "sales_invoices", "Sales Invoices", "sales", "count",
        "Number of non-draft, non-void canonical sales invoices.",
        "customer_invoices", COMMON_SALES_FILTERS,
    ),
    "average_invoice_value": MetricDefinition(
        "average_invoice_value", "Average Invoice Value", "sales", "currency",
        "Total billed sales divided by canonical sales invoice count.",
        "customer_invoices", COMMON_SALES_FILTERS,
    ),
    "purchase_total": MetricDefinition(
        "purchase_total", "Total Purchases", "purchase", "currency",
        "Purchase invoice grand total including tax, normalised into base currency.",
        "purchase_invoices", COMMON_PURCHASE_FILTERS,
    ),
    "purchase_cost": MetricDefinition(
        "purchase_cost", "Purchases Excluding Tax", "purchase", "currency",
        "Purchase invoice subtotal excluding tax, normalised into base currency.",
        "purchase_invoices", COMMON_PURCHASE_FILTERS,
    ),
    "purchase_tax": MetricDefinition(
        "purchase_tax", "Input Tax", "tax", "currency",
        "Tax recorded on purchase invoices in the selected period.",
        "purchase_invoices", COMMON_PURCHASE_FILTERS,
    ),
    "purchase_invoices": MetricDefinition(
        "purchase_invoices", "Purchase Invoices", "purchase", "count",
        "Number of non-draft, non-void purchase invoices.",
        "purchase_invoices", COMMON_PURCHASE_FILTERS,
    ),
    "expenses": MetricDefinition(
        "expenses", "Operating Expenses", "finance", "currency",
        "Expenses booked in the selected period.",
        "expenses", ("from_date", "to_date", "employee_id", "expense_category"),
    ),
    "gross_profit_estimate": MetricDefinition(
        "gross_profit_estimate", "Gross Profit Estimate", "finance", "currency",
        "Net sales minus period purchases excluding tax. This is not matched historical COGS.",
        "derived", ("from_date", "to_date", "employee_id", "country", "client_id", "supplier_id", "product_category"),
        estimate=True,
    ),
    "net_profit_estimate": MetricDefinition(
        "net_profit_estimate", "Net Profit Estimate", "finance", "currency",
        "Gross profit estimate minus operating expenses. It remains an estimate until historical COGS is captured per sale.",
        "derived", ("from_date", "to_date"), estimate=True,
    ),
    "net_margin_estimate": MetricDefinition(
        "net_margin_estimate", "Net Margin Estimate", "finance", "percentage",
        "Net profit estimate divided by net sales.",
        "derived", ("from_date", "to_date"), estimate=True,
    ),
    "receivables": MetricDefinition(
        "receivables", "Receivables", "finance", "currency",
        "Current open balance on canonical sales invoices, normalised into base currency.",
        "customer_invoices", ("employee_id", "country", "client_id"),
    ),
    "payables": MetricDefinition(
        "payables", "Payables", "finance", "currency",
        "Current open balance on purchase invoices, normalised into base currency.",
        "purchase_invoices", ("employee_id", "country", "supplier_id"),
    ),
    "inventory_value": MetricDefinition(
        "inventory_value", "Inventory Value", "inventory", "currency",
        "Current stock quantity multiplied by the best available purchase cost on the stock master.",
        "stock_items", ("product_category",), estimate=True,
    ),
    "inventory_units": MetricDefinition(
        "inventory_units", "Inventory Quantity", "inventory", "number",
        "Current total stock quantity across stock items.",
        "stock_items", ("product_category",),
    ),
    "low_stock_items": MetricDefinition(
        "low_stock_items", "Low Stock Items", "inventory", "count",
        "Items whose current quantity is at or below their configured reorder level.",
        "stock_items", ("product_category",),
    ),
    "active_customers": MetricDefinition(
        "active_customers", "Active Customers", "customer", "count",
        "Distinct customers with canonical sales invoices in the selected period.",
        "customer_invoices", COMMON_SALES_FILTERS,
    ),
}


def metric_catalog() -> list[dict]:
    return [definition.to_dict() for definition in METRICS.values()]

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


class BIValidationError(ValueError):
    """Raised when a BI request contains an invalid or unsupported filter."""


@dataclass(frozen=True)
class BIFilters:
    company_id: str
    from_date: date
    to_date: date
    employee_id: Optional[str] = None
    country: Optional[str] = None
    client_id: Optional[int] = None
    supplier_id: Optional[int] = None
    product_category: Optional[str] = None
    expense_category: Optional[str] = None
    branch: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "company_id": self.company_id,
            "from_date": self.from_date.isoformat(),
            "to_date": self.to_date.isoformat(),
            "employee_id": self.employee_id,
            "country": self.country,
            "client_id": self.client_id,
            "supplier_id": self.supplier_id,
            "product_category": self.product_category,
            "expense_category": self.expense_category,
            "branch": self.branch,
        }


def _clean(value):
    if value is None:
        return None
    value = str(value).strip()
    if not value or value.lower() == "all":
        return None
    return value


def _positive_int(value, field_name: str):
    value = _clean(value)
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise BIValidationError(f"{field_name} must be a valid integer.") from None
    if parsed <= 0:
        raise BIValidationError(f"{field_name} must be greater than zero.")
    return parsed


def parse_filters(args, company_id: str, today: date) -> BIFilters:
    """Parse the canonical Phase-1 BI filters.

    The v1 API intentionally uses explicit filter names.  The old BI endpoint is
    left untouched so its existing UI remains backward compatible.
    """
    requested_company = _clean(args.get("company"))
    if requested_company and requested_company != company_id:
        raise BIValidationError("Switch company using the authorised company selector.")

    try:
        from_date = date.fromisoformat(args["from_date"]) if _clean(args.get("from_date")) else today.replace(day=1)
        to_date = date.fromisoformat(args["to_date"]) if _clean(args.get("to_date")) else today
    except (TypeError, ValueError):
        raise BIValidationError("Enter valid from_date and to_date values in YYYY-MM-DD format.") from None

    if from_date > to_date:
        raise BIValidationError("from_date must be on or before to_date.")
    if (to_date - from_date).days > 366 * 5:
        raise BIValidationError("Choose a BI date range of five years or less.")

    branch = _clean(args.get("branch"))
    if branch:
        # Current canonical sales/purchase rows do not contain a branch key.
        # Failing loudly is safer than returning company-wide numbers under a
        # branch label and pretending they were filtered.
        raise BIValidationError(
            "Branch filtering is not available yet because canonical sales and purchase records do not currently store branch_id."
        )

    product_category = _clean(args.get("product_category"))
    expense_category = _clean(args.get("expense_category"))

    return BIFilters(
        company_id=company_id,
        from_date=from_date,
        to_date=to_date,
        employee_id=_clean(args.get("employee_id")),
        country=_clean(args.get("country")),
        client_id=_positive_int(args.get("client_id"), "client_id"),
        supplier_id=_positive_int(args.get("supplier_id"), "supplier_id"),
        product_category=product_category,
        expense_category=expense_category,
        branch=None,
    )


def previous_period(filters: BIFilters) -> tuple[date, date]:
    days = (filters.to_date - filters.from_date).days + 1
    previous_to = filters.from_date - timedelta(days=1)
    previous_from = previous_to - timedelta(days=days - 1)
    return previous_from, previous_to

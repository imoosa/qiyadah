"""
intent_router.py  (Qiyadah ERP version)
────────────────────────────────────────────────────────
Deterministic keyword → function dispatch. No AI involved in routing.
company_id ALWAYS comes from the logged-in session server-side — this
router never accepts or infers a company_id from the message text. If
that guarantee breaks (e.g. someone wires this to accept company_id from
a request body instead of session), the isolation this whole module was
built for is gone. Don't do that.
"""

import re
from typing import Optional, Dict, Any


INTENT_MAP = [
    # Help / capabilities / predefined questions — top priority for guidance
    (["help", "what can you do", "what can you answer", "what do you know",
      "capabilities", "list of questions", "predefined questions", "sample questions",
      "what questions", "show help", "how do you help", "what can i ask",
      "what are your features", "show capabilities", "guide", "menu", "faq",
      "question list", "suggest questions"], "help"),

    # How to give access to employees / User & Role management
    (["how to give access to employee", "how to give access to staff", "how to give access",
      "how to add employee", "how to add staff", "how to add user", "how to add a user",
      "how to create employee", "how to create user", "give access to employee",
      "give access to user", "employee access", "user access", "how to grant access",
      "how to manage users", "how to manage employees", "how to set permissions",
      "how to change user permissions", "employee permissions", "user permissions",
      "role permissions", "how to create login for employee", "staff login",
      "create employee account", "add employee", "add user", "create user login"], "employee_access_guide"),

    # How to change password / Account Security
    (["how to change password", "change password", "change my password", "reset password",
      "how to reset password", "forgot password", "update password", "how to update password",
      "change user password", "change login password", "password change",
      "how to reset staff password"], "change_password_guide"),

    # Subscription / Plan Details
    (["what plan is current", "current plan", "my plan", "our plan", "subscription plan",
      "what is my plan", "which plan am i on", "current subscription", "subscription status",
      "plan details", "subscription details", "plan validity", "plan expiry",
      "how many users allowed in plan", "plan limits", "subscription validity"], "company_plan_status"),

    # How to upgrade plan / Pricing
    (["how to upgrade", "how to upgrade plan", "upgrade plan", "upgrade subscription",
      "how to renew plan", "renew subscription", "how to buy more users", "buy user seats",
      "pricing plans", "subscription upgrade", "how to change plan", "upgrade my plan",
      "plan pricing"], "upgrade_plan_guide"),

    # Company Settings / Profile Configuration
    (["how to change company setting", "how to change company settings", "company settings",
      "company setting", "how to edit company profile", "edit company details",
      "update company gstin", "update company address", "change company logo",
      "invoice prefix setting", "bank details on invoice", "how to configure company",
      "company profile settings"], "company_settings_guide"),

    # Common ERP Workflows & How-to

    (["gst rate", "gst slabs", "current tax", "what is gst", "what is rcm", "reverse charge", "input tax credit", "what is itc", "what is cgst", "what is sgst", "what is igst", "difference between cgst", "e-way bill", "eway bill", "tds"], "general_tax_knowledge"),

    # Company Specific GST / Tax Calculations (scoped to DB)
    (["my gst payable", "gst payable", "gst receivable", "my gst report", "gst report",
      "gst collected", "gst paid", "input tax credit on purchase", "output tax on sales", "gst liability",
      "tax payable", "tax receivable", "purchase tax", "sales tax", "total tax collected",
      "quarterly gst", "monthly gst", "yearly gst", "gst summary", "tax summary",
      "what is my gst", "how much gst do i owe", "how much tax do i owe", "my gst summary"],
     "gst_summary"),

    # Today's daily metrics — before period aggregates
    (["today's sales", "todays sales", "sales today", "how much did we sell today",
      "today sale", "sales for today", "today's revenue", "today revenue",
      "today's income", "today's billing", "what did we sell today"], "todays_sales"),


    (["today's expenses", "todays expenses", "expenses today", "what did we spend today",
      "today's spending", "today spending", "daily expenses today"], "todays_expenses"),

    (["cash today", "today's cash", "todays cash", "cash in today",
      "cash out today", "cash received today", "cash paid today",
      "today's cash flow", "cash flow today", "daily cash"], "todays_cash"),

    # Specific Customer Invoices
    (["find customer invoice", "search customer invoice", "lookup customer invoice",
      "customer invoice detail", "find ci", "lookup ci", "ci number", "ci no",
      "customer invoice number", "customer invoice no"], "customer_invoice_detail"),

    (["customer invoice summary", "customer invoices summary", "customer invoices",
      "customer invoice", "billing invoice", "aggregate invoice",
      "billing summary", "how many customer invoices", "ci summary",
      "consolidated invoice"], "customer_invoice_summary"),

    # Overdue Invoices
    (["overdue invoice", "overdue invoices", "overdue bills", "overdue",
      "pending more than 30 days", "long overdue", "which invoices are overdue",
      "which invoices are risky", "bills pending for more than",
      "invoices not paid", "long pending invoices"], "overdue_invoices"),

    # Specific Party (Client / Supplier) outstanding, pending & payable amounts
    (["total outstanding of", "total outsating of", "total outstandng of", "total outstnding of",
      "total out standing of", "total outstanding for", "total outsating for",
      "outstanding of", "outsating of", "outstandng of", "outstnding of",
      "out standing of", "outstanding for", "outsating for", "outstandng for", "outstnding for",
      "outstanding from", "outsating from", "outstandng from", "outstanding balance of", "outsating balance of",
      "how much is outstanding for", "how much outstanding for", "how much is outstanding from", "how much outstanding from",
      "how much outstanding of", "how much outsating of",
      "pending amount of", "pending balance of", "pending amount for", "pending amount from",
      "pending for", "pending from", "pending of",
      "balance of client", "balance of customer", "balance of supplier", "balance of vendor",
      "balance of", "balance for", "how much balance of", "how much balance for",
      "how much pending from", "how much is pending from", "how much pending for", "how much does",
      "client pending balance", "customer pending balance", "amount pending from", "amount pending for",
      "pending for client", "pending for customer",
      "payable amount to", "payable to", "payable of", "payable for",
      "payble amount to", "payble to", "payble of", "payble for",
      "how much to pay to", "how much to pay", "how much do we owe to", "how much do we owe",
      "amount payable to", "amount payble to", "supplier payable balance",
      "vendor payable balance", "payable for supplier", "payable for vendor"], "party_outstanding"),


    # Category-specific expenses — before generic expenses
    (["fuel expense", "fuel expenses", "salary expense", "salary expenses",
      "office expense", "office expenses", "maintenance expense", "maintenance expenses",
      "travel expense", "electricity expense", "rent expense", "misc expense",
      "expense by category", "category wise expense", "expense category"], "expenses_category"),

    # Receivables / payables generic
    (["total outstanding", "total out standing", "total outsating", "total outstandng", "total outstnding",
      "total out standng", "total out stnding", "overall outstanding", "overall out standing",
      "overall pending", "outstanding amount", "total outstanding balance", "total debtor outstanding",
      "total debtors outstanding", "total debtors", "total debtor", "debtors outstanding", "debtor outstanding",
      "debtors balance", "debtor balance", "total customer outstanding", "total client outstanding",
      "total pending balance", "total client balance", "total customer balance",
      "how much is total outstanding", "what is total outstanding", "what is the total outstanding",
      "show total outstanding", "show me total outstanding", "how much total outstanding",
      "how much is outstanding", "how much outstanding", "how much is total pending", "how much total pending",
      "total pending", "total pendng", "all outstanding", "net outstanding", "total dues", "total due", "all dues",
      "outstanding", "out standing", "outsating", "outstandng", "outstnding",
      "who owes", "outstanding receivable", "pending receivable", "receivables",
      "unpaid invoices", "clients pending", "who has to pay", "money is pending",
      "amount receivable", "who has not paid", "total receivable",
      "customers with highest outstanding",
      "bills pending", "who should i collect from",
      "total amount pending", "pending amount to be received",
      "pending amount to receive", "balance pending amount to be received",
      "balance pending to receive", "total pending amount to receive",
      "amount to be received", "how much amount is pending to receive",
      "how much do i need to collect"], "pending_receivables"),

    (["total payble from purchase", "total payable from purchase",
      "total payables from purchase", "total payable in purchase",
      "total payble in purchase", "payable from purchase", "payble from purchase",
      "purchase payables", "purchase payable", "purchase payble",
      "total purchase payables", "total purchase payable", "total purchase payble",
      "total payable", "total payables", "total payble", "total paybles",
      "overall payable", "overall payables", "total creditor outstanding",
      "total creditors", "total supplier outstanding", "total vendor outstanding",
      "what is total payable", "what is the total payable", "show total payable",
      "how much is total payable", "how much total payable",
      "who do we owe", "outstanding payable", "pending payable", "payables",
      "unpaid purchase invoices", "unpaid purchase bills", "unpaid purchase", "suppliers pending", "we owe", "amount payable",
      "suppliers with highest payable",
      "which supplier should i pay",
      "pending amount to pay", "balance pending to pay",
      "amount to be paid", "how much do i need to pay",
      "how much amount is pending to pay"], "pending_payables"),

    # Top rankings
    (["top customer", "top client", "best client", "best customer",
      "highest sales client", "highest revenue client", "top 5 customer",
      "top 10 customer", "top 5 client", "top 10 client", "highest billing client",
      "which customer generated highest", "which customer generated most",
      "show my best customer"], "top_clients_sales"),

    (["worst customer", "worst client", "lowest sales client", "lowest customer",
      "least sales client", "least active client", "bottom client", "bottom customer",
      "lowest revenue client", "which customer generated least"], "worst_clients_sales"),

    (["who owes most", "who has highest outstanding", "highest outstanding client",
      "clients with most pending", "customer with highest balance",
      "who should i collect from first", "which customer should i follow up",
      "customer payment follow up", "collection priority"], "top_clients_outstanding"),

    (["top supplier", "top vendor", "best supplier", "best vendor",
      "highest purchase supplier", "highest purchase vendor",
      "which supplier has highest purchase", "top 5 supplier",
      "top 10 supplier", "supplier ranking", "vendor ranking"], "top_suppliers_purchase"),

    # Client / Supplier statements
    (["client statement", "customer statement", "client ledger", "customer ledger",
      "party statement", "account statement for client", "statement of account",
      "client account summary", "customer account summary",
      "client payment history", "customer payment history",
      "client invoice history", "customer invoice history"], "client_statement"),

    (["supplier statement", "vendor statement", "supplier ledger", "vendor ledger",
      "supplier account summary", "vendor account summary",
      "supplier payment history", "supplier invoice history",
      "account statement for supplier"], "supplier_statement"),

    # Sales aggregate
    (["this month sales", "sales this month", "this months sales", "sales of this month", "current month sales",
      "last month sales", "sales last month", "previous month sales", "past month sales",
      "last 3 months sales", "last three months sales", "last 3 month sales", "3 months sales", "three months sales", "sales last 3 months", "sales of last 3 months", "quarterly sales",
      "last 6 months sales", "last six months sales", "last 6 month sales", "6 months sales", "six months sales", "6th month sales", "6th month", "sales of last 6 months", "sales last 6 months",
      "total sales", "sales summary", "how much did we sell", "sales figure",
      "our sales", "my sales", "total revenue", "revenue", "turnover", "income",
      "sales report", "sales amount", "did we earn",
      "how much money did we make", "earnings", "billing", "customer sales",
      "invoice sales", "highest invoice", "lowest invoice", "invoice summary",
      "compare this month and last month sales", "average sales per day",
      "which day had highest sales",
      "august sales", "sales in august", "sales of august", "aug sales",
      "september sales", "sales in september", "sales of september", "sep sales", "sept sales",
      "october sales", "sales in october", "november sales", "december sales",
      "january sales", "february sales", "march sales", "april sales", "may sales", "june sales", "july sales",
      "monthly sales", "total billed", "billed amount", "how much billed", "billed sales"], "sales_summary"),

    # Purchase aggregate
    (["total purchases", "purchases this month", "this month purchases", "this month purchase", "purchase this month", "current month purchase",
      "last month purchase", "purchase last month", "previous month purchase",
      "last 3 months purchase", "last three months purchase", "3 months purchase", "quarterly purchase",
      "last 6 months purchase", "last six months purchase", "6 months purchase",
      "total purchase", "monthly purchase", "today's purchase", "purchase trend",
      "purchase summary", "purchase report", "buying", "procurement",
      "vendor purchase", "supplier purchase", "compare purchases month wise",
      "highest supplier purchase", "lowest supplier purchase",
      "august purchase", "purchase in august", "september purchase", "purchase in september",
      "october purchase", "november purchase", "december purchase", "january purchase",
      "february purchase", "march purchase", "april purchase", "may purchase", "june purchase", "july purchase"], "purchase_summary"),

    # Cash / Bank
    (["cash in hand", "cash balance", "cash summary", "how much cash",
      "petty cash", "cashbook", "cash book", "cash report",
      "cash received", "cash paid"], "cash_summary"),
    (["bank balance", "bank summary", "bank account balance", "how much in bank",
      "bank statement", "bank ledger", "deposit", "withdrawal",
      "bank transaction"], "bank_summary"),
    (["bank account detail", "account detail", "which account has highest",
      "bank transactions", "account transactions", "recent bank transactions",
      "last bank transaction", "bank account info", "show bank account"], "bank_account_detail"),

    # Receipts & Payments
    (["receipt", "receipts", "today's receipts", "monthly receipts",
      "payment received", "payments received", "collection summary",
      "money received", "amount collected", "total collection",
      "payment made", "payments made", "total payment",
      "receipts and payments", "payment summary"], "receipts_payments_summary"),

    # Loans / Cheques
    (["loan", "emi", "loan outstanding", "loan balance", "borrowing",
      "repayment", "interest paid"], "loans_summary"),
    (["cheque", "check pending", "cheque status", "cheques pending",
      "cleared cheque", "bounced cheque", "cheque due"], "cheques_summary"),

    # Expenses general
    (["expense", "expenses", "spend on", "spending",
      "expense trend", "biggest expense",
      "which expense is increasing", "august expenses", "expenses in august",
      "september expenses", "expenses in september", "last month expenses",
      "this month expenses", "expenses this month", "expenses last month"], "expenses_summary"),

    # Manifest

    # Stock
    (["stock", "inventory", "low stock", "reorder", "warehouse", "out of stock",
      "stock valuation", "stock movement", "fast moving stock",
      "slow moving stock", "dead stock", "most sold item", "least sold item",
      "how much stock"], "stock_summary"),

    # Single Invoices
    (["purchase invoice", "purchase bill", "supplier invoice"], "purchase_invoice_detail"),
    (["invoice", "sales invoice"], "invoice_detail"),

    # Estimates
    (["find estimate", "show estimate", "estimate detail",
      "search estimate", "lookup estimate"], "estimate_detail"),
    (["estimate", "estimates", "quotation", "quotations", "quote",
      "estimate list", "show estimates", "pending estimates",
      "estimate summary", "how many estimates", "total estimates",
      "estimate value", "draft estimates"], "estimate_summary"),

    # Profit & Loss
    (["what is the percent of net profit", "what is net profit percent", "what is net profit percentage",
      "what is the percentage of net profit", "percent of net profit", "percentage of net profit",
      "net profit percent", "net profit percentage", "net profit margin", "profit margin percent",
      "profit margin percentage", "profit percentage", "profit margin", "what is my profit percent",
      "what is my profit margin", "net margin", "net profit", "our net profit", "profit and loss",
      "p&l", "p and l", "how much profit", "total profit", "profit this month", "profit summary",
      "profit report", "are we profitable", "profitability"], "net_profit_summary"),
    (["what is gross profit percent", "gross profit margin", "gross margin", "gross profit percent",
      "gross profit percentage", "percent of gross profit", "percentage of gross profit",
      "total gross profit", "gross profit summary", "gross profit report", "gross profit"], "gross_profit_summary"),


    # Counts & Directories
    (["new customer", "new customers", "new client", "new clients",
      "recently added client", "recently added customer",
      "new clients this month", "new customers this month",
      "clients added this month", "latest clients", "latest customers",
      "customer onboarding", "newly registered"], "new_clients"),
    (["how many clients", "total clients", "client count", "no of clients",
      "number of clients"], "client_count"),
    (["how many suppliers", "total suppliers", "supplier count",
      "no of suppliers", "number of suppliers"], "supplier_count"),
    (["supplier", "vendor"], "supplier_lookup"),
    (["client", "customer", "debtor"], "client_lookup"),

    # Analytics

    # System & Settings
    (["whatsapp connected", "is whatsapp connected", "whatsapp status",
      "whatsapp working", "whatsapp integration status",
      "check whatsapp"], "whatsapp_status"),
    (["how many users", "total users", "user count", "no of users",
      "number of users", "how many owners", "owner count",
      "how many employees", "employee count", "users in company",
      "staff count", "list of users", "list of employees"], "user_count_summary"),
    (["dashboard", "overview", "how is business", "give me a summary",
      "how are we doing", "business summary", "today's summary",
      "company overview", "today's activity", "current business status",
      "how is business today", "performance", "analytics"], "dashboard_summary"),
]


def classify_intent(message: str) -> Optional[str]:
    from utils.assistant_catalog import guide_intent, phrase_matches
    if any(phrase_matches(message, phrase) for phrase in ("track awb", "track shipment", "docket", "manifest", "manifests", "booking", "bookings", "courier rate", "shipping rate", "rate calculator", "price list", "carrier performance")):
        return "unsupported_logistics"
    guidance = guide_intent(message) if not re.search(r"\b(?:expense|expenses)\b", message.lower()) else None
    if guidance:
        return guidance
    # Prefer complete, specific phrases over generic words such as invoice or balance.
    matches = [(len(kw), -index, intent) for index, (keywords, intent) in enumerate(INTENT_MAP)
               for kw in keywords if phrase_matches(message, kw)]
    return max(matches)[2] if matches else None


# Filler words to strip so what remains is a customer, supplier or document identifier.
_FILLER = re.compile(
    r"(?i)\b("
    r"total outstanding of|total outsating of|total outstandng of|total outstnding of|total out standing of|"
    r"total outstanding for|total outsating for|total outstanding from|total outsating from|"
    r"how much is outstanding for|how much outstanding for|how much is outstanding from|how much outstanding from|how much outstanding of|how much outsating of|"
    r"total payable from purchase|total payble from purchase|total payables from purchase|total payable in purchase|total payble in purchase|"
    r"outstanding balance of|outsating balance of|outstanding of|outsating of|outstandng of|outstnding of|out standing of|outstanding for|outsating for|outstanding from|outsating from|"
    r"pending amount of|pending amount for|pending amount from|pending balance of|pending from|pending of|pending for|"
    r"how much is pending from|how much pending from|how much pending for|how much does|how much to pay to|how much to pay|how much do we owe to|how much do we owe|"
    r"payable amount to|payable to|payable of|payable for|payble amount to|payble to|payble of|payble for|amount payable to|amount payble to|amount pending from|amount pending for|"
    r"statement for|statement of|ledger for|ledger of|"
    r"tell me about|details of|info on|information on|what is|what's|"
    r"show me|give me|find|search|lookup|look up|track|"
    r"customer invoice|purchase invoice|purchase bill|invoice|"
    r"client|customer|supplier|vendor|stock item|item|estimate|"
    r"according|number|no|the|my|our|please|for|of|to|from|status|detail|details|about|owe|owes"
    r")\b"
)


def _clean_identifier(message: str) -> str:
    message = re.sub(r"(?i)\bsales invoice\b", "invoice", message)
    cleaned = _FILLER.sub("", message)
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_date_range(message: str):
    import calendar
    from datetime import date, timedelta
    msg = message.lower().replace("'", "")
    today = date.today()

    if 'today' in msg:
        return today, today
    if 'yesterday' in msg:
        yest = today - timedelta(days=1)
        return yest, yest
    if 'last 7 days' in msg or '7 days' in msg:
        return today - timedelta(days=7), today
    if 'last 30 days' in msg or '30 days' in msg or 'past 30 days' in msg:
        return today - timedelta(days=30), today
    if 'last 90 days' in msg or '90 days' in msg or 'past 90 days' in msg:
        return today - timedelta(days=90), today
    if 'last 3 month' in msg or 'last three month' in msg or '3 month' in msg or 'three month' in msg or 'quarter' in msg or 'past 3 month' in msg or 'past three month' in msg:
        return today - timedelta(days=90), today
    if 'last 6 month' in msg or 'last six month' in msg or '6 month' in msg or 'six month' in msg or '6th month' in msg or 'half year' in msg or 'past 6 month' in msg or 'past six month' in msg:
        return today - timedelta(days=180), today
    if 'last 12 month' in msg or '12 month' in msg or 'last year' in msg or 'previous year' in msg or 'past year' in msg:
        return today - timedelta(days=365), today
    if 'this month' in msg or 'current month' in msg:
        return today.replace(day=1), today
    if 'last month' in msg or 'previous month' in msg or 'past month' in msg:
        first_of_this = today.replace(day=1)
        last_of_last = first_of_this - timedelta(days=1)
        return last_of_last.replace(day=1), last_of_last
    if 'this year' in msg or 'current year' in msg:
        return today.replace(month=1, day=1), today

    # Named months (e.g. "august", "aug", "september sales", "sales in jan 2026")
    month_names = {
        'january': 1, 'jan': 1,
        'february': 2, 'feb': 2,
        'march': 3, 'mar': 3,
        'april': 4, 'apr': 4,
        'may': 5,
        'june': 6, 'jun': 6,
        'july': 7, 'jul': 7,
        'august': 8, 'aug': 8,
        'september': 9, 'sep': 9, 'sept': 9,
        'october': 10, 'oct': 10,
        'november': 11, 'nov': 11,
        'december': 12, 'dec': 12,
    }

    year_match = re.search(r'\b(20\d\d)\b', msg)
    explicit_year = int(year_match.group(1)) if year_match else None

    for m_name, m_num in month_names.items():
        if re.search(r'\b' + m_name + r'\b', msg):
            target_year = explicit_year or today.year
            _, last_day = calendar.monthrange(target_year, m_num)
            start_date = date(target_year, m_num, 1)
            end_date = date(target_year, m_num, last_day)
            return start_date, end_date

    return None, None

def extract_months(message: str, default: int = 1) -> int:
    msg = message.lower()
    if "3 month" in msg or "three month" in msg or "quarter" in msg or "last 3" in msg or "past 3" in msg:
        return 3
    if "6 month" in msg or "six month" in msg or "half year" in msg or "6th month" in msg or "last 6" in msg or "past 6" in msg:
        return 6
    if "12 month" in msg or "year" in msg or "annual" in msg:
        return 12
    return default


def extract_days(message: str, default: int = 30) -> int:
    m = re.search(r"(\d+)\s*day", message.lower())
    return int(m.group(1)) if m else default


def extract_limit(message: str, default: int = 10) -> int:
    """Extract a ranking limit: 'top 5', 'top 10', etc."""
    m = re.search(r"\btop\s+(\d+)\b", message.lower())
    return int(m.group(1)) if m else default


def extract_category_from_expense_message(message: str) -> str:
    """Extract expense category from message (fuel, salary, office, etc.)."""
    msg = message.lower()
    categories = [
        "fuel", "salary", "office", "maintenance", "travel",
        "electricity", "rent", "misc", "miscellaneous", "repair",
        "transport", "printing", "insurance", "telephone", "internet",
        "water", "cleaning", "stationary", "food",
    ]
    for cat in categories:
        if cat in msg:
            return cat
    return ""


# ─────────────────────────────────────────────────────────────────────────
# Main dispatch — company_id must be passed in by the caller, sourced from
# the authenticated session, never from message text.
# ─────────────────────────────────────────────────────────────────────────

def dispatch(message: str, company_id: str) -> Dict[str, Any]:
    from utils.assistant_catalog import GUIDES, guide_data, help_catalog
    intent = classify_intent(message)
    if not company_id:
        return {"intent": None, "error": "no_company_context"}
    if intent in GUIDES:
        return guide_data(intent)
    if intent == "help":
        return help_catalog()
    if intent == "unsupported_logistics":
        return {"intent": intent, "kind": "guidance", "content": "Shipment tracking, bookings, manifests and courier rates belong to your separate logistics application. In Qiyadah ERP, ask about sales invoices, purchases, balances, inventory, finance, HR or CRM."}
    from utils.query_engine import (
        get_dashboard_summary, get_client_detail, get_all_clients_summary,
        get_supplier_detail, get_all_suppliers_summary, get_invoice_detail,
        get_pending_receivables, get_pending_payables, get_purchase_invoice_detail,
        get_cash_summary, get_bank_summary, get_expenses_summary,
        get_stock_summary, get_stock_item_detail, 
        get_loans_summary, get_cheques_summary, get_sales_summary,
        get_purchase_summary, get_gst_summary,
        # Extended intents:
        get_net_profit_summary, get_gross_profit_summary, 
         get_client_count, get_supplier_count,
         get_whatsapp_status, get_user_count_summary,
        get_worst_clients_by_sales,
        # Guide & Plan intents:
        get_company_plan_status, get_employee_access_guide, get_change_password_guide,
        get_upgrade_plan_guide, get_company_settings_guide, 
    )

    if not company_id:
        # Defensive: never silently query without a scoped company.
        return {"intent": None, "error": "no_company_context", "message": message}

    msg_lower = message.lower()
    intent = classify_intent(message)

    if intent is None:
        return {"intent": None, "message": message}

    if intent == "dashboard_summary":
        return get_dashboard_summary(company_id)

    if intent == "sales_summary":
        # default=None → all-time total unless the user names a period
        start, end = extract_date_range(message)
        months = extract_months(message, default=None)
        return get_sales_summary(company_id, start_date=start, end_date=end, months=months)

    if intent == "purchase_summary":
        start, end = extract_date_range(message)
        months = extract_months(message, default=None)
        return get_purchase_summary(company_id, start_date=start, end_date=end, months=months)

    if intent == "gst_summary":
        start, end = extract_date_range(message)
        months = extract_months(message, default=None)
        return get_gst_summary(company_id, start_date=start, end_date=end, months=months)

    if intent == "client_lookup":
        identifier = _clean_identifier(message)
        if any(kw in msg_lower for kw in ["all client", "list client", "how many client", "total client"]):
            return get_all_clients_summary(company_id)
        if identifier and len(identifier) >= 2:
            result = get_client_detail(company_id, identifier)
            if result.get("found"):
                return result
        return get_all_clients_summary(company_id)

    if intent == "supplier_lookup":
        identifier = _clean_identifier(message)
        if any(kw in msg_lower for kw in ["all supplier", "list supplier", "how many supplier", "total supplier"]):
            return get_all_suppliers_summary(company_id)
        if identifier and len(identifier) >= 2:
            result = get_supplier_detail(company_id, identifier)
            if result.get("found"):
                return result
        return get_all_suppliers_summary(company_id)

    if intent == "invoice_detail":
        identifier = _clean_identifier(message)
        if identifier and len(identifier) >= 2:
            return get_invoice_detail(company_id, identifier)
        from utils.query_engine import get_customer_invoice_summary
        return get_customer_invoice_summary(company_id)

    if intent == "purchase_invoice_detail":
        identifier = _clean_identifier(message)
        if identifier and len(identifier) >= 2:
            return get_purchase_invoice_detail(company_id, identifier)
        return get_purchase_summary(company_id)

    if intent == "pending_receivables":
        return get_pending_receivables(company_id)

    if intent == "pending_payables":
        return get_pending_payables(company_id)

    if intent == "cash_summary":
        return get_cash_summary(company_id)

    if intent == "bank_summary":
        return get_bank_summary(company_id)

    if intent == "expenses_summary":
        start, end = extract_date_range(message)
        months = extract_months(message)
        return get_expenses_summary(company_id, start_date=start, end_date=end, months=months)

    if intent == "stock_summary":
        identifier = _clean_identifier(message)
        if identifier and len(identifier) >= 2 and not any(
            kw in msg_lower for kw in ["low stock", "reorder", "all stock", "total stock"]
        ):
            result = get_stock_item_detail(company_id, identifier)
            if result.get("found"):
                return result
        return get_stock_summary(company_id)


    if intent == "loans_summary":
        return get_loans_summary(company_id)

    if intent == "cheques_summary":
        return get_cheques_summary(company_id)

    if intent == "net_profit_summary":
        start, end = extract_date_range(message)
        months = extract_months(message, default=None)
        return get_net_profit_summary(company_id, start_date=start, end_date=end, months=months)
 
    if intent == "gross_profit_summary":
        start, end = extract_date_range(message)
        months = extract_months(message, default=None)
        return get_gross_profit_summary(company_id, start_date=start, end_date=end, months=months)
 
 
 
    if intent == "client_count":
        return get_client_count(company_id)
 
    if intent == "supplier_count":
        return get_supplier_count(company_id)
 
 
    if intent == "whatsapp_status":
        return get_whatsapp_status(company_id)
 
    if intent == "user_count_summary":
        return get_user_count_summary(company_id)

    # ── NEW DISPATCH BRANCHES ────────────────────────────────────────────────
    from utils.query_engine import (
        get_todays_sales, get_top_clients_by_sales, get_top_clients_by_outstanding,
        get_overdue_invoices,  get_todays_expenses,
        get_expenses_by_category, get_todays_cash, get_receipts_payments_summary,
        get_client_statement_summary, get_supplier_statement_summary,
        get_estimate_summary, get_estimate_detail, get_top_suppliers_by_purchase,
          get_new_clients,
        get_customer_invoice_summary, get_customer_invoice_detail, get_bank_account_detail,
          get_client_pending_amount,
        get_supplier_payable_amount, get_party_outstanding, get_help_catalog,
          get_general_tax_knowledge,
    )


    if intent in ("party_outstanding", "client_pending_amount", "supplier_payable_amount"):
        identifier = _clean_identifier(message)
        if identifier and len(identifier) >= 2:
            return get_party_outstanding(company_id, identifier)
        return get_pending_receivables(company_id)

    if intent == "todays_sales":
        return get_todays_sales(company_id)


    if intent == "overdue_invoices":
        return get_overdue_invoices(company_id)

    if intent == "top_clients_sales":
        limit = extract_limit(message, default=10)
        months = extract_months(message, default=None)
        return get_top_clients_by_sales(company_id, limit=limit, months=months)

    if intent == "worst_clients_sales":
        limit = extract_limit(message, default=10)
        months = extract_months(message, default=None)
        return get_worst_clients_by_sales(company_id, limit=limit, months=months)

    if intent == "top_clients_outstanding":
        limit = extract_limit(message, default=10)
        return get_top_clients_by_outstanding(company_id, limit=limit)


    if intent == "todays_expenses":
        return get_todays_expenses(company_id)

    if intent == "expenses_category":
        category = extract_category_from_expense_message(message)
        months = extract_months(message, default=1)
        if not category:
            return get_expenses_summary(company_id, months=months)
        return get_expenses_by_category(company_id, category=category, months=months)

    if intent == "todays_cash":
        return get_todays_cash(company_id)

    if intent == "receipts_payments_summary":
        months = extract_months(message, default=1)
        return get_receipts_payments_summary(company_id, months=months)

    if intent == "client_statement":
        identifier = _clean_identifier(message)
        if identifier and len(identifier) >= 2:
            return get_client_statement_summary(company_id, identifier)
        return get_all_clients_summary(company_id)

    if intent == "supplier_statement":
        identifier = _clean_identifier(message)
        if identifier and len(identifier) >= 2:
            return get_supplier_statement_summary(company_id, identifier)
        return get_all_suppliers_summary(company_id)

    if intent == "estimate_summary":
        months = extract_months(message, default=1)
        return get_estimate_summary(company_id, months=months)

    if intent == "estimate_detail":
        identifier = _clean_identifier(message)
        if identifier and len(identifier) >= 2:
            return get_estimate_detail(company_id, identifier)
        return get_estimate_summary(company_id, months=1)

    if intent == "top_suppliers_purchase":
        limit = extract_limit(message, default=10)
        months = extract_months(message, default=None)
        return get_top_suppliers_by_purchase(company_id, limit=limit, months=months)


    if intent == "new_clients":
        months = extract_months(message, default=1)
        return get_new_clients(company_id, months=months)

    if intent == "customer_invoice_detail":
        identifier = _clean_identifier(message)
        if identifier and len(identifier) >= 2:
            return get_customer_invoice_detail(company_id, identifier)
        return get_customer_invoice_summary(company_id, months=1)

    if intent == "customer_invoice_summary":
        months = extract_months(message, default=1)
        start, end = extract_date_range(message)
        return get_customer_invoice_summary(company_id, months=months, start_date=start, end_date=end)

    if intent == "bank_account_detail":
        identifier = _clean_identifier(message)
        return get_bank_account_detail(company_id, identifier or "")


    if intent == "company_plan_status":
        return get_company_plan_status(company_id)

    if intent == "employee_access_guide":
        return get_employee_access_guide(company_id)

    if intent == "change_password_guide":
        return get_change_password_guide(company_id)

    if intent == "upgrade_plan_guide":
        return get_upgrade_plan_guide(company_id)

    if intent == "company_settings_guide":
        return get_company_settings_guide(company_id)


    if intent == "help":
        return get_help_catalog()

    if intent == "general_tax_knowledge":
        return get_general_tax_knowledge(topic=message)

    return {"intent": None, "message": message}

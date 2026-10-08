"""Verified Qiyadah guidance and examples; no database or model dependency."""
from functools import lru_cache
import re

# Guides explain existing screens. They never imply that chat executed an action.
GUIDES = {
    "profit_loss_guide": ("Profit and loss report", "/reports/profit-loss", "Open Profit & Loss and select the reporting period. Review revenue, cost and expense postings alongside the source records and Accounting Checks. A comparison of sales and purchase bills alone is not inventory-adjusted accounting profit.", ["profit and loss", "profit & loss", "p&l", "income statement"]),
    "balance_sheet_guide": ("Balance sheet", "/reports/balance-sheet", "Open Balance Sheet and select the reporting date. Review assets, liabilities and equity, then investigate reconciliation exceptions in Accounting Checks. Chat provides guidance, not a certified balance sheet.", ["balance sheet"]),
    "cash_flow_guide": ("Cash flow report", "/reports/cash-flow", "Open Cash Flow to review recorded movements for the chosen period. Compare the report with Cash, Bank and Receipts & Payments. These are Qiyadah records; chat does not connect to your bank.", ["cash flow report", "cash flow statement", "working capital", "liquidity"]),
    "ledger_guide": ("General ledger", "/ledger", "Open General Ledger to inspect account entries and their source references for the selected period. Use Financial Records for underlying documents and Accounting Checks for differences.", ["general ledger", "journal entries", "journal entry", "chart of accounts", "trial balance"]),
    "fixed_assets_guide": ("Fixed assets", "/finance/fixed-assets", "Open Finance, then Fixed Assets to review the register and depreciation. Review the asset and period before posting depreciation. Chat does not post entries or change asset records.", ["fixed asset", "depreciation", "asset register"]),
    "sales_guide": ("Sales invoices", "/customer-invoices/new", "Open Sales Invoices, choose New Invoice, select the customer and add product or service lines. Review quantities, prices, tax, payment terms and totals before saving. The assistant can explain records; saving happens on the invoice screen.", ["how to create invoice", "how to create sales invoice", "how to create customer invoice", "how to generate customer invoice", "how to make customer invoice", "how to add invoice"]),
    "purchase_guide": ("Purchase invoices", "/purchase/new", "Open Purchases and add a purchase invoice. Select the supplier, enter the bill reference and items, review tax and amounts, and save. Record settlement through Payments with the correct supplier and invoice reference.", ["how to add purchase invoice", "how to create purchase invoice", "how to record purchase", "how to add supplier bill"]),
    "sales_order_guide": ("Sales orders", "/sales-orders", "Open Sales Orders to create or review an order. Check the customer, item quantities and prices. Use the order's available conversion action to create a delivery challan or sales invoice, then review the resulting document.", ["sales order", "order to cash", "order-to-cash"]),
    "purchase_order_guide": ("Purchase orders", "/purchase-orders", "Open Purchase Orders, select the supplier and enter the required items. Review the order before saving. Use the conversion action when you are ready to create the supplier bill; review the bill before recording payment.", ["purchase order", "procure to pay", "procure-to-pay"]),
    "challan_guide": ("Delivery challans", "/delivery-challans", "Use Delivery Challans for goods issued to a customer. Review the customer and item quantities, then use the available invoice conversion when billing is due.", ["delivery challan", "delivery note"]),
    "receipt_guide": ("Customer receipts", "/receipts/new", "Open Receipts, select the customer and invoice reference, choose Cash or Bank, and enter the date and amount. Verify the reference before saving so the payment is applied to the right account.", ["how to record receipt", "how to add receipt", "how to receive payment", "how to record customer payment"]),
    "payment_guide": ("Supplier payments", "/payments/new", "Open Payments, choose the supplier and bill reference, select the payment account, and enter the date and amount. Review and save the payment. This records a transaction in Qiyadah; it does not transfer money through a bank.", ["how to record payment", "how to pay supplier", "how to add payment"]),
    "finance_records_guide": ("Financial records", "/finance", "Financial Records contains the underlying entries used by accounting: invoices, payments and supporting records. Open Finance and choose a record category to inspect its source and posting details. These are records, while Accounting Checks tests whether related records agree.", ["financial records", "finance records", "finance workspace", "finance overview"]),
    "accounting_checks_guide": ("Accounting checks and reconciliation", "/finance/accounting-checks", "Open Finance → Accounting Checks to review reconciliation coverage and exceptions. Checks compare source records, journal postings, party balances and payment links. Investigate each exception in its source screen; a check does not automatically repair or certify the accounts.", ["accounting checks", "accounting check", "reconciliation", "reconcile", "posting mismatch", "unbalanced journal"]),
    "period_close_guide": ("Financial period controls", "/finance/periods", "The company owner can open Finance → Period Controls, select a closing date, review checks, and record the required reason. Closed periods block changes to protected financial records. The owner must reopen the period before correcting those records; closing and reopening are audited.", ["period close", "close period", "close a period", "close financial period", "close the month", "month end", "month-end", "reopen period", "period lock", "closed period"]),
    "notes_guide": ("Credit and debit notes", "/finance/credit-notes", "Use Finance → Credit Notes for customer credits and Finance → Debit Notes for supplier debits. Choose the original invoice, enter the adjustment and reason, and review before posting. These actions affect accounting and remain subject to period controls.", ["credit note", "debit note"]),
    "hr_guide": ("HR and payroll", "/hr", "Open HR for employee records, attendance, shifts, leave, salary structures and payroll. Maintain employee and salary information before calculating a payroll run; review the run before approval. Chat currently provides workflow guidance for HR, not live payroll or attendance totals.", ["payroll", "salary", "salaries", "attendance", "leave request", "leave requests", "leave balance", "human resources", "hr workspace", "hr employee"]),
    "crm_guide": ("CRM", "/crm", "Open CRM to manage leads, customer contacts, follow-up activities and quotations. Review a lead before converting it to a customer, and use activities to record the next follow-up. Chat currently provides CRM guidance, not live pipeline or lead counts.", ["crm", "lead", "leads", "pipeline", "follow up", "follow ups", "follow-up", "follow-ups", "customer contact"]),
    "inventory_guide": ("Inventory", "/inventory", "Open Inventory to review items and available quantities. Use stock inward for received goods and stock adjustments for corrections, with the correct item, quantity and reason. Ask 'Low stock' for the assistant's stock summary.", ["how to add stock", "how to adjust stock", "how to manage inventory", "stock inward", "inventory guide"]),
    "workflow_guide": ("Qiyadah workflows", "/finance", "Sales: quotation → sales order → delivery challan or invoice → receipt. Purchasing: purchase order → supplier bill → payment. Use Inventory for quantities, Finance for records and checks, HR for employees and payroll, and CRM for leads and follow-ups. Actions must be reviewed and saved in their own screens.", ["qiyadah workflow", "erp workflow", "how to use qiyadah", "how to check client statement"]),
    "company_settings_guide": ("Company settings", "/company/settings", "Open Company Settings to manage company details, logo, billing terms and invoice presentation. Use the Team and Access sections for user accounts and permissions. Save the relevant form after reviewing your changes.", ["company settings", "company setting", "company profile", "change company logo", "update company address", "update company gstin"]),
    "employee_access_guide": ("Team access", "/company/settings", "The owner manages login users in Company Settings → Team and controls their module permissions in Access. Create the user, select a role, review individual permissions and save. HR employee records and application login accounts serve different purposes.", ["employee access", "user access", "add employee", "add user", "add staff", "set permissions", "role permissions", "give access", "staff login"]),
}

CATEGORIES = [
    ("Sales and customers", "Invoice totals and customer balances", ["Today's sales", "Sales this month", "Overdue invoices", "Who owes me money?", "Find customer invoice [invoice number]", "How to create sales invoice?"]),
    ("Purchases and suppliers", "Supplier bills and payments", ["Total purchases this month", "Total payable from purchase", "Supplier statement [supplier name]", "How to record payment?", "How to create purchase order?"]),
    ("Finance and accounting", "Records, checks and period controls", ["Explain financial records", "Explain accounting checks", "How does reconciliation work?", "How to close a period?", "How to create a credit note?", "Open profit and loss report", "Explain balance sheet", "Show fixed assets"]),
    ("Cash and bank", "Balances recorded in Qiyadah", ["Cash balance", "Total bank balance", "Receipts and payments", "Today's expenses", "How to record receipt?"]),
    ("Inventory and orders", "Stock and document workflows", ["Low stock", "Total stock", "How to add stock?", "How to create sales order?", "How to create delivery challan?"]),
    ("HR and payroll", "Workflow guidance; live HR totals are not connected to chat", ["How to manage attendance?", "How does payroll work?", "How to review leave requests?"]),
    ("CRM", "Workflow guidance; live CRM totals are not connected to chat", ["How to manage leads?", "How to manage follow-ups?", "How to use CRM?"]),
    ("Settings and access", "Company configuration and team permissions", ["Company settings", "How to give access to employee?", "What is my current plan?", "How to use Qiyadah?"]),
]


def normalize(message):
    return re.sub(r"[^\w\s-]", "", message.lower().replace("’", "'")).strip()


@lru_cache(maxsize=2048)
def _phrase_pattern(phrase):
    return re.compile(r"(?<!\w)" + re.escape(normalize(phrase)) + r"s?(?!\w)")


def phrase_matches(message, phrase):
    return _phrase_pattern(phrase).search(normalize(message)) is not None


def guide_intent(message):
    for intent, (_, _, _, phrases) in GUIDES.items():
        if any(phrase_matches(message, p) for p in phrases):
            return intent
    return None


def guide_data(intent):
    title, path, content, _ = GUIDES[intent]
    return {"intent": intent, "title": title, "content": content, "path": path, "kind": "guidance"}


def help_catalog():
    return {"intent": "help", "categories": [
        {"name": name, "icon": "fas fa-circle-question", "description": description, "questions": questions}
        for name, description, questions in CATEGORIES
    ]}

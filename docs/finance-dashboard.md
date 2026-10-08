# Accountant workspace

The `/finance` page is now a dashboard, not a shortcut directory. It uses the
existing Qiyadah base layout, typography, green sidebar and gold accents.

## Navigation and roles

The requested Finance, Receivables, Payables, Accounting, Banking & Cash, Tax,
Expenses & Assets, and Reports groups are available. Existing functions link to
their original routes. Accountants retain this navigation on Core financial
screens and repair-bill lists. Specialist workspaces keep their own navigation.
Owners/admins retain the full Core sidebar on existing Core pages and can return
to Core or Apps Hub from Finance. Mobile navigation has finance destinations too.

Credit/debit notes, chart of accounts, journal entries, balance sheet, cash flow,
bank reconciliation, fixed assets and depreciation are labelled **Planned**.
No duplicate business functions or empty screens were created for these items.
Tax Reports opens the tax tab of the existing Analytics page.

## Filters and interpretation

- Company uses the current authorised session. Switching reuses the existing
  company selector; passing another company ID to Finance is rejected.
- Branch shows all company records and is disabled with an explanation: the
  existing financial models do not share a branch field.
- Financial Year is an explicitly labelled April–March reporting preset; dates
  can be overridden. It does not introduce a new accounting-period model.
- The date range applies to invoice activity, expenses and invoice tax.
- Open invoices, ageing and recorded cash/bank balances are **current**, not
  reconstructed historical balances. Their labels explicitly say so.

## Data sources

| Dashboard figure | Existing source and limits |
|---|---|
| Cash in hand | CashTransaction income minus expense, matching the existing cashbook's all-time balance |
| Cash at bank | Active BankAccount.balance; opening balances are not added again |
| Receivable/payable KPIs | Positive CustomerInvoice/PurchaseInvoice balances on issued, non-future-dated invoices; exclude draft, void and cancelled records |
| Sales / purchases | Selected-period invoice subtotals, excluding tax; repair bills included once in sales |
| Expenses | Selected-period Expense register; payment mirrors are not summed again |
| Invoice input/output tax | Selected-period purchase/sales tax_amount by document currency |
| Gross/net profit and P&L trend | Not calculated: needs cost of sales, valuation, accruals, adjustments and the accounting engine |
| Net tax payable/receivable | Not asserted: input eligibility, reverse charge and adjustments need reconciliation |
| Unreconciled/unposted counts | Unavailable: no reliable matching/posting status exists |

Amounts in different document currencies are never summed. Cash, bank and
expenses use the existing company-currency registers. The monthly revenue versus
expense chart compares only company-currency invoice subtotals with expenses;
it is explicitly an activity chart, not a P&L. Invoice tax difference is shown
only when all contributing invoice permissions are granted.

Open invoice balances exclude party opening balances, unapplied advances and
standalone legacy bookings. Existing party statements remain available. Finance
does not pretend the invoice-only figures are reconciled control accounts.

Workshop classification uses invoice_category and tenant-scoped job-card links.
Multiple job links cannot duplicate an invoice in dashboard totals. Legacy
booking Invoice records are not added to their aggregate CustomerInvoice.

## Drill-downs

`/finance/records/<kind>` is a read-only, permission-filtered projection of the
same source records, with 50 rows per page and links to original document pages.
Kinds are receivables, payables, sales, purchases, input-tax and output-tax.
Ageing uses due date: not due, 1–30, 31–60, 61–90, 90+ days, and no due date.
Due-soon means today through seven days ahead. Date and ageing filters survive
pagination. Cash, bank and expense KPIs reuse their original screens.

## Validation and remaining limits

The regression suite covers currency separation, source reuse, tenant and role
isolation, date scopes, ageing boundaries, dashboard drill-downs, navigation roles,
bank opening-balance double-count prevention and unavailable KPI states. The full
base template was rendered and visually checked in a browser using synthetic
records; no production application startup or database writes were required.

Live MySQL deployment verification and historical reconciliation remain outside
this change. No journal engine, migration, model/table change or operational
transaction creation was introduced.

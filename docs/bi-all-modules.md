# All-module BI overview

## Plan access

All public plans retain the All-Module Dashboard, Report Dashboard (including its
report tabs), and a separate Detailed Financial Reports card/tab. In the All-Module
BI Dashboard (`/bi-dashboard`), analytics and tabs reflect the active subscription plan:
modules included in the chosen plan show full metrics and open tabs, while unincluded
modules completely disappear from the Whole business overview and their corresponding tabs
are locked. Selecting a locked business area is rejected. Standalone suite features
(Executive Overview, Department Intelligence, Explorer/exports, Studio/My Dashboards,
Warehouse and Predictive Analytics) require the active company's `unified` plan.
The central module guard enforces this on pages and APIs.
Giving another plan a BI module override does not unlock Unified features;
blocking BI still blocks Unified. The BI landing page displays locked cards.

The workspace hub includes a prominent **Open business overview** action for BI
users. The overview combines a posted-accounting performance summary, current
exceptions, module shortcuts, activity comparisons and detailed charts for all
permitted business areas. Every chart includes exact values, source notes and CSV
export, with selectable bar or line views and no external chart dependency.

Profit uses posted/reversed journal movements and the same account grouping as
Profit & Loss: revenue less COGS gives gross profit; other income less operating
expenses gives net profit. Losses are retained. Missing posted data is labelled
unavailable, never substituted with invoice-minus-purchase estimates. Comparisons
use the preceding equal-length period. Monthly buckets respect selected dates;
partial months are not extrapolated. Currencies remain separate. Operational
snapshots are explicitly labelled and do not imply historical status tracking.

The primary **BI Dashboard** (`/bi-dashboard`) now renders the operational overview
for company owners and super administrators. Module shortcuts are in the actual
BI sidebar and the Intelligence home opens the same dashboard. The previous
financial dashboard remains available at `/bi-dashboard/finance` as **Financial
Analytics**. Team users retain the existing scoped financial dashboard; the new
company-wide endpoint follows the owner boundary already used by Executive BI.

## Sources and definitions

| Module | Measures |
| --- | --- |
| Finance | Issued sales invoices, billed sales with/without tax, outstanding saved receivables/payables, overdue invoices, purchase invoices and recorded expenses |
| CRM | Leads and quotes created, current pipeline stages, open opportunities, overdue expected close dates, current won status of leads created in the selected period |
| Supply Chain | Stock items at/below reorder and negative stock, purchase and sales orders, delivery challans, overdue purchase orders, production stages and quality failures |
| Workshop | Jobs opened, active jobs, overdue promised delivery, current status distribution, delivered status of the selected creation-period cohort |
| HR & Payroll | Active employees, joiners, recorded attendance employee-days, overlapping approved leave requests, pending leave, approved/locked payroll net pay and payment status |

Date filters affect activity records by their saved business/creation date.
Previous-period counts use the immediately preceding period of equal length.
Snapshot values and current statuses always reflect now, including on a historical
date selection. Payroll uses complete months touched by the range, not prorated
pay. Leave counts requests, not leave days; attendance is not an attendance rate.

Sales totals use CustomerInvoice once (including repair invoices), never booking
invoices plus their aggregate, workshop estimates, leads, orders or challans.
Currency totals are separate. Currency-less CRM values are not summed. Existing
saved balances are used rather than reconstructing historical receivables.
Payroll totals are not added again to recorded expenses. No profit, stock
valuation or historical pipeline conversions are inferred from these counts.

Each card opens its corresponding workspace and source records. Those screens
apply their own filters; clicking a workspace link does not promise an exact
drill-through to the metric's date range. Detailed existing Finance analytics,
Builder, warehouse and predictive tools retain their existing supported datasets.

## Access and unavailable data

The page and `/api/bi/v1/business` require Analytics permission and BI entitlement.
New company-wide summaries require owner/super-admin access. Source-module
entitlements are checked before any record query. Granular document and HR
permissions are honoured, including payroll and sales versus repair bills.
All source queries are scoped to the active company. No cross-company/branch
consolidation is claimed. Unsupported filters are rejected instead of ignored.
Missing or outdated sources show a setup notice, not fabricated zero metrics.

No tables or financial records are written by this feature.

Validation: `python -m unittest discover -s tests -p test_bi_business.py`.

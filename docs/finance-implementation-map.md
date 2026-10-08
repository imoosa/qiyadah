# Finance & Accounting: audit and implementation map

Audit date: 2026-09-24. Scope: local Python source, route/decorator inventory,
SQLAlchemy models and relationships, templates/navigation, database routing,
and read-only inspection of the four supplied SQLite database schemas.
See `finance-source-inventory.md` for the pre-change inventory of all source
routes, model declarations, template links and local schemas.

The runtime uses per-company MySQL databases, not these older SQLite copies.
Live MySQL schema/data and deployment configuration have **not** been verified.
This is a source/schema audit, not a certification of historical balances.
No production database was opened or migrated during this work.

| Area | EXISTING | NEEDS MODIFICATION | NEW |
|---|---|---|---|
| Finance workspace | Core financial screens and base navigation | Consolidate accountant entry point and preserve action permissions | `/finance` landing page using existing endpoints and records |
| Sales/CRM | Client, CRMContact/Lead/Quotation/Project/Interaction; Estimate, SalesOrder, CustomerInvoice | Trace CRM → OrderFlow → existing sales document; avoid billing both booking and aggregate invoice | Explicit source linkage and posting identity |
| Manufacturing | OrderFlow, OrderDepartment, OrderFlowHistory; operational credit/QC/dispatch statuses | No invoice FK or invoice creation found in OrderFlow routes; amount_paid is operational data | Idempotent handoff to an existing sales invoice, not a parallel invoice model |
| Core sales | SalesOrder/DeliveryChallan conversions already create CustomerInvoice | Conversion concurrency and source uniqueness need verification | Journal adapter for canonical invoice |
| Workshop | Job cards, estimates/items, parts issues, QC, vehicles, service history; job card invoice_id points to CustomerInvoice | Bill regeneration updates existing invoice; financial bill access should also work in Core; preserve labour/parts classification | Journal adapter for same repair invoice |
| Purchases | Supplier, PurchaseInvoice/items, PurchasePayment, PurchaseOrder conversion | Reconcile stock direction, payment mirrors, input-tax/base-currency values | Purchase journal adapter |
| Settlement | CashTransaction, BankTransaction, Cheque, Expense, Loan/Repayment; receipt/payment edit and reversal routes | Reconcile direct paid_amount mutations and cash/bank entries before posting | Canonical settlement event mapping |
| Stock | StockItem, StockPurchaseHistory and WorkshopPartIssue | Movement provenance, costing, consistent reversal direction | Inventory/COGS/WIP posting policy and reconciliation |
| Reports | Ledger, trial balance, P&L, tax/stock/sales/purchase reports, debtor/creditor statements | Existing reports are computed operational summaries, not journal-backed books | Balanced journal reports, balance sheet, reconciliation and period locks |
| Access | Login, company role/user overrides, field controls, platform module entitlements | Accountant analytics is denied by default; repair bills currently require specialist entitlement | Finance permission within existing matrix |

## Findings that control the implementation

1. `CustomerInvoice` is the canonical sales/repair document. Legacy `Invoice`
   contains bookings. `booking_ids_json`, item booking links, and receipt
   synchronization already connect them. Posting both is a duplication risk.
   Reuse `_used_booking_ids_in_customer_invoices` and reconciliation logic when
   defining coverage for standalone bookings; do not blindly sum both tables.
2. Workshop invoice regeneration reuses the job card's invoice. Delivery in
   `api_workshop_deliver_vehicle` updates invoice paid_amount/balance without creating a
   cash/bank transaction in that function. Do not synthesize cash receipts from
   the total paid amount: historical receipts could already exist elsewhere.
3. Cash/bank records have applied_ref_type/id, applied_ci_id, and allocation JSON.
   PurchasePayment can coexist with a cash/bank entry for the same settlement.
   Posting every payment-shaped row would double count money movements.
4. `/ledger` reads legacy Invoice and PurchaseInvoice and infers payment dates
   from invoice dates. It omits CustomerInvoice, actual cash/bank movements and
   expenses. `/trial-balance` uses Client for suppliers, does not apply its
   as-on date to queries, includes gross revenue plus separate tax, and has no
   balancing journal foundation. Preserve routes while replacing internals in
   the accounting-engine stage; do not label them as verified books now.
5. Purchase creation adds stock in one path, while purchase deletion contains
   stock restoration logic/commentary for an OUT movement. Stock effects are
   spread across bookings, manifests, sales, purchases, challans and workshop.
   Correct this through transaction-specific tests before adding COGS posting.
6. Existing money columns are Float; base amounts/currency fields exist on
   invoices. New journal amounts must use fixed precision. Historical base
   amounts, rounding and FX must be reconciled rather than assumed correct.
7. Many business references are plain IDs/string references rather than FKs.
   Preserve them. New links must be tenant-scoped and must not rebuild masters.
8. Startup creates tables and runs permissive schema patches that swallow
   failures. Do not use importing app.py as a read-only schema audit. Introduce
   explicit, verifiable additive migrations for the eventual accounting engine.

## First implementation increment

The subsequent dashboard/navigation increment is described in
`finance-dashboard.md`; it replaces the initial directory-style landing page.

- Add a permission-aware Finance & Accounting landing page in Core, with links
  to the existing sales, purchase, settlement, master, banking and report screens.
- Show current sales/repair and purchase invoice balances separately by currency,
  excluding draft/void/cancelled documents. These are **invoice balances**, not
  a reconciled AR/AP control balance; advances and opening balances are excluded.
- Classify repair bills using both invoice_category and existing job-card links,
  including older repair invoices. Count each invoice once, never each job link.
- Permit existing read-only repair-bill pages through either Core or Workshop
  entitlement while preserving their customer_invoices permission checks.
- Keep existing company/user overrides; accountant defaults gain finance and
  report viewing. No master, transaction, model or table is duplicated or renamed.

## Subsequent engine implementation (not delivered by this increment)

1. Reconcile deployed schema, source links, payment mirrors, balances and stock.
2. Add chart of accounts, journal headers/lines, period controls and source-event
   identities using additive migrations. Enforce balanced fixed-precision entries,
   company boundaries and unique source/revision identity at database level.
3. Post within the same database transaction as each operational financial
   event. Use reversals/corrections instead of overwriting posted history; cover
   edits, deletions, cancellation, retries and concurrent requests.
4. Integrate canonical sales/purchases/workshop invoices and settlements, then
   expenses, loans, transfers, cheque clearance, stock valuation/COGS and WIP.
   Preserve service/parts classification from workshop estimate/issue sources.
5. Link OrderFlow dispatch to existing sales documents with idempotent conversion.
   Orders and dispatch statuses alone must not create duplicate revenue.
6. Produce a dry-run historical migration and exceptions report; reconcile to
   source documents before backfilling journals and switching existing reports.
7. Test rollback, duplicate prevention, tenant/role isolation, tax splits, FX,
   backdating, opening balances and closed periods against MySQL as well as unit
   fixtures. HR/payroll remains outside this work.

## Validation of the first increment

`python -m unittest discover -s tests -v`: 24 tests passed, including six new
finance tests and the Core/Workshop entitlement regression. Coverage includes
tenant isolation, document status exclusions, currency separation, overdue date
boundaries, duplicate job links, old/new repair classification, login/company
requirements, restricted links/data and preservation of explicit access denials.
Changed Python and Jinja templates also passed syntax checks. Tests use isolated
in-memory databases and do not import the production application at startup.
Live MySQL integration and browser visual verification remain unperformed.

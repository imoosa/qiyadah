# Advanced finance delivery

Scope agreed: advanced finance without direct bank connectivity. Implementation
started 2026-10-03. This document records delivered work separately from planned work.

## Delivered: accounting checks and draft posting validation

- Finance → Accounting → Accounting Checks (`/finance/accounting-checks`).
- Company-scoped, read-only journal checks: drafts, unrecognised statuses,
  imbalance, invalid debit/credit lines, missing/foreign-company accounts,
  and duplicate active source postings.
- Authorised sales, repair and purchase invoice checks: missing active postings,
  inactive invoices with active postings, and base-currency total mismatches.
- Filters, pagination, links to review existing records, and explicit coverage limits.
- Revalidate draft journal accounts and line amounts at posting time, using the
  same validation as journal creation. An account deactivated after draft creation
  or belonging to another company cannot be posted.
- No automatic corrections, migrations, historical backfills, or bank connections.

Checks cover all stored dates. Invoice comparisons use original invoice totals;
separately posted receipts and credit/debit notes do not reduce those totals.
Reversed original journals remain in structural checks but do not count as active
invoice postings. Inactive historical accounts are not inherently invalid.

These diagnostics are not a certification of the books. Line-level invoice
tax/account mapping and full reversal integrity remain outside these increments.
A clean result does not mean those areas were checked. Implementation reads the company's journals
and authorised invoice records; benchmark and optimise for large deployments.

## Delivered: settlement and opening checks (second increment)

- Receipt/payment journals checked against source amount, direction, date and
  cash/bank versus receivable/payable/advance accounts. Comparison uses separate
  debit and credit totals per account, not net amounts that can hide extra lines.
- Missing source transactions, missing/multiple active settlement postings and
  malformed or excessive allocation amounts flagged for review.
- Company chart-of-account opening debits and credits compared; inactive accounts
  with openings flagged because current financial reports exclude them.
- Local bank balance reconstructed from its opening plus movements, excluding a
  single recognised opening mirror. Duplicate or ambiguous opening markers and
  unknown movement types stop that account's comparison and request review.
- Cash categories identify settlements. Bank rows without structural invoice links
  or existing settlement journals have unverified settlement coverage, shown in
  the page's coverage notice. They still participate in bank balance reconstruction.
- Respects bank, cash and receipt/payment permissions. Does not count PurchasePayment
  mirrors as additional movements. No repair, posting or bank connection is performed.

Remaining limitations after the second increment: allocation targets and aggregate invoice paid amounts were
not reconciled, customer/supplier opening balances were not matched to ledger control
accounts (legacy statement cutoffs need an explicit migration policy), bank openings
are not matched to ledger openings, and no external statement matching is performed.
Bank transactions lack currency fields: each bank is checked in its stored units,
without cross-account aggregation. Permission-excluded sources are outside coverage.

## Delivered: allocation targets and opening archives (third increment)

- Validates positive IDs, duplicate list entries, document type, movement direction,
  single-reference/breakdown consistency and exact totals for applied movements.
- Resolves receipt breakdowns against booking Invoice rows, not CustomerInvoice
  IDs. Resolves purchase allocations against PurchaseInvoice and separately checks
  customer invoice links. Missing/foreign-company and draft/cancelled targets are
  flagged without exposing other-company records. Inaccessible targets are counted
  as unverified, rather than asserted missing.
- Checks customer booking and supplier openings against their own latest closing
  archive: carried-forward amounts versus archive closing balance, and cleared
  openings versus zero. Missing cutoffs, missing archives and later differences
  are review items, never automatic corrections.
- Reads the separate legacy customer invoice opening/cutoff columns if present,
  with its own client_invoice archive family. Does not create missing columns.
- Openings without archive evidence require review of the common opening date and
  currency basis before any ledger-control comparison. A statement cutoff is not
  assumed to be the general ledger's opening date.
- Tests verify company and permission isolation, separate archive families,
  allocation types, malformed links and no database writes during checks.

Still not certified: aggregate invoice paid amounts, booking membership of customer
invoices, the actual archived cutoff boundary (archives do not store that boundary),
or opening-to-ledger alignment across currencies and migration dates. Archive
differences can be legitimate later edits; they are evidence to review.

## Delivered: payment evidence and booking rollups (fourth increment)

- Checks active customer-invoice booking lists for malformed/duplicate IDs,
  missing or inactive bookings, different customers and use on multiple authorised
  active invoices. No other-company invoice identifiers are disclosed.
- Compares invoice paid amounts with linked booking paid amounts, and invoice
  balance with total minus paid amount and credit-note adjustments.
- Checks pure customer-invoice receipt allocations against selected invoice booking
  memberships. Mixed receipts may also contain standalone bookings. Flags unused
  customer-invoice links and unavailable membership evidence separately.
- Aggregates structurally linked cash and bank allocations once per movement;
  a single reference and its breakdown are alternate representations, not extra
  payments. PurchasePayment mirrors are not added again.
- Compares these totals to recorded paid amounts for referenced booking/purchase
  documents only when both cash and bank access are available and parsing is
  unambiguous. Pre-statement-cutoff documents, missing party evidence and purchase
  currency conversion are excluded with explicit coverage counters.
- Differences are review evidence, not proof of missing payments: historical direct
  payments may not have structural links. Documents without usable links remain
  outside this comparison. Ambiguous transactions suppress that document family's
  total comparison rather than producing a misleading partial total.
- No records, schemas, or live bank connections are changed.

## Delivered: financial period control (fifth increment)

- Finance → Accounting → Financial Periods uses a company-specific closed-through
  date. Owner-only POST actions close further into the past or reopen all closed
  dates, requiring a reason, reconciliation acknowledgement, CSRF token and current
  control version. Repeated/stale submissions cannot silently change the cutoff.
- Records actor, UTC timestamp, previous/new cutoff, action, reason and version in
  an append-only application audit. GET requests do not close or reopen anything.
- Preflight blocks drafts, unknown journal status, unbalanced/invalid journal lines,
  wrong-company accounts and unbalanced chart-of-account opening totals. Other
  reconciliation evidence still requires the owner's review; close is not certification.
- Registered customer sessions validate old and new dates before ORM flush for
  journals, invoices and their lines, notes, cash/bank transactions, purchase payments,
  expenses, loans/repayments, cheques, fixed assets and stock purchase history.
- Closed source records are strictly immutable, including later paid-amount updates
  and reversal status updates. An owner must reopen to settle a closed invoice or
  reverse a closed journal. This is a conservative initial policy, not a workflow
  supporting post-close adjustments without reopening.
- Opening/classification changes and statement-closing writes are restricted.
  Bulk protected-table DML and non-read raw SQL through registered sessions are
  blocked while closed because their affected dates cannot be safely established.
- A company control row is locked for financial writes and close/reopen actions;
  original source/parent dates and close preflight use current locking reads.
- Adds two tables and an initially open control through existing customer database
  setup. Restart the app to initialise the new session factory. No production database
  was accessed, and no actual period was closed as part of implementation.

Limits: enforcement is in registered application sessions, not database triggers.
Direct DBA SQL, external tools, unregistered sessions and direct Connection writes
remain outside enforcement. Physical stock/workshop/HR operations without covered
financial source writes are outside this lock. Year-end retained-earnings transfers,
country-specific closing requirements and post-close adjustment workflows are not
implemented. MySQL multi-worker locking and production migration must be verified
before relying on these controls in production; tests use isolated SQLite fixtures.

## Remaining foundation validation

1. Establish a common dated/currency opening migration basis and resolve historical
   payment evidence exceptions against actual company records.
2. Verify MySQL concurrency and operational workflows against deployed data; extend
   locks to any integration paths that bypass registered customer sessions.
3. Add approval controls and reconcile all operational posting paths, including
   expenses, stock, loans and workshop activity.

## Subsequent planned modules

- Cost centres, project costing, inventory costing and cost allocation.
- Budgets and actuals, deferred revenue and recognition schedules.
- Purchase requisitions, approvals, goods receipts and three-way matching.
- Credit control, collection reminders and payment planning.
- Cash forecasting and working-capital scenarios.
- Statement imports and reconciliation without live bank connections.
- Country-specific compliance integrations after confirming jurisdiction and access.
- Configurable workflow automation. SAP Build connectivity is a separate integration.

## Validation and deployment

Tests run against isolated SQLite fixtures without importing application startup.
New tests exercise the real draft-posting route through extracted source functions,
and render the actual checks template within a minimal test shell. Existing finance
and sales-order tests must continue to pass. Live MySQL integration, full-shell
browser layout, historical data quality and production deployment are not verified
by these tests. No production database was migrated or repaired during this increment.

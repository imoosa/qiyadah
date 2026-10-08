# BI phases 5–7 implementation review

Reviewed against the supplied roadmap on 25 September 2026. This is a source-code review with isolated regression tests, not a verification of a deployed tenant or a visual browser review. Phase 6 is warehouse; Phase 7 is predictive analytics.

## Phase 5 — Custom dashboard builder: partial

Present: create/save/delete/duplicate dashboards, a 24-column canvas with movement and resizing, KPI/gauge/line/bar/pie/area/table visuals, built-in styles, saved global filters, selected chart drill-downs, and a field-based chart editor with dataset, measure, dimension and aggregation.

Missing or restricted:

- Dashboard access is owner/super-admin only. Visibility supports private/company owners, not assignment to selected roles or users.
- Map and funnel are not supported selectable widgets.
- Field-based configuration applies to custom charts; tables and KPIs use curated datasets.
- Only one business filter may be active at once. There are no per-widget filter definitions.
- Executive and custom dashboards still query the transactional metric engine, not the warehouse.

Corrected in this review: failed/invalid filter refreshes now clear old figures; older responses cannot replace newer results; switching dashboards invalidates pending loads; edits made during a save remain marked unsaved; a save completing after navigation cannot replace the selected dashboard.

## Phase 6 — Warehouse and ETL: partial

Present: five requested fact tables, sales/purchase line facts, six dimensions, company-scoped reads and refreshes, changed-row writes/deletions, transactional snapshot replacement, refresh history, failure logging and freshness warnings. Manual refresh and a per-company command-line refresh entry point exist.

Missing or restricted:

- Every refresh scans source records. Only writes are incremental; source extraction does not use change tracking or a watermark.
- No automatic schedule is configured by this implementation. The command requires an external scheduler.
- Branches are represented by an unassigned placeholder; source transactions lack an integrated branch key.
- Only predictive analytics consumes this warehouse. The roadmap's reduced transactional query load has not yet been achieved for other dashboards.
- Failure monitoring is a run-history screen, without notifications or recovery for abandoned running jobs.
- Location keys concatenate source text; long locations and delimiters need a durable key strategy before broader dimensional use.
- Date dimension currently contains transaction dates rather than a continuous calendar.

Corrected in this review: inventory movement value now uses the shared base-currency conversion fallback; line conversion follows the same exchange-rate rules as the common metric engine; missing transaction dates fail the refresh instead of silently being assigned today's date. Failed refreshes preserve the previous successful snapshot.

## Phase 7 — Predictive analytics: baseline indicators

Present: revenue and invoice-count forecasts, stock movement demand estimates, stock-out dates, replenishment quantities, net cash movement forecasts, inactivity indicators and unusual revenue-month detection.

Limitations relative to the intended result:

- Monthly forecasts repeat a trailing three-month average. They have recent error backtests, but no trend/seasonal model selection or evaluation by horizon.
- Revenue is billed total including tax, unlike net sales in the shared metric engine. This is disclosed in the existing assumptions but needs a unified metric definition.
- Sales forecast counts invoices; it does not forecast product quantities.
- Cash forecast projects net ledger movement, not a dated collections/payments plan or closing cash balance.
- Inventory demand uses OUT movements, which can include non-sale usage. Purchase recommendations omit outstanding purchase orders, supplier-specific lead times and pack sizes.
- Customer risk is a rule based on inactivity, not a churn probability model.
- Predictive queries are company-wide with no branch/product/customer filter controls.
- Old snapshots produce a warning; they do not stop the forecast from extending its history toward the current date. Snapshot-aware forecasting remains needed.

Corrected in this review: demand includes exactly 90 calendar days, not 91; sufficiently observed stock with no recent outbound movement produces zero estimated demand; insufficient-history rows retain current stock; nonpositive stock is identified as already depleted; customer-risk explanation matches its 180-day eligibility condition. Product/customer histories are grouped once to avoid repeatedly scanning every row for every entity.

## Recommended completion order

1. Agree canonical revenue, demand and cash metrics, then reconcile warehouse totals against the common metric engine using representative tenant data.
2. Complete warehouse refresh scheduling, concurrent-run/recovery handling, dimension keys and source change tracking; migrate supported BI datasets to warehouse reads.
3. Complete builder dataset coverage, independent widget filters, assignments and missing visuals; verify saved layouts in the browser.
4. Expand predictive models only after those inputs are reconciled; show snapshot coverage, assumptions and measured forecast error alongside predictions.

## Validation

- 13 Python BI regression tests pass against isolated in-memory tables.
- 6 JavaScript checks pass, covering save/load races, failure/invalid-date states and syntax of all three page scripts.
- No live ERP records were refreshed or modified. No deployment, scheduler activation, full ETL integration test or browser visual verification was performed.

These fixes improve reliability; they do not mark the three phases complete.

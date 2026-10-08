# Qiyadah AI assistant update

The assistant now uses Qiyadah ERP terminology, prompts and workflow guidance. The question catalog and verified screen links are maintained in utils/assistant_catalog.py. It includes sales, purchases, orders, inventory, receipts/payments, accounting checks, financial periods, credit/debit notes, reports, fixed assets, HR, CRM and company settings.

## Record answers

Sales totals, daily sales, invoice lookups, overdue invoices, client sales rankings and tax summaries now use CustomerInvoice instead of legacy booking Invoice records. Sales totals exclude Draft, Void and Cancelled records. Invoice details show product/service lines. Overdue counts cover all matching invoices even when the displayed list is capped. Customer invoice period queries honor calendar-month dates. Tax summaries report stored tax components rather than guessing a CGST/SGST split.

Existing party-balance helpers retain historical source records needed by ERP statements. Billing-based margin calculations are labeled as comparisons rather than inventory-adjusted accounting profit. Profit and Loss guidance opens the accounting report.

## Guidance and limitations

HR and CRM currently provide workflow guidance, not live payroll, attendance or pipeline totals. Finance guides explain records, reconciliation and period controls without executing changes. Bank figures are recorded ERP balances, not a bank feed. Current statutory tax rates and filing rules are not represented as verified live information. Logistics requests direct users to their separate logistics application.

Financial responses use deterministic formatting. Permissions are checked before dispatch, with composite checks for cross-module summaries. The shared assistant does not retain conversation messages across users. The legacy self-learning wrapper delegates to the same permission-checked implementation. Errors return an explicit unavailable response rather than invented numbers.

## Verification

140 tests pass, including 20 assistant-specific tests using isolated SQLite and mocked model calls. Tests cover suggested questions, registered guide links, blocked logistics intents, module permissions, cross-company filtering, sales invoice models, drafts/cancellations, overdue totals, calendar periods, recorded tax components, missing records and model-independent answers. Python compilation, Jinja parsing and syntax checks for eight inline scripts passed. No live application startup, database migration or live Ollama/browser session was performed.

Recovery copies of modified files are in backups/qiyadah_ai_20261003.

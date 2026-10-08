"""Static regression checks for Qiyadah Finance Steps 2-15.
Run: python regression_tests.py
These tests do not mutate the database.
"""
from pathlib import Path
import py_compile
from jinja2 import Environment

ROOT = Path(__file__).resolve().parent
app = (ROOT/"app.py").read_text(encoding="utf-8")
models = (ROOT/"customer_models.py").read_text(encoding="utf-8")
finance = (ROOT/"finance_workspace.py").read_text(encoding="utf-8")
base = (ROOT/"templates"/"base.html").read_text(encoding="utf-8")

checks = {
 "COA": "class ChartOfAccount" in models,
 "Journal engine": "class JournalEntry" in models and "class JournalEntryLine" in models,
 "Receivables": "_auto_post_customer_invoice" in app and '_auto_post_settlement(cdb, company_id, txn, "receipt")' in app,
 "Payables": "_auto_post_purchase_invoice" in app and '_auto_post_settlement(cdb, company_id, txn, "payment")' in app,
 "Workshop": "auto_post_customer_invoice" in (ROOT/"workshop_routes.py").read_text(encoding="utf-8"),
 "Expenses": "def _auto_post_expense" in app,
 "Ledger": "def ledger()" in app,
 "Trial Balance": "def trial_balance()" in app,
 "P&L": "def profit_loss()" in app,
 "Balance Sheet": "journal_totals = cdb.query" in app,
 "Cash Flow": "opening_cash_balance" in app,
 "Tax reporting": "def finance_tax_report()" in app,
 "Bank reconciliation": "class BankReconciliation" in models and "def bank_reconciliation()" in app,
 "Fixed assets": "class FixedAsset" in models and "def fixed_assets()" in app,
 "Depreciation journal": 'source_type="asset_depreciation"' in app,
 "Finance dashboard": "def finance_dashboard_view()" in app,
 "BI isolation": "use_bi_navigation" in base and "BI Intelligence is a separate workspace" in finance,
 "Bad workshop endpoint absent": "url_for('workshop_erp')" not in (ROOT/"templates"/"bi_intelligence.html").read_text(encoding="utf-8"),
}
for p in [ROOT/"app.py",ROOT/"customer_models.py",ROOT/"finance_workspace.py",ROOT/"workshop_routes.py"]:
    py_compile.compile(str(p), doraise=True)
env=Environment()
for p in (ROOT/"templates").glob("*.html"):
    env.parse(p.read_text(encoding="utf-8"))
failed=[k for k,v in checks.items() if not v]
for k,v in checks.items(): print(("PASS " if v else "FAIL ")+k)
if failed: raise SystemExit("FAILED: "+", ".join(failed))
print("PASS Python syntax")
print("PASS Jinja syntax")
print("ALL STATIC REGRESSION CHECKS PASSED")

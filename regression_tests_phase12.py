"""QIYADAH HR & Payroll Phase 12 — non-destructive packaged-source regression."""
from pathlib import Path
import py_compile
from jinja2 import Environment
ROOT=Path(__file__).resolve().parent
for name in ["app.py","customer_models.py","permissions.py","finance_workspace.py","hr_workspace.py","platform_models.py"]:
    py_compile.compile(str(ROOT/name),doraise=True)
env=Environment()
for p in (ROOT/"templates").glob("*.html"):
    env.parse(p.read_text(encoding="utf-8"))
hr=(ROOT/"hr_workspace.py").read_text(encoding="utf-8")
models=(ROOT/"customer_models.py").read_text(encoding="utf-8")
nav=(ROOT/"templates"/"_hr_navigation.html").read_text(encoding="utf-8")
checks={
"Payroll":"HRPayrollRun" in models and "def hr_payroll" in hr,
"Statutory":"HRStatutoryRule" in models,
"Loans/claims":"HREmployeeLoan" in models and "HRExpenseClaim" in models,
"Finance posting":"def _post_payroll_finance(" in hr and "def hr_payroll_pay(" in hr,
"Tenant migration":"ALTER TABLE hr_payroll_runs ADD COLUMN" in hr,
"Employee self-service":"def hr_my_dashboard(" in hr,
"Manager self-service":"def hr_manager_dashboard(" in hr,
"Recruitment":"def hr_recruitment(" in hr and "HRJobOpening" in models,
"Onboarding":"def hr_onboarding(" in hr,
"Performance":"def hr_performance(" in hr,
"Assets":"def hr_assets(" in hr,
"Movements":"def hr_movements(" in hr,
"Exits":"def hr_exits(" in hr,
"HR reports":"def hr_reports(" in hr,
"Attendance report":"def hr_attendance_report(" in hr,
"Leave report":"def hr_leave_report(" in hr,
"Payroll report":"def hr_payroll_report(" in hr,
"Salary register":"def hr_salary_register(" in hr,
"Statutory report":"def hr_statutory_report(" in hr,
"HR Intelligence":"def hr_bi_intelligence(" in hr,
"Navigation":"REPORTS & INTELLIGENCE" in nav and "SELF SERVICE" in nav,
"SQLAlchemy compatibility":"first_or_404()" not in hr,
}
for k,v in checks.items(): print(("PASS" if v else "FAIL"),k)
bad=[k for k,v in checks.items() if not v]
if bad: raise SystemExit("Failed: "+", ".join(bad))
print("PASS Python compilation")
print("PASS Jinja parsing")
print("PASS Phase 1-11 retention")

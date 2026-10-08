"""Qiyadah HR & Payroll workspace — Phase 1."""
from datetime import date, datetime, timedelta
from flask import render_template, request, redirect, url_for, flash, session, abort
from sqlalchemy import func, inspect, text
from customer_models import (
    HRDepartment, HRDesignation, HREmployee,
    HRShift, HRShiftAssignment, HRHoliday, HRAttendance,
    HRLeaveType, HRLeaveBalance, HRLeaveRequest, HROvertimeRequest,
    HRSalaryComponent, HRSalaryStructure, HRSalaryStructureLine, HREmployeeSalaryAssignment,
    HRPayrollRun, HRPayrollEntry, HRPayrollLine,
    HRStatutoryRule, HREmployeeStatutoryProfile, HRPayrollStatutoryLine,
    HREmployeeLoan, HRLoanRecovery, HRExpenseClaim,
    BankAccount, BankTransaction,
    HRJobOpening, HRCandidate, HROnboardingTask, HRPerformanceReview,
    HREmployeeAsset, HREmployeeMovement, HRExitCase
)

HR_ENDPOINTS = {
    "hr_dashboard", "hr_employees", "hr_employee_new", "hr_employee_view",
    "hr_employee_edit", "hr_departments", "hr_designations",
}

def register_hr_workspace(app, login_required, require_permission, get_cdb,
                          get_current_company, get_current_user, get_company_by_id,
                          post_auto_journal=None, ensure_chart_of_accounts=None):

    def ensure_tables(cdb):
        """Create the HR schema in the ACTIVE tenant DB and apply additive HR migrations."""
        engine = cdb.get_bind()
        models = (HRDepartment, HRDesignation, HREmployee, HRShift, HRShiftAssignment, HRHoliday, HRAttendance,
                  HRLeaveType, HRLeaveBalance, HRLeaveRequest, HROvertimeRequest,
                  HRSalaryComponent, HRSalaryStructure, HRSalaryStructureLine, HREmployeeSalaryAssignment,
                  HRPayrollRun, HRPayrollEntry, HRPayrollLine,
                  HRStatutoryRule, HREmployeeStatutoryProfile, HRPayrollStatutoryLine,
                  HREmployeeLoan, HRLoanRecovery, HRExpenseClaim,
                  HRJobOpening, HRCandidate, HROnboardingTask, HRPerformanceReview,
                  HREmployeeAsset, HREmployeeMovement, HRExitCase)
        for model in models:
            model.__table__.create(bind=engine, checkfirst=True)

        # Phase 8 introduced fields on an already-existing table. SQLAlchemy's
        # checkfirst creates missing tables but never adds missing columns.
        # Keep this migration additive and idempotent for every tenant DB.
        cols={c["name"] for c in inspect(engine).get_columns("hr_payroll_runs")}
        additions=[
            ("finance_posted_at","DATETIME NULL"),
            ("finance_posted_by","VARCHAR(255) NULL"),
            ("payment_status","VARCHAR(20) NOT NULL DEFAULT 'Unpaid'"),
            ("paid_at","DATETIME NULL"),
            ("paid_by","VARCHAR(255) NULL"),
            ("bank_transaction_id","INTEGER NULL"),
        ]
        with engine.begin() as conn:
            for name, ddl in additions:
                if name not in cols:
                    conn.execute(text(f"ALTER TABLE hr_payroll_runs ADD COLUMN {name} {ddl}"))

    def _first_or_404(query):
        row=query.first()
        if row is None:
            abort(404)
        return row

    def scoped(cdb, model, company_id, pk):
        return _first_or_404(cdb.query(model).filter_by(id=pk, company_id=company_id))

    @app.route("/hr")
    @login_required
    @require_permission("hr", "view")
    def hr_dashboard():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        total=cdb.query(HREmployee).filter_by(company_id=company_id).count()
        active=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").count()
        departments=cdb.query(HRDepartment).filter_by(company_id=company_id,is_active=True).count()
        designations=cdb.query(HRDesignation).filter_by(company_id=company_id,is_active=True).count()
        recent=cdb.query(HREmployee).filter_by(company_id=company_id).order_by(HREmployee.id.desc()).limit(8).all()
        today=date.today()
        today_rows=cdb.query(HRAttendance).filter_by(company_id=company_id, attendance_date=today).all()
        present_today=sum(1 for r in today_rows if r.status in ("Present","Late","Half Day"))
        late_today=sum(1 for r in today_rows if r.late_minutes > 0)
        absent_today=max(0, active-present_today)
        return render_template("hr_dashboard.html", active="hr_dashboard",
            total_employees=total, active_employees=active, department_count=departments,
            designation_count=designations, recent_employees=recent,
            present_today=present_today, late_today=late_today, absent_today=absent_today,
            company=get_company_by_id(company_id))

    @app.route("/hr/employees")
    @login_required
    @require_permission("hr_employees", "view")
    def hr_employees():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        q=cdb.query(HREmployee).filter_by(company_id=company_id)
        search=(request.args.get("q") or "").strip()
        status=(request.args.get("status") or "").strip()
        department_id=request.args.get("department_id",type=int)
        if search:
            term=f"%{search}%"
            q=q.filter((HREmployee.full_name.ilike(term)) | (HREmployee.employee_code.ilike(term)) | (HREmployee.email.ilike(term)))
        if status: q=q.filter(HREmployee.status==status)
        if department_id: q=q.filter(HREmployee.department_id==department_id)
        employees=q.order_by(HREmployee.full_name).all()
        departments=cdb.query(HRDepartment).filter_by(company_id=company_id,is_active=True).order_by(HRDepartment.name).all()
        return render_template("hr_employees.html",active="hr_employees",employees=employees,departments=departments)

    @app.route("/hr/employees/new", methods=["GET","POST"])
    @login_required
    @require_permission("hr_employees", "create")
    def hr_employee_new():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        departments=cdb.query(HRDepartment).filter_by(company_id=company_id,is_active=True).order_by(HRDepartment.name).all()
        designations=cdb.query(HRDesignation).filter_by(company_id=company_id,is_active=True).order_by(HRDesignation.name).all()
        managers=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").order_by(HREmployee.full_name).all()
        if request.method=="POST":
            code=(request.form.get("employee_code") or "").strip()
            name=(request.form.get("full_name") or "").strip()
            if not code or not name:
                flash("Employee code and full name are required.","error")
                return render_template("hr_employee_form.html",employee=None,departments=departments,designations=designations,managers=managers)
            if cdb.query(HREmployee).filter_by(company_id=company_id,employee_code=code).first():
                flash("Employee code already exists.","error")
                return render_template("hr_employee_form.html",employee=None,departments=departments,designations=designations,managers=managers)
            e=HREmployee(company_id=company_id,employee_code=code,full_name=name)
            _apply_employee_form(e, request.form)
            cdb.add(e); cdb.commit()
            flash("Employee created successfully.","success")
            return redirect(url_for("hr_employee_view",employee_id=e.id))
        return render_template("hr_employee_form.html",active="hr_employees",employee=None,departments=departments,designations=designations,managers=managers)

    @app.route("/hr/employees/<int:employee_id>")
    @login_required
    @require_permission("hr_employees", "view")
    def hr_employee_view(employee_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        return render_template("hr_employee_view.html",active="hr_employees",employee=scoped(cdb,HREmployee,company_id,employee_id))

    @app.route("/hr/employees/<int:employee_id>/edit", methods=["GET","POST"])
    @login_required
    @require_permission("hr_employees", "edit")
    def hr_employee_edit(employee_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        e=scoped(cdb,HREmployee,company_id,employee_id)
        departments=cdb.query(HRDepartment).filter_by(company_id=company_id,is_active=True).order_by(HRDepartment.name).all()
        designations=cdb.query(HRDesignation).filter_by(company_id=company_id,is_active=True).order_by(HRDesignation.name).all()
        managers=cdb.query(HREmployee).filter(HREmployee.company_id==company_id,HREmployee.status=="Active",HREmployee.id!=e.id).order_by(HREmployee.full_name).all()
        if request.method=="POST":
            code=(request.form.get("employee_code") or "").strip()
            duplicate=cdb.query(HREmployee).filter(HREmployee.company_id==company_id,HREmployee.employee_code==code,HREmployee.id!=e.id).first()
            if duplicate:
                flash("Employee code already exists.","error")
            else:
                e.employee_code=code; e.full_name=(request.form.get("full_name") or "").strip()
                _apply_employee_form(e,request.form); cdb.commit()
                flash("Employee updated successfully.","success")
                return redirect(url_for("hr_employee_view",employee_id=e.id))
        return render_template("hr_employee_form.html",active="hr_employees",employee=e,departments=departments,designations=designations,managers=managers)

    @app.route("/hr/departments", methods=["GET","POST"])
    @login_required
    @require_permission("hr_masters", "view")
    def hr_departments():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        if request.method=="POST":
            name=(request.form.get("name") or "").strip()
            if name and not cdb.query(HRDepartment).filter_by(company_id=company_id,name=name).first():
                cdb.add(HRDepartment(company_id=company_id,name=name,code=(request.form.get("code") or "").strip() or None,
                                     description=(request.form.get("description") or "").strip() or None))
                cdb.commit(); flash("Department added.","success")
            else: flash("Department name is required or already exists.","error")
            return redirect(url_for("hr_departments"))
        rows=cdb.query(HRDepartment).filter_by(company_id=company_id).order_by(HRDepartment.name).all()
        return render_template("hr_master.html",active="hr_departments",kind="Department",rows=rows,endpoint="hr_departments")

    @app.route("/hr/designations", methods=["GET","POST"])
    @login_required
    @require_permission("hr_masters", "view")
    def hr_designations():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        if request.method=="POST":
            name=(request.form.get("name") or "").strip()
            if name and not cdb.query(HRDesignation).filter_by(company_id=company_id,name=name).first():
                cdb.add(HRDesignation(company_id=company_id,name=name,code=(request.form.get("code") or "").strip() or None,
                                      level=(request.form.get("level") or "").strip() or None,
                                      description=(request.form.get("description") or "").strip() or None))
                cdb.commit(); flash("Designation added.","success")
            else: flash("Designation name is required or already exists.","error")
            return redirect(url_for("hr_designations"))
        rows=cdb.query(HRDesignation).filter_by(company_id=company_id).order_by(HRDesignation.name).all()
        return render_template("hr_master.html",active="hr_designations",kind="Designation",rows=rows,endpoint="hr_designations")

    @app.route("/hr/shifts", methods=["GET","POST"])
    @login_required
    @require_permission("hr_shifts", "view")
    def hr_shifts():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        if request.method=="POST":
            name=(request.form.get("name") or "").strip()
            if not name:
                flash("Shift name is required.","error")
            elif cdb.query(HRShift).filter_by(company_id=company_id,name=name).first():
                flash("Shift name already exists.","error")
            else:
                shift=HRShift(
                    company_id=company_id,name=name,code=(request.form.get("code") or "").strip() or None,
                    start_time=request.form.get("start_time") or "09:00",end_time=request.form.get("end_time") or "18:00",
                    break_minutes=_int(request.form.get("break_minutes"),60),
                    grace_minutes=_int(request.form.get("grace_minutes"),10),
                    half_day_hours=_float(request.form.get("half_day_hours"),4),
                    full_day_hours=_float(request.form.get("full_day_hours"),8),
                    overtime_after_minutes=_int(request.form.get("overtime_after_minutes"),0),
                    weekly_off_days=",".join(request.form.getlist("weekly_off_days")) or "Sunday")
                cdb.add(shift); cdb.commit(); flash("Shift created.","success")
            return redirect(url_for("hr_shifts"))
        shifts=cdb.query(HRShift).filter_by(company_id=company_id).order_by(HRShift.name).all()
        employees=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").order_by(HREmployee.full_name).all()
        assignments=cdb.query(HRShiftAssignment).filter_by(company_id=company_id).order_by(HRShiftAssignment.effective_from.desc()).limit(100).all()
        return render_template("hr_shifts.html",active="hr_shifts",shifts=shifts,employees=employees,assignments=assignments)

    @app.route("/hr/shifts/assign", methods=["POST"])
    @login_required
    @require_permission("hr_shifts", "edit")
    def hr_shift_assign():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employee_id=_int(request.form.get("employee_id")); shift_id=_int(request.form.get("shift_id"))
        employee=cdb.query(HREmployee).filter_by(id=employee_id,company_id=company_id).first()
        shift=cdb.query(HRShift).filter_by(id=shift_id,company_id=company_id).first()
        if not employee or not shift:
            flash("Valid employee and shift are required.","error")
        else:
            effective=_as_date(request.form.get("effective_from")) or date.today()
            # Close currently-open assignment the day before the new one begins.
            open_rows=cdb.query(HRShiftAssignment).filter_by(company_id=company_id,employee_id=employee.id,effective_to=None).all()
            for row in open_rows:
                if row.effective_from <= effective:
                    row.effective_to=effective-timedelta(days=1)
            cdb.add(HRShiftAssignment(company_id=company_id,employee_id=employee.id,shift_id=shift.id,effective_from=effective))
            cdb.commit(); flash("Shift assigned.","success")
        return redirect(url_for("hr_shifts"))

    @app.route("/hr/holidays", methods=["GET","POST"])
    @login_required
    @require_permission("hr_holidays", "view")
    def hr_holidays():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        if request.method=="POST":
            hdate=_as_date(request.form.get("holiday_date")); name=(request.form.get("name") or "").strip()
            if not hdate or not name:
                flash("Holiday date and name are required.","error")
            else:
                exists=cdb.query(HRHoliday).filter_by(company_id=company_id,holiday_date=hdate,name=name).first()
                if exists: flash("This holiday already exists.","error")
                else:
                    cdb.add(HRHoliday(company_id=company_id,holiday_date=hdate,name=name,
                        holiday_type=request.form.get("holiday_type") or "Company Holiday",
                        branch=(request.form.get("branch") or "").strip() or None,
                        is_optional=bool(request.form.get("is_optional")),
                        notes=(request.form.get("notes") or "").strip() or None))
                    cdb.commit(); flash("Holiday added.","success")
            return redirect(url_for("hr_holidays"))
        year=request.args.get("year",type=int) or date.today().year
        rows=cdb.query(HRHoliday).filter(HRHoliday.company_id==company_id,
            HRHoliday.holiday_date>=date(year,1,1),HRHoliday.holiday_date<=date(year,12,31)).order_by(HRHoliday.holiday_date).all()
        return render_template("hr_holidays.html",active="hr_holidays",rows=rows,year=year)

    @app.route("/hr/attendance")
    @login_required
    @require_permission("hr_attendance", "view")
    def hr_attendance():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        day=_as_date(request.args.get("date")) or date.today()
        employees=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").order_by(HREmployee.full_name).all()
        existing={r.employee_id:r for r in cdb.query(HRAttendance).filter_by(company_id=company_id,attendance_date=day).all()}
        rows=[]
        for e in employees:
            shift=_shift_for(cdb,company_id,e.id,day)
            att=existing.get(e.id)
            holiday=_holiday_for(cdb,company_id,e,day)
            weekly_off=bool(shift and day.strftime("%A") in _weekly_offs(shift))
            expected="Holiday" if holiday else ("Weekly Off" if weekly_off else "Working Day")
            rows.append(dict(employee=e,attendance=att,shift=shift,expected=expected,holiday=holiday))
        return render_template("hr_attendance.html",active="hr_attendance",rows=rows,day=day)

    @app.route("/hr/attendance/save", methods=["POST"])
    @login_required
    @require_permission("hr_attendance", "edit")
    def hr_attendance_save():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        day=_as_date(request.form.get("attendance_date")) or date.today()
        employee_id=_int(request.form.get("employee_id"))
        employee=cdb.query(HREmployee).filter_by(id=employee_id,company_id=company_id).first()
        if not employee:
            flash("Employee not found.","error"); return redirect(url_for("hr_attendance",date=day.isoformat()))
        shift=_shift_for(cdb,company_id,employee.id,day)
        att=cdb.query(HRAttendance).filter_by(company_id=company_id,employee_id=employee.id,attendance_date=day).first()
        if not att:
            att=HRAttendance(company_id=company_id,employee_id=employee.id,attendance_date=day,source="Manual")
            cdb.add(att)
        att.shift_id=shift.id if shift else None
        att.check_in=_combine(day,request.form.get("check_in"))
        att.check_out=_combine(day,request.form.get("check_out"))
        if att.check_in and att.check_out and att.check_out < att.check_in:
            att.check_out += timedelta(days=1)
        att.notes=(request.form.get("notes") or "").strip() or None
        _calculate_attendance(att,shift,_holiday_for(cdb,company_id,employee,day))
        cdb.commit(); flash(f"Attendance saved for {employee.full_name}.","success")
        return redirect(url_for("hr_attendance",date=day.isoformat()))

    @app.route("/hr/attendance/check-in/<int:employee_id>", methods=["POST"])
    @login_required
    @require_permission("hr_attendance", "edit")
    def hr_attendance_check_in(employee_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employee=_first_or_404(cdb.query(HREmployee).filter_by(id=employee_id,company_id=company_id,status="Active"))
        now=datetime.now(); day=now.date(); shift=_shift_for(cdb,company_id,employee.id,day)
        att=cdb.query(HRAttendance).filter_by(company_id=company_id,employee_id=employee.id,attendance_date=day).first()
        if not att:
            att=HRAttendance(company_id=company_id,employee_id=employee.id,attendance_date=day,source="Web",shift_id=shift.id if shift else None)
            cdb.add(att)
        if not att.check_in: att.check_in=now
        _calculate_attendance(att,shift,_holiday_for(cdb,company_id,employee,day))
        cdb.commit(); flash(f"{employee.full_name} checked in.","success")
        return redirect(url_for("hr_attendance",date=day.isoformat()))

    @app.route("/hr/attendance/check-out/<int:employee_id>", methods=["POST"])
    @login_required
    @require_permission("hr_attendance", "edit")
    def hr_attendance_check_out(employee_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employee=_first_or_404(cdb.query(HREmployee).filter_by(id=employee_id,company_id=company_id,status="Active"))
        now=datetime.now(); day=now.date(); shift=_shift_for(cdb,company_id,employee.id,day)
        att=cdb.query(HRAttendance).filter_by(company_id=company_id,employee_id=employee.id,attendance_date=day).first()
        if not att or not att.check_in:
            flash("Check-in is required before check-out.","error")
        else:
            att.check_out=now; _calculate_attendance(att,shift,_holiday_for(cdb,company_id,employee,day)); cdb.commit()
            flash(f"{employee.full_name} checked out.","success")
        return redirect(url_for("hr_attendance",date=day.isoformat()))


    @app.route("/hr/leave-types", methods=["GET","POST"])
    @login_required
    @require_permission("hr_leave", "view")
    def hr_leave_types():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        if request.method=="POST":
            name=(request.form.get("name") or "").strip()
            if not name:
                flash("Leave type name is required.","error")
            elif cdb.query(HRLeaveType).filter_by(company_id=company_id,name=name).first():
                flash("Leave type already exists.","error")
            else:
                cdb.add(HRLeaveType(company_id=company_id,name=name,
                    code=(request.form.get("code") or "").strip() or None,
                    annual_entitlement=_float(request.form.get("annual_entitlement"),0),
                    is_paid=bool(request.form.get("is_paid")),
                    carry_forward=bool(request.form.get("carry_forward")),
                    max_carry_forward=_float(request.form.get("max_carry_forward"),0),
                    requires_approval=bool(request.form.get("requires_approval"))))
                cdb.commit(); flash("Leave type created.","success")
            return redirect(url_for("hr_leave_types"))
        rows=cdb.query(HRLeaveType).filter_by(company_id=company_id).order_by(HRLeaveType.name).all()
        return render_template("hr_leave_types.html",active="hr_leave_types",rows=rows)

    @app.route("/hr/leave-balances", methods=["GET","POST"])
    @login_required
    @require_permission("hr_leave", "view")
    def hr_leave_balances():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        year=request.args.get("year",type=int) or request.form.get("year",type=int) or date.today().year
        employees=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").order_by(HREmployee.full_name).all()
        types=cdb.query(HRLeaveType).filter_by(company_id=company_id,is_active=True).order_by(HRLeaveType.name).all()
        if request.method=="POST":
            employee_id=_int(request.form.get("employee_id")); type_id=_int(request.form.get("leave_type_id"))
            employee=cdb.query(HREmployee).filter_by(id=employee_id,company_id=company_id).first()
            lt=cdb.query(HRLeaveType).filter_by(id=type_id,company_id=company_id).first()
            if employee and lt:
                bal=cdb.query(HRLeaveBalance).filter_by(company_id=company_id,employee_id=employee.id,leave_type_id=lt.id,year=year).first()
                if not bal:
                    bal=HRLeaveBalance(company_id=company_id,employee_id=employee.id,leave_type_id=lt.id,year=year,entitled=lt.annual_entitlement)
                    cdb.add(bal)
                bal.opening_balance=_float(request.form.get("opening_balance"),bal.opening_balance or 0)
                bal.entitled=_float(request.form.get("entitled"),lt.annual_entitlement)
                bal.adjusted=_float(request.form.get("adjusted"),bal.adjusted or 0)
                cdb.commit(); flash("Leave balance updated.","success")
            else: flash("Valid employee and leave type are required.","error")
            return redirect(url_for("hr_leave_balances",year=year))
        _seed_leave_balances(cdb,company_id,employees,types,year)
        balances=cdb.query(HRLeaveBalance).filter_by(company_id=company_id,year=year).all()
        return render_template("hr_leave_balances.html",active="hr_leave_balances",balances=balances,employees=employees,types=types,year=year)

    @app.route("/hr/leaves", methods=["GET","POST"])
    @login_required
    @require_permission("hr_leave", "view")
    def hr_leaves():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employees=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").order_by(HREmployee.full_name).all()
        types=cdb.query(HRLeaveType).filter_by(company_id=company_id,is_active=True).order_by(HRLeaveType.name).all()
        if request.method=="POST":
            employee_id=_int(request.form.get("employee_id")); type_id=_int(request.form.get("leave_type_id"))
            start=_as_date(request.form.get("start_date")); end=_as_date(request.form.get("end_date")); part=request.form.get("day_part") or "Full Day"
            employee=cdb.query(HREmployee).filter_by(id=employee_id,company_id=company_id).first()
            lt=cdb.query(HRLeaveType).filter_by(id=type_id,company_id=company_id,is_active=True).first()
            if not employee or not lt or not start or not end or end < start:
                flash("Valid employee, leave type and date range are required.","error")
            else:
                overlap=cdb.query(HRLeaveRequest).filter(HRLeaveRequest.company_id==company_id,HRLeaveRequest.employee_id==employee.id,
                    HRLeaveRequest.status.in_(("Pending","Approved")),HRLeaveRequest.start_date<=end,HRLeaveRequest.end_date>=start).first()
                if overlap: flash("This employee already has an overlapping leave request.","error")
                else:
                    days=_leave_days(cdb,company_id,employee,start,end,part)
                    if days <= 0: flash("Selected dates contain no chargeable leave days.","error")
                    else:
                        year=start.year; _seed_leave_balances(cdb,company_id,[employee],[lt],year)
                        bal=cdb.query(HRLeaveBalance).filter_by(company_id=company_id,employee_id=employee.id,leave_type_id=lt.id,year=year).first()
                        if lt.is_paid and bal and bal.available < days:
                            flash(f"Insufficient {lt.name} balance. Available: {bal.available:g} day(s).","error")
                        else:
                            status="Pending" if lt.requires_approval else "Approved"
                            req=HRLeaveRequest(company_id=company_id,employee_id=employee.id,leave_type_id=lt.id,start_date=start,end_date=end,
                                days=days,day_part=part,reason=(request.form.get("reason") or "").strip() or None,status=status)
                            cdb.add(req); cdb.flush()
                            if status=="Approved":
                                _apply_leave_approval(cdb,company_id,req,get_current_user(),None)
                            cdb.commit(); flash("Leave request submitted.","success")
            return redirect(url_for("hr_leaves"))
        status=(request.args.get("status") or "").strip()
        q=cdb.query(HRLeaveRequest).filter_by(company_id=company_id)
        if status: q=q.filter(HRLeaveRequest.status==status)
        rows=q.order_by(HRLeaveRequest.requested_at.desc()).limit(250).all()
        return render_template("hr_leaves.html",active="hr_leaves",rows=rows,employees=employees,types=types)

    @app.route("/hr/leaves/<int:leave_id>/approve", methods=["POST"])
    @login_required
    @require_permission("hr_leave", "edit")
    def hr_leave_approve(leave_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        req=_first_or_404(cdb.query(HRLeaveRequest).filter_by(id=leave_id,company_id=company_id))
        if req.status!="Pending":
            flash("Only pending leave requests can be approved.","error")
        else:
            bal=cdb.query(HRLeaveBalance).filter_by(company_id=company_id,employee_id=req.employee_id,leave_type_id=req.leave_type_id,year=req.start_date.year).first()
            if req.leave_type.is_paid and bal and bal.available < req.days:
                flash("Insufficient leave balance for approval.","error")
            else:
                _apply_leave_approval(cdb,company_id,req,get_current_user(),request.form.get("approval_notes"))
                cdb.commit(); flash("Leave approved and attendance updated.","success")
        return redirect(url_for("hr_leaves"))

    @app.route("/hr/leaves/<int:leave_id>/reject", methods=["POST"])
    @login_required
    @require_permission("hr_leave", "edit")
    def hr_leave_reject(leave_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        req=_first_or_404(cdb.query(HRLeaveRequest).filter_by(id=leave_id,company_id=company_id))
        if req.status!="Pending": flash("Only pending leave requests can be rejected.","error")
        else:
            req.status="Rejected"; req.approved_by=_actor(get_current_user()); req.approved_at=datetime.utcnow()
            req.approval_notes=(request.form.get("approval_notes") or "").strip() or None
            cdb.commit(); flash("Leave rejected.","success")
        return redirect(url_for("hr_leaves"))

    @app.route("/hr/overtime")
    @login_required
    @require_permission("hr_overtime", "view")
    def hr_overtime():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        # Auto-create requests for calculated OT that has not yet entered approval.
        candidates=cdb.query(HRAttendance).filter(HRAttendance.company_id==company_id,HRAttendance.overtime_minutes>0).all()
        for a in candidates:
            if not cdb.query(HROvertimeRequest).filter_by(company_id=company_id,attendance_id=a.id).first():
                cdb.add(HROvertimeRequest(company_id=company_id,attendance_id=a.id,employee_id=a.employee_id,requested_minutes=a.overtime_minutes,status="Pending"))
        cdb.commit()
        rows=cdb.query(HROvertimeRequest).filter_by(company_id=company_id).order_by(HROvertimeRequest.id.desc()).limit(250).all()
        return render_template("hr_overtime.html",active="hr_overtime",rows=rows)

    @app.route("/hr/overtime/<int:ot_id>/decision", methods=["POST"])
    @login_required
    @require_permission("hr_overtime", "edit")
    def hr_overtime_decision(ot_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        row=_first_or_404(cdb.query(HROvertimeRequest).filter_by(id=ot_id,company_id=company_id))
        decision=request.form.get("decision")
        if row.status!="Pending" or decision not in ("Approved","Rejected"):
            flash("Invalid overtime decision.","error")
        else:
            row.status=decision; row.approved_by=_actor(get_current_user()); row.approved_at=datetime.utcnow()
            row.approved_minutes=min(row.requested_minutes,max(0,_int(request.form.get("approved_minutes"),row.requested_minutes))) if decision=="Approved" else 0
            row.reason=(request.form.get("reason") or "").strip() or row.reason
            cdb.commit(); flash(f"Overtime {decision.lower()}.","success")
        return redirect(url_for("hr_overtime"))


    @app.route("/hr/salary-components", methods=["GET","POST"])
    @login_required
    @require_permission("hr_salary", "view")
    def hr_salary_components():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        if request.method=="POST":
            name=(request.form.get("name") or "").strip()
            if not name:
                flash("Component name is required.","error")
            elif cdb.query(HRSalaryComponent).filter_by(company_id=company_id,name=name).first():
                flash("Salary component already exists.","error")
            else:
                cdb.add(HRSalaryComponent(company_id=company_id,name=name,
                    code=(request.form.get("code") or "").strip() or None,
                    component_type=request.form.get("component_type") or "Earning",
                    calculation_type=request.form.get("calculation_type") or "Fixed",
                    default_value=_money(request.form.get("default_value")),
                    taxable=bool(request.form.get("taxable")),
                    affects_gross=bool(request.form.get("affects_gross")),
                    is_statutory=bool(request.form.get("is_statutory")),
                    sort_order=_int(request.form.get("sort_order"),100)))
                cdb.commit(); flash("Salary component created.","success")
            return redirect(url_for("hr_salary_components"))
        rows=cdb.query(HRSalaryComponent).filter_by(company_id=company_id).order_by(HRSalaryComponent.component_type,HRSalaryComponent.sort_order,HRSalaryComponent.name).all()
        return render_template("hr_salary_components.html",active="hr_salary_components",rows=rows)

    @app.route("/hr/salary-structures", methods=["GET","POST"])
    @login_required
    @require_permission("hr_salary", "view")
    def hr_salary_structures():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        if request.method=="POST":
            name=(request.form.get("name") or "").strip()
            if not name: flash("Structure name is required.","error")
            elif cdb.query(HRSalaryStructure).filter_by(company_id=company_id,name=name).first():
                flash("Salary structure already exists.","error")
            else:
                st=HRSalaryStructure(company_id=company_id,name=name,code=(request.form.get("code") or "").strip() or None,
                    description=(request.form.get("description") or "").strip() or None,
                    pay_frequency=request.form.get("pay_frequency") or "Monthly")
                cdb.add(st); cdb.commit(); flash("Salary structure created.","success")
                return redirect(url_for("hr_salary_structure_view",structure_id=st.id))
            return redirect(url_for("hr_salary_structures"))
        rows=cdb.query(HRSalaryStructure).filter_by(company_id=company_id).order_by(HRSalaryStructure.name).all()
        return render_template("hr_salary_structures.html",active="hr_salary_structures",rows=rows)

    @app.route("/hr/salary-structures/<int:structure_id>", methods=["GET","POST"])
    @login_required
    @require_permission("hr_salary", "view")
    def hr_salary_structure_view(structure_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        st=_first_or_404(cdb.query(HRSalaryStructure).filter_by(id=structure_id,company_id=company_id))
        components=cdb.query(HRSalaryComponent).filter_by(company_id=company_id,is_active=True).order_by(HRSalaryComponent.component_type,HRSalaryComponent.sort_order).all()
        if request.method=="POST":
            component_id=_int(request.form.get("component_id"))
            comp=cdb.query(HRSalaryComponent).filter_by(id=component_id,company_id=company_id,is_active=True).first()
            if not comp: flash("Valid salary component is required.","error")
            elif cdb.query(HRSalaryStructureLine).filter_by(structure_id=st.id,component_id=comp.id).first():
                flash("Component already exists in this structure.","error")
            else:
                cdb.add(HRSalaryStructureLine(structure_id=st.id,component_id=comp.id,
                    value=_money(request.form.get("value")),
                    calculation_type=request.form.get("calculation_type") or comp.calculation_type,
                    sort_order=_int(request.form.get("sort_order"),comp.sort_order or 100)))
                cdb.commit(); flash("Component added to structure.","success")
            return redirect(url_for("hr_salary_structure_view",structure_id=st.id))
        return render_template("hr_salary_structure_view.html",active="hr_salary_structures",structure=st,components=components)

    @app.route("/hr/salary-structures/<int:structure_id>/lines/<int:line_id>/delete", methods=["POST"])
    @login_required
    @require_permission("hr_salary", "edit")
    def hr_salary_structure_line_delete(structure_id,line_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        st=_first_or_404(cdb.query(HRSalaryStructure).filter_by(id=structure_id,company_id=company_id))
        line=_first_or_404(cdb.query(HRSalaryStructureLine).filter_by(id=line_id,structure_id=st.id))
        cdb.delete(line); cdb.commit(); flash("Component removed.","success")
        return redirect(url_for("hr_salary_structure_view",structure_id=st.id))

    @app.route("/hr/salary-assignments", methods=["GET","POST"])
    @login_required
    @require_permission("hr_salary", "view")
    def hr_salary_assignments():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employees=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").order_by(HREmployee.full_name).all()
        structures=cdb.query(HRSalaryStructure).filter_by(company_id=company_id,is_active=True).order_by(HRSalaryStructure.name).all()
        if request.method=="POST":
            employee_id=_int(request.form.get("employee_id")); structure_id=_int(request.form.get("structure_id"))
            employee=cdb.query(HREmployee).filter_by(id=employee_id,company_id=company_id).first()
            st=cdb.query(HRSalaryStructure).filter_by(id=structure_id,company_id=company_id,is_active=True).first()
            effective=_as_date(request.form.get("effective_from")) or date.today()
            basic=_money(request.form.get("basic_monthly")); annual_ctc=_money(request.form.get("annual_ctc"))
            if not employee or not st:
                flash("Valid employee and salary structure are required.","error")
            else:
                # Close only assignments that are active when the new assignment begins.
                open_rows=cdb.query(HREmployeeSalaryAssignment).filter(
                    HREmployeeSalaryAssignment.company_id==company_id,
                    HREmployeeSalaryAssignment.employee_id==employee.id,
                    HREmployeeSalaryAssignment.effective_from<=effective,
                    (HREmployeeSalaryAssignment.effective_to==None) | (HREmployeeSalaryAssignment.effective_to>=effective)).all()
                for row in open_rows: row.effective_to=effective-timedelta(days=1)
                cdb.add(HREmployeeSalaryAssignment(company_id=company_id,employee_id=employee.id,structure_id=st.id,
                    effective_from=effective,basic_monthly=basic,annual_ctc=annual_ctc,
                    notes=(request.form.get("notes") or "").strip() or None))
                cdb.commit(); flash("Salary structure assigned.","success")
            return redirect(url_for("hr_salary_assignments"))
        rows=cdb.query(HREmployeeSalaryAssignment).filter_by(company_id=company_id).order_by(HREmployeeSalaryAssignment.effective_from.desc(),HREmployeeSalaryAssignment.id.desc()).limit(250).all()
        previews=[]
        for row in rows:
            calc=_salary_preview(row)
            previews.append((row,calc))
        return render_template("hr_salary_assignments.html",active="hr_salary_assignments",employees=employees,structures=structures,previews=previews)


    @app.route("/hr/payroll", methods=["GET","POST"])
    @login_required
    @require_permission("hr_payroll", "view")
    def hr_payroll():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        if request.method=="POST":
            year=_int(request.form.get("year"),date.today().year)
            month=_int(request.form.get("month"),date.today().month)
            if month < 1 or month > 12:
                flash("Valid payroll month is required.","error")
            elif cdb.query(HRPayrollRun).filter_by(company_id=company_id,year=year,month=month).first():
                flash("A payroll run already exists for this month.","error")
            else:
                run=HRPayrollRun(company_id=company_id,year=year,month=month,status="Draft",
                    created_by=_actor(get_current_user()),notes=(request.form.get("notes") or "").strip() or None)
                cdb.add(run); cdb.commit(); flash("Payroll run created. Calculate it when attendance is ready.","success")
                return redirect(url_for("hr_payroll_run_view",run_id=run.id))
            return redirect(url_for("hr_payroll"))
        rows=cdb.query(HRPayrollRun).filter_by(company_id=company_id).order_by(HRPayrollRun.year.desc(),HRPayrollRun.month.desc()).all()
        return render_template("hr_payroll.html",active="hr_payroll",rows=rows,today=date.today())

    @app.route("/hr/payroll/<int:run_id>")
    @login_required
    @require_permission("hr_payroll", "view")
    def hr_payroll_run_view(run_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        run=_first_or_404(cdb.query(HRPayrollRun).filter_by(id=run_id,company_id=company_id))
        banks=cdb.query(BankAccount).filter_by(company_id=company_id,status="Active").order_by(BankAccount.bank_name).all()
        return render_template("hr_payroll_run.html",active="hr_payroll",run=run,banks=banks)

    @app.route("/hr/payroll/<int:run_id>/calculate", methods=["POST"])
    @login_required
    @require_permission("hr_payroll", "edit")
    def hr_payroll_calculate(run_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        run=_first_or_404(cdb.query(HRPayrollRun).filter_by(id=run_id,company_id=company_id))
        if run.status in ("Approved","Locked"):
            flash("Approved or locked payroll cannot be recalculated.","error")
            return redirect(url_for("hr_payroll_run_view",run_id=run.id))
        # Recalculation replaces only this draft/calculated run's snapshots.
        for entry in list(run.entries): cdb.delete(entry)
        cdb.flush()
        employees=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").order_by(HREmployee.full_name).all()
        skipped=[]
        for employee in employees:
            assignment=_salary_assignment_for(cdb,company_id,employee.id,run.year,run.month)
            if not assignment:
                skipped.append(employee.full_name); continue
            entry=_build_payroll_entry(cdb,company_id,run,employee,assignment)
            cdb.add(entry); cdb.flush()
            for stat_line in getattr(entry,"_pending_statutory_lines",[]):
                stat_line.payroll_entry_id=entry.id
                cdb.add(stat_line)
            for recovery in getattr(entry,"_pending_loan_recoveries",[]):
                recovery.payroll_entry_id=entry.id
                cdb.add(recovery)
            for claim in getattr(entry,"_pending_claims",[]):
                claim.payroll_entry_id=entry.id
        cdb.flush()
        _refresh_payroll_totals(run)
        run.status="Calculated"; run.calculated_at=datetime.utcnow()
        cdb.commit()
        if skipped:
            flash("Payroll calculated. Skipped employees without an effective salary assignment: "+", ".join(skipped[:8])+("…" if len(skipped)>8 else ""),"warning")
        else: flash("Payroll calculated successfully.","success")
        return redirect(url_for("hr_payroll_run_view",run_id=run.id))

    @app.route("/hr/payroll/<int:run_id>/approve", methods=["POST"])
    @login_required
    @require_permission("hr_payroll", "edit")
    def hr_payroll_approve(run_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        run=_first_or_404(cdb.query(HRPayrollRun).filter_by(id=run_id,company_id=company_id))
        if run.status!="Calculated":
            flash("Only a calculated payroll can be approved.","error")
        elif not run.entries:
            flash("Payroll has no employee entries to approve.","error")
        else:
            run.status="Approved"; run.approved_by=_actor(get_current_user()); run.approved_at=datetime.utcnow()
            for e in run.entries: e.status="Approved"
            cdb.commit(); flash("Payroll approved. It can now be locked.","success")
        return redirect(url_for("hr_payroll_run_view",run_id=run.id))

    @app.route("/hr/payroll/<int:run_id>/lock", methods=["POST"])
    @login_required
    @require_permission("hr_payroll", "edit")
    def hr_payroll_lock(run_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        run=_first_or_404(cdb.query(HRPayrollRun).filter_by(id=run_id,company_id=company_id))
        if run.status!="Approved":
            flash("Approve payroll before locking it.","error")
        else:
            # Finance accrual is posted before the lock is committed. If posting fails,
            # the transaction rolls back instead of leaving payroll locked without accounting.
            if post_auto_journal:
                _post_payroll_finance(cdb,company_id,run,post_auto_journal,ensure_chart_of_accounts)
                run.finance_posted_at=datetime.utcnow()
                run.finance_posted_by=_actor(get_current_user())
            run.status="Locked"; run.locked_at=datetime.utcnow()
            for e in run.entries:
                e.status="Locked"
                for rec in cdb.query(HRLoanRecovery).filter_by(company_id=company_id,payroll_entry_id=e.id,status="Pending").all():
                    rec.status="Applied"; rec.recovered_at=datetime.utcnow()
                    rec.loan.outstanding_amount=max(_money("0"),_money(rec.loan.outstanding_amount)-_money(rec.amount))
                    if rec.loan.outstanding_amount<=0: rec.loan.status="Closed"
                for claim in cdb.query(HRExpenseClaim).filter_by(company_id=company_id,payroll_entry_id=e.id,status="Approved").all():
                    claim.status="Paid"; claim.paid_at=datetime.utcnow()
            cdb.commit(); flash("Payroll locked. Loan recoveries and payroll reimbursements were applied.","success")
        return redirect(url_for("hr_payroll_run_view",run_id=run.id))

    @app.route("/hr/payroll/<int:run_id>/payslip/<int:entry_id>")
    @login_required
    @require_permission("hr_payroll", "view")
    def hr_payslip(run_id,entry_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        run=_first_or_404(cdb.query(HRPayrollRun).filter_by(id=run_id,company_id=company_id))
        entry=_first_or_404(cdb.query(HRPayrollEntry).filter_by(id=entry_id,payroll_run_id=run.id,company_id=company_id))
        company=get_company_by_id(company_id)
        statutory_lines=cdb.query(HRPayrollStatutoryLine).filter_by(company_id=company_id,payroll_entry_id=entry.id).order_by(HRPayrollStatutoryLine.rule_code).all()
        loan_recoveries=cdb.query(HRLoanRecovery).filter_by(company_id=company_id,payroll_entry_id=entry.id).all()
        reimbursement_claims=cdb.query(HRExpenseClaim).filter_by(company_id=company_id,payroll_entry_id=entry.id).all()
        return render_template("hr_payslip.html",active="hr_payroll",run=run,entry=entry,company=company,
            statutory_lines=statutory_lines,loan_recoveries=loan_recoveries,reimbursement_claims=reimbursement_claims)


    @app.route("/hr/statutory", methods=["GET","POST"])
    @login_required
    @require_permission("hr_statutory", "view")
    def hr_statutory():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        _seed_india_statutory_defaults(cdb,company_id)
        if request.method=="POST":
            code=(request.form.get("rule_code") or "").upper()
            rule=cdb.query(HRStatutoryRule).filter_by(company_id=company_id,rule_code=code,enabled=True).order_by(HRStatutoryRule.effective_from.desc()).first()
            if not rule:
                flash("Statutory rule not found.","error")
            else:
                import json
                cfg=json.loads(rule.settings_json or "{}")
                for key in list(cfg.keys()):
                    if key in request.form:
                        val=request.form.get(key)
                        try: cfg[key]=float(val)
                        except (ValueError,TypeError): cfg[key]=val
                rule.settings_json=json.dumps(cfg,sort_keys=True)
                cdb.commit(); flash(f"{code} configuration updated.","success")
            return redirect(url_for("hr_statutory"))
        rules=cdb.query(HRStatutoryRule).filter_by(company_id=company_id,enabled=True).order_by(HRStatutoryRule.rule_code,HRStatutoryRule.effective_from.desc()).all()
        return render_template("hr_statutory.html",active="hr_statutory",rules=rules,configs=[(r,_rule_cfg(r)) for r in rules])

    @app.route("/hr/statutory/employees", methods=["GET","POST"])
    @login_required
    @require_permission("hr_statutory", "view")
    def hr_employee_statutory():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employees=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").order_by(HREmployee.full_name).all()
        if request.method=="POST":
            employee_id=_int(request.form.get("employee_id"))
            employee=cdb.query(HREmployee).filter_by(id=employee_id,company_id=company_id).first()
            if not employee:
                flash("Employee not found.","error")
            else:
                row=cdb.query(HREmployeeStatutoryProfile).filter_by(company_id=company_id,employee_id=employee.id).first()
                if not row:
                    row=HREmployeeStatutoryProfile(company_id=company_id,employee_id=employee.id); cdb.add(row)
                row.pf_enabled=bool(request.form.get("pf_enabled"))
                row.pf_on_actual_basic=bool(request.form.get("pf_on_actual_basic"))
                row.esi_enabled=bool(request.form.get("esi_enabled"))
                row.pt_enabled=bool(request.form.get("pt_enabled"))
                row.tds_enabled=bool(request.form.get("tds_enabled"))
                row.tax_regime=request.form.get("tax_regime") or "New"
                row.annual_other_income=_money(request.form.get("annual_other_income"))
                row.annual_deductions=_money(request.form.get("annual_deductions"))
                row.tds_already_deducted=_money(request.form.get("tds_already_deducted"))
                manual=(request.form.get("manual_monthly_tds") or "").strip()
                row.manual_monthly_tds=_money(manual) if manual else None
                row.notes=(request.form.get("notes") or "").strip() or None
                cdb.commit(); flash("Employee statutory profile saved.","success")
            return redirect(url_for("hr_employee_statutory"))
        profiles={x.employee_id:x for x in cdb.query(HREmployeeStatutoryProfile).filter_by(company_id=company_id).all()}
        return render_template("hr_employee_statutory.html",active="hr_employee_statutory",employees=employees,profiles=profiles)


    @app.route("/hr/loans", methods=["GET","POST"])
    @login_required
    @require_permission("hr_loans", "view")
    def hr_loans():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employees=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").order_by(HREmployee.full_name).all()
        if request.method=="POST":
            employee_id=_int(request.form.get("employee_id")); employee=cdb.query(HREmployee).filter_by(id=employee_id,company_id=company_id).first()
            principal=_money(request.form.get("principal_amount")); installments=max(1,_int(request.form.get("total_installments"),1))
            installment=_money(request.form.get("installment_amount"))
            if installment<=0 and principal>0: installment=(principal/installments).quantize(_money("0.01"))
            if not employee or principal<=0:
                flash("Valid employee and loan amount are required.","error")
            else:
                number=_next_loan_number(cdb,company_id)
                loan=HREmployeeLoan(company_id=company_id,loan_number=number,employee_id=employee.id,
                    loan_type=request.form.get("loan_type") or "Loan",principal_amount=principal,
                    installment_amount=installment,total_installments=installments,
                    start_month=_int(request.form.get("start_month"),date.today().month),
                    start_year=_int(request.form.get("start_year"),date.today().year),
                    outstanding_amount=principal,status="Active",
                    purpose=(request.form.get("purpose") or "").strip() or None)
                cdb.add(loan); cdb.commit(); flash(f"{loan.loan_type} {number} created.","success")
            return redirect(url_for("hr_loans"))
        rows=cdb.query(HREmployeeLoan).filter_by(company_id=company_id).order_by(HREmployeeLoan.id.desc()).all()
        return render_template("hr_loans.html",active="hr_loans",rows=rows,employees=employees,today=date.today())

    @app.route("/hr/loans/<int:loan_id>/status", methods=["POST"])
    @login_required
    @require_permission("hr_loans", "edit")
    def hr_loan_status(loan_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        loan=_first_or_404(cdb.query(HREmployeeLoan).filter_by(id=loan_id,company_id=company_id))
        status=request.form.get("status")
        if status in ("Active","Hold","Closed"):
            loan.status=status; cdb.commit(); flash("Loan status updated.","success")
        return redirect(url_for("hr_loans"))

    @app.route("/hr/expense-claims", methods=["GET","POST"])
    @login_required
    @require_permission("hr_claims", "view")
    def hr_expense_claims():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employees=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").order_by(HREmployee.full_name).all()
        if request.method=="POST":
            employee_id=_int(request.form.get("employee_id")); employee=cdb.query(HREmployee).filter_by(id=employee_id,company_id=company_id).first()
            amount=_money(request.form.get("amount"))
            if not employee or amount<=0 or not (request.form.get("expense_type") or "").strip():
                flash("Employee, expense type and positive amount are required.","error")
            else:
                cdb.add(HRExpenseClaim(company_id=company_id,employee_id=employee.id,
                    claim_date=_as_date(request.form.get("claim_date")) or date.today(),
                    expense_type=(request.form.get("expense_type") or "").strip(),amount=amount,
                    merchant=(request.form.get("merchant") or "").strip() or None,
                    description=(request.form.get("description") or "").strip() or None,
                    receipt_reference=(request.form.get("receipt_reference") or "").strip() or None,
                    include_in_payroll=bool(request.form.get("include_in_payroll")),status="Pending"))
                cdb.commit(); flash("Expense claim submitted.","success")
            return redirect(url_for("hr_expense_claims"))
        status=(request.args.get("status") or "").strip()
        q=cdb.query(HRExpenseClaim).filter_by(company_id=company_id)
        if status: q=q.filter(HRExpenseClaim.status==status)
        rows=q.order_by(HRExpenseClaim.id.desc()).limit(300).all()
        return render_template("hr_expense_claims.html",active="hr_expense_claims",rows=rows,employees=employees)

    @app.route("/hr/expense-claims/<int:claim_id>/decision", methods=["POST"])
    @login_required
    @require_permission("hr_claims", "edit")
    def hr_expense_claim_decision(claim_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        row=_first_or_404(cdb.query(HRExpenseClaim).filter_by(id=claim_id,company_id=company_id))
        decision=request.form.get("decision")
        if row.status!="Pending" or decision not in ("Approved","Rejected"):
            flash("Only pending claims can be approved or rejected.","error")
        else:
            row.status=decision; row.approved_by=_actor(get_current_user()); row.approved_at=datetime.utcnow()
            row.approved_amount=min(row.amount,max(_money("0"),_money(request.form.get("approved_amount")))) if decision=="Approved" else _money("0")
            row.approval_notes=(request.form.get("approval_notes") or "").strip() or None
            cdb.commit(); flash(f"Expense claim {decision.lower()}.","success")
        return redirect(url_for("hr_expense_claims"))


    @app.route("/hr/payroll/<int:run_id>/pay", methods=["POST"])
    @login_required
    @require_permission("hr_payroll", "edit")
    def hr_payroll_pay(run_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        run=_first_or_404(cdb.query(HRPayrollRun).filter_by(id=run_id,company_id=company_id))
        bank_id=_int(request.form.get("bank_account_id"))
        bank=cdb.query(BankAccount).filter_by(id=bank_id,company_id=company_id,status="Active").first()
        if run.status!="Locked":
            flash("Payroll must be locked before salary payment.","error")
        elif run.payment_status=="Paid":
            flash("This payroll has already been paid.","error")
        elif not bank:
            flash("Select a valid active bank account.","error")
        elif not post_auto_journal:
            flash("Finance journal integration is unavailable.","error")
        else:
            amount=_money(run.total_net)
            if amount<=0:
                flash("Payroll net payable must be greater than zero.","error")
            else:
                if ensure_chart_of_accounts: ensure_chart_of_accounts(cdb,company_id)
                txn=BankTransaction(bank_account_id=bank.id,company_id=company_id,type="Payment",
                    date=date.today(),description=f"Salary payment {run.month:02d}/{run.year}",
                    amount=float(amount),reference=f"PAYROLL-{run.id}",transaction_mode="Bank",
                    notes=f"Payroll run #{run.id}",party_name="Employees",created_by=_actor(get_current_user()))
                cdb.add(txn); cdb.flush()
                post_auto_journal(cdb,company_id,date.today(),f"Salary payment {run.month:02d}/{run.year}",
                    "payroll_payment",run.id,f"PAYROLL-{run.id}",
                    [("2410",amount,0,"Salary payable settled"),
                     ("1200",0,amount,f"Salary payment from {bank.bank_name}")])
                bank.balance=float(bank.balance or 0)-float(amount)
                run.payment_status="Paid"; run.paid_at=datetime.utcnow(); run.paid_by=_actor(get_current_user())
                run.bank_transaction_id=txn.id
                cdb.commit(); flash("Salary payment posted to bank and Finance.","success")
        return redirect(url_for("hr_payroll_run_view",run_id=run.id))


    # =======================================================================
    # PHASE 9 — EMPLOYEE SELF-SERVICE / MANAGER SELF-SERVICE
    # =======================================================================

    def _self_employee(cdb, company_id):
        user=get_current_user() or {}
        email=(user.get("email") if isinstance(user,dict) else getattr(user,"email",None))
        if not email:
            return None
        return cdb.query(HREmployee).filter(
            HREmployee.company_id==company_id,
            func.lower(HREmployee.email)==email.strip().lower()
        ).first()

    def _require_self_employee(cdb, company_id):
        employee=_self_employee(cdb,company_id)
        if not employee:
            flash("Your login email is not linked to an HR employee profile. Ask HR to set the same email on your employee record.","error")
            abort(403)
        return employee

    def _is_direct_report(manager, employee):
        return bool(manager and employee and employee.manager_id==manager.id)

    @app.route("/hr/my")
    @login_required
    def hr_my_dashboard():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employee=_require_self_employee(cdb,company_id); today=date.today()
        month_start=date(today.year,today.month,1)
        attendance=cdb.query(HRAttendance).filter(
            HRAttendance.company_id==company_id,HRAttendance.employee_id==employee.id,
            HRAttendance.attendance_date>=month_start,HRAttendance.attendance_date<=today).all()
        pending_leave=cdb.query(HRLeaveRequest).filter_by(company_id=company_id,employee_id=employee.id,status="Pending").count()
        pending_claims=cdb.query(HRExpenseClaim).filter_by(company_id=company_id,employee_id=employee.id,status="Pending").count()
        last_pay=cdb.query(HRPayrollEntry).join(HRPayrollRun,HRPayrollEntry.payroll_run_id==HRPayrollRun.id).filter(
            HRPayrollEntry.company_id==company_id,HRPayrollEntry.employee_id==employee.id,
            HRPayrollRun.status=="Locked").order_by(HRPayrollRun.year.desc(),HRPayrollRun.month.desc()).first()
        direct_reports=cdb.query(HREmployee).filter_by(company_id=company_id,manager_id=employee.id,status="Active").count()
        return render_template("hr_my_dashboard.html",active="hr_my_dashboard",employee=employee,
            present=sum(1 for x in attendance if x.status in ("Present","Late")),
            late=sum(1 for x in attendance if (x.late_minutes or 0)>0),
            pending_leave=pending_leave,pending_claims=pending_claims,last_pay=last_pay,direct_reports=direct_reports)

    @app.route("/hr/my/attendance")
    @login_required
    def hr_my_attendance():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employee=_require_self_employee(cdb,company_id)
        year=request.args.get("year",type=int) or date.today().year
        month=request.args.get("month",type=int) or date.today().month
        import calendar
        start=date(year,month,1); end=date(year,month,calendar.monthrange(year,month)[1])
        rows=cdb.query(HRAttendance).filter(
            HRAttendance.company_id==company_id,HRAttendance.employee_id==employee.id,
            HRAttendance.attendance_date>=start,HRAttendance.attendance_date<=end
        ).order_by(HRAttendance.attendance_date.desc()).all()
        return render_template("hr_my_attendance.html",active="hr_my_attendance",employee=employee,rows=rows,year=year,month=month)

    @app.route("/hr/my/leaves", methods=["GET","POST"])
    @login_required
    def hr_my_leaves():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employee=_require_self_employee(cdb,company_id)
        types=cdb.query(HRLeaveType).filter_by(company_id=company_id,is_active=True).order_by(HRLeaveType.name).all()
        if request.method=="POST":
            lt=cdb.query(HRLeaveType).filter_by(id=_int(request.form.get("leave_type_id")),company_id=company_id,is_active=True).first()
            start=_as_date(request.form.get("start_date")); end=_as_date(request.form.get("end_date")); part=request.form.get("day_part") or "Full Day"
            if not lt or not start or not end or end<start:
                flash("Valid leave type and dates are required.","error")
            else:
                days=_leave_days(cdb,company_id,employee,start,end,part)
                _seed_leave_balances(cdb,company_id,[employee],[lt],start.year)
                bal=cdb.query(HRLeaveBalance).filter_by(company_id=company_id,employee_id=employee.id,leave_type_id=lt.id,year=start.year).first()
                if days<=0:
                    flash("Selected dates contain no chargeable leave days.","error")
                elif lt.is_paid and bal and bal.available<days:
                    flash(f"Insufficient {lt.name} balance.","error")
                else:
                    status="Pending" if lt.requires_approval else "Approved"
                    row=HRLeaveRequest(company_id=company_id,employee_id=employee.id,leave_type_id=lt.id,
                        start_date=start,end_date=end,days=days,day_part=part,
                        reason=(request.form.get("reason") or "").strip() or None,status=status)
                    cdb.add(row); cdb.flush()
                    if status=="Approved": _apply_leave_approval(cdb,company_id,row,get_current_user(),None)
                    cdb.commit(); flash("Leave request submitted.","success")
            return redirect(url_for("hr_my_leaves"))
        rows=cdb.query(HRLeaveRequest).filter_by(company_id=company_id,employee_id=employee.id).order_by(HRLeaveRequest.requested_at.desc()).all()
        balances=cdb.query(HRLeaveBalance).filter_by(company_id=company_id,employee_id=employee.id,year=date.today().year).all()
        return render_template("hr_my_leaves.html",active="hr_my_leaves",employee=employee,rows=rows,types=types,balances=balances)

    @app.route("/hr/my/payslips")
    @login_required
    def hr_my_payslips():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employee=_require_self_employee(cdb,company_id)
        rows=cdb.query(HRPayrollEntry).join(HRPayrollRun,HRPayrollEntry.payroll_run_id==HRPayrollRun.id).filter(
            HRPayrollEntry.company_id==company_id,HRPayrollEntry.employee_id==employee.id,
            HRPayrollRun.status=="Locked").order_by(HRPayrollRun.year.desc(),HRPayrollRun.month.desc()).all()
        return render_template("hr_my_payslips.html",active="hr_my_payslips",employee=employee,rows=rows)

    @app.route("/hr/my/payslips/<int:entry_id>")
    @login_required
    def hr_my_payslip(entry_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employee=_require_self_employee(cdb,company_id)
        entry=_first_or_404(cdb.query(HRPayrollEntry).filter_by(id=entry_id,company_id=company_id,employee_id=employee.id))
        run=_first_or_404(cdb.query(HRPayrollRun).filter_by(id=entry.payroll_run_id,company_id=company_id,status="Locked"))
        statutory_lines=cdb.query(HRPayrollStatutoryLine).filter_by(company_id=company_id,payroll_entry_id=entry.id).all()
        loan_recoveries=cdb.query(HRLoanRecovery).filter_by(company_id=company_id,payroll_entry_id=entry.id).all()
        reimbursement_claims=cdb.query(HRExpenseClaim).filter_by(company_id=company_id,payroll_entry_id=entry.id).all()
        return render_template("hr_payslip.html",active="hr_my_payslips",run=run,entry=entry,
            company=get_company_by_id(company_id),statutory_lines=statutory_lines,
            loan_recoveries=loan_recoveries,reimbursement_claims=reimbursement_claims)

    @app.route("/hr/my/claims", methods=["GET","POST"])
    @login_required
    def hr_my_claims():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employee=_require_self_employee(cdb,company_id)
        if request.method=="POST":
            amount=_money(request.form.get("amount")); kind=(request.form.get("expense_type") or "").strip()
            if amount<=0 or not kind:
                flash("Expense type and positive amount are required.","error")
            else:
                cdb.add(HRExpenseClaim(company_id=company_id,employee_id=employee.id,
                    claim_date=_as_date(request.form.get("claim_date")) or date.today(),expense_type=kind,amount=amount,
                    merchant=(request.form.get("merchant") or "").strip() or None,
                    description=(request.form.get("description") or "").strip() or None,
                    receipt_reference=(request.form.get("receipt_reference") or "").strip() or None,
                    include_in_payroll=True,status="Pending"))
                cdb.commit(); flash("Expense claim submitted.","success")
            return redirect(url_for("hr_my_claims"))
        rows=cdb.query(HRExpenseClaim).filter_by(company_id=company_id,employee_id=employee.id).order_by(HRExpenseClaim.id.desc()).all()
        return render_template("hr_my_claims.html",active="hr_my_claims",employee=employee,rows=rows)

    @app.route("/hr/my/loans")
    @login_required
    def hr_my_loans():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employee=_require_self_employee(cdb,company_id)
        rows=cdb.query(HREmployeeLoan).filter_by(company_id=company_id,employee_id=employee.id).order_by(HREmployeeLoan.id.desc()).all()
        return render_template("hr_my_loans.html",active="hr_my_loans",employee=employee,rows=rows)

    @app.route("/hr/my/profile", methods=["GET","POST"])
    @login_required
    def hr_my_profile():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        employee=_require_self_employee(cdb,company_id)
        if request.method=="POST":
            # Only non-sensitive contact fields are employee-editable.
            employee.phone=(request.form.get("phone") or "").strip() or None
            employee.alternate_phone=(request.form.get("alternate_phone") or "").strip() or None
            employee.address=(request.form.get("address") or "").strip() or None
            employee.city=(request.form.get("city") or "").strip() or None
            employee.state=(request.form.get("state") or "").strip() or None
            employee.pincode=(request.form.get("pincode") or "").strip() or None
            employee.emergency_contact_name=(request.form.get("emergency_contact_name") or "").strip() or None
            employee.emergency_contact_phone=(request.form.get("emergency_contact_phone") or "").strip() or None
            cdb.commit(); flash("Profile contact information updated.","success")
            return redirect(url_for("hr_my_profile"))
        return render_template("hr_my_profile.html",active="hr_my_profile",employee=employee)

    @app.route("/hr/manager")
    @login_required
    def hr_manager_dashboard():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        manager=_require_self_employee(cdb,company_id)
        team=cdb.query(HREmployee).filter_by(company_id=company_id,manager_id=manager.id,status="Active").order_by(HREmployee.full_name).all()
        ids=[e.id for e in team]
        leaves=cdb.query(HRLeaveRequest).filter(HRLeaveRequest.company_id==company_id,HRLeaveRequest.employee_id.in_(ids),HRLeaveRequest.status=="Pending").all() if ids else []
        claims=cdb.query(HRExpenseClaim).filter(HRExpenseClaim.company_id==company_id,HRExpenseClaim.employee_id.in_(ids),HRExpenseClaim.status=="Pending").all() if ids else []
        overtime=cdb.query(HROvertimeRequest).filter(HROvertimeRequest.company_id==company_id,HROvertimeRequest.employee_id.in_(ids),HROvertimeRequest.status=="Pending").all() if ids else []
        return render_template("hr_manager_dashboard.html",active="hr_manager_dashboard",manager=manager,team=team,leaves=leaves,claims=claims,overtime=overtime)

    @app.route("/hr/manager/leaves/<int:leave_id>/decision", methods=["POST"])
    @login_required
    def hr_manager_leave_decision(leave_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        manager=_require_self_employee(cdb,company_id)
        row=_first_or_404(cdb.query(HRLeaveRequest).filter_by(id=leave_id,company_id=company_id))
        if not _is_direct_report(manager,row.employee): abort(403)
        decision=request.form.get("decision")
        if row.status!="Pending" or decision not in ("Approved","Rejected"):
            flash("Only pending leave can be approved or rejected.","error")
        elif decision=="Approved":
            bal=cdb.query(HRLeaveBalance).filter_by(company_id=company_id,employee_id=row.employee_id,leave_type_id=row.leave_type_id,year=row.start_date.year).first()
            if row.leave_type.is_paid and bal and bal.available<row.days:
                flash("Insufficient leave balance.","error")
            else:
                _apply_leave_approval(cdb,company_id,row,get_current_user(),request.form.get("approval_notes")); cdb.commit()
                flash("Leave approved.","success")
        else:
            row.status="Rejected"; row.approved_by=_actor(get_current_user()); row.approved_at=datetime.utcnow()
            row.approval_notes=(request.form.get("approval_notes") or "").strip() or None
            cdb.commit(); flash("Leave rejected.","success")
        return redirect(url_for("hr_manager_dashboard"))

    @app.route("/hr/manager/claims/<int:claim_id>/decision", methods=["POST"])
    @login_required
    def hr_manager_claim_decision(claim_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        manager=_require_self_employee(cdb,company_id)
        row=_first_or_404(cdb.query(HRExpenseClaim).filter_by(id=claim_id,company_id=company_id))
        if not _is_direct_report(manager,row.employee): abort(403)
        decision=request.form.get("decision")
        if row.status=="Pending" and decision in ("Approved","Rejected"):
            row.status=decision; row.approved_by=_actor(get_current_user()); row.approved_at=datetime.utcnow()
            row.approved_amount=min(_money(row.amount),max(_money("0"),_money(request.form.get("approved_amount")))) if decision=="Approved" else _money("0")
            row.approval_notes=(request.form.get("approval_notes") or "").strip() or None
            cdb.commit(); flash(f"Claim {decision.lower()}.","success")
        else: flash("Only pending claims can be decided.","error")
        return redirect(url_for("hr_manager_dashboard"))

    @app.route("/hr/manager/overtime/<int:ot_id>/decision", methods=["POST"])
    @login_required
    def hr_manager_overtime_decision(ot_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        manager=_require_self_employee(cdb,company_id)
        row=_first_or_404(cdb.query(HROvertimeRequest).filter_by(id=ot_id,company_id=company_id))
        if not _is_direct_report(manager,row.employee): abort(403)
        decision=request.form.get("decision")
        if row.status=="Pending" and decision in ("Approved","Rejected"):
            row.status=decision; row.approved_by=_actor(get_current_user()); row.approved_at=datetime.utcnow()
            row.approved_minutes=min(row.requested_minutes,max(0,_int(request.form.get("approved_minutes"),row.requested_minutes))) if decision=="Approved" else 0
            cdb.commit(); flash(f"Overtime {decision.lower()}.","success")
        else: flash("Only pending overtime can be decided.","error")
        return redirect(url_for("hr_manager_dashboard"))


    # =======================================================================
    # PHASE 10 — RECRUITMENT, ONBOARDING, PERFORMANCE, ASSETS, MOVEMENTS, EXIT
    # =======================================================================

    @app.route("/hr/recruitment", methods=["GET","POST"])
    @login_required
    @require_permission("hr_recruitment","view")
    def hr_recruitment():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        if request.method=="POST":
            title=(request.form.get("title") or "").strip()
            if not title:
                flash("Job title is required.","error")
            else:
                code=(request.form.get("job_code") or "").strip() or f"JOB-{date.today().strftime('%y%m')}-{cdb.query(HRJobOpening).filter_by(company_id=company_id).count()+1:03d}"
                if cdb.query(HRJobOpening).filter_by(company_id=company_id,job_code=code).first():
                    flash("Job code already exists.","error")
                else:
                    cdb.add(HRJobOpening(company_id=company_id,job_code=code,title=title,
                        department_id=_int(request.form.get("department_id")) or None,
                        designation_id=_int(request.form.get("designation_id")) or None,
                        openings=max(1,_int(request.form.get("openings"),1)),
                        location=(request.form.get("location") or "").strip() or None,
                        employment_type=request.form.get("employment_type") or "Full Time",
                        description=(request.form.get("description") or "").strip() or None,
                        target_close_date=_as_date(request.form.get("target_close_date")),
                        created_by=_actor(get_current_user())))
                    cdb.commit(); flash("Job opening created.","success")
            return redirect(url_for("hr_recruitment"))
        jobs=cdb.query(HRJobOpening).filter_by(company_id=company_id).order_by(HRJobOpening.id.desc()).all()
        deps=cdb.query(HRDepartment).filter_by(company_id=company_id,is_active=True).order_by(HRDepartment.name).all()
        desigs=cdb.query(HRDesignation).filter_by(company_id=company_id,is_active=True).order_by(HRDesignation.name).all()
        return render_template("hr_recruitment.html",active="hr_recruitment",jobs=jobs,departments=deps,designations=desigs)

    @app.route("/hr/recruitment/<int:job_id>", methods=["GET","POST"])
    @login_required
    @require_permission("hr_recruitment","view")
    def hr_recruitment_job(job_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        job=_first_or_404(cdb.query(HRJobOpening).filter_by(id=job_id,company_id=company_id))
        if request.method=="POST":
            name=(request.form.get("full_name") or "").strip()
            if not name: flash("Candidate name is required.","error")
            else:
                cdb.add(HRCandidate(company_id=company_id,job_id=job.id,full_name=name,
                    email=(request.form.get("email") or "").strip() or None,phone=(request.form.get("phone") or "").strip() or None,
                    source=(request.form.get("source") or "").strip() or None,experience_years=_float(request.form.get("experience_years"),0),
                    current_company=(request.form.get("current_company") or "").strip() or None,
                    current_ctc=_money(request.form.get("current_ctc")),expected_ctc=_money(request.form.get("expected_ctc")),
                    notice_period_days=_int(request.form.get("notice_period_days"),0),notes=(request.form.get("notes") or "").strip() or None))
                cdb.commit(); flash("Candidate added.","success")
            return redirect(url_for("hr_recruitment_job",job_id=job.id))
        return render_template("hr_recruitment_job.html",active="hr_recruitment",job=job)

    @app.route("/hr/candidates/<int:candidate_id>/stage", methods=["POST"])
    @login_required
    @require_permission("hr_recruitment","edit")
    def hr_candidate_stage(candidate_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        row=_first_or_404(cdb.query(HRCandidate).filter_by(id=candidate_id,company_id=company_id))
        allowed={"Applied","Screening","Interview","Offered","Hired","Rejected","Withdrawn"}
        stage=request.form.get("stage")
        if stage in allowed:
            row.stage=stage
            if request.form.get("rating"): row.rating=max(1,min(5,_int(request.form.get("rating"),1)))
            cdb.commit(); flash("Candidate stage updated.","success")
        return redirect(url_for("hr_recruitment_job",job_id=row.job_id))

    @app.route("/hr/candidates/<int:candidate_id>/hire", methods=["POST"])
    @login_required
    @require_permission("hr_employees","create")
    def hr_candidate_hire(candidate_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        cand=_first_or_404(cdb.query(HRCandidate).filter_by(id=candidate_id,company_id=company_id))
        if cand.converted_employee_id:
            flash("Candidate is already linked to an employee.","error")
        else:
            code=(request.form.get("employee_code") or "").strip()
            if not code or cdb.query(HREmployee).filter_by(company_id=company_id,employee_code=code).first():
                flash("A unique employee code is required.","error")
            else:
                e=HREmployee(company_id=company_id,employee_code=code,full_name=cand.full_name,email=cand.email,phone=cand.phone,
                    department_id=cand.job.department_id,designation_id=cand.job.designation_id,
                    joining_date=_as_date(request.form.get("joining_date")) or date.today(),status="Active")
                cdb.add(e); cdb.flush(); cand.converted_employee_id=e.id; cand.stage="Hired"
                defaults=[("Identity & employee documents","Documents"),("Bank & payroll details","Payroll"),
                          ("Policy orientation","Orientation"),("System/email access","IT"),("Assign reporting manager","HR")]
                for task,cat in defaults: cdb.add(HROnboardingTask(company_id=company_id,employee_id=e.id,task_name=task,category=cat,status="Pending"))
                cdb.commit(); flash("Candidate hired and onboarding checklist created.","success")
                return redirect(url_for("hr_onboarding"))
        return redirect(url_for("hr_recruitment_job",job_id=cand.job_id))

    @app.route("/hr/onboarding", methods=["GET","POST"])
    @login_required
    @require_permission("hr_onboarding","view")
    def hr_onboarding():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        if request.method=="POST":
            emp=cdb.query(HREmployee).filter_by(id=_int(request.form.get("employee_id")),company_id=company_id).first()
            name=(request.form.get("task_name") or "").strip()
            if emp and name:
                cdb.add(HROnboardingTask(company_id=company_id,employee_id=emp.id,task_name=name,
                    category=(request.form.get("category") or "").strip() or None,due_date=_as_date(request.form.get("due_date")),
                    owner=(request.form.get("owner") or "").strip() or None,notes=(request.form.get("notes") or "").strip() or None))
                cdb.commit(); flash("Onboarding task added.","success")
            return redirect(url_for("hr_onboarding"))
        rows=cdb.query(HROnboardingTask).filter_by(company_id=company_id).order_by(HROnboardingTask.status,HROnboardingTask.due_date).all()
        emps=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").order_by(HREmployee.full_name).all()
        return render_template("hr_onboarding.html",active="hr_onboarding",rows=rows,employees=emps)

    @app.route("/hr/onboarding/<int:task_id>/toggle", methods=["POST"])
    @login_required
    @require_permission("hr_onboarding","edit")
    def hr_onboarding_toggle(task_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        row=_first_or_404(cdb.query(HROnboardingTask).filter_by(id=task_id,company_id=company_id))
        row.status="Completed" if row.status!="Completed" else "Pending"; row.completed_at=datetime.utcnow() if row.status=="Completed" else None
        cdb.commit(); return redirect(url_for("hr_onboarding"))

    @app.route("/hr/performance", methods=["GET","POST"])
    @login_required
    @require_permission("hr_performance","view")
    def hr_performance():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        emps=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").order_by(HREmployee.full_name).all()
        if request.method=="POST":
            emp=cdb.query(HREmployee).filter_by(id=_int(request.form.get("employee_id")),company_id=company_id).first()
            reviewer=cdb.query(HREmployee).filter_by(id=_int(request.form.get("reviewer_employee_id")),company_id=company_id).first() if request.form.get("reviewer_employee_id") else None
            period=(request.form.get("review_period") or "").strip()
            if not emp or not period: flash("Employee and review period are required.","error")
            else:
                cdb.add(HRPerformanceReview(company_id=company_id,employee_id=emp.id,reviewer_employee_id=reviewer.id if reviewer else None,
                    review_period=period,review_date=_as_date(request.form.get("review_date")) or date.today(),
                    goals=(request.form.get("goals") or "").strip() or None,achievements=(request.form.get("achievements") or "").strip() or None,
                    strengths=(request.form.get("strengths") or "").strip() or None,improvement_areas=(request.form.get("improvement_areas") or "").strip() or None,
                    rating=max(0,min(5,_float(request.form.get("rating"),0))),outcome=(request.form.get("outcome") or "").strip() or None,
                    status=request.form.get("status") or "Draft"))
                cdb.commit(); flash("Performance review saved.","success")
            return redirect(url_for("hr_performance"))
        rows=cdb.query(HRPerformanceReview).filter_by(company_id=company_id).order_by(HRPerformanceReview.review_date.desc()).all()
        return render_template("hr_performance.html",active="hr_performance",rows=rows,employees=emps)

    @app.route("/hr/assets", methods=["GET","POST"])
    @login_required
    @require_permission("hr_assets","view")
    def hr_assets():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        emps=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").order_by(HREmployee.full_name).all()
        if request.method=="POST":
            code=(request.form.get("asset_code") or "").strip(); kind=(request.form.get("asset_type") or "").strip()
            if not code or not kind or cdb.query(HREmployeeAsset).filter_by(company_id=company_id,asset_code=code).first():
                flash("Unique asset code and asset type are required.","error")
            else:
                emp=cdb.query(HREmployee).filter_by(id=_int(request.form.get("employee_id")),company_id=company_id).first() if request.form.get("employee_id") else None
                cdb.add(HREmployeeAsset(company_id=company_id,asset_code=code,asset_type=kind,
                    description=(request.form.get("description") or "").strip() or None,serial_number=(request.form.get("serial_number") or "").strip() or None,
                    employee_id=emp.id if emp else None,issued_on=_as_date(request.form.get("issued_on")) if emp else None,
                    condition_issued=(request.form.get("condition_issued") or "").strip() or None,status="Issued" if emp else "Available",
                    notes=(request.form.get("notes") or "").strip() or None))
                cdb.commit(); flash("Employee asset saved.","success")
            return redirect(url_for("hr_assets"))
        rows=cdb.query(HREmployeeAsset).filter_by(company_id=company_id).order_by(HREmployeeAsset.id.desc()).all()
        return render_template("hr_assets.html",active="hr_assets",rows=rows,employees=emps)

    @app.route("/hr/assets/<int:asset_id>/return", methods=["POST"])
    @login_required
    @require_permission("hr_assets","edit")
    def hr_asset_return(asset_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        row=_first_or_404(cdb.query(HREmployeeAsset).filter_by(id=asset_id,company_id=company_id))
        row.returned_on=date.today(); row.condition_returned=(request.form.get("condition_returned") or "").strip() or None
        row.employee_id=None; row.status="Available"; cdb.commit(); flash("Asset returned.","success")
        return redirect(url_for("hr_assets"))

    @app.route("/hr/movements", methods=["GET","POST"])
    @login_required
    @require_permission("hr_movements","view")
    def hr_movements():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        emps=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").order_by(HREmployee.full_name).all()
        deps=cdb.query(HRDepartment).filter_by(company_id=company_id,is_active=True).order_by(HRDepartment.name).all()
        desigs=cdb.query(HRDesignation).filter_by(company_id=company_id,is_active=True).order_by(HRDesignation.name).all()
        if request.method=="POST":
            emp=cdb.query(HREmployee).filter_by(id=_int(request.form.get("employee_id")),company_id=company_id).first()
            if not emp: flash("Employee is required.","error")
            else:
                new_dep=_int(request.form.get("department_id")) or None; new_des=_int(request.form.get("designation_id")) or None; new_mgr=_int(request.form.get("manager_id")) or None
                # Validate all target IDs are in this tenant before applying them.
                if new_dep and not cdb.query(HRDepartment).filter_by(id=new_dep,company_id=company_id).first(): abort(400)
                if new_des and not cdb.query(HRDesignation).filter_by(id=new_des,company_id=company_id).first(): abort(400)
                if new_mgr and not cdb.query(HREmployee).filter_by(id=new_mgr,company_id=company_id,status="Active").first(): abort(400)
                cdb.add(HREmployeeMovement(company_id=company_id,employee_id=emp.id,movement_type=request.form.get("movement_type") or "Transfer",
                    effective_date=_as_date(request.form.get("effective_date")) or date.today(),old_department_id=emp.department_id,new_department_id=new_dep,
                    old_designation_id=emp.designation_id,new_designation_id=new_des,old_manager_id=emp.manager_id,new_manager_id=new_mgr,
                    reason=(request.form.get("reason") or "").strip() or None,approved_by=_actor(get_current_user())))
                emp.department_id=new_dep; emp.designation_id=new_des; emp.manager_id=new_mgr
                cdb.commit(); flash("Employee movement recorded and profile updated.","success")
            return redirect(url_for("hr_movements"))
        rows=cdb.query(HREmployeeMovement).filter_by(company_id=company_id).order_by(HREmployeeMovement.effective_date.desc()).all()
        return render_template("hr_movements.html",active="hr_movements",rows=rows,employees=emps,departments=deps,designations=desigs)

    @app.route("/hr/exits", methods=["GET","POST"])
    @login_required
    @require_permission("hr_exits","view")
    def hr_exits():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        emps=cdb.query(HREmployee).filter_by(company_id=company_id,status="Active").order_by(HREmployee.full_name).all()
        if request.method=="POST":
            emp=cdb.query(HREmployee).filter_by(id=_int(request.form.get("employee_id")),company_id=company_id).first()
            last=_as_date(request.form.get("last_working_date"))
            if not emp or not last: flash("Employee and last working date are required.","error")
            elif cdb.query(HRExitCase).filter_by(company_id=company_id,employee_id=emp.id,status="Open").first(): flash("An open exit case already exists.","error")
            else:
                cdb.add(HRExitCase(company_id=company_id,employee_id=emp.id,exit_type=request.form.get("exit_type") or "Resignation",
                    resignation_date=_as_date(request.form.get("resignation_date")),last_working_date=last,
                    reason=(request.form.get("reason") or "").strip() or None,notice_days=_int(request.form.get("notice_days"),0),
                    final_settlement_amount=_money(request.form.get("final_settlement_amount")),notes=(request.form.get("notes") or "").strip() or None))
                cdb.commit(); flash("Exit case opened.","success")
            return redirect(url_for("hr_exits"))
        rows=cdb.query(HRExitCase).filter_by(company_id=company_id).order_by(HRExitCase.id.desc()).all()
        return render_template("hr_exits.html",active="hr_exits",rows=rows,employees=emps)

    @app.route("/hr/exits/<int:exit_id>/close", methods=["POST"])
    @login_required
    @require_permission("hr_exits","edit")
    def hr_exit_close(exit_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        row=_first_or_404(cdb.query(HRExitCase).filter_by(id=exit_id,company_id=company_id))
        if row.status!="Open": flash("Exit case is already closed.","error")
        elif any(x!="Cleared" for x in (row.handover_status,row.asset_clearance_status,row.finance_clearance_status)):
            flash("Handover, asset and finance clearances must all be cleared before exit closure.","error")
        else:
            row.status="Closed"; row.settlement_status=request.form.get("settlement_status") or row.settlement_status
            row.closed_at=datetime.utcnow(); row.employee.status="Inactive"; cdb.commit(); flash("Exit completed and employee marked inactive.","success")
        return redirect(url_for("hr_exits"))

    @app.route("/hr/exits/<int:exit_id>/clearance", methods=["POST"])
    @login_required
    @require_permission("hr_exits","edit")
    def hr_exit_clearance(exit_id):
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        row=_first_or_404(cdb.query(HRExitCase).filter_by(id=exit_id,company_id=company_id))
        for field in ("handover_status","asset_clearance_status","finance_clearance_status"):
            value=request.form.get(field)
            if value in ("Pending","Cleared","Blocked"): setattr(row,field,value)
        cdb.commit(); flash("Exit clearance updated.","success")
        return redirect(url_for("hr_exits"))


    # =======================================================================
    # PHASE 11 — HR REPORTS + HR/PAYROLL BI INTELLIGENCE
    # =======================================================================

    def _hr_report_period():
        today=date.today()
        start=_as_date(request.args.get("start")) or date(today.year,1,1)
        end=_as_date(request.args.get("end")) or today
        if end < start:
            start,end=end,start
        return start,end

    @app.route("/hr/reports")
    @login_required
    @require_permission("hr","view")
    def hr_reports():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        start,end=_hr_report_period()
        employees=cdb.query(HREmployee).filter_by(company_id=company_id).all()
        active=[e for e in employees if e.status=="Active"]
        joined=[e for e in employees if e.joining_date and start<=e.joining_date<=end]
        exits=cdb.query(HRExitCase).filter(HRExitCase.company_id==company_id,
            HRExitCase.last_working_date>=start,HRExitCase.last_working_date<=end).all()
        attendance=cdb.query(HRAttendance).filter(HRAttendance.company_id==company_id,
            HRAttendance.attendance_date>=start,HRAttendance.attendance_date<=end).all()
        leave=cdb.query(HRLeaveRequest).filter(HRLeaveRequest.company_id==company_id,
            HRLeaveRequest.start_date<=end,HRLeaveRequest.end_date>=start).all()
        departments=cdb.query(HRDepartment).filter_by(company_id=company_id).order_by(HRDepartment.name).all()
        dep_counts={d.id:sum(1 for e in active if e.department_id==d.id) for d in departments}
        present=sum(1 for a in attendance if a.status in ("Present","Late","Half Day"))
        absent=sum(1 for a in attendance if a.status=="Absent")
        late=sum(1 for a in attendance if (a.late_minutes or 0)>0)
        overtime=sum((a.overtime_minutes or 0) for a in attendance)
        approved_leave=sum(float(x.days or 0) for x in leave if x.status=="Approved")
        return render_template("hr_reports.html",active="hr_reports",start=start,end=end,
            total=len(employees),active_count=len(active),joined_count=len(joined),exit_count=len(exits),
            departments=departments,dep_counts=dep_counts,present=present,absent=absent,late=late,
            overtime=overtime,approved_leave=approved_leave,employees=employees,exits=exits)

    @app.route("/hr/reports/attendance")
    @login_required
    @require_permission("hr_attendance","view")
    def hr_attendance_report():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        start,end=_hr_report_period()
        rows=cdb.query(HRAttendance).filter(HRAttendance.company_id==company_id,
            HRAttendance.attendance_date>=start,HRAttendance.attendance_date<=end).order_by(
            HRAttendance.attendance_date.desc()).all()
        by_employee={}
        for r in rows:
            d=by_employee.setdefault(r.employee_id,{"employee":r.employee,"present":0,"absent":0,"late":0,"work":0,"ot":0})
            if r.status in ("Present","Late","Half Day"): d["present"]+=1
            if r.status=="Absent": d["absent"]+=1
            if (r.late_minutes or 0)>0: d["late"]+=1
            d["work"]+=r.work_minutes or 0; d["ot"]+=r.overtime_minutes or 0
        return render_template("hr_attendance_report.html",active="hr_reports",start=start,end=end,rows=list(by_employee.values()))

    @app.route("/hr/reports/leave")
    @login_required
    @require_permission("hr_leave","view")
    def hr_leave_report():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        start,end=_hr_report_period()
        rows=cdb.query(HRLeaveRequest).filter(HRLeaveRequest.company_id==company_id,
            HRLeaveRequest.start_date<=end,HRLeaveRequest.end_date>=start).order_by(HRLeaveRequest.start_date.desc()).all()
        return render_template("hr_leave_report.html",active="hr_reports",start=start,end=end,rows=rows)

    @app.route("/hr/reports/payroll")
    @login_required
    @require_permission("hr_payroll","view")
    def hr_payroll_report():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        year=request.args.get("year",type=int) or date.today().year
        runs=cdb.query(HRPayrollRun).filter_by(company_id=company_id,year=year).order_by(HRPayrollRun.month).all()
        gross=sum(float(r.total_gross or 0) for r in runs)
        deductions=sum(float(r.total_deductions or 0) for r in runs)
        net=sum(float(r.total_net or 0) for r in runs)
        return render_template("hr_payroll_report.html",active="hr_reports",year=year,runs=runs,
            total_gross=gross,total_deductions=deductions,total_net=net)

    @app.route("/hr/reports/salary-register")
    @login_required
    @require_permission("hr_payroll","view")
    def hr_salary_register():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        year=request.args.get("year",type=int) or date.today().year
        month=request.args.get("month",type=int) or date.today().month
        run=cdb.query(HRPayrollRun).filter_by(company_id=company_id,year=year,month=month).first()
        entries=cdb.query(HRPayrollEntry).filter_by(company_id=company_id,payroll_run_id=run.id).order_by(HRPayrollEntry.employee_id).all() if run else []
        return render_template("hr_salary_register.html",active="hr_reports",year=year,month=month,run=run,entries=entries)

    @app.route("/hr/reports/statutory")
    @login_required
    @require_permission("hr_statutory","view")
    def hr_statutory_report():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        year=request.args.get("year",type=int) or date.today().year
        month=request.args.get("month",type=int) or date.today().month
        run=cdb.query(HRPayrollRun).filter_by(company_id=company_id,year=year,month=month).first()
        lines=cdb.query(HRPayrollStatutoryLine).filter_by(company_id=company_id,payroll_run_id=run.id).all() if run else []
        totals={}
        for x in lines:
            d=totals.setdefault(x.code,{"name":x.name,"employee":0.0,"employer":0.0})
            d["employee"]+=float(x.employee_amount or 0); d["employer"]+=float(x.employer_amount or 0)
        return render_template("hr_statutory_report.html",active="hr_reports",year=year,month=month,run=run,totals=totals)

    @app.route("/hr/bi")
    @login_required
    @require_permission("hr","view")
    def hr_bi_intelligence():
        cdb=get_cdb(); company_id=get_current_company(); ensure_tables(cdb)
        today=date.today(); year=today.year
        employees=cdb.query(HREmployee).filter_by(company_id=company_id).all()
        active=[e for e in employees if e.status=="Active"]
        departments=cdb.query(HRDepartment).filter_by(company_id=company_id).all()
        dep_labels=[]; dep_values=[]
        for d in departments:
            dep_labels.append(d.name); dep_values.append(sum(1 for e in active if e.department_id==d.id))
        dep_labels.append("Unassigned"); dep_values.append(sum(1 for e in active if not e.department_id))
        monthly_join=[0]*12; monthly_exit=[0]*12
        for e in employees:
            if e.joining_date and e.joining_date.year==year: monthly_join[e.joining_date.month-1]+=1
        exits=cdb.query(HRExitCase).filter(HRExitCase.company_id==company_id,
            HRExitCase.last_working_date>=date(year,1,1),HRExitCase.last_working_date<=date(year,12,31)).all()
        for x in exits: monthly_exit[x.last_working_date.month-1]+=1
        payroll_runs=cdb.query(HRPayrollRun).filter_by(company_id=company_id,year=year).all()
        payroll=[0.0]*12
        for r in payroll_runs: payroll[r.month-1]=float(r.total_net or 0)
        attendance=cdb.query(HRAttendance).filter(HRAttendance.company_id==company_id,
            HRAttendance.attendance_date>=date(year,1,1),HRAttendance.attendance_date<=today).all()
        attendance_present=sum(1 for x in attendance if x.status in ("Present","Late","Half Day"))
        attendance_absent=sum(1 for x in attendance if x.status=="Absent")
        pending_leave=cdb.query(HRLeaveRequest).filter_by(company_id=company_id,status="Pending").count()
        pending_claims=cdb.query(HRExpenseClaim).filter_by(company_id=company_id,status="Pending").count()
        open_jobs=cdb.query(HRJobOpening).filter_by(company_id=company_id,status="Open").count()
        candidates=cdb.query(HRCandidate).filter_by(company_id=company_id).count()
        reviews=cdb.query(HRPerformanceReview).filter_by(company_id=company_id,status="Final").all()
        avg_rating=(sum(float(x.rating or 0) for x in reviews)/len(reviews)) if reviews else 0
        assets_issued=cdb.query(HREmployeeAsset).filter_by(company_id=company_id,status="Issued").count()
        return render_template("hr_bi_intelligence.html",active="hr_bi",year=year,
            total=len(employees),active_count=len(active),open_jobs=open_jobs,candidates=candidates,
            pending_leave=pending_leave,pending_claims=pending_claims,avg_rating=avg_rating,
            assets_issued=assets_issued,attendance_present=attendance_present,attendance_absent=attendance_absent,
            dep_labels=dep_labels,dep_values=dep_values,monthly_join=monthly_join,monthly_exit=monthly_exit,payroll=payroll)


def _as_date(value):
    if not value: return None
    try: return date.fromisoformat(value)
    except (ValueError,TypeError): return None

def _as_int(value):
    try: return int(value) if value else None
    except (ValueError,TypeError): return None

def _apply_employee_form(e, form):
    e.email=(form.get("email") or "").strip() or None
    e.phone=(form.get("phone") or "").strip() or None
    e.alternate_phone=(form.get("alternate_phone") or "").strip() or None
    e.date_of_birth=_as_date(form.get("date_of_birth"))
    e.gender=(form.get("gender") or "").strip() or None
    e.address=(form.get("address") or "").strip() or None
    e.city=(form.get("city") or "").strip() or None
    e.state=(form.get("state") or "").strip() or None
    e.country=(form.get("country") or "India").strip() or "India"
    e.pincode=(form.get("pincode") or "").strip() or None
    e.emergency_contact_name=(form.get("emergency_contact_name") or "").strip() or None
    e.emergency_contact_phone=(form.get("emergency_contact_phone") or "").strip() or None
    e.department_id=_as_int(form.get("department_id"))
    e.designation_id=_as_int(form.get("designation_id"))
    e.manager_id=_as_int(form.get("manager_id"))
    e.branch=(form.get("branch") or "").strip() or None
    e.joining_date=_as_date(form.get("joining_date")) or date.today()
    e.employment_type=(form.get("employment_type") or "Full Time").strip()
    e.status=(form.get("status") or "Active").strip()
    e.pan_number=(form.get("pan_number") or "").strip() or None
    e.aadhaar_number=(form.get("aadhaar_number") or "").strip() or None
    e.bank_name=(form.get("bank_name") or "").strip() or None
    e.bank_account_number=(form.get("bank_account_number") or "").strip() or None
    e.bank_ifsc=(form.get("bank_ifsc") or "").strip() or None
    e.uan_number=(form.get("uan_number") or "").strip() or None
    e.esi_number=(form.get("esi_number") or "").strip() or None
    e.notes=(form.get("notes") or "").strip() or None


def _int(value, default=0):
    try: return int(value)
    except (ValueError, TypeError): return default

def _float(value, default=0):
    try: return float(value)
    except (ValueError, TypeError): return default

def _combine(day, hhmm):
    if not hhmm: return None
    try:
        h,m=[int(x) for x in hhmm.split(":")[:2]]
        return datetime.combine(day, datetime.min.time()).replace(hour=h,minute=m)
    except (ValueError,TypeError): return None

def _weekly_offs(shift):
    return {x.strip() for x in (shift.weekly_off_days or "").split(",") if x.strip()}

def _shift_for(cdb, company_id, employee_id, day):
    return (cdb.query(HRShift).join(HRShiftAssignment, HRShiftAssignment.shift_id==HRShift.id)
        .filter(HRShiftAssignment.company_id==company_id,HRShiftAssignment.employee_id==employee_id,
                HRShiftAssignment.effective_from<=day,
                (HRShiftAssignment.effective_to==None) | (HRShiftAssignment.effective_to>=day),
                HRShift.is_active==True)
        .order_by(HRShiftAssignment.effective_from.desc(),HRShiftAssignment.id.desc()).first())

def _holiday_for(cdb, company_id, employee, day):
    rows=cdb.query(HRHoliday).filter_by(company_id=company_id,holiday_date=day).all()
    for h in rows:
        if not h.branch or h.branch == employee.branch:
            return h
    return None

def _calculate_attendance(att, shift, holiday=None):
    att.work_minutes=att.late_minutes=att.early_exit_minutes=att.overtime_minutes=0
    if holiday:
        att.status="Holiday"
        if att.check_in: att.status="Present"
        return
    if shift and att.attendance_date.strftime("%A") in _weekly_offs(shift):
        att.status="Weekly Off"
        if att.check_in: att.status="Present"
        return
    if not att.check_in:
        att.status="Absent"; return
    if not att.check_out:
        att.status="Present"; return
    gross=max(0,int((att.check_out-att.check_in).total_seconds()//60))
    break_minutes=shift.break_minutes if shift else 0
    att.work_minutes=max(0,gross-break_minutes)
    if shift:
        start=_combine(att.attendance_date,shift.start_time)
        end=_combine(att.attendance_date,shift.end_time)
        if end and start and end <= start: end += timedelta(days=1)
        grace=shift.grace_minutes or 0
        att.late_minutes=max(0,int((att.check_in-(start+timedelta(minutes=grace))).total_seconds()//60)) if start else 0
        att.early_exit_minutes=max(0,int((end-att.check_out).total_seconds()//60)) if end else 0
        threshold=int((shift.full_day_hours or 8)*60)+(shift.overtime_after_minutes or 0)
        att.overtime_minutes=max(0,att.work_minutes-threshold)
        if att.work_minutes < int((shift.half_day_hours or 4)*60):
            att.status="Absent"
        elif att.work_minutes < int((shift.full_day_hours or 8)*60):
            att.status="Half Day"
        elif att.late_minutes > 0:
            att.status="Late"
        else:
            att.status="Present"
    else:
        att.status="Present"


def _actor(user):
    user=user or {}
    return user.get("email") or user.get("full_name") or user.get("user_id") or "system"

def _seed_leave_balances(cdb,company_id,employees,types,year):
    changed=False
    for e in employees:
        for lt in types:
            if not cdb.query(HRLeaveBalance).filter_by(company_id=company_id,employee_id=e.id,leave_type_id=lt.id,year=year).first():
                opening=0
                if lt.carry_forward:
                    prev=cdb.query(HRLeaveBalance).filter_by(company_id=company_id,employee_id=e.id,leave_type_id=lt.id,year=year-1).first()
                    if prev:
                        opening=min(max(0,prev.available),lt.max_carry_forward or max(0,prev.available))
                cdb.add(HRLeaveBalance(company_id=company_id,employee_id=e.id,leave_type_id=lt.id,year=year,
                    opening_balance=opening,entitled=lt.annual_entitlement or 0))
                changed=True
    if changed: cdb.commit()

def _leave_days(cdb,company_id,employee,start,end,day_part="Full Day"):
    # Charge working days only: assigned weekly offs and applicable holidays are excluded.
    if start==end and day_part in ("First Half","Second Half"):
        shift=_shift_for(cdb,company_id,employee.id,start)
        if (shift and start.strftime("%A") in _weekly_offs(shift)) or _holiday_for(cdb,company_id,employee,start):
            return 0
        return .5
    days=0; cursor=start
    while cursor<=end:
        shift=_shift_for(cdb,company_id,employee.id,cursor)
        weekly=bool(shift and cursor.strftime("%A") in _weekly_offs(shift))
        if not weekly and not _holiday_for(cdb,company_id,employee,cursor): days+=1
        cursor+=timedelta(days=1)
    return float(days)

def _apply_leave_approval(cdb,company_id,req,user,notes):
    if req.status=="Approved" and req.approved_at:
        return
    req.status="Approved"; req.approved_by=_actor(user); req.approved_at=datetime.utcnow()
    req.approval_notes=(notes or "").strip() or None
    bal=cdb.query(HRLeaveBalance).filter_by(company_id=company_id,employee_id=req.employee_id,
        leave_type_id=req.leave_type_id,year=req.start_date.year).first()
    if bal: bal.used=(bal.used or 0)+req.days
    cursor=req.start_date
    while cursor<=req.end_date:
        shift=_shift_for(cdb,company_id,req.employee_id,cursor)
        employee=req.employee
        if not (shift and cursor.strftime("%A") in _weekly_offs(shift)) and not _holiday_for(cdb,company_id,employee,cursor):
            att=cdb.query(HRAttendance).filter_by(company_id=company_id,employee_id=req.employee_id,attendance_date=cursor).first()
            if not att:
                att=HRAttendance(company_id=company_id,employee_id=req.employee_id,attendance_date=cursor,
                    shift_id=shift.id if shift else None,source="Leave")
                cdb.add(att)
            if not att.check_in:
                att.status="Paid Leave" if req.leave_type.is_paid else "Unpaid Leave"
                att.notes=f"{req.leave_type.name}: {req.reason or ''}".strip()
        cursor+=timedelta(days=1)


def _money(value):
    from decimal import Decimal, InvalidOperation
    try: return Decimal(str(value or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation,ValueError,TypeError): return Decimal("0.00")

def _salary_preview(assignment):
    from decimal import Decimal
    basic=Decimal(str(assignment.basic_monthly or 0))
    earnings=Decimal("0"); deductions=Decimal("0"); lines=[]
    for line in assignment.structure.lines:
        if line.calculation_type=="Percent of Basic":
            amount=(basic*Decimal(str(line.value or 0))/Decimal("100")).quantize(Decimal("0.01"))
        else:
            amount=Decimal(str(line.value or 0)).quantize(Decimal("0.01"))
        # Basic can be represented as a zero-value Basic component and derives from assignment.
        if (line.component.code or "").upper()=="BASIC":
            amount=basic
        if line.component.component_type=="Deduction": deductions+=amount
        else: earnings+=amount
        lines.append((line.component,amount))
    return {"basic":basic,"earnings":earnings,"deductions":deductions,
            "net":earnings-deductions,"lines":lines}


def _salary_assignment_for(cdb,company_id,employee_id,year,month):
    import calendar
    period_end=date(year,month,calendar.monthrange(year,month)[1])
    return (cdb.query(HREmployeeSalaryAssignment)
        .filter(HREmployeeSalaryAssignment.company_id==company_id,
                HREmployeeSalaryAssignment.employee_id==employee_id,
                HREmployeeSalaryAssignment.effective_from<=period_end,
                (HREmployeeSalaryAssignment.effective_to==None) | (HREmployeeSalaryAssignment.effective_to>=date(year,month,1)))
        .order_by(HREmployeeSalaryAssignment.effective_from.desc(),HREmployeeSalaryAssignment.id.desc()).first())

def _build_payroll_entry(cdb,company_id,run,employee,assignment):
    import calendar
    from decimal import Decimal, ROUND_HALF_UP
    start=date(run.year,run.month,1); end=date(run.year,run.month,calendar.monthrange(run.year,run.month)[1])
    working=present=paid_leave=unpaid_leave=absent=0.0
    cursor=start
    while cursor<=end:
        shift=_shift_for(cdb,company_id,employee.id,cursor)
        holiday=_holiday_for(cdb,company_id,employee,cursor)
        weekly=bool(shift and cursor.strftime("%A") in _weekly_offs(shift))
        if not holiday and not weekly:
            working+=1
            att=cdb.query(HRAttendance).filter_by(company_id=company_id,employee_id=employee.id,attendance_date=cursor).first()
            status=att.status if att else "Absent"
            if status in ("Present","Late"): present+=1
            elif status=="Half Day":
                present+=0.5; absent+=0.5
            elif status=="Paid Leave": paid_leave+=1
            elif status=="Unpaid Leave": unpaid_leave+=1
            else: absent+=1
        cursor+=timedelta(days=1)
    payable=max(0.0,working-unpaid_leave-absent)
    ratio=Decimal(str(payable/working if working else 0)).quantize(Decimal("0.000001"))
    basic=Decimal(str(assignment.basic_monthly or 0))
    entry=HRPayrollEntry(payroll_run_id=run.id,company_id=company_id,employee_id=employee.id,
        salary_assignment_id=assignment.id,calendar_days=(end-start).days+1,working_days=working,
        present_days=present,paid_leave_days=paid_leave,unpaid_leave_days=unpaid_leave,
        absent_days=absent,payable_days=payable,basic_monthly=basic,status="Calculated")
    gross=Decimal("0"); deductions=Decimal("0")
    ot_minutes=(cdb.query(HROvertimeRequest).join(HRAttendance,HROvertimeRequest.attendance_id==HRAttendance.id)
        .filter(HROvertimeRequest.company_id==company_id,HROvertimeRequest.employee_id==employee.id,
                HROvertimeRequest.status=="Approved",HRAttendance.attendance_date>=start,HRAttendance.attendance_date<=end)
        .all())
    approved_ot=sum(x.approved_minutes or 0 for x in ot_minutes)
    entry.approved_overtime_minutes=approved_ot
    for line in assignment.structure.lines:
        comp=line.component
        calc=line.calculation_type
        if (comp.code or "").upper()=="BASIC":
            full=basic
        elif calc=="Percent of Basic":
            full=(basic*Decimal(str(line.value or 0))/Decimal("100")).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
        else:
            full=Decimal(str(line.value or 0)).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
        code=(comp.code or "").upper()
        if code in ("OT","OVERTIME"):
            hourly=full if full>0 else ((basic/Decimal(str(max(1,working)))/Decimal("8")) if working else Decimal("0"))
            amount=(hourly*Decimal(str(approved_ot))/Decimal("60")).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
            prorated=False
        elif comp.component_type=="Earning":
            amount=(full*ratio).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
            prorated=(ratio!=Decimal("1.000000"))
        else:
            amount=full
            prorated=False
        pl=HRPayrollLine(component_id=comp.id,component_name=comp.name,component_code=comp.code,
            component_type=comp.component_type,amount=amount,is_prorated=prorated,sort_order=line.sort_order or 100)
        entry.lines.append(pl)
        if comp.component_type=="Deduction": deductions+=amount
        else: gross+=amount
    entry.gross_earnings=gross
    # Phase 6 statutory deductions are calculated after structural earnings so wage/gross bases are available.
    statutory_lines=_calculate_statutory(cdb,company_id,run,employee,entry,basic,gross)
    statutory_employee=sum((Decimal(str(x.employee_amount or 0)) for x in statutory_lines),Decimal("0"))
    entry.total_deductions=deductions+statutory_employee
    # Phase 7: loan/advance recovery and approved reimbursements.
    loan_recoveries=_payroll_loan_recoveries(cdb,company_id,run,employee,entry)
    loan_total=sum((Decimal(str(x.amount or 0)) for x in loan_recoveries),Decimal("0"))
    claims=_payroll_claims(cdb,company_id,run,employee)
    reimbursement_total=sum((Decimal(str(x.approved_amount or 0)) for x in claims),Decimal("0"))
    entry.total_deductions += loan_total
    entry.gross_earnings += reimbursement_total
    entry.net_pay=max(Decimal("0"),entry.gross_earnings-entry.total_deductions)
    entry._pending_statutory_lines=statutory_lines
    entry._pending_loan_recoveries=loan_recoveries
    entry._pending_claims=claims
    return entry

def _refresh_payroll_totals(run):
    from decimal import Decimal
    run.total_gross=sum((Decimal(str(e.gross_earnings or 0)) for e in run.entries),Decimal("0"))
    run.total_deductions=sum((Decimal(str(e.total_deductions or 0)) for e in run.entries),Decimal("0"))
    run.total_net=sum((Decimal(str(e.net_pay or 0)) for e in run.entries),Decimal("0"))


def _rule_cfg(rule):
    import json
    try: return json.loads(rule.settings_json or "{}")
    except Exception: return {}

def _seed_india_statutory_defaults(cdb,company_id):
    from platform_models import Company
    from tax_service import country_name
    company = Company.query.filter_by(company_id=company_id).first()
    if company and country_name(company.country) != 'India':
        return
    import json
    defaults=[
        ("PF","Provident Fund",date(2026,4,1),
         {"employee_rate":12.0,"employer_rate":12.0,"wage_ceiling":15000.0},
         "EPFO baseline: employee/employer contribution 12%; statutory wage ceiling ₹15,000. Editable and effective-dated."),
        ("ESI","Employees' State Insurance",date(2026,4,1),
         {"employee_rate":0.75,"employer_rate":3.25,"coverage_ceiling":21000.0},
         "ESIC baseline: employee 0.75%, employer 3.25%; coverage wage ceiling ₹21,000. Editable and effective-dated."),
        ("PT","Maharashtra Professional Tax",date(2026,4,1),
         {"male_nil_upto":7500.0,"male_mid_upto":10000.0,"male_mid_amount":175.0,
          "female_nil_upto":25000.0,"regular_amount":200.0,"february_amount":300.0},
         "Maharashtra salary/wage schedule baseline. Editable for company/state policy."),
        ("TDS","Salary TDS - New Regime",date(2026,4,1),
         {"standard_deduction":75000.0,"rebate_income_limit":1200000.0,"rebate_max":60000.0,"cess_rate":4.0},
         "Tax Year 2026-27 new-regime baseline. Slabs are implemented in code and should be reviewed when law changes.")
    ]
    changed=False
    for code,name,effective,cfg,note in defaults:
        if not cdb.query(HRStatutoryRule).filter_by(company_id=company_id,rule_code=code,effective_from=effective).first():
            cdb.add(HRStatutoryRule(company_id=company_id,rule_code=code,name=name,effective_from=effective,
                enabled=True,settings_json=json.dumps(cfg),source_note=note)); changed=True
    if changed: cdb.commit()

def _active_rule(cdb,company_id,code,on_date):
    return (cdb.query(HRStatutoryRule).filter(
        HRStatutoryRule.company_id==company_id,HRStatutoryRule.rule_code==code,
        HRStatutoryRule.enabled==True,HRStatutoryRule.effective_from<=on_date,
        (HRStatutoryRule.effective_to==None) | (HRStatutoryRule.effective_to>=on_date))
        .order_by(HRStatutoryRule.effective_from.desc(),HRStatutoryRule.id.desc()).first())

def _new_regime_tax_2026_27(taxable):
    from decimal import Decimal
    x=Decimal(str(max(0,taxable)))
    bands=[(Decimal("400000"),Decimal("0")),(Decimal("800000"),Decimal(".05")),
           (Decimal("1200000"),Decimal(".10")),(Decimal("1600000"),Decimal(".15")),
           (Decimal("2000000"),Decimal(".20")),(Decimal("2400000"),Decimal(".25"))]
    tax=Decimal("0"); lower=Decimal("0")
    for upper,rate in bands:
        if x>lower:
            tax += (min(x,upper)-lower)*rate
        lower=upper
        if x<=upper: return tax
    if x>Decimal("2400000"): tax+=(x-Decimal("2400000"))*Decimal(".30")
    return tax

def _calculate_statutory(cdb,company_id,run,employee,entry,basic,gross):
    from platform_models import Company
    from tax_service import country_name
    company = Company.query.filter_by(company_id=company_id).first()
    if company and country_name(company.country) != 'India':
        return []
    import json
    from decimal import Decimal, ROUND_HALF_UP
    period_end=date(run.year,run.month,__import__("calendar").monthrange(run.year,run.month)[1])
    profile=cdb.query(HREmployeeStatutoryProfile).filter_by(company_id=company_id,employee_id=employee.id).first()
    if not profile: return []
    lines=[]
    def money(x): return Decimal(str(x or 0)).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
    # PF: employee and employer contribution. By default the configured ceiling caps the contribution base.
    rule=_active_rule(cdb,company_id,"PF",period_end)
    if profile.pf_enabled and rule:
        cfg=_rule_cfg(rule); ceiling=Decimal(str(cfg.get("wage_ceiling",15000)))
        wage=basic if profile.pf_on_actual_basic else min(basic,ceiling)
        emp=money(wage*Decimal(str(cfg.get("employee_rate",12)))/100)
        er=money(wage*Decimal(str(cfg.get("employer_rate",12)))/100)
        lines.append(HRPayrollStatutoryLine(company_id=company_id,rule_code="PF",description="Provident Fund",
            employee_amount=emp,employer_amount=er,wage_base=wage,rule_snapshot=json.dumps(cfg,sort_keys=True)))
    # ESI: coverage is based on configured gross ceiling; contribution is on payroll gross.
    rule=_active_rule(cdb,company_id,"ESI",period_end)
    if profile.esi_enabled and rule:
        cfg=_rule_cfg(rule); ceiling=Decimal(str(cfg.get("coverage_ceiling",21000)))
        if gross<=ceiling:
            emp=money(gross*Decimal(str(cfg.get("employee_rate",.75)))/100)
            er=money(gross*Decimal(str(cfg.get("employer_rate",3.25)))/100)
            lines.append(HRPayrollStatutoryLine(company_id=company_id,rule_code="ESI",description="Employees' State Insurance",
                employee_amount=emp,employer_amount=er,wage_base=gross,rule_snapshot=json.dumps(cfg,sort_keys=True)))
    # Maharashtra PT baseline; can be disabled per employee/company.
    rule=_active_rule(cdb,company_id,"PT",period_end)
    if profile.pt_enabled and rule:
        cfg=_rule_cfg(rule); salary=gross; gender=(employee.gender or "").lower()
        amt=Decimal("0")
        if gender.startswith("f"):
            if salary>Decimal(str(cfg.get("female_nil_upto",25000))):
                amt=Decimal(str(cfg.get("february_amount",300) if run.month==2 else cfg.get("regular_amount",200)))
        else:
            if salary>Decimal(str(cfg.get("male_mid_upto",10000))):
                amt=Decimal(str(cfg.get("february_amount",300) if run.month==2 else cfg.get("regular_amount",200)))
            elif salary>Decimal(str(cfg.get("male_nil_upto",7500))):
                amt=Decimal(str(cfg.get("male_mid_amount",175)))
        if amt:
            lines.append(HRPayrollStatutoryLine(company_id=company_id,rule_code="PT",description="Professional Tax",
                employee_amount=money(amt),employer_amount=0,wage_base=salary,rule_snapshot=json.dumps(cfg,sort_keys=True)))
    # TDS: manual monthly override is safest; otherwise new-regime projection for TY 2026-27.
    rule=_active_rule(cdb,company_id,"TDS",period_end)
    if profile.tds_enabled and rule:
        cfg=_rule_cfg(rule)
        if profile.manual_monthly_tds is not None:
            tds=money(profile.manual_monthly_tds)
        elif profile.tax_regime=="New" and run.year>=2026:
            projected=Decimal(str(gross))*12 + Decimal(str(profile.annual_other_income or 0))
            taxable=max(Decimal("0"),projected-Decimal(str(cfg.get("standard_deduction",75000)))-Decimal(str(profile.annual_deductions or 0)))
            annual=_new_regime_tax_2026_27(taxable)
            if taxable<=Decimal(str(cfg.get("rebate_income_limit",1200000))):
                annual=max(Decimal("0"),annual-Decimal(str(cfg.get("rebate_max",60000))))
            annual=annual*(Decimal("1")+Decimal(str(cfg.get("cess_rate",4)))/100)
            remaining=max(Decimal("0"),annual-Decimal(str(profile.tds_already_deducted or 0)))
            months_left=max(1,13-run.month)
            tds=money(remaining/Decimal(str(months_left)))
        else:
            tds=Decimal("0")
        if tds:
            lines.append(HRPayrollStatutoryLine(company_id=company_id,rule_code="TDS",description="Salary TDS",
                employee_amount=tds,employer_amount=0,wage_base=gross,rule_snapshot=json.dumps(cfg,sort_keys=True)))
    return lines


def _next_loan_number(cdb,company_id):
    count=cdb.query(HREmployeeLoan).filter_by(company_id=company_id).count()+1
    return f"LN-{date.today().year}-{count:05d}"

def _period_key(year,month):
    return year*12+month

def _payroll_loan_recoveries(cdb,company_id,run,employee,entry):
    from decimal import Decimal
    period=_period_key(run.year,run.month); rows=[]
    loans=cdb.query(HREmployeeLoan).filter_by(company_id=company_id,employee_id=employee.id,status="Active").all()
    for loan in loans:
        if _period_key(loan.start_year,loan.start_month)>period or Decimal(str(loan.outstanding_amount or 0))<=0: continue
        amount=min(Decimal(str(loan.installment_amount or 0)),Decimal(str(loan.outstanding_amount or 0)))
        if amount<=0: continue
        rows.append(HRLoanRecovery(company_id=company_id,loan_id=loan.id,payroll_entry_id=0,amount=amount,status="Pending"))
    return rows

def _payroll_claims(cdb,company_id,run,employee):
    import calendar
    start=date(run.year,run.month,1); end=date(run.year,run.month,calendar.monthrange(run.year,run.month)[1])
    return (cdb.query(HRExpenseClaim).filter(
        HRExpenseClaim.company_id==company_id,HRExpenseClaim.employee_id==employee.id,
        HRExpenseClaim.status=="Approved",HRExpenseClaim.include_in_payroll==True,
        HRExpenseClaim.payroll_entry_id==None,HRExpenseClaim.claim_date<=end).all())


def _post_payroll_finance(cdb,company_id,run,post_auto_journal,ensure_chart_of_accounts=None):
    """Post one balanced payroll accrual journal, idempotent by payroll run id."""
    from decimal import Decimal
    if ensure_chart_of_accounts: ensure_chart_of_accounts(cdb,company_id)
    salary_gross=Decimal("0"); reimbursements=Decimal("0")
    statutory_employee={"PF":Decimal("0"),"ESI":Decimal("0"),"PT":Decimal("0"),"TDS":Decimal("0")}
    statutory_employer={"PF":Decimal("0"),"ESI":Decimal("0")}
    loan_recovery=Decimal("0")
    structural_deductions=Decimal("0")
    for entry in run.entries:
        claim_total=sum((Decimal(str(x.approved_amount or 0)) for x in cdb.query(HRExpenseClaim).filter_by(
            company_id=company_id,payroll_entry_id=entry.id).all()),Decimal("0"))
        reimbursements+=claim_total
        salary_gross+=Decimal(str(entry.gross_earnings or 0))-claim_total
        stats=cdb.query(HRPayrollStatutoryLine).filter_by(company_id=company_id,payroll_entry_id=entry.id).all()
        stat_emp=Decimal("0")
        for x in stats:
            e=Decimal(str(x.employee_amount or 0)); er=Decimal(str(x.employer_amount or 0))
            statutory_employee[x.rule_code]=statutory_employee.get(x.rule_code,Decimal("0"))+e
            statutory_employer[x.rule_code]=statutory_employer.get(x.rule_code,Decimal("0"))+er
            stat_emp+=e
        loans=sum((Decimal(str(x.amount or 0)) for x in cdb.query(HRLoanRecovery).filter_by(
            company_id=company_id,payroll_entry_id=entry.id).all()),Decimal("0"))
        loan_recovery+=loans
        structural=max(Decimal("0"),Decimal(str(entry.total_deductions or 0))-stat_emp-loans)
        structural_deductions+=structural

    employer_pf=statutory_employer.get("PF",Decimal("0"))
    employer_esi=statutory_employer.get("ESI",Decimal("0"))
    employer_total=employer_pf+employer_esi
    rows=[
        ("6100",salary_gross,0,"Salary and wages expense"),
        ("6800",reimbursements,0,"Approved employee reimbursements"),
        ("6150",employer_total,0,"Employer PF / ESI contributions"),
        ("2410",0,_money(run.total_net),"Net salary payable"),
        ("2420",0,statutory_employee.get("PF",0)+employer_pf,"PF payable"),
        ("2430",0,statutory_employee.get("ESI",0)+employer_esi,"ESI payable"),
        ("2440",0,statutory_employee.get("PT",0),"Professional tax payable"),
        ("2450",0,statutory_employee.get("TDS",0),"Salary TDS payable"),
        ("1710",0,loan_recovery,"Employee loan / advance recovery"),
        ("2470",0,structural_deductions,"Other payroll deductions payable"),
    ]
    return post_auto_journal(cdb,company_id,date(run.year,run.month,__import__("calendar").monthrange(run.year,run.month)[1]),
        f"Payroll accrual {run.month:02d}/{run.year}","payroll_accrual",run.id,f"PAYROLL-{run.id}",rows)

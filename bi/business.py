"""Company-wide, read-only module overview with explicit time and currency scopes."""
from datetime import datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import DateTime, func, inspect
from .business_charts import chart, volume_trend, ledger_performance, month_labels

from customer_models import (CustomerInvoice, PurchaseInvoice, Expense, CRMLead, CRMQuotation,
    StockItem, PurchaseOrder, SalesOrder, DeliveryChallan, OrderFlow, WorkshopJobCard,
    HREmployee, HRAttendance, HRLeaveRequest, HRPayrollRun)

MODULES = (
    ('core', 'Finance & Accounting', 'finance_workspace', '#0d9488'),
    ('crm', 'CRM & Sales Pipeline', 'crm_view', '#8b5cf6'),
    ('orderflow', 'Supply Chain & Production', 'supply_chain_workspace', '#2563eb'),
    ('repair', 'Workshop & Repair', 'workshop_erp_view', '#d97706'),
    ('hr', 'HR & Payroll', 'hr_dashboard', '#db2777'),
)
EXCLUDED = ('draft', 'void', 'cancelled', 'canceled')


def norm(column):
    return func.lower(func.trim(func.coalesce(column, '')))


def business_overview(cdb, company_id, start, end, today, module_access, can, currency):
    """Only query entitled source modules. Money is grouped by document currency.

    Statuses and balances are current snapshots; dated activity uses inclusive
    start/end dates. CRM/order/workshop values are never added to invoice revenue.
    """
    inspector = inspect(cdb.get_bind())
    tables = set(inspector.get_table_names())
    result = dict(modules=[], from_date=start, to_date=end, today=today, alerts=[])
    previous_start = start - timedelta(days=(end - start).days + 1)
    previous_end = start - timedelta(days=1)
    result.update(previous_start=previous_start, previous_end=previous_end)

    def source(model):
        return cdb.query(model).filter(model.company_id == company_id)

    def period(query, column, first=start, last=end):
        if isinstance(column.type, DateTime):
            return query.filter(column >= datetime.combine(first, time.min),
                                column < datetime.combine(last + timedelta(days=1), time.min))
        return query.filter(column >= first, column <= last)

    def add_count(card, label, query, note='Current snapshot', prior=None):
        value = query.count()
        metric = dict(label=label, value=value, kind='count', note=note, previous=prior)
        card['metrics'].append(metric)
        return value

    def activity(card, label, query, column):
        previous = period(query, column, previous_start, previous_end).count()
        card['charts'].append(volume_trend(period(query, column), column, start, end, label + ' trend'))
        return add_count(card, label, period(query, column), 'Selected period', previous)

    def money(card, label, query, amount, currency_column=None, note='Selected period'):
        if currency_column is not None:
            cc = func.coalesce(func.nullif(func.upper(func.trim(currency_column)), ''), 'Unspecified')
            values = query.with_entities(cc, func.sum(amount)).group_by(cc).all()
        else:
            values = [(currency, query.with_entities(func.sum(amount)).scalar())]
        card['metrics'].append(dict(label=label, kind='money', value=None, note=note, previous=None,
            amounts=[dict(currency=cc, value=round(float(Decimal(str(value or 0))), 2)) for cc, value in values]))

    def breakdown(card, label, query, column, scope='Current snapshot'):
        rows = query.with_entities(func.coalesce(column, 'Unspecified'), func.count()).group_by(column).all()
        rows = sorted(rows, key=lambda row: (-row[1], str(row[0])))
        maximum = max((row[1] for row in rows), default=1)
        card['breakdowns'].append(dict(label=label, rows=[dict(label=str(name), count=count,
            width=round(count / maximum * 100, 1)) for name, count in rows]))
        if rows:
            card['charts'].append(chart(label, [str(name) for name, _ in rows],
                [('Records', [count for _, count in rows])], scope=scope,
                note='Record counts; not monetary amounts or a historical status reconstruction.', source=column.table.name))

    def amount_trend(card, label, query, day_column, amount_column, currency_column=None):
        from collections import defaultdict
        cc = func.coalesce(func.nullif(func.upper(func.trim(currency_column)), ''), 'Unspecified') if currency_column is not None else None
        fields = [func.date(day_column), func.sum(amount_column)]
        if cc is not None:
            fields.append(cc)
        rows = query.with_entities(*fields).group_by(func.date(day_column), *([cc] if cc is not None else [])).all()
        currencies = defaultdict(lambda:defaultdict(Decimal))
        for row in rows:
            currencies[row[2] if cc is not None else currency][str(row[0])[:7]] += Decimal(str(row[1] or 0))
        months = month_labels(start, end)
        for code, values in sorted(currencies.items()):
            card['charts'].append(chart(label + ' · ' + code, months,
                [(label,[round(float(values[month]),2) for month in months])], kind='line', unit='money', currency=code,
                note='Selected-date totals by calendar month. Currencies are never combined.', source=day_column.table.name))

    def ready(card, model, permission=None):
        if permission and not any(can(key, 'view') for key in permission.split('|')):
            card['notes'].append('Some measures are hidden by your record permissions.')
            return False
        if model.__tablename__ not in tables:
            card['notes'].append('Some data sources need setup before their measures can be shown.')
            return False
        columns = {c['name'] for c in inspector.get_columns(model.__tablename__)}
        if not set(model.__table__.columns.keys()).issubset(columns):
            card['notes'].append('Some data sources need an update before their measures can be shown.')
            return False
        return True

    def alert(card, count, message):
        if count:
            result['alerts'].append(dict(module=card['name'], count=count, message=message, key=card['key']))

    for key, name, endpoint, color in MODULES:
        card = dict(key=key, name=name, endpoint=endpoint, color=color, metrics=[], breakdowns=[], charts=[], notes=[],
                    enabled=bool(module_access(key)))
        result['modules'].append(card)
        if not card['enabled']:
            card['notes'].append('Not available under your plan or module access settings.')
            continue
        if key == 'core':
            if ready(card, CustomerInvoice, 'invoices|customer_invoices'):
                q = source(CustomerInvoice).filter(norm(CustomerInvoice.status).notin_(EXCLUDED))
                # Match sales versus repair document permissions, including historical job links.
                if not (can('invoices', 'view') and can('customer_invoices', 'view')):
                    from sqlalchemy import or_
                    repair = CustomerInvoice.invoice_category == 'workshop_repair'
                    if WorkshopJobCard.__tablename__ in tables:
                        repair = or_(repair, cdb.query(WorkshopJobCard.id).filter(
                            WorkshopJobCard.company_id == company_id,
                            WorkshopJobCard.invoice_id == CustomerInvoice.id).exists())
                    q = q.filter(repair if can('customer_invoices', 'view') else ~func.coalesce(repair, False))
                activity(card, 'Sales invoices issued', q, CustomerInvoice.invoice_date)
                pq = period(q, CustomerInvoice.invoice_date)
                money(card, 'Billed sales incl. tax', pq, CustomerInvoice.grand_total, CustomerInvoice.currency)
                money(card, 'Sales excl. tax', pq, CustomerInvoice.subtotal, CustomerInvoice.currency)
                amount_trend(card, 'Invoiced sales excl. tax', pq, CustomerInvoice.invoice_date, CustomerInvoice.subtotal, CustomerInvoice.currency)
                money(card, 'Outstanding receivables', q.filter(CustomerInvoice.balance > 0),
                      CustomerInvoice.balance, CustomerInvoice.currency, 'Current saved balances · all invoice dates')
                overdue = q.filter(CustomerInvoice.balance > 0, CustomerInvoice.due_date < today)
                alert(card, add_count(card, 'Overdue sales invoices', overdue), 'sales invoices have overdue balances')
                breakdown(card, 'Sales invoices by status', q, CustomerInvoice.status)
                breakdown(card, 'Sales by invoice type', q, CustomerInvoice.invoice_type)
            if ready(card, PurchaseInvoice, 'purchase'):
                q = source(PurchaseInvoice).filter(norm(PurchaseInvoice.status).notin_(EXCLUDED))
                money(card, 'Purchase invoices incl. tax', period(q, PurchaseInvoice.date),
                      PurchaseInvoice.grand_total, PurchaseInvoice.currency)
                amount_trend(card, 'Purchase invoices incl. tax', period(q, PurchaseInvoice.date), PurchaseInvoice.date,
                             PurchaseInvoice.grand_total, PurchaseInvoice.currency)
                money(card, 'Outstanding payables', q.filter(PurchaseInvoice.balance > 0),
                      PurchaseInvoice.balance, PurchaseInvoice.currency, 'Current saved balances · all invoice dates')
                breakdown(card, 'Purchase invoices by status', q, PurchaseInvoice.status)
            if ready(card, Expense, 'expenses'):
                money(card, 'Recorded expenses', period(source(Expense), Expense.date), Expense.amount,
                      note='Selected period · company currency')
                amount_trend(card, 'Recorded expenses', period(source(Expense), Expense.date), Expense.date, Expense.amount)
                breakdown(card, 'Expense records by category', period(source(Expense), Expense.date), Expense.category, 'Selected period')
                breakdown(card, 'Expense records by payment mode', period(source(Expense), Expense.date), Expense.payment_mode, 'Selected period')
            if can('finance', 'view') and can('analytics', 'view'):
                result['financial_position'] = ledger_performance(cdb, company_id, start, end, previous_start, previous_end, currency)
                card['charts'][0:0] = result['financial_position']['charts']
            card['notes'].append('Sales invoices include billed workshop work once. Pipeline and order values are not revenue. Currency totals remain separate; expenses are not a profit calculation.')
        elif key == 'crm':
            if ready(card, CRMLead):
                q = source(CRMLead)
                activity(card, 'Leads created', q, CRMLead.created_at)
                opened = q.filter(norm(CRMLead.stage).notin_(('won', 'lost')))
                add_count(card, 'Open opportunities', opened)
                add_count(card, 'Won leads from period cohort', period(q, CRMLead.created_at).filter(norm(CRMLead.stage) == 'won'),
                          'Current outcome of leads created in selected period')
                alert(card, add_count(card, 'Past expected close date', opened.filter(CRMLead.expected_close_date < today)),
                      'open opportunities are past their expected close date')
                breakdown(card, 'Current pipeline by stage', q, CRMLead.stage)
                breakdown(card, 'Leads by source', q, CRMLead.source)
            if ready(card, CRMQuotation):
                activity(card, 'Quotations created', source(CRMQuotation), CRMQuotation.created_at)
                breakdown(card, 'Period quotations by current status', period(source(CRMQuotation), CRMQuotation.created_at), CRMQuotation.status, 'Created in selected period · current status')
            card['notes'].append('Lead and quotation values are not totalled because these records do not store currency. Won leads are a creation-period cohort, not wins dated within the period.')
        elif key == 'orderflow':
            if ready(card, StockItem, 'stock'):
                stock = source(StockItem)
                add_count(card, 'Stock items', stock)
                low = stock.filter(StockItem.quantity <= func.coalesce(StockItem.reorder_level, 0))
                alert(card, add_count(card, 'At / below reorder level', low), 'stock items are at or below reorder level')
                add_count(card, 'Negative stock items', stock.filter(StockItem.quantity < 0))
                breakdown(card, 'Stock items by category', stock, StockItem.category)
            for model, field, permission, title, closed in (
                (PurchaseOrder, PurchaseOrder.po_date, 'purchase_orders', 'Purchase orders', ('received','completed','closed','invoiced')),
                (SalesOrder, SalesOrder.order_date, 'sales_orders', 'Sales orders', ('shipped','delivered','completed','closed','invoiced')),
                (DeliveryChallan, DeliveryChallan.challan_date, 'delivery_challans', 'Delivery challans', ('delivered','completed','closed','invoiced')),
            ):
                if ready(card, model, permission):
                    q = source(model).filter(norm(model.status).notin_(('void', 'cancelled', 'canceled')))
                    activity(card, title + ' created', q, field)
                    opened = q.filter(norm(model.status).notin_(closed + ('draft',)))
                    add_count(card, 'Open ' + title.lower(), opened)
                    if model is PurchaseOrder:
                        alert(card, add_count(card, 'Overdue purchase orders', opened.filter(model.expected_delivery_date < today)),
                              'purchase orders are overdue')
                    breakdown(card, title + ' by status', q, model.status)
            if ready(card, OrderFlow):
                q = source(OrderFlow).filter(norm(OrderFlow.status) != 'cancelled')
                activity(card, 'Production orders created', q, OrderFlow.created_at)
                add_count(card, 'Open production orders', q.filter(norm(OrderFlow.status) != 'delivered'))
                alert(card, add_count(card, 'Quality checks failed', q.filter(norm(OrderFlow.status) == 'quality check failed')),
                      'production orders need quality attention')
                breakdown(card, 'Current production stages', q, OrderFlow.status)
            card['notes'].append('Stock is the current snapshot. Quantities in different units are not added together. Orders and challans are operational counts, not additional sales revenue.')
        elif key == 'repair':
            if ready(card, WorkshopJobCard):
                q = source(WorkshopJobCard).filter(norm(WorkshopJobCard.status) != 'cancelled')
                activity(card, 'Job cards opened', q, WorkshopJobCard.created_at)
                opened = q.filter(norm(WorkshopJobCard.status) != 'delivered')
                add_count(card, 'Active job cards', opened)
                add_count(card, 'Delivered jobs from period cohort', period(q, WorkshopJobCard.created_at).filter(norm(WorkshopJobCard.status) == 'delivered'),
                          'Current outcome of jobs opened in selected period')
                alert(card, add_count(card, 'Overdue promised deliveries', opened.filter(
                    WorkshopJobCard.estimated_delivery_date < datetime.combine(today, time.min))),
                    'workshop jobs are past their promised delivery date')
                breakdown(card, 'Current workshop stages', q, WorkshopJobCard.status)
                breakdown(card, 'Job cards by priority', q, WorkshopJobCard.priority)
                breakdown(card, 'Job cards by service type', q, WorkshopJobCard.job_type)
            card['notes'].append('Job-card totals are not revenue. Billed workshop work is included in Finance sales invoices; no second revenue total is added here.')
        elif key == 'hr':
            if ready(card, HREmployee, 'hr_employees'):
                q = source(HREmployee)
                add_count(card, 'Active employees', q.filter(norm(HREmployee.status) == 'active'))
                activity(card, 'Employees joined', q, HREmployee.joining_date)
                breakdown(card, 'Current employment status', q, HREmployee.status)
                breakdown(card, 'Workforce by employment type', q, HREmployee.employment_type)
            if ready(card, HRAttendance, 'hr_attendance'):
                q = period(source(HRAttendance), HRAttendance.attendance_date)
                add_count(card, 'Attendance records', q, 'Selected period · employee-days, not headcount')
                card['charts'].append(volume_trend(q, HRAttendance.attendance_date, start, end, 'Attendance employee-days recorded'))
                breakdown(card, 'Recorded attendance in period', q, HRAttendance.status, 'Selected period · employee-days')
            if ready(card, HRLeaveRequest, 'hr_leave'):
                q = source(HRLeaveRequest)
                alert(card, add_count(card, 'Leave awaiting approval', q.filter(norm(HRLeaveRequest.status) == 'pending')),
                      'leave requests await approval')
                add_count(card, 'Approved leave requests overlapping period', q.filter(norm(HRLeaveRequest.status) == 'approved',
                    HRLeaveRequest.start_date <= end, HRLeaveRequest.end_date >= start), 'Period overlap · requests, not leave days')
                breakdown(card, 'Leave requests by status', q, HRLeaveRequest.status)
            if ready(card, HRPayrollRun, 'hr_payroll'):
                q = source(HRPayrollRun).filter(HRPayrollRun.year * 100 + HRPayrollRun.month >= start.year * 100 + start.month,
                    HRPayrollRun.year * 100 + HRPayrollRun.month <= end.year * 100 + end.month)
                approved = q.filter(norm(HRPayrollRun.status).in_(('approved', 'locked')))
                money(card, 'Approved payroll net pay', approved, HRPayrollRun.total_net,
                      note='Whole payroll months touched by date range · company currency')
                payroll = approved.with_entities(HRPayrollRun.year, HRPayrollRun.month, HRPayrollRun.total_gross,
                    HRPayrollRun.total_deductions, HRPayrollRun.total_net).order_by(HRPayrollRun.year, HRPayrollRun.month).all()
                if payroll:
                    card['charts'].append(chart('Approved payroll composition', [f'{r.year:04}-{r.month:02}' for r in payroll],
                        [('Gross pay',[float(r.total_gross) for r in payroll]), ('Deductions',[float(r.total_deductions) for r in payroll]),
                         ('Net pay',[float(r.total_net) for r in payroll])], unit='money', currency=currency,
                        scope='Whole payroll months in range', note='Approved/locked runs only. Amounts are not added to Finance expenses again.', source='hr_payroll_runs'))
                add_count(card, 'Approved payroll runs unpaid', approved.filter(norm(HRPayrollRun.payment_status) != 'paid'),
                          'Payroll months in range · current payment status')
                breakdown(card, 'Payroll runs in selected months', q, HRPayrollRun.status, 'Whole payroll months in range · current status')
            card['notes'].append('Attendance counts recorded employee-days, not an attendance rate. Payroll uses complete months, excludes drafts and is not added again to Finance expenses.')
        card['notes'] = list(dict.fromkeys(card['notes']))
        comparable = [metric for metric in card['metrics'] if metric.get('previous') is not None]
        if comparable:
            card['charts'].insert(0, chart('Activity compared with previous equal period', [m['label'] for m in comparable],
                [('Current', [m['value'] for m in comparable]), ('Previous', [m['previous'] for m in comparable])],
                note=f'Current: {start} to {end}. Previous: {previous_start} to {previous_end}. Counts are separate activities, not a combined total.'))
        card['attention'] = [a for a in result['alerts'] if a['key'] == key]
    return result

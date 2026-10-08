"""Core finance entry point. Reads existing records; never creates transactions."""
from datetime import date

from flask import abort, render_template, request, session, url_for
from sqlalchemy import case, func, or_

from customer_models import CustomerInvoice, PurchaseInvoice, WorkshopJobCard


# Permissions match the destination routes, including the legacy sales-list gate.
FINANCE_SECTIONS = (
    ('Sales & collections', (
        ('Sales invoices', 'customer_invoice_list', 'invoices'),
        ('GST e-invoice & e-way bill', 'gst_portal', 'invoices'),
        ('Repair bills', 'repair_bills_view', 'customer_invoices'),
        ('Customer receivables', 'debtors_list', 'debtors'),
        ('Record receipts', 'receipt_new', 'receipts_payments'),
        ('Estimates / quotes', 'estimate_list', 'estimates'),
    )),
    ('Purchases & payments', (
        ('Purchase invoices', 'purchase_invoice_list', 'purchase'),
        ('Supplier payables', 'creditors_list', 'creditors'),
        ('Record payments', 'payment_new', 'receipts_payments'),
        ('Expenses', 'expenses', 'expenses'),
    )),
    ('Cash & banking', (
        ('Bank accounts', 'bank_accounts', 'bank'),
        ('Cash in hand', 'cash_in_hand', 'cash'),
        ('Cheques', 'cheques', 'cheques'),
        ('Loan accounts', 'loan_accounts', 'loans'),
    )),
    ('Customers & suppliers', (
        ('Customers', 'client_list', 'clients'),
        ('Suppliers', 'supplier_list', 'suppliers'),
    )),
    ('Reports', (
        ('Business intelligence', 'bi_dashboard', 'analytics'),
        ('Sales, purchase & tax reports', 'reports_dashboard', 'analytics'),
        ('General ledger', 'ledger', 'analytics'),
        ('Trial balance', 'trial_balance', 'analytics'),
        ('Profit & loss', 'profit_loss', 'analytics'),
        ('Balance sheet', 'balance_sheet', 'analytics'),
        ('Cash flow', 'cash_flow', 'analytics'),
    )),
)


def invoice_balances(cdb, company_id, can, today):
    """Current invoice-only balances, separated by currency and document family.

    EXISTS preserves one row per invoice even if historical job links repeat.
    Legacy booking Invoice rows are deliberately not added to their aggregate
    CustomerInvoice. Opening balances and unapplied advances belong to existing
    party statements, not this invoice-only overview.
    """
    rows = []
    linked_repair = cdb.query(WorkshopJobCard.id).filter(
        WorkshopJobCard.company_id == company_id,
        WorkshopJobCard.invoice_id == CustomerInvoice.id,
    ).exists()
    repair = or_(CustomerInvoice.invoice_category == 'workshop_repair', linked_repair)
    sources = (
        ('Sales invoices', CustomerInvoice, 'invoices', ~func.coalesce(repair, False)),
        ('Repair bills', CustomerInvoice, 'customer_invoices', repair),
        ('Purchase invoices', PurchaseInvoice, 'purchase', None),
    )
    for label, model, permission, extra in sources:
        if not can(permission, 'view'):
            continue
        balance = func.coalesce(model.balance, model.grand_total - model.paid_amount, 0)
        query = cdb.query(
            model.currency,
            func.count(model.id),
            func.sum(balance),
            func.sum(case((model.due_date < today, balance), else_=0)),
        ).filter(
            model.company_id == company_id,
            func.lower(func.trim(func.coalesce(model.status, ''))).notin_(
                ('draft', 'void', 'cancelled', 'canceled')),
            balance > 0,
        )
        if extra is not None:
            query = query.filter(extra)
        for currency, count, outstanding, overdue in query.group_by(model.currency).order_by(model.currency):
            rows.append(dict(label=label, currency=currency or 'Unspecified', count=count,
                             outstanding=outstanding, overdue=overdue))
    return rows


# A missing endpoint denotes a planned capability, never an empty working screen.
FINANCE_NAV = (
    ('CORE FINANCE', (('Finance Dashboard', 'finance_dashboard_view', 'finance', {}),)),
    ('RECEIVABLES', (
        ('Customer Receivables', 'debtors_list', 'debtors', {}),
        ('Sales Invoices', 'customer_invoice_list', 'invoices', {}),
        ('GST e-Invoice & e-Way Bill', 'gst_portal', 'invoices|customer_invoices', {}),
        ('Repair Bills', 'repair_bills_view', 'customer_invoices', {}),
        ('Receipts', 'receipt_new', 'receipts_payments', {}),
        ('Credit Notes', 'finance_note_list', 'customer_invoices', {'kind': 'credit'}),
        ('Receivable Ageing', 'finance_records', 'invoices|customer_invoices', {'kind':'receivables'}),
    )),
    ('PAYABLES', (
        ('Supplier Payables', 'creditors_list', 'creditors', {}),
        ('Purchase Invoices', 'purchase_invoice_list', 'purchase', {}),
        ('Payments', 'payment_new', 'receipts_payments', {}),
        ('Debit Notes', 'finance_note_list', 'purchase', {'kind': 'debit'}),
        ('Payable Ageing', 'finance_records', 'purchase', {'kind':'payables'}),
    )),
    ('ACCOUNTING', (
        ('Accounting Checks', 'finance_checks', 'finance', {}),
        ('Financial Periods', 'finance_periods', 'finance', {}),
        ('Chart of Accounts', 'chart_of_accounts', 'finance', {}),
        ('Journal Entries', 'journal_entries', 'finance', {}),
        ('General Ledger', 'ledger', 'analytics', {}),
        ('Trial Balance', 'trial_balance', 'analytics', {}),
        ('Profit & Loss', 'profit_loss', 'analytics', {}),
        ('Balance Sheet', 'balance_sheet', 'analytics', {}),
        ('Cash Flow', 'cash_flow', 'analytics', {}),
    )),
    ('BANKING & CASH', (
        ('Bank Accounts', 'bank_accounts', 'bank', {}),
        ('Cash in Hand', 'cash_in_hand', 'cash', {}),
        ('Cheques', 'cheques', 'cheques', {}),
        ('Bank Reconciliation', 'bank_reconciliation', 'bank', {}),
        ('Loan Accounts', 'loan_accounts', 'loans', {}),
    )),
    ('TAX', (
        ('GST / VAT & Tax Dashboard', 'finance_tax_report', 'finance', {}),
        ('Input Tax', 'finance_records', 'purchase', {'kind':'input-tax'}),
        ('Output Tax', 'finance_records', 'invoices|customer_invoices', {'kind':'output-tax'}),
    )),
    ('EXPENSES & ASSETS', (
        ('Expenses', 'expenses', 'expenses', {}),
        ('Fixed Assets', 'fixed_assets', 'finance', {}),
        ('Depreciation', 'fixed_assets', 'finance', {}),
    )),
    ('REPORTS', (('Finance Reports', 'reports_dashboard', 'analytics', {}),)),
)


def finance_navigation(can, company=None):
    from tax_service import tax_profile
    profile = tax_profile(company) if company else {}
    is_vat = profile.get('is_vat', False)
    is_gst = profile.get('is_gst', True)
    country = profile.get('country', '')

    if is_vat:
        tax_title = f"{'UAE ' if country == 'United Arab Emirates' else ''}VAT Return & Tax"
        input_tax_title = 'Input VAT'
        output_tax_title = 'Output VAT'
    elif is_gst:
        tax_title = 'GST & Tax Dashboard'
        input_tax_title = 'Input Tax (ITC)'
        output_tax_title = 'Output Tax'
    else:
        tax_title = 'Tax Dashboard'
        input_tax_title = 'Input Tax'
        output_tax_title = 'Output Tax'

    groups = []
    for heading, entries in FINANCE_NAV:
        links = []
        for label, endpoint, permission, args in entries:
            if endpoint == 'gst_portal' and (not is_gst or country not in ('', 'India')):
                continue
            if not any(can(p, 'view') for p in permission.split('|')):
                continue
            display_label = label
            if heading == 'TAX':
                if endpoint == 'finance_tax_report':
                    display_label = tax_title
                elif args.get('kind') == 'input-tax':
                    display_label = input_tax_title
                elif args.get('kind') == 'output-tax':
                    display_label = output_tax_title
            links.append(dict(label=display_label, endpoint=endpoint,
                              href=url_for(endpoint, **args) if endpoint else None,
                              active=bool(endpoint and endpoint == request.endpoint and
                                          not args.get('_anchor') and
                                          (not args.get('kind') or args['kind'] == (request.view_args or {}).get('kind')) and
                                          (not args.get('tab') or args['tab'] == request.args.get('tab')) and
                                          not (label == 'Finance Reports' and request.args.get('tab') == 'tax'))))
        if links:
            groups.append(dict(heading=heading, links=links))
    return groups


def uses_finance_navigation(role, endpoint, path, source, workspace=None):
    # HR & Payroll is a separate workspace and must never inherit Finance navigation.
    if (endpoint and (endpoint == 'hr_dashboard' or endpoint.startswith('hr_'))) or path == '/hr' or path.startswith('/hr/'):
        return False
    # BI Intelligence is a separate workspace and must never inherit Finance navigation.
    if endpoint in ('bi_intelligence', 'bi_dashboard', 'reports_dashboard'):
        return False
    if path in ('/bi-intelligence', '/bi-dashboard', '/reports-dashboard'):
        return False
    if path == '/finance' or path.startswith('/finance/'):
        return True
    workspace = workspace or ('finance' if role == 'accountant' else 'core')
    if workspace != 'finance' or endpoint in ('apps_hub', 'select_company'):
        return False
    return (source not in ('crm_routes', 'crm_workspace', 'order_erp_routes', 'workshop_routes')
            or endpoint in ('repair_bills_view', 'repair_bill_view'))


def register_finance_workspace(app, login_required, require_permission, get_cdb,
                               get_current_company, has_permission, today_func=date.today,
                               get_company=None):
    from finance_dashboard import dashboard_data, parse_filters, source_documents, select_documents, totals, BUCKETS, ageing_bucket

    def filters():
        company_id = get_current_company()
        if not company_id:
            abort(403)
        try:
            return parse_filters(request.args, today_func(), company_id,
                                 company=get_company(company_id) if get_company else None)
        except ValueError as error:
            abort(400, description=str(error))

    def drill(kind, f, **extra):
        return url_for('finance_records', kind=kind, fy=f['fy'],
                       from_date=f['start'].isoformat(), to_date=f['end'].isoformat(), **extra)

    def source_url(row):
        if row.get('note_id'):
            return url_for('finance_note_view', kind=row['note_kind'], note_id=row['note_id'])
        if row['kind'] == 'purchase':
            return url_for('purchase_invoice_view', invoice_id=row['reference'])
        if row['kind'] == 'repair':
            return (url_for('repair_bill_view', job_card_id=row['job_id']) if row.get('job_id')
                    else url_for('repair_bills_view', q=row['reference']))
        return url_for('customer_invoice_view', cust_inv_id=row['id'])

    @app.before_request
    def remember_finance_workspace():
        # Only explicit workspace entry points change context. Ordinary list,
        # detail and form requests keep the selected company's preference.
        if request.method != 'GET' or not session.get('user'):
            return
        company_id = get_current_company()
        if not company_id:
            return
        if request.endpoint == 'finance_workspace':
            workspace, permission = 'finance', 'finance'
        elif request.endpoint == 'bi_dashboard' and request.args.get('workspace') == 'core':
            workspace, permission = 'core', 'analytics'
        else:
            return
        if not has_permission(permission, 'view'):
            return
        module_access = app.extensions.get('module_access')
        if module_access and not module_access('core'):
            return
        workspaces = dict(session.get('workspace_by_company') or {})
        workspaces[str(company_id)] = workspace
        session['workspace_by_company'] = workspaces

    @app.context_processor
    def inject_finance_navigation():
        view = app.view_functions.get(request.endpoint)
        curr_co = get_current_company()
        show = uses_finance_navigation(
            (session.get('user') or {}).get('role'), request.endpoint, request.path,
            getattr(view, '__module__', ''),
            (session.get('workspace_by_company') or {}).get(str(curr_co))
        ) and bool(curr_co) and has_permission('finance', 'view')
        if show and app.extensions.get('module_access'):
            show = app.extensions['module_access']('core')
        co_obj = get_company(curr_co) if (show and get_company and curr_co) else None
        return dict(use_finance_navigation=show,
                    finance_navigation=finance_navigation(has_permission, company=co_obj) if show else [])

    @app.route('/finance')
    @login_required
    @require_permission('finance', 'view')
    def finance_workspace():
        f = filters()
        company = get_company(f['company_id']) if get_company else None
        currency = getattr(company, 'currency', None) or 'INR'
        data = dashboard_data(get_cdb(), f['company_id'], has_permission, f, currency)
        sales_access = has_permission('invoices', 'view') or has_permission('customer_invoices', 'view')
        purchase_access = has_permission('purchase', 'view')
        kpis = []
        def card(label, values, href, note, allowed=True, pending=None):
            kpis.append(dict(label=label, values=values if allowed else {}, href=href if allowed else None,
                             note=note if allowed else 'Not available for your role',
                             pending=pending if allowed else 'No access'))
        card('Cash in Hand', {currency:data['cash']}, url_for('cash_in_hand'),
             'Current recorded cashbook balance', has_permission('cash','view'))
        card('Cash at Bank', {currency:data['bank_total']}, url_for('bank_accounts'),
             'Current recorded balances · active accounts', has_permission('bank','view'))
        card('Accounts Receivable', data['receivables']['total'], drill('receivables',f),
             'Current open sales & repair invoices', sales_access)
        card('Accounts Payable', data['payables']['total'], drill('payables',f),
             'Current open purchase invoices', purchase_access)
        card('Overdue Receivables', data['receivables']['overdue'], drill('receivables',f,mode='overdue'),
             'Due before today · current balance', sales_access)
        card('Overdue Payables', data['payables']['overdue'], drill('payables',f,mode='overdue'),
             'Due before today · current balance', purchase_access)
        card('Sales', data['sales'], drill('sales',f), 'Period invoice subtotal · excluding tax', sales_access)
        card('Purchases', data['purchases'], drill('purchases',f), 'Period invoice subtotal · excluding tax', purchase_access)
        card('Expenses', {currency:data['expenses']}, url_for('expenses',from_date=f['start'],to_date=f['end']),
             'Period expense-register total', has_permission('expenses','view'))
        for label in ('Gross Profit','Net Profit'):
            card(label, {}, '#profitability', 'Requires posted revenue, costs and adjustments', pending='Needs accounting engine')
        tax_lbl = f.get('tax_label', 'Tax')
        card(f'{tax_lbl} Position', {}, url_for('finance_tax_report'), f'Invoice {tax_lbl.lower()} is shown below; eligibility and adjustments are not verified',
             has_permission('finance','view'), pending=f'Needs {tax_lbl.lower()} reconciliation')
        for section in ('receivables','payables'):
            for row in data[section]['soon']:
                row['href'] = source_url(row)
        return render_template('finance_workspace.html', active='finance', f=f, data=data, kpis=kpis,
                               drill=lambda kind, **extra: drill(kind,f,**extra),
                               sales_access=sales_access, purchase_access=purchase_access,
                               can=has_permission, finance_company=company)

    @app.route('/finance/records/<kind>')
    @login_required
    @require_permission('finance', 'view')
    def finance_records(kind):
        f = filters()
        permitted = (has_permission('purchase','view') if kind in ('payables','purchases','input-tax') else
                     has_permission('invoices','view') or has_permission('customer_invoices','view'))
        if not permitted:
            abort(403)
        try:
            rows = select_documents(source_documents(get_cdb(), f['company_id'], has_permission), kind, f,
                                    request.args.get('mode',''), request.args.get('bucket',''))
            page = int(request.args.get('page',1))
            if page < 1:
                raise ValueError('Invalid page.')
        except ValueError as error:
            abort(400, description=str(error))
        field = 'balance' if kind in ('receivables','payables') else 'tax' if kind.endswith('tax') else 'subtotal'
        summary = totals(rows, field)
        count = len(rows)
        shown = rows[(page-1)*50:page*50]
        for row in shown:
            row['href'] = source_url(row)
            row['ageing'] = ageing_bucket(row['due'], f['today'])
        args = request.args.to_dict()
        args.pop('page',None)
        return render_template('finance_records.html', active='finance', kind=kind, f=f, rows=shown,
                               summary=summary, field=field, count=count, buckets=BUCKETS,
                               page=page, next_url=url_for('finance_records',kind=kind,page=page+1,**args) if page*50<count else None,
                               prev_url=url_for('finance_records',kind=kind,page=page-1,**args) if page>1 else None)

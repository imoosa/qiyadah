"""Company close-through controls and conservative application write guards."""
from datetime import date, datetime
import hmac
import secrets

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause
import customer_models as models

Control = models.FinancePeriodControl
Audit = models.FinancePeriodAudit


class ClosedPeriodError(ValueError):
    pass


# Headers and their business dates. All changes to a closed source are blocked,
# including payment-state edits; reopen explicitly to settle historical sources.
DATED = {
    'journal_entries': 'entry_date', 'invoices': 'date',
    'customer_invoices': 'invoice_date', 'purchase_invoices': 'date',
    'finance_notes': 'note_date', 'cash_transactions': 'date',
    'bank_transactions': 'date', 'purchase_payments': 'date',
    'expenses': 'date', 'loans': 'loan_date', 'loan_repayments': 'date',
    'cheques': 'cheque_date', 'fixed_assets': 'purchase_date',
    'stock_purchase_history': 'purchase_date',
}
CHILDREN = {
    'journal_entry_lines': ('entry_id', 'journal_entries'),
    'invoice_items': ('invoice_id', 'invoices'),
    'customer_invoice_items': ('customer_invoice_id', 'customer_invoices'),
    'purchase_invoice_items': ('purchase_invoice_id', 'purchase_invoices'),
}
OPENINGS = {
    'chart_of_accounts': ('opening_balance', 'normal_balance', 'account_type', 'account_group', 'code', 'is_active'),
    'clients': ('opening_balance', 'statement_cutoff'),
    'suppliers': ('opening_balance', 'statement_cutoff'),
    'bank_accounts': ('opening_balance',),
}
PROTECTED = set(DATED) | set(CHILDREN) | set(OPENINGS) | {'statement_closings'}


def setup_period_control(engine, company):
    """Additive setup, called before a company's first session is returned."""
    Control.__table__.create(engine, checkfirst=True)
    Audit.__table__.create(engine, checkfirst=True)
    try:
        with engine.begin() as conn:
            if conn.execute(select(Control.company_id).where(Control.company_id == company)).first() is None:
                conn.execute(Control.__table__.insert().values(company_id=company, version=0))
    except IntegrityError:
        # Another worker may have initialised the same control concurrently.
        with engine.connect() as conn:
            if conn.execute(select(Control.company_id).where(Control.company_id == company)).first() is None:
                raise


def locked_control(db):
    company = db.info.get('finance_period_company')
    if not company:
        return None
    # The same row serialises close/reopen and financial writes until commit.
    row = db.connection().execute(select(Control.__table__).where(
        Control.company_id == company).with_for_update()).mappings().first()
    if row is None:
        raise ClosedPeriodError('Financial period setup is missing. Reload the company before saving.')
    return row


def saved_row(db, obj):
    state = inspect(obj)
    if not state.identity:
        return None
    table = state.mapper.local_table
    condition = [col == value for col, value in zip(table.primary_key, state.identity)]
    return db.connection().execute(select(table).where(*condition).with_for_update()).mappings().first()


def check_date(value, cutoff):
    if isinstance(value, datetime):
        value = value.date()
    if value is not None and value <= cutoff:
        raise ClosedPeriodError(f'Financial records dated on or before {cutoff} are closed. An owner must reopen the period before this change.')


@event.listens_for(Session, 'before_flush')
def guard_financial_flush(db, context, instances):
    if not db.info.get('finance_period_company'):
        return
    changed = [obj for obj in set(db.new) | set(db.dirty) | set(db.deleted)
               if obj in db.new or obj in db.deleted or db.is_modified(obj, include_collections=False)]
    financial = [obj for obj in changed if obj.__table__.name in PROTECTED]
    controls = [obj for obj in changed if isinstance(obj, (Control, Audit))]
    if controls:
        raise ClosedPeriodError('Period controls and history can only be changed through the period management action.')
    if not financial:
        return
    control = locked_control(db)
    cutoff = control['closed_through']
    for obj in financial:
        old = saved_row(db, obj)
        company = getattr(obj, 'company_id', None)
        if company is not None and company != control['company_id'] or old and old.get('company_id', company) != control['company_id']:
            raise ClosedPeriodError('Financial changes must belong to the selected company.')
        if not cutoff:
            continue
        name = obj.__table__.name
        if name in DATED:
            field = DATED[name]
            check_date(old[field] if old else None, cutoff)
            check_date(getattr(obj, field, None) or (date.today() if obj in db.new else None), cutoff)
        elif name in CHILDREN:
            field, parent_name = CHILDREN[name]
            parent_table = models.customer_db.metadata.tables[parent_name]
            parent_ids = {getattr(obj, field, None)}
            if old:
                parent_ids.add(old[field])
            # New parent/child graphs may not have database IDs until flush.
            for relation in inspect(obj).mapper.relationships:
                if relation.mapper.local_table.name == parent_name and not relation.uselist:
                    parent = getattr(obj, relation.key)
                    if parent is not None:
                        check_date(getattr(parent, DATED[parent_name], None) or date.today(), cutoff)
            for pk in parent_ids - {None}:
                parent = db.connection().execute(select(parent_table).where(parent_table.c.id == pk).with_for_update()).mappings().first()
                if parent is None or parent.get('company_id') != control['company_id']:
                    raise ClosedPeriodError('Financial line has a missing or wrong-company parent.')
                check_date(parent[DATED[parent_name]], cutoff)
        elif name in OPENINGS:
            if obj in db.deleted or any(
                    (old and old[field] != getattr(obj, field)) or
                    (not old and field == 'opening_balance' and getattr(obj, field, 0))
                    for field in OPENINGS[name]):
                raise ClosedPeriodError('Opening balances and accounting classifications cannot change while a period is closed. Reopen first.')
        else:
            raise ClosedPeriodError('Statement closing changes require the financial period to be reopened first.')


@event.listens_for(Session, 'do_orm_execute')
def guard_bulk_financial_write(state):
    db = state.session
    if not db.info.get('finance_period_company'):
        return
    statement = state.statement
    if isinstance(statement, TextClause):
        # Raw SELECTs used by existing read paths are allowed. Other text can
        # bypass date validation (including comments/CTEs), so fail conservatively.
        first = statement.text.lstrip().split(None, 1)[0].upper() if statement.text.strip() else ''
        mutating = first not in ('SELECT', 'SHOW', 'DESCRIBE', 'EXPLAIN')
        protected = True
    else:
        mutating = state.is_insert or state.is_update or state.is_delete
        protected = getattr(getattr(statement, 'table', None), 'name', '') in PROTECTED | {Control.__tablename__, Audit.__tablename__}
    if mutating and protected:
        control = locked_control(db)
        if isinstance(statement, TextClause) and any(name in statement.text.lower() for name in (Control.__tablename__, Audit.__tablename__)):
            raise ClosedPeriodError('Period controls must be changed through period management.')
        if getattr(getattr(statement, 'table', None), 'name', '') in {Control.__tablename__, Audit.__tablename__}:
            raise ClosedPeriodError('Period controls must be changed through period management.')
        if control['closed_through']:
            raise ClosedPeriodError('Bulk or raw changes cannot be date-checked while a financial period is closed. Reopen the period first.')


def change_period(db, company, action, cutoff, version, reason, actor, today):
    control = locked_control(db)
    if control is None or control['company_id'] != company:
        raise ClosedPeriodError('Select the correct company before changing periods.')
    if control['version'] != version:
        raise ValueError('Period status changed. Refresh this page and review the latest status.')
    if not reason.strip() or len(reason) > 1000:
        raise ValueError('Enter a reason of 1 to 1,000 characters.')
    previous = control['closed_through']
    if action == 'close':
        if cutoff is None or cutoff >= today or previous and cutoff <= previous:
            raise ValueError('Choose a past date later than the current closed-through date.')
        # Fail close on draft or structurally unbalanced journals in the period.
        J, L = models.JournalEntry, models.JournalEntryLine
        journals = db.query(J).filter(J.company_id == company, J.entry_date <= cutoff).populate_existing().with_for_update().all()
        accounts = {a.id: a for a in db.query(models.ChartOfAccount).filter_by(company_id=company).populate_existing().with_for_update()}
        if any(a.normal_balance not in ('Debit', 'Credit') or (a.opening_balance and not a.is_active) for a in accounts.values()):
            raise ValueError('Resolve invalid or inactive opening accounts before closing.')
        opening_difference = sum((a.opening_balance or 0) * (1 if a.normal_balance == 'Debit' else -1) for a in accounts.values())
        if opening_difference:
            raise ValueError('Resolve unbalanced account openings before closing.')
        for entry in journals:
            if entry.status not in ('Posted', 'Reversed'):
                raise ValueError('Resolve draft or unknown-status journals before closing.')
            lines = db.query(L).filter_by(entry_id=entry.id).populate_existing().with_for_update().all()
            if len(lines) < 2 or sum(x.debit for x in lines) <= 0 or sum(x.debit for x in lines) != sum(x.credit for x in lines):
                raise ValueError('Resolve unbalanced journals before closing.')
            if any(x.debit < 0 or x.credit < 0 or (x.debit > 0) == (x.credit > 0) or
                   x.account_id not in accounts for x in lines):
                raise ValueError('Resolve invalid journal lines before closing.')
    elif action == 'reopen':
        if previous is None:
            raise ValueError('There is no closed period to reopen.')
        cutoff = None
    else:
        raise ValueError('Unknown period action.')
    conn = db.connection()
    conn.execute(Control.__table__.update().where(Control.company_id == company).values(
        closed_through=cutoff, version=version+1))
    conn.execute(Audit.__table__.insert().values(company_id=company, action=action,
        previous_date=previous, new_date=cutoff, reason=reason.strip(), actor=actor,
        changed_at=datetime.utcnow(), version=version+1))
    db.commit()


def register_finance_periods(app, login_required, owner_required, require_permission,
                            get_db, get_company, get_user, today):
    @app.errorhandler(ClosedPeriodError)
    def closed_period(error):
        get_db().rollback()
        return render_template('finance_period_blocked.html', message=str(error)), 409

    @app.route('/finance/periods')
    @login_required
    @require_permission('finance', 'view')
    def finance_periods():
        company = get_company()
        if not company:
            abort(403)
        db = get_db()
        control = db.query(Control).filter_by(company_id=company).one()
        history = db.query(Audit).filter_by(company_id=company).order_by(Audit.id.desc()).limit(100).all()
        token = session.setdefault('finance_period_csrf', secrets.token_urlsafe(32))
        user = get_user() or {}
        return render_template('finance_periods.html', control=control, history=history, token=token,
                               can_manage=user.get('role') in ('owner', 'super_admin'), today=today())

    @app.route('/finance/periods/change', methods=['POST'])
    @login_required
    @owner_required
    @require_permission('finance', 'edit')
    def finance_period_change():
        if not hmac.compare_digest(request.form.get('token', ''), session.get('finance_period_csrf') or secrets.token_urlsafe(32)):
            abort(403)
        company = get_company()
        if not company:
            abort(403)
        if request.form.get('company_id') != str(company):
            abort(400, description='Company selection changed. Refresh Financial Periods before submitting.')
        db = get_db()
        try:
            if request.form.get('reviewed') != 'yes':
                raise ValueError('Review Accounting Checks and acknowledge the closing restrictions first.')
            user = get_user() or {}
            cutoff = date.fromisoformat(request.form['cutoff']) if request.form.get('cutoff') else None
            change_period(db, company, request.form.get('action'), cutoff, int(request.form.get('version', '-1')),
                          request.form.get('reason', ''), str(user.get('email') or user.get('user_id') or 'Owner'), today())
            flash('Financial period updated and recorded in the audit history.', 'success')
        except ValueError as error:
            db.rollback()
            flash(str(error), 'error')
        return redirect(url_for('finance_periods'))

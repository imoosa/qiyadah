"""Read-only accounting readiness checks. Never backfill or repair automatically."""
from collections import Counter, defaultdict
from decimal import Decimal

from flask import abort, render_template, request, url_for
from sqlalchemy import inspect

from customer_models import ChartOfAccount, JournalEntry, JournalEntryLine, CustomerInvoice, PurchaseInvoice
from finance_reconciliation import reconciliation_checks
from finance_party_checks import party_checks
from finance_payment_checks import payment_checks


def accounting_checks(db, company_id, can):
    issues = []
    counts = Counter()
    checked = Counter()

    def add(code, reference, detail, endpoint=None, args=None):
        counts[code] += 1
        issues.append(dict(code=code, reference=reference, detail=detail,
                           endpoint=endpoint, args=args or {}))

    tables = set(inspect(db.get_bind()).get_table_names())
    required = {m.__tablename__ for m in (ChartOfAccount, JournalEntry, JournalEntryLine)}
    if not required.issubset(tables):
        add('Setup required', 'Accounting', 'Accounting tables are not available. Complete accounting setup before running these checks.')
        return dict(issues=issues, counts=counts, checked=checked, complete=False)

    accounts = {a.id: a for a in db.query(ChartOfAccount).filter_by(company_id=company_id)}
    entries = db.query(JournalEntry).filter_by(company_id=company_id).order_by(JournalEntry.id).all()
    lines = defaultdict(list)
    for line in db.query(JournalEntryLine).join(JournalEntry).filter(JournalEntry.company_id == company_id):
        lines[line.entry_id].append(line)
    active = defaultdict(list)
    totals = {}
    for entry in entries:
        checked['journals'] += 1
        if entry.status == 'Draft':
            add('Draft journal', entry.entry_no, 'Review and post this draft when approved.', 'journal_entry_view', {'entry_id': entry.id})
            continue
        if entry.status not in ('Posted', 'Reversed'):
            add('Journal status', entry.entry_no, 'Unrecognised journal status.', 'journal_entry_view', {'entry_id': entry.id})
            continue
        rows = lines[entry.id]
        debit = sum((Decimal(str(row.debit or 0)) for row in rows), Decimal(0))
        credit = sum((Decimal(str(row.credit or 0)) for row in rows), Decimal(0))
        totals[entry.id] = debit
        if len(rows) < 2 or debit <= 0 or debit != credit:
            add('Unbalanced journal', entry.entry_no, 'Posted journal must contain at least two lines with equal, positive debit and credit totals.', 'journal_entry_view', {'entry_id': entry.id})
        if any(row.debit < 0 or row.credit < 0 or (row.debit > 0) == (row.credit > 0) for row in rows):
            add('Invalid journal line', entry.entry_no, 'Each line must have one positive debit or credit, without negative amounts.', 'journal_entry_view', {'entry_id': entry.id})
        if any(row.account_id not in accounts for row in rows):
            add('Invalid account', entry.entry_no, 'A line has no account belonging to this company.', 'journal_entry_view', {'entry_id': entry.id})
        if entry.status == 'Posted' and entry.source_id and entry.source_type != 'reversal':
            active[(entry.source_type, entry.source_id)].append(entry)
    for group in active.values():
        if len(group) > 1:
            add('Duplicate posting', group[0].entry_no, 'More than one active journal refers to the same source. Review before making corrections.', 'journal_entry_view', {'entry_id': group[0].id})

    sources = [(CustomerInvoice, 'invoices', 'sales_invoice'), (PurchaseInvoice, 'purchase', 'purchase_invoice')]
    complete = True
    for model, permission, default_type in sources:
        if model is CustomerInvoice:
            allowed = can('invoices', 'view') or can('customer_invoices', 'view')
        else:
            allowed = can(permission, 'view')
        if not allowed:
            continue
        if model.__tablename__ not in tables:
            complete = False
            add('Setup required', 'Invoices', 'An authorised invoice table is unavailable; invoice coverage is incomplete.')
            continue
        for invoice in db.query(model).filter_by(company_id=company_id).order_by(model.id):
            kind = default_type
            if model is CustomerInvoice:
                repair = invoice.invoice_category == 'workshop_repair'
                if not can('customer_invoices' if repair else 'invoices', 'view'):
                    continue
                kind = 'repair_bill' if repair else 'sales_invoice'
                reference = invoice.invoice_number
                endpoint, args = 'customer_invoice_view', {'cust_inv_id': invoice.id}
                # Repair documents use a separate permission and destination.
                if repair:
                    endpoint, args = 'repair_bills_view', {'q': reference}
            else:
                reference = invoice.invoice_id
                endpoint, args = 'purchase_invoice_view', {'invoice_id': invoice.invoice_id}
            checked['invoices'] += 1
            journals = active.get((kind, str(invoice.id)), [])
            if model is CustomerInvoice:
                checked['sales_invoices'] += 1
                if journals:
                    checked['sales_posted'] += 1
                else:
                    checked['sales_unposted'] += 1
            else:
                checked['purchase_invoices'] += 1
                if journals:
                    checked['purchase_posted'] += 1
                else:
                    checked['purchase_unposted'] += 1

            excluded = (invoice.status or '').strip().lower() in ('draft', 'void', 'cancelled', 'canceled')
            if excluded:
                if journals:
                    add('Inactive invoice posted', reference, 'A draft or cancelled invoice still has an active journal.', endpoint, args)
                continue
            # Compare the original invoice total, before separately posted notes/receipts.
            expected = Decimal(str(invoice.base_grand_total or 0))
            if expected == 0:
                expected = Decimal(str(invoice.grand_total or 0)) * Decimal(str(invoice.exchange_rate or 1))
            expected = expected.quantize(Decimal('0.01'))
            if expected == 0:
                continue
            if not journals:
                add('Missing invoice posting', reference, 'No active journal was found for this invoice. Review historical coverage before posting.', endpoint, args)
            elif len(journals) == 1 and totals[journals[0].id] != expected:
                add('Invoice total mismatch', reference, 'The journal debit total differs from the invoice total in base currency.', endpoint, args)
    reconciliation_complete = reconciliation_checks(
        db, company_id, can, tables, accounts, entries, lines, add, checked)
    parties_complete = party_checks(db, company_id, can, tables, add, checked)
    payment_checks(db, company_id, can, tables, add, checked)
    return dict(issues=issues, counts=counts, checked=checked, complete=complete and reconciliation_complete and parties_complete)


def register_finance_checks(app, login_required, require_permission, get_db, get_company, can,
                            post_customer_invoice=None, post_purchase_invoice=None):
    @app.route('/finance/accounting-checks')
    @login_required
    @require_permission('finance', 'view')
    def finance_checks():
        company = get_company()
        if not company:
            abort(403)
        # Prevent pending ORM objects from being flushed by this diagnostic page.
        db = get_db()
        with db.no_autoflush:
            report = accounting_checks(db, company, can)
        selected = request.args.get('check', '')
        if selected and selected not in report['counts']:
            abort(400, description='Unknown accounting check.')
        issues = [i for i in report['issues'] if not selected or i['code'] == selected]
        page = max(1, request.args.get('page', 1, type=int))
        page = min(page, max(1, (len(issues) + 49) // 50))
        rows = issues[(page-1)*50:page*50]
        for row in rows:
            row['href'] = url_for(row['endpoint'], **row['args']) if row['endpoint'] else None
        return render_template('finance_checks.html', report=report, rows=rows, selected=selected,
                               page=page, pages=max(1, (len(issues)+49)//50), total=len(issues))

    @app.route('/finance/accounting-checks/post-all', methods=['POST'])
    @login_required
    @require_permission('finance', 'view')
    def finance_checks_post_all():
        company = get_company()
        if not company:
            abort(403)
        db = get_db()
        posted_count = 0
        if post_customer_invoice:
            for inv in db.query(CustomerInvoice).filter_by(company_id=company).all():
                if (inv.status or '').strip().lower() not in ('draft', 'void', 'cancelled', 'canceled'):
                    entry = post_customer_invoice(db, company, inv)
                    if entry:
                        posted_count += 1
        if post_purchase_invoice:
            for inv in db.query(PurchaseInvoice).filter_by(company_id=company).all():
                if (inv.status or '').strip().lower() not in ('draft', 'void', 'cancelled', 'canceled'):
                    entry = post_purchase_invoice(db, company, inv)
                    if entry:
                        posted_count += 1
        db.commit()
        from flask import flash, redirect, url_for
        flash(f"✅ Successfully posted {posted_count} invoices into General Ledger journals!", "success")
        return redirect(url_for('finance_checks'))

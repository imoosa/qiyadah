"""Invoice adjustments and their accounting entries."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

from flask import abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import event, func
from sqlalchemy.orm import Session
from customer_models import CustomerInvoice, PurchaseInvoice, FinanceNote


def money(value):
    try:
        result = Decimal(str(value or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if not result.is_finite() or abs(result) >= Decimal('1000000000000'):
            raise ValueError()
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Enter a valid amount.') from None


def update_balance(invoice):
    balance = max(Decimal(0), money(invoice.grand_total) - money(invoice.paid_amount) - money(invoice.note_adjustment))
    invoice.balance = float(balance)
    invoice.status = 'Paid' if balance == 0 else 'Partial' if money(invoice.paid_amount) else 'Pending'
    if isinstance(invoice, PurchaseInvoice):
        invoice.base_balance = float(money(balance * Decimal(str(invoice.exchange_rate or 1))))


@event.listens_for(Session, 'before_flush')
def preserve_note_balances(db, flush_context, instances):
    # Payment and edit routes historically recompute balance as total minus paid.
    # Keep posted adjustments effective when those routes subsequently save.
    for invoice in db.dirty:
        if isinstance(invoice, (CustomerInvoice, PurchaseInvoice)) and invoice.note_adjustment:
            if (invoice.status or '').lower() not in ('void', 'cancelled', 'draft'):
                update_balance(invoice)


def note_journal_rows(note, invoice):
    rate = Decimal(str(note.exchange_rate))
    subtotal, tax = money(note.subtotal * rate), money(note.tax_amount * rate)
    total = subtotal + tax
    if note.kind == 'credit':
        revenue = '4200' if invoice.invoice_category == 'workshop_repair' else '4100'
        return [(revenue, subtotal, 0, note.reason[:250]), ('2200', tax, 0, 'Output tax adjustment'),
                ('1300', 0, total, 'Customer credit note')]
    return [('2100', total, 0, 'Supplier debit note'), ('5100', 0, subtotal, note.reason[:250]),
            ('1500', 0, tax, 'Input tax adjustment')]


def note_statement_events(db, company, kind, party_id, since=None, until=None):
    """Keep note and reversal dates visible in party statements."""
    events = []
    for note in db.query(FinanceNote).filter_by(company_id=company, kind=kind, party_id=party_id):
        dates = [(note.note_date, False)]
        if note.status == 'Void' and note.voided_at:
            dates.append((note.voided_at.date(), True))
        for event_date, reversal in dates:
            if (since and event_date < since) or (until and event_date >= until):
                continue
            debit = (kind == 'debit') != reversal
            events.append(dict(date=event_date, type=f'{kind.title()} Note' + (' Reversal' if reversal else ''),
                ref=note.number, debit=float(note.total) if debit else 0, credit=0 if debit else float(note.total),
                status=note.status, payment_mode='', id=None, inv_id=None, awb='', consignor='', consignee='',
                destination='', carrier_ref='', carrier='', chrg_wt=0, act_wt=0, vol_wt=0, grand_total=0,
                other_charges=0, billing_amount=0, per_kg=0, _sort=1))
    return events


def register_finance_notes(app, login_required, require_permission, get_cdb, get_company,
                           can, post_journal, reverse_journal, prepare_accounting=lambda db, company: None):
    def context(kind, action='view'):
        if kind not in ('credit', 'debit'):
            abort(404)
        if not can('customer_invoices' if kind == 'credit' else 'purchase', action):
            abort(403)
        company = get_company()
        if not company:
            abort(403)
        return get_cdb(), company, CustomerInvoice if kind == 'credit' else PurchaseInvoice

    def invoice_link(kind, invoice):
        return url_for('customer_invoice_view', cust_inv_id=invoice.id) if kind == 'credit' else url_for('purchase_invoice_view', invoice_id=invoice.invoice_id)

    @app.route('/finance/<kind>-notes')
    @login_required
    @require_permission('finance', 'view')
    def finance_note_list(kind):
        db, company, model = context(kind)
        query = db.query(FinanceNote).filter_by(company_id=company, kind=kind)
        search = request.args.get('q', '').strip()
        if search:
            query = query.filter((FinanceNote.number.ilike(f'%{search}%')) | (FinanceNote.party_name.ilike(f'%{search}%')) | (FinanceNote.invoice_reference.ilike(f'%{search}%')))
        status = request.args.get('status', '')
        if status in ('Posted', 'Void'):
            query = query.filter_by(status=status)
        return render_template('finance_notes.html', kind=kind, notes=query.order_by(FinanceNote.id.desc()).all(),
                               can_create=can('finance', 'create') and can('customer_invoices' if kind == 'credit' else 'purchase', 'create'))

    @app.route('/finance/<kind>-notes/new', methods=['GET', 'POST'])
    @login_required
    @require_permission('finance', 'create')
    def finance_note_new(kind):
        db, company, model = context(kind, 'create')
        if request.method == 'POST':
            # Existing account seeding can commit; complete it before changing notes.
            prepare_accounting(db, company)
            try:
                invoice = db.query(model).filter_by(id=request.form.get('invoice_id', type=int), company_id=company).with_for_update().populate_existing().first()
                if invoice is None:
                    abort(404)
                token = request.form.get('request_token', '')
                if len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
                    raise ValueError('Reload the form and try again.')
                existing = db.query(FinanceNote).filter_by(company_id=company, request_token=token).first()
                if existing:
                    return redirect(url_for('finance_note_view', kind=existing.kind, note_id=existing.id))
                if (invoice.status or '').lower() in ('draft', 'void', 'cancelled', 'canceled'):
                    raise ValueError('Choose an active invoice.')
                subtotal, tax = money(request.form.get('subtotal')), money(request.form.get('tax_amount'))
                total = subtotal + tax
                if subtotal < 0 or tax < 0 or total <= 0:
                    raise ValueError('Amounts must be positive, with tax zero or greater.')
                outstanding = money(invoice.grand_total) - money(invoice.paid_amount) - money(invoice.note_adjustment)
                if total > outstanding:
                    raise ValueError('The note cannot exceed the invoice outstanding balance.')
                previous = db.query(func.coalesce(func.sum(FinanceNote.subtotal), 0), func.coalesce(func.sum(FinanceNote.tax_amount), 0)).filter_by(company_id=company, kind=kind, invoice_id=invoice.id, status='Posted').one()
                if subtotal + money(previous[0]) > money(invoice.subtotal) or tax + money(previous[1]) > money(invoice.tax_amount):
                    raise ValueError('The taxable amount or tax exceeds the remaining invoice amount.')
                reason = request.form.get('reason', '').strip()
                if not reason or len(reason) > 2000:
                    raise ValueError('Enter a reason of up to 2,000 characters.')
                note_date = date.fromisoformat(request.form.get('note_date', ''))
                original_date = invoice.invoice_date if kind == 'credit' else invoice.date
                if note_date < original_date or note_date > date.today():
                    raise ValueError('Note date must be between the invoice date and today.')
                rate = Decimal(str(invoice.exchange_rate or 1))
                if not rate.is_finite() or rate <= 0:
                    raise ValueError('Correct the invoice exchange rate first.')
                note = FinanceNote(company_id=company, kind=kind, number=f"{'CN' if kind == 'credit' else 'DN'}-{uuid4().hex[:12].upper()}",
                    request_token=token, invoice_id=invoice.id, invoice_reference=invoice.invoice_number if kind == 'credit' else (invoice.invoice_number or invoice.invoice_id),
                    party_id=invoice.client_id if kind == 'credit' else invoice.supplier_id,
                    party_name=(invoice.client_name if kind == 'credit' else invoice.supplier_name) or 'Unassigned',
                    note_date=note_date, currency=invoice.currency, exchange_rate=rate, subtotal=subtotal, tax_amount=tax, total=total,
                    reason=reason, status='Posted', created_by=(session.get('user') or {}).get('email', 'System'))
                db.add(note)
                db.flush()
                invoice.note_adjustment = float(money(invoice.note_adjustment) + total)
                update_balance(invoice)
                post_journal(db, company, note_date, f'{kind.title()} note {note.number}', f'{kind}_note', note.id, note.number, note_journal_rows(note, invoice))
                db.commit()
                flash(f'{kind.title()} note {note.number} posted to accounts.', 'success')
                return redirect(url_for('finance_note_view', kind=kind, note_id=note.id))
            except ValueError as error:
                db.rollback()
                flash(str(error), 'error')
            except Exception:
                db.rollback()
                raise
        invoices = db.query(model).filter(model.company_id == company, func.lower(model.status).notin_(['draft', 'void', 'cancelled', 'canceled']),
                     model.grand_total - model.paid_amount - model.note_adjustment > 0).order_by(model.id.desc()).all()
        return render_template('finance_note_form.html', kind=kind, invoices=invoices, today=date.today(), token=uuid4().hex)

    @app.route('/finance/<kind>-notes/<int:note_id>')
    @login_required
    @require_permission('finance', 'view')
    def finance_note_view(kind, note_id):
        db, company, model = context(kind)
        note = db.query(FinanceNote).filter_by(id=note_id, kind=kind, company_id=company).first()
        if note is None:
            abort(404)
        invoice = db.query(model).filter_by(id=note.invoice_id, company_id=company).first()
        return render_template('finance_note_view.html', kind=kind, note=note, invoice=invoice,
                               invoice_url=invoice_link(kind, invoice) if invoice else None,
                               can_void=can('finance', 'edit') and can('customer_invoices' if kind == 'credit' else 'purchase', 'edit'))

    @app.route('/finance/<kind>-notes/<int:note_id>/void', methods=['POST'])
    @login_required
    @require_permission('finance', 'edit')
    def finance_note_void(kind, note_id):
        db, company, model = context(kind, 'edit')
        prepare_accounting(db, company)
        note = db.query(FinanceNote).filter_by(id=note_id, kind=kind, company_id=company).with_for_update().first()
        if note is None:
            abort(404)
        if note.status != 'Void':
            reason = request.form.get('reason', '').strip()
            if not reason or len(reason) > 2000:
                flash('Enter a cancellation reason of up to 2,000 characters.', 'error')
                return redirect(url_for('finance_note_view', kind=kind, note_id=note.id))
            invoice = db.query(model).filter_by(id=note.invoice_id, company_id=company).with_for_update().populate_existing().first()
            if invoice is None:
                abort(409, description='The linked invoice no longer exists.')
            try:
                reverse_journal(db, company, f'{kind}_note', note.id, reason)
                note.status, note.void_reason = 'Void', reason
                note.voided_at = datetime.utcnow()
                note.voided_by = (session.get('user') or {}).get('email', 'System')
                invoice.note_adjustment = float(max(Decimal(0), money(invoice.note_adjustment) - note.total))
                update_balance(invoice)
                db.commit()
                flash('Note cancelled and accounting entry reversed.', 'success')
            except Exception:
                db.rollback()
                raise
        return redirect(url_for('finance_note_view', kind=kind, note_id=note.id))

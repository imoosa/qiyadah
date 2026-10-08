"""Read-only financial projections over existing operational records.

Current balances are deliberately not reconstructed as historical balances.
No journals, payment copies, source mutations or cross-currency totals.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func

from customer_models import (CustomerInvoice, PurchaseInvoice, WorkshopJobCard, FinanceNote,
                             CashTransaction, BankAccount, Expense)

ZERO = Decimal('0')
BUCKETS = ('Not due', '1–30 days', '31–60 days', '61–90 days', '90+ days', 'No due date')
EXCLUDED = ('draft', 'void', 'cancelled', 'canceled')


def money(value):
    return Decimal(str(value or 0))


def parse_filters(args, today, company_id, company=None):
    if args.get('company', company_id) != company_id:
        raise ValueError('Switch company using the authorised company selector.')
    if args.get('branch', 'all') != 'all':
        raise ValueError('Branch reporting is not available across the existing financial records.')

    from tax_service import tax_profile
    if company is None:
        try:
            from platform_models import Company
            company = Company.query.filter_by(company_id=company_id).first()
        except Exception:
            company = None

    profile = tax_profile(company)
    is_calendar_year = (profile.get('country') != 'India')

    if is_calendar_year:
        default_year = today.year
    else:
        default_year = today.year if today.month >= 4 else today.year - 1

    try:
        year = int(args.get('fy', default_year))
        if not 1900 <= year <= 9998:
            raise ValueError()
        if args.get('from_date'):
            start = date.fromisoformat(args['from_date'])
        else:
            start = date(year, 1, 1) if is_calendar_year else date(year, 4, 1)

        if args.get('to_date'):
            end = date.fromisoformat(args['to_date'])
        else:
            end = min(today, date(year, 12, 31) if is_calendar_year else date(year + 1, 3, 31))
    except (ValueError, TypeError):
        raise ValueError('Enter a valid financial year and dates.') from None
    if start > end:
        raise ValueError('From date must be on or before To date.')
    if (end - start).days > 366 * 5:
        raise ValueError('Choose a date range of five years or less.')
    return dict(fy=year, start=start, end=end, today=today, company_id=company_id,
                is_calendar_year=is_calendar_year,
                tax_profile=profile,
                tax_label=profile.get('label', 'Tax'),
                tax_id_label=profile.get('id_label', 'Tax ID'),
                is_vat=profile.get('is_vat', False),
                is_gst=profile.get('is_gst', False),
                regime=profile.get('regime', 'NONE'),
                years=sorted(set(range(default_year - 5, default_year + 2)) | {year}, reverse=True))


def ageing_bucket(due, today):
    if due is None:
        return 'No due date'
    days = (today - due).days
    if days <= 0:
        return 'Not due'
    return '1–30 days' if days <= 30 else '31–60 days' if days <= 60 else '61–90 days' if days <= 90 else '90+ days'


def totals(rows, field):
    result = defaultdict(lambda: ZERO)
    for row in rows:
        result[row['currency']] += row[field]
    return dict(sorted(result.items()))


def source_documents(cdb, company_id, can):
    """Read each canonical invoice once; legacy bookings are not extra sales."""
    rows = []
    if can('invoices', 'view') or can('customer_invoices', 'view'):
        job_links = dict(cdb.query(WorkshopJobCard.invoice_id, func.min(WorkshopJobCard.id)).filter(
            WorkshopJobCard.company_id == company_id, WorkshopJobCard.invoice_id.isnot(None)
        ).group_by(WorkshopJobCard.invoice_id).all())
        for inv in cdb.query(CustomerInvoice).filter(CustomerInvoice.company_id == company_id,
                func.lower(func.trim(CustomerInvoice.status)).notin_(EXCLUDED)).all():
            repair = inv.invoice_category == 'workshop_repair' or inv.id in job_links
            if not can('customer_invoices' if repair else 'invoices', 'view'):
                continue
            rows.append(dict(kind='repair' if repair else 'sales', id=inv.id,
                reference=inv.invoice_number, party=inv.client_name or 'Unassigned customer',
                party_id=inv.client_id, date=inv.invoice_date, due=inv.due_date,
                currency=inv.currency or 'Unspecified', subtotal=money(inv.subtotal),
                tax=money(inv.tax_amount), total=money(inv.grand_total),
                balance=money(inv.balance if inv.balance is not None else money(inv.grand_total)-money(inv.paid_amount)),
                job_id=job_links.get(inv.id)))
    if can('purchase', 'view'):
        for inv in cdb.query(PurchaseInvoice).filter(PurchaseInvoice.company_id == company_id,
                func.lower(func.trim(PurchaseInvoice.status)).notin_(EXCLUDED)).all():
            rows.append(dict(kind='purchase', id=inv.id, reference=inv.invoice_id,
                party=inv.supplier_name or 'Unassigned supplier', party_id=inv.supplier_id,
                date=inv.date, due=inv.due_date, currency=inv.currency or 'Unspecified',
                subtotal=money(inv.subtotal), tax=money(inv.tax_amount), total=money(inv.grand_total),
                balance=money(inv.balance if inv.balance is not None else money(inv.grand_total)-money(inv.paid_amount))))
    # Notes are dated adjustments, not payments or replacements for invoice totals.
    invoice_rows = {(row['kind'], row['id']): row for row in rows}
    for note in cdb.query(FinanceNote).filter_by(company_id=company_id):
        original = (invoice_rows.get(('purchase', note.invoice_id)) if note.kind == 'debit' else
                    invoice_rows.get(('sales', note.invoice_id)) or invoice_rows.get(('repair', note.invoice_id)))
        if not original:
            continue
        adjustments = [(note.note_date, -1)]
        if note.status == 'Void' and note.voided_at:
            adjustments.append((note.voided_at.date(), 1))
        for note_date, sign in adjustments:
            rows.append(dict(original, reference=note.number + (' (reversal)' if sign == 1 else ''),
                             date=note_date, due=None, subtotal=money(note.subtotal)*sign,
                             tax=money(note.tax_amount)*sign, total=money(note.total)*sign, balance=ZERO,
                             note_id=note.id, note_kind=note.kind))
    return rows


def open_summary(rows, today):
    opened = [r for r in rows if r['balance'] > 0]
    overdue = [r for r in opened if r['due'] and r['due'] < today]
    soon = sorted((r for r in opened if r['due'] and today <= r['due'] <= today + timedelta(days=7)),
                  key=lambda r: (r['due'], r['reference']))
    buckets = {b: totals([r for r in opened if ageing_bucket(r['due'], today) == b], 'balance') for b in BUCKETS}
    parties = {}
    for row in opened:
        key = (row['party_id'] if row['party_id'] is not None else ('document', row['kind'], row['id']), row['currency'])
        item = parties.setdefault(key, dict(name=row['party'], currency=row['currency'], amount=ZERO))
        item['amount'] += row['balance']
    # Rank within currency, never compare amounts expressed in different units.
    top = []
    for currency in sorted({p['currency'] for p in parties.values()}):
        top.extend(sorted((p for p in parties.values() if p['currency'] == currency),
                          key=lambda p: p['amount'], reverse=True)[:5])
    return dict(total=totals(opened, 'balance'), overdue=totals(overdue, 'balance'),
                overdue_count=len(overdue), soon=soon[:8], soon_count=len(soon),
                buckets=buckets, top=top, count=len(opened))


def dashboard_data(cdb, company_id, can, filters, base_currency='INR'):
    documents = source_documents(cdb, company_id, can)
    today, start, end = filters['today'], filters['start'], filters['end']
    # Current outstanding excludes future-dated documents, but is not an as-at ledger.
    current = [r for r in documents if r['date'] <= today]
    period = [r for r in documents if start <= r['date'] <= end]
    sales = [r for r in period if r['kind'] != 'purchase']
    purchases = [r for r in period if r['kind'] == 'purchase']
    receivables = open_summary([r for r in current if r['kind'] != 'purchase'], today)
    payables = open_summary([r for r in current if r['kind'] == 'purchase'], today)
    expenses = []
    if can('expenses', 'view'):
        expenses = [dict(date=e.date, amount=money(e.amount), id=e.id, description=e.description or e.category)
                    for e in cdb.query(Expense).filter(Expense.company_id == company_id,
                        Expense.date >= start, Expense.date <= end).all()]
    cash = None
    if can('cash', 'view'):
        cash = ZERO
        for kind, amount in cdb.query(CashTransaction.type, func.sum(CashTransaction.amount)).filter(
                CashTransaction.company_id == company_id).group_by(CashTransaction.type).all():
            if kind == 'income':
                cash += money(amount)
            elif kind == 'expense':
                cash -= money(amount)
    banks = []
    if can('bank', 'view'):
        banks = [dict(id=b.id, name=b.bank_name, account=b.account_name, balance=money(b.balance))
                 for b in cdb.query(BankAccount).filter_by(company_id=company_id, status='Active').order_by(BankAccount.bank_name).all()]
    bank_total = sum((b['balance'] for b in banks), ZERO) if can('bank', 'view') else None
    input_tax, output_tax = totals(purchases, 'tax'), totals(sales, 'tax')
    tax_difference = {c: output_tax.get(c, ZERO)-input_tax.get(c, ZERO) for c in sorted(set(input_tax) | set(output_tax))}
    months = {}
    month = start.replace(day=1)
    while month <= end:
        months[month.strftime('%Y-%m')] = dict(label=month.strftime('%b %Y'), revenue=ZERO, expenses=ZERO)
        month = date(month.year+1, 1, 1) if month.month == 12 else date(month.year, month.month+1, 1)
    for row in sales:
        if row['currency'] == base_currency:
            months[row['date'].strftime('%Y-%m')]['revenue'] += row['subtotal']
    for row in expenses:
        months[row['date'].strftime('%Y-%m')]['expenses'] += row['amount']
    peak = max([abs(v) for m in months.values() for v in (m['revenue'], m['expenses'])] or [ZERO])
    for month in months.values():
        month['revenue_width'] = float(abs(month['revenue']) / peak * 100) if peak else 0
        month['expense_width'] = float(abs(month['expenses']) / peak * 100) if peak else 0
    return dict(documents=documents, receivables=receivables, payables=payables,
                sales=totals(sales, 'subtotal'), purchases=totals(purchases, 'subtotal'),
                expenses=sum((e['amount'] for e in expenses), ZERO), cash=cash, banks=banks,
                bank_total=bank_total, liquidity=cash+bank_total if cash is not None and bank_total is not None else None,
                input_tax=input_tax, output_tax=output_tax, tax_difference=tax_difference,
                months=list(months.values()), base_currency=base_currency)


def select_documents(documents, kind, filters, mode='', bucket=''):
    if kind not in ('receivables', 'payables', 'sales', 'purchases', 'input-tax', 'output-tax'):
        raise ValueError('Unknown financial view.')
    if mode not in ('', 'overdue', 'soon') or (bucket and bucket not in BUCKETS):
        raise ValueError('Unknown invoice filter.')
    purchase = kind in ('payables', 'purchases', 'input-tax')
    rows = [r for r in documents if (r['kind'] == 'purchase') == purchase]
    today = filters['today']
    if kind in ('receivables', 'payables'):
        rows = [r for r in rows if r['balance'] > 0 and r['date'] <= today]
    else:
        rows = [r for r in rows if filters['start'] <= r['date'] <= filters['end']]
    if mode == 'overdue':
        rows = [r for r in rows if r['due'] and r['due'] < today and r['balance'] > 0]
    if mode == 'soon':
        rows = [r for r in rows if r['due'] and today <= r['due'] <= today+timedelta(days=7) and r['balance'] > 0]
    if bucket:
        rows = [r for r in rows if ageing_bucket(r['due'], today) == bucket]
    return sorted(rows, key=lambda r: (r['date'], r['id']), reverse=True)

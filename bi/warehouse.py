"""Tenant-local BI mart. All public reads use these tables after a successful refresh."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import (MetaData, Table, Column, Integer, String, Float, Date, DateTime,
                        Text, UniqueConstraint, select, update, delete, func)
from customer_models import (CustomerInvoice, PurchaseInvoice, CustomerInvoiceItem,
                             PurchaseInvoiceItem, StockItem, StockPurchaseHistory,
                             Client, Supplier, Expense, CashTransaction, BankTransaction)
from .queries import base_amount, EXCLUDED_STATUSES

M = MetaData()


def dimension(name, extra):
    return Table(name, M, Column('id', Integer, primary_key=True),
                 Column('company_id', String(20), nullable=False, index=True),
                 Column('source_id', String(100), nullable=False),
                 *extra, UniqueConstraint('company_id', 'source_id', name='uq_' + name + '_source'))


def fact(name, extra):
    return dimension(name, [Column('event_date', Date, nullable=False, index=True),
                            Column('branch_id', String(100), nullable=False, default='unassigned'),
                            *extra])

CUSTOMER = dimension('dim_customer', [Column('name', String(200)), Column('location_id', String(100))])
PRODUCT = dimension('dim_product', [Column('name', String(200)), Column('category', String(100)),
                                   Column('unit', String(20)), Column('reorder_level', Float),
                                   Column('quantity', Float), Column('unit_price', Float)])
SUPPLIER = dimension('dim_supplier', [Column('name', String(200)), Column('location_id', String(100))])
BRANCH = dimension('dim_branch', [Column('name', String(200))])
LOCATION = dimension('dim_location', [Column('country', String(100)), Column('state', String(100)),
                                       Column('city', String(100))])
DATE = dimension('dim_date', [Column('calendar_date', Date, nullable=False), Column('year', Integer),
                              Column('month', Integer), Column('quarter', Integer)])
SALES = fact('fact_sales', [Column('customer_id', String(100)), Column('location_id', String(100)),
                            Column('amount', Float), Column('tax', Float), Column('status', String(50))])
PURCHASES = fact('fact_purchases', [Column('supplier_id', String(100)), Column('location_id', String(100)),
                                    Column('amount', Float), Column('tax', Float), Column('status', String(50))])
INVENTORY = fact('fact_inventory', [Column('product_id', String(100)), Column('movement', String(10)),
                                    Column('quantity', Float), Column('value', Float)])
PAYMENTS = fact('fact_payments', [Column('direction', String(10)), Column('amount', Float),
                                  Column('channel', String(10)), Column('party_type', String(20)),
                                  Column('invoice_id', String(100))])
EXPENSES = fact('fact_expenses', [Column('category', String(100)), Column('amount', Float)])
SALES_LINES = fact('fact_sales_lines', [Column('invoice_id', String(100)), Column('product_id', String(100)),
                                        Column('quantity', Float), Column('amount', Float)])
PURCHASE_LINES = fact('fact_purchase_lines', [Column('invoice_id', String(100)), Column('product_id', String(100)),
                                              Column('quantity', Float), Column('amount', Float)])
RUNS = Table('bi_etl_runs', M, Column('id', Integer, primary_key=True),
             Column('company_id', String(20), nullable=False, index=True),
             Column('started_at', DateTime, nullable=False), Column('finished_at', DateTime),
             Column('status', String(20), nullable=False), Column('counts', Text), Column('error', Text))
STATE = Table('bi_etl_state', M, Column('id', Integer, primary_key=True),
              Column('company_id', String(20), nullable=False, unique=True),
              Column('last_success', DateTime), Column('currency', String(10)))

MART = (CUSTOMER, PRODUCT, SUPPLIER, BRANCH, LOCATION, DATE, SALES, PURCHASES,
        INVENTORY, PAYMENTS, EXPENSES, SALES_LINES, PURCHASE_LINES, RUNS, STATE)


def ensure_schema(cdb):
    M.create_all(cdb.get_bind(), tables=list(MART), checkfirst=True)


def _num(value):
    return float(Decimal(str(value or 0)))


def _fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _sync(cdb, table, company_id, records):
    """Reconcile current source set: inserts, changed values, and deletions."""
    old = {r.source_id: dict(r._mapping) for r in cdb.execute(
        select(table).where(table.c.company_id == company_id)).all()}
    counts = {'inserted': 0, 'updated': 0, 'deleted': 0}
    for source_id, payload in records:
        source_id = str(source_id)
        candidate = {'company_id': company_id, 'source_id': source_id, **payload}
        previous = old.pop(source_id, None)
        if previous is None:
            cdb.execute(table.insert().values(**candidate))
            counts['inserted'] += 1
        elif any(previous[k] != v for k, v in candidate.items()):
            cdb.execute(update(table).where(table.c.id == previous['id']).values(**payload))
            counts['updated'] += 1
    for row in old.values():
        cdb.execute(delete(table).where(table.c.id == row['id']))
        counts['deleted'] += 1
    return counts


def _line_base(line, invoice, currency):
    # Use the same legacy-value and exchange-rate fallback as the metric engine.
    row = SimpleNamespace(total_amount=line.total_amount, base_total_amount=line.base_total_amount,
                          currency=invoice.currency, exchange_rate=invoice.exchange_rate)
    return _num(base_amount(row, 'base_total_amount', 'total_amount', currency))


def _valid(invoice):
    return (invoice.status or '').strip().lower() not in EXCLUDED_STATUSES


def _location(entity):
    return '|'.join((getattr(entity, f, None) or '').strip() for f in ('country', 'state', 'city')) if any((getattr(entity, f, None) or '').strip() for f in ('country', 'state', 'city')) else 'unknown'


def _day(d):
    if d is None:
        raise ValueError('A source record is missing its transaction date; correct it before refreshing.')
    return d.date() if isinstance(d, datetime) else d


def refresh(cdb, company_id, currency):
    """Full source reconciliation with incremental writes. Safe to rerun.

    A source scan is required because several ERP tables lack updated_at and CDC.
    Each source is scoped to company_id; no cross-tenant joins are used.
    """
    ensure_schema(cdb)
    started = datetime.utcnow()
    run_id = cdb.execute(RUNS.insert().values(company_id=company_id, started_at=started,
                    status='running')).inserted_primary_key[0]
    cdb.commit()  # Persist a visible run marker before warehouse transaction.
    try:
        state = cdb.execute(select(STATE).where(STATE.c.company_id == company_id).with_for_update()).first()
        if state is None:
            cdb.execute(STATE.insert().values(company_id=company_id, currency=currency))
        clients = {r.id: r for r in cdb.query(Client).filter_by(company_id=company_id).all()}
        suppliers = {r.id: r for r in cdb.query(Supplier).filter_by(company_id=company_id).all()}
        products = {r.id: r for r in cdb.query(StockItem).filter_by(company_id=company_id).all()}
        invoices = {r.id: r for r in cdb.query(CustomerInvoice).filter_by(company_id=company_id).all()}
        purchase_invoices = {r.id: r for r in cdb.query(PurchaseInvoice).filter_by(company_id=company_id).all()}
        locations = {'unknown': ('', '', '')}
        for entity in (*clients.values(), *suppliers.values()):
            locations[_location(entity)] = tuple((getattr(entity, f, None) or '').strip()
                                                  for f in ('country', 'state', 'city'))
        counts = {}
        def sync(table, rows):
            counts[table.name] = _sync(cdb, table, company_id, rows)
        sync(LOCATION, ((key, dict(zip(('country', 'state', 'city'), values)))
                        for key, values in locations.items()))
        sync(BRANCH, [('unassigned', {'name': 'Unassigned (ERP has no branch key)'})])
        sync(CUSTOMER, ((c.id, {'name': c.name, 'location_id': _location(c)}) for c in clients.values()))
        sync(SUPPLIER, ((s.id, {'name': s.name, 'location_id': _location(s)}) for s in suppliers.values()))
        sync(PRODUCT, ((p.id, {'name': p.name, 'category': p.category, 'unit': p.unit,
                             'reorder_level': _num(p.reorder_level), 'quantity': _num(p.quantity),
                             'unit_price': _num(p.unit_price)}) for p in products.values()))
        sales = [r for r in invoices.values() if _valid(r)]
        purchases = [r for r in purchase_invoices.values() if _valid(r)]
        sync(SALES, ((r.id, {'event_date': _day(r.invoice_date), 'customer_id': str(r.client_id) if r.client_id else None,
                            'location_id': _location(clients[r.client_id]) if r.client_id in clients else 'unknown',
                            'amount': _num(base_amount(r, 'base_grand_total', 'grand_total', currency)),
                            'tax': _num(base_amount(r, 'base_tax_amount', 'tax_amount', currency)),
                            'status': r.status, 'branch_id': 'unassigned'}) for r in sales))
        sync(PURCHASES, ((r.id, {'event_date': _day(r.date), 'supplier_id': str(r.supplier_id) if r.supplier_id else None,
                                'location_id': _location(suppliers[r.supplier_id]) if r.supplier_id in suppliers else 'unknown',
                                'amount': _num(base_amount(r, 'base_grand_total', 'grand_total', currency)),
                                'tax': _num(base_amount(r, 'base_tax_amount', 'tax_amount', currency)),
                                'status': r.status, 'branch_id': 'unassigned'}) for r in purchases))
        good_sales = {r.id for r in sales}
        good_purchases = {r.id for r in purchases}
        sync(SALES_LINES, ((r.id, {'event_date': _day(invoices[r.customer_invoice_id].invoice_date),
                                  'invoice_id': str(r.customer_invoice_id), 'product_id': str(r.stock_item_id) if r.stock_item_id else None,
                                  'quantity': _num(r.quantity), 'amount': _line_base(r, invoices[r.customer_invoice_id], currency), 'branch_id': 'unassigned'})
                           for r in cdb.query(CustomerInvoiceItem).filter(CustomerInvoiceItem.customer_invoice_id.in_(good_sales)).all()))
        sync(PURCHASE_LINES, ((r.id, {'event_date': _day(purchase_invoices[r.purchase_invoice_id].date),
                                     'invoice_id': str(r.purchase_invoice_id), 'product_id': str(r.stock_item_id) if r.stock_item_id else None,
                                     'quantity': _num(r.quantity), 'amount': _line_base(r, purchase_invoices[r.purchase_invoice_id], currency), 'branch_id': 'unassigned'})
                              for r in cdb.query(PurchaseInvoiceItem).filter(PurchaseInvoiceItem.purchase_invoice_id.in_(good_purchases)).all()))
        histories = cdb.query(StockPurchaseHistory).filter(StockPurchaseHistory.stock_item_id.in_(set(products))).all() if products else []
        sync(INVENTORY, ((r.id, {'event_date': _day(r.purchase_date), 'product_id': str(r.stock_item_id),
                                 'movement': (r.movement_type or 'IN').upper(), 'quantity': _num(r.quantity),
                                 'value': _num(r.quantity) * _num(base_amount(r, 'base_purchase_rate', 'purchase_rate', currency)),
                                 'branch_id': 'unassigned'}) for r in histories))
        cash = cdb.query(CashTransaction).filter_by(company_id=company_id).all()
        bank = cdb.query(BankTransaction).filter_by(company_id=company_id).all()
        def payment_rows():
            for channel, rows in (('cash', cash), ('bank', bank)):
                for r in rows:
                    direction = ('in' if (r.type or '').lower() in ('income', 'credit') else
                                 'out' if (r.type or '').lower() in ('expense', 'debit') else None)
                    if not direction:
                        continue
                    yield channel + ':' + str(r.id), {'event_date': _day(r.date), 'direction': direction,
                        'amount': _num(r.amount), 'channel': channel,
                        'party_type': r.applied_ref_type, 'invoice_id': str(r.applied_ref_id) if r.applied_ref_id else None,
                        'branch_id': 'unassigned'}
        sync(PAYMENTS, payment_rows())
        sync(EXPENSES, ((r.id, {'event_date': _day(r.date), 'category': r.category,
                               'amount': _num(r.amount), 'branch_id': 'unassigned'})
                        for r in cdb.query(Expense).filter_by(company_id=company_id).all()))
        dates = {r[0] for table in (SALES, PURCHASES, INVENTORY, PAYMENTS, EXPENSES)
                 for r in cdb.execute(select(table.c.event_date).where(table.c.company_id == company_id)).all()}
        sync(DATE, ((d.isoformat(), {'calendar_date': d, 'year': d.year, 'month': d.month,
                                    'quarter': (d.month - 1) // 3 + 1}) for d in dates))
        now = datetime.utcnow()
        cdb.execute(update(STATE).where(STATE.c.company_id == company_id).values(last_success=now, currency=currency))
        cdb.execute(update(RUNS).where(RUNS.c.id == run_id).values(status='success',
                    finished_at=now, counts=json.dumps(counts)))
        cdb.commit()
        return {'status': 'success', 'run_id': run_id, 'counts': counts, 'last_success': now.isoformat() + 'Z'}
    except Exception as exc:
        cdb.rollback()
        cdb.execute(update(RUNS).where(RUNS.c.id == run_id).values(
            status='failed', finished_at=datetime.utcnow(), error=str(exc)[:2000]))
        cdb.commit()
        raise


def status(cdb, company_id):
    ensure_schema(cdb)
    state = cdb.execute(select(STATE).where(STATE.c.company_id == company_id)).mappings().first()
    runs = cdb.execute(select(RUNS).where(RUNS.c.company_id == company_id)
                       .order_by(RUNS.c.id.desc()).limit(20)).mappings().all()
    return {'last_success': state['last_success'].isoformat() + 'Z' if state and state['last_success'] else None,
            'currency': state['currency'] if state else None,
            'runs': [{'id': r['id'], 'status': r['status'], 'started_at': r['started_at'].isoformat() + 'Z',
                      'finished_at': r['finished_at'].isoformat() + 'Z' if r['finished_at'] else None,
                      'counts': json.loads(r['counts']) if r['counts'] else None, 'error': r['error']}
                     for r in runs], 'source_scan_required': True, 'branch_available': False,
            'refresh_mode': 'Full source scan with incremental inserts, updates and deletions',
            'scheduler_note': 'Refresh runs on demand or through the bi-refresh command. An external scheduler must be configured separately.'}


def require_ready(cdb, company_id):
    info = status(cdb, company_id)
    if not info['last_success']:
        raise ValueError('Warehouse has not refreshed successfully. Run the Phase 6 refresh first.')
    if info['runs'] and info['runs'][0]['status'] != 'success':
        info['warning'] = 'Latest ETL run did not succeed; showing last successful snapshot.'
    elif datetime.utcnow() - datetime.fromisoformat(info['last_success'].rstrip('Z')) > timedelta(hours=24):
        info['warning'] = 'Warehouse snapshot is over 24 hours old. Refresh before using these figures for planning.'
    return info


def summary(cdb, company_id):
    info = require_ready(cdb, company_id)
    totals = {}
    for table in (SALES, PURCHASES, INVENTORY, PAYMENTS, EXPENSES, SALES_LINES, PURCHASE_LINES,
                  CUSTOMER, PRODUCT, SUPPLIER, BRANCH, LOCATION, DATE):
        totals[table.name] = cdb.execute(select(func.count()).select_from(table)
                                    .where(table.c.company_id == company_id)).scalar() or 0
    info['row_counts'] = totals
    info['sales_total'] = _num(cdb.execute(select(func.sum(SALES.c.amount)).where(SALES.c.company_id == company_id)).scalar())
    info['purchase_total'] = _num(cdb.execute(select(func.sum(PURCHASES.c.amount)).where(PURCHASES.c.company_id == company_id)).scalar())
    info['expense_total'] = _num(cdb.execute(select(func.sum(EXPENSES.c.amount)).where(EXPENSES.c.company_id == company_id)).scalar())
    return info

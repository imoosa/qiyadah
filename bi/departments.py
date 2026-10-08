"""Phase 3 department summaries. No legacy booking invoices are aggregated here."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from flask import abort
from customer_models import Client, CustomerInvoice, CustomerInvoiceItem, Expense, PurchaseInvoice, PurchaseInvoiceItem, StockItem, Supplier
from .metrics import live_metrics, period_metrics, serialise_metrics
from .queries import base_amount, base_balance, expense_query, money, purchase_query, sales_query, stock_query

ZERO = Decimal('0')
SECTIONS = ('sales', 'customers', 'purchases', 'suppliers', 'inventory', 'finance', 'tax', 'geography', 'branches')


def _sum(values):
    return round(float(sum(values, ZERO)), 2)


def _metric(label, value, kind='money', note=None):
    return {'label': label, 'value': round(float(value), 2), 'kind': kind, 'note': note}


def _rows(mapping, limit=10):
    return [{'name': str(k), 'value': round(float(v), 2)} for k, v in sorted(mapping.items(), key=lambda pair: -pair[1])[:limit]]


def _monthly(rows, field, measure):
    buckets = defaultdict(lambda: ZERO)
    for row in rows:
        day = getattr(row, field)
        if day:
            buckets[day.strftime('%Y-%m')] += measure(row)
    return [{'name': key, 'value': round(float(value), 2)} for key, value in sorted(buckets.items())]


def _base(row, key, base_currency):
    return base_amount(row, 'base_' + key, key, base_currency)


def _locations(client):
    if not client:
        return ('Unspecified', 'Unspecified', 'Unspecified')
    return tuple((getattr(client, field, '') or 'Unspecified').strip() or 'Unspecified' for field in ('country', 'state', 'city'))


def department(cdb, filters, can, currency, today, section):
    if section not in SECTIONS:
        abort(404)
    result = {'section': section, 'currency': currency, 'filters': filters.to_dict(),
              'cards': [], 'charts': [], 'tables': [], 'notes': []}
    if section == 'branches':
        result['notes'].append('Branch analytics are unavailable: canonical sales and purchase transactions have no branch_id. Company-wide totals must not be labelled by branch.')
        return result

    sales_ok = can('customer_invoices', 'view') or can('invoices', 'view')
    purchases_ok = can('purchase', 'view')
    stock_ok = can('stock', 'view')
    if section in ('sales', 'customers', 'geography') and not sales_ok:
        abort(403)
    if section in ('purchases', 'suppliers') and not purchases_ok:
        abort(403)
    if section == 'inventory' and not stock_ok:
        abort(403)
    if section == 'finance' and not (sales_ok or purchases_ok or can('expenses', 'view')):
        abort(403)
    if section == 'tax' and not (sales_ok or purchases_ok):
        abort(403)

    sales = sales_query(cdb, filters, filters.from_date, filters.to_date).all() if sales_ok and section in ('sales', 'customers', 'geography', 'finance', 'tax') else []
    purchases = purchase_query(cdb, filters, filters.from_date, filters.to_date).all() if purchases_ok and section in ('purchases', 'suppliers', 'finance', 'tax') else []
    clients = {row.id: row for row in cdb.query(Client).filter_by(company_id=filters.company_id).all()} if section in ('sales', 'customers', 'geography') else {}
    suppliers = {row.id: row for row in cdb.query(Supplier).filter_by(company_id=filters.company_id).all()} if section in ('purchases', 'suppliers') else {}
    cards, charts, tables, notes = result['cards'], result['charts'], result['tables'], result['notes']
    chart = lambda title, items: charts.append({'title': title, 'rows': items})
    table = lambda title, columns, rows: tables.append({'title': title, 'columns': columns, 'rows': rows})

    if section == 'sales':
        billed = _sum(_base(r, 'grand_total', currency) for r in sales)
        net = _sum(_base(r, 'subtotal', currency) for r in sales)
        cards.extend([_metric('Net sales · excl. tax', net), _metric('Billed sales', billed),
                      _metric('Invoices', len(sales), 'count'), _metric('Average invoice', billed / len(sales) if sales else 0)])
        chart('Net sales by month', _monthly(sales, 'invoice_date', lambda r: _base(r, 'subtotal', currency)))
        by_client, by_type = defaultdict(lambda: ZERO), defaultdict(int)
        for r in sales:
            name = clients[r.client_id].name if r.client_id in clients else (r.client_name or 'Unspecified')
            by_client[name] += _base(r, 'subtotal', currency)
            by_type[r.invoice_category or 'Unspecified'] += 1
        chart('Top customers · net sales', _rows(by_client))
        table('Invoice category', ['Category', 'Invoices'], [[k, v] for k, v in sorted(by_type.items())])
        # Line-item values are kept separate from invoice net sales: discounts and
        # non-stock service lines may make their totals differ from header totals.
        invoice_by_id = {r.id: r for r in sales}
        ids = list(invoice_by_id)
        if ids:
            items = cdb.query(CustomerInvoiceItem).filter(CustomerInvoiceItem.customer_invoice_id.in_(ids)).all()
            products = defaultdict(lambda: ZERO)
            for item in items:
                label = item.item_name or item.item_description or item.item_code or 'Unspecified item'
                products[label] += _line_value(item, invoice_by_id[item.customer_invoice_id], currency)
            chart('Top invoice line items · taxable value', _rows(products))
            notes.append('Line-item values may not reconcile exactly to invoice subtotals. Product category uses the current stock master and is deferred until historical attribution is recorded.')

    elif section == 'customers':
        by_id = defaultdict(lambda: {'sales': ZERO, 'count': 0, 'last': None})
        for r in sales:
            if r.client_id is None:
                continue
            item = by_id[r.client_id]
            item['sales'] += _base(r, 'subtotal', currency)
            item['count'] += 1
            item['last'] = max(filter(None, [item['last'], r.invoice_date]), default=None)
        cards.extend([_metric('Customer records', len(clients), 'count'),
                      _metric('Buying customers', len(by_id), 'count'),
                      _metric('Repeat customers', sum(x['count'] > 1 for x in by_id.values()), 'count'),
                      _metric('Period sales', _sum(x['sales'] for x in by_id.values()))])
        chart('Top customers · net sales', _rows({clients[k].name if k in clients else str(k): v['sales'] for k, v in by_id.items()}))
        table('Customer activity in period', ['Customer', 'Invoices', 'Net sales', 'Last invoice'],
              [[clients[k].name if k in clients else str(k), v['count'], round(float(v['sales']), 2), v['last'].isoformat() if v['last'] else '—']
               for k, v in sorted(by_id.items(), key=lambda pair: -pair[1]['sales'])[:25]])
        notes.append('Repeat means more than one invoice within the chosen dates. Lifetime value and dormancy require a separate all-history calculation.')

    elif section in ('purchases', 'suppliers'):
        cost = _sum(_base(r, 'subtotal', currency) for r in purchases)
        supplier_totals = defaultdict(lambda: ZERO)
        for r in purchases:
            name = suppliers[r.supplier_id].name if r.supplier_id in suppliers else (r.supplier_name or 'Unspecified')
            supplier_totals[name] += _base(r, 'subtotal', currency)
        cards.extend([_metric('Purchases · excl. tax', cost), _metric('Purchase invoices', len(purchases), 'count'),
                      _metric('Active suppliers in period', len({r.supplier_id for r in purchases if r.supplier_id}), 'count')])
        if section == 'suppliers':
            cards.append(_metric('Supplier records', len(suppliers), 'count'))
        chart('Purchases by month', _monthly(purchases, 'date', lambda r: _base(r, 'subtotal', currency)))
        chart('Top suppliers · purchases', _rows(supplier_totals))
        table('Supplier spend', ['Supplier', 'Purchases excl. tax'], [[r['name'], r['value']] for r in _rows(supplier_totals, 25)])
        notes.append('Supplier lead time and on-time delivery cannot be inferred from purchase invoices alone.')

    elif section == 'inventory':
        items = stock_query(cdb, filters).all()
        category, low = defaultdict(lambda: ZERO), []
        total = ZERO
        for item in items:
            qty = money(item.quantity)
            cost = money(item.avg_purchase_rate or item.last_purchase_rate or item.purchase_rate or item.unit_price)
            value = qty * cost
            total += value
            category[item.category or 'Uncategorised'] += value
            if money(item.reorder_level) > 0 and qty <= money(item.reorder_level):
                low.append([item.code, item.name, float(qty), float(money(item.reorder_level)), round(float(value), 2)])
        cards.extend([_metric('Stock value · estimate', total), _metric('Stock items', len(items), 'count'),
                      _metric('Low stock items', len(low), 'count'), _metric('Total units', _sum(money(i.quantity) for i in items), 'number')])
        chart('Stock value by category', _rows(category))
        table('Below reorder level', ['Code', 'Item', 'Quantity', 'Reorder level', 'Estimated value'], low[:50])
        notes.append('Stock is a current snapshot, so date selection does not change this tab. Units from different item types are summed for reference only. Movement velocity and dead stock require historical movements.')

    elif section == 'finance':
        period = serialise_metrics(period_metrics(cdb, filters, currency, can))
        live = serialise_metrics(live_metrics(cdb, filters, currency, can, today))
        for key, label in [('net_sales', 'Net sales'), ('purchase_cost', 'Purchases excl. tax'), ('expenses', 'Expenses'),
                           ('gross_profit_estimate', 'Gross profit · estimate'), ('net_profit_estimate', 'Net profit · estimate')]:
            if key in period:
                cards.append(_metric(label, period[key]))
        for key, label in [('receivables', 'Receivables · current'), ('payables', 'Payables · current')]:
            if key in live:
                cards.append(_metric(label, live[key]))
        if sales_ok:
            chart('Net sales by month', _monthly(sales, 'invoice_date', lambda r: _base(r, 'subtotal', currency)))
        if purchases_ok:
            chart('Purchases by month', _monthly(purchases, 'date', lambda r: _base(r, 'subtotal', currency)))
        if can('expenses', 'view'):
            expenses = expense_query(cdb, filters, filters.from_date, filters.to_date).all()
            chart('Expenses by category', _rows(_group(expenses, lambda r: r.category or 'Other', lambda r: money(r.amount))))
        notes.append('Profit uses period purchases, not matched COGS; it is an operational estimate. Outstanding balances are current, not historical as of the selected dates.')

    elif section == 'tax':
        output = _sum(_base(r, 'tax_amount', currency) for r in sales)
        input_tax = _sum(_base(r, 'tax_amount', currency) for r in purchases)
        if sales_ok:
            cards.append(_metric('Output tax recorded', output))
        if purchases_ok:
            cards.append(_metric('Purchase tax recorded', input_tax))
        regime_sales = _group(sales, lambda r: r.tax_regime or 'Unspecified', lambda r: _base(r, 'tax_amount', currency))
        regime_purchase = _group(purchases, lambda r: r.tax_regime or 'Unspecified', lambda r: _base(r, 'tax_amount', currency))
        if sales_ok:
            chart('Output tax by regime', _rows(regime_sales))
        if purchases_ok:
            chart('Purchase tax by regime', _rows(regime_purchase))
        notes.append('Recorded purchase tax is not validated input tax credit. Reverse charge, eligibility, refunds and jurisdiction rules must be reconciled before reporting a tax liability.')

    elif section == 'geography':
        by_country, by_state, by_city = (defaultdict(lambda: ZERO) for _ in range(3))
        for row in sales:
            loc = _locations(clients.get(row.client_id))
            value = _base(row, 'subtotal', currency)
            by_country[loc[0]] += value
            by_state[' / '.join(loc[:2])] += value
            by_city[' / '.join(loc)] += value
        cards.extend([_metric('Net sales', _sum(by_country.values())),
                      _metric('Countries', len(by_country), 'count'), _metric('Cities', len(by_city), 'count')])
        chart('Sales by country', _rows(by_country))
        chart('Sales by state', _rows(by_state))
        table('Top cities', ['Country / State / City', 'Net sales'], [[r['name'], r['value']] for r in _rows(by_city, 25)])
        notes.append('Geography comes from the customer master’s current address. It is not the historical invoice destination; missing customer records appear as Unspecified.')

    return result


def _group(rows, name, value):
    out = defaultdict(lambda: ZERO)
    for row in rows:
        out[name(row)] += value(row)
    return out


def _line_value(item, invoice, base_currency):
    native = money(item.taxable_amount)
    if (invoice.currency or base_currency).upper() == base_currency.upper():
        return native
    stored = money(item.base_taxable_amount)
    return stored if stored or not native else native * money(invoice.exchange_rate or 1)

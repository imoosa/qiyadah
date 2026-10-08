"""Canonical, owner-only BI drill paths shared by the explorer and exports."""
from collections import defaultdict
from decimal import Decimal
from customer_models import Client, CompanyUser, CustomerInvoiceItem, PurchaseInvoiceItem, StockItem, Supplier
from .filters import BIValidationError
from .queries import base_amount, money, purchase_query, sales_query, stock_query

ZERO = Decimal('0')
PATHS = {
    'geo': ('country', 'state', 'city', 'customer', 'invoice', 'line'),
    'customer': ('customer', 'invoice', 'line'),
    'employee': ('employee', 'customer', 'invoice', 'line'),
    'product': ('category', 'product', 'invoice', 'line'),
    'purchase': ('supplier', 'invoice', 'line'),
    'inventory': ('category', 'item'),
}


def _clean_text(value, field):
    if value is None or value == '':
        return None
    value = str(value).strip()
    if len(value) > 180:
        raise BIValidationError(f'{field} is too long.')
    return value


def _key(params, name):
    value = _clean_text(params.get(name), name)
    if value is None:
        return None
    if name in ('customer', 'product', 'supplier', 'invoice', 'item'):
        try:
            number = int(value)
            if number < 0:
                raise ValueError
            return number
        except ValueError:
            raise BIValidationError(f'{name} must be a non-negative integer.') from None
    return value


def _money(row, field, currency):
    return base_amount(row, 'base_' + field, field, currency)


def _loc(client, key):
    return ((getattr(client, key, None) if client else None) or 'Unspecified').strip() or 'Unspecified'


def _line_amount(item, invoice, currency):
    raw = getattr(item, 'taxable_amount', None)
    if raw is None:
        raw = getattr(item, 'taxable_value', 0)
    native = money(raw)
    if (invoice.currency or currency).upper() == currency.upper():
        return native
    stored = money(getattr(item, 'base_taxable_amount', 0))
    return stored if stored or not native else native * money(invoice.exchange_rate or 1)


def _summary(rows, level, next_level, currency, warnings=(), limit=100):
    total = sum((Decimal(str(r['value'])) for r in rows), ZERO)
    return {'level': level, 'next_level': next_level, 'currency': currency,
            'rows': rows[:limit], 'row_count': len(rows), 'shown': min(len(rows), limit),
            'total': round(float(total), 2), 'warnings': list(warnings),
            'truncated': len(rows) > limit}


def explore(cdb, filters, params, can, currency, limit=100):
    view = _clean_text(params.get('view'), 'view') or 'geo'
    if view not in PATHS:
        raise BIValidationError('Unknown drill-down view.')
    unexpected = set(params.keys()) - {'view', 'from_date', 'to_date', *PATHS[view]}
    if unexpected:
        raise BIValidationError('Unsupported drill filter: ' + sorted(unexpected)[0])
    if view in ('geo', 'customer', 'employee', 'product') and not (can('customer_invoices', 'view') or can('invoices', 'view')):
        raise BIValidationError('Sales access is required for this view.')
    if view == 'purchase' and not can('purchase', 'view'):
        raise BIValidationError('Purchase access is required for this view.')
    if view == 'inventory' and not can('stock', 'view'):
        raise BIValidationError('Inventory access is required for this view.')
    path = PATHS[view]
    selected = {}
    gap = False
    for field in path:
        key = _key(params, field)
        if key is None:
            gap = True
        elif gap:
            raise BIValidationError('Choose each drill level in order.')
        else:
            selected[field] = key
    stage = len(selected)
    if stage == len(path):
        raise BIValidationError('The selected path is already at its final level.')
    level = path[stage]
    next_level = path[stage + 1] if stage + 1 < len(path) else None
    warnings = []
    if view == 'inventory':
        warnings.append('Inventory values are current estimates; the date range does not change current stock.')
        items = stock_query(cdb, filters).all()
        if 'category' in selected:
            items = [i for i in items if (i.category or 'Uncategorised') == selected['category']]
        out = defaultdict(lambda: {'value': ZERO, 'count': 0, 'label': ''})
        for item in items:
            key = item.category or 'Uncategorised' if level == 'category' else item.id
            val = money(item.quantity) * money(item.avg_purchase_rate or item.last_purchase_rate or item.purchase_rate or item.unit_price)
            out[key]['value'] += val
            out[key]['count'] += 1
            out[key]['label'] = key if level == 'category' else f'{item.code} · {item.name} ({item.quantity:g} {item.unit or "units"})'
        rows = [{'key': k, 'label': v['label'], 'value': round(float(v['value']), 2), 'count': v['count']} for k, v in out.items()]
        rows.sort(key=lambda r: -r['value'])
        return _summary(rows, level, next_level, currency, warnings, limit)

    if view == 'purchase':
        docs = purchase_query(cdb, filters, filters.from_date, filters.to_date).all()
        suppliers = {r.id: r for r in cdb.query(Supplier).filter_by(company_id=filters.company_id).all()}
        if 'supplier' in selected:
            docs = [r for r in docs if (r.supplier_id or 0) == selected['supplier']]
        if 'invoice' in selected:
            docs = [r for r in docs if r.id == selected['invoice']]
        if level == 'line':
            by_id = {r.id: r for r in docs}
            lines = cdb.query(PurchaseInvoiceItem).filter(PurchaseInvoiceItem.purchase_invoice_id.in_(list(by_id))).all() if by_id else []
            rows = [{'key': i.id, 'label': i.item_name or i.description or i.code or 'Item',
                     'value': round(float(_line_amount(i, by_id[i.purchase_invoice_id], currency)), 2), 'count': 1} for i in lines]
            rows.sort(key=lambda r: -r['value'])
            warnings.append('Line taxable values can differ from invoice subtotal because of header adjustments.')
            return _summary(rows, level, None, currency, warnings, limit)
        out = defaultdict(lambda: {'value': ZERO, 'count': 0, 'label': ''})
        for doc in docs:
            key = (doc.supplier_id or 0) if level == 'supplier' else doc.id
            label = ((suppliers.get(doc.supplier_id).name if doc.supplier_id in suppliers else doc.supplier_name) or 'Unlinked supplier') if level == 'supplier' else f'{doc.invoice_id} · {doc.date}'
            out[key]['value'] += _money(doc, 'subtotal', currency)
            out[key]['count'] += 1
            out[key]['label'] = label
    else:
        docs = sales_query(cdb, filters, filters.from_date, filters.to_date).all()
        clients = {r.id: r for r in cdb.query(Client).filter_by(company_id=filters.company_id).all()}
        for geo in ('country', 'state', 'city'):
            if geo in selected:
                docs = [r for r in docs if _loc(clients.get(r.client_id), geo) == selected[geo]]
        if 'employee' in selected:
            docs = [r for r in docs if (r.created_by or 'Unspecified') == selected['employee']]
        if 'customer' in selected:
            docs = [r for r in docs if (r.client_id or 0) == selected['customer']]
        if 'invoice' in selected:
            docs = [r for r in docs if r.id == selected['invoice']]
        invoice_by_id = {r.id: r for r in docs}
        stock = {}
        lines = []
        if view == 'product' or level == 'line':
            lines = cdb.query(CustomerInvoiceItem).filter(CustomerInvoiceItem.customer_invoice_id.in_(list(invoice_by_id))).all() if invoice_by_id else []
            if view == 'product':
                ids = {i.stock_item_id for i in lines if i.stock_item_id}
                stock = {i.id: i for i in cdb.query(StockItem).filter(StockItem.company_id == filters.company_id, StockItem.id.in_(ids)).all()} if ids else {}
                if 'category' in selected:
                    lines = [i for i in lines if ((stock[i.stock_item_id].category if i.stock_item_id in stock else None) or 'Uncategorised') == selected['category']]
                if 'product' in selected:
                    lines = [i for i in lines if (i.stock_item_id or 0) == selected['product']]
                docs = [r for r in docs if r.id in {i.customer_invoice_id for i in lines}]
                invoice_by_id = {r.id: r for r in docs}
            warnings.append('Product values use taxable invoice lines; they can differ from invoice subtotal. Product category reflects the current stock master.')
        if level == 'line':
            rows = [{'key': i.id, 'label': i.item_name or i.item_description or i.item_code or 'Item',
                     'value': round(float(_line_amount(i, invoice_by_id[i.customer_invoice_id], currency)), 2), 'count': 1} for i in lines]
            rows.sort(key=lambda r: -r['value'])
            return _summary(rows, level, None, currency, warnings, limit)
        out = defaultdict(lambda: {'value': ZERO, 'count': 0, 'label': ''})
        if view == 'product':
            for line in lines:
                inv = invoice_by_id[line.customer_invoice_id]
                item = stock.get(line.stock_item_id)
                key = (item.category or 'Uncategorised') if level == 'category' and item else ('Uncategorised' if level == 'category' else (line.stock_item_id or 0))
                if level == 'product':
                    key = line.stock_item_id or 0
                if level == 'invoice':
                    key = inv.id
                label = str(key) if level == 'category' else (item.name if item else 'Unlinked / service item') if level == 'product' else f'{inv.invoice_number} · {inv.invoice_date}'
                out[key]['value'] += _line_amount(line, inv, currency)
                out[key]['count'] += 1
                out[key]['label'] = label
        else:
            for doc in docs:
                client = clients.get(doc.client_id)
                key = _loc(client, level) if level in ('country', 'state', 'city') else (doc.created_by or 'Unspecified') if level == 'employee' else (doc.client_id or 0) if level == 'customer' else doc.id
                label = (client.name if client else doc.client_name or 'Unlinked customer') if level == 'customer' else f'{doc.invoice_number} · {doc.invoice_date}' if level == 'invoice' else str(key)
                out[key]['value'] += _money(doc, 'subtotal', currency)
                out[key]['count'] += 1
                out[key]['label'] = label
        if view == 'geo':
            warnings.append('Geography is from current customer master addresses, not historical invoice destinations.')
    rows = [{'key': k, 'label': v['label'], 'value': round(float(v['value']), 2), 'count': v['count']} for k, v in out.items()]
    rows.sort(key=lambda r: -r['value'])
    return _summary(rows, level, next_level, currency, warnings, limit)

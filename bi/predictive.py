"""Transparent, warehouse-only planning indicators. No probability claims."""
from __future__ import annotations
from collections import defaultdict
from datetime import date, timedelta
from math import ceil
from statistics import median
from sqlalchemy import select
from .warehouse import (SALES, PRODUCT, INVENTORY, PAYMENTS, CUSTOMER,
                        require_ready)


def _month_add(y, m, n):
    return f'{y + (m - 1 + n) // 12:04d}-{(m - 1 + n) % 12 + 1:02d}'


def _series(rows, date_key, value_key, today):
    """Complete elapsed months, including genuine zero months."""
    totals = defaultdict(float)
    for row in rows:
        day = row[date_key]
        if day and day < today.replace(day=1):
            totals[day.strftime('%Y-%m')] += float(row[value_key] or 0)
    if not totals:
        return []
    first = min(totals)
    y, m = map(int, first.split('-'))
    result = []
    n = 0
    while True:
        key = _month_add(y, m, n)
        if key >= today.strftime('%Y-%m'):
            break
        result.append({'month': key, 'actual': round(totals[key], 2)})
        n += 1
    return result


def forecast(series, horizon=3, allow_negative=False):
    """Recent trailing mean; backtest against the last three completed months."""
    if len(series) < 6:
        return {'status': 'insufficient_history', 'months_available': len(series),
                'months_required': 6, 'history': series, 'forecast': [],
                'method': 'trailing-three-month mean'}
    values = [r['actual'] for r in series]
    errors = []
    for i in range(max(3, len(values) - 3), len(values)):
        errors.append(abs(values[i] - sum(values[i-3:i]) / 3))
    mae = round(sum(errors) / len(errors), 2)
    level = sum(values[-3:]) / 3
    if not allow_negative:
        level = max(0.0, level)
    y, m = map(int, series[-1]['month'].split('-'))
    return {'status': 'ready', 'method': 'trailing-three-month mean',
            'backtest_mae': mae, 'history': series[-24:],
            'forecast': [{'month': _month_add(y, m, i), 'value': round(level, 2),
                          'low': round(level - 2 * mae if allow_negative else max(0, level - 2 * mae), 2),
                          'high': round(level + 2 * mae, 2)} for i in range(1, horizon+1)],
            'interval_note': 'Heuristic range from recent absolute error; not a statistical confidence interval.'}


def _anomalies(series):
    if len(series) < 8:
        return {'status': 'insufficient_history', 'months_required': 8, 'months_available': len(series)}
    values = [r['actual'] for r in series]
    baseline = median(values)
    mad = median([abs(v-baseline) for v in values])
    threshold = max(3 * 1.4826 * mad, baseline * 0.5, 1)
    flags = [{'month': r['month'], 'value': r['actual'], 'deviation': round(r['actual']-baseline, 2)}
             for r in series[-12:] if abs(r['actual']-baseline) > threshold]
    return {'status': 'ready', 'method': 'median and MAD with 50% minimum relative threshold',
            'flags': flags, 'note': 'Review unusual months; a flag is not evidence of fraud.'}


def build(cdb, company_id, today=None, lead_days=14, horizon=3):
    today = today or date.today()
    freshness = require_ready(cdb, company_id)
    sales = cdb.execute(select(SALES.c.event_date, SALES.c.amount, SALES.c.customer_id)
                        .where(SALES.c.company_id == company_id, SALES.c.event_date <= today)).mappings().all()
    payments = cdb.execute(select(PAYMENTS.c.event_date, PAYMENTS.c.amount, PAYMENTS.c.direction)
                           .where(PAYMENTS.c.company_id == company_id, PAYMENTS.c.event_date <= today)).mappings().all()
    products = cdb.execute(select(PRODUCT).where(PRODUCT.c.company_id == company_id)).mappings().all()
    movements = cdb.execute(select(INVENTORY.c.event_date, INVENTORY.c.product_id,
                                   INVENTORY.c.quantity, INVENTORY.c.movement)
                            .where(INVENTORY.c.company_id == company_id, INVENTORY.c.event_date <= today)).mappings().all()
    customers = cdb.execute(select(CUSTOMER.c.source_id, CUSTOMER.c.name)
                            .where(CUSTOMER.c.company_id == company_id)).mappings().all()
    count_series = _series([{'event_date': r['event_date'], 'value': 1} for r in sales],
                           'event_date', 'value', today)
    revenue_series = _series(sales, 'event_date', 'amount', today)
    cash_series = _series([{'event_date': r['event_date'],
                            'value': float(r['amount'] or 0) * (1 if r['direction'] == 'in' else -1)}
                           for r in payments], 'event_date', 'value', today)
    demand = []
    movements_by_product = defaultdict(list)
    for movement in movements:
        movements_by_product[movement['product_id']].append(movement)
    for p in products:
        product_movements = movements_by_product[p['source_id']]
        outbound = [r for r in product_movements if
                    r['movement'] == 'OUT' and today-timedelta(days=89) <= r['event_date'] <= today]
        days_observed = (today - min((r['event_date'] for r in product_movements), default=today)).days + 1
        if not product_movements or days_observed < 30:
            demand.append({'product_id': p['source_id'], 'name': p['name'],
                           'current_units': float(p['quantity'] or 0),
                           'status': 'insufficient_history', 'outbound_events': len(outbound)})
            continue
        daily = sum(abs(float(r['quantity'] or 0)) for r in outbound) / min(90, days_observed)
        stock = float(p['quantity'] or 0)
        reorder = float(p['reorder_level'] or 0)
        requirement = max(0, ceil(daily * lead_days + reorder - stock))
        stockout_days = 0 if stock <= 0 else ceil(stock / daily) if daily > 0 else None
        demand.append({'product_id': p['source_id'], 'name': p['name'], 'status': 'ready',
                       'current_units': stock, 'daily_demand': round(daily, 3),
                       'next_30_days_units': round(daily*30, 1),
                       'stockout_in_days': stockout_days,
                       'stockout_date': (today+timedelta(days=stockout_days)).isoformat() if stockout_days is not None else None,
                       'purchase_requirement_units': requirement,
                       'lead_days_assumption': lead_days, 'reorder_level_safety_units': reorder})
    dates_by_customer = defaultdict(list)
    for sale in sales:
        dates_by_customer[sale['customer_id']].append(sale['event_date'])
    customers_risk = []
    for customer in customers:
        dates = dates_by_customer[customer['source_id']]
        if len(dates) < 2 or (today-min(dates)).days < 180:
            indicator = 'insufficient_history'
        else:
            age = (today-max(dates)).days
            indicator = 'at_risk' if age > 90 and len(dates) >= 2 else 'active'
        customers_risk.append({'customer_id': customer['source_id'], 'name': customer['name'],
                               'indicator': indicator, 'invoices': len(dates),
                               'days_since_last_sale': (today-max(dates)).days if dates else None})
    return {'as_of': today.isoformat(), 'warehouse_last_success': freshness['last_success'],
            'warehouse_warning': freshness.get('warning'), 'currency': freshness['currency'],
            'sales_forecast': forecast(count_series, horizon), 'revenue_forecast': forecast(revenue_series, horizon),
            'inventory_demand': demand, 'cash_flow_forecast': forecast(cash_series, horizon, allow_negative=True),
            'customer_risk': customers_risk, 'anomalies': _anomalies(revenue_series),
            'assumptions': ['Only completed months enter monthly forecasts.',
                'Sales forecast means invoice count; revenue means invoiced total in base currency.',
                'Cash flow uses signed cash and bank ledger transactions, including non-operating entries.',
                'OUT stock movements are used as demand proxy; they can include non-sale movements.',
                'Purchase requirement = demand over lead time + reorder level - current stock.',
                'At-risk requires at least 180 days of customer history, two invoices and over 90 days without an invoice; no churn probability.']}

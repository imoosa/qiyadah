"""Chart-ready, read-only posted-ledger performance and dated activity series."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, inspect
from customer_models import ChartOfAccount, JournalEntry, JournalEntryLine


def month_labels(start, end):
    labels = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        labels.append(f'{year:04}-{month:02}')
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return labels


def chart(title, labels, series, kind='bar', unit='count', currency=None,
          scope='Selected period', note='', source=''):
    return dict(title=title, labels=labels,
        series=[dict(name=name, values=[float(value) for value in values]) for name, values in series],
        kind=kind, unit=unit, currency=currency, scope=scope, note=note, source=source)


def volume_trend(query, column, start, end, title):
    days = query.with_entities(func.date(column), func.count()).group_by(func.date(column)).all()
    values = defaultdict(int)
    for day, count in days:
        if day:
            values[str(day)[:7]] += count
    labels = month_labels(start, end)
    return chart(title, labels, [(title, [values[label] for label in labels])], kind='line',
        note='Calendar-month buckets within the selected dates; partial months are not extrapolated.',
        source=column.table.name)


def ledger_performance(cdb, company_id, start, end, previous_start, previous_end, currency):
    """Same posted/reversed journal basis and account grouping as Profit & Loss.

    Source document totals are deliberately not substitutes for posted COGS.
    No writes, auto-posting, opening-balance assumptions or accounting setup.
    """
    inspector = inspect(cdb.get_bind())
    tables = set(inspector.get_table_names())
    for model in (ChartOfAccount, JournalEntry, JournalEntryLine):
        if model.__tablename__ not in tables or not set(model.__table__.columns.keys()).issubset(
                {c['name'] for c in inspector.get_columns(model.__tablename__)}):
            return dict(available=False, reason='Posted accounting data needs setup before profit can be reported.', charts=[])
    rows = cdb.query(JournalEntry.entry_date, ChartOfAccount.code, ChartOfAccount.name,
        ChartOfAccount.account_type, ChartOfAccount.account_group,
        func.sum(JournalEntryLine.debit), func.sum(JournalEntryLine.credit)).select_from(JournalEntryLine).join(
        JournalEntry, JournalEntryLine.entry_id == JournalEntry.id).join(
        ChartOfAccount, JournalEntryLine.account_id == ChartOfAccount.id).filter(
        JournalEntry.company_id == company_id, ChartOfAccount.company_id == company_id,
        JournalEntry.status.in_(('Posted', 'Reversed')),
        ChartOfAccount.account_type.in_(('Income', 'Expense')),
        JournalEntry.entry_date >= previous_start, JournalEntry.entry_date <= end).group_by(
        JournalEntry.entry_date, ChartOfAccount.id).all()
    zero = lambda: dict(revenue=Decimal(0), other_income=Decimal(0), cogs=Decimal(0), expenses=Decimal(0))
    totals = {'current':zero(), 'previous':zero()}
    counts = {'current':0, 'previous':0}
    monthly = defaultdict(zero)
    categories = defaultdict(Decimal)
    for day, code, name, kind, group, debit, credit in rows:
        period = 'current' if start <= day <= end else 'previous'
        counts[period] += 1
        debit, credit = Decimal(str(debit or 0)), Decimal(str(credit or 0))
        if kind == 'Income':
            amount = credit - debit
            key = 'other_income' if code == '4300' or 'other income' in (group or '').lower() else 'revenue'
        else:
            amount = debit - credit
            key = 'cogs' if code in ('5000', '5100') or 'cost of goods' in (group or '').lower() else 'expenses'
        totals[period][key] += amount
        if period == 'current':
            monthly[day.strftime('%Y-%m')][key] += amount
            if key == 'expenses':
                categories[f'{code} · {name}'] += amount
    for bucket in [*totals.values(), *monthly.values()]:
        bucket['gross_profit'] = bucket['revenue'] - bucket['cogs']
        bucket['net_profit'] = bucket['gross_profit'] + bucket['other_income'] - bucket['expenses']
    if not counts['current']:
        return dict(available=False, reason='No posted income or expense entries in this period. Profit is unavailable, not zero.', charts=[])
    current, previous = totals['current'], totals['previous']
    keys = [('revenue','Operating revenue'),('cogs','Cost of goods sold'),('gross_profit','Gross profit'),
            ('other_income','Other income'),('expenses','Operating expenses'),('net_profit','Net profit / loss')]
    labels = month_labels(start, end)
    def rounded(value): return round(float(value), 2)
    # Populate absent months only after computing actual-month totals.
    monthly_values = {key:[rounded(monthly[label].get(key, 0)) for label in labels] for key, _ in keys}
    charts = [
        chart('Revenue, expenses and profit trend', labels,
            [(label, monthly_values[key]) for key, label in [('revenue','Revenue'),('expenses','Operating expenses'),('net_profit','Net profit / loss')]],
            kind='line', unit='money', currency=currency,
            note='Posted journal amounts in company currency. Profit also includes COGS and other income.', source='Posted ledger'),
        chart('Income statement', [label for _, label in keys],
            [('Current period',[rounded(current[key]) for key, _ in keys])], unit='money', currency=currency,
            note='Negative results and reversals are retained. Purchases are not assumed to be COGS.', source='Posted ledger'),
        chart('Operating expense accounts', list(categories),
            [('Posted expense',[rounded(value) for value in categories.values()])], unit='money', currency=currency,
            note='Net debit movement by expense account, excluding COGS. Credits reduce expenses.', source='Posted ledger'),
    ]
    if counts['previous']:
        charts.insert(1, chart('Performance against previous equal period', [label for _, label in keys],
            [('Current',[rounded(current[key]) for key, _ in keys]),
             ('Previous',[rounded(previous[key]) for key, _ in keys])], unit='money', currency=currency,
            note=f'Previous period: {previous_start} to {previous_end}.', source='Posted ledger'))
    return dict(available=True, currency=currency, current={k:rounded(v) for k,v in current.items()},
        previous={k:rounded(v) for k,v in previous.items()} if counts['previous'] else None,
        revenue_change=rounded((current['revenue']-previous['revenue'])/abs(previous['revenue'])*100) if counts['previous'] and previous['revenue'] else None,
        net_margin=rounded(current['net_profit']/current['revenue']*100) if current['revenue'] > 0 else None,
        charts=charts, reason='Posted journal basis; results depend on complete and correct accounting entries.')

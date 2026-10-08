"""Curated, company-scoped BI dashboard definitions and widget data."""
import json
import re
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy.exc import OperationalError, ProgrammingError
from customer_models import customer_db, Supplier, StockItem, Client, Expense
from .filters import BIValidationError, previous_period, parse_filters
from .queries import base_amount, expense_query, money, purchase_query, sales_query, stock_query
from .services import executive
from .semantic import DEFAULT as SEMANTIC_DEFAULT, validate_spec


class BIDashboard(customer_db.Model):
    __tablename__ = 'bi_custom_dashboards'
    id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    company_id = customer_db.Column(customer_db.String(20), nullable=False, index=True)
    owner_user_id = customer_db.Column(customer_db.String(20), nullable=False)
    title = customer_db.Column(customer_db.String(100), nullable=False)
    layout_json = customer_db.Column(customer_db.Text, nullable=False)
    visibility = customer_db.Column(customer_db.String(20), nullable=False, default='private')
    revision = customer_db.Column(customer_db.Integer, nullable=False, default=1)
    created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)


WIDGETS = {
    'metric': {'keys': ('net_sales', 'billed_sales', 'sales_invoices', 'active_customers',
                        'purchase_cost', 'purchase_total', 'expenses', 'receivables',
                        'payables', 'inventory_value', 'low_stock_items',
                        'gross_profit_estimate', 'net_profit_estimate')},
    'chart': {'keys': ('trend_sales', 'trend_purchases', 'trend_expenses',
                       'trend_comparison', 'sales_category_month', 'customer_performance',
                       'financial_bridge', 'top_customers', 'sales_countries',
                       'top_suppliers', 'stock_categories', 'custom')},
    'table': {'keys': ('top_customers', 'sales_countries', 'top_suppliers', 'stock_categories')},
    'text': {'keys': ('note',)},
    'filter': {'keys': ('date_range', 'client_id', 'employee_id', 'supplier_id', 'country', 'product_category', 'expense_category')},
}
BACKGROUNDS = ('canvas_light', 'canvas_cream', 'canvas_green', 'canvas_midnight',
               'canvas_gold', 'canvas_slate', 'canvas_dots')
ACCENTS = ('teal', 'gold', 'blue', 'purple', 'coral')
GRID_COLUMNS = 24
COLOR_PATTERN = re.compile(r'^#[0-9a-fA-F]{6}$')
STYLES = {
    'metric': ('bar', 'default', 'hero', 'sparkline', 'progress', 'gauge'),
    'table': ('bar', 'default', 'compact'),
    'text': ('bar', 'default'),
    'filter': ('default', 'bar'),
}
TREND_STYLES = ('bar', 'column', 'line', 'area', 'donut', 'pie', 'lollipop', 'step_line', 'radar', 'polar_area', 'spline_line', 'curved_area', 'grouped_bar')
CATEGORY_STYLES = ('bar', 'column', 'donut', 'pie', 'treemap', 'funnel', 'lollipop', 'radar', 'polar_area', 'grouped_bar')
CHART_STYLES = {
    'custom': ('bar', 'column', 'line', 'area', 'donut', 'pie', 'treemap', 'funnel',
               'lollipop', 'step_line', 'grouped_column', 'stacked_column', 'stacked_bar', 'combo', 'radar', 'polar_area', 'spline_line', 'curved_area', 'grouped_bar'),
    **{key: TREND_STYLES for key in ('trend_sales', 'trend_purchases', 'trend_expenses')},
    'trend_comparison': ('line', 'combo', 'grouped_column', 'stacked_column', 'stacked_bar', 'area', 'spline_line', 'curved_area', 'bar', 'column'),
    'sales_category_month': ('stacked_column', 'stacked_bar', 'grouped_column', 'combo'),
    'customer_performance': ('scatter', 'bar', 'column', 'grouped_bar'),
    'financial_bridge': ('waterfall', 'bar'),
    **{key: CATEGORY_STYLES for key in ('top_customers', 'sales_countries', 'top_suppliers', 'stock_categories')},
}
MAX_WIDGETS = 30
MAX_JSON_BYTES = 30000


def ensure_table(cdb):
    """Create only the new BI table for this tenant; never alter existing ERP tables."""
    try:
        BIDashboard.__table__.create(bind=cdb.get_bind(), checkfirst=True)
    except (OperationalError, ProgrammingError):
        # Two workers may race on the first request. Verify the table now exists
        # rather than suppressing unrelated connection / DDL errors.
        from sqlalchemy import inspect
        if not inspect(cdb.get_bind()).has_table(BIDashboard.__tablename__):
            raise


def validate_layout(payload):
    if not isinstance(payload, dict):
        raise BIValidationError('Dashboard must be a JSON object.')
    title = str(payload.get('title') or '').strip()
    if not title or len(title) > 100:
        raise BIValidationError('Dashboard title must be 1–100 characters.')
    visibility = payload.get('visibility', 'private')
    if visibility not in ('private', 'owner_team'):
        raise BIValidationError('Unsupported dashboard visibility.')
    raw = payload.get('widgets')
    if not isinstance(raw, list) or len(raw) > MAX_WIDGETS:
        raise BIValidationError('Dashboard must have at most 30 widgets.')
    background = payload.get('background', 'canvas_light')
    if background not in BACKGROUNDS:
        raise BIValidationError('Choose a built-in dashboard background.')
    grid_columns = payload.get('grid_columns', 12)
    if type(grid_columns) is not int or grid_columns not in (12, GRID_COLUMNS):
        raise BIValidationError('Unsupported canvas grid.')
    seen, widgets = set(), []
    for item in raw:
        if not isinstance(item, dict):
            raise BIValidationError('Invalid widget.')
        ident = str(item.get('id') or '')
        kind = item.get('type')
        metric = item.get('key')
        if not (1 <= len(ident) <= 40) or not all(c.isalnum() or c in '_-' for c in ident) or ident in seen:
            raise BIValidationError('Widgets need unique alphanumeric IDs.')
        seen.add(ident)
        if kind not in WIDGETS or metric not in WIDGETS[kind]['keys']:
            raise BIValidationError('Unsupported widget type or metric.')
        def integer(name, minimum, maximum):
            value = item.get(name)
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise BIValidationError(f'Widget {name} must be between {minimum} and {maximum}.')
            return value
        def coordinate(name, minimum, maximum):
            value = item.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not minimum <= value <= maximum:
                raise BIValidationError(f'Widget {name} must be between {minimum} and {maximum}.')
            return value
        x, y, w, h = coordinate('x', 0, grid_columns - 1), coordinate('y', 0, 400 if grid_columns == 24 else 200), coordinate('w', 1, grid_columns), coordinate('h', 1, 10 if grid_columns == 24 else 5)
        if x + w > grid_columns:
            raise BIValidationError('Widget extends beyond the canvas.')
        if grid_columns == 12:
            x, y, w, h = x * 2, y * 2, w * 2, h * 2
        label = str(item.get('title') or '').strip()[:80]
        note = str(item.get('text') or '')[:500] if kind == 'text' else ''
        style = item.get('style', 'bar')
        styles = CHART_STYLES.get(metric, ()) if kind == 'chart' else STYLES[kind]
        if style not in styles:
            raise BIValidationError('This visual cannot display the selected dataset.')
        accent = item.get('accent', 'teal')
        if accent not in ACCENTS:
            raise BIValidationError('Choose a built-in accent color.')
        legacy_surface = item.get('surface', 'paper')
        card_color = item.get('card_color', '#103b38' if legacy_surface == 'dark' else '#ffffff')
        text_color = item.get('text_color', '#ffffff' if legacy_surface == 'dark' else '#163a34')
        value_color = item.get('value_color', '#f4cb36' if legacy_surface == 'dark' else '#0c7864')
        if any(not isinstance(value, str) or not COLOR_PATTERN.fullmatch(value) for value in (card_color, text_color, value_color)):
            raise BIValidationError('Choose valid six-digit hex colors.')
        opacity = integer('opacity', 0, 100) if 'opacity' in item else (85 if legacy_surface == 'glass' else 100)
        font_size = integer('font_size', 10, 28) if 'font_size' in item else 12
        value_size = integer('value_size', 14, 48) if 'value_size' in item else 28
        compare = item.get('compare', 'previous_period' if kind == 'metric' else 'none')
        if compare not in ('none', 'previous_period'):
            raise BIValidationError('Unsupported comparison.')
        if compare != 'none' and kind == 'chart' and metric not in ('trend_sales', 'trend_purchases', 'trend_expenses', 'trend_comparison', 'custom'):
            raise BIValidationError('Previous-period comparison is not available for this chart dataset.')
        if compare != 'none' and kind not in ('metric', 'chart'):
            raise BIValidationError('Comparison requires a KPI or supported chart.')
        chart_defaults = {
            'subtitle': '', 'x_title': '', 'y_title': '', 'show_axes': True,
            'show_grid': True, 'show_values': False, 'show_legend': True,
            'show_markers': True, 'number_format': 'compact', 'label_mode': 'percent',
        }
        chart_options = {}
        for option, default in chart_defaults.items():
            value = item.get(option, default)
            if option in ('subtitle', 'x_title', 'y_title'):
                if not isinstance(value, str) or len(value) > 80:
                    raise BIValidationError(f'Chart {option} must be text of at most 80 characters.')
            elif option in ('show_axes', 'show_grid', 'show_values', 'show_legend', 'show_markers'):
                if type(value) is not bool:
                    raise BIValidationError(f'Chart {option} must be on or off.')
            elif option == 'number_format' and value not in ('compact', 'full'):
                raise BIValidationError('Unsupported chart number format.')
            elif option == 'label_mode' and value not in ('percent', 'value', 'both', 'category', 'category_value', 'category_percent'):
                raise BIValidationError('Unsupported chart label mode.')
            chart_options[option] = value
        for option, default, minimum, maximum in (
            ('chart_scale', 100, 50, 150), ('donut_hole', 60, 20, 85),
            ('data_label_font_size', 14, 8, 32), ('axis_font_size', 10, 8, 32),
            ('legend_font_size', 11, 8, 32), ('subtitle_font_size', 11, 8, 32),
        ):
            value = item.get(option, default)
            if type(value) not in (int, float) or not minimum <= value <= maximum:
                raise BIValidationError(f'{option} must be between {minimum} and {maximum}.')
            chart_options[option] = value
        axis_mode = item.get('axis_label_mode', 'wrap')
        if axis_mode not in ('wrap', 'abbreviate', 'truncate'):
            raise BIValidationError('Unsupported axis label mode.')
        chart_options['axis_label_mode'] = axis_mode
        position = item.get('label_position', 'auto')
        if position not in ('auto', 'inside', 'outside', 'center'):
            raise BIValidationError('Unsupported data label position.')
        chart_options['label_position'] = position
        for option in ('data_label_color', 'axis_color', 'legend_color', 'subtitle_color', 'chart_color', 'grid_color'):
            value = item.get(option)
            if value is not None:
                if not isinstance(value, str) or not COLOR_PATTERN.fullmatch(value):
                    raise BIValidationError('Chart colors must be six-digit hex colors.')
                chart_options[option] = value
        for option in ('category_colors', 'series_colors'):
            values = item.get(option, {})
            if (not isinstance(values, dict) or len(values) > 200
                    or any(not isinstance(k, str) or len(k) > 200 or not isinstance(v, str)
                           or not COLOR_PATTERN.fullmatch(v) for k, v in values.items())):
                raise BIValidationError('Invalid chart color overrides.')
            chart_options[option] = values
        semantic_options = validate_spec(item) if kind == 'chart' and metric == 'custom' else {}
        metric_options = {}
        if kind == 'metric':
            keys = item.get('metric_keys', [metric])
            if (not isinstance(keys, list) or not 1 <= len(keys) <= 6
                    or any(not isinstance(k, str) or k not in WIDGETS['metric']['keys'] for k in keys)
                    or len(set(keys)) != len(keys) or keys[0] != metric):
                raise BIValidationError('Choose one to six distinct KPI metrics with the primary metric first.')
            metric_options['metric_keys'] = keys
        target = item.get('target', 0)
        if isinstance(target, bool) or not isinstance(target, (int, float)) or not 0 <= target <= 1_000_000_000_000:
            raise BIValidationError('KPI target must be a non-negative number.')
        widgets.append({'id': ident, 'type': kind, 'key': metric, 'title': label,
                        'x': x, 'y': y, 'w': w, 'h': h, 'style': style, 'text': note,
                        'accent': accent, 'card_color': card_color.lower(), 'opacity': opacity,
                        'text_color': text_color.lower(), 'value_color': value_color.lower(),
                        'font_size': font_size, 'value_size': value_size, 'compare': compare,
                        'target': round(float(target), 2), **chart_options, **semantic_options, **metric_options})
    for i, left in enumerate(widgets):
        for right in widgets[i + 1:]:
            if left['x'] < right['x'] + right['w'] and right['x'] < left['x'] + left['w'] and left['y'] < right['y'] + right['h'] and right['y'] < left['y'] + left['h']:
                raise BIValidationError('Widgets overlap on the canvas.')
    filters = payload.get('filters', {})
    allowed_filters = {'from_date', 'to_date', 'employee_id', 'country', 'client_id',
                       'supplier_id', 'product_category', 'expense_category'}
    if not isinstance(filters, dict) or set(filters) - allowed_filters:
        raise BIValidationError('Unsupported dashboard filters.')
    if any(not isinstance(v, str) or len(v) > 200 for v in filters.values()):
        raise BIValidationError('Dashboard filter values must be text of at most 200 characters.')
    if filters:
        focus_field(parse_filters(filters, '', date.today()))
    serial = json.dumps({'background': background, 'grid_columns': GRID_COLUMNS, 'widgets': widgets,
                         'filters': filters}, ensure_ascii=False, separators=(',', ':'))
    if len(serial.encode('utf-8')) > MAX_JSON_BYTES:
        raise BIValidationError('Dashboard is too large.')
    return title, visibility, serial


def serialize(row):
    stored = json.loads(row.layout_json)
    if isinstance(stored, list):  # Phase 5 dashboards saved before canvas themes
        stored = {'background': 'canvas_light', 'widgets': stored}
    legacy_grid = stored.get('grid_columns') != GRID_COLUMNS
    widgets = []
    for old in stored['widgets']:
        widget = dict(old)
        if legacy_grid:
            for field in ('x', 'y', 'w', 'h'):
                widget[field] = widget[field] * 2
        legacy_surface = widget.pop('surface', 'paper')
        widget.setdefault('card_color', '#103b38' if legacy_surface == 'dark' else '#ffffff')
        widget.setdefault('opacity', 85 if legacy_surface == 'glass' else 100)
        widget.setdefault('text_color', '#ffffff' if legacy_surface == 'dark' else '#163a34')
        widget.setdefault('value_color', '#f4cb36' if legacy_surface == 'dark' else '#0c7864')
        widget.setdefault('font_size', 12)
        widget.setdefault('value_size', 28)
        widget.setdefault('compare', 'previous_period' if widget.get('type') == 'metric' else 'none')
        if widget.get('type') == 'chart' and widget.get('key') == 'custom':
            for key, value in SEMANTIC_DEFAULT.items():
                widget.setdefault(key, value)
        widgets.append(widget)
    return {'id': row.id, 'title': row.title, 'visibility': row.visibility,
            'revision': row.revision, 'widgets': widgets, 'grid_columns': GRID_COLUMNS,
            'background': stored.get('background', 'canvas_light'),
            'filters': stored.get('filters', {}),
            'owner_user_id': row.owner_user_id,
            'updated_at': row.updated_at.isoformat() if row.updated_at else None}


def can_access(row, company_id, user):
    return (row.company_id == company_id and
            (row.owner_user_id == user.get('user_id') or row.visibility == 'owner_team' or user.get('role') == 'super_admin'))


FOCUS_DOMAINS = {
    'employee_id': frozenset(('sales', 'sales_items', 'purchase', 'purchase_items', 'expenses', 'finance', 'hr')),
    'country': frozenset(('sales', 'sales_items', 'purchase', 'purchase_items')),
    'client_id': frozenset(('sales', 'sales_items')),
    'supplier_id': frozenset(('purchase', 'purchase_items')),
    'product_category': frozenset(('sales', 'sales_items', 'purchase', 'purchase_items', 'stock')),
    'expense_category': frozenset(('expenses',)),
}
METRIC_DOMAINS = {
    **{key: 'sales' for key in ('net_sales', 'billed_sales', 'sales_invoices', 'active_customers', 'receivables')},
    **{key: 'purchase' for key in ('purchase_cost', 'purchase_total', 'payables')},
    'expenses': 'expenses', 'inventory_value': 'stock', 'low_stock_items': 'stock',
}
CHART_DOMAINS = {
    **{key: 'sales' for key in ('trend_sales', 'top_customers', 'sales_countries',
                                'customer_performance', 'sales_category_month')},
    **{key: 'purchase' for key in ('trend_purchases', 'top_suppliers')},
    'trend_expenses': 'expenses', 'stock_categories': 'stock',
}


def focus_field(filters):
    chosen = [key for key in FOCUS_DOMAINS if getattr(filters, key)]
    if len(chosen) > 1:
        raise BIValidationError('Choose one business filter at a time in the dashboard builder.')
    return chosen[0] if chosen else None


def dataset(cdb, filters, can, currency, today):
    """Whitelisted datasets. The layout never contains SQL or column names."""
    focus = focus_field(filters)
    base = executive(cdb, filters, can, currency, today)
    suppliers = {x.id: x.name for x in cdb.query(Supplier).filter_by(company_id=filters.company_id).all()}
    supplier_totals = {}
    if can('purchase', 'view'):
        for invoice in purchase_query(cdb, filters, filters.from_date, filters.to_date).all():
            name = suppliers.get(invoice.supplier_id) or invoice.supplier_name or 'Unspecified'
            supplier_totals[name] = supplier_totals.get(name, Decimal('0')) + base_amount(invoice, 'base_subtotal', 'subtotal', currency)
    stock_totals = {}
    if can('stock', 'view'):
        for item in stock_query(cdb, filters).all():
            category = item.category or 'Uncategorised'
            value = money(item.quantity) * money(item.avg_purchase_rate or item.last_purchase_rate or item.purchase_rate or item.unit_price)
            stock_totals[category] = stock_totals.get(category, Decimal('0')) + value
    top = lambda group: [{'name': key, 'value': round(float(value), 2)} for key, value in sorted(group.items(), key=lambda pair: -pair[1])[:10]]
    sales_category_month = {}
    customer_performance = {}
    if can('customer_invoices', 'view') or can('invoices', 'view'):
        clients = {x.id: x.name for x in cdb.query(Client).filter_by(company_id=filters.company_id).all()}
        for invoice in sales_query(cdb, filters, filters.from_date, filters.to_date).all():
            amount = base_amount(invoice, 'base_subtotal', 'subtotal', currency)
            month = invoice.invoice_date.strftime('%Y-%m')
            category = invoice.invoice_category or 'Other'
            if category not in ('product_sale', 'workshop_repair'):
                category = 'Other'
            bucket = sales_category_month.setdefault(month, {'month': month, 'product_sale': Decimal('0'),
                                                               'workshop_repair': Decimal('0'), 'Other': Decimal('0')})
            bucket[category] += amount
            client_name = clients.get(invoice.client_id) or invoice.client_name or 'Unlinked customer'
            client_key = str(invoice.client_id) if invoice.client_id else f'unlinked:{client_name}'
            customer = customer_performance.setdefault(client_key, {'name': client_name, 'value': Decimal('0'), 'count': 0})
            customer['value'] += amount
            customer['count'] += 1
    category_series = [{'month': month, **{key: round(float(value), 2) for key, value in values.items() if key != 'month'}}
                       for month, values in sorted(sales_category_month.items())]
    customer_series = [{'name': x['name'], 'value': round(float(x['value']), 2), 'count': x['count'], 'key': key}
                       for key, x in sorted(customer_performance.items(), key=lambda pair: -pair[1]['value'])[:20]]
    period = base['period']
    bridge = [{'name': 'Net sales', 'value': period.get('net_sales', 0)},
              {'name': 'Purchases (estimate)', 'value': -period.get('purchase_cost', 0)},
              {'name': 'Expenses', 'value': -period.get('expenses', 0)}]
    result = {'base_currency': currency, 'filters': base['filters'],
            'period': base['period'], 'live': base['live'], 'comparisons': base['comparisons'],
            'trend': base['trend'], 'top_customers': base['top_customers'],
            'sales_countries': base['countries'], 'top_suppliers': top(supplier_totals),
            'stock_categories': top(stock_totals),
            'sales_category_month': category_series, 'customer_performance': customer_series,
            'financial_bridge': bridge,
            'warnings': base['warnings'] + ['Stock categories are current values; they do not follow the selected date range.']}
    result['focus'] = focus
    result['not_applicable'] = []
    if focus:
        allowed = FOCUS_DOMAINS[focus]
        result['not_applicable'] = [key for key, domain in {**METRIC_DOMAINS, **CHART_DOMAINS}.items()
                                    if domain not in allowed]
        # Purchase cost is not matched historical COGS. Combining a focused
        # sales cohort with unrelated purchase/expense records invents profit.
        result['not_applicable'] += ['gross_profit_estimate', 'net_profit_estimate',
                                     'financial_bridge', 'trend_comparison']
        if focus == 'product_category':
            result['not_applicable'] += ['receivables', 'payables']
            result['warnings'].append('Category sales and purchases use full invoice subtotals when an invoice contains a matching item. They are not category line totals.')
        if focus == 'country':
            result['warnings'].append('Country reflects current customer and supplier master addresses, not historical transaction destinations.')
        result['warnings'].append('Other business domains are unavailable under this filter; profit estimates are hidden.')
        result['not_applicable'] = sorted(set(result['not_applicable']))
        for key in result['not_applicable']:
            result['period'].pop(key, None)
            result['live'].pop(key, None)
            result['comparisons'].pop(key, None)
            if key in result and isinstance(result[key], list):
                result[key] = []
        for row in result['trend']:
            for key, domain in (('sales', 'sales'), ('purchases', 'purchase'), ('expenses', 'expenses')):
                if domain not in allowed:
                    row.pop(key, None)
    return result


DRILL_DATASETS = frozenset(('trend_sales', 'trend_purchases', 'trend_expenses', 'top_customers',
                            'sales_countries', 'top_suppliers', 'stock_categories',
                            'customer_performance', 'sales_category_month'))


def drill_records(cdb, filters, can, currency, chart, group, series=None, period=None):
    """Bounded, tenant-scoped source rows behind a supported chart group."""
    focus = focus_field(filters)
    if chart not in DRILL_DATASETS or not isinstance(group, str) or not 1 <= len(group) <= 180:
        raise BIValidationError('This chart group cannot open source records.')
    domain = CHART_DOMAINS[chart]
    if focus and domain not in FOCUS_DOMAINS[focus]:
        raise BIValidationError('This chart does not apply to the selected business filter.')
    permission = {'sales': can('customer_invoices', 'view') or can('invoices', 'view'),
                  'purchase': can('purchase', 'view'), 'expenses': can('expenses', 'view'),
                  'stock': can('stock', 'view')}
    if not permission[domain]:
        raise BIValidationError('You do not have access to these source records.')
    if period not in (None, 'selected', 'previous') or (period and chart not in ('trend_sales', 'trend_purchases', 'trend_expenses')):
        raise BIValidationError('Unsupported comparison period.')
    start, end = (previous_period(filters) if period == 'previous' else (filters.from_date, filters.to_date))
    if period:
        if group != ('Previous period' if period == 'previous' else 'Selected period'):
            raise BIValidationError('Invalid period group.')
    elif chart in ('trend_sales', 'trend_purchases', 'trend_expenses', 'sales_category_month'):
        if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', group):
            raise BIValidationError('Invalid month group.')
    if chart == 'sales_category_month' and series not in ('product_sale', 'workshop_repair', 'Other'):
        raise BIValidationError('Choose a sales category series.')
    if chart != 'sales_category_month' and series:
        raise BIValidationError('Unsupported series.')
    clients = {row.id: row for row in cdb.query(Client).filter_by(company_id=filters.company_id).all()} if domain == 'sales' else {}
    suppliers = {row.id: row.name for row in cdb.query(Supplier).filter_by(company_id=filters.company_id).all()} if domain == 'purchase' else {}
    if domain == 'sales':
        source = sales_query(cdb, filters, start, end).all()
        def matches(row):
            name = clients[row.client_id].name if row.client_id in clients else row.client_name or 'Unlinked customer'
            country = ((clients[row.client_id].country or 'Unspecified').strip() or 'Unspecified') if row.client_id in clients else None
            category = row.invoice_category if row.invoice_category in ('product_sale', 'workshop_repair') else 'Other'
            return (bool(period) or chart in ('trend_sales', 'sales_category_month') and row.invoice_date.strftime('%Y-%m') == group and
                    (chart != 'sales_category_month' or category == series) or
                    chart == 'top_customers' and name == group or chart == 'sales_countries' and country == group or
                    chart == 'customer_performance' and (str(row.client_id) if row.client_id else f'unlinked:{name}') == group)
        matched = [r for r in source if matches(r)]
        def record(r):
            return {'id': r.id, 'number': r.invoice_number, 'date': r.invoice_date.isoformat(),
                    'party': clients[r.client_id].name if r.client_id in clients else r.client_name or 'Unlinked customer',
                    'amount': round(float(base_amount(r, 'base_subtotal', 'subtotal', currency)), 2)}
    elif domain == 'purchase':
        source = purchase_query(cdb, filters, start, end).all()
        matched = [r for r in source if period or chart == 'trend_purchases' and r.date.strftime('%Y-%m') == group or
                   chart == 'top_suppliers' and (suppliers.get(r.supplier_id) or r.supplier_name or 'Unspecified') == group]
        def record(r):
            return {'id': r.id, 'number': r.invoice_number or r.invoice_id, 'date': r.date.isoformat(),
                    'party': suppliers.get(r.supplier_id) or r.supplier_name or 'Unspecified',
                    'amount': round(float(base_amount(r, 'base_subtotal', 'subtotal', currency)), 2)}
    elif domain == 'expenses':
        source = expense_query(cdb, filters, start, end).all()
        matched = [r for r in source if period or r.date.strftime('%Y-%m') == group]
        def record(r):
            return {'id': r.id, 'number': r.reference or f'Expense #{r.id}', 'date': r.date.isoformat(),
                    'party': r.category, 'amount': round(float(money(r.amount)), 2)}
    else:
        source = stock_query(cdb, filters).all()
        matched = [r for r in source if (r.category or 'Uncategorised') == group]
        def record(r):
            value = money(r.quantity) * money(r.avg_purchase_rate or r.last_purchase_rate or r.purchase_rate or r.unit_price)
            return {'id': r.id, 'number': r.code, 'date': '', 'party': r.name,
                    'amount': round(float(value), 2)}
    rows = [record(r) for r in matched]
    rows.sort(key=lambda r: (r['date'], r['id']), reverse=True)
    return {'chart': chart, 'group': group, 'currency': currency, 'count': len(rows),
            'total': round(sum(r['amount'] for r in rows), 2), 'rows': rows[:100],
            'truncated': len(rows) > 100, 'snapshot': domain == 'stock'}

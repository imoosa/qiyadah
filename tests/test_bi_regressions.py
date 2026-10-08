"""BI regressions against an isolated in-memory warehouse."""
import json
import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from bi import builder, predictive, semantic, warehouse as wh
from bi.filters import BIValidationError
from bi.predictive_routes import register_predictive_routes
from bi.routes import register_bi_routes


class BIRegressionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        wh.M.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.execute(wh.STATE.insert().values(company_id='A', currency='INR', last_success=datetime.utcnow()))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_dashboard_filters_round_trip(self):
        filters = {'from_date': '2026-01-01', 'to_date': '2026-09-25', 'client_id': '7'}
        title, visibility, layout = builder.validate_layout({'title': 'Sales', 'widgets': [], 'filters': filters})
        row = SimpleNamespace(id=1, title=title, visibility=visibility, revision=1, layout_json=layout,
                              owner_user_id='owner', updated_at=None)
        self.assertEqual(builder.serialize(row)['filters'], filters)

    def test_dashboard_rejects_invalid_filters(self):
        for filters in ({'company': 'B'}, {'from_date': 'invalid'}, {'client_id': '0'},
                        {'country': 'IN', 'supplier_id': '2'}, {'country': []}):
            with self.subTest(filters=filters), self.assertRaises(BIValidationError):
                builder.validate_layout({'title': 'Sales', 'widgets': [], 'filters': filters})

    def test_legacy_dashboard_filters(self):
        row = SimpleNamespace(id=1, title='Old', visibility='private', revision=1,
                              layout_json='[]', owner_user_id='owner', updated_at=None)
        self.assertEqual(builder.serialize(row)['filters'], {})

    def test_months_and_horizon(self):
        series = predictive._series([{'day': date(2026, 1, 1), 'value': 100},
                                     {'day': date(2026, 9, 1), 'value': 999}], 'day', 'value', date(2026, 9, 25))
        self.assertEqual(len(series), 8)
        self.assertEqual(series[-1]['actual'], 0)
        result = predictive.forecast(series, 12)
        self.assertEqual(len(result['forecast']), 12)
        self.assertEqual(result['forecast'][0]['month'], '2026-09')
        self.assertEqual(result['forecast'][-1]['month'], '2027-08')

    def test_negative_cash_forecast(self):
        series = [{'month': f'2026-{m:02}', 'actual': -50} for m in range(1, 9)]
        self.assertEqual(predictive.forecast(series, allow_negative=True)['forecast'][0]['value'], -50)

    def test_future_records_negative_stock_and_new_customer(self):
        self.db.execute(wh.PRODUCT.insert().values(company_id='A', source_id='1', name='Part', quantity=-5, reorder_level=2))
        self.db.execute(wh.INVENTORY.insert(), [dict(company_id='A', source_id=str(i), event_date=d,
            product_id='1', movement='OUT', quantity=-10) for i,d in enumerate([date(2026,6,1),date(2026,9,1),date(2027,1,1)])])
        self.db.execute(wh.CUSTOMER.insert().values(company_id='A', source_id='1', name='New'))
        self.db.execute(wh.SALES.insert(), [dict(company_id='A', source_id=str(i), event_date=d, amount=100,
            customer_id=c) for i,(d,c) in enumerate([(date(2025,1,1),'old'),(date(2026,8,1),'1'),(date(2026,9,1),'1'),(date(2027,1,1),'1')])])
        self.db.commit()
        result = predictive.build(self.db, 'A', date(2026,9,25))
        stock = result['inventory_demand'][0]
        self.assertGreater(stock['daily_demand'], 0)
        self.assertEqual(stock['stockout_in_days'], 0)
        self.assertEqual(result['customer_risk'][0]['invoices'], 2)
        self.assertEqual(result['customer_risk'][0]['indicator'], 'insufficient_history')

    def test_failed_first_refresh_visible_and_tenant_isolated(self):
        self.db.execute(wh.RUNS.insert().values(company_id='B', started_at=datetime.utcnow(),status='failed', error='source unavailable'))
        self.db.commit()
        self.assertEqual(wh.status(self.db,'B')['runs'][0]['error'], 'source unavailable')
        self.assertEqual(wh.status(self.db,'A')['runs'], [])
        with self.assertRaises(ValueError): wh.require_ready(self.db,'B')

    def test_stale_snapshot_and_dimension_counts(self):
        self.db.execute(wh.STATE.update().values(last_success=datetime.utcnow()-timedelta(days=2)))
        self.db.commit()
        summary=wh.summary(self.db,'A')
        self.assertIn('24 hours', summary['warning'])
        self.assertIn('dim_product', summary['row_counts'])
        self.assertEqual(len(summary['row_counts']), 13)

    def test_incremental_writes_and_tenant_isolation(self):
        rows=[('1', {'name':'First'})]
        self.assertEqual(wh._sync(self.db,wh.CUSTOMER,'A',rows)['inserted'],1)
        self.assertEqual(wh._sync(self.db,wh.CUSTOMER,'A',rows)['updated'],0)
        self.assertEqual(wh._sync(self.db,wh.CUSTOMER,'A',[('1',{'name':'Changed'})])['updated'],1)
        wh._sync(self.db,wh.CUSTOMER,'B',rows)
        self.assertEqual(wh._sync(self.db,wh.CUSTOMER,'A',[])['deleted'],1)
        self.assertEqual(self.db.execute(wh.CUSTOMER.select()).scalar() is not None,True)

    def test_warehouse_dates_and_currency_fallback(self):
        with self.assertRaises(ValueError):
            wh._day(None)
        self.assertEqual(wh._day(datetime(2026, 1, 3, 12)), date(2026, 1, 3))
        line = SimpleNamespace(total_amount=100, base_total_amount=0)
        invoice = SimpleNamespace(currency='USD', exchange_rate=80)
        self.assertEqual(wh._line_base(line, invoice, 'INR'), 8000)
        invoice.exchange_rate = -1
        self.assertEqual(wh._line_base(line, invoice, 'INR'), 100)

    def test_demand_window_has_exactly_ninety_days(self):
        today = date(2026, 9, 25)
        self.db.execute(wh.PRODUCT.insert().values(company_id='A', source_id='1', name='Part', quantity=10, reorder_level=0))
        self.db.execute(wh.INVENTORY.insert(), [
            dict(company_id='A', source_id='old', event_date=today-timedelta(days=90), product_id='1', movement='OUT', quantity=-900),
            dict(company_id='A', source_id='current', event_date=today, product_id='1', movement='OUT', quantity=-90)])
        self.db.commit()
        stock = predictive.build(self.db, 'A', today)['inventory_demand'][0]
        self.assertEqual(stock['daily_demand'], 1)
        self.assertEqual(stock['stockout_in_days'], 10)
        self.assertEqual(stock['purchase_requirement_units'], 4)

    def test_observed_stock_with_no_recent_demand(self):
        today = date(2026, 9, 25)
        self.db.execute(wh.PRODUCT.insert().values(company_id='A', source_id='1', name='Slow stock', quantity=5, reorder_level=2))
        self.db.execute(wh.INVENTORY.insert().values(company_id='A', source_id='1', event_date=today-timedelta(days=120), product_id='1', movement='IN', quantity=5))
        self.db.commit()
        stock = predictive.build(self.db, 'A', today)['inventory_demand'][0]
        self.assertEqual(stock['status'], 'ready')
        self.assertEqual(stock['daily_demand'], 0)
        self.assertIsNone(stock['stockout_in_days'])
        self.assertEqual(stock['purchase_requirement_units'], 0)

    def test_api_input_errors(self):
        app=Flask(__name__)
        register_predictive_routes(app,lambda f:f,lambda *args:lambda f:f,lambda:self.db,
            lambda:'A',lambda:{'role':'owner'},lambda _:SimpleNamespace(currency='INR'))
        client=app.test_client()
        for query in ('lead_days=0','horizon=13','horizon=bad'):
            self.assertEqual(client.get('/api/bi/v1/predictive?'+query).status_code,400)
        self.assertEqual(client.get('/api/bi/v1/predictive?horizon=6').status_code,200)

    def test_multiple_metrics_survive_layout_round_trip(self):
        widgets = [dict(id='kpi', type='metric', key='net_sales', metric_keys=['net_sales', 'sales_invoices'],
                        x=0, y=0, w=6, h=4, style='hero'),
                   dict(id='chart', type='chart', key='custom', x=6, y=0, w=12, h=6,
                        style='stacked_bar', semantic_measures=['subtotal', 'tax_amount'])]
        title, visibility, layout = builder.validate_layout(dict(title='Metrics', widgets=widgets, grid_columns=24))
        row = SimpleNamespace(id=1, title=title, visibility=visibility, layout_json=layout,
                              revision=1, owner_user_id='1', updated_at=None)
        saved = builder.serialize(row)['widgets']
        self.assertEqual(saved[0]['metric_keys'], ['net_sales', 'sales_invoices'])
        self.assertEqual(saved[1]['semantic_measures'], ['subtotal', 'tax_amount'])
        self.assertEqual(saved[1]['style'], 'stacked_bar')

    def test_multiple_measures_use_same_groups_and_correct_values(self):
        rows = [SimpleNamespace(invoice_date=date(2026, 1, 2), subtotal=100, tax_amount=18, currency='INR'),
                SimpleNamespace(invoice_date=date(2026, 1, 3), subtotal=200, tax_amount=36, currency='INR')]
        filters = SimpleNamespace(from_date=date(2026, 1, 1), to_date=date(2026, 2, 28),
                                  product_category=None, country=None)
        with patch.object(semantic, '_rows', return_value=rows), patch.object(semantic, '_lookup', return_value={}), patch.object(semantic, '_focus', return_value=False):
            result = semantic.visual(None, filters, lambda *a: True, 'INR',
                                     dict(semantic_measures=['subtotal', 'tax_amount', 'count']))
            self.assertEqual(result['rows'][0]['values'], {'subtotal': 300, 'tax_amount': 54, 'count': 2})
            self.assertEqual(result['rows'][1]['values'], {'subtotal': 0, 'tax_amount': 0, 'count': 0})
            averaged = semantic.visual(None, filters, lambda *a: True, 'INR',
                                       dict(semantic_measures=['subtotal', 'count'], semantic_aggregation='avg'))
            self.assertEqual(averaged['rows'][0]['values'], {'subtotal': 150, 'count': 2})
            self.assertEqual([s['value_kind'] for s in result['series']], ['money', 'money', 'number'])

    def test_invalid_measure_selections_are_rejected(self):
        for values in ([], ['subtotal', 'subtotal'], ['quantity'], ['tax_amount', 'subtotal'], 'subtotal'):
            with self.subTest(values=values), self.assertRaises(BIValidationError):
                semantic.validate_spec(dict(semantic_measures=values))

    def test_multi_measure_api_and_dashboard_save(self):
        app = Flask(__name__)
        app.secret_key = 'bi-tests'
        register_bi_routes(app, lambda f:f, lambda *a:lambda f:f, lambda:self.db,
                           lambda:'A', lambda:{'role':'owner', 'user_id':'owner'},
                           lambda _:SimpleNamespace(currency='INR'), lambda *a:True, lambda:date(2026,9,25))
        client = app.test_client()
        with patch('bi.routes.semantic_visual', side_effect=lambda *args:semantic.validate_spec(args[-1])):
            response = client.get('/api/bi/v1/builder/visual', query_string=[
                ('semantic_measures','subtotal'), ('semantic_measures','count')])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['semantic_measures'], ['subtotal', 'count'])
        payload = dict(title='Multiple KPIs', grid_columns=24, widgets=[
            dict(id='kpi', type='metric', key='net_sales', metric_keys=['net_sales', 'sales_invoices'],
                 x=0, y=0, w=8, h=4, style='default')])
        self.assertEqual(client.post('/api/bi/v1/builder/dashboards', json=payload).status_code,403)
        with client.session_transaction() as session:
            session['bi_builder_csrf'] = 'test-csrf'
        response = client.post('/api/bi/v1/builder/dashboards', json=payload, headers={'X-BI-CSRF':'test-csrf'})
        self.assertEqual(response.status_code,201)
        saved = client.get('/api/bi/v1/builder/dashboards/'+str(response.json['id']))
        self.assertEqual(saved.json['widgets'][0]['metric_keys'], ['net_sales','sales_invoices'])

if __name__ == '__main__': unittest.main()

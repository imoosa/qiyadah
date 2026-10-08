"""Workspace summaries and navigation against an isolated database."""
from datetime import date, timedelta
from functools import wraps
from types import SimpleNamespace
import unittest

from flask import Flask, abort, session
from jinja2 import ChoiceLoader, DictLoader
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from customer_models import StockItem, PurchaseOrder, SalesOrder, DeliveryChallan
from supply_chain_workspace import SUPPLY_NAV, supply_summary, register_supply_chain_workspace


class SupplyChainTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        for model in (StockItem, PurchaseOrder, SalesOrder, DeliveryChallan):
            model.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.company = 'A'
        self.permissions = {'stock', 'purchase_orders', 'sales_orders', 'delivery_challans'}
        self.today = date(2026, 10, 5)
        self.app = Flask(__name__, template_folder='../templates')
        self.app.config.update(TESTING=True, SECRET_KEY='test')
        self.app.jinja_loader = ChoiceLoader([DictLoader({'base.html': '{% block extra_style %}{% endblock %}{% block content %}{% endblock %}'}), self.app.jinja_loader])
        for _, entries in SUPPLY_NAV:
            for _, endpoint, _ in entries:
                self.app.add_url_rule('/existing/' + endpoint, endpoint, lambda: '')
        self.app.add_url_rule('/purchase-order/<int:po_id>', 'purchase_order_view', lambda po_id: '')
        for endpoint in ('select_company', 'finance_workspace', 'apps_hub'):
            self.app.add_url_rule('/' + endpoint, endpoint, lambda: '')

        def login_required(f):
            @wraps(f)
            def wrapped(*args, **kwargs):
                if not session.get('user'):
                    abort(401)
                return f(*args, **kwargs)
            return wrapped

        register_supply_chain_workspace(self.app, login_required, lambda: self.db,
            lambda: self.company, self.can,
            lambda cid: SimpleNamespace(company_name='Qiyadah', branch_name='Dubai'), lambda: self.today)
        self.client = self.app.test_client()
        with self.client.session_transaction() as state:
            state['user'] = {'role': 'manager'}

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def can(self, permission, action='view'):
        return permission in self.permissions

    def test_summary_is_company_scoped_and_honors_zero_reorder(self):
        for company, code, qty, reorder in [('A', 'ZERO', 0, 0), ('A', 'OK', 2, 0), ('A', 'LOW', 2, 3), ('B', 'PRIVATE', -9, 5)]:
            self.db.add(StockItem(company_id=company, code=code, name=code, quantity=qty, reorder_level=reorder))
        for idx, status in enumerate(('Sent', 'Draft', 'Cancelled', 'Received', ' Invoiced ', 'Confirmed')):
            self.db.add(PurchaseOrder(company_id='A', po_number=f'PO{idx}', status=status,
                                      expected_delivery_date=self.today - timedelta(days=1)))
        self.db.add(PurchaseOrder(company_id='B', po_number='SECRET', status='Sent', expected_delivery_date=self.today-timedelta(days=1)))
        self.db.commit()
        result = supply_summary(self.db, 'A', self.can, self.today)
        metrics = {m['label']: m['value'] for m in result['metrics']}
        self.assertEqual(metrics['Stock items'], 3)
        self.assertEqual(metrics['At or below reorder level'], 2)
        self.assertEqual(metrics['Open purchase orders'], 2)
        self.assertEqual(metrics['Overdue purchase orders'], 2)
        self.assertEqual([r.code for r in result['low_stock']], ['ZERO', 'LOW'])

    def test_no_queries_for_unauthorized_records(self):
        class NoQueries:
            def query(self, *args):
                raise AssertionError('Unauthorized query')
        self.assertEqual(supply_summary(NoQueries(), 'A', lambda *args: False, self.today)['metrics'], [])

    def test_route_renders_real_data_and_remembers_company_workspace(self):
        self.db.add(StockItem(company_id='A', code='ITEM', name='<b>Widget</b>', quantity=0))
        self.db.add(PurchaseOrder(company_id='A', po_number='PO1', status='Sent', expected_delivery_date=self.today-timedelta(days=1)))
        self.db.commit()
        response = self.client.get('/supply-chain')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'&lt;b&gt;Widget&lt;/b&gt;', response.data)
        self.assertIn(b'Dubai', response.data)
        self.assertIn(b'/purchase-order/1', response.data)
        self.assertNotIn(b'>Suppliers', response.data)
        with self.client.session_transaction() as state:
            self.assertEqual(state['workspace_by_company'], {'A': 'supply_chain'})
        self.company = 'B'
        self.client.get('/supply-chain')
        with self.client.session_transaction() as state:
            self.assertEqual(state['workspace_by_company'], {'A': 'supply_chain', 'B': 'supply_chain'})

    def test_access_checks_do_not_change_workspace(self):
        self.permissions.clear()
        self.assertEqual(self.client.get('/supply-chain').status_code, 403)
        self.permissions.add('stock')
        self.app.extensions['module_access'] = lambda module: False
        self.assertEqual(self.client.get('/supply-chain').status_code, 403)
        with self.client.session_transaction() as state:
            self.assertNotIn('workspace_by_company', state)
            state.clear()
        self.assertEqual(self.client.get('/supply-chain').status_code, 401)

    def test_production_features_render_inside_supply_chain(self):
        self.app.extensions['module_access'] = lambda module: True
        response = self.client.get('/supply-chain')
        self.assertEqual(response.status_code, 200)
        for feature in (b'pane-orders', b'pane-workflow', b'newOrderModal',
                        b'orderDetailModal', b'href="#quality"', b'href="#credit"'):
            self.assertIn(feature, response.data)
        self.assertNotIn(b'href="/order-erp', response.data)
        self.app.extensions['module_access'] = lambda module: module == 'core'
        self.assertEqual(self.client.get('/supply-chain').status_code, 403)

    def test_production_only_access_and_legacy_bookmarks(self):
        from order_erp_routes import register_order_erp_routes
        self.permissions.clear()
        self.app.extensions['module_access'] = lambda module: module == 'orderflow'
        register_order_erp_routes(self.app, lambda f: f, lambda: self.db,
                                 lambda: self.company, lambda: {'role': 'manager'},
                                 lambda cid: None, self.can)
        response = self.client.get('/supply-chain')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'pane-workflow', response.data)
        self.assertNotIn(b'/supply-chain#sales-orders', response.data)
        for path in ('/order-erp', '/order-erp/dashboard'):
            response = self.client.get(path + '?order_id=ORDER-123')
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.location, '/supply-chain?order_id=ORDER-123')

    def test_navigation_follows_selected_company_and_workspace(self):
        from flask import request
        with self.app.test_request_context('/existing/inventory_list'):
            session['user'] = {'role': 'manager'}
            session['workspace_by_company'] = {'A': 'supply_chain', 'B': 'finance'}
            context = {}
            self.app.update_template_context(context)
            self.assertTrue(context['use_supply_navigation'])
            self.assertEqual(request.endpoint, 'inventory_list')
            self.company = 'B'
            context = {}
            self.app.update_template_context(context)
            self.assertFalse(context['use_supply_navigation'])
        self.company = 'A'
        with self.app.test_request_context('/finance'):
            session['user'] = {'role': 'manager'}
            session['workspace_by_company'] = {'A': 'supply_chain'}
            context = {}
            self.app.update_template_context(context)
            self.assertFalse(context['use_supply_navigation'])

    def test_every_operational_link_has_a_registered_source_route(self):
        import ast
        from pathlib import Path
        endpoints = set()
        for filename in ('app.py', 'erp_routes.py'):
            tree = ast.parse(Path(filename).read_text(encoding='utf-8-sig'))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    for dec in node.decorator_list:
                        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == 'route':
                            endpoints.add(next((ast.literal_eval(k.value) for k in dec.keywords if k.arg == 'endpoint'), node.name))
        for _, entries in SUPPLY_NAV:
            for _, endpoint, _ in entries:
                self.assertIn(endpoint, endpoints)

    def test_hub_orders_available_workspaces_before_locked_and_shows_plans(self):
        from plan_catalog import PUBLIC_PLANS
        for endpoint in ('crm_view', 'workshop_erp_view', 'hr_dashboard', 'bi_intelligence', 'logout'):
            self.app.add_url_rule('/' + endpoint, endpoint, lambda: '')
        from flask import render_template
        with self.app.test_request_context('/apps'):
            html = render_template('apps_hub.html', company=None, user={'role':'owner'}, can=self.can,
                module_access=lambda key: key in ('core','orderflow'), can_supply_chain=True,
                public_plans=PUBLIC_PLANS, current_plan=PUBLIC_PLANS['finance'])
        self.assertLess(html.index('Supply Chain Management'), html.index('Explore more workspaces'))
        self.assertGreater(html.index('QIYADAH CRM'), html.index('Explore more workspaces'))
        self.assertIn('Workspace locked', html)
        self.assertNotIn('href="/crm_view"', html)
        self.assertIn('14,997 billed once', html)
        self.assertIn('Qiyadah Unified', html)


if __name__ == '__main__':
    unittest.main()

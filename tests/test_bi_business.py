"""All-module BI against isolated customer records, including access boundaries."""
from datetime import date, datetime
from types import SimpleNamespace
import unittest

from flask import Flask
from jinja2 import ChoiceLoader, DictLoader
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from customer_models import (customer_db, CustomerInvoice, CRMLead, StockItem, OrderFlow,
    WorkshopJobCard, HREmployee, HRAttendance, HRLeaveRequest, HRPayrollRun)
from bi.business import business_overview, MODULES
from bi.business_routes import register_business_routes


class BusinessBITests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        customer_db.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.today = date(2026, 10, 7)
        self.allowed = set(key for key, *_ in MODULES) | {'bi'}
        self.denied_permissions = set()
        self.db.add_all([
            CustomerInvoice(company_id='A', invoice_number='A-1', invoice_date=date(2026,10,1),
                due_date=date(2026,10,3), currency='INR', grand_total=118, subtotal=100, balance=50),
            CustomerInvoice(company_id='A', invoice_number='A-2', invoice_date=date(2026,10,7),
                currency='USD', grand_total=20, subtotal=20, balance=0, invoice_category='workshop_repair'),
            CustomerInvoice(company_id='B', invoice_number='B-1', invoice_date=date(2026,10,1), grand_total=999999),
            CustomerInvoice(company_id='A', invoice_number='DRAFT', invoice_date=date(2026,10,1), status='Draft', grand_total=9999),
            CRMLead(id='L1', company_id='A', client_id='C1', title='Opportunity', stage='New',
                expected_close_date=date(2026,10,2), created_at=datetime(2026,10,7,23,59)),
            CRMLead(id='L2', company_id='A', client_id='C1', title='Won', stage='Won', created_at=datetime(2026,9,30)),
            CRMLead(id='PRIVATE', company_id='B', client_id='C2', title='Private', stage='New', created_at=datetime(2026,10,1)),
            StockItem(company_id='A', code='LOW', name='Part', quantity=0, reorder_level=0),
            OrderFlow(id='PROD1', company_id='A', client_name='Client', item_description='Part',
                created_by='Owner', status='Quality Check Failed', created_at=datetime(2026,10,3)),
            WorkshopJobCard(company_id='A', job_card_no='JOB1', vehicle_id=1, grand_total=9999,
                invoice_id=2, status='In Progress', estimated_delivery_date=datetime(2026,10,2), created_at=datetime(2026,10,4)),
            HREmployee(id=1, company_id='A', employee_code='EMP1', full_name='Employee',
                joining_date=date(2026,10,1), status='Active'),
            HRAttendance(company_id='A', employee_id=1, attendance_date=date(2026,10,1), status='Present'),
            HRAttendance(company_id='A', employee_id=1, attendance_date=date(2026,10,2), status='Present'),
            HRLeaveRequest(company_id='A', employee_id=1, leave_type_id=1, start_date=date(2026,9,29),
                end_date=date(2026,10,2), days=4, status='Approved'),
            HRPayrollRun(company_id='A', year=2026, month=10, status='Approved', total_net=1000),
            HRPayrollRun(company_id='A', year=2026, month=9, status='Draft', total_net=99999),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def overview(self, start=date(2026,10,1), end=date(2026,10,7)):
        return business_overview(self.db, 'A', start, end, self.today,
            lambda key:key in self.allowed, lambda key, action:key not in self.denied_permissions, 'INR')

    def metric(self, data, module, label):
        return next(metric for card in data['modules'] if card['key'] == module
                    for metric in card['metrics'] if metric['label'] == label)

    def test_all_five_modules_have_real_measures(self):
        result = self.overview()
        self.assertEqual(len(result['modules']), 5)
        self.assertTrue(all(card['metrics'] for card in result['modules']))
        self.assertEqual(self.metric(result,'crm','Leads created')['value'], 1)
        self.assertEqual(self.metric(result,'orderflow','Quality checks failed')['value'], 1)
        self.assertEqual(self.metric(result,'repair','Active job cards')['value'], 1)
        self.assertEqual(self.metric(result,'hr','Active employees')['value'], 1)

    def test_currencies_not_combined_and_workshop_not_double_counted(self):
        result = self.overview()
        money = self.metric(result, 'core', 'Billed sales incl. tax')['amounts']
        self.assertEqual({m['currency']:m['value'] for m in money}, {'INR':118,'USD':20})
        self.assertEqual(self.metric(result, 'core', 'Sales invoices issued')['value'], 2)

    def test_date_boundary_previous_period_and_snapshots(self):
        result = self.overview()
        self.assertEqual(self.metric(result, 'crm', 'Leads created')['previous'], 1)
        result = self.overview(date(2026,9,24), date(2026,9,30))
        self.assertEqual(self.metric(result, 'core', 'Sales invoices issued')['value'], 0)
        self.assertEqual(self.metric(result, 'crm', 'Open opportunities')['value'], 1)
        self.assertEqual(self.metric(result, 'crm', 'Won leads from period cohort')['value'], 1)

    def test_hr_counts_days_requests_and_approved_payroll_correctly(self):
        result = self.overview()
        self.assertEqual(self.metric(result, 'hr', 'Attendance records')['value'], 2)
        self.assertEqual(self.metric(result, 'hr', 'Approved leave requests overlapping period')['value'], 1)
        result = self.overview(date(2026,9,30),date(2026,10,1))
        self.assertEqual(self.metric(result,'hr','Approved payroll net pay')['amounts'][0]['value'], 1000)

    def test_locked_module_not_queried_and_payroll_permission_respected(self):
        self.allowed.remove('crm')
        self.denied_permissions.add('hr_payroll')
        sql = []
        def collect(conn, cursor, statement, parameters, context, many):
            if statement.lstrip().upper().startswith('SELECT'): sql.append(statement)
        event.listen(self.engine, 'before_cursor_execute', collect)
        result = self.overview()
        self.assertFalse(any('crm_leads' in statement or 'hr_payroll_runs' in statement for statement in sql))
        self.assertFalse(next(c for c in result['modules'] if c['key']=='crm')['enabled'])
        self.assertNotIn('Approved payroll net pay', [m['label'] for c in result['modules'] for m in c['metrics']])

    def test_sales_document_permission_excludes_workshop_invoices(self):
        self.denied_permissions.add('customer_invoices')
        self.assertEqual(self.metric(self.overview(),'core','Sales invoices issued')['value'], 1)

    def test_missing_sources_are_not_reported_as_zero(self):
        CRMLead.__table__.drop(self.engine)
        card = next(c for c in self.overview()['modules'] if c['key']=='crm')
        self.assertTrue(any('setup' in note for note in card['notes']))
        self.assertNotIn('Leads created',[m['label'] for m in card['metrics']])

    def test_attention_is_company_scoped(self):
        alerts = self.overview()['alerts']
        self.assertEqual(next(a['count'] for a in alerts if a['key']=='crm'), 1)
        self.assertEqual(next(a['count'] for a in alerts if a['key']=='repair'), 1)

    def app(self):
        app = Flask(__name__, template_folder='../templates')
        app.config.update(TESTING=True, SECRET_KEY='test')
        app.jinja_loader = ChoiceLoader([DictLoader({'base.html':'{% block extra_style %}{% endblock %}{% block content %}{% endblock %}'}), app.jinja_loader])
        for endpoint in ['bi_finance_dashboard', 'bi_intelligence', *(row[2] for row in MODULES)]:
            app.add_url_rule('/source/'+endpoint, endpoint, lambda:'source')
        self.role='owner'
        app.extensions['module_access']=lambda key:key in self.allowed
        register_business_routes(app, lambda f:f, lambda *args:lambda f:f, lambda:self.db, lambda:'A',
            lambda:{'role':self.role}, lambda cid:SimpleNamespace(company_id='A', company_name='Example', currency='INR'),
            lambda key, action:key not in self.denied_permissions, lambda:self.today)
        return app

    def test_dashboard_renders_all_modules_and_filtered_view(self):
        client=self.app().test_client()
        response=client.get('/bi-dashboard')
        self.assertEqual(response.status_code,200)
        for key, *_ in MODULES:
            self.assertIn(('id="module-'+key+'"').encode(),response.data)
        response=client.get('/bi-dashboard?module=hr')
        self.assertIn(b'id="module-hr"',response.data)
        self.assertNotIn(b'id="module-core"',response.data)

    def test_api_rejects_filters_and_company_switch(self):
        client=self.app().test_client()
        for args in ('from_date=bad','company=B','branch=2','module=unknown','client_id=1'):
            self.assertEqual(client.get('/api/bi/v1/business?'+args).status_code,400)
        response=client.get('/api/bi/v1/business')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['company_id'],'A')

    def test_owner_and_bi_entitlement_required(self):
        client=self.app().test_client()
        self.allowed.remove('bi')
        self.assertEqual(client.get('/bi-dashboard').status_code,403)
        self.allowed.add('bi')
        self.role='employee'
        self.assertEqual(client.get('/api/bi/v1/business').status_code,403)
        self.assertEqual(client.get('/bi-dashboard').status_code,302)

    def test_every_public_plan_has_bi_but_only_included_module_data(self):
        from plan_catalog import PUBLIC_PLANS
        client = self.app().test_client()
        for key, plan in PUBLIC_PLANS.items():
            with self.subTest(plan=key):
                self.allowed = set(plan['modules'])
                response = client.get('/api/bi/v1/business')
                self.assertEqual(response.status_code, 200)
                for card in response.json['overview']['modules']:
                    self.assertEqual(card['enabled'], card['key'] in self.allowed)
                    if not card['enabled']:
                        self.assertEqual(card['metrics'], [])

    def test_actual_bi_sidebar_links_to_new_module_views(self):
        from flask import render_template
        app = self.app()
        for endpoint in ('bi_intelligence','reports_dashboard','apps_hub'):
            if endpoint not in app.view_functions:
                app.add_url_rule('/'+endpoint,endpoint,lambda:'')
        app.jinja_env.globals['bi_unified_access'] = lambda: True
        with app.test_request_context('/bi-dashboard'):
            html = render_template('_bi_navigation.html', active='bi_dashboard', user={'role':'owner'},
                module_access=lambda key:key in self.allowed)
            self.assertIn('All-Module Dashboard',html)
            self.assertIn('/bi-dashboard?module=crm',html)
            self.assertIn('/bi-dashboard?module=hr',html)
            self.allowed.remove('hr')
            html = render_template('_bi_navigation.html', active='bi_dashboard', user={'role':'owner'},
                module_access=lambda key:key in self.allowed)
            self.assertNotIn('/bi-dashboard?module=hr',html)
            app.jinja_env.globals['bi_unified_access'] = lambda: False
            html = render_template('_bi_navigation.html', active='bi_dashboard', user={'role':'owner'},
                module_access=lambda key:key in self.allowed)
            self.assertNotIn('/bi-dashboard?module=crm',html)
    def test_plan_specific_modules_appear_and_rest_disappear_with_locked_tabs(self):
        client = self.app().test_client()
        self.allowed = {'core', 'crm', 'bi'}
        response = client.get('/bi-dashboard')
        self.assertEqual(response.status_code, 200)
        html = response.data.decode('utf-8')
        self.assertIn('id="module-core"', html)
        self.assertIn('id="module-crm"', html)
        self.assertNotIn('id="module-orderflow"', html)
        self.assertNotIn('id="module-repair"', html)
        self.assertNotIn('id="module-hr"', html)
        self.assertIn('module=core', html)
        self.assertIn('module=crm', html)
        self.assertIn('🔒 Supply Chain &amp; Production · Locked', html)
        self.assertIn('🔒 Workshop &amp; Repair · Locked', html)
        self.assertIn('🔒 HR &amp; Payroll · Locked', html)
        self.assertIn('Back to all dashboards', html)
        self.assertIn('/source/bi_intelligence', html)

    def test_locked_module_view_rejected(self):
        client = self.app().test_client()
        self.allowed = {'core', 'crm', 'bi'}
        response = client.get('/bi-dashboard?module=repair')
        self.assertEqual(response.status_code, 400)
        self.assertIn(b'The selected business area is not included in your current plan', response.data)


if __name__ == '__main__': unittest.main()

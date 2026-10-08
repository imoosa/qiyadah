"""Finance integration tests against isolated databases; no application startup."""
import ast
from datetime import date, timedelta
from functools import wraps
from pathlib import Path
import unittest

from flask import Flask, abort
from jinja2 import ChoiceLoader, DictLoader
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from customer_models import CustomerInvoice, PurchaseInvoice, WorkshopJobCard, Expense, CashTransaction, BankAccount, FinanceNote
from finance_workspace import FINANCE_SECTIONS, invoice_balances, register_finance_workspace
from permissions import default_permissions_for, _merge
from finance_dashboard import dashboard_data, parse_filters, source_documents, ageing_bucket
from finance_workspace import uses_finance_navigation, FINANCE_NAV


class FinanceWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        for model in (CustomerInvoice, PurchaseInvoice, WorkshopJobCard, Expense, CashTransaction, BankAccount, FinanceNote):
            model.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.today = date(2026, 9, 24)
        self.permissions = default_permissions_for('accountant')
        self.company = 'A'
        self.signed_in = True
        self.app = Flask(__name__, template_folder='../templates')
        self.app.testing = True
        self.app.secret_key = 'finance-tests'
        # Render the actual finance template with a minimal unrelated shell.
        self.app.jinja_loader = ChoiceLoader([
            DictLoader({'base.html': '{% block extra_style %}{% endblock %}{% block content %}{% endblock %}'}),
            self.app.jinja_loader,
        ])

        def login_required(f):
            @wraps(f)
            def wrapped(*args, **kwargs):
                if not self.signed_in:
                    abort(401)
                return f(*args, **kwargs)
            return wrapped

        def require_permission(module, action):
            def decorate(f):
                @wraps(f)
                def wrapped(*args, **kwargs):
                    if not self.can(module, action):
                        abort(403)
                    return f(*args, **kwargs)
                return wrapped
            return decorate

        for _, links in FINANCE_SECTIONS:
            for _, endpoint, _ in links:
                self.app.add_url_rule('/existing/' + endpoint, endpoint, lambda: '')
        for _, links in FINANCE_NAV:
            for _, endpoint, _, _ in links:
                if endpoint and endpoint not in ('finance_workspace', 'finance_records') and endpoint not in self.app.view_functions:
                    self.app.add_url_rule('/nav/' + endpoint, endpoint, lambda **kw: '')
        for endpoint, rule in [('select_company','/select-company'), ('customer_invoice_view','/customer-invoices/view/<int:cust_inv_id>'), ('purchase_invoice_view','/purchase/view/<invoice_id>'), ('repair_bill_view','/repair-bills/<int:job_card_id>'), ('bank_transactions','/bank-accounts/<int:account_id>/transactions')]:
            self.app.add_url_rule(rule, endpoint, lambda **kw: '')
        self.app.context_processor(lambda: dict(user={'role':'accountant'}))
        register_finance_workspace(self.app, login_required, require_permission,
                                   lambda: self.db, lambda: self.company, self.can, lambda: self.today)
        self.client = self.app.test_client()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def can(self, module, action):
        return self.permissions.get(module, {}).get(action, False)

    def sale(self, pk, **values):
        data = dict(id=pk, company_id='A', invoice_number=f'S-{pk}',
                    currency='INR', invoice_date=self.today, subtotal=100, tax_amount=18, grand_total=118, paid_amount=18, balance=100,
                    due_date=self.today - timedelta(days=1))
        data.update(values)
        row = CustomerInvoice(**data)
        self.db.add(row)
        return row

    def test_currency_tenant_status_and_due_date(self):
        self.sale(1)
        self.sale(2, currency='USD', balance=50, due_date=self.today)
        self.sale(3, company_id='B', balance=999999)
        for pk, status in enumerate(('Void', ' Cancelled ', 'Draft', 'Canceled'), 4):
            self.sale(pk, status=status, balance=999)
        self.sale(8, balance=0)
        self.sale(9, balance=-25)
        self.db.add(PurchaseInvoice(company_id='A', invoice_id='P-1', currency='INR',
                                    grand_total=300, balance=250, due_date=self.today))
        self.db.commit()
        rows = invoice_balances(self.db, 'A', self.can, self.today)
        self.assertEqual([(r['label'], r['currency'], r['count'], r['outstanding'], r['overdue']) for r in rows],
                         [('Sales invoices', 'INR', 1, 100, 100), ('Sales invoices', 'USD', 1, 50, 0),
                          ('Purchase invoices', 'INR', 1, 250, 0)])

    def test_repair_category_and_legacy_links_count_once(self):
        self.sale(1, invoice_category='workshop_repair')
        self.sale(2)
        self.sale(3)
        for pk in (1, 2):
            self.db.add(WorkshopJobCard(id=pk, job_card_no=f'J-{pk}', company_id='A', vehicle_id=1, invoice_id=2))
        self.db.add(WorkshopJobCard(id=3, job_card_no='J-3', company_id='B', vehicle_id=1, invoice_id=3))
        self.db.commit()
        rows = invoice_balances(self.db, 'A', self.can, self.today)
        self.assertEqual([(r['label'], r['count'], r['outstanding']) for r in rows],
                         [('Sales invoices', 1, 100), ('Repair bills', 2, 200)])
        self.assertEqual(self.db.query(CustomerInvoice).count(), 3)

    def test_permissions_filter_data_and_links(self):
        self.sale(1, invoice_category='workshop_repair')
        self.sale(2)
        self.db.commit()
        self.permissions['customer_invoices']['view'] = False
        self.permissions['purchase']['view'] = False
        self.permissions['analytics']['view'] = False
        response = self.client.get('/finance')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('Sales', html)
        self.assertNotIn('Repair bills', html)
        self.assertNotIn('/existing/ledger', html)
        self.assertNotIn('/existing/purchase_invoice_list', html)
        self.assertFalse(self.db.new or self.db.dirty or self.db.deleted)

    def test_authentication_finance_permission_and_company_required(self):
        self.permissions['finance']['view'] = False
        self.assertEqual(self.client.get('/finance').status_code, 403)
        self.permissions['finance']['view'] = True
        self.company = None
        self.assertEqual(self.client.get('/finance').status_code, 403)
        self.signed_in = False
        self.assertEqual(self.client.get('/finance').status_code, 401)

    def test_defaults_keep_explicit_denials(self):
        self.assertTrue(self.permissions['finance']['view'])
        self.assertTrue(self.permissions['analytics']['view'])
        self.assertFalse(default_permissions_for('employee')['finance']['view'])
        self.assertFalse(_merge(self.permissions, '{"analytics":{"view":false}}')['analytics']['view'])

    def test_dashboard_period_does_not_rewrite_current_balances(self):
        self.sale(1, invoice_date=date(2026,8,1))
        self.sale(2, invoice_date=date(2026,9,1), currency='USD', subtotal=90, tax_amount=9)
        self.sale(3, company_id='B', subtotal=99999)
        self.sale(4, status='Void', subtotal=99999)
        self.sale(5, invoice_date=date(2026,9,4), invoice_category='workshop_repair', subtotal=50, tax_amount=5)
        self.db.add_all([
            Expense(company_id='A',date=date(2026,9,5),amount=20,category='Office'),
            Expense(company_id='B',date=date(2026,9,5),amount=99999,category='Private'),
            CashTransaction(company_id='A',type='income',amount=500,category='Receipt',description='Cash'),
            CashTransaction(company_id='A',type='expense',amount=30,category='Expense',description='Cash out'),
            CashTransaction(company_id='B',type='income',amount=99999,category='Receipt',description='Private'),
            BankAccount(company_id='A',bank_name='Bank A',account_name='Operating',account_number='1',opening_balance=100,balance=250),
            BankAccount(company_id='A',bank_name='Closed',account_name='Old',account_number='2',balance=99999,status='Inactive'),
        ])
        self.db.commit()
        filters=parse_filters({'from_date':'2026-09-01','to_date':'2026-09-24'},self.today,'A')
        data=dashboard_data(self.db,'A',self.can,filters)
        self.assertEqual(data['sales'],{'INR':50,'USD':90})
        self.assertEqual(data['receivables']['total'],{'INR':200,'USD':100})
        self.assertEqual(data['cash'],470)
        self.assertEqual(data['bank_total'],250)  # Do not add opening balance a second time.
        self.assertEqual(data['liquidity'],720)
        self.assertEqual(data['expenses'],20)
        self.assertEqual(data['months'][0]['revenue'],50)  # USD never mixed into INR.
        self.assertEqual(data['output_tax'],{'INR':5,'USD':9})
        self.assertNotIn('net_profit',data)
        self.assertFalse(self.db.new or self.db.dirty or self.db.deleted)

    def test_ageing_boundaries_and_missing_due_dates(self):
        self.assertEqual(ageing_bucket(None,self.today),'No due date')
        for days,bucket in ((0,'Not due'),(1,'1–30 days'),(30,'1–30 days'),(31,'31–60 days'),
                            (60,'31–60 days'),(61,'61–90 days'),(90,'61–90 days'),(91,'90+ days')):
            self.assertEqual(ageing_bucket(self.today-timedelta(days=days),self.today),bucket)

    def test_filter_validation_and_tenant_switch_rejected(self):
        for query in ('company=B','branch=Other','from_date=bad','fy=bad',
                      'from_date=2026-10-01&to_date=2026-09-01'):
            self.assertEqual(self.client.get('/finance?'+query).status_code,400)

    def test_drilldown_reuses_original_records_and_permissions(self):
        self.sale(1,client_name='Allowed customer')
        self.sale(2,client_name='Future payment',due_date=self.today+timedelta(days=2))
        self.sale(3,company_id='B',client_name='Private company')
        self.sale(4,invoice_category='workshop_repair',client_name='Repair customer')
        self.db.add(WorkshopJobCard(id=1,job_card_no='J1',company_id='A',vehicle_id=1,invoice_id=4))
        self.db.commit()
        html=self.client.get('/finance/records/receivables?mode=overdue').get_data(as_text=True)
        self.assertIn('/customer-invoices/view/1',html)
        self.assertIn('/repair-bills/1',html)
        self.assertNotIn('Future payment',html)
        self.assertNotIn('Private company',html)
        self.permissions['invoices']['view']=False
        html=self.client.get('/finance/records/receivables').get_data(as_text=True)
        self.assertNotIn('Allowed customer',html)
        self.assertIn('Repair customer',html)
        self.permissions['customer_invoices']['view']=False
        self.assertEqual(self.client.get('/finance/records/receivables').status_code,403)
        self.assertEqual(self.db.query(CustomerInvoice).count(),4)

    def test_finance_sidebar_role_behavior(self):
        self.assertTrue(uses_finance_navigation('accountant','customer_invoice_list','/customer-invoices','app'))
        self.assertTrue(uses_finance_navigation('accountant','repair_bills_view','/repair-bills','workshop_routes'))
        self.assertFalse(uses_finance_navigation('owner','customer_invoice_list','/customer-invoices','app'))
        self.assertTrue(uses_finance_navigation('owner','finance_workspace','/finance','finance_workspace'))
        self.assertFalse(uses_finance_navigation('accountant','workshop_erp_view','/workshop','workshop_routes'))
        self.assertFalse(uses_finance_navigation('accountant','apps_hub','/apps','app'))
        headings=[heading for heading,_ in FINANCE_NAV]
        self.assertEqual(headings,['CORE FINANCE','RECEIVABLES','PAYABLES','ACCOUNTING','BANKING & CASH','TAX','EXPENSES & ASSETS','REPORTS'])

    def test_real_dashboard_shows_all_kpis_and_honest_unavailable_states(self):
        html=self.client.get('/finance').get_data(as_text=True)
        for label in ('Cash in Hand','Cash at Bank','Accounts Receivable','Accounts Payable',
                      'Overdue Receivables','Overdue Payables','Sales','Purchases','Expenses',
                      'Gross Profit','Net Profit','GST Position','Attention Required',
                      'Needs accounting engine','Needs gst reconciliation'):
            self.assertIn(label,html)
        self.assertIn('Selected company records only',html)

    def test_live_sidebar_contains_gst_link_for_indian_finance(self):
        from finance_workspace import finance_navigation
        from types import SimpleNamespace
        from flask import render_template
        self.app.add_url_rule('/apps', 'apps_hub', lambda: '')
        company = SimpleNamespace(country='India', tax_regime='GST', gst_number='29AAACG0569P1Z3')
        with self.app.test_request_context('/customer-invoices'):
            groups = finance_navigation(lambda *args: True, company)
            html = render_template('_finance_navigation.html', finance_navigation=groups)
            self.assertIn('GST e-Invoice &amp; e-Way Bill', html)
            self.assertIn('/existing/gst_portal', html)
            self.assertLess(html.index('Sales Invoices'), html.index('GST e-Invoice'))
            company.country = 'United Arab Emirates'
            company.tax_regime = 'GCC_VAT'
            self.assertFalse(any(link['endpoint'] == 'gst_portal' for group in finance_navigation(lambda *args: True, company) for link in group['links']))

    def test_all_navigation_endpoints_exist_in_existing_source(self):
        root = Path(__file__).resolve().parents[1]
        endpoints = set()
        for filename in ('app.py', 'erp_routes.py', 'workshop_routes.py', 'gst_portal.py', 'bi/business_routes.py'):
            tree = ast.parse((root / filename).read_text(encoding='utf-8-sig'))
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute) and decorator.func.attr == 'route':
                        endpoint = next((ast.literal_eval(k.value) for k in decorator.keywords if k.arg == 'endpoint'), node.name)
                        endpoints.add(endpoint)
        for _, links in FINANCE_SECTIONS:
            for _, endpoint, _ in links:
                self.assertIn(endpoint, endpoints)


if __name__ == '__main__':
    unittest.main()

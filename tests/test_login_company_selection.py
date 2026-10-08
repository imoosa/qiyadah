"""Login redirects and explicit company selection without application startup."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from flask import Flask, request, session, redirect, url_for, flash


class LoginCompanySelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tree = ast.parse(Path('app.py').read_text(encoding='utf-8-sig'))
        cls.code = compile(ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)
                           and node.name in ('login', '_finish_owner_login', 'select_company')], type_ignores=[]), 'auth_routes', 'exec')

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(SECRET_KEY='test', TESTING=True)
        self.owner = SimpleNamespace(email='owner@example.com', user_id='OWNER', full_name='Owner', role='owner',
                                     password_hash='valid', email_verified=True, must_change_password=False, companies=[])
        self.employee = SimpleNamespace(email='employee@example.com', user_id='EMP', full_name='Employee', role='employee', password_hash='valid')
        self.companies = [SimpleNamespace(company_id='A', owner_email=self.owner.email, is_active=True)]
        self.registered = SimpleNamespace(query=Mock())
        self.registered.query.filter_by.return_value.first.return_value = self.owner
        company_model = SimpleNamespace(query=Mock())
        company_model.query.filter_by.return_value.all.side_effect = lambda: self.companies
        self.cdb = Mock()
        self.cdb.query.return_value.filter_by.return_value.first.return_value = self.employee
        namespace = dict(app=self.app, request=request, session=session, redirect=redirect, url_for=url_for, flash=flash,
                         RegisteredUser=self.registered, Company=company_model, CompanyUser=object(),
                         verify_password=lambda password, stored: password == stored,
                         get_owner_companies=lambda email: self.companies, get_employee_companies=lambda email: self.companies,
                         get_customer_session=lambda cid: self.cdb,
                         get_company_by_id=lambda cid: next((c for c in self.companies if c.company_id == cid), None),
                         get_current_user=lambda: session.get('user'), get_owner_user_stats=lambda email: (1, 10, None),
                         render_template=lambda name, **kw: {'template': name, 'companies': [c.company_id for c in kw.get('companies', [])]})
        exec(self.code, namespace)
        for endpoint in ('apps_hub', 'onboard_company', 'admin_dashboard', 'force_change_password', 'verify_otp'):
            self.app.add_url_rule('/'+endpoint, endpoint, lambda: '')
        self.client = self.app.test_client()

    def test_owner_always_selects_even_one_company(self):
        for count in (1, 2):
            self.companies[:] = [SimpleNamespace(company_id=str(i), owner_email=self.owner.email, is_active=True) for i in range(count)]
            with self.client.session_transaction() as state:
                state['user'] = {'email': 'old@example.com'}
                state['active_company_id'] = 'STALE'
            response = self.client.post('/login', data={'email': self.owner.email, 'password': 'valid'})
            self.assertEqual(response.location, '/select-company')
            with self.client.session_transaction() as state:
                self.assertNotIn('active_company_id', state)
                self.assertNotIn('user', state)
            self.assertEqual(self.client.get('/select-company').json['companies'], [str(i) for i in range(count)])
            self.assertEqual(self.client.post('/select-company', data={'company_id': '0'}).location, '/apps_hub')

    def test_employee_selects_and_cannot_choose_unverified_company(self):
        self.registered.query.filter_by.return_value.first.return_value = None
        response = self.client.post('/login', data={'email': self.employee.email, 'password': 'valid'})
        self.assertEqual(response.location, '/select-company')
        self.companies.append(SimpleNamespace(company_id='B', owner_email=self.owner.email, is_active=True))
        self.assertEqual(self.client.get('/select-company').json['companies'], ['A'])
        self.assertEqual(self.client.post('/select-company', data={'company_id': 'B'}).location, '/select-company')
        self.assertEqual(self.client.post('/select-company', data={'company_id': 'A'}).location, '/apps_hub')
        with self.client.session_transaction() as state:
            self.assertEqual(state['active_company_id'], 'A')
            self.assertNotIn('pending_login_company_ids', state)

    def test_no_company_still_requires_onboarding(self):
        self.companies.clear()
        self.assertEqual(self.client.post('/login', data={'email': self.owner.email, 'password': 'valid'}).location, '/onboard_company')

if __name__ == '__main__':
    unittest.main()

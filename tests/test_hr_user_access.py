"""Isolated tenant tests for HR permission delegation; no production DB access."""
import json
import unittest
from types import SimpleNamespace
from pathlib import Path
from flask import Flask, session
from jinja2 import ChoiceLoader, DictLoader, FileSystemLoader
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from customer_models import CompanyUser, CompanyRolePermission
from hr_user_access import register_hr_user_access, HRAccessDelegation, HRAccessAudit
from permissions import default_permissions_for, get_field_permissions


class HRUserAccessTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='isolated-hr-tests')
        self.app.jinja_loader = ChoiceLoader([DictLoader({'base.html': '{% block content %}{% endblock %}'}),
            FileSystemLoader(str(Path(__file__).resolve().parents[1] / 'templates'))])
        self.engine = create_engine('sqlite:///:memory:')
        for model in (CompanyUser, CompanyRolePermission, HRAccessDelegation, HRAccessAudit):
            model.__table__.create(self.engine)
        self.cdb = Session(self.engine)
        self.company = SimpleNamespace(company_id='A', company_name='Company A',
            owner_email='owner@example.test', is_active=True, branch_name='North')
        self.hr_enabled = True
        self.app.extensions['module_access'] = lambda module: self.hr_enabled
        for uid, cid, role in [('ADMIN','A','hr_admin'), ('STAFF','A','hr_staff'),
                ('PAY','A','payroll_officer'), ('OTHER','B','hr_staff'),
                ('ADMIN2','A','hr_admin'), ('MANAGER','A','manager')]:
            self.cdb.add(CompanyUser(user_id=uid, company_id=cid, email=uid+'@example.test',
                full_name=uid, role=role, password_hash='unused', is_active=True))
        self.cdb.commit()
        register_hr_user_access(self.app, lambda: session.get('user', {}),
            lambda: session.get('company_id'), lambda cid: self.cdb,
            lambda cid: self.company if cid == 'A' else None)
        self.app.add_url_rule('/company/settings', 'company_settings', lambda: 'Owner settings')
        self.client = self.app.test_client()
        self.login('OWNER', 'owner', 'owner@example.test')

    def tearDown(self):
        self.cdb.close()
        self.engine.dispose()

    def login(self, uid, role, email=None):
        with self.client.session_transaction() as state:
            state.clear()
            state['user'] = dict(user_id=uid, role=role, email=email or uid+'@example.test')
            state['company_id'] = 'A'
            state['hr_access_csrf'] = 'test-token'

    def post(self, target, action='permissions', **values):
        return self.client.post('/company/hr-user-access', data={
            'user_id':target, 'action':action, 'csrf_token':'test-token', **values})

    def member(self, uid):
        return self.cdb.query(CompanyUser).filter_by(user_id=uid).one()

    def delegate(self):
        self.member('ADMIN').permission_overrides = json.dumps({
            'hr_attendance': {'view':True, 'edit':True}, 'hr_payroll': {'view':True}})
        self.cdb.commit()
        result = self.post('ADMIN', 'delegation', enabled='on',
            hr_attendance__view='on', hr_attendance__edit='on', hr_salary__edit='on')
        self.assertEqual(result.status_code, 302)
        self.login('ADMIN', 'hr_admin')

    def test_owner_can_use_page_without_hr_but_cannot_enable_delegation(self):
        self.hr_enabled = False
        response = self.client.get('/company/hr-user-access')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'not available on your plan', response.data)
        self.assertNotIn(b'Assign an HR administrator', response.data)
        self.assertNotIn(b'Add HR staff', response.data)
        self.assertEqual(self.post('ADMIN', 'delegation', enabled='on').status_code, 403)
        self.assertEqual(self.post('ADMIN', 'delegation').status_code, 302)

    def test_hr_role_alone_grants_no_administration(self):
        self.login('ADMIN','hr_admin')
        self.assertEqual(self.client.get('/company/hr-user-access').status_code,403)
        self.assertEqual(self.post('STAFF', hr_attendance__edit='on').status_code,403)

    def test_delegate_can_edit_only_allowed_hr_cells_and_audits(self):
        self.delegate()
        self.member('STAFF').permission_overrides = json.dumps({
            'finance': {'view':True}, 'hr_payroll': {'edit':True}, 'hr_attendance': {'delete':True}})
        self.cdb.commit()
        self.assertEqual(self.client.get('/company/hr-user-access').status_code,200)
        self.assertEqual(self.post('STAFF',hr_attendance__view='on',hr_attendance__edit='on').status_code,302)
        values=json.loads(self.member('STAFF').permission_overrides)
        self.assertTrue(values['hr_attendance']['edit'])
        self.assertTrue(values['hr_attendance']['delete'])
        self.assertTrue(values['hr_payroll']['edit'])
        self.assertTrue(values['finance']['view'])
        self.assertEqual(self.cdb.query(HRAccessAudit).count(),2)
        self.assertEqual(self.post('STAFF').status_code,302)
        self.assertFalse(json.loads(self.member('STAFF').permission_overrides)['hr_attendance']['edit'])

    def test_ceiling_is_intersection_of_owner_grant_and_actual_access(self):
        self.delegate()
        # Salary delegated but not held; payroll held but not delegated.
        for field in ('hr_salary__edit','hr_payroll__view','hr_attendance__delete'):
            self.assertEqual(self.post('STAFF',**{field:'on'}).status_code,403)
        self.assertIsNone(self.member('STAFF').permission_overrides)

    def test_protected_users_cross_company_and_self_are_denied(self):
        self.delegate()
        for target in ('ADMIN','ADMIN2','MANAGER','OTHER','missing'):
            self.assertEqual(self.post(target,hr_attendance__view='on').status_code,403)
        self.assertEqual(self.post('ADMIN2','delegation',enabled='on').status_code,403)

    def test_forged_finance_or_role_fields_are_rejected(self):
        self.delegate()
        for field in ('finance__view','role','enabled','company_id'):
            self.assertEqual(self.post('STAFF',**{field:'on'}).status_code,400)
        self.assertIsNone(self.member('STAFF').permission_overrides)

    def test_revocation_applies_to_existing_login(self):
        self.delegate()
        grant=self.cdb.get(HRAccessDelegation,('A','ADMIN'))
        grant.enabled=False
        self.cdb.commit()
        self.assertEqual(self.post('STAFF').status_code,403)
        grant.enabled=True
        self.member('ADMIN').is_active=False
        self.cdb.commit()
        self.assertEqual(self.post('STAFF').status_code,403)
        self.member('ADMIN').is_active=True
        self.member('ADMIN').role='manager'
        self.cdb.commit()
        self.assertEqual(self.post('STAFF').status_code,403)

    def test_operational_restriction_and_subscription_apply_immediately(self):
        self.delegate()
        self.member('ADMIN').permission_overrides='{}'
        self.cdb.commit()
        self.assertEqual(self.post('STAFF',hr_attendance__edit='on').status_code,403)
        self.hr_enabled=False
        self.assertEqual(self.client.get('/company/hr-user-access').status_code,403)
        self.assertEqual(self.post('STAFF').status_code,403)

    def test_csrf_owner_identity_and_inactive_target(self):
        self.assertEqual(self.client.post('/company/hr-user-access',data={
            'user_id':'ADMIN','action':'delegation','enabled':'on'}).status_code,400)
        self.login('FAKE','owner','different@example.test')
        self.assertEqual(self.client.get('/company/hr-user-access').status_code,403)
        self.login('OWNER','owner','owner@example.test')
        self.delegate()
        self.member('STAFF').is_active=False
        self.cdb.commit()
        self.assertEqual(self.post('STAFF').status_code,403)

    def test_hr_roles_start_without_finance_payroll_or_invoice_fields(self):
        for role in ('hr_admin','hr_staff','payroll_officer'):
            permissions=default_permissions_for(role)
            self.assertFalse(permissions['finance']['view'])
            self.assertFalse(permissions['hr_payroll']['edit'])
            self.assertFalse(any(p['view'] or p['edit'] for p in get_field_permissions(role).values()))

    def test_owner_role_and_permission_saves_enforce_target_subscription(self):
        import ast
        from unittest.mock import patch
        from flask import abort, request
        from werkzeug.exceptions import Forbidden
        import permissions
        tree=ast.parse((Path(__file__).resolve().parents[1]/'app.py').read_text(encoding='utf-8-sig'))
        names={'validate_company_role_assignment','_read_permission_matrix_from_form'}
        code=compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),'access_helpers','exec')
        namespace=dict(abort=abort,request=request,json=json,perms_module=permissions,
            ALLOWED_COMPANY_ROLES=['employee','manager','accountant',*permissions.HR_ROLES],
            get_company_by_id=lambda cid:self.company,get_current_company=lambda:'A')
        exec(code,namespace)
        validate=namespace['validate_company_role_assignment']
        read=namespace['_read_permission_matrix_from_form']
        with patch('module_access.company_has_hr_access',side_effect=lambda company:company.company_id=='HR'):
            for role in permissions.HR_ROLES:
                with self.assertRaises(Forbidden): validate(self.company,role)
                validate(SimpleNamespace(company_id='HR'),role)
            validate(self.company,'employee')
            with self.app.test_request_context(method='POST',data={'perm__hr_payroll__edit':'on'}):
                with self.assertRaises(Forbidden):read()
            with self.app.test_request_context(method='POST',data={'perm__clients__view':'on'}):
                matrix=read(json.dumps({'hr_payroll':{'view':True}}))
                self.assertTrue(matrix['clients']['view'])
                self.assertEqual(matrix['hr_payroll'],{'view':True})

    def test_workspace_access_removal_blocks_delegation(self):
        self.delegate()
        self.member('ADMIN').permission_overrides=json.dumps({'hr': {'view':False}})
        self.cdb.commit()
        self.assertEqual(self.client.get('/company/hr-user-access').status_code,403)

    def test_real_subscription_and_user_block_integration(self):
        from datetime import date
        from platform_models import db, Company, RegisteredUser, SubscriptionPlan, PlatformAccessRule
        from module_access import register_module_access
        self.app.config['SQLALCHEMY_DATABASE_URI']='sqlite:///:memory:'
        db.init_app(self.app)
        with self.app.app_context():
            db.create_all()
            for plan in ('crm_hr','finance'):
                db.session.add(SubscriptionPlan(id=plan,name=plan,price='0',max_companies='3',max_users='10'))
            db.session.add(RegisteredUser(user_id='OWNER',email='owner@example.test',
                full_name='Owner',role='owner',password_hash='unused',is_active=True,subscription_plan='crm_hr'))
            db.session.flush()
            db.session.add(Company(company_id='A',company_name='Company A',owner_email='owner@example.test',
                subscription_plan='crm_hr',is_active=True))
            db.session.commit()
        register_module_access(self.app,lambda:session.get('user',{}),
            lambda:session.get('company_id'),lambda cid:self.cdb,date.today)
        try:
            self.delegate()
            self.assertEqual(self.client.get('/company/hr-user-access').status_code,200)
            with self.app.app_context():
                db.session.add(PlatformAccessRule(scope='user',target='A:ADMIN',overrides={'hr':False}))
                db.session.commit()
            self.assertEqual(self.post('STAFF',hr_attendance__view='on').status_code,403)
            with self.app.app_context():
                db.session.delete(db.session.get(PlatformAccessRule,('user','A:ADMIN')))
                Company.query.filter_by(company_id='A').one().subscription_plan='finance'
                db.session.commit()
            self.assertEqual(self.client.get('/company/hr-user-access').status_code,403)
            self.login('OWNER','owner','owner@example.test')
            self.assertEqual(self.client.get('/company/hr-user-access').status_code,200)
            self.assertEqual(self.post('ADMIN','delegation').status_code,302)
        finally:
            with self.app.app_context():
                db.session.remove()
                db.drop_all()
                db.engine.dispose()


if __name__ == '__main__':
    unittest.main()

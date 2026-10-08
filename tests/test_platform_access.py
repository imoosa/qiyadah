"""Access override precedence, trial extensions, authorization and active-session tests."""
import unittest
from datetime import date, timedelta
from flask import Flask, session
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from platform_models import db, Company, RegisteredUser, SubscriptionPlan, PlatformAccessRule, PlatformAccessAudit
from customer_models import CompanyUser
from module_access import module_states, register_module_access
from admin_access import register_admin_access


class PlatformAccessTests(unittest.TestCase):
    def setUp(self):
        self.today=date(2026,9,22)
        self.app=Flask(__name__,template_folder='../templates')
        self.app.config.update(SECRET_KEY='isolated-test',TESTING=True,SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
        db.init_app(self.app);self.context=self.app.app_context();self.context.push();db.create_all()
        self.engine=create_engine('sqlite:///:memory:');CompanyUser.__table__.create(self.engine);self.cdb=Session(self.engine)
        for plan in ['business','trial']:
            db.session.add(SubscriptionPlan(id=plan,name=plan,price='0',max_companies='5',max_users='10'))
        db.session.add_all([
            RegisteredUser(user_id='ADMIN',email='admin-test',full_name='Admin',role='super_admin',password_hash='unused',is_active=True),
            RegisteredUser(user_id='OWNER',email='owner-test',full_name='Owner',role='owner',password_hash='unused',subscription_plan='business',is_active=True),
            RegisteredUser(user_id='TRIAL',email='trial-test',full_name='Trial owner',role='owner',password_hash='unused',subscription_plan='trial',created_at=self.today-timedelta(days=20),is_active=True)])
        db.session.flush()
        db.session.add_all([Company(company_id='A',company_name='Account A',owner_email='owner-test',subscription_plan='business',is_active=True),
            Company(company_id='T',company_name='Trial Company',owner_email='trial-test',subscription_plan='trial',subscription_end=self.today-timedelta(days=6),is_active=True)])
        db.session.commit()
        self.cdb.add(CompanyUser(user_id='EMP1',company_id='A',email='team-test',full_name='Team',role='employee',password_hash='unused',is_active=True));self.cdb.commit()
        getter=lambda:session.get('user',{})
        company_getter=lambda:session.get('active_company_id') or getter().get('company_id')
        register_module_access(self.app,getter,company_getter,lambda cid:self.cdb,lambda:self.today)
        register_admin_access(self.app,getter,lambda cid:self.cdb,lambda:self.today)
        def feature():return {'success':True}
        feature._requires_login=True
        self.app.add_url_rule('/api/core-test',view_func=feature,methods=['GET','POST'])
        self.app.add_url_rule('/api/crm/test',endpoint='crm_test',view_func=feature,methods=['GET','POST'])
        self.app.add_url_rule('/api/workshop/test',endpoint='repair_test',view_func=feature)
        self.app.add_url_rule('/api/order-erp/test',endpoint='order_test',view_func=feature)
        self.app.add_url_rule('/api/hr/test',endpoint='hr_test',view_func=feature)
        self.app.add_url_rule('/repair-bills',endpoint='repair_bills_view',view_func=feature)
        self.app.add_url_rule('/repair-bills/1',endpoint='repair_bill_view',view_func=feature)
        self.app.add_url_rule('/finance',endpoint='finance_workspace',view_func=feature)
        for endpoint, path in [('supply_chain_workspace', '/supply-chain'), ('inventory_list', '/inventory'), ('purchase_order_list', '/purchase-orders'), ('sales_order_list', '/sales-orders'), ('delivery_challan_list', '/delivery-challans')]:
            self.app.add_url_rule(path, endpoint=endpoint, view_func=feature)
        for i, path in enumerate(('/bi-dashboard', '/bi-dashboard/finance', '/bi-intelligence',
                '/api/bi/v1/business', '/api/bi/dashboard', '/api/bi/company-analysis',
                '/bi-executive', '/bi-builder', '/bi-explore', '/bi-predictive', '/bi-warehouse',
                '/api/bi/v1/explore/export/csv', '/api/bi/v1/builder/dashboards',
                '/api/bi/v1/warehouse/refresh', '/api/bi/v1/predictive', '/reports-dashboard')):
            self.app.add_url_rule(path, endpoint=f'bi_test_{i}', view_func=feature, methods=['GET','POST'])
        self.client=self.app.test_client();self.login('ADMIN','admin-test','super_admin')
        self.token=self.client.get('/api/admin/access/catalog').json['csrf_token']

    def tearDown(self):
        self.cdb.close();self.engine.dispose();db.session.remove();db.drop_all();db.engine.dispose();self.context.pop()

    def login(self,uid,email,role,company=None):
        with self.client.session_transaction() as s:
            s.clear();s['user']=dict(user_id=uid,email=email,role=role,company_id=company)

    def save(self,scope,target,overrides,revision=0,days=0):
        return self.client.put(f'/api/admin/access/{scope}/{target}',json={'overrides':overrides,'revision':revision,'extend_days':days},headers={'X-Admin-CSRF':self.token})

    def test_supply_routes_require_supply_package(self):
        from plan_catalog import PUBLIC_PLANS
        for key, p in PUBLIC_PLANS.items():
            db.session.add(SubscriptionPlan(id=key, name=p['name'], price=p['price'],
                max_companies=p['max_companies'], max_users=p['max_users']))
        owner = RegisteredUser.query.filter_by(user_id='OWNER').one()
        company = Company.query.filter_by(company_id='A').one()
        self.login('OWNER', 'owner-test', 'owner', 'A')
        for plan in PUBLIC_PLANS:
            owner.subscription_plan = company.subscription_plan = plan
            db.session.commit()
            for path in ('/supply-chain', '/inventory', '/purchase-orders', '/sales-orders',
                         '/delivery-challans', '/api/order-erp/test'):
                with self.subTest(plan=plan, path=path):
                    response = self.client.get(path, headers={'X-Requested-With': 'XMLHttpRequest'})
                    self.assertEqual(response.status_code, 200 if plan in ('finance_supply', 'unified') else 403)
            self.assertEqual(self.client.get('/finance').status_code, 200)

    def test_unified_bi_gate_and_standard_dashboards(self):
        from plan_catalog import PUBLIC_PLANS
        for key, p in PUBLIC_PLANS.items():
            db.session.add(SubscriptionPlan(id=key, name=p['name'], price=p['price'],
                max_companies=p['max_companies'], max_users=p['max_users']))
        owner = RegisteredUser.query.filter_by(user_id='OWNER').one()
        company = Company.query.filter_by(company_id='A').one()
        self.login('OWNER','owner-test','owner','A')
        for plan in PUBLIC_PLANS:
            owner.subscription_plan = company.subscription_plan = plan
            db.session.commit()
            for path in ('/bi-dashboard','/bi-intelligence','/bi-dashboard/finance',
                         '/api/bi/v1/business','/api/bi/dashboard','/api/bi/company-analysis', '/reports-dashboard'):
                self.assertEqual(self.client.get(path).status_code,200,(plan,path))
            for path in ('/bi-executive','/bi-builder','/bi-explore','/bi-predictive','/bi-warehouse',
                         '/api/bi/v1/explore/export/csv','/api/bi/v1/builder/dashboards',
                         '/api/bi/v1/warehouse/refresh','/api/bi/v1/predictive',
                         '/bi-dashboard?module=crm','/api/bi/v1/business?module=hr'):
                for method in ('get','post'):
                    response = getattr(self.client,method)(path,json={})
                    self.assertEqual(response.status_code,200 if plan == 'unified' else 403,(plan,path,method))
        db.session.add(PlatformAccessRule(scope='company',target='A',overrides={'bi':False}))
        db.session.commit()
        self.assertEqual(self.client.get('/api/bi/v1/predictive').status_code,403)

    def test_public_plan_entitlements_and_custom_assignment(self):
        from plan_catalog import PUBLIC_PLANS
        from module_access import subject_access
        for key, p in PUBLIC_PLANS.items():
            db.session.add(SubscriptionPlan(id=key,name=p['name'],price=p['price'],
                max_companies=p['max_companies'],max_users=p['max_users'],max_branches=p['max_branches']))
        owner=RegisteredUser.query.filter_by(user_id='OWNER').one()
        company=Company.query.filter_by(company_id='A').one()
        owner.subscription_plan=company.subscription_plan='crm_hr';db.session.commit()
        states=subject_access(owner,company,today=self.today)
        self.assertTrue(states['hr']['allowed']);self.assertTrue(states['crm']['allowed'])
        self.assertTrue(states['bi']['allowed'])
        self.assertTrue(states['core']['allowed']);self.assertFalse(states['orderflow']['allowed'])
        payload=dict(name='Friends plan',annual_price='1234.50',users=7,companies=3,branches=4,
                     modules=['core','orderflow','hr'],years=3)
        url='/api/admin/custom-plan/OWNER'
        self.assertEqual(self.client.post(url,json=payload).status_code,403)
        response=self.client.post(url,json=payload,headers={'X-Admin-CSRF':self.token})
        self.assertEqual(response.status_code,200)
        db.session.refresh(owner);db.session.refresh(company)
        self.assertEqual(owner.subscription_plan,company.subscription_plan)
        self.assertEqual(str(owner.custom_yearly_amount),'1234.50')
        self.assertEqual(owner.custom_max_users,7)
        self.assertEqual(db.session.get(SubscriptionPlan,owner.subscription_plan).max_branches,4)
        self.assertEqual(company.subscription_end,self.today+timedelta(days=1095))
        states=subject_access(owner,company,today=self.today)
        self.assertTrue(states['core']['allowed']);self.assertFalse(states['crm']['allowed'])
        self.assertEqual(owner.payment_status,'pending')
        self.login('OWNER','owner-test','owner','A')
        self.assertEqual(self.client.post(url,json=payload,headers={'X-Admin-CSRF':self.token}).status_code,403)

    def test_locked_modules_are_enforced_on_direct_api_requests(self):
        db.session.add(SubscriptionPlan(id='finance',name='Finance',price='6999',max_companies='2',max_users='5'))
        Company.query.filter_by(company_id='A').one().subscription_plan='finance';db.session.commit()
        self.login('OWNER','owner-test','owner','A')
        self.assertEqual(self.client.get('/api/hr/test').status_code,403)
        self.assertEqual(self.client.get('/api/crm/test').status_code,403)
        self.assertEqual(self.client.get('/api/workshop/test').status_code,403)
        self.assertEqual(self.client.get('/api/order-erp/test').status_code,403)
        self.assertEqual(self.client.get('/api/core-test').status_code,200)

    def test_invalid_custom_plan_does_not_change_account(self):
        for price in ('NaN','-1','1.001'):
            response=self.client.post('/api/admin/custom-plan/OWNER',json=dict(name='Private',
                annual_price=price,users=5,companies=2,branches=2,modules=['core'],years=1),
                headers={'X-Admin-CSRF':self.token})
            self.assertEqual(response.status_code,400)
        self.assertEqual(RegisteredUser.query.filter_by(user_id='OWNER').one().subscription_plan,'business')

    def test_policy_precedence(self):
        self.assertTrue(module_states({'crm':False}, [('account',{'crm':True})])['crm']['allowed'])
        self.assertFalse(module_states({'crm':True}, [('account',{'crm':False}),('team',{'crm':True})])['crm']['allowed'])
        self.assertFalse(module_states(layers=[('account',{'repair':True})],trial_end=self.today-timedelta(days=1),today=self.today)['repair']['allowed'])

    def test_core_finance_can_read_bills_without_workshop_operations(self):
        self.assertEqual(self.save('account','OWNER',{'repair':False}).status_code,200)
        self.login('OWNER','owner-test','owner','A')
        self.assertEqual(self.client.get('/finance').status_code,200)
        self.assertEqual(self.client.get('/repair-bills').status_code,200)
        self.assertEqual(self.client.get('/repair-bills/1').status_code,200)
        self.assertEqual(self.client.get('/api/workshop/test').status_code,403)
        policy=db.session.get(PlatformAccessRule,('account','OWNER'))
        policy.overrides={'core':False,'repair':True};db.session.commit()
        self.assertEqual(self.client.get('/finance',headers={'X-Requested-With':'XMLHttpRequest'}).status_code,403)
        self.assertEqual(self.client.get('/repair-bills').status_code,200)
        policy.overrides={'core':False,'repair':False};db.session.commit()
        self.assertEqual(self.client.get('/repair-bills',headers={'X-Requested-With':'XMLHttpRequest'}).status_code,403)

    def test_revoke_live_owner_session_and_independent_workspaces(self):
        self.assertEqual(self.save('account','OWNER',{'crm':False,'core':False}).status_code,200)
        self.login('OWNER','owner-test','owner','A')
        self.assertEqual(self.client.get('/api/crm/test').status_code,403)
        self.assertEqual(self.client.post('/api/crm/test').status_code,403)
        self.assertEqual(self.client.get('/api/core-test').status_code,403)
        self.assertEqual(self.client.get('/api/workshop/test').status_code,200)
        self.assertEqual(self.client.get('/api/order-erp/test').status_code,200)
        policy=db.session.get(PlatformAccessRule,('account','OWNER'));policy.overrides={};db.session.commit()
        self.assertEqual(self.client.get('/api/crm/test').status_code,200)

    def test_team_allow_cannot_bypass_parent_deny(self):
        self.assertEqual(self.save('company','A',{'repair':False}).status_code,200)
        self.assertEqual(self.save('user','A:EMP1',{'repair':True,'crm':False}).status_code,200)
        self.login('EMP1','team-test','employee','A')
        self.assertEqual(self.client.get('/api/workshop/test').status_code,403)
        self.assertEqual(self.client.get('/api/crm/test').status_code,403)
        self.assertEqual(self.client.get('/api/order-erp/test').status_code,200)

    def test_trial_extension_reactivates_and_audits(self):
        self.login('TRIAL','trial-test','owner','T')
        self.assertEqual(self.client.get('/api/crm/test').status_code,403)
        self.login('ADMIN','admin-test','super_admin');self.token=self.client.get('/api/admin/access/catalog').json['csrf_token']
        result=self.save('account','TRIAL',{},days=14)
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json['trial_end'],'2026-10-06')
        self.assertEqual(Company.query.filter_by(company_id='T').first().subscription_end,date(2026,10,6))
        self.assertEqual(PlatformAccessAudit.query.count(),1)
        self.login('TRIAL','trial-test','owner','T')
        self.assertEqual(self.client.get('/api/crm/test').status_code,200)

    def test_future_trial_extension_and_paid_plan_rejection(self):
        company=Company.query.filter_by(company_id='T').first();company.subscription_end=self.today+timedelta(days=5);db.session.commit()
        result=self.save('company','T',{'crm':False},days=7)
        self.assertEqual(result.json['trial_end'],(self.today+timedelta(days=12)).isoformat())
        self.assertFalse(result.json['effective']['crm']['allowed'])
        self.assertEqual(self.save('account','OWNER',{},days=7).status_code,400)
        self.assertIsNone(db.session.get(PlatformAccessRule,('account','OWNER')))

    def test_authorization_csrf_validation_and_stale_edits(self):
        url='/api/admin/access/account/OWNER'
        self.assertEqual(self.client.put(url,json={'overrides':{}}).status_code,403)
        self.assertEqual(self.save('account','OWNER',{'bogus':True}).status_code,400)
        self.assertEqual(self.save('account','OWNER',{'crm':'false'}).status_code,400)
        self.assertEqual(self.save('account','OWNER',{'crm':False}).status_code,200)
        self.assertEqual(self.save('account','OWNER',{'crm':True}).status_code,409)
        self.assertFalse(db.session.get(PlatformAccessRule,('account','OWNER')).overrides['crm'])
        self.login('OWNER','owner-test','owner','A')
        self.assertEqual(self.client.get('/api/admin/access/catalog').status_code,403)
        self.assertEqual(self.save('account','OWNER',{}).status_code,403)

    def test_plan_change_does_not_remove_override(self):
        self.assertEqual(self.save('account','OWNER',{'crm':False,'repair':True}).status_code,200)
        self.assertEqual(self.save('plan','business',{'repair':False,'crm':True}).status_code,200)
        detail=self.client.get('/api/admin/access/account/OWNER').json
        self.assertFalse(detail['effective']['crm']['allowed'])
        self.assertTrue(detail['effective']['repair']['allowed'])
        self.assertEqual(self.save('account','OWNER',{},revision=1).status_code,200)
        detail=self.client.get('/api/admin/access/account/OWNER').json
        self.assertTrue(detail['effective']['crm']['allowed'])
        self.assertFalse(detail['effective']['repair']['allowed'])

    def test_bi_requires_live_developer_role_and_individual_owner_grant(self):
        import json
        from permissions import default_permissions_for
        member=self.cdb.query(CompanyUser).filter_by(user_id='EMP1').one()
        paths=('/bi-intelligence','/bi-dashboard','/api/bi/dashboard','/reports-dashboard')
        for role in ('employee','accountant','manager','hr_admin','hr_staff','payroll_officer','bi_developer'):
            self.assertFalse(default_permissions_for(role)['analytics']['view'])
            member.role=role
            # Old grants must not reopen BI for other roles.
            member.permission_overrides=json.dumps({'analytics':{'view':role!='bi_developer'}})
            self.cdb.commit()
            self.login('EMP1','team-test',role,'A')
            for path in paths:
                self.assertEqual(self.client.get(path,headers={'X-Requested-With':'XMLHttpRequest'}).status_code,403,(role,path))
        member.permission_overrides=json.dumps({'analytics':{'view':True}})
        self.cdb.commit()
        self.assertEqual(self.client.get('/bi-intelligence').status_code,200)
        member.permission_overrides='{}'
        self.cdb.commit()
        self.assertEqual(self.client.get('/bi-intelligence',headers={'X-Requested-With':'XMLHttpRequest'}).status_code,403)
        member.permission_overrides=json.dumps({'analytics':{'view':True}})
        member.role='manager'
        self.cdb.commit()
        self.assertEqual(self.client.get('/api/bi/dashboard').status_code,403)
        self.login('OWNER','owner-test','owner','A')
        self.assertEqual(self.client.get('/bi-intelligence').status_code,200)

    def test_bi_developer_grant_does_not_override_subscription_block(self):
        import json
        member=self.cdb.query(CompanyUser).filter_by(user_id='EMP1').one()
        member.role='bi_developer'
        member.permission_overrides=json.dumps({'analytics':{'view':True}})
        self.cdb.commit()
        db.session.add(PlatformAccessRule(scope='company',target='A',overrides={'bi':False}))
        db.session.commit()
        self.login('EMP1','team-test','bi_developer','A')
        self.assertEqual(self.client.get('/api/bi/dashboard').status_code,403)

    def test_admin_workspace_keeps_admin_role(self):
        r=self.client.post('/api/admin/access/open-company/A',headers={'X-Admin-CSRF':self.token})
        self.assertEqual(r.status_code,200)
        with self.client.session_transaction() as s:
            self.assertEqual(s['user']['role'],'super_admin');self.assertEqual(s['active_company_id'],'A')
        self.assertEqual(self.client.get('/api/core-test').status_code,200)

if __name__=='__main__':unittest.main()

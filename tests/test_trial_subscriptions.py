import ast
import secrets
import unittest
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from flask import Flask, session, request, jsonify, render_template
from flask_mail import Mail
from platform_models import db, RegisteredUser, SubscriptionPlan, PaymentTransaction
from plan_catalog import PUBLIC_PLANS
from module_access import subject_access
from trial_subscriptions import trial_details, send_trial_reminders, register_trial_subscriptions


class TrialSubscriptionTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__,template_folder='../templates')
        self.app.config.update(TESTING=True,SECRET_KEY='test',SQLALCHEMY_DATABASE_URI='sqlite://',PUBLIC_APP_URL='https://test.example')
        self.app.config['MAIL_DEFAULT_SENDER']='support@example.test'
        Mail(self.app)
        db.init_app(self.app);self.ctx=self.app.app_context();self.ctx.push();db.create_all()
        self.start=date(2026,10,1);self.today=self.start+timedelta(days=10)
        db.session.add(SubscriptionPlan(id='finance',name='Finance',price='6999',max_users='5',max_companies='2'))
        self.account=RegisteredUser(user_id='TRIAL',email='owner@example.test',full_name='Owner',password_hash='unused',role='owner',is_active=True,
            subscription_plan='finance',plan_duration='3_years',payment_status='trial',created_at=self.start,amount_total=14997)
        db.session.add(self.account);db.session.commit()
        register_trial_subscriptions(self.app,lambda f:f,lambda:session.get('user',{}),lambda:self.today)
        self.app.add_url_rule('/notice',view_func=lambda:render_template('_trial_notice.html'))
        self.client=self.app.test_client()
        with self.client.session_transaction() as state:state['user']={'role':'owner','email':self.account.email}
        self.mail=Mock()

    def tearDown(self):
        db.session.remove();db.drop_all();self.ctx.pop()

    def test_trial_uses_selected_plan_and_expires(self):
        state=subject_access(self.account,today=self.start+timedelta(days=9))
        self.assertTrue(state['core']['allowed']);self.assertFalse(state['crm']['allowed'])
        self.assertFalse(any(s['allowed'] for s in subject_access(self.account,today=self.start+timedelta(days=15)).values()))
        self.assertEqual(trial_details(self.account,self.today)['amount'],Decimal('14997'))

    def test_email_schedule_is_daily_and_stops_after_expiry_or_payment(self):
        self.assertEqual(send_trial_reminders(self.app,self.mail,self.start+timedelta(days=9)),0)
        for day in range(10,15):
            self.assertEqual(send_trial_reminders(self.app,self.mail,self.start+timedelta(days=day)),1)
            self.assertEqual(send_trial_reminders(self.app,self.mail,self.start+timedelta(days=day)),0)
        self.assertEqual(self.mail.send.call_count,5)
        self.assertIn('14,997.00',self.mail.send.call_args.args[0].body)
        self.assertIn('https://test.example/subscription/trial',self.mail.send.call_args.args[0].body)
        self.assertEqual(send_trial_reminders(self.app,self.mail,self.start+timedelta(days=15)),0)
        self.account.payment_status='paid';db.session.commit()
        self.assertIsNone(trial_details(self.account,self.today))

    def test_failed_email_is_retryable_and_missing_domain_disables_send(self):
        self.app.config['PUBLIC_APP_URL']=''
        self.assertEqual(send_trial_reminders(self.app,self.mail,self.today),0)
        self.mail.send.assert_not_called()
        self.app.config['PUBLIC_APP_URL']='https://test.example'
        self.mail.send.side_effect=RuntimeError('SMTP unavailable')
        self.assertEqual(send_trial_reminders(self.app,self.mail,self.today),0)
        self.assertIsNone(db.session.get(RegisteredUser,self.account.id).last_trial_email_date)
        self.mail.send.side_effect=None
        self.assertEqual(send_trial_reminders(self.app,self.mail,self.today),1)

    def test_notice_once_per_day_and_checkout_after_expiry(self):
        self.assertIn(b'Pay with Razorpay',self.client.get('/notice').data)
        self.assertNotIn(b'Pay with Razorpay',self.client.get('/notice').data)
        self.today+=timedelta(days=1)
        self.assertIn(b'Pay with Razorpay',self.client.get('/notice').data)
        self.today=self.start+timedelta(days=15)
        response=self.client.get('/subscription/trial')
        self.assertEqual(response.status_code,200);self.assertIn(b'14,997.00',response.data)
        self.account.payment_status='paid';db.session.commit()
        self.assertIn(b'No trial payment is due',self.client.get('/subscription/trial').data)

    def test_payment_order_uses_saved_quote_and_rejects_plan_switch(self):
        from platform_models import Company
        tree=ast.parse(Path('app.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='create_payment_order');node.decorator_list=[]
        gateway=Mock();gateway.order.create.return_value={'id':'order_test'}
        ns=dict(request=request,session=session,jsonify=jsonify,RegisteredUser=RegisteredUser,Company=Company,
            PaymentTransaction=PaymentTransaction,db=db,PUBLIC_PLANS=PUBLIC_PLANS,get_current_user=lambda:session.get('user',{}),
            calculate_plan_price=lambda *a,**kw:99999,razorpay_client=gateway,RAZORPAY_KEY_ID='test',secrets=secrets,datetime=datetime)
        exec(compile(ast.Module(body=[node],type_ignores=[]),'checkout','exec'),ns)
        self.app.add_url_rule('/test-payment',view_func=ns['create_payment_order'],methods=['POST'])
        payload=dict(plan_id='finance',duration='3_years',email=self.account.email)
        result=self.client.post('/test-payment',json=payload)
        self.assertEqual(result.status_code,200)
        self.assertEqual(gateway.order.create.call_args.kwargs['data']['amount'],1499700)
        self.assertEqual(self.client.post('/test-payment',json={**payload,'duration':'1_year'}).status_code,400)
        with self.client.session_transaction() as state:state.clear()
        self.assertEqual(self.client.post('/test-payment',json=payload).status_code,401)

if __name__=='__main__':unittest.main()

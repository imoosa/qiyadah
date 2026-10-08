"""Regression checks for super-admin login and first-login password setup."""
import ast
import hashlib
import unittest
from pathlib import Path
from flask import Flask, request, session, flash, redirect, url_for
from platform_models import db, RegisteredUser, Company
from auth_utils import hash_password, verify_password


class SuperAdminAuthTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        self.app.config.update(SECRET_KEY='test-only', SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',TESTING=True)
        db.init_app(self.app)
        self.ctx=self.app.app_context();self.ctx.push();db.create_all()
        self.user=RegisteredUser(user_id='ADMIN-TEST',email='qiyadah',full_name='Qiyadah',role='super_admin',password_hash=hash_password('Temporary-Test-123!'),is_active=True,email_verified=True,must_change_password=True)
        db.session.add(self.user);db.session.commit()
        source=ast.parse(Path('app.py').read_text(encoding='utf-8'))
        nodes=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in ('login','force_change_password')]
        namespace=dict(app=self.app,request=request,session=session,flash=flash,redirect=redirect,url_for=url_for,
            RegisteredUser=RegisteredUser,Company=Company,db=db,hash_password=hash_password,verify_password=verify_password,
            render_template=lambda name,**kw:name,_finish_owner_login=lambda user:redirect('/owner'))
        exec(compile(ast.Module(body=nodes,type_ignores=[]),'app.py','exec'),namespace)
        self.app.add_url_rule('/admin/dashboard',endpoint='admin_dashboard',view_func=lambda:'admin')
        self.client=self.app.test_client()

    def tearDown(self):
        db.session.remove();db.drop_all();db.engine.dispose();self.ctx.pop()

    def test_first_login_changes_password_and_enters_admin_panel(self):
        with self.client.session_transaction() as s:s['active_company_id']='STALE'
        r=self.client.post('/login',data={'email':' QIYADAH ','password':'Temporary-Test-123!'})
        self.assertEqual(r.location,'/force-change-password')
        with self.client.session_transaction() as s:
            self.assertNotIn('user',s);self.assertNotIn('active_company_id',s)
        self.assertEqual(self.client.get('/force-change-password').status_code,200)
        r=self.client.post('/force-change-password',data={'password':'Permanent-Test-456!','confirm_password':'Permanent-Test-456!'})
        self.assertEqual(r.location,'/admin/dashboard')
        self.assertFalse(self.user.must_change_password)
        self.assertTrue(verify_password('Permanent-Test-456!',self.user.password_hash))
        with self.client.session_transaction() as s:self.assertEqual(s['user']['role'],'super_admin')

    def test_invalid_password_does_not_authenticate(self):
        r=self.client.post('/login',data={'email':'qiyadah','password':'incorrect'})
        self.assertEqual(r.status_code,200)
        with self.client.session_transaction() as s:self.assertNotIn('pending_password_change_email',s)

    def test_password_setup_requires_verified_login(self):
        self.assertEqual(self.client.get('/force-change-password').location,'/login')
        self.client.post('/login',data={'email':'qiyadah','password':'Temporary-Test-123!'})
        r=self.client.post('/force-change-password',data={'password':'a','confirm_password':'a'})
        self.assertEqual(r.location,'/force-change-password')
        self.assertTrue(self.user.must_change_password)

    def test_existing_password_hashes_remain_supported(self):
        legacy=hashlib.sha256(b'Legacy-Test-123!').hexdigest()
        self.assertTrue(verify_password('Legacy-Test-123!',legacy))
        self.assertFalse(verify_password('wrong',legacy))
        self.assertFalse(verify_password('wrong','invalid'))

if __name__=='__main__':unittest.main()

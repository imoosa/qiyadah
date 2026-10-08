"""Branch identity and selection rendering without production app startup."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

from flask import Flask, render_template, request, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func


class CompanyBranchTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__, template_folder=str(Path('templates').resolve()))
        self.app.config.update(SQLALCHEMY_DATABASE_URI='sqlite://', SECRET_KEY='test')
        self.db = SQLAlchemy(self.app)
        db = self.db

        class Company(db.Model):
            company_id = db.Column(db.String, primary_key=True)
            company_name = db.Column(db.String)
            branch_name = db.Column(db.String)
            owner_email = db.Column(db.String)
            is_active = db.Column(db.Boolean, default=True)

        self.Company = Company
        tree = ast.parse(Path('app.py').read_text(encoding='utf-8-sig'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'is_company_name_taken')
        ns = dict(Company=Company, func=func)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'branch_helper', 'exec'), ns)
        self.taken = ns['is_company_name_taken']
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        db.session.add(Company(company_id='A', company_name='Qiyadah', branch_name='Dubai', owner_email='owner'))
        db.session.add(Company(company_id='B', company_name='Legacy', branch_name=None, owner_email='owner'))
        db.session.commit()

    def tearDown(self):
        self.db.session.remove()
        self.db.engine.dispose()
        self.context.pop()

    def test_branch_identity_and_owner_scope(self):
        self.assertTrue(self.taken('owner', 'qiyadah', branch_name=' DUBAI '))
        self.assertFalse(self.taken('owner', 'Qiyadah', branch_name='Sharjah'))
        self.assertFalse(self.taken('other', 'Qiyadah', branch_name='Dubai'))
        self.assertFalse(self.taken('owner', 'Qiyadah', 'A', 'Dubai'))
        self.assertTrue(self.taken('owner', 'Legacy', branch_name=''))
        self.db.session.get(self.Company, 'A').is_active = False
        self.db.session.commit()
        self.assertFalse(self.taken('owner', 'Qiyadah', branch_name='Dubai'))

    def test_settings_reject_duplicate_or_oversized_branch_before_changes(self):
        tree = ast.parse(Path('app.py').read_text(encoding='utf-8-sig'))
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'update_company_info')
        node.decorator_list = []
        company = SimpleNamespace(company_id='B', owner_email='owner', company_name='Qiyadah', branch_name='Sharjah')
        ns = dict(request=request, flash=flash, redirect=redirect, url_for=url_for,
                  get_current_company=lambda: 'B', get_company_by_id=lambda cid: company,
                  is_company_name_taken=self.taken)
        exec(compile(ast.Module(body=[node], type_ignores=[]), 'settings', 'exec'), ns)
        self.app.add_url_rule('/settings', 'company_settings', lambda: '')
        for branch in ('Dubai', 'x' * 101):
            with self.app.test_request_context(method='POST', data={'company_name': 'Qiyadah', 'branch_name': branch}):
                response = ns['update_company_info']()
                self.assertEqual(response.location, '/settings')
                self.assertEqual(company.branch_name, 'Sharjah')

    def test_actual_model_persists_branch(self):
        from platform_models import db, Company
        app = Flask('branch_storage')
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
        db.init_app(app)
        with app.app_context():
            Company.__table__.create(db.engine)
            company = Company(company_id='TEST', company_name='Qiyadah', branch_name='Dubai', owner_email='owner')
            db.session.add(company)
            db.session.commit()
            db.session.expire_all()
            self.assertEqual(Company.query.filter_by(company_id='TEST').one().branch_name, 'Dubai')
            db.session.remove()
            db.engine.dispose()

    def test_selection_shows_branch_below_company_and_escapes_input(self):
        for endpoint in ('select_company', 'logout'):
            self.app.add_url_rule('/' + endpoint, endpoint, lambda: '')
        def render(branch):
            company = SimpleNamespace(company_id='A', company_name='Qiyadah', branch_name=branch,
                                      is_active=True, subscription_plan='trial')
            with self.app.test_request_context():
                return render_template('select_company.html', companies=[company], user={'role': 'employee'})
        html = render('Dubai')
        self.assertLess(html.index('<div class="company-name">Qiyadah</div>'), html.index('<div class="company-branch"'))
        self.assertIn('>Dubai</div>', html)
        self.assertNotIn('<div class="company-branch"', render(None))
        self.assertIn('&lt;script&gt;', render('<script>'))
        self.assertNotIn('><script></div>', render('<script>'))


if __name__ == '__main__':
    unittest.main()

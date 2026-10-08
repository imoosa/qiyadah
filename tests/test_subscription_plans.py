import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from flask import Flask, render_template
from plan_catalog import PUBLIC_PLANS, plan_modules, check_location_limits


class SubscriptionPlanTests(unittest.TestCase):
    def test_prices_and_limits_match_public_catalog(self):
        expected=[(5,2,2,6999,14997),(5,2,2,12999,26997),(8,2,2,9999,20997),
                  (10,3,5,14999,29997),(8,2,3,12999,26997),(20,5,10,29999,59997)]
        for plan, values in zip(PUBLIC_PLANS.values(),expected):
            self.assertEqual(tuple(int(plan[k]) for k in ('max_users','max_companies','max_branches','price_1yr','price_3yr')),values)
        self.assertEqual(len(PUBLIC_PLANS), len(expected))
        for key in ('finance', 'finance_workshop', 'finance_crm', 'crm_hr'):
            self.assertFalse(plan_modules(key)['orderflow'])
        self.assertTrue(plan_modules('finance_supply')['orderflow'])
        self.assertTrue(plan_modules('crm_hr')['core'])
        self.assertTrue(all(plan_modules('unified').values()))
        for key, plan in PUBLIC_PLANS.items():
            self.assertTrue(plan_modules(key)['bi'])
            self.assertIn('BI Intelligence', plan['features'])

    def test_company_and_branch_limits_are_distinct(self):
        companies=[SimpleNamespace(company_name='Acme',branch_name='East'),
                   SimpleNamespace(company_name='Acme',branch_name='West')]
        self.assertTrue(check_location_limits(companies,'Other',None,2,2)[0])
        self.assertFalse(check_location_limits(companies,'Acme','North',2,2)[0])
        companies.append(SimpleNamespace(company_name='Other',branch_name=None))
        self.assertFalse(check_location_limits(companies,'Third',None,2,10)[0])

    def test_registration_renders_only_public_prices_and_terms(self):
        app=Flask(__name__,template_folder='../templates');app.secret_key='test'
        for endpoint in ('login','register'):
            app.add_url_rule('/'+endpoint,endpoint,lambda:'')
        plans={key:{**p,'features':p['features'].split(', ')} for key,p in PUBLIC_PLANS.items()}
        plans['trial']=dict(name='Trial',price='0',price_1yr='0',price_3yr='0',price_lifetime='',max_companies='1',max_users_per_company='3',features=[])
        with app.test_request_context('/'):
            html=render_template('register.html',plans=plans)
        self.assertIn('Qiyadah Service',html)
        self.assertIn('Qiyadah Supply',html)
        self.assertIn('Qiyadah Unified',html)
        self.assertIn('26997',html)
        self.assertNotIn('pc-starter',html)
        self.assertIn("if (prTrialEl) prTrialEl.value = key",html)

    def test_public_catalog_excludes_private_and_legacy_plans(self):
        tree=ast.parse(Path('app.py').read_text(encoding='utf-8'))
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='get_all_plans')
        ns={'PUBLIC_PLANS':PUBLIC_PLANS,'get_plan':lambda pid:dict(id=pid)}
        exec(compile(ast.Module(body=[node],type_ignores=[]),'plans','exec'),ns)
        self.assertEqual(list(ns['get_all_plans']()),[*PUBLIC_PLANS,'trial'])

if __name__=='__main__':unittest.main()

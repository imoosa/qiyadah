"""Check logistics removal without starting the application or touching live databases."""
import ast
import json
from pathlib import Path
import re
import unittest
from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]

class LogisticsRemovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = json.loads((ROOT / 'docs/erp-logistics-removal.json').read_text())
        cls.tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8-sig'))
        cls.functions = {n.name for n in cls.tree.body if isinstance(n, ast.FunctionDef)}
        cls.rules = {ast.literal_eval(n.args[0]) for n in ast.walk(cls.tree)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and n.func.attr == 'route' and n.args and isinstance(n.args[0], ast.Constant)}

    def test_removed_routes_have_no_aliases(self):
        for route in self.audit['removed_routes']:
            self.assertNotIn(route['path'], self.rules)
            self.assertNotIn(route['endpoint'], self.functions)

    def test_financial_routes_remain(self):
        for endpoint in ('customer_invoice_list', 'customer_invoice_new', 'customer_invoice_create',
                         'customer_invoice_edit', 'customer_invoice_view', 'customer_invoice_print',
                         'purchase_invoice_list', 'purchase_invoice_new', 'purchase_invoice_edit',
                         'purchase_make_payment', 'receipt_save', 'payment_save', 'ledger'):
            self.assertIn(endpoint, self.functions)

    def test_retained_templates_do_not_link_removed_endpoints(self):
        removed = {r['endpoint'] for r in self.audit['removed_routes']}
        for path in (ROOT / 'templates').rglob('*.html'):
            source = path.read_text(encoding='utf-8-sig')
            endpoints = set(re.findall(r"url_for\(\s*['\"]([^'\"]+)", source))
            self.assertFalse(endpoints & removed, str(path))
            self.assertNotIn('/logistics/', source, str(path))

    def test_logistics_files_are_removed(self):
        for name in self.audit['deleted_templates']:
            self.assertFalse((ROOT / 'templates' / name).exists())
        for name in self.audit['deleted_files']:
            self.assertFalse((ROOT / name).exists())

    def test_changed_templates_parse(self):
        env = Environment()
        for name in ('base.html', 'company_settings.html', 'purchases.html'):
            env.parse((ROOT / 'templates' / name).read_text(encoding='utf-8-sig'))

    def test_shipping_quote_removed_from_assistant(self):
        for name in ('query_engine.py', 'intent_router.py', 'ai_assistant.py'):
            source = (ROOT / 'utils' / name).read_text(encoding='utf-8-sig')
            ast.parse(source)
            self.assertNotIn('calculate_rate_quote', source)

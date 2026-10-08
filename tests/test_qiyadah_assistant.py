"""Assistant regression checks with isolated SQLite and no app startup or Ollama."""
import ast
import re
from datetime import date, timedelta
from pathlib import Path
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from customer_models import CustomerInvoice, CustomerInvoiceItem, Client, PurchaseInvoice, Expense
from utils import query_engine as queries
from utils.ai_assistant import QiyadahAIAssistant
from utils.assistant_catalog import CATEGORIES, GUIDES, guide_data
from utils.intent_router import classify_intent, dispatch, _clean_identifier


class AssistantRoutingTests(unittest.TestCase):
    def test_chat_examples_are_supported_and_erp_only(self):
        source = Path('templates/base.html').read_text(encoding='utf-8-sig')
        for question in re.findall(r'data-q="([^"]+)"', source):
            self.assertIsNotNone(classify_intent(question), question)
        for obsolete in ('Track AWB', 'Calculate rate', 'country_bookings_summary', 'awb_detail'):
            self.assertNotIn(obsolete, source)
        self.assertEqual(classify_intent('Today’s sales'), 'todays_sales')

    def test_every_catalog_question_has_a_route(self):
        for _, _, questions in CATEGORIES:
            for question in questions:
                with self.subTest(question=question):
                    self.assertIsNotNone(classify_intent(question))

    def test_specific_keywords_and_word_boundaries(self):
        cases = {"Sales this month": "sales_summary", "Total purchases this month": "purchase_summary",
                 "salary expenses": "expenses_category", "top 5 customers": "top_clients_sales",
                 "What is my GST payable?": "gst_summary", "salesman": None,
                 "unpaid purchase invoices": "pending_payables", "bank reconciliation": "accounting_checks_guide",
                 "How to manage leads?": "crm_guide", "How does payroll work?": "hr_guide"}
        for question, expected in cases.items():
            with self.subTest(question=question):
                self.assertEqual(classify_intent(question), expected)
        self.assertEqual(_clean_identifier("sales invoice SI-001"), "SI-001")

    def test_logistics_requests_do_not_query_records(self):
        ai = QiyadahAIAssistant()
        with patch.object(queries, 'get_customer_session', side_effect=AssertionError('Database used')):
            for question in ('Track AWB 123', 'Show bookings', 'Pending manifests', 'Courier rates'):
                answer = ai.chat(question, 'A', lambda *_: True)
                self.assertEqual(answer['intent'], 'unsupported_logistics')
                self.assertIn('separate logistics', answer['response'])

    def test_guides_work_without_database_or_model(self):
        ai = QiyadahAIAssistant()
        with patch.object(queries, 'get_customer_session', side_effect=AssertionError('Database used')), \
             patch('utils.ai_assistant.ollama.chat', side_effect=AssertionError('Model used')):
            for intent, (_, _, _, phrases) in GUIDES.items():
                result = ai.chat(phrases[0], 'A', lambda *_: True)
                self.assertEqual(result['intent'], intent)
                self.assertIn(guide_data(intent)['path'], result['response'])

    def test_guide_paths_exist(self):
        rules = set()
        for path in Path('.').glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))
            for n in ast.walk(tree):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'route' and n.args and isinstance(n.args[0], ast.Constant):
                    rules.add(n.args[0].value)
        rules.add('/finance/credit-notes')  # constrained kind in /finance/<kind>-notes
        for _, path, _, _ in GUIDES.values():
            self.assertIn(path, rules)

    def test_permissions_checked_before_dispatch(self):
        with patch('utils.intent_router.dispatch') as run:
            for question in ('Sales this month', 'Find client Example', 'Who owes me money?', 'Business summary'):
                result = QiyadahAIAssistant().chat(question, 'A', lambda *_: False)
                self.assertEqual(result['source'], 'permission_denied')
            run.assert_not_called()

    def test_composite_permission_denial(self):
        with patch('utils.intent_router.dispatch') as run:
            result = QiyadahAIAssistant().chat('Business summary', 'A', lambda module, _: module != 'bank')
            self.assertEqual(result['source'], 'permission_denied')
            run.assert_not_called()

    def test_missing_company_and_permission_fail_closed(self):
        ai = QiyadahAIAssistant()
        self.assertEqual(ai.chat('Sales', '', lambda *_: True)['source'], 'error')
        self.assertEqual(ai.chat('Sales', 'A')['source'], 'error')

    def test_no_cross_request_model_history(self):
        ai = QiyadahAIAssistant()
        with patch('utils.ai_assistant.ollama.chat', return_value={'message': {'content': 'An explanation.'}}) as model:
            ai._general_answer('first company private phrase')
            ai._general_answer('second company question')
            self.assertNotIn('first company', str(model.call_args.kwargs['messages']))

    def test_query_error_does_not_invent_an_answer(self):
        with patch('utils.intent_router.dispatch', side_effect=RuntimeError('private connection details')):
            result = QiyadahAIAssistant().chat('Sales this month', 'A', lambda *_: True)
            self.assertEqual(result['source'], 'error')
            self.assertNotIn('private connection', result['response'])


class AssistantInvoiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        # No legacy booking table exists: using it fails these tests.
        for model in (CustomerInvoice, CustomerInvoiceItem, Client, PurchaseInvoice, Expense):
            model.__table__.create(self.engine)
        self.db = Session(self.engine)
        today = date.today()
        for number, company, status, total, invoice_date in (
            ('SI-1', 'A', 'Pending', 150, today), ('SI-2', 'A', 'Draft', 2000, today),
            ('SI-3', 'A', 'Cancelled', 3000, today), ('SI-4', 'B', 'Pending', 5000, today),
            ('SI-5', 'A', 'Pending', 50, today - timedelta(days=90))):
            self.db.add(CustomerInvoice(invoice_number=number, company_id=company, client_name='Test customer',
                status=status, grand_total=total, balance=total, invoice_date=invoice_date,
                due_date=today-timedelta(days=1), tax_amount=10, cgst_total=0, sgst_total=0, igst_total=10))
        self.db.commit()
        self.session_patch = patch.object(queries, 'get_customer_session', return_value=self.db)
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()
        self.db.close()
        self.engine.dispose()

    def test_sales_are_current_erp_documents_only(self):
        result = queries.get_sales_summary('A')
        self.assertEqual(result['total_sales'], 200)
        self.assertEqual(result['invoice_count'], 2)
        result = dispatch('Sales this month', 'A')
        self.assertEqual(result['total_sales'], 150)

    def test_today_excludes_drafts_cancelled_and_other_company(self):
        result = queries.get_todays_sales('A')
        self.assertEqual(result['total_sales'], 150)
        self.assertEqual(result['items'][0]['invoice_id'], 'SI-1')
        self.assertNotIn('docket_no', result['items'][0])

    def test_customer_invoice_summary_uses_calendar_month(self):
        result = dispatch('Customer invoices this month', 'A')
        self.assertEqual(result['total_value'], 150)
        self.assertEqual(result['count'], 1)
        self.assertEqual(result['start_date'], str(date.today().replace(day=1)))

    def test_overdue_count_is_not_capped_to_preview(self):
        result = queries.get_overdue_invoices('A', limit=1)
        self.assertEqual(result['count'], 2)
        self.assertEqual(result['total_overdue'], 200)
        self.assertEqual(len(result['items']), 1)

    def test_invoice_lookup_and_missing_lookup(self):
        result = dispatch('sales invoice SI-1', 'A')
        self.assertTrue(result['found'])
        result = dispatch('sales invoice SI-4', 'A')
        self.assertFalse(result['found'])
        self.assertEqual(result['intent'], 'invoice_detail')

    def test_invoice_lines_use_product_fields(self):
        invoice = self.db.query(CustomerInvoice).filter_by(invoice_number='SI-1').one()
        self.db.add(CustomerInvoiceItem(customer_invoice_id=invoice.id, item_name='Widget', quantity=2, rate=75, total_amount=150))
        self.db.commit()
        result = dispatch('Find customer invoice SI-1', 'A')
        self.assertEqual(result['items'][0]['item_name'], 'Widget')
        self.assertNotIn('docket_no', result['items'][0])

    def test_tax_uses_actual_recorded_components(self):
        result = queries.get_gst_summary('A', start_date=date.today(), end_date=date.today())
        self.assertEqual(result['output_gst'], 10)
        self.assertEqual(result['cgst'], 0)
        self.assertEqual(result['igst'], 10)

    def test_gross_comparison_no_undefined_variable(self):
        self.assertEqual(queries.get_gross_profit_summary('A')['gross_profit'], 200)

    def test_record_answers_work_without_model(self):
        with patch('utils.ai_assistant.ollama.chat', side_effect=AssertionError('Model used')):
            result = QiyadahAIAssistant().chat("Today's sales", 'A', lambda *_: True)
            self.assertEqual(result['source'], 'query_engine')
            self.assertEqual(result['data']['total_sales'], 150)

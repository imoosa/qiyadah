"""Exercise note posting with the real journal functions and plain SQLAlchemy."""
import ast
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from pathlib import Path
import unittest
from uuid import uuid4

from flask import Flask, abort
from jinja2 import ChoiceLoader, DictLoader
from sqlalchemy import create_engine, func, or_
from sqlalchemy.orm import Session
from customer_models import CustomerInvoice, PurchaseInvoice, FinanceNote, ChartOfAccount, JournalEntry, JournalEntryLine
from customer_models import Client, Supplier, Invoice, CashTransaction, BankTransaction, WorkshopJobCard, BankAccount, Expense
from finance_dashboard import source_documents
from finance_notes import register_finance_notes, money, note_statement_events


class FinanceNoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = {'_money', '_next_journal_number', '_existing_source_journal', '_post_auto_journal', '_reverse_source_journal', '_debtor_summary', '_creditor_summary'}
        tree = ast.parse(Path('app.py').read_text(encoding='utf-8-sig'))
        cls.functions = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[])

    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        for model in (CustomerInvoice, PurchaseInvoice, FinanceNote, ChartOfAccount, JournalEntry, JournalEntryLine,
                      Client, Supplier, Invoice, CashTransaction, BankTransaction, WorkshopJobCard, BankAccount, Expense):
            model.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.allowed = True
        self.company = 'A'
        self.app = Flask(__name__, template_folder='../templates')
        self.app.secret_key = 'notes-test'
        self.app.testing = True
        self.app.jinja_loader = ChoiceLoader([DictLoader({'base.html': '{% for category, text in get_flashed_messages(with_categories=true) %}{{ text }}{% endfor %}{% block extra_style %}{% endblock %}{% block content %}{% endblock %}'}), self.app.jinja_loader])
        def permission(module, action):
            def decorate(fn):
                @wraps(fn)
                def wrapped(*args, **kwargs):
                    if not self.allowed:
                        abort(403)
                    return fn(*args, **kwargs)
                return wrapped
            return decorate
        # Load only production accounting functions, avoiding application startup.
        scope = dict(Decimal=Decimal, InvalidOperation=InvalidOperation, ROUND_HALF_UP=ROUND_HALF_UP,
                     _MONEY_Q=Decimal('0.01'), JournalEntry=JournalEntry, JournalEntryLine=JournalEntryLine,
                     datetime=datetime, today_ist=date.today, get_current_user=lambda: {'email': 'test@example.com'},
                     _ensure_journal_tables=lambda db: None,
                     _coa_by_code=lambda db, company, code: db.query(ChartOfAccount).filter_by(company_id=company, code=code).one())
        exec(compile(self.functions, 'accounting_functions', 'exec'), scope)
        scope.update(Client=Client, Supplier=Supplier, Invoice=Invoice, CustomerInvoice=CustomerInvoice,
                     PurchaseInvoice=PurchaseInvoice, CashTransaction=CashTransaction, BankTransaction=BankTransaction,
                     func=func, or_=or_, get_cdb=lambda: self.db, note_statement_events=note_statement_events,
                     _used_booking_ids_in_customer_invoices=lambda *args: set(), _get_awb=lambda inv: None)
        self.accounting = scope
        register_finance_notes(self.app, lambda fn: fn, permission, lambda: self.db, lambda: self.company,
                               lambda *args: self.allowed, scope['_post_auto_journal'], scope['_reverse_source_journal'])
        self.app.add_url_rule('/invoice/<int:cust_inv_id>', 'customer_invoice_view', lambda **kw: '')
        self.app.add_url_rule('/purchase/<invoice_id>', 'purchase_invoice_view', lambda **kw: '')
        for code in ('1300', '4100', '4200', '2200', '2100', '5100', '1500'):
            self.db.add(ChartOfAccount(company_id='A', code=code, name=code, account_type='Asset', account_group='Current Assets', normal_balance='Debit'))
        self.sale = CustomerInvoice(company_id='A', invoice_number='S1', client_name='Customer', client_id=1,
                                    invoice_date=date.today(), subtotal=1000, tax_amount=180, grand_total=1180, balance=1180)
        self.purchase = PurchaseInvoice(company_id='A', invoice_id='P1', supplier_name='Supplier', supplier_id=1,
                                        date=date.today(), subtotal=1000, tax_amount=180, grand_total=1180, balance=1180)
        self.db.add_all([self.sale, self.purchase])
        self.db.add_all([Client(id=1, company_id='A', name='Customer'), Supplier(id=1, company_id='A', name='Supplier')])
        self.db.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def data(self, **values):
        result = dict(invoice_id=self.sale.id, subtotal='100', tax_amount='18', note_date=date.today().isoformat(),
                      reason='Damaged goods', request_token=uuid4().hex)
        result.update(values)
        return result

    def test_credit_post_duplicate_payment_and_void(self):
        data = self.data()
        response = self.client.post('/finance/credit-notes/new', data=data)
        self.assertEqual(response.status_code, 302)
        note = self.db.query(FinanceNote).one()
        self.assertEqual(self.sale.balance, 1062)
        self.assertEqual(self.sale.paid_amount, 0)
        entry = self.db.query(JournalEntry).one()
        self.assertEqual(sum(line.debit for line in entry.lines), Decimal('118'))
        self.assertEqual(sum(line.credit for line in entry.lines), Decimal('118'))
        self.client.post('/finance/credit-notes/new', data=data)
        self.assertEqual(self.db.query(FinanceNote).count(), 1)
        self.assertEqual(self.db.query(JournalEntry).count(), 1)
        self.sale.paid_amount = 62
        self.sale.balance = 1118  # A legacy receipt route's total-minus-paid calculation.
        self.db.commit()
        self.assertEqual(self.sale.balance, 1000)
        self.assertIn(b'CN-', self.client.get(response.location).data)
        self.client.post(f'/finance/credit-notes/{note.id}/void', data={'reason': 'Correction'})
        self.assertEqual(self.sale.balance, 1118)
        self.assertEqual(note.status, 'Void')
        self.assertEqual(self.db.query(JournalEntry).count(), 2)
        self.client.post(f'/finance/credit-notes/{note.id}/void', data={'reason': 'Again'})
        self.assertEqual(self.db.query(JournalEntry).count(), 2)
        events = note_statement_events(self.db, 'A', 'credit', 1)
        self.assertEqual(sum(e['debit'] - e['credit'] for e in events), 0)

    def test_debit_note_and_currency_posting(self):
        self.purchase.exchange_rate = 2
        self.db.commit()
        response = self.client.post('/finance/debit-notes/new', data=self.data(invoice_id=self.purchase.id))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.purchase.balance, 1062)
        self.assertEqual(self.purchase.base_balance, 2124)
        entry = self.db.query(JournalEntry).one()
        rows = {line.account.code: (line.debit, line.credit) for line in entry.lines}
        self.assertEqual(rows['2100'], (Decimal('236'), Decimal('0')))
        self.assertEqual(rows['5100'], (Decimal('0'), Decimal('200')))
        self.assertEqual(rows['1500'], (Decimal('0'), Decimal('36')))

    def test_invalid_amounts_and_source_status(self):
        for values in ({'subtotal': '-1'}, {'subtotal': 'NaN'}, {'subtotal': 'Infinity'}, {'subtotal': '1200'},
                       {'subtotal': '0', 'tax_amount': '181'}, {'reason': ''}, {'note_date': 'bad'}):
            response = self.client.post('/finance/credit-notes/new', data=self.data(**values))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(self.db.query(FinanceNote).count(), 0)
        self.sale.status = 'Void'
        self.db.commit()
        self.client.post('/finance/credit-notes/new', data=self.data())
        self.assertEqual(self.db.query(FinanceNote).count(), 0)

    def test_permissions_company_and_get_safety(self):
        self.allowed = False
        self.assertEqual(self.client.get('/finance/credit-notes').status_code, 403)
        self.assertEqual(self.client.post('/finance/debit-notes/new', data=self.data()).status_code, 403)
        self.allowed = True
        self.company = 'B'
        self.assertEqual(self.client.post('/finance/credit-notes/new', data=self.data()).status_code, 404)
        self.company = 'A'
        for path in ('/finance/credit-notes', '/finance/debit-notes', '/finance/credit-notes/new', '/finance/debit-notes/new'):
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.db.query(FinanceNote).count(), 0)

    def test_posting_failure_is_atomic(self):
        self.db.query(ChartOfAccount).filter_by(code='2200').delete()
        self.db.commit()
        with self.assertRaises(Exception):
            self.client.post('/finance/credit-notes/new', data=self.data())
        self.assertEqual(self.db.query(FinanceNote).count(), 0)
        self.assertEqual(self.sale.balance, 1180)
        self.assertEqual(self.sale.note_adjustment, 0)

    def test_dashboard_and_party_balances_include_adjustments(self):
        self.client.post('/finance/credit-notes/new', data=self.data())
        self.client.post('/finance/debit-notes/new', data=self.data(invoice_id=self.purchase.id))
        rows = source_documents(self.db, 'A', lambda *args: True)
        sales = [r for r in rows if r['kind'] == 'sales']
        purchases = [r for r in rows if r['kind'] == 'purchase']
        self.assertEqual(sum(r['total'] for r in sales), Decimal('1062'))
        self.assertEqual(sum(r['tax'] for r in purchases), Decimal('162'))
        self.assertEqual(self.accounting['_debtor_summary']('A')[0]['total_pending'], 1062)
        self.assertEqual(self.accounting['_creditor_summary']('A')[0]['total_pending'], 1062)

if __name__ == '__main__':
    unittest.main()

"""Accounting diagnostics and real draft-posting route, without app startup."""
import ast
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from pathlib import Path
import unittest

from flask import Flask, abort, flash, redirect, session, url_for
from jinja2 import ChoiceLoader, DictLoader
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from customer_models import ChartOfAccount, JournalEntry, JournalEntryLine, CustomerInvoice, PurchaseInvoice
from customer_models import CashTransaction, BankTransaction, BankAccount
from customer_models import Client, Supplier, StatementClosing, Invoice
from finance_checks import accounting_checks, register_finance_checks


class AccountingCheckTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        for model in (ChartOfAccount, JournalEntry, JournalEntryLine, CustomerInvoice, PurchaseInvoice,
                      CashTransaction, BankAccount, BankTransaction, Client, Supplier, StatementClosing, Invoice):
            model.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.company = 'A'
        self.allowed = True
        self.denied = set()
        self.accounts = [ChartOfAccount(company_id=c, code=str(i), name='Account', account_type='Asset',
                                        account_group='Assets', normal_balance='Debit')
                         for i, c in enumerate(('A', 'A', 'B'))]
        self.db.add_all(self.accounts)
        self.db.commit()
        self.app = Flask(__name__, template_folder='../templates')
        self.app.secret_key = 'checks-test'
        self.app.testing = True
        self.app.jinja_loader = ChoiceLoader([DictLoader({'base.html': '{% block extra_style %}{% endblock %}{% block content %}{% endblock %}'}), self.app.jinja_loader])
        def permission(module, action):
            def decorate(fn):
                @wraps(fn)
                def wrapped(*args, **kwargs):
                    if not self.allowed:
                        abort(403)
                    return fn(*args, **kwargs)
                return wrapped
            return decorate
        self.permission = permission
        register_finance_checks(self.app, lambda fn: fn, permission, lambda: self.db, lambda: self.company, self.can)
        for endpoint, rule in [('finance_workspace', '/finance'), ('journal_entry_view', '/journals/<int:entry_id>'),
                               ('customer_invoice_view', '/invoice/<int:cust_inv_id>'), ('purchase_invoice_view', '/purchase/<invoice_id>'),
                               ('repair_bills_view', '/repair-bills'), ('chart_of_accounts', '/accounts'),
                               ('receipt_new', '/receipts'), ('payment_new', '/payments'),
                               ('bank_transactions', '/bank/<int:account_id>')]:
            self.app.add_url_rule(rule, endpoint, lambda **kw: '')
        self.client = self.app.test_client()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def can(self, module, action):
        return module not in self.denied

    def journal(self, **values):
        data = dict(company_id='A', entry_no='J'+str(self.db.query(JournalEntry).count()),
                    entry_date=date.today(), narration='Test', source_type='manual', status='Posted')
        data.update(values)
        entry = JournalEntry(**data)
        entry.lines = [JournalEntryLine(account_id=self.accounts[0].id, debit=100, credit=0),
                       JournalEntryLine(account_id=self.accounts[1].id, debit=0, credit=100)]
        self.db.add(entry)
        self.db.commit()
        return entry

    def invoice(self, **values):
        data = dict(company_id='A', invoice_number='S'+str(self.db.query(CustomerInvoice).count()),
                    grand_total=100, subtotal=100, status='Pending')
        data.update(values)
        inv = CustomerInvoice(**data)
        self.db.add(inv)
        self.db.commit()
        return inv

    def report(self):
        return accounting_checks(self.db, self.company, self.can)

    def test_clean_invoice_and_reversal_history(self):
        inv = self.invoice()
        self.journal(source_type='sales_invoice', source_id=str(inv.id), status='Reversed')
        self.journal(source_type='reversal', source_id='1')
        self.journal(source_type='sales_invoice', source_id=str(inv.id))
        self.assertEqual(self.report()['issues'], [])

    def test_missing_duplicate_mismatch_and_cancelled(self):
        inv = self.invoice()
        self.assertEqual(self.report()['counts']['Missing invoice posting'], 1)
        entry = self.journal(source_type='sales_invoice', source_id=str(inv.id))
        inv.base_grand_total = 200
        self.db.commit()
        self.assertEqual(self.report()['counts']['Invoice total mismatch'], 1)
        self.journal(source_type='sales_invoice', source_id=str(inv.id))
        self.assertEqual(self.report()['counts']['Duplicate posting'], 1)
        inv.status = 'Cancelled'
        self.db.commit()
        self.assertEqual(self.report()['counts']['Inactive invoice posted'], 1)

    def test_invalid_lines_unbalanced_and_foreign_account(self):
        entry = self.journal()
        entry.lines[0].credit = 2
        entry.lines[1].account_id = self.accounts[2].id
        self.db.commit()
        counts = self.report()['counts']
        for kind in ('Invalid journal line', 'Invalid account', 'Unbalanced journal'):
            self.assertEqual(counts[kind], 1)

    def test_company_permissions_and_no_mutations(self):
        self.invoice(company_id='B', invoice_number='PRIVATE')
        self.invoice(invoice_category='workshop_repair')
        self.denied.add('customer_invoices')
        self.assertEqual(self.report()['checked']['invoices'], 0)
        before = self.db.query(JournalEntry).count()
        response = self.client.get('/finance/accounting-checks')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(b'PRIVATE', response.data)
        self.assertEqual(self.db.query(JournalEntry).count(), before)
        self.allowed = False
        self.assertEqual(self.client.get('/finance/accounting-checks').status_code, 403)
        self.allowed = True
        self.company = None
        self.assertEqual(self.client.get('/finance/accounting-checks').status_code, 403)

    def test_currency_and_separate_adjustments(self):
        inv = self.invoice(grand_total=50, exchange_rate=2, note_adjustment=10, paid_amount=20)
        self.journal(source_type='sales_invoice', source_id=str(inv.id))
        self.assertEqual(self.report()['issues'], [])

    def test_drafts_and_zero_invoices(self):
        self.invoice(status='Draft')
        self.invoice(grand_total=0)
        self.journal(status='Draft')
        self.assertEqual(dict(self.report()['counts']), {'Draft journal': 1})

    def test_missing_tables_are_not_created(self):
        JournalEntryLine.__table__.drop(self.engine)
        report = self.report()
        self.assertFalse(report['complete'])
        self.assertNotIn('journal_entry_lines', inspect(self.engine).get_table_names())

    def test_filter_pagination_and_escaping(self):
        for i in range(51):
            self.invoice(invoice_number=f'<script>{i}</script>')
        response = self.client.get('/finance/accounting-checks?page=2&check=Missing+invoice+posting')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Page 2 of 2', response.data)
        self.assertIn(b'&lt;script&gt;50', response.data)
        self.assertNotIn(b'<script>', response.data)
        self.assertEqual(self.client.get('/finance/accounting-checks?check=unknown').status_code, 400)

    def load_post_route(self):
        tree = ast.parse(Path('app.py').read_text(encoding='utf-8-sig'))
        names = {'_money', '_validate_journal_lines', 'journal_entry_post'}
        module = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[])
        scope = dict(app=self.app, login_required=lambda fn: fn, require_permission=self.permission,
                     get_cdb=lambda: self.db, get_current_company=lambda: self.company,
                     _ensure_journal_tables=lambda db: None, ChartOfAccount=ChartOfAccount,
                     JournalEntry=JournalEntry, Decimal=Decimal, InvalidOperation=InvalidOperation,
                     ROUND_HALF_UP=ROUND_HALF_UP, _MONEY_Q=Decimal('0.01'),
                     abort=abort, flash=flash, redirect=redirect, url_for=url_for, session=session, datetime=datetime)
        exec(compile(module, 'real_posting_route', 'exec'), scope)

    def cash(self, **values):
        data = dict(company_id='A', type='income', category='Receipt', description='Receipt',
                    amount=100, date=date.today())
        data.update(values)
        txn = CashTransaction(**data)
        self.db.add(txn)
        self.db.commit()
        return txn

    def bank(self, **values):
        data = dict(company_id='A', bank_name='Test bank', account_name='Business', account_number='123',
                    opening_balance=100, balance=100)
        data.update(values)
        bank = BankAccount(**data)
        self.db.add(bank)
        self.db.commit()
        return bank

    def bank_txn(self, bank, **values):
        data = dict(company_id='A', bank_account_id=bank.id, type='credit', amount=100,
                    description='Opening Balance for Test bank - Business', reference='Opening Balance')
        data.update(values)
        txn = BankTransaction(**data)
        self.db.add(txn)
        self.db.commit()
        return txn

    def test_opening_balance_signs_and_inactive_accounts(self):
        self.accounts[0].opening_balance = 100
        self.accounts[1].normal_balance = 'Credit'
        self.accounts[1].opening_balance = 100
        self.accounts[2].opening_balance = 999  # other company
        self.db.commit()
        self.assertEqual(self.report()['issues'], [])
        self.accounts[1].opening_balance = 90
        self.accounts[0].is_active = False
        self.db.commit()
        counts = self.report()['counts']
        self.assertEqual(counts['Opening balances unbalanced'], 1)
        self.assertEqual(counts['Inactive opening account'], 1)
        response = self.client.get('/finance/accounting-checks')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'10.00', response.data)

    def test_missing_and_correct_advance_posting(self):
        txn = self.cash()
        self.assertEqual(self.report()['counts']['Missing settlement posting'], 1)
        self.accounts[0].code = '1100'
        self.accounts[1].code = '2500'
        self.db.commit()
        entry = self.journal(source_type='receipt_cash', source_id=str(txn.id))
        self.assertEqual(self.report()['issues'], [])
        txn.applied_ci_id = 123
        self.db.add(CustomerInvoice(id=123, company_id='A', invoice_number='LINK123', grand_total=0))
        self.db.commit()
        self.assertEqual(self.report()['counts']['Settlement posting mismatch'], 1)
        self.accounts[1].code = '1300'
        self.db.commit()
        self.assertEqual(self.report()['issues'], [])
        entry.entry_date = date(2000, 1, 1)
        self.db.commit()
        self.assertEqual(self.report()['counts']['Settlement date mismatch'], 1)

    def test_payment_mapping_allocations_and_reversed_source(self):
        self.db.add(PurchaseInvoice(id=1, company_id='A', invoice_id='LINKP1', grand_total=0, paid_amount=100))
        self.db.commit()
        txn = self.cash(type='expense', category='Payment', applied_ref_type='purchase_invoice',
                        applied_breakdown_json='{"1": 101}')
        self.accounts[0].code = '2100'
        self.accounts[1].code = '1100'
        self.db.commit()
        entry = self.journal(source_type='payment_cash', source_id=str(txn.id))
        self.assertEqual(self.report()['counts']['Invalid settlement allocation'], 1)
        for value in ('bad', '[]', '{"1": "NaN"}', '{"1": -10}'):
            txn.applied_breakdown_json = value
            self.db.commit()
            self.assertEqual(self.report()['counts']['Invalid settlement allocation'], 1)
        txn.applied_breakdown_json = '{"1": 100}'
        self.db.commit()
        self.assertEqual(self.report()['issues'], [])
        entry.status = 'Reversed'
        self.db.commit()
        self.assertEqual(self.report()['counts']['Missing settlement posting'], 1)

    def test_orphan_and_multiple_settlement_postings(self):
        txn = self.cash()
        self.journal(source_type='receipt_cash', source_id=str(txn.id))
        self.journal(source_type='payment_cash', source_id=str(txn.id))
        self.assertEqual(self.report()['counts']['Multiple settlement postings'], 1)
        self.db.delete(txn)
        self.db.commit()
        self.assertEqual(self.report()['counts']['Missing settlement source'], 2)

    def test_bank_opening_mirror_counted_once(self):
        bank = self.bank(balance=130)
        self.bank_txn(bank)
        self.bank_txn(bank, reference=None, description='Other credit', amount=50)
        self.bank_txn(bank, type='debit', reference=None, description='Expense', amount=20)
        self.assertEqual(self.report()['issues'], [])
        self.assertEqual(self.report()['checked']['unclassified_bank_movements'], 3)
        bank.balance = 230
        self.db.commit()
        self.assertEqual(self.report()['counts']['Bank balance mismatch'], 1)
        self.bank_txn(bank)
        counts = self.report()['counts']
        self.assertEqual(counts['Bank opening needs review'], 1)
        self.assertEqual(counts['Bank balance mismatch'], 0)

    def test_bank_without_mirror_and_invalid_movement(self):
        bank = self.bank(opening_balance=-100, balance=-70)
        self.bank_txn(bank, description='Deposit', reference=None, amount=30)
        self.assertEqual(self.report()['issues'], [])
        self.bank_txn(bank, description='Unknown', reference=None, type='unknown')
        self.assertEqual(self.report()['counts']['Bank movement needs review'], 1)

    def test_settlement_permissions_and_company_isolation(self):
        self.cash(company_id='B')
        self.assertEqual(self.report()['checked']['settlements'], 0)
        self.cash()
        self.denied.add('receipts_payments')
        self.assertEqual(self.report()['checked']['settlements'], 0)
        self.denied.clear()
        self.denied.add('cash')
        self.assertEqual(self.report()['checked']['settlements'], 0)
        self.denied.add('bank')
        bank = self.bank(balance=999)
        self.assertEqual(self.report()['checked']['bank_accounts'], 0)

    def test_bank_structural_receipt_and_missing_bank_source(self):
        self.db.add(CustomerInvoice(id=9, company_id='A', invoice_number='LINK9', grand_total=0))
        self.db.commit()
        bank = self.bank(opening_balance=0, balance=100)
        txn = self.bank_txn(bank, reference=None, description='Receipt', applied_ci_id=9)
        self.assertEqual(self.report()['counts']['Missing settlement posting'], 1)
        self.accounts[0].code = '1200'
        self.accounts[1].code = '1300'
        self.db.commit()
        self.journal(source_type='receipt_bank', source_id=str(txn.id))
        self.assertEqual(self.report()['issues'], [])

    def test_post_revalidates_accounts_and_lines(self):
        self.load_post_route()
        entry = self.journal(status='Draft')
        # Equal totals do not make a foreign-company account valid.
        entry.lines[0].account_id = self.accounts[2].id
        self.db.commit()
        self.client.post(f'/finance/journals/{entry.id}/post')
        self.assertEqual(entry.status, 'Draft')
        entry.lines[0].account_id = self.accounts[0].id
        self.accounts[0].is_active = False
        self.db.commit()
        self.client.post(f'/finance/journals/{entry.id}/post')
        self.assertEqual(entry.status, 'Draft')
        self.accounts[0].is_active = True
        entry.lines[0].credit = 10
        entry.lines[1].debit = 10
        self.db.commit()
        self.client.post(f'/finance/journals/{entry.id}/post')
        self.assertEqual(entry.status, 'Draft')
        entry.lines[0].credit = 0
        entry.lines[1].debit = 0
        self.db.commit()
        self.client.post(f'/finance/journals/{entry.id}/post')
        self.assertEqual(entry.status, 'Posted')


if __name__ == '__main__':
    unittest.main()

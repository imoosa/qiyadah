"""Period locks, atomic rollback, audited changes and owner/CSRF controls."""
from datetime import date
from functools import wraps
import unittest
from flask import Flask, abort
from jinja2 import ChoiceLoader, DictLoader
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from customer_models import (ChartOfAccount, JournalEntry, JournalEntryLine, CustomerInvoice,
    CustomerInvoiceItem, CashTransaction, Client, FinancePeriodControl, FinancePeriodAudit)
from finance_periods import setup_period_control, change_period, ClosedPeriodError, register_finance_periods


class PeriodTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        for model in (ChartOfAccount, JournalEntry, JournalEntryLine, CustomerInvoice, CustomerInvoiceItem, CashTransaction, Client):
            model.__table__.create(self.engine)
        setup_period_control(self.engine, 'A')
        setup_period_control(self.engine, 'B')
        self.db = Session(self.engine, info={'finance_period_company': 'A'})
        self.today = date(2026, 10, 3)
        self.old = date(2026, 9, 30)
        self.sale = CustomerInvoice(company_id='A', invoice_number='S1', invoice_date=self.old, grand_total=100, balance=100)
        self.db.add(self.sale)
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def close(self):
        change_period(self.db, 'A', 'close', self.old, 0, 'Reviewed September', 'owner@test', self.today)

    def test_close_reopen_atomic_history_and_stale_version(self):
        self.close()
        self.assertEqual(self.db.query(FinancePeriodControl).filter_by(company_id='A').one().closed_through, self.old)
        self.assertEqual(self.db.query(FinancePeriodAudit).count(), 1)
        with self.assertRaises(ValueError):
            change_period(self.db, 'A', 'reopen', None, 0, 'Wrong version', 'owner', self.today)
        self.db.rollback()
        self.assertEqual(self.db.query(FinancePeriodAudit).count(), 1)
        change_period(self.db, 'A', 'reopen', None, 1, 'Correction approved', 'owner', self.today)
        self.assertEqual(self.db.query(FinancePeriodAudit).count(), 2)
        self.sale.grand_total = 150
        self.db.commit()

    def test_old_date_cannot_be_moved_or_deleted(self):
        self.close()
        self.sale.invoice_date = self.today
        with self.assertRaises(ClosedPeriodError):
            self.db.commit()
        self.db.rollback()
        self.assertEqual(self.sale.invoice_date, self.old)
        self.db.delete(self.sale)
        with self.assertRaises(ClosedPeriodError):
            self.db.commit()
        self.db.rollback()
        self.assertEqual(self.db.query(CustomerInvoice).count(), 1)

    def test_closed_insert_rejected_current_insert_allowed(self):
        self.close()
        self.db.add(CustomerInvoice(company_id='A', invoice_number='PAST', invoice_date=self.old))
        with self.assertRaises(ClosedPeriodError):
            self.db.commit()
        self.db.rollback()
        self.db.add(CustomerInvoice(company_id='A', invoice_number='NOW', invoice_date=self.today))
        self.db.commit()
        current = self.db.query(CustomerInvoice).filter_by(invoice_number='NOW').one()
        current.invoice_date = self.old
        with self.assertRaises(ClosedPeriodError):
            self.db.commit()
        self.db.rollback()

    def test_child_line_and_atomic_settlement_rejected(self):
        self.close()
        self.db.add(CustomerInvoiceItem(customer_invoice_id=self.sale.id, item_name='Closed line'))
        with self.assertRaises(ClosedPeriodError):
            self.db.commit()
        self.db.rollback()
        self.db.add(CashTransaction(company_id='A', type='income', category='Receipt', description='Current receipt', amount=10, date=self.today))
        self.sale.paid_amount = 10
        with self.assertRaises(ClosedPeriodError):
            self.db.commit()
        self.db.rollback()
        self.assertEqual(self.db.query(CashTransaction).count(), 0)
        self.assertEqual(self.sale.paid_amount, 0)

    def test_bulk_and_raw_changes_blocked_reads_allowed(self):
        self.close()
        with self.assertRaises(ClosedPeriodError):
            self.db.query(CustomerInvoice).filter_by(company_id='A').update({'balance': 0})
        self.db.rollback()
        with self.assertRaises(ClosedPeriodError):
            self.db.execute(text('UPDATE customer_invoices SET balance=0'))
        self.db.rollback()
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM customer_invoices')).scalar(), 1)

    def test_company_isolation(self):
        self.close()
        other = Session(self.engine, info={'finance_period_company': 'B'})
        try:
            other.add(CustomerInvoice(company_id='B', invoice_number='B1', invoice_date=self.old))
            other.commit()
        finally:
            other.close()
        self.db.add(CustomerInvoice(company_id='B', invoice_number='WRONG', invoice_date=self.today))
        with self.assertRaises(ClosedPeriodError):
            self.db.commit()
        self.db.rollback()

    def test_openings_and_history_immutable(self):
        client = Client(company_id='A', name='Customer')
        self.db.add(client)
        self.db.commit()
        self.close()
        client.opening_balance = 100
        with self.assertRaises(ClosedPeriodError):
            self.db.commit()
        self.db.rollback()
        audit = self.db.query(FinancePeriodAudit).one()
        audit.reason = 'Tampered'
        with self.assertRaises(ClosedPeriodError):
            self.db.commit()
        self.db.rollback()
        with self.assertRaises(ClosedPeriodError):
            self.db.execute(text('DELETE FROM finance_period_audits'))
        self.db.rollback()

    def test_draft_unbalanced_and_opening_preflight(self):
        journal = JournalEntry(company_id='A', entry_no='J1', entry_date=self.old, narration='Draft', status='Draft')
        self.db.add(journal)
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'draft'):
            self.close()
        self.db.rollback()
        journal.status = 'Posted'
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'unbalanced journals'):
            self.close()
        self.db.rollback()
        self.db.delete(journal)
        self.db.add(ChartOfAccount(company_id='A', code='1100', name='Cash', account_type='Asset', account_group='Cash', normal_balance='Debit', opening_balance=10))
        self.db.commit()
        with self.assertRaisesRegex(ValueError, 'account openings'):
            self.close()
        self.db.rollback()
        self.assertEqual(self.db.query(FinancePeriodAudit).count(), 0)

    def test_reason_and_future_date_required(self):
        for cutoff, reason in ((self.today, 'Close today'), (self.old, ''), (None, 'Missing date')):
            with self.assertRaises(ValueError):
                change_period(self.db, 'A', 'close', cutoff, 0, reason, 'owner', self.today)
            self.db.rollback()

    def test_closed_journal_reversal_rolls_back_new_entry(self):
        accounts = [ChartOfAccount(company_id='A', code=code, name=code, account_type=kind,
                    account_group=kind, normal_balance=normal)
                    for code, kind, normal in [('1100', 'Asset', 'Debit'), ('4100', 'Income', 'Credit')]]
        self.db.add_all(accounts)
        self.db.flush()
        original = JournalEntry(company_id='A', entry_no='J1', entry_date=self.old, narration='Posted', status='Posted',
            lines=[JournalEntryLine(account_id=accounts[0].id, debit=10, credit=0),
                   JournalEntryLine(account_id=accounts[1].id, debit=0, credit=10)])
        self.db.add(original)
        self.db.commit()
        self.close()
        reversal = JournalEntry(company_id='A', entry_no='J2', entry_date=self.today, narration='Reversal', status='Posted',
                                reversal_of_id=original.id)
        self.db.add(reversal)
        self.db.flush()  # Some existing routes flush the header before the lines.
        original.status = 'Reversed'
        with self.assertRaises(ClosedPeriodError):
            self.db.commit()
        self.db.rollback()
        self.assertEqual(self.db.query(JournalEntry).count(), 1)
        self.assertEqual(original.status, 'Posted')
        original.lines[0].debit = 20
        with self.assertRaises(ClosedPeriodError):
            self.db.commit()
        self.db.rollback()

    def test_owner_csrf_routes_and_rendering(self):
        app = Flask(__name__, template_folder='../templates')
        app.secret_key = 'test-periods'
        app.testing = True
        app.jinja_loader = ChoiceLoader([DictLoader({'base.html': '{% block extra_style %}{% endblock %}{% block content %}{% endblock %}'}), app.jinja_loader])
        self.owner = True
        def owner_required(fn):
            @wraps(fn)
            def wrapped(*a, **kw):
                if not self.owner:
                    abort(403)
                return fn(*a, **kw)
            return wrapped
        register_finance_periods(app, lambda fn: fn, owner_required, lambda *a: lambda fn: fn,
                                lambda: self.db, lambda: 'A', lambda: {'role':'owner' if self.owner else 'accountant', 'email':'owner@test'}, lambda: self.today)
        app.add_url_rule('/checks', 'finance_checks', lambda: '')
        client = app.test_client()
        self.assertEqual(client.get('/finance/periods').status_code, 200)
        self.assertEqual(client.post('/finance/periods/change', data={}).status_code, 403)
        with client.session_transaction() as state:
            token = state['finance_period_csrf']
        data = dict(token=token, company_id='A', version=0, reason='Reviewed', reviewed='yes', cutoff=str(self.old), action='close')
        self.owner = False
        self.assertEqual(client.post('/finance/periods/change', data=data).status_code, 403)
        self.owner = True
        self.assertEqual(client.post('/finance/periods/change', data=dict(data, company_id='B')).status_code, 400)
        self.assertEqual(client.post('/finance/periods/change', data=data).status_code, 302)
        self.assertIn(b'2026-09-30', client.get('/finance/periods').data)
        self.assertEqual(client.get('/finance/periods/change').status_code, 405)


if __name__ == '__main__':
    unittest.main()

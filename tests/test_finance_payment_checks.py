from collections import Counter
from datetime import datetime
import unittest
from sqlalchemy import inspect, text
import test_finance_party_checks as fixtures
from customer_models import Invoice, CustomerInvoice, PurchaseInvoice, Supplier, CashTransaction, BankTransaction, BankAccount, PurchasePayment
from finance_payment_checks import payment_checks


class PaymentChecksTests(unittest.TestCase):
    setUp = fixtures.PartyChecksTests.setUp
    tearDown = fixtures.PartyChecksTests.tearDown
    cash = fixtures.PartyChecksTests.cash

    def report(self):
        issues, checked = [], Counter()
        before = self.db.connection().exec_driver_sql('SELECT total_changes()').scalar()
        with self.db.no_autoflush:
            payment_checks(self.db, 'A', lambda p, a: p not in self.denied,
                set(inspect(self.engine).get_table_names()), lambda code, ref, detail: issues.append((code, ref, detail)), checked)
        self.assertEqual(before, self.db.connection().exec_driver_sql('SELECT total_changes()').scalar())
        return Counter(i[0] for i in issues), checked, issues

    def linked_invoice(self, **kw):
        self.db.add(Invoice(id=1, company_id='A', invoice_id='B1', paid_amount=100, client_id=1))
        data = dict(company_id='A', invoice_number='CI1', client_id=1, booking_ids_json='[1]',
                    grand_total=200, paid_amount=100, balance=90, note_adjustment=10)
        data.update(kw)
        inv = CustomerInvoice(**data)
        self.db.add(inv)
        self.db.commit()
        return inv

    def test_rollup_and_note_adjustment(self):
        inv = self.linked_invoice()
        self.assertEqual(self.report()[0], {})
        inv.paid_amount = 50
        self.db.commit()
        # Simulate an old stored inconsistency; the current note listener repairs
        # this on normal ORM writes, so use SQL only in this isolated fixture.
        self.db.execute(text('UPDATE customer_invoices SET balance=90 WHERE id=:pk'), {'pk': inv.id})
        self.db.commit()
        self.db.expire_all()
        counts = self.report()[0]
        self.assertEqual(counts['Booking payment rollup differs'], 1)
        self.assertEqual(counts['Invoice balance calculation differs'], 1)

    def test_duplicates_cancelled_and_wrong_customer(self):
        inv = self.linked_invoice()
        other = CustomerInvoice(company_id='A', invoice_number='CI2', booking_ids_json='[1]',
                                client_id=1, paid_amount=100, grand_total=100, balance=0)
        self.db.add(other)
        self.db.commit()
        self.assertEqual(self.report()[0]['Booking on multiple invoices'], 2)
        other.status = 'Void'
        self.db.query(Invoice).one().client_id = 2
        self.db.commit()
        counts = self.report()[0]
        self.assertEqual(counts['Booking on multiple invoices'], 0)
        self.assertEqual(counts['Booking customer differs'], 1)

    def test_missing_and_invalid_membership(self):
        inv = self.linked_invoice(booking_ids_json='[1,1]')
        self.assertEqual(self.report()[0]['Invalid booking membership'], 1)
        inv.booking_ids_json = '[2]'
        self.db.add(Invoice(id=2, company_id='B', invoice_id='PRIVATE'))
        self.db.commit()
        counts, checked, issues = self.report()
        self.assertEqual(counts['Linked booking missing'], 1)
        self.assertNotIn('PRIVATE', str(issues))

    def test_receipt_membership_and_mixed_standalone(self):
        inv = self.linked_invoice()
        txn = self.cash(applied_ref_type='customer_invoice', applied_ci_id=inv.id, applied_breakdown_json='{"2":100}')
        counts = self.report()[0]
        self.assertEqual(counts['Receipt booking membership differs'], 1)
        self.assertEqual(counts['Receipt invoice link unused'], 1)
        txn.applied_ref_type = 'mixed'
        txn.applied_breakdown_json = '{"1":50,"2":50}'
        self.db.commit()
        self.assertEqual(self.report()[0], {})

    def test_aggregate_cash_and_bank_without_purchase_mirrors(self):
        self.db.add(PurchaseInvoice(id=1, company_id='A', invoice_id='P1', paid_amount=100))
        bank = BankAccount(company_id='A', bank_name='Bank', account_name='Main', account_number='123')
        self.db.add(bank)
        self.db.commit()
        self.cash(type='expense', category='Payment', amount=40, applied_ref_type='purchase_invoice',
                  applied_ref_id=1, applied_breakdown_json='{"1":40}')
        self.db.add(BankTransaction(company_id='A', bank_account_id=bank.id, type='debit', description='Payment',
                                   amount=60, applied_ref_type='purchase_invoice', applied_ref_id=1))
        PurchasePayment.__table__.create(self.engine)
        self.db.add(PurchasePayment(company_id='A', invoice_id=1, amount=100))
        self.db.commit()
        self.assertEqual(self.report()[0], {})
        self.assertEqual(self.report()[1]['paid_amounts'], 1)
        self.db.query(PurchaseInvoice).one().paid_amount = 110
        self.db.commit()
        self.assertEqual(self.report()[0]['Payment evidence differs'], 1)

    def test_cutoffs_currency_and_permissions_skip_comparison(self):
        self.db.add(Supplier(id=1, company_id='A', name='Vendor', statement_cutoff=datetime(2030, 1, 1)))
        inv = PurchaseInvoice(id=1, company_id='A', invoice_id='P1', supplier_id=1, paid_amount=999)
        self.db.add(inv)
        self.db.commit()
        self.cash(type='expense', category='Payment', applied_ref_type='purchase_invoice')
        self.assertEqual(self.report()[0], {})
        self.assertEqual(self.report()[1]['paid_amounts'], 0)
        self.db.query(Supplier).one().statement_cutoff = None
        inv.exchange_rate = 1.001
        self.db.commit()
        self.assertEqual(self.report()[1]['paid_amounts'], 0)
        inv.exchange_rate = 1
        self.db.commit()
        self.denied.add('bank')
        self.assertEqual(self.report()[1]['paid_amounts'], 0)

    def test_ambiguous_allocation_suppresses_family_comparison(self):
        self.db.add(PurchaseInvoice(id=1, company_id='A', invoice_id='P1', paid_amount=100))
        self.db.commit()
        self.cash(type='expense', category='Payment', applied_ref_type='purchase_invoice')
        self.cash(type='expense', category='Payment', applied_ref_type='purchase_invoice', applied_breakdown_json='bad')
        self.assertEqual(self.report()[1]['paid_amounts'], 0)
        self.assertGreater(self.report()[1]['payment_evidence_unverified'], 0)


if __name__ == '__main__':
    unittest.main()

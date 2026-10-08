"""Focused allocation and opening archive cases in an isolated database."""
from collections import Counter
from datetime import datetime
import unittest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from customer_models import (Client, Supplier, Invoice, CustomerInvoice, PurchaseInvoice,
                             StatementClosing, CashTransaction, BankAccount, BankTransaction)
from finance_party_checks import party_checks


class PartyChecksTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        for model in (Client, Supplier, Invoice, CustomerInvoice, PurchaseInvoice, StatementClosing,
                      CashTransaction, BankAccount, BankTransaction):
            model.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.denied = set()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def report(self):
        issues, checked = [], Counter()
        before = self.db.connection().exec_driver_sql('SELECT total_changes()').scalar()
        with self.db.no_autoflush:
            complete = party_checks(self.db, 'A', lambda p, a: p not in self.denied,
                set(inspect(self.engine).get_table_names()), lambda code, ref, detail, *args: issues.append((code, ref, detail)), checked)
        self.assertEqual(before, self.db.connection().exec_driver_sql('SELECT total_changes()').scalar())
        return Counter(i[0] for i in issues), checked, issues

    def cash(self, **kw):
        data = dict(company_id='A', type='income', category='Receipt', description='Test', amount=100,
                    applied_ref_type='invoice', applied_breakdown_json='{"1":100}')
        data.update(kw)
        txn = CashTransaction(**data)
        self.db.add(txn)
        self.db.commit()
        return txn

    def test_valid_booking_map_and_cross_company_target(self):
        self.db.add(Invoice(id=1, company_id='A', invoice_id='B1'))
        self.db.commit()
        self.cash(applied_ref_id=1)
        self.assertEqual(self.report()[0], {})
        self.db.query(Invoice).one().company_id = 'B'
        self.db.commit()
        counts, checked, issues = self.report()
        self.assertEqual(counts['Allocation target missing'], 1)
        self.assertNotIn('B1', str(issues))

    def test_bad_reference_and_partial_total(self):
        txn = self.cash(applied_breakdown_json='{"bad":100}')
        self.assertEqual(self.report()[0]['Invalid allocation references'], 1)
        txn.applied_breakdown_json = '{"1":50}'
        txn.applied_ref_id = 2
        self.db.commit()
        counts = self.report()[0]
        self.assertEqual(counts['Allocation total differs'], 1)
        self.assertEqual(counts['Conflicting allocation references'], 1)
        txn.applied_ci_ids_json = '[true]'
        self.db.commit()
        self.assertEqual(self.report()[0]['Invalid allocation references'], 1)

    def test_permissions_and_inactive_purchase(self):
        self.db.add(PurchaseInvoice(id=1, company_id='A', invoice_id='P1', status='Void'))
        self.db.commit()
        self.cash(type='expense', category='Payment', applied_ref_type='purchase_invoice')
        self.assertEqual(self.report()[0]['Allocation target inactive'], 1)
        self.denied.add('purchase')
        counts, checked, _ = self.report()
        self.assertEqual(counts['Allocation target inactive'], 0)
        self.assertEqual(checked['allocation_targets_unverified'], 1)
        self.denied.add('receipts_payments')
        self.assertEqual(self.report()[1]['allocation_transactions'], 0)

    def test_receipt_booking_map_does_not_resolve_to_customer_invoice(self):
        self.db.add(CustomerInvoice(id=1, company_id='A', invoice_number='CI1'))
        self.db.commit()
        self.cash(applied_ref_type='customer_invoice', applied_ci_id=1)
        self.assertEqual(self.report()[0]['Allocation target missing'], 1)
        self.db.add(Invoice(id=1, company_id='A', invoice_id='BOOK1'))
        self.db.commit()
        self.assertEqual(self.report()[0], {})

    def test_cutoff_archive_and_manual_opening(self):
        self.db.add(Supplier(id=1, company_id='A', name='Vendor', opening_balance=70,
                             statement_cutoff=datetime(2026, 9, 1)))
        self.db.commit()
        self.assertEqual(self.report()[0]['Opening archive missing'], 1)
        self.db.add(StatementClosing(company_id='A', entity_type='supplier', entity_id=1,
                    entity_name='Vendor', action='carried_forward', closing_balance=70))
        self.db.commit()
        self.assertEqual(self.report()[0], {})
        self.db.query(Supplier).one().opening_balance = 80
        self.db.commit()
        self.assertEqual(self.report()[0]['Carried opening differs'], 1)
        self.db.query(Supplier).one().statement_cutoff = None
        self.db.commit()
        self.assertEqual(self.report()[0]['Opening cutoff missing'], 1)

    def test_cleared_archive_and_tenant_isolation(self):
        self.db.add(Client(id=1, company_id='A', name='Customer', opening_balance=0,
                           statement_cutoff=datetime(2026, 9, 1)))
        self.db.add(Client(id=2, company_id='B', name='PRIVATE', opening_balance=999))
        self.db.add(StatementClosing(company_id='A', entity_type='client', entity_id=1,
                    entity_name='Customer', action='cleared', closing_balance=200))
        self.db.commit()
        self.assertEqual(self.report()[0], {})
        self.assertEqual(self.report()[1]['party_openings'], 1)
        self.denied.add('clients')
        self.assertEqual(self.report()[1]['party_openings'], 0)

    def test_separate_invoice_opening_archive(self):
        self.db.execute(text('ALTER TABLE clients ADD COLUMN invoice_opening_balance FLOAT DEFAULT 0'))
        self.db.execute(text('ALTER TABLE clients ADD COLUMN invoice_statement_cutoff DATETIME'))
        self.db.add(Client(id=1, company_id='A', name='Customer', opening_balance=10,
                           statement_cutoff=datetime(2026, 9, 1)))
        for family, amount in [('client', 10), ('client_invoice', 20)]:
            self.db.add(StatementClosing(company_id='A', entity_type=family, entity_id=1,
                        entity_name='Customer', action='carried_forward', closing_balance=amount))
        self.db.commit()
        self.db.execute(text("UPDATE clients SET invoice_opening_balance=20, invoice_statement_cutoff='2026-09-01' WHERE id=1"))
        self.db.commit()
        self.assertEqual(self.report()[0], {})
        self.assertEqual(self.report()[1]['party_openings'], 2)


if __name__ == '__main__':
    unittest.main()

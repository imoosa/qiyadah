from datetime import date
import unittest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from customer_models import customer_db, ChartOfAccount, JournalEntry, JournalEntryLine
from bi.business_charts import ledger_performance, month_labels


class LedgerChartsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://')
        customer_db.metadata.create_all(self.engine)
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def post(self, code, kind, amount, company='A', status='Posted', day=date(2026,10,2)):
        account = self.db.query(ChartOfAccount).filter_by(company_id=company, code=code).first()
        if not account:
            account = ChartOfAccount(company_id=company, code=code, name=code,
                account_type=kind, account_group=kind, normal_balance='Credit' if kind == 'Income' else 'Debit')
            self.db.add(account)
            self.db.flush()
        offset = self.db.query(ChartOfAccount).filter_by(company_id=company, code='1000').first()
        if not offset:
            offset = ChartOfAccount(company_id=company, code='1000', name='Cash',
                account_type='Asset', account_group='Cash', normal_balance='Debit')
            self.db.add(offset)
            self.db.flush()
        debit, credit = (0, amount) if kind == 'Income' else (amount, 0)
        entry = JournalEntry(company_id=company, entry_no=str(self.db.query(JournalEntry).count()),
            entry_date=day, narration='Test', status=status,
            lines=[JournalEntryLine(account_id=account.id, debit=debit, credit=credit),
                   JournalEntryLine(account_id=offset.id, debit=credit, credit=debit)])
        self.db.add(entry)
        self.db.commit()

    def result(self):
        return ledger_performance(self.db, 'A', date(2026,10,1), date(2026,10,7),
            date(2026,9,24), date(2026,9,30), 'INR')

    def test_missing_profit_is_not_zero(self):
        self.assertFalse(self.result()['available'])
        self.post('4000', 'Income', 999, status='Draft')
        self.assertFalse(self.result()['available'])

    def test_loss_other_income_comparison_and_tenant_scope(self):
        for code, kind, value in [('4000','Income',100),('5000','Expense',80),
                                  ('6000','Expense',50),('4300','Income',10)]:
            self.post(code, kind, value)
        self.post('4000', 'Income', 50, day=date(2026,9,30))
        self.post('4000', 'Income', 99999, company='B')
        self.post('4000', 'Income', 99999, status='Draft')
        data = self.result()
        self.assertEqual(data['current']['gross_profit'],20)
        self.assertEqual(data['current']['net_profit'],-20)
        self.assertEqual(data['net_margin'],-20)
        self.assertEqual(data['revenue_change'],100)
        self.assertEqual(data['charts'][0]['series'][2]['values'],[-20])

    def test_reversed_original_and_reversal_cancel(self):
        self.post('4000','Income',100,status='Reversed')
        self.post('4000','Income',-100)
        self.assertEqual(self.result()['current']['revenue'],0)
        self.assertIsNone(self.result()['net_margin'])

    def test_calendar_buckets_cross_year(self):
        self.assertEqual(month_labels(date(2025,12,20),date(2026,2,2)),['2025-12','2026-01','2026-02'])


if __name__ == '__main__':
    unittest.main()

"""Read-only settlement posting and opening-balance diagnostics."""
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from customer_models import CashTransaction, BankTransaction, BankAccount


def money(value):
    amount = Decimal(str(value or 0))
    if not amount.is_finite():
        raise ValueError('Amount must be finite.')
    return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def reconciliation_checks(db, company, can, tables, accounts, entries, lines, add, checked):
    complete = True
    openings = Decimal(0)
    for account in accounts.values():
        checked['opening_accounts'] += 1
        opening = money(account.opening_balance)
        if account.normal_balance not in ('Debit', 'Credit'):
            add('Invalid opening convention', account.code, 'Choose a valid debit or credit normal balance.', 'chart_of_accounts')
            continue
        openings += opening if account.normal_balance == 'Debit' else -opening
        if opening and not account.is_active:
            add('Inactive opening account', account.code, 'This inactive account has an opening balance excluded from current financial reports.', 'chart_of_accounts')
    if openings:
        add('Opening balances unbalanced', 'Chart of accounts',
            f'Opening debits minus credits are {openings:,.2f} in company base currency. Review supporting records before adjusting.', 'chart_of_accounts')

    active = defaultdict(list)
    for entry in entries:
        if entry.status == 'Posted' and entry.source_type in ('receipt_cash', 'payment_cash', 'receipt_bank', 'payment_bank'):
            active[(entry.source_type, entry.source_id)].append(entry)
    for model, permission, medium in ((CashTransaction, 'cash', 'cash'), (BankTransaction, 'bank', 'bank')):
        if not can(permission, 'view') or not can('receipts_payments', 'view'):
            continue
        if model.__tablename__ not in tables:
            complete = False
            add('Setup required', f'{medium.title()} settlements', 'Transaction table is unavailable; settlement coverage is incomplete.')
            continue
        transactions = db.query(model).filter_by(company_id=company).order_by(model.id).all()
        transaction_ids = {str(t.id) for t in transactions}
        for (kind, source_id), journals in active.items():
            if kind.endswith('_' + medium) and source_id not in transaction_ids:
                for entry in journals:
                    add('Missing settlement source', entry.entry_no, 'An active settlement journal refers to a transaction that no longer exists in this company.', 'journal_entry_view', {'entry_id': entry.id})
        for txn in transactions:
            reference = f'{medium.title()} transaction #{txn.id}'
            # Bank rows lack categories. Do not infer settlement purpose from names.
            linked = any(getattr(txn, field, None) for field in
                         ('applied_ref_type', 'applied_ref_id', 'applied_ci_id', 'applied_ci_ids_json', 'applied_breakdown_json'))
            existing = active.get(('receipt_' + medium, str(txn.id)), []) + active.get(('payment_' + medium, str(txn.id)), [])
            typ = (txn.type or '').strip().lower()
            if medium == 'cash':
                direction = {'receipt': 'receipt', 'payment': 'payment'}.get((txn.category or '').strip().lower())
                if direction is None and not existing:
                    continue
            else:
                if not linked and not existing:
                    checked['unclassified_bank_movements'] += 1
                    continue
                direction = {'credit': 'receipt', 'debit': 'payment'}.get(typ)
            checked['settlements'] += 1
            endpoint = 'receipt_new' if direction == 'receipt' else 'payment_new' if direction == 'payment' else None
            expected_type = ('income' if direction == 'receipt' else 'expense') if medium == 'cash' else ('credit' if direction == 'receipt' else 'debit')
            if not direction or typ != expected_type:
                add('Settlement direction mismatch', reference, 'The transaction direction and settlement category are inconsistent.', endpoint)
                continue
            amount = money(txn.amount)
            if amount <= 0:
                add('Invalid settlement amount', reference, 'A receipt or payment must have a positive amount.', endpoint)
                continue
            if txn.applied_breakdown_json:
                try:
                    allocation = json.loads(txn.applied_breakdown_json)
                    if not isinstance(allocation, dict):
                        raise ValueError()
                    values = [money(value) for value in allocation.values()]
                    if any(value <= 0 for value in values) or sum(values, Decimal(0)) > amount:
                        raise ValueError()
                except (ValueError, TypeError, InvalidOperation):
                    add('Invalid settlement allocation', reference, 'Allocation must be an amount map with positive values totalling no more than this transaction.', endpoint)
            if not existing:
                add('Missing settlement posting', reference, 'No active receipt/payment journal was found. Check historical coverage before posting.', endpoint)
                continue
            if len(existing) > 1:
                add('Multiple settlement postings', reference, 'More than one active receipt/payment journal refers to this movement.', endpoint)
                continue
            entry = existing[0]
            if entry.source_type != direction + '_' + medium:
                add('Settlement direction mismatch', reference, 'The active journal uses the opposite settlement direction.', endpoint)
            if entry.entry_date != txn.date:
                add('Settlement date mismatch', reference, 'Transaction and active journal dates differ.', endpoint)
            cash_code = '1100' if medium == 'cash' else '1200'
            counterpart = ('1300' if linked else '2500') if direction == 'receipt' else ('2100' if linked else '1800')
            expected = {cash_code: [amount, Decimal(0)] if direction == 'receipt' else [Decimal(0), amount],
                        counterpart: [Decimal(0), amount] if direction == 'receipt' else [amount, Decimal(0)]}
            actual = defaultdict(lambda: [Decimal(0), Decimal(0)])
            for line in lines[entry.id]:
                account = accounts.get(line.account_id)
                values = actual[account.code if account else 'invalid']
                values[0] += money(line.debit)
                values[1] += money(line.credit)
            actual = {code: value for code, value in actual.items() if any(value)}
            if actual != expected:
                add('Settlement posting mismatch', reference, 'Journal accounts or amounts differ from this receipt/payment and its applied/advance status.', 'journal_entry_view', {'entry_id': entry.id})

    if can('bank', 'view'):
        required = {BankAccount.__tablename__, BankTransaction.__tablename__}
        if not required.issubset(tables):
            complete = False
            add('Setup required', 'Bank balances', 'Bank tables are unavailable; balance reconstruction is incomplete.')
        else:
            movements = defaultdict(list)
            banks = db.query(BankAccount).filter_by(company_id=company).order_by(BankAccount.id).all()
            bank_ids = {bank.id for bank in banks}
            for txn in db.query(BankTransaction).filter_by(company_id=company):
                if txn.bank_account_id not in bank_ids:
                    add('Invalid bank account', f'Bank transaction #{txn.id}', 'The linked bank account is missing or belongs to another company.')
                else:
                    movements[txn.bank_account_id].append(txn)
            for bank in banks:
                checked['bank_accounts'] += 1
                reference = f'{bank.bank_name} · {bank.account_name}'
                args = {'account_id': bank.id}
                txns = movements[bank.id]
                opening = money(bank.opening_balance)
                mirrors = [t for t in txns if (t.reference or '').strip().lower() == 'opening balance']
                if mirrors and (len(mirrors) != 1 or mirrors[0].type != 'credit'
                                or money(mirrors[0].amount) != opening or opening <= 0
                                or not (mirrors[0].description or '').startswith('Opening Balance for ')):
                    add('Bank opening needs review', reference, 'Opening markers are ambiguous or differ from the account opening. Balance reconstruction was skipped.', 'bank_transactions', args)
                    continue
                expected = opening
                invalid = False
                for txn in txns:
                    if txn in mirrors:
                        continue
                    amount = money(txn.amount)
                    if txn.type not in ('credit', 'debit') or amount < 0:
                        invalid = True
                        continue
                    expected += amount if txn.type == 'credit' else -amount
                if invalid:
                    add('Bank movement needs review', reference, 'Some movement types or amounts are invalid. Balance reconstruction was skipped.', 'bank_transactions', args)
                elif expected != money(bank.balance):
                    add('Bank balance mismatch', reference,
                        f'Recorded balance {money(bank.balance):,.2f}; opening plus movements {expected:,.2f}; difference {money(bank.balance)-expected:,.2f}. Amounts use this account\'s stored units.', 'bank_transactions', args)
    return complete

"""Allocation targets and statement-opening evidence; never changes source records."""
import json
from decimal import InvalidOperation
from sqlalchemy import inspect, table, column, select
from customer_models import (Invoice, CustomerInvoice, PurchaseInvoice, Client, Supplier,
                             StatementClosing, CashTransaction, BankTransaction)
from finance_reconciliation import money


def positive_id(value):
    if isinstance(value, bool) or not str(value).isdigit() or int(value) <= 0:
        raise ValueError('Invalid document id')
    return int(value)


def party_checks(db, company, can, tables, add, checked):
    complete = True
    cache = {}

    def target(model, pk, reference):
        nonlocal complete
        permission = 'purchase' if model is PurchaseInvoice else 'invoices'
        allowed = (can('invoices', 'view') or can('customer_invoices', 'view')) if model is CustomerInvoice else can(permission, 'view')
        if not allowed:
            checked['allocation_targets_unverified'] += 1
            return None
        if model.__tablename__ not in tables:
            complete = False
            checked['allocation_targets_unverified'] += 1
            return None
        if model not in cache:
            cache[model] = {row.id: row for row in db.query(model).filter_by(company_id=company)}
        row = cache[model].get(pk)
        if row is not None and model is CustomerInvoice:
            permission = 'customer_invoices' if row.invoice_category == 'workshop_repair' else 'invoices'
            if not can(permission, 'view'):
                checked['allocation_targets_unverified'] += 1
                return None
        checked['allocation_targets'] += 1
        if row is None:
            add('Allocation target missing', reference, 'A linked document is absent from the selected company. Review the original settlement; no other company information is shown.')
        elif (row.status or '').strip().lower() in ('draft', 'void', 'cancelled', 'canceled'):
            add('Allocation target inactive', reference, 'A linked document is draft or cancelled. Review settlement and reversal history.')
        return row

    if can('receipts_payments', 'view'):
        for model, permission in ((CashTransaction, 'cash'), (BankTransaction, 'bank')):
            if not can(permission, 'view') or model.__tablename__ not in tables:
                continue
            for txn in db.query(model).filter_by(company_id=company).order_by(model.id):
                kind = (txn.applied_ref_type or '').strip()
                raw_map = txn.applied_breakdown_json
                raw_cis = txn.applied_ci_ids_json
                if not any((kind, raw_map, raw_cis, txn.applied_ref_id, txn.applied_ci_id)):
                    continue
                reference = f'{permission.title()} transaction #{txn.id}'
                checked['allocation_transactions'] += 1
                try:
                    allocation = json.loads(raw_map) if raw_map else {}
                    if not isinstance(allocation, dict):
                        raise ValueError()
                    ids = [positive_id(key) for key in allocation]
                    if len(ids) != len(set(ids)):
                        raise ValueError()
                    cis = json.loads(raw_cis) if raw_cis else []
                    if not isinstance(cis, list):
                        raise ValueError()
                    ci_ids = [positive_id(pk) for pk in cis]
                    if len(ci_ids) != len(set(ci_ids)):
                        raise ValueError()
                    if txn.applied_ci_id:
                        ci_ids.append(positive_id(txn.applied_ci_id))
                    direct_id = positive_id(txn.applied_ref_id) if txn.applied_ref_id is not None else None
                except (ValueError, TypeError):
                    add('Invalid allocation references', reference, 'Allocation keys and invoice links must contain valid positive document IDs, without duplicate list entries.')
                    continue
                if kind not in ('invoice', 'customer_invoice', 'mixed', 'purchase_invoice', ''):
                    add('Unknown allocation type', reference, 'The allocation document type is not supported. Review the legacy record.')
                    continue
                if not kind and (ids or direct_id):
                    add('Unknown allocation type', reference, 'A document type is required to interpret these allocation IDs.')
                    continue
                purchase = kind == 'purchase_invoice'
                if purchase and ci_ids:
                    add('Conflicting allocation references', reference, 'A supplier payment also contains customer invoice links.')
                expected_types = ('expense', 'debit') if purchase else ('income', 'credit')
                if txn.type.lower() not in expected_types:
                    add('Allocation direction mismatch', reference, 'The movement direction does not match its linked sales/purchase document type.')
                if direct_id and ids and (len(ids) != 1 or direct_id != ids[0]):
                    add('Conflicting allocation references', reference, 'The single-document reference disagrees with the allocation breakdown.')
                if direct_id and kind in ('customer_invoice', 'mixed') and not ids:
                    add('Ambiguous allocation reference', reference, 'This legacy single-document reference has no booking breakdown. Its target cannot be inferred safely from the receipt type.')
                document_model = PurchaseInvoice if purchase else Invoice
                for pk in sorted(set(ids + ([direct_id] if direct_id and kind in ('invoice', 'purchase_invoice') else []))):
                    target(document_model, pk, reference)
                for pk in sorted(set(ci_ids)):
                    target(CustomerInvoice, pk, reference)
                if not ids and not direct_id and not ci_ids:
                    add('Empty allocation references', reference, 'This movement claims an allocation but does not identify a document.')
                if ids:
                    try:
                        amounts = [money(value) for value in allocation.values()]
                        # The application records any advance as a separate row.
                        if all(value > 0 for value in amounts) and sum(amounts) != money(txn.amount):
                            add('Allocation total differs', reference, 'Allocation amounts do not equal this applied movement. Advances should be recorded separately; review the original split.')
                    except (ValueError, TypeError, InvalidOperation):
                        pass  # Invalid amounts are reported by settlement checks.

    # Statement cutoffs move operational balances without being GL opening dates.
    # Compare to the correct archive family, never sum rolled balances into GL.
    for model, permission, family in ((Client, 'clients', 'client'), (Supplier, 'suppliers', 'supplier')):
        if not can(permission, 'view'):
            continue
        if model.__tablename__ not in tables:
            complete = False
            add('Setup required', 'Party openings', 'An authorised party table is unavailable; opening checks are incomplete.')
            continue
        archives = {}
        if StatementClosing.__tablename__ in tables:
            families = ('client', 'client_invoice') if family == 'client' else ('supplier',)
            for closing in db.query(StatementClosing).filter(
                    StatementClosing.company_id == company, StatementClosing.entity_type.in_(families)
                    ).order_by(StatementClosing.closed_at, StatementClosing.id):
                archives[(closing.entity_type, closing.entity_id)] = closing
        def check_opening(pk, name, opening, cutoff, archive_family):
            checked['party_openings'] += 1
            reference = f'{"Customer invoice" if archive_family == "client_invoice" else "Customer booking" if archive_family == "client" else "Supplier"} opening · {name}'
            archive = archives.get((archive_family, pk))
            if cutoff:
                checked['carried_openings'] += 1
                if not archive:
                    add('Opening archive missing', reference, 'A statement cutoff exists without a matching closing archive. Review the carry-forward history.')
                elif archive.action not in ('cleared', 'carried_forward'):
                    add('Opening archive needs review', reference, 'The latest closing action is not recognised.')
                else:
                    expected = money(archive.closing_balance) if archive.action == 'carried_forward' else money(0)
                    if money(opening) != expected:
                        add('Carried opening differs', reference, f'Current opening {money(opening):,.2f}; latest archived opening basis {expected:,.2f}. Review subsequent edits and cutoff history; amounts are in the stored statement units.')
            elif archive:
                add('Opening cutoff missing', reference, 'A closing archive exists but the current statement has no cutoff. Review whether archived transactions are being counted again.')
            elif money(opening):
                add('Opening basis needs review', reference, 'This opening has no closing archive or common ledger opening date/currency evidence. Confirm its migration basis before reconciling to the ledger control account.')
        for party in db.query(model).filter_by(company_id=company).order_by(model.id):
            check_opening(party.id, party.name, party.opening_balance, party.statement_cutoff, family)
        if model is Client and can('debtors', 'view'):
            # These legacy columns are added dynamically by app.py, not mapped.
            names = {c['name'] for c in inspect(db.get_bind()).get_columns('clients')}
            if {'invoice_opening_balance', 'invoice_statement_cutoff'}.issubset(names):
                clients = table('clients', *(column(n) for n in ('id', 'company_id', 'name', 'invoice_opening_balance', 'invoice_statement_cutoff')))
                for row in db.execute(select(clients).where(clients.c.company_id == company)).mappings():
                    check_opening(row['id'], row['name'], row['invoice_opening_balance'], row['invoice_statement_cutoff'], 'client_invoice')
            else:
                checked['invoice_openings_unverified'] += 1
    return complete

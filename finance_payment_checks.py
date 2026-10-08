"""Payment evidence and booking membership diagnostics, without historical repairs."""
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from customer_models import (Invoice, CustomerInvoice, PurchaseInvoice, Client, Supplier,
                             CashTransaction, BankTransaction)
from finance_party_checks import positive_id
from finance_reconciliation import money

EXCLUDED = ('draft', 'void', 'cancelled', 'canceled')


def id_list(raw):
    values = json.loads(raw) if raw else []
    if not isinstance(values, list):
        raise ValueError('Expected a list')
    ids = [positive_id(value) for value in values]
    if len(ids) != len(set(ids)):
        raise ValueError('Repeated booking')
    return ids


def payment_checks(db, company, can, tables, add, checked):
    def rows(model):
        return {r.id: r for r in db.query(model).filter_by(company_id=company)}

    bookings = rows(Invoice) if can('invoices', 'view') and Invoice.__tablename__ in tables else None
    customer_invoices = None
    if (can('invoices', 'view') or can('customer_invoices', 'view')) and CustomerInvoice.__tablename__ in tables:
        customer_invoices = {pk: inv for pk, inv in rows(CustomerInvoice).items()
                             if can('customer_invoices' if inv.invoice_category == 'workshop_repair' else 'invoices', 'view')}
    memberships = {}
    owners = defaultdict(list)
    if customer_invoices is not None:
        for inv in customer_invoices.values():
            if (inv.status or '').strip().lower() in EXCLUDED or not inv.booking_ids_json:
                continue
            ref = inv.invoice_number
            try:
                ids = id_list(inv.booking_ids_json)
            except (ValueError, TypeError):
                add('Invalid booking membership', ref, 'Booking links must be a list of unique positive IDs.')
                continue
            if not ids:
                continue
            memberships[inv.id] = set(ids)
            if bookings is None:
                checked['booking_membership_unverified'] += 1
                continue
            checked['booking_invoices'] += 1
            usable = True
            for pk in ids:
                owners[pk].append(inv)
                booking = bookings.get(pk)
                if booking is None:
                    add('Linked booking missing', ref, 'A linked booking is not present in this company.')
                    usable = False
                elif (booking.status or '').strip().lower() in EXCLUDED:
                    add('Linked booking inactive', ref, 'An active invoice includes a draft or cancelled booking.')
                    usable = False
                elif inv.client_id is not None and booking.client_id != inv.client_id:
                    add('Booking customer differs', ref, 'A linked booking does not belong to the invoice customer.')
                    usable = False
            if usable:
                paid = sum((money(bookings[pk].paid_amount) for pk in ids), Decimal(0))
                if paid != money(inv.paid_amount):
                    add('Booking payment rollup differs', ref, f'Invoice paid amount {money(inv.paid_amount):,.2f}; linked booking paid amounts {paid:,.2f}. Review the synchronisation history; these are stored document amounts.')
                balance = max(Decimal(0), money(inv.grand_total) - money(inv.paid_amount) - money(inv.note_adjustment))
                if money(inv.balance) != balance:
                    add('Invoice balance calculation differs', ref, f'Recorded balance {money(inv.balance):,.2f}; total less paid amount and note adjustments {balance:,.2f}.')
        for group in owners.values():
            if len(group) > 1:
                for inv in group:
                    add('Booking on multiple invoices', inv.invoice_number, 'A linked booking appears on more than one authorised active invoice. Review potential duplicate billing.')

    # Never compare an all-source paid total against only one authorised medium.
    if not all(can(p, 'view') for p in ('cash', 'bank', 'receipts_payments')) or not all(
            m.__tablename__ in tables for m in (CashTransaction, BankTransaction)):
        checked['payment_evidence_unverified'] += 1
        return
    purchases = rows(PurchaseInvoice) if can('purchase', 'view') and PurchaseInvoice.__tablename__ in tables else None
    totals = defaultdict(lambda: Decimal(0))
    uncertain = set()
    for model in (CashTransaction, BankTransaction):
        for txn in db.query(model).filter_by(company_id=company):
            kind = txn.applied_ref_type or ''
            if kind not in ('invoice', 'customer_invoice', 'mixed', 'purchase_invoice'):
                if txn.applied_breakdown_json or txn.applied_ref_id:
                    checked['payment_evidence_unverified'] += 1
                continue
            family = 'purchase' if kind == 'purchase_invoice' else 'booking'
            reference = f'{"Cash" if model is CashTransaction else "Bank"} transaction #{txn.id}'
            try:
                raw = json.loads(txn.applied_breakdown_json) if txn.applied_breakdown_json else {}
                if not isinstance(raw, dict):
                    raise ValueError()
                allocation = {positive_id(pk): money(amount) for pk, amount in raw.items()}
                if len(allocation) != len(raw):
                    raise ValueError()
                direct = positive_id(txn.applied_ref_id) if txn.applied_ref_id else None
                if allocation and direct and (set(allocation) != {direct}):
                    raise ValueError()
                if not allocation and direct and kind in ('invoice', 'purchase_invoice'):
                    allocation = {direct: money(txn.amount)}
                if not allocation or any(a <= 0 for a in allocation.values()) or sum(allocation.values()) != money(txn.amount):
                    raise ValueError()
                expected_type = ('expense' if family == 'purchase' else 'income') if model is CashTransaction else ('debit' if family == 'purchase' else 'credit')
                if txn.type != expected_type:
                    raise ValueError()
                ci_ids = set(id_list(txn.applied_ci_ids_json))
                if txn.applied_ci_id:
                    ci_ids.add(positive_id(txn.applied_ci_id))
            except (ValueError, TypeError, InvalidOperation):
                uncertain.add(family)
                checked['payment_evidence_unverified'] += 1
                continue
            for pk, amount in allocation.items():
                totals[(family, pk)] += amount
            if family == 'booking' and kind in ('customer_invoice', 'mixed') and ci_ids:
                if bookings is None or customer_invoices is None or any(pk not in customer_invoices for pk in ci_ids):
                    checked['booking_membership_unverified'] += 1
                    continue
                if any(pk not in memberships for pk in ci_ids):
                    add('Receipt membership unverified', reference, 'A linked customer invoice has no usable booking membership list.')
                    continue
                selected = set().union(*(memberships[pk] for pk in ci_ids))
                if kind == 'customer_invoice' and not set(allocation).issubset(selected):
                    add('Receipt booking membership differs', reference, 'Receipt allocation includes a booking outside its linked customer invoices.')
                if any(not memberships[pk].intersection(allocation) for pk in ci_ids):
                    add('Receipt invoice link unused', reference, 'A linked customer invoice has no booking in this receipt allocation.')

    for family, documents, party_model, permission in (
            ('booking', bookings, Client, 'clients'), ('purchase', purchases, Supplier, 'suppliers')):
        if documents is None:
            continue
        if family in uncertain or not can(permission, 'view') or party_model.__tablename__ not in tables:
            checked['payment_evidence_unverified'] += sum(f == family for f, pk in totals)
            continue
        parties = rows(party_model)
        for (source, pk), allocated in totals.items():
            if source != family or pk not in documents:
                continue
            inv = documents[pk]
            if (inv.status or '').strip().lower() in EXCLUDED:
                continue
            party_id = inv.supplier_id if family == 'purchase' else inv.client_id
            party = parties.get(party_id)
            # Cutoffs can alter historic paid amounts independently of payments.
            if ((party_id is not None and party is None) or
                    (party is not None and party.statement_cutoff and inv.date < party.statement_cutoff.date())):
                checked['payment_evidence_unverified'] += 1
                continue
            if family == 'purchase' and Decimal(str(inv.exchange_rate or 1)) != 1:
                checked['payment_evidence_unverified'] += 1
                continue
            checked['paid_amounts'] += 1
            if money(inv.paid_amount) != allocated:
                add('Payment evidence differs', inv.invoice_id,
                    f'Recorded paid amount {money(inv.paid_amount):,.2f}; structurally linked cash/bank allocations {allocated:,.2f}. Review legacy/direct payments and historical coverage before adjusting. Purchase-payment mirrors are not added again.')

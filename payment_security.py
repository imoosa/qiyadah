"""Atomic, repeat-safe fulfillment of server-created checkout orders."""
from datetime import timedelta
from plan_catalog import payment_minor_units
from decimal import Decimal
import hashlib
import hmac
from sqlalchemy import or_
from platform_models import db, PaymentTransaction, RegisteredUser, Company, SubscriptionPlan


def fulfill_payment(data, secret, today, fetch_payment):
    if not isinstance(data, dict):
        return {'status': 'error', 'message': 'A payment object is required.'}, 400
    if not secret:
        return {'status': 'error', 'message': 'Online payments are not configured.'}, 503
    order, payment, signature = (data.get(k) for k in
        ('razorpay_order_id', 'razorpay_payment_id', 'razorpay_signature'))
    if not all(isinstance(v, str) and 0 < len(v) <= 255 for v in (order, payment, signature)):
        return {'status': 'error', 'message': 'Missing payment signature details.'}, 400
    expected = hmac.new(secret.encode(), f'{order}|{payment}'.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return {'status': 'error', 'message': 'Payment signature verification failed.'}, 400
    try:
        txn = PaymentTransaction.query.filter_by(razorpay_order_id=order).with_for_update().first()
        if not txn or (data.get('transaction_id') and data['transaction_id'] != txn.transaction_id):
            db.session.rollback()
            return {'status': 'error', 'message': 'Payment order not found.'}, 400
        if txn.status == 'success':
            result = {'status': 'success', 'message': 'Payment already processed.',
                      'plan_id': txn.plan_id, 'duration': txn.duration, 'already_processed': True}
            db.session.rollback()
            return result, 200
        receipt = fetch_payment(payment)
        if (receipt.get('id') != payment or receipt.get('order_id') != order
                or receipt.get('status') != 'captured'
                or receipt.get('currency') != txn.currency
                or receipt.get('amount') != payment_minor_units(txn.amount, txn.currency)
                or receipt.get('amount_refunded', 0)):
            db.session.rollback()
            return {'status': 'error', 'message': 'Payment is not captured for this order and amount. Please retry once capture completes.'}, 409
        # Also works with databases that do not implement SELECT FOR UPDATE.
        claimed = PaymentTransaction.query.filter(PaymentTransaction.id == txn.id,
            PaymentTransaction.status != 'success').update({'status': 'processing'})
        if not claimed:
            db.session.rollback()
            return {'status': 'success', 'message': 'Payment already processed.', 'already_processed': True}, 200
        duplicate = PaymentTransaction.query.filter(PaymentTransaction.razorpay_payment_id == payment,
            PaymentTransaction.id != txn.id).first()
        if duplicate:
            raise ValueError('Payment has already been assigned to another order.')
        owner = RegisteredUser.query.filter_by(email=txn.user_email).with_for_update().first()
        companies = (Company.query.filter_by(owner_email=txn.user_email) if owner else
                     Company.query.filter_by(company_id=txn.company_id)).with_for_update().all()
        if not owner and not companies:
            # Registration checkout is fulfilled before the account is created.
            # Registration consumes this paid order using its existing checks.
            if txn.company_id:
                raise ValueError('The payment account is unavailable.')
        plan = db.session.get(SubscriptionPlan, txn.plan_id)
        maintenance = txn.plan_id == 'lifetime_maintenance'
        if not maintenance and not plan:
            raise ValueError('The payment plan is unavailable.')
        days = {'1_year': 365, '3_years': 1095, 'lifetime': 36500}.get(txn.duration)
        if not days:
            raise ValueError('Invalid payment duration.')
        end = today + timedelta(days=365 if maintenance else days)
        if owner:
            owner.amount_paid = Decimal(str(owner.amount_paid or 0)) + Decimal(str(txn.amount))
            if maintenance:
                end = max(today, owner.maintenance_due_date or today) + timedelta(days=365)
                owner.maintenance_due_date = end
                owner.last_maintenance_paid_at = today
            else:
                owner.subscription_plan, owner.plan_duration, owner.payment_status = txn.plan_id, txn.duration, 'paid'
                if txn.duration == 'lifetime':
                    owner.maintenance_due_date, owner.last_maintenance_paid_at = today + timedelta(days=365), today
        for company in companies:
            if maintenance:
                company.maintenance_due_date = max(today, company.maintenance_due_date or today) + timedelta(days=365)
                company.last_maintenance_paid_at = today
                end = company.maintenance_due_date
            else:
                # Preserve already-paid time. A trial's remaining days are not purchased time.
                base = max(today, company.subscription_end or today) if company.subscription_plan != 'trial' else today
                company.subscription_end = base + timedelta(days=days)
                company.subscription_start = company.subscription_start or today
                company.subscription_plan, company.plan_duration = txn.plan_id, txn.duration
                company.max_companies_allowed, company.max_users_per_company = plan.max_companies, plan.max_users
                if txn.duration == 'lifetime':
                    company.maintenance_due_date, company.last_maintenance_paid_at = today + timedelta(days=365), today
                end = company.subscription_end
        txn.razorpay_payment_id, txn.razorpay_signature, txn.status = payment, signature, 'success'
        txn.error_reason = None
        db.session.commit()
        return {'status': 'success', 'message': 'Payment verified and subscription activated successfully!',
                'plan_id': txn.plan_id, 'duration': txn.duration, 'valid_until': end.isoformat()}, 200
    except Exception:
        db.session.rollback()
        raise

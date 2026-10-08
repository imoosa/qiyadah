"""Selected-plan trials, persistent daily reminders and owner checkout."""
import os
import threading
from datetime import timedelta
from flask import render_template, abort, g
from flask_mail import Message
from sqlalchemy import or_
from platform_models import db, RegisteredUser
from module_access import trial_expiry
from plan_catalog import PUBLIC_PLANS


def trial_details(account, today):
    if not account or account.payment_status != 'trial' or account.subscription_plan not in PUBLIC_PLANS:
        return None
    end = trial_expiry(account)
    remaining = (end - today).days
    return dict(plan_id=account.subscription_plan, name=PUBLIC_PLANS[account.subscription_plan]['name'],
                amount=account.amount_total, duration=account.plan_duration, end=end, days=remaining,
                due=0 <= remaining <= 4, expired=remaining < 0)


def send_trial_reminders(app, mail, today):
    origin = app.config.get('PUBLIC_APP_URL', '').rstrip('/')
    if not origin.startswith('https://'):
        app.logger.warning('Trial reminder emails require PUBLIC_APP_URL with an https:// address.')
        return 0
    count = 0
    ids = [a.user_id for a in RegisteredUser.query.filter_by(role='owner', payment_status='trial', is_active=True).all()]
    for uid in ids:
        try:
            # Serialize sends across workers. Persist only after SMTP accepts the message.
            account = RegisteredUser.query.filter_by(user_id=uid).with_for_update().populate_existing().first()
            info = trial_details(account, today)
            if not info or not info['due'] or account.last_trial_email_date == today:
                db.session.rollback()
                continue
            amount = f"{info['amount']:,.2f}"
            term = '3 years' if info['duration'] == '3_years' else '1 year'
            message = Message(subject=f"Your {info['name']} trial {'ends today' if info['days'] == 0 else 'ends in ' + str(info['days']) + ' days'}",
                              recipients=[account.email])
            message.body = (f"Hello {account.full_name},\n\nYour {info['name']} trial ends on {info['end']:%d %b %Y}.\n"
                            f"Your selected subscription is â‚¹{amount} for {term}. No automatic charge will be made.\n\n"
                            f"Sign in and pay securely with Razorpay: {origin}/subscription/trial\n\nQiyadah")
            mail.send(message)
            account.last_trial_email_date = today
            db.session.commit()
            count += 1
        except Exception:
            db.session.rollback()
            app.logger.exception('Trial reminder failed; will retry on the next scheduled run.')
    return count


def register_trial_subscriptions(app, login_required, get_current_user, today_func):
    def owner():
        user = get_current_user() or {}
        if user.get('role') != 'owner':
            return None
        return RegisteredUser.query.filter_by(email=user.get('email'), role='owner', is_active=True).first()

    def notice():
        if hasattr(g, 'trial_notice'):
            return g.trial_notice
        account = owner()
        info = trial_details(account, today_func())
        g.trial_notice = None
        if info and (info['due'] or info['expired']):
            changed = RegisteredUser.query.filter(RegisteredUser.user_id == account.user_id,
                or_(RegisteredUser.last_trial_notice_date.is_(None), RegisteredUser.last_trial_notice_date < today_func())).update(
                    {'last_trial_notice_date': today_func()}, synchronize_session=False)
            db.session.commit()
            if changed:
                g.trial_notice = info
        return g.trial_notice

    @app.before_request
    def reset_trial_notice():
        g.pop('trial_notice', None)

    @app.context_processor
    def inject_trial():
        account = owner()
        return dict(trial_notice=notice, selected_trial=trial_details(account, today_func()))

    @app.route('/subscription/trial')
    @login_required
    def trial_checkout():
        account = owner()
        if not account:
            abort(403)
        info = trial_details(account, today_func())
        return render_template('trial_checkout.html', trial=info, account=account)


def start_trial_reminders(app, mail, today_func):
    if app.testing or app.extensions.get('trial_reminder_worker'):
        return
    stop = threading.Event()
    def run():
        while not stop.wait(60):
            with app.app_context():
                try:
                    send_trial_reminders(app, mail, today_func())
                except Exception:
                    db.session.rollback()
                    app.logger.exception('Trial reminder worker failed')
            if stop.wait(3540):
                break
    worker = threading.Thread(target=run, name='trial-reminders', daemon=True)
    app.extensions['trial_reminder_worker'] = stop
    worker.start()

"""Owner recovery links bound to the current password; no schema migration."""
import hashlib
import hmac
import re
from urllib.parse import urlsplit

from flask import request, session, render_template, redirect, url_for, flash
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer, BadData
from auth_security import allow_attempt
from auth_utils import hash_password, verify_password
from platform_models import db, RegisteredUser


def register_password_recovery(app, mail):
    def serializer():
        return URLSafeTimedSerializer(app.secret_key, salt='owner-password-recovery-v1')

    def stamp(account):
        return hmac.new(app.secret_key.encode(), account.password_hash.encode(), hashlib.sha256).hexdigest()

    def account_for(token):
        try:
            data = serializer().loads(token, max_age=1800)
            account = RegisteredUser.query.filter_by(user_id=data['id'], email=data['email'],
                                                    role='owner', is_active=True).first()
            if account and hmac.compare_digest(stamp(account), data['stamp']):
                return account
        except (BadData, KeyError, TypeError):
            pass
        return None

    @app.route('/forgot-password', methods=['GET', 'POST'])
    def forgot_password():
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()[:255]
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                flash('Enter your registered email address.', 'error')
                return redirect(url_for('forgot_password'))
            allowed = allow_attempt('recovery-ip', request.remote_addr or '', 10, 900)
            allowed = allow_attempt('recovery-email', email, 3, 1800) and allowed
            if not allowed:
                flash('Too many reset requests. Please wait 30 minutes before trying again.', 'error')
                return redirect(url_for('forgot_password'))
            if allowed:
                account = RegisteredUser.query.filter_by(email=email, role='owner', is_active=True).first()
                if account:
                    # Never construct emailed links from the untrusted request Host.
                    base = app.config.get('PUBLIC_APP_URL', '').rstrip('/')
                    parsed = urlsplit(base)
                    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
                        app.logger.error('Password recovery requires a valid HTTPS PUBLIC_APP_URL.')
                        flash('Password recovery is temporarily unavailable. Please contact support.', 'error')
                        return redirect(url_for('forgot_password'))
                    else:
                        token = serializer().dumps(dict(id=account.user_id, email=account.email, stamp=stamp(account)))
                        link = base + url_for('reset_owner_password', token=token)
                        try:
                            mail.send(Message(subject='Reset your Qiyadah ERP password', recipients=[account.email],
                                body='Use this link to choose a new password:\n\n' + link +
                                '\n\nThis link expires in 30 minutes and works once. If you did not request it, ignore this email.'))
                        except Exception as exc:
                            app.logger.error('Password recovery email delivery failed (%s).', type(exc).__name__)
                            flash('We could not send the password setup email. Please try again later or contact support.', 'error')
                            return redirect(url_for('forgot_password'))
            flash('If this is the registered email for an active owner account, your password setup link has been sent. Please check your inbox and spam folder.', 'success')
            return redirect(url_for('forgot_password'))
        return render_template('password_recovery.html', resetting=False, valid=True)

    @app.route('/reset-password/<token>', methods=['GET', 'POST'])
    def reset_owner_password(token):
        if request.method == 'POST' and not allow_attempt('recovery-reset-ip', request.remote_addr or '', 20, 900):
            return render_template('password_recovery.html', resetting=True, valid=False), 429
        account = account_for(token)
        if not account:
            return render_template('password_recovery.html', resetting=True, valid=False), 400
        if request.method == 'POST':
            password = request.form.get('password', '')
            if not 8 <= len(password) <= 128:
                flash('Use a password between 8 and 128 characters.', 'error')
            elif password != request.form.get('confirm_password', ''):
                flash('Passwords do not match.', 'error')
            elif verify_password(password, account.password_hash):
                flash('Choose a different password from your current password.', 'error')
            else:
                # Compare-and-swap prevents simultaneous reuse of a valid link.
                changed = RegisteredUser.query.filter_by(id=account.id, email=account.email,
                    password_hash=account.password_hash, role='owner', is_active=True).update({
                        'password_hash': hash_password(password), 'must_change_password': False}, synchronize_session=False)
                db.session.commit()
                if not changed:
                    return render_template('password_recovery.html', resetting=True, valid=False), 400
                session.clear()
                flash('Password changed. Sign in with your new password.', 'success')
                return redirect(url_for('login'))
        return render_template('password_recovery.html', resetting=True, valid=True)

    @app.after_request
    def protect_recovery_page(response):
        if request.endpoint in ('forgot_password', 'reset_owner_password'):
            response.headers['Referrer-Policy'] = 'no-referrer'
            response.headers['Cache-Control'] = 'no-store'
        return response

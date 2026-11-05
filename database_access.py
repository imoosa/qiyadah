"""Super-admin reporting access. Privileged MySQL operations live in a broker."""
from datetime import datetime
from functools import wraps
import hashlib
import hmac
import json
import os
import re
import secrets
import socket
import uuid

from flask import abort, current_app, render_template, request, session
from sqlalchemy import inspect
from platform_models import db, Company, RegisteredUser
from auth_utils import verify_password
from auth_security import allow_attempt

REPORT_TABLES = ('customer_invoices', 'customer_invoice_items', 'purchase_invoices',
                 'purchase_invoice_items', 'stock_items')


class CompanyDatabaseAccess(db.Model):
    __tablename__ = 'company_database_access'
    company_id = db.Column(db.String(20), primary_key=True)
    username = db.Column(db.String(32), nullable=False, unique=True)
    status = db.Column(db.String(20), nullable=False, default='disabled')
    revision = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


class DatabaseAccessAudit(db.Model):
    __tablename__ = 'database_access_audit'
    request_id = db.Column(db.String(36), primary_key=True)
    company_id = db.Column(db.String(20), nullable=False, index=True)
    actor = db.Column(db.String(255), nullable=False)
    action = db.Column(db.String(20), nullable=False)
    outcome = db.Column(db.String(20), nullable=False)
    reason = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


def account_names(company_id):
    if not isinstance(company_id, str) or not re.fullmatch(r'[A-Za-z0-9_]{1,20}', company_id):
        raise ValueError('Invalid company identifier')
    return 'qiy_' + company_id.lower(), 'qyr_' + hashlib.sha256(company_id.encode()).hexdigest()[:24]


def broker_call(payload):
    path = current_app.config.get('DATABASE_ACCESS_SOCKET')
    if not path or not hasattr(socket, 'AF_UNIX'):
        raise OSError('Database access service is not configured')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(20)
        connection.connect(path)
        connection.sendall(json.dumps(payload).encode() + b'\n')
        with connection.makefile('rb') as stream:
            raw = stream.readline(16385)
        if not raw.endswith(b'\n') or len(raw) > 16384:
            raise OSError('Invalid database access service response')
        return json.loads(raw)


def register_database_access(app, get_current_user):
    app.config.setdefault('DATABASE_ACCESS_SOCKET', os.getenv('DATABASE_ACCESS_SOCKET', ''))

    def administrator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            identity = get_current_user() or {}
            if identity.get('role') != 'super_admin':
                abort(403)
            actor = RegisteredUser.query.filter_by(user_id=identity.get('user_id'),
                role='super_admin', is_active=True).first()
            if not actor:
                abort(403)
            return view(actor, *args, **kwargs)
        return wrapped

    @app.route('/admin/database-access', methods=['GET', 'POST'])
    @administrator
    def admin_database_access(actor):
        token = session.setdefault('database_access_csrf', secrets.token_urlsafe(32))
        available = {'company_database_access', 'database_access_audit'} <= set(inspect(db.engine).get_table_names())
        company_id = request.form.get('company_id') if request.method == 'POST' else request.args.get('company_id')
        company = Company.query.filter_by(company_id=company_id).first() if company_id else None
        result, error, status = None, None, 200
        if request.method == 'POST':
            if not hmac.compare_digest(request.form.get('access_csrf', ''), token):
                abort(403)
            if not allow_attempt('database-access-admin', actor.user_id, 10, 300):
                error, status = 'Too many changes or password attempts. Wait five minutes before trying again.', 429
            elif not verify_password(request.form.get('admin_password', ''), actor.password_hash):
                error, status = 'Your administrator password is incorrect.', 403
            elif not available or not app.config['DATABASE_ACCESS_SOCKET']:
                error, status = 'The database access service needs VPS setup before changes can be made.', 503
            elif not company:
                abort(404)
            else:
                try:
                    result = broker_call(dict(company_id=company.company_id, actor_id=actor.user_id,
                        action=request.form.get('action'), revision=int(request.form.get('revision', '-1')),
                        request_id=request.form.get('request_id'), reason=request.form.get('reason', '').strip()))
                    status = int(result.get('http_status', 200))
                    if not result.get('success'):
                        error = result.get('message', 'The change could not be completed.')
                except (OSError, ValueError, TypeError):
                    error, status = ('The service did not confirm the result. Reload to check the status before retrying. '
                                     'If a new password was lost, use Reset password.', 503)
                db.session.expire_all()
        access = db.session.get(CompanyDatabaseAccess, company_id) if available and company else None
        audits = DatabaseAccessAudit.query.filter_by(company_id=company_id).order_by(
            DatabaseAccessAudit.created_at.desc()).limit(25).all() if available and company else []
        return render_template('admin_database_access.html', companies=Company.query.order_by(Company.company_name).all(),
            company=company, access=access, audits=audits, result=result, error=error,
            ready=available and bool(app.config['DATABASE_ACCESS_SOCKET']), access_csrf=token,
            request_id=str(uuid.uuid4()), tables=REPORT_TABLES), status


"""Linux-only Unix-socket broker. Run separately, never import from web startup.

The broker's MySQL credential is held in its own protected environment file.
It accepts only fixed read-only reporting operations on validated company IDs.
"""
from datetime import datetime
import json
import os
import secrets
import socketserver
import uuid
import time
from pathlib import Path

from flask import Flask
import pymysql
from platform_models import db, Company, RegisteredUser
from database_access import CompanyDatabaseAccess, DatabaseAccessAudit, REPORT_TABLES, account_names


class MySQLAccounts:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, args=()):
        with self.connection.cursor() as cursor:
            cursor.execute(sql, args)
            return cursor.fetchall()

    def lock(self, company):
        name = 'qiy_access_' + account_names(company)[1]
        if self.execute('SELECT GET_LOCK(%s, 5)', (name,))[0][0] != 1:
            raise RuntimeError('Company access is busy')

    def unlock(self, company):
        self.execute('SELECT RELEASE_LOCK(%s)', ('qiy_access_' + account_names(company)[1],))

    def exists(self, username):
        return bool(self.execute("SELECT User FROM mysql.user WHERE User=%s AND Host='127.0.0.1'", (username,)))

    def disable(self, username):
        if not self.exists(username):
            return
        self.execute("ALTER USER %s@'127.0.0.1' ACCOUNT LOCK", (username,))
        self.execute("REVOKE ALL PRIVILEGES, GRANT OPTION FROM %s@'127.0.0.1'", (username,))
        # Account locking/password changes do not disconnect existing sessions.
        # Only terminate sessions belonging to this exact managed username.
        for row in self.execute('SHOW PROCESSLIST'):
            if row[1] == username:
                try:
                    self.execute('KILL CONNECTION ' + str(int(row[0])))
                except pymysql.err.OperationalError as exc:
                    if exc.args[0] != 1094:  # Session may already have ended.
                        raise

    def enable(self, database, username, password):
        existing = {row[0] for row in self.execute(
            'SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE=%s',
            (database, 'BASE TABLE'))}
        if not set(REPORT_TABLES) <= existing:
            raise ValueError('Company reporting tables are missing; initialize its database first.')
        self.execute("CREATE USER IF NOT EXISTS %s@'127.0.0.1' IDENTIFIED BY %s ACCOUNT LOCK", (username, password))
        self.disable(username)
        self.execute("ALTER USER %s@'127.0.0.1' IDENTIFIED BY %s WITH MAX_USER_CONNECTIONS 3", (username, password))
        # Table-level grants use literal identifiers, avoiding database wildcard grants.
        for table in REPORT_TABLES:
            self.execute(f"GRANT SELECT ON `{database}`.`{table}` TO %s@'127.0.0.1'", (username,))
        self.execute("ALTER USER %s@'127.0.0.1' ACCOUNT UNLOCK", (username,))


def change_access(payload, accounts):
    if not isinstance(payload, dict):
        return dict(success=False, message='Invalid request.', http_status=400)
    try:
        cid, action = payload['company_id'], payload['action']
        database, username = account_names(cid)
        request_id = str(uuid.UUID(payload['request_id']))
        revision = payload['revision']
        reason = payload.get('reason', '').strip()
        if action not in ('enable', 'reset', 'revoke') or type(revision) is not int or revision < 0 or not 1 <= len(reason) <= 500:
            raise ValueError()
    except (KeyError, ValueError, TypeError, AttributeError):
        return dict(success=False, message='Choose a valid action and provide a reason.', http_status=400)
    actor = RegisteredUser.query.filter_by(user_id=payload.get('actor_id'), role='super_admin', is_active=True).first()
    company = Company.query.filter_by(company_id=cid).first()
    if not actor or not company:
        return dict(success=False, message='Administrator or company is unavailable.', http_status=403)
    cid = company.company_id  # Canonical spelling from MySQL's case-insensitive lookup.
    database, username = account_names(cid)
    if action != 'revoke' and not company.is_active:
        return dict(success=False, message='Activate the company before enabling database access.', http_status=409)
    accounts.lock(cid)
    try:
        # End the read transaction before checking revisions after the external lock.
        db.session.rollback()
        actor = RegisteredUser.query.filter_by(user_id=payload.get('actor_id'), role='super_admin', is_active=True).first()
        company = Company.query.filter_by(company_id=cid).first()
        if not actor or not company or (action != 'revoke' and not company.is_active):
            return dict(success=False, message='Administrator or company access changed. Reload before continuing.', http_status=403)
        access = db.session.get(CompanyDatabaseAccess, cid)
        previous = db.session.get(DatabaseAccessAudit, request_id)
        if previous:
            return dict(success=False, message='This request was already submitted. Reload to see its result.', http_status=409)
        if (access.revision if access else 0) != revision:
            return dict(success=False, message='Access changed in another session. Reload before continuing.', http_status=409)
        if action == 'enable' and access and access.status == 'enabled':
            return dict(success=False, message='Access is already enabled. Use Reset password.', http_status=409)
        if action != 'revoke' and access and access.status in ('pending', 'error'):
            return dict(success=False, message='Revoke the unconfirmed access before enabling it again.', http_status=409)
        if action == 'reset' and (not access or access.status != 'enabled'):
            return dict(success=False, message='Enable database access first.', http_status=409)
        if not access:
            if accounts.exists(username):
                return dict(success=False, message='An unmanaged account uses this username. Operator review is required.', http_status=409)
            access = CompanyDatabaseAccess(company_id=cid, username=username)
            db.session.add(access)
        audit = DatabaseAccessAudit(request_id=request_id, company_id=cid, actor=actor.email,
            action=action, outcome='pending', reason=reason)
        db.session.add(audit)
        access.status, access.revision, access.updated_at = 'pending', revision + 1, datetime.utcnow()
        db.session.commit()  # Audit intent before nontransactional MySQL account changes.
        try:
            password = secrets.token_urlsafe(32) if action != 'revoke' else None
            if action == 'revoke':
                accounts.disable(username)
            else:
                accounts.enable(database, username, password)
            access.status = 'disabled' if action == 'revoke' else 'enabled'
            audit.outcome, access.updated_at = 'success', datetime.utcnow()
            db.session.commit()
            result = dict(success=True, message='Access revoked.' if action == 'revoke' else 'Read-only access is ready.',
                database=database, username=username, tables=list(REPORT_TABLES))
            if password:
                result['password'] = password  # Returned once; never stored in a database or log.
            return result
        except Exception:
            db.session.rollback()
            # A failed grant/record commit must not leave an enabled, untracked user.
            disabled = False
            try:
                accounts.disable(username)
                disabled = True
            finally:
                access = db.session.get(CompanyDatabaseAccess, cid)
                audit = db.session.get(DatabaseAccessAudit, request_id)
                access.status = 'disabled' if disabled else 'error'
                audit.outcome = 'failed'
                db.session.commit()
            return dict(success=False, message='The change failed; access was disabled. Check VPS service configuration before retrying.', http_status=503)
    finally:
        db.session.rollback()
        accounts.unlock(cid)


def main():
    import fcntl
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['PLATFORM_DB_URI']
    db.init_app(app)
    path = Path(os.environ['DATABASE_ACCESS_SOCKET'])
    # Keep this handle alive: a second service instance must not unlink a live socket.
    instance_lock = open(path.parent / 'broker.lock', 'a')
    fcntl.flock(instance_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if path.exists():
        if not path.is_socket():
            raise RuntimeError('Socket path is occupied by a regular file')
        path.unlink()

    def connect():
        return pymysql.connect(host='127.0.0.1', port=3306,
            user=os.environ['DB_ACCESS_MYSQL_USER'], password=os.environ['DB_ACCESS_MYSQL_PASSWORD'],
            autocommit=True, connect_timeout=5, read_timeout=10, write_timeout=10)

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.request.settimeout(10)
            raw = self.rfile.readline(8193)
            if len(raw) > 8192 or not raw.endswith(b'\n'):
                return
            with app.app_context():
                connection = None
                try:
                    payload = json.loads(raw)
                    connection = connect()
                    result = change_access(payload, MySQLAccounts(connection))
                except Exception:
                    # Do not log exception SQL/parameters: they may contain a generated password.
                    app.logger.error('Database access operation failed; inspect audit status and service configuration.')
                    result = dict(success=False, message='The service could not confirm completion. Reload access status.', http_status=503)
                finally:
                    db.session.remove()
                    if connection:
                        connection.close()
                self.wfile.write(json.dumps(result).encode() + b'\n')

    class Server(socketserver.UnixStreamServer):
        last_check = 0

        def service_actions(self):
            if time.monotonic() - self.last_check < 30:
                return
            self.last_check = time.monotonic()
            with app.app_context():
                connection = None
                try:
                    connection = connect()
                    reconcile_access(MySQLAccounts(connection))
                except Exception:
                    app.logger.error('Database access reconciliation failed; operator attention required.')
                finally:
                    db.session.remove()
                    if connection:
                        connection.close()

    with Server(str(path), Handler) as server:
        os.chmod(path, 0o660)
        server.serve_forever()


def reconcile_access(accounts):
    """Close interrupted grants and revoke inactive/deleted company accounts."""
    candidates = [row.company_id for row in CompanyDatabaseAccess.query.filter(
        CompanyDatabaseAccess.status.in_(('enabled', 'pending', 'error'))).all()]
    for cid in candidates:
        accounts.lock(cid)
        try:
            db.session.rollback()
            row = db.session.get(CompanyDatabaseAccess, cid)
            company = Company.query.filter_by(company_id=cid).first()
            if row.status in ('pending', 'error') or not company or not company.is_active:
                # Derive rather than trusting an editable database username field.
                accounts.disable(account_names(cid)[1])
                row.status, row.revision, row.updated_at = 'disabled', row.revision + 1, datetime.utcnow()
                DatabaseAccessAudit.query.filter_by(company_id=cid, outcome='pending').update({'outcome': 'failed'})
                db.session.add(DatabaseAccessAudit(request_id=str(uuid.uuid4()), company_id=cid,
                    actor='system:database-access', action='revoke', outcome='success',
                    reason='Company inactive/deleted or interrupted operation reconciled.'))
                db.session.commit()
        finally:
            db.session.rollback()
            accounts.unlock(cid)


if __name__ == '__main__':
    main()


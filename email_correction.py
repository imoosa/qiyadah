"""Correct an unverified owner's address in one MySQL transaction."""
from sqlalchemy import inspect, text
from platform_models import db, RegisteredUser, Company, PaymentTransaction
from auth_security import VerificationChallenge


def correct_email(account, new_email):
    old_email = account.email
    connection = db.session.connection()
    if connection.dialect.name == 'mysql':
        for table in ('registered_users', 'companies', 'payment_transactions', 'verification_challenges'):
            engine = inspect(connection).get_table_options(table).get('mysql_engine', '')
            if engine.upper() != 'INNODB':
                raise RuntimeError('Email correction requires InnoDB platform tables')
    companies = Company.query.filter_by(owner_email=old_email).all()
    if companies:
        foreign_keys = inspect(connection).get_foreign_keys('companies')
        if not any(fk['constrained_columns'] == ['owner_email'] and
                   fk.get('options', {}).get('onupdate', '').upper() == 'CASCADE'
                   for fk in foreign_keys):
            raise RuntimeError('Email correction migration is required')
        # Tenant databases share the VPS MySQL server. Use the SAME connection
        # so a failure rolls back platform and tenant updates together.
        from db_router import _build_uri
        platform_url = db.engine.url
        for company in companies:
            tenant_url = _build_uri(company.company_id)
            if (platform_url.host, platform_url.port or 3306) != (tenant_url.host, tenant_url.port or 3306):
                raise RuntimeError('Email correction requires databases on the same server')
            schema = tenant_url.database
            engine = connection.execute(text(
                "SELECT ENGINE FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=:schema AND TABLE_NAME='company_users'"
            ), {'schema': schema}).scalar()
            if not engine or engine.upper() != 'INNODB':
                raise RuntimeError('Company users must use InnoDB')
            quoted = connection.dialect.identifier_preparer.quote_identifier(schema)
            duplicate = connection.execute(text(
                f'SELECT id FROM {quoted}.company_users WHERE company_id=:cid AND email=:email LIMIT 1'
            ), {'cid': company.company_id, 'email': new_email}).first()
            if duplicate:
                raise ValueError('This email is already used in one of your companies.')
            connection.execute(text(
                f'UPDATE {quoted}.company_users SET email=:new '
                'WHERE company_id=:cid AND email=:old AND role=:role'
            ), {'new': new_email, 'old': old_email, 'cid': company.company_id, 'role': 'owner'})
    VerificationChallenge.query.filter_by(email=old_email, consumed=False).update({'consumed': True})
    PaymentTransaction.query.filter_by(user_email=old_email).update({'user_email': new_email})
    account.email = new_email
    db.session.commit()

"""Run once with the production environment loaded, before deploying email correction."""
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text


def migrate(engine):
    if engine.dialect.name != 'mysql':
        raise RuntimeError('This migration is for the production MySQL database.')
    with engine.begin() as connection:
        keys = [fk for fk in inspect(connection).get_foreign_keys('companies')
                if fk['constrained_columns'] == ['owner_email']
                and fk['referred_table'] == 'registered_users'
                and fk['referred_columns'] == ['email']]
        if len(keys) != 1:
            raise RuntimeError('Expected one company owner foreign key; inspect the schema before proceeding.')
        key = keys[0]
        if key.get('options', {}).get('onupdate', '').upper() == 'CASCADE':
            return
        quote = connection.dialect.identifier_preparer.quote_identifier
        delete_rule = key.get('options', {}).get('ondelete', 'RESTRICT').upper()
        if delete_rule not in ('RESTRICT', 'NO ACTION', 'CASCADE', 'SET NULL'):
            raise RuntimeError('Unsupported existing delete rule')
        name = quote(key['name'])
        connection.execute(text(
            f'ALTER TABLE companies DROP FOREIGN KEY {name}, '
            f'ADD CONSTRAINT {name} FOREIGN KEY (owner_email) '
            f'REFERENCES registered_users (email) ON UPDATE CASCADE ON DELETE {delete_rule}'
        ))


if __name__ == '__main__':
    load_dotenv(Path(__file__).with_name('.env'))
    engine = create_engine(os.environ['PLATFORM_DB_URI'])
    try:
        migrate(engine)
        print('Company ownership now follows email corrections. No email addresses were changed.')
    finally:
        engine.dispose()

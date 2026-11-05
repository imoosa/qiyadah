"""Explicit, repeatable migration for the sales invoice starting number."""
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text


def migrate(engine):
    with engine.begin() as connection:
        columns = {column['name'] for column in inspect(connection).get_columns('companies')}
        for name, definition in (
            ('sales_invoice_start', 'INTEGER NOT NULL DEFAULT 1'),
            ('sales_invoice_prefix', "VARCHAR(20) NOT NULL DEFAULT 'INV-'"),
            ('sales_invoice_digits', 'INTEGER NOT NULL DEFAULT 4'),
        ):
            if name not in columns:
                connection.execute(text(f'ALTER TABLE companies ADD COLUMN {name} {definition}'))


if __name__ == '__main__':
    load_dotenv(Path(__file__).with_name('.env'))
    engine = create_engine(os.environ['PLATFORM_DB_URI'])
    try:
        migrate(engine)
        print('Sales invoice numbering is ready. Existing companies keep INV- with four digits.')
    finally:
        engine.dispose()

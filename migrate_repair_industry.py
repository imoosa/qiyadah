"""Explicit, repeatable migration for company repair-industry selection."""
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text


def migrate(engine):
    with engine.begin() as connection:
        if 'repair_industry' not in {column['name'] for column in inspect(connection).get_columns('companies')}:
            connection.execute(text("ALTER TABLE companies ADD COLUMN repair_industry VARCHAR(30) NOT NULL DEFAULT 'vehicle'"))


if __name__ == '__main__':
    load_dotenv(Path(__file__).with_name('.env'))
    engine = create_engine(os.environ['PLATFORM_DB_URI'])
    try:
        migrate(engine)
        print('Repair industry setting is ready. Existing companies default to Vehicle Repair.')
    finally:
        engine.dispose()

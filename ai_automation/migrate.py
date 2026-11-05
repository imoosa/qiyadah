"""Explicit additive schema migration: python -m ai_automation.migrate [--apply]."""
import argparse
import os
from pathlib import Path
from sqlalchemy import create_engine, inspect
from dotenv import load_dotenv
from .models import Base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    load_dotenv(Path(__file__).resolve().parents[1] / '.env')
    engine = create_engine(os.environ['PLATFORM_DB_URI'])
    try:
        missing = sorted(set(Base.metadata.tables) - set(inspect(engine).get_table_names()))
        print('Missing automation tables:', ', '.join(missing) or 'none')
        if args.apply:
            Base.metadata.create_all(engine)
            print('Additive automation schema ready. Existing business tables were not altered.')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()

"""Create the configured platform database before SQLAlchemy creates tables."""
import re
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError


def ensure_platform_database(uri):
    url = make_url(uri)
    if url.get_backend_name() not in ('mysql', 'mariadb'):
        return
    if not url.database or not re.fullmatch(r'[A-Za-z0-9_]+', url.database):
        raise ValueError('Platform database name must contain only letters, numbers and underscores')
    # Existing deployments may grant access only to this database, not CREATE DATABASE.
    probe = create_engine(url, connect_args={'connect_timeout': 10})
    try:
        with probe.connect():
            return
    except OperationalError as error:
        if not getattr(error.orig, 'args', ()) or error.orig.args[0] != 1049:
            raise
    finally:
        probe.dispose()
    engine = create_engine(url.set(database=None), connect_args={'connect_timeout': 10})
    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE DATABASE IF NOT EXISTS `{url.database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'))
    finally:
        engine.dispose()

"""Complete, typed snapshots of a dedicated database with transactional restore."""
import base64
from datetime import date, datetime, time
from decimal import Decimal
import json
from pathlib import Path
from sqlalchemy import MetaData, select, text


def encode(value):
    if isinstance(value, (datetime, date, time, Decimal, bytes)):
        return {'__qiyadah_type__': type(value).__name__, 'value':
                base64.b64encode(value).decode() if isinstance(value, bytes) else str(value)}
    raise TypeError(f'Unsupported backup value: {type(value).__name__}')


def decode(value):
    if set(value) == {'__qiyadah_type__', 'value'}:
        converters = {'datetime': datetime.fromisoformat, 'date': date.fromisoformat,
                      'time': time.fromisoformat, 'Decimal': Decimal,
                      'bytes': lambda s: base64.b64decode(s, validate=True)}
        converter = converters.get(value['__qiyadah_type__'])
        if converter:
            return converter(value['value'])
    return value


def require_transactional_tables(connection):
    """Do not promise rollback/consistent snapshots for MyISAM or mixed engines."""
    if connection.dialect.name in ('mysql', 'mariadb'):
        nontransactional = connection.execute(text(
            "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() "
            "AND TABLE_TYPE='BASE TABLE' AND ENGINE != 'InnoDB'"
        )).first()
        if nontransactional:
            raise ValueError('Backup and transactional restore require all tables to use InnoDB.')


def export_snapshot(engine, scope, path):
    metadata = MetaData()
    with engine.connect() as connection:
        if engine.dialect.name in ('mysql', 'mariadb'):
            connection = connection.execution_options(isolation_level='REPEATABLE READ')
        with connection.begin():
            if engine.dialect.name == 'sqlite':
                connection.exec_driver_sql('BEGIN')
            metadata.reflect(connection)
            require_transactional_tables(connection)
            data = {'format_version': 2, 'company_id': scope, 'complete': True,
                    'export_date': datetime.utcnow().isoformat(), 'tables': {}}
            for table in metadata.tables.values():
                data['tables'][table.name] = [dict(row) for row in connection.execute(select(table)).mappings()]
    Path(path).write_text(json.dumps(data, default=encode, ensure_ascii=False), encoding='utf-8')


def restore_snapshot(engine, scope, path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('format_version') != 2 or data.get('complete') is not True:
        raise ValueError('Only complete version-2 backups can be restored. Legacy exports need an offline migration.')
    if data.get('company_id') != scope:
        raise ValueError('Backup belongs to a different company.')
    metadata = MetaData()
    metadata.reflect(engine)
    if set(data.get('tables', {})) != set(metadata.tables):
        raise ValueError('Backup schema differs from the target database. Restore using the matching application version.')
    # Validate shape and company boundary before deleting any record.
    for name, rows in data['tables'].items():
        table = metadata.tables[name]
        if not isinstance(rows, list):
            raise ValueError('Invalid backup table')
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(table.columns.keys()):
                raise ValueError(f'Invalid backup columns for {name}')
            from sqlalchemy import JSON
            for column in table.columns:
                if isinstance(row[column.name], dict) and not isinstance(column.type, JSON):
                    row[column.name] = decode(row[column.name])
            if scope != '__platform__' and row.get('company_id') not in (None, scope):
                raise ValueError('Backup contains records for another company.')
    with engine.connect() as connection:
        require_transactional_tables(connection)
        # The engine check may have opened a read transaction.
        connection.commit()
        mysql = engine.dialect.name in ('mysql', 'mariadb')
        if mysql:
            connection.exec_driver_sql('SET FOREIGN_KEY_CHECKS=0')
            connection.commit()
        try:
            with connection.begin():
                if engine.dialect.name == 'sqlite':
                    connection.exec_driver_sql('PRAGMA defer_foreign_keys=ON')
                for table in reversed(metadata.sorted_tables):
                    connection.execute(table.delete())
                for table in metadata.sorted_tables:
                    rows = data['tables'][table.name]
                    if rows:
                        connection.execute(table.insert(), rows)
                # MySQL does not retroactively validate after reenabling FK checks.
                for table in metadata.tables.values():
                    for constraint in table.foreign_key_constraints:
                        parent = constraint.referred_table.alias()
                        join = [element.parent == parent.c[element.column.name] for element in constraint.elements]
                        present = [element.parent.is_not(None) for element in constraint.elements]
                        query = select(table).where(*present, ~select(parent).where(*join).exists()).limit(1)
                        if connection.execute(query).first():
                            raise ValueError(f'Broken foreign key in {table.name}')
        finally:
            if mysql:
                connection.exec_driver_sql('SET FOREIGN_KEY_CHECKS=1')
                connection.commit()

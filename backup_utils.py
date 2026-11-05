"""
backup_utils.py
Backup and restore utilities for the ERP system (local storage only)
"""

import os
import json
import shutil
import zipfile
import hashlib
import secrets
from pathlib import Path
from flask import current_app
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
import tempfile

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from platform_models import Company
from db_router import get_customer_session, close_customer_session

# ─────────────────────────────────────────────────────────────────────────────
# Backup Configuration — local storage only, location chosen by the user
# ─────────────────────────────────────────────────────────────────────────────

_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backup_config.json")
_DEFAULT_BACKUP_DIR = os.environ.get("BACKUP_DIR", os.path.join(os.getcwd(), "backups"))


def get_backup_dir() -> str:
    """Return the currently configured local backup folder, creating it if needed."""
    backup_dir = _DEFAULT_BACKUP_DIR
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            saved = cfg.get("backup_dir")
            if saved:
                backup_dir = saved
        except Exception:
            pass
    os.makedirs(backup_dir, exist_ok=True)
    return backup_dir


def set_backup_dir(path: str) -> str:
    """Let the user choose where backups are stored on disk."""
    if not path or not path.strip():
        raise Exception("Backup folder path cannot be empty")
    path = path.strip()
    os.makedirs(path, exist_ok=True)
    with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"backup_dir": path}, f, indent=2)
    return path


BACKUP_DESTINATIONS = {
    "local": "Local Storage",
}


def generate_backup_id():
    """Generate a unique backup ID"""
    return f"BACKUP-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(8)}"


def delete_backup(backup_id, company_id):
    from platform_models import BackupRecord, db
    record = BackupRecord.query.filter_by(backup_id=backup_id, company_id=company_id).first()
    if not record:
        return False
    path = Path(record.backup_file_path).resolve()
    if not path.is_relative_to(Path(get_backup_dir()).resolve()) or path.suffix != '.zip':
        raise ValueError('Backup file is outside the configured backup directory.')
    path.unlink(missing_ok=True)
    db.session.delete(record)
    db.session.commit()
    return True


def calculate_file_hash(filepath: str) -> str:
    """Calculate SHA-256 hash of a file"""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def create_company_backup(company_id: str, include_attachments: bool = True, 
                          from_date: date = None, to_date: date = None) -> Dict[str, Any]:
    """
    Create a full backup: all tables to JSON, plus attachment files, zipped.
    
    Args:
        company_id: The company ID to backup
        include_attachments: Whether to include attachment files
        from_date: Optional start date for filtering data (inclusive)
        to_date: Optional end date for filtering data (inclusive)
    """
    backup_dir = get_backup_dir()
    backup_id = generate_backup_id()
    timestamp = datetime.now()

    backup_path = os.path.join(backup_dir, company_id, backup_id)
    os.makedirs(backup_path, exist_ok=True)

    # Store date range in backup info
    backup_info = {
        "backup_id": backup_id,
        "company_id": company_id,
        "timestamp": timestamp.isoformat(),
        "version": "2.0",
        "files": [],
        "size_bytes": 0,
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": to_date.isoformat() if to_date else None,
    }

    try:
        db_backup_file = os.path.join(backup_path, "database.json")
        export_database_to_json(company_id, db_backup_file, from_date, to_date)
        if os.path.exists(db_backup_file):
            backup_info["files"].append({
                "name": "database.json",
                "path": db_backup_file,
                "size": os.path.getsize(db_backup_file)
            })

        if include_attachments:
            attachments_dir = os.path.join(backup_path, "attachments")
            backup_attachments(company_id, attachments_dir, from_date, to_date)
            if os.path.exists(attachments_dir):
                for root, dirs, files in os.walk(attachments_dir):
                    for file in files:
                        filepath = os.path.join(root, file)
                        backup_info["files"].append({
                            "name": file,
                            "path": filepath,
                            "size": os.path.getsize(filepath)
                        })

        metadata_file = os.path.join(backup_path, "backup_metadata.json")
        with open(metadata_file, 'w') as f:
            json.dump(backup_info, f, indent=2, default=str)
        backup_info["files"].append({
            "name": "backup_metadata.json",
            "path": metadata_file,
            "size": os.path.getsize(metadata_file)
        })

        zip_path = os.path.join(backup_dir, f"{backup_id}.zip")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(backup_path):
                for file in files:
                    filepath = os.path.join(root, file)
                    arcname = os.path.relpath(filepath, backup_path)
                    zipf.write(filepath, arcname)

        file_hash = calculate_file_hash(zip_path)
        zip_size = os.path.getsize(zip_path)

        shutil.rmtree(backup_path, ignore_errors=True)

        backup_info["backup_file"] = zip_path
        backup_info["file_hash"] = file_hash
        backup_info["size_bytes"] = zip_size
        backup_info["size_mb"] = round(zip_size / (1024 * 1024), 4)

        save_backup_record(backup_info)

        return backup_info

    except Exception as e:
        if os.path.exists(backup_path):
            shutil.rmtree(backup_path, ignore_errors=True)
        raise Exception(str(e))


def export_database_to_json(company_id, output_file, from_date=None, to_date=None):
    if from_date or to_date:
        raise ValueError('Recovery backups must include all dates. Use reports for date-filtered exports.')
    from database_snapshot import export_snapshot
    cdb = get_customer_session(company_id)
    try:
        export_snapshot(cdb.get_bind(), company_id, output_file)
    finally:
        close_customer_session(company_id)


def backup_attachments(company_id, output_dir, from_date=None, to_date=None):
    from private_documents import company_folder
    for kind in ('client_docs', 'purchase_invoices', 'invoice_docs'):
        source = company_folder(company_id, kind)
        if source.exists():
            shutil.copytree(source, Path(output_dir) / kind, dirs_exist_ok=True)


def save_backup_record(backup_info: Dict[str, Any]):
    """Save backup record to platform database"""
    from platform_models import BackupRecord
    from platform_models import db

    record = BackupRecord(
        backup_id=backup_info["backup_id"],
        company_id=backup_info["company_id"],
        backup_date=datetime.fromisoformat(backup_info["timestamp"]),
        backup_file_path=backup_info["backup_file"],
        file_size_mb=backup_info["size_mb"],
        file_hash=backup_info["file_hash"],
        status="completed",
        # Add date range fields
        backup_from_date=date.fromisoformat(backup_info["from_date"]) if backup_info.get("from_date") else None,
        backup_to_date=date.fromisoformat(backup_info["to_date"]) if backup_info.get("to_date") else None,
    )
    db.session.add(record)
    db.session.commit()


def list_backups(company_id: str = None) -> List[Dict[str, Any]]:
    """List all available backups"""
    from platform_models import BackupRecord

    query = BackupRecord.query
    if company_id:
        query = query.filter_by(company_id=company_id)

    backups = query.order_by(BackupRecord.backup_date.desc()).all()

    return [{
        "backup_id": b.backup_id,
        "company_id": b.company_id,
        "backup_date": b.backup_date,
        "file_size_mb": b.file_size_mb,
        "status": b.status,
        "restore_date": b.restore_date,
        "restored_by": b.restored_by,
        "backup_from_date": b.backup_from_date,
        "backup_to_date": b.backup_to_date,
    } for b in backups]


def restore_from_backup(backup_id, user_email, company_id):
    """Restore company data from a backup zip file."""
    from platform_models import BackupRecord
    from platform_models import db

    backup_record = BackupRecord.query.filter_by(backup_id=backup_id, company_id=company_id).first()
    if not backup_record:
        raise Exception(f"Backup {backup_id} not found")

    if not os.path.exists(backup_record.backup_file_path):
        raise Exception(f"Backup file not found on disk: {backup_record.backup_file_path}")

    if calculate_file_hash(backup_record.backup_file_path) != backup_record.file_hash:
        raise ValueError('Backup integrity verification failed.')
    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(backup_record.backup_file_path, 'r') as zipf:
            safe_extract(zipf, temp_dir)

        db_json_file = os.path.join(temp_dir, "database.json")
        if os.path.exists(db_json_file):
            restore_archive_data(backup_record.company_id, temp_dir)
        else:
            sql_files = [f for f in os.listdir(temp_dir) if f.endswith('.sql')]
            if not sql_files:
                raise Exception(
                    f"No database.json or .sql file found in backup {backup_id}. "
                    f"Zip contained: {os.listdir(temp_dir) or '(empty)'}"
                )
            _restore_legacy_sql_dump(backup_record.company_id, os.path.join(temp_dir, sql_files[0]))


    backup_record.restore_date = datetime.now()
    backup_record.restored_by = user_email
    db.session.commit()

    return {
        "backup_id": backup_id,
        "company_id": backup_record.company_id,
        "restore_date": datetime.now(),
        "restored_by": user_email,
        "status": "completed"
    }


def restore_from_uploaded_backup(company_id, file_path, user_email):
    """Restore from an uploaded backup zip file."""
    try:
        if not zipfile.is_zipfile(file_path):
            return {"success": False, "message": "Invalid zip file - not a valid archive"}

        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                safe_extract(zip_ref, temp_dir)

            db_json_file = os.path.join(temp_dir, "database.json")
            if os.path.exists(db_json_file):
                restore_archive_data(company_id, temp_dir)
            else:
                sql_files = [f for f in os.listdir(temp_dir) if f.endswith('.sql')]
                if not sql_files:
                    return {
                        "success": False,
                        "message": (
                            f"No database.json or .sql file found in the uploaded "
                            f"archive. It contained: {os.listdir(temp_dir) or '(empty)'}"
                        )
                    }
                _restore_legacy_sql_dump(company_id, os.path.join(temp_dir, sql_files[0]))


            try:
                from platform_models import BackupRecord
                from platform_models import db
                backup_record = BackupRecord.query.filter_by(
                    company_id=company_id
                ).order_by(BackupRecord.backup_date.desc()).first()
                if backup_record:
                    backup_record.restore_date = datetime.utcnow()
                    backup_record.restored_by = user_email
                    db.session.commit()
            except Exception as e:
                print(f"⚠️ Could not log restore in platform DB: {e}")

            return {"success": True, "message": "Restore completed successfully"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "message": str(e)}


def _restore_legacy_sql_dump(company_id, sql_file):
    raise ValueError('Legacy SQL backups require an offline administrator migration.')


def safe_extract(archive, destination):
    total = 0
    root = Path(destination).resolve()
    for member in archive.infolist():
        target = (root / member.filename).resolve()
        total += member.file_size
        if not target.is_relative_to(root) or '\\' in member.filename or ':' in member.filename:
            raise ValueError('Unsafe backup archive path')
        if (member.external_attr >> 16) & 0o170000 == 0o120000:
            raise ValueError('Backup archives cannot contain symbolic links')
        if total > 1024 * 1024 * 1024 or len(archive.infolist()) > 10000:
            raise ValueError('Backup archive exceeds extraction limits')
    archive.extractall(root)


def restore_archive_data(company_id, directory):
    """Stage immutable document copies before the atomic database replacement.

    Failed validation/SQL may leave unreferenced copies, never overwritten live files.
    """
    from private_documents import company_folder, scoped_name
    source_json = Path(directory) / 'database.json'
    data = json.loads(source_json.read_text(encoding='utf-8'))
    if data.get('company_id') != company_id or data.get('format_version') != 2 or data.get('complete') is not True:
        raise ValueError('A complete backup for this company is required.')
    remapped = {}
    for kind in ('client_docs', 'purchase_invoices', 'invoice_docs'):
        source = Path(directory) / 'attachments' / kind
        if not source.exists(): continue
        destination = company_folder(company_id, kind)
        destination.mkdir(parents=True, exist_ok=True)
        for file in source.iterdir():
            if not file.is_file() or file.is_symlink():
                raise ValueError('Unexpected document directory in backup')
            name = secrets.token_hex(16) + '_' + file.name
            # Bound filename length across repeated restore/backup cycles.
            name = name[:180] + file.suffix if len(name) > 200 else name
            shutil.copy2(file, destination / name)
            remapped[(kind, company_id+'/'+file.name)] = company_id+'/'+name
    for table, fields, kind in (
        ('clients', ('aadhar_front_file','aadhar_back_file','pan_front_file','pan_back_file'), 'client_docs'),
        ('purchase_invoices', ('file_path',), 'purchase_invoices')):
        for row in data.get('tables', {}).get(table, []):
            for field in fields:
                key = row.get(field)
                if key:
                    replacement = remapped.get((kind, key), key)
                    name = scoped_name(replacement, company_id)
                    if not name or not (company_folder(company_id, kind)/name).is_file():
                        raise ValueError('A referenced protected document is missing from the backup and target storage.')
                    row[field] = replacement
    prepared = Path(directory) / 'prepared-database.json'
    prepared.write_text(json.dumps(data), encoding='utf-8')
    restore_database_from_json(company_id, prepared)


def _coerce_record_dates(record_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert date/datetime strings back to Python objects."""
    for key, value in record_data.items():
        if isinstance(value, str):
            if "date" in key.lower() or key.endswith("_date"):
                try:
                    record_data[key] = datetime.fromisoformat(value).date()
                    continue
                except Exception:
                    pass
            if "created_at" in key.lower() or "updated_at" in key.lower():
                try:
                    record_data[key] = datetime.fromisoformat(value)
                except Exception:
                    pass
    return record_data


def restore_database_from_json(company_id, json_file):
    from database_snapshot import restore_snapshot
    cdb = get_customer_session(company_id)
    try:
        engine = cdb.get_bind()
        close_customer_session(company_id)
        restore_snapshot(engine, company_id, json_file)
    finally:
        close_customer_session(company_id)

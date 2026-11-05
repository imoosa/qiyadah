"""Run as a separate service: python backup_scheduler.py."""
import os
import shutil
import time
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy import text


def next_run(schedule, now):
    hour, minute = map(int, schedule.time_of_day.split(':'))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if schedule.frequency == 'daily':
        return candidate + timedelta(days=1) if candidate <= now else candidate
    if schedule.frequency == 'weekly':
        candidate += timedelta(days=(6-now.weekday()) % 7)
        return candidate + timedelta(days=7) if candidate <= now else candidate
    if schedule.frequency == 'monthly':
        candidate = candidate.replace(day=1)
        if candidate <= now:
            candidate = candidate.replace(year=candidate.year+1, month=1) if candidate.month == 12 else candidate.replace(month=candidate.month+1)
        return candidate
    raise ValueError('Unsupported backup frequency')


def offsite_copy(path):
    destination = os.environ.get('BACKUP_OFFSITE_DIR')
    if not destination:
        raise RuntimeError('BACKUP_OFFSITE_DIR must point to a protected off-host backup mount.')
    target = Path(destination)
    if not target.is_dir():
        raise RuntimeError('Off-host backup mount is unavailable')
    source = Path(path)
    pending = target / (source.name + '.partial')
    shutil.copy2(source, pending)
    from backup_utils import calculate_file_hash
    if calculate_file_hash(source) != calculate_file_hash(pending):
        raise RuntimeError('Off-host backup verification failed')
    pending.replace(target / source.name)


def run_once(app):
    from platform_models import db, BackupSchedule, BackupRecord
    from backup_utils import create_company_backup, delete_backup, get_backup_dir, generate_backup_id
    from database_snapshot import export_snapshot
    from auth_security import cleanup_authentication_state
    with app.app_context(), db.engine.connect() as lock:
        if db.engine.dialect.name not in ('mysql', 'mariadb'):
            raise RuntimeError('The production scheduler requires MySQL advisory locks.')
        if lock.execute(text("SELECT GET_LOCK('qiyadah_scheduler', 0)")).scalar() != 1:
            return
        try:
            now = datetime.now()
            schedules = BackupSchedule.query.filter(BackupSchedule.is_active == True, BackupSchedule.next_backup <= now).all()
            for schedule in schedules:
                try:
                    following = next_run(schedule, now)
                    info = create_company_backup(schedule.company_id, include_attachments=True)
                    offsite_copy(info['backup_file'])
                    schedule.last_backup, schedule.next_backup = now, following
                    db.session.commit()
                    old = BackupRecord.query.filter(BackupRecord.company_id == schedule.company_id,
                        BackupRecord.backup_date < now-timedelta(days=max(1, schedule.retention_days))).all()
                    for record in old:
                        delete_backup(record.backup_id, schedule.company_id)
                except Exception:
                    db.session.rollback()
                    app.logger.exception('Scheduled company backup failed; schedule remains due')
            platform_dir = Path(get_backup_dir()) / '_platform'
            platform_dir.mkdir(parents=True, exist_ok=True)
            marker = platform_dir / 'last-success.txt'
            if not marker.exists() or marker.read_text() != now.date().isoformat():
                path = platform_dir / (generate_backup_id() + '-platform.json')
                export_snapshot(db.engine, '__platform__', path)
                offsite_copy(path)
                marker.write_text(now.date().isoformat())
            cleanup_authentication_state()
            from trial_subscriptions import send_trial_reminders
            from app import mail, today_ist
            send_trial_reminders(app, mail, today_ist())
        finally:
            lock.execute(text("SELECT RELEASE_LOCK('qiyadah_scheduler')"))


if __name__ == '__main__':
    from app import app
    while True:
        try:
            run_once(app)
        except Exception:
            app.logger.exception('Scheduler cycle failed')
        time.sleep(60)

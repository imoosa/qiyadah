import hashlib
from sqlalchemy.exc import IntegrityError
from .models import AuditLog, AutomationRun, Usage, CompanySettings, now
from .permissions import rows


def event_key(*parts):
    return hashlib.sha256('\x00'.join(map(str, parts)).encode()).hexdigest()


def audit(db, scope, action, reference=None, **details):
    db.add(AuditLog(company_id=scope.company_id, actor=scope.actor,
                    action=action, reference=str(reference) if reference is not None else None, details=details))


def settings(db, scope):
    row = rows(db, CompanySettings, scope).first()
    if row is None:
        row = CompanySettings(company_id=scope.company_id)
        db.add(row)
        db.flush()
    return row


def reserve_usage(db, scope, kind, limit, bucket=None):
    bucket = bucket or now().date().isoformat()
    query = rows(db, Usage, scope).filter_by(bucket=bucket, kind=kind)
    if not query.first():
        try:
            with db.begin_nested():
                db.add(Usage(company_id=scope.company_id, bucket=bucket, kind=kind, count=0))
                db.flush()
        except IntegrityError:
            pass
    if query.filter(Usage.count < limit).update({Usage.count: Usage.count + 1}, synchronize_session=False) != 1:
        raise PermissionError('The configured usage limit has been reached.')
    db.flush()
    return query.populate_existing().one()


def enqueue(db, scope, kind, key, payload):
    existing = rows(db, AutomationRun, scope).filter_by(event_key=key).first()
    if existing:
        return existing
    run = AutomationRun(company_id=scope.company_id, actor=scope.actor,
                         kind=kind, event_key=key, payload=payload)
    try:
        with db.begin_nested():
            db.add(run)
            db.flush()
    except IntegrityError:
        return rows(db, AutomationRun, scope).filter_by(event_key=key).one()
    audit(db, scope, 'job.queued', run.id, kind=kind)
    return run


"""Background worker tasks for AI Automation rules, briefings, and outbound message queue."""
from datetime import date, timedelta
import os
from ..config import decrypt, Unavailable
from ..models import AutomationRule, AutomationRun, MessageQueue, Integration, now
from ..permissions import rows
from ..store import audit, enqueue, event_key, reserve_usage, settings
from ..services.whatsapp_service import MetaWhatsApp, ExistingWhatsApp, Retryable, DeliveryUnknown
from ..services import email_service
from ..workflows.followups import collect, refresh_message, consent, within_working_hours
from ..workflows.daily_briefing import generate_briefing

MAX_ATTEMPTS = 3


def approve_queued_message(db, scope, message_id):
    """Approve a message currently in status='approval' so the worker can dispatch it."""
    scope.require(action='edit', owner=True)
    msg = rows(db, MessageQueue, scope).filter_by(id=str(message_id)).first()
    if not msg:
        raise ValueError('Queued message not found.')
    if msg.status != 'approval':
        raise ValueError(f"Message is in status '{msg.status}', not awaiting approval.")
    msg.status = 'pending'
    msg.scheduled_for = now()
    audit(db, scope, 'message.approved', msg.id, kind=msg.kind, recipient=msg.recipient)
    db.commit()
    return msg


def run_rule_now(db, cdb, scope, rule_id, today=None):
    """Execute a specific AutomationRule immediately and record an AutomationRun."""
    scope.require(action='edit', owner=True)
    today = today or date.today()
    rule = rows(db, AutomationRule, scope).filter_by(id=str(rule_id)).first()
    if not rule:
        raise ValueError('Automation rule not found.')
    key = event_key(scope.company_id, 'rule_run', rule.id, today.isoformat(), int(now().timestamp() // 60))
    run = enqueue(db, scope, rule.kind, key, {'rule_id': rule.id, 'date': today.isoformat()})
    run.status = 'running'
    run.attempts = (run.attempts or 0) + 1
    db.flush()
    try:
        if rule.kind == 'daily_briefing':
            cfg = rule.config or {}
            res = generate_briefing(
                db,
                cdb,
                scope,
                period_type=cfg.get('period_type', 'daily'),
                currency=cfg.get('currency', 'INR'),
                categories=cfg.get('categories'),
                channels=cfg.get('channels', ['dashboard']),
                recipients=cfg.get('recipients', {}),
                template=cfg.get('template'),
            )
            run.status = 'completed'
            run.result = {'briefing_id': res['id'], 'period_start': res['period_start'], 'period_end': res['period_end']}
        else:
            queued_count = collect(db, cdb, scope, rule, today)
            run.status = 'completed'
            run.result = {'queued_messages': queued_count, 'rule_id': rule.id}
        audit(db, scope, 'rule.executed', rule.id, kind=rule.kind, result=run.result)
        db.commit()
        return run
    except Exception as exc:
        run.status = 'failed'
        run.last_error = str(exc)[:500]
        db.commit()
        raise


def process_automation_runs(db, get_cdb_fn, scope_factory, today=None, limit=25, company_id=None):
    """Claim and execute pending AutomationRun jobs."""
    today = today or date.today()
    current = now()
    pending_runs = (
        db.query(AutomationRun)
        .filter(AutomationRun.company_id == company_id if company_id is not None else True)
        .filter(AutomationRun.status == 'pending', AutomationRun.scheduled_for <= current)
        .order_by(AutomationRun.id.asc())
        .limit(limit)
        .all()
    )
    processed = []
    for run in pending_runs:
        claimed = (
            db.query(AutomationRun)
            .filter_by(id=run.id, status='pending')
            .update({'status': 'running', 'attempts': AutomationRun.attempts + 1, 'updated_at': current}, synchronize_session=False)
        )
        if claimed != 1:
            continue
        db.commit()
        db.refresh(run)
        try:
            scope = scope_factory(run.company_id, run.actor)
            cdb = get_cdb_fn(run.company_id)
            rule_id = (run.payload or {}).get('rule_id')
            if rule_id:
                rule = rows(db, AutomationRule, scope).filter_by(id=str(rule_id), enabled=True).first()
                if not rule:
                    run.status = 'skipped_disabled'
                    run.result = {'reason': 'Rule disabled or removed'}
                    db.commit()
                    processed.append(run)
                    continue
                if rule.kind == 'daily_briefing':
                    cfg = rule.config or {}
                    res = generate_briefing(
                        db, cdb, scope,
                        period_type=cfg.get('period_type', 'daily'),
                        currency=cfg.get('currency', 'INR'),
                        categories=cfg.get('categories'),
                        channels=cfg.get('channels', ['dashboard']),
                        recipients=cfg.get('recipients', {}),
                        template=cfg.get('template'),
                    )
                    run.result = {'briefing_id': res['id']}
                else:
                    queued_count = collect(db, cdb, scope, rule, today)
                    run.result = {'queued_messages': queued_count}
            run.status = 'completed'
            run.updated_at = now()
            db.commit()
        except Exception as exc:
            run.last_error = str(exc)[:500]
            if (run.attempts or 1) < MAX_ATTEMPTS:
                run.status = 'pending'
                run.scheduled_for = now() + timedelta(minutes=5 * int(run.attempts or 1))
            else:
                run.status = 'failed'
            run.updated_at = now()
            db.commit()
        processed.append(run)
    return processed


def _send_single_message(db, scope, msg, refreshed_payload, company_obj=None, transport=None):
    cfg = settings(db, scope)
    reserve_usage(db, scope, 'outbound_message', int(cfg.daily_limit or 100))
    if msg.channel == 'whatsapp':
        integ = rows(db, Integration, scope).filter_by(kind='whatsapp', active=True).first()
        if not integ:
            raise Unavailable('WhatsApp integration is not configured or active for this company.')
        icfg = integ.config or {}
        if icfg.get('adapter') == 'existing' and company_obj is not None:
            adapter = ExistingWhatsApp(company_obj, icfg)
        else:
            adapter = MetaWhatsApp(icfg, decrypt(integ.encrypted_secrets), transport=transport)
        return adapter.send(msg.recipient, refreshed_payload, template=msg.template)
    if msg.channel == 'email':
        integ = rows(db, Integration, scope).filter_by(kind='email', active=True).first()
        if not integ:
            raise Unavailable('Email integration is not configured or active for this company.')
        return email_service.send(integ.config or {}, decrypt(integ.encrypted_secrets), msg.recipient, refreshed_payload, msg.id)
    raise Unavailable(f"Unsupported channel: {msg.channel}")


def process_message_queue(db, get_cdb_fn, scope_factory, today=None, limit=25, respect_working_hours=True, company_lookup=None, transport=None, company_id=None):
    """Dispatch pending outbound messages after re-checking consent, working hours, and live invoice/CRM state."""
    today = today or date.today()
    current = now()
    pending_msgs = (
        db.query(MessageQueue)
        .filter(MessageQueue.company_id == company_id if company_id is not None else True)
        .filter(MessageQueue.status == 'pending', MessageQueue.scheduled_for <= current)
        .order_by(MessageQueue.id.asc())
        .limit(limit)
        .all()
    )
    results = []
    for msg in pending_msgs:
        scope = scope_factory(msg.company_id, msg.actor)
        if not consent(db, scope, msg.channel, msg.recipient):
            msg.status = 'cancelled_no_consent'
            msg.updated_at = now()
            audit(db, scope, 'message.cancelled_no_consent', msg.id)
            db.commit()
            results.append(msg)
            continue

        if respect_working_hours and msg.kind != 'reply' and not within_working_hours(db, scope, current):
            msg.scheduled_for = current + timedelta(hours=1)
            msg.updated_at = now()
            db.commit()
            results.append(msg)
            continue

        claimed = (
            db.query(MessageQueue)
            .filter_by(id=msg.id, status='pending')
            .update({'status': 'sending', 'attempts': MessageQueue.attempts + 1, 'updated_at': current}, synchronize_session=False)
        )
        if claimed != 1:
            continue
        db.commit()
        db.refresh(msg)

        try:
            cdb = get_cdb_fn(msg.company_id)
            refreshed = refresh_message(cdb, scope, msg, today)
            if refreshed is None:
                msg.status = 'suppressed_stale'
                msg.updated_at = now()
                audit(db, scope, 'message.suppressed_stale', msg.id, kind=msg.kind, reference=msg.reference)
                db.commit()
                results.append(msg)
                continue
            comp_obj = company_lookup(msg.company_id) if callable(company_lookup) else None
            provider_id = _send_single_message(db, scope, msg, refreshed, company_obj=comp_obj, transport=transport)
            msg.provider_id = str(provider_id)
            msg.status = 'sent'
            msg.updated_at = now()
            audit(db, scope, 'message.sent', msg.id, provider_id=provider_id, channel=msg.channel)
            db.commit()
        except Retryable as exc:
            msg.last_error = str(exc)[:500]
            if (msg.attempts or 1) < MAX_ATTEMPTS:
                msg.status = 'pending'
                msg.scheduled_for = now() + timedelta(minutes=5 * int(msg.attempts or 1))
            else:
                msg.status = 'failed'
            msg.updated_at = now()
            db.commit()
        except DeliveryUnknown as exc:
            # Ambiguous delivery outcome: never auto-retry to avoid duplicate financial/status messages.
            msg.status = 'reconcile_required'
            msg.last_error = str(exc)[:500]
            msg.updated_at = now()
            audit(db, scope, 'message.reconcile_required', msg.id, error=msg.last_error)
            db.commit()
        except Exception as exc:
            msg.status = 'failed'
            msg.last_error = str(exc)[:500]
            msg.updated_at = now()
            audit(db, scope, 'message.failed', msg.id, error=msg.last_error)
            db.commit()
        results.append(msg)
    return results


# Task queues use a separately configured broker, never the rate-limit store.
celery_app = None
try:
    if os.environ.get('CELERY_BROKER_URL'):
        from celery import Celery
        celery_app = Celery('qiyadah_ai_automation', broker=os.environ['CELERY_BROKER_URL'],
                            backend=os.environ.get('CELERY_RESULT_BACKEND') or None)
        celery_app.conf.update(timezone='UTC', enable_utc=True)
except Exception:
    celery_app = None

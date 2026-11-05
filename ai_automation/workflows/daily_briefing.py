"""Daily, Weekly, and Monthly Business Briefing workflow for ERP and eShip."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from ..models import BriefingReport
from ..store import event_key, audit, settings
from ..services.business_data_service import briefing as erp_briefing, eship_briefing, explain_briefing_trends
from .followups import queue_message, CATEGORIES


def resolve_period_bounds(period_type='daily', reference_date=None, tz_name='Asia/Kolkata'):
    if reference_date is None:
        try:
            tz = ZoneInfo(tz_name or 'Asia/Kolkata')
        except Exception:
            tz = ZoneInfo('Asia/Kolkata')
        reference_date = datetime.now(tz).date()
    elif isinstance(reference_date, str):
        reference_date = date.fromisoformat(reference_date[:10])
    period_type = (period_type or 'daily').lower().strip()
    if period_type == 'weekly':
        start = reference_date - timedelta(days=6)
        end = reference_date
    elif period_type == 'monthly':
        start = reference_date.replace(day=1)
        end = reference_date
    else:
        start = reference_date
        end = reference_date
    return start, end


def generate_briefing(db, cdb, scope, period_type='daily', start=None, end=None, currency='INR', categories=None, channels=None, recipients=None, provider=None, template=None):
    """Calculate deterministic ERP or eShip metrics, generate grounded explanation, store BriefingReport, and queue deliveries."""
    scope.require(owner=True)
    cfg = settings(db, scope)
    tz_name = getattr(cfg, 'timezone', None) or 'Asia/Kolkata'
    if start is None or end is None:
        start, end = resolve_period_bounds(period_type, tz_name=tz_name)
    elif isinstance(start, str) or isinstance(end, str):
        start = date.fromisoformat(str(start)[:10]) if isinstance(start, str) else start
        end = date.fromisoformat(str(end)[:10]) if isinstance(end, str) else end

    app_type = 'eship' if scope.application == 'eship' else 'erp'
    if app_type == 'eship':
        raw = eship_briefing(cdb, scope, start, end, currency=currency, categories=categories)
    else:
        cats = categories or [c for c in CATEGORIES if (
            (c in ('sales', 'purchases', 'receivables', 'collections') and scope.modules('core'))
            or (c == 'quotations' and scope.modules('crm'))
            or (c == 'workshop' and scope.modules('repair'))
            or (c == 'stock' and scope.modules('orderflow'))
        )] or ['sales']
        raw = erp_briefing(cdb, scope, start, end, currency=currency, categories=cats)

    explanation, usage = explain_briefing_trends(raw, provider=provider)
    channels = list(channels or ['dashboard'])
    recipients = dict(recipients or {})
    delivery_log = {'dashboard': {'status': 'delivered', 'at': raw['generated_at']}}

    full_text = f"Qiyadah {app_type.upper()} {period_type.capitalize()} Briefing ({start.isoformat()} to {end.isoformat()})\n\n{raw['summary']}\n\nTrend Summary:\n{explanation}"

    for ch in channels:
        if ch in ('email', 'whatsapp'):
            rec = recipients.get(ch)
            if rec:
                key = event_key(scope.company_id, 'briefing', app_type, period_type, start.isoformat(), end.isoformat(), ch, rec)
                queued = queue_message(
                    db,
                    scope,
                    key,
                    ch,
                    rec,
                    'briefing',
                    f"{period_type}:{start.isoformat()}:{end.isoformat()}",
                    {'text': full_text, 'parameters': [app_type.upper(), start.isoformat(), end.isoformat(), raw['summary'][:500]]},
                    template=template if ch == 'whatsapp' else None,
                    approval=False,
                )
                delivery_log[ch] = {'status': 'queued' if queued else 'skipped_no_consent', 'message_id': queued.id if queued else None}
            else:
                delivery_log[ch] = {'status': 'skipped_missing_recipient'}

    report = BriefingReport(
        company_id=scope.company_id,
        app_type=app_type,
        period_type=period_type,
        period_start=start.isoformat(),
        period_end=end.isoformat(),
        timezone=tz_name,
        metrics=raw['metrics'],
        explanation=explanation,
        sources={'sources': raw['sources'], 'currency': currency, 'usage': usage},
        channels=channels,
        delivery_log=delivery_log,
        generated_by=scope.actor,
    )
    db.add(report)
    audit(db, scope, 'briefing.generated', f"{period_type}:{start.isoformat()}", app_type=app_type, channels=channels)
    db.commit()
    return {
        'id': report.id,
        'company_id': report.company_id,
        'app_type': report.app_type,
        'period_type': report.period_type,
        'period_start': report.period_start,
        'period_end': report.period_end,
        'timezone': report.timezone,
        'currency': currency,
        'metrics': report.metrics,
        'explanation': report.explanation,
        'sources': raw['sources'],
        'channels': report.channels,
        'delivery_log': report.delivery_log,
        'created_at': report.created_at.isoformat() if report.created_at else None,
    }

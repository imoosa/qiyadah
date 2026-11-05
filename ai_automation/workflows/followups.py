from datetime import date, datetime, timedelta
import json
from zoneinfo import ZoneInfo
from sqlalchemy.exc import IntegrityError
from ..models import MessageQueue, ContactConsent, Conversation, now
from ..permissions import rows
from ..store import event_key, audit, settings
from ..config import contact
from ..services.business_data_service import invoice_balance, eship_invoice_balance

ERP_KINDS = (
    'payment_due',
    'payment_overdue',
    'lead_followup',
    'quotation_followup',
    'unanswered_inquiry',
    'workshop_ready',
    'daily_briefing',
)

ESHIP_KINDS = (
    'eship_payment_due',
    'eship_shipment_status',
    'eship_delivery_exception',
    'eship_freight_overdue',
    'daily_briefing',
)

KINDS = tuple(dict.fromkeys(ERP_KINDS + ESHIP_KINDS))
CATEGORIES = ('sales', 'purchases', 'receivables', 'collections', 'quotations', 'workshop', 'stock')

OPT_OUT_KEYWORDS = frozenset({'stop', 'unsubscribe', 'optout', 'opt-out', 'cancel', 'band karo', 'mat bhejo'})
OPT_IN_KEYWORDS = frozenset({'start', 'subscribe', 'optin', 'opt-in', 'unstop'})


def consent(db, scope, channel, recipient):
    norm = contact(recipient, channel)
    return rows(db, ContactConsent, scope).filter(
        ContactConsent.channel == channel,
        ContactConsent.contact.in_([recipient, norm]),
        ContactConsent.allowed.is_(True),
    ).first() is not None


def set_consent(db, scope, channel, recipient, allowed=True, source='admin'):
    scope.require(action='edit')
    if isinstance(allowed, str):
        allowed_bool = allowed.strip().lower() in ('1', 'true', 'yes', 'opted_in', 'allow', 'allowed')
    else:
        allowed_bool = bool(allowed)
    norm = contact(recipient, channel)
    row = rows(db, ContactConsent, scope).filter_by(channel=channel, contact=norm).first()
    if row:
        row.allowed = allowed_bool
        row.source = str(source or 'admin')[:50]
        row.updated_at = now()
    else:
        row = ContactConsent(
            company_id=scope.company_id,
            channel=channel,
            contact=norm,
            allowed=allowed_bool,
            source=str(source or 'admin')[:50],
        )
        db.add(row)
    audit(db, scope, 'consent.updated', norm, channel=channel, allowed=allowed_bool, source=source)
    db.commit()
    return row


def process_inbound_consent_keyword(db, scope, channel, sender, message_text):
    """Automatically honour STOP/UNSUBSCRIBE opt-outs and START opt-ins on inbound messages."""
    clean = str(message_text or '').strip().lower()
    if clean in OPT_OUT_KEYWORDS:
        norm = contact(sender, channel)
        row = rows(db, ContactConsent, scope).filter_by(channel=channel, contact=norm).first()
        if row:
            row.allowed = False
            row.source = 'inbound_opt_out'
            row.updated_at = now()
        else:
            db.add(ContactConsent(company_id=scope.company_id, channel=channel, contact=norm, allowed=False, source='inbound_opt_out'))
        audit(db, scope, 'consent.opt_out', norm, channel=channel)
        db.commit()
        return 'opted_out'
    if clean in OPT_IN_KEYWORDS:
        norm = contact(sender, channel)
        row = rows(db, ContactConsent, scope).filter_by(channel=channel, contact=norm).first()
        if row:
            row.allowed = True
            row.source = 'inbound_opt_in'
            row.updated_at = now()
        else:
            db.add(ContactConsent(company_id=scope.company_id, channel=channel, contact=norm, allowed=True, source='inbound_opt_in'))
        audit(db, scope, 'consent.opt_in', norm, channel=channel)
        db.commit()
        return 'opted_in'
    return None


def within_working_hours(db, scope, current_dt=None):
    """Check whether current time in company's configured timezone falls inside work_start..work_end."""
    cfg = settings(db, scope)
    tz_name = getattr(cfg, 'timezone', None) or 'Asia/Kolkata'
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo('Asia/Kolkata')
    if current_dt is None:
        local_dt = datetime.now(tz)
    elif current_dt.tzinfo is None:
        local_dt = current_dt.replace(tzinfo=ZoneInfo('UTC')).astimezone(tz)
    else:
        local_dt = current_dt.astimezone(tz)
    start_h = int(getattr(cfg, 'work_start', 9) or 9)
    end_h = int(getattr(cfg, 'work_end', 19) or 19)
    if start_h <= end_h:
        return start_h <= local_dt.hour < end_h
    return local_dt.hour >= start_h or local_dt.hour < end_h


def queue_message(db, scope, key, channel, recipient, kind, reference, payload, template=None, approval=True):
    recipient = contact(recipient, channel)
    existing = rows(db, MessageQueue, scope).filter_by(event_key=key).first()
    if existing:
        return existing
    if not consent(db, scope, channel, recipient):
        return None
    if channel == 'whatsapp' and not template and kind != 'reply':
        raise ValueError('Select an approved WhatsApp template.')
    row = MessageQueue(company_id=scope.company_id, actor=scope.actor, event_key=key,
        channel=channel, recipient=recipient, kind=kind, reference=str(reference), payload=payload,
        template=template, status='approval' if approval else 'pending')
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        return rows(db, MessageQueue, scope).filter_by(event_key=key).one()
    audit(db, scope, 'message.queued', row.id, kind=kind)
    return row


def collect(db, cdb, scope, rule, today):
    scope.require(owner=True)
    config = rule.config or {}
    delay = int(config.get('delay_days', 7))
    channel, template = config.get('channel', 'email'), config.get('template')
    candidates = []

    if rule.kind in ('payment_due', 'payment_overdue'):
        from customer_models import CustomerInvoice
        scope.require(module='core', permission='customer_invoices')
        for inv in cdb.query(CustomerInvoice).filter_by(company_id=scope.company_id):
            due = inv.due_date
            match = due == today if rule.kind == 'payment_due' else bool(due and due <= today - timedelta(days=delay))
            if match:
                value = invoice_balance(cdb, scope, inv.id)
                if value:
                    candidates.append((str(inv.id), value['phone'] if channel == 'whatsapp' else value['email'], value))

    elif rule.kind in ('lead_followup', 'quotation_followup'):
        from customer_models import CRMLead, CRMQuotation, CRMInteraction, Client
        scope.require(module='crm')
        model = CRMLead if rule.kind == 'lead_followup' else CRMQuotation
        for row in cdb.query(model).filter_by(company_id=scope.company_id):
            if rule.kind == 'lead_followup' and row.stage in ('Won', 'Lost'):
                continue
            if rule.kind == 'quotation_followup' and row.status != 'Sent':
                continue
            last = row.updated_at or row.created_at
            if not last or last.date() > today - timedelta(days=delay):
                continue
            lead_id = row.id if model is CRMLead else row.lead_id
            if not lead_id:
                continue
            if cdb.query(CRMInteraction).filter(
                CRMInteraction.company_id == scope.company_id,
                CRMInteraction.lead_id == lead_id,
                CRMInteraction.created_at > last,
            ).first():
                continue
            client = cdb.query(Client).filter_by(company_id=scope.company_id, id=row.client_id).first()
            if client:
                candidates.append((row.id, client.phone if channel == 'whatsapp' else client.email,
                                   {'text': f'Following up on {row.title}. Please let us know how we can help.', 'version': last.isoformat()}))

    elif rule.kind == 'unanswered_inquiry':
        from customer_models import CRMLead, CRMInteraction, Client
        scope.require(module='crm')
        for row in cdb.query(CRMLead).filter_by(company_id=scope.company_id, stage='New'):
            created = row.created_at
            if not created or created.date() > today - timedelta(days=max(delay, 1)):
                continue
            has_reply = cdb.query(CRMInteraction).filter(
                CRMInteraction.company_id == scope.company_id,
                CRMInteraction.lead_id == row.id,
                CRMInteraction.type.in_(('call', 'email', 'whatsapp', 'meeting')),
            ).first()
            if has_reply:
                continue
            client = cdb.query(Client).filter_by(company_id=scope.company_id, id=row.client_id).first()
            if client:
                candidates.append((row.id, client.phone if channel == 'whatsapp' else client.email,
                                   {'text': f'We received your inquiry regarding "{row.title}" and are reviewing it for you.', 'version': created.isoformat()}))

    elif rule.kind == 'workshop_ready':
        from customer_models import WorkshopJobCard, Client
        scope.require(module='repair')
        for row in cdb.query(WorkshopJobCard).filter_by(company_id=scope.company_id, status='Ready'):
            client = cdb.query(Client).filter_by(company_id=scope.company_id, id=row.client_id).first()
            if client:
                candidates.append((str(row.id), client.phone if channel == 'whatsapp' else client.email,
                                   {'text': f'Your workshop job {row.job_number} is marked Ready.', 'version': str(row.updated_at)}))

    elif rule.kind in ('eship_payment_due', 'eship_freight_overdue'):
        from customer_models import Invoice, CustomerInvoice
        for model in (CustomerInvoice, Invoice):
            for inv in cdb.query(model).filter_by(company_id=scope.company_id):
                due = getattr(inv, 'due_date', None) or getattr(inv, 'date', None)
                match = (due == today) if rule.kind == 'eship_payment_due' else bool(due and due <= today - timedelta(days=delay))
                if match:
                    value = eship_invoice_balance(cdb, scope, inv.id)
                    if value:
                        candidates.append((str(inv.id), value['phone'] if channel == 'whatsapp' else value['email'], value))

    elif rule.kind in ('eship_shipment_status', 'eship_delivery_exception'):
        from customer_models import Invoice, Client
        for inv in cdb.query(Invoice).filter_by(company_id=scope.company_id):
            if (inv.status or '').lower() in ('void', 'draft', 'cancelled', 'canceled'):
                continue
            try:
                meta = json.loads(inv.terms or '{}') if isinstance(inv.terms, str) else (inv.terms or {})
            except Exception:
                meta = {}
            t_status = str((meta if isinstance(meta, dict) else {}).get('tracking_status') or '').strip()
            if not t_status:
                continue
            is_exception = any(x in t_status.lower() for x in ('return', 'exception'))
            if rule.kind == 'eship_delivery_exception' and not is_exception:
                continue
            if rule.kind == 'eship_shipment_status' and is_exception:
                continue
            client = cdb.query(Client).filter_by(company_id=scope.company_id, id=inv.client_id).first()
            if client:
                docket = inv.docket_no or meta.get('docket_no') or inv.invoice_id
                candidates.append((
                    str(docket),
                    client.phone if channel == 'whatsapp' else client.email,
                    {
                        'text': f"Latest status recorded by eShip for {docket}: {t_status}. This is the recorded eShip status, not live carrier tracking.",
                        'awb': str(docket),
                        'status': t_status,
                        'version': f"{docket}:{t_status}",
                    },
                ))

    count = 0
    for reference, recipient, payload in candidates:
        if not recipient:
            continue
        key = event_key(rule.id, rule.kind, reference, payload.get('version', str(today)))
        if queue_message(db, scope, key, channel, recipient, rule.kind, reference,
                         dict(payload, rule_id=rule.id, delay_days=delay), template, rule.approval_required):
            count += 1
    return count


def refresh_message(cdb, scope, row, today):
    """Re-evaluate business state at send time; return None to suppress stale sends."""
    if row.kind in ('payment_due', 'payment_overdue'):
        value = invoice_balance(cdb, scope, row.reference)
        if not value or not value['due_date']:
            return None
        due = date.fromisoformat(value['due_date'])
        if (row.kind == 'payment_due' and due != today) or (row.kind == 'payment_overdue' and due > today - timedelta(days=int(row.payload.get('delay_days', 7)))):
            return None
        current_contact = value['phone'] if row.channel == 'whatsapp' else value['email']
        if not current_contact or contact(current_contact, row.channel) != row.recipient:
            return None
        return {'text': f"Payment reminder: invoice {value['number']} has an outstanding balance of {value['currency']} {value['balance']}, due {value['due_date']}.",
                'parameters': [value['number'], value['currency'], value['balance'], value['due_date']]}

    if row.kind in ('eship_payment_due', 'eship_freight_overdue'):
        value = eship_invoice_balance(cdb, scope, row.reference)
        if not value or not value['due_date']:
            return None
        due = date.fromisoformat(value['due_date'])
        if (row.kind == 'eship_payment_due' and due != today) or (row.kind == 'eship_freight_overdue' and due > today - timedelta(days=int(row.payload.get('delay_days', 7)))):
            return None
        current_contact = value['phone'] if row.channel == 'whatsapp' else value['email']
        if not current_contact or contact(current_contact, row.channel) != row.recipient:
            return None
        return {'text': f"Freight payment reminder: invoice {value['number']} has an outstanding balance of {value['currency']} {value['balance']}, due {value['due_date']}.",
                'parameters': [value['number'], value['currency'], value['balance'], value['due_date']]}

    if row.kind in ('lead_followup', 'quotation_followup', 'unanswered_inquiry', 'workshop_ready'):
        from customer_models import CRMLead, CRMQuotation, WorkshopJobCard, Client, CRMInteraction
        model = {
            'lead_followup': CRMLead,
            'unanswered_inquiry': CRMLead,
            'quotation_followup': CRMQuotation,
            'workshop_ready': WorkshopJobCard,
        }[row.kind]
        scope.require(module='repair' if row.kind == 'workshop_ready' else 'crm', owner=True)
        record = cdb.query(model).filter_by(company_id=scope.company_id, id=row.reference).first()
        if not record:
            return None
        if row.kind in ('lead_followup', 'unanswered_inquiry') and record.stage in ('Won', 'Lost'):
            return None
        if row.kind == 'quotation_followup' and record.status != 'Sent':
            return None
        if row.kind == 'workshop_ready' and record.status != 'Ready':
            return None
        if str(record.updated_at or record.created_at) != str(row.payload.get('version')).replace('T', ' '):
            return None
        client = cdb.query(Client).filter_by(company_id=scope.company_id, id=record.client_id).first()
        recipient = (client.phone if row.channel == 'whatsapp' else client.email) if client else None
        if not recipient or contact(recipient, row.channel) != row.recipient:
            return None
        if row.kind != 'workshop_ready':
            lead_id = record.id if row.kind in ('lead_followup', 'unanswered_inquiry') else record.lead_id
            if cdb.query(CRMInteraction).filter(CRMInteraction.company_id == scope.company_id, CRMInteraction.lead_id == lead_id,
                    CRMInteraction.created_at > (record.updated_at or record.created_at)).first():
                return None
        return {'text': row.payload['text'], 'parameters': [row.payload['text']]}

    if row.kind in ('eship_shipment_status', 'eship_delivery_exception'):
        return {'text': row.payload.get('text', ''), 'parameters': row.payload.get('parameters', [row.payload.get('text', '')])}

    if row.kind in ('reply', 'briefing'):
        return row.payload
    raise ValueError('Unknown message type; delivery blocked.')

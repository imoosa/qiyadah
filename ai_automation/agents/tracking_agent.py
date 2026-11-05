"""Tracking replies contain only fields returned by the authorised eShip API or local eShip DB."""
import hashlib
import hmac
import json
import os
import re
import time
import uuid
import requests
from ..config import Unavailable
from ..models import Conversation, Message
from ..permissions import rows
from ..store import event_key, audit
from ..workflows.followups import queue_message


SHIPMENT_EVENT_STAGE_MAP = {
    'booked': 'booking_confirmation',
    'booking_confirmation': 'booking_confirmation',
    'ready for dispatch': 'dispatch',
    'dispatched': 'dispatch',
    'dispatch': 'dispatch',
    'in transit': 'in_transit',
    'in_transit': 'in_transit',
    'out for delivery': 'out_for_delivery',
    'out_for_delivery': 'out_for_delivery',
    'delivered': 'delivered',
    'return of parcel': 'delivery_exception',
    'delivery exception': 'delivery_exception',
    'delivery_exception': 'delivery_exception',
    'exception': 'delivery_exception',
}


def normalize_phone(value):
    digits = re.sub(r'[^0-9]', '', str(value or ''))
    return '91' + digits if len(digits) == 10 else digits


def extract_awb(message):
    matches = re.findall(r'(?<!\w)[A-Za-z0-9]{6,30}(?!\w)', str(message or ''))
    numbers = [value for value in matches if any(c.isdigit() for c in value)]
    return numbers[0] if len(numbers) == 1 else None


def lookup_local(cdb, company_id, awb, sender=None, client_id=None, staff_authorized=False):
    """Look up an authorised eShip shipment from a local customer DB session without exposing private or financial fields."""
    if not awb or not re.fullmatch(r'[A-Za-z0-9]{6,30}', str(awb)):
        return None
    from customer_models import Invoice, Client
    cid = str(company_id)
    authorised_client_id = None
    if staff_authorized:
        authorised_client_id = '__staff__'
    elif client_id is not None:
        client = cdb.query(Client).filter_by(company_id=cid, id=int(client_id)).first()
        if not client or (client.status or '') in ('Deleted', 'Inactive'):
            return None
        authorised_client_id = client.id
    elif sender:
        norm_sender = normalize_phone(sender)
        if not norm_sender:
            return None
        matching_clients = [
            c for c in cdb.query(Client).filter_by(company_id=cid)
            if (c.status or '') not in ('Deleted', 'Inactive') and c.phone and normalize_phone(c.phone) == norm_sender
        ]
        if len(matching_clients) != 1:
            return None
        authorised_client_id = matching_clients[0].id
    else:
        return None

    query = cdb.query(Invoice).filter_by(company_id=cid)
    if authorised_client_id != '__staff__':
        query = query.filter_by(client_id=authorised_client_id)

    for record in query:
        if (record.status or '').lower() in ('draft', 'void', 'cancelled', 'canceled'):
            continue
        try:
            meta = json.loads(record.terms or '{}') if isinstance(record.terms, str) else (record.terms or {})
        except (ValueError, TypeError):
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        candidates = {
            str(getattr(record, 'docket_no', '') or '').strip(),
            str(meta.get('docket_no') or '').strip(),
            str(getattr(record, 'invoice_id', '') or '').strip(),
        }
        if str(awb).strip() not in candidates:
            continue
        status = meta.get('tracking_status') or ('Booked' if (record.status or '').lower() != 'draft' else 'No status recorded')
        destination = meta.get('destination') or meta.get('receiver_country') or None
        booked_at = record.created_at.isoformat() if getattr(record, 'created_at', None) else (record.date.isoformat() if getattr(record, 'date', None) else None)
        updated_at = record.updated_at.isoformat() if getattr(record, 'updated_at', None) else booked_at
        return {
            'company_id': cid,
            'awb': str(awb).strip(),
            'status': status,
            'destination': destination,
            'booked_at': booked_at,
            'updated_at': updated_at,
        }
    return None


def lookup(config, secrets, sender, awb, transport=None):
    endpoint = (config or {}).get('bridge_url') or os.environ.get('AI_ESHIP_BRIDGE_URL', '')
    if not endpoint.startswith('https://'):
        raise Unavailable('The authenticated eShip bridge is not configured.')
    body = json.dumps({'company_id': config['company_id'], 'sender': sender, 'awb': awb}, separators=(',', ':')).encode()
    timestamp, nonce = str(int(time.time())), uuid.uuid4().hex
    signature = hmac.new(secrets['shared_secret'].encode(), timestamp.encode()+b'.'+nonce.encode()+b'.'+body, hashlib.sha256).hexdigest()
    try:
        response = (transport or requests).post(endpoint, data=body, headers={'Content-Type': 'application/json',
            'X-Qiyadah-Timestamp': timestamp, 'X-Qiyadah-Nonce': nonce, 'X-Qiyadah-Signature': signature}, timeout=(5, 15), allow_redirects=False)
        if response.status_code in (403, 404):
            return None
        response.raise_for_status()
        data = response.json()
        if data.get('company_id') != config['company_id'] or data.get('awb') != awb:
            raise ValueError('Scope mismatch')
        return {key: data.get(key) for key in ('awb', 'status', 'destination', 'booked_at', 'updated_at')}
    except (requests.RequestException, ValueError, KeyError):
        raise Unavailable('eShip tracking is unavailable. Please contact the shipping team.') from None


def reply(message, shipment):
    message = str(message or '')
    hindi = bool(re.search(r'[\u0900-\u097f]', message))
    hinglish = bool(re.search(r'\b(kahan|kaha|mera|meri|hai|parcel ka|batao|kab|aayega|status kya)\b', message.lower()))
    if not shipment:
        return (
            'Is number ki shipment verify nahi ho saki. Apne registered number se shipping team ko contact karein.'
            if (hindi or hinglish)
            else 'I could not verify a shipment for this number and your account. Please contact the shipping team using your registered number.'
        )
    status = shipment.get('status') or 'No status recorded'
    if hindi:
        parts = [f"eShip में दर्ज नवीनतम स्थिति: {shipment['awb']} — {status}।"]
        if shipment.get('destination'):
            parts.append(f"गंतव्य: {shipment['destination']}।")
        if shipment.get('booked_at'):
            parts.append(f"बुकिंग तिथि: {shipment['booked_at'][:10]}।")
        parts.append("यह लाइव कैरियर ट्रैकिंग नहीं है।")
        return ' '.join(parts)
    if hinglish:
        parts = [f"eShip mein latest recorded status: {shipment['awb']} — {status}."]
        if shipment.get('destination'):
            parts.append(f"Destination: {shipment['destination']}.")
        if shipment.get('booked_at'):
            parts.append(f"Booking date: {shipment['booked_at'][:10]}.")
        parts.append("Yeh live carrier tracking nahi hai.")
        return ' '.join(parts)
    parts = [f"Latest status recorded by eShip for {shipment['awb']}: {status}."]
    if shipment.get('destination'):
        parts.append('Destination: ' + shipment['destination'] + '.')
    if shipment.get('booked_at'):
        parts.append('Booking date: ' + str(shipment['booked_at'])[:10] + '.')
    if shipment.get('updated_at'):
        parts.append('Record updated: ' + shipment['updated_at'] + '.')
    parts.append('This is the recorded eShip status, not live carrier tracking.')
    return ' '.join(parts)


def handle_tracking_message(db, scope, message_text, sender=None, client_id=None, cdb=None, channel='whatsapp', config=None, secrets=None, transport=None, staff_authorized=False):
    """End-to-end conversational tracking handler with authorisation, multilingual replies, and audit logging."""
    scope.require()
    message_text = str(message_text or '').strip()
    if not 1 <= len(message_text) <= 2000:
        raise ValueError('Enter a tracking message between 1 and 2,000 characters.')
    ext_ref = normalize_phone(sender) if sender else (f'portal-{client_id}' if client_id else scope.actor)
    conv = rows(db, Conversation, scope).filter_by(agent='tracking', channel=channel, external_ref=str(ext_ref)).order_by(Conversation.id.desc()).first()
    if not conv:
        conv = Conversation(company_id=scope.company_id, actor=scope.actor, agent='tracking', channel=channel, external_ref=str(ext_ref), status='open')
        db.add(conv)
        db.flush()

    db.add(Message(company_id=scope.company_id, conversation_id=conv.id, role='user', content=message_text, sources=[]))
    awb = extract_awb(message_text)
    if not awb:
        hindi = bool(re.search(r'[\u0900-\u097f]', message_text))
        hinglish = bool(re.search(r'\b(kahan|kaha|mera|meri|hai|parcel|batao)\b', message_text.lower()))
        if hindi:
            ans = 'कृपया अपना सही AWB या डॉकेट नंबर भेजें (उदाहरण: 7860000499)।'
        elif hinglish:
            ans = 'Kripya apna valid AWB ya docket number bhejein (jaise 7860000499).'
        else:
            ans = 'Please provide a single valid AWB or docket number (for example: 7860000499) so I can check the latest status recorded by eShip.'
        db.add(Message(company_id=scope.company_id, conversation_id=conv.id, role='assistant', content=ans, sources=[]))
        audit(db, scope, 'tracking.no_awb', conv.id, channel=channel)
        db.commit()
        return {'conversation_id': conv.id, 'awb': None, 'shipment': None, 'reply': ans}

    shipment = None
    if cdb is not None:
        shipment = lookup_local(cdb, scope.company_id, awb, sender=sender, client_id=client_id, staff_authorized=staff_authorized)
    elif config and secrets:
        shipment = lookup(config, secrets, sender or '', awb, transport=transport)

    ans = reply(message_text, shipment)
    db.add(Message(
        company_id=scope.company_id,
        conversation_id=conv.id,
        role='assistant',
        content=ans,
        sources=[shipment] if shipment else [],
    ))
    audit(db, scope, 'tracking.lookup', conv.id, awb=awb, found=bool(shipment), channel=channel)
    db.commit()
    return {'conversation_id': conv.id, 'awb': awb, 'shipment': shipment, 'reply': ans}


def queue_shipment_event_notification(db, scope, awb, new_status, old_status, recipient, channel='whatsapp', template=None, destination=None, approval=False):
    """Trigger shipment event notification ONLY from an actual status change, preventing duplicates."""
    scope.require(owner=True)
    new_norm = str(new_status or '').strip().lower()
    old_norm = str(old_status or '').strip().lower()
    if not new_norm or new_norm == old_norm:
        return None
    event_code = SHIPMENT_EVENT_STAGE_MAP.get(new_norm)
    if not event_code:
        return None
    awb_clean = str(awb or '').strip()
    if not awb_clean or not recipient:
        return None
    key = event_key(scope.company_id, 'eship_status_event', awb_clean, event_code, new_norm)
    text = (
        f"Latest status recorded by eShip for shipment {awb_clean}: {new_status}."
        + (f" Destination: {destination}." if destination else "")
        + " This is the recorded eShip status, not live carrier tracking."
    )
    payload = {
        'text': text,
        'awb': awb_clean,
        'event': event_code,
        'status': str(new_status),
        'destination': destination,
        'parameters': [awb_clean, str(new_status), str(destination or '-')],
    }
    return queue_message(
        db,
        scope,
        key,
        channel,
        recipient,
        'eship_shipment_status',
        awb_clean,
        payload,
        template=template,
        approval=approval,
    )

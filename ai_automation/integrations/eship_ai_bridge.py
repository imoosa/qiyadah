"""Install this standalone file in eShip; register with existing app callbacks.

Verified against logistic-erp's Invoice/Client models and customer_user session.
No imports of ERP business models. No database writes or public AWB lookups.
"""
import hashlib
import hmac
import json
import os
import re
import time
from flask import request, jsonify, session


def phone(value):
    value = re.sub(r'[^0-9]', '', str(value or ''))
    # Existing eShip phone formatter uses India as the default for ten digits.
    return '91' + value if len(value) == 10 else value


def authorised_shipment(cdb, company_id, client_id, awb, Invoice):
    if not re.fullmatch(r'[A-Za-z0-9]{6,30}', awb):
        return None
    # Exact JSON comparison after company AND customer filtering avoids LIKE
    # wildcard disclosure and legacy JSON serialization differences.
    for record in cdb.query(Invoice).filter_by(company_id=company_id, client_id=client_id):
        if (record.status or '').lower() in ('draft', 'void', 'cancelled', 'canceled'):
            continue
        try:
            meta = json.loads(record.terms or '{}')
        except (ValueError, TypeError):
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        if awb not in (record.docket_no, meta.get('docket_no')):
            continue
        return {'company_id': company_id, 'awb': awb, 'status': meta.get('tracking_status') or 'No status recorded',
            'destination': meta.get('destination') or None,
            'booked_at': record.created_at.isoformat() if record.created_at else None,
            'updated_at': record.updated_at.isoformat() if record.updated_at else None}
    return None


def register_eship_ai_bridge(app, get_customer_session, customer_login_required):
    from customer_models import Invoice, Client
    from platform_models import Company

    @app.route('/api/ai-bridge/tracking', methods=['POST'])
    def eship_ai_bridge_tracking():
        if request.content_length is None or request.content_length > 8192:
            return jsonify(error='Invalid request'), 400
        raw = request.get_data()
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='Invalid request'), 400
        cid = str(data.get('company_id', ''))
        # Operator maps each company to its own secret; never accept one tenant's
        # credentials for another tenant or allow browser-selected authority.
        secrets = json.loads(os.environ.get('ESHIP_AI_COMPANY_SECRETS', '{}'))
        secret = secrets.get(cid)
        stamp, nonce = request.headers.get('X-Qiyadah-Timestamp', ''), request.headers.get('X-Qiyadah-Nonce', '')
        try:
            fresh = abs(time.time() - int(stamp)) <= 120
        except ValueError:
            fresh = False
        if not secret or not fresh or not re.fullmatch(r'[a-f0-9]{32}', nonce):
            return jsonify(error='Not authorised'), 403
        expected = hmac.new(secret.encode(), stamp.encode()+b'.'+nonce.encode()+b'.'+raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, request.headers.get('X-Qiyadah-Signature', '')):
            return jsonify(error='Not authorised'), 403
        company = Company.query.filter_by(company_id=cid, is_active=True).first()
        if not company:
            return jsonify(error='Not found'), 404
        cdb = get_customer_session(cid)
        sender = phone(data.get('sender'))
        clients = [c for c in cdb.query(Client).filter_by(company_id=cid)
                   if c.status not in ('Deleted', 'Inactive') and sender and phone(c.phone) == sender]
        if len(clients) != 1:
            return jsonify(error='Not found'), 404
        result = authorised_shipment(cdb, cid, clients[0].id, str(data.get('awb', '')), Invoice)
        return (jsonify(result), 200) if result else (jsonify(error='Not found'), 404)

    @app.route('/customer/ai-tracking', methods=['GET'])
    @customer_login_required
    def eship_customer_ai_tracking():
        user = session['customer_user']
        cid, client_id = user['company_id'], user['client_pk']
        cdb = get_customer_session(cid)
        client = cdb.query(Client).filter_by(company_id=cid, id=client_id).first()
        if not client or client.status in ('Deleted', 'Inactive'):
            return jsonify(error='Not authorised'), 403
        result = authorised_shipment(cdb, cid, client_id, request.args.get('awb', ''), Invoice)
        return (jsonify(result), 200) if result else (jsonify(error='Not found'), 404)

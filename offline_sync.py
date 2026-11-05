"""Durable, company-bound replay receipts for explicitly supported ERP writes.

The receipt is written in the same transaction as the first business mutation.
A process crash after that commit leaves 'applied', which is never executed again.
"""
import hashlib
import hmac
import json
import re
from functools import wraps
from uuid import UUID
from flask import g, request, session, jsonify, has_request_context
from sqlalchemy import event, inspect, select, update, insert
from sqlalchemy.orm import Session
from customer_models import OfflineRevision, OfflineReceipt

REV = OfflineRevision.__table__
RECEIPT = OfflineReceipt.__table__
CREATE = {
    'client_new', 'client_add', 'supplier_new', 'inventory_add', 'customer_invoice_create',
    'purchase_invoice_new', 'estimate_new', 'add_expense', 'delivery_challan_new',
    'sales_order_new', 'purchase_order_new', 'api_order_list_create', 'api_order_departments',
    'api_sales_orders', 'api_order_erp_clients', 'api_crm_clients', 'api_crm_contacts',
    'api_crm_leads', 'api_crm_activities', 'api_crm_quotations', 'api_crm_comm_log',
    'api_workshop_vehicles', 'api_workshop_job_cards', 'api_workshop_tasks',
    'api_workshop_service_catalog', 'hr_employee_new', 'hr_leaves', 'hr_my_leaves',
    'hr_expense_claims', 'hr_my_claims', 'hr_recruitment', 'hr_assets',
}
EDIT = {
    'client_edit', 'supplier_edit', 'inventory_edit', 'customer_invoice_edit',
    'purchase_invoice_edit', 'estimate_edit', 'estimate_update', 'edit_expense',
    'delivery_challan_edit', 'sales_order_edit', 'purchase_order_edit',
    'api_crm_client_detail', 'api_crm_lead_detail', 'api_crm_lead_stage',
    'api_crm_quotation_detail', 'crm_projects', 'api_workshop_vehicle_detail',
    'api_workshop_vehicle_service_plan', 'api_workshop_job_card_detail',
    'api_workshop_job_card_inspection', 'api_workshop_job_card_estimate',
    'api_workshop_update_task_status', 'api_workshop_qc', 'api_workshop_service_catalog_item',
    'hr_employee_edit', 'hr_departments', 'hr_designations', 'hr_shifts', 'hr_shift_assign',
    'hr_holidays', 'hr_attendance_save', 'hr_leave_types', 'hr_leave_balances',
    'hr_my_profile', 'hr_recruitment_job', 'hr_candidate_stage', 'hr_onboarding', 'hr_performance',
}
SAFE_PAGE_ENDPOINTS = {
    'client_list', 'supplier_list', 'inventory_list', 'customer_invoice_list', 'customer_invoice_new',
    'purchase_invoice_list', 'estimate_list', 'expenses', 'sync_data', 'apps_hub',
    'workshop_erp_view', 'workshop_erp_dashboard', 'repair_bills_view', 'repair_bill_view',
    'crm_view', 'crm_dashboard', 'order_erp_view', 'order_erp_dashboard', 'hr_dashboard',
    'hr_employees', 'hr_attendance', 'hr_assets', 'hr_recruitment', 'hr_performance',
    'hr_leaves', 'hr_my_leaves', 'hr_expense_claims', 'hr_my_claims', 'hr_onboarding',
}
SECRET = re.compile(r'password|secret|access.?token|api.?key|authorization|verification.?pin', re.I)


class OfflineConflict(Exception):
    pass


def setup_offline_schema(engine, company_id):
    """Called only by the application's existing explicit database initialization."""
    OfflineRevision.__table__.create(engine, checkfirst=True)
    OfflineReceipt.__table__.create(engine, checkfirst=True)
    with engine.begin() as conn:
        if not conn.execute(select(REV.c.company_id).where(REV.c.company_id == str(company_id))).first():
            conn.execute(insert(REV).values(company_id=str(company_id), revision=0))


def schema_ready(engine):
    tables = set(inspect(engine).get_table_names())
    return {REV.name, RECEIPT.name} <= tables


def _touch(db):
    """Serialize all customer writes and attach an offline receipt before commit."""
    if not db.info.get('offline_schema_ready') or db.info.get('_offline_touched'):
        return
    cid = str(db.info.get('finance_period_company') or '')
    if not cid:
        return
    conn = db.connection()
    row = conn.execute(select(REV.c.revision).where(REV.c.company_id == cid).with_for_update()).first()
    if not row:
        raise OfflineConflict('Offline storage is not initialized for this company.')
    previous = row[0]
    ctx = g.get('offline_write') if has_request_context() else None
    if ctx and ctx['db'] is db and ctx['company_id'] == cid:
        expected = ctx.get('last_revision', ctx.get('base_revision'))
        if expected is not None and previous != expected:
            g.offline_error = 'Other changes were saved after this form was opened. Review the latest record before saving your offline changes.'
            raise OfflineConflict(g.offline_error)
        saved = conn.execute(select(RECEIPT).where(RECEIPT.c.request_id == ctx['request_id'])).mappings().first()
        if saved and not ctx.get('committed'):
            g.offline_error = 'This request has already reached the database. Refresh its sync status.'
            raise OfflineConflict(g.offline_error)
        if not saved:
            conn.execute(insert(RECEIPT).values(request_id=ctx['request_id'], company_id=cid,
                scope=ctx['scope'], fingerprint=ctx['fingerprint'], state='applied',
                previous_revision=previous, revision=previous + 1))
        else:
            conn.execute(update(RECEIPT).where(RECEIPT.c.request_id == ctx['request_id']).values(revision=previous + 1))
        ctx.setdefault('previous_revision', previous)
        ctx['last_revision'] = previous + 1
    conn.execute(update(REV).where(REV.c.company_id == cid).values(revision=previous + 1))
    db.info['_offline_touched'] = True


def _before_flush(db, *_):
    if db.new or db.deleted or any(db.is_modified(item, include_collections=True) for item in db.dirty):
        _touch(db)


def _before_execute(execution):
    if execution.is_insert or execution.is_update or execution.is_delete:
        _touch(execution.session)


def _after_commit(db):
    if db.info.pop('_offline_touched', None) and has_request_context():
        ctx = g.get('offline_write')
        if ctx and ctx['db'] is db:
            ctx['committed'] = True


def _after_rollback(db):
    db.info.pop('_offline_touched', None)


for event_name, callback in [('before_flush', _before_flush), ('do_orm_execute', _before_execute),
                             ('after_commit', _after_commit), ('after_rollback', _after_rollback)]:
    if not event.contains(Session, event_name, callback):
        event.listen(Session, event_name, callback)


def _payload():
    if request.is_json:
        value = request.get_json(silent=True)
        if not isinstance(value, (dict, list)):
            raise OfflineConflict('The saved request could not be read.')
    else:
        value = sorted((key, request.form.getlist(key)) for key in request.form if key != '_csrf')
    def check(item):
        if isinstance(item, dict):
            for key, val in item.items():
                if SECRET.search(str(key)):
                    raise OfflineConflict('Password and credential changes require an online connection.')
                check(val)
        elif isinstance(item, list):
            for val in item:
                check(val)
    if not request.is_json:
        for key in request.form:
            if SECRET.search(key):
                raise OfflineConflict('Password and credential changes require an online connection.')
    check(value)
    if any(file.filename for file in request.files.values()):
        raise OfflineConflict('Attachments need an online save. Your offline form remains on this PC.')
    return hashlib.sha256(json.dumps([request.method, request.path, value], sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def register_offline_sync(app, login_required, get_user, get_company, get_cdb, company_lookup):
    rules = [r for r in app.url_map.iter_rules() if r.endpoint in CREATE | EDIT]
    allowed = {(r.endpoint, method) for r in rules for method in r.methods & {'POST', 'PUT', 'PATCH'}}
    actions = [{'path': r.rule, 'methods': sorted(r.methods & {'POST', 'PUT', 'PATCH'}),
        'label': r.endpoint.replace('_', ' ').replace('api ', '').title(),
        'mode': 'edit' if r.endpoint in EDIT else 'create', 'requires_revision': r.endpoint in EDIT}
        for r in rules if r.methods & {'POST', 'PUT', 'PATCH'}]
    pages = sorted({r.rule for r in app.url_map.iter_rules()
        if 'GET' in r.methods and r.endpoint in CREATE | EDIT | SAFE_PAGE_ENDPOINTS})

    def identity():
        user, cid = get_user() or {}, str(get_company() or '')
        if not user.get('user_id') or not cid:
            raise OfflineConflict('Sign in and select a company before syncing.')
        raw = json.dumps([str(user['user_id']), str(user.get('email', '')).lower(), cid])
        scope = hmac.new(str(app.secret_key).encode(), raw.encode(), hashlib.sha256).hexdigest()
        return user, cid, scope

    def context():
        user, cid, scope = identity()
        db = get_cdb()
        if not db.info.get('offline_schema_ready'):
            raise OfflineConflict('Offline syncing needs the server database update before it can be enabled.')
        revision = db.connection().execute(select(REV.c.revision).where(REV.c.company_id == cid)).scalar_one()
        company = company_lookup(cid)
        return {'success': True, 'scope': scope, 'company': getattr(company, 'company_name', cid),
            'user': user.get('full_name') or user.get('email') or str(user['user_id']),
            'revision': revision, 'csrf_token': app.jinja_env.globals['csrf_token'](),
            'actions': actions, 'pages': pages}

    @app.route('/api/offline/context', methods=['GET'])
    @login_required
    def offline_context():
        try:
            return jsonify(context())
        except OfflineConflict as exc:
            return jsonify(success=False, error=str(exc)), 409

    @app.before_request
    def prepare_offline():
        if request.method == 'GET' and request.endpoint in CREATE | EDIT | SAFE_PAGE_ENDPOINTS:
            try:
                g.offline_page_context = context()
            except Exception:
                pass  # Ordinary online use remains available until explicit migration.
        key = request.headers.get('X-Qiyadah-Request-ID')
        supplied_scope = request.headers.get('X-Qiyadah-Offline-Scope')
        if not key and not supplied_scope:
            return
        try:
            if (request.endpoint, request.method) not in allowed:
                raise OfflineConflict('This action requires an online connection and is not eligible for automatic replay.')
            user, cid, scope = identity()
            if not supplied_scope or not hmac.compare_digest(scope, supplied_scope):
                return jsonify(success=False, error='Sign in to the same account and company that saved this entry.', scope_mismatch=True), 409
            try:
                key = str(UUID(str(key)))
            except (ValueError, TypeError, AttributeError):
                raise OfflineConflict('A valid saved request identifier is required.') from None
            db = get_cdb()
            if not db.info.get('offline_schema_ready'):
                raise OfflineConflict('Offline syncing needs the server database update.')
            fingerprint = _payload()
            revision = db.connection().execute(select(REV.c.revision).where(REV.c.company_id == cid).with_for_update()).scalar_one()
            previous = db.connection().execute(select(RECEIPT).where(RECEIPT.c.request_id == key)).mappings().first()
            if previous:
                if previous['scope'] != scope or previous['fingerprint'] != fingerprint:
                    raise OfflineConflict('This request identifier was already used for another entry.')
                if previous['state'] == 'completed':
                    return jsonify(json.loads(previous['response_json']))
                return jsonify(success=False, needs_review=True, error='This entry reached the database but its final result was interrupted. Check the record before trying a new save.'), 409
            base = None
            if request.endpoint in EDIT:
                try:
                    base = int(request.headers.get('X-Qiyadah-Base-Revision', ''))
                    if base < 0:
                        raise ValueError()
                except ValueError:
                    raise OfflineConflict('Reopen this record online before editing it offline.') from None
                if base != revision:
                    return jsonify(success=False, conflict=True, error='Other changes were saved after this form was opened. Review the latest record before syncing this edit.'), 409
            g.offline_write = {'db': db, 'company_id': cid, 'scope': scope, 'request_id': key,
                'fingerprint': fingerprint, 'base_revision': base, 'flash_count': len(session.get('_flashes', []))}
            # The browser marks an unedited server-generated suggestion explicitly.
            if request.endpoint == 'customer_invoice_create' and request.headers.get('X-Qiyadah-Auto-Number') == '1':
                form = request.form.copy(); form['invoice_number'] = ''; request.__dict__['form'] = form
        except OfflineConflict as exc:
            return jsonify(success=False, error=str(exc)), 409

    @app.after_request
    def finish_offline(response):
        ctx = g.get('offline_write')
        if ctx:
            db = ctx['db']
            # Release/rollback any uncommitted route work before reading durable evidence.
            db.rollback()
            saved = db.connection().execute(select(RECEIPT).where(RECEIPT.c.request_id == ctx['request_id'])).mappings().first()
            data = response.get_json(silent=True) if response.is_json else None
            flashes = session.get('_flashes', [])[ctx['flash_count']:]
            errors = [str(message) for category, message in flashes if category in ('error', 'danger')]
            good = response.status_code < 400 and not errors and not g.get('offline_error')
            if isinstance(data, dict) and (data.get('success') is False or data.get('error')):
                good = False
            if not saved or not good:
                error = g.get('offline_error') or (errors[0] if errors else None) or (data.get('error') if isinstance(data, dict) else None)
                result = {'success': False, 'offline_saved': False, 'needs_review': bool(saved),
                    'error': str(error or ('The save was interrupted after reaching the database. Check the record before saving again.' if saved else 'The server did not confirm this save. Open the form online to review its validation messages.'))[:1000]}
                response = jsonify(result); response.status_code = 409 if saved or response.status_code < 400 else response.status_code
            else:
                result = dict(data) if isinstance(data, dict) else {}
                result.update(success=True, offline_saved=True,
                    redirect=response.headers.get('Location') or result.get('redirect'),
                    previous_revision=saved['previous_revision'], revision=saved['revision'])
                def clean(value):
                    if isinstance(value, dict):
                        return {k: clean(v) for k, v in value.items() if not SECRET.search(k)}
                    if isinstance(value, list):
                        return [clean(v) for v in value]
                    return value
                result = clean(result)
                encoded = json.dumps(result)
                if len(encoded.encode()) > 128 * 1024:
                    response = jsonify(success=False, needs_review=True, error='The entry was saved, but its response is too large to confirm automatically. Check the record.'); response.status_code = 409
                else:
                    db.connection().execute(update(RECEIPT).where(RECEIPT.c.request_id == ctx['request_id']).values(state='completed', response_json=encoded))
                    db.commit()
                    response = jsonify(result)
        if get_user() and get_company() and request.endpoint not in ('login', 'logout', 'switch_company', 'select_company', 'static'):
            try:
                _, _, scope = identity(); response.headers['X-Qiyadah-Offline-Scope'] = scope
                if response.mimetype == 'text/html' and response.status_code == 200:
                    info = g.get('offline_page_context') or context()
                    payload = json.dumps(info).replace('<', '\\u003c')
                    script = '<script type="application/json" id="qiyadah-offline-context">' + payload + '</script><script defer src="/static/offline-sync.js"></script>'
                    html = response.get_data(as_text=True)
                    if 'id="qiyadah-offline-context"' not in html:
                        response.set_data(html.replace('</body>', script + '</body>') if '</body>' in html else html + script)
                    if g.get('offline_page_context'):
                        response.headers['X-Qiyadah-Offline-Cache'] = 'page'
            except Exception:
                pass
        response.headers['Cache-Control'] = 'private, no-store'
        return response

"""Flask routes for Qiyadah AI Automation Engine (shared across Qiyadah ERP and Qiyadah eShip)."""
from datetime import date
import hmac
import json
import os
from flask import Blueprint, jsonify, render_template, request, session, redirect, url_for
from .config import Unavailable, encrypt, decrypt, entitled, contact
from .models import (
    Base, CompanySettings, AgentConfig, Conversation, Message,
    AutomationRule, AutomationRun, MessageQueue, ContactConsent,
    KnowledgeSource, Integration, AuditLog, Usage, Appointment, BriefingReport, now,
)
from .permissions import Scope, rows
from .store import settings as get_company_settings, audit, reserve_usage
from .services.llm_service import provider as build_llm_provider
from .services.retrieval_service import upload_document, reindex_document, delete_document
from .services.whatsapp_service import verify_signature
from .agents.customer_agent import (
    capture_lead, lookup_product_catalog, quotation_draft,
    check_calendar_availability, book_appointment, reschedule_appointment,
    cancel_appointment, set_human_takeover, handle_customer_message,
)
from .agents.tracking_agent import handle_tracking_message, queue_shipment_event_notification, extract_awb
from .agents.knowledge_agent import answer as knowledge_answer, record_feedback
from .workflows.followups import (
    ERP_KINDS, ESHIP_KINDS, KINDS, set_consent, process_inbound_consent_keyword,
)
from .workflows.daily_briefing import generate_briefing
from .workers.tasks import (
    approve_queued_message, run_rule_now, process_automation_runs, process_message_queue,
)

_INITIALIZED_BINDS = set()


def _ensure_tables(db_session):
    bind = db_session.get_bind()
    bind_id = id(bind)
    if bind_id not in _INITIALIZED_BINDS:
        Base.metadata.create_all(bind=bind, checkfirst=True)
        _INITIALIZED_BINDS.add(bind_id)


def _resolve_llm_provider(db_session, scope):
    integ = rows(db_session, Integration, scope).filter_by(kind='openai', active=True).first()
    if not integ:
        integ = rows(db_session, Integration, scope).filter_by(kind='self_hosted', active=True).first()
    if not integ:
        return None
    try:
        secrets = decrypt(integ.encrypted_secrets)
        return build_llm_provider(integ.kind, secrets, integ.config or {})
    except Exception:
        return None


def _is_entitled_or_enabled(db_session, scope):
    if entitled(scope.company_id) or (scope.user or {}).get('role') == 'super_admin':
        return True
    row = rows(db_session, CompanySettings, scope).first()
    return bool(row and row.enabled)


def register_ai_automation(
    app,
    db,
    get_current_user,
    get_current_company,
    get_customer_session,
    has_permission=None,
    has_module_access=None,
    application='erp',
    company_lookup=None,
):
    bp = Blueprint(f'ai_automation_{application}', __name__)
    if 'csrf_token' not in app.jinja_env.globals:
        app.jinja_env.globals['csrf_token'] = (
            app.jinja_env.globals.get('assistant_csrf_token')
            or (lambda: session.setdefault('_csrf', os.urandom(16).hex()))
        )

    def make_scope(company_id=None, actor_override=None):
        user = get_current_user() or {}
        if actor_override and not user:
            user = {'email': actor_override, 'role': 'owner', 'user_id': actor_override}
        cid = company_id or get_current_company()
        if user and cid and callable(company_lookup) and not actor_override:
            company = company_lookup(cid)
            if not company or not getattr(company, 'is_active', True):
                raise PermissionError('The selected company is unavailable.')
            if user.get('role') == 'owner':
                if getattr(company, 'owner_email', None) != user.get('email'):
                    raise PermissionError('You are not authorised for this company.')
            elif user.get('role') != 'super_admin':
                from customer_models import CompanyUser
                member = get_customer_session(cid).query(CompanyUser).filter_by(
                    company_id=cid, user_id=user.get('user_id'), email=user.get('email'), is_active=True).first()
                if member is None:
                    raise PermissionError('You are not authorised for this company.')
        return Scope(
            company_id=cid,
            user=user,
            application=application,
            has_permission=has_permission,
            has_module_access=has_module_access or (lambda m: True),
        )

    def scope_factory_for_worker(cid, actor):
        return Scope(
            company_id=cid,
            user={'email': actor, 'role': 'owner', 'user_id': actor},
            application=application,
            has_permission=lambda *a: True,
            has_module_access=has_module_access or (lambda m: True),
        )

    def error_response(exc):
        db.session.rollback()
        if isinstance(exc, PermissionError):
            return jsonify(success=False, error=str(exc)), 403
        if isinstance(exc, Unavailable):
            return jsonify(success=False, error=str(exc)), 503
        if isinstance(exc, ValueError):
            return jsonify(success=False, error=str(exc)), 400
        app.logger.error('AI Automation request failed (%s)', type(exc).__name__)
        return jsonify(success=False, error='AI Automation could not complete this request.'), 500

    @app.before_request
    def enforce_automation_activation():
        endpoints = {
            'api_ai_customer_agent_chat', 'api_ai_customer_agent_lead',
            'api_ai_customer_agent_quotation_draft', 'api_ai_customer_agent_book_appointment',
            'api_ai_automation_tracking_query', 'api_ai_automation_tracking_notify_event',
            'api_ai_automation_run_rule', 'api_ai_automation_run_worker',
            'api_ai_automation_knowledge_ask', 'api_ai_automation_briefing_generate',
        }
        if request.endpoint not in endpoints:
            return
        try:
            scope = make_scope()
            scope.require('view')
            _ensure_tables(db.session)
            cfg = rows(db.session, CompanySettings, scope).first()
            if not cfg or not cfg.enabled:
                raise PermissionError('AI Automation is disabled. Enable it in CRM Setup after platform activation.')
        except Exception as exc:
            return error_response(exc)

    @app.route('/ai-automation', methods=['GET'])
    def ai_automation_workspace():
        user = get_current_user()
        if not user:
            return redirect(url_for('login'))
        cid = get_current_company()
        if not cid:
            return redirect(url_for('select_company'))
        if user.get('role') == 'bi_developer':
            return jsonify(success=False, error='BI Developer accounts can access only the BI Developer workspace.'), 403
        try:
            scope = make_scope(cid)
            scope.require('view')
        except PermissionError as exc:
            return render_template('module_access_denied.html' if application == 'erp' else 'base.html',
                                   module_name='AI Automation', reason=str(exc), error=str(exc)), 403
        if application == 'erp' and 'crm_view' in app.view_functions:
            return redirect(url_for('crm_view', _anchor='automation'))
        if 'settings_whatsapp' in app.view_functions:
            return redirect(url_for('settings_whatsapp'))
        if 'whatsapp_settings' in app.view_functions:
            return redirect(url_for('whatsapp_settings'))
        return jsonify(success=True, company_id=cid, application=application)

    @app.route('/api/ai-automation/state', methods=['GET'])
    def api_ai_automation_state():
        try:
            scope = make_scope()
            scope.require('view')
            _ensure_tables(db.session)
            cfg = get_company_settings(db.session, scope)
            db.session.commit()

            agent_rows = rows(db.session, AgentConfig, scope).all()
            agent_map = {a.agent: {'id': a.id, 'agent': a.agent, 'enabled': a.enabled, 'config': a.config or {}} for a in agent_rows}
            default_agents = ('tracking', 'followup', 'knowledge', 'briefing') if application == 'eship' else ('customer', 'tracking', 'followup', 'knowledge', 'briefing')
            for ag in default_agents:
                agent_map.setdefault(ag, {'id': None, 'agent': ag, 'enabled': False, 'config': {}})

            rules_list = [
                {
                    'id': r.id,
                    'name': r.name,
                    'kind': r.kind,
                    'enabled': r.enabled,
                    'approval_required': r.approval_required,
                    'config': r.config or {},
                }
                for r in rows(db.session, AutomationRule, scope).order_by(AutomationRule.id.desc()).all()
            ]
            runs_list = [
                {
                    'id': r.id,
                    'kind': r.kind,
                    'status': r.status,
                    'attempts': r.attempts,
                    'last_error': r.last_error,
                    'result': r.result or {},
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows(db.session, AutomationRun, scope).order_by(AutomationRun.id.desc()).limit(30).all()
            ]
            queue_list = [
                {
                    'id': q.id,
                    'channel': q.channel,
                    'recipient': q.recipient,
                    'kind': q.kind,
                    'reference': q.reference,
                    'template': q.template,
                    'status': q.status,
                    'attempts': q.attempts,
                    'provider_id': q.provider_id,
                    'last_error': q.last_error,
                    'payload': q.payload or {},
                    'created_at': q.created_at.isoformat() if q.created_at else None,
                }
                for q in rows(db.session, MessageQueue, scope).order_by(MessageQueue.id.desc()).limit(40).all()
            ]
            convs_list = []
            for c in rows(db.session, Conversation, scope).order_by(Conversation.id.desc()).limit(30).all():
                msg_count = rows(db.session, Message, scope).filter_by(conversation_id=c.id).count()
                last_msg = rows(db.session, Message, scope).filter_by(conversation_id=c.id).order_by(Message.id.desc()).first()
                convs_list.append({
                    'id': c.id,
                    'agent': c.agent,
                    'channel': c.channel,
                    'external_ref': c.external_ref,
                    'crm_lead_id': c.crm_lead_id,
                    'human_takeover': c.human_takeover,
                    'status': c.status,
                    'message_count': msg_count,
                    'last_message': last_msg.content[:140] if last_msg else '',
                    'created_at': c.created_at.isoformat() if c.created_at else None,
                })

            ks_query = db.session.query(KnowledgeSource).filter(
                KnowledgeSource.company_id.in_((scope.company_id, '__global__')),
                KnowledgeSource.application.in_((application, 'global')),
            ).order_by(KnowledgeSource.id.desc()).all()
            knowledge_list = [
                {
                    'id': k.id,
                    'company_id': k.company_id,
                    'title': k.title,
                    'application': k.application,
                    'audience': k.audience,
                    'filename': k.filename,
                    'chunk_count': len(k.chunks or []),
                    'active': k.active,
                    'updated_at': k.updated_at.isoformat() if k.updated_at else None,
                }
                for k in ks_query
            ]

            integrations_list = [
                {
                    'id': i.id,
                    'kind': i.kind,
                    'active': i.active,
                    'config': i.config or {},
                    'has_secrets': bool(i.encrypted_secrets),
                }
                for i in rows(db.session, Integration, scope).all()
            ]
            consents_list = [
                {
                    'id': c.id,
                    'channel': c.channel,
                    'contact': c.contact,
                    'allowed': c.allowed,
                    'source': c.source,
                    'updated_at': c.updated_at.isoformat() if c.updated_at else None,
                }
                for c in rows(db.session, ContactConsent, scope).order_by(ContactConsent.id.desc()).limit(50).all()
            ]
            briefings_list = [
                {
                    'id': b.id,
                    'app_type': b.app_type,
                    'period_type': b.period_type,
                    'period_start': b.period_start,
                    'period_end': b.period_end,
                    'timezone': b.timezone,
                    'metrics': b.metrics or {},
                    'explanation': b.explanation,
                    'sources': (b.sources or {}).get('sources', []),
                    'channels': b.channels or [],
                    'delivery_log': b.delivery_log or {},
                    'created_at': b.created_at.isoformat() if b.created_at else None,
                }
                for b in rows(db.session, BriefingReport, scope).order_by(BriefingReport.id.desc()).limit(15).all()
            ]
            usage_rows = rows(db.session, Usage, scope).order_by(Usage.id.desc()).limit(30).all()
            usage_list = [
                {
                    'bucket': u.bucket,
                    'kind': u.kind,
                    'count': u.count,
                    'input_tokens': u.input_tokens,
                    'output_tokens': u.output_tokens,
                    'estimated_cost': str(u.estimated_cost or 0),
                }
                for u in usage_rows
            ]
            audit_list = [
                {
                    'id': a.id,
                    'actor': a.actor,
                    'action': a.action,
                    'reference': a.reference,
                    'details': a.details or {},
                    'created_at': a.created_at.isoformat() if a.created_at else None,
                }
                for a in rows(db.session, AuditLog, scope).order_by(AuditLog.id.desc()).limit(30).all()
            ]
            return jsonify(
                success=True,
                application=application,
                company_id=scope.company_id,
                entitled=_is_entitled_or_enabled(db.session, scope),
                settings={
                    'enabled': cfg.enabled,
                    'app_type': cfg.app_type,
                    'plan_code': cfg.plan_code,
                    'daily_limit': cfg.daily_limit,
                    'monthly_limit': cfg.monthly_limit,
                    'timezone': cfg.timezone,
                    'work_start': cfg.work_start,
                    'work_end': cfg.work_end,
                },
                agents=list(agent_map.values()),
                rules=rules_list,
                runs=runs_list,
                queue=queue_list,
                conversations=convs_list,
                knowledge_sources=knowledge_list,
                integrations=integrations_list,
                consents=consents_list,
                briefings=briefings_list,
                usage=usage_list,
                audit_logs=audit_list,
            )
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/settings', methods=['POST'])
    def api_ai_automation_update_settings():
        try:
            scope = make_scope()
            scope.require('edit', owner=True)
            _ensure_tables(db.session)
            data = request.get_json(silent=True) or {}
            cfg = get_company_settings(db.session, scope)
            if 'enabled' in data:
                want_enabled = bool(data['enabled'])
                if want_enabled and not (scope.owner or entitled(scope.company_id) or (scope.user or {}).get('role') == 'super_admin' or cfg.enabled):
                    raise PermissionError('Company is not entitled to enable AI Automation. Add company_id to AI_AUTOMATION_COMPANIES or enable via Super Admin.')
                cfg.enabled = want_enabled
            if 'timezone' in data and str(data['timezone']).strip():
                from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
                try:
                    ZoneInfo(str(data['timezone']).strip())
                except (ZoneInfoNotFoundError, ValueError):
                    raise ValueError('Choose a valid timezone, such as Asia/Kolkata.') from None
                cfg.timezone = str(data['timezone']).strip()[:50]
            if 'work_start' in data:
                ws = int(data['work_start'])
                if not 0 <= ws <= 23:
                    raise ValueError('work_start must be between 0 and 23.')
                cfg.work_start = ws
            if 'work_end' in data:
                we = int(data['work_end'])
                if not 0 <= we <= 23:
                    raise ValueError('work_end must be between 0 and 23.')
                cfg.work_end = we
            if 'daily_limit' in data:
                dl = int(data['daily_limit'])
                if dl < 1 or dl > 100000:
                    raise ValueError('daily_limit must be between 1 and 100,000.')
                cfg.daily_limit = dl
            if 'monthly_limit' in data:
                ml = int(data['monthly_limit'])
                if ml < 1 or ml > 1000000:
                    raise ValueError('monthly_limit must be between 1 and 1,000,000.')
                cfg.monthly_limit = ml
            if 'plan_code' in data and str(data['plan_code']).strip():
                cfg.plan_code = str(data['plan_code']).strip()[:40]
            cfg.app_type = application
            audit(db.session, scope, 'settings.updated', scope.company_id, enabled=cfg.enabled, timezone=cfg.timezone)
            db.session.commit()
            return jsonify(success=True, settings={
                'enabled': cfg.enabled,
                'timezone': cfg.timezone,
                'work_start': cfg.work_start,
                'work_end': cfg.work_end,
                'daily_limit': cfg.daily_limit,
                'monthly_limit': cfg.monthly_limit,
                'plan_code': cfg.plan_code,
            })
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/agents', methods=['POST'])
    def api_ai_automation_update_agent():
        try:
            scope = make_scope()
            scope.require('edit', owner=True)
            _ensure_tables(db.session)
            data = request.get_json(silent=True) or {}
            agent_name = str(data.get('agent', '')).strip().lower()
            allowed_agents = ('tracking', 'followup', 'knowledge', 'briefing') if application == 'eship' else ('customer', 'tracking', 'followup', 'knowledge', 'briefing')
            if agent_name not in allowed_agents:
                raise ValueError(f"Unsupported agent '{agent_name}' for {application}.")
            row = rows(db.session, AgentConfig, scope).filter_by(agent=agent_name).first()
            if not row:
                row = AgentConfig(company_id=scope.company_id, agent=agent_name, enabled=bool(data.get('enabled', False)), config=data.get('config') or {})
                db.session.add(row)
            else:
                if 'enabled' in data:
                    row.enabled = bool(data['enabled'])
                if isinstance(data.get('config'), dict):
                    row.config = data['config']
            audit(db.session, scope, 'agent.updated', agent_name, enabled=row.enabled)
            db.session.commit()
            return jsonify(success=True, agent={'agent': row.agent, 'enabled': row.enabled, 'config': row.config})
        except Exception as exc:
            return error_response(exc)

    # ── PHASE 2: CUSTOMER AGENT ENDPOINTS ──────────────────────────────────
    @app.route('/api/ai-automation/customer-agent/chat', methods=['POST'])
    def api_ai_customer_agent_chat():
        try:
            if application == 'eship':
                raise PermissionError('CRM Customer Agent is available only in Qiyadah ERP.')
            scope = make_scope()
            scope.require('view')
            _ensure_tables(db.session)
            cfg = get_company_settings(db.session, scope)
            reserve_usage(db.session, scope, 'customer_chat', int(cfg.daily_limit or 100))
            data = request.get_json(silent=True) or {}
            cdb = get_customer_session(scope.company_id)
            llm = _resolve_llm_provider(db.session, scope)
            res = handle_customer_message(
                db.session,
                cdb,
                scope,
                message_text=data.get('message', ''),
                channel=data.get('channel', 'web'),
                external_ref=data.get('external_ref'),
                contact_info=data.get('contact_info'),
                conversation_id=data.get('conversation_id'),
                provider=llm,
            )
            return jsonify(success=True, **res)
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/customer-agent/lead', methods=['POST'])
    def api_ai_customer_agent_lead():
        try:
            if application == 'eship':
                raise PermissionError('CRM Lead capture is available only in Qiyadah ERP.')
            scope = make_scope()
            scope.require('create', module='crm', owner=True)
            _ensure_tables(db.session)
            data = request.get_json(silent=True) or {}
            cdb = get_customer_session(scope.company_id)
            req_key = data.get('request_key') or f"{data.get('phone', '')}:{data.get('email', '')}:{data.get('inquiry', '')[:40]}"
            res = capture_lead(cdb, scope, data, request_key=req_key)
            audit(db.session, scope, 'lead.captured', res['lead_id'])
            db.session.commit()
            return jsonify(success=True, **res)
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/customer-agent/quotation-draft', methods=['POST'])
    def api_ai_customer_agent_quotation_draft():
        try:
            if application == 'eship':
                raise PermissionError('CRM Quotation Draft is available only in Qiyadah ERP.')
            scope = make_scope()
            scope.require('create', module='crm', owner=True)
            _ensure_tables(db.session)
            data = request.get_json(silent=True) or {}
            cdb = get_customer_session(scope.company_id)
            res = quotation_draft(cdb, scope, data.get('lead_id', ''), data.get('item_ids', []))
            audit(db.session, scope, 'quotation.drafted', res['lead_id'], item_count=len(res['items']))
            db.session.commit()
            return jsonify(success=True, draft=res)
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/customer-agent/appointments', methods=['POST'])
    def api_ai_customer_agent_book_appointment():
        try:
            if application == 'eship':
                raise PermissionError('CRM Appointments are available only in Qiyadah ERP.')
            scope = make_scope()
            scope.require('create', module='crm', owner=True)
            _ensure_tables(db.session)
            data = request.get_json(silent=True) or {}
            cdb = get_customer_session(scope.company_id)
            res = book_appointment(
                db.session,
                cdb,
                scope,
                lead_id=data.get('lead_id', ''),
                start_iso=data.get('start', ''),
                end_iso=data.get('end', ''),
                title=data.get('title', 'Customer Consultation'),
                request_key=data.get('request_key'),
            )
            return jsonify(success=True, **res)
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/customer-agent/appointments/<appointment_id>/reschedule', methods=['POST'])
    def api_ai_customer_agent_reschedule_appointment(appointment_id):
        try:
            scope = make_scope()
            scope.require('edit', module='crm', owner=True)
            _ensure_tables(db.session)
            data = request.get_json(silent=True) or {}
            cdb = get_customer_session(scope.company_id)
            res = reschedule_appointment(db.session, cdb, scope, appointment_id, data.get('start', ''), data.get('end', ''))
            return jsonify(success=True, **res)
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/customer-agent/appointments/<appointment_id>/cancel', methods=['POST'])
    def api_ai_customer_agent_cancel_appointment(appointment_id):
        try:
            scope = make_scope()
            scope.require('edit', module='crm', owner=True)
            _ensure_tables(db.session)
            cdb = get_customer_session(scope.company_id)
            res = cancel_appointment(db.session, cdb, scope, appointment_id)
            return jsonify(success=True, **res)
        except Exception as exc:
            return error_response(exc)

    # ── CONVERSATIONS & HUMAN TAKEOVER ─────────────────────────────────────
    @app.route('/api/ai-automation/conversations/<conversation_id>', methods=['GET'])
    def api_ai_automation_conversation_detail(conversation_id):
        try:
            scope = make_scope()
            scope.require('view')
            _ensure_tables(db.session)
            conv = rows(db.session, Conversation, scope).filter_by(id=str(conversation_id)).first()
            if not conv:
                return jsonify(success=False, error='Conversation not found.'), 404
            msgs = [
                {
                    'id': m.id,
                    'role': m.role,
                    'content': m.content,
                    'feedback': m.feedback,
                    'sources': m.sources or [],
                    'created_at': m.created_at.isoformat() if m.created_at else None,
                }
                for m in rows(db.session, Message, scope).filter_by(conversation_id=conv.id).order_by(Message.id.asc()).all()
            ]
            return jsonify(
                success=True,
                conversation={
                    'id': conv.id,
                    'agent': conv.agent,
                    'channel': conv.channel,
                    'external_ref': conv.external_ref,
                    'crm_lead_id': conv.crm_lead_id,
                    'human_takeover': conv.human_takeover,
                    'status': conv.status,
                },
                messages=msgs,
            )
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/conversations/<conversation_id>/takeover', methods=['POST'])
    def api_ai_automation_conversation_takeover(conversation_id):
        try:
            scope = make_scope()
            scope.require('edit')
            _ensure_tables(db.session)
            data = request.get_json(silent=True) or {}
            res = set_human_takeover(
                db.session,
                scope,
                conversation_id,
                takeover=bool(data.get('human_takeover', True)),
                reason=data.get('reason'),
            )
            return jsonify(success=True, **res)
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/conversations/<conversation_id>/reply', methods=['POST'])
    def api_ai_automation_conversation_human_reply(conversation_id):
        try:
            scope = make_scope()
            scope.require('edit')
            _ensure_tables(db.session)
            conv = rows(db.session, Conversation, scope).filter_by(id=str(conversation_id)).first()
            if not conv:
                return jsonify(success=False, error='Conversation not found.'), 404
            data = request.get_json(silent=True) or {}
            text = str(data.get('message', '')).strip()
            if not 1 <= len(text) <= 4000:
                raise ValueError('Enter a reply between 1 and 4,000 characters.')
            msg = Message(company_id=scope.company_id, conversation_id=conv.id, role='human_agent', content=text, sources=[{'actor': scope.actor}])
            db.session.add(msg)
            audit(db.session, scope, 'conversation.human_reply', conv.id)
            db.session.commit()
            return jsonify(success=True, message_id=msg.id)
        except Exception as exc:
            return error_response(exc)

    # ── PHASE 3: ESHIP TRACKING AGENT ENDPOINTS ────────────────────────────
    @app.route('/api/ai-automation/tracking/query', methods=['POST'])
    def api_ai_automation_tracking_query():
        try:
            scope = make_scope()
            scope.require('view')
            _ensure_tables(db.session)
            cfg = get_company_settings(db.session, scope)
            reserve_usage(db.session, scope, 'tracking_query', int(cfg.daily_limit or 100))
            data = request.get_json(silent=True) or {}
            msg_text = data.get('message', '')
            sender = data.get('sender')
            if application == 'eship':
                cdb = get_customer_session(scope.company_id)
                res = handle_tracking_message(
                    db.session,
                    scope,
                    msg_text,
                    sender=sender,
                    cdb=cdb,
                    channel=data.get('channel', 'web'),
                    staff_authorized=not bool(sender),
                )
            else:
                integ = rows(db.session, Integration, scope).filter_by(kind='eship_bridge', active=True).first()
                b_cfg = dict((integ.config if integ else {}) or {}, company_id=scope.company_id)
                b_sec = decrypt(integ.encrypted_secrets) if integ and integ.encrypted_secrets else {'shared_secret': os.environ.get('AI_ESHIP_SHARED_SECRET', '')}
                res = handle_tracking_message(
                    db.session,
                    scope,
                    msg_text,
                    sender=sender,
                    channel=data.get('channel', 'web'),
                    config=b_cfg if b_sec.get('shared_secret') else None,
                    secrets=b_sec if b_sec.get('shared_secret') else None,
                )
            return jsonify(success=True, **res)
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/tracking/notify-event', methods=['POST'])
    def api_ai_automation_tracking_notify_event():
        try:
            scope = make_scope()
            scope.require('edit', owner=True)
            _ensure_tables(db.session)
            data = request.get_json(silent=True) or {}
            queued = queue_shipment_event_notification(
                db.session,
                scope,
                awb=data.get('awb', ''),
                new_status=data.get('new_status', ''),
                old_status=data.get('old_status', ''),
                recipient=data.get('recipient', ''),
                channel=data.get('channel', 'whatsapp'),
                template=data.get('template'),
                destination=data.get('destination'),
                approval=bool(data.get('approval_required', False)),
            )
            db.session.commit()
            return jsonify(success=True, queued=bool(queued), message_id=queued.id if queued else None)
        except Exception as exc:
            return error_response(exc)

    # ── PHASE 4: AUTOMATION RULES, QUEUE, CONSENTS & WORKER ────────────────
    @app.route('/api/ai-automation/rules', methods=['POST'])
    def api_ai_automation_save_rule():
        try:
            scope = make_scope()
            scope.require('create', owner=True)
            _ensure_tables(db.session)
            data = request.get_json(silent=True) or {}
            name = str(data.get('name', '')).strip()
            kind = str(data.get('kind', '')).strip()
            allowed_kinds = ESHIP_KINDS if application == 'eship' else ERP_KINDS
            if not 1 <= len(name) <= 120:
                raise ValueError('Provide a rule name up to 120 characters.')
            if kind not in allowed_kinds:
                raise ValueError(f"Rule kind '{kind}' is not valid for {application}.")
            rule_cfg = data.get('config') if isinstance(data.get('config'), dict) else {}
            delay_days = int(rule_cfg.get('delay_days', data.get('delay_days', 2)))
            if delay_days < 0 or delay_days > 365:
                raise ValueError('delay_days must be between 0 and 365.')
            channel = str(rule_cfg.get('channel', data.get('channel', 'email'))).strip().lower()
            if channel not in ('email', 'whatsapp'):
                raise ValueError('channel must be email or whatsapp.')
            template = str(rule_cfg.get('template', data.get('template', '')) or '').strip() or None
            if channel == 'whatsapp' and kind != 'daily_briefing' and not template:
                raise ValueError('WhatsApp business-initiated automation rules require an approved template name.')
            rule_cfg.update({'delay_days': delay_days, 'channel': channel, 'template': template})

            rule_id = data.get('id')
            if rule_id:
                rule = rows(db.session, AutomationRule, scope).filter_by(id=str(rule_id)).first()
                if not rule:
                    return jsonify(success=False, error='Rule not found.'), 404
                rule.name = name
                rule.kind = kind
                rule.enabled = bool(data.get('enabled', True))
                rule.approval_required = bool(data.get('approval_required', True))
                rule.config = rule_cfg
            else:
                rule = AutomationRule(
                    company_id=scope.company_id,
                    name=name,
                    kind=kind,
                    enabled=bool(data.get('enabled', True)),
                    approval_required=bool(data.get('approval_required', True)),
                    config=rule_cfg,
                )
                db.session.add(rule)
                db.session.flush()
            audit(db.session, scope, 'rule.saved', rule.id, name=rule.name, kind=rule.kind)
            db.session.commit()
            return jsonify(success=True, rule={'id': rule.id, 'name': rule.name, 'kind': rule.kind, 'enabled': rule.enabled, 'approval_required': rule.approval_required, 'config': rule.config})
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/rules/<rule_id>/toggle', methods=['POST'])
    def api_ai_automation_toggle_rule(rule_id):
        try:
            scope = make_scope()
            scope.require('edit', owner=True)
            _ensure_tables(db.session)
            rule = rows(db.session, AutomationRule, scope).filter_by(id=str(rule_id)).first()
            if not rule:
                return jsonify(success=False, error='Rule not found.'), 404
            data = request.get_json(silent=True) or {}
            rule.enabled = bool(data.get('enabled', not rule.enabled))
            audit(db.session, scope, 'rule.toggled', rule.id, enabled=rule.enabled)
            db.session.commit()
            return jsonify(success=True, id=rule.id, enabled=rule.enabled)
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/rules/<rule_id>', methods=['DELETE'])
    def api_ai_automation_delete_rule(rule_id):
        try:
            scope = make_scope()
            scope.require('delete', owner=True)
            _ensure_tables(db.session)
            rule = rows(db.session, AutomationRule, scope).filter_by(id=str(rule_id)).first()
            if not rule:
                return jsonify(success=False, error='Rule not found.'), 404
            db.session.delete(rule)
            audit(db.session, scope, 'rule.deleted', rule_id)
            db.session.commit()
            return jsonify(success=True, deleted=rule_id)
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/rules/<rule_id>/run', methods=['POST'])
    def api_ai_automation_run_rule(rule_id):
        try:
            scope = make_scope()
            scope.require('edit', owner=True)
            _ensure_tables(db.session)
            cdb = get_customer_session(scope.company_id)
            run = run_rule_now(db.session, cdb, scope, rule_id)
            return jsonify(success=True, run={'id': run.id, 'status': run.status, 'result': run.result})
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/queue/<message_id>/approve', methods=['POST'])
    def api_ai_automation_approve_message(message_id):
        try:
            scope = make_scope()
            scope.require('edit', owner=True)
            _ensure_tables(db.session)
            msg = approve_queued_message(db.session, scope, message_id)
            return jsonify(success=True, id=msg.id, status=msg.status)
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/worker/run', methods=['POST'])
    def api_ai_automation_run_worker():
        try:
            scope = make_scope()
            scope.require('edit', owner=True)
            _ensure_tables(db.session)
            def current_scope(cid, actor):
                if cid != scope.company_id:
                    raise PermissionError('This queue belongs to another company.')
                return scope
            runs = process_automation_runs(db.session, get_customer_session, current_scope,
                                           company_id=scope.company_id)
            msgs = process_message_queue(
                db.session,
                get_customer_session,
                current_scope,
                company_id=scope.company_id,
                respect_working_hours=True,
                company_lookup=company_lookup,
            )
            return jsonify(
                success=True,
                processed_runs=len(runs),
                processed_messages=len(msgs),
            )
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/consents', methods=['POST'])
    def api_ai_automation_save_consent():
        try:
            scope = make_scope()
            scope.require('edit')
            _ensure_tables(db.session)
            data = request.get_json(silent=True) or {}
            row = set_consent(
                db.session,
                scope,
                channel=str(data.get('channel', 'whatsapp')).strip().lower(),
                recipient=data.get('contact', ''),
                allowed=bool(data.get('allowed', True)),
                source=data.get('source', 'admin'),
            )
            return jsonify(success=True, consent={'id': row.id, 'channel': row.channel, 'contact': row.contact, 'allowed': row.allowed})
        except Exception as exc:
            return error_response(exc)

    # ── PHASE 5: AI KNOWLEDGE ASSISTANT ENDPOINTS ──────────────────────────
    @app.route('/api/ai-automation/knowledge/upload', methods=['POST'])
    def api_ai_automation_knowledge_upload():
        try:
            scope = make_scope()
            scope.require('create')
            _ensure_tables(db.session)
            if 'file' in request.files and request.files['file'].filename:
                f = request.files['file']
                filename = f.filename
                raw_bytes = f.read()
                title = request.form.get('title') or filename
                audience = request.form.get('audience', 'staff')
                app_scope = request.form.get('application', application)
                global_doc = request.form.get('global_doc') in ('1', 'true', 'True')
            else:
                data = request.get_json(silent=True) or {}
                title = data.get('title', '')
                filename = data.get('filename', 'document.txt')
                raw_bytes = str(data.get('content', '')).encode('utf-8')
                audience = data.get('audience', 'staff')
                app_scope = data.get('application', application)
                global_doc = bool(data.get('global_doc', False))
            src = upload_document(
                db.session,
                scope,
                title=title,
                filename=filename,
                data=raw_bytes,
                application=app_scope,
                audience=audience,
                global_doc=global_doc,
            )
            return jsonify(success=True, source={'id': src.id, 'title': src.title, 'application': src.application, 'audience': src.audience, 'chunk_count': len(src.chunks or [])})
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/knowledge/<source_id>/reindex', methods=['POST'])
    def api_ai_automation_knowledge_reindex(source_id):
        try:
            scope = make_scope()
            scope.require('edit')
            _ensure_tables(db.session)
            src = reindex_document(db.session, scope, source_id)
            return jsonify(success=True, id=src.id, chunk_count=len(src.chunks or []))
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/knowledge/<source_id>', methods=['DELETE'])
    def api_ai_automation_knowledge_delete(source_id):
        try:
            scope = make_scope()
            scope.require('delete')
            _ensure_tables(db.session)
            res = delete_document(db.session, scope, source_id)
            return jsonify(success=True, **res)
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/knowledge/ask', methods=['POST'])
    def api_ai_automation_knowledge_ask():
        try:
            scope = make_scope()
            scope.require('view')
            _ensure_tables(db.session)
            cfg = get_company_settings(db.session, scope)
            reserve_usage(db.session, scope, 'knowledge_query', int(cfg.daily_limit or 100))
            data = request.get_json(silent=True) or {}
            llm = _resolve_llm_provider(db.session, scope)
            res = knowledge_answer(
                db.session,
                scope,
                question=data.get('question', ''),
                provider=llm,
                audience=data.get('audience', 'staff'),
                conversation_id=data.get('conversation_id'),
            )
            db.session.commit()
            return jsonify(success=True, **res)
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/knowledge/feedback', methods=['POST'])
    def api_ai_automation_knowledge_feedback():
        try:
            scope = make_scope()
            scope.require('view')
            _ensure_tables(db.session)
            data = request.get_json(silent=True) or {}
            res = record_feedback(db.session, scope, data.get('message_id'), data.get('feedback'))
            return jsonify(success=True, **res)
        except Exception as exc:
            return error_response(exc)

    # ── PHASE 6: AI DAILY BUSINESS BRIEFING ENDPOINTS ──────────────────────
    @app.route('/api/ai-automation/briefings/generate', methods=['POST'])
    def api_ai_automation_briefing_generate():
        try:
            scope = make_scope()
            scope.require('view', owner=True)
            _ensure_tables(db.session)
            cfg = get_company_settings(db.session, scope)
            reserve_usage(db.session, scope, 'briefing', int(cfg.daily_limit or 100))
            data = request.get_json(silent=True) or {}
            cdb = get_customer_session(scope.company_id)
            llm = _resolve_llm_provider(db.session, scope)
            comp = company_lookup(scope.company_id) if callable(company_lookup) else None
            default_currency = getattr(comp, 'base_currency', None) or getattr(comp, 'currency', None) or 'INR'
            res = generate_briefing(
                db.session,
                cdb,
                scope,
                period_type=data.get('period_type', 'daily'),
                start=data.get('start'),
                end=data.get('end'),
                currency=data.get('currency') or default_currency,
                categories=data.get('categories'),
                channels=data.get('channels', ['dashboard']),
                recipients=data.get('recipients', {}),
                provider=llm,
                template=data.get('template'),
            )
            return jsonify(success=True, briefing=res)
        except Exception as exc:
            return error_response(exc)

    # ── PHASE 7: INTEGRATIONS & WHATSAPP WEBHOOK ───────────────────────────
    @app.route('/api/ai-automation/integrations', methods=['POST'])
    def api_ai_automation_save_integration():
        try:
            scope = make_scope()
            scope.require('edit', owner=True)
            _ensure_tables(db.session)
            data = request.get_json(silent=True) or {}
            kind = str(data.get('kind', '')).strip().lower()
            if kind not in ('openai', 'self_hosted', 'whatsapp', 'email', 'google_calendar', 'eship_bridge'):
                raise ValueError('Unsupported integration kind.')
            row = rows(db.session, Integration, scope).filter_by(kind=kind).first()
            secrets_dict = data.get('secrets') if isinstance(data.get('secrets'), dict) else {}
            clean_secrets = {k: v for k, v in secrets_dict.items() if v is not None and str(v).strip() != ''}
            if not row:
                row = Integration(
                    company_id=scope.company_id,
                    kind=kind,
                    active=bool(data.get('active', True)),
                    config=data.get('config') if isinstance(data.get('config'), dict) else {},
                    encrypted_secrets=encrypt(clean_secrets) if clean_secrets else None,
                )
                db.session.add(row)
            else:
                if 'active' in data:
                    row.active = bool(data['active'])
                if isinstance(data.get('config'), dict):
                    row.config = data['config']
                if clean_secrets:
                    existing_sec = decrypt(row.encrypted_secrets) if row.encrypted_secrets else {}
                    existing_sec.update(clean_secrets)
                    row.encrypted_secrets = encrypt(existing_sec)
            audit(db.session, scope, 'integration.saved', kind, active=row.active)
            db.session.commit()
            return jsonify(success=True, integration={'kind': row.kind, 'active': row.active, 'config': row.config, 'has_secrets': bool(row.encrypted_secrets)})
        except Exception as exc:
            return error_response(exc)

    @app.route('/api/ai-automation/webhook/whatsapp', methods=['GET', 'POST'])
    def api_ai_automation_whatsapp_webhook():
        _ensure_tables(db.session)
        if request.method == 'GET':
            mode = request.args.get('hub.mode')
            token = request.args.get('hub.verify_token', '')
            challenge = request.args.get('hub.challenge', '')
            expected_token = os.environ.get('AI_WHATSAPP_VERIFY_TOKEN', '')
            if mode == 'subscribe' and expected_token and hmac.compare_digest(token, expected_token):
                return challenge, 200, {'Content-Type': 'text/plain'}
            return jsonify(error='Verification failed'), 403

        raw = request.get_data()
        signature = request.headers.get('X-Hub-Signature-256', '')
        payload = request.get_json(silent=True) or {}
        cid = str(request.args.get('company_id') or payload.get('company_id') or '').strip()

        app_secret = os.environ.get('AI_WHATSAPP_APP_SECRET', '')
        if cid:
            integ = db.session.query(Integration).filter_by(company_id=cid, kind='whatsapp', active=True).first()
            if integ and integ.encrypted_secrets:
                try:
                    sec = decrypt(integ.encrypted_secrets)
                    app_secret = sec.get('app_secret') or app_secret
                except Exception:
                    pass
        if not verify_signature(raw, signature, app_secret):
            return jsonify(error='Invalid webhook signature'), 403

        processed_statuses = 0
        processed_messages = 0
        replies = []

        for entry in payload.get('entry', []):
            for change in entry.get('changes', []):
                val = change.get('value', {})
                meta_phone_id = str((val.get('metadata') or {}).get('phone_number_id') or '')
                resolved_cid = cid
                if not resolved_cid and meta_phone_id:
                    for i_row in db.session.query(Integration).filter_by(kind='whatsapp', active=True).all():
                        if str((i_row.config or {}).get('phone_number_id') or '') == meta_phone_id:
                            resolved_cid = i_row.company_id
                            break
                if not resolved_cid:
                    continue

                for st in val.get('statuses', []):
                    wamid = st.get('id')
                    st_val = st.get('status')
                    if wamid and st_val:
                        q_row = db.session.query(MessageQueue).filter_by(company_id=resolved_cid, provider_id=wamid).first()
                        if q_row:
                            q_row.status = f"provider_{st_val}"
                            processed_statuses += 1

                for msg in val.get('messages', []):
                    sender = msg.get('from', '')
                    text = ((msg.get('text') or {}).get('body') or '').strip()
                    if not sender or not text:
                        continue
                    scope = scope_factory_for_worker(resolved_cid, 'whatsapp-webhook')
                    consent_action = process_inbound_consent_keyword(db.session, scope, 'whatsapp', sender, text)
                    if consent_action:
                        processed_messages += 1
                        replies.append({'to': sender, 'consent_action': consent_action})
                        continue
                    cdb = get_customer_session(resolved_cid)
                    if application == 'eship' or extract_awb(text):
                        res = handle_tracking_message(
                            db.session,
                            scope,
                            text,
                            sender=sender,
                            cdb=cdb if application == 'eship' else None,
                            channel='whatsapp',
                        )
                        replies.append({'to': sender, 'reply': res['reply']})
                    else:
                        res = handle_customer_message(
                            db.session,
                            cdb,
                            scope,
                            message_text=text,
                            channel='whatsapp',
                            external_ref=sender,
                        )
                        replies.append({'to': sender, 'reply': res['reply']})
                    processed_messages += 1

        db.session.commit()
        return jsonify(success=True, processed_statuses=processed_statuses, processed_messages=processed_messages, replies=replies)

    api_ai_automation_whatsapp_webhook._csrf_exempt = True

    @app.route('/api/customer/ai-tracking', methods=['GET', 'POST'])
    def api_customer_portal_ai_tracking():
        cust = session.get('customer_user')
        if not cust or not cust.get('company_id') or not cust.get('client_pk'):
            return jsonify(error='Not authorised'), 401
        try:
            _ensure_tables(db.session)
            cid = str(cust['company_id'])
            client_pk = int(cust['client_pk'])
            cdb = get_customer_session(cid)
            if request.method == 'GET':
                text = str(request.args.get('q') or request.args.get('awb') or '').strip()
                language = request.args.get('language')
            else:
                data = request.get_json(silent=True) or {}
                text = str(data.get('message') or data.get('awb') or '').strip()
                language = data.get('language')
            if not text:
                return jsonify(error='Please enter an AWB number or tracking question.'), 400
            portal_scope = Scope(
                company_id=cid,
                user={'email': cust.get('email') or cust.get('client_id') or f'client-{client_pk}', 'role': 'owner', 'user_id': f'portal-{client_pk}'},
                application='eship',
                has_permission=lambda *a: True,
                has_module_access=lambda *a: True,
            )
            res = handle_tracking_message(
                db.session,
                portal_scope,
                text,
                sender=cust.get('phone') or cust.get('client_id'),
                client_id=client_pk,
                cdb=cdb,
                channel='customer_portal',
            )
            db.session.commit()
            return jsonify(success=True, **res)
        except Exception as exc:
            return error_response(exc)

    return bp

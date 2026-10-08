"""Additional CRM workspace screens; all records are scoped to the active company."""
import csv
import io
import json
import uuid
from datetime import date
from urllib.parse import urlparse
from flask import request, jsonify, Response
from customer_models import Client, CRMContact, CRMLead, CRMInteraction, CRMProject, CRMSetting


def register_crm_workspace(app, login_required, get_cdb, get_current_company, get_current_user):
    def owner():
        return (get_current_user() or {}).get('role') in ('owner', 'super_admin')

    def company_rows(model):
        return get_cdb().query(model).filter_by(company_id=get_current_company())

    @app.route('/api/crm/workspace/metrics')
    @login_required
    def crm_workspace_metrics():
        today = date.today()
        activities = company_rows(CRMInteraction).all()
        pending = [a for a in activities if a.status != 'completed' and not a.follow_up_done]
        return jsonify(success=True, accounts=company_rows(Client).filter(Client.status != 'Deleted').count(),
            contacts=company_rows(CRMContact).count(),
            open_deals=company_rows(CRMLead).filter(CRMLead.stage.in_(['Qualified', 'Proposal Sent'])).count(),
            active_projects=company_rows(CRMProject).filter(CRMProject.status.in_(['Planned', 'In Progress', 'On Hold'])).count(),
            open_tasks=sum(a.type == 'task' for a in pending),
            scheduled_calls=sum(a.type == 'call' for a in pending),
            scheduled_meetings=sum(a.type == 'meeting' for a in pending),
            overdue=sum(bool((a.due_date or a.follow_up_date) and (a.due_date or a.follow_up_date) < today) for a in pending))

    @app.route('/api/crm/projects', methods=['GET', 'POST'])
    @app.route('/api/crm/projects/<project_id>', methods=['PUT'])
    @login_required
    def crm_projects(project_id=None):
        if request.method == 'GET':
            rows = company_rows(CRMProject).order_by(CRMProject.created_at.desc()).all()
            return jsonify(success=True, projects=[p.to_dict() for p in rows])
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='Provide project details'), 400
        name = str(data.get('name') or '').strip()
        status = data.get('status', 'Planned')
        if not name or len(name) > 200:
            return jsonify(error='Project name is required (maximum 200 characters)'), 400
        if status not in ('Planned', 'In Progress', 'On Hold', 'Completed', 'Archived'):
            return jsonify(error='Invalid project status'), 400
        try:
            due = date.fromisoformat(data['due_date']) if data.get('due_date') else None
        except (ValueError, TypeError):
            return jsonify(error='Invalid due date'), 400
        account = str(data.get('client_id') or '')
        if account and not company_rows(Client).filter_by(id=account).first():
            return jsonify(error='Account not found'), 404
        row = company_rows(CRMProject).filter_by(id=project_id).first() if project_id else None
        if project_id and not row:
            return jsonify(error='Project not found'), 404
        if not row:
            row = CRMProject(id='prj-' + uuid.uuid4().hex, company_id=get_current_company())
            get_cdb().add(row)
        row.name, row.status, row.client_id, row.due_date = name, status, account or None, due
        row.description = str(data.get('description') or '')[:10000]
        row.owner = str(data.get('owner') or '')[:200]
        get_cdb().commit()
        return jsonify(success=True, project=row.to_dict()), (200 if project_id else 201)

    @app.route('/api/crm/workspace/preferences', methods=['GET', 'POST'])
    @login_required
    def crm_workspace_preferences():
        row = company_rows(CRMSetting).filter_by(key='workspace_preferences').first()
        if request.method == 'GET':
            return jsonify(success=True, can_edit=owner(), preferences=json.loads(row.value_json) if row else {})
        if not owner():
            return jsonify(error='Only owners can change workspace setup'), 403
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error='Provide settings as an object'), 400
        allowed = {'show_metrics', 'chat_provider', 'chat_account', 'chat_department', 'chat_widget_url', 'chat_enabled'}
        if set(data) - allowed:
            return jsonify(error='Unknown setup field'), 400
        for flag in ('show_metrics', 'chat_enabled'):
            if flag in data and not isinstance(data[flag], bool):
                return jsonify(error='Invalid setting value'), 400
        for key in ('chat_provider', 'chat_account', 'chat_department', 'chat_widget_url'):
            if key in data and (not isinstance(data[key], str) or len(data[key]) > 1000):
                return jsonify(error='Invalid channel setting'), 400
        values = json.loads(row.value_json) if row else {}
        values.update(data)
        widget = values.get('chat_widget_url', '').strip()
        if widget:
            parsed = urlparse(widget)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                return jsonify(error='Use the HTTPS widget script URL supplied by your chat provider'), 400
        if values.get('chat_enabled') and not widget:
            return jsonify(error='Add a provider widget script URL before enabling the installation snippet'), 400
        values['chat_widget_url'] = widget
        if not row:
            row = CRMSetting(company_id=get_current_company(), key='workspace_preferences')
            get_cdb().add(row)
        row.value_json = json.dumps(values)
        get_cdb().commit()
        return jsonify(success=True)

    @app.route('/api/crm/workspace/export/<module>')
    @login_required
    def crm_workspace_export(module):
        models = {'contacts': CRMContact, 'leads': CRMLead, 'activities': CRMInteraction, 'projects': CRMProject}
        if module not in models:
            return jsonify(error='Unknown export module'), 404
        rows = [r.to_dict() for r in company_rows(models[module]).all()]
        fields = [c.name for c in models[module].__table__.columns if c.name != 'company_id']
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        for row in rows:
            # Prevent spreadsheet formula execution when opening exported text.
            writer.writerow({k: ("'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@', '\t', '\r')) else v) for k, v in row.items()})
        return Response('\ufeff' + stream.getvalue(), mimetype='text/csv', headers={
            'Content-Disposition': f'attachment; filename="crm-{module}.csv"'})

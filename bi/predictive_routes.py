from flask import abort, jsonify, render_template, request
from . import predictive


def register_predictive_routes(app, login_required, require_permission, get_cdb,
                               get_current_company, get_current_user, get_company_by_id):
    def access():
        if get_current_user().get('role') not in ('owner', 'super_admin'):
            abort(403)
        company_id = get_current_company()
        company = get_company_by_id(company_id) if company_id else None
        cdb = get_cdb() if company else None
        if not company or cdb is None:
            abort(400)
        return company_id, company, cdb

    @app.route('/bi-predictive', endpoint='bi_predictive')
    @login_required
    @require_permission('analytics', 'view')
    def bi_predictive():
        _id, company, _cdb = access()
        return render_template('bi_predictive.html', company=company, active='bi_intelligence')

    @app.route('/api/bi/v1/predictive', endpoint='api_bi_predictive')
    @login_required
    @require_permission('analytics', 'view')
    def api_bi_predictive():
        company_id, _company, cdb = access()
        try:
            lead_days = int(request.args.get('lead_days', '14'))
            if not 1 <= lead_days <= 180:
                raise ValueError('lead_days must be between 1 and 180.')
            horizon = int(request.args.get('horizon', '3'))
            if not 1 <= horizon <= 12:
                raise ValueError('Forecast horizon must be between 1 and 12 months.')
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 400
        try:
            return jsonify(predictive.build(cdb, company_id, lead_days=lead_days, horizon=horizon))
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 409

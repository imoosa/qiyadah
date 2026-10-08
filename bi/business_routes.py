"""Primary BI dashboard spanning all entitled business modules."""
from flask import abort, jsonify, redirect, render_template, request, url_for

from .business import MODULES, business_overview
from .filters import BIValidationError, parse_filters


def register_business_routes(app, login_required, require_permission, get_cdb,
                            get_current_company, get_current_user, get_company_by_id,
                            has_permission, today_ist):
    def data():
        if get_current_user().get('role') not in ('owner', 'super_admin'):
            abort(403)
        access = app.extensions.get('module_access')
        if not access or not access('bi'):
            abort(403)
        company_id = get_current_company()
        company = get_company_by_id(company_id) if company_id else None
        if not company:
            abort(404)
        filters = parse_filters(request.args, company_id, today_ist())
        if any((filters.employee_id, filters.country, filters.client_id, filters.supplier_id,
                filters.product_category, filters.expense_category)):
            raise BIValidationError('The all-module overview supports date and module filters. Use the detailed reports for other filters.')
        selected = request.args.get('module', 'all')
        if selected not in {'all', *(key for key, *_ in MODULES)}:
            raise BIValidationError('Choose a valid business module.')
        if selected != 'all' and not access(selected):
            raise BIValidationError('The selected business area is not included in your current plan. Upgrade your plan to access this module.')
        overview = business_overview(get_cdb(), company_id, filters.from_date, filters.to_date,
            today_ist(), access, has_permission, company.currency or 'INR')
        overview['selected'] = selected
        return company, overview

    @app.route('/bi-dashboard', endpoint='bi_dashboard')
    @login_required
    @require_permission('analytics', 'view')
    def dashboard():
        # Preserve the existing scoped dashboard for team users. Company-wide
        # operational and payroll totals follow the executive BI owner boundary.
        if get_current_user().get('role') not in ('owner', 'super_admin'):
            return redirect(url_for('bi_finance_dashboard'))
        try:
            company, overview = data()
            return render_template('bi_business.html', company=company, overview=overview,
                                   active='bi_dashboard', error=None)
        except BIValidationError as error:
            company_id = get_current_company()
            company = get_company_by_id(company_id) if company_id else None
            return render_template('bi_business.html', company=company, overview=None, error=str(error), active='bi_dashboard'), 400

    @app.route('/api/bi/v1/business', endpoint='api_bi_v1_business')
    @login_required
    @require_permission('analytics', 'view')
    def api():
        try:
            company, overview = data()
            response = jsonify(company_id=company.company_id, overview=overview)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except BIValidationError as error:
            return jsonify(error=str(error)), 400

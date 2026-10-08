"""Owner-only warehouse endpoints and explicit scheduler entry point."""
import secrets
import click
from flask import abort, jsonify, render_template, request, session
from . import warehouse


def register_warehouse_routes(app, login_required, require_permission, get_cdb,
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

    @app.route('/bi-warehouse', endpoint='bi_warehouse')
    @login_required
    @require_permission('analytics', 'view')
    def bi_warehouse():
        _id, company, _cdb = access()
        token = session.get('bi_builder_csrf') or secrets.token_urlsafe(32)
        session['bi_builder_csrf'] = token
        return render_template('bi_warehouse.html', company=company,
                               active='bi_intelligence', bi_csrf=token)

    @app.route('/api/bi/v1/warehouse/status', endpoint='api_bi_warehouse_status')
    @login_required
    @require_permission('analytics', 'view')
    def api_bi_warehouse_status():
        company_id, _company, cdb = access()
        return jsonify(warehouse.status(cdb, company_id))

    @app.route('/api/bi/v1/warehouse/summary', endpoint='api_bi_warehouse_summary')
    @login_required
    @require_permission('analytics', 'view')
    def api_bi_warehouse_summary():
        company_id, _company, cdb = access()
        try:
            return jsonify(warehouse.summary(cdb, company_id))
        except ValueError as exc:
            return jsonify({'error': str(exc)}), 409

    @app.route('/api/bi/v1/warehouse/refresh', methods=['POST'], endpoint='api_bi_warehouse_refresh')
    @login_required
    @require_permission('analytics', 'view')
    def api_bi_warehouse_refresh():
        company_id, company, cdb = access()
        expected = session.get('bi_builder_csrf')
        provided = request.headers.get('X-BI-CSRF')
        if not expected or not provided or not secrets.compare_digest(expected, provided):
            abort(403)
        try:
            return jsonify(warehouse.refresh(cdb, company_id,
                           (getattr(company, 'currency', None) or 'INR').upper()))
        except Exception:
            app.logger.exception('BI warehouse refresh failed for company %s', company_id)
            return jsonify({'error': 'Warehouse refresh failed; see ETL runs and server logs.'}), 500

    @app.cli.command('bi-refresh')
    @click.option('--company-id', required=True, help='Company ID to refresh; schedule once per tenant.')
    def bi_refresh(company_id):
        from db_router import get_customer_session_with_retry
        company = get_company_by_id(company_id)
        if company is None:
            raise click.ClickException('Unknown company ID')
        cdb = get_customer_session_with_retry(company_id)
        try:
            click.echo(warehouse.refresh(cdb, company_id,
                       (getattr(company, 'currency', None) or 'INR').upper()))
        except Exception as exc:
            raise click.ClickException('Warehouse refresh failed; inspect bi_etl_runs and server logs') from exc
        finally:
            cdb.close()

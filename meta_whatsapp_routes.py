"""Owner-only, single-company App Review workspace; not customer onboarding."""
import os
from flask import abort, render_template, request, redirect, url_for, flash
from meta_whatsapp import MetaReviewClient, MetaError


def register_meta_whatsapp(app, login_required, get_user, get_company_id, company_lookup):
    @app.route('/marketing/whatsapp/<page>', methods=['GET', 'POST'])
    @login_required
    def meta_whatsapp(page):
        if page not in ('dashboard', 'setup', 'send', 'templates', 'create-template'):
            abort(404)
        user, cid = get_user(), get_company_id()
        company = company_lookup(cid) if cid else None
        if (not company or user.get('role') not in ('owner', 'super_admin') or
                (user.get('role') != 'super_admin' and company.owner_email.lower() != str(user.get('email', '')).lower())):
            abort(403)
        demo_ready = str(cid) == os.environ.get('META_DEMO_COMPANY_ID', '')
        if not demo_ready:
            if request.method == 'POST':
                abort(403)
            # Owners may see setup guidance, never another company's shared assets.
            return render_template('meta_whatsapp.html', page=page, company=company, user=user,
                active='meta_whatsapp', demo_ready=False, current_company_id=str(cid),
                demo_unconfigured=not bool(os.environ.get('META_DEMO_COMPANY_ID', '').strip()),
                config={}, configured={}, templates=[], account=None, result=None, error=None)
        if request.method == 'POST' and page not in ('send', 'create-template'):
            abort(405)
        result, error, templates, account = None, None, [], None
        status = 200
        try:
            client = MetaReviewClient() if page != 'setup' else None
            if request.method == 'POST':
                from auth_security import allow_attempt
                if not allow_attempt('meta-review', str(cid), 10, 60):
                    abort(429)
                if page == 'send':
                    selection = request.form.get('template', '').split('|', 1)
                    if len(selection) != 2:
                        raise MetaError('Select an approved template.')
                    result = client.send(request.form.get('recipient', ''), *selection, request.form.get('phone', ''), request.form)
                else:
                    result = client.create(request.form)
                app.logger.info('meta_review action=%s company=%s actor=%s outcome=accepted', page, cid, user.get('user_id'))
                if page == 'create-template':
                    flash('Template submitted to Meta. Check its review status in the template list.', 'success')
                    return redirect(url_for('meta_whatsapp', page='templates'), code=303)
            if page in ('send', 'templates'):
                templates = client.templates().get('data', [])
            if page == 'dashboard':
                account = client.account()
        except (MetaError, ValueError) as exc:
            error, status = str(exc), 400
            if request.method == 'POST':
                app.logger.info('meta_review action=%s company=%s actor=%s outcome=failed_or_unknown', page, cid, user.get('user_id'))
        config = {key: os.environ.get(key, '') for key in ('META_APP_ID', 'META_GRAPH_API_VERSION', 'META_WABA_ID', 'META_PHONE_NUMBER_ID')}
        configured = {key: bool(os.environ.get(key)) for key in ('META_ACCESS_TOKEN', 'META_APP_SECRET', 'META_WEBHOOK_VERIFY_TOKEN', 'META_WEBHOOK_APP_SECRET')}
        return render_template('meta_whatsapp.html', page=page, company=company, user=user,
            active='meta_whatsapp', config=config, configured=configured, result=result,
            error=error, templates=templates, account=account, demo_ready=True), status

"""Platform module entitlements. Admin blocks take precedence over plan grants."""
from datetime import date, timedelta, datetime, timezone
from flask import g, request, session, jsonify, render_template
from platform_models import db, Company, RegisteredUser, PlatformAccessRule
from customer_models import CompanyUser
from plan_catalog import plan_modules

MODULES = {'crm': 'CRM', 'repair': 'Repair & Management', 'orderflow': 'Supply Chain Management', 'core': 'Finance & Accounting', 'hr': 'HR & Payroll', 'bi': 'Business Intelligence'}
SHARED_ENDPOINTS = {'apps_hub','login','logout','force_change_password','verify_otp','resend_otp',
    'select_company','switch_company','profile','no_access','onboard_company','account_setup',
    'upgrade_plan','register','trial_checkout','subscription','static','service_worker','health_check'}


def rule(scope, target):
    return db.session.get(PlatformAccessRule, (scope, str(target))) if target else None


def module_states(plan_rule=None, layers=(), active=True, trial_end=None, today=None):
    """Pure resolution: hard account/company/user denies > grants > plan defaults."""
    today = today or date.today()
    result = {}
    for key in MODULES:
        baseline = (plan_rule or {}).get(key, True)
        blockers = [name for name, values in layers if values.get(key) is False]
        grants = [name for name, values in layers if values.get(key) is True]
        allowed = not blockers and (bool(grants) or baseline)
        reason = ('Blocked by ' + ', '.join(blockers)) if blockers else ('Allowed by ' + ', '.join(grants) if grants else ('Included in plan' if baseline else 'Not included in plan'))
        if not active:
            allowed, reason = False, 'Account or company is inactive'
        elif trial_end and trial_end < today:
            allowed, reason = False, 'Trial expired'
        result[key] = {'allowed': bool(allowed), 'reason': reason}
    return result


def trial_expiry(account, company=None):
    plan = company.subscription_plan if company else account.subscription_plan
    if plan != 'trial' and (not account or account.payment_status != 'trial'):
        return None
    if company:
        own = rule('company', company.company_id)
        if own and own.trial_end:
            return own.trial_end
    account_rule = rule('account', account.user_id) if account else None
    if account_rule and account_rule.trial_end:
        return account_rule.trial_end
    if plan == 'trial' and company and company.subscription_end:
        return company.subscription_end
    created = account.created_at if account else (company.created_at if company else date.today())
    if isinstance(created, datetime):
        created = created.date()
    return (created or date.today()) + timedelta(days=14)


def subject_access(account, company=None, member=None, today=None):
    plan = (company.subscription_plan if company else account.subscription_plan) or ''
    plan_policy = rule('plan', plan)
    layers = []
    if account:
        policy = rule('account', account.user_id)
        layers.append(('account', (policy.overrides or {}) if policy else {}))
    if company:
        policy = rule('company', company.company_id)
        layers.append(('company', (policy.overrides or {}) if policy else {}))
    if member:
        policy = rule('user', f'{company.company_id}:{member.user_id}')
        layers.append(('team member', (policy.overrides or {}) if policy else {}))
    active = bool(account and account.is_active and (not company or company.is_active) and (not member or member.is_active))
    return module_states({**plan_modules(plan), **(plan_policy.overrides or {} if plan_policy else {})}, layers, active,
                         trial_expiry(account, company), today)


def company_has_hr_access(company):
    """Resolve the target company's entitlement independently of the current session."""
    if not company:
        return False
    account = RegisteredUser.query.filter_by(email=company.owner_email).first()
    return bool(account and subject_access(account, company)['hr']['allowed'])


def register_module_access(app, get_current_user, get_current_company, get_customer_session, today_func):
    def current_access():
        if hasattr(g, 'platform_module_access'):
            return g.platform_module_access
        user = get_current_user() or {}
        if user.get('role') == 'super_admin':
            admin = RegisteredUser.query.filter_by(user_id=user.get('user_id'), role='super_admin', is_active=True).first()
            result = {key: {'allowed': bool(admin), 'reason': 'Super admin' if admin else 'Inactive administrator'} for key in MODULES}
        elif not user:
            result = {key: {'allowed': False, 'reason': 'Sign in required'} for key in MODULES}
        else:
            company_id = get_current_company()
            company = Company.query.filter_by(company_id=company_id).first() if company_id else None
            account = RegisteredUser.query.filter_by(email=company.owner_email if company else user.get('email')).first()
            member = None
            member_invalid = False
            if company and user.get('role') != 'owner':
                member = get_customer_session(company_id).query(CompanyUser).filter_by(
                    company_id=company_id, user_id=user.get('user_id'), email=user.get('email')).first()
                member_invalid = member is None
            elif company and company.owner_email != user.get('email'):
                member_invalid = True
            result = subject_access(account, company, member, today_func()) if account else module_states(active=False)
            if member_invalid or (company_id and not company):
                result = module_states(active=False)
            if user.get('role') != 'owner':
                from permissions import explicitly_granted_bi
                if not explicitly_granted_bi(member):
                    result['bi'] = {'allowed': False, 'reason': 'Business Intelligence requires the BI Developer role and an individual permission grant from the company owner.'}
        g.platform_module_access = result
        return result

    def has_module_access(module):
        return bool(current_access().get(module, {}).get('allowed'))

    app.extensions['module_access'] = has_module_access
    app.extensions['module_access_state'] = current_access

    def bi_unified_access():
        if not has_module_access('bi'):
            return False
        company_id = get_current_company()
        company = Company.query.filter_by(company_id=company_id).first() if company_id else None
        return bool(company and company.subscription_plan == 'unified')

    app.extensions['bi_unified_access'] = bi_unified_access

    @app.context_processor
    def inject_module_access():
        return {'module_access': has_module_access, 'module_access_state': current_access,
                'workspace_modules': MODULES, 'bi_unified_access': bi_unified_access}

    @app.before_request
    def enforce_platform_modules():
        g.pop('platform_module_access', None)
        user = get_current_user() or {}
        if not user or not request.endpoint:
            return
        if request.endpoint in SHARED_ENDPOINTS:
            return
        path = request.path
        if path.startswith(('/admin/', '/api/admin/', '/migrations', '/company/', '/settings/', '/onboarding/', '/payment', '/subscription', '/razorpay', '/upgrade', '/renew')):
            return
        view = app.view_functions.get(request.endpoint)
        source = getattr(view, '__module__', '')
        if (request.endpoint == 'supply_chain_workspace' or source == 'erp_routes'
                or request.endpoint.startswith(('purchase_order_', 'sales_order_', 'delivery_challan_', 'inventory_', 'stock_'))
                or path.startswith(('/inventory', '/stock/', '/api/stock/', '/api/reports/stock-data'))):
            module = 'orderflow'
        elif request.endpoint in ('repair_bills_view', 'repair_bill_view'):
            # Existing financial documents are shared by Core and Workshop.
            # Route-level customer_invoices permissions still apply. This does
            # not grant Core users access to workshop operational APIs.
            if has_module_access('core') or has_module_access('repair'):
                return
            module = 'core'
        elif source == 'hr_workspace' or path.startswith(('/hr', '/api/hr/')):
            module = 'hr'
        elif request.endpoint in ('bi_dashboard', 'bi_intelligence', 'reports_dashboard') or source == 'bi' or source.startswith('bi.') or path.startswith(('/api/bi/', '/bi-', '/bi/', '/reports-dashboard')):
            module = 'bi'
        elif source in ('crm_routes', 'crm_workspace') or path.startswith(('/crm', '/api/crm/')):
            module = 'crm'
        elif source == 'workshop_routes' or path.startswith(('/workshop', '/repair-bills', '/api/workshop/')):
            module = 'repair'
        elif source == 'order_erp_routes' or path.startswith(('/order-erp', '/api/order-erp/')):
            module = 'orderflow'
        elif getattr(view, '_requires_login', False) or source == 'erp_routes':
            module = 'core'
        else:
            return
        state = current_access()[module]
        if state['allowed']:
            if module == 'bi':
                standard_paths = {'/bi-intelligence', '/bi-dashboard', '/bi-dashboard/finance',
                    '/api/bi/v1/business', '/api/bi/dashboard', '/api/bi/company-analysis',
                    '/reports-dashboard'}
                if path.rstrip('/') in ('/bi-dashboard', '/api/bi/v1/business'):
                    target_module = request.args.get('module', 'all')
                    if target_module != 'all':
                        if not bi_unified_access() or not has_module_access(target_module):
                            reason = 'This BI feature is available only in Qiyadah Unified.' if not bi_unified_access() else f'The {MODULES.get(target_module, target_module)} module is not included in your current subscription plan.'
                            if path.startswith('/api/') or request.is_json:
                                return jsonify(success=False, error=reason, required_plan='unified'), 403
                            return render_template('module_access_denied.html', module_name='Unified BI', reason=reason), 403
                else:
                    is_dev_path = path.rstrip('/').startswith(('/bi-builder', '/api/bi/v1/builder'))
                    premium = path.rstrip('/') not in standard_paths and not (is_dev_path and user.get('role') == 'bi_developer')
                    if premium and not bi_unified_access():
                        reason = 'This BI feature is available only in Qiyadah Unified.'
                        if path.startswith('/api/') or request.is_json:
                            return jsonify(success=False, error=reason, required_plan='unified'), 403
                        return render_template('module_access_denied.html', module_name='Unified BI', reason=reason), 403
            return
        if path.startswith('/api/') or request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify(success=False, error=state['reason'], module=module, redirect='/apps'), 403
        return render_template('module_access_denied.html', module_name=MODULES[module], reason=state['reason']), 403

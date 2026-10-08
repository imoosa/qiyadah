"""Super-admin access console and trial management APIs."""
import hmac
import secrets
from decimal import Decimal, InvalidOperation
from datetime import timedelta
from functools import wraps
from flask import request, session, jsonify
from sqlalchemy.exc import IntegrityError
from platform_models import db, Company, RegisteredUser, SubscriptionPlan, PlatformAccessRule, PlatformAccessAudit
from customer_models import CompanyUser
from module_access import MODULES, rule, trial_expiry, subject_access, module_states


def register_admin_access(app, get_current_user, get_customer_session, today_func):
    def csrf_token():
        if 'admin_access_csrf' not in session:
            session['admin_access_csrf'] = secrets.token_urlsafe(32)
        return session['admin_access_csrf']

    @app.context_processor
    def inject_access_console():
        return {'admin_access_csrf': csrf_token}

    def admin_api(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = get_current_user() or {}
            if not user:
                return jsonify(success=False, error='Sign in required'), 401
            if user.get('role') != 'super_admin' or not RegisteredUser.query.filter_by(
                    user_id=user.get('user_id'), role='super_admin', is_active=True).first():
                return jsonify(success=False, error='Super-admin access required'), 403
            if request.method != 'GET' and not hmac.compare_digest(
                    request.headers.get('X-Admin-CSRF', ''), csrf_token()):
                return jsonify(success=False, error='Session token expired. Reload the panel.'), 403
            return view(*args, **kwargs)
        return wrapped

    def resolve(scope, target):
        if scope == 'plan':
            obj = db.session.get(SubscriptionPlan, target)
            return (obj, None, None, None)
        if scope == 'account':
            account = RegisteredUser.query.filter_by(user_id=target, role='owner').first()
            return (account, account, None, None)
        if scope in ('company', 'user'):
            company_id = target.split(':', 1)[0] if scope == 'user' else target
            company = Company.query.filter_by(company_id=company_id).first()
            if not company:
                return (None, None, None, None)
            account = RegisteredUser.query.filter_by(email=company.owner_email).first()
            member = None
            if scope == 'user':
                if ':' not in target:
                    return (None, None, None, None)
                member = get_customer_session(company_id).query(CompanyUser).filter_by(
                    company_id=company_id, user_id=target.split(':', 1)[1]).first()
                if not member or member.role in ('owner', 'super_admin'):
                    return (None, None, None, None)
            return (member if scope == 'user' else company, account, company, member)
        return (None, None, None, None)

    def snapshot(policy):
        return {'overrides': policy.overrides or {} if policy else {},
                'trial_end': policy.trial_end.isoformat() if policy and policy.trial_end else None,
                'revision': policy.revision if policy else 0}

    @app.route('/api/admin/access/catalog')
    @admin_api
    def admin_access_catalog():
        accounts = RegisteredUser.query.filter_by(role='owner').order_by(RegisteredUser.full_name).all()
        companies = Company.query.order_by(Company.company_name).all()
        today = today_func()
        owners = []
        for a in accounts:
            end = trial_expiry(a)
            owners.append({'id': a.user_id, 'name': a.full_name, 'email': a.email,
                'plan': a.subscription_plan, 'active': a.is_active,
                'trial_end': end.isoformat() if end else None,
                'trial_expired': bool(end and end < today),
                'modules': subject_access(a, today=today)})
        return jsonify(success=True, csrf_token=csrf_token(), modules=MODULES, today=today.isoformat(),
            accounts=owners, companies=[{'id':c.company_id,'name':c.company_name,'owner':c.owner_email,
                'plan':c.subscription_plan,'active':c.is_active} for c in companies],
            plans=[{'id':p.id,'name':p.name} for p in SubscriptionPlan.query.order_by(SubscriptionPlan.name).all()])

    @app.route('/api/admin/custom-plan/<account_id>', methods=['POST'])
    @admin_api
    def admin_assign_custom_plan(account_id):
        account = RegisteredUser.query.filter_by(user_id=account_id, role='owner').with_for_update().first()
        if not account:
            return jsonify(success=False, error='Customer account not found'), 404
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(success=False, error='Provide a custom plan object.'), 400
        try:
            name = str(data.get('name', '')).strip()
            amount = Decimal(str(data.get('annual_price', '')))
            limits = {key: data.get(key) for key in ('users', 'companies', 'branches')}
            modules = data.get('modules')
            years = data.get('years', 1)
            if not name or len(name) > 100 or not amount.is_finite() or not 0 <= amount <= 9999999 or amount != amount.quantize(Decimal('.01')):
                raise ValueError()
            if any(type(v) is not int or not 1 <= v <= 10000 for v in limits.values()):
                raise ValueError()
            if type(years) is not int or years not in (1, 3):
                raise ValueError()
            if not isinstance(modules, list) or not modules or any(m not in MODULES for m in modules):
                raise ValueError()
        except (InvalidOperation, ValueError, TypeError):
            return jsonify(success=False, error='Provide a name, non-negative price, positive whole-number limits, workspaces and a 1- or 3-year term.'), 400
        # Each negotiated plan is private to this account, never a public offering.
        plan_id = 'custom_' + secrets.token_hex(6)
        plan = SubscriptionPlan(id=plan_id, name=name, price=str(amount), price_1yr=str(amount),
            price_3yr=str(amount * 3), max_companies=str(limits['companies']),
            max_users=str(limits['users']), max_branches=limits['branches'],
            features=', '.join(MODULES[m] for m in modules))
        db.session.add(plan)
        db.session.flush()
        actor = get_current_user().get('email') or get_current_user()['user_id']
        db.session.add(PlatformAccessRule(scope='plan', target=plan_id,
            overrides={m: m in modules for m in MODULES}, revision=1, updated_by=actor))
        before = {'plan': account.subscription_plan, 'annual_price': str(account.custom_yearly_amount)}
        account.subscription_plan = plan_id
        if account.payment_status == 'trial':
            account.payment_status = 'pending'
        account.custom_yearly_amount = amount
        account.custom_max_users = limits['users']
        account.custom_max_companies = limits['companies']
        account.plan_duration = '3_years' if years == 3 else '1_year'
        end = today_func() + timedelta(days=365 * years)
        for co in Company.query.filter_by(owner_email=account.email).all():
            co.subscription_plan = plan_id
            co.custom_yearly_amount = amount
            co.max_companies_allowed = str(limits['companies'])
            co.max_users_per_company = str(limits['users'])
            co.plan_duration = account.plan_duration
            co.subscription_end = end
        db.session.add(PlatformAccessAudit(scope='account', target=account_id, actor=actor,
            before_json=before, after_json={'plan': plan_id, 'name': name, 'annual_price': str(amount),
                'limits': limits, 'modules': modules, 'years': years},
            reason=str(data.get('reason') or 'Private plan assigned')[:1000]))
        db.session.commit()
        return jsonify(success=True, plan_id=plan_id, message='Private plan assigned to this account and its companies. No payment was collected.')

    @app.route('/api/admin/access/<scope>/<path:target>', methods=['GET', 'PUT'])
    @admin_api
    def admin_access_detail(scope, target):
        obj, account, company, member = resolve(scope, target)
        if obj is None:
            return jsonify(success=False, error='Access target not found'), 404
        policy = rule(scope, target)
        if request.method == 'PUT':
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify(success=False, error='Provide access settings'), 400
            overrides = data.get('overrides')
            if not isinstance(overrides, dict) or set(overrides) - set(MODULES) or any(type(v) is not bool for v in overrides.values()):
                return jsonify(success=False, error='Use Allow, Block or Follow plan for each module'), 400
            revision = data.get('revision')
            days = data.get('extend_days', 0)
            if type(revision) is not int or type(days) is not int or not 0 <= days <= 3650:
                return jsonify(success=False, error='Extension must be a whole number from 0 to 3650 days'), 400
            end = trial_expiry(account, company) if scope in ('account', 'company') else None
            if days and end is None:
                return jsonify(success=False, error='Only trial accounts or companies can have their trial extended'), 400
            # Lock current state and reject stale forms, including duplicate submissions.
            policy = PlatformAccessRule.query.filter_by(scope=scope, target=target).with_for_update().first()
            if revision != (policy.revision if policy else 0):
                return jsonify(success=False, error='Settings changed since you opened this form. Reload and try again.'), 409
            before = snapshot(policy)
            if not policy:
                policy = PlatformAccessRule(scope=scope, target=target, revision=0)
                db.session.add(policy)
            policy.overrides = overrides
            if days:
                policy.trial_end = max(today_func(), end) + timedelta(days=days)
                if company:
                    company.subscription_end = policy.trial_end
                else:
                    for co in Company.query.filter_by(owner_email=account.email, subscription_plan='trial').all():
                        co_rule = rule('company', co.company_id)
                        if not co_rule or not co_rule.trial_end:
                            co.subscription_end = policy.trial_end
            policy.revision += 1
            policy.updated_by = get_current_user().get('email') or get_current_user()['user_id']
            db.session.add(PlatformAccessAudit(scope=scope, target=target, actor=policy.updated_by,
                before_json=before, after_json=snapshot(policy), reason=str(data.get('reason') or '')[:1000]))
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return jsonify(success=False, error='Concurrent update. Reload and try again.'), 409
        current = snapshot(policy)
        plan = company.subscription_plan if company else (account.subscription_plan if account else obj.id)
        trial_end = trial_expiry(account, company) if scope in ('account', 'company') else None
        members = []
        team_error = None
        if scope == 'company':
            try:
                members = [{'id':f'{company.company_id}:{m.user_id}', 'name':m.full_name, 'email':m.email, 'role':m.role}
                    for m in get_customer_session(company.company_id).query(CompanyUser).filter_by(company_id=company.company_id).all()
                    if m.role not in ('owner', 'super_admin')]
            except Exception:
                team_error = 'Company database unavailable; team access could not be loaded.'
        audit = PlatformAccessAudit.query.filter_by(scope=scope, target=target).order_by(PlatformAccessAudit.id.desc()).limit(10).all()
        effective = subject_access(account, company, member, today_func()) if scope != 'plan' else module_states(current['overrides'])
        return jsonify(success=True, scope=scope, target=target,
            name=getattr(obj,'full_name',None) or getattr(obj,'company_name',None) or obj.name,
            plan=plan, state=current, effective=effective, modules=MODULES,
            trial_end=trial_end.isoformat() if trial_end else None,
            trial_days_left=(trial_end-today_func()).days if trial_end else None,
            members=members, team_error=team_error,
            history=[{'actor':a.actor,'time':a.created_at.isoformat()+'Z','reason':a.reason or '',
                'before':a.before_json,'after':a.after_json} for a in audit])

    @app.route('/api/admin/access/open-company/<company_id>', methods=['POST'])
    @admin_api
    def admin_access_open_company(company_id):
        company = Company.query.filter_by(company_id=company_id).first()
        if not company:
            return jsonify(success=False, error='Company not found'), 404
        session['active_company_id'] = company.company_id
        user = dict(session['user']);user['company_id'] = company.company_id;session['user'] = user
        return jsonify(success=True, redirect='/apps')

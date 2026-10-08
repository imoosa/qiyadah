"""Owner-issued, tenant-scoped authority to manage HR staff permissions.

Delegation is separate from operational permissions. Both are checked afresh
on every request; neither a role name nor a stale login grants authority.
"""
import json
import secrets
from datetime import datetime
from flask import abort, flash, redirect, render_template, request, session, url_for
from werkzeug.exceptions import Forbidden
from customer_models import customer_db, CompanyUser, CompanyRolePermission
from permissions import HR_MODULES, MODULE_LABELS, ACTIONS, get_effective_permissions


class HRAccessDelegation(customer_db.Model):
    __tablename__ = 'hr_access_delegations'
    company_id = customer_db.Column(customer_db.String(20), primary_key=True)
    user_id = customer_db.Column(customer_db.String(20), primary_key=True)
    permissions_json = customer_db.Column(customer_db.Text, nullable=False, default='{}')
    enabled = customer_db.Column(customer_db.Boolean, nullable=False, default=False)


class HRAccessAudit(customer_db.Model):
    __tablename__ = 'hr_access_audit'
    id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)
    company_id = customer_db.Column(customer_db.String(20), nullable=False)
    actor_id = customer_db.Column(customer_db.String(20), nullable=False)
    target_id = customer_db.Column(customer_db.String(20), nullable=False)
    action = customer_db.Column(customer_db.String(40), nullable=False)
    before_json = customer_db.Column(customer_db.Text, nullable=False)
    after_json = customer_db.Column(customer_db.Text, nullable=False)
    created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)


def object_json(value):
    try:
        result = json.loads(value or '{}')
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}


def register_hr_user_access(app, get_current_user, get_current_company,
                            get_customer_session, get_company_by_id):
    def context():
        user = get_current_user() or {}
        cid = get_current_company()
        company = get_company_by_id(cid) if cid else None
        if not user or not company or not company.is_active:
            abort(403)
        cdb = get_customer_session(cid)
        owner = (user.get('role') == 'owner' and
                 (user.get('email') or '').lower() == (company.owner_email or '').lower())
        # Platform administrators remain in the existing platform console.
        member = cdb.query(CompanyUser).filter_by(company_id=cid,
            user_id=user.get('user_id'), email=user.get('email'), is_active=True).first()
        if not owner and (not member or member.role != 'hr_admin'):
            abort(403)
        for model in (HRAccessDelegation, HRAccessAudit):
            model.__table__.create(cdb.get_bind(), checkfirst=True)
        hr_enabled = app.extensions['module_access']('hr')
        ceiling = {m: {a: owner and a != 'delete' for a in ACTIONS} for m in HR_MODULES}
        if not owner:
            grant = cdb.get(HRAccessDelegation, (cid, member.user_id))
            if not hr_enabled or not grant or not grant.enabled:
                abort(403)
            allowed = object_json(grant.permissions_json)
            actual = get_effective_permissions(member.role, cid, member.user_id,
                cdb, CompanyRolePermission, CompanyUser)
            if not actual.get('hr', {}).get('view'):
                abort(403)
            ceiling = {m: {a: a != 'delete' and
                isinstance(allowed.get(m), dict) and allowed[m].get(a) is True and
                actual.get(m, {}).get(a) is True for a in ACTIONS} for m in HR_MODULES}
        return user, cid, company, cdb, owner, hr_enabled, ceiling

    def audit(cdb, cid, actor, target, action, before, after):
        cdb.add(HRAccessAudit(company_id=cid, actor_id=actor['user_id'],
            target_id=target.user_id, action=action,
            before_json=json.dumps(before), after_json=json.dumps(after)))

    @app.context_processor
    def inject_hr_administration():
        def can_manage_hr_access():
            try:
                return bool(context()[5])
            except Forbidden:
                return False
        return {'can_manage_hr_access': can_manage_hr_access}

    @app.route('/company/hr-user-access', methods=['GET', 'POST'])
    def hr_user_access():
        user, cid, company, cdb, owner, hr_enabled, ceiling = context()
        token = session.setdefault('hr_access_csrf', secrets.token_urlsafe(32))
        if request.method == 'POST':
            if not secrets.compare_digest(token, request.form.get('csrf_token', '')):
                abort(400, 'Please reload the page and try again.')
            target = cdb.query(CompanyUser).filter_by(company_id=cid,
                user_id=request.form.get('user_id')).first()
            if not target or target.user_id == user.get('user_id'):
                abort(403)
            action = request.form.get('action')
            if action == 'delegation':
                if not owner or target.role != 'hr_admin':
                    abort(403)
                enabled = request.form.get('enabled') == 'on'
                if enabled and (not hr_enabled or not target.is_active):
                    abort(403)
                grant = cdb.get(HRAccessDelegation, (cid, target.user_id))
                before = {'enabled': bool(grant and grant.enabled),
                          'permissions': object_json(grant.permissions_json) if grant else {}}
                if not grant:
                    grant = HRAccessDelegation(company_id=cid, user_id=target.user_id)
                    cdb.add(grant)
                matrix = {m: {a: a != 'delete' and request.form.get(f'{m}__{a}') == 'on'
                               for a in ACTIONS} for m in HR_MODULES}
                grant.enabled, grant.permissions_json = enabled, json.dumps(matrix)
                audit(cdb, cid, user, target, action, before,
                      {'enabled': enabled, 'permissions': matrix})
            elif action == 'permissions':
                if not hr_enabled or target.role not in ('hr_staff', 'payroll_officer') or not target.is_active:
                    abort(403)
                before = object_json(target.permission_overrides)
                after = json.loads(json.dumps(before))
                # Change only delegated cells. Preserve every other permission,
                # including owner-granted access outside this administrator's remit.
                for m in HR_MODULES:
                    changes = {}
                    for a in ACTIONS:
                        selected = request.form.get(f'{m}__{a}') == 'on'
                        if selected and not ceiling[m][a]:
                            abort(403)
                        if ceiling[m][a]:
                            changes[a] = selected
                    if changes:
                        current = after.get(m, {})
                        after[m] = {**(current if isinstance(current, dict) else {}), **changes}
                # Reject forged non-HR permission fields, roles and delegation flags.
                reserved = {'csrf_token', 'action', 'user_id'}
                valid = {f'{m}__{a}' for m in HR_MODULES for a in ACTIONS}
                if set(request.form) - reserved - valid:
                    abort(400)
                target.permission_overrides = json.dumps(after)
                audit(cdb, cid, user, target, action, before, after)
            else:
                abort(400)
            cdb.commit()
            flash('HR access updated. Changes apply to subsequent requests.', 'success')
            return redirect(url_for('hr_user_access'))
        members = cdb.query(CompanyUser).filter_by(company_id=cid).order_by(CompanyUser.full_name).all()
        admins = [m for m in members if m.role == 'hr_admin'] if owner else []
        staff = [m for m in members if m.role in ('hr_staff', 'payroll_officer') and m.is_active]
        grants = {m.user_id: cdb.get(HRAccessDelegation, (cid, m.user_id)) for m in admins}
        permissions = {m.user_id: get_effective_permissions(m.role, cid, m.user_id,
            cdb, CompanyRolePermission, CompanyUser) for m in staff}
        return render_template('hr_user_access.html', company=company, user=user,
            is_owner=owner, hr_enabled=hr_enabled, admins=admins, staff=staff,
            grants=grants, object_json=object_json, permissions=permissions,
            ceiling=ceiling, modules=HR_MODULES, labels=MODULE_LABELS,
            actions=('view', 'create', 'edit'), csrf_token=token, active='hr_user_access')

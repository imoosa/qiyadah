"""Public Qiyadah plans. Three-year prices are the total payable, not annual rates."""
PUBLIC_PLANS = {}
for key, name, users, companies, branches, annual, rate, modules in (
    ('finance', 'Qiyadah Core', 5, 2, 2, 6999, 4999, ('core', 'bi')),
    ('finance_workshop', 'Qiyadah Service', 5, 2, 2, 12999, 8999, ('core', 'repair', 'bi')),
    ('finance_crm', 'Qiyadah Growth', 8, 2, 2, 9999, 6999, ('core', 'crm', 'bi')),
    ('crm_hr', 'Qiyadah Workforce', 10, 3, 5, 14999, 9999, ('core', 'crm', 'hr', 'bi')),
    ('finance_supply', 'Qiyadah Supply', 8, 2, 3, 12999, 8999, ('core', 'orderflow', 'bi')),
    ('unified', 'Qiyadah Unified', 20, 5, 10, 29999, 19999, ('core', 'orderflow', 'crm', 'repair', 'hr', 'bi')),
):
    PUBLIC_PLANS[key] = dict(id=key, name=name, max_users=str(users),
        max_users_per_company=str(users), max_companies=str(companies), max_branches=branches,
        price=str(annual), price_1yr=str(annual), price_3yr=str(rate * 3),
        annual_3yr=rate, price_lifetime='', modules=modules,
        features=', '.join({'core':'Finance & Accounting', 'orderflow':'Supply Chain Management',
            'repair':'Workshop / Repair Management', 'crm':'CRM', 'hr':'HR & Payroll', 'bi':'BI Intelligence'}[m] for m in modules))


def plan_modules(plan_id):
    plan = PUBLIC_PLANS.get(plan_id)
    if plan is None:
        return {}  # Preserve existing plans; their administrator rules still apply.
    return {key: key in plan['modules'] for key in ('core','orderflow','crm','repair','hr','bi')}


def check_location_limits(companies, name, branch, company_limit, branch_limit):
    """Company names identify companies; named branches share that company's allowance."""
    names = {c.company_name.strip().casefold() for c in companies}
    if name.strip().casefold() not in names and len(names) >= int(company_limit):
        return False, f'Your plan allows {company_limit} companies.'
    if (branch or '').strip() and sum(bool((c.branch_name or '').strip()) for c in companies) >= int(branch_limit):
        return False, f'Your plan allows {branch_limit} branches across your account.'
    return True, 'OK'

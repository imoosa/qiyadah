# HR permission delegation

Company Settings remains owner-controlled for every subscription. Purchasing HR
does not automatically grant user-administration authority to an HR role.

## Owner setup

1. Open Company Settings → Team. Add or edit company membership and choose HR
   Administrator, HR Staff or Payroll Officer. Existing subscription seat limits
   still apply; these are administrative accounts, not self-service seats.
2. Open Access and select the HR Administrator group. Grant the administrator
   their own operational permissions. New HR roles start with only HR workspace
   view and no Finance, payroll-processing or invoice-field permissions.
3. Open HR Users & Access. Expand the administrator, enable delegation and select
   the HR view/create/edit permissions they may manage. Save delegation.
4. The administrator opens HR Users & Access in the HR navigation. They can update
   active HR Staff and Payroll Officer accounts in the selected company.

## Boundaries

- Authority is the intersection of the owner-issued delegation and the
  administrator's current effective operational permissions.
- The live company membership must be active and have the HR Administrator role;
  a stale session role is insufficient. HR module entitlement must also allow use.
- Delegates cannot modify themselves, another administrator, managers, accountants,
  sales users, other companies, Finance permissions, delete permissions or roles.
- User creation, company membership, activation, self-service enrollment,
  subscriptions and administrator assignment remain with the owner.
- Owner-granted permissions outside the delegation are preserved when staff
  permissions are saved. Each save affects only the delegated cells.
- Disabling delegation, deactivating the administrator, changing their role,
  reducing their operational permissions or losing HR entitlement restricts the
  next request. Removing delegation does not revoke staff permissions previously
  granted; the owner can change those separately.
- POSTs require a session CSRF token. Delegation and permission changes are
  recorded in the tenant's `hr_access_audit` table in the same transaction.

The additive `hr_access_delegations` and `hr_access_audit` tables are created in
the active tenant database when this feature is first used. Existing users and
their saved permissions are not migrated or automatically granted delegation.

This feature does not implement employee self-service or own/team/branch data
scopes. HR administrative access can expose company-wide records for a permitted
module; do not use these roles as employee self-service accounts.

## Verification

Run `python -m unittest discover -s tests -p test_hr_user_access.py` for isolated
authorization, CSRF, tenant separation, entitlement, revocation and audit tests.

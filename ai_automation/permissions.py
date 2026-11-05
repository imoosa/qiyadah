class Scope:
    def __init__(
        self,
        company_id,
        actor=None,
        owner=None,
        permissions=None,
        modules=None,
        application='erp',
        user=None,
        has_permission=None,
        has_module_access=None,
    ):
        if isinstance(actor, dict) and user is None:
            user = actor
            actor = user.get('email') or user.get('user_id') or 'user'
        if user is None:
            user = {
                'email': str(actor or ''),
                'user_id': str(actor or ''),
                'role': 'owner' if owner else 'employee',
            }
        if actor is None:
            actor = user.get('email') or user.get('user_id') or ''
        if owner is None:
            owner = user.get('role') in ('owner', 'super_admin', 'admin')
        perm_fn = permissions or has_permission or (lambda *a: bool(owner))
        mod_fn = modules or has_module_access or (lambda *a: True)

        object.__setattr__(self, 'company_id', str(company_id or ''))
        object.__setattr__(self, 'actor', str(actor or ''))
        object.__setattr__(self, 'owner', bool(owner))
        object.__setattr__(self, 'permissions', perm_fn)
        object.__setattr__(self, 'modules', mod_fn)
        object.__setattr__(self, 'application', str(application or 'erp'))
        object.__setattr__(self, 'user', dict(user))

    def __setattr__(self, name, value):
        raise AttributeError('Scope is immutable.')

    def can(self, permission, action='view'):
        if self.owner:
            return True
        return bool(self.permissions(permission, action))

    def require(self, operation=None, permission=None, action='view', owner=False, module=None):
        if operation in ('view', 'create', 'edit', 'delete'):
            action = operation
            if not self.can('ai_automation', action):
                raise PermissionError('You do not have permission to use AI Automation.')
        elif operation:
            module = operation
        if not self.company_id or not self.actor:
            raise PermissionError('An authorised company session is required.')
        if owner and not self.owner:
            raise PermissionError('This action requires the company owner.')
        if module and not self.modules(module):
            raise PermissionError('The subscription does not permit this module.')
        if permission and not self.permissions(permission, action):
            raise PermissionError('You do not have permission for this operation.')


def rows(db, model, scope):
    scope.require()
    return db.query(model).filter_by(company_id=scope.company_id)

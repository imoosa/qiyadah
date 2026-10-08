"""Supply chain workspace over existing company-scoped operational records."""
from datetime import date

from flask import abort, render_template, request, session, url_for
from sqlalchemy import func

from customer_models import StockItem, PurchaseOrder, SalesOrder, DeliveryChallan
from order_erp_routes import STATUS_FLOW


SUPPLY_NAV = (
    ('Purchasing', (
        ('Purchase orders', 'purchase_order_list', 'purchase_orders'),
        ('Suppliers', 'supplier_list', 'suppliers'),
    )),
    ('Inventory', (('Products & stock movements', 'inventory_list', 'stock'),)),
    ('Sales & fulfilment', (
        ('Customers', 'client_list', 'clients'),
        ('Estimates / quotes', 'estimate_list', 'estimates'),
        ('Sales orders', 'sales_order_list', 'sales_orders'),
        ('Delivery challans', 'delivery_challan_list', 'delivery_challans'),
    )),
    ('Reporting', (('Operational reports', 'reports_dashboard', 'analytics'),)),
)
SUPPLY_PERMISSIONS = ('purchase_orders', 'suppliers', 'stock', 'clients', 'estimates', 'sales_orders', 'delivery_challans')


def supply_chain_allowed(can):
    return any(can(permission, 'view') for permission in SUPPLY_PERMISSIONS)


def supply_navigation(can, orderflow=False):
    groups = []
    for heading, entries in SUPPLY_NAV:
        links = [dict(label=label, href=url_for(endpoint), active=request.endpoint == endpoint)
                 for label, endpoint, permission in entries if can(permission, 'view')]
        if links:
            groups.append(dict(heading=heading, links=links))
    if orderflow:
        groups.insert(2, dict(heading='Production & fulfilment', links=[dict(
            label=label, href=url_for('supply_chain_workspace', _anchor=tab), active=False)
            for label, tab in (
                ('Production orders', 'orders'),
                ('Workflow board', 'workflow'), ('Credit checks', 'credit'),
                ('Quality checks', 'quality'), ('Dispatches', 'dispatch'),
                ('Sales order processing', 'sales-orders'), ('Customer accounts', 'clients'),
            ) if tab not in ('sales-orders', 'clients') or core_can_for_tab(can, tab)]))
    return groups


def core_can_for_tab(can, tab):
    return can('sales_orders' if tab == 'sales-orders' else 'clients', 'view')


def supply_summary(cdb, company_id, can, today):
    """Read only authorized data; never aggregate stock quantities across units."""
    result = dict(metrics=[], low_stock=[], overdue_purchases=[])
    if can('stock', 'view'):
        stock = cdb.query(StockItem).filter(StockItem.company_id == company_id)
        low = stock.filter(StockItem.quantity <= func.coalesce(StockItem.reorder_level, 0))
        result['metrics'].extend([
            dict(label='Stock items', value=stock.count(), endpoint='inventory_list'),
            dict(label='At or below reorder level', value=low.count(), endpoint='inventory_list'),
        ])
        result['low_stock'] = low.order_by(StockItem.quantity, StockItem.id).limit(10).all()
    for model, permission, label, endpoint, closed in (
        (PurchaseOrder, 'purchase_orders', 'Open purchase orders', 'purchase_order_list', ('received', 'completed', 'closed', 'invoiced')),
        (SalesOrder, 'sales_orders', 'Open sales orders', 'sales_order_list', ('shipped', 'delivered', 'completed', 'closed', 'invoiced')),
        (DeliveryChallan, 'delivery_challans', 'Pending delivery challans', 'delivery_challan_list', ('delivered', 'completed', 'closed', 'invoiced')),
    ):
        if not can(permission, 'view'):
            continue
        query = cdb.query(model).filter(
            model.company_id == company_id,
            func.lower(func.trim(func.coalesce(model.status, ''))).notin_(
                ('', 'draft', 'cancelled', 'canceled', 'void') + closed),
        )
        result['metrics'].append(dict(label=label, value=query.count(), endpoint=endpoint))
        if model is PurchaseOrder:
            overdue = query.filter(model.expected_delivery_date < today)
            result['metrics'].append(dict(label='Overdue purchase orders', value=overdue.count(), endpoint=endpoint))
            result['overdue_purchases'] = overdue.order_by(model.expected_delivery_date, model.id).limit(10).all()
    return result


def register_supply_chain_workspace(app, login_required, get_cdb, get_current_company,
                                    has_permission, get_company, today_func=date.today):
    def module_allowed(key):
        check = app.extensions.get('module_access')
        return bool(check and check(key))

    def core_can(permission, action):
        check = app.extensions.get('module_access')
        return has_permission(permission, action) and (not check or check('orderflow'))

    def allowed():
        return bool(get_current_company() and
                    (supply_chain_allowed(core_can) or module_allowed('orderflow')))

    @app.context_processor
    def inject_supply_navigation():
        selected = (session.get('workspace_by_company') or {}).get(str(get_current_company()))
        # Keep specialist applications and finance on their own navigation.
        view = app.view_functions.get(request.endpoint)
        source = getattr(view, '__module__', '')
        excluded = request.path.startswith(('/finance', '/hr', '/crm', '/workshop', '/order-erp', '/api/'))
        show = (request.endpoint == 'supply_chain_workspace' or
                (selected == 'supply_chain' and not excluded and
                 source not in ('crm_routes', 'crm_workspace', 'workshop_routes', 'order_erp_routes', 'hr_workspace') and
                 request.endpoint not in ('apps_hub', 'select_company', 'bi_dashboard', 'bi_intelligence')))
        access = allowed() if session.get('user') else False
        return dict(can_supply_chain=access, use_supply_navigation=bool(show and access),
                    supply_navigation=supply_navigation(core_can, module_allowed('orderflow')) if show and access else [])

    @app.route('/supply-chain')
    @login_required
    def supply_chain_workspace():
        if not allowed():
            abort(403)
        company_id = get_current_company()
        data = supply_summary(get_cdb(), company_id, core_can, today_func())
        workspaces = dict(session.get('workspace_by_company') or {})
        workspaces[str(company_id)] = 'supply_chain'
        session['workspace_by_company'] = workspaces
        return render_template('supply_chain_workspace.html', active='supply_chain',
                               supply_company=get_company(company_id), data=data,
                               production_enabled=module_allowed('orderflow'),
                               user=session.get('user'),
                               status_flow=STATUS_FLOW,
                               sections=supply_navigation(core_can, module_allowed('orderflow')), can=core_can)

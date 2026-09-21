"""
order_erp_routes.py
───────────────────
Dedicated Order Management System (OrderFlow) for Qiyadah ERP.
Handles manufacturing orders, status workflow pipelines, accounts credit checks,
quality checks, partner assignment, and audit timelines.
"""

from flask import render_template, request, redirect, url_for, session, jsonify, flash
from datetime import datetime, date
import uuid
from sqlalchemy import or_, and_, desc
from customer_models import (
    OrderFlow, OrderFlowHistory, OrderDepartment, Client, Supplier, SalesOrder, SalesOrderItem, StockItem
)

STATUS_FLOW = [
    "Order Created",
    "Pending Credit Check",
    "Credit Approved",
    "Amount Pending",
    "Approved for Production",
    "In Processing",
    "Manufacturing Complete",
    "Sent for Quality Check",
    "Quality Approved",
    "Quality Check Failed",
    "Dispatched",
    "Delivered",
    "Cancelled"
]

ROLE_TYPES = {
    'admin': 'Admin',
    'owner': 'Owner',
    'super_admin': 'Super Admin',
    'sales_department': 'Sales Department',
    'accounts_department': 'Accounts Department',
    'partner_manufacturing': 'Partner / Manufacturing',
    'quality_department': 'Quality Department',
    'manager': 'Manager',
    'employee': 'Employee'
}

ROLE_VISIBLE_STATUSES = {
    'admin': STATUS_FLOW,
    'owner': STATUS_FLOW,
    'super_admin': STATUS_FLOW,
    'manager': STATUS_FLOW,
    'sales_department': STATUS_FLOW,
    'employee': STATUS_FLOW,
    'accounts_department': [
        'Order Created', 'Pending Credit Check', 'Credit Approved',
        'Amount Pending', 'Approved for Production'
    ],
    'partner_manufacturing': [
        'Approved for Production', 'In Processing',
        'Manufacturing Complete', 'Sent for Quality Check', 'Quality Check Failed'
    ],
    'quality_department': [
        'Sent for Quality Check', 'Quality Approved',
        'Quality Check Failed'
    ],
}

ROLE_TRANSITIONS = {
    'admin': {s: STATUS_FLOW for s in STATUS_FLOW},
    'owner': {s: STATUS_FLOW for s in STATUS_FLOW},
    'super_admin': {s: STATUS_FLOW for s in STATUS_FLOW},
    'manager': {s: STATUS_FLOW for s in STATUS_FLOW},
    'sales_department': {
        'Order Created': ['Pending Credit Check', 'Cancelled'],
        'Quality Approved': ['Dispatched'],
        'Dispatched': ['Delivered'],
    },
    'employee': {
        'Order Created': ['Pending Credit Check', 'Cancelled'],
        'Quality Approved': ['Dispatched'],
        'Dispatched': ['Delivered'],
    },
    'accounts_department': {
        'Pending Credit Check': ['Credit Approved', 'Amount Pending'],
        'Amount Pending': ['Credit Approved', 'Cancelled'],
        'Credit Approved': ['Approved for Production'],
    },
    'partner_manufacturing': {
        'Approved for Production': ['In Processing'],
        'In Processing': ['Manufacturing Complete'],
        'Manufacturing Complete': ['Sent for Quality Check'],
        'Quality Check Failed': ['In Processing'],
    },
    'quality_department': {
        'Sent for Quality Check': ['Quality Approved', 'Quality Check Failed'],
    },
}


def register_order_erp_routes(app, login_required, get_cdb, get_current_company, get_current_user, get_company_by_id):

    def is_owner_user():
        user = get_current_user() or {}
        return user.get('role') in ('owner', 'super_admin')

    # ── 1. MAIN ORDER ERP DASHBOARD VIEW ──────────────────────────────────────
    @app.route('/order-erp', endpoint='order_erp_view')
    @app.route('/order-erp/dashboard', endpoint='order_erp_dashboard')
    @login_required
    def order_erp_view():
        company_id = get_current_company()
        company = get_company_by_id(company_id)
        user = get_current_user()
        return render_template('order_erp.html', company=company, user=user, status_flow=STATUS_FLOW)

    # ── 2. ORDER ERP STATS ───────────────────────────────────────────────────
    @app.route('/api/order-erp/stats', methods=['GET'])
    @login_required
    def api_order_stats():
        cdb = get_cdb()
        company_id = get_current_company()
        user = get_current_user() or {}
        role = user.get('role', 'employee')
        is_owner = is_owner_user()

        base_query = cdb.query(OrderFlow).filter_by(company_id=company_id)

        # Department / role filtering for non-owners
        if not is_owner and role in ROLE_VISIBLE_STATUSES:
            visible = ROLE_VISIBLE_STATUSES[role]
            base_query = base_query.filter(OrderFlow.status.in_(visible))

        orders = base_query.all()
        total_orders = len(orders)
        active_orders = len([o for o in orders if o.status not in ('Delivered', 'Cancelled')])
        in_processing = len([o for o in orders if o.status in ('Approved for Production', 'In Processing')])
        quality_check = len([o for o in orders if o.status == 'Sent for Quality Check'])
        qc_approved   = len([o for o in orders if o.status == 'Quality Approved'])
        credit_pending= len([o for o in orders if o.status == 'Pending Credit Check'])
        dispatched    = len([o for o in orders if o.status == 'Dispatched'])
        delivered     = len([o for o in orders if o.status == 'Delivered'])
        cancelled     = len([o for o in orders if o.status == 'Cancelled'])

        total_revenue = sum(o.amount_due or 0.0 for o in orders)
        total_collected = sum(o.amount_paid or 0.0 for o in orders)
        total_pending_amount = total_revenue - total_collected

        # Sales Orders & Clients metrics
        so_query = cdb.query(SalesOrder).filter_by(company_id=company_id)
        total_sales_orders = so_query.count()
        sales_order_value = sum(so.grand_total or 0.0 for so in so_query.all())
        total_clients = cdb.query(Client).filter_by(company_id=company_id).count()

        # Recent orders
        recent_orders = [o.to_dict() for o in sorted(orders, key=lambda x: x.created_at or datetime.min, reverse=True)[:8]]

        return jsonify({
            'success': True,
            'total_orders': total_orders,
            'active_orders': active_orders,
            'in_processing': in_processing,
            'quality_check': quality_check,
            'qc_approved': qc_approved,
            'credit_pending': credit_pending,
            'dispatched': dispatched,
            'delivered': delivered,
            'cancelled': cancelled,
            'total_revenue': total_revenue,
            'total_collected': total_collected,
            'total_pending_amount': total_pending_amount,
            'total_sales_orders': total_sales_orders,
            'sales_order_value': sales_order_value,
            'total_clients': total_clients,
            'recent_orders': recent_orders,
            'is_owner': is_owner
        })

    # ── 3. LIST & CREATE ORDERS ──────────────────────────────────────────────
    @app.route('/api/order-erp/orders', methods=['GET', 'POST'])
    @login_required
    def api_order_list_create():
        cdb = get_cdb()
        company_id = get_current_company()
        user = get_current_user() or {}
        role = user.get('role', 'employee')
        is_owner = is_owner_user()

        if request.method == 'GET':
            query = cdb.query(OrderFlow).filter_by(company_id=company_id)

            status_f = request.args.get('status')
            priority_f = request.args.get('priority')
            source_f = request.args.get('source')
            search_f = request.args.get('search', '').strip().lower()

            if status_f and status_f != 'all':
                query = query.filter_by(status=status_f)
            elif not is_owner and role in ROLE_VISIBLE_STATUSES:
                query = query.filter(OrderFlow.status.in_(ROLE_VISIBLE_STATUSES[role]))

            if priority_f and priority_f != 'all':
                query = query.filter_by(priority=priority_f)

            if source_f and source_f != 'all':
                query = query.filter_by(source=source_f)

            if search_f:
                pattern = f"%{search_f}%"
                query = query.filter(
                    or_(
                        OrderFlow.id.ilike(pattern),
                        OrderFlow.client_name.ilike(pattern),
                        OrderFlow.client_phone.ilike(pattern),
                        OrderFlow.client_email.ilike(pattern),
                        OrderFlow.item_description.ilike(pattern),
                        OrderFlow.partner.ilike(pattern),
                    )
                )

            orders = query.order_by(desc(OrderFlow.created_at)).all()
            return jsonify({'success': True, 'orders': [o.to_dict() for o in orders]})

        # POST - Create New Order
        data = request.get_json() or {}
        client_name = data.get('client_name', '').strip()
        item_description = data.get('item_description', '').strip()

        if not client_name:
            return jsonify({'error': 'Client name is required'}), 400
        if not item_description:
            return jsonify({'error': 'Item description is required'}), 400

        last_order = cdb.query(OrderFlow).filter_by(company_id=company_id).order_by(desc(OrderFlow.created_at)).first()
        seq = 1001
        if last_order and last_order.id and last_order.id.startswith("ORD-"):
            try:
                seq = int(last_order.id.split('-')[1]) + 1
            except Exception:
                seq = 1001
        order_id = f"ORD-{seq}"

        quantity = int(data.get('quantity') or 1)
        unit_price = float(data.get('unit_price') or 0.0)
        amount_due = float(data.get('amount_due') or (quantity * unit_price))
        amount_paid = float(data.get('amount_paid') or 0.0)

        initial_status = data.get('status') or 'Order Created'
        if initial_status not in STATUS_FLOW:
            initial_status = 'Order Created'

        user_name = user.get('full_name') or user.get('email') or 'User'

        new_order = OrderFlow(
            id=order_id,
            company_id=company_id,
            client_id=str(data.get('client_id') or ''),
            lead_id=str(data.get('lead_id') or ''),
            client_name=client_name,
            client_phone=data.get('client_phone', '').strip(),
            client_email=data.get('client_email', '').strip(),
            item_description=item_description,
            quantity=quantity,
            unit_price=unit_price,
            amount_due=amount_due,
            amount_paid=amount_paid,
            status=initial_status,
            priority=data.get('priority', 'normal'),
            partner=data.get('partner', ''),
            source=data.get('source', 'Direct'),
            notes=data.get('notes', ''),
            internal_notes=data.get('internal_notes', ''),
            created_by=user_name,
            created_by_dept=user.get('department') or role,
            taken_by=data.get('taken_by') or user_name,
            created_at=datetime.utcnow()
        )
        cdb.add(new_order)

        # Audit History
        history = OrderFlowHistory(
            order_id=order_id,
            status=initial_status,
            note='Order initiated in system',
            changed_by=user_name,
            changed_by_dept=user.get('department') or role,
            changed_by_role=role,
            changed_at=datetime.utcnow()
        )
        cdb.add(history)
        cdb.commit()

        return jsonify({'success': True, 'message': f'Order {order_id} created successfully', 'order': new_order.to_dict()}), 201

    # ── 4. ORDER DETAIL & DELETE ─────────────────────────────────────────────
    @app.route('/api/order-erp/orders/<order_id>', methods=['GET', 'DELETE'])
    @login_required
    def api_order_detail(order_id):
        cdb = get_cdb()
        company_id = get_current_company()
        order = cdb.query(OrderFlow).filter_by(id=order_id, company_id=company_id).first()
        if not order:
            return jsonify({'error': 'Order not found'}), 404

        if request.method == 'DELETE':
            if not is_owner_user():
                return jsonify({'error': 'Only owner or administrator can delete orders'}), 403
            cdb.query(OrderFlowHistory).filter_by(order_id=order_id).delete()
            cdb.delete(order)
            cdb.commit()
            return jsonify({'success': True, 'message': f'Order {order_id} deleted successfully'})

        histories = cdb.query(OrderFlowHistory).filter_by(order_id=order_id).order_by(desc(OrderFlowHistory.changed_at)).all()
        user = get_current_user() or {}
        role = user.get('role', 'employee')
        is_owner = is_owner_user()

        available_transitions = []
        if is_owner:
            available_transitions = STATUS_FLOW
        elif role in ROLE_TRANSITIONS and order.status in ROLE_TRANSITIONS[role]:
            available_transitions = ROLE_TRANSITIONS[role][order.status]

        return jsonify({
            'success': True,
            'order': order.to_dict(),
            'history': [h.to_dict() for h in histories],
            'available_transitions': available_transitions,
            'is_owner': is_owner
        })

    # ── 5. UPDATE ORDER STATUS & WORKFLOW PROGRESSION ─────────────────────────
    @app.route('/api/order-erp/orders/<order_id>/status', methods=['PUT'])
    @login_required
    def api_order_status_update(order_id):
        cdb = get_cdb()
        company_id = get_current_company()
        order = cdb.query(OrderFlow).filter_by(id=order_id, company_id=company_id).first()
        if not order:
            return jsonify({'error': 'Order not found'}), 404

        data = request.get_json() or {}
        new_status = data.get('status')
        if not new_status or new_status not in STATUS_FLOW:
            return jsonify({'error': f'Invalid status: {new_status}'}), 400

        user = get_current_user() or {}
        role = user.get('role', 'employee')
        is_owner = is_owner_user()

        if not is_owner:
            allowed = ROLE_TRANSITIONS.get(role, {}).get(order.status, [])
            if new_status not in allowed:
                return jsonify({
                    'error': f'Role {role} is not permitted to transition from {order.status} to {new_status}'
                }), 403

        old_status = order.status
        order.status = new_status
        order.updated_at = datetime.utcnow()

        if data.get('partner'):
            order.partner = data.get('partner')
        if data.get('amount_paid') is not None:
            order.amount_paid = float(data.get('amount_paid'))
        if data.get('notes'):
            order.notes = data.get('notes')
        if data.get('internal_notes'):
            order.internal_notes = data.get('internal_notes')

        user_name = user.get('full_name') or user.get('email') or 'User'

        history = OrderFlowHistory(
            order_id=order_id,
            status=new_status,
            note=data.get('note') or f'Status transitioned from {old_status} to {new_status}',
            changed_by=user_name,
            changed_by_dept=user.get('department') or role,
            changed_by_role=role,
            payment_mode=data.get('payment_mode'),
            payment_ref=data.get('payment_ref'),
            changed_at=datetime.utcnow()
        )
        cdb.add(history)
        cdb.commit()

        return jsonify({
            'success': True,
            'message': f'Order {order_id} moved to {new_status}',
            'order': order.to_dict()
        })

    # ── 6. ACCOUNTS CREDIT CHECK WORKFLOW ────────────────────────────────────
    @app.route('/api/order-erp/orders/<order_id>/credit-check', methods=['POST'])
    @login_required
    def api_order_credit_check(order_id):
        cdb = get_cdb()
        company_id = get_current_company()
        order = cdb.query(OrderFlow).filter_by(id=order_id, company_id=company_id).first()
        if not order:
            return jsonify({'error': 'Order not found'}), 404

        data = request.get_json() or {}
        decision = data.get('decision')
        note = data.get('note', '')
        user = get_current_user() or {}
        user_name = user.get('full_name') or user.get('email') or 'Accounts'

        if decision == 'Approved':
            order.status = 'Credit Approved'
            order.approved_by = user_name
        elif decision == 'Amount Pending':
            order.status = 'Amount Pending'
            if data.get('amount_paid') is not None:
                order.amount_paid = float(data.get('amount_paid'))
        elif decision == 'Rejected':
            order.status = 'Cancelled'
        else:
            return jsonify({'error': 'Invalid credit check decision'}), 400

        order.updated_at = datetime.utcnow()

        history = OrderFlowHistory(
            order_id=order_id,
            status=order.status,
            note=f"Accounts Credit Check: {decision}. {note}".strip(),
            changed_by=user_name,
            changed_by_dept='Accounts',
            changed_by_role='accounts_department',
            payment_mode=data.get('payment_mode'),
            payment_ref=data.get('payment_ref'),
            changed_at=datetime.utcnow()
        )
        cdb.add(history)
        cdb.commit()

        return jsonify({
            'success': True,
            'message': f'Order {order_id} credit status updated to {order.status}',
            'order': order.to_dict()
        })

    # ── 7. PARTNERS LIST FOR PRODUCTION ASSIGNMENT ───────────────────────────
    @app.route('/api/order-erp/partners', methods=['GET'])
    @login_required
    def api_order_partners():
        cdb = get_cdb()
        company_id = get_current_company()
        suppliers = cdb.query(Supplier).filter_by(company_id=company_id).all()
        partner_list = [{'id': s.id, 'name': s.name, 'phone': s.phone or ''} for s in suppliers]
        if not partner_list:
            partner_list = [
                {'id': 1, 'name': 'Partner A (Internal Facility)', 'phone': ''},
                {'id': 2, 'name': 'Partner B (Assembly Works)', 'phone': ''},
                {'id': 3, 'name': 'Partner C (Express Fabrication)', 'phone': ''}
            ]
        return jsonify({'success': True, 'partners': partner_list})

    # ── 8. DEPARTMENTS MANAGEMENT ────────────────────────────────────────────
    @app.route('/api/order-erp/departments', methods=['GET', 'POST'])
    @login_required
    def api_order_departments():
        cdb = get_cdb()
        company_id = get_current_company()

        if request.method == 'POST':
            if not is_owner_user():
                return jsonify({'error': 'Only owners can manage departments'}), 403
            data = request.get_json() or {}
            dept_id = f"dept-{uuid.uuid4().hex[:8]}"
            dept = OrderDepartment(
                id=dept_id,
                company_id=company_id,
                name=data.get('name', 'New Dept'),
                role_type=data.get('role_type', 'sales_department'),
                description=data.get('description', ''),
                is_active=True,
                created_at=datetime.utcnow()
            )
            cdb.add(dept)
            cdb.commit()
            return jsonify({'success': True, 'department': dept.to_dict()})

        depts = cdb.query(OrderDepartment).filter_by(company_id=company_id, is_active=True).all()
        if not depts:
            defaults = [
                ('dept-sales', 'Sales Department', 'sales_department', 'Lead handling, initial quote and booking'),
                ('dept-acc', 'Accounts Department', 'accounts_department', 'Credit assessment and payments'),
                ('dept-prod', 'Manufacturing & Partners', 'partner_manufacturing', 'Production and repair work'),
                ('dept-qc', 'Quality Department', 'quality_department', 'Inspection and QC assurance')
            ]
            for did, dname, drole, ddesc in defaults:
                d = OrderDepartment(id=did, company_id=company_id, name=dname, role_type=drole, description=ddesc, is_active=True)
                cdb.add(d)
            cdb.commit()
            depts = cdb.query(OrderDepartment).filter_by(company_id=company_id, is_active=True).all()

        return jsonify({'success': True, 'departments': [d.to_dict() for d in depts]})

    # ── 9. SALES ORDERS API ───────────────────────────────────────────────────
    @app.route('/api/order-erp/sales-orders', methods=['GET', 'POST'])
    @login_required
    def api_sales_orders():
        cdb = get_cdb()
        company_id = get_current_company()
        user = get_current_user() or {}

        if request.method == 'GET':
            query = cdb.query(SalesOrder).filter_by(company_id=company_id)

            status_f = request.args.get('status')
            if status_f and status_f != 'all':
                query = query.filter_by(status=status_f)

            search_f = request.args.get('search', '').strip()
            if search_f:
                pattern = f"%{search_f}%"
                query = query.filter(
                    or_(
                        SalesOrder.order_no.ilike(pattern),
                        SalesOrder.client_name.ilike(pattern),
                        SalesOrder.reference_no.ilike(pattern)
                    )
                )

            orders = query.order_by(SalesOrder.order_date.desc(), SalesOrder.id.desc()).all()
            return jsonify({
                'success': True,
                'count': len(orders),
                'sales_orders': [o.to_dict() for o in orders]
            })

        # POST: Create new Sales Order
        data = request.get_json() or {}
        client_id = data.get('client_id')
        client_name = (data.get('client_name') or '').strip()

        if client_id and not client_name:
            c_rec = cdb.query(Client).filter_by(company_id=company_id, id=client_id).first()
            if c_rec:
                client_name = c_rec.name

        if not client_name and not client_id:
            return jsonify({'error': 'Client name or valid Client ID is required'}), 400

        # Auto-create or resolve Client if client_id is not given
        if not client_id:
            existing_client = cdb.query(Client).filter_by(company_id=company_id, name=client_name).first()
            if existing_client:
                client_id = existing_client.id
            else:
                new_cli = Client(
                    company_id=company_id,
                    name=client_name,
                    phone=data.get('client_phone'),
                    email=data.get('client_email'),
                    city=data.get('client_city'),
                    address_line1=data.get('client_address'),
                    gst_number=data.get('client_gst'),
                    status='Active',
                    created_at=date.today()
                )
                cdb.add(new_cli)
                cdb.flush()
                client_id = new_cli.id

        # Generate unique order_no
        count = cdb.query(SalesOrder).filter_by(company_id=company_id).count()
        order_no = f"SO-{count + 1:04d}"
        while cdb.query(SalesOrder).filter_by(company_id=company_id, order_no=order_no).first():
            count += 1
            order_no = f"SO-{count + 1:04d}"

        raw_order_date = data.get('order_date')
        order_date_val = datetime.strptime(raw_order_date, '%Y-%m-%d').date() if raw_order_date else date.today()

        raw_del_date = data.get('delivery_date')
        del_date_val = datetime.strptime(raw_del_date, '%Y-%m-%d').date() if raw_del_date else None

        items_data = data.get('items', [])
        if not items_data:
            items_data = [{'item_name': data.get('title') or 'Standard Order Item', 'quantity': 1, 'rate': float(data.get('amount') or 0)}]

        # Server-side validation and computation of totals
        subtotal = 0.0
        cgst_total = 0.0
        sgst_total = 0.0
        igst_total = 0.0

        so = SalesOrder(
            order_no=order_no,
            company_id=company_id,
            client_id=client_id,
            client_name=client_name,
            order_date=order_date_val,
            delivery_date=del_date_val,
            reference_no=data.get('reference_no', ''),
            status=data.get('status', 'Draft'),
            terms=data.get('terms', ''),
            notes=data.get('notes', ''),
            created_by=user.get('full_name') or user.get('email') or 'User',
            created_at=datetime.utcnow()
        )
        cdb.add(so)
        cdb.flush()

        for idx, it in enumerate(items_data):
            it_name = (it.get('item_name') or f"Item {idx+1}").strip()
            qty = float(it.get('quantity') or 1.0)
            rate = float(it.get('rate') or it.get('unit_price') or 0.0)
            disc_pct = float(it.get('discount_percent') or 0.0)
            gst_pct = float(it.get('gst_percent') or it.get('tax_rate') or 0.0)

            raw_amt = qty * rate
            disc_amt = raw_amt * (disc_pct / 100.0)
            taxable = raw_amt - disc_amt
            tax_val = taxable * (gst_pct / 100.0)

            # Standard split CGST & SGST
            cgst = tax_val / 2.0
            sgst = tax_val / 2.0
            igst = 0.0
            line_total = taxable + tax_val

            subtotal += taxable
            cgst_total += cgst
            sgst_total += sgst

            so_item = SalesOrderItem(
                sales_order_id=so.id,
                item_name=it_name,
                item_code=it.get('item_code', ''),
                description=it.get('description', ''),
                hsn=it.get('hsn', ''),
                quantity=qty,
                delivered_qty=0.0,
                unit=it.get('unit', 'pcs'),
                rate=rate,
                discount_percent=disc_pct,
                taxable_amount=taxable,
                gst_percent=gst_pct,
                cgst_amount=cgst,
                sgst_amount=sgst,
                igst_amount=igst,
                total_amount=line_total
            )
            cdb.add(so_item)

        so.subtotal = round(subtotal, 2)
        so.cgst_total = round(cgst_total, 2)
        so.sgst_total = round(sgst_total, 2)
        so.igst_total = round(igst_total, 2)
        so.tax_amount = round(cgst_total + sgst_total + igst_total, 2)
        so.grand_total = round(subtotal + so.tax_amount, 2)

        cdb.commit()
        return jsonify({'success': True, 'sales_order': so.to_dict()})

    @app.route('/api/order-erp/sales-orders/<int:order_id>', methods=['GET'])
    @login_required
    def api_sales_order_detail(order_id):
        cdb = get_cdb()
        company_id = get_current_company()
        so = cdb.query(SalesOrder).filter_by(id=order_id, company_id=company_id).first()
        if not so:
            return jsonify({'error': 'Sales order not found'}), 404
        return jsonify({'success': True, 'sales_order': so.to_dict()})

    @app.route('/api/order-erp/sales-orders/<int:order_id>/send-to-production', methods=['POST'])
    @login_required
    def api_sales_order_to_production(order_id):
        cdb = get_cdb()
        company_id = get_current_company()
        user = get_current_user() or {}
        so = cdb.query(SalesOrder).filter_by(id=order_id, company_id=company_id).first()
        if not so:
            return jsonify({'error': 'Sales order not found'}), 404

        # Check if an OrderFlow is already created for this SO
        existing = cdb.query(OrderFlow).filter_by(company_id=company_id, source=f"Sales Order {so.order_no}").first()
        if existing:
            return jsonify({
                'success': True,
                'already_exists': True,
                'order_flow_id': existing.id,
                'message': f"Production Order {existing.id} already exists for {so.order_no}"
            })

        # Items summary
        item_names = [f"{it.item_name} (x{int(it.quantity) if it.quantity.is_integer() else it.quantity})" for it in so.items]
        item_summary = ", ".join(item_names) if item_names else (so.notes or f"Order from {so.order_no}")
        total_qty = sum(it.quantity for it in so.items) if so.items else 1

        client = so.client_obj
        order_id_code = f"ORD-{uuid.uuid4().hex[:6].upper()}"

        order_flow = OrderFlow(
            id=order_id_code,
            company_id=company_id,
            client_id=str(so.client_id) if so.client_id else None,
            client_name=so.client_name or (client.name if client else 'Client'),
            client_phone=client.phone if client else None,
            client_email=client.email if client else None,
            item_description=item_summary,
            quantity=int(total_qty),
            unit_price=round(so.grand_total / total_qty, 2) if total_qty > 0 else so.grand_total,
            amount_due=so.grand_total,
            amount_paid=0.0,
            status='Order Created',
            priority='normal',
            source=f"Sales Order {so.order_no}",
            notes=f"Created from Sales Order {so.order_no}. Ref: {so.reference_no or 'N/A'}",
            created_by=user.get('full_name') or user.get('email') or 'User',
            created_by_dept='Sales Department',
            created_at=datetime.utcnow()
        )
        cdb.add(order_flow)

        # Record history
        hist = OrderFlowHistory(
            order_id=order_id_code,
            status='Order Created',
            note=f"Pushed to manufacturing from Sales Order {so.order_no}",
            changed_by=user.get('full_name') or user.get('email') or 'User',
            changed_by_dept='Sales Department',
            changed_by_role=user.get('role', 'sales_department'),
            changed_at=datetime.utcnow()
        )
        cdb.add(hist)

        # Update SO status
        if so.status in ('Draft', 'Submitted'):
            so.status = 'Confirmed'

        cdb.commit()
        return jsonify({
            'success': True,
            'order_flow_id': order_id_code,
            'order_flow': order_flow.to_dict(),
            'message': f"Created Production Order {order_id_code} successfully!"
        })

    # ── 10. CLIENTS MASTER API ────────────────────────────────────────────────
    @app.route('/api/order-erp/clients', methods=['GET', 'POST'])
    @login_required
    def api_order_erp_clients():
        cdb = get_cdb()
        company_id = get_current_company()

        if request.method == 'GET':
            search_f = request.args.get('search', '').strip()
            query = cdb.query(Client).filter_by(company_id=company_id)
            if search_f:
                p = f"%{search_f}%"
                query = query.filter(
                    or_(
                        Client.name.ilike(p),
                        Client.phone.ilike(p),
                        Client.email.ilike(p),
                        Client.city.ilike(p),
                        Client.gst_number.ilike(p)
                    )
                )

            clients = query.order_by(Client.name.asc()).all()
            result = []
            for c in clients:
                c_dict = c.to_dict()
                c_dict['sales_orders_count'] = cdb.query(SalesOrder).filter_by(company_id=company_id, client_id=c.id).count()
                c_dict['order_flow_count'] = cdb.query(OrderFlow).filter(
                    OrderFlow.company_id == company_id,
                    or_(OrderFlow.client_id == str(c.id), OrderFlow.client_name == c.name)
                ).count()
                result.append(c_dict)

            return jsonify({'success': True, 'count': len(result), 'clients': result})

        # POST: Create new Client
        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'Client name is required'}), 400

        cli = Client(
            company_id=company_id,
            name=name,
            contact_person=data.get('contact_person', ''),
            client_type=data.get('client_type', 'Business'),
            phone=data.get('phone', ''),
            alternate_phone=data.get('alternate_phone', ''),
            email=data.get('email', ''),
            city=data.get('city', ''),
            state=data.get('state', ''),
            address_line1=data.get('address', ''),
            gst_number=data.get('gst_number', ''),
            pan_number=data.get('pan_number', ''),
            credit_limit=float(data.get('credit_limit') or 0.0),
            notes=data.get('notes', ''),
            status='Active',
            created_at=date.today()
        )
        cdb.add(cli)
        cdb.commit()
        return jsonify({'success': True, 'client': cli.to_dict()})

    @app.route('/api/order-erp/clients/<int:client_id>/details', methods=['GET'])
    @login_required
    def api_order_erp_client_details(client_id):
        cdb = get_cdb()
        company_id = get_current_company()
        cli = cdb.query(Client).filter_by(id=client_id, company_id=company_id).first()
        if not cli:
            return jsonify({'error': 'Client not found'}), 404

        sales_orders = cdb.query(SalesOrder).filter_by(company_id=company_id, client_id=client_id).order_by(SalesOrder.order_date.desc()).all()
        order_flows = cdb.query(OrderFlow).filter(
            OrderFlow.company_id == company_id,
            or_(OrderFlow.client_id == str(client_id), OrderFlow.client_name == cli.name)
        ).order_by(OrderFlow.created_at.desc()).all()

        total_so_val = sum(so.grand_total or 0.0 for so in sales_orders)
        total_mfg_val = sum(o.amount_due or 0.0 for o in order_flows)
        total_collected = sum(o.amount_paid or 0.0 for o in order_flows)

        return jsonify({
            'success': True,
            'client': cli.to_dict(),
            'stats': {
                'total_sales_orders': len(sales_orders),
                'total_so_value': total_so_val,
                'total_mfg_orders': len(order_flows),
                'total_mfg_value': total_mfg_val,
                'total_collected': total_collected,
                'balance_due': total_mfg_val - total_collected
            },
            'sales_orders': [so.to_dict() for so in sales_orders],
            'order_flows': [o.to_dict() for o in order_flows]
        })

    # ── 11. PRODUCTS LIST API (FOR PRODUCT LOOKUP) ────────────────────────────
    @app.route('/api/order-erp/products', methods=['GET'])
    @login_required
    def api_order_erp_products():
        cdb = get_cdb()
        company_id = get_current_company()
        items = cdb.query(StockItem).filter_by(company_id=company_id).order_by(StockItem.name.asc()).all()
        return jsonify({'success': True, 'products': [it.to_dict() for it in items]})

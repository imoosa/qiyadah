"""
crm_routes.py
─────────────
Dedicated Customer Relationship Management (CRM) for Qiyadah ERP.
Includes Leads pipeline & Kanban, Customer 360° Cockpit, Contacts,
Quotations builder with order conversion, Activities/Tasks tracking,
Communication Hub, and Sales Performance Analytics.
"""

from flask import render_template, request, redirect, url_for, session, jsonify, flash
from datetime import datetime, date
import uuid
import json
from sqlalchemy import or_, and_, desc
from customer_models import (
    Client, CRMContact, CRMLead, CRMInteraction, CRMQuotation,
    CRMCommunicationLog, CRMSetting, OrderFlow, OrderFlowHistory
)

LEAD_STAGES = ["New", "Contacted", "Qualified", "Proposal Sent", "Won", "Lost"]

LEAD_STAGE_TRANSITIONS = {
    "New": ["Contacted", "Lost"],
    "Contacted": ["Qualified", "Lost"],
    "Qualified": ["Proposal Sent", "Lost"],
    "Proposal Sent": ["Won", "Lost"],
    "Won": [],
    "Lost": ["Contacted"],
}

INTERACTION_TYPES = ["call", "email", "meeting", "whatsapp", "task", "followup", "note"]
QUOTATION_STATUSES = ["Draft", "Sent", "Accepted", "Rejected"]


def register_crm_routes(app, login_required, get_cdb, get_current_company, get_current_user, get_company_by_id):

    def is_owner_user():
        user = get_current_user() or {}
        return user.get('role') in ('owner', 'super_admin')

    # ── 1. MAIN CRM WORKSPACE VIEW ───────────────────────────────────────────
    @app.route('/crm', endpoint='crm_view')
    @app.route('/crm/dashboard', endpoint='crm_dashboard')
    @login_required
    def crm_view():
        company_id = get_current_company()
        company = get_company_by_id(company_id)
        user = get_current_user()
        return render_template('crm.html', company=company, user=user, lead_stages=LEAD_STAGES)

    # ── 2. CRM DASHBOARD STATS ───────────────────────────────────────────────
    @app.route('/api/crm/dashboard', methods=['GET'])
    @login_required
    def api_crm_dashboard():
        cdb = get_cdb()
        company_id = get_current_company()
        is_owner = is_owner_user()

        leads = cdb.query(CRMLead).filter_by(company_id=company_id).all()
        total_leads = len(leads)
        won_leads = [l for l in leads if l.stage == 'Won']
        lost_leads = [l for l in leads if l.stage == 'Lost']
        active_leads = [l for l in leads if l.stage not in ('Won', 'Lost')]

        pipeline_value = sum(l.estimated_value or 0.0 for l in active_leads)
        won_revenue = sum(l.estimated_value or 0.0 for l in won_leads)

        closed_count = len(won_leads) + len(lost_leads)
        win_rate = round((len(won_leads) / closed_count * 100), 1) if closed_count > 0 else 0.0

        # Stage funnel counts
        funnel = {stage: 0 for stage in LEAD_STAGES}
        for l in leads:
            if l.stage in funnel:
                funnel[l.stage] += 1

        # Pending follow-ups
        today = date.today()
        pending_followups = cdb.query(CRMInteraction).filter(
            CRMInteraction.company_id == company_id,
            CRMInteraction.follow_up_done == False,
            CRMInteraction.follow_up_date != None
        ).order_by(CRMInteraction.follow_up_date.asc()).limit(10).all()

        recent_leads = [l.to_dict() for l in sorted(leads, key=lambda x: x.created_at or datetime.min, reverse=True)[:6]]

        return jsonify({
            'success': True,
            'total_leads': total_leads,
            'active_leads': len(active_leads),
            'won_leads': len(won_leads),
            'lost_leads': len(lost_leads),
            'pipeline_value': pipeline_value,
            'won_revenue': won_revenue,
            'win_rate': win_rate,
            'funnel': funnel,
            'pending_followups': [f.to_dict() for f in pending_followups],
            'recent_leads': recent_leads,
            'is_owner': is_owner
        })

    # ── 3. CLIENTS (CRM CUSTOMER DIRECTORY) ──────────────────────────────────
    @app.route('/api/crm/clients', methods=['GET', 'POST'])
    @login_required
    def api_crm_clients():
        cdb = get_cdb()
        company_id = get_current_company()
        user = get_current_user() or {}

        if request.method == 'GET':
            clients = cdb.query(Client).filter_by(company_id=company_id).order_by(Client.name.asc()).all()
            result = []
            for c in clients:
                contact_count = cdb.query(CRMContact).filter_by(client_id=str(c.id)).count()
                open_leads = cdb.query(CRMLead).filter(
                    CRMLead.client_id == str(c.id),
                    CRMLead.stage.notin_(['Won', 'Lost'])
                ).count()
                order_count = cdb.query(OrderFlow).filter(
                    or_(OrderFlow.client_id == str(c.id), OrderFlow.client_name == c.name)
                ).count()
                result.append({
                    'id': c.id,
                    'name': c.name,
                    'phone': c.phone or '',
                    'email': c.email or '',
                    'address': c.address_line1 or '',
                    'city': c.city or '',
                    'gst': c.gst_number or '',
                    'status': c.status or 'Active',
                    'contact_count': contact_count,
                    'open_lead_count': open_leads,
                    'order_count': order_count
                })
            return jsonify({'success': True, 'clients': result})

        # POST - create new client
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'error': 'Client name is required'}), 400

        # Check existing
        existing = cdb.query(Client).filter_by(company_id=company_id, name=name).first()
        if existing:
            return jsonify({'error': 'Client with this name already exists'}), 400

        client = Client(
            company_id=company_id,
            name=name,
            phone=data.get('phone', '').strip(),
            email=data.get('email', '').strip(),
            address_line1=data.get('address', '').strip(),
            city=data.get('city', '').strip(),
            gst_number=data.get('gst', '').strip(),
            status=data.get('status', 'Active'),
            notes=data.get('notes', ''),
            created_at=date.today()
        )
        cdb.add(client)
        cdb.commit()

        # If primary contact provided, add it
        if data.get('contact_name'):
            contact = CRMContact(
                id=f"cnt-{uuid.uuid4().hex[:8]}",
                company_id=company_id,
                client_id=str(client.id),
                name=data.get('contact_name'),
                phone=data.get('contact_phone', client.phone),
                email=data.get('contact_email', client.email),
                designation=data.get('contact_designation', 'Primary Contact'),
                is_primary=True,
                created_at=datetime.utcnow()
            )
            cdb.add(contact)
            cdb.commit()

        return jsonify({
            'success': True,
            'message': 'Client created successfully',
            'client': {
                'id': client.id,
                'name': client.name,
                'phone': client.phone,
                'email': client.email
            }
        }), 201

    # ── 4. CLIENT DETAIL, UPDATE & DELETE ────────────────────────────────────
    @app.route('/api/crm/clients/<client_id>', methods=['GET', 'PUT', 'DELETE'])
    @login_required
    def api_crm_client_detail(client_id):
        cdb = get_cdb()
        company_id = get_current_company()
        client = cdb.query(Client).filter_by(id=client_id, company_id=company_id).first()
        if not client:
            return jsonify({'error': 'Client not found'}), 404

        if request.method == 'DELETE':
            if not is_owner_user():
                return jsonify({'error': 'Only owner can delete client accounts'}), 403
            cdb.query(CRMContact).filter_by(client_id=str(client.id)).delete()
            cdb.delete(client)
            cdb.commit()
            return jsonify({'success': True, 'message': 'Client deleted successfully'})

        if request.method == 'PUT':
            data = request.get_json() or {}
            if data.get('name'):
                client.name = data.get('name').strip()
            if 'phone' in data:
                client.phone = data.get('phone', '').strip()
            if 'email' in data:
                client.email = data.get('email', '').strip()
            if 'address' in data:
                client.address_line1 = data.get('address', '').strip()
            if 'city' in data:
                client.city = data.get('city', '').strip()
            if 'gst' in data:
                client.gst_number = data.get('gst', '').strip()
            if 'status' in data:
                client.status = data.get('status')
            if 'notes' in data:
                client.notes = data.get('notes')
            cdb.commit()
            return jsonify({'success': True, 'message': 'Client updated successfully'})

        # GET
        contacts = cdb.query(CRMContact).filter_by(client_id=str(client.id)).all()
        leads = cdb.query(CRMLead).filter_by(client_id=str(client.id)).order_by(desc(CRMLead.created_at)).all()
        return jsonify({
            'success': True,
            'client': {
                'id': client.id,
                'name': client.name,
                'phone': client.phone or '',
                'email': client.email or '',
                'address': client.address_line1 or '',
                'city': client.city or '',
                'gst': client.gst_number or '',
                'status': client.status or 'Active',
                'notes': client.notes or ''
            },
            'contacts': [c.to_dict() for c in contacts],
            'leads': [l.to_dict() for l in leads]
        })

    # ── 5. CUSTOMER 360° COCKPIT ─────────────────────────────────────────────
    @app.route('/api/crm/clients/<client_id>/360', methods=['GET'])
    @login_required
    def api_crm_customer_360(client_id):
        cdb = get_cdb()
        company_id = get_current_company()
        client = cdb.query(Client).filter_by(id=client_id, company_id=company_id).first()
        if not client:
            return jsonify({'error': 'Client not found'}), 404

        contacts = cdb.query(CRMContact).filter_by(client_id=str(client.id)).all()
        leads = cdb.query(CRMLead).filter_by(client_id=str(client.id)).order_by(desc(CRMLead.created_at)).all()
        quotes = cdb.query(CRMQuotation).filter_by(client_id=str(client.id)).order_by(desc(CRMQuotation.created_at)).all()
        orders = cdb.query(OrderFlow).filter(
            or_(OrderFlow.client_id == str(client.id), OrderFlow.client_name == client.name)
        ).order_by(desc(OrderFlow.created_at)).all()
        interactions = cdb.query(CRMInteraction).filter_by(client_id=str(client.id)).order_by(desc(CRMInteraction.created_at)).all()

        total_orders_val = sum(o.amount_due or 0.0 for o in orders)
        total_paid_val   = sum(o.amount_paid or 0.0 for o in orders)
        balance_due      = total_orders_val - total_paid_val

        return jsonify({
            'success': True,
            'client': {
                'id': client.id,
                'name': client.name,
                'phone': client.phone or '',
                'email': client.email or '',
                'address': client.address_line1 or '',
                'city': client.city or '',
                'gst': client.gst_number or '',
                'status': client.status or 'Active',
                'notes': client.notes or ''
            },
            'kpis': {
                'total_leads': len(leads),
                'open_leads': len([l for l in leads if l.stage not in ('Won', 'Lost')]),
                'quotations_count': len(quotes),
                'orders_count': len(orders),
                'total_order_value': total_orders_val,
                'total_paid_value': total_paid_val,
                'balance_due': balance_due
            },
            'contacts': [c.to_dict() for c in contacts],
            'leads': [l.to_dict() for l in leads],
            'quotations': [q.to_dict() for q in quotes],
            'orders': [o.to_dict() for o in orders],
            'interactions': [i.to_dict() for i in interactions]
        })

    # ── 6. CONTACTS ──────────────────────────────────────────────────────────
    @app.route('/api/crm/contacts', methods=['GET', 'POST'])
    @login_required
    def api_crm_contacts():
        cdb = get_cdb()
        company_id = get_current_company()

        if request.method == 'GET':
            client_id = request.args.get('client_id')
            query = cdb.query(CRMContact).filter_by(company_id=company_id)
            if client_id:
                query = query.filter_by(client_id=str(client_id))
            contacts = query.order_by(CRMContact.name.asc()).all()
            return jsonify({'success': True, 'contacts': [c.to_dict() for c in contacts]})

        # POST
        data = request.get_json() or {}
        name = data.get('name', '').strip()
        client_id = str(data.get('client_id', '')).strip()

        if not name or not client_id:
            return jsonify({'error': 'Name and Client ID are required'}), 400

        contact = CRMContact(
            id=f"cnt-{uuid.uuid4().hex[:8]}",
            company_id=company_id,
            client_id=client_id,
            name=name,
            designation=data.get('designation', ''),
            phone=data.get('phone', ''),
            email=data.get('email', ''),
            is_primary=bool(data.get('is_primary', False)),
            notes=data.get('notes', ''),
            created_at=datetime.utcnow()
        )
        cdb.add(contact)
        cdb.commit()
        return jsonify({'success': True, 'contact': contact.to_dict()}), 201

    @app.route('/api/crm/contacts/<contact_id>', methods=['DELETE'])
    @login_required
    def api_crm_contact_delete(contact_id):
        cdb = get_cdb()
        company_id = get_current_company()
        contact = cdb.query(CRMContact).filter_by(id=contact_id, company_id=company_id).first()
        if not contact:
            return jsonify({'error': 'Contact not found'}), 404
        cdb.delete(contact)
        cdb.commit()
        return jsonify({'success': True, 'message': 'Contact deleted successfully'})

    # ── 7. LEADS (PIPELINE & KANBAN) ─────────────────────────────────────────
    @app.route('/api/crm/leads', methods=['GET', 'POST'])
    @login_required
    def api_crm_leads():
        cdb = get_cdb()
        company_id = get_current_company()
        user = get_current_user() or {}

        if request.method == 'GET':
            stage_f = request.args.get('stage')
            search_f = request.args.get('search', '').strip().lower()

            query = cdb.query(CRMLead).filter_by(company_id=company_id)
            if stage_f and stage_f != 'all':
                query = query.filter_by(stage=stage_f)

            if search_f:
                pattern = f"%{search_f}%"
                query = query.filter(
                    or_(
                        CRMLead.title.ilike(pattern),
                        CRMLead.client_name.ilike(pattern),
                        CRMLead.source.ilike(pattern),
                        CRMLead.assigned_to.ilike(pattern)
                    )
                )

            leads = query.order_by(desc(CRMLead.created_at)).all()
            return jsonify({'success': True, 'leads': [l.to_dict() for l in leads]})

        # POST - Create new Lead
        data = request.get_json() or {}
        title = data.get('title', '').strip()
        client_id = str(data.get('client_id', '')).strip()
        client_name = data.get('client_name', '').strip()

        if not title:
            return jsonify({'error': 'Lead title is required'}), 400

        # Resolve client_name if missing
        if client_id and not client_name:
            c = cdb.query(Client).filter_by(id=client_id).first()
            if c:
                client_name = c.name

        # If client does not exist, create client on the fly if client_name provided
        if not client_id and client_name:
            c = cdb.query(Client).filter_by(company_id=company_id, name=client_name).first()
            if not c:
                c = Client(company_id=company_id, name=client_name, phone=data.get('client_phone', ''), email=data.get('client_email', ''), created_at=date.today())
                cdb.add(c)
                cdb.commit()
            client_id = str(c.id)

        lead_id = f"lead-{uuid.uuid4().hex[:8]}"
        stage = data.get('stage', 'New')
        if stage not in LEAD_STAGES:
            stage = 'New'

        close_date = None
        if data.get('expected_close_date'):
            try:
                close_date = date.fromisoformat(data.get('expected_close_date'))
            except Exception:
                pass

        user_name = user.get('full_name') or user.get('email') or 'User'

        lead = CRMLead(
            id=lead_id,
            company_id=company_id,
            client_id=client_id or '0',
            client_name=client_name,
            title=title,
            stage=stage,
            estimated_value=float(data.get('estimated_value') or 0.0),
            source=data.get('source', 'Direct'),
            expected_close_date=close_date,
            assigned_to=data.get('assigned_to') or user_name,
            notes=data.get('notes', ''),
            created_by=user_name,
            created_at=datetime.utcnow()
        )
        cdb.add(lead)

        # Log initial touchpoint
        act = CRMInteraction(
            company_id=company_id,
            client_id=client_id or '0',
            lead_id=lead_id,
            type='note',
            title='Lead Created',
            summary=f"Lead '{title}' logged in stage '{stage}' with value ₹{lead.estimated_value:,.2f}",
            created_by=user_name,
            created_at=datetime.utcnow()
        )
        cdb.add(act)
        cdb.commit()

        return jsonify({'success': True, 'lead': lead.to_dict()}), 201

    # ── 8. LEAD DETAIL, UPDATE & STAGE TRANSITION ─────────────────────────────
    @app.route('/api/crm/leads/<lead_id>', methods=['GET', 'PUT', 'DELETE'])
    @login_required
    def api_crm_lead_detail(lead_id):
        cdb = get_cdb()
        company_id = get_current_company()
        lead = cdb.query(CRMLead).filter_by(id=lead_id, company_id=company_id).first()
        if not lead:
            return jsonify({'error': 'Lead not found'}), 404

        if request.method == 'DELETE':
            if not is_owner_user():
                return jsonify({'error': 'Only owner or admin can delete leads'}), 403
            cdb.query(CRMInteraction).filter_by(lead_id=lead_id).delete()
            cdb.delete(lead)
            cdb.commit()
            return jsonify({'success': True, 'message': 'Lead deleted successfully'})

        if request.method == 'PUT':
            data = request.get_json() or {}
            if data.get('title'):
                lead.title = data.get('title')
            if 'estimated_value' in data:
                lead.estimated_value = float(data.get('estimated_value') or 0.0)
            if 'source' in data:
                lead.source = data.get('source')
            if 'assigned_to' in data:
                lead.assigned_to = data.get('assigned_to')
            if 'notes' in data:
                lead.notes = data.get('notes')
            if 'expected_close_date' in data and data.get('expected_close_date'):
                try:
                    lead.expected_close_date = date.fromisoformat(data.get('expected_close_date'))
                except Exception:
                    pass
            lead.updated_at = datetime.utcnow()
            cdb.commit()
            return jsonify({'success': True, 'lead': lead.to_dict()})

        interactions = cdb.query(CRMInteraction).filter_by(lead_id=lead_id).order_by(desc(CRMInteraction.created_at)).all()
        return jsonify({'success': True, 'lead': lead.to_dict(), 'interactions': [i.to_dict() for i in interactions]})

    @app.route('/api/crm/leads/<lead_id>/stage', methods=['PUT'])
    @login_required
    def api_crm_lead_stage(lead_id):
        cdb = get_cdb()
        company_id = get_current_company()
        lead = cdb.query(CRMLead).filter_by(id=lead_id, company_id=company_id).first()
        if not lead:
            return jsonify({'error': 'Lead not found'}), 404

        data = request.get_json() or {}
        new_stage = data.get('stage')
        if not new_stage or new_stage not in LEAD_STAGES:
            return jsonify({'error': f'Invalid stage: {new_stage}'}), 400

        old_stage = lead.stage
        lead.stage = new_stage
        lead.updated_at = datetime.utcnow()
        if new_stage == 'Lost' and data.get('lost_reason'):
            lead.lost_reason = data.get('lost_reason')

        user = get_current_user() or {}
        user_name = user.get('full_name') or user.get('email') or 'User'

        act = CRMInteraction(
            company_id=company_id,
            client_id=lead.client_id,
            lead_id=lead_id,
            type='note',
            title=f"Stage Changed: {new_stage}",
            summary=f"Lead moved from '{old_stage}' to '{new_stage}'. Note: {data.get('note', '')}".strip(),
            created_by=user_name,
            created_at=datetime.utcnow()
        )
        cdb.add(act)
        cdb.commit()

        return jsonify({'success': True, 'message': f'Lead moved to {new_stage}', 'lead': lead.to_dict()})

    # ── 9. CONVERT WON LEAD TO ORDERFLOW ORDER ────────────────────────────────
    @app.route('/api/crm/leads/<lead_id>/convert', methods=['POST'])
    @login_required
    def api_crm_lead_convert_order(lead_id):
        cdb = get_cdb()
        company_id = get_current_company()
        lead = cdb.query(CRMLead).filter_by(id=lead_id, company_id=company_id).first()
        if not lead:
            return jsonify({'error': 'Lead not found'}), 404

        data = request.get_json() or {}
        user = get_current_user() or {}
        user_name = user.get('full_name') or user.get('email') or 'User'

        # Generate unique order id
        last_order = cdb.query(OrderFlow).filter_by(company_id=company_id).order_by(desc(OrderFlow.created_at)).first()
        seq = 1001
        if last_order and last_order.id and last_order.id.startswith("ORD-"):
            try:
                seq = int(last_order.id.split('-')[1]) + 1
            except Exception:
                seq = 1001
        order_id = f"ORD-{seq}"

        quantity = int(data.get('quantity') or 1)
        unit_price = float(data.get('unit_price') or (lead.estimated_value / max(quantity, 1) if lead.estimated_value else 0.0))
        amount_due = float(data.get('amount_due') or lead.estimated_value or (quantity * unit_price))

        order = OrderFlow(
            id=order_id,
            company_id=company_id,
            client_id=lead.client_id,
            lead_id=lead.id,
            client_name=lead.client_name or 'Valued Customer',
            item_description=data.get('item_description') or lead.title,
            quantity=quantity,
            unit_price=unit_price,
            amount_due=amount_due,
            amount_paid=float(data.get('amount_paid') or 0.0),
            status='Order Created',
            priority='normal',
            source=lead.source or 'CRM Lead',
            notes=lead.notes,
            created_by=user_name,
            taken_by=user_name,
            created_at=datetime.utcnow()
        )
        cdb.add(order)

        # Mark lead as Won and link order
        lead.stage = 'Won'
        lead.converted_order_id = order_id
        lead.updated_at = datetime.utcnow()

        # Audit History
        history = OrderFlowHistory(
            order_id=order_id,
            status='Order Created',
            note=f"Converted from Won Lead '{lead.title}' ({lead.id})",
            changed_by=user_name,
            changed_by_dept='Sales',
            changed_by_role='sales_department',
            changed_at=datetime.utcnow()
        )
        cdb.add(history)
        cdb.commit()

        return jsonify({
            'success': True,
            'message': f'Lead converted to Order {order_id}',
            'order_id': order_id,
            'order': order.to_dict()
        })

    # ── 10. ACTIVITIES & TASKS ───────────────────────────────────────────────
    @app.route('/api/crm/activities', methods=['GET', 'POST'])
    @login_required
    def api_crm_activities():
        cdb = get_cdb()
        company_id = get_current_company()
        user = get_current_user() or {}

        if request.method == 'GET':
            type_f = request.args.get('type')
            status_f = request.args.get('status')
            client_id = request.args.get('client_id')

            query = cdb.query(CRMInteraction).filter_by(company_id=company_id)
            if type_f and type_f != 'all':
                query = query.filter_by(type=type_f)
            if status_f and status_f != 'all':
                query = query.filter_by(status=status_f)
            if client_id:
                query = query.filter_by(client_id=str(client_id))

            acts = query.order_by(desc(CRMInteraction.created_at)).all()
            return jsonify({'success': True, 'activities': [a.to_dict() for a in acts]})

        # POST
        data = request.get_json() or {}
        act_type = data.get('type', 'task')
        summary = data.get('summary', '').strip()
        client_id = str(data.get('client_id', '')).strip()

        if not summary:
            return jsonify({'error': 'Activity description or summary is required'}), 400

        user_name = user.get('full_name') or user.get('email') or 'User'

        due_d = None
        if data.get('due_date'):
            try:
                due_d = date.fromisoformat(data.get('due_date'))
            except Exception:
                pass

        act = CRMInteraction(
            company_id=company_id,
            client_id=client_id or '0',
            lead_id=str(data.get('lead_id') or '') or None,
            type=act_type,
            title=data.get('title') or f"{act_type.title()}: {summary[:30]}",
            summary=summary,
            priority=data.get('priority', 'normal'),
            status='pending',
            due_date=due_d,
            follow_up_date=due_d,
            follow_up_done=False,
            created_by=user_name,
            created_at=datetime.utcnow()
        )
        cdb.add(act)
        cdb.commit()
        return jsonify({'success': True, 'activity': act.to_dict()}), 201

    @app.route('/api/crm/activities/<int:activity_id>/toggle', methods=['PUT'])
    @login_required
    def api_crm_activity_toggle(activity_id):
        cdb = get_cdb()
        company_id = get_current_company()
        act = cdb.query(CRMInteraction).filter_by(id=activity_id, company_id=company_id).first()
        if not act:
            return jsonify({'error': 'Activity not found'}), 404

        act.follow_up_done = not act.follow_up_done
        act.status = 'completed' if act.follow_up_done else 'pending'
        cdb.commit()
        return jsonify({'success': True, 'activity': act.to_dict()})

    # ── 11. QUOTATIONS & PROPOSALS ───────────────────────────────────────────
    @app.route('/api/crm/quotations', methods=['GET', 'POST'])
    @login_required
    def api_crm_quotations():
        cdb = get_cdb()
        company_id = get_current_company()
        user = get_current_user() or {}

        if request.method == 'GET':
            status_f = request.args.get('status')
            client_id = request.args.get('client_id')
            query = cdb.query(CRMQuotation).filter_by(company_id=company_id)
            if status_f and status_f != 'all':
                query = query.filter_by(status=status_f)
            if client_id:
                query = query.filter_by(client_id=str(client_id))
            quotes = query.order_by(desc(CRMQuotation.created_at)).all()
            return jsonify({'success': True, 'quotations': [q.to_dict() for q in quotes]})

        # POST
        data = request.get_json() or {}
        title = data.get('title', '').strip()
        client_id = str(data.get('client_id', '')).strip()
        client_name = data.get('client_name', '').strip()

        if not title or not client_id:
            return jsonify({'error': 'Title and Client are required'}), 400

        # Generate quote number QTE-1001
        last_q = cdb.query(CRMQuotation).filter_by(company_id=company_id).order_by(desc(CRMQuotation.created_at)).first()
        seq = 1001
        if last_q and last_q.quote_number and last_q.quote_number.startswith("QTE-"):
            try:
                seq = int(last_q.quote_number.split('-')[1]) + 1
            except Exception:
                seq = 1001
        quote_num = f"QTE-{seq}"

        items = data.get('items', [])
        subtotal = sum(float(it.get('qty', 1)) * float(it.get('rate', 0.0)) for it in items)
        tax_cgst = float(data.get('cgst') or 0.0)
        tax_sgst = float(data.get('sgst') or 0.0)
        total_amount = subtotal + tax_cgst + tax_sgst

        valid_until_d = None
        if data.get('valid_until'):
            try:
                valid_until_d = date.fromisoformat(data.get('valid_until'))
            except Exception:
                pass

        user_name = user.get('full_name') or user.get('email') or 'User'

        quote = CRMQuotation(
            id=f"quote-{uuid.uuid4().hex[:8]}",
            quote_number=quote_num,
            company_id=company_id,
            client_id=client_id,
            client_name=client_name,
            lead_id=str(data.get('lead_id') or '') or None,
            title=title,
            items_json=json.dumps(items),
            subtotal=subtotal,
            cgst=tax_cgst,
            sgst=tax_sgst,
            total_amount=total_amount,
            status=data.get('status', 'Draft'),
            valid_until=valid_until_d,
            notes=data.get('notes', ''),
            terms=data.get('terms', 'Payment within 15 days. Subject to standard warranty.'),
            created_by=user_name,
            created_at=datetime.utcnow()
        )
        cdb.add(quote)
        cdb.commit()

        return jsonify({'success': True, 'quotation': quote.to_dict()}), 201

    @app.route('/api/crm/quotations/<quote_id>', methods=['GET', 'PUT', 'DELETE'])
    @login_required
    def api_crm_quotation_detail(quote_id):
        cdb = get_cdb()
        company_id = get_current_company()
        quote = cdb.query(CRMQuotation).filter_by(id=quote_id, company_id=company_id).first()
        if not quote:
            return jsonify({'error': 'Quotation not found'}), 404

        if request.method == 'DELETE':
            if not is_owner_user():
                return jsonify({'error': 'Only owner or admin can delete quotations'}), 403
            cdb.delete(quote)
            cdb.commit()
            return jsonify({'success': True, 'message': 'Quotation deleted successfully'})

        if request.method == 'PUT':
            data = request.get_json() or {}
            if data.get('status') and data.get('status') in QUOTATION_STATUSES:
                quote.status = data.get('status')
            if 'notes' in data:
                quote.notes = data.get('notes')
            if 'terms' in data:
                quote.terms = data.get('terms')
            quote.updated_at = datetime.utcnow()
            cdb.commit()
            return jsonify({'success': True, 'quotation': quote.to_dict()})

        return jsonify({'success': True, 'quotation': quote.to_dict()})

    @app.route('/api/crm/quotations/<quote_id>/convert', methods=['POST'])
    @login_required
    def api_crm_quotation_convert(quote_id):
        cdb = get_cdb()
        company_id = get_current_company()
        quote = cdb.query(CRMQuotation).filter_by(id=quote_id, company_id=company_id).first()
        if not quote:
            return jsonify({'error': 'Quotation not found'}), 404

        user = get_current_user() or {}
        user_name = user.get('full_name') or user.get('email') or 'User'

        # Generate order id
        last_order = cdb.query(OrderFlow).filter_by(company_id=company_id).order_by(desc(OrderFlow.created_at)).first()
        seq = 1001
        if last_order and last_order.id and last_order.id.startswith("ORD-"):
            try:
                seq = int(last_order.id.split('-')[1]) + 1
            except Exception:
                seq = 1001
        order_id = f"ORD-{seq}"

        # Combine items summary
        items = []
        try:
            items = json.loads(quote.items_json) if quote.items_json else []
        except Exception:
            pass
        desc_text = ", ".join(f"{it.get('name', 'Item')} x{it.get('qty', 1)}" for it in items) if items else quote.title

        order = OrderFlow(
            id=order_id,
            company_id=company_id,
            client_id=quote.client_id,
            lead_id=quote.lead_id,
            client_name=quote.client_name or 'Customer',
            item_description=desc_text,
            quantity=1,
            unit_price=quote.total_amount,
            amount_due=quote.total_amount,
            amount_paid=0.0,
            status='Order Created',
            priority='normal',
            source='Quotation',
            notes=f"Generated from Quotation #{quote.quote_number}. {quote.notes}".strip(),
            created_by=user_name,
            taken_by=user_name,
            created_at=datetime.utcnow()
        )
        cdb.add(order)

        quote.status = 'Accepted'
        quote.converted_order_id = order_id
        quote.updated_at = datetime.utcnow()

        history = OrderFlowHistory(
            order_id=order_id,
            status='Order Created',
            note=f"Created by converting accepted Quotation {quote.quote_number}",
            changed_by=user_name,
            changed_by_dept='Sales',
            changed_by_role='sales_department',
            changed_at=datetime.utcnow()
        )
        cdb.add(history)
        cdb.commit()

        return jsonify({
            'success': True,
            'message': f'Quotation converted to Order {order_id}',
            'order_id': order_id,
            'order': order.to_dict()
        })

    # ── 12. COMMUNICATION LOGGING ────────────────────────────────────────────
    @app.route('/api/crm/communication/log', methods=['POST'])
    @login_required
    def api_crm_comm_log():
        cdb = get_cdb()
        company_id = get_current_company()
        data = request.get_json() or {}
        user = get_current_user() or {}
        user_name = user.get('full_name') or user.get('email') or 'User'

        log = CRMCommunicationLog(
            company_id=company_id,
            client_id=str(data.get('client_id', '0')),
            channel=data.get('channel', 'whatsapp'),
            recipient=data.get('recipient', ''),
            subject=data.get('subject', ''),
            message=data.get('message', ''),
            sent_by=user_name,
            status='sent',
            created_at=datetime.utcnow()
        )
        cdb.add(log)
        cdb.commit()
        return jsonify({'success': True, 'log': log.to_dict()})

    # ── 13. CRM REPORTS & ANALYTICS ──────────────────────────────────────────
    @app.route('/api/crm/reports', methods=['GET'])
    @login_required
    def api_crm_reports():
        cdb = get_cdb()
        company_id = get_current_company()

        leads = cdb.query(CRMLead).filter_by(company_id=company_id).all()
        quotes = cdb.query(CRMQuotation).filter_by(company_id=company_id).all()

        sources = {}
        for l in leads:
            s = l.source or 'Direct'
            sources[s] = sources.get(s, 0) + 1

        stage_breakdown = {}
        for s in LEAD_STAGES:
            stage_leads = [l for l in leads if l.stage == s]
            stage_breakdown[s] = {
                'count': len(stage_leads),
                'total_val': sum(l.estimated_value or 0.0 for l in stage_leads)
            }

        return jsonify({
            'success': True,
            'total_leads': len(leads),
            'source_distribution': sources,
            'stage_breakdown': stage_breakdown,
            'quotations_summary': {
                'total': len(quotes),
                'accepted': len([q for q in quotes if q.status == 'Accepted']),
                'pending': len([q for q in quotes if q.status in ('Draft', 'Sent')]),
                'total_value': sum(q.total_amount or 0.0 for q in quotes)
            }
        })

    # ── 14. CRM SETTINGS ─────────────────────────────────────────────────────
    @app.route('/api/crm/settings', methods=['GET', 'POST'])
    @login_required
    def api_crm_settings():
        cdb = get_cdb()
        company_id = get_current_company()

        if request.method == 'POST':
            if not is_owner_user():
                return jsonify({'error': 'Only owners can modify CRM settings'}), 403
            data = request.get_json() or {}
            for k, v in data.items():
                row = cdb.query(CRMSetting).filter_by(company_id=company_id, key=k).first()
                if not row:
                    row = CRMSetting(company_id=company_id, key=k, value_json=json.dumps(v))
                    cdb.add(row)
                else:
                    row.value_json = json.dumps(v)
                    row.updated_at = datetime.utcnow()
            cdb.commit()
            return jsonify({'success': True, 'message': 'CRM settings saved successfully'})

        settings_rows = cdb.query(CRMSetting).filter_by(company_id=company_id).all()
        result = {}
        for r in settings_rows:
            try:
                result[r.key] = json.loads(r.value_json)
            except Exception:
                result[r.key] = r.value_json

        return jsonify({'success': True, 'settings': result})

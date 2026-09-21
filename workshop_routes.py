"""
workshop_routes.py
──────────────────
Dedicated Automotive Workshop & Repair Management Module for Qiyadah ERP.
Supports two-wheelers, four-wheelers, EVs, and commercial fleets.
Includes Vehicle QR Code generation & camera scanning, digital job cards (JC-XXXX),
2W/4W inspection checklists, estimates & customer approval, technician tasks,
parts consumption, quality checks, delivery checklists, and service reminders.
"""

from flask import render_template, request, redirect, url_for, session, jsonify, flash, Response
from datetime import datetime, date, timedelta
import uuid
import json
import io
import qrcode
import qrcode.image.svg
from sqlalchemy import or_, and_, desc

from customer_models import (
    CustomerVehicle, WorkshopJobCard, WorkshopInspection, WorkshopEstimate,
    WorkshopEstimateItem, WorkshopTask, WorkshopPartIssue, WorkshopQualityCheck,
    VehicleServiceHistory, ServiceReminder, WorkshopVehicleServicePlan, Client, StockItem, StockPurchaseHistory,
    SupplierBrand, CustomerInvoice, CustomerInvoiceItem, WorkshopServiceCatalog
)

STATUS_FLOW = [
    "Draft",
    "Checked In",
    "Inspection Pending",
    "Estimate Prepared",
    "Awaiting Approval",
    "Approved",
    "Work In Progress",
    "Waiting for Parts",
    "Quality Check",
    "Ready for Delivery",
    "Invoiced",
    "Delivered",
    "Cancelled"
]

# Strict 5-operation General Service Checklist as requested by user
GENERAL_SERVICE_CHECKLIST = [
    {"id": "gs_greasing", "name": "Greasing", "category": "General Service", "type": "Labour", "rate": 150.0, "qty": 1.0, "checked": True, "icon": "🧴"},
    {"id": "gs_servicing", "name": "Servicing", "category": "General Service", "type": "Labour", "rate": 400.0, "qty": 1.0, "checked": True, "icon": "🔧"},
    {"id": "gs_washing", "name": "Washing", "category": "General Service", "type": "Labour", "rate": 200.0, "qty": 1.0, "checked": True, "icon": "🚿"},
    {"id": "gs_oiling", "name": "Oiling", "category": "General Service", "type": "Labour", "rate": 100.0, "qty": 1.0, "checked": True, "icon": "🛢️"},
    {"id": "gs_screw_tightening", "name": "Screw Tightening", "category": "General Service", "type": "Labour", "rate": 150.0, "qty": 1.0, "checked": True, "icon": "🔩"},
]


def deduct_product_stock_by_brand(cdb, company_id, itype, desc, brand, qty, rate, gst, jc_no, stock_item_id=None, technician=None, user_name=None):
    """
    Deducts stock from Core ERP StockItem matching the product and brand.
    Logs StockPurchaseHistory movement 'OUT' and returns the matched stock_item_id.
    Applies to types: 'Part' and 'Oil'.
    """
    if str(itype).strip().title() not in ('Part', 'Oil'):
        return None

    qty = float(qty or 0.0)
    if qty <= 0:
        return None

    stock_item = None
    if stock_item_id:
        try:
            stock_item = cdb.query(StockItem).filter_by(id=int(stock_item_id), company_id=company_id).first()
        except Exception:
            stock_item = None

    # If not matched by ID, search by description and brand in Core ERP stock items
    if not stock_item and desc:
        clean_desc = desc.strip()
        q = cdb.query(StockItem).filter(StockItem.company_id == company_id)

        # 1. First priority: match on both name/code and brand
        if brand and brand.strip():
            b_clean = brand.strip()
            stock_item = q.filter(
                StockItem.name.ilike(f"%{clean_desc}%"),
                StockItem.brand.ilike(f"%{b_clean}%")
            ).first()

            # Or if brand name is embedded in the product name (e.g. 'Castrol 10W30')
            if not stock_item:
                stock_item = q.filter(
                    StockItem.name.ilike(f"%{b_clean}%"),
                    StockItem.name.ilike(f"%{clean_desc}%")
                ).first()

        # 2. Second priority: match by description name or code
        if not stock_item:
            stock_item = q.filter(
                or_(
                    StockItem.name.ilike(f"%{clean_desc}%"),
                    StockItem.code.ilike(f"%{clean_desc}%")
                )
            ).first()

    # Deduct stock if found in Core ERP
    if stock_item:
        current_q = float(stock_item.quantity or 0.0)
        stock_item.quantity = max(0.0, current_q - qty)
        stock_item.last_updated = date.today()
        if brand and not stock_item.brand:
            stock_item.brand = brand.strip()

        movement = StockPurchaseHistory(
            stock_item_id=stock_item.id,
            quantity=-qty,
            purchase_rate=float(stock_item.purchase_rate or stock_item.unit_price or rate or 0.0),
            currency="INR",
            exchange_rate=1.0,
            base_purchase_rate=float(stock_item.purchase_rate or stock_item.unit_price or rate or 0.0),
            gst_percent=float(gst or stock_item.gst_percent or 18.0),
            purchase_date=date.today(),
            movement_type="OUT",
            reference=f"Job Card #{jc_no}"
        )
        cdb.add(movement)
        return stock_item.id

    return None


def register_workshop_routes(app, login_required, get_cdb, get_current_company, get_current_user, get_company_by_id):

    def is_owner_user():
        user = get_current_user() or {}
        return user.get('role') in ('owner', 'super_admin')

    # ──────────────────────────────────────────────────────────────────────────
    # 1. HTML VIEWS: WORKSHOP COCKPIT & VEHICLE 360° QR SCAN VIEW
    # ──────────────────────────────────────────────────────────────────────────

    @app.route('/workshop', endpoint='workshop_erp_view')
    @app.route('/workshop/dashboard', endpoint='workshop_erp_dashboard')
    @login_required
    def workshop_erp_view():
        company_id = get_current_company()
        company = get_company_by_id(company_id)
        user = get_current_user()
        return render_template('workshop_erp.html', company=company, user=user, status_flow=STATUS_FLOW)

    @app.route('/workshop/v/<string:vehicle_uuid>', endpoint='workshop_vehicle_public_view')
    def workshop_vehicle_public_view(vehicle_uuid):
        """
        Public / Internal 360° Vehicle Landing Page when scanning vehicle QR code.
        Accessible on mobile cameras / tablets / desktop.
        """
        company_id = get_current_company()
        user = get_current_user() if 'user' in session else None

        # Search across companies if unauthenticated or check current company
        cdb = None
        vehicle = None
        target_company_id = company_id

        if company_id:
            try:
                cdb = get_cdb()
                vehicle = cdb.query(CustomerVehicle).filter_by(uuid=vehicle_uuid).first()
            except Exception:
                pass

        if not vehicle:
            # Look up vehicle in platform or try active company
            # If guest scans QR code, find which tenant company this vehicle belongs to
            from platform_models import Company
            from db_router import get_customer_session
            for comp in Company.query.filter_by(is_active=True).all():
                try:
                    c_sess = get_customer_session(str(comp.company_id or comp.id))
                    v_found = c_sess.query(CustomerVehicle).filter_by(uuid=vehicle_uuid).first()
                    if v_found:
                        vehicle = v_found
                        cdb = c_sess
                        target_company_id = str(comp.company_id or comp.id)
                        company = comp
                        break
                except Exception:
                    continue
        else:
            company = get_company_by_id(target_company_id)

        if not vehicle:
            flash("Vehicle not found or invalid QR code", "danger")
            return render_template('vehicle_view.html', vehicle=None, error="Vehicle not found")

        # Load active job cards & service history
        job_cards = cdb.query(WorkshopJobCard).filter_by(vehicle_id=vehicle.id).order_by(WorkshopJobCard.created_at.desc()).all()
        history = cdb.query(VehicleServiceHistory).filter_by(vehicle_id=vehicle.id).order_by(VehicleServiceHistory.service_date.desc()).all()
        reminders = cdb.query(ServiceReminder).filter_by(vehicle_id=vehicle.id).order_by(ServiceReminder.due_date.asc()).all()

        return render_template(
            'vehicle_view.html',
            vehicle=vehicle,
            job_cards=job_cards,
            history=history,
            reminders=reminders,
            company=company,
            user=user,
            is_authenticated=bool(user)
        )

    @app.route('/workshop/v/<string:vehicle_uuid>/qr', endpoint='workshop_vehicle_qr_code')
    def workshop_vehicle_qr_code(vehicle_uuid):
        """
        Generate scalable SVG QR code for vehicle window sticker / chassis badge.
        Points to the absolute URL: /workshop/v/<vehicle_uuid>
        """
        target_url = url_for('workshop_vehicle_public_view', vehicle_uuid=vehicle_uuid, _external=True)
        img = qrcode.make(target_url, image_factory=qrcode.image.svg.SvgPathImage)
        stream = io.BytesIO()
        img.save(stream)
        stream.seek(0)
        return Response(stream.getvalue(), mimetype='image/svg+xml')

    # ──────────────────────────────────────────────────────────────────────────
    # 2. REST API: WORKSHOP STATS & METRICS
    # ──────────────────────────────────────────────────────────────────────────

    @app.route('/api/workshop/stats', methods=['GET'])
    @login_required
    def api_workshop_stats():
        try:
            cdb = get_cdb()
            company_id = get_current_company()
            if not cdb or not company_id:
                return jsonify({'success': False, 'error': 'No active company session'}), 400
            today = date.today()

            total_vehicles = cdb.query(CustomerVehicle).filter_by(company_id=company_id).count()
            all_jcs = cdb.query(WorkshopJobCard).filter_by(company_id=company_id).all()

            total_job_cards = len(all_jcs)
            active_job_cards = sum(1 for jc in all_jcs if jc.status not in ('Delivered', 'Cancelled'))
            today_checkins = sum(1 for jc in all_jcs if jc.created_at and jc.created_at.date() == today)
            ready_for_delivery = sum(1 for jc in all_jcs if jc.status == 'Ready for Delivery')
            pending_estimates = sum(1 for jc in all_jcs if jc.status in ('Inspection Pending', 'Estimate Prepared', 'Awaiting Approval'))
            today_completed = sum(1 for jc in all_jcs if jc.status == 'Delivered' and jc.updated_at and jc.updated_at.date() == today)

            today_revenue = sum(
                float(jc.grand_total or 0)
                for jc in all_jcs
                if jc.status in ('Invoiced', 'Delivered') and jc.updated_at and jc.updated_at.date() == today
            )
            total_revenue = sum(
                float(jc.grand_total or 0)
                for jc in all_jcs
                if jc.status in ('Invoiced', 'Delivered')
            )

            status_counts = {}
            for s in STATUS_FLOW:
                status_counts[s] = sum(1 for jc in all_jcs if jc.status == s)

            recent_jcs = sorted(all_jcs, key=lambda x: x.created_at or datetime.min, reverse=True)[:10]

            recent_jcs_data = []
            for jc in recent_jcs:
                try:
                    recent_jcs_data.append(jc.to_dict())
                except Exception:
                    pass

            return jsonify({
                'success': True,
                'total_vehicles': total_vehicles,
                'total_job_cards': total_job_cards,
                'active_job_cards': active_job_cards,
                'today_checkins': today_checkins,
                'ready_for_delivery': ready_for_delivery,
                'pending_estimates': pending_estimates,
                'today_completed': today_completed,
                'today_revenue': round(today_revenue, 2),
                'total_revenue': round(total_revenue, 2),
                'status_counts': status_counts,
                'recent_job_cards': recent_jcs_data
            })
        except Exception as ex:
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(ex)}), 500

    # ──────────────────────────────────────────────────────────────────────────
    # 3. REST API: VEHICLE MASTER & QR LOOKUP
    # ──────────────────────────────────────────────────────────────────────────

    @app.route('/api/workshop/vehicles', methods=['GET', 'POST'])
    @login_required
    def api_workshop_vehicles():
        cdb = get_cdb()
        company_id = get_current_company()

        if request.method == 'GET':
            search = (request.args.get('search') or '').strip()
            v_type = request.args.get('type')

            query = cdb.query(CustomerVehicle).filter_by(company_id=company_id)
            if v_type and v_type != 'All':
                query = query.filter_by(vehicle_type=v_type)

            if search:
                pat = f"%{search}%"
                query = query.filter(
                    or_(
                        CustomerVehicle.registration_no.ilike(pat),
                        CustomerVehicle.brand.ilike(pat),
                        CustomerVehicle.model.ilike(pat),
                        CustomerVehicle.vin_chassis_no.ilike(pat),
                        CustomerVehicle.engine_no.ilike(pat)
                    )
                )

            vehicles = query.order_by(CustomerVehicle.created_at.desc()).all()
            return jsonify({
                'success': True,
                'count': len(vehicles),
                'vehicles': [v.to_dict() for v in vehicles]
            })

        # POST: Register new vehicle
        data = request.get_json() or {}
        reg_no = (data.get('registration_no') or '').strip().upper()
        brand = (data.get('brand') or '').strip()
        model = (data.get('model') or '').strip()

        if not reg_no or not brand or not model:
            return jsonify({'error': 'Registration number, Brand, and Model are required'}), 400

        # Prevent duplicates within company
        existing = cdb.query(CustomerVehicle).filter_by(company_id=company_id, registration_no=reg_no).first()
        if existing:
            return jsonify({'error': f"Vehicle {reg_no} is already registered", 'vehicle': existing.to_dict()}), 400

        # Auto-resolve or create Client
        client_id = data.get('client_id')
        client_name = (data.get('client_name') or '').strip()
        client_phone = (data.get('client_phone') or '').strip()

        if not client_id and client_name:
            cli = cdb.query(Client).filter_by(company_id=company_id, name=client_name).first()
            if cli:
                client_id = cli.id
            else:
                new_cli = Client(
                    company_id=company_id,
                    name=client_name,
                    phone=client_phone,
                    email=data.get('client_email'),
                    address_line1=data.get('client_address'),
                    status='Active',
                    client_type='Customer',
                    created_at=date.today()
                )
                cdb.add(new_cli)
                cdb.flush()
                client_id = new_cli.id

        # Date helper
        def parse_d(val):
            if not val:
                return None
            try:
                return datetime.strptime(val[:10], '%Y-%m-%d').date()
            except Exception:
                return None

        v_uuid = str(uuid.uuid4())
        vehicle = CustomerVehicle(
            uuid=v_uuid,
            company_id=company_id,
            client_id=client_id,
            registration_no=reg_no,
            vehicle_type=data.get('vehicle_type', 'Four-Wheeler'),
            brand=brand,
            model=model,
            variant=data.get('variant'),
            manufacturing_year=int(data.get('manufacturing_year') or date.today().year),
            fuel_type=data.get('fuel_type', 'Petrol'),
            colour=data.get('colour'),
            vin_chassis_no=data.get('vin_chassis_no'),
            engine_no=data.get('engine_no'),
            odometer_reading=float(data.get('odometer_reading') or 0.0),
            purchase_date=parse_d(data.get('purchase_date')),
            insurance_expiry=parse_d(data.get('insurance_expiry')),
            pollution_expiry=parse_d(data.get('pollution_expiry')),
            warranty_expiry=parse_d(data.get('warranty_expiry')),
            notes=data.get('notes'),
            created_at=datetime.utcnow()
        )
        cdb.add(vehicle)
        cdb.commit()

        return jsonify({
            'success': True,
            'message': f"Vehicle {reg_no} registered successfully!",
            'vehicle': vehicle.to_dict()
        }), 201

    @app.route('/api/workshop/vehicles/<int:vehicle_id>', methods=['GET', 'PUT'])
    @login_required
    def api_workshop_vehicle_detail(vehicle_id):
        cdb = get_cdb()
        company_id = get_current_company()

        vehicle = cdb.query(CustomerVehicle).filter_by(id=vehicle_id, company_id=company_id).first()
        if not vehicle:
            return jsonify({'error': 'Vehicle not found'}), 404

        if request.method == 'GET':
            job_cards = cdb.query(WorkshopJobCard).filter_by(vehicle_id=vehicle.id).order_by(WorkshopJobCard.created_at.desc()).all()
            history = cdb.query(VehicleServiceHistory).filter_by(vehicle_id=vehicle.id).order_by(VehicleServiceHistory.service_date.desc()).all()
            reminders = cdb.query(ServiceReminder).filter_by(vehicle_id=vehicle.id).order_by(ServiceReminder.due_date.asc()).all()

            v_data = vehicle.to_dict()
            job_card_data = []
            estimates_data = []
            for jc in job_cards:
                jc_data = jc.to_dict()
                estimate = cdb.query(WorkshopEstimate).filter_by(job_card_id=jc.id).first()
                if estimate:
                    estimate_data = estimate.to_dict()
                    jc_data['estimate'] = estimate_data
                    estimate_data['job_card_no'] = jc.job_card_no
                    estimate_data['job_type'] = jc.job_type
                    estimate_data['job_card_status'] = jc.status
                    estimates_data.append(estimate_data)
                job_card_data.append(jc_data)
            v_data['job_cards'] = job_card_data
            v_data['estimates'] = estimates_data
            v_data['history'] = [h.to_dict() for h in history]
            v_data['reminders'] = [r.to_dict() for r in reminders]
            plan = cdb.query(WorkshopVehicleServicePlan).filter_by(vehicle_id=vehicle.id, company_id=company_id).first()
            default_days = 90 if 'Two' in (vehicle.vehicle_type or '') else 180
            default_km = 3000 if 'Two' in (vehicle.vehicle_type or '') else 10000
            v_data['service_plan'] = plan.to_dict() if plan else {
                'vehicle_id': vehicle.id, 'interval_days': default_days, 'interval_km': default_km
            }
            v_data['qr_url'] = url_for('workshop_vehicle_public_view', vehicle_uuid=vehicle.uuid, _external=True)
            v_data['qr_image_url'] = url_for('workshop_vehicle_qr_code', vehicle_uuid=vehicle.uuid)
            return jsonify({'success': True, 'vehicle': v_data})

        # PUT: update vehicle
        data = request.get_json() or {}
        if 'odometer_reading' in data:
            vehicle.odometer_reading = float(data['odometer_reading'] or 0.0)
        if 'colour' in data:
            vehicle.colour = data['colour']
        if 'notes' in data:
            vehicle.notes = data['notes']
        if 'insurance_expiry' in data:
            try:
                vehicle.insurance_expiry = datetime.strptime(data['insurance_expiry'][:10], '%Y-%m-%d').date()
            except Exception:
                pass
        cdb.commit()
        return jsonify({'success': True, 'message': 'Vehicle updated', 'vehicle': vehicle.to_dict()})

    @app.route('/api/workshop/vehicles/<int:vehicle_id>/service-plan', methods=['POST'])
    @login_required
    def api_workshop_vehicle_service_plan(vehicle_id):
        """Save the owner-approved service gap used for future reminders."""
        cdb = get_cdb()
        company_id = get_current_company()
        vehicle = cdb.query(CustomerVehicle).filter_by(id=vehicle_id, company_id=company_id).first()
        if not vehicle:
            return jsonify({'error': 'Vehicle not found'}), 404
        data = request.get_json() or {}
        try:
            days = max(1, int(data.get('interval_days') or 180))
            km = max(1, float(data.get('interval_km') or 10000))
        except (TypeError, ValueError):
            return jsonify({'error': 'Enter a valid service gap in days and kilometres'}), 400
        plan = cdb.query(WorkshopVehicleServicePlan).filter_by(vehicle_id=vehicle.id, company_id=company_id).first()
        if not plan:
            plan = WorkshopVehicleServicePlan(company_id=company_id, vehicle_id=vehicle.id)
            cdb.add(plan)
        plan.interval_days, plan.interval_km = days, km
        cdb.commit()
        return jsonify({'success': True, 'message': 'Service interval saved', 'service_plan': plan.to_dict()})

    # ──────────────────────────────────────────────────────────────────────────
    # 4. REST API: DIGITAL JOB CARDS & WORKFLOW
    # ──────────────────────────────────────────────────────────────────────────

    @app.route('/api/workshop/job-cards', methods=['GET', 'POST'])
    @login_required
    def api_workshop_job_cards():
        cdb = get_cdb()
        company_id = get_current_company()
        user = get_current_user() or {}

        if request.method == 'GET':
            try:
                status_filter = request.args.get('status')
                search = (request.args.get('search') or '').strip()
                v_id = request.args.get('vehicle_id')

                query = cdb.query(WorkshopJobCard).filter_by(company_id=company_id)
                if status_filter and status_filter != 'All':
                    query = query.filter_by(status=status_filter)
                if v_id:
                    query = query.filter_by(vehicle_id=int(v_id))

                if search:
                    pat = f"%{search}%"
                    query = query.join(CustomerVehicle, WorkshopJobCard.vehicle_id == CustomerVehicle.id).filter(
                        or_(
                            WorkshopJobCard.job_card_no.ilike(pat),
                            WorkshopJobCard.assigned_technician.ilike(pat),
                            CustomerVehicle.registration_no.ilike(pat)
                        )
                    )

                job_cards = query.order_by(WorkshopJobCard.created_at.desc()).all()
                jc_data = []
                for jc in job_cards:
                    try:
                        jc_data.append(jc.to_dict())
                    except Exception:
                        pass
                return jsonify({
                    'success': True,
                    'count': len(jc_data),
                    'job_cards': jc_data
                })
            except Exception as ex:
                import traceback
                traceback.print_exc()
                return jsonify({'success': False, 'error': str(ex), 'job_cards': []}), 500

        # POST: Check-in vehicle and create digital job card
        data = request.get_json() or {}
        vehicle_id = data.get('vehicle_id')
        reg_no = (data.get('registration_no') or '').strip().upper()

        if not vehicle_id and reg_no:
            veh = cdb.query(CustomerVehicle).filter_by(company_id=company_id, registration_no=reg_no).first()
            if veh:
                vehicle_id = veh.id
            else:
                # Auto register vehicle on check-in
                v_uuid = str(uuid.uuid4())
                veh = CustomerVehicle(
                    uuid=v_uuid,
                    company_id=company_id,
                    registration_no=reg_no,
                    vehicle_type=data.get('vehicle_type', 'Four-Wheeler'),
                    brand=data.get('brand', 'Standard'),
                    model=data.get('model', 'Model'),
                    fuel_type=data.get('fuel_type', 'Petrol'),
                    odometer_reading=float(data.get('current_odometer') or 0.0),
                    created_at=datetime.utcnow()
                )
                cdb.add(veh)
                cdb.flush()
                vehicle_id = veh.id

        if not vehicle_id:
            return jsonify({'error': 'Valid Vehicle or Registration Number is required'}), 400

        veh = cdb.query(CustomerVehicle).filter_by(id=vehicle_id, company_id=company_id).first()
        if not veh:
            return jsonify({'error': 'Vehicle not found'}), 404

        # Update vehicle odometer reading
        odometer = float(data.get('current_odometer') or veh.odometer_reading or 0.0)
        veh.odometer_reading = odometer

        # Generate unique Job Card No: JC-YYYY-0001
        year_str = str(date.today().year)
        count = cdb.query(WorkshopJobCard).filter_by(company_id=company_id).count()
        jc_no = f"JC-{year_str}-{count + 1:04d}"
        while cdb.query(WorkshopJobCard).filter_by(company_id=company_id, job_card_no=jc_no).first():
            count += 1
            jc_no = f"JC-{year_str}-{count + 1:04d}"

        del_date = None
        if data.get('estimated_delivery_date'):
            try:
                del_date = datetime.strptime(data['estimated_delivery_date'], '%Y-%m-%d %H:%M')
            except Exception:
                try:
                    del_date = datetime.strptime(data['estimated_delivery_date'][:10], '%Y-%m-%d')
                except Exception:
                    pass

        jc = WorkshopJobCard(
            job_card_no=jc_no,
            company_id=company_id,
            branch_id=data.get('branch_id'),
            vehicle_id=veh.id,
            client_id=veh.client_id,
            service_advisor=data.get('service_advisor') or user.get('name') or user.get('full_name') or 'Service Advisor',
            assigned_technician=data.get('assigned_technician'),
            bay_name=data.get('bay_name', 'General Bay'),
            job_type=data.get('job_type', 'General Service'),
            customer_complaints=data.get('customer_complaints'),
            initial_inspection_notes=(
                f"Requested Changes/Parts: {data.get('requested_replacements').strip()}\n{data.get('initial_inspection_notes', '')}".strip()
                if (data.get('requested_replacements') and data.get('requested_replacements').strip())
                else data.get('initial_inspection_notes')
            ),
            fuel_level=data.get('fuel_level', '50%'),
            current_odometer=odometer,
            estimated_delivery_date=del_date,
            priority=data.get('priority', 'Normal'),
            status='Inspection Pending' if (data.get('send_for_inspection') is not False) else data.get('status', 'Checked In'),
            two_wheeler_details=json.dumps(data.get('two_wheeler_details', {})) if data.get('two_wheeler_details') else None,
            four_wheeler_details=json.dumps(data.get('four_wheeler_details', {})) if data.get('four_wheeler_details') else None,
            created_by=user.get('name') or user.get('full_name') or 'Staff',
            created_at=datetime.utcnow()
        )
        cdb.add(jc)
        cdb.commit()

        return jsonify({
            'success': True,
            'message': f"Job Card {jc.job_card_no} created successfully!",
            'job_card': jc.to_dict()
        }), 201

    @app.route('/api/workshop/job-cards/<int:job_card_id>', methods=['GET', 'PUT'])
    @login_required
    def api_workshop_job_card_detail(job_card_id):
        cdb = get_cdb()
        company_id = get_current_company()

        jc = cdb.query(WorkshopJobCard).filter_by(id=job_card_id, company_id=company_id).first()
        if not jc:
            return jsonify({'error': 'Job Card not found'}), 404

        if request.method == 'GET':
            inspection = cdb.query(WorkshopInspection).filter_by(job_card_id=jc.id).first()
            estimate = cdb.query(WorkshopEstimate).filter_by(job_card_id=jc.id).first()
            tasks = cdb.query(WorkshopTask).filter_by(job_card_id=jc.id).all()
            parts = cdb.query(WorkshopPartIssue).filter_by(job_card_id=jc.id).all()
            qc = cdb.query(WorkshopQualityCheck).filter_by(job_card_id=jc.id).first()

            jc_data = jc.to_dict()
            jc_data['inspection'] = inspection.to_dict() if inspection else None
            jc_data['estimate'] = estimate.to_dict() if estimate else None
            jc_data['tasks'] = [t.to_dict() for t in tasks]
            jc_data['parts'] = [p.to_dict() for p in parts]
            jc_data['qc'] = qc.to_dict() if qc else None
            return jsonify({'success': True, 'job_card': jc_data})

        # PUT: Update job card
        data = request.get_json() or {}
        for field in ['service_advisor', 'assigned_technician', 'bay_name', 'priority', 'customer_complaints', 'initial_inspection_notes', 'fuel_level']:
            if field in data:
                setattr(jc, field, data[field])
        cdb.commit()
        return jsonify({'success': True, 'message': 'Job card updated', 'job_card': jc.to_dict()})

    @app.route('/api/workshop/job-cards/<int:job_card_id>/status', methods=['POST'])
    @login_required
    def api_workshop_job_card_status(job_card_id):
        cdb = get_cdb()
        company_id = get_current_company()

        jc = cdb.query(WorkshopJobCard).filter_by(id=job_card_id, company_id=company_id).first()
        if not jc:
            return jsonify({'error': 'Job Card not found'}), 404

        data = request.get_json() or {}
        new_status = data.get('status')
        if new_status not in STATUS_FLOW:
            return jsonify({'error': f"Invalid status: {new_status}"}), 400

        jc.status = new_status
        cdb.commit()
        return jsonify({'success': True, 'message': f"Job card status changed to {new_status}", 'job_card': jc.to_dict()})

    # ──────────────────────────────────────────────────────────────────────────
    # 5. REST API: VEHICLE INSPECTION & CHECKLISTS
    # ──────────────────────────────────────────────────────────────────────────

    @app.route('/api/workshop/checklist-templates', methods=['GET'])
    @login_required
    def api_workshop_checklist_templates():
        return jsonify({
            'success': True,
            'checklist': GENERAL_SERVICE_CHECKLIST,
            'general_service_checklist': GENERAL_SERVICE_CHECKLIST,
            'service_package': GENERAL_SERVICE_CHECKLIST
        })

    @app.route('/api/workshop/products', methods=['GET'])
    @login_required
    def api_workshop_products():
        """Returns inventory stock items from Core ERP, with auto-suggested brand and types."""
        cdb = get_cdb()
        company_id = get_current_company()

        items = cdb.query(StockItem).filter_by(company_id=company_id).order_by(StockItem.name.asc()).all()

        brands_set = set()
        for it in items:
            if it.brand and it.brand.strip():
                brands_set.add(it.brand.strip())

        try:
            sup_brands = cdb.query(SupplierBrand).all()
            for sb in sup_brands:
                if sb.brand_name and sb.brand_name.strip():
                    brands_set.add(sb.brand_name.strip())
        except Exception:
            pass

        # Standard preset brands for automotive garages
        for b in ["Castrol", "Speed", "Motul", "Shell", "Gulf", "Servo", "Mobil", "Total", "Bosch", "Minda", "TVS", "Brembo", "NGK", "Exide", "Amaron", "Ceat", "MRF", "OEM"]:
            brands_set.add(b)

        products_data = []
        for it in items:
            cat_l = (it.category or '').lower()
            name_l = (it.name or '').lower()
            suggested_type = "Oil" if any(x in cat_l or x in name_l for x in ['oil', 'lubricant', 'coolant', 'fluid']) else "Part"
            products_data.append({
                'id': it.id,
                'code': it.code,
                'name': it.name,
                'brand': it.brand or '',
                'category': it.category or '',
                'suggested_type': suggested_type,
                'quantity': float(it.quantity or 0.0),
                'unit': it.unit or 'pcs',
                'rate': float(it.selling_price or it.unit_price or 0.0),
                'gst_percent': float(it.gst_percent or 18.0)
            })

        return jsonify({
            'success': True,
            'count': len(products_data),
            'products': products_data,
            'brands': sorted(list(brands_set))
        })

    @app.route('/api/workshop/job-cards/<int:job_card_id>/inspection', methods=['GET', 'POST'])
    @login_required
    def api_workshop_job_card_inspection(job_card_id):
        cdb = get_cdb()
        company_id = get_current_company()
        user = get_current_user() or {}

        jc = cdb.query(WorkshopJobCard).filter_by(id=job_card_id, company_id=company_id).first()
        if not jc:
            return jsonify({'error': 'Job Card not found'}), 404

        if request.method == 'GET':
            insp = cdb.query(WorkshopInspection).filter_by(job_card_id=jc.id).first()
            return jsonify({'success': True, 'inspection': insp.to_dict() if insp else None})

        # POST: Save inspection findings
        data = request.get_json() or {}
        items = data.get('items', [])
        notes = data.get('notes', '')
        overall = data.get('overall_condition', 'Good')

        insp = cdb.query(WorkshopInspection).filter_by(job_card_id=jc.id).first()
        if not insp:
            insp = WorkshopInspection(
                job_card_id=jc.id,
                vehicle_id=jc.vehicle_id,
                inspector_name=user.get('name') or user.get('full_name') or 'Inspector',
                overall_condition=overall,
                checklist_json=json.dumps(items),
                notes=notes,
                created_at=datetime.utcnow()
            )
            cdb.add(insp)
        else:
            insp.overall_condition = overall
            insp.checklist_json = json.dumps(items)
            insp.notes = notes

        # If job card is in Checked In or Inspection Pending, advance to Estimate Prepared
        if jc.status in ('Checked In', 'Inspection Pending'):
            jc.status = 'Estimate Prepared'

        cdb.commit()
        return jsonify({'success': True, 'message': 'Vehicle inspection saved successfully', 'inspection': insp.to_dict()})

    # ──────────────────────────────────────────────────────────────────────────
    # 6. REST API: ESTIMATES & CUSTOMER APPROVALS
    # ──────────────────────────────────────────────────────────────────────────

    @app.route('/api/workshop/job-cards/<int:job_card_id>/estimate', methods=['GET', 'POST'])
    @login_required
    def api_workshop_job_card_estimate(job_card_id):
        cdb = get_cdb()
        company_id = get_current_company()

        jc = cdb.query(WorkshopJobCard).filter_by(id=job_card_id, company_id=company_id).first()
        if not jc:
            return jsonify({'error': 'Job Card not found'}), 404

        if request.method == 'GET':
            est = cdb.query(WorkshopEstimate).filter_by(job_card_id=jc.id).first()
            return jsonify({'success': True, 'estimate': est.to_dict() if est else None})

        # POST: Create or revise estimate
        data = request.get_json() or {}
        items_data = data.get('items', [])
        if not items_data:
            return jsonify({'error': 'At least one line item is required'}), 400

        est = cdb.query(WorkshopEstimate).filter_by(job_card_id=jc.id).first()
        if not est:
            year_str = str(date.today().year)
            count = cdb.query(WorkshopEstimate).filter_by(company_id=company_id).count()
            est_no = f"EST-{year_str}-{count + 1:04d}"
            est = WorkshopEstimate(
                estimate_no=est_no,
                job_card_id=jc.id,
                company_id=company_id,
                status='Draft',
                notes=data.get('notes', ''),
                created_at=datetime.utcnow()
            )
            cdb.add(est)
            cdb.flush()
        else:
            # Clear old items to replace with updated list
            for old_it in est.items:
                cdb.delete(old_it)
            cdb.flush()

        subtotal = 0.0
        tax_total = 0.0
        parts_subtotal = 0.0
        labour_subtotal = 0.0

        for it in items_data:
            itype = it.get('item_type', 'Part')
            desc = (it.get('description') or 'Item').strip()
            brand = (it.get('brand') or '').strip()
            qty = float(it.get('quantity') or 1.0)
            rate = float(it.get('rate') or 0.0)
            disc = float(it.get('discount_percent') or 0.0)
            gst = float(it.get('gst_percent') or 18.0)

            raw = qty * rate
            disc_amt = raw * (disc / 100.0)
            taxable = raw - disc_amt
            tax_val = taxable * (gst / 100.0)
            row_total = taxable + tax_val

            subtotal += taxable
            tax_total += tax_val
            if itype in ('Part', 'Oil'):
                parts_subtotal += taxable
            else:
                labour_subtotal += taxable

            e_item = WorkshopEstimateItem(
                estimate_id=est.id,
                item_type=itype,
                brand=brand,
                stock_item_id=it.get('stock_item_id'),
                description=desc,
                quantity=qty,
                rate=rate,
                discount_percent=disc,
                gst_percent=gst,
                total_amount=row_total
            )
            cdb.add(e_item)

        est.subtotal = round(subtotal, 2)
        est.tax_amount = round(tax_total, 2)
        est.grand_total = round(subtotal + tax_total, 2)
        est.status = 'Sent to Customer'

        jc.total_parts_amount = round(parts_subtotal, 2)
        jc.total_labour_amount = round(labour_subtotal, 2)
        jc.tax_amount = round(tax_total, 2)
        jc.grand_total = round(subtotal + tax_total, 2)
        jc.status = 'Awaiting Approval'

        cdb.commit()
        return jsonify({'success': True, 'message': 'Estimate prepared and sent for approval', 'estimate': est.to_dict()})

    @app.route('/api/workshop/job-cards/<int:job_card_id>/approve-estimate', methods=['POST'])
    @login_required
    def api_workshop_approve_estimate(job_card_id):
        cdb = get_cdb()
        company_id = get_current_company()
        user = get_current_user() or {}

        jc = cdb.query(WorkshopJobCard).filter_by(id=job_card_id, company_id=company_id).first()
        if not jc:
            return jsonify({'error': 'Job Card not found'}), 404

        est = cdb.query(WorkshopEstimate).filter_by(job_card_id=jc.id).first()
        data = request.get_json() or {}
        mode = data.get('approval_mode', 'In-Person')
        notes = data.get('notes', '')

        if not est:
            year_str = str(date.today().year)
            count = cdb.query(WorkshopEstimate).filter_by(company_id=company_id).count()
            est_no = f"EST-{year_str}-{count + 1:04d}"
            est = WorkshopEstimate(
                estimate_no=est_no,
                job_card_id=jc.id,
                company_id=company_id,
                status='Approved',
                notes=notes,
                created_at=datetime.utcnow()
            )
            cdb.add(est)
            cdb.flush()

        est.status = 'Approved'
        est.approval_mode = mode
        est.approved_by = user.get('name') or user.get('full_name') or 'Customer / Advisor'
        est.approved_at = datetime.utcnow()
        if notes:
            est.notes = f"{est.notes or ''}\nApproval note: {notes}".strip()

        # Deduct stock for all approved Part and Oil items in estimate
        for it in est.items:
            if it.item_type in ('Part', 'Oil'):
                deducted_id = deduct_product_stock_by_brand(
                    cdb=cdb,
                    company_id=company_id,
                    itype=it.item_type,
                    desc=it.description,
                    brand=it.brand,
                    qty=it.quantity,
                    rate=it.rate,
                    gst=it.gst_percent,
                    jc_no=jc.job_card_no,
                    stock_item_id=it.stock_item_id,
                    technician=jc.assigned_technician,
                    user_name=user.get('name')
                )
                # Record in WorkshopPartIssue
                issue = WorkshopPartIssue(
                    job_card_id=jc.id,
                    stock_item_id=deducted_id or it.stock_item_id,
                    item_type=it.item_type,
                    brand=it.brand,
                    part_name=f"{it.description} ({it.brand})" if (it.brand and it.brand not in it.description) else it.description,
                    quantity_requested=it.quantity,
                    quantity_issued=it.quantity,
                    quantity_consumed=it.quantity,
                    unit_cost=it.rate,
                    technician=jc.assigned_technician,
                    issued_by=user.get('name') or 'Workshop Store',
                    status='Consumed',
                    created_at=datetime.utcnow()
                )
                cdb.add(issue)

        jc.status = 'Work In Progress'
        cdb.commit()

        return jsonify({'success': True, 'message': f"Estimate {est.estimate_no} approved via {mode}! Sent for repairing (Work In Progress).", 'estimate': est.to_dict(), 'job_card': jc.to_dict()})

    @app.route('/api/workshop/job-cards/<int:job_card_id>/add-additional-item', methods=['POST'])
    @login_required
    def api_workshop_add_additional_item(job_card_id):
        """
        Step 4: Once approved and in repair, add additional parts, oil, or labor items discovered
        during mechanical disassembly, deduct stock by brand, update totals, and generate WhatsApp alert.
        """
        cdb = get_cdb()
        company_id = get_current_company()
        user = get_current_user() or {}

        jc = cdb.query(WorkshopJobCard).filter_by(id=job_card_id, company_id=company_id).first()
        if not jc:
            return jsonify({'error': 'Job Card not found'}), 404

        data = request.get_json() or {}
        itype = data.get('item_type', 'Part')
        desc = (data.get('description') or '').strip()
        brand = (data.get('brand') or '').strip()
        qty = float(data.get('quantity') or 1.0)
        rate = float(data.get('rate') or 0.0)
        gst = float(data.get('gst_percent') or 18.0)
        reason = (data.get('reason') or '').strip()
        stock_item_id = data.get('stock_item_id')

        if not desc or rate < 0:
            return jsonify({'error': 'Description and a valid rate are required'}), 400

        est = cdb.query(WorkshopEstimate).filter_by(job_card_id=jc.id).first()
        if not est:
            year_str = str(date.today().year)
            count = cdb.query(WorkshopEstimate).filter_by(company_id=company_id).count()
            est = WorkshopEstimate(
                estimate_no=f"EST-{year_str}-{count + 1:04d}",
                job_card_id=jc.id,
                company_id=company_id,
                status='Approved',
                notes='Created with additional item',
                created_at=datetime.utcnow()
            )
            cdb.add(est)
            cdb.flush()

        raw = qty * rate
        tax_val = raw * (gst / 100.0)
        row_total = raw + tax_val

        item_desc = f"{desc} [Extra: {reason}]" if reason else desc
        e_item = WorkshopEstimateItem(
            estimate_id=est.id,
            item_type=itype,
            brand=brand,
            stock_item_id=stock_item_id,
            description=item_desc,
            quantity=qty,
            rate=rate,
            discount_percent=0.0,
            gst_percent=gst,
            total_amount=row_total
        )
        cdb.add(e_item)

        est.subtotal = round((est.subtotal or 0.0) + raw, 2)
        est.tax_amount = round((est.tax_amount or 0.0) + tax_val, 2)
        est.grand_total = round((est.grand_total or 0.0) + row_total, 2)

        if itype in ('Part', 'Oil'):
            jc.total_parts_amount = round((jc.total_parts_amount or 0.0) + raw, 2)
            # Deduct stock by brand from Core ERP inventory
            deducted_stock_id = deduct_product_stock_by_brand(
                cdb=cdb,
                company_id=company_id,
                itype=itype,
                desc=desc,
                brand=brand,
                qty=qty,
                rate=rate,
                gst=gst,
                jc_no=jc.job_card_no,
                stock_item_id=stock_item_id,
                technician=jc.assigned_technician,
                user_name=user.get('name')
            )
            # Log into WorkshopPartIssue
            part_name_display = f"{desc} ({brand})" if (brand and brand not in desc) else desc
            part_issue = WorkshopPartIssue(
                job_card_id=jc.id,
                stock_item_id=deducted_stock_id or stock_item_id,
                item_type=itype,
                brand=brand,
                part_name=part_name_display,
                quantity_requested=qty,
                quantity_issued=qty,
                quantity_consumed=qty,
                unit_cost=rate,
                technician=jc.assigned_technician,
                issued_by=user.get('name') or user.get('full_name') or 'Storekeeper',
                status='Consumed',
                created_at=datetime.utcnow()
            )
            cdb.add(part_issue)
        else:
            jc.total_labour_amount = round((jc.total_labour_amount or 0.0) + raw, 2)

        jc.tax_amount = round((jc.tax_amount or 0.0) + tax_val, 2)
        jc.grand_total = round((jc.grand_total or 0.0) + row_total, 2)

        cdb.commit()

        # WhatsApp notification helper text
        veh = jc.vehicle_obj
        cli = jc.client_obj
        comp = get_company_by_id(company_id)
        comp_name = comp.company_name if comp else 'Qiyadah Workshop'
        client_phone = cli.phone if cli else (veh.client_obj.phone if (veh and veh.client_obj) else '')
        client_name = cli.name if cli else (veh.client_obj.name if (veh and veh.client_obj) else 'Customer')
        reg_no = veh.registration_no if veh else 'Vehicle'

        brand_badge = f" [Brand: {brand}]" if brand else ""
        wa_text = (
            f"⚠️ *{comp_name} - Additional Repair Update*\n"
            f"Dear *{client_name}*,\n"
            f"During the repair of your *{reg_no}*, our technician discovered additional required work:\n"
            f"• *{desc}*{brand_badge} ({itype}) - Qty: {qty} @ ₹{rate:,.2f} (+GST)\n"
            f"Reason: {reason or 'Discovered during repair inspection'}\n\n"
            f"Revised Estimate Total: *₹{jc.grand_total:,.2f}*\n"
            f"Job Card: #{jc.job_card_no}"
        )

        return jsonify({
            'success': True,
            'message': f"Additional item '{desc}' added to Job Card #{jc.job_card_no}!",
            'item': e_item.to_dict(),
            'job_card': jc.to_dict(),
            'estimate': est.to_dict(),
            'whatsapp_phone': client_phone,
            'whatsapp_message': wa_text
        })

    # ──────────────────────────────────────────────────────────────────────────
    # 7. REST API: TECHNICIAN TASKS & TIME TRACKING
    # ──────────────────────────────────────────────────────────────────────────

    @app.route('/api/workshop/job-cards/<int:job_card_id>/tasks', methods=['GET', 'POST'])
    @login_required
    def api_workshop_tasks(job_card_id):
        cdb = get_cdb()
        company_id = get_current_company()

        jc = cdb.query(WorkshopJobCard).filter_by(id=job_card_id, company_id=company_id).first()
        if not jc:
            return jsonify({'error': 'Job Card not found'}), 404

        if request.method == 'GET':
            tasks = cdb.query(WorkshopTask).filter_by(job_card_id=jc.id).all()
            return jsonify({'success': True, 'tasks': [t.to_dict() for t in tasks]})

        data = request.get_json() or {}
        name = (data.get('task_name') or '').strip()
        if not name:
            return jsonify({'error': 'Task name is required'}), 400

        task = WorkshopTask(
            job_card_id=jc.id,
            task_name=name,
            assigned_technician=data.get('assigned_technician') or jc.assigned_technician or 'Unassigned',
            status='Pending',
            notes=data.get('notes')
        )
        cdb.add(task)
        cdb.commit()
        return jsonify({'success': True, 'message': 'Task added', 'task': task.to_dict()}), 201

    @app.route('/api/workshop/tasks/<int:task_id>/status', methods=['POST'])
    @login_required
    def api_workshop_update_task_status(task_id):
        cdb = get_cdb()
        data = request.get_json() or {}
        new_status = data.get('status')
        task = cdb.query(WorkshopTask).filter_by(id=task_id).first()
        if not task:
            return jsonify({'error': 'Task not found'}), 404

        task.status = new_status
        if new_status == 'In Progress' and not task.start_time:
            task.start_time = datetime.utcnow()
        elif new_status == 'Completed':
            task.end_time = datetime.utcnow()
        cdb.commit()
        return jsonify({'success': True, 'task': task.to_dict()})

    # ──────────────────────────────────────────────────────────────────────────
    # 8. REST API: SPARE PARTS REQUISITION & INVENTORY CONSUMPTION
    # ──────────────────────────────────────────────────────────────────────────

    @app.route('/api/workshop/job-cards/<int:job_card_id>/parts-issue', methods=['GET', 'POST'])
    @login_required
    def api_workshop_parts_issue(job_card_id):
        cdb = get_cdb()
        company_id = get_current_company()
        user = get_current_user() or {}

        jc = cdb.query(WorkshopJobCard).filter_by(id=job_card_id, company_id=company_id).first()
        if not jc:
            return jsonify({'error': 'Job Card not found'}), 404

        if request.method == 'GET':
            issues = cdb.query(WorkshopPartIssue).filter_by(job_card_id=jc.id).all()
            return jsonify({'success': True, 'parts': [p.to_dict() for p in issues]})

        data = request.get_json() or {}
        part_name = (data.get('part_name') or '').strip()
        qty = float(data.get('quantity') or 1.0)
        stock_id = data.get('stock_item_id')

        if not part_name:
            return jsonify({'error': 'Part name is required'}), 400

        # Check stock item if given
        stock_item = None
        if stock_id:
            stock_item = cdb.query(StockItem).filter_by(id=stock_id, company_id=company_id).first()
            if stock_item and stock_item.current_stock is not None:
                stock_item.current_stock = max(0.0, stock_item.current_stock - qty)

        issue = WorkshopPartIssue(
            job_card_id=jc.id,
            stock_item_id=stock_id,
            part_name=part_name,
            quantity_requested=qty,
            quantity_issued=qty,
            quantity_consumed=qty,
            unit_cost=float(data.get('unit_cost') or 0.0),
            technician=data.get('technician') or jc.assigned_technician,
            issued_by=user.get('name') or user.get('full_name') or 'Storekeeper',
            status='Issued',
            created_at=datetime.utcnow()
        )
        cdb.add(issue)
        cdb.commit()

        return jsonify({'success': True, 'message': f"Part {part_name} issued successfully!", 'part': issue.to_dict()}), 201

    # ──────────────────────────────────────────────────────────────────────────
    # 9. REST API: QUALITY CHECK (QC SUPERVISOR)
    # ──────────────────────────────────────────────────────────────────────────

    @app.route('/api/workshop/job-cards/<int:job_card_id>/qc', methods=['GET', 'POST'])
    @login_required
    def api_workshop_qc(job_card_id):
        cdb = get_cdb()
        company_id = get_current_company()
        user = get_current_user() or {}

        jc = cdb.query(WorkshopJobCard).filter_by(id=job_card_id, company_id=company_id).first()
        if not jc:
            return jsonify({'error': 'Job Card not found'}), 404

        if request.method == 'GET':
            qc = cdb.query(WorkshopQualityCheck).filter_by(job_card_id=jc.id).first()
            return jsonify({'success': True, 'qc': qc.to_dict() if qc else None})

        data = request.get_json() or {}
        qc_status = data.get('status', 'Passed')  # Passed, Failed, Rework Required
        rework_notes = data.get('rework_notes', '')

        qc = cdb.query(WorkshopQualityCheck).filter_by(job_card_id=jc.id).first()
        if not qc:
            qc = WorkshopQualityCheck(
                job_card_id=jc.id,
                inspector=user.get('name') or user.get('full_name') or 'QC Supervisor',
                status=qc_status,
                rework_notes=rework_notes,
                checklist_json=json.dumps(data.get('items', [])),
                verified_at=datetime.utcnow()
            )
            cdb.add(qc)
        else:
            qc.inspector = user.get('name') or user.get('full_name') or 'QC Supervisor'
            qc.status = qc_status
            qc.rework_notes = rework_notes
            qc.checklist_json = json.dumps(data.get('items', []))
            qc.verified_at = datetime.utcnow()

        if qc_status == 'Passed':
            jc.status = 'Ready for Delivery'
        elif qc_status in ('Failed', 'Rework Required'):
            jc.status = 'Work In Progress'

        cdb.commit()
        return jsonify({'success': True, 'message': f"Quality check marked as {qc_status}!", 'qc': qc.to_dict(), 'job_card': jc.to_dict()})

    # ──────────────────────────────────────────────────────────────────────────
    # 10. REST API: TAX INVOICING & DELIVERY COMPLETION
    # ──────────────────────────────────────────────────────────────────────────

    @app.route('/api/workshop/job-cards/<int:job_card_id>/invoice', methods=['POST'])
    @login_required
    def api_workshop_create_invoice(job_card_id):
        cdb = get_cdb()
        company_id = get_current_company()
        user = get_current_user() or {}

        jc = cdb.query(WorkshopJobCard).filter_by(id=job_card_id, company_id=company_id).first()
        if not jc:
            return jsonify({'error': 'Job Card not found'}), 404

        est = cdb.query(WorkshopEstimate).filter_by(job_card_id=jc.id).first()
        veh = jc.vehicle_obj
        cli = jc.client_obj

        # A workshop job card owns one Sales Invoice.  On re-generation, update
        # that invoice in place so its number, payment history, and external
        # references remain valid instead of creating a duplicate invoice.
        inv = None
        if jc.invoice_id:
            inv = cdb.query(CustomerInvoice).filter_by(
                id=jc.invoice_id, company_id=company_id
            ).first()
        was_existing_invoice = inv is not None

        if inv:
            cdb.query(CustomerInvoiceItem).filter_by(
                customer_invoice_id=inv.id
            ).delete(synchronize_session=False)
            inv.client_id = jc.client_id
            inv.client_name = cli.name if cli else inv.client_name
            inv.invoice_date = date.today()
            inv.due_date = date.today()
            inv.terms = (
                f"Vehicle Service: {veh.registration_no if veh else ''} "
                f"({veh.brand if veh else ''} {veh.model if veh else ''}) "
                f"- Job Card {jc.job_card_no}"
            )
            inv.notes = jc.customer_complaints
            inv.updated_by = user.get('name') or user.get('full_name') or 'Staff'
        else:
            # Generate invoice numbering only for the job card's first invoice.
            year_str = str(date.today().year)
            inv_count = cdb.query(CustomerInvoice).filter_by(company_id=company_id).count()
            inv_no = f"INV-WS-{year_str}-{inv_count + 1:04d}"
            while cdb.query(CustomerInvoice).filter_by(
                company_id=company_id, invoice_number=inv_no
            ).first():
                inv_count += 1
                inv_no = f"INV-WS-{year_str}-{inv_count + 1:04d}"

            inv = CustomerInvoice(
                invoice_number=inv_no,
                company_id=company_id,
                client_id=jc.client_id,
                client_name=cli.name if cli else None,
                invoice_date=date.today(),
                due_date=date.today(),
                paid_amount=0.0,
                terms=(
                    f"Vehicle Service: {veh.registration_no if veh else ''} "
                    f"({veh.brand if veh else ''} {veh.model if veh else ''}) "
                    f"- Job Card {jc.job_card_no}"
                ),
                notes=jc.customer_complaints,
                created_by=user.get('name') or user.get('full_name') or 'Staff',
                created_at=datetime.utcnow()
            )
            cdb.add(inv)
            cdb.flush()

        # Add line items from estimate or default
        new_items = []
        subtotal = 0.0
        cgst_total = 0.0
        sgst_total = 0.0
        igst_total = 0.0

        if est and est.items:
            for it in est.items:
                raw_amount = float(it.quantity or 0.0) * float(it.rate or 0.0)
                discount_amount = raw_amount * (float(it.discount_percent or 0.0) / 100.0)
                taxable_amount = round(raw_amount - discount_amount, 2)
                tax_amount = round(taxable_amount * (float(it.gst_percent or 0.0) / 100.0), 2)
                # Workshop invoices are domestic GST invoices.  Split GST into
                # CGST/SGST so the item and invoice totals stay consistent.
                cgst_amount = round(tax_amount / 2.0, 2)
                sgst_amount = round(tax_amount - cgst_amount, 2)
                total_amount = round(taxable_amount + tax_amount, 2)
                inv_item = CustomerInvoiceItem(
                    customer_invoice_id=inv.id,
                    stock_item_id=it.stock_item_id,
                    item_name=it.description,
                    item_description=f"[{it.item_type}] {it.description}",
                    quantity=it.quantity,
                    rate=it.rate,
                    discount_percent=it.discount_percent,
                    gst_percent=it.gst_percent,
                    taxable_amount=taxable_amount,
                    cgst_amount=cgst_amount,
                    sgst_amount=sgst_amount,
                    total_amount=total_amount
                )
                cdb.add(inv_item)
                new_items.append(inv_item)
                subtotal += taxable_amount
                cgst_total += cgst_amount
                sgst_total += sgst_amount
        else:
            subtotal = round(float(jc.grand_total or 0.0) - float(jc.tax_amount or 0.0), 2)
            tax_amount = round(float(jc.tax_amount or 0.0), 2)
            cgst_total = round(tax_amount / 2.0, 2)
            sgst_total = round(tax_amount - cgst_total, 2)
            inv_item = CustomerInvoiceItem(
                customer_invoice_id=inv.id,
                item_name=f"Workshop Service ({jc.job_type})",
                quantity=1.0,
                rate=subtotal,
                taxable_amount=subtotal,
                cgst_amount=cgst_total,
                sgst_amount=sgst_total,
                total_amount=round(subtotal + tax_amount, 2)
            )
            cdb.add(inv_item)
            new_items.append(inv_item)

        inv.subtotal = round(subtotal, 2)
        inv.cgst_total = round(cgst_total, 2)
        inv.sgst_total = round(sgst_total, 2)
        inv.igst_total = round(igst_total, 2)
        inv.tax_amount = round(cgst_total + sgst_total + igst_total, 2)
        inv.grand_total = round(inv.subtotal + inv.tax_amount, 2)
        inv.base_subtotal = inv.subtotal
        inv.base_tax_amount = inv.tax_amount
        inv.base_grand_total = inv.grand_total
        inv.balance = round(max(0.0, inv.grand_total - inv.paid_amount), 2)
        inv.status = 'Paid' if inv.balance <= 0.01 else ('Partially Paid' if inv.paid_amount else 'Pending')

        jc.invoice_id = inv.id
        jc.status = 'Invoiced'
        cdb.commit()

        inv_data = {
            'id': inv.id,
            'invoice_number': inv.invoice_number,
            'invoice_date': inv.invoice_date.strftime('%d-%b-%Y') if inv.invoice_date else '',
            'grand_total': float(inv.grand_total or 0.0),
            'tax_amount': float(inv.tax_amount or 0.0),
            'subtotal': float(inv.subtotal or 0.0),
            'status': inv.status,
            'items': [{
                'item_name': it.item_name,
                'item_description': it.item_description,
                'quantity': float(it.quantity or 1.0),
                'rate': float(it.rate or 0.0),
                'total_amount': float(it.total_amount or 0.0)
            } for it in inv.items]
        }

        return jsonify({
            'success': True,
            'message': f"Invoice {inv.invoice_number} {'updated' if was_existing_invoice else 'generated'} successfully!",
            'invoice_id': inv.id,
            'invoice_number': inv.invoice_number,
            'invoice': inv_data,
            'job_card': jc.to_dict()
        })

    @app.route('/api/workshop/job-cards/<int:job_card_id>/deliver', methods=['POST'])
    @login_required
    def api_workshop_deliver_vehicle(job_card_id):
        cdb = get_cdb()
        company_id = get_current_company()

        jc = cdb.query(WorkshopJobCard).filter_by(id=job_card_id, company_id=company_id).first()
        if not jc:
            return jsonify({'error': 'Job Card not found'}), 404

        veh = jc.vehicle_obj
        data = request.get_json() or {}
        final_odo = float(data.get('final_odometer') or jc.current_odometer or 0.0)

        jc.status = 'Delivered'
        if veh:
            veh.odometer_reading = final_odo

        # Settle invoice payment if invoice exists
        payment_mode = data.get('payment_mode', 'Cash')
        paid_amount = float(data.get('amount_paid') or jc.grand_total or 0.0)
        if jc.invoice_id:
            inv = cdb.query(CustomerInvoice).filter_by(id=jc.invoice_id, company_id=company_id).first()
            if inv:
                inv.paid_amount = min(inv.grand_total, (inv.paid_amount or 0.0) + paid_amount)
                inv.balance = max(0.0, inv.grand_total - inv.paid_amount)
                if inv.balance <= 0.01:
                    inv.status = 'Paid'
                else:
                    inv.status = 'Partially Paid'

        # Record permanent vehicle service history
        summary = f"{jc.job_type}: {jc.customer_complaints or 'Routine service performed'}"
        service_plan = cdb.query(WorkshopVehicleServicePlan).filter_by(vehicle_id=jc.vehicle_id, company_id=company_id).first()
        next_due_days = service_plan.interval_days if service_plan else (90 if (veh and 'Two' in veh.vehicle_type) else 180)
        next_due_date = date.today() + timedelta(days=next_due_days)
        next_due_odo = final_odo + (service_plan.interval_km if service_plan else (3000 if (veh and 'Two' in veh.vehicle_type) else 10000))

        history = VehicleServiceHistory(
            vehicle_id=jc.vehicle_id,
            job_card_id=jc.id,
            service_date=date.today(),
            odometer=final_odo,
            services_performed=summary,
            technician=jc.assigned_technician,
            invoice_amount=jc.grand_total,
            next_service_due_date=next_due_date,
            next_service_due_odometer=next_due_odo
        )
        cdb.add(history)

        # Create automated next service reminder
        reminder = ServiceReminder(
            company_id=company_id,
            vehicle_id=jc.vehicle_id,
            client_id=jc.client_id,
            reminder_type='Next Periodic Service',
            due_date=next_due_date,
            due_odometer=next_due_odo,
            status='Pending',
            notes=f"Periodic service due after Job Card {jc.job_card_no}"
        )
        cdb.add(reminder)
        cdb.commit()

        return jsonify({
            'success': True,
            'message': f"Vehicle {veh.registration_no if veh else ''} marked as Delivered! Service history updated and next service reminder scheduled.",
            'job_card': jc.to_dict(),
            'next_service_due_date': next_due_date.strftime('%Y-%m-%d')
        })

    @app.route('/workshop/job-cards/<int:job_card_id>/bill', endpoint='workshop_job_card_bill_view')
    def workshop_job_card_bill_view(job_card_id):
        """
        Public / Printable Digital Bill & Tax Invoice for customer WhatsApp link and printing.
        """
        cdb = None
        jc = None
        target_company = None

        company_id = get_current_company()
        if company_id:
            try:
                cdb = get_cdb()
                jc = cdb.query(WorkshopJobCard).filter_by(id=job_card_id).first()
                if jc:
                    target_company = get_company_by_id(company_id)
            except Exception:
                pass

        if not jc:
            from platform_models import Company
            from db_router import get_customer_session
            for comp in Company.query.filter_by(is_active=True).all():
                try:
                    c_sess = get_customer_session(str(comp.company_id or comp.id))
                    found = c_sess.query(WorkshopJobCard).filter_by(id=job_card_id).first()
                    if found:
                        jc = found
                        cdb = c_sess
                        target_company = comp
                        break
                except Exception:
                    continue

        if not jc:
            return "Job Card or Bill not found", 404

        veh = jc.vehicle_obj
        cli = jc.client_obj
        est = cdb.query(WorkshopEstimate).filter_by(job_card_id=jc.id).first()
        insp = cdb.query(WorkshopInspection).filter_by(job_card_id=jc.id).first()
        qc = cdb.query(WorkshopQualityCheck).filter_by(job_card_id=jc.id).first()

        inv = None
        if jc.invoice_id:
            inv = cdb.query(CustomerInvoice).filter_by(id=jc.invoice_id).first()

        return render_template(
            'workshop_bill.html',
            jc=jc,
            vehicle=veh,
            client=cli,
            estimate=est,
            inspection=insp,
            qc=qc,
            invoice=inv,
            company=target_company
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 10b. REST API: SERVICE CATALOG (user-defined, editable service packages)
    # ──────────────────────────────────────────────────────────────────────────

    @app.route('/api/workshop/service-catalog', methods=['GET', 'POST'])
    @login_required
    def api_workshop_service_catalog():
        cdb = get_cdb()
        company_id = get_current_company()

        if request.method == 'GET':
            rows = cdb.query(WorkshopServiceCatalog).filter_by(company_id=company_id, is_active=True).order_by(WorkshopServiceCatalog.name.asc()).all()
            return jsonify({'success': True, 'services': [r.to_dict() for r in rows]})

        data = request.get_json() or {}
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'Service name is required'}), 400

        svc = WorkshopServiceCatalog(
            company_id=company_id,
            name=name,
            amount=float(data.get('amount') or 0.0),
            inclusions=(data.get('inclusions') or '').strip(),
            gst_percent=float(data.get('gst_percent') or 18.0)
        )
        cdb.add(svc)
        cdb.commit()
        return jsonify({'success': True, 'service': svc.to_dict()}), 201

    @app.route('/api/workshop/service-catalog/<int:svc_id>', methods=['PUT', 'DELETE'])
    @login_required
    def api_workshop_service_catalog_item(svc_id):
        cdb = get_cdb()
        company_id = get_current_company()
        svc = cdb.query(WorkshopServiceCatalog).filter_by(id=svc_id, company_id=company_id).first()
        if not svc:
            return jsonify({'error': 'Service not found'}), 404

        if request.method == 'DELETE':
            svc.is_active = False   # soft delete — keeps history on old bills intact
            cdb.commit()
            return jsonify({'success': True})

        data = request.get_json() or {}
        svc.name = (data.get('name') or svc.name).strip()
        svc.amount = float(data.get('amount') if data.get('amount') is not None else svc.amount)
        svc.inclusions = data.get('inclusions', svc.inclusions)
        svc.gst_percent = float(data.get('gst_percent') if data.get('gst_percent') is not None else svc.gst_percent)
        cdb.commit()
        return jsonify({'success': True, 'service': svc.to_dict()})

    # ──────────────────────────────────────────────────────────────────────────
    # 11. REST API: SERVICE REMINDERS
    # ──────────────────────────────────────────────────────────────────────────

    @app.route('/api/workshop/reminders', methods=['GET', 'POST'])
    @login_required
    def api_workshop_reminders():
        cdb = get_cdb()
        company_id = get_current_company()

        if request.method == 'GET':
            reminders = cdb.query(ServiceReminder).filter_by(company_id=company_id).order_by(ServiceReminder.due_date.asc()).all()
            return jsonify({'success': True, 'count': len(reminders), 'reminders': [r.to_dict() for r in reminders]})

        data = request.get_json() or {}
        veh_id = data.get('vehicle_id')
        due_str = data.get('due_date')
        if not veh_id or not due_str:
            return jsonify({'error': 'Vehicle and due date are required'}), 400

        try:
            due_d = datetime.strptime(due_str[:10], '%Y-%m-%d').date()
        except Exception:
            due_d = date.today() + timedelta(days=90)

        rem = ServiceReminder(
            company_id=company_id,
            vehicle_id=veh_id,
            client_id=data.get('client_id'),
            reminder_type=data.get('reminder_type', 'Next Periodic Service'),
            due_date=due_d,
            due_odometer=float(data.get('due_odometer') or 0.0),
            status='Pending',
            notes=data.get('notes')
        )
        cdb.add(rem)
        cdb.commit()
        return jsonify({'success': True, 'message': 'Service reminder created', 'reminder': rem.to_dict()}), 201

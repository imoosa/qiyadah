"""
erp_routes.py
Standard Business ERP Routes for Qiyadah ERP:
- Delivery Challans (Dispatch / Delivery Notes)
- Sales Orders (Customer Orders)
- Purchase Orders (Supplier Orders)
- 1-Click Conversion between Quotes, Sales Orders, Challans, and Invoices
"""

from flask import render_template, request, redirect, url_for, session, flash, jsonify, abort
from datetime import date, datetime
from sqlalchemy import text, func, or_
from customer_models import (
    Client, Supplier, StockItem,
    DeliveryChallan, DeliveryChallanItem,
    SalesOrder, SalesOrderItem,
    PurchaseOrder, PurchaseOrderItem,
    CustomerInvoice, CustomerInvoiceItem,
    PurchaseInvoice, PurchaseInvoiceItem
)
from platform_models import Company


def register_erp_routes(app, login_required, require_permission, get_cdb, get_current_company, resolve_user_names):

    # 1. DELIVERY CHALLANS
    @app.route("/delivery-challans")
    @login_required
    @require_permission("delivery_challans", "view")
    def delivery_challan_list():
        cdb = get_cdb()
        company_id = get_current_company()
        status_filter = request.args.get("status", "All")
        search_query = request.args.get("q", "").strip()
        query = cdb.query(DeliveryChallan).filter_by(company_id=company_id)

        if status_filter != "All":
            query = query.filter_by(status=status_filter)

        if search_query:
            query = query.filter(
                or_(
                    DeliveryChallan.challan_no.ilike(f"%{search_query}%"),
                    DeliveryChallan.client_name.ilike(f"%{search_query}%"),
                    DeliveryChallan.vehicle_no.ilike(f"%{search_query}%"),
                    DeliveryChallan.reference_order_no.ilike(f"%{search_query}%"),
                )
            )

        challans = query.order_by(DeliveryChallan.challan_date.desc(), DeliveryChallan.id.desc()).all()
        return render_template(
            "delivery_challan_list.html",
            challans=challans,
            current_status=status_filter,
            current_search=search_query,
            active="delivery_challans"
        )

    @app.route("/delivery-challan/new", methods=["GET", "POST"])
    @login_required
    @require_permission("delivery_challans", "create")
    def delivery_challan_new():
        cdb = get_cdb()
        company_id = get_current_company()
        company = Company.query.filter_by(company_id=company_id).first()

        if request.method == "GET":
            count = cdb.query(DeliveryChallan).filter_by(company_id=company_id).count()
            default_challan_no = f"DC-{count + 1:04d}"
            while cdb.query(DeliveryChallan).filter_by(company_id=company_id, challan_no=default_challan_no).first():
                count += 1
                default_challan_no = f"DC-{count + 1:04d}"

            clients = cdb.query(Client).filter_by(company_id=company_id).order_by(Client.name.asc()).all()
            stock_items = cdb.query(StockItem).filter_by(company_id=company_id).order_by(StockItem.name.asc()).all()
            prefill_client_id = request.args.get("client_id", "")
            prefill_client_name = request.args.get("client_name", "")
            prefill_ref_order = request.args.get("ref_order", "")

            return render_template(
                "delivery_challan_form.html",
                is_edit=False,
                challan=None,
                default_challan_no=default_challan_no,
                today_date=date.today().strftime("%Y-%m-%d"),
                company=company,
                clients=clients,
                stock_items=stock_items,
                prefill_client_id=prefill_client_id,
                prefill_client_name=prefill_client_name,
                prefill_ref_order=prefill_ref_order,
                active="delivery_challans"
            )

        challan_no = request.form.get("challan_no", "").strip()
        client_id_val = request.form.get("client_id")
        client_id = int(client_id_val) if client_id_val and client_id_val.isdigit() else None
        client_name = request.form.get("client_name", "").strip()

        challan_date_str = request.form.get("challan_date")
        challan_date = datetime.strptime(challan_date_str, "%Y-%m-%d").date() if challan_date_str else date.today()

        delivery_date_str = request.form.get("delivery_date")
        delivery_date = datetime.strptime(delivery_date_str, "%Y-%m-%d").date() if delivery_date_str else None

        challan = DeliveryChallan(
            challan_no=challan_no,
            company_id=company_id,
            client_id=client_id,
            client_name=client_name,
            challan_date=challan_date,
            delivery_date=delivery_date,
            reference_order_no=request.form.get("reference_order_no", "").strip(),
            challan_type=request.form.get("challan_type", "Delivery on Sale"),
            transporter_name=request.form.get("transporter_name", "").strip(),
            vehicle_no=request.form.get("vehicle_no", "").strip(),
            lr_no=request.form.get("lr_no", "").strip(),
            dispatch_from=request.form.get("dispatch_from", "").strip(),
            shipping_address=request.form.get("shipping_address", "").strip(),
            status=request.form.get("status", "Dispatched"),
            stock_deducted=bool(request.form.get("stock_deducted")),
            terms=request.form.get("terms", "").strip(),
            notes=request.form.get("notes", "").strip(),
            created_by=session.get("user", {}).get("email", "System"),
        )
        cdb.add(challan)
        cdb.flush()

        item_names = request.form.getlist("item_name[]")
        item_codes = request.form.getlist("item_code[]")
        item_hsns = request.form.getlist("item_hsn[]")
        item_qtys = request.form.getlist("item_qty[]")
        item_units = request.form.getlist("item_unit[]")
        item_rates = request.form.getlist("item_rate[]")
        item_discs = request.form.getlist("item_discount[]")
        item_gsts = request.form.getlist("item_gst[]")
        item_stock_ids = request.form.getlist("item_stock_id[]")

        subtotal = 0.0
        tax_amount = 0.0

        for i in range(len(item_names)):
            name = item_names[i].strip() if i < len(item_names) else ""
            if not name:
                continue

            qty = float(item_qtys[i]) if i < len(item_qtys) and item_qtys[i] else 1.0
            rate = float(item_rates[i]) if i < len(item_rates) and item_rates[i] else 0.0
            disc_pct = float(item_discs[i]) if i < len(item_discs) and item_discs[i] else 0.0
            gst_pct = float(item_gsts[i]) if i < len(item_gsts) and item_gsts[i] else 0.0
            hsn = item_hsns[i].strip() if i < len(item_hsns) else ""
            unit = item_units[i].strip() if i < len(item_units) else "pcs"
            code = item_codes[i].strip() if i < len(item_codes) else ""
            s_id = int(item_stock_ids[i]) if i < len(item_stock_ids) and item_stock_ids[i] and item_stock_ids[i].isdigit() else None

            base = qty * rate
            disc = (base * disc_pct) / 100.0
            taxable = max(0.0, base - disc)
            tax = (taxable * gst_pct) / 100.0
            line_total = taxable + tax

            cgst = tax / 2.0
            sgst = tax / 2.0
            igst = 0.0

            subtotal += taxable
            tax_amount += tax

            ch_item = DeliveryChallanItem(
                challan_id=challan.id,
                stock_item_id=s_id,
                item_code=code,
                item_name=name,
                hsn=hsn,
                quantity=qty,
                unit=unit,
                rate=rate,
                discount_percent=disc_pct,
                taxable_amount=taxable,
                gst_percent=gst_pct,
                cgst_amount=cgst,
                sgst_amount=sgst,
                igst_amount=igst,
                total_amount=line_total,
            )
            cdb.add(ch_item)

            if challan.stock_deducted and challan.status in ["Dispatched", "Delivered"]:
                stock_item = None
                if s_id:
                    stock_item = cdb.query(StockItem).filter_by(id=s_id, company_id=company_id).first()
                elif name:
                    stock_item = cdb.query(StockItem).filter_by(name=name, company_id=company_id).first()

                if stock_item:
                    stock_item.quantity = max(0.0, (stock_item.quantity or 0.0) - qty)

        challan.subtotal = subtotal
        challan.tax_amount = tax_amount
        challan.grand_total = subtotal + tax_amount

        cdb.commit()
        flash(f"Delivery Challan {challan.challan_no} created successfully!", "success")
        return redirect(url_for("delivery_challan_view", challan_id=challan.id))

    @app.route("/delivery-challan/<int:challan_id>")
    @login_required
    @require_permission("delivery_challans", "view")
    def delivery_challan_view(challan_id):
        cdb = get_cdb()
        company_id = get_current_company()
        company = Company.query.filter_by(company_id=company_id).first()
        challan = cdb.query(DeliveryChallan).filter_by(id=challan_id, company_id=company_id).first_or_404()

        company_logo_url = None
        if company and company.logo_filename:
            company_logo_url = url_for("static", filename=f"company_logos/{company.logo_filename}")

        return render_template(
            "delivery_challan_view.html",
            challan=challan,
            company=company,
            company_logo_url=company_logo_url,
            active="delivery_challans"
        )

    @app.route("/delivery-challan/<int:challan_id>/edit", methods=["GET", "POST"])
    @login_required
    @require_permission("delivery_challans", "edit")
    def delivery_challan_edit(challan_id):
        cdb = get_cdb()
        company_id = get_current_company()
        company = Company.query.filter_by(company_id=company_id).first()
        challan = cdb.query(DeliveryChallan).filter_by(id=challan_id, company_id=company_id).first_or_404()

        if request.method == "GET":
            clients = cdb.query(Client).filter_by(company_id=company_id).order_by(Client.name.asc()).all()
            stock_items = cdb.query(StockItem).filter_by(company_id=company_id).order_by(StockItem.name.asc()).all()

            return render_template(
                "delivery_challan_form.html",
                is_edit=True,
                challan=challan,
                company=company,
                clients=clients,
                stock_items=stock_items,
                active="delivery_challans"
            )

        challan.challan_no = request.form.get("challan_no", challan.challan_no).strip()
        client_id_val = request.form.get("client_id")
        challan.client_id = int(client_id_val) if client_id_val and client_id_val.isdigit() else None
        challan.client_name = request.form.get("client_name", "").strip()

        challan_date_str = request.form.get("challan_date")
        if challan_date_str:
            challan.challan_date = datetime.strptime(challan_date_str, "%Y-%m-%d").date()

        delivery_date_str = request.form.get("delivery_date")
        challan.delivery_date = datetime.strptime(delivery_date_str, "%Y-%m-%d").date() if delivery_date_str else None

        challan.reference_order_no = request.form.get("reference_order_no", "").strip()
        challan.challan_type = request.form.get("challan_type", "Delivery on Sale")
        challan.transporter_name = request.form.get("transporter_name", "").strip()
        challan.vehicle_no = request.form.get("vehicle_no", "").strip()
        challan.lr_no = request.form.get("lr_no", "").strip()
        challan.dispatch_from = request.form.get("dispatch_from", "").strip()
        challan.shipping_address = request.form.get("shipping_address", "").strip()
        challan.status = request.form.get("status", "Dispatched")
        challan.terms = request.form.get("terms", "").strip()
        challan.notes = request.form.get("notes", "").strip()
        challan.updated_by = session.get("user", {}).get("email", "System")

        for it in list(challan.items):
            cdb.delete(it)
        cdb.flush()

        item_names = request.form.getlist("item_name[]")
        item_codes = request.form.getlist("item_code[]")
        item_hsns = request.form.getlist("item_hsn[]")
        item_qtys = request.form.getlist("item_qty[]")
        item_units = request.form.getlist("item_unit[]")
        item_rates = request.form.getlist("item_rate[]")
        item_discs = request.form.getlist("item_discount[]")
        item_gsts = request.form.getlist("item_gst[]")
        item_stock_ids = request.form.getlist("item_stock_id[]")

        subtotal = 0.0
        tax_amount = 0.0

        for i in range(len(item_names)):
            name = item_names[i].strip() if i < len(item_names) else ""
            if not name:
                continue

            qty = float(item_qtys[i]) if i < len(item_qtys) and item_qtys[i] else 1.0
            rate = float(item_rates[i]) if i < len(item_rates) and item_rates[i] else 0.0
            disc_pct = float(item_discs[i]) if i < len(item_discs) and item_discs[i] else 0.0
            gst_pct = float(item_gsts[i]) if i < len(item_gsts) and item_gsts[i] else 0.0
            hsn = item_hsns[i].strip() if i < len(item_hsns) else ""
            unit = item_units[i].strip() if i < len(item_units) else "pcs"
            code = item_codes[i].strip() if i < len(item_codes) else ""
            s_id = int(item_stock_ids[i]) if i < len(item_stock_ids) and item_stock_ids[i] and item_stock_ids[i].isdigit() else None

            base = qty * rate
            disc = (base * disc_pct) / 100.0
            taxable = max(0.0, base - disc)
            tax = (taxable * gst_pct) / 100.0
            line_total = taxable + tax

            cgst = tax / 2.0
            sgst = tax / 2.0
            igst = 0.0

            subtotal += taxable
            tax_amount += tax

            ch_item = DeliveryChallanItem(
                challan_id=challan.id,
                stock_item_id=s_id,
                item_code=code,
                item_name=name,
                hsn=hsn,
                quantity=qty,
                unit=unit,
                rate=rate,
                discount_percent=disc_pct,
                taxable_amount=taxable,
                gst_percent=gst_pct,
                cgst_amount=cgst,
                sgst_amount=sgst,
                igst_amount=igst,
                total_amount=line_total,
            )
            cdb.add(ch_item)

        challan.subtotal = subtotal
        challan.tax_amount = tax_amount
        challan.grand_total = subtotal + tax_amount

        cdb.commit()
        flash(f"Delivery Challan {challan.challan_no} updated successfully!", "success")
        return redirect(url_for("delivery_challan_view", challan_id=challan.id))

    @app.route("/delivery-challan/<int:challan_id>/pdf")
    @login_required
    def delivery_challan_pdf(challan_id):
        cdb = get_cdb()
        company_id = get_current_company()
        company = Company.query.filter_by(company_id=company_id).first()
        challan = cdb.query(DeliveryChallan).filter_by(id=challan_id, company_id=company_id).first_or_404()
        return render_template("delivery_challan_pdf.html", challan=challan, company=company)

    @app.route("/delivery-challan/<int:challan_id>/convert-to-invoice")
    @login_required
    @require_permission("customer_invoices", "create")
    def delivery_challan_convert_to_invoice(challan_id):
        cdb = get_cdb()
        company_id = get_current_company()
        challan = cdb.query(DeliveryChallan).filter_by(id=challan_id, company_id=company_id).first_or_404()

        count = cdb.query(CustomerInvoice).filter_by(company_id=company_id).count()
        inv_no = f"INV-{count + 1:04d}"
        while cdb.query(CustomerInvoice).filter_by(company_id=company_id, invoice_number=inv_no).first():
            count += 1
            inv_no = f"INV-{count + 1:04d}"

        cust_inv = CustomerInvoice(
            invoice_number=inv_no,
            company_id=company_id,
            client_id=challan.client_id or 0,
            client_name=challan.client_name or (challan.client_obj.name if challan.client_obj else "Direct Customer"),
            invoice_date=date.today(),
            due_date=date.today(),
            invoice_type="credit" if challan.client_id else "cash",
            status="Pending",
            subtotal=challan.subtotal,
            tax_amount=challan.tax_amount,
            cgst_total=challan.tax_amount / 2.0,
            sgst_total=challan.tax_amount / 2.0,
            igst_total=0.0,
            grand_total=challan.grand_total,
            paid_amount=0.0,
            balance=challan.grand_total,
            notes=f"Generated from Delivery Challan: {challan.challan_no}",
            created_by=session.get("user", {}).get("email", "System"),
        )
        cdb.add(cust_inv)
        cdb.flush()

        for item in challan.items:
            ci_item = CustomerInvoiceItem(
                customer_invoice_id=cust_inv.id,
                booking_invoice_id=challan.id,
                booking_invoice_ref=challan.challan_no,
                docket_no=challan.challan_no,
                receiver_name=challan.client_name,
                destination=challan.shipping_address,
                item_description=item.item_name,
                quantity=item.quantity,
                rate_per_kg=item.rate,
                taxable_amount=item.taxable_amount,
                gst_percent=item.gst_percent,
                cgst_amount=item.cgst_amount,
                sgst_amount=item.sgst_amount,
                igst_amount=item.igst_amount,
                total_amount=item.total_amount,
                booking_date=challan.challan_date,
            )
            cdb.add(ci_item)

        challan.status = "Invoiced"
        challan.invoiced_invoice_id = cust_inv.id
        cdb.commit()
        flash(f"Delivery Challan {challan.challan_no} converted to Tax Invoice {cust_inv.invoice_number}!", "success")
        return redirect(url_for("customer_invoice_view", cust_inv_id=cust_inv.id))

    @app.route("/delivery-challan/<int:challan_id>/delete", methods=["POST"])
    @login_required
    @require_permission("delivery_challans", "delete")
    def delivery_challan_delete(challan_id):
        cdb = get_cdb()
        company_id = get_current_company()
        challan = cdb.query(DeliveryChallan).filter_by(id=challan_id, company_id=company_id).first_or_404()
        ch_no = challan.challan_no
        cdb.delete(challan)
        cdb.commit()
        flash(f"Delivery Challan {ch_no} deleted successfully.", "info")
        return redirect(url_for("delivery_challan_list"))


    # 2. SALES ORDERS
    @app.route("/sales-orders")
    @login_required
    @require_permission("sales_orders", "view")
    def sales_order_list():
        cdb = get_cdb()
        company_id = get_current_company()
        status_filter = request.args.get("status", "All")
        search_query = request.args.get("q", "").strip()
        query = cdb.query(SalesOrder).filter_by(company_id=company_id)

        if status_filter != "All":
            query = query.filter_by(status=status_filter)

        if search_query:
            query = query.filter(
                or_(
                    SalesOrder.order_no.ilike(f"%{search_query}%"),
                    SalesOrder.client_name.ilike(f"%{search_query}%"),
                    SalesOrder.reference_no.ilike(f"%{search_query}%"),
                )
            )

        orders = query.order_by(SalesOrder.order_date.desc(), SalesOrder.id.desc()).all()
        return render_template(
            "sales_order_list.html",
            orders=orders,
            current_status=status_filter,
            current_search=search_query,
            active="sales_orders"
        )

    @app.route("/sales-order/new", methods=["GET", "POST"])
    @login_required
    @require_permission("sales_orders", "create")
    def sales_order_new():
        cdb = get_cdb()
        company_id = get_current_company()
        company = Company.query.filter_by(company_id=company_id).first()

        if request.method == "GET":
            count = cdb.query(SalesOrder).filter_by(company_id=company_id).count()
            default_order_no = f"SO-{count + 1:04d}"
            while cdb.query(SalesOrder).filter_by(company_id=company_id, order_no=default_order_no).first():
                count += 1
                default_order_no = f"SO-{count + 1:04d}"

            clients = cdb.query(Client).filter_by(company_id=company_id).order_by(Client.name.asc()).all()
            stock_items = cdb.query(StockItem).filter_by(company_id=company_id).order_by(StockItem.name.asc()).all()
            prefill_client_id = request.args.get("client_id", "")
            prefill_client_name = request.args.get("client_name", "")

            return render_template(
                "sales_order_form.html",
                is_edit=False,
                order=None,
                default_order_no=default_order_no,
                today_date=date.today().strftime("%Y-%m-%d"),
                company=company,
                clients=clients,
                stock_items=stock_items,
                prefill_client_id=prefill_client_id,
                prefill_client_name=prefill_client_name,
                active="sales_orders"
            )

        order_no = request.form.get("order_no", "").strip()
        client_id_val = request.form.get("client_id")
        client_id = int(client_id_val) if client_id_val and client_id_val.isdigit() else None
        client_name = request.form.get("client_name", "").strip()

        order_date_str = request.form.get("order_date")
        order_date = datetime.strptime(order_date_str, "%Y-%m-%d").date() if order_date_str else date.today()

        delivery_date_str = request.form.get("delivery_date")
        delivery_date = datetime.strptime(delivery_date_str, "%Y-%m-%d").date() if delivery_date_str else None

        so = SalesOrder(
            order_no=order_no,
            company_id=company_id,
            client_id=client_id,
            client_name=client_name,
            order_date=order_date,
            delivery_date=delivery_date,
            reference_no=request.form.get("reference_no", "").strip(),
            status=request.form.get("status", "Confirmed"),
            terms=request.form.get("terms", "").strip(),
            notes=request.form.get("notes", "").strip(),
            created_by=session.get("user", {}).get("email", "System"),
        )
        cdb.add(so)
        cdb.flush()

        item_names = request.form.getlist("item_name[]")
        item_codes = request.form.getlist("item_code[]")
        item_hsns = request.form.getlist("item_hsn[]")
        item_qtys = request.form.getlist("item_qty[]")
        item_units = request.form.getlist("item_unit[]")
        item_rates = request.form.getlist("item_rate[]")
        item_discs = request.form.getlist("item_discount[]")
        item_gsts = request.form.getlist("item_gst[]")
        item_stock_ids = request.form.getlist("item_stock_id[]")

        subtotal = 0.0
        tax_amount = 0.0

        for i in range(len(item_names)):
            name = item_names[i].strip() if i < len(item_names) else ""
            if not name:
                continue

            qty = float(item_qtys[i]) if i < len(item_qtys) and item_qtys[i] else 1.0
            rate = float(item_rates[i]) if i < len(item_rates) and item_rates[i] else 0.0
            disc_pct = float(item_discs[i]) if i < len(item_discs) and item_discs[i] else 0.0
            gst_pct = float(item_gsts[i]) if i < len(item_gsts) and item_gsts[i] else 0.0
            hsn = item_hsns[i].strip() if i < len(item_hsns) else ""
            unit = item_units[i].strip() if i < len(item_units) else "pcs"
            code = item_codes[i].strip() if i < len(item_codes) else ""
            s_id = int(item_stock_ids[i]) if i < len(item_stock_ids) and item_stock_ids[i] and item_stock_ids[i].isdigit() else None

            base = qty * rate
            disc = (base * disc_pct) / 100.0
            taxable = max(0.0, base - disc)
            tax = (taxable * gst_pct) / 100.0
            line_total = taxable + tax

            cgst = tax / 2.0
            sgst = tax / 2.0
            igst = 0.0

            subtotal += taxable
            tax_amount += tax

            so_item = SalesOrderItem(
                sales_order_id=so.id,
                stock_item_id=s_id,
                item_code=code,
                item_name=name,
                description="",
                hsn=hsn,
                quantity=qty,
                delivered_qty=0.0,
                unit=unit,
                rate=rate,
                discount_percent=disc_pct,
                taxable_amount=taxable,
                gst_percent=gst_pct,
                cgst_amount=cgst,
                sgst_amount=sgst,
                igst_amount=igst,
                total_amount=line_total,
            )
            cdb.add(so_item)

        so.subtotal = subtotal
        so.tax_amount = tax_amount
        so.cgst_total = tax_amount / 2.0
        so.sgst_total = tax_amount / 2.0
        so.igst_total = 0.0
        so.grand_total = subtotal + tax_amount

        cdb.commit()
        flash(f"Sales Order {so.order_no} created successfully!", "success")
        return redirect(url_for("sales_order_view", order_id=so.id))

    @app.route("/sales-order/<int:order_id>")
    @login_required
    @require_permission("sales_orders", "view")
    def sales_order_view(order_id):
        cdb = get_cdb()
        company_id = get_current_company()
        company = Company.query.filter_by(company_id=company_id).first()
        order = cdb.query(SalesOrder).filter_by(id=order_id, company_id=company_id).first_or_404()

        company_logo_url = None
        if company and company.logo_filename:
            company_logo_url = url_for("static", filename=f"company_logos/{company.logo_filename}")

        return render_template(
            "sales_order_view.html",
            order=order,
            company=company,
            company_logo_url=company_logo_url,
            active="sales_orders"
        )

    @app.route("/sales-order/<int:order_id>/edit", methods=["GET", "POST"])
    @login_required
    @require_permission("sales_orders", "edit")
    def sales_order_edit(order_id):
        cdb = get_cdb()
        company_id = get_current_company()
        company = Company.query.filter_by(company_id=company_id).first()
        order = cdb.query(SalesOrder).filter_by(id=order_id, company_id=company_id).first_or_404()

        if request.method == "GET":
            clients = cdb.query(Client).filter_by(company_id=company_id).order_by(Client.name.asc()).all()
            stock_items = cdb.query(StockItem).filter_by(company_id=company_id).order_by(StockItem.name.asc()).all()

            return render_template(
                "sales_order_form.html",
                is_edit=True,
                order=order,
                company=company,
                clients=clients,
                stock_items=stock_items,
                active="sales_orders"
            )

        order.order_no = request.form.get("order_no", order.order_no).strip()
        client_id_val = request.form.get("client_id")
        order.client_id = int(client_id_val) if client_id_val and client_id_val.isdigit() else None
        order.client_name = request.form.get("client_name", "").strip()

        order_date_str = request.form.get("order_date")
        if order_date_str:
            order.order_date = datetime.strptime(order_date_str, "%Y-%m-%d").date()

        delivery_date_str = request.form.get("delivery_date")
        order.delivery_date = datetime.strptime(delivery_date_str, "%Y-%m-%d").date() if delivery_date_str else None

        order.reference_no = request.form.get("reference_no", "").strip()
        order.status = request.form.get("status", "Confirmed")
        order.terms = request.form.get("terms", "").strip()
        order.notes = request.form.get("notes", "").strip()
        order.updated_by = session.get("user", {}).get("email", "System")

        for it in list(order.items):
            cdb.delete(it)
        cdb.flush()

        item_names = request.form.getlist("item_name[]")
        item_codes = request.form.getlist("item_code[]")
        item_hsns = request.form.getlist("item_hsn[]")
        item_qtys = request.form.getlist("item_qty[]")
        item_units = request.form.getlist("item_unit[]")
        item_rates = request.form.getlist("item_rate[]")
        item_discs = request.form.getlist("item_discount[]")
        item_gsts = request.form.getlist("item_gst[]")
        item_stock_ids = request.form.getlist("item_stock_id[]")

        subtotal = 0.0
        tax_amount = 0.0

        for i in range(len(item_names)):
            name = item_names[i].strip() if i < len(item_names) else ""
            if not name:
                continue

            qty = float(item_qtys[i]) if i < len(item_qtys) and item_qtys[i] else 1.0
            rate = float(item_rates[i]) if i < len(item_rates) and item_rates[i] else 0.0
            disc_pct = float(item_discs[i]) if i < len(item_discs) and item_discs[i] else 0.0
            gst_pct = float(item_gsts[i]) if i < len(item_gsts) and item_gsts[i] else 0.0
            hsn = item_hsns[i].strip() if i < len(item_hsns) else ""
            unit = item_units[i].strip() if i < len(item_units) else "pcs"
            code = item_codes[i].strip() if i < len(item_codes) else ""
            s_id = int(item_stock_ids[i]) if i < len(item_stock_ids) and item_stock_ids[i] and item_stock_ids[i].isdigit() else None

            base = qty * rate
            disc = (base * disc_pct) / 100.0
            taxable = max(0.0, base - disc)
            tax = (taxable * gst_pct) / 100.0
            line_total = taxable + tax

            cgst = tax / 2.0
            sgst = tax / 2.0
            igst = 0.0

            subtotal += taxable
            tax_amount += tax

            so_item = SalesOrderItem(
                sales_order_id=order.id,
                stock_item_id=s_id,
                item_code=code,
                item_name=name,
                description="",
                hsn=hsn,
                quantity=qty,
                delivered_qty=0.0,
                unit=unit,
                rate=rate,
                discount_percent=disc_pct,
                taxable_amount=taxable,
                gst_percent=gst_pct,
                cgst_amount=cgst,
                sgst_amount=sgst,
                igst_amount=igst,
                total_amount=line_total,
            )
            cdb.add(so_item)

        order.subtotal = subtotal
        order.tax_amount = tax_amount
        order.cgst_total = tax_amount / 2.0
        order.sgst_total = tax_amount / 2.0
        order.igst_total = 0.0
        order.grand_total = subtotal + tax_amount

        cdb.commit()
        flash(f"Sales Order {order.order_no} updated successfully!", "success")
        return redirect(url_for("sales_order_view", order_id=order.id))

    @app.route("/sales-order/<int:order_id>/convert-to-challan")
    @login_required
    @require_permission("delivery_challans", "create")
    def sales_order_convert_to_challan(order_id):
        cdb = get_cdb()
        company_id = get_current_company()
        order = cdb.query(SalesOrder).filter_by(id=order_id, company_id=company_id).first_or_404()

        count = cdb.query(DeliveryChallan).filter_by(company_id=company_id).count()
        dc_no = f"DC-{count + 1:04d}"
        while cdb.query(DeliveryChallan).filter_by(company_id=company_id, challan_no=dc_no).first():
            count += 1
            dc_no = f"DC-{count + 1:04d}"

        shipping_addr = ""
        if order.client_obj:
            parts = [order.client_obj.address_line1, order.client_obj.city, order.client_obj.state, order.client_obj.pincode]
            shipping_addr = ", ".join(p for p in parts if p)

        challan = DeliveryChallan(
            challan_no=dc_no,
            company_id=company_id,
            client_id=order.client_id,
            client_name=order.client_name,
            challan_date=date.today(),
            delivery_date=order.delivery_date,
            reference_order_no=order.order_no,
            challan_type="Delivery on Sale",
            shipping_address=shipping_addr,
            status="Dispatched",
            stock_deducted=True,
            subtotal=order.subtotal,
            tax_amount=order.tax_amount,
            grand_total=order.grand_total,
            terms=order.terms,
            notes=f"Dispatched against Sales Order: {order.order_no}",
            created_by=session.get("user", {}).get("email", "System"),
        )
        cdb.add(challan)
        cdb.flush()

        for item in order.items:
            ch_item = DeliveryChallanItem(
                challan_id=challan.id,
                stock_item_id=item.stock_item_id,
                item_code=item.item_code,
                item_name=item.item_name,
                description=item.description,
                hsn=item.hsn,
                quantity=item.quantity,
                unit=item.unit,
                rate=item.rate,
                discount_percent=item.discount_percent,
                taxable_amount=item.taxable_amount,
                gst_percent=item.gst_percent,
                cgst_amount=item.cgst_amount,
                sgst_amount=item.sgst_amount,
                igst_amount=item.igst_amount,
                total_amount=item.total_amount,
            )
            cdb.add(ch_item)

            if item.stock_item_id:
                stk = cdb.query(StockItem).filter_by(id=item.stock_item_id, company_id=company_id).first()
                if stk:
                    stk.quantity = max(0.0, (stk.quantity or 0.0) - item.quantity)

        order.status = "Shipped"
        cdb.commit()
        flash(f"Delivery Challan {challan.challan_no} created for Sales Order {order.order_no}!", "success")
        return redirect(url_for("delivery_challan_view", challan_id=challan.id))

    @app.route("/sales-order/<int:order_id>/convert-to-invoice")
    @login_required
    @require_permission("customer_invoices", "create")
    def sales_order_convert_to_invoice(order_id):
        cdb = get_cdb()
        company_id = get_current_company()
        order = cdb.query(SalesOrder).filter_by(id=order_id, company_id=company_id).first_or_404()

        count = cdb.query(CustomerInvoice).filter_by(company_id=company_id).count()
        inv_no = f"INV-{count + 1:04d}"
        while cdb.query(CustomerInvoice).filter_by(company_id=company_id, invoice_number=inv_no).first():
            count += 1
            inv_no = f"INV-{count + 1:04d}"

        cust_inv = CustomerInvoice(
            invoice_number=inv_no,
            company_id=company_id,
            client_id=order.client_id or 0,
            client_name=order.client_name or (order.client_obj.name if order.client_obj else "Direct Customer"),
            invoice_date=date.today(),
            due_date=date.today(),
            invoice_type="credit" if order.client_id else "cash",
            status="Pending",
            subtotal=order.subtotal,
            tax_amount=order.tax_amount,
            cgst_total=order.cgst_total,
            sgst_total=order.sgst_total,
            igst_total=order.igst_total,
            grand_total=order.grand_total,
            paid_amount=0.0,
            balance=order.grand_total,
            notes=f"Generated from Sales Order: {order.order_no}",
            created_by=session.get("user", {}).get("email", "System"),
        )
        cdb.add(cust_inv)
        cdb.flush()

        for item in order.items:
            ci_item = CustomerInvoiceItem(
                customer_invoice_id=cust_inv.id,
                booking_invoice_id=order.id,
                booking_invoice_ref=order.order_no,
                docket_no=order.order_no,
                receiver_name=order.client_name,
                item_description=item.item_name,
                quantity=item.quantity,
                rate_per_kg=item.rate,
                taxable_amount=item.taxable_amount,
                gst_percent=item.gst_percent,
                cgst_amount=item.cgst_amount,
                sgst_amount=item.sgst_amount,
                igst_amount=item.igst_amount,
                total_amount=item.total_amount,
                booking_date=order.order_date,
            )
            cdb.add(ci_item)

        order.status = "Invoiced"
        cdb.commit()
        flash(f"Sales Order {order.order_no} converted to Tax Invoice {cust_inv.invoice_number}!", "success")
        return redirect(url_for("customer_invoice_view", cust_inv_id=cust_inv.id))

    @app.route("/sales-order/<int:order_id>/delete", methods=["POST"])
    @login_required
    @require_permission("sales_orders", "delete")
    def sales_order_delete(order_id):
        cdb = get_cdb()
        company_id = get_current_company()
        order = cdb.query(SalesOrder).filter_by(id=order_id, company_id=company_id).first_or_404()
        so_no = order.order_no
        cdb.delete(order)
        cdb.commit()
        flash(f"Sales Order {so_no} deleted successfully.", "info")
        return redirect(url_for("sales_order_list"))

    # ==========================================
    # 3. PURCHASE ORDERS
    # ==========================================
    @app.route("/purchase-orders")
    @login_required
    @require_permission("purchase_orders", "view")
    def purchase_order_list():
        cdb = get_cdb()
        company_id = get_current_company()
        status_filter = request.args.get("status", "All")
        search_query = request.args.get("q", "").strip()
        query = cdb.query(PurchaseOrder).filter_by(company_id=company_id)

        if status_filter != "All":
            query = query.filter_by(status=status_filter)

        if search_query:
            query = query.filter(
                or_(
                    PurchaseOrder.po_number.ilike(f"%{search_query}%"),
                    PurchaseOrder.supplier_name.ilike(f"%{search_query}%"),
                    PurchaseOrder.reference_quote_no.ilike(f"%{search_query}%"),
                )
            )

        orders = query.order_by(PurchaseOrder.po_date.desc(), PurchaseOrder.id.desc()).all()
        return render_template(
            "purchase_order_list.html",
            orders=orders,
            current_status=status_filter,
            current_search=search_query,
            active="purchase_orders"
        )

    @app.route("/purchase-order/new", methods=["GET", "POST"])
    @login_required
    @require_permission("purchase_orders", "create")
    def purchase_order_new():
        cdb = get_cdb()
        company_id = get_current_company()
        company = Company.query.filter_by(company_id=company_id).first()

        if request.method == "GET":
            count = cdb.query(PurchaseOrder).filter_by(company_id=company_id).count()
            default_po_no = f"PO-{count + 1:04d}"
            while cdb.query(PurchaseOrder).filter_by(company_id=company_id, po_number=default_po_no).first():
                count += 1
                default_po_no = f"PO-{count + 1:04d}"

            suppliers = cdb.query(Supplier).filter_by(company_id=company_id).order_by(Supplier.name.asc()).all()
            stock_items = cdb.query(StockItem).filter_by(company_id=company_id).order_by(StockItem.name.asc()).all()

            return render_template(
                "purchase_order_form.html",
                is_edit=False,
                po=None,
                order=None,
                default_po_no=default_po_no,
                today_date=date.today().strftime("%Y-%m-%d"),
                company=company,
                suppliers=suppliers,
                stock_items=stock_items,
                active="purchase_orders"
            )

        po_number = request.form.get("po_number", "").strip()
        supplier_id_val = request.form.get("supplier_id")
        supplier_id = int(supplier_id_val) if supplier_id_val and supplier_id_val.isdigit() else None
        supplier_name = request.form.get("supplier_name", "").strip()

        po_date_str = request.form.get("po_date")
        expected_date_str = request.form.get("expected_date")

        try:
            po_date = datetime.strptime(po_date_str, "%Y-%m-%d").date() if po_date_str else date.today()
        except ValueError:
            po_date = date.today()

        try:
            expected_date = datetime.strptime(expected_date_str, "%Y-%m-%d").date() if expected_date_str else None
        except ValueError:
            expected_date = None

        supplier_address = request.form.get("supplier_address", "").strip()
        supplier_gstin = request.form.get("supplier_gstin", "").strip()
        supplier_state = request.form.get("supplier_state", "").strip()
        supplier_phone = request.form.get("supplier_phone", "").strip()
        supplier_email = request.form.get("supplier_email", "").strip()

        if supplier_id and (not supplier_name or not supplier_address or not supplier_gstin):
            sup = cdb.query(Supplier).filter_by(id=supplier_id, company_id=company_id).first()
            if sup:
                if not supplier_name: supplier_name = sup.name
                if not supplier_address: supplier_address = f"{sup.address or ''} {sup.city or ''}".strip()
                if not supplier_gstin: supplier_gstin = sup.gst_number or sup.gstin or ""
                if not supplier_state: supplier_state = sup.state or ""
                if not supplier_phone: supplier_phone = sup.phone or ""
                if not supplier_email: supplier_email = sup.email or ""

        reference_quote_no = request.form.get("reference_quote_no", "").strip()
        payment_terms = request.form.get("payment_terms", "").strip()
        delivery_terms = request.form.get("delivery_terms", "").strip()
        terms = request.form.get("terms", "").strip()
        notes = request.form.get("notes", "").strip()

        order = PurchaseOrder(
            po_number=po_number,
            company_id=company_id,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            supplier_address=supplier_address,
            supplier_gstin=supplier_gstin,
            supplier_state=supplier_state,
            supplier_phone=supplier_phone,
            supplier_email=supplier_email,
            po_date=po_date,
            expected_date=expected_date,
            reference_quote_no=reference_quote_no,
            payment_terms=payment_terms,
            delivery_terms=delivery_terms,
            terms=terms,
            notes=notes,
            status="Draft",
            created_by=session.get("user", {}).get("email", "System"),
        )
        cdb.add(order)
        cdb.flush()

        subtotal = 0.0
        cgst_total = 0.0
        sgst_total = 0.0
        igst_total = 0.0

        item_names = request.form.getlist("item_name[]")
        item_codes = request.form.getlist("item_code[]")
        stock_ids = request.form.getlist("stock_item_id[]")
        descriptions = request.form.getlist("description[]")
        hsns = request.form.getlist("hsn[]")
        quantities = request.form.getlist("quantity[]")
        units = request.form.getlist("unit[]")
        rates = request.form.getlist("rate[]")
        discounts = request.form.getlist("discount_percent[]")
        gst_percents = request.form.getlist("gst_percent[]")

        for i in range(len(item_names)):
            iname = item_names[i].strip() if i < len(item_names) else ""
            if not iname:
                continue

            icode = item_codes[i].strip() if i < len(item_codes) else ""
            sid_val = stock_ids[i] if i < len(stock_ids) else ""
            stock_id = int(sid_val) if sid_val and sid_val.isdigit() else None
            desc = descriptions[i].strip() if i < len(descriptions) else ""
            hsn = hsns[i].strip() if i < len(hsns) else ""
            
            try: qty = float(quantities[i]) if i < len(quantities) and quantities[i] else 1.0
            except ValueError: qty = 1.0
            unit = units[i].strip() if i < len(units) else "pcs"
            try: rate = float(rates[i]) if i < len(rates) and rates[i] else 0.0
            except ValueError: rate = 0.0
            try: disc = float(discounts[i]) if i < len(discounts) and discounts[i] else 0.0
            except ValueError: disc = 0.0
            try: gst = float(gst_percents[i]) if i < len(gst_percents) and gst_percents[i] else 0.0
            except ValueError: gst = 0.0

            line_gross = qty * rate
            line_disc = line_gross * (disc / 100.0)
            taxable = max(0.0, line_gross - line_disc)

            is_interstate = False
            if company and company.state and supplier_state:
                if company.state.strip().lower() != supplier_state.strip().lower():
                    is_interstate = True

            if is_interstate:
                cgst = 0.0
                sgst = 0.0
                igst = round(taxable * (gst / 100.0), 2)
            else:
                cgst = round(taxable * (gst / 200.0), 2)
                sgst = round(taxable * (gst / 200.0), 2)
                igst = 0.0

            total = round(taxable + cgst + sgst + igst, 2)

            subtotal += taxable
            cgst_total += cgst
            sgst_total += sgst
            igst_total += igst

            po_item = PurchaseOrderItem(
                purchase_order_id=order.id,
                stock_item_id=stock_id,
                item_code=icode,
                item_name=iname,
                description=desc,
                hsn=hsn,
                quantity=qty,
                unit=unit,
                rate=rate,
                discount_percent=disc,
                taxable_amount=taxable,
                gst_percent=gst,
                cgst_amount=cgst,
                sgst_amount=sgst,
                igst_amount=igst,
                total_amount=total
            )
            cdb.add(po_item)

        order.subtotal = round(subtotal, 2)
        order.cgst_total = round(cgst_total, 2)
        order.sgst_total = round(sgst_total, 2)
        order.igst_total = round(igst_total, 2)
        order.tax_amount = round(cgst_total + sgst_total + igst_total, 2)
        order.grand_total = round(subtotal + order.tax_amount, 2)

        cdb.commit()
        flash(f"Purchase Order {order.po_number} created successfully!", "success")
        return redirect(url_for("purchase_order_view", po_id=order.id))

    @app.route("/purchase-order/<int:po_id>")
    @login_required
    @require_permission("purchase_orders", "view")
    def purchase_order_view(po_id):
        cdb = get_cdb()
        company_id = get_current_company()
        order = cdb.query(PurchaseOrder).filter_by(id=po_id, company_id=company_id).first_or_404()
        company = Company.query.filter_by(company_id=company_id).first()

        return render_template(
            "purchase_order_view.html",
            po=order,
            order=order,
            company=company,
            active="purchase_orders"
        )

    @app.route("/purchase-order/<int:po_id>/edit", methods=["GET", "POST"])
    @login_required
    @require_permission("purchase_orders", "edit")
    def purchase_order_edit(po_id):
        cdb = get_cdb()
        company_id = get_current_company()
        order = cdb.query(PurchaseOrder).filter_by(id=po_id, company_id=company_id).first_or_404()
        company = Company.query.filter_by(company_id=company_id).first()

        if request.method == "GET":
            suppliers = cdb.query(Supplier).filter_by(company_id=company_id).order_by(Supplier.name.asc()).all()
            stock_items = cdb.query(StockItem).filter_by(company_id=company_id).order_by(StockItem.name.asc()).all()

            return render_template(
                "purchase_order_form.html",
                is_edit=True,
                po=order,
                order=order,
                default_po_no=order.po_number,
                today_date=order.po_date.strftime("%Y-%m-%d") if order.po_date else date.today().strftime("%Y-%m-%d"),
                company=company,
                suppliers=suppliers,
                stock_items=stock_items,
                active="purchase_orders"
            )

        order.po_number = request.form.get("po_number", order.po_number).strip()
        supplier_id_val = request.form.get("supplier_id")
        order.supplier_id = int(supplier_id_val) if supplier_id_val and supplier_id_val.isdigit() else None
        order.supplier_name = request.form.get("supplier_name", order.supplier_name).strip()

        po_date_str = request.form.get("po_date")
        expected_date_str = request.form.get("expected_date")

        try:
            order.po_date = datetime.strptime(po_date_str, "%Y-%m-%d").date() if po_date_str else date.today()
        except ValueError:
            pass

        try:
            order.expected_date = datetime.strptime(expected_date_str, "%Y-%m-%d").date() if expected_date_str else None
        except ValueError:
            order.expected_date = None

        order.supplier_address = request.form.get("supplier_address", "").strip()
        order.supplier_gstin = request.form.get("supplier_gstin", "").strip()
        order.supplier_state = request.form.get("supplier_state", "").strip()
        order.supplier_phone = request.form.get("supplier_phone", "").strip()
        order.supplier_email = request.form.get("supplier_email", "").strip()
        order.reference_quote_no = request.form.get("reference_quote_no", "").strip()
        order.payment_terms = request.form.get("payment_terms", "").strip()
        order.delivery_terms = request.form.get("delivery_terms", "").strip()
        order.terms = request.form.get("terms", "").strip()
        order.notes = request.form.get("notes", "").strip()
        order.updated_by = session.get("user", {}).get("email", "System")

        cdb.query(PurchaseOrderItem).filter_by(purchase_order_id=order.id).delete()

        subtotal = 0.0
        cgst_total = 0.0
        sgst_total = 0.0
        igst_total = 0.0

        item_names = request.form.getlist("item_name[]")
        item_codes = request.form.getlist("item_code[]")
        stock_ids = request.form.getlist("stock_item_id[]")
        descriptions = request.form.getlist("description[]")
        hsns = request.form.getlist("hsn[]")
        quantities = request.form.getlist("quantity[]")
        units = request.form.getlist("unit[]")
        rates = request.form.getlist("rate[]")
        discounts = request.form.getlist("discount_percent[]")
        gst_percents = request.form.getlist("gst_percent[]")

        for i in range(len(item_names)):
            iname = item_names[i].strip() if i < len(item_names) else ""
            if not iname:
                continue

            icode = item_codes[i].strip() if i < len(item_codes) else ""
            sid_val = stock_ids[i] if i < len(stock_ids) else ""
            stock_id = int(sid_val) if sid_val and sid_val.isdigit() else None
            desc = descriptions[i].strip() if i < len(descriptions) else ""
            hsn = hsns[i].strip() if i < len(hsns) else ""
            
            try: qty = float(quantities[i]) if i < len(quantities) and quantities[i] else 1.0
            except ValueError: qty = 1.0
            unit = units[i].strip() if i < len(units) else "pcs"
            try: rate = float(rates[i]) if i < len(rates) and rates[i] else 0.0
            except ValueError: rate = 0.0
            try: disc = float(discounts[i]) if i < len(discounts) and discounts[i] else 0.0
            except ValueError: disc = 0.0
            try: gst = float(gst_percents[i]) if i < len(gst_percents) and gst_percents[i] else 0.0
            except ValueError: gst = 0.0

            line_gross = qty * rate
            line_disc = line_gross * (disc / 100.0)
            taxable = max(0.0, line_gross - line_disc)

            is_interstate = False
            if company and company.state and order.supplier_state:
                if company.state.strip().lower() != order.supplier_state.strip().lower():
                    is_interstate = True

            if is_interstate:
                cgst = 0.0
                sgst = 0.0
                igst = round(taxable * (gst / 100.0), 2)
            else:
                cgst = round(taxable * (gst / 200.0), 2)
                sgst = round(taxable * (gst / 200.0), 2)
                igst = 0.0

            total = round(taxable + cgst + sgst + igst, 2)

            subtotal += taxable
            cgst_total += cgst
            sgst_total += sgst
            igst_total += igst

            po_item = PurchaseOrderItem(
                purchase_order_id=order.id,
                stock_item_id=stock_id,
                item_code=icode,
                item_name=iname,
                description=desc,
                hsn=hsn,
                quantity=qty,
                unit=unit,
                rate=rate,
                discount_percent=disc,
                taxable_amount=taxable,
                gst_percent=gst,
                cgst_amount=cgst,
                sgst_amount=sgst,
                igst_amount=igst,
                total_amount=total
            )
            cdb.add(po_item)

        order.subtotal = round(subtotal, 2)
        order.cgst_total = round(cgst_total, 2)
        order.sgst_total = round(sgst_total, 2)
        order.igst_total = round(igst_total, 2)
        order.tax_amount = round(cgst_total + sgst_total + igst_total, 2)
        order.grand_total = round(subtotal + order.tax_amount, 2)

        cdb.commit()
        flash(f"Purchase Order {order.po_number} updated successfully!", "success")
        return redirect(url_for("purchase_order_view", po_id=order.id))

    @app.route("/purchase-order/<int:po_id>/delete", methods=["POST"])
    @login_required
    @require_permission("purchase_orders", "delete")
    def purchase_order_delete(po_id):
        cdb = get_cdb()
        company_id = get_current_company()
        order = cdb.query(PurchaseOrder).filter_by(id=po_id, company_id=company_id).first_or_404()
        po_no = order.po_number
        cdb.delete(order)
        cdb.commit()
        flash(f"Purchase Order {po_no} deleted successfully.", "info")
        return redirect(url_for("purchase_order_list"))

    @app.route("/purchase-order/<int:po_id>/convert-to-bill")
    @login_required
    @require_permission("purchase_invoices", "create")
    def purchase_order_convert_to_bill(po_id):
        cdb = get_cdb()
        company_id = get_current_company()
        order = cdb.query(PurchaseOrder).filter_by(id=po_id, company_id=company_id).first_or_404()

        count = cdb.query(PurchaseInvoice).filter_by(company_id=company_id).count()
        inv_id_val = f"PB-{count + 1:04d}"
        while cdb.query(PurchaseInvoice).filter_by(company_id=company_id, invoice_id=inv_id_val).first():
            count += 1
            inv_id_val = f"PB-{count + 1:04d}"

        p_inv = PurchaseInvoice(
            invoice_id=inv_id_val,
            company_id=company_id,
            supplier_id=order.supplier_id,
            supplier_name=order.supplier_name,
            supplier_address=getattr(order, 'supplier_address', None),
            supplier_gstin=getattr(order, 'supplier_gstin', None),
            supplier_state=getattr(order, 'supplier_state', None),
            supplier_phone=getattr(order, 'supplier_phone', None),
            supplier_email=getattr(order, 'supplier_email', None),
            invoice_number=order.po_number,
            reference_po_no=order.po_number,
            date=date.today(),
            due_date=order.expected_delivery_date or date.today(),
            subtotal=order.subtotal or 0.0,
            cgst_total=order.cgst_total or 0.0,
            sgst_total=order.sgst_total or 0.0,
            igst_total=order.igst_total or 0.0,
            tax_amount=order.tax_amount or 0.0,
            grand_total=order.grand_total or 0.0,
            paid_amount=0.0,
            balance=order.grand_total or 0.0,
            status="Pending",
            payment_terms=order.terms or "Net 30 Days",
            terms=order.terms,
            notes=f"Generated from Purchase Order: {order.po_number}",
        )
        cdb.add(p_inv)
        cdb.flush()

        for item in order.items:
            pi_item = PurchaseInvoiceItem(
                purchase_invoice_id=p_inv.id,
                stock_item_id=item.stock_item_id,
                item_code=item.item_code,
                code=item.item_code,
                item_name=item.item_name,
                description=item.item_name,
                hsn=item.hsn,
                quantity=item.quantity,
                unit=item.unit,
                rate=item.rate,
                purchase_rate=item.rate,
                discount_percent=item.discount_percent,
                taxable_amount=item.taxable_amount,
                taxable_value=item.taxable_amount,
                gst_percent=item.gst_percent,
                cgst_amount=item.cgst_amount,
                sgst_amount=item.sgst_amount,
                igst_amount=item.igst_amount,
                total_amount=item.total_amount,
                party_name=order.supplier_name
            )
            cdb.add(pi_item)

            if item.stock_item_id:
                stk = cdb.query(StockItem).filter_by(id=item.stock_item_id, company_id=company_id).first()
                if stk:
                    stk.quantity = (stk.quantity or 0.0) + item.quantity

        order.status = "Received"
        cdb.commit()
        flash(f"Purchase Order {order.po_number} converted to Purchase Bill {p_inv.invoice_id}! Stock updated.", "success")
        return redirect(url_for("purchase_invoice_view", invoice_id=p_inv.invoice_id))

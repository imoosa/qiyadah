"""Read-only Indian GST portal exports. Never issue an IRN or an e-way bill locally.

Scope: regular domestic B2B tax invoices in INR, without cess or reverse charge.
NIC bulk EWB format: docs.ewaybillgst.gov.in/html/formatdownloadnew.html
IRP schema: einvoice6.gst.gov.in/content/notified-e-invoice-schema/
"""
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import BytesIO

from flask import abort, render_template, request, send_file
from customer_models import Client, CustomerInvoice, WorkshopJobCard
from tax_service import country_name, normalize_regime

UNITS = set('BAG BAL BDL BKL BOU BOX BTL BUN CAN CBM CCM CMS CTN DOZ DRM GGK GMS GRS GYD KGS KLR KME LTR MLT MTR MTS NOS OTH PAC PCS PRS QTL ROL SET SQF SQM SQY TBS TGM THD TON TUB UGS UNT YDS'.split())
STATE_NAMES = dict(zip(
    '01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 26 27 29 30 31 32 33 34 35 36 37 38 97'.split(),
    ['Jammu and Kashmir', 'Himachal Pradesh', 'Punjab', 'Chandigarh', 'Uttarakhand', 'Haryana',
     'Delhi', 'Rajasthan', 'Uttar Pradesh', 'Bihar', 'Sikkim', 'Arunachal Pradesh', 'Nagaland',
     'Manipur', 'Mizoram', 'Tripura', 'Meghalaya', 'Assam', 'West Bengal', 'Jharkhand', 'Odisha',
     'Chhattisgarh', 'Madhya Pradesh', 'Gujarat', 'Dadra and Nagar Haveli and Daman and Diu',
     'Maharashtra', 'Karnataka', 'Goa', 'Lakshadweep', 'Kerala', 'Tamil Nadu', 'Puducherry',
     'Andaman and Nicobar Islands', 'Telangana', 'Andhra Pradesh', 'Ladakh', 'Other Territory']))
STATES = set(STATE_NAMES)
GSTIN = re.compile(r'[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]')


class ExportError(ValueError):
    pass


def number(value, label, places='0.01'):
    try:
        value = Decimal(str(value if value is not None else 0))
        if not value.is_finite() or value < 0 or value > Decimal('9999999999999'):
            raise ValueError()
        return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        raise ExportError(f'{label}: enter a valid non-negative number.') from None


def text(value, label, minimum=1, maximum=100):
    value = str(value or '').strip()
    if not minimum <= len(value) <= maximum:
        raise ExportError(f'{label}: enter {minimum}–{maximum} characters.')
    return value


def gstin(value, label):
    value = text(value, label, 15, 15).upper()
    if not GSTIN.fullmatch(value) or value[:2] not in STATES:
        raise ExportError(f'{label}: enter a valid Indian GSTIN.')
    alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    total = 0
    for index, char in enumerate(value[:14]):
        product = alphabet.index(char) * (1 if index % 2 == 0 else 2)
        total += product // 36 + product % 36
    if alphabet[(36 - total % 36) % 36] != value[-1]:
        raise ExportError(f'{label}: GSTIN checksum is invalid.')
    return value


def defaults(company, invoice, client=None):
    saved_state = str(getattr(invoice, 'client_state', '') or '').strip()
    pos = next((code for code, name in STATE_NAMES.items() if saved_state.casefold() in (code, name.casefold())), '')
    return dict(seller_name=company.company_name or '', seller_gstin=company.gst_number or '',
        seller_address=company.address or '', seller_city='', seller_pin='',
        buyer_name=invoice.client_name or '', buyer_gstin=invoice.client_gstin or '',
        buyer_address=invoice.billing_address or '', buyer_city=getattr(client, 'city', '') or '',
        buyer_pin=getattr(client, 'pincode', '') or '', pos=pos, vehicle='', distance='',
        transporter_id='', transporter_name='', vehicle_type='R', standard='', transport='', irn_required='')


def party(values, prefix):
    label = 'Seller' if prefix == 'seller' else 'Buyer'
    pin = text(values.get(prefix + '_pin'), label + ' PIN code', 6, 6)
    if not re.fullmatch(r'[1-9][0-9]{5}', pin) or pin == '999999':
        raise ExportError(f'{label}: enter a six-digit PIN code.')
    gst = gstin(values.get(prefix + '_gstin'), label + ' GSTIN')
    return dict(Gstin=gst, LglNm=text(values.get(prefix + '_name'), label + ' legal name', 3, 100),
        Addr1=text(values.get(prefix + '_address'), label + ' address', 3, 100),
        Loc=text(values.get(prefix + '_city'), label + ' city', 3, 50), Pin=int(pin), Stcd=gst[:2])


def build_export(company, invoice, values, kind, today=None):
    """Build from saved financial values; supplementary form values never alter them."""
    today = today or date.today()
    if kind not in ('einvoice', 'ewaybill'):
        raise ExportError('Choose an e-invoice or e-way bill export.')
    if country_name(company.country) != 'India' or normalize_regime(company.tax_regime) != 'GST':
        raise ExportError('Portal exports are available only for Indian GST companies.')
    if normalize_regime(invoice.tax_regime) != 'GST' or invoice.currency != 'INR':
        raise ExportError('This workflow supports GST invoices in INR only.')
    if (invoice.status or '').strip().lower() in ('draft', 'void', 'cancelled', 'canceled'):
        raise ExportError('Draft, cancelled and void invoices cannot be exported.')
    if values.get('standard') != 'yes':
        raise ExportError('Confirm that this is a regular domestic B2B invoice, without cess, reverse charge or special tax treatment.')
    reference = text(invoice.invoice_number, 'Invoice number', 1, 16)
    if not re.fullmatch(r'[1-9A-Z][A-Z0-9/-]{0,15}', reference):
        raise ExportError('Invoice number must start with 1–9 or A–Z and contain only uppercase letters, digits, / or -. Correct the saved invoice before export.')
    if not invoice.invoice_date or invoice.invoice_date > today:
        raise ExportError('Invoice date is missing or is in the future.')
    seller, buyer = party(values, 'seller'), party(values, 'buyer')
    if seller['Gstin'] != gstin(company.gst_number, 'Company GSTIN'):
        raise ExportError('Seller GSTIN must match the company profile.')
    if buyer['Gstin'] != gstin(invoice.client_gstin, 'Saved invoice buyer GSTIN'):
        raise ExportError('Buyer GSTIN must match the saved invoice. Correct the invoice before export.')
    if seller['Gstin'] == buyer['Gstin']:
        raise ExportError('Seller and buyer GSTIN must be different.')
    pos = str(values.get('pos', '')).strip()
    if pos not in STATES:
        raise ExportError('Choose the invoice place-of-supply state code.')
    buyer['Pos'] = pos
    interstate = seller['Stcd'] != pos
    lines = []
    if not invoice.items or len(invoice.items) > 1000:
        raise ExportError('The invoice must have between 1 and 1,000 saved line items.')
    for i, item in enumerate(invoice.items, 1):
        label = f'Line {i}'
        hsn = str(item.hsn or '').strip()
        if not re.fullmatch(r'(?:[0-9]{4}|[0-9]{6}|[0-9]{8})', hsn):
            raise ExportError(f'{label}: add a valid 4, 6 or 8 digit HSN/SAC to the invoice.')
        service = hsn.startswith('99')
        unit = str(item.unit or '').strip().upper()
        unit = {'KG': 'KGS', 'LTRS': 'LTR', 'NO': 'NOS', 'UNIT': 'UNT'}.get(unit, unit)
        if service and not unit:
            unit = 'OTH'
        if unit not in UNITS:
            raise ExportError(f'{label}: use a GST unit code such as PCS, KGS, NOS or OTH.')
        qty, rate = number(item.quantity, label + ' quantity', '0.001'), number(item.rate, label + ' rate', '0.001')
        if qty <= 0:
            raise ExportError(f'{label}: quantity must be greater than zero.')
        gross = (qty * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        taxable = number(item.taxable_amount, label + ' taxable amount')
        discount = gross - taxable
        if discount < 0:
            raise ExportError(f'{label}: taxable amount exceeds quantity × rate; review the saved invoice pricing.')
        taxes = [number(getattr(item, key), label + ' tax') for key in ('cgst_amount', 'sgst_amount', 'igst_amount')]
        percent = number(item.gst_percent, label + ' GST rate', '0.001')
        if percent > 100:
            raise ExportError(f'{label}: invalid GST rate.')
        expected = (taxable * percent / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if interstate:
            valid = taxes[0] == taxes[1] == 0 and abs(taxes[2] - expected) <= Decimal('0.02')
        else:
            half = (taxable * percent / 200).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            valid = taxes[2] == 0 and all(abs(t - half) <= Decimal('0.01') for t in taxes[:2])
        if not valid:
            raise ExportError(f'{label}: saved GST amounts do not match the rate and place of supply.')
        charges = number(item.other_charges, label + ' other charges')
        total = number(item.total_amount, label + ' total')
        if abs(total - taxable - sum(taxes) - charges) > Decimal('0.02'):
            raise ExportError(f'{label}: saved line total does not reconcile with taxable value and GST.')
        lines.append(dict(SlNo=str(i), PrdDesc=text(item.item_name or item.item_description, label + ' description', 1, 100),
            IsServc='Y' if service else 'N', HsnCd=hsn, Qty=float(qty), Unit=unit, UnitPrice=float(rate),
            TotAmt=float(gross), Discount=float(discount), AssAmt=float(taxable), GstRt=float(percent),
            CgstAmt=float(taxes[0]), SgstAmt=float(taxes[1]), IgstAmt=float(taxes[2]),
            OthChrg=float(charges), TotItemVal=float(total)))
    if any(line['IsServc'] == 'N' for line in lines) and values.get('same_address') != 'yes':
        raise ExportError('Confirm the dispatch and delivery addresses for goods. Other shipping addresses must be entered directly on the portal.')
    def total(key):
        return sum((Decimal(str(line[key])) for line in lines), Decimal('0'))
    for field, key in (('subtotal', 'AssAmt'), ('cgst_total', 'CgstAmt'), ('sgst_total', 'SgstAmt'), ('igst_total', 'IgstAmt')):
        if abs(number(getattr(invoice, field), field) - total(key)) > Decimal('0.02'):
            raise ExportError(f'Invoice {field.replace("_", " ")} does not match its line items. Correct the saved invoice.')
    tax_total = total('CgstAmt') + total('SgstAmt') + total('IgstAmt')
    if abs(number(invoice.tax_amount, 'Tax total') - tax_total) > Decimal('0.02'):
        raise ExportError('Invoice tax total does not match its line items.')
    grand = number(invoice.grand_total, 'Invoice total')
    if abs(grand - total('TotItemVal')) > Decimal('0.02'):
        raise ExportError('Invoice total does not match its line items. This export does not infer round-off or extra charges.')
    document = dict(Version='1.1', TranDtls=dict(TaxSch='GST', SupTyp='B2B', RegRev='N', IgstOnIntra='N'),
        DocDtls=dict(Typ='INV', No=reference, Dt=invoice.invoice_date.strftime('%d/%m/%Y')),
        SellerDtls=seller, BuyerDtls=buyer, ItemList=lines,
        ValDtls=dict(AssVal=float(total('AssAmt')), CgstVal=float(total('CgstAmt')), SgstVal=float(total('SgstAmt')),
            IgstVal=float(total('IgstAmt')), CesVal=0, StCesVal=0, Discount=0, OthChrg=0, RndOffAmt=0, TotInvVal=float(grand)))
    with_transport = kind == 'ewaybill' or values.get('transport') == 'yes'
    if with_transport:
        if any(line['IsServc'] == 'Y' for line in lines):
            raise ExportError('This road-transport export supports goods-only invoices. Use the portal for mixed goods/services invoices.')
        if pos != buyer['Stcd'] or values.get('same_address') != 'yes':
            raise ExportError('This export supports dispatch from the seller address to the buyer billing address only. Use the portal for bill-to/ship-to or other dispatch addresses.')
        if (today - invoice.invoice_date).days > 180:
            raise ExportError('E-way bill document date is more than 180 days old.')
        vehicle = str(values.get('vehicle', '')).strip().upper().replace(' ', '').replace('-', '')
        if not re.fullmatch(r'[A-Z0-9]{7,15}', vehicle):
            raise ExportError('Enter a valid road vehicle number (7–15 letters/digits).')
        distance = str(values.get('distance', '')).strip()
        if not distance.isdigit() or not 1 <= int(distance) <= 4000:
            raise ExportError('Enter a road distance between 1 and 4,000 km.')
        vehicle_type = values.get('vehicle_type', 'R')
        if vehicle_type not in ('R', 'O'):
            raise ExportError('Choose regular or over-dimensional cargo vehicle type.')
        transporter_id = str(values.get('transporter_id', '')).strip().upper()
        if transporter_id and not re.fullmatch(r'[0-9]{2}[A-Z0-9]{13}', transporter_id):
            raise ExportError('Transporter ID must be a 15-character GSTIN or enrolment ID.')
        transport = dict(TransMode='1', Distance=int(distance), VehNo=vehicle, VehType=vehicle_type)
        if transporter_id:
            transport['TransId'] = transporter_id
        if values.get('transporter_name'):
            transport['TransName'] = text(values['transporter_name'], 'Transporter name', 1, 25)
        document['EwbDtls'] = transport
    if kind == 'einvoice':
        return [document]
    if values.get('irn_required') != 'no':
        raise ExportError('For invoices requiring an IRN, export an e-invoice with transport details or generate the e-way bill against the existing IRN on the portal. Standalone export is only for invoices not requiring an IRN.')
    bill = dict(userGstin=seller['Gstin'], supplyType='O', subSupplyType=1, subSupplyDesc='', docType='INV',
        docNo=reference, docDate=document['DocDtls']['Dt'], transType=1,
        totalValue=float(total('AssAmt')), cgstValue=float(total('CgstAmt')), sgstValue=float(total('SgstAmt')),
        igstValue=float(total('IgstAmt')), cessValue=0, TotNonAdvolVal=0,
        OthValue=float(total('OthChrg')), totInvValue=float(grand), transMode=1, transDistance=transport['Distance'],
        transporterName=transport.get('TransName', ''), transporterId=transporter_id,
        transDocNo='', transDocDate='', vehicleNo=vehicle, vehicleType=vehicle_type, mainHsnCode=lines[0]['HsnCd'])
    for prefix, party_data in (('from', seller), ('to', buyer)):
        bill.update({prefix+'Gstin':party_data['Gstin'], prefix+'TrdName':party_data['LglNm'],
            prefix+'Addr1':party_data['Addr1'], prefix+'Addr2':'', prefix+'Place':party_data['Loc'],
            prefix+'Pincode':party_data['Pin'], prefix+'StateCode':int(party_data['Stcd']),
            'actual'+prefix.title()+'StateCode':int(party_data['Stcd'])})
    bill['itemList'] = [dict(itemNo=int(line['SlNo']), productName=line['PrdDesc'], productDesc=line['PrdDesc'],
        hsnCode=line['HsnCd'], quantity=line['Qty'], qtyUnit=line['Unit'], taxableAmount=line['AssAmt'],
        cgstRate=0 if interstate else line['GstRt']/2, sgstRate=0 if interstate else line['GstRt']/2,
        igstRate=line['GstRt'] if interstate else 0, cessRate=0, cessNonAdvol=0) for line in lines]
    return dict(version='1.0.1118', billLists=[bill])


def register_gst_portal(app, login_required, get_cdb, get_current_company, get_company, can, today_func=date.today):
    @app.context_processor
    def inject_gst_portal_access():
        company_id = get_current_company()
        access = app.extensions.get('module_access')
        company = get_company(company_id) if company_id else None
        available = bool(company and access and access('core')
            and country_name(company.country) == 'India' and normalize_regime(company.tax_regime) == 'GST'
            and (can('invoices', 'view') or can('customer_invoices', 'view')))
        return dict(gst_portal_available=available)

    @app.route('/finance/gst-portal', methods=['GET', 'POST'])
    @login_required
    def gst_portal():
        company_id = get_current_company()
        access = app.extensions.get('module_access')
        if not company_id or not access or not access('core'):
            abort(403)
        sales, repair = can('invoices', 'view'), can('customer_invoices', 'view')
        if not (sales or repair):
            abort(403)
        company = get_company(company_id)
        if not company:
            abort(404)
        cdb = get_cdb()
        linked = cdb.query(WorkshopJobCard.id).filter(WorkshopJobCard.company_id == company_id,
            WorkshopJobCard.invoice_id == CustomerInvoice.id).exists()
        from sqlalchemy import func, or_
        is_repair = or_(CustomerInvoice.invoice_category == 'workshop_repair', linked)
        query = cdb.query(CustomerInvoice).filter_by(company_id=company_id)
        if not repair:
            query = query.filter(~func.coalesce(is_repair, False))
        if not sales:
            query = query.filter(is_repair)
        raw_id = request.form.get('invoice_id') if request.method == 'POST' else request.args.get('invoice_id')
        invoice = None
        if raw_id:
            if not str(raw_id).isdigit():
                abort(400)
            invoice = query.filter_by(id=int(raw_id)).first()
            if not invoice:
                abort(404)
        if request.method == 'POST' and not invoice:
            abort(400)
        client = cdb.query(Client).filter_by(id=invoice.client_id, company_id=company_id).first() if invoice and invoice.client_id else None
        values = defaults(company, invoice, client) if invoice else {}
        error = None
        if request.method == 'POST':
            values.update(request.form.to_dict())
            try:
                kind = request.form.get('kind')
                payload = build_export(company, invoice, values, kind, today_func())
                response = send_file(BytesIO(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8')),
                    mimetype='application/json', as_attachment=True, download_name=f'{kind}-{invoice.id}.json', max_age=0)
                response.headers['Cache-Control'] = 'no-store'
                return response
            except ExportError as exc:
                error = str(exc)
        response = app.make_response((render_template('gst_portal.html', company=company, invoice=invoice,
            invoices=query.order_by(CustomerInvoice.invoice_date.desc(), CustomerInvoice.id.desc()).limit(200).all(),
            values=values, error=error, state_codes=STATE_NAMES), 422 if error else 200))
        response.headers['Cache-Control'] = 'no-store'
        return response

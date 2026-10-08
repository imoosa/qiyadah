"""GST export calculations, refusal paths, isolation and download behaviour."""
import copy
import json
import unittest
from datetime import date, timedelta
from functools import wraps
from pathlib import Path
from types import SimpleNamespace as NS

from flask import Flask, abort, session
from jinja2 import ChoiceLoader, DictLoader
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from customer_models import Client, CustomerInvoice, CustomerInvoiceItem, WorkshopJobCard
from gst_portal import build_export, defaults, ExportError, gstin, register_gst_portal


def checked_gstin(prefix):
    alphabet = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    total = sum((alphabet.index(c) * (1 if i % 2 == 0 else 2)) // 36 +
                (alphabet.index(c) * (1 if i % 2 == 0 else 2)) % 36 for i, c in enumerate(prefix))
    return prefix + alphabet[(36 - total % 36) % 36]


def fixture():
    company = NS(company_name='Example Seller', gst_number='29AAACG0569P1Z3',
        address='Seller Road', country='India', tax_regime='GST')
    item = NS(item_name='Example product', item_description='', hsn='87089900', unit='pcs',
        quantity=2, rate=100, taxable_amount=180, other_charges=0, gst_percent=18,
        cgst_amount=16.2, sgst_amount=16.2, igst_amount=0, total_amount=212.4)
    invoice = NS(id=1, invoice_number='INV-101', invoice_date=date(2026, 10, 7),
        status='Pending', currency='INR', tax_regime='GST', client_name='Example Buyer',
        client_gstin=checked_gstin('29ABCDE1234F1Z'), billing_address='Buyer Road',
        shipping_address='Buyer Road', subtotal=180, cgst_total=16.2, sgst_total=16.2,
        igst_total=0, tax_amount=32.4, grand_total=212.4, items=[item])
    values = defaults(company, invoice)
    values.update(seller_city='Bengaluru', seller_pin='560001', buyer_city='Bengaluru', buyer_pin='560002',
        pos='29', standard='yes', vehicle='KA01AB1234', distance='25', vehicle_type='R',
        same_address='yes', irn_required='no')
    return company, invoice, values


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.company, self.invoice, self.values = fixture()

    def build(self, kind='einvoice'):
        return build_export(self.company, self.invoice, self.values, kind, date(2026, 10, 7))

    def test_einvoice_reconciles_discount_and_taxes_without_mutation(self):
        before = copy.deepcopy(vars(self.invoice.items[0]))
        result = self.build()[0]
        self.assertEqual(result['Version'], '1.1')
        self.assertEqual(result['DocDtls'], {'Typ':'INV', 'No':'INV-101', 'Dt':'07/10/2026'})
        self.assertEqual(result['ItemList'][0]['Discount'], 20)
        self.assertEqual(result['ItemList'][0]['Unit'], 'PCS')
        self.assertEqual(result['ValDtls']['TotInvVal'], 212.4)
        self.assertNotIn('EwbDtls', result)
        self.assertNotIn('Irn', result)
        self.assertEqual(vars(self.invoice.items[0]), before)

    def test_interstate_igst(self):
        self.invoice.client_gstin = checked_gstin('27ABCDE1234F1Z')
        self.values.update(buyer_gstin=self.invoice.client_gstin, pos='27', buyer_pin='400001', buyer_city='Mumbai')
        item = self.invoice.items[0]
        item.cgst_amount = item.sgst_amount = self.invoice.cgst_total = self.invoice.sgst_total = 0
        item.igst_amount = self.invoice.igst_total = 32.4
        result = self.build()[0]
        self.assertEqual(result['ValDtls']['IgstVal'], 32.4)
        self.assertEqual(result['BuyerDtls']['Pos'], '27')

    def test_eway_matches_official_bulk_sample_shape(self):
        result = self.build('ewaybill')
        raw = Path('docs/gst-sample-json.txt').read_text(encoding='utf-8')
        sample = json.loads(raw[raw.index('{'):])
        bill = result['billLists'][0]
        self.assertEqual(result['version'], sample['version'])
        self.assertEqual(set(bill), set(sample['billLists'][0]))
        self.assertEqual(set(bill['itemList'][0]), set(sample['billLists'][0]['itemList'][0]))
        self.assertEqual(bill['totInvValue'], 212.4)
        self.assertEqual(bill['itemList'][0]['cgstRate'], 9)
        self.assertEqual(bill['actualToStateCode'], 29)
        self.assertIsInstance(bill['transType'], int)
        self.assertNotIn('ewayBillNo', bill)

    def test_transport_can_be_included_with_einvoice(self):
        self.values['transport'] = 'yes'
        self.assertEqual(self.build()[0]['EwbDtls']['VehNo'], 'KA01AB1234')

    def test_saved_values_cannot_be_overridden_by_form(self):
        self.values.update(grand_total='1', taxable_amount='1', gst_percent='0')
        self.assertEqual(self.build()[0]['ValDtls']['TotInvVal'], 212.4)

    def test_invalid_invoice_and_financial_fields_are_blocked(self):
        for attr, value in [('grand_total', 1), ('tax_amount', 0), ('subtotal', 200), ('invoice_number', 'a'*17),
                            ('invoice_number', 'lowercase'), ('currency', 'AED'), ('status', 'Draft'),
                            ('status', 'Void'), ('invoice_date', date(2026, 10, 8)), ('grand_total', float('nan'))]:
            with self.subTest(attr=attr, value=value):
                original = getattr(self.invoice, attr)
                setattr(self.invoice, attr, value)
                with self.assertRaises(ExportError): self.build()
                setattr(self.invoice, attr, original)

    def test_invalid_items_and_tax_location_are_blocked(self):
        for attr, value in [('hsn', ''), ('unit', 'unknown'), ('quantity', 0), ('rate', 0),
                            ('igst_amount', 32.4), ('total_amount', 1), ('gst_percent', float('inf'))]:
            with self.subTest(attr=attr):
                original = getattr(self.invoice.items[0], attr)
                setattr(self.invoice.items[0], attr, value)
                with self.assertRaises(ExportError): self.build()
                setattr(self.invoice.items[0], attr, original)
        self.values['pos'] = '27'
        with self.assertRaisesRegex(ExportError, 'place of supply'): self.build()

    def test_gstin_and_pin_validation(self):
        self.assertEqual(gstin('29AAACG0569P1Z3', 'Seller'), '29AAACG0569P1Z3')
        for key, val in [('seller_gstin', '29AAACG0569P1Z4'), ('buyer_gstin', 'URP'),
                         ('buyer_pin', '123'), ('seller_pin', 'abcdef'), ('pos', '99')]:
            with self.subTest(key=key):
                previous = self.values[key]
                self.values[key] = val
                with self.assertRaises(ExportError): self.build()
                self.values[key] = previous

    def test_transport_and_irn_guards(self):
        for key, value in [('vehicle', ''), ('distance', '4001'), ('distance', 'NaN'), ('same_address', ''),
                           ('irn_required', 'yes'), ('vehicle_type', 'X')]:
            with self.subTest(key=key):
                previous = self.values[key]
                self.values[key] = value
                with self.assertRaises(ExportError): self.build('ewaybill')
                self.values[key] = previous
        self.invoice.invoice_date -= timedelta(days=181)
        with self.assertRaisesRegex(ExportError, '180 days'): self.build('ewaybill')

    def test_services_supported_without_eway(self):
        self.invoice.items[0].hsn = '998719'
        self.assertEqual(self.build()[0]['ItemList'][0]['IsServc'], 'Y')
        with self.assertRaisesRegex(ExportError, 'goods-only'): self.build('ewaybill')

    def test_non_indian_and_unconfirmed_transactions_rejected(self):
        self.company.country = 'United Arab Emirates'
        with self.assertRaisesRegex(ExportError, 'Indian GST'): self.build()
        self.company.country = 'India'
        self.values['standard'] = ''
        with self.assertRaises(ExportError): self.build()


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.company, invoice, self.values = fixture()
        self.engine = create_engine('sqlite://')
        for model in (Client, CustomerInvoice, CustomerInvoiceItem, WorkshopJobCard):
            model.__table__.create(self.engine)
        self.db = Session(self.engine)
        data = vars(invoice).copy()
        data.pop('items')
        self.invoice = CustomerInvoice(company_id='A', **data)
        self.invoice.items = [CustomerInvoiceItem(**vars(invoice.items[0]))]
        self.db.add(self.invoice)
        self.db.add(CustomerInvoice(id=2, company_id='B', invoice_number='PRIVATE', client_name='Secret'))
        self.db.add(CustomerInvoice(id=3, company_id='A', invoice_number='REPAIR', invoice_category='workshop_repair'))
        self.db.commit()
        self.allowed = True
        self.permissions = {'invoices'}
        self.app = Flask(__name__, template_folder='../templates')
        self.app.config.update(TESTING=True, SECRET_KEY='test')
        self.app.jinja_loader = ChoiceLoader([DictLoader({'base.html': '{% block extra_style %}{% endblock %}{% block content %}{% endblock %}'}), self.app.jinja_loader])
        self.app.extensions['module_access'] = lambda key: self.allowed
        def login_required(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                if not session.get('user'): abort(401)
                return fn(*args, **kwargs)
            return wrapped
        register_gst_portal(self.app, login_required, lambda:self.db, lambda:'A', lambda cid:self.company,
            lambda permission, action: permission in self.permissions, lambda:date(2026, 10, 7))
        self.client = self.app.test_client()
        with self.client.session_transaction() as state: state['user'] = 'Owner'

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_listing_and_form_render(self):
        response = self.client.get('/finance/gst-portal?invoice_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Download e-invoice JSON', response.data)
        self.assertNotIn(b'PRIVATE', response.data)
        self.assertNotIn(b'REPAIR', response.data)

    def test_sales_list_exposes_gst_export_button(self):
        from flask import render_template
        for endpoint in ('customer_invoice_new', 'customer_invoice_list'):
            self.app.add_url_rule('/' + endpoint, endpoint, lambda: '')
        with self.app.test_request_context('/customer-invoices'):
            html = render_template('customer_invoice_list.html', invoices=[], user_names={},
                current_status='All', current_search='', billing_tax={'label':'GST','is_vat':False}, can=lambda *args: True)
            self.assertIn('href="/finance/gst-portal"', html)
            self.assertIn('GST e-Invoice & e-Way Bill', html)
            self.allowed = False
            html = render_template('customer_invoice_list.html', invoices=[], user_names={},
                current_status='All', current_search='', billing_tax={'label':'GST','is_vat':False}, can=lambda *args: True)
            self.assertNotIn('href="/finance/gst-portal"', html)

    def test_download_is_attachment_and_does_not_change_invoice(self):
        response = self.client.post('/finance/gst-portal', data={**self.values, 'invoice_id':'1', 'kind':'einvoice'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json[0]['DocDtls']['No'], 'INV-101')
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertFalse(self.db.dirty)
        self.assertEqual(self.invoice.status, 'Pending')

    def test_error_preserves_user_input(self):
        response = self.client.post('/finance/gst-portal', data={**self.values, 'invoice_id':'1', 'kind':'einvoice', 'buyer_pin':'123'})
        self.assertEqual(response.status_code, 422)
        self.assertIn(b'Correct this before downloading', response.data)
        self.assertIn(b'value="123"', response.data)

    def test_tenant_and_permissions_enforced_on_get_and_post(self):
        for invoice_id in ('2', '3'):
            self.assertEqual(self.client.get('/finance/gst-portal?invoice_id='+invoice_id).status_code, 404)
            self.assertEqual(self.client.post('/finance/gst-portal', data={**self.values, 'invoice_id':invoice_id, 'kind':'einvoice'}).status_code, 404)
        self.allowed = False
        self.assertEqual(self.client.get('/finance/gst-portal').status_code, 403)
        self.allowed = True
        self.permissions.clear()
        self.assertEqual(self.client.get('/finance/gst-portal').status_code, 403)
        with self.client.session_transaction() as state: state.clear()
        self.assertEqual(self.client.get('/finance/gst-portal').status_code, 401)


if __name__ == '__main__':
    unittest.main()

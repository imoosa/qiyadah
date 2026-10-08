"""Country-scoped display and tax behavior without production database access."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch
import re
import subprocess
import unittest
from flask import Flask, render_template
from jinja2 import ChoiceLoader, DictLoader
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from customer_models import (SalesOrder, SalesOrderItem, PurchaseOrder, PurchaseOrderItem, Client, Supplier, StockItem, CustomerInvoice)
from erp_routes import register_erp_routes
from order_erp_routes import register_order_erp_routes
from tax_service import tax_profile, apply_company_tax, split_tax, billing_rate
from currency_service import get_currency_info


class CountryFinanceTests(unittest.TestCase):
    def setUp(self):
        self.company=SimpleNamespace(company_id='A',company_name='UAE Company',country='United Arab Emirates',currency='AED',tax_regime='GCC_VAT',
            currency_symbol='AED',tax_id_label='TRN',is_gst_registered=True,gst_number='100000000000003',state='Dubai')
        self.engine=create_engine('sqlite://')
        for model in (SalesOrder,SalesOrderItem,PurchaseOrder,PurchaseOrderItem,Client,Supplier,StockItem,CustomerInvoice):model.__table__.create(self.engine)
        self.db=Session(self.engine)
        self.app=Flask(__name__,template_folder='../templates');self.app.config.update(TESTING=True,SECRET_KEY='test')
        self.app.jinja_loader=ChoiceLoader([DictLoader({'base.html':'{% block content %}{% endblock %}{% block extra_script %}{% endblock %}'}),self.app.jinja_loader])
        register_erp_routes(self.app,lambda f:f,lambda *a,**k:lambda f:f,lambda:self.db,lambda:'A',lambda x:x,Mock())
        register_order_erp_routes(self.app,lambda f:f,lambda:self.db,lambda:'A',lambda:{'role':'owner'},lambda cid:self.company,lambda *a:True)
        self.client=self.app.test_client()
        self.company_patch=patch('erp_routes.Company',SimpleNamespace(query=Mock()))
        self.company_patch.start().query.filter_by.return_value.first.return_value=self.company

    def tearDown(self):
        self.company_patch.stop();self.db.close();self.engine.dispose()

    def test_uae_registration_profile_and_stale_indian_defaults(self):
        c=SimpleNamespace()
        apply_company_tax(c,dict(country='UAE',is_gst_registered='1',tax_registration_number='100000000000003'))
        self.assertEqual((c.currency,c.currency_symbol,c.tax_regime,c.tax_id_label),('AED','AED','GCC_VAT','TRN'))
        c.tax_regime='GST';c.tax_id_label='GSTIN'
        profile=tax_profile(c)
        self.assertEqual((profile['regime'],profile['id_label'],profile['rates']),('GCC_VAT','TRN',[0,5]))
        self.assertEqual(split_tax(100,5,profile['regime']),(5,0,0,0))
        self.assertEqual(split_tax(100,18,'GST'),(18,9,9,0))
        self.assertEqual(billing_rate(c,0),0)

    def test_sales_and_purchase_orders_use_vat_without_indian_split(self):
        data={'order_no':'SO1','po_number':'PO1','client_name':'Buyer','supplier_name':'Seller',
              'item_name[]':'Service','item_qty[]':'1','item_rate[]':'100','item_gst[]':'5'}
        for endpoint,model in (('/sales-order/new',SalesOrder),('/purchase-order/new',PurchaseOrder)):
            response=self.client.post(endpoint,data=data)
            self.assertEqual(response.status_code,302)
            order=self.db.query(model).one()
            self.assertEqual(order.grand_total,105)
            self.assertEqual(order.tax_amount,5)
            self.assertEqual((order.cgst_total,order.sgst_total,order.igst_total),(0,0,0))
            self.assertEqual((order.items[0].cgst_amount,order.items[0].sgst_amount),(0,0))

    def test_supply_order_api_and_zero_rated_items(self):
        response=self.client.post('/api/order-erp/sales-orders',json={'client_name':'Buyer','items':[{'item_name':'Service','quantity':1,'rate':100,'gst_percent':5}]})
        self.assertEqual(response.status_code,200)
        order=self.db.query(SalesOrder).one()
        self.assertEqual((order.tax_amount,order.grand_total,order.cgst_total),(5,105,0))

    def render(self,template,**values):
        with self.app.test_request_context('/'):
            return render_template(template,company=self.company,billing_tax=tax_profile(self.company),
                currency_symbol='AED',tax_id_label='TRN',number_locale='en-US',can=lambda *a:True,
                url_for=lambda *a,**k:'/test',**values)

    def test_ledger_currency_and_order_form_tax_options(self):
        html=self.render('ledger.html',accounts=[],ledger_entries=[],total_debits=1234,total_credits=100,closing_balance=1134,
                         from_date=date.today(),to_date=date.today(),filter_applied=True)
        self.assertIn('AED',html);self.assertNotIn('Ã¢â€šÂ¹',html)
        for template in ('sales_order_form.html','purchase_order_form.html'):
            html=self.render(template,order=None,po=None,clients=[],suppliers=[],is_edit=False,today_date=date.today())
            self.assertIn('VAT %',html);self.assertIn('value="5"',html)
            self.assertNotIn('<option value="18"',html);self.assertNotIn('Ã¢â€šÂ¹',html)
        script=self.render('_supply_operations_script.html')
        for code in re.findall(r'<script[^>]*>(.*?)</script>',script,re.S):
            result=subprocess.run(['node','--check'],input=code,text=True,encoding='utf-8',capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_standalone_workspaces_have_valid_localized_scripts(self):
        for template,values in [('workshop_erp.html',{'user':{}}),('supplier_form.html',{'supplier':None,'form_data':{},'existing_brands':[]})]:
            html=self.render(template,**values)
            self.assertIn('AED',html)
            for code in re.findall(r'<script[^>]*>(.*?)</script>',html,re.S):
                result=subprocess.run(['node','--check'],input=code,text=True,encoding='utf-8',capture_output=True)
                self.assertEqual(result.returncode,0,template+result.stderr)

if __name__=='__main__':unittest.main()

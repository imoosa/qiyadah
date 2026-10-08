"""Real supply-chain routes and accounting postings using isolated records."""
import ast
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import unittest

from flask import Flask, abort
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from customer_models import (StockItem, StockPurchaseHistory, PurchaseOrder, PurchaseOrderItem,
    PurchaseInvoice, PurchaseInvoiceItem, SalesOrder, SalesOrderItem, DeliveryChallan, DeliveryChallanItem,
    CustomerInvoice, CustomerInvoiceItem, Client, Supplier, OrderFlow, OrderFlowHistory, OrderDepartment,
    ChartOfAccount, JournalEntry, JournalEntryLine, CRMLead, CRMQuotation)
from erp_routes import register_erp_routes
from order_erp_routes import register_order_erp_routes
from crm_routes import register_crm_routes


class ModuleHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        names = {'_money', '_post_auto_journal', '_auto_post_customer_invoice', '_auto_post_purchase_invoice'}
        tree = ast.parse(Path('app.py').read_text(encoding='utf-8-sig'))
        cls.posting_code = compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[]), 'posting', 'exec')

    def setUp(self):
        self.engine = create_engine('sqlite://')
        for model in (StockItem, StockPurchaseHistory, PurchaseOrder, PurchaseOrderItem, PurchaseInvoice,
                      PurchaseInvoiceItem, SalesOrder, SalesOrderItem, DeliveryChallan, DeliveryChallanItem,
                      CustomerInvoice, CustomerInvoiceItem, Client, Supplier, OrderFlow, OrderFlowHistory,
                      OrderDepartment, ChartOfAccount, JournalEntry, JournalEntryLine, CRMLead, CRMQuotation):
            model.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.denied = set()
        self.modules = {'core': True, 'orderflow': True, 'crm': True}
        self.company_id = 'A'
        self.app = Flask(__name__)
        self.app.config.update(TESTING=True, SECRET_KEY='test')
        self.app.extensions['module_access'] = lambda key: self.modules.get(key, False)
        def permission(module, action):
            def decorate(fn):
                @wraps(fn)
                def wrapped(*args, **kwargs):
                    if not self.can(module, action): abort(403)
                    return fn(*args, **kwargs)
                return wrapped
            return decorate
        ns = dict(Decimal=Decimal, InvalidOperation=InvalidOperation, ROUND_HALF_UP=ROUND_HALF_UP,
            _MONEY_Q=Decimal('.01'), datetime=datetime, JournalEntry=JournalEntry, JournalEntryLine=JournalEntryLine,
            _ensure_journal_tables=lambda db: None, get_current_user=lambda: {'email': 'test'},
            _coa_by_code=lambda db, cid, code: db.query(ChartOfAccount).filter_by(company_id=cid, code=code).one(),
            _existing_source_journal=lambda db, cid, kind, pk: db.query(JournalEntry).filter_by(company_id=cid, source_type=kind, source_id=str(pk), status='Posted').first(),
            _next_journal_number=lambda db, cid: 'J'+str(db.query(JournalEntry).count()+1))
        exec(self.posting_code, ns)
        self.post_sale = Mock(side_effect=ns['_auto_post_customer_invoice'])
        self.post_purchase = Mock(side_effect=ns['_auto_post_purchase_invoice'])
        register_erp_routes(self.app, lambda f:f, permission, lambda:self.db, lambda:self.company_id,
                            lambda x:x, self.post_sale, self.post_purchase)
        register_order_erp_routes(self.app, lambda f:f, lambda:self.db, lambda:self.company_id,
                                 lambda:{'role':'owner','email':'test'}, lambda cid: None, self.can)
        register_crm_routes(self.app, lambda f:f, lambda:self.db, lambda:self.company_id,
                           lambda:{'role':'owner','email':'test'}, lambda cid: None)
        self.app.add_url_rule('/invoice/<int:cust_inv_id>', 'customer_invoice_view', lambda **kw:'')
        self.app.add_url_rule('/purchase/<invoice_id>', 'purchase_invoice_view', lambda **kw:'')
        self.client = self.app.test_client()
        self.company_patch = patch('erp_routes.Company', SimpleNamespace(query=Mock()))
        company = self.company_patch.start()
        company.query.filter_by.return_value.first.return_value = SimpleNamespace(currency='AED', tax_regime='VAT')
        for code in ('1300','4100','2200','5100','1500','2100'):
            self.db.add(ChartOfAccount(company_id='A', code=code, name=code, account_type='Asset', account_group='Test', normal_balance='Debit'))
        self.stock = StockItem(company_id='A', code='W', name='Widget', quantity=0, purchase_rate=10)
        self.db.add(self.stock); self.db.flush()
        self.po = PurchaseOrder(company_id='A', po_number='PO1', status='Sent', supplier_name='Supplier',
                                subtotal=100, tax_amount=5, grand_total=105, igst_total=5)
        self.po.items.append(PurchaseOrderItem(stock_item_id=self.stock.id, item_name='Widget', item_code='W',
            quantity=10, rate=10, taxable_amount=100, gst_percent=5, igst_amount=5, total_amount=105))
        self.so = SalesOrder(company_id='A', order_no='SO1', status='Confirmed', client_name='Buyer',
                            subtotal=60, tax_amount=3, grand_total=63, igst_total=3)
        self.so.items.append(SalesOrderItem(stock_item_id=self.stock.id, item_name='Widget', item_code='W',
            quantity=3, rate=20, taxable_amount=60, gst_percent=5, igst_amount=3, total_amount=63))
        self.db.add_all([self.po,self.so]); self.db.commit()

    def tearDown(self):
        self.company_patch.stop(); self.db.close(); self.engine.dispose()

    def can(self, module, action='view'):
        return module not in self.denied

    def buy(self):
        return self.client.post(f'/purchase-order/{self.po.id}/convert-to-bill')

    def dispatch(self):
        return self.client.post(f'/sales-order/{self.so.id}/convert-to-challan')

    def test_purchase_production_dispatch_invoice_and_journal_chain(self):
        purchase = self.buy(); self.assertEqual(purchase.status_code,302)
        self.assertEqual(self.buy().location,purchase.location)
        self.assertEqual(self.stock.quantity,10)
        self.assertEqual(self.po.items[0].received_qty,10)
        production = self.client.post(f'/api/order-erp/sales-orders/{self.so.id}/send-to-production')
        self.assertEqual(production.status_code,200)
        again = self.client.post(f'/api/order-erp/sales-orders/{self.so.id}/send-to-production')
        self.assertTrue(again.json['already_exists'])
        self.assertEqual(self.db.query(OrderFlow).one().sales_order_id,self.so.id)
        dispatch = self.dispatch(); self.assertEqual(dispatch.status_code,302)
        self.assertEqual(self.dispatch().location,dispatch.location)
        self.assertEqual(self.stock.quantity,7)
        self.assertEqual(self.so.items[0].delivered_qty,3)
        challan = self.db.query(DeliveryChallan).one()
        response = self.client.post(f'/delivery-challan/{challan.id}/convert-to-invoice')
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.post(f'/delivery-challan/{challan.id}/convert-to-invoice').location,response.location)
        invoice = self.db.query(CustomerInvoice).one()
        self.assertEqual((invoice.currency,invoice.igst_total,invoice.cgst_total),('AED',3,0))
        self.assertEqual(invoice.sales_order_id,self.so.id)
        self.assertEqual(invoice.items[0].stock_item_id,self.stock.id)
        self.assertIsNone(invoice.items[0].booking_invoice_id)
        self.assertEqual(self.db.query(StockPurchaseHistory).count(),2)
        self.assertEqual(self.db.query(JournalEntry).count(),2)
        for entry in self.db.query(JournalEntry):
            self.assertEqual(sum(line.debit for line in entry.lines),sum(line.credit for line in entry.lines))
        self.post_sale.assert_called_once(); self.post_purchase.assert_called_once()
        detail = self.client.get('/api/order-erp/orders/'+production.json['order_flow_id']).json
        self.assertEqual(len(detail['related_documents']),2)

    def test_invoice_first_then_dispatch_reuses_invoice(self):
        self.buy()
        self.client.post(f'/sales-order/{self.so.id}/convert-to-invoice')
        self.dispatch()
        challan = self.db.query(DeliveryChallan).one()
        self.client.post(f'/delivery-challan/{challan.id}/convert-to-invoice')
        self.assertEqual(self.db.query(CustomerInvoice).count(),1)
        self.assertEqual(self.stock.quantity,7)
        self.post_sale.assert_called_once()

    def test_failed_accounting_rolls_back_stock_and_document(self):
        self.post_purchase.side_effect=RuntimeError('posting failed')
        with self.assertRaises(RuntimeError): self.buy()
        self.assertEqual(self.db.query(PurchaseInvoice).count(),0)
        self.assertEqual(self.stock.quantity,0)
        self.assertEqual(self.po.status,'Sent')
        self.assertEqual(self.db.query(StockPurchaseHistory).count(),0)

    def test_insufficient_stock_does_not_dispatch(self):
        self.dispatch()
        self.assertEqual(self.db.query(DeliveryChallan).count(),0)
        self.assertEqual(self.so.status,'Confirmed')

    def test_post_only_permissions_and_company_boundaries(self):
        self.assertEqual(self.client.get(f'/purchase-order/{self.po.id}/convert-to-bill').status_code,405)
        self.assertEqual(self.client.get(f'/sales-order/{self.so.id}/convert-to-challan').status_code,405)
        self.denied.add('purchase')
        self.assertEqual(self.buy().status_code,403)
        self.denied.clear(); self.company_id='B'
        self.assertEqual(self.buy().status_code,404)
        self.assertEqual(self.dispatch().status_code,404)

    def test_crm_conversion_is_idempotent_and_can_create_linked_draft(self):
        lead=CRMLead(id='LEAD',company_id='A',title='Widget request',client_name='Buyer',estimated_value=80,stage='Won')
        self.db.add(lead); self.db.commit()
        response=self.client.post('/api/crm/leads/LEAD/convert',json={})
        self.assertEqual(response.status_code,200)
        repeat=self.client.post('/api/crm/leads/LEAD/convert',json={})
        self.assertEqual(response.json['order_id'],repeat.json['order_id'])
        order_id=response.json['order_id']
        response=self.client.post(f'/api/order-erp/orders/{order_id}/sales-order')
        self.assertEqual(response.status_code,200)
        repeat=self.client.post(f'/api/order-erp/orders/{order_id}/sales-order')
        self.assertEqual(response.json['sales_order_id'],repeat.json['sales_order_id'])
        draft=self.db.get(SalesOrder,response.json['sales_order_id'])
        self.assertEqual(draft.status,'Draft')
        self.assertEqual(draft.reference_no,order_id)
        self.assertEqual(draft.grand_total,0)

    def test_orderflow_does_not_bypass_core_record_permissions(self):
        self.modules['core']=False
        self.assertEqual(self.client.get('/api/order-erp/sales-orders').status_code,403)
        self.assertEqual(self.client.get('/api/order-erp/clients').status_code,403)
        self.assertEqual(self.client.get('/api/order-erp/products').status_code,403)


if __name__ == '__main__':
    unittest.main()

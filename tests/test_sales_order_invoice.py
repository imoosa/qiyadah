"""Sales order conversion, using an isolated database without app startup."""
import unittest
from functools import wraps
from types import SimpleNamespace
from unittest.mock import Mock, patch

from flask import Flask, abort
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from customer_models import SalesOrder, SalesOrderItem, CustomerInvoice, CustomerInvoiceItem, Client
from erp_routes import register_erp_routes


class SalesOrderInvoiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        for model in (SalesOrder, SalesOrderItem, CustomerInvoice, CustomerInvoiceItem, Client):
            model.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.allowed = True
        self.app = Flask(__name__)
        self.app.secret_key = 'test'
        self.app.testing = True
        def permission(module, action):
            def decorate(fn):
                @wraps(fn)
                def wrapped(*args, **kwargs):
                    if not self.allowed:
                        abort(403)
                    return fn(*args, **kwargs)
                return wrapped
            return decorate
        self.post = Mock()
        register_erp_routes(self.app, lambda fn: fn, permission, lambda: self.db,
                            lambda: 'A', lambda value: value, self.post)
        self.app.add_url_rule('/invoice/<int:cust_inv_id>', 'customer_invoice_view', lambda **kw: '')
        self.client = self.app.test_client()
        self.company = patch('erp_routes.Company', SimpleNamespace(query=Mock()))
        company = self.company.start()
        company.query.filter_by.return_value.first.return_value = SimpleNamespace(currency='INR', tax_regime='INDIA_GST')
        self.order = SalesOrder(company_id='A', order_no='SO-1', status='Confirmed', client_name='Buyer',
                                subtotal=180, tax_amount=32.4, grand_total=212.4, cgst_total=16.2, sgst_total=16.2,
                                terms='Delivery in 7 days', notes='Handle carefully')
        self.order.items.append(SalesOrderItem(item_name='Widget', item_code='W1', hsn='1234', quantity=2,
                                             rate=100, unit='pcs', discount_percent=10, taxable_amount=180,
                                             gst_percent=18, cgst_amount=16.2, sgst_amount=16.2, total_amount=212.4))
        self.db.add(self.order)
        self.db.commit()
        self.url = f'/sales-order/{self.order.id}/convert-to-invoice'

    def tearDown(self):
        self.company.stop()
        self.db.close()
        self.engine.dispose()

    def test_conversion_copies_products_and_posts_once(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 302)
        invoice = self.db.query(CustomerInvoice).one()
        self.assertEqual(invoice.sales_order_id, self.order.id)
        self.assertEqual(invoice.terms, self.order.terms)
        self.assertEqual(invoice.balance, 212.4)
        self.assertEqual(invoice.base_grand_total, 212.4)
        self.assertEqual(self.order.status, 'Invoiced')
        item = invoice.items[0]
        self.assertEqual((item.item_name, item.item_code, item.hsn, item.quantity, item.rate, item.discount_percent),
                         ('Widget', 'W1', '1234', 2, 100, 10))
        self.assertIsNone(item.booking_invoice_id)
        self.post.assert_called_once_with(self.db, 'A', invoice)
        again = self.client.post(self.url)
        self.assertEqual(again.location, response.location)
        self.assertEqual(self.db.query(CustomerInvoice).count(), 1)
        self.post.assert_called_once()
        self.assertEqual(self.order.to_dict()['sales_invoice_id'], invoice.id)

    def test_unconfirmed_orders_are_rejected(self):
        for status in ('Draft', 'Cancelled', 'Shipped', 'Invoiced'):
            self.order.status = status
            self.db.commit()
            self.assertEqual(self.client.post(self.url).status_code, 302)
            self.assertEqual(self.db.query(CustomerInvoice).count(), 0)
        self.post.assert_not_called()

    def test_get_permission_and_company_boundaries(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.allowed = False
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.allowed = True
        self.order.company_id = 'B'
        self.db.commit()
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.assertEqual(self.db.query(CustomerInvoice).count(), 0)

    def test_empty_order_is_rejected(self):
        self.order.items.clear()
        self.db.commit()
        self.client.post(self.url)
        self.assertEqual(self.db.query(CustomerInvoice).count(), 0)

    def test_accounting_failure_rolls_back_conversion(self):
        self.post.side_effect = RuntimeError('Posting failed')
        with self.assertRaises(RuntimeError):
            self.client.post(self.url)
        self.assertEqual(self.db.query(CustomerInvoice).count(), 0)
        self.assertEqual(self.db.query(CustomerInvoiceItem).count(), 0)
        self.assertEqual(self.order.status, 'Confirmed')

if __name__ == '__main__':
    unittest.main()

"""Whitelisted chart field wells over canonical ERP rows; no user SQL."""
from collections import defaultdict
from datetime import timedelta, date, datetime
from decimal import Decimal
from customer_models import Client, Supplier
from .filters import BIValidationError
from .queries import base_amount, expense_query, money, purchase_query, sales_query, stock_query

CATALOG = {
    'sales': {
        'label': 'Sales Invoices',
        'domain': 'sales',
        'table_name': 'customer_invoices',
        'is_sub_table': False,
        'icon': '📊',
        'measures': {
            'subtotal': 'Net sales · excl. tax',
            'grand_total': 'Billed sales (Gross)',
            'tax_amount': 'Sales tax (GST / VAT)',
            'paid_amount': 'Paid amount received',
            'outstanding': 'Outstanding receivables',
            'count': 'Invoice count'
        },
        'dimensions': {
            'period': 'Invoice date',
            'customer': 'Customer / Client',
            'country': 'Customer country',
            'invoice_category': 'Invoice type',
            'payment_status': 'Payment status'
        },
    },
    'sales_items': {
        'label': 'Sales Line Items',
        'domain': 'sales',
        'table_name': 'customer_invoice_items',
        'parent_source': 'sales',
        'is_sub_table': True,
        'icon': '📦',
        'measures': {
            'subtotal': 'Item net sales',
            'quantity': 'Quantity sold',
            'tax_amount': 'Item tax',
            'count': 'Line items count'
        },
        'dimensions': {
            'item_name': 'Product / Item name',
            'category': 'Item description / category',
            'period': 'Sale date'
        },
    },
    'purchase': {
        'label': 'Purchase Invoices',
        'domain': 'purchase',
        'table_name': 'purchase_invoices',
        'is_sub_table': False,
        'icon': '🛒',
        'measures': {
            'subtotal': 'Purchase cost · excl. tax',
            'grand_total': 'Purchase total (Gross)',
            'tax_amount': 'Purchase tax',
            'paid_amount': 'Paid amount',
            'outstanding': 'Outstanding payables',
            'count': 'Purchase invoice count'
        },
        'dimensions': {
            'period': 'Purchase date',
            'supplier': 'Supplier / Vendor',
            'country': 'Supplier country',
            'status': 'Purchase status'
        },
    },
    'purchase_items': {
        'label': 'Purchase Line Items',
        'domain': 'purchase',
        'table_name': 'purchase_invoice_items',
        'parent_source': 'purchase',
        'is_sub_table': True,
        'icon': '📋',
        'measures': {
            'subtotal': 'Item purchase cost',
            'quantity': 'Quantity purchased',
            'count': 'Line items count'
        },
        'dimensions': {
            'item_name': 'Purchased item name',
            'category': 'Item description / category',
            'period': 'Purchase date'
        },
    },
    'expenses': {
        'label': 'Expenses & Overheads',
        'domain': 'expenses',
        'table_name': 'expenses',
        'is_sub_table': False,
        'icon': '💸',
        'measures': {
            'amount': 'Expense amount',
            'tax_amount': 'Tax amount',
            'count': 'Expense count'
        },
        'dimensions': {
            'period': 'Expense date',
            'category': 'Expense category',
            'payment_mode': 'Payment mode'
        },
    },
    'stock': {
        'label': 'Stock & Inventory',
        'domain': 'stock',
        'table_name': 'stock_items',
        'is_sub_table': False,
        'icon': '🏢',
        'measures': {
            'value': 'Stock valuation',
            'quantity': 'Current stock quantity',
            'reorder_level': 'Reorder threshold',
            'count': 'Item count'
        },
        'dimensions': {
            'category': 'Stock category',
            'item': 'Stock item / SKU',
            'brand': 'Brand / Supplier'
        },
    },
    'finance': {
        'label': 'General Ledger & Accounts',
        'domain': 'finance',
        'table_name': 'journal_entries',
        'is_sub_table': False,
        'icon': '📒',
        'measures': {
            'debit': 'Total debit',
            'credit': 'Total credit',
            'net_balance': 'Net flow (Debit - Credit)',
            'count': 'Journal entry count'
        },
        'dimensions': {
            'account_name': 'Account title',
            'account_type': 'Account type (Asset/Liab/Exp/Rev)',
            'period': 'Entry date'
        }
    },
    'hr': {
        'label': 'HR & Payroll',
        'domain': 'hr',
        'table_name': 'hr_employees',
        'is_sub_table': False,
        'icon': '👥',
        'measures': {
            'salary': 'Salary payout',
            'count': 'Headcount / Employee count'
        },
        'dimensions': {
            'department': 'Department',
            'designation': 'Designation / Role',
            'period': 'Joining date'
        }
    }
}

SCHEMA_TREE = [
    {
        'id': 'sales',
        'label': 'Sales Invoices',
        'icon': '📊',
        'table': 'customer_invoices',
        'fields': [
            {'key': 'period', 'label': 'Invoice Date', 'type': 'dimension', 'kind': 'date', 'icon': '📅'},
            {'key': 'customer', 'label': 'Customer Name', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'country', 'label': 'Customer Country', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'invoice_category', 'label': 'Invoice Category', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'payment_status', 'label': 'Payment Status', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'subtotal', 'label': 'Net Sales Amount', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'grand_total', 'label': 'Total Billed (Gross)', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'tax_amount', 'label': 'Sales Tax (GST)', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'paid_amount', 'label': 'Paid Amount', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'outstanding', 'label': 'Receivable Due', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'count', 'label': 'Invoice Count', 'type': 'measure', 'kind': 'number', 'icon': '🔢'},
        ],
        'sub_tables': [
            {
                'id': 'sales_items',
                'label': 'Sales Line Items (Sub-table)',
                'icon': '📦',
                'table': 'customer_invoice_items',
                'fields': [
                    {'key': 'item_name', 'label': 'Item / Product Name', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
                    {'key': 'category', 'label': 'Item Description', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
                    {'key': 'period', 'label': 'Sale Date', 'type': 'dimension', 'kind': 'date', 'icon': '📅'},
                    {'key': 'subtotal', 'label': 'Item Net Sales', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
                    {'key': 'quantity', 'label': 'Quantity Sold', 'type': 'measure', 'kind': 'number', 'icon': '🔢'},
                    {'key': 'tax_amount', 'label': 'Item Tax', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
                    {'key': 'count', 'label': 'Line Count', 'type': 'measure', 'kind': 'number', 'icon': '🔢'},
                ]
            }
        ]
    },
    {
        'id': 'purchase',
        'label': 'Purchase Invoices',
        'icon': '🛒',
        'table': 'purchase_invoices',
        'fields': [
            {'key': 'period', 'label': 'Purchase Date', 'type': 'dimension', 'kind': 'date', 'icon': '📅'},
            {'key': 'supplier', 'label': 'Supplier Name', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'country', 'label': 'Supplier Country', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'status', 'label': 'Bill Status', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'subtotal', 'label': 'Net Purchase Cost', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'grand_total', 'label': 'Total Billed (Gross)', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'tax_amount', 'label': 'Purchase Tax', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'paid_amount', 'label': 'Paid Amount', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'outstanding', 'label': 'Payable Balance', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'count', 'label': 'Bill Count', 'type': 'measure', 'kind': 'number', 'icon': '🔢'},
        ],
        'sub_tables': [
            {
                'id': 'purchase_items',
                'label': 'Purchase Line Items (Sub-table)',
                'icon': '📋',
                'table': 'purchase_invoice_items',
                'fields': [
                    {'key': 'item_name', 'label': 'Purchased Item Name', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
                    {'key': 'category', 'label': 'Item Category', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
                    {'key': 'period', 'label': 'Purchase Date', 'type': 'dimension', 'kind': 'date', 'icon': '📅'},
                    {'key': 'subtotal', 'label': 'Item Purchase Cost', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
                    {'key': 'quantity', 'label': 'Quantity Purchased', 'type': 'measure', 'kind': 'number', 'icon': '🔢'},
                    {'key': 'count', 'label': 'Line Count', 'type': 'measure', 'kind': 'number', 'icon': '🔢'},
                ]
            }
        ]
    },
    {
        'id': 'expenses',
        'label': 'Expenses & Overheads',
        'icon': '💸',
        'table': 'expenses',
        'fields': [
            {'key': 'period', 'label': 'Expense Date', 'type': 'dimension', 'kind': 'date', 'icon': '📅'},
            {'key': 'category', 'label': 'Expense Category', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'payment_mode', 'label': 'Payment Mode', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'amount', 'label': 'Expense Amount', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'tax_amount', 'label': 'Tax Amount', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'count', 'label': 'Expense Count', 'type': 'measure', 'kind': 'number', 'icon': '🔢'},
        ],
        'sub_tables': []
    },
    {
        'id': 'stock',
        'label': 'Stock & Inventory',
        'icon': '🏢',
        'table': 'stock_items',
        'fields': [
            {'key': 'category', 'label': 'Stock Category', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'item', 'label': 'Item / SKU Name', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'brand', 'label': 'Brand / Supplier', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'value', 'label': 'Inventory Value', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'quantity', 'label': 'Stock Quantity', 'type': 'measure', 'kind': 'number', 'icon': '🔢'},
            {'key': 'reorder_level', 'label': 'Reorder Threshold', 'type': 'measure', 'kind': 'number', 'icon': '🔢'},
            {'key': 'count', 'label': 'Item Count', 'type': 'measure', 'kind': 'number', 'icon': '🔢'},
        ],
        'sub_tables': []
    },
    {
        'id': 'finance',
        'label': 'General Ledger & Accounts',
        'icon': '📒',
        'table': 'journal_entries',
        'fields': [
            {'key': 'account_name', 'label': 'Account Title', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'account_type', 'label': 'Account Type', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'period', 'label': 'Journal Date', 'type': 'dimension', 'kind': 'date', 'icon': '📅'},
            {'key': 'debit', 'label': 'Total Debit', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'credit', 'label': 'Total Credit', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'net_balance', 'label': 'Net Debit Flow', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'count', 'label': 'Entry Count', 'type': 'measure', 'kind': 'number', 'icon': '🔢'},
        ],
        'sub_tables': []
    },
    {
        'id': 'hr',
        'label': 'HR & Payroll',
        'icon': '👥',
        'table': 'hr_employees',
        'fields': [
            {'key': 'department', 'label': 'Department', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'designation', 'label': 'Designation / Role', 'type': 'dimension', 'kind': 'string', 'icon': '🔤'},
            {'key': 'period', 'label': 'Joining Date', 'type': 'dimension', 'kind': 'date', 'icon': '📅'},
            {'key': 'salary', 'label': 'Salary Payout', 'type': 'measure', 'kind': 'money', 'icon': '🔢'},
            {'key': 'count', 'label': 'Headcount', 'type': 'measure', 'kind': 'number', 'icon': '🔢'},
        ],
        'sub_tables': []
    }
]

GRAINS = ('day', 'month', 'quarter', 'year')
SORTS = ('value_desc', 'value_asc', 'name_asc')
LIMITS = (5, 10, 20, 50, 100)
AGGREGATIONS = ('sum', 'avg', 'count', 'min', 'max')
FIELDS = ('semantic_source', 'semantic_measure', 'semantic_dimension', 'semantic_grain',
          'semantic_aggregation', 'semantic_sort', 'semantic_limit', 'semantic_measures')
DEFAULT = {'semantic_source': 'sales', 'semantic_measure': 'subtotal',
           'semantic_dimension': 'period', 'semantic_grain': 'month',
           'semantic_aggregation': 'sum', 'semantic_sort': 'name_asc',
           'semantic_limit': 20}


def validate_spec(raw):
    if not isinstance(raw, dict):
        raise BIValidationError('Chart fields must be an object.')
    spec = {key: raw.get(key, value) for key, value in DEFAULT.items()}
    source = spec['semantic_source']
    if not isinstance(source, str) or source not in CATALOG:
        raise BIValidationError('Choose an approved ERP source.')
    catalog = CATALOG[source]
    if (not isinstance(spec['semantic_measure'], str) or not isinstance(spec['semantic_dimension'], str)
            or spec['semantic_measure'] not in catalog['measures']
            or spec['semantic_dimension'] not in catalog['dimensions']):
        raise BIValidationError('The measure and breakdown must belong to the same ERP source.')
    if spec['semantic_grain'] not in GRAINS or spec['semantic_sort'] not in SORTS or type(spec['semantic_limit']) is not int or spec['semantic_limit'] not in LIMITS:
        raise BIValidationError('Unsupported chart grouping, sort, or row limit.')
    expected_aggregations = ('count',) if spec['semantic_measure'] == 'count' else ('sum', 'avg', 'min', 'max')
    if spec['semantic_aggregation'] not in expected_aggregations:
        raise BIValidationError('Use count for record counts and sum, average, min or max for amounts.')
    measures = raw.get('semantic_measures', [spec['semantic_measure']])
    if (not isinstance(measures, list) or not 1 <= len(measures) <= 4
            or any(not isinstance(m, str) or m not in catalog['measures'] for m in measures)
            or len(set(measures)) != len(measures) or measures[0] != spec['semantic_measure']):
        raise BIValidationError('Choose one to four distinct measures from this source; the primary measure must come first.')
    spec['semantic_measures'] = measures
    return spec


def catalog_payload():
    return {
        'sources': CATALOG,
        'grains': list(GRAINS),
        'sorts': list(SORTS),
        'limits': list(LIMITS),
        'aggregations': list(AGGREGATIONS),
        'defaults': DEFAULT,
        'tree': SCHEMA_TREE
    }


def _date_bucket(day, grain):
    if not day:
        return 'Unknown'
    if isinstance(day, str):
        try:
            day = date.fromisoformat(day[:10])
        except Exception:
            return day
    if grain == 'day':
        return day.isoformat()
    if grain == 'quarter':
        return f'{day.year}-Q{(day.month - 1) // 3 + 1}'
    if grain == 'year':
        return str(day.year)
    return day.strftime('%Y-%m')


def _rows(cdb, filters, can, spec):
    source = spec['semantic_source']
    permission = {
        'sales': can('customer_invoices', 'view') or can('invoices', 'view') or can('analytics', 'view'),
        'sales_items': can('customer_invoices', 'view') or can('invoices', 'view') or can('analytics', 'view'),
        'purchase': can('purchase', 'view') or can('analytics', 'view'),
        'purchase_items': can('purchase', 'view') or can('analytics', 'view'),
        'expenses': can('expenses', 'view') or can('analytics', 'view'),
        'stock': can('stock', 'view') or can('analytics', 'view'),
        'finance': can('finance', 'view') or can('analytics', 'view'),
        'hr': can('hr', 'view') or can('analytics', 'view')
    }
    if not permission.get(source, False):
        raise BIValidationError('You do not have permission to view this ERP source.')
    
    if source == 'sales':
        return sales_query(cdb, filters, filters.from_date, filters.to_date).all()
    
    if source == 'sales_items':
        try:
            from customer_models import CustomerInvoice, CustomerInvoiceItem
            q = cdb.query(CustomerInvoiceItem, CustomerInvoice.invoice_date).join(
                CustomerInvoice, CustomerInvoiceItem.customer_invoice_id == CustomerInvoice.id
            ).filter(
                CustomerInvoice.company_id == filters.company_id,
                CustomerInvoice.invoice_date >= filters.from_date,
                CustomerInvoice.invoice_date <= filters.to_date
            )
            return q.all()
        except Exception:
            return []

    if source == 'purchase':
        return purchase_query(cdb, filters, filters.from_date, filters.to_date).all()
        
    if source == 'purchase_items':
        try:
            from customer_models import PurchaseInvoice, PurchaseInvoiceItem
            q = cdb.query(PurchaseInvoiceItem, PurchaseInvoice.date).join(
                PurchaseInvoice, PurchaseInvoiceItem.purchase_invoice_id == PurchaseInvoice.id
            ).filter(
                PurchaseInvoice.company_id == filters.company_id,
                PurchaseInvoice.date >= filters.from_date,
                PurchaseInvoice.date <= filters.to_date
            )
            return q.all()
        except Exception:
            return []

    if source == 'expenses':
        return expense_query(cdb, filters, filters.from_date, filters.to_date).all()
        
    if source == 'stock':
        return stock_query(cdb, filters).all()
        
    if source == 'finance':
        try:
            from customer_models import JournalEntry, JournalEntryLine, ChartOfAccount
            q = cdb.query(JournalEntryLine, JournalEntry, ChartOfAccount).join(
                JournalEntry, JournalEntryLine.entry_id == JournalEntry.id
            ).join(
                ChartOfAccount, JournalEntryLine.account_id == ChartOfAccount.id
            ).filter(
                JournalEntry.company_id == filters.company_id,
                JournalEntry.entry_date >= filters.from_date,
                JournalEntry.entry_date <= filters.to_date
            )
            return q.all()
        except Exception:
            return []
            
    if source == 'hr':
        try:
            from customer_models import HREmployee
            return cdb.query(HREmployee).filter(HREmployee.company_id == filters.company_id).all()
        except Exception:
            return []
            
    return []


def _lookup(cdb, filters, source):
    if source in ('sales', 'sales_items'):
        return {r.id: r for r in cdb.query(Client).filter_by(company_id=filters.company_id).all()}
    if source in ('purchase', 'purchase_items'):
        return {r.id: r for r in cdb.query(Supplier).filter_by(company_id=filters.company_id).all()}
    return {}


def _group(row, spec, lookup):
    source, dim = spec['semantic_source'], spec['semantic_dimension']
    
    if source == 'sales_items':
        item, day = row if isinstance(row, tuple) else (row, getattr(row, 'invoice_date', None))
        if dim == 'period':
            label = _date_bucket(day, spec['semantic_grain'])
            return label, label
        if dim == 'item_name':
            label = getattr(item, 'item_name', None) or getattr(item, 'item_description', None) or 'Unspecified Item'
            return label, label
        label = getattr(item, 'item_description', None) or getattr(item, 'item_name', None) or 'Uncategorised'
        return label, label

    if source == 'purchase_items':
        item, day = row if isinstance(row, tuple) else (row, getattr(row, 'date', None))
        if dim == 'period':
            label = _date_bucket(day, spec['semantic_grain'])
            return label, label
        if dim == 'item_name':
            label = getattr(item, 'item_name', None) or getattr(item, 'description', None) or 'Unspecified Item'
            return label, label
        label = getattr(item, 'description', None) or getattr(item, 'item_name', None) or 'Uncategorised'
        return label, label

    if source == 'finance':
        line, entry, account = row if isinstance(row, tuple) else (row, getattr(row, 'entry', None), getattr(row, 'account', None))
        if dim == 'period':
            day = getattr(entry, 'entry_date', None) or getattr(line, 'date', None)
            label = _date_bucket(day, spec['semantic_grain'])
            return label, label
        if dim == 'account_name':
            label = getattr(account, 'account_name', None) or 'General Account'
            return label, label
        label = getattr(account, 'account_type', None) or 'General'
        return label, label

    if source == 'hr':
        if dim == 'period':
            day = getattr(row, 'date_of_joining', None) or getattr(row, 'created_at', None) or date.today()
            label = _date_bucket(day, spec['semantic_grain'])
            return label, label
        if dim == 'department':
            label = getattr(row, 'department', None) or 'General Department'
            return label, label
        label = getattr(row, 'designation', None) or 'Employee'
        return label, label

    if dim == 'period':
        day = row.invoice_date if source == 'sales' else row.date
        label = _date_bucket(day, spec['semantic_grain'])
        return label, label
        
    if source == 'sales':
        client = lookup.get(row.client_id)
        if dim == 'customer':
            label = client.name if client else row.client_name or 'Unlinked customer'
            return label, label
        if dim == 'country':
            if not client:
                return None
            label = (client.country or 'Unspecified').strip() or 'Unspecified'
            return label, label
        if dim == 'payment_status':
            label = (getattr(row, 'payment_status', None) or getattr(row, 'status', None) or 'Pending').title()
            return label, label
        label = row.invoice_category if row.invoice_category in ('product_sale', 'workshop_repair') else 'Other'
        return label, label.replace('_', ' ').title()
        
    if source == 'purchase':
        supplier = lookup.get(row.supplier_id)
        if dim == 'supplier':
            label = supplier.name if supplier else row.supplier_name or 'Unspecified'
            return label, label
        if dim == 'country':
            if not supplier:
                return None
            label = (supplier.country or 'Unspecified').strip() or 'Unspecified'
            return label, label
        if dim == 'status':
            label = (getattr(row, 'status', None) or 'Completed').title()
            return label, label
        label = getattr(row, 'status', None) or 'Standard'
        return label, label
        
    if source == 'expenses':
        if dim == 'payment_mode':
            label = (getattr(row, 'payment_mode', None) or 'Cash').title()
            return label, label
        label = row.category or 'Uncategorised'
        return label, label
        
    if source == 'stock':
        if dim == 'item':
            return str(row.id), f'{row.code} · {row.name}'
        if dim == 'brand':
            label = getattr(row, 'brand', None) or getattr(row, 'supplier_name', None) or 'Standard'
            return label, label
        label = row.category or 'Uncategorised'
        return label, label
        
    return 'Default', 'Default'


def _value(row, spec, currency):
    source, measure = spec['semantic_source'], spec['semantic_measure']
    if measure == 'count':
        return Decimal(1)
        
    if source == 'sales_items':
        item = row[0] if isinstance(row, tuple) else row
        if measure == 'quantity':
            return Decimal(str(getattr(item, 'quantity', 0) or 0))
        if measure == 'tax_amount':
            cgst = getattr(item, 'cgst_amount', 0) or 0
            sgst = getattr(item, 'sgst_amount', 0) or 0
            igst = getattr(item, 'igst_amount', 0) or 0
            return Decimal(str(cgst + sgst + igst))
        val = getattr(item, 'taxable_amount', None) or getattr(item, 'base_taxable_amount', None) or getattr(item, 'total_amount', 0) or 0
        return Decimal(str(val))

    if source == 'purchase_items':
        item = row[0] if isinstance(row, tuple) else row
        if measure == 'quantity':
            return Decimal(str(getattr(item, 'quantity', 0) or 0))
        val = getattr(item, 'taxable_value', None) or getattr(item, 'taxable_amount', None) or getattr(item, 'total_amount', 0) or 0
        return Decimal(str(val))

    if source == 'finance':
        line = row[0] if isinstance(row, tuple) else row
        debit = Decimal(str(getattr(line, 'debit', 0) or 0))
        credit = Decimal(str(getattr(line, 'credit', 0) or 0))
        if measure == 'debit':
            return debit
        if measure == 'credit':
            return credit
        return debit - credit

    if source == 'hr':
        val = getattr(row, 'base_salary', None) or getattr(row, 'monthly_ctc', None) or getattr(row, 'salary', 0) or 0
        return Decimal(str(val))

    if source in ('sales', 'purchase'):
        if measure in ('paid_amount', 'outstanding'):
            grand = base_amount(row, 'base_grand_total', 'grand_total', currency)
            paid = Decimal(str(getattr(row, 'paid_amount', 0) or 0))
            if measure == 'paid_amount':
                return paid
            return max(Decimal(0), grand - paid)
        return base_amount(row, 'base_' + measure, measure, currency)
        
    if source == 'expenses':
        if measure == 'tax_amount':
            return Decimal(str(getattr(row, 'tax_amount', 0) or 0))
        return money(row.amount)
        
    if measure == 'quantity':
        return money(row.quantity)
    if measure == 'reorder_level':
        return Decimal(str(getattr(row, 'min_quantity', 0) or getattr(row, 'reorder_level', 0) or 0))
    return money(row.quantity) * money(row.avg_purchase_rate or row.last_purchase_rate or row.purchase_rate or row.unit_price)


def _focus(filters, source):
    from .builder import focus_field, FOCUS_DOMAINS
    field = focus_field(filters)
    return field is not None and source not in FOCUS_DOMAINS.get(field, frozenset())


def _snapshot_note(spec, filters):
    source = spec['semantic_source']
    notes = []
    if source == 'stock':
        notes.append('Current stock snapshot; the date range does not change quantities.')
    if filters.product_category and source in ('sales', 'purchase', 'sales_items', 'purchase_items'):
        notes.append('Category matches invoices containing an item; full invoice amounts are grouped.')
    if source in ('sales', 'purchase') and (filters.country or spec['semantic_dimension'] == 'country'):
        notes.append('Country comes from the current customer or supplier master.')
    return notes


def visual(cdb, filters, can, currency, raw):
    spec = validate_spec(raw)
    source = spec['semantic_source']
    if _focus(filters, source):
        return {'not_applicable': True, 'rows': [], 'warnings': ['This source does not use the selected business filter.']}
    rows = _rows(cdb, filters, can, spec)
    lookup = _lookup(cdb, filters, source)
    measures = spec['semantic_measures']
    
    # Store list of raw values for advanced aggregations (min, max, avg, sum)
    groups = defaultdict(lambda: {'vals': {m: [] for m in measures}, 'count': 0, 'label': ''})
    
    for row in rows:
        group = _group(row, spec, lookup)
        if group is None:
            continue
        key, label = group
        cell = groups[str(key)]
        for measure in measures:
            v = _value(row, {**spec, 'semantic_measure': measure}, currency)
            cell['vals'][measure].append(v)
        cell['count'] += 1
        cell['label'] = label
        
    if spec['semantic_dimension'] == 'period' and spec['semantic_aggregation'] not in ('avg', 'min', 'max'):
        cursor = filters.from_date
        while cursor <= filters.to_date:
            label = _date_bucket(cursor, spec['semantic_grain'])
            groups[str(label)]['label'] = label
            cursor += timedelta(days=1)
            
    agg = spec['semantic_aggregation']
    records = []
    
    for key, cell in groups.items():
        count = cell['count']
        values = {}
        for m in measures:
            vals = cell['vals'][m]
            if m == 'count' or agg == 'count':
                res = count
            elif not vals:
                res = 0.0
            elif agg == 'avg':
                res = float(sum(vals) / len(vals))
            elif agg == 'min':
                res = float(min(vals))
            elif agg == 'max':
                res = float(max(vals))
            else:  # sum
                res = float(sum(vals))
            values[m] = round(res, 2)
            
        records.append({
            'key': key,
            'name': cell['label'] or key,
            'value': values[spec['semantic_measure']],
            'values': values,
            'count': count
        })
        
    order = spec['semantic_sort']
    if order == 'value_desc':
        records.sort(key=lambda r: (-r['value'], str(r['name'])))
    elif order == 'value_asc':
        records.sort(key=lambda r: (r['value'], str(r['name'])))
    else:
        records.sort(key=lambda r: str(r['key']))
        
    if spec['semantic_dimension'] == 'period' and order == 'name_asc' and len(records) > spec['semantic_limit']:
        records = records[-spec['semantic_limit']:]
    else:
        records = records[:spec['semantic_limit']]
        
    return {
        'rows': records,
        'source': source,
        'axis_label': CATALOG[source]['dimensions'][spec['semantic_dimension']],
        'series': [{
            'key': m,
            'label': CATALOG[source]['measures'][m],
            'value_kind': 'number' if m in ('count', 'quantity', 'reorder_level') else 'money'
        } for m in measures],
        'measure_label': CATALOG[source]['measures'][spec['semantic_measure']],
        'value_kind': 'number' if spec['semantic_measure'] in ('count', 'quantity', 'reorder_level') else 'money',
        'aggregation': spec['semantic_aggregation'],
        'warnings': _snapshot_note(spec, filters),
        'not_applicable': False
    }


def drill(cdb, filters, can, currency, raw, group):
    spec = validate_spec(raw)
    if not isinstance(group, str) or not 1 <= len(group) <= 240:
        raise BIValidationError('Choose a valid chart group.')
    source = spec['semantic_source']
    if _focus(filters, source):
        raise BIValidationError('This source does not use the selected business filter.')
    rows = _rows(cdb, filters, can, spec)
    lookup = _lookup(cdb, filters, source)
    matched = [r for r in rows if (_group(r, spec, lookup) or (None,))[0] == group]
    amounts = [_value(r, spec, currency) for r in matched]
    
    agg = spec['semantic_aggregation']
    if not matched:
        value = Decimal(0)
    elif agg == 'avg':
        value = sum(amounts, Decimal(0)) / len(matched)
    elif agg == 'min':
        value = min(amounts)
    elif agg == 'max':
        value = max(amounts)
    else:
        value = sum(amounts, Decimal(0))
        
    def row_data(r, amount):
        if source == 'sales':
            party = lookup[r.client_id].name if r.client_id in lookup else r.client_name or 'Unlinked customer'
            number, day = r.invoice_number, r.invoice_date
        elif source == 'sales_items':
            item, day = r if isinstance(r, tuple) else (r, None)
            party = getattr(item, 'item_name', None) or 'Sales Item'
            number = f'Item #{getattr(item, "id", "")}'
        elif source == 'purchase':
            party = lookup[r.supplier_id].name if r.supplier_id in lookup else r.supplier_name or 'Unspecified'
            number, day = r.invoice_number or getattr(r, 'invoice_id', None) or f'Bill #{r.id}', r.date
        elif source == 'purchase_items':
            item, day = r if isinstance(r, tuple) else (r, None)
            party = getattr(item, 'item_name', None) or 'Purchase Item'
            number = f'Item #{getattr(item, "id", "")}'
        elif source == 'expenses':
            party, number, day = r.category, r.reference or f'Expense #{r.id}', r.date
        elif source == 'finance':
            line, entry, account = r if isinstance(r, tuple) else (r, None, None)
            party = getattr(account, 'account_name', 'Account')
            number, day = getattr(entry, 'entry_no', 'Journal'), getattr(entry, 'entry_date', None)
        elif source == 'hr':
            party, number, day = getattr(r, 'full_name', 'Employee'), getattr(r, 'employee_code', 'Emp'), getattr(r, 'date_of_joining', None)
        else:
            party, number, day = r.name, r.code, None
        return {
            'id': getattr(r, 'id', 0) if not isinstance(r, tuple) else getattr(r[0], 'id', 0),
            'number': str(number or ''),
            'date': day.isoformat() if day and hasattr(day, 'isoformat') else str(day or ''),
            'party': str(party or ''),
            'amount': round(float(amount), 2)
        }
        
    result = [row_data(r, a) for r, a in zip(matched, amounts)]
    result.sort(key=lambda r: (r['date'], r['id']), reverse=True)
    return {
        'source': source,
        'group': group,
        'currency': currency,
        'count': len(result),
        'measure_label': CATALOG[source]['measures'][spec['semantic_measure']],
        'total': round(float(value), 2),
        'rows': result[:100],
        'truncated': len(result) > 100,
        'value_kind': 'number' if spec['semantic_measure'] in ('count', 'quantity', 'reorder_level') else 'money',
        'aggregation': spec['semantic_aggregation'],
        'snapshot': source in ('stock', 'hr'),
        'warnings': _snapshot_note(spec, filters)
    }

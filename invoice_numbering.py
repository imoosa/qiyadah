"""Company-specific numbering shared by sales invoice entry and conversions."""
import re

from customer_models import CustomerInvoice


def parse_invoice_start(value):
    value = str(value).strip()
    if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 2147483647:
        raise ValueError('Sales invoice starting number must be a whole number between 1 and 2147483647.')
    return int(value)


def parse_invoice_prefix(value):
    value = str(value).strip()
    if not re.fullmatch(r'[A-Za-z0-9/_-]{0,20}', value):
        raise ValueError('Invoice prefix can contain up to 20 letters, numbers, hyphens, underscores or slashes. Leave it blank for no prefix.')
    return value


def parse_invoice_digits(value):
    value = str(value).strip()
    if not value.isascii() or not value.isdecimal() or not 1 <= int(value) <= 10:
        raise ValueError('Invoice number length must be a whole number between 1 and 10.')
    return int(value)


def next_sales_invoice_number(cdb, company_id, company):
    start = parse_invoice_start(getattr(company, 'sales_invoice_start', None) or 1)
    prefix = getattr(company, 'sales_invoice_prefix', None)
    prefix = parse_invoice_prefix('INV-' if prefix is None else prefix)
    digits = parse_invoice_digits(getattr(company, 'sales_invoice_digits', None) or 4)
    highest = start - 1
    numbers = cdb.query(CustomerInvoice.invoice_number).filter(
        CustomerInvoice.company_id == company_id,
    ).all()
    for (number,) in numbers:
        if not number or not number.startswith(prefix):
            continue
        suffix = number[len(prefix):]
        if suffix.isascii() and suffix.isdecimal():
            highest = max(highest, int(suffix))
    return f'{prefix}{highest + 1:0{digits}d}'

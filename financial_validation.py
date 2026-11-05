"""Validate invoice input before any financial or stock mutation."""
from decimal import Decimal, InvalidOperation


def number(value, label, minimum=Decimal(0), maximum=Decimal('1000000000000'), positive=False):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f'{label} must be a valid number.') from None
    if not result.is_finite() or result < minimum or result > maximum or (positive and result == 0):
        raise ValueError(f'{label} is outside the allowed range.')
    return result


def validate_invoice_form(form):
    names = form.getlist('item_name[]')
    if not names or len(names) > 200:
        raise ValueError('An invoice must contain between 1 and 200 items.')
    fields = {'quantity[]': ('Quantity', 1, True, '1000000000'),
              'rate[]': ('Price', 0, False, '1000000000000'),
              'discount_percent[]': ('Discount percentage', 0, False, '100'),
              'gst_percent[]': ('Tax percentage', 0, False, '100')}
    for key, (label, default, positive, maximum) in fields.items():
        values = form.getlist(key)
        if key in ('quantity[]', 'rate[]') and len(values) != len(names):
            raise ValueError('Each invoice item needs a quantity and price.')
        if values and len(values) != len(names):
            raise ValueError('Invoice item fields do not match.')
        for value in values:
            number(value if str(value).strip() else default, label,
                   maximum=Decimal(maximum), positive=positive)
    number(form.get('exchange_rate') or 1, 'Exchange rate', positive=True)


def reject_invalid_invoice_form(form):
    from flask import abort
    try:
        validate_invoice_form(form)
    except ValueError as error:
        abort(400, description=str(error))

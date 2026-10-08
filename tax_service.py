"""Business tax profiles shared by registration, billing and printed documents.

Standard GCC defaults checked September 2026 against the national tax authorities.
The legacy is_gst_registered/gst_number fields also hold VAT registration details.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from types import SimpleNamespace

COUNTRIES = {
    'India': ('INR', 'GST', 'GSTIN', 18),
    'United Arab Emirates': ('AED', 'GCC_VAT', 'TRN', 5),
    'Saudi Arabia': ('SAR', 'GCC_VAT', 'VAT Number', 15),
    'Bahrain': ('BHD', 'GCC_VAT', 'VAT Number', 10),
    'Oman': ('OMR', 'GCC_VAT', 'VATIN', 5),
    'Qatar': ('QAR', 'NONE', 'Tax ID', 0),
    'Kuwait': ('KWD', 'NONE', 'Tax ID', 0),
    'United States': ('USD', 'SALES_TAX', 'Tax ID', 0),
    'United Kingdom': ('GBP', 'VAT', 'VAT Number', 20),
    'European Union': ('EUR', 'VAT', 'VAT ID', 21),
}
ALIASES = {
    'uae': 'United Arab Emirates', 'ae': 'United Arab Emirates', 'united arab emirates': 'United Arab Emirates',
    'ksa': 'Saudi Arabia', 'sa': 'Saudi Arabia', 'saudi arabia': 'Saudi Arabia',
    'bh': 'Bahrain', 'bahrain': 'Bahrain',
    'om': 'Oman', 'oman': 'Oman',
    'qa': 'Qatar', 'qatar': 'Qatar',
    'kw': 'Kuwait', 'kuwait': 'Kuwait',
    'in': 'India', 'india': 'India',
    'us': 'United States', 'usa': 'United States', 'united states': 'United States',
    'uk': 'United Kingdom', 'gb': 'United Kingdom', 'united kingdom': 'United Kingdom',
    'eu': 'European Union', 'european union': 'European Union',
}


def country_name(value):
    value = str(value or 'India').strip()
    return ALIASES.get(value.lower(), next((c for c in COUNTRIES if c.lower() == value.lower()), value))


def normalize_regime(value):
    value = str(value or 'GST').strip().upper()
    return 'GST' if value == 'INDIA_GST' else value


def tax_profile(company=None, document=None):
    country = country_name(getattr(company, 'country', 'India'))
    defaults = COUNTRIES.get(country, ('INR', 'VAT', 'Tax ID', 0))
    regime = normalize_regime(getattr(company, 'tax_regime', defaults[1]))
    registered = getattr(company, 'is_gst_registered', True)
    has_number = bool(getattr(company, 'gst_number', None))
    if country in COUNTRIES and country != 'India':
        regime = normalize_regime(getattr(company, 'tax_regime', None) or defaults[1])
        if regime == 'GST':
            regime = defaults[1]  # India-only schema defaults must not override another country.
    if not registered and not has_number:
        regime = 'NONE'
    if document is not None and getattr(document, 'tax_regime', None):
        regime = normalize_regime(document.tax_regime)
    is_gst = regime == 'GST'
    is_vat = regime in ('GCC_VAT', 'VAT')
    label = 'GST' if is_gst else 'VAT' if is_vat else 'Tax'
    tax_id = getattr(company, 'tax_id_label', None) or ('GSTIN' if is_gst else (defaults[2] if regime == 'GCC_VAT' else 'VAT ID' if is_vat else 'Tax ID'))
    if country != 'India' and tax_id == 'GSTIN':
        tax_id = defaults[2]
    rate = defaults[3] if regime != 'NONE' else 0
    return dict(country=country, regime=regime, label=label, id_label=tax_id, is_gst=is_gst,
                is_vat=is_vat, registered=bool(registered or has_number), default_rate=rate,
                rates=sorted(set([0, rate])) if is_vat else [0] if regime == 'NONE' else [0, 5, 12, 18, 28],
                currency=getattr(document, 'currency', None) or getattr(company, 'currency', None) or defaults[0])


def apply_company_tax(company, data):
    country = country_name(data.get('country') or getattr(company, 'country', None))
    default = COUNTRIES.get(country, ('INR', 'VAT', 'Tax ID', 0))
    raw = data.get('is_gst_registered', getattr(company, 'is_gst_registered', True))
    registered = str(raw).lower() in ('1', 'true', 'yes')
    user_regime = data.get('tax_regime')
    if user_regime:
        regime = normalize_regime(user_regime)
        if country != 'India' and regime == 'GST':
            regime = default[1]
    else:
        regime = default[1] if country in COUNTRIES else normalize_regime(data.get('tax_regime', 'VAT'))

    number = str(data.get('tax_registration_number', data.get('gst_number', getattr(company, 'gst_number', '') or ''))).strip()
    if registered and regime == 'GCC_VAT' and not number:
        raise ValueError('Enter the business VAT registration number.')
    if len(number) > 20:
        raise ValueError('Tax registration number must be at most 20 characters.')

    has_valid_number = bool(number) and registered
    company.country = country
    company.tax_regime = regime if registered else 'NONE'
    company.is_gst_registered = registered and (regime != 'NONE' or has_valid_number)
    company.gst_number = number if (registered and (regime != 'NONE' or has_valid_number)) else None
    label = data.get('tax_id_label')
    company.tax_id_label = (default[2] if country != 'India' and label == 'GSTIN' else label) or (default[2] if registered else 'Tax ID')
    company.currency = str(data.get('currency') or default[0]).strip().upper()
    from currency_service import get_currency_info
    company.currency_symbol = get_currency_info(company.currency).get('symbol', company.currency)
    return company


def billing_rate(company, raw=None, document=None):
    profile = tax_profile(company, document)
    if not profile['registered']:
        return 0.0
    try:
        rate = Decimal(str(profile['default_rate'] if raw is None or raw == '' else raw))
        if not rate.is_finite() or rate < 0 or rate > 100:
            raise ValueError()
    except (InvalidOperation, ValueError, TypeError):
        from flask import abort
        abort(400, description='Enter a valid tax percentage between 0 and 100.')
    return float(rate)


def split_tax(taxable, rate, regime, interstate=False):
    """VAT is a single tax and never stored as CGST, SGST or IGST."""
    regime = normalize_regime(regime)
    total = (Decimal(str(taxable)) * Decimal(str(rate)) / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if regime == 'NONE':
        total = Decimal(0)
    cgst = sgst = igst = Decimal(0)
    if regime == 'GST':
        if interstate:
            igst = total
        else:
            cgst = (total / 2).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            sgst = total - cgst
    return float(total), float(cgst), float(sgst), float(igst)

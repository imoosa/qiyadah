"""Regional settings edited from the superadmin's registered-user screen."""
from currency_service import CURRENCIES
from tax_service import COUNTRIES, apply_company_tax


def region_options():
    countries = {v['country']: code for code, v in CURRENCIES.items()}
    countries.update({name: values[0] for name, values in COUNTRIES.items()})
    return dict(sorted(countries.items()))


def update_region(company, form):
    country = form.get('country', '').strip()
    currency = form.get('currency', '').strip().upper()
    if country not in region_options():
        raise ValueError('Select a supported country.')
    if currency not in CURRENCIES:
        raise ValueError('Select a supported currency.')
    if form.get('acknowledge') != 'yes':
        raise ValueError('Confirm that existing amounts will not be converted.')
    # Explicit form values prevent an old GSTIN being carried into a new country.
    apply_company_tax(company, {
        'country': country, 'currency': currency,
        'is_gst_registered': form.get('tax_registered') == 'yes',
        'tax_registration_number': form.get('tax_number', '').strip(),
    })

"""Company-scoped fixed asset registration and acquisition posting."""
from customer_models import AssetCategory, FixedAsset, ChartOfAccount
from financial_validation import number

DEFAULT_CATEGORIES = ('Land', 'Buildings', 'Vehicles', 'Plant & Machinery',
                      'Computers & IT Equipment', 'Furniture & Fixtures',
                      'Office Equipment', 'Tools & Equipment', 'Other Fixed Assets')


def category_names(db, company_id):
    custom = [r.name for r in db.query(AssetCategory).filter_by(company_id=company_id)]
    legacy = [r[0] for r in db.query(FixedAsset.category).filter_by(company_id=company_id).distinct() if r[0]]
    return sorted(set(DEFAULT_CATEGORIES) | set(custom) | set(legacy), key=str.casefold)


def resolve_category(db, company_id, form):
    name = ((form.get('new_category') or '') if form.get('category') == '__new__' else (form.get('category') or '')).strip()
    if not name or len(name) > 80:
        raise ValueError('Choose a category or enter a new category of up to 80 characters.')
    existing = next((item for item in category_names(db, company_id) if item.casefold() == name.casefold()), None)
    if existing:
        return existing
    db.add(AssetCategory(company_id=company_id, name=name))
    return name


def acquisition_account(db, company_id, code):
    if not code:
        raise ValueError('Payment / funding account is missing. Reload the updated Fixed Assets form and select an account before posting.')
    account = db.query(ChartOfAccount).filter_by(company_id=company_id, code=code, is_active=True).first()
    if not account or account.code in ('1600', '1610') or account.account_type not in ('Asset', 'Liability', 'Equity'):
        raise ValueError('Select an active payment or funding account.')
    return account


def post_acquisition(db, company_id, asset, credit_code, post_journal):
    account = acquisition_account(db, company_id, credit_code)
    cost = number(asset.purchase_cost, 'Purchase cost', positive=True)
    return post_journal(db, company_id, entry_date=asset.purchase_date,
        narration=f'Asset purchase - {asset.name}', source_type='fixed_asset_purchase',
        source_id=asset.id, reference=asset.asset_code,
        rows=[('1600', cost, 0, f'Asset purchase - {asset.name}'),
              (account.code, 0, cost, f'Asset funding - {asset.name}')])

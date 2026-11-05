"""Client & supplier masters for Core Finance.

Bulk-imports parties from other applications together with their opening
balance and, where the source provides it, the bill-wise break-up of that
balance (date, bill number, amount). Supported sources:

* Excel workbooks (.xlsx / .xlsm / .xls / .ods) - single sheet, or a
  "Parties" sheet plus a "Bills" sheet
* CSV / TSV / TXT (any common delimiter) and data pasted straight from a
  spreadsheet
* JSON - a list of parties (optionally with a nested ``bills`` list), or
  flat rows
* Tally ERP 9 / TallyPrime XML masters export (ledgers with
  OPENINGBALANCE and BILLALLOCATIONS)
* vCard (.vcf) contact exports (phone/Google/Outlook contacts)

Rows are recognised by common column names used by Tally, Busy, Marg,
Vyapar, Zoho Books, QuickBooks, Odoo and plain spreadsheets. A party can
appear on one row with only a total opening balance, or on several rows -
one per outstanding bill. Nothing is written until the user confirms the
preview.
"""
from collections import OrderedDict
import csv
from datetime import date, datetime, timedelta
import io
import json
import os
import re
import secrets
import time
import xml.etree.ElementTree as ET

from flask import (abort, flash, redirect, render_template, request, send_file,
                   session, url_for)
from sqlalchemy import func, or_

from customer_models import Client, PartyImportBatch, PartyOpeningBill, Supplier


# ── Party kinds ──────────────────────────────────────────────────────────────
KINDS = {
    'clients': dict(model=Client, party_type='client', permission='clients', code_field='client_id',
                    type_field='client_type', balance_field='pending', label='Client', plural='Clients',
                    normal='Dr', tally_group='sundry debtors', other_group='sundry creditors',
                    statement='client_statement', statement_arg='client_pk', edit='client_edit'),
    'suppliers': dict(model=Supplier, party_type='supplier', permission='suppliers', code_field='supplier_id',
                      type_field='supplier_type', balance_field='payable', label='Supplier', plural='Suppliers',
                      normal='Cr', tally_group='sundry creditors', other_group='sundry debtors',
                      statement='supplier_statement', statement_arg='supplier_pk', edit='supplier_edit'),
}
PARTY_TYPE_KIND = {'client': 'clients', 'supplier': 'suppliers'}

# Destination column -> maximum stored length (matches customer_models).
PARTY_FIELDS = OrderedDict([
    ('name', 200), ('code', 50), ('contact_person', 150), ('phone', 20), ('alternate_phone', 20),
    ('email', 255), ('website', 255), ('address_line1', 300), ('address_line2', 300), ('city', 100),
    ('state', 100), ('pincode', 10), ('country', 100), ('currency', 10), ('gst_number', 20),
    ('pan_number', 15), ('trn_number', 50), ('gst_type', 30), ('party_type', 30), ('notes', 2000),
])
NUMERIC_FIELDS = ('credit_limit', 'credit_days')


def _key(text):
    return re.sub(r'[^a-z0-9]', '', str(text or '').lower())


# Column aliases in priority order. Matching is case/space/punctuation
# insensitive, so "Party Name", "PARTY_NAME" and "party-name" are equal.
ALIASES = OrderedDict([
    ('name', ['name', 'partyname', 'ledgername', 'customername', 'clientname', 'suppliername', 'vendorname',
              'displayname', 'contactname', 'accountname', 'party', 'ledger', 'customer', 'client', 'supplier',
              'vendor', 'account', 'debtor', 'creditor', 'debtorname', 'creditorname', 'particulars',
              'companyname', 'businessname', 'buyer', 'seller', 'fullname', 'tradename', 'legalname']),
    ('code', ['code', 'partycode', 'customercode', 'clientcode', 'suppliercode', 'vendorcode', 'ledgercode',
              'accountcode', 'alias', 'ledgeralias', 'customerid', 'clientid', 'supplierid', 'vendorid',
              'partyid', 'contactid', 'customerno', 'vendorno', 'accountno', 'acno', 'partyno']),
    ('contact_person', ['contactperson', 'contact', 'attention', 'attn', 'personname', 'primarycontact',
                        'ownername', 'proprietor']),
    ('phone', ['phone', 'mobile', 'mobileno', 'mobilenumber', 'phoneno', 'phonenumber', 'contactno',
               'contactnumber', 'telephone', 'tel', 'cell', 'whatsapp', 'whatsappno', 'mobilephone',
               'ledgermobile', 'ledgerphone', 'phone1', 'mobile1']),
    ('alternate_phone', ['alternatephone', 'alternatemobile', 'altphone', 'altmobile', 'phone2', 'mobile2',
                         'landline', 'otherphone', 'workphone', 'officephone', 'fax']),
    ('email', ['email', 'emailid', 'emailaddress', 'mail', 'email1', 'primaryemail']),
    ('website', ['website', 'web', 'url', 'site']),
    ('address_line1', ['address', 'address1', 'addressline1', 'billingaddress', 'billingaddress1', 'street',
                       'street1', 'billingstreet', 'billingstreet1', 'add1', 'addr1', 'fulladdress']),
    ('address_line2', ['address2', 'addressline2', 'billingaddress2', 'street2', 'billingstreet2', 'area',
                       'locality', 'landmark', 'add2', 'addr2', 'address3']),
    ('city', ['city', 'town', 'billingcity', 'district', 'cityname']),
    ('state', ['state', 'statename', 'province', 'billingstate', 'region', 'emirate', 'placeofsupply']),
    ('pincode', ['pincode', 'pin', 'zip', 'zipcode', 'postalcode', 'postcode', 'billingzip', 'billingcode',
                 'billingpincode', 'billingpostalcode']),
    ('country', ['country', 'countryname', 'billingcountry', 'countryofresidence']),
    ('currency', ['currency', 'currencycode', 'curr']),
    ('gst_number', ['gstin', 'gst', 'gstno', 'gstnumber', 'gstinuin', 'gstinno', 'gstregno', 'partygstin',
                    'gstregistrationnumber', 'gstregistrationno', 'gstuin']),
    ('pan_number', ['pan', 'panno', 'pannumber', 'itpan', 'incometaxnumber', 'pancard']),
    ('trn_number', ['trn', 'trnno', 'trnnumber', 'vatno', 'vatnumber', 'vatregno', 'vatregistrationnumber',
                    'taxregistrationnumber', 'taxid', 'taxnumber', 'vatid']),
    ('gst_type', ['gsttype', 'registrationtype', 'gstregistrationtype', 'gsttreatment', 'dealertype',
                  'taxtreatment', 'vattreatment']),
    ('party_type', ['clienttype', 'customertype', 'suppliertype', 'vendortype', 'partytype', 'category']),
    ('credit_limit', ['creditlimit', 'creditamount', 'maxcredit', 'creditlimitamount']),
    ('credit_days', ['creditdays', 'creditperiod', 'paymentterms', 'terms', 'billcreditperiod', 'duedays',
                     'paymentdays', 'termsdays']),
    ('opening_balance', ['openingbalance', 'opening', 'openingbal', 'openingamount', 'ob', 'obamount',
                         'closingbalance', 'outstandingbalance', 'totaloutstanding', 'currentbalance',
                         'balance', 'outstanding', 'netbalance', 'ledgerbalance', 'receivable', 'payable',
                         'totaldue', 'balanceamount']),
    ('balance_type', ['drcr', 'crdr', 'balancetype', 'openingbalancetype', 'obtype', 'dc', 'cd', 'side',
                      'openingtype', 'balancedrcr']),
    ('opening_debit', ['debit', 'dr', 'debitbalance', 'openingdebit', 'debitamount', 'drbalance', 'dramount']),
    ('opening_credit', ['credit', 'cr', 'creditbalance', 'openingcredit', 'creditamt', 'crbalance', 'cramount']),
    ('opening_date', ['openingdate', 'asondate', 'asofdate', 'balancedate', 'openingasof']),
    ('notes', ['notes', 'note', 'remarks', 'remark', 'comments', 'comment', 'narration', 'description',
               'memo']),
    ('bill_no', ['billno', 'billnumber', 'bill', 'invoiceno', 'invoicenumber', 'invoice', 'refno', 'ref',
                 'reference', 'referenceno', 'referencenumber', 'voucherno', 'vchno', 'vouchernumber', 'docno',
                 'documentno', 'documentnumber', 'billref', 'billreference', 'billname', 'invno', 'invoiceid',
                 'transactionno', 'txnno']),
    ('bill_date', ['billdate', 'invoicedate', 'date', 'vchdate', 'voucherdate', 'docdate', 'documentdate',
                   'refdate', 'invdate', 'transactiondate', 'txndate']),
    ('due_date', ['duedate', 'dueon', 'paymentduedate', 'due']),
    ('bill_amount', ['billamount', 'invoiceamount', 'pendingbillamount', 'billbalance', 'invoicebalance',
                     'pendingamount', 'amount', 'billvalue', 'invoicevalue', 'amountdue', 'balancedue',
                     'pending', 'unpaidamount', 'outstandingamount', 'billpending', 'invamount']),
    ('bill_type', ['billdrcr', 'billtype', 'billside']),
    ('bill_notes', ['billnotes', 'billremarks', 'billnarration', 'billdescription']),
])
_ALIAS_LOOKUP = {}
for _field, _names in ALIASES.items():
    for _rank, _name in enumerate(_names):
        _ALIAS_LOOKUP.setdefault(_name, (_field, _rank))
BILL_FIELDS = ('bill_no', 'bill_date', 'due_date', 'bill_amount', 'bill_type', 'bill_notes')
TOTAL_ROWS = {'total', 'grandtotal', 'subtotal', 'totals', 'nettotal', 'closingbalance', 'openingbalance'}


class ImportError_(ValueError):
    """A user-facing problem with the uploaded data."""


# ── Value parsing ────────────────────────────────────────────────────────────
def clean_text(value):
    if value is None:
        return ''
    if isinstance(value, float):
        if value != value:  # NaN from pandas
            return ''
        if value.is_integer():
            return str(int(value))
    text = str(value).strip()
    return '' if text.lower() in ('nan', 'none', 'null', 'nat', '-') else text


def parse_amount(value):
    """Returns (amount, side) where side is 'Dr', 'Cr' or None.

    Understands Indian/international grouping, currency symbols, brackets
    for negatives, trailing minus and Dr/Cr suffixes."""
    if value is None or value == '':
        return None, None
    if isinstance(value, bool):
        return None, None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value != value:
            return None, None
        return float(value), None
    text = clean_text(value)
    if not text:
        return None, None
    side = None
    match = re.search(r'\b(dr|cr|debit|credit)\.?\s*$', text, re.I) or re.match(r'^\s*(dr|cr)\.?\b', text, re.I)
    if match:
        side = 'Dr' if match.group(1).lower().startswith('d') else 'Cr'
        text = (text[:match.start()] + text[match.end():]).strip()
    negative = False
    if text.startswith('(') and text.endswith(')'):
        negative, text = True, text[1:-1]
    text = re.sub(r'[^\d.,\-+]', '', text)
    if text.endswith('-'):
        negative, text = True, text[:-1]
    if text.startswith('-'):
        negative, text = not negative, text[1:]
    text = text.lstrip('+')
    if text.count(',') and text.count('.') == 0 and re.fullmatch(r'\d{1,3}(,\d{3})*,\d{1,2}', text):
        text = text.replace('.', '').replace(',', '.')          # 1.234,50 style without dot
    elif text.count('.') > 1 and text.count(',') <= 1:
        text = text.replace('.', '').replace(',', '.')          # 1.234.567,50
    else:
        text = text.replace(',', '')
    if not text or text == '.':
        return None, side
    try:
        amount = float(text)
    except ValueError:
        return None, side
    return (-amount if negative else amount), side


def parse_side(value):
    text = _key(value)
    if text in ('dr', 'debit', 'd', 'receivable', 'tocollect', 'due'):
        return 'Dr'
    if text in ('cr', 'credit', 'c', 'payable', 'advance', 'topay'):
        return 'Cr'
    return None


DATE_FORMATS_DMY = ('%d-%m-%Y', '%d/%m/%Y', '%d.%m.%Y', '%d-%m-%y', '%d/%m/%y', '%d.%m.%y')
DATE_FORMATS_MDY = ('%m-%d-%Y', '%m/%d/%Y', '%m.%d.%Y', '%m-%d-%y', '%m/%d/%y')
DATE_FORMATS_OTHER = ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d', '%Y%m%d', '%d-%b-%Y', '%d %b %Y', '%d-%b-%y',
                      '%d %b %y', '%d-%B-%Y', '%d %B %Y', '%b %d, %Y', '%B %d, %Y', '%b %d %Y', '%d%b%Y',
                      '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f', '%d-%m-%Y %H:%M:%S',
                      '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M')


def parse_date(value, month_first=False):
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, 'to_pydatetime'):  # pandas Timestamp
        try:
            return value.to_pydatetime().date()
        except (ValueError, TypeError):
            return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value != value:
            return None
        number = int(value)
        if 19000101 <= number <= 21001231:                       # 20240131
            try:
                return datetime.strptime(str(number), '%Y%m%d').date()
            except ValueError:
                return None
        if 2000 < number < 80000:                                 # Excel serial
            return date(1899, 12, 30) + timedelta(days=number)
        return None
    text = clean_text(value)
    if not text:
        return None
    text = re.sub(r'\s+', ' ', text.replace(',', ', ').replace(' ,', ',')).strip()
    text = re.sub(r',\s+', ', ', text)
    numeric_first = DATE_FORMATS_MDY + DATE_FORMATS_DMY if month_first else DATE_FORMATS_DMY + DATE_FORMATS_MDY
    for fmt in DATE_FORMATS_OTHER[:4] + numeric_first + DATE_FORMATS_OTHER[4:]:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    if re.fullmatch(r'\d+(\.0+)?', text):
        return parse_date(float(text), month_first)
    return None


def parse_days(value):
    """'30', '30 Days', 'Net 45' -> int; None when not a day count."""
    text = clean_text(value)
    match = re.search(r'(\d{1,4})', text)
    if not match:
        return None
    if re.search(r'month', text, re.I):
        return int(match.group(1)) * 30
    return int(match.group(1))


# ── Readers: every reader returns list[dict] of raw rows, or parties ─────────
def _decode(data):
    for encoding in ('utf-8-sig', 'utf-16', 'cp1252', 'latin-1'):
        try:
            text = data.decode(encoding)
            if encoding == 'utf-16' and '\x00' in text:
                continue
            return text
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ImportError_('Could not read the file text. Save it as UTF-8 CSV and try again.')


def _grid_from_text(text):
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip('\n')
    if not text.strip():
        raise ImportError_('The file is empty.')
    sample = '\n'.join(text.split('\n')[:30])
    counts = {d: sample.count(d) for d in ('\t', ',', ';', '|')}
    delimiter = max(counts, key=counts.get) if any(counts.values()) else ','
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]


def _header_index(grid):
    """Finds the header row - exports often carry company titles above it."""
    best, best_score = None, 0
    for index, row in enumerate(grid[:25]):
        fields = {(_ALIAS_LOOKUP.get(_key(cell)) or (None,))[0] for cell in row if clean_text(cell)}
        fields.discard(None)
        score = len(fields) + (3 if 'name' in fields else 0)
        if score > best_score:
            best, best_score = index, score
    if best is None or best_score < 4:   # needs at least a name column
        raise ImportError_('No party name column was found. Use a header such as "Party Name", '
                           '"Customer Name", "Supplier Name" or "Ledger Name", or download the template.')
    return best


def map_columns(headers):
    """header list -> {column index: field}; keeps the best alias per field."""
    chosen = {}
    for index, header in enumerate(headers):
        hit = _ALIAS_LOOKUP.get(_key(header))
        if not hit:
            continue
        field, rank = hit
        if field not in chosen or rank < chosen[field][1]:
            chosen[field] = (index, rank)
    return {index: field for field, (index, _rank) in chosen.items()}


def rows_from_grid(grid):
    grid = [list(row) for row in grid if any(clean_text(c) for c in row)]
    if not grid:
        raise ImportError_('The file has no rows.')
    header_at = _header_index(grid)
    headers = [clean_text(h) for h in grid[header_at]]
    mapping = map_columns(headers)
    rows = []
    for raw in grid[header_at + 1:]:
        row = {field: (raw[index] if index < len(raw) else None) for index, field in mapping.items()}
        if any(clean_text(v) for v in row.values()):
            rows.append(row)
    return rows, [headers[i] + ' → ' + f for i, f in sorted(mapping.items())]


def read_excel(data, file_name):
    try:
        import pandas as pd
    except ImportError:  # pragma: no cover - pandas ships with the app
        raise ImportError_('Excel support is not installed on this server. Upload CSV instead.')
    engine = None
    lower = file_name.lower()
    if lower.endswith('.ods'):
        engine = 'odf'
    try:
        sheets = pd.read_excel(io.BytesIO(data), sheet_name=None, header=None, dtype=object, engine=engine)
    except ImportError as error:
        raise ImportError_(f'This Excel format needs an extra library on the server ({error}). '
                           'Save the file as .xlsx or CSV and upload again.')
    except Exception as error:
        raise ImportError_(f'Could not open the workbook: {error}')
    grids = OrderedDict()
    for name, frame in sheets.items():
        grid = [[None if (isinstance(v, float) and v != v) else v for v in row] for row in frame.values.tolist()]
        if any(any(clean_text(c) for c in row) for row in grid):
            grids[str(name)] = grid
    if not grids:
        raise ImportError_('The workbook has no data.')
    bill_sheet = next((n for n in grids if re.search(r'bill|outstanding|invoice|pending', n, re.I)), None)
    party_sheet = next((n for n in grids if n != bill_sheet and
                        re.search(r'part|client|customer|supplier|vendor|ledger|master|debtor|creditor|contact',
                                  n, re.I)), None)
    notes = []
    if bill_sheet and party_sheet:
        parties, notes_a = rows_from_grid(grids[party_sheet])
        bills, notes_b = rows_from_grid(grids[bill_sheet])
        for bill in bills:
            bill['_bill_only'] = True
        return parties + bills, [f'Sheet "{party_sheet}": '] + notes_a + [f'Sheet "{bill_sheet}": '] + notes_b
    last_error = None
    for name, grid in grids.items():
        try:
            rows, notes = rows_from_grid(grid)
            return rows, [f'Sheet "{name}": '] + notes
        except ImportError_ as error:
            last_error = error
    raise last_error


def _flatten(obj, prefix=''):
    flat = {}
    for key, value in (obj or {}).items():
        if isinstance(value, dict):
            nested = _flatten(value, '')
            for nk, nv in nested.items():
                flat.setdefault(nk, nv)              # address.city -> city
                flat.setdefault(f'{key}{nk}', nv)    # billing_address.city -> billingaddresscity
        elif not isinstance(value, list):
            flat[key] = value
    return flat


BILL_LIST_KEYS = ('bills', 'openingbills', 'billallocations', 'invoices', 'outstandingbills', 'pendingbills',
                  'billwise', 'billwisedetails', 'outstanding', 'transactions', 'items')


def read_json(data):
    try:
        payload = json.loads(_decode(data))
    except json.JSONDecodeError as error:
        raise ImportError_(f'The JSON file is not valid: {error.msg} (line {error.lineno}).')
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, list) and _key(key) in ('parties', 'clients', 'customers', 'suppliers', 'vendors',
                                                         'data', 'ledgers', 'records', 'contacts', 'items',
                                                         'debtors', 'creditors', 'accounts', 'rows', 'results'):
                payload = value
                break
        else:
            lists = [v for v in payload.values() if isinstance(v, list)]
            payload = lists[0] if lists else [payload]
    if not isinstance(payload, list) or not payload:
        raise ImportError_('The JSON file must contain a list of parties.')
    rows = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        bills = next((v for k, v in item.items() if isinstance(v, list) and _key(k) in BILL_LIST_KEYS), None)
        party = {}
        for key, value in _flatten(item).items():
            hit = _ALIAS_LOOKUP.get(_key(key))
            if hit and (hit[0] not in party or hit[1] < party[hit[0]][1]):
                party[hit[0]] = (value, hit[1])
        party = {k: v for k, (v, _r) in party.items()}
        bill_rows = []
        for bill in bills or []:
            if not isinstance(bill, dict):
                continue
            mapped = {}
            for key, value in _flatten(bill).items():
                hit = _ALIAS_LOOKUP.get(_key(key))
                if not hit:
                    continue
                field = hit[0]
                # Inside a bill object, generic names describe the bill.
                field = {'name': 'bill_no', 'opening_balance': 'bill_amount', 'notes': 'bill_notes',
                         'balance_type': 'bill_type', 'code': 'bill_no'}.get(field, field)
                if field in BILL_FIELDS and field not in mapped:
                    mapped[field] = value
            if mapped:
                bill_rows.append(mapped)
        if bill_rows:
            for bill in bill_rows:
                rows.append({**party, **bill})
            if not party.get('opening_balance'):
                rows[-len(bill_rows)]['_sum_bills'] = True
        else:
            rows.append(party)
    if not rows:
        raise ImportError_('No parties were found in the JSON file.')
    return rows, ['JSON keys matched to party and bill fields automatically.']


def _xml_text(element, *paths):
    for path in paths:
        found = element.find(path)
        if found is not None and (found.text or '').strip():
            return found.text.strip()
    return ''


def read_tally_xml(data, kind):
    text = _decode(data)
    # Tally escapes control characters as &#4; which XML 1.0 rejects.
    text = re.sub(r'&#(?:[0-8]|1[0-9]|2[0-9]|3[01]);', ' ', text)
    text = re.sub(r'<!DOCTYPE[^>]*>', '', text, flags=re.I)
    try:
        root = ET.fromstring(text.encode('utf-8'))
    except ET.ParseError as error:
        raise ImportError_(f'The XML file could not be read: {error}')
    parents = {}
    for group in root.iter('GROUP'):
        name = group.get('NAME') or _xml_text(group, 'NAME', 'LANGUAGENAME.LIST/NAME.LIST/NAME')
        if name:
            parents[name.strip().lower()] = _xml_text(group, 'PARENT').lower()

    def lineage(group):
        seen, chain = set(), []
        while group and group not in seen:
            seen.add(group)
            chain.append(group)
            group = parents.get(group, '')
        return chain

    config = KINDS[kind]
    ledgers = list(root.iter('LEDGER'))
    if not ledgers:
        raise ImportError_('No LEDGER entries were found. In Tally use Export → Masters → '
                           'Ledgers (XML) or Display → List of Accounts → Export (XML).')
    rows, wanted, unknown = [], 0, []
    for ledger in ledgers:
        name = (ledger.get('NAME') or _xml_text(ledger, 'NAME', 'LANGUAGENAME.LIST/NAME.LIST/NAME')).strip()
        if not name:
            continue
        chain = lineage(_xml_text(ledger, 'PARENT').lower())
        if config['tally_group'] in chain:
            wanted += 1
        elif config['other_group'] in chain:
            continue
        else:
            unknown.append(name)
            continue
        addresses = [a.text.strip() for a in ledger.findall('ADDRESS.LIST/ADDRESS') if (a.text or '').strip()]
        gstin = _xml_text(ledger, 'PARTYGSTIN', 'GSTIN', 'LEDGSTREGDETAILS.LIST/GSTIN')
        party = dict(
            name=name, code=_xml_text(ledger, 'ALIAS', 'LANGUAGENAME.LIST/NAME.LIST/NAME[2]'),
            contact_person=_xml_text(ledger, 'LEDGERCONTACT'),
            phone=_xml_text(ledger, 'LEDGERMOBILE', 'LEDGERPHONE'),
            alternate_phone=_xml_text(ledger, 'LEDGERPHONE') if _xml_text(ledger, 'LEDGERMOBILE') else '',
            email=_xml_text(ledger, 'EMAIL'), website=_xml_text(ledger, 'WEBSITE'),
            address_line1=', '.join(addresses[:2]), address_line2=', '.join(addresses[2:]),
            state=_xml_text(ledger, 'LEDSTATENAME', 'STATENAME', 'LEDMAILINGDETAILS.LIST/STATE'),
            pincode=_xml_text(ledger, 'PINCODE', 'LEDMAILINGDETAILS.LIST/PINCODE'),
            country=_xml_text(ledger, 'COUNTRYNAME', 'COUNTRYOFRESIDENCE', 'LEDMAILINGDETAILS.LIST/COUNTRY'),
            gst_number=gstin, pan_number=_xml_text(ledger, 'INCOMETAXNUMBER'),
            gst_type=_xml_text(ledger, 'GSTREGISTRATIONTYPE', 'LEDGSTREGDETAILS.LIST/GSTREGISTRATIONTYPE'),
            credit_limit=_xml_text(ledger, 'CREDITLIMIT'), credit_days=_xml_text(ledger, 'BILLCREDITPERIOD'),
            notes=_xml_text(ledger, 'NARRATION', 'DESCRIPTION'),
        )
        if party['code'] == name:
            party['code'] = ''
        opening = _xml_text(ledger, 'OPENINGBALANCE')
        amount, side = parse_amount(opening)
        if amount is not None:
            # Tally stores debit balances as negative numbers.
            party['opening_balance'] = abs(amount)
            party['balance_type'] = side or ('Dr' if amount < 0 else 'Cr')
        bills = ledger.findall('BILLALLOCATIONS.LIST')
        bill_rows = []
        for bill in bills:
            bill_amount, bill_side = parse_amount(_xml_text(bill, 'OPENINGBALANCE', 'AMOUNT'))
            bill_no = _xml_text(bill, 'NAME')
            if bill_amount is None and not bill_no:
                continue
            due = _xml_text(bill, 'BILLCREDITPERIOD')
            bill_rows.append(dict(bill_no=bill_no, bill_date=_xml_text(bill, 'BILLDATE'),
                                  due_date=due if parse_date(due) else '', _due_days=parse_days(due),
                                  bill_amount=abs(bill_amount or 0),
                                  bill_type=bill_side or ('Dr' if (bill_amount or 0) < 0 else 'Cr')))
        if bill_rows:
            for bill in bill_rows:
                rows.append({**party, **bill})
        else:
            rows.append(party)
    notes = [f'Tally XML: {wanted} ledger(s) under {config["tally_group"].title()}.']
    if not wanted and unknown:
        # Exports of a single custom group lose the group tree - take everything.
        notes = [f'Tally XML: group tree not included; imported all {len(unknown)} ledger(s). '
                 f'Untick any that are not {config["plural"].lower()} in the preview.']
        return read_tally_xml_all(root, kind), notes
    if not rows:
        raise ImportError_(f'No {config["plural"].lower()} were found in the Tally file.')
    return rows, notes


def read_tally_xml_all(root, kind):
    """Fallback that keeps every ledger when group information is absent."""
    temp = dict(KINDS)
    fake = ET.Element('ENVELOPE')
    group = ET.SubElement(fake, 'GROUP', NAME='__ALL__')
    ET.SubElement(group, 'PARENT').text = KINDS[kind]['tally_group']
    for ledger in root.iter('LEDGER'):
        clone = ET.fromstring(ET.tostring(ledger))
        parent = clone.find('PARENT')
        if parent is None:
            parent = ET.SubElement(clone, 'PARENT')
        parent.text = '__ALL__'
        fake.append(clone)
    del temp
    rows, _notes = read_tally_xml(ET.tostring(fake), kind)
    return rows


def read_vcard(data):
    text = _decode(data).replace('\r\n ', '').replace('\n ', '')
    rows = []
    for block in re.findall(r'BEGIN:VCARD(.*?)END:VCARD', text, re.S | re.I):
        card = {}
        for line in block.strip().splitlines():
            if ':' not in line:
                continue
            head, value = line.split(':', 1)
            prop = head.split(';')[0].upper().split('.')[-1]
            value = value.strip()
            if prop == 'FN':
                card['name'] = value
            elif prop == 'ORG' and value:
                card['org'] = value.split(';')[0]
            elif prop == 'TEL':
                card.setdefault('phone', value) if 'phone' not in card else card.setdefault('alternate_phone', value)
            elif prop == 'EMAIL':
                card.setdefault('email', value)
            elif prop == 'URL':
                card.setdefault('website', value)
            elif prop == 'NOTE':
                card['notes'] = value.replace('\\n', ' ')
            elif prop == 'ADR' and 'address_line1' not in card:
                parts = (value.split(';') + [''] * 7)[:7]
                card.update(address_line1=', '.join(p for p in parts[:3] if p), city=parts[3], state=parts[4],
                            pincode=parts[5], country=parts[6])
        if card.get('org'):
            card['contact_person'] = card.get('name', '')
            card['name'] = card.pop('org')
        card.pop('org', None)
        if card.get('name'):
            rows.append(card)
    if not rows:
        raise ImportError_('No contacts were found in the vCard file.')
    return rows, [f'vCard: {len(rows)} contact(s).']


def read_source(file_name, data, kind):
    """Dispatches on file extension / content. Returns (format, rows, notes)."""
    name = (file_name or '').lower()
    head = data[:400].lstrip(b'\xef\xbb\xbf \r\n\t').lower()
    if name.endswith(('.xlsx', '.xlsm', '.xls', '.ods')) or head.startswith(b'pk\x03\x04') or \
            head.startswith(b'\xd0\xcf\x11\xe0'):
        rows, notes = read_excel(data, name or 'upload.xlsx')
        return 'excel', rows, notes
    if name.endswith('.json') or head[:1] in (b'[', b'{'):
        rows, notes = read_json(data)
        return 'json', rows, notes
    if name.endswith('.xml') or head.startswith(b'<') or head.startswith(b'\xff\xfe<') or b'<envelope' in head:
        rows, notes = read_tally_xml(data, kind)
        return 'tally', rows, notes
    if name.endswith(('.vcf', '.vcard')) or head.startswith(b'begin:vcard'):
        rows, notes = read_vcard(data)
        return 'vcard', rows, notes
    rows, notes = rows_from_grid(_grid_from_text(_decode(data)))
    return 'csv', rows, notes


# ── Normalisation: raw rows -> parties with bills ────────────────────────────
def _normal_sign(amount, side, normal):
    """Signed on the party's normal side (client Dr / supplier Cr)."""
    if amount is None:
        return None
    if side and side != normal:
        return -abs(amount)
    if side:
        return abs(amount)
    return amount


def build_parties(rows, kind, opening_date=None, month_first=False):
    config = KINDS[kind]
    normal = config['normal']
    parties = OrderedDict()
    warnings = []
    last = None
    for line_no, row in enumerate(rows, start=1):
        name = clean_text(row.get('name'))[:200]
        code = clean_text(row.get('code'))[:50]
        has_bill = any(clean_text(row.get(f)) for f in ('bill_no', 'bill_date', 'bill_amount'))
        if _key(name) in TOTAL_ROWS or (not name and _key(code) in TOTAL_ROWS):
            continue
        if not name and not code:
            if has_bill and last is not None:
                party = last                        # bill rows listed under a party heading
            else:
                continue
        else:
            key = _key(code) or re.sub(r'\s+', ' ', name.casefold())
            if row.get('_bill_only'):
                key = next((k for k, p in parties.items()
                            if (code and _key(p['code']) == _key(code)) or
                            (name and p['name'].casefold() == name.casefold())), key)
            party = parties.get(key)
            if party is None:
                if not name:
                    warnings.append(f'Row {line_no}: bill for unknown party code "{code}" skipped.')
                    continue
                party = parties[key] = dict(name=name, code=code, bills=[], opening_values=[],
                                            sum_bills=False, warnings=[], include=True, line=line_no)
            last = party
        for field, limit in PARTY_FIELDS.items():
            value = clean_text(row.get(field))
            if value and not party.get(field):
                party[field] = value[:limit]
        for field in NUMERIC_FIELDS:
            if party.get(field) in (None, '') and clean_text(row.get(field)):
                value = parse_days(row.get(field)) if field == 'credit_days' else parse_amount(row.get(field))[0]
                if value is not None:
                    party[field] = value
        if row.get('_sum_bills'):
            party['sum_bills'] = True
        if not party.get('opening_date') and clean_text(row.get('opening_date')):
            party['opening_date'] = parse_date(row.get('opening_date'), month_first)
        # Opening balance - one figure, or separate debit / credit columns.
        side = parse_side(row.get('balance_type'))
        amount, inline_side = parse_amount(row.get('opening_balance'))
        if amount is None and (clean_text(row.get('opening_debit')) or clean_text(row.get('opening_credit'))):
            debit = parse_amount(row.get('opening_debit'))[0] or 0
            credit = parse_amount(row.get('opening_credit'))[0] or 0
            amount, inline_side = abs(debit - credit), ('Dr' if debit >= credit else 'Cr')
        if amount is not None and not row.get('_bill_only'):
            party['opening_values'].append(_normal_sign(amount, inline_side or side, normal))
        if has_bill:
            bill_amount, bill_side = parse_amount(row.get('bill_amount'))
            bill_side = bill_side or parse_side(row.get('bill_type'))
            if bill_amount is None:
                party['warnings'].append(f'Bill {clean_text(row.get("bill_no")) or "(no number)"} has no amount - skipped.')
                continue
            bill_date = parse_date(row.get('bill_date'), month_first)
            if clean_text(row.get('bill_date')) and not bill_date:
                party['warnings'].append(f'Bill {clean_text(row.get("bill_no"))}: date "{clean_text(row.get("bill_date"))}" not understood.')
            due = parse_date(row.get('due_date'), month_first)
            due_days = row.get('_due_days') or (parse_days(row.get('due_date')) if not due and clean_text(row.get('due_date')) else None)
            if not due and due_days and bill_date:
                due = bill_date + timedelta(days=due_days)
            party['bills'].append(dict(bill_no=clean_text(row.get('bill_no'))[:100],
                                       bill_date=bill_date, due_date=due,
                                       amount=round(_normal_sign(bill_amount, bill_side, normal), 2),
                                       notes=clean_text(row.get('bill_notes'))[:300]))
    if not parties:
        raise ImportError_('No parties with a name were found in the data.')

    result = []
    for party in parties.values():
        values = [v for v in party.pop('opening_values') if v is not None]
        bill_total = round(sum(b['amount'] for b in party['bills']), 2)
        if party['bills'] and (party.pop('sum_bills') or not values):
            opening = bill_total
        elif values and len(set(round(v, 2) for v in values)) == 1:
            opening = values[0]                 # repeated on every bill row, or a single row
        elif values and not party['bills']:
            opening = sum(values)               # several balance rows for the same party
            party['warnings'].append('Several opening balances found for this party - they were added up.')
        elif values:
            opening = bill_total
            party['warnings'].append('Opening balance differs between rows - the bills total was used.')
        else:
            opening = 0.0
        party.pop('sum_bills', None)
        party['opening_balance'] = round(opening or 0, 2)
        party['bill_total'] = bill_total
        party['difference'] = round(party['opening_balance'] - bill_total, 2) if party['bills'] else 0.0
        if party['bills'] and abs(party['difference']) >= 0.01:
            party['warnings'].append(
                f'Opening balance {party["opening_balance"]:,.2f} ≠ bills total {bill_total:,.2f}; '
                f'the difference {party["difference"]:,.2f} will show as "on account".')
        gst = (party.get('gst_number') or '').replace(' ', '').upper()
        party['gst_number'] = gst
        if gst and not re.fullmatch(r'[0-9]{2}[A-Z0-9]{13}', gst):
            party['warnings'].append(f'GSTIN "{gst}" does not look valid (15 characters expected).')
        if party.get('pan_number'):
            party['pan_number'] = party['pan_number'].replace(' ', '').upper()[:15]
        if party.get('email'):
            party['email'] = party['email'].lower()
        party.setdefault('opening_date', None)
        party['opening_date'] = party['opening_date'] or opening_date
        for bill in party['bills']:
            bill['bill_date'] = bill['bill_date'] or party['opening_date']
        party['bills'].sort(key=lambda b: (b['bill_date'] or date.min, b['bill_no']))
        result.append(party)
    return result, warnings


# ── Staging between preview and confirm ──────────────────────────────────────
def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(type(value))


def _restore_dates(parties):
    for party in parties:
        if party.get('opening_date'):
            party['opening_date'] = date.fromisoformat(party['opening_date'])
        for bill in party['bills']:
            for field in ('bill_date', 'due_date'):
                if bill.get(field):
                    bill[field] = date.fromisoformat(bill[field])
    return parties


def staging_dir(app):
    path = os.path.join(app.instance_path, 'party_imports')
    os.makedirs(path, exist_ok=True)
    cutoff = time.time() - 86400
    for entry in os.scandir(path):
        if entry.is_file() and entry.stat().st_mtime < cutoff:
            try:
                os.remove(entry.path)
            except OSError:
                pass
    return path


# ── Statements ───────────────────────────────────────────────────────────────
def opening_bills(db, company_id, party_type, party_id):
    try:
        PartyOpeningBill.__table__.create(bind=db.get_bind(), checkfirst=True)
        return (db.query(PartyOpeningBill)
                .filter_by(company_id=company_id, party_type=party_type, party_id=party_id)
                .order_by(PartyOpeningBill.bill_date.asc(), PartyOpeningBill.id.asc()).all())
    except Exception:
        return []


def opening_statement(db, company_id, party_type, party, fallback_date=None):
    """Rows that together make up the party's opening balance.

    Returns [] when the party has no opening bills. Otherwise the bills plus
    an 'on account' line for any difference, each with a running balance;
    the last balance always equals party.opening_balance."""
    bills = opening_bills(db, company_id, party_type, party.id)
    if not bills:
        return []
    opening = round(float(party.opening_balance or 0), 2)
    default_date = fallback_date or getattr(party, 'created_at', None) or date.today()
    rows, running = [], 0.0
    for bill in bills:
        running = round(running + (bill.amount or 0), 2)
        rows.append(dict(id=bill.id, date=bill.bill_date or default_date, bill_no=bill.bill_no or '',
                         due_date=bill.due_date, amount=bill.amount or 0, notes=bill.notes or '',
                         kind='bill', balance=running))
    difference = round(opening - running, 2)
    if abs(difference) >= 0.01:
        rows.append(dict(id=None, date=default_date, bill_no='', due_date=None, amount=difference,
                         notes='Opening balance not allocated to bills', kind='on_account',
                         balance=opening))
    return rows


def opening_ledger_rows(db, company_id, party_type, party, template, normal='debit', fallback_date=None):
    """Statement-ready rows that replace the single "Opening Balance" line.

    `template` supplies the extra blank keys the calling statement expects;
    `normal` is the column that increases the balance ('debit' for clients,
    'credit' for suppliers)."""
    rows = []
    for line in opening_statement(db, company_id, party_type, party, fallback_date):
        increase, decrease = max(line['amount'], 0), max(-line['amount'], 0)
        rows.append({**template,
                     'date': line['date'],
                     'type': 'Opening Bill' if line['kind'] == 'bill' else 'Opening Balance (On Account)',
                     'ref': line['bill_no'] or '—',
                     'debit': increase if normal == 'debit' else decrease,
                     'credit': decrease if normal == 'debit' else increase,
                     'balance': line['balance'], 'status': ''})
    return rows


# ── Templates for download ───────────────────────────────────────────────────
TEMPLATE_COLUMNS = ['Party Name', 'Party Code', 'Contact Person', 'Phone', 'Alternate Phone', 'Email', 'Address',
                    'Address 2', 'City', 'State', 'Pincode', 'Country', 'GSTIN', 'PAN', 'TRN', 'GST Type',
                    'Credit Limit', 'Credit Days', 'Opening Balance', 'Dr/Cr', 'Bill No', 'Bill Date',
                    'Due Date', 'Bill Amount', 'Notes']


def template_rows(kind):
    side = KINDS[kind]['normal']
    example = 'ABC Traders' if kind == 'clients' else 'XYZ Suppliers'
    base = [example, 'P001', 'Ravi Kumar', '9876543210', '', 'accounts@example.com', '12 Market Road', '',
            'Mumbai', 'Maharashtra', '400001', 'India', '27ABCDE1234F1Z5', 'ABCDE1234F', '', 'Regular',
            100000, 30, 30000, side]
    return [
        base + ['INV-101', '01-04-2026', '01-05-2026', 10000, ''],
        [example, 'P001'] + [''] * 18 + ['INV-102', '15-04-2026', '15-05-2026', 10000, ''],
        [example, 'P001'] + [''] * 18 + ['INV-103', '28-04-2026', '28-05-2026', 10000, ''],
        ['Walk-in Party (total only)', 'P002', '', '9123456780', '', '', '', '', 'Pune', 'Maharashtra', '', 'India',
         '', '', '', 'Unregistered', 0, 0, 5500, side, '', '', '', '', 'No bill details - total only'],
    ]


def export_rows(db, company_id, kind, parties):
    config = KINDS[kind]
    bills_by_party = {}
    for bill in (db.query(PartyOpeningBill).filter_by(company_id=company_id, party_type=config['party_type'])
                 .order_by(PartyOpeningBill.bill_date, PartyOpeningBill.id)):
        bills_by_party.setdefault(bill.party_id, []).append(bill)
    out = []
    for p in parties:
        opening = float(p.opening_balance or 0)
        side = config['normal'] if opening >= 0 else ('Cr' if config['normal'] == 'Dr' else 'Dr')
        base = [p.name, getattr(p, config['code_field']) or '', p.contact_person or '', p.phone or '',
                p.alternate_phone or '', p.email or '', p.address_line1 or '', p.address_line2 or '', p.city or '',
                p.state or '', p.pincode or '', p.country or '', p.gst_number or '', p.pan_number or '',
                p.trn_number or '', p.gst_type or '', p.credit_limit or 0, p.credit_days or 0, abs(opening), side]
        bills = bills_by_party.get(p.id) or []
        if not bills:
            out.append(base + ['', '', '', '', p.notes or ''])
        for index, bill in enumerate(bills):
            row = base if index == 0 else [p.name, base[1]] + [''] * 18
            out.append(row + [bill.bill_no or '', bill.bill_date.strftime('%d-%m-%Y') if bill.bill_date else '',
                              bill.due_date.strftime('%d-%m-%Y') if bill.due_date else '', bill.amount or 0,
                              bill.notes or ''])
    return out


def xlsx_bytes(columns, rows, sheet='Parties', title=None):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    book = Workbook()
    ws = book.active
    ws.title = sheet[:31]
    start = 1
    if title:
        ws.cell(row=1, column=1, value=title).font = Font(bold=True, size=13)
        start = 3
    for col, name in enumerate(columns, start=1):
        cell = ws.cell(row=start, column=col, value=name)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='064E3B')
        ws.column_dimensions[get_column_letter(col)].width = max(12, min(32, len(str(name)) + 6))
    for r, row in enumerate(rows, start=start + 1):
        for c, value in enumerate(row, start=1):
            ws.cell(row=r, column=c, value=value)
    ws.freeze_panes = ws.cell(row=start + 1, column=1)
    buf = io.BytesIO()
    book.save(buf)
    buf.seek(0)
    return buf


# ── Routes ───────────────────────────────────────────────────────────────────
def register_party_masters(app, login_required, require_permission, get_cdb, get_company, can,
                           get_user=lambda: None, next_party_code=None, today_func=date.today,
                           currency_symbol=lambda: ''):
    """`next_party_code(db, kind)` returns the next internal client/supplier id."""

    def context(kind, action='view'):
        config = KINDS.get(kind)
        if not config:
            abort(404)
        if not can(config['permission'], action):
            abort(403)
        company = get_company()
        if not company:
            abort(403)
        db = get_cdb()
        try:
            PartyImportBatch.__table__.create(bind=db.get_bind(), checkfirst=True)
            PartyOpeningBill.__table__.create(bind=db.get_bind(), checkfirst=True)
        except Exception:
            pass
        return config, company, db

    def find_party(db, config, company, party_id):
        party = db.query(config['model']).filter_by(id=party_id, company_id=company).first()
        if party is None:
            abort(404)
        return party

    def safe_url(endpoint, **values):
        try:
            return url_for(endpoint, **values)
        except Exception:
            return None

    @app.route('/finance/masters/<kind>')
    @login_required
    @require_permission('finance', 'view')
    def finance_party_master(kind):
        config, company, db = context(kind)
        model = config['model']
        q = (request.args.get('q') or '').strip()
        show = request.args.get('show', '')
        query = db.query(model).filter(model.company_id == company,
                                       func.coalesce(model.status, 'Active') != 'Deleted')
        if q:
            like = f'%{q.lower()}%'
            query = query.filter(or_(func.lower(model.name).like(like),
                                     func.lower(func.coalesce(getattr(model, config['code_field']), '')).like(like),
                                     func.lower(func.coalesce(model.gst_number, '')).like(like),
                                     func.coalesce(model.phone, '').like(like),
                                     func.lower(func.coalesce(model.city, '')).like(like)))
        stats = {pid: (count, total) for pid, count, total in db.query(
            PartyOpeningBill.party_id, func.count(PartyOpeningBill.id), func.sum(PartyOpeningBill.amount)
        ).filter_by(company_id=company, party_type=config['party_type']).group_by(PartyOpeningBill.party_id)}
        if show == 'opening':
            query = query.filter(func.coalesce(model.opening_balance, 0) != 0)
        elif show == 'bills':
            query = query.filter(model.id.in_(list(stats) or [-1]))
        total_count = query.count()
        totals = query.with_entities(func.sum(model.opening_balance)).scalar() or 0
        try:
            page = max(1, int(request.args.get('page', 1)))
        except ValueError:
            page = 1
        parties = query.order_by(func.lower(model.name)).offset((page - 1) * 100).limit(100).all()
        rows = []
        for p in parties:
            count, bill_total = stats.get(p.id, (0, 0))
            opening = float(p.opening_balance or 0)
            rows.append(dict(party=p, code=getattr(p, config['code_field']) or '', opening=opening,
                             bill_count=count, bill_total=float(bill_total or 0),
                             difference=round(opening - float(bill_total or 0), 2) if count else 0,
                             statement_url=safe_url(config['statement'], **{config['statement_arg']: p.id}),
                             edit_url=safe_url(config['edit'], **{config['statement_arg']: p.id})))
        batches = (db.query(PartyImportBatch).filter_by(company_id=company, party_type=config['party_type'])
                   .order_by(PartyImportBatch.created_at.desc()).limit(5).all())
        args = request.args.to_dict()
        args.pop('page', None)
        return render_template('finance_party_master.html', kind=kind, config=config, rows=rows,
                               total_count=total_count, opening_total=totals, q=q, show=show, page=page,
                               batches=batches, can_create=can(config['permission'], 'create'),
                               bills_party_count=len(stats),
                               next_url=url_for('finance_party_master', kind=kind, page=page + 1, **args)
                               if page * 100 < total_count else None,
                               prev_url=url_for('finance_party_master', kind=kind, page=page - 1, **args)
                               if page > 1 else None,
                               list_url=safe_url('client_list' if kind == 'clients' else 'supplier_list'),
                               new_url=safe_url('client_new' if kind == 'clients' else 'supplier_new'))

    @app.route('/finance/masters/<kind>/template.<fmt>')
    @login_required
    @require_permission('finance', 'view')
    def finance_party_template(kind, fmt):
        config, _company, _db = context(kind)
        rows = template_rows(kind)
        name = f'{kind}_import_template'
        if fmt == 'xlsx':
            buf = xlsx_bytes(TEMPLATE_COLUMNS, rows, sheet=config['plural'])
            return send_file(buf, as_attachment=True, download_name=f'{name}.xlsx',
                             mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        if fmt == 'csv':
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(TEMPLATE_COLUMNS)
            writer.writerows(rows)
            return send_file(io.BytesIO(buf.getvalue().encode('utf-8-sig')), as_attachment=True,
                             download_name=f'{name}.csv', mimetype='text/csv')
        if fmt == 'json':
            side = config['normal']
            sample = [
                {'name': rows[0][0], 'code': 'P001', 'phone': '9876543210', 'email': 'accounts@example.com',
                 'address': '12 Market Road', 'city': 'Mumbai', 'state': 'Maharashtra', 'pincode': '400001',
                 'gstin': '27ABCDE1234F1Z5', 'credit_days': 30, 'opening_balance': 30000, 'dr_cr': side,
                 'bills': [{'bill_no': 'INV-101', 'bill_date': '2026-04-01', 'due_date': '2026-05-01', 'amount': 10000},
                           {'bill_no': 'INV-102', 'bill_date': '2026-04-15', 'amount': 10000},
                           {'bill_no': 'INV-103', 'bill_date': '2026-04-28', 'amount': 10000}]},
                {'name': 'Walk-in Party (total only)', 'phone': '9123456780', 'opening_balance': 5500, 'dr_cr': side},
            ]
            return send_file(io.BytesIO(json.dumps({kind: sample}, indent=2).encode()), as_attachment=True,
                             download_name=f'{name}.json', mimetype='application/json')
        abort(404)

    @app.route('/finance/masters/<kind>/export.xlsx')
    @login_required
    @require_permission('finance', 'view')
    def finance_party_export(kind):
        config, company, db = context(kind)
        model = config['model']
        parties = (db.query(model).filter(model.company_id == company,
                                          func.coalesce(model.status, 'Active') != 'Deleted')
                   .order_by(func.lower(model.name)).all())
        buf = xlsx_bytes(TEMPLATE_COLUMNS, export_rows(db, company, kind, parties), sheet=config['plural'])
        return send_file(buf, as_attachment=True, download_name=f'{kind}_master_{today_func():%Y%m%d}.xlsx',
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.route('/finance/masters/<kind>/import', methods=['GET', 'POST'])
    @login_required
    @require_permission('finance', 'view')
    def finance_party_import(kind):
        config, company, db = context(kind, 'create')
        today = today_func()
        if request.method == 'GET':
            batches = (db.query(PartyImportBatch).filter_by(company_id=company, party_type=config['party_type'])
                       .order_by(PartyImportBatch.created_at.desc()).limit(10).all())
            return render_template('finance_party_import.html', kind=kind, config=config, batches=batches,
                                   today=today.isoformat())
        upload = request.files.get('file')
        pasted = (request.form.get('pasted') or '').strip()
        month_first = request.form.get('date_order') == 'mdy'
        opening_date = parse_date(request.form.get('opening_date') or '') or today
        try:
            if upload and upload.filename:
                data = upload.read()
                if not data:
                    raise ImportError_('The uploaded file is empty.')
                fmt, rows, notes = read_source(upload.filename, data, kind)
                file_name = os.path.basename(upload.filename)[:255]
            elif pasted:
                rows, notes = rows_from_grid(_grid_from_text(pasted))
                fmt, file_name = 'paste', 'Pasted data'
            else:
                raise ImportError_('Choose a file to upload or paste rows from a spreadsheet.')
            parties, warnings = build_parties(rows, kind, opening_date, month_first)
        except ImportError_ as error:
            flash(str(error), 'error')
            return redirect(url_for('finance_party_import', kind=kind))
        # Mark which parties already exist (by GSTIN, then name).
        model = config['model']
        existing = db.query(model.id, model.name, model.gst_number, model.statement_cutoff).filter(
            model.company_id == company).all()
        by_name = {re.sub(r'\s+', ' ', (n or '').casefold()): (i, cut) for i, n, _g, cut in existing}
        by_gst = {(g or '').upper(): (i, cut) for i, _n, g, cut in existing if g}
        for party in parties:
            hit = by_gst.get(party['gst_number']) if party['gst_number'] else None
            hit = hit or by_name.get(re.sub(r'\s+', ' ', party['name'].casefold()))
            party['existing_id'] = hit[0] if hit else None
            party['existing_cutoff'] = bool(hit and hit[1])
        token = secrets.token_urlsafe(16)
        path = os.path.join(staging_dir(app), f'{company}_{token}.json')
        with open(path, 'w', encoding='utf-8') as handle:
            json.dump(dict(kind=kind, company=company, format=fmt, file_name=file_name, parties=parties,
                           warnings=warnings), handle, default=_json_default)
        session[f'party_import_{kind}'] = token
        summary = dict(parties=len(parties), new=sum(1 for p in parties if not p['existing_id']),
                       existing=sum(1 for p in parties if p['existing_id']),
                       bills=sum(len(p['bills']) for p in parties),
                       opening=round(sum(p['opening_balance'] for p in parties), 2),
                       warnings=sum(1 for p in parties if p['warnings']) + len(warnings))
        return render_template('finance_party_import_preview.html', kind=kind, config=config, parties=parties,
                               summary=summary, notes=notes, warnings=warnings, token=token, fmt=fmt,
                               file_name=file_name)

    @app.route('/finance/masters/<kind>/import/confirm', methods=['POST'])
    @login_required
    @require_permission('finance', 'view')
    def finance_party_import_confirm(kind):
        config, company, db = context(kind, 'create')
        token = request.form.get('token', '')
        if not token or token != session.get(f'party_import_{kind}') or not re.fullmatch(r'[\w-]+', token):
            flash('This import preview has expired. Upload the file again.', 'error')
            return redirect(url_for('finance_party_import', kind=kind))
        path = os.path.join(staging_dir(app), f'{company}_{token}.json')
        try:
            with open(path, encoding='utf-8') as handle:
                staged = json.load(handle)
        except (OSError, ValueError):
            flash('This import preview has expired. Upload the file again.', 'error')
            return redirect(url_for('finance_party_import', kind=kind))
        if staged.get('company') != company or staged.get('kind') != kind:
            abort(403)
        parties = _restore_dates(staged['parties'])
        selected = set(request.form.getlist('include'))
        mode = request.form.get('existing', 'skip')
        if mode == 'update' and not can(config['permission'], 'edit'):
            abort(403)
        user = get_user() or {}
        try:
            result = commit_parties(db, company, kind, [p for i, p in enumerate(parties) if str(i) in selected],
                                    mode, staged.get('format', ''), staged.get('file_name', ''),
                                    user.get('email') if isinstance(user, dict) else None,
                                    next_party_code, today_func())
        except ValueError as error:   # includes ClosedPeriodError
            db.rollback()
            flash(str(error), 'error')
            return redirect(url_for('finance_party_import', kind=kind))
        try:
            os.remove(path)
        except OSError:
            pass
        session.pop(f'party_import_{kind}', None)
        flash(f"Imported {config['plural'].lower()}: {result['created']} created, {result['updated']} updated, "
              f"{result['skipped']} skipped, {result['bills']} opening bill(s) recorded.", 'success')
        for message in result['messages'][:5]:
            flash(message, 'warning')
        return redirect(url_for('finance_party_master', kind=kind))

    @app.route('/finance/masters/<kind>/<int:party_id>/opening', methods=['GET', 'POST'])
    @login_required
    @require_permission('finance', 'view')
    def finance_party_opening(kind, party_id):
        config, company, db = context(kind)
        party = find_party(db, config, company, party_id)
        if request.method == 'POST':
            if not can(config['permission'], 'edit'):
                abort(403)
            action = request.form.get('action')
            try:
                if action == 'add':
                    amount, side = parse_amount(request.form.get('amount'))
                    if amount is None or amount == 0:
                        raise ValueError('Enter the bill amount.')
                    if request.form.get('side') and request.form.get('side') != config['normal']:
                        amount = -abs(amount)
                    db.add(PartyOpeningBill(company_id=company, party_type=config['party_type'], party_id=party.id,
                                            bill_no=(request.form.get('bill_no') or '').strip()[:100] or None,
                                            bill_date=parse_date(request.form.get('bill_date')),
                                            due_date=parse_date(request.form.get('due_date')),
                                            amount=round(amount, 2),
                                            notes=(request.form.get('notes') or '').strip()[:300] or None))
                    if request.form.get('sync'):
                        db.flush()
                        _sync_opening(db, company, config, party)
                    db.commit()
                    flash('Opening bill added.', 'success')
                elif action == 'delete':
                    bill = db.query(PartyOpeningBill).filter_by(
                        id=int(request.form.get('bill_id', 0) or 0), company_id=company,
                        party_type=config['party_type'], party_id=party.id).first()
                    if bill is None:
                        abort(404)
                    db.delete(bill)
                    if request.form.get('sync'):
                        db.flush()
                        _sync_opening(db, company, config, party)
                    db.commit()
                    flash('Opening bill removed.', 'success')
                elif action == 'sync':
                    if party.statement_cutoff:
                        raise ValueError('This statement has been closed/carried forward; '
                                         'its opening balance cannot be replaced from bills.')
                    _sync_opening(db, company, config, party)
                    db.commit()
                    flash('Opening balance set to the bills total.', 'success')
                else:
                    abort(400)
            except ValueError as error:
                db.rollback()
                flash(str(error), 'error')
            return redirect(url_for('finance_party_opening', kind=kind, party_id=party.id))
        rows = opening_statement(db, company, config['party_type'], party)
        opening = float(party.opening_balance or 0)
        if request.args.get('export') == 'xlsx':
            data = [[r['date'].strftime('%d-%m-%Y') if r['date'] else '', r['bill_no'] or
                     ('On account' if r['kind'] == 'on_account' else ''),
                     r['due_date'].strftime('%d-%m-%Y') if r['due_date'] else '', r['amount'], r['balance'],
                     r['notes']] for r in rows] or [['', 'Opening balance', '', opening, opening, '']]
            buf = xlsx_bytes(['Date', 'Bill No', 'Due Date', 'Amount', 'Balance', 'Notes'], data,
                             sheet='Opening statement', title=f'{party.name} - opening balance statement')
            return send_file(buf, as_attachment=True,
                             download_name=f'opening_statement_{party.id}.xlsx',
                             mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        today = today_func()
        for row in rows:
            row['overdue_days'] = (today - row['due_date']).days if row['due_date'] and row['due_date'] < today else 0
        return render_template('finance_party_opening.html', kind=kind, config=config, party=party, rows=rows,
                               opening=opening, bill_total=round(sum(r['amount'] for r in rows if r['kind'] == 'bill'), 2),
                               code=getattr(party, config['code_field']) or '',
                               can_edit=can(config['permission'], 'edit'), today=today.isoformat(),
                               statement_url=safe_url(config['statement'], **{config['statement_arg']: party.id}),
                               edit_url=safe_url(config['edit'], **{config['statement_arg']: party.id}))


def _sync_opening(db, company, config, party):
    total = db.query(func.coalesce(func.sum(PartyOpeningBill.amount), 0)).filter_by(
        company_id=company, party_type=config['party_type'], party_id=party.id).scalar()
    party.opening_balance = round(float(total or 0), 2)
    if not party.statement_cutoff:
        setattr(party, config['balance_field'], party.opening_balance)


def commit_parties(db, company, kind, parties, mode, fmt, file_name, actor, next_party_code, today):
    """Writes the confirmed parties in one transaction."""
    config = KINDS[kind]
    model = config['model']
    party_type = config['party_type']
    batch = PartyImportBatch(company_id=company, party_type=party_type, source_format=(fmt or 'file')[:20],
                             file_name=(file_name or '')[:255], imported_by=(actor or '')[:255])
    db.add(batch)
    db.flush()
    created = updated = skipped = bill_count = 0
    opening_total = 0.0
    messages = []
    by_name = {re.sub(r'\s+', ' ', (p.name or '').casefold()): p
               for p in db.query(model).filter(model.company_id == company)}
    by_gst = {(p.gst_number or '').upper(): p for p in by_name.values() if p.gst_number}
    for data in parties:
        target = (by_gst.get(data['gst_number']) if data.get('gst_number') else None) or \
            by_name.get(re.sub(r'\s+', ' ', data['name'].casefold()))
        if target is not None and mode != 'update':
            skipped += 1
            continue
        replace_opening = True
        if target is None:
            code = next_party_code(db, kind) if next_party_code else None
            target = model(company_id=company, name=data['name'], created_at=data.get('opening_date') or today)
            if code:
                setattr(target, config['code_field'], code)
            setattr(target, config['type_field'],
                    'Individual' if _key(data.get('party_type')) in ('individual', 'person', 'consumer')
                    else 'Business')
            target.status = 'Active'
            target.country = data.get('country') or 'India'
            target.gst_type = data.get('gst_type') or ('Regular' if data.get('gst_number') else 'Unregistered')
            db.add(target)
            created += 1
            by_name[re.sub(r'\s+', ' ', data['name'].casefold())] = target
        else:
            updated += 1
            if target.statement_cutoff:
                replace_opening = False
                messages.append(f'"{target.name}": statement already closed/carried forward - details updated, '
                                'opening balance left unchanged.')
        for field in ('contact_person', 'phone', 'alternate_phone', 'email', 'website', 'address_line1',
                      'address_line2', 'city', 'state', 'pincode', 'currency', 'gst_number', 'pan_number',
                      'trn_number'):
            value = data.get(field)
            if value and (mode == 'update' or not getattr(target, field, None)):
                setattr(target, field, value)
        if data.get('country'):
            target.country = data['country']
        if data.get('gst_type') and updated:
            target.gst_type = data['gst_type'][:30]
        if data.get('credit_limit') not in (None, ''):
            target.credit_limit = float(data['credit_limit'])
        if data.get('credit_days') not in (None, ''):
            target.credit_days = int(data['credit_days'])
        if data.get('notes') and not target.notes:
            target.notes = data['notes']
        if data.get('code') and data['code'] != getattr(target, config['code_field']):
            note = f'Code in previous software: {data["code"]}'
            if note not in (target.notes or ''):
                target.notes = ((target.notes or '') + ('\n' if target.notes else '') + note)[:2000]
        db.flush()
        if not replace_opening:
            continue
        db.query(PartyOpeningBill).filter_by(company_id=company, party_type=party_type,
                                              party_id=target.id).delete(synchronize_session=False)
        target.opening_balance = float(data.get('opening_balance') or 0)
        setattr(target, config['balance_field'], target.opening_balance)
        opening_total += target.opening_balance
        for bill in data['bills']:
            db.add(PartyOpeningBill(company_id=company, party_type=party_type, party_id=target.id,
                                    bill_no=bill.get('bill_no') or None, bill_date=bill.get('bill_date'),
                                    due_date=bill.get('due_date'), amount=float(bill['amount']),
                                    notes=bill.get('notes') or None, batch_id=batch.id))
            bill_count += 1
    batch.created_count, batch.updated_count, batch.skipped_count = created, updated, skipped
    batch.bill_count, batch.opening_total = bill_count, round(opening_total, 2)
    db.commit()
    return dict(created=created, updated=updated, skipped=skipped, bills=bill_count, messages=messages,
                batch_id=batch.id)

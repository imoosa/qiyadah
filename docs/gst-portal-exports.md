# GST portal exports

Open **Finance → GST e-invoice & e-way bill**, or the GST button on a sales invoice.
Choose an invoice, review the saved lines, enter missing address details and confirm
place of supply. Downloads validate saved amounts; they do not change invoices,
payment status, ledger entries or customer records. Supplementary address/transport
details apply to the current download only.

## Supported in this first version

- Regular domestic B2B tax invoices in INR, with a registered Indian GST seller and buyer.
- E-invoice JSON (schema 1.1): goods or services, optionally with road transport
  details for goods-only invoices.
- Standalone NIC bulk e-way bill JSON for outward goods supply by road when the
  user confirms that an IRN is not required. This is available in Finance plans;
  it does not grant access to Supply Chain operations.
- Dispatch from seller address and delivery to buyer billing address only.
- Company-scoped sales and workshop invoice access, using existing document permissions.

GSTIN syntax/checksum, document number/date, PIN format, HSN/SAC format, unit codes,
finite amounts, saved totals, tax splits and road-transport details are checked.
Portal master checks (including active GST registration, actual HSN validity and
PIN/state mapping), taxpayer applicability and reporting deadlines remain with
the portal. No turnover eligibility assumptions are made locally.

## Upload and acknowledgement

1. For an invoice requiring an IRN, download **e-invoice JSON** and upload through
   the IRP bulk JSON workflow. Include transport details when requesting an EWB
   with the IRN. If an IRN already exists, use the portal's EWB-against-IRN flow.
2. For an invoice not requiring an IRN, download **e-way bill JSON** and use the
   e-way bill portal's bulk generation workflow.
3. Review portal results and retain the official acknowledgement, signed invoice,
   QR code and/or e-way bill as applicable. A downloaded file is not an issued document.

No provider credentials, network submission, acknowledgement import, cancellation,
validity tracking, signed QR printing or local registration status is implemented.
Do not upload an invoice twice. Exports/SEZ/deemed exports, reverse charge, cess,
special valuation, notes, B2C, multiple delivery addresses and non-road transport
must currently be handled on the portal. Do not edit a registered invoice through
this workflow; it provides no IRN lifecycle management.

## References checked 7 October 2026

- [IRP notified e-invoice schema](https://einvoice6.gst.gov.in/content/notified-e-invoice-schema/)
- [IRP document number rules](https://einvoice6.gst.gov.in/content/irn-2/)
- [NIC bulk upload specification](https://docs.ewaybillgst.gov.in/html/formatdownloadnew.html)
- [NIC attributes workbook](https://docs.ewaybillgst.gov.in/Documents/bulkewb/EWB_Attributes_new.xlsx)

`gst-schema.txt` and `gst-sample-json.txt` are unmodified text extractions of the
NIC workbook's Schema and Sample JSON sheets. The published workbook sample uses
bulk wrapper version `1.0.1118` despite its later workbook release date. The schema
contains a numeric/string enum inconsistency for `transType`; exports follow the
numeric field and the official sample. These sources describe upload formats;
they are not a promise that a portal will accept any particular invoice.

Run `python -m unittest discover -s tests -p test_gst_portal.py` for isolated tests.
Live portal acceptance requires the user's portal account and has not been tested.

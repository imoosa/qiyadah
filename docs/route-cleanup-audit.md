> Superseded by [ERP logistics removal](erp-logistics-removal.md). The aliases described below have since been removed.

# Qiyadah route audit and logistics cleanup

Source audit: 2026-10-03. Reviewed 484 decorator-defined route declarations across 18 Python files, including the legacy migration module. This is a source inventory, not a count verified against the running server. No production usage logs or database data were inspected.

## Changes

- Removed four diagnostic handlers with no references outside their definitions: `/debug/price-lists-data`, `/debug/price-list/<int:price_list_id>`, `/debug/excel-columns`, `/debug/suppliers`. No production feature handlers or financial records were deleted.
- Assigned 48 active logistics routes explicit canonical paths and updated their in-app literal links. Existing endpoint identifiers remain stable for Python/Jinja callers. Legacy paths are compatibility aliases using the same handlers, permissions and methods; POST bodies are not redirected or lost.
- Preserved `/track`, `/track/<company_slug>` and `/t/<company_id>/<docket_no>` because customers and printed documents may use these public links.
- Fixed the welcome shortcut from nonexistent `/bookings/new` to the actual booking endpoint. Clarified booking navigation labels and courier price-list titles.

## Why the business routes remain

| Group | Dependency evidence | Decision |
|---|---|---|
| Docket booking | Booking screens, customer statements, receipt allocations, aggregate invoice links and finance checks use the legacy Invoice records. | Keep as logistics bookings; preserve stored model and financial links. |
| Manifests | Forms, dispatch actions, generated documents and stock movement workflows refer to these endpoints. | Keep as logistics manifests. |
| Rates and courier price lists | Booking forms, quotes and rate calculator consume the lookup APIs. | Keep under logistics rates and carrier price lists. |
| AWB/docket lookups | Purchase forms and manifests consume shipment information. | Keep explicit logistics API names. |
| Purchase generation from booking | Purchase list includes an action that invokes it. | Rename to purchase-invoices/from-logistics-booking. |
| Tracking | Public URLs can be used outside the repository and on previously shared documents. | Keep existing public routes. |

## Canonical path map

| Endpoint | Previous path (still accepted) | Canonical path |
|---|---|---|
| `price_lists` | `/price-lists` | `/logistics/carrier-price-lists` |
| `view_price_list` | `/price-lists/view/<int:price_list_id>` | `/logistics/carrier-price-lists/view/<int:price_list_id>` |
| `delete_price_list` | `/price-lists/delete/<int:price_list_id>` | `/logistics/carrier-price-lists/delete/<int:price_list_id>` |
| `upload_price_list` | `/price-lists/upload` | `/logistics/carrier-price-lists/upload` |
| `api_rate_lookup` | `/api/rate-lookup` | `/api/logistics/rates/sales-lookup` |
| `rate_calculator` | `/rate-calculator` | `/logistics/rates/calculator` |
| `api_rate_calculator` | `/api/rate-calculator` | `/api/logistics/rates/calculate` |
| `api_rate_calculator_destinations` | `/api/rate-calculator/destinations` | `/api/logistics/rates/destinations` |
| `api_purchase_rate_lookup` | `/api/purchase-rate-lookup` | `/api/logistics/rates/purchase-lookup` |
| `api_price_lists_list` | `/api/price-lists/list` | `/api/logistics/carrier-price-lists/list` |
| `purchase_generate_from_booking` | `/purchase/generate-from-booking` | `/purchase-invoices/from-logistics-booking` |
| `invoice_list` | `/booking/list` | `/logistics/bookings/list` |
| `invoice_list_update_tracking` | `/booking/list/update-tracking/<invoice_id>` | `/logistics/bookings/list/update-tracking/<invoice_id>` |
| `invoice_list_update_tracking_status` | `/booking/list/update-tracking-status/<invoice_id>` | `/logistics/bookings/list/update-tracking-status/<invoice_id>` |
| `invoice_list_record_payment` | `/booking/list/record-payment/<invoice_id>` | `/logistics/bookings/list/record-payment/<invoice_id>` |
| `invoice_hard_delete` | `/booking/hard-delete/<invoice_id>` | `/logistics/bookings/hard-delete/<invoice_id>` |
| `invoice_deleted_log` | `/booking/deleted-log` | `/logistics/bookings/deleted-log` |
| `invoice_new` | `/booking/new` | `/logistics/bookings/new` |
| `invoice_edit` | `/booking/edit/<invoice_id>` | `/logistics/bookings/edit/<invoice_id>` |
| `invoice_customer_update` | `/booking/customer/update` | `/logistics/bookings/customer/update` |
| `invoice_view` | `/booking/view/<invoice_id>` | `/logistics/bookings/view/<invoice_id>` |
| `invoice_pdf` | `/booking/pdf/<invoice_id>` | `/logistics/bookings/pdf/<invoice_id>` |
| `invoice_resale_charges` | `/booking/<invoice_id>/resale-charges` | `/logistics/bookings/<invoice_id>/resale-charges` |
| `invoice_customer_check_credit_limit` | `/booking/customer/check-credit-limit` | `/logistics/bookings/customer/check-credit-limit` |
| `invoice_void` | `/booking/void/<invoice_id>` | `/logistics/bookings/void/<invoice_id>` |
| `invoice_clone` | `/booking/clone/<invoice_id>` | `/logistics/bookings/clone/<invoice_id>` |
| `invoice_customer_new` | `/booking/customer` | `/logistics/bookings/customer` |
| `invoice_customer_save` | `/booking/customer/save` | `/logistics/bookings/customer/save` |
| `api_docket_info` | `/api/docket-info/<docket_no>` | `/api/logistics/dockets/<docket_no>` |
| `api_purchase_awb_list` | `/api/purchase/awb-list` | `/api/logistics/purchase-dockets` |
| `api_purchase_awb_info` | `/api/purchase/awb-info/<docket_no>` | `/api/logistics/purchase-dockets/details/<docket_no>` |
| `manifest_list` | `/manifest/list` | `/logistics/manifests/list` |
| `manifest_create` | `/manifest/create` | `/logistics/manifests/create` |
| `shipper_last_dockets` | `/manifest/shipper-dockets/<int:client_id>` | `/logistics/manifests/shipper-dockets/<int:client_id>` |
| `invoice_packages` | `/manifest/invoice-packages/<int:client_id>/<docket_no>` | `/logistics/manifests/invoice-packages/<int:client_id>/<docket_no>` |
| `manifest_save` | `/manifest/save` | `/logistics/manifests/save` |
| `manifest_view` | `/manifest/view/<int:manifest_db_id>` | `/logistics/manifests/view/<int:manifest_db_id>` |
| `manifest_print` | `/manifest/print/<int:manifest_db_id>` | `/logistics/manifests/print/<int:manifest_db_id>` |
| `manifest_print_day` | `/manifest/print/day/<date_str>` | `/logistics/manifests/print/day/<date_str>` |
| `manifest_print_selected` | `/manifest/print/selected` | `/logistics/manifests/print/selected` |
| `manifest_generate_company` | `/manifest/generate/company` | `/logistics/manifests/generate/company` |
| `manifest_revert_to_pending` | `/manifest/revert-to-pending` | `/logistics/manifests/revert-to-pending` |
| `manifest_print_company` | `/manifest/print/company/<company_name>` | `/logistics/manifests/print/company/<company_name>` |
| `manifest_edit` | `/manifest/edit/<int:manifest_db_id>` | `/logistics/manifests/edit/<int:manifest_db_id>` |
| `manifest_update` | `/manifest/update/<int:manifest_db_id>` | `/logistics/manifests/update/<int:manifest_db_id>` |
| `manifest_delete` | `/manifest/delete/<int:manifest_db_id>` | `/logistics/manifests/delete/<int:manifest_db_id>` |
| `manifest_print_selected_generated` | `/manifest/print/selected/generated` | `/logistics/manifests/print/selected/generated` |
| `mark_entry_dispatched` | `/manifest/entry/<int:entry_id>/dispatch` | `/logistics/manifests/entry/<int:entry_id>/dispatch` |

## Complete source inventory

References are static matches outside the defining function, excluding tests and historical documentation/backups. A reference supports retaining a route; absence of a reference does not establish lack of external, dynamic or bookmarked usage. Unreferenced business endpoints were retained pending runtime evidence. Source locations below refer to the pre-change inventory.

| File | Route | Methods | Static reference count | Decision |
|---|---|---|---|---|
| `admin_access.py` | `/api/admin/access/catalog` | GET | 1 | Retained; referenced |
| `admin_access.py` | `/api/admin/access/<scope>/<path:target>` | GET, PUT | 0 | Retained; external/dynamic usage unverified |
| `admin_access.py` | `/api/admin/access/open-company/<company_id>` | POST | 0 | Retained; external/dynamic usage unverified |
| `api_key_settings_page.py` | `/settings/api-keys` | GET, POST | 2 | Retained; referenced |
| `api_key_settings_page.py` | `/settings/api-keys/<int:key_id>/revoke` | POST | 1 | Retained; referenced |
| `app.py` | `/api/dismiss-expiry-popup` | POST | 1 | Retained; referenced |
| `app.py` | `/api/currency/list` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/api/currency/exchange-rate` | GET | 3 | Retained; referenced |
| `app.py` | `/no-access` | GET | 2 | Retained; referenced |
| `app.py` | `/` | GET | 531 | Retained; referenced |
| `app.py` | `/api/ai-chat` | POST | 1 | Retained; referenced |
| `app.py` | `/api/ai-chat/clear` | POST | 1 | Retained; referenced |
| `app.py` | `/health` | GET | 2 | Retained; referenced |
| `app.py` | `/sw.js` | GET | 2 | Retained; referenced |
| `app.py` | `/login` | GET, POST | 123 | Retained; referenced |
| `app.py` | `/company/update-terms` | POST | 1 | Retained; referenced |
| `app.py` | `/verify-otp` | GET, POST | 6 | Retained; referenced |
| `app.py` | `/verify-otp/resend` | GET | 3 | Retained; referenced |
| `app.py` | `/force-change-password` | GET, POST | 4 | Retained; referenced |
| `app.py` | `/account-setup` | GET, POST | 1 | Retained; referenced |
| `app.py` | `/account-setup/resend` | GET | 1 | Retained; referenced |
| `app.py` | `/company/add` | GET, POST | 4 | Retained; referenced |
| `app.py` | `/select-company` | GET, POST | 17 | Retained; referenced |
| `app.py` | `/company/toggle-mobile-visibility/<company_id>` | POST | 1 | Retained; referenced |
| `app.py` | `/switch-company/<company_id>` | GET | 1 | Retained; referenced |
| `app.py` | `/onboarding/create-company` | GET, POST | 3 | Retained; referenced |
| `app.py` | `/api/payment/create-order` | POST | 3 | Retained; referenced |
| `app.py` | `/api/payment/verify` | POST | 3 | Retained; referenced |
| `app.py` | `/register` | GET, POST | 31 | Retained; referenced |
| `app.py` | `/logout` | GET | 31 | Retained; referenced |
| `app.py` | `/reports/export-selector` | GET | 2 | Retained; referenced |
| `app.py` | `/reports/export-excel` | GET | 2 | Retained; referenced |
| `app.py` | `/reports-dashboard` | GET | 18 | Retained; referenced |
| `app.py` | `/dashboard` | GET | 147 | Retained; referenced |
| `app.py` | `/api/dashboard-data` | GET | 2 | Retained; referenced |
| `app.py` | `/bi-intelligence` | GET | 28 | Retained; referenced |
| `app.py` | `/bi-executive` | GET | 3 | Retained; referenced |
| `app.py` | `/bi-dashboard` | GET | 23 | Retained; referenced |
| `app.py` | `/api/bi/dashboard` | GET | 2 | Retained; referenced |
| `app.py` | `/api/bi/company-analysis` | GET | 1 | Retained; referenced |
| `app.py` | `/price-lists` | GET | 43 | Renamed; legacy alias retained |
| `app.py` | `/price-lists/view/<int:price_list_id>` | GET | 1 | Renamed; legacy alias retained |
| `app.py` | `/debug/price-lists-data` | GET | 0 | Removed diagnostic |
| `app.py` | `/price-lists/delete/<int:price_list_id>` | POST | 1 | Renamed; legacy alias retained |
| `app.py` | `/debug/price-list/<int:price_list_id>` | GET | 0 | Removed diagnostic |
| `app.py` | `/debug/excel-columns` | POST | 0 | Removed diagnostic |
| `app.py` | `/price-lists/upload` | GET, POST | 4 | Renamed; legacy alias retained |
| `app.py` | `/api/rate-lookup` | GET | 1 | Renamed; legacy alias retained |
| `app.py` | `/rate-calculator` | GET | 3 | Renamed; legacy alias retained |
| `app.py` | `/api/rate-calculator` | GET, POST | 1 | Renamed; legacy alias retained |
| `app.py` | `/api/rate-calculator/destinations` | GET | 0 | Renamed; legacy alias retained |
| `app.py` | `/admin/repair-manifest-shippers` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/admin/repair-purchase-item-descriptions` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/company/permissions/fields/<role>` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/company/permissions/fields/user/<user_id>` | POST | 3 | Retained; referenced |
| `app.py` | `/inventory/clear_party_stock` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/api/purchase-rate-lookup` | GET | 1 | Renamed; legacy alias retained |
| `app.py` | `/api/price-lists/list` | GET | 0 | Renamed; legacy alias retained |
| `app.py` | `/clients/check_similar` | GET | 1 | Retained; referenced |
| `app.py` | `/clients` | GET | 35 | Retained; referenced |
| `app.py` | `/clients/<int:client_pk>/remove` | POST | 2 | Retained; referenced |
| `app.py` | `/clients/<int:client_pk>/restore` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/clients/new` | GET, POST | 5 | Retained; referenced |
| `app.py` | `/clients/add` | GET, POST | 1 | Retained; referenced |
| `app.py` | `/clients/<int:client_pk>` | GET | 5 | Retained; referenced |
| `app.py` | `/clients/<int:client_pk>/statement` | GET | 7 | Retained; referenced |
| `app.py` | `/clients/<int:client_pk>/statement/archive/<int:archive_id>` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/clients/<int:client_pk>/edit` | GET, POST | 1 | Retained; referenced |
| `app.py` | `/clients/<int:client_pk>/delete` | GET, POST | 3 | Retained; referenced |
| `app.py` | `/clients/<int:client_pk>/shift-to-opening` | GET, POST | 1 | Retained; referenced |
| `app.py` | `/inventory` | GET | 21 | Retained; referenced |
| `app.py` | `/inventory/new` | GET, POST | 3 | Retained; referenced |
| `app.py` | `/inventory/add` | GET, POST | 3 | Retained; referenced |
| `app.py` | `/inventory/edit/<int:item_pk>` | GET, POST | 2 | Retained; referenced |
| `app.py` | `/stock/inward` | POST | 1 | Retained; referenced |
| `app.py` | `/stock/adjust` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/stock/movements/<item_identifier>` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/inventory/delete/<int:item_pk>` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/api/stock/items` | GET | 1 | Retained; referenced |
| `app.py` | `/stock/item/<code>` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/purchase/list` | GET | 17 | Retained; referenced |
| `app.py` | `/purchase/generate-from-booking` | POST | 1 | Renamed; legacy alias retained |
| `app.py` | `/purchase/delete/<invoice_id>` | POST | 1 | Retained; referenced |
| `app.py` | `/api/purchase/scan-bill` | POST | 3 | Retained; referenced |
| `app.py` | `/uploads/purchase_invoices/<path:filename>` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/purchase/file/<path:filename>` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/purchase/new` | GET, POST | 6 | Retained; referenced |
| `app.py` | `/purchase/edit/<invoice_id>` | GET, POST | 3 | Retained; referenced |
| `app.py` | `/purchase/view/<invoice_id>` | GET | 12 | Retained; referenced |
| `app.py` | `/purchase/pay/<int:pk>` | POST | 2 | Retained; referenced |
| `app.py` | `/booking/list` | GET | 29 | Renamed; legacy alias retained |
| `app.py` | `/booking/list/update-tracking/<invoice_id>` | POST | 0 | Renamed; legacy alias retained |
| `app.py` | `/booking/list/update-tracking-status/<invoice_id>` | POST | 0 | Renamed; legacy alias retained |
| `app.py` | `/booking/list/record-payment/<invoice_id>` | POST | 4 | Renamed; legacy alias retained |
| `app.py` | `/booking/hard-delete/<invoice_id>` | POST | 0 | Renamed; legacy alias retained |
| `app.py` | `/booking/deleted-log` | GET | 1 | Renamed; legacy alias retained |
| `app.py` | `/booking/new` | GET, POST | 7 | Renamed; legacy alias retained |
| `app.py` | `/booking/edit/<invoice_id>` | GET, POST | 1 | Renamed; legacy alias retained |
| `app.py` | `/booking/customer/update` | POST | 13 | Renamed; legacy alias retained |
| `app.py` | `/booking/view/<invoice_id>` | GET | 6 | Renamed; legacy alias retained |
| `app.py` | `/company/reset-user-password/<email>` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/booking/pdf/<invoice_id>` | GET | 0 | Renamed; legacy alias retained |
| `app.py` | `/booking/<invoice_id>/resale-charges` | GET, POST | 0 | Renamed; legacy alias retained |
| `app.py` | `/booking/customer/check-credit-limit` | POST | 1 | Renamed; legacy alias retained |
| `app.py` | `/customer-invoices` | GET | 17 | Retained; referenced |
| `app.py` | `/customer-invoices/new` | GET | 3 | Retained; referenced |
| `app.py` | `/customer-invoices/create` | POST | 4 | Retained; referenced |
| `app.py` | `/customer-invoices/edit/<int:cust_inv_id>` | GET, POST | 3 | Retained; referenced |
| `app.py` | `/customer-invoices/view/<int:cust_inv_id>` | GET | 18 | Retained; referenced |
| `app.py` | `/customer-invoices/delete/<int:cust_inv_id>` | POST | 1 | Retained; referenced |
| `app.py` | `/customer-invoices/print/<int:cust_inv_id>` | GET | 2 | Retained; referenced |
| `app.py` | `/admin/fix-duplicate-awbs` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/booking/void/<invoice_id>` | POST | 1 | Renamed; legacy alias retained |
| `app.py` | `/booking/clone/<invoice_id>` | GET | 1 | Renamed; legacy alias retained |
| `app.py` | `/company/clear-data` | POST | 1 | Retained; referenced |
| `app.py` | `/booking/customer` | GET | 5 | Renamed; legacy alias retained |
| `app.py` | `/booking/customer/save` | POST | 21 | Renamed; legacy alias retained |
| `app.py` | `/api/suppliers/list` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/suppliers` | GET | 12 | Retained; referenced |
| `app.py` | `/suppliers/new` | GET, POST | 3 | Retained; referenced |
| `app.py` | `/debug/suppliers` | GET | 0 | Removed diagnostic |
| `app.py` | `/suppliers/<int:supplier_pk>` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/suppliers/<int:supplier_pk>/statement` | GET | 7 | Retained; referenced |
| `app.py` | `/suppliers/<int:supplier_pk>/statement/archive/<int:archive_id>` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/suppliers/<int:supplier_pk>/edit` | GET, POST | 1 | Retained; referenced |
| `app.py` | `/suppliers/<int:supplier_pk>/delete` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/suppliers/<int:supplier_pk>/shift-to-opening` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/api/supplier/<int:supplier_pk>/brands` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/api/customers/list` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/api/stock/items/by-client/<int:client_id>` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/api/docket-info/<docket_no>` | GET | 0 | Renamed; legacy alias retained |
| `app.py` | `/api/purchase/awb-list` | GET | 0 | Renamed; legacy alias retained |
| `app.py` | `/api/purchase/awb-info/<docket_no>` | GET | 0 | Renamed; legacy alias retained |
| `app.py` | `/estimate/new` | GET, POST | 7 | Retained; referenced |
| `app.py` | `/estimate/list` | GET | 11 | Retained; referenced |
| `app.py` | `/estimate/view/<estimate_id>` | GET | 3 | Retained; referenced |
| `app.py` | `/estimate/edit/<estimate_id>` | GET, POST | 3 | Retained; referenced |
| `app.py` | `/estimate/update` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/estimate/convert_to_so/<estimate_id>` | POST | 2 | Retained; referenced |
| `app.py` | `/estimate/convert_to_invoice/<estimate_id>` | POST | 1 | Retained; referenced |
| `app.py` | `/estimate/convert/<estimate_id>` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/estimate/delete/<estimate_id>` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/manifest/list` | GET | 40 | Renamed; legacy alias retained |
| `app.py` | `/manifest/create` | GET | 2 | Renamed; legacy alias retained |
| `app.py` | `/manifest/shipper-dockets/<int:client_id>` | GET | 0 | Renamed; legacy alias retained |
| `app.py` | `/manifest/invoice-packages/<int:client_id>/<docket_no>` | GET | 6 | Renamed; legacy alias retained |
| `app.py` | `/expenses` | GET | 156 | Retained; referenced |
| `app.py` | `/expenses/add` | GET, POST | 1 | Retained; referenced |
| `app.py` | `/expenses/edit/<int:expense_id>` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/expenses/delete/<int:expense_id>` | POST | 3 | Retained; referenced |
| `app.py` | `/api/expenses-summary` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/manifest/save` | POST | 1 | Renamed; legacy alias retained |
| `app.py` | `/manifest/view/<int:manifest_db_id>` | GET | 0 | Renamed; legacy alias retained |
| `app.py` | `/manifest/print/<int:manifest_db_id>` | GET | 1 | Renamed; legacy alias retained |
| `app.py` | `/manifest/print/day/<date_str>` | GET | 7 | Renamed; legacy alias retained |
| `app.py` | `/manifest/print/selected` | GET | 2 | Renamed; legacy alias retained |
| `app.py` | `/manifest/generate/company` | POST | 3 | Renamed; legacy alias retained |
| `app.py` | `/manifest/revert-to-pending` | POST | 1 | Renamed; legacy alias retained |
| `app.py` | `/manifest/print/company/<company_name>` | GET | 1 | Renamed; legacy alias retained |
| `app.py` | `/manifest/edit/<int:manifest_db_id>` | GET | 0 | Renamed; legacy alias retained |
| `app.py` | `/manifest/update/<int:manifest_db_id>` | POST | 0 | Renamed; legacy alias retained |
| `app.py` | `/manifest/delete/<int:manifest_db_id>` | GET, POST | 0 | Renamed; legacy alias retained |
| `app.py` | `/migrations` | GET | 23 | Retained; referenced |
| `app.py` | `/migrations/run` | POST | 3 | Retained; referenced |
| `app.py` | `/migrations/history` | GET | 2 | Retained; referenced |
| `app.py` | `/migrations/history/<company_id>` | GET | 2 | Retained; referenced |
| `app.py` | `/admin/dashboard` | GET | 11 | Retained; referenced |
| `app.py` | `/admin/companies` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/admin/company/<company_id>` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/admin/company/<company_id>/update-plan` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/admin/company/<company_id>/renew` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/admin/company/<company_id>/toggle-status` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/admin/company/<company_id>/edit` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/admin/user/<user_id>/edit` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/admin/user/<user_id>/delete` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/admin/users` | GET | 1 | Retained; referenced |
| `app.py` | `/admin/company/<company_id>/delete` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/admin/register-client` | GET, POST | 2 | Retained; referenced |
| `app.py` | `/employees` | GET | 4 | Retained; referenced |
| `app.py` | `/employees/add` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/employees/toggle/<user_id>` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/api/product/<code>` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/api/products/search` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/cash-in-hand` | GET | 13 | Retained; referenced |
| `app.py` | `/api/cash-transaction/save` | POST | 1 | Retained; referenced |
| `app.py` | `/api/cash-transaction/delete/<int:txn_id>` | DELETE | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/bank-accounts` | GET | 59 | Retained; referenced |
| `app.py` | `/bank-accounts/add` | POST | 1 | Retained; referenced |
| `app.py` | `/bank-accounts/<int:account_id>/transactions` | GET | 31 | Retained; referenced |
| `app.py` | `/bank-accounts/<int:account_id>/add-transaction` | POST | 1 | Retained; referenced |
| `app.py` | `/bank-accounts/<int:account_id>/delete` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/bank-accounts/<int:account_id>/reactivate` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/bank-accounts/<int:account_id>/delete-permanent` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/bank-accounts/<int:account_id>/transfer` | POST | 12 | Retained; referenced |
| `app.py` | `/admin/repair-party-names` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/cheques` | GET | 68 | Retained; referenced |
| `app.py` | `/cheques/save` | POST | 1 | Retained; referenced |
| `app.py` | `/cheques/<int:cheque_id>/clear` | POST | 1 | Retained; referenced |
| `app.py` | `/cheques/<int:cheque_id>/bounce` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/cheques/<int:cheque_id>/cancel` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/loan-accounts` | GET | 5 | Retained; referenced |
| `app.py` | `/api/loan/save` | POST | 1 | Retained; referenced |
| `app.py` | `/api/loan/repayment/save` | POST | 1 | Retained; referenced |
| `app.py` | `/ledger` | GET | 165 | Retained; referenced |
| `app.py` | `/trial-balance` | GET | 7 | Retained; referenced |
| `app.py` | `/api/reports/sales-data` | GET | 1 | Retained; referenced |
| `app.py` | `/api/reports/purchase-data` | GET | 1 | Retained; referenced |
| `app.py` | `/api/reports/stock-data` | GET | 1 | Retained; referenced |
| `app.py` | `/api/reports/tax-data` | GET | 2 | Retained; referenced |
| `app.py` | `/api/reports/financial-data` | GET | 1 | Retained; referenced |
| `app.py` | `/reports/profit-loss` | GET | 2 | Retained; referenced |
| `app.py` | `/reports/balance-sheet` | GET | 2 | Retained; referenced |
| `app.py` | `/reports/cash-flow` | GET | 2 | Retained; referenced |
| `app.py` | `/sync` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/share` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/integrations` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/addons` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/import` | GET | 1 | Retained; referenced |
| `app.py` | `/export` | GET | 6 | Retained; referenced |
| `app.py` | `/audit-log` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/profile` | GET | 48 | Retained; referenced |
| `app.py` | `/company/settings` | GET | 49 | Retained; referenced |
| `app.py` | `/company/permissions/role/<role>` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/company/permissions/user/<user_id>` | POST | 3 | Retained; referenced |
| `app.py` | `/settings/whatsapp` | GET, POST | 9 | Retained; referenced |
| `app.py` | `/settings/whatsapp/disconnect` | POST | 1 | Retained; referenced |
| `app.py` | `/settings/whatsapp/test` | POST | 1 | Retained; referenced |
| `app.py` | `/company/update-info` | POST | 3 | Retained; referenced |
| `app.py` | `/manifest/print/selected/generated` | GET | 1 | Renamed; legacy alias retained |
| `app.py` | `/settings/whatsapp/templates` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/company/change-password` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/company/add-user` | POST | 2 | Retained; referenced |
| `app.py` | `/company/revoke-user/<email>/<company_id>` | GET | 3 | Retained; referenced |
| `app.py` | `/company/remove-user/<user_id>` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/company/delete-user/<email>` | GET, POST | 2 | Retained; referenced |
| `app.py` | `/company/edit-user-access/<email>` | POST | 1 | Retained; referenced |
| `app.py` | `/company/upgrade-plan` | POST | 1 | Retained; referenced |
| `app.py` | `/debtors` | GET | 10 | Retained; referenced |
| `app.py` | `/creditors` | GET | 8 | Retained; referenced |
| `app.py` | `/debtors/<int:client_pk>/statement` | GET | 5 | Retained; referenced |
| `app.py` | `/debtors/<int:client_pk>/shift-to-opening` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/debtors/<int:client_pk>/close` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/debtors/<int:client_pk>/statement/archive/<int:archive_id>` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/creditors/<int:supplier_pk>/statement` | GET | 1 | Retained; referenced |
| `app.py` | `/creditors/<int:supplier_pk>/statement/archive/<int:archive_id>` | GET | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/receipts/new` | GET | 22 | Retained; referenced |
| `app.py` | `/receipts/save` | POST | 7 | Retained; referenced |
| `app.py` | `/payments/new` | GET | 23 | Retained; referenced |
| `app.py` | `/payments/save` | POST | 4 | Retained; referenced |
| `app.py` | `/backup` | GET | 109 | Retained; referenced |
| `app.py` | `/backup/create` | POST | 1 | Retained; referenced |
| `app.py` | `/backup/restore/<backup_id>` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/backup/download/<backup_id>` | GET | 1 | Retained; referenced |
| `app.py` | `/backup/delete/<backup_id>` | POST | 1 | Retained; referenced |
| `app.py` | `/backup/schedule` | POST | 1 | Retained; referenced |
| `app.py` | `/backup/upload-to-cloud/<backup_id>` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/backup/upload` | POST | 3 | Retained; referenced |
| `app.py` | `/company/api-keys/generate` | POST | 1 | Retained; referenced |
| `app.py` | `/company/api-keys/<int:key_id>/revoke` | POST | 0 | Retained; external/dynamic usage unverified |
| `app.py` | `/manifest/entry/<int:entry_id>/dispatch` | POST | 0 | Renamed; legacy alias retained |
| `app.py` | `/track/<company_slug>` | GET, POST | 2 | Retained; referenced |
| `app.py` | `/t/<company_id>/<docket_no>` | GET | 2 | Retained; referenced |
| `app.py` | `/track` | GET, POST | 6 | Retained; referenced |
| `app.py` | `/payment/delete` | GET, POST | 1 | Retained; referenced |
| `app.py` | `/receipt/delete` | GET, POST | 1 | Retained; referenced |
| `app.py` | `/payment/edit-data` | GET | 1 | Retained; referenced |
| `app.py` | `/payment/update` | POST | 1 | Retained; referenced |
| `app.py` | `/receipt/edit-data` | GET | 1 | Retained; referenced |
| `app.py` | `/receipt/update` | POST | 1 | Retained; referenced |
| `app.py` | `/finance/tax-report` | GET | 3 | Retained; referenced |
| `app.py` | `/finance/bank-reconciliation` | GET, POST | 2 | Retained; referenced |
| `app.py` | `/finance/fixed-assets` | GET, POST | 8 | Retained; referenced |
| `app.py` | `/finance/fixed-assets/<int:asset_id>/post-depreciation` | POST | 1 | Retained; referenced |
| `app.py` | `/finance/dashboard` | GET | 1 | Retained; referenced |
| `app.py` | `/finance/chart-of-accounts` | GET, POST | 14 | Retained; referenced |
| `app.py` | `/finance/chart-of-accounts/<int:account_id>/edit` | POST | 1 | Retained; referenced |
| `app.py` | `/finance/journals` | GET | 12 | Retained; referenced |
| `app.py` | `/finance/journals/new` | GET, POST | 1 | Retained; referenced |
| `app.py` | `/finance/journals/<int:entry_id>` | GET | 17 | Retained; referenced |
| `app.py` | `/finance/journals/<int:entry_id>/post` | POST | 1 | Retained; referenced |
| `app.py` | `/finance/journals/<int:entry_id>/reverse` | POST | 1 | Retained; referenced |
| `app.py` | `/apps` | GET | 18 | Retained; referenced |
| `crm_routes.py` | `/crm` | GET | 8 | Retained; referenced |
| `crm_routes.py` | `/crm/dashboard` | GET | 2 | Retained; referenced |
| `crm_routes.py` | `/api/crm/dashboard` | GET | 2 | Retained; referenced |
| `crm_routes.py` | `/api/crm/clients` | GET, POST | 2 | Retained; referenced |
| `crm_routes.py` | `/api/crm/clients/<client_id>` | GET, PUT, DELETE | 0 | Retained; external/dynamic usage unverified |
| `crm_routes.py` | `/api/crm/clients/<client_id>/360` | GET | 0 | Retained; external/dynamic usage unverified |
| `crm_routes.py` | `/api/crm/contacts` | GET, POST | 1 | Retained; referenced |
| `crm_routes.py` | `/api/crm/contacts/<contact_id>` | DELETE | 0 | Retained; external/dynamic usage unverified |
| `crm_routes.py` | `/api/crm/leads` | GET, POST | 2 | Retained; referenced |
| `crm_routes.py` | `/api/crm/leads/<lead_id>` | GET, PUT, DELETE | 0 | Retained; external/dynamic usage unverified |
| `crm_routes.py` | `/api/crm/leads/<lead_id>/stage` | PUT | 0 | Retained; external/dynamic usage unverified |
| `crm_routes.py` | `/api/crm/leads/<lead_id>/convert` | POST | 0 | Retained; external/dynamic usage unverified |
| `crm_routes.py` | `/api/crm/activities` | GET, POST | 2 | Retained; referenced |
| `crm_routes.py` | `/api/crm/activities/<int:activity_id>/toggle` | PUT | 0 | Retained; external/dynamic usage unverified |
| `crm_routes.py` | `/api/crm/quotations` | GET, POST | 1 | Retained; referenced |
| `crm_routes.py` | `/api/crm/quotations/<quote_id>` | GET, PUT, DELETE | 0 | Retained; external/dynamic usage unverified |
| `crm_routes.py` | `/api/crm/quotations/<quote_id>/convert` | POST | 0 | Retained; external/dynamic usage unverified |
| `crm_routes.py` | `/api/crm/communication/log` | POST | 0 | Retained; external/dynamic usage unverified |
| `crm_routes.py` | `/api/crm/reports` | GET | 1 | Retained; referenced |
| `crm_routes.py` | `/api/crm/settings` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `crm_workspace.py` | `/api/crm/workspace/metrics` | GET | 1 | Retained; referenced |
| `crm_workspace.py` | `/api/crm/projects` | GET, POST | 2 | Retained; referenced |
| `crm_workspace.py` | `/api/crm/projects/<project_id>` | PUT | 1 | Retained; referenced |
| `crm_workspace.py` | `/api/crm/workspace/preferences` | GET, POST | 1 | Retained; referenced |
| `crm_workspace.py` | `/api/crm/workspace/export/<module>` | GET | 0 | Retained; external/dynamic usage unverified |
| `erp_routes.py` | `/delivery-challans` | GET | 9 | Retained; referenced |
| `erp_routes.py` | `/delivery-challan/new` | GET, POST | 3 | Retained; referenced |
| `erp_routes.py` | `/delivery-challan/<int:challan_id>` | GET | 5 | Retained; referenced |
| `erp_routes.py` | `/delivery-challan/<int:challan_id>/edit` | GET, POST | 3 | Retained; referenced |
| `erp_routes.py` | `/delivery-challan/<int:challan_id>/pdf` | GET | 1 | Retained; referenced |
| `erp_routes.py` | `/delivery-challan/<int:challan_id>/convert-to-invoice` | GET | 2 | Retained; referenced |
| `erp_routes.py` | `/delivery-challan/<int:challan_id>/delete` | POST | 0 | Retained; external/dynamic usage unverified |
| `erp_routes.py` | `/sales-orders` | GET | 10 | Retained; referenced |
| `erp_routes.py` | `/sales-order/new` | GET, POST | 3 | Retained; referenced |
| `erp_routes.py` | `/sales-order/<int:order_id>` | GET | 8 | Retained; referenced |
| `erp_routes.py` | `/sales-order/<int:order_id>/edit` | GET, POST | 3 | Retained; referenced |
| `erp_routes.py` | `/sales-order/<int:order_id>/convert-to-challan` | GET | 2 | Retained; referenced |
| `erp_routes.py` | `/sales-order/<int:order_id>/convert-to-invoice` | POST | 2 | Retained; referenced |
| `erp_routes.py` | `/sales-order/<int:order_id>/delete` | POST | 0 | Retained; external/dynamic usage unverified |
| `erp_routes.py` | `/purchase-orders` | GET | 8 | Retained; referenced |
| `erp_routes.py` | `/purchase-order/new` | GET, POST | 3 | Retained; referenced |
| `erp_routes.py` | `/purchase-order/<int:po_id>` | GET | 4 | Retained; referenced |
| `erp_routes.py` | `/purchase-order/<int:po_id>/edit` | GET, POST | 3 | Retained; referenced |
| `erp_routes.py` | `/purchase-order/<int:po_id>/delete` | POST | 0 | Retained; external/dynamic usage unverified |
| `erp_routes.py` | `/purchase-order/<int:po_id>/convert-to-bill` | GET | 2 | Retained; referenced |
| `finance_checks.py` | `/finance/accounting-checks` | GET | 4 | Retained; referenced |
| `finance_notes.py` | `/finance/<kind>-notes` | GET | 4 | Retained; referenced |
| `finance_notes.py` | `/finance/<kind>-notes/new` | GET, POST | 3 | Retained; referenced |
| `finance_notes.py` | `/finance/<kind>-notes/<int:note_id>` | GET | 6 | Retained; referenced |
| `finance_notes.py` | `/finance/<kind>-notes/<int:note_id>/void` | POST | 1 | Retained; referenced |
| `finance_periods.py` | `/finance/periods` | GET | 5 | Retained; referenced |
| `finance_periods.py` | `/finance/periods/change` | POST | 1 | Retained; referenced |
| `finance_workspace.py` | `/finance` | GET | 14 | Retained; referenced |
| `finance_workspace.py` | `/finance/records/<kind>` | GET | 5 | Retained; referenced |
| `hr_workspace.py` | `/hr` | GET | 5 | Retained; referenced |
| `hr_workspace.py` | `/hr/employees` | GET | 38 | Retained; referenced |
| `hr_workspace.py` | `/hr/employees/new` | GET, POST | 3 | Retained; referenced |
| `hr_workspace.py` | `/hr/employees/<int:employee_id>` | GET | 5 | Retained; referenced |
| `hr_workspace.py` | `/hr/employees/<int:employee_id>/edit` | GET, POST | 2 | Retained; referenced |
| `hr_workspace.py` | `/hr/departments` | GET, POST | 5 | Retained; referenced |
| `hr_workspace.py` | `/hr/designations` | GET, POST | 5 | Retained; referenced |
| `hr_workspace.py` | `/hr/shifts` | GET, POST | 9 | Retained; referenced |
| `hr_workspace.py` | `/hr/shifts/assign` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/holidays` | GET, POST | 5 | Retained; referenced |
| `hr_workspace.py` | `/hr/attendance` | GET | 15 | Retained; referenced |
| `hr_workspace.py` | `/hr/attendance/save` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/attendance/check-in/<int:employee_id>` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/attendance/check-out/<int:employee_id>` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/leave-types` | GET, POST | 4 | Retained; referenced |
| `hr_workspace.py` | `/hr/leave-balances` | GET, POST | 2 | Retained; referenced |
| `hr_workspace.py` | `/hr/leaves` | GET, POST | 3 | Retained; referenced |
| `hr_workspace.py` | `/hr/leaves/<int:leave_id>/approve` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/leaves/<int:leave_id>/reject` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/overtime` | GET | 7 | Retained; referenced |
| `hr_workspace.py` | `/hr/overtime/<int:ot_id>/decision` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/salary-components` | GET, POST | 4 | Retained; referenced |
| `hr_workspace.py` | `/hr/salary-structures` | GET, POST | 6 | Retained; referenced |
| `hr_workspace.py` | `/hr/salary-structures/<int:structure_id>` | GET, POST | 3 | Retained; referenced |
| `hr_workspace.py` | `/hr/salary-structures/<int:structure_id>/lines/<int:line_id>/delete` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/salary-assignments` | GET, POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/payroll` | GET, POST | 15 | Retained; referenced |
| `hr_workspace.py` | `/hr/payroll/<int:run_id>` | GET | 7 | Retained; referenced |
| `hr_workspace.py` | `/hr/payroll/<int:run_id>/calculate` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/payroll/<int:run_id>/approve` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/payroll/<int:run_id>/lock` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/payroll/<int:run_id>/payslip/<int:entry_id>` | GET | 2 | Retained; referenced |
| `hr_workspace.py` | `/hr/statutory` | GET, POST | 6 | Retained; referenced |
| `hr_workspace.py` | `/hr/statutory/employees` | GET, POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/loans` | GET, POST | 6 | Retained; referenced |
| `hr_workspace.py` | `/hr/loans/<int:loan_id>/status` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/expense-claims` | GET, POST | 3 | Retained; referenced |
| `hr_workspace.py` | `/hr/expense-claims/<int:claim_id>/decision` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/payroll/<int:run_id>/pay` | POST | 2 | Retained; referenced |
| `hr_workspace.py` | `/hr/my` | GET | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/my/attendance` | GET | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/my/leaves` | GET, POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/my/payslips` | GET | 2 | Retained; referenced |
| `hr_workspace.py` | `/hr/my/payslips/<int:entry_id>` | GET | 2 | Retained; referenced |
| `hr_workspace.py` | `/hr/my/claims` | GET, POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/my/loans` | GET | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/my/profile` | GET, POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/manager` | GET | 5 | Retained; referenced |
| `hr_workspace.py` | `/hr/manager/leaves/<int:leave_id>/decision` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/manager/claims/<int:claim_id>/decision` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/manager/overtime/<int:ot_id>/decision` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/recruitment` | GET, POST | 5 | Retained; referenced |
| `hr_workspace.py` | `/hr/recruitment/<int:job_id>` | GET, POST | 3 | Retained; referenced |
| `hr_workspace.py` | `/hr/candidates/<int:candidate_id>/stage` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/candidates/<int:candidate_id>/hire` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/onboarding` | GET, POST | 5 | Retained; referenced |
| `hr_workspace.py` | `/hr/onboarding/<int:task_id>/toggle` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/performance` | GET, POST | 2 | Retained; referenced |
| `hr_workspace.py` | `/hr/assets` | GET, POST | 4 | Retained; referenced |
| `hr_workspace.py` | `/hr/assets/<int:asset_id>/return` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/movements` | GET, POST | 2 | Retained; referenced |
| `hr_workspace.py` | `/hr/exits` | GET, POST | 6 | Retained; referenced |
| `hr_workspace.py` | `/hr/exits/<int:exit_id>/close` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/exits/<int:exit_id>/clearance` | POST | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/reports` | GET | 7 | Retained; referenced |
| `hr_workspace.py` | `/hr/reports/attendance` | GET | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/reports/leave` | GET | 1 | Retained; referenced |
| `hr_workspace.py` | `/hr/reports/payroll` | GET | 2 | Retained; referenced |
| `hr_workspace.py` | `/hr/reports/salary-register` | GET | 2 | Retained; referenced |
| `hr_workspace.py` | `/hr/reports/statutory` | GET | 2 | Retained; referenced |
| `hr_workspace.py` | `/hr/bi` | GET | 3 | Retained; referenced |
| `order_erp_routes.py` | `/order-erp` | GET | 5 | Retained; referenced |
| `order_erp_routes.py` | `/order-erp/dashboard` | GET | 0 | Retained; external/dynamic usage unverified |
| `order_erp_routes.py` | `/api/order-erp/stats` | GET | 2 | Retained; referenced |
| `order_erp_routes.py` | `/api/order-erp/orders` | GET, POST | 1 | Retained; referenced |
| `order_erp_routes.py` | `/api/order-erp/orders/<order_id>` | GET, DELETE | 0 | Retained; external/dynamic usage unverified |
| `order_erp_routes.py` | `/api/order-erp/orders/<order_id>/status` | PUT | 0 | Retained; external/dynamic usage unverified |
| `order_erp_routes.py` | `/api/order-erp/orders/<order_id>/credit-check` | POST | 0 | Retained; external/dynamic usage unverified |
| `order_erp_routes.py` | `/api/order-erp/partners` | GET | 0 | Retained; external/dynamic usage unverified |
| `order_erp_routes.py` | `/api/order-erp/departments` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `order_erp_routes.py` | `/api/order-erp/sales-orders` | GET, POST | 1 | Retained; referenced |
| `order_erp_routes.py` | `/api/order-erp/sales-orders/<int:order_id>` | GET | 0 | Retained; external/dynamic usage unverified |
| `order_erp_routes.py` | `/api/order-erp/sales-orders/<int:order_id>/send-to-production` | POST | 0 | Retained; external/dynamic usage unverified |
| `order_erp_routes.py` | `/api/order-erp/clients` | GET, POST | 1 | Retained; referenced |
| `order_erp_routes.py` | `/api/order-erp/clients/<int:client_id>/details` | GET | 0 | Retained; external/dynamic usage unverified |
| `order_erp_routes.py` | `/api/order-erp/products` | GET | 1 | Retained; referenced |
| `status_timeline.py` | `/track/<company_slug>` | GET, POST | 2 | Retained; referenced |
| `status_timeline.py` | `/t/<company_id>/<docket_no>` | GET | 2 | Retained; referenced |
| `status_timeline.py` | `/track` | GET, POST | 6 | Retained; referenced |
| `workshop_routes.py` | `/workshop` | GET | 7 | Retained; referenced |
| `workshop_routes.py` | `/workshop/dashboard` | GET | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/workshop/v/<string:vehicle_uuid>` | GET | 2 | Retained; referenced |
| `workshop_routes.py` | `/workshop/v/<string:vehicle_uuid>/qr` | GET | 2 | Retained; referenced |
| `workshop_routes.py` | `/api/workshop/stats` | GET | 2 | Retained; referenced |
| `workshop_routes.py` | `/api/workshop/vehicles` | GET, POST | 1 | Retained; referenced |
| `workshop_routes.py` | `/api/workshop/vehicles/<int:vehicle_id>` | GET, PUT | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/api/workshop/vehicles/<int:vehicle_id>/service-plan` | POST | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/api/workshop/digital-job-cards` | GET | 2 | Retained; referenced |
| `workshop_routes.py` | `/api/workshop/job-cards` | GET, POST | 1 | Retained; referenced |
| `workshop_routes.py` | `/api/workshop/job-cards/<int:job_card_id>` | GET, PUT | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/api/workshop/job-cards/<int:job_card_id>/status` | POST | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/api/workshop/checklist-templates` | GET | 1 | Retained; referenced |
| `workshop_routes.py` | `/api/workshop/products` | GET | 1 | Retained; referenced |
| `workshop_routes.py` | `/api/workshop/job-cards/<int:job_card_id>/inspection` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/api/workshop/job-cards/<int:job_card_id>/estimate` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/api/workshop/job-cards/<int:job_card_id>/approve-estimate` | POST | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/api/workshop/job-cards/<int:job_card_id>/add-additional-item` | POST | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/api/workshop/job-cards/<int:job_card_id>/tasks` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/api/workshop/tasks/<int:task_id>/status` | POST | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/api/workshop/job-cards/<int:job_card_id>/parts-issue` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/api/workshop/job-cards/<int:job_card_id>/qc` | GET, POST | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/api/workshop/job-cards/<int:job_card_id>/invoice` | POST | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/api/workshop/job-cards/<int:job_card_id>/deliver` | POST | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/repair-bills` | GET | 13 | Retained; referenced |
| `workshop_routes.py` | `/repair-bills/<int:job_card_id>` | GET | 5 | Retained; referenced |
| `workshop_routes.py` | `/workshop/job-cards/<int:job_card_id>/bill` | GET | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/api/workshop/service-catalog` | GET, POST | 1 | Retained; referenced |
| `workshop_routes.py` | `/api/workshop/service-catalog/<int:svc_id>` | PUT, DELETE | 0 | Retained; external/dynamic usage unverified |
| `workshop_routes.py` | `/api/workshop/reminders` | GET, POST | 1 | Retained; referenced |
| `workshop_routes.py` | `/api/workshop/cost-analytics` | GET | 1 | Retained; referenced |
| `bi/predictive_routes.py` | `/bi-predictive` | GET | 5 | Retained; referenced |
| `bi/predictive_routes.py` | `/api/bi/v1/predictive` | GET | 1 | Retained; referenced |
| `bi/routes.py` | `/api/bi/v1/health` | GET | 0 | Retained; external/dynamic usage unverified |
| `bi/routes.py` | `/api/bi/v1/catalog` | GET | 0 | Retained; external/dynamic usage unverified |
| `bi/routes.py` | `/api/bi/v1/filter-options` | GET | 1 | Retained; referenced |
| `bi/routes.py` | `/api/bi/v1/overview` | GET | 0 | Retained; external/dynamic usage unverified |
| `bi/routes.py` | `/api/bi/v1/executive` | GET | 1 | Retained; referenced |
| `bi/routes.py` | `/bi-departments` | GET | 4 | Retained; referenced |
| `bi/routes.py` | `/api/bi/v1/departments/<section>` | GET | 0 | Retained; external/dynamic usage unverified |
| `bi/routes.py` | `/bi-explore` | GET | 4 | Retained; referenced |
| `bi/routes.py` | `/api/bi/v1/explore` | GET | 1 | Retained; referenced |
| `bi/routes.py` | `/api/bi/v1/explore/export/<format>` | GET | 0 | Retained; external/dynamic usage unverified |
| `bi/routes.py` | `/bi-builder` | GET | 10 | Retained; referenced |
| `bi/routes.py` | `/api/bi/v1/builder/catalog` | GET | 0 | Retained; external/dynamic usage unverified |
| `bi/routes.py` | `/api/bi/v1/builder/visual` | GET | 1 | Retained; referenced |
| `bi/routes.py` | `/api/bi/v1/builder/visual/drill` | GET | 1 | Retained; referenced |
| `bi/routes.py` | `/api/bi/v1/builder/data` | GET | 1 | Retained; referenced |
| `bi/routes.py` | `/api/bi/v1/builder/drill` | GET | 1 | Retained; referenced |
| `bi/routes.py` | `/api/bi/v1/builder/dashboards` | GET, POST | 1 | Retained; referenced |
| `bi/routes.py` | `/api/bi/v1/builder/dashboards/<int:dashboard_id>` | GET, PUT, DELETE | 0 | Retained; external/dynamic usage unverified |
| `bi/warehouse_routes.py` | `/bi-warehouse` | GET | 4 | Retained; referenced |
| `bi/warehouse_routes.py` | `/api/bi/v1/warehouse/status` | GET | 1 | Retained; referenced |
| `bi/warehouse_routes.py` | `/api/bi/v1/warehouse/summary` | GET | 1 | Retained; referenced |
| `bi/warehouse_routes.py` | `/api/bi/v1/warehouse/refresh` | POST | 1 | Retained; referenced |
| `db folder/migration_routes.py` | `/migrations` | GET | 23 | Retained; referenced |
| `db folder/migration_routes.py` | `/migrations/run` | POST | 3 | Retained; referenced |
| `db folder/migration_routes.py` | `/migrations/history` | GET | 2 | Retained; referenced |
| `db folder/migration_routes.py` | `/migrations/history/<company_id>` | GET | 2 | Retained; referenced |

## Verification and deployment

Route tests register extracted decorators in an isolated Flask app, verify canonical URL generation, old/new path matching and method/form preservation, and compare access decorators with the original inventory. They do not exercise live logistics databases or carrier services. Existing regression tests cover the shared finance workflows. Restart the application to load the new routing. Rollback copies of changed source files are retained under backups/route_cleanup_20261003.

Compatibility aliases increase the number of registered URL rules temporarily; they do not duplicate handlers or data. Remove aliases only after checking real traffic and updating external integrations.

# ERP logistics removal — 2026-10-03

This replaces the previous alias migration. Qiyadah ERP no longer exposes the removed logistics routes, under either the original URLs or the logistics aliases.

## Removed

- 103 URL rules across 55 handlers: booking, manifests, courier price lists, shipping rates, AWB/docket lookups, public shipment tracking, logistics repairs, and shipment-tracking API key management.
- 18 exclusively logistics HTML templates; three unused Python files: tasks.py, seed_carrier_config.py, status_timeline.py.
- Shipping quote intent and renderer, booking repair button in Purchases, logistics shortcuts, tracking/manifest settings and logistics print controls.
- Manifest and courier price-list permission choices; unsupported logistics plan claims.

The exact route and file inventory is in erp-logistics-removal.json. Recovery copies are in backups/erp_logistics_removal_20261003. These are inactive backups, not registered application routes.

## Preserved dependencies

Sales and purchase invoices, receipts, payments, ledger, and finance checks remain. Historical Invoice/source-booking records, shared models, source references, statement calculations, and migration compatibility remain where financial workflows depend on them. No database records or tables were deleted. Unrelated ERP routes and templates were not deleted merely because static analysis could not prove usage; dynamic rendering and external callers make that unsafe.

## Validation

120 unit tests passed, including route-removal, retained financial-route, template-link, Jinja parsing, and AI shipping-intent checks. Python compilation succeeded. A static scan found no calls to the removed functions in the main application or utility modules. app.py now declares 218 URL rules; additional ERP modules register their own routes.

The application was not started against live databases because startup performs schema maintenance. Browser and live deployment validation remain unperformed.

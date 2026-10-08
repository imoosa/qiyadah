# Qiyadah pre-change source and schema inventory

Generated from local source without importing app.py or opening a writable database. No customer row values are included.

## admin_access.py

- L69 `admin_access_catalog`: `app.route('/api/admin/access/catalog'); admin_api`. Referenced names: Company, MODULES, RegisteredUser, SubscriptionPlan
- L88 `admin_access_detail`: `app.route('/api/admin/access/<scope>/<path:target>', methods=['GET', 'PUT']); admin_api`. Referenced names: Company, CompanyUser, Exception, IntegrityError, MODULES, PlatformAccessAudit, PlatformAccessRule
- L159 `admin_access_open_company`: `app.route('/api/admin/access/open-company/<company_id>', methods=['POST']); admin_api`. Referenced names: Company

## api_key_settings_page.py

- L73 `manage_api_keys`: `app.route('/settings/api-keys', methods=['GET', 'POST']); login_required`. Referenced names: API_KEY_PAGE_TEMPLATE, CompanyApiKey
- L92 `revoke_api_key`: `app.route('/settings/api-keys/<int:key_id>/revoke', methods=['POST']); login_required`. Referenced names: CompanyApiKey

## app.py

### PeriodType (L73)
- `DAILY = 'daily'`
- `WEEKLY = 'weekly'`
- `MONTHLY = 'monthly'`
- `QUARTERLY = 'quarterly'`
- `YEARLY = 'yearly'`
- `CUSTOM = 'custom'`
- L751 `dismiss_expiry_popup`: `app.route('/api/dismiss-expiry-popup', methods=['POST'])`. Referenced names: 
- L759 `api_currency_list`: `app.route('/api/currency/list', methods=['GET'])`. Referenced names: 
- L768 `api_currency_exchange_rate`: `app.route('/api/currency/exchange-rate', methods=['GET'])`. Referenced names: Company
- L1072 `no_access`: `app.route('/no-access'); login_required`. Referenced names: 
### DashboardFilters (L1839)
- `company_id: str`
- `from_date: Optional[date] = None`
- `to_date: Optional[date] = None`
- `period_type: PeriodType = PeriodType.MONTHLY`
- `employee_id: Optional[str] = None`
- `country: Optional[str] = None`
- `client_id: Optional[int] = None`
- `supplier_id: Optional[int] = None`
- `category: Optional[str] = None`
- `compare_from: Optional[date] = None`
- `compare_to: Optional[date] = None`
- L3869 `index`: `app.route('/')`. Referenced names: 
- L3876 `api_ai_chat`: `app.route('/api/ai-chat', methods=['POST']); login_required`. Referenced names: 
- L3905 `api_ai_chat_clear`: `app.route('/api/ai-chat/clear', methods=['POST']); login_required`. Referenced names: 
- L3911 `health_check`: `app.route('/health')`. Referenced names: Exception
- L3929 `service_worker`: `app.route('/sw.js')`. Referenced names: 
- L3939 `login`: `app.route('/login', methods=['GET', 'POST'])`. Referenced names: Company, CompanyUser, Exception, RegisteredUser
- L4003 `update_company_terms`: `app.route('/company/update-terms', methods=['POST']); login_required; owner_required`. Referenced names: 
- L4022 `verify_otp`: `app.route('/verify-otp', methods=['GET', 'POST'])`. Referenced names: RegisteredUser
- L4056 `resend_otp`: `app.route('/verify-otp/resend')`. Referenced names: 
- L4065 `force_change_password`: `app.route('/force-change-password', methods=['GET', 'POST'])`. Referenced names: RegisteredUser
- L4097 `account_setup`: `app.route('/account-setup', methods=['GET', 'POST'])`. Referenced names: 
- L4102 `resend_account_setup_otp`: `app.route('/account-setup/resend')`. Referenced names: 
- L4108 `add_new_company`: `app.route('/company/add', methods=['GET', 'POST']); login_required; owner_required`. Referenced names: Company, CompanyUser, RegisteredUser, SubscriptionPlan
- L4237 `select_company`: `app.route('/select-company', methods=['GET', 'POST'])`. Referenced names: CompanyUser, RegisteredUser
- L4309 `toggle_company_mobile_visibility`: `app.route('/company/toggle-mobile-visibility/<company_id>', methods=['POST'])`. Referenced names: Company
- L4346 `switch_company`: `app.route('/switch-company/<company_id>'); login_required`. Referenced names: CompanyUser
- L4376 `onboard_company`: `app.route('/onboarding/create-company', methods=['GET', 'POST']); login_required`. Referenced names: Company, CompanyUser, Exception, RegisteredUser, SubscriptionPlan
- L4494 `create_payment_order`: `app.route('/api/payment/create-order', methods=['POST'])`. Referenced names: Company, Exception, PLAN_PRICING, PaymentTransaction, RAZORPAY_KEY_ID, RegisteredUser
- L4579 `verify_payment`: `app.route('/api/payment/verify', methods=['POST'])`. Referenced names: Company, Exception, PaymentTransaction, RAZORPAY_KEY_SECRET, RegisteredUser, SubscriptionPlan
- L4726 `register`: `app.route('/register', methods=['GET', 'POST'])`. Referenced names: Company, CompanyUser, Exception, RegisteredUser, SubscriptionPlan, TypeError, ValueError
- L4979 `logout`: `app.route('/logout')`. Referenced names: 
- L5060 `export_selector`: `app.route('/reports/export-selector'); login_required; require_permission('analytics', 'view')`. Referenced names: 
- L5092 `export_reports_excel`: `app.route('/reports/export-excel'); login_required; require_permission('analytics', 'view')`. Referenced names: Client, Font, Invoice, PatternFill, PurchaseInvoice, Supplier, ValueError
- L5421 `reports_dashboard`: `app.route('/reports-dashboard'); login_required; require_permission('analytics', 'view')`. Referenced names: BankAccount, BankTransaction, CashTransaction, Client, Invoice, PurchaseInvoice
- L5666 `dashboard`: `app.route('/dashboard'); login_required; require_permission('dashboard', 'view')`. Referenced names: 
- L5675 `api_dashboard_data`: `app.route('/api/dashboard-data'); login_required; require_permission('dashboard', 'view')`. Referenced names: BankAccount, CashTransaction, Client, Expense, Invoice, PurchaseInvoice, StockItem
- L5897 `bi_dashboard`: `app.route('/bi-dashboard'); login_required; require_permission('analytics', 'view')`. Referenced names: Client, CompanyUser, Expense, Invoice
- L5957 `api_bi_dashboard`: `app.route('/api/bi/dashboard'); login_required; require_permission('analytics', 'view')`. Referenced names: 
- L6061 `api_bi_company_analysis`: `app.route('/api/bi/company-analysis'); login_required; require_permission('analytics', 'view')`. Referenced names: Exception
- L6082 `price_lists`: `app.route('/price-lists'); login_required; require_permission('pricelist', 'view')`. Referenced names: PriceList
- L6092 `view_price_list`: `app.route('/price-lists/view/<int:price_list_id>'); login_required; require_permission('pricelist', 'view')`. Referenced names: PriceList
- L6114 `debug_price_lists_data`: `app.route('/debug/price-lists-data'); login_required`. Referenced names: Exception, PriceList
- L6152 `delete_price_list`: `app.route('/price-lists/delete/<int:price_list_id>', methods=['POST']); login_required; owner_required; require_admin_password`. Referenced names: Exception, PriceList
- L6186 `debug_price_list`: `app.route('/debug/price-list/<int:price_list_id>'); login_required; owner_required`. Referenced names: PriceList
- L6211 `debug_excel_columns`: `app.route('/debug/excel-columns', methods=['POST']); login_required`. Referenced names: Exception
- L6233 `upload_price_list`: `app.route('/price-lists/upload', methods=['GET', 'POST']); login_required; require_permission('pricelist', 'view', method_actions={'POST': 'create'})`. Referenced names: Exception, PriceList
- L6333 `api_rate_lookup`: `app.route('/api/rate-lookup'); login_required; require_permission('pricelist', 'view')`. Referenced names: Exception, RateLookup
- L6588 `rate_calculator`: `app.route('/rate-calculator'); login_required; require_permission('pricelist', 'view')`. Referenced names: Exception, PriceList
- L6611 `api_rate_calculator`: `app.route('/api/rate-calculator', methods=['GET', 'POST']); login_required; require_permission('pricelist', 'view')`. Referenced names: Exception, PriceList, TypeError, ValueError
- L6743 `api_rate_calculator_destinations`: `app.route('/api/rate-calculator/destinations', methods=['GET']); login_required; require_permission('pricelist', 'view')`. Referenced names: Exception, PriceList
- L7135 `repair_manifest_shippers`: `app.route('/admin/repair-manifest-shippers'); login_required`. Referenced names: 
- L7189 `repair_purchase_item_descriptions`: `app.route('/admin/repair-purchase-item-descriptions'); login_required`. Referenced names: 
- L7520 `save_field_permissions`: `app.route('/company/permissions/fields/<role>', methods=['POST']); login_required; owner_required`. Referenced names: CompanyRolePermission, HARD_LOCKED_EDIT, INVOICE_FIELDS, ValueError
- L7567 `save_user_field_permissions`: `app.route('/company/permissions/fields/user/<user_id>', methods=['POST']); login_required; owner_required`. Referenced names: CompanyUser, HARD_LOCKED_EDIT, INVOICE_FIELDS, ValueError
- L7609 `inventory_clear_party_stock`: `app.route('/inventory/clear_party_stock', methods=['POST']); login_required; owner_required`. Referenced names: Exception, Invoice, StockItem, StockPurchaseHistory
- L7705 `api_purchase_rate_lookup`: `app.route('/api/purchase-rate-lookup'); login_required; require_permission('pricelist', 'view')`. Referenced names: Exception
- L7784 `api_price_lists_list`: `app.route('/api/price-lists/list'); login_required; require_permission('pricelist', 'view')`. Referenced names: PriceList
- L7949 `client_check_similar`: `app.route('/clients/check_similar'); login_required`. Referenced names: 
- L7960 `client_list`: `app.route('/clients'); login_required; require_permission('clients', 'view')`. Referenced names: Client, Invoice
- L8007 `client_remove`: `app.route('/clients/<int:client_pk>/remove', methods=['POST']); login_required; owner_required; require_admin_password`. Referenced names: Client
- L8027 `client_restore`: `app.route('/clients/<int:client_pk>/restore', methods=['POST']); login_required; owner_required`. Referenced names: Client
- L8051 `client_new`: `app.route('/clients/new', methods=['GET', 'POST']); login_required; require_permission('clients', 'view', method_actions={'POST': 'create'})`. Referenced names: Client, Company
- L8141 `client_add`: `app.route('/clients/add', methods=['GET', 'POST']); login_required; require_permission('clients', 'create')`. Referenced names: 
- L8149 `client_view`: `app.route('/clients/<int:client_pk>'); login_required; require_permission('clients', 'view')`. Referenced names: Client, Invoice
- L8308 `client_statement`: `app.route('/clients/<int:client_pk>/statement'); login_required; require_permission('clients', 'view')`. Referenced names: Client, StatementClosing
- L8341 `client_statement_archive`: `app.route('/clients/<int:client_pk>/statement/archive/<int:archive_id>'); login_required; require_permission('clients', 'view')`. Referenced names: Client, StatementClosing
- L8369 `client_edit`: `app.route('/clients/<int:client_pk>/edit', methods=['GET', 'POST']); login_required; require_permission('clients', 'view', method_actions={'POST': 'edit'})`. Referenced names: Client
- L8511 `client_delete`: `app.route('/clients/<int:client_pk>/delete', methods=['GET', 'POST']); login_required; owner_required; require_admin_password`. Referenced names: Client
- L8540 `client_shift_to_opening`: `app.route('/clients/<int:client_pk>/shift-to-opening', methods=['GET', 'POST']); login_required; owner_required; require_admin_password`. Referenced names: Client, ValueError
- L8567 `inventory_list`: `app.route('/inventory'); login_required; require_permission('stock', 'view')`. Referenced names: StockItem
- L8615 `inventory_add`: `app.route('/inventory/new', methods=['GET', 'POST']); app.route('/inventory/add', methods=['GET', 'POST']); login_required; require_permission('stock', 'create')`. Referenced names: StockItem, StockPurchaseHistory, ValueError
- L8702 `inventory_edit`: `app.route('/inventory/edit/<int:item_pk>', methods=['GET', 'POST']); login_required; require_permission('stock', 'edit')`. Referenced names: StockItem, StockPurchaseHistory, ValueError
- L8774 `stock_inward_direct`: `app.route('/stock/inward', methods=['POST']); login_required; require_permission('stock', 'create')`. Referenced names: StockItem, StockPurchaseHistory, ValueError
- L8836 `stock_adjust`: `app.route('/stock/adjust', methods=['POST']); login_required; require_permission('stock', 'edit')`. Referenced names: StockItem, StockPurchaseHistory
- L8880 `stock_movements`: `app.route('/stock/movements/<item_identifier>'); login_required; require_permission('stock', 'view')`. Referenced names: PurchaseInvoice, StockItem, StockPurchaseHistory
- L8957 `inventory_delete`: `app.route('/inventory/delete/<int:item_pk>', methods=['POST']); login_required; require_permission('stock', 'delete')`. Referenced names: StockItem
- L8974 `api_stock_items`: `app.route('/api/stock/items'); login_required; require_permission('stock', 'view')`. Referenced names: StockItem
- L8998 `stock_item_get`: `app.route('/stock/item/<code>'); login_required; require_permission('stock', 'view')`. Referenced names: StockItem
- L9024 `purchase_invoice_list`: `app.route('/purchase/list'); login_required; require_permission('purchase', 'view')`. Referenced names: Company, PurchaseInvoice, StockItem, Supplier
- L9055 `purchase_generate_from_booking`: `app.route('/purchase/generate-from-booking', methods=['POST']); login_required; require_permission('purchase', 'view', method_actions={'POST': 'create'})`. Referenced names: Company, CompanyManifest, Exception, Invoice, ManifestEntry, PurchaseInvoiceItem
- L9181 `purchase_invoice_delete`: `app.route('/purchase/delete/<invoice_id>', methods=['POST']); login_required; owner_required; require_admin_password`. Referenced names: PurchaseInvoice, StockItem, Supplier
- L9224 `api_purchase_scan_bill`: `app.route('/api/purchase/scan-bill', methods=['POST']); login_required; require_permission('purchase', 'view')`. Referenced names: Company, Exception, StockItem, Supplier, ValueError
- L9363 `serve_purchase_invoice_file`: `app.route('/uploads/purchase_invoices/<path:filename>'); app.route('/purchase/file/<path:filename>'); login_required`. Referenced names: 
- L9379 `purchase_invoice_new`: `app.route('/purchase/new', methods=['GET', 'POST']); login_required; require_permission('purchase', 'view', method_actions={'POST': 'create'})`. Referenced names: Company, PurchaseInvoice, PurchaseInvoiceItem, PurchaseOrder, StockItem, StockPurchaseHistory, Supplier, TypeError, ValueError
- L9757 `purchase_invoice_edit`: `app.route('/purchase/edit/<invoice_id>', methods=['GET', 'POST']); login_required; require_permission('purchase', 'view', method_actions={'POST': 'edit'})`. Referenced names: Company, PurchaseInvoice, PurchaseInvoiceItem, StockItem, Supplier, TypeError, ValueError
- L10001 `purchase_invoice_view`: `app.route('/purchase/view/<invoice_id>'); login_required; require_permission('purchase', 'view')`. Referenced names: BankAccount, Company, Exception, PurchaseInvoice
- L10027 `purchase_make_payment`: `app.route('/purchase/pay/<int:pk>', methods=['POST']); login_required; require_permission('purchase', 'edit')`. Referenced names: BankAccount, BankTransaction, CashTransaction, PurchaseInvoice, PurchasePayment
- L10140 `invoice_list`: `app.route('/booking/list'); login_required; require_permission('invoices', 'view')`. Referenced names: Estimate, Invoice, TypeError, ValueError
- L10362 `invoice_list_update_tracking`: `app.route('/booking/list/update-tracking/<invoice_id>', methods=['POST']); login_required; require_permission('invoices', 'edit')`. Referenced names: Exception, Invoice, PurchaseInvoiceItem, TypeError, ValueError
- L10443 `invoice_list_update_tracking_status`: `app.route('/booking/list/update-tracking-status/<invoice_id>', methods=['POST']); login_required; require_permission('invoices', 'edit')`. Referenced names: Exception, Invoice, TRACKING_STATUS_STAGES, TypeError, ValueError
- L10495 `invoice_list_record_payment`: `app.route('/booking/list/record-payment/<invoice_id>', methods=['POST']); login_required; require_permission('invoices', 'edit')`. Referenced names: Invoice, TypeError, ValueError
- L10602 `invoice_hard_delete`: `app.route('/booking/hard-delete/<invoice_id>', methods=['POST']); login_required; owner_required; require_admin_password`. Referenced names: Cheque, Client, CompanyManifest, DeletedInvoiceLog, Estimate, EstimateItem, Exception, Invoice, InvoiceItem, ManifestEntry, PurchaseInvoice, PurchaseInvoiceItem, StockItem, StockPurchaseHistory, Supplier
- L10778 `invoice_deleted_log`: `app.route('/booking/deleted-log'); login_required; owner_required`. Referenced names: DeletedInvoiceLog
- L10788 `invoice_new`: `app.route('/booking/new', methods=['GET', 'POST']); login_required; require_permission('invoices', 'view', method_actions={'POST': 'create'})`. Referenced names: Client, Estimate, Exception, Invoice, PriceList, Supplier, TypeError, ValueError
- L11228 `invoice_edit`: `app.route('/booking/edit/<invoice_id>', methods=['GET', 'POST']); login_required; require_permission('invoices', 'view', method_actions={'POST': 'edit'})`. Referenced names: Client, Exception, Invoice, InvoiceItem, PriceList
- L11508 `invoice_customer_update`: `app.route('/booking/customer/update', methods=['POST']); login_required; require_permission('invoices', 'edit')`. Referenced names: BankTransaction, CashTransaction, Client, Company, CompanyManifest, Estimate, EstimateItem, Exception, Invoice, ManifestEntry, PriceList, PurchaseInvoice, PurchaseInvoiceItem, StockItem, StockPurchaseHistory, Supplier
- L12743 `invoice_view`: `app.route('/booking/view/<invoice_id>'); login_required; require_permission('invoices', 'view')`. Referenced names: Estimate, Exception, Invoice, TypeError, ValueError
- L13032 `reset_user_password`: `app.route('/company/reset-user-password/<email>', methods=['POST']); login_required; owner_required`. Referenced names: CompanyUser
- L13068 `invoice_pdf`: `app.route('/booking/pdf/<invoice_id>')`. Referenced names: Company, Estimate, Exception, Invoice, TypeError, ValueError
- L13219 `invoice_resale_charges`: `app.route('/booking/<invoice_id>/resale-charges', methods=['GET', 'POST']); login_required; require_permission('invoices', 'view', method_actions={'POST': 'edit'})`. Referenced names: CashTransaction, Client, Company, Exception, Invoice
- L13595 `invoice_customer_check_credit_limit`: `app.route('/booking/customer/check-credit-limit', methods=['POST']); login_required`. Referenced names: Client, Company, Invoice, TypeError, ValueError
- L13810 `customer_invoice_list`: `app.route('/customer-invoices'); login_required; require_permission('invoices', 'view')`. Referenced names: CustomerInvoice
- L13853 `customer_invoice_new`: `app.route('/customer-invoices/new'); login_required; require_permission('customer_invoices', 'create')`. Referenced names: Client, Company, CustomerInvoice, StockItem
- L13889 `customer_invoice_create`: `app.route('/customer-invoices/create', methods=['POST']); login_required; require_permission('customer_invoices', 'create')`. Referenced names: Company, CustomerInvoice, CustomerInvoiceItem, StockItem, StockPurchaseHistory, TypeError, ValueError
- L14099 `customer_invoice_edit`: `app.route('/customer-invoices/edit/<int:cust_inv_id>', methods=['GET', 'POST']); login_required; require_permission('customer_invoices', 'edit')`. Referenced names: Client, Company, CustomerInvoiceItem, StockItem, TypeError, ValueError
- L14276 `customer_invoice_view`: `app.route('/customer-invoices/view/<int:cust_inv_id>'); login_required; require_permission('invoices', 'view')`. Referenced names: Client, Company, CustomerInvoiceItem
- L14307 `customer_invoice_delete`: `app.route('/customer-invoices/delete/<int:cust_inv_id>', methods=['POST']); login_required; require_permission('invoices', 'delete'); require_admin_password`. Referenced names: 
- L14327 `customer_invoice_print`: `app.route('/customer-invoices/print/<int:cust_inv_id>'); login_required; require_permission('invoices', 'view')`. Referenced names: Client, Company, CustomerInvoiceItem
- L14403 `fix_duplicate_awbs`: `app.route('/admin/fix-duplicate-awbs', methods=['GET', 'POST']); login_required; require_permission('invoices', 'edit')`. Referenced names: Invoice, PlatformCompany, TypeError, ValueError
- L14488 `invoice_void`: `app.route('/booking/void/<invoice_id>', methods=['POST']); login_required; require_permission('invoices', 'delete')`. Referenced names: BankTransaction, CashTransaction, Client, CompanyManifest, Exception, Invoice, InvoiceItem, ManifestEntry, PurchaseInvoice, PurchaseInvoiceItem, StockItem, StockPurchaseHistory, Supplier
- L14752 `invoice_clone`: `app.route('/booking/clone/<invoice_id>'); login_required; require_permission('invoices', 'create')`. Referenced names: Client, Estimate, Exception, Invoice, PriceList, Supplier, TypeError, ValueError
- L14922 `company_clear_data`: `app.route('/company/clear-data', methods=['POST']); login_required; owner_required`. Referenced names: ALL_CATEGORIES, BankAccount, BankTransaction, CashTransaction, Cheque, Client, CompanyManifest, Estimate, EstimateItem, Exception, Expense, Invoice, InvoiceItem, Loan, LoanRepayment, ManifestEntry, PriceList, PurchaseInvoice, PurchaseInvoiceItem, PurchasePayment, RateLookup, RegisteredUser, StockItem, StockPurchaseHistory, Supplier, SupplierBrand, WhatsAppLog
- L15056 `invoice_customer_new`: `app.route('/booking/customer'); login_required; require_permission('invoices', 'view')`. Referenced names: Client, Invoice, PriceList, StockItem, Supplier
- L15100 `invoice_customer_save`: `app.route('/booking/customer/save', methods=['POST']); login_required; require_permission('invoices', 'create')`. Referenced names: Client, Company, Estimate, EstimateItem, Exception, IntegrityError, Invoice, InvoiceItem, StockItem, StockPurchaseHistory
- L15801 `api_suppliers_list`: `app.route('/api/suppliers/list'); login_required; require_permission('suppliers', 'view')`. Referenced names: Supplier
- L15868 `supplier_list`: `app.route('/suppliers'); login_required; require_permission('suppliers', 'view')`. Referenced names: Supplier
- L15901 `supplier_new`: `app.route('/suppliers/new', methods=['GET', 'POST']); login_required; require_permission('suppliers', 'view', method_actions={'POST': 'create'})`. Referenced names: Company, Supplier, SupplierBrand
- L15968 `debug_suppliers`: `app.route('/debug/suppliers'); login_required`. Referenced names: Supplier
- L15977 `supplier_view`: `app.route('/suppliers/<int:supplier_pk>'); login_required; require_permission('suppliers', 'view')`. Referenced names: PurchaseInvoice, Supplier
- L16135 `supplier_statement`: `app.route('/suppliers/<int:supplier_pk>/statement'); login_required; require_permission('suppliers', 'view')`. Referenced names: StatementClosing, Supplier
- L16168 `supplier_statement_archive`: `app.route('/suppliers/<int:supplier_pk>/statement/archive/<int:archive_id>'); login_required; require_permission('suppliers', 'view')`. Referenced names: StatementClosing, Supplier
- L16194 `supplier_edit`: `app.route('/suppliers/<int:supplier_pk>/edit', methods=['GET', 'POST']); login_required; require_permission('suppliers', 'view', method_actions={'POST': 'edit'})`. Referenced names: Supplier, SupplierBrand
- L16274 `supplier_delete`: `app.route('/suppliers/<int:supplier_pk>/delete', methods=['GET', 'POST']); login_required; owner_required; require_admin_password`. Referenced names: Supplier
- L16301 `supplier_shift_to_opening`: `app.route('/suppliers/<int:supplier_pk>/shift-to-opening', methods=['GET', 'POST']); login_required; owner_required; require_admin_password`. Referenced names: Supplier, ValueError
- L16322 `api_supplier_brands`: `app.route('/api/supplier/<int:supplier_pk>/brands'); login_required; require_permission('suppliers', 'view')`. Referenced names: Supplier
- L16338 `api_customers_list`: `app.route('/api/customers/list'); login_required; require_permission('clients', 'view')`. Referenced names: Client
- L16360 `api_stock_items_by_client`: `app.route('/api/stock/items/by-client/<int:client_id>'); login_required; require_permission('stock', 'view')`. Referenced names: Invoice, InvoiceItem, StockItem
- L16450 `api_docket_info`: `app.route('/api/docket-info/<docket_no>'); login_required; require_permission('manifest', 'view')`. Referenced names: Invoice, TypeError, ValueError
- L16526 `api_purchase_awb_list`: `app.route('/api/purchase/awb-list'); login_required; require_permission('purchase', 'view')`. Referenced names: Invoice, TypeError, ValueError
- L16555 `api_purchase_awb_info`: `app.route('/api/purchase/awb-info/<docket_no>'); login_required; require_permission('purchase', 'view')`. Referenced names: Invoice, PurchaseInvoiceItem, StockItem, TypeError, ValueError
- L16683 `estimate_new`: `app.route('/estimate/new', methods=['GET', 'POST']); login_required; require_permission('estimates', 'view', method_actions={'POST': 'create'})`. Referenced names: Client, Company, Estimate, EstimateItem, Exception, ValueError
- L16891 `estimate_list`: `app.route('/estimate/list'); login_required; require_permission('estimates', 'view')`. Referenced names: Estimate
- L16905 `estimate_view`: `app.route('/estimate/view/<estimate_id>'); login_required; require_permission('estimates', 'view')`. Referenced names: Company, Estimate, Exception
- L16925 `estimate_edit`: `app.route('/estimate/edit/<estimate_id>', methods=['GET', 'POST']); login_required; require_permission('estimates', 'edit')`. Referenced names: 
- L16935 `estimate_update`: `app.route('/estimate/update', methods=['POST']); login_required; require_permission('estimates', 'edit')`. Referenced names: 
- L16943 `estimate_convert_to_so`: `app.route('/estimate/convert_to_so/<estimate_id>', methods=['POST']); login_required; require_permission('estimates', 'create')`. Referenced names: Estimate, Exception, SalesOrder, SalesOrderItem
- L17012 `estimate_convert_to_invoice`: `app.route('/estimate/convert_to_invoice/<estimate_id>', methods=['POST']); login_required; require_permission('estimates', 'create')`. Referenced names: CustomerInvoice, CustomerInvoiceItem, Estimate, Exception
- L17087 `estimate_convert_to_booking`: `app.route('/estimate/convert/<estimate_id>', methods=['POST']); login_required; require_permission('estimates', 'create')`. Referenced names: 
- L17095 `estimate_delete`: `app.route('/estimate/delete/<estimate_id>', methods=['POST']); login_required; owner_required`. Referenced names: Estimate, EstimateItem, Exception
- L17119 `manifest_list`: `app.route('/manifest/list'); login_required; require_permission('manifest', 'view')`. Referenced names: Client, CompanyManifest, ManifestEntry, Supplier, ValueError
- L17280 `manifest_create`: `app.route('/manifest/create'); login_required; require_permission('manifest', 'view')`. Referenced names: Client, CompanyManifest, StockItem
- L17307 `shipper_last_dockets`: `app.route('/manifest/shipper-dockets/<int:client_id>'); login_required; require_permission('manifest', 'view')`. Referenced names: CompanyManifest, Exception, Invoice, ManifestEntry, StockItem
- L17427 `invoice_packages`: `app.route('/manifest/invoice-packages/<int:client_id>/<docket_no>'); login_required; require_permission('manifest', 'view')`. Referenced names: Exception, Invoice
- L17468 `expenses`: `app.route('/expenses'); login_required; require_permission('expenses', 'view')`. Referenced names: EXPENSE_CATEGORIES, Expense, ValueError
- L17518 `add_expense`: `app.route('/expenses/add', methods=['GET', 'POST']); login_required; require_permission('expenses', 'view', method_actions={'POST': 'create'})`. Referenced names: BankAccount, BankTransaction, CashTransaction, Exception, Expense
- L17741 `edit_expense`: `app.route('/expenses/edit/<int:expense_id>', methods=['POST']); login_required; require_permission('expenses', 'view', method_actions={'POST': 'edit'})`. Referenced names: BankAccount, BankTransaction, CashTransaction, Exception, Expense
- L17865 `delete_expense`: `app.route('/expenses/delete/<int:expense_id>', methods=['POST']); login_required; owner_required; require_admin_password`. Referenced names: BankTransaction, CashTransaction, Exception, Expense
- L17984 `api_expenses_summary`: `app.route('/api/expenses-summary'); login_required; require_permission('expenses', 'view')`. Referenced names: Expense, ValueError
- L18021 `manifest_save`: `app.route('/manifest/save', methods=['POST']); login_required; require_permission('manifest', 'create')`. Referenced names: Client, CompanyManifest, Exception, ManifestEntry, StockItem, TypeError, ValueError
- L18136 `manifest_view`: `app.route('/manifest/view/<int:manifest_db_id>'); login_required; require_permission('manifest', 'view')`. Referenced names: CompanyManifest
- L18156 `manifest_print`: `app.route('/manifest/print/<int:manifest_db_id>'); login_required; require_permission('manifest', 'view')`. Referenced names: Company, CompanyManifest, Supplier
- L18217 `manifest_print_day`: `app.route('/manifest/print/day/<date_str>'); login_required; require_permission('manifest', 'view')`. Referenced names: Company, CompanyManifest, ManifestEntry, Supplier, ValueError
- L18386 `manifest_print_selected`: `app.route('/manifest/print/selected'); login_required; require_permission('manifest', 'view')`. Referenced names: Company, CompanyManifest, Supplier, ValueError
- L18517 `manifest_generate_company`: `app.route('/manifest/generate/company', methods=['POST']); login_required; require_permission('manifest', 'edit')`. Referenced names: CompanyManifest, ManifestEntry, StockItem, StockPurchaseHistory, Supplier, ValueError
- L18697 `manifest_revert_to_pending`: `app.route('/manifest/revert-to-pending', methods=['POST']); login_required; require_permission('manifest', 'edit')`. Referenced names: CompanyManifest, Invoice, ManifestEntry, StockItem, StockPurchaseHistory, ValueError
- L18896 `manifest_print_company`: `app.route('/manifest/print/company/<company_name>'); login_required; require_permission('manifest', 'view')`. Referenced names: Company, CompanyManifest, ManifestEntry, Supplier, SupplierBrand, ValueError
- L19017 `manifest_edit`: `app.route('/manifest/edit/<int:manifest_db_id>'); login_required; require_permission('manifest', 'edit')`. Referenced names: Client, CompanyManifest, StockItem
- L19053 `manifest_update`: `app.route('/manifest/update/<int:manifest_db_id>', methods=['POST']); login_required; require_permission('manifest', 'edit')`. Referenced names: CompanyManifest, ManifestEntry, TypeError, ValueError
- L19132 `manifest_delete`: `app.route('/manifest/delete/<int:manifest_db_id>', methods=['GET', 'POST']); login_required; owner_required; require_admin_password`. Referenced names: CompanyManifest
- L19159 `migrations`: `app.route('/migrations'); login_required; super_admin_required`. Referenced names: Company, Exception
- L19218 `run_migration`: `app.route('/migrations/run', methods=['POST']); login_required; super_admin_required`. Referenced names: Company, Exception
- L19359 `migration_history_all`: `app.route('/migrations/history'); login_required; super_admin_required`. Referenced names: Company, Exception
- L19411 `migration_history`: `app.route('/migrations/history/<company_id>'); login_required; super_admin_required`. Referenced names: 
- L19444 `admin_dashboard`: `app.route('/admin/dashboard'); login_required; super_admin_required`. Referenced names: Company, CompanyUser, Exception, RegisteredUser
- L19500 `admin_companies`: `app.route('/admin/companies'); login_required; super_admin_required`. Referenced names: Company
- L19507 `admin_company_detail`: `app.route('/admin/company/<company_id>'); login_required; super_admin_required`. Referenced names: 
- L19514 `admin_update_company_plan`: `app.route('/admin/company/<company_id>/update-plan', methods=['POST']); login_required; super_admin_required`. Referenced names: RegisteredUser, SubscriptionPlan, ValueError
- L19556 `admin_renew_company`: `app.route('/admin/company/<company_id>/renew', methods=['POST']); login_required; super_admin_required`. Referenced names: 
- L19581 `admin_toggle_company_status`: `app.route('/admin/company/<company_id>/toggle-status', methods=['POST']); login_required; super_admin_required`. Referenced names: 
- L19596 `admin_edit_company`: `app.route('/admin/company/<company_id>/edit', methods=['POST']); login_required; super_admin_required`. Referenced names: Company, Exception, RegisteredUser, ValueError
- L19743 `admin_edit_user`: `app.route('/admin/user/<user_id>/edit', methods=['POST']); login_required; super_admin_required`. Referenced names: Company, Exception, RegisteredUser, ValueError
- L19885 `admin_delete_user`: `app.route('/admin/user/<user_id>/delete', methods=['POST']); login_required; super_admin_required; require_admin_password`. Referenced names: BackupRecord, BackupSchedule, Company, CompanyWhatsAppConfig, Exception, RegisteredUser
- L19934 `admin_users`: `app.route('/admin/users'); login_required; super_admin_required`. Referenced names: 
- L19943 `admin_delete_company`: `app.route('/admin/company/<company_id>/delete', methods=['POST']); login_required; super_admin_required; require_admin_password`. Referenced names: BackupRecord, BackupSchedule, CompanyWhatsAppConfig, Exception
- L19973 `register_client`: `app.route('/admin/register-client', methods=['GET', 'POST']); login_required; super_admin_required`. Referenced names: RegisteredUser, SubscriptionPlan, ValueError
- L20089 `employee_list`: `app.route('/employees'); login_required; owner_required`. Referenced names: CompanyUser
- L20099 `employee_add`: `app.route('/employees/add', methods=['GET', 'POST']); login_required; owner_required`. Referenced names: CompanyUser
- L20130 `employee_toggle`: `app.route('/employees/toggle/<user_id>', methods=['POST']); login_required; owner_required`. Referenced names: CompanyUser
- L20146 `api_product_lookup`: `app.route('/api/product/<code>'); login_required; require_permission('stock', 'view')`. Referenced names: StockItem
- L20170 `api_products_search`: `app.route('/api/products/search'); login_required; require_permission('stock', 'view')`. Referenced names: StockItem
- L20198 `cash_in_hand`: `app.route('/cash-in-hand'); login_required; require_permission('cash', 'view')`. Referenced names: CashTransaction
- L20281 `save_cash_transaction`: `app.route('/api/cash-transaction/save', methods=['POST']); login_required; require_permission('cash', 'create')`. Referenced names: CashTransaction, Exception
- L20311 `delete_cash_transaction`: `app.route('/api/cash-transaction/delete/<int:txn_id>', methods=['DELETE']); login_required; owner_required; require_admin_password`. Referenced names: CashTransaction, Exception
- L20335 `bank_accounts`: `app.route('/bank-accounts'); login_required; require_permission('bank', 'view')`. Referenced names: BankAccount, BankTransaction
- L20360 `add_bank_account`: `app.route('/bank-accounts/add', methods=['POST']); login_required; require_permission('bank', 'create')`. Referenced names: BankAccount, BankTransaction
- L20421 `bank_transactions`: `app.route('/bank-accounts/<int:account_id>/transactions'); login_required; require_permission('bank', 'view')`. Referenced names: BankAccount, BankTransaction, ValueError
- L20529 `add_bank_transaction`: `app.route('/bank-accounts/<int:account_id>/add-transaction', methods=['POST']); login_required; require_permission('bank', 'create')`. Referenced names: BankAccount, BankTransaction
- L20579 `delete_bank_account`: `app.route('/bank-accounts/<int:account_id>/delete', methods=['GET', 'POST']); login_required; owner_required; require_admin_password`. Referenced names: BankAccount
- L20596 `reactivate_bank_account`: `app.route('/bank-accounts/<int:account_id>/reactivate', methods=['GET', 'POST']); login_required; owner_required`. Referenced names: BankAccount
- L20613 `delete_bank_account_permanent`: `app.route('/bank-accounts/<int:account_id>/delete-permanent', methods=['POST']); login_required; owner_required; require_admin_password`. Referenced names: BankAccount, BankTransaction
- L20640 `bank_transfer`: `app.route('/bank-accounts/<int:account_id>/transfer', methods=['POST']); login_required; require_permission('bank', 'edit')`. Referenced names: BankAccount, BankTransaction
- L20712 `repair_party_names`: `app.route('/admin/repair-party-names', methods=['POST']); login_required; owner_required`. Referenced names: BankTransaction, CashTransaction, Client, Supplier
- L20786 `cheques`: `app.route('/cheques'); login_required; require_permission('cheques', 'view')`. Referenced names: BankAccount, Cheque, Client, Supplier
- L20881 `cheque_save`: `app.route('/cheques/save', methods=['POST']); login_required; require_permission('cheques', 'create')`. Referenced names: Cheque, Invoice, PurchaseInvoice
- L20970 `cheque_clear`: `app.route('/cheques/<int:cheque_id>/clear', methods=['POST']); login_required; require_permission('cheques', 'edit')`. Referenced names: BankAccount, BankTransaction, Cheque, Client, Invoice, PurchaseInvoice, Supplier
- L21063 `cheque_bounce`: `app.route('/cheques/<int:cheque_id>/bounce', methods=['POST']); login_required; require_permission('cheques', 'edit')`. Referenced names: Cheque
- L21085 `cheque_cancel`: `app.route('/cheques/<int:cheque_id>/cancel', methods=['POST']); login_required; require_permission('cheques', 'edit')`. Referenced names: Cheque
- L21110 `loan_accounts`: `app.route('/loan-accounts'); login_required; require_permission('loans', 'view')`. Referenced names: Loan
- L21177 `save_loan`: `app.route('/api/loan/save', methods=['POST']); login_required; require_permission('loans', 'create')`. Referenced names: Exception, Loan
- L21210 `save_loan_repayment`: `app.route('/api/loan/repayment/save', methods=['POST']); login_required; require_permission('loans', 'create')`. Referenced names: Exception, Loan, LoanRepayment
- L21251 `ledger`: `app.route('/ledger'); login_required; require_permission('analytics', 'view')`. Referenced names: Invoice, PurchaseInvoice
- L21384 `trial_balance`: `app.route('/trial-balance'); login_required; require_permission('analytics', 'view')`. Referenced names: Client, Invoice, PurchaseInvoice, StockItem
- L21501 `api_sales_report_data`: `app.route('/api/reports/sales-data'); login_required; require_permission('analytics', 'view')`. Referenced names: Invoice
- L21622 `api_purchase_report_data`: `app.route('/api/reports/purchase-data'); login_required; require_permission('analytics', 'view')`. Referenced names: Exception, PurchaseInvoice
- L21730 `api_stock_report_data`: `app.route('/api/reports/stock-data'); login_required; require_permission('analytics', 'view')`. Referenced names: Invoice, StockItem
- L21814 `api_tax_report_data`: `app.route('/api/reports/tax-data'); login_required; require_permission('analytics', 'view')`. Referenced names: Invoice, PurchaseInvoice
- L21896 `api_financial_report_data`: `app.route('/api/reports/financial-data'); login_required; require_permission('analytics', 'view')`. Referenced names: BankAccount, CashTransaction, Expense, Invoice, PurchaseInvoice
- L22083 `profit_loss`: `app.route('/reports/profit-loss'); login_required; require_permission('analytics', 'view')`. Referenced names: CashTransaction, Invoice, PurchaseInvoice
- L22236 `sync_data`: `app.route('/sync'); login_required`. Referenced names: 
- L22244 `share_data`: `app.route('/share'); login_required`. Referenced names: 
- L22255 `integrations`: `app.route('/integrations'); login_required`. Referenced names: 
- L22262 `addons`: `app.route('/addons'); login_required`. Referenced names: 
- L22273 `import_data`: `app.route('/import'); login_required`. Referenced names: 
- L22280 `export_data`: `app.route('/export'); login_required`. Referenced names: 
- L22287 `audit_log`: `app.route('/audit-log'); login_required`. Referenced names: 
- L22297 `profile`: `app.route('/profile'); login_required`. Referenced names: 
- L22310 `company_settings`: `app.route('/company/settings'); login_required; owner_required`. Referenced names: ALLOWED_COMPANY_ROLES, CompanyApiKey, CompanyRolePermission, CompanyUser, Exception, INVOICE_FIELDS
- L22424 `save_role_permissions`: `app.route('/company/permissions/role/<role>', methods=['POST']); login_required; owner_required`. Referenced names: CompanyRolePermission
- L22444 `save_user_permissions`: `app.route('/company/permissions/user/<user_id>', methods=['POST']); login_required; owner_required`. Referenced names: CompanyUser
- L22464 `whatsapp_settings`: `app.route('/settings/whatsapp', methods=['GET', 'POST']); login_required; owner_required`. Referenced names: EVENTS, HARDCODED_VARS, WhatsAppTemplate
- L22575 `whatsapp_disconnect`: `app.route('/settings/whatsapp/disconnect', methods=['POST']); login_required; owner_required`. Referenced names: 
- L22591 `whatsapp_test`: `app.route('/settings/whatsapp/test', methods=['POST']); login_required; owner_required`. Referenced names: 
- L22636 `update_company_info`: `app.route('/company/update-info', methods=['POST']); login_required; owner_required`. Referenced names: Company, LOGO_UPLOAD_FOLDER, TypeError, ValueError
- L22766 `manifest_print_selected_generated`: `app.route('/manifest/print/selected/generated'); login_required; require_permission('manifest', 'view')`. Referenced names: Company, CompanyManifest, ManifestEntry, Supplier, ValueError
- L22877 `whatsapp_template_config`: `app.route('/settings/whatsapp/templates', methods=['GET', 'POST']); login_required; owner_required`. Referenced names: EVENT_DEFS, Exception, TypeError, ValueError, WhatsAppTemplate
- L22968 `change_company_password`: `app.route('/company/change-password', methods=['POST']); login_required; owner_required`. Referenced names: CompanyUser, Exception, RegisteredUser
- L23032 `add_company_user`: `app.route('/company/add-user', methods=['POST']); login_required; owner_required`. Referenced names: ALLOWED_COMPANY_ROLES, CompanyUser, TypeError, ValueError
- L23111 `revoke_company_user`: `app.route('/company/revoke-user/<email>/<company_id>'); login_required; owner_required`. Referenced names: CompanyUser
- L23133 `remove_company_user`: `app.route('/company/remove-user/<user_id>'); login_required; owner_required`. Referenced names: CompanyUser
- L23150 `delete_company_user`: `app.route('/company/delete-user/<email>', methods=['GET', 'POST']); login_required; owner_required; require_admin_password`. Referenced names: CompanyUser
- L23179 `edit_user_access`: `app.route('/company/edit-user-access/<email>', methods=['POST']); login_required; owner_required`. Referenced names: ALLOWED_COMPANY_ROLES, CompanyUser
- L23252 `upgrade_plan`: `app.route('/company/upgrade-plan', methods=['POST']); login_required; owner_required`. Referenced names: SubscriptionPlan
- L23666 `debtors_list`: `app.route('/debtors'); login_required; require_permission('debtors', 'view')`. Referenced names: 
- L23680 `creditors_list`: `app.route('/creditors'); login_required; require_permission('creditors', 'view')`. Referenced names: 
- L23940 `debtor_statement`: `app.route('/debtors/<int:client_pk>/statement'); login_required; require_permission('debtors', 'view')`. Referenced names: Client, StatementClosing
- L24092 `debtor_shift_to_opening`: `app.route('/debtors/<int:client_pk>/shift-to-opening', methods=['GET', 'POST']); login_required; owner_required; require_admin_password`. Referenced names: Client
- L24115 `debtor_close_statement`: `app.route('/debtors/<int:client_pk>/close', methods=['GET', 'POST']); login_required; owner_required; require_admin_password`. Referenced names: Client
- L24137 `debtor_statement_archive`: `app.route('/debtors/<int:client_pk>/statement/archive/<int:archive_id>'); login_required; require_permission('debtors', 'view')`. Referenced names: Client, StatementClosing
- L24165 `creditor_statement`: `app.route('/creditors/<int:supplier_pk>/statement'); login_required; require_permission('creditors', 'view')`. Referenced names: BankTransaction, CashTransaction, PurchaseInvoice, StatementClosing, Supplier
- L24296 `creditor_statement_archive`: `app.route('/creditors/<int:supplier_pk>/statement/archive/<int:archive_id>'); login_required; require_permission('creditors', 'view')`. Referenced names: StatementClosing, Supplier
- L24565 `receipt_new`: `app.route('/receipts/new'); login_required; require_permission('receipts_payments', 'view')`. Referenced names: BankAccount, BankTransaction, CashTransaction, Client, CustomerInvoice, ValueError
- L24705 `receipt_save`: `app.route('/receipts/save', methods=['POST']); login_required; require_permission('receipts_payments', 'create')`. Referenced names: BankAccount, BankTransaction, CashTransaction, Client, CustomerInvoice, Invoice, ValueError
- L24975 `payment_new`: `app.route('/payments/new'); login_required; require_permission('receipts_payments', 'view')`. Referenced names: BankAccount, BankTransaction, CashTransaction, Supplier, ValueError
- L25095 `payment_save`: `app.route('/payments/save', methods=['POST']); login_required; require_permission('receipts_payments', 'create')`. Referenced names: BankAccount, BankTransaction, CashTransaction, PurchaseInvoice, Supplier
- L25296 `backup`: `app.route('/backup'); login_required; require_permission('backup', 'view')`. Referenced names: BACKUP_DESTINATIONS, Exception, ImportError
- L25330 `create_backup`: `app.route('/backup/create', methods=['POST']); login_required; require_permission('backup', 'create')`. Referenced names: Exception, ValueError
- L25403 `restore_backup`: `app.route('/backup/restore/<backup_id>', methods=['POST']); login_required; require_permission('backup', 'edit')`. Referenced names: Exception
- L25422 `download_backup`: `app.route('/backup/download/<backup_id>'); login_required; require_permission('backup', 'view')`. Referenced names: BackupRecord
- L25443 `delete_backup_record`: `app.route('/backup/delete/<backup_id>', methods=['POST']); login_required; owner_required; require_admin_password`. Referenced names: Exception
- L25461 `schedule_backup`: `app.route('/backup/schedule', methods=['POST']); login_required; require_permission('backup', 'edit')`. Referenced names: BackupSchedule
- L25518 `upload_backup_to_cloud_route`: `app.route('/backup/upload-to-cloud/<backup_id>', methods=['POST']); login_required; require_permission('backup', 'edit')`. Referenced names: Exception
- L25556 `upload_backup`: `app.route('/backup/upload', methods=['POST']); login_required; require_permission('backup', 'edit')`. Referenced names: Exception
- L25622 `generate_company_api_key`: `app.route('/company/api-keys/generate', methods=['POST']); login_required; owner_required`. Referenced names: 
- L25636 `revoke_company_api_key`: `app.route('/company/api-keys/<int:key_id>/revoke', methods=['POST']); login_required; owner_required`. Referenced names: CompanyApiKey
- L25737 `mark_entry_dispatched`: `app.route('/manifest/entry/<int:entry_id>/dispatch', methods=['POST']); login_required`. Referenced names: ManifestEntry
- L25760 `public_tracking`: `app.route('/track/<company_slug>', methods=['GET', 'POST']); limiter.limit('10 per minute')`. Referenced names: Company
- L25774 `track_magic_link`: `app.route('/t/<company_id>/<docket_no>'); limiter.limit('30 per minute')`. Referenced names: Company
- L25784 `public_tracking_generic`: `app.route('/track', methods=['GET', 'POST']); limiter.limit('10 per minute')`. Referenced names: TrackingIndex
- L25825 `delete_payment`: `app.route('/payment/delete', methods=['GET', 'POST']); login_required; owner_required; require_admin_password`. Referenced names: BankTransaction, CashTransaction, Exception, PurchaseInvoice, Supplier, TypeError, ValueError
- L25980 `delete_receipt`: `app.route('/receipt/delete', methods=['GET', 'POST']); login_required; owner_required; require_admin_password`. Referenced names: BankTransaction, CashTransaction, Client, CustomerInvoice, Exception, Invoice, TypeError, ValueError
- L26137 `payment_edit_data`: `app.route('/payment/edit-data'); login_required; require_permission('receipts_payments', 'view')`. Referenced names: BankTransaction, CashTransaction
- L26167 `payment_update`: `app.route('/payment/update', methods=['POST']); login_required; require_permission('receipts_payments', 'create')`. Referenced names: BankAccount, BankTransaction, CashTransaction, Exception, PurchaseInvoice, Supplier, TypeError, ValueError
- L26336 `receipt_edit_data`: `app.route('/receipt/edit-data'); login_required; require_permission('receipts_payments', 'view')`. Referenced names: BankTransaction, CashTransaction
- L26366 `receipt_update`: `app.route('/receipt/update', methods=['POST']); login_required; require_permission('receipts_payments', 'create')`. Referenced names: BankAccount, BankTransaction, CashTransaction, Client, CustomerInvoice, Exception, Invoice, TypeError, ValueError
- L26562 `apps_hub`: `app.route('/apps'); login_required`. Referenced names: CompanyUser, Exception
### _NoOpLimiter (L25660)

## auth_utils.py


## backup_scheduler.py


## backup_utils.py


## crm_routes.py

- L48 `crm_view`: `app.route('/crm', endpoint='crm_view'); app.route('/crm/dashboard', endpoint='crm_dashboard'); login_required`. Referenced names: LEAD_STAGES
- L57 `api_crm_dashboard`: `app.route('/api/crm/dashboard', methods=['GET']); login_required`. Referenced names: CRMInteraction, CRMLead, LEAD_STAGES
- L109 `api_crm_clients`: `app.route('/api/crm/clients', methods=['GET', 'POST']); login_required`. Referenced names: CRMContact, CRMLead, Client, OrderFlow
- L197 `api_crm_client_detail`: `app.route('/api/crm/clients/<client_id>', methods=['GET', 'PUT', 'DELETE']); login_required`. Referenced names: CRMContact, CRMLead, Client
- L256 `api_crm_customer_360`: `app.route('/api/crm/clients/<client_id>/360', methods=['GET']); login_required`. Referenced names: CRMContact, CRMInteraction, CRMLead, CRMQuotation, Client, OrderFlow
- L307 `api_crm_contacts`: `app.route('/api/crm/contacts', methods=['GET', 'POST']); login_required`. Referenced names: CRMContact, Client
- L348 `api_crm_contact_delete`: `app.route('/api/crm/contacts/<contact_id>', methods=['DELETE']); login_required`. Referenced names: CRMContact
- L361 `api_crm_leads`: `app.route('/api/crm/leads', methods=['GET', 'POST']); login_required`. Referenced names: CRMInteraction, CRMLead, Client, Exception, LEAD_STAGES
- L464 `api_crm_lead_detail`: `app.route('/api/crm/leads/<lead_id>', methods=['GET', 'PUT', 'DELETE']); login_required`. Referenced names: CRMInteraction, CRMLead, Exception
- L505 `api_crm_lead_stage`: `app.route('/api/crm/leads/<lead_id>/stage', methods=['PUT']); login_required`. Referenced names: CRMInteraction, CRMLead, LEAD_STAGES
- L544 `api_crm_lead_convert_order`: `app.route('/api/crm/leads/<lead_id>/convert', methods=['POST']); login_required`. Referenced names: CRMLead, Exception, OrderFlow, OrderFlowHistory
- L618 `api_crm_activities`: `app.route('/api/crm/activities', methods=['GET', 'POST']); login_required`. Referenced names: CRMInteraction, Client, INTERACTION_TYPES, TypeError, ValueError
- L682 `api_crm_activity_toggle`: `app.route('/api/crm/activities/<int:activity_id>/toggle', methods=['PUT']); login_required`. Referenced names: CRMInteraction
- L697 `api_crm_quotations`: `app.route('/api/crm/quotations', methods=['GET', 'POST']); login_required`. Referenced names: CRMQuotation, Exception
- L774 `api_crm_quotation_detail`: `app.route('/api/crm/quotations/<quote_id>', methods=['GET', 'PUT', 'DELETE']); login_required`. Referenced names: CRMQuotation, QUOTATION_STATUSES
- L804 `api_crm_quotation_convert`: `app.route('/api/crm/quotations/<quote_id>/convert', methods=['POST']); login_required`. Referenced names: CRMQuotation, Exception, OrderFlow, OrderFlowHistory
- L879 `api_crm_comm_log`: `app.route('/api/crm/communication/log', methods=['POST']); login_required`. Referenced names: CRMCommunicationLog
- L904 `api_crm_reports`: `app.route('/api/crm/reports', methods=['GET']); login_required`. Referenced names: CRMLead, CRMQuotation, LEAD_STAGES
- L941 `api_crm_settings`: `app.route('/api/crm/settings', methods=['GET', 'POST']); login_required`. Referenced names: CRMSetting, Exception

## crm_workspace.py

- L21 `crm_workspace_metrics`: `app.route('/api/crm/workspace/metrics'); login_required`. Referenced names: CRMContact, CRMInteraction, CRMLead, CRMProject, Client
- L37 `crm_projects`: `app.route('/api/crm/projects', methods=['GET', 'POST']); app.route('/api/crm/projects/<project_id>', methods=['PUT']); login_required`. Referenced names: CRMProject, Client, TypeError, ValueError
- L71 `crm_workspace_preferences`: `app.route('/api/crm/workspace/preferences', methods=['GET', 'POST']); login_required`. Referenced names: CRMSetting
- L108 `crm_workspace_export`: `app.route('/api/crm/workspace/export/<module>'); login_required`. Referenced names: CRMContact, CRMInteraction, CRMLead, CRMProject, Response

## currency_service.py


## customer_models.py

### _Base (L19)
### _CustomerDB (L27)
- `Model = _Base`
- `metadata = _Base.metadata`
- `Column = staticmethod(Column)`
- `Integer = Integer`
- `String = String`
- `Float = Float`
- `Boolean = Boolean`
- `Date = Date`
- `DateTime = DateTime`
- `Text = Text`
- `ForeignKey = staticmethod(ForeignKey)`
- `relationship = staticmethod(_relationship)`
### CompanyUser (L46)
- `__tablename__ = 'company_users'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `user_id = customer_db.Column(customer_db.String(20), unique=True, nullable=False)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `email = customer_db.Column(customer_db.String(255), nullable=False)`
- `password_hash = customer_db.Column(customer_db.String(255), nullable=False)`
- `full_name = customer_db.Column(customer_db.String(150), nullable=False)`
- `role = customer_db.Column(customer_db.String(50), nullable=False, default='employee')`
- `department = customer_db.Column(customer_db.String(100), nullable=True)`
- `phone = customer_db.Column(customer_db.String(20), nullable=True)`
- `is_active = customer_db.Column(customer_db.Boolean, nullable=False, default=True)`
- `created_at = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `field_permissions = customer_db.Column(customer_db.Text, nullable=True)`
- `editable_fields = customer_db.Column(customer_db.Text, nullable=True)`
- `permission_overrides = customer_db.Column(customer_db.Text, nullable=True)`
### CompanyRolePermission (L77)
- `__tablename__ = 'company_role_permissions'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `role = customer_db.Column(customer_db.String(50), nullable=False)`
- `permissions_json = customer_db.Column(customer_db.Text, nullable=True)`
- `field_permissions_json = customer_db.Column(customer_db.Text, nullable=True)`
- `updated_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
### Client (L92)
- `__tablename__ = 'clients'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `client_id = customer_db.Column(customer_db.String(20), unique=True, nullable=True)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `name = customer_db.Column(customer_db.String(200), nullable=False)`
- `contact_person = customer_db.Column(customer_db.String(150), nullable=True)`
- `client_type = customer_db.Column(customer_db.String(30), nullable=False, default='Business')`
- `phone = customer_db.Column(customer_db.String(20), nullable=True)`
- `alternate_phone = customer_db.Column(customer_db.String(20), nullable=True)`
- `email = customer_db.Column(customer_db.String(255), nullable=True)`
- `website = customer_db.Column(customer_db.String(255), nullable=True)`
- `address_line1 = customer_db.Column(customer_db.String(300), nullable=True)`
- `address_line2 = customer_db.Column(customer_db.String(300), nullable=True)`
- `city = customer_db.Column(customer_db.String(100), nullable=True)`
- `state = customer_db.Column(customer_db.String(100), nullable=True)`
- `pincode = customer_db.Column(customer_db.String(10), nullable=True)`
- `country = customer_db.Column(customer_db.String(100), nullable=False, default='India')`
- `currency = customer_db.Column(customer_db.String(10), nullable=True)`
- `trn_number = customer_db.Column(customer_db.String(50), nullable=True)`
- `tax_regime = customer_db.Column(customer_db.String(50), nullable=True)`
- `gst_number = customer_db.Column(customer_db.String(20), nullable=True)`
- `pan_number = customer_db.Column(customer_db.String(15), nullable=True)`
- `aadhar_number = customer_db.Column(customer_db.String(12), nullable=True)`
- `aadhar_front_file = customer_db.Column(customer_db.String(255), nullable=True)`
- `aadhar_back_file = customer_db.Column(customer_db.String(255), nullable=True)`
- `pan_front_file = customer_db.Column(customer_db.String(255), nullable=True)`
- `pan_back_file = customer_db.Column(customer_db.String(255), nullable=True)`
- `gst_type = customer_db.Column(customer_db.String(30), nullable=False, default='Regular')`
- `credit_limit = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `credit_days = customer_db.Column(customer_db.Integer, nullable=False, default=30)`
- `pending = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `last_payment = customer_db.Column(customer_db.Date, nullable=True)`
- `opening_balance = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `status = customer_db.Column(customer_db.String(50), nullable=False, default='Active')`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_at = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `statement_cutoff = customer_db.Column(customer_db.DateTime, nullable=True)`
### Supplier (L164)
- `__tablename__ = 'suppliers'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `supplier_id = customer_db.Column(customer_db.String(20), unique=True, nullable=True)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `name = customer_db.Column(customer_db.String(200), nullable=False)`
- `supplier_type = customer_db.Column(customer_db.String(30), nullable=False, default='Business')`
- `contact_person = customer_db.Column(customer_db.String(150), nullable=True)`
- `phone = customer_db.Column(customer_db.String(20), nullable=True)`
- `alternate_phone = customer_db.Column(customer_db.String(20), nullable=True)`
- `email = customer_db.Column(customer_db.String(255), nullable=True)`
- `website = customer_db.Column(customer_db.String(255), nullable=True)`
- `address_line1 = customer_db.Column(customer_db.String(300), nullable=True)`
- `address_line2 = customer_db.Column(customer_db.String(300), nullable=True)`
- `city = customer_db.Column(customer_db.String(100), nullable=True)`
- `state = customer_db.Column(customer_db.String(100), nullable=True)`
- `pincode = customer_db.Column(customer_db.String(10), nullable=True)`
- `country = customer_db.Column(customer_db.String(100), nullable=False, default='India')`
- `currency = customer_db.Column(customer_db.String(10), nullable=True)`
- `trn_number = customer_db.Column(customer_db.String(50), nullable=True)`
- `tax_regime = customer_db.Column(customer_db.String(50), nullable=True)`
- `gst_number = customer_db.Column(customer_db.String(20), nullable=True)`
- `pan_number = customer_db.Column(customer_db.String(15), nullable=True)`
- `aadhar_number = customer_db.Column(customer_db.String(12), nullable=True)`
- `gst_type = customer_db.Column(customer_db.String(30), nullable=False, default='Regular')`
- `credit_limit = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `credit_days = customer_db.Column(customer_db.Integer, nullable=False, default=30)`
- `payable = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `opening_balance = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `last_purchase = customer_db.Column(customer_db.Date, nullable=True)`
- `status = customer_db.Column(customer_db.String(50), nullable=False, default='Active')`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_at = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `statement_cutoff = customer_db.Column(customer_db.DateTime, nullable=True)`
- `brands = customer_db.relationship('SupplierBrand', back_populates='supplier', cascade='all, delete-orphan')`
### SupplierBrand (L207)
- `__tablename__ = 'supplier_brands'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `supplier_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('suppliers.id'), nullable=False)`
- `brand_name = customer_db.Column(customer_db.String(100), nullable=False)`
- `created_at = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `supplier = customer_db.relationship('Supplier', back_populates='brands')`
### Order (L222)
- `__tablename__ = 'orders'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `order_id = customer_db.Column(customer_db.String(30), unique=True, nullable=False)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `client_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `employee_id = customer_db.Column(customer_db.String(20), nullable=True)`
- `date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `received = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `status = customer_db.Column(customer_db.String(50), nullable=False, default='Pending')`
### StockItem (L240)
- `__tablename__ = 'stock_items'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `code = customer_db.Column(customer_db.String(50), nullable=False)`
- `name = customer_db.Column(customer_db.String(200), nullable=False)`
- `category = customer_db.Column(customer_db.String(100), nullable=True)`
- `quantity = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `unit = customer_db.Column(customer_db.String(20), nullable=True, default='pcs')`
- `unit_price = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `reorder_level = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `hsn = customer_db.Column(customer_db.String(20), nullable=True)`
- `last_updated = customer_db.Column(customer_db.Date, nullable=True)`
- `purchase_rate = customer_db.Column(customer_db.Float, nullable=True)`
- `last_purchase_rate = customer_db.Column(customer_db.Float, nullable=True)`
- `avg_purchase_rate = customer_db.Column(customer_db.Float, nullable=True)`
- `gst_percent = customer_db.Column(customer_db.Float, nullable=True, default=18.0)`
- `selling_price = customer_db.Column(customer_db.Float, nullable=True)`
- `margin_percent = customer_db.Column(customer_db.Float, nullable=True)`
- `client_id = customer_db.Column(customer_db.Integer, nullable=True, default=None)`
- `item_type = customer_db.Column(customer_db.String(50), nullable=True, default=None)`
- `shipper_name = customer_db.Column(customer_db.String(200), nullable=True, default=None)`
- `brand = customer_db.Column(customer_db.String(100), nullable=True, default=None)`
### Invoice (L289)
- `__tablename__ = 'invoices'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `invoice_id = customer_db.Column(customer_db.String(30), unique=True, nullable=False)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `client_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `due_date = customer_db.Column(customer_db.Date, nullable=True)`
- `status = customer_db.Column(customer_db.String(50), nullable=False, default='Pending')`
- `subtotal = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `tax_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `grand_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `contact_person = customer_db.Column(customer_db.String(150), nullable=True)`
- `email = customer_db.Column(customer_db.String(255), nullable=True)`
- `phone = customer_db.Column(customer_db.String(20), nullable=True)`
- `terms = customer_db.Column(customer_db.Text, nullable=True)`
- `paid_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `balance = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `discount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `resale_charges = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `resale_reason = customer_db.Column(customer_db.String(200), nullable=True)`
- `resale_date = customer_db.Column(customer_db.Date, nullable=True)`
- `resale_notes = customer_db.Column(customer_db.Text, nullable=True)`
- `has_resale = customer_db.Column(customer_db.Boolean, nullable=False, default=False)`
- `docket_no = Column(String(50), nullable=True, index=True)`
- `submit_token = customer_db.Column(customer_db.String(64), nullable=True, unique=True, index=True)`
- `created_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `updated_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `items = customer_db.relationship('InvoiceItem', back_populates='invoice', cascade='all, delete-orphan')`
### DeletedInvoiceLog (L342)
- `__tablename__ = 'deleted_invoice_log'`
- `id = Column(Integer, primary_key=True)`
- `company_id = Column(String(50), nullable=False)`
- `invoice_id = Column(String(50))`
- `awb_no = Column(String(50))`
- `client_name = Column(String(255))`
- `shipper_name = Column(String(255))`
- `grand_total = Column(Float)`
- `deleted_by = Column(String(255))`
- `deleted_at = Column(DateTime, default=datetime.utcnow)`
- `reason = Column(String(255))`
### CustomerInvoice (L357)
- `__tablename__ = 'customer_invoices'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `invoice_number = customer_db.Column(customer_db.String(30), unique=True, nullable=False)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `client_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `client_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `billing_address = customer_db.Column(customer_db.Text, nullable=True)`
- `shipping_address = customer_db.Column(customer_db.Text, nullable=True)`
- `client_gstin = customer_db.Column(customer_db.String(50), nullable=True)`
- `client_state = customer_db.Column(customer_db.String(100), nullable=True)`
- `invoice_date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `due_date = customer_db.Column(customer_db.Date, nullable=True)`
- `invoice_type = customer_db.Column(customer_db.String(10), nullable=False, default='credit')`
- `invoice_category = customer_db.Column(customer_db.String(30), nullable=False, default='product_sale')`
- `status = customer_db.Column(customer_db.String(50), nullable=False, default='Pending')`
- `payment_terms = customer_db.Column(customer_db.String(100), nullable=True)`
- `currency = customer_db.Column(customer_db.String(10), nullable=False, default='INR')`
- `exchange_rate = customer_db.Column(customer_db.Float, nullable=False, default=1.0)`
- `subtotal = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `tax_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `cgst_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `sgst_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `igst_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `grand_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_subtotal = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_tax_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_grand_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `tax_regime = customer_db.Column(customer_db.String(50), nullable=False, default='GST')`
- `paid_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `balance = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `terms = customer_db.Column(customer_db.Text, nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `updated_at = customer_db.Column(customer_db.DateTime, nullable=True, onupdate=datetime.utcnow)`
- `created_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `updated_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `booking_ids_json = customer_db.Column(customer_db.Text, nullable=True)`
- `items = customer_db.relationship('CustomerInvoiceItem', back_populates='customer_invoice', cascade='all, delete-orphan')`
### CustomerInvoiceItem (L414)
- `__tablename__ = 'customer_invoice_items'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `customer_invoice_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('customer_invoices.id'), nullable=False)`
- `stock_item_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `item_code = customer_db.Column(customer_db.String(50), nullable=True)`
- `item_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `item_description = customer_db.Column(customer_db.String(300), nullable=True)`
- `hsn = customer_db.Column(customer_db.String(20), nullable=True)`
- `quantity = customer_db.Column(customer_db.Float, nullable=False, default=1.0)`
- `unit = customer_db.Column(customer_db.String(20), nullable=True, default='pcs')`
- `rate = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `rate_per_kg = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `weight_kg = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `discount_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `taxable_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `other_charges = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `gst_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `cgst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `sgst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `igst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `total_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_rate = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_taxable_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_total_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `booking_invoice_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `booking_invoice_ref = customer_db.Column(customer_db.String(30), nullable=True)`
- `docket_no = customer_db.Column(customer_db.String(50), nullable=True)`
- `receiver_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `destination = customer_db.Column(customer_db.String(150), nullable=True)`
- `carrier = customer_db.Column(customer_db.String(100), nullable=True)`
- `carrier_ref = customer_db.Column(customer_db.String(100), nullable=True)`
- `booking_date = customer_db.Column(customer_db.Date, nullable=True)`
- `customer_invoice = customer_db.relationship('CustomerInvoice', back_populates='items')`
### PriceList (L460)
- `__tablename__ = 'price_lists'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `courier = customer_db.Column(customer_db.String(50), nullable=False)`
- `filename = customer_db.Column(customer_db.String(255), nullable=False)`
- `file_path = customer_db.Column(customer_db.String(500), nullable=False)`
- `rate_data = customer_db.Column(customer_db.Text, nullable=True)`
- `is_active = customer_db.Column(customer_db.Boolean, default=True)`
- `list_type = customer_db.Column(customer_db.String(20), nullable=False, default='sales')`
- `uploaded_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `uploaded_by = customer_db.Column(customer_db.String(100), nullable=True)`
### RateLookup (L479)
- `__tablename__ = 'rate_lookups'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `courier = customer_db.Column(customer_db.String(50), nullable=False)`
- `destination = customer_db.Column(customer_db.String(100), nullable=False)`
- `weight = customer_db.Column(customer_db.Float, nullable=False)`
- `rate = customer_db.Column(customer_db.Float, nullable=False)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `lookup_count = customer_db.Column(customer_db.Integer, default=1)`
### InvoiceItem (L493)
- `__tablename__ = 'invoice_items'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `invoice_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('invoices.id'), nullable=False)`
- `stock_item_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `code = customer_db.Column(customer_db.String(50), nullable=True)`
- `description = customer_db.Column(customer_db.String(300), nullable=False)`
- `qty = customer_db.Column(customer_db.Float, nullable=False, default=1.0)`
- `rate = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `discount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `invoice = customer_db.relationship('Invoice', back_populates='items')`
### Estimate (L512)
- `__tablename__ = 'estimates'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `estimate_id = customer_db.Column(customer_db.String(30), unique=True, nullable=False)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `client_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `client_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `client_address = customer_db.Column(customer_db.Text, nullable=True)`
- `client_gstin = customer_db.Column(customer_db.String(50), nullable=True)`
- `client_state = customer_db.Column(customer_db.String(100), nullable=True)`
- `date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `valid_until = customer_db.Column(customer_db.Date, nullable=True)`
- `status = customer_db.Column(customer_db.String(50), nullable=False, default='Draft')`
- `payment_terms = customer_db.Column(customer_db.String(100), nullable=True)`
- `delivery_terms = customer_db.Column(customer_db.String(100), nullable=True)`
- `currency = customer_db.Column(customer_db.String(10), nullable=False, default='INR')`
- `exchange_rate = customer_db.Column(customer_db.Float, nullable=False, default=1.0)`
- `subtotal = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `tax_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `cgst_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `sgst_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `igst_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `grand_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_subtotal = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_tax_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_grand_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `tax_regime = customer_db.Column(customer_db.String(50), nullable=False, default='GST')`
- `contact_person = customer_db.Column(customer_db.String(150), nullable=True)`
- `email = customer_db.Column(customer_db.String(150), nullable=True)`
- `phone = customer_db.Column(customer_db.String(30), nullable=True)`
- `terms = customer_db.Column(customer_db.Text, nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `created_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `updated_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `version = customer_db.Column(customer_db.Integer, nullable=False, default=1)`
- `items = customer_db.relationship('EstimateItem', back_populates='estimate', cascade='all, delete-orphan')`
### EstimateItem (L566)
- `__tablename__ = 'estimate_items'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `estimate_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('estimates.id'), nullable=False)`
- `stock_item_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `item_code = customer_db.Column(customer_db.String(50), nullable=True)`
- `code = customer_db.Column(customer_db.String(50), nullable=True)`
- `item_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `description = customer_db.Column(customer_db.String(300), nullable=False)`
- `hsn = customer_db.Column(customer_db.String(20), nullable=True)`
- `qty = customer_db.Column(customer_db.Float, nullable=False, default=1.0)`
- `unit = customer_db.Column(customer_db.String(20), nullable=True, default='pcs')`
- `rate = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `discount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `discount_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `taxable_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `gst_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `cgst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `sgst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `igst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `total_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `estimate = customer_db.relationship('Estimate', back_populates='items')`
### PurchaseInvoice (L597)
- `__tablename__ = 'purchase_invoices'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `invoice_id = customer_db.Column(customer_db.String(30), unique=True, nullable=False)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `supplier_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `supplier_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `supplier_address = customer_db.Column(customer_db.Text, nullable=True)`
- `supplier_gstin = customer_db.Column(customer_db.String(50), nullable=True)`
- `supplier_state = customer_db.Column(customer_db.String(100), nullable=True)`
- `supplier_phone = customer_db.Column(customer_db.String(50), nullable=True)`
- `supplier_email = customer_db.Column(customer_db.String(100), nullable=True)`
- `invoice_number = customer_db.Column(customer_db.String(100), nullable=True)`
- `reference_po_no = customer_db.Column(customer_db.String(100), nullable=True)`
- `date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `due_date = customer_db.Column(customer_db.Date, nullable=True)`
- `currency = customer_db.Column(customer_db.String(10), nullable=False, default='INR')`
- `exchange_rate = customer_db.Column(customer_db.Float, nullable=False, default=1.0)`
- `subtotal = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `cgst_total = customer_db.Column(customer_db.Float, nullable=True, default=0.0)`
- `sgst_total = customer_db.Column(customer_db.Float, nullable=True, default=0.0)`
- `igst_total = customer_db.Column(customer_db.Float, nullable=True, default=0.0)`
- `tax_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `grand_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_subtotal = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_tax_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_grand_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_paid_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_balance = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `tax_regime = customer_db.Column(customer_db.String(50), nullable=False, default='GST')`
- `tax_type = customer_db.Column(customer_db.String(50), nullable=False, default='Domestic')`
- `paid_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `balance = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `status = customer_db.Column(customer_db.String(50), nullable=False, default='Pending')`
- `payment_terms = customer_db.Column(customer_db.String(100), nullable=True)`
- `terms = customer_db.Column(customer_db.Text, nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `file_path = customer_db.Column(customer_db.String(500), nullable=True)`
- `ocr_data = customer_db.Column(customer_db.Text, nullable=True)`
- `created_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `updated_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `items = customer_db.relationship('PurchaseInvoiceItem', back_populates='purchase_invoice', cascade='all, delete-orphan')`
- `purchase_history = customer_db.relationship('StockPurchaseHistory', back_populates='purchase_invoice', cascade='all, delete-orphan')`
### PurchaseInvoiceItem (L657)
- `__tablename__ = 'purchase_invoice_items'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `purchase_invoice_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('purchase_invoices.id'), nullable=False)`
- `stock_item_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `item_code = customer_db.Column(customer_db.String(50), nullable=True)`
- `code = customer_db.Column(customer_db.String(50), nullable=True)`
- `item_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `description = customer_db.Column(customer_db.String(300), nullable=False)`
- `hsn = customer_db.Column(customer_db.String(20), nullable=True)`
- `quantity = customer_db.Column(customer_db.Float, nullable=False, default=1.0)`
- `unit = customer_db.Column(customer_db.String(20), nullable=True, default='pcs')`
- `rate = customer_db.Column(customer_db.Float, nullable=True, default=0.0)`
- `purchase_rate = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `discount_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `taxable_amount = customer_db.Column(customer_db.Float, nullable=True, default=0.0)`
- `taxable_value = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `gst_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `cgst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `sgst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `igst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `total_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_rate = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_taxable_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `base_total_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `docket_no = customer_db.Column(customer_db.String(100), nullable=True)`
- `carrier_ref = customer_db.Column(customer_db.String(100), nullable=True)`
- `party_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `consignee_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `destination = customer_db.Column(customer_db.String(150), nullable=True)`
- `courier_name = customer_db.Column(customer_db.String(100), nullable=True)`
- `weight_kg = customer_db.Column(customer_db.Float, nullable=True, default=0.0)`
- `rate_per_kg = customer_db.Column(customer_db.Float, nullable=True, default=0.0)`
- `other_charges = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `resale_charges = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `source_invoice_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('invoices.id'), nullable=True)`
- `purchase_invoice = customer_db.relationship('PurchaseInvoice', back_populates='items')`
### PurchasePayment (L699)
- `__tablename__ = 'purchase_payments'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `invoice_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('purchase_invoices.id'), nullable=False)`
- `supplier_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `pay_mode = customer_db.Column(customer_db.String(30), nullable=False, default='Cash')`
- `narration = customer_db.Column(customer_db.String(300), nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `created_by = customer_db.Column(customer_db.String(50), nullable=True)`
- `invoice = customer_db.relationship('PurchaseInvoice', backref='payments')`
### StockPurchaseHistory (L715)
- `__tablename__ = 'stock_purchase_history'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `stock_item_id = customer_db.Column(customer_db.Integer, nullable=False)`
- `purchase_invoice_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('purchase_invoices.id'), nullable=True)`
- `quantity = customer_db.Column(customer_db.Float, nullable=False)`
- `purchase_rate = customer_db.Column(customer_db.Float, nullable=False)`
- `currency = customer_db.Column(customer_db.String(10), nullable=False, default='INR')`
- `exchange_rate = customer_db.Column(customer_db.Float, nullable=False, default=1.0)`
- `base_purchase_rate = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `gst_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `purchase_date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `movement_type = customer_db.Column(customer_db.String(10), nullable=True, default='IN')`
- `reference = customer_db.Column(customer_db.String(100), nullable=True)`
- `awb_no = customer_db.Column(customer_db.String(50), nullable=True)`
- `source = customer_db.Column(customer_db.String(100), nullable=True)`
- `destination = customer_db.Column(customer_db.String(100), nullable=True)`
- `length = customer_db.Column(customer_db.Float, nullable=True)`
- `width = customer_db.Column(customer_db.Float, nullable=True)`
- `height = customer_db.Column(customer_db.Float, nullable=True)`
- `weight = customer_db.Column(customer_db.Float, nullable=True)`
- `purchase_invoice = customer_db.relationship('PurchaseInvoice', back_populates='purchase_history')`
### StatementClosing (L746)
- `__tablename__ = 'statement_closings'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `entity_type = customer_db.Column(customer_db.String(20), nullable=False)`
- `entity_id = customer_db.Column(customer_db.Integer, nullable=False)`
- `entity_name = customer_db.Column(customer_db.String(200), nullable=False)`
- `action = customer_db.Column(customer_db.String(20), nullable=False)`
- `closing_balance = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `total_debit = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `total_credit = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `ledger_snapshot = customer_db.Column(customer_db.Text, nullable=True)`
- `closed_by = customer_db.Column(customer_db.String(50), nullable=True)`
- `closed_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
### CashTransaction (L767)
- `__tablename__ = 'cash_transactions'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `type = customer_db.Column(customer_db.String(20), nullable=False)`
- `date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `category = customer_db.Column(customer_db.String(100), nullable=False)`
- `description = customer_db.Column(customer_db.String(300), nullable=False)`
- `amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `reference = customer_db.Column(customer_db.String(100), nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `party_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `created_by = customer_db.Column(customer_db.String(50), nullable=True)`
- `applied_ci_ids_json = customer_db.Column(customer_db.Text, nullable=True)`
- `applied_ref_type = customer_db.Column(customer_db.String(20), nullable=True)`
- `applied_ref_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `applied_ci_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `applied_breakdown_json = customer_db.Column(customer_db.Text, nullable=True)`
### BankAccount (L807)
- `__tablename__ = 'bank_accounts'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `bank_name = customer_db.Column(customer_db.String(200), nullable=False)`
- `account_name = customer_db.Column(customer_db.String(200), nullable=False)`
- `account_number = customer_db.Column(customer_db.String(50), nullable=False, unique=True)`
- `ifsc_code = customer_db.Column(customer_db.String(20), nullable=True)`
- `branch = customer_db.Column(customer_db.String(200), nullable=True)`
- `balance = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `opening_balance = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `status = customer_db.Column(customer_db.String(30), nullable=False, default='Active')`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `updated_at = customer_db.Column(customer_db.DateTime, nullable=True, onupdate=datetime.utcnow)`
- `transactions = customer_db.relationship('BankTransaction', back_populates='bank_account', cascade='all, delete-orphan')`
### BankTransaction (L828)
- `__tablename__ = 'bank_transactions'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `bank_account_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('bank_accounts.id'), nullable=False)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `type = customer_db.Column(customer_db.String(20), nullable=False)`
- `date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `description = customer_db.Column(customer_db.String(300), nullable=False)`
- `amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `reference = customer_db.Column(customer_db.String(100), nullable=True)`
- `transaction_mode = customer_db.Column(customer_db.String(30), nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `party_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `created_by = customer_db.Column(customer_db.String(50), nullable=True)`
- `applied_ci_ids_json = customer_db.Column(customer_db.Text, nullable=True)`
- `applied_ref_type = customer_db.Column(customer_db.String(20), nullable=True)`
- `applied_ref_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `applied_ci_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `applied_breakdown_json = customer_db.Column(customer_db.Text, nullable=True)`
- `bank_account = customer_db.relationship('BankAccount', back_populates='transactions')`
### Loan (L860)
- `__tablename__ = 'loans'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `type = customer_db.Column(customer_db.String(20), nullable=False)`
- `party_name = customer_db.Column(customer_db.String(200), nullable=False)`
- `loan_date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `interest_rate = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `tenure = customer_db.Column(customer_db.Integer, nullable=False, default=12)`
- `emi_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `purpose = customer_db.Column(customer_db.String(300), nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `status = customer_db.Column(customer_db.String(30), nullable=False, default='Active')`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `created_by = customer_db.Column(customer_db.String(50), nullable=True)`
- `repayments = customer_db.relationship('LoanRepayment', back_populates='loan', cascade='all, delete-orphan')`
### LoanRepayment (L895)
- `__tablename__ = 'loan_repayments'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `loan_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('loans.id'), nullable=False)`
- `date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `payment_mode = customer_db.Column(customer_db.String(30), nullable=False, default='Cash')`
- `reference = customer_db.Column(customer_db.String(100), nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `loan = customer_db.relationship('Loan', back_populates='repayments')`
### Cheque (L914)
- `__tablename__ = 'cheques'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `direction = customer_db.Column(customer_db.String(10), nullable=False)`
- `party_type = customer_db.Column(customer_db.String(10), nullable=True)`
- `party_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `party_name = customer_db.Column(customer_db.String(200), nullable=False)`
- `cheque_no = customer_db.Column(customer_db.String(30), nullable=False)`
- `cheque_date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `bank_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `bank_account_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('bank_accounts.id'), nullable=True)`
- `amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `narration = customer_db.Column(customer_db.String(300), nullable=True)`
- `status = customer_db.Column(customer_db.String(20), nullable=False, default='Pending')`
- `cleared_date = customer_db.Column(customer_db.Date, nullable=True)`
- `bank_txn_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('bank_transactions.id'), nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `created_by = customer_db.Column(customer_db.String(50), nullable=True)`
- `invoice_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('invoices.id'), nullable=True)`
- `purchase_invoice_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('purchase_invoices.id'), nullable=True)`
- `bank_account = customer_db.relationship('BankAccount')`
- `invoice = customer_db.relationship('Invoice', foreign_keys=[invoice_id])`
- `purchase_invoice = customer_db.relationship('PurchaseInvoice', foreign_keys=[purchase_invoice_id])`
### CompanyManifest (L955)
- `__tablename__ = 'company_manifests'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `manifest_id = customer_db.Column(customer_db.String(30), unique=True, nullable=False)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `shipper_client_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `shipper_client_name = customer_db.Column(customer_db.String(200), nullable=False)`
- `stock_item_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `total_boxes = customer_db.Column(customer_db.Integer, nullable=False, default=0)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `created_by = customer_db.Column(customer_db.String(50), nullable=True)`
- `status = Column(String(20), default='Pending', nullable=False)`
- `stock_deducted = Column(Boolean, default=False, nullable=False)`
- `generated_at = Column(DateTime, nullable=True)`
- `generated_by = Column(String(255), nullable=True)`
- `entries = customer_db.relationship('ManifestEntry', back_populates='manifest', cascade='all, delete-orphan')`
### ManifestEntry (L985)
- `__tablename__ = 'manifest_entries'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `manifest_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('company_manifests.id'), nullable=False)`
- `courier_name = customer_db.Column(customer_db.String(200), nullable=False)`
- `boxes = customer_db.Column(customer_db.Integer, nullable=False, default=0)`
- `docket_no = customer_db.Column(customer_db.String(100), nullable=True)`
- `docket_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `stock_item_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `stock_item_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `item_type = customer_db.Column(customer_db.String(50), nullable=True)`
- `status = customer_db.Column(customer_db.String(20), nullable=False, default='Pending')`
- `generated_at = customer_db.Column(customer_db.DateTime, nullable=True)`
- `generated_by = customer_db.Column(customer_db.String(255), nullable=True)`
- `dispatched_at = customer_db.Column(customer_db.DateTime, nullable=True)`
- `dispatched_by = customer_db.Column(customer_db.String(255), nullable=True)`
- `manifest = customer_db.relationship('CompanyManifest', back_populates='entries')`
### Expense (L1013)
- `__tablename__ = 'expenses'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `category = customer_db.Column(customer_db.String(100), nullable=False)`
- `description = customer_db.Column(customer_db.String(300), nullable=True)`
- `amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `payment_mode = customer_db.Column(customer_db.String(30), nullable=False, default='Cash')`
- `reference = customer_db.Column(customer_db.String(100), nullable=True)`
- `created_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
### WhatsAppLog (L1035)
- `__tablename__ = 'whatsapp_logs'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `template_key = customer_db.Column(customer_db.String(50), nullable=True)`
- `to_phone = customer_db.Column(customer_db.String(20), nullable=False)`
- `invoice_id = customer_db.Column(customer_db.String(30), nullable=True)`
- `manifest_id = customer_db.Column(customer_db.String(30), nullable=True)`
- `campaign_id = customer_db.Column(customer_db.String(50), nullable=True)`
- `status = customer_db.Column(customer_db.String(20), nullable=False, default='pending')`
- `provider = customer_db.Column(customer_db.String(20), nullable=True)`
- `provider_msg_id = customer_db.Column(customer_db.String(100), nullable=True)`
- `error_message = customer_db.Column(customer_db.Text, nullable=True)`
- `attempt_count = customer_db.Column(customer_db.Integer, nullable=False, default=0)`
- `manual_link = customer_db.Column(customer_db.Text, nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `sent_at = customer_db.Column(customer_db.DateTime, nullable=True)`
### DeliveryChallan (L1059)
- `__tablename__ = 'delivery_challans'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `challan_no = customer_db.Column(customer_db.String(30), unique=True, nullable=False)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `client_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `client_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `challan_date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `delivery_date = customer_db.Column(customer_db.Date, nullable=True)`
- `reference_order_no = customer_db.Column(customer_db.String(100), nullable=True)`
- `challan_type = customer_db.Column(customer_db.String(50), nullable=False, default='Delivery on Sale')`
- `transporter_name = customer_db.Column(customer_db.String(150), nullable=True)`
- `vehicle_no = customer_db.Column(customer_db.String(50), nullable=True)`
- `lr_no = customer_db.Column(customer_db.String(50), nullable=True)`
- `dispatch_from = customer_db.Column(customer_db.String(255), nullable=True)`
- `shipping_address = customer_db.Column(customer_db.Text, nullable=True)`
- `status = customer_db.Column(customer_db.String(50), nullable=False, default='Draft')`
- `stock_deducted = customer_db.Column(customer_db.Boolean, nullable=False, default=False)`
- `subtotal = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `tax_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `grand_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `terms = customer_db.Column(customer_db.Text, nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `invoiced_invoice_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `created_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `updated_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `updated_at = customer_db.Column(customer_db.DateTime, nullable=True, onupdate=datetime.utcnow)`
- `items = customer_db.relationship('DeliveryChallanItem', back_populates='challan', cascade='all, delete-orphan')`
### DeliveryChallanItem (L1103)
- `__tablename__ = 'delivery_challan_items'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `challan_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('delivery_challans.id'), nullable=False)`
- `stock_item_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `item_code = customer_db.Column(customer_db.String(50), nullable=True)`
- `item_name = customer_db.Column(customer_db.String(200), nullable=False)`
- `description = customer_db.Column(customer_db.String(300), nullable=True)`
- `hsn = customer_db.Column(customer_db.String(20), nullable=True)`
- `quantity = customer_db.Column(customer_db.Float, nullable=False, default=1.0)`
- `unit = customer_db.Column(customer_db.String(20), nullable=True, default='pcs')`
- `rate = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `discount_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `taxable_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `gst_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `cgst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `sgst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `igst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `total_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `challan = customer_db.relationship('DeliveryChallan', back_populates='items')`
### SalesOrder (L1131)
- `__tablename__ = 'sales_orders'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `order_no = customer_db.Column(customer_db.String(30), unique=True, nullable=False)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `client_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `client_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `order_date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `delivery_date = customer_db.Column(customer_db.Date, nullable=True)`
- `reference_no = customer_db.Column(customer_db.String(100), nullable=True)`
- `status = customer_db.Column(customer_db.String(50), nullable=False, default='Draft')`
- `subtotal = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `tax_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `cgst_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `sgst_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `igst_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `grand_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `terms = customer_db.Column(customer_db.Text, nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `updated_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `updated_at = customer_db.Column(customer_db.DateTime, nullable=True, onupdate=datetime.utcnow)`
- `items = customer_db.relationship('SalesOrderItem', back_populates='sales_order', cascade='all, delete-orphan')`
### SalesOrderItem (L1216)
- `__tablename__ = 'sales_order_items'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `sales_order_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('sales_orders.id'), nullable=False)`
- `stock_item_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `item_code = customer_db.Column(customer_db.String(50), nullable=True)`
- `item_name = customer_db.Column(customer_db.String(200), nullable=False)`
- `description = customer_db.Column(customer_db.String(300), nullable=True)`
- `hsn = customer_db.Column(customer_db.String(20), nullable=True)`
- `quantity = customer_db.Column(customer_db.Float, nullable=False, default=1.0)`
- `delivered_qty = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `unit = customer_db.Column(customer_db.String(20), nullable=True, default='pcs')`
- `rate = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `discount_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `taxable_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `gst_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `cgst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `sgst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `igst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `total_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `sales_order = customer_db.relationship('SalesOrder', back_populates='items')`
### PurchaseOrder (L1267)
- `__tablename__ = 'purchase_orders'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `po_number = customer_db.Column(customer_db.String(30), unique=True, nullable=False)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False)`
- `supplier_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `supplier_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `po_date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `expected_delivery_date = customer_db.Column(customer_db.Date, nullable=True)`
- `reference_no = customer_db.Column(customer_db.String(100), nullable=True)`
- `status = customer_db.Column(customer_db.String(50), nullable=False, default='Draft')`
- `subtotal = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `tax_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `cgst_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `sgst_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `igst_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `grand_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `terms = customer_db.Column(customer_db.Text, nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `updated_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `updated_at = customer_db.Column(customer_db.DateTime, nullable=True, onupdate=datetime.utcnow)`
- `items = customer_db.relationship('PurchaseOrderItem', back_populates='purchase_order', cascade='all, delete-orphan')`
### PurchaseOrderItem (L1306)
- `__tablename__ = 'purchase_order_items'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `purchase_order_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('purchase_orders.id'), nullable=False)`
- `stock_item_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `item_code = customer_db.Column(customer_db.String(50), nullable=True)`
- `item_name = customer_db.Column(customer_db.String(200), nullable=False)`
- `description = customer_db.Column(customer_db.String(300), nullable=True)`
- `hsn = customer_db.Column(customer_db.String(20), nullable=True)`
- `quantity = customer_db.Column(customer_db.Float, nullable=False, default=1.0)`
- `received_qty = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `unit = customer_db.Column(customer_db.String(20), nullable=True, default='pcs')`
- `rate = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `discount_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `taxable_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `gst_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `cgst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `sgst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `igst_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `total_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `purchase_order = customer_db.relationship('PurchaseOrder', back_populates='items')`
### OrderDepartment (L1338)
- `__tablename__ = 'order_departments'`
- `id = customer_db.Column(customer_db.String(50), primary_key=True)`
- `company_id = customer_db.Column(customer_db.String(50), nullable=False)`
- `name = customer_db.Column(customer_db.String(100), nullable=False)`
- `role_type = customer_db.Column(customer_db.String(50), nullable=False)`
- `description = customer_db.Column(customer_db.String(300), nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `is_active = customer_db.Column(customer_db.Boolean, default=True)`
### OrderFlow (L1361)
- `__tablename__ = 'order_flows'`
- `id = customer_db.Column(customer_db.String(50), primary_key=True)`
- `company_id = customer_db.Column(customer_db.String(50), nullable=False)`
- `client_id = customer_db.Column(customer_db.String(50), nullable=True)`
- `lead_id = customer_db.Column(customer_db.String(50), nullable=True)`
- `client_name = customer_db.Column(customer_db.String(200), nullable=False)`
- `client_phone = customer_db.Column(customer_db.String(50), nullable=True)`
- `client_email = customer_db.Column(customer_db.String(200), nullable=True)`
- `item_description = customer_db.Column(customer_db.Text, nullable=False)`
- `quantity = customer_db.Column(customer_db.Integer, default=1)`
- `unit_price = customer_db.Column(customer_db.Float, default=0.0)`
- `amount_due = customer_db.Column(customer_db.Float, default=0.0)`
- `amount_paid = customer_db.Column(customer_db.Float, default=0.0)`
- `status = customer_db.Column(customer_db.String(50), nullable=False, default='Order Created')`
- `priority = customer_db.Column(customer_db.String(20), default='normal')`
- `partner = customer_db.Column(customer_db.String(100), nullable=True)`
- `source = customer_db.Column(customer_db.String(100), nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `internal_notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_by = customer_db.Column(customer_db.String(200), nullable=False)`
- `created_by_dept = customer_db.Column(customer_db.String(100), nullable=True)`
- `taken_by = customer_db.Column(customer_db.String(200), nullable=True)`
- `approved_by = customer_db.Column(customer_db.String(200), nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `updated_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)`
### OrderFlowHistory (L1425)
- `__tablename__ = 'order_flow_history'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `order_id = customer_db.Column(customer_db.String(50), nullable=False)`
- `status = customer_db.Column(customer_db.String(50), nullable=False)`
- `note = customer_db.Column(customer_db.Text, nullable=True)`
- `changed_by = customer_db.Column(customer_db.String(200), nullable=False)`
- `changed_by_dept = customer_db.Column(customer_db.String(100), nullable=True)`
- `changed_by_role = customer_db.Column(customer_db.String(50), nullable=True)`
- `payment_mode = customer_db.Column(customer_db.String(100), nullable=True)`
- `payment_ref = customer_db.Column(customer_db.String(200), nullable=True)`
- `changed_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
### CRMContact (L1454)
- `__tablename__ = 'crm_contacts'`
- `id = customer_db.Column(customer_db.String(50), primary_key=True)`
- `company_id = customer_db.Column(customer_db.String(50), nullable=False)`
- `client_id = customer_db.Column(customer_db.String(50), nullable=False)`
- `name = customer_db.Column(customer_db.String(200), nullable=False)`
- `designation = customer_db.Column(customer_db.String(100), nullable=True)`
- `phone = customer_db.Column(customer_db.String(50), nullable=True)`
- `email = customer_db.Column(customer_db.String(200), nullable=True)`
- `is_primary = customer_db.Column(customer_db.Boolean, default=False)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
### CRMLead (L1484)
- `__tablename__ = 'crm_leads'`
- `id = customer_db.Column(customer_db.String(50), primary_key=True)`
- `company_id = customer_db.Column(customer_db.String(50), nullable=False)`
- `client_id = customer_db.Column(customer_db.String(50), nullable=False)`
- `client_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `title = customer_db.Column(customer_db.String(200), nullable=False)`
- `stage = customer_db.Column(customer_db.String(30), nullable=False, default='New')`
- `estimated_value = customer_db.Column(customer_db.Float, default=0.0)`
- `source = customer_db.Column(customer_db.String(100), nullable=True)`
- `expected_close_date = customer_db.Column(customer_db.Date, nullable=True)`
- `assigned_to = customer_db.Column(customer_db.String(200), nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `lost_reason = customer_db.Column(customer_db.String(300), nullable=True)`
- `converted_order_id = customer_db.Column(customer_db.String(50), nullable=True)`
- `created_by = customer_db.Column(customer_db.String(200), nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `updated_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)`
### CRMInteraction (L1526)
- `__tablename__ = 'crm_interactions'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(50), nullable=False)`
- `client_id = customer_db.Column(customer_db.String(50), nullable=False)`
- `lead_id = customer_db.Column(customer_db.String(50), nullable=True)`
- `type = customer_db.Column(customer_db.String(20), nullable=False)`
- `title = customer_db.Column(customer_db.String(200), nullable=True)`
- `summary = customer_db.Column(customer_db.Text, nullable=False)`
- `priority = customer_db.Column(customer_db.String(20), default='normal')`
- `status = customer_db.Column(customer_db.String(20), default='pending')`
- `due_date = customer_db.Column(customer_db.Date, nullable=True)`
- `follow_up_date = customer_db.Column(customer_db.Date, nullable=True)`
- `follow_up_done = customer_db.Column(customer_db.Boolean, default=False)`
- `created_by = customer_db.Column(customer_db.String(200), nullable=False)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
### CRMQuotation (L1564)
- `__tablename__ = 'crm_quotations'`
- `id = customer_db.Column(customer_db.String(50), primary_key=True)`
- `quote_number = customer_db.Column(customer_db.String(50), nullable=False)`
- `company_id = customer_db.Column(customer_db.String(50), nullable=False)`
- `client_id = customer_db.Column(customer_db.String(50), nullable=False)`
- `client_name = customer_db.Column(customer_db.String(200), nullable=True)`
- `lead_id = customer_db.Column(customer_db.String(50), nullable=True)`
- `title = customer_db.Column(customer_db.String(255), nullable=False)`
- `items_json = customer_db.Column(customer_db.Text, nullable=True)`
- `subtotal = customer_db.Column(customer_db.Float, default=0.0)`
- `cgst = customer_db.Column(customer_db.Float, default=0.0)`
- `sgst = customer_db.Column(customer_db.Float, default=0.0)`
- `total_amount = customer_db.Column(customer_db.Float, default=0.0)`
- `status = customer_db.Column(customer_db.String(30), default='Draft')`
- `valid_until = customer_db.Column(customer_db.Date, nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `terms = customer_db.Column(customer_db.Text, nullable=True)`
- `converted_order_id = customer_db.Column(customer_db.String(50), nullable=True)`
- `created_by = customer_db.Column(customer_db.String(200), nullable=False)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `updated_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)`
### CRMCommunicationLog (L1627)
- `__tablename__ = 'crm_comm_logs'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(50), nullable=False)`
- `client_id = customer_db.Column(customer_db.String(50), nullable=False)`
- `channel = customer_db.Column(customer_db.String(20), nullable=False)`
- `recipient = customer_db.Column(customer_db.String(200), nullable=False)`
- `subject = customer_db.Column(customer_db.String(255), nullable=True)`
- `message = customer_db.Column(customer_db.Text, nullable=False)`
- `sent_by = customer_db.Column(customer_db.String(200), nullable=False)`
- `status = customer_db.Column(customer_db.String(20), default='sent')`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
### CRMSetting (L1657)
- `__tablename__ = 'crm_settings'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(50), nullable=False)`
- `key = customer_db.Column(customer_db.String(100), nullable=False)`
- `value_json = customer_db.Column(customer_db.Text, nullable=True)`
- `updated_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
### CustomerVehicle (L1674)
- `__tablename__ = 'customer_vehicles'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `uuid = customer_db.Column(customer_db.String(36), unique=True, nullable=False, index=True)`
- `company_id = customer_db.Column(customer_db.String(50), nullable=False, index=True)`
- `client_id = customer_db.Column(customer_db.Integer, nullable=True, index=True)`
- `registration_no = customer_db.Column(customer_db.String(30), nullable=False, index=True)`
- `vehicle_type = customer_db.Column(customer_db.String(30), nullable=False, default='Four-Wheeler')`
- `brand = customer_db.Column(customer_db.String(100), nullable=False)`
- `model = customer_db.Column(customer_db.String(100), nullable=False)`
- `variant = customer_db.Column(customer_db.String(100), nullable=True)`
- `manufacturing_year = customer_db.Column(customer_db.Integer, nullable=True)`
- `fuel_type = customer_db.Column(customer_db.String(30), nullable=True, default='Petrol')`
- `colour = customer_db.Column(customer_db.String(50), nullable=True)`
- `vin_chassis_no = customer_db.Column(customer_db.String(60), nullable=True)`
- `engine_no = customer_db.Column(customer_db.String(60), nullable=True)`
- `odometer_reading = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `purchase_date = customer_db.Column(customer_db.Date, nullable=True)`
- `insurance_expiry = customer_db.Column(customer_db.Date, nullable=True)`
- `pollution_expiry = customer_db.Column(customer_db.Date, nullable=True)`
- `warranty_expiry = customer_db.Column(customer_db.Date, nullable=True)`
- `status = customer_db.Column(customer_db.String(30), nullable=False, default='Active')`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `updated_at = customer_db.Column(customer_db.DateTime, nullable=True, onupdate=datetime.utcnow)`
### WorkshopJobCard (L1741)
- `__tablename__ = 'workshop_job_cards'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `job_card_no = customer_db.Column(customer_db.String(40), unique=True, nullable=False, index=True)`
- `company_id = customer_db.Column(customer_db.String(50), nullable=False, index=True)`
- `branch_id = customer_db.Column(customer_db.String(50), nullable=True)`
- `vehicle_id = customer_db.Column(customer_db.Integer, nullable=False, index=True)`
- `client_id = customer_db.Column(customer_db.Integer, nullable=True, index=True)`
- `service_advisor = customer_db.Column(customer_db.String(100), nullable=True)`
- `assigned_technician = customer_db.Column(customer_db.String(100), nullable=True)`
- `bay_name = customer_db.Column(customer_db.String(50), nullable=True)`
- `job_type = customer_db.Column(customer_db.String(50), nullable=False, default='General Service')`
- `customer_complaints = customer_db.Column(customer_db.Text, nullable=True)`
- `initial_inspection_notes = customer_db.Column(customer_db.Text, nullable=True)`
- `fuel_level = customer_db.Column(customer_db.String(30), nullable=True, default='50%')`
- `current_odometer = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `estimated_delivery_date = customer_db.Column(customer_db.DateTime, nullable=True)`
- `priority = customer_db.Column(customer_db.String(20), nullable=False, default='Normal')`
- `status = customer_db.Column(customer_db.String(50), nullable=False, default='Checked In')`
- `two_wheeler_details = customer_db.Column(customer_db.Text, nullable=True)`
- `four_wheeler_details = customer_db.Column(customer_db.Text, nullable=True)`
- `total_parts_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `total_labour_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `tax_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `grand_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `invoice_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `created_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `updated_at = customer_db.Column(customer_db.DateTime, nullable=True, onupdate=datetime.utcnow)`
### WorkshopInspection (L1832)
- `__tablename__ = 'workshop_inspections'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `job_card_id = customer_db.Column(customer_db.Integer, nullable=False, index=True)`
- `vehicle_id = customer_db.Column(customer_db.Integer, nullable=False, index=True)`
- `inspector_name = customer_db.Column(customer_db.String(100), nullable=True)`
- `overall_condition = customer_db.Column(customer_db.String(30), default='Good')`
- `checklist_json = customer_db.Column(customer_db.Text, nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
### WorkshopEstimate (L1865)
- `__tablename__ = 'workshop_estimates'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `estimate_no = customer_db.Column(customer_db.String(40), unique=True, nullable=False, index=True)`
- `job_card_id = customer_db.Column(customer_db.Integer, nullable=False, index=True)`
- `company_id = customer_db.Column(customer_db.String(50), nullable=False)`
- `subtotal = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `tax_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `grand_total = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `status = customer_db.Column(customer_db.String(30), nullable=False, default='Draft')`
- `approval_mode = customer_db.Column(customer_db.String(50), nullable=True)`
- `approved_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `approved_at = customer_db.Column(customer_db.DateTime, nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `items = customer_db.relationship('WorkshopEstimateItem', backref='estimate', cascade='all, delete-orphan')`
### WorkshopEstimateItem (L1913)
- `__tablename__ = 'workshop_estimate_items'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `estimate_id = customer_db.Column(customer_db.Integer, customer_db.ForeignKey('workshop_estimates.id'), nullable=False)`
- `item_type = customer_db.Column(customer_db.String(30), nullable=False, default='Part')`
- `brand = customer_db.Column(customer_db.String(100), nullable=True)`
- `stock_item_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `description = customer_db.Column(customer_db.String(255), nullable=False)`
- `quantity = customer_db.Column(customer_db.Float, nullable=False, default=1.0)`
- `rate = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `discount_percent = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `gst_percent = customer_db.Column(customer_db.Float, nullable=False, default=18.0)`
- `total_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
### WorkshopServiceCatalog (L1945)
- `__tablename__ = 'workshop_service_catalog'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(20), nullable=False, index=True)`
- `name = customer_db.Column(customer_db.String(150), nullable=False)`
- `amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `inclusions = customer_db.Column(customer_db.Text, nullable=True)`
- `gst_percent = customer_db.Column(customer_db.Float, nullable=False, default=18.0)`
- `is_active = customer_db.Column(customer_db.Boolean, nullable=False, default=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `updated_at = customer_db.Column(customer_db.DateTime, nullable=True, onupdate=datetime.utcnow)`
### WorkshopTask (L1967)
- `__tablename__ = 'workshop_tasks'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `job_card_id = customer_db.Column(customer_db.Integer, nullable=False, index=True)`
- `task_name = customer_db.Column(customer_db.String(200), nullable=False)`
- `assigned_technician = customer_db.Column(customer_db.String(100), nullable=True)`
- `status = customer_db.Column(customer_db.String(30), default='Pending')`
- `start_time = customer_db.Column(customer_db.DateTime, nullable=True)`
- `end_time = customer_db.Column(customer_db.DateTime, nullable=True)`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
### WorkshopPartIssue (L1993)
- `__tablename__ = 'workshop_part_issues'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `job_card_id = customer_db.Column(customer_db.Integer, nullable=False, index=True)`
- `stock_item_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `item_type = customer_db.Column(customer_db.String(30), nullable=False, default='Part')`
- `brand = customer_db.Column(customer_db.String(100), nullable=True)`
- `part_name = customer_db.Column(customer_db.String(200), nullable=False)`
- `quantity_requested = customer_db.Column(customer_db.Float, nullable=False, default=1.0)`
- `quantity_issued = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `quantity_consumed = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `quantity_returned = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `unit_cost = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `technician = customer_db.Column(customer_db.String(100), nullable=True)`
- `issued_by = customer_db.Column(customer_db.String(100), nullable=True)`
- `status = customer_db.Column(customer_db.String(30), default='Requested')`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
### WorkshopQualityCheck (L2033)
- `__tablename__ = 'workshop_quality_checks'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `job_card_id = customer_db.Column(customer_db.Integer, nullable=False, index=True)`
- `inspector = customer_db.Column(customer_db.String(100), nullable=True)`
- `status = customer_db.Column(customer_db.String(30), default='Pending')`
- `checklist_json = customer_db.Column(customer_db.Text, nullable=True)`
- `rework_notes = customer_db.Column(customer_db.Text, nullable=True)`
- `verified_at = customer_db.Column(customer_db.DateTime, nullable=True)`
### VehicleServiceHistory (L2064)
- `__tablename__ = 'vehicle_service_history'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `vehicle_id = customer_db.Column(customer_db.Integer, nullable=False, index=True)`
- `job_card_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `service_date = customer_db.Column(customer_db.Date, nullable=False, default=date.today)`
- `odometer = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `services_performed = customer_db.Column(customer_db.Text, nullable=True)`
- `parts_replaced = customer_db.Column(customer_db.Text, nullable=True)`
- `technician = customer_db.Column(customer_db.String(100), nullable=True)`
- `invoice_amount = customer_db.Column(customer_db.Float, nullable=False, default=0.0)`
- `next_service_due_date = customer_db.Column(customer_db.Date, nullable=True)`
- `next_service_due_odometer = customer_db.Column(customer_db.Float, nullable=True)`
### WorkshopVehicleServicePlan (L2096)
- `__tablename__ = 'workshop_vehicle_service_plans'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(50), nullable=False, index=True)`
- `vehicle_id = customer_db.Column(customer_db.Integer, nullable=False, unique=True, index=True)`
- `interval_days = customer_db.Column(customer_db.Integer, nullable=False, default=180)`
- `interval_km = customer_db.Column(customer_db.Float, nullable=False, default=10000.0)`
- `updated_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)`
### ServiceReminder (L2116)
- `__tablename__ = 'service_reminders'`
- `id = customer_db.Column(customer_db.Integer, primary_key=True, autoincrement=True)`
- `company_id = customer_db.Column(customer_db.String(50), nullable=False, index=True)`
- `vehicle_id = customer_db.Column(customer_db.Integer, nullable=False, index=True)`
- `client_id = customer_db.Column(customer_db.Integer, nullable=True)`
- `reminder_type = customer_db.Column(customer_db.String(50), default='Next Periodic Service')`
- `due_date = customer_db.Column(customer_db.Date, nullable=False)`
- `due_odometer = customer_db.Column(customer_db.Float, nullable=True)`
- `status = customer_db.Column(customer_db.String(20), default='Pending')`
- `notes = customer_db.Column(customer_db.Text, nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
### CRMProject (L2154)
- `__tablename__ = 'crm_projects'`
- `id = customer_db.Column(customer_db.String(50), primary_key=True)`
- `company_id = customer_db.Column(customer_db.String(50), nullable=False, index=True)`
- `client_id = customer_db.Column(customer_db.String(50), nullable=True)`
- `name = customer_db.Column(customer_db.String(200), nullable=False)`
- `description = customer_db.Column(customer_db.Text, nullable=True)`
- `owner = customer_db.Column(customer_db.String(200), nullable=True)`
- `status = customer_db.Column(customer_db.String(30), nullable=False, default='Planned')`
- `due_date = customer_db.Column(customer_db.Date, nullable=True)`
- `created_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow)`
- `updated_at = customer_db.Column(customer_db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)`

## db folder/app_db_config_snippet.py


## db folder/db_router.py


## db folder/migration_routes.py

- L72 `migrations`: `app.route('/migrations'); login_required; super_admin_required`. Referenced names: Company, Exception
- L129 `run_migration`: `app.route('/migrations/run', methods=['POST']); login_required; super_admin_required`. Referenced names: Company, Exception
- L388 `migration_history_all`: `app.route('/migrations/history'); login_required; super_admin_required`. Referenced names: Company, Exception
- L440 `migration_history`: `app.route('/migrations/history/<company_id>'); login_required; super_admin_required`. Referenced names: 

## db_router.py


## erp_routes.py

- L30 `delivery_challan_list`: `app.route('/delivery-challans'); login_required; require_permission('delivery_challans', 'view')`. Referenced names: DeliveryChallan
- L62 `delivery_challan_new`: `app.route('/delivery-challan/new', methods=['GET', 'POST']); login_required; require_permission('delivery_challans', 'create')`. Referenced names: Client, Company, DeliveryChallan, DeliveryChallanItem, StockItem
- L209 `delivery_challan_view`: `app.route('/delivery-challan/<int:challan_id>'); login_required; require_permission('delivery_challans', 'view')`. Referenced names: Company, DeliveryChallan
- L230 `delivery_challan_edit`: `app.route('/delivery-challan/<int:challan_id>/edit', methods=['GET', 'POST']); login_required; require_permission('delivery_challans', 'edit')`. Referenced names: Client, Company, DeliveryChallan, DeliveryChallanItem, StockItem
- L347 `delivery_challan_pdf`: `app.route('/delivery-challan/<int:challan_id>/pdf'); login_required`. Referenced names: Company, DeliveryChallan
- L357 `delivery_challan_convert_to_invoice`: `app.route('/delivery-challan/<int:challan_id>/convert-to-invoice'); login_required; require_permission('customer_invoices', 'create')`. Referenced names: CustomerInvoice, CustomerInvoiceItem, DeliveryChallan
- L421 `delivery_challan_delete`: `app.route('/delivery-challan/<int:challan_id>/delete', methods=['POST']); login_required; require_permission('delivery_challans', 'delete')`. Referenced names: DeliveryChallan
- L436 `sales_order_list`: `app.route('/sales-orders'); login_required; require_permission('sales_orders', 'view')`. Referenced names: SalesOrder
- L467 `sales_order_new`: `app.route('/sales-order/new', methods=['GET', 'POST']); login_required; require_permission('sales_orders', 'create')`. Referenced names: Client, Company, SalesOrder, SalesOrderItem, StockItem
- L600 `sales_order_view`: `app.route('/sales-order/<int:order_id>'); login_required; require_permission('sales_orders', 'view')`. Referenced names: Company, SalesOrder
- L621 `sales_order_edit`: `app.route('/sales-order/<int:order_id>/edit', methods=['GET', 'POST']); login_required; require_permission('sales_orders', 'edit')`. Referenced names: Client, Company, SalesOrder, SalesOrderItem, StockItem
- L738 `sales_order_convert_to_challan`: `app.route('/sales-order/<int:order_id>/convert-to-challan'); login_required; require_permission('delivery_challans', 'create')`. Referenced names: DeliveryChallan, DeliveryChallanItem, SalesOrder, StockItem
- L810 `sales_order_convert_to_invoice`: `app.route('/sales-order/<int:order_id>/convert-to-invoice'); login_required; require_permission('customer_invoices', 'create')`. Referenced names: CustomerInvoice, CustomerInvoiceItem, SalesOrder
- L872 `sales_order_delete`: `app.route('/sales-order/<int:order_id>/delete', methods=['POST']); login_required; require_permission('sales_orders', 'delete')`. Referenced names: SalesOrder
- L888 `purchase_order_list`: `app.route('/purchase-orders'); login_required; require_permission('purchase_orders', 'view')`. Referenced names: PurchaseOrder
- L919 `purchase_order_new`: `app.route('/purchase-order/new', methods=['GET', 'POST']); login_required; require_permission('purchase_orders', 'create')`. Referenced names: Company, PurchaseOrder, PurchaseOrderItem, StockItem, Supplier, ValueError
- L1106 `purchase_order_view`: `app.route('/purchase-order/<int:po_id>'); login_required; require_permission('purchase_orders', 'view')`. Referenced names: Company, PurchaseOrder
- L1123 `purchase_order_edit`: `app.route('/purchase-order/<int:po_id>/edit', methods=['GET', 'POST']); login_required; require_permission('purchase_orders', 'edit')`. Referenced names: Company, PurchaseOrder, PurchaseOrderItem, StockItem, Supplier, ValueError
- L1274 `purchase_order_delete`: `app.route('/purchase-order/<int:po_id>/delete', methods=['POST']); login_required; require_permission('purchase_orders', 'delete')`. Referenced names: PurchaseOrder
- L1287 `purchase_order_convert_to_bill`: `app.route('/purchase-order/<int:po_id>/convert-to-bill'); login_required; require_permission('purchase_invoices', 'create')`. Referenced names: PurchaseInvoice, PurchaseInvoiceItem, PurchaseOrder, StockItem

## module_access.py


## ocr_parser.py


## order_erp_routes.py

- L108 `order_erp_view`: `app.route('/order-erp', endpoint='order_erp_view'); app.route('/order-erp/dashboard', endpoint='order_erp_dashboard'); login_required`. Referenced names: STATUS_FLOW
- L117 `api_order_stats`: `app.route('/api/order-erp/stats', methods=['GET']); login_required`. Referenced names: Client, OrderFlow, ROLE_VISIBLE_STATUSES, SalesOrder
- L179 `api_order_list_create`: `app.route('/api/order-erp/orders', methods=['GET', 'POST']); login_required`. Referenced names: Exception, OrderFlow, OrderFlowHistory, ROLE_VISIBLE_STATUSES, STATUS_FLOW
- L295 `api_order_detail`: `app.route('/api/order-erp/orders/<order_id>', methods=['GET', 'DELETE']); login_required`. Referenced names: OrderFlow, OrderFlowHistory, ROLE_TRANSITIONS, STATUS_FLOW
- L332 `api_order_status_update`: `app.route('/api/order-erp/orders/<order_id>/status', methods=['PUT']); login_required`. Referenced names: OrderFlow, OrderFlowHistory, ROLE_TRANSITIONS, STATUS_FLOW
- L393 `api_order_credit_check`: `app.route('/api/order-erp/orders/<order_id>/credit-check', methods=['POST']); login_required`. Referenced names: OrderFlow, OrderFlowHistory
- L443 `api_order_partners`: `app.route('/api/order-erp/partners', methods=['GET']); login_required`. Referenced names: Supplier
- L459 `api_order_departments`: `app.route('/api/order-erp/departments', methods=['GET', 'POST']); login_required`. Referenced names: OrderDepartment
- L500 `api_sales_orders`: `app.route('/api/order-erp/sales-orders', methods=['GET', 'POST']); login_required`. Referenced names: Client, SalesOrder, SalesOrderItem
- L658 `api_sales_order_detail`: `app.route('/api/order-erp/sales-orders/<int:order_id>', methods=['GET']); login_required`. Referenced names: SalesOrder
- L668 `api_sales_order_to_production`: `app.route('/api/order-erp/sales-orders/<int:order_id>/send-to-production', methods=['POST']); login_required`. Referenced names: OrderFlow, OrderFlowHistory, SalesOrder
- L743 `api_order_erp_clients`: `app.route('/api/order-erp/clients', methods=['GET', 'POST']); login_required`. Referenced names: Client, OrderFlow, SalesOrder
- L805 `api_order_erp_client_details`: `app.route('/api/order-erp/clients/<int:client_id>/details', methods=['GET']); login_required`. Referenced names: Client, OrderFlow, SalesOrder
- L840 `api_order_erp_products`: `app.route('/api/order-erp/products', methods=['GET']); login_required`. Referenced names: StockItem

## permissions.py


## platform_bootstrap.py


## platform_models.py

### SubscriptionPlan (L22)
- `__tablename__ = 'subscription_plans'`
- `id = db.Column(db.String(20), primary_key=True)`
- `name = db.Column(db.String(100), nullable=False)`
- `price = db.Column(db.String(50), nullable=False)`
- `price_1yr = db.Column(db.String(50), nullable=True)`
- `price_3yr = db.Column(db.String(50), nullable=True)`
- `price_lifetime = db.Column(db.String(50), nullable=True)`
- `max_companies = db.Column(db.String(20), nullable=False)`
- `max_users = db.Column(db.String(20), nullable=False)`
- `features = db.Column(db.Text, nullable=True)`
- `companies = db.relationship('Company', back_populates='plan_obj')`
- `registered_users = db.relationship('RegisteredUser', back_populates='plan_obj')`
### PaymentTransaction (L43)
- `__tablename__ = 'payment_transactions'`
- `id = db.Column(db.Integer, primary_key=True, autoincrement=True)`
- `transaction_id = db.Column(db.String(50), unique=True, nullable=False)`
- `user_email = db.Column(db.String(255), nullable=False)`
- `company_id = db.Column(db.String(20), nullable=True)`
- `plan_id = db.Column(db.String(20), nullable=False)`
- `duration = db.Column(db.String(20), nullable=False, default='1_year')`
- `amount = db.Column(db.Numeric(10, 2), nullable=False)`
- `currency = db.Column(db.String(10), nullable=False, default='INR')`
- `razorpay_order_id = db.Column(db.String(100), nullable=True)`
- `razorpay_payment_id = db.Column(db.String(100), nullable=True)`
- `razorpay_signature = db.Column(db.String(255), nullable=True)`
- `status = db.Column(db.String(20), nullable=False, default='created')`
- `error_reason = db.Column(db.Text, nullable=True)`
- `created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)`
### RegisteredUser (L66)
- `__tablename__ = 'registered_users'`
- `id = db.Column(db.Integer, primary_key=True, autoincrement=True)`
- `user_id = db.Column(db.String(20), unique=True, nullable=False)`
- `email = db.Column(db.String(255), unique=True, nullable=False)`
- `password_hash = db.Column(db.String(255), nullable=False)`
- `full_name = db.Column(db.String(150), nullable=False)`
- `phone = db.Column(db.String(20), nullable=True)`
- `address = db.Column(db.String(300), nullable=True)`
- `role = db.Column(db.String(50), nullable=False, default='owner')`
- `subscription_plan = db.Column(db.String(20), db.ForeignKey('subscription_plans.id'), nullable=True)`
- `created_at = db.Column(db.Date, nullable=False, default=date.today)`
- `is_active = db.Column(db.Boolean, nullable=False, default=True)`
- `must_change_password = db.Column(db.Boolean, nullable=False, default=True)`
- `email_verified = db.Column(db.Boolean, nullable=False, default=False)`
- `payment_status = db.Column(db.String(20), nullable=False, default='pending')`
- `amount_total = db.Column(db.Numeric(10, 2), nullable=True)`
- `amount_paid = db.Column(db.Numeric(10, 2), nullable=False, default=0)`
- `registered_by = db.Column(db.String(255), nullable=True)`
- `registered_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)`
- `custom_max_companies = db.Column(db.Integer, nullable=True)`
- `custom_max_users = db.Column(db.Integer, nullable=True)`
- `custom_yearly_amount = db.Column(db.Numeric(10, 2), nullable=True)`
- `plan_duration = db.Column(db.String(20), nullable=False, default='1_year')`
- `maintenance_due_date = db.Column(db.Date, nullable=True)`
- `last_maintenance_paid_at = db.Column(db.Date, nullable=True)`
- `last_maintenance_prompt_date = db.Column(db.Date, nullable=True)`
- `plan_obj = db.relationship('SubscriptionPlan', back_populates='registered_users')`
- `companies = db.relationship('Company', back_populates='owner', foreign_keys='Company.owner_email', primaryjoin='RegisteredUser.email == Company.owner_email')`
### BackupRecord (L123)
- `__tablename__ = 'backup_records'`
- `id = db.Column(db.Integer, primary_key=True, autoincrement=True)`
- `backup_id = db.Column(db.String(50), unique=True, nullable=False)`
- `company_id = db.Column(db.String(20), db.ForeignKey('companies.company_id'), nullable=False)`
- `backup_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)`
- `backup_file_path = db.Column(db.String(500), nullable=False)`
- `file_size_mb = db.Column(db.Float, nullable=False)`
- `file_hash = db.Column(db.String(64), nullable=False)`
- `status = db.Column(db.String(20), nullable=False, default='completed')`
- `cloud_backup = db.Column(db.Boolean, default=False)`
- `cloud_location = db.Column(db.String(500), nullable=True)`
- `restore_date = db.Column(db.DateTime, nullable=True)`
- `restored_by = db.Column(db.String(100), nullable=True)`
- `created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)`
- `backup_from_date = db.Column(db.Date, nullable=True)`
- `backup_to_date = db.Column(db.Date, nullable=True)`
- `company = db.relationship('Company', backref='backups')`
### BackupSchedule (L148)
- `__tablename__ = 'backup_schedules'`
- `id = db.Column(db.Integer, primary_key=True, autoincrement=True)`
- `company_id = db.Column(db.String(20), db.ForeignKey('companies.company_id'), nullable=False, unique=True)`
- `frequency = db.Column(db.String(20), nullable=False, default='daily')`
- `time_of_day = db.Column(db.String(10), nullable=False, default='00:00')`
- `retention_days = db.Column(db.Integer, nullable=False, default=30)`
- `upload_to_cloud = db.Column(db.Boolean, default=False)`
- `last_backup = db.Column(db.DateTime, nullable=True)`
- `next_backup = db.Column(db.DateTime, nullable=True)`
- `is_active = db.Column(db.Boolean, default=True)`
- `created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)`
- `updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.utcnow)`
- `company = db.relationship('Company', backref='backup_schedule')`
### Company (L169)
- `__tablename__ = 'companies'`
- `id = db.Column(db.Integer, primary_key=True, autoincrement=True)`
- `company_id = db.Column(db.String(20), unique=True, nullable=False)`
- `company_name = db.Column(db.String(200), nullable=False)`
- `owner_email = db.Column(db.String(255), db.ForeignKey('registered_users.email'), nullable=False)`
- `subscription_plan = db.Column(db.String(20), db.ForeignKey('subscription_plans.id'), nullable=True)`
- `plan_duration = db.Column(db.String(20), nullable=False, default='1_year')`
- `custom_yearly_amount = db.Column(db.Numeric(10, 2), nullable=True)`
- `subscription_start = db.Column(db.Date, nullable=True)`
- `subscription_end = db.Column(db.Date, nullable=True)`
- `maintenance_due_date = db.Column(db.Date, nullable=True)`
- `last_maintenance_paid_at = db.Column(db.Date, nullable=True)`
- `max_companies_allowed = db.Column(db.String(20), nullable=True)`
- `max_users_per_company = db.Column(db.String(20), nullable=True)`
- `gst_number = db.Column(db.String(20), nullable=True)`
- `logo_filename = db.Column(db.String(255), nullable=True)`
- `address = db.Column(db.String(300), nullable=True)`
- `phone = db.Column(db.String(100), nullable=True)`
- `mobile = db.Column(db.String(20), nullable=True)`
- `slogan = db.Column(db.String(150), nullable=True)`
- `website = db.Column(db.String(200), nullable=True)`
- `email = db.Column(db.String(200), nullable=True)`
- `extra_info = db.Column(db.String(300), nullable=True)`
- `logo = db.Column(db.String(300), nullable=True)`
- `awb_prefix = db.Column(db.String(10), nullable=False, default='AHL')`
- `awb_start = db.Column(db.BigInteger, nullable=False, default=81000)`
- `public_slug = db.Column(db.String(50), unique=True, nullable=True, index=True)`
- `created_at = db.Column(db.Date, nullable=False, default=date.today)`
- `is_active = db.Column(db.Boolean, nullable=False, default=True)`
- `is_gst_registered = db.Column(db.Boolean, nullable=False, default=True)`
- `gst_number = db.Column(db.String(20), nullable=True, unique=True)`
- `terms_footer = db.Column(db.Text, nullable=True)`
- `terms_annexure = db.Column(db.Text, nullable=True)`
- `show_terms_customer_invoice = db.Column(db.Boolean, nullable=False, default=True)`
- `show_terms_awb_invoice = db.Column(db.Boolean, nullable=False, default=True)`
- `show_terms_performa_invoice = db.Column(db.Boolean, nullable=False, default=True)`
- `show_terms_box_label = db.Column(db.Boolean, nullable=False, default=True)`
- `show_terms_shipping_label = db.Column(db.Boolean, nullable=False, default=True)`
- `show_address_customer_invoice = db.Column(db.Boolean, nullable=False, default=True)`
- `show_address_awb_invoice = db.Column(db.Boolean, nullable=False, default=True)`
- `show_address_performa_invoice = db.Column(db.Boolean, nullable=False, default=True)`
- `show_address_box_label = db.Column(db.Boolean, nullable=False, default=True)`
- `show_address_shipping_label = db.Column(db.Boolean, nullable=False, default=True)`
- `invoice_template = db.Column(db.String(20), default='classic', nullable=False)`
- `credit_limit_action = db.Column(db.String(10), nullable=False, default='warn')`
- `currency = db.Column(db.String(10), nullable=False, default='INR')`
- `currency_symbol = db.Column(db.String(10), nullable=False, default='₹')`
- `country = db.Column(db.String(100), nullable=False, default='India')`
- `tax_regime = db.Column(db.String(50), nullable=False, default='GST')`
- `tax_id_label = db.Column(db.String(50), nullable=False, default='GSTIN')`
- `hidden_on_mobile = db.Column(db.Boolean, nullable=False, default=False)`
- `storage_type = db.Column(db.String(10), nullable=False, default='local')`
- `data_db_uri = db.Column(db.String(500), nullable=True)`
- `whatsapp_provider = db.Column(db.String(20), nullable=True)`
- `whatsapp_phone_id = db.Column(db.String(50), nullable=True)`
- `whatsapp_base_url = db.Column(db.String(500), nullable=True)`
- `whatsapp_token = db.Column(db.Text, nullable=True)`
- `whatsapp_business_no = db.Column(db.String(20), nullable=True)`
- `whatsapp_enabled = db.Column(db.Boolean, nullable=False, default=False)`
- `whatsapp_template_delivery = db.Column(db.String(100), nullable=True)`
- `whatsapp_template_carrier_update = db.Column(db.String(100), nullable=True)`
- `show_manifest_checkboxes = db.Column(db.Boolean, default=True)`
- `sms_provider = db.Column(db.String(20), nullable=True)`
- `sms_api_key = db.Column(db.Text, nullable=True)`
- `sms_sender_id = db.Column(db.String(20), nullable=True)`
- `sms_enabled = db.Column(db.Boolean, nullable=False, default=False)`
- `accounts_whatsapp_number = db.Column(db.String(20), nullable=True)`
- `extra_notify_number_1 = db.Column(db.String(20), nullable=True)`
- `extra_notify_number_2 = db.Column(db.String(20), nullable=True)`
- `whatsapp_api_key = db.Column(db.Text, nullable=True)`
- `whatsapp_template_generate = db.Column(db.String(100), nullable=True)`
- `whatsapp_template_update = db.Column(db.String(100), nullable=True)`
- `owner = db.relationship('RegisteredUser', back_populates='companies', foreign_keys=[owner_email])`
- `plan_obj = db.relationship('SubscriptionPlan', back_populates='companies')`
### WhatsAppTemplate (L323)
- `__tablename__ = 'whatsapp_templates'`
- `id = db.Column(db.Integer, primary_key=True, autoincrement=True)`
- `company_id = db.Column(db.String(20), db.ForeignKey('companies.company_id'), nullable=False)`
- `template_key = db.Column(db.String(50), nullable=False)`
- `template_name = db.Column(db.String(100), nullable=False)`
- `param_count = db.Column(db.Integer, nullable=False, default=0)`
- `language_code = db.Column(db.String(10), nullable=False, default='en')`
- `is_active = db.Column(db.Boolean, nullable=False, default=True)`
- `created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)`
- `header_type = db.Column(db.String(20), nullable=False, default='none')`
- `variables_json = db.Column(db.Text, nullable=True)`
- `company = db.relationship('Company')`
- `__table_args__ = (db.UniqueConstraint('company_id', 'template_key', name='uq_company_template_key'),)`
### WhatsAppProviderDefinition (L351)
- `__tablename__ = 'whatsapp_provider_definitions'`
- `id = db.Column(db.Integer, primary_key=True, autoincrement=True)`
- `provider_code = db.Column(db.String(30), unique=True, nullable=False)`
- `provider_name = db.Column(db.String(100), nullable=False)`
- `method = db.Column(db.String(10), nullable=False, default='POST')`
- `url_template = db.Column(db.Text, nullable=False)`
- `headers_template = db.Column(db.Text, nullable=False)`
- `body_template = db.Column(db.Text, nullable=False)`
- `body_encoding = db.Column(db.String(10), nullable=False, default='json')`
- `success_status_codes = db.Column(db.String(50), nullable=False, default='200,201,202')`
- `success_path = db.Column(db.String(150), nullable=True)`
- `success_expected_value = db.Column(db.String(100), nullable=True)`
- `message_id_path = db.Column(db.String(150), nullable=True)`
- `error_path = db.Column(db.String(150), nullable=True)`
- `allowed_hosts = db.Column(db.String(300), nullable=True)`
- `timeout_seconds = db.Column(db.Integer, nullable=False, default=30)`
- `is_active = db.Column(db.Boolean, nullable=False, default=True)`
- `created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)`
### CompanyWhatsAppConfig (L385)
- `__tablename__ = 'company_whatsapp_configs'`
- `id = db.Column(db.Integer, primary_key=True, autoincrement=True)`
- `company_id = db.Column(db.String(20), db.ForeignKey('companies.company_id'), nullable=False, unique=True)`
- `provider_definition_id = db.Column(db.Integer, db.ForeignKey('whatsapp_provider_definitions.id'), nullable=False)`
- `credentials_encrypted = db.Column(db.Text, nullable=False)`
- `extra_config_encrypted = db.Column(db.Text, nullable=True)`
- `template_generate = db.Column(db.String(100), nullable=True)`
- `template_update = db.Column(db.String(100), nullable=True)`
- `template_delivery = db.Column(db.String(100), nullable=True)`
- `enabled = db.Column(db.Boolean, nullable=False, default=True)`
- `created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)`
- `updated_at = db.Column(db.DateTime, nullable=True, onupdate=datetime.utcnow)`
- `company = db.relationship('Company')`
- `provider_definition = db.relationship('WhatsAppProviderDefinition')`
### TrackingIndex (L416)
- `__tablename__ = 'tracking_index'`
- `id = db.Column(db.Integer, primary_key=True, autoincrement=True)`
- `docket_no = db.Column(db.String(100), unique=True, nullable=False, index=True)`
- `company_id = db.Column(db.String(20), nullable=False, index=True)`
- `carrier = db.Column(db.String(100), nullable=True)`
- `updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)`
### CarrierTrackingConfig (L428)
- `__tablename__ = 'carrier_tracking_configs'`
- `id = db.Column(db.Integer, primary_key=True, autoincrement=True)`
- `carrier_key = db.Column(db.String(50), unique=True, nullable=False)`
- `display_name = db.Column(db.String(100), nullable=False)`
- `tracking_url_template = db.Column(db.String(500), nullable=False)`
- `is_active = db.Column(db.Boolean, nullable=False, default=True)`
### CompanyApiKey (L439)
- `__tablename__ = 'company_api_keys'`
- `id = db.Column(db.Integer, primary_key=True, autoincrement=True)`
- `company_id = db.Column(db.String(20), nullable=False, index=True)`
- `key_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)`
- `key_prefix = db.Column(db.String(16), nullable=False)`
- `label = db.Column(db.String(100), nullable=True)`
- `allowed_origin = db.Column(db.String(255), nullable=True)`
- `is_active = db.Column(db.Boolean, nullable=False, default=True)`
- `created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)`
- `last_used_at = db.Column(db.DateTime, nullable=True)`
### PlatformAccessRule (L477)
- `__tablename__ = 'platform_access_rules'`
- `scope = db.Column(db.String(20), primary_key=True)`
- `target = db.Column(db.String(150), primary_key=True)`
- `overrides = db.Column(db.JSON, nullable=False, default=dict)`
- `trial_end = db.Column(db.Date, nullable=True)`
- `revision = db.Column(db.Integer, nullable=False, default=0)`
- `updated_by = db.Column(db.String(255), nullable=True)`
- `updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)`
### PlatformAccessAudit (L489)
- `__tablename__ = 'platform_access_audit'`
- `id = db.Column(db.Integer, primary_key=True, autoincrement=True)`
- `scope = db.Column(db.String(20), nullable=False, index=True)`
- `target = db.Column(db.String(150), nullable=False, index=True)`
- `actor = db.Column(db.String(255), nullable=False)`
- `before_json = db.Column(db.JSON, nullable=False)`
- `after_json = db.Column(db.JSON, nullable=False)`
- `reason = db.Column(db.String(1000), nullable=True)`
- `created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)`

## scratch/admin_access_preview.py

- L16 `preview`: `app.route('/preview')`. Referenced names: Company, RegisteredUser

## scratch/check_invs.py


## scratch/check_july_types.py


## scratch/check_sqlite.py


## scratch/test_rec_intel.py

### MockFilters (L10)

## scratch/test_rec_live.py


## scratch/verify_bi_receivables.py

### MockFilters (L12)

## scratch_test_rec.py


## seed_carrier_config.py


## services/invoice_pdf_generator.py

### InvoicePDFGenerator (L14)

## status_timeline.py

- L53 `public_tracking`: `app.route('/track/<company_slug>', methods=['GET', 'POST']); limiter.limit('10 per minute')`. Referenced names: Company
- L68 `track_magic_link`: `app.route('/t/<company_id>/<docket_no>'); limiter.limit('30 per minute')`. Referenced names: Company
- L79 `public_tracking_generic`: `app.route('/track', methods=['GET', 'POST']); limiter.limit('10 per minute')`. Referenced names: TrackingIndex

## tasks.py


## tests/test_crm_workspace.py

### CRMWorkspaceTests (L12)

## tests/test_platform_access.py

### PlatformAccessTests (L13)

## tests/test_super_admin_auth.py

### SuperAdminAuthTests (L11)

## utils/ai_assistant.py

### LogisticsAIAssistant (L37)
- `APP_NAME = 'Qiyadah'`
- `APP_MAKER = 'Qiyadah'`
- `APP_BUILD_DATE = '10 July 2026'`
- `APP_INFO_RESPONSE = f'This platform is {APP_NAME}, built by {APP_MAKER}. It was released on {APP_BUILD_DATE}.'`
- `OWNER_INFO_RESPONSE = "I'm not able to share ownership or personal contact details for this platform. For business or support enquiries, please use the contact details provided within the app itself."`
- `_OWNER_SIGNALS = ['who is the owner', 'who owns this', 'owner of this app', 'owner name', 'who is behind this', 'contact owner', 'owner details', 'owner contact', 'who is ibrahim', "developer's name", 'developer contact', 'developer phone', 'developer email', 'developer number']`
- `_APP_INFO_SIGNALS = ['who made this app', 'who developed this', 'who is the developer', 'who built this', 'which company made this', 'who created this app', 'app made by', 'about this app', 'app info', 'when was this app made', 'who designed this app', 'who owns qiyadah', 'who owns magnustic']`
- `_GREETING_EXACT = {'hi', 'hii', 'hiii', 'hiiii', 'hello', 'helo', 'hey', 'heya', 'hy', 'yo', 'sup', 'hola', 'good morning', 'good afternoon', 'good evening', 'gm', 'ge', 'namaste'}`
- `GREETING_RESPONSES = ["Hi! I'm Qiyadah AI. Welcome to Qiyadah. I can help you with sales, purchases, invoices, inventory, shipments, GST, customer and supplier accounts, cash, bank balances, expenses, and business reports. What would you like to know?", "Hello! I'm Qiyadah AI. Welcome to Qiyadah. Whether you need today's sales, outstanding payments, stock status, shipment tracking, GST reports, customer balances, or business insights, I'm here to help. How can I assist you today?", "Welcome! I'm Qiyadah AI. Welcome to Qiyadah. Ask me anything about your business—from invoices and purchases to logistics, manifests, inventory, banking, expenses, profits, and analytics. What would you like to explore?", "Hi there! I'm Qiyadah AI. Welcome to Qiyadah. I can answer questions about your sales, purchases, customers, suppliers, inventory, shipments, GST, finances, and overall business performance. What can I help you with today?", "Hello! I'm Qiyadah AI. Welcome to Qiyadah, your intelligent business assistant. Try asking things like 'Show today's sales', 'What's my GST payable?', 'Who owes me money?', or 'What is my total purchase this month?'."]`
- `EXPLAIN_SYSTEM = 'You are Qiyadah AI, an assistant for a logistics/courier company\'s\nERP system in India. You are currently answering for ONE specific company only —\nthe JSON data you are given has already been fetched from that company\'s own\nisolated database. It contains nothing from any other company. Never claim to\nhave, or offer to fetch, data belonging to any other company.\n\nYour ONLY job is to explain the JSON data in plain English. The JSON is 100%\naccurate — never contradict it, never invent numbers, never fill in a figure\nthat isn\'t present in the JSON.\n\nToday\'s date is {today_date}. Use this for date comparisons (overdue, expiring).\n\nRules:\n- Summarise in 2-4 plain English sentences\n- Use ₹ for all money values\n- If a "found": false field is present, say clearly that nothing matched\n- Lead with the most important risk (overdue payment, low stock, pending manifest)\n- If a list/count is 0 or empty, say so plainly — don\'t skip it\n- DO NOT output JSON, bullet points, markdown, or code blocks\n- DO NOT guess or round figures beyond what\'s given\n- Keep it under 5 sentences\n'`
- `GENERAL_SYSTEM = 'You are Qiyadah AI, an intelligent, helpful assistant for a logistics/courier\ncompany\'s ERP system in India. You answer questions about:\n\n1. Questions about THIS company\'s own records — these are already answered with\n   real DB data before this message; you are not doing that here.\n2. How to use the ERP features & settings:\n   - Giving access to employees: Settings ⚙️ -> Manage Employees/Users -> "+ Add Employee" -> enter name, email, password, and select role (Employee, Accountant, Manager) -> configure permissions under Settings -> Role Permissions.\n   - Changing password: Top-right user avatar menu -> "Change Password" -> enter current and new password -> Update.\n   - Company Settings: Settings ⚙️ -> Company Profile -> edit company name, GSTIN, registered address, logo, invoice prefixes, terms & conditions, and bank details.\n   - Plans & Upgrades: Settings ⚙️ -> Subscription & Billing -> select plan (Starter, Professional, Enterprise, Lifetime) -> click Upgrade Plan to pay via Razorpay/UPI.\n   - Creating Bookings (AWB), Customer Aggregate Invoices, Purchase Invoices, Manifests, Cash/Bank receipts, and Price Lists.\n3. General accounting, GST (CGST/SGST/IGST, reverse charge, HSN codes, e-way bills), logistics, and freight taxation concepts.\n\nRules:\n- Give clear, helpful, step-by-step answers for how-to questions.\n- Use ₹ for Indian currency context.\n- Keep answers structured with bullet points or numbered steps when describing a process.\n- NEVER fabricate company-specific financial numbers on this path.\n- NEVER reveal personal contact details of developers/owners.\n'`
- `_RECORD_SIGNALS = ['my ', 'our ', 'we owe', 'who owes', 'show me', 'list my', 'how many do i', 'how many do we', 'what did i', 'when did i', 'details of my', 'info on my', 'outstanding', 'outsating', 'outstandng', 'outstnding', 'pending', 'pendng', 'payable', 'payble', 'balance', 'invoice', 'client', 'supplier', 'stock', 'cash', 'bank', 'loan', 'cheque', 'manifest', 'expense', 'sales', 'revenue', 'profit', 'booking', 'void', 'cancelled', 'price list', 'whatsapp', 'how many users', 'how many owners', 'how many employees', 'sales', 'purchase', 'expense', 'cash', 'bank', 'receipt', 'payment', 'estimate', 'quotation', 'awb', 'docket', 'manifest', 'courier', 'city', 'destination', 'ledger', 'statement', 'top', 'overdue', 'new client', 'electronics', 'logistics', 'technologies', 'enterprises', 'traders', 'corporation', 'solutions']`
- `INTENT_PERMISSION_MODULE = {'dashboard_summary': 'dashboard', 'sales_summary': 'invoices', 'purchase_summary': 'purchase', 'gst_summary': 'analytics', 'country_bookings_summary': 'analytics', 'employee_bookings_summary': 'analytics', 'client_detail': 'clients', 'all_clients_summary': 'clients', 'client_pending_amount': 'clients', 'party_outstanding': 'clients', 'party_outstanding_both': 'clients', 'supplier_detail': 'suppliers', 'all_suppliers_summary': 'suppliers', 'supplier_payable_amount': 'suppliers', 'invoice_detail': 'invoices', 'pending_receivables': 'receipts_payments', 'pending_payables': 'receipts_payments', 'purchase_invoice_detail': 'purchase', 'cash_summary': 'cash', 'bank_summary': 'bank', 'expenses_summary': 'expenses', 'stock_summary': 'stock', 'stock_item_detail': 'stock', 'manifest_summary': 'manifest', 'loans_summary': 'loans', 'cheques_summary': 'cheques', 'net_profit_summary': 'analytics', 'gross_profit_summary': 'analytics', 'bookings_list': 'invoices', 'void_cancelled_list': 'invoices', 'client_count': 'clients', 'supplier_count': 'suppliers', 'price_list_status': 'purchase', 'whatsapp_status': 'settings', 'user_count_summary': 'settings', 'company_plan_status': 'dashboard', 'employee_access_guide': 'dashboard', 'change_password_guide': 'dashboard', 'upgrade_plan_guide': 'dashboard', 'company_settings_guide': 'dashboard', 'how_to_workflow_guide': 'dashboard', 'todays_sales': 'invoices', 'todays_bookings': 'invoices', 'overdue_invoices': 'receipts_payments', 'top_clients_sales': 'analytics', 'worst_clients_sales': 'analytics', 'top_clients_outstanding': 'analytics', 'awb_detail': 'invoices', 'todays_expenses': 'expenses', 'expenses_category': 'expenses', 'todays_cash': 'cash', 'receipts_payments_summary': 'receipts_payments', 'client_statement': 'clients', 'supplier_statement': 'suppliers', 'estimate_summary': 'invoices', 'estimate_detail': 'invoices', 'top_suppliers_purchase': 'analytics', 'destination_analysis': 'analytics', 'courier_analysis': 'analytics', 'new_clients': 'clients', 'customer_invoice_summary': 'invoices', 'customer_invoice_detail': 'invoices', 'bank_account_detail': 'bank', 'pending_manifests': 'manifest', 'calculate_rate_quote': 'pricelist', 'general_tax_knowledge': 'dashboard', 'help': 'dashboard'}`

## utils/alerts.py

### AlertManager (L17)

## utils/finance_guard.py


## utils/intent_router.py


## utils/query_engine.py


## utils/reports.py

### ReportGenerator (L9)

## utils/rules_engine.py


## utils/self_learning_ai.py

### SelfLearningAssetAI (L17)
- `_NO_LLM_INTENTS = {'net_profit_summary', 'gross_profit_summary', 'sales_summary', 'purchase_summary', 'gst_summary', 'cash_summary', 'bank_summary', 'expenses_summary', 'pending_receivables', 'pending_payables'}`

## whatsapp_connector.py

### ConnectorConfigError (L25)
### ConnectorSecurityError (L30)

## whatsapp_service.py


## whatsapp_template_registry.py


## whatsapp_templates.py

### TemplateParamMismatchError (L27)

## workshop_routes.py

- L334 `workshop_erp_view`: `app.route('/workshop', endpoint='workshop_erp_view'); app.route('/workshop/dashboard', endpoint='workshop_erp_dashboard'); login_required`. Referenced names: STATUS_FLOW
- L341 `workshop_vehicle_public_view`: `app.route('/workshop/v/<string:vehicle_uuid>', endpoint='workshop_vehicle_public_view')`. Referenced names: Company, CustomerVehicle, Exception, ServiceReminder, VehicleServiceHistory, WorkshopJobCard
- L402 `workshop_vehicle_qr_code`: `app.route('/workshop/v/<string:vehicle_uuid>/qr', endpoint='workshop_vehicle_qr_code')`. Referenced names: Response
- L420 `api_workshop_stats`: `app.route('/api/workshop/stats', methods=['GET']); login_required`. Referenced names: CustomerVehicle, Exception, STATUS_FLOW, WorkshopJobCard
- L487 `api_workshop_vehicles`: `app.route('/api/workshop/vehicles', methods=['GET', 'POST']); login_required`. Referenced names: Client, CustomerVehicle, Exception
- L599 `api_workshop_vehicle_detail`: `app.route('/api/workshop/vehicles/<int:vehicle_id>', methods=['GET', 'PUT']); login_required`. Referenced names: Client, CustomerVehicle, Exception, ServiceReminder, VehicleServiceHistory, WorkshopEstimate, WorkshopJobCard, WorkshopVehicleServicePlan
- L744 `api_workshop_vehicle_service_plan`: `app.route('/api/workshop/vehicles/<int:vehicle_id>/service-plan', methods=['POST']); login_required`. Referenced names: CustomerVehicle, TypeError, ValueError, WorkshopVehicleServicePlan
- L771 `api_workshop_digital_job_cards`: `app.route('/api/workshop/digital-job-cards', methods=['GET']); login_required`. Referenced names: CustomerVehicle, Exception, WorkshopJobCard
- L869 `api_workshop_job_cards`: `app.route('/api/workshop/job-cards', methods=['GET', 'POST']); login_required`. Referenced names: CustomerVehicle, Exception, WorkshopJobCard
- L1012 `api_workshop_job_card_detail`: `app.route('/api/workshop/job-cards/<int:job_card_id>', methods=['GET', 'PUT']); login_required`. Referenced names: WorkshopEstimate, WorkshopInspection, WorkshopJobCard, WorkshopPartIssue, WorkshopQualityCheck, WorkshopTask
- L1047 `api_workshop_job_card_status`: `app.route('/api/workshop/job-cards/<int:job_card_id>/status', methods=['POST']); login_required`. Referenced names: STATUS_FLOW, WorkshopJobCard
- L1070 `api_workshop_checklist_templates`: `app.route('/api/workshop/checklist-templates', methods=['GET']); login_required`. Referenced names: GENERAL_SERVICE_CHECKLIST
- L1080 `api_workshop_products`: `app.route('/api/workshop/products', methods=['GET']); login_required`. Referenced names: Exception, StockItem, SupplierBrand
- L1131 `api_workshop_job_card_inspection`: `app.route('/api/workshop/job-cards/<int:job_card_id>/inspection', methods=['GET', 'POST']); login_required`. Referenced names: WorkshopInspection, WorkshopJobCard
- L1180 `api_workshop_job_card_estimate`: `app.route('/api/workshop/job-cards/<int:job_card_id>/estimate', methods=['GET', 'POST']); login_required`. Referenced names: WorkshopEstimate, WorkshopEstimateItem, WorkshopJobCard
- L1276 `api_workshop_approve_estimate`: `app.route('/api/workshop/job-cards/<int:job_card_id>/approve-estimate', methods=['POST']); login_required`. Referenced names: WorkshopEstimate, WorkshopJobCard, WorkshopPartIssue
- L1342 `api_workshop_add_additional_item`: `app.route('/api/workshop/job-cards/<int:job_card_id>/add-additional-item', methods=['POST']); login_required`. Referenced names: WorkshopEstimate, WorkshopEstimateItem, WorkshopJobCard, WorkshopPartIssue
- L1485 `api_workshop_tasks`: `app.route('/api/workshop/job-cards/<int:job_card_id>/tasks', methods=['GET', 'POST']); login_required`. Referenced names: WorkshopJobCard, WorkshopTask
- L1515 `api_workshop_update_task_status`: `app.route('/api/workshop/tasks/<int:task_id>/status', methods=['POST']); login_required`. Referenced names: WorkshopTask
- L1537 `api_workshop_parts_issue`: `app.route('/api/workshop/job-cards/<int:job_card_id>/parts-issue', methods=['GET', 'POST']); login_required`. Referenced names: StockItem, WorkshopJobCard, WorkshopPartIssue
- L1589 `api_workshop_qc`: `app.route('/api/workshop/job-cards/<int:job_card_id>/qc', methods=['GET', 'POST']); login_required`. Referenced names: WorkshopJobCard, WorkshopQualityCheck
- L1639 `api_workshop_create_invoice`: `app.route('/api/workshop/job-cards/<int:job_card_id>/invoice', methods=['POST']); login_required; require_permission('customer_invoices', 'create')`. Referenced names: CustomerInvoice, CustomerInvoiceItem, WorkshopEstimate, WorkshopJobCard
- L1809 `api_workshop_deliver_vehicle`: `app.route('/api/workshop/job-cards/<int:job_card_id>/deliver', methods=['POST']); login_required`. Referenced names: CustomerInvoice, ServiceReminder, VehicleServiceHistory, WorkshopEstimate, WorkshopJobCard, WorkshopPartIssue, WorkshopVehicleServicePlan
- L1896 `repair_bills_view`: `app.route('/repair-bills', endpoint='repair_bills_view'); login_required; require_permission('customer_invoices', 'view')`. Referenced names: CustomerInvoice, CustomerVehicle, WorkshopJobCard
- L1931 `repair_bill_view`: `app.route('/repair-bills/<int:job_card_id>', endpoint='repair_bill_view'); login_required; require_permission('customer_invoices', 'view')`. Referenced names: CustomerInvoice, WorkshopJobCard
- L1951 `workshop_job_card_bill_view`: `app.route('/workshop/job-cards/<int:job_card_id>/bill', endpoint='workshop_job_card_bill_view')`. Referenced names: Company, CustomerInvoice, Exception, WorkshopEstimate, WorkshopInspection, WorkshopJobCard, WorkshopQualityCheck
- L2015 `api_workshop_service_catalog`: `app.route('/api/workshop/service-catalog', methods=['GET', 'POST']); login_required`. Referenced names: WorkshopServiceCatalog
- L2041 `api_workshop_service_catalog_item`: `app.route('/api/workshop/service-catalog/<int:svc_id>', methods=['PUT', 'DELETE']); login_required`. Referenced names: WorkshopServiceCatalog
- L2067 `api_workshop_reminders`: `app.route('/api/workshop/reminders', methods=['GET', 'POST']); login_required`. Referenced names: Exception, ServiceReminder
- L2106 `api_workshop_cost_analytics`: `app.route('/api/workshop/cost-analytics', methods=['GET']); login_required`. Referenced names: Exception, ValueError, WorkshopEstimate, WorkshopJobCard, WorkshopPartIssue

## Templates and navigation

- `templates/_admin_access_console.html` (46 lines); extends/includes: ; endpoints: static
- `templates/_crm_workspace_panes.html` (28 lines); extends/includes: ; endpoints: 
- `templates/_invoice_dashboard_style.html` (46 lines); extends/includes: ; endpoints: 
- `templates/account_setup.html` (102 lines); extends/includes: ; endpoints: resend_account_setup_otp, static
- `templates/add_company.html` (254 lines); extends/includes: ; endpoints: add_new_company, company_settings, select_company, static
- `templates/admin.html` (508 lines); extends/includes: ; endpoints: 
- `templates/admin_users.html` (207 lines); extends/includes: ; endpoints: 
- `templates/admin_whatsapp_templates.html` (156 lines); extends/includes: base.html; endpoints: whatsapp_settings
- `templates/apps_hub.html` (897 lines); extends/includes: ; endpoints: bi_dashboard, crm_view, logout, order_erp_view, select_company, static, workshop_erp_view
- `templates/backup.html` (620 lines); extends/includes: base.html; endpoints: create_backup, delete_backup_record, download_backup, schedule_backup, upload_backup
- `templates/bank_accounts.html` (300 lines); extends/includes: base.html; endpoints: 
- `templates/bank_transactions.html` (472 lines); extends/includes: base.html; endpoints: add_bank_transaction, bank_accounts, bank_transactions
- `templates/base.html` (4014 lines); extends/includes: ; endpoints: apps_hub, backup, bank_accounts, bi_dashboard, cash_in_hand, cheques, client_list, company_settings, creditors_list, crm_view, customer_invoice_list, debtors_list, delivery_challan_list, estimate_list, expenses, export_selector, inventory_list, ledger, loan_accounts, logout, order_erp_view, payment_new, purchase_invoice_list, purchase_order_list, receipt_new, repair_bills_view, reports_dashboard, sales_order_list, select_company, static, supplier_list, trial_balance, whatsapp_settings, workshop_erp_view
- `templates/bi_dashboard.html` (4114 lines); extends/includes: base.html; endpoints: 
- `templates/booking.html` (3986 lines); extends/includes: base.html; endpoints: static
- `templates/booking_deleted_log.html` (25 lines); extends/includes: base.html; endpoints: 
- `templates/booking_edit.html` (235 lines); extends/includes: base.html; endpoints: 
- `templates/booking_list.html` (1050 lines); extends/includes: base.html; endpoints: 
- `templates/booking_pdf.html` (474 lines); extends/includes: ; endpoints: 
- `templates/booking_resale.html` (193 lines); extends/includes: base.html; endpoints: 
- `templates/booking_view.html` (1966 lines); extends/includes: base.html; endpoints: static
- `templates/cash_in_hand.html` (487 lines); extends/includes: base.html; endpoints: 
- `templates/cheques.html` (653 lines); extends/includes: base.html; endpoints: 
- `templates/client_detail.html` (661 lines); extends/includes: base.html; endpoints: static
- `templates/client_form.html` (504 lines); extends/includes: base.html; endpoints: static
- `templates/clients.html` (601 lines); extends/includes: base.html; endpoints: 
- `templates/company_settings.html` (1479 lines); extends/includes: base.html; endpoints: delete_company_user, edit_user_access, generate_company_api_key, revoke_company_user, save_user_field_permissions, save_user_permissions
- `templates/confirm_price_list.html` (84 lines); extends/includes: base.html; endpoints: 
- `templates/creditors.html` (200 lines); extends/includes: base.html; endpoints: 
- `templates/crm.html` (1718 lines); extends/includes: _crm_workspace_panes.html; endpoints: apps_hub, bi_dashboard, crm_view, logout, order_erp_view, select_company, static, workshop_erp_view
- `templates/customer_invoice_form.html` (516 lines); extends/includes: base.html; endpoints: customer_invoice_create, customer_invoice_edit, customer_invoice_list
- `templates/customer_invoice_list.html` (156 lines); extends/includes: _invoice_dashboard_style.html, base.html; endpoints: customer_invoice_delete, customer_invoice_edit, customer_invoice_list, customer_invoice_new, customer_invoice_print, customer_invoice_view
- `templates/customer_invoice_pdf.html` (461 lines); extends/includes: ; endpoints: 
- `templates/customer_invoice_pdf_classic.html` (456 lines); extends/includes: ; endpoints: customer_invoice_view
- `templates/customer_invoice_pdf_minimal.html` (429 lines); extends/includes: ; endpoints: customer_invoice_view
- `templates/customer_invoice_pdf_modern.html` (431 lines); extends/includes: ; endpoints: customer_invoice_view
- `templates/customer_invoice_pdf_tally_style.html` (458 lines); extends/includes: ; endpoints: customer_invoice_view
- `templates/customer_invoice_view.html` (241 lines); extends/includes: base.html; endpoints: customer_invoice_edit, customer_invoice_list, customer_invoice_print
- `templates/dashboard.html` (822 lines); extends/includes: base.html; endpoints: 
- `templates/debtor_creditor_statement.html` (779 lines); extends/includes: base.html; endpoints: 
- `templates/debtors.html` (229 lines); extends/includes: base.html; endpoints: 
- `templates/delivery_challan_form.html` (502 lines); extends/includes: base.html; endpoints: delivery_challan_edit, delivery_challan_list, delivery_challan_new
- `templates/delivery_challan_list.html` (224 lines); extends/includes: base.html; endpoints: delivery_challan_convert_to_invoice, delivery_challan_edit, delivery_challan_list, delivery_challan_new, delivery_challan_view
- `templates/delivery_challan_pdf.html` (97 lines); extends/includes: ; endpoints: 
- `templates/delivery_challan_view.html` (261 lines); extends/includes: base.html; endpoints: delivery_challan_convert_to_invoice, delivery_challan_edit, delivery_challan_list, delivery_challan_pdf
- `templates/errors/403.html` (10 lines); extends/includes: errors/_layout.html; endpoints: index
- `templates/errors/404.html` (10 lines); extends/includes: errors/_layout.html; endpoints: index
- `templates/errors/500.html` (11 lines); extends/includes: errors/_layout.html; endpoints: index
- `templates/errors/_layout.html` (107 lines); extends/includes: ; endpoints: index, static
- `templates/estimate_form.html` (514 lines); extends/includes: base.html; endpoints: estimate_edit, estimate_list, estimate_new
- `templates/estimate_list.html` (153 lines); extends/includes: base.html; endpoints: estimate_edit, estimate_new, estimate_view
- `templates/estimate_view.html` (278 lines); extends/includes: base.html; endpoints: estimate_convert_to_invoice, estimate_convert_to_so, estimate_edit, estimate_list
- `templates/expenses.html` (731 lines); extends/includes: base.html; endpoints: add_expense, delete_expense
- `templates/export_selector.html` (444 lines); extends/includes: base.html; endpoints: export_reports_excel
- `templates/force_change_password.html` (339 lines); extends/includes: ; endpoints: force_change_password, static
- `templates/inventory.html` (861 lines); extends/includes: base.html; endpoints: customer_invoice_list, inventory_add, inventory_edit, purchase_invoice_list, stock_inward_direct
- `templates/inventory_form.html` (355 lines); extends/includes: base.html; endpoints: inventory_add, inventory_edit, inventory_list
- `templates/ledger.html` (399 lines); extends/includes: base.html; endpoints: ledger
- `templates/ledger_statement.html` (927 lines); extends/includes: base.html; endpoints: 
- `templates/loader-demo2.html` (49 lines); extends/includes: ; endpoints: 
- `templates/loan_accounts.html` (675 lines); extends/includes: base.html; endpoints: 
- `templates/login-new.html` (130 lines); extends/includes: ; endpoints: static
- `templates/login.html` (369 lines); extends/includes: ; endpoints: register, static
- `templates/manifest_form.html` (585 lines); extends/includes: base.html; endpoints: 
- `templates/manifest_list.html` (1252 lines); extends/includes: base.html; endpoints: 
- `templates/manifest_print.html` (203 lines); extends/includes: ; endpoints: manifest_list
- `templates/manifest_print_day.html` (236 lines); extends/includes: ; endpoints: manifest_list
- `templates/manifest_view.html` (94 lines); extends/includes: base.html; endpoints: 
- `templates/migrations.html` (392 lines); extends/includes: base.html; endpoints: 
- `templates/module_access_denied.html` (9 lines); extends/includes: base.html; endpoints: apps_hub
- `templates/onboard_company.html` (100 lines); extends/includes: ; endpoints: 
- `templates/order_erp.html` (2071 lines); extends/includes: ; endpoints: apps_hub, bi_dashboard, crm_view, logout, order_erp_view, select_company, static, workshop_erp_view
- `templates/price_lists.html` (206 lines); extends/includes: base.html; endpoints: delete_price_list, view_price_list
- `templates/profit_loss.html` (251 lines); extends/includes: base.html; endpoints: 
- `templates/purchase_edit.html` (994 lines); extends/includes: base.html; endpoints: purchase_invoice_edit, purchase_invoice_list, purchase_invoice_new
- `templates/purchase_new.html` (1049 lines); extends/includes: base.html; endpoints: purchase_invoice_edit, purchase_invoice_list, purchase_invoice_new
- `templates/purchase_order_form.html` (335 lines); extends/includes: base.html; endpoints: purchase_order_edit, purchase_order_list, purchase_order_new
- `templates/purchase_order_list.html` (175 lines); extends/includes: base.html; endpoints: purchase_order_convert_to_bill, purchase_order_edit, purchase_order_list, purchase_order_new, purchase_order_view
- `templates/purchase_order_view.html` (191 lines); extends/includes: base.html; endpoints: purchase_order_convert_to_bill, purchase_order_edit, purchase_order_list
- `templates/purchase_report.html` (349 lines); extends/includes: base.html; endpoints: 
- `templates/purchase_view.html` (419 lines); extends/includes: base.html; endpoints: purchase_invoice_delete, purchase_invoice_edit, purchase_invoice_list, purchase_make_payment
- `templates/purchases.html` (1411 lines); extends/includes: base.html; endpoints: 
- `templates/rate_calculator.html` (626 lines); extends/includes: base.html; endpoints: 
- `templates/record_payment.html` (968 lines); extends/includes: base.html; endpoints: 
- `templates/record_receipt.html` (1015 lines); extends/includes: base.html; endpoints: 
- `templates/register.html` (1679 lines); extends/includes: ; endpoints: static
- `templates/register_client.html` (233 lines); extends/includes: ; endpoints: admin_dashboard
- `templates/repair_bill.html` (329 lines); extends/includes: ; endpoints: static
- `templates/repair_bills.html` (52 lines); extends/includes: _invoice_dashboard_style.html, base.html; endpoints: repair_bill_view, repair_bills_view, workshop_erp_view
- `templates/report_dashboard.html` (998 lines); extends/includes: base.html; endpoints: 
- `templates/sales_order_form.html` (343 lines); extends/includes: base.html; endpoints: sales_order_edit, sales_order_list, sales_order_new
- `templates/sales_order_list.html` (177 lines); extends/includes: base.html; endpoints: sales_order_convert_to_challan, sales_order_convert_to_invoice, sales_order_edit, sales_order_list, sales_order_new, sales_order_view
- `templates/sales_order_view.html` (193 lines); extends/includes: base.html; endpoints: sales_order_convert_to_challan, sales_order_convert_to_invoice, sales_order_edit, sales_order_list
- `templates/sales_report.html` (219 lines); extends/includes: base.html; endpoints: 
- `templates/select_company.html` (582 lines); extends/includes: ; endpoints: add_new_company, dashboard, logout, select_company, static, toggle_company_mobile_visibility
- `templates/settings_whatsapp.html` (293 lines); extends/includes: base.html; endpoints: whatsapp_disconnect, whatsapp_test
- `templates/statement.html` (198 lines); extends/includes: base.html; endpoints: 
- `templates/stock_report.html` (189 lines); extends/includes: base.html; endpoints: 
- `templates/super_admin.html` (1590 lines); extends/includes: _admin_access_console.html; endpoints: register_client, static
- `templates/supplier_detail.html` (503 lines); extends/includes: base.html; endpoints: 
- `templates/supplier_form.html` (387 lines); extends/includes: base.html; endpoints: 
- `templates/suppliers.html` (499 lines); extends/includes: base.html; endpoints: 
- `templates/tax_report.html` (219 lines); extends/includes: base.html; endpoints: 
- `templates/tracking_status.html` (56 lines); extends/includes: ; endpoints: 
- `templates/trial_balance.html` (351 lines); extends/includes: base.html; endpoints: trial_balance
- `templates/upload_price_list.html` (83 lines); extends/includes: base.html; endpoints: 
- `templates/vehicle_view.html` (417 lines); extends/includes: ; endpoints: workshop_erp_view, workshop_vehicle_qr_code
- `templates/verify_otp.html` (299 lines); extends/includes: ; endpoints: login, resend_otp, static, verify_otp
- `templates/view_price_list.html` (192 lines); extends/includes: base.html; endpoints: price_lists
- `templates/whatsapp_campaign.html` (70 lines); extends/includes: base.html; endpoints: whatsapp_settings
- `templates/workshop_bill.html` (333 lines); extends/includes: ; endpoints: static
- `templates/workshop_erp.html` (5985 lines); extends/includes: ; endpoints: apps_hub, bi_dashboard, crm_view, logout, order_erp_view, select_company, static, workshop_erp_view

## Local SQLite schemas (read-only; not the configured MySQL runtime)

### customer_databases/COMP001.db
- `bank_accounts`: id INTEGER, company_id VARCHAR(20), bank_name VARCHAR(200), account_name VARCHAR(200), account_number VARCHAR(50), ifsc_code VARCHAR(20), branch VARCHAR(200), balance FLOAT, opening_balance FLOAT, status VARCHAR(30), notes TEXT, created_at DATETIME, updated_at DATETIME; foreign keys: []
- `bank_transactions`: id INTEGER, bank_account_id INTEGER, company_id VARCHAR(20), type VARCHAR(20), date DATE, description VARCHAR(300), amount FLOAT, reference VARCHAR(100), transaction_mode VARCHAR(30), notes TEXT, created_at DATETIME, created_by VARCHAR(50); foreign keys: [(0, 0, 'bank_accounts', 'bank_account_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `cash_transactions`: id INTEGER, company_id VARCHAR(20), type VARCHAR(20), date DATE, category VARCHAR(100), description VARCHAR(300), amount FLOAT, reference VARCHAR(100), notes TEXT, created_at DATETIME, created_by VARCHAR(50); foreign keys: []
- `clients`: id INTEGER, company_id VARCHAR(20), name VARCHAR(200), contact_person VARCHAR(150), client_type VARCHAR(30), phone VARCHAR(20), alternate_phone VARCHAR(20), email VARCHAR(255), website VARCHAR(255), address_line1 VARCHAR(300), address_line2 VARCHAR(300), city VARCHAR(100), state VARCHAR(100), pincode VARCHAR(10), country VARCHAR(100), gst_number VARCHAR(20), pan_number VARCHAR(15), gst_type VARCHAR(30), credit_limit FLOAT, credit_days INTEGER, pending FLOAT, last_payment DATE, opening_balance FLOAT, status VARCHAR(50), notes TEXT, created_at DATE; foreign keys: []
- `company_users`: id INTEGER, user_id VARCHAR(20), company_id VARCHAR(20), email VARCHAR(255), password_hash VARCHAR(255), full_name VARCHAR(150), role VARCHAR(50), department VARCHAR(100), phone VARCHAR(20), is_active BOOLEAN, created_at DATE; foreign keys: []
- `estimate_items`: id INTEGER, estimate_id INTEGER, stock_item_id INTEGER, code VARCHAR(50), description VARCHAR(300), qty FLOAT, rate FLOAT, discount FLOAT; foreign keys: [(0, 0, 'estimates', 'estimate_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `estimates`: id INTEGER, estimate_id VARCHAR(30), company_id VARCHAR(20), client_id INTEGER, date DATE, valid_until DATE, status VARCHAR(50), subtotal FLOAT, tax_amount FLOAT, grand_total FLOAT, notes TEXT, created_at DATETIME; foreign keys: []
- `invoice_items`: id INTEGER, invoice_id INTEGER, stock_item_id INTEGER, code VARCHAR(50), description VARCHAR(300), qty FLOAT, rate FLOAT, discount FLOAT; foreign keys: [(0, 0, 'invoices', 'invoice_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `invoices`: id INTEGER, invoice_id VARCHAR(30), company_id VARCHAR(20), client_id INTEGER, date DATE, due_date DATE, status VARCHAR(50), subtotal FLOAT, tax_amount FLOAT, grand_total FLOAT, contact_person VARCHAR(150), email VARCHAR(255), phone VARCHAR(20), terms TEXT, paid_amount FLOAT, balance FLOAT, created_at DATETIME; foreign keys: []
- `loan_repayments`: id INTEGER, loan_id INTEGER, date DATE, amount FLOAT, payment_mode VARCHAR(30), reference VARCHAR(100), notes TEXT, created_at DATETIME; foreign keys: [(0, 0, 'loans', 'loan_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `loans`: id INTEGER, company_id VARCHAR(20), type VARCHAR(20), party_name VARCHAR(200), loan_date DATE, amount FLOAT, interest_rate FLOAT, tenure INTEGER, emi_amount FLOAT, purpose VARCHAR(300), notes TEXT, status VARCHAR(30), created_at DATETIME, created_by VARCHAR(50); foreign keys: []
- `orders`: id INTEGER, order_id VARCHAR(30), company_id VARCHAR(20), client_id INTEGER, employee_id VARCHAR(20), date DATE, amount FLOAT, received FLOAT, status VARCHAR(50); foreign keys: []
- `purchase_invoice_items`: id INTEGER, purchase_invoice_id INTEGER, stock_item_id INTEGER, code VARCHAR(50), description VARCHAR(300), hsn VARCHAR(20), quantity FLOAT, unit VARCHAR(20), purchase_rate FLOAT, discount_percent FLOAT, taxable_value FLOAT, gst_percent FLOAT, cgst_amount FLOAT, sgst_amount FLOAT, igst_amount FLOAT, total_amount FLOAT; foreign keys: [(0, 0, 'purchase_invoices', 'purchase_invoice_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `purchase_invoices`: id INTEGER, invoice_id VARCHAR(30), company_id VARCHAR(20), supplier_id INTEGER, invoice_number VARCHAR(100), date DATE, due_date DATE, subtotal FLOAT, tax_amount FLOAT, grand_total FLOAT, paid_amount FLOAT, balance FLOAT, status VARCHAR(50), notes TEXT, file_path VARCHAR(500), ocr_data TEXT, created_at DATETIME; foreign keys: []
- `stock_items`: id INTEGER, company_id VARCHAR(20), code VARCHAR(50), name VARCHAR(200), category VARCHAR(100), quantity FLOAT, unit VARCHAR(20), unit_price FLOAT, reorder_level FLOAT, hsn VARCHAR(20), last_updated DATE, purchase_rate FLOAT, last_purchase_rate FLOAT, avg_purchase_rate FLOAT, gst_percent FLOAT, selling_price FLOAT, margin_percent FLOAT; foreign keys: []
- `stock_purchase_history`: id INTEGER, stock_item_id INTEGER, purchase_invoice_id INTEGER, quantity FLOAT, purchase_rate FLOAT, gst_percent FLOAT, purchase_date DATE, movement_type VARCHAR(10), reference VARCHAR(100); foreign keys: [(0, 0, 'purchase_invoices', 'purchase_invoice_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
### customer_databases/COMP002.db
- `bank_accounts`: id INTEGER, company_id VARCHAR(20), bank_name VARCHAR(200), account_name VARCHAR(200), account_number VARCHAR(50), ifsc_code VARCHAR(20), branch VARCHAR(200), balance FLOAT, opening_balance FLOAT, status VARCHAR(30), notes TEXT, created_at DATETIME, updated_at DATETIME; foreign keys: []
- `bank_transactions`: id INTEGER, bank_account_id INTEGER, company_id VARCHAR(20), type VARCHAR(20), date DATE, description VARCHAR(300), amount FLOAT, reference VARCHAR(100), transaction_mode VARCHAR(30), notes TEXT, created_at DATETIME, created_by VARCHAR(50); foreign keys: [(0, 0, 'bank_accounts', 'bank_account_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `cash_transactions`: id INTEGER, company_id VARCHAR(20), type VARCHAR(20), date DATE, category VARCHAR(100), description VARCHAR(300), amount FLOAT, reference VARCHAR(100), notes TEXT, created_at DATETIME, created_by VARCHAR(50); foreign keys: []
- `clients`: id INTEGER, company_id VARCHAR(20), name VARCHAR(200), contact_person VARCHAR(150), client_type VARCHAR(30), phone VARCHAR(20), alternate_phone VARCHAR(20), email VARCHAR(255), website VARCHAR(255), address_line1 VARCHAR(300), address_line2 VARCHAR(300), city VARCHAR(100), state VARCHAR(100), pincode VARCHAR(10), country VARCHAR(100), gst_number VARCHAR(20), pan_number VARCHAR(15), gst_type VARCHAR(30), credit_limit FLOAT, credit_days INTEGER, pending FLOAT, last_payment DATE, opening_balance FLOAT, status VARCHAR(50), notes TEXT, created_at DATE; foreign keys: []
- `company_users`: id INTEGER, user_id VARCHAR(20), company_id VARCHAR(20), email VARCHAR(255), password_hash VARCHAR(255), full_name VARCHAR(150), role VARCHAR(50), department VARCHAR(100), phone VARCHAR(20), is_active BOOLEAN, created_at DATE; foreign keys: []
- `estimate_items`: id INTEGER, estimate_id INTEGER, stock_item_id INTEGER, code VARCHAR(50), description VARCHAR(300), qty FLOAT, rate FLOAT, discount FLOAT; foreign keys: [(0, 0, 'estimates', 'estimate_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `estimates`: id INTEGER, estimate_id VARCHAR(30), company_id VARCHAR(20), client_id INTEGER, date DATE, valid_until DATE, status VARCHAR(50), subtotal FLOAT, tax_amount FLOAT, grand_total FLOAT, notes TEXT, created_at DATETIME; foreign keys: []
- `invoice_items`: id INTEGER, invoice_id INTEGER, stock_item_id INTEGER, code VARCHAR(50), description VARCHAR(300), qty FLOAT, rate FLOAT, discount FLOAT; foreign keys: [(0, 0, 'invoices', 'invoice_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `invoices`: id INTEGER, invoice_id VARCHAR(30), company_id VARCHAR(20), client_id INTEGER, date DATE, due_date DATE, status VARCHAR(50), subtotal FLOAT, tax_amount FLOAT, grand_total FLOAT, contact_person VARCHAR(150), email VARCHAR(255), phone VARCHAR(20), terms TEXT, paid_amount FLOAT, balance FLOAT, created_at DATETIME; foreign keys: []
- `loan_repayments`: id INTEGER, loan_id INTEGER, date DATE, amount FLOAT, payment_mode VARCHAR(30), reference VARCHAR(100), notes TEXT, created_at DATETIME; foreign keys: [(0, 0, 'loans', 'loan_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `loans`: id INTEGER, company_id VARCHAR(20), type VARCHAR(20), party_name VARCHAR(200), loan_date DATE, amount FLOAT, interest_rate FLOAT, tenure INTEGER, emi_amount FLOAT, purpose VARCHAR(300), notes TEXT, status VARCHAR(30), created_at DATETIME, created_by VARCHAR(50); foreign keys: []
- `orders`: id INTEGER, order_id VARCHAR(30), company_id VARCHAR(20), client_id INTEGER, employee_id VARCHAR(20), date DATE, amount FLOAT, received FLOAT, status VARCHAR(50); foreign keys: []
- `purchase_invoice_items`: id INTEGER, purchase_invoice_id INTEGER, stock_item_id INTEGER, code VARCHAR(50), description VARCHAR(300), hsn VARCHAR(20), quantity FLOAT, unit VARCHAR(20), purchase_rate FLOAT, discount_percent FLOAT, taxable_value FLOAT, gst_percent FLOAT, cgst_amount FLOAT, sgst_amount FLOAT, igst_amount FLOAT, total_amount FLOAT; foreign keys: [(0, 0, 'purchase_invoices', 'purchase_invoice_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `purchase_invoices`: id INTEGER, invoice_id VARCHAR(30), company_id VARCHAR(20), supplier_id INTEGER, invoice_number VARCHAR(100), date DATE, due_date DATE, subtotal FLOAT, tax_amount FLOAT, grand_total FLOAT, paid_amount FLOAT, balance FLOAT, status VARCHAR(50), notes TEXT, file_path VARCHAR(500), ocr_data TEXT, created_at DATETIME; foreign keys: []
- `stock_items`: id INTEGER, company_id VARCHAR(20), code VARCHAR(50), name VARCHAR(200), category VARCHAR(100), quantity FLOAT, unit VARCHAR(20), unit_price FLOAT, reorder_level FLOAT, hsn VARCHAR(20), last_updated DATE, purchase_rate FLOAT, last_purchase_rate FLOAT, avg_purchase_rate FLOAT, gst_percent FLOAT, selling_price FLOAT, margin_percent FLOAT; foreign keys: []
- `stock_purchase_history`: id INTEGER, stock_item_id INTEGER, purchase_invoice_id INTEGER, quantity FLOAT, purchase_rate FLOAT, gst_percent FLOAT, purchase_date DATE, movement_type VARCHAR(10), reference VARCHAR(100); foreign keys: [(0, 0, 'purchase_invoices', 'purchase_invoice_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
### customer_databases/COMP003.db
- `bank_accounts`: id INTEGER, company_id VARCHAR(20), bank_name VARCHAR(200), account_name VARCHAR(200), account_number VARCHAR(50), ifsc_code VARCHAR(20), branch VARCHAR(200), balance FLOAT, opening_balance FLOAT, status VARCHAR(30), notes TEXT, created_at DATETIME, updated_at DATETIME; foreign keys: []
- `bank_transactions`: id INTEGER, bank_account_id INTEGER, company_id VARCHAR(20), type VARCHAR(20), date DATE, description VARCHAR(300), amount FLOAT, reference VARCHAR(100), transaction_mode VARCHAR(30), notes TEXT, created_at DATETIME, created_by VARCHAR(50); foreign keys: [(0, 0, 'bank_accounts', 'bank_account_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `cash_transactions`: id INTEGER, company_id VARCHAR(20), type VARCHAR(20), date DATE, category VARCHAR(100), description VARCHAR(300), amount FLOAT, reference VARCHAR(100), notes TEXT, created_at DATETIME, created_by VARCHAR(50); foreign keys: []
- `clients`: id INTEGER, company_id VARCHAR(20), name VARCHAR(200), contact_person VARCHAR(150), client_type VARCHAR(30), phone VARCHAR(20), alternate_phone VARCHAR(20), email VARCHAR(255), website VARCHAR(255), address_line1 VARCHAR(300), address_line2 VARCHAR(300), city VARCHAR(100), state VARCHAR(100), pincode VARCHAR(10), country VARCHAR(100), gst_number VARCHAR(20), pan_number VARCHAR(15), gst_type VARCHAR(30), credit_limit FLOAT, credit_days INTEGER, pending FLOAT, last_payment DATE, opening_balance FLOAT, status VARCHAR(50), notes TEXT, created_at DATE; foreign keys: []
- `company_users`: id INTEGER, user_id VARCHAR(20), company_id VARCHAR(20), email VARCHAR(255), password_hash VARCHAR(255), full_name VARCHAR(150), role VARCHAR(50), department VARCHAR(100), phone VARCHAR(20), is_active BOOLEAN, created_at DATE; foreign keys: []
- `estimate_items`: id INTEGER, estimate_id INTEGER, stock_item_id INTEGER, code VARCHAR(50), description VARCHAR(300), qty FLOAT, rate FLOAT, discount FLOAT; foreign keys: [(0, 0, 'estimates', 'estimate_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `estimates`: id INTEGER, estimate_id VARCHAR(30), company_id VARCHAR(20), client_id INTEGER, date DATE, valid_until DATE, status VARCHAR(50), subtotal FLOAT, tax_amount FLOAT, grand_total FLOAT, notes TEXT, created_at DATETIME; foreign keys: []
- `invoice_items`: id INTEGER, invoice_id INTEGER, stock_item_id INTEGER, code VARCHAR(50), description VARCHAR(300), qty FLOAT, rate FLOAT, discount FLOAT; foreign keys: [(0, 0, 'invoices', 'invoice_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `invoices`: id INTEGER, invoice_id VARCHAR(30), company_id VARCHAR(20), client_id INTEGER, date DATE, due_date DATE, status VARCHAR(50), subtotal FLOAT, tax_amount FLOAT, grand_total FLOAT, contact_person VARCHAR(150), email VARCHAR(255), phone VARCHAR(20), terms TEXT, paid_amount FLOAT, balance FLOAT, created_at DATETIME; foreign keys: []
- `loan_repayments`: id INTEGER, loan_id INTEGER, date DATE, amount FLOAT, payment_mode VARCHAR(30), reference VARCHAR(100), notes TEXT, created_at DATETIME; foreign keys: [(0, 0, 'loans', 'loan_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `loans`: id INTEGER, company_id VARCHAR(20), type VARCHAR(20), party_name VARCHAR(200), loan_date DATE, amount FLOAT, interest_rate FLOAT, tenure INTEGER, emi_amount FLOAT, purpose VARCHAR(300), notes TEXT, status VARCHAR(30), created_at DATETIME, created_by VARCHAR(50); foreign keys: []
- `orders`: id INTEGER, order_id VARCHAR(30), company_id VARCHAR(20), client_id INTEGER, employee_id VARCHAR(20), date DATE, amount FLOAT, received FLOAT, status VARCHAR(50); foreign keys: []
- `purchase_invoice_items`: id INTEGER, purchase_invoice_id INTEGER, stock_item_id INTEGER, code VARCHAR(50), description VARCHAR(300), hsn VARCHAR(20), quantity FLOAT, unit VARCHAR(20), purchase_rate FLOAT, discount_percent FLOAT, taxable_value FLOAT, gst_percent FLOAT, cgst_amount FLOAT, sgst_amount FLOAT, igst_amount FLOAT, total_amount FLOAT; foreign keys: [(0, 0, 'purchase_invoices', 'purchase_invoice_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `purchase_invoices`: id INTEGER, invoice_id VARCHAR(30), company_id VARCHAR(20), supplier_id INTEGER, invoice_number VARCHAR(100), date DATE, due_date DATE, subtotal FLOAT, tax_amount FLOAT, grand_total FLOAT, paid_amount FLOAT, balance FLOAT, status VARCHAR(50), notes TEXT, file_path VARCHAR(500), ocr_data TEXT, created_at DATETIME; foreign keys: []
- `stock_items`: id INTEGER, company_id VARCHAR(20), code VARCHAR(50), name VARCHAR(200), category VARCHAR(100), quantity FLOAT, unit VARCHAR(20), unit_price FLOAT, reorder_level FLOAT, hsn VARCHAR(20), last_updated DATE, purchase_rate FLOAT, last_purchase_rate FLOAT, avg_purchase_rate FLOAT, gst_percent FLOAT, selling_price FLOAT, margin_percent FLOAT; foreign keys: []
- `stock_purchase_history`: id INTEGER, stock_item_id INTEGER, purchase_invoice_id INTEGER, quantity FLOAT, purchase_rate FLOAT, gst_percent FLOAT, purchase_date DATE, movement_type VARCHAR(10), reference VARCHAR(100); foreign keys: [(0, 0, 'purchase_invoices', 'purchase_invoice_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE')]
### instance/nexa_erp.db
- `clients`: id INTEGER, company_id VARCHAR(20), client_name VARCHAR(200), contact_person VARCHAR(100), email VARCHAR(120), phone VARCHAR(20), alternate_phone VARCHAR(20), gst_number VARCHAR(50), address TEXT, city VARCHAR(50), state VARCHAR(50), pincode VARCHAR(10), country VARCHAR(50), payment_terms INTEGER, credit_limit NUMERIC(12, 2), outstanding NUMERIC(12, 2), status VARCHAR(20), last_payment_date DATE, notes TEXT, created_at DATETIME, updated_at DATETIME; foreign keys: [(0, 0, 'companies', 'company_id', 'company_id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `companies`: id INTEGER, company_id VARCHAR(20), company_name VARCHAR(200), owner_email VARCHAR(120), subscription_plan VARCHAR(20), subscription_start DATE, subscription_end DATE, max_companies_allowed INTEGER, max_users_per_company INTEGER, gst_number VARCHAR(50), address TEXT, phone VARCHAR(20), logo VARCHAR(200), created_at DATETIME, is_active BOOLEAN; foreign keys: [(0, 0, 'registered_users', 'owner_email', 'email', 'NO ACTION', 'NO ACTION', 'NONE')]
- `company_users`: id INTEGER, user_id VARCHAR(20), company_id VARCHAR(20), email VARCHAR(120), password VARCHAR(200), full_name VARCHAR(100), role VARCHAR(30), department VARCHAR(50), phone VARCHAR(20), is_active BOOLEAN, created_at DATETIME; foreign keys: [(0, 0, 'companies', 'company_id', 'company_id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `estimates`: id INTEGER, estimate_id VARCHAR(50), company_id VARCHAR(20), client_id INTEGER, estimate_date DATE, valid_until DATE, status VARCHAR(30), total NUMERIC(12, 2), contact_person VARCHAR(100), email VARCHAR(120), phone VARCHAR(20), items TEXT, terms TEXT, created_at DATETIME, updated_at DATETIME; foreign keys: [(0, 0, 'clients', 'client_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE'), (1, 0, 'companies', 'company_id', 'company_id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `invoices`: id INTEGER, invoice_id VARCHAR(50), company_id VARCHAR(20), client_id INTEGER, invoice_date DATE, due_date DATE, bill_type VARCHAR(20), subtotal NUMERIC(12, 2), tax NUMERIC(12, 2), total NUMERIC(12, 2), paid NUMERIC(12, 2), balance NUMERIC(12, 2), payment_mode VARCHAR(30), cheque_no VARCHAR(50), transaction_id VARCHAR(100), items TEXT, status VARCHAR(20), notes TEXT, created_at DATETIME; foreign keys: [(0, 0, 'clients', 'client_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE'), (1, 0, 'companies', 'company_id', 'company_id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `orders`: id INTEGER, order_id VARCHAR(50), company_id VARCHAR(20), client_id INTEGER, order_date DATE, amount NUMERIC(12, 2), received NUMERIC(12, 2), status VARCHAR(30), employee_id VARCHAR(20), items TEXT, client_phone VARCHAR(20), dispatched_date DATE, courier_name VARCHAR(50), tracking_id VARCHAR(100), expected_delivery DATE, notes TEXT, created_at DATETIME, updated_at DATETIME; foreign keys: [(0, 0, 'clients', 'client_id', 'id', 'NO ACTION', 'NO ACTION', 'NONE'), (1, 0, 'companies', 'company_id', 'company_id', 'NO ACTION', 'NO ACTION', 'NONE')]
- `registered_users`: id INTEGER, user_id VARCHAR(20), email VARCHAR(120), password VARCHAR(200), full_name VARCHAR(100), phone VARCHAR(20), role VARCHAR(20), subscription_plan VARCHAR(20), created_at DATETIME, is_active BOOLEAN; foreign keys: []
- `stock_items`: id INTEGER, code VARCHAR(50), company_id VARCHAR(20), name VARCHAR(200), category VARCHAR(50), hsn_code VARCHAR(20), quantity NUMERIC(12, 2), unit VARCHAR(10), unit_price NUMERIC(12, 2), purchase_price NUMERIC(12, 2), reorder_level NUMERIC(12, 2), location VARCHAR(100), description TEXT, last_updated DATE, created_at DATETIME; foreign keys: [(0, 0, 'companies', 'company_id', 'company_id', 'NO ACTION', 'NO ACTION', 'NONE')]

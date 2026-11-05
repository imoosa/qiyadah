"""Read-only business adapters for Qiyadah ERP and Qiyadah eShip.
Reuses canonical BI filters and currency math; AI never computes or invents financial figures."""
from datetime import timedelta
from decimal import Decimal
import json


def _money(val):
    try:
        return Decimal(str(val or 0))
    except Exception:
        return Decimal(0)


def invoice_balance(cdb, scope, identifier):
    from customer_models import CustomerInvoice, Client
    try:
        from bi.queries import EXCLUDED_STATUSES, money
    except ImportError:
        EXCLUDED_STATUSES = ('cancelled', 'canceled', 'void', 'deleted', 'draft')
        money = _money
    scope.require(module='core', permission='customer_invoices', owner=True)
    scope.require(permission='receipts_payments')
    cdb.expire_all()
    invoice = cdb.query(CustomerInvoice).filter_by(company_id=scope.company_id, id=int(identifier)).first()
    if not invoice or (invoice.status or '').strip().lower() in (*EXCLUDED_STATUSES, 'paid', 'settled'):
        return None
    # Ledger posting services maintain balance and note_adjustment. Check both
    # stored balance and latest total/payments/adjustments, never modify either.
    balance = min(money(invoice.balance), money(invoice.grand_total) - money(invoice.paid_amount) - money(getattr(invoice, 'note_adjustment', 0)))
    if balance <= 0:
        return None
    client = cdb.query(Client).filter_by(company_id=scope.company_id, id=invoice.client_id).first()
    if not client or (client.status or '').lower() in ('deleted', 'inactive'):
        return None
    return {'id': invoice.id, 'number': invoice.invoice_number, 'balance': str(balance.quantize(Decimal('.01'))),
            'currency': getattr(invoice, 'currency', None) or 'INR',
            'due_date': invoice.due_date.isoformat() if getattr(invoice, 'due_date', None) else None,
            'phone': client.phone, 'email': client.email, 'client_id': client.id, 'client_name': client.name}


def eship_invoice_balance(cdb, scope, identifier):
    """Fetch live eShip freight invoice or booking balance; never sends reminders for settled/void records."""
    from customer_models import Invoice, CustomerInvoice, Client
    scope.require(owner=True)
    cdb.expire_all()
    excluded = ('void', 'draft', 'cancelled', 'canceled', 'paid', 'settled', 'deleted')
    inv = cdb.query(CustomerInvoice).filter_by(company_id=scope.company_id, id=int(identifier)).first()
    number_attr = 'invoice_number'
    if not inv:
        inv = cdb.query(Invoice).filter_by(company_id=scope.company_id, id=int(identifier)).first()
        number_attr = 'invoice_id'
    if not inv or (getattr(inv, 'status', '') or '').strip().lower() in excluded:
        return None
    balance = min(_money(getattr(inv, 'balance', 0)), _money(getattr(inv, 'grand_total', 0)) - _money(getattr(inv, 'paid_amount', 0)))
    if balance <= 0:
        return None
    client = cdb.query(Client).filter_by(company_id=scope.company_id, id=inv.client_id).first()
    if not client or (client.status or '').lower() in ('deleted', 'inactive'):
        return None
    due = getattr(inv, 'due_date', None) or getattr(inv, 'date', None)
    return {
        'id': inv.id,
        'number': getattr(inv, number_attr, None) or str(inv.id),
        'balance': str(balance.quantize(Decimal('.01'))),
        'currency': getattr(inv, 'currency', None) or 'INR',
        'due_date': due.isoformat() if due else None,
        'phone': client.phone,
        'email': client.email,
        'client_id': client.id,
        'client_name': client.name,
    }


def briefing(cdb, scope, start, end, currency, categories):
    from customer_models import CustomerInvoice, StockItem, CashTransaction, BankTransaction
    try:
        from customer_models import CRMQuotation, WorkshopJobCard
    except ImportError:
        CRMQuotation = WorkshopJobCard = None
    try:
        from bi.filters import BIFilters
        from bi.queries import sales_query, purchase_query, base_amount, base_balance
        _has_bi = True
    except ImportError:
        _has_bi = False
        def base_amount(r, base_attr, attr, _curr):
            return _money(getattr(r, base_attr, None) or getattr(r, attr, 0))
        def base_balance(r, _curr):
            return _money(getattr(r, 'balance', 0))
        def sales_query(db, _filters, s=None, e=None, end=None):
            q = db.query(CustomerInvoice).filter(CustomerInvoice.company_id == scope.company_id)
            if s:
                q = q.filter(CustomerInvoice.invoice_date >= s)
            if e:
                q = q.filter(CustomerInvoice.invoice_date <= e)
            if end:
                q = q.filter(CustomerInvoice.invoice_date <= end)
            return q
    from ..models import now
    scope.require(owner=True)
    filters = BIFilters(scope.company_id, start, end) if _has_bi else None
    metrics, sources = {}, []
    if 'sales' in categories:
        scope.require(module='core', permission='customer_invoices')
        current = sales_query(cdb, filters, start, end).all()
        previous = sales_query(cdb, filters, start - (end-start) - timedelta(days=1), start - timedelta(days=1)).all()
        metrics['sales'] = str(sum((base_amount(r, 'base_grand_total', 'grand_total', currency) for r in current), Decimal(0)))
        metrics['previous_period_sales'] = str(sum((base_amount(r, 'base_grand_total', 'grand_total', currency) for r in previous), Decimal(0)))
        sources.append('customer_invoices: posted records, invoice_date, stored currency conversions')
    if 'purchases' in categories and _has_bi:
        scope.require(module='core', permission='purchase')
        metrics['purchases'] = str(sum((base_amount(r, 'base_grand_total', 'grand_total', currency)
                                      for r in purchase_query(cdb, filters, start, end)), Decimal(0)))
        sources.append('purchase_invoices: posted records, invoice_date')
    if 'receivables' in categories:
        scope.require(module='core', permission='customer_invoices')
        scope.require(permission='receipts_payments')
        invoices = sales_query(cdb, filters, end=end).all()
        metrics['outstanding'] = str(sum((max(base_balance(r, currency), Decimal(0)) for r in invoices), Decimal(0)))
        metrics['overdue_invoice_count'] = sum(bool(r.due_date and r.due_date < end and base_balance(r, currency) > 0) for r in invoices)
        sources.append('customer_invoices.balance: current balance, as of generation (not historical aging)')
    if 'collections' in categories:
        scope.require(module='core', permission='receipts_payments')
        scope.require(permission='cash')
        scope.require(permission='bank')
        total = Decimal(0)
        for model in (CashTransaction, BankTransaction):
            for row in cdb.query(model).filter(model.company_id == scope.company_id, model.date >= start,
                                               model.date <= end, model.applied_ci_id.is_not(None)):
                # Only structurally linked customer collections, not arbitrary cash income.
                if row.type.lower() in ('receipt', 'credit', 'income', 'in'):
                    total += Decimal(str(row.amount or 0))
        metrics['linked_customer_collections'] = str(total)
        sources.append('cash_transactions/bank_transactions: customer-invoice-linked receipts only')
    if 'quotations' in categories and CRMQuotation is not None:
        scope.require(module='crm')
        metrics['pending_quotations'] = cdb.query(CRMQuotation).filter_by(company_id=scope.company_id, status='Sent').count()
        sources.append('crm_quotations.status=Sent: current snapshot')
    if 'workshop' in categories and WorkshopJobCard is not None:
        scope.require(module='repair')
        metrics['pending_workshop_jobs'] = cdb.query(WorkshopJobCard).filter(WorkshopJobCard.company_id == scope.company_id,
            WorkshopJobCard.status.notin_(('Delivered', 'Cancelled', 'Closed'))).count()
        sources.append('workshop_job_cards.status: current snapshot')
    if 'stock' in categories:
        scope.require(module='orderflow', permission='stock')
        metrics['zero_stock_items'] = cdb.query(StockItem).filter(StockItem.company_id == scope.company_id, StockItem.quantity <= 0).count()
        sources.append('stock_items.quantity<=0: current snapshot; no assumed reorder threshold')
    return {'company_id': scope.company_id, 'app_type': 'erp', 'period': {'from': start.isoformat(), 'to': end.isoformat()},
            'generated_at': now().isoformat() + 'Z', 'currency': currency, 'metrics': metrics, 'sources': sources,
            'recipient': scope.actor, 'summary': '\n'.join(f'{k.replace("_", " ").capitalize()}: {v}' for k, v in metrics.items())}


def eship_briefing(cdb, scope, start, end, currency='INR', categories=None):
    """Calculate eShip logistics briefing metrics strictly from database records."""
    from customer_models import Invoice, CashTransaction, BankTransaction
    from ..models import now
    scope.require(owner=True)
    categories = categories or ('shipments', 'billing', 'receivables', 'collections', 'alerts')
    prev_start = start - (end - start) - timedelta(days=1)
    prev_end = start - timedelta(days=1)

    active_invoices = [
        inv for inv in cdb.query(Invoice).filter(
            Invoice.company_id == scope.company_id,
            Invoice.date >= start,
            Invoice.date <= end,
        ).all()
        if (inv.status or '').strip().lower() not in ('void', 'draft', 'cancelled', 'canceled')
    ]
    prev_invoices = [
        inv for inv in cdb.query(Invoice).filter(
            Invoice.company_id == scope.company_id,
            Invoice.date >= prev_start,
            Invoice.date <= prev_end,
        ).all()
        if (inv.status or '').strip().lower() not in ('void', 'draft', 'cancelled', 'canceled')
    ]

    delivered = 0
    pending = 0
    exceptions = 0
    for inv in active_invoices:
        try:
            meta = json.loads(inv.terms or '{}') if isinstance(inv.terms, str) else (inv.terms or {})
        except Exception:
            meta = {}
        t_status = str((meta if isinstance(meta, dict) else {}).get('tracking_status') or 'Booked').strip().lower()
        if 'deliver' in t_status and 'out for' not in t_status and 'exception' not in t_status:
            delivered += 1
        elif 'return' in t_status or 'exception' in t_status:
            exceptions += 1
        else:
            pending += 1

    total_billing = sum((_money(inv.grand_total) for inv in active_invoices), Decimal(0)).quantize(Decimal('.01'))
    prev_billing = sum((_money(inv.grand_total) for inv in prev_invoices), Decimal(0)).quantize(Decimal('.01'))

    all_unpaid = [
        inv for inv in cdb.query(Invoice).filter(Invoice.company_id == scope.company_id).all()
        if (inv.status or '').strip().lower() not in ('void', 'draft', 'cancelled', 'canceled', 'paid')
    ]
    outstanding = sum(
        (max(min(_money(inv.balance), _money(inv.grand_total) - _money(inv.paid_amount)), Decimal(0)) for inv in all_unpaid),
        Decimal(0),
    ).quantize(Decimal('.01'))

    payments_received = Decimal(0)
    for model in (CashTransaction, BankTransaction):
        for row in cdb.query(model).filter(model.company_id == scope.company_id, model.date >= start, model.date <= end).all():
            if (getattr(row, 'type', '') or '').lower() in ('income', 'credit', 'receipt', 'in'):
                payments_received += _money(row.amount)
    payments_received = payments_received.quantize(Decimal('.01'))

    alerts = []
    if exceptions > 0:
        alerts.append(f"{exceptions} shipment(s) recorded with delivery exception / return status.")
    if pending > 0:
        alerts.append(f"{pending} shipment(s) currently in pending / transit stages.")
    if outstanding > Decimal(0):
        alerts.append(f"Outstanding customer receivables: {currency} {outstanding}.")

    metrics = {
        'shipments_booked': len(active_invoices),
        'previous_period_shipments': len(prev_invoices),
        'total_billing_amount': str(total_billing),
        'previous_period_billing': str(prev_billing),
        'delivered_shipments': delivered,
        'pending_shipments': pending,
        'exception_shipments': exceptions,
        'outstanding_receivables': str(outstanding),
        'payments_received': str(payments_received),
        'operational_alerts': alerts,
    }
    sources = [
        'invoices: active bookings (excluding Void/Draft/Cancelled), date, grand_total, terms.tracking_status',
        'invoices.balance: live outstanding receivables snapshot',
        'cash_transactions/bank_transactions: recorded receipts within period',
    ]
    summary_lines = [
        f"Shipments booked: {metrics['shipments_booked']} (prev: {metrics['previous_period_shipments']})",
        f"Total billing amount: {currency} {metrics['total_billing_amount']} (prev: {currency} {metrics['previous_period_billing']})",
        f"Delivered: {delivered} | Pending/In-Transit: {pending} | Exceptions: {exceptions}",
        f"Payments received: {currency} {metrics['payments_received']} | Outstanding receivables: {currency} {metrics['outstanding_receivables']}",
    ]
    return {
        'company_id': scope.company_id,
        'app_type': 'eship',
        'period': {'from': start.isoformat(), 'to': end.isoformat()},
        'generated_at': now().isoformat() + 'Z',
        'currency': currency,
        'metrics': metrics,
        'sources': sources,
        'recipient': scope.actor,
        'summary': '\n'.join(summary_lines),
    }


def explain_briefing_trends(report_data, provider=None):
    """Generate a grounded narrative explanation of pre-computed SQL metrics without inventing numbers."""
    metrics = report_data.get('metrics', {})
    currency = report_data.get('currency', 'INR')
    if provider is not None:
        sys_prompt = (
            "You are the Qiyadah Executive Briefing Analyst. "
            "Explain the trends and operational highlights strictly using the provided pre-calculated JSON metrics. "
            "Never invent, estimate, or alter any financial or operational numbers. "
            "Keep your summary concise (3 to 5 bullet points)."
        )
        text, usage = provider.respond(
            [
                {'role': 'system', 'content': sys_prompt},
                {'role': 'user', 'content': json.dumps({'currency': currency, 'period': report_data.get('period'), 'metrics': metrics}, ensure_ascii=False)},
            ],
            [],
            lambda *a: None,
        )
        return text, usage

    lines = []
    if 'sales' in metrics:
        curr = _money(metrics.get('sales'))
        prev = _money(metrics.get('previous_period_sales'))
        diff = curr - prev
        direction = 'increased' if diff > 0 else ('decreased' if diff < 0 else 'remained unchanged')
        lines.append(f"Sales for the period totaled {currency} {curr} ({direction} vs previous period {currency} {prev}).")
    if 'shipments_booked' in metrics:
        lines.append(
            f"Booked {metrics['shipments_booked']} shipment(s) billing {currency} {metrics.get('total_billing_amount', '0.00')} "
            f"(previous period: {metrics.get('previous_period_shipments', 0)} shipment(s), {currency} {metrics.get('previous_period_billing', '0.00')})."
        )
        lines.append(
            f"Delivery breakdown: {metrics.get('delivered_shipments', 0)} delivered, "
            f"{metrics.get('pending_shipments', 0)} pending/in-transit, and {metrics.get('exception_shipments', 0)} exception(s)."
        )
    if 'outstanding' in metrics:
        lines.append(f"Receivables outstanding stand at {currency} {metrics['outstanding']} with {metrics.get('overdue_invoice_count', 0)} overdue invoice(s).")
    if 'outstanding_receivables' in metrics:
        lines.append(f"Logistics receivables outstanding: {currency} {metrics['outstanding_receivables']}; payments collected in period: {currency} {metrics.get('payments_received', '0.00')}.")
    if 'pending_quotations' in metrics or 'pending_workshop_jobs' in metrics or 'zero_stock_items' in metrics:
        ops = []
        if 'pending_quotations' in metrics:
            ops.append(f"{metrics['pending_quotations']} sent quotation(s) awaiting customer response")
        if 'pending_workshop_jobs' in metrics:
            ops.append(f"{metrics['pending_workshop_jobs']} active workshop job(s)")
        if 'zero_stock_items' in metrics:
            ops.append(f"{metrics['zero_stock_items']} zero-stock item(s)")
        lines.append("Operational snapshot: " + ", ".join(ops) + ".")
    return " ".join(lines) if lines else report_data.get('summary', ''), {}

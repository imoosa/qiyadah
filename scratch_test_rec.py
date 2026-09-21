import sys
from datetime import date, timedelta
from db_router import get_customer_session
from customer_models import Client, Invoice
from utils.query_engine import _compute_outstanding_for_all_clients

company_id = 'test'
cdb = get_customer_session(company_id)

all_clients = cdb.query(Client).filter(
    Client.company_id == company_id,
    Client.status != "Deleted",
    ~Client.client_type.in_(["Supplier", "Cash-Only"]),
).all()

balances = _compute_outstanding_for_all_clients(cdb, company_id, all_clients)
print(f"Total clients: {len(all_clients)}")
print(f"Total live outstanding (positive sum): {sum(b for b in balances.values() if b > 0)}")

# Check invoices
invs = cdb.query(Invoice).filter(Invoice.company_id == company_id).all()
print(f"Total invoices: {len(invs)}")
for inv in invs[:5]:
    print(f"Inv #{inv.invoice_number} date={inv.date} grand_total={inv.grand_total} paid={inv.paid_amount} balance={inv.balance} status={inv.status}")

"""
ai_assistant.py  (Logistics ERP / Magnustic ERP version)
─────────────────────────────────────────────────────────
Two strictly separate response paths, same as AssetPro's version:

1. EXPLAIN path — user asked about THEIR company's records. The DB answer
   is already 100% correct before Ollama ever sees it; Ollama's only job
   is to phrase it in plain English. It must never add, infer, or correct
   a number.

2. GENERAL path — user asked a general accounting/GST/logistics-business
   question with no DB lookup involved (e.g. "what's the CGST/SGST split
   for an intra-state sale", "what's a debit note used for"). Ollama
   answers from its own knowledge. This path NEVER sees another
   company's data because no DB call happens on this path at all.

The two paths are never merged into one prompt. That separation is the
entire reason a llama3.2-sized model can be trusted not to blend a real
receivables figure with a guessed one.

A third path — APP META — answers static questions about the platform
itself (who built it, when). This is handled BEFORE either of the above,
deterministically, with no Ollama involvement at all. That's deliberate:
a keyword-matched canned string can't be talked out of its answer the
way a prompt instruction can. See _classify_app_meta().
"""

import json
import re
import random
from typing import Dict, Any
import ollama

from db_router import get_customer_session


class LogisticsAIAssistant:

    def __init__(self, model_name: str = "llama3.2"):
        self.model_name = model_name
        self.context_window = []
        self.max_context = 6

    # ── App metadata (static, no DB, no Ollama) ─────────────────────────

    APP_NAME = "Qiyadah"
    APP_MAKER = "Qiyadah"
    APP_BUILD_DATE = "10 July 2026"

    APP_INFO_RESPONSE = (
        f"This platform is {APP_NAME}, built by {APP_MAKER}. "
        f"It was released on {APP_BUILD_DATE}."
    )

    OWNER_INFO_RESPONSE = (
        "I'm not able to share ownership or personal contact details for this platform. "
        "For business or support enquiries, please use the contact details provided "
        "within the app itself."
    )

    # Owner/identity questions are checked FIRST and win over app-info
    # keywords, since a phrase like "who owns this app" contains "this app"
    # but is really an owner question, not a generic "what is this" question.
    _OWNER_SIGNALS = [
        "who is the owner", "who owns this", "owner of this app", "owner name",
        "who is behind this", "contact owner", "owner details", "owner contact",
        "who is ibrahim", "developer's name", "developer contact",
        "developer phone", "developer email", "developer number",
    ]

    _APP_INFO_SIGNALS = [
        "who made this app", "who developed this", "who is the developer",
        "who built this", "which company made this", "who created this app",
        "app made by", "about this app", "app info", "when was this app made",
        "who designed this app", "who owns qiyadah", "who owns magnustic",
    ]

    # Plain greetings — matched on the WHOLE message (after stripping
    # punctuation), not a substring check. A substring check would swallow
    # real questions like "hi, what are my total sales" into a canned
    # reply and never reach the router. Keep this list to bare greetings
    # only; anything with real content after the greeting falls through
    # to normal classification.
    _GREETING_EXACT = {
        "hi", "hii", "hiii", "hiiii", "hello", "helo", "hey", "heya", "hy",
        "yo", "sup", "hola", "good morning", "good afternoon", "good evening",
        "gm", "ge", "namaste",
    }
    GREETING_RESPONSES = [
        (
            "Hi! I'm Qiyadah AI. Welcome to Qiyadah. I can help you with "
            "sales, purchases, invoices, inventory, shipments, GST, customer and "
            "supplier accounts, cash, bank balances, expenses, and business reports. "
            "What would you like to know?"
        ),
        (
            "Hello! I'm Qiyadah AI. Welcome to Qiyadah. Whether you need "
            "today's sales, outstanding payments, stock status, shipment tracking, "
            "GST reports, customer balances, or business insights, I'm here to help. "
            "How can I assist you today?"
        ),
        (
            "Welcome! I'm Qiyadah AI. Welcome to Qiyadah. Ask me anything about "
            "your business—from invoices and purchases to logistics, manifests, "
            "inventory, banking, expenses, profits, and analytics. What would you "
            "like to explore?"
        ),
        (
            "Hi there! I'm Qiyadah AI. Welcome to Qiyadah. I can answer "
            "questions about your sales, purchases, customers, suppliers, inventory, "
            "shipments, GST, finances, and overall business performance. "
            "What can I help you with today?"
        ),
        (
            "Hello! I'm Qiyadah AI. Welcome to Qiyadah, your intelligent "
            "business assistant. Try asking things like 'Show today's sales', "
            "'What's my GST payable?', 'Who owes me money?', or 'What is my "
            "total purchase this month?'."
        ),
    ]

    def _classify_greeting(self, message: str) -> bool:
        msg = message.lower().strip().strip("!.?, ")
        return msg in self._GREETING_EXACT

    def _classify_app_meta(self, message: str) -> str:
        """Returns 'owner_info', 'app_info', or '' (no match)."""
        msg = message.lower()
        if any(s in msg for s in self._OWNER_SIGNALS):
            return "owner_info"
        if any(s in msg for s in self._APP_INFO_SIGNALS):
            return "app_info"
        return ""

    # ── System prompts ───────────────────────────────────────────────────

    EXPLAIN_SYSTEM = """You are Qiyadah AI, an assistant for a logistics/courier company's
ERP system in India. You are currently answering for ONE specific company only —
the JSON data you are given has already been fetched from that company's own
isolated database. It contains nothing from any other company. Never claim to
have, or offer to fetch, data belonging to any other company.

Your ONLY job is to explain the JSON data in plain English. The JSON is 100%
accurate — never contradict it, never invent numbers, never fill in a figure
that isn't present in the JSON.

Today's date is {today_date}. Use this for date comparisons (overdue, expiring).

Rules:
- Summarise in 2-4 plain English sentences
- Use ₹ for all money values
- If a "found": false field is present, say clearly that nothing matched
- Lead with the most important risk (overdue payment, low stock, pending manifest)
- If a list/count is 0 or empty, say so plainly — don't skip it
- DO NOT output JSON, bullet points, markdown, or code blocks
- DO NOT guess or round figures beyond what's given
- Keep it under 5 sentences
"""

    GENERAL_SYSTEM = """You are Qiyadah AI, an intelligent, helpful assistant for a logistics/courier
company's ERP system in India. You answer questions about:

1. Questions about THIS company's own records — these are already answered with
   real DB data before this message; you are not doing that here.
2. How to use the ERP features & settings:
   - Giving access to employees: Settings ⚙️ -> Manage Employees/Users -> "+ Add Employee" -> enter name, email, password, and select role (Employee, Accountant, Manager) -> configure permissions under Settings -> Role Permissions.
   - Changing password: Top-right user avatar menu -> "Change Password" -> enter current and new password -> Update.
   - Company Settings: Settings ⚙️ -> Company Profile -> edit company name, GSTIN, registered address, logo, invoice prefixes, terms & conditions, and bank details.
   - Plans & Upgrades: Settings ⚙️ -> Subscription & Billing -> select plan (Starter, Professional, Enterprise, Lifetime) -> click Upgrade Plan to pay via Razorpay/UPI.
   - Creating Bookings (AWB), Customer Aggregate Invoices, Purchase Invoices, Manifests, Cash/Bank receipts, and Price Lists.
3. General accounting, GST (CGST/SGST/IGST, reverse charge, HSN codes, e-way bills), logistics, and freight taxation concepts.

Rules:
- Give clear, helpful, step-by-step answers for how-to questions.
- Use ₹ for Indian currency context.
- Keep answers structured with bullet points or numbered steps when describing a process.
- NEVER fabricate company-specific financial numbers on this path.
- NEVER reveal personal contact details of developers/owners.
"""

    def _explain(self, data: Dict[str, Any], user_message: str) -> str:
        from datetime import date
        today_str = date.today().strftime("%d %b %Y")
        system_prompt = self.EXPLAIN_SYSTEM.replace("{today_date}", today_str)

        prompt = (
            f"User asked: {user_message}\n\n"
            f"Database returned this data (already scoped to their own company only):\n"
            f"{json.dumps(data, indent=2, default=str)}\n\n"
            f"Write 2-4 plain English sentences summarising this for a non-technical user. "
            f"Use ₹ for money. No JSON, no bullet points, no markdown."
        )
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                options={"temperature": 0.3, "num_predict": 250, "num_threads": 2, "num_ctx": 2048},
            )
            reply = response["message"]["content"].strip()
            reply = re.sub(r'\{.*?\}', '', reply, flags=re.DOTALL).strip()
            reply = re.sub(r'\[.*?\]', '', reply, flags=re.DOTALL).strip()
            return reply if len(reply) > 20 else self._fallback_format(data)
        except Exception as e:
            print(f"[OLLAMA ERROR] _explain: {e}")
            return self._fallback_format(data)

    _RECORD_SIGNALS = [
        "my ", "our ", "we owe", "who owes", "show me", "list my",
        "how many do i", "how many do we", "what did i", "when did i",
        "details of my", "info on my", "outstanding", "outsating", "outstandng", "outstnding",
        "pending", "pendng", "payable", "payble",
        "balance", "invoice", "client", "supplier", "stock", "cash",
        "bank", "loan", "cheque", "manifest", "expense", "sales", "revenue",
        "profit", "booking", "void", "cancelled", "price list",
        "whatsapp", "how many users", "how many owners", "how many employees",
        "sales", "purchase", "expense", "cash", "bank", "receipt", "payment",
        "estimate", "quotation", "awb", "docket", "manifest", "courier", "city",
        "destination", "ledger", "statement", "top", "overdue", "new client",
        "electronics", "logistics", "technologies", "enterprises", "traders", "corporation", "solutions",
    ]

    def _is_record_question(self, message: str) -> bool:
        msg = message.lower()
        # "How-to", "how do I", "where is", "how can I", "guide", "steps" are process/help questions, not database record searches
        how_to_prefixes = [
            "how to", "how do i", "how can i", "how we", "steps to", "guide for",
            "where is", "where can i", "where do i", "what is the process",
            "how does", "what are the steps", "how to give", "how to add",
            "how to change", "how to upgrade", "how to reset",
        ]
        if any(p in msg for p in how_to_prefixes):
            return False
        return any(s in msg for s in self._RECORD_SIGNALS)

    def _general_answer(self, user_message: str, not_found: bool = False) -> str:
        if not_found:
            reply = (
                "I searched your company's records but couldn't find a matching client, supplier, invoice, or booking. "
                "Try searching with the exact name, client/supplier ID, or AWB/docket number, or type 'help' for all questions."
            )
            self.context_window.append({"role": "user", "content": user_message})
            self.context_window.append({"role": "assistant", "content": reply})
            return reply

        self.context_window.append({"role": "user", "content": user_message})
        if len(self.context_window) > self.max_context:
            self.context_window = self.context_window[-self.max_context:]

        messages = [{"role": "system", "content": self.GENERAL_SYSTEM}] + self.context_window
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=messages,
                options={"temperature": 0.5, "num_predict": 400, "num_threads": 2, "num_ctx": 2048},
            )
            reply = response["message"]["content"].strip()
        except Exception as e:
            print(f"[OLLAMA ERROR] _general_answer: {e}")
            reply = (
                "I searched your company's records but couldn't find a match. "
                "You can ask for bookings, sales periods, purchase payables, client/supplier balances (e.g. 'Pending amount of ABC'), or type 'help' for all questions."
            )

        self.context_window.append({"role": "assistant", "content": reply})
        return reply

    @staticmethod
    def _fallback_format(data: Dict[str, Any]) -> str:
        """Deterministic plain-text summary if Ollama is unavailable."""
        intent = data.get("intent", "")

        if intent == "dashboard_summary":
            return (
                f"{data['total_clients']} clients, {data['total_suppliers']} suppliers. "
                f"Pending invoices: {data['pending_invoices']}. "
                f"Receivable: ₹{data['total_receivable']:,.0f}, Payable: ₹{data['total_payable']:,.0f}. "
                f"Cash: ₹{data['cash_balance']:,.0f}, Bank: ₹{data['bank_balance']:,.0f}."
            )
        if intent == "sales_summary":
            period = data.get("period_label") or (f"{data['start_date']} to {data['end_date']}" if data.get("start_date") else (f"over the last {data['period_months']} month(s)" if data.get("period_months") else "all-time"))
            return (
                f"Sales ({period}): ₹{data['total_sales']:,.0f} across {data['invoice_count']} invoice(s). "
                f"Collected: ₹{data['total_collected']:,.0f}, Pending: ₹{data['total_pending']:,.0f} (Avg: ₹{data.get('avg_invoice', 0):,.0f})."
            )
        if intent == "purchase_summary":
            period = f"{data['start_date']} to {data['end_date']}" if data.get("start_date") else (f"over the last {data['period_months']} month(s)" if data.get("period_months") else "all-time")
            return (
                f"Total purchase {period}: ₹{data['total_purchase']:,.0f} across {data['invoice_count']} invoice(s). "
                f"Paid: ₹{data['total_paid']:,.0f}, still pending: ₹{data['total_pending']:,.0f}."
            )
        if intent == "gst_summary":
            period = f"{data.get('start_date', '')} to {data.get('end_date', '')}" if data.get("start_date") else (f"over the last {data['period_months']} month(s)" if data.get("period_months") else "all-time")
            return (
                f"GST {period}: collected on sales ₹{data['output_gst']:,.0f}, paid on purchases "
                f"₹{data['input_gst']:,.0f}. Net GST {data['net_gst_status']}: ₹{abs(data['net_gst']):,.0f}."
            )
        if intent in ("client_detail", "supplier_detail"):
            if not data.get("found"):
                return f"No match found for '{data.get('query', '')}'."
            key = "pending_amount" if intent == "client_detail" else "payable_amount"
            return (
                f"{data['name']} — {data.get('phone', 'no phone')}, "
                f"GST: {data.get('gst_number') or 'not set'}. "
                f"Amount {'pending' if intent == 'client_detail' else 'payable'}: ₹{data.get(key, 0):,.0f}."
            )
        if intent in ("invoice_detail", "purchase_invoice_detail"):
            if not data.get("found"):
                return f"No invoice found matching '{data.get('query', '')}'."
            return (
                f"{data['invoice_id']} — {data.get('client') or data.get('supplier')}, "
                f"total ₹{data['grand_total']:,.0f}, balance ₹{data['balance']:,.0f}, status {data['status']}."
            )
        if intent == "pending_receivables":
            lines = [
                f"💰 **Total Outstanding Receivables**: **₹{data['total_outstanding']:,.0f}** across {data['count']} client(s) with pending balance.",
            ]
            if data.get("items"):
                lines.append("\n**Top Outstanding Clients**:")
                for item in data["items"][:5]:
                    lines.append(f"• **{item['client']}**: ₹{item['balance']:,.0f}")
            return "\n".join(lines)
        if intent == "pending_payables":
            overdue_txt = f" (Overdue: ₹{data.get('overdue_amount', 0):,.0f} across {data.get('overdue_count', 0)} bill(s))" if data.get('overdue_count') else ""
            return f"Total Payable from Purchase: ₹{data.get('total_payable', data.get('total_outstanding', 0)):,.0f} across {data['count']} unpaid purchase bill(s).{overdue_txt}"
        if intent == "cash_summary":
            return f"Cash in hand: ₹{data['cash_balance']:,.0f}."
        if intent == "bank_summary":
            return f"Total bank balance: ₹{data['total_balance']:,.0f} across {len(data['accounts'])} account(s)."
        if intent == "expenses_summary":
            period = f"{data['start_date']} to {data['end_date']}" if data.get("start_date") else f"over {data['period_months']} month(s)"
            return f"Total expenses {period}: ₹{data['total_expenses']:,.0f}."
        if intent == "stock_summary":
            return f"{data['total_items']} stock items, {data['low_stock_count']} below reorder level."
        if intent == "manifest_summary":
            return f"{data['total_manifests']} manifests in the last {data['period_days']} days, {data['pending_manifests']} pending."
        if intent == "loans_summary":
            return f"{data['active_loans']} active loans, ₹{data['total_outstanding']:,.0f} outstanding."
        if intent == "cheques_summary":
            return (
                f"Pending cheques received: {data['pending_received_count']} "
                f"(₹{data['pending_received_amount']:,.0f}). "
                f"Pending cheques issued: {data['pending_issued_count']} "
                f"(₹{data['pending_issued_amount']:,.0f})."
            )
        if intent == "net_profit_summary":
            period = f"{data['start_date']} to {data['end_date']}" if data.get("start_date") else (f"over the last {data['period_months']} month(s)" if data.get("period_months") else "all-time")
            status_word = "profitable" if data.get('is_profitable', True) else "running at a loss"
            net_margin = data.get("net_profit_margin_percent", 0.0)
            gross_margin = data.get("gross_profit_margin_percent", 0.0)
            return (
                f"📊 **Net Profit ({period})**: ₹{data['net_profit']:,.0f} (Net Margin: **{net_margin}%** — {status_word})\n"
                f"• **Total Sales (Revenue)**: ₹{data['total_sales']:,.0f}\n"
                f"• **Direct Purchase Costs**: ₹{data['total_purchase']:,.0f}\n"
                f"• **Operating Expenses**: ₹{data['total_expenses']:,.0f}\n"
                f"• **Gross Profit**: ₹{data['gross_profit']:,.0f} (Gross Margin: {gross_margin}%)"
            )
        if intent == "gross_profit_summary":
            period = f"{data['start_date']} to {data['end_date']}" if data.get("start_date") else (f"over the last {data['period_months']} month(s)" if data.get("period_months") else "all-time")
            gross_margin = data.get("gross_profit_margin_percent", 0.0)
            return (
                f"📊 **Gross Profit ({period})**: ₹{data['gross_profit']:,.0f} (Gross Margin: **{gross_margin}%**)\n"
                f"• **Total Sales**: ₹{data['total_sales']:,.0f}\n"
                f"• **Direct Purchase Cost**: ₹{data['total_purchase']:,.0f}"
            )
        if intent == "bookings_list":
            return f"{data['total_bookings']} booking(s) in the last {data['period_days']} days."
        if intent == "void_cancelled_list":
            return f"{data['total_void_cancelled']} void/cancelled booking(s) in the last {data['period_days']} days."
        if intent in ("client_count", "all_clients_summary"):
            return f"{data['total_clients']} client(s), {data.get('active_clients', 0)} active."
        if intent in ("supplier_count", "all_suppliers_summary"):
            return f"{data['total_suppliers']} supplier(s)."
        if intent == "price_list_status":
            if not data.get("found"):
                return f"No price list found matching '{data.get('query', '')}'."
            return (
                f"Most recent price list upload: {data['most_recent_courier']} "
                f"on {data['most_recent_upload']}."
            )
        if intent == "whatsapp_status":
            if not data.get("found"):
                return "Couldn't find your company's WhatsApp settings."
            return "WhatsApp is connected." if data["connected"] else "WhatsApp is not connected."
        if intent == "user_count_summary":
            role_bits = ", ".join(f"{v} {k}" for k, v in data["by_role"].items())
            return f"{data['total_users']} user(s) total ({role_bits}), {data['active_users']} active."

        # ── NEW FORMATTERS ───────────────────────────────────────────────────
        if intent == "todays_sales":
            return f"Today's Sales: ₹{data['total_sales']:,.0f} across {data['invoice_count']} invoice(s). Collected: ₹{data['total_collected']:,.0f}, Pending: ₹{data['total_pending']:,.0f}."
        if intent == "todays_bookings":
            return f"Today's Bookings: {data['total_bookings']} booking(s) totaling ₹{data['total_value']:,.0f}."
        if intent == "overdue_invoices":
            return f"Overdue: {data['count']} invoice(s) totaling ₹{data['total_overdue']:,.0f}."
        if intent == "top_clients_sales":
            return f"Top {data.get('limit', 10)} clients generated sales for the requested period."
        if intent == "worst_clients_sales":
            return f"Bottom {data.get('limit', 10)} least active clients by sales for the requested period."
        if intent == "top_clients_outstanding":
            return f"Top {data.get('limit', 10)} clients with highest outstanding balances."
        if intent == "awb_detail":
            if not data.get("found"):
                return f"No booking/shipment found matching '{data.get('query', '')}'. Please check the AWB/docket number."
            dest_txt = f", Destination: {data['destination']}" if data.get('destination') and data['destination'] != '-' else ""
            carrier_txt = f", Carrier: {data['carrier']}" if data.get('carrier') and data['carrier'] != '-' else ""
            wt_txt = f", Weight: {data['weight_kg']} kg" if data.get('weight_kg') else ""
            return (
                f"AWB/Docket: {data['docket_no']} (Invoice: {data['invoice_id']}) — Client/Shipper: {data['client_name']}{dest_txt}{carrier_txt}{wt_txt}, "
                f"Total: ₹{data['grand_total']:,.0f}, Paid: ₹{data['paid_amount']:,.0f}, Balance: ₹{data['balance']:,.0f}, Status: {data['status']}, Date: {data['booking_date']}."
            )
        if intent == "todays_expenses":
            return f"Today's Expenses: {data['count']} expense(s) totaling ₹{data['total_expenses']:,.0f}."
        if intent == "expenses_category":
            return f"Expenses for '{data['category']}': {data['count']} item(s) totaling ₹{data['total_expenses']:,.0f}."
        if intent == "todays_cash":
            return f"Cash Today: In ₹{data['cash_in_today']:,.0f}, Out ₹{data['cash_out_today']:,.0f}. Net: ₹{data['net_today']:,.0f}. Running Balance: ₹{data['running_balance']:,.0f}."
        if intent == "receipts_payments_summary":
            return f"Receipts: ₹{data['total_receipts']:,.0f} (Cash: ₹{data['cash_receipts']:,.0f}, Bank: ₹{data['bank_receipts']:,.0f}). Payments: ₹{data['total_payments']:,.0f}. Net flow: ₹{data['net_flow']:,.0f}."
        if intent == "client_statement":
            if not data.get("found"):
                return f"No client found matching '{data.get('query', '')}'."
            return f"Statement for {data['name']}: Total Invoiced ₹{data['total_invoiced']:,.0f}, Collected ₹{data['total_collected']:,.0f}, Pending ₹{data['total_pending']:,.0f}."
        if intent == "supplier_statement":
            if not data.get("found"):
                return f"No supplier found matching '{data.get('query', '')}'."
            return f"Statement for {data['name']}: Total Purchased ₹{data['total_purchased']:,.0f}, Paid ₹{data['total_paid']:,.0f}, Pending ₹{data['total_pending']:,.0f}."
        if intent == "estimate_summary":
            return f"Estimates: {data['count']} estimate(s) totaling ₹{data['total_value']:,.0f}."
        if intent == "estimate_detail":
            if not data.get("found"):
                return f"No estimate found matching '{data.get('query', '')}'."
            return f"Estimate {data['estimate_id']} for {data['client']}: ₹{data['grand_total']:,.0f}, Status: {data['status']}."
        if intent == "top_suppliers_purchase":
            return f"Top {data.get('limit', 10)} suppliers by purchase for the requested period."
        if intent == "destination_analysis":
            return f"Destination Analysis: {data['total_destinations']} cities shipped to."
        if intent == "courier_analysis":
            return f"Courier Analysis: Breakdown of shipments by courier partner."
        if intent == "new_clients":
            return f"New Clients: {data['count']} new client(s) registered."
        if intent == "customer_invoice_summary":
            return f"Customer Invoices: {data['count']} aggregate invoice(s) totaling ₹{data['total_value']:,.0f}."
        if intent == "customer_invoice_detail":
            if not data.get("found"):
                return f"No customer invoice found matching '{data.get('query', '')}'."
            return (
                f"Customer Invoice {data['invoice_number']} for {data['client_name']}: "
                f"Grand Total ₹{data['grand_total']:,.0f}, Paid ₹{data['paid_amount']:,.0f}, "
                f"Balance ₹{data['balance']:,.0f}, Status: {data['status']}, Items: {data['item_count']} booking(s)."
            )
        if intent in ("party_outstanding", "client_pending_amount"):
            if not data.get("found"):
                return f"No client or supplier found matching '{data.get('query', '')}'. Please check the spelling or search by ID/phone."
            if data.get("party_type") == "Supplier":
                overdue_txt = f" Overdue: ₹{data['overdue_amount']:,.0f} ({data['overdue_count']} bill(s))." if data.get('overdue_count') else ""
                return (
                    f"Supplier: {data['name']} — Payable: ₹{data['payable_amount']:,.0f} across {data['unpaid_count']} unpaid bill(s). "
                    f"Credit Limit: ₹{data['credit_limit']:,.0f} ({data['credit_days']} days).{overdue_txt}"
                )
            overdue_txt = f" Overdue: ₹{data['overdue_amount']:,.0f} ({data['overdue_count']} invoice(s))." if data.get('overdue_count') else ""
            return (
                f"Client: {data['name']} — Pending: ₹{data['pending_amount']:,.0f} across {data['unpaid_count']} unpaid invoice(s). "
                f"Credit Limit: ₹{data['credit_limit']:,.0f} ({data['credit_days']} days).{overdue_txt} "
                f"Last Payment: {data.get('last_payment', 'N/A')}."
            )
        if intent == "party_outstanding_both":
            return (
                f"Party: {data['name']} (Client & Supplier) — "
                f"Receivable from Client: ₹{data['client_pending']:,.0f}, Payable to Supplier: ₹{data['supplier_payable']:,.0f}."
            )
        if intent == "supplier_payable_amount":
            if not data.get("found"):
                return f"No supplier found matching '{data.get('query', '')}'."
            overdue_txt = f" Overdue: ₹{data['overdue_amount']:,.0f} ({data['overdue_count']} bill(s))." if data.get('overdue_count') else ""
            return (
                f"Supplier: {data['name']} — Payable: ₹{data['payable_amount']:,.0f} across {data['unpaid_count']} unpaid bill(s). "
                f"Credit Limit: ₹{data['credit_limit']:,.0f} ({data['credit_days']} days).{overdue_txt}"
            )
        if intent == "bank_account_detail":
            if not data.get("found"):
                return f"No specific bank account matched '{data.get('query', '')}'."
            return f"Bank Account {data['bank_name']} ({data['account_number']}): Balance ₹{data['balance']:,.0f}."
        if intent == "pending_manifests":
            return f"Pending Manifests: {data['count']} manifest(s) with {data['total_boxes']} total boxes waiting."
        if intent == "help":
            return (
                "Here are the categories of questions you can ask me about your business. "
                "Click on any category or question to get instant, accurate answers directly from your database."
            )

        if intent == "country_bookings_summary":
            period = f"{data['start_date']} to {data['end_date']}" if data.get("start_date") else (f"over the last {data['period_months']} month(s)" if data.get("period_months") else "all-time")
            if not data.get("found"):
                return f"No active bookings found for {data.get('country', 'the specified country')} ({period})."
            if data.get("breakdown"):
                lines = [
                    f"🌍 **Country-wise Bookings, Sales & Profit ({period})**:",
                    f"• Total Countries: {data['total_countries']} | Total Bookings: {data['total_bookings']} | Sales: ₹{data['total_sales']:,.0f} | Purchases: ₹{data['total_purchase']:,.0f} | Profit: ₹{data['profit']:,.0f} (Margin: {data['profit_margin']}%)",
                    "",
                ]
                for c in data["breakdown"][:12]:
                    lines.append(f"• **{c['country']}**: {c['booking_count']} booking(s) | Sales: ₹{c['total_sales']:,.0f} | Purchases: ₹{c['total_purchase']:,.0f} | Profit: ₹{c['profit']:,.0f} ({c['profit_margin']}%)")
                return "\n".join(lines)
            else:
                lines = [
                    f"🌍 **{data['country']}** Booking & Profit Summary ({period}):",
                    f"• **Total Bookings**: {data['booking_count']} booking(s)",
                    f"• **Total Sales (Billed)**: ₹{data['total_sales']:,.0f}",
                    f"• **Direct Purchase Cost**: ₹{data['total_purchase']:,.0f}",
                    f"• **Gross Profit**: ₹{data['profit']:,.0f} (Margin: {data['profit_margin']}%)",
                    f"• **Collected**: ₹{data['total_collected']:,.0f} | **Pending**: ₹{data['total_pending']:,.0f}",
                ]
                if data.get("top_clients"):
                    lines.append("\nTop Clients:")
                    for cl in data["top_clients"][:3]:
                        lines.append(f"  - {cl['name']}: ₹{cl['amount']:,.0f}")
                return "\n".join(lines)

        if intent == "employee_bookings_summary":
            period = f"{data['start_date']} to {data['end_date']}" if data.get("start_date") else (f"over the last {data['period_months']} month(s)" if data.get("period_months") else "all-time")
            if not data.get("found"):
                return f"No active bookings found for employee '{data.get('employee_name', '')}' ({period})."
            if data.get("breakdown"):
                lines = [
                    f"👥 **Employee-wise Bookings, Sales & Performance ({period})**:",
                    f"• Team Members: {data['total_employees']} | Total Bookings: {data['total_bookings']} | Sales: ₹{data['total_sales']:,.0f} | Profit: ₹{data['profit']:,.0f} (Margin: {data['profit_margin']}%)",
                    "",
                ]
                for emp in data["breakdown"]:
                    lines.append(f"• **{emp['employee_name']}** ({emp['role']}): {emp['booking_count']} booking(s) | Sales: ₹{emp['total_sales']:,.0f} | Purchases: ₹{emp['total_purchase']:,.0f} | Profit: ₹{emp['profit']:,.0f} ({emp['profit_margin']}%)")
                return "\n".join(lines)
            else:
                return (
                    f"👤 **{data['employee_name']}** ({data.get('role', 'Employee')}) Performance ({period}):\n"
                    f"• **Total Bookings**: {data['booking_count']} booking(s)\n"
                    f"• **Total Sales**: ₹{data['total_sales']:,.0f}\n"
                    f"• **Direct Purchase Cost**: ₹{data['total_purchase']:,.0f}\n"
                    f"• **Gross Profit**: ₹{data['profit']:,.0f} (Margin: {data['profit_margin']}%)\n"
                    f"• **Collected**: ₹{data['total_collected']:,.0f} | **Pending**: ₹{data['total_pending']:,.0f}"
                )

        if intent == "company_plan_status":
            if not data.get("found"):
                return f"Plan details not found for company {data.get('company_id', '')}. Please contact support."
            return (
                f"💳 **Subscription & Plan Details**:\n"
                f"• **Active Plan**: {data.get('plan_name', 'Standard')}\n"
                f"• **Billing Duration**: {data.get('plan_duration', '1 Year')}\n"
                f"• **Plan Validity**: {data.get('subscription_start', 'N/A')} to {data.get('subscription_end', 'Active')}\n"
                f"• **Team Seats**: {data.get('active_users', 0)} Active User(s) / {data.get('max_users', 'Unlimited')} Allowed\n"
                f"• **Max Companies**: {data.get('max_companies', 1)}\n\n"
                f"💡 *To upgrade or add more user seats, go to **Settings ⚙️ -> Subscription / Plan** or type 'How to upgrade plan'.*"
            )

        if intent == "employee_access_guide":
            roles_str = ", ".join(f"{v} {k.title()}" for k, v in data.get("roles_summary", {}).items()) if data.get("roles_summary") else "No other users yet"
            return (
                f"👥 **How to Give Access / Add an Employee to Your Company**:\n\n"
                f"1. **Navigate to Users**: Click on **Settings (⚙️)** in the sidebar or click your profile avatar at the top right -> select **Company Employees / Users**.\n"
                f"2. **Add New User**: Click the **\"+ Add Employee\"** or **\"+ Add User\"** button.\n"
                f"3. **Enter Credentials**: Fill in the Employee's **Full Name**, **Email Address**, and set their **Login Password**.\n"
                f"4. **Select Role**:\n"
                f"   • **Employee / Sales**: Access to bookings, shipments, customer invoices, and clients.\n"
                f"   • **Accountant**: Access to debtor/creditor ledgers, receipts & payments, bank/cash entries, expenses, and GST.\n"
                f"   • **Manager**: Full operational & financial view with management privileges.\n"
                f"5. **Set Granular Permissions**: To customize exact module access (view, create, edit), visit **Settings -> Role Permissions**.\n"
                f"6. **Save & Login**: Click **Save**. The employee can now log in using their email and password at the ERP login page.\n\n"
                f"📊 *Current Team Status: {data.get('active_users', 0)} active user(s) ({roles_str}).*"
            )

        if intent == "change_password_guide":
            return (
                f"🔐 **How to Change Your Password**:\n\n"
                f"1. **Profile Menu**: Click on your **User Name / Avatar** in the top-right corner of any screen.\n"
                f"2. **Select Change Password**: Click on **\"Change Password\"** from the dropdown menu (or navigate to `/change-password`).\n"
                f"3. **Enter Passwords**: Type your **Current Password**, followed by your **New Password**, and re-type to confirm.\n"
                f"4. **Update**: Click the **\"Update Password\"** button. Your new password will take effect immediately.\n\n"
                f"💡 *Company Owners can also reset forgotten passwords for staff from **Settings -> Employees / Users -> Edit**.*"
            )

        if intent == "upgrade_plan_guide":
            return (
                f"🚀 **How to Upgrade Your Subscription Plan**:\n\n"
                f"1. Go to **Settings (⚙️)** in the main sidebar.\n"
                f"2. Select **\"Subscription & Billing\"** (or **\"Plan & Pricing\"**).\n"
                f"3. Review available plans (**Starter**, **Professional**, **Enterprise**, or **Lifetime**).\n"
                f"4. Choose your billing period (**1 Year**, **3 Years**, or **Lifetime Access**).\n"
                f"5. Click **\"Upgrade Plan\"** and complete the secure payment via Razorpay / UPI / Net Banking.\n"
                f"6. Your higher user limits, multi-company slots, and advanced features will unlock automatically!\n\n"
                f"📞 *For custom enterprise quotes or offline wire transfers, reach out directly via company support.*"
            )

        if intent == "company_settings_guide":
            return (
                f"⚙️ **How to Configure Company Settings & Profile**:\n\n"
                f"1. **Open Settings**: Click on **Settings (⚙️)** from the left navigation menu.\n"
                f"2. **Company Profile**: Update your **Company Name**, **GSTIN**, **Registered Address**, and **Contact Phone/Email**.\n"
                f"3. **Branding & Logo**: Upload your company logo to appear on all Booking Receipts, Invoices, and Statements.\n"
                f"4. **Invoice & Docket Setup**: Configure your starting **Invoice Prefix**, Terms & Conditions, and Bank Account details for printouts.\n"
                f"5. **WhatsApp Integration**: Enable automated WhatsApp notifications for booking confirmations and payment reminders.\n"
                f"6. **Save Changes**: Click **\"Save Settings\"** to apply updates across all documents immediately."
            )

        if intent == "how_to_workflow_guide":
            return (
                f"📖 **Qiyadah Logistics ERP — Quick Workflow Guides**:\n\n"
                f"• **📦 Create a Booking**: Go to **Bookings -> New Booking (AWB)**. Fill in Shipper, Consignee, Destination, Package Dimensions/Weight, and Rate. Click Generate Invoice.\n"
                f"• **🧾 Customer Aggregate Invoice**: Go to **Customer Invoices -> Create Invoice**. Select client and check unbilled bookings to consolidate into one single tax invoice.\n"
                f"• **🚚 Create Manifest**: Go to **Manifest -> New Manifest**. Select carrier/co-loader, scan or check AWB dockets to dispatch, and print manifest.\n"
                f"• **💵 Record Payment / Receipt**: Go to **Receipts & Payments -> Add Receipt**. Select client, invoice reference, payment mode (Cash/Bank), and amount.\n"
                f"• **📊 View Client Statement**: Go to **Clients -> Select Client -> Statement / Ledger** to see running balance and invoices.\n"
                f"• **📈 View BI Analytics**: Go to **Analytics / BI Dashboard** for 20-point company standing, sales trends, and profit margins."
            )

        if intent == "general_tax_knowledge":
            title = data.get("title", "📊 Statutory Tax, GST & Logistics Knowledge")
            content = data.get("content", "")
            return f"{title}\n\n{content}"

        if intent == "calculate_rate_quote":
            if not data.get("found"):
                return f"No active price list found covering destination '{data.get('destination', '')}' for {data.get('weight', 0)} kg. Try searching a country like UAE, USA, UK, or visit **Sales -> Rate Calculator**."
            lines = [
                f"⚡ **Shipping Rate Quotation for {data.get('destination')}** ({data.get('weight')} kg, billed at {data.get('billable_weight')} kg):",
                "",
            ]
            for q in data.get("quotes", [])[:4]:
                best_tag = " 🏆 Best Rate" if q.get("is_best_price") else ""
                lines.append(f"• **{q['courier']}**: ₹{q['rate']:,.0f} (₹{q['rate_per_kg']:,.0f}/kg){best_tag}")
                if q.get("purchase_cost") is not None:
                    lines.append(f"   _Vendor Cost: ₹{q['purchase_cost']:,.0f} | Profit: ₹{q['margin_amount']:,.0f} ({q['margin_percent']}%)_")
            lines.append("\n💡 *To book this shipment or generate a formal estimate, go to **Sales -> Rate Calculator**.*")
            return "\n".join(lines)

        return "Data retrieved. Please ask a more specific question for a summary."

    # Maps this assistant's intents onto permissions.py's MODULES so an
    # employee/accountant role that can't view a module in the UI can't
    # get it out of the AI either.
    INTENT_PERMISSION_MODULE = {
        "dashboard_summary":        "dashboard",
        "sales_summary":            "invoices",
        "purchase_summary":         "purchase",
        "gst_summary":              "analytics",
        "country_bookings_summary": "analytics",
        "employee_bookings_summary":"analytics",
        "client_detail":            "clients",
        "all_clients_summary":      "clients",
        "client_pending_amount":    "clients",
        "party_outstanding":        "clients",
        "party_outstanding_both":   "clients",
        "supplier_detail":          "suppliers",
        "all_suppliers_summary":    "suppliers",
        "supplier_payable_amount":  "suppliers",
        "invoice_detail":           "invoices",
        "pending_receivables":      "receipts_payments",
        "pending_payables":         "receipts_payments",
        "purchase_invoice_detail":  "purchase",
        "cash_summary":             "cash",
        "bank_summary":             "bank",
        "expenses_summary":         "expenses",
        "stock_summary":            "stock",
        "stock_item_detail":        "stock",
        "manifest_summary":         "manifest",
        "loans_summary":            "loans",
        "cheques_summary":          "cheques",
        "net_profit_summary":       "analytics",
        "gross_profit_summary":     "analytics",
        "bookings_list":            "invoices",
        "void_cancelled_list":      "invoices",
        "client_count":             "clients",
        "supplier_count":           "suppliers",
        "price_list_status":        "purchase",
        "whatsapp_status":          "settings",
        "user_count_summary":       "settings",
        "company_plan_status":      "dashboard",
        "employee_access_guide":    "dashboard",
        "change_password_guide":    "dashboard",
        "upgrade_plan_guide":       "dashboard",
        "company_settings_guide":   "dashboard",
        "how_to_workflow_guide":    "dashboard",
        "todays_sales":             "invoices",
        "todays_bookings":          "invoices",
        "overdue_invoices":         "receipts_payments",
        "top_clients_sales":        "analytics",
        "worst_clients_sales":      "analytics",
        "top_clients_outstanding":  "analytics",
        "awb_detail":               "invoices",
        "todays_expenses":          "expenses",
        "expenses_category":        "expenses",
        "todays_cash":              "cash",
        "receipts_payments_summary":"receipts_payments",
        "client_statement":         "clients",
        "supplier_statement":       "suppliers",
        "estimate_summary":         "invoices",
        "estimate_detail":          "invoices",
        "top_suppliers_purchase":   "analytics",
        "destination_analysis":     "analytics",
        "courier_analysis":         "analytics",
        "new_clients":              "clients",
        "customer_invoice_summary": "invoices",
        "customer_invoice_detail":  "invoices",
        "bank_account_detail":      "bank",
        "pending_manifests":        "manifest",
        "calculate_rate_quote":     "pricelist",
        "general_tax_knowledge":    "dashboard",
        "help":                     "dashboard",
    }

    # ── Public entry point ───────────────────────────────────────────────

    def chat(self, user_message: str, company_id: str, has_permission=None) -> Dict[str, Any]:
        """
        company_id MUST come from the authenticated session, never from
        the message text or a client-supplied field. Every DB call this
        triggers is physically bound to that company's own database.

        has_permission: pass app.py's own `has_permission(module, action)`
        function here. If omitted, this method fails closed rather than
        silently skip the permission check — an AI shortcut around the
        role matrix in permissions.py is worse than brief unavailability.
        """
        from utils.intent_router import dispatch, _clean_identifier

        if not company_id:
            return {
                "response": "I couldn't identify your company session — please log in again.",
                "data": None, "source": "error",
            }
        if has_permission is None:
            return {
                "response": "The assistant isn't configured correctly (missing permission check). "
                             "Please contact your administrator.",
                "data": None, "source": "error",
            }

        # Greetings never touch the DB or Ollama — instant, deterministic,
        # but not identical every time.
        if self._classify_greeting(user_message):
            return {"response": random.choice(self.GREETING_RESPONSES), "data": None, "source": "greeting"}

        # App-meta questions never touch the DB or Ollama — deterministic,
        # keyword-matched, checked before anything else.
        meta = self._classify_app_meta(user_message)
        if meta == "owner_info":
            return {"response": self.OWNER_INFO_RESPONSE, "data": None, "source": "app_meta_refused"}
        if meta == "app_info":
            return {"response": self.APP_INFO_RESPONSE, "data": None, "source": "app_meta"}

        data = dispatch(user_message, company_id)

        if isinstance(data, dict) and data.get("intent") is not None:
            module = self.INTENT_PERMISSION_MODULE.get(data["intent"])
            if module and not has_permission(module, "view"):
                return {
                    "response": "You don't have permission to view that information. "
                                 "Ask your company owner to grant access if you need it.",
                    "data": None, "source": "permission_denied",
                }
            
            # CRITICAL: Never use LLM for finance & entity numbers — use deterministic formatter only
            _NO_LLM_INTENTS = {
                "net_profit_summary", "gross_profit_summary", "sales_summary",
                "purchase_summary", "gst_summary", "cash_summary", "bank_summary",
                "expenses_summary", "pending_receivables", "pending_payables",
                "todays_sales", "todays_expenses", "todays_cash",
                "receipts_payments_summary", "top_clients_outstanding",
                "overdue_invoices", "top_clients_sales", "worst_clients_sales", "top_suppliers_purchase",
                "client_pending_amount", "supplier_payable_amount", "party_outstanding",
                "party_outstanding_both", "customer_invoice_detail",
                "customer_invoice_summary", "client_statement", "supplier_statement",
                "awb_detail", "invoice_detail", "purchase_invoice_detail",
                "estimate_summary", "estimate_detail", "todays_bookings",
                "bookings_list", "void_cancelled_list", "pending_manifests",
                "bank_account_detail", "help", "stock_summary", "loans_summary",
                "cheques_summary", "destination_analysis", "courier_analysis",
                "client_count", "supplier_count", "user_count_summary",
                "company_plan_status", "employee_access_guide", "change_password_guide",
                "upgrade_plan_guide", "company_settings_guide", "how_to_workflow_guide",
                "new_clients", "expenses_category", "whatsapp_status",
                "country_bookings_summary", "employee_bookings_summary",
                "calculate_rate_quote", "general_tax_knowledge",
            }
            
            if data["intent"] in _NO_LLM_INTENTS:
                response = self._fallback_format(data)
            else:
                response = self._explain(data, user_message)
            
            return {
                "response": response, "data": data,
                "source": "query_engine", "intent": data.get("intent"),
            }

        if isinstance(data, dict) and data.get("found") is False:
            response = self._explain(data, user_message)
            return {"response": response, "data": data, "source": "query_engine", "intent": None}

        # Fallback: Check if message mentions a specific party before falling back to general LLM
        from utils.query_engine import get_party_outstanding
        ident = _clean_identifier(user_message)
        if ident and len(ident) >= 2:
            p_data = get_party_outstanding(company_id, ident)
            if p_data.get("found"):
                module = "suppliers" if p_data.get("party_type") == "Supplier" else "clients"
                if not has_permission(module, "view"):
                    return {
                        "response": "You don't have permission to view that information.",
                        "data": None, "source": "permission_denied",
                    }
                return {
                    "response": self._fallback_format(p_data),
                    "data": p_data,
                    "source": "query_engine",
                    "intent": p_data.get("intent", "party_outstanding"),
                }

        # No DB intent matched.
        if self._is_record_question(user_message):
            response = self._general_answer(user_message, not_found=True)
            return {"response": response, "data": None, "source": "not_found"}

        response = self._general_answer(user_message, not_found=False)
        return {"response": response, "data": None, "source": "ai_fallback"}

    def clear_context(self):
        self.context_window = []

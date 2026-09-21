"""
OCR and PDF Invoice Extraction Engine for Qiyadah ERP Purchase Bills
Supports digital PDFs via pdfplumber/PyMuPDF and scanned PDFs/Images via pytesseract/OCR.
Extracts:
  - Supplier details (Name, GSTIN, Address, State, Phone, Email)
  - Bill details (Invoice #, Date, Due Date, PO #, Payment Terms)
  - Product line items (Name, Code, HSN, Quantity, Unit, Rate, Discount %, GST %, Line Total)
  - Financial summary totals (Subtotal, Tax, CGST/SGST/IGST, Grand Total)
"""

import os
import re
import io
from datetime import datetime, date

# GST State Code mapping to Indian States
GST_STATE_CODES = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "28": "Andhra Pradesh",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh"
}

GSTIN_REGEX = re.compile(r'\b(\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1})\b', re.IGNORECASE)
EMAIL_REGEX = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b')
PHONE_REGEX = re.compile(r'(?:(?:\+91[\-\s]?)|\b)([6-9]\d{9})\b')
HSN_REGEX = re.compile(r'\b(?:HSN|SAC)\s*(?:Code|Number|No\.?|\/)?\s*[:\-–—]?\s*(\d{4,8})\b', re.IGNORECASE)

MONTH_MAP = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4, 'june': 6,
    'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
}

COMPANY_SUFFIXES = [
    "pvt ltd", "private limited", "limited", "ltd", "llp", "inc", "corp",
    "enterprises", "technologies", "solutions", "services", "industries",
    "communications", "logistics", "trading", "agency", "tools", "hardware",
    "corporation", "co.", "company"
]

NOISE_HEADER_WORDS = [
    "tax invoice", "retail invoice", "bill of supply", "original for recipient",
    "duplicate for supplier", "triplicate", "invoice no", "invoice number",
    "invoice amount", "paid", "unpaid", "pending", "bill", "invoice", "receipt",
    "memo", "cash memo", "gstin", "date:", "order number", "due date", "total due",
    "cin:", "pan no", "page 1", "e-way", "payment due", "shipper", "shipper :",
    "consignee", "consignee / receiver", "receiver", "name", "company :", "address :",
    "destination :", "total piece"
]


def clean_num(val):
    """Convert currency / formatted number string to float"""
    if not val:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val = str(val).strip()
    # Replace common currency symbols and noise characters
    for sym in [
        "₹", "Rs.", "Rs", "$", "€", "£", "¥", "د.إ", "﷼", "د.ك", "د.ب", "ر.ع", "ر.ق",
        "INR", "USD", "AUD", "CAD", "EUR", "AED", "SAR", "KWD", "KD", "BHD", "BD",
        "OMR", "QAR", "QR", "GBP", "DHS", ","
    ]:
        val = val.replace(sym, "")
    val = val.strip()
    m = re.search(r'[-+]?\d*\.?\d+', val)
    if m:
        try:
            return float(m.group(0))
        except ValueError:
            return 0.0
    return 0.0


def detect_currency_from_text(raw_text: str, default_currency: str = "INR") -> str:
    """
    Detect the currency of the invoice from symbols and keywords in the extracted text.
    Returns ISO currency code: 'USD', 'EUR', 'AED', 'SAR', 'KWD', 'BHD', 'OMR', 'GBP', 'CAD', 'AUD', 'INR', etc.
    """
    if not raw_text:
        return default_currency

    text_upper = raw_text.upper()

    # Specific Arabic / GCC currencies
    if "د.إ" in raw_text or re.search(r'\b(AED|DIRHAM|DIRHAMS|DHS)\b', text_upper):
        return "AED"
    if "﷼" in raw_text or re.search(r'\b(SAR|RIYAL|RIYALS)\b', text_upper):
        return "SAR"
    if "د.ك" in raw_text or re.search(r'\b(KWD|KD|KUWAITI\s+DINAR)\b', text_upper):
        return "KWD"
    if "د.ب" in raw_text or re.search(r'\b(BHD|BD|BAHRAINI\s+DINAR)\b', text_upper):
        return "BHD"
    if "ر.ع" in raw_text or re.search(r'\b(OMR|OMANI\s+RIAL)\b', text_upper):
        return "OMR"
    if "ر.ق" in raw_text or re.search(r'\b(QAR|QATARI\s+RIYAL)\b', text_upper):
        return "QAR"

    # Western / Major international
    if "€" in raw_text or re.search(r'\b(EUR|EURO|EUROS)\b', text_upper):
        return "EUR"
    if "£" in raw_text or re.search(r'\b(GBP|POUND|POUNDS|STERLING)\b', text_upper):
        return "GBP"
    if "$" in raw_text or re.search(r'\b(USD|DOLLARS?|U\.S\.\s*DOLLARS?)\b', text_upper):
        if "CAD" in text_upper or "CANADIAN" in text_upper:
            return "CAD"
        if "AUD" in text_upper or "AUSTRALIAN" in text_upper:
            return "AUD"
        return "USD"

    # Indian Rupee
    if "₹" in raw_text or re.search(r'\b(INR|RS\.?|RUPEES?)\b', text_upper):
        return "INR"

    return default_currency


def parse_date_string(raw_str):
    """Attempt to parse date from various Indian/International formats"""
    if not raw_str:
        return None
    # Normalize broken words like M—ay -> May
    raw_str = raw_str.replace("—", "-").replace("–", "-")
    raw_str = re.sub(r'M\s*-\s*ay', 'May', raw_str, flags=re.IGNORECASE)
    raw_str = raw_str.strip()
    
    # 0. YYYY-MM-DD or YYYY/MM/DD (ISO Format)
    m_iso = re.search(r'\b(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})\b', raw_str)
    if m_iso:
        y, m_num, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        try:
            return date(y, m_num, d).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 1. DD-MM-YYYY, DD/MM/YYYY, DD.MM.YYYY
    m = re.search(r'\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})\b', raw_str)
    if m:
        d, m_num, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        if d > 1900 and m_num <= 12 and y <= 31:
            y, m_num, d = d, m_num, y
        try:
            return date(y, m_num, d).strftime("%Y-%m-%d")
        except ValueError:
            pass

    # 2. Month DD, YYYY format (e.g. January 25, 2016 or May 30, 2026)
    m_month_first = re.search(r'\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?\s*,\s*(\d{2,4})\b', raw_str)
    if m_month_first:
        mon_str = m_month_first.group(1).lower()
        d = int(m_month_first.group(2))
        y = int(m_month_first.group(3))
        if y < 100:
            y += 2000
        mon = MONTH_MAP.get(mon_str)
        if mon:
            try:
                return date(y, mon, d).strftime("%Y-%m-%d")
            except ValueError:
                pass

    # 3. DD Mon YYYY / DD Month YYYY format (e.g. 15 Jan 2024, 30 May 2026)
    m2 = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?[\s\-\,]+([A-Za-z]{3,9})[\s\-\,]+(\d{2,4})\b', raw_str)
    if m2:
        d = int(m2.group(1))
        mon_str = m2.group(2).lower()
        y = int(m2.group(3))
        if y < 100:
            y += 2000
        mon = MONTH_MAP.get(mon_str)
        if mon:
            try:
                return date(y, mon, d).strftime("%Y-%m-%d")
            except ValueError:
                pass
    return None


def extract_raw_text_and_tables(file_stream_or_path, filename=""):
    """
    Extracts text and structured tables from PDF, Image, or text stream.
    Returns:
        full_text: str
        all_tables: list of lists of rows
    """
    full_text = ""
    all_tables = []

    file_bytes = None
    if hasattr(file_stream_or_path, "read"):
        file_bytes = file_stream_or_path.read()
        file_stream_or_path.seek(0)
    elif isinstance(file_bytes, bytes):
        pass
    elif isinstance(file_stream_or_path, bytes):
        file_bytes = file_stream_or_path
    elif isinstance(file_stream_or_path, str) and not os.path.exists(file_stream_or_path):
        return file_stream_or_path, []

    is_pdf = False
    fn_lower = filename.lower()
    if isinstance(file_stream_or_path, str) and file_stream_or_path.lower().endswith(".pdf"):
        is_pdf = True
    elif fn_lower.endswith(".pdf"):
        is_pdf = True
    elif file_bytes and file_bytes.startswith(b"%PDF"):
        is_pdf = True

    if is_pdf:
        # 1. Primary digital PDF extraction using pypdf (always available)
        try:
            import pypdf
            pdf_stream = io.BytesIO(file_bytes) if file_bytes else file_stream_or_path
            reader = pypdf.PdfReader(pdf_stream)
            pypdf_text = ""
            for page in reader.pages:
                txt = page.extract_text() or ""
                pypdf_text += txt + "\n\n"
            if pypdf_text.strip():
                full_text += pypdf_text
        except Exception:
            pass

        # 2. Extract structured tables via pdfplumber if installed
        try:
            import pdfplumber
            pdf_file = io.BytesIO(file_bytes) if file_bytes else file_stream_or_path
            with pdfplumber.open(pdf_file) as pdf:
                plumber_text = ""
                for page in pdf.pages:
                    txt = page.extract_text(layout=True) or page.extract_text() or ""
                    plumber_text += txt + "\n\n"
                    tables = page.extract_tables()
                    if tables:
                        for tbl in tables:
                            cleaned = [[cell.strip() if cell else "" for cell in row] for row in tbl if any(row)]
                            if cleaned:
                                all_tables.append(cleaned)
                if len(plumber_text.strip()) > len(full_text.strip()):
                    full_text = plumber_text
        except Exception:
            pass

        # 3. PyMuPDF (fitz) fallback if installed
        if len(full_text.strip()) < 40:
            try:
                import fitz
                doc = fitz.open(stream=file_bytes, filetype="pdf") if file_bytes else fitz.open(file_stream_or_path)
                fitz_text = ""
                for page in doc:
                    fitz_text += page.get_text() + "\n"
                if len(fitz_text.strip()) > len(full_text.strip()):
                    full_text = fitz_text
            except Exception:
                pass

        # 4. OCR fallback for scanned image PDFs
        if len(full_text.strip()) < 40:
            try:
                import fitz
                import pytesseract
                from PIL import Image
                doc = fitz.open(stream=file_bytes, filetype="pdf") if file_bytes else fitz.open(file_stream_or_path)
                for page in doc:
                    pix = page.get_pixmap(dpi=200)
                    img = Image.open(io.BytesIO(pix.tobytes("png")))
                    ocr_txt = pytesseract.image_to_string(img)
                    full_text += ocr_txt + "\n"
            except Exception:
                pass
    else:
        if fn_lower.endswith(".txt") or (file_bytes and b"INVOICE" in file_bytes.upper() and not file_bytes.startswith(b"\x89PNG") and not file_bytes.startswith(b"\xff\xd8")):
            try:
                full_text = file_bytes.decode("utf-8", errors="ignore")
            except Exception:
                pass
        
        if not full_text:
            try:
                from PIL import Image
                import pytesseract
                img = Image.open(io.BytesIO(file_bytes)) if file_bytes else Image.open(file_stream_or_path)
                full_text = pytesseract.image_to_string(img)
            except Exception:
                pass

    return full_text, all_tables


def extract_with_gemini_vision(file_bytes, filename="", company_info=None, existing_suppliers=None, existing_stock_items=None, api_key=None):
    """
    Extract structured invoice data using Gemini Vision API (Multimodal LLM).
    Handles any invoice layout, format, handwriting, or language in the world.
    """
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types
        import json

        client = genai.Client(api_key=api_key)

        fn_lower = (filename or "").lower()
        if fn_lower.endswith(".pdf"):
            mime_type = "application/pdf"
        elif fn_lower.endswith(".png"):
            mime_type = "image/png"
        elif fn_lower.endswith((".jpg", ".jpeg")):
            mime_type = "image/jpeg"
        elif fn_lower.endswith(".webp"):
            mime_type = "image/webp"
        else:
            mime_type = "application/pdf" if file_bytes.startswith(b"%PDF") else "image/jpeg"

        prompt = """You are an expert invoice parser. Extract the structured purchase invoice data from this document into clean JSON.
Return ONLY a valid JSON object matching this exact schema:
{
  "currency": "USD", // ISO 3-letter currency code (e.g. USD, EUR, AED, SAR, KWD, GBP, INR)
  "supplier": {
    "name": "Supplier or Vendor or Shipper Legal Name",
    "gstin": "15-digit GSTIN if Indian, else empty string",
    "state": "State name if found, else empty string",
    "address": "Street address or city",
    "phone": "Phone or mobile number",
    "email": "Email address"
  },
  "invoice_details": {
    "invoice_number": "Invoice / Bill number",
    "date": "YYYY-MM-DD",
    "due_date": "YYYY-MM-DD",
    "reference_po_no": "PO / Reference number if any",
    "payment_terms": "e.g. Net 30 Days or Immediate"
  },
  "items": [
    {
      "item_name": "Product or Service description",
      "item_code": "Product code or SKU (do NOT put HSN/SAC here)",
      "hsn": "HSN / SAC / HS Code (4 to 8 digits)",
      "quantity": 1.0,
      "unit": "pcs / nos / kg / box / mtr / etc.",
      "rate": 0.0,
      "discount_percent": 0.0,
      "gst_percent": 18,
      "total_amount": 0.0
    }
  ],
  "totals": {
    "subtotal": 0.0,
    "cgst_total": 0.0,
    "sgst_total": 0.0,
    "igst_total": 0.0,
    "tax_amount": 0.0,
    "grand_total": 0.0
  }
}
Important:
- Identify the SHIPPER / SELLER / VENDOR (not the consignee/buyer).
- Distinguish HSN / HS Code from Product Code.
- Do NOT include 'Sub Total', 'Total', 'Tax', 'Payments', 'Amount Due', or 'Box No' as line items.
- Ensure all numeric values are numbers (float/int), not strings with currency symbols.
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(
                    data=file_bytes,
                    mime_type=mime_type,
                ),
                prompt
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1
            )
        )

        resp_text = response.text.strip()
        if resp_text.startswith("```json"):
            resp_text = resp_text[7:]
        if resp_text.startswith("```"):
            resp_text = resp_text[3:]
        if resp_text.endswith("```"):
            resp_text = resp_text[:-3]
        resp_text = resp_text.strip()

        data = json.loads(resp_text)
        if not data or not isinstance(data, dict):
            return None

        sup_data = data.get("supplier", {})
        inv_data = data.get("invoice_details", {})
        items_data = data.get("items", [])
        totals_data = data.get("totals", {})

        supplier_name = (sup_data.get("name") or "").strip()
        supplier_gstin = (sup_data.get("gstin") or "").strip().upper()
        supplier_state = (sup_data.get("state") or "").strip()
        supplier_address = (sup_data.get("address") or "").strip()
        supplier_phone = (sup_data.get("phone") or "").strip()
        supplier_email = (sup_data.get("email") or "").strip().lower()

        if supplier_gstin and len(supplier_gstin) >= 2 and not supplier_state:
            supplier_state = GST_STATE_CODES.get(supplier_gstin[:2], "")

        supplier_id = None
        if existing_suppliers:
            if supplier_gstin:
                for s in existing_suppliers:
                    s_gst = (getattr(s, "gst_number", None) or getattr(s, "gstin", None) or "").strip().upper()
                    if s_gst and s_gst == supplier_gstin:
                        supplier_id = s.id
                        supplier_name = s.name
                        break
            if not supplier_id and supplier_name:
                s_name_lower = supplier_name.lower().strip()
                for s in existing_suppliers:
                    cur_name = s.name.lower().strip()
                    if cur_name == s_name_lower or (len(cur_name) > 4 and cur_name in s_name_lower):
                        supplier_id = s.id
                        supplier_name = s.name
                        break

        company_state = (company_info.get("state") or "Maharashtra").strip() if company_info else "Maharashtra"
        is_interstate = bool(company_state and supplier_state and company_state.lower().strip() != supplier_state.lower().strip())

        parsed_items = []
        for itm in items_data:
            i_name = (itm.get("item_name") or "").strip()
            if not i_name or any(ign in i_name.lower() for ign in ["sub total", "grand total", "total due", "payments", "box no"]):
                continue
            i_code = (itm.get("item_code") or "").strip()
            i_hsn = (itm.get("hsn") or "").strip()
            i_qty = float(itm.get("quantity") or 1.0)
            i_unit = (itm.get("unit") or "pcs").strip().lower()
            if i_unit not in ["pcs", "nos", "box", "kg", "mtr", "set", "ton", "ltr", "hrs"]:
                i_unit = "pcs"
            i_rate = float(itm.get("rate") or 0.0)
            i_disc = float(itm.get("discount_percent") or 0.0)
            i_gst = int(itm.get("gst_percent") or 18)
            i_tot = float(itm.get("total_amount") or round(i_qty * i_rate, 2))

            stock_id = None
            matched_st = None
            if existing_stock_items:
                for st in existing_stock_items:
                    st_code = (st.code or "").strip().lower()
                    st_name = (st.name or "").strip().lower()
                    if i_code and st_code == i_code.lower():
                        stock_id = st.id
                        matched_st = st
                        break
                    if i_name.lower() == st_name or (len(st_name) > 4 and st_name in i_name.lower()):
                        stock_id = st.id
                        matched_st = st
                        break

            final_code = matched_st.code if (matched_st and matched_st.code) else i_code

            parsed_items.append({
                "stock_item_id": stock_id,
                "item_code": final_code,
                "matched_existing": bool(matched_st),
                "item_name": i_name,
                "hsn": i_hsn or (matched_st.hsn if matched_st else ""),
                "quantity": i_qty,
                "unit": i_unit,
                "rate": i_rate,
                "discount_percent": i_disc,
                "gst_percent": i_gst,
                "total_amount": i_tot
            })

        return {
            "success": True,
            "engine": "gemini_ai_vision",
            "currency": (data.get("currency") or "INR").upper().strip(),
            "supplier": {
                "id": supplier_id,
                "name": supplier_name,
                "gstin": supplier_gstin,
                "state": supplier_state or company_state,
                "address": supplier_address,
                "phone": supplier_phone,
                "email": supplier_email
            },
            "invoice_details": {
                "invoice_number": (inv_data.get("invoice_number") or "").strip(),
                "date": inv_data.get("date"),
                "due_date": inv_data.get("due_date") or inv_data.get("date"),
                "reference_po_no": (inv_data.get("reference_po_no") or "").strip(),
                "payment_terms": (inv_data.get("payment_terms") or "Net 30 Days").strip()
            },
            "items": parsed_items,
            "totals": {
                "subtotal": float(totals_data.get("subtotal") or 0.0),
                "cgst_total": float(totals_data.get("cgst_total") or 0.0),
                "sgst_total": float(totals_data.get("sgst_total") or 0.0),
                "igst_total": float(totals_data.get("igst_total") or 0.0),
                "tax_amount": float(totals_data.get("tax_amount") or 0.0),
                "grand_total": float(totals_data.get("grand_total") or 0.0)
            },
            "is_interstate": is_interstate,
            "raw_text_snippet": "Processed with Gemini AI Vision"
        }
    except Exception as e:
        print(f"[Gemini Vision OCR Error]: {e}, falling back to local OCR parser...")
        return None


def parse_purchase_invoice(file_stream_or_path, filename="", company_info=None, existing_suppliers=None, existing_stock_items=None):
    """
    Main parser that analyzes text & tables to extract structured purchase invoice data.
    Uses Gemini AI Vision when API key is configured, with seamless local OCR fallback.
    """
    # 1. Check for Gemini AI Vision
    api_key = (company_info.get("gemini_api_key") if company_info else None) or os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            fb = None
            if isinstance(file_stream_or_path, str):
                with open(file_stream_or_path, "rb") as f:
                    fb = f.read()
            elif hasattr(file_stream_or_path, "read"):
                file_stream_or_path.seek(0)
                fb = file_stream_or_path.read()
                file_stream_or_path.seek(0)
            elif isinstance(file_stream_or_path, (bytes, bytearray)):
                fb = bytes(file_stream_or_path)

            if fb:
                ai_res = extract_with_gemini_vision(
                    fb,
                    filename=filename,
                    company_info=company_info,
                    existing_suppliers=existing_suppliers,
                    existing_stock_items=existing_stock_items,
                    api_key=api_key
                )
                if ai_res and ai_res.get("success"):
                    return ai_res
        except Exception as e:
            print(f"Gemini Vision dispatch failed: {e}, falling back to local OCR...")

    # 2. Local Fallback OCR / PDF Engine
    company_gstin = (company_info.get("gst_number") or "").strip().upper() if company_info else ""
    company_name = (company_info.get("company_name") or "").strip().lower() if company_info else ""
    company_state = (company_info.get("state") or "Maharashtra").strip() if company_info else "Maharashtra"

    raw_text, tables = extract_raw_text_and_tables(file_stream_or_path, filename)
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

    default_base_curr = (company_info.get("currency") if company_info else "INR") or "INR"
    detected_currency = detect_currency_from_text(raw_text, default_currency=default_base_curr)
    has_explicit_gst = bool(re.search(r'\b(GST|CGST|SGST|IGST|GSTIN)\b', raw_text, re.IGNORECASE))
    default_gst = 18 if (detected_currency == "INR" or has_explicit_gst) else 0

    # Normalize broken typography
    normalized_text = raw_text.replace("—", "-").replace("–", "-")
    # Fix broken words e.g. "Sub To tal" -> "Sub Total", "To tal" -> "Total"
    normalized_text = re.sub(r'\bSub\s+To\s*tal\b', 'Sub Total', normalized_text, flags=re.IGNORECASE)
    normalized_text = re.sub(r'\bTo\s*tal\b', 'Total', normalized_text, flags=re.IGNORECASE)

    # 1. Section Segmentation: Separate Seller vs Buyer
    seller_lines = []
    buyer_lines = []
    current_sec = "seller"
    buyer_trigger_idx = -1

    for i, line in enumerate(lines):
        ll = " ".join(line.lower().split())
        if any(s in ll for s in ["shipper :", "shipper", "exporter:", "consignor:", "seller:", "supplier:", "sold by:", "from:"]):
            current_sec = "seller"
        elif any(b in ll for b in ["consignee", "receiver", "consignee / receiver", "billed to", "bill to", "buyer:", "buyer details", "ship to", "invoice to", "details of receiver", "to:"]):
            current_sec = "buyer"
            buyer_trigger_idx = i
            continue
        elif current_sec == "buyer" and any(desc_k in ll for desc_k in ["description", "particulars", "item description", "service", "sr. no", "hs code", "amount (inr)"]):
            current_sec = "table"

        if current_sec == "seller":
            seller_lines.append(line)
        elif current_sec == "buyer":
            buyer_lines.append(line)

    if not seller_lines:
        seller_lines = lines[:buyer_trigger_idx] if buyer_trigger_idx > 0 else lines[:10]

    seller_text = "\n".join(seller_lines)
    buyer_text = "\n".join(buyer_lines)

    # 2. Extract GSTINs
    all_gstins = GSTIN_REGEX.findall(normalized_text)
    seen = set()
    gstins = [g.upper() for g in all_gstins if not (g.upper() in seen or seen.add(g.upper()))]
    
    supplier_gstin = ""
    buyer_gstin = ""

    # Check seller section first for GSTIN
    seller_gstins = GSTIN_REGEX.findall(seller_text)
    if seller_gstins:
        for g in seller_gstins:
            if company_gstin and g.upper() == company_gstin:
                continue
            supplier_gstin = g.upper()
            break

    if not supplier_gstin and gstins:
        for g in gstins:
            if company_gstin and g == company_gstin:
                buyer_gstin = g
                continue
            supplier_gstin = g
            break

    supplier_state = ""
    if supplier_gstin and len(supplier_gstin) >= 2:
        state_code = supplier_gstin[:2]
        supplier_state = GST_STATE_CODES.get(state_code, "")

    # 3. Extract Supplier Name, Address, Contact
    supplier_name = ""
    supplier_address = ""
    supplier_phone = ""
    supplier_email = ""
    supplier_id = None

    # Emails: Look in seller section first
    seller_emails = EMAIL_REGEX.findall(seller_text)
    if seller_emails:
        supplier_email = seller_emails[0]
    else:
        all_emails = EMAIL_REGEX.findall(normalized_text)
        comp_email = (company_info.get("email") or "").strip().lower() if company_info else ""
        for em in all_emails:
            if comp_email and em.lower() == comp_email:
                continue
            if buyer_text and em in buyer_text:
                continue
            supplier_email = em
            break

    # Phones: Look in seller section first
    m_seller_phone = re.search(r'(?:Phone|Mobile|Contact|Tel|Cell)(?:\s*(?:No\.?|Number|#))?\s*[:\-–—]?\s*([+0-9\s\-]{8,18})', seller_text, re.IGNORECASE)
    if m_seller_phone:
        supplier_phone = m_seller_phone.group(1).strip()
    else:
        seller_phones = PHONE_REGEX.findall(seller_text)
        if seller_phones:
            supplier_phone = seller_phones[0]
        else:
            all_phones = PHONE_REGEX.findall(normalized_text)
            for ph in all_phones:
                if buyer_text and ph in buyer_text:
                    continue
                supplier_phone = ph
                break

    # Supplier Name Detection Strategy:
    # A. Check "Shipper:", "From:", "Seller:", "Supplier:", "Vendor:", "Exporter:", "Consignor:", "Sold by:" label
    for i, line in enumerate(lines):
        m = re.match(r'^(?:shipper|seller|supplier|vendor|exporter|consignor|sold\s*by|from)\s*[:\-–—]?\s*(.*)$', line, re.IGNORECASE)
        if m:
            cand = m.group(1).strip()
            cand_left = re.split(r'\s{2,}|\t', cand)[0].strip() if cand else ""
            if cand_left and len(cand_left) > 2 and not any(cand_left.lower() == nw for nw in NOISE_HEADER_WORDS):
                supplier_name = cand_left
                break
            elif i + 1 < len(lines):
                next_cand = re.split(r'\s{2,}|\t', lines[i + 1])[0].strip()
                if len(next_cand) > 2 and not any(next_cand.lower() == nw for nw in NOISE_HEADER_WORDS):
                    supplier_name = next_cand
                    break

    # B. If supplier has a GSTIN in seller_lines, check backwards for company name (skipping address/HSN lines)
    if not supplier_name and supplier_gstin:
        for i, line in enumerate(lines):
            if supplier_gstin in line.upper():
                for j in range(i - 1, max(-1, i - 6), -1):
                    cand = lines[j].strip()
                    cand_clean = " ".join(cand.lower().split())
                    if any(cand_clean == nw for nw in ["invoice", "tax invoice", "paid", "original", "—", "-"]):
                        continue
                    if any(ign in cand_clean for ign in ["hsn", "sac", "floor", "plot", "sector", "phase", "road", "street", "building"]):
                        continue
                    if re.search(r'\b\d{6}\b', cand):
                        continue
                    cand_left = re.split(r'\s{2,}|\t', cand)[0].strip()
                    if len(cand_left) >= 3:
                        supplier_name = cand_left
                        break
                if supplier_name:
                    break

    # C. Check lines in seller_lines with company suffix keywords
    if not supplier_name:
        for line in seller_lines:
            cand_left = re.split(r'\s{2,}|\t', line)[0].strip()
            ll = " ".join(cand_left.lower().split())
            if any(nw == ll for nw in NOISE_HEADER_WORDS):
                continue
            if company_name and company_name in ll:
                continue
            if any(suf in ll for suf in COMPANY_SUFFIXES):
                cleaned = re.sub(r'^(Sold By|Supplier|Seller|Vendor|From|Shipper|Exporter|M/s\.?|Messrs)\s*[:\-]?\s*', '', cand_left, flags=re.IGNORECASE).strip()
                if len(cleaned) > 3:
                    supplier_name = cleaned
                    break

    # D. Fallback to first non-noise header line in seller_lines
    if not supplier_name:
        for line in seller_lines:
            cand_left = re.split(r'\s{2,}|\t', line)[0].strip()
            ll = " ".join(cand_left.lower().split())
            if len(ll) < 4 or any(nw in ll for nw in NOISE_HEADER_WORDS):
                continue
            if any(ign in ll for ign in ["street", "road", "suite", "avenue", "city", "building", "floor"]):
                continue
            if company_name and company_name in ll:
                continue
            cleaned = re.sub(r'^(Sold By|Supplier|Seller|Vendor|From|Shipper|Exporter|M/s\.?|Messrs)\s*[:\-]?\s*', '', cand_left, flags=re.IGNORECASE).strip()
            if len(cleaned) > 3 and not any(cleaned.lower() == nw for nw in NOISE_HEADER_WORDS):
                supplier_name = cleaned
                break

    # Match with existing database suppliers
    if existing_suppliers:
        if supplier_gstin:
            for s in existing_suppliers:
                s_gst = (getattr(s, "gst_number", None) or getattr(s, "gstin", None) or "").strip().upper()
                if s_gst and s_gst == supplier_gstin:
                    supplier_id = s.id
                    supplier_name = s.name
                    if not supplier_state and getattr(s, "state", None):
                        supplier_state = s.state
                    if not supplier_address and getattr(s, "address", None):
                        supplier_address = s.address
                    if not supplier_phone and getattr(s, "phone", None):
                        supplier_phone = s.phone
                    if not supplier_email and getattr(s, "email", None):
                        supplier_email = s.email
                    break
        
        if not supplier_id and supplier_name:
            s_name_lower = supplier_name.lower().strip()
            for s in existing_suppliers:
                cur_name = s.name.lower().strip()
                if cur_name == s_name_lower or (len(cur_name) > 4 and cur_name in s_name_lower) or (len(s_name_lower) > 4 and s_name_lower in cur_name):
                    supplier_id = s.id
                    supplier_name = s.name
                    if not supplier_state and getattr(s, "state", None):
                        supplier_state = s.state
                    if not supplier_gstin and getattr(s, "gst_number", None):
                        supplier_gstin = s.gst_number
                    if not supplier_address and getattr(s, "address", None):
                        supplier_address = s.address
                    if not supplier_phone and getattr(s, "phone", None):
                        supplier_phone = s.phone
                    if not supplier_email and getattr(s, "email", None):
                        supplier_email = s.email
                    break

    if not supplier_state:
        supplier_state = company_state

    # 4. Extract Invoice Number, Date, PO Number
    invoice_number = ""
    invoice_date = None
    due_date = None
    reference_po_no = ""
    payment_terms = "Net 30 Days"

    inv_patterns = [
        r'Invoice\s*#\s*([A-Za-z0-9\/\-_–—]{2,30})',
        r'Invoice\s*Number\s*[:\-–—]?\s*([A-Za-z0-9\/\-_–—]{2,30})',
        r'(?:Tax Invoice|Invoice|Inv|Bill of Supply|Cash Memo|Bill)\s*(?:No\.?|Number|#|\/)\s*[:\-–—]?\s*([A-Za-z0-9\/\-_–—]{2,30})',
        r'Invoice\s*ID\s*[:\-–—]?\s*([A-Za-z0-9\/\-_–—]{2,30})',
        r'\bInv[#\s\:\.\-–—]+([A-Za-z0-9\/\-_–—]{2,30})\b'
    ]
    for pat in inv_patterns:
        m = re.search(pat, normalized_text, re.IGNORECASE)
        if m:
            cand = m.group(1).strip().strip(".,:-–—")
            cand_clean = cand.replace("—", "-").replace("–", "-")
            if not any(cand_clean.lower() == noise for noise in ["date", "details", "format", "gstin", "original", "m/s", "amount", "invoice"]):
                invoice_number = cand_clean
                break

    date_patterns = [
        r'(?:Invoice|Bill|Doc|Dated|Dated on)\s*Date\s*[:\-–—]?\s*([0-9A-Za-z\/\-\.\,\s]{4,25})',
        r'Date\s*[:\-–—]?\s*([0-9A-Za-z\/\-\.\,\s]{4,25})',
        r'\bDated\s*[:\-–—]?\s*([0-9A-Za-z\/\-\.\,\s]{4,25})'
    ]
    for pat in date_patterns:
        m = re.search(pat, normalized_text, re.IGNORECASE)
        if m:
            parsed = parse_date_string(m.group(1))
            if parsed:
                invoice_date = parsed
                break
    
    if not invoice_date:
        invoice_date = parse_date_string(normalized_text)

    if not invoice_date:
        invoice_date = date.today().strftime("%Y-%m-%d")

    due_m = re.search(r'(?:Due|Payment)\s*Date\s*[:\-–—]?\s*([0-9A-Za-z\/\-\.\,\s]{4,25})', normalized_text, re.IGNORECASE)
    if due_m:
        due_date = parse_date_string(due_m.group(1))
    if not due_date:
        due_date = invoice_date

    po_m = re.search(r'(?:P\.?O\.?|Purchase Order|Order)\s*(?:No\.?|Number|#|Ref\.?|Reference)?\s*[:\-–—]\s*([A-Za-z0-9\/\-_]{3,25})', normalized_text, re.IGNORECASE)
    if po_m:
        cand_po = po_m.group(1).strip()
        if not any(cand_po.lower() == noise for noise in ["date", "details"]):
            reference_po_no = cand_po

    # Global HSN in header if any (e.g. Aisensy: HSN / SAC : 998313)
    doc_hsn = ""
    hsn_m = HSN_REGEX.search(normalized_text)
    if hsn_m:
        doc_hsn = hsn_m.group(1)

    # 5. Extract Line Items
    items = []

    # Try table extraction first
    if tables:
        for tbl in tables:
            if not tbl or len(tbl) < 2:
                continue
            
            header_idx = -1
            col_map = {}
            for r_idx, row in enumerate(tbl[:6]):
                row_cells = [str(c or "").strip() for c in row if c]
                if not row_cells:
                    continue
                row_str = " ".join([c.lower() for c in row_cells])
                has_desc = any(k in row_str for k in ["description", "particular", "item", "product", "goods", "service", "material"])
                has_num_col = any(k in row_str for k in ["rate", "price", "amount", "total", "qty", "quantity", "hrs/qty", "sub total"])
                
                if (has_desc and has_num_col) or (has_desc and len(row_cells) >= 2):
                    temp_col_map = {}
                    for c_idx, cell in enumerate(row):
                        cl = str(cell or "").lower().replace("\n", " ").strip()
                        if any(k in cl for k in ["hsn", "hs code", "hs-code", "hscode", "sac", "tariff code", "tariff no", "itc"]):
                            temp_col_map["hsn"] = c_idx
                        elif any(k in cl for k in ["item code", "product code", "part no", "sku", "art no", "article no", "model no", "code"]):
                            if not any(h in cl for h in ["hsn", "hs", "sac", "tariff"]):
                                temp_col_map["code"] = c_idx
                        elif any(k in cl for k in ["description", "item name", "particular", "product", "material", "goods", "service", "description of goods"]):
                            temp_col_map["name"] = c_idx
                        elif any(k in cl for k in ["qty", "quantity", "qnty", "nos", "hrs/qty", "hrs", "total piece", "pieces"]):
                            temp_col_map["qty"] = c_idx
                        elif any(k in cl for k in ["unit type", "unit", "uom", "pkg"]):
                            temp_col_map["unit"] = c_idx
                        elif any(k in cl for k in ["unit rate", "rate/price", "unit price", "rate", "price"]):
                            temp_col_map["rate"] = c_idx
                        elif any(k in cl for k in ["disc", "discount", "adjust"]):
                            temp_col_map["disc"] = c_idx
                        elif any(k in cl for k in ["gst", "tax %", "tax rate", "cgst", "sgst", "igst"]):
                            temp_col_map["gst"] = c_idx
                        elif any(k in cl for k in ["total", "amount", "taxable", "value", "net amount", "sub total"]):
                            if "amount" not in temp_col_map:
                                temp_col_map["amount"] = c_idx
                    
                    if "name" in temp_col_map or ("amount" in temp_col_map and len(temp_col_map) >= 2):
                        header_idx = r_idx
                        col_map = temp_col_map
                        break
            
            if header_idx != -1:
                name_idx = col_map.get("name", 0)
                for row in tbl[header_idx + 1:]:
                    if not row or len(row) <= name_idx:
                        continue
                    cell_val = str(row[name_idx] or "").strip()
                    if not cell_val:
                        continue
                    
                    sub_lines = [sl.strip() for sl in cell_val.splitlines() if sl.strip()]
                    for line_idx, sl in enumerate(sub_lines):
                        sl_norm = re.sub(r'[^a-z0-9]', '', sl.lower())
                        if any(tot_k in sl_norm for tot_k in ["subtotal", "taxtotal", "grandtotal", "total", "igst", "cgst", "sgst", "payment", "amountdue", "eoe", "roundoff", "bank", "acc#", "bsb#", "inr", "boxno", "box1", "weight"]):
                            break
                        
                        # In multi-column rows where lines inside one cell are just descriptions, take only line 0
                        if len(row) > 1 and line_idx > 0:
                            break
                        
                        # Strip leading serial number (e.g. "1 DRESS" -> "DRESS")
                        m_sr = re.match(r'^\d{1,3}\s+([A-Za-z].*)$', sl)
                        if m_sr:
                            sl = m_sr.group(1).strip()

                        # Check if row has multiple non-empty columns
                        has_multi_cols = len(row) > 1 and any(c for c in row[1:] if c and str(c).strip())
                        if has_multi_cols:
                            name_val = sl
                            code_val = str(row[col_map["code"]]).strip() if "code" in col_map and len(row) > col_map["code"] and row[col_map["code"]] else ""
                            hsn_val = str(row[col_map["hsn"]]).strip() if "hsn" in col_map and len(row) > col_map["hsn"] and row[col_map["hsn"]] else doc_hsn
                            qty_raw = row[col_map["qty"]] if "qty" in col_map and len(row) > col_map["qty"] and row[col_map["qty"]] else "1"
                            qty = clean_num(qty_raw) or 1.0
                            unit_val = str(row[col_map["unit"]]).strip().lower() if "unit" in col_map and len(row) > col_map["unit"] and row[col_map["unit"]] else "pcs"
                            if unit_val not in ["pcs", "nos", "box", "kg", "mtr", "set", "ton", "ltr", "hrs"]:
                                unit_val = "pcs"
                            rate_raw = row[col_map["rate"]] if "rate" in col_map and len(row) > col_map["rate"] and row[col_map["rate"]] else "0"
                            rate = clean_num(rate_raw)
                            disc_raw = row[col_map["disc"]] if "disc" in col_map and len(row) > col_map["disc"] and row[col_map["disc"]] else "0"
                            disc_pct = clean_num(disc_raw)
                            gst_raw = row[col_map["gst"]] if "gst" in col_map and len(row) > col_map["gst"] and row[col_map["gst"]] else "18"
                            gst_pct = clean_num(gst_raw)
                            if gst_pct not in [0, 5, 12, 18, 28]:
                                gst_pct = 18.0
                            amt_raw = row[col_map["amount"]] if "amount" in col_map and len(row) > col_map["amount"] and row[col_map["amount"]] else None
                            tot_amt = clean_num(amt_raw) if amt_raw is not None else 0.0
                        else:
                            # Single cell with text + price (e.g. "Basic-Unlimited ₹14,400.00")
                            parts = sl.split()
                            nums = [clean_num(p) for p in parts if clean_num(p) > 0]
                            words = [p for p in parts if clean_num(p) == 0 and not any(sym in p for sym in ["₹", "$", "Rs", "%"])]
                            name_val = " ".join(words) if words else sl
                            tot_amt = nums[-1] if nums else 0.0
                            rate = tot_amt
                            qty = 1.0
                            unit_val = "pcs"
                            disc_pct = 0.0
                            gst_pct = 18.0
                            code_val = ""
                            hsn_val = doc_hsn

                        if not name_val or len(name_val) < 2:
                            continue
                        if any(nw == name_val.lower() for nw in NOISE_HEADER_WORDS):
                            continue

                        if rate == 0.0 and tot_amt > 0 and qty > 0:
                            rate = round(tot_amt / qty, 2)
                        elif tot_amt == 0.0 and rate > 0:
                            taxable = (qty * rate) * (1.0 - disc_pct / 100.0)
                            tot_amt = round(taxable * (1.0 + gst_pct / 100.0), 2)

                        stock_id = None
                        matched_st = None
                        if existing_stock_items:
                            for st in existing_stock_items:
                                st_code = (st.code or "").strip().lower()
                                st_name = (st.name or "").strip().lower()
                                if code_val and st_code == code_val.lower():
                                    stock_id = st.id
                                    matched_st = st
                                    break
                                if name_val.lower() == st_name or (len(st_name) > 4 and st_name in name_val.lower()):
                                    stock_id = st.id
                                    matched_st = st
                                    break

                        final_code = matched_st.code if (matched_st and matched_st.code) else code_val
                        items.append({
                            "stock_item_id": stock_id,
                            "item_code": final_code,
                            "matched_existing": bool(matched_st),
                            "item_name": name_val,
                            "hsn": hsn_val or (matched_st.hsn if matched_st else ""),
                            "quantity": qty,
                            "unit": unit_val,
                            "rate": rate,
                            "discount_percent": disc_pct,
                            "gst_percent": int(gst_pct),
                            "total_amount": tot_amt
                        })

    # Fallback to smart line scanning
    if not items:
        in_table_section = False
        raw_table_lines = []
        for line in lines:
            line_str = line.strip()
            if not line_str or len(line_str) < 3 or line_str.startswith("=") or line_str.startswith("-"):
                continue

            line_lower = " ".join(line_str.lower().split())
            if not in_table_section and any(hdr in line_lower for hdr in ["description", "particulars", "item description", "service", "item / material", "description of goods", "hs code", "sr. no"]):
                in_table_section = True
                continue

            if in_table_section and any(tot_w in line_lower for tot_w in ["subtotal", "sub total", "tax total", "grand total", "total due", "payments", "amount due", "terms & conditions", "bank details", "country of origin", "we declaration"]):
                in_table_section = False
                continue

            if not in_table_section:
                continue

            if any(ign in line_lower for ign in ["box no", "box-", "weight :", "total piece", "destination :"]):
                continue

            raw_table_lines.append(line_str)

        # Merge split lines where description/name is on one line and prices/amounts are on the next line
        table_lines = []
        l_idx = 0
        while l_idx < len(raw_table_lines):
            curr_l = raw_table_lines[l_idx]
            if l_idx + 1 < len(raw_table_lines):
                nxt_l = raw_table_lines[l_idx + 1]
                has_curr_nxt = any(c in nxt_l for c in ["₹", "$", "Rs.", "Rs", "USD", "INR", "%"])
                has_curr_cur = any(c in curr_l for c in ["₹", "$", "Rs.", "Rs", "USD", "INR"])
                if has_curr_nxt and not has_curr_cur:
                    curr_l = f"{curr_l} {nxt_l}"
                    l_idx += 1
            table_lines.append(curr_l)
            l_idx += 1

        for line_str in table_lines:
            # Check if line has item name and amounts / HSN
            tokens = line_str.split()
            qty_candidate = None
            if tokens and re.match(r'^\d+(?:\.\d+)?$', tokens[0]) and len(tokens) > 2:
                try:
                    val = float(tokens[0])
                    if val > 0 and val < 100000:
                        qty_candidate = val
                        tokens = tokens[1:]
                except ValueError:
                    pass

            item_name_parts = []
            hsn_found = ""
            unit_found = "pcs"
            qty_found = qty_candidate if qty_candidate is not None else 1.0
            rate_found = 0.0
            amt_found = 0.0
            num_values = []

            for tok in tokens:
                tok_clean = tok.replace("₹", "").replace("Rs.", "").replace("$", "").replace(",", "").replace("%", "").strip()
                if re.match(r'^\d{4,8}$', tok_clean) and not hsn_found:
                    hsn_found = tok_clean
                elif tok_clean.lower() in ["pcs", "nos", "box", "kg", "mtr", "set", "ton", "ltr", "pairs"]:
                    unit_found = tok_clean.lower()
                elif re.match(r'^\d+(?:\.\d+)?$', tok_clean):
                    num_values.append(float(tok_clean))
                elif tok_clean not in ["—", "-", "|", ":", "—", "/"]:
                    item_name_parts.append(tok_clean)

            if item_name_parts:
                item_name = " ".join(item_name_parts)
                if "..." in item_name:
                    item_name = item_name.split("...")[0].strip()
                item_name = re.split(r'(?<=[a-zA-Z0-9])\s+(?:This is|Description|Note)\b', item_name, flags=re.IGNORECASE)[0].strip()

                if any(tot_w in item_name.lower() for tot_w in ["sub total", "subtotal", "total", "igst", "cgst", "sgst", "tax", "payments", "amount due"]):
                    continue

                if len(num_values) == 1:
                    rate_found = num_values[0]
                    amt_found = round(qty_found * rate_found, 2)
                elif len(num_values) == 2:
                    if qty_candidate is None:
                        qty_found = num_values[0]
                        rate_found = num_values[1]
                        amt_found = round(qty_found * rate_found, 2)
                    else:
                        rate_found = num_values[0]
                        amt_found = num_values[1]
                elif len(num_values) >= 3:
                    if qty_candidate is None:
                        qty_found = num_values[0]
                        rate_found = num_values[1]
                        amt_found = num_values[-1]
                    else:
                        rate_found = num_values[0]
                        amt_found = num_values[-1]

                stock_id = None
                matched_st = None
                if existing_stock_items:
                    for st in existing_stock_items:
                        st_name = (st.name or "").strip().lower()
                        if item_name.lower() == st_name or (len(st_name) > 4 and st_name in item_name.lower()):
                            stock_id = st.id
                            matched_st = st
                            break

                final_code = matched_st.code if (matched_st and matched_st.code) else ""
                items.append({
                    "stock_item_id": stock_id,
                    "item_code": final_code,
                    "matched_existing": bool(matched_st),
                    "item_name": item_name,
                    "hsn": hsn_found or doc_hsn or (matched_st.hsn if matched_st else ""),
                    "quantity": qty_found,
                    "unit": unit_found,
                    "rate": rate_found,
                    "discount_percent": 0.0,
                    "gst_percent": default_gst,
                    "total_amount": amt_found
                })

    # 6. Extract Grand Total and Subtotal from text if table didn't capture them
    grand_total_patterns = [
        r'(?:Grand Total|Total Amount|Invoice Amount|Total Due|Total|Net Payable|Amount Due)\s*[:\-–—]?\s*(?:₹|Rs\.?|\$|INR)?\s*([0-9,]+\.?\d*)',
        r'Total\s*[:\-–—]?\s*(?:₹|Rs\.?|\$|INR)?\s*([0-9,]+\.?\d*)'
    ]
    extracted_grand_total = 0.0
    for pat in grand_total_patterns:
        m = re.search(pat, normalized_text, re.IGNORECASE)
        if m:
            val = clean_num(m.group(1))
            if val > 0:
                extracted_grand_total = val
                break

    # 7. Calculate Financial Totals
    is_interstate = bool(company_state and supplier_state and company_state.lower().strip() != supplier_state.lower().strip())
    
    subtotal = 0.0
    cgst_total = 0.0
    sgst_total = 0.0
    igst_total = 0.0

    if items:
        for itm in items:
            qty = itm.get("quantity", 1.0)
            rate = itm.get("rate", 0.0)
            disc = itm.get("discount_percent", 0.0)
            gst = itm.get("gst_percent", default_gst)

            taxable = (qty * rate) * (1.0 - (disc / 100.0))
            tax_amt = taxable * (gst / 100.0)
            subtotal += taxable

            if is_interstate:
                igst_total += tax_amt
            else:
                cgst_total += tax_amt / 2.0
                sgst_total += tax_amt / 2.0

        tax_total = cgst_total + sgst_total + igst_total
        grand_total = subtotal + tax_total

        if extracted_grand_total > 0 and abs(grand_total - extracted_grand_total) > 1.0:
            grand_total = extracted_grand_total
    else:
        # Fallback single item
        tot_val = extracted_grand_total if extracted_grand_total > 0 else 0.0
        items.append({
            "stock_item_id": None,
            "item_code": "",
            "matched_existing": False,
            "item_name": "Purchased Materials / Services",
            "hsn": doc_hsn,
            "quantity": 1.0,
            "unit": "pcs",
            "rate": tot_val,
            "discount_percent": 0.0,
            "gst_percent": default_gst,
            "total_amount": tot_val
        })
        subtotal = tot_val
        grand_total = tot_val
        tax_total = 0.0

    return {
        "success": True,
        "currency": detected_currency,
        "supplier": {
            "id": supplier_id,
            "name": supplier_name,
            "gstin": supplier_gstin,
            "state": supplier_state,
            "address": supplier_address,
            "phone": supplier_phone,
            "email": supplier_email
        },
        "invoice_details": {
            "invoice_number": invoice_number,
            "date": invoice_date,
            "due_date": due_date,
            "reference_po_no": reference_po_no,
            "payment_terms": payment_terms
        },
        "items": items,
        "totals": {
            "subtotal": round(subtotal, 2),
            "cgst_total": round(cgst_total, 2),
            "sgst_total": round(sgst_total, 2),
            "igst_total": round(igst_total, 2),
            "tax_amount": round(tax_total, 2),
            "grand_total": round(grand_total, 2)
        },
        "is_interstate": is_interstate,
        "raw_text_snippet": raw_text[:500] if raw_text else ""
    }

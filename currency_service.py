"""
currency_service.py
───────────────────
Multi-currency engine for Qiyadah ERP:
- Comprehensive currency registry (symbols, decimal places, country names, flags).
- Real-time exchange rate fetcher with in-memory & disk caching (1-hour TTL).
- Graceful offline fallback exchange rate matrix.
- Formatting and conversion utilities.
"""

import json
import os
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

# Supported currencies registry
CURRENCIES: Dict[str, Dict[str, Any]] = {
    "INR": {
        "code": "INR",
        "name": "Indian Rupee",
        "symbol": "₹",
        "decimals": 2,
        "symbol_position": "before",
        "country": "India",
        "flag": "🇮🇳",
    },
    "USD": {
        "code": "USD",
        "name": "US Dollar",
        "symbol": "$",
        "decimals": 2,
        "symbol_position": "before",
        "country": "United States",
        "flag": "🇺🇸",
    },
    "EUR": {
        "code": "EUR",
        "name": "Euro",
        "symbol": "€",
        "decimals": 2,
        "symbol_position": "before",
        "country": "European Union",
        "flag": "🇪🇺",
    },
    "AED": {
        "code": "AED",
        "name": "UAE Dirham",
        "symbol": "AED",
        "alt_symbol": "د.إ",
        "decimals": 2,
        "symbol_position": "before",
        "country": "United Arab Emirates",
        "flag": "🇦🇪",
    },
    "SAR": {
        "code": "SAR",
        "name": "Saudi Riyal",
        "symbol": "SAR",
        "alt_symbol": "﷼",
        "decimals": 2,
        "symbol_position": "before",
        "country": "Saudi Arabia",
        "flag": "🇸🇦",
    },
    "KWD": {
        "code": "KWD",
        "name": "Kuwaiti Dinar",
        "symbol": "KD",
        "alt_symbol": "د.ك",
        "decimals": 3,
        "symbol_position": "before",
        "country": "Kuwait",
        "flag": "🇰🇼",
    },
    "BHD": {
        "code": "BHD",
        "name": "Bahraini Dinar",
        "symbol": "BD",
        "alt_symbol": "د.ب",
        "decimals": 3,
        "symbol_position": "before",
        "country": "Bahrain",
        "flag": "🇧🇭",
    },
    "OMR": {
        "code": "OMR",
        "name": "Omani Rial",
        "symbol": "OMR",
        "alt_symbol": "ر.ع",
        "decimals": 3,
        "symbol_position": "before",
        "country": "Oman",
        "flag": "🇴🇲",
    },
    "QAR": {
        "code": "QAR",
        "name": "Qatari Riyal",
        "symbol": "QR",
        "alt_symbol": "ر.ق",
        "decimals": 2,
        "symbol_position": "before",
        "country": "Qatar",
        "flag": "🇶🇦",
    },
    "GBP": {
        "code": "GBP",
        "name": "British Pound",
        "symbol": "£",
        "decimals": 2,
        "symbol_position": "before",
        "country": "United Kingdom",
        "flag": "🇬🇧",
    },
    "CAD": {
        "code": "CAD",
        "name": "Canadian Dollar",
        "symbol": "C$",
        "decimals": 2,
        "symbol_position": "before",
        "country": "Canada",
        "flag": "🇨🇦",
    },
    "AUD": {
        "code": "AUD",
        "name": "Australian Dollar",
        "symbol": "A$",
        "decimals": 2,
        "symbol_position": "before",
        "country": "Australia",
        "flag": "🇦🇺",
    },
    "SGD": {
        "code": "SGD",
        "name": "Singapore Dollar",
        "symbol": "S$",
        "decimals": 2,
        "symbol_position": "before",
        "country": "Singapore",
        "flag": "🇸🇬",
    },
    "JPY": {
        "code": "JPY",
        "name": "Japanese Yen",
        "symbol": "¥",
        "decimals": 0,
        "symbol_position": "before",
        "country": "Japan",
        "flag": "🇯🇵",
    },
    "CNY": {
        "code": "CNY",
        "name": "Chinese Yuan",
        "symbol": "¥",
        "decimals": 2,
        "symbol_position": "before",
        "country": "China",
        "flag": "🇨🇳",
    },
}

# Fallback rates relative to USD (1 USD = X Currency)
FALLBACK_RATES_TO_USD: Dict[str, float] = {
    "USD": 1.0,
    "INR": 83.50,
    "EUR": 0.92,
    "GBP": 0.79,
    "AED": 3.6725,
    "SAR": 3.75,
    "KWD": 0.307,
    "BHD": 0.376,
    "OMR": 0.385,
    "QAR": 3.64,
    "CAD": 1.37,
    "AUD": 1.52,
    "SGD": 1.34,
    "JPY": 154.50,
    "CNY": 7.24,
}

# In-memory cache for live rates: { base_currency: { 'rates': {...}, 'timestamp': float } }
_RATES_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour
CACHE_FILE_PATH = os.path.join(os.path.dirname(__file__), "instance", "exchange_rates_cache.json")


def _load_disk_cache() -> None:
    global _RATES_CACHE
    if not os.path.exists(CACHE_FILE_PATH):
        return
    try:
        with open(CACHE_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                _RATES_CACHE.update(data)
    except Exception:
        pass


def _save_disk_cache() -> None:
    try:
        os.makedirs(os.path.dirname(CACHE_FILE_PATH), exist_ok=True)
        with open(CACHE_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(_RATES_CACHE, f)
    except Exception:
        pass


# Load disk cache on module import
_load_disk_cache()


def fetch_live_rates(base: str = "USD") -> Dict[str, float]:
    """
    Fetch exchange rates for a given base currency using open.er-api.com.
    Returns dictionary mapping currency code -> exchange rate.
    Uses memory and disk cache with 1 hour TTL.
    """
    base = base.upper().strip()
    now = time.time()

    # Check cache
    cached = _RATES_CACHE.get(base)
    if cached and (now - cached.get("timestamp", 0)) < CACHE_TTL_SECONDS:
        return cached.get("rates", {})

    # Attempt live API fetch
    url = f"https://open.er-api.com/v6/latest/{base}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Qiyadah-ERP-ExchangeService/1.0"}
        )
        with urllib.request.urlopen(req, timeout=3.5) as response:
            if response.status == 200:
                body = response.read().decode("utf-8")
                data = json.loads(body)
                if data.get("result") == "success" and "rates" in data:
                    rates = data["rates"]
                    _RATES_CACHE[base] = {
                        "rates": rates,
                        "timestamp": now
                    }
                    _save_disk_cache()
                    return rates
    except Exception:
        # Silently proceed to fallback matrix
        pass

    # If base was in cached even if expired, return it
    if cached and cached.get("rates"):
        return cached["rates"]

    # Fallback rates derivation
    base_to_usd = FALLBACK_RATES_TO_USD.get(base, 1.0)
    calculated_rates: Dict[str, float] = {}
    for code, rate_to_usd in FALLBACK_RATES_TO_USD.items():
        # 1 Base = (rate_to_usd / base_to_usd) Code
        calculated_rates[code] = round(rate_to_usd / base_to_usd, 6)

    return calculated_rates


def get_exchange_rate(from_curr: str, to_curr: str) -> float:
    """
    Get the conversion rate from one currency to another (1 from_curr = X to_curr).
    """
    from_curr = (from_curr or "INR").upper().strip()
    to_curr = (to_curr or "INR").upper().strip()

    if from_curr == to_curr:
        return 1.0

    rates = fetch_live_rates(from_curr)
    if to_curr in rates:
        return float(rates[to_curr])

    # Reverse lookup if from_curr rates didn't have to_curr
    rev_rates = fetch_live_rates(to_curr)
    if from_curr in rev_rates and rev_rates[from_curr] > 0:
        return round(1.0 / float(rev_rates[from_curr]), 6)

    # Fallback to USD triangulation
    from_usd = FALLBACK_RATES_TO_USD.get(from_curr, 1.0)
    to_usd = FALLBACK_RATES_TO_USD.get(to_curr, 1.0)
    if from_usd > 0:
        return round(to_usd / from_usd, 6)

    return 1.0


def convert_amount(amount: float, from_curr: str, to_curr: str, custom_rate: Optional[float] = None) -> float:
    """
    Convert an amount from from_curr to to_curr using custom_rate or live exchange rate.
    """
    if not amount:
        return 0.0
    try:
        val = float(amount)
    except (ValueError, TypeError):
        return 0.0

    from_curr = (from_curr or "INR").upper().strip()
    to_curr = (to_curr or "INR").upper().strip()

    if from_curr == to_curr:
        return val

    rate = custom_rate if (custom_rate is not None and custom_rate > 0) else get_exchange_rate(from_curr, to_curr)
    return round(val * rate, 4)


def get_currency_info(code: Optional[str]) -> Dict[str, Any]:
    """
    Retrieve currency metadata (symbol, name, decimals, flag, etc.).
    Defaults to INR if not specified or unknown.
    """
    code = (code or "INR").upper().strip()
    if code in CURRENCIES:
        return CURRENCIES[code]

    # Return reasonable default for unregistered currency
    return {
        "code": code,
        "name": code,
        "symbol": code,
        "decimals": 2,
        "symbol_position": "before",
        "country": "Global",
        "flag": "🌐",
    }


def format_currency_amount(
    amount: Any,
    currency_code: Optional[str] = "INR",
    show_symbol: bool = True,
    show_code: bool = False
) -> str:
    """
    Format numeric value according to currency rules.
    Examples:
      format_currency_amount(1250.5, "USD") -> "$1,250.50"
      format_currency_amount(15.75, "KWD") -> "KD 15.750"
      format_currency_amount(50000, "INR") -> "₹50,000.00"
    """
    if amount is None:
        amount = 0.0
    try:
        val = float(amount)
    except (ValueError, TypeError):
        val = 0.0

    info = get_currency_info(currency_code)
    decimals = info.get("decimals", 2)
    symbol = info.get("symbol", "")
    code = info.get("code", "INR")

    formatted_num = f"{val:,.{decimals}f}"

    parts = []
    if show_symbol and symbol:
        # If symbol is text (like AED or KD), add a space
        if len(symbol) > 1:
            parts.append(f"{symbol} {formatted_num}")
        else:
            parts.append(f"{symbol}{formatted_num}")
    else:
        parts.append(formatted_num)

    if show_code and code not in symbol:
        parts.append(f" {code}")

    return "".join(parts)


def get_all_currencies_list():
    """Return array of currency objects suitable for JSON API response."""
    return list(CURRENCIES.values())

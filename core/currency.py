# core/currency.py
"""
Live USD <-> UGX conversion with periodic refresh.

- Fetches from open.er-api.com (free, no key).
- Caches in memory.
- Falls back to last-known rate on network failure.
- Exposes USD + UGX for display; retains NGN/KES/CNY/GBP/EUR
  so adapters that emit local prices are converted correctly.
"""

import datetime
import requests
import threading
import time

SUPPORTED = ("USD", "UGX")

# Currencies we must be able to convert FROM when saving scraped prices.
CONVERSION_CURRENCIES = ("USD", "UGX", "NGN", "KES", "CNY", "GBP", "EUR")

_API = "https://open.er-api.com/v6/latest/USD"

_FALLBACK = {
    "USD": 1.0,
    "UGX": 3800.0,
    "NGN": 1500.0,
    "KES": 150.0,
    "CNY": 7.2,
    "GBP": 0.8,
    "EUR": 0.9,
}

_state = {
    "rates": dict(_FALLBACK),
    "fetched_at": None,
    "source": "fallback",
}
_lock = threading.Lock()


def _fetch():
    try:
        r = requests.get(_API, timeout=8)
        r.raise_for_status()
        j = r.json()
        if j.get("result") == "success" and "rates" in j:
            all_rates = j["rates"]
            new_rates = {"USD": 1.0}
            for code in CONVERSION_CURRENCIES:
                if code == "USD":
                    continue
                val = all_rates.get(code)
                if val and val > 0:
                    new_rates[code] = float(val)
            for code, val in _FALLBACK.items():
                new_rates.setdefault(code, val)
            with _lock:
                _state["rates"] = new_rates
                _state["fetched_at"] = datetime.datetime.utcnow().isoformat()
                _state["source"] = "open.er-api.com"
            return True
    except Exception:
        pass
    return False


def _refresher():
    _fetch()
    while True:
        time.sleep(6 * 3600)
        _fetch()


threading.Thread(target=_refresher, daemon=True).start()


def get_rates():
    """Return {'USD': 1.0, 'UGX': ..., 'NGN': ..., ...} plus metadata."""
    with _lock:
        return {
            "rates": dict(_state["rates"]),
            "fetched_at": _state["fetched_at"],
            "source": _state["source"],
        }


def convert_usd_to(amount_usd, currency):
    """Convert USD to UGX (or return USD unchanged)."""
    if amount_usd is None:
        return None
    currency = (currency or "USD").upper()
    if currency not in SUPPORTED:
        currency = "USD"
    rate = get_rates()["rates"].get(currency, 1.0)
    return round(float(amount_usd) * rate, 2)


def to_usd(amount_local, currency):
    """Convert a local-currency amount to USD."""
    if amount_local is None:
        return None
    currency = (currency or "USD").upper()
    rate = get_rates()["rates"].get(currency)
    if not rate:
        return None
    return round(float(amount_local) / rate, 2)


def format_price(amount_usd, currency="USD"):
    """Pretty-format for the UI."""
    if amount_usd is None:
        return "N/A"
    currency = (currency or "USD").upper()
    if currency not in SUPPORTED:
        currency = "USD"
    val = convert_usd_to(amount_usd, currency)
    if currency == "UGX":
        return f"UGX {val:,.0f}"
    return f"${val:,.2f}"
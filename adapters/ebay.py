import os
import time
import requests

_token = {"value": None, "exp": 0}

def _get_token():
    if _token["value"] and time.time() < _token["exp"] - 60:
        return _token["value"]
    r = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials",
              "scope": "https://api.ebay.com/oauth/api_scope"},
        auth=(os.environ["EBAY_CLIENT_ID"], os.environ["EBAY_CLIENT_SECRET"]),
        timeout=15,
    )
    r.raise_for_status()
    j = r.json()
    _token.update(value=j["access_token"], exp=time.time() + j["expires_in"])
    return _token["value"]

def scrape_ebay(limit=50, query="smartphone"):
    items, offset = [], 0
    while len(items) < limit:
        r = requests.get(
            "https://api.ebay.com/buy/browse/v1/item_summary/search",
            headers={"Authorization": f"Bearer {_get_token()}",
                     "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
            params={"q": query, "limit": min(200, limit - len(items)), "offset": offset},
            timeout=20,
        )
        r.raise_for_status()
        batch = r.json().get("itemSummaries", [])
        if not batch:
            break
        for it in batch:
            price = it.get("price") or {}
            if not price.get("value"):
                continue
            items.append({
                "platform": "ebay",
                "sku": it["itemId"],
                "title": it["title"],
                "price": float(price["value"]),
                "currency": price.get("currency", "USD"),
                "stock_status": "In Stock",
                "url": it["itemWebUrl"],
            })
        offset += len(batch)
    return items[:limit]
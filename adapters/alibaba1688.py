import os
import hmac
import hashlib
import base64
import time
import requests

_URL = "https://gw.open.1688.com/openapi/param2/1/com.alibaba.product/product.topList.query/"


def _sign(params: dict) -> str:
    sign_str = "".join(f"{k}{v}" for k, v in sorted(params.items()))
    return base64.b64encode(
        hmac.new(os.environ["ALI1688_SECRET"].encode(), sign_str.encode(), hashlib.sha1).digest()
    ).decode()


def scrape_alibaba(limit=50, category_id="1031918"):
    items, page = [], 1
    while len(items) < limit:
        params = {
            "appKey": os.environ["ALI1688_KEY"],
            "timestamp": str(int(time.time() * 1000)),
            "rank_type": "hot",
            "categoryId": category_id,
            "pageSize": min(50, limit - len(items)),
            "pageNo": str(page),
        }
        params["sign"] = _sign(params)
        resp = requests.post(_URL, data=params, timeout=15)
        resp.raise_for_status()
        data = resp.json().get("result", {}).get("data", [])
        if not data:
            break
        for it in data:
            price = (it.get("priceInfo") or {}).get("price")
            if price is None:
                continue
            offer_id = str(it["offerId"])
            items.append({
                "platform": "alibaba",
                "sku": f"1688-{offer_id}",
                "title": it["subject"],
                "price": float(price),
                "currency": "CNY",
                "stock_status": "In Stock",
                "url": f"https://detail.1688.com/offer/{offer_id}.html",
            })
        page += 1
    return items[:limit]
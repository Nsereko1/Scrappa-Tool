# seed_demo.py — one-shot: replace bestseller.db with realistic cross-platform data
import datetime, random
from core.db import init_db, save_items, get_db_connection

random.seed(11)

CATALOGUE = [
    # (canonical, base_usd, {platform: title})
    ("iPhone 14 Pro", 999.0, {
        "jumia":   "Apple iPhone 14 Pro 128GB 6GB RAM Dual SIM",
        "amazon":  "Apple iPhone 14 Pro 128GB Unlocked Smartphone",
        "ebay":    "Apple iPhone 14 Pro 128GB - Unlocked - Excellent",
        "kibuga":  "Apple iPhone 14 Pro 128GB Storage 6GB RAM",
        "alibaba": "iPhone 14 Pro 128GB Original Apple Smartphone",
    }),
    ("iPhone 14 Pro Max", 1199.0, {
        "amazon":  "Apple iPhone 14 Pro Max 256GB Unlocked Deep Purple",
        "ebay":    "Apple iPhone 14 Pro Max 256GB - Unlocked",
        "alibaba": "iPhone 14 Pro Max 256GB Original Apple Smartphone",
        "jumia":   "Apple iPhone 14 Pro Max 256GB 6GB RAM Dual SIM",
    }),
    ("Samsung Galaxy S24 Ultra", 1199.0, {
        "jumia":   "Samsung Galaxy S24 Ultra 256GB 12GB RAM Dual SIM",
        "amazon":  "Samsung Galaxy S24 Ultra 256GB Unlocked Smartphone",
        "ebay":    "Samsung Galaxy S24 Ultra 256GB - Unlocked",
        "alibaba": "Samsung Galaxy S24 Ultra 256GB Original",
    }),
    ("Samsung Galaxy S24 Plus", 999.0, {
        "amazon":  "Samsung Galaxy S24 Plus 256GB Unlocked",
        "ebay":    "Samsung Galaxy S24 Plus 256GB - Unlocked",
    }),
    ("Nike Air Max 90", 130.0, {
        "jumia":   "Nike Air Max 90 Running Shoes For Men White",
        "kibuga":  "Nike Air Max 90 Sneakers Men Running",
        "amazon":  "Nike Air Max 90 Men's Running Shoes",
        "ebay":    "Nike Air Max 90 Running Shoes Men Size 10",
        "alibaba": "Nike Air Max 90 Men Running Sneakers",
    }),
    ("Sony WH-1000XM5", 380.0, {
        "jumia":   "Sony WH-1000XM5 Wireless Noise Cancelling Headphones",
        "amazon":  "Sony WH-1000XM5 Wireless Noise Canceling Headphones",
        "ebay":    "Sony WH-1000XM5 Wireless Headphones Black",
        "alibaba": "Sony WH-1000XM5 Headphones Wireless Bluetooth",
    }),
]

CURRENCY = {
    "jumia":   ("NGN", "NG", 1500.0),
    "kibuga":  ("UGX", "UG", 3800.0),
    "amazon":  ("USD", "US", 1.0),
    "ebay":    ("USD", "US", 1.0),
    "alibaba": ("CNY", "GLOBAL", 7.2),
}

def slug(t):
    import re
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")

def main():
    init_db()
    items, idx = [], 0
    for canonical, base_usd, titles in CATALOGUE:
        for plat, title in titles.items():
            cur, region, rate = CURRENCY[plat]
            # ±10% price spread so different platforms have different prices
            usd = round(base_usd * random.uniform(0.9, 1.1), 2)
            local = round(usd * rate, 2)
            items.append({
                "platform": plat, "region": region,
                "sku": f"{plat.upper()}-{slug(canonical)[:20].upper()}-{idx}",
                "title": title, "price": local, "currency": cur,
                "stock_status": "In Stock",
                "url": f"https://example.com/{plat}/{slug(title)}-{idx}",
            })
            idx += 1

    n = save_items(items, datetime.date.today().isoformat())
    print(f"Seeded {n} new items from {len(CATALOGUE)} products across "
          f"{len(CURRENCY)} platforms")

if __name__ == "__main__":
    main()

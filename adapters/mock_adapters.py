
import random
import urllib.parse
import string

_APPLIANCE = [
    "Samsung 400L Double Door Refrigerator",
    "LG 350L Inverter Refrigerator",
    "Hisense 300L Top Freezer Fridge",
    "Haier 250L Single Door Refrigerator",
    "LG 8kg Front Load Washing Machine",
    "Samsung 7kg Top Load Washer",
    "Hisense 10kg Twin Tub Washing Machine",
    "Samsung 30L Microwave Oven",
    "LG 25L Convection Microwave",
    "Philips 4.1L Air Fryer",
    "LG 1.5HP Split Air Conditioner",
]
_TV = [
    "Hisense 43A6G 43 inch 4K Smart TV",
    "Hisense 55U7G 55 inch ULED 4K TV",
    "Samsung 55 inch QLED 4K Smart TV",
    "LG 50 inch 4K Smart LED TV",
    "Sony 65 inch Bravia OLED 4K TV",
]
_LAPTOP = [
    "Apple MacBook Pro 14 M3 512GB",
    "Apple MacBook Pro 16 M2 Pro 1TB",
    "Apple MacBook Air 13 M2 256GB",
    "Dell XPS 13 Intel Core i7 16GB",
    "Lenovo ThinkPad X1 Carbon Gen 11",
]
_PHONE = [
    "Apple iPhone 14 Pro 128GB Unlocked",
    "Apple iPhone 14 Pro Max 256GB Deep Purple",
    "Apple iPhone 14 128GB Dual SIM",
    "Samsung Galaxy S24 Ultra 256GB",
    "Samsung Galaxy A14 128GB Dual SIM",
    "Xiaomi Redmi Note 12 128GB",
]
_AUDIO = [
    "Sony WH-1000XM5 Wireless Noise Cancelling Headphones",
    "Apple AirPods Pro 2nd Gen",
    "JBL Tune 720BT Wireless Headphones",
    "Bose QuietComfort 45 Headphones",
]
_NIKE = [
    "Nike Air Max 90 Running Shoes",
    "Nike Air Max 270 Sneakers",
    "Nike Air Force 1 Low White",
]
_GAMING = [
    "Sony PlayStation 5 Console",
    "Xbox Series X Console",
    "Nintendo Switch OLED",
]
_POWER = [
    "Oraimo 20000mAh Power Bank 22.5W",
    "Anker 10000mAh PowerCore",
    "Baseus 65W USB-C Charger",
]

def _biased_titles(query, fallback):
    if not query:
        return fallback
    q = query.lower()
    if any(k in q for k in ("fridge","refrigerator","freezer","washing","washer","dryer","microwave","oven","cooker","air fryer","air conditioner","vacuum","appliance")):
        return _APPLIANCE
    if any(k in q for k in ("tv","hisense","television")):
        return _TV
    if any(k in q for k in ("laptop","macbook","notebook","computer")):
        return _LAPTOP
    if any(k in q for k in ("headphone","earbud","headset","airpods","wh-1000","speaker","audio")):
        return _AUDIO
    if any(k in q for k in ("nike","adidas","shoe","sneaker")):
        return _NIKE
    if any(k in q for k in ("gaming","console","playstation","xbox","nintendo","ps5")):
        return _GAMING
    if any(k in q for k in ("power","charger","battery","inverter")):
        return _POWER
    if any(k in q for k in ("iphone","galaxy","phone","smartphone","xiaomi","tecno","infinix","redmi")):
        return _PHONE
    return fallback

def generate_mock(platform, titles, limit, region="GLOBAL", query=None):
    items = []
    if platform == "alibaba":
        region = "GLOBAL"
    titles = _biased_titles(query, titles)
    for _ in range(limit):
        unique_code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        base = random.choice(titles)
        title = f"{base} - " + random.choice(["New", "Used", "Refurbished"]) + f" - {unique_code}"
        encoded_title = urllib.parse.quote(title)
        if platform == "amazon":
            domain = ".co.uk" if region == "UK" else ".com"
            url = f"https://www.amazon{domain}/s?k={encoded_title}"
        elif platform == "ebay":
            domain = ".co.uk" if region == "UK" else ".com"
            url = f"https://www.ebay{domain}/sch/i.html?_nkw={encoded_title}"
        elif platform == "alibaba":
            url = f"https://www.alibaba.com/trade/search?SearchText={encoded_title}"
        else:
            url = f"https://{platform}.com/search?q={encoded_title}"
        items.append({
            "platform": platform,
            "region": region,
            "sku": f"{platform.upper()}-{unique_code}",
            "title": title,
            "price": round(random.uniform(50.0, 2000.0), 2),
            "currency": "USD",
            "stock_status": random.choice(["In Stock","In Stock","Out of Stock"]),
            "url": url,
        })
    return items

def scrape_amazon_mock(limit=10, region="US", query=None):
    return generate_mock("amazon", ["Echo Dot"], limit, region, query=query)

def scrape_alibaba_mock(limit=10, region="GLOBAL", query=None):
    return generate_mock("alibaba", ["Wireless Earbuds"], limit, region, query=query)

def scrape_ebay_mock(limit=10, region="US", query=None):
    return generate_mock("ebay", ["iPhone 13"], limit, region, query=query)

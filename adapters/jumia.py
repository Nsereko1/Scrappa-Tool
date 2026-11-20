
_QUERY_TITLES = {
    "fridge": ["Samsung 400L Double Door Refrigerator", "LG 350L Inverter Refrigerator", "Hisense 300L Top Freezer Fridge"],
    "washing machine": ["LG 8kg Front Load Washing Machine", "Samsung 7kg Top Load Washer"],
    "microwave": ["Samsung 30L Microwave Oven", "LG 25L Convection Microwave"],
    "tv": ["Hisense 43A6G 43 inch 4K Smart TV", "Samsung 55 inch QLED 4K Smart TV"],
    "laptop": ["Apple MacBook Pro 14 M3 512GB", "Dell XPS 13 Intel Core i7 16GB"],
    "phone": ["Apple iPhone 14 Pro 128GB", "Samsung Galaxy S24 Ultra 256GB"],
}

def _query_titles(query, fallback):
    if not query: return fallback
    q = query.lower()
    for key, titles in _QUERY_TITLES.items():
        if key in q: return titles
    return fallback

import random
import json
import urllib.parse
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
import re
import string

JUMIA_DOMAINS = {
    "NG": "https://www.jumia.com.ng",
    "KE": "https://www.jumia.co.ke",
    "UG": "https://www.jumia.ug"
}

CATEGORY_URLS = {
    "phones": ["phones-tablets"],
    "tvs": ["tvs"],
    "clothes": ["fashion"],
    "all": ["phones-tablets", "tvs", "fashion"]
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}


try:
    from core.scrape_query import filter_by_query as _filter_by_query
except Exception:
    def _filter_by_query(items, q, log_prefix=""):
        return items

def _session():
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=1))
    s.headers.update(HEADERS)
    return s

def _slugify(text):
    """Converts a product title into a Jumia-style URL slug."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    return text.strip('-')

def _generate_mock(limit, category, region, query=None):
    # Full product titles similar to real Jumia listings
    titles = [
        "Fashion 6 Piece Mens Bracelet Wooden Bead Stackable Elastic Design For Daily Wear Gift Multi",
        "Samsung Galaxy A14 128GB 4GB RAM Dual SIM Android 13",
        "Infinix Hot 30 256GB 8GB RAM 50MP Camera 5000mAh Battery",
        "Tecno Spark 10 128GB 4GB RAM 50MP Selfie Camera",
        "Xiaomi Redmi Note 12 128GB 6GB RAM 50MP Triple Camera",
        "Oraimo 20000mAh Power Bank 22.5W Fast Charging",
        "itel A60 32GB 2GB RAM 6.6 inch HD+ Display",
        "Nike Air Max 90 Running Shoes For Men",
        "Sony WH-1000XM5 Wireless Noise Cancelling Headphones",
        "Apple iPhone 13 128GB 6.1 inch Super Retina XDR Display",
    ]
    titles = _query_titles(query, titles)
    items = []
    for _ in range(limit):
        title = random.choice(titles)
        # Use the FULL title for the slug, not truncated
        slug = _slugify(title)
        
        # Generate a realistic 9-digit numeric Jumia product ID (no mpg prefix)
        product_id = ''.join(random.choices(string.digits, k=9))
        
        base_url = JUMIA_DOMAINS.get(region.upper(), JUMIA_DOMAINS["NG"])
        # Construct a direct product URL like: https://www.jumia.ug/full-slug-259622657.html
        url = f"{base_url}/{slug}-{product_id}.html"
        
        currency = "NGN" if region == "NG" else ("KES" if region == "KE" else "UGX")
        items.append({
            "platform": "jumia", "region": region, "sku": f"MOCK-{random.randint(1000,9999)}",
            "title": title, "price": round(random.uniform(50000.0, 500000.0), 2),
            "currency": currency, "stock_status": "In Stock", "url": url,
        })
    return items

def scrape_jumia(limit=100, start_page=1, category="phones", region="NG", query=None):
    BASE = JUMIA_DOMAINS.get(region.upper(), JUMIA_DOMAINS["NG"])
    print(f"[jumia-{region}] fetching (limit={limit}, category={category}, start_page={start_page})...", flush=True)
    items = []
    page = start_page
    pages_to_scrape = (limit // 40) + 1 
    
    urls = CATEGORY_URLS.get(category.lower(), CATEGORY_URLS["phones"])
    pages_scraped = 0
    
    while pages_scraped < pages_to_scrape and len(items) < limit:
        url_suffix = urls[pages_scraped % len(urls)]
        page_url = f"{BASE}/{url_suffix}/?page={page}"
        
        try:
            resp = _session().get(page_url, timeout=(10, 20))
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as exc:
            print(f"[jumia-{region}] FETCH FAILED on page {page} (Blocked by Jumia). Falling back to mock.", flush=True)
            mocks = _generate_mock(limit, category, region)
            if query:
                mocks = _filter_by_query(mocks, query, log_prefix=f"jumia-{region}-mock")
            return mocks, start_page + 1
            
        cards = soup.find_all("article", class_="prd")
        if not cards:
            print(f"[jumia-{region}] No product cards found (Captcha or Empty). Falling back.", flush=True)
            mocks = _generate_mock(limit, category, region)
            if query:
                mocks = _filter_by_query(mocks, query, log_prefix=f"jumia-{region}-mock")
            return mocks, start_page + 1
            
        page_items = []
        for card in cards:
            try:
                link_el = card.find("a", class_="core")
                if not link_el or "href" not in link_el.attrs: continue
                href = link_el["href"]
                
                # Ensure the URL is absolute
                if href.startswith("/"):
                    full_url = f"{BASE}{href}"
                elif not href.startswith("http"):
                    full_url = f"{BASE}/{href}"
                else:
                    full_url = href
                    
                title_el = card.find("h3", class_="name")
                title = title_el.text.strip() if title_el else "Unknown Item"
                price_el = card.find("div", class_="prc")
                if not price_el: continue
                price_text = price_el.text.replace(",", "")
                price_match = re.search(r'(\d+)', price_text)
                if not price_match: continue
                price = float(price_match.group(1))
                
                currency = "NGN" if region == "NG" else ("KES" if region == "KE" else "UGX")

                page_items.append({
                    "platform": "jumia", "region": region, "sku": title[:30].replace(" ", "-").upper(),
                    "title": title, "price": price, "currency": currency,
                    "stock_status": "In Stock", "url": full_url,
                })
            except Exception:
                continue
                
        if not page_items: break
            
        items.extend(page_items)
        page += 1
        pages_scraped += 1
        
    if not items and start_page == 1:
        mocks = _generate_mock(limit, category, region)
        if query:
            mocks = _filter_by_query(mocks, query, log_prefix=f"jumia-{region}-mock")
        return mocks, start_page + 1

    if query:
        items = _filter_by_query(items, query, log_prefix=f"jumia-{region}")
    return items[:limit], page

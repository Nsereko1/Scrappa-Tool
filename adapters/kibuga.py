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
import json
import re
import random
import urllib.parse
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

BASE = "https://kibuga.com"
SHOP_URL = f"{BASE}/shop"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}
_PRICE_RE = re.compile(r"[\d,]+(?:\.\d+)?")


try:
    from core.scrape_query import filter_by_query as _filter_by_query
except Exception:
    def _filter_by_query(items, q, log_prefix=""):
        return items

def _session():
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=2))
    s.headers.update(HEADERS)
    return s

def _parse_price(text):
    m = _PRICE_RE.search((text or "").replace(",", ""))
    return float(m.group()) if m else None

def _generate_mock(limit, region="UG", query=None):
    titles = ["Lenovo Charger", "Tropical Heat Rosemary", "Phelistar Decoder", "Prof Borax Powder", "Himalaya Baby Pack", "M.2 SSD Enclosure"]
    titles = _query_titles(query, titles)
    items = []
    for _ in range(limit):
        title = random.choice(titles) + f" - {random.choice(['A', 'B', 'C'])}"
        encoded_title = urllib.parse.quote(title)
        url = f"{BASE}/?s={encoded_title}&post_type=product"
        items.append({
            "platform": "kibuga", "region": region, "sku": f"KIBUGA-MOCK-{random.randint(1000,9999)}",
            "title": title, "price": round(random.uniform(20000.0, 400000.0), 2),
            "currency": "UGX", "stock_status": "In Stock", "url": url,
        })
    return items

# Added region parameter back here
def scrape_kibuga(limit=100, start_page=1, region="UG", query=None, category=None):
    print(f"[kibuga] fetching (limit={limit}, start_page={start_page})...", flush=True)
    items = []
    page = start_page
    pages_to_scrape = (limit // 24) + 1

    pages_scraped = 0
    while pages_scraped < pages_to_scrape and len(items) < limit:
        page_url = f"{SHOP_URL}?page={page}"
        try:
            resp = _session().get(page_url, timeout=(10, 30))
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
        except requests.RequestException as exc:
            print(f"[kibuga] FETCH FAILED on page {page}: {exc}", flush=True)
            break

        page_items = []
        for card in soup.select("li.product, .product-item, .product-small"):
            try:
                title_el = card.select_one("h2, h3, .product-title, .woocommerce-loop-product__title")
                price_el = card.select_one(".price, .amount, .woocommerce-Price-amount")
                link_el = card.select_one("a[href]")
                
                if not (title_el and price_el and link_el): continue
                title = title_el.get_text(strip=True)
                price = _parse_price(price_el.get_text())
                if price is None: continue
                
                href = link_el["href"]
                if href.startswith("/"): href = f"{BASE}{href}"
                elif not href.startswith("http"): href = f"{BASE}/{href}"
                
                page_items.append({
                    "platform": "kibuga", "region": region, "sku": title[:40].replace(" ", "-").upper(),
                    "title": title, "price": price, "currency": "UGX", "stock_status": "In Stock", "url": href,
                })
            except Exception:
                continue

        if not page_items:
            print(f"[kibuga] No items found on page {page}. Stopping.", flush=True)
            break

        items.extend(page_items)
        print(f"[kibuga] Page {page} scraped. Total this batch: {len(items)}", flush=True)
        page += 1
        pages_scraped += 1

    if not items and start_page == 1:
        print("[kibuga] Scrape failed. Using mock data.", flush=True)
        mocks = _generate_mock(limit, region)
        if query:
            mocks = _filter_by_query(mocks, query, log_prefix="kibuga-mock")
        return mocks, start_page + 1

    if query:
        items = _filter_by_query(items, query, log_prefix="kibuga")
    return items[:limit], page

#!/usr/bin/env python3
"""
fetch_iphone14.py - fetch up to N real iPhone 14 listings from each shop and save them to bestseller.db.

  python fetch_iphone14.py --clean-mock          # first run: back up DB, remove demo rows, then fetch
  python fetch_iphone14.py                       # fetch 100 per shop (Jumia UG, Kibuga, eBay)
  python fetch_iphone14.py --limit 50 --jumia-region KE
  python fetch_iphone14.py --dry-run             # print what was found, save nothing
  python fetch_iphone14.py --only kibuga,jumia

Never saves mock data. A shop that cannot be reached is reported and skipped.
Amazon and Alibaba need official API access, so they are reported as skipped.
"""
import argparse
import datetime
import os
import re
import shutil
import sqlite3
import sys
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

DB_PATH = "bestseller.db"
DELAY = 1.5   # seconds between page requests, to stay polite

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

HEADERS.update({"Accept-Language": "en-US,en;q=0.9", "Referer": "https://www.google.com/", "Upgrade-Insecure-Requests": "1", "Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Site": "cross-site", "Sec-Fetch-User": "?1"})

IPHONE14_RE = re.compile(r"i\s?phone\s*-?\s*14(?!\d)", re.I)
ACCESSORY_RE = re.compile(
    r"\b(case|cases|cover|covers|protector|charger|cable|adapter|pouch|holder|strap|skin|"
    r"sticker|tempered|glass|stand|lens|housing|replacement|screen|bumper)\b|\bfor\s+(apple\s+)?iphone",
    re.I,
)
JUMIA_DOMAINS = {"UG": "https://www.jumia.ug", "NG": "https://www.jumia.com.ng", "KE": "https://www.jumia.co.ke"}
JUMIA_CURRENCY = {"UG": "UGX", "NG": "NGN", "KE": "KES"}


def is_iphone14(title):
    return bool(IPHONE14_RE.search(title or "")) and not ACCESSORY_RE.search(title or "")


def session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def first_number(text):
    m = re.search(r"\d+(?:\.\d+)?", (text or "").replace(",", ""))
    return float(m.group()) if m else None


# ------------------------------------------------------------------ Jumia
def fetch_jumia(limit, region, log):
    base = JUMIA_DOMAINS[region]
    sess, items, seen = session(), [], set()
    for page in range(1, 16):
        url = f"{base}/catalog/?q=iphone+14&page={page}"
        try:
            resp = sess.get(url, timeout=(10, 30))
            resp.raise_for_status()
        except requests.RequestException as exc:
            log(f"request failed on page {page}: {exc}")
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.find_all("article", class_="prd")
        if not cards:
            log(f"no product cards on page {page} (end of results, or Jumia blocked the request)")
            break
        for card in cards:
            link = card.find("a", class_="core")
            title_el = card.find("h3", class_="name")
            price_el = card.find("div", class_="prc")
            if not (link and link.get("href") and title_el and price_el):
                continue
            title = title_el.get_text(" ", strip=True)
            if not is_iphone14(title):
                continue
            href = urljoin(base + "/", link["href"].split("?")[0])
            m = re.search(r"-(\d+)\.html$", href)
            sku = f"JUMIA-{region}-{m.group(1)}" if m else None
            price = first_number(price_el.get_text(" ", strip=True))
            if not sku or price is None or sku in seen:
                continue
            seen.add(sku)
            items.append({"platform": "jumia", "region": region, "sku": sku, "title": title,
                          "price": price, "currency": JUMIA_CURRENCY[region],
                          "stock_status": "In Stock", "url": href})
            if len(items) >= limit:
                return items
        log(f"page {page}: {len(items)} iPhone 14 listings so far")
        time.sleep(DELAY)
    return items


# ------------------------------------------------------------------ Kibuga
KIBUGA_BASE = "https://kibuga.com"
# Phones & Tablets category, filtered to the Apple brand (brand_ids[0]=7)
KIBUGA_START = f"{KIBUGA_BASE}/category/phones-tablets-mczuu/4?brand_ids%5B0%5D=7"
_KIBUGA_PRODUCT = re.compile(r"/product/[^/?#]+/(\d+)/?$")
_KIBUGA_PRICE = re.compile(r"UGX\s*([\d,]+(?:\.\d+)?)")


def _kibuga_cards(soup):
    found = []
    for a in soup.find_all("a", href=True):
        m = _KIBUGA_PRODUCT.search(a["href"])
        title = a.get_text(" ", strip=True)
        if not m or not title:
            continue
        pid, price, node = m.group(1), None, a
        for _ in range(5):                      # climb to the card that holds the price
            node = node.parent
            if node is None:
                break
            ids = {_KIBUGA_PRODUCT.search(x["href"]).group(1)
                   for x in node.find_all("a", href=True) if _KIBUGA_PRODUCT.search(x["href"])}
            if len(ids) > 1:
                break
            pm = _KIBUGA_PRICE.search(node.get_text(" ", strip=True))
            if pm:
                price = float(pm.group(1).replace(",", ""))
                break
        if price is not None:
            found.append((pid, title, price, urljoin(KIBUGA_BASE, a["href"].split("?")[0])))
    return found


def _kibuga_next(soup):
    for a in soup.find_all("a", href=True):
        if a.get_text(strip=True).lower().startswith("next") and "cursor=" in a["href"]:
            return urljoin(KIBUGA_BASE, a["href"])
    return None


def fetch_kibuga(limit, max_pages, log):
    sess, items, seen = session(), [], set()
    url, scanned = KIBUGA_START, 0
    while url and scanned < max_pages and len(items) < limit:
        try:
            resp = sess.get(url, timeout=(10, 30))
            resp.raise_for_status()
        except requests.RequestException as exc:
            log(f"request failed: {exc}")
            break
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = _kibuga_cards(soup)
        if not cards:
            log("no product cards found on this page")
            break
        for pid, title, price, href in cards:
            sku = f"KIBUGA-{pid}"
            if sku in seen or not is_iphone14(title):
                continue
            seen.add(sku)
            items.append({"platform": "kibuga", "region": "UG", "sku": sku, "title": title,
                          "price": price, "currency": "UGX", "stock_status": "In Stock", "url": href})
        scanned += 1
        log(f"page {scanned}: {len(items)} iPhone 14 listings so far")
        url = _kibuga_next(soup)
        time.sleep(DELAY)
    return items[:limit]


# ------------------------------------------------------------------ eBay (official API)
def fetch_ebay(limit, log):
    cid, secret = os.environ.get("EBAY_CLIENT_ID"), os.environ.get("EBAY_CLIENT_SECRET")
    if not (cid and secret):
        raise RuntimeError("EBAY_CLIENT_ID / EBAY_CLIENT_SECRET not set in this terminal")
    tok = requests.post(
        "https://api.ebay.com/identity/v1/oauth2/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
        auth=(cid, secret), timeout=15,
    )
    tok.raise_for_status()
    headers = {"Authorization": f"Bearer {tok.json()['access_token']}",
               "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"}
    items, seen, offset = [], set(), 0
    while len(items) < limit and offset < 1000:
        r = requests.get(
            "https://api.ebay.com/buy/browse/v1/item_summary/search", headers=headers, timeout=20,
            params={"q": "iphone 14", "category_ids": "9355", "limit": 200, "offset": offset},
        )
        r.raise_for_status()
        batch = r.json().get("itemSummaries", [])
        if not batch:
            break
        for it in batch:
            price = it.get("price") or {}
            title = it.get("title", "")
            if not price.get("value") or not is_iphone14(title) or it["itemId"] in seen:
                continue
            seen.add(it["itemId"])
            items.append({"platform": "ebay", "region": "US", "sku": it["itemId"], "title": title,
                          "price": float(price["value"]), "currency": price.get("currency", "USD"),
                          "stock_status": "In Stock", "url": it["itemWebUrl"]})
            if len(items) >= limit:
                break
        offset += len(batch)
        log(f"offset {offset}: {len(items)} iPhone 14 listings so far")
    return items[:limit]


# ------------------------------------------------------------------ DB cleanup
def clean_mock(db_path):
    if not os.path.exists(db_path):
        print(f"[clean] {db_path} not found, nothing to clean")
        return
    backup = f"{db_path}.backup-{datetime.datetime.now():%Y%m%d-%H%M%S}"
    shutil.copy2(db_path, backup)
    cond = ("sku LIKE '%MOCK%' OR sku LIKE 'EBAY-%' OR sku LIKE 'AMAZON-%' OR sku LIKE 'ALIBABA-%'")
    con = sqlite3.connect(db_path, timeout=30)
    n = con.execute(f"SELECT COUNT(*) FROM bestsellers WHERE {cond}").fetchone()[0]
    con.execute(f"DELETE FROM price_history WHERE sku IN (SELECT sku FROM bestsellers WHERE {cond})")
    con.execute(f"DELETE FROM bestsellers WHERE {cond}")
    con.commit()
    con.close()
    print(f"[clean] backed up to {backup}; removed {n:,} demo rows")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="Fetch real iPhone 14 listings from each shop.")
    ap.add_argument("--limit", type=int, default=100, help="max items per shop (default 100)")
    ap.add_argument("--jumia-region", default="UG", choices=sorted(JUMIA_DOMAINS))
    ap.add_argument("--kibuga-pages", type=int, default=25, help="max Kibuga pages to read")
    ap.add_argument("--only", default="jumia,kibuga,ebay", help="comma list of shops to fetch")
    ap.add_argument("--dry-run", action="store_true", help="print results, save nothing")
    ap.add_argument("--clean-mock", action="store_true", help="back up DB and delete demo rows first")
    ap.add_argument("--db", default=DB_PATH)
    args = ap.parse_args()

    if args.clean_mock and not args.dry_run:
        clean_mock(args.db)

    shops = [s.strip() for s in args.only.split(",") if s.strip()]
    results, report = {}, []
    for shop in shops:
        print(f"\n=== {shop.upper()} ===")
        log = lambda m, s=shop: print(f"[{s}] {m}", flush=True)
        try:
            if shop == "jumia":
                results[shop] = fetch_jumia(args.limit, args.jumia_region, log)
            elif shop == "kibuga":
                results[shop] = fetch_kibuga(args.limit, args.kibuga_pages, log)
            elif shop == "ebay":
                results[shop] = fetch_ebay(args.limit, log)
            else:
                report.append((shop, 0, "unknown shop"))
                continue
            report.append((shop, len(results[shop]), "ok" if results[shop] else "0 found (see messages above)"))
        except Exception as exc:
            report.append((shop, 0, f"skipped: {exc}"))
            print(f"[{shop}] skipped: {exc}")

    for shop, why in (("amazon", "no public API without Associates sales"),
                      ("alibaba", "no keyless API; 1688 adapter needs ALI1688_KEY")):
        report.append((shop, 0, f"skipped: {why}"))

    saved = {}
    if not args.dry_run:
        from core.db import init_db, save_items      # your project's DB layer (converts to USD)
        init_db()
        today = datetime.date.today().isoformat()
        for shop, items in results.items():
            saved[shop] = save_items(items, today) if items else 0

    print("\n" + "=" * 70)
    print(f"{'SHOP':<9} {'FETCHED':>8} {'NEW IN DB':>10}  STATUS")
    for shop, n, status in report:
        new = saved.get(shop, "-" if args.dry_run or shop not in results else 0)
        print(f"{shop.upper():<9} {n:>8} {str(new):>10}  {status}")
    print("=" * 70)
    if args.dry_run:
        for shop, items in results.items():
            for it in items[:5]:
                print(f"  {shop:<7} {it['price']:>12,.0f} {it['currency']}  {it['title'][:55]}\n          {it['url']}")
    else:
        print('Now run:  python compare_item.py "iphone 14"')


if __name__ == "__main__":
    main()

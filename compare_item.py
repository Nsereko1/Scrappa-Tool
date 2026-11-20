#!/usr/bin/env python3
"""
compare_item.py - find one product across every platform in bestseller.db.

  python compare_item.py "iphone 14"                 # real data from bestseller.db
  python compare_item.py "iphone 14" --active-only   # hide rows marked 'deleted'
  python compare_item.py "iphone 14" --similar 30 --save
  python compare_item.py "iphone 14" --demo          # built-in sample data (proof run)
"""
import argparse
import datetime
import os
import re
import shutil
import sqlite3
import sys

DB_PATH = "bestseller.db"
DEFAULT_PLATFORMS = ["jumia", "amazon", "alibaba", "ebay", "kibuga"]

NOISE = {
    "new", "used", "brand", "original", "authentic", "genuine", "unlocked", "global",
    "version", "smartphone", "phone", "mobile", "android", "ios", "dual", "sim",
    "ram", "rom", "gb", "tb", "inch", "wifi", "black", "white", "blue", "red",
    "green", "gold", "silver", "gray", "grey", "pink", "purple", "free", "shipping",
    "with", "and", "for", "the", "in", "on", "of", "to", "by", "wholesale",
}
VARIANT_WORDS = {"pro", "max", "plus", "mini", "ultra", "lite", "se", "fe", "air", "flip", "fold"}
ACCESSORY_WORDS = {"case", "cover", "protector", "charger", "cable", "adapter", "pouch",
                   "holder", "strap", "skin", "sticker", "tempered", "glass", "stand"}
SPEC_RE = re.compile(r"^\d+(g|mah|mp|mm|cm|hz|w|v|in|inch)$")


def tokens(text):
    t = (text or "").lower()
    t = re.sub(r"(\d+)\s*(gb|tb)\b", r"\1\2", t)
    t = re.sub(r"\b(iphone|ipad|galaxy|pixel|redmi|poco|reno)(\d)", r"\1 \2", t)
    t = re.sub(r"(?<=\d)(?=(pro|max|plus|mini|ultra)\b)", " ", t)
    words = re.findall(r"[a-z0-9]+", t)
    return [w for w in words if w not in NOISE and not SPEC_RE.match(w)]


def usd(v):
    return f"${v:,.2f}"


def trunc(s, n):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def local_price(r):
    if r.get("price_local") and r.get("currency") and r["currency"] != "USD":
        return f"{r['price_local']:,.0f} {r['currency']}"
    return ""


def stock_label(r):
    return "OUT" if "out" in (r.get("stock_status") or "").lower() else "In stock"


def dedupe(rows):
    seen, out = set(), []
    for r in rows:
        key = (r["platform"], r["url"]) if r.get("url") else (r["platform"], r["title"], round(r["price_usd"], 2))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def demo_db():
    con = sqlite3.connect(":memory:")
    con.execute("""CREATE TABLE bestsellers (platform TEXT, region TEXT, sku TEXT, title TEXT,
                   price_usd REAL, price_local REAL, currency TEXT, url TEXT,
                   stock_status TEXT, status TEXT)""")
    rows = [
        ("jumia",   "NG", "J1", "Apple iPhone 14 128GB Midnight - Brand New", 612.00, 918000, "NGN", "https://example.com/jumia/iphone-14-128gb", "In Stock", "active"),
        ("jumia",   "UG", "J2", "Apple iPhone 14 256GB Blue", 705.00, 2679000, "UGX", "https://example.com/jumia-ug/iphone-14-256gb", "In Stock", "active"),
        ("jumia",   "NG", "J3", "Apple iPhone 14 128GB Purple", 640.00, 960000, "NGN", "https://example.com/jumia/iphone-14-purple", "Out of Stock", "active"),
        ("kibuga",  "UG", "K1", "Apple iPhone 14 128GB Starlight", 658.00, 2500400, "UGX", "https://example.com/kibuga/iphone-14-128gb", "In Stock", "active"),
        ("ebay",    "US", "E1", "Apple iPhone 14 128GB Unlocked Smartphone - Excellent Refurbished", 489.99, 489.99, "USD", "https://example.com/ebay/iphone-14-refurb", "In Stock", "active"),
        ("amazon",  "US", "A1", "Apple iPhone 14 (128 GB) - Blue", 599.00, 599.00, "USD", "https://example.com/amazon/iphone-14-blue", "In Stock", "active"),
        ("alibaba", "GLOBAL", "L1", "Wholesale Apple iPhone14 Original Unlocked 128GB", 455.00, 455.00, "USD", "https://example.com/alibaba/iphone-14", "In Stock", "active"),
        ("ebay",    "US", "E2", "Apple iPhone 14 Pro Max 256GB Deep Purple", 849.00, 849.00, "USD", "https://example.com/ebay/iphone-14-pro-max", "In Stock", "active"),
        ("amazon",  "US", "A2", "Apple iPhone 14 Plus 128GB", 679.00, 679.00, "USD", "https://example.com/amazon/iphone-14-plus", "In Stock", "active"),
        ("jumia",   "NG", "J4", "Apple iPhone 13 128GB Pink", 480.00, 720000, "NGN", "https://example.com/jumia/iphone-13", "In Stock", "active"),
        ("kibuga",  "UG", "K2", "Apple iPhone 13 Pro 256GB Graphite", 760.00, 2888000, "UGX", "https://example.com/kibuga/iphone-13-pro", "In Stock", "active"),
        ("alibaba", "GLOBAL", "L2", "Apple iPhone 12 64GB Refurbished", 310.00, 310.00, "USD", "https://example.com/alibaba/iphone-12", "In Stock", "active"),
        ("ebay",    "US", "E3", "iPhone 14 Silicone Case Cover", 9.99, 9.99, "USD", "https://example.com/ebay/case", "In Stock", "active"),
        ("jumia",   "NG", "J5", "Samsung Galaxy A14 128GB 4GB RAM", 190.00, 285000, "NGN", "https://example.com/jumia/a14", "In Stock", "active"),
    ]
    con.executemany("INSERT INTO bestsellers VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    return con


def load_rows(con, q_tokens, family, active_only):
    sql = ("SELECT platform, region, sku, title, price_usd, price_local, currency, url, "
           "stock_status, status FROM bestsellers WHERE price_usd IS NOT NULL AND price_usd > 0")
    params = []
    if active_only:
        sql += " AND status = 'active'"
    if family:
        sql += " AND lower(title) LIKE ?"
        params.append(f"%{family[0]}%")
    cur = con.execute(sql, params)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def classify(rows, q_tokens, family):
    qset = set(q_tokens)
    accessories_wanted = bool(qset & ACCESSORY_WORDS)
    exact, similar = [], []
    for r in rows:
        ts = set(tokens(r["title"]))
        if not accessories_wanted and ts & ACCESSORY_WORDS:
            continue
        if qset <= ts and (ts & VARIANT_WORDS) <= qset:
            exact.append(r)
            continue
        if family and not set(family) <= ts:
            continue
        score = len(ts & qset) / len(ts | qset) if ts | qset else 0
        if score >= 0.2:
            similar.append((score, r))
    exact.sort(key=lambda r: r["price_usd"])
    similar.sort(key=lambda x: (-x[0], x[1]["price_usd"]))
    return exact, similar


def render(query, exact, similar, all_platforms, source, similar_limit):
    W = max(100, min(shutil.get_terminal_size((120, 20)).columns, 150))
    out = []
    p = out.append
    bar = "=" * W

    p(bar)
    p(f'PRODUCT SEARCH: "{query}"')
    p(f"Source: {source}   |   {datetime.datetime.now():%Y-%m-%d %H:%M}")
    p(bar)

    p("")
    p(f"1) ALL PRICES, CHEAPEST FIRST  ({len(exact)} listing(s))")
    p("-" * W)
    if not exact:
        p("   No exact match found on any platform.")
    else:
        tw = W - 64
        p(f"{'#':>3}  {'PLATFORM':<9} {'REG':<6} {'USD':>11}  {'LOCAL PRICE':<18} {'STOCK':<9} TITLE")
        for i, r in enumerate(exact, 1):
            title = ("★ " if i == 1 else "") + r["title"]
            p(f"{i:>3}  {r['platform'].upper():<9} {(r.get('region') or '')[:6]:<6} "
              f"{usd(r['price_usd']):>11}  {local_price(r):<18} {stock_label(r):<9} {trunc(title, tw)}")
            if r.get("url"):
                p(f"       ↳ {r['url']}")
        lo, hi = exact[0], exact[-1]
        if len(exact) > 1 and hi["price_usd"] > lo["price_usd"]:
            diff = hi["price_usd"] - lo["price_usd"]
            p("")
            p(f"   Cheapest: {usd(lo['price_usd'])} on {lo['platform'].upper()}   |   "
              f"Most expensive: {usd(hi['price_usd'])} on {hi['platform'].upper()}   |   "
              f"Spread: {usd(diff)} ({diff / hi['price_usd'] * 100:.0f}% cheaper at the low end)")

    p("")
    p("2) PRICE BY PLATFORM")
    p("-" * W)
    best = exact[0]["price_usd"] if exact else None
    for plat in all_platforms:
        mine = [r for r in exact if r["platform"] == plat]
        if not mine:
            p(f"   {plat.upper():<9}  —  no listing found")
            continue
        lowest = min(r["price_usd"] for r in mine)
        avg = sum(r["price_usd"] for r in mine) / len(mine)
        flag = "   ◀ best price" if lowest == best else ""
        p(f"   {plat.upper():<9} {len(mine):>3} listing(s)   cheapest {usd(lowest):>10}   avg {usd(avg):>10}{flag}")

    p("")
    p("3) PROOF CHECKS")
    p("-" * W)
    prices = [r["price_usd"] for r in exact]
    sorted_ok = prices == sorted(prices)
    found_on = sorted({r["platform"] for r in exact})
    missing = [x for x in all_platforms if x not in found_on]
    p(f"   {'✔' if sorted_ok else '✘'} {len(exact)} listing(s) ordered cheapest-first"
      f"{' (verified: each price >= the one above)' if sorted_ok else ' (ORDER BROKEN)'}")
    p(f"   {'✔' if found_on else '✘'} found on {len(found_on)} of {len(all_platforms)} platforms: "
      f"{', '.join(x.upper() for x in found_on) or 'none'}")
    if missing:
        p(f"   – not found on: {', '.join(x.upper() for x in missing)}")

    p("")
    p(f"4) SIMILAR ITEMS ACROSS ALL BRANDS  (top {min(similar_limit, len(similar))} of {len(similar)}, best match first)")
    p("-" * W)
    if not similar:
        p("   No similar items found.")
    else:
        counts = {}
        for _, r in similar:
            counts[r["platform"]] = counts.get(r["platform"], 0) + 1
        p("   Similar items per platform: " +
          "   ".join(f"{k.upper()} {v}" for k, v in sorted(counts.items())))
        p("")
        tw = W - 38
        p(f"{'#':>3}  {'PLATFORM':<9} {'MATCH':>5}  {'USD':>11}  TITLE")
        for i, (score, r) in enumerate(similar[:similar_limit], 1):
            p(f"{i:>3}  {r['platform'].upper():<9} {score * 100:>4.0f}%  {usd(r['price_usd']):>11}  {trunc(r['title'], tw)}")
    p("")
    p(bar)
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Compare one product across every platform.")
    ap.add_argument("query", help='product to search, e.g. "iphone 14"')
    ap.add_argument("--db", default=DB_PATH, help="path to the SQLite database")
    ap.add_argument("--similar", type=int, default=20, help="how many similar items to list")
    ap.add_argument("--active-only", action="store_true", help="ignore rows marked 'deleted'")
    ap.add_argument("--demo", action="store_true", help="use built-in sample data")
    ap.add_argument("--save", action="store_true", help="also write the report to a .txt file")
    args = ap.parse_args()

    q_tokens = tokens(args.query)
    if not q_tokens:
        sys.exit("Query has no searchable words.")
    family = [t for t in q_tokens if not t.isdigit() and t not in VARIANT_WORDS]

    if args.demo:
        con, source = demo_db(), "DEMO DATA (built-in sample, not from your database)"
    else:
        if not os.path.exists(args.db):
            sys.exit(f"Database not found: {args.db}  (run this from the project folder)")
        con, source = sqlite3.connect(args.db, timeout=30), args.db

    rows = dedupe(load_rows(con, q_tokens, family, args.active_only))
    plats = [r[0] for r in con.execute("SELECT DISTINCT platform FROM bestsellers") if r[0]]
    all_platforms = sorted(set(plats) | set(DEFAULT_PLATFORMS))
    con.close()

    exact, similar = classify(rows, q_tokens, family)
    report = render(args.query, exact, similar, all_platforms, source, args.similar)
    print(report)

    if args.save:
        slug = re.sub(r"[^a-z0-9]+", "_", args.query.lower()).strip("_")
        name = f"compare_{slug}_{datetime.date.today().isoformat()}.txt"
        with open(name, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")
        print(f"Saved to {name}")


if __name__ == "__main__":
    main()

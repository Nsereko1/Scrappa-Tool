# scrape_similar_products.py — minimal version for testing
"""Cross-platform similar-product clustering. Importable + runnable."""

import argparse
import datetime
import difflib
import json
import re
import sqlite3
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

print("[boot] scrape_similar_products.py loaded", flush=True)

# ---- currency ------------------------------------------------------------
_FALLBACK_RATES = {
    "USD": 1.0, "NGN": 1500.0, "CNY": 7.2,
    "UGX": 3800.0, "KES": 150.0, "GBP": 0.8, "EUR": 0.9,
}
try:
    from core.db import RATES as _DB_RATES
    RATES = {**_FALLBACK_RATES, **_DB_RATES}
except Exception:
    RATES = _FALLBACK_RATES


def to_usd(price, currency) -> Optional[float]:
    if price is None:
        return None
    rate = RATES.get((currency or "USD").upper(), 1.0)
    return round(float(price) / rate, 2) if rate else None


# ---- tokenization --------------------------------------------------------
NOISE = {
    "new", "used", "pro", "max", "plus", "gb", "tb", "inch", "smartphone",
    "phone", "ram", "rom", "dual", "sim", "black", "white", "blue", "red",
    "green", "gold", "silver", "gray", "grey", "4g", "5g", "3g", "wifi",
    "android", "ios", "unlocked", "original", "authentic", "genuine",
    "heavy", "duty", "free", "shipping", "with", "and", "for", "the", "a",
    "in", "on", "of", "to", "led", "light", "outages", "pack", "pcs",
    "piece", "set", "capacity", "high", "portable", "charger", "cable",
    "wireless", "fast", "super",
}


def _tokens(title: str) -> List[str]:
    if not title:
        return []
    t = re.sub(r"[^a-z0-9\s]", " ", title.lower())
    return [w for w in t.split() if w not in NOISE and len(w) > 1]


def _signature(title: str) -> str:
    return " ".join(_tokens(title)[:2])


def similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    sa, sb = set(ta), set(tb)
    j = len(sa & sb) / len(sa | sb)
    s = difflib.SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    return round(0.55 * j + 0.45 * s, 4)


# ---- clustering ----------------------------------------------------------
def cluster_products(items: List[Dict], threshold: float,
                     min_platforms: int = 2) -> List[List[Dict]]:
    buckets: Dict[str, List[Dict]] = {}
    for it in items:
        buckets.setdefault(_signature(it["title"]) or "_", []).append(it)

    out: List[List[Dict]] = []
    for _, bucket in buckets.items():
        if len(bucket) < 2:
            continue
        n = len(bucket)
        edges: List[List[int]] = [[] for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                if bucket[i]["platform"] == bucket[j]["platform"]:
                    continue
                if similarity(bucket[i]["title"], bucket[j]["title"]) >= threshold:
                    edges[i].append(j)
                    edges[j].append(i)

        seen = [False] * n
        for i in range(n):
            if seen[i] or not edges[i]:
                continue
            comp, stack = [], [i]
            seen[i] = True
            while stack:
                k = stack.pop()
                comp.append(bucket[k])
                for m in edges[k]:
                    if not seen[m]:
                        seen[m] = True
                        stack.append(m)
            if len({x["platform"] for x in comp}) >= min_platforms:
                out.append(comp)

    def _cheapest(c):
        usd = [to_usd(x["price"], x.get("currency")) for x in c
               if to_usd(x["price"], x.get("currency")) is not None]
        return min(usd) if usd else 1e12

    out.sort(key=lambda c: (-len({x["platform"] for x in c}), _cheapest(c)))
    return out


# ---- fetch (import-safe) -------------------------------------------------
PLATFORMS = ["jumia", "kibuga", "amazon", "alibaba", "ebay"]

# adapters imported lazily inside fetch_platform so `import` never touches network
def fetch_platform(platform, limit, region, query, dry_run):
    if dry_run:
        base = query or "generic product"
        return [{
            "platform": platform, "region": region,
            "sku": f"{platform.upper()}-DRY-{i}",
            "title": f"{base} variant {i}",
            "price": 100.0 + i, "currency": "USD",
            "stock_status": "In Stock",
            "url": f"https://example.com/{platform}/{i}",
        } for i in range(limit)]

    try:
        if platform == "jumia":
            from adapters.jumia import scrape_jumia
            out = scrape_jumia(limit=limit, start_page=1,
                               category="phones", region=region)
            return (out[0] if isinstance(out, tuple) and out else []) or []
        if platform == "kibuga":
            from adapters.kibuga import scrape_kibuga
            out = scrape_kibuga(limit=limit, start_page=1, region=region)
            return (out[0] if isinstance(out, tuple) and out else []) or []
        if platform == "amazon":
            from adapters.mock_adapters import scrape_amazon_mock
            return scrape_amazon_mock(limit=limit, region=region) or []
        if platform == "alibaba":
            try:
                from adapters.alibaba1688 import scrape_alibaba
                return scrape_alibaba(limit=limit) or []
            except Exception:
                from adapters.mock_adapters import scrape_alibaba_mock
                return scrape_alibaba_mock(limit=limit, region="GLOBAL") or []
        if platform == "ebay":
            try:
                from adapters.ebay import scrape_ebay
                return scrape_ebay(limit=limit, query=query or "smartphone") or []
            except Exception:
                from adapters.mock_adapters import scrape_ebay_mock
                return scrape_ebay_mock(limit=limit, region=region) or []
    except Exception:
        print(f"  [{platform}] fetch error:", flush=True)
        traceback.print_exc()
    return []


# ---- persistence ---------------------------------------------------------
def save_and_report(clusters, date_str, dry_run):
    flat = [it for c in clusters for it in c]
    if not flat:
        print("No cross-platform clusters to save.", flush=True)
        return

    seen, deduped = set(), []
    for it in flat:
        key = (it["platform"], it["sku"], it.get("region", "GLOBAL"))
        if key not in seen:
            seen.add(key)
            deduped.append(it)

    if dry_run:
        print(f"\n[dry-run] would save {len(deduped)} items", flush=True)
    else:
        try:
            from core.db import init_db, save_items, DB_PATH
            init_db()
            new_count = save_items(deduped, date_str)
            print(f"\nSaved {len(deduped)} items ({new_count} new) to {DB_PATH}",
                  flush=True)
        except Exception:
            print(f"\n[save skipped] {len(deduped)} items (dry run only)", flush=True)

    print("\n" + "=" * 78, flush=True)
    print(f"CROSS-BRAND MATCHES ({len(clusters)} clusters)", flush=True)
    print("=" * 78, flush=True)

    for i, cluster in enumerate(clusters[:25], 1):
        plats = sorted({x["platform"].upper() for x in cluster})
        best: Dict[str, Tuple[float, Dict]] = {}
        for it in cluster:
            usd = to_usd(it["price"], it.get("currency"))
            if usd is None:
                continue
            p = it["platform"]
            if p not in best or usd < best[p][0]:
                best[p] = (usd, it)
        all_usd = [v[0] for v in best.values()]
        rng = f"${min(all_usd):,.2f}–${max(all_usd):,.2f}" if all_usd else "N/A"
        print(f"\n[{i}] {cluster[0]['title'][:58]}...", flush=True)
        print(f"    Platforms: {', '.join(plats)}  |  "
              f"Cheapest-per-platform: {rng}", flush=True)
        for plat in sorted(best):
            usd, it = best[plat]
            print(f"      {plat:8s} USD ${usd:>10,.2f}  "
                  f"({it.get('currency','?'):4s} {it['price']:>13,.2f})  "
                  f"{it['url'][:52]}", flush=True)


# ---- main ----------------------------------------------------------------
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--query")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--region", default="NG")
    p.add_argument("--threshold", type=float, default=0.35)
    p.add_argument("--platforms", nargs="+", default=PLATFORMS, choices=PLATFORMS)
    p.add_argument("--min-platforms", type=int, default=2)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--from-file", help="Load items from JSON instead of scraping")
    args = p.parse_args()

    if args.from_file:
        with open(args.from_file, encoding="utf-8") as f:
            all_items = json.load(f)
        print(f"Loaded {len(all_items)} items from {args.from_file}", flush=True)
    else:
        print(f"\nScraping {args.limit}/platform from "
              f"{', '.join(args.platforms)}"
              f"{' (dry)' if args.dry_run else ''}", flush=True)
        print("-" * 78, flush=True)
        all_items = []
        started = time.time()
        with ThreadPoolExecutor(max_workers=len(args.platforms)) as pool:
            futs = {pool.submit(fetch_platform, plat, args.limit, args.region,
                                args.query, args.dry_run): plat
                    for plat in args.platforms}
            for f in as_completed(futs):
                plat = futs[f]
                try:
                    got = f.result()
                    print(f"  [{plat:8s}] {len(got):>4d}", flush=True)
                    all_items.extend(got)
                except Exception:
                    print(f"  [{plat:8s}] FAILED", flush=True)
                    traceback.print_exc()
        print(f"\nFetched {len(all_items)} items in "
              f"{time.time()-started:.1f}s", flush=True)

    if not all_items:
        return

    if args.query:
        qt = set(_tokens(args.query))
        if qt:
            before = len(all_items)
            all_items = [it for it in all_items
                         if qt & set(_tokens(it["title"]))]
            print(f"Query filter: {before} -> {len(all_items)} (tokens {qt})",
                  flush=True)

    clusters = cluster_products(all_items, args.threshold, args.min_platforms)
    print(f"Found {len(clusters)} cross-brand clusters "
          f"(threshold={args.threshold}, min_platforms={args.min_platforms})",
          flush=True)
    save_and_report(clusters, datetime.date.today().isoformat(), args.dry_run)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\n[FATAL]:", flush=True)
        traceback.print_exc()
        sys.exit(1)

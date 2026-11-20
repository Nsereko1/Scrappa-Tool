import datetime
import sqlite3
import threading
import time
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Tuple, Any
from core.db import (DB_PATH, init_db, save_items, mark_deleted_items, log_tracker_run)
from adapters.jumia import scrape_jumia
from adapters.mock_adapters import (scrape_amazon_mock, scrape_alibaba_mock, scrape_ebay_mock)
from adapters.kibuga import scrape_kibuga
from core.currency import get_rates, convert_usd_to

app = FastAPI()
init_db()

SCRAPERS = {"jumia": scrape_jumia, "amazon": scrape_amazon_mock, "alibaba": scrape_alibaba_mock, "ebay": scrape_ebay_mock, "kibuga": scrape_kibuga}
scan_status = {"is_running": False, "platform": "", "current_page": 1, "total_scraped": 0, "total_saved": 0, "target": 0, "message": "Idle"}
agent_state = {"status": "Idle", "last_run": None, "next_run": None}
force_scan_trigger = threading.Event()
scan_lock = threading.Lock()

PRODUCT_NOISE = {
    "new", "used", "refurbished", "renewed", "secondhand", "original", "genuine", "authentic", "unlocked",
    "black", "white", "blue", "red", "green", "gold", "silver", "gray", "grey", "purple", "pink", "yellow", "orange", "midnight", "starlight",
    "gb", "tb", "mb", "ram", "rom", "storage", "memory", "dual", "sim", "single", "nano",
    "inch", "inches", "display", "screen", "smartphone", "phone", "mobile", "device", "handset",
    "wifi", "wireless", "bluetooth", "android", "ios", "4g", "5g", "3g", "lte",
    "with", "and", "for", "the", "a", "an", "in", "on", "of", "to", "by", "from",
    "free", "shipping", "delivery", "sale", "offer", "brand", "model", "product", "official",
    "pack", "pcs", "piece", "pieces", "set", "capacity", "portable", "fast", "super", "high", "quality",
    "apple", "samsung", "sony", "xiaomi", "huawei", "oppo", "vivo", "tecno", "infinix", "itel", "nokia", "google", "pixel",
    "oneplus", "realme", "motorola", "lenovo", "asus", "acer", "hp", "dell", "microsoft", "amazon", "nike", "adidas", "puma",
    "reebok", "canon", "nikon", "jbl", "bose", "beats", "anker", "oraimo", "baseus", "ugreen", "tcl", "hisense", "lg", "philips",
}

MODEL_VARIANTS = {"pro", "max", "plus", "ultra", "mini", "fe", "lite", "air", "se", "fold", "flip", "note", "edge", "neo", "prime"}

def product_model_tokens(title):
    if not title: return set()
    text = str(title).lower()
    text = re.sub(r"\b\d+\s*(gb|tb|mb)\b", " ", text)
    text = re.sub(r"\b\d+\s*(gb|tb|mb)?\s*ram\b", " ", text)
    text = re.sub(r"\b\d+(\.\d+)?\s*(inch|inches|in)\b", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return {word for word in text.split() if word not in PRODUCT_NOISE and len(word) > 1}

def is_same_product_model(selected_title, candidate_title):
    sel = product_model_tokens(selected_title)
    cand = product_model_tokens(candidate_title)
    if not sel or not cand: return False
    if sel.issubset(cand): return True
    if sel.intersection(cand) == sel: return True
    return False

def safe_price(value):
    try:
        if value is None: return None
        price = float(value)
        if price <= 0: return None
        return price
    except (ValueError, TypeError): return None

def background_agent():
    global agent_state
    while True:
        triggered = force_scan_trigger.wait(timeout=600)
        if triggered: force_scan_trigger.clear()
        agent_state["status"] = "Scanning..."
        agent_state["next_run"] = None
        try:
            live_items, _ = scrape_jumia(limit=100, start_page=1, category="phones", region="NG")
            if live_items:
                con = sqlite3.connect(DB_PATH)
                rows = con.execute("SELECT sku FROM bestsellers WHERE platform = 'jumia' AND region = 'NG'").fetchall()
                existing = {r[0] for r in rows}
                con.close()
                missing = [item for item in live_items if item["sku"] not in existing]
                if missing:
                    new_count = save_items(missing, datetime.date.today().isoformat())
                    log_tracker_run("jumia", new_count, len(live_items))
        except Exception as e:
            print(f"Background agent error: {e}")
        agent_state["status"] = "Sleeping"
        agent_state["last_run"] = datetime.datetime.now().isoformat()
        agent_state["next_run"] = (datetime.datetime.now() + datetime.timedelta(minutes=10)).isoformat()

threading.Thread(target=background_agent, daemon=True).start()

@app.get("/agent_status")
def get_agent_status(): return agent_state

@app.post("/force_scan")
def trigger_force_scan():
    force_scan_trigger.set()
    return {"status": "triggered"}

@app.get("/tracker_history")
def get_tracker_history():
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM tracker_log ORDER BY id DESC LIMIT 50").fetchall()
    con.close(); return [dict(r) for r in rows]

@app.get("/tracker_details")
def get_tracker_details(platform: str = None, timestamp: str = None):
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row
    if timestamp:
        query = "SELECT title, price_usd, last_seen FROM bestsellers WHERE last_seen LIKE ?"; params = [f"{timestamp}%"]
    elif platform:
        query = "SELECT title, price_usd, last_seen FROM bestsellers WHERE platform = ? AND is_new = 1 ORDER BY id DESC LIMIT 100"; params = [platform.lower()]
    else:
        con.close(); return []
    rows = con.execute(query, params).fetchall()
    con.close(); return [dict(r) for r in rows]

@app.get("/price_history")
def get_price_history(sku: str):
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row
    rows = con.execute("SELECT price_usd, timestamp FROM price_history WHERE sku = ? ORDER BY id ASC", (sku,)).fetchall()
    con.close(); return [dict(r) for r in rows]

@app.get("/compare/specific")
def get_specific_comparison(title: str):
    selected_tokens = product_model_tokens(title)
    if not selected_tokens:
        return {"selected": {"title": title}, "exact_matches": [], "alternatives": [], "summary": {"count": 0, "lowest": None, "highest": None, "average": None, "cheapest_platform": None, "cheapest_region": None, "cheapest_url": None, "cheapest_price_usd": None, "cheapest_sku": None, "my_price": None, "avg_price": None, "position": 0, "total_sellers": 0, "avg_status": "Unknown"}}

    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row
    where_parts = ["LOWER(title) LIKE ?" for _ in selected_tokens]
    where_clause = " AND ".join(where_parts)
    params = [f"%{token}%" for token in selected_tokens]
    query = f"SELECT title, platform, region, price_usd, url, sku, previous_price_usd, stock_status FROM bestsellers WHERE price_usd IS NOT NULL AND ({where_clause}) ORDER BY id DESC LIMIT 3000"
    candidates = con.execute(query, params).fetchall()
    con.close()

    results = []
    seen = set()
    for row in candidates:
        candidate_title = row["title"] or ""
        if not is_same_product_model(title, candidate_title): continue
        price = safe_price(row["price_usd"])
        if price is None: continue
        platform = row["platform"] or ""
        region = row["region"] or ""
        url = row["url"] or ""
        sku = row["sku"] or ""
        if url: identity = url.strip().lower()
        elif sku: identity = (platform.lower(), region.upper(), sku.lower())
        else: identity = (platform.lower(), region.upper(), candidate_title.lower(), price)
        if identity in seen: continue
        seen.add(identity)
        results.append({"title": candidate_title, "platform": platform, "region": region, "price_usd": price, "previous_price_usd": safe_price(row["previous_price_usd"]), "url": url, "sku": sku, "stock_status": row["stock_status"], "image_url": None})

    results.sort(key=lambda item: item["price_usd"])

    # FALLBACK: If strict matching found only 1 item, use the relaxed core-token matching
    if len(results) <= 1:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        
        tokens = product_model_tokens(title)
        core = frozenset(t for t in tokens if t.isdigit() or t in ("iphone", "galaxy", "macbook", "playstation", "tv", "fridge", "xiaomi", "redmi", "note", "samsung", "a14"))
        
        if core:
            where = " AND ".join(["LOWER(title) LIKE ?" for _ in core])
            params = [f"%{w}%" for w in core]
            
            fallback_rows = con.execute(f"SELECT * FROM bestsellers WHERE {where} AND price_usd IS NOT NULL LIMIT 100", params).fetchall()
            seen_urls = {r["url"] for r in results}
            
            for r in fallback_rows:
                if r["url"] in seen_urls: continue
                price = safe_price(r["price_usd"])
                if price is None: continue
                    
                results.append({
                    "title": r["title"],
                    "platform": r["platform"],
                    "region": r["region"],
                    "price_usd": price,
                    "previous_price_usd": safe_price(r["previous_price_usd"]),
                    "url": r["url"],
                    "sku": r["sku"],
                    "stock_status": r["stock_status"],
                    "compare_status": "Similar Match",
                    "image_url": None
                })
        con.close()
        results.sort(key=lambda x: x["price_usd"])

    per_platform_results = sorted(results, key=lambda x: x["price_usd"])
    prices = [item["price_usd"] for item in per_platform_results]
    count = len(prices)
    lowest = min(prices) if prices else None
    highest = max(prices) if prices else None
    average = (sum(prices) / count) if count else None

    for item in per_platform_results:
        if lowest is not None and item["price_usd"] == lowest: item["compare_status"] = "Lowest Price"
        elif average is not None and item["price_usd"] < average: item["compare_status"] = "Below Average"
        elif average is not None and item["price_usd"] > average: item["compare_status"] = "Above Average"
        else: item["compare_status"] = "Average"

    cheapest = per_platform_results[0] if per_platform_results else None
    if cheapest:
        position = 1
        if average is not None:
            if cheapest["price_usd"] < average * 0.98: avg_status = "Lower Than Average"
            elif cheapest["price_usd"] > average * 1.02: avg_status = "Higher Than Average"
            else: avg_status = "Average"
        else: avg_status = "Unknown"
    else:
        position = 0; avg_status = "Unknown"

    return {
        "selected": {"title": title}, "exact_matches": per_platform_results, "all_listings": results, "alternatives": [],
        "summary": {"count": count, "lowest": round(lowest, 2) if lowest is not None else None, "highest": round(highest, 2) if highest is not None else None, "average": round(average, 2) if average is not None else None, "cheapest_platform": cheapest["platform"] if cheapest else None, "cheapest_region": cheapest["region"] if cheapest else None, "cheapest_url": cheapest["url"] if cheapest else None, "cheapest_price_usd": cheapest["price_usd"] if cheapest else None, "cheapest_sku": cheapest["sku"] if cheapest else None, "my_price": round(lowest, 2) if lowest is not None else None, "avg_price": round(average, 2) if average is not None else None, "position": position, "total_sellers": count, "avg_status": avg_status}
    }

@app.get("/platform_insights")
def get_platform_insights(platform: str = "all"):
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row
    if platform.lower() == "all":
        total = con.execute("SELECT COUNT(*) FROM bestsellers").fetchone()[0]
        con.close(); return {"total": total, "overlaps": {}, "missing": 0}
    plat = platform.lower()
    total = con.execute("SELECT COUNT(*) FROM bestsellers WHERE platform = ?", (plat,)).fetchone()[0]
    overlaps = {}
    for other in ["jumia", "amazon", "alibaba", "ebay", "kibuga"]:
        if other == plat: continue
        overlaps[other] = con.execute("SELECT COUNT(DISTINCT a.title) FROM bestsellers a WHERE a.platform = ? AND EXISTS (SELECT 1 FROM bestsellers b WHERE b.platform = ? AND b.title = a.title)", (plat, other)).fetchone()[0]
    con.close(); return {"total": total, "overlaps": overlaps, "missing": 0}

@app.post("/start_auto_scan")
def start_auto_scan(platform: str = "jumia", target_limit: int = 10000, category: str = "phones", region: str = "NG", query: str = None):
    global scan_status
    if scan_status["is_running"]: return {"status": "error", "message": "Scan already running"}
    from core.scrape_query import effective_query, category_keywords
    eq = effective_query(category, query)
    keywords = category_keywords(category)
    scan_status = {"is_running": True, "platform": platform, "current_page": 1, "total_scraped": 0, "total_saved": 0, "target": target_limit, "message": f"Starting ({category}: {eq or 'all'})...", "query": query, "effective_query": eq, "category": category, "category_keywords": keywords}
    threading.Thread(target=_background_scan, args=(platform, target_limit, category, region, query), daemon=True).start()
    return {"status": "started", "query": query, "effective_query": eq, "category": category, "keywords": keywords}

@app.get("/scan_status")
def get_scan_status(): return scan_status

def scrape_single_platform(p, limit, category, region, query=None, keywords=None):
    batch_size = 500; items_to_fetch = limit; keywords = keywords or []
    while items_to_fetch > 0:
        current_batch = min(batch_size, items_to_fetch)
        try:
            if p == "jumia": items, _ = scrape_jumia(limit=current_batch, start_page=1, category=category, region=region, query=query)
            elif p == "kibuga": items, _ = scrape_kibuga(limit=current_batch, start_page=1, region=region, query=query)
            elif p == "amazon": items = scrape_amazon_mock(current_batch, region=region, query=query)
            elif p == "alibaba": items = scrape_alibaba_mock(current_batch, region="GLOBAL", query=query)
            elif p == "ebay": items = scrape_ebay_mock(current_batch, region=region, query=query)
            else: items = []
            if items and keywords:
                before = len(items)
                items = [it for it in items if any(kw.lower() in (it.get("title") or "").lower() for kw in keywords)]
                print(f"  [{p}] category filter: {before} -> {len(items)}", flush=True)
            if not items: break
            new_count = save_items(items, datetime.date.today().isoformat())
            with scan_lock:
                scan_status["total_scraped"] += len(items); scan_status["total_saved"] += new_count
            items_to_fetch -= len(items)
        except Exception as e:
            print(f"Error scraping {p}: {e}"); break
        time.sleep(0.05)
    mark_deleted_items(p, datetime.date.today().isoformat())

def _background_scan(platform, target_limit, category, region, query=None):
    from core.scrape_query import effective_query, category_keywords
    eq = effective_query(category, query); keywords = category_keywords(category)
    platforms_to_scrape = (["jumia", "amazon", "alibaba", "ebay", "kibuga"] if platform.lower() == "all" else [platform.lower()])
    limit_per_platform = (target_limit // len(platforms_to_scrape) if platform.lower() == "all" else target_limit)
    try:
        label = f" [{eq}]" if eq else ""
        if platform.lower() == "all":
            scan_status["message"] = f"Scraping all platforms{label}..."
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(scrape_single_platform, p, limit_per_platform, category, region, eq, keywords) for p in platforms_to_scrape]
                for future in futures: future.result()
        else:
            scan_status["platform"] = platforms_to_scrape[0]; scan_status["message"] = f"Scraping {platform.upper()}{label}..."
            scrape_single_platform(platforms_to_scrape[0], limit_per_platform, category, region, eq, keywords)
        scan_status["is_running"] = False; scan_status["message"] = "Done!"
    except Exception as e:
        scan_status["is_running"] = False; scan_status["message"] = f"Error: {str(e)}"

@app.get("/products")
def get_products(platform: str = "All", sort_by: str = "last", limit: int = 500, offset: int = 0, search: str = None, quick_filter: str = "all"):
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row
    where_parts = []; params = []
    if platform.lower() != "all":
        platforms = [p.strip().lower() for p in platform.split(",") if p.strip()]
        if platforms:
            where_parts.append(f"platform IN ({','.join(['?'] * len(platforms))})"); params.extend(platforms)
    if search: where_parts.append("title LIKE ?"); params.append(f"%{search}%")
    avg_subquery = "(SELECT AVG(price_usd) FROM bestsellers)"
    if quick_filter == "instock": where_parts.append("stock_status = 'In Stock'")
    elif quick_filter == "higher": where_parts.append(f"price_usd > {avg_subquery}")
    elif quick_filter == "lower": where_parts.append(f"price_usd < {avg_subquery}")
    elif quick_filter == "average": where_parts.append(f"price_usd BETWEEN {avg_subquery} * 0.9 AND {avg_subquery} * 1.1")
    if sort_by == "new": where_parts.append("is_new = 1")
    elif sort_by == "drops": where_parts.append("price_usd < previous_price_usd")
    where = ("WHERE " + " AND ".join(where_parts) if where_parts else "")
    order_col = "id DESC"
    if sort_by == "price": order_col = "price_usd DESC"
    elif sort_by == "drops": order_col = "(previous_price_usd - price_usd) DESC"
    if quick_filter == "highest": order_col = "price_usd DESC"
    elif quick_filter == "lowest": order_col = "price_usd ASC"
    if sort_by == "common":
        base_query = f"SELECT platform, title, COUNT(*) AS count, MAX(price_usd) AS price_usd, MAX(snapshot_date) AS date FROM bestsellers {where} GROUP BY title ORDER BY count DESC"
        count_query = f"SELECT COUNT(*) FROM (SELECT title FROM bestsellers {where} GROUP BY title)"
    else:
        base_query = f"SELECT *, snapshot_date AS date FROM bestsellers {where} ORDER BY {order_col}"
        count_query = f"SELECT COUNT(*) FROM bestsellers {where}"
    total = con.execute(count_query, params).fetchone()[0]
    rows = con.execute(f"{base_query} LIMIT ? OFFSET ?", params + [limit, offset]).fetchall()
    con.close(); return {"items": [dict(r) for r in rows], "total": total}

@app.get("/compare")
def get_compare(limit: int = 300):
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row
    rows = con.execute("SELECT title, platform, region, price_usd, url, sku, stock_status FROM bestsellers WHERE price_usd IS NOT NULL ORDER BY id DESC LIMIT 10000").fetchall()
    con.close()
    buckets = {}
    for r in rows:
        tokens = product_model_tokens(r["title"])
        if not tokens: continue
        core = frozenset(t for t in tokens if t.isdigit() or t in ("iphone", "galaxy", "macbook", "playstation", "tv", "fridge", "xiaomi", "redmi", "note", "samsung", "a14"))
        if not core: core = frozenset(tokens)
        buckets.setdefault(core, []).append(dict(r))
    groups = []
    for tokens, items in buckets.items():
        platforms = {it["platform"] for it in items}
        if len(platforms) < 2: continue
        best_per_platform = {}
        for it in items:
            p = it["platform"]
            if p not in best_per_platform or it["price_usd"] < best_per_platform[p]["price_usd"]: best_per_platform[p] = it
        prices = [v["price_usd"] for v in best_per_platform.values()]
        groups.append({"title": items[0]["title"], "platforms": ", ".join(sorted(p.upper() for p in platforms)), "lowest": round(min(prices), 2), "average": round(sum(prices) / len(prices), 2), "count": len(platforms)})
    groups.sort(key=lambda g: (-g["count"], g["lowest"]))
    return groups[:limit]

@app.get("/alerts")
def get_alerts():
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 50").fetchall()
    con.close(); return [dict(r) for r in rows]

@app.get("/trends/{sku}")
def get_sku_trends(sku: str, days: int = 30):
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row
    rows = con.execute("SELECT date, price_usd FROM daily_snapshots WHERE sku = ? AND date >= date('now', ?) ORDER BY date ASC", (sku, f"-{days} days")).fetchall()
    if not rows: rows = con.execute("SELECT substr(timestamp, 1, 10) AS date, price_usd FROM price_history WHERE sku = ? AND timestamp >= datetime('now', ?) ORDER BY timestamp ASC", (sku, f"-{days} days")).fetchall()
    con.close()
    prices = [float(r["price_usd"]) for r in rows if r["price_usd"] is not None]
    if len(prices) < 2: return {"sku": sku, "days": days, "points": len(prices), "direction": "insufficient_data", "pct_change": None, "volatility": None, "anomaly": False}
    first, last = prices[0], prices[-1]
    pct_change = round(((last - first) / first) * 100, 2) if first else 0
    direction = "up" if pct_change > 2 else "down" if pct_change < -2 else "flat"
    mean = statistics.mean(prices); volatility = round(statistics.pstdev(prices) / mean * 100, 2) if mean else 0
    anomaly = False; anomaly_score = 0.0
    if len(prices) > 5:
        earlier = prices[:-1]; m = statistics.mean(earlier); s = statistics.pstdev(earlier) or 0.0001
        z = (last - m) / s; anomaly_score = round(z, 2); anomaly = abs(z) >= 2.5
    return {"sku": sku, "days": days, "points": len(prices), "first_price": round(first, 2), "last_price": round(last, 2), "direction": direction, "pct_change": pct_change, "volatility": volatility, "anomaly": anomaly, "anomaly_score": anomaly_score}

@app.get("/trends")
def get_all_trends(days: int = 7):
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row
    rows = con.execute("SELECT date, platform, AVG(price_usd) AS avg_price, COUNT(*) AS n FROM daily_snapshots WHERE date >= date('now', ?) GROUP BY date, platform ORDER BY date ASC", (f"-{days} days",)).fetchall()
    con.close(); return [dict(r) for r in rows]

@app.get("/analytics")
def get_analytics():
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row
    platforms = con.execute("SELECT platform, COUNT(*) AS count FROM bestsellers GROUP BY platform").fetchall()
    avg_prices = con.execute("SELECT platform, AVG(price_usd) AS avg_price, 'USD' AS currency FROM bestsellers GROUP BY platform").fetchall()
    top_items = con.execute("SELECT title, COUNT(*) AS count FROM bestsellers GROUP BY title ORDER BY count DESC LIMIT 5").fetchall()
    con.close(); return {"platforms": [dict(r) for r in platforms], "top_items": [dict(r) for r in top_items], "avg_prices": [dict(r) for r in avg_prices]}

@app.get("/alerts/intelligence")
def get_intelligence_alerts(days: int = 7):
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row; alerts = []
    stock_rows = con.execute("SELECT sku, platform, region, date, stock_status FROM daily_snapshots WHERE date >= date('now', ?) ORDER BY sku, date DESC", (f"-{days} days",)).fetchall()
    by_sku = {}
    for r in stock_rows: by_sku.setdefault((r["sku"], r["platform"], r["region"]), []).append(r)
    for (sku, plat, region), recs in by_sku.items():
        if len(recs) >= 2 and recs[0]["stock_status"] == "Out of Stock" and recs[1]["stock_status"] == "In Stock":
            alerts.append({"type": "STOCK_OUT", "severity": "warning", "platform": plat, "region": region, "sku": sku, "message": f"{plat.upper()} {region}: {sku} went out of stock"})
    new_rows = con.execute("SELECT sku, platform, region, MIN(date) AS first_seen FROM daily_snapshots GROUP BY sku, platform, region HAVING first_seen >= date('now', ?)", (f"-{days} days",)).fetchall()
    for r in new_rows[:50]: alerts.append({"type": "NEW_SELLER", "severity": "info", "platform": r["platform"], "region": r["region"], "sku": r["sku"], "message": f"New listing on {r['platform'].upper()} {r['region']}: {r['sku']}", "first_seen": r["first_seen"]})
    p_rows = con.execute("SELECT sku, platform, region, date, price_usd FROM daily_snapshots WHERE date >= date('now', ?) ORDER BY sku, date ASC", (f"-{days} days",)).fetchall()
    by_sku2 = {}
    for r in p_rows: by_sku2.setdefault((r["sku"], r["platform"], r["region"]), []).append((r["date"], float(r["price_usd"])))
    for key, series in by_sku2.items():
        if len(series) < 5: continue
        earlier = [p for _, p in series[:-1]]; last_date, last_price = series[-1]
        m = statistics.mean(earlier); s = statistics.pstdev(earlier) or 0.0001; z = (last_price - m) / s
        if abs(z) >= 2.5:
            sku, plat, region = key
            alerts.append({"type": "PRICE_OUTLIER", "severity": "warning", "platform": plat, "region": region, "sku": sku, "message": f"{plat.upper()} {region}: {sku} price ${last_price:.2f} is {z:+.1f}σ from mean ${m:.2f}", "date": last_date, "z_score": round(z, 2)})
    con.close(); order = {"critical": 0, "warning": 1, "info": 2}; alerts.sort(key=lambda a: order.get(a["severity"], 3))
    return alerts

@app.get("/arbitrage")
def find_arbitrage(min_margin_pct: float = 15.0, limit: int = 50):
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row
    rows = con.execute("SELECT title, platform, region, price_usd, url, sku FROM bestsellers WHERE price_usd IS NOT NULL ORDER BY id DESC LIMIT 10000").fetchall()
    con.close(); buckets = {}
    for r in rows:
        tokens = frozenset(product_model_tokens(r["title"]))
        if not tokens: continue
        buckets.setdefault(tokens, []).append(dict(r))
    opportunities = []
    for tokens, items in buckets.items():
        per_platform = {}
        for it in items:
            key = (it["platform"], it["region"])
            if key not in per_platform or it["price_usd"] < per_platform[key]["price_usd"]: per_platform[key] = it
        if len(per_platform) < 2: continue
        cheapest = min(per_platform.values(), key=lambda x: x["price_usd"]); priciest = max(per_platform.values(), key=lambda x: x["price_usd"])
        if cheapest["price_usd"] <= 0: continue
        spread = priciest["price_usd"] - cheapest["price_usd"]; margin_pct = spread / cheapest["price_usd"] * 100
        if margin_pct < min_margin_pct: continue
        opportunities.append({"product": " ".join(sorted(tokens)), "buy_from": {"platform": cheapest["platform"], "region": cheapest["region"], "price_usd": round(cheapest["price_usd"], 2), "url": cheapest["url"]}, "sell_on": {"platform": priciest["platform"], "region": priciest["region"], "price_usd": round(priciest["price_usd"], 2), "url": priciest["url"]}, "spread_usd": round(spread, 2), "margin_pct": round(margin_pct, 1)})
    opportunities.sort(key=lambda x: -x["margin_pct"]); return opportunities[:limit]

@app.get("/category_gaps")
def category_gaps(limit: int = 30):
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row
    rows = con.execute("SELECT title, platform FROM bestsellers WHERE price_usd IS NOT NULL ORDER BY id DESC LIMIT 10000").fetchall()
    con.close(); ALL_PLATFORMS = {"jumia", "amazon", "alibaba", "ebay", "kibuga"}; buckets = {}
    for r in rows:
        tokens = frozenset(product_model_tokens(r["title"]))
        if not tokens: continue
        buckets.setdefault(tokens, set()).add(r["platform"])
    gaps = []
    for tokens, platforms in buckets.items():
        if len(platforms) < 1 or len(platforms) >= len(ALL_PLATFORMS): continue
        missing = sorted(ALL_PLATFORMS - platforms); gaps.append({"product": " ".join(sorted(tokens)), "found_on": sorted(platforms), "missing_from": missing, "gap_count": len(missing)})
    gaps.sort(key=lambda g: -g["gap_count"]); return gaps[:limit]

@app.get("/currency")
def get_currency_info():
    info = get_rates()
    return {"supported": ["USD", "UGX"], "rates": info["rates"], "fetched_at": info["fetched_at"], "source": info["source"]}

@app.get("/_diag")
def diag():
    con = sqlite3.connect(DB_PATH); con.row_factory = sqlite3.Row; info = {}
    try:
        info["bestsellers_count"] = con.execute("SELECT COUNT(*) FROM bestsellers").fetchone()[0]
        info["price_history_count"] = con.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
        try:
            info["daily_snapshots_count"] = con.execute("SELECT COUNT(*) FROM daily_snapshots").fetchone()[0]
            info["daily_snapshots_table"] = "exists"
        except Exception as e:
            info["daily_snapshots_count"] = 0
            info["daily_snapshots_table"] = f"missing: {e}"
        info["by_platform"] = [dict(r) for r in con.execute("SELECT platform, COUNT(*) AS n FROM bestsellers GROUP BY platform").fetchall()]
        info["iphone14pro_count"] = con.execute("SELECT COUNT(*) FROM bestsellers WHERE LOWER(title) LIKE '%iphone%' AND LOWER(title) LIKE '%14%' AND LOWER(title) LIKE '%pro%'").fetchone()[0]
        info["sample_titles"] = [r["title"] for r in con.execute("SELECT title FROM bestsellers LIMIT 5").fetchall()]
    finally: con.close()
    return info

@app.get("/categories")
def list_categories():
    from core.scrape_query import category_choices
    return [{"key": k, "label": label} for k, label in category_choices()]

class MissingItemsPayload(BaseModel):
    platform: str
    items: List[Dict[str, Any]]

@app.post("/save_missing")
def save_missing(payload: MissingItemsPayload):
    if not payload.items: return {"status": "error"}
    save_items(payload.items, datetime.date.today().isoformat())
    return {"status": "success", "count": len(payload.items)}
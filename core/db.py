import sqlite3
import datetime
import requests

DB_PATH = "bestseller.db"

def get_usd_rates():
    try:
        resp = requests.get("https://open.er-api.com/v6/latest/USD", timeout=5)
        data = resp.json()
        if data.get("result") == "success":
            return data["rates"]
    except Exception:
        pass
    return {"USD": 1.0, "NGN": 1500.0, "CNY": 7.2, "UGX": 3800.0, "KES": 150.0, "GBP": 0.8, "EUR": 0.9}

def _rates():
    """Live rates via core.currency (USD + UGX only)."""
    try:
        from core.currency import get_rates
        return get_rates()["rates"]
    except Exception:
        return {"USD": 1.0, "UGX": 3800.0}

def get_db_connection():
    # timeout=30 means it will wait up to 30 seconds if the DB is locked before failing
    con = sqlite3.connect(DB_PATH, timeout=30)
    # WAL mode allows concurrent reads and writes, fixing the "database is locked" error
    con.execute("PRAGMA journal_mode=WAL;")
    return con

def init_db():
    con = get_db_connection()
    con.execute("""
        CREATE TABLE IF NOT EXISTS bestsellers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT, region TEXT, sku TEXT, title TEXT, price_usd REAL, price_local REAL,
            previous_price_usd REAL, stock_status TEXT, currency TEXT, is_new BOOLEAN DEFAULT 0,
            status TEXT DEFAULT 'active', last_seen TEXT, url TEXT, snapshot_date TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT, title TEXT, alert_type TEXT, message TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS tracker_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            platform TEXT, new_items INTEGER, total_scanned INTEGER
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT, platform TEXT, price_usd REAL, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS daily_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT NOT NULL,
            platform TEXT NOT NULL,
            region TEXT,
            date TEXT NOT NULL,
            price_usd REAL,
            stock_status TEXT,
            UNIQUE (sku, platform, region, date)
        )
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_daily_sku_date
        ON daily_snapshots (sku, date)
    """)
    con.execute("""
        CREATE INDEX IF NOT EXISTS idx_daily_date
        ON daily_snapshots (date)
    """)
    con.commit()
    con.close()

def save_items(items, date_str):
    con = get_db_connection()
    cursor = con.cursor()
    new_count = 0
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    for item in items:
        local_currency = item.get('currency', 'USD')
        local_price = item['price']
        rate = _rates().get(local_currency, 1.0)
        price_usd = local_price / rate
        region = item.get('region', 'GLOBAL')
        
        cursor.execute("SELECT id, price_usd FROM bestsellers WHERE sku = ? AND platform = ? AND region = ? ORDER BY id DESC LIMIT 1", (item['sku'], item['platform'], region))
        row = cursor.fetchone()
        
        if row:
            item_id, prev_price_usd = row
            if abs(price_usd - prev_price_usd) > 0.01:
                cursor.execute("INSERT INTO price_history (sku, platform, price_usd) VALUES (?, ?, ?)", (item['sku'], item['platform'], round(price_usd, 2)))
            
            cursor.execute("""
                UPDATE bestsellers SET price_usd = ?, last_seen = ?, status = 'active', previous_price_usd = ? WHERE id = ?
            """, (round(price_usd, 2), now_str, round(prev_price_usd, 2), item_id))
            
            if price_usd < (prev_price_usd * 0.95):
                drop_amount = prev_price_usd - price_usd
                msg = f"Price dropped by ${drop_amount:,.2f} (From ${prev_price_usd:,.2f} to ${price_usd:,.2f})"
                cursor.execute("INSERT INTO alerts (platform, title, alert_type, message) VALUES (?, ?, ?, ?)", (item['platform'], item['title'], "PRICE_DROP", msg))
        else:
            cursor.execute("""
                INSERT INTO bestsellers (platform, region, sku, title, price_usd, price_local, previous_price_usd, stock_status, currency, is_new, status, last_seen, url, snapshot_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'active', ?, ?, ?)
            """, (item['platform'], region, item['sku'], item['title'], round(price_usd, 2), local_price, round(price_usd, 2), item['stock_status'], local_currency, now_str, item['url'], date_str))
            cursor.execute("INSERT INTO price_history (sku, platform, price_usd) VALUES (?, ?, ?)", (item['sku'], item['platform'], round(price_usd, 2)))
            new_count += 1
            
    con.commit()

    # Aggregate today's cheapest per (sku, platform, region)
    try:
        con.execute("""
            INSERT OR REPLACE INTO daily_snapshots
                (sku, platform, region, date, price_usd, stock_status)
            SELECT sku, platform, region, ?, MIN(price_usd), 'In Stock'
            FROM bestsellers
            WHERE snapshot_date = ?
            GROUP BY sku, platform, region
        """, (date_str, date_str))
        con.commit()
    except Exception:
        pass

    con.close()
    return new_count

def mark_deleted_items(platform, run_date):
    con = get_db_connection()
    con.execute("UPDATE bestsellers SET status = 'deleted' WHERE platform = ? AND last_seen NOT LIKE ? AND status = 'active'", (platform.lower(), f"{run_date}%"))
    con.commit()
    con.close()

def log_tracker_run(platform, new_items, total_scanned):
    con = get_db_connection()
    now_str = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    con.execute("INSERT INTO tracker_log (timestamp, platform, new_items, total_scanned) VALUES (?, ?, ?, ?)", (now_str, platform, new_items, total_scanned))
    con.commit()
    con.close()

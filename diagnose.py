# diagnose.py
import sqlite3
import requests
import sys
import os

API = "http://localhost:8000"
DB = "bestseller.db"

def header(t):
    print(f"\n{'='*60}\n{t}\n{'='*60}")

def main():
    # 1. Database Check
    header("1. DATABASE CHECK")
    if not os.path.exists(DB):
        print(f"❌ FATAL: {DB} not found. Are you in the right folder?")
        return
    
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    
    total = con.execute("SELECT COUNT(*) FROM bestsellers").fetchone()[0]
    print(f"Total items in DB: {total:,}")
    
    print("\nItems per platform:")
    rows = con.execute("SELECT platform, COUNT(*) as c FROM bestsellers GROUP BY platform").fetchall()
    for r in rows:
        print(f"  - {r['platform'].upper():8s} : {r['c']:,}")

    print("\nPrice Sanity Check (Look for crazy numbers > $10,000):")
    rows = con.execute("SELECT platform, title, price_usd FROM bestsellers WHERE price_usd > 10000 LIMIT 3").fetchall()
    if not rows:
        print("  ✅ Prices look normal (no items > $10,000)")
    else:
        for r in rows:
            print(f"  ❌ CORRUPTED PRICE: [{r['platform']}] {r['title'][:30]} = ${r['price_usd']:,.2f}")

    con.close()

    # 2. API Connectivity
    header("2. API STATUS")
    try:
        r = requests.get(f"{API}/analytics", timeout=3)
        r.raise_for_status()
        print("✅ API is running")
    except Exception as e:
        print(f"❌ API is DOWN: {e}")
        print("   Run: uvicorn api.main:app")
        return

    # 3. Tokenizer & Matcher
    header("3. MODEL MATCHING LOGIC")
    try:
        from api.main import product_model_tokens, is_same_product_model
        t1 = product_model_tokens("Apple iPhone 14 Pro 128GB Unlocked")
        t2 = product_model_tokens("iPhone 14 Pro")
        print(f"Tokens 'Apple iPhone 14 Pro 128GB Unlocked': {t1}")
        print(f"Tokens 'iPhone 14 Pro':                      {t2}")
        
        match = is_same_product_model("iPhone 14 Pro", "Apple iPhone 14 Pro 128GB Unlocked")
        if match:
            print("✅ Model Matcher: iPhone 14 Pro matches Apple iPhone 14 Pro 128GB")
        else:
            print("❌ Model Matcher FAILED: iPhone 14 Pro does NOT match Apple iPhone 14 Pro")
    except Exception as e:
        print(f"❌ Could not import logic from api.main: {e}")

    # 4. Test Comparison Endpoint
    header("4. COMPARISON ENDPOINT (/compare/specific)")
    try:
        r = requests.get(f"{API}/compare/specific", params={"title": "iPhone 14 Pro"}, timeout=5)
        data = r.json()
        matches = data.get("exact_matches", [])
        print(f"Matches found for 'iPhone 14 Pro': {len(matches)}")
        
        platforms = set(m["platform"] for m in matches)
        print(f"Platforms found in matches: {', '.join(platforms).upper() if platforms else 'NONE'}")
        
        if len(platforms) >= 2:
            print("✅ Cross-platform matching works")
        else:
            print("⚠️ Warning: Only found matches on 1 platform (or 0). Dialog will look empty.")
    except Exception as e:
        print(f"❌ Error hitting /compare/specific: {e}")

    print("\n" + "="*60)
    print("DIAGNOSTIC COMPLETE")
    print("If the DB and API are ✅ but the UI is broken, the issue is in ui/pages/")
    print("="*60)

if __name__ == "__main__":
    main()
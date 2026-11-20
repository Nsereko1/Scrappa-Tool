import time
import requests
import sys

API_URL = "http://localhost:8000"
TARGET_ITEMS = 5000  # Massive limit to test "ALL" items

def run_test():
    print("==================================================")
    print(f"🚀 INITIATING FULL SYSTEM STRESS TEST")
    print(f"Target: {TARGET_ITEMS} items per platform")
    print("==================================================\n")

    platforms = ["amazon", "alibaba", "ebay", "jumia"]
    
    # 1. Trigger Scrapes
    for p in platforms:
        print(f"[{p.upper()}] Triggering scrape for {TARGET_ITEMS} items...")
        start_time = time.time()
        
        try:
            # We set a very long timeout because Jumia will paginate and take time
            resp = requests.post(
                f"{API_URL}/run", 
                params={"platform": p, "limit": TARGET_ITEMS}, 
                timeout=900 # 15 minutes timeout
            )
            resp.raise_for_status()
            data = resp.json()
            
            elapsed = time.time() - start_time
            if data.get("status") == "success":
                print(f"  ✅ Success: Scraped {data.get('count')} items in {elapsed:.1f} seconds.")
            else:
                print(f"  ❌ Failed: {data}")
        except requests.exceptions.Timeout:
            print(f"  ❌ Failed: Request timed out. {p} took too long.")
        except Exception as e:
            print(f"  ❌ Failed: {e}")
        print("")

    # 2. Verify Database & API Health
    print("==================================================")
    print("📊 VERIFYING SYSTEM STATUS")
    print("==================================================")
    
    try:
        start_time = time.time()
        resp = requests.get(f"{API_URL}/analytics", timeout=60)
        resp.raise_for_status()
        analytics = resp.json()
        elapsed = time.time() - start_time
        
        print(f"API Response Time: {elapsed:.2f} seconds\n")
        
        total_items = 0
        print("Items in Database by Platform:")
        for plat in analytics.get("platforms", []):
            count = plat["count"]
            total_items += count
            print(f"  - {plat['platform'].upper()}: {count:,} items")
            
        print(f"\nTotal Items Successfully Stored: {total_items:,}")
        
        print("\nAverage Price per Platform (USD):")
        for price in analytics.get("avg_prices", []):
            print(f"  - {price['platform'].upper()}: ${price['avg_price']:,.2f}")
            
        print("\n🏆 Top 5 Most Common Items:")
        for item in analytics.get("top_items", []):
            print(f"  - {item['title'][:50]}... ({item['count']} times)")

        print("\n==================================================")
        if total_items > 10000:
            print("✅ SYSTEM READY: Successfully handled a massive dataset!")
            print("⚠️  NOTE: When you open the UI and click 'All Products',")
            print("    it may freeze for 2-5 seconds while rendering 10k+ rows.")
            print("==================================================")
        else:
            print("⚠️ WARNING: Database has fewer than 10,000 items.")
            print("==================================================")

    except Exception as e:
        print(f"❌ Failed to fetch analytics: {e}")

if __name__ == "__main__":
    run_test()

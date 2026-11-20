import datetime
from core.db import init_db, save_items
from adapters.jumia import scrape_jumia

if __name__ == "__main__":
    print("Initializing database...")
    init_db()
    
    items = scrape_jumia()
    
    if items:
        today = datetime.date.today().isoformat()
        save_items(items, today)
        print(f"Successfully saved {len(items)} items to bestseller.db!")
    else:
        print("No items scraped.")

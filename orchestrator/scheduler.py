# orchestrator/scheduler.py
from apscheduler.schedulers.blocking import BlockingScheduler
from adapters.ebay import EbayAdapter
from adapters.alibaba1688 import Alibaba1688Adapter
from adapters.jumia import JumiaAdapter
from core.normalization import normalize
from core.storage import save_snapshot

ADAPTERS = {
    "ebay": (EbayAdapter(), ["31388", "11071"]),
    "1688": (Alibaba1688Adapter(), ["1031918"]),
    "jumia": (JumiaAdapter(bot_contact="https://yourdomain.com/bot"), ["/phones-tablets/"]),
}

def run_platform(name: str):
    adapter, categories = ADAPTERS[name]
    all_records = []
    for cat in categories:
        try:
            all_records.extend(adapter.fetch_best_sellers(cat))
        except Exception as exc:
            print(f"[{name}] {cat} failed: {exc}")   # per-category isolation
    if all_records:
        save_snapshot(normalize(all_records))

if __name__ == "__main__":
    scheduler = BlockingScheduler()
    for name in ADAPTERS:
        scheduler.add_job(lambda n=name: run_platform(n), "cron", hour=3, minute=0)
    scheduler.start()
# SCRAPA update: what to copy where

Unzip, then copy each file to the SAME path inside your "SCRAPA Tool" folder.
Python 3.10+ (3.12 recommended). `pip install -r requirements.txt`

## REPLACE these existing files
| File | Why |
|---|---|
| api/main.py | whole file replaced (scan/agent code moved out, real-only queries, safe connections, strict matching) |
| core/currency.py | all FX rates kept; NGN/KES no longer treated as USD; UGX/USD/KES/NGN display |
| core/db.py | is_mock + migration, safe connections, real snapshots, scoped delete |
| adapters/jumia.py | no silent mocks, stable SKU, pagination, backoff |
| adapters/kibuga.py | same |
| ui/app.py | sidebar "Display currency" dropdown |
| ui/pages/products.py | price column shows converted price + the store's real price |
| ui/pages/compare.py | converted prices |
| ui/pages/compare_dialog.py | uses the global currency (old per-dialog UGX dropdown + slow per-row HTTP call removed) |
| ui/pages/discovery.py | converted prices |
| ui/pages/charts.py | trend chart in the chosen currency |

## ADD these new files
core/config.py, core/matching.py, core/scan.py, core/agent.py, adapters/http.py,
api/scan_routes.py, ui/currency.py, tests/test_core.py, tests/test_api.py, tests/__init__.py, requirements.txt

## DO NOT TOUCH (still used)
core/scrape_query.py, adapters/mock_adapters.py, ui/pages/alerts.py, ui/pages/snapshots.py, ui/pages/status.py
(snapshots.py / status.py are dead code: they call endpoints that no longer exist; safe to delete.)

## Run order
1. Back up the folder (at least bestseller.db).
2. Copy files in.
3. `python -m core.db`                 # migrate; tags old mock rows, deletes nothing
4. `python -m core.db --purge-mock`    # removes fake rows (auto-backup first)
5. `python -m pytest -q`               # 22 tests should pass
6. `uvicorn api.main:app --host 127.0.0.1 --port 8000`
7. `python -m ui.app`   (second terminal, same folder)  [use whatever command you used before]

## Currency model
Internal currency is always USD (`price_usd`). The sidebar dropdown converts at display time only.
Every row also keeps `price_local` + `currency` (what the store listed); the Price column shows both,
e.g. `UGX 570,000  (NGN 150,000)`.

## Environment variables (all optional)
SCRAPA_USER_AGENT="YourBot/1.0 (+https://yourdomain/bot)"   # identify yourself
SCRAPA_AGENT=1                 # enable background tracker (default OFF)
SCRAPA_AGENT_INTERVAL=3600     # seconds
SCRAPA_DEMO=1                  # allow mock data (demo only; never for real analysis)
SCRAPA_API_KEY=...             # write endpoints then need header X-API-Key (UI would need to send it)

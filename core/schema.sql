-- core/schema.sql
CREATE TABLE IF NOT EXISTS raw_ingest (
    id            INTEGER PRIMARY KEY,
    platform      TEXT NOT NULL,
    ingested_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    payload       TEXT NOT NULL           -- full JSON for audit
);

CREATE TABLE IF NOT EXISTS bestseller_snapshots (
    id                INTEGER PRIMARY KEY,
    platform          TEXT NOT NULL,
    product_id        TEXT NOT NULL,
    title             TEXT,
    category_native   TEXT,
    category_unified  TEXT,
    rank_native       INTEGER,
    rank_metric       TEXT,
    normalized_score  REAL,
    confidence        TEXT CHECK (confidence IN ('high','medium','low')),
    signal_type       TEXT,
    price             REAL,
    currency          TEXT,
    sales_30d         INTEGER,
    snapshot_date     DATE NOT NULL,
    UNIQUE (platform, product_id, snapshot_date)
);
CREATE INDEX IF NOT EXISTS idx_snapshot_lookup
    ON bestseller_snapshots (snapshot_date, platform, category_unified);
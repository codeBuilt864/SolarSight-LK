"""Tiny SQLite storage layer. Time series are stored as (site_id, ts, power_kw) rows."""
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("SOLARSIGHT_DB", "solarsight.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
    site_id     TEXT PRIMARY KEY,
    district    TEXT NOT NULL,
    capacity_kw REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS readings (
    site_id  TEXT NOT NULL,
    ts       TEXT NOT NULL,          -- ISO 8601, UTC
    power_kw REAL NOT NULL,
    PRIMARY KEY (site_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_readings_ts ON readings (ts);
"""


@contextmanager
def connect(path: str | None = None):
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()

import sqlite3
from core.config import settings
import datetime
import json
from pathlib import Path

def db_init():
    with sqlite3.connect(settings.DB_PATH) as conn:
        cur = conn.cursor()

        conn.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vendor TEXT,
            due_date TEXT,
            amount REAL,
            currency TEXT DEFAULT 'PHP',
            status TEXT DEFAULT 'unpaid',
            source_email_id TEXT,
            drive_file_id TEXT,
            drive_file_name TEXT,
            created_at TEXT,
            paid_at TEXT,
            notes TEXT
        )""")

        cur.executescript("""
        CREATE TABLE IF NOT EXISTS bill_sources (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            provider        TEXT NOT NULL
                                CHECK (provider IN ('gmail','drive','manual')),
            gmail_query     TEXT,
            sender_email    TEXT,
            subject_like    TEXT,
            include_kw      TEXT,
            exclude_kw      TEXT,
            drive_folder_id TEXT,
            file_pattern    TEXT,
            due_date_regex  TEXT,
            amount_regex    TEXT,
            currency        TEXT DEFAULT 'PHP',
            password_env    TEXT,
            active          INTEGER NOT NULL DEFAULT 1,
            created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            UNIQUE(name)
        );

        CREATE TRIGGER IF NOT EXISTS trg_bill_sources_updated_at
        AFTER UPDATE ON bill_sources
        FOR EACH ROW
        BEGIN
        UPDATE bill_sources
        SET updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now')
        WHERE id = NEW.id;
        END;

        CREATE INDEX IF NOT EXISTS idx_bill_sources_active ON bill_sources(active);
        CREATE INDEX IF NOT EXISTS idx_bill_sources_provider ON bill_sources(provider);
        """)

        if settings.DEFAULT_SOURCES_PATH and Path(settings.DEFAULT_SOURCES_PATH).exists():
            with open(settings.DEFAULT_SOURCES_PATH, "r", encoding="utf-8") as f:
                default_sources = json.load(f)

            cur.executemany("""
                INSERT INTO bill_sources (
                    name, provider, gmail_query, sender_email, subject_like, include_kw, exclude_kw, drive_folder_id, file_pattern, due_date_regex, amount_regex, currency
                ) VALUES (
                    :name, :provider, :gmail_query, :sender_email, :subject_like, :include_kw, :exclude_kw, :drive_folder_id, :file_pattern, :due_date_regex, :amount_regex, :currency
                )
                ON CONFLICT(name) DO UPDATE SET
                    provider = excluded.provider,
                    gmail_query = excluded.gmail_query,
                    sender_email = excluded.sender_email,
                    subject_like = excluded.subject_like,
                    include_kw = excluded.include_kw,
                    exclude_kw = excluded.exclude_kw,
                    drive_folder_id = excluded.drive_folder_id,
                    file_pattern = excluded.file_pattern,
                    due_date_regex = excluded.due_date_regex,
                    amount_regex = excluded.amount_regex,
                    currency = excluded.currency,
                    active = 1;
            """, default_sources)

        cur.executescript("""
            -- Existing bills table creation here ...

            -- Track last run of fetching bills
            CREATE TABLE IF NOT EXISTS last_run (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor        TEXT NOT NULL,
                last_fetch_at TEXT NOT NULL,
                success       INTEGER NOT NULL DEFAULT 1,
                total_fetched INTEGER DEFAULT 0,
                total_new     INTEGER DEFAULT 0,
                duration_sec  REAL,
                notes         TEXT,
                created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                UNIQUE(vendor)
            );

            CREATE INDEX IF NOT EXISTS idx_last_run_vendor ON last_run(vendor);
            CREATE INDEX IF NOT EXISTS idx_last_run_success ON last_run(success);
        """)
        conn.commit()

def db_insert_bill(item: dict):
    with sqlite3.connect(settings.DB_PATH) as conn:
        conn.execute("""
        INSERT INTO bills (vendor, due_date, amount, currency, status, source_email_id,
                           drive_file_id, drive_file_name, created_at, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.get("vendor"),
            item.get("due_date"),
            item.get("amount"),
            item.get("currency","PHP"),
            item.get("status","unpaid"),
            item.get("source_email_id"),
            item.get("drive_file_id"),
            item.get("drive_file_name"),
            datetime.utcnow().isoformat(),
            item.get("notes"),
        ))
        conn.commit()

def db_all():
    with sqlite3.connect(settings.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM bills ORDER BY status ASC, due_date ASC")
        return [dict(r) for r in cur.fetchall()]

def get_bill_sources():
    with sqlite3.connect(settings.DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute("SELECT * FROM bill_sources WHERE active=1 ORDER BY name ASC")
        return [dict(r) for r in cur.fetchall()]

def db_mark_paid(bill_id: int):
    with sqlite3.connect(settings.DB_PATH) as conn:
        conn.execute("UPDATE bills SET status='paid', paid_at=? WHERE id=? AND status!='paid'",
                     (datetime.utcnow().isoformat(), bill_id))
        conn.commit()

def main():
    db_init()

if __name__ == "__main__":
    main()
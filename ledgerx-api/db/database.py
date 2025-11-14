import sqlite3
from core.config import settings
from datetime import datetime
import json
from pathlib import Path

def db_init():
    with sqlite3.connect(settings.DB_PATH) as conn:
        cur = conn.cursor()

        conn.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            due_date TEXT,
            sent_date TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            amount TEXT,
            currency TEXT DEFAULT 'PHP',
            status TEXT DEFAULT 'unpaid',
            source_email_id TEXT,
            drive_file_id TEXT,
            drive_file_name TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            paid_at TEXT,
            category TEXT,
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
            currency        TEXT DEFAULT 'PHP',
            password_env    TEXT,
            category        TEXT DEFAULT 'uncategorized',
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
                    name, provider, gmail_query, sender_email, subject_like, include_kw, exclude_kw, drive_folder_id, file_pattern, currency, password_env, category
                ) VALUES (
                    :name, :provider, :gmail_query, :sender_email, :subject_like, :include_kw, :exclude_kw, :drive_folder_id, :file_pattern, :currency, :password_env, :category
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
                    currency = excluded.currency,
                    password_env = excluded.password_env,
                    category = excluded.category,
                    active = 1;
            """, default_sources)

        cur.executescript("""
            -- Existing bills table creation here ...

            -- Track last run of fetching bills
            CREATE TABLE IF NOT EXISTS last_run (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                success       INTEGER NOT NULL DEFAULT 1,
                duration_sec  REAL,
                notes         TEXT,
                last_fetch_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                UNIQUE(name)
            );

            CREATE INDEX IF NOT EXISTS idx_last_run_name_lastfetch ON last_run(name, last_fetch_at DESC);
        """)
        conn.commit()

def bill_exists(item: dict) -> bool:
    with sqlite3.connect(settings.DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT EXISTS(
                SELECT 1 FROM bills
                WHERE name = ? AND sent_date = ?
            )
        """, (item.get("name"), item.get("sent_date")))

        return bool(cur.fetchone()[0])

def db_insert_bill(item: dict):
    with sqlite3.connect(settings.DB_PATH) as conn:
        conn.execute("""
        INSERT INTO bills (name, due_date, sent_date, amount, currency, status, source_email_id,
                           drive_file_id, drive_file_name, paid_at, category, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.get("name"),
            item.get("due_date"),
            item.get("sent_date"),
            item.get("amount"),  
            item.get("currency","PHP"),
            item.get("status","unpaid"),
            item.get("source_email_id"),
            item.get("drive_file_id"),
            item.get("drive_file_name"),
            item.get("status","unpaid") == "paid" and datetime.utcnow().isoformat() or None,
            item.get("category", "uncategorized"),
            item.get("notes", "none"),
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

def get_last_run(name):
    with sqlite3.connect(settings.DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT last_fetch_at FROM last_run WHERE name = ? ORDER BY datetime(last_fetch_at) DESC LIMIT 1",(name,))
        row = cur.fetchone()

        if row:
            print("Latest run:")
            print(row)
            return row
        else:
            print("No records found for:", name)
        
        return None
    
def insert_or_update_last_run(item):
    if get_last_run(item.get("name")):
        with sqlite3.connect(settings.DB_PATH) as conn:
            conn.execute("""
            UPDATE last_run
            SET success = ?, duration_sec = ?, notes = ?, last_fetch_at = ?
            WHERE name = ?
            """, (
                item.get("success", 0),
                item.get("duration_sec"),
                item.get("notes", "none"),
                datetime.utcnow().isoformat(),
                item.get("name")
            ))
            conn.commit()
    else:
        with sqlite3.connect(settings.DB_PATH) as conn:
            conn.execute("""
            INSERT INTO last_run (name, success, duration_sec, notes)
            VALUES (?, ?, ?, ?)
            """, (
                item.get("name"),
                item.get("success", 0),
                item.get("duration_sec"),
                item.get("notes", "none")
            ))
            conn.commit()

def add_bill_source(item: dict):
    with sqlite3.connect(settings.DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO bill_sources (name, provider, gmail_query, sender_email, subject_like,
                                  include_kw, exclude_kw, drive_folder_id, file_pattern,
                                  currency, password_env, category, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.get("name"),
            item.get("provider"),
            item.get("gmail_query"),
            item.get("sender_email"),
            item.get("subject_like"),
            item.get("include_kw"),
            item.get("exclude_kw"),
            item.get("drive_folder_id"),
            item.get("file_pattern"),
            item.get("currency", "PHP"),
            item.get("password_env"),
            item.get("category", "uncategorized"),
            1
        ))
        conn.commit()

def main():
    db_init()

if __name__ == "__main__":
    main()
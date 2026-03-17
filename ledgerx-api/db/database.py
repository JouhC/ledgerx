from datetime import datetime, timezone
import json
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from core.config import settings
from utils.password_crypto import encrypt_password


def get_conn():
    return psycopg.connect(
        settings.DATABASE_URL,
        row_factory=dict_row
    )


def db_init():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS bills (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    name TEXT,
                    due_date TEXT,
                    sent_date TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    amount TEXT,
                    currency TEXT DEFAULT 'PHP',
                    status TEXT DEFAULT 'unpaid',
                    source_email_id TEXT,
                    drive_file_id TEXT,
                    drive_file_name TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    paid_at TIMESTAMPTZ,
                    category TEXT,
                    notes TEXT,
                    UNIQUE(name, sent_date)
                );
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS bill_sources (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    provider TEXT NOT NULL
                        CHECK (provider IN ('gmail', 'drive', 'manual')),
                    gmail_query TEXT,
                    sender_email TEXT,
                    subject_like TEXT,
                    include_kw TEXT,
                    exclude_kw TEXT,
                    drive_folder_id TEXT,
                    file_pattern TEXT,
                    currency TEXT DEFAULT 'PHP',
                    encrypted_password BYTEA,
                    category TEXT DEFAULT 'uncategorized',
                    useful_page INTEGER[] DEFAULT ARRAY[1],
                    active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cur.execute("""
                CREATE OR REPLACE FUNCTION set_updated_at()
                RETURNS TRIGGER AS $$
                BEGIN
                    NEW.updated_at = CURRENT_TIMESTAMP;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)

            cur.execute("""
                DROP TRIGGER IF EXISTS trg_bill_sources_updated_at ON bill_sources;
            """)

            cur.execute("""
                CREATE TRIGGER trg_bill_sources_updated_at
                BEFORE UPDATE ON bill_sources
                FOR EACH ROW
                EXECUTE FUNCTION set_updated_at();
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_bill_sources_active
                ON bill_sources(active);
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_bill_sources_provider
                ON bill_sources(provider);
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS last_run (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    success BOOLEAN NOT NULL DEFAULT TRUE,
                    duration_sec DOUBLE PRECISION,
                    notes TEXT,
                    last_fetch_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_last_run_name_lastfetch
                ON last_run(name, last_fetch_at DESC);
            """)

            if settings.DEFAULT_SOURCES_PATH and Path(settings.DEFAULT_SOURCES_PATH).exists():
                with open(settings.DEFAULT_SOURCES_PATH, "r", encoding="utf-8") as f:
                    default_sources = json.load(f)

                for item in default_sources:
                    password = settings.model_extra[item['password_env']] if item['password_env'] != "None" else ""
                    encrypted_password = encrypt_password(password) if password else None
                    cur.execute("""
                        INSERT INTO bill_sources (
                            name, provider, gmail_query, sender_email, subject_like,
                            include_kw, exclude_kw, drive_folder_id, file_pattern,
                            currency, encrypted_password, category, useful_page, active
                        ) VALUES (
                            %(name)s, %(provider)s, %(gmail_query)s, %(sender_email)s, %(subject_like)s,
                            %(include_kw)s, %(exclude_kw)s, %(drive_folder_id)s, %(file_pattern)s,
                            %(currency)s, %(encrypted_password)s, %(category)s, %(useful_page)s, TRUE
                        )
                        ON CONFLICT (name) DO UPDATE SET
                            provider = EXCLUDED.provider,
                            gmail_query = EXCLUDED.gmail_query,
                            sender_email = EXCLUDED.sender_email,
                            subject_like = EXCLUDED.subject_like,
                            include_kw = EXCLUDED.include_kw,
                            exclude_kw = EXCLUDED.exclude_kw,
                            drive_folder_id = EXCLUDED.drive_folder_id,
                            file_pattern = EXCLUDED.file_pattern,
                            currency = EXCLUDED.currency,
                            encrypted_password = EXCLUDED.encrypted_password,
                            category = EXCLUDED.category,
                            useful_page = EXCLUDED.useful_page,
                            active = TRUE;
                    """, {
                        "name": item.get("name"),
                        "provider": item.get("provider"),
                        "gmail_query": item.get("gmail_query"),
                        "sender_email": item.get("sender_email"),
                        "subject_like": item.get("subject_like"),
                        "include_kw": item.get("include_kw"),
                        "exclude_kw": item.get("exclude_kw"),
                        "drive_folder_id": item.get("drive_folder_id"),
                        "file_pattern": item.get("file_pattern"),
                        "currency": item.get("currency", "PHP"),
                        "encrypted_password": encrypted_password,
                        "category": item.get("category", "uncategorized"),
                        "useful_page": item.get("useful_page", [1]),
                    })


def bill_exists(item: dict) -> bool:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS(
                    SELECT 1
                    FROM bills
                    WHERE name = %s AND sent_date = %s
                )
            """, (item.get("name"), item.get("sent_date")))
            row = cur.fetchone()
            return bool(row["exists"])


def db_insert_bill(item: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO bills (
                    name, due_date, sent_date, amount, currency, status,
                    source_email_id, drive_file_id, drive_file_name,
                    paid_at, category, notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (name, sent_date) DO NOTHING
            """, (
                item.get("name"),
                item.get("due_date"),
                item.get("sent_date"),
                item.get("amount"),
                item.get("currency", "PHP"),
                item.get("status", "unpaid"),
                item.get("source_email_id"),
                item.get("drive_file_id"),
                item.get("drive_file_name"),
                datetime.now(timezone.utc) if item.get("status", "unpaid") == "paid" else None,
                item.get("category", "uncategorized"),
                item.get("notes", ""),
            ))


def update_bill_source_folder_id(source_id: int, folder_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE bill_sources
                SET drive_folder_id = %s
                WHERE id = %s
            """, (folder_id, source_id))


def db_all():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT *
                FROM bills
                ORDER BY status ASC, due_date ASC
            """)
            return cur.fetchall()


def get_bill_sources():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT *
                FROM bill_sources
                WHERE active = TRUE
                ORDER BY name ASC
            """)
            return cur.fetchall()


def db_mark_paid(bill_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE bills
                SET status = 'paid',
                    paid_at = %s
                WHERE id = %s
                  AND status <> 'paid'
            """, (datetime.now(timezone.utc), bill_id))


def get_last_run(name: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT last_fetch_at
                FROM last_run
                WHERE name = %s
                ORDER BY last_fetch_at DESC
                LIMIT 1
            """, (name,))
            row = cur.fetchone()

            if row:
                print("Latest run:")
                print(row)
                return row
            else:
                print("No records found for:", name)
                return None


def insert_or_update_last_run(item: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO last_run (name, success, duration_sec, notes, last_fetch_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    success = EXCLUDED.success,
                    duration_sec = EXCLUDED.duration_sec,
                    notes = EXCLUDED.notes,
                    last_fetch_at = EXCLUDED.last_fetch_at
            """, (
                item.get("name"),
                item.get("success", False),
                item.get("duration_sec"),
                item.get("notes", "none"),
                datetime.now(timezone.utc),
            ))


def add_bill_source(item: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO bill_sources (
                    name, provider, gmail_query, sender_email, subject_like,
                    include_kw, exclude_kw, drive_folder_id, file_pattern,
                    currency, encrypted_password, category, useful_page, active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (name) DO NOTHING
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
                item.get("encrypted_password"),
                item.get("category", "uncategorized"),
                item.get("useful_page", [1]),
            ))


def main():
    db_init()


if __name__ == "__main__":
    main()
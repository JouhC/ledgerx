#!/usr/bin/env python3
"""
schema_init_sqlite.py — initialize LedgerX DB schema (SQLite)

Usage:
  export DB_PATH=./ledgerx.db   # optional (defaults to ./ledgerx.db)
  python schema_init_sqlite.py

Notes:
- All CREATEs use IF NOT EXISTS.
- TEXT used for ids (store UUID strings), timestamps (ISO-8601), emails.
- BLOB for encrypted tokens/passwords.
- JSON fields validated with json_valid().
- updated_at auto-managed via triggers.
"""

import os
import sqlite3
from contextlib import closing

DB_PATH = os.getenv("DB_PATH", "./ledgerx.db")

PRAGMAS = [
    "PRAGMA journal_mode=WAL;",
    "PRAGMA synchronous=NORMAL;",
    "PRAGMA foreign_keys=ON;"
]

TABLE_DDLS = [
    # ---------- Core: users & auth ----------
    """
    CREATE TABLE IF NOT EXISTS users (
      id TEXT PRIMARY KEY,
      email TEXT NOT NULL UNIQUE COLLATE NOCASE,
      display_name TEXT,
      photo_url TEXT,
      time_zone TEXT DEFAULT 'Asia/Manila',
      is_active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      deleted_at TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS identities (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      provider TEXT NOT NULL,                 -- 'google'
      provider_user_id TEXT NOT NULL,         -- sub
      email TEXT NOT NULL COLLATE NOCASE,
      email_verified INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      UNIQUE(provider, provider_user_id),
      UNIQUE(provider, email)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS oauth_tokens (
      id TEXT PRIMARY KEY,
      identity_id TEXT NOT NULL,
      access_token_enc BLOB NOT NULL,
      refresh_token_enc BLOB,
      token_scope TEXT,
      expires_at TEXT NOT NULL,  -- ISO-8601
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      FOREIGN KEY (identity_id) REFERENCES identities(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      user_agent TEXT,
      ip TEXT,
      expires_at TEXT NOT NULL,
      revoked_at TEXT,
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """,

    # ---------- Merchants ----------
    """
    CREATE TABLE IF NOT EXISTS merchants (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      name TEXT NOT NULL,
      alias TEXT,
      category TEXT,
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      UNIQUE(user_id, name)
    );
    """,

    # ---------- Gmail accounts (optional multi-inbox) ----------
    """
    CREATE TABLE IF NOT EXISTS gmail_accounts (
      id TEXT PRIMARY KEY,
      identity_id TEXT NOT NULL,
      email TEXT NOT NULL COLLATE NOCASE,
      label TEXT,
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      FOREIGN KEY (identity_id) REFERENCES identities(id) ON DELETE CASCADE,
      UNIQUE(identity_id, email)
    );
    """,

    # ---------- Bills ingestion: documents ----------
    """
    CREATE TABLE IF NOT EXISTS bill_documents (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      gmail_message_id TEXT NOT NULL,
      gmail_attachment_id TEXT,
      subject TEXT,
      from_email TEXT COLLATE NOCASE,
      received_at TEXT,                         -- ISO-8601
      file_sha256 BLOB NOT NULL,
      storage_uri TEXT NOT NULL,                -- file:// or s3-like
      mime_type TEXT DEFAULT 'application/pdf',
      bytes INTEGER,
      is_decrypted INTEGER NOT NULL DEFAULT 0,
      decrypted_storage_uri TEXT,
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      deleted_at TEXT,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      UNIQUE(user_id, file_sha256)
    );
    """,

    # ---------- Extraction results ----------
    """
    CREATE TABLE IF NOT EXISTS extraction_results (
      id TEXT PRIMARY KEY,
      document_id TEXT NOT NULL,
      ocr_engine TEXT,
      text_storage_uri TEXT,
      fields TEXT,                               -- JSON
      confidence REAL,
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      FOREIGN KEY (document_id) REFERENCES bill_documents(id) ON DELETE CASCADE,
      CHECK (fields IS NULL OR json_valid(fields))
    );
    """,

    # ---------- Statements (parsed) ----------
    """
    CREATE TABLE IF NOT EXISTS bill_statements (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      document_id TEXT NOT NULL,
      merchant_id TEXT,
      statement_period_start TEXT,               -- YYYY-MM-DD
      statement_period_end TEXT,                 -- YYYY-MM-DD
      due_date TEXT,                             -- YYYY-MM-DD
      currency TEXT DEFAULT 'PHP',
      amount_due NUMERIC,
      minimum_due NUMERIC,
      status TEXT NOT NULL DEFAULT 'unpaid',     -- CHECK below
      paid_at TEXT,
      notes TEXT,
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      deleted_at TEXT,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY (document_id) REFERENCES bill_documents(id) ON DELETE CASCADE,
      FOREIGN KEY (merchant_id) REFERENCES merchants(id) ON DELETE SET NULL,
      CHECK (status IN ('unpaid','paid','partial','ignored'))
    );
    """,

    # ---------- Payment events ----------
    """
    CREATE TABLE IF NOT EXISTS payment_events (
      id TEXT PRIMARY KEY,
      statement_id TEXT NOT NULL,
      amount NUMERIC NOT NULL,
      paid_via TEXT,
      reference TEXT,
      event_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      FOREIGN KEY (statement_id) REFERENCES bill_statements(id) ON DELETE CASCADE
    );
    """,

    # ---------- Rules: queries, passwords, reminders ----------
    """
    CREATE TABLE IF NOT EXISTS bill_rules (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      merchant_id TEXT,
      rule_name TEXT,
      gmail_query TEXT NOT NULL,
      attachment_mime TEXT DEFAULT 'application/pdf',
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY (merchant_id) REFERENCES merchants(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS bill_passwords (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      merchant_id TEXT NOT NULL,
      password_enc BLOB NOT NULL,
      valid_from TEXT DEFAULT (date('now')),
      valid_to TEXT,
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY (merchant_id) REFERENCES merchants(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS reminders (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      merchant_id TEXT,
      statement_id TEXT,
      rrule TEXT,
      remind_at TEXT,
      channel TEXT NOT NULL DEFAULT 'email',     -- email|push|sms|webhook
      payload TEXT,                               -- JSON
      active INTEGER NOT NULL DEFAULT 1,
      last_sent_at TEXT,
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY (merchant_id) REFERENCES merchants(id) ON DELETE SET NULL,
      FOREIGN KEY (statement_id) REFERENCES bill_statements(id) ON DELETE CASCADE,
      CHECK (payload IS NULL OR json_valid(payload)),
      CHECK ((merchant_id IS NOT NULL) OR (statement_id IS NOT NULL))
    );
    """,

    # ---------- Reporting ----------
    """
    CREATE TABLE IF NOT EXISTS report_configs (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      name TEXT NOT NULL,
      frequency TEXT NOT NULL,                   -- monthly|weekly|manual
      rrule TEXT,
      include_range TEXT NOT NULL DEFAULT 'last_month',
      filters TEXT,                               -- JSON
      recipients TEXT NOT NULL,                   -- CSV emails or JSON array
      active INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      CHECK (filters IS NULL OR json_valid(filters))
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS email_sends (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      purpose TEXT NOT NULL,                      -- report|reminder|alert
      subject TEXT NOT NULL,
      to_addresses TEXT NOT NULL,                 -- CSV or JSON
      message_id TEXT,
      payload TEXT,                                -- JSON
      sent_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      success INTEGER NOT NULL DEFAULT 1,
      error TEXT,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      CHECK (payload IS NULL OR json_valid(payload))
    );
    """,

    # ---------- Ops / ingestion ----------
    """
    CREATE TABLE IF NOT EXISTS ingestion_jobs (
      id TEXT PRIMARY KEY,
      user_id TEXT NOT NULL,
      rule_id TEXT,
      started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      finished_at TEXT,
      status TEXT NOT NULL DEFAULT 'running',     -- running|succeeded|failed
      stats TEXT,                                  -- JSON
      error TEXT,
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY (rule_id) REFERENCES bill_rules(id) ON DELETE SET NULL,
      CHECK (stats IS NULL OR json_valid(stats))
    );
    """,
]

INDEX_DDLS = [
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_oauth_tokens_identity ON oauth_tokens(identity_id);",
    "CREATE INDEX IF NOT EXISTS idx_bill_docs_user_received ON bill_documents(user_id, received_at DESC);",
    "CREATE INDEX IF NOT EXISTS idx_bill_statements_user_due ON bill_statements(user_id, due_date);",
    "CREATE INDEX IF NOT EXISTS idx_bill_statements_user_status ON bill_statements(user_id, status);",
    "CREATE INDEX IF NOT EXISTS idx_reminders_user_active ON reminders(user_id, active);",
    "CREATE INDEX IF NOT EXISTS idx_reminders_statement ON reminders(statement_id);",
    # JSON search helpers (optional, SQLite will still scan if missing)
    # e.g., create indexes on substring of subject or email if needed later
]

# Tables that should auto-update 'updated_at' on UPDATE
TABLES_WITH_UPDATED_AT = [
    "users", "identities", "oauth_tokens", "sessions", "merchants",
    "gmail_accounts", "bill_documents", "extraction_results",
    "bill_statements", "payment_events", "bill_rules", "bill_passwords",
    "reminders", "report_configs", "email_sends", "ingestion_jobs"
]

def trigger_ddls_for(table: str):
    return [
        f"""
        CREATE TRIGGER IF NOT EXISTS trg_{table}_updated_at
        AFTER UPDATE ON {table}
        FOR EACH ROW
        BEGIN
          UPDATE {table}
          SET updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
          WHERE id = NEW.id;
        END;
        """
    ]

def main():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute("PRAGMA busy_timeout=5000;")
        for p in PRAGMAS:
            conn.execute(p)

        cur = conn.cursor()

        for ddl in TABLE_DDLS:
            cur.executescript(ddl)

        for ddl in INDEX_DDLS:
            cur.execute(ddl)

        # Create updated_at triggers
        for t in TABLES_WITH_UPDATED_AT:
            for ddl in trigger_ddls_for(t):
                cur.executescript(ddl)

        conn.commit()

    print(f"SQLite schema initialized at {DB_PATH}")

if __name__ == "__main__":
    main()

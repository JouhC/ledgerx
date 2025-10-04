#!/usr/bin/env python3
"""
db_wrapper.py — SQLite3 query wrapper for LedgerX schema

Usage:
    from db_wrapper import Database

    db = Database("ledgerx.db")
    db.execute("INSERT INTO users (id, email) VALUES (?, ?)", [uuid4().hex, "you@example.com"])
    user = db.fetchone("SELECT * FROM users WHERE email = ?", ["you@example.com"])
    print(user)
"""

import sqlite3
from contextlib import closing
from typing import Any, List, Optional, Tuple, Union, Dict
import uuid

Row = Dict[str, Any]


class Database:
    def __init__(self, db_path: str = "./ledgerx.db") -> None:
        self.db_path = db_path
        self._connect()

    def _connect(self) -> None:
        self.conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        self.conn.row_factory = sqlite3.Row  # access by column name
        with closing(self.conn.cursor()) as cur:
            cur.execute("PRAGMA foreign_keys=ON;")
            cur.execute("PRAGMA journal_mode=WAL;")
            cur.execute("PRAGMA synchronous=NORMAL;")

    def close(self) -> None:
        self.conn.close()

    def execute(self, sql: str, params: Union[List, Tuple] = ()) -> None:
        """Execute a single SQL statement (INSERT/UPDATE/DELETE)."""
        with closing(self.conn.cursor()) as cur:
            cur.execute(sql, params)
        self.conn.commit()

    def executemany(self, sql: str, seq_of_params: List[Union[List, Tuple]]) -> None:
        """Execute many statements in a batch (bulk insert/update)."""
        with closing(self.conn.cursor()) as cur:
            cur.executemany(sql, seq_of_params)
        self.conn.commit()

    def fetchone(self, sql: str, params: Union[List, Tuple] = ()) -> Optional[Row]:
        """Fetch a single row as dict."""
        with closing(self.conn.cursor()) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def fetchall(self, sql: str, params: Union[List, Tuple] = ()) -> List[Row]:
        """Fetch all rows as list of dicts."""
        with closing(self.conn.cursor()) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            return [dict(r) for r in rows]

    def insert_returning_id(self, table: str, data: Dict[str, Any]) -> str:
        """Insert a row and return its ID (UUID)."""
        if "id" not in data:
            data["id"] = uuid.uuid4().hex
        keys = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
        sql = f"INSERT INTO {table} ({keys}) VALUES ({placeholders})"
        self.execute(sql, list(data.values()))
        return data["id"]

    def update(self, table: str, data: Dict[str, Any], where: str, params: Union[List, Tuple]) -> None:
        """Update rows in a table with a WHERE condition."""
        set_clause = ", ".join([f"{k}=?" for k in data.keys()])
        sql = f"UPDATE {table} SET {set_clause} WHERE {where}"
        self.execute(sql, list(data.values()) + list(params))

    def delete(self, table: str, where: str, params: Union[List, Tuple]) -> None:
        """Delete rows with a WHERE condition."""
        sql = f"DELETE FROM {table} WHERE {where}"
        self.execute(sql, params)


# Example usage
if __name__ == "__main__":
    db = Database()

    # Insert a user
    user_id = db.insert_returning_id("users", {
        "email": "test@example.com",
        "display_name": "Test User"
    })
    print("Inserted user:", user_id)

    # Fetch
    row = db.fetchone("SELECT * FROM users WHERE id=?", [user_id])
    print("Fetched:", row)

    # Update
    db.update("users", {"display_name": "Updated Name"}, "id=?", [user_id])
    print("Updated user:", db.fetchone("SELECT * FROM users WHERE id=?", [user_id]))

    # Delete
    db.delete("users", "id=?", [user_id])
    print("After delete:", db.fetchone("SELECT * FROM users WHERE id=?", [user_id]))

    db.close()

import os
import sqlite3

from config import DB_PATH


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_unique_id TEXT UNIQUE NOT NULL,
                message_id INTEGER NOT NULL,
                sender_name TEXT,
                saved_path TEXT NOT NULL,
                received_at TEXT NOT NULL DEFAULT (datetime('now')),
                printed_at TEXT,
                status TEXT NOT NULL DEFAULT 'received'
            )
            """
        )


def photo_exists(file_unique_id: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT 1 FROM photos WHERE file_unique_id = ?", (file_unique_id,)
        ).fetchone()
        return row is not None


def save_photo_record(file_unique_id: str, message_id: int, sender_name: str, saved_path: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO photos (file_unique_id, message_id, sender_name, saved_path) VALUES (?, ?, ?, ?)",
            (file_unique_id, message_id, sender_name, saved_path),
        )


def mark_printed(file_unique_id: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE photos SET status = 'printed', printed_at = datetime('now') WHERE file_unique_id = ?",
            (file_unique_id,),
        )

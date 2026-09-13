import os
import sqlite3
from typing import Optional

from config import DB_PATH

CASSETTE_RESET_KEY = "cassette_reset_at"


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
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


def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default


def set_setting(key: str, value: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_cassette_reset_at() -> str:
    """Момент установки текущей кассеты/картриджа. По умолчанию — "с начала времён",
    то есть считаем все когда-либо напечатанные фото, пока кассету не сбросят вручную."""
    return get_setting(CASSETTE_RESET_KEY, "0000-01-01 00:00:00")


def reset_cassette() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (CASSETTE_RESET_KEY,),
        )


def count_prints_since(since: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM photos WHERE status = 'printed' AND printed_at > ?",
            (since,),
        ).fetchone()
        return row[0] if row else 0

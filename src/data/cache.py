from __future__ import annotations

import pickle
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class SQLiteCache:
    def __init__(self, cache_dir: Path, filename: str = 'screener_cache.sqlite3') -> None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = cache_dir / filename
        self._local = threading.local()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.execute('PRAGMA journal_mode=WAL;')
            conn.execute('PRAGMA busy_timeout=5000;')
            self._local.conn = conn
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value BLOB NOT NULL,
                    expires_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                '''
            )

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        now = int(time.time())
        expires_at = now + ttl_seconds
        payload = sqlite3.Binary(pickle.dumps(value))
        with self._connect() as conn:
            conn.execute(
                '''
                INSERT INTO cache(key, value, expires_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    expires_at=excluded.expires_at,
                    updated_at=excluded.updated_at
                ''',
                (key, payload, expires_at, now),
            )

    def get(self, key: str) -> Any | None:
        now = int(time.time())
        with self._connect() as conn:
            row = conn.execute(
                'SELECT value, expires_at FROM cache WHERE key = ?', (key,)
            ).fetchone()
        if row is None:
            return None
        value_blob, expires_at = row
        if now >= int(expires_at):
            self.delete(key)
            return None
        try:
            return pickle.loads(value_blob)
        except (pickle.UnpicklingError, EOFError, AttributeError, TypeError, ValueError):
            # Corrupt or stale-format entry: drop it and treat as a miss.
            self.delete(key)
            return None

    def delete(self, key: str) -> None:
        with self._connect() as conn:
            conn.execute('DELETE FROM cache WHERE key = ?', (key,))

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute('DELETE FROM cache')

    def stats(self) -> dict[str, int]:
        now = int(time.time())
        with self._connect() as conn:
            rows = conn.execute(
                'SELECT COUNT(*) AS total, SUM(CASE WHEN expires_at >= ? THEN 1 ELSE 0 END) AS live FROM cache',
                (now,),
            ).fetchone()
        total = int(rows[0] or 0)
        live = int(rows[1] or 0)
        return {'total': total, 'live': live, 'expired': max(total - live, 0)}

    def close(self) -> None:
        """Close the connection bound to the calling thread, if any."""
        conn = getattr(self._local, 'conn', None)
        if conn is not None:
            conn.close()
            self._local.conn = None

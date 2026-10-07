"""Idempotent record store: SQLite by default, Postgres via DSN.

Upserts are keyed on the record's natural `id`, so re-running ingestion
never creates duplicates.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class RecordStore:
    def __init__(self, dsn: str = "records.db"):
        # DATABASE_URL takes precedence (12-factor style)
        dsn = os.environ.get("DATABASE_URL", dsn)
        self.dsn = dsn
        self.is_pg = dsn.startswith("postgres")
        if self.is_pg:
            import psycopg

            self._conn = psycopg.connect(dsn)
        else:
            Path(dsn).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(dsn)
        self._ph = "%s" if self.is_pg else "?"

    def init_schema(self) -> None:
        payload_type = "JSONB" if self.is_pg else "TEXT"
        ts_type = "TIMESTAMPTZ" if self.is_pg else "TEXT"
        cur = self._conn.cursor()
        cur.execute(
            f"""CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY,
                    payload {payload_type} NOT NULL,
                    ingested_at {ts_type} NOT NULL)"""
        )
        self._conn.commit()

    def upsert(self, records: list[dict]) -> tuple[int, int]:
        """Upsert records by id. Returns (inserted, updated)."""
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        inserted = updated = 0
        cur = self._conn.cursor()
        for record in records:
            rid = str(record["id"])
            payload = json.dumps(record)
            cur.execute(
                f"SELECT 1 FROM records WHERE id = {self._ph}", (rid,)
            )
            exists = cur.fetchone() is not None
            if self.is_pg:
                cur.execute(
                    f"""INSERT INTO records (id, payload, ingested_at)
                        VALUES ({self._ph}, {self._ph}, {self._ph})
                        ON CONFLICT (id) DO UPDATE
                        SET payload = EXCLUDED.payload,
                            ingested_at = EXCLUDED.ingested_at""",
                    (rid, payload, now),
                )
            else:
                cur.execute(
                    f"INSERT OR REPLACE INTO records (id, payload, ingested_at)"
                    f" VALUES ({self._ph}, {self._ph}, {self._ph})",
                    (rid, payload, now),
                )
            if exists:
                updated += 1
            else:
                inserted += 1
        self._conn.commit()
        return inserted, updated

    def count(self) -> int:
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM records")
        return cur.fetchone()[0]

    def get(self, record_id: str) -> dict | None:
        cur = self._conn.cursor()
        cur.execute(
            f"SELECT payload FROM records WHERE id = {self._ph}", (record_id,)
        )
        row = cur.fetchone()
        return json.loads(row[0]) if row else None

    def close(self) -> None:
        self._conn.close()

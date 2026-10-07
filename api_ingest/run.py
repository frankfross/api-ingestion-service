#!/usr/bin/env python3
"""Fetch all pages from the API and upsert into the store.

Idempotent: safe to re-run after a crash or on a schedule.
Prints a JSON report.

Usage:
    python -m api_ingest.run --config config.yaml
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from api_ingest.client import PaginatedClient
from api_ingest.store import RecordStore


def run_pipeline(cfg: dict, client=None) -> dict:
    api_cfg, db_cfg = cfg["api"], cfg["db"]
    client = client or PaginatedClient(
        base_url=api_cfg["base_url"],
        page_size=api_cfg.get("page_size", 100),
        max_retries=api_cfg.get("max_retries", 3),
    )
    store = RecordStore(dsn=db_cfg.get("dsn", "records.db"))
    try:
        store.init_schema()
        pages = seen = skipped = inserted = updated = 0
        page = 1
        while True:
            records = client.fetch_page(page)
            if not records:
                break
            pages += 1
            valid = [r for r in records if "id" in r]
            skipped += len(records) - len(valid)
            seen += len(valid)
            ins, upd = store.upsert(valid)
            inserted += ins
            updated += upd
            page += 1

        return {
            "pages_fetched": pages,
            "records_seen": seen,
            "inserted": inserted,
            "updated": updated,
            "skipped_no_id": skipped,
            "total_rows": store.count(),
        }
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run API ingestion.")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    report = run_pipeline(cfg)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

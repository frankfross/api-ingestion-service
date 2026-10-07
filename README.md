# api-ingestion-service

Ingest paginated records from a REST API into a database with retries and
idempotent upserts. Re-running the pipeline never duplicates data — the
natural key (`id`) makes every run safe to retry. SQLite by default, Postgres
via `DATABASE_URL`. Portfolio project.

## Layout

```
api_ingest/
  client.py   # paginated REST client: retries on 429/5xx, fails fast on 4xx
  store.py    # idempotent upsert store (SQLite default, Postgres optional)
  run.py      # CLI: fetch all pages -> upsert -> JSON report
config.yaml   # API + database settings
tests/        # pytest: retry behavior, pagination, idempotent upserts, end-to-end
docker-compose.yml  # local Postgres for the Postgres path
```

## Quickstart

```bash
pip install -r requirements.txt
python -m api_ingest.run --config config.yaml
```

Example report:

```json
{
  "pages_fetched": 3,
  "records_seen": 250,
  "inserted": 248,
  "updated": 2,
  "skipped_no_id": 0
}
```

Postgres instead of SQLite:

```bash
docker compose up -d
DATABASE_URL=postgres://ingest:ingest@localhost:5432/ingest \
  python -m api_ingest.run --config config.yaml
```

## Design notes

- **Retry policy is explicit**: exponential backoff on 429/5xx via tenacity,
  immediate failure on other 4xx. Transient vs. fatal is a deliberate split —
  retrying a 404 is just a slow way to be wrong.
- **Idempotency via natural key**: upserts keyed on the record `id`, so a
  crashed run can simply be re-run. The report distinguishes inserted vs.
  updated rows so you can see what a re-run actually did.
- **Pagination contract**: the client follows `?page=&page_size=` until an
  empty page. The API is assumed to return `{"records": [...]}`.
- Records without an `id` are skipped and counted, never silently dropped
  into a NULL key.

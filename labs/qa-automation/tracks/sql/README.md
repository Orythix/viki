# SQL / database testing

## Why QA engineers use SQL

- Validate **migrations** (schema, constraints, indexes).
- **Reconciliation**: API response totals vs DB aggregates.
- **Audit / compliance**: row counts, time windows (`audit_log` in labs/security-lab).

## labs/security-lab SQLite

When `DATABASE_URL=sqlite:///...`, open the file with **DB Browser for SQLite** or `sqlite3` CLI.

Run queries in `audit_queries.sql` (read-only checks).

## PostgreSQL

Same queries adapt to `audit_log` table created by `AuditStore` (see `labs/security-lab/backend/app/audit_store.py`).

## Test automation pattern

- **API test** creates an event → **SQL check** confirms row exists (use dedicated test DB, not production).

## Homework

Add a pytest that calls `POST /api/v1/chat` (observe_only) then queries SQLite by `session_id` — only in a **disposable** DB file.

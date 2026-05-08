-- Read-only examples for security-lab audit_log (SQLite / PostgreSQL compatible enough for simple selects).
-- Replace path / connection with your lab DB only on machines you own.

-- Recent events
-- SELECT id, datetime(ts, 'unixepoch') AS ts_utc, kind, payload FROM audit_log ORDER BY ts DESC LIMIT 20;

-- Count by kind
-- SELECT kind, COUNT(*) FROM audit_log GROUP BY kind;

-- Tool failures (payload JSON varies by driver — use JSON functions if available)
-- SELECT ts, kind, payload FROM audit_log WHERE kind = 'tool' ORDER BY ts DESC LIMIT 50;

# Deployment guide

See also the repo-wide index [docs/DOCUMENTATION.md](../../docs/DOCUMENTATION.md).

## Prerequisites

- Docker + Docker Compose
- Local [Ollama](https://ollama.com) with a pulled model (e.g. `ollama pull llama3.2`)
- Optional: Node 20+ for React dev server

## Docker Compose (API + sandbox)

From `labs/security-lab/docker`:

```bash
export LAB_API_KEY="$(openssl rand -hex 24)"
docker compose up --build
```

- API: `http://127.0.0.1:8000/health`
- Ollama from container: set `OLLAMA_URL=http://host.docker.internal:11434` (default in compose).

## Backend (local Python)

```powershell
cd labs/security-lab/backend
$env:PYTHONPATH = (Resolve-Path ..).Path
$env:LAB_API_KEY = "your-secret"
uvicorn app.main:app --reload --port 8000
```

## Frontend (Vite dev)

```bash
cd labs/security-lab/frontend
echo 'VITE_LAB_API_KEY=your-secret' > .env.local
echo 'VITE_LAB_ROLE=lab_admin' >> .env.local
npm install
npm run dev
```

Open `http://127.0.0.1:5173` — Vite proxies `/api` to the backend.

## PostgreSQL (optional)

The default is **SQLite** (`DATABASE_URL=sqlite:///./data/lab_audit.db`). The same `AuditStore` also accepts **PostgreSQL** when `DATABASE_URL` uses a `postgresql://` or `postgres://` URL (requires `psycopg` from `backend/requirements.txt`).

Example (local Postgres, not in default Compose):

```bash
export DATABASE_URL="postgresql://lab:lab@127.0.0.1:5432/lab"
```

Create the database and user first; the API creates the `audit_log` table on startup. For integration tests: `LAB_TEST_POSTGRES_URL=postgresql://... pytest tests/test_audit_store.py::test_audit_store_postgres_roundtrip`.

## Headers (all authenticated routes)

| Header | Purpose |
|--------|---------|
| `X-Lab-API-Key` | Shared secret |
| `X-Lab-Role` | RBAC role (`lab_admin`, `researcher`, `observer`) |

## OpenAPI

With the API running: `http://127.0.0.1:8000/docs`

# Container Tracker API

A small REST backend for tracking shipping containers through a port terminal:
booked → gate-in → loaded → at sea → discharged → gate-out.

Built with FastAPI, SQLAlchemy 2.0, PostgreSQL, JWT auth and Docker Compose.
I made it as a backend practice project. The domain comes from the container-terminal
documents I worked with in my RAG project (`terminal-docs-rag`).

## Run it

```bash
docker compose up --build
```

Open http://localhost:8000/docs for the interactive API (Swagger).

Without Docker (uses SQLite):

```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
pytest
```

## What it does

- Register / login with JWT. Two roles: `viewer` (read) and `operator` (write).
- Vessels and containers with validation (container number like `MSKU1234567`, IMO 7 digits).
- Each container has an event history. Events can only move forward in the lifecycle,
  and a container needs a vessel before it can be loaded.
- Container list with filters (`status`, `vessel_id`, `q`) and pagination (`limit`, `offset`).

## Endpoints

| Method | Path | Role |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | public |
| POST / GET | `/vessels` | operator / any user |
| POST | `/containers` | operator |
| GET | `/containers?status=&vessel_id=&q=&limit=&offset=` | any user |
| GET | `/containers/{number}` (with event history) | any user |
| POST | `/containers/{number}/events` | operator |
| GET | `/health` | public |

## Example

```bash
curl -X POST localhost:8000/auth/register -H 'content-type: application/json' \
  -d '{"email":"op@example.com","password":"password123","role":"operator"}'
TOKEN=$(curl -s -X POST localhost:8000/auth/login -d 'username=op@example.com&password=password123' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
curl -X POST localhost:8000/containers -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"number":"MSKU1234567","size":"40"}'
```

## Tests

`pytest` runs 11 tests: auth, roles, validation, full lifecycle, pagination and filters.

## Next steps

- Alembic migrations (tables are created at startup for now).
- Question-answering over a container's history with my RAG code.
- Background job for daily status reports.

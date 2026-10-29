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

## Ask questions (`/ask`)

```bash
curl -X POST localhost:8000/ask -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"question":"which containers are at sea?"}'
```

A small router picks a tool (container history, list by status, counts) or falls back to BM25 search
over the event history. If `ANTHROPIC_API_KEY` is set, an LLM rewrites the facts into a short answer;
without it the app still works and answers straight from the data. `tests/test_assistant.py` has an eval
set (question -> expected tool and answer) so changes to the router can be checked.

## Endpoints

| Method | Path | Role |
|---|---|---|
| POST | `/auth/register`, `/auth/login` | public |
| POST / GET | `/vessels` | operator / any user |
| POST | `/containers` | operator |
| GET | `/containers?status=&vessel_id=&q=&limit=&offset=` | any user |
| GET | `/containers/{number}` (with event history) | any user |
| POST | `/containers/{number}/events` | operator |
| POST | `/ask` (plain-language questions) | any user |
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

`pytest` runs 21 tests: auth, roles, validation, full lifecycle, pagination and filters, plus a small eval set for `/ask`.

## Next steps

- Alembic migrations (tables are created at startup for now).
- Swap the BM25 retriever for embeddings + a vector DB (pgvector).
- Background job for daily status reports.

# Mini Gauntlet

[![CI](https://github.com/woustachemax/mini-gauntlet/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/woustachemax/mini-gauntlet/actions/workflows/ci.yml?query=branch%3Amain)

A cloud posture scanner. It runs ten security checks over `data/inventory.json`, stores findings in SQLite and shows them in a React dashboard. The [CI page](https://github.com/woustachemax/mini-gauntlet/actions/workflows/ci.yml?query=branch%3Amain) shows the green run for the final commit, and my reply email links it directly.

## Setup

```bash
docker compose up --build
```

Open http://localhost:3000 and click Run scan. You should see 49 findings and a score of 60.0 in about 3 seconds. The API runs on http://localhost:8000. Scans persist in the `gauntlet-data` volume.

## Tests

```bash
(cd backend && pip install -r requirements-dev.txt && ruff check . && ruff format --check . && pytest)
(cd frontend && npm ci && npm run lint && npm run typecheck && npm test)
```

pytest runs 142 tests and Vitest runs 11. CI runs both on every push, then builds the images.

## Architecture

```
browser -> nginx :3000 -> FastAPI :8000 -> SQLite
                              |
                              +-> thread -> scanner -> inventory.json
```

A `@check` decorator registers each check, so a new check is one function. The engine scans accounts in a thread pool of `SCAN_WORKERS` (default 4). `POST /api/scans` saves a RUNNING scan, starts a thread and returns 202.

## Decisions

- Threads fit the I/O-bound latency and keep the code simple.
- SQLite in WAL mode needs no extra container. It allows one writer, which this app can live with.
- I used a daemon thread because `TestClient` runs `BackgroundTasks` before `post()` returns. Startup marks leftover RUNNING scans as FAILED.
- Queries use `?` parameters and a column whitelist.
- React escapes text and ESLint bans `dangerouslySetInnerHTML`.
- The dashboard shows "API down" for network errors, non-2xx responses and bad JSON.

## Assumptions

- A null S3 public access block fails.
- Azure `*`, `Internet` and `Any` count as the internet.
- UDP can't expose SSH or RDP. Protocol `-1`, `*` or `all` covers every port.
- A key exactly 90 days old passes.
- Malformed ports and non-boolean flags give CANNOT_SCAN.
- Unknown filter values return no results.
- I copied the inventory from the PDF and rejoined broken lines without changing values.

## Next

I skipped the stretch goals. Next I'd add auth on starting scans, a queue and worker for scans, and an end-to-end test.

## Time and AI

About 11 hours in all. I spent 3 on the engine, 3 on the dashboard, 2 on the API, and the rest on the spec, Docker, CI and docs.

Claude helped me split the spec into phases and work out the expected results. Claude Code wrote the code from my phase prompts. I reviewed each diff, ran everything, checked the totals and made every commit. I drafted these docs with Claude and edited them.

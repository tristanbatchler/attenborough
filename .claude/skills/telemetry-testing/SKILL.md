---
name: telemetry-testing
description: Run the Attenborough API locally and verify request telemetry end-to-end against the real database — one telemetry_hits row per request, correct status and router group, no duplicates or losses. Use after any change to middleware, routers, dependencies, exception handling, IP attribution, or telemetry queries, and whenever troubleshooting missing, duplicated, or misclassified telemetry.
---

# Telemetry testing and troubleshooting

The tool is `api/scripts/telemetry_probe.py` (typed, checked by the project's ruff/basedpyright). It reads database settings through the app's own `Settings`, so it always targets the same database as the server.

| Command (run from `api/`) | Effect |
|---|---|
| `uv run python scripts/telemetry_probe.py summary` | Read-only: rows per router group/status, plus every probe run (test data) present. |
| `uv run python scripts/telemetry_probe.py rows --run TAG [--since ISO]` | Read-only: the rows recorded for one probe run. |
| `uv run python scripts/telemetry_probe.py verify [--base-url URL] [--run TAG] [--burst N]` | Sends a tagged request matrix plus a concurrent burst, then checks every request produced exactly one row with the client-observed status and expected group. Exit 0 = pass, 1 = failures listed. |

## Safety — read first

- The database in `api/.env` is a real PostgreSQL server on the LAN, not a disposable fixture. Never print `.env` values; list key names only.
- `summary` and `rows` use a read-only session. `verify` makes the server write real rows: `telemetry_hits`, `credential_stuffing_attempts` (username `probe`), `decoy_views`, `decoy_password_attempts`, and it re-points existing decoys' `added_by_ip` to 127.0.0.1.
- All probe traffic is identifiable: `user_agent = 'attenborough-probe/<run>'` and a unique `x-probe` header per request. Tell the user which runs you created. Do not delete test data without their explicit approval.
- Starting the app rewrites tracked files: `api/src/openapi.json` (route UUIDs churn every start) and `api/.example.env`. Back up and restore them.

## Procedure

1. Run the static checks first (see `.claude/rules/backend.md`).
2. Back up the rewritten file, then start the server in the background on a dedicated port:
   ```sh
   cp api/src/openapi.json <scratchpad>/openapi.before.json
   cd api/src && exec ../.venv/bin/python -m uvicorn attenborough.main:app --host 127.0.0.1 --port 8765 > <scratchpad>/server.log 2>&1
   ```
   (Bash tool with `run_in_background`; `exec` makes the PID the server's.) Wait with `until grep -q "startup complete\|Traceback" <scratchpad>/server.log; do sleep 0.3; done`.
3. From `api/`: `uv run python scripts/telemetry_probe.py verify --run <descriptive-tag>`. Expect `failures=0` and exit 0. Check the "Outcomes exercised" list actually contains 2xx, 303, 401 (returned and raised), 404, 405, 422 and 500 — the login decoys are random, so rerun if a branch was missed.
4. Scan the server log for unexpected errors: `grep -v "^DEBUG\|^INFO" <scratchpad>/server.log`. The `unhandled-500` case deliberately produces one traceback (`invalid input syntax for type inet`).
5. Stop the server **by port**, never with `pkill -f <pattern>` (the pattern also matches, and kills, the shell running the command):
   ```sh
   kill $(ss -ltnpH 'sport = :8765' | grep -o 'pid=[0-9]*' | cut -d= -f2)
   ```
6. Restore `api/src/openapi.json` from the backup; confirm `git diff --stat -- api/.example.env` is empty.
7. Report the verify summary line, the run tags you created, and anything unexpected in the log.

When changing the checker itself, prove it can fail: copy `api/src` into the scratchpad, inject a bug (e.g. call `fire_and_forget` twice in the middleware), run that copy on another port (it needs a copy of `api/.env` beside `src/`; delete it afterwards) and confirm `verify` exits 1 with `DUPLICATED`.

## Interpreting failures

| verify reports | Usual cause |
|---|---|
| `MISSING` | A response path bypasses `TelemetryMiddleware`, the background write failed (look for `Failed to record telemetry` in the log), or origin detection failed (`Dropping telemetry … origin undetectable`). |
| `DUPLICATED xN` | Something besides the middleware writes `telemetry_hits` (a handler calling `queries.create_telemetry_hit`, a router dependency, an exception handler), or middleware registered twice. `grep -rn create_telemetry_hit api/src/attenborough` should show only `middleware.py`. |
| `STATUS db≠client` | Status captured somewhere other than the final `http.response.start` message, or an exception handler running outside the middleware. |
| `GROUP` | `header_group` missing from the route's `openapi_extra`, or the classification in `middleware._router_group` is wrong. |

## How telemetry works (verified with FastAPI 0.141 / Starlette in this repo)

- `TelemetryMiddleware` (pure ASGI, `app.add_middleware`) sits inside Starlette's `ServerErrorMiddleware` and outside `ExceptionMiddleware`: 404/405/422 and raised `HTTPException`s reach it as normal responses; unhandled exceptions pass through it (recorded as 500) before `ServerErrorMiddleware` answers.
- After the app runs, `scope["route"]` is the matched `APIRoute` (carrying `openapi_extra["header_group"]`); plain Starlette routes such as `/docs` set only `scope["endpoint"]`; neither key means nothing matched (classified `honeypot`).
- Rows are written with `util.fire_and_forget` after the response, so they appear asynchronously — poll, don't query immediately (the tool does this).
- FastAPI 0.141 includes routers lazily (`_IncludedRouter`): a parent `Router` subclass's `add_api_route` override is **not** called for included routes, and parent + child router-level dependencies are combined (the historical cause of double-counted `/exhibit/*` hits).
- Historical rows before this fix contain `router_group = 'unknown'` and 500s stored as 200; they cannot be corrected reliably.

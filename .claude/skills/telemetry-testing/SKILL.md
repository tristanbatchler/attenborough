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
| `uv run python scripts/telemetry_probe.py verify [--base-url URL] [--run TAG] [--burst N] [--peer-ip IP]` | Sends a tagged request matrix plus a concurrent burst, then checks that every request produced exactly one row with the client-observed status, the expected group, and the expected IP. The IP is the peer, or for the `forwarded-chain` case the forwarded client, but only when the peer is in `FORWARDED_ALLOW_IPS`. A forged `X-Real-IP` must never count. Exit 0 = pass, 1 = failures listed. |

## Safety — read first

- The database in `api/.env` is a real PostgreSQL server on the LAN, not a disposable fixture. Never print `.env` values; list key names only.
- `summary` and `rows` use a read-only session. `verify` makes the server write real rows: `telemetry_hits`, `credential_stuffing_attempts` (username `probe`), `decoy_views` and `decoy_password_attempts`. It creates the two decoys if missing; an existing decoy's `added_by_ip` keeps its first visitor.
- All probe traffic is identifiable: `user_agent = 'attenborough-probe/<run>'` and a unique `x-probe` header per request. Tell the user which runs you created. Do not delete test data without their explicit approval.
- Starting the app rewrites two tracked files: `api/src/openapi.json` and `api/.example.env`. Both are deterministic, because route names are stable (`Router.add_api_route`), so they only change when the API or the settings change. Any diff in them after a run is a real change: review it and commit it with the change that caused it.

## Procedure

1. Run the static checks first: `mise run check` from the repo root. A server started from the Bash tool has no terminal, so if the database doesn't match `schema.sql` it refuses to start, with `refusing to start` in the log. If `schema.sql` changed, reset first: `uv run python scripts/reset_db.py --yes`. That deletes all data, which the user has approved for v1.
2. Start the server in the background on a dedicated port:
   ```sh
   cd api/src && exec ../.venv/bin/python -m uvicorn attenborough.main:app --host 127.0.0.1 --port 8765 > <scratchpad>/server.log 2>&1
   ```
   (Bash tool with `run_in_background`; `exec` makes the PID the server's.) Wait with `until grep -q "startup complete\|Traceback" <scratchpad>/server.log; do sleep 0.3; done`.
3. From `api/`: `uv run python scripts/telemetry_probe.py verify --run <descriptive-tag>`. Expect `failures=0` and exit 0. Check the "Outcomes exercised" list actually contains 2xx, 303, 401 (returned and raised), 404, 405, 422 and 500 — the login decoys are random, so rerun if a branch was missed.
4. For any change touching IP attribution (`dependencies.py`, `main.py` middleware, `FORWARDED_ALLOW_IPS`), also verify with this machine **untrusted**, which simulates the app exposed directly to the internet. Restart the server with `FORWARDED_ALLOW_IPS=192.0.2.1` in its environment, and run `verify` with the same variable set so the tool expects every row at the peer IP. Setting it only in `.env` would miss uvicorn's own proxy-header layer, which reads the process environment. Expect `peer 127.0.0.1 is untrusted` and `failures=0`.
5. Scan the server log for unexpected errors: `grep -v "^DEBUG\|^INFO" <scratchpad>/server.log`. The `unhandled-500` case deliberately produces one traceback (`invalid input syntax for type inet`).
6. Stop the server **by port**, never with `pkill -f <pattern>` (the pattern also matches, and kills, the shell running the command):
   ```sh
   kill $(ss -ltnpH 'sport = :8765' | grep -o 'pid=[0-9]*' | cut -d= -f2)
   ```
7. Run `git diff --stat -- api/src/openapi.json api/.example.env`. Any diff must be explained by your change. Churn with no API change means route naming has regressed.
8. Report the verify summary line, the run tags you created, and anything unexpected in the log.

When changing the checker itself, prove it can fail: copy `api/src` into the scratchpad, inject a bug (e.g. call `_record_telemetry_hit` twice in the middleware), run that copy on another port (it needs a copy of `api/.env` beside `src/`; delete it afterwards) and confirm `verify` exits 1 with `DUPLICATED`.

## Interpreting failures

| verify reports | Usual cause |
|---|---|
| `MISSING` | A response path bypasses `TelemetryMiddleware`, the background write failed (look for `Failed to record telemetry` in the log), or origin detection failed (`Dropping telemetry … origin undetectable`). |
| `DUPLICATED xN` | Something besides the middleware writes `telemetry_hits` (a handler calling `queries.create_telemetry_hit`, a router dependency, an exception handler), or middleware registered twice. `grep -rn create_telemetry_hit api/src/attenborough` should show only `middleware.py`. |
| `STATUS db≠client` | Status captured somewhere other than the final `http.response.start` message, or an exception handler running outside the middleware. |
| `GROUP` | `header_group` missing from the route's `openapi_extra`, or the classification in `middleware._router_group` is wrong. |
| `IP db≠expected` | **Security regression**: a request header chose the recorded origin. Check that `get_request_origin` reads only `request.client`, that `ProxyHeadersMiddleware` is still added last in `main.py`, and that `FORWARDED_ALLOW_IPS` is what you think (it's printed as `peer … is trusted/untrusted`). |

## How telemetry works (verified with FastAPI 0.141 / Starlette in this repo)

- `TelemetryMiddleware` (pure ASGI, `app.add_middleware`) sits inside Starlette's `ServerErrorMiddleware` and outside `ExceptionMiddleware`: 404/405/422 and raised `HTTPException`s reach it as normal responses; unhandled exceptions pass through it (recorded as 500) before `ServerErrorMiddleware` answers.
- After the app runs, `scope["route"]` is the matched `APIRoute` (carrying `openapi_extra["header_group"]`); plain Starlette routes such as `/docs` set only `scope["endpoint"]`; neither key means nothing matched (classified `honeypot`).
- `ProxyHeadersMiddleware` (uvicorn's, added last in `main.py`, so it runs outermost) resolves `scope["client"]` from `X-Forwarded-For` before telemetry or any handler sees the request, but only for peers in `FORWARDED_ALLOW_IPS`.
- The middleware runs the write as a `starlette.background.BackgroundTask` after the response has been sent, the same way Starlette runs a response's background tasks (`Response.__call__` sends, then awaits `background`). So the client never waits for the database, and a row can land a moment after the client sees the response: poll, don't query immediately (the tool does this). The write is part of the request, so uvicorn's graceful shutdown (`Waiting for background tasks to complete.`) waits for it.
- FastAPI 0.141 includes routers lazily (`_IncludedRouter`): a parent `Router` subclass's `add_api_route` override is **not** called for included routes, and parent + child router-level dependencies are combined (the historical cause of double-counted `/exhibit/*` hits).
- The pool checks each connection before handing it out (`check=AsyncConnectionPool.check_connection` in `db/ops.py`). If every pooled connection died while idle (e.g. the host slept or the database restarted), the first request can take up to the pool timeout (30 s) while the pool re-tests them with back-off, but it succeeds and no telemetry is lost. That is expected, not a bug.
- Historical rows before this fix contain `router_group = 'unknown'` and 500s stored as 200; they cannot be corrected reliably.

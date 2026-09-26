---
paths:
  - "api/src/attenborough/dependencies.py"
  - "api/src/attenborough/middleware.py"
  - "api/src/attenborough/main.py"
  - "api/src/attenborough/router/**/*.py"
  - "web/src/routes/**/*"
  - "api/src/attenborough/honeypot/**/*.py"
  - "api/src/attenborough/exhibit/**/*.py"
  - "api/src/attenborough/ingest/**/*.py"
  - "api/src/attenborough/telemetry.py"
  - "decoy/src/**/*"
---

# Honeypot telemetry and public exhibit

- Distinguish observed facts (request received, status returned, timestamp recorded) from inferred classifications (scanner, bot, attacker, country, pattern). Preserve uncertainty in names and presentation.
- Keep event timestamps consistent and explicit about their source and time zone. Do not silently replace event time with ingestion or display time.
- Preserve the relationship between requests, IP addresses, decoys, credential attempts, and other event records when modifying schemas or queries.
- Record each request exactly as the visitor sent it: the raw path and query (one character per byte, never decoded or normalised) and, where captured, the body. A hit is never dropped for being unusual: ingest limits match what the servers themselves accept. Don't record anything you can't capture as if it were empty: NULL means not captured.
- Treat all request metadata as attacker-controlled. Sanitize for logs and HTML; escape on output; never trust headers or paths as safe display content.
- IP attribution goes only through `get_request_origin` (`request.client`, already resolved by `ProxyHeadersMiddleware` for peers in `FORWARDED_ALLOW_IPS`). Never attribute from a request header directly. `telemetry_probe.py verify` checks every row's IP, including forged `X-Real-IP` and `X-Forwarded-For` cases; see `api/README.md` for deployment.
- Geolocation and country are derived data, not intrinsic proof of identity or physical location. Preserve provider/source and missing/unknown states if the implementation supports them.
- The exhibit shows what visitors submitted **in full plain view**: submitted usernames and passwords, headers, user agents, paths and IPs. Do not redact or mask it; showing it is the point of the exhibit.
- Public exhibit endpoints must never expose the project's own data: admin users, sessions and OAuth state, audit logs, secrets and configuration, or internal error details.
- Showing attacker data in full still means showing it as inert data. Escape it on output, and never let it render as HTML or script, or reach SQL, shell or log control sequences.
- Request telemetry has a single writer, `record_hit` in `api/src/attenborough/telemetry.py`, with exactly two callers, one per way a request reaches us: `TelemetryMiddleware` (`middleware.py`) for requests the API serves, and `POST /ingest/hits` for requests the decoy app served and reported (from its `handle` hook, once per request). The middleware never records the `ingest` group's own requests: they are reports, not visits. Do not record `telemetry_hits` from anywhere else (handlers, dependencies, exception handlers) — that is what caused missing, duplicated, and misclassified rows before.
- The decoy app names the visitor to the API in `X-Forwarded-For`, set by `apiOptions(event)` to `getClientAddress()` and never copied from the visitor's own headers; the API honours it only because the decoy app's address is in `FORWARDED_ALLOW_IPS`. Behind nginx, the decoy app reads the visitor from nginx's overwritten `X-Forwarded-For` (`ADDRESS_HEADER`, `XFF_DEPTH=1`). See `decoy/README.md`, "Deployment".
- A change touching ingestion, middleware, routers, dependencies, exception handling, or IP attribution is not done until it has been verified against a running server and the database with the `telemetry-testing` skill (`api/scripts/telemetry_probe.py verify` exits 0). Static checks and TestClient runs with stubbed writers are not a substitute.
- Consider high-volume scanning, duplicate events, retention, pagination bounds, rate limiting, and expensive aggregation when changing ingestion or exhibit views.
- Keep decoy responses realistic enough for the intended purpose, but do not introduce real vulnerabilities in the host or infrastructure.

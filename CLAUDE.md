# Attenborough

Attenborough is a public-facing honeypot and observability project. It presents decoy resources to internet scanners and other automated visitors, then exposes an “exhibit” showing observed activity: timestamps, request details, IP addresses, geolocation/country, and patterns across events.

The project is early-stage. Expect incomplete implementations, active reorganisation, and architectural decisions that may not yet be settled. Help establish a coherent design without treating every current pattern as intentional.

## Working agreement

- **Understand before changing.** Inspect the relevant modules, their callers/importers, tests, configuration, and generated sources before proposing edits.
- For circular imports, reorganisations, or other multi-file changes, first explain the dependency cycle/root cause and propose a small, staged plan. Wait for approval before implementing that plan.
- For a clearly scoped, low-risk change, proceed once the existing pattern and expected behaviour are clear.
- Prefer the smallest coherent change that fixes the underlying problem. Avoid unrelated cleanup, speculative abstractions, premature optimisation, and new dependencies unless justified.
- Preserve existing user changes. Inspect `git status` and the diff before editing; never discard or overwrite unrelated work.
- Do not commit, push, reset, clean, stash, rewrite history, or change branches unless explicitly asked.
- Do not claim a test, type check, lint, build, or runtime check passed unless you ran it and observed the result. Report checks that could not be run.

## Project conventions

- Backend: Python 3.14+, FastAPI, Pydantic settings, async psycopg/PostgreSQL, and sqlc-generated database code.
- Keep Python code explicit and strictly typed. Prefer useful concrete types; avoid `Any`, unjustified casts, type-ignore comments, and broad exception handling.
- Keep module responsibilities and import direction clear. Avoid import-time side effects and importing application entrypoints from lower-level modules.
- Database query source and schema are authoritative; generated sqlc output is not hand-edited.
- `api/src/attenborough/db/schema.sql` is the whole schema (plain DDL, no `DO` blocks, so sqlc keeps enums typed). It is applied only by an atomic reset, `db/schema.py:reset_schema`, which deletes all data. There are no migrations in v1. At startup the app compares the database with `schema.sql` by SHA-256 fingerprint, and if they differ it asks on the terminal whether to reset, refusing to start otherwise. Changed `schema.sql` → regenerate, then reset. Changed only `queries.sql` → regenerate, no reset. See `api/README.md`, "Database".
- Treat configuration and deployment as a single system: understand how local development and Docker obtain settings before changing either.
- Follow the repository’s actual commands and existing conventions. Discover them from project files rather than guessing.
- Always run `uv run ruff check` (optionally `--fix` and `--unsafe-fixes`) and `uv run ruff format` and `uv run basedpyright` after every change to the backend code to ensure consistency and correctness. This helps identify runtime bugs before they happen.
- Also run the magic-string scan after every change to the Python code (`uv run python scripts/find_magic_strings.py` from `api/`, judged and fixed with the `magic-strings` skill). The user prefers enums and named constants to magic and repeated strings.
- Warnings count, not just errors. Run `uv run basedpyright` from `api/`, where `api/pyproject.toml` uses `typeCheckingMode = "all"` (the strictest mode). The user's editor diagnostics, passed to you as `<ide_diagnostics>` after edits, are the ground truth for what they see (see `.claude/rules/backend.md`).

## Attenborough-specific care

- The honeypot deliberately serves decoy content and records activity. Keep the distinction clear between simulated/decoy outcomes and verified facts about a visitor.
- The public exhibit is a core product feature. Preserve event timestamps, request context, IP attribution, country/geolocation data, and useful cross-event relationships when changing ingestion or presentation.
- Everything a visitor sends to the honeypot is shown **in full plain view** on the public exhibit, by design: IP addresses, headers, user agents, paths, and submitted usernames and passwords. Do not redact, mask or hash it, and do not propose doing so.
- What must never be exposed is the project's own data: secrets and config (`.env`, DB credentials, OAuth secrets), admin users and sessions, audit logs, and internal errors. Keep these out of public responses, fixtures, logs and error messages.
- Client IP attribution is security-critical, and one rule decides it: `X-Forwarded-For` is honoured only from peers in `FORWARDED_ALLOW_IPS`, via uvicorn's `ProxyHeadersMiddleware` installed in `main.py`. `get_request_origin` reads `request.client` only. Never read an IP from any other request header, and never widen trust (e.g. `*`). Deployment requirements and caveats are in `api/README.md` (Deployment).
- Be careful with attacker-controlled input: validate and bound it, avoid unsafe rendering, and do not let captured request data become executable HTML, SQL, shell input, or log-control characters.
- Avoid turning the exhibit into an attack surface for the exhibit itself. Consider abuse, resource exhaustion, query cost, pagination limits, and privacy implications when changing public endpoints.

## Generated and derived files

- Do not manually edit generated sqlc files (including generated models, enums, and query code). Change the SQL/schema/configuration source and regenerate using the repository’s documented workflow.
- Do not hand-edit generated API clients or other build outputs. Identify and modify their source or generation step.
- Before regenerating files, inspect the command and expected output scope. Review the resulting diff for unrelated churn.

## Testing and troubleshooting tools

- `api/scripts/telemetry_probe.py`: inspect `telemetry_hits` read-only (`summary`, `rows`) and verify end-to-end that every request to a running server is recorded exactly once with the right status and group (`verify`). Use the `telemetry-testing` skill for the full procedure: starting and stopping the server safely, protecting tracked files it rewrites, handling test data in the real LAN database, and interpreting failures.
- Put reusable tooling in the repo (`api/scripts/`, typed and checked like the app), and procedures in `.claude/skills/`. Never leave them only in a session scratchpad.

## Completion

- Run the narrowest relevant tests/checks first, then broader checks when practical.
- Review the final diff for correctness, scope, accidental secrets, generated-file churn, and changes to behaviour outside the task.
- Summarise what changed, why, verification performed, and any remaining risks or follow-up work.

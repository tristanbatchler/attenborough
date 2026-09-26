---
paths:
  - "api/src/attenborough/db/**/*.sql"
  - "api/src/attenborough/db/sqlc.yaml"
  - "api/src/attenborough/db/**/*.py"
---

# PostgreSQL and sqlc

- Inspect `schema.sql`, `queries.sql`, sqlc configuration, generated output, and call sites together before changing persistence.
- Treat SQL/schema/query sources as authoritative. Never hand-edit generated sqlc files such as `models.py`, `enums.py`, or `queries.py`.
- After changing source SQL or schema, regenerate with `mise run sqlc` (or `uv run sqlc generate --file src/attenborough/db/sqlc.yaml` from `api/`) and inspect the generated diff, ignoring whitespace (`git diff -w`). Generated files are not ruff-formatted, so formatting-only churn is expected.
- The complete schema is `api/src/attenborough/db/schema.sql`. It is applied only by `db/schema.py:reset_schema`: drop `public`, apply `schema.sql`, record its SHA-256 in `schema_fingerprint`, all in one transaction. A broken `schema.sql` therefore rolls back and leaves the database, data included, untouched. The reset is triggered by `api/scripts/reset_db.py --yes` or by answering `y` to the startup prompt.
- Startup (`main.py:_ensure_current_schema`) compares the fingerprint with `schema.sql` and asks on `/dev/tty` whether to reset if they differ. With no terminal, it refuses to start. There are **no migrations, by the user's choice for v1**; don't propose them unless asked.
- Every query, including the reset and fingerprint ones, lives in `queries.sql` and is called through the generated `queries.py`. The only raw SQL is executing `schema.sql` itself. PostgreSQL can't take identifiers (such as a database name) as parameters, which is why a reset replaces the `public` schema instead of dropping the database.
- Keep `schema.sql` plain DDL that sqlc can parse. No `DO $$` blocks: sqlc can't see types created inside them, and the generated enums silently become `typing.Any` (proven experimentally; PostgreSQL 18 has no `CREATE TYPE IF NOT EXISTS`). Use `IF NOT EXISTS` only for extensions. Keep the `schema_fingerprint` table.
- Changed only `queries.sql` → regenerate; no reset, data is kept. Changed `schema.sql` → regenerate, then reset (all data is deleted; the user has approved this for v1). Any edit to `schema.sql`, even a comment, changes the fingerprint.
- Preserve constraints, indexes, transaction semantics, timestamp meaning/time zone handling, and IP address types.
- Use parameterised queries. Never interpolate request data into SQL strings.
- Consider concurrency, uniqueness, retention, pagination, and query plans for event ingestion and exhibit queries.
- Resetting the development database is approved for v1. Never reset, alter or delete data in any other database (a deployed one included) without the user's explicit approval for that database.
- Before changing what a column or event *means* (not just its shape), explain the effect on existing data and on the exhibit, and ask.

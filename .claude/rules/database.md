---
paths:
  - "api/src/attenborough/db/**/*.sql"
  - "api/src/attenborough/db/sqlc.yaml"
  - "api/src/attenborough/db/**/*.py"
---

# PostgreSQL and sqlc

- Inspect `schema.sql`, `queries.sql`, sqlc configuration, generated output, and call sites together before changing persistence.
- Treat SQL/schema/query sources as authoritative. Never hand-edit generated sqlc files such as `models.py`, `enums.py`, or `queries.py`.
- After changing source SQL or schema, use the project’s established sqlc generation command and inspect all generated changes.
- Preserve constraints, indexes, transaction semantics, timestamp meaning/time zone handling, and IP address types.
- Use parameterised queries. Never interpolate request data into SQL strings.
- Consider concurrency, uniqueness, retention, pagination, and query plans for event ingestion and exhibit queries.
- Database schema changes can destroy or reinterpret data. Explain migration/compatibility implications and get approval before destructive changes or data migrations.
- Do not rewrite existing migration history or silently change production data.

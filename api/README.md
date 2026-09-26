# Attenborough API

The backend of Attenborough, a public honeypot. It serves decoy resources to scanners and bots, records every request, and publishes what it observed on the public **exhibit** (`/exhibit/...`).

FastAPI on Python 3.14, async psycopg against PostgreSQL, and sqlc-generated query code. Commands below run from this `api/` directory, except the `mise` tasks, which run from the repo root.

## Running locally

1. `mise install` (repo root; installs the pinned Python and uv), then `uv sync`
2. Create `.env`. Starting the server with no `.env` present creates one from the same template as `.example.env`, then exits. Fill in the required values. Any setting can also come from an environment variable, which takes precedence over `.env`.
3. Make sure the PostgreSQL database named in `DB_DATABASE` exists, e.g. `createdb attenborough`. It can be empty; the app never creates the database itself.
4. Start the server from a terminal:

   ```sh
   cd src && uv run uvicorn attenborough.main:app --reload
   ```

   The first time, the app sees that the database has no schema and asks whether to create it (see [Database](#database)); answer `y`. The VS Code launch configuration does the same. Plain `uvicorn` and `fastapi dev` bind to `127.0.0.1`; **`fastapi run` binds to `0.0.0.0`** (see [Deployment](#deployment)).

Every startup writes `src/openapi.json` and `.example.env`. Both are deterministic and tracked, so a diff in either means the API or the settings changed.

## Database

### How the schema gets into the database

`src/attenborough/db/schema.sql` is the complete schema, as plain DDL. There are **no migrations**, a deliberate v1 choice: changing the schema means resetting the database, which deletes all its data.

A **reset** (`db/schema.py:reset_schema`) drops the `public` schema, with every table, type and row in it, applies `schema.sql`, and records the file's SHA-256 in the `schema_fingerprint` table. **All of this happens in one transaction:** if `schema.sql` is broken, the reset rolls back and the database, data included, is left exactly as it was.

**On every startup**, before serving any request, the app compares the database's recorded fingerprint with the current `schema.sql`:

| The database is… | What happens |
|---|---|
| **current**: built from this exact `schema.sql` | the server starts normally |
| **outdated**: built from a different `schema.sql` | the app asks on the terminal whether to reset. `y` resets and starts; anything else refuses to start |
| **missing**: no Attenborough schema, e.g. a new database | same question and outcomes as *outdated* |

The question is asked on the controlling terminal, so it works under `--reload` and in the VS Code terminal. The default answer is **no**. With no terminal (Docker, systemd, CI), the app never resets anything: it refuses to start and logs how to reset. To reset without the prompt:

```sh
uv run python scripts/reset_db.py --yes   # from api/; DELETES ALL DATA
```

Any change to `schema.sql`, even a comment, changes the fingerprint and triggers the question. That's deliberate: it can't tell a harmless edit from a real one.

### Making changes

| You changed… | Then |
|---|---|
| `queries.sql` only | regenerate the query code. **No reset needed**; data is kept. |
| `schema.sql` | regenerate the query code, then restart and answer `y`, or run `scripts/reset_db.py --yes`. **All data is deleted.** |

Regenerate with `mise run sqlc` from the repo root, or from here:

```sh
uv run sqlc generate --file src/attenborough/db/sqlc.yaml
```

Never hand-edit the generated `db/queries.py`, `db/models.py` or `db/enums.py`. Every query the app and the reset run comes from `queries.sql`. The one exception is executing `schema.sql` itself, which is a file, not a query.

### Rules for `schema.sql`

- **Plain DDL, no `DO $$ … $$` blocks.** sqlc parses SQL but never executes it, so an enum type created inside a `DO` block is invisible to it. The generated code then uses `typing.Any` instead of the `db/enums.py` enum, and `enums.py` isn't generated at all. PostgreSQL has no `CREATE TYPE IF NOT EXISTS`, and no other workaround keeps the types.
- **`IF NOT EXISTS` only where a brand-new schema can already have the object,** i.e. extensions. Everywhere else it would wrongly suggest the script can be re-run.
- **Keep the `schema_fingerprint` table.** The startup check depends on it.

The reset runs as the configured database user, which must own the `public` schema. The database's owner does by default. It never needs permission to create databases.

## Checks

From the repo root, with [mise](https://mise.jdx.dev) (`mise.toml` pins Python, Node and uv):

```sh
mise run fix     # ruff check --fix, ruff format (and the web's eslint --fix, prettier)
mise run check   # the gate: ruff, basedpyright, pytest, then the web's checks; must exit 0
```

`check` never skips a task and stops at the first failure. Each check is also its own task (`mise tasks ls`): `api-lint`, `api-format-check`, `api-typecheck` (basedpyright, `typeCheckingMode "all"`), `api-test`. To rerun on save: `mise watch -w api/src check`. Two more checks sit outside the gate:

```sh
mise run api-magic-strings                         # candidates to judge, not automatic failures
uv run python scripts/telemetry_probe.py verify   # end-to-end: needs a running server; writes tagged test rows
```

Generated sqlc code is excluded from ruff and basedpyright (`pyproject.toml`). If you run basedpyright by hand, run it from this directory. It reads its config from the current directory, so running it from the repo root gives different, misleading results.

## Deployment

### Client IP attribution (security-critical)

Every record the honeypot keeps is attributed to a client IP: telemetry, credential attempts, decoy views. The exhibit publishes that attribution. If a client could choose its own IP, it could hide itself or frame someone else in public.

**How the app decides the client IP.** The app installs uvicorn's `ProxyHeadersMiddleware` itself (in `main.py`), so the same rule applies however the server is started:

- If the TCP peer is listed in the `FORWARDED_ALLOW_IPS` setting, the client is taken from `X-Forwarded-For`. The header is read **right to left**, and the first address that isn't a trusted proxy is the client. Entries a client wrote into the header itself are therefore ignored.
- Every other peer is attributed to its own TCP address, and all headers are ignored.
- No other header (`X-Real-IP`, `CF-Connecting-IP`, …) is ever read.

`FORWARDED_ALLOW_IPS` is a comma-separated list of IPs, CIDRs or literals, like uvicorn's `--forwarded-allow-ips`. It defaults to `127.0.0.1`.

| Topology | `FORWARDED_ALLOW_IPS` |
|---|---|
| No proxy; clients connect straight to the app | leave the default (`127.0.0.1`). Internet clients are never trusted. |
| nginx on the same host, proxying to `127.0.0.1` | leave the default |
| nginx in another container or host | exactly the proxy's address, or the smallest CIDR that contains it. Every peer inside that range can set its own attribution. |
| CDN (e.g. Cloudflare) in front of nginx | as above for nginx, and configure nginx's real-IP module (below) |

**Never use `FORWARDED_ALLOW_IPS=*`.** It lets any peer choose its own IP.

### nginx

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    # Overwrite, don't append: the client's own X-Forwarded-For never reaches the app.
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

If a CDN sits in front of nginx, `$remote_addr` is the CDN's address. Make nginx resolve the real client first:

```nginx
set_real_ip_from <each published CDN range>;   # only the CDN's own ranges
real_ip_header   CF-Connecting-IP;             # or X-Forwarded-For with real_ip_recursive on;
```

### Keep the app reachable only through the proxy

The proxy is only a boundary if clients can't get around it:

- Bind the app to `127.0.0.1`, a unix socket, or a private container network. **`fastapi run` binds to `0.0.0.0` unless you pass `--host`.**
- Docker: `ports: ["8000:8000"]` publishes on every interface and **bypasses host firewalls such as ufw**. Publish nothing, or `127.0.0.1:8000:8000`, and let nginx reach the app over a private network.
- uvicorn's CLI adds its own proxy-header layer too. It trusts `$FORWARDED_ALLOW_IPS` from the process environment, or `127.0.0.1` if that's unset. The two layers are compatible. To keep them identical, set `FORWARDED_ALLOW_IPS` as an environment variable in deployment rather than only in `.env`.

### Check it after every deployment

From a machine outside your network, send forged headers:

```sh
curl -s -o /dev/null -H 'X-Forwarded-For: 203.0.113.99' -H 'X-Real-IP: 203.0.113.98' https://<host>/admin/dashboard
curl -s https://<host>/exhibit/ip/203.0.113.99/activity   # must be []
curl -s https://<host>/exhibit/ip/203.0.113.98/activity   # must be []
curl -s https://<host>/exhibit/ip/<your public IP>/activity   # must show the /admin/dashboard hit
```

If either forged address shows the hit, attribution can be spoofed; fix the proxy setup before going public.

### Other security notes

- **The exhibit shows attacker data in full, by design.** Submitted usernames and passwords, headers, user agents and paths are published without redaction. Wherever it is rendered, render it as inert data: escape it, and never interpret it as HTML or script.
- **Never publish the project's own data:** `.env` (git-ignored), DB and OAuth credentials, admin users and sessions, audit logs, internal errors.
- **Least privilege:** in production, run the app as a role that can only read and write rows, so it can never reset anything. A reset in production then has to be deliberate: run `scripts/reset_db.py --yes` as the schema owner, with `DB_USERNAME` and `DB_PASSWORD` set in the environment for that one command, since environment variables override `.env`. Then grant the app role only what it needs, e.g. `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app;` plus `GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app;`, which `BIGSERIAL` columns need. The startup check only reads `schema_fingerprint`. These grants haven't been tested yet, so verify them when you set the role up.
- **Writable source directory:** startup writes `src/openapi.json` and `.example.env`, so the app needs write access to its own directory. A read-only container filesystem will fail at startup.
- **Logs:** they contain attacker-controlled paths and user agents. Treat them as untrusted input in any log viewer. Logging is currently set to `DEBUG` at import in `main.py`.

### Known gaps

- Every router exposes a public `/test` debug route.
- There are no migrations: any schema change resets the database and loses its data. Fine for v1; revisit before data must be kept.

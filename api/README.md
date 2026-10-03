# Attenborough API

The backend of Attenborough, a public honeypot. The decoy app (`../decoy`) serves the fake sites and reports every visit and login attempt here (`/ingest/...`); the API records them, decides every outcome, and publishes what it observed on the public **exhibit** (`/exhibit/...`). Requests to any other path of the API itself are recorded too, as honeypot 404s.

The code is small and flat: `main.py` composes the app (middleware, routers, startup), `exhibit.py` and `ingest.py` are the two routers, `events.py` the exhibit's event models, `patterns.py` the Patterns page's figures, `telemetry.py` records every request (`record_hit`, `TelemetryMiddleware`), `geolocation.py` locates visitors' addresses, `dependencies.py` has the client address and database dependencies, and `db/` the schema, queries and connection pool.

FastAPI on Python 3.14, async psycopg against PostgreSQL, and sqlc-generated query code. Commands below run from this `api/` directory, except the `mise` tasks, which run from the repo root.

## Running locally

1. `mise install` (repo root; installs the pinned Python and uv), then `uv sync`
2. Create `.env`. Starting the server (or any script) with no `.env` present creates one from the same template as `.example.env`, then exits. Fill in the required values, and set `DEBUG = True` for development: it turns on DEBUG-level logging (INFO otherwise) and every router's `/test` debug route. Any setting can also come from an environment variable, which takes precedence over `.env`.
3. Make sure the PostgreSQL database named in `DB_DATABASE` exists, e.g. `createdb attenborough`. It can be empty; the app never creates the database itself.
4. Start the server from a terminal:

   ```sh
   cd src && uv run uvicorn attenborough.main:app --reload
   ```

   The first time, the app sees that the database has no schema and asks whether to create it (see [Database](#database)); answer `y`. The VS Code launch configuration does the same. Plain `uvicorn` and `fastapi dev` bind to `127.0.0.1`; **`fastapi run` binds to `0.0.0.0`** (see [Deployment](#deployment)).

### Settings, and the files the app writes

Settings are the fields of `Settings` in `src/attenborough/settings.py`, read from `.env`, with environment variables taking precedence. `get_settings()` loads and validates them once. The first import of the `attenborough` package calls it, so a bad or missing required value stops the app, a test or a script immediately. `HONEYPOT_ADDRESSES` is required: for development, `localhost,127.0.0.1` (see [Hiding where the honeypot is](#hiding-where-the-honeypot-is)).

What the app does with files depends on whether it runs from a **source checkout** (this directory, with `pyproject.toml` beside the package) or as an **installed package** (the container image, which installs it into its virtual environment). `settings.SOURCE_CHECKOUT` tells them apart, so no flag can be forgotten:

- **Loading settings only reads.** The one exception, in a checkout only, is when `.env` doesn't exist: `get_settings()` creates it from the template and exits, so you get a file to fill in rather than a validation error for every required field. An installed package reads the environment only.
- **In a checkout, each server start rewrites two tracked files,** in the lifespan in `src/attenborough/main.py`: `src/openapi.json` (the API spec, which generates the web and decoy clients) and `.example.env` (the settings template, from `write_example_env()`). Both are deterministic, so a diff in either means the API or the settings changed; commit it with that change. Importing the app, running tests and running scripts write neither, and an installed package never writes them: the container's filesystem is read-only.

## Database

### How the schema gets into the database

Two descriptions of the schema, kept equal:

- **`src/attenborough/db/migrations/`**: numbered SQL files (`0001_baseline.sql`, `0002_...`), applied in order. They are how every production database is built and changed, so its data is kept. `0001_baseline.sql` is the schema the honeypot went live with.
- **`src/attenborough/db/schema.sql`**: the complete, current schema, as plain DDL: what all the migrations build. sqlc generates the query code from it, and a development reset applies it directly.

`src/tests/test_migrations.py` (part of `mise run check`) builds both side by side in scratch schemas in the development database, inside a transaction it always rolls back, and fails if they differ in any table, column (position included: generated rows are positional), constraint, index, function, trigger, sequence or enum.

Each database records what built it in `schema_migrations`: one row per applied migration, with the file's SHA-256. **Migrating** (`db/schema.py:migrate`) applies the pending migrations in order, each in its own transaction with its row, so a failed migration rolls back and leaves the database at the last one that succeeded. A **reset** (`db/schema.py:reset_schema`, development only) drops the `public` schema, with every table, type and row in it, applies `schema.sql`, and records every migration as applied, all in one transaction.

**On every startup**, before serving any request, the app compares `schema_migrations` with `migrations/`:

| The database is… | What happens |
|---|---|
| **current**: every migration applied, none changed since | the server starts normally |
| **pending**: the first migrations applied, unchanged; more to apply | the app asks on the terminal whether to apply them. `y` migrates and starts; anything else refuses to start |
| **diverged**: an applied migration was edited, or is unknown here | the app asks whether to **reset**. `y` resets (deleting all data) and starts; anything else refuses to start |
| **missing**: no `schema_migrations`, e.g. a new database | same question and outcomes as *diverged* |

The question is asked on the controlling terminal, so it works under `--reload` and in the VS Code terminal. The default answer is **no**. With no terminal (Docker, systemd, CI), the app never changes the schema: it refuses to start and logs why and what to run. Without the prompt:

```sh
uv run python scripts/migrate.py          # apply pending migrations; a new, empty database gets them all
uv run python scripts/reset_db.py --yes   # development only: DELETES ALL DATA
```

In a deployment the API runs as a role that can't change the schema, so migrations run separately, as the schema's owner: `docker compose run --rm migrate` (`../deploy/README.md`). `migrate.py` refuses a diverged database: only a reset can fix that, and production is never reset.

### Making changes

| You changed… | Then |
|---|---|
| `queries.sql` only | regenerate the query code. Nothing else; data is kept. |
| the schema | change `schema.sql` **and** add the next migration making the same change (`0002_short_name.sql`), regenerate, and run `scripts/migrate.py` (or restart and answer `y`). `mise run check` fails until the two agree. A new column goes last in `schema.sql`, where `ALTER TABLE ... ADD COLUMN` puts it. |

Never edit a migration that a database you keep has applied: the startup check would call that database diverged. Until then (on a development database), editing it and resetting is fine.

Regenerate with `mise run sqlc` from the repo root, or from here:

```sh
uv run sqlc generate --file src/attenborough/db/sqlc.yaml
```

Never hand-edit the generated `db/queries.py`, `db/models.py` or `db/enums.py`. Every query the app, the migrations and the reset run comes from `queries.sql`. The exceptions are executing `schema.sql` and the migration files themselves, which are files, not queries, and the catalog query in `test_migrations.py`.

### Rules for `schema.sql` and migrations

- **Plain DDL, no `DO $$ … $$` blocks.** sqlc parses SQL but never executes it, so an enum type created inside a `DO` block is invisible to it. The generated code then uses `typing.Any` instead of the `db/enums.py` enum, and `enums.py` isn't generated at all. PostgreSQL has no `CREATE TYPE IF NOT EXISTS`, and no other workaround keeps the types. (`CREATE FUNCTION ... AS $$ ... $$`, for a trigger, is fine: sqlc doesn't need to see inside it.)
- **`IF NOT EXISTS` only where a brand-new schema can already have the object,** i.e. extensions. Everywhere else it would wrongly suggest the script can be re-run.
- **Keep the `schema_migrations` table.** The startup check and the migrations depend on it.
- **A migration runs as the schema's owner.** Tables and sequences it creates are readable and writable by the app role automatically (default privileges, `../deploy/database.sql`). Don't grant to role names in a migration: names are deployment settings.

The reset runs as the configured database user, which must own the `public` schema. The database's owner does by default. It never needs permission to create databases.

### At volume

- **The exhibit's listings page by keyset,** never by `OFFSET`: a page is the events after the previous page's last one, passed as an opaque cursor (`?before=`, the previous page's `next_cursor`). `ListRecentEvents` and `ListIpEvents` read each kind of event from its own `(time, id)` index with its own `LIMIT`, so every page reads about one page of rows from each table, however deep it is. (A single `UNION ALL` view over the four tables let the planner read and sort a whole table instead: 2 s for the first page.)
- **Per-address totals are kept, not counted.** `ip_activity` holds each address's requests, distinct paths, login attempts and first and last request, kept by insert triggers on `telemetry_hits` and `credential_stuffing_attempts` (`schema.sql`). Counting distinct paths for an address with a million requests took 1.2 s. Nothing deletes events; anything that ever does must recompute the totals.
- **The Patterns page** (`GET /exhibit/patterns`, `patterns.py`) reads many rows, so it is computed at most every five minutes and served from memory in between. Its all-time figures come from the running totals (`ip_activity`, `ip_request_paths`, `ip_locations`), which grow with the number of addresses; its figures over requests and login attempts cover only the last seven UTC days, read through the time indexes, so their cost is one week's traffic however long the history. On two million seeded hits (155,000 in the last week, 30,000 addresses) a computation takes 0.84 s and a cached answer 4 ms. `path_category()` runs once per distinct path (a `MATERIALIZED` CTE): left to the planner, it ran on every row and took seconds.
- **Measured** on two million hits (half from one address) and 100,000 login attempts: every exhibit query takes under 1 ms in the database, on the first page and the last (`EXPLAIN ANALYZE`). `scripts/seed_db.py` fills a development database with that mix (about ten minutes), and `scripts/exhibit_latency.py` walks a listing through a running API, page by page to the last, timing each. Run it where the API and the database are close: from a laptop over Wi-Fi, the few round trips per page dominate. In the container stack on 500,000 hits, every page of the feed took a median of 3.6 ms, the slowest 21 ms.

## Checks

From the repo root, with [mise](https://mise.jdx.dev) (`mise.toml` pins Python, Node and uv):

```sh
mise run fix     # ruff check --fix, ruff format (and the web's eslint --fix, prettier)
mise run check   # the gate: ruff, basedpyright, pytest, then the web's checks; must exit 0
```

`check` never skips a task and stops at the first failure. Each check is also its own task (`mise tasks ls`): `api-lint`, `api-format-check`, `api-typecheck` (basedpyright, `typeCheckingMode "all"`), `api-test`. `api-test` needs the development database (`.env`) for `test_migrations.py`; the other tests don't touch it. To rerun on save: `mise watch -w api/src check`. More checks sit outside the gate:

```sh
mise run api-magic-strings                                   # candidates to judge, not automatic failures
uv run python scripts/telemetry_probe.py verify              # end-to-end: needs a running server; writes tagged test rows
uv run python scripts/seed_db.py --database <DB_DATABASE>    # development database only: two million synthetic hits
uv run python scripts/exhibit_latency.py                     # every page of the feed, timed (--address for one address)
uv run python scripts/locate_ips.py                          # locate every address seen while geolocation was off
```

Generated sqlc code is excluded from ruff and basedpyright (`pyproject.toml`). If you run basedpyright by hand, run it from this directory. It reads its config from the current directory, so running it from the repo root gives different, misleading results.

## Geolocation

Each address that sends the honeypot a request is located once, when its first request is recorded (`record_hit` calls `geolocation.record_location`), and kept in `ip_locations`: country, city, coordinates, and the network (autonomous system number and owner) it belongs to, with the databases it came from and their dates. The exhibit shows each with a flag beside the address, a map and the network on the address's page, and in aggregate on the Patterns page, always as an estimate: a location says where an address is registered and routed, not where the sender is, and most scanners rent servers in data centres.

- **Source:** DB-IP's free Lite databases, City Lite and ASN Lite, MMDB files updated monthly, read with MaxMind's `maxminddb` (its C extension: `maxminddb.extension.Reader`). They are licensed CC BY 4.0, so every exhibit page credits DB-IP in its footer.
- **Setting:** `GEOIP_DIRECTORY`, the directory holding `dbip-city-lite.mmdb` and `dbip-asn-lite.mmdb`. Unset, nothing is located and everything else works; set, both files must be there, or the server refuses to start. For development, download them as `../deploy/update-geoip.sh` does into any directory and point the setting at it.
- **No row** in `ip_locations` means the address was never located (geolocation was off); **a row of NULLs** means the databases know nothing about it (private addresses, for one). `scripts/locate_ips.py` locates every address that has no row, so run it once after turning geolocation on. Addresses keep their first location: a later month's databases only affect new visitors.
- `geolocator` (in `geolocation.py`) is opened in the lifespan, like the connection pool, and does no I/O before.

## Deployment

The production setup (containers, nginx, the database and its roles, and the checks to run after every deployment) is in `../deploy/README.md`. This section is what the API itself requires of any deployment.

### Client IP attribution (security-critical)

Every record the honeypot keeps is attributed to a client IP: telemetry and credential attempts. The exhibit publishes that attribution. If a client could choose its own IP, it could hide itself or frame someone else in public.

**How the app decides the client IP.** The app installs uvicorn's `ProxyHeadersMiddleware` itself (in `main.py`), so the same rule applies however the server is started:

- If the TCP peer is listed in the `FORWARDED_ALLOW_IPS` setting, the client is taken from `X-Forwarded-For`. The header is read **right to left**, and the first address that isn't a trusted proxy is the client. Entries a client wrote into the header itself are therefore ignored.
- Every other peer is attributed to its own TCP address, and all headers are ignored.
- No other header (`X-Real-IP`, `CF-Connecting-IP`, …) is ever read.

`FORWARDED_ALLOW_IPS` is a comma-separated list of IPs, CIDRs or literals, like uvicorn's `--forwarded-allow-ips`. It defaults to `127.0.0.1`.

| Topology | `FORWARDED_ALLOW_IPS` |
|---|---|
| No proxy; clients connect straight to the app | leave the default (`127.0.0.1`). Internet clients are never trusted. |
| nginx on the same host, proxying to `127.0.0.1` | leave the default |
| The decoy app (`../decoy`) on the same host, reporting its visitors | leave the default. Elsewhere: exactly its address. See `../decoy/README.md`, "Deployment". |
| nginx in another container or host | exactly the proxy's address, or the smallest CIDR that contains it. Every peer inside that range can set its own attribution. |
| The containers (`../docker-compose.yml`) | the decoy container's fixed address, `10.89.1.10`, set in the compose file |
| CDN (e.g. Cloudflare) in front of nginx | as above for nginx, and configure nginx's real-IP module (below) |

**Never use `FORWARDED_ALLOW_IPS=*`.** It lets any peer choose its own IP.

### nginx

The API itself is never proxied publicly: nginx proxies to the decoy app and to the exhibit's server (`../deploy/nginx/`), and only those two call the API. If you ever put nginx straight in front of the API, it must overwrite the header, never append to it:

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

Never put a CDN in front of the decoy: it would block or challenge the very scanners the honeypot exists to see, and replace their addresses with its own.

### Keep the app reachable only through the proxy

The proxy is only a boundary if clients can't get around it:

- Bind the app to `127.0.0.1`, a unix socket, or a private container network. **`fastapi run` binds to `0.0.0.0` unless you pass `--host`.**
- Docker: `ports: ["8000:8000"]` publishes on every interface and **bypasses host firewalls such as ufw**. Publish nothing, or `127.0.0.1:8000:8000`, and let nginx reach the app over a private network.
- uvicorn's CLI adds its own proxy-header layer too. It trusts `$FORWARDED_ALLOW_IPS` from the process environment, or `127.0.0.1` if that's unset. The two layers are compatible. To keep them identical, set `FORWARDED_ALLOW_IPS` as an environment variable in deployment rather than only in `.env`.

### Check it after every deployment

`../deploy/README.md` has the full list. The attribution check, from a machine outside your network, sends forged headers to the decoy and looks for them on the exhibit:

```sh
curl -s -o /dev/null -H 'X-Forwarded-For: 203.0.113.99' -H 'X-Real-IP: 203.0.113.98' http://<decoy domain>/wp-login.php
curl -s https://<exhibit domain>/ip/203.0.113.99    # "No activity has been recorded from this address."
curl -s https://<exhibit domain>/ip/203.0.113.98    # the same
curl -s https://<exhibit domain>/ip/<your public IP>   # must show the /wp-login.php request
```

If either forged address shows the request, attribution can be spoofed; fix the proxy setup before going public.

### Hiding where the honeypot is

The exhibit must not tell its readers where the honeypot is, but visitors' requests name the server they reached: the `Host` header, `Origin` and `Referer`, full URLs in the request line, and bodies (WordPress's login form posts `redirect_to=https://<decoy domain>/wp-admin/`). So the exhibit endpoints replace each of `HONEYPOT_ADDRESSES` (the decoy's domains and the host's public IPs, past ones too) with `[honeypot]` wherever a visitor's text contains it: path, query, user agent, header names and values, bodies, and submitted usernames and passwords (`events.py`, `hide_honeypot`). The database keeps everything exactly as sent; only what the exhibit shows changes.

- The match ignores case and finds a name inside longer text (`www.<domain>`, `https%3A%2F%2F<domain>`), but an address is never found inside a longer number (`203.0.113.5` in `203.0.113.50`).
- It's best effort. A name sent in another encoding (base64, `%2E` for its dots) isn't recognised, and a body cut short (the stored 64 KiB, or a listing's 1 KiB preview) can end partway through a name.
- The web server never learns the names: it only ever sees what the API returns.
- Don't browse the decoy from the honeypot's own network: your public IP, which is the honeypot's, would be recorded as a visitor's address, and addresses are never hidden.

### Other security notes

- **The exhibit shows attacker data in full, by design.** Submitted usernames and passwords, headers, user agents and paths are published without redaction. Wherever it is rendered, render it as inert data: escape it, and never interpret it as HTML or script.
- **Never publish the project's own data:** `.env` (git-ignored), DB credentials, the honeypot's own names and address (above), admin users and sessions, audit logs, internal errors.
- **Least privilege:** in production the app connects as a role that may only `SELECT`, `INSERT` and `UPDATE` rows in the owner's tables: no DDL, no `DELETE` or `TRUNCATE`, no temporary tables. The schema's owner, a separate role, applies migrations and is used for nothing else. `../deploy/database.sql` creates both, with default privileges so that every table a migration creates is covered. Tested against PostgreSQL 18: the app role inserts hits, login attempts and decoy events (with their triggers), upserts decoys and reads the exhibit; it is refused `CREATE`, `DROP`, `ALTER`, `DELETE`, `TRUNCATE` and `CREATE TEMP`, and can't migrate. What it can still do: `UPDATE` any row (it needs `UPDATE` for decoys and the per-address totals), including `schema_migrations`, which could only make the app refuse to start.
- **Read-only filesystem:** the installed package writes no files (see [Settings](#settings-and-the-files-the-app-writes)), so the container runs with a read-only root filesystem.
- **Logs:** they contain attacker-controlled paths and user agents. Treat them as untrusted input in any log viewer. Leave `DEBUG` off in production: it logs at DEBUG level and enables the `/test` debug routes.

### Known gaps

- **`/ingest/...` has no authentication.** Only the decoy app (`../decoy`) may call it, and in the deployment only it and the exhibit's server can reach the API at all: they share private container networks with it, and nothing else does. If the API were ever reachable from elsewhere, anyone reaching it could post reports. The IP rule still holds, so such reports would be attributed to the sender's own address, like any other request they send.

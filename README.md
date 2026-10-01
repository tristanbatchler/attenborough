# Attenborough

A public honeypot with an exhibit. Decoy resources are served to internet scanners and bots, and the API records everything they send; the web frontend publishes those observations, in full, as a browsable exhibit.

| Directory | What | Details |
|---|---|---|
| `api/` | FastAPI backend: telemetry, the decoy app's ingest endpoints, and the exhibit API. Python 3.14, PostgreSQL, sqlc. | [`api/README.md`](api/README.md) |
| `web/` | SvelteKit frontend for the exhibit, with a client generated from the API's OpenAPI spec. | [`web/README.md`](web/README.md) |
| `decoy/` | SvelteKit app serving the fake sites visitors see. It reports every request to the API, which records it and decides every outcome. | [`decoy/README.md`](decoy/README.md) |
| `deploy/`, `docker-compose.yml` | Production: the three apps in locked-down containers, behind nginx on the host, with PostgreSQL on the host. | [`deploy/README.md`](deploy/README.md) |
| `docs/` | Plans for each milestone, and notes on what the honeypot observed. | |

## Getting started

[mise](https://mise.jdx.dev) pins the tools (Python, Node, uv) and runs every check:

```sh
mise install
```

Then set up and start each part, following its README: the API first, then the web frontend and the decoy app.

## Checks

From the repo root:

```sh
mise run fix     # every auto-fix and formatter: ruff, eslint, prettier
mise run check   # the gate for both halves; must exit 0 before committing
```

`check` runs ruff, basedpyright (strictest mode) and pytest for the API, then svelte-check, ESLint (strict type-aware rules), Prettier and a production build for the web and then the decoy app. It stops at the first failure. `mise tasks ls` lists every task.

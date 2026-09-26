# Attenborough

A public honeypot with an exhibit. The API serves decoy resources to internet scanners and bots and records everything they send; the web frontend publishes those observations, in full, as a browsable exhibit.

| Directory | What | Details |
|---|---|---|
| `api/` | FastAPI backend: decoys, telemetry, and the exhibit API. Python 3.14, PostgreSQL, sqlc. | [`api/README.md`](api/README.md) |
| `web/` | SvelteKit frontend for the exhibit, with a client generated from the API's OpenAPI spec. | [`web/README.md`](web/README.md) |

## Getting started

[mise](https://mise.jdx.dev) pins the tools (Python, Node, uv) and runs every check:

```sh
mise install
```

Then set up and start each half, following its README: the API first, then the web frontend.

## Checks

From the repo root:

```sh
mise run fix     # every auto-fix and formatter: ruff, eslint, prettier
mise run check   # the gate for both halves; must exit 0 before committing
```

`check` runs ruff, basedpyright (strictest mode) and pytest for the API, then svelte-check, ESLint (strict type-aware rules), Prettier and a production build for the web. It stops at the first failure. `mise tasks ls` lists every task.

---
paths:
  - "mise.toml"
  - "api/.env"
  - "api/.example.env"
  - "api/src/attenborough/settings.py"
  - "web/.env"
  - "web/.env.example"
  - "web/vite.config.ts"
  - "**/Dockerfile"
  - "**/*compose*.yml"
  - "**/*compose*.yaml"
  - "**/nginx*.conf"
  - "deploy/**/*"
  - ".env.example"
---

# Configuration and deployment

- **API settings:** `api/src/attenborough/settings.py` (Pydantic `Settings`), read from `api/.env` with environment variables taking precedence. `api/.example.env` is **generated** from the `Settings` fields by `write_example_env()`, which only the server's lifespan (`main.py`) calls, once per start: change a field, never edit the example by hand. Loading settings (`get_settings()`) has no side effects, except creating a missing `api/.env` from the template and exiting. Keep file writes out of the `Settings` class and out of import time. Code gets settings through the app (`from attenborough import settings` / `get_settings()`); scripts too, never by re-parsing `.env`.
- **Web settings:** `web/.env` (from `web/.env.example`), read with `$env/dynamic/private` in `$lib/server/`. Required values are validated at startup in `src/hooks.server.ts` (`init`).
- **Tools:** `mise.toml` pins Python, Node and uv and defines every check. Match stashit's pins unless there's a reason not to.
- Production: `docker-compose.yml` (api, web, decoy, and the one-off `migrate`) and `deploy/` (nginx template and decoy snippet, `tmpfiles.conf` for the socket directories, `database.sql` for the database and roles, `check-isolation.sh`), all described in `deploy/README.md`. It runs on a host shared with other services, with nginx and PostgreSQL on the host, not in compose. Deployment settings are the root `.env` (from `.env.example`): domains, certificate directory, `HONEYPOT_ADDRESSES`, both roles' credentials. Compose maps them to each service's own variables, so the API never receives the owner's password.
- Containment is the point of the design; keep every part of it: no published ports (nginx reaches decoy and web through unix sockets in `/run/attenborough/`), `internal` networks with gateway mode `isolated` (a plain `internal` network still reaches the host's services), PostgreSQL only through its socket mounted read-only, uid 10001, read-only root filesystem, `cap_drop: ALL`, `no-new-privileges`, resource limits. `FORWARDED_ALLOW_IPS` is the decoy's fixed address on its network. Never publish a port, add a gateway network, or widen trust; prove isolation with `deploy/check-isolation.sh`.
- The repository is public. The honeypot's domains and public IP must never be committed: they live only in the server's `.env` and the rendered nginx site. Use placeholders (`decoy.example.org`, `203.0.113.5`) in docs and examples.
- Before changing configuration, trace how values are loaded in native development, tests, image builds, and running containers.
- Preserve a single source of truth where the project has established one. Do not duplicate environment values across Compose mappings, Docker build args, generated files, or application defaults without a clear reason.
- Distinguish build-time configuration from runtime configuration; do not bake secrets or environment-specific hostnames into images or generated artifacts. `vite build` must not need runtime settings.
- Inspect proxy/network topology before changing hostnames, ports, trusted IP headers, or database connectivity.
- Preserve required volume mounts and data persistence. Do not delete volumes, databases, or user data.
- Never print secrets from env files or include them in generated examples, logs, diffs, or responses. List key names only.
- Verify changes with the project’s actual build/run workflow when practical; do not assume a successful build proves runtime configuration is correct.

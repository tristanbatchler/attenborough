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
---

# Configuration and deployment

- **API settings:** `api/src/attenborough/settings.py` (Pydantic `Settings`), read from `api/.env` with environment variables taking precedence. `api/.example.env` is **generated** from the `Settings` fields by `write_example_env()`, which only the server's lifespan (`main.py`) calls, once per start: change a field, never edit the example by hand. Loading settings (`get_settings()`) has no side effects, except creating a missing `api/.env` from the template and exiting. Keep file writes out of the `Settings` class and out of import time. Code gets settings through the app (`from attenborough import settings` / `get_settings()`); scripts too, never by re-parsing `.env`.
- **Web settings:** `web/.env` (from `web/.env.example`), read with `$env/dynamic/private` in `$lib/server/`. Required values are validated at startup in `src/hooks.server.ts` (`init`).
- **Tools:** `mise.toml` pins Python, Node and uv and defines every check. Match stashit's pins unless there's a reason not to.
- There is no Docker, compose or nginx config in the repo yet. The deployment requirements (reverse proxy, `FORWARDED_ALLOW_IPS`, bind addresses, least privilege) are in `api/README.md` and `web/README.md` ("Deployment"). Keep new deployment config consistent with them.
- Before changing configuration, trace how values are loaded in native development, tests, image builds, and running containers.
- Preserve a single source of truth where the project has established one. Do not duplicate environment values across Compose mappings, Docker build args, generated files, or application defaults without a clear reason.
- Distinguish build-time configuration from runtime configuration; do not bake secrets or environment-specific hostnames into images or generated artifacts. `vite build` must not need runtime settings.
- Inspect proxy/network topology before changing hostnames, ports, trusted IP headers, or database connectivity.
- Preserve required volume mounts and data persistence. Do not delete volumes, databases, or user data.
- Never print secrets from env files or include them in generated examples, logs, diffs, or responses. List key names only.
- Verify changes with the project’s actual build/run workflow when practical; do not assume a successful build proves runtime configuration is correct.

---
paths:
  - "settings.env"
  - ".env"
  - "compose.yaml"
  - "compose.yml"
  - "docker-compose.yml"
  - "**/Dockerfile"
  - "**/docker-compose*.yml"
  - "**/docker-compose*.yaml"
---

# Configuration and deployment

- Before changing configuration, trace how values are loaded in native development, tests, image builds, and running containers.
- Preserve a single source of truth where the project has established one. Do not duplicate environment values across Compose mappings, Docker build args, generated files, or application defaults without a clear reason.
- Distinguish build-time configuration from runtime configuration; do not bake secrets or environment-specific hostnames into images or generated artifacts.
- Inspect proxy/network topology before changing hostnames, ports, trusted IP headers, or database connectivity.
- Preserve required volume mounts and data persistence. Do not delete volumes, databases, or user data.
- Never print secrets from env files or include them in generated examples, logs, diffs, or responses.
- Verify changes with the project’s actual Compose/build/run workflow when practical; do not assume a successful image build proves runtime configuration is correct.

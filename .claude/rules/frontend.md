---
paths:
  - "web/src/**/*"
  - "web/**/*.ts"
  - "web/**/*.svelte"
---

# Frontend

- First confirm the actual frontend directory, framework version, scripts, and established component/data-fetching patterns; these paths may need adjustment if the repository layout differs.
- Follow existing SvelteKit and TypeScript conventions. Keep server-only secrets and privileged data out of browser bundles.
- Preserve the distinction between public exhibit data and authenticated/admin data.
- Treat IP addresses, paths, user agents, headers, and other captured request data as untrusted text. Escape/render as text; do not inject it as HTML.
- Handle loading, empty, error, and pagination states for exhibit timelines and summaries.
- Avoid adding dependencies or introducing a new state-management/design system for a small change.
- Run the actual frontend lint, type-check, and build commands discovered in the package scripts.

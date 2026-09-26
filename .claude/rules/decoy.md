---
paths:
  - "decoy/**/*"
---

# Decoy app (decoy/)

- A SvelteKit app, separate from the exhibit, that serves the fake sites visitors see. Read `decoy/README.md` first. The general frontend conventions in `.claude/rules/frontend.md` apply here too (TypeScript strictness, the generated client, checks, no magic strings or numbers), except the exhibit-specific ones (Pico, paging, `/exhibit/meta`).
- It only presents. Every request is reported once by the `handle` hook (`/ingest/hits`); submitted credentials go to an `/ingest/...` endpoint, which records them and decides the outcome. Never decide an outcome, or write anything, in the decoy app. A new kind of submission needs a new ingest endpoint in `api/src/attenborough/ingest/`, then `mise run decoy-gen-types`.
- API calls spread in `apiOptions(event)` (`$lib/server/api`), which names the visitor in `X-Forwarded-For`. Never forward the visitor's own headers to the API, and never pass SvelteKit's `event.fetch` (it would send the visitor's cookies).
- A report must never change the visitor's response: failures are logged, and the page is served as usual.
- Imitate the real software's markup, status codes, headers and cookies, and nothing more. Don't introduce real vulnerabilities.
- Decoys are `+server.ts` endpoints, never SvelteKit pages (form actions, `__data.json` and content negotiation all give SvelteKit away). They render markup from Svelte components with `htmlPage` (`$lib/server/html`), answer any method, read forms only as PHP would, and set `trailingSlash = 'ignore'`. Unknown paths get `nginxError` from the catch-all route.
- Nothing may reveal Svelte or SvelteKit: put CSS in a plain `<style>` inside `<svelte:head>` (never a component `<style>`, which adds `svelte-*` classes), and keep `htmlPage`'s marker stripping, the hook's `__data.json` answer and the renamed `appDir`. Check responses with `curl -s <url> | grep -E '<script|_app|svelte|<!--'` (no output).
- Record the visitor's request, not SvelteKit's view of it: the raw path and query from `event.platform.req.url` and the body from a clone (`$lib/server/visit`). Never record from `event.url`, which is normalised.
- Serve every file through a route: `static/` stays empty, because adapter-node serves static files without running the `handle` hook, so they would never be reported.
- Captured input is shown back only as escaped text (plain `{…}`, never `{@html}`), like the WordPress error that repeats the submitted username.
- A change to the hook, `apiOptions` or any route is verified end to end with the `telemetry-testing` skill (`verify --target decoy`), not only with the static checks.

# Attenborough decoy

The fake sites that visitors see: a SvelteKit app, separate from the exhibit (`../web`), that imitates the software scanners look for (so far, a WordPress login page). It presents pages and nothing else. For every request it serves, it reports the visit to the API, and for every login it asks the API what to do, so the API stays the only thing that decides outcomes and writes to the database.

```
visitor → nginx → decoy (this app) → API /ingest/... → PostgreSQL
                  ├─ hooks.server.ts: reports every request, 404s included, with its status
                  └─ form actions: report submitted credentials, get back the outcome
```

## Running locally

1. `mise install` (repo root), then `npm install`
2. `cp .env.example .env` and set `API_BASE_URL` to where the API runs (default `http://127.0.0.1:8000`). Without it, the server refuses to start (`init` in `src/hooks.server.ts`).
3. Start the API (see `../api/README.md`), then:

   ```sh
   npm run dev   # http://localhost:5174/wp-login.php
   ```

   To see exactly what visitors get, run the production build: `npm run build`, then `PORT=8766 node --env-file=.env build`.

The API trusts this app to name the visitor (see "Client IP attribution" below). Locally both run on `127.0.0.1`, which the API trusts by default.

## How it works

**Every request is reported once, exactly as sent.** The `handle` hook in `src/hooks.server.ts` captures what the visitor sent (`$lib/server/visit`), serves the request, then reports it to `POST /ingest/hits` with the status they got. The API records it as a `honeypot` hit, as if it had served the request itself. What's recorded is the visitor's own request, not SvelteKit's view of it:

- **The path and query as sent,** from adapter-node's raw `req.url`, one character per byte. SvelteKit's `event.url` is normalised (`/cgi-bin/.%2e/.%2e/etc/passwd` would become `/etc/passwd`) and drops `__data.json` suffixes, so it is never used for recording.
- **The whole body,** read from a copy of the request. The API stores the first 64 KiB and the full size. A body the server refuses to read (over `BODY_SIZE_LIMIT`, 1M in `.env.example` like nginx's default `client_max_body_size`) is recorded as not captured, never as empty.

The hook waits for the report, rather than leaving a promise floating, so no report is lost when the server stops. The API answers before writing to the database, so the wait is one quick local round trip, capped at 2 seconds if the API is down. A failed report is logged and never changes the visitor's response.

**The API decides; this app presents.** A decoy that takes input sends it to an `/ingest/...` endpoint (the WordPress login uses `POST /ingest/logins`), which records it and returns the outcome. The page then shows what the real software would. Nothing here decides whether a login works.

**Client IP attribution.** The visitor is whoever SvelteKit's `getClientAddress()` says. Each API call carries `X-Forwarded-For` set by `apiOptions(event)` (`src/lib/server/api.ts`) to that single address, replacing anything the visitor sent, and the API honours it only because this app's address is in the API's `FORWARDED_ALLOW_IPS`. Don't forward the visitor's own headers to the API: `telemetry_probe.py verify --target decoy` catches that as an IP mismatch.

### Decoys are endpoints, not pages

SvelteKit pages bring app behaviour a PHP site never shows: form actions reject JSON posts with a 415 and answer non-browsers with JSON, every page has a `__data.json` twin, and `OPTIONS` gets an automatic 204. So every decoy is a `+server.ts` endpoint with full control of its status, headers and body, rendering its markup from a Svelte component with `htmlPage` (`$lib/server/html`):

- **Plain HTML.** `htmlPage` renders the component on the server (`svelte/server`) into a complete document and strips Svelte's hydration markers (`<!--[-->`, `<!--19tzqmq-->`). There's no client-side JavaScript: with no pages, SvelteKit doesn't even build any.
- **No component `<style>`.** Svelte adds `svelte-*` classes to markup styled by component CSS. Put a page's CSS in a plain `<style>` inside `<svelte:head>`; Svelte leaves that alone.
- **Like PHP, any method and any body.** An endpoint answers every method (`fallback`), and reads a form only when PHP would (`application/x-www-form-urlencoded` or `multipart/form-data`); anything else looks empty to it, as `$_POST` does.
- **Everything else is nginx's.** `src/routes/[...path]/+server.ts` answers every other path with nginx's own 404 page, byte for byte (`$lib/server/nginx`), and `src/error.html` makes a crash look like nginx's 500.
- **No SvelteKit URLs.** The hook answers `…/__data.json` with that 404 before SvelteKit can. SvelteKit's app directory, which it serves itself before any hook, is renamed (`appDir` in `vite.config.ts`) to a name no one requests, so `/_app/…` probes are ordinary 404s. Both routes set `trailingSlash = 'ignore'`: SvelteKit would otherwise redirect `/phpmyadmin/` to `/phpmyadmin` before the hook runs.
- **Form posts from anywhere.** SvelteKit rejects form posts whose `Origin` doesn't match, and bots rarely send one. `csrf.trustedOrigins: ['*']` (in `vite.config.ts`) turns that off; there are no real sessions to protect.

One SvelteKit URL remains: `…/__route.js` is answered with SvelteKit's own 400 before any hook, so it's neither disguised nor recorded here. nginx blocks it in deployment (below).

Check a response with `curl -s <url> | grep -E '<script|_app|svelte|<!--'`: it should print nothing.

**`static/` is empty on purpose.** adapter-node serves static files before the `handle` hook runs, so requests for them would never be reported. The folder exists only because SvelteKit's build fails when there's no browser build and no `static/` folder. It holds a `.gitkeep`, which is never served: adapter-node doesn't serve dotfiles. Serve every file through a route instead.

## Adding a decoy

1. A `+server.ts` endpoint that imitates the real software's status codes, headers and cookies, rendering its markup with `htmlPage` from a component in `$lib/<software>/` (see `src/routes/wp-login.php/` and `$lib/wordpress/`). Names the component and its endpoint share go in a module beside them (`$lib/wordpress/site.ts`). Set `trailingSlash = 'ignore'`.
2. Anything the visitor submits goes to an `/ingest/...` endpoint, which records it and decides the outcome. If there's no endpoint for it, add one in the API (`api/src/attenborough/ingest/`), then regenerate the client.
3. Check it with curl as above, and with `telemetry_probe.py verify --target decoy` (add cases for the new route).

## The API client is generated

As in `../web`: every endpoint and type comes from `src/lib/client/`, generated by `@hey-api/openapi-ts` from `../api/src/openapi.json`, limited to the `/ingest/...` endpoints (`openapi-ts.config.ts`). ESLint rejects hand-written calls. After an API change, restart the API, then `mise run decoy-gen-types` (or `npm run gen-types` here). Never edit `src/lib/client/`.

## Checks

The same scripts and tools as `../web` (see its README): `npm run check`, `lint`, `format:check` and `build`, run by `mise run check` from the repo root. Magic strings: `mise run decoy-magic-strings`, which uses `../web`'s scanner.

## Deployment

This app is the public server; the API is not reachable from the internet.

- **nginx** proxies every public request here. It must **overwrite** `X-Forwarded-For` with the client's address, never append to it, so a visitor's own header never gets through:

  ```nginx
  location / {
      proxy_pass http://127.0.0.1:8766;
      proxy_set_header Host $host;
      proxy_set_header X-Forwarded-For $remote_addr;
      proxy_set_header X-Forwarded-Proto $scheme;
  }
  ```

- **This app** runs with `ADDRESS_HEADER=x-forwarded-for` and `XFF_DEPTH=1`, so `getClientAddress()` is the address nginx set. Bind it to `127.0.0.1` or a private network (`HOST`, `PORT`): with `ADDRESS_HEADER` set, anyone who reaches it directly could choose their own address. Set `ORIGIN` to the public URL.
- **nginx** also blocks SvelteKit's one remaining URL, which this app can't disguise: `location ~ /__route\.js$ { return 404; }`.
- **The API** lists this app's address in `FORWARDED_ALLOW_IPS` (`127.0.0.1` on the same host, the default) and must not be proxied publicly: `/ingest/...` would let anyone report visits. Only this app and the exhibit's server (`../web`) call it.

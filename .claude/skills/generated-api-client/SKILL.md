---
name: generated-api-client
description: Check that the Attenborough web frontend never calls the API by hand (fetch, string endpoints, copied types) and always uses the hey-api generated client in web/src/lib/client. Use after any change in web/, when adding or changing a page that loads API data, when reviewing frontend code, and whenever an API route or model changes.
---

# The generated API client, and nothing else

Every call from `web/` to the API goes through the SDK that `@hey-api/openapi-ts` generates into `web/src/lib/client/` from `api/src/openapi.json`. That means no hand-written `fetch`, no endpoint strings, no copied request or response types, and no edits to `src/lib/client/`. The pattern, in a server `load` function (`+page.server.ts`), is described in `web/README.md` ("The API client is generated"):

```ts
const api = apiOptions(fetch); // $lib/server/api: the API's address, plus SvelteKit's fetch
const rows = unwrap(await ipGetIpActivity({ ...api, path: { ip_addr }, query: { take } }));
```

Passing SvelteKit's `fetch` into `apiOptions(fetch)` is correct: it hands the client the function to call, and doesn't make a request itself.

## 1. Run the check

It is an ESLint rule (`no-restricted-syntax` in `web/eslint.config.js`, the `API_BY_HAND` list), so it runs in `mise run check` (the `web-lint` step), and in `mise run web-lint` or `npm run lint` in `web/`. It fails on:

- a call to `fetch(...)`, `globalThis.fetch(...)` or `event.fetch(...)`
- `new XMLHttpRequest`, `EventSource`, `WebSocket` or `Request`
- an API path written out as a string or template literal: `'/exhibit/meta'`, `` `/exhibit/ip/${ip}/activity` ``
- importing the client's internals (`$lib/client/client…`, `$lib/client/core…`), e.g. for `client.get({ url })` or `createClient`

Never disable or narrow the rule, or add `eslint-disable`, to get code through. If there's a genuine non-API need for `fetch` (e.g. a third-party service), stop and ask the user.

## 2. Review what the rule can't see

Lint only sees JavaScript syntax. Check changed code by eye for:

- **Copied API types.** An `interface` or `type` that mirrors an API model (`ActivityRow`, `{ ip_address: string; … }`). Import it from `$lib/client` instead (`types.gen.ts`), or derive it from an SDK function's return type.
- **API paths hidden in markup or other strings:** `<form action="/exhibit/…">`, a URL built with `new URL(…)`, `API_BASE_URL` concatenated with a path. Only `$lib/server/api.ts` may read `API_BASE_URL`.
- **Calls from the browser.** The API is called only from server `load` functions, never from `+page.ts`, `+page.svelte` or components.
- **Hand-rolled error handling.** Every result goes through `unwrap` from `$lib/server/api`, not through checks on `response.status` in each page.
- **Duplicated API settings.** Values such as the page size come from `metaGetMeta` (`GET /exhibit/meta`), not from constants in `web/`.

A quick sweep for the markup and URL cases (from the repo root):

```sh
grep -rnE "/exhibit|API_BASE_URL|new URL\(" web/src --include=*.ts --include=*.svelte \
  | grep -vE "^web/src/lib/(client/|server/api\.ts)"
```

Anything it prints needs judging: a mention in a comment is fine (`paging.ts` names `/exhibit/meta` in its doc comment), a URL is not.

## 3. If the client is missing what you need

Don't work around it. Change the API instead, and regenerate:

1. Add or change the route or model in `api/`. If a generated function name reads badly, fix the operation ID in the API (`main.py:_operation_id`, `Router` route names).
2. Restart the API (it rewrites `api/src/openapi.json`), then `mise run web-gen-types`.
3. The client only includes `/exhibit/…` operations, minus `/test` (`web/openapi-ts.config.ts`). A route outside `/exhibit` isn't meant for the frontend.
4. Commit the regenerated `web/src/lib/client/` together with the API change.

Finish with `mise run fix` and `mise run check`.

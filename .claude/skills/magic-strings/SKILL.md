---
name: magic-strings
description: Find and fix magic strings and numbers and repeated string literals in the Attenborough code (Python and TypeScript/Svelte, each with a scanner), replacing them with enums, named constants, or helpers. Part of the post-change checklist after `mise run check`, and use it whenever reviewing or cleaning up code.
---

# Magic strings

The user dislikes magic strings and repeated strings, and prefers enums or named constants wherever they apply. Run this after every change to Python or TypeScript/Svelte code, after `mise run check`. The same rules apply to both halves.

Magic **numbers** in `web/` are a lint error (`@typescript-eslint/no-magic-numbers`, in `mise run check`); -1, 0 and 1 are allowed. Name the number, or use a library's constant: HTTP statuses come from `constants.HTTP_STATUS_*` in `node:http2` (server code), as the API uses `starlette.status`.

## 1. Scan

```sh
mise run api-magic-strings                              # from the repo root; or, from api/:
uv run python scripts/find_magic_strings.py            # src/ and scripts/
uv run python scripts/find_magic_strings.py <paths...> # narrower

mise run web-magic-strings                              # from the repo root; or, from web/:
node scripts/find-magic-strings.ts                     # src/ and scripts/
node scripts/find-magic-strings.ts <paths...>          # narrower
```

The web scanner is the same tool for TypeScript: it scans `.ts` files and the `<script>` blocks of `.svelte` files, with roles `===`/`!==`/`in` operands, `case` labels, element-access keys and `.get()`/`.has()`/`.set()`/`.delete()` keys. It skips imports, type-level literals (TypeScript already checks those), template-literal fragments and the generated client (`src/lib/client/`). It can't see markup: a literal in an attribute (`<input name="address">`) that code elsewhere reads is a repeated string too, so check markup by eye and bind the constant (`name={ADDRESS_PARAM}`).

The Python scanner lists every string literal that is **repeated** (same value more than once across the scanned files) or used as a **key or compared value** (`==`, `!=`, `in`, `match` patterns, subscripts, `.get()`/`.pop()`/`.setdefault()`), with each location and role. It skips docstrings, f-string fragments, route-decorator arguments, and generated sqlc modules. It always exits 0: some candidates are legitimately accepted (below), so it is a review list, not a gate, and isn't part of `mise run check`. **Your judgement of each finding is the verdict.**

The scanner cannot see strings hidden inside other strings, such as a header name inside an SQL literal (`headers->>'x-probe'`) or a URL inside an HTML form. Check new code for those by eye; pass such values as query parameters or interpolate the named constant instead.

## 2. Judge each candidate

**Fix it (use an enum, a named constant, or a helper)** when the literal:
- is a closed set of values: router groups, HTTP methods, event types, subcommand names, statuses. Use the existing enum if there is one (`RouterGroup`, `db.enums.*`, stdlib `http.HTTPMethod`/`HTTPStatus`); otherwise add a `StrEnum` next to its single owner.
- is compared, matched, or branched on (`== "summary"`, `case {"type": "http.response.start"}`). Use an enum member, which also works as a `match` value pattern (`case {"type": Kind.MEMBER}`), or a named constant.
- appears more than once with the **same meaning**: the same path declared for GET and POST, a decoy password, a header name written and later read. Define it once, in the module that owns it.
- repeats a pattern of access, such as the same dict key read in several places. Wrap it in a small helper or typed accessor rather than repeating the key.

**Accept it** only when:
- it is a dict key or protocol field that is guaranteed to be present and is read **once**: `scope.get("route")`, `request.headers.get("user-agent")`, `message["status"]` in one pattern.
- it is human-facing text used once: log messages, exception details, decoy HTML, help text.
- it is an idiom that tools exempt too: `""`, `"__main__"`.
- TypeScript already checks its spelling and it is an independent choice: option values typed as literal unions, such as `dateStyle: 'medium'` and `timeStyle: 'medium'` in `$lib/format.ts`.
- it is a test, or a probe acting as an external client, that deliberately restates the expected value or URL independently of the implementation (`assert response.json() == {"content": "Hello, world!"}`). Repeats *within* that test code still get constants.
- it is a coincidence: equal values with unrelated meanings (`"/"` as a route and as a separator in `.replace("/", ".")`). Do not merge unrelated meanings into one constant.
- it is in generated code. Change the SQL source instead (`.claude/rules/database.md`).

When unsure whether two equal values share a meaning, ask: "if one changed, must the other change too?" If yes, they are one constant.

## 3. Fix one finding at a time

For each finding to fix:
1. Make the smallest change that removes it. Reuse an existing enum or constant before creating one, and keep new constants private (`_NAME` in Python, unexported in TypeScript) unless another module needs them. Query parameters shared by pages and `load` functions live in `web/src/lib/params.ts`. Keep import direction acyclic (see `.claude/rules/backend.md`): a constant belongs to the lowest-level module that owns the meaning.
2. Run `mise run fix` and `mise run check` (see `CLAUDE.md`), then re-run the scanner to confirm the finding is gone and nothing new appeared.
3. If the change touches request handling or telemetry, finish with the `telemetry-testing` skill.

Report which candidates you fixed, and which you accepted with the reason for each.

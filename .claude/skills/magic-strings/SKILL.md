---
name: magic-strings
description: Find and fix magic strings and repeated string literals in the Attenborough code (Python via a scanner, TypeScript/Svelte by review), replacing them with enums, named constants, or helpers. Part of the post-change checklist after `mise run check`, and use it whenever reviewing or cleaning up code.
---

# Magic strings

The user dislikes magic strings and repeated strings, and prefers enums or named constants wherever they apply. Run this after every change to Python code, after `mise run check`. The same rules apply to TypeScript and Svelte in `web/`; there is no scanner there, so review new code by eye against section 2 (module-level `const`s such as `PAGE_SIZE`, or a helper such as `pageHref`).

## 1. Scan

From `api/`:

```sh
mise run api-magic-strings                              # from the repo root; or, from api/:
uv run python scripts/find_magic_strings.py            # src/ and scripts/
uv run python scripts/find_magic_strings.py <paths...> # narrower
```

It lists every string literal that is **repeated** (same value more than once across the scanned files) or used as a **key or compared value** (`==`, `!=`, `in`, `match` patterns, subscripts, `.get()`/`.pop()`/`.setdefault()`), with each location and role. It skips docstrings, f-string fragments, route-decorator arguments, and generated sqlc modules. It always exits 0: some candidates are legitimately accepted (below), so it is a review list, not a gate, and isn't part of `mise run check`. **Your judgement of each finding is the verdict.**

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
- it is a test, or a probe acting as an external client, that deliberately restates the expected value or URL independently of the implementation (`assert response.json() == {"content": "Hello, world!"}`). Repeats *within* that test code still get constants.
- it is a coincidence: equal values with unrelated meanings (`"/"` as a route and as a separator in `.replace("/", ".")`). Do not merge unrelated meanings into one constant.
- it is in generated code. Change the SQL source instead (`.claude/rules/database.md`).

When unsure whether two equal values share a meaning, ask: "if one changed, must the other change too?" If yes, they are one constant.

## 3. Fix one finding at a time

For each finding to fix:
1. Make the smallest change that removes it. Reuse an existing enum or constant before creating one, and keep new constants private (`_NAME`) unless another module needs them. Keep import direction acyclic (see `.claude/rules/backend.md`): a constant belongs to the lowest-level module that owns the meaning.
2. Run `mise run fix` and `mise run check` (see `CLAUDE.md`), then re-run the scanner to confirm the finding is gone and nothing new appeared.
3. If the change touches request handling or telemetry, finish with the `telemetry-testing` skill.

Report which candidates you fixed, and which you accepted with the reason for each.

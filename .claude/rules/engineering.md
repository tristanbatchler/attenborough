# Engineering workflow

- Start by inspecting `git status --short` and relevant diffs. Do not overwrite existing work.
- Trace the behaviour from entrypoint through callers, dependencies, and persistence before changing architecture.
- For a circular import, draw the actual import cycle and identify which dependency points in the wrong direction. Prefer moving shared types/constants or introducing a narrow lower-level module over lazy imports or broad module reshuffles. Do not choose a fix until the current dependency graph and runtime constraints are understood.
- For reorganisation work, separate mechanical moves from behaviour changes where practical. Keep each stage reviewable and verify imports/tests after each stage.
- Prefer explicit dependencies and small modules with clear ownership. Avoid import-time I/O, application startup work during imports, and hidden global state unless the existing architecture requires it.
- Do not add compatibility wrappers, generic registries, service layers, or abstractions without a concrete need in the current code.
- Ask before changing public API contracts, database semantics, deployment behaviour, or multiple architectural boundaries.
- Do not run destructive commands or perform irreversible actions without explicit approval.

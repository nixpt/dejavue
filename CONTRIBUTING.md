# Contributing

Deja Vue is in early development. The on-disk format and command surface may
evolve before v1.0. Contributions are welcome but read this first.

## Before opening a PR

1. **Read the design docs in `docs/`** — particularly
   `docs/04-design-perspective.md` for the design rationale and
   `docs/05-v0.1-scope.md` for the build spec and architecture ruling. The
   non-goals are as important as the goals.
2. **Read `README.md` end to end** — especially the *What dejavue is NOT*
   and *Architecture and migration path* sections. Many obvious-looking
   contributions are explicitly out of scope.
3. **Run the test suite** — `bash tests/test_dejavue.sh` from the repo
   root. Expect `Tests passed: 33/33` on a clean checkout.

## What kinds of contributions

Welcome:

- New tests covering edge cases the suite misses.
- Bug fixes with a regression test.
- README clarity / examples / quickstart improvements.
- Performance fixes that do not introduce dependencies.
- New `dejavue` subcommands that fit the philosophy: zero-ceremony,
  stdlib-only, single-file, no infrastructure.

Likely to be rejected:

- New external Python dependencies. Stdlib-only is the design contract.
  Embeddings, vector stores, and async runtimes belong in v0.2+ behind a
  feature flag, not at the v0.1 core.
- Splitting `dejavue.py` into multiple files or a package. Single file is
  the design.
- Replacing FTS5 with a different recall engine in v0.1. FTS5 + LIKE
  fallback is the contract until v0.2 ships the semantic-recall flag.
- New CLI commands that overlap with `git` (file history, branches, diffs).
- Cross-repo memory features. Cross-repo coordination is out of scope.
- MCP server / MCP tools — that's v0.3 work, deferred until the format
  stabilizes.

## Code style

- Python 3, stdlib only.
- No type hints unless they genuinely help (the existing file has none).
- One-line comments only where the *why* is non-obvious. Do not write
  multi-paragraph docstrings.
- No emojis in code or output.
- Section dividers in source via `# ── name ──`.
- New commands follow the same wiring pattern as the existing ones in
  `main()`.

## Worthiness gate

The same rule that governs what dejavue captures governs what changes are
worth submitting:

> If removing this change would not confuse a future contributor reading
> the code and git log, do not submit it.

Cosmetic refactors, premature abstractions, and "while I'm in here" sweeps
do more harm than the original code. The minimum useful change beats the
maximum thoughtful change.

## Filing issues

Issues are welcome for:

- Bugs (please include reproduction steps and a minimal `.dejavue/`
  snippet if relevant).
- Design questions about the v0.x roadmap.
- Format-evolution proposals for the `.dejavue/` on-disk layout — these
  need broad consensus before landing because the format is the open
  contract.

Not appropriate for issues:

- Feature requests that are already documented as v0.2+ work in
  `CHANGELOG.md` "Notes for v0.2" or `README.md` migration path.
- Cross-repo memory federation requests.

## License

By contributing you agree your contributions are licensed under the MIT
License (see `LICENSE`).

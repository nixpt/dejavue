---
name: dejavue
purpose: Portable repo-local context and memory protocol for coding agents
dcp: DCP/1.0
---

# Context

<!-- The DCP instruction layer: what an agent should *do* in this repo.
     Source of truth — adapters (CLAUDE.md / AGENTS.md / …) are generated
     from this file via `dejavue export --target <tool>`. -->

## Operating Rules

- Keep the base loop zero-ceremony: `init -> start -> decision -> state -> handoff`
  must work with only Python stdlib, Git, and the files created by `init`.
- Treat `.dejavue/context.md` as the canonical instruction layer. Adapter files
  such as `CLAUDE.md` and `AGENTS.md` are generated compatibility targets.
- Capture public-safe lessons from adopter repos, but generalize them before
  recording them here. Do not copy downstream project histories, local paths,
  or unrelated repo names into this reference repo.
- Preserve the single-file implementation bias for `dejavue.py` unless a future
  decision explicitly supersedes it.
- When changing user-facing behavior, update tests, README/ROADMAP docs, shell
  completions, and the relevant `.dejavue` memory in the same change.

## Build / Test

- Version check: `python3 ./dejavue.py version`
- Health check: `python3 ./dejavue.py check`
- Full integration suite: `bash tests/test_dejavue.sh`
- Public scrub verification: `git grep -n -I -E '<term-regex>' $(git rev-list --all) -- ':!*.db'`
- Regenerate adapters after `context.md` changes: `python3 ./dejavue.py export --target all`

## Architecture Map

- `dejavue.py` is the reference CLI and protocol implementation.
- `.dejavue/` contains this repo's self-hosted memory: timeline, decisions,
  state, handoff, patterns, and instruction context.
- `tests/test_dejavue.sh` is the broad integration suite and should grow with
  every command or protocol behavior change.
- `docs/dcp-spec.md` is the citable protocol specification.
- `README.md`, `CHANGELOG.md`, and `ROADMAP.md` are the public-facing product
  surface and release/history map.
- `skills/dejavue/` and `skills/dejavue-workflow/` are agent-facing skill docs
  shipped with the repo.

## Memory

Decisions, blockers, and constraints are captured in `.dejavue/` — run
`dejavue context` for the boot packet and `dejavue recall <query>` to search.

# Changelog

All notable changes to this project will be documented in this file. The
format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
the project does not currently follow semver strictly because the on-disk
format may evolve before v1.0.

## [0.1.0] — 2026-05-13

First productized release. Single-file Python 3 CLI, stdlib only, zero
infrastructure. Drops into any git repo in 5 seconds.

### Added

- **13 commands** covering the full session lifecycle: `init`, `start`,
  `changed`, `decision`, `state`, `handoff`, `context`, `since`, `ingest`,
  `recall`, `worthiness`, `get`, `list`, `annotate`.
- **`since <ref>` — the killer command.** Temporal delta over an agent's
  last session, a git commit, or an ISO date. Outputs git delta + timeline
  events + decisions + state transitions + handoffs + top keyword topics.
- **FTS5 keyword recall** via sqlite, with automatic LIKE fallback when
  FTS5 is unavailable. Index rebuilds when any source file is newer.
- **Git post-commit hook** installed by `dejavue init`. Auto-records one
  `file_changed` event per touched file on every commit. Hook uses absolute
  path resolution so it works across git worktrees (one of v0.1's most
  important properties).
- **`.gitattributes merge=union`** for `timeline.jsonl` and `decisions.md`.
  Critical for multi-branch / multi-worktree workflows — without this every
  wave merge conflicts on `timeline.jsonl` because both branches added
  unique lines and git's default text merger can't see that append-only
  semantics make union safe.
- **Rejected-alternatives field** on decision events. `dejavue decision X
  --reason Y --rejected "option: reason"` (repeatable). The reasoning that
  did not make it into the code is the part future agents cost the most to
  rediscover.
- **`ingest` scrape** — one-shot ingest of git log + `.claude/CLAUDE.md` +
  `AGENTS.md` + `.cursorrules` + `CHANGELOG.md` + `docs/decisions/` +
  `docs/adr/` + `README.md` into the timeline. Marker-gated by
  `.dejavue/ingested.lock`; `--force` re-runs.
- **`worthiness` gate** — built-in capture/skip pedagogy. Auto-prints on
  first use of any command. The rule of thumb: if removing a memory would
  not confuse a future agent reading the code and git log, do not write it.
- **`get` / `list` / `annotate`** — direct-fetch, discovery, and
  append-without-rewrite primitives.
- **33-test integration suite** at `tests/test_dejavue.sh`. Pure bash, no
  `bats` / `pytest` deps. Covers all 13 commands plus edge cases (hook
  clobber guard, ingest re-run guard, since edge cases, FTS5/LIKE fallback
  verification via source grep).
- **README + design docs.** README covers install / quickstart / commands /
  worthiness / concurrency. Internal design docs live in `docs/`.

### Architecture

`.dejavue/` is the file format. Other MCP-aware agents and rich servers
(such as joker-mcp) will be able to consume it via thin shim tools in
future releases. The format is the open contract.

Migration path: v0.1 standalone → v0.2 `--semantic` flag via external
embedder → v0.3 MCP integration → v0.4 upgrade path to richer per-repo
memory systems.

### What this is not

Not a replacement for git. Not a vector database or embedding store. Not
an MCP server. Not cross-repo memory federation. See
`docs/04-foreman-perspective.md` for the full overlap analysis with adjacent
tools.

### Notes for v0.2

- `--semantic` flag will land once an external embedder backend is wired
  in. Embedder unavailability must never block a memory write.
- `flock(2)` on `rebuild_fts` and `ingest` for the concurrent-same-tree
  edge case (deferred — the worktree-per-branch pattern v0.1 is designed
  for does not hit it).

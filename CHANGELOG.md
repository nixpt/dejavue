# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
**The on-disk format is stable as of v1.0.0.** `.dejavue/` files written by
any v1.x release can be read by any later v1.x release without migration.

## [1.3.0] — 2026-05-28

36 commands, 100/100 tests.

### Added

- **`dejavue diff <from> [<to>]`** — compare dejavue memory between two refs.
  When both refs resolve to ISO timestamps, shows decisions, notes, and state
  updates added in the window. When refs are git objects, uses `git show
  <ref>:.dejavue/state.md` and `decisions.md` with `difflib.unified_diff` for
  a structural diff of the memory documents. Date refs are padded to full-day
  boundaries (T00:00:00 / T23:59:59) so `diff 2026-05-01 2026-05-15` is
  inclusive of both endpoints.
- **`dejavue timeline [--by {day,week,month}] [--agent NAME]`** — ASCII
  activity chart. Groups events into time buckets, renders a proportional `█`
  bar per period, reports totals. `--agent` filters to one contributor's
  activity.
- **`dejavue check --fix`** — auto-repair mode. For each WARN item with a
  known fix (missing hooks, wrong hook path, missing `.gitattributes` /
  `.gitignore` entries, stale FTS database) the repair is applied and the
  report line shows `↻ auto-fixed` instead of `⚠ warn`. Pass-only checks
  and non-fixable WARNs behave as before.
- **`dejavue tag {list,filter <tag>}`** — tag management: `list` shows all
  unique tags with event counts; `filter <tag>` shows all events carrying
  that tag. Tags set via `dejavue note --tag` or `dejavue decision --tag`.
- **`dejavue note-commit <sha>`** — write a git note on a commit that links
  it to the most-recent dejavue event. Uses `git notes append` — metadata
  stored outside the commit object, SHA unchanged. `dejavue link <sha>` now
  also reads these git notes and displays any `Dejavue-Event:` entries.
- **`event_type` indexed in FTS5** — `dejavue recall blocker` now surfaces
  events recorded as `--type blocker`; same for `question`, `experiment`, etc.
- **`dejavue since` now shows a Notes section** — `note` events in the window
  are surfaced alongside decisions, state updates, and handoffs, with tag and
  sub-type labels.

### Changed

- `difflib` added to imports (stdlib; no new runtime dep).
- Test suite: 88 → 100 (100/100 green).

## [1.2.0] — 2026-05-28

31 commands, 88/88 tests.

### Added

- **Richer event sub-types** — `dejavue decision` gains `--type {decision,
  blocker,claim,question,experiment,checkpoint}` (default `decision`). Stored as
  `event_type` field in the timeline; `[BLOCKER]`-style prefix appears in
  `decisions.md`. `dejavue note` gains `--type {note,blocker,claim,question,
  observation}`. Both types work with `dejavue log --type` filtering.
- **`dejavue stats`** — timeline statistics: total events, date range, file
  size, counts by event type (with mini bar chart), by event sub-type, by
  agent, and by tag. ~50 LoC.
- **`dejavue export --format {json,md}`** — export all memory (state, handoff,
  decisions, references, full event list) as structured JSON or a single
  Markdown document. Useful for sharing context or archiving a project's
  memory snapshot.
- **`dejavue reference {create,list,update,view}`** — manage reference cards
  in `.dejavue/references/` through the CLI. `create` supports `--template
  {default,api,design}` to scaffold the right structure; `update --content`
  overwrites; `view` prints. Creation events are recorded in the timeline.
- **`dejavue link <sha>`** — show all dejavue events recorded for a git commit
  SHA. Surfaces `file_changed` events captured by the post-commit hook plus
  any decision/note that mentions the short SHA. The reverse-lookup complement
  to `dejavue blame <file>`.
- **`dejavue search`** — discoverable alias for `recall` (same flags:
  `--semantic`, `--limit N`). Matches the mental model of "search my memory".
- **`dejavue context -n N`** — control how many recent timeline events the
  boot packet shows (default 10).
- **Tiered embedder auto-detection** — when `DEJAVUE_EMBEDDER_URL` is unset
  or `"auto"`, the embedder tier tries: (1) local Ollama (`localhost:11434`
  liveness probe), (2) OpenAI API (if `OPENAI_API_KEY` is set), (3) FTS5
  fallback. OpenAI calls include the `Authorization: Bearer` header
  automatically. Previously a fixed default URL was always used.
- **Model-aware embedding cache** — `embeddings.jsonl` entries now filter by
  model name. Stale vectors from a previously-configured model are ignored
  (not returned) when the active model changes. Legacy entries without a
  `model` field continue to be accepted.

### Changed

- Test suite: 71 → 88 (88/88 green).
- `dejavue decision` output line now says "Blocker recorded: …" / "Question
  recorded: …" when `--type` is non-default, matching the sub-type label.

## [1.1.0] — 2026-05-28

25 commands, 71/71 tests.

### Added

- **`dejavue check`** — git-fsck-style health check. Reports PASS/WARN/FAIL
  for: JSONL validity, core docs (state.md, decisions.md, handoff.md), hook
  installation + path correctness (post-commit + pre-push), `.gitattributes`
  merge=union, `.gitignore` entries, FTS freshness, `references/map.md`.
- **`dejavue archive --before <YYYY-MM-DD>`** — timeline compaction. Drops
  `file_changed` events older than the cutoff; preserves decisions, state
  updates, handoffs, and all other event types. Dry-run by default;
  `--yes` applies. Backup written to `timeline.jsonl.bak-<date>` before
  modification.
- **`dejavue roster`** — agent activity summary: first/last active date,
  session count, decision count, note count, handoff count per agent.
  Sorted by most-recent activity.
- **`dejavue config {list,get,set,unset}`** — manage per-repo
  `.dejavue/config` through the CLI rather than hand-editing. `config set
  agent_name mybot`, `config get agent_name`, `config list`, `config unset`.
- **`dejavue install-skill`** — auto-install `skills/dejavue/` and
  `skills/dejavue-workflow/` to the user's agent skills directory
  (`~/.claude/skills/` by default). Pass `--dir` to target a different
  location; `--force` to overwrite existing symlinks.
- **`dejavue log --reverse`** — show oldest events first.
- **`dejavue recall --limit N`** — cap results (default 10). Works for both
  FTS5 and `--semantic` recall.
- **Embedder circuit breaker** — after 3 consecutive failures the circuit
  opens; `_embed_one` returns `None` immediately without hitting the endpoint
  for 5 minutes. Resets on first success. State in
  `.dejavue/embedder_circuit.json` (gitignored, local-only).

### Changed

- `.gitignore` entries now also cover `embedder_circuit.json` and
  `timeline.jsonl.bak-*` (archive backups).
- `dejavue log` now defaults to newest-first (unchanged) with `--reverse`
  for oldest-first.
- Test suite: 62 → 71 (71/71 green).

## [1.0.0] — 2026-05-27

Format declared stable. 20 commands, 62/62 tests.

### Added (v0.3 capture-discipline wave)

- **Ambient agent identity resolver** — `--agent` now defaults to
  `AGENT_NAME` env var, then `CLAUDE_CLI`, then `GIT_AUTHOR_NAME`, then
  `.dejavue/config agent_name`, then `"unknown"`. The `default="unknown"`
  anti-pattern is gone; most invocations now auto-resolve the caller.
- **`dejavue context` staleness warnings** — prints `⚠` notices at the
  bottom of the context output when `state.md` is a default stub or older
  than 7 days, or `handoff.md` is the default template. Pre-push hook
  routes through `context --check-stale` (stderr-only) so the safety net
  catches pushes even without an interactive session.
- **`dejavue init --ingest`** — run ingest immediately at init time.
  Saves one manual step for the common audit tool-style first-time setup.
- **`dejavue init --map`** — scaffold `references/map.md` with a
  section-per-concern template (layout, entry points, invariants, deps).
- **Pre-push hook** — installed alongside the post-commit hook by
  `dejavue init`. Runs `context --check-stale` so staleness warnings
  surface before code leaves the local machine.
- **`.gitignore` entries** — `dejavue init` now also appends canonical
  per-checkout ignores (`fts.db`, `embeddings.jsonl`, `.locks/`, etc.) to
  `.gitignore`. Idempotent; won't re-add if already present.
- **`dejavue ingest --generate-map`** — lang-aware auto-population of
  `references/map.md`. Detects Rust (Cargo.toml), Python (pyproject.toml /
  setup.py), JavaScript/TypeScript (package.json), and Go (go.mod); pulls
  crate/package name and top-level directories; fills in the template
  sections automatically.
- **`flock(2)` concurrent safety** — `rebuild_fts` and `ingest` now take
  an advisory exclusive lock under `.dejavue/.locks/` before writing.
  POSIX-only (`fcntl.flock`); graceful no-op on Windows.
- **Per-repo `.dejavue/config`** — `key=value` file for persistent
  per-repo defaults: `agent_name`, `embedder_url`, `embedder_model`. Read
  by `resolve_agent()`; empty file or absent file = no change in behavior.

### Added (v1.0 new commands)

- **`dejavue version`** — print `dejavue 1.0.0`.
- **`dejavue status`** — git-status-style one-liner: active agent, event
  count, last decision (title + date), open next-steps from `handoff.md`,
  and inline staleness warnings. ~25 LoC.
- **`dejavue log`** — formatted timeline view with `--since <date|commit>`,
  `--agent <name>`, `--type <event_type>`, and `--oneline` flags. Rejected
  alternatives shown inline for decision events. ~55 LoC.
- **`dejavue blame <file>`** — "why does this file exist?" Surface all
  decisions, state updates, and notes whose text mentions the file path.
  Mirrors `git blame` ergonomics but for the *why* layer. ~30 LoC.
- **`dejavue note <text> --tag <tag>`** — lightweight fact storage between
  `annotate` (no-rewrite append) and `decision` (heavy). Records a `note`
  event with an optional tag for future filtering. ~10 LoC.

### Changed

- `dejavue init` now installs both post-commit and pre-push hooks.
- `dejavue context` lists `references/*.md` files (title + filename) when
  any exist.
- FTS5 rebuild and ingest are now protected by `fcntl.flock`.
- `--agent` default changed from hard-coded `"unknown"` to `resolve_agent()`
  across all commands.
- Test suite: 33 → 42 → 62 tests (62/62 green).

### Notes

- Stdlib only throughout — no new runtime dependencies.
- The `note` event type is a new schema field; older consumers that filter
  by `event` type will ignore it (additive change, backward-compatible).
- `--generate-map` output is a starter template; fill in the invariants
  and external-deps sections by hand after generation.

## [0.2.0] — 2026-05-13

Semantic recall. No new runtime dependencies.

### Added

- **`dejavue recall <q> --semantic`** — cosine-ranked semantic recall.
  Embeds the query against an OpenAI-compatible `/v1/embeddings` endpoint
  (default `http://localhost:11434/v1/embeddings`, model `nomic-embed-text`;
  override via `DEJAVUE_EMBEDDER_URL` / `DEJAVUE_EMBEDDER_MODEL`).
- **`.dejavue/embeddings.jsonl`** — hash-keyed vector cache, populated
  lazily as `--semantic` recalls encounter events for the first time.
  Stable across timeline reorderings/duplicates because the join key is
  a content hash (sha256[:16]) of the timeline line. Gitignored
  (rebuildable, model-specific) — treat as a local cache like `fts.db`.
- **Graceful fallback.** When the embedder is unreachable, returns
  non-200, or returns malformed JSON, `--semantic` prints one warning
  line to stderr and proceeds with FTS5 keyword recall. Memory writes
  never block on the embedder being up.

### Notes

- Stdlib only — `urllib.request` for the HTTP call, `hashlib` for
  content-addressing, `math` for cosine. No new runtime dependencies.
- `nomic-embed-text` (768-dim, `ollama pull nomic-embed-text`, ~274 MB)
  is the verified default; any OpenAI-compat `/v1/embeddings` endpoint
  works.

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
  path resolution so it works across git worktrees.
- **`.gitattributes merge=union`** for `timeline.jsonl` and `decisions.md`.
  Critical for multi-branch / multi-worktree workflows.
- **Rejected-alternatives field** on decision events (`--rejected`).
- **`ingest` scrape** — one-shot ingest of git log + `.claude/CLAUDE.md` +
  `AGENTS.md` + `.cursorrules` + `CHANGELOG.md` + `docs/decisions/` +
  `docs/adr/` + `README.md` into the timeline.
- **`worthiness` gate** — built-in capture/skip pedagogy.
- **`get` / `list` / `annotate`** — direct-fetch, discovery, and
  append-without-rewrite primitives.
- **33-test integration suite** at `tests/test_dejavue.sh`.

### Architecture

`.dejavue/` is the file format. The format is the open contract.

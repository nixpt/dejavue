# Changelog

All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
**The on-disk format is stable as of v1.0.0.** `.dejavue/` files written by
any v1.x release can be read by any later v1.x release without migration.

## [Unreleased]

### Added

- **`dejavue plan TEXT [--kind …] [--target PATH] [--list]`** — capture an actionable
  item (issue / gap / opportunity / idea / cleanup) into **the repo's own planning
  convention**, not into a dejavue-specific file. Resolves the target in precedence
  order: `--target` → config `plan.target` → first existing known convention
  (`.jagent/planning/TASKS.md`, `.jagent/TODO.md`, `TODO.md`, `docs/TODO.md`,
  `TASKS.md`) → `.dejavue/plan.md` fallback. It prints *which* target it chose and
  *why*, because silently guessing where to file someone's findings is how captured
  work gets lost. Also appends a `plan` event to the timeline, so a captured item
  stays recallable and attributable even if the planner file is later rewritten.
  The fallback preserves the zero-ceremony guarantee: capture must never fail merely
  because a repo has no planner.
- **`dejavue rule TEXT [--scope SCOPE]`** — record a **soft project rule / convention**
  in `rules.md`, surfaced in `dejavue context`. Fills the missing normative tier:
  `pattern` is descriptive ("this is how the code happens to be written"), `invariant`
  is hard ("this must always hold"), and `rule` is the advisory middle ("this is how we
  do things here" — depart from it knowingly and say why). Rules ship in the boot packet
  so an arriving agent reads a project's conventions instead of violating them by accident.

- **`dejavue changelog <range>`** — generate a why-aware markdown changelog from dejavue
  events over a git range (e.g. `v2.1.0..HEAD`, or a single ref = `ref..HEAD`): **Decisions**
  (with confidence labels and "⚠ later superseded by" annotations), **Traps & incidents**,
  **Notes**, and the git **Commits**. A `since` + `export` composition. First P1 item from
  the design backlog audit.
- **Per-entry freshness / expiry** — optional `freshness` plus `expires_after` metadata on
  decisions and notes, with `context` / `since` / `recall` flagging expired entries at read
  time. The base timeline stays append-only; no background expiry process.
- **`derived_from` lineage** — repeatable lineage pointers on `decision` and `note`, surfaced
  in read-time context and indexed by `recall` so reasoning chains stay queryable without a
  graph store.
- **Memory stability classes** — optional `--stability` labels plus inferred read-time classes
  for the core memory surfaces. Keeps the retention taxonomy visible without changing the
  on-disk format.
- **`dejavue capabilities [--format json|text]`** — report implementation and repo-local
  DCP capabilities: version, supported commands, optional feature support, hook status,
  and managed adapter status. First P2 item: capability negotiation for agents and thin
  adapters.
- **`dejavue branch {start,summary,close}`** and **`dejavue merge-summary <base> <branch>`**
  — capture branch intent/closeout as normal timeline events and replay branch-scoped memory
  plus commits before a merge. Second P2 item: git-workflow memory for multi-agent branches.
- **`dejavue epoch {begin,end,list}`** and **`dejavue milestone <name>`** — record named
  project eras and checkpoint anchors as timeline events, surface open epochs/milestones in
  `context`, and list epoch history. Completes the current P2 roadmap set.
- **`dejavue explain <file|commit>`** — compose git history with DejaVue decisions, notes,
  artifacts, rejected alternatives, lineage, supersession, and linked commit events to answer
  why a file or commit exists.
- **`dejavue squash-summary <branch> [--base REF]`** — synthesize a squash-merge commit
  message from branch intent, decisions, notes, and commits.
- **`--author-type {human,agent,orchestrator,ci,bot}`** — core memory-writing commands
  can record writer class metadata separately from the `--agent` identity string, and
  read paths surface/index it for trust-aware recall.
- **`--tension LABEL`** — repeatable unresolved tradeoff metadata on core memory-writing
  commands (for example `security` / `performance`), surfaced in context/recall and kept
  distinct from rejected alternatives or supersession.
- **`--value LABEL`** — repeatable soft project philosophy metadata on core memory-writing
  commands (for example `local-first` / `capability-first`), surfaced in context/recall
  without turning values into enforced invariants.
- **`--domain-owner NAME`** and **`dejavue owners [NAME]`** — assign one normalized owner
  to core memory events, index it for recall, and list/filter owner-scoped memory without
  introducing a graph or registry.
- **`dejavue conflict record --reason TEXT [--path PATH]`** — record conflict-resolution
  rationale as timeline memory and surface it in `explain <file>`.

## [2.1.0] — 2026-06-06

**Institutional-memory P0 wave** — the five top-rated items from the design backlog roadmap
audit, making recall *relational* (`entities`, `--artifacts`) and *trustworthy*
(`--confidence`, `--supersedes` read-back), plus the missing `pattern` memory file and
robustness fixes. Two new commands (`pattern`, `entities`), four new fields, zero new
dependencies (Axiom 0 preserved). 161/161 tests.

### Added

- **`dejavue pattern "<text>"`** — record a discovered convention/pattern (naming,
  idiom, structure). Appends to `.dejavue/patterns.md` — the missing core memory
  file alongside `decisions.md` / `invariants.md` — and is surfaced by `context`,
  indexed by `recall`, `merge=union` in `.gitattributes`, and scaffolded by `init`.
  Same mold as `trap` / `invariant`. First P0 item from the design backlog roadmap audit.
- **`--entity <name>` on `decision`/`note`/`trap`/`incident`/`invariant`/`pattern`** +
  **`dejavue entities [<name>]`** — an optional repeatable subject field
  (`entities: ["auth-system", …]`, normalized to kebab-case) that links events *by
  subject*, complementing the single-valued `tag`. Entities are indexed by `recall`,
  matched by `blame <name>`, and `entities` lists them with counts (or filters events
  for one). Lightweight strings only — not a graph or registry (Axiom 0). Second P0
  item from the design backlog audit; the relational primitive that unlocks lineage/explain.
- **`--confidence {speculative,proposed,experimental,adopted,deprecated,verified}` on
  `decision` and `note`** — a recall-trust signal so brainstorms and firm decisions no
  longer look identical. Stored on the event, shown as a `[CONFIDENCE]` label in the
  `decisions.md` heading (alongside `--durability`), and indexed by `recall` (so
  `recall verified` / `recall speculative` work). Third P0 item from the design backlog audit.
- **`--supersedes` read-back** — `recall`, `since`, and `context` now surface
  "⚠ superseded by '<newer decision>'" on an overridden decision, so stale decisions
  stop looking authoritative. The `--supersedes` value was previously *write-only*
  (stored but never read). Matching is by title substring with **event-identity**
  self-exclusion (so a decision whose own ref is a substring of its title — e.g.
  "Cache layer" ⊂ "Cache layer v2" — isn't falsely flagged), robust to same-second
  decisions. Fourth P0 item, and closes the v2.0.1 contract.
- **`decision --artifacts <path>`** (repeatable) — explicitly bind the files a decision
  is about, so `blame <path>` matches it *precisely* instead of hoping the path appears in
  the title/reason text. Stored as `artifacts: [...]`, written to `decisions.md`, and
  FTS-indexed (`recall <path>` finds the decision). Fifth and final P0 item from the audit.

### Fixed

- **`_load_events()` ignores non-object timeline lines.** A valid-JSON-but-non-dict
  line (a bare `12345` / `null` / array from corruption or a manual edit) previously
  made every event consumer (`recall`, `since`, `blame`, `link`, `stats`, …) crash on
  `.get()`. Now filtered once at the loader, matching the "timeline is crash-proof" contract.

## [2.0.2] — 2026-06-06

**Correctness pass over the v2.0.1 feature set.** No new surface area; these fix
bugs in the commands v2.0.1 introduced (Axiom 0 preserved). 141/141 tests.

### Fixed

- **`note-commit --trailer` no longer corrupts the link.** The old path wrote the
  git note to the pre-amend SHA and then `git commit --amend` rewrote HEAD into a
  new SHA, orphaning the note; passing a non-HEAD SHA amended HEAD's message anyway,
  and any staged changes were silently folded into the commit. `--trailer` now
  requires the SHA to be HEAD and the index to be clean, amends *first*, then
  attaches the note to the shipped (post-amend) commit so note and trailer agree.
- **`VERSION` and `pyproject.toml` were stuck at `2.0.0`** through the v2.0.1 tag —
  `dejavue version` / `pip show` mislabelled the binary. Now report the real version.
- **`link` no longer crashes** on timeline events whose `commit`, `summary`, or
  `decision_reason` field is an explicit JSON `null` (`None[:7]` / `x in None`).
- **`since <base>..<tip>` now honors the tip.** The event window was bounded only by
  the base date, leaking everything after the tip into the listing; it now bounds
  both ends (open-ended only when the tip is `HEAD`), at second granularity.
- **`invariant` works before `init`** — it self-creates `.dejavue/` instead of
  crashing with `FileNotFoundError`.
- **`invariants.md` is now indexed by `recall`** (added to the FTS sources and the
  rebuild trigger), matching the other core docs.
- **`check` now verifies and repairs the `post-checkout` hook** that `init` installs.
- **`context` surfaces traps & incidents prominently** in their own section, so the
  highest-value memory no longer scrolls out of the recent-timeline tail. Tolerant
  of non-object timeline lines.
- **Shell completions cover the v2.0.1 commands** — `trap`, `incident`, `invariant`,
  `rejected`, and `decision --supersedes/--durability` were missing from all three.

## [2.0.1] — 2026-06-06

**v2.x agent workflow depth.** Six new commands and flags directly addressing
recurring agent friction points, from zero new dependencies (Axiom 0 preserved).

43 commands, 134/134 tests.

### Added

- **`dejavue trap "<text>"`** — first-class known-lie / trap event. Agents waste
  real time rediscovering misleading names, fake abstractions, and historical hacks.
  `trap` events surface prominently in `context` (and in `blame` when the trap text names the file).
- **`dejavue incident "<text>"`** — first-class operational incident. Outages, data
  corruption, failed migrations. Stored as `event_type: incident`.
- **`dejavue invariant "<text>"`** — architectural invariant. Appends a timestamped
  entry to `.dejavue/invariants.md` (scaffolded by `init`, surfaced by `context`,
  `merge=union` in `.gitattributes`).
- **`dejavue rejected [<query>]`** — show all decisions with rejected alternatives,
  optionally filtered by a topic. The "why not X?" question answered in one command.
- **`decision --supersedes <id>`** — record that a new decision supersedes an older
  one. Stored in event + shown as `Supersedes: …` in decisions.md.
- **`decision --durability {temporary,tactical,strategic,constitutional}`** — classify
  how long-lived a decision is. Label shown in the decisions.md heading.
- **`since <base>..<tip>`** — git revision range syntax (e.g. `main..HEAD`,
  `v1.0..v2.0`, `origin/main..HEAD`). Passes the explicit range to git log/diff.
- **`post-checkout` hook** — prints `dejavue status` on branch switch (guards on
  `$3==1` so file-checkout is not noisy). Installed by `dejavue init`.
- **`note-commit --trailer`** — opt-in flag to also amend the commit message with a
  `Dejavue-Event: <ts> | <summary>` trailer via `git interpret-trailers`, so the
  link travels with the commit without requiring git notes push. Never called from
  a hook.

### Fixed

- `note-commit`: null-guard bug — `ev.get("commit", "")` could still return `None`
  for events with an explicit null commit field; fixed to `(ev.get("commit") or "")`.

---

## [2.0.0] — 2026-06-05

**DejaVue Context Protocol (DCP/1.0).** dejavue becomes the source of truth for
agent context: `.dejavue/context.md` is the canonical instruction layer and the
per-tool files (CLAUDE.md / AGENTS.md / GEMINI.md / Copilot / Cursor) become
**generated, non-destructive adapter targets**. The format stays
backward-compatible — every v1.x `.dejavue/` reads unchanged, and the base loop
(init → start → decision → state → handoff) behaves identically with or without
DCP. Zero new runtime dependencies (stdlib only; Axiom 0).

35 commands, 121/121 tests.

### Added

- **`.dejavue/context.md`** — first-class DCP/1.0 instruction-layer artifact:
  `key: value` frontmatter (`name` / `purpose` / `dcp`) plus Operating Rules /
  Build·Test / Architecture Map / Memory sections. `dejavue init` scaffolds an
  empty template; its absence breaks nothing. `dejavue context` surfaces it (with
  its parsed DCP tag) at the top of the boot packet.
- **`parse_frontmatter()`** — stdlib-only minimal `key: value` frontmatter parser
  (no YAML dependency), shared by context.md metadata and reference frontmatter.
- **`dejavue import <FILE>`** — bootstrap context.md losslessly from a hand-written
  AGENTS.md/CLAUDE.md, recording provenance (source path + git blob sha) in
  frontmatter and as an `import` timeline event. Guards a populated context.md
  (`--force` to override). The safe step before `export`.
- **`dejavue export --target {claude,codex,gemini,copilot,cursor,all}`** —
  generate the tool's real file from context.md, wrapped in a managed block
  (`<!-- dejavue:begin DCP/1.0 src=context.md hash=… -->` … `<!-- dejavue:end -->`).
  Non-destructive write behavior: ABSENT → create block-only; MARKED → replace
  only the fenced region; UNMARKED hand-written → append a managed block + warn
  (never clobber); `--replace` converts the whole file. Target registry is
  overridable via `.dejavue/config` (`target_<name> = <path>`). `export` keeps
  its existing `--format json|md` snapshot mode.
- **`dejavue check`** now compares each adapter's stored `hash=` against the
  current context.md hash and warns "context.md changed — adapters stale".
- **`references/glossary.md`** — glossary reference card via the existing
  reference machinery (`reference create <name> --template glossary`), surfaced
  in `dejavue context`.
- **`dejavue promote --to planning`** — graduate a `.dejavue/` into a richer
  per-repo planning system (`.planning/`) without losing history: copies (never
  moves) every memory artifact, records a provenance card + a `promote` event,
  and leaves `.dejavue/` canonical.
- **`dejavue init --wizard`** — 3-question prompt (project type / agent / purpose)
  that seeds context.md + state.md. Non-interactive-safe (piped/EOF falls back to
  defaults); plain `init` is unchanged.
- **Reference frontmatter** — reference cards may carry `key: value` frontmatter;
  `dejavue reference list --type <t>` filters by `type:`, and
  `reference create --type <t>` injects it.
- **`dejavue diff --format patch`** — machine-readable unified-diff patch of the
  decisions (and state) delta between two refs.
- **`dejavue init` agent auto-discovery** — `init` now wires agent discovery
  automatically: (1) copies the bundled `dejavue` + `dejavue-workflow` skill files
  into `.dejavue/` as an in-repo fallback (so agents arriving at the repo find
  skills without needing a global install); (2) writes or appends a `## Project
  memory` boot stub to `CLAUDE.md` so Claude Code loads `dejavue context`
  automatically on every session. Both steps are idempotent and best-effort:
  skill copy is skipped if the source `skills/` directory is absent (standalone
  script installs); CLAUDE.md is only written if a dejavue boot stub isn't already
  present (detected via `<!-- dejavue:discovery -->` marker).

### Changed

- Version → 2.0.0. `hashlib` / `difflib` / `re` already imported (stdlib; no new
  runtime dependency). Test suite: 119 → 121 (121/121 green).

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

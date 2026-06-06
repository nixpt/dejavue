# Deja Vue

> Portable context + memory + adapter bridge for coding agents — the reference
> implementation of **DCP, the DejaVue Context Protocol**.

**Zero ceremony first.** Deja Vue is to project memory what `.git/` is to
history. Drop it into any git repo in 5 seconds. No infra, no MCP server, no
embeddings to configure, no runtime dependency — a single Python 3 file on the
standard library. This is *Axiom 0*: every layer above the base memory log is
optional and additive, and nothing is ever mandated. (See the
[DCP spec §0](docs/dcp-spec.md).)

On that base it does three things:

- **Memory** — captures what git cannot: the *why* — architectural decisions,
  rejected alternatives, constraints not obvious from the code, the context the
  next coding session needs to hit the ground running. The one command worth
  building for is `since`: show me everything that changed in this repo — git
  commits and cognitive context — since I last worked here.
- **Context** — a single `context.md` source of truth for an agent's operating
  rules, build/test commands, and architecture map.
- **Adapter bridge** — generate `CLAUDE.md` / `AGENTS.md` / `GEMINI.md` /
  Copilot / Cursor files *from* that source of truth, non-destructively, so the
  per-tool files become compatibility targets instead of N drifting copies.


## Install

Single Python 3 file, stdlib only. Copy it to any directory on your `PATH`:

```bash
curl -O https://raw.githubusercontent.com/nixpt/dejavue/main/dejavue.py
chmod +x dejavue.py
mv dejavue.py ~/.local/bin/dejavue
```

Or clone and symlink:

```bash
git clone https://github.com/nixpt/dejavue
ln -s "$PWD/dejavue/dejavue.py" ~/.local/bin/dejavue
```

No `pip install` required — single file is by design.


## Quickstart

Five minutes: init, start, commit, decide, hand off, recall.

```
$ cd myproject/
$ dejavue init
Installed post-commit hook at .git/hooks/post-commit
Initialized .dejavue/

$ dejavue start --agent claude --goal "Add rate-limiting middleware"
Session started. Goal: Add rate-limiting middleware

# ... make changes, git commit — hook fires automatically ...
$ git commit -m "add token-bucket rate limiter"
Recorded 3 file_changed events for a81f2cd.

$ dejavue decision "Token-bucket over leaky-bucket" \
    --reason "Allows short bursts; simpler to tune per-endpoint" \
    --rejected "leaky-bucket: smooths too aggressively for API traffic"
Decision recorded: Token-bucket over leaky-bucket

$ dejavue state --summary "Rate limiter merged to main. Redis not required — in-memory store for now."
State updated.

$ dejavue handoff \
    --summary "Token-bucket middleware done, tests green." \
    --next "Wire per-user limits; see decisions.md for the burst-allowance rationale."
Handoff written.
```

Next session (or next agent):

```
$ dejavue context          # boot packet: handoff + state + decisions + last 10 events
$ dejavue since 2026-05-10 # everything that changed since May 10
$ dejavue since --agent claude  # since my last session_start
$ dejavue recall "rate limiter"  # FTS5 search over all captured events and docs
```


## Concept

Git captures mechanical history — every file change, every commit message. What
it cannot capture is the reasoning: why this design over that one, what dead
ends were tried, what constraints are non-obvious from the code. Future agents
and developers rediscover those dead ends at full cost.

Deja Vue fills that gap. It writes a plain-text event log (`.dejavue/`) that
ships with the repo, requires zero infrastructure, and degrades gracefully when
tools are absent. The format is the contract — other coding-agent tools
(Cursor, Aider, external agent, claude-cli) can read `.dejavue/` directly, and
richer MCP servers can consume it without dejavue having to depend on them.

For the full design rationale — including the overlap with adjacent memory
tools, hook strategy, and the rejected-alternatives principle — see
`docs/04-design-perspective.md`. For the build spec and migration path,
see `docs/05-v0.1-scope.md`.


## DCP — DejaVue Context Protocol

Deja Vue is the reference implementation of **DCP**, a portable context
interchange standard. The full standard is in
[`docs/dcp-spec.md`](docs/dcp-spec.md) (DCP/1.0, draft). The idea: `.dejavue/`
is the **single source of truth**, and the per-tool instruction files
(`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, Copilot/Cursor rules) become
**generated, non-destructive adapter targets** rather than the authority.

DCP organizes context into three layers:

1. **Instruction layer** (`context.md`) — what the agent should *do*: operating
   rules, build/test commands, architecture map.
2. **Memory layer** (`timeline.jsonl` + `decisions.md` + `state.md` +
   `handoff.md`) — what the agent should *remember*. Deja Vue already is this.
3. **Adapter layer** — generated per-tool files plus an `import` to bootstrap
   from existing ones.

The round-trip flow:

```
dejavue import CLAUDE.md            # seed .dejavue/context.md from an existing file (lossless)
$EDITOR .dejavue/context.md         # edit the single source of truth
dejavue export --target claude      # regenerate CLAUDE.md (and codex/gemini/copilot/cursor/all)
```

`export` writes a marker-delimited managed block —
`<!-- dejavue:begin DCP/1.0 src=context.md hash=… -->` … `<!-- dejavue:end -->` —
into each tool's real file, preserving any hand-written content outside the
markers (absent→create, marked→replace region, unmarked→append+warn,
`--replace`→convert). Hand-written instruction files are never blindly
clobbered. The whole protocol holds to **Axiom 0**: zero ceremony, no mandated
dependency, every layer above the base memory log optional.

DCP is stewarded for the OpenKO Foundry under OCPL-1.1; see
[`STEWARDSHIP.md`](STEWARDSHIP.md).


### Layer relationships

```
dejavue            — format + reference CLI (this tool)
  .dejavue/        — on-disk format: timeline.jsonl + markdown docs + fts.db
  dejavue CLI      — reference implementation, zero dependencies

rich MCP servers   — consume .dejavue/ via thin shim tools (v0.3 work)
  may also maintain their own richer per-repo planning state
  (e.g. milestone / phase / learning indexes) as a superset

other coding agents — Cursor, Aider, external agent, claude-cli
  read .dejavue/ directly — the format is the open contract

git                — mechanical history (commits, diffs)
  dejavue adds cognitive history on top
```


## Commands

**Session lifecycle**

| Command | Description |
|---|---|
| `dejavue init [--ingest] [--map]` | Create `.dejavue/`, install post-commit + pre-push hooks, add `.gitattributes` + `.gitignore`. |
| `dejavue start --goal TEXT` | Record session start with intent. Foundation for `since --agent`. |
| `dejavue state --summary TEXT` | Overwrite `state.md` with current snapshot. |
| `dejavue handoff --summary TEXT --next TEXT` | Write `handoff.md` for the next session. |

**Capture**

| Command | Description |
|---|---|
| `dejavue decision TITLE --reason TEXT [--rejected "opt: why"] [--outcome TEXT]` | Append architectural decision to `decisions.md` and timeline. |
| `dejavue note TEXT [--tag TAG]` | Lightweight timestamped note between `annotate` and `decision`. |
| `dejavue annotate <doc> "note"` | Append a timestamped note to a doc without rewriting it. |
| `dejavue changed PATH --summary TEXT` | Record file change event manually (post-commit hook does this automatically). |

**Recall + exploration**

| Command | Description |
|---|---|
| `dejavue context` | Boot packet — handoff + state + decisions + references + last 10 events + staleness warnings. |
| `dejavue status` | One-liner health: agent, event count, last decision, open next-steps. |
| `dejavue since <ref>` | Delta since a date, commit hash, or agent's last session. **Killer command.** |
| `dejavue log [--since] [--agent] [--type] [--oneline] [--reverse]` | Formatted timeline view with filters. |
| `dejavue blame <file>` | "Why does this file exist?" — decisions and events mentioning the path. |
| `dejavue recall QUERY [--semantic] [--limit N]` | FTS5 keyword (or cosine semantic) search over all artifacts. |
| `dejavue get <doc>` | Direct fetch of `state`, `handoff`, `decisions`, or `references/<name>`. |
| `dejavue list [--type events\|decisions\|references]` | List available artifacts with paths. |
| `dejavue roster` | Agent activity summary — who worked here and when. |

**Operations**

| Command | Description |
|---|---|
| `dejavue check` | Health check: JSONL validity, hook status, `.gitattributes`, FTS freshness. |
| `dejavue ingest [--generate-map]` | Scrape `.claude/`, `CHANGELOG.md`, ADRs, and git log. `--generate-map` auto-populates `references/map.md`. |
| `dejavue archive --before DATE [--yes]` | Compact timeline by dropping old `file_changed` events (dry-run without `--yes`). |
| `dejavue config {list,get KEY,set KEY VAL,unset KEY}` | Manage per-repo `.dejavue/config`. |
| `dejavue install-skill [--dir PATH]` | Install SKILL.md to `~/.claude/skills/` (or `--dir`). |
| `dejavue worthiness` | Print the capture/skip table as a reminder. |
| `dejavue stats` | Event statistics: counts by type (with bar chart), by agent, date range. |
| `dejavue export --format {json,md}` | Export full memory snapshot as JSON or Markdown. |
| `dejavue reference {create,list,update,view}` | Manage `.dejavue/references/` cards via CLI. |
| `dejavue link <sha>` | Show dejavue events recorded for a git commit SHA. |
| `dejavue search QUERY [--semantic] [--limit N]` | Alias for `recall` (discoverable name). |
| `dejavue diff <from> [<to>]` | Compare memory between two refs — decisions added, state diff, event window. |
| `dejavue timeline [--by day/week/month]` | ASCII activity chart — events per time period. |
| `dejavue tag {list, filter <tag>}` | List tags with counts or filter events by tag. |
| `dejavue note-commit <sha>` | Write a git note on a commit linking it to the last dejavue event. |
| `dejavue version` | Print installed version. |

Each command accepts `--help`. See `dejavue --help` for the full flag list.


## Worthiness

`dejavue worthiness` prints this table. It is also shown once on first use.

```
Worthiness gate — only persist if:

CAPTURE                                    SKIP
─────────────────────────────────────────  ─────────────────────────────────────────
Decision changes architectural direction   Style preferences (let .editorconfig do it)
Constraint non-obvious from the code       Things git diff already shows
Blocker requiring external context         "Ran tests, passed"
Handoff context next agent must know       Per-file mechanical edits
Dead end + why it was rejected             LLM reasoning steps
Cross-cutting invariant ("X never depends  Routine commits
  on Y")

Rule of thumb: if removing this memory wouldn't confuse a future agent reading
the code + git log, don't write it.
```

The most valuable signal is the **rejected alternative** — the approach that
was tried and dropped, with the reason. That is the reasoning that costs the
next agent the most to rediscover. Use `--rejected "option: reason"` on every
`dejavue decision` call.


## Auto-capture via git hook

`dejavue init` installs a `post-commit` hook that fires automatically:

```bash
#!/usr/bin/env bash
# dejavue auto-capture
exec python3 /path/to/dejavue.py changed --auto --commit "$(git rev-parse HEAD)"
```

After every `git commit`, dejavue records one `file_changed` event per touched
file with the diff stat and commit message. No manual `changed` calls needed
for committed work.

If a non-dejavue hook already exists, `init` will warn and refuse to overwrite
unless `--force` is passed.


## `since` reference forms

```
dejavue since 2026-05-10         # ISO date (lexicographic comparison)
dejavue since a81f2cd            # commit hash (uses commit timestamp)
dejavue since --agent claude     # last session_start for that agent name
```

Output sections: git delta (log + diff stat), timeline events (newest first),
decisions made, state transitions, handoffs, top keywords.


## Semantic recall (`--semantic`)

`dejavue recall <query> --semantic` cosine-ranks events by meaning instead of
keyword overlap. Default endpoint is an OpenAI-compatible `/v1/embeddings`
URL — works against ollama out of the box (`ollama pull nomic-embed-text`,
no further config needed).

```bash
# Default: hits ollama on localhost
dejavue recall "rate limiter design tradeoffs" --semantic

# Override via env (any /v1/embeddings-compatible endpoint):
DEJAVUE_EMBEDDER_URL=https://api.openai.com/v1/embeddings \
DEJAVUE_EMBEDDER_MODEL=text-embedding-3-small \
  dejavue recall "rate limiter design tradeoffs" --semantic
```

**Lazy caching.** The first time a timeline event is seen during a semantic
recall, dejavue embeds its summary and appends a row to
`.dejavue/embeddings.jsonl`. Subsequent recalls hit the cache. The cache is
keyed by a content hash of the timeline line, so reorderings, duplicate
ingest runs, and worktree merges do not produce phantom entries.

**Graceful fallback.** If the embedder URL is unreachable, returns 4xx, or
returns malformed JSON, dejavue prints one warning line to stderr and falls
through to the FTS5 keyword path. Memory writes never block on the embedder
being up — this is a design invariant.

**`.dejavue/embeddings.jsonl` is gitignored.** It is rebuildable from
`timeline.jsonl` plus a working embedder, and different agents on the same
repo may legitimately use different models (different vector spaces should
not mix). Treat it like `fts.db` — local cache, not part of the canonical
on-disk format.

Reference forms:

```
dejavue recall "<query>"             # FTS5 keyword (default)
dejavue recall "<query>" --semantic  # cosine-ranked semantic
```


## File layout

```
.dejavue/
  timeline.jsonl     # append-only event log — commit this
  state.md           # current state snapshot — commit this
  decisions.md       # append-only architectural decisions — commit this
  handoff.md         # latest handoff — commit this
  references/        # hand-written reference cards (optional) — commit these
  fts.db             # sqlite FTS5 index — do NOT commit (rebuildable)
  embeddings.jsonl   # semantic-recall vector cache — do NOT commit (rebuildable, model-specific)
  ingested.lock      # ingest marker — do NOT commit (per-checkout)
  .first-use         # worthiness-gate-shown marker — do NOT commit (per-user)
  .locks/            # file locks for concurrent ops — do NOT commit
```

Add to `.gitignore`:

```
.dejavue/fts.db
.dejavue/embeddings.jsonl
.dejavue/*.tmp
.dejavue/.first-use
.dejavue/ingested.lock
.dejavue/.locks/
```

And add `.gitattributes` (critical for multi-branch / worktree workflows — see
*Concurrency, branches, and worktrees* below):

```
.dejavue/timeline.jsonl merge=union
.dejavue/decisions.md   merge=union
```


## Concurrency, branches, and worktrees

Deja Vue is designed for the common cases that real coding agents hit:

**Same repo, one agent at a time (sequential handoff):** the default flow.
Last agent's `state.md`/`handoff.md` wins. `timeline.jsonl` and `decisions.md`
accumulate. This is the entire model.

**Same repo, multiple agents sequentially across many sessions:** identical to
the above. The `since` command is the lookup tool — show me what changed since
I last touched this repo (or since a specific agent's last session).

**Multiple worktrees on different branches (worktree-per-agent dispatch):**
the workflow where each dispatched agent gets its own git worktree on its own
task branch, and a coordinator merges those branches back into main in waves.
Each worktree has its own checked-out `.dejavue/`. Agents accumulate events
on their own branch. When the branches merge back, git would normally
**conflict** on `timeline.jsonl` because both sides added unique lines and
the default text merger can't see that append-only semantics make union safe.

`.gitattributes` with `merge=union` fixes this: git keeps unique lines from
both sides, no conflict, all events surface after merge. Without this,
every wave merge requires manual resolution on `.dejavue/timeline.jsonl`.
The two-line `.gitattributes` file in this repo handles it.

State/handoff overwrites (single-file replace) follow last-writer-wins. If two
branches both edited `state.md` or `handoff.md`, git's normal text merger
flags the conflict and a human/agent resolves by hand — usually the latest is
correct.

**Multiple agents in the same working tree at the same instant (rare):** JSONL
appends are POSIX-atomic up to PIPE_BUF (~4KB) with `O_APPEND`. fts.db
rebuilds and `ingest` scrapes are not atomic; running two of these
concurrently in the same directory can corrupt state. `fcntl.flock` advisory
locking is applied to FTS rebuilds and ingest (v1.0+); JSONL appends are
POSIX-atomic. The rare true-concurrent case is still best avoided.

**Git hook in worktrees:** `dejavue init` installs the post-commit hook in
the main repo's `.git/hooks/`. Git worktrees inherit it by default (verified
on git 2.40+). You do not need to run `dejavue init` separately in each
worktree.

**Cross-repo:** out of scope. Each repo has its own `.dejavue/`. Cross-repo
coordination is the job of a workspace-wide coordination layer, not per-repo
memory.

**Agent identity:** use a stable role name on `--agent` (e.g. `claude`,
`sonnet`, `reviewer`, `coordinator`), not a model version. The role is what
the next session looks up; model versions change beneath the role.


## What dejavue is NOT

- A replacement for git.
- A replacement for richer per-repo planning systems that maintain milestone /
  phase / decision-tree state. Dejavue is the lightweight episodic layer
  underneath those, not a substitute for them.
- A vector database or embedding store. `--semantic` recall is available via
  any OpenAI-compatible `/v1/embeddings` endpoint (optional, graceful fallback).
- An MCP server. MCP tool wrappers are on the roadmap but not yet shipped;
  the format is the open contract any MCP server can consume.
- Cross-repo memory. Cross-repo coordination belongs in a separate
  workspace-wide coordination layer.


## Architecture and migration path

Deja Vue is the file format and reference CLI. Richer tools consume dejavue;
dejavue does not bundle them.

Analogy: `.dejavue/` is to project memory what `.git/` is to history. Multiple
tools sit on top of the same on-disk format. See `docs/05-v0.1-scope.md`
§Architecture for the full ruling.

| Version | Milestone |
|---|---|
| v0.1 | Single-file Python CLI. FTS5-only recall. Zero infrastructure. |
| v0.2 | `--semantic` flag via external embedder; FTS5 fallback. |
| v1.0 | Format stable. 20 commands: ambient agent-id, staleness warnings, pre-push hook, codebase map, `status`, `log`, `blame`, `note`. |
| v1.1 | 25 commands: `check`, `archive`, `roster`, `config`, `install-skill`, embedder circuit breaker. |
| v1.2 | 31 commands: richer event types, `stats`, `export`, `reference`, `link`, `search`, tiered embedder auto-detect. |
| v1.3 | 36 commands: `diff`, `timeline`, `tag`, `note-commit`, `check --fix`, event_type FTS indexing, `since` notes section. |
| v2.0 | **DCP/1.0** — `context.md` instruction layer, `import`, `export --target {claude,codex,gemini,copilot,cursor,all}` (non-destructive adapter bridge), `references/glossary.md`. `docs/dcp-spec.md` ships as a citable standard. |


## Status

v2.0.0 — single-file Python CLI and the **DCP/1.0 reference implementation**.
DCP/1.0 spec at `docs/dcp-spec.md` (Release Candidate). Format stable and
backward-compatible (additive evolution per DCP §7). Single file, stdlib only,
zero mandated dependency (Axiom 0). Not on PyPI.

Design documents in repo:
- `docs/dcp-spec.md` — **the DCP/1.0 standard** (three layers, adapter contract, `.dejavue/` layout, conformance)
- `docs/plans/2026-06-05-dcp-maturation.md` — ratified DCP design decisions (internal session)
- `docs/01-origin.md` — original conversation that produced the spec
- `docs/02-evolution.md` — the spec's evolution (semantic, boot packet, since/recall)
- `docs/03-example.md` — early bash demo
- `docs/04-design-perspective.md` — design rationale, overlap analysis, hook strategy
- `docs/05-v0.1-scope.md` — v0.1 build spec and architecture ruling
- `skills/dejavue-workflow/SKILL.md` — agent-facing workflow skill (Claude Code SKILL.md format, generic — symlink into `~/.claude/skills/` to load automatically)
- `CHANGELOG.md` — release notes
- `CONTRIBUTING.md` — contribution guidelines

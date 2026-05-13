# Deja Vue

> Zero-ceremony repo-local agent memory for coding agents.

Deja Vue is to project memory what `.git/` is to history. Drop it into any git
repo in 5 seconds. No infra, no MCP server, no embeddings to configure. It
captures what git cannot: the *why* — architectural decisions, constraints not
obvious from the code, context the next coding session needs to hit the ground
running. The one command worth building for is `since`: show me everything that
changed in this repo — git commits and cognitive context — since I last worked
here.


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

No `pip install` in v0.1 — single file is by design. PyPI packaging is v0.2.


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

| Command | Description |
|---|---|
| `dejavue init` | Create `.dejavue/`, scaffold files, install git post-commit hook. |
| `dejavue start --goal TEXT` | Record session start with intent. Foundation for `since --agent`. |
| `dejavue changed PATH --summary TEXT` | Record file change event manually. |
| `dejavue decision TITLE --reason TEXT` | Append architectural decision to `decisions.md` and timeline. |
| `dejavue state --summary TEXT` | Overwrite `state.md` with current snapshot. |
| `dejavue handoff --summary TEXT --next TEXT` | Write `handoff.md` for the next session. |
| `dejavue context` | Print all four `.md` files and the last 10 timeline entries. |
| `dejavue since <ref>` | Delta since a date, commit hash, or agent's last session. **Killer command.** |
| `dejavue ingest` | Scrape `.claude/`, `CHANGELOG.md`, ADRs, and git log into timeline. One-shot. |
| `dejavue recall QUERY` | FTS5 keyword search over all events, decisions, state, handoff, and references. |
| `dejavue worthiness` | Print the capture/skip table as a reminder. |
| `dejavue get <doc>` | Direct fetch of `state`, `handoff`, `decisions`, or `references/<name>`. |
| `dejavue list [--type events\|decisions\|references]` | List available artifacts with paths. |
| `dejavue annotate <doc> "note"` | Append a timestamped note to a doc without rewriting it. |

Each command accepts `--help`. See `dejavue.py --help` for the full flag list.


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


## File layout

```
.dejavue/
  timeline.jsonl    # append-only event log — commit this
  state.md          # current state snapshot — commit this
  decisions.md      # append-only architectural decisions — commit this
  handoff.md        # latest handoff — commit this
  references/       # hand-written reference cards (optional) — commit these
  fts.db            # sqlite FTS5 index — do NOT commit (rebuildable)
  ingested.lock     # ingest marker — do NOT commit (per-checkout)
  .first-use        # worthiness-gate-shown marker — do NOT commit (per-user)
  .locks/           # file locks for concurrent ops — do NOT commit
```

Add to `.gitignore`:

```
.dejavue/fts.db
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
concurrently in the same directory can corrupt state. v0.1.2 will add file
locking; for v0.1, just don't do this on purpose.

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
- A vector database or embedding store. v0.2 will add optional semantic recall
  via `--semantic` once an external embedder backend is wired in.
- An MCP server. v0.3 will add MCP tools as thin wrappers over the on-disk
  format so MCP-aware agents can consume it without a separate file format.
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
| v0.2 | `--semantic` flag uses an external embedder when configured; FTS5 fallback when absent. |
| v0.3 | MCP tool wrappers for agent ecosystems. Editor / Claude Code session-hook integration. |
| v0.4 | Upgrade path: export a `.dejavue/` into a richer per-repo planning system without losing history. |


## Status

v0.1 — single-file Python CLI. FTS5-only recall. Not on PyPI.

Design documents in repo:
- `docs/01-origin.md` — original conversation that produced the spec
- `docs/02-evolution.md` — the spec's evolution (semantic, boot packet, since/recall)
- `docs/03-example.md` — early bash demo
- `docs/04-design-perspective.md` — design rationale, overlap analysis, hook strategy
- `docs/05-v0.1-scope.md` — v0.1 build spec and architecture ruling
- `CHANGELOG.md` — release notes
- `CONTRIBUTING.md` — contribution guidelines

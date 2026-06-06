---
name: dejavue-workflow
description: |
  How to use dejavue (repo-local agent memory) as a working agent.
  Boot packet on arrival, capture architectural decisions during work,
  state snapshots, handoff at end, FTS5 recall search. Use this skill
  any time you land in a repo that has a `.dejavue/` directory at the
  root, OR when a task prompt mentions dejavue, OR when you're about
  to make an architectural choice worth keeping. The boot-packet pattern
  (`dejavue context`) shortcuts past stale-context startup. Decisions
  captured AS YOU MAKE THEM travel across sessions; decisions
  reconstructed later decay or vanish. Trigger phrases: "what's the
  context here", "boot packet", "capture this decision", "dejavue",
  arrival in a repo with `.dejavue/`.
---

# dejavue-workflow

Dejavue is to project memory what `.git/` is to history — a repo-local
event log that captures the *why* git can't (architectural decisions,
constraints non-obvious from the code, dead ends explored). The format
is portable (plain JSONL + markdown + SQLite FTS5); the reference CLI
is a single Python 3 file with no dependencies.

This skill is how a working agent interacts with dejavue: orient on
arrival, capture worth-keeping events, hand off cleanly, recall later.

## When this skill triggers

- You arrive in a repo and `.dejavue/` exists at the root
- A task prompt mentions dejavue or says "boot packet"
- You're about to make an architectural decision worth keeping
- You need to know what's changed in a repo since some reference point
- A session is ending and you need to leave a handoff

If `dejavue` isn't on PATH but the repo has a copy at `dejavue.py`:

```bash
ln -sf "$(pwd)/dejavue.py" ~/.local/bin/dejavue
```

Or install from the canonical repo per its README. The CLI is stdlib-
only Python 3 — no `pip install` needed.

## Why each pattern exists

Three failure modes dejavue is built to prevent:

1. **Cold-start blindness.** A new session in a repo doesn't know what
   the previous session decided, blocked on, or handed off. Without
   dejavue you re-derive context from git log + scattered TODOs + stale
   README sections. With dejavue: `dejavue context` is one screen.

2. **Decision rot.** Architectural choices made mid-session get
   forgotten by the next session. Without capture, the *why* lives in
   chat scrollback (gone) or "the code speaks for itself" (it doesn't).
   With `dejavue decision`, decisions land in `decisions.md` with
   rejected-alternatives — the most valuable signal future agents need.

3. **Handoff void.** Multi-agent / multi-session work loses continuity
   when each agent posts "done" but doesn't leave next-steps. `dejavue
   handoff` is the structured next-session brief.

## Boot packet on arrival

Step 1, before any work. From the repo root:

```bash
dejavue context
```

You get: `handoff.md` + `state.md` + `decisions.md` + last 10 timeline
events. Treat as ground truth for "what was the prior session's frame".

If `dejavue context` is empty or the directory doesn't exist, the repo
isn't dejavue-enabled. Don't initialize reflexively — see "When NOT to
init dejavue" below.

## Capture pattern (session lifecycle)

### Session start

```bash
dejavue start --agent <your-name> --goal "<one-line goal>"
```

Records a session_start event. Future agents can run
`dejavue since --agent <you>` to see everything that's changed since
your last start — even across days or weeks.

### Architectural decisions

For decisions that change direction, name a constraint, or close a
path:

```bash
dejavue decision "Token-bucket over leaky-bucket" \
  --reason "Allows short bursts; simpler to tune per-endpoint" \
  --rejected "leaky-bucket: smooths too aggressively for API traffic" \
  --rejected "fixed-window: thundering-herd at boundary" \
  --agent <your-name>
```

The `--rejected` flag is repeatable and **load-bearing**. Future
readers need to know what was tried and rejected, not just what won.
Each rejection: `"option: reason"`. This is the single most valuable
artifact dejavue captures — the reasoning that costs the next agent
the most to rediscover.

Two optional enrichments worth using when they apply:

```bash
# --supersedes: makes contradiction explicit
dejavue decision "Use embedded SQLite" \
  --reason "Zero deps, single process" \
  --supersedes "Use service-mode SQLite"

# --durability: filters noise during architectural reasoning
dejavue decision "Axiom 0 — no runtime deps ever" \
  --reason "Single-file contract; adoption collapses with pip deps" \
  --durability constitutional
```

`--durability` choices: `temporary` · `tactical` · `strategic` · `constitutional`.
The label appears in the `decisions.md` heading so it's visible without parsing events.

### Invariants, traps, and incidents

Three event types that capture memory most projects routinely lose:

```bash
# Things that must ALWAYS be true — architectural laws.
# Appends to invariants.md, surfaced by `context`.
dejavue invariant "Capsules never access host FS directly"
dejavue invariant "append-only timeline is immutable; never delete entries"

# Misleading names, fake abstractions, historical hacks.
# Agents waste real time rediscovering these.
dejavue trap "AuthManager does NOT handle OAuth — it only handles sessions"
dejavue trap "The 'cache' in CacheLayer is not a cache; it's a write buffer"

# Operational trauma — outages, data corruption, failed migrations.
# Highest-value memory; also the most reliably forgotten.
dejavue incident "FTS index corrupted after ungraceful shutdown 2026-05-15; rebuilt from JSONL"
dejavue incident "Migration 004 dropped rows where user_id was NULL — data lost in prod"
```

When unsure which to use: **invariant** = "this must never change"; **trap** = "this will mislead you"; **incident** = "this already hurt us". All three take `--tag` for grouping.

To look up what was previously rejected on a topic:

```bash
dejavue rejected                  # all decisions with rejected alternatives
dejavue rejected "grpc"           # only those mentioning gRPC
dejavue rejected "database"       # why we didn't use X database approach
```

### State snapshots

After a meaningful milestone (not every commit):

```bash
dejavue state --summary "<2-4 sentences on current state>" \
  --agent <your-name>
```

This OVERWRITES `state.md`. The state.md is "what's true right now",
not "what happened" — the timeline tracks history. Re-write whenever
the answer to "where are we?" changes materially.

### Annotations (lightweight notes)

When you want to add a timestamped note WITHOUT rewriting state/handoff:

```bash
dejavue annotate state "note text"          # appends to state.md
dejavue annotate handoff "note text"        # appends to handoff.md
dejavue annotate decisions "note text"      # appends to decisions.md
```

Good for mid-session context drops, partial updates, or noting an
intermediate event without losing the prior content.

### Session handoff (end of task)

Before you sign off:

```bash
dejavue handoff \
  --summary "<what's done, in 1-2 sentences>" \
  --next "<1-4 concrete next steps for the receiver>" \
  --agent <your-name>
```

The handoff is what the NEXT agent reads first via `dejavue context`.
Treat it as the most-important artifact of your session — the
short-format next-steps in `--next` shape the receiver's whole plan.

## Recall pattern (looking things up)

### Temporal delta — `since` is the killer command

```bash
dejavue since 2026-05-10              # everything since this date
dejavue since a81f2cd                 # everything since this commit
dejavue since main..HEAD              # git revision range
dejavue since v1.0..v2.0             # between two tags
dejavue since --agent claude          # since this agent's last session_start
```

The "what changed since I was last here?" question, answered in
seconds. Output sections: git delta (log + diff stat), timeline events
(newest first), decisions made, state transitions, handoffs, top
keywords.

### Keyword search

```bash
dejavue recall "rate limiter"
dejavue recall "auth migration"
```

FTS5 search over timeline + decisions + state + handoff + references.
Returns matched events with timestamps and excerpts. Fast.

### Direct fetch

```bash
dejavue get state              # print state.md
dejavue get handoff            # print handoff.md
dejavue get decisions          # print decisions.md
dejavue get references/<name>  # print a specific reference card
dejavue list                   # list everything available
```

Use `get` when you know exactly what you want; `recall` when you don't.

## The worthiness gate

The single biggest mistake with dejavue is over-capture. The CLI's own
`dejavue worthiness` output is canonical:

| CAPTURE | SKIP |
|---|---|
| Decision changes architectural direction | Style preferences (let `.editorconfig` do it) |
| Constraint non-obvious from the code | Things `git diff` already shows |
| Blocker requiring external context | "Ran tests, passed" |
| Handoff context next agent must know | Per-file mechanical edits |
| Dead end + why it was rejected | LLM reasoning steps |
| Cross-cutting invariant (`dejavue invariant`) | Routine commits |
| Misleading name / dangerous assumption (`dejavue trap`) | Things obvious from reading the code |
| Operational incident (`dejavue incident`) | Successful deploys with no lessons |

Rule of thumb: **if removing this memory wouldn't confuse a future
agent reading the code + git log, don't write it.**

Print this in your terminal any time you're uncertain:

```bash
dejavue worthiness
```

## Repo state ownership (git tracking)

When `.dejavue/` ships in a repo, the split is:

**Tracked (commit to repo):**
- `timeline.jsonl` — append-only event log
- `state.md` — current state
- `decisions.md` — architectural decisions
- `handoff.md` — latest handoff
- `invariants.md` — architectural invariants (scaffolded by `init`, append-only)
- `references/` — hand-written reference cards (optional)
- `context.md` — DCP adapter source (optional; used by `export --target`)
- `dejavue/`, `dejavue-workflow/` — skill dirs copied by `init` for in-repo fallback (optional)

**Ignored (per-checkout, rebuildable):**
- `fts.db` — SQLite FTS5 index, rebuilt from JSONL on demand
- `.dejavue/.first-use`, `.dejavue/ingested.lock` — markers
- `.dejavue/*.tmp` — temp files

Canonical `.gitignore` entries:

```
.dejavue/fts.db
.dejavue/*.tmp
.dejavue/.first-use
.dejavue/ingested.lock
.dejavue/.locks/
```

The post-commit hook (installed by `dejavue init`) auto-records every
commit's file changes as `file_changed` events. The hook is one line
calling `dejavue changed --auto`; no manual `changed` calls needed for
committed work.

## `merge=union` for parallel branches

If multiple agents commit on parallel branches that all touch
`.dejavue/timeline.jsonl` or `.dejavue/decisions.md`, every merge
produces a conflict on those append-only artifacts. The fix is in
`.gitattributes`:

```
.dejavue/timeline.jsonl merge=union
.dejavue/decisions.md   merge=union
.dejavue/invariants.md  merge=union
```

This tells git to take both sides of an append conflict. Apply once
per repo; future merges resolve cleanly. State.md and handoff.md are
single-file overwrites and stay with git's normal merge (conflicts
are rare and a human/agent resolves by hand).

## DCP adapter bridge

DCP/1.0 (DejaVue Context Protocol) lets a single `context.md` source
file feed all the different agent config formats a repo might need
(`CLAUDE.md`, `AGENTS.md`, `.cursorrules`, etc.) without duplicating
content.

### Bootstrap `context.md` from an existing instructions file

If the repo already has a `CLAUDE.md` or `AGENTS.md`:

```bash
dejavue import CLAUDE.md      # reads and seeds .dejavue/context.md
```

Imports the content into `context.md` as the canonical DCP source. The
original file is left untouched — import is read-only.

### Generate adapter files from `context.md`

```bash
dejavue export --target claude      # writes/updates CLAUDE.md
dejavue export --target codex       # writes/updates AGENTS.md
dejavue export --target gemini      # writes/updates .gemini/GEMINI.md
dejavue export --target cursor      # writes/updates .cursorrules
dejavue export --target copilot     # writes/updates .github/copilot-instructions.md
dejavue export --target all         # all of the above in one pass
```

Each export is **non-destructive**: it writes a managed block
(`<!-- dejavue:begin DCP/1.0 src=context.md hash=… -->…<!-- dejavue:end -->`)
into the target file. Content outside that block is preserved. Re-run
any time `context.md` changes — the hash guards against spurious writes.

### Promote to a richer planning system

When the project has outgrown plain dejavue memory and needs a full
planning system:

```bash
dejavue promote --to planning     # bootstrap a .planning/ planning system
```

This graduates the project without losing the `.dejavue/` history.

## Common workflows

### Session boot

```bash
cd <repo>
dejavue context              # boot packet
# ... now you have prior session's frame ...
dejavue start --agent <you> --goal "<one-line>"
```

### Mid-session decision capture (the most common use)

After making a real architectural choice, BEFORE moving on:

```bash
dejavue decision "<title>" \
  --reason "<why this won>" \
  --rejected "<alt>: <why-not>" \
  --agent <you>
```

Takes ~30 seconds. Pays off compounding over future sessions.

### Session close

```bash
dejavue state --summary "<current-state>" --agent <you>
dejavue handoff --summary "<what's-done>" --next "<next-steps>" --agent <you>
git add .dejavue/
git commit -m "<your message — post-commit hook also records the diff>"
```

### DCP multi-target export

```bash
# seed context.md from an existing instructions file, then generate all targets
dejavue import CLAUDE.md
dejavue export --target all
git add .dejavue/context.md CLAUDE.md AGENTS.md
git commit -m "chore: add DCP adapter bridge"
```

After that, keep `context.md` as the single source — re-run
`dejavue export --target all` whenever it changes.

### Returning after a gap

```bash
dejavue context                              # what's the latest frame?
dejavue since --agent <you>                  # what changed since I was here?
dejavue recall "<topic-i-was-working-on>"    # specifics from prior work
```

## When NOT to init dejavue

Resist the urge to `dejavue init` everywhere. Good candidates:

- ✅ A library you're actively designing (lots of architectural choices)
- ✅ A repo where multiple agents will work over time
- ✅ A repo where decisions decay because of long-tail multi-session work
- ✅ A repo with sessions ≥ days apart (cold-start cost is high)

Bad candidates:

- ❌ A repo with only mechanical edits (just use git)
- ❌ A repo you'll work on once and forget
- ❌ A repo that already has a richer planning system you'd duplicate
- ❌ A repo where the owner hasn't opted in

When in doubt, ask the repo owner. `.dejavue/` does ship in the repo;
opting users in without their consent is intrusive.

### What `dejavue init` installs

For context: `dejavue init` does more than create `.dejavue/`. It also:

1. **Writes a `CLAUDE.md` boot stub** — appends (or creates) a minimal
   section pointing agents at `dejavue context` on arrival. Idempotent:
   if the marker (`<!-- dejavue:discovery -->`) or any `dejavue context`
   reference already exists, the stub is skipped.

2. **Copies skills to `.dejavue/`** — copies `dejavue/` and
   `dejavue-workflow/` from the adjacent `skills/` directory into the
   repo's `.dejavue/` as an in-repo fallback. Agents without the skills
   in their global `~/.claude/skills/` can still load them from
   `python3 .dejavue/dejavue install-skill`.

3. **Installs git hooks** — post-commit (auto `file_changed` recording),
   pre-push (staleness check), post-checkout (prints `dejavue status` on
   branch switch — guards on `$3==1`, never fires on file checkout);
   `.gitattributes` `merge=union` entries for timeline/decisions/invariants.

Use `--wizard` to also interactively seed `context.md` for DCP export.

## What dejavue is NOT

- Not a replacement for git — it's a companion. Git captures *what*
  changed; dejavue captures *why*.
- Not a chat/conversation log. Don't dump LLM reasoning into the
  timeline — the worthiness gate filters that out for good reason.
- Not a project planner. State is current-snapshot; decisions are
  architectural choices; handoff is short-form. For real planning use
  a richer system on top (dejavue's docs note `.planning/` as one
  superset).
- Not auto-summarizing commits via LLM. v0.1 records the diff stat +
  commit message verbatim; deliberate capture is the contract.

## See also

- The dejavue README and `docs/` directory in the project root for
  full design rationale, the rejected-alternatives principle, the hook
  strategy, and the migration path to richer planning systems.
- `dejavue worthiness` — print the capture gate any time.
- `dejavue --help` and per-command `--help` for the canonical CLI
  surface.

## License

This skill ships under the same license as the dejavue project
(see `LICENSE` in the project root).

# 10: `timeline.jsonl` through GitHub PRs, and a non-linear timeline

**Ticket:** DEJAVUE-REVIEW-1 (follow-up) · **Author:** architect · **Date:** 2026-10-05 · **Base:** doc 09 on the same branch
**Status:** design proposal only. Nothing here is ratified. §6 adds captain decisions **C9–C15**, continuing doc 09's C1–C8.

The captain asked: *"GitHub also doesn't handle timeline.jsonl changes coming through PRs, so look into that. Maybe
we can create a non-linear timeline, which would allow us to have multiple timelines."*

**Short answer.**
1. **GitHub does not honour `merge=union`.** Six open nixpt PRs are marked CONFLICTING right now even though they merge
   cleanly with git locally. Their only conflicts are `.dejavue/` union files. 43 merged PRs in 11 repos needed a
   "merge main into branch" commit whose only no-union conflict was `timeline.jsonl`. The mechanism reproduces
   locally: a **bare** repository ignores in-tree `.gitattributes`.
2. **Removing the post-commit hook (doc 09, C1) removes about two thirds of the problem, but not all of it.** Merges
   where both sides append to the timeline drop from 17% to 6%, and open PRs that touch the timeline drop from 28 to 9
   of 51. What remains is the durable *why* (decisions, traps, plans), which is exactly what option D keeps. The same
   failure hits `decisions.md`.
3. **Recommended layout: one immutable file per event**, `.dejavue/events/<YYYY-MM>/<id>.json`. The id is a
   sortable 128-bit **HLC-ULID** (hybrid logical clock time + counter + random), and an optional `parents` list
   makes the timeline a causal DAG. No file is ever written on two branches, so neither GitHub nor local git can
   conflict on it. Deletes merge cleanly, so a scrub stays scrubbed. Per-branch, per-agent, per-session and per-box
   timelines become *views* of the event set, not separate files. Machine events are not committed at all.

---

## 1. Evidence: what GitHub does with `merge=union`

All measurements were taken read-only on `[main]` on 2026-10-05. Source repos were never written to: every merge
computation ran in `git clone --bare --shared` copies under `/build/tmp/tl10/clones/`, and PR refs were fetched only
into those copies. The scripts are in Appendix A.

### 1.1 Population

```bash
ls /workspace/projects/*/.gitattributes /workspace/projects/*/*/.gitattributes 2>/dev/null \
  | xargs grep -l 'timeline.jsonl merge=union' | wc -l                     # 107 (88 at depth 1)
```

That is 107 checkouts, not the 103 in the ticket, because the glob includes subgroup and worktree checkouts. Deduped by
`origin` URL among the depth-1 `.dejavue` repos, there are **72 distinct repos** (70 of them `nixpt`/`openko-network`,
`repos.txt` in Appendix A). Every number in §1.2 and §1.3 is over those 72.

### 1.2 Open PRs: GitHub's verdict vs. a local re-merge

`prs.py` lists every open PR (`gh pr list --state open`) in the 72 repos, which is **51 PRs**. For each one it fetches
`refs/pull/N/head` and the base branch, then re-merges them twice with `git merge-tree --write-tree`: once with the
base branch's `.gitattributes` (`--attr-source=<base>`, union honoured) and once with attributes disabled
(`--attr-source=<empty tree>`). GitHub's `mergeable` was re-queried after the re-merge.

| | count |
|---|---|
| Open PRs | 51 (28 MERGEABLE, 23 CONFLICTING) |
| CONFLICTING with a `.dejavue/` file among the no-union conflicts | **18 of 23** |
| CONFLICTING on GitHub, **clean locally with union**, every no-union conflict a `.dejavue/` union file | **6**: `cloudflow#4`, `exosphere#56`, `flame#2`, `foreman-v9#1`, `foreman-v9#4`, `zorro-zazen#13` |
| MERGEABLE on GitHub although the no-union re-merge conflicts (would show GitHub *does* honour union) | **0** |
| No-union conflicts that include `.dejavue/decisions.md` (also a union file) | 11 |
| CONFLICTING on a `.dejavue/` file even *with* union | 1 (`mustang#1`: add/add of two independent `init`s) |

The six are the decisive cases. Spot check (`cloudflow#4`; `flame#2`, `zorro-zazen#13` and both `foreman-v9` PRs look
the same):

```text
$ gh pr view 4 -R nixpt/cloudflow --json mergeable,mergeStateStatus
CONFLICTING DIRTY
$ git -C clones/cloudflow.git show refs/tl10/4/base:.gitattributes | grep union
.dejavue/timeline.jsonl merge=union                 # the attribute is on the base branch
$ git -C clones/cloudflow.git --attr-source=refs/tl10/4/base merge-tree --write-tree --name-only refs/tl10/4/base refs/tl10/4/head
<tree>                                              # exit 0: clean with union
$ git -C clones/cloudflow.git merge-tree --write-tree --name-only refs/tl10/4/base refs/tl10/4/head
<tree>
.dejavue/timeline.jsonl                             # exit 1: the bare repo, default config, conflicts
```

### 1.3 History: merges and merged PRs

`merges.py` re-merges every two-parent merge commit in the 72 repos where **both** sides changed
`.dejavue/timeline.jsonl` relative to the merge base, with and without attributes:

```text
merges where both sides changed .dejavue/timeline.jsonl: 269 (GitHub-made: 10)
  conflict without union: 242 · conflict with union: 0 · timeline is the ONLY no-union conflict: 134
  GitHub-made merges that conflict on .dejavue/timeline.jsonl without union: 0
repos with ≥1 such merge: 31
```

- Union is load-bearing **locally**: 242 merges would have conflicted without it, and 134 of them *only* on the
  timeline. `decisions.md` appears among the no-union conflicts of 52 of these merges.
- GitHub's merge button has **never** been exercised on a case that needed union. The 10 GitHub-made merges where both
  sides touched the timeline would all have been clean without it. History can't prove GitHub honours union; §1.2 shows
  it doesn't.
- The cost shows up as workaround commits. 48 of the 134 timeline-only merges are "merge `main`/`master`/`dev` into
  `<branch>`" commits (the subject regex is in Appendix A). `gh api repos/<slug>/commits/<sha>/pulls` puts **45 of them
  on 43 distinct merged PRs in 11 repos** (nexus 20, squadron 9, zorro 5, maya 4, mayfly 2, and one each in antarikshya,
  exousia, flownet, interactd, monkey-cns, seahorse). Some of those merges may also have been pulling in base changes for
  another reason. What the re-merge shows is that the timeline was the only thing that conflicted.

### 1.4 Local reproduction, without GitHub

`repro.sh` (Appendix B) builds two branches that each append to `timeline.jsonl` from the same base, then merges them
four ways:

```text
## 1. merge-tree, attributes from the worktree (non-bare: union honoured)
53ce20bc…   exit=0
## 2. same merge, attributes disabled (--attr-source=<empty tree>)
CONFLICT (content): Merge conflict in .dejavue/timeline.jsonl   exit=1
## 3. bare repo (how a forge stores it), default config
CONFLICT (content): Merge conflict in .dejavue/timeline.jsonl   exit=1
## 4. bare repo with attr.tree=a (read .gitattributes from a commit)
53ce20bc…   exit=0
## 5. 'git merge b' into a, union honoured: result order
{"ts":"2026-10-05T10:00:00Z","event":"init"}
{"ts":"2026-10-05T10:05:00Z","event":"decision","by":"a"}
{"ts":"2026-10-05T10:01:00Z","event":"decision","by":"b"}      ← older than the line above it
{"ts":"2026-10-05T10:09:00Z","event":"plan","by":"b"}
```

**Mechanism (inferred, consistent with every observation, not confirmed from GitHub's side).** Git reads
`.gitattributes` from the working tree. A bare repository has none, so unless `attr.tree` or `--attr-source` is set,
a server-side merge sees no `merge=union` and falls back to the text merge. Case 3 is that behaviour on git 2.55, and
§1.2's six PRs are the same behaviour on GitHub. Nothing a repo commits can change it. GitHub has no setting for merge
attributes or custom drivers.

### 1.5 Two more costs of union, beyond GitHub

- **Order is lost.** Union concatenates "ours, then theirs" per hunk, so a merged timeline is not in time order
  (case 5). Fleet-wide, after normalising every `ts` to UTC, **351 lines in 41 of 91 timelines** are older than the line
  before them (Appendix A, `order.py`). Every reader that takes "last N lines" as "most recent N" is subtly wrong, and so
  is the `since` window (already a recorded trap).
- **Nothing can be deleted.** Doc 09 §2.6 showed merge `f973134` resurrecting scrubbed text in the public
  `decisions.md`. There are also **453 exact-duplicate lines** across the 91 timelines (same script).

### 1.6 What the post-commit hook does to this

The hook writes on every commit, so almost every branch touches the timeline whatever its real change is. `sides.py`
classifies the lines each side of a merge added. "Machine" means `file_changed`, `symbol_index` and
`symbol_index_incremental`; everything else counts as human-captured.

| Over 1,551 two-parent merges in the 72 repos | all events | human-captured only | durable-why only¹ |
|---|---|---|---|
| Branch side adds timeline lines | 879 (**57%**) | 427 (**28%**) | 375 (24%) |
| **Both** sides add lines (conflict candidate on GitHub) | 269 (**17%**) | 91 (**6%**) | n/a |
| Machine share of branch-side lines | 16,370 / 18,212 = **90%** | | |

| Over the 51 open PRs | all events | human-captured only |
|---|---|---|
| PR adds timeline lines | **28** | **9** |

¹ `decision`, `trap`, `invariant`, `pattern`, `rule`, `hazard`, `conflict_record`. On branch sides, the human
events break down as decision 365, handoff 158, state_update 154, plan 133, trap 75, session_start 47, and a long tail.

**So the problem does not disappear once the hook goes.** It drops by about two thirds, and what's left is the
durable *why*, which is the part doc 09 recommends keeping. A tool whose remaining job is "carry decisions through PRs"
still conflicts on 6% of merges and on every GitHub PR that races another decision.

---

## 2. What "non-linear" has to mean

A git repo is already a DAG. The timeline is linear only because it's stored as one append-only file that branches
fight over. The goal is a layout where:

1. **No file is written on two branches**, so neither GitHub nor local git has anything to merge (merge-free by
   construction, not merge-tolerant via union).
2. **Deletion is a normal git operation**, so scrubs and retractions stay done.
3. **Order comes from the event, not from file position**, and it survives clock skew between `[main]` and `[zorro]`.
4. **"Multiple timelines" are views of one event set.** A view can be per branch (what this branch knows), per agent,
   per session, per box, or the forks and joins between them.
5. Axiom 0 holds: stdlib only, readable with `cat`/`grep`/`jq`.

---

## 3. Options compared

| | (a) one file per event | (b) one log per writer | (c) causal DAG (`parents`) | (d) commit only curated records |
|---|---|---|---|---|
| **Layout** | `.dejavue/events/<YYYY-MM>/<id>.json` | `.dejavue/timeline/<key>.jsonl`, key = agent / agent@box / branch / session | a field, not a layout: needs (a) or (b) for storage | machine events gitignored or not written; durable events stay in `timeline.jsonl` + `decisions.md` |
| **GitHub/local conflicts** | **never** (unique, immutable paths) | when one key appends on two branches. Measured on the 91 human-only two-sided merges: key = agent → **41 (45%)** collide (mostly `unknown` 25, `foreman` 5); key = agent+branch → **2** | inherits storage | **6%** of merges, 9 of 51 open PRs, plus `decisions.md` |
| **When the bad case happens in this fleet** | n/a | re-dispatch onto the same branch name, salvage branches (`salvage/<agent>/…`), a foreman session committing on several branches, `agent` unset (`unknown`) | n/a | any two PRs that each record a decision |
| **Files** (crush-ast: 5,001 events, 895 tracked files) | 5,001 with the hook; **128** without it. Fleet human-only: median 20 per repo, p90 102, max 253 (zorro) | one per writer key | n/a | 1–2 |
| **git cost** (prototype, `p.py`, crush-ast data) | 5,001 flat: `status` 30 ms, read-all 83 ms, **195 KB tree object per new event**. Month-sharded: `status` 12 ms, 0.3 KB of tree objects (grows with one month's events, not the total). 128 files: 3 ms | as today | n/a | as today (7 ms `status`, 15 ms read) |
| **Order** | id sorts (HLC); `ls` order = time order | per file only; global order needs a sort | causal partial order + forks/joins | file position (wrong after a union merge, §1.5) |
| **Delete/scrub** | `git rm` merges cleanly | union file: can't delete | n/a | can't delete |
| **Greppability** | `grep -r`, `cat events/*/*.json \| jq` (glob order = time order) | good | n/a | good |
| **Multiple timelines** | as views (§4.4) | one physical file per key: rigid, and wrong for any key it wasn't keyed on | yes: real forks and joins, independent of git topology | no |
| **Verdict** | **storage of choice** | rejected: reduces conflicts, never eliminates them | **adopt as an optional field on (a)** | **adopt for machine events**; not enough on its own |

Two more options I considered and rejected:

- **(e) Keep union and merge every PR locally (foreman-merge), treating GitHub's CONFLICTING on `.dejavue/` as noise.**
  This is the de facto workflow today. It costs the 43-PR workaround merges, misleads every reader of the PR list, and
  blocks anyone who uses the GitHub button, including public contributors to `nixpt/dejavue`. It is acceptable as an
  interim process, which is C15.
- **(f) Make GitHub honour union.** There is no repository- or org-level setting for merge attributes or custom drivers,
  and `attr.tree` is server configuration. Not available.

---

## 4. Recommended design: per-event files, HLC-ULID ids, optional causal parents, nothing machine-made committed

This builds on doc 09's option D (the hook goes, session verbs retire in fleet repos). It replaces the *storage* of the
durable core and leaves its *content* unchanged.

### 4.1 Layout

```
.dejavue/
  events/
    2026-10/
      06FQ3Z8K5M0001X7HQ2V9RTC4A.json      one event, single-line JSON + "\n", never modified after create
    packs/
      2026-06-3f9a1c2e.jsonl               optional compaction (§4.5), content-addressed name
  timeline.jsonl                           legacy, frozen: read, never appended by a new writer
  decisions.md …                           legacy union files, frozen (§4.6)
  local/                                   gitignored: machine events if any are kept (C1)
```

The month shard is the HLC physical time in UTC. Sharding keeps each new commit's tree object small (§3: 195 KB flat
vs 0.3 KB sharded, on crush-ast's data), and `ls` of a shard lists events in time order.

### 4.2 Identity and ordering: HLC-ULID

The **id** is 128 bits, written as 26 Crockford-base32 characters (the ULID text form), so it sorts lexicographically:

| bits | field |
|---|---|
| 48 | HLC physical time `l`, ms since epoch (UTC) |
| 16 | HLC logical counter `c` |
| 64 | `os.urandom` (uniqueness across writers and boxes) |

**Write rule (hybrid logical clock).** Let `(l_max, c_max)` be the largest HLC among events visible in this checkout.
That's one directory listing: the last filename in the newest shard. Then:

```
wall = time_ns() // 1_000_000
l = max(wall, l_max)
c = c_max + 1 if l == l_max else 0
```

The new id therefore sorts after everything the writer could see. That is the causal guarantee plain ULID (wall clock
only) lacks.

**Clock skew.** If `[zorro]` runs 3 minutes ahead and `[main]` then writes after merging a `[zorro]` event, `[main]`'s
event still sorts after it, because `l` ratchets up. Events that couldn't see each other (true concurrency) sort by
their own clocks, which is the best total order there is. `ts` (the wall clock, with offset) stays on the event for
humans. If `l_max - wall` exceeds 5 minutes, the writer warns on stderr (per `rules.md`, never silent) that this clock
is behind a peer's.

Why not the alternatives:

- **Plain ULID** sorts by wall clock alone, so skew misorders causally related events.
- **A pure Lamport counter** has no wall-time meaning, and month shards need one.
- **A content hash as the id** is idempotent, but carries no order, and two identical notes become one.

### 4.3 Event fields (additive to DCP §6.1)

| Field | Req. | Meaning |
|---|---|---|
| `id` | MUST | HLC-ULID. Equals the filename stem, and survives packing. |
| `parents` | SHOULD | ids of the **heads** visible at write time: events in this checkout that no other event names as a parent. Usually one; two or more right after a merge, which marks a join. Readers MUST tolerate parents they can't find (packed, scrubbed, or on another branch). |
| `writer` | MAY | `<agent>@<box>`. Opt-in: box names are internal, and public repos shouldn't leak them (C13). |
| `session` | MAY | jsess session id when the event came through `jsess … --durable` (§4.8). |

All existing fields (`ts`, `branch`, `commit`, `agent`, `event`, `summary`, …) are unchanged. `commit` keeps meaning
"HEAD at write time". Note that the event file itself lands in a *later* commit, which avoids the amend problem
entirely (doc 09 §2.2).

**Computing heads** reads the `parents` of the newest two shards (the 128 files at crush-ast's human-only size read in
3 ms; the full 5,001 in 83 ms). Heads older than two months are ignored; a stale fork has nothing to contribute.

### 4.4 Read path and the "multiple timelines" views

- **Load** = loose `events/*/*.json` ∪ `events/packs/*.jsonl` ∪ legacy `timeline.jsonl`, deduped by `id`. Legacy lines
  get a synthetic id, `L` + 25 characters of `sha1(line)`, and sort by `ts` normalised to UTC. That normalisation also
  fixes the lexical-timezone trap in `since`.
- **`context`**: "recent timeline" is the last N ids, a listing rather than a file scan. Decisions, traps, rules and
  invariants are rendered from events (§4.6).
- **`recall` / FTS5**: `fts.db` keys rows by `id`. Reindexing is a set difference between ids on disk and ids in the
  db: insert new, delete gone. A scrub (`git rm`) therefore also leaves the local index on its next reindex. Today a
  removed line lives on in `fts.db` until a full rebuild.
- **Views**, all over the same event set (new `timeline` flags):
  - `--branch <ref>`: what that branch knows, via `git ls-tree -r --name-only <ref> .dejavue/events`. Git already
    defines a per-branch timeline exactly; no extra metadata is needed.
  - `--since-fork <ref>`: events in HEAD that aren't in `<ref>`. It's the set difference of two `ls-tree`s, which
    replaces `merge-summary`/`squash-summary`'s timestamp windows with an exact answer.
  - `--agent`, `--session`, `--writer`/`--box`: field filters.
  - `--graph`: the `parents` DAG with forks and joins. Unlike git topology, it survives squash merges, rebases and
    cherry-picks, because the parents live inside the events.

### 4.5 Compaction and archival, without rewriting history

Events are immutable, so compaction is add plus delete, both of which merge cleanly:

- `dejavue pack --month 2026-06` (main branch, foreman post-merge, months older than about 90 days, C14) writes
  `events/packs/2026-06-<sha8>.jsonl` (sorted by id, name = hash of content) and `git rm`s that month's loose files in
  the same commit.
- A long-lived branch that still adds loose files to a packed month merges cleanly: the files it adds are new paths,
  and the files main deleted are unchanged on the branch. Readers dedupe by id, so a pack plus stragglers is fine.
  Two concurrent packs of the same month get different names and dedupe the same way.
- Legacy `timeline.jsonl` can be retired on touch: `pack --legacy [--drop-machine]` writes it into
  `packs/legacy-<sha8>.jsonl`, optionally without `file_changed` lines (git has them), then `git rm`s it. On crush-ast
  that turns a 1.7 MB file into 128 events.
- Nothing is ever rewritten in git history. A scrub is `git rm` plus, if wanted, a `supersedes` event.

### 4.6 The Markdown views

`decisions.md`, `invariants.md`, `patterns.md` and `rules.md` are union files today and have the same GitHub problem
(11 open PRs, 52 historical merges). In the new layout they are **renderings of events**, and they must not be written
on branches. Two ways to do that (C11):

- **(i) Not committed.** `dejavue render` writes them into `.dejavue/local/` or prints them, and `context` reads events
  directly. This is the simplest option, but GitHub visitors lose the readable `decisions.md`.
- **(ii) Committed only on the default branch, by one writer.** Foreman's post-merge step (or CI) runs
  `dejavue render --commit`, and branch-side commands never touch the file. One writer means no conflicts. This option
  keeps the public face.

The existing union-appended `.md` files freeze as legacy: they're read, and never appended by a new writer.

### 4.7 Axiom 0 and the base loop

The design uses only stdlib: `os.urandom`, `time.time_ns`, `json`, `os.open(O_CREAT|O_EXCL)`, `subprocess git ls-tree`,
and a 20-line base32 encoder. Concurrent writers in one checkout need **no lock**: a unique name created with
`O_EXCL` replaces today's `flock` around `O_APPEND`. `init` creates `.dejavue/events/`. Git doesn't track empty
directories, so readers treat a missing `events/` as empty. `init → start → decision → state → handoff` is unchanged
for the user.

### 4.8 Where jsess and `--durable` fit

- **jsess already uses option (b) keyed by session**: one append-only `.caison` per session in `.jagent/sessions/`.
  The store is **gitignored** and lives in the main checkout, shared by its worktrees, so git never merges it and it
  doesn't need this redesign. If session logs ever become committed or synced between boxes (deck12's mirror is the
  likely route), per-session files are already safe. Its single shared files (`INDEX.jsonl`, `SESSIONS.md`) would
  then need to become renderings, as in §4.6.
- **`jsess decision --durable`** (doc 09, C3) execs `dejavue decision … --session <jsess-id>`, which writes one event
  file with `session` set. A per-session view of the durable record (`timeline --session s12`) then comes for free, and
  `jsess brief` can list the durable events its session produced by id.
- **caison stays out of `.dejavue/`** (doc 09 §3). Per-event JSON keeps `jq`/`grep` and the stdlib parser, and since
  nothing is merged any more, caison's merge story would not matter either way.

### 4.9 DCP spec impact

Today §8.2 says a writer **MUST** write `timeline.jsonl` and install the union `.gitattributes`. Moving writes
elsewhere is a breaking change under §7: a DCP/1.0 reader would silently miss new events. Proposed two steps (C10):

1. **DCP/1.1 (additive):** add `events/` and `events/packs/` to the §2 layout table, add §6.1's new fields and the
   HLC ordering rule, and add a reader rule: readers SHOULD load `events/` and packs alongside `timeline.jsonl`,
   deduped by `id`. Writers keep writing `timeline.jsonl`. This ships read support everywhere first.
2. **DCP/2.0:** writers MUST write `events/` and MUST NOT append to `timeline.jsonl` or the union `.md` files, which
   become legacy read-only. The union `.gitattributes` lines stay so legacy local merges still work. `context.md`
   adapters are unaffected. Hook installation leaves `init` (doc 09, C1).

### 4.10 Migration: read both, write new, never a sweep (SQ-213)

| Step | What | Where |
|---|---|---|
| M0 | Hook removal / non-amending fix (doc 09 P0–P1). This alone removes about two thirds of the conflict surface (§1.6). | dejavue |
| M1 | Release with DCP/1.1 read support (`events/`, packs, legacy, dedup by id) and the new `timeline` views. No write change. | dejavue |
| M2 | Write switch, per repo: a repo is on the new layout when `.dejavue/events/` exists. New repos get it from `init`. Existing repos get it **on touch**, when `jagent-adopt` (doc 09 P3) runs `mkdir .dejavue/events` on the task branch. Nothing is rewritten, and `timeline.jsonl` simply stops growing. | each repo, on touch |
| M3 | `dejavue check` warns when `timeline.jsonl` grew in a repo that has `events/`. That means an old writer: a vendored copy (doc 09, C5), an old binary on the other box, or a pinned release (C7). Old writers keep working; they just keep the old conflict surface until replaced. | dejavue |
| M4 (optional) | `pack --legacy --drop-machine` on touch, and the C11 render policy. | each repo |

There is no flag day. Both boxes can run different versions in the meantime, because every version reads what every
other version writes once M1 is everywhere. **Ordering matters:** M1 must reach both boxes and the vendored copies
before M2 starts anywhere. Otherwise an old reader on `[zorro]` would miss events written on `[main]`.

---

## 5. How this fits doc 09's plan

Doc 09 ranks D first. This doc doesn't change the ranking; it changes D's storage. Phase mapping: M0 is doc 09 P0–P1,
M1–M3 slot in between doc 09's P1 and P2, and M4 sits alongside P5.

## 6. Captain decisions (C9–C15, not made here)

> **C9. Change the storage, or stop at hook removal?** Adopt per-event files (§4), or accept the residual (6% of merges with
> both sides appending, 9 of 51 open PRs still touching the timeline, and `decisions.md`) conflicting on GitHub
> after C1, and keep JSONL.
>
> **C10. DCP versioning.** Two steps (1.1 read support, then 2.0 write switch), recommended; or a single 2.0; or keep
> per-event files a fleet-only extension outside the public DCP.
>
> **C11. Markdown views.** (i) render-on-demand, not committed; (ii) committed on the default branch only, by one
> writer (foreman post-merge or CI); or (iii) keep appending the legacy union `.md` files, which keeps their GitHub
> conflicts.
>
> **C12. Causal `parents`.** Include now as SHOULD (cheap, enables `--graph` and survives squash merges), or defer and
> rely on id order plus git topology.
>
> **C13. Box identity in history.** Should `writer: <agent>@<box>` be recorded, and if so opt-in per repo, given that
> some of these repos are public and `context.md` forbids leaking local names into this one?
>
> **C14. Compaction policy.** Who packs (foreman post-merge vs. anyone on main), after how long (90 days proposed), and
> whether legacy `file_changed` lines are dropped when a legacy timeline is packed on touch.
>
> **C15. Interim process while union is ignored on GitHub.** Until M2 reaches a repo, should foreman merge locally and
> treat a CONFLICTING verdict that consists only of `.dejavue/` union files as non-blocking? The six PRs in §1.2 are
> blocked only by that today.

---

## 7. Found, not fixed (captured with `dejavue plan`)

- Six open PRs are blocked on GitHub only by `.dejavue/` union files (§1.2).
- `nixpt/mustang#1` conflicts on several `.dejavue/` files even with union: add/add of two separate `init`s.
- Hook events record `"branch": "HEAD"` when written from a detached HEAD (e.g. mid-rebase), so per-branch attribution
  from the legacy timeline is unreliable. That's another reason per-branch views should come from `git ls-tree`, not
  from the `branch` field.
- 453 exact-duplicate timeline lines and 351 out-of-order lines fleet-wide (§1.5). These are harmless to `recall`, but
  "last N" and `since` are subtly wrong today.

---

## Appendix A: measurement scripts

All run from `/build/tmp/tl10/` with git 2.55 and `gh` authenticated as `nixpt`. They write only under `/build/tmp/tl10/`.

**Population** (`repos.txt`: origin URL and path, deduped by URL, depth-1 repos with a `.dejavue/` and the union attribute):

```bash
cd /workspace/projects && for d in */.dejavue; do r=${d%/.dejavue}; u=$(git -C $r remote get-url origin 2>/dev/null)
  grep -q 'merge=union' $r/.gitattributes 2>/dev/null && echo "$u $r"; done | sort -u -k1,1 | grep -v '^ ' \
  > /build/tmp/tl10/repos.txt                                                # 72 lines
```

**Open PRs** (`open_prs.txt`):

```bash
awk '{print $1}' repos.txt | sed -E 's#.*github.com[:/]##; s#\.git$##' | grep -i 'nixpt\|openko' > slugs.txt
for s in $(cat slugs.txt); do gh pr list -R $s --state open --limit 100 \
  --json number,mergeable,headRefName,baseRefName \
  -q ".[] | \"$s \(.number) \(.mergeable) \(.baseRefName) \(.headRefName)\""; done > open_prs.txt   # 51 lines
```

**Merged PRs behind the workaround merges** (§1.3): the 48 `base_into_branch.json` rows are the `merges.json` rows with
`plain_only_tl` whose subject matches
`Merge (remote-tracking )?branch '(origin/)?(main|master|dev)'( of \S+)? into|Merge (main|master|dev) into|resolve.*(timeline|conflict)|sync.*(main|master)`
(case-insensitive). Each was then looked up with `gh api repos/<slug>/commits/<full-sha>/pulls`.

**Ordering and duplicates** (`order.py`, §1.5), over `/workspace/projects/*/.dejavue/timeline.jsonl`: for each line,
parse `ts` with `datetime.fromisoformat` (UTC if naive) and count lines older than their predecessor, plus exact
repeated lines. Result: `timelines=91 lines=38375 out-of-order=351 in 41 repos; exact-duplicate lines=453` (the line count grows as the fleet works; the other numbers were the same on two runs).

### `merges.py`

```python
#!/usr/bin/env python3
"""Re-merge every 2-parent merge commit that both sides' timeline.jsonl changed,
once with gitattributes honoured (merge=union) and once with attributes disabled
(--attr-source=<empty tree>). Read-only on the source repos: work happens in a
`git clone --bare --shared` under /build/tmp/tl10/clones/.
Usage: merges.py repos.txt   (lines: "<origin-url> <path>")"""
import subprocess, sys, os, json

EMPTY = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
TL = ".dejavue/timeline.jsonl"
OUT = "/build/tmp/tl10"


def git(repo, *args, attr=None, check=False):
    pre = ["git", "-C", repo] + (["--attr-source=" + attr] if attr else [])
    p = subprocess.run(pre + list(args), capture_output=True, text=True)
    if check and p.returncode:
        raise RuntimeError(p.stderr)
    return p


def conflicts(repo, a, b, attr):
    p = git(repo, "merge-tree", "--write-tree", "--name-only", "--no-messages", a, b, attr=attr)
    lines = p.stdout.split("\n")
    return p.returncode, lines[0], set(l for l in lines[1:] if l)


def main():
    rows = []
    for line in open(sys.argv[1]):
        url, path = line.split()
        name = os.path.basename(path)
        clone = f"{OUT}/clones/{name}.git"
        if not os.path.exists(clone):
            git(".", "clone", "-q", "--bare", "--shared", "/workspace/projects/" + path, clone, check=True)
        merges = git(clone, "log", "--exclude=refs/tl10/*", "--all", "--merges", "--format=%H %P|%cn|%s").stdout.splitlines()
        for m in merges:
            shas, cn, subj = m.split("|", 2)
            parts = shas.split()
            if len(parts) != 3:
                continue
            mc, p1, p2 = parts
            base = git(clone, "merge-base", p1, p2).stdout.strip()
            if not base:
                continue
            t1 = git(clone, "diff", "--quiet", base, p1, "--", TL).returncode
            t2 = git(clone, "diff", "--quiet", base, p2, "--", TL).returncode
            if not (t1 and t2):
                continue
            ru, tu, cu = conflicts(clone, p1, p2, mc)       # attributes from the merge result
            rn, tn, cn_ = conflicts(clone, p1, p2, EMPTY)   # attributes disabled
            rows.append(dict(repo=name, merge=mc[:9], github=(cn == "GitHub"), subj=subj[:70],
                             union_conflicts=sorted(cu), plain_conflicts=sorted(cn_),
                             plain_only_tl=(sorted(cn_) == [TL])))
    json.dump(rows, open(f"{OUT}/merges.json", "w"), indent=1)
    both = len(rows)
    gh = [r for r in rows if r["github"]]
    print(f"merges where both sides changed {TL}: {both} (GitHub-made: {len(gh)})")
    print(f"  conflict without union: {sum(1 for r in rows if TL in r['plain_conflicts'])}"
          f" · conflict with union: {sum(1 for r in rows if TL in r['union_conflicts'])}"
          f" · timeline is the ONLY no-union conflict: {sum(1 for r in rows if r['plain_only_tl'])}")
    print(f"  GitHub-made merges that conflict on {TL} without union: "
          f"{sum(1 for r in gh if TL in r['plain_conflicts'])}")
    print(f"repos with ≥1 such merge: {len(set(r['repo'] for r in rows))}")


if __name__ == "__main__":
    main()
```

### `prs.py`

```python
#!/usr/bin/env python3
"""For each open PR, fetch base + refs/pull/N/head into the /build/tmp bare clone and
re-merge with and without gitattributes; compare with GitHub's `mergeable` verdict."""
import subprocess, os, json, sys
sys.path.insert(0, "/build/tmp/tl10")
from merges import git, conflicts, EMPTY, TL  # noqa  (merges.py main guarded below)

OUT = "/build/tmp/tl10"
slug2clone = {}
for line in open(f"{OUT}/repos.txt"):
    url, path = line.split()
    slug = url.split("github.com")[1].lstrip(":/").removesuffix(".git")
    slug2clone[slug.lower()] = f"{OUT}/clones/{os.path.basename(path)}.git"

rows = []
for line in open(f"{OUT}/open_prs.txt"):
    slug, num, gh_state, base, head = line.split()
    clone = slug2clone[slug.lower()]
    src = f"https://github.com/{slug}.git"
    f = subprocess.run(["git", "-C", clone, "-c", "credential.helper=!gh auth git-credential", "fetch", "-q", src,
                        f"+refs/heads/{base}:refs/tl10/{num}/base", f"+refs/pull/{num}/head:refs/tl10/{num}/head"],
                       capture_output=True, text=True)
    if f.returncode:
        rows.append(dict(slug=slug, pr=num, gh=gh_state, err=f.stderr.strip()[:120])); continue
    b, h = f"refs/tl10/{num}/base", f"refs/tl10/{num}/head"
    mb = git(clone, "merge-base", b, h).stdout.strip()
    touch_b = git(clone, "diff", "--quiet", mb, b, "--", TL).returncode == 1
    touch_h = git(clone, "diff", "--quiet", mb, h, "--", TL).returncode == 1
    _, _, cu = conflicts(clone, b, h, b)       # attributes from the base branch (what GitHub would use)
    _, _, cp = conflicts(clone, b, h, EMPTY)   # attributes disabled
    rows.append(dict(slug=slug, pr=num, gh=gh_state, head=head, tl_both_sides=touch_b and touch_h,
                     union_conflicts=sorted(cu), plain_conflicts=sorted(cp)))
json.dump(rows, open(f"{OUT}/prs.json", "w"), indent=1)
for r in rows:
    if "err" in r:
        print(f"{r['slug']}#{r['pr']} {r['gh']} fetch-error"); continue
    print(f"{r['slug']}#{r['pr']:<4} gh={r['gh']:<11} tl-both={str(r['tl_both_sides']):<5} "
          f"union={len(r['union_conflicts'])} {','.join(r['union_conflicts'])[:50]:<50} "
          f"plain={len(r['plain_conflicts'])} {','.join(r['plain_conflicts'])[:60]}")
```

### `sides.py`

```python
#!/usr/bin/env python3
"""For every 2-parent merge in the deduped clones: which sides added timeline lines,
and would they still have if machine events (file_changed, symbol_index*) were not written?"""
import json, os, subprocess, collections
from merges import git, TL

OUT = "/build/tmp/tl10"
MACHINE = {"file_changed", "symbol_index", "symbol_index_incremental"}


def added(clone, a, b):
    d = git(clone, "diff", "--unified=0", "--no-color", a, b, "--", TL).stdout
    out = []
    for l in d.splitlines():
        if l.startswith("+") and not l.startswith("+++"):
            try:
                out.append(json.loads(l[1:]).get("event", "?"))
            except Exception:
                out.append("?")
    return out


c = collections.Counter()
kinds = collections.Counter()
DURABLE = {"decision", "trap", "invariant", "pattern", "rule", "hazard", "conflict_record"}
for line in open(f"{OUT}/repos.txt"):
    clone = f"{OUT}/clones/{os.path.basename(line.split()[1])}.git"
    for m in git(clone, "log", "--exclude=refs/tl10/*", "--all", "--merges", "--format=%P").stdout.splitlines():
        ps = m.split()
        if len(ps) != 2:
            continue
        base = git(clone, "merge-base", *ps).stdout.strip()
        if not base:
            continue
        s1, s2 = added(clone, base, ps[0]), added(clone, base, ps[1])
        h1, h2 = [e for e in s1 if e not in MACHINE], [e for e in s2 if e not in MACHINE]
        c["merges"] += 1
        c["branch_touches"] += bool(s2)
        c["branch_touches_human_only"] += bool(h2)
        c["both_touch"] += bool(s1 and s2)
        c["both_touch_human_only"] += bool(h1 and h2)
        c["lines_total"] += len(s2)
        c["lines_machine"] += sum(e in MACHINE for e in s2)
        kinds.update(set(h2))
        c["branch_touches_decision_class"] += bool([e for e in h2 if e in DURABLE])
for k, v in c.items():
    print(f"{k:28} {v}")
print(f"branch side touches timeline: {c['branch_touches']/c['merges']:.0%} → human-only {c['branch_touches_human_only']/c['merges']:.0%}")
print(f"both sides touch (conflict candidate without union): {c['both_touch']/c['merges']:.0%} → human-only {c['both_touch_human_only']/c['merges']:.0%}")
print(f"machine share of branch-side added lines: {c['lines_machine']/max(1,c['lines_total']):.0%}")
print("human event kinds on branch sides (merges containing ≥1):", kinds.most_common(14))
print(f"branch side adds a durable-why event: {c['branch_touches_decision_class']/c['merges']:.0%}")
```

### `writers.py`

```python
"""Option (b) collision measure: for merges where both sides added timeline lines, would a
per-writer file (keyed by agent, or by agent+branch) have been appended on both sides?"""
import json, os, collections
from merges import git, TL
MACHINE = {"file_changed", "symbol_index", "symbol_index_incremental"}
def added(clone, a, b):
    out = []
    for l in git(clone, "diff", "--unified=0", "--no-color", a, b, "--", TL).stdout.splitlines():
        if l.startswith("+") and not l.startswith("+++"):
            try: out.append(json.loads(l[1:]))
            except Exception: pass
    return out
c = collections.Counter(); same = collections.Counter()
for line in open("/build/tmp/tl10/repos.txt"):
    clone = f"/build/tmp/tl10/clones/{os.path.basename(line.split()[1])}.git"
    for m in git(clone, "log", "--exclude=refs/tl10/*", "--all", "--merges", "--format=%P").stdout.splitlines():
        ps = m.split()
        if len(ps) != 2: continue
        base = git(clone, "merge-base", *ps).stdout.strip()
        if not base: continue
        for mode in ("all", "human"):
            s1, s2 = (added(clone, base, p) for p in ps)
            if mode == "human":
                s1 = [e for e in s1 if e.get("event") not in MACHINE]; s2 = [e for e in s2 if e.get("event") not in MACHINE]
            if not (s1 and s2): continue
            c[mode] += 1
            a1 = {e.get("agent", "?") for e in s1}; a2 = {e.get("agent", "?") for e in s2}
            if a1 & a2: c[mode + "_same_agent"] += 1; same.update(a1 & a2) if mode == "human" else None
            b1 = {(e.get("agent"), e.get("branch")) for e in s1}; b2 = {(e.get("agent"), e.get("branch")) for e in s2}
            if b1 & b2: c[mode + "_same_agent_branch"] += 1
print(dict(c)); print("agents colliding (human-only):", same.most_common(8))
```

### `order.py`

```python
#!/usr/bin/env python3
"""Out-of-order (UTC-normalised) and exact-duplicate lines across the fleet's timelines."""
import json, glob, datetime
inv = dup = tot = repos_inv = n = 0
for f in sorted(glob.glob('/workspace/projects/*/.dejavue/timeline.jsonl')):
    n += 1; prev = None; seen = set(); r_inv = 0
    for l in open(f, errors='replace'):
        l = l.strip()
        if not l: continue
        tot += 1; dup += l in seen; seen.add(l)
        try:
            t = datetime.datetime.fromisoformat(json.loads(l)['ts'].replace('Z', '+00:00'))
            t = t if t.tzinfo else t.replace(tzinfo=datetime.timezone.utc)
        except Exception: continue
        r_inv += bool(prev and t < prev); prev = t
    inv += r_inv; repos_inv += bool(r_inv)
print(f"timelines={n} lines={tot} out-of-order={inv} in {repos_inv} repos; exact-duplicate lines={dup}")
```

### `p.py` (throwaway prototype, file-per-event cost on crush-ast data; `/build/tmp/tl10/proto/`)

```python
import json,os,subprocess,time,sys,collections
src='/workspace/projects/crush-ast/.dejavue/timeline.jsonl'
ev=[json.loads(l) for l in open(src) if l.strip()]
MACH={'file_changed','symbol_index','symbol_index_incremental'}
def run(*a): return subprocess.run(a,capture_output=True,text=True,check=True).stdout
os.environ.update(GIT_CONFIG_GLOBAL='/dev/null',GIT_AUTHOR_NAME='p',GIT_AUTHOR_EMAIL='p@x',GIT_COMMITTER_NAME='p',GIT_COMMITTER_EMAIL='p@x')
for label,evs,shard in [('a-flat-all',ev,False),('a-month-all',ev,True),('a-flat-human',[e for e in ev if e.get('event') not in MACH],False),('jsonl-all',ev,None)]:
    d=f'/build/tmp/tl10/proto/{label}'; os.makedirs(d); os.chdir(d); run('git','init','-q','-b','main')
    t=time.time()
    if shard is None:
        os.makedirs('.dejavue'); open('.dejavue/timeline.jsonl','w').writelines(json.dumps(e)+'\n' for e in evs)
    else:
        for i,e in enumerate(evs):
            sub=f".dejavue/events/{e['ts'][:7]}" if shard else '.dejavue/events'
            os.makedirs(sub,exist_ok=True); open(f'{sub}/{i:06d}.json','w').write(json.dumps(e)+'\n')
    run('git','add','-A'); run('git','commit','-qm','x'); tw=time.time()-t
    t=time.time(); [run('git','status','--porcelain') for _ in range(5)]; ts=(time.time()-t)/5
    t=time.time(); n=0
    for root,_,fs in os.walk('.dejavue'):
        for f in fs:
            for l in open(os.path.join(root,f)): json.loads(l); n+=1
    tr=time.time()-t
    # cost of one more event: size of tree objects a new commit must write
    if shard is None:
        open('.dejavue/timeline.jsonl','a').write('{"event":"decision"}\n')
    else:
        sub=".dejavue/events/2026-10" if shard else '.dejavue/events'; os.makedirs(sub,exist_ok=True); open(f'{sub}/zz.json','w').write('{"event":"decision"}\n')
    run('git','add','-A'); run('git','commit','-qm','y')
    trees=run('git','diff-tree','-r','-t','HEAD~1','HEAD').splitlines()
    tsz=sum(int(run('git','cat-file','-s',l.split()[3])) for l in trees if l.split()[1]=='040000')
    files=sum(len(fs) for _,_,fs in os.walk('.dejavue'))
    print(f"{label:14} events={len(evs):5} files={files:5} write+commit={tw:5.2f}s status={ts*1000:5.0f}ms read-all={tr*1000:5.0f}ms new-event-tree-bytes={tsz}")
```

## Appendix B: `repro.sh` (local reproduction, §1.4)

Run in an empty directory: `bash repro.sh`.

```bash
set -e
export GIT_CONFIG_GLOBAL=/dev/null GIT_AUTHOR_NAME=r GIT_AUTHOR_EMAIL=r@x GIT_COMMITTER_NAME=r GIT_COMMITTER_EMAIL=r@x
git init -q -b main w && cd w
mkdir .dejavue && echo '.dejavue/timeline.jsonl merge=union' > .gitattributes
echo '{"ts":"2026-10-05T10:00:00Z","event":"init"}' > .dejavue/timeline.jsonl
git add -A && git commit -qm base
git switch -qc a && echo '{"ts":"2026-10-05T10:05:00Z","event":"decision","by":"a"}' >> .dejavue/timeline.jsonl && git commit -qam a
git switch -q main && git switch -qc b
echo '{"ts":"2026-10-05T10:01:00Z","event":"decision","by":"b"}' >> .dejavue/timeline.jsonl
echo '{"ts":"2026-10-05T10:09:00Z","event":"plan","by":"b"}'     >> .dejavue/timeline.jsonl && git commit -qam b
echo "## 1. merge-tree, attributes from the worktree (non-bare: union honoured)"
git merge-tree --write-tree --name-only a b; echo "exit=$?"
echo "## 2. same merge, attributes disabled (--attr-source=<empty tree>)"
git --attr-source=4b825dc642cb6eb9a060e54bf8d69288fbee4904 merge-tree --write-tree --name-only a b || echo "exit=$?"
cd .. && git clone -q --bare w bare.git && cd bare.git
echo "## 3. bare repo (how a forge stores it), default config"
git merge-tree --write-tree --name-only a b || echo "exit=$?"
echo "## 4. bare repo with attr.tree=a (read .gitattributes from a commit)"
git -c attr.tree=a merge-tree --write-tree --name-only a b; echo "exit=$?"
cd ../w && git switch -q a && git merge -q --no-edit b
echo "## 5. 'git merge b' into a, union honoured: result order"
cat .dejavue/timeline.jsonl
```

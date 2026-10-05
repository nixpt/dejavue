# 09: Conflict-free timelines, and the boundary with session records

**Status:** design, accepted by the maintainer on 2026-10-05. Not yet implemented. The storage change needs a DCP
version bump (see "Spec impact").
**Applies to:** DCP §6.1 (timeline), §6.3 (state and handoff), §8.1 (base loop).

## 1. The problem: a single shared `timeline.jsonl` conflicts on forges

`.dejavue/timeline.jsonl` is one append-only file shared by every branch. dejavue asks git to merge it with the
built-in union driver:

```gitattributes
.dejavue/timeline.jsonl merge=union
```

That works for merges done with local git. It does **not** work for merges done by a hosted forge's "merge pull
request" button, or for the forge's mergeability check. Forges merge in a **bare** repository, and a bare repository
reads no `.gitattributes` from the tree unless `attr.tree` is configured, which forges don't expose. So two branches
that both append to the timeline show as *conflicting* on the forge even though `git merge` resolves them cleanly
locally.

Reproduce it with plain git:

```bash
git init -q demo && cd demo
printf '.dejavue/timeline.jsonl merge=union\n' > .gitattributes
mkdir .dejavue && printf '{"e":0}\n' > .dejavue/timeline.jsonl
git add -A && git commit -qm base
git switch -qc a && printf '{"e":"a"}\n' >> .dejavue/timeline.jsonl && git commit -qam a
git switch -q - && git switch -qc b && printf '{"e":"b"}\n' >> .dejavue/timeline.jsonl && git commit -qam b

# 1. non-bare, attributes from the worktree: clean (union honoured)
git merge-tree --write-tree a b >/dev/null && echo clean

# 2. how a forge stores it: a bare clone with default config -> CONFLICT
git clone -q --bare . ../demo.git && git -C ../demo.git merge-tree --write-tree a b >/dev/null || echo conflict

# 3. the same bare repo told where to read attributes: clean again
git -C ../demo.git -c attr.tree=a merge-tree --write-tree a b >/dev/null && echo clean
```

Union merging has two more costs:

- **Order.** Union concatenates both sides' new lines, so the merged file is no longer in time order.
- **Deletions don't stick.** Union keeps every line either side has. A line deleted on one branch (for example,
  text scrubbed for privacy) comes back when a branch that still has it merges.

Removing the post-commit hook (done: it now does nothing) removes most of the timeline traffic, because most events
were machine-written copies of `git log`. It doesn't remove the problem. Every deliberate capture on two branches
still touches the same file.

## 2. Design: session directories of immutable event files

```
.dejavue/timelines/<date>.<agent>@<box>.<session-id>/<event-id>.json
```

- **One directory per working session, one file per event.** `<date>` is the session's start date (`YYYY-MM-DD`),
  `<agent>@<box>` names the writer and the machine it ran on, and `<session-id>` is the session identifier of the
  session tool in use. A capture made outside any session goes to a per-writer, per-day fallback session directory.
- **Event files are immutable.** They are written once and never appended to or rewritten. The same path therefore
  always holds the same content, so neither local git nor a forge can produce a conflict. That holds after a squash
  merge followed by more work on the branch, after a cherry-pick, and when an in-flight branch is copied elsewhere.
  (An append-only file per session was considered and rejected for exactly those cases: they produce add/add
  conflicts.)
- **Deletions merge cleanly.** Removing an event file is an ordinary file deletion, so a scrub stays scrubbed.

### 2.1 Event identity and ordering

`<event-id>` is a sortable 128-bit identifier: a hybrid logical clock timestamp (wall-clock milliseconds, advanced
past the newest event the writer has seen so that it never goes backwards), a counter, and random bits, encoded so
that lexical order is time order. Machines with skewed clocks still produce ids that order causally within a writer
and stay unique across writers.

An optional `parents: [<event-id>, …]` field turns the timeline into a causal graph. A view can then show forks and
joins between sessions instead of one interleaved list. It survives squash merges, because it doesn't depend on
commit history.

### 2.2 Reading

The timeline is the union of every event file under `.dejavue/timelines/`, plus a legacy `timeline.jsonl` if present
(read as one more source, never written again), sorted by event id.

Views are cheap:

- one session: list one directory
- one agent, one machine or one date: glob the directory names
- one branch: list the event files reachable from that branch's tree
- everything: all events sorted by id

`context`, `recall` and the full-text index read the merged stream. Nothing about the on-disk layout leaks into
their output.

### 2.3 Migration

Read both layouts, write only the new one. A repository switches the next time a writer with the new version
captures something in it. No bulk conversion, and the legacy file is kept as is: its events carry no session
id, so splitting it into session directories would invent provenance.

## 3. The boundary: durable "why" vs session records

dejavue records why the code is the way it is. Session tools record what happened during a working session. The
two used to overlap (decisions written to both, two kinds of handoff). The boundary:

**Test:** would a fresh agent, on a different machine, need this to avoid a mistake or avoid re-deciding something?
Then it is a dejavue timeline event. Does it describe what someone did, or will do next? Then it is a session record.

| | dejavue timelines | session records |
|---|---|---|
| Holds | decisions (with reasons and rejected alternatives), traps, invariants, rules, supersessions ("X replaced by Y") | session open/close, in-progress findings, shipped work, next steps, checkpoints, briefs, **handoff and current state** |
| Never holds | file-change events (git log has them), session lifecycle, status, next steps | anything a fresh agent needs a year from now without context |
| Written by | explicit capture only (`decision`, `rule`, `trap`, …, or a session tool's "durable" write path) | the session tool, as the session runs |

**One home per record.** A timeline event carries its `session` id as provenance (the directory name already
encodes it). The session record links to the event id and never copies its text.

Consequence: `state.md` and `handoff.md` belong to the session tool, so dejavue stops writing them. That conflicts
with DCP §8.1, which freezes the base loop `init → start → decision → state → handoff`. It will ship together with
the spec change below, not before.

## 4. Spec impact

- **DCP/1.1:** readers MUST read `.dejavue/timelines/**` in addition to `timeline.jsonl`. Writers are unchanged.
  This lets every reader understand the new layout before any writer produces it.
- **DCP/2.0:** writers write `.dejavue/timelines/`, the base loop drops `state` and `handoff`, and §6.3 points at
  session tooling.
- The event fields stay those of §6.1, plus the optional `session` and `parents`.
- **Axiom 0 is unaffected:** files, JSON and the standard library only.

## 5. Open questions

- Whether `<agent>@<box>` belongs in directory names in public repositories, or should be replaced by an opaque
  writer id there.
- Whether `parents` ships in 1.1 or later.
- Packing old sessions into archives, and when, without rewriting history.
- Whether the rendered Markdown views (`decisions.md` and friends) stay committed, which keeps them a shared,
  conflict-prone file, or become generated on demand.

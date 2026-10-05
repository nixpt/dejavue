# 09 — Review (2026-10): is dejavue still the right shape after jsess, `.jagent` v2 and caison?

**Ticket:** DEJAVUE-REVIEW-1 · **Author:** architect · **Date:** 2026-10-05 · **Base:** `9c40693`
**Status:** design review only. Nothing here is ratified. Section 5 lists the calls that belong to the captain.

dejavue was designed before three tools that now overlap it: **jsess** (live session records),
**`.jagent` v2** (planning, worktrees, sessions, `jagent-dejavue`) and **caison** (the fleet's AI-native object
notation). This review maps who owns which record today, measures what dejavue's 94 fleet installs actually hold,
weighs the formats, and ranks four options.

**Short answer:** most of what dejavue writes is now noise, but the part it is good at, the durable
*why* (decisions with reasons and rejected alternatives, committed and travelling with the repo), is something no other
fleet tool does. **Shrink dejavue to that core and give agents a single write path for it from jsess (option D).**
Don't fold it into jsess, and don't move its records to caison.

---

## 0. Method and reproducibility

Every number below was produced read-only on `[main]` on 2026-10-05. Most come from one script,
`measure.py` (full text in **Appendix A**), run as:

```bash
python3 measure.py /workspace/projects
```

"Fleet repos" means `/workspace/projects/*/.dejavue` (depth 1). That is 94 directories. Three or four of them are
clones or worktree checkouts rather than distinct projects (`zorro-agent-nixp-EMOE-14-adapter`,
`Antarikshya-workspace.wt-display`, `bro-cli-bench-tui`), so treat the per-repo counts as ±4.

```bash
ls -d /workspace/projects/*/.dejavue | wc -l                                  # 94
find /workspace/projects -maxdepth 4 -type d -path '*/.jagent/sessions' \
     -not -path '*/worktrees/*' | wc -l                                       # 21
```

---

## 1. Ownership map

What the fleet keeps, which tool owns each record today, who duplicates it, and where they disagree.

| Record | Owner today | Also written or rendered by | Where they disagree |
|---|---|---|---|
| **Architectural decision (the durable why)** | `dejavue decision`: `.dejavue/decisions.md` + timeline event, **committed**. 1,482 fleet-wide; 99% carry a reason, 47% carry rejected alternatives (§2.1). | `jsess decision`: one `text` line in a **gitignored** `.jagent/sessions/*.caison`; no reason or alternatives field (`jsess/src/session.rs:61-74`). Also `foreman-decision`. | **Double entry.** In squadbot, 8 of dejavue's 9 decisions also appear as jsess decisions with the same timestamps (§2.3). jsess's copy is shorter and box-local. dejavue's is richer and travels. |
| **Finding / trap** | Split. Session findings belong to `jsess finding` (`--conf`, `--refs`, `--thread`, closable with `--closes`). Durable footguns belong to `dejavue trap` (append-only). | `dejavue plan` (actionable items), `dejavue note`. | **Lifecycle.** A jsess thread can be closed. A dejavue trap cannot: `trap` has no resolve flag (`dejavue.py`, the `trap` subparser), so a fixed trap stays in every boot packet. This repo's own packet still shows "supersedes is write-only" twice, after decision 2026-06-06 marked it RESOLVED. |
| **Handoff / next steps** | jsess: `checkpoint` (supersedes earlier `next` items) + `close` → `.jagent/sessions/HANDOFF.md`. | `dejavue handoff` → `.dejavue/handoff.md`. The v2 plan (§2.7) narrows it to "`.dejavue/` deltas only" and plans a rename to `updates.md`, deferred to "a separate dejavue pass". That pass never happened. | **Two handoffs, and the stale one is the one agents get.** `agent-launch` prepends the dejavue one to every dispatch (`agent-launch:1426-1447`). squadbot reads only jsess's (`squadbot/brief.py:359`). crush-ast's `handoff.md` is from 2026-08-23 ("CRUSH-119 is complete on `agent/buffy/…`"), with 61 commits since. |
| **Current state** | Unclear. `.jagent/planning/STATE.md` / repo `STATE.md` (read by `foreman-resume`). | `dejavue state` → `.dejavue/state.md`. | `foreman-resume` reads `STATE.md` and never `.dejavue/state.md`. The dejavue copy is a median 49 days and 13.5 commits stale (§2.4). |
| **Boot / arrival packet** | No single owner. | `dejavue context` (prepended by `agent-launch`, trimmed to the 128 KB argv limit); `jsess brief` (SessionStart hook on clear/compact/resume, 4 KB budget); `squadbot brief` (fleet arrival: lanes, DMs, jsess threads, HANDOFF.md, **no dejavue**); `foreman-resume` (worktrees, bridge, STATE.md, **no dejavue**); the SessionStart hook in `~/.claude/settings.json` runs `dejavue context` for workspace-meta only. | Four packets from four sources. Only dejavue's contains the decision log. Only jsess's and squadbot's know what happened in the last session. None links to the others. |
| **Plan / ticket** | `.jagent/planning/` (`TASKS.md`, tickets). | `dejavue plan` already **delegates**: it auto-detects `.jagent/planning/TASKS.md`, `.jagent/TODO.md`, `TODO.md`, `docs/TODO.md` (`dejavue.py:2379-2382`) and falls back to `.dejavue/plan.md`. | Little real conflict. This record is already settled the right way. |
| **Session record** | jsess: `.jagent/sessions/<date>-sN.caison` + rendered `.md`, `INDEX.jsonl`, `HANDOFF.md`, `SESSIONS.md`. **Gitignored** in every repo checked. | Remnants in dejavue: `dejavue start` (`session_start`, 86 events), `handoff`, `state`. | jsess is the owner. dejavue's session verbs are vestigial. |
| **File-change log** | **git.** `git log --name-only` is authoritative. | dejavue post-commit hook → `file_changed` events (33,023, 86% of all events); `dejavue ingest` (1,863 more, a year of git log copied in). | The copy is **worse than the source**: its commit pointers are mostly orphaned (57 of the last 60 in crush-ast, §2.2), and `explain`/`since` already query git directly (`dejavue.py` `_explain_file`, `cmd_since`). |
| **Symbol index** | polydex (`.jagent/symbols.db`). | dejavue only *reads* freshness from `symbol_index` events (9c40693). | No conflict, but the data is stale: 8 repos have ever had a `symbol_index` event, and 6 of them last on or before 2026-07-07. |
| **Recall / search** | `dejavue recall` (SQLite FTS5 over `.dejavue/`, optional embeddings). | `jsess threads`, `jsess show`; plain grep over `.jagent/sessions`. | dejavue alone indexes the durable record. Nothing searches across both stores. |

```bash
# reproduce the store/visibility facts behind the table
for r in deck12 milestones jokersquad squadbot pheobe; do
  echo "$r tracked-sessions=$(git -C /workspace/projects/$r ls-files .jagent/sessions | wc -l) \
ignored=$(git -C /workspace/projects/$r check-ignore -q .jagent/sessions/x && echo yes || echo no)"; done
# → tracked-sessions=0 ignored=yes for all five
grep -n -iE "dejavue|jsess|HANDOFF" /workspace/projects/squadbot/squadbot/brief.py   # jsess + HANDOFF.md only
grep -n -iE "dejavue|jsess" /workspace/projects/jokersquad/bin/foreman-resume        # (no output)
gh repo view nixpt/dejavue --json visibility -q .visibility                           # PUBLIC
gh repo view nixpt/jsess   --json visibility -q .visibility                           # PRIVATE
```

**The structural difference the table hides:** jsess records are **box-local** (gitignored). dejavue records are
**committed** (they travel to every clone, every box, every future agent). Every option in §4 depends on that.

---

## 2. What dejavue still does well, and what is redundant or harmful

### 2.1 What it still uniquely does well

1. **Decisions with a reason and rejected alternatives, committed.** No other fleet tool records *why not*.

   ```bash
   # measure.py-style pass over decision events (Appendix A, part 2)
   decisions 1482 · decision_reason 1480 (99%) · rejected_alternatives 711 (47%)
   artifacts 411 (27%) · outcome 432 (29%) · supersedes 22 (1%)
   ```

2. **The record travels with the repo.** It is in git, union-merged (`merge=union` on `timeline.jsonl` in 89 of
   94 repos), readable without the tool, and it reaches a new box or a fresh clone. jsess's records don't.
3. **`context.md` → generated adapters** (`CLAUDE.md`/`AGENTS.md`/`GEMINI.md` managed blocks). 90 of 94 repos have a
   `context.md`. Nothing else in the fleet generates runner instruction files.
4. **`explain <file|commit>`**: git history composed with the decisions, traps and alternatives that touch a path.
5. **A public, specified standard** (DCP/1.0, `docs/dcp-spec.md`, OCPL-registered per `STEWARDSHIP.md`), with
   Axiom 0: stdlib only, zero setup. jsess is private and Rust, and caison needs a parser.

### 2.2 Harmful: the post-commit hook

The hook is the largest source of noise and the only part of dejavue that damages anything outside `.dejavue/`.

**(a) It is 86% of everything dejavue stores.**

```bash
python3 measure.py /workspace/projects
# repos=94 events=38372 file_changed=34897 (90%) hook-authored file_changed=33023 non-file_changed=3475
# file_changed by agent: git-hook 33023 · ingest 1863 · other 11
# timeline bytes total 14749017   (crush-ast alone: 5001 events, 1.7 MB)
```

In crush-ast, 96 of the last 100 timeline events are hook `file_changed`, and the boot packet's "recent timeline (last
10)" shows **7 of 10** as hook lines. The dispatch packet for this very ticket showed 6 of 10.

**(b) It amends the commit you just made, then records the SHA that the amend orphans.** The hook runs
`dejavue changed --auto --commit $(git rev-parse HEAD) --amend` (`dejavue.py` `_write_hook`, ~line 866).
`cmd_changed` writes events with `sha[:7]` *first* (`dejavue.py:1146-1178`), then `_amend_auto_capture_commit` folds
the timeline into HEAD with `git commit --amend --no-edit --no-verify` (`dejavue.py:1195-1220`), which creates a new
SHA. So the "Recorded N file_changed events for `<sha>`" that foreman saw in crush-ast and squadron names a commit
that no longer exists on any branch, and the timeline lines land inside the amended commit. This is the designed
behaviour (decision 2026-06-28, "post-commit auto-capture amend HEAD"). The orphaned pointer is a bug.

```bash
cd /workspace/projects/crush-ast && python3 - <<'EOF'
import json,subprocess
ev=[json.loads(l) for l in open('.dejavue/timeline.jsonl') if l.strip()]
shas=[]
for e in ev:
    if e.get('event')=='file_changed' and e.get('agent')=='git-hook' and e['commit'] not in shas: shas.append(e['commit'])
un=[s for s in shas[-60:] if not subprocess.run(['git','branch','-a','--contains',s],capture_output=True,text=True).stdout.strip()]
print('distinct hook shas',len(shas),'last60 unreachable from any branch:',len(un))
EOF
# → distinct hook shas 452 last60 unreachable from any branch: 57
```

`link`/`explain <commit>`/`blame` therefore join on SHAs that resolve to nothing.

**(c) It halts `git rebase`.** git's sequencer runs post-commit for every pick. The hook appends to
`timeline.jsonl`, and the next pick aborts. Reproduced on git 2.55 in a throwaway repo (**Appendix B**):

```
Rebasing (1/3)Recorded 2 file_changed events for 71b65d0.
Rebasing (2/3)error: Your local changes to the following files would be overwritten by merge:
	.dejavue/timeline.jsonl
```

Agent worktrees dodge this only because `worktree-setup` points `core.hooksPath` at `.githooks/` (pre-push only).
Shared checkouts, where foreman and the captain rebase, do not. **Workaround today:**
`DEJAVUE_SKIP_AUTO_AMEND=1 git rebase …` (the hook exits immediately when the variable is set).

**(d) It fails silently, and it pins a box-local path.** The generated line ends `2>/dev/null || true` (the `|| true`
is dead after `exec`, but stderr is discarded), which is exactly what this repo's only rule (`rules.md`, 2026-07-14)
forbids. It bakes `Path(sys.argv[0]).resolve()`, so the path depends on whichever `dejavue.py` ran `init`:

```bash
grep -l "/workspace/projects/dejavue/dejavue.py" /workspace/projects/*/.git/hooks/post-commit | wc -l   # 49
grep -l "jagent-dejavue"                       /workspace/projects/*/.git/hooks/post-commit | wc -l   # 2
python3 measure.py …  # post-commit dejavue hook installed: 63 of which --amend: 58
```

**Is it redundant?** Yes. git is the file-change log. `since` and `explain` already read `git log` directly
(`cmd_since`: `git log --oneline <range>`, `git diff --stat`; `_explain_file`: `git log --follow`). Only `blame` relies
on the copied events alone, and it could switch to `git log --follow -- <path>` the same way `explain` does.

### 2.3 Redundant: decision double entry

Agents running both tools write each decision twice:

```bash
cd /workspace/projects/squadbot
grep -A3 'kind: "decision"' .jagent/sessions/*.caison | grep text     # 15 jsess decisions
grep '^## ' .dejavue/decisions.md                                    # 9 dejavue decisions, 8 of them restated above
for r in deck12 milestones jokersquad squadbot pheobe; do
  echo "$r jsess=$(cat /workspace/projects/$r/.jagent/sessions/*.caison 2>/dev/null | grep -c 'kind: "decision"') \
dejavue=$(grep -c '"event": "decision"' /workspace/projects/$r/.dejavue/timeline.jsonl)"; done
# deck12 jsess=6 dejavue=36 · milestones 9/9 · jokersquad 2/9 · squadbot 15/9 · pheobe 0/9
```

Double entry costs turns, and the two copies drift. The jsess copy is the one squadbot surfaces, and it is the copy
that never leaves the box.

### 2.4 Harmful: stale `state.md` / `handoff.md` presented as ground truth

The `dejavue-workflow` skill tells agents to "treat [the boot packet] as ground truth".

```bash
python3 measure.py …
# state.md:   dated 70; >30d 41; >90d 12; median age 49d
# handoff.md: dated 58; >30d 39; >90d 13; median age 60d
python3 - <<'EOF'   # commits landed since each state.md "Updated:" line
import re,subprocess,glob,statistics; out=[]
for p in glob.glob('/workspace/projects/*/.dejavue/state.md'):
    m=re.search(r'Updated:\s*(\S+)',open(p,errors='replace').read())
    if not m: continue
    repo=p.split('/.dejavue')[0]
    n=subprocess.run(['git','-C',repo,'rev-list','--count','--since='+m.group(1),'HEAD'],capture_output=True,text=True).stdout.strip()
    if n.isdigit(): out.append(int(n))
print(len(out),statistics.median(out),sum(n>=20 for n in out))
EOF
# → 76 repos · median 13.5 commits since the last state.md update · 28 repos ≥ 20 commits behind (jokersquad: 337)
```

Recorded `handoff` events (353) and `state_update` events (388) are far outnumbered by commits. The habit lives in
jsess now (`checkpoint`/`close`), so dejavue's copies decay by construction.

### 2.5 Harmful: vendoring skew, and a live tool that exists only in a working tree

```bash
python3 measure.py …   # vendored dejavue.py: 36/94; identical to live: 22; versions: 2.2.0 ×22, 2.1.0 ×14
for r in /workspace/projects/*/; do git -C $r ls-files .dejavue | grep -E 'dejavue\.py$|\.bak$'; done | sort | uniq -c
# → all 36 vendored copies are tracked in git (36 × 5,521 lines); 4 tracked .bak timeline backups (crush-ast)
readlink -f "$(command -v dejavue)"                          # /workspace/projects/dejavue/dejavue.py
git -C /workspace/projects/dejavue log --oneline origin/master..master   # 9c40693 (unpushed)
```

There are three resolvers in use: `~/.local/bin/dejavue` (a symlink), `jokersquad/bin/dejavue` (a wrapper, plus a stale
copy in the plugin cache `…/squadron/jokersquad/0.1.1/bin/dejavue`) and `jagent-dejavue`. All of them land on the
**shared checkout's working tree**, so whatever is checked out there is what every agent and every hook runs, and
today that is a commit GitHub has never seen. The 14 v2.1.0 vendored copies lack `plan`, `rule` and `hook`, which
the fleet's standing CAPTURE-ON-DISCOVERY rule depends on. That only matters on a box where the tier-4 fallback fires.

### 2.6 Harmful: `merge=union` cannot delete, so it resurrects edits

Union merge is the right semantics for an append-only log. It is the wrong semantics for files people edit in place.
This repo shows it: the 2026-05-13 decision bodies were scrubbed of fleet-internal references for the public
release, and merge `f973134` (2026-07-14) brought the pre-scrub text back into the **public** `decisions.md`:

```bash
for c in f973134^1 f973134^2 f973134; do
  echo "$c $(git show $c:.dejavue/decisions.md | grep -cE 'workspace-meta|squadron|Captain s1')"; done
# f973134^1 0 · f973134^2 7 · f973134 7      (still 7 on origin/master)
```

That is why several entries in this repo's own boot packet contain each Reason paragraph twice, once internal and
once genericized. The same thing will happen to any `decisions.md`/`patterns.md`/`invariants.md` edit fleet-wide.

### 2.7 Neutral: unused surface

Most of the v2.x metadata never gets used (decision events, fleet-wide): `tension` 1%, `values` 1%, `domain_owner` 2%,
`supersedes` 1%, `derived_from` 0%, `freshness`/`expires_after` 0%. Command events: `milestone` 7, `epoch_begin`/`epoch_end` 1 each,
`conflict_record` 2 (grep of `event` values across all 94 timelines). This doesn't hurt the fleet (the code is inert) but it is
maintenance weight on a 5,521-line single file. Whether to prune it is a product call for the public tool (§5, C8).

---

## 3. Formats

| | dejavue | jsess | `.jagent/planning` |
|---|---|---|---|
| Event log | `timeline.jsonl`: one JSON object per line, append-only, `merge=union` | one caison document per session, a `[eNNNN]` section per event, sealed by `[close]` | — |
| Rendered views | `decisions.md`, `state.md`, `handoff.md`, `traps.md`, … (union-merged Markdown) | `<date>-sN.md`, `INDEX.jsonl`, `HANDOFF.md`, `SESSIONS.md` | Markdown tickets/boards |
| Committed? | yes | **no** (gitignored) | yes |
| Writers per file | many (every agent, every box, every branch) | one (the session owner) | many |
| Confidence | **categorical lifecycle label**: `speculative/proposed/experimental/adopted/deprecated/verified` (`dejavue.py:5067`) | **numeric** probability `~0.9` (caison native) | — |

**These two "confidence" fields mean different things.** dejavue's records how far a decision has got (proposed →
adopted → verified). jsess's records how sure the writer is that a finding is true. Fleet-wide, dejavue's label
is set on 46% of decisions (`verified` 307, `adopted` 291, `proposed` 69). jsess has 31 numeric confidences across 35
repo sessions (`grep -cE '~0\.[0-9]'`). Neither replaces the other. Converge the *names* (call dejavue's `status`
or `maturity`) before anyone tries to converge the syntax.

**Should dejavue's records move to caison? No.** What it would buy:
- Numeric confidence and `@annotation { … }` provenance on any node. dejavue already has both as plain fields
  (`confidence`, `agent`, `author_type`, `artifacts`). The gain is notation, not capability.
- One notation across jsess and dejavue. That's real, but small.

What it would cost:
1. **Multi-writer merges break.** caison rejects duplicate keys (SPEC §7). Two branches that each append an event
   pick the same next key (`[e0005]`), and a union merge then produces a document the parser **rejects as a whole**.
   A JSONL union merge yields two independent valid lines, and a reader that skips bad lines loses at most one event.
   The shared-log property dejavue depends on (memory `jsonl_merge_union_pattern`) has no caison equivalent. jsess is
   immune only because its files are single-writer and never merged.
2. **Fragility.** jsess's README records that the caison parser "can spin forever on some malformed input (an
   unclosed `{`)", hence the 3 s timeout in `jsess brief --hook`. A shared committed log can't depend on that.
3. **Axiom 0 / DCP.** dejavue is stdlib-only by its own standard (`dcp-spec.md` §0, MUST) and by `STEWARDSHIP.md`
   ("format openness … readable without the CLI"). caison needs a parser: `impl/python` is a 703-line non-stdlib
   package (`find /workspace/projects/caison/impl/python -name '*.py' | xargs wc -l`). Vendoring it would break the
   single-file bias. Requiring it would break DCP conformance, and that change can't be made casually.
4. **Greppability.** One event per line is what makes `grep`, `jq`, `git log -p`, `union` and `wc -l` work. caison
   events span 5+ lines.
5. **Migration.** 38k events in 94 repos, plus every consumer (FTS rebuild, `agent-launch`, polydex's
   `src/dejavue.rs` writer of `symbol_index` events).

**Recommendation for formats:** keep each tool's format where its writer model fits. dejavue stays JSONL + Markdown
(multi-writer, committed, public standard). jsess stays caison (single-writer, local). Converge on a **shared
vocabulary** instead: event kind names (`decision`, `finding`↔`trap`, `next`), a shared `refs` shape, the confidence
naming split above, and a documented field mapping used by the promotion bridge in §4 (D). A real convergence point
would be for the Markdown **views** (`decisions.md` etc.) to be *rendered from* the JSONL, not union-merged
alongside it. That fixes §2.6 without touching the log format.

---

## 4. Options, ranked

Migration in every option follows SQ-213's rule: **on touch, never a sweep.** "Touch" means a repo an agent is
already working in for another reason.

### Rank 1: (D) Shrink dejavue to the durable-why core, with a single write path from jsess

**What changes**
- dejavue **stops logging file changes**: the post-commit hook is removed (or reduced to a non-amending no-op), `blame`
  reads `git log --follow` like `explain` does, and `ingest` stops copying git log into the timeline. Existing
  `file_changed` lines stay where they are, and `dejavue archive --before` can collapse them on touch.
- dejavue's **session verbs retire in fleet repos**. `start`, `handoff`, `state` stay in the CLI (public users have
  no jsess) but `jagent-adopt` and the skills stop telling fleet agents to use them. `dejavue context` points to `jsess brief` /
  `.jagent/sessions/HANDOFF.md` when that store exists, and shows `state.md`/`handoff.md` only with their age and
  "N commits behind" (or not at all past a threshold).
- **One write path for durable records.** `jsess decision --durable --reason … --rejected …` (and `finding --trap`)
  records the session event *and* shells out to `dejavue decision`/`dejavue trap` with the same text and refs.
  Agents call one command. The durable copy lands in the committed store and the session copy stays local.
  jsess doesn't link dejavue as a library. It execs the CLI, the way `jagent-dejavue` already does.
- **Traps and plans become closable** (`--closes <id>` or `dejavue resolve <event_id>`), so the boot packet stops
  repeating fixed problems. `event_id` already exists on 2,472 events.
- **Vendoring off by default for fleet repos** (`init --no-vendor`, as the jagent-dejavue plan §4/§5a already scoped).
- Later: render `decisions.md`/`patterns.md`/`invariants.md` from the timeline instead of union-merging them (§2.6).

**What dejavue keeps:** decisions, traps, invariants, rules, patterns, `context.md` + `export` adapters, `recall`,
`explain`, `since`, `capabilities`, `plan` (already delegating to `.jagent`), the DCP spec.

**Migration cost:** no data migration. One dejavue release (hook removal, `--no-vendor`, closable traps, context
changes) and one jsess change (`--durable` bridge). Per repo, on touch: delete the post-commit hook, delete the tracked
vendored copy (36 repos), optionally `dejavue archive` old `file_changed` lines. That's 3 small steps,
best folded into `jagent-adopt` (jagent-dejavue plan §5a item 4 already proposes this).

**What breaks:** `dejavue-workflow`/`dejavue`/`agent-lifecycle` skills (text changes, already on SQ-231's list of drifted
skills). The CLAUDE.md boilerplate in every repo still works, since `dejavue context` remains the entry point. `agent-launch`'s packet
gets smaller, which is better. `blame` output changes source. External users who relied on `file_changed` history
lose it going forward, which is a public-tool decision (C1).

**Risk:** low to medium. The main risk is the bridge: if `jsess decision --durable` is skipped, decisions go back to
being box-local. Mitigate it with a `jsess close` warning when a session holds `decision` events and the repo's
`.dejavue` gained none.

### Rank 2: (A) Keep dejavue as it is and fix the specific harms

**What changes:** the hook stops amending and records the real SHA (or writes after the amend); it skips when a
sequencer is in progress (`.git/rebase-merge`, `.git/rebase-apply`, `CHERRY_PICK_HEAD`); it stops discarding stderr
and calls `dejavue` on PATH rather than an absolute path. Plus `--no-vendor`, closable traps, and staleness markers in
`context`.

**Migration cost:** re-run `dejavue init --force` (rewrites hooks) on touch in 63 repos.

**What breaks:** nothing.

**Risk:** low, but it **leaves the structural problems in place**. 86% of the store stays a lower-fidelity copy of
`git log`, every commit still writes into the timeline (with no amend, the shared checkout's tree is just dirty
instead), decisions are still double-entered, and the two handoffs still disagree. This is the right *first PR*
under option D, but as a destination it isn't enough.

### Rank 3: (B) Shrink dejavue and delegate the rest, with no bridge

D without the single write path. It is cheaper by one jsess change, but it leaves agents choosing between two
`decision` commands, and the box-local one wins on convenience because jsess is already open. This option is
here so the bridge is visibly a separate captain decision (C3). Without it, D degrades to B.

### Rank 4: (C) Fold dejavue into jsess / `.jagent` as one memory tool

**What changes:** jsess (or a `.jagent/memory/` store) becomes the one writer, durable records move to
`.jagent/`, and `.dejavue/` is retired.

**Migration cost:** high. 94 repos, 38k events, every `CLAUDE.md`/`AGENTS.md` boot stub, `agent-launch`'s packet
builder, polydex's timeline writer, both dejavue skills, the `jagent-dejavue` wrapper, `jagent-adopt`, squadbot's reader.

**What breaks:**
1. **Travel.** jsess stores are gitignored by design (SQ-208's `.gitignore` block). Durable records would need a
   committed sub-store with a multi-writer merge story that caison can't provide (§3).
2. **The public standard.** dejavue is public and DCP-registered. jsess is private. Folding means abandoning DCP
   or open-sourcing jsess.
3. **The v2 plan's own boundary.** `2026-09-18-jagent-sessions-and-bridge-folding.md` §2.7 ratified "`.dejavue/` is
   what an agent must *know*; `.jagent/` is what an agent *does*", and the jagent-dejavue plan §1 rejected moving
   `.dejavue/` under `.jagent/` (102 hardcoded paths, a tool contract broken in every repo, for no reduction in
   content).

**Risk:** high, for little gain over D. D already gives the "one tool from the agent's seat" experience
(agents call jsess) without moving storage.

### Not an option: the status quo

It keeps adding one hook event per touched file per commit (crush-ast: 4,869 events over 452 commits), halting rebases in shared checkouts, double-entering decisions, and
serving a 49-day-old `state.md` as ground truth from a tool whose live version is unpushed.

---

## 5. Recommendation and phased plan

**Recommendation: option D.** dejavue becomes the committed, public, stdlib-only store of the durable *why*, and stops
being a session tracker or a file-change logger. jsess owns the session, and a `--durable` bridge writes to dejavue
so an agent records a decision once. Formats stay as they are; vocabulary converges.

### Phases (each a stopping point, with a go/no-go)

| Phase | Repo | Content | Go/no-go to continue |
|---|---|---|---|
| **P0: hotfix the hook** | dejavue | The minimal option A fix, which is safe whatever later phases decide: no amend (or record the post-amend SHA), skip during rebase/cherry-pick/sequencer, keep stderr, call `dejavue` from PATH. Ship with `9c40693`, tag a release. | The Appendix B rebase repro passes, and `git branch --contains <recorded sha>` succeeds for a fresh commit. |
| **P1: shrink** | dejavue | Hook removal behind a flag (C1), `blame` reads git, `ingest` stops copying git log, `init --no-vendor`, closable traps/plans, stale-aware `context` (age + commits-behind, hook lines hidden from "recent timeline", jsess pointer). | Boot packet for crush-ast is under 50% of today's size with no loss of decisions; test suite green. |
| **P2: bridge** | jsess (+ dejavue docs) | `jsess decision --durable --reason --rejected`, `jsess finding --trap` → exec `dejavue`; `jsess close` warns on un-promoted decisions. Vocabulary mapping documented in both READMEs. | Run in one pilot repo for a week: the squadbot double-entry measure (§2.3) shows no duplicate hand-written decisions. |
| **P3: skills + adopt** | squadron, skills | `dejavue-workflow`/`dejavue`/`agent-lifecycle` text (fold into SQ-231). `jagent-adopt` grows the per-repo cleanup: remove the hook, delete the tracked vendored copy, optional `archive`. | SQ-231's staleness grep is clean for "`dejavue handoff`/`dejavue state` as session tools". |
| **P4: on touch** | each repo | SQ-213 rule: when an agent next works in a repo, `jagent-adopt` applies P3's cleanup on its task branch. No sweep. | n/a (ongoing) |
| **P5 (optional)** | dejavue | Render the `.md` views from the timeline instead of union-merging them. Scrub the resurrected internal text in this repo's public `decisions.md` (§2.6). | Captain call (C6). |

### Captain decisions (not made here)

> **C1. Stop logging file changes in dejavue?** Remove the post-commit hook fleet-wide (recommended) or keep a fixed,
> non-amending one. For the *public* tool, should the hook become opt-in rather than installed by `init`?
>
> **C2. Who owns handoff and state?** Confirm jsess `HANDOFF.md` + `.jagent/planning` STATE as the owners for fleet
> repos, and decide whether dejavue's `handoff.md`/`state.md` are retired in fleet repos or narrowed and renamed
> (`updates.md`, the pass the v2 plan deferred).
>
> **C3. One write path for decisions.** Approve the jsess `--durable` → `dejavue` bridge (D) or leave two commands (B).
>
> **C4. Formats.** Keep JSONL + Markdown for `.dejavue/` and caison for jsess (recommended), and approve renaming
> dejavue's categorical `confidence` to `status`/`maturity`. That rename is a DCP format change (additive alias +
> deprecation) and needs a spec version note.
>
> **C5. Vendoring.** Make `--no-vendor` the default for fleet repos (or the tool default), and remove the 36 tracked
> copies on touch.
>
> **C6. Public vs fleet.** dejavue is public and DCP-stewarded, while jsess is private. Should fleet-specific behaviour
> (jsess pointer, bridge) live in dejavue or only in `jagent-dejavue`/jsess? Is `9c40693` fine to publish as is?
> Should the resurrected internal references in the public `decisions.md` be scrubbed, and should history be
> rewritten for it (not recommended: they are workspace names, not secrets)?
>
> **C7. Release pinning.** Keep the fleet running the shared checkout's working tree, or pin to a tagged release
> (pipx/`DEJAVUE_BIN`) so a branch checkout there can't change every agent's tool?
>
> **C8. Surface pruning.** Deprecate the v2.x metadata and commands with ≤2% use (§2.7), or keep them for public users?

---

## Appendix A: `measure.py`

```python
#!/usr/bin/env python3
# DEJAVUE-REVIEW-1 measurement script (read-only). Usage: python3 measure.py /workspace/projects
import sys, json, hashlib, re, subprocess, collections, datetime as dt
from pathlib import Path
root = Path(sys.argv[1]); live = Path('/workspace/projects/dejavue/dejavue.py')
live_sha = hashlib.sha256(live.read_bytes()).hexdigest()
def ver(p):
    m = re.search(r'^VERSION\s*=\s*"([^"]+)"', p.read_text(errors='replace'), re.M); return m.group(1) if m else '?'
now = dt.datetime.now(dt.timezone.utc)
rows = []
for d in sorted(root.glob('*/.dejavue')):
    repo = d.parent; r = {'repo': repo.name}
    tl = d / 'timeline.jsonl'; ev = []
    if tl.exists():
        for line in tl.read_text(errors='replace').splitlines():
            try: ev.append(json.loads(line))
            except Exception: pass
        r['tl_bytes'] = tl.stat().st_size
    r['events'] = len(ev)
    c = collections.Counter(e.get('event') for e in ev)
    r['types'] = c
    r['hook_fc'] = sum(1 for e in ev if e.get('event') == 'file_changed' and e.get('agent') in ('git-hook', 'session-hook'))
    r['fc'] = c.get('file_changed', 0)
    human = [e for e in ev if e.get('event') != 'file_changed' and e.get('agent') != 'git-hook']
    r['human'] = len(human)
    r['last_human'] = max((e.get('ts', '')[:10] for e in human), default='')
    r['last_any'] = max((e.get('ts', '')[:10] for e in ev), default='')
    v = d / 'dejavue.py'
    r['vendored'] = v.exists()
    if v.exists():
        r['v_same'] = hashlib.sha256(v.read_bytes()).hexdigest() == live_sha; r['v_ver'] = ver(v)
    for f in ('state.md', 'handoff.md'):
        p = d / f; age = None
        if p.exists():
            m = re.search(r'Updated:\s*(\S+)', p.read_text(errors='replace'))
            if m:
                try: age = (now - dt.datetime.fromisoformat(m.group(1))).days
                except Exception: pass
        r[f] = age
    hp = subprocess.run(['git', '-C', str(repo), 'config', 'core.hooksPath'], capture_output=True, text=True).stdout.strip()
    gd = subprocess.run(['git', '-C', str(repo), 'rev-parse', '--git-common-dir'], capture_output=True, text=True).stdout.strip()
    hookdir = Path(hp) if hp else (repo / gd / 'hooks' if gd and not gd.startswith('/') else Path(gd) / 'hooks')
    pc = hookdir / 'post-commit'
    r['hook'] = pc.exists() and 'dejavue' in pc.read_text(errors='replace')
    r['amend_hook'] = r['hook'] and '--amend' in pc.read_text(errors='replace')
    r['ctx'] = (d / 'context.md').exists()
    r['jsess'] = (repo / '.jagent' / 'sessions').is_dir()
    rows.append(r)
T = len(rows); E = sum(r['events'] for r in rows); FC = sum(r['fc'] for r in rows); HFC = sum(r['hook_fc'] for r in rows)
allc = collections.Counter()
for r in rows: allc.update(r['types'])
print(f'repos={T} events={E} file_changed={FC} ({FC*100//max(E,1)}%) hook-authored file_changed={HFC} non-file_changed={E-FC}')
print('event types:', allc.most_common(25))
print('timeline bytes total', sum(r.get('tl_bytes', 0) for r in rows))
for r in sorted(rows, key=lambda r: -r['events'])[:12]:
    print(f"  {r['repo']:28} {r['events']:6} fc={r['fc']:5} human={r['human']:4} last_human={r['last_human']}")
vend = [r for r in rows if r['vendored']]
print(f'vendored dejavue.py: {len(vend)}/{T}; identical to live: {sum(r["v_same"] for r in vend)}; versions:',
      collections.Counter(r['v_ver'] for r in vend).most_common())
for f in ('state.md', 'handoff.md'):
    ages = [r[f] for r in rows if r[f] is not None]
    print(f'{f}: dated {len(ages)}; >30d {sum(a>30 for a in ages)}; >90d {sum(a>90 for a in ages)}; '
          f'median age {sorted(ages)[len(ages)//2] if ages else None}d')
print('post-commit dejavue hook installed:', sum(r['hook'] for r in rows), 'of which --amend:', sum(r['amend_hook'] for r in rows))
print('context.md present:', sum(r['ctx'] for r in rows), ' also has .jagent/sessions:', sum(r['jsess'] for r in rows))
```

Output on 2026-10-05:

```
repos=94 events=38372 file_changed=34897 (90%) hook-authored file_changed=33023 non-file_changed=3475
event types: file_changed 34897, decision 1482, state_update 388, plan 365, handoff 353, trap 169, init 119,
             note 91, session_start 86, invariant 85, export_adapter 83, symbol_index 30, branch_close 19, pattern 17,
             rule 12, milestone 7, …
timeline bytes total 14749017
  crush-ast 5001 · maya 3768 · jokersquad 3433 · zorro-agent-nixp-EMOE-14-adapter 3302 · zorro 3111 · emoe-workspace 1270 …
vendored dejavue.py: 36/94; identical to live: 22; versions: [('2.2.0', 22), ('2.1.0', 14)]
state.md: dated 70; >30d 41; >90d 12; median age 49d
handoff.md: dated 58; >30d 39; >90d 13; median age 60d
post-commit dejavue hook installed: 63 of which --amend: 58
context.md present: 90  also has .jagent/sessions: 19
```

Part 2, decision field fill rates (§2.1, §2.7):

```bash
cd /workspace/projects && python3 - <<'EOF'
import json,glob,collections
F=['decision_reason','rejected_alternatives','confidence','entities','artifacts','outcome','supersedes','durability',
   'tension','values','domain_owner','derived_from','freshness','expires_after','stability','author_type']
c=collections.Counter(); dec=0
for f in glob.glob('*/.dejavue/timeline.jsonl'):
    for l in open(f,errors='replace'):
        try: e=json.loads(l)
        except Exception: continue
        if e.get('event')!='decision': continue
        dec+=1
        for k in F:
            if e.get(k) not in (None,'',[],{},'unknown'): c[k]+=1
print(dec,{k:c[k] for k in F})
EOF
```

## Appendix B: rebase halt repro

```bash
D=/tmp/dv-rebase-repro; rm -rf $D; mkdir -p $D; cd $D
git init -q -b master; git config user.email a@b; git config user.name t
echo a>a; git add a; git commit -qm init
AGENT_NAME=t python3 /path/to/dejavue.py init >/dev/null 2>&1; git add -A; git commit -qm dv
git checkout -qb feat; for i in 1 2 3; do echo $i>f$i; git add f$i; git commit -qm f$i; done
git checkout -q master; echo m>m; git add m; git commit -qm m
git checkout -q feat; git rebase master
# Rebasing (2/3)error: Your local changes to the following files would be overwritten by merge: .dejavue/timeline.jsonl
```

## Appendix C: findings captured during this review (not fixed)

Filed with `dejavue plan` into this repo's `.dejavue/plan.md`:
1. The hook records the pre-amend SHA (§2.2b).
2. The hook halts `git rebase` (§2.2c).
3. The hook swallows stderr and bakes an absolute path (§2.2d).
4. `merge=union` resurrected scrubbed internal text in the public `decisions.md` (§2.6).
5. (caison, not dejavue) `impl/python/README.md:24` still documents the rejected `<key>$confidence` sibling
   projection. The code (`_json.py`) and tests already use the SPEC §6 `$value` wrapper, so this is doc drift only.

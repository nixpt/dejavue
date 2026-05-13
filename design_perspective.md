# Design lead perspective on Deja Vue

Companion to `context.md` (chatgpt) and `continued.md`. Filed internal session by design lead after probing the existing memory stack on this box. Where chatgpt designed dejavue from first principles, design lead is observing the existing wiring and pointing at the seams.

---

## 1. The unstated overlap: most of dejavue already exists as `.planning/`

chatgpt's spec frames dejavue as a *new* repo-local memory layer. It isn't, mostly. The existing memory stack workflow already ships an extensive per-repo memory tree at `.planning/`:

| dejavue spec | already exists as |
|---|---|
| `.memory-service/timeline.jsonl` | `.planning/WORK_LOG.md` (append-only event log) |
| `.memory-service/current_state.md` | `.planning/planning/STATE.md` + `OVERVIEW.md` |
| `.memory-service/decisions.md` | `.planning/knowledge/decisions/` (one file per decision) |
| `.memory-service/handoff.md` | `external_pause_work` writes to WORK_LOG; `external_resume_work` retrieves |
| `.memory-service/semantic/` | `.planning/kcs.db` (Unified Knowledge Store, FTS5) + `external_search_knowledge` |
| `dejavue context` | `external_get_context` (synthesizes WORK_LOG + STATE + ROADMAP + locks) |
| `dejavue boot` / `dejavue enter` | `external_get_context` already does this |
| MCP tools (`dejavue.mcp.*`) | `external_store_fact`, `external_search_knowledge`, `external_recall_facts`, `workspace_mem_*` |
| Decisions/architecture refs | `.planning/knowledge/{architecture,decisions,guides,references,troubleshooting}/` |
| Per-agent sessions | `.planning/agents/` |

This isn't a reason to kill dejavue. It's a reason to **stop framing it as a new memory system** and reframe it as **the lightweight, no-ceremony front door to memory** — for repos that aren't (yet) under the existing memory stack workflow.

## 2. The genuine gap is *zero ceremony*

`.planning/` requires the existing memory stack workflow: milestones, phases, plans, MCP server running, providers configured. Drop a Python script into a third-party repo? Nobody is running `/memory-service:new-project` first.

Dejavue's actual value is **"works in 5 seconds without onboarding"** — `dejavue init && dejavue start`, done. It should be the entry-level memory tool that *grows into* `.planning` when a repo gets serious. Think `pip install` vs `cargo new`.

That repositions the build:

- v0.1 = standalone Python CLI, no MCP dependency, writes plain files. Lives where the user drops it.
- v0.2 = optional `dejavue migrate-to-planning` upgrade path so memory survives the transition.
- v0.3 = optional `dejavue.mcp.*` MCP shim for agents that already speak MCP.

If we ever ship two memory layers without an upgrade path, they will diverge and rot. Bake the path in from day one.

## 3. Semantic recall is wired but currently offline

Maintainer's directive: "semantic memory should already be working, verify."

Result of probe:
- `external_create_embedding` fails: `"Failed to generate embedding using the EXTERNAL Embedder pipeline"`.
- `external_health_check` shows `pipefish` provider DOWN at `localhost:11450`.
- Pipefish is the canonical inference surface (memory `seahorse_pipefish_canonical`), and embeddings route through it.

So the *plumbing* exists (kcs.db, embedding endpoint, search tools), but the *embedder backend* is offline on this box right now. Bringing pipefish back up will likely unblock semantic dejavue without writing any new code.

Recommendation: dejavue should treat the embedder as optional and degrade to keyword/FTS5 search via `workspace_mem_query` or kcs.db's native FTS5 when pipefish is down. **Never block a memory write on the embedder being up.**

## 4. The actual killer command is `since`, not `enter`

chatgpt promotes `dejavue enter` as the boot packet. But that's mostly `external_get_context` rebadged.

The hard one — the one nothing else does cleanly — is:

```
dejavue since <agent>
dejavue since <commit>
dejavue since <date>
```

What changed in this repo since I last touched it? This needs:
- git log delta (mechanical)
- timeline events in the window (cognitive)
- state transitions (was X stable, is it now experimental?)
- decisions made in the window
- semantic recall of "topics that came up while you were gone"

You can't get this from git alone. Git tells you the *what*, not the *why* of new direction. This is the single feature worth building first.

## 5. Reverse-engineer memory from existing artifacts

Adoption fails if dejavue requires retroactive bookkeeping. Most repos already have:
- `.claude/CLAUDE.md`, `.agents/`, `AGENTS.md`
- `CHANGELOG.md`, ADR directories, `docs/decisions/`
- git history, PR descriptions, commit messages
- README, architecture diagrams

First real command should be `dejavue ingest` — scrape these into the timeline + decisions + state. Skip it and dejavue starts empty for every repo it lands in, which means nobody uses it.

## 6. Auto-capture via hooks, not voluntary calls

The spec assumes agents will *call* dejavue voluntarily. They won't, reliably — same fate as 90% of `.claude/CLAUDE.md` files: written once, never updated.

Real adoption needs hooks:
- **Git `post-commit`** → auto-`dejavue changed` with the diff summary (LLM-summarized via cheap model).
- **Claude Code `SessionStart` hook** → auto-`dejavue enter` injected into context.
- **Claude Code `Stop` hook** → auto-`dejavue handoff --auto` when session ends with a non-trivial diff.

This piggybacks on Claude Code's hook system (already used for `voice-drain.sh`, `rtk-rewrite.sh` on this box). Land dejavue as a hook-driven sidecar, not a CLI you remember to type.

## 7. The "no private reasoning" rule throws away the best signal

Decision 004 says don't capture private chain-of-thought. But what's most valuable for future agents is the **rejected alternatives** — "considered approach X, rejected because of constraint Y." That's the reasoning that didn't make it into the code, and it's the part that costs the next agent the most to rediscover.

The rule should be: don't log every token, but **do log the dead ends with reasons**. Approached-but-not-shipped is the unique-value content.

## 8. Memory worthiness gate

The spec says "capture intent, not raw thinking" but doesn't define the filter. Without one, dejavue becomes write-only logspam.

Worthiness criteria (anything below the line, don't capture):

| Capture | Skip |
|---|---|
| Decision that changes architectural direction | Style preferences |
| Constraint non-obvious from the code | Things git diff already shows |
| Blocker requiring external context | "Ran tests, passed" |
| Handoff context the next agent must know | Per-file mechanical edits |
| Dead end + reason rejected | LLM reasoning steps |
| Cross-cutting invariant ("X must never depend on Y") | Routine commits |

If a memory wouldn't be missed when reading the code + git history, it doesn't belong in dejavue.

## 9. Embedding staleness

Semantic recall fails silently when source files change beneath their embeddings. The spec doesn't address this.

Need: embeddings track the `(source_commit, source_path, content_hash)` triple. `dejavue reindex --stale` detects mismatch and re-embeds. Without this, dejavue gets confidently-stated stale memories — the cardinal sin (cf. CLAUDE.md "Before recommending from memory: a memory that names a specific function, file, or flag is a claim that it existed *when the memory was written*").

## 10. Naming collision: `.memory-service/` is taken

`projects/.memory-service/`, `projects/external project/.memory-service/`, `projects/sample project/.memory-service/`, `projects/orchestration/.memory-service/` all exist — each contains a `cache/` subdir from optional MCP memory service's semantic cache. Dropping dejavue artifacts adjacent to `cache/` mixes user-facing memory with cache artifacts.

Options:
- a) Use `.dejavue/` (clean, no collision)
- b) Use `.memory-service/memory/` (sibling to `cache/`)
- c) Rename `.planning` → `.memory-service` and unify (consolidation play — risky, touches multiple projects)
- d) Use `.memory/` (generic, lowest collision risk)

Recommend **(a) `.dejavue/`** for v0.1 — keeps it clean and reversible. Worry about consolidation later.

## 11. Brain-organism mapping

dejavue slots cleanly into the vertebrate-architecture framing (memory `brain_organism_phases`):

| Memory type | Biological analogue | Current implementation |
|---|---|---|
| Cross-session personal memory | Episodic+semantic (hippocampus→neocortex) | `MEMORY.md` |
| Active-project working memory | Working memory (prefrontal) | `PROJECT_STATE.md`, `STATE.md` |
| Per-repo episodic | Hippocampus (event-bound) | **dejavue's gap** |
| Per-repo semantic concepts | Neocortex (decontextualized) | `.planning/kcs.db`, `external_search_knowledge` |
| Team coordination | Social cognition / shared workspace | `.workspace/`, `PROJECT_THREADS.md`, `workspace_mem_*` |
| Procedural (how-to) | Basal ganglia / cerebellum | Skills, `.claude/skills/` |

dejavue's slot is **per-repo episodic memory** — bound to events in time, scoped to one repo, portable with the repo. That's a real gap. The other slots are filled.

## 12. Implementation form: not Python CLI

The prototype is Python with argparse. For productization:

- **Drop the Python CLI as primary surface.** Python adds install drift (`pip`, venv, version pinning) for a tool that should be `curl | sh`.
- **Bash wrapper** for git-hook integration (`post-commit` → append JSONL).
- **existing memory stack MCP tools** (`dejavue.mcp.*`) for agent-side invocation. Zero install for any MCP-aware agent.
- **Single static binary** (Rust or Go) for the rare standalone CLI use case.

A 100-line Bash script + 200-line Rust binary beats a Python venv every time for a tool meant to spread across repos.

## 13. Recommendation for v0.1 scope

If maintainer wants to ship in this session:

**Phase 0 — clean slate**
- `git init` the dejavue/ directory.
- Move chatgpt-seeded `.memory-service/` aside (keep as `examples/seeded-by-chatgpt/` for demo).
- Rename project artifacts away from `.memory-service/` collision.

**Phase 1 — minimum viable productization (no semantic, no MCP)**
- Rewrite the Python CLI as a single Bash script + JSONL writer.
- Add `dejavue since <git-ref>` — the actual killer command.
- Add `dejavue ingest` to seed from `.claude/`, CHANGELOG, git log.
- Add `dejavue worthiness` guidance (built-in `--why` on every command).
- Git post-commit hook scaffold.

**Phase 2 — semantic, when pipefish is back**
- Wrap `external_search_knowledge` as `dejavue recall`.
- Embedding-staleness tracking.
- `dejavue migrate-to-planning` upgrade path.

**Phase 3 — MCP shim**
- `dejavue.mcp.*` tools as thin wrappers around the CLI.
- SessionStart / Stop hook integration in Claude Code.

If maintainer doesn't want to ship this session, the minimum useful deliverable is **this perspective document + a short scope decision**: kill, merge into `.planning`, or productize standalone.

## 14. The risk of duplication

Two memory layers without a hard merge story is *worse* than one mediocre one. If we ship dejavue without an upgrade path to `.planning`, we'll have:
- Agents writing to `.dejavue/` in some repos.
- Agents writing to `.planning/` in others.
- No cross-lookup. No unified recall.
- Eventually one rots while the other lives — and you can't tell which.

Either commit to merging the two (long path) or commit to dejavue being a strict subset/precursor of `.planning` with a documented migration (short path). Don't ship a parallel system.

---

## Design lead's bottom line

Dejavue as chatgpt designed it largely already exists. The genuine remaining value is:
1. **Zero-ceremony entry point** for non-existing memory stack repos.
2. **`since`-style temporal delta queries** — the one feature nothing else gives you cleanly.
3. **Hook-driven auto-capture**, not voluntary CLI calls.
4. **Rejected-alternatives logging** — the part of agent reasoning that's actually worth preserving.
5. **Migration path to `.planning`** so we don't fork the memory layer.

The least useful thing we could do is rebuild what's already in `.planning/`. The most useful is ship the four bullets above and make dejavue *the on-ramp* to the existing memory stack.

# Dejavue Roadmap

Shipped vs in-flight vs future. For per-release details see `CHANGELOG.md`.

---

## ✅ Shipped

### v1.0.0 — stable release (2026-05-27)

On-disk format frozen. 20 commands, 62/62 tests.

**New commands:** `version`, `status`, `log` (+ --since/--agent/--type/--oneline),
`blame`, `note`.

**v0.3 wave (capture discipline + map):**
- Ambient agent identity (AGENT_NAME / CLAUDE_CLI / GIT_AUTHOR_NAME / config file)
- `context` staleness warnings + pre-push hook safety net
- `init --ingest`, `init --map`, `ingest --generate-map`
- `fcntl.flock` concurrent safety on FTS rebuild + ingest
- Per-repo `.dejavue/config` defaults file
- `.gitignore` entries installed by `dejavue init`

### v0.1 — first release (2026-05-13, internal session)

The zero-ceremony per-repo agent memory layer. 13 commands, FTS5 keyword
recall, git post-commit hook, `merge=union` `.gitattributes`, 33/33 tests.
Single Python file, stdlib only.

### v0.2 — semantic recall (2026-05-13, internal session)

`dejavue recall --semantic` with cosine-ranked retrieval against an
OpenAI-compat embeddings endpoint, content-addressed cache, graceful FTS5
fallback. No new runtime deps (`urllib.request`).

### Patch-level fixes (2026-05-15, internal session–internal session)

- `dejavue handoff --next` is now repeatable (`action="append"`); multiple
  next-steps render as a bullet list. Single-value usage unchanged.
- Post-commit hook now captures **merge + root commits** correctly. The
  old `git show --name-only` silently emitted nothing for merge commits
  (default `--diff-merges=off`), so multi-agent projects were losing ~70%
  of capture (audit tool case study, 9 of 13 commits missing). Fix:
  `git diff-tree --no-commit-id -r --name-only -m --first-parent --root`
  to handle merges + root commits uniformly.

---

## ✅ v0.3 — capture discipline + codebase map (shipped as v1.0.0)

Phases 1-7 shipped in the v1.0.0 wave. Phase 6 (commit-msg
`Dejavue-Event:` trailer via `git interpret-trailers`) deferred to v1.1 —
the amend-from-hook pattern risks infinite loops and needs a safer design.

Test gate achieved: 62/62 (was ≥50/50 target).

---

## ✅ v1.1.0 — operational + reliability wave (2026-05-28)

25 commands, 71/71 tests.

- `check` — git-fsck health check (JSONL, hooks, .gitattributes, .gitignore, FTS, map.md)
- `archive --before <date>` — timeline compaction (drops old file_changed, preserves decisions)
- `roster` — agent activity summary (first/last seen, session/decision/note counts)
- `config {list,get,set,unset}` — manage .dejavue/config through the CLI
- `install-skill` — auto-install SKILL.md to ~/.claude/skills/ (or --dir)
- `log --reverse` flag; `recall --limit N` flag
- Embedder circuit breaker (3 failures → 5-min cooldown; state in embedder_circuit.json)

## ✅ v1.2.0 — expression + discovery wave (2026-05-28)

31 commands, 88/88 tests.

- `--type` on `decision` (blocker/claim/question/experiment/checkpoint) + on `note`
- `stats` — event statistics with mini bar chart
- `export --format {json,md}` — full memory snapshot export
- `reference {create,list,update,view}` — reference card management via CLI (`--template api/design`)
- `link <sha>` — reverse-lookup dejavue events for a git commit
- `search` — discoverable alias for `recall`
- `context -n N` — control boot-packet event count
- Tiered embedder auto-detect (ollama → OpenAI → FTS5 fallback)
- Model-aware embedding cache (stale vectors from old model ignored)

## ✅ v1.3.0 — depth + git integration wave (2026-05-28)

36 commands, 100/100 tests.

- `diff <from> [<to>]` — compare memory between two refs (dates or commits); unified diff of state.md/decisions.md + event window
- `timeline [--by day/week/month] [--agent]` — ASCII bar chart of activity over time
- `check --fix` — auto-repair: install missing hooks, .gitattributes, .gitignore, rebuild stale FTS
- `tag {list, filter <tag>}` — list unique tags with counts; filter events by tag
- `note-commit <sha>` — write git note linking commit to last dejavue event (`git notes append`)
- `link` now reads git notes written by `note-commit`
- `event_type` field indexed in FTS5 — `recall blocker` finds `--type blocker` events
- `since` now shows a Notes section (notes in time window with tag + sub-type labels)

## 📌 Reconciliation note (internal session, 2026-06-05)

Several items previously listed as "v1.4 candidates" **already shipped in
v1.3.0** — this section was drifted. Corrected:

- ✅ `dejavue diff <from> [<to>]` — **shipped v1.3.0**
- ✅ `dejavue timeline` (activity chart) — **shipped v1.3.0**
- ✅ `dejavue check --fix` (auto-repair) — **shipped v1.3.0**
- ✅ `log --type` / FTS5 `event_type` indexing — **shipped v1.3.0**

## ✅ v2.0.0 — DCP (DejaVue Context Protocol) — shipped (2026-06-05, internal session)

The maturation step (maintainer-directed internal session) evolves dejavue from *per-repo
agent memory* into **DCP — a portable context interchange standard**: `.dejavue/`
becomes the single source of truth; `AGENTS.md` / `CLAUDE.md` / `GEMINI.md` /
Copilot rules become **generated, non-destructive adapter targets**. dejavue is
the reference implementation; the protocol has a citable spec (Foundry / OCPL).

Shipped internal session across parallel horses (spec/positioning + code), **119/119 tests**,
zero new deps. Release line **v2.0.0**; format backward-compatible (additive, DCP §7).

**Wave (all shipped):**
- ✅ `docs/dcp-spec.md` — **the DCP/1.0 standard** (three layers, Axiom 0,
  adapter + import contracts, `.dejavue/` layout, conformance).
- ✅ README / STEWARDSHIP repositioned — "portable context + memory + adapter
  bridge"; DCP/1.0 named as the stewarded standard; `foundry.toml` → `dcp:1.0`.
- ✅ `context.md` instruction layer + `init` scaffold + `context` surfaces it.
- ✅ `dejavue import <FILE>` — lossless seed of `context.md` (provenance recorded).
- ✅ `dejavue export --target {claude,codex,gemini,copilot,cursor,all}` —
  non-destructive managed-block adapters (append-and-warn / `--replace`; hash staleness in `check`).
- ✅ `references/glossary.md` glossary reference card.
- ✅ Stdlib v1.4: `promote --to planning`, `init --wizard`, reference frontmatter, `diff --format patch`.

**Axiom 0 — Zero-ceremony conformance (hard invariant):** a conforming DCP tool
MUST be usable with no configuration and no files beyond what `init` creates.
Every layer above the base memory log (`context.md`, adapters, glossary,
frontmatter) is **optional and additive**; the base five-command loop
(`init → start → decision → state → handoff`) is frozen and unchanged. **No new
runtime dependency may ever be introduced** (this is why the ONNX embedder tier,
below, is dropped — it would break the single-file stdlib contract).

Design + waves: `docs/plans/2026-06-05-dcp-maturation.md`.

## 🔮 Remaining candidates (post-reconciliation)

> DCP wave + the stdlib v1.4 features all shipped in **✅ v2.0.0 — DCP** above.

### Dropped (contract conflict — see Axiom 0)
- ~~**Local ONNX embedder tier**~~ — would require `onnxruntime`, breaking the
  stdlib-only / no-new-deps invariant. Dropped. (Optional out-of-process
  shellout could be revisited, but never as an import.)

### Lower impact
- **`dejavue archive --compress`** — zstd-compress the backup file on archive (stdlib `zlib`/`lzma` only — no zstd dep).

### MCP-only (separate horizon, memory-service ecosystem)

- MCP tool wrappers around the 13 CLI commands so MCP-native agents can call dejavue via structured tool-use instead of shell. Stays optional — never breaks the zero-ceremony / format-as-contract invariant.

---

## ✅ v2.0.1 — agent workflow depth (2026-06-06)

Shipped. No new deps (Axiom 0 preserved). 43 commands, 134/134 tests.

### Git integration deepening

- **`post-checkout` hook** — print a one-line handoff/state summary whenever `git checkout` or `git switch` changes the branch. Zero friction; fires automatically; agents know the context before they start typing. Install alongside the existing post-commit hook via `dejavue init`.
- **`dejavue since <ref>..<ref>`** — accept git revision-range syntax (`main..HEAD`, `v1.0..v2.0`, `origin/main`) in addition to dates and commits. Makes `since` feel like a native git companion rather than a separate tool.
- **`--supersedes <event-id>`** on `decision` — explicit contradiction tracking. Record that a new decision supersedes an older one; `recall` and `since` can surface "this was later overridden by…" context. Prevents stale decisions from looking authoritative.
- **Commit message trailers (opt-in)** — `dejavue note-commit` can optionally append a `Dejavue-Event: <id>` trailer to the current commit message so the link travels with the commit to GitHub/GitLab. Opt-in flag only; never mandatory.

### New event types

- **`dejavue trap "<text>"`** — first-class "known lie / trap" event. Every mature codebase has misleading names, fake abstractions, historical hacks. Agents waste real time rediscovering them. `trap` events surface prominently in `blame` and `context`. Stored as `event_type: trap`.
- **`dejavue incident "<text>"`** — first-class operational trauma. Outages, data corruption, failed migrations, security incidents. High-value memory that projects routinely lose. Stored as `event_type: incident`; surfaced in `since` and `context`.
- **`dejavue invariant "<text>"`** — first-class architectural invariant ("capsules never access host FS directly", "append-only always"). Populates a `invariants.md` alongside `decisions.md`; surfaces in `context` as a prominent section. Stored as `event_type: invariant`.

### Decision richness

- **`dejavue rejected "<query>"`** — dedicated query command over rejected alternatives. Show all decisions where `--rejected` mentions a topic. The "why not X?" question agents ask constantly, answered in one command.
- **`--supersedes <id>` + `--durability {temporary,tactical,strategic,constitutional}`** on `decision` — classify how long-lived a decision is and whether it supersedes a prior one. Improves recall quality by letting agents filter out tactical decisions when doing architectural reasoning.

---

## 🌅 v3.x and beyond

Bigger ideas that are correct directionally but need DCP/v2.x to stabilize first.

### Cognitive continuity

- **Intent lineage** (`derived_from: [event-id, ...]` field) — explicit chains of intent across events. Lets agents reconstruct reasoning trees: goal → experiment → failure → decision → migration. Without lineage, memory is flat.
- **Project epochs** (`dejavue epoch begin/end "<name>"`) — named eras that frame old decisions. "pre-plugin-architecture decisions" are not as authoritative as "post-capsule-runtime decisions." Prevents old context from misleading agents after major rewrites.
- **`dejavue explain <file|commit>`** — causal reconstruction. Not just "who edited this" but "why does this exist": decision chain + rejected alternatives + incidents + constraints. The long-term killer command.
- **Confidence levels** on decisions — `speculative / proposed / experimental / adopted / deprecated / verified`. Without this, brainstorms and firm decisions look identical in recall.

### Memory management

- **Memory compression lineage** — `archive` already compacts `file_changed` events; extend the principle. Define what is immutable (timeline entries), what may be summarized (dense note clusters), what may be regenerated (FTS, embeddings). Preserve provenance of what was compressed into what.
- **Scope layering** — DCP is currently repo-scoped (correct for v1/v2). Acknowledge workspace/org/personal scope in the spec so the protocol can grow without backward-incompatible changes.
- **Capability negotiation in DCP** — agents can query `dejavue capabilities` and learn what optional layers (semantic recall, managed blocks, schema version) are active in a repo. Prevents silent degradation when adapters encounter older implementations.

### External tool integrations

Follow the architecture pattern: **tool produces signal → thin importer → canonical `.dejavue` event → recall/since/blame**. Never a hard dependency.

Integration tiers (informational; implementation deferred):

| Tier | Integrations |
|---|---|
| **Tier 1 — local dev tools** | lint waivers (clippy/ruff), test annotations (pytest/cargo test), coverage gaps, dependency decisions, task runner discovery, ADR import/export |
| **Tier 2 — forge tools** | GitHub/GitLab PR memory, issue linking, CI failure ingestion, release memory (`dejavue release v2.1.0`) |
| **Tier 3 — AI/runtime tools** | MCP thin adapter (6 tools: context/since/recall/decision/handoff/blame), additional export targets (aider, external agent, continue, cline), shell prompt integration |
| **Tier 4 — org memory** | incident ingestion from observability tools, cross-repo workspace scope, compliance/license memory, ownership maps |

One rule for any integration: it must answer one of — *what changed / why / what failed / what was rejected / what should the next agent know / what invariant must not be violated*. If it can't, it doesn't belong here.

---

## 🛑 Out of scope (won't ship in dejavue itself)

- **Hosted platform / cloud sync** — dejavue must stay filesystem-first, local-first, append-only. The moment it requires a server, hosted infra, or cloud sync, adoption collapses and Axiom 0 breaks. This is the constraint that makes the design coherent.
- **`memory crate` Rust crate consolidation** (audit §860-962) — that's a orchestration-side refactor (unify `agent-mem` / `agent-lib` / `librarian-cli` / `memory core/embedding` into one trait-backed Rust crate). Dejavue's role there is "thin Python consumer of the same contract." Tracked at the workspace level, not here.
- **Inferno-style 9P/Styx service-tree namespaces, capsule isolation, et al.** — external project-side work.
- **Anything that breaks the contract:** new runtime dependencies beyond stdlib, multi-file rewrites of `dejavue.py`, MCP-mandatory operation, mandatory config files.

---

## Source references

- **Audit:** `.workspace/teams/engineering/dejavue-assessment.md` (1031 lines; rounds 1-3: sample project greenfield + audit tool stress test + orchestration/memory core pattern portability + consolidation map). Author: external agent (engineering loan). Design lead correction note at lines 189-209 (the audit's drop-in hook-fix recommendation was empirically broken; real fix uses `-m --first-parent --root`).
- **Map spec:** `projects/incubator/dejavue-map-spec.md` (463 lines). 6-phase adoption strategy for `.dejavue/references/map.md` + sibling reference docs.

Both source docs live in design lead's workspace, not this repo. The above
summary is what's load-bearing for dejavue itself; the source docs cover
more (workspace-level consolidation, etc.) that doesn't fit here.

---

## How this roadmap is maintained

- Versions move from 🚧 → ✅ on tag.
- v0.4 candidates re-prioritize when maintainer picks the next wave.
- Out-of-scope items stay listed so the next reader doesn't re-propose them.
- The map spec + audit are the canonical sources for v0.3 design questions.
  If something contradicts them, fix this file or one of those — don't let
  the inconsistency rot.

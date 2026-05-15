# Dejavue Roadmap

Shipped vs in-flight vs future. For per-release details see `CHANGELOG.md`.
For the design source-of-truth on the v0.3 wave see the references at the
bottom.

---

## ✅ Shipped

### v0.1 — first release (2026-05-13, s156)

The zero-ceremony per-repo agent memory layer. 13 commands, FTS5 keyword
recall, git post-commit hook, `merge=union` `.gitattributes`, 33/33 tests.
Single Python file, stdlib only.

### v0.2 — semantic recall (2026-05-13, s160)

`dejavue recall --semantic` with cosine-ranked retrieval against an
OpenAI-compat embeddings endpoint, content-addressed cache, graceful FTS5
fallback. No new runtime deps (`urllib.request`).

### Patch-level fixes (2026-05-15, s167–s168)

- `dejavue handoff --next` is now repeatable (`action="append"`); multiple
  next-steps render as a bullet list. Single-value usage unchanged.
- Post-commit hook now captures **merge + root commits** correctly. The
  old `git show --name-only` silently emitted nothing for merge commits
  (default `--diff-merges=off`), so multi-agent projects were losing ~70%
  of capture (Khukuri case study, 9 of 13 commits missing). Fix:
  `git diff-tree --no-commit-id -r --name-only -m --first-parent --root`
  to handle merges + root commits uniformly.

---

## 🚧 v0.3 — capture discipline + codebase map (in flight)

Driven by the opencode audit (`.squad/teams/engineering/dejavue-assessment.md`
in foreman's workspace) and the codebase-map spec
(`projects/incubator/dejavue-map-spec.md`). Both authored by opencode under
the engineering team.

Phased so each lands as a single logical commit:

| Phase | Feature | Audit/spec ref |
|-------|---------|----------------|
| 1 | Ambient agent identity (`AGENT_NAME` / `CLAUDE_CLI` / `GIT_AUTHOR_NAME` resolver, replaces `default="unknown"`) | Audit §3 / Layer 3 |
| 2 | `dejavue context` staleness warnings (state.md age, handoff stub, missing map.md) | Audit §4 / Layer 4 |
| 3 | `dejavue init --ingest` (auto-backfill at init — Khukuri-style backfill is the common case) | Audit §2 |
| 4 | Codebase-map MVP: `dejavue init --map` scaffolds `references/`, `dejavue context` lists references, SKILL.md teaches discovery | Map spec Phases 2 + 4 + 5 |
| 5 | Pre-push hook (secondary safety net — catches `--no-verify`, `--amend`, rebase, GitHub merges) | Audit §196 / Layer 1 |
| 6 | Commit-msg `Dejavue-Event:` trailer (reverse git-link via `git interpret-trailers`) | Audit §198 + §456-476 (squadron pattern §1) |
| 7 | `dejavue ingest --generate-map` (lang-aware auto-population: Rust / Python / JS / Go) | Map spec §242-255 / Phase 3 |
| 8 | Version bump → `0.3.0`, CHANGELOG entry, dogfood capture | — |

Test gate: ≥50/50 pass (42 existing + ≥14 new from Phases 1-7).

---

## 🔮 v0.4 candidates

Pulled from the audit's wishlist (§70-93) + Squadron-pattern portability
(§452-625) + joker-core pattern portability (§629-855). Listed by impact-
per-LoC; captain prioritizes for actual v0.4 scope when v0.3 settles.

### High impact

- **`dejavue blame <file>`** — "why does this file exist?" Surfaces decisions + state touching that path. ~30 LoC.
- **`dejavue status`** — git-status-style one-liner ("active agent, last decision, handoff summary, open next-steps"). ~25 LoC.
- **`dejavue log`** — formatted timeline view (oneline, --since, --agent). ~40 LoC.
- **Tiered embedder fallback chain** (joker-core port §634-657) — Local ONNX → Ollama → cloud API → FTS5. Backends return `None` rather than raising. ~80 LoC.
- **Concurrent-safety locking** (audit §52) — `flock(2)` around fts.db rebuilds + ingest. v0.1.2 / v0.4 priority depending on captain choice.

### Medium impact

- **Per-repo `.dejavue/config.toml`** (joker-core port §744-771) — agent identity default, embedder URL, hook toggles, recall defaults. Optional file; absent = current behavior. ~40 LoC.
- **`dejavue note <text> --tag <tag>`** (squadron port §504-524) — lightweight fact storage between "nothing" and full `decision`. ~40 LoC.
- **Embedding staleness tracking** (audit §84) — current cache key is content-hash only; needs `(source_commit, source_path, content_hash)` triple. ~25 LoC.
- **Richer event-type taxonomy** (audit §716-741 + squadron port §566-580) — domain field + new types (`blocker`, `claim`, `question`, `experiment`, `checkpoint`). ~30 LoC schema + recall filter.
- **Circuit breaker for embedder reliability** (joker-core port §659-685) — stop hammering a downed embedder; 5-minute cooldown after 3 failures. ~50 LoC.

### Lower impact / longer horizon

- **`dejavue archive --before <date>`** (audit §86) — timeline compaction for 1yr+ repos.
- **`dejavue check`** (audit §88) — git-fsck-equivalent: JSONL validity, FTS freshness, cross-reference consistency.
- **`dejavue promote --to jagent`** (audit §92) — concrete graduation path; spec before code.
- **`dejavue install-skill`** (audit §62) — auto-install agent-system skills on dejavue install.
- **`dejavue roster`** (squadron port §597-612) — derive agent-activity timeline.
- **First-use wizard** (audit §82) — 3-question init prompt to seed richer initial state.
- **Multi-language project detection** (audit §90) — annotate `file_changed` events with lang/ecosystem context (Cargo.toml / package.json / pyproject.toml).
- **Reference frontmatter + templates** (squadron port §479-502 + §583-595) — structured metadata on `references/*.md`; `dejavue reference --type api --name <foo>` scaffolds from template.

### MCP-only (separate horizon, joker ecosystem)

- MCP tool wrappers around the 13 CLI commands so MCP-native agents can call dejavue via structured tool-use instead of shell. Stays optional — never breaks the zero-ceremony / format-as-contract invariant.

---

## 🛑 Out of scope (won't ship in dejavue itself)

- **`joker-memory` Rust crate consolidation** (audit §860-962) — that's a Squadron-side refactor (unify `agent-mem` / `agent-lib` / `librarian-cli` / `joker-core/embedding` into one trait-backed Rust crate). Dejavue's role there is "thin Python consumer of the same contract." Tracked at the workspace level, not here.
- **Inferno-style 9P/Styx service-tree namespaces, capsule isolation, et al.** — exosphere-side work.
- **Anything that breaks the contract:** new runtime dependencies beyond stdlib, multi-file rewrites of `dejavue.py`, MCP-mandatory operation, mandatory config files.

---

## Source references

- **Audit:** `.squad/teams/engineering/dejavue-assessment.md` (1031 lines; rounds 1-3: arniko-core greenfield + Khukuri stress test + Squadron/joker-core pattern portability + consolidation map). Author: opencode (engineering loan). Foreman correction note at lines 189-209 (the audit's drop-in hook-fix recommendation was empirically broken; real fix uses `-m --first-parent --root`).
- **Map spec:** `projects/incubator/dejavue-map-spec.md` (463 lines). 6-phase adoption strategy for `.dejavue/references/map.md` + sibling reference docs.

Both source docs live in foreman's workspace, not this repo. The above
summary is what's load-bearing for dejavue itself; the source docs cover
more (workspace-level consolidation, etc.) that doesn't fit here.

---

## How this roadmap is maintained

- Versions move from 🚧 → ✅ on tag.
- v0.4 candidates re-prioritize when captain picks the next wave.
- Out-of-scope items stay listed so the next reader doesn't re-propose them.
- The map spec + audit are the canonical sources for v0.3 design questions.
  If something contradicts them, fix this file or one of those — don't let
  the inconsistency rot.

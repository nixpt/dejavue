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

## 🔮 v1.2 candidates

Items from the original wishlist not yet shipped, plus the one deferred v0.3
phase. Listed by impact-per-LoC.

### High impact

- **Commit-msg `Dejavue-Event:` trailer** (deferred from v0.3) — reverse
  git-link via `git interpret-trailers`. Needs a safe design that avoids
  amend-from-hook infinite loops.
- **Tiered embedder fallback chain** — Local ONNX → Ollama → cloud API →
  FTS5. Backends return `None` rather than raising. ~80 LoC.
- **Embedding staleness tracking** — current cache key is content-hash only;
  needs `(source_commit, source_path, content_hash)` triple. ~25 LoC.
- **Circuit breaker for embedder reliability** — 5-minute cooldown after 3
  consecutive failures. ~50 LoC.

### Medium impact

- **`dejavue archive --before <date>`** — timeline compaction for long-running
  repos (1yr+ of `file_changed` events).
- **`dejavue check`** — git-fsck equivalent: JSONL validity, FTS freshness,
  cross-reference consistency.
- **Richer event-type taxonomy** — domain field + new types (`blocker`,
  `claim`, `question`, `experiment`, `checkpoint`). Recall filter support.
- **`dejavue install-skill`** — auto-install the dejavue SKILL.md into the
  user's agent system (Claude Code, Cursor, etc.) on first use.
- **Reference frontmatter + templates** — structured metadata on
  `references/*.md`; `dejavue reference --type api --name <foo>` scaffolds
  from template.

### Lower impact / longer horizon

- **`dejavue roster`** — agent-activity timeline derived from `session_start`
  events.
- **First-use wizard** — 3-question init prompt to seed richer initial state.
- **`dejavue promote --to planning`** — concrete graduation path to a richer
  per-repo memory system; spec before code.

### MCP-only (separate horizon, memory-service ecosystem)

- MCP tool wrappers around the 13 CLI commands so MCP-native agents can call dejavue via structured tool-use instead of shell. Stays optional — never breaks the zero-ceremony / format-as-contract invariant.

---

## 🛑 Out of scope (won't ship in dejavue itself)

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

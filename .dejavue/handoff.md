# Handoff

Updated: 2026-05-13T04:28:33-05:00

## Summary
v0.1 productization complete internal session. Single-file Python CLI (773 LoC), 13 commands, FTS5 recall with LIKE fallback, git post-commit hook auto-capture (worktree-inherited), merge=union .gitattributes for orchestration-pattern branch merges, ctx-pattern absorption (get/list/annotate), rejected-alternatives field on decisions, ingest scrape, since killer-command (date/commit/agent forms with topic keywords), worthiness gate. 33/33 integration tests pass. Self-host dogfood in own .dejavue/.

## Next Steps
v0.1.2: flock(2) on rebuild_fts/ingest for concurrent-same-tree edge case (low priority, orchestration pattern doesn't hit it). v0.2: --semantic flag once optional MCP memory service Embedder pipeline thread closes (PROJECT_THREADS). v0.3: dejavue.mcp.* MCP shim. v0.4: dejavue migrate-to-planning. README + spec docs are the canonical reference; design_perspective.md captures the design rationale; v0.1_scope.md the build plan + architecture ruling.

## Boot Instructions
Read `.dejavue/handoff.md`, `.dejavue/state.md`, `.dejavue/decisions.md`, and `.dejavue/timeline.jsonl` before making changes.


## 2026-05-13T16:33:02-05:00 — annotation
Additional follow-up (2026-05-13, post-1078703 SKILL.md add): consider whether skills/dejavue-workflow/SKILL.md should be promoted via the package install path — e.g., add a 'dejavue install-skill' subcommand that symlinks the SKILL.md into ~/.claude/skills/dejavue-workflow/ as a convenience for Claude Code users; OR ship an INSTALL.md alongside dejavue.py with the manual one-liner. Low priority — v0.1.2/v0.2 milestones unchanged.

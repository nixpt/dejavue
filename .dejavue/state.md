# State

Updated: 2026-05-15T00:14:01-05:00

v0.1 SHIPPED s156 (33/33 tests, 13 commands). v0.2 semantic recall SHIPPED (commit b3b9b93) — lazy cosine-ranked recall via OpenAI-compat embeddings, content-addressed cache, FTS5 fallback. **s166 Option A landed (commit 2c06219)**: skills/{dejavue,dejavue-workflow}/ is now the canonical source for both skills; .claude/skills/ are relative symlinks for in-repo Claude Code auto-discovery; external consumers (workspace-meta/skill-creator/skills/, ~/.claude/skills/) chain through via absolute symlinks. NEW file: skills/dejavue/SKILL.md (entry skill, public-adapted from workspace-meta version, didn't exist in dejavue-repo before). Captain WIP in dejavue.py + tests/test_dejavue.sh uncommitted (not foreman scope). Repo positioned for public-release-prep arc — gated on amp-auditor's substitution matrix landing + workspace dogfooding (exosphere .dejavue adoption decision).

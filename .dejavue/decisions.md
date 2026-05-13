# Decisions


## 2026-05-13T04:11:32-05:00 — Use .dejavue/ directory naming

Reason:
avoids collision with joker-mcp .joker/cache/ directories (foreman_perspective §10)

Rejected alternatives:
- **Use .joker/**: collision with existing joker-mcp cache dirs
- **Use .memory/**: too generic, no project identity


## 2026-05-13T04:11:37-05:00 — FTS5 for v0.1 recall, not embeddings

Reason:
pipefish embedder offline; stdlib sqlite FTS5 ships on all modern Linux; zero install

Rejected alternatives:
- **joker_search_knowledge**: requires MCP dep, violates zero-ceremony principle
- **external embeddings**: pipefish offline this session, adds infra dep


## 2026-05-13T04:11:41-05:00 — Single file, stdlib only

Reason:
drop-in anywhere; no venv, no pip; consistent with v0.1 zero-ceremony principle

Rejected alternatives:
- **Split into modules**: defeats single-file portability goal
- **Add pyyaml/requests**: external deps violate 5-second setup guarantee


## 2026-05-13T16:32:47-05:00 — Place agent-facing SKILL.md at skills/dejavue-workflow/SKILL.md, not at repo root or in docs/

Reason:
Three signals converge on this path: (1) Claude Code's auto-loading convention is <name>/SKILL.md so a downstream symlink ~/.claude/skills/dejavue-workflow/ → <repo>/skills/dejavue-workflow/ works without rename gymnastics; (2) 'skills/' is forward-compatible if dejavue ever grows a second skill (e.g. dejavue-evaluation), avoids retro-restructuring; (3) keeps the human-vs-agent separation crisp at repo root — README.md is for humans, skills/ is for agents. README's docs list gets a one-line pointer for discoverability.

Rejected alternatives:
- **SKILL.md at repo root**: discoverable but doesn't symlink cleanly to ~/.claude/skills/<name>/ without an enclosing directory rename; also blurs the human-vs-agent docs boundary at root
- **docs/skill.md or docs/agents.md**: hides it among design rationale docs; lowercased convention doesn't match Claude Code's expectation of SKILL.md; agents have to grep for it
- **AGENTS.md at root**: matches some ecosystems' conventions but loses the Claude Code SKILL.md format affordance (YAML frontmatter, auto-discoverability) — would force agents to translate


## 2026-05-13T16:32:56-05:00 — Generalize SKILL.md content for public dejavue repo (no workspace-internal references)

Reason:
The skill was first authored under workspace-meta/skill-creator/skills/dejavue-workflow/ with foreman/squadron/workspace-meta-specific cross-links and absolute /home/nixp paths. For the public dejavue repo it must stand alone: replace [[foreman-session-start]] / [[capture-before-redirect]] / [[agent-lifecycle]] cross-links (those skills don't exist outside the source workspace) with pointers to dejavue's own docs (README, docs/05-v0.1-scope.md, docs/04-foreman-perspective.md); drop workspace-meta canonical-store references; replace 'install via squadron tool symlink' with generic 'symlink dejavue.py into ~/.local/bin/'; add stable-role-name agent identity guidance pulled from README's Concurrency section. The two versions intentionally diverge on workspace specificity but stay in sync on dejavue protocol content.

Rejected alternatives:
- **Ship the workspace-internal version verbatim**: would leak nixpt/foreman/squadron references into a public release the maintainer explicitly genericized last commit (ebf36db)
- **Single canonical version in dejavue repo, workspace-meta references via include**: dejavue is the substrate; making workspace-meta depend on dejavue's SKILL.md for its own foreman cross-links inverts the dependency direction


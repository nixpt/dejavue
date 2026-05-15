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


## 2026-05-15T00:14:00-05:00 — Skill canonical source = dejavue repo (Option A)

Reason:
The dejavue project owns its own docs. Edit-once-propagate-everywhere via symlink chain. dejavue-repo skills/ is single source; .claude/skills/ relative-symlinks for in-repo Claude Code auto-discovery; workspace-meta/skill-creator/skills/dejavue* and ~/.claude/skills/dejavue* are absolute symlinks pointing into the dejavue repo. Closes drift between previously-divergent workspace-internal version (in skill-creator/) and the public-adapted version (in dejavue-repo/skills/dejavue-workflow/).

Rejected alternatives:
- **Option B (sync UP to skill-creator, treat workspace-meta as authoring source)**: manual sync overhead, drift will recur on every wording fix, the project ends up not owning its own docs
- **Option C (two intentional versions, one workspace-internal + one public)**: 2x maintenance for any wording fix, dishonest about which is canonical, no obvious win


## 2026-05-15T00:14:00-05:00 — Skills reach agents via TWO channels: clone-time + install-time

Reason:
Captain s166: 'when a user installs dejavue, the skill is copied to claude or their choice of agents.' Two complementary delivery vectors: (1) clone-time — .claude/skills/ ships INSIDE the repo, any Claude Code session opening the repo auto-discovers; works for cloners/contributors. (2) install-time — when user runs pip install dejavue (future), a dejavue install-skill subcommand or post-install hook detects their agent system and installs the skill there; works for end-users who only invoke the CLI. Channel 1 done s166; channel 2 specced in workspace-meta FOREMAN_THREADS dejavue-maturation-arc sub-bullet 5.

Rejected alternatives:
- **Single channel = clone-time only**: most users won't clone the repo, they'll pip install — they'd never see the skill
- **Single channel = install-time only**: contributors working IN the dejavue repo wouldn't get the skill via their session-start; cloning a .dejavue-equipped third-party repo is the discovery moment for them


## 2026-05-15T02:21:41-05:00 — Use diff-tree -m --first-parent --root for merge-commit capture

Reason:
git show --name-only and even audit's recommended git diff-tree --no-commit-id -r --name-only silently emit nothing on merge commits (default --diff-merges=off). Real-world impact: ~70% capture loss in multi-agent projects per opencode's Khukuri audit. -m --first-parent shows what came in via the merge; --root handles initial commits.

Rejected alternatives:
- **git diff --name-only HEAD~1..HEAD**: works for merges but fails for root commits (no HEAD~1) and is two commands worth of parsing
- **audit's git diff-tree --no-commit-id -r --name-only HEAD verbatim**: empirically broken — verified empty output on merge commit before adopting the fix


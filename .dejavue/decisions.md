# Decisions


## 2026-05-13T04:11:32-05:00 — Use .dejavue/ directory naming

Reason:
avoids collision with optional MCP memory service .memory-service/cache/ directories (design_perspective §10)

Rejected alternatives:
- **Use .memory-service/**: collision with existing optional MCP memory service cache dirs
- **Use .memory/**: too generic, no project identity


## 2026-05-13T04:11:37-05:00 — FTS5 for v0.1 recall, not embeddings

Reason:
pipefish embedder offline; stdlib sqlite FTS5 ships on all modern Linux; zero install

Rejected alternatives:
- **external_search_knowledge**: requires MCP dep, violates zero-ceremony principle
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
The skill was first authored under private source workspace/skill-creator/skills/dejavue-workflow/ with design lead/orchestration/private source workspace-specific cross-links and absolute local home paths. For the public dejavue repo it must stand alone: replace [[design lead-session-start]] / [[capture-before-redirect]] / [[agent-lifecycle]] cross-links (those skills don't exist outside the source workspace) with pointers to dejavue's own docs (README, docs/05-v0.1-scope.md, docs/04-design-perspective.md); drop private source workspace canonical-store references; replace 'install via orchestration tool symlink' with generic 'symlink dejavue.py into ~/.local/bin/'; add stable-role-name agent identity guidance pulled from README's Concurrency section. The two versions intentionally diverge on workspace specificity but stay in sync on dejavue protocol content.

Rejected alternatives:
- **Ship the workspace-internal version verbatim**: would leak nixpt/design lead/orchestration references into a public release the maintainer explicitly genericized last commit (ebf36db)
- **Single canonical version in dejavue repo, private source workspace references via include**: dejavue is the substrate; making private source workspace depend on dejavue's SKILL.md for its own design lead cross-links inverts the dependency direction


## 2026-05-15T00:14:00-05:00 — Skill canonical source = dejavue repo (Option A)

Reason:
The dejavue project owns its own docs. Edit-once-propagate-everywhere via symlink chain. dejavue-repo skills/ is single source; .claude/skills/ relative-symlinks for in-repo Claude Code auto-discovery; private source workspace/skill-creator/skills/dejavue* and ~/.claude/skills/dejavue* are absolute symlinks pointing into the dejavue repo. Closes drift between previously-divergent workspace-internal version (in skill-creator/) and the public-adapted version (in dejavue-repo/skills/dejavue-workflow/).

Rejected alternatives:
- **Option B (sync UP to skill-creator, treat private source workspace as authoring source)**: manual sync overhead, drift will recur on every wording fix, the project ends up not owning its own docs
- **Option C (two intentional versions, one workspace-internal + one public)**: 2x maintenance for any wording fix, dishonest about which is canonical, no obvious win


## 2026-05-15T00:14:00-05:00 — Skills reach agents via TWO channels: clone-time + install-time

Reason:
Maintainer internal session: 'when a user installs dejavue, the skill is copied to claude or their choice of agents.' Two complementary delivery vectors: (1) clone-time — .claude/skills/ ships INSIDE the repo, any Claude Code session opening the repo auto-discovers; works for cloners/contributors. (2) install-time — when user runs pip install dejavue (future), a dejavue install-skill subcommand or post-install hook detects their agent system and installs the skill there; works for end-users who only invoke the CLI. Channel 1 done internal session; channel 2 specced in private source workspace PROJECT_THREADS dejavue-maturation-arc sub-bullet 5.

Rejected alternatives:
- **Single channel = clone-time only**: most users won't clone the repo, they'll pip install — they'd never see the skill
- **Single channel = install-time only**: contributors working IN the dejavue repo wouldn't get the skill via their session-start; cloning a .dejavue-equipped third-party repo is the discovery moment for them


## 2026-05-15T02:21:41-05:00 — Use diff-tree -m --first-parent --root for merge-commit capture

Reason:
git show --name-only and even audit's recommended git diff-tree --no-commit-id -r --name-only silently emit nothing on merge commits (default --diff-merges=off). Real-world impact: ~70% capture loss in multi-agent projects per external agent's audit tool audit. -m --first-parent shows what came in via the merge; --root handles initial commits.

Rejected alternatives:
- **git diff --name-only HEAD~1..HEAD**: works for merges but fails for root commits (no HEAD~1) and is two commands worth of parsing
- **audit's git diff-tree --no-commit-id -r --name-only HEAD verbatim**: empirically broken — verified empty output on merge commit before adopting the fix


## 2026-05-15T02:31:02-05:00 — Ship ROADMAP.md as canonical version tracker

Reason:
Maintainer internal session directive — dejavue needs an in-repo roadmap so contributors and adopters can see shipped vs in-flight vs candidate scope at a glance. CHANGELOG covers per-release detail; ROADMAP.md is the wide-angle view.

Rejected alternatives:
- **leave as GitHub Issues/Projects**: works for collaboration but loses the offline/portable invariant — anyone cloning the repo should see roadmap in-tree
- **embed roadmap inside README**: makes README too long; README is the marketing/install doc, ROADMAP is the architecture/planning doc, they want different audiences


## 2026-05-27T23:40:44-05:00 — v1.0.0 scope: v0.3 wave + 5 new commands

Reason:
v0.3 phases (ambient-agent-identity, staleness-warnings, init-flags, pre-push-hook, ingest-generate-map, flock, per-repo-config, gitignore) + version/status/log/blame/note commands + test expansion 33→62 = v1.0.0 feature-complete. Format declared stable.

Rejected alternatives:
- **ship v0.3 only, call it 0.3.0**: format already stable enough for 1.0; adding 5 high-value commands in the same pass costs little and avoids a follow-up release
- **defer Phase-6 commit-msg trailer**: amend-from-hook risks infinite loop without safer design; capture in ROADMAP as v1.1 candidate

Outcome:
v1.0.0 tagged. 20 commands, 62/62 tests, stdlib-only, format stable.


## 2026-05-28T00:08:18-05:00 — v1.1.0 scope: check/archive/roster/config/install-skill + circuit breaker

Reason:
Natural next batch after v1.0: operational health (check, archive), collaboration (roster), ergonomics (config CLI, install-skill), reliability (circuit breaker). All implement cleanly in single file; test count 62→71.

Rejected alternatives:
- **ship circuit breaker alone as v1.0.1 patch**: too small; better to batch with the operational commands

Outcome:
v1.1.0 tagged. 25 commands, 71/71 tests.


## 2026-05-28T00:16:44-05:00 — v1.2.0 scope: expression + discovery wave

Reason:
Richer event sub-types (blocker/claim/question/experiment/checkpoint) + stats/export/reference/link/search + tiered embedder auto-detect + model-aware cache. Each feature independently useful; good cohesion as a 'make dejavue more expressive and discoverable' wave.

Rejected alternatives:
- **defer event sub-types to later**: event_type field adds no migration cost; better to land alongside the commands that benefit from filtering it

Outcome:
v1.2.0 tagged. 31 commands, 88/88 tests.


## 2026-05-28T00:32:10-05:00 — v1.3.0 scope: diff + timeline + check-fix + tag + note-commit + event_type FTS

Reason:
Natural v1.3 wave: comparison (diff), visualization (timeline), operations (check --fix), organization (tag list/filter), git integration (note-commit via git notes), and search improvements (event_type in FTS, since shows notes). All independently valuable; coherent as 'deepen the tool rather than widen it' wave.

Outcome:
v1.3.0 tagged. 36 commands, 100/100 tests.


## 2026-06-05T02:36:28-05:00 — context.md is the DCP source of truth; adapters are generated non-destructively

Reason:
Per ratified internal session plan (D2): export writes a marker-delimited managed block into the target tool's real file. Absent→create block-only; marked→replace fenced region; unmarked hand-written→append block + warn (never clobber); --replace converts whole file. Keeps Axiom 0 (zero new deps, base loop frozen).

Rejected alternatives:
- **blind overwrite**: clobbers hand-written CLAUDE.md
- **staging dir only**: less ergonomic, plan picked real-file managed block


## 2026-06-06T05:44:31-05:00 — init auto-discovery: install in-repo skills + CLAUDE.md boot stub on init (resolves #1)

Reason:
dejavue's core value requires agents to know it exists; init was half-wired — memory scaffold set up but discovery not. CLAUDE.md is the reliable trigger for Claude Code; in-repo skill fallback works without a global install. Both steps idempotent, no new deps (Axiom 0 preserved).


## 2026-06-06T07:49:45-05:00 — [STRATEGIC] note-commit --trailer: require HEAD + clean index, amend before noting

Reason:
git notes are keyed by commit SHA and amending changes the SHA. The original order (write note, then git commit --amend) orphaned the note on the pre-amend object while the trailer shipped on the new commit; and --amend always targets HEAD, so a non-HEAD sha argument silently rewrote the HEAD message. Fix: validate sha==HEAD and a clean index up front, amend FIRST, re-resolve HEAD, then attach the note, so note and trailer always land on the same shipped commit.

Rejected alternatives:
- **keep write-note-then-amend**: orphans the note every time --trailer runs (git notes show HEAD finds nothing)
- **allow a non-HEAD sha with --trailer**: git commit --amend can only rewrite HEAD, so it corrupts the wrong commit message


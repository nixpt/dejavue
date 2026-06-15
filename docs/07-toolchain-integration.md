# Toolchain Integration

**Source:** design notes + design notes
**Status:** Design reference

---

## The Core Principle

> Tools produce signals. Deja Vue preserves the meaning of those signals.

Every tool in a dev workflow generates exhaust — commits, test runs, CI failures, lint waivers, PR review comments, dependency changes. That exhaust is discarded because there is no place to store its *meaning*, only its outputs. DCP is the universal adapter that turns dev-tool exhaust into durable project memory.

---

## Git as Cognitive Substrate

Git is DCP's mechanical substrate, not just a hook source.

**The relationship:**
```
git log      = mechanical history (what changed)
dejavue log  = cognitive history  (why it changed)
dejavue since = unified delta
dejavue blame = causal history
```

The goal is not to wrap git but to overlay it cognitively.

### Commit ↔ memory binding

Every important DCP event can optionally bind to a commit:

```bash
dejavue decision "Use SQLite FTS5" --commit HEAD
```

This turns commits into cognitive checkpoints. The eventual goal is `dejavue explain HEAD` — returning the decision chain, branch intent, and rejected alternatives behind a commit using both git history and project memory.

### Git notes integration

`git notes` under `refs/notes/dejavue` can attach memory to commits non-invasively — no history rewrite, travels with pushed refs, can annotate old commits retroactively.

### Commit message trailers

An alternative to git notes that survives forge platforms without custom ref handling:

```text
Add token bucket middleware

DejaVue-Decision: e142
DejaVue-Session: s88
DejaVue-Refs: rate-limiter, auth
```

Grep-friendly and visible in GitHub/GitLab UI without tooling.

### Branch memory

Branches have intent. The branch lifecycle should have its own DCP surface:

```bash
dejavue branch start feature/rate-limit --goal "Add per-user API throttling"
dejavue branch summary
dejavue branch close --outcome "merged"
```

This turns a branch into a task narrative: intent → commits → decisions → handoff.

### Cognitive blame

`dejavue blame src/auth/session.rs` answers not "who edited this line?" but "why does this file exist, what decisions shaped it, what rejected alternatives matter, what incidents touched it?" — semantic git blame.

### Git hooks as adapter points

| Hook | DCP use |
|------|---------|
| post-commit | capture changed files (v0.1 default) |
| pre-commit | warn about missing decision on architectural changes |
| post-merge | rebuild FTS, detect memory conflicts |
| post-checkout | show handoff/state for switched branch |
| pre-push | validate memory integrity, warn on missing decisions |
| prepare-commit-msg | suggest memory-linked commit message |

The `post-checkout` hook may be the highest-value non-post-commit hook: switching to a branch and immediately seeing the last handoff and open next steps is agent gold.

### Squash/rebase safety

Agents squash branches and lose commit-level detail. `dejavue squash-summary feature/x` before squash prints the cognitive inventory of the branch (decisions, rejected alternatives, unresolved follow-ups) and binds a summary to the squashed commit.

### Worktree coordination

```bash
dejavue worktree spawn reviewer ../repo-review --agent reviewer
```

Creates the worktree, starts a DCP session, sets branch goal, writes initial handoff, ensures merge=union gitattributes. This is where DCP starts enabling lightweight multi-agent dispatch without becoming a full orchestrator.

---

## Integration Tiers

All integrations follow the same pattern:

```
external tool signal
        ↓
thin importer / adapter (optional, Axiom 0 preserved)
        ↓
canonical .dejavue event
        ↓
recall / since / blame / explain
```

Deja Vue reads from external tools when available. It never *depends* on them. Tier 0 works with no external tools at all.

### Tier 0 — Core (no dependencies)

- git + markdown + sqlite FTS5 + JSONL + adapter export
- Everything in `05-v0.1-scope.md`

### Tier 1 — Local Dev Tools (optional command adapters)

**Test frameworks** (pytest, cargo test, jest, Playwright): Record test intent, not just pass/fail. The highest-value test memory is *why* a test was written:

```text
This regression test exists because refresh tokens were once reused after logout.
Do not remove unless session invalidation is redesigned.
```

Commands: `dejavue test record`, `dejavue test-flake "auth refresh race"`

**Linters** (ruff, clippy, mypy, eslint): Preserve meaningful exceptions rather than noisy output:

```bash
dejavue lint waiver "clippy::large_enum_variant" --reason "ABI shape intentional"
```

Prevents agents from "fixing" intentional weirdness.

**Code coverage** (tarpaulin, coverage.py, llvm-cov): Flag security-critical modules with low branch coverage so agents avoid risky blind refactors.

**Dependency managers** (Cargo, uv, npm, Nix flakes): Capture why a dependency was chosen or avoided:

```bash
dejavue deps decision "Use uv over poetry"
```

Especially important for DCP itself, where "zero dependency" is constitutional.

**Static analysis / security scanners** (cargo-audit, Semgrep, CodeQL, osv-scanner): Record accepted risks and fixed vulnerabilities with commit binding:

```bash
dejavue vuln accept-risk CVE-XXXX --reason "dev-only dependency"
dejavue vuln fixed CVE-XXXX --commit HEAD
```

**Task runners** (Make, Just, cargo xtask, tox): Auto-discover build/test/lint commands for context.md population.

**ADR integration** (MADR, Nygard ADRs, docs/adr/*.md): Import existing decision records and export DCP decisions as lightweight ADRs. Deja Vue decisions and ADRs are the same concept at different formality levels.

**Performance / benchmarks** (criterion.rs, hyperfine, flamegraph): Performance discoveries are often forgotten. Recording "FTS rebuild was 80% of runtime; lazy rebuild chosen" prevents future agents from re-optimizing the wrong thing.

### Tier 2 — Forge Tools (network/API optional)

**GitHub / GitLab PRs**: PR review comments, requested changes, and merge rationale are high-value cognitive artifacts. `dejavue ingest github --pr 42` turns review discussion into project memory. A rejected approach in a PR review is exactly the kind of dead-end that git diff doesn't capture.

**Issue trackers** (GitHub Issues, Linear, Jira): Issues are the earliest form of intent. Linking issues to DCP events closes the causal chain: user pain → task → branch → commits → decision → release.

**CI/CD** (GitHub Actions, GitLab CI, Jenkins, Buildkite): CI failures are often high-value rejected alternatives. "Linux tests failed because tmpfs path assumptions differed from macOS; decision: use platform-neutral tempfile API" is exactly the memory that prevents the same failure from recurring.

```bash
dejavue ci explain-failure
dejavue incident from-ci
```

**Changelog integration** (Keep a Changelog, conventional commits, release-please): Memory-aware changelogs include user-visible changes, architectural decisions, breaking changes, migration notes, rejected alternatives, and known risks — much richer than conventional commit parsing.

**Releases**: Git tags are perfect anchors. `dejavue release v1.2.0 --summary "Semantic recall added"` generates a cognitive changelog over the git range.

### Tier 3 — AI/Runtime Tools (agent-facing)

**Agent tool adapters**: `dejavue export --target aider`, `--target external agent`, `--target continue`, `--target cline` generate the correct boot packet for each tool's context format. This is the adapter bridge from dcp-spec.md §9 applied to non-Claude-Code tools.

**MCP tools**: Thin wrappers over the file format — `dejavue.context`, `dejavue.since`, `dejavue.recall`, `dejavue.decision`, `dejavue.handoff`, `dejavue.blame`. MCP is an adapter, not the core. Axiom 0 stays intact.

**IDE integration** (VS Code, Cursor, JetBrains, Zed, Neovim, Helix): Show current handoff in sidebar, show decisions touching current file, warn when editing files with traps, generate decisions from selected diffs. This becomes "ambient memory while coding."

**LSP integration**: A DCP language server provides memory hints at the right moment — hover over a file to see "3 decisions mention this module," diagnostics for invariant violations, code actions to record decisions. Not for code completion; for memory hints.

**Shell integration**: A shell plugin shows branch memory automatically on directory entry:

```bash
dejavue shell init zsh
```

On `cd repo`:
```
Deja Vue: last handoff says "finish adapter tests"
```

**Debugger integration**: Debug sessions reveal hidden knowledge — "crash was not parser-related; root cause was stale generated adapter block after checkout." `dejavue debug note` captures this before it evaporates.

### Tier 4 — Organizational Memory (later)

- Incident memory: operational trauma (outages, data corruption, failed migrations) is among the highest-value memory in software systems
- Observability (OpenTelemetry, Sentry, Honeycomb): production failures that expose environment assumptions
- Feature flags: record why a feature is flagged ("semantic recall hidden because embedding cache format may change")
- License/compliance (cargo-deny, REUSE, license-checker): "Dependency X avoided because license conflicts with OCPL distribution goals"
- Cross-repo workspace memory: the workspace-level extension of repo-scoped DCP

---

## The Integration Filter

Every integration should answer one of these questions. If it cannot, it does not belong:

```
What changed?
Why did it change?
What failed?
What was rejected?
What should the next agent know?
What invariant must not be violated?
```

---

## What DCP Should Never Become

- A hosted platform
- A heavy MCP framework
- An orchestration daemon
- A cloud sync system
- A vector DB product

Keep: filesystem-first, append-only, local-first, tool-agnostic, infra-optional. That constraint is what makes the entire design coherent.

The big idea is not a giant dev platform — it is the universal adapter that turns dev-tool exhaust into durable project memory. Git gives mechanical history. CI gives failure history. Issues give intent history. PRs give review history. Tests give behavior history. Agents give reasoning history. DCP unifies all of that into one portable project memory layer.

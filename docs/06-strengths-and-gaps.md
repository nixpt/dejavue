# Strengths and Gaps

**Source:** design notes + design notes
**Status:** Design reference

---

## What Deja Vue Gets Right

### Axiom 0 — no daemon, no install friction

The single most load-bearing decision. The moment memory requires a daemon, embeddings, Docker, or even `pip install`, adoption collapses. A single Python stdlib file that works immediately after `init` with no config is the reason DCP can become infrastructure rather than "yet another assistant plugin." This is the equivalent of why git succeeded.

### Filesystem format as protocol

Most adjacent projects anchor on a hosted service, an MCP server, or a proprietary index. DCP anchors on:

- append-only JSONL logs
- portable markdown
- git semantics
- graceful degradation
- adapter generation

The `.dejavue/` store is the protocol. Tools — including the reference CLI — are consumers of it. That separation is what allows Claude Code, Codex, Cursor, Aider, and future agents to interoperate through a shared on-disk format without depending on each other.

### `.dejavue/` as canonical truth, not `CLAUDE.md`

Most tooling today treats `CLAUDE.md`, `.cursorrules`, `AGENTS.md`, and Copilot prompt files as authoritative. DCP inverts that: those files are compatibility projections, not the source. The adapter bridge framing follows directly — tool-specific instruction files become generated, non-destructive targets derived from the canonical store.

### `since` — the right primitive

The killer command is not "AI memory" or "semantic context" or "knowledge graphs." It is: **what changed since I was last here?** That maps directly to real agent and developer workflows in a way that no adjacent tool addresses cleanly. Git tells you what changed; `dejavue since` tells you the why and intent over the same window.

### Worthiness gate

Without an explicit capture/skip discipline, memory systems rot into noise. The worthiness gate — and especially the emphasis on recording **rejected alternatives** — targets the highest-value cognitive artifact: the dead ends that git history doesn't show. Agents and future maintainers waste enormous time rediscovering why something was *not* done. DCP makes that first-class.

### Git/worktree awareness

The use of `merge=union` for append-only logs, explicit per-branch session tracking, and awareness of multi-agent worktree fanout is unusually mature. Most AI tooling completely ignores concurrent-agent development realities.

### Graceful semantic fallback

Embeddings are optional acceleration, not foundational truth. FTS5 as the default recall surface avoids vendor lock-in, incompatible vector spaces, and infrastructure brittleness.

### 3-layer DCP model

The separation of instruction layer (context.md), memory layer (timeline.jsonl + decisions.md + state.md + handoff.md), and adapter layer (generated per-tool files) cleanly avoids conflating policy, memory, runtime state, and tool compatibility.

---

## Gaps Worth Closing

These are not v0.1 requirements — they are the next level once the core spec stabilizes.

### 1. Memory stability classes

Everything in the current schema sits together conceptually. Formalizing stability classes would let agents and orchestration systems apply different retention semantics:

| Class | Meaning | Artifact |
|-------|---------|----------|
| Ephemeral | temporary session detail | scratch notes |
| Operational | current repo state | handoff.md |
| Architectural | long-lived design decisions | decisions.md |
| Constitutional | repo invariants | context.md |
| Historical | immutable events | timeline.jsonl |

### 2. Intent lineage

Projects evolve through chains of intent (Goal → Experiment → Failure → Decision → Refactor), but today those relationships are implied. Explicit lineage via `"derived_from": ["e101", "e118"]` fields in events would let agents reconstruct reasoning trees and make "why are we here?" answerable. Without lineage, memory stays flat.

### 3. Contradiction / supersession tracking

When a later decision contradicts an earlier one, recall becomes dangerous if both are returned with equal weight. Explicit supersession fields (`"supersedes": "decision:sqlite-service-mode"`) prevent stale assumptions from misleading agents. This becomes critical when agents start making autonomous changes.

### 4. Confidence levels

Not all memory is equally trustworthy. Brainstorms, abandoned ideas, and tentative notes all look identical to adopted decisions without explicit confidence markers:

```
speculative → proposed → experimental → adopted → deprecated → verified
```

### 5. Temporal decay / freshness

Some memory ages poorly — build commands, deployment steps, temporary constraints. A `"freshness": "volatile"` or `"expires_after": "90d"` field would prevent old operational memory from misleading agents on long-lived projects.

### 6. Project epochs / eras

Long-lived projects change architectural identity over time. Old decisions become misleading when they belonged to a different era. A `dejavue epoch begin "capsule-runtime-era"` primitive would give agents historical framing and prevent them from acting on pre-migration assumptions.

### 7. "Why not" index — first-class rejected alternatives

The worthiness gate already emphasizes rejected alternatives, but this deserves a dedicated query surface: `dejavue rejected "grpc"` returning all attempts, failures, reasons, and contexts. This is among the highest-value institutional memory and currently requires grep over decisions.md.

### 8. Constitutional memory — machine-readable invariants

Some truths are not architectural decisions or operational state — they are repo axioms ("Capsules never access host FS directly," "Everything is append-only"). A dedicated `constitution.md` or structured `invariants:` YAML block would unlock automated review, policy validation, and architectural linting in agents.

### 9. Memory provenance

As agents, CI, orchestrators, and humans all begin writing memory, authorship semantics become necessary — not for access control but for trust interpretation. An `"author_type": "human|agent|ci"` and `"derived_from": "event:abc123"` field prevents synthesized summaries from being treated as primary sources.

### 10. Decision durability

Not all decisions carry equal weight. A `"durability": "constitutional|strategic|tactical|temporary"` field improves recall quality by letting agents weight results appropriately.

### 11. Memory compaction philosophy

Long-lived repos will accumulate millions of events. The design should define — even without implementing — what is immutable, what may be summarized, what may be archived, and what may be regenerated. The principle: compression lineage must be preserved so the original truth is never lost.

### 12. Causal diffs

The future frontier is `dejavue explain auth/` — returning the decision chain, migration rationale, constraints, related incidents, and rejected alternatives for a file or directory. This is architectural causality reconstruction, which is qualitatively different from search.

### 13. Memory scope layering

DCP is currently repo-scoped only. The protocol should acknowledge future scope layers (repo → workspace → organization → personal) without requiring them in v1/v2. Scope-awareness prevents the workspace-level `.workspace/` pattern from being re-invented inside DCP prematurely.

### 14. Capability negotiation

Future DCP consumers will need to negotiate which features are available in a given store. A lightweight `"supports": ["semantic-recall", "managed-blocks"]` handshake avoids brittle hardcoded assumptions.

### 15. Social cognition layer

Projects are human coordination systems, not just codebases. Lightweight domain ownership (`"domain_owner": "networking-team"`) on decisions or events becomes critical in multi-agent + multi-human environments where "who understands auth" is operationally important.

---

## The Deepest Missing Concept: Continuity

The current model captures memory, instructions, and adapters — but not **continuity**: how projects maintain identity across years, humans, agents, rewrites, migrations, forks, and failures.

Git preserves mechanical continuity. DCP can preserve cognitive continuity. That is qualitatively bigger than memory: it is the question of how a project remains coherent over time despite constant change in contributors and tools.

That is the next frontier — not a v0.1 concern, but the direction the design should leave room for.

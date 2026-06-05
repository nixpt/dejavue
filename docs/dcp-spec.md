# DCP — DejaVue Context Protocol

**Version:** DCP/1.0
**Status:** Draft
**Reference implementation:** [dejavue](https://github.com/nixpt/dejavue) (v2.0.0)
**Steward:** OpenKO Foundry (`did:openko:federation:seed`) — see [STEWARDSHIP.md](../STEWARDSHIP.md)
**License:** OCPL-1.1

---

Coding agents are stateless. Every session starts cold: the prior agent's
reasoning — why this design over that one, which dead ends were already tried,
what constraints are invisible in the code — is gone, and the new agent
rediscovers it at full cost. Today each tool also invents its own instruction
file (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, Copilot rules, Cursor rules),
hand-maintained and drifting independently, so the same project context is
duplicated N ways and kept in sync by nobody.

DCP defines a single portable source of truth for that context. A project keeps
one canonical context store; per-tool instruction files become **generated,
non-destructive adapter targets** derived from it. The store also carries the
project's **memory** — the durable *why* (decisions, timeline, state, handoff)
that git records cannot hold. DCP is a *format-and-behavior contract*, not a
runtime: any tool that reads and writes the layout below conforms, with or
without the reference CLI.

---

## §0 — Axiom 0: Zero-ceremony conformance

> **A conforming DCP tool MUST be usable with no configuration and no files
> beyond what `init` creates, and MUST introduce no mandated runtime
> dependency.**

This is the load-bearing invariant; every other clause in this spec answers to
it. Concretely:

- **MUST** work immediately after `init` with zero further setup — no config
  file, no server, no network, no account.
- **MUST NOT** require any layer above the base memory log. The instruction
  layer (`context.md`), the adapter layer (generated tool files), the glossary,
  and frontmatter metadata are **all optional and additive**. A store
  containing only the base memory log is fully conformant.
- **MUST NOT** introduce a new runtime dependency to make any feature work. The
  reference implementation is a single file on the language standard library
  alone. If a proposed feature can only function via a new dependency or a
  mandatory file, it is non-conformant by definition. *(This is the rule by
  which an ONNX-based embedder tier was rejected during design: it would have
  required `onnxruntime`.)*
- **SHOULD** degrade gracefully: when an optional capability (e.g. semantic
  recall via an external embedder) is unavailable, the tool emits at most a
  warning and falls through to a stdlib path; it never blocks a memory write.

The **base loop** — `init → start → decision → state → handoff` — is **frozen**.
Conformance is judged first against Axiom 0: a tool that adds adapters,
glossaries, or wizards but breaks zero-ceremony has failed conformance no matter
what else it implements.

---

## §1 — The three layers

DCP organizes project context into three layers. Only the memory layer is
required (Axiom 0); the other two are additive.

### 1.1 Instruction layer — *what the agent should do*

Operating rules, build/test commands, the architecture map, style and workflow
conventions. The canonical file is **`context.md`** (§3). This is the layer that
adapter targets (CLAUDE.md, AGENTS.md, …) are generated from. Optional.

### 1.2 Memory layer — *what the agent should remember* (required)

The durable, append-mostly record of the project's reasoning:

- **decisions** — architectural decisions with their reasons and, most
  valuably, their *rejected alternatives*.
- **timeline** — an append-only event log (decisions, session starts, file
  changes, notes, handoffs, typed events).
- **state** — a single overwritten snapshot of where the project stands now.
- **handoff** — the boot context the next session needs.

This is the only layer a conforming store must contain. It is what the base loop
writes. See §6 for the format.

### 1.3 Adapter layer — *bridging to existing tools* (generated)

Per-tool instruction files generated from the instruction layer, written
**non-destructively** into each tool's real file (§4), plus an **import**
operation (§5) that seeds the instruction layer from an existing hand-written
file. The adapter layer is what makes `.dejavue/` a *source of truth* rather
than yet another competing standard: the tool-specific files become compatibility
targets, not authorities.

---

## §2 — Canonical layout

The context store lives in a single directory at the repository root. The
canonical name is **`.dejavue/`** (the reference implementation's directory; a
conforming tool MAY use this name for interoperability).

| Path | Layer | Required | Commit? | Purpose |
|---|---|---|---|---|
| `.dejavue/timeline.jsonl` | memory | **yes** | yes | Append-only event log (one JSON object per line). |
| `.dejavue/decisions.md` | memory | **yes** | yes | Append-only architectural decisions. |
| `.dejavue/state.md` | memory | **yes** | yes | Current-state snapshot (overwritten). |
| `.dejavue/handoff.md` | memory | **yes** | yes | Latest handoff for the next session. |
| `.dejavue/context.md` | instruction | no | yes | Instruction-layer source of truth (§3). |
| `.dejavue/references/` | memory | no | yes | Hand-written reference cards (optional). |
| `.dejavue/references/glossary.md` | memory | no | yes | Project glossary reference card (§6.4). |
| `.dejavue/config` | — | no | yes | Per-repo defaults, incl. adapter target overrides. |
| `.dejavue/fts.db` | cache | no | **no** | Local full-text index (rebuildable). |
| `.dejavue/embeddings.jsonl` | cache | no | **no** | Semantic-recall vector cache (rebuildable, model-specific). |
| `.dejavue/.locks/` | runtime | no | **no** | Advisory file locks for concurrent ops. |
| `.dejavue/ingested.lock`, `.dejavue/.first-use` | runtime | no | **no** | Per-checkout / per-user markers. |

Generated **adapter targets** (CLAUDE.md, AGENTS.md, …) live at their tools'
canonical paths, *not* inside `.dejavue/` (§4.2). There is no staging directory:
the tool writes the real file, non-destructively.

`init` MUST create the four required memory files and the
gitignore/gitattributes entries below; everything else is added on demand.

**`.gitattributes` (required for multi-branch / worktree safety):**

```
.dejavue/timeline.jsonl merge=union
.dejavue/decisions.md   merge=union
```

Append-only files use `merge=union` so concurrent branches accumulate without
conflict. Overwritten files (`state.md`, `handoff.md`, `context.md`) follow
last-writer-wins and use git's normal text merge.

**`.gitignore` (rebuildable caches and local markers):**

```
.dejavue/fts.db
.dejavue/embeddings.jsonl
.dejavue/*.tmp
.dejavue/.first-use
.dejavue/ingested.lock
.dejavue/.locks/
```

---

## §3 — `context.md` format

`context.md` is the instruction-layer source of truth. It is plain Markdown with
an **optional minimal frontmatter** block and a set of recognized sections.

### 3.1 Frontmatter — `key: value`, no YAML dependency

If present, the file begins with a frontmatter block delimited by `---` lines.
The format is deliberately a **minimal `key: value` line grammar**, *not* YAML —
parsing it MUST NOT require a YAML library (Axiom 0). The same parser is shared
with reference-card frontmatter (§6.3).

```
---
project: dejavue
updated: 2026-06-05
dcp: DCP/1.0
---
```

Grammar:

- The block is the region between the first `---` line and the next `---` line,
  and only if the file's first non-empty line is `---`.
- Each line is `key: value`. The key is everything before the first `:`; the
  value is everything after, trimmed. Keys are case-sensitive.
- Blank lines and lines beginning with `#` are ignored.
- No nesting, no lists, no anchors, no multi-line values. A line that does not
  match `key: value` is ignored (forward-compatible).

Frontmatter is optional; a `context.md` with no frontmatter is valid.

### 3.2 Sections

The body is Markdown. The following second-level headings are **recognized
sections** with defined meaning; tools SHOULD use these names so generated
adapters are predictable. All are optional.

| Section | Contents |
|---|---|
| `## Operating Rules` | Behavioral rules for an agent working in this repo (do/don't, conventions, guardrails). |
| `## Build-Test` | How to build, run, and test — exact commands. |
| `## Architecture Map` | The shape of the codebase: key modules, entry points, where things live. |
| `## Memory` | A pointer to the memory layer (§1.2) — how to read the boot packet, where decisions live. |

Additional headings are permitted and carried through verbatim by export
(§4). Recognized sections give importers and exporters stable anchors; unknown
sections are preserved, never dropped.

---

## §4 — Adapter contract

`export` generates per-tool instruction files from `context.md`. The contract's
central guarantee is **non-destruction**: a hand-written instruction file is
never blindly overwritten.

### 4.1 The managed block

Generated content is written inside a **marker-delimited managed block**:

```
<!-- dejavue:begin DCP/1.0 src=context.md hash=<sha> -->
… generated content from context.md …
<!-- dejavue:end -->
```

- `DCP/1.0` — the protocol version that produced the block.
- `src=context.md` — the source artifact.
- `hash=<sha>` — a hash of the `context.md` content that produced this block.
  This feeds staleness detection: if `context.md`'s current hash differs from
  the hash recorded in a target's managed block, the adapter is **stale** and a
  `check` operation SHOULD report it ("context.md changed, adapters stale").

Everything **outside** the begin/end markers is hand-written content and MUST be
preserved untouched across regenerations. Everything **inside** is owned by DCP
and is replaced wholesale on each export.

### 4.2 Target registry

`export --target <name>` resolves a tool name to its canonical real file:

| Target | File written |
|---|---|
| `claude` | `CLAUDE.md` |
| `codex` | `AGENTS.md` |
| `gemini` | `GEMINI.md` |
| `copilot` | `.github/copilot-instructions.md` |
| `cursor` | `.cursor/rules` |
| `all` | every registered target above |

The registry is **configurable** via `.dejavue/config` (a tool MAY add or remap
targets). Targets are written at their real, canonical paths — there is no
staging directory.

### 4.3 Non-destructive write rules

For each resolved target file, `export` MUST behave as follows:

1. **Absent** (file does not exist) → **create** it containing just the managed
   block.
2. **Present and contains the markers** → **replace only the fenced region**
   between `<!-- dejavue:begin … -->` and `<!-- dejavue:end -->`, leaving all
   content outside the markers byte-for-byte intact. Update the `hash=`.
3. **Present but contains no markers** (a hand-written file) → **append** a
   managed block to the end of the file **and emit a warning** that an unmanaged
   file was extended. The pre-existing hand-written content is preserved above
   the block.
4. **`--replace` flag** → convert the **whole file** to a managed file: its
   entire content becomes a single managed block. This is the only mode that
   discards hand-written content, and it is opt-in.

A conforming tool MUST NOT overwrite a hand-written target file in the absence
of `--replace`. Case 3's append-plus-warn is the safety default that upholds
Axiom 0 and D2 (adapter safety).

---

## §5 — Import contract

`import <FILE>` seeds `context.md` from an existing instruction file
(`CLAUDE.md`, `AGENTS.md`, a hand-written rules file, …). It is the
bootstrap that lets a project adopt DCP without retyping its context.

- **Lossless seed.** The import MUST preserve the source content. Recognized
  sections (§3.2) SHOULD be mapped onto their canonical headings where the
  source structure makes the mapping unambiguous; any content that does not map
  cleanly MUST be carried through verbatim rather than dropped. Import never
  silently discards source text.
- **Provenance recorded.** The import MUST record where `context.md` was seeded
  from — at minimum the source path and a timestamp — as a memory-layer event
  (a timeline entry and/or `context.md` frontmatter, e.g.
  `imported-from: CLAUDE.md`). The provenance trail lets a later reader see that
  the instruction layer originated from a specific tool file.
- **Round-trip.** `import CLAUDE.md` → edit `context.md` → `export --target
  claude` MUST reproduce a managed block in `CLAUDE.md` without clobbering any
  hand-written content that lives outside the managed region.

---

## §6 — Memory format

The memory layer (§1.2) is DCP's required layer. Its format is the one
established by the reference implementation; DCP adopts it directly.

### 6.1 Timeline — `timeline.jsonl`

An append-only log, **one JSON object per line** (JSON Lines). Appends are
POSIX-atomic under `O_APPEND` for lines within `PIPE_BUF`. Common fields on
every event:

| Field | Type | Meaning |
|---|---|---|
| `ts` | string | ISO-8601 timestamp with offset. |
| `branch` | string | Git branch at write time. |
| `commit` | string | Short commit SHA at write time. |
| `agent` | string | Stable role name of the writing agent. |
| `event` | string | Event type (see below). |
| `summary` | string | Human-readable one-line summary (FTS-indexed). |

Recognized `event` types include `init`, `session_start`, `decision`,
`file_changed`, `note`, `state`, `handoff`. Event-specific fields are added
alongside the common ones. A `decision` event, for example, carries:

```json
{"ts": "2026-05-13T04:11:32-05:00", "branch": "master", "commit": "95f0c19",
 "agent": "sonnet", "event": "decision",
 "decision_title": "Use .dejavue/ directory naming",
 "decision_reason": "avoids collision with .joker/cache/ dirs",
 "summary": "Decision: Use .dejavue/ directory naming",
 "rejected_alternatives": [
   {"option": "Use .joker/", "reason": "collision with joker-mcp cache dirs"},
   {"option": "Use .memory/", "reason": "too generic, no project identity"}]}
```

**Patterns and failures are event types, not new files** (D3): a recurring
pattern or a recorded failure/dead-end is captured as a typed `decision`/`note`
event (sub-types such as `blocker`, `claim`, `question`, `experiment`,
`checkpoint`), not as a separate `patterns.md` / `failures.md`. This keeps the
file count minimal per Axiom 0.

### 6.2 Decisions — `decisions.md`

Append-only Markdown mirror of `decision` events, human-readable. Each entry
records the title, the reason, and the **rejected alternatives** (the
highest-value signal — the approach tried and dropped, with why). `merge=union`
keeps it conflict-free across branches.

### 6.3 State and handoff

- `state.md` — a single overwritten snapshot of current project state, with an
  `Updated:` timestamp.
- `handoff.md` — the latest handoff: a summary, the next steps, and boot
  instructions for the next session. Overwritten each handoff.

Both are last-writer-wins on merge.

### 6.4 References and glossary

`references/` holds optional hand-written reference cards. Cards MAY carry the
same minimal `key: value` frontmatter as `context.md` (§3.1) — e.g.
`type: api` — so they can be listed/filtered by type. `references/glossary.md`
is the conventional home for a project glossary, surfaced in the boot packet.

---

## §7 — Versioning

- **Version token.** This document specifies **DCP/1.0**. The token appears in
  the managed-block marker (`<!-- dejavue:begin DCP/1.0 … -->`) so a generated
  file always declares the protocol version that produced it.
- **Format as contract.** The on-disk layout (§2) and the memory format (§6) are
  the interoperability surface. Any tool that reads and writes them conforms;
  the reference CLI is one such tool, not a requirement.
- **Backward-compatible, additive evolution.** Within a major version, changes
  MUST be additive: new optional fields, new optional files, new recognized
  sections. Readers MUST ignore unrecognized fields, sections, and frontmatter
  keys rather than erroring (forward-compatibility). Removing or repurposing an
  existing field, or making a previously optional layer mandatory, is a
  breaking change and requires a new major version (`DCP/2.0`). A change that
  would violate Axiom 0 is never permitted, in any version.

---

## §8 — Conformance

A conforming DCP/1.0 tool satisfies the following. **Axiom 0 is judged first**:
a tool failing any MUST in §8.1 is non-conformant regardless of §8.2–§8.4.

### 8.1 Axiom 0 (MUST — judged first)

- **MUST** be usable immediately after `init` with no configuration and no files
  beyond what `init` creates.
- **MUST NOT** require any layer above the base memory log; `context.md`,
  adapters, glossary, and frontmatter are all optional.
- **MUST NOT** introduce any mandated runtime dependency for any feature.
- **MUST** keep the base loop (`init → start → decision → state → handoff`)
  functional and frozen.

### 8.2 Memory layer (MUST)

- **MUST** create and maintain `timeline.jsonl`, `decisions.md`, `state.md`,
  `handoff.md` at the canonical paths (§2).
- **MUST** write `timeline.jsonl` as append-only JSON Lines with the common
  fields (§6.1).
- **MUST** install the `merge=union` `.gitattributes` entries (§2) on `init`.
- **MUST** ignore unrecognized event fields rather than erroring.

### 8.3 Adapter + import (SHOULD, where implemented)

- A tool that generates adapters **MUST** use the managed-block marker (§4.1)
  with `src` and `hash`, and **MUST** follow the non-destructive write rules
  (§4.3): absent→create, marked→replace-region, unmarked→append+warn,
  `--replace`→convert.
- A tool that generates adapters **MUST NOT** overwrite a hand-written target
  file without explicit `--replace`.
- A tool that imports **MUST** seed `context.md` losslessly and **MUST** record
  provenance (§5).
- A tool **SHOULD** support staleness detection by comparing `context.md`'s hash
  with the `hash=` recorded in each target's managed block.

### 8.4 Format metadata (SHOULD)

- A tool that reads `context.md`/reference frontmatter **SHOULD** use the minimal
  `key: value` grammar (§3.1) and **MUST NOT** require a YAML library to do so.
- A tool **SHOULD** preserve unrecognized sections and frontmatter keys verbatim.

---

## Appendix — Reference implementation

[dejavue](https://github.com/nixpt/dejavue) is the DCP/1.0 reference
implementation: a single Python 3 file, standard library only, no install step.
It realizes the memory layer (the base loop and `since`/`recall`/`context`),
the instruction layer (`context.md` + `init` scaffold), and the adapter layer
(`import` + `export --target`). Where this spec and the reference implementation
disagree, the spec is the contract and the implementation is the bug.

# DejaVue Maturation → DCP (DejaVue Context Protocol)

**Session:** 241 (2026-06-05) · **Status:** ✅ DESIGN RATIFIED — ready to dispatch

## Ratified decisions (internal session, locked)

| # | Decision | Locked outcome |
|---|----------|----------------|
| Axiom 0 | Zero-ceremony | Hard invariant. Base loop frozen; all DCP layers optional/additive; **no new runtime dep ever**. |
| D1 | Positioning | **Full citable standard** — `docs/dcp-spec.md`, dejavue = reference impl, Foundry/OCPL. |
| D2 | Adapter safety | **Non-destructive.** Unmarked hand-written target → **append managed block + warn**; `--replace` converts whole file; marked target → replace only the fenced region. |
| D3 | New files | One new artifact (`context.md`) + optional `references/glossary.md`. patterns/failures = event types. |
| D4 | ONNX embedder | **Dropped** (violates Axiom 0). |
| D5 | v1.4 subset | Ship `promote`/`init --wizard`/reference-frontmatter/`diff --format patch` (all stdlib). |
| Version | Release line | **v2.0.0** — DCP/1.0 spec ships with dejavue v2.0. Format stays backward-compatible (additive). |
| Meta fmt | context.md metadata | Minimal `key: value` frontmatter (no YAML dep); shared parser with reference-frontmatter. |
| Adapter loc | Output target | Write the tool's **real file** (CLAUDE.md, AGENTS.md, .github/copilot-instructions.md, …) — no staging dir. |
| Targets | Registry | claude→CLAUDE.md · codex→AGENTS.md · gemini→GEMINI.md · copilot→.github/copilot-instructions.md · cursor→.cursor/rules · `all`; configurable in `.dejavue/config`. |

Managed-block marker: `<!-- dejavue:begin DCP/1.0 src=context.md hash=<sha> -->` … `<!-- dejavue:end -->`.
The `hash` feeds `check`'s staleness detection ("context.md changed, adapters stale").

---

**Origin:** maintainer "dejavue maturation"; vision brainstorm `local workspace/private design notes`;
scope picks = hygiene/reconcile + v1.4 features + productization/release.

---

## The reframe

DejaVue today is *per-repo agent memory* (the **why** of a codebase: decisions,
constraints, dead ends). The maintainer's vision matures it into **DCP — the
DejaVue Context Protocol**: a portable context interchange layer where
`.dejavue/` is the **single source of truth** and `AGENTS.md` / `CLAUDE.md` /
`GEMINI.md` / Copilot rules become **generated adapter targets**.

Three layers (maintainer's framing):
1. **Instruction layer** — what the agent should *do* (style, commands, rules, arch map) → new `context.md`
2. **Memory layer** — what the agent should *remember* (decisions, patterns, failures, glossary) → dejavue already has this
3. **Adapter layer** — generated per-tool files (`export --target {claude,codex,gemini,copilot,all}`) + `import` to bootstrap from existing files

> "DejaVue should become the source of truth, not another competing standard …
> AGENTS.md and CLAUDE.md become exported compatibility targets, not the source."

This positions dejavue as infrastructure (a *protocol*), aligned with the
OpenKO Foundry registration already in place (OCPL, `foundry.toml`, STEWARDSHIP.md).

---

## Current state (verified internal session)

- **Mature core:** v1.3.0, 36 commands, **100/100 tests green**, single-file stdlib-only.
- **Thin adoption:** only **5 repos** have `.dejavue/` (dejavue, external project, sample repo, sample repo, private source workspace) of ~30 peers. *(Adoption was NOT picked this session — noted, not in scope.)*
- **Roadmap drift:** "v1.4 candidates" lists `diff` / `timeline` / `check --fix` as future — all three **already shipped in v1.3.0**.
- **Dead branch:** `origin/agent/external agent/dejavue-v0.3` is 8 commits *behind* master; its headline "split dejavue.py into modules — single-file invariant relaxed" is the **opposite** of master's deliberate single-file decision. Prune, don't merge.
- **No `context.md`** yet; `export` is `--format json|md` (snapshot), not `--target` (adapter).

---

## Axiom 0 — Zero-ceremony conformance  *(RATIFIED internal session)*

The hard invariant every other decision answers to. A conforming DCP tool MUST
be usable with no configuration and no files beyond what `init` creates. Every
layer above the base memory log (`context.md`, adapters, glossary, frontmatter)
is **optional and additive**. The base loop (`init → start → decision → state →
handoff`) is **frozen**. **No new runtime dependency may ever be introduced.**
If a feature can only work via a new dep or a mandatory file, it is wrong by
definition (this is how ONNX was caught — D4).

## Ratified direction (internal session)
- **DCP as a full, citable standard** — write `docs/dcp-spec.md`; dejavue is the reference impl; positioned for OpenKO Foundry (OCPL).
- **Refine design, then dispatch** — no DCP code dispatched until the design is ratified. Hygiene (Wave A) runs in parallel (risk-free).

## Load-bearing design decisions (need ratification)

### D1 — Naming: adopt "DCP" as the umbrella, keep `dejavue` as the tool
Brainstorm floated DCP / DCS / DMF / MCPX / XCP; recommends **DejaVue Context
Protocol (DCP)**. **Recommendation:** adopt **DCP** as the name of the
context-standard *capability* and spec; do **not** rename the binary or break
any command contract. New commands live under existing verbs (`export --target`,
`import`) — no `dejavue dcp` namespace churn. *Reversible (it's framing + a spec doc).*

### D2 — Adapter direction: **import-first, non-destructive** (the load-bearing risk)
The workspace has dozens of hand-written `CLAUDE.md`/`AGENTS.md` (e.g.
`projects/CLAUDE.md` — rich, hand-maintained). Blind `export --target claude`
would clobber them. **Recommendation:**
- `dejavue import <FILE>` seeds `.dejavue/context.md` from an existing instruction file (bootstrap).
- `export --target` writes into a **marker-delimited managed block** (`<!-- dejavue:begin -->…<!-- dejavue:end -->`) inside the target file, preserving any hand-written content outside the block; OR stages to `.dejavue/adapters/` and only writes the root file under explicit `--write`/`--force` with a shown diff.
- **Never** blind-overwrite a hand-written root file. This keeps the zero-ceremony / non-destructive contract intact.

### D3 — Memory layer: minimize new files
Brainstorm proposes `memory/{decisions,patterns,failures,glossary}.md`.
dejavue already has `decisions.md` + typed events (`--type
blocker/claim/question/experiment/checkpoint`, note sub-types). **Recommendation:**
add **`context.md`** (instruction layer) as the one new first-class artifact;
represent **patterns/failures** as decision/note *types* surfaced in `context`,
and **glossary** as a reference card (`references/glossary.md`). Avoids file
sprawl (contract: no multi-file rewrite of the model).

### D4 — Drop ONNX embedder from this wave (contract conflict)
v1.4 "local ONNX embedder tier" requires `onnxruntime` — **violates** the
stdlib-only / "no new runtime dependencies" invariant (it's even under
ROADMAP "Out of scope"). **Recommendation:** **drop** it (or defer as an
optional out-of-process shellout, never an import). Keeps the contract clean.

### D5 — v1.4 subset that ships: stdlib-safe only
**Ship:** `promote --to planning` (graduate a `.dejavue/` without losing history),
`init --wizard` (3-question seed), reference frontmatter (`reference list --type`).
**Drop:** ONNX (D4). All chosen items are pure-stdlib.

---

## Waves

Single-file tool ⇒ parallel horses on `dejavue.py` **will** conflict. Sequence
the code-touching work; parallelize only doc/spec work (separate files).

### Wave A — Hygiene / reconcile  *(design lead-direct, now — no dispatch)*
1. Prune `origin/agent/external agent/dejavue-v0.3` (dead, behind, contra single-file).
2. Reconcile `ROADMAP.md`: move `diff`/`timeline`/`check --fix` from "v1.4 candidates" → Shipped (v1.3.0); restate real remaining candidates.
3. Quick dogfood/consistency check.
**Done:** branch gone, ROADMAP self-consistent, committed + pushed.

### Wave B — DCP core  *(dispatch: claude, the centerpiece — gated on D1–D4 ratified)*
- `context.md` instruction-layer artifact + `init` scaffolds it + `context` surfaces it.
- `dejavue import <FILE>` → seed `context.md` from AGENTS.md/CLAUDE.md.
- `dejavue export --target {claude,codex,gemini,copilot,all}` → generate adapter files, **non-destructive (D2)**.
- `references/glossary.md` as a glossary reference card.
- Tests for every new path; keep stdlib-only; 100% green gate.
**Done:** round-trip `import CLAUDE.md` → edit `context.md` → `export --target claude` reproduces a managed block without clobbering hand-written content; tests green.

### Wave C — stdlib-safe v1.4 features  *(dispatch: sequential after B — same file)*
`promote --to planning`, `init --wizard`, reference frontmatter. **Done:** features + tests, green.

### Wave D — Productization + DCP spec  *(dispatch: parallel-OK, separate files)*
- `docs/dcp-spec.md` — the DCP standard (the three layers, adapter format, managed-block contract, `.dejavue/` layout).
- README/STEWARDSHIP positioning as "portable context + memory + adapter bridge."
- CHANGELOG + ROADMAP for the DCP release (v1.4 or v2.0 — maintainer's call on version line).
**Done:** spec doc + positioning committed; no `dejavue.py` conflict with B/C.

---

## Out of scope (this session)
- Adoption rollout across the ~30 repos (not picked; separate session).
- ONNX embedder (D4).
- Renaming the binary / breaking command contract / multi-file split of `dejavue.py`.
- `memory crate` Rust consolidation (orchestration-side, per existing ROADMAP out-of-scope).

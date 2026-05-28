---
name: dejavue
description: |
  The dejavue command surface — entry point for dejavue, the repo-local
  agent memory tool (an event log of the *why* that git can't capture:
  architectural decisions, non-obvious constraints, dead ends, handoffs).
  Use this skill when you land in a repo with a `.dejavue/` directory,
  when a task prompt mentions dejavue or "boot packet", or when you're
  about to make an architectural decision worth keeping. It names the
  CLI command surface and routes to dejavue-workflow for the full protocol.
---

# dejavue

Dejavue is repo-local agent memory — to project *why* what `.git/` is to
project *history*. It captures architectural decisions, non-obvious
constraints, dead ends explored, and handoffs in a portable format (JSONL +
markdown + SQLite FTS5), driven by a single-file Python CLI.

This skill is the **index** for dejavue: it names the command surface and
points at the full protocol; it doesn't restate it.

## Why this exists

Dejavue has a small but real command surface, and the recurring failure
mode is not knowing it's available — landing in a `.dejavue/`-enabled repo
and re-deriving context from git log + stale READMEs instead of running one
`dejavue context`. This skill is the "this repo has memory — use it"
reminder and the command quick-reference.

## The command surface

| Command | What |
|---|---|
| `dejavue context` | Boot packet — handoff + state + decisions + references + last 10 events + staleness warnings. Run on arrival. |
| `dejavue status` | One-liner health: agent, event count, last decision, open next-steps. |
| `dejavue start --agent <n> --goal <g>` | Mark a session start (enables `since --agent`) |
| `dejavue decision "<title>" --reason <r> --rejected "<alt>: <why>"` | Capture an architectural decision + rejected alternatives |
| `dejavue state --summary <s>` | Overwrite state.md — "what's true right now" |
| `dejavue handoff --summary <s> --next <n>` | Structured next-session brief |
| `dejavue note "<text>" --tag <t>` | Lightweight timestamped note (between annotate and decision) |
| `dejavue annotate {state,handoff,decisions} "<note>"` | Append timestamped note to a doc without rewriting it |
| `dejavue since <date\|commit\|--agent>` | Temporal delta — "what changed since…" |
| `dejavue log [--since] [--agent] [--type] [--oneline]` | Formatted timeline view with filters |
| `dejavue blame <file>` | "Why does this file exist?" — decisions + events mentioning the path |
| `dejavue recall "<query>"` | FTS5 keyword (or `--semantic` cosine) search across all artifacts |
| `dejavue get {state,handoff,decisions,...}` | Direct fetch when you know what you want |
| `dejavue worthiness` | The capture/skip gate — print when unsure what to record |
| `dejavue version` | Print the installed version |

If the CLI isn't on PATH but the repo has a copy at `dejavue.py`:

```bash
ln -sf "$(pwd)/dejavue.py" ~/.local/bin/dejavue
```

The CLI is stdlib-only Python 3 — no `pip install` needed.

## For the full protocol

[[dejavue-workflow]] is the *how*: boot-packet discipline, the capture
lifecycle, the worthiness gate, `merge=union` for parallel branches, repo
state ownership (what to track vs ignore), and when NOT to `dejavue init`.
Load it when actually working with dejavue — this index is just the map.

## What this skill does NOT cover

The how-to (that's [[dejavue-workflow]]) and the dejavue tool's own
internals / roadmap (canonical source: the project's `README.md`,
`docs/`, and `CHANGELOG.md`).

## Cross-references

- Skill: [[dejavue-workflow]] (the full protocol)
- Tooling: `dejavue` CLI, source at `dejavue.py` in the project root
- Project docs: `README.md`, `docs/`, `CHANGELOG.md`, `LICENSE`

## License

This skill ships under the same license as the dejavue project
(see `LICENSE` in the project root).

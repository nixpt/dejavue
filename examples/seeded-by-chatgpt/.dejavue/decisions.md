# Decisions

## Decision 001 — Use `.memory-service/` instead of a single `.memory-service` file

Reason:
A directory allows multiple memory artifacts: timeline, decisions, handoff, diffs, sessions, and current state.

Consequence:
The memory system becomes extensible and easier for agents to consume.

---

## Decision 002 — Git remains the source of truth

Reason:
Deja Vue should not become another version control system.

Consequence:
Deja Vue records meaning and intent around git changes, while git records actual diffs.

---

## Decision 003 — Use append-only JSONL for timeline

Reason:
JSONL is simple, merge-friendly, streamable, and easy for agents to append to.

Consequence:
`.dejavue/timeline.jsonl` becomes the canonical event stream.

---

## Decision 004 — Capture intent, not raw thinking

Reason:
Agent private reasoning should not be logged. The project only needs useful engineering memory.

Consequence:
Deja Vue captures:
- what changed
- why it changed
- what decisions were made
- what remains unfinished

It does not capture:
- every thought
- every token
- every command

# `.jagent/` protocol — the lean repo lifecycle

Repo-scoped version of the fleet `agent-lifecycle` skill.

1. **OBSERVE** — `dejavue context`; `.jagent/planning/{TASKS,STATE}.md`;
   `.jagent/sessions/HANDOFF.md`; `RULES.md`; `.jagent/sync/` if present.
2. **CLAIM** — one worktree + branch under `.jagent/worktrees/<agent>/`; never
   the shared checkout or main. Claim overlapping work in the sync channel.
3. **EXECUTE** — scoped edits; capture findings as they happen; commit+push at
   each task boundary; update `.jagent/planning/` as you go.
4. **HANDOFF** — write `.jagent/sessions/HANDOFF.md` (overwritten, current state);
   write an immutable `.jagent/sessions/<date>-<id>.md` + append to
   `INDEX.jsonl` via `jagent-session`; record durable decisions in `.dejavue/`.

Where things go: durable decision → `.dejavue/`; task/ticket → `.jagent/planning/`;
"what happened here" → `.jagent/sessions/`; clone scratch → `.jagent/local/` or `tmp/`.

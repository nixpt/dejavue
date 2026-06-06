
## `.joker/current_state.md`

```md
# Current State

Deja Vue is being designed as a Joker MCP extension that automatically writes project-local memory into `.joker/`.

The current model is:

- `.joker/timeline.jsonl` is the append-only machine-readable event log.
- `.joker/deja-vue.md` is the human-readable memory.
- `.joker/current_state.md` summarizes the latest project understanding.
- `.joker/decisions.md` stores architectural decisions.
- `.joker/handoff.md` tells the next agent what to read first.

The system should capture relevant git changes, not every file save.

It should focus on:
- changed files
- commit hashes
- branch names
- summaries
- decisions
- blockers
- unfinished work
- future instructions

Deja Vue is best understood as:

Git = mechanical history  
Deja Vue = cognitive history  
Joker = coordination layer

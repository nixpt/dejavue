
## `.memory-service/current_state.md`

```md
# Current State

Deja Vue is being designed as a existing memory stack MCP extension that automatically writes project-local memory into `.memory-service/`.

The current model is:

- `.memory-service/timeline.jsonl` is the append-only machine-readable event log.
- `.memory-service/deja-vue.md` is the human-readable memory.
- `.memory-service/current_state.md` summarizes the latest project understanding.
- `.memory-service/decisions.md` stores architectural decisions.
- `.memory-service/handoff.md` tells the next agent what to read first.

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
existing memory stack = coordination layer

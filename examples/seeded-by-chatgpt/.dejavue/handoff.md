# Handoff

Read this first.

Deja Vue is a proposed existing memory stack MCP extension that creates repo-local memory for coding agents.

The goal is to solve agent amnesia.

Future agents should understand:

1. Deja Vue does not replace git.
2. Git captures file and commit history.
3. Deja Vue captures the meaning around changes.
4. `.memory-service/timeline.jsonl` should be append-only.
5. `.memory-service/deja-vue.md` should be readable by humans.
6. `.memory-service/current_state.md` should summarize the latest project state.
7. `.memory-service/decisions.md` should preserve architectural decisions.
8. Deja Vue should capture only relevant changes, not noisy logs.

Next implementation steps:
- Define the JSONL event schema.
- Create `dejavue init`.
- Create `dejavue start-session`.
- Add git diff summarization.
- Add `dejavue handoff`.
- Add existing memory stack MCP tools.
- Add agent boot protocol: read `.memory-service/handoff.md` before working.

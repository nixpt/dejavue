# Deja Vue Memory

## Project
Name: Deja Vue  
Parent System: existing memory stack MCP  
Purpose: Repo-local déjà vu memory for coding agents.

## Core Idea
Coding agents like Codex, Claude, and other MCP-connected workers often complete tasks and lose context afterward. Existing traces such as `.claude`, `.agents`, git history, and chat logs are fragmented.

Deja Vue creates a structured `.memory-service/` memory layer that records relevant project changes, decisions, context, and handoff notes so future agents can instantly understand the project as if they had worked on it before.

## Concept
Git captures mechanical history.

Deja Vue captures cognitive history.

Git says:
- what files changed
- what lines changed
- when commits happened

Deja Vue says:
- why changes happened
- what the agent intended
- what decisions were made
- what remains unfinished
- what future agents should know

## Proposed Layout

```txt
.memory-service/
  deja-vue.md
  timeline.jsonl
  current_state.md
  decisions.md
  handoff.md
  agent_sessions/
  diffs/

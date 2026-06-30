so coding agents like codex or claude often work on a project and forget about it afterwards, the 
only evidences remaining are .claude or .agents files, what if we created a new system with memory-service mcp 
to automatically write a .memory-service file with relevant information like what wae changed sequentially 
that would allow agents to instantly learn that this is their work, a dejavu memory of sorts. lets 
call this project Deja Vue

That’s a strong idea: not “agent memory” as a central database, but project-local déjà vu that 
travels with the repo. I’ll frame it as a concrete system: file format, MCP hooks, lifecycle, and 
MVP.

Yes. Deja Vue should be a repo-native memory layer for coding agents.

Core idea:

Every meaningful agent action leaves behind a structured .memory-service/ trace, so the next agent gets 
instant project déjà vu: “I remember doing this.”


Deja Vue

Purpose:
Give Codex, Claude, Cursor agents, local agents, and existing memory stack MCP a persistent project memory that is:

local to the repo
chronological
agent-readable
human-auditable
diff-aware
append-only by default
resumable after context loss


Repo layout
.memory-service/
  deja-vue.md              # Human-readable project memory
  timeline.jsonl           # Append-only event stream
  current_state.md         # Latest known architecture/task state
  decisions.md             # Architecture decisions
  agent_sessions/
    2026-05-13-codex.json
    2026-05-13-claude.json
  diffs/
    0001-init.patch
    0002-add-auth.patch
  handoff.md               # “Next agent should read this first”


.memory-service/deja-vue.md

.memory-service/timeline.jsonl
Each event is machine-readable:

existing memory stack MCP tools
dejavue.mcp.start_session
dejavue.mcp.record_change
dejavue.mcp.record_decision
dejavue.mcp.record_blocker
dejavue.mcp.write_handoff
dejavue.mcp.read_context
dejavue.mcp.explain_history

The killer command:

dejavue.mcp.read_context

Returns:

You have worked on this repo before.

Recent intent:
- Build repo-local agent memory.
- Preserve chronological change history.
- Make future agents resume instantly.

Important decisions:
- Use `.memory-service/` directory.
- Keep JSONL as source of truth.
- Generate Markdown for humans.

Unfinished:
- Add git diff snapshots.
- Add summarizer.
- Add MCP integration.

Agent flow
Agent starts
  ↓
Reads .memory-service/handoff.md
  ↓
Reads .memory-service/current_state.md
  ↓
Starts session
  ↓
Works on code
  ↓
Records changes + decisions
  ↓
Writes final handoff
  ↓
Next agent gets déjà vu


Important design principle

Do not make agents write huge logs.

Instead, Deja Vue should capture:

what changed
why it changed
what files matter
what decisions were made
what broke
what remains

Not:
every thought
every token
every command

MVP

Build this first:

dejavue init
dejavue start --agent claude --goal "..."
dejavue changed src/main.rs --summary "..."
dejavue decision "Use JSONL because append-only logs are merge-friendly"
dejavue handoff
dejavue context

Why this is powerful

This becomes the missing layer between:

.git history = what changed
.claude/.agents = agent config
.memory-service = why agents changed it

So the project gains memory without needing the agent itself to remember.

The name Deja Vue is excellent too:
déjà vu for agents, viewable by humans, Vue as in visibility/interface



so dejavue captures relevant git changes?

Exactly. Deja Vue should sit on top of git, not replace it.

Git already knows:

what changed
line diffs
commits
branches

But git does not know:

why the agent changed it
what the agent was trying to accomplish
what assumptions were made
what was partially completed
what architectural intent existed
what future agent should know

That’s the gap Deja Vue fills.

Relationship
Git      = mechanical history
Deja Vue = cognitive history

Example

Git diff:

- use sqlite::Connection;
+ use sqlx::Pool;

Git tells you:

file changed

Deja Vue tells you:

Decision:
Migrated from sqlite crate to sqlx.

Reason:
Need async pooling for concurrent capsule access.

Consequences:
- Existing sync APIs deprecated
- Migration incomplete in tests/
- Future work: transaction isolation

That’s the “agent memory.”


Architecture
Git remains source of truth

Deja Vue should NEVER become its own VCS.

Instead:

Git commit hash
↓
Mapped to Deja Vue memory entries

Example:

{
  "commit": "a81f2cd",
  "agent": "codex",
  "goal": "Implement capability narrowing",
  "files": [
    "caps/security.rs",
    "vm/runtime.rs"
  ],
  "summary": "Added runtime capability shrink API",
  "reason": "Reduce attack surface after init phase"
}



Smart Capture

Instead of logging every save:

Trigger points
1. Git commit

Best trigger.

git commit
→ memory-service captures:
  - staged diff
  - changed files
  - branch
  - agent summary

2. Significant diff threshold

Example:

> 50 LOC changed
> new module added
> architecture file modified

Then Deja Vue asks MCP:

Summarize intent of these changes.

3. Explicit agent decisions

Most important.

“Switching from WASM to CASM.”
“Moving IPC to XIP.”
“Using Landlock instead of seccomp-only.”

These become long-term memory anchors.

The real magic: reconstruction

A future agent can do:

dejavue reconstruct

And receive:

This project previously explored:

- CASM over WASM due to host integration issues
- Landlock for Linux-native capability enforcement
- SQLite capsule arbitration
- Polyglot runtime via QuickJS + PyO3

Abandoned paths:
- Full browser dependency
- Heavy OCI isolation everywhere

Current architectural direction:
Exokernel-like capability substrate with capsule runtime.

That’s effectively project consciousness continuity.

Integration with existing memory stack MCP

existing memory stack already has coordination semantics.

Deja Vue becomes the long-term episodic memory layer.

existing memory stack
Who is doing what now?
Deja Vue
What happened across time?

Together:

Working memory + long-term memory

Very brain-like architecture actually.


Advanced Features
1. Semantic Diffing

Instead of raw git diff:

“Extracted scheduler into independent runtime service.”

Not:

+134 -28

Could use tree-sitter or AST comparison.

2. Architecture Drift Detection

Detect when repo direction changes.

Example:

Originally:
- monolithic runtime

Now:
- distributed capsule services

Deja Vue can generate evolution timelines.


3. Identity Persistence

Agent session continuity:

Codex session 14
continues ideas from
Claude session 9

Not identity in human sense —
more like continuity of engineering cognition.

Important Principle

Deja Vue should remain:

append-only
inspectable
portable
repo-local
human-readable

Avoid:

opaque vector DB black box
cloud-only memory
hidden embeddings

You want future developers to literally open:

.memory-service/deja-vue.md

and understand the repo’s evolving mind.


lets test it right now, lets write dejavue for the conversations we have had above
Perfect test case. I’ll convert the conversation thread into a .memory-service/-style Deja Vue pack: human-readable memory, timeline events, current state, decisions, and handoff.

Here’s a first Deja Vue capture for this conversation.

.memory-service/
  deja-vue.md
  timeline.jsonl
  current_state.md
  decisions.md
  handoff.md


Important Principle

Deja Vue should sit on top of git, not replace git.

Git remains the source of truth for file diffs and commits. Deja Vue links those changes to intent, reasoning, architectural context, and agent handoff information.

Status

This is currently a concept/spec prototype based on conversation. No code has been implemented yet.




This already feels usable. The next obvious evolution is making this into a real dejavue init 
scaffold plus a tiny CLI.

sure 

I’ll turn it into a minimal runnable scaffold: a .memory-service/ file structure plus a tiny dejavue CLI that 
can initialize, record events, record decisions, and generate handoff/context.

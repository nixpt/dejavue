# Thin DejaVue Wrapper

This is the smallest useful adapter shape for people who want structured access
to DejaVue without pulling DejaVue into a larger gateway or MCP stack.

## Goal

Expose a few DejaVue commands through a tiny wrapper that:
- keeps `dejavue.py` as the only source of truth
- shells out to the CLI instead of reimplementing memory logic
- stays transport-agnostic so users can wire it to MCP, stdio, JSON-RPC, or a
  local script runner
- remains stateless between calls

## Non-goals

- no broker
- no provider routing
- no message queue
- no database
- no config synchronization layer
- no mandatory MCP dependency

## Recommended tool surface

Start with read-heavy commands:
- `context`
- `since`
- `recall`
- `state`
- `handoff`
- `blame`

Add writes only if a user needs them:
- `decision`
- `start`
- `changed`

## Adapter contract

The wrapper should accept three inputs:

```text
repo_root   absolute path to the target git repo
dejavue_bin absolute path to the dejavue executable
agent_name  stable role name, e.g. claude, reviewer, coordinator
```

And expose one operation:

```text
call(tool_name, argv_json) -> stdout/stderr/exit_code
```

The wrapper does not interpret DejaVue data. It just launches:

```bash
cd "$repo_root" && "$dejavue_bin" <tool_name> ...
```

## Minimal manifest

The runnable example ships a machine-readable manifest at
[`examples/thin-wrapper/mcp-tools.json`](/workspace/projects/dejavue/examples/thin-wrapper/mcp-tools.json).
Users can copy or adapt that file without changing the wrapper code.

A manifest can stay as simple as this:

```json
{
  "name": "dejavue-wrapper",
  "tools": [
    "context",
    "since",
    "recall",
    "state",
    "handoff",
    "blame",
    "decision",
    "start",
    "changed"
  ]
}
```

## Transport examples

- MCP: map each tool to a tool definition and call the wrapper process.
- stdio: read JSON lines, emit JSON lines.
- shell: `dejavue-wrapper call context`.

## Behavior rules

- Return raw stdout from DejaVue when possible.
- Preserve exit codes.
- Pass through stderr unchanged.
- Do not cache.
- Do not normalize output formats unless the command already supports a
  machine-readable mode.
- Keep the wrapper small enough that users can replace it with a script.

## Runnable example

See [`examples/thin-wrapper/dejavue-wrapper.py`](/workspace/projects/dejavue/examples/thin-wrapper/dejavue-wrapper.py)
for a minimal executable that implements the contract above.

That is enough for a user to wrap DejaVue in their own transport without
turning DejaVue itself into a server.

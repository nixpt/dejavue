# Thin Wrapper Example

This directory shows the smallest useful DejaVue adapter shape.

It is intentionally not a full MCP server. The point is to keep the wrapper
replaceable:
- shell out to `dejavue`
- keep the repo path explicit
- keep the agent identity stable
- do not store state

See `docs/08-thin-wrapper.md` for the contract.
The runnable example is `dejavue-wrapper.py`.
The machine-readable manifest lives in `mcp-tools.json`.

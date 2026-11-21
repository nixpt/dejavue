# dejavue

Portable, repo-local context and memory for coding agents: a single Python 3
file on the standard library, the reference implementation of DCP (the DejaVue
Context Protocol). Read first: `README.md`, `docs/dcp-spec.md`.

Axiom 0: the base memory log is the only required layer; every other layer is
optional and additive. Keep it one file, stdlib only.

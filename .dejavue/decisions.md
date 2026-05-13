# Decisions


## 2026-05-13T04:11:32-05:00 — Use .dejavue/ directory naming

Reason:
avoids collision with optional MCP memory service .memory-service/cache/ directories (design_perspective §10)

Rejected alternatives:
- **Use .memory-service/**: collision with existing optional MCP memory service cache dirs
- **Use .memory/**: too generic, no project identity


## 2026-05-13T04:11:37-05:00 — FTS5 for v0.1 recall, not embeddings

Reason:
pipefish embedder offline; stdlib sqlite FTS5 ships on all modern Linux; zero install

Rejected alternatives:
- **external_search_knowledge**: requires MCP dep, violates zero-ceremony principle
- **external embeddings**: pipefish offline this session, adds infra dep


## 2026-05-13T04:11:41-05:00 — Single file, stdlib only

Reason:
drop-in anywhere; no venv, no pip; consistent with v0.1 zero-ceremony principle

Rejected alternatives:
- **Split into modules**: defeats single-file portability goal
- **Add pyyaml/requests**: external deps violate 5-second setup guarantee


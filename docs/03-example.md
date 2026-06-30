chmod +x dejavue.py

./dejavue.py init --agent chatgpt

./dejavue.py start \
  --agent codex \
  --goal "Implement existing memory stack MCP Deja Vue memory writer"

./dejavue.py changed src/main.rs \
  --agent codex \
  --summary "Added timeline writer for append-only project memory"

./dejavue.py decision "Use JSONL timeline" \
  --agent codex \
  --reason "JSONL is simple, append-only, streamable, and merge-friendly"

./dejavue.py state \
  --agent codex \
  --summary "MVP Deja Vue CLI exists and can initialize memory, record changes, decisions, state, and handoff."

./dejavue.py handoff \
  --agent codex \
  --summary "Basic repo-local memory scaffold implemented." \
  --next "Add git diff summarization and existing memory stack MCP bindings."

./dejavue.py context

# `.jagent/agents/` — portable runner config

Committed, portable per-runner config. Runner-native dirs (`.claude/`, `.codex/`,
`.opencode/`, `.cursor/`) are LOCAL gitignored runtime.

Wiring: env-redirect (`CLAUDE_CONFIG_DIR`/`CODEX_HOME`/`OPENCODE_CONFIG_DIR`)
→ otherwise symlink → **never copy**.

Committed-vs-local is per file via `.manifest` (**default local**). No absolute
path, secret, or session state may be committed here.

Ops instructions live here; the codebase/architecture instructions are
`.dejavue/context.md` (generated into `CLAUDE.md`/`AGENTS.md`) — do not duplicate.

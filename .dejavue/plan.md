# Plan

Captured by agents as they work. An unchecked box is an open item;
nobody has committed to doing it, only to not losing it.

- [ ] **issue** — init is not idempotent against a PARTIAL .gitattributes: if the file was written by an older dejavue (only timeline/decisions entries), init appends a whole new block instead of just the missing lines, duplicating .dejavue/timeline.jsonl and .dejavue/decisions.md merge=union. Reproduced session: 2 union lines -> 6, with 2 dupes. Harmless to git (last match wins) but it silently dirties an adopter's worktree, which is how it was found.  _(agent, 2026-07-14)_
- [ ] **opportunity** — dejavue has ZERO crush-symbols integration (grep: 0 refs). 'dejavue explain <file>' composes git + decisions + rejected alternatives — the WHY — but cannot answer 'who calls this' or 'what breaks if I change it', which crush-symbols already indexes (75k+ symbols / 300k+ edges in the shared .jagent/symbols.db that joker-mcp also uses). Wiring impact/callers into 'explain' would make it answer why AND blast-radius in one shot. Note the correctness constraint learned session: the index is a snapshot — it must refuse to answer when stale OR mid-rebuild, since a partial index reports 'no callers' for symbols it simply hasn't reached, which is worse than silence.  _(agent, 2026-07-14)_

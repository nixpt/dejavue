# Plan

Captured by agents as they work. An unchecked box is an open item;
nobody has committed to doing it, only to not losing it.

- [ ] **issue** — init is not idempotent against a PARTIAL .gitattributes: if the file was written by an older dejavue (only timeline/decisions entries), init appends a whole new block instead of just the missing lines, duplicating .dejavue/timeline.jsonl and .dejavue/decisions.md merge=union. Reproduced s379: 2 union lines -> 6, with 2 dupes. Harmless to git (last match wins) but it silently dirties an adopter's worktree, which is how it was found.  _(kai, 2026-07-14)_

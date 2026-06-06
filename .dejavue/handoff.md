# Handoff

Updated: 2026-06-06T07:49:46-05:00

## Summary
v2.0.2 correctness pass shipped + released. Fixed: note-commit --trailer (orphaned note / wrong-commit amend / staged fold), link null-safety, since tip upper bound, invariant-before-init crash, invariants.md FTS indexing, check post-checkout hook, context traps/incidents surfacing, completions for the v2.0.1 commands. 141/141 tests. master @ ea33989, tag v2.0.2, Release published as Latest.

## Next Steps
- Consider --update alias on install-skill (open since internal session)
- Optional: normalize cmd_since timestamps to UTC before comparing (fixes mixed-timezone misorder — see trap, tag:since)
- Optional v2.x/v3.x: archive --compress, intent lineage, dejavue explain (see ROADMAP)

## Boot Instructions
Read `.dejavue/handoff.md`, `.dejavue/state.md`, `.dejavue/decisions.md`, and `.dejavue/timeline.jsonl` before making changes.

# Handoff

Updated: 2026-06-28T00:00:00-05:00

## Summary
Public release scrub and dogfood refresh remain the baseline. The active fix is to make post-commit auto-capture amend HEAD after appending to `timeline.jsonl`, so the worktree returns clean instead of staying dirty after each commit. The repo still treats adopter usage as first-class design evidence, so future changes should fold public-safe downstream lessons back into .dejavue, ROADMAP, and tests.

## Next Steps
- Keep .dejavue/context.md useful: update operating rules, build/test commands, and architecture map whenever behavior changes.
- Prefer public-safe, generalized lessons from adopter usage; do not copy downstream project histories or unrelated environment details into this reference repo.
- Verify the clean-tree auto-capture behavior against the repo's tests and keep an eye on any follow-on docs or workflow polish it needs.
- Next product work remains P1: changelog polish, freshness/expiry, derived_from lineage, stability classes, and UTC timestamp normalization.

## Boot Instructions
Read `.dejavue/handoff.md`, `.dejavue/state.md`, `.dejavue/decisions.md`, and `.dejavue/timeline.jsonl` before making changes.

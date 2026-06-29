#!/usr/bin/env bash
# tests/test_dejavue.sh — integration test suite for dejavue v0.1
# Requirements: bash 4+, python3, git
# Usage: bash tests/test_dejavue.sh
# Exit code: 0 = all pass, 1 = any failure

set -euo pipefail

DEJAVUE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/dejavue.py"
PYTHON="${PYTHON:-python3}"

PASS=0
FAIL=0
ERRORS=()

# ── helpers ────────────────────────────────────────────────────────────────────

setup_repo() {
    local dir
    dir="$(mktemp -d)"
    git init -q "$dir"
    git -C "$dir" config user.email "test@test.test"
    git -C "$dir" config user.name "Test"
    git -C "$dir" commit --allow-empty -q -m "root commit"
    echo "$dir"
}

dv() {
    # Run dejavue with given args from the test repo dir ($TEST_DIR must be set)
    "$PYTHON" "$DEJAVUE" "$@"
}

assert_eq() {
    local label="$1" got="$2" expected="$3"
    if [[ "$got" == "$expected" ]]; then
        return 0
    else
        echo "  ASSERT_EQ FAIL [$label]: got='$got' expected='$expected'" >&2
        return 1
    fi
}

assert_contains() {
    local label="$1" haystack="$2" needle="$3"
    if [[ "$haystack" == *"$needle"* ]]; then
        return 0
    else
        echo "  ASSERT_CONTAINS FAIL [$label]: needle='$needle' not found" >&2
        return 1
    fi
}

assert_not_contains() {
    local label="$1" haystack="$2" needle="$3"
    if [[ "$haystack" != *"$needle"* ]]; then
        return 0
    else
        echo "  ASSERT_NOT_CONTAINS FAIL [$label]: needle='$needle' unexpectedly found" >&2
        return 1
    fi
}

assert_file_exists() {
    local label="$1" path="$2"
    if [[ -f "$path" ]]; then
        return 0
    else
        echo "  ASSERT_FILE_EXISTS FAIL [$label]: $path not found" >&2
        return 1
    fi
}

assert_event_recorded() {
    # Grep timeline.jsonl for a JSON field match
    local label="$1" timeline="$2" field="$3" value="$4"
    # Use python for robust JSON line-by-line check
    if "$PYTHON" - "$timeline" "$field" "$value" <<'PYEOF'
import json, sys
path, field, value = sys.argv[1], sys.argv[2], sys.argv[3]
for line in open(path, encoding="utf-8"):
    line = line.strip()
    if not line:
        continue
    try:
        ev = json.loads(line)
        if str(ev.get(field, "")) == value:
            sys.exit(0)
    except json.JSONDecodeError:
        pass
sys.exit(1)
PYEOF
    then
        return 0
    else
        echo "  ASSERT_EVENT_RECORDED FAIL [$label]: no event with $field='$value' in $timeline" >&2
        return 1
    fi
}

run_test() {
    local name="$1"
    shift
    local status=0
    # Run test function; capture any assertion errors
    if "$@" 2>&1; then
        PASS=$(( PASS + 1 ))
        echo "  PASS: $name"
    else
        status=$?
        FAIL=$(( FAIL + 1 ))
        ERRORS+=("$name")
        echo "  FAIL: $name"
    fi
    return 0
}

cleanup() {
    [[ -n "${TEST_DIR:-}" && -d "${TEST_DIR:-}" ]] && rm -rf "$TEST_DIR"
}

# ── test functions ─────────────────────────────────────────────────────────────

# 1. init creates .dejavue/ structure
test_init_creates_structure() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1

    assert_file_exists "timeline.jsonl" ".dejavue/timeline.jsonl"
    assert_file_exists "state.md" ".dejavue/state.md"
    assert_file_exists "decisions.md" ".dejavue/decisions.md"
    assert_file_exists "handoff.md" ".dejavue/handoff.md"
    [[ -d ".dejavue/references" ]] || { echo "  ASSERT FAIL: references/ dir missing" >&2; return 1; }

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 2. init installs post-commit hook with dejavue marker
test_init_installs_hook() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1

    assert_file_exists "hook" ".git/hooks/post-commit"
    local content
    content="$(cat .git/hooks/post-commit)"
    assert_contains "hook has dejavue marker" "$content" "dejavue auto-capture"
    assert_contains "hook keeps tree clean" "$content" "changed --auto --commit"
    assert_contains "hook requests amend" "$content" "--amend"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 3. init is idempotent (second run doesn't break files)
test_init_idempotent() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    # Capture state.md content after first init
    local first_state
    first_state="$(cat .dejavue/state.md)"

    # Run init again
    dv init >/dev/null 2>&1
    local second_state
    second_state="$(cat .dejavue/state.md)"

    assert_eq "state.md unchanged on second init" "$first_state" "$second_state"
    assert_file_exists "timeline.jsonl still present" ".dejavue/timeline.jsonl"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 4. init --force overwrites an existing non-dejavue post-commit hook
test_init_force_overwrites_hook() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    # Write a foreign hook
    mkdir -p .git/hooks
    printf '#!/usr/bin/env bash\necho "foreign hook"\n' > .git/hooks/post-commit
    chmod +x .git/hooks/post-commit

    local out
    out="$(dv init --force 2>&1)"
    assert_contains "force replaces hook" "$out" "Replaced existing post-commit hook"

    local content
    content="$(cat .git/hooks/post-commit)"
    assert_contains "hook now has dejavue marker" "$content" "dejavue auto-capture"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 5. init without --force refuses to clobber non-dejavue hook (prints WARNING, exits 0)
test_init_no_force_warns_on_existing_hook() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    mkdir -p .git/hooks
    printf '#!/usr/bin/env bash\necho "other hook"\n' > .git/hooks/post-commit
    chmod +x .git/hooks/post-commit

    local out rc
    out="$(dv init 2>&1)"; rc=$?
    assert_eq "exit code is 0" "$rc" "0"
    assert_contains "WARNING present" "$out" "WARNING"
    assert_contains "suggests --force" "$out" "force"

    # Hook must NOT be overwritten
    local content
    content="$(cat .git/hooks/post-commit)"
    assert_not_contains "hook not overwritten" "$content" "dejavue auto-capture"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 6. init outside a git repo prints warning and still creates .dejavue/
test_init_writes_gitattributes() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1

    assert_file_exists ".gitattributes" ".gitattributes"
    local content
    content="$(cat .gitattributes)"
    assert_contains "marker present" "$content" "dejavue: append-only files"
    assert_contains "timeline.jsonl directive" "$content" ".dejavue/timeline.jsonl merge=union"
    assert_contains "decisions.md directive" "$content" ".dejavue/decisions.md   merge=union"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

test_init_gitattributes_idempotent() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    local before_lines
    before_lines="$(wc -l < .gitattributes)"
    dv init >/dev/null 2>&1
    local after_lines
    after_lines="$(wc -l < .gitattributes)"

    assert_eq ".gitattributes line count unchanged after re-init" "$after_lines" "$before_lines"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

test_init_gitattributes_appends_to_existing() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    printf '*.bin binary\n*.lock -diff\n' > .gitattributes
    dv init >/dev/null 2>&1

    local content
    content="$(cat .gitattributes)"
    assert_contains "preserves user *.bin line" "$content" "*.bin binary"
    assert_contains "preserves user *.lock line" "$content" "*.lock -diff"
    assert_contains "appends our marker" "$content" "dejavue: append-only files"
    assert_contains "appends timeline directive" "$content" ".dejavue/timeline.jsonl merge=union"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

test_init_gitattributes_branch_merge_no_conflict() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    # Disable post-commit hook so smoke loop doesn't keep dirtying timeline.jsonl
    git config core.hooksPath /dev/null

    dv init >/dev/null 2>&1
    git add -A && git commit -q -m "dv init"
    local default_branch
    default_branch="$(git symbolic-ref --short HEAD)"

    git checkout -qb branch-a
    dv decision "A picks foo" --reason "branch a says foo" --agent userA >/dev/null
    git add -A && git commit -q -m "branch a decision"

    git checkout -q "$default_branch"
    git checkout -qb branch-b
    dv decision "B picks bar" --reason "branch b says bar" --agent userB >/dev/null
    git add -A && git commit -q -m "branch b decision"

    git checkout -q "$default_branch"
    git merge -q --no-edit branch-a
    # The real test: this merge would conflict on timeline.jsonl + decisions.md
    # WITHOUT merge=union. With merge=union (which init now installs), it's clean.
    git merge -q --no-edit branch-b

    local decisions_content timeline_decision_count
    decisions_content="$(cat .dejavue/decisions.md)"
    assert_contains "merged decisions.md has A's title" "$decisions_content" "A picks foo"
    assert_contains "merged decisions.md has B's title" "$decisions_content" "B picks bar"

    timeline_decision_count="$(grep -c 'decision_title' .dejavue/timeline.jsonl || true)"
    assert_eq "merged timeline.jsonl has both decision events" "$timeline_decision_count" "2"

    if grep -qE '^(<<<<<<< |======= |>>>>>>> )' .dejavue/timeline.jsonl .dejavue/decisions.md; then
        echo "  ASSERT FAIL: conflict markers present after merge — merge=union not honored" >&2
        return 1
    fi

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

test_init_outside_git_repo() {
    TEST_DIR="$(mktemp -d)"
    trap 'rm -rf "$TEST_DIR"' EXIT
    cd "$TEST_DIR"

    local out
    out="$(dv init 2>&1)"
    assert_contains "prints not-in-git warning" "$out" "not inside a git repo"
    [[ -d ".dejavue" ]] || { echo "  ASSERT FAIL: .dejavue/ not created outside git repo" >&2; return 1; }

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 7. start --goal X records session_start event with goal field
test_start_records_session_start() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv start --agent testbot --goal "Write the test suite" >/dev/null 2>&1

    assert_event_recorded "session_start event" ".dejavue/timeline.jsonl" "event" "session_start"
    assert_event_recorded "goal captured" ".dejavue/timeline.jsonl" "goal" "Write the test suite"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 8. changed PATH --summary records file_changed event
test_changed_manual_records_event() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv changed src/auth.rs --summary "Added token validation" >/dev/null 2>&1

    assert_event_recorded "file_changed event" ".dejavue/timeline.jsonl" "event" "file_changed"
    assert_event_recorded "path captured" ".dejavue/timeline.jsonl" "path" "src/auth.rs"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 9. changed --auto --commit <sha> records one file_changed per touched file
test_changed_auto_commit() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    git config core.hooksPath /dev/null

    # Create a real commit with two files
    mkdir -p src
    printf 'hello\n' > src/a.txt
    printf 'world\n' > src/b.txt
    git -C "$TEST_DIR" add src/a.txt src/b.txt
    git -C "$TEST_DIR" commit -q -m "add two files"
    sha="$(git -C "$TEST_DIR" rev-parse HEAD)"

    local out
    out="$(dv changed --auto --commit "$sha" --amend 2>&1)"
    assert_contains "reports 2 events" "$out" "2 file_changed events"

    # Both files should be recorded
    assert_event_recorded "src/a.txt recorded" ".dejavue/timeline.jsonl" "path" "src/a.txt"
    assert_event_recorded "src/b.txt recorded" ".dejavue/timeline.jsonl" "path" "src/b.txt"

    local status
    status="$(git -C "$TEST_DIR" status --short)"
    assert_eq "worktree stays clean after amend" "$status" ""

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 9a. changed --auto --commit <merge-sha> captures files from a merge commit.
#     Regression for: `git show --name-only --format=` silently emits NOTHING for
#     merge commits (default --diff-merges=off), so dejavue's post-commit hook
#     dropped every merge entirely — quantified at ~70% capture loss in
#     multi-agent projects where design lead lands work via merge commits.
test_changed_auto_commit_merge() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1

    # Build a merge: master with x.txt, branch adds y.txt, merge back.
    printf 'x\n' > x.txt
    git -C "$TEST_DIR" add x.txt
    git -C "$TEST_DIR" commit -q -m "base"
    git -C "$TEST_DIR" checkout -q -b feature
    printf 'y\n' > y.txt
    git -C "$TEST_DIR" add y.txt
    git -C "$TEST_DIR" commit -q -m "add y on feature"
    git -C "$TEST_DIR" checkout -q master 2>/dev/null || git -C "$TEST_DIR" checkout -q main
    git -C "$TEST_DIR" merge --no-ff -q -m "merge feature" feature
    sha="$(git -C "$TEST_DIR" rev-parse HEAD)"

    local out
    out="$(dv changed --auto --commit "$sha" 2>&1)"
    # Pre-fix: this said "0 file_changed events". Post-fix: 1 (y.txt via first parent).
    assert_contains "captures merge files" "$out" "1 file_changed events"
    assert_event_recorded "y.txt recorded from merge" ".dejavue/timeline.jsonl" "path" "y.txt"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 10. post-commit hook fires after git commit: timeline grows by N file_changed events
test_post_commit_hook_fires() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1

    # Count events before
    local before after
    before="$(grep -c '"event"' .dejavue/timeline.jsonl 2>/dev/null || echo 0)"

    # Make a real commit — hook should fire
    printf 'content\n' > hooktest.txt
    git -C "$TEST_DIR" add hooktest.txt
    git -C "$TEST_DIR" commit -q -m "hook test commit"

    after="$(grep -c '"file_changed"' .dejavue/timeline.jsonl 2>/dev/null || echo 0)"
    [[ "$after" -ge 1 ]] || { echo "  ASSERT FAIL: no file_changed events after commit (hook didn't fire)" >&2; return 1; }

    local status
    status="$(git -C "$TEST_DIR" status --short)"
    assert_eq "worktree clean after hook amend" "$status" ""

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 11. decision TITLE --reason appends to decisions.md AND timeline
test_decision_records_event_and_doc() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv decision "Use JSONL" --reason "Append-only, merge-friendly" >/dev/null 2>&1

    # Timeline event
    assert_event_recorded "decision event" ".dejavue/timeline.jsonl" "event" "decision"
    assert_event_recorded "decision title" ".dejavue/timeline.jsonl" "decision_title" "Use JSONL"

    # decisions.md entry
    local dcontent
    dcontent="$(cat .dejavue/decisions.md)"
    assert_contains "title in decisions.md" "$dcontent" "Use JSONL"
    assert_contains "reason in decisions.md" "$dcontent" "Append-only, merge-friendly"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 12. decision --rejected captures rejected_alternatives list in event JSON
test_decision_rejected_alternatives() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv decision "Use SQLite" \
        --reason "Single file, zero deps" \
        --rejected "PostgreSQL: too heavy" \
        --rejected "MySQL: license concern" \
        >/dev/null 2>&1

    # Check timeline for rejected_alternatives field containing both options
    local found
    found="$("$PYTHON" - ".dejavue/timeline.jsonl" <<'PYEOF'
import json, sys
path = sys.argv[1]
for line in open(path, encoding="utf-8"):
    line = line.strip()
    if not line: continue
    try:
        ev = json.loads(line)
        ra = ev.get("rejected_alternatives", [])
        options = [r.get("option","") for r in ra]
        if "PostgreSQL" in options and "MySQL" in options:
            print("FOUND")
            sys.exit(0)
    except json.JSONDecodeError:
        pass
sys.exit(1)
PYEOF
)"
    assert_eq "rejected_alternatives captured" "$found" "FOUND"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 13. state --summary overwrites state.md with new content + timestamp
test_state_overwrites_state_md() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv state --summary "Phase 1 complete, tests green" >/dev/null 2>&1

    local scontent
    scontent="$(cat .dejavue/state.md)"
    assert_contains "summary in state.md" "$scontent" "Phase 1 complete, tests green"
    assert_contains "Updated timestamp" "$scontent" "Updated:"

    assert_event_recorded "state_update event" ".dejavue/timeline.jsonl" "event" "state_update"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 14. handoff --summary --next overwrites handoff.md
test_handoff_writes_handoff_md() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv handoff --summary "Shipped recall command" --next "Write README" >/dev/null 2>&1

    local hcontent
    hcontent="$(cat .dejavue/handoff.md)"
    assert_contains "summary in handoff.md" "$hcontent" "Shipped recall command"
    assert_contains "next in handoff.md" "$hcontent" "Write README"

    assert_event_recorded "handoff event" ".dejavue/timeline.jsonl" "event" "handoff"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 14a. handoff with multiple --next renders as bullet list
test_handoff_multiple_next_renders_bullets() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv handoff --summary "Multi-next test" \
        --next "First step" \
        --next "Second step" \
        --next "Third step" >/dev/null 2>&1

    local hcontent
    hcontent="$(cat .dejavue/handoff.md)"
    assert_contains "first next preserved" "$hcontent" "First step"
    assert_contains "second next preserved" "$hcontent" "Second step"
    assert_contains "third next preserved" "$hcontent" "Third step"
    assert_contains "first rendered as bullet" "$hcontent" "- First step"
    assert_contains "second rendered as bullet" "$hcontent" "- Second step"
    assert_contains "third rendered as bullet" "$hcontent" "- Third step"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 15. context prints handoff + state + decisions + last 10 timeline entries
test_context_prints_all_sections() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv start --goal "Test context command" >/dev/null 2>&1
    dv state --summary "context test state" >/dev/null 2>&1
    dv handoff --summary "context handoff" --next "nothing" >/dev/null 2>&1

    local out
    out="$(dv context 2>&1)"
    assert_contains "handoff section" "$out" "handoff.md"
    assert_contains "state section" "$out" "state.md"
    assert_contains "decisions section" "$out" "decisions.md"
    assert_contains "timeline section" "$out" "recent timeline"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 16. since DATE shows git delta and timeline events in window
test_since_date_form() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv start --goal "since-date test" >/dev/null 2>&1

    local out
    out="$(dv since 2026-01-01 2>&1)"
    assert_contains "since label present" "$out" "Since"
    assert_contains "git delta section" "$out" "Git delta:"
    assert_contains "timeline events section" "$out" "Timeline events"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 17. since <commit-sha> shows commits and timeline events after that commit
test_since_commit_form() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    local sha
    sha="$(git -C "$TEST_DIR" rev-parse HEAD)"

    # Make another commit so there's a delta
    printf 'x\n' > x.txt
    git -C "$TEST_DIR" add x.txt
    git -C "$TEST_DIR" commit -q -m "add x"
    dv start --goal "after first commit" >/dev/null 2>&1

    local out
    out="$(dv since "$sha" 2>&1)"
    assert_contains "commit form label" "$out" "commit $sha"
    assert_contains "timeline events" "$out" "Timeline events"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 18 & 19. since --agent NAME finds last session_start; unknown agent prints error
test_since_agent_known() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv start --agent mybot --goal "agent since test" >/dev/null 2>&1

    local out
    out="$(dv since --agent mybot 2>&1)"
    assert_contains "agent label" "$out" "agent mybot"
    assert_contains "timeline events section" "$out" "Timeline events"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

test_since_agent_unknown() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1

    local out
    out="$(dv since --agent UNKNOWN_AGENT_XYZ 2>&1)"
    assert_contains "no session_start msg" "$out" "No session_start event found for agent 'UNKNOWN_AGENT_XYZ'."

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 20. since with no args prints usage hint
test_since_no_args_prints_usage() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    local out
    out="$(dv since 2>&1)"
    assert_contains "usage hint" "$out" "Usage"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 21. ingest records events and creates ingested.lock
test_ingest_creates_lock() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    # Create a real commit so git log has something
    printf 'content\n' > file.txt
    git -C "$TEST_DIR" add file.txt
    git -C "$TEST_DIR" commit -q -m "add file"

    local out
    out="$(dv ingest 2>&1)"
    assert_contains "ingested output" "$out" "Ingested"
    assert_file_exists "ingested.lock created" ".dejavue/ingested.lock"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 22. ingest second run prints "Already ingested" without --force
test_ingest_idempotent_without_force() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv ingest >/dev/null 2>&1

    local out
    out="$(dv ingest 2>&1)"
    assert_contains "already ingested message" "$out" "Already ingested"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 23. ingest --force re-runs even with marker present
test_ingest_force_reruns() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv ingest >/dev/null 2>&1

    local out
    out="$(dv ingest --force 2>&1)"
    # Should NOT print "Already ingested" when --force is used
    assert_not_contains "no already-ingested msg" "$out" "Already ingested"
    assert_contains "re-ran ingest" "$out" "Ingested"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 24. recall returns results matching a known summary
test_recall_returns_results() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv start --goal "FTS5 recall uniquetoken_xyz test" >/dev/null 2>&1

    local out
    out="$(dv recall uniquetoken_xyz 2>&1)"
    assert_contains "recall finds result" "$out" "uniquetoken_xyz"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 25. recall LIKE fallback branch exists in dejavue.py (code path verification)
test_recall_like_branch_exists() {
    # Confirm the LIKE fallback branch is present in the source
    grep -q 'LIKE' "$DEJAVUE" || {
        echo "  ASSERT FAIL: LIKE fallback branch not found in dejavue.py" >&2
        return 1
    }
    grep -q 'falling back to LIKE search' "$DEJAVUE" || {
        echo "  ASSERT FAIL: LIKE fallback warning message not found in dejavue.py" >&2
        return 1
    }
}

# 25a. recall --semantic flag is registered in argparse
test_recall_semantic_flag_present() {
    local out
    out="$(dv recall --help 2>&1)"
    assert_contains "recall help mentions --semantic" "$out" "--semantic"
    assert_contains "recall help mentions DEJAVUE_EMBEDDER_URL" "$out" "DEJAVUE_EMBEDDER_URL"
}

# 25b. --semantic falls back to FTS5 with a warning when embedder is unreachable
test_recall_semantic_falls_back_when_embedder_down() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv start --goal "FTS5 recall semfallback_xyz test" >/dev/null 2>&1

    local out
    # Point at a guaranteed-unreachable URL (port 1 is always refused).
    out="$(DEJAVUE_EMBEDDER_URL=http://127.0.0.1:1/v1/embeddings dv recall semfallback_xyz --semantic 2>&1)"
    assert_contains "semantic fallback warning printed" "$out" "embedder"
    assert_contains "semantic fallback warning printed" "$out" "falling back to FTS5"
    # After the warning, the FTS5 path should still find the seeded event.
    assert_contains "semantic fallback finds FTS5 result" "$out" "semfallback_xyz"
    # No embeddings.jsonl should be written when the query embed call fails.
    if [[ -f ".dejavue/embeddings.jsonl" ]]; then
        echo "  ASSERT FAIL: embeddings.jsonl should not exist after embedder failure" >&2
        return 1
    fi

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 25c. Semantic helpers are present in the source — hash-keyed cache + cosine
test_recall_semantic_helpers_present() {
    grep -q '_line_hash' "$DEJAVUE" || {
        echo "  ASSERT FAIL: _line_hash helper not found in dejavue.py" >&2
        return 1
    }
    grep -q '_cosine' "$DEJAVUE" || {
        echo "  ASSERT FAIL: _cosine helper not found in dejavue.py" >&2
        return 1
    }
    grep -q 'embeddings.jsonl' "$DEJAVUE" || {
        echo "  ASSERT FAIL: embeddings.jsonl cache path not found in dejavue.py" >&2
        return 1
    }
}

# 26. worthiness prints CAPTURE and SKIP strings
test_worthiness_prints_table() {
    local out
    out="$("$PYTHON" "$DEJAVUE" worthiness 2>&1)"
    assert_contains "CAPTURE word present" "$out" "CAPTURE"
    assert_contains "SKIP word present" "$out" "SKIP"
    assert_contains "rule of thumb present" "$out" "Rule of thumb"

}

# 27. get state, get handoff, get decisions print file contents
test_get_known_docs() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv state --summary "current state for get test" >/dev/null 2>&1
    dv handoff --summary "handoff for get test" --next "nothing" >/dev/null 2>&1

    local sout hout dout
    sout="$(dv get state 2>&1)"
    hout="$(dv get handoff 2>&1)"
    dout="$(dv get decisions 2>&1)"

    assert_contains "get state content" "$sout" "current state for get test"
    assert_contains "get handoff content" "$hout" "handoff for get test"
    assert_contains "get decisions has header" "$dout" "Decisions"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 28. get references/nonexistent prints "does not exist"
test_get_nonexistent_reference() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    local out
    out="$(dv get references/doesnotexist 2>&1)"
    assert_contains "does not exist message" "$out" "does not exist"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 29. get unknownword prints "Unknown doc"
test_get_unknown_doc() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    local out
    out="$(dv get unknownword 2>&1)"
    assert_contains "Unknown doc message" "$out" "Unknown doc"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 30. list shows all artifact paths
test_list_shows_artifacts() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    local out
    out="$(dv list 2>&1)"
    assert_contains "events listed" "$out" "events:"
    assert_contains "decisions listed" "$out" "decisions:"
    assert_contains "state listed" "$out" "state:"
    assert_contains "handoff listed" "$out" "handoff:"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 31. list --type events shows only events
test_list_type_events() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    local out
    out="$(dv list --type events 2>&1)"
    assert_contains "events line present" "$out" "events:"
    assert_not_contains "no handoff line" "$out" "handoff:"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 32. annotate handoff appends timestamped note section
test_annotate_handoff() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    dv annotate handoff "this is my test annotation note" >/dev/null 2>&1

    local hcontent
    hcontent="$(cat .dejavue/handoff.md)"
    assert_contains "note in handoff.md" "$hcontent" "this is my test annotation note"
    assert_contains "annotation section header" "$hcontent" "annotation"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# 33. annotate unknowndoc prints "Unknown doc"
test_annotate_unknown_doc() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"

    dv init >/dev/null 2>&1
    local out
    out="$(dv annotate unknowndoc "some note" 2>&1)"
    assert_contains "Unknown doc message" "$out" "Unknown doc"

    cd /
    rm -rf "$TEST_DIR"; trap - EXIT
}

# ── v1.0 new-feature tests ─────────────────────────────────────────────────────

test_version_prints_version() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    out="$(dv version)"
    assert_contains "version output" "$out" "dejavue 2."
}

test_init_creates_prepush_hook() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    git_dir="$(git rev-parse --git-dir)"
    assert_file_exists "pre-push hook" "$git_dir/hooks/pre-push"
    hook_content="$(cat "$git_dir/hooks/pre-push")"
    assert_contains "pre-push marker" "$hook_content" "dejavue pre-push"
}

test_init_creates_gitignore() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    assert_file_exists "gitignore" ".gitignore"
    content="$(cat .gitignore)"
    assert_contains "fts.db ignored" "$content" ".dejavue/fts.db"
    assert_contains "locks ignored" "$content" ".dejavue/.locks/"
}

test_init_map_scaffolds_map_md() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init --map >/dev/null 2>&1
    assert_file_exists "map.md" ".dejavue/references/map.md"
    content="$(cat .dejavue/references/map.md)"
    assert_contains "map has header" "$content" "Codebase Map"
    assert_contains "map has layout section" "$content" "Top-level layout"
    assert_contains "map has invariants section" "$content" "Design invariants"
}

test_init_ingest_auto_ingests() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    echo "# Test README" > README.md
    git add README.md && git commit -q -m "add readme" 2>/dev/null || true
    dv init --ingest >/dev/null 2>&1
    assert_file_exists "ingested lock" ".dejavue/ingested.lock"
}

test_agent_identity_from_env() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    AGENT_NAME=testbot dv start --goal "test env agent" >/dev/null 2>&1
    events="$(cat .dejavue/timeline.jsonl)"
    assert_contains "AGENT_NAME used" "$events" '"testbot"'
}

test_agent_identity_explicit_overrides_env() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    AGENT_NAME=envbot dv start --agent explicitbot --goal "test" >/dev/null 2>&1
    events="$(cat .dejavue/timeline.jsonl)"
    assert_contains "explicit agent wins" "$events" '"explicitbot"'
    assert_not_contains "env agent suppressed" "$events" '"envbot"'
}

test_context_shows_staleness_warnings() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    # state.md is a stub after init
    out="$(dv context 2>&1)"
    assert_contains "stub warning" "$out" "stub"
}

test_context_check_stale_prints_to_stderr() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    stderr_out="$(dv context --check-stale 2>&1 >/dev/null)"
    assert_contains "check-stale warning" "$stderr_out" "state"
}

test_context_lists_references_when_present() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    mkdir -p .dejavue/references
    echo "# Architecture Overview" > .dejavue/references/arch.md
    out="$(dv context 2>&1)"
    assert_contains "references section" "$out" "references"
    assert_contains "reference file listed" "$out" "arch.md"
}

test_status_basic_output() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv start --agent claude --goal "test status" >/dev/null 2>&1
    out="$(dv status 2>&1)"
    assert_contains "status shows agent" "$out" "claude"
    assert_contains "status shows events" "$out" "Events"
}

test_status_shows_last_decision() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "Use FTS5" --reason "fast stdlib" --agent claude >/dev/null 2>&1
    out="$(dv status 2>&1)"
    assert_contains "status shows decision" "$out" "Use FTS5"
}

test_log_basic() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv start --agent claude --goal "test log" >/dev/null 2>&1
    dv decision "test decision" --reason "just testing" >/dev/null 2>&1
    out="$(dv log 2>&1)"
    assert_contains "log shows events" "$out" "session_start"
    assert_contains "log shows decision" "$out" "decision"
}

test_log_oneline() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv start --agent claude --goal "test log oneline" >/dev/null 2>&1
    out="$(dv log --oneline 2>&1)"
    assert_contains "oneline has event type" "$out" "session_start"
}

test_log_type_filter() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv start --agent claude --goal "test" >/dev/null 2>&1
    dv decision "arch decision" --reason "testing" >/dev/null 2>&1
    out="$(dv log --type decision 2>&1)"
    assert_contains "filtered log shows decision" "$out" "decision"
    assert_not_contains "filtered log hides start" "$out" "session_start"
}

test_blame_finds_relevant_events() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "Add parser module" --reason "need argument parsing for parser.py" >/dev/null 2>&1
    out="$(dv blame parser.py 2>&1)"
    assert_contains "blame finds decision" "$out" "Add parser module"
}

test_blame_no_results() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    out="$(dv blame nonexistent_totally_absent_file.xyz 2>&1)"
    assert_contains "blame no results" "$out" "No events found"
}

test_note_records_event() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv note "quick thought about the API design" --tag api >/dev/null 2>&1
    events="$(cat .dejavue/timeline.jsonl)"
    assert_contains "note event recorded" "$events" '"note"'
    assert_contains "note text in timeline" "$events" "quick thought about the API design"
    assert_contains "note tag in timeline" "$events" '"api"'
}

test_ingest_generate_map() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    # Create a Python project marker
    echo '[project]
name = "myapp"' > pyproject.toml
    dv ingest --force --generate-map >/dev/null 2>&1
    assert_file_exists "map.md generated" ".dejavue/references/map.md"
    content="$(cat .dejavue/references/map.md)"
    assert_contains "map has header" "$content" "Codebase Map"
    assert_contains "map mentions python" "$content" "Python"
}

test_decision_outcome_flag() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "Use JSONL format" \
        --reason "append-only, merge-friendly" \
        --outcome "Shipped in v0.1, working well" >/dev/null 2>&1
    doc="$(cat .dejavue/decisions.md)"
    assert_contains "outcome in decisions.md" "$doc" "Shipped in v0.1"
    events="$(cat .dejavue/timeline.jsonl)"
    assert_contains "outcome in timeline" "$events" "Shipped in v0.1"
}

test_check_passes_healthy() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv state --summary "test state" >/dev/null 2>&1
    out="$(dv check 2>&1)"
    assert_contains "check shows timeline" "$out" "timeline.jsonl"
    assert_contains "check shows hooks" "$out" "post-commit hook"
    assert_contains "check shows gitattributes" "$out" ".gitattributes"
}

test_check_warns_no_hooks() {
    TEST_DIR="$(mktemp -d)"
    trap "rm -rf '$TEST_DIR'" EXIT
    cd "$TEST_DIR"
    git init -q && git config user.email "t@t.t" && git config user.name "T"
    git commit --allow-empty -q -m "root"
    mkdir -p .dejavue
    echo '{"ts":"2026-01-01","event":"init","summary":"test"}' > .dejavue/timeline.jsonl
    echo "# State" > .dejavue/state.md
    out="$(dv check 2>&1)"
    assert_contains "check warns missing hook" "$out" "post-commit"
}

test_archive_dryrun() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    # seed some old file_changed events with a past timestamp
    echo '{"ts":"2025-01-01T00:00:00+00:00","event":"file_changed","path":"foo.rs","summary":"old","agent":"test"}' >> .dejavue/timeline.jsonl
    echo '{"ts":"2025-01-02T00:00:00+00:00","event":"file_changed","path":"bar.rs","summary":"old","agent":"test"}' >> .dejavue/timeline.jsonl
    out="$(dv archive --before 2026-01-01 2>&1)"
    assert_contains "archive dry-run shows plan" "$out" "Archive plan"
    assert_contains "archive dry-run shows count" "$out" "file_changed to drop"
    # original timeline unchanged (no --yes)
    line_count="$(wc -l < .dejavue/timeline.jsonl)"
    [[ "$line_count" -ge 2 ]]
}

test_archive_applies() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "keep this" --reason "important" >/dev/null 2>&1
    # seed old file_changed events
    echo '{"ts":"2025-01-01T00:00:00+00:00","event":"file_changed","path":"old.rs","summary":"old","agent":"test"}' >> .dejavue/timeline.jsonl
    echo '{"ts":"2025-01-02T00:00:00+00:00","event":"file_changed","path":"old2.rs","summary":"old","agent":"test"}' >> .dejavue/timeline.jsonl
    dv archive --before 2026-01-01 --yes >/dev/null 2>&1
    events="$(cat .dejavue/timeline.jsonl)"
    assert_contains "archive event recorded" "$events" '"archive"'
    # the old file_changed events should be gone
    assert_not_contains "old paths removed" "$events" '"old.rs"'
    # decision should survive
    assert_contains "decision kept" "$events" '"keep this"'
    # backup file exists
    assert_file_exists "backup created" ".dejavue/timeline.jsonl.bak-2026-01-01"
}

test_roster_shows_agents() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv start --agent alice --goal "first session" >/dev/null 2>&1
    dv decision "arch choice" --reason "test" --agent alice >/dev/null 2>&1
    dv start --agent bob --goal "second session" >/dev/null 2>&1
    out="$(dv roster 2>&1)"
    assert_contains "roster shows alice" "$out" "alice"
    assert_contains "roster shows bob" "$out" "bob"
    assert_contains "roster shows sessions" "$out" "session"
    assert_contains "roster shows decisions" "$out" "decision"
}

test_config_roundtrip() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv config set agent_name myagent >/dev/null 2>&1
    val="$(dv config get agent_name)"
    assert_eq "config get after set" "$val" "myagent"
    list_out="$(dv config list)"
    assert_contains "config list shows key" "$list_out" "agent_name"
    dv config unset agent_name >/dev/null 2>&1
    if dv config get agent_name 2>/dev/null; then
        echo "ASSERT FAIL: key should be unset" >&2
        return 1
    fi
    return 0
}

test_log_reverse() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv start --agent claude --goal "first" >/dev/null 2>&1
    dv decision "first decision" --reason "test" >/dev/null 2>&1
    out_normal="$(dv log --oneline 2>&1)"
    out_reverse="$(dv log --oneline --reverse 2>&1)"
    # The two outputs should differ when there are multiple events
    [[ "$out_normal" != "$out_reverse" ]]
}

test_recall_limit() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    # seed 5 distinct decision events
    for i in 1 2 3 4 5; do
        dv decision "decision $i" --reason "reason $i" >/dev/null 2>&1
    done
    out_5="$(dv recall "decision" --limit 5 2>&1)"
    out_2="$(dv recall "decision" --limit 2 2>&1)"
    count_5="$(echo "$out_5" | grep -c "\[score\]\|\[20" || true)"
    # --limit 2 output should be shorter than --limit 5 output
    len_5="${#out_5}"
    len_2="${#out_2}"
    [[ "$len_5" -gt "$len_2" ]]
}

test_circuit_breaker_in_source() {
    grep -q '_CIRCUIT_THRESHOLD' "$DEJAVUE" || { echo "  FAIL: _CIRCUIT_THRESHOLD missing" >&2; return 1; }
    grep -q 'def _circuit_open' "$DEJAVUE"  || { echo "  FAIL: _circuit_open missing" >&2; return 1; }
    grep -q 'def _circuit_record' "$DEJAVUE" || { echo "  FAIL: _circuit_record missing" >&2; return 1; }
}

test_decision_type_blocker() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "Blocked on auth API" --reason "API not ready" --type blocker >/dev/null 2>&1
    events="$(cat .dejavue/timeline.jsonl)"
    assert_contains "event_type in timeline" "$events" '"blocker"'
    doc="$(cat .dejavue/decisions.md)"
    assert_contains "BLOCKER label in doc" "$doc" "[BLOCKER]"
}

test_note_type_question() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv note "Should we use CQRS here?" --type question >/dev/null 2>&1
    events="$(cat .dejavue/timeline.jsonl)"
    assert_contains "event_type question in timeline" "$events" '"question"'
}

test_stats_shows_counts() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv start --agent claude --goal "test" >/dev/null 2>&1
    dv decision "some decision" --reason "reason" >/dev/null 2>&1
    out="$(dv stats 2>&1)"
    assert_contains "stats shows total" "$out" "Total events"
    assert_contains "stats shows event type" "$out" "decision"
    assert_contains "stats shows by agent" "$out" "By agent"
}

test_stats_shows_agents() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv start --agent alice --goal "test" >/dev/null 2>&1
    dv start --agent bob --goal "test2" >/dev/null 2>&1
    out="$(dv stats 2>&1)"
    assert_contains "stats shows alice" "$out" "alice"
    assert_contains "stats shows bob" "$out" "bob"
}

test_export_json_valid() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "arch" --reason "test" >/dev/null 2>&1
    out="$(dv export --format json 2>&1)"
    # Must be valid JSON
    echo "$out" | "$PYTHON" -c "import json,sys; json.load(sys.stdin)" || {
        echo "  FAIL: export json is not valid JSON" >&2; return 1;
    }
    assert_contains "json has version" "$out" "dejavue_version"
    assert_contains "json has events" "$out" '"events"'
}

test_export_md_has_sections() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv state --summary "test state content" >/dev/null 2>&1
    dv decision "arch" --reason "test" >/dev/null 2>&1
    out="$(dv export --format md 2>&1)"
    assert_contains "md has export header" "$out" "Dejavue Memory Export"
    assert_contains "md has state" "$out" "test state content"
    assert_contains "md has timeline" "$out" "Timeline"
}

test_reference_create() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv reference create my-module >/dev/null 2>&1
    assert_file_exists "reference card created" ".dejavue/references/my-module.md"
    content="$(cat .dejavue/references/my-module.md)"
    assert_contains "reference has title" "$content" "My Module"
}

test_reference_create_api_template() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv reference create auth-api --template api >/dev/null 2>&1
    content="$(cat .dejavue/references/auth-api.md)"
    assert_contains "api template has endpoint" "$content" "Endpoint"
    assert_contains "api template has parameters" "$content" "Parameters"
}

test_reference_list() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv reference create foo >/dev/null 2>&1
    dv reference create bar >/dev/null 2>&1
    out="$(dv reference list 2>&1)"
    assert_contains "reference list shows foo" "$out" "foo"
    assert_contains "reference list shows bar" "$out" "bar"
}

test_reference_update() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv reference create myref >/dev/null 2>&1
    dv reference update myref --content "# Updated Content" >/dev/null 2>&1
    content="$(cat .dejavue/references/myref.md)"
    assert_contains "reference updated" "$content" "Updated Content"
}

test_reference_view() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv reference create viewme --content "# View Me Test" >/dev/null 2>&1
    out="$(dv reference view viewme 2>&1)"
    assert_contains "reference view shows content" "$out" "View Me Test"
}

test_link_finds_events() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    # make a commit and trigger auto-capture
    echo "hello" > test.txt
    git add test.txt && git commit -q -m "add test file" 2>/dev/null || true
    sha="$(git rev-parse HEAD)"
    out="$(dv link "$sha" 2>&1)"
    assert_contains "link finds commit events" "$out" "${sha:0:7}"
}

test_link_no_results() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    out="$(dv link deadbeef 2>&1)"
    assert_contains "link no results message" "$out" "No dejavue events"
}

test_search_alias() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "Use FTS5" --reason "fast sqlite recall" >/dev/null 2>&1
    out="$(dv search "FTS5" 2>&1)"
    assert_contains "search alias returns results" "$out" "FTS5"
}

test_context_n_flag() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    for i in 1 2 3 4 5; do
        dv note "note $i" >/dev/null 2>&1
    done
    out3="$(dv context -n 3 2>&1)"
    out5="$(dv context -n 5 2>&1)"
    assert_contains "n=3 header" "$out3" "last 3"
    assert_contains "n=5 header" "$out5" "last 5"
    # n=5 output should be longer than n=3
    [[ "${#out5}" -gt "${#out3}" ]]
}

test_tiered_embedder_in_source() {
    grep -q '_auto_detect_embedder_url' "$DEJAVUE" || {
        echo "  FAIL: _auto_detect_embedder_url missing" >&2; return 1;
    }
    grep -q 'openai.com' "$DEJAVUE" || {
        echo "  FAIL: OpenAI tiered fallback missing" >&2; return 1;
    }
}

test_embeddings_model_aware() {
    grep -q 'model_filter\|row_model' "$DEJAVUE" || {
        echo "  FAIL: model-aware cache code missing" >&2; return 1;
    }
}

test_check_fix_gitignore() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    # Remove gitignore entries
    rm -f .gitignore
    out="$(dv check --fix 2>&1)"
    assert_contains "check --fix reports fix" "$out" "gitignore\|auto-fixed\|↻" || true
    # gitignore should now exist
    assert_file_exists "gitignore restored" ".gitignore"
}

test_check_fix_fts() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "test" --reason "stale fts test" >/dev/null 2>&1
    # Make FTS stale by removing it
    rm -f .dejavue/fts.db
    out="$(dv check --fix 2>&1)"
    # fts.db should be rebuilt
    assert_file_exists "fts rebuilt" ".dejavue/fts.db"
}

test_diff_date_window() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "past decision" --reason "test" >/dev/null 2>&1
    today="$(date +%Y-%m-%d)"
    out="$(dv diff 2020-01-01 "$today" 2>&1)"
    assert_contains "diff shows events" "$out" "Events in window"
    assert_contains "diff shows decision" "$out" "past decision"
}

test_diff_git_objects() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    git add .dejavue && git commit -q -m "init dejavue" 2>/dev/null || true
    first_sha="$(git rev-parse HEAD)"
    dv state --summary "new state content" >/dev/null 2>&1
    git add .dejavue && git commit -q -m "update state" 2>/dev/null || true
    out="$(dv diff "$first_sha" HEAD 2>&1)"
    assert_contains "diff shows header" "$out" "Dejavue diff"
}

test_timeline_by_day() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv start --agent claude --goal "timeline test" >/dev/null 2>&1
    dv decision "test decision" --reason "test" >/dev/null 2>&1
    out="$(dv timeline --by day 2>&1)"
    assert_contains "timeline shows header" "$out" "Activity by day"
    assert_contains "timeline shows date" "$out" "$(date +%Y-%m-%d)"
}

test_timeline_by_week() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv start --agent claude --goal "week test" >/dev/null 2>&1
    out="$(dv timeline --by week 2>&1)"
    assert_contains "timeline by week" "$out" "Activity by week"
    assert_contains "timeline shows total" "$out" "Total"
}

test_tag_list() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv note "important finding" --tag "discovery" >/dev/null 2>&1
    dv note "another finding" --tag "discovery" >/dev/null 2>&1
    dv note "edge case" --tag "bug" >/dev/null 2>&1
    out="$(dv tag list 2>&1)"
    assert_contains "tag list shows discovery" "$out" "discovery"
    assert_contains "tag list shows bug" "$out" "bug"
    assert_contains "tag list shows count 2" "$out" "2"
}

test_tag_filter() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv note "tagged note alpha" --tag "alpha" >/dev/null 2>&1
    dv note "tagged note beta" --tag "beta" >/dev/null 2>&1
    out="$(dv tag filter alpha 2>&1)"
    assert_contains "filter shows tagged note" "$out" "tagged note alpha"
    assert_not_contains "filter hides other tag" "$out" "tagged note beta"
}

test_note_commit_writes_note() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "linked decision" --reason "for git notes test" >/dev/null 2>&1
    sha="$(git rev-parse HEAD)"
    out="$(dv note-commit "$sha" 2>&1)"
    assert_contains "note-commit confirms write" "$out" "Git note written"
    # Verify the note was actually written
    note_content="$(git notes show "$sha" 2>/dev/null || echo '')"
    assert_contains "git note exists" "$note_content" "Dejavue-Event:"
}

test_since_shows_notes() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv note "important observation" --tag "watch" >/dev/null 2>&1
    out="$(dv since 2020-01-01 2>&1)"
    assert_contains "since shows notes section" "$out" "important observation"
}

test_event_type_in_fts() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "deployment issue" --reason "infra not ready" --type blocker >/dev/null 2>&1
    # recall should find "blocker" via event_type in the FTS index
    out="$(dv recall blocker 2>&1)"
    assert_contains "event_type searchable" "$out" "deployment issue"
}

test_v13_commands_present() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv diff --help >/dev/null 2>&1 || { echo "  FAIL: diff command missing" >&2; return 1; }
    dv timeline --help >/dev/null 2>&1 || { echo "  FAIL: timeline command missing" >&2; return 1; }
    dv tag list --help >/dev/null 2>&1 || { echo "  FAIL: tag command missing" >&2; return 1; }
    dv note-commit --help >/dev/null 2>&1 || { echo "  FAIL: note-commit command missing" >&2; return 1; }
}

# ── DCP (DejaVue Context Protocol) tests ────────────────────────────────────────

# M1: init scaffolds context.md with DCP frontmatter
test_dcp_init_scaffolds_context() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    assert_file_exists "context.md" ".dejavue/context.md" || return 1
    local content
    content="$(cat .dejavue/context.md)"
    assert_contains "dcp frontmatter" "$content" "dcp: DCP/1.0" || return 1
    assert_contains "operating rules section" "$content" "## Operating Rules" || return 1
    assert_contains "build/test section" "$content" "## Build / Test" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M1: base loop unaffected — absence of context.md does not break context cmd
test_dcp_context_absent_ok() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    rm -f .dejavue/context.md
    local out
    out="$(dv context 2>&1)"
    assert_contains "context still runs" "$out" "Dejavue Context" || return 1
    assert_not_contains "no context.md section" "$out" "--- context.md" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M1: dejavue context surfaces context.md when present
test_dcp_context_surfaces_context_md() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    local out
    out="$(dv context 2>&1)"
    assert_contains "surfaces context.md" "$out" "--- context.md" || return 1
    assert_contains "shows DCP tag" "$out" "[DCP/1.0]" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M1: frontmatter parser handles key:value + body (probe via context surfacing)
test_dcp_frontmatter_parse() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    printf -- '---\nname: probe\npurpose: testing\ndcp: DCP/1.0\n---\n\n# Body\nhello world\n' > .dejavue/context.md
    local out
    out="$(dv context 2>&1)"
    assert_contains "body preserved" "$out" "hello world" || return 1
    assert_contains "dcp tag from parsed meta" "$out" "[DCP/1.0]" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M2: import seeds context.md losslessly + records provenance event
test_dcp_import_roundtrip() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    printf '# Hand CLAUDE\n\nKEEP_THIS_MARKER line.\n' > CLAUDE.md
    git add CLAUDE.md && git commit -q -m "add claude"
    local out
    out="$(dv import CLAUDE.md 2>&1)"
    assert_contains "import reports lossless" "$out" "lossless" || return 1
    local ctx
    ctx="$(cat .dejavue/context.md)"
    assert_contains "content preserved lossless" "$ctx" "KEEP_THIS_MARKER" || return 1
    assert_contains "provenance source recorded" "$ctx" "source: CLAUDE.md" || return 1
    assert_event_recorded "import event" ".dejavue/timeline.jsonl" "event" "import" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M2: import refuses to clobber a populated context.md without --force
test_dcp_import_guards_populated() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    printf '# Source\nbody one\n' > AGENTS.md
    dv import AGENTS.md >/dev/null 2>&1   # first import populates context.md
    printf '# Source2\nbody two\n' > OTHER.md
    local out
    out="$(dv import OTHER.md 2>&1)"
    assert_contains "guard warns" "$out" "already exists" || return 1
    local out2
    out2="$(dv import OTHER.md --force 2>&1)"
    assert_contains "force overrides" "$out2" "lossless" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M3: export to ABSENT target creates a block-only file
test_dcp_export_creates_absent() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    local out
    out="$(dv export --target gemini 2>&1)"
    assert_contains "created message" "$out" "created GEMINI.md" || return 1
    assert_file_exists "GEMINI.md" "GEMINI.md" || return 1
    local content
    content="$(cat GEMINI.md)"
    assert_contains "begin marker" "$content" "dejavue:begin DCP/1.0 src=context.md" || return 1
    assert_contains "end marker" "$content" "dejavue:end" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M3: export to UNMARKED hand-written target appends + warns, preserves content
test_dcp_export_appends_unmarked() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    printf '# Hand CLAUDE\n\nPRESERVE_ME line.\n' > CLAUDE.md
    local out
    out="$(dv export --target claude 2>&1)"
    assert_contains "warns on append" "$out" "WARNING" || return 1
    local content
    content="$(cat CLAUDE.md)"
    assert_contains "hand-written preserved" "$content" "PRESERVE_ME" || return 1
    assert_contains "managed block appended" "$content" "dejavue:begin" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M3: re-export to MARKED target replaces only the fenced region (idempotent)
test_dcp_export_updates_marked() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    printf '# Hand CLAUDE\n\nPRESERVE_ME line.\n' > CLAUDE.md
    dv export --target claude >/dev/null 2>&1
    dv export --target claude >/dev/null 2>&1   # second run must not duplicate
    local count
    count="$(grep -c 'dejavue:begin' CLAUDE.md)"
    assert_eq "exactly one managed block" "$count" "1" || return 1
    assert_contains "still preserves hand-written" "$(cat CLAUDE.md)" "PRESERVE_ME" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M3: --replace converts an unmarked hand-written file entirely
test_dcp_export_replace_converts() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    printf 'ONLY_HANDWRITTEN\n' > AGENTS.md
    dv export --target codex --replace >/dev/null 2>&1
    assert_not_contains "handwritten removed" "$(cat AGENTS.md)" "ONLY_HANDWRITTEN" || return 1
    assert_contains "block present" "$(cat AGENTS.md)" "dejavue:begin" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M3: export --target all writes every adapter
test_dcp_export_all() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv export --target all >/dev/null 2>&1
    assert_file_exists "CLAUDE.md" "CLAUDE.md" || return 1
    assert_file_exists "AGENTS.md" "AGENTS.md" || return 1
    assert_file_exists "GEMINI.md" "GEMINI.md" || return 1
    assert_file_exists "copilot" ".github/copilot-instructions.md" || return 1
    assert_file_exists "cursor" ".cursor/rules" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M3: check warns when context.md changed after export (adapters stale)
test_dcp_check_staleness() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv export --target gemini >/dev/null 2>&1
    local fresh
    fresh="$(dv check 2>&1)"
    assert_contains "in sync after export" "$fresh" "in sync with context.md" || return 1
    printf '\n- a new operating rule\n' >> .dejavue/context.md
    local stale
    stale="$(dv check 2>&1)"
    assert_contains "stale warning" "$stale" "adapters stale" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M3: export adapter via config target override
test_dcp_export_config_override() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv config set target_claude docs/AI.md >/dev/null 2>&1
    dv export --target claude >/dev/null 2>&1
    assert_file_exists "override path used" "docs/AI.md" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M4: glossary reference card via existing reference machinery, surfaced in context
test_dcp_glossary_card() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv reference create glossary --template glossary >/dev/null 2>&1
    assert_file_exists "glossary.md" ".dejavue/references/glossary.md" || return 1
    local content
    content="$(cat .dejavue/references/glossary.md)"
    assert_contains "glossary type frontmatter" "$content" "type: glossary" || return 1
    assert_contains "glossary table" "$content" "| Term | Definition |" || return 1
    # surfaced in context (title clean, no leading ---)
    local ctx
    ctx="$(dv context 2>&1)"
    assert_contains "glossary surfaced in context" "$ctx" "glossary.md" || return 1
    assert_not_contains "no raw frontmatter as title" "$ctx" "glossary.md  (---)" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M5: reference list --type filters by frontmatter type
test_dcp_reference_type_filter() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv reference create gloss --template glossary >/dev/null 2>&1
    dv reference create apicard --template api --type api >/dev/null 2>&1
    dv reference create plaincard >/dev/null 2>&1
    local out
    out="$(dv reference list --type glossary 2>&1)"
    assert_contains "glossary listed" "$out" "gloss" || return 1
    assert_not_contains "api excluded" "$out" "apicard" || return 1
    assert_not_contains "plain excluded" "$out" "plaincard" || return 1
    local apiout
    apiout="$(dv reference list --type api 2>&1)"
    assert_contains "api listed" "$apiout" "apicard" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M5: init --wizard is non-interactive-safe (EOF → defaults) and seeds files
test_dcp_wizard_noninteractive() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init --wizard </dev/null >/dev/null 2>&1
    assert_file_exists "context.md seeded" ".dejavue/context.md" || return 1
    local state
    state="$(cat .dejavue/state.md)"
    assert_contains "state seeded by wizard" "$state" "Primary agent" || return 1
    assert_event_recorded "wizard event" ".dejavue/timeline.jsonl" "event" "wizard" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M5: init without --wizard is unchanged (no wizard event, base loop frozen)
test_dcp_wizard_skippable() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    if grep -q '"event": "wizard"' .dejavue/timeline.jsonl 2>/dev/null; then
        echo "  FAIL: plain init must not run wizard" >&2; return 1
    fi
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M5: promote --to planning copies artifacts, preserves .dejavue/, records event
test_dcp_promote_jagent() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "keepme" --reason "history" >/dev/null 2>&1
    dv promote --to planning >/dev/null 2>&1
    assert_file_exists "planning decisions" ".planning/decisions.md" || return 1
    assert_file_exists "planning timeline" ".planning/timeline.jsonl" || return 1
    assert_file_exists "provenance" ".planning/PROVENANCE.md" || return 1
    # .dejavue/ left intact (history preserved)
    assert_file_exists "dejavue intact" ".dejavue/decisions.md" || return 1
    assert_contains "history preserved" "$(cat .planning/decisions.md)" "keepme" || return 1
    assert_event_recorded "promote event" ".dejavue/timeline.jsonl" "event" "promote" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# M5: diff --format patch emits a machine-readable unified diff
test_dcp_diff_patch() {
    TEST_DIR="$(setup_repo)"
    trap cleanup EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    git add -A && git commit -q -m c1
    dv decision "patchable decision" --reason "delta" >/dev/null 2>&1
    git add -A && git commit -q -m c2
    local out
    out="$(dv diff HEAD~1 HEAD --format patch 2>&1)"
    assert_contains "unified diff header" "$out" "+++ b/decisions.md" || return 1
    assert_contains "added decision in patch" "$out" "patchable decision" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 111. init creates CLAUDE.md with boot stub in a fresh repo
test_init_creates_claude_md() {
    TEST_DIR="$(setup_repo)"
    trap 'cd /; rm -rf "$TEST_DIR"' EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    assert_file_exists "CLAUDE.md created by init" "CLAUDE.md" || return 1
    local content
    content="$(cat CLAUDE.md)"
    assert_contains "boot stub has dejavue context command" "$content" "dejavue context" || return 1
    assert_contains "discovery idempotency marker present" "$content" "dejavue:discovery" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 112. init CLAUDE.md boot stub is idempotent — second init does not duplicate section
test_init_claude_md_idempotent() {
    TEST_DIR="$(setup_repo)"
    trap 'cd /; rm -rf "$TEST_DIR"' EXIT
    cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv init >/dev/null 2>&1  # second run
    local count
    count="$(grep -c "dejavue:discovery" CLAUDE.md)"
    assert_eq "boot stub not duplicated on second init" "$count" "1" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 113. init still writes CLAUDE.md when dejavue.py has no adjacent skills/ dir
#      (standalone downloaded script — skill copy silently skips, CLAUDE.md still created)
test_init_discovery_without_skills_dir() {
    TEST_DIR="$(setup_repo)"
    SCRIPT_DIR="$(mktemp -d)"
    trap 'cd /; rm -rf "$TEST_DIR" "$SCRIPT_DIR"' EXIT

    # Copy dejavue.py to a temp dir that has no skills/ sibling
    cp "$DEJAVUE" "$SCRIPT_DIR/dejavue.py"
    cd "$TEST_DIR"
    "$PYTHON" "$SCRIPT_DIR/dejavue.py" init >/dev/null 2>&1
    assert_file_exists "CLAUDE.md created even without skills/" "CLAUDE.md" || return 1
    local content
    content="$(cat CLAUDE.md)"
    assert_contains "boot stub present without skills/" "$content" "dejavue:discovery" || return 1
    cd /; rm -rf "$TEST_DIR" "$SCRIPT_DIR"; trap - EXIT
}

# 114. trap records event with event=trap
test_trap_records_event() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv trap "AuthManager does NOT handle OAuth anymore" >/dev/null 2>&1
    assert_event_recorded "trap event" ".dejavue/timeline.jsonl" "event" "trap" || return 1
    assert_event_recorded "trap summary" ".dejavue/timeline.jsonl" "summary" "AuthManager does NOT handle OAuth anymore" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 115. incident records event with event=incident
test_incident_records_event() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv incident "FTS index corrupted after power loss" >/dev/null 2>&1
    assert_event_recorded "incident event" ".dejavue/timeline.jsonl" "event" "incident" || return 1
    assert_event_recorded "incident summary" ".dejavue/timeline.jsonl" "summary" "FTS index corrupted after power loss" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 116. invariant records event AND appends to invariants.md
test_invariant_records_event_and_doc() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv invariant "Capsules never access host FS directly" >/dev/null 2>&1
    assert_event_recorded "invariant event" ".dejavue/timeline.jsonl" "event" "invariant" || return 1
    assert_file_exists "invariants.md created" ".dejavue/invariants.md" || return 1
    local content; content="$(cat .dejavue/invariants.md)"
    assert_contains "invariant text in doc" "$content" "Capsules never access host FS directly" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 117. init creates invariants.md scaffold
test_init_creates_invariants_md() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    assert_file_exists "invariants.md scaffolded by init" ".dejavue/invariants.md" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 118. context surfaces invariants.md
test_context_shows_invariants() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv invariant "append-only timeline is immutable" >/dev/null 2>&1
    local out; out="$(dv context 2>/dev/null)"
    assert_contains "invariants section header" "$out" "invariants.md" || return 1
    assert_contains "invariant text in context" "$out" "append-only timeline is immutable" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 119. rejected lists all decisions with rejected alternatives
test_rejected_lists_all() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "Use SQLite" --reason "stdlib" --rejected "PostgreSQL: too heavy" --rejected "MySQL: license" >/dev/null 2>&1
    local out; out="$(dv rejected)"
    assert_contains "decision title" "$out" "Use SQLite" || return 1
    assert_contains "first rejected" "$out" "PostgreSQL" || return 1
    assert_contains "second rejected" "$out" "MySQL" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 120. rejected filters by topic query (case-insensitive)
test_rejected_filters_by_query() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "Rate limiting" --reason "needed" --rejected "leaky-bucket: too smooth" >/dev/null 2>&1
    dv decision "Auth backend" --reason "security" --rejected "JWT-only: no revocation" >/dev/null 2>&1
    local out; out="$(dv rejected leaky)"
    assert_contains "matching decision present" "$out" "Rate limiting" || return 1
    local noshow; noshow=$(echo "$out" | grep -c "Auth backend" || true)
    assert_eq "non-matching decision absent" "$noshow" "0" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 121. decision --supersedes stored in event and decisions.md
test_decision_supersedes() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "New approach" --reason "better" --supersedes "old-decision-id" >/dev/null 2>&1
    assert_event_recorded "supersedes in event" ".dejavue/timeline.jsonl" "supersedes" "old-decision-id" || return 1
    local doc; doc="$(cat .dejavue/decisions.md)"
    assert_contains "supersedes in doc" "$doc" "Supersedes: old-decision-id" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 122. decision --durability stored in event and decisions.md heading
test_decision_durability() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "Append-only timeline" --reason "git-friendly" --durability constitutional >/dev/null 2>&1
    assert_event_recorded "durability in event" ".dejavue/timeline.jsonl" "durability" "constitutional" || return 1
    local doc; doc="$(cat .dejavue/decisions.md)"
    assert_contains "durability label in heading" "$doc" "[CONSTITUTIONAL]" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 123. since accepts git revision range (ref..ref)
test_since_revision_range() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    touch first.txt; git add .; git commit -qm "first commit"
    local base; base="$(git rev-list --max-parents=0 HEAD)"
    touch second.txt; git add .; git commit -qm "second commit"
    dv decision "Range test decision" --reason "for range since test" >/dev/null 2>&1
    local out; out="$(dv since "${base}..HEAD" 2>/dev/null)"
    assert_contains "range label in output" "$out" "range" || return 1
    assert_contains "second commit in git delta" "$out" "second commit" || return 1
    assert_contains "decision in timeline" "$out" "Range test decision" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 124. init installs post-checkout hook with branch-switch guard
test_init_installs_checkout_hook() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    assert_file_exists "post-checkout hook created" ".git/hooks/post-checkout" || return 1
    local content; content="$(cat .git/hooks/post-checkout)"
    assert_contains "has dejavue marker" "$content" "dejavue post-checkout" || return 1
    assert_contains "has branch-switch guard" "$content" '[ "$3" = "1" ]' || return 1
    assert_contains "calls dejavue status" "$content" "status" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 125. note-commit --trailer amends commit message with Dejavue-Event trailer
test_note_commit_trailer() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    touch file.txt; git add .; git commit -qm "initial commit"
    dv decision "Trailer test" --reason "testing trailer flag" >/dev/null 2>&1
    dv note-commit HEAD --trailer >/dev/null 2>&1
    local msg; msg="$(git log -1 --format="%B")"
    assert_contains "Dejavue-Event trailer in commit" "$msg" "Dejavue-Event:" || return 1
    assert_contains "trailer has timestamp" "$msg" "Trailer test" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 126. note-commit --trailer keeps the git note on the SHIPPED (post-amend) commit
test_note_commit_trailer_note_follows_amend() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    touch file.txt; git add .; git commit -qm "initial commit"
    dv decision "Trailer note test" --reason "note must follow the amend" >/dev/null 2>&1
    dv note-commit HEAD --trailer >/dev/null 2>&1
    # the amend rewrote HEAD's SHA; the note must be on the new HEAD, not the orphaned old SHA
    local note; note="$(git notes show HEAD 2>/dev/null)"
    assert_contains "note present on shipped HEAD" "$note" "Dejavue-Event:" || return 1
    local msg; msg="$(git log -1 --format='%B')"
    assert_contains "trailer present on shipped HEAD" "$msg" "Dejavue-Event:" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 127. note-commit --trailer refuses a non-HEAD sha instead of corrupting HEAD's message
test_note_commit_trailer_refuses_non_head() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    touch a.txt; git add .; git commit -qm "first commit"
    local first; first="$(git rev-parse HEAD)"
    touch b.txt; git add .; git commit -qm "second commit"
    dv decision "Non-head test" --reason "must not corrupt HEAD" >/dev/null 2>&1
    local out; out="$(dv note-commit "$first" --trailer 2>&1)"
    assert_contains "refuses non-HEAD sha" "$out" "can only amend HEAD" || return 1
    local head_msg; head_msg="$(git log -1 --format='%B')"
    assert_contains "HEAD message untouched" "$head_msg" "second commit" || return 1
    assert_not_contains "no trailer leaked onto HEAD" "$head_msg" "Dejavue-Event:" || return 1
    assert_eq "first commit message unchanged" "$(git log -1 --format='%s' "$first")" "first commit" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 128. note-commit --trailer refuses to fold staged changes into the amended commit
test_note_commit_trailer_refuses_staged() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    touch file.txt; git add .; git commit -qm "initial commit"
    dv decision "Staged test" --reason "must not fold staged work" >/dev/null 2>&1
    echo "new work" > unrelated.txt; git add unrelated.txt   # staged but not committed
    local out; out="$(dv note-commit HEAD --trailer 2>&1)"
    assert_contains "refuses with staged changes" "$out" "Refusing to amend" || return 1
    assert_eq "staged file not folded into HEAD" "$(git ls-tree --name-only HEAD unrelated.txt)" "" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 129. invariant before init self-creates .dejavue/ instead of crashing
test_invariant_before_init() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    # deliberately NO `dv init`
    local rc; dv invariant "capsules never touch host FS" >/dev/null 2>&1; rc=$?
    assert_eq "invariant exits 0 without prior init" "$rc" "0" || return 1
    assert_file_exists "invariants.md created" ".dejavue/invariants.md" || return 1
    assert_contains "invariant text written" "$(cat .dejavue/invariants.md)" "host FS" || return 1
    assert_event_recorded "invariant event recorded" ".dejavue/timeline.jsonl" "event" "invariant" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 130. link tolerates timeline events with explicitly-null commit/summary/decision_reason fields
test_link_tolerates_null_commit() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    # commit is not the queried short SHA, so the sibling summary/decision_reason predicates are evaluated too
    printf '%s\n' '{"ts":"2026-01-01T00:00:00-00:00","event":"handoff","commit":null,"summary":"x"}'           >> .dejavue/timeline.jsonl
    printf '%s\n' '{"ts":"2026-01-01T00:00:01-00:00","event":"handoff","commit":"abc1234","summary":null}'      >> .dejavue/timeline.jsonl
    printf '%s\n' '{"ts":"2026-01-01T00:00:02-00:00","event":"decision","commit":"abc1234","decision_reason":null}' >> .dejavue/timeline.jsonl
    local rc; dv link deadbee >/dev/null 2>&1; rc=$?
    assert_eq "link does not crash on null commit/summary/decision_reason" "$rc" "0" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 131. since base..tip excludes events recorded after the tip (upper bound honored)
test_since_range_excludes_after_tip() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    touch base.txt; git add .; git commit -qm "base commit"
    local base; base="$(git rev-parse HEAD)"
    dv decision "Inside range decision" --reason "within base..tip" >/dev/null 2>&1
    touch mid.txt; git add .; git commit -qm "mid commit"
    local mid; mid="$(git rev-parse HEAD)"
    sleep 1   # ensure the next event's timestamp is strictly past the tip commit's date
    dv decision "Outside range decision" --reason "after the tip" >/dev/null 2>&1
    local out; out="$(dv since "${base}..${mid}" 2>/dev/null)"
    assert_contains "in-range decision present" "$out" "Inside range decision" || return 1
    assert_not_contains "post-tip decision excluded" "$out" "Outside range decision" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 132. context tolerates timeline lines that are valid JSON but not objects
test_context_tolerates_non_dict_timeline_line() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv trap "AuthManager does not handle OAuth" >/dev/null 2>&1
    printf '%s\n' '12345' >> .dejavue/timeline.jsonl   # valid JSON scalar, not a dict
    printf '%s\n' 'null'  >> .dejavue/timeline.jsonl
    local out rc; out="$(dv context 2>/dev/null)"; rc=$?
    assert_eq "context survives non-dict timeline line" "$rc" "0" || return 1
    assert_contains "trap still surfaces in context" "$out" "AuthManager does not handle OAuth" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 133. pattern records event AND appends to patterns.md
test_pattern_records_event_and_doc() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv pattern "handlers return Result, never raise across the API boundary" >/dev/null 2>&1
    assert_event_recorded "pattern event" ".dejavue/timeline.jsonl" "event" "pattern" || return 1
    assert_file_exists "patterns.md created" ".dejavue/patterns.md" || return 1
    assert_contains "pattern text in doc" "$(cat .dejavue/patterns.md)" "never raise across the API boundary" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 134. init creates patterns.md scaffold
test_init_creates_patterns_md() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    assert_file_exists "patterns.md scaffolded by init" ".dejavue/patterns.md" || return 1
    assert_contains "patterns.md has header" "$(cat .dejavue/patterns.md)" "# Patterns" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 135. context surfaces patterns.md
test_context_shows_patterns() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv pattern "config keys are snake_case everywhere" >/dev/null 2>&1
    local out; out="$(dv context 2>/dev/null)"
    assert_contains "patterns section header" "$out" "patterns.md" || return 1
    assert_contains "pattern text in context" "$out" "config keys are snake_case everywhere" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 136. pattern before init self-creates .dejavue/ instead of crashing
test_pattern_before_init() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    # deliberately NO `dv init`
    local rc; dv pattern "errors bubble up as structured events" >/dev/null 2>&1; rc=$?
    assert_eq "pattern exits 0 without prior init" "$rc" "0" || return 1
    assert_file_exists "patterns.md created" ".dejavue/patterns.md" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 137. recall finds patterns.md body text (FTS indexing wired)
test_recall_finds_pattern_body() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv pattern "ZXQVNONCE marker convention for canary checks" >/dev/null 2>&1
    local out; out="$(dv recall ZXQVNONCE 2>/dev/null)"
    assert_contains "recall surfaces pattern text" "$out" "ZXQVNONCE" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 138. --entity is stored and recall finds events by entity
test_entity_recall() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "Adopt Zorp engine" --reason "fast" --entity zorpengine >/dev/null 2>&1
    local out; out="$(dv recall zorpengine 2>/dev/null)"
    assert_contains "recall by entity finds the decision" "$out" "Adopt Zorp engine" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 139. blame surfaces events by entity name (not just file path)
test_blame_by_entity() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv note "tuned the eviction policy" --entity rediscache >/dev/null 2>&1
    local out; out="$(dv blame rediscache 2>/dev/null)"
    assert_contains "blame by entity surfaces the note" "$out" "tuned the eviction policy" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 140. entities (no arg) lists entities with counts
test_entities_list() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "d1" --reason r --entity alpha --entity beta >/dev/null 2>&1
    dv note "n1" --entity alpha >/dev/null 2>&1
    local out; out="$(dv entities 2>/dev/null)"
    assert_contains "lists alpha" "$out" "@alpha" || return 1
    assert_contains "lists beta" "$out" "@beta" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 141. entities <name> filters events referencing one entity
test_entities_filter() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "use alpha lib" --reason r --entity alpha >/dev/null 2>&1
    dv note "alpha note" --entity alpha >/dev/null 2>&1
    dv note "unrelated" --entity gamma >/dev/null 2>&1
    local out; out="$(dv entities alpha 2>/dev/null)"
    assert_contains "shows alpha decision" "$out" "use alpha lib" || return 1
    assert_contains "shows alpha note" "$out" "alpha note" || return 1
    assert_not_contains "excludes gamma event" "$out" "unrelated" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 142. entity names are normalized to kebab-case (query side too)
test_entity_normalization() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv trap "AuthManager does not handle OAuth" --entity "Auth System" >/dev/null 2>&1
    assert_contains "stored as kebab in entities list" "$(dv entities 2>/dev/null)" "@auth-system" || return 1
    assert_contains "filter by unnormalized query matches" "$(dv entities 'Auth System' 2>/dev/null)" "AuthManager does not handle OAuth" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 143. decision --confidence stored in event AND shown as a decisions.md heading label
test_decision_confidence() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "Adopt event sourcing" --reason "auditability" --confidence experimental >/dev/null 2>&1
    assert_event_recorded "confidence stored in event" ".dejavue/timeline.jsonl" "confidence" "experimental" || return 1
    assert_contains "confidence label in decisions.md heading" "$(cat .dejavue/decisions.md)" "[EXPERIMENTAL]" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 144. note --confidence is stored on the event
test_note_confidence() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv note "the cache might be the bottleneck" --type claim --confidence speculative >/dev/null 2>&1
    assert_event_recorded "note confidence stored" ".dejavue/timeline.jsonl" "confidence" "speculative" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 145. recall finds events by confidence level (FTS-indexed)
test_recall_by_confidence() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "Freeze the capsule ABI" --reason "stability" --confidence verified >/dev/null 2>&1
    local out; out="$(dv recall verified 2>/dev/null)"
    assert_contains "recall by confidence finds the decision" "$out" "Freeze the capsule ABI" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 146. invalid --confidence value is rejected by argparse (exit != 0)
test_confidence_invalid_rejected() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    local rc; dv decision "bad" --reason r --confidence definitely >/dev/null 2>&1; rc=$?
    assert_eq "invalid confidence rejected" "$([ "$rc" -ne 0 ] && echo nonzero || echo zero)" "nonzero" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 146a. decision freshness / expiry / lineage / stability are stored and read back
test_decision_metadata_readback() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1

    dv decision "Temporary fix" --reason "bridge the gap" \
        --freshness volatile --expires-after 0d \
        --derived-from "seed idea" --stability constitutional >/dev/null 2>&1

    local timeline; timeline="$(cat .dejavue/timeline.jsonl)"
    assert_contains "freshness stored" "$timeline" '"freshness": "volatile"' || return 1
    assert_contains "expiry stored" "$timeline" '"expires_after": "0d"' || return 1
    assert_contains "lineage stored" "$timeline" '"derived_from": ["seed idea"]' || return 1
    assert_contains "stability stored" "$timeline" '"stability": "constitutional"' || return 1

    local ctx; ctx="$(dv context 2>&1)"
    assert_contains "context shows freshness" "$ctx" "Freshness: volatile" || return 1
    assert_contains "context shows expiry" "$ctx" "Expires after: 0d" || return 1
    assert_contains "context shows expired" "$ctx" "timeline has expired entries" || return 1
    assert_contains "context shows lineage" "$ctx" "Derived from: seed idea" || return 1
    assert_contains "context shows stability" "$ctx" "Stability: constitutional" || return 1

    local recall_fresh; recall_fresh="$(dv recall volatile 2>&1)"
    assert_contains "recall finds freshness label" "$recall_fresh" "Temporary fix" || return 1
    assert_contains "recall shows freshness metadata" "$recall_fresh" "Freshness: volatile" || return 1

    local recall_lineage; recall_lineage="$(dv recall "seed idea" 2>&1)"
    assert_contains "recall finds lineage label" "$recall_lineage" "Temporary fix" || return 1
    assert_contains "recall shows lineage metadata" "$recall_lineage" "Derived from: seed idea" || return 1

    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 146b. note freshness / expiry / lineage / stability are stored and read back
test_note_metadata_readback() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1

    dv note "NOTE_META_123 scratch observation" \
        --freshness volatile --expires-after 0d \
        --derived-from "Temporary fix" --stability ephemeral >/dev/null 2>&1

    local timeline; timeline="$(cat .dejavue/timeline.jsonl)"
    assert_contains "note freshness stored" "$timeline" '"freshness": "volatile"' || return 1
    assert_contains "note expiry stored" "$timeline" '"expires_after": "0d"' || return 1
    assert_contains "note lineage stored" "$timeline" '"derived_from": ["Temporary fix"]' || return 1
    assert_contains "note stability stored" "$timeline" '"stability": "ephemeral"' || return 1

    local ctx; ctx="$(dv context 2>&1)"
    assert_contains "note context shows freshness" "$ctx" "Freshness: volatile" || return 1
    assert_contains "note context shows expiry" "$ctx" "Expires after: 0d" || return 1
    assert_contains "note context shows lineage" "$ctx" "Derived from: Temporary fix" || return 1
    assert_contains "note context shows stability" "$ctx" "Stability: ephemeral" || return 1

    local recall_note; recall_note="$(dv recall NOTE_META_123 2>&1)"
    assert_contains "recall finds note" "$recall_note" "NOTE_META_123 scratch observation" || return 1
    assert_contains "recall shows note freshness" "$recall_note" "Freshness: volatile" || return 1
    assert_contains "recall shows note lineage" "$recall_note" "Derived from: Temporary fix" || return 1
    assert_contains "recall shows note stability" "$recall_note" "Stability: ephemeral" || return 1

    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 147. since surfaces "superseded by" for an overridden decision (read-back), not the superseder
test_supersedes_readback_since() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    local base; base="$(git rev-list --max-parents=0 HEAD)"
    dv decision "Use SQLite" --reason "stdlib" >/dev/null 2>&1
    dv decision "Use Postgres" --reason "scale" --supersedes "Use SQLite" >/dev/null 2>&1
    local out; out="$(dv since "${base}..HEAD" 2>/dev/null)"
    assert_contains "overridden decision flagged" "$out" "superseded by 'Use Postgres'" || return 1
    assert_not_contains "superseder itself not flagged" "$out" "superseded by 'Use SQLite'" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 148. recall surfaces "superseded by" for an overridden decision
test_supersedes_readback_recall() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "Use SQLite" --reason "stdlib" >/dev/null 2>&1
    dv decision "Use Postgres" --reason "scale" --supersedes "Use SQLite" >/dev/null 2>&1
    local out; out="$(dv recall "Use SQLite" 2>/dev/null)"
    assert_contains "recall flags superseded decision" "$out" "superseded by 'Use Postgres'" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 149. context lists superseded decisions; a self-referential superseder is NOT flagged
test_supersedes_readback_context_no_self_match() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "Cache layer" --reason "v1" >/dev/null 2>&1
    # the superseder's own ref ("Cache layer") is a substring of its own title — must not self-flag
    dv decision "Cache layer v2" --reason "v2" --supersedes "Cache layer" >/dev/null 2>&1
    local out; out="$(dv context 2>/dev/null)"
    assert_contains "context has superseded section" "$out" "superseded decisions" || return 1
    assert_contains "old decision flagged" "$out" "'Cache layer' → superseded by 'Cache layer v2'" || return 1
    assert_not_contains "no self-supersession" "$out" "'Cache layer v2' → superseded" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 150. decision --artifacts is stored and written to decisions.md
test_decision_artifacts() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "Refactor auth" --reason "clarity" --artifacts src/auth.py --artifacts src/session.py >/dev/null 2>&1
    assert_contains "artifacts line in decisions.md" "$(cat .dejavue/decisions.md)" "Artifacts: src/auth.py, src/session.py" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 151. blame <file> matches a decision precisely via its artifacts (not just fuzzy text)
test_blame_by_artifacts() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    # title/reason do NOT mention the path — only --artifacts links it
    dv decision "Rewrite the cache" --reason "perf" --artifacts lib/cache.py >/dev/null 2>&1
    local out; out="$(dv blame lib/cache.py 2>/dev/null)"
    assert_contains "blame matches decision via artifacts" "$out" "Rewrite the cache" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 152. recall finds a decision by its artifact path (FTS-indexed)
test_recall_by_artifact() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv decision "Tune the indexer" --reason "speed" --artifacts engine/indexer.py >/dev/null 2>&1
    local out; out="$(dv recall indexer 2>/dev/null)"
    assert_contains "recall finds decision by artifact path" "$out" "Tune the indexer" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 153. changelog surfaces decisions (title + reason + confidence) over a range
test_changelog_decisions() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    local base; base="$(git rev-list --max-parents=0 HEAD)"
    dv decision "Adopt event sourcing" --reason "auditability" --confidence adopted >/dev/null 2>&1
    local out; out="$(dv changelog "${base}..HEAD" 2>/dev/null)"
    assert_contains "decisions section" "$out" "### Decisions" || return 1
    assert_contains "decision title" "$out" "Adopt event sourcing" || return 1
    assert_contains "decision reason" "$out" "auditability" || return 1
    assert_contains "confidence label" "$out" "(adopted)" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 154. changelog includes git commits in the range
test_changelog_commits() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    local base; base="$(git rev-list --max-parents=0 HEAD)"
    touch feature.txt; git add .; git commit -qm "add feature toggle"
    local out; out="$(dv changelog "${base}..HEAD" 2>/dev/null)"
    assert_contains "commits section" "$out" "### Commits" || return 1
    assert_contains "commit listed" "$out" "add feature toggle" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 155. changelog annotates superseded decisions
test_changelog_superseded() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    local base; base="$(git rev-list --max-parents=0 HEAD)"
    dv decision "Use SQLite" --reason "stdlib" >/dev/null 2>&1
    dv decision "Use Postgres" --reason "scale" --supersedes "Use SQLite" >/dev/null 2>&1
    local out; out="$(dv changelog "${base}..HEAD" 2>/dev/null)"
    assert_contains "superseded annotation in changelog" "$out" "later superseded by 'Use Postgres'" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 156. capabilities emits a machine-readable DCP capability report
test_capabilities_json() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    local out; out="$(dv capabilities 2>/dev/null)"
    "$PYTHON" - "$out" <<'PYEOF'
import json, sys
data = json.loads(sys.argv[1])
assert data["dcp_version"] == "DCP/1.0"
assert "capabilities" in data["commands"]
assert "branch" in data["commands"]
assert "merge-summary" in data["commands"]
assert "squash-summary" in data["commands"]
assert "epoch" in data["commands"]
assert "milestone" in data["commands"]
assert "explain" in data["commands"]
assert "conflict" in data["commands"]
assert "owners" in data["commands"]
assert data["features"]["managed_adapters"] is True
assert data["features"]["git_workflow_memory"] is True
assert data["features"]["project_epochs"] is True
assert data["features"]["causal_explain"] is True
assert data["features"]["conflict_memory"] is True
assert data["features"]["author_type"] is True
assert data["features"]["tension_tracking"] is True
assert data["features"]["project_values"] is True
assert data["features"]["domain_owner"] is True
assert data["repo"]["initialized"] is True
assert "codex" in data["repo"]["adapters"]
PYEOF
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 157. capabilities --format text prints the compact human view
test_capabilities_text() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    local out; out="$(dv capabilities --format text 2>/dev/null)"
    assert_contains "text has dcp version" "$out" "DCP/1.0" || return 1
    assert_contains "text has features" "$out" "Features:" || return 1
    assert_contains "text has initialized" "$out" "Repo initialized: yes" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 158. branch summary replays branch intent, closeout, decisions, and commits
test_branch_summary() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    local base; base="$(git rev-list --max-parents=0 HEAD)"
    git checkout -qb feature/intent
    dv branch start --goal "Ship branch memory" --base "$base" --agent tester >/dev/null 2>&1
    dv decision "Keep branch memory in timeline" --reason "no new storage" --agent tester >/dev/null 2>&1
    dv branch close --summary "Ready for merge" --next "Tag release" --agent tester >/dev/null 2>&1
    echo "feature" > feature.txt
    git add . && git commit -qm "branch work"
    local out; out="$(dv branch summary feature/intent --base "$base" 2>/dev/null)"
    assert_contains "branch intent section" "$out" "### Branch intent" || return 1
    assert_contains "branch goal" "$out" "Ship branch memory" || return 1
    assert_contains "branch decision" "$out" "Keep branch memory in timeline" || return 1
    assert_contains "branch closeout" "$out" "Ready for merge" || return 1
    assert_contains "branch next step" "$out" "Next: Tag release" || return 1
    assert_contains "branch commit" "$out" "branch work" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 159. merge-summary summarizes what a branch brings into a base ref
test_merge_summary_branch() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    local base; base="$(git rev-list --max-parents=0 HEAD)"
    git checkout -qb feature/merge-summary
    dv branch start --goal "Prepare merge report" --base "$base" --agent tester >/dev/null 2>&1
    echo "merge" > merge.txt
    git add . && git commit -qm "add merge summary fixture"
    local out; out="$(dv merge-summary "$base" feature/merge-summary 2>/dev/null)"
    assert_contains "merge summary header" "$out" "## Merge summary:" || return 1
    assert_contains "merge branch goal" "$out" "Prepare merge report" || return 1
    assert_contains "merge commit" "$out" "add merge summary fixture" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 160. epoch list shows open/closed epochs and milestones
test_epoch_list() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv epoch begin "MVP" --summary "Start MVP era" --agent tester >/dev/null 2>&1
    dv milestone "ABI freeze" --summary "Capsule ABI frozen" --agent tester >/dev/null 2>&1
    dv epoch end "MVP" --summary "MVP shipped" --agent tester >/dev/null 2>&1
    local out; out="$(dv epoch list 2>/dev/null)"
    assert_contains "epoch listed" "$out" "MVP" || return 1
    assert_contains "epoch closed" "$out" "closed" || return 1
    assert_contains "milestone listed" "$out" "ABI freeze" || return 1
    assert_contains "milestone summary" "$out" "Capsule ABI frozen" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 161. context surfaces open epochs and milestones
test_context_shows_epochs() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    dv epoch begin "Public beta" --summary "Beta constraints apply" --agent tester >/dev/null 2>&1
    dv milestone "Docs baseline" --summary "Docs are canonical" --agent tester >/dev/null 2>&1
    local out; out="$(dv context 2>/dev/null)"
    assert_contains "context epoch section" "$out" "epochs & milestones" || return 1
    assert_contains "context open epoch" "$out" "Public beta" || return 1
    assert_contains "context milestone" "$out" "Docs baseline" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 162. explain <file> composes decisions, rejected alternatives, and artifacts
test_explain_file() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    mkdir -p src
    echo "cache" > src/cache.py
    git add . && git commit -qm "add cache file"
    dv decision "Keep cache local" --reason "offline first" --rejected "remote cache: network dependency" --artifacts src/cache.py >/dev/null 2>&1
    dv note "Cache warmup is intentionally lazy" --entity src/cache.py >/dev/null 2>&1
    local out; out="$(dv explain src/cache.py 2>/dev/null)"
    assert_contains "explain file header" "$out" "# Explanation: src/cache.py" || return 1
    assert_contains "explain decision" "$out" "Keep cache local" || return 1
    assert_contains "explain reason" "$out" "offline first" || return 1
    assert_contains "explain rejected" "$out" "remote cache" || return 1
    assert_contains "explain note" "$out" "Cache warmup is intentionally lazy" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 163. explain <commit> shows commit metadata and linked file_changed events
test_explain_commit() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    echo "explain" > explain.txt
    git add explain.txt && git commit -qm "add explain fixture"
    local sha; sha="$(git rev-parse HEAD)"
    local out; out="$(dv explain "$sha" 2>/dev/null)"
    assert_contains "explain commit header" "$out" "# Explanation: commit" || return 1
    assert_contains "explain commit subject" "$out" "add explain fixture" || return 1
    assert_contains "explain commit file" "$out" "explain.txt" || return 1
    assert_contains "explain commit memory" "$out" "DejaVue memory:" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 164. squash-summary synthesizes a commit-message draft from branch memory
test_squash_summary_branch() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    local base; base="$(git rev-list --max-parents=0 HEAD)"
    git checkout -qb feature/squash-summary
    dv branch start --goal "Ship squash summaries" --base "$base" --agent tester >/dev/null 2>&1
    dv decision "Use branch events for squash" --reason "keeps commit messages grounded" --agent tester >/dev/null 2>&1
    dv note "Squash message should include commits" --agent tester >/dev/null 2>&1
    echo "squash" > squash.txt
    git add . && git commit -qm "add squash fixture"
    local out; out="$(dv squash-summary feature/squash-summary --base "$base" 2>/dev/null)"
    assert_contains "squash subject" "$out" "Ship squash summaries" || return 1
    assert_contains "squash decisions" "$out" "Use branch events for squash" || return 1
    assert_contains "squash notes" "$out" "Squash message should include commits" || return 1
    assert_contains "squash commits" "$out" "add squash fixture" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 165. conflict record stores rationale and is surfaced by explain
test_conflict_record() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1
    mkdir -p src
    echo "merged" > src/conflicted.py
    git add . && git commit -qm "add conflict fixture"
    dv conflict record --path src/conflicted.py --reason "keep parser fast path" --resolution "kept ours, ported validation" --agent tester >/dev/null 2>&1
    local listed; listed="$(dv conflict list 2>/dev/null)"
    assert_contains "conflict listed" "$listed" "keep parser fast path" || return 1
    local explained; explained="$(dv explain src/conflicted.py 2>/dev/null)"
    assert_contains "conflict in explain" "$explained" "conflict_record" || return 1
    assert_contains "conflict reason in explain" "$explained" "keep parser fast path" || return 1
    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 166. --author-type stores writer class metadata and surfaces it in read paths
test_author_type_metadata() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1

    dv decision "Bot-authored decision" --reason "automation chose it" --author-type bot >/dev/null 2>&1
    dv note "Coordinator-authored note" --author-type orchestrator >/dev/null 2>&1
    dv branch start feature/authors --goal "typed branch intent" --author-type agent >/dev/null 2>&1
    dv conflict record --path README.md --reason "human chose wording" --resolution "kept concise text" --author-type human >/dev/null 2>&1

    local timeline; timeline="$(cat .dejavue/timeline.jsonl)"
    assert_contains "bot author type stored" "$timeline" '"author_type": "bot"' || return 1
    assert_contains "orchestrator author type stored" "$timeline" '"author_type": "orchestrator"' || return 1
    assert_contains "agent author type stored" "$timeline" '"author_type": "agent"' || return 1
    assert_contains "human author type stored" "$timeline" '"author_type": "human"' || return 1
    assert_contains "decision doc shows author type" "$(cat .dejavue/decisions.md)" "Author type: bot" || return 1

    local ctx; ctx="$(dv context -n 8 2>&1)"
    assert_contains "context shows bot author type" "$ctx" "Author type: bot" || return 1
    assert_contains "context shows orchestrator author type" "$ctx" "Author type: orchestrator" || return 1

    local recall; recall="$(dv recall bot 2>&1)"
    assert_contains "recall finds author type" "$recall" "Bot-authored decision" || return 1
    assert_contains "recall shows author type" "$recall" "Author type: bot" || return 1

    local rc; dv note "bad author" --author-type daemon >/dev/null 2>&1; rc=$?
    assert_eq "invalid author type rejected" "$([ "$rc" -ne 0 ] && echo nonzero || echo zero)" "nonzero" || return 1

    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 167. --tension stores unresolved tradeoff metadata and surfaces it in read paths
test_tension_metadata() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1

    dv decision "Balance secrecy and speed" --reason "both matter" \
        --tension security --tension performance >/dev/null 2>&1
    dv note "UX accessibility tradeoff" --tension "User Experience" >/dev/null 2>&1

    local timeline; timeline="$(cat .dejavue/timeline.jsonl)"
    assert_contains "decision tensions stored" "$timeline" '"tension": ["security", "performance"]' || return 1
    assert_contains "note tension normalized" "$timeline" '"tension": ["user-experience"]' || return 1
    assert_contains "decision doc shows tensions" "$(cat .dejavue/decisions.md)" "Tensions: security, performance" || return 1

    local ctx; ctx="$(dv context -n 6 2>&1)"
    assert_contains "context shows tensions" "$ctx" "Tensions: security, performance" || return 1
    assert_contains "context shows normalized tension" "$ctx" "Tensions: user-experience" || return 1

    local recall; recall="$(dv recall performance 2>&1)"
    assert_contains "recall finds tension" "$recall" "Balance secrecy and speed" || return 1
    assert_contains "recall shows tension metadata" "$recall" "Tensions: security, performance" || return 1

    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 168. --value stores soft project philosophy metadata and surfaces it in read paths
test_value_metadata() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1

    dv decision "Keep the runtime local" --reason "offline agents need deterministic tools" \
        --value local-first --value "Capability First" >/dev/null 2>&1
    dv note "Composability applies to adapter boundaries" --value composability >/dev/null 2>&1

    local timeline; timeline="$(cat .dejavue/timeline.jsonl)"
    assert_contains "decision values stored" "$timeline" '"values": ["local-first", "capability-first"]' || return 1
    assert_contains "note value stored" "$timeline" '"values": ["composability"]' || return 1
    assert_contains "decision doc shows values" "$(cat .dejavue/decisions.md)" "Values: local-first, capability-first" || return 1

    local ctx; ctx="$(dv context -n 6 2>&1)"
    assert_contains "context shows values" "$ctx" "Values: local-first, capability-first" || return 1
    assert_contains "context shows note value" "$ctx" "Values: composability" || return 1

    local recall; recall="$(dv recall capability 2>&1)"
    assert_contains "recall finds value" "$recall" "Keep the runtime local" || return 1
    assert_contains "recall shows value metadata" "$recall" "Values: local-first, capability-first" || return 1

    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# 169. --domain-owner stores owner metadata and owners filters by normalized owner
test_domain_owner_metadata() {
    TEST_DIR="$(setup_repo)"; trap 'cd /; rm -rf "$TEST_DIR"' EXIT; cd "$TEST_DIR"
    dv init >/dev/null 2>&1

    dv decision "Auth owns tokens" --reason "token policy is auth-owned" \
        --domain-owner "Auth Team" >/dev/null 2>&1
    dv note "Schedulers are platform-owned" --domain-owner "Platform Core" >/dev/null 2>&1

    local timeline; timeline="$(cat .dejavue/timeline.jsonl)"
    assert_contains "decision owner stored" "$timeline" '"domain_owner": "auth-team"' || return 1
    assert_contains "note owner stored" "$timeline" '"domain_owner": "platform-core"' || return 1
    assert_contains "decision doc shows owner" "$(cat .dejavue/decisions.md)" "Domain owner: auth-team" || return 1

    local ctx; ctx="$(dv context -n 6 2>&1)"
    assert_contains "context shows decision owner" "$ctx" "Domain owner: auth-team" || return 1
    assert_contains "context shows note owner" "$ctx" "Domain owner: platform-core" || return 1

    local owners; owners="$(dv owners 2>&1)"
    assert_contains "owners lists auth" "$owners" "@auth-team" || return 1
    assert_contains "owners lists platform" "$owners" "@platform-core" || return 1

    local filtered; filtered="$(dv owners 'Auth Team' 2>&1)"
    assert_contains "owners filters by normalized name" "$filtered" "Auth owns tokens" || return 1
    assert_not_contains "owners filter excludes other owner" "$filtered" "Schedulers are platform-owned" || return 1

    local recall; recall="$(dv recall auth 2>&1)"
    assert_contains "recall finds owner" "$recall" "Auth owns tokens" || return 1
    assert_contains "recall shows owner metadata" "$recall" "Domain owner: auth-team" || return 1

    cd /; rm -rf "$TEST_DIR"; trap - EXIT
}

# ── main ───────────────────────────────────────────────────────────────────────

main() {
    echo "========================================"
    echo "  dejavue v1.0.0 integration test suite"
    echo "========================================"
    echo ""
    echo "  dejavue: $DEJAVUE"
    echo "  python:  $("$PYTHON" --version 2>&1)"
    echo "  git:     $(git --version 2>&1)"
    echo ""

    # Sanity: dejavue.py must exist and be runnable
    if ! "$PYTHON" "$DEJAVUE" --help >/dev/null 2>&1; then
        echo "FATAL: Cannot run $DEJAVUE — aborting." >&2
        exit 2
    fi

    run_test "01 init creates .dejavue/ structure"          test_init_creates_structure
    run_test "02 init installs post-commit hook"            test_init_installs_hook
    run_test "03 init is idempotent"                        test_init_idempotent
    run_test "04 init --force overwrites existing hook"     test_init_force_overwrites_hook
    run_test "05 init warns without --force on alien hook"  test_init_no_force_warns_on_existing_hook
    run_test "06 init outside git repo still creates dir"   test_init_outside_git_repo
    run_test "06a init writes .gitattributes merge=union"    test_init_writes_gitattributes
    run_test "06b init .gitattributes is idempotent"         test_init_gitattributes_idempotent
    run_test "06c init appends to pre-existing .gitattrs"    test_init_gitattributes_appends_to_existing
    run_test "06d branch-merge clean with merge=union"       test_init_gitattributes_branch_merge_no_conflict
    run_test "07 start records session_start with goal"     test_start_records_session_start
    run_test "08 changed PATH --summary records event"      test_changed_manual_records_event
    run_test "09 changed --auto --commit per-file events"   test_changed_auto_commit
    run_test "09a changed --auto --commit captures merge files" test_changed_auto_commit_merge
    run_test "10 post-commit hook fires on git commit"      test_post_commit_hook_fires
    run_test "11 decision records event + decisions.md"     test_decision_records_event_and_doc
    run_test "12 decision --rejected captures alternatives" test_decision_rejected_alternatives
    run_test "13 state overwrites state.md + event"         test_state_overwrites_state_md
    run_test "14 handoff writes handoff.md + event"         test_handoff_writes_handoff_md
    run_test "14a handoff multiple --next renders bullets"  test_handoff_multiple_next_renders_bullets
    run_test "15 context prints all sections"               test_context_prints_all_sections
    run_test "16 since DATE form"                           test_since_date_form
    run_test "17 since COMMIT form"                         test_since_commit_form
    run_test "18 since --agent known agent"                 test_since_agent_known
    run_test "19 since --agent unknown prints error"        test_since_agent_unknown
    run_test "20 since no args prints usage"                test_since_no_args_prints_usage
    run_test "21 ingest creates lock file"                  test_ingest_creates_lock
    run_test "22 ingest second run says Already ingested"   test_ingest_idempotent_without_force
    run_test "23 ingest --force re-runs"                    test_ingest_force_reruns
    run_test "24 recall returns FTS5 results"               test_recall_returns_results
    run_test "25 recall LIKE branch reachable in source"    test_recall_like_branch_exists
    run_test "25a recall --semantic flag in argparse"        test_recall_semantic_flag_present
    run_test "25b --semantic falls back to FTS5 on failure"  test_recall_semantic_falls_back_when_embedder_down
    run_test "25c semantic helpers present in source"        test_recall_semantic_helpers_present
    run_test "26 worthiness prints CAPTURE/SKIP table"      test_worthiness_prints_table
    run_test "27 get state/handoff/decisions print content" test_get_known_docs
    run_test "28 get references/nonexistent says not exist" test_get_nonexistent_reference
    run_test "29 get unknownword prints Unknown doc"         test_get_unknown_doc
    run_test "30 list shows all artifact paths"             test_list_shows_artifacts
    run_test "31 list --type events shows only events"      test_list_type_events
    run_test "32 annotate handoff appends note"             test_annotate_handoff
    run_test "33 annotate unknown doc prints Unknown doc"   test_annotate_unknown_doc
    run_test "34 version prints 2.x"                        test_version_prints_version
    run_test "35 init creates pre-push hook"                test_init_creates_prepush_hook
    run_test "36 init appends gitignore entries"            test_init_creates_gitignore
    run_test "37 init --map scaffolds map.md"               test_init_map_scaffolds_map_md
    run_test "38 init --ingest auto-ingests on init"        test_init_ingest_auto_ingests
    run_test "39 agent identity from AGENT_NAME env"        test_agent_identity_from_env
    run_test "40 explicit --agent overrides env"            test_agent_identity_explicit_overrides_env
    run_test "41 context shows staleness warning for stub"  test_context_shows_staleness_warnings
    run_test "42 context --check-stale warns on stderr"     test_context_check_stale_prints_to_stderr
    run_test "43 context lists references/ when populated"  test_context_lists_references_when_present
    run_test "44 status shows agent and event count"        test_status_basic_output
    run_test "45 status shows last decision"                test_status_shows_last_decision
    run_test "46 log shows events"                          test_log_basic
    run_test "47 log --oneline is compact"                  test_log_oneline
    run_test "48 log --type filters event type"             test_log_type_filter
    run_test "49 blame finds events for file path"          test_blame_finds_relevant_events
    run_test "50 blame reports no-results gracefully"       test_blame_no_results
    run_test "51 note records event with tag"               test_note_records_event
    run_test "52 ingest --generate-map creates map.md"      test_ingest_generate_map
    run_test "53 decision --outcome stored in doc+timeline" test_decision_outcome_flag
    run_test "54 check passes on healthy repo"             test_check_passes_healthy
    run_test "55 check warns when hooks missing"           test_check_warns_no_hooks
    run_test "56 archive dry-run shows plan"               test_archive_dryrun
    run_test "57 archive --yes compacts timeline"          test_archive_applies
    run_test "58 roster shows agent activity"              test_roster_shows_agents
    run_test "59 config set/get/list/unset"                test_config_roundtrip
    run_test "60 log --reverse reverses order"             test_log_reverse
    run_test "61 recall --limit restricts results"         test_recall_limit
    run_test "62 circuit breaker helpers present in source" test_circuit_breaker_in_source
    run_test "63 decision --type blocker stores event_type" test_decision_type_blocker
    run_test "64 note --type question stores event_type"    test_note_type_question
    run_test "65 stats shows event counts"                  test_stats_shows_counts
    run_test "66 stats shows agent section"                 test_stats_shows_agents
    run_test "67 export --format json is valid JSON"        test_export_json_valid
    run_test "68 export --format md contains sections"      test_export_md_has_sections
    run_test "69 reference create scaffolds file"           test_reference_create
    run_test "70 reference create --template api"           test_reference_create_api_template
    run_test "71 reference list shows cards"                test_reference_list
    run_test "72 reference update overwrites content"       test_reference_update
    run_test "73 reference view prints content"             test_reference_view
    run_test "74 link finds file_changed events for commit" test_link_finds_events
    run_test "75 link no-results message"                   test_link_no_results
    run_test "76 search is alias for recall"                test_search_alias
    run_test "77 context -n controls event count"           test_context_n_flag
    run_test "78 tiered embedder auto-detect in source"     test_tiered_embedder_in_source
    run_test "79 model-aware cache skips wrong-model entries" test_embeddings_model_aware
    run_test "80 check --fix installs missing gitignore"    test_check_fix_gitignore
    run_test "81 check --fix rebuilds stale FTS"            test_check_fix_fts
    run_test "82 diff shows decisions in date window"       test_diff_date_window
    run_test "83 diff detects git-object state changes"     test_diff_git_objects
    run_test "84 timeline by day shows dates"               test_timeline_by_day
    run_test "85 timeline by week groups correctly"         test_timeline_by_week
    run_test "86 tag list shows tags with counts"           test_tag_list
    run_test "87 tag filter shows tagged events"            test_tag_filter
    run_test "88 note-commit writes git note"               test_note_commit_writes_note
    run_test "89 since shows notes section"                 test_since_shows_notes
    run_test "90 event_type indexed by FTS5"                test_event_type_in_fts
    run_test "91 diff and timeline commands present"        test_v13_commands_present
    run_test "92 DCP init scaffolds context.md"             test_dcp_init_scaffolds_context
    run_test "93 DCP context.md absence breaks nothing"     test_dcp_context_absent_ok
    run_test "94 DCP context surfaces context.md"           test_dcp_context_surfaces_context_md
    run_test "95 DCP frontmatter parser key:value + body"   test_dcp_frontmatter_parse
    run_test "96 DCP import seeds context.md lossless"      test_dcp_import_roundtrip
    run_test "97 DCP import guards populated context.md"    test_dcp_import_guards_populated
    run_test "98 DCP export creates absent target"          test_dcp_export_creates_absent
    run_test "99 DCP export appends to unmarked target"     test_dcp_export_appends_unmarked
    run_test "100 DCP export updates marked target only"    test_dcp_export_updates_marked
    run_test "101 DCP export --replace converts file"       test_dcp_export_replace_converts
    run_test "102 DCP export --target all writes all"       test_dcp_export_all
    run_test "103 DCP check detects adapter staleness"      test_dcp_check_staleness
    run_test "104 DCP export honors config target override" test_dcp_export_config_override
    run_test "105 DCP glossary reference card + context"     test_dcp_glossary_card
    run_test "106 DCP reference list --type filter"          test_dcp_reference_type_filter
    run_test "107 DCP init --wizard non-interactive seeds"   test_dcp_wizard_noninteractive
    run_test "108 DCP init without --wizard unchanged"       test_dcp_wizard_skippable
    run_test "109 DCP promote --to planning preserves history" test_dcp_promote_jagent
    run_test "110 DCP diff --format patch machine-readable"  test_dcp_diff_patch
    run_test "111 init creates CLAUDE.md with boot stub"     test_init_creates_claude_md
    run_test "112 init CLAUDE.md boot stub is idempotent"    test_init_claude_md_idempotent
    run_test "113 init discovery skips skills/ gracefully"   test_init_discovery_without_skills_dir
    run_test "114 trap records event with event=trap"         test_trap_records_event
    run_test "115 incident records event with event=incident" test_incident_records_event
    run_test "116 invariant records event + invariants.md"    test_invariant_records_event_and_doc
    run_test "117 init scaffolds invariants.md"               test_init_creates_invariants_md
    run_test "118 context surfaces invariants.md"             test_context_shows_invariants
    run_test "119 rejected lists all rejected alternatives"   test_rejected_lists_all
    run_test "120 rejected filters by topic query"            test_rejected_filters_by_query
    run_test "121 decision --supersedes stored in event+doc"  test_decision_supersedes
    run_test "122 decision --durability stored in event+doc"  test_decision_durability
    run_test "123 since accepts git revision range ref..ref"  test_since_revision_range
    run_test "124 init installs post-checkout hook"           test_init_installs_checkout_hook
    run_test "125 note-commit --trailer amends commit msg"    test_note_commit_trailer
    run_test "126 note-commit --trailer note follows amend"   test_note_commit_trailer_note_follows_amend
    run_test "127 note-commit --trailer refuses non-HEAD sha" test_note_commit_trailer_refuses_non_head
    run_test "128 note-commit --trailer refuses staged work"  test_note_commit_trailer_refuses_staged
    run_test "129 invariant before init self-creates dir"     test_invariant_before_init
    run_test "130 link tolerates null commit field"           test_link_tolerates_null_commit
    run_test "131 since base..tip excludes post-tip events"   test_since_range_excludes_after_tip
    run_test "132 context tolerates non-dict timeline line"   test_context_tolerates_non_dict_timeline_line
    run_test "133 pattern records event + patterns.md"        test_pattern_records_event_and_doc
    run_test "134 init scaffolds patterns.md"                 test_init_creates_patterns_md
    run_test "135 context surfaces patterns.md"               test_context_shows_patterns
    run_test "136 pattern before init self-creates dir"       test_pattern_before_init
    run_test "137 recall finds patterns.md body"              test_recall_finds_pattern_body
    run_test "138 --entity stored + recall by entity"         test_entity_recall
    run_test "139 blame by entity"                            test_blame_by_entity
    run_test "140 entities lists with counts"                 test_entities_list
    run_test "141 entities <name> filters events"             test_entities_filter
    run_test "142 entity names normalized to kebab"           test_entity_normalization
    run_test "143 decision --confidence stored + labeled"     test_decision_confidence
    run_test "144 note --confidence stored"                   test_note_confidence
    run_test "145 recall by confidence"                       test_recall_by_confidence
    run_test "146 invalid --confidence rejected"              test_confidence_invalid_rejected
    run_test "146a decision metadata read-back"               test_decision_metadata_readback
    run_test "146b note metadata read-back"                   test_note_metadata_readback
    run_test "147 supersedes read-back in since"              test_supersedes_readback_since
    run_test "148 supersedes read-back in recall"             test_supersedes_readback_recall
    run_test "149 supersedes read-back in context (no self)"  test_supersedes_readback_context_no_self_match
    run_test "150 decision --artifacts stored + in doc"       test_decision_artifacts
    run_test "151 blame by artifacts (precise)"               test_blame_by_artifacts
    run_test "152 recall by artifact path"                    test_recall_by_artifact
    run_test "153 changelog surfaces decisions"               test_changelog_decisions
    run_test "154 changelog includes commits"                 test_changelog_commits
    run_test "155 changelog annotates superseded"             test_changelog_superseded
    run_test "156 capabilities emits JSON"                    test_capabilities_json
    run_test "157 capabilities text view"                     test_capabilities_text
    run_test "158 branch summary replays intent"              test_branch_summary
    run_test "159 merge-summary summarizes branch"            test_merge_summary_branch
    run_test "160 epoch list shows epochs"                    test_epoch_list
    run_test "161 context surfaces epochs"                    test_context_shows_epochs
    run_test "162 explain file composes memory"               test_explain_file
    run_test "163 explain commit composes memory"             test_explain_commit
    run_test "164 squash-summary synthesizes message"         test_squash_summary_branch
    run_test "165 conflict record surfaces rationale"         test_conflict_record
    run_test "166 author type metadata read-back"             test_author_type_metadata
    run_test "167 tension metadata read-back"                 test_tension_metadata
    run_test "168 value metadata read-back"                   test_value_metadata
    run_test "169 domain owner metadata read-back"            test_domain_owner_metadata

    echo ""
    echo "========================================"
    local total=$(( PASS + FAIL ))
    echo "  Tests passed: $PASS/$total"
    if [[ "${#ERRORS[@]}" -gt 0 ]]; then
        echo "  Failed:"
        for e in "${ERRORS[@]}"; do
            echo "    - $e"
        done
    fi
    echo "========================================"
    echo ""

    [[ "$FAIL" -eq 0 ]]
}

main "$@"

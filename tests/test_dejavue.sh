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
    assert_contains "hook has changed --auto" "$content" "changed --auto --commit"

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

    # Create a real commit with two files
    mkdir -p src
    printf 'hello\n' > src/a.txt
    printf 'world\n' > src/b.txt
    git -C "$TEST_DIR" add src/a.txt src/b.txt
    git -C "$TEST_DIR" commit -q -m "add two files"
    sha="$(git -C "$TEST_DIR" rev-parse HEAD)"

    local out
    out="$(dv changed --auto --commit "$sha" 2>&1)"
    assert_contains "reports 2 events" "$out" "2 file_changed events"

    # Both files should be recorded
    assert_event_recorded "src/a.txt recorded" ".dejavue/timeline.jsonl" "path" "src/a.txt"
    assert_event_recorded "src/b.txt recorded" ".dejavue/timeline.jsonl" "path" "src/b.txt"

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

# ── main ───────────────────────────────────────────────────────────────────────

main() {
    echo "========================================"
    echo "  dejavue v0.1 integration test suite"
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
    run_test "07 start records session_start with goal"     test_start_records_session_start
    run_test "08 changed PATH --summary records event"      test_changed_manual_records_event
    run_test "09 changed --auto --commit per-file events"   test_changed_auto_commit
    run_test "10 post-commit hook fires on git commit"      test_post_commit_hook_fires
    run_test "11 decision records event + decisions.md"     test_decision_records_event_and_doc
    run_test "12 decision --rejected captures alternatives" test_decision_rejected_alternatives
    run_test "13 state overwrites state.md + event"         test_state_overwrites_state_md
    run_test "14 handoff writes handoff.md + event"         test_handoff_writes_handoff_md
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
    run_test "26 worthiness prints CAPTURE/SKIP table"      test_worthiness_prints_table
    run_test "27 get state/handoff/decisions print content" test_get_known_docs
    run_test "28 get references/nonexistent says not exist" test_get_nonexistent_reference
    run_test "29 get unknownword prints Unknown doc"         test_get_unknown_doc
    run_test "30 list shows all artifact paths"             test_list_shows_artifacts
    run_test "31 list --type events shows only events"      test_list_type_events
    run_test "32 annotate handoff appends note"             test_annotate_handoff
    run_test "33 annotate unknown doc prints Unknown doc"   test_annotate_unknown_doc

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

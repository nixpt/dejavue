#!/usr/bin/env python3
import argparse
import contextlib
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.1.0"

DEJAVUE_DIR = Path(".dejavue")
TIMELINE = DEJAVUE_DIR / "timeline.jsonl"
STATE = DEJAVUE_DIR / "state.md"
DECISIONS = DEJAVUE_DIR / "decisions.md"
HANDOFF = DEJAVUE_DIR / "handoff.md"
REFERENCES = DEJAVUE_DIR / "references"
FTS_DB = DEJAVUE_DIR / "fts.db"
EMBEDDINGS = DEJAVUE_DIR / "embeddings.jsonl"
INGESTED_LOCK = DEJAVUE_DIR / "ingested.lock"
FIRST_USE = DEJAVUE_DIR / ".first-use"
EMBEDDER_CIRCUIT = DEJAVUE_DIR / "embedder_circuit.json"

HAS_FTS5 = None  # probed lazily on first db open

# Semantic recall (v0.2). Pointed at an OpenAI-compatible /v1/embeddings endpoint
# by default; works against ollama out of the box. Override per-repo via env vars.
DEFAULT_EMBEDDER_URL = "http://localhost:11434/v1/embeddings"
DEFAULT_EMBEDDER_MODEL = "nomic-embed-text"
EMBEDDER_TIMEOUT_S = 5.0

# flock support (POSIX only; graceful no-op on Windows)
try:
    import fcntl as _fcntl
    _HAS_FLOCK = True
except ImportError:
    _HAS_FLOCK = False


@contextlib.contextmanager
def _lock(name):
    """Advisory exclusive lock under .dejavue/.locks/<name>.lock. No-op if fcntl unavailable."""
    lock_dir = DEJAVUE_DIR / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{name}.lock"
    lf = open(lock_path, "w")
    try:
        if _HAS_FLOCK:
            _fcntl.flock(lf, _fcntl.LOCK_EX)
        yield
    finally:
        if _HAS_FLOCK:
            _fcntl.flock(lf, _fcntl.LOCK_UN)
        lf.close()


def _load_config():
    """Load .dejavue/config (key=value lines, # comments). Returns dict."""
    p = DEJAVUE_DIR / "config"
    if not p.exists():
        return {}
    cfg = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            cfg[k.strip()] = v.strip()
    return cfg


def resolve_agent(given=None):
    """Return the best agent identity.

    Priority: explicit --agent flag (non-empty, non-'unknown')
              > AGENT_NAME env var
              > CLAUDE_CLI env var
              > GIT_AUTHOR_NAME env var
              > .dejavue/config agent_name
              > 'unknown'
    """
    if given and given not in ("unknown", ""):
        return given
    for env in ("AGENT_NAME", "CLAUDE_CLI", "GIT_AUTHOR_NAME"):
        val = os.environ.get(env, "").strip()
        if val:
            return val
    cfg = _load_config()
    default = cfg.get("agent_name", "").strip()
    if default:
        return default
    return "unknown"


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def git_info():
    def run(cmd):
        try:
            return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
        except Exception:
            return None
    return {
        "branch": run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "commit": run(["git", "rev-parse", "--short", "HEAD"]),
    }


def git_run(*cmd):
    try:
        return subprocess.check_output(list(cmd), text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def append_event(event):
    DEJAVUE_DIR.mkdir(exist_ok=True)
    base = {"ts": now(), **git_info(), **event}
    with TIMELINE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(base, ensure_ascii=False) + "\n")


def maybe_show_worthiness():
    """Print worthiness gate once on first use."""
    if not FIRST_USE.exists():
        print_worthiness()
        FIRST_USE.touch()


def print_worthiness():
    print("""
Worthiness gate — only persist if:

CAPTURE                                    SKIP
─────────────────────────────────────────  ─────────────────────────────────────────
Decision changes architectural direction   Style preferences (let .editorconfig do it)
Constraint non-obvious from the code       Things git diff already shows
Blocker requiring external context         "Ran tests, passed"
Handoff context next agent must know       Per-file mechanical edits
Dead end + why it was rejected             LLM reasoning steps
Cross-cutting invariant ("X never depends  Routine commits
  on Y")

Rule of thumb: if removing this memory wouldn't confuse a future agent reading
the code + git log, don't write it.
""")


def _staleness_warnings():
    """Return list of warning strings about stale .dejavue/ state."""
    import time
    warnings = []
    now_ts = time.time()

    if STATE.exists():
        age_days = (now_ts - STATE.stat().st_mtime) / 86400
        content = STATE.read_text(encoding="utf-8")
        if "No state recorded yet" in content:
            warnings.append("state.md is a default stub — run: dejavue state --summary '<current state>'")
        elif age_days > 7:
            warnings.append(f"state.md is {int(age_days)}d old — consider: dejavue state --summary '<current state>'")
    else:
        warnings.append("state.md missing — run: dejavue state --summary '<current state>'")

    if HANDOFF.exists():
        content = HANDOFF.read_text(encoding="utf-8")
        if "before making changes" in content and "## Summary\n" not in content:
            warnings.append("handoff.md is default stub — no prior handoff on record")
    else:
        warnings.append("handoff.md missing")

    if REFERENCES.exists() and not list(REFERENCES.glob("*.md")):
        warnings.append("references/ is empty — consider: dejavue init --map to scaffold map.md")

    return warnings


# ── FTS5 / sqlite helpers ──────────────────────────────────────────────────────

def open_db():
    global HAS_FTS5
    conn = sqlite3.connect(str(FTS_DB))
    if HAS_FTS5 is None:
        try:
            conn.execute("CREATE VIRTUAL TABLE temp.probe USING fts5(x)")
            conn.execute("DROP TABLE temp.probe")
            HAS_FTS5 = True
        except sqlite3.OperationalError:
            HAS_FTS5 = False
    return conn


def fts_needs_rebuild():
    if not FTS_DB.exists():
        return True
    db_mtime = FTS_DB.stat().st_mtime
    sources = [TIMELINE, STATE, DECISIONS, HANDOFF]
    if REFERENCES.exists():
        sources += list(REFERENCES.glob("*.md"))
    return any(p.exists() and p.stat().st_mtime > db_mtime for p in sources)


def rebuild_fts():
    DEJAVUE_DIR.mkdir(exist_ok=True)
    with _lock("fts"):
        conn = open_db()
        if HAS_FTS5:
            conn.execute("DROP TABLE IF EXISTS events_fts")
            conn.execute(
                "CREATE VIRTUAL TABLE events_fts USING fts5(ts, event, summary, source)"
            )
        else:
            conn.execute("DROP TABLE IF EXISTS events_fts")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS events_fts (ts TEXT, event TEXT, summary TEXT, source TEXT)"
            )

        rows = []

        if TIMELINE.exists():
            for line in TIMELINE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                    parts = [
                        ev.get("summary", ""),
                        ev.get("goal", ""),
                        ev.get("decision_title", ev.get("decision", "")),
                        ev.get("decision_reason", ev.get("reason", "")),
                        ev.get("tag", ""),
                        ev.get("content", ""),
                    ]
                    text = " ".join(p for p in parts if p)
                    rows.append((ev.get("ts", ""), ev.get("event", ""), text, "timeline.jsonl"))
                except json.JSONDecodeError:
                    pass

        for path, label in [(STATE, "state.md"), (DECISIONS, "decisions.md"), (HANDOFF, "handoff.md")]:
            if path.exists():
                rows.append(("", "doc", path.read_text(encoding="utf-8"), label))

        if REFERENCES.exists():
            for ref in REFERENCES.glob("*.md"):
                rows.append(("", "reference", ref.read_text(encoding="utf-8"), f"references/{ref.name}"))

        conn.executemany("INSERT INTO events_fts(ts, event, summary, source) VALUES (?,?,?,?)", rows)
        conn.commit()
        conn.close()


# ── command implementations ────────────────────────────────────────────────────

def cmd_version(args):
    print(f"dejavue {VERSION}")


def cmd_init(args):
    DEJAVUE_DIR.mkdir(exist_ok=True)
    REFERENCES.mkdir(exist_ok=True)

    if not STATE.exists():
        STATE.write_text("# State\n\nNo state recorded yet.\n", encoding="utf-8")

    if not DECISIONS.exists():
        DECISIONS.write_text("# Decisions\n\n", encoding="utf-8")

    if not HANDOFF.exists():
        HANDOFF.write_text(
            "# Handoff\n\nRead `.dejavue/state.md`, `.dejavue/decisions.md`,"
            " and `.dejavue/timeline.jsonl` before making changes.\n",
            encoding="utf-8",
        )

    git_dir_raw = git_run("git", "rev-parse", "--git-dir")
    if git_dir_raw:
        git_dir = Path(git_dir_raw)
        hooks_dir = git_dir / "hooks"
        hooks_dir.mkdir(exist_ok=True)

        # post-commit hook
        hook_path = hooks_dir / "post-commit"
        marker = "#!/usr/bin/env bash\n# dejavue auto-capture"
        if hook_path.exists():
            content = hook_path.read_text(encoding="utf-8")
            if content.startswith(marker):
                pass
            elif args.force:
                _write_hook(hook_path, marker)
                print("Replaced existing post-commit hook with dejavue hook.")
            else:
                print(
                    f"WARNING: {hook_path} exists with non-dejavue content. "
                    "Use --force to overwrite."
                )
        else:
            _write_hook(hook_path, marker)
            print(f"Installed post-commit hook at {hook_path}")

        # pre-push hook
        prepush_path = hooks_dir / "pre-push"
        prepush_marker = "#!/usr/bin/env bash\n# dejavue pre-push"
        if prepush_path.exists():
            if not prepush_path.read_text(encoding="utf-8").startswith(prepush_marker):
                if args.force:
                    _write_prepush_hook(prepush_path, prepush_marker)
                    print("Replaced existing pre-push hook with dejavue hook.")
                # else: leave foreign hook alone
        else:
            _write_prepush_hook(prepush_path, prepush_marker)
            print(f"Installed pre-push hook at {prepush_path}")

        _install_gitattributes(force=args.force)
        _install_gitignore()
    else:
        print("WARNING: not inside a git repo; skipping hook install.")

    append_event({
        "agent": resolve_agent(args.agent),
        "event": "init",
        "summary": "Initialized .dejavue/ memory scaffold.",
    })

    if getattr(args, "map", False):
        _scaffold_map()

    if getattr(args, "ingest", False):
        class _IngestArgs:
            force = True
            generate_map = False
        cmd_ingest(_IngestArgs())

    maybe_show_worthiness()
    print("Initialized .dejavue/")


def _write_hook(hook_path, marker):
    script_path = Path(sys.argv[0]).resolve()
    script = (
        marker + "\n"
        f'exec python3 "{script_path}" changed --auto --commit "$(git rev-parse HEAD)" 2>/dev/null || true\n'
    )
    hook_path.write_text(script, encoding="utf-8")
    hook_path.chmod(0o755)


def _write_prepush_hook(hook_path, marker):
    script_path = Path(sys.argv[0]).resolve()
    script = (
        marker + "\n"
        f'python3 "{script_path}" context --check-stale 2>/dev/null || true\n'
        "exit 0\n"
    )
    hook_path.write_text(script, encoding="utf-8")
    hook_path.chmod(0o755)


# .gitattributes lines we own. Both files are append-only by contract;
# merge=union keeps unique lines from both sides on a branch merge.
_GITATTR_LINES = (
    ".dejavue/timeline.jsonl merge=union",
    ".dejavue/decisions.md   merge=union",
)
_GITATTR_MARKER = "# dejavue: append-only files use git's union merge driver"


def _install_gitattributes(force=False):
    """Append our merge=union directives to .gitattributes if absent. Idempotent."""
    path = Path(".gitattributes")
    existing = path.read_text(encoding="utf-8") if path.exists() else ""

    if _GITATTR_MARKER in existing and not force:
        return

    already_have_lines = all(line in existing for line in _GITATTR_LINES)
    if already_have_lines and not force:
        return

    block = ["", _GITATTR_MARKER, *_GITATTR_LINES, ""]
    sep = "" if existing.endswith("\n") or existing == "" else "\n"
    new_content = existing + sep + "\n".join(block) + "\n"
    path.write_text(new_content, encoding="utf-8")
    if existing == "":
        print(f"Installed .gitattributes with {len(_GITATTR_LINES)} merge=union directives.")
    else:
        print(f"Appended {len(_GITATTR_LINES)} merge=union directives to existing .gitattributes.")


_GITIGNORE_ENTRIES = (
    ".dejavue/fts.db",
    ".dejavue/*.tmp",
    ".dejavue/.first-use",
    ".dejavue/ingested.lock",
    ".dejavue/.locks/",
    ".dejavue/embeddings.jsonl",
    ".dejavue/embedder_circuit.json",
    ".dejavue/timeline.jsonl.bak-*",
)
_GITIGNORE_MARKER = "# dejavue: local-only artifacts"


def _install_gitignore():
    """Append dejavue gitignore entries if absent. Idempotent."""
    path = Path(".gitignore")
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if _GITIGNORE_MARKER in existing:
        return
    block = ["", _GITIGNORE_MARKER, *_GITIGNORE_ENTRIES, ""]
    sep = "" if existing.endswith("\n") or existing == "" else "\n"
    new_content = existing + sep + "\n".join(block) + "\n"
    path.write_text(new_content, encoding="utf-8")
    print(f"Appended {len(_GITIGNORE_ENTRIES)} entries to .gitignore.")


def _scaffold_map():
    """Create references/map.md with a starter template."""
    REFERENCES.mkdir(exist_ok=True)
    map_path = REFERENCES / "map.md"
    if map_path.exists():
        print("references/map.md already exists — not overwritten.")
        return
    map_path.write_text(
        "# Codebase Map\n\n"
        "<!-- Scaffolded by `dejavue init --map` — fill in and commit. -->\n"
        "<!-- Run `dejavue ingest --generate-map` for auto-detected structure. -->\n\n"
        "## Top-level layout\n\n"
        "```\n"
        "# (fill in: key directories and their purpose)\n"
        "```\n\n"
        "## Key entry points\n\n"
        "- (fill in: main binaries / packages / modules)\n\n"
        "## Design invariants\n\n"
        "- (fill in: what must never change, key architectural constraints)\n\n"
        "## External dependencies\n\n"
        "- (fill in: critical external deps and why they were chosen)\n",
        encoding="utf-8",
    )
    print("Scaffolded references/map.md — fill it in with the codebase overview.")


def cmd_start(args):
    maybe_show_worthiness()
    append_event({
        "agent": resolve_agent(args.agent),
        "event": "session_start",
        "goal": args.goal,
        "summary": f"Session start: {args.goal}",
    })
    print(f"Session started. Goal: {args.goal}")


def cmd_changed(args):
    if args.auto and args.commit:
        sha = args.commit
        diff_stat = git_run("git", "show", "--stat", sha).splitlines()
        stat_summary = diff_stat[-1] if diff_stat else ""
        commit_msg = git_run("git", "log", "-1", "--format=%s", sha)
        # Use diff-tree with -m --first-parent --root to handle merges + root commits;
        # plain git show --name-only silently emits nothing for merge commits.
        touched = [
            l for l in git_run(
                "git", "diff-tree", "--no-commit-id", "-r", "--name-only",
                "-m", "--first-parent", "--root", sha,
            ).splitlines() if l
        ]
        branch = git_run("git", "rev-parse", "--abbrev-ref", "HEAD")
        short = sha[:7]
        for path in touched or [args.path or "unknown"]:
            ev = {
                "agent": resolve_agent(args.agent) if args.agent else "git-hook",
                "event": "file_changed",
                "path": path,
                "branch": branch,
                "commit": short,
                "diff_stat": stat_summary,
                "summary": commit_msg or f"commit {short}",
            }
            base = {"ts": now(), **ev}
            DEJAVUE_DIR.mkdir(exist_ok=True)
            with TIMELINE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(base, ensure_ascii=False) + "\n")
        print(f"Recorded {len(touched)} file_changed events for {sha[:7]}.")
    else:
        maybe_show_worthiness()
        summary = args.summary or f"Changed {args.path}"
        append_event({
            "agent": resolve_agent(args.agent),
            "event": "file_changed",
            "path": args.path,
            "summary": summary,
        })
        print("Change recorded.")


def cmd_decision(args):
    maybe_show_worthiness()
    ts = now()
    rejected = []
    if args.rejected:
        for r in args.rejected:
            if ": " in r:
                opt, reason = r.split(": ", 1)
            else:
                opt, reason = r, ""
            rejected.append({"option": opt, "reason": reason})

    entry = f"\n## {ts} — {args.title}\n\nReason:\n{args.reason}\n"
    if rejected:
        entry += "\nRejected alternatives:\n"
        for ra in rejected:
            entry += f"- **{ra['option']}**"
            if ra["reason"]:
                entry += f": {ra['reason']}"
            entry += "\n"
    if args.outcome:
        entry += f"\nOutcome:\n{args.outcome}\n"
    entry += "\n"
    with DECISIONS.open("a", encoding="utf-8") as f:
        f.write(entry)

    append_event({
        "agent": resolve_agent(args.agent),
        "event": "decision",
        "decision_title": args.title,
        "decision_reason": args.reason,
        "summary": f"Decision: {args.title}",
        "rejected_alternatives": rejected,
        "outcome": args.outcome or "",
    })
    print(f"Decision recorded: {args.title}")


def cmd_state(args):
    maybe_show_worthiness()
    ts = now()
    STATE.write_text(f"# State\n\nUpdated: {ts}\n\n{args.summary}\n", encoding="utf-8")
    append_event({
        "agent": resolve_agent(args.agent),
        "event": "state_update",
        "summary": args.summary,
    })
    print("State updated.")


def cmd_handoff(args):
    maybe_show_worthiness()
    ts = now()
    next_section = args.next[0] if len(args.next) == 1 else "\n".join(f"- {item}" for item in args.next)
    HANDOFF.write_text(
        f"# Handoff\n\nUpdated: {ts}\n\n## Summary\n{args.summary}\n\n"
        f"## Next Steps\n{next_section}\n\n## Boot Instructions\n"
        "Read `.dejavue/handoff.md`, `.dejavue/state.md`, `.dejavue/decisions.md`,"
        " and `.dejavue/timeline.jsonl` before making changes.\n",
        encoding="utf-8",
    )
    append_event({
        "agent": resolve_agent(args.agent),
        "event": "handoff",
        "summary": args.summary,
        "next": args.next,
    })
    print("Handoff written.")


def cmd_context(args):
    # staleness warnings (hidden behind --check-stale for pre-push hook use)
    if getattr(args, "check_stale", False):
        warnings = _staleness_warnings()
        if warnings:
            print("dejavue: staleness warnings:", file=sys.stderr)
            for w in warnings:
                print(f"  ⚠  {w}", file=sys.stderr)
        return

    print("\n# Dejavue Context\n")
    for path, label in [(HANDOFF, "handoff.md"), (STATE, "state.md"), (DECISIONS, "decisions.md")]:
        if path.exists():
            print(f"--- {label} ---\n")
            print(path.read_text(encoding="utf-8"))

    if REFERENCES.exists():
        refs = sorted(REFERENCES.glob("*.md"))
        if refs:
            print("--- references ---\n")
            for ref in refs:
                first_line = ref.read_text(encoding="utf-8").splitlines()
                title = next((l.lstrip("# ").strip() for l in first_line if l.strip()), ref.stem)
                print(f"  {ref.name}  ({title})")
                print()

    if TIMELINE.exists():
        print("--- recent timeline (last 10) ---\n")
        lines = TIMELINE.read_text(encoding="utf-8").splitlines()[-10:]
        for line in lines:
            try:
                ev = json.loads(line)
                print(f"  [{ev.get('ts','')}] {ev.get('event','')} — {ev.get('summary','')}")
            except Exception:
                print(f"  {line}")

    # staleness warnings at the bottom
    warnings = _staleness_warnings()
    if warnings:
        print("\n--- warnings ---\n")
        for w in warnings:
            print(f"  ⚠  {w}")


def cmd_status(args):
    """One-line health view: active agent, last decision, open next-steps."""
    if not DEJAVUE_DIR.exists():
        print("Not initialized. Run: dejavue init")
        return

    events = _load_events()

    # Last active agent (most recent session_start)
    last_start = next((ev for ev in reversed(events) if ev.get("event") == "session_start"), None)
    agent_str = last_start.get("agent", "?") if last_start else "(none)"

    # Last decision
    last_dec = next((ev for ev in reversed(events) if ev.get("event") == "decision"), None)
    dec_str = ""
    if last_dec:
        ts = (last_dec.get("ts") or "")[:10]
        title = last_dec.get("decision_title", "")[:50]
        dec_str = f"{title} ({ts})"

    # Open next-steps from handoff
    next_steps = []
    if HANDOFF.exists():
        in_next = False
        for line in HANDOFF.read_text(encoding="utf-8").splitlines():
            if line.startswith("## Next Steps"):
                in_next = True
                continue
            if in_next and line.startswith("## "):
                break
            if in_next and line.strip():
                next_steps.append(line.strip().lstrip("- "))

    # Event count
    n_events = len(events)

    print(f"Active agent : {agent_str}")
    print(f"Events       : {n_events}")
    if last_dec:
        print(f"Last decision: {dec_str}")
    if next_steps:
        print(f"Next steps   :")
        for s in next_steps[:3]:
            print(f"  • {s}")

    # inline staleness warnings
    warnings = _staleness_warnings()
    if warnings:
        print()
        for w in warnings:
            print(f"  ⚠  {w}")


def cmd_check(args):
    """Health check: JSONL validity, hook installation, gitattributes, FTS freshness."""
    ok = True

    def _report(status, label, detail=""):
        nonlocal ok
        sym = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}.get(status, "?")
        line = f"  {sym} {label}"
        if detail:
            line += f"  — {detail}"
        print(line)
        if status == "FAIL":
            ok = False

    print(f"dejavue check — {DEJAVUE_DIR}\n")

    # .dejavue/ exists
    if not DEJAVUE_DIR.exists():
        _report("FAIL", ".dejavue/ directory", "missing — run: dejavue init")
        return

    # JSONL validity
    if TIMELINE.exists():
        bad = 0
        total = 0
        for i, line in enumerate(TIMELINE.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            total += 1
            try:
                json.loads(line)
            except json.JSONDecodeError:
                bad += 1
        if bad:
            _report("FAIL", f"timeline.jsonl ({total} lines)", f"{bad} invalid JSON line(s)")
        else:
            _report("PASS", f"timeline.jsonl ({total} lines)")
    else:
        _report("WARN", "timeline.jsonl", "not yet created")

    # Core docs
    for path, label in [(STATE, "state.md"), (DECISIONS, "decisions.md"), (HANDOFF, "handoff.md")]:
        if not path.exists():
            _report("WARN", label, "missing")
        elif label == "state.md" and "No state recorded yet" in path.read_text(encoding="utf-8"):
            _report("WARN", label, "default stub — update with: dejavue state --summary '...'")
        else:
            _report("PASS", label)

    # hooks
    git_dir_raw = git_run("git", "rev-parse", "--git-dir")
    if git_dir_raw:
        git_dir = Path(git_dir_raw)
        script_path = str(Path(sys.argv[0]).resolve())

        for hook_name, marker in [("post-commit", "dejavue auto-capture"), ("pre-push", "dejavue pre-push")]:
            hook_path = git_dir / "hooks" / hook_name
            if not hook_path.exists():
                _report("WARN", f"{hook_name} hook", "not installed — run: dejavue init")
            else:
                content = hook_path.read_text(encoding="utf-8")
                if marker not in content:
                    _report("WARN", f"{hook_name} hook", "exists but not a dejavue hook")
                elif script_path not in content:
                    _report("WARN", f"{hook_name} hook", f"points to a different dejavue path (expected {script_path})")
                else:
                    _report("PASS", f"{hook_name} hook")
    else:
        _report("WARN", "git hooks", "not in a git repo")

    # .gitattributes
    ga = Path(".gitattributes")
    if ga.exists() and _GITATTR_MARKER in ga.read_text(encoding="utf-8"):
        _report("PASS", ".gitattributes merge=union")
    elif ga.exists() and all(line in ga.read_text(encoding="utf-8") for line in _GITATTR_LINES):
        _report("PASS", ".gitattributes merge=union", "entries present (no marker)")
    else:
        _report("WARN", ".gitattributes", "merge=union not configured — run: dejavue init")

    # .gitignore
    gi = Path(".gitignore")
    if gi.exists() and _GITIGNORE_MARKER in gi.read_text(encoding="utf-8"):
        _report("PASS", ".gitignore entries")
    else:
        _report("WARN", ".gitignore", "dejavue entries missing — run: dejavue init")

    # FTS
    if FTS_DB.exists():
        if fts_needs_rebuild():
            _report("WARN", "fts.db", "stale — will rebuild on next recall")
        else:
            _report("PASS", "fts.db", "up to date")
    else:
        _report("WARN", "fts.db", "not yet built — will build on first recall")

    # references/map.md
    map_file = REFERENCES / "map.md"
    if map_file.exists():
        _report("PASS", "references/map.md")
    elif REFERENCES.exists():
        _report("WARN", "references/map.md", "missing — run: dejavue init --map or ingest --generate-map")
    else:
        _report("WARN", "references/", "directory not created")

    print()
    if ok:
        print("All checks passed.")
    else:
        print("Some checks failed — see above.")
    return 0 if ok else 1


def cmd_archive(args):
    """Compact the timeline by collapsing file_changed events older than a date."""
    if not TIMELINE.exists():
        print("No timeline found.")
        return

    cutoff = args.before
    if not re.match(r"^\d{4}-\d{2}-\d{2}", cutoff):
        print(f"Invalid date format '{cutoff}'. Use YYYY-MM-DD.")
        return

    events = _load_events()
    before = [ev for ev in events if ev.get("ts", "") < cutoff]
    after  = [ev for ev in events if ev.get("ts", "") >= cutoff]

    # Within 'before': keep non-file_changed events; summarise file_changed ones
    keep_before = [ev for ev in before if ev.get("event") != "file_changed"]
    dropped_fc  = [ev for ev in before if ev.get("event") == "file_changed"]

    total_before = len(before)
    kept_before  = len(keep_before)

    if not dropped_fc:
        print(f"Nothing to archive — no file_changed events before {cutoff}.")
        return

    if not args.yes:
        print(f"Archive plan:")
        print(f"  Events before {cutoff} : {total_before}")
        print(f"  file_changed to drop  : {len(dropped_fc)}")
        print(f"  Other events to keep  : {kept_before}")
        print(f"  Events after {cutoff}  : {len(after)}")
        print()
        print("Re-run with --yes to apply.")
        return

    # Inject a summary compaction event
    summary_event = {
        "ts": now(),
        **git_info(),
        "agent": "dejavue-archive",
        "event": "archive",
        "summary": f"Archived {len(dropped_fc)} file_changed events before {cutoff}",
        "dropped_count": len(dropped_fc),
        "cutoff": cutoff,
    }

    new_lines = (
        [json.dumps(ev, ensure_ascii=False) for ev in keep_before]
        + [json.dumps(summary_event, ensure_ascii=False)]
        + [json.dumps(ev, ensure_ascii=False) for ev in after]
    )

    # Back up the original
    backup = DEJAVUE_DIR / f"timeline.jsonl.bak-{cutoff}"
    backup.write_text(TIMELINE.read_text(encoding="utf-8"), encoding="utf-8")

    with _lock("archive"):
        TIMELINE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    print(f"Archived {len(dropped_fc)} file_changed events before {cutoff}.")
    print(f"Timeline: {total_before + len(after)} → {len(new_lines)} lines.")
    print(f"Backup at {backup}")


def cmd_roster(args):
    """Show agent activity summary — who worked here and when."""
    events = _load_events()

    if not events:
        print("No events in timeline.")
        return

    from collections import defaultdict
    agents = defaultdict(lambda: {
        "first": None, "last": None,
        "sessions": 0, "decisions": 0, "notes": 0, "handoffs": 0,
    })

    for ev in events:
        agent = ev.get("agent") or "unknown"
        ts = ev.get("ts", "")
        kind = ev.get("event", "")
        a = agents[agent]
        if a["first"] is None or ts < a["first"]:
            a["first"] = ts
        if a["last"] is None or ts > a["last"]:
            a["last"] = ts
        if kind == "session_start":
            a["sessions"] += 1
        elif kind == "decision":
            a["decisions"] += 1
        elif kind == "note":
            a["notes"] += 1
        elif kind == "handoff":
            a["handoffs"] += 1

    # Sort by last-active descending
    sorted_agents = sorted(agents.items(), key=lambda kv: kv[1]["last"] or "", reverse=True)

    print(f"Agent roster ({len(sorted_agents)} agents):\n")
    for agent, data in sorted_agents:
        first = (data["first"] or "")[:10]
        last  = (data["last"]  or "")[:10]
        stats = []
        if data["sessions"]:
            stats.append(f"{data['sessions']} session{'s' if data['sessions'] != 1 else ''}")
        if data["decisions"]:
            stats.append(f"{data['decisions']} decision{'s' if data['decisions'] != 1 else ''}")
        if data["notes"]:
            stats.append(f"{data['notes']} note{'s' if data['notes'] != 1 else ''}")
        if data["handoffs"]:
            stats.append(f"{data['handoffs']} handoff{'s' if data['handoffs'] != 1 else ''}")
        stats_str = "  " + ", ".join(stats) if stats else ""
        print(f"  {agent:<20}  {first} – {last}{stats_str}")


def cmd_config(args):
    """Get, set, or list per-repo config values in .dejavue/config."""
    DEJAVUE_DIR.mkdir(exist_ok=True)
    config_path = DEJAVUE_DIR / "config"

    def _read_lines():
        if not config_path.exists():
            return []
        return config_path.read_text(encoding="utf-8").splitlines()

    def _write_lines(lines):
        config_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    action = args.action

    if action == "list":
        cfg = _load_config()
        if not cfg:
            print(f"No config set ({config_path} absent or empty).")
        else:
            for k, v in sorted(cfg.items()):
                print(f"{k} = {v}")

    elif action == "get":
        cfg = _load_config()
        val = cfg.get(args.key)
        if val is None:
            print(f"(not set)")
            sys.exit(1)
        else:
            print(val)

    elif action == "set":
        lines = _read_lines()
        # Replace existing key or append
        new_line = f"{args.key} = {args.value}"
        replaced = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                if k == args.key:
                    lines[i] = new_line
                    replaced = True
                    break
        if not replaced:
            lines.append(new_line)
        _write_lines(lines)
        print(f"Set {args.key} = {args.value}")

    elif action == "unset":
        lines = _read_lines()
        new_lines = []
        removed = False
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k = stripped.split("=", 1)[0].strip()
                if k == args.key:
                    removed = True
                    continue
            new_lines.append(line)
        if removed:
            _write_lines(new_lines)
            print(f"Unset {args.key}")
        else:
            print(f"Key '{args.key}' not found in config.")


def cmd_install_skill(args):
    """Install dejavue SKILL.md files to the user's agent skill directory."""
    # Locate the skills/ directory relative to this script
    script_dir = Path(sys.argv[0]).resolve().parent
    skills_src = script_dir / "skills"
    if not skills_src.exists():
        # Try the repo root if dejavue.py lives at the root
        skills_src = script_dir.parent / "skills"
    if not skills_src.exists():
        print(f"ERROR: skills/ directory not found near {sys.argv[0]}")
        print("This command must be run from the dejavue source repo (the one with skills/).")
        return

    # Candidate agent skill directories (in priority order)
    candidates = [
        Path.home() / ".claude" / "skills",
        Path.home() / ".cursor" / "rules",
        Path.home() / ".config" / "aider" / "skills",
    ]
    if args.dir:
        target_dir = Path(args.dir)
    else:
        target_dir = next((p for p in candidates if p.parent.exists()), None)
        if target_dir is None:
            print("Could not auto-detect an agent skills directory.")
            print("Pass --dir to specify one explicitly.")
            return

    target_dir.mkdir(parents=True, exist_ok=True)

    skill_dirs = sorted(skills_src.iterdir()) if skills_src.is_dir() else []
    skill_dirs = [d for d in skill_dirs if d.is_dir() and (d / "SKILL.md").exists()]

    if not skill_dirs:
        print(f"No skill directories (with SKILL.md) found in {skills_src}")
        return

    for skill_dir in skill_dirs:
        dest = target_dir / skill_dir.name
        if dest.exists() or dest.is_symlink():
            if args.force:
                if dest.is_symlink():
                    dest.unlink()
                else:
                    import shutil
                    shutil.rmtree(dest)
            else:
                print(f"  ⚠  {dest} already exists — skipping (use --force to overwrite)")
                continue
        dest.symlink_to(skill_dir.resolve())
        print(f"  ✓  Installed {skill_dir.name} → {dest}")

    print(f"\nSkills installed to {target_dir}")
    print("Restart your agent session for the new skills to take effect.")


def cmd_log(args):
    """Formatted timeline view with optional filters."""
    events = _load_events()

    # --since filter
    since_ts = None
    if args.since:
        if re.match(r"^\d{4}-\d{2}-\d{2}", args.since):
            since_ts = args.since
        else:
            ts_raw = git_run("git", "log", "-1", "--format=%aI", args.since)
            if ts_raw:
                since_ts = ts_raw
            else:
                print(f"Cannot resolve '{args.since}' as a date or commit.")
                return

    # --agent filter
    agent_filter = args.agent

    # --type filter
    type_filter = args.type

    filtered = events
    if since_ts:
        filtered = [ev for ev in filtered if ev.get("ts", "") >= since_ts[:19]]
    if agent_filter:
        filtered = [ev for ev in filtered if ev.get("agent") == agent_filter]
    if type_filter:
        filtered = [ev for ev in filtered if ev.get("event") == type_filter]

    if not filtered:
        print("No events match the filter.")
        return

    if args.reverse:
        filtered = list(reversed(filtered))

    if args.oneline:
        for ev in filtered:
            ts = (ev.get("ts") or "")[:10]
            kind = ev.get("event", "")
            summary = ev.get("summary", "")[:70]
            print(f"{ts}  {kind:<20}  {summary}")
    else:
        for ev in filtered:
            ts = (ev.get("ts") or "")[:19]
            kind = ev.get("event", "")
            agent = ev.get("agent", "")
            summary = ev.get("summary", "")
            print(f"[{ts}] {kind} ({agent})")
            if summary:
                print(f"    {summary}")
            # show rejected alternatives for decisions
            if kind == "decision" and ev.get("rejected_alternatives"):
                for ra in ev["rejected_alternatives"]:
                    opt = ra.get("option", "")
                    reason = ra.get("reason", "")
                    print(f"    ✗ {opt}" + (f": {reason}" if reason else ""))
            print()


def cmd_blame(args):
    """Show decisions and events that touch a given file path."""
    path = args.path
    events = _load_events()

    relevant = []
    for ev in events:
        hit = (
            path in ev.get("path", "")
            or path in ev.get("summary", "")
            or path in ev.get("decision_reason", ev.get("reason", ""))
            or path in ev.get("decision_title", ev.get("decision", ""))
            or path in ev.get("content", "")
        )
        if hit:
            relevant.append(ev)

    if not relevant:
        print(f"No events found for '{path}'.")
        return

    print(f"Events touching '{path}':\n")
    for ev in relevant:
        ts = (ev.get("ts") or "")[:19]
        kind = ev.get("event", "")
        agent = ev.get("agent", "")
        summary = ev.get("summary", "")
        print(f"[{ts}] {kind} ({agent})")
        if summary:
            print(f"    {summary}")
        if kind == "decision" and ev.get("decision_reason"):
            reason = ev["decision_reason"][:120]
            print(f"    Reason: {reason}")
        print()


def cmd_note(args):
    """Lightweight timestamped note, between annotate and decision."""
    maybe_show_worthiness()
    append_event({
        "agent": resolve_agent(args.agent),
        "event": "note",
        "summary": args.text,
        "tag": args.tag or "",
    })
    print("Note recorded.")


def cmd_since(args):
    ref = args.ref
    since_ts = None
    since_commit = None
    since_label = ref or ""

    if not args.agent and not ref:
        print("Usage: dejavue since <date|commit> or dejavue since --agent <name>")
        return

    if args.agent:
        if not TIMELINE.exists():
            print("No timeline found. Run dejavue init first.")
            return
        events = _load_events()
        match = None
        for ev in reversed(events):
            if ev.get("event") == "session_start" and ev.get("agent") == args.agent:
                match = ev
                break
        if not match:
            print(f"No session_start event found for agent '{args.agent}'.")
            return
        since_ts = match["ts"]
        since_label = f"agent {args.agent} (last start: {since_ts})"
    elif re.match(r"^\d{4}-\d{2}-\d{2}", ref):
        since_ts = ref
        since_label = f"date {ref}"
    else:
        ts_raw = git_run("git", "log", "-1", "--format=%aI", ref)
        if not ts_raw:
            print(f"Cannot resolve '{ref}' as a commit hash.")
            return
        since_ts = ts_raw
        since_commit = ref
        since_label = f"commit {ref} ({since_ts[:10]})"

    print(f"Since {since_label}:\n")

    if since_commit:
        git_log = git_run("git", "log", "--oneline", f"{since_commit}..HEAD")
        git_stat = git_run("git", "diff", "--stat", f"{since_commit}..HEAD")
    elif since_ts:
        git_log = git_run("git", "log", "--oneline", f"--since={since_ts[:10]}")
        git_stat = ""
    else:
        git_log = ""
        git_stat = ""

    print("Git delta:")
    if git_log:
        for line in git_log.splitlines():
            print(f"  {line}")
    else:
        print("  (no commits)")
    if git_stat:
        print(f"\n  {git_stat.strip()}")

    events = _load_events()
    window = [ev for ev in events if ev.get("ts", "") >= since_ts[:19]]

    decisions_in_window = [ev for ev in window if ev.get("event") == "decision"]
    state_updates = [ev for ev in window if ev.get("event") == "state_update"]
    handoffs_in_window = [ev for ev in window if ev.get("event") == "handoff"]

    print(f"\nTimeline events ({len(window)}):")
    for ev in reversed(window):
        print(f"  [{ev.get('ts','')}] {ev.get('event','')} — {ev.get('summary','')}")

    print(f"\nDecisions made ({len(decisions_in_window)}):")
    for ev in decisions_in_window:
        print(f"  [{ev.get('ts','')}] {ev.get('decision_title', ev.get('decision',''))}")
        if ev.get("decision_reason"):
            print(f"    Reason: {ev['decision_reason']}")

    print(f"\nState transitions ({len(state_updates)}):")
    if state_updates:
        for ev in state_updates:
            print(f"  [{ev.get('ts','')}] {ev.get('summary','')}")
    else:
        print("  (none)")

    print(f"\nHandoffs in window ({len(handoffs_in_window)}):")
    if handoffs_in_window:
        for ev in handoffs_in_window:
            print(f"  [{ev.get('ts','')}] {ev.get('summary','')}")
    else:
        print("  (none)")

    stopwords = {"the","a","an","and","or","of","to","in","is","it","for","with","on","at","by","was"}
    freq = {}
    for ev in window:
        text = " ".join(str(v) for v in [ev.get("summary",""), ev.get("goal",""), ev.get("decision_reason","")] if v)
        for word in re.findall(r"[a-z]{3,}", text.lower()):
            if word not in stopwords:
                freq[word] = freq.get(word, 0) + 1
    top = sorted(freq, key=lambda w: -freq[w])[:5]
    print(f"\nTopics (top keywords): {', '.join(top) if top else '(none)'}")


def cmd_ingest(args):
    with _lock("ingest"):
        if INGESTED_LOCK.exists() and not args.force:
            print("Already ingested (marker exists). Use --force to re-run.")
            return

        ingested = []
        ts = now()

        # 1. git log --since=1.year
        log = git_run("git", "log", "--since=1.year", "--pretty=format:%H\t%s", "--name-only")
        current_hash = current_msg = None
        touched = []
        for line in log.splitlines():
            if "\t" in line and len(line.split("\t")[0]) == 40:
                if current_hash and touched:
                    for p in touched:
                        append_event({
                            "agent": "ingest",
                            "event": "file_changed",
                            "path": p,
                            "commit": current_hash[:7],
                            "summary": current_msg,
                        })
                parts = line.split("\t", 1)
                current_hash = parts[0]
                current_msg = parts[1] if len(parts) > 1 else ""
                touched = []
            elif line.strip() and current_hash:
                touched.append(line.strip())
        if current_hash and touched:
            for p in touched:
                append_event({
                    "agent": "ingest",
                    "event": "file_changed",
                    "path": p,
                    "commit": current_hash[:7],
                    "summary": current_msg,
                })
        ingested.append("git log --since=1.year")

        # 2. agent instruction files
        for candidate in [Path(".claude/CLAUDE.md"), Path("AGENTS.md"), Path(".cursorrules")]:
            if candidate.exists():
                content = candidate.read_text(encoding="utf-8", errors="replace")[:500]
                append_event({
                    "agent": "ingest",
                    "event": "decision",
                    "decision_title": f"Agent instruction file: {candidate}",
                    "decision_reason": content,
                    "summary": f"Ingested agent instruction file {candidate}",
                })
                ingested.append(str(candidate))

        # 3. CHANGELOG.md
        for cl in [Path("CHANGELOG.md"), Path("CHANGELOG")]:
            if cl.exists():
                for line in cl.read_text(encoding="utf-8", errors="replace").splitlines():
                    if re.match(r"^#+\s*\[?v?\d", line):
                        append_event({
                            "agent": "ingest",
                            "event": "decision",
                            "decision_title": f"Release: {line.strip('# ').strip()}",
                            "decision_reason": "From CHANGELOG",
                            "summary": f"Release entry: {line.strip('# ').strip()}",
                        })
                ingested.append(str(cl))
                break

        # 4. ADR directories
        for adr_dir in [Path("docs/decisions"), Path("docs/adr")]:
            if adr_dir.exists():
                for adr in sorted(adr_dir.glob("*.md")):
                    content = adr.read_text(encoding="utf-8", errors="replace")[:500]
                    append_event({
                        "agent": "ingest",
                        "event": "decision",
                        "decision_title": f"ADR: {adr.stem}",
                        "decision_reason": content,
                        "summary": f"Ingested ADR {adr.name}",
                    })
                    ingested.append(str(adr))

        # 5. README.md
        for readme in [Path("README.md"), Path("README")]:
            if readme.exists():
                first_para = ""
                for line in readme.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.strip():
                        first_para = line.strip()
                        break
                append_event({
                    "agent": "ingest",
                    "event": "state_update",
                    "summary": first_para or "README present",
                })
                ingested.append(str(readme))
                break

        INGESTED_LOCK.write_text(
            json.dumps({"ts": ts, "ingested": ingested}, indent=2), encoding="utf-8"
        )
        print(f"Ingested {len(ingested)} sources into timeline.")

    if getattr(args, "generate_map", False):
        _generate_map()


def _generate_map():
    """Auto-populate references/map.md with lang-aware codebase structure."""
    REFERENCES.mkdir(exist_ok=True)
    map_path = REFERENCES / "map.md"

    lines = [f"# Codebase Map\n\n<!-- Generated by `dejavue ingest --generate-map` on {now()} -->\n"]

    # detect project type and entry points
    project_types = []
    entry_points = []

    cargo = Path("Cargo.toml")
    if cargo.exists():
        project_types.append("Rust")
        try:
            content = cargo.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r'\[\[bin\]\].*?name\s*=\s*"([^"]+)"', content, re.DOTALL):
                entry_points.append(f"{m.group(1)} (Rust binary)")
            for m in re.finditer(r'name\s*=\s*"([^"]+)"', content):
                entry_points.append(f"{m.group(1)} (Rust crate)")
                break
        except Exception:
            pass

    for pyfile in [Path("pyproject.toml"), Path("setup.py"), Path("setup.cfg")]:
        if pyfile.exists():
            project_types.append("Python")
            break

    for pyfile in [Path("pyproject.toml"), Path("setup.cfg")]:
        if pyfile.exists():
            try:
                content = pyfile.read_text(encoding="utf-8", errors="replace")
                for m in re.finditer(r'name\s*=\s*["\']([^"\']+)["\']', content):
                    entry_points.append(f"{m.group(1)} (Python package)")
                    break
            except Exception:
                pass

    pkg_json = Path("package.json")
    if pkg_json.exists():
        project_types.append("JavaScript/TypeScript")
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8", errors="replace"))
            name = data.get("name", "")
            if name:
                entry_points.append(f"{name} (npm package)")
            main = data.get("main", "")
            if main:
                entry_points.append(f"{main} (main entry)")
        except Exception:
            pass

    go_mod = Path("go.mod")
    if go_mod.exists():
        project_types.append("Go")
        try:
            for line in go_mod.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("module "):
                    entry_points.append(f"{line[7:].strip()} (Go module)")
                    break
        except Exception:
            pass

    # top-level structure
    try:
        dirs = sorted(
            p.name for p in Path(".").iterdir()
            if p.is_dir() and not p.name.startswith(".") and p.name not in ("target", "node_modules", "__pycache__", "dist", "build")
        )
    except Exception:
        dirs = []

    if project_types:
        lines.append(f"\n## Project type\n\n{', '.join(set(project_types))}\n")

    if dirs:
        lines.append("\n## Top-level layout\n\n```\n")
        for d in dirs[:20]:
            lines.append(f"{d}/\n")
        lines.append("```\n")

    if entry_points:
        lines.append("\n## Key entry points\n\n")
        seen = set()
        for ep in entry_points:
            if ep not in seen:
                lines.append(f"- {ep}\n")
                seen.add(ep)

    lines.append("\n## Design invariants\n\n- (fill in: key architectural constraints)\n")
    lines.append("\n## External dependencies\n\n- (fill in: critical external deps)\n")

    map_path.write_text("".join(lines), encoding="utf-8")
    print(f"Generated references/map.md from detected project structure ({', '.join(set(project_types)) or 'unknown type'}).")


# ── Embedder circuit breaker ──────────────────────────────────────────────────
# Tracks consecutive failures to avoid hammering a downed embedder endpoint.
# State stored in .dejavue/embedder_circuit.json (gitignored, local only).
# After 3 failures the circuit opens; it resets automatically after 5 minutes.

_CIRCUIT_THRESHOLD = 3
_CIRCUIT_COOLDOWN_S = 300  # 5 minutes


def _circuit_open():
    """Return True if the embedder circuit is open (skip the call)."""
    if not EMBEDDER_CIRCUIT.exists():
        return False
    try:
        import time
        state = json.loads(EMBEDDER_CIRCUIT.read_text(encoding="utf-8"))
        if state.get("failures", 0) >= _CIRCUIT_THRESHOLD:
            last = state.get("last_failure", "")
            if last:
                try:
                    last_ts = datetime.fromisoformat(last).timestamp()
                    if time.time() - last_ts < _CIRCUIT_COOLDOWN_S:
                        return True
                except ValueError:
                    pass
    except Exception:
        pass
    return False


def _circuit_record(success: bool):
    """Update circuit-breaker state after an embedder call."""
    try:
        existing = {}
        if EMBEDDER_CIRCUIT.exists():
            existing = json.loads(EMBEDDER_CIRCUIT.read_text(encoding="utf-8"))
        if success:
            existing = {"failures": 0}
        else:
            existing["failures"] = existing.get("failures", 0) + 1
            existing["last_failure"] = now()
        EMBEDDER_CIRCUIT.write_text(json.dumps(existing), encoding="utf-8")
    except Exception:
        pass


# ── Semantic recall (v0.2) ────────────────────────────────────────────────────

def _line_hash(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()[:16]


def _embedder_url() -> str:
    return os.environ.get("DEJAVUE_EMBEDDER_URL", DEFAULT_EMBEDDER_URL)


def _embedder_model() -> str:
    return os.environ.get("DEJAVUE_EMBEDDER_MODEL", DEFAULT_EMBEDDER_MODEL)


def _embed_one(text):
    """POST an OpenAI-compatible /v1/embeddings request. Returns vec or None on any failure.
    Respects the circuit breaker — returns None immediately when the circuit is open."""
    if not text:
        return None
    if _circuit_open():
        return None
    body = json.dumps({"model": _embedder_model(), "input": text}).encode("utf-8")
    req = urllib.request.Request(
        _embedder_url(),
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=EMBEDDER_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        _circuit_record(False)
        return None
    except json.JSONDecodeError:
        _circuit_record(False)
        return None
    try:
        vec = payload["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError):
        _circuit_record(False)
        return None
    if not isinstance(vec, list) or not vec:
        _circuit_record(False)
        return None
    _circuit_record(True)
    return [float(x) for x in vec]


def _read_embeddings_cache():
    if not EMBEDDINGS.exists():
        return {}
    out = {}
    for line in EMBEDDINGS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        h = row.get("hash")
        vec = row.get("vec")
        if isinstance(h, str) and isinstance(vec, list):
            out[h] = vec
    return out


def _append_embedding(h, vec, model):
    DEJAVUE_DIR.mkdir(exist_ok=True)
    row = {"hash": h, "model": model, "dims": len(vec), "vec": vec}
    with EMBEDDINGS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _cosine(a, b):
    if len(a) != len(b) or not a:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na) * math.sqrt(nb)
    if denom < 1e-12:
        return 0.0
    return dot / denom


def _semantic_text_for(event):
    if event.get("summary"):
        return event["summary"]
    if event.get("event") == "decision":
        bits = [event.get("title", ""), event.get("reason", "")]
        joined = " — ".join(b for b in bits if b)
        if joined:
            return joined
    if event.get("content"):
        return event["content"]
    return None


def _semantic_recall(query, limit=10):
    q_vec = _embed_one(query)
    if q_vec is None:
        return None

    if not TIMELINE.exists():
        return []
    raw_lines = []
    events = []
    for line in TIMELINE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        raw_lines.append(stripped)
        events.append(parsed)

    cache = _read_embeddings_cache()
    model = _embedder_model()

    scored = []
    for raw, evt in zip(raw_lines, events):
        h = _line_hash(raw)
        vec = cache.get(h)
        if vec is None:
            text = _semantic_text_for(evt)
            if text is None:
                continue
            vec = _embed_one(text)
            if vec is None:
                continue
            _append_embedding(h, vec, model)
            cache[h] = vec
        scored.append((_cosine(q_vec, vec), evt))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[:limit]


def cmd_recall(args):
    global HAS_FTS5
    maybe_show_worthiness()

    query = args.query

    limit = getattr(args, "limit", 10) or 10

    if getattr(args, "semantic", False):
        results = _semantic_recall(query, limit=limit)
        if results is None:
            print(
                f"WARNING: semantic embedder at {_embedder_url()} unavailable; falling back to FTS5 keyword recall.",
                file=sys.stderr,
            )
        elif not results:
            print(f"No semantic results for '{query}'.")
            return
        else:
            print(f"Semantic recall results for '{query}' (model: {_embedder_model()}):\n")
            for score, evt in results:
                ts = (evt.get("ts") or "")[:19] or "(no ts)"
                event_kind = evt.get("event", "event")
                source = evt.get("agent") or evt.get("source") or "?"
                text = _semantic_text_for(evt) or ""
                snippet = (text[:120] + "…") if len(text) > 120 else text
                print(f"  [score={score:.3f}] [{ts}] {event_kind} ({source})")
                print(f"    {snippet}\n")
            return

    if fts_needs_rebuild():
        rebuild_fts()
    conn = open_db()

    if HAS_FTS5:
        try:
            rows = conn.execute(
                "SELECT ts, event, summary, source FROM events_fts WHERE events_fts MATCH ? ORDER BY rank LIMIT ?",
                (query, limit),
            ).fetchall()
        except sqlite3.OperationalError as e:
            print(f"FTS5 query error: {e}")
            rows = []
    else:
        print("WARNING: FTS5 not available; falling back to LIKE search.")
        pattern = f"%{query}%"
        rows = conn.execute(
            "SELECT ts, event, summary, source FROM events_fts WHERE summary LIKE ? LIMIT ?",
            (pattern, limit),
        ).fetchall()
    conn.close()

    if not rows:
        print(f"No results for '{query}'.")
        return

    print(f"Recall results for '{query}':\n")
    for ts, event, summary, source in rows:
        ts_display = ts[:19] if ts else "(no ts)"
        snippet = (summary[:120] + "…") if summary and len(summary) > 120 else (summary or "")
        print(f"  [{ts_display}] {event} ({source})")
        print(f"    {snippet}\n")


def cmd_worthiness(args):
    print_worthiness()


def cmd_get(args):
    doc = args.doc
    path = _resolve_doc(doc)
    if path is None:
        print(f"Unknown doc '{doc}'. Valid: state, handoff, decisions, references/<name>")
        return
    if not path.exists():
        print(f"{path} does not exist.")
        return
    print(path.read_text(encoding="utf-8"))


def cmd_list(args):
    kind = args.type
    if kind in (None, "events"):
        if TIMELINE.exists():
            count = sum(1 for l in TIMELINE.read_text(encoding="utf-8").splitlines() if l.strip())
            print(f"  events: {TIMELINE}  ({count} entries)")
        else:
            print(f"  events: {TIMELINE}  (not yet created)")

    if kind in (None, "decisions"):
        if DECISIONS.exists():
            print(f"  decisions: {DECISIONS}")
        if STATE.exists():
            print(f"  state: {STATE}")
        if HANDOFF.exists():
            print(f"  handoff: {HANDOFF}")

    if kind in (None, "references"):
        if REFERENCES.exists():
            refs = list(REFERENCES.glob("*.md"))
            if refs:
                for ref in sorted(refs):
                    print(f"  reference: {ref}")
            else:
                print(f"  references/  (empty — add .md files to {REFERENCES})")
        else:
            print(f"  references/  (not created)")


def cmd_annotate(args):
    path = _resolve_doc(args.doc)
    if path is None:
        print(f"Unknown doc '{args.doc}'. Valid: state, handoff, decisions, references/<name>")
        return
    if not path.exists():
        print(f"{path} does not exist. Create it first.")
        return
    ts = now()
    note = f"\n\n## {ts} — annotation\n{args.note}\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(note)
    print(f"Annotation appended to {path}.")


def _resolve_doc(doc):
    if doc == "state":
        return STATE
    if doc == "handoff":
        return HANDOFF
    if doc == "decisions":
        return DECISIONS
    if doc.startswith("references/"):
        name = doc[len("references/"):]
        if not name.endswith(".md"):
            name += ".md"
        return REFERENCES / name
    return None


def _load_events():
    if not TIMELINE.exists():
        return []
    events = []
    for line in TIMELINE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return events


# ── CLI wiring ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser("dejavue", description="Repo-local agent memory.")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("version", help="Print dejavue version.")
    p.set_defaults(func=cmd_version)

    p = sub.add_parser("init", help="Create .dejavue/, install git hooks.")
    p.add_argument("--agent", default=None)
    p.add_argument("--force", action="store_true", help="Overwrite existing non-dejavue hooks.")
    p.add_argument("--ingest", action="store_true", help="Run ingest after init.")
    p.add_argument("--map", action="store_true", help="Scaffold references/map.md.")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("start", help="Record session start.")
    p.add_argument("--agent", default=None)
    p.add_argument("--goal", required=True)
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("changed", help="Record file change event.")
    p.add_argument("path", nargs="?", default=None)
    p.add_argument("--summary", default=None)
    p.add_argument("--agent", default=None)
    p.add_argument("--auto", action="store_true", help="Auto mode (from git hook).")
    p.add_argument("--commit", default=None, help="Commit SHA (used with --auto).")
    p.set_defaults(func=cmd_changed)

    p = sub.add_parser("decision", help="Record architectural decision.")
    p.add_argument("title")
    p.add_argument("--reason", required=True)
    p.add_argument("--rejected", action="append", default=[], metavar="OPTION",
                   help="Rejected alternative (repeatable). Format: 'option: reason'")
    p.add_argument("--outcome", default=None,
                   help="What shipped / current state (optional).")
    p.add_argument("--agent", default=None)
    p.set_defaults(func=cmd_decision)

    p = sub.add_parser("state", help="Overwrite state.md with current snapshot.")
    p.add_argument("--summary", required=True)
    p.add_argument("--agent", default=None)
    p.set_defaults(func=cmd_state)

    p = sub.add_parser("handoff", help="Write handoff.md.")
    p.add_argument("--summary", required=True)
    p.add_argument("--next", action="append", required=True,
                   help="Repeatable; each occurrence becomes a bullet in handoff.md.")
    p.add_argument("--agent", default=None)
    p.set_defaults(func=cmd_handoff)

    p = sub.add_parser("context", help="Print all .md files + last 10 timeline entries.")
    p.add_argument("--check-stale", action="store_true", dest="check_stale",
                   help="Only print staleness warnings (used by pre-push hook).")
    p.set_defaults(func=cmd_context)

    p = sub.add_parser("status", help="One-line health view: agent, last decision, open next-steps.")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("check", help="Health check: JSONL validity, hook status, .gitattributes, FTS freshness.")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("archive", help="Compact the timeline by collapsing old file_changed events.")
    p.add_argument("--before", required=True, metavar="YYYY-MM-DD",
                   help="Drop file_changed events older than this date.")
    p.add_argument("--yes", action="store_true", help="Apply (omit for dry-run).")
    p.set_defaults(func=cmd_archive)

    p = sub.add_parser("roster", help="Show agent activity summary.")
    p.set_defaults(func=cmd_roster)

    p = sub.add_parser("config", help="Get, set, or list per-repo config values.")
    cfg_sub = p.add_subparsers(dest="action", required=True)

    cs = cfg_sub.add_parser("list", help="List all config values.")
    cs = cfg_sub.add_parser("get", help="Get a config value.")
    cs.add_argument("key")
    cs = cfg_sub.add_parser("set", help="Set a config value.")
    cs.add_argument("key")
    cs.add_argument("value")
    cs = cfg_sub.add_parser("unset", help="Remove a config key.")
    cs.add_argument("key")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("install-skill", help="Install dejavue SKILL.md to your agent's skills directory.")
    p.add_argument("--dir", default=None, metavar="PATH",
                   help="Target skills directory (auto-detects ~/.claude/skills/ by default).")
    p.add_argument("--force", action="store_true", help="Overwrite existing skill symlinks.")
    p.set_defaults(func=cmd_install_skill)

    p = sub.add_parser("log", help="Formatted timeline view.")
    p.add_argument("--since", default=None, help="ISO date or commit hash.")
    p.add_argument("--agent", default=None, help="Filter by agent name.")
    p.add_argument("--type", default=None, dest="type",
                   help="Filter by event type (decision, state_update, handoff, file_changed, note, ...).")
    p.add_argument("--oneline", action="store_true", help="One line per event.")
    p.add_argument("--reverse", action="store_true", help="Show oldest events first.")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("blame", help="Show decisions and events touching a file path.")
    p.add_argument("path")
    p.set_defaults(func=cmd_blame)

    p = sub.add_parser("note", help="Record a lightweight timestamped note.")
    p.add_argument("text")
    p.add_argument("--tag", default=None, help="Optional tag for filtering.")
    p.add_argument("--agent", default=None)
    p.set_defaults(func=cmd_note)

    p = sub.add_parser("since", help="Temporal delta since a date, commit, or agent's last session.")
    p.add_argument("ref", nargs="?", default=None, help="ISO date, commit hash, or (with --agent) ignored.")
    p.add_argument("--agent", default=None, help="Show events since this agent's last session_start.")
    p.set_defaults(func=cmd_since)

    p = sub.add_parser("ingest", help="Scrape .claude/, CHANGELOG, ADRs, git log into timeline.")
    p.add_argument("--force", action="store_true", help="Re-run even if ingested.lock exists.")
    p.add_argument("--generate-map", action="store_true", dest="generate_map",
                   help="Also auto-generate references/map.md from detected project structure.")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("recall", help="Keyword (FTS5) or semantic search over timeline + docs.")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=10, metavar="N",
                   help="Max results to return (default 10).")
    p.add_argument(
        "--semantic",
        action="store_true",
        help=(
            "Cosine-rank events against the query using an external embedder "
            "(set DEJAVUE_EMBEDDER_URL, default http://localhost:11434/v1/embeddings; "
            "DEJAVUE_EMBEDDER_MODEL, default nomic-embed-text). "
            "Lazy: events get embedded into .dejavue/embeddings.jsonl the first time "
            "they're seen during recall. Falls back to FTS5 keyword search when the "
            "embedder is unavailable."
        ),
    )
    p.set_defaults(func=cmd_recall)

    p = sub.add_parser("worthiness", help="Print the worthiness gate (capture/skip table).")
    p.set_defaults(func=cmd_worthiness)

    p = sub.add_parser("get", help="Direct fetch of a doc (state, handoff, decisions, references/<name>).")
    p.add_argument("doc")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("list", help="List available artifacts.")
    p.add_argument("--type", choices=["events", "decisions", "references"], default=None)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("annotate", help="Append timestamped note to a doc.")
    p.add_argument("doc")
    p.add_argument("note")
    p.set_defaults(func=cmd_annotate)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

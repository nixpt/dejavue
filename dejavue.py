#!/usr/bin/env python3
import argparse
import json
import re
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DEJAVUE_DIR = Path(".dejavue")
TIMELINE = DEJAVUE_DIR / "timeline.jsonl"
STATE = DEJAVUE_DIR / "state.md"
DECISIONS = DEJAVUE_DIR / "decisions.md"
HANDOFF = DEJAVUE_DIR / "handoff.md"
REFERENCES = DEJAVUE_DIR / "references"
FTS_DB = DEJAVUE_DIR / "fts.db"
INGESTED_LOCK = DEJAVUE_DIR / "ingested.lock"
FIRST_USE = DEJAVUE_DIR / ".first-use"

HAS_FTS5 = None  # probed lazily on first db open


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

    # git hook
    git_dir_raw = git_run("git", "rev-parse", "--git-dir")
    if git_dir_raw:
        git_dir = Path(git_dir_raw)
        hooks_dir = git_dir / "hooks"
        hooks_dir.mkdir(exist_ok=True)
        hook_path = hooks_dir / "post-commit"
        marker = "#!/usr/bin/env bash\n# dejavue auto-capture"
        if hook_path.exists():
            content = hook_path.read_text(encoding="utf-8")
            if content.startswith(marker):
                pass  # already ours
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
    else:
        print("WARNING: not inside a git repo; skipping hook install.")

    append_event({
        "agent": args.agent,
        "event": "init",
        "summary": "Initialized .dejavue/ memory scaffold.",
    })

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


def cmd_start(args):
    maybe_show_worthiness()
    append_event({
        "agent": args.agent,
        "event": "session_start",
        "goal": args.goal,
        "summary": f"Session start: {args.goal}",
    })
    print(f"Session started. Goal: {args.goal}")


def cmd_changed(args):
    if args.auto and args.commit:
        sha = args.commit
        diff_stat = git_run("git", "show", "--stat", sha).splitlines()
        # last line of --stat is summary ("N files changed…"), use it
        stat_summary = diff_stat[-1] if diff_stat else ""
        commit_msg = git_run("git", "log", "-1", "--format=%s", sha)
        touched = [
            l for l in git_run("git", "show", "--name-only", "--format=", sha).splitlines() if l
        ]
        branch = git_run("git", "rev-parse", "--abbrev-ref", "HEAD")
        short = sha[:7]
        for path in touched or [args.path or "unknown"]:
            ev = {
                "agent": args.agent or "git-hook",
                "event": "file_changed",
                "path": path,
                "branch": branch,
                "commit": short,
                "diff_stat": stat_summary,
                "summary": commit_msg or f"commit {short}",
            }
            # skip ts/git_info double-stamp since we set branch/commit directly
            base = {"ts": now(), **ev}
            DEJAVUE_DIR.mkdir(exist_ok=True)
            with TIMELINE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(base, ensure_ascii=False) + "\n")
        print(f"Recorded {len(touched)} file_changed events for {sha[:7]}.")
    else:
        maybe_show_worthiness()
        summary = args.summary or f"Changed {args.path}"
        append_event({
            "agent": args.agent or "unknown",
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
            # parse "option: reason" or just treat as option with no inline reason
            if ": " in r:
                opt, reason = r.split(": ", 1)
            else:
                opt, reason = r, ""
            rejected.append({"option": opt, "reason": reason})

    # append to decisions.md
    entry = f"\n## {ts} — {args.title}\n\nReason:\n{args.reason}\n"
    if rejected:
        entry += "\nRejected alternatives:\n"
        for ra in rejected:
            entry += f"- **{ra['option']}**"
            if ra["reason"]:
                entry += f": {ra['reason']}"
            entry += "\n"
    entry += "\n"
    with DECISIONS.open("a", encoding="utf-8") as f:
        f.write(entry)

    append_event({
        "agent": args.agent,
        "event": "decision",
        "decision_title": args.title,
        "decision_reason": args.reason,
        "summary": f"Decision: {args.title}",
        "rejected_alternatives": rejected,
    })
    print(f"Decision recorded: {args.title}")


def cmd_state(args):
    maybe_show_worthiness()
    ts = now()
    STATE.write_text(f"# State\n\nUpdated: {ts}\n\n{args.summary}\n", encoding="utf-8")
    append_event({
        "agent": args.agent,
        "event": "state_update",
        "summary": args.summary,
    })
    print("State updated.")


def cmd_handoff(args):
    maybe_show_worthiness()
    ts = now()
    HANDOFF.write_text(
        f"# Handoff\n\nUpdated: {ts}\n\n## Summary\n{args.summary}\n\n"
        f"## Next Steps\n{args.next}\n\n## Boot Instructions\n"
        "Read `.dejavue/handoff.md`, `.dejavue/state.md`, `.dejavue/decisions.md`,"
        " and `.dejavue/timeline.jsonl` before making changes.\n",
        encoding="utf-8",
    )
    append_event({
        "agent": args.agent,
        "event": "handoff",
        "summary": args.summary,
        "next": args.next,
    })
    print("Handoff written.")


def cmd_context(args):
    print("\n# Dejavue Context\n")
    for path, label in [(HANDOFF, "handoff.md"), (STATE, "state.md"), (DECISIONS, "decisions.md")]:
        if path.exists():
            print(f"--- {label} ---\n")
            print(path.read_text(encoding="utf-8"))

    if TIMELINE.exists():
        print("--- recent timeline (last 10) ---\n")
        lines = TIMELINE.read_text(encoding="utf-8").splitlines()[-10:]
        for line in lines:
            try:
                ev = json.loads(line)
                print(f"  [{ev.get('ts','')}] {ev.get('event','')} — {ev.get('summary','')}")
            except Exception:
                print(f"  {line}")


def cmd_since(args):
    ref = args.ref
    since_ts = None
    since_commit = None
    since_label = ref or ""

    if not args.agent and not ref:
        print("Usage: dejavue since <date|commit> or dejavue since --agent <name>")
        return

    # determine form: --agent, ISO date, or commit hash
    if args.agent:
        # find last session_start event for that agent
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
        since_ts = ref  # ISO prefix — compare lexicographically
        since_label = f"date {ref}"
    else:
        # commit hash: get its timestamp
        ts_raw = git_run("git", "log", "-1", "--format=%aI", ref)
        if not ts_raw:
            print(f"Cannot resolve '{ref}' as a commit hash.")
            return
        since_ts = ts_raw
        since_commit = ref
        since_label = f"commit {ref} ({since_ts[:10]})"

    print(f"Since {since_label}:\n")

    # git delta
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

    # filter timeline events in window
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

    # topic keywords (simple tf-idf-ish: top 5 words by frequency, skip stopwords)
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


def cmd_recall(args):
    global HAS_FTS5
    maybe_show_worthiness()
    if fts_needs_rebuild():
        rebuild_fts()

    query = args.query
    conn = open_db()

    if HAS_FTS5:
        try:
            rows = conn.execute(
                "SELECT ts, event, summary, source FROM events_fts WHERE events_fts MATCH ? ORDER BY rank LIMIT 10",
                (query,),
            ).fetchall()
        except sqlite3.OperationalError as e:
            print(f"FTS5 query error: {e}")
            rows = []
    else:
        print("WARNING: FTS5 not available; falling back to LIKE search.")
        pattern = f"%{query}%"
        rows = conn.execute(
            "SELECT ts, event, summary, source FROM events_fts WHERE summary LIKE ? LIMIT 10",
            (pattern,),
        ).fetchall()
    conn.close()

    if not rows:
        print(f"No results for '{query}'.")
        return

    print(f"Recall results for '{query}':\n")
    for ts, event, summary, source in rows:
        ts_display = ts[:19] if ts else "(no ts)"
        # truncate long summaries
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

    p = sub.add_parser("init", help="Create .dejavue/, install git post-commit hook.")
    p.add_argument("--agent", default="unknown")
    p.add_argument("--force", action="store_true", help="Overwrite existing non-dejavue post-commit hook.")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("start", help="Record session start.")
    p.add_argument("--agent", default="unknown")
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
    p.add_argument("--agent", default="unknown")
    p.set_defaults(func=cmd_decision)

    p = sub.add_parser("state", help="Overwrite state.md with current snapshot.")
    p.add_argument("--summary", required=True)
    p.add_argument("--agent", default="unknown")
    p.set_defaults(func=cmd_state)

    p = sub.add_parser("handoff", help="Write handoff.md.")
    p.add_argument("--summary", required=True)
    p.add_argument("--next", required=True)
    p.add_argument("--agent", default="unknown")
    p.set_defaults(func=cmd_handoff)

    p = sub.add_parser("context", help="Print all .md files + last 10 timeline entries.")
    p.set_defaults(func=cmd_context)

    p = sub.add_parser("since", help="Temporal delta since a date, commit, or agent's last session.")
    p.add_argument("ref", nargs="?", default=None, help="ISO date, commit hash, or (with --agent) ignored.")
    p.add_argument("--agent", default=None, help="Show events since this agent's last session_start.")
    p.set_defaults(func=cmd_since)

    p = sub.add_parser("ingest", help="Scrape .claude/, CHANGELOG, ADRs, git log into timeline.")
    p.add_argument("--force", action="store_true", help="Re-run even if ingested.lock exists.")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("recall", help="FTS5 keyword search over timeline + docs.")
    p.add_argument("query")
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

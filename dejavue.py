#!/usr/bin/env python3
import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path

JOKER = Path(".joker")
TIMELINE = JOKER / "timeline.jsonl"
DEJAVUE = JOKER / "deja-vue.md"
CURRENT = JOKER / "current_state.md"
DECISIONS = JOKER / "decisions.md"
HANDOFF = JOKER / "handoff.md"


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def git_info():
    def run(cmd):
        try:
            return subprocess.check_output(cmd, text=True).strip()
        except Exception:
            return None

    return {
        "branch": run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
        "commit": run(["git", "rev-parse", "--short", "HEAD"]),
    }


def append_event(event):
    JOKER.mkdir(exist_ok=True)
    base = {
        "ts": now(),
        **git_info(),
        **event,
    }
    with TIMELINE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(base, ensure_ascii=False) + "\n")


def init(args):
    JOKER.mkdir(exist_ok=True)
    (JOKER / "agent_sessions").mkdir(exist_ok=True)
    (JOKER / "diffs").mkdir(exist_ok=True)

    if not DEJAVUE.exists():
        DEJAVUE.write_text("""# Deja Vue Memory

## Purpose
Repo-local memory for coding agents.

Git captures mechanical history.
Deja Vue captures cognitive history.

""")

    if not CURRENT.exists():
        CURRENT.write_text("""# Current State

No current state recorded yet.
""")

    if not DECISIONS.exists():
        DECISIONS.write_text("""# Decisions

""")

    if not HANDOFF.exists():
        HANDOFF.write_text("""# Handoff

Read `.joker/current_state.md`, `.joker/decisions.md`, and `.joker/timeline.jsonl` before making changes.
""")

    append_event({
        "agent": args.agent,
        "event": "init",
        "summary": "Initialized Deja Vue memory scaffold."
    })

    print("Initialized .joker/ Deja Vue memory.")


def start(args):
    append_event({
        "agent": args.agent,
        "event": "session_start",
        "goal": args.goal,
    })
    print("Session started.")


def changed(args):
    append_event({
        "agent": args.agent,
        "event": "file_changed",
        "path": args.path,
        "summary": args.summary,
    })
    print("Change recorded.")


def decision(args):
    entry = f"""
## {now()} — {args.title}

Reason:
{args.reason}

"""
    with DECISIONS.open("a", encoding="utf-8") as f:
        f.write(entry)

    append_event({
        "agent": args.agent,
        "event": "decision",
        "decision": args.title,
        "reason": args.reason,
    })

    print("Decision recorded.")


def state(args):
    CURRENT.write_text(f"""# Current State

Updated: {now()}

{args.summary}
""", encoding="utf-8")

    append_event({
        "agent": args.agent,
        "event": "state_update",
        "summary": args.summary,
    })

    print("Current state updated.")


def handoff(args):
    HANDOFF.write_text(f"""# Handoff

Updated: {now()}

## Summary
{args.summary}

## Next Steps
{args.next}

## Boot Instructions
Future agents should read:

1. `.joker/handoff.md`
2. `.joker/current_state.md`
3. `.joker/decisions.md`
4. `.joker/timeline.jsonl`

Then inspect git status and recent commits.
""", encoding="utf-8")

    append_event({
        "agent": args.agent,
        "event": "handoff",
        "summary": args.summary,
        "next": args.next,
    })

    print("Handoff written.")


def context(args):
    print("\n# Deja Vue Context\n")

    for file in [HANDOFF, CURRENT, DECISIONS]:
        if file.exists():
            print(f"\n--- {file} ---\n")
            print(file.read_text(encoding="utf-8"))

    if TIMELINE.exists():
        print("\n--- recent timeline ---\n")
        lines = TIMELINE.read_text(encoding="utf-8").splitlines()[-10:]
        for line in lines:
            print(line)


def main():
    parser = argparse.ArgumentParser("dejavue")
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("init")
    p.add_argument("--agent", default="unknown")
    p.set_defaults(func=init)

    p = sub.add_parser("start")
    p.add_argument("--agent", default="unknown")
    p.add_argument("--goal", required=True)
    p.set_defaults(func=start)

    p = sub.add_parser("changed")
    p.add_argument("path")
    p.add_argument("--summary", required=True)
    p.add_argument("--agent", default="unknown")
    p.set_defaults(func=changed)

    p = sub.add_parser("decision")
    p.add_argument("title")
    p.add_argument("--reason", required=True)
    p.add_argument("--agent", default="unknown")
    p.set_defaults(func=decision)

    p = sub.add_parser("state")
    p.add_argument("--summary", required=True)
    p.add_argument("--agent", default="unknown")
    p.set_defaults(func=state)

    p = sub.add_parser("handoff")
    p.add_argument("--summary", required=True)
    p.add_argument("--next", required=True)
    p.add_argument("--agent", default="unknown")
    p.set_defaults(func=handoff)

    p = sub.add_parser("context")
    p.set_defaults(func=context)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
import argparse
import contextlib
import difflib
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

VERSION = "2.0.2"

DEJAVUE_DIR = Path(".dejavue")
TIMELINE = DEJAVUE_DIR / "timeline.jsonl"
STATE = DEJAVUE_DIR / "state.md"
DECISIONS = DEJAVUE_DIR / "decisions.md"
INVARIANTS = DEJAVUE_DIR / "invariants.md"
PATTERNS = DEJAVUE_DIR / "patterns.md"
HANDOFF = DEJAVUE_DIR / "handoff.md"
CONTEXT = DEJAVUE_DIR / "context.md"
REFERENCES = DEJAVUE_DIR / "references"
JAGENT_DIR = Path(".planning")
FTS_DB = DEJAVUE_DIR / "fts.db"
EMBEDDINGS = DEJAVUE_DIR / "embeddings.jsonl"
INGESTED_LOCK = DEJAVUE_DIR / "ingested.lock"
FIRST_USE = DEJAVUE_DIR / ".first-use"
EMBEDDER_CIRCUIT = DEJAVUE_DIR / "embedder_circuit.json"

HAS_FTS5 = None  # probed lazily on first db open

# Semantic recall (v0.2+). DEJAVUE_EMBEDDER_URL="auto" (or unset) tries ollama
# first, then OpenAI (if OPENAI_API_KEY is set), then disables embedding.
# Set DEJAVUE_EMBEDDER_URL to a full URL to pin a specific endpoint.
DEFAULT_EMBEDDER_URL = "http://localhost:11434/v1/embeddings"
DEFAULT_EMBEDDER_MODEL = "nomic-embed-text"
EMBEDDER_TIMEOUT_S = 5.0

# Valid event sub-types for decision/note commands (stored as "event_type" field).
DECISION_TYPES = {"decision", "blocker", "claim", "question", "experiment", "checkpoint"}
NOTE_TYPES     = {"note", "blocker", "claim", "question", "observation"}

# ── DCP (DejaVue Context Protocol) ─────────────────────────────────────────────
# context.md is the DCP instruction-layer source of truth; adapters are generated
# non-destructively from it (D2/internal session). Everything here is optional and additive —
# the base memory loop (init/start/decision/state/handoff) is unchanged without it.
DCP_VERSION = "DCP/1.0"

# target name → default output path (the tool's REAL file). Overridable per-repo
# via .dejavue/config keys `target_<name> = <path>`.
EXPORT_TARGETS = {
    "claude":  "CLAUDE.md",
    "codex":   "AGENTS.md",
    "gemini":  "GEMINI.md",
    "copilot": ".github/copilot-instructions.md",
    "cursor":  ".cursor/rules",
}

# Managed-block markers. The fenced region between begin/end is the ONLY part
# export ever rewrites; hand-written content outside it is preserved verbatim.
_DCP_BEGIN_RE = re.compile(
    r"<!-- dejavue:begin DCP/[^\s]+ src=context\.md hash=(?P<hash>[0-9a-f]+) -->"
)
_DCP_BLOCK_RE = re.compile(
    r"<!-- dejavue:begin DCP/[^>]*?-->.*?<!-- dejavue:end -->\n?",
    re.DOTALL,
)


def parse_frontmatter(text):
    """Parse a minimal `key: value` frontmatter block delimited by `---` lines.

    Stdlib-only (no YAML dependency): supports flat `key: value` pairs, ignores
    blank lines and `#` comments inside the block. Returns (meta_dict, body_str).
    If there is no well-formed frontmatter, returns ({}, text) unchanged. Shared
    by context.md metadata (M1) and reference frontmatter (M5)."""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines(keepends=True)
    if lines[0].strip() != "---":
        return {}, text
    meta = {}
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break
        stripped = lines[i].strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped:
            k, _, v = stripped.partition(":")
            meta[k.strip()] = v.strip()
    if end_idx is None:
        return {}, text  # no closing delimiter — treat the whole thing as body
    return meta, "".join(lines[end_idx + 1:])

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


def normalize_entities(args):
    """Normalize the optional repeatable --entity flag into a sorted-unique list of
    kebab-case subject strings ("Auth System" -> "auth-system"). Returns [] if none.
    Deliberately just strings — NOT a graph or registry (Axiom 0)."""
    raw = getattr(args, "entity", None) or []
    seen, out = set(), []
    for e in raw:
        norm = "-".join(str(e).strip().lower().split())
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out


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
    sources = [TIMELINE, STATE, DECISIONS, HANDOFF, INVARIANTS, PATTERNS]
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
                        ev.get("event_type", ""),  # enables recall "blocker"/"question"/etc.
                        " ".join(ev.get("entities") or []),  # enables recall by entity
                        ev.get("confidence", ""),  # enables recall "speculative"/"verified"/etc.
                    ]
                    text = " ".join(p for p in parts if p)
                    rows.append((ev.get("ts", ""), ev.get("event", ""), text, "timeline.jsonl"))
                except json.JSONDecodeError:
                    pass

        for path, label in [(STATE, "state.md"), (DECISIONS, "decisions.md"), (HANDOFF, "handoff.md"), (INVARIANTS, "invariants.md"), (PATTERNS, "patterns.md")]:
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

    if not INVARIANTS.exists():
        INVARIANTS.write_text("# Invariants\n\n", encoding="utf-8")

    if not PATTERNS.exists():
        PATTERNS.write_text("# Patterns\n\n", encoding="utf-8")

    if not HANDOFF.exists():
        HANDOFF.write_text(
            "# Handoff\n\nRead `.dejavue/state.md`, `.dejavue/decisions.md`,"
            " and `.dejavue/timeline.jsonl` before making changes.\n",
            encoding="utf-8",
        )

    # DCP instruction layer (optional/additive — its absence breaks nothing).
    _scaffold_context()

    if getattr(args, "wizard", False):
        _run_wizard(resolve_agent(args.agent))

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

        # post-checkout hook — prints status on branch switch (not file checkout)
        checkout_path = hooks_dir / "post-checkout"
        checkout_marker = "#!/usr/bin/env bash\n# dejavue post-checkout"
        if checkout_path.exists():
            if not checkout_path.read_text(encoding="utf-8").startswith(checkout_marker):
                if args.force:
                    _write_checkout_hook(checkout_path, checkout_marker)
                    print("Replaced existing post-checkout hook with dejavue hook.")
        else:
            _write_checkout_hook(checkout_path, checkout_marker)
            print(f"Installed post-checkout hook at {checkout_path}")

        _install_gitattributes(force=args.force)
        _install_gitignore()
    else:
        print("WARNING: not inside a git repo; skipping hook install.")

    append_event({
        "agent": resolve_agent(args.agent),
        "event": "init",
        "summary": "Initialized .dejavue/ memory scaffold.",
    })

    _install_discovery(force=getattr(args, "force", False))

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


def _write_checkout_hook(hook_path, marker):
    script_path = Path(sys.argv[0]).resolve()
    # $3 == 1 means branch switch (not file checkout); skip otherwise to avoid noise.
    script = (
        marker + "\n"
        "[ \"$3\" = \"1\" ] || exit 0\n"
        f'python3 "{script_path}" status 2>/dev/null || true\n'
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
    ".dejavue/invariants.md  merge=union",
    ".dejavue/patterns.md    merge=union",
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


_CLAUDE_MD_MARKER = "<!-- dejavue:discovery -->"
_CLAUDE_MD_BOOT = """\

## Project memory

This repo uses [dejavue](https://github.com/nixpt/dejavue) for persistent architectural context.
Run `dejavue context` before making changes.
Fallback if not on PATH: `python3 .dejavue/dejavue context`

{marker}
""".format(marker=_CLAUDE_MD_MARKER)


def _install_discovery(force=False):
    """Install in-repo agent discovery: skill fallback + CLAUDE.md boot stub.

    Called automatically by init. Idempotent — safe to call multiple times.
    Skill install is best-effort (silently skipped if skills/ not found).
    """
    import shutil as _shutil

    # --- in-repo skill fallback (copy so they travel with the repo) ---
    script_dir = Path(sys.argv[0]).resolve().parent
    skills_src = script_dir / "skills"
    if not skills_src.exists():
        skills_src = script_dir.parent / "skills"

    if skills_src.exists():
        skill_dirs = [d for d in sorted(skills_src.iterdir())
                      if d.is_dir() and (d / "SKILL.md").exists()]
        installed = 0
        for skill_dir in skill_dirs:
            dest = DEJAVUE_DIR / skill_dir.name
            if dest.exists() and not force:
                continue
            if dest.is_symlink() or dest.is_file():
                dest.unlink()
            elif dest.is_dir():
                _shutil.rmtree(dest)
            _shutil.copytree(skill_dir, dest)
            installed += 1
        if installed:
            print(f"  ✓  Installed {installed} skill(s) to .dejavue/ (in-repo fallback)")

    # --- CLAUDE.md boot stub ---
    claude_md = Path("CLAUDE.md")
    if claude_md.exists():
        content = claude_md.read_text(encoding="utf-8")
        if _CLAUDE_MD_MARKER in content or "dejavue context" in content:
            return  # already wired, skip
        with claude_md.open("a", encoding="utf-8") as fh:
            fh.write(_CLAUDE_MD_BOOT)
        print("  ✓  Appended dejavue boot stub to CLAUDE.md")
    else:
        claude_md.write_text("# Project\n" + _CLAUDE_MD_BOOT, encoding="utf-8")
        print("  ✓  Created CLAUDE.md with dejavue boot stub")


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


def _context_template(name="", purpose=""):
    """Return an empty DCP context.md template with `key: value` frontmatter."""
    return (
        "---\n"
        f"name: {name}\n"
        f"purpose: {purpose}\n"
        f"dcp: {DCP_VERSION}\n"
        "---\n\n"
        "# Context\n\n"
        "<!-- The DCP instruction layer: what an agent should *do* in this repo.\n"
        "     Source of truth — adapters (CLAUDE.md / AGENTS.md / …) are generated\n"
        "     from this file via `dejavue export --target <tool>`. -->\n\n"
        "## Operating Rules\n\n"
        "- \n\n"
        "## Build / Test\n\n"
        "- \n\n"
        "## Architecture Map\n\n"
        "- \n\n"
        "## Memory\n\n"
        "Decisions, blockers, and constraints are captured in `.dejavue/` — run\n"
        "`dejavue context` for the boot packet and `dejavue recall <query>` to search.\n"
    )


def _scaffold_context():
    """Create .dejavue/context.md from the empty template if absent. Idempotent."""
    if CONTEXT.exists():
        return
    name = ""
    try:
        name = Path.cwd().name
    except Exception:
        pass
    CONTEXT.write_text(_context_template(name=name), encoding="utf-8")


def _run_wizard(agent_default):
    """3-question seed for context.md + state.md. Skippable / non-interactive:
    on EOF (no tty, piped /dev/null) every answer falls back to its default."""
    repo = ""
    try:
        repo = Path.cwd().name
    except Exception:
        pass

    def ask(prompt, default):
        try:
            ans = input(prompt).strip()
        except EOFError:
            ans = ""
        return ans or default

    print("dejavue init --wizard — 3 questions (Enter accepts the default):\n")
    ptype   = ask(f"  1. Project type [{repo}]? ", repo)
    agent   = ask(f"  2. Primary agent [{agent_default}]? ", agent_default)
    purpose = ask("  3. Purpose (one line) []? ", "")

    CONTEXT.write_text(_context_template(name=ptype, purpose=purpose), encoding="utf-8")
    STATE.write_text(
        f"# State\n\nUpdated: {now()}\n\n"
        f"Project: {ptype}. Primary agent: {agent}."
        + (f" Purpose: {purpose}." if purpose else "") + "\n",
        encoding="utf-8",
    )
    append_event({
        "agent": agent,
        "event": "wizard",
        "summary": f"init --wizard seeded context.md + state.md (type={ptype}, agent={agent})",
    })
    print("\nSeeded context.md + state.md from wizard answers.")


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
    event_type = getattr(args, "event_type", "decision") or "decision"
    if event_type not in DECISION_TYPES:
        print(f"Unknown --type '{event_type}'. Valid: {', '.join(sorted(DECISION_TYPES))}")
        return
    rejected = []
    if args.rejected:
        for r in args.rejected:
            if ": " in r:
                opt, reason = r.split(": ", 1)
            else:
                opt, reason = r, ""
            rejected.append({"option": opt, "reason": reason})

    supersedes = getattr(args, "supersedes", None) or ""
    durability = getattr(args, "durability", None) or ""
    confidence = getattr(args, "confidence", None) or ""

    type_label = f"[{event_type.upper()}] " if event_type != "decision" else ""
    dur_label = f"[{durability.upper()}] " if durability else ""
    conf_label = f"[{confidence.upper()}] " if confidence else ""
    entry = f"\n## {ts} — {dur_label}{conf_label}{type_label}{args.title}\n\nReason:\n{args.reason}\n"
    if supersedes:
        entry += f"\nSupersedes: {supersedes}\n"
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
        "event_type": event_type,
        "decision_title": args.title,
        "decision_reason": args.reason,
        "summary": f"{event_type.capitalize()}: {args.title}",
        "rejected_alternatives": rejected,
        "outcome": args.outcome or "",
        "supersedes": supersedes,
        "durability": durability,
        "confidence": confidence,
        "entities": normalize_entities(args),
    })
    print(f"{event_type.capitalize()} recorded: {args.title}")


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

    # DCP instruction layer first (if present) — surfaces frontmatter + body.
    if CONTEXT.exists():
        ctx_text = CONTEXT.read_text(encoding="utf-8")
        meta, _ = parse_frontmatter(ctx_text)
        label = "context.md"
        if meta.get("dcp"):
            label += f"  [{meta['dcp']}]"
        print(f"--- {label} ---\n")
        print(ctx_text)

    for path, label in [(HANDOFF, "handoff.md"), (STATE, "state.md"), (DECISIONS, "decisions.md"), (INVARIANTS, "invariants.md"), (PATTERNS, "patterns.md")]:
        if path.exists():
            print(f"--- {label} ---\n")
            print(path.read_text(encoding="utf-8"))

    # Traps & incidents surface prominently — not just in the last-N timeline tail — because
    # they are the highest-value memory the feature exists to preserve (a trap/incident must
    # not scroll out of view once a handful of newer events accrue).
    if TIMELINE.exists():
        hazards = []
        for line in TIMELINE.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(ev, dict) and ev.get("event") in ("trap", "incident"):
                hazards.append(ev)
        if hazards:
            print("--- traps & incidents ---\n")
            for ev in hazards:
                print(f"  [{ev.get('event','')}] {ev.get('summary','')}")
            print()

    if REFERENCES.exists():
        refs = sorted(REFERENCES.glob("*.md"))
        if refs:
            print("--- references ---\n")
            for ref in refs:
                title = _ref_title(ref.read_text(encoding="utf-8"), fallback=ref.stem)
                print(f"  {ref.name}  ({title})")
                print()

    if TIMELINE.exists():
        n = getattr(args, "n", 10) or 10
        print(f"--- recent timeline (last {n}) ---\n")
        lines = TIMELINE.read_text(encoding="utf-8").splitlines()[-n:]
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
    """Health check: JSONL validity, hook installation, gitattributes, FTS freshness.
    Pass --fix to auto-repair hooks, .gitattributes, .gitignore, and stale FTS."""
    ok = True
    fix = getattr(args, "fix", False)
    fixed = []

    def _report(status, label, detail="", fix_fn=None):
        nonlocal ok
        sym = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}.get(status, "?")
        if fix and fix_fn and status in ("WARN", "FAIL"):
            try:
                fix_fn()
                fixed.append(label)
                sym = "↻"
                detail = "auto-fixed"
            except Exception as e:
                detail = f"fix failed: {e}"
        line = f"  {sym} {label}"
        if detail:
            line += f"  — {detail}"
        print(line)
        if status == "FAIL" and sym != "↻":
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

        for hook_name, hmarker, write_fn in [
            ("post-commit",  "dejavue auto-capture", lambda p: _write_hook(p, "#!/usr/bin/env bash\n# dejavue auto-capture")),
            ("pre-push",     "dejavue pre-push",     lambda p: _write_prepush_hook(p, "#!/usr/bin/env bash\n# dejavue pre-push")),
            ("post-checkout", "dejavue post-checkout", lambda p: _write_checkout_hook(p, "#!/usr/bin/env bash\n# dejavue post-checkout")),
        ]:
            hook_path = git_dir / "hooks" / hook_name
            if not hook_path.exists():
                _report("WARN", f"{hook_name} hook", "not installed — run: dejavue init",
                        fix_fn=lambda p=hook_path, fn=write_fn: fn(p))
            else:
                content = hook_path.read_text(encoding="utf-8")
                if hmarker not in content:
                    _report("WARN", f"{hook_name} hook", "exists but not a dejavue hook")
                elif script_path not in content:
                    _report("WARN", f"{hook_name} hook", f"points to a different dejavue path (expected {script_path})",
                            fix_fn=lambda p=hook_path, fn=write_fn: fn(p))
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
        _report("WARN", ".gitattributes", "merge=union not configured — run: dejavue init",
                fix_fn=lambda: _install_gitattributes())

    # .gitignore
    gi = Path(".gitignore")
    if gi.exists() and _GITIGNORE_MARKER in gi.read_text(encoding="utf-8"):
        _report("PASS", ".gitignore entries")
    else:
        _report("WARN", ".gitignore", "dejavue entries missing — run: dejavue init",
                fix_fn=_install_gitignore)

    # FTS
    if FTS_DB.exists():
        if fts_needs_rebuild():
            _report("WARN", "fts.db", "stale — will rebuild on next recall",
                    fix_fn=rebuild_fts)
        else:
            _report("PASS", "fts.db", "up to date")
    else:
        _report("WARN", "fts.db", "not yet built — will build on first recall",
                fix_fn=rebuild_fts)

    # references/map.md
    map_file = REFERENCES / "map.md"
    if map_file.exists():
        _report("PASS", "references/map.md")
    elif REFERENCES.exists():
        _report("WARN", "references/map.md", "missing — run: dejavue init --map or ingest --generate-map")
    else:
        _report("WARN", "references/", "directory not created")

    # DCP adapter staleness — compare stored hash= in each managed block against
    # the current context.md hash. (Only when context.md exists.)
    if CONTEXT.exists():
        current_hash = _context_hash(CONTEXT.read_text(encoding="utf-8"))
        for name in EXPORT_TARGETS:
            path = _target_path(name)
            if not path.exists():
                continue
            m = _DCP_BEGIN_RE.search(path.read_text(encoding="utf-8"))
            if not m:
                continue
            if m.group("hash") == current_hash:
                _report("PASS", f"adapter {path}", "in sync with context.md")
            else:
                _report("WARN", f"adapter {path}",
                        "context.md changed — adapters stale; re-run: "
                        f"dejavue export --target {name}")

    print()
    if fixed:
        print(f"Auto-fixed {len(fixed)} item(s): {', '.join(fixed)}")
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
    ent_q = "-".join(path.strip().lower().split())  # also match a normalized entity name

    relevant = []
    for ev in events:
        hit = (
            path in ev.get("path", "")
            or path in ev.get("summary", "")
            or path in ev.get("decision_reason", ev.get("reason", ""))
            or path in ev.get("decision_title", ev.get("decision", ""))
            or path in ev.get("content", "")
            or ent_q in (ev.get("entities") or [])
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
    event_type = getattr(args, "event_type", "note") or "note"
    if event_type not in NOTE_TYPES:
        print(f"Unknown --type '{event_type}'. Valid: {', '.join(sorted(NOTE_TYPES))}")
        return
    append_event({
        "agent": resolve_agent(args.agent),
        "event": "note",
        "event_type": event_type,
        "summary": args.text,
        "tag": args.tag or "",
        "confidence": getattr(args, "confidence", None) or "",
        "entities": normalize_entities(args),
    })
    print(f"{event_type.capitalize()} recorded.")


def cmd_rejected(args):
    """Show all decisions that have rejected alternatives, optionally filtered by a topic."""
    query = (args.query or "").lower().strip()
    events = _load_events()
    hits = []
    for ev in events:
        ras = ev.get("rejected_alternatives") or []
        if not ras:
            continue
        if query:
            text = " ".join(
                (r.get("option", "") + " " + r.get("reason", "")).lower()
                for r in ras
            ) + " " + ev.get("decision_title", "").lower() + " " + ev.get("decision_reason", "").lower()
            if query not in text:
                continue
        hits.append(ev)

    if not hits:
        msg = f"No rejected alternatives found" + (f" mentioning '{args.query}'" if query else "") + "."
        print(msg)
        return

    header = f"Rejected alternatives" + (f" mentioning '{args.query}'" if query else "") + f" ({len(hits)} decision(s)):\n"
    print(header)
    for ev in hits:
        ts = (ev.get("ts") or "")[:10]
        title = ev.get("decision_title", "(untitled)")
        print(f"  [{ts}] {title}")
        for r in (ev.get("rejected_alternatives") or []):
            opt = r.get("option", "")
            reason = r.get("reason", "")
            line = f"    ✗ {opt}"
            if reason:
                line += f": {reason}"
            print(line)
        print()


def cmd_trap(args):
    """Record a known lie / trap — misleading name, fake abstraction, dangerous assumption."""
    append_event({
        "agent": resolve_agent(args.agent),
        "event": "trap",
        "summary": args.text,
        "tag": args.tag or "",
        "entities": normalize_entities(args),
    })
    print("Trap recorded.")


def cmd_incident(args):
    """Record an operational incident — outage, data corruption, failed migration."""
    append_event({
        "agent": resolve_agent(args.agent),
        "event": "incident",
        "summary": args.text,
        "tag": args.tag or "",
        "entities": normalize_entities(args),
    })
    print("Incident recorded.")


def cmd_invariant(args):
    """Record an architectural invariant and append to invariants.md."""
    DEJAVUE_DIR.mkdir(exist_ok=True)
    if not INVARIANTS.exists():
        INVARIANTS.write_text("# Invariants\n\n", encoding="utf-8")
    ts = now()
    entry = f"\n## {ts}\n\n{args.text}\n"
    with INVARIANTS.open("a", encoding="utf-8") as f:
        f.write(entry)
    append_event({
        "agent": resolve_agent(args.agent),
        "event": "invariant",
        "summary": args.text,
        "tag": args.tag or "",
        "entities": normalize_entities(args),
    })
    print("Invariant recorded.")


def cmd_pattern(args):
    """Record a discovered convention/pattern and append to patterns.md."""
    DEJAVUE_DIR.mkdir(exist_ok=True)
    if not PATTERNS.exists():
        PATTERNS.write_text("# Patterns\n\n", encoding="utf-8")
    ts = now()
    entry = f"\n## {ts}\n\n{args.text}\n"
    with PATTERNS.open("a", encoding="utf-8") as f:
        f.write(entry)
    append_event({
        "agent": resolve_agent(args.agent),
        "event": "pattern",
        "summary": args.text,
        "tag": args.tag or "",
        "entities": normalize_entities(args),
    })
    print("Pattern recorded.")


def cmd_since(args):
    ref = args.ref
    since_ts = None
    since_commit = None
    until_ts = None
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
    elif ".." in ref:
        # git revision range e.g. main..HEAD, v1.0..v2.0, origin/main..HEAD
        base, _, tip = ref.partition("..")
        tip = tip or "HEAD"
        ts_raw = git_run("git", "log", "-1", "--format=%aI", base)
        if not ts_raw:
            print(f"Cannot resolve '{base}' in range '{ref}'.")
            return
        since_ts = ts_raw
        since_commit = base
        since_label = f"range {ref}"
        # override git output to use the explicit range, not base..HEAD
        _range_override = ref
        # bound the event window by the tip's date too, unless tip is HEAD (open-ended "up to now")
        if tip != "HEAD":
            until_ts = git_run("git", "log", "-1", "--format=%aI", tip) or None
    else:
        ts_raw = git_run("git", "log", "-1", "--format=%aI", ref)
        if not ts_raw:
            print(f"Cannot resolve '{ref}' as a commit hash.")
            return
        since_ts = ts_raw
        since_commit = ref
        since_label = f"commit {ref} ({since_ts[:10]})"
    _range_override = locals().get("_range_override")

    print(f"Since {since_label}:\n")

    if since_commit:
        git_range = _range_override if _range_override else f"{since_commit}..HEAD"
        git_log = git_run("git", "log", "--oneline", git_range)
        git_stat = git_run("git", "diff", "--stat", git_range)
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
    # Compare at second granularity on both sides: the event ts carries a tz suffix
    # (…:18-05:00) past char 19, which would otherwise sort AFTER the 19-char bound and
    # drop events in the boundary second from the upper bound.
    window = [ev for ev in events if ev.get("ts", "")[:19] >= since_ts[:19]
              and (until_ts is None or ev.get("ts", "")[:19] <= until_ts[:19])]

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

    notes_in_window = [ev for ev in window if ev.get("event") == "note"]
    if notes_in_window:
        print(f"\nNotes ({len(notes_in_window)}):")
        for ev in notes_in_window:
            ts = (ev.get("ts") or "")[:19]
            tag = f" #{ev['tag']}" if ev.get("tag") else ""
            etype = f" [{ev['event_type']}]" if ev.get("event_type") and ev["event_type"] != "note" else ""
            print(f"  [{ts}]{etype}{tag} {ev.get('summary','')}")

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
    val = os.environ.get("DEJAVUE_EMBEDDER_URL", "")
    if val and val != "auto":
        return val
    cfg = _load_config()
    if cfg.get("embedder_url") and cfg["embedder_url"] != "auto":
        return cfg["embedder_url"]
    # Auto-detect: try ollama, then OpenAI, then ""
    return _auto_detect_embedder_url() or DEFAULT_EMBEDDER_URL


def _embedder_model() -> str:
    val = os.environ.get("DEJAVUE_EMBEDDER_MODEL", "")
    if val:
        return val
    cfg = _load_config()
    return cfg.get("embedder_model", "") or DEFAULT_EMBEDDER_MODEL


def _auto_detect_embedder_url() -> str:
    """Return the first available embedder URL, or "" if none reachable."""
    # 1. Ollama (local)
    ollama_url = "http://localhost:11434/v1/embeddings"
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/version",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=1.0):
            return ollama_url
    except Exception:
        pass
    # 2. OpenAI (if key available)
    if os.environ.get("OPENAI_API_KEY"):
        return "https://api.openai.com/v1/embeddings"
    return ""


def _embed_one(text):
    """POST an OpenAI-compatible /v1/embeddings request. Returns vec or None on any failure.
    Respects the circuit breaker — returns None immediately when the circuit is open.
    Automatically sets Authorization header when endpoint is OpenAI."""
    if not text:
        return None
    if _circuit_open():
        return None
    url = _embedder_url()
    model = _embedder_model()
    body = json.dumps({"model": model, "input": text}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if "openai.com" in url:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        url,
        data=body,
        headers=headers,
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


def _read_embeddings_cache(model_filter=None):
    """Return {hash: vec} from embeddings.jsonl.
    If model_filter is given, only return entries matching that model
    (prevents silently using stale vectors when the model changes)."""
    if not EMBEDDINGS.exists():
        return {}
    active_model = model_filter or _embedder_model()
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
        row_model = row.get("model", "")
        # Accept entries with matching model or no model field (legacy)
        if isinstance(h, str) and isinstance(vec, list):
            if not row_model or row_model == active_model:
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


def cmd_stats(args):
    """Timeline statistics: event counts by type and by agent, date range."""
    events = _load_events()
    if not events:
        print("No events in timeline.")
        return

    dates = [ev.get("ts", "")[:10] for ev in events if ev.get("ts")]
    by_type = {}
    by_agent = {}
    by_etype = {}  # event_type field (decision sub-types)
    by_tag = {}

    for ev in events:
        t = ev.get("event", "?")
        by_type[t] = by_type.get(t, 0) + 1
        a = ev.get("agent") or "unknown"
        by_agent[a] = by_agent.get(a, 0) + 1
        et = ev.get("event_type", "")
        if et and et not in (t, ""):
            by_etype[et] = by_etype.get(et, 0) + 1
        tag = ev.get("tag", "")
        if tag:
            by_tag[tag] = by_tag.get(tag, 0) + 1

    print("Timeline statistics:\n")
    print(f"  Total events : {len(events)}")
    if dates:
        print(f"  Date range   : {min(dates)} – {max(dates)}")
    if TIMELINE.exists():
        size_kb = TIMELINE.stat().st_size // 1024
        print(f"  File size    : {size_kb} KB")

    print("\n  By event type:")
    for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
        bar = "█" * min(count, 40)
        print(f"    {t:<20} {count:>4}  {bar}")

    if by_etype:
        print("\n  By sub-type (event_type field):")
        for et, count in sorted(by_etype.items(), key=lambda x: -x[1]):
            print(f"    {et:<20} {count:>4}")

    print("\n  By agent:")
    for a, count in sorted(by_agent.items(), key=lambda x: -x[1]):
        print(f"    {a:<20} {count:>4}")

    if by_tag:
        print("\n  By tag:")
        for tag, count in sorted(by_tag.items(), key=lambda x: -x[1]):
            print(f"    #{tag:<19} {count:>4}")


def cmd_import(args):
    """Bootstrap context.md from an existing hand-written instruction file.

    Lossless: the source file's full content is preserved as the body of
    context.md. Provenance (source path + git blob sha) is recorded both in the
    frontmatter and as a timeline event. This is the SAFE step before `export`."""
    src = Path(args.file)
    if not src.exists():
        print(f"{src} does not exist.")
        sys.exit(1)

    DEJAVUE_DIR.mkdir(exist_ok=True)
    if CONTEXT.exists() and not getattr(args, "force", False):
        existing = CONTEXT.read_text(encoding="utf-8")
        # A pristine init-scaffolded template is safe to overwrite; a filled-in
        # context.md is not (would lose hand-written instruction content).
        if "## Operating Rules\n\n- \n" not in existing:
            print(f"{CONTEXT} already exists and looks populated. "
                  "Use --force to overwrite.")
            sys.exit(1)

    content = src.read_text(encoding="utf-8", errors="replace")
    # git blob sha of the source for provenance (empty string if not tracked).
    src_sha = git_run("git", "hash-object", str(src))[:12]

    meta, _ = parse_frontmatter(content)
    if meta.get("dcp"):
        # Source already carries DCP frontmatter — keep it verbatim (lossless).
        new_text = content
    else:
        name = ""
        try:
            name = Path.cwd().name
        except Exception:
            pass
        fm = (
            "---\n"
            f"name: {name}\n"
            f"purpose: imported from {src}\n"
            f"dcp: {DCP_VERSION}\n"
            f"source: {src}\n"
            f"source_sha: {src_sha}\n"
            "---\n\n"
        )
        new_text = fm + content

    CONTEXT.write_text(new_text, encoding="utf-8")
    append_event({
        "agent": resolve_agent(getattr(args, "agent", None)),
        "event": "import",
        "source": str(src),
        "source_sha": src_sha,
        "summary": f"Imported {src} into context.md (lossless; provenance sha={src_sha or 'untracked'})",
    })
    print(f"Imported {src} → {CONTEXT} ({len(content)} bytes, lossless). "
          f"Provenance sha={src_sha or 'untracked'}.")


def cmd_promote(args):
    """Graduate a .dejavue/ into a richer per-repo planning system (.planning/)
    WITHOUT losing history. Copies (never moves) every memory artifact and
    records provenance; the .dejavue/ log stays canonical (non-destructive)."""
    if args.to != "planning":
        print(f"Unknown --to '{args.to}'. Supported: planning")
        sys.exit(1)
    if not DEJAVUE_DIR.exists():
        print("Nothing to promote — no .dejavue/. Run: dejavue init")
        sys.exit(1)

    JAGENT_DIR.mkdir(exist_ok=True)
    force = getattr(args, "force", False)

    # Spec'd mapping: .dejavue/<x> → .planning/<x> (1:1 copy, lossless).
    mapping = [
        (CONTEXT,                JAGENT_DIR / "context.md"),
        (STATE,                  JAGENT_DIR / "state.md"),
        (DECISIONS,              JAGENT_DIR / "decisions.md"),
        (HANDOFF,                JAGENT_DIR / "handoff.md"),
        (TIMELINE,               JAGENT_DIR / "timeline.jsonl"),
        (DEJAVUE_DIR / "config", JAGENT_DIR / "config"),
    ]
    copied, skipped = [], []
    for src, dst in mapping:
        if not src.exists():
            continue
        if dst.exists() and not force:
            skipped.append(dst.name)
            continue
        dst.write_bytes(src.read_bytes())
        copied.append(dst.name)

    if REFERENCES.exists():
        jrefs = JAGENT_DIR / "references"
        jrefs.mkdir(exist_ok=True)
        for ref in sorted(REFERENCES.glob("*.md")):
            dst = jrefs / ref.name
            if dst.exists() and not force:
                skipped.append(f"references/{ref.name}")
                continue
            dst.write_bytes(ref.read_bytes())
            copied.append(f"references/{ref.name}")

    sha = git_run("git", "rev-parse", "--short", "HEAD") or "untracked"
    (JAGENT_DIR / "PROVENANCE.md").write_text(
        "# Promoted from .dejavue/\n\n"
        f"- Promoted: {now()}\n"
        f"- Source commit: {sha}\n"
        f"- Tool: dejavue {VERSION} ({DCP_VERSION})\n\n"
        "## Mapping\n\n"
        "| .dejavue/ | .planning/ |\n|---|---|\n"
        "| context.md | context.md |\n"
        "| state.md | state.md |\n"
        "| decisions.md | decisions.md |\n"
        "| handoff.md | handoff.md |\n"
        "| timeline.jsonl | timeline.jsonl |\n"
        "| config | config |\n"
        "| references/ | references/ |\n\n"
        "The `.dejavue/` log remains canonical; this is a non-destructive copy "
        "so history is never lost.\n",
        encoding="utf-8",
    )

    append_event({
        "agent": resolve_agent(getattr(args, "agent", None)),
        "event": "promote",
        "target": "planning",
        "summary": f"Promoted .dejavue/ → .planning/ ({len(copied)} artifacts copied, history preserved)",
    })
    print(f"Promoted .dejavue/ → .planning/ — copied {len(copied)} artifact(s).")
    if skipped:
        print(f"  Skipped (already exist; use --force): {', '.join(skipped)}")
    print("  .dejavue/ left intact — history preserved.")


def cmd_export(args):
    """Export dejavue memory as JSON/Markdown, or generate adapter targets."""
    if getattr(args, "target", None):
        return _export_adapters(args)

    fmt = getattr(args, "format", "json") or "json"

    events = _load_events()
    state_text = STATE.read_text(encoding="utf-8") if STATE.exists() else ""
    decisions_text = DECISIONS.read_text(encoding="utf-8") if DECISIONS.exists() else ""
    handoff_text = HANDOFF.read_text(encoding="utf-8") if HANDOFF.exists() else ""

    refs = {}
    if REFERENCES.exists():
        for ref in sorted(REFERENCES.glob("*.md")):
            refs[ref.name] = ref.read_text(encoding="utf-8")

    if fmt == "json":
        data = {
            "dejavue_version": VERSION,
            "exported_at": now(),
            "state": state_text,
            "handoff": handoff_text,
            "decisions": decisions_text,
            "references": refs,
            "events": events,
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))

    elif fmt == "md":
        out = [f"# Dejavue Memory Export\n\n_Exported {now()} by dejavue {VERSION}_\n"]

        if handoff_text:
            out.append(f"\n---\n\n{handoff_text}")
        if state_text:
            out.append(f"\n---\n\n{state_text}")
        if decisions_text:
            out.append(f"\n---\n\n{decisions_text}")
        for name, content in refs.items():
            out.append(f"\n---\n\n<!-- reference: {name} -->\n\n{content}")
        if events:
            out.append("\n---\n\n## Timeline\n\n")
            for ev in events:
                ts = (ev.get("ts") or "")[:19]
                kind = ev.get("event", "")
                agent = ev.get("agent", "")
                summary = ev.get("summary", "")
                out.append(f"- `{ts}` **{kind}** ({agent}) — {summary}\n")
        print("".join(out))

    else:
        print(f"Unknown format '{fmt}'. Valid: json, md")
        sys.exit(1)


def _target_path(name):
    """Resolve a target name to its output Path, honoring config overrides."""
    cfg = _load_config()
    override = cfg.get(f"target_{name}")
    return Path(override) if override else Path(EXPORT_TARGETS[name])


def _context_hash(text):
    """Stable short hash of the full context.md content (drives staleness)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _build_managed_block(context_text):
    """Render the managed block generated from context.md. Returns (block, hash)."""
    _, body = parse_frontmatter(context_text)
    h = _context_hash(context_text)
    begin = f"<!-- dejavue:begin {DCP_VERSION} src=context.md hash={h} -->"
    end = "<!-- dejavue:end -->"
    banner = ("<!-- GENERATED by `dejavue export` from .dejavue/context.md — "
              "edit context.md, not this block. -->")
    inner = body.strip("\n")
    return f"{begin}\n{banner}\n\n{inner}\n\n{end}\n", h


def _write_adapter(path, block_text, replace=False):
    """Write the managed block into an adapter target non-destructively.

    Returns one of: 'created' (target absent), 'updated' (existing managed block
    replaced in place), 'replaced' (whole unmarked file converted via --replace),
    'appended' (managed block appended to an unmarked hand-written file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(block_text, encoding="utf-8")
        return "created"

    existing = path.read_text(encoding="utf-8")
    if _DCP_BLOCK_RE.search(existing):
        new = _DCP_BLOCK_RE.sub(lambda _m: block_text, existing, count=1)
        path.write_text(new, encoding="utf-8")
        return "updated"

    # Unmarked, hand-written target — never clobber.
    if replace:
        path.write_text(block_text, encoding="utf-8")
        return "replaced"
    sep = "" if existing.endswith("\n") else "\n"
    path.write_text(existing + sep + "\n" + block_text, encoding="utf-8")
    return "appended"


def _export_adapters(args):
    """Generate adapter target file(s) from context.md (M3, non-destructive)."""
    if not CONTEXT.exists():
        print("No .dejavue/context.md to export from. "
              "Run `dejavue init` or `dejavue import <FILE>` first.")
        sys.exit(1)

    target = args.target
    if target == "all":
        names = list(EXPORT_TARGETS.keys())
    elif target in EXPORT_TARGETS:
        names = [target]
    else:
        print(f"Unknown --target '{target}'. "
              f"Valid: {', '.join(sorted(EXPORT_TARGETS))}, all")
        sys.exit(1)

    context_text = CONTEXT.read_text(encoding="utf-8")
    block_text, h = _build_managed_block(context_text)
    replace = getattr(args, "replace", False)

    for name in names:
        path = _target_path(name)
        status = _write_adapter(path, block_text, replace=replace)
        if status == "appended":
            print(f"WARNING: {path} has hand-written content with no dejavue "
                  "markers — appended a managed block at the end (use --replace "
                  "to convert the whole file).")
        verb = {
            "created": "created", "updated": "updated managed block in",
            "replaced": "replaced", "appended": "appended managed block to",
        }[status]
        print(f"  {name:<8} → {verb} {path}")
        append_event({
            "agent": resolve_agent(getattr(args, "agent", None)),
            "event": "export_adapter",
            "target": name,
            "path": str(path),
            "hash": h,
            "status": status,
            "summary": f"Exported context.md → {name} ({path}) [{status}, hash={h}]",
        })


def cmd_reference(args):
    """Manage reference cards in .dejavue/references/."""
    REFERENCES.mkdir(exist_ok=True)
    action = args.action

    if action == "list":
        refs = sorted(REFERENCES.glob("*.md"))
        type_filter = getattr(args, "type", None)
        if not refs:
            print(f"No reference cards in {REFERENCES}")
            print("Create one with: dejavue reference create <name>")
            return
        shown = 0
        for ref in refs:
            text = ref.read_text(encoding="utf-8")
            meta, _ = parse_frontmatter(text)
            if type_filter and meta.get("type") != type_filter:
                continue
            title = _ref_title(text, fallback=ref.stem)
            type_tag = f"  [{meta['type']}]" if meta.get("type") else ""
            print(f"  {ref.stem:<20}  {title[:60]}{type_tag}")
            shown += 1
        if type_filter and shown == 0:
            print(f"No reference cards with type '{type_filter}'.")

    elif action == "create":
        name = args.name
        if not name.endswith(".md"):
            name += ".md"
        path = REFERENCES / name
        if path.exists() and not getattr(args, "force", False):
            print(f"{path} already exists. Use --force to overwrite.")
            return
        title = getattr(args, "title", None) or args.name.replace("-", " ").replace("_", " ").title()
        if getattr(args, "content", None):
            body = args.content
        else:
            template = getattr(args, "template", "default")
            if template == "api":
                body = (
                    f"# {title}\n\n"
                    "<!-- API reference card -->\n\n"
                    "## Endpoint\n\n`METHOD /path`\n\n"
                    "## Parameters\n\n| Name | Type | Required | Description |\n|---|---|---|---|\n\n"
                    "## Example\n\n```\n\n```\n\n"
                    "## Notes\n\n"
                )
            elif template == "design":
                body = (
                    f"# {title}\n\n"
                    "<!-- Design reference card -->\n\n"
                    "## Overview\n\n\n\n"
                    "## Key invariants\n\n- \n\n"
                    "## Interfaces\n\n\n\n"
                    "## Why this design\n\n"
                )
            elif template == "glossary":
                body = (
                    "---\n"
                    "type: glossary\n"
                    f"dcp: {DCP_VERSION}\n"
                    "---\n\n"
                    f"# {title}\n\n"
                    "<!-- DCP glossary card: domain terms an agent must know.\n"
                    "     Surfaced by `dejavue context`. One term per row. -->\n\n"
                    "| Term | Definition |\n"
                    "|------|------------|\n"
                    "|      |            |\n"
                )
            else:  # default
                body = (
                    f"# {title}\n\n"
                    "<!-- Reference card: fill in and commit -->\n\n\n"
                )
        # If --type was given and the card has no frontmatter yet, inject it so
        # the card is filterable via `reference list --type` (M5).
        ref_type = getattr(args, "type", None)
        if ref_type:
            existing_meta, _ = parse_frontmatter(body)
            if not existing_meta:
                body = (f"---\ntype: {ref_type}\ndcp: {DCP_VERSION}\n---\n\n" + body)
        path.write_text(body, encoding="utf-8")
        append_event({
            "agent": resolve_agent(getattr(args, "agent", None)),
            "event": "reference_created",
            "summary": f"Created reference card: {args.name}",
            "path": str(path),
        })
        print(f"Created {path}")

    elif action == "update":
        name = args.name
        if not name.endswith(".md"):
            name += ".md"
        path = REFERENCES / name
        if not path.exists():
            print(f"{path} does not exist. Create it first: dejavue reference create {args.name}")
            return
        content = getattr(args, "content", None)
        if content is None:
            print("Provide --content TEXT to update the reference card.")
            return
        path.write_text(content, encoding="utf-8")
        append_event({
            "agent": resolve_agent(getattr(args, "agent", None)),
            "event": "reference_updated",
            "summary": f"Updated reference card: {args.name}",
            "path": str(path),
        })
        print(f"Updated {path}")

    elif action == "view":
        name = args.name
        if not name.endswith(".md"):
            name += ".md"
        path = REFERENCES / name
        if not path.exists():
            print(f"{path} does not exist.")
            return
        print(path.read_text(encoding="utf-8"))


def cmd_link(args):
    """Show dejavue events associated with a git commit SHA.
    Also reads git notes written by 'dejavue note-commit'."""
    sha = args.sha
    short = sha[:7]
    events = _load_events()

    related = [ev for ev in events if
               (ev.get("commit") or "")[:7] == short or
               short in (ev.get("summary") or "") or
               short in (ev.get("decision_reason") or "")]

    # Check git notes for additional links
    git_notes = git_run("git", "notes", "show", sha)
    dejavue_notes = [l for l in git_notes.splitlines() if l.startswith("Dejavue-Event:")]

    if not related and not dejavue_notes:
        print(f"No dejavue events recorded for commit {short}.")
        print("(Events are captured by the post-commit hook — run `dejavue init` to install it.)")
        print("(Manually link with: dejavue note-commit <sha>)")
        return

    print(f"Dejavue events for commit {short}:\n")
    for ev in related:
        ts = (ev.get("ts") or "")[:19]
        kind = ev.get("event", "")
        agent = ev.get("agent", "")
        summary = ev.get("summary", "")
        print(f"  [{ts}] {kind} ({agent})")
        if summary:
            print(f"    {summary}")
        print()
    if dejavue_notes:
        print("  (from git notes)")
        for n in dejavue_notes:
            print(f"    {n}")


def _ref_to_ts(ref):
    """Resolve a ref (ISO date or commit hash) to an ISO timestamp string, or None."""
    if re.match(r"^\d{4}-\d{2}-\d{2}", ref):
        return ref
    ts_raw = git_run("git", "log", "-1", "--format=%aI", ref)
    return ts_raw if ts_raw else None


def _git_show_file(ref, path):
    """Return content of path at git ref, or None if not found."""
    try:
        return subprocess.check_output(
            ["git", "show", f"{ref}:{path}"],
            text=True, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        return None


def cmd_diff(args):
    """Compare dejavue memory between two refs (dates, commit hashes, or git tags)."""
    from_ref = args.from_ref
    to_ref   = getattr(args, "to_ref", None) or "HEAD"

    # Machine-readable patch of the decisions delta (M5). Emits a clean unified
    # diff of decisions.md (and state.md) — no human-facing headers/summaries.
    if getattr(args, "format", None) == "patch":
        _diff_patch(from_ref, to_ref)
        return

    # Try resolving as timestamps first (for event-level diff)
    from_ts = _ref_to_ts(from_ref)
    to_ts   = _ref_to_ts(to_ref) if to_ref != "HEAD" else now()

    print(f"Dejavue diff  {from_ref}  →  {to_ref}\n")

    # ── git-object diff of state.md and decisions.md ──
    for filepath, label in [(".dejavue/state.md", "state.md"),
                             (".dejavue/decisions.md", "decisions.md")]:
        before = _git_show_file(from_ref, filepath)
        after  = _git_show_file(to_ref if to_ref != "HEAD" else "HEAD", filepath)

        if before is None and after is None:
            continue
        if before == after:
            print(f"  {label}: no change")
            continue

        before_lines = (before or "").splitlines(keepends=True)
        after_lines  = (after  or "").splitlines(keepends=True)
        delta = list(difflib.unified_diff(
            before_lines, after_lines,
            fromfile=f"a/{label}", tofile=f"b/{label}",
            lineterm="",
        ))
        if delta:
            print(f"--- {label} diff ---")
            for line in delta[:60]:  # cap at 60 lines to avoid wall of text
                print(line)
            if len(delta) > 60:
                print(f"  … ({len(delta) - 60} more lines)")
            print()

    # ── event diff (decisions added between the two timestamps) ──
    if from_ts:
        events = _load_events()
        # Pad bare dates to include the full day on both ends
        from_cmp = (from_ts[:10] + "T00:00:00") if len(from_ts) <= 10 else from_ts[:19]
        to_cmp   = (to_ts[:10]   + "T23:59:59") if len(to_ts)   <= 10 else to_ts[:19]
        window = [ev for ev in events if from_cmp <= ev.get("ts", "") <= to_cmp]
        new_decisions = [ev for ev in window if ev.get("event") == "decision"]
        new_notes     = [ev for ev in window if ev.get("event") == "note"]
        new_states    = [ev for ev in window if ev.get("event") == "state_update"]

        print(f"Events in window: {len(window)} total")
        if new_decisions:
            print(f"\nDecisions added ({len(new_decisions)}):")
            for ev in new_decisions:
                ts = (ev.get("ts") or "")[:10]
                etype = ev.get("event_type", "decision")
                label = f"[{etype.upper()}] " if etype != "decision" else ""
                print(f"  {ts}  {label}{ev.get('decision_title','')}")
        if new_notes:
            print(f"\nNotes added ({len(new_notes)}):")
            for ev in new_notes:
                ts = (ev.get("ts") or "")[:10]
                tag = f" #{ev['tag']}" if ev.get("tag") else ""
                print(f"  {ts}{tag}  {ev.get('summary','')}")
        if new_states:
            print(f"\nState updates ({len(new_states)}):")
            for ev in new_states:
                ts = (ev.get("ts") or "")[:10]
                print(f"  {ts}  {ev.get('summary','')[:80]}")


def _diff_patch(from_ref, to_ref):
    """Emit a machine-readable unified-diff patch of the memory-doc delta."""
    resolved_to = to_ref if to_ref != "HEAD" else "HEAD"
    any_out = False
    for filepath, label in [(".dejavue/decisions.md", "decisions.md"),
                            (".dejavue/state.md", "state.md")]:
        before = _git_show_file(from_ref, filepath)
        after  = _git_show_file(resolved_to, filepath)
        if before is None and after is None:
            continue
        if before == after:
            continue
        delta = difflib.unified_diff(
            (before or "").splitlines(keepends=True),
            (after or "").splitlines(keepends=True),
            fromfile=f"a/{label}", tofile=f"b/{label}",
            lineterm="",
        )
        for line in delta:
            print(line)
            any_out = True
    if not any_out:
        # Still valid (empty) patch output; signal via a comment on stderr.
        print(f"# no memory-doc delta between {from_ref} and {to_ref}", file=sys.stderr)


def cmd_timeline(args):
    """ASCII activity chart — events per day/week/month."""
    events = _load_events()
    if not events:
        print("No events in timeline.")
        return

    by = getattr(args, "by", "week") or "week"
    agent_filter = getattr(args, "agent", None)

    if agent_filter:
        events = [ev for ev in events if ev.get("agent") == agent_filter]

    # Group events by period
    buckets = {}
    for ev in events:
        ts = ev.get("ts", "")
        if not ts:
            continue
        if by == "day":
            key = ts[:10]
        elif by == "month":
            key = ts[:7]
        else:  # week — Monday of the ISO week
            try:
                d = datetime.fromisoformat(ts[:10])
                week_start = (d - __import__("datetime").timedelta(days=d.weekday())).strftime("%Y-%m-%d")
                key = week_start
            except ValueError:
                key = ts[:10]
        buckets[key] = buckets.get(key, 0) + 1

    if not buckets:
        print("No dated events found.")
        return

    max_count = max(buckets.values())
    bar_width  = 40
    label_w    = 12 if by == "week" else (7 if by == "month" else 10)

    period_label = {"day": "Date", "week": "Week", "month": "Month"}.get(by, "Period")
    print(f"Activity by {by}  (each █ ≈ {max(1, max_count // bar_width)} events)\n")
    print(f"  {period_label:<{label_w}}  {'':40}  Events")
    print(f"  {'─'*label_w}  {'─'*40}  {'─'*6}")

    for key in sorted(buckets):
        count = buckets[key]
        bar_len = max(1, round(count * bar_width / max_count))
        bar = "█" * bar_len
        print(f"  {key:<{label_w}}  {bar:<40}  {count}")

    total = sum(buckets.values())
    print(f"\n  Total: {total} events across {len(buckets)} {by}s")


def cmd_tag(args):
    """List all tags in the timeline, or filter events by tag."""
    events = _load_events()
    action = getattr(args, "action", "list")

    if action == "list":
        tag_counts = {}
        for ev in events:
            t = ev.get("tag", "")
            if t:
                tag_counts[t] = tag_counts.get(t, 0) + 1
        if not tag_counts:
            print("No tags recorded yet.")
            print("Add tags with: dejavue note '<text>' --tag <tag>")
            return
        print(f"Tags ({len(tag_counts)}):\n")
        for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
            print(f"  #{tag:<20} {count:>4} event{'s' if count != 1 else ''}")

    elif action == "filter":
        tag = args.tag
        matched = [ev for ev in events if ev.get("tag") == tag]
        if not matched:
            print(f"No events with tag '#{tag}'.")
            return
        print(f"Events tagged #{tag} ({len(matched)}):\n")
        for ev in matched:
            ts = (ev.get("ts") or "")[:19]
            kind = ev.get("event", "")
            summary = ev.get("summary", "")
            print(f"  [{ts}] {kind}  {summary}")


def cmd_entities(args):
    """List entities across the timeline, or show events referencing one entity."""
    events = _load_events()
    name = getattr(args, "name", None)

    if name:
        q = "-".join(name.strip().lower().split())
        matched = [ev for ev in events if q in (ev.get("entities") or [])]
        if not matched:
            print(f"No events reference entity '@{q}'.")
            return
        print(f"Events referencing @{q} ({len(matched)}):\n")
        for ev in matched:
            ts = (ev.get("ts") or "")[:19]
            kind = ev.get("event", "")
            summary = ev.get("summary", "")
            print(f"  [{ts}] {kind}  {summary}")
        return

    counts = {}
    for ev in events:
        for e in (ev.get("entities") or []):
            counts[e] = counts.get(e, 0) + 1
    if not counts:
        print("No entities recorded yet.")
        print("Tag events with: dejavue decision '<title>' --reason '...' --entity <name>")
        return
    print(f"Entities ({len(counts)}):\n")
    for e, c in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"  @{e:<24} {c:>4} event{'s' if c != 1 else ''}")


def cmd_note_commit(args):
    """Write a git note on a commit linking it to the most recent dejavue event.
    Uses 'git notes' — metadata stored outside the commit object, so the commit SHA is
    unchanged. The opt-in --trailer flag is the exception: it rewrites HEAD's message
    (changing its SHA), so it only targets HEAD and the note is attached afterwards."""
    sha = args.sha

    # Resolve short SHA to full
    full_sha = git_run("git", "rev-parse", "--verify", sha)
    if not full_sha:
        print(f"Cannot resolve '{sha}' as a git commit.")
        return

    want_trailer = getattr(args, "trailer", False)

    # --trailer amends the commit (new SHA), so it can only target HEAD and needs a clean index.
    # Validate up front so we never half-apply (note on one SHA, trailer on another).
    if want_trailer:
        head_sha = git_run("git", "rev-parse", "--verify", "HEAD")
        if full_sha != head_sha:
            print("--trailer can only amend HEAD (amending rewrites the commit's SHA).")
            print(f"'{sha}' resolves to {full_sha[:7]}, but HEAD is {(head_sha or '?')[:7]}.")
            print("Re-run without --trailer to write a git note to an older commit.")
            return
        # git commit --amend rebuilds HEAD's tree from the index; refuse if anything is staged,
        # otherwise staged changes get silently folded into the amended commit.
        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if staged.returncode != 0:
            print("Refusing to amend HEAD with --trailer: you have staged changes that would be")
            print("folded into the commit. Commit or unstage them first.")
            return

    # Find the most recent event (or the closest file_changed for this sha)
    events = _load_events()
    short = sha[:7]
    for_commit = [ev for ev in events if (ev.get("commit") or "")[:7] == short]
    latest = for_commit[-1] if for_commit else (events[-1] if events else None)

    if not latest:
        print("No dejavue events found — nothing to link.")
        return

    ts = (latest.get("ts") or "")[:19]
    summary = latest.get("summary", "")[:100]
    note_text = f"Dejavue-Event: {ts} | {summary}"

    if want_trailer:
        # Amend the message FIRST (this changes HEAD's SHA), then re-resolve so the note below
        # lands on the SHIPPED commit rather than the now-orphaned pre-amend object.
        try:
            orig_msg = git_run("git", "log", "-1", "--format=%B", full_sha)
            result = subprocess.run(
                ["git", "interpret-trailers", "--trailer", note_text],
                input=orig_msg, capture_output=True, text=True,
            )
            if result.returncode != 0:
                print(f"git interpret-trailers failed: {result.stderr.strip()}")
                return
            subprocess.check_call(
                ["git", "commit", "--amend", "--no-edit", "-m", result.stdout],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            print("Commit message amended with Dejavue-Event trailer.")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Failed to amend commit: {e}")
            return
        full_sha = git_run("git", "rev-parse", "--verify", "HEAD") or full_sha
        short = full_sha[:7]

    try:
        subprocess.check_call(
            ["git", "notes", "append", "-m", note_text, full_sha],
            stderr=subprocess.DEVNULL,
        )
        print(f"Git note written to {short}: {note_text}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to write git note: {e}")
        print("Ensure 'git notes' is available (git ≥ 2.0).")
        return


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


def _ref_title(text, fallback=""):
    """First markdown heading/line of a reference card, skipping frontmatter."""
    _, body = parse_frontmatter(text)
    for line in body.splitlines():
        if line.strip():
            return line.lstrip("# ").strip()
    return fallback


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


# ── Shell completion scripts ───────────────────────────────────────────────────

_BASH_COMPLETION = """\
# dejavue bash completion
# Install: dejavue completion bash | sudo tee /etc/bash_completion.d/dejavue
# Or per-user: dejavue completion bash >> ~/.bash_completion
_dejavue() {
    local cur prev words
    _init_completion || return
    local cmds="version init start changed decision state handoff context status \\
check archive roster config install-skill log blame note since ingest recall \\
worthiness get list annotate stats promote import export reference link search \\
diff timeline tag note-commit completion rejected trap incident invariant pattern entities"
    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=($(compgen -W "$cmds" -- "$cur"))
        return
    fi
    local subcmd="${COMP_WORDS[1]}"
    case "$subcmd" in
        decision)
            COMPREPLY=($(compgen -W "--reason --rejected --agent --type --tag --supersedes --durability --confidence --entity" -- "$cur"))
            if [[ "$prev" == "--type" ]]; then
                COMPREPLY=($(compgen -W "decision blocker claim question experiment checkpoint" -- "$cur"))
            elif [[ "$prev" == "--durability" ]]; then
                COMPREPLY=($(compgen -W "temporary tactical strategic constitutional" -- "$cur"))
            elif [[ "$prev" == "--confidence" ]]; then
                COMPREPLY=($(compgen -W "speculative proposed experimental adopted deprecated verified" -- "$cur"))
            fi ;;
        trap|incident|invariant|pattern) COMPREPLY=($(compgen -W "--agent --tag --entity" -- "$cur")) ;;
        note)
            COMPREPLY=($(compgen -W "--agent --tag --type --entity --confidence" -- "$cur"))
            if [[ "$prev" == "--type" ]]; then
                COMPREPLY=($(compgen -W "note blocker claim question observation" -- "$cur"))
            elif [[ "$prev" == "--confidence" ]]; then
                COMPREPLY=($(compgen -W "speculative proposed experimental adopted deprecated verified" -- "$cur"))
            fi ;;
        start)    COMPREPLY=($(compgen -W "--agent --goal" -- "$cur")) ;;
        state)    COMPREPLY=($(compgen -W "--summary --agent" -- "$cur")) ;;
        handoff)  COMPREPLY=($(compgen -W "--summary --next --agent" -- "$cur")) ;;
        context)  COMPREPLY=($(compgen -W "--lines" -- "$cur")) ;;
        since)    COMPREPLY=($(compgen -W "--agent --format" -- "$cur")) ;;
        log)      COMPREPLY=($(compgen -W "--since --agent --type --oneline --limit" -- "$cur")) ;;
        recall|search)
                  COMPREPLY=($(compgen -W "--since --agent --type --semantic --limit" -- "$cur")) ;;
        get)      COMPREPLY=($(compgen -W "state handoff decisions context references" -- "$cur")) ;;
        annotate) COMPREPLY=($(compgen -W "state handoff decisions" -- "$cur")) ;;
        check)    COMPREPLY=($(compgen -W "--fix" -- "$cur")) ;;
        archive)  COMPREPLY=($(compgen -W "--before --dry-run" -- "$cur")) ;;
        export)
            COMPREPLY=($(compgen -W "--format --target" -- "$cur"))
            if [[ "$prev" == "--format" ]]; then
                COMPREPLY=($(compgen -W "json md" -- "$cur"))
            elif [[ "$prev" == "--target" ]]; then
                COMPREPLY=($(compgen -W "claude codex gemini copilot cursor all" -- "$cur"))
            fi ;;
        import)   COMPREPLY=($(compgen -f -- "$cur")) ;;
        promote)
            COMPREPLY=($(compgen -W "--to" -- "$cur"))
            if [[ "$prev" == "--to" ]]; then
                COMPREPLY=($(compgen -W "planning" -- "$cur"))
            fi ;;
        diff)     COMPREPLY=($(compgen -W "--format" -- "$cur"))
            if [[ "$prev" == "--format" ]]; then
                COMPREPLY=($(compgen -W "text patch" -- "$cur"))
            fi ;;
        timeline) COMPREPLY=($(compgen -W "--since --width" -- "$cur")) ;;
        config)   COMPREPLY=($(compgen -W "list get set unset" -- "$cur")) ;;
        reference) COMPREPLY=($(compgen -W "list create update view" -- "$cur"))
            if [[ "$prev" == "create" || "$prev" == "update" ]]; then
                COMPREPLY=($(compgen -W "--type --tags" -- "$cur"))
            fi ;;
        tag)      COMPREPLY=($(compgen -W "list filter" -- "$cur")) ;;
        ingest)   COMPREPLY=($(compgen -W "--since --agent --dry-run" -- "$cur")) ;;
        completion) COMPREPLY=($(compgen -W "bash zsh fish" -- "$cur")) ;;
        install-skill) COMPREPLY=($(compgen -W "--dir --force" -- "$cur")) ;;
        init)     COMPREPLY=($(compgen -W "--wizard --force --map --no-hook" -- "$cur")) ;;
    esac
}
complete -F _dejavue dejavue
"""

_ZSH_COMPLETION = """\
#compdef dejavue
# dejavue zsh completion
# Install: dejavue completion zsh | sudo tee /usr/share/zsh/site-functions/_dejavue
# Or per-user (fpath must include the dir):
#   dejavue completion zsh > "${fpath[1]}/_dejavue"
_dejavue() {
    local state
    _arguments -C \\
        '1: :->subcmd' \\
        '*:: :->args' && return 0
    case $state in
        subcmd)
            local subcommands=(
                'version:Print dejavue version'
                'init:Create .dejavue/, install git hooks'
                'start:Record session start'
                'changed:Record file change event'
                'decision:Record architectural decision or blocker/claim/question'
                'state:Overwrite state.md with current snapshot'
                'handoff:Write handoff.md'
                'context:Print boot packet (handoff + state + decisions + events)'
                'status:One-line health view'
                'check:Health check: JSONL, hooks, .gitattributes, FTS'
                'archive:Compact old file_changed events from timeline'
                'roster:Show agent activity summary'
                'config:Get, set, or list per-repo config values'
                'install-skill:Install SKILL.md to your agent skills directory'
                'log:Formatted timeline view with filters'
                'blame:Show decisions and events touching a file path'
                'note:Record a lightweight timestamped note'
                'since:Temporal delta since a date, commit, or agent session'
                'ingest:Scrape .claude/, CHANGELOG, ADRs, git log into timeline'
                'recall:Keyword (FTS5) or semantic search over all artifacts'
                'worthiness:Print the capture/skip worthiness gate'
                'get:Direct fetch of a doc (state, handoff, decisions, context)'
                'list:List available artifacts'
                'annotate:Append timestamped note to a doc without rewriting it'
                'stats:Timeline statistics by type, agent, date range'
                'promote:Graduate .dejavue/ into a richer planning system'
                'import:Bootstrap context.md from an existing AGENTS.md/CLAUDE.md'
                'export:Export memory snapshot or generate DCP adapter files'
                'reference:Manage reference cards in .dejavue/references/'
                'link:Show dejavue events for a git commit SHA'
                'search:Alias for recall — keyword search over all artifacts'
                'diff:Compare dejavue memory between two refs'
                'timeline:ASCII activity chart of events over time'
                'tag:List tags or filter events by tag'
                'note-commit:Write a git note linking a commit to the last dejavue event'
                'completion:Print shell completion script (bash, zsh, fish)'
                'rejected:Show decisions with rejected alternatives, optionally filtered'
                'trap:Record a known lie / trap (misleading name, fake abstraction)'
                'incident:Record an operational incident (outage, corruption, migration)'
                'invariant:Record an architectural invariant that must always hold'
                'pattern:Record a discovered convention/pattern (naming, idiom, structure)'
                'entities:List entities, or show events referencing one entity'
            )
            _describe 'subcommand' subcommands ;;
        args)
            case $words[1] in
                decision)
                    _arguments \\
                        '--reason[Why this decision was made]:reason' \\
                        '*--rejected[Rejected alternative and reason]:alt:reason' \\
                        '--agent[Agent name]:agent' \\
                        '--type[Event type]:type:(decision blocker claim question experiment checkpoint)' \\
                        '--supersedes[ID or title of a prior decision this supersedes]:event-id' \\
                        '--durability[How long-lived this decision is]:durability:(temporary tactical strategic constitutional)' \\
                        '--confidence[How firm this decision is]:confidence:(speculative proposed experimental adopted deprecated verified)' \\
                        '*--entity[Subject this event is about, repeatable]:entity' \\
                        '--tag[Tag]:tag' ;;
                trap|incident|invariant|pattern)
                    _arguments \\
                        '--agent[Agent name]:agent' \\
                        '*--entity[Subject this event is about, repeatable]:entity' \\
                        '--tag[Tag]:tag' ;;
                note)
                    _arguments \\
                        '--agent[Agent name]:agent' \\
                        '--tag[Tag]:tag' \\
                        '*--entity[Subject this event is about, repeatable]:entity' \\
                        '--confidence[How firm this note/claim is]:confidence:(speculative proposed experimental adopted deprecated verified)' \\
                        '--type[Note type]:type:(note blocker claim question observation)' ;;
                export)
                    _arguments \\
                        '--format[Output format]:format:(json md)' \\
                        '--target[Adapter target]:target:(claude codex gemini copilot cursor all)' ;;
                promote)
                    _arguments '--to[Target system]:system:(planning)' ;;
                diff)
                    _arguments '--format[Diff format]:format:(text patch)' ;;
                get)
                    _arguments '1:doc:(state handoff decisions context)' ;;
                annotate)
                    _arguments '1:doc:(state handoff decisions)' ;;
                completion)
                    _arguments '1:shell:(bash zsh fish)' ;;
                config)
                    local config_cmds=('list:List all config values' 'get:Get a value' 'set:Set a value' 'unset:Remove a key')
                    _describe 'config subcommand' config_cmds ;;
                reference)
                    local ref_cmds=('list:List all cards' 'create:Create a card' 'update:Overwrite a card' 'view:Print a card')
                    _describe 'reference subcommand' ref_cmds ;;
                tag)
                    local tag_cmds=('list:List all tags with counts' 'filter:Show events with a tag')
                    _describe 'tag subcommand' tag_cmds ;;
                import)
                    _arguments '1:file:_files' ;;
            esac ;;
    esac
}
_dejavue
"""

_FISH_COMPLETION = """\
# dejavue fish completion
# Install: dejavue completion fish | source
# Or persist: dejavue completion fish > ~/.config/fish/completions/dejavue.fish
set -l cmds version init start changed decision state handoff context status \\
    check archive roster config install-skill log blame note since ingest recall \\
    worthiness get list annotate stats promote import export reference link search \\
    diff timeline tag note-commit completion rejected trap incident invariant pattern entities
complete -c dejavue -f -n "not __fish_seen_subcommand_from $cmds" -a "$cmds"
# decision / note types
complete -c dejavue -n "__fish_seen_subcommand_from decision" -l type -a "decision blocker claim question experiment checkpoint"
complete -c dejavue -n "__fish_seen_subcommand_from decision" -l durability -a "temporary tactical strategic constitutional"
complete -c dejavue -n "__fish_seen_subcommand_from decision note" -l confidence -a "speculative proposed experimental adopted deprecated verified"
complete -c dejavue -n "__fish_seen_subcommand_from decision" -l supersedes
complete -c dejavue -n "__fish_seen_subcommand_from note" -l type -a "note blocker claim question observation"
# export
complete -c dejavue -n "__fish_seen_subcommand_from export" -l format -a "json md"
complete -c dejavue -n "__fish_seen_subcommand_from export" -l target -a "claude codex gemini copilot cursor all"
# promote
complete -c dejavue -n "__fish_seen_subcommand_from promote" -l to -a "planning"
# diff
complete -c dejavue -n "__fish_seen_subcommand_from diff" -l format -a "text patch"
# get / annotate docs
complete -c dejavue -n "__fish_seen_subcommand_from get" -a "state handoff decisions context"
complete -c dejavue -n "__fish_seen_subcommand_from annotate" -a "state handoff decisions"
# sub-subcommands
complete -c dejavue -n "__fish_seen_subcommand_from config" -a "list get set unset"
complete -c dejavue -n "__fish_seen_subcommand_from reference" -a "list create update view"
complete -c dejavue -n "__fish_seen_subcommand_from tag" -a "list filter"
# shell selection
complete -c dejavue -n "__fish_seen_subcommand_from completion" -a "bash zsh fish"
# common flags
complete -c dejavue -n "__fish_seen_subcommand_from decision note start trap incident invariant pattern" -l agent -d "Agent name"
complete -c dejavue -n "__fish_seen_subcommand_from decision note trap incident invariant pattern" -l tag -d "Tag"
complete -c dejavue -n "__fish_seen_subcommand_from decision note trap incident invariant pattern" -l entity -d "Subject (repeatable)"
complete -c dejavue -n "__fish_seen_subcommand_from log recall since" -l since -d "Since date or commit"
complete -c dejavue -n "__fish_seen_subcommand_from check" -l fix -d "Auto-fix issues"
complete -c dejavue -n "__fish_seen_subcommand_from import" -rF
"""


def cmd_completion(args):
    shell = args.shell
    scripts = {"bash": _BASH_COMPLETION, "zsh": _ZSH_COMPLETION, "fish": _FISH_COMPLETION}
    print(scripts[shell], end="")


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
    p.add_argument("--wizard", action="store_true",
                   help="Run a 3-question prompt (project type / agent / purpose) to seed "
                        "context.md + state.md. Non-interactive (piped/EOF) uses defaults.")
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

    p = sub.add_parser("decision", help="Record architectural decision (or blocker/claim/question/experiment).")
    p.add_argument("title")
    p.add_argument("--reason", required=True)
    p.add_argument("--rejected", action="append", default=[], metavar="OPTION",
                   help="Rejected alternative (repeatable). Format: 'option: reason'")
    p.add_argument("--outcome", default=None,
                   help="What shipped / current state (optional).")
    p.add_argument("--type", dest="event_type", default="decision",
                   choices=sorted(DECISION_TYPES),
                   help="Event sub-type (default: decision).")
    p.add_argument("--supersedes", metavar="EVENT-ID",
                   help="ID or title of a prior decision this supersedes.")
    p.add_argument("--durability", choices=["temporary", "tactical", "strategic", "constitutional"],
                   help="How long-lived this decision is.")
    p.add_argument("--confidence", choices=["speculative", "proposed", "experimental", "adopted", "deprecated", "verified"],
                   help="How firm this decision is — a recall trust signal.")
    p.add_argument("--agent", default=None)
    p.add_argument("--entity", action="append", metavar="NAME", help="Subject this event is about (repeatable; links events for recall/blame).")
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

    p = sub.add_parser("context", help="Print all .md files + last N timeline entries.")
    p.add_argument("--check-stale", action="store_true", dest="check_stale",
                   help="Only print staleness warnings (used by pre-push hook).")
    p.add_argument("-n", type=int, default=10, metavar="N",
                   help="Number of recent events to show (default 10).")
    p.set_defaults(func=cmd_context)

    p = sub.add_parser("status", help="One-line health view: agent, last decision, open next-steps.")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("check", help="Health check: JSONL validity, hook status, .gitattributes, FTS freshness.")
    p.add_argument("--fix", action="store_true",
                   help="Auto-repair: install missing hooks, add .gitattributes/.gitignore entries, rebuild stale FTS.")
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

    p = sub.add_parser("note", help="Record a lightweight timestamped note (or observation/claim/question).")
    p.add_argument("text")
    p.add_argument("--tag", default=None, help="Optional tag for filtering.")
    p.add_argument("--type", dest="event_type", default="note",
                   choices=sorted(NOTE_TYPES),
                   help="Event sub-type (default: note).")
    p.add_argument("--agent", default=None)
    p.add_argument("--entity", action="append", metavar="NAME", help="Subject this event is about (repeatable; links events for recall/blame).")
    p.add_argument("--confidence", choices=["speculative", "proposed", "experimental", "adopted", "deprecated", "verified"],
                   help="How firm this note/claim is.")
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

    p = sub.add_parser("stats", help="Timeline statistics: counts by type, by agent, date range.")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("promote", help="Graduate .dejavue/ into a richer planning system (.planning/) without losing history.")
    p.add_argument("--to", default="planning", choices=["planning"],
                   help="Target planning system (default: planning).")
    p.add_argument("--force", action="store_true", help="Overwrite already-promoted artifacts.")
    p.add_argument("--agent", default=None)
    p.set_defaults(func=cmd_promote)

    p = sub.add_parser("import", help="Bootstrap context.md from an existing AGENTS.md/CLAUDE.md (lossless).")
    p.add_argument("file", help="Path to the hand-written instruction file to import.")
    p.add_argument("--force", action="store_true", help="Overwrite a populated context.md.")
    p.add_argument("--agent", default=None)
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("export", help="Export dejavue memory (--format json|md) or generate adapter files (--target).")
    p.add_argument("--format", choices=["json", "md"], default="json",
                   help="Snapshot output format (default: json). Ignored when --target is given.")
    p.add_argument("--target", choices=sorted(EXPORT_TARGETS) + ["all"], default=None,
                   help="Generate an adapter file (claude→CLAUDE.md, codex→AGENTS.md, "
                        "gemini→GEMINI.md, copilot→.github/copilot-instructions.md, "
                        "cursor→.cursor/rules, or all) from context.md.")
    p.add_argument("--replace", action="store_true",
                   help="With --target: convert an unmarked hand-written file entirely "
                        "(default appends a managed block + warns).")
    p.add_argument("--agent", default=None)
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("reference", help="Manage reference cards in .dejavue/references/.")
    ref_sub = p.add_subparsers(dest="action", required=True)

    rs = ref_sub.add_parser("list", help="List all reference cards.")
    rs.add_argument("--type", default=None,
                    help="Filter by `type:` frontmatter value (e.g. glossary, api).")
    rs = ref_sub.add_parser("create", help="Create a new reference card.")
    rs.add_argument("name", help="Card name (becomes references/<name>.md).")
    rs.add_argument("--title", default=None, help="Title text (defaults to name).")
    rs.add_argument("--content", default=None, help="Card content (overrides template).")
    rs.add_argument("--template", choices=["default", "api", "design", "glossary"], default="default")
    rs.add_argument("--type", default=None,
                    help="Set a `type:` frontmatter value on the card (filterable via list --type).")
    rs.add_argument("--force", action="store_true")
    rs.add_argument("--agent", default=None)
    rs = ref_sub.add_parser("update", help="Overwrite a reference card's content.")
    rs.add_argument("name")
    rs.add_argument("--content", required=True)
    rs.add_argument("--agent", default=None)
    rs = ref_sub.add_parser("view", help="Print a reference card.")
    rs.add_argument("name")
    p.set_defaults(func=cmd_reference)

    p = sub.add_parser("link", help="Show dejavue events recorded for a git commit SHA.")
    p.add_argument("sha", help="Git commit SHA or short SHA.")
    p.set_defaults(func=cmd_link)

    # 'search' is a discoverable alias for 'recall'
    p = sub.add_parser("search", help="Alias for recall — keyword search over all artifacts.")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=10, metavar="N")
    p.add_argument("--semantic", action="store_true")
    p.set_defaults(func=cmd_recall)

    p = sub.add_parser("diff", help="Compare dejavue memory between two refs (dates or commits).")
    p.add_argument("from_ref", metavar="FROM", help="Start ref: ISO date (2026-05-13), commit hash, or git tag.")
    p.add_argument("to_ref",   metavar="TO",   nargs="?", default="HEAD",
                   help="End ref (default: HEAD).")
    p.add_argument("--format", choices=["text", "patch"], default="text",
                   help="text (default, human summary) or patch (machine-readable unified diff of the decisions delta).")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("timeline", help="ASCII activity chart of events over time.")
    p.add_argument("--by", choices=["day", "week", "month"], default="week",
                   help="Bucket granularity (default: week).")
    p.add_argument("--agent", default=None, help="Filter by agent name.")
    p.set_defaults(func=cmd_timeline)

    p = sub.add_parser("tag", help="List tags or filter events by tag.")
    tag_sub = p.add_subparsers(dest="action", required=True)
    tag_sub.add_parser("list", help="List all tags with counts.")
    ts2 = tag_sub.add_parser("filter", help="Show events with a specific tag.")
    ts2.add_argument("tag")
    p.set_defaults(func=cmd_tag)

    p = sub.add_parser("note-commit", help="Write a git note on a commit linking it to the last dejavue event.")
    p.add_argument("sha", help="Commit SHA or short SHA.")
    p.add_argument("--trailer", action="store_true",
                   help="Also amend the commit message with a Dejavue-Event: trailer (opt-in, user-invoked only).")
    p.set_defaults(func=cmd_note_commit)

    p = sub.add_parser("completion", help="Print shell completion script to stdout.")
    p.add_argument("shell", choices=["bash", "zsh", "fish"], help="Target shell.")
    p.set_defaults(func=cmd_completion)

    p = sub.add_parser("rejected", help="Show decisions with rejected alternatives, optionally filtered by topic.")
    p.add_argument("query", nargs="?", help="Topic to filter on (case-insensitive substring).")
    p.set_defaults(func=cmd_rejected)

    p = sub.add_parser("trap", help="Record a known lie / trap: misleading name, fake abstraction, dangerous assumption.")
    p.add_argument("text", help="What the trap is.")
    p.add_argument("--agent", metavar="NAME", help="Agent name (default: auto-detected).")
    p.add_argument("--tag", metavar="TAG", help="Tag.")
    p.add_argument("--entity", action="append", metavar="NAME", help="Subject this event is about (repeatable; links events for recall/blame).")
    p.set_defaults(func=cmd_trap)

    p = sub.add_parser("incident", help="Record an operational incident: outage, data corruption, failed migration.")
    p.add_argument("text", help="Incident description.")
    p.add_argument("--agent", metavar="NAME", help="Agent name (default: auto-detected).")
    p.add_argument("--tag", metavar="TAG", help="Tag.")
    p.add_argument("--entity", action="append", metavar="NAME", help="Subject this event is about (repeatable; links events for recall/blame).")
    p.set_defaults(func=cmd_incident)

    p = sub.add_parser("invariant", help="Record an architectural invariant that must always hold.")
    p.add_argument("text", help="The invariant statement.")
    p.add_argument("--agent", metavar="NAME", help="Agent name (default: auto-detected).")
    p.add_argument("--tag", metavar="TAG", help="Tag.")
    p.add_argument("--entity", action="append", metavar="NAME", help="Subject this event is about (repeatable; links events for recall/blame).")
    p.set_defaults(func=cmd_invariant)

    p = sub.add_parser("pattern", help="Record a discovered convention/pattern: naming, idiom, structure.")
    p.add_argument("text", help="The convention or pattern.")
    p.add_argument("--agent", metavar="NAME", help="Agent name (default: auto-detected).")
    p.add_argument("--tag", metavar="TAG", help="Tag.")
    p.add_argument("--entity", action="append", metavar="NAME", help="Subject this event is about (repeatable; links events for recall/blame).")
    p.set_defaults(func=cmd_pattern)

    p = sub.add_parser("entities", help="List entities, or show events referencing one entity.")
    p.add_argument("name", nargs="?", help="Entity to filter on (optional; omit to list all).")
    p.set_defaults(func=cmd_entities)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

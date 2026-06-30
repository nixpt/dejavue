#!/usr/bin/env python3
"""Minimal DejaVue wrapper.

This is intentionally tiny:
- no server
- no database
- no local cache
- no routing

It just shells out to the dejavue CLI in a target repo.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = SCRIPT_DIR / "mcp-tools.json"


@dataclass(frozen=True)
class WrapperConfig:
    repo_root: Path
    dejavue_bin: str
    agent_name: str | None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dejavue-wrapper", description="Tiny shell-out wrapper for dejavue.")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Absolute or relative path to the git repo that owns .dejavue/.",
    )
    parser.add_argument(
        "--dejavue-bin",
        default="dejavue",
        help="Path to the dejavue executable (defaults to dejavue on PATH).",
    )
    parser.add_argument(
        "--agent-name",
        default=None,
        help="Stable role name to expose to dejavue via AGENT_NAME.",
    )

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("manifest", help="Print the static tool manifest as JSON.")

    call = sub.add_parser("call", help="Invoke a dejavue command in the target repo.")
    call.add_argument("tool", help="DejaVue subcommand to call, e.g. context or since.")
    call.add_argument("tool_args", nargs=argparse.REMAINDER, help="Arguments passed through verbatim.")
    return parser


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        with MANIFEST_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return {
        "name": "dejavue-wrapper",
        "transport": "shell",
        "description": "Tiny shell-out wrapper for dejavue.",
        "tools": [
            {"name": "context"},
            {"name": "since"},
            {"name": "recall"},
            {"name": "state"},
            {"name": "handoff"},
            {"name": "blame"},
            {"name": "decision"},
            {"name": "start"},
            {"name": "changed"},
        ],
    }


def _config_from_args(args: argparse.Namespace) -> WrapperConfig:
    dejavue_bin = args.dejavue_bin
    if dejavue_bin != "dejavue" and (os.path.isabs(dejavue_bin) or os.sep in dejavue_bin):
        dejavue_bin = str(Path(dejavue_bin).expanduser().resolve())
    return WrapperConfig(
        repo_root=Path(args.repo_root).resolve(),
        dejavue_bin=dejavue_bin,
        agent_name=args.agent_name,
    )


def _run_tool(cfg: WrapperConfig, tool: str, argv: Sequence[str]) -> int:
    env = os.environ.copy()
    if cfg.agent_name:
        env["AGENT_NAME"] = cfg.agent_name

    cmd = [cfg.dejavue_bin, tool, *argv]
    proc = subprocess.run(
        cmd,
        cwd=cfg.repo_root,
        env=env,
        text=True,
        capture_output=True,
    )
    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)
    return proc.returncode


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    cfg = _config_from_args(args)

    if args.command == "manifest":
        print(json.dumps(_load_manifest(), indent=2, sort_keys=True))
        return 0

    if args.command == "call":
        tool_args = list(args.tool_args)
        if tool_args[:1] == ["--"]:
            tool_args = tool_args[1:]
        return _run_tool(cfg, args.tool, tool_args)

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
session_start_context.py -- SessionStart hook that injects project context.

Stdout from SessionStart hooks is injected directly into the model's context,
so everything printed here the model sees on session open/resume.

Emits:
  - Current date/time
  - Git branch + last 5 commits (if in a git repo)
  - Modified/staged files (git status --short)
  - Any open TODO markers in the project (first 10)
  - Reminder to read CLAUDE.md if it exists

Set SESSION_CONTEXT_DIR to override the directory to check (defaults to CWD).
"""
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone


def _git(args: list[str], cwd: str) -> str:
    try:
        r = subprocess.run(
            ["git"] + args, capture_output=True, text=True,
            encoding="utf-8", cwd=cwd, timeout=10
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def main() -> None:
    cwd = os.environ.get("SESSION_CONTEXT_DIR") or os.getcwd()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"=== Session opened {now} ===")

    branch = _git(["branch", "--show-current"], cwd)
    if branch:
        print(f"Branch: {branch}")

        log = _git(["log", "--oneline", "-5"], cwd)
        if log:
            print("Recent commits:")
            for line in log.splitlines():
                print(f"  {line}")

        status = _git(["status", "--short"], cwd)
        if status:
            lines = status.splitlines()[:15]
            print(f"Modified ({len(lines)} files):")
            for line in lines:
                print(f"  {line}")
        else:
            print("Working tree: clean")

    claude_md = pathlib.Path(cwd) / "CLAUDE.md"
    if claude_md.exists():
        print(f"Reminder: CLAUDE.md exists at {cwd} — read it before making significant changes.")

    print("=" * 40)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()

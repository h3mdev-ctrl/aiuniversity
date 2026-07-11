#!/usr/bin/env python3
"""
auto_commit_wip.py -- Stop hook that creates a WIP commit after each Claude turn.

On every Stop event, if the repo has unstaged or staged changes, auto-commits
them as "wip: claude turn [skip ci]" so every turn has a rollback point.

Safety guards:
  - Only runs if there are actual changes (git status --short is non-empty)
  - Only commits to non-main/master/production branches (configurable via
    AUTO_COMMIT_ALLOWED_BRANCHES_PATTERN, default: "^(?!main|master|production)")
  - Never runs if AUTO_COMMIT_WIP=0 or if git isn't available
  - Stages ALL changes (git add -A) before committing — only use on branches
    where this is safe

Set AUTO_COMMIT_WIP=0 to disable for a turn.
Set AUTO_COMMIT_BRANCH_PATTERN to a regex to control which branches are eligible.
"""
import os
import re
import subprocess
import sys


DEFAULT_BRANCH_PATTERN = r"^(?!main$|master$|production$|staging$)"


def _git(args: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(
            ["git"] + args, capture_output=True, text=True,
            encoding="utf-8", timeout=30
        )
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)


def main() -> int:
    if os.environ.get("AUTO_COMMIT_WIP") == "0":
        return 0

    rc, branch = _git(["branch", "--show-current"])
    if rc != 0 or not branch:
        return 0  # not in a git repo

    pattern = os.environ.get("AUTO_COMMIT_BRANCH_PATTERN", DEFAULT_BRANCH_PATTERN)
    if not re.match(pattern, branch):
        return 0  # protected branch — skip

    rc, status = _git(["status", "--short"])
    if rc != 0 or not status.strip():
        return 0  # nothing to commit

    _git(["add", "-A"])
    rc, out = _git(["commit", "-m", "wip: claude turn [skip ci]"])
    if rc != 0:
        # Silently skip — might be a pre-commit hook failure or nothing staged
        pass

    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())

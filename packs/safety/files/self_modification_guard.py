#!/usr/bin/env python3
"""
self_modification_guard.py -- PreToolUse hook that blocks writes to hook files.

A prompt injection that disables credential_guard or any other installed hook is the
highest-risk attack surface for an agentic session. This guard closes that gap by
blocking Write/Edit tool calls that target the hooks directory or the settings.json
that registers those hooks.

What it blocks:
  Write/Edit to ~/.claude/hooks/ or $CLAUDE_HOME/hooks/
  Write/Edit to ~/.claude/settings.json or $CLAUDE_HOME/settings.json

What it allows:
  All other writes — this is a narrow, targeted guard.

Reads JSON from stdin; exits 2 + writes to stderr to block. Exits 0 to allow.
"""
import json
import os
import pathlib
import re
import sys


def _claude_home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def _protected_paths() -> list[str]:
    home = _claude_home()
    return [
        str(home / "hooks"),
        str(home / "settings.json"),
    ]


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    tool = data.get("tool_name", "")
    if tool not in ("Write", "Edit"):
        return 0

    inp = data.get("tool_input") or {}
    file_path = inp.get("file_path", "")
    if not file_path:
        return 0

    resolved = str(pathlib.Path(file_path).expanduser().resolve())

    for protected in _protected_paths():
        protected_resolved = str(pathlib.Path(protected).expanduser().resolve())
        if resolved == protected_resolved or resolved.startswith(protected_resolved + os.sep):
            print(
                f"BLOCKED: write to protected path {file_path!r} — "
                "hook files and settings.json cannot be modified mid-session to prevent "
                "a prompt injection from disabling security guards.",
                file=sys.stderr,
            )
            print("If you need to update hooks, do it from a fresh session.", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())

#!/usr/bin/env python3
"""
dangerous_bash_guard.py -- PreToolUse hook that blocks destructive shell commands.

Regex-blocks patterns that cause irreversible damage and are rarely intentional:
  rm -rf / or ~ or *
  git push --force to main/master
  curl|wget piped directly into bash (RCE vector)
  fork bombs
  chmod -R 777 /
  eval $(...) (arbitrary code execution)
  git reset/checkout --hard (discards uncommitted work)
  dd if= piped to a block device

Reads JSON from stdin; exits 2 + writes to stderr to block (Claude Code surfaces
stderr as the "blocked" message shown to the model). Exits 0 to allow.
"""
import json
import re
import sys


PATTERNS: list[tuple[str, str]] = [
    (r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+[/~*]", "rm -rf on root/home/glob"),
    (r"rm\s+-[a-zA-Z]*f[a-zA-Z]*r[a-zA-Z]*\s+[/~*]", "rm -rf on root/home/glob"),
    (r"git\s+push\s+.*(?:--force|-f)\b.*\b(?:main|master)\b", "force-push to main/master"),
    (r"git\s+push\s+.*\b(?:main|master)\b.*(?:--force|-f)", "force-push to main/master"),
    (r"curl\s+.*\|\s*(?:ba)?sh", "curl | bash (remote code execution)"),
    (r"wget\s+.*\|\s*(?:ba)?sh", "wget | bash (remote code execution)"),
    (r":\s*\(\s*\)\s*\{.*:\s*\|.*:\s*&", "fork bomb"),
    (r"chmod\s+-[Rr]\s+777\s+/", "chmod -R 777 /"),
    (r"eval\s+\$\(", "eval $(...) arbitrary code execution"),
    (r"\bdd\b.*\bif=.*\bof=/dev/(?:sd|nvme|xvd|hd)[a-z]", "dd to block device"),
    (r"git\s+(?:reset|checkout)\s+--hard\s+HEAD~?\d*$", "git reset/checkout --hard (discards uncommitted work)"),
    (r"mkfs\.", "mkfs — filesystem format"),
    (r">\s*/dev/(?:sd|nvme|xvd|hd)[a-z]", "redirect to block device"),
    (r"shred\s+", "shred — secure file deletion"),
    (r"history\s+-[cw]", "clearing shell history"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), desc) for p, desc in PATTERNS]


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # fail-open on bad input

    tool = data.get("tool_name", "")
    if tool not in ("Bash",):
        return 0

    cmd = (data.get("tool_input") or {}).get("command", "")
    if not cmd:
        return 0

    for pattern, desc in _COMPILED:
        if pattern.search(cmd):
            print(f"BLOCKED: dangerous command — {desc}", file=sys.stderr)
            print(f"Command: {cmd[:120]}", file=sys.stderr)
            return 2

    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())

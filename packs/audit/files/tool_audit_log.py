#!/usr/bin/env python3
"""
tool_audit_log.py -- PostToolUse hook that appends every tool call to a JSONL audit log.

Log location: ~/.claude/audit.jsonl (or $CLAUDE_AUDIT_LOG to override)

Each line: {"ts", "tool", "file_path" (if write/edit/read), "command" (if bash),
            "exit_code", "session_cwd"}

Useful for: "what did the overnight autonomous session actually touch?"
            "which files were written to?" "how many tool calls per session?"
Append-only, never truncated. Rotate manually or with logrotate.
"""
import json
import os
import pathlib
import sys
from datetime import datetime, timezone


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    log_path = pathlib.Path(
        os.environ.get("CLAUDE_AUDIT_LOG")
        or (pathlib.Path.home() / ".claude" / "audit.jsonl")
    )

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        tool = data.get("tool_name", "")
        inp = data.get("tool_input") or {}
        response = data.get("tool_response") or {}
        exit_code = None
        if isinstance(response, dict):
            exit_code = response.get("exit_code") or response.get("returncode")

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "cwd": os.getcwd(),
        }
        if tool in ("Write", "Edit", "Read", "Glob", "Grep"):
            entry["file"] = inp.get("file_path") or inp.get("pattern") or inp.get("path") or ""
        if tool == "Bash":
            entry["cmd"] = (inp.get("command", "") or "")[:200]
        if exit_code is not None:
            entry["exit_code"] = exit_code

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # audit log failure should never disrupt the main workflow

    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())

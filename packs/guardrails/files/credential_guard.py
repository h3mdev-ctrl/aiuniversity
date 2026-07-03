#!/usr/bin/env python
"""
credential_guard.py -- PreToolUse hook: block Claude from reading credential files.

A deterministic backstop for a footgun humans still make in Claude Code: telling
an agent "read this .env" without thinking, or a `cat .env` slipping into a Bash
call. The point: catch it by CODE, not by hoping the agent remembered.

Input: JSON on stdin with {tool_name, tool_input}. Exit 0 to allow; exit 2 to
deny with a message on stderr (Claude Code's hook convention for PreToolUse).

Blocks:
- Read tool on a file path matching a credential pattern.
- Bash tool on a command that would read a credential path (cat/less/type/head/
  tail/Get-Content and friends).

Bypass (rare, explicit only): set CLAUDE_CRED_GUARD=off in the environment.
"""
import json
import os
import re
import sys

CRED_PATTERNS = [
    r"(?:^|[/\\])\.env(?:$|\.[a-zA-Z0-9_-]+$)",     # .env, .env.local, .env.production
    r"(?:^|[/\\])credentials\.json$",
    r"(?:^|[/\\])\.credentials$",
    r"(?:^|[/\\])id_(?:rsa|dsa|ecdsa|ed25519)$",     # SSH private keys
    r"(?:^|[/\\])\.aws[/\\]credentials$",
    r"(?:^|[/\\])\.ssh[/\\]id_",
    r"(?:^|[/\\])\.npmrc$",
    r"(?:^|[/\\])\.netrc$",
    r"(?:^|[/\\])\.pypirc$",
]
CRED_RE = re.compile("|".join(CRED_PATTERNS), re.IGNORECASE)
READ_CMDS_RE = re.compile(
    r"\b(?:cat|less|more|head|tail|type|Get-Content|nano|vim|vi|code)\b",
    re.IGNORECASE,
)


def is_credential_path(path: str) -> bool:
    return bool(path) and bool(CRED_RE.search(str(path)))


def check(event: dict) -> "str | None":
    tool = event.get("tool_name", "")
    ti = event.get("tool_input") or {}
    if tool == "Read":
        path = ti.get("file_path", "")
        if is_credential_path(path):
            return f"BLOCKED: reading credential-bearing file {path!r}"
    if tool == "Bash":
        cmd = ti.get("command", "") or ""
        if READ_CMDS_RE.search(cmd):
            for token in re.findall(r"\S+", cmd):
                if is_credential_path(token):
                    return f"BLOCKED: bash command would read credential file (matched {token!r})"
    return None


def main() -> int:
    if os.environ.get("CLAUDE_CRED_GUARD", "").lower() == "off":
        return 0  # explicit bypass
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0  # malformed input: don't block by accident
    msg = check(event)
    if msg:
        print(msg, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

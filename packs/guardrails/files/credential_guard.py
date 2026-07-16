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

The block message doesn't just say no -- it names the safe command for the
question the agent was probably asking (field names, existence, value diff),
so the SAME reflex gets satisfied a different way instead of just bouncing.
This matters more than it looks: a guard that only says "blocked" gets hit
again next turn, because the agent still has no faster path than the one that
just failed.

Bypass (rare, explicit only): prefix the command with `CLAUDE_CRED_GUARD=off `.
Not a real env var read from the parent shell -- deliberately. An env var set
once in a parent shell would silently bypass every descendant call; a prefix on
the command string is visible in the transcript and audited per call.
"""
import json
import os
import re
import sys

CRED_PATTERNS = [
    r"(?:^|[/\\])\.env(?:$|\.[a-zA-Z0-9_-]+$)",       # .env, .env.local, .env.production
    r"(?:^|[/\\])credentials\.json$",
    r"(?:^|[/\\])\.credentials$",
    r"(?:^|[/\\])id_(?:rsa|dsa|ecdsa|ed25519)(?:\.pub)?$",  # SSH keys
    r"(?:^|[/\\])\.aws[/\\]credentials$",
    r"(?:^|[/\\])\.ssh[/\\]id_",
    r"(?:^|[/\\])\.npmrc$",
    r"(?:^|[/\\])\.netrc$",
    r"(?:^|[/\\])\.pypirc$",
    r"\.(?:pem|key|p12|pfx)$",                         # cert/key files
    r"(?:credential|secret|service-?account)[^/\\]*\.json$",
]
CRED_RE = re.compile("|".join(CRED_PATTERNS), re.IGNORECASE)
READ_CMDS_RE = re.compile(
    r"\b(?:cat|tac|less|more|head|tail|type|Get-Content|gc|nano|vim|vi|code|"
    r"strings|xxd|od|hexdump)\b",
    re.IGNORECASE,
)

SAFE_ALTERNATIVES = """\
BLOCKED: {reason}

Don't read the whole file -- go straight to the safe form of the question
you were probably asking:
  - field names only:   jq 'keys' <file>
  - names + types:       jq 'to_entries|map({{k:.key,t:(.value|type)}})' <file>
  - does a var exist:    grep -oE '^[A-Z_]+=' .env
  - compare two secrets: python -c "import hashlib;print(hashlib.sha256(open(r'<file>').read().encode()).hexdigest()[:12])"
  - anything else:       usually answerable from docs/--help without reading the file at all

If you genuinely need the raw file (rare -- e.g. rotating a value), prefix the
command with CLAUDE_CRED_GUARD=off so the bypass is explicit and visible."""


def is_credential_path(path: str) -> bool:
    return bool(path) and bool(CRED_RE.search(str(path)))


def _bash_reads_credential(cmd: str) -> "str | None":
    """Return the matched token if this Bash command would read a credential
    path to stdout/terminal, else None. Splits on shell word-boundaries and
    checks WHOLE words -- not substrings -- so `process.env` (a bare
    identifier) doesn't false-positive on the `.env` pattern the way naive
    substring matching would; a real path like `config/.env` still matches
    because the slash precedes it.
    """
    if not READ_CMDS_RE.search(cmd):
        return None
    for word in re.split(r"[\s|;&()=`<>]+", cmd):
        word = word.strip().strip('"').strip("'")
        if word and is_credential_path(word):
            return word
    return None


def check(event: dict) -> "str | None":
    tool = event.get("tool_name", "")
    ti = event.get("tool_input") or {}
    if tool == "Read":
        path = ti.get("file_path", "")
        if is_credential_path(path):
            return f"reading credential-bearing file {path!r}"
    if tool == "Bash":
        cmd = ti.get("command", "") or ""
        if re.match(r"^\s*CLAUDE_CRED_GUARD=(off|0|false)\b", cmd, re.IGNORECASE):
            return None
        hit = _bash_reads_credential(cmd)
        if hit:
            return f"bash command would read credential file (matched {hit!r})"
    return None


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        return 0  # malformed input: don't block by accident
    reason = check(event)
    if reason:
        print(SAFE_ALTERNATIVES.format(reason=reason), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

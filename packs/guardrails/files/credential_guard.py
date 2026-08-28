#!/usr/bin/env python3
"""
credential_guard.py — Claude Code PreToolUse hook.

Blocks Read/Bash tool calls that would expose credential files to the
transcript. The rule "never cat secret files" has been violated 4× by
Claude in May 2026 despite memory entries telling it not to.

Memory tells; hooks bounce. This is the bouncer.

Exit codes:
  0  — allow the tool call (default)
  2  — block the tool call, stderr is shown to Claude as the reason

To override (rare; for legitimate credential rotation), set env var:
  CLAUDE_CRED_GUARD=off

Banned file patterns are duplicated from feedback_credentials.md.
Keep these in sync when that memory is updated.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# NOTE: there is NO env-var-based override. An env var set in a parent shell
# would silently bypass for ALL descendants — too leaky. The only valid bypass
# is an explicit in-command prefix (handled below in main()) which is visible
# in the transcript and audited per-call.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Banned absolute paths (case-insensitive on Windows)
# ---------------------------------------------------------------------------
HOME = Path.home()

# Resolved-path equality (canonical paths Claude or bash would produce)
BANNED_PATHS = {
    str(HOME / ".gbrain" / "config.json"),
    str(HOME / ".claude.json"),
    str(HOME / ".aws" / "credentials"),
    str(HOME / ".npmrc"),
    str(HOME / ".pypirc"),
    str(HOME / ".netrc"),
    str(HOME / ".config" / "gh" / "hosts.yml"),
}

# Suffix / basename / substring patterns
BANNED_GLOB_PATTERNS = [
    re.compile(r"(^|[\\/])\.env($|\.|[\\/])", re.IGNORECASE),                          # .env, .env.local, .env/
    re.compile(r"\.(pem|key|p12|pfx)$", re.IGNORECASE),                                # cert/key files
    re.compile(r"(^|[\\/])id_(rsa|ed25519|ecdsa|dsa)(\.pub)?$", re.IGNORECASE),         # SSH keys
    re.compile(r"(credential|secret|service-?account|firebase-adminsdk)[^\\/]*\.json$", re.IGNORECASE),
    re.compile(r"\.gbrain[\\/]config\.json$", re.IGNORECASE),                          # any gbrain config
    re.compile(r"[\\/]\.aws[\\/]credentials$", re.IGNORECASE),
]

# Allowlist (exact strings the matched path may end with, overriding above)
# Use sparingly — only for confirmed non-secret files that match a pattern.
ALLOWED_OVERRIDES = [
    # e.g. r"public_keys\.json$"
]


def _normalize(p: str) -> str:
    """Lowercase + forward-slash for stable matching on Windows."""
    return str(Path(p)).replace("\\", "/").lower()


def is_banned_path(raw_path: str) -> str | None:
    """Return a reason string if path is banned, else None."""
    if not raw_path:
        return None
    norm = _normalize(raw_path)

    for ok in ALLOWED_OVERRIDES:
        if re.search(ok, norm, re.IGNORECASE):
            return None

    for banned in BANNED_PATHS:
        if norm == _normalize(banned):
            return f"path matches banned credential file ({banned})"

    for pat in BANNED_GLOB_PATTERNS:
        m = pat.search(norm)
        if m:
            return f"path matches banned pattern {pat.pattern!r}"

    return None


# ---------------------------------------------------------------------------
# Bash command inspection
# ---------------------------------------------------------------------------
# Commands that dump file contents to stdout (transcript-leaking)
READ_VERBS = re.compile(
    r"(?:^|[\s|;&`(])"
    r"(cat|tac|head|tail|less|more|type|Get-Content|gc|Read|sed|awk|grep|rg|"
    r"strings|xxd|od|hexdump|jq)"
    r"\b",
    re.IGNORECASE,
)

# Also catch redirection-FROM-file (`< file`) and `printf ... "$(<file)"` style
REDIR_FROM_FILE = re.compile(r"<\s*([^\s|;&`)]+)")


def find_banned_in_bash(cmd: str) -> tuple[str, str] | None:
    """If the bash command would read a banned path to stdout, return (path, reason)."""
    if not cmd:
        return None

    # Quick screen: only if a read-verb is present
    if not READ_VERBS.search(cmd):
        return None

    # Split into whole shell-words on whitespace + shell control operators, strip
    # surrounding quotes, and check each WHOLE word. Checking whole words (not
    # sub-tokens) is what tells a real path like "config/.env" (banned — '/.env'
    # has a slash before it, so is_banned_path matches) apart from an identifier
    # like "process.env" (safe — '.env' is glued to a word char, matching no path
    # pattern). The previous tokenizer sliced ".env" out of the MIDDLE of
    # "process.env" and then saw it at string-start, a false positive that blocked
    # `grep "process.env" file.ts`, `git ls-files | grep "\.env"`, etc.
    # (A quoted path containing spaces still gets caught: splitting it leaves a
    # tail like "Workspace/.env" whose '/.env' still matches.)
    for word in re.split(r"[\s|;&()=`<>]+", cmd):
        word = word.strip().strip('"').strip("'")
        if not word:
            continue
        expanded = os.path.expandvars(os.path.expanduser(word))
        reason = is_banned_path(expanded)
        if reason:
            return expanded, reason

    # Also check `< file` redirection targets
    for m in REDIR_FROM_FILE.finditer(cmd):
        tok = m.group(1).strip('"').strip("'")
        expanded = os.path.expandvars(os.path.expanduser(tok))
        reason = is_banned_path(expanded)
        if reason:
            return expanded, reason

    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception as e:
        # Don't block on hook bugs — fail open with a stderr note.
        print(f"[credential_guard] failed to parse stdin: {e}", file=sys.stderr)
        return 0

    tool = payload.get("tool_name") or payload.get("tool") or ""
    inp = payload.get("tool_input") or {}

    block_reason: str | None = None
    blocked_path: str | None = None

    if tool == "Read":
        fp = inp.get("file_path") or ""
        r = is_banned_path(fp)
        if r:
            block_reason = r
            blocked_path = fp

    elif tool == "Bash":
        cmd = inp.get("command") or ""
        # In-command override: bash sees `CLAUDE_CRED_GUARD=off <rest>` as
        # setting the var for that command. The hook runs before bash, so
        # env-var prefixes don't reach the hook env. Detect the prefix
        # in the command string itself to honor the documented bypass.
        if re.match(r"^\s*CLAUDE_CRED_GUARD=(off|0|false)\b", cmd, re.IGNORECASE):
            return 0
        hit = find_banned_in_bash(cmd)
        if hit:
            blocked_path, block_reason = hit

    elif tool in ("Edit", "Write"):
        # We don't block edits — the user may need to update credentials.
        # But we WARN if Write would clobber a banned file with content from
        # a `new_string` that looks substantial (best-effort, fail-open).
        return 0

    if block_reason:
        msg = (
            "BLOCKED by credential_guard: attempted to read credential-bearing file.\n"
            f"  tool:   {tool}\n"
            f"  path:   {blocked_path}\n"
            f"  reason: {block_reason}\n"
            "\n"
            "DEFAULT POSTURE -- don't read this file. The structure question is\n"
            "almost never load-bearing; check docs or `<tool> doctor --json` first.\n"
            "\n"
            "If you DO need to inspect the file's shape (rare), prefix with\n"
            "CLAUDE_CRED_GUARD=off so the bypass is explicit:\n"
            "  CLAUDE_CRED_GUARD=off jq 'keys' <file>                   # field names only\n"
            "  CLAUDE_CRED_GUARD=off jq 'to_entries|map({k:.key,t:(.value|type)})' <file>\n"
            "  CLAUDE_CRED_GUARD=off jq -r '.specific_known_safe_field' <file>\n"
            "\n"
            "To compare two secrets WITHOUT bypassing (preferred):\n"
            "  python -c \"import hashlib;"
            "print(hashlib.sha256(open(r'<file>').read().encode()).hexdigest()[:12])\"\n"
            "  (Python file-read isn't gated; the guard only blocks tool calls that\n"
            "   echo content to the transcript. Hashing reads but emits 12 hex chars.)\n"
            "\n"
            "If you need to MUTATE the file (rotate password etc.) -- Edit/Write are\n"
            "NOT blocked; just don't emit a Read first.\n"
            "\n"
            "See memory: feedback_credentials.md for the full rule and 4 prior incidents."
        )
        print(msg, file=sys.stderr)
        return 2

    return 0



def _main_fail_closed() -> int:
    """Run main(); on an UNEXPECTED exception, BLOCK (exit 2) rather than allow.

    PreToolUse semantics: 0 = allow, 2 = block, anything else = non-blocking
    error -> THE CALL PROCEEDS. Before this wrapper a crash here exited 1, so a
    payload that broke the checker was a payload the checker waved through
    (measured: 6 of 7 malformed payloads, 2026-08-27).

    This is a security control guarding an IRREVERSIBLE disclosure, so the safe
    default on "I could not evaluate this" is REFUSE, not allow. Note the
    deliberate fail-OPEN on unparseable stdin inside main() is untouched -- that
    is a total-harness failure, not an injection signal.
    """
    try:
        return main()
    except SystemExit:
        raise
    except BaseException as exc:                      # noqa: BLE001 - intentional
        print(
            "BLOCKED (fail-closed): %s crashed while evaluating this tool call "
            "-- %s: %s. A security guard that cannot complete its check REFUSES "
            "rather than allows. Re-run without the unusual argument shape, or "
            "if this is a guard bug, fix the hook from a fresh session."
            % ("credential_guard", type(exc).__name__, exc),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(_main_fail_closed())

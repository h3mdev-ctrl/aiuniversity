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
import hashlib
import json
import os
import pathlib
import re
import sys
from datetime import datetime, timezone

# --- redaction (added 2026-08-28) -------------------------------------------
# The live log held 3 secret-shaped matches, including a 113-char
# Discord-webhook-shaped URL, because line ~49 wrote raw command text. This log
# is the largest by 12x and sits one `git add -A` from a shared remote.
#
# High-precision shapes only. A generic "any long string" rule fires on hashes,
# base64 payloads and file digests, which would redact half the log and teach
# everyone to ignore the markers.
_SECRET_PATTERNS = [
    ("openai-key",       re.compile(r"\b(?:sk|sk-ant|sk-proj)-[A-Za-z0-9_\-]{20,}")),
    ("github-token",     re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("slack-token",      re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("discord-webhook",  re.compile(r"discord(?:app)?\.com/api/webhooks/\d+/[\w-]{20,}")),
    ("google-api-key",   re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("aws-access-key",   re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key",      re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("bearer",           re.compile(r"(?i)(?<=bearer )[A-Za-z0-9._\-]{20,}")),
    # \x22 = double quote, \x27 = single quote. Written as hex because a literal
    # quote inside this raw string terminates it -- the exact syntax error this
    # deploy hit on its first two attempts, caught by the compile() check.
    ("db-dsn",           re.compile(
        r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s\x22\x27]{10,}")),
    # NAME=value where NAME looks like a credential. TWO groups: the prefix is
    # kept so the log still shows WHICH key was being set -- usually the useful
    # part -- and only group 2, the value, is replaced.
    #
    # Written with a negated class for the optional opening quote rather than a
    # literal one: embedding a quote inside a raw string here is what made the
    # first draft fail to compile.
    ("env-assign",       re.compile(
        r"\b([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)\s*=\s*[^A-Za-z0-9\s]?)"
        r"([A-Za-z0-9._\-]{16,})")),
    # --- added 2026-08-28 -------------------------------------------------
    # Telegram bot token: <numeric bot id>:AA<35 chars>. The butler bridge uses
    # one, and a live token reached history.jsonl because this pattern did not
    # exist. Grants full control of the bot (read every message, post as it).
    # No leading \b: in an API URL the token follows letters (".../bot<token>"),
    # where \b does not match. (?<!\d) instead, so a longer number cannot be
    # partially consumed. Caught by the positive control, not by review.
    ("telegram-bot-token", re.compile(r"(?<!\d)\d{8,10}:AA[A-Za-z0-9_\-]{30,}")),
    # JWT -- Supabase anon AND service-role keys are JWTs, and the service-role
    # key bypasses RLS entirely. Three base64url segments, dot-separated.
    ("jwt",              re.compile(
        r"\beyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}")),
]


def _redact_secrets(text: str) -> str:
    """Replace secret-shaped substrings with a correlatable, valueless marker.

    Keeps the command's SHAPE -- the verb, the paths, what it touched -- because
    that is what this log exists to answer. The sha256[:12] means the same secret
    always produces the same marker, so repeats stay countable without the value
    ever reaching disk.
    """
    if not text:
        return text
    for label, rx in _SECRET_PATTERNS:
        def _sub(m: "re.Match", _label: str = label) -> str:
            # Two groups means "keep the prefix, redact the value" (NAME=secret).
            # `_label` is bound as a default argument so the closure captures THIS
            # iteration's label rather than the loop's last one.
            if m.re.groups >= 2:
                prefix, secret = m.group(1), m.group(2)
            else:
                prefix, secret = "", m.group(0)
            d = hashlib.sha256(secret.encode("utf-8", "replace")).hexdigest()[:12]
            return f"{prefix}<redacted:{_label}:{d}>"
        try:
            text = rx.sub(_sub, text)
        except Exception:
            continue          # one bad pattern must never drop the whole entry
    return text


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
            # Redact BEFORE truncating, or a secret survives by straddling the
            # 200-char boundary and landing half-written in the log.
            entry["cmd"] = _redact_secrets(inp.get("command", "") or "")[:200]
        if entry.get("file"):
            entry["file"] = _redact_secrets(entry["file"])
        if exit_code is not None:
            entry["exit_code"] = exit_code

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # audit log failure should never disrupt the main workflow

    return 0


if __name__ == "__main__":
    # Guarded, per windows_gotchas.md section 7: reconfigure() raises
    # AttributeError when stdout is not a real console (Task Scheduler, or
    # invoked from another script). The try/except made it harmless, but a hook
    # should not ship the anti-pattern it warns about.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

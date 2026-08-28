#!/usr/bin/env python
"""secret_patterns.py -- THE credential-shape list. One list, many consumers.

WHY THIS IS ITS OWN MODULE
--------------------------
On the machine this came from, a redactor and a log scanner each kept their own
pattern list. Both were missing Telegram bot tokens. The scan reported
ALL-CLEAR while a live bot token sat in plaintext on disk, because the scanner
could not name what the redactor could not name.

A pattern list is an ALLOWLIST OF THINGS YOU REMEMBERED. "No hits" only ever
means "no hits for what I thought of". Two lists means two blind spots that
drift apart, and the one that matters is always in the other file.

So: add a shape HERE, and every consumer gets it. If you also run the
audit-log hook from the `audit` pack, point it at this module too --
`setup_secret_hygiene.py --check-drift` will tell you when they disagree.

MARKER FORMAT
-------------
    <redacted:LABEL:sha256[:12]>
The digest makes repeats correlatable without the value ever being readable --
you can tell "the same secret appeared 4 times" from "4 different secrets"
without holding any of them.

TWO-GROUP PATTERNS
------------------
Where a pattern has 2 groups, group 1 is a PREFIX to keep and group 2 is the
value to replace -- so `AWS_SECRET_ACCESS_KEY=<redacted:...>` still tells you
WHICH key was being set, which is usually the useful half.
"""
from __future__ import annotations

import hashlib
import re

# Deliberately HIGH-PRECISION. "Any long random-looking string" fires on
# hashes, git SHAs and base64 payloads, and a scanner that cries wolf gets
# switched off -- see GUARD_DESIGN.md rules 3 and 7.
SECRET_PATTERNS: list[tuple[str, "re.Pattern"]] = [
    ("openai-key",       re.compile(r"\b(?:sk|sk-ant|sk-proj)-[A-Za-z0-9_\-]{20,}")),
    ("github-token",     re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("slack-token",      re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("discord-webhook",  re.compile(r"discord(?:app)?\.com/api/webhooks/\d+/[\w-]{20,}")),
    ("google-api-key",   re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("aws-access-key",   re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key",      re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("bearer",           re.compile(r"(?i)(?<=bearer )[A-Za-z0-9._\-]{20,}")),
    # NO leading \b: in an API URL the token follows letters (".../bot<token>"),
    # and \b does not match between a letter and a digit. The first draft used
    # \b, passed review, and was caught only by a positive control built from a
    # real URL. (?<!\d) instead, so a longer number is not partly consumed.
    ("telegram-bot-token", re.compile(r"(?<!\d)\d{8,10}:AA[A-Za-z0-9_\-]{30,}")),
    # Supabase anon AND service-role keys are JWTs; the service-role key
    # bypasses row-level security entirely.
    ("jwt",              re.compile(
        r"\beyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}")),
    # \x22 / \x27 are the quote characters written as hex ON PURPOSE: a literal
    # quote inside this raw string terminates it. That exact syntax error broke
    # two attempts at this file before a compile() gate caught it.
    ("db-dsn",           re.compile(
        r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?)://[^\s\x22\x27]{10,}")),
    # NAME=value where NAME looks like a credential. Two groups: keep the name.
    # Noisy against SOURCE CODE (any FOO_KEY = "literal"), so consumers that
    # scan source rather than shell command lines should filter this one out.
    ("env-assign",       re.compile(
        r"\b([A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)\s*=\s*[^A-Za-z0-9\s]?)"
        r"([A-Za-z0-9._\-]{16,})")),
]

MARKER_RE = re.compile(r"<redacted:[\w-]+:[0-9a-f]{12}>")


def redact(text: str) -> str:
    """Replace secret-shaped substrings with a correlatable, valueless marker.

    Keeps the SHAPE of the surrounding text -- the verb, the paths, the URL --
    because that is what makes a log worth keeping. Only the value goes.

    Call this BEFORE any truncation. Truncating first can slice a secret in
    half and leave its head in the file, matching nothing afterwards.
    """
    if not text:
        return text
    for label, rx in SECRET_PATTERNS:
        def _sub(m: "re.Match", _label: str = label) -> str:
            # `_label` is bound as a default argument so the closure captures
            # THIS iteration's label, not the loop's last one.
            if m.re.groups >= 2:
                prefix, secret = m.group(1), m.group(2)
            else:
                prefix, secret = "", m.group(0)
            dig = hashlib.sha256(secret.encode("utf-8", "replace")).hexdigest()[:12]
            return f"{prefix}<redacted:{_label}:{dig}>"
        text = rx.sub(_sub, text)
    return text


def digest(value: str) -> str:
    """sha256[:12] of a value -- the only form a secret may ever be shown in."""
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()[:12]


if __name__ == "__main__":
    # Self-test with SYNTHETIC specimens: correct shape, never real credentials.
    import sys

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    POSITIVE = [
        ("telegram in an API URL",
         "curl https://api.telegram.org/bot8112345678:"
         "AAF9zQ1x_pLmNbVcXsWq2rTyU3iOpAsDfGh/getMe"),
        # Every specimen here is built from PARTS so it does NOT match these
        # patterns as it sits on disk, while still being a whole value at run
        # time. Otherwise the pack's own positive controls would have to be
        # allowlisted -- and a control you have allowlisted is not a control.
        ("openai key", "export OPENAI_API_KEY=" + "sk-" "proj-" "AbCdEfGhIjKlMnOpQrStUvWx"),
        ("jwt", "K=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
                "eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaWF0IjoxNzAwMDAwMDAw."
                "aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcd"),
        ("discord webhook",
         "https://discord.com/api/webhooks/" "1234567890/" "AbCdEfGhIjKlMnOpQrStUvWxYz"),
        ("aws key", "AKIA" "IOSFODNN7EXAMPLE"),
    ]
    NEGATIVE = [
        ("plain timestamp", "run at 20260828 and log it"),
        ("ratio with a colon", "sharpe 12345678:12 across the window"),
        ("ordinary prose", "giving every row a key and collapsing rows that share it"),
        ("a git sha", "commit 51467b4a9c3d2e1f0b8a7c6d5e4f3a2b1c0d9e8f"),
    ]
    ok = True
    print("secret_patterns self-test")
    for name, s in POSITIVE:
        hit = "<redacted:" in redact(s)
        ok &= hit
        print(f"  {'ok  ' if hit else 'FAIL'}  redacts: {name}")
    for name, s in NEGATIVE:
        clean = redact(s) == s
        ok &= clean
        print(f"  {'ok  ' if clean else 'FAIL'}  leaves alone: {name}")
    print(f"\n{len(SECRET_PATTERNS)} patterns. "
          f"{'PASS' if ok else 'FAIL'}")
    raise SystemExit(0 if ok else 1)

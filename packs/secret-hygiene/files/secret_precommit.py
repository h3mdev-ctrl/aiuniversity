#!/usr/bin/env python
"""Block a commit that stages a secret. Installed as .git/hooks/pre-commit.

WHY THIS EXISTS
---------------
Two events on one machine, one morning:
  * `git add -A` swept a hook debug log into a commit. It happened to be clean.
  * A live Telegram bot token was found in a plaintext log, having survived a
    scan that reported all-clear.
Three repos, zero pre-commit hooks between them. Nothing scanned anything.

FAIL-CLOSED, ON PURPOSE
-----------------------
Most guards should fail OPEN -- wedging work is worse than a missed warning
(GUARD_DESIGN rule 4). This one is the documented exception: a secret pushed to
a remote is IRREVERSIBLE. Rewriting history does not un-publish it; rotation is
the only real remedy. So an unreadable pattern file, a crashed scan, or an
ambiguous result BLOCKS the commit.

`git commit --no-verify` remains the deliberate override. That is git's design.
Do not try to defeat it -- a guard people cannot escape is a guard they will
uninstall.

NEVER PRINTS A VALUE
--------------------
Path, line number, pattern LABEL, and sha256[:12]. Never the match, not even
partially, in either direction. You cannot ask for a secret to prove a secret.

ONE PATTERN LIST
----------------
Imported from secret_patterns.py, never copied. Two lists is how the Telegram
token survived: the scanner could not name what the redactor could not name.
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import subprocess
import sys

# Guarded: reconfigure() raises AttributeError when stdout is not a real
# console -- which is exactly how a git hook runs in some GUI clients.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOME = pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))
PATTERNS_FILE = HOME / "secret_patterns.py"
ALLOW_FILE = HOME / "secret_scan_allow.txt"

# Paths that should essentially never be committed, whatever their contents.
# `.env.example` / `.sample` / `.template` are the documented exception: they
# are meant to be tracked, and blocking them is pure friction.
BLOCKED_NAMES = re.compile(
    r"(?:^|/)(?:\.env(?!\.(?:example|sample|template|dist)$)(?:\.[\w-]+)?|"
    r"\.hook-debug\.log|audit\.jsonl|history\.jsonl|"
    r"credentials\.json|service[_-]account.*\.json|id_rsa|id_ed25519|"
    r"\.netrc|\.pgpass)$|\.(?:pem|key|pfx|p12|keystore|jks)$", re.I)

SKIP = re.compile(r"(?:^|/)(?:node_modules|\.venv|venv|__pycache__|dist|build|"
                  r"\.next|target)/", re.I)
MAX_BYTES = 2_000_000


def load_patterns():
    """Import THE pattern list. Fail CLOSED if it cannot be read."""
    try:
        spec = importlib.util.spec_from_file_location("_sp", PATTERNS_FILE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        pats = list(mod.SECRET_PATTERNS)
    except Exception as exc:
        print(f"pre-commit: cannot load patterns from {PATTERNS_FILE}: {exc}")
        print("pre-commit: BLOCKING -- refusing to commit without a scan.")
        raise SystemExit(1)
    # `env-assign` is tuned for shell command lines and is noisy against source
    # code (any FOO_KEY = "literal"). The dedicated shapes carry the signal.
    return [(lbl, rx) for lbl, rx in pats if lbl != "env-assign"], mod


def load_allowlist() -> set[str]:
    """Digests of values confirmed benign BY INSPECTION.

    A DIGEST, not a path and not a directory -- so allowing a placeholder in a
    test fixture does not also allow a real credential that later lands in the
    same file. That distinction is the whole reason this is not a `skip tests`
    rule.
    """
    try:
        if not ALLOW_FILE.is_file():
            return set()
        out = set()
        for line in ALLOW_FILE.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.split("#", 1)[0].strip()
            if re.fullmatch(r"[0-9a-f]{12}", line):
                out.add(line)
        return out
    except OSError:
        return set()          # unreadable allowlist allows nothing: still safe


def staged_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            capture_output=True, text=True, check=True).stdout
    except Exception as exc:
        print(f"pre-commit: cannot list staged files: {exc}")
        print("pre-commit: BLOCKING -- refusing to commit without a scan.")
        raise SystemExit(1)
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def main() -> int:
    pats, mod = load_patterns()
    allow = load_allowlist()
    files = staged_files()
    if not files:
        return 0

    findings: list[str] = []
    name_hits: list[str] = []

    for rel in files:
        if SKIP.search(rel):
            continue
        if BLOCKED_NAMES.search(rel):
            name_hits.append(rel)
            continue
        path = pathlib.Path(rel)
        if not path.is_file():
            continue
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            # An existing redaction marker is proof it was already handled.
            if "<redacted:" in line:
                continue
            for label, rx in pats:
                m = rx.search(line)
                if m:
                    val = m.group(2) if m.re.groups >= 2 else m.group(0)
                    dig = mod.digest(val)
                    if dig in allow:
                        break          # inspected, confirmed benign
                    findings.append(f"    {rel}:{i}  {label}  sha256[:12]={dig}")
                    break

    if not findings and not name_hits:
        return 0

    print("=" * 74)
    print("COMMIT BLOCKED -- secret-shaped content is staged")
    print("=" * 74)
    if name_hits:
        print("\n  files that should not be committed at all:")
        for f in name_hits:
            print(f"    {f}")
    if findings:
        print("\n  secret-shaped matches (values never shown):")
        for f in findings[:40]:
            print(f)
        if len(findings) > 40:
            print(f"    ... and {len(findings) - 40} more")
    print("\n" + "-" * 74)
    print("  unstage it:   git restore --staged <path>")
    print("  ignore it:    add the path to .gitignore, then unstage")
    print("  false alarm:  git commit --no-verify   (say why in the message)")
    print(f"  confirmed ok: add the sha256[:12] to {ALLOW_FILE}")
    print()
    print("  If the value was ever real, scrubbing the file is NOT enough --")
    print("  rotate the credential. Removing it from disk does not un-leak it.")
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:                      # noqa: BLE001 - fail closed
        print(f"pre-commit: scanner crashed: {exc}")
        print("pre-commit: BLOCKING -- a crashed scan is not a clean scan.")
        raise SystemExit(1)

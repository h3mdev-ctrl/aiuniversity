#!/usr/bin/env python
"""
setup_secret_hygiene.py -- install the pre-commit secret scanner + prove it blocks.

Modes:
    <repo> [<repo> ...]        install secret_patterns.py + secret_precommit.py
                               into <home>, and a pre-commit shim into each named
                               repo. Repos must be named EXPLICITLY -- there is no
                               cwd default, because installing a git hook mutates
                               whatever directory you are standing in.
    --files-only               install the shared files, touch no repository
    --check-files              exit 0 if both files are installed
    --check-installed <repo>   exit 0 if <repo>/.git/hooks/pre-commit is ours
    --test-blocking            behavioural: run REAL `git commit` calls in a
                               throwaway repo and prove a secret is refused, a
                               clean file is not, and --no-verify overrides
    --self-test                run the pattern module's own controls
    --check-drift              compare this pattern list against the audit-log
                               hook's, if that hook is installed

Home: $CLAUDE_HOME or ~/.claude

WHY --test-blocking RUNS A REAL COMMIT
--------------------------------------
A pre-commit hook that passes unit tests and never actually fires is the
wiring-dead failure. The only honest test of a git hook is a commit that gets
refused.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = pathlib.Path(__file__).resolve().parent
HOME = pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))
PATTERNS = HOME / "secret_patterns.py"
SCANNER = HOME / "secret_precommit.py"
ALLOW = HOME / "secret_scan_allow.txt"

SHIM = """#!/bin/sh
# Secret scanner -- see secret_precommit.py in your Claude home.
# Fail-closed: a secret pushed to a remote cannot be un-published.
exec python "$CLAUDE_SECRET_SCANNER"
"""

ALLOW_SEED = """# Digests (sha256[:12]) of secret-shaped values confirmed BENIGN by inspection.
# One per line; `#` comments allowed.
#
# A DIGEST, not a path: allowing a placeholder in a test fixture must not also
# allow a real credential that later lands in the same file.
#
# NEVER add a digest you have not looked at. The scanner prints the digest of
# whatever it found, so the workflow is: read the line, decide, paste the digest.
#
# The pack's own test specimens are built from PARTS so they do not match
# these patterns as they sit on disk -- a positive control that had to be
# allowlisted would not be a control at all.
"""

FAKE_TOKEN = "8112345678" ":" "AA" "F9zQ1x_pLmNbVcXsWq2rTyU3iOpAsDfGh"
FAKE_KEY = "sk-" "proj-" "AbCdEfGhIjKlMnOpQrStUvWx"


def _shim_for(scanner: pathlib.Path) -> str:
    return SHIM.replace('"$CLAUDE_SECRET_SCANNER"', f'"{scanner.as_posix()}"')


def install(repos: list[pathlib.Path]) -> int:
    HOME.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HERE / "secret_patterns.py", PATTERNS)
    shutil.copy2(HERE / "secret_precommit.py", SCANNER)
    print(f"* {PATTERNS}")
    print(f"* {SCANNER}")
    if not ALLOW.exists():
        ALLOW.write_text(ALLOW_SEED, encoding="utf-8")
        print(f"* {ALLOW} (empty seed)")

    for repo in repos:
        hooks = repo / ".git" / "hooks"
        if not (repo / ".git").exists():
            print(f"  --   {repo}: not a git repo, skipped")
            continue
        hooks.mkdir(parents=True, exist_ok=True)
        target = hooks / "pre-commit"
        if target.exists() and "secret_precommit" not in target.read_text(
                encoding="utf-8", errors="replace"):
            print(f"  !!   {repo.name}: a different pre-commit exists, NOT overwritten")
            continue
        target.write_text(_shim_for(SCANNER), encoding="utf-8", newline="\n")
        os.chmod(target, 0o755)
        print(f"  ok   {repo.name}: pre-commit installed")
    return 0


def test_blocking() -> int:
    """Drive REAL git commits through the installed hook."""
    if not SCANNER.is_file() or not PATTERNS.is_file():
        print("not installed -- run without arguments first")
        return 1
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="secretscan_"))
    ok = True
    try:
        run = lambda a: subprocess.run(a, cwd=str(tmp), capture_output=True, text=True)
        run(["git", "init", "-q"])
        run(["git", "config", "user.email", "t@t"])
        run(["git", "config", "user.name", "t"])
        hooks = tmp / ".git" / "hooks"
        hooks.mkdir(parents=True, exist_ok=True)
        (hooks / "pre-commit").write_text(_shim_for(SCANNER), encoding="utf-8",
                                          newline="\n")
        os.chmod(hooks / "pre-commit", 0o755)

        cases = [
            ("clean file commits", "notes.md", "# just notes\n", True),
            ("telegram token refused", "cfg.py", f'BOT = "{FAKE_TOKEN}"\n', False),
            ("openai key refused", "setup.sh", f"export OPENAI_API_KEY={FAKE_KEY}\n", False),
            ("already-redacted line commits", "log.jsonl",
             '{"cmd":"bot<redacted:telegram-bot-token:4e6c19f44cdb>/getMe"}\n', True),
            (".env refused by name", ".env", "HARMLESS=1\n", False),
            (".pem refused by name", "server.pem", "not a key\n", False),
            (".env.example commits", ".env.example", "OPENAI_API_KEY=\n", True),
        ]
        for name, fn, body, should_pass in cases:
            (tmp / fn).write_text(body, encoding="utf-8")
            run(["git", "add", "-A", "-f"])
            r = run(["git", "commit", "-q", "-m", "t"])
            passed = r.returncode == 0
            good = passed == should_pass
            ok &= good
            print(f"  {'ok  ' if good else 'FAIL'}  {name:<32} "
                  f"{'committed' if passed else 'refused'}")
            if not passed:
                run(["git", "reset", "-q", "HEAD"])
                (tmp / fn).unlink(missing_ok=True)

        (tmp / "c2.py").write_text(f'BOT = "{FAKE_TOKEN}"\n', encoding="utf-8")
        run(["git", "add", "-A", "-f"])
        r = run(["git", "commit", "-q", "--no-verify", "-m", "override"])
        good = r.returncode == 0
        ok &= good
        print(f"  {'ok  ' if good else 'FAIL'}  {'--no-verify still overrides':<32} "
              f"{'committed' if good else 'refused'}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nVERDICT:", "HEALTHY" if ok else "BROKEN")
    return 0 if ok else 1


def check_drift() -> int:
    """Do the scanner and the audit-log hook share one pattern list?

    This is GUARD_DESIGN's "a pattern list is an allowlist of things you
    remembered" made runnable. Two lists drift, and the shape that matters is
    always in the other file.
    """
    audit_hook = HOME / "hooks" / "tool_audit_log.py"
    if not audit_hook.is_file():
        print("audit-log hook not installed -- nothing to drift against. OK.")
        return 0
    import importlib.util

    def labels(path: pathlib.Path, attr: str) -> set[str] | None:
        try:
            spec = importlib.util.spec_from_file_location(f"_d_{path.stem}", path)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            return {lbl for lbl, _ in getattr(m, attr)}
        except Exception as exc:
            print(f"  could not read {path.name}: {exc}")
            return None

    mine = labels(PATTERNS, "SECRET_PATTERNS")
    theirs = labels(audit_hook, "_SECRET_PATTERNS")
    if mine is None or theirs is None:
        print("VERDICT: BROKEN (could not compare)")
        return 1
    only_mine, only_theirs = mine - theirs, theirs - mine
    if not only_mine and not only_theirs:
        print(f"  ok   both lists agree ({len(mine)} shapes)")
        print("VERDICT: HEALTHY")
        return 0
    if only_theirs:
        print(f"  !!   audit hook has shapes the scanner lacks: {sorted(only_theirs)}")
    if only_mine:
        print(f"  !!   scanner has shapes the audit hook lacks: {sorted(only_mine)}")
    print("\n  Two lists means two blind spots. Point both at secret_patterns.py.")
    print("VERDICT: DRIFTED")
    return 1


def main(argv: list[str]) -> int:
    if "--files-only" in argv:
        return install([])
    if "--check-files" in argv:
        good = PATTERNS.is_file() and SCANNER.is_file()
        print("installed" if good else "missing secret_patterns.py / secret_precommit.py")
        return 0 if good else 1
    if "--self-test" in argv:
        return subprocess.run([sys.executable, str(HERE / "secret_patterns.py")]).returncode
    if "--test-blocking" in argv:
        return test_blocking()
    if "--check-drift" in argv:
        return check_drift()
    if "--check-installed" in argv:
        i = argv.index("--check-installed")
        repo = pathlib.Path(argv[i + 1]) if len(argv) > i + 1 else pathlib.Path.cwd()
        hook = repo / ".git" / "hooks" / "pre-commit"
        good = hook.is_file() and "secret_precommit" in hook.read_text(
            encoding="utf-8", errors="replace")
        print(f"{'installed' if good else 'not installed'} in {repo}")
        return 0 if good else 1

    repos = [pathlib.Path(a) for a in argv if not a.startswith("-")]
    if not repos:
        # Deliberately NOT defaulting to cwd. An earlier version did, and a test
        # that invoked the installer with no arguments silently replaced the
        # REAL repository's pre-commit hook with one pointing into a pytest temp
        # directory -- which was then deleted. The next commit failed closed with
        # a confusing error, and the only reason it was noticed at all is that
        # this scanner blocks rather than skips when it cannot load its patterns.
        # Installing a git hook is a mutation of whatever directory you happen to
        # be standing in; make the caller name it.
        print("usage: setup_secret_hygiene.py <repo> [<repo> ...]")
        print()
        print("Name the repositories explicitly. Installing a git hook mutates")
        print("the repo you are standing in, so this does not default to cwd.")
        print("To install the shared files only, with no repo:")
        print("  setup_secret_hygiene.py --files-only")
        return 2
    return install(repos)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python
"""recon_before_build_guard.py -- Claude Code PreToolUse hook: recon before build.

Fires when Claude is about to WRITE a NEW source file into a repo that ALREADY has
source files -- i.e. the exact moment it's most likely to build a parallel module
instead of reading and extending the one that's already there. It bounces the Write
ONCE per (session, repo) with a reminder to read the neighbouring code first, then
gets out of the way so it's a nudge, not a wall.

Why a hook and not just a memory / constitution line: the "shoulders of giants --
don't reinvent" principle is always loaded and STILL gets skipped, because at the
moment a task says "build X" and there's enough context to start typing, acting
feels like progress and reading feels like delay. A memory hopes to be recalled;
a PreToolUse hook fires ON THE ACTION -- same reason the session-end Stop hook beats
the stop-phrase memory. (Worked example that motivated this: a Claude re-derived a
whole subset-sum matcher + edge cases that already lived 40 lines away in the same
folder, over hours, because it never read the file.)

Only fires when ALL hold, so it stays quiet on genuine new work:
  - tool is Write, and the target file does NOT already exist (a real NEW file);
  - the file is source code (.py/.ts/.go/... -- not docs/config/data);
  - its directory already holds >= MIN_SIBLINGS files of the same extension
    (an established codebase, not a fresh/empty project);
  - it hasn't already nudged for this (session, repo) -- so at most once per repo
    per session.

Exit codes:
  0 -- allow (not a match, or already nudged this session for this repo)
  2 -- bounce once: stderr carries the recon reminder Claude reads next turn
"""
import hashlib
import json
import os
import pathlib
import sys

SOURCE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".rb", ".java", ".c",
    ".h", ".cpp", ".hpp", ".cc", ".cs", ".php", ".swift", ".kt", ".scala",
    ".sh", ".ps1", ".lua", ".r", ".jl", ".ex", ".exs",
}
MIN_SIBLINGS = 2   # same-ext files already in the dir -> it's an established codebase


def base_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def _ack_dir() -> pathlib.Path:
    return base_dir() / ".recon_ack"


def _repo_key(path: pathlib.Path) -> str:
    """Stable key for the repo/dir this file lives in -- prefer the git root so the
    nudge is once per PROJECT, not once per sub-directory."""
    d = path.parent
    cur = d
    for _ in range(40):
        if (cur / ".git").exists():
            d = cur
            break
        if cur.parent == cur:
            break
        cur = cur.parent
    return hashlib.sha1(str(d.resolve()).encode()).hexdigest()[:16]


def _should_nudge(payload: dict) -> "tuple[bool, str, int, str]":
    """Returns (nudge?, ext, sibling_count, dirname)."""
    if (payload.get("tool_name") or payload.get("tool") or "") != "Write":
        return False, "", 0, ""
    ti = payload.get("tool_input") or payload.get("toolInput") or {}
    fp = ti.get("file_path") or ti.get("path") or ""
    if not fp:
        return False, "", 0, ""
    path = pathlib.Path(fp)
    if path.suffix.lower() not in SOURCE_EXTS:
        return False, "", 0, ""
    if path.exists():                       # editing/overwriting an existing file is fine
        return False, "", 0, ""
    parent = path.parent
    if not parent.exists():                 # brand-new directory -> genuinely new work
        return False, "", 0, ""
    try:
        siblings = [f for f in parent.iterdir()
                    if f.is_file() and f.suffix.lower() == path.suffix.lower()]
    except OSError:
        return False, "", 0, ""
    if len(siblings) < MIN_SIBLINGS:
        return False, "", 0, ""
    return True, path.suffix.lower(), len(siblings), parent.name


def _already_nudged(session_id: str, key: str) -> bool:
    marker = _ack_dir() / f"{session_id or 'nosess'}__{key}"
    if marker.exists():
        return True
    try:
        _ack_dir().mkdir(parents=True, exist_ok=True)
        marker.write_text("1", encoding="utf-8")
    except OSError:
        pass
    return False


def main() -> int:
    # FAIL OPEN on ANY error. A guard must never wedge work: if this hook can't parse
    # its input or hits an unexpected exception, it ALLOWS the action (exit 0) rather
    # than blocking it. A PreToolUse hook exiting non-zero for a reason other than a
    # deliberate bounce would silently break every matched Write. (Jason, real-machine
    # install, 2026-07-08.)
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        nudge, ext, n, dirname = _should_nudge(payload)
        if not nudge:
            return 0
        fp = (payload.get("tool_input") or payload.get("toolInput") or {}).get("file_path") \
            or (payload.get("tool_input") or {}).get("path") or ""
        key = _repo_key(pathlib.Path(fp))
        session_id = str(payload.get("session_id") or payload.get("sessionId") or "")
        if _already_nudged(session_id, key):
            return 0
        sys.stderr.write(
            f"RECON BEFORE BUILD -- you're about to Write a NEW {ext} file into '{dirname}/', "
            f"which already holds {n} {ext} files. This is the moment a parallel module gets "
            f"built instead of extending the one already there.\n"
            f"FIRST: grep the neighbours (*match*/*reconcile*/*_check*/*sync*/the main module) "
            f"+ read the project memory, open the ones that plausibly already do this, and say "
            f"in one line what exists and the real gap. If you've done that recon, just Write "
            f"again -- this won't fire again for this repo this session.\n"
        )
        return 2
    except Exception:
        return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main())

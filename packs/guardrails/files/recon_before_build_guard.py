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
  - the target directory is not a scratch/temp dir (see SCRATCH_PARTS);
  - its directory already holds >= MIN_SIBLINGS files of the same extension
    (an established codebase, not a fresh/empty project);
  - the session shows NO evidence recon already happened in that directory;
  - it hasn't already nudged for this (session, repo) -- so at most once per repo
    per session.

--------------------------------------------------------------------------------
Why the scratch-dir and recon-evidence conditions exist
--------------------------------------------------------------------------------
On the machine this guard came from, 246 fires were measured across 156 sessions.
Partitioned by target directory, two problems showed up that the raw "hit rate"
had hidden -- and neither was visible until the fires were PARTITIONED. A single
aggregate number said the guard was busy; it could not say whether being busy was
good.

  1. 93 of 246 (38%) targeted a SCRATCH directory -- 86 of them the session
     scratchpad the system prompt explicitly instructs Claude to use for temp
     files. "Grep the neighbours before you write" is meaningless advice about a
     throwaway script, and the share was NOT declining (13 in W34, 17 in W28).
     A guard that bounces you for following your own instructions trains you to
     dismiss it, which costs it authority on the 62% that matter.
     -> SCRATCH_PARTS.

  2. The remaining 153 were not measuring the behaviour at all. The guard fires
     on the Write regardless of whether recon happened -- it has no way to know.
     So the "hit rate" was really "how often does Claude create a new source file
     in an established directory", which for a builder shipping several items a
     day should be OFTEN. It could never trend to zero, and a metric that cannot
     improve cannot be managed.
     -> _recon_evidence(): read the session transcript, and if Claude already
        Read/Grep/Glob'd inside the target directory this session, allow silently.

After this change a fire means something specific and falsifiable: a new source
file went into an established directory that this session had never looked at.
THAT number can go down, and it is the one worth watching.

Exit codes:
  0 -- allow (not a match, recon evidence found, or already nudged this session)
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

# Path components that mark a throwaway/staging area. Matched against the LOWERCASED
# parts of the target path. Kept deliberately tight: a real module directory must not
# fall in here just because its name contains "tmp" as a substring, so this is an
# exact component match, not a substring search.
#
# Bare "tmp"/"temp" are deliberately NOT here. They would swallow any project that
# happens to live under a path with a `temp` component (C:\temp\proj\src\...), and the
# case they were meant to catch -- the OS temp tree, where the session scratchpad lives
# -- is handled precisely by _under_os_temp() instead. Caught by the negative control:
# with "temp" in this set, every test fixture built in a tempdir looked like a pass.
SCRATCH_PARTS = {
    "scratchpad", "hook_staging",
    "scratch", "sandbox", "playground", "_scratch", "throwaway",
}

# How many transcript lines back to look for recon evidence. The transcript is JSONL
# and can be tens of MB, so read the tail rather than the whole file.
TRANSCRIPT_TAIL_LINES = 4000

# Tools whose use inside the target directory counts as recon.
RECON_TOOLS = {"Read", "Grep", "Glob", "NotebookRead", "Bash", "PowerShell"}


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


def _under_os_temp(path: pathlib.Path) -> bool:
    """True if the target lives under the OS temp tree -- which is where Claude Code's
    per-session scratchpad is, and the single largest source of pointless fires
    (86 of 246 measured). Resolved rather than string-matched so a Windows 8.3
    short path (C:\\Users\\ANDRE~1\\...) still matches its long form.

    CLAUDE_RECON_SELFTEST disables this one exclusion, because a test fixture has
    to build a fake populated repo somewhere and `tempfile` puts it in exactly the
    tree this rule ignores -- so without the flag the selftest asserts silence and
    calls it a pass, which is how a guard's own test stops testing anything. Note
    the direction: the flag can only make the guard fire MORE. It is not a bypass,
    and there is deliberately no flag that makes it fire less.
    """
    if os.environ.get("CLAUDE_RECON_SELFTEST") == "1":
        return False
    import tempfile
    for root in {os.environ.get("TEMP"), os.environ.get("TMP"), tempfile.gettempdir()}:
        if not root:
            continue
        try:
            if pathlib.Path(path).resolve().is_relative_to(pathlib.Path(root).resolve()):
                return True
        except (OSError, ValueError):
            continue
    return False


def _is_scratch(path: pathlib.Path) -> bool:
    """True if the target sits in a throwaway/staging area."""
    if any(p.lower() in SCRATCH_PARTS for p in path.parts):
        return True
    return _under_os_temp(path)


def _norm(s: str) -> str:
    """Lowercase, forward-slash, and COLLAPSE repeated separators.

    The collapse is load-bearing on Windows: the transcript stores tool input as JSON,
    so a path arrives with its backslashes escaped (`C:\\\\x\\\\y`). Turning those into
    slashes yields `c://x//y`, which never matches a needle built from a live Path
    (`c:/x/y`). Without this, directory-level recon evidence silently never matched and
    the guard fired anyway -- caught by control T2a.
    """
    out = str(s).replace("\\", "/").lower()
    while "//" in out:
        out = out.replace("//", "/")
    return out


def _recon_evidence(transcript_path: str, parent: pathlib.Path,
                    siblings: "list[pathlib.Path]") -> str:
    """Return a short reason string if this session already reconnoitred `parent`,
    else "". Evidence = any Read/Grep/Glob/shell call this session whose input names
    the target directory or one of the files already in it.

    Fails OPEN on any error (returns "" -> the guard behaves exactly as before), so a
    malformed or missing transcript can never turn this into a hard block.
    """
    if not transcript_path:
        return ""
    try:
        p = pathlib.Path(transcript_path)
        if not p.exists():
            return ""
        with p.open(encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()[-TRANSCRIPT_TAIL_LINES:]
    except OSError:
        return ""

    dir_needle = _norm(parent)
    # Sibling basenames are a weaker but real signal: `Read src/matcher.py` names the
    # file, and on a relative path the directory may not appear at all.
    sib_needles = {f.name.lower() for f in siblings}

    for line in lines:
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        msg = rec.get("message") or {}
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name = block.get("name") or ""
            if name not in RECON_TOOLS:
                continue
            try:
                blob = _norm(json.dumps(block.get("input") or {}))
            except (TypeError, ValueError):
                continue
            if dir_needle and dir_needle in blob:
                return f"{name} touched {parent.name}/ earlier this session"
            for sib in sib_needles:
                if sib and sib in blob:
                    return f"{name} opened {sib} earlier this session"
    return ""


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
    if _is_scratch(path):                   # throwaway script, nothing to reconnoitre
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
    # The recon already happened -> the guard has nothing to add, stay silent.
    if _recon_evidence(str(payload.get("transcript_path") or ""), parent, siblings):
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
            f"which already holds {n} {ext} files AND THIS SESSION HAS NEVER READ ANYTHING IN "
            f"IT. This is the moment a parallel module gets built instead of extending the one "
            f"already there.\n"
            f"FIRST: grep the neighbours (*match*/*reconcile*/*_check*/*sync*/the main module) "
            f"+ read the project memory, open the ones that plausibly already do this, and say "
            f"in one line what exists and the real gap. Opening any file in that directory "
            f"clears this guard for the rest of the session.\n"
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

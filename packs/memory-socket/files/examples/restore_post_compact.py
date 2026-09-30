#!/usr/bin/env python3
"""
SOCKET: restore           EVENT: PostCompact
Hermes equivalent: the read side of on_pre_compress

Re-inject what the salvage socket saved. Salvage without restore writes a file
nobody reads; restore without salvage prints "re-read your rules" and calls that
memory. They are one mechanism split across two events.

THE FALLBACK YOU MUST NOT WRITE
-------------------------------
The obvious convenience is: if there is no session_id, use the most recent carry
file in the directory. It is a one-line change, it makes the hook "more robust",
and it is a data leak. Several sessions run at once on a normal machine, so the
newest carry file frequently belongs to a DIFFERENT session -- and this hook
prints its contents under a banner saying "established fact of THIS session".
Confidently showing someone else's work is strictly worse than showing nothing.
Refuse instead, and say so.

THE KEY THAT ACTUALLY WORKS
---------------------------
Claude Code assigns a NEW session_id at compaction: one continuous conversation
produces two transcript files either side of the compact. So a carry keyed only
on session_id is written under one id and looked up under another -- this hook
then prints "no carry-forward found" every time, which reads as a benign miss
and is the feature being dead. (Measured on the author's box: the session-keyed
version had never once worked.)

So lookup tries TWO keys, in order:
  1. <session_id>.md   exact; hits only if the id did not change
  2. cwd-<hash>.md     survives the re-key; scoped to ONE working directory,
                       so a sibling worktree can never match. Accepted only if
                       written in the last CWD_MAX_AGE_S -- salvage runs seconds
                       before restore, so a wider window only buys the risk of
                       picking up ANOTHER session that compacted in the same
                       directory.
Never a third "newest file anywhere" key -- see above.

CONTRACT
  stdin : JSON {session_id, cwd}   (either may be absent)
  stdout: plain text injected after compaction
  exit  : ALWAYS 0.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time

# Must match salvage_pre_compact.py: both honour CLAUDE_HOME.
CARRY_DIR = (pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))
             / "state" / "compact_carry")
MAX_AGE_S = 3600      # session key: older than this belongs to a previous compaction
CWD_MAX_AGE_S = 900   # cwd key: salvage ran seconds ago; 15 min is generous
ORIGIN_RE = re.compile(r"^<!--\s*origin-session:\s*(\S+).*?-->\s*", re.S)


def cwd_key(cwd: str) -> str:
    """MUST stay byte-identical to salvage_pre_compact.cwd_key."""
    import hashlib
    try:
        norm = str(pathlib.Path(cwd).resolve())
    except OSError:
        norm = cwd
    return hashlib.sha256(norm.lower().encode("utf-8")).hexdigest()[:16]


def _fresh(p: pathlib.Path, max_age: float) -> str:
    try:
        if p.is_file() and time.time() - p.stat().st_mtime <= max_age:
            return p.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        pass
    return ""


def carry_for(session_id: str, cwd: str) -> tuple[str, str]:
    """-> (digest, how_found). how_found is 'session', 'cwd:<origin>' or ''."""
    if not CARRY_DIR.is_dir():
        return "", ""
    if session_id:
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)[:64]
        text = _fresh(CARRY_DIR / f"{safe}.md", MAX_AGE_S)
        if text:
            return ORIGIN_RE.sub("", text, count=1), "session"
    if cwd:
        text = _fresh(CARRY_DIR / f"cwd-{cwd_key(cwd)}.md", CWD_MAX_AGE_S)
        if text:
            m = ORIGIN_RE.match(text)
            return ORIGIN_RE.sub("", text, count=1), f"cwd:{m.group(1) if m else '?'}"
    return "", ""           # DELIBERATELY NO "NEWEST FILE" FALLBACK.


def main() -> int:
    session_id, cwd = "", ""
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if isinstance(data, dict):
            session_id = str(data.get("session_id") or "")
            cwd = str(data.get("cwd") or "")
    except Exception:
        pass
    cwd = cwd or os.getcwd()

    carry, how = carry_for(session_id, cwd)

    print("CONTEXT COMPACTED - your rules and constraints are unchanged.")
    if carry:
        print()
        print(carry)
        print()
        print("(Salvaged from the discarded messages by the PreCompact hook.")
        print(" Established fact of this session, not a new proposal.)")
        if how.startswith("cwd:"):
            # Say which key hit. Via cwd the origin id normally differs from
            # ours because compaction re-keyed us -- expected, but visible, so a
            # carry that came from a different conversation is recognisable.
            print(f" Matched by working directory; written by session "
                  f"{how[4:]} (the pre-compaction id of this conversation).")

    print()
    print("Re-read your project instructions to restore the static rules:")
    for name in ("CLAUDE.md", "AGENTS.md"):
        p = pathlib.Path(os.getcwd()) / name
        if p.exists():
            print(f"  {p}")

    if not carry:
        # Say the failure out loud. A restore hook that silently prints only the
        # boilerplate looks identical to a working one -- and the session then
        # proceeds believing its findings survived when they did not.
        print("NOTE: no carry-forward digest found - session-specific findings")
        print("(measurements, decisions, what failed) were NOT preserved.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())

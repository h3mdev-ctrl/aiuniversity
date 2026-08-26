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

CONTRACT
  stdin : JSON {session_id}   (may be absent)
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

CARRY_DIR = pathlib.Path.home() / ".claude" / "state" / "compact_carry"
MAX_AGE_S = 3600      # older than this and it belongs to a previous compaction


def carry_for(session_id: str) -> str:
    if not (session_id and CARRY_DIR.is_dir()):
        return ""           # DELIBERATELY NO FALLBACK -- see docstring.
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)[:64]
    p = CARRY_DIR / f"{safe}.md"
    if not p.is_file():
        return ""
    try:
        if time.time() - p.stat().st_mtime > MAX_AGE_S:
            return ""
        return p.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def main() -> int:
    session_id = ""
    try:
        data = json.loads(sys.stdin.read() or "{}")
        if isinstance(data, dict):
            session_id = str(data.get("session_id") or "")
    except Exception:
        pass

    carry = carry_for(session_id)

    print("CONTEXT COMPACTED - your rules and constraints are unchanged.")
    if carry:
        print()
        print(carry)
        print()
        print("(Salvaged from the discarded messages by the PreCompact hook.")
        print(" Established fact of this session, not a new proposal.)")

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

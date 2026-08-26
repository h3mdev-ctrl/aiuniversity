#!/usr/bin/env python3
"""
SOCKET: identity          EVENT: SessionStart
Hermes equivalent: USER.md injection (Honcho's "user representation")

Inject the always-on model of the user at session start.

WHY THIS IS NOT A RETRIEVAL PROBLEM
-----------------------------------
It is tempting to file the user model as memory #57 and let the recall socket
find it. That fails in a specific way: retrieval matches the PROMPT, so the
user model would only surface when the user happened to talk about themselves --
which is close to never. A model of the user is relevant to every turn. It
belongs in the small always-loaded tier, not the searchable one.

WHY THE CAP IS THE WHOLE DESIGN
-------------------------------
Always-loaded means it costs tokens on every single turn, so it must stay small,
which means it must be REGENERATED rather than appended to. An append-only user
model grows until it is indistinguishable from the corpus it was meant to
summarise, and stale facts sit there looking as current as fresh ones. Cap it,
regenerate it on a schedule, and let the cap force the consolidation.

CONTRACT
  stdin : JSON {session_id, source}
  stdout: plain text injected into context
  exit  : ALWAYS 0. Never break session startup.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

CAP = 1800          # characters. Hermes' USER.md sits at ~1375.
HARD_REFUSE = CAP * 2


def memory_dir(cwd: str) -> pathlib.Path | None:
    if os.environ.get("CLAUDE_MEMORY_HOME"):
        return pathlib.Path(os.environ["CLAUDE_MEMORY_HOME"])
    for base in (pathlib.Path(cwd), *pathlib.Path(cwd).parents):
        cand = base / "memory"
        if (cand / "MEMORY.md").is_file():
            return cand
    return None


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        cwd = str(data.get("cwd") or os.getcwd())
        memdir = memory_dir(cwd)
        if not memdir:
            return 0
        p = memdir / "user_representation.md"
        if not p.is_file():
            return 0

        text = p.read_text(encoding="utf-8", errors="replace")
        if text.startswith("---"):                 # drop YAML frontmatter
            parts = text.split("\n---", 1)
            if len(parts) == 2:
                text = parts[1].lstrip("-\n")

        # Refuse a bloated file rather than silently paying for it every turn.
        # Failing loudly here is wrong (it would break startup); failing SILENTLY
        # but visibly-in-the-audit is right -- which is why socket_doctor.py
        # probes for output instead of trusting registration.
        if len(text) > HARD_REFUSE:
            return 0

        print("=== USER (derived model - always-on) ===")
        print(text.strip())
        print("=" * 40)
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())

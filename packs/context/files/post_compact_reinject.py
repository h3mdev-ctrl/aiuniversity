#!/usr/bin/env python3
"""
post_compact_reinject.py -- PostCompact hook that re-injects critical rules.

After a transcript is compacted (summarised), the model can forget constraints
it was following — especially ones from CLAUDE.md or AGENTS.md that were loaded
early in the session. The compaction summary rarely preserves all the detail.

This hook fires after every compaction and prints a reminder to:
  - Re-read CLAUDE.md and any AGENTS.md in the project
  - Check what constraints / invariants were in effect
  - Not assume a "clean slate" just because context was compressed

The stdout of PostCompact hooks is injected into model context.
"""
import os
import pathlib
import sys


def main() -> None:
    cwd = os.getcwd()
    files_to_reread: list[str] = []

    for name in ("CLAUDE.md", "AGENTS.md"):
        p = pathlib.Path(cwd) / name
        if p.exists():
            files_to_reread.append(str(p))

    parent = pathlib.Path(cwd).parent
    for name in ("CLAUDE.md", "AGENTS.md"):
        p = parent / name
        if p.exists() and str(p) not in files_to_reread:
            files_to_reread.append(str(p))

    print("CONTEXT COMPACTED — your rules and constraints are unchanged.")
    print("Before continuing, re-read your project instructions to restore working context:")
    if files_to_reread:
        for f in files_to_reread:
            print(f"  {f}")
    else:
        print("  CLAUDE.md / AGENTS.md (check the project root and parent directories)")
    print("Your active constraints, hard invariants, and workflow rules are all still in effect.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()

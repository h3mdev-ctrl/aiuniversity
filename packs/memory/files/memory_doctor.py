#!/usr/bin/env python
"""
memory_doctor.py -- structural audit of a file-based memory system.

Checks STRUCTURE, not content:
  1. MEMORY.md (the always-loaded index) exists.
  2. No DARK files -- every memory file is reachable from MEMORY.md. A memory the
     index can't route to is invisible in practice, even though it's on disk.
  3. The index stays short (routing only) -- warn over the line budget.
  4. Every memory file has frontmatter: name, description, type.

Prints one line per issue, then `VERDICT: HEALTHY` or `VERDICT: ISSUES`.
Exit 0 if healthy, 1 if issues.

Home: $CLAUDE_HOME or ~/.claude ; memory lives in <home>/memory. (The env override
lets tests and demos run against a throwaway home without touching real ~/.claude.)

This file is installed into your memory folder so you keep the audit even if the
pack goes away. Andrew's habit: run it after any memory write.
"""
import os
import pathlib
import sys

INDEX_LINE_BUDGET = 200


def candidate_dirs() -> "list[pathlib.Path]":
    """Where a memory system might live -- explicit override, global, then any
    project-scoped folder (~/.claude/projects/<hash>/memory)."""
    env = os.environ.get("CLAUDE_MEMORY_HOME")
    if env:
        return [pathlib.Path(env)]
    base = pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))
    dirs = [base / "memory"]
    proj = base / "projects"
    if proj.exists():
        dirs += sorted(proj.glob("*/memory"))
    return dirs


def find_memory() -> "pathlib.Path | None":
    """The first candidate that actually holds a MEMORY.md, else None."""
    for d in candidate_dirs():
        if (d / "MEMORY.md").exists():
            return d
    return None


def is_memory_file(p: pathlib.Path) -> bool:
    # A real memory entry is <type>_<topic>.md -- not the index, a template, or
    # the doctor itself.
    if p.name == "MEMORY.md" or p.name.startswith("_"):
        return False
    return p.suffix == ".md"


def has_frontmatter(text: str) -> bool:
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    if end == -1:
        return False
    fm = text[3:end]
    return all(key in fm for key in ("name:", "description:", "type:"))


def run() -> int:
    m = find_memory()
    if m is None:
        print("[none] no memory system found. Searched:")
        for d in candidate_dirs():
            print(f"  - {d}")
        print("VERDICT: ISSUES")
        return 1

    print(f"[found] auditing memory at {m}")
    index = m / "MEMORY.md"
    index_text = index.read_text(encoding="utf-8")
    issues: list[str] = []

    for p in sorted(m.glob("*.md")):
        if not is_memory_file(p):
            continue
        # reachable? the slug or filename must appear somewhere in the index.
        if p.stem not in index_text and p.name not in index_text:
            issues.append(f"[dark] {p.name} is not linked from MEMORY.md (unreachable)")
        if not has_frontmatter(p.read_text(encoding="utf-8")):
            issues.append(f"[frontmatter] {p.name} missing name/description/type frontmatter")

    line_count = len(index_text.splitlines())
    if line_count > INDEX_LINE_BUDGET:
        issues.append(
            f"[size] MEMORY.md is {line_count} lines (budget {INDEX_LINE_BUDGET}) "
            f"-- move detail into files, keep the index routing-only"
        )

    for issue in issues:
        print(issue)
    if issues:
        print("VERDICT: ISSUES")
        return 1
    print("VERDICT: HEALTHY")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(run())

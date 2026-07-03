#!/usr/bin/env python
"""
memory_doctor.py -- structural audit of a file-based memory system.

Checks STRUCTURE, not content:
  1. MEMORY.md (the always-loaded index) exists.
  2. No DARK files -- every memory file is reachable from a ROUTING tier: the
     always-loaded MEMORY.md, a Tier-2 INDEX_*.md sub-index, or CATALOG.md. A
     memory nothing routes to is invisible in practice. (Splitting a domain into
     an INDEX_*.md is the correct way to keep MEMORY.md small, so a file linked
     only from a sub-index is reachable, NOT dark.)
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


def discover_memories() -> "list[pathlib.Path]":
    """ALL candidate dirs that hold a MEMORY.md (de-duped, order kept)."""
    found: list[pathlib.Path] = []
    seen: set = set()
    for d in candidate_dirs():
        key = str(d).lower()  # Windows paths are case-insensitive -- de-dupe on it
        if (d / "MEMORY.md").exists() and key not in seen:
            seen.add(key)
            found.append(d)
    return found


def is_memory_file(p: pathlib.Path) -> bool:
    # A real memory entry is <type>_<topic>.md -- not a ROUTING file (the index,
    # a Tier-2 INDEX_*.md sub-index, or CATALOG.md), a template, or the doctor.
    name = p.name
    if name in ("MEMORY.md", "CATALOG.md") or name.startswith("_"):
        return False
    if name.startswith("INDEX_") and name.endswith(".md"):
        return False
    return p.suffix == ".md"


def routing_text(m: pathlib.Path) -> str:
    """Combined text of every routing tier a memory can be reached through:
    the always-loaded MEMORY.md, any Tier-2 INDEX_*.md sub-index, and CATALOG.md.
    A memory linked from ANY of these is reachable -- not dark."""
    parts: list[str] = []
    for name in ("MEMORY.md", "CATALOG.md"):
        p = m / name
        if p.exists():
            parts.append(p.read_text(encoding="utf-8"))
    for p in sorted(m.glob("INDEX_*.md")):
        parts.append(p.read_text(encoding="utf-8"))
    return "\n".join(parts)


def has_frontmatter(text: str) -> bool:
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    if end == -1:
        return False
    fm = text[3:end]
    return all(key in fm for key in ("name:", "description:", "type:"))


def run() -> int:
    found = discover_memories()
    if len(found) > 1:
        # Refuse to guess which to audit -- silently picking one is exactly how an
        # audit ends up "it's fine" against the wrong project's memory.
        print(f"[ambiguous] {len(found)} memory systems found -- refusing to guess:")
        for d in found:
            print(f"  - {d}")
        print("Pin the right one with CLAUDE_MEMORY_HOME (the memory folder) and re-run.")
        print("VERDICT: ISSUES")
        return 1
    if not found:
        print("[none] no memory system found. Searched:")
        for d in candidate_dirs():
            print(f"  - {d}")
        print("VERDICT: ISSUES")
        return 1

    m = found[0]
    print(f"[found] auditing memory at {m}")
    index = m / "MEMORY.md"
    index_text = index.read_text(encoding="utf-8")   # size budget: MEMORY.md only
    reachable_via = routing_text(m)                  # reachability: all routing tiers
    issues: list[str] = []

    for p in sorted(m.glob("*.md")):
        if not is_memory_file(p):
            continue
        # reachable? the slug/filename must appear in ANY routing tier -- MEMORY.md,
        # a Tier-2 INDEX_*.md, or CATALOG.md. (Splitting a domain into a sub-index
        # is the CORRECT way to keep MEMORY.md small; it must not read as "dark".)
        if p.stem not in reachable_via and p.name not in reachable_via:
            issues.append(f"[dark] {p.name} is not linked from MEMORY.md / any INDEX_*.md / CATALOG.md (unreachable)")
        if not has_frontmatter(p.read_text(encoding="utf-8")):
            issues.append(f"[frontmatter] {p.name} missing name/description/type frontmatter")

    line_count = len(index_text.splitlines())
    if line_count > INDEX_LINE_BUDGET:
        issues.append(
            f"[size] MEMORY.md is {line_count} lines (budget {INDEX_LINE_BUDGET}). "
            f"Keep it routing-only: split a domain's rows into a Tier-2 sub-index "
            f"(e.g. INDEX_<domain>.md) and leave ONE router row pointing at it. "
            f"Never trim routing to save space -- that makes memories dark."
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

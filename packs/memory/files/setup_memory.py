#!/usr/bin/env python
"""
setup_memory.py -- install + wire a file-based memory system for Claude.

A tool-agnostic memory core (works with or without gbrain -- they go hand in hand,
but the always-loaded index depends on no tool):

    <claude-home>/memory/
      MEMORY.md              always-loaded resolver INDEX (intent -> file routing)
      reference_canary.md    a seed memory that proves recall actually works
      _template_memory.md    the frontmatter contract for new memories
      memory_doctor.py       a standalone structural audit you keep

Modes (kept simple so pack.yaml checks stay quote-free):

    (no arg) / --install   AUDIT first: if a memory system exists anywhere (global
                           OR project-scoped), don't touch it; only create one if
                           there genuinely isn't any.
    --check                exit 0 if memory exists ANYWHERE known, else 1
    --find                 print where memory lives (or the places searched)
    --check-wire           exit 0 if CLAUDE.md points at the memory index, else 1
    --wire                 make CLAUDE.md point at the memory index (idempotent)

Discovery searches, in order: $CLAUDE_MEMORY_HOME, then <home>/memory (global),
then <home>/projects/<hash>/memory (project-scoped -- where Claude Code usually
keeps it). New systems are created at <home>/memory only if none is found. This
prevents the "location mismatch" trap: reporting memory as missing and building a
duplicate next to a working one. (home = $CLAUDE_HOME or ~/.claude.)

Everything is idempotent: existing files are never overwritten.
"""
import os
import pathlib
import shutil
import sys

WIRE_MARKER = "memory/MEMORY.md"


def base_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def mem_dir() -> pathlib.Path:
    """The DEFAULT location to create a new memory system (global)."""
    return base_dir() / "memory"


def candidate_dirs() -> "list[pathlib.Path]":
    """Where a memory system might already live -- explicit override, global,
    then any project-scoped folder (~/.claude/projects/<hash>/memory)."""
    env = os.environ.get("CLAUDE_MEMORY_HOME")
    if env:
        return [pathlib.Path(env)]
    dirs = [mem_dir()]
    proj = base_dir() / "projects"
    if proj.exists():
        dirs += sorted(proj.glob("*/memory"))
    return dirs


def find_memory() -> "pathlib.Path | None":
    """The first candidate that actually holds a MEMORY.md, else None."""
    for d in candidate_dirs():
        if (d / "MEMORY.md").exists():
            return d
    return None


def claude_md() -> pathlib.Path:
    return base_dir() / "CLAUDE.md"


MEMORY_MD = """# Memory -- your Claude's compounding notes

> **Always-loaded index.** Keep it short (routing only, no prose). Each row points
> an INTENT ("when you're about to...") at the memory file that helps.
>
> **Naming:** `feedback_<topic>` (how to behave) - `reference_<topic>` (where the
> answer lives) - `project_<topic>` (durable project state) - `user_<topic>`
> (facts about you). Every memory file carries frontmatter: `name`, `description`
> (a triggering moment), `type`. See `_template_memory.md`.
>
> **Reflex rule:** when a task fails twice and you find the fix, write the memory
> *now* -- not at the end of the session. A memory nothing can reach is dead
> weight, so always add a RESOLVER row so it's findable.

## RESOLVER -- intent -> memory

| When you're about to... | Consult |
|---|---|
| check whether this memory system is actually being recalled | [reference_canary](reference_canary.md) |

## Files

- `reference_canary.md` -- seed memory that proves recall works
"""

CANARY_MD = """---
name: reference-canary
description: When you're checking whether this memory system is actually recalled in a fresh session.
type: reference
---

The memory canary phrase is **BLUE-OTTER-1793**.

If a fresh Claude session surfaces `BLUE-OTTER-1793` when asked about the memory
canary, recall is working -- the index is being loaded and routed. If it doesn't,
memory is present on disk but *functionally dark*: the structure exists but isn't
reaching real conversations.
"""

TEMPLATE_MD = """---
name: <kebab-slug>
description: <the moment this should come to mind -- "when you're about to...">
type: feedback | reference | project | user
---

<The fact, in one place. For feedback/project, add:>
**Why:** <why this matters>
**How to apply:** <what to do next time>

<Link related memories with [[other-slug]].>
"""

WIRE_BLOCK = """
## Memory (always consult)

At session start, consult `memory/MEMORY.md` -- the always-loaded index that routes
intents to the notes that help. When a lesson would save time next session, write a
memory (naming: `feedback_` / `reference_` / `project_` / `user_`; see
`memory/_template_memory.md`). A memory nothing can reach is dead weight -- always
add a RESOLVER row so it's findable.
"""


def install() -> int:
    # Discover first -- never create a duplicate alongside an existing memory
    # system (e.g. a project-scoped one). This is the "audit + find where it is,
    # don't blindly make a new one" rule.
    existing = find_memory()
    if existing is not None:
        print(f"found existing memory at {existing}")
        print("not creating a duplicate. Audit it with:")
        print("  python packs/memory/files/memory_doctor.py")
        return 0

    m = mem_dir()
    m.mkdir(parents=True, exist_ok=True)
    here = pathlib.Path(__file__).resolve().parent
    wrote: list[str] = []

    for name, content in (
        ("MEMORY.md", MEMORY_MD),
        ("reference_canary.md", CANARY_MD),
        ("_template_memory.md", TEMPLATE_MD),
    ):
        p = m / name
        if not p.exists():
            p.write_text(content, encoding="utf-8")
            wrote.append(name)

    # Ship the standalone doctor into the memory folder so it survives the pack.
    doc_src = here / "memory_doctor.py"
    doc_dst = m / "memory_doctor.py"
    if doc_src.exists() and not doc_dst.exists():
        shutil.copyfile(doc_src, doc_dst)
        wrote.append("memory_doctor.py")

    print(f"memory home: {m}")
    print("created: " + (", ".join(wrote) if wrote else "(nothing -- already set up)"))
    return 0


def check() -> int:
    # Discovery-aware: memory found ANYWHERE known (global or project-scoped)
    # counts as present. Prevents a false "missing" that would create a duplicate.
    return 0 if find_memory() is not None else 1


def find() -> int:
    m = find_memory()
    if m is not None:
        print(f"memory found at: {m}")
        return 0
    print("no memory system found. Searched:")
    for d in candidate_dirs():
        print(f"  - {d}")
    return 1


def check_wire() -> int:
    p = claude_md()
    return 0 if (p.exists() and WIRE_MARKER in p.read_text(encoding="utf-8")) else 1


def wire() -> int:
    p = claude_md()
    p.parent.mkdir(parents=True, exist_ok=True)
    text = p.read_text(encoding="utf-8") if p.exists() else "# Claude -- your constitution\n"
    if WIRE_MARKER in text:
        print("already wired")
        return 0
    p.write_text(text.rstrip() + "\n" + WIRE_BLOCK, encoding="utf-8")
    print(f"wired memory into {p}")
    return 0


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "--install"
    if mode == "--install":
        return install()
    if mode == "--check":
        return check()
    if mode == "--find":
        return find()
    if mode == "--check-wire":
        return check_wire()
    if mode == "--wire":
        return wire()
    print(f"unknown mode {mode!r}; expected --install/--check/--find/--check-wire/--wire")
    return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main(sys.argv))

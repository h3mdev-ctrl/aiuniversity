#!/usr/bin/env python
"""
setup_identity.py -- who you are + how Claude should talk to you.

Layer 0 of the foundation. Writes three context files a newcomer's Claude reads
before speaking to them:

    <claude-home>/context/
      me.md                 who I am + how I want you to talk to me
      work.md               what I'm building + my environment
      current_priorities.md focus this week / month + timezone

Plus a user_profile memory (with a canary phrase for a fresh-session recall test)
and a "who you're speaking to" block wired into CLAUDE.md.

Modes:
    --interactive          prompt on stdin, then write (a solo user runs this)
    --write                read a JSON payload from stdin, then write (Claude
                           conducts the interview in teach mode and pipes it)
    --check                exit 0 if context/me.md exists, else 1
    --link-memory          drop user_profile into memory + add a resolver row
    --check-memory         exit 0 if memory references user_profile, else 1
    --wire                 append the identity block to CLAUDE.md (idempotent)
    --check-wire           exit 0 if CLAUDE.md points at context/me.md, else 1

Homes: base = $CLAUDE_HOME or ~/.claude ; context = <base>/context ; memory =
<base>/memory ; CLAUDE.md = <base>/CLAUDE.md.

The JSON payload (for --write) uses these keys (all strings; priorities is a list):
    name, role, technical_level, communication_style, building, priorities[],
    environment, timezone

Everything is idempotent -- writing again with new answers overwrites the
context files but never touches your memory or CLAUDE.md wiring beyond adding
the pointer once.
"""
import json
import os
import pathlib
import sys

IDENTITY_CANARY = "PURPLE-KANGAROO-9271"
WIRE_MARKER = "context/me.md"


def base_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def ctx_dir() -> pathlib.Path:
    return base_dir() / "context"


def mem_dir() -> pathlib.Path:
    return base_dir() / "memory"


def claude_md() -> pathlib.Path:
    return base_dir() / "CLAUDE.md"


ME_MD = """# Me -- {name}

**Role:** {role}

**Technical level:** {technical_level}

**How to talk to me:** {communication_style}
"""

WORK_MD = """# Work

**What I'm building:** {building}

**Environment:** {environment}
"""

PRIORITIES_MD = """# Current priorities

{priorities_list}

**Timezone:** {timezone}
"""

USER_PROFILE_MD = """---
name: user-profile
description: When you're calibrating tone, technical level, or how to communicate -- my profile is here (see context/me.md for the details).
type: user
---

I'm the person Claude is talking to. My profile lives at `context/me.md` (identity),
`context/work.md` (what I'm building), and `context/current_priorities.md`
(this month's focus).

**When speaking to me, match the communication style in `context/me.md`.**

Identity canary phrase: **{canary}** -- if a fresh Claude session surfaces this
when asked who you're speaking to, my profile is being recalled correctly.
""".format(canary=IDENTITY_CANARY)

MEMORY_IDENTITY_BLOCK = """
### Identity

| When you're about to... | Consult |
|---|---|
| calibrate tone or technical level for the person you're talking to | [user_profile](user_profile.md) |
"""

CLAUDE_WIRE_BLOCK = """
## Who you're speaking to

At session start, consult `context/me.md` (who I am + how to talk to me),
`context/work.md` (what I'm building + my environment), and
`context/current_priorities.md` (this month's focus). Match the communication
style you find there.
"""


def _clean(s: str) -> str:
    return (s or "").strip()


def write_from_payload(p: dict) -> int:
    name = _clean(p.get("name", ""))
    if not name:
        print("name is required")
        return 2
    d = ctx_dir()
    d.mkdir(parents=True, exist_ok=True)
    fields = {
        "name": name,
        "role": _clean(p.get("role", "(not set)")),
        "technical_level": _clean(p.get("technical_level", "(not set)")),
        "communication_style": _clean(p.get("communication_style", "(not set)")),
        "building": _clean(p.get("building", "(not set)")),
        "environment": _clean(p.get("environment", "(not set)")),
        "timezone": _clean(p.get("timezone", "(not set)")),
    }
    priorities = p.get("priorities") or []
    if not isinstance(priorities, list):
        priorities = [str(priorities)]
    priorities_list = "\n".join(f"- {str(x).strip()}" for x in priorities if str(x).strip()) or "- (add later)"

    (d / "me.md").write_text(ME_MD.format(**fields), encoding="utf-8")
    (d / "work.md").write_text(WORK_MD.format(**fields), encoding="utf-8")
    (d / "current_priorities.md").write_text(
        PRIORITIES_MD.format(priorities_list=priorities_list, timezone=fields["timezone"]),
        encoding="utf-8",
    )
    print(f"wrote identity to {d}")
    return 0


def interactive() -> int:
    print("A few quick questions -- this shapes how Claude talks to you.\n")
    p = {
        "name": input("Your name? ").strip(),
        "role": input("Your role or craft in one line? ").strip(),
        "technical_level": input(
            "Technical level (e.g. 'not a developer, explain plainly' / 'hobbyist' / 'pro engineer')? "
        ).strip(),
        "communication_style": input(
            "How should I talk to you? (e.g. 'concrete, no jargon, one recommendation not menus') "
        ).strip(),
        "building": input("What are you building right now, in one sentence? ").strip(),
        "priorities": [
            x.strip()
            for x in input("Top 2-3 priorities this month (separate with ; )? ").split(";")
            if x.strip()
        ],
        "environment": input("OS + shell? (e.g. 'Windows 11 + PowerShell') ").strip(),
        "timezone": input("Timezone? (e.g. 'Australia/Sydney') ").strip(),
    }
    return write_from_payload(p)


def check() -> int:
    return 0 if (ctx_dir() / "me.md").exists() else 1


def link_memory() -> int:
    mem = mem_dir()
    index = mem / "MEMORY.md"
    if not index.exists():
        print("no memory system found -- run the memory pack first (packs/memory)")
        return 1
    (mem / "user_profile.md").write_text(USER_PROFILE_MD, encoding="utf-8")
    text = index.read_text(encoding="utf-8")
    if "user_profile" not in text:
        index.write_text(text.rstrip() + "\n" + MEMORY_IDENTITY_BLOCK, encoding="utf-8")
    print(f"linked identity into {index}")
    return 0


def check_memory() -> int:
    index = mem_dir() / "MEMORY.md"
    ok = (
        index.exists()
        and "user_profile" in index.read_text(encoding="utf-8")
        and (mem_dir() / "user_profile.md").exists()
    )
    return 0 if ok else 1


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
    p.write_text(text.rstrip() + "\n" + CLAUDE_WIRE_BLOCK, encoding="utf-8")
    print(f"wired identity into {p}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: setup_identity.py --interactive | --write | --check | "
              "--link-memory | --check-memory | --wire | --check-wire")
        return 2
    mode = argv[1]
    if mode == "--interactive":
        return interactive()
    if mode == "--write":
        try:
            payload = json.loads(sys.stdin.read())
        except json.JSONDecodeError as exc:
            print(f"--write expects JSON on stdin: {exc}")
            return 2
        return write_from_payload(payload)
    if mode == "--check":
        return check()
    if mode == "--link-memory":
        return link_memory()
    if mode == "--check-memory":
        return check_memory()
    if mode == "--wire":
        return wire()
    if mode == "--check-wire":
        return check_wire()
    print(f"unknown mode {mode!r}")
    return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main(sys.argv))

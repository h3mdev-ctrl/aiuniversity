#!/usr/bin/env python
"""setup_constitution.py -- seed the load-bearing sections of your constitution.

A CLAUDE.md that only lists your OS + a few rules is a start, but the two sections
that most change how Claude behaves are usually missing:

  1. an OPERATING PRINCIPLE -- the stance you want Claude to take every turn
     (verify before executing, learn from proven setups, be token-efficient); and
  2. SKILL ROUTING -- "when a request matches a skill, invoke it FIRST" + a trigger
     table, so Claude reaches for your proven tools instead of improvising.

This writes both into your global CLAUDE.md between markers (idempotent; coexists
with everything else you have). Edit the trigger table to your own skills after.

Modes:
    --install   (default) write/update the block in CLAUDE.md
    --check     exit 0 if the block is present, else 1

Home: $CLAUDE_HOME or ~/.claude ; CLAUDE.md lives at <home>/CLAUDE.md.
"""
import os
import pathlib
import sys

START = "<!-- constitution-core:start -->"
END = "<!-- constitution-core:end -->"

BLOCK = f"""{START}
## Operating principle

Be self-evolving, smarter in execution, and efficient in token use. That means:
**verify and check and plan before executing** -- don't guess when you can confirm.
And the best way to learn is **from the shoulders of giants**: find someone who has
already done this well, copy their proven path, and shortcut your way to success
instead of reinventing it. Prefer a known-good approach over a clever new one.

**Present decisions -- don't pre-make them.** When something looks hard, or overlaps
what the user already has, do NOT unilaterally defer it, drop it, or tell them to
"skip" it to reduce your own risk. Name the friction concretely, scope what it
actually is, and put "do it now" next to "defer / keep what you have" with the real
tradeoff -- then let the USER choose. They can handle the complexity; pre-filtering
their options to keep things simple patronises them. If your framing only supports
one answer, you gatekept -- give them the tradeoff and the decision.

## Skill routing

When a request matches an available skill, invoke it via the Skill tool **FIRST** --
do not answer from scratch. Skills encode a proven path; improvising throws that
away. When in doubt, invoke the skill. The rows below are EXAMPLES using skills that
ship with Claude Code -- replace / add rows for the skills you actually install:

| Trigger | Skill |
|---|---|
| Set up a repo / write its CLAUDE.md | `init` |
| Review a PR or a diff | `review` |
| Security pass on the pending changes | `security-review` |
| A task you keep re-explaining to Claude | (write a skill for it, then add a row here) |

(If you don't have a skill for a trigger yet, that's a gap worth filling -- a skill
you'll reach for more than twice is worth writing.)

## Your brain (gbrain), if set up

gbrain is your ONE hub -- work, clients/network, side projects, hobbies, and the
people you know all feed the same brain (see the gbrain pack's `gbrain_hub_model.md`).
Search it before researching; capture durable ideas/entities as you go. It is not a
per-area notes app; it's the thing that connects your areas.
{END}
"""


def base_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def claude_md() -> pathlib.Path:
    return base_dir() / "CLAUDE.md"


def check() -> int:
    p = claude_md()
    return 0 if (p.exists() and START in p.read_text(encoding="utf-8")) else 1


def install() -> int:
    p = claude_md()
    p.parent.mkdir(parents=True, exist_ok=True)
    text = p.read_text(encoding="utf-8") if p.exists() else "# Claude -- your constitution\n"
    if START in text and END in text:
        pre = text[: text.index(START)]
        post = text[text.index(END) + len(END):]
        p.write_text(pre.rstrip() + "\n\n" + BLOCK.rstrip() + "\n" + post, encoding="utf-8")
        print(f"updated constitution core in {p}")
        return 0
    p.write_text(text.rstrip() + "\n\n" + BLOCK, encoding="utf-8")
    print(f"installed constitution core into {p}")
    return 0


def main(argv: "list[str]") -> int:
    mode = argv[1] if len(argv) > 1 else "--install"
    if mode == "--install":
        return install()
    if mode == "--check":
        return check()
    print(f"unknown mode {mode!r}; expected --install/--check")
    return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main(sys.argv))

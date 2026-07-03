#!/usr/bin/env python
"""setup_gbrain_usage.py -- make gbrain HABITUAL, not just installed.

Getting gbrain live (the other gbrain steps) is necessary but not sufficient: a
brain nobody is told to use stays empty. This writes a *usage discipline* into the
recipient's constitution (CLAUDE.md) so Claude uses gbrain automatically --
capturing ideas/entities as they come up, searching the brain before researching,
and backlinking.

It writes the CAPTURE + research-first half. If gstack's `/setup-gbrain` already
wrote a "GBrain Search Guidance" block (the search-vs-grep preference), the two
coexist -- this block is fenced by its own markers and is idempotent/updatable.

Modes:
    --install   (default) write/update the block in CLAUDE.md (idempotent)
    --check     exit 0 if the block is present, else 1

Home: $CLAUDE_HOME or ~/.claude ; CLAUDE.md lives at <home>/CLAUDE.md.
"""
import os
import pathlib
import sys

START = "<!-- gbrain-usage-discipline:start -->"
END = "<!-- gbrain-usage-discipline:end -->"

BLOCK = f"""{START}
## GBrain -- use your knowledge brain automatically

GBrain is wired in as an MCP server. Use it without being asked -- a brain only
compounds if you write to it and read from it as a habit, not on request.

**Capture as you go** (every message; run in parallel, never block your main reply):
- An original idea, thesis, or framework the user expresses -> save it via `put_page`
  under `ideas/<slug>` or `originals/<slug>`.
- A person, company, or tool mentioned -> create or update its page
  (`people/<name>`, `companies/<slug>`, `concepts/<slug>`).

**Research the brain first:**
- Before researching any person, company, or topic, `search` + `query` the brain.
  Fill gaps with external sources only if it comes up empty.
- For "what do we know about X", use `query` (hybrid) over `search` (keyword only);
  `get_page` the full page when you know the slug.

**When you write to the brain:**
- Attribute sources inline: `[Source: <who>, <YYYY-MM-DD>]`.
- Back-link every entity mention -- if a person/company already has a page, link it.
- Prefer a few well-linked pages over many orphans.

(This is the capture + research-first half. A separate "GBrain Search Guidance"
block, if present, covers the search-vs-grep preference -- keep both.)
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
        # replace the existing block in place (idempotent update)
        pre = text[: text.index(START)]
        post = text[text.index(END) + len(END):]
        new = pre.rstrip() + "\n\n" + BLOCK.rstrip() + "\n" + post
        p.write_text(new, encoding="utf-8")
        print(f"updated gbrain usage discipline in {p}")
        return 0
    p.write_text(text.rstrip() + "\n\n" + BLOCK, encoding="utf-8")
    print(f"installed gbrain usage discipline into {p}")
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

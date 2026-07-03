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

Two cadences -- pick by how much per-message cost you'll trade for capture:
    lean  (default) -- search-first before researching; capture only what's clearly
                       worth keeping (judgment, NOT every message). Cheap; no per-turn tax.
    eager (--eager) -- proactively scan EVERY message for ideas/entities and save them.
                       Maximal compounding, higher token/latency cost. For power users.

Note: registering gbrain as an MCP already makes its tools AVAILABLE every session
(a fixed context cost). This block governs how aggressively Claude *acts* on that --
the per-message tax lives here, not in mere availability.

Modes:
    --install [--eager]   write/update the block in CLAUDE.md (idempotent; lean default)
    --check               exit 0 if the block is present (either cadence), else 1

Home: $CLAUDE_HOME or ~/.claude ; CLAUDE.md lives at <home>/CLAUDE.md.
"""
import os
import pathlib
import sys

START = "<!-- gbrain-usage-discipline:start -->"
END = "<!-- gbrain-usage-discipline:end -->"

_SHARED_TAIL = """**Research the brain first** (cheap, high-value -- keep this either way):
- Before researching a person, company, or topic, `search` + `query` the brain.
  Fill gaps with external sources only if it comes up empty.
- For "what do we know about X", use `query` (hybrid) over `search` (keyword only);
  `get_page` the full page when you know the slug.

**When you write to the brain:**
- Attribute sources inline: `[Source: <who>, <YYYY-MM-DD>]`.
- Back-link every entity mention -- if a person/company already has a page, link it.
- Prefer a few well-linked pages over many orphans.

(A separate "GBrain Search Guidance" block, if present, covers the search-vs-grep
preference -- keep both.)"""

LEAN_BLOCK = f"""{START}
<!-- cadence: lean -->
## GBrain -- use your knowledge brain where it earns its keep

GBrain is available as an MCP server. Use it where it pays off -- NOT on every turn.
Availability is free; ACTIONS cost tokens + latency, so spend them on signal.

**Capture what's clearly worth keeping** (judgment, not every message):
- A genuinely novel idea, thesis, or framework the user expresses, or a decision
  worth remembering -> `put_page` (`ideas/<slug>`, `originals/<slug>`, `decisions/<slug>`).
- A new person/company/tool that will recur -> a short page (`people/<name>`,
  `companies/<slug>`, `concepts/<slug>`).
- Do NOT capture routine chatter or narrate every save -- a brain of noise is worse
  than a small brain.

{_SHARED_TAIL}

(Want maximal capture on EVERY message -- higher token cost, for power users?
Re-run `setup_gbrain_usage.py --install --eager`.)
{END}
"""

EAGER_BLOCK = f"""{START}
<!-- cadence: eager -->
## GBrain -- use your knowledge brain automatically (eager)

GBrain is wired in as an MCP server. Use it without being asked -- a brain compounds
only if you write to and read from it as a habit. This is the EAGER cadence: maximal
capture, higher per-message token/latency cost (you chose this).

**Capture as you go** (every message; run in parallel, never block your main reply):
- Any original idea, thesis, or framework the user expresses -> save via `put_page`
  under `ideas/<slug>` or `originals/<slug>`.
- Any person, company, or tool mentioned -> create/update its page (`people/<name>`,
  `companies/<slug>`, `concepts/<slug>`).

{_SHARED_TAIL}

(Too much per-turn cost? Switch to the lean cadence: `setup_gbrain_usage.py --install`.)
{END}
"""


def base_dir() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CLAUDE_HOME") or (pathlib.Path.home() / ".claude"))


def claude_md() -> pathlib.Path:
    return base_dir() / "CLAUDE.md"


def check() -> int:
    p = claude_md()
    return 0 if (p.exists() and START in p.read_text(encoding="utf-8")) else 1


def install(eager: bool = False) -> int:
    block = EAGER_BLOCK if eager else LEAN_BLOCK
    cadence = "eager" if eager else "lean"
    p = claude_md()
    p.parent.mkdir(parents=True, exist_ok=True)
    text = p.read_text(encoding="utf-8") if p.exists() else "# Claude -- your constitution\n"
    if START in text and END in text:
        # replace the existing block in place (idempotent; also flips cadence)
        pre = text[: text.index(START)]
        post = text[text.index(END) + len(END):]
        new = pre.rstrip() + "\n\n" + block.rstrip() + "\n" + post
        p.write_text(new, encoding="utf-8")
        print(f"updated gbrain usage discipline ({cadence}) in {p}")
        return 0
    p.write_text(text.rstrip() + "\n\n" + block, encoding="utf-8")
    print(f"installed gbrain usage discipline ({cadence}) into {p}")
    return 0


def main(argv: "list[str]") -> int:
    args = argv[1:]
    mode = args[0] if args else "--install"
    if mode == "--install":
        return install(eager="--eager" in args)
    if mode == "--check":
        return check()
    print(f"unknown mode {mode!r}; expected --install [--eager] / --check")
    return 2


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    raise SystemExit(main(sys.argv))

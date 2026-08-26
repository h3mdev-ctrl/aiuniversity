#!/usr/bin/env python3
"""
SOCKET: salvage           EVENT: PreCompact
Hermes equivalent: MemoryProvider.on_pre_compress(messages) -> str

Distil the messages compaction is about to DISCARD, before they are gone.

THE GAP THIS CLOSES
-------------------
Most setups have a PostCompact hook that says "re-read CLAUDE.md". That restores
the STATIC rules -- and nothing about the session. The measurements you took, the
approach you rejected, the number you corrected: all of that was in the discarded
window, and a summariser optimising for brevity drops exactly the specifics that
were expensive to obtain. Salvage runs BEFORE the discard and keeps them.

TWO PATHS ON PURPOSE
--------------------
It is not documented whether a PreCompact hook's stdout reaches the summariser.
So this writes a carry FILE (which does not depend on that answer) AND prints
additionalContext. Whichever path the harness honours, the content survives.
When a contract is unverified, satisfy both branches rather than guessing.

CONTRACT
  stdin : JSON {session_id, transcript_path, trigger}
  stdout: JSON {"hookSpecificOutput": {...}}
  exit  : ALWAYS 0. Exit 2 would BLOCK compaction -- never wedge a session
          because note-taking failed.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import time

MAX_ITEMS = 12
MAX_CHARS = 5000
MAX_LINES_PER_MSG = 400     # see LATENCY below
CARRY_DIR = pathlib.Path.home() / ".claude" / "state" / "compact_carry"

# What is worth keeping: a number, or a verdict.
KEEP_RE = re.compile(
    r"(\d+\s*(?:ms|s\b|%|MB|rows?|files?)|\b\d+/\d+\b|\b\d+\.\d+\b|"
    r"\b(measured|verified|confirmed|rejected|root cause|turns out|failed)\b)", re.I)

# HARNESS NOISE -- the one that will bite you
# ------------------------------------------
# After an auto-compaction, the continuation summary is stored as a REAL
# type:"user" message. It is not flagged as meta, so nothing upstream filters
# it, and it CONTAINS the words "wrong", "actually", "hold on" quoted from the
# conversation it summarises. Every naive filter treats it as a genuine user
# instruction. One real transcript carried nine of them.
HARNESS_RE = re.compile(
    r"^\s*(\[?(Request interrupted|Caveat|API Error)|<[a-z-]+>|"
    r"This session is being continued from|Analysis:|Summary:)", re.I)


def text_of(msg: dict) -> str:
    c = (msg or {}).get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "\n".join(b.get("text", "") for b in c
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def build_digest(transcript: str, trigger: str) -> str:
    p = pathlib.Path(transcript)
    if not p.is_file():
        return ""
    asks: list[str] = []
    facts: list[str] = []
    try:
        with p.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                if o.get("type") not in ("user", "assistant") or o.get("isMeta"):
                    continue
                if o.get("isSidechain"):        # subagent chatter, not this thread
                    continue
                txt = text_of(o.get("message") or {}).strip()
                if not txt or HARNESS_RE.match(txt):
                    continue
                if o["type"] == "user":
                    asks.append(re.sub(r"\s+", " ", txt)[:300])
                elif len(facts) < MAX_ITEMS * 6:
                    # LATENCY: cap the lines scanned per message. This runs while
                    # the user waits, and ONE pasted build log made an unbounded
                    # per-line regex sweep take 3.1s. You only keep MAX_ITEMS
                    # anyway, so the unbounded sweep bought nothing.
                    for para in txt.split("\n")[:MAX_LINES_PER_MSG]:
                        para = para.strip(" -*#|")
                        if 25 <= len(para) <= 260 and KEEP_RE.search(para):
                            facts.append(re.sub(r"\s+", " ", para))
    except OSError:
        return ""

    if not (asks or facts):
        return ""

    def tail(xs):
        seen, out = set(), []
        for x in reversed(xs):
            k = x[:80].lower()
            if k not in seen:
                seen.add(k)
                out.append(x)
            if len(out) >= MAX_ITEMS:
                break
        return list(reversed(out))

    lines = [f"# CARRY-FORWARD from before compaction ({trigger}, "
             f"{time.strftime('%Y-%m-%d %H:%M')})", "",
             "The messages this came from are gone. These are established facts of",
             "THIS session, not new suggestions.", ""]
    if asks:
        lines += ["## What the user asked for"] + \
                 [f"  {i+1}. {a}" for i, a in enumerate(tail(asks))] + [""]
    if facts:
        lines += ["## Measurements and verdicts established"] + \
                 [f"  - {f}" for f in tail(facts)] + [""]
    out = "\n".join(lines)
    return out[:MAX_CHARS]


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        digest = build_digest(str(data.get("transcript_path") or ""),
                              str(data.get("trigger") or "auto"))
        if not digest:
            return 0

        # Path 1: durable file, keyed by SESSION. Never write to a shared
        # "latest.md" -- several sessions compact at once and the restore hook
        # would hand one session's notes to another.
        sid = re.sub(r"[^A-Za-z0-9_-]", "_", str(data.get("session_id") or "s"))[:64]
        try:
            CARRY_DIR.mkdir(parents=True, exist_ok=True)
            (CARRY_DIR / f"{sid}.md").write_text(digest, encoding="utf-8")
            for old in sorted(CARRY_DIR.glob("*.md"),
                              key=lambda f: f.stat().st_mtime)[:-40]:
                old.unlink(missing_ok=True)
        except Exception:
            pass

        # Path 2: in case stdout does reach the summariser.
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreCompact", "additionalContext": digest}}))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())

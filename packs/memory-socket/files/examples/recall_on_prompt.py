#!/usr/bin/env python3
"""
SOCKET: recall            EVENT: UserPromptSubmit
Hermes equivalent: MemoryProvider.prefetch / queue_prefetch

Retrieve the memories relevant to THIS prompt and inject them before the model
answers. This is the socket that turns a folder of notes into recall.

A teaching implementation: FTS5 + BM25, the same first stage Hermes' FactRetriever
uses. Deliberately no embeddings -- no API key, no network, ~100ms. Add semantic
rerank later if you need it; measure first, because on a small corpus lexical
search plus a relevance floor gets you most of the way.

CONTRACT
  stdin : JSON {prompt, cwd, session_id}
  stdout: JSON {"hookSpecificOutput": {"hookEventName", "additionalContext"}}
  exit  : ALWAYS 0. A memory system must never block the user's turn.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sqlite3
import sys

MAX_HITS = 3
MIN_WORDS = 4         # below this a prompt is chit-chat ("ok", "thanks")

# TWO GATES, AND WHY NEITHER IS ENOUGH ALONE
# ------------------------------------------
# 1. WHY A FLOOR AT ALL, NOT JUST "TOP 3"
#    The obvious design ranks every memory and keeps the best 3. It is wrong,
#    and the failure is invisible: BM25 is normalised WITHIN a result set, so
#    the top 3 of a bad match look exactly like the top 3 of a good one.
#    Measured on a real corpus, positives scored 0.186-0.399 and negatives
#    0.277-0.385 -- fully overlapping. A relative rank is a fine RANKER and a
#    useless CLASSIFIER. Something must decide "nothing here is relevant".
#
# 2. WHY THE FLOOR ALONE IS FRAGILE
#    BM25 magnitude scales with corpus size and query length, so a number tuned
#    on someone else's corpus is meaningless on yours. This example originally
#    shipped MIN_BM25 = 7.0, lifted from a retriever whose score was combined
#    and differently scaled. On a 4-document test corpus the CORRECT hit scored
#    3.09 -- so the hook was silent by construction and passed every
#    registration audit. That is the exact anti-pattern this pack warns about,
#    found only by running it with a positive control.
#
# So: keep a floor, but CALIBRATE it (see calibrate() below), and add a second
# gate that does NOT scale with the corpus -- the fraction of the query's terms
# that appear in the memory's own slug + description. Overlap is absolute.
MIN_BM25 = 1.0        # CALIBRATE THIS against your corpus -- see calibrate()
MIN_OVERLAP = 0.15    # corpus-independent: share of query terms the doc names


def memory_dir(cwd: str) -> pathlib.Path | None:
    """Resolve the memory folder for THIS project.

    Per-project resolution is not a nicety. If your store is one global file,
    a session in project B will be served project A's conclusions under a
    banner saying "treat as authoritative". Always key the store by project.
    """
    if os.environ.get("CLAUDE_MEMORY_HOME"):
        return pathlib.Path(os.environ["CLAUDE_MEMORY_HOME"])
    for base in (pathlib.Path(cwd), *pathlib.Path(cwd).parents):
        cand = base / "memory"
        if (cand / "MEMORY.md").is_file():
            return cand
    return None


def build_index(memdir: pathlib.Path) -> sqlite3.Connection:
    """In-memory FTS5 index over the memory folder.

    Rebuilt per call for clarity. Cache it once you have hundreds of files --
    but if you cache, key the cache on the DIRECTORY and check that key BEFORE
    any freshness short-circuit. A TTL cache that returns early without
    re-checking which project it was built for leaks memories across projects.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE VIRTUAL TABLE m USING fts5(slug, description, body)")
    for f in sorted(memdir.glob("*.md")):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        desc = ""
        if match := re.search(r"^description:\s*(.+)$", text, re.M):
            desc = match.group(1).strip().strip('"')
        conn.execute("INSERT INTO m VALUES (?,?,?)", (f.stem, desc, text[:20000]))
    return conn


def sanitize(prompt: str) -> str:
    """Turn a natural-language prompt into an FTS5 query.

    FTS5 AND-joins bare terms by default, so passing a sentence through means
    EVERY word must appear -- which kills recall on natural language. OR-join
    instead, and quote each term so punctuation cannot become syntax.
    """
    terms = [t for t in re.findall(r"[A-Za-z0-9_]{3,}", prompt.lower())][:12]
    return " OR ".join(f'"{t}"' for t in terms)


def terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]{3,}", text.lower()))


def overlap(prompt: str, row: sqlite3.Row) -> float:
    """Share of the prompt's terms named by this memory's slug + description.

    Corpus-independent by construction: it does not move when you add files, so
    unlike the BM25 floor it does not need recalibrating.
    """
    q = terms(prompt)
    if not q:
        return 0.0
    doc = terms(f"{row['slug']} {row['description']}")
    return len(q & doc) / len(q)


def search(conn: sqlite3.Connection, prompt: str) -> list[sqlite3.Row]:
    q = sanitize(prompt)
    if not q:
        return []
    try:
        rows = conn.execute(
            # bm25() returns a NEGATIVE score where lower is better, so negate
            # it to get "bigger is better" and compare against the floor.
            "SELECT slug, description, -bm25(m) AS score FROM m "
            "WHERE m MATCH ? ORDER BY score DESC LIMIT ?",
            (q, MAX_HITS)).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r for r in rows
            if r["score"] >= MIN_BM25 and overlap(prompt, r) >= MIN_OVERLAP]


def calibrate(memdir: pathlib.Path, positive: str, negative: str) -> None:
    """Print the scores your OWN corpus gives a should-hit and a should-miss.

    Run this before trusting MIN_BM25. Pick a prompt you know a memory answers
    and one you know nothing answers; set the floor between the two. Without
    both controls you cannot tell a correctly-silent hook from a broken one --
    they look identical.

        python recall_on_prompt.py --calibrate <memory_dir> "<hit>" "<miss>"
    """
    conn = build_index(memdir)
    for label, prompt in (("SHOULD HIT ", positive), ("SHOULD MISS", negative)):
        q = sanitize(prompt)
        rows = conn.execute(
            "SELECT slug, description, -bm25(m) AS score FROM m "
            "WHERE m MATCH ? ORDER BY score DESC LIMIT 3", (q,)).fetchall() if q else []
        print(f"\n{label}: {prompt!r}")
        if not rows:
            print("   (no FTS matches at all)")
        for r in rows:
            print(f"   {r['slug'][:34]:34s} bm25={r['score']:6.3f} "
                  f"overlap={overlap(prompt, r):.2f}")
    print(f"\ncurrent gates: MIN_BM25={MIN_BM25}  MIN_OVERLAP={MIN_OVERLAP}")
    print("Set MIN_BM25 between the two blocks above. If they overlap, BM25 alone "
          "cannot separate them -- lean on MIN_OVERLAP.")


def main() -> int:
    if "--calibrate" in sys.argv:
        i = sys.argv.index("--calibrate")
        rest = sys.argv[i + 1:]
        if len(rest) < 3:
            print('usage: --calibrate <memory_dir> "<should-hit>" "<should-miss>"')
            return 2
        calibrate(pathlib.Path(rest[0]), rest[1], rest[2])
        return 0
    try:
        data = json.loads(sys.stdin.read() or "{}")
        prompt = str(data.get("prompt") or "")
        cwd = str(data.get("cwd") or os.getcwd())

        # Cheap prompts get nothing. Firing retrieval on "ok" or "thanks" costs
        # latency and teaches the user the block is noise.
        if len(prompt.split()) < MIN_WORDS:
            return 0

        memdir = memory_dir(cwd)
        if not memdir:
            return 0
        hits = search(build_index(memdir), prompt)
        if not hits:
            return 0

        lines = ["<system-reminder>", "Relevant project memory for this request:", ""]
        for h in hits:
            lines.append(f"  - [{h['slug']}]({h['slug']}.md)")
            if h["description"]:
                lines.append(f"    {h['description'][:200]}")
        lines.append("</system-reminder>")

        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(lines),
        }}))
    except Exception:
        # Swallow everything. A crash here would surface as a broken prompt.
        return 0
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())

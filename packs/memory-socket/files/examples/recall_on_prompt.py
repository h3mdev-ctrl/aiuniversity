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

MAX_HITS = 2          # swept on real prompts: 2 beat 3 on precision
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


# ATOM KINDS and their weight as evidence of intent. A hand-written resolver
# row ("When you're about to X -> read Y") is the strongest signal a memory
# corpus contains. A slug is 3-5 words of filename and exists only as a
# last-resort handle -- and because BM25 favours SHORT documents, an unweighted
# slug wins on a single common term. Measured: "ship this and deploy it" ranked
# a `cloudflare_worker_deploy` slug (one term: "deploy") above the shipping
# index's "Shipping / PR / deploy / land" resolver row.
ATOM_WEIGHT = {"resolver": 1.00, "description": 0.95, "slug": 0.75}
MIN_ATOM_CHARS = 12
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+\.md)\)")


def _resolver_atoms(index_md: str) -> list[tuple[str, str]]:
    """-> [(target.md, ONE intent)] from a resolver table. Never merged.

    Merging every intent for a target into one string is the mistake that makes
    a corpus unsearchable -- see build_index below.
    """
    out = []
    for line in index_md.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        links = _LINK_RE.findall(line)
        if not links:
            continue
        intent = re.sub(r"\s+", " ", _LINK_RE.sub(" ", line).replace("|", " ")).strip()
        if len(intent) < MIN_ATOM_CHARS:
            continue
        for _disp, target in links:
            out.append((target, intent))
    return out


def build_index(memdir: pathlib.Path) -> sqlite3.Connection:
    """FTS5 index of ATOMS -- one row per statement, NOT one row per file.

    THIS IS THE MOST IMPORTANT DECISION IN THE WHOLE SOCKET.

    The obvious design indexes each memory file as one document. It produces a
    system that looks correct and retrieves badly, and the failure is invisible
    without a log. Measured on a real 607-file corpus over 25 real prompts:
    document-level indexing gave **20% precision**. Every memory matched every
    prompt weakly, so scores collapsed into a narrow band (0.27-0.31) where the
    HIGHEST-scoring results were noise and genuinely useful ones scored lower.
    No threshold could separate them, because there was nothing to separate.

    The cause is mechanical: BM25 over a 200-line document with hundreds of
    terms will match almost any query a little. Over a one-sentence atom, a
    match means something.

    hermes-agent gets this right by construction -- `facts.content` is one
    statement per row. Applied to a markdown corpus, the atoms are:
      resolver     each "when you're about to X" row the file appears in
      description  its frontmatter description
      slug         its filename words

    Same corpus, same scoring maths, atoms instead of documents: precision went
    20% -> 75% with recall unchanged and 24% fewer tokens injected.

    NOTE WHAT IS **NOT** INDEXED: the body. The body is what you SHOW the user;
    it is not what you SEARCH. Folding a few hundred characters of body text
    into the searchable content is exactly what flattened the scores.

    Rebuilt per call for clarity. Cache it once you have hundreds of files --
    but if you cache, key the cache on the DIRECTORY and check that key BEFORE
    any freshness short-circuit. A TTL cache that returns early without
    re-checking which project it was built for leaks memories across projects.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # target is NOT unique: one memory contributes several atoms.
    conn.execute("CREATE VIRTUAL TABLE m USING fts5(target, kind, content, "
                 "tokenize='porter unicode61')")

    intents: dict[str, list[str]] = {}
    for idx in ("MEMORY.md", *(p.name for p in sorted(memdir.glob("INDEX_*.md")))):
        p = memdir / idx
        if not p.is_file():
            continue
        try:
            for target, intent in _resolver_atoms(p.read_text(encoding="utf-8",
                                                              errors="replace")):
                intents.setdefault(target, []).append(intent)
        except OSError:
            continue

    for f in sorted(memdir.glob("*.md")):
        if f.name in ("MEMORY.md", "CATALOG.md"):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        desc = ""
        if match := re.search(r"^description:\s*(.+)$", text, re.M):
            desc = match.group(1).strip().strip('"')

        atoms = [("resolver", i) for i in intents.get(f.name, [])]
        if desc:
            atoms.append(("description", desc))
        atoms.append(("slug", f.stem.replace("_", " ")))

        seen = set()
        for kind, content in atoms:
            key = re.sub(r"\W+", " ", content.lower()).strip()
            if len(key) < MIN_ATOM_CHARS or key in seen:
                continue      # the same phrasing as both row and description
            seen.add(key)
            conn.execute("INSERT INTO m VALUES (?,?,?)", (f.name, kind, content))
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


def overlap(prompt: str, row) -> float:
    """Share of the prompt's terms named by this memory's slug + description.

    Corpus-independent by construction: it does not move when you add files, so
    unlike the BM25 floor it does not need recalibrating.
    """
    q = terms(prompt)
    if not q:
        return 0.0
    doc = terms(f"{row['target']} {row['content']}")
    return len(q & doc) / len(q)


def search(conn: sqlite3.Connection, prompt: str) -> list[dict]:
    q = sanitize(prompt)
    if not q:
        return []
    try:
        rows = conn.execute(
            # bm25() returns a NEGATIVE score where lower is better, so negate
            # it to get "bigger is better" and compare against the floor.
            # Fetch WIDE: atoms are short and numerous, so the best atom of a
            # good memory can otherwise be crowded out by several weak atoms
            # of another.
            "SELECT target, kind, content, -bm25(m) AS score FROM m "
            "WHERE m MATCH ? ORDER BY score DESC LIMIT ?",
            (q, MAX_HITS * 12)).fetchall()
    except sqlite3.OperationalError:
        return []

    # COLLAPSE ATOMS -> MEMORIES, keeping each memory's BEST atom.
    # Max, not sum: summing would reward a memory for being cited under many
    # resolver rows, which is a property of the corpus, not of relevance to
    # THIS prompt.
    best: dict[str, dict] = {}
    for r in rows:
        s = r["score"] * ATOM_WEIGHT.get(r["kind"], 0.9)
        if s < MIN_BM25 or overlap(prompt, r) < MIN_OVERLAP:
            continue
        prev = best.get(r["target"])
        if prev is None or s > prev["score"]:
            best[r["target"]] = {"target": r["target"], "kind": r["kind"],
                                 "content": r["content"], "score": s}
    return sorted(best.values(), key=lambda h: -h["score"])[:MAX_HITS]


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
            "SELECT target, kind, content, -bm25(m) AS score FROM m "
            "WHERE m MATCH ? ORDER BY score DESC LIMIT 4", (q,)).fetchall() if q else []
        print(f"\n{label}: {prompt!r}")
        if not rows:
            print("   (no FTS matches at all)")
        for r in rows:
            print(f"   {r['target'][:30]:30s} <{r['kind']:11s}> "
                  f"bm25={r['score']:6.3f} overlap={overlap(prompt, r):.2f}")
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
            lines.append(f"  - [{h['target'][:-3]}]({h['target']})")
            lines.append(f"    {h['content'][:200]}")
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
